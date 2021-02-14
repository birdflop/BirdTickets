import os
import discord
from discord.ext.commands import has_permissions
from dotenv import load_dotenv
from discord.ext import commands
import sqlite3
import chat_exporter
import io
from bs4 import BeautifulSoup
import asyncio

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')


async def get_prefix(client, message):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT prefix FROM guilds WHERE guildid = {message.channel.guild.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        return result[0]


bot = commands.Bot(command_prefix=get_prefix, intents=discord.Intents.all())


@bot.command(name='setprefix', help='Set the ticket category')
@has_permissions(administrator=True)
async def set_prefix(ctx, prefix):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        response = f"Setting prefix to {prefix}"
        print(f"UPDATE guilds SET prefix = ?' WHERE guildid = {ctx.guild.id};", (prefix, ))
        cursor.execute(f"UPDATE guilds SET prefix = ? WHERE guildid = {ctx.guild.id};", (prefix, ))
        await ctx.channel.send(response)


@bot.event
async def on_ready():
    print("I am running")
    await bot.change_presence(activity=discord.Game(name="birdflop.com"))
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = """CREATE TABLE IF NOT EXISTS guilds (
                        guildid bigint PRIMARY KEY,
                        panelmessage bigint,
                        ticketscategory bigint,
                        nextticketid bigint NOT NULL,
                        transcriptchannel bigint,
                        prefix varchar(6) DEFAULT '-');"""
        cursor.execute(command)
        command = """CREATE TABLE IF NOT EXISTS tickets (
                        ticketchannel bigint PRIMARY KEY,
                        owner bigint NOT NULL,
                        parentguild bigint NOT NULL,
                        FOREIGN KEY (parentguild) REFERENCES guilds (guildid));"""
        cursor.execute(command)


@bot.event
async def on_guild_join(guild):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"""INSERT INTO guilds (guildid, panelmessage, ticketscategory, nextticketid, transcriptchannel)
                        VALUES({guild.id}, null, null, 1, null, '-');"""
        cursor.execute(command)


@bot.event
async def on_member_remove(member):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT ticketchannel FROM tickets WHERE owner = {member.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        for r in result:
            channel = await bot.fetch_channel(r)
            guild = channel.guild
            if discord.utils.get(guild.members, id=int(member.id)) is None:
                await channel.send("The ticket owner left the Discord. This ticket will now automatically close")
                await saveandclose(channel)


@bot.command(name='add', help='Add someone to a ticket')
async def add(ctx, user: discord.Member):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT COUNT(*) FROM tickets WHERE ticketchannel = {ctx.channel.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result[0] > 0:
            await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)


@bot.command(name='getprefix', help='Get prefix')
async def add(ctx, user: discord.Member):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT prefix FROM guilds WHERE guildid = {ctx.channel.guild.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result[0] > 0:
            await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)


@bot.command(name='remove', help='Remove someone from a ticket')
async def remove(ctx, user: discord.Member):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT COUNT(*) FROM tickets WHERE ticketchannel = {ctx.channel.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result[0] > 0:
            await ctx.channel.set_permissions(user, read_messages=None, send_messages=None)


@bot.command(name='close', help='Close a ticket')
async def close(ctx):
    await saveandclose(ctx.channel)


async def saveandclose(channel):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT COUNT(*) FROM tickets WHERE ticketchannel = {channel.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result[0] > 0:
            cursor = db.cursor()
            command = f"SELECT transcriptchannel FROM guilds WHERE guildid = {channel.guild.id} LIMIT 1;"
            cursor.execute(command)
            result = cursor.fetchone()
            transcript_channel_id = result[0]
            if transcript_channel_id:
                transcript_channel = discord.utils.get(channel.guild.channels, id=transcript_channel_id)
                if transcript_channel:
                    transcript = await get_transcript(channel)
                    embedVar = discord.Embed(title='Preparing Transcript', description='Please wait...', color=0xffff00)
                    msg_var = await channel.send(embed=embedVar)
                    await transcript_channel.send(file=transcript)
                    embedVar = discord.Embed(title='Transcript Created', description='Transcript was successfully created.', color=0x00ff00)
                    await msg_var.edit(embed=embedVar)
            transcript = await get_transcript(channel)
            cursor = db.cursor()
            print(channel.id)
            command = f"SELECT owner FROM tickets WHERE ticketchannel = {channel.id} LIMIT 1;"
            cursor.execute(command)
            result = cursor.fetchone()
            ticket_owner = bot.get_user(result[0])
            embedVar = discord.Embed(title='Ticket Transcript', description=f'Thank you for creating a ticket in **{channel.guild.name}**. A transcript of your conversation is attached.', color=0x00ffff)
            await ticket_owner.send(embed=embedVar, file=transcript)
            cursor = db.cursor()
            command = f"DELETE FROM tickets WHERE ticketchannel = {channel.id};"
            cursor.execute(command)
            await channel.delete()


async def get_transcript(channel):
    messages_limit = 2000
    transcript = await chat_exporter.export(channel, messages_limit, 'America/New_York')

    # Convert transcript bytes into .html file
    transcript_file = discord.File(io.BytesIO(transcript.encode()), filename=f"transcript-{channel.name}.html")

    # Check number of messages
    soup = BeautifulSoup(transcript, "html.parser")
    messages = soup.find("div", class_="info__channel-message-count").getText().split(" ")[0]

    # Warn if file reaches message number limit
    if int(messages) == messages_limit:
        await channel.send(
            f'WARNING: Channel contains over {messages_limit} messages, so the transcript may have been truncated.')

    # Send transcript
    return transcript_file


@bot.command()
async def make_raw_transcript(ctx):
    # Create transcript
    await ctx.send("Please wait, creating transcript...")
    messages_limit = 2000
    messages = await ctx.channel.history(limit=messages_limit).flatten()
    try:
        with open("transcript.txt", "w", encoding="utf-8") as text_transcript:
            for message in reversed(messages):
                created_at = message.created_at.strftime("[%m-%d-%y %I:%M:%S %p]")
                if message.content == "":
                    message.content = "Non-Text Information: See HTML transcript for more information."
                text_transcript.write(created_at + " " + message.author.name + "#" + str(
                    message.author.discriminator) + " | " + message.content + "\n")
        await ctx.send(file=discord.File('transcript.txt'))
    finally:
        os.remove('transcript.txt')


@bot.command(name='setcategory', help='Set the ticket category')
@has_permissions(administrator=True)
async def set_category(ctx, category_id):
    category = discord.utils.get(ctx.guild.categories, id=int(category_id))

    if category:
        with sqlite3.connect("data.db") as db:
            cursor = db.cursor()
            response = f"Setting category to {category_id}"
            command = f"""UPDATE guilds
                            SET ticketscategory = {category_id}
                            WHERE guildid = {ctx.guild.id};"""
            cursor.execute(command)
            await ctx.send(response)


@bot.command(name='query', help='Debug command')
async def query(ctx, arg):
    if ctx.author.id == 322764955516665856 or ctx.author.id == 223585930093658122:
        with sqlite3.connect("data.db") as db:
            cursor = db.cursor()
            cursor.execute(arg)
            result = cursor.fetchall()
            await ctx.author.send(result)


@bot.command(name='setlog', help='Set the log channel')
@has_permissions(administrator=True)
async def set_log(ctx, channel: discord.TextChannel):
    channel = discord.utils.get(ctx.guild.channels, id=channel.id)
    if channel:
        with sqlite3.connect("data.db") as db:
            cursor = db.cursor()
            response = f"Setting logs to {channel}"
            command = f"""UPDATE guilds
                            SET transcriptchannel = {channel.id}
                            WHERE guildid = {ctx.guild.id};"""
            cursor.execute(command)
            await ctx.send(response)


@bot.command(name='panel', help='Create a panel')
@has_permissions(administrator=True)
async def panel(ctx, color=39393):
    channel = ctx.channel
    embed_var = discord.Embed(title="Need Help?", color=int(color), description="React below to create a support ticket.")
    embed_var.set_footer(text="Powered by Birdflop Hosting")
    p = await channel.send(embed=embed_var)
    await p.add_reaction('🎟️')
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"""UPDATE guilds
                        SET panelmessage = {p.id}
                        WHERE guildid = {ctx.guild.id};"""
        cursor.execute(command)


@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT COUNT(*) FROM guilds WHERE panelmessage = {payload.message_id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result[0] > 0:
            guild = bot.get_guild(payload.guild_id)
            channel = discord.utils.get(guild.channels, id=payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            member = await guild.fetch_member(payload.user_id)
            await message.remove_reaction('🎟️', member)
            cursor = db.cursor()
            command = f"SELECT * FROM tickets WHERE parentguild = {payload.guild_id} AND owner = {payload.user_id} LIMIT 1;"
            cursor.execute(command)
            result = cursor.fetchone()
            if result:
                user = await guild.fetch_member(payload.user_id)
                mention = user.mention
                reply = f"You already have a ticket open. Please state your issue here {mention}"  # TODO Mention them
                cursor = db.cursor()
                command = f"SELECT ticketchannel FROM tickets WHERE owner = {payload.user_id} AND parentguild = {payload.guild_id} LIMIT 1;"
                cursor.execute(command)
                result = cursor.fetchone()
                guild = bot.get_guild(payload.guild_id)
                channel = discord.utils.get(guild.channels, id=result[0])
                await channel.send(reply)
            else:
                cursor = db.cursor()
                command = f"SELECT ticketscategory FROM guilds WHERE guildid = {payload.guild_id} LIMIT 1;"
                cursor.execute(command)
                result = cursor.fetchone()
                category = discord.utils.get(guild.categories, id=result[0])
                cursor = db.cursor()
                command = f"SELECT nextticketid FROM guilds WHERE guildid = {payload.guild_id} LIMIT 1;"
                cursor.execute(command)
                result = cursor.fetchone()
                nextid = result[0]
                cursor = db.cursor()
                command = f"UPDATE guilds SET nextticketid = {nextid + 1} WHERE guildid = {payload.guild_id};"
                cursor.execute(command)
                channel = await guild.create_text_channel(f'ticket-{nextid}', category=category)
                await channel.set_permissions(member, read_messages=True, send_messages=True)
                await channel.send(f"Hello {member.mention}, please explain your issue in as much detail as possible.")
                cursor = db.cursor()
                command = f"""INSERT INTO tickets (ticketchannel, owner, parentguild)
                                VALUES({channel.id}, {payload.user_id}, {payload.guild_id});"""
                cursor.execute(command)
                db.commit()
                cursor.close()
                await asyncio.sleep(30*60)
                if not await channel.history().get(author__id=payload.user_id):
                    await channel.send(f"{member.mention}, are you there? This ticket will automatically be closed after 30 minutes if you do not respond.")
                    await asyncio.sleep(30*60)
                    if not await channel.history().get(author__id=payload.user_id):
                        await saveandclose(channel)


bot.run(TOKEN)

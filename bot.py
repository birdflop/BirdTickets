import os
import discord
from discord.ext.commands import has_permissions
from dotenv import load_dotenv
from discord.ext import commands
import sqlite3
import chat_exporter
import io
import asyncio
import requests
import json

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
messages_limit = 2000


async def get_prefix(client, message):
    if isinstance(message.channel, discord.channel.DMChannel):
        return '-'
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT prefix FROM guilds WHERE guildid = {message.channel.guild.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result:
            return result[0]
        return '-'


bot = commands.Bot(command_prefix=get_prefix, intents=discord.Intents.all())


@bot.command(name='setprefix', help='Set the ticket category')
@has_permissions(administrator=True)
async def set_prefix(ctx, prefix):
    if ctx.guild is None:
        return
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        print(f"UPDATE guilds SET prefix = ?' WHERE guildid = {ctx.guild.id};", (prefix, ))
        cursor.execute(f"UPDATE guilds SET prefix = ? WHERE guildid = {ctx.guild.id};", (prefix, ))
        response = f"Prefix set to {prefix}."
        await ctx.channel.send(response)


@bot.command(name='reseticketdata', help='Reset all ticket data')
@has_permissions(administrator=True)
async def reset_ticket_data(ctx):
    if ctx.guild is None:
        return
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"DELETE FROM tickets WHERE parentguild = {ctx.guild.id};"
        cursor.execute(command)
        await ctx.channel.send("All tickets have been removed from the database")


@bot.event
async def on_ready():
    print("I am running")
    await bot.change_presence(activity=discord.Game(name="birdflop.com"))
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = """CREATE TABLE IF NOT EXISTS guilds (
                        guildid int PRIMARY KEY,
                        panelmessage int,
                        ticketscategory int,
                        nextticketid int NOT NULL,
                        transcriptchannel int,
                        prefix char(2) DEFAULT '-');"""
        cursor.execute(command)
        command = """CREATE TABLE IF NOT EXISTS tickets (
                        ticketchannel int PRIMARY KEY,
                        owner int NOT NULL,
                        parentguild int NOT NULL,
                        FOREIGN KEY (parentguild) REFERENCES guilds (guildid));"""
        cursor.execute(command)


@bot.event
async def on_guild_join(guild):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"""INSERT INTO guilds (guildid, panelmessage, ticketscategory, nextticketid, transcriptchannel, prefix)
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
    if ctx.guild is None:
        return
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT COUNT(*) FROM tickets WHERE ticketchannel = {ctx.channel.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result[0] > 0:
            await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)


bot.remove_command('help')
@bot.command(name='help', help='Shows this message')
async def help(ctx):
    if ctx.guild is None:
        return
    embed_var = discord.Embed(title='BirdTickets Commands', color=39393)
    embed_var.add_field(name="Player commands",
                        value="__new__ - Create a new ticket\n"
                              "__close__ - Close an existing ticket\n"
                              "__add__ - Add someone to a ticket\n"
                              "__remove__ - Remove someone from a ticket"
                              "__invite__ - Invite BirdTickets to your serer", inline=False)
    if ctx.author.guild_permissions.administrator:
        embed_var.add_field(name="Admin commands",
                            value="__panel__ - Create a support panel\n"
                                  "__setprefix__ - Change the prefix\n"
                                  "__setlog__ - Save transcripts to a channel\n"
                                  "__setcategory__ - Set the ticket category\n"
                                  "__removelog__ - Stop saving transcripts\n"
                                  "__resetticketdata__ - Reset all ticket data\n", inline=False)
    await ctx.reply(embed=embed_var)


bot.remove_command('invite')
@bot.command(name='invite', help='Get the bot''s invite link')
async def invite(ctx):
    embed_var = discord.Embed(title='BirdTickets Invite', color=39393, description="https://discord.com/api/oauth2/authorize?client_id=809975422640717845&permissions=126032&scope=bot")
    await ctx.reply(embed=embed_var)

@bot.command(name='remove', help='Remove someone from a ticket')
async def remove(ctx, user: discord.Member):
    if ctx.guild is None:
        return
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT COUNT(*) FROM tickets WHERE ticketchannel = {ctx.channel.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result[0] > 0:
            await ctx.channel.set_permissions(user, read_messages=None, send_messages=None)


@bot.command(name='close', help='Close a ticket')
async def close(ctx):
    if ctx.guild is None:
        return
    with sqlite3.connect("data.db") as db:
        # if ticket channel, saveandclose
        cursor = db.cursor()
        command = f"SELECT COUNT(*) FROM tickets WHERE ticketchannel = {ctx.channel.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result[0] > 0:
            await saveandclose(ctx.channel)
        else:
            # check the user for their ticket channel in that guild
            cursor = db.cursor()
            command = f"SELECT ticketchannel FROM tickets WHERE owner = {ctx.author.id} AND parentguild = {ctx.guild.id} LIMIT 1;"
            cursor.execute(command)
            result = cursor.fetchone()
            if result:
                channel = ctx.guild.get_channel(result[0])
                await ctx.reply(f"Use that command in {channel.mention}.")
            else:
                await ctx.reply(f"You do not have an open ticket.")


async def saveandclose(channel):
    with sqlite3.connect("data.db") as db:
        embed_var = discord.Embed(title='Preparing Transcript', description='Please wait...', color=0xffff00)
        msg_var = await channel.send(embed=embed_var)
        cursor = db.cursor()
        command = f"SELECT transcriptchannel FROM guilds WHERE guildid = {channel.guild.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        transcript_channel_id = result[0]
        cursor = db.cursor()
        command = f"SELECT owner FROM tickets WHERE ticketchannel = {channel.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        ticket_owner = bot.get_user(result[0])
        if transcript_channel_id:
            transcript_channel = discord.utils.get(channel.guild.channels, id=transcript_channel_id)
            if transcript_channel:
                transcript_file_1, transcript_file_2, binflop_link, truncated = await get_transcript(channel)
                embed_var = discord.Embed(title=channel.name,
                                          description=f"Created by {ticket_owner.mention} ({ticket_owner.name}#{ticket_owner.discriminator}). "
                                                      f"Text transcript at [bin.birdflop.com]({binflop_link}).",
                                          color=39393)
                await transcript_channel.send(embed=embed_var)
                await transcript_channel.send(file=transcript_file_1)
                embed_var = discord.Embed(title='Transcript Created', description='Transcript was successfully created.', color=39393)
                await msg_var.edit(embed=embed_var)
        if truncated:
            global messages_limit
            embed_var = discord.Embed(title='Ticket Transcript',
                                     description=f'Thank you for creating a ticket in **{channel.guild.name}**. Your transcript contained over {messages_limit} messages, so it has been truncated to the most recent {messages_limit}. An HTML transcript of your conversation is attached. Alternatively, you can view a text transcript at [bin.birdflop.com]({binflop_link}).',
                                     color=39393)
        else:
            embed_var = discord.Embed(title='Ticket Transcript',
                                     description=f'Thank you for creating a ticket in **{channel.guild.name}**. A transcript of your conversation is attached. Alternatively, you can view a text transcript at [bin.birdflop.com]({binflop_link}).',
                                     color=39393)
        await ticket_owner.send(embed=embed_var, file=transcript_file_2)
        cursor = db.cursor()
        command = f"DELETE FROM tickets WHERE ticketchannel = {channel.id};"
        cursor.execute(command)
        await channel.delete()


async def get_transcript(channel):
    global messages_limit
    messages = await channel.history(limit=messages_limit).flatten()
    # Warn if file reaches message number limit
    truncated = ''
    if len(messages) == messages_limit:
        truncated = '-truncated'
    try:
        with open(f"transcript-{channel.id}.txt", "w", encoding="utf-8") as text_transcript:
            for message in reversed(messages):
                created_at = message.created_at.strftime("[%m-%d-%y %I:%M:%S %p]")
                if message.content == "":
                    message.content = "Non-Text Information: See HTML transcript for more information."
                text_transcript.write(created_at + " " + message.author.name + "#" + str(
                    message.author.discriminator) + " | " + message.content + "\n")
        with open(f"transcript-{channel.id}.txt", "r", encoding="utf-8") as text_transcript:
            req = requests.post('https://bin.birdflop.com/documents', data=text_transcript.read().encode('utf-8'))
            key = json.loads(req.content)['key']
        binflop_link = 'https://bin.birdflop.com/' + key
    finally:
        os.remove(f'transcript-{channel.id}.txt')

    transcript = await chat_exporter.raw_export(channel, messages, 'America/New_York')

    # make transcript file
    transcript_file_1, transcript_file_2 = discord.File(io.BytesIO(transcript.encode()), filename=f'{channel.name}{truncated}.html'), discord.File(io.BytesIO(transcript.encode()), filename=f'{channel.name}{truncated}.html')

    # Send transcript
    return transcript_file_1, transcript_file_2, binflop_link, bool(truncated)


@bot.command(name='setcategory', help='Set the ticket category')
@has_permissions(administrator=True)
async def set_category(ctx, category_id):
    if ctx.guild is None:
        return
    category = discord.utils.get(ctx.guild.categories, id=int(category_id))
    if category:
        with sqlite3.connect("data.db") as db:
            cursor = db.cursor()
            response = f"Setting category to {category_id}"
            command = f"""UPDATE guilds
                            SET ticketscategory = {category_id}
                            WHERE guildid = {ctx.guild.id};"""
            cursor.execute(command)
            await ctx.reply(response)


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
    if ctx.guild is None:
        return
    channel = discord.utils.get(ctx.guild.channels, id=channel.id)
    if channel:
        with sqlite3.connect("data.db") as db:
            cursor = db.cursor()
            response = f"Setting logs to {channel.mention}"
            command = f"""UPDATE guilds
                            SET transcriptchannel = {channel.id}
                            WHERE guildid = {ctx.guild.id};"""
            cursor.execute(command)
            await ctx.reply(response)


@bot.command(name='removelog', help='Remove the log channel')
@has_permissions(administrator=True)
async def remove_log(ctx):
    if ctx.guild is None:
        return
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"""UPDATE guilds
                        SET transcriptchannel = null
                        WHERE guildid = {ctx.guild.id};"""
        cursor.execute(command)
        response = f"No longer logging transcripts."
        await ctx.reply(response)


@bot.command(name='panel', help='Create a panel')
@has_permissions(administrator=True)
async def panel(ctx, color=39393):
    if ctx.guild is None:
        return
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


@bot.command(name='new', help='Create a new ticket')
async def new(ctx):
    if ctx.guild is None:
        return
    member = await ctx.guild.fetch_member(ctx.author.id)
    guild = ctx.guild
    await create_ticket(guild, member)


@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.guild_id is None:
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
            await create_ticket(guild, member)


async def create_ticket(guild, member):
    with sqlite3.connect("data.db") as db:
        cursor = db.cursor()
        command = f"SELECT ticketchannel FROM tickets WHERE parentguild = {guild.id} AND owner = {member.id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result:
            channel = discord.utils.get(guild.channels, id=result[0])
            reply = f"You already have a ticket open. Please state your issue here {member.mention}"
            await channel.send(reply)
        else:
            cursor = db.cursor()
            command = f"SELECT ticketscategory, nextticketid FROM guilds WHERE guildid = {guild.id} LIMIT 1;"
            cursor.execute(command)
            result = cursor.fetchone()
            category = discord.utils.get(guild.categories, id=result[0])
            nextid = result[1]
            cursor = db.cursor()
            command = f"UPDATE guilds SET nextticketid = {nextid + 1} WHERE guildid = {guild.id};"
            cursor.execute(command)
            channel = await guild.create_text_channel(f'ticket-{nextid}', category=category)
            channel_id = channel.id
            await channel.set_permissions(member, read_messages=True, send_messages=True)
            await channel.send(f"Hello {member.mention}, please explain your issue in as much detail as possible.")
            cursor = db.cursor()
            command = f"""INSERT INTO tickets (ticketchannel, owner, parentguild)
                            VALUES({channel.id}, {member.id}, {guild.id});"""
            cursor.execute(command)
            db.commit()
            cursor.close()
            guild = channel.guild
            await asyncio.sleep(30*60)
            channel = guild.get_channel(channel_id)
            if channel:
                if not await channel.history.get(author__id=member.id):
                    await channel.send(f"{member.mention}, are you there? This ticket will automatically be closed after 30 minutes if you do not respond.")
                    await asyncio.sleep(30*60)
                    channel = guild.get_channel(channel_id)
                    if channel:
                        if not await channel.history.get(author__id=member.id):
                            await saveandclose(channel)


bot.run(TOKEN)

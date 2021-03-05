import os
import discord
from discord.ext.commands import has_permissions
from dotenv import load_dotenv
from discord.ext import commands, tasks
import chat_exporter
import io
import asyncio
import requests
import json
import time
from datetime import datetime
import mysql.connector

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
messages_limit = 2000
db = mysql.connector.connect(host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASS'),
                             database="s136_data")


async def get_prefix(client, message):
    if isinstance(message.channel, discord.channel.DMChannel):
        return '-'
    cursor = db.cursor()
    command = f"SELECT prefix FROM guilds WHERE id = {message.channel.guild.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result:
        return result[0]
    return '-'


async def get_prefix_from_guild(guild_id):
    cursor = db.cursor()
    command = f"SELECT prefix FROM guilds WHERE id = {guild_id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result:
        return result[0]
    return '-'


bot = commands.Bot(command_prefix=get_prefix, intents=discord.Intents.all())
bot.remove_command('help')
bot.remove_command('invite')


@bot.command(name='setprefix', help='Set the ticket category')
@has_permissions(administrator=True)
async def set_prefix(ctx, prefix):
    if ctx.guild is None:
        return
    if len(prefix) <= 2:
        cursor = db.cursor()
        cursor.execute(f"UPDATE guilds SET prefix = '{prefix}' WHERE id = {ctx.guild.id};")
        db.commit()
        response = f"Prefix set to {prefix}."
        await ctx.channel.send(response)
    else:
        ctx.reply(f"`{prefix}` is too long. The maximum prefix length is 2.")


@bot.event
async def on_ready():
    t = time.strftime("%b %d, %I:%M:%S %p")
    print(f"[{t}] I am running")
    await bot.change_presence(activity=discord.Game(name="birdflop.com"))
    cursor = db.cursor()
    command = """CREATE TABLE IF NOT EXISTS guilds (
                    id bigint PRIMARY KEY,
                    panel bigint,
                    category bigint,
                    next int NOT NULL,
                    transcript bigint,
                    prefix char(2) DEFAULT '-');"""
    cursor.execute(command)
    db.commit()
    cursor = db.cursor()
    command = """CREATE TABLE IF NOT EXISTS tickets (
                 channel bigint PRIMARY KEY,
                 creator bigint NOT NULL,
                 guild bigint NOT NULL,
                 expiry int(11),
                 FOREIGN KEY (guild) REFERENCES guilds (id));"""
    cursor.execute(command)
    db.commit()
    now = int(time.time())
    cursor = db.cursor()
    command = f"SELECT expiry, channel FROM tickets WHERE expiry > 0 AND expiry < {now};"
    cursor.execute(command)
    result = cursor.fetchall()
    for r in result:
        if 0 < r[0] < now:
            channel = bot.get_channel(r[1])
            if channel:
                await channel.send("This ticket has been automatically closed.")
                await saveandclose(channel)
            else:
                cursor = db.cursor()
                command = f"DELETE FROM tickets WHERE channel = {r[1]};"
                cursor.execute(command)
                db.commit()
        else:
            print("[ERROR] THIS SHOULD NEVER HAPPEN BUT IF IT DOES I NEED TO FIX")


@bot.event
async def on_guild_join(guild):
    cursor = db.cursor()
    command = f"""INSERT IGNORE INTO guilds (id, panel, category, next, transcript, prefix)
                  VALUES({guild.id}, NULL, NULL, 1, NULL, '-');"""
    cursor.execute(command)
    db.commit()


@bot.event
async def on_member_remove(member):
    cursor = db.cursor()
    command = f"SELECT channel FROM tickets WHERE creator = {member.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result and result[0]:
        channel = await bot.fetch_channel(result[0])
        guild = channel.guild
        if discord.utils.get(guild.members, id=int(member.id)) is None:
            await channel.send("The ticket owner left the Discord. Closing ticket...")
            await saveandclose(channel)


@bot.command(name='add', help='Add someone to a ticket')
async def add(ctx, user: discord.Member):
    if ctx.guild is None:
        return
    cursor = db.cursor()
    command = f"SELECT COUNT(*) FROM tickets WHERE channel = {ctx.channel.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result and result[0] > 0:
        await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
        embed_var = discord.Embed(title='User Added', color=0x22dd22,
                                  description=f'{user.mention} has been added to {ctx.channel.mention}')
        await ctx.send(embed=embed_var)


@bot.command(name='help', help='Shows this message')
async def help(ctx):
    if ctx.guild is None:
        return
    embed_var = discord.Embed(title='BirdTickets Commands', color=0x6592e6)
    embed_var.add_field(name="Player commands",
                        value="__new__ - Create a new ticket\n"
                              "__close__ - Close an existing ticket\n"
                              "__add__ - Add someone to a ticket\n"
                              "__remove__ - Remove someone from a ticket\n"
                              "__invite__ - Invite BirdTickets to your server",
                        inline=False)
    if is_staff(ctx.author, ctx.guild):
        embed_var.add_field(name="Staff commands",
                            value="__persist__ - Prevent a ticket from expiring\n"
                                  "__unpersist__ - Make a ticket unpersist\n"
                                  "__resolved__ - Mark a ticket as resolved",
                            inline=False)
    if ctx.author.guild_permissions.administrator:
        embed_var.add_field(name="Admin commands",
                            value="__panel__ - Create a support panel\n"
                                  "__setprefix__ - Change the prefix\n"
                                  "__setcategory__ - Set the ticket category\n"
                                  "__setlog__ - Save transcripts to a channel\n"
                                  "__removelog__ - Stop saving transcripts",
                            inline=False)
    await ctx.reply(embed=embed_var)


def is_staff(member, guild):
    cursor = db.cursor()
    command = f"SELECT category FROM guilds WHERE id = {guild.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result and result[0]:
        for c in guild.categories:
            if c.id == result[0]:
                perms = c.permissions_for(member)
                if perms.send_messages:
                    return True
                return False
    return False


@bot.command(name='invite', help='Get the bot''s invite link')
async def invite(ctx):
    embed_var = discord.Embed(title='BirdTickets Invite', color=0x6592e6,
                              description="See setup instructions [here](https://github.com/Pemigrade/BirdTickets)")
    await ctx.reply(embed=embed_var)


@bot.command(name='remove', help='Remove someone from a ticket')
async def remove(ctx, user: discord.Member):
    if ctx.guild is None:
        return
    cursor = db.cursor()
    command = f"SELECT creator FROM tickets WHERE channel = {ctx.channel.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result and result[0] != user.id:
        await ctx.channel.set_permissions(user, read_messages=None, send_messages=None)
        embed_var = discord.Embed(title='User Removed', color=0xdd2222,
                                  description=f'{user.mention} has been removed from {ctx.channel.mention}')
        await ctx.send(embed=embed_var)


@bot.command(name='close', help='Close a ticket')
async def close(ctx):
    if ctx.guild is None:
        return
    cursor = db.cursor()
    command = f"SELECT COUNT(*) FROM tickets WHERE channel = {ctx.channel.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result:
        if result[0] > 0:
            await saveandclose(ctx.channel)
        else:
            # check the user for their ticket channel in that guild
            cursor = db.cursor()
            command = f"SELECT channel FROM tickets WHERE creator = {ctx.author.id} AND guild = {ctx.guild.id} LIMIT 1;"
            cursor.execute(command)
            result = cursor.fetchone()
            if result:
                channel = ctx.guild.get_channel(result[0])
                await ctx.reply(f"Use that command in {channel.mention}.")
            else:
                await ctx.reply(f"You do not have an open ticket.")


async def saveandclose(channel):
    embed_var = discord.Embed(title='Preparing Transcript', description='Please wait...', color=0xffff00)
    msg_var = await channel.send(embed=embed_var)
    cursor = db.cursor()
    command = f"SELECT transcript FROM guilds WHERE id = {channel.guild.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    transcript_channel_id = result[0]
    cursor = db.cursor()
    command = f"SELECT creator FROM tickets WHERE channel = {channel.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    ticket_owner = bot.get_user(result[0])
    transcript_file_1, transcript_file_2, binflop_link, truncated = await get_transcript(channel)
    transcript_channel = None
    if transcript_channel_id:
        transcript_channel = discord.utils.get(channel.guild.channels, id=transcript_channel_id)
        if transcript_channel:
            embed_var = discord.Embed(title=channel.name,
                                      description=f"Created by {ticket_owner.mention} ({ticket_owner.name}#{ticket_owner.discriminator}). "
                                                  f"Text transcript at [bin.birdflop.com]({binflop_link}).",
                                      color=0x6592e6)
            await transcript_channel.send(embed=embed_var)
            await transcript_channel.send(file=transcript_file_1)
            embed_var = discord.Embed(title='Transcript Created', description='Transcript was successfully created.',
                                      color=0x6592e6)
            await msg_var.edit(embed=embed_var)
    if truncated:
        global messages_limit
        embed_var = discord.Embed(title='Ticket Transcript',
                                  description=f'Thank you for creating a ticket in **{channel.guild.name}**. Your transcript contained over {messages_limit} messages, so it has been truncated to the most recent {messages_limit}. An HTML transcript of your conversation is attached. Alternatively, you can view a text transcript at [bin.birdflop.com]({binflop_link}).',
                                  color=0x6592e6)
    else:
        embed_var = discord.Embed(title='Ticket Transcript',
                                  description=f'Thank you for creating a ticket in **{channel.guild.name}**. A transcript of your conversation is attached. Alternatively, you can view a text transcript at [bin.birdflop.com]({binflop_link}).',
                                  color=0x6592e6)
    try:
        await ticket_owner.send(embed=embed_var, file=transcript_file_2)
    except discord.errors.Forbidden:
        if transcript_channel:
            await transcript_channel.send(ticket_owner.name + " does not accept DMs")
    cursor = db.cursor()
    command = f"DELETE FROM tickets WHERE channel = {channel.id};"
    cursor.execute(command)
    db.commit()
    await channel.delete()


async def get_transcript(channel):
    global messages_limit
    messages = await channel.history(limit=messages_limit).flatten()
    messages_html = messages[:]
    # Warn if file reaches message number limit
    truncated = ''
    if len(messages) == messages_limit:
        truncated = '-truncated'
    try:
        with open(f"transcript-{channel.id}.txt", "w", encoding="utf-8") as text_transcript:
            for message in reversed(messages):
                created_at = message.created_at.strftime("[%m-%d-%y %I:%M:%S %p]")
                msg = message.content
                if not msg:
                    if message.embeds:
                        for embed in message.embeds:
                            if embed.title:
                                msg += "\n" + embed.title
                            if embed.description:
                                msg += " - " + embed.description
                    else:
                        msg = "Unknown message: See HTML transcript for more information."
                text_transcript.write(f"{created_at} {message.author.name}#{message.author.discriminator} | {msg}\n")
        with open(f"transcript-{channel.id}.txt", "r", encoding="utf-8") as text_transcript:
            req = requests.post('https://bin.birdflop.com/documents', data=text_transcript.read().encode('utf-8'))
            key = json.loads(req.content)['key']
        binflop_link = 'https://bin.birdflop.com/' + key
    finally:
        os.remove(f'transcript-{channel.id}.txt')

    transcript = await chat_exporter.raw_export(channel, messages_html, 'America/New_York')

    # make transcript file
    transcript_file_1, transcript_file_2 = discord.File(io.BytesIO(transcript.encode()),
                                                        filename=f'{channel.name}{truncated}.html'), discord.File(
        io.BytesIO(transcript.encode()), filename=f'{channel.name}{truncated}.html')

    # Send transcript
    return transcript_file_1, transcript_file_2, binflop_link, bool(truncated)


@bot.command(name='setcategory', help='Set the ticket category')
@has_permissions(administrator=True)
async def set_category(ctx, category_id):
    if ctx.guild is None:
        return
    category = discord.utils.get(ctx.guild.categories, id=int(category_id))
    if category:
        cursor = db.cursor()
        command = f"""UPDATE guilds
                        SET category = {category_id}
                        WHERE id = {ctx.guild.id};"""
        cursor.execute(command)
        db.commit()
        response = f"Category set to {category_id}"
        await ctx.reply(response)


@bot.command(name='q', help='Debug command')
async def q(ctx, arg):
    if ctx.author.id == 322764955516665856 or ctx.author.id == 223585930093658122:
        cursor = db.cursor()
        cursor.execute(arg)
        db.commit()
        result = cursor.fetchall()
        if result:
            await ctx.author.send(result)
        else:
            rows = cursor.rowcount
            await ctx.author.send(f" {rows} rows updated")


@bot.command(name='setlog', help='Set the log channel')
@has_permissions(administrator=True)
async def set_log(ctx, channel: discord.TextChannel):
    if ctx.guild is None:
        return
    channel = discord.utils.get(ctx.guild.channels, id=channel.id)
    if channel:
        cursor = db.cursor()
        command = f"""UPDATE guilds
                        SET transcript = {channel.id}
                        WHERE id = {ctx.guild.id};"""
        cursor.execute(command)
        db.commit()
        response = f"Set logs to {channel.mention}"
        await ctx.reply(response)


@bot.command(name='removelog', help='Remove the log channel')
@has_permissions(administrator=True)
async def remove_log(ctx):
    if ctx.guild is None:
        return
    cursor = db.cursor()
    command = f"""UPDATE guilds
                SET transcript = NULL
                WHERE id = {ctx.guild.id};"""
    cursor.execute(command)
    db.commit()
    response = f"No longer logging transcripts."
    await ctx.reply(response)


@bot.command(name='panel', help='Create a panel')
@has_permissions(administrator=True)
async def panel(ctx, color=0x6592e6):
    if ctx.guild is None:
        return
    channel = ctx.channel
    embed_var = discord.Embed(title="Need Help?", color=int(color),
                              description="React below to create a support ticket.")
    p = await channel.send(embed=embed_var)
    await p.add_reaction('🎟️')
    cursor = db.cursor()
    command = f"""UPDATE guilds
                    SET panel = {p.id}
                    WHERE id = {ctx.guild.id};"""
    cursor.execute(command)
    db.commit()


@bot.command(name='new', help='Create a new ticket')
async def new(ctx):
    if ctx.guild is None:
        return
    member = await ctx.guild.fetch_member(ctx.author.id)
    guild = ctx.guild
    await create_ticket(guild, member)


@bot.command(name='persist', help='Make the ticket persist')
async def persist(ctx):
    if ctx.guild is None:
        return
    if is_staff(ctx.author, ctx.guild):
        cursor = db.cursor()
        command = f"UPDATE tickets SET expiry = NULL WHERE channel = {ctx.channel.id} LIMIT 1;"
        cursor.execute(command)
        db.commit()
        if cursor.rowcount == 1:
            await ctx.reply("This ticket will now persist")


@bot.command(name='unpersist', help='Make the ticket unpersist')
async def unpersist(ctx):
    if ctx.guild is None:
        return
    if is_staff(ctx.author, ctx.guild):
        cursor = db.cursor()
        command = f"UPDATE tickets SET expiry = {int(time.time()) + 48 * 60 * 60} WHERE channel = {ctx.channel.id} LIMIT 1;"
        cursor.execute(command)
        db.commit()
        if cursor.rowcount == 1:
            await ctx.reply("This ticket will no longer persist")


@bot.command(name='resolved', help='Makes the ticket expire soon')
async def resolved(ctx):
    if ctx.guild is None:
        return
    if is_staff(ctx.author, ctx.guild):
        cursor = db.cursor()
        command = f"UPDATE tickets SET expiry = {int(time.time()) + 12 * 60 * 60} WHERE channel = {ctx.channel.id};"
        cursor.execute(command)
        db.commit()
        if cursor.rowcount == 1:
            await ctx.message.delete()
            cursor = db.cursor()
            command = f"SELECT creator FROM tickets WHERE channel = {ctx.channel.id} LIMIT 1;"
            cursor.execute(command)
            result = cursor.fetchone()
            owner = bot.get_user(result[0])
            await ctx.channel.send(
                f"{owner.mention}, this ticket has been marked as resolved and will automatically close in 12 hours. If you still have an issue, please explain it. Otherwise, you can say `{await get_prefix_from_guild(ctx.guild.id)}close` to close the ticket now.")


@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.guild_id is None:
        return
    if payload.emoji.name == "🎟️":
        cursor = db.cursor()
        command = f"SELECT COUNT(*) FROM guilds WHERE panel = {payload.message_id} LIMIT 1;"
        cursor.execute(command)
        result = cursor.fetchone()
        if result and result[0] > 0:
            guild = bot.get_guild(payload.guild_id)
            channel = discord.utils.get(guild.channels, id=payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            member = await guild.fetch_member(payload.user_id)
            await message.remove_reaction('🎟️', member)
            await create_ticket(guild, member)
    elif payload.emoji.name == "🔒":
        channel = bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        for r in message.reactions:
            if r.me and r.emoji == "🔒" and r.count > 1:
                cursor = db.cursor()
                command = f"SELECT COUNT(*) FROM tickets WHERE channel = {payload.channel_id} LIMIT 1;"
                cursor.execute(command)
                result = cursor.fetchone()
                if result and result[0] > 0:
                    guild = bot.get_guild(payload.guild_id)
                    await saveandclose(discord.utils.get(guild.channels, id=payload.channel_id))


async def create_ticket(guild, member):
    cursor = db.cursor()
    command = f"SELECT channel FROM tickets WHERE guild = {guild.id} AND creator = {member.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result:
        channel = guild.get_channel(result[0])
        if channel:
            reply = f"You already have a ticket open. Please state your issue here {member.mention}"
            await channel.send(reply)
            return
        else:
            cursor = db.cursor()
            command = f"DELETE FROM tickets WHERE channel = {result[0]} LIMIT 1;"
            cursor.execute(command)
            db.commit()
    cursor = db.cursor()
    command = f"SELECT category, next FROM guilds WHERE id = {guild.id} LIMIT 1;"
    cursor.execute(command)
    result = cursor.fetchone()
    if result:
        category = discord.utils.get(guild.categories, id=result[0])
        nextid = result[1]
        cursor = db.cursor()
        command = f"UPDATE guilds SET next = {nextid + 1} WHERE id = {guild.id};"
        cursor.execute(command)
        db.commit()
        channel = await guild.create_text_channel(f'ticket-{nextid}', category=category)
        await channel.set_permissions(member, read_messages=True, send_messages=True, view_channel=True)
        embed = discord.Embed(title="Closing Tickets",
                              description=f"When your issue has been resolved, react with 🔒 or type `{await get_prefix_from_guild(guild.id)}close` to close the ticket",
                              color=0x6592e6)
        ticket_message = await channel.send(
            f"Hello {member.mention}, please describe your issue in as much detail as possible.", embed=embed)
        await ticket_message.add_reaction("🔒")
        await ticket_message.pin(reason=f'Pinned first message in #{channel.name}')
        cursor = db.cursor()
        command = f"""INSERT INTO tickets (channel, creator, guild, expiry)
                        VALUES({channel.id}, {member.id}, {guild.id}, {int(time.time()) + 30 * 60});"""
        cursor.execute(command)
        db.commit()


@bot.event
async def on_message(message):
    if message.type == discord.MessageType.pins_add and message.author.id == bot.user.id:
        await message.delete()
    if not message.author.bot:
        if message.content == "<@!809975422640717845>":
            prefix = await get_prefix_from_guild(message.guild.id)
            await message.reply(f"my prefix is {prefix}")
        cursor = db.cursor()
        command = f"UPDATE tickets SET expiry = 0 WHERE channel = {message.channel.id} AND creator = {message.author.id} AND expiry IS NOT NULL LIMIT 1;"
        cursor.execute(command)
        db.commit()
        if cursor.rowcount == 1 and is_staff(message.author, message.guild):
            cursor = db.cursor()
            command = f"UPDATE tickets SET expiry = {int(time.time()) + 48 * 60 * 60} WHERE channel = {message.channel.id} AND creator != {message.author.id} AND expiry IS NOT NULL LIMIT 1;"
            cursor.execute(command)
            db.commit()
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandNotFound):
        print(f"Command {ctx.message.content} in {ctx.guild.name} not found")
    if isinstance(error, discord.Forbidden):
        print(f"Bot does not have permissions in {ctx.guild.name}")


@tasks.loop(seconds=1)
async def repeating_task():
    now = int(time.time())
    cursor = db.cursor()
    command = f"SELECT channel, creator, expiry FROM tickets WHERE expiry > 0;"
    cursor.execute(command)
    result = cursor.fetchall()
    if result:
        for r in result:
            expiry = r[2]
            if expiry - now == 24 * 60 * 60:
                channel = bot.get_channel(r[0])
                owner = bot.get_user(r[1])
                await channel.send(
                    f"This ticket has been inactive for 24 hours. It will automatically close after 24 more hours if you do not respond. If the issue has been resolved, you can say -close to close the ticket now. {owner.mention}")
            elif expiry - now == 15 * 60:
                channel = bot.get_channel(r[0])
                owner = bot.get_user(r[1])
                if not await channel.history().get(author__id=owner.id):
                    await channel.send(
                        f"{owner.mention}, this ticket will automatically close after 15 minutes if you do not describe your issue.")
            elif expiry - now == 0:
                channel = bot.get_channel(r[0])
                await channel.send("This ticket has been automatically closed.")
                await saveandclose(channel)

repeating_task.start()
bot.run(TOKEN)

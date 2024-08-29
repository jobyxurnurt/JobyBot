import discord
from discord.ext import commands
import spotipy
from youtube_dl import YoutubeDL
import requests
import json
import datetime
from datetime import datetime, timedelta, date
import asyncio
import yt_dlp
from googletrans import Translator, LANGUAGES
import operator
from transformers import pipeline, Conversation
import re
import math
import random
import sqlite3
import config

webhook_url = config.discord_hookurl
afk_users = {}

# Connect to the database
conn = sqlite3.connect('coinflip.db')
c = conn.cursor()

# Create table if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS coinflip
             (server_id integer, user_id integer, wins integer, losses integer)''')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')


@bot.command(pass_context = True, help='Join Your Current Channel')
async def join(ctx):
    # Check if the author is in a voice channel
    if ctx.author.voice:
        channel = ctx.message.author.voice.channel
        await channel.connect()
        await ctx.send("Yo I'm Here!")
    else:
        await ctx.send("You are not in a voice channel, you must be in a voice channel to run this command!")


@bot.command(pass_context = True, help='Leave Your Current Channel')
async def leave(ctx):
   await ctx.voice_client.disconnect()
   await ctx.send("Ight Bruh Ima Catch Ya!")

@bot.command(pass_context = True, help='I will let other users know you are not available')
async def afk(ctx):
    if ctx.author not in afk_users:
        afk_users[ctx.author] = True
        await ctx.send(f'{ctx.author.mention} is now AFK.')
    else:
        del afk_users[ctx.author]
        await ctx.send(f'{ctx.author.mention} is no longer AFK.')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    for mention in message.mentions:
        if mention in afk_users:
            if afk_users[mention]:
                data = {
                    "content": 'I am not here right now, I will be back.',
                    "username": mention.name,
                    "avatar_url": mention.display_avatar.url
                }
                try:
                    requests.post(webhook_url, json=data)
                except requests.exceptions.RequestException as e:
                    print(f"Error sending request: {e}")

    await bot.process_commands(message)

@bot.command(help='Random Fact')
async def fact(ctx):
    response = requests.get('https://uselessfacts.jsph.pl/random.json?language=en')
    data = response.json()
    fact = data['text']
    await ctx.send(fact)

@bot.command()
async def coinflip(ctx, player1: discord.Member, choice1, vs, player2: discord.Member, choice2):
    choices = ['heads', 'tails']
    if choice1.lower() not in choices or choice2.lower() not in choices:
        await ctx.send('Invalid choice. Please choose heads or tails.')
        return
    if choice1.lower() == choice2.lower():
        await ctx.send('Both players cannot choose the same side.')
        return
    flip = random.choice(choices)
    winner = player1 if flip == choice1.lower() else player2
    loser = player2 if flip == choice1.lower() else player1

    # Update the database
    c.execute("SELECT * FROM coinflip WHERE server_id = ? AND user_id = ?", (ctx.guild.id, winner.id))
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO coinflip VALUES (?, ?, 1, 0)", (ctx.guild.id, winner.id))
    else:
        c.execute("UPDATE coinflip SET wins = wins + 1 WHERE server_id = ? AND user_id = ?", (ctx.guild.id, winner.id))

    c.execute("SELECT * FROM coinflip WHERE server_id = ? AND user_id = ?", (ctx.guild.id, loser.id))
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO coinflip VALUES (?, ?, 0, 1)", (ctx.guild.id, loser.id))
    else:
        c.execute("UPDATE coinflip SET losses = losses + 1 WHERE server_id = ? AND user_id = ?", (ctx.guild.id, loser.id))

    conn.commit()

    await ctx.send(f'{flip.capitalize()}. {winner.mention} wins!')

@bot.command()
async def coinflipwins(ctx, user: discord.Member = None):
    if user is None:
        user = ctx.author
    c.execute("SELECT * FROM coinflip WHERE server_id = ? AND user_id = ?", (ctx.guild.id, user.id))
    row = c.fetchone()
    if row is None:
        await ctx.send(f'{user.mention} has no coinflip record.')
    else:
        wins = row[2]
        losses = row[3]
        await ctx.send(f'{user.mention}\'s coinflip record: {wins}-{losses}')


reminders = {}

@bot.command(name='reminder', help='Create a reminder')
async def reminder(ctx):
    await ctx.send('When would you like to be reminded? Today, or in a certain amount of days? Provide me with 0 if it\'s a time today, or any number that matches in how many days you\'d like to be reminded.')

    def check_days(message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check_days, timeout=60.0)
    except asyncio.TimeoutError:
        await ctx.send('Sorry, you took too long.')
        return

    try:
        days = int(msg.content)
    except ValueError:
        await ctx.send('Invalid input. Please provide a number.')
        return

    remind_date = datetime.now() + timedelta(days=days)

    await ctx.send(f'Okay, I will remind you on {remind_date.strftime("%B %d")}. What time would you like me to remind you?')

    def check_time(message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check_time, timeout=60.0)
    except asyncio.TimeoutError:
        await ctx.send('Sorry, you took too long.')
        return

    try:
        remind_time = datetime.strptime(msg.content, '%H:%M')
    except ValueError:
        await ctx.send('Invalid time format. Please use HH:MM.')
        return

    remind_datetime = remind_date.replace(hour=remind_time.hour, minute=remind_time.minute)

    await ctx.send('What is the message?')

    def check_message(message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check_message, timeout=60.0)
    except asyncio.TimeoutError:
        await ctx.send('Sorry, you took too long.')
        return

    reminders[len(reminders) + 1] = (remind_datetime, msg.content, ctx.author.id)

    await ctx.send('Reminder set!')

@bot.command(name='reminders', help='List all reminders')
async def reminders_list(ctx):
    if not reminders:
        await ctx.send('No reminders found.')
        return

    embed = discord.Embed(title='Reminders', color=discord.Color.blue())
    for reminder_id, (time, message, author_id) in reminders.items():
        user = bot.get_user(author_id)
        embed.add_field(name=f'{reminder_id}. {user.name}', value=f'Time: {time}\nMessage: {message}', inline=False)

    await ctx.send(embed=embed)

@bot.command(name='delete_reminder', help='Delete a reminder')
async def delete_reminder(ctx, reminder_id: int):
    if reminder_id not in reminders:
        await ctx.send('Reminder not found.')
        return

    del reminders[reminder_id]
    await ctx.send(f'Reminder with ID {reminder_id} deleted.')

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')

    while True:
        now = datetime.now()
        for reminder_id, (time, message, author_id) in list(reminders.items()):
            if time <= now:
                user = bot.get_user(author_id)
                await user.send(message)
                del reminders[reminder_id]

        await asyncio.sleep(1)

@bot.command(name='play')
async def play(ctx, url):
    vc = ctx.voice_client

    if not vc:
        await ctx.send('I need to be in a voice channel to play music.')
        return

    ydl_opts = {'format': '140', 'listformats': 'true'}
    ydl = yt_dlp.YoutubeDL(ydl_opts)
    info = ydl.extract_info(url, download=False)
    url2 = info['formats'][0]['url']
    source = discord.FFmpegPCMAudio(url2)
    vc.play(source)


bot.remove_command('help')


class CustomHelp(commands.DefaultHelpCommand):
    def __init__(self):
        super().__init__()
        self.no_category = 'Commands'
        self.command_attrs['help'] = 'List all commands'

    def get_ending_note(self):
        return ''

bot.help_command = CustomHelp()

@bot.command(name='translate', help='Translates text from any language to English')
async def translate(ctx, *args):
    text = ' '.join(args)
    translator = Translator()
    try:
        lang_from = translator.detect(text).lang
        result = translator.translate(text, src=lang_from, dest='en')
        await ctx.send(f"Translated from {LANGUAGES[lang_from].title()}: {result.text}")
    except Exception as e:
        await ctx.send('Error: ' + str(e))
    
# Load the question answering model
qa_model = pipeline("conversational")


@bot.command(name='answer', help='Asks a question and receives an answer')
async def answer(ctx, *, question):
    # Create a new conversation
    conversation = Conversation()

    # Add the user's question to the conversation
    conversation.add_user_input(question)

    # Use the model to generate an answer
    answer = qa_model(conversation)

    # Get the generated answer from the conversation
    generated_answer = answer.generated_responses[-1]

    await ctx.send(generated_answer)

operators = {
    '+': operator.add,
    '-': operator.sub,
    '*': operator.mul,
    '/': operator.truediv,
    'x': operator.mul,
    '^': operator.pow,
}

@bot.command(name='math')
async def math(ctx, expression):
    # Check if the expression contains parentheses
    if '(' in expression and ')' in expression:
        # Extract the expression inside the parentheses
        match = re.search(r'\(([^)]+)\)', expression)
        if match:
            sub_expression = match.group(1)
            # Evaluate the sub-expression
            sub_result = await evaluate_expression(sub_expression)
            # Replace the sub-expression with its result in the original expression
            expression = expression.replace(f'({sub_expression})', str(sub_result))

    # Check if the expression is a square root operation
    if expression.startswith('sqrt'):
        try:
            num = float(expression[4:])
            result = math.sqrt(num)
            await ctx.send(result)
        except ValueError:
            await ctx.send('Cannot calculate square root of a negative number')
        return

    # Split the expression into numbers and an operator
    num1, op, num2 = '', '', ''
    for char in expression:
        if char.isdigit() or char == '.':
            if op == '':
                num1 += char
            else:
                num2 += char
        else:
            op = char

    # Check if the operator is valid
    if op not in operators:
        await ctx.send('Invalid operator')
        return

    # Perform the calculation
    try:
        result = operators[op](float(num1), float(num2))
        await ctx.send(result)
    except ZeroDivisionError:
        await ctx.send('Cannot divide by zero')

async def evaluate_expression(ctx, expression):
    # Split the expression into numbers and an operator
    num1, op, num2 = '', '', ''
    for char in expression:
        if char.isdigit() or char == '.':
            if op == '':
                num1 += char
            else:
                num2 += char
        else:
            op = char

    # Check if the operator is valid
    if op not in operators:
        await ctx.send('Invalid operator')
        return

    # Perform the calculation
    try:
        result = operators[op](float(num1), float(num2))
        return result
    except ZeroDivisionError:
        return 'Cannot divide by zero'

bot.run(config.botkey)
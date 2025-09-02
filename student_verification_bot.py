"""
To run this script, in a screen session just do `python student_verification_bot.py`

I keep all of my env vars in a .env file which `load_dotenv()` loads into the environment.

Env variables:
- DISCORD_TOKEN: comes from the discord API. 
                 You will need to make a discord app for your bot which will DM users,
                 and give it permission to create DMs. I'd recommend asking chatgpt for help with this. 
- CHANNEL_ID: The ID from Discord for your channel that contains the message. 
              (Enable developer tools, right click on a channel -> Copy Channel ID)
- MESSAGE_ID: The ID for the individual discord message users will be interacting with the "+" emoji
- DATABASE_PATH: Where the user database should be stored on disk. Mine is saved to `student_emails.db`
"""

import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import aiosqlite
import re
from datetime import datetime

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.dm_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Replace the following/set env variables for each of these values to the message in discord that users
# will be reacting to
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
MESSAGE_ID = int(os.getenv('MESSAGE_ID'))
DATABASE_PATH = os.getenv('DATABASE_PATH')

pending_verifications = {}

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS student_emails (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                verified BOOLEAN DEFAULT FALSE
            )
        ''')
        await db.commit()

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await init_db()
    
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        try:
            message = await channel.fetch_message(MESSAGE_ID)
            print(f"Monitoring message: {MESSAGE_ID} in channel: {CHANNEL_ID}")
        except discord.NotFound:
            print(f"Message {MESSAGE_ID} not found in channel {CHANNEL_ID}")
        except discord.Forbidden:
            print(f"Bot doesn't have permission to access channel {CHANNEL_ID}")
    else:
        print(f"Channel {CHANNEL_ID} not found")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.message_id != MESSAGE_ID:
        return
    
    if payload.emoji.name != '➕':
        return
    
    if payload.user_id == bot.user.id:
        return
    
    user = await bot.fetch_user(payload.user_id)
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT email, verified FROM student_emails WHERE user_id = ?",
            (user.id,)
        )
        result = await cursor.fetchone()
        
        if result:
            email, verified = result
            if verified:
                await user.send(
                    f"You've already been verified with email: {email}. "
                    "You should have access to the course materials."
                )
            else:
                await user.send(
                    f"You've already submitted email: {email}. "
                    "It's pending verification. Please wait for approval."
                )
            return
    
    pending_verifications[user.id] = True
    
    try:
        await user.send(
            "Welcome! To verify your enrollment in the course, please reply with "
            "the email address you used to sign up for the course.\n\n"
            "Example: your.email@example.com"
        )
    except discord.Forbidden:
        print(f"Cannot send DM to user {user.name}")
        pending_verifications.pop(user.id, None)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if isinstance(message.channel, discord.DMChannel):
        if message.author.id in pending_verifications:
            email = message.content.strip()
            
            if not is_valid_email(email):
                await message.channel.send(
                    "That doesn't look like a valid email address. "
                    "Please send a valid email address (e.g., your.email@example.com)"
                )
                return
            
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute(
                    "SELECT email FROM student_emails WHERE user_id = ?",
                    (message.author.id,)
                )
                existing = await cursor.fetchone()
                
                if existing:
                    await message.channel.send(
                        f"You've already submitted an email: {existing[0]}. "
                        "If you need to update it, please contact an administrator."
                    )
                else:
                    await db.execute(
                        "INSERT INTO student_emails (user_id, username, email, submitted_at, verified) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            message.author.id,
                            str(message.author),
                            email,
                            datetime.now().isoformat(),
                            False
                        )
                    )
                    await db.commit()
                    
                    await message.channel.send(
                        f"Thank you! Your email ({email}) has been recorded and is pending verification. "
                        "You'll receive access to the course materials once verified."
                    )
                
                pending_verifications.pop(message.author.id, None)
    
    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

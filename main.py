import os

import asyncio
from dotenv import load_dotenv

from aiohttp_requests.request import check_website
from telegram.telegram_bot import TelegramBot
from database.aiosqlite.database_local import Database
from logger import logger

load_dotenv()
TOKEN = os.getenv('TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
URLS = [
    'https://teater-mikhailovski.ru',
    'https://bdt-tovstonogova.online',
    'https://ugolok-durova.online',
    'https://oktyabrsky-online.ru',
    'https://kislovodskiy-cirq.ru',
    'https://sochi-festival.ru',
    'https://greenteatr-vdnh.online',
    'https://alexandrinskiy-teatr.online',
    'https://lenkom-tickets.online',
    'https://simferopolskiy-cirq.ru',
    'https://navernadskogo.online',
    'https://nickulinacirk.site',
    'https://fontanke-spb.ru',
    'https://bolshoi-teatr.online',
    'https://zaryadie-online.ru',
    'https://kremlin-dvoretc.ru',
    'https://anapa-estrada.online',
    'https://mdt-europe.ru',
    'https://zimny-teatr.ru',
    'https://permsky-circus.ru',
    'https://kazan-cirq.ru',
    'https://sochinskiy-cirq.ru',
    'https://maly-theatr.online',
]


db = Database()
# Initialize the Telegram Bot
telegram_bot = TelegramBot(token=TOKEN, channel_id=CHAT_ID)

async def process_website_check(url):
    url, status, response_time, checked_at = await check_website(url)
    if status != 200:
        await db.log_status(url, status, response_time, checked_at)
        telegram_bot.add_to_queue(f"Site {url} is down! Status code: {status}")
    else:
        await db.log_status(url, status, response_time, checked_at)
    logger.info(f"{url} {status} {response_time} {checked_at}")

# Function to periodically check all websites
async def uptime_check(interval=800):
    while True:
        tasks = [process_website_check(url) for url in URLS]
        await asyncio.gather(*tasks)
        await asyncio.sleep(interval)

# Main function to start the bot and tasks
async def main():
    await db.init_db()  # Initialize the database
    asyncio.create_task(uptime_check())
    await telegram_bot.start_polling()

if __name__ == '__main__':
    asyncio.run(main())
import os
from datetime import datetime, timedelta

import asyncio
from dotenv import load_dotenv

from aiohttp_requests.request import check_website
from telegram.telegram_bot import TelegramBot
from database.aiosqlite.database_local import Database
from database.nebilet_postgresql.database_nebilet import DBConnection
from logs.logger import logger

load_dotenv()
TOKEN = os.getenv('TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_DATABASE = os.getenv('DB_DATABASE')
class UptimeMonitor:
    def __init__(self, token, chat_id, db_connection,
                 interval_between_checking=800,
                 time_wait_before_retrying=80,
                 delay_wait_before_retrying=5,
                 retries_in_repeated_requests=3):
        self.token = token
        self.chat_id = chat_id
        self.db = Database()
        self.telegram_bot = TelegramBot(token=self.token, channel_id=self.chat_id)
        self.db_connection = db_connection
        self.urls = []
        self.INTERVAL_BETWEEN_CHECKING = interval_between_checking
        self.TIME_WAIT_BEFORE_RETRYING = time_wait_before_retrying
        self.DELAY_WAIT_BEFORE_START_RETRYING = delay_wait_before_retrying
        self.RETRIES_IN_REPEATING_REQUESTS = retries_in_repeated_requests
        self.down_since = {}

    def _create_success_message(self, url, downtime):
        return f"🟢 Monitor is UP: {url} ( {url} ). It was down for {downtime}."

    def _create_error_message(self, url, status, error=None):
        downtime = self._calculate_downtime(url)
        message = f"🔴 Monitor is DOWN: {url} (Status: {status}). Down for: {downtime}."
        if error:
            message += f" Error: {error[:100]}..."
        return message

    def _calculate_downtime(self, url):
        downtime = datetime.utcnow() - self.down_since.get(url, datetime.utcnow())
        if downtime < timedelta(0):
            downtime = timedelta(0)
        return str(downtime).split('.')[0]

    async def check_site_until_up(self, url):
        self.down_since.setdefault(url, datetime.utcnow())
        current_wait_time = 0
        await asyncio.sleep(self.DELAY_WAIT_BEFORE_START_RETRYING)
        while True:
            url, status, response_time, checked_at, error = await check_website(
                url,
                self.RETRIES_IN_REPEATING_REQUESTS
            )
            if status == 200:
                downtime = self._calculate_downtime(url)
                await self.db.log_status(url, status, response_time, checked_at)
                success_message = self._create_success_message(url, downtime)
                self.telegram_bot.add_to_queue(success_message)
                logger.info(f"{url} is back up. Downtime: {downtime}")
                del self.down_since[url]
                break
            else:
                error_message = self._create_error_message(url, status, error)
                self.telegram_bot.add_to_queue(error_message)
                await asyncio.sleep(self.TIME_WAIT_BEFORE_RETRYING + current_wait_time)
                current_wait_time += 5

    async def process_website_check(self, url):
        url, status, response_time, checked_at, error = await check_website(
            url,
            self.RETRIES_IN_REPEATING_REQUESTS
        )
        if status != 200:
            await self.db.log_status(url, status, response_time, checked_at)
            error_message = self._create_error_message(url, status, error)
            self.telegram_bot.add_to_queue(error_message)
            asyncio.create_task(self.check_site_until_up(url))
        else:
            await self.db.log_status(url, status, response_time, checked_at)
        logger.info(f"{url} {status} {response_time} {checked_at}")

    async def uptime_check(self):
        while True:
            self.urls = self.db_connection.get_sites()
            tasks = [self.process_website_check(url) for url in self.urls]
            await asyncio.gather(*tasks)
            await asyncio.sleep(self.INTERVAL_BETWEEN_CHECKING)
    async def main(self):
        asyncio.create_task(self.uptime_check())
        await self.telegram_bot.start_polling()


if __name__ == '__main__':
    db_connection = DBConnection(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        use_json=True,
        logger=logger
    )
    monitor = UptimeMonitor(
        token=TOKEN,
        chat_id=CHAT_ID,
        db_connection=db_connection,
        interval_between_checking=800,
        time_wait_before_retrying=80,
        delay_wait_before_retrying=5
    )
    asyncio.run(monitor.main())
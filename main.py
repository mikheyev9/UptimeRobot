import aiohttp
import os
from datetime import datetime, timedelta, timezone
import socket
from urllib.parse import urlparse

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
                 need_saving_in_local_db=False,
                 interval_between_checking=800,
                 time_wait_before_retrying=80,
                 delay_wait_before_start_retrying=5,
                 retries_in_repeated_requests=3,
                 pool_size=100,
                 limit_per_host=4,
                 limit_request_ip=1):
        self.token = token
        self.chat_id = chat_id
        self.db = Database()
        self.need_saving_in_local_db = need_saving_in_local_db
        self.telegram_bot = TelegramBot(token=self.token, channel_id=self.chat_id)
        self.db_connection = db_connection
        self.urls = []

        self.INTERVAL_BETWEEN_CHECKING = interval_between_checking
        self.TIME_WAIT_BEFORE_RETRYING = time_wait_before_retrying
        self.DELAY_WAIT_BEFORE_START_RETRYING = delay_wait_before_start_retrying
        self.RETRIES_IN_REPEATING_REQUESTS = retries_in_repeated_requests
        self.POOL_SIZE = pool_size
        self.LIMIT_PER_HOST = limit_per_host
        self.LIMIT_REQUEST_IP = limit_request_ip
        self.down_since = {}
        self.ip_semaphores = {}

    def _create_success_message(self, url, downtime):
        return f"🟢 Monitor is UP: {url} ( {url} ). It was down for {downtime}."

    def _create_error_message(self, url, status, error=None):
        downtime = self._calculate_downtime(url)
        message = f"🔴 Monitor is DOWN: {url} (Status: {status}). Down for: {downtime}."
        if error:
            message += f" Error: {error[:100]}..."
        return message

    def _create_disabled_message(self, url):
        return f"⚫ Monitor is DISABLED for: {url}. The check has been turned off."

    def _create_exception_message(self, url, exception):
        return f"⚠️ An exception occurred while processing {url}: {str(exception)[:100]}..."

    def _calculate_downtime(self, url):
        downtime = datetime.now(timezone.utc) - self.down_since.get(url, datetime.now(timezone.utc))
        if downtime < timedelta(0):
            downtime = timedelta(0)
        return str(downtime).split('.')[0]

    async def log_status_in_sqlite(self, url, status, response_time, checked_at):
        if self.need_saving_in_local_db:
            await self.db.log_status(url, status, response_time, checked_at)
    async def create_session(self):
        connector = aiohttp.TCPConnector(limit=self.POOL_SIZE,
                                         limit_per_host=self.LIMIT_PER_HOST)
        session = aiohttp.ClientSession(connector=connector)
        return session

    async def check_site_until_up(self, url, domain):
        self.down_since.setdefault(url, datetime.now(timezone.utc))
        session = await self.create_session()
        current_wait_time = 0
        await asyncio.sleep(self.DELAY_WAIT_BEFORE_START_RETRYING)

        while True:
            try:
                if not await self.db_connection.is_site_check_enabled(url):
                    disabled_message = self._create_disabled_message(url)
                    self.telegram_bot.add_to_queue(disabled_message)
                    logger.info(disabled_message)
                    break

                url, status, response_time, checked_at, error = await check_website(
                    url,
                    domain,
                    session,
                    self.RETRIES_IN_REPEATING_REQUESTS,
                    self.DELAY_WAIT_BEFORE_START_RETRYING
                )
                await self.log_status_in_sqlite(url, status, response_time, checked_at)

                if status == 200:
                    downtime = self._calculate_downtime(url)
                    success_message = self._create_success_message(url, downtime)
                    self.telegram_bot.add_to_queue(success_message)
                    logger.info(f"{url} is back up. Downtime: {downtime}")
                    del self.down_since[url]
                    break
                else:
                    error_message = self._create_error_message(url, status, error)
                    self.telegram_bot.add_to_queue(error_message)
                    await asyncio.sleep(self.TIME_WAIT_BEFORE_RETRYING + current_wait_time)
                    current_wait_time += self.DELAY_WAIT_BEFORE_START_RETRYING
                    logger.info(f"{url} {status} {response_time} {checked_at} {error if error else ''}")

            except Exception as e:
                logger.error(f"An error occurred while checking {url}: {str(e)}")
                exception_message = self._create_exception_message(url, e)
                self.telegram_bot.add_to_queue(exception_message)
                await asyncio.sleep(self.TIME_WAIT_BEFORE_RETRYING + current_wait_time)
                current_wait_time += 5
        await session.close()

    async def process_website_check(self, url, session):
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        semaphore = self.get_semaphore(domain)
        async with semaphore:
            try:
                url, status, response_time, checked_at, error = await check_website(
                    url,
                    domain,
                    session,
                    self.RETRIES_IN_REPEATING_REQUESTS,
                    self.DELAY_WAIT_BEFORE_START_RETRYING
                )
                if status != 200:
                    error_message = self._create_error_message(url, status, error)
                    self.telegram_bot.add_to_queue(error_message)
                    if url not in self.down_since:
                        asyncio.create_task(self.check_site_until_up(url, domain))
                await self.log_status_in_sqlite(url, status, response_time, checked_at)
                logger.info(f"{url} {status} {response_time} {checked_at} {error if error else ''}")

            except Exception as e:
                logger.error(f"An error occurred while processing {url}: {str(e)}")
                exception_message = self._create_exception_message(url, e)
                self.telegram_bot.add_to_queue(exception_message)

    def get_ip(self, domain):
        try:
            return socket.gethostbyname(domain)
        except socket.gaierror:
            return None
    def get_semaphore(self, domain):
        ip = self.get_ip(domain)
        if ip not in self.ip_semaphores:
            self.ip_semaphores[ip] = asyncio.Semaphore(self.LIMIT_REQUEST_IP)
        return self.ip_semaphores[ip]

    async def check_all_websites(self):
        session = await self.create_session()
        tasks = [self.process_website_check(url, session) for url in self.urls]
        await asyncio.gather(*tasks)
        await session.close()

    async def uptime_check(self):
        while True:
            self.urls = await self.db_connection.get_sites()
            await self.check_all_websites()
            await asyncio.sleep(self.INTERVAL_BETWEEN_CHECKING)

    async def main(self):
        if self.need_saving_in_local_db:
            await self.db.init_db()
        asyncio.create_task(self.uptime_check())
        await self.telegram_bot.start_polling()


if __name__ == '__main__':
    db_connection = DBConnection(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        use_json=False,
        logger=logger
    )
    monitor = UptimeMonitor(
        token=TOKEN,
        chat_id=CHAT_ID,
        db_connection=db_connection,
        need_saving_in_local_db=False,
        interval_between_checking=800,
        time_wait_before_retrying=80,
        delay_wait_before_start_retrying=35,
        pool_size=50,
        limit_per_host=1,
        limit_request_ip=1
    )
    asyncio.run(monitor.main())
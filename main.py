import os
from datetime import datetime, timezone
from typing import Optional

import asyncio
from dotenv import load_dotenv

from aiohttp_requests.request import (WebsiteChecker,
                                      create_session,
                                      get_domain_from_url,
                                      resolve_domain)
from aiohttp_requests.proxy import ProxyManager
from telegram.telegram_bot import TelegramBot
from database.aiosqlite.database_local import Database
from database.nebilet_postgresql.database_nebilet import DBConnection
from logs.logger import logger
from logs.logger_message import (create_message_site_is_up,
                                 create_error_message,
                                 create_disabled_message,
                                 create_exception_message)
from tools.time_tools import calculate_downtime

load_dotenv()
TOKEN = os.getenv('TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_DATABASE = os.getenv('DB_DATABASE')


class UptimeMonitor:
    def __init__(self,
                 token,
                 chat_id,
                 db_connection,
                 need_saving_in_local_db=False,
                 interval_between_checking=800,
                 time_wait_before_retrying=80,
                 delay_wait_before_start_retrying=5,
                 retries_in_repeated_requests=3,
                 pool_size=100,
                 limit_per_host=4,
                 limit_request_ip=1,
                 proxy_check_interval=5):
        self.token = token
        self.chat_id = chat_id
        self.db = Database()
        self.need_saving_in_local_db = need_saving_in_local_db
        self.proxy_manager = ProxyManager(check_interval=proxy_check_interval)
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

    async def log_status_in_sqlite(self, url, status, response_time, checked_at) -> None:
        if self.need_saving_in_local_db:
            await self.db.log_status(url, status, response_time, checked_at)

    async def process_website_check(self, url, session) -> None:
        semaphore = await self.get_semaphore(url)
        async with semaphore:
            try:
                checker = WebsiteChecker(
                    url,
                    self.proxy_manager,
                    self.RETRIES_IN_REPEATING_REQUESTS,
                    self.DELAY_WAIT_BEFORE_START_RETRYING,
                    session
                )
                url, status, response_time, checked_at, error = await checker.check_website()
                if status != 200:
                    if url not in self.down_since:
                        error_message = create_error_message(url, status, error)
                        await self.telegram_bot.add_to_queue(error_message)
                        self.down_since.setdefault(url, datetime.now(timezone.utc))
                        asyncio.create_task(self.check_site_until_up(url))

                await self.log_status_in_sqlite(url, status, response_time, checked_at)
                logger.info(f"{url} {status} {response_time} {error if error else ''}")

            except Exception as e:
                await self._send_debug_exception_message(url, e)

    async def check_site_until_up(self, url):
        await asyncio.sleep(self.DELAY_WAIT_BEFORE_START_RETRYING)

        while True:
            try:
                if not await self.db_connection.domain_in_production(url):
                    disabled_message = create_disabled_message(url)
                    await self.telegram_bot.add_to_queue(disabled_message)
                    logger.info(disabled_message)
                    return

                checker = WebsiteChecker(
                    url,
                    self.proxy_manager,
                    self.RETRIES_IN_REPEATING_REQUESTS,
                    self.DELAY_WAIT_BEFORE_START_RETRYING,
                    session=None
                )
                url, status, response_time, checked_at, error = await checker.check_website()
                downtime = calculate_downtime(self.down_since, url)
                await self.log_status_in_sqlite(url, status, response_time, checked_at)

                if status == 200:
                    success_message = create_message_site_is_up(url, downtime)
                    await self.telegram_bot.add_to_queue(success_message)
                    logger.info(f"{url} is back up. Downtime: {downtime}")
                    del self.down_since[url]
                    return
                else:
                    error_message = create_error_message(url, status, error, downtime)
                    await self.telegram_bot.add_to_queue(error_message)
                    logger.error(f"{url} {status} {response_time} {error if error else ''}")

            except Exception as e:
                await self._send_debug_exception_message(url, e)

            await asyncio.sleep(self.TIME_WAIT_BEFORE_RETRYING)

    async def _send_debug_exception_message(self, url: str, e: Exception) -> None:
        logger.error(f"An error occurred while checking {url}: {str(e)}")
        exception_message = create_exception_message(url, str(e))
        await self.telegram_bot.add_to_queue(exception_message)

    async def get_semaphore(self, url) -> Optional[asyncio.Semaphore]:
        '''Oграничивает одновременные запросы к 1 ip адресу'''
        domain = get_domain_from_url(url)
        ip = await resolve_domain(domain)
        if ip not in self.ip_semaphores:
            self.ip_semaphores[ip] = asyncio.Semaphore(self.LIMIT_REQUEST_IP)
        return self.ip_semaphores[ip]

    async def uptime_check_cycle(self) -> None:
        while True:
            self.urls = await self.db_connection.get_sites()
            async with await create_session(self.POOL_SIZE,
                                            self.LIMIT_PER_HOST) as session:
                await self.send_request_to_all_urls(session)
            await asyncio.sleep(self.INTERVAL_BETWEEN_CHECKING)

    async def send_request_to_all_urls(self, session) -> None:
        tasks = [self.process_website_check(url, session) for url in self.urls]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def main(self) -> None:
        if self.need_saving_in_local_db:
            await self.db.init_db()
        await self.proxy_manager.initialize()
        asyncio.create_task(self.uptime_check_cycle())
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
        retries_in_repeated_requests=3,
        pool_size=50,
        limit_per_host=1,
        limit_request_ip=1
    )
    asyncio.run(monitor.main())

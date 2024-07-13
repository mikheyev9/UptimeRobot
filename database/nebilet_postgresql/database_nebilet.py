import asyncpg
import os
import json

import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from logs.logger import setup_logger

class DBConnection:
    def __init__(self,
                 host,
                 port,
                 user,
                 password,
                 database,
                 logger,
                 use_json=False,
                 retry_attempts=5,
                 retry_delay=5,
                 backup_file='backup_sites.json'):
        self.host = host
        self.port = str(port)
        self.user = user
        self.password = password
        self.database = database
        self.use_json = use_json
        self.logger = logger
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.backup_file = self._get_backup_path(backup_file)
        self.pool = None

    @staticmethod
    def _get_backup_path(name):
        current_file_path = os.path.abspath(__file__)
        current_directory = os.path.dirname(current_file_path)
        backup_file_path = os.path.join(current_directory, name)
        return backup_file_path

    async def connect_db(self):
        for attempt in range(self.retry_attempts):
            try:
                self.pool = await asyncpg.create_pool(user=self.user,
                                                      password=self.password,
                                                      host=self.host,
                                                      port=self.port,
                                                      database=self.database)
                return True
            except (asyncpg.PostgresError, OSError) as e:
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    self.logger.error(f"Could not connect to the database after {self.retry_attempts} attempts.")
                    raise ConnectionError("Failed to connect to the database.")

    @asynccontextmanager
    async def get_cursor(self):
        if not self.pool:
            await self.connect_db()
        async with self.pool.acquire(timeout=30) as connection:
            async with connection.transaction():
                yield connection

    async def get_sites(self):
        if self.use_json:
            return self.load_backup_data()
        try:
            async with self.get_cursor() as conn:
                sites = await conn.fetch('SELECT name FROM public.tables_sites WHERE site_check=True')
                sites = ['https://' + row['name'] for row in sites]
                self.save_backup_data(sites)
                return sites
        except (Exception, asyncpg.PostgresError) as e:
            self.logger.error(f"Error fetching sites from the database: {e}")
            return self.load_backup_data()

    async def is_site_check_enabled(self, domain):
        domain = domain.replace('https://', '').replace('http://', '')
        query = 'SELECT site_check FROM public.tables_sites WHERE name=$1'
        try:
            async with self.get_cursor() as conn:
                result = await conn.fetchrow(query, domain)
                if result:
                    return result['site_check']
                return False
        except (Exception, asyncpg.PostgresError) as e:
            self.logger.error(f"Error checking site_check for domain {domain}: {e}")
            return False

    def save_backup_data(self, data):
        try:
            with open(self.backup_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving backup data: {e}")

    def load_backup_data(self):
        try:
            with open(self.backup_file, 'r') as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            return []

    async def close(self):
        if self.pool:
            await self.pool.close()



async def main():
    logger = setup_logger(
        'test_nebilet_postgresql.log',
        logger_name='test_nebilet_postgresql'
    )
    load_dotenv()
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = os.getenv('DB_PORT')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_DATABASE = os.getenv('DB_DATABASE')

    db_connection = DBConnection(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        use_json=False,
        logger=logger
    )

    try:
        # Ensure the pool is connected
        await db_connection.connect_db()

        # Get sites
        sites = await db_connection.get_sites()
        print(f"Retrieved {len(sites)} sites from the database or backup.")
        for site in sites:
            print(site)
    except Exception as e:
        logger.error(f"Error during database operation: {e}")
    finally:
        await db_connection.close()

if __name__ == '__main__':
    asyncio.run(main())
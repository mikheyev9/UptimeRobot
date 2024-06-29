from contextlib import contextmanager
import json
import time

import psycopg2
from psycopg2.extras import RealDictCursor


class DBConnection:
    def __init__(self, host, port, user, password, database,
                 logger, use_json=False, retry_attempts=5, retry_delay=5,
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
        self.connection = None
        self.cursor = None

    @staticmethod
    def _get_backup_path(name):
        current_file_path = os.path.abspath(__file__)
        current_directory = os.path.dirname(current_file_path)
        backup_file_path = os.path.join(current_directory, name)
        return backup_file_path

    def connect_db(self):
        for attempt in range(self.retry_attempts):
            try:
                self.connection = psycopg2.connect(user=self.user,
                                                   password=self.password,
                                                   host=self.host,
                                                   port=self.port,
                                                   database=self.database)
                self.cursor = self.connection.cursor(cursor_factory=RealDictCursor)
                return True
            except psycopg2.OperationalError as e:
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay)
                else:
                    return False

    @contextmanager
    def get_cursor(self):
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor

    def get_sites(self):
        if self.use_json or not self.connect_db():
            return self.load_backup_data()
        try:
            with self.get_cursor() as cursor:
                cursor.execute('SELECT name FROM public.tables_sites WHERE site_check=True')
                sites = ['https://' + row['name'] for row in cursor.fetchall()]
                self.save_backup_data(sites)
                return sites
        except (Exception, psycopg2.DatabaseError) as e:
            logger.error(f"Error fetching sites from the database")
            return self.load_backup_data()

    def save_backup_data(self, data):
        try:
            with open(self.backup_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass
    def load_backup_data(self):
        try:
            with open(self.backup_file, 'r') as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            return []

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()


# Тестовый запуск для проверки получения сайтов
if __name__ == '__main__':
    import os
    from dotenv import load_dotenv
    from logs.logger import setup_logger

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

    sites = db_connection.get_sites()
    print(f"Retrieved {len(sites)} sites from the database or backup.")
    for site in sites:
        print(site)

    db_connection.close()

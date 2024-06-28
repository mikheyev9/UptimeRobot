import aiosqlite


DATABASE = 'database/aiosqlite/uptime.db'

class Database:
    def __init__(self, db_path=DATABASE):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS url_status (
                                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                                   url TEXT NOT NULL,
                                   status TEXT NOT NULL,
                                   response_time REAL,
                                   checked_at TEXT NOT NULL
                                 )''')
            await db.commit()

    async def log_status(self, url, status, response_time, checked_at):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO url_status (url, status, response_time, checked_at) VALUES (?, ?, ?, ?)",
                             (url, status, response_time, checked_at))
            await db.commit()

    async def get_status_by_url(self, url):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT * FROM url_status WHERE url = ?", (url,)) as cursor:
                rows = await cursor.fetchall()
                return rows
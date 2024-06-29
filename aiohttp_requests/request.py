import asyncio
from datetime import datetime
import time

import aiohttp

async def check_website(url,
                        retries_in_repeated_requests=3):
    retries = retries_in_repeated_requests
    delays = [i + 1 for i in range(retries)]
    async with aiohttp.ClientSession() as session:
        for attempt in range(retries):
            start_time = time.time()
            checked_at = datetime.utcnow().isoformat()
            try:
                async with session.get(url, timeout=10) as response:
                    response_time = time.time() - start_time
                    status = response.status
                    error = None
                    if status == 200:
                        return url, status, response_time, checked_at, error
            except Exception as ex:
                response_time = time.time() - start_time
                status = 'Exception'
                error = str(ex)
                if attempt < retries - 1:
                    await asyncio.sleep(delays[attempt])
                else:
                    return url, status, response_time, checked_at, error


# Пример использования функции
if __name__ == "__main__":
    # URL для проверки
    url = "https://example.com"

    # Запуск асинхронной функции
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(check_website(url))
    print(result)
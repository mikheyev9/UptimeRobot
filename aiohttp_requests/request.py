import asyncio
from datetime import datetime, timezone
import time

import aiohttp

async def check_website(url,
                        session,
                        retries_in_repeated_requests=3,
                        delay_wait_before_start_retrying=3):
    retries = retries_in_repeated_requests
    delays = [i + delay_wait_before_start_retrying for i in range(retries)]
    for attempt in range(retries):
        start_time = time.time()
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            async with session.get(url, timeout=15) as response:
                response_time = time.time() - start_time
                status = response.status
                error = None
                if status == 200:
                    return url, status, response_time, checked_at, error
        except Exception as ex:
            response_time = time.time() - start_time
            status = 'Exception'
            error = str(ex)
            await asyncio.sleep(delays[attempt])
        return url, status, response_time, checked_at, error


# Пример использования функции
if __name__ == "__main__":
    # URL для проверки
    url = "https://example.com"

    # Запуск асинхронной функции
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(check_website(url))
    print(result)
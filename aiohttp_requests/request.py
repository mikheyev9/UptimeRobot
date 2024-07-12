import asyncio
from datetime import datetime, timezone
import time

import aiohttp

async def check_website(url,
                        domain,
                        session,
                        retries_in_repeated_requests=3,
                        delay_wait_before_start_retrying=3):
    retries = retries_in_repeated_requests
    delays = [i + delay_wait_before_start_retrying for i in range(retries)]
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "DNT": "1",
        "Host": domain,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "sec-ch-ua": "\"Not/A)Brand\";v=\"8\", \"Chromium\";v=\"126\", \"Google Chrome\";v=\"126\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Linux\""
    }
    for attempt in range(retries):
        start_time = time.time()
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
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
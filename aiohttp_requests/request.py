from datetime import datetime
import time

import aiohttp

async def check_website(url):
    async with aiohttp.ClientSession() as session:
        start_time = time.time()
        checked_at = datetime.utcnow().isoformat()
        try:
            async with session.get(url, timeout=10) as response:
                response_time = time.time() - start_time
                status = response.status
        except Exception:
            response_time = time.time() - start_time
            status = 'Exception'
        return url, status, response_time, checked_at
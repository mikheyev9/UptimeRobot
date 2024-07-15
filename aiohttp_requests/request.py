import asyncio
import socket
import random
from datetime import datetime, timezone
import time
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import List, Optional, NamedTuple
from functools import wraps

import aiohttp
import aiodns

from aiohttp_requests.proxy import ProxyManager
from logs.logger import logger


resolver = None

def lazy_init_resolver(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global resolver
        if resolver is None:
            loop = asyncio.get_event_loop()
            resolver = aiodns.DNSResolver(loop=loop)
        return await func(*args, **kwargs)
    return wrapper

@lazy_init_resolver
async def resolve_domain(domain) -> str:
    global resolver
    try:
        result = await resolver.gethostbyname(domain, socket.AF_INET)
    except Exception as e:
        logger.error(f"Error resolving {domain}: {e}")
        resolver = aiodns.DNSResolver()
        try:
            result = await resolver.gethostbyname(domain, socket.AF_INET)
        except Exception as retry_e:
            logger.error(f"Retry error resolving {domain}: {retry_e}")
            return 'None'
    return result.addresses[0] if result.addresses else 'None'


def get_domain_from_url(url: str) -> str:
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    return domain


async def create_session(need_connector=True,
                         pool_size=50,
                         limit_per_host=10) -> aiohttp.ClientSession:
    if need_connector:
        connector = aiohttp.TCPConnector(limit=pool_size, limit_per_host=limit_per_host)
        session = aiohttp.ClientSession(connector=connector)
    else:
        session = aiohttp.ClientSession()
    return session


class CheckResult(NamedTuple):
    url: str
    status: str | int
    response_time: float
    checked_at: str
    error: Optional[str]


@dataclass
class WebsiteChecker:
    url: str
    proxy_manager: ProxyManager
    retries_in_repeated_requests: int = 3
    delay_wait_before_start_retrying: int = 3
    session: Optional[aiohttp.ClientSession] = None
    headers: dict = field(init=False)
    proxy: Optional[str] = None

    def __post_init__(self):
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "DNT": "1",
            "Host": self.domain,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, как Gecko) Chrome/126.0.0.0 Safari/537.36",
            "sec-ch-ua": "\"Not/A)Brand\";v=\"8\", \"Chromium\";v=\"126\", \"Google Chrome\";v=\"126\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Linux\""
        }

    @property
    def domain(self) -> str:
        return get_domain_from_url(self.url)

    async def check_website(self) -> CheckResult:
        for attempt in range(self.retries_in_repeated_requests):
            if not self.session:
                async with await create_session(need_connector=False) as session:
                    result = await self._get_request(session)
            else:
                result = await self._get_request(self.session)
            if result.status == 200:
                return result
            await asyncio.sleep(self.delay_wait_before_start_retrying)
        return result

    async def _get_request(self, session: aiohttp.ClientSession) -> CheckResult:
        error = None
        start_time = time.time()
        checked_at = datetime.now(timezone.utc).isoformat()
        status = 'Exception'
        response_time = 0
        try:
            async with session.get(self.url,
                                   headers=self.headers,
                                   timeout=60,
                                   proxy=self.proxy) as response:
                response_time = time.time() - start_time
                status = response.status
                if status == 200:
                    return CheckResult(self.url, status, response_time, checked_at, error)

        except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError) as ex:
            error = f"Proxy connection error: {self.proxy}"
            await self.proxy_manager.remove_proxy(self.proxy)
            self.proxy = await self.proxy_manager.get_proxy()
            logger.warning(f"{self.url} {error} bad proxy {self.proxy}")
        except (aiohttp.ClientConnectorCertificateError) as ex:
            error = f"ClientConnectorCertificateError"
            self.proxy = await self.proxy_manager.get_proxy()
        except Exception as ex:
            error = repr(ex)
            if self.session:
                self.session = None
                self.proxy = await self.proxy_manager.get_proxy()
            logger.warning(f"{self.url} {status} {error} trying to use proxy {self.proxy}")

        return CheckResult(self.url, status, response_time, checked_at, error)


if __name__ == '__main__':
    async def main():
        url = "http://example.com"
        proxy_manager = ProxyManager(check_interval=5)
        await proxy_manager.initialize()

        checker = WebsiteChecker(url=url,
                                 proxy_manager=proxy_manager)

        session = await create_session(need_connector=False)
        checker2 = WebsiteChecker(url=url,
                                  proxy_manager=proxy_manager,
                                  session=session)

        result = await checker.check_website()
        result2 = await checker2.check_website()

        await session.close()
        print(result, result2, sep='\n')

    asyncio.run(main())

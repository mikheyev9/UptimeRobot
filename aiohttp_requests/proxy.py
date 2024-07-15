import json
import os
import random
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import asyncio
import aiohttp
import aiofiles

from logs.logger import logger

module_dir = os.path.dirname(__file__)
class ProxyManager:
    def __init__(self,
                 url='http://httpbin.org/ip',
                 proxy_file='all_proxies.json',
                 state_file='checked_proxies.json',
                 check_interval=24):
        self.proxy_file = os.path.join(module_dir, proxy_file)
        self.state_file = os.path.join(module_dir, state_file)
        self.url = url
        self.check_interval = timedelta(hours=check_interval)
        self.lock = asyncio.Lock()
        self.proxies = []
        self.proxy_states = {}

    async def load_all_proxies(self) -> None:
        async with self.lock:
            try:
                async with aiofiles.open(self.proxy_file, 'r') as fp:
                    data = await fp.read()
                    proxy_list = json.loads(data)
                    self.proxies = [self._create_proxy(row) for row in proxy_list]
                    self.proxies = [proxy for proxy in self.proxies if proxy]
            except FileNotFoundError:
                print(f"File {self.proxy_file} not found.")
            except json.JSONDecodeError:
                print(f"File {self.proxy_file} is not a valid JSON.")

    async def load_proxy_states(self) -> None:
        async with self.lock:
            try:
                async with aiofiles.open(self.state_file, 'r') as fp:
                    data = await fp.read()
                    if data:
                        self.proxy_states = json.loads(data)
                    else:
                        print(f"File {self.state_file} is empty.")
            except FileNotFoundError:
                print(f"File {self.state_file} not found.")
            except json.JSONDecodeError:
                print(f"File {self.state_file} is not a valid JSON.")

    def _create_proxy(self, proxy_data):
        if isinstance(proxy_data, str):
            type_, ip, port, user, pwd = self._parse_str(proxy_data)
        else:
            print(f'Invalid proxy format: {proxy_data}')
            return False
        return {
            'schema': type_,
            'ip': ip,
            'port': port,
            'user': user,
            'password': pwd
        }

    @staticmethod
    def _parse_str(row):
        proxy_type, proxy_user, proxy_pass = 'http', None, None
        if '://' in row:
            proxy_type, row = row.split('://')
        if '@' in row:
            row, logpass = row.split('@')
            proxy_user, proxy_pass = logpass.split(':')
        spl_proxy = row.split(':')
        proxy_host = spl_proxy[0]
        proxy_port = int(spl_proxy[1])
        return proxy_type, proxy_host, proxy_port, proxy_user, proxy_pass

    async def ensure_proxies_checked(self) -> None:
        now = datetime.now()
        async with self.lock:
            proxies_to_check = []
            for proxy in self.proxies:
                proxy_key = f"{proxy['ip']}:{proxy['port']}"
                # Проверяем, существует ли ключ прокси в состояниях и если нет - добавляем к проверке
                if proxy_key not in self.proxy_states:
                    proxies_to_check.append(proxy)
                    continue
                # Проверяем, если время последней проверки превышает заданный интервал
                last_checked = datetime.fromisoformat(self.proxy_states[proxy_key]['last_checked'])
                if (now - last_checked) > self.check_interval:
                    proxies_to_check.append(proxy)
        # Если есть прокси для проверки, запускаем проверку
        if proxies_to_check:
            await self.check_proxies()
            await self.save_proxy_states()

    async def check_proxies(self) -> None:
        async with aiohttp.ClientSession() as session:
            tasks = [self._check_proxy(session, proxy, self.url, timeout=10) for proxy in self.proxies]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for proxy, result in zip(self.proxies, results):
                proxy_key = f"{proxy['ip']}:{proxy['port']}"

                if not result or isinstance(result, Exception):
                    logger.error(f"Proxy {proxy['ip']}:{proxy['port']} failed")
                    if proxy_key in self.proxy_states:
                        del self.proxy_states[proxy_key]
                else:
                    proxy_url = f"{proxy['schema']}://{proxy['user']}:{proxy['password']}@{proxy_key}"
                    self.proxy_states[proxy_key] = {
                        'last_checked': datetime.now().isoformat(),
                        'schema': proxy['schema'],
                        'user': proxy['user'],
                        'password': proxy['password'],
                        'proxy_url': proxy_url
                    }

    async def _check_proxy(self, session, proxy, url, timeout) -> bool:
        try:
            proxy_url = f"{proxy['schema']}://{proxy['user']}:{proxy['password']}@{proxy['ip']}:{proxy['port']}"
            async with session.get(url, proxy=proxy_url, timeout=timeout) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Proxy {proxy['ip']}:{proxy['port']} failed: {e}")
            return False

    async def save_proxy_states(self) -> None:
        async with self.lock:
            async with aiofiles.open(self.state_file, 'w') as fp:
                await fp.write(json.dumps(self.proxy_states, default=str, indent=2))

    async def get_proxy(self) -> Optional[str | bool]:
        async with self.lock:
            if not self.proxy_states:
                logger.error("No proxies available")
                return None
            now = datetime.now()
            oldest_check = min(self.proxy_states.values(), key=lambda x: datetime.fromisoformat(x['last_checked']))
            if (now - datetime.fromisoformat(oldest_check['last_checked'])) > self.check_interval:
                loop = asyncio.get_running_loop()
                loop.create_task(self.check_proxies())
            return random.choice(list(self.proxy_states.values()))['proxy_url']

    async def remove_proxy(self, proxy_url: str) -> None:
        parsed_url = urlparse(proxy_url)
        ip_port = parsed_url.netloc.split('@')[-1]
        async with self.lock:
            if ip_port in self.proxy_states:
                del self.proxy_states[ip_port]
            else:
                logger.warning(f"Proxy {ip_port} not found in proxy states")
        await self.save_proxy_states()

    async def initialize(self) -> None:
        await self.load_all_proxies()
        await self.load_proxy_states()
        await self.ensure_proxies_checked()


# Пример использования
if __name__ == "__main__":
    async def main():
        proxy_manager = ProxyManager(check_interval=5)
        await proxy_manager.initialize()
        proxy = await proxy_manager.get_proxy()
        if proxy:
            print(f"Using proxy: {proxy}")


    if __name__ == "__main__":
        asyncio.run(main())

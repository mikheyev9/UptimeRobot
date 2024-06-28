import asyncio
from aiogram import Bot, Dispatcher, html
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
from collections import deque

class TelegramBot:
    def __init__(self, token, channel_id, initial_delay=1):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.channel_id = channel_id
        self.message_queue = deque()
        self.delay = initial_delay

    async def send_message(self, message):
        try:
            await self.bot.send_message(chat_id=self.channel_id, text=html.quote(message))
            self.delay = 1  # Reset delay after successful send
        except TelegramRetryAfter as e:
            # Too many requests, need to wait
            self.delay = e.retry_after + 2
            self.message_queue.appendleft(message)  # Re-add the message to the front of the queue
        except TelegramAPIError as e:
            # Other API errors
            self.message_queue.appendleft(message)  # Re-add the message to the front of the queue
            print(f"Failed to send message: {e}")

    async def process_queue(self):
        while True:
            if self.message_queue:
                message = self.message_queue.popleft()
                await self.send_message(message)
            await asyncio.sleep(self.delay)  # Delay between messages

    def add_to_queue(self, message):
        self.message_queue.append(message)

    async def start_polling(self):
        asyncio.create_task(self.process_queue())
        await self.dp.start_polling(self.bot)

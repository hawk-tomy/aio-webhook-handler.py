from __future__ import annotations

from asyncio import Queue, sleep
from collections.abc import Awaitable, Callable
from io import BytesIO
from logging import WARNING, Filter, Handler, LogRecord
from typing import TYPE_CHECKING

from aiohttp import ClientSession
from discord import File, Webhook

if TYPE_CHECKING:
    from logging import LogRecord
    from typing import Self


__all__ = ("generate_webhook_handler", "WebhookHandler", "WebhookSender")

type WebhookSender = Callable[[], Awaitable[None]]
"""A callable that asynchronously sends webhook messages.

This type alias represents a function that takes no arguments and returns an awaitable
object. When awaited, the callable sends a message via a Discord webhook.
"""


class _AsyncQueueAsAsyncIterator[T](Queue[T]):
    def __aiter__(self) -> Self:
        return self

    async def __anext__(self):
        return await self.get()


class _WebhookFilter(Filter):
    def filter(self, record: LogRecord) -> bool | LogRecord:
        return record.name != "discord.webhook.async_"


class WebhookHandler(Handler):
    """Logging handler that sends log messages to a Discord webhook.

    This handler formats log records and enqueues them into an asynchronous queue for dispatching via a webhook.

    Key features:
    - Enqueues formatted log messages for asynchronous sending.
    - Ignores log messages from 'discord.webhook.async_' (i.e. warnings or debug logs generated
      by the webhook sending process) using a custom filter.

    Args:
        queue (_AsyncQueueAsAsyncIterator[str]): The asynchronous queue used to send log messages.
    """

    def __init__(self, queue: _AsyncQueueAsAsyncIterator[str]) -> None:
        super().__init__(level=WARNING)
        self.queue = queue
        self.addFilter(_WebhookFilter())

    def emit(self, record: LogRecord) -> None:
        self.queue.put_nowait(self.format(record))


def generate_webhook_handler(url: str) -> tuple[WebhookHandler, WebhookSender]:
    """Generates a webhook handler and sender function.

    This function creates a WebhookHandler that enqueues formatted log records, and a corresponding
    asynchronous webhook_sender function that sends messages via a Discord webhook.

    Args:
        url (str): The URL of the Discord webhook.

    Returns:
        tuple[WebhookHandler, WebhookSender]: A tuple containing a WebhookHandler instance and a webhook sender callable.
    """
    queue = _AsyncQueueAsAsyncIterator[str]()

    async def webhook_sender():
        async with ClientSession() as session:
            webhook = await Webhook.from_url(url, session=session).fetch()
            async for msg in queue:
                sleep_until = 4
                while True:
                    try:
                        if len(msg) <= 1990:
                            await webhook.send(f"```py\n{msg}```")
                        else:
                            await webhook.send(file=File(BytesIO(msg.encode("utf-8")), filename="log.txt"))
                    except Exception:
                        await sleep(sleep_until)
                        sleep_until <<= 2
                    else:
                        break

    return (WebhookHandler(queue), webhook_sender)

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import TYPE_CHECKING, Any, Generator, Optional, Type, TypeVar

if TYPE_CHECKING:
    from .abc import Messageable, MessageableChannel

__all__ = ('Typing',)

_log = logging.getLogger(__name__)

TypingT = TypeVar('TypingT', bound='Typing')

# Bisim shows a typing indicator for a few seconds; it is refreshed well before it fades.
TYPING_REFRESH_SECONDS = 5.0


def _typing_done_callback(fut: 'asyncio.Future[Any]') -> None:
    # just retrieve any exception and call it a day
    try:
        fut.exception()
    except (asyncio.CancelledError, Exception):
        pass


class Typing:
    """The typing indicator returned by :meth:`abc.Messageable.typing`.

    Use it with ``async with`` to keep the indicator on while a block runs,
    or ``await`` it to show it once.
    """

    def __init__(self, messageable: Messageable) -> None:
        self.messageable: Messageable = messageable
        self.channel: Optional[MessageableChannel] = None
        self.task: Optional[asyncio.Task[None]] = None

    async def wrapped_typer(self) -> None:
        channel = await self._get_channel()
        await self.messageable._state._trigger_typing(channel)

    def __await__(self) -> Generator[None, None, None]:
        return self.wrapped_typer().__await__()

    async def _get_channel(self) -> MessageableChannel:
        if self.channel is None:
            self.channel = await self.messageable._get_channel()
        return self.channel

    async def do_typing(self) -> None:
        channel = await self._get_channel()
        state = self.messageable._state
        while True:
            await asyncio.sleep(TYPING_REFRESH_SECONDS)
            try:
                await state._trigger_typing(channel)
            except Exception:
                _log.debug('Refreshing the typing indicator failed.', exc_info=True)

    async def __aenter__(self) -> None:
        channel = await self._get_channel()
        await self.messageable._state._trigger_typing(channel)
        self.task = asyncio.get_running_loop().create_task(self.do_typing())
        self.task.add_done_callback(_typing_done_callback)

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.task:
            self.task.cancel()

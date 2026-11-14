"""The exceptions raised by the library.

They follow discord.py's hierarchy, with ``DiscordException`` named
:exc:`BisimException` and ``DiscordServerError`` named :exc:`BisimServerError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from aiohttp import ClientResponse, ClientWebSocketResponse

    from .interactions import Interaction

__all__ = (
    'BisimException',
    'ClientException',
    'GatewayNotFound',
    'HTTPException',
    'RateLimited',
    'Forbidden',
    'NotFound',
    'BisimServerError',
    'InvalidData',
    'LoginFailure',
    'ConnectionClosed',
    'PrivilegedIntentsRequired',
    'InteractionResponded',
    'MissingApplicationID',
    'NotSupported',
    'FFmpegProcessError',
)

APP_ID_NOT_FOUND = (
    'Client does not have an application_id set. Either the function was called before on_ready '
    'was called or application_id was not passed to the Client constructor.'
)


class BisimException(Exception):
    """Base exception class for bisim.py

    Ideally speaking, this could be caught to handle any exceptions raised from this library.
    """

    pass


class ClientException(BisimException):
    """Exception that's raised when an operation in the :class:`Client` fails.

    These are usually for exceptions that happened due to user input.
    """

    pass


class FFmpegProcessError(ClientException):
    """Exception that's raised when an FFmpeg process fails.

    It reaches the ``after`` callback of :meth:`VoiceClient.play` when ffmpeg
    exits with an error while an :class:`FFmpegAudio` source is playing.
    """

    pass


class NotSupported(ClientException):
    """Raised when a feature of discord.py has no counterpart on Bisim.

    Voice connections, threads, stage and forum channels, scheduled events and
    sharding are examples. This is a :exc:`ClientException`, so code that
    catches that keeps working.
    """

    def __init__(self, feature: str) -> None:
        self.feature: str = feature
        super().__init__(f'{feature} is not supported on Bisim.')


class GatewayNotFound(BisimException):
    """An exception that is raised when the gateway for Bisim could not be found"""

    def __init__(self) -> None:
        message = 'The gateway to connect to Bisim was not found.'
        super().__init__(message)


def _flatten_error_message(data: Any) -> str:
    if isinstance(data, list):
        return '; '.join(str(item) for item in data)
    if data is None:
        return ''
    return str(data)


class HTTPException(BisimException):
    """Exception that's raised when an HTTP request operation fails.

    Attributes
    ------------
    response: :class:`aiohttp.ClientResponse`
        The response of the failed HTTP request. This is an
        instance of :class:`aiohttp.ClientResponse`. In some cases
        this could also be a :class:`requests.Response`.

    text: :class:`str`
        The text of the error. Could be an empty string.
    status: :class:`int`
        The status code of the HTTP request.
    code: Union[:class:`str`, :class:`int`]
        Bisim's error code, such as ``'BOT_NOT_ALLOWED'`` or ``'RATE_LIMITED'``.
        Bisim's codes are strings; ``0`` when the response carried none.
    errors: List[:class:`str`]
        The individual validation messages when Bisim refused the request body
        (a 400 with a list of messages). Empty otherwise.
    """

    def __init__(self, response: ClientResponse, message: Optional[Union[str, Dict[str, Any]]]):
        self.response: ClientResponse = response
        self.status: int = getattr(response, 'status', 0)
        self.code: Union[str, int]
        self.text: str
        self.errors: List[str] = []
        if isinstance(message, dict):
            self.code = message.get('code') or 0
            raw = message.get('message', '')
            if isinstance(raw, list):
                self.errors = [str(item) for item in raw]
            self.text = _flatten_error_message(raw)
            if not self.text and message.get('error'):
                self.text = str(message['error'])
        else:
            self.text = message or ''
            self.code = 0

        reason = getattr(response, 'reason', '') or ''
        base = f'{self.status} {reason}'.strip()
        if self.code:
            base += f' (error code: {self.code})'
        if self.text:
            super().__init__(f'{base}: {self.text}')
        else:
            super().__init__(base)


class RateLimited(BisimException):
    """Exception that's raised for when status code 429 occurs
    and the timeout is greater than the configured maximum using
    the ``max_ratelimit_timeout`` parameter in :class:`Client`.

    This is not raised during global ratelimits.

    Since sometimes requests are halted pre-emptively before they're
    even made, this **does not** subclass :exc:`HTTPException`.

    Attributes
    ------------
    retry_after: :class:`float`
        The amount of seconds that the client should wait before retrying
        the request.
    """

    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f'Too many requests. Retry in {retry_after:.2f} seconds.')


class Forbidden(HTTPException):
    """Exception that's raised for when status code 403 occurs.

    Subclass of :exc:`HTTPException`
    """

    pass


class NotFound(HTTPException):
    """Exception that's raised for when status code 404 occurs.

    Subclass of :exc:`HTTPException`
    """

    pass


class BisimServerError(HTTPException):
    """Exception that's raised for when a 500 range status code occurs.

    Subclass of :exc:`HTTPException`.
    """

    pass


class InvalidData(ClientException):
    """Exception that's raised when the library encounters unknown
    or invalid data from Bisim.
    """

    pass


class LoginFailure(ClientException):
    """Exception that's raised when the :meth:`Client.login` function
    fails to log you in from improper credentials or some other misc.
    failure.
    """

    pass


class ConnectionClosed(ClientException):
    """Exception that's raised when the gateway connection is
    closed for reasons that could not be handled internally.

    Attributes
    -----------
    code: :class:`int`
        The close code of the websocket.
    reason: :class:`str`
        The reason provided for the closure.
    shard_id: Optional[:class:`int`]
        Always ``None``: Bisim has no sharding.
    """

    def __init__(
        self,
        socket: Optional[Union[ClientWebSocketResponse, int]] = None,
        *,
        shard_id: Optional[int] = None,
        code: Optional[int] = None,
        reason: Optional[str] = None,
    ):
        if isinstance(socket, int):
            code = socket
        elif code is None and socket is not None:
            code = getattr(socket, 'close_code', None)
        self.code: int = code or -1
        self.reason: str = reason or ''
        self.shard_id: Optional[int] = shard_id
        super().__init__(f'Gateway connection closed with code {self.code}' + (f': {self.reason}' if self.reason else ''))


class PrivilegedIntentsRequired(ClientException):
    """Kept for compatibility with discord.py; never raised.

    Bisim has no privileged intents: what a bot sees is decided by its
    permissions in each server.

    Attributes
    -----------
    shard_id: Optional[:class:`int`]
        Always ``None``.
    """

    def __init__(self, shard_id: Optional[int] = None):
        self.shard_id: Optional[int] = shard_id
        super().__init__('Bisim has no privileged intents.')


class InteractionResponded(ClientException):
    """Exception that's raised when sending another interaction response using
    :class:`InteractionResponse` when one has already been done before.

    An interaction can only respond once.

    Attributes
    -----------
    interaction: :class:`Interaction`
        The interaction that's already been responded to.
    """

    def __init__(self, interaction: Interaction):
        self.interaction: Interaction = interaction
        super().__init__('This interaction has already been responded to before')


class MissingApplicationID(ClientException):
    """An exception raised when the client does not have an application ID set.

    An application ID is required for syncing application commands. On Bisim
    the application ID is the bot's own user ID, which the client learns when
    it logs in.
    """

    def __init__(self, message: Optional[str] = None):
        super().__init__(message or APP_ID_NOT_FOUND)

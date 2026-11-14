"""
Helpers used across the library and useful to bot authors.

The names and behaviour follow ``discord.utils`` so code written for
discord.py keeps working, with Bisim's own snowflake epoch, invite links and
OAuth2 address.
"""

from __future__ import annotations

import array
import asyncio
import bisect
import collections.abc
import datetime
import functools
import inspect
import json
import logging
import os
import re
import sys
import typing
import unicodedata
from operator import attrgetter
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    ForwardRef,
    Generic,
    Iterable,
    Iterator,
    List,
    Literal,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)
from urllib.parse import urlencode

try:
    import orjson  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional speedup
    HAS_ORJSON = False
else:  # pragma: no cover
    HAS_ORJSON = True

if TYPE_CHECKING:
    from .abc import Snowflake
    from .invite import Invite
    from .permissions import Permissions

__all__ = (
    'MISSING',
    'BISIM_EPOCH',
    'oauth_url',
    'snowflake_time',
    'time_snowflake',
    'find',
    'get',
    'sleep_until',
    'utcnow',
    'remove_markdown',
    'escape_markdown',
    'escape_mentions',
    'maybe_coroutine',
    'as_chunks',
    'format_dt',
    'resolve_invite',
    'resolve_template',
    'setup_logging',
    'parse_time',
    'compute_timedelta',
)

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)
_Iter = Union[Iterable[T], AsyncIterable[T]]

#: The Bisim snowflake epoch in milliseconds (2026-06-01T00:00:00Z).
BISIM_EPOCH = 1780272000000

_log = logging.getLogger(__name__)


class _MissingSentinel:
    """A value that means "not given", distinct from ``None``."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return False

    def __bool__(self) -> bool:
        return False

    def __hash__(self) -> int:
        return 0

    def __repr__(self) -> str:
        return '...'

    def __copy__(self) -> '_MissingSentinel':
        return self

    def __deepcopy__(self, memo: Any) -> '_MissingSentinel':
        return self


MISSING: Any = _MissingSentinel()


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

if HAS_ORJSON:  # pragma: no cover

    def _to_json(obj: Any) -> str:
        return orjson.dumps(obj).decode('utf-8')

    _from_json = orjson.loads

else:

    def _to_json(obj: Any) -> str:
        return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)

    _from_json = json.loads


# ---------------------------------------------------------------------------
# Snowflakes and time
# ---------------------------------------------------------------------------


def utcnow() -> datetime.datetime:
    """A timezone aware :class:`datetime.datetime` for the current time in UTC.

    Prefer this over :meth:`datetime.datetime.utcnow`, which returns a naive
    datetime that is easy to misread as local time.

    Returns
    --------
    :class:`datetime.datetime`
        The current aware datetime in UTC.
    """
    return datetime.datetime.now(datetime.timezone.utc)


def snowflake_time(id: int, /) -> datetime.datetime:
    """Returns the creation time of a Bisim snowflake.

    Parameters
    -----------
    id: :class:`int`
        The snowflake ID.

    Returns
    --------
    :class:`datetime.datetime`
        An aware datetime in UTC representing the creation time of the snowflake.
    """
    milliseconds = (int(id) >> 22) + BISIM_EPOCH
    return datetime.datetime.fromtimestamp(milliseconds / 1000, tz=datetime.timezone.utc)


def time_snowflake(dt: datetime.datetime, /, *, high: bool = False) -> int:
    """Returns a numeric snowflake pretending to be created at the given date.

    When using as the lower end of a range, use ``time_snowflake(dt, high=False) - 1``
    to be inclusive, ``high=True`` to be exclusive.

    When using as the higher end of a range, use ``time_snowflake(dt, high=True) + 1``
    to be inclusive, ``high=False`` to be exclusive.

    Parameters
    -----------
    dt: :class:`datetime.datetime`
        A datetime object to convert to a snowflake.
        If naive, the timezone is assumed to be local time.
    high: :class:`bool`
        Whether or not to set the lower 22 bits to high or low.

    Returns
    --------
    :class:`int`
        The snowflake representing the time given.
    """
    milliseconds = int(dt.timestamp() * 1000)
    value = (milliseconds - BISIM_EPOCH) << 22
    if high:
        value += (1 << 22) - 1
    return value


def parse_time(timestamp: Optional[str]) -> Optional[datetime.datetime]:
    """Parses an ISO 8601 timestamp from Bisim into an aware datetime.

    Empty strings and ``None`` give ``None``, which is how Bisim's events say
    "not set".
    """
    if not timestamp:
        return None
    if isinstance(timestamp, datetime.datetime):
        return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=datetime.timezone.utc)
    text = str(timestamp).strip()
    if text.endswith('Z') or text.endswith('z'):
        text = text[:-1] + '+00:00'
    # Python 3.9 and 3.10 only accept 3 or 6 digit fractions.
    match = re.match(r'^(.*?\.)(\d+)(.*)$', text)
    if match:
        head, fraction, tail = match.groups()
        fraction = (fraction + '000000')[:6]
        text = head + fraction + tail
    try:
        result = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=datetime.timezone.utc)
    return result


def _isoformat(dt: Optional[datetime.datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')


def compute_timedelta(dt: datetime.datetime) -> float:
    """Returns the number of seconds from now until ``dt``, never negative."""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    now = datetime.datetime.now(datetime.timezone.utc)
    return max((dt - now).total_seconds(), 0)


@overload
async def sleep_until(when: datetime.datetime, result: T) -> T:
    ...


@overload
async def sleep_until(when: datetime.datetime) -> None:
    ...


async def sleep_until(when: datetime.datetime, result: Optional[T] = None) -> Optional[T]:
    """|coro|

    Sleep until a specified time.

    If the time supplied is in the past this function will yield instantly.

    Parameters
    -----------
    when: :class:`datetime.datetime`
        The timestamp in which to sleep until. If the datetime is naive then
        it is assumed to be local time.
    result: Any
        If provided is returned to the caller when the coroutine completes.
    """
    delta = compute_timedelta(when)
    return await asyncio.sleep(delta, result)


TimestampStyle = Literal['f', 'F', 'd', 'D', 't', 'T', 'R', 's', 'S']


def format_dt(dt: datetime.datetime, /, style: Optional[TimestampStyle] = None) -> str:
    """A helper function to format a :class:`datetime.datetime` for presentation within Bisim.

    This allows for a locale-independent way of presenting data using Bisim specific Markdown.

    +-------------+--------------------------------+-----------------+
    |    Style    |       Example Output           |   Description   |
    +=============+================================+=================+
    | t           | 22:57                          | Short Time      |
    +-------------+--------------------------------+-----------------+
    | T           | 22:57:58                       | Long Time       |
    +-------------+--------------------------------+-----------------+
    | d           | 17/05/2016                     | Short Date      |
    +-------------+--------------------------------+-----------------+
    | D           | 17 May 2016                    | Long Date       |
    +-------------+--------------------------------+-----------------+
    | f (default) | 17 May 2016 22:57              | Short Date Time |
    +-------------+--------------------------------+-----------------+
    | F           | Tuesday, 17 May 2016 22:57     | Long Date Time  |
    +-------------+--------------------------------+-----------------+
    | R           | 5 years ago                    | Relative Time   |
    +-------------+--------------------------------+-----------------+

    Parameters
    -----------
    dt: :class:`datetime.datetime`
        The datetime to format. If naive, it is assumed to be local time.
    style: :class:`str`
        The style to format the datetime with.

    Returns
    --------
    :class:`str`
        The formatted string.
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()
    seconds = int(dt.timestamp())
    if style is None:
        return f'<t:{seconds}>'
    return f'<t:{seconds}:{style}>'


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def _find_sync(predicate: Callable[[T], Any], iterable: Iterable[T], /) -> Optional[T]:
    for element in iterable:
        if predicate(element):
            return element
    return None


async def _find_async(predicate: Callable[[T], Any], iterable: AsyncIterable[T], /) -> Optional[T]:
    async for element in iterable:
        if predicate(element):
            return element
    return None


@overload
def find(predicate: Callable[[T], Any], iterable: AsyncIterable[T], /) -> Coroutine[Any, Any, Optional[T]]:
    ...


@overload
def find(predicate: Callable[[T], Any], iterable: Iterable[T], /) -> Optional[T]:
    ...


def find(predicate: Callable[[T], Any], iterable: _Iter[T], /) -> Union[Optional[T], Coroutine[Any, Any, Optional[T]]]:
    r"""A helper to return the first element found in the sequence
    that meets the predicate. For example: ::

        member = bisim.utils.find(lambda m: m.name == 'Mighty', channel.guild.members)

    would find the first :class:`~bisim.Member` whose name is 'Mighty' and return it.
    If an entry is not found, then ``None`` is returned.

    This is different from :func:`py:filter` due to the fact it stops the moment it finds
    a valid entry.

    Parameters
    -----------
    predicate
        A function that returns a boolean-like result.
    iterable: Union[:class:`collections.abc.Iterable`, :class:`collections.abc.AsyncIterable`]
        The iterable to search through. Using a :class:`collections.abc.AsyncIterable`,
        makes this function return a :term:`coroutine`.
    """
    if hasattr(iterable, '__aiter__'):
        return _find_async(predicate, iterable)  # type: ignore
    return _find_sync(predicate, iterable)  # type: ignore


def _attribute_matchers(attrs: Dict[str, Any]) -> List[Tuple[Callable[[Any], Any], Any]]:
    return [(attrgetter(name.replace('__', '.')), value) for name, value in attrs.items()]


def _get_sync(iterable: Iterable[T], /, **attrs: Any) -> Optional[T]:
    matchers = _attribute_matchers(attrs)
    for element in iterable:
        if all(getter(element) == value for getter, value in matchers):
            return element
    return None


async def _get_async(iterable: AsyncIterable[T], /, **attrs: Any) -> Optional[T]:
    matchers = _attribute_matchers(attrs)
    async for element in iterable:
        if all(getter(element) == value for getter, value in matchers):
            return element
    return None


@overload
def get(iterable: AsyncIterable[T], /, **attrs: Any) -> Coroutine[Any, Any, Optional[T]]:
    ...


@overload
def get(iterable: Iterable[T], /, **attrs: Any) -> Optional[T]:
    ...


def get(iterable: _Iter[T], /, **attrs: Any) -> Union[Optional[T], Coroutine[Any, Any, Optional[T]]]:
    r"""A helper that returns the first element in the iterable that meets
    all the traits passed in ``attrs``. This is an alternative for
    :func:`~bisim.utils.find`.

    When multiple attributes are specified, they are checked using
    logical AND, not logical OR. Meaning they have to meet every
    attribute passed in and not one of them.

    To have a nested attribute search (i.e. search by ``x.y``) then
    pass in ``x__y`` as the keyword argument.

    If nothing is found that matches the attributes passed, then
    ``None`` is returned.

    Examples
    ---------

    Basic usage:

    .. code-block:: python3

        member = bisim.utils.get(message.guild.members, name='Foo')

    Multiple attribute matching:

    .. code-block:: python3

        channel = bisim.utils.get(guild.voice_channels, name='Foo', bitrate=64000)

    Nested attribute matching:

    .. code-block:: python3

        channel = bisim.utils.get(client.get_all_channels(), guild__name='Cool', name='general')

    Parameters
    -----------
    iterable: Union[:class:`collections.abc.Iterable`, :class:`collections.abc.AsyncIterable`]
        The iterable to search through. Using a :class:`collections.abc.AsyncIterable`,
        makes this function return a :term:`coroutine`.
    \*\*attrs
        Keyword arguments that denote attributes to search with.
    """
    if hasattr(iterable, '__aiter__'):
        return _get_async(iterable, **attrs)  # type: ignore
    return _get_sync(iterable, **attrs)  # type: ignore


def _unique(iterable: Iterable[T]) -> List[T]:
    seen = set()
    result = []
    for item in iterable:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _get_as_snowflake(data: Any, key: str) -> Optional[int]:
    try:
        value = data[key]
    except (KeyError, TypeError):
        return None
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _snowflake(value: Any) -> Optional[int]:
    """An id from Bisim (a decimal string, or empty for "none") as an int."""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _id_of(value: Any) -> int:
    """The snowflake of an object with an ``id`` or of a plain int or string."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return int(value.id)


def _int(value: Any, default: int = 0) -> int:
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class CachedSlotProperty(Generic[T, T_co]):
    """A cached property for classes with ``__slots__``: the value is kept in a named slot."""

    def __init__(self, name: str, function: Callable[[T], T_co]) -> None:
        self.name = name
        self.function = function
        self.__doc__ = getattr(function, '__doc__')

    @overload
    def __get__(self, instance: None, owner: Type[T]) -> 'CachedSlotProperty[T, T_co]':
        ...

    @overload
    def __get__(self, instance: T, owner: Type[T]) -> T_co:
        ...

    def __get__(self, instance: Optional[T], owner: Type[T]) -> Any:
        if instance is None:
            return self
        try:
            return getattr(instance, self.name)
        except AttributeError:
            value = self.function(instance)
            setattr(instance, self.name, value)
            return value


def cached_slot_property(name: str) -> Callable[[Callable[[T], T_co]], CachedSlotProperty[T, T_co]]:
    def decorator(func: Callable[[T], T_co]) -> CachedSlotProperty[T, T_co]:
        return CachedSlotProperty(name, func)

    return decorator


class SnowflakeList(list):
    """A sorted list of snowflakes with fast membership tests (used for role ids)."""

    def __init__(self, data: Iterable[Any] = (), *, is_sorted: bool = False):
        values = [int(x) for x in data]
        super().__init__(values if is_sorted else sorted(set(values)))

    def add(self, element: int) -> None:
        element = int(element)
        if not self.has(element):
            bisect.insort(self, element)

    def get(self, element: int) -> Optional[int]:
        i = bisect.bisect_left(self, element)
        return self[i] if i != len(self) and self[i] == element else None

    def has(self, element: int) -> bool:
        i = bisect.bisect_left(self, int(element))
        return i != len(self) and self[i] == int(element)

    def discard(self, element: int) -> None:
        i = bisect.bisect_left(self, int(element))
        if i != len(self) and self[i] == int(element):
            del self[i]


async def maybe_coroutine(f: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    r"""|coro|

    A helper function that will await the result of a function if it's a coroutine
    or return the result if it's not.

    This is useful for functions that may or may not be coroutines.

    Parameters
    -----------
    f: Callable[..., Any]
        The function or coroutine to call.
    \*args
        The arguments to pass to the function.
    \*\*kwargs
        The keyword arguments to pass to the function.

    Returns
    --------
    Any
        The result of the function or coroutine.
    """
    value = f(*args, **kwargs)
    if inspect.isawaitable(value):
        return await value
    return value


async def async_all(gen: Iterable[Union[T, Awaitable[T]]], *, check: Callable[[Any], bool] = inspect.isawaitable) -> bool:
    for elem in gen:
        if check(elem):
            elem = await elem  # type: ignore
        if not elem:
            return False
    return True


async def sane_wait_for(futures: Iterable[Awaitable[T]], *, timeout: Optional[float]) -> Any:
    ensured = [asyncio.ensure_future(fut) for fut in futures]
    done, pending = await asyncio.wait(ensured, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
    if len(pending) != 0:
        raise asyncio.TimeoutError()
    return done


def _chunk_sync(iterator: Iterable[T], max_size: int) -> Iterator[List[T]]:
    chunk: List[T] = []
    for item in iterator:
        chunk.append(item)
        if len(chunk) == max_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


async def _chunk_async(iterator: AsyncIterable[T], max_size: int) -> AsyncIterator[List[T]]:
    chunk: List[T] = []
    async for item in iterator:
        chunk.append(item)
        if len(chunk) == max_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


@overload
def as_chunks(iterator: AsyncIterable[T], max_size: int) -> AsyncIterator[List[T]]:
    ...


@overload
def as_chunks(iterator: Iterable[T], max_size: int) -> Iterator[List[T]]:
    ...


def as_chunks(iterator: _Iter[T], max_size: int) -> Union[Iterator[List[T]], AsyncIterator[List[T]]]:
    """A helper function that collects an iterator into chunks of a given size.

    Parameters
    ----------
    iterator: Union[:class:`collections.abc.Iterable`, :class:`collections.abc.AsyncIterable`]
        The iterator to chunk, can be sync or async.
    max_size: :class:`int`
        The maximum chunk size.

    .. warning::

        The last chunk collected may not be as large as ``max_size``.

    Returns
    --------
    Union[:class:`Iterator`, :class:`AsyncIterator`]
        A new iterator which yields chunks of a given size.
    """
    if max_size <= 0:
        raise ValueError('Chunk sizes must be greater than 0.')
    if hasattr(iterator, '__aiter__'):
        return _chunk_async(iterator, max_size)  # type: ignore
    return _chunk_sync(iterator, max_size)  # type: ignore


def copy_doc(original: Callable[..., Any]) -> Callable[[T], T]:
    def decorator(overridden: T) -> T:
        overridden.__doc__ = original.__doc__
        try:
            overridden.__signature__ = inspect.signature(original)  # type: ignore
        except (TypeError, ValueError):
            pass
        return overridden

    return decorator


class SequenceProxy(collections.abc.Sequence, Generic[T_co]):
    """A read only proxy of a sequence."""

    def __init__(self, proxied: Iterable[T_co], *, sorted: bool = False):
        self.__proxied = proxied
        self.__sorted = sorted

    @functools.cached_property
    def __copied(self) -> List[T_co]:
        if self.__sorted:
            return sorted(self.__proxied)  # type: ignore
        return list(self.__proxied)

    def __repr__(self) -> str:
        return f'SequenceProxy({self.__proxied!r})'

    def __getitem__(self, idx: Any) -> Any:
        return self.__copied[idx]

    def __len__(self) -> int:
        return len(self.__copied)

    def __contains__(self, item: Any) -> bool:
        return item in self.__copied

    def __iter__(self) -> Iterator[T_co]:
        return iter(self.__copied)

    def __reversed__(self) -> Iterator[T_co]:
        return reversed(self.__copied)

    def index(self, value: Any, *args: Any, **kwargs: Any) -> int:
        return self.__copied.index(value, *args, **kwargs)

    def count(self, value: Any) -> int:
        return self.__copied.count(value)


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

#: The web app's address, used for jump links and the OAuth2 page.
WEB_URL = 'https://bisim.gg'


def oauth_url(
    client_id: Union[int, str],
    *,
    permissions: Permissions = MISSING,
    guild: Snowflake = MISSING,
    redirect_uri: str = MISSING,
    scopes: Iterable[str] = MISSING,
    disable_guild_select: bool = False,
    state: str = MISSING,
) -> str:
    """A helper function that returns the OAuth2 URL for adding a bot to a server.

    Bisim's address is ``https://bisim.gg/oauth2/authorize``. A Bisim bot gets
    its slash commands with the ``bot`` scope, so that is the default scope.

    Parameters
    -----------
    client_id: Union[:class:`int`, :class:`str`]
        The client ID for the bot, which is also its user ID.
    permissions: :class:`~bisim.Permissions`
        The permissions you're requesting. If not given then you won't be requesting any
        permissions.
    guild: :class:`~bisim.abc.Snowflake`
        The server to pre-select in the authorization screen, if available.
    redirect_uri: :class:`str`
        An optional valid redirect URI.
    scopes: Iterable[:class:`str`]
        An optional valid list of scopes. Defaults to ``('bot',)``.
    disable_guild_select: :class:`bool`
        Whether to disallow the user from changing the server dropdown.
    state: :class:`str`
        The state to return after the authorization.

    Returns
    --------
    :class:`str`
        The OAuth2 URL for adding the bot to a server.
    """
    params: Dict[str, Any] = {'client_id': str(client_id)}
    params['scope'] = ' '.join(scopes if scopes is not MISSING else ('bot',))
    if permissions is not MISSING:
        params['permissions'] = str(permissions.value)
    if guild is not MISSING:
        params['guild_id'] = str(guild.id)
    if disable_guild_select:
        params['disable_guild_select'] = 'true'
    if redirect_uri is not MISSING:
        params['response_type'] = 'code'
        params['redirect_uri'] = redirect_uri
    if state is not MISSING:
        params['state'] = state
    return f'{WEB_URL}/oauth2/authorize?' + urlencode(params)


class ResolvedInvite(NamedTuple):
    code: str
    event: Optional[int]


_INVITE_RE = re.compile(
    r'(?:https?://)?(?:www\.)?bisim\.gg/(?:(?:invite|r|invites)/)?(?P<code>[A-Za-z0-9_-]+)/?(?:\?(?P<query>\S*))?$'
)


def resolve_invite(invite: Union[Invite, str]) -> ResolvedInvite:
    """Resolves an invite from a :class:`~bisim.Invite`, URL or code.

    Accepts ``https://bisim.gg/<code>``, ``https://bisim.gg/invite/<code>``,
    ``https://bisim.gg/r/<code>`` and a bare code.

    Parameters
    -----------
    invite: Union[:class:`~bisim.Invite`, :class:`str`]
        The invite.

    Returns
    --------
    :class:`.ResolvedInvite`
        A data class containing the invite code and the event ID (always ``None`` on Bisim).
    """
    from .invite import Invite  # circular import

    if isinstance(invite, Invite):
        return ResolvedInvite(invite.code, None)
    text = str(invite).strip()
    match = _INVITE_RE.match(text)
    if match:
        return ResolvedInvite(match.group('code'), None)
    return ResolvedInvite(text.rstrip('/').rsplit('/', 1)[-1], None)


def resolve_template(code: Any) -> str:
    """Resolves a template code from a URL or code (``https://bisim.gg/template/<code>``)."""
    text = getattr(code, 'code', None) or str(code)
    match = re.match(r'(?:https?://)?(?:www\.)?bisim\.gg/template/([\w-]+)', text)
    return match.group(1) if match else text


# ---------------------------------------------------------------------------
# Markdown and mentions
# ---------------------------------------------------------------------------

_MARKDOWN_CHARS = r'\\*_~`|>#-'
_URL_RE = re.compile(r'(?P<url><[^: >]+:\/[^ >]+>|(?:https?|steam):\/\/[^\s<]+[^<.,:;\"\'\]\s])')
_MARKDOWN_STOCK = r'(?:\*\*|\*|__|_|~~|`{1,3}|\|\||>{1,3} |^#{1,3} |^-# |^ *[-*] |^\d+\. )'
_MARKDOWN_ESCAPE_RE = re.compile(r'([\\*_~`|>#\-\[\]()])')
_MARKDOWN_REMOVE_RE = re.compile(
    r'(\*\*|\*|__|_|~~|`{1,3}|\|\|)|(?m:^>{1,3} )|(?m:^#{1,3} )|(?m:^-# )|(?m:^ *[-*] )|(?m:^\d+\. )'
)
_MENTION_RE = re.compile(r'@(everyone|here|[!&]?[0-9]{17,20})')


def _split_links(text: str) -> List[Tuple[bool, str]]:
    """Splits text into (is_link, part) pieces so links can be left alone."""
    parts: List[Tuple[bool, str]] = []
    last = 0
    for match in _URL_RE.finditer(text):
        if match.start() > last:
            parts.append((False, text[last : match.start()]))
        parts.append((True, match.group(0)))
        last = match.end()
    if last < len(text):
        parts.append((False, text[last:]))
    return parts


def remove_markdown(text: str, *, ignore_links: bool = True) -> str:
    """A helper function that removes markdown characters.

    .. note::
            This function is not markdown aware and may remove meaning from the original text. For example,
            if the input contains ``10 * 5`` then it will be converted into ``10  5``.

    Parameters
    -----------
    text: :class:`str`
        The text to remove markdown from.
    ignore_links: :class:`bool`
        Whether to leave links alone when removing markdown. For example,
        if a URL in the text contains characters such as ``_`` then it will
        be left alone. Defaults to ``True``.

    Returns
    --------
    :class:`str`
        The text with the markdown special characters removed.
    """

    def strip(part: str) -> str:
        return _MARKDOWN_REMOVE_RE.sub('', part)

    if not ignore_links:
        return strip(text)
    return ''.join(part if is_link else strip(part) for is_link, part in _split_links(text))


def escape_markdown(text: str, *, as_needed: bool = False, ignore_links: bool = True) -> str:
    r"""A helper function that escapes Bisim's markdown.

    Parameters
    -----------
    text: :class:`str`
        The text to escape markdown from.
    as_needed: :class:`bool`
        Whether to escape the markdown characters as needed. This
        means that only characters that form markdown are escaped, and
        other punctuation such as brackets is left alone. Note however
        that this can open you up to some clever syntax abuse.
        Defaults to ``False``.
    ignore_links: :class:`bool`
        Whether to leave links alone when escaping markdown. For example,
        if a URL in the text contains characters such as ``_`` then it will
        be left alone. This option is not supported with ``as_needed``.
        Defaults to ``True``.

    Returns
    --------
    :class:`str`
        The text with the markdown special characters escaped with a slash.
    """

    if as_needed:
        pattern = re.compile(r'(?m)(\*\*|\*|__|_|~~|`{1,3}|\|\||^>{1,3} |^#{1,3} |^-# |^ *[-*] |^\d+\. )')

        def escape_needed(match: 're.Match[str]') -> str:
            token = match.group(0)
            leading = len(token) - len(token.lstrip(' '))
            body = token[leading:].rstrip(' ')
            trailing = token[leading + len(body) :]
            return token[:leading] + ''.join('\\' + char for char in body) + trailing

        text = text.replace('\\', '\\\\')
        return pattern.sub(escape_needed, text)

    def escape(part: str) -> str:
        return _MARKDOWN_ESCAPE_RE.sub(r'\\\1', part)

    if not ignore_links:
        return escape(text)
    return ''.join(part if is_link else escape(part) for is_link, part in _split_links(text))


def escape_mentions(text: str) -> str:
    """A helper function that escapes everyone, here, role, and user mentions.

    .. note::

        This does not include channel mentions.

    .. note::

        For more granular control over what mentions should be escaped
        within messages, refer to the :class:`~bisim.AllowedMentions`
        class.

    Parameters
    -----------
    text: :class:`str`
        The text to escape mentions from.

    Returns
    --------
    :class:`str`
        The text with the mentions removed.
    """
    return _MENTION_RE.sub('@​\\1', text)


def _string_width(string: str) -> int:
    """Width of a string in a monospaced font (wide East Asian characters count twice)."""
    width = 0
    for char in string:
        width += 2 if unicodedata.east_asian_width(char) in ('W', 'F', 'A') else 1
    return width


def _human_join(seq: Sequence[str], /, *, delimiter: str = ', ', final: str = 'or') -> str:
    size = len(seq)
    if size == 0:
        return ''
    if size == 1:
        return seq[0]
    if size == 2:
        return f'{seq[0]} {final} {seq[1]}'
    return delimiter.join(seq[:-1]) + f' {final} {seq[-1]}'


def _get_mime_type_for_image(data: bytes) -> str:
    if data.startswith(b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'):
        return 'image/png'
    if data[0:3] == b'\xff\xd8\xff' or data[6:10] in (b'JFIF', b'Exif'):
        return 'image/jpeg'
    if data.startswith((b'\x47\x49\x46\x38\x37\x61', b'\x47\x49\x46\x38\x39\x61')):
        return 'image/gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'image/webp'
    raise ValueError('Unsupported image type given')


# ---------------------------------------------------------------------------
# Annotation helpers (used by ext.commands and app_commands)
# ---------------------------------------------------------------------------

PY_310 = sys.version_info >= (3, 10)


def flatten_literal_params(parameters: Iterable[Any]) -> Tuple[Any, ...]:
    params = []
    literal_cls = type(Literal[0])
    for p in parameters:
        if isinstance(p, literal_cls):
            params.extend(p.__args__)
        else:
            params.append(p)
    return tuple(params)


def normalise_optional_params(parameters: Iterable[Any]) -> Tuple[Any, ...]:
    none_cls = type(None)
    return tuple(p for p in parameters if p is not none_cls) + (none_cls,)


def _eval_union_string(text: str, globalns: Dict[str, Any], localns: Dict[str, Any]) -> Any:
    """Evaluates ``A | B`` annotations on Python versions without PEP 604 at runtime."""
    depth = 0
    pieces: List[str] = []
    current = ''
    for char in text:
        if char in '[(':
            depth += 1
        elif char in '])':
            depth -= 1
        if char == '|' and depth == 0:
            pieces.append(current.strip())
            current = ''
            continue
        current += char
    pieces.append(current.strip())
    if len(pieces) == 1:
        return eval(text, globalns, localns)  # noqa: S307 - annotations are code written by the bot author
    values = tuple(resolve_annotation(piece, globalns, localns, None) for piece in pieces)
    return Union[values]  # type: ignore


def resolve_annotation(
    annotation: Any,
    globalns: Dict[str, Any],
    localns: Optional[Dict[str, Any]],
    cache: Optional[Dict[str, Any]],
) -> Any:
    """Turns a (possibly string) annotation into a real object.

    Handles ``from __future__ import annotations``, forward references and
    ``X | Y`` unions on Python 3.9.
    """
    if annotation is None:
        return type(None)
    if isinstance(annotation, ForwardRef):
        annotation = annotation.__forward_arg__
    locals_ = globalns if localns is None else localns
    if isinstance(annotation, str):
        if cache is not None and annotation in cache:
            return cache[annotation]
        try:
            value = eval(annotation, globalns, locals_)  # noqa: S307
        except TypeError:
            if '|' not in annotation:
                raise
            value = _eval_union_string(annotation, globalns, locals_)
        value = _resolve_nested(value, globalns, locals_, cache)
        if cache is not None:
            cache[annotation] = value
        return value
    return _resolve_nested(annotation, globalns, locals_, cache)


def _resolve_nested(annotation: Any, globalns: Dict[str, Any], localns: Dict[str, Any], cache: Optional[Dict[str, Any]]) -> Any:
    origin = typing.get_origin(annotation)
    if origin is None:
        if isinstance(annotation, (str, ForwardRef)):
            return resolve_annotation(annotation, globalns, localns, cache)
        return annotation
    args = typing.get_args(annotation)
    if not args:
        return annotation
    if origin is Literal:
        return annotation
    if origin is typing.Annotated:  # type: ignore[attr-defined]
        return annotation
    resolved = tuple(
        resolve_annotation(arg, globalns, localns, cache) if isinstance(arg, (str, ForwardRef)) else _resolve_nested(arg, globalns, localns, cache)
        for arg in args
    )
    if origin is Union or (PY_310 and _is_pep604_union(annotation)):
        return Union[resolved]  # type: ignore
    if resolved == args:
        return annotation
    try:
        return annotation.copy_with(resolved)  # type: ignore[attr-defined]
    except AttributeError:
        try:
            return origin[resolved]
        except TypeError:
            return annotation


def _is_pep604_union(annotation: Any) -> bool:
    return PY_310 and type(annotation).__name__ == 'UnionType'


def is_inside_class(func: Callable[..., Any]) -> bool:
    # A function defined in a class body has a dotted qualified name whose last
    # piece before the function name is not <locals>.
    if func.__qualname__ == func.__name__:
        return False
    (remaining, _, _) = func.__qualname__.rpartition('.')
    return not remaining.endswith('<locals>')


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def stream_supports_colour(stream: Any) -> bool:
    """Whether a stream (usually ``sys.stderr``) can show ANSI colours."""
    is_a_tty = hasattr(stream, 'isatty') and stream.isatty()
    if 'PYCHARM_HOSTED' in os.environ or os.environ.get('TERM_PROGRAM') == 'vscode':
        return is_a_tty
    if sys.platform != 'win32':
        return is_a_tty
    # Windows Terminal, and terminals that set ANSICON, understand colour codes.
    return is_a_tty and ('ANSICON' in os.environ or 'WT_SESSION' in os.environ)


class _ColourFormatter(logging.Formatter):
    """A log formatter with a coloured level name, for terminals that show colour."""

    _COLOURS = {
        logging.DEBUG: '\x1b[40;1m',
        logging.INFO: '\x1b[34;1m',
        logging.WARNING: '\x1b[33;1m',
        logging.ERROR: '\x1b[31m',
        logging.CRITICAL: '\x1b[41m',
    }

    def __init__(self) -> None:
        super().__init__()
        self._formatters = {
            level: logging.Formatter(
                f'\x1b[30;1m%(asctime)s\x1b[0m {colour}%(levelname)-8s\x1b[0m \x1b[35m%(name)s\x1b[0m %(message)s',
                '%Y-%m-%d %H:%M:%S',
            )
            for level, colour in self._COLOURS.items()
        }

    def format(self, record: logging.LogRecord) -> str:
        formatter = self._formatters.get(record.levelno, self._formatters[logging.DEBUG])
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f'\x1b[31m{text}\x1b[0m'
        output = formatter.format(record)
        record.exc_text = None
        return output


def setup_logging(
    *,
    handler: logging.Handler = MISSING,
    formatter: logging.Formatter = MISSING,
    level: int = MISSING,
    root: bool = True,
) -> None:
    """A helper function to setup logging.

    This is superficially similar to :func:`logging.basicConfig` but
    uses different defaults and a colour formatter if the stream can
    display colour.

    This is used by the :class:`~bisim.Client` to set up logging
    if ``log_handler`` is not ``None``.

    Parameters
    -----------
    handler: :class:`logging.Handler`
        The log handler to use for the library's logger.

        The default log handler if not provided is :class:`logging.StreamHandler`.
    formatter: :class:`logging.Formatter`
        The formatter to use with the given log handler. If not provided then it
        defaults to a colour based logging formatter (if available). If colour
        is not available then a simple logging formatter is provided.
    level: :class:`int`
        The default log level for the library's logger. Defaults to ``logging.INFO``.
    root: :class:`bool`
        Whether to set up the root logger rather than the library logger.
        Unlike the default for :class:`~bisim.Client`, this defaults to ``True``.
    """
    if level is MISSING:
        level = logging.INFO
    if handler is MISSING:
        handler = logging.StreamHandler()
    if formatter is MISSING:
        if isinstance(handler, logging.StreamHandler) and stream_supports_colour(handler.stream):
            formatter = _ColourFormatter()
        else:
            formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', '%Y-%m-%d %H:%M:%S', style='{')

    logger = logging.getLogger() if root else logging.getLogger(__name__.split('.')[0])
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)


def _shorten(text: str, limit: int, placeholder: str = '...') -> str:
    if len(text) <= limit:
        return text
    return text[: max(limit - len(placeholder), 0)] + placeholder


def _cdn_key(value: Any) -> Optional[str]:
    if not value:
        return None
    return str(value)

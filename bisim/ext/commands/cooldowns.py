from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Callable, Deque, Dict, Generic, Optional, TypeVar, Union

from ...app_commands.checks import Cooldown
from ...enums import Enum
from .errors import MaxConcurrencyReached

if TYPE_CHECKING:
    from typing_extensions import Self

    from ...message import Message

__all__ = (
    'BucketType',
    'Cooldown',
    'CooldownMapping',
    'DynamicCooldownMapping',
    'MaxConcurrency',
)

T_contra = TypeVar('T_contra', contravariant=True)


class BucketType(Enum):
    """Specifies a type of bucket for, e.g. a cooldown."""

    default = 0
    user = 1
    guild = 2
    channel = 3
    member = 4
    category = 5
    role = 6

    def get_key(self, msg: Any) -> Any:
        if self is BucketType.user:
            return msg.author.id
        elif self is BucketType.guild:
            return (msg.guild or msg.author).id
        elif self is BucketType.channel:
            return msg.channel.id
        elif self is BucketType.member:
            return ((msg.guild and msg.guild.id), msg.author.id)
        elif self is BucketType.category:
            return (getattr(msg.channel, 'category', None) or msg.channel).id
        elif self is BucketType.role:
            return (msg.channel if getattr(msg.channel, 'guild', None) is None else msg.author.top_role).id
        return None

    def __call__(self, msg: Any) -> Any:
        return self.get_key(msg)


class CooldownMapping(Generic[T_contra]):
    """A mapping of keys (users, channels...) to their cooldown buckets."""

    def __init__(
        self,
        original: Optional[Cooldown],
        type: Callable[[T_contra], Any],
    ) -> None:
        if not callable(type):
            raise TypeError('Cooldown type must be a BucketType or callable')

        self._cache: Dict[Any, Cooldown] = {}
        self._cooldown: Optional[Cooldown] = original
        self._type: Callable[[T_contra], Any] = type

    def copy(self) -> CooldownMapping[T_contra]:
        ret = CooldownMapping(self._cooldown, self._type)
        ret._cache = self._cache.copy()
        return ret

    @property
    def valid(self) -> bool:
        return self._cooldown is not None

    @property
    def type(self) -> Callable[[T_contra], Any]:
        return self._type

    @classmethod
    def from_cooldown(cls, rate: float, per: float, type: Callable[[T_contra], Any]) -> Self:
        return cls(Cooldown(rate, per), type)

    def _bucket_key(self, msg: T_contra) -> Any:
        return self._type(msg)

    def _verify_cache_integrity(self, current: Optional[float] = None) -> None:
        current = current or time.time()
        dead_keys = [k for k, v in self._cache.items() if current > v._last + v.per]
        for k in dead_keys:
            del self._cache[k]

    def create_bucket(self, message: T_contra) -> Cooldown:
        return self._cooldown.copy()  # type: ignore

    def get_bucket(self, message: T_contra, current: Optional[float] = None) -> Optional[Cooldown]:
        if self._type is BucketType.default:
            return self._cooldown

        self._verify_cache_integrity(current)
        key = self._bucket_key(message)
        if key not in self._cache:
            bucket = self.create_bucket(message)
            if bucket is not None:
                self._cache[key] = bucket
        else:
            bucket = self._cache[key]

        return bucket

    def update_rate_limit(self, message: T_contra, current: Optional[float] = None, tokens: int = 1) -> Optional[float]:
        bucket = self.get_bucket(message, current)
        if bucket is None:
            return None
        return bucket.update_rate_limit(current, tokens=tokens)


class DynamicCooldownMapping(CooldownMapping[T_contra]):
    """A cooldown mapping whose cooldown comes from a factory, per message."""

    def __init__(
        self,
        factory: Callable[[T_contra], Optional[Cooldown]],
        type: Callable[[T_contra], Any],
    ) -> None:
        super().__init__(None, type)
        self._factory: Callable[[T_contra], Optional[Cooldown]] = factory

    def copy(self) -> DynamicCooldownMapping[T_contra]:
        ret = DynamicCooldownMapping(self._factory, self._type)
        ret._cache = self._cache.copy()
        return ret

    @property
    def valid(self) -> bool:
        return True

    def create_bucket(self, message: T_contra) -> Optional[Cooldown]:  # type: ignore
        return self._factory(message)


class _Semaphore:
    """Free slots for one key of a :class:`MaxConcurrency`.

    A caller either waits for a slot or is refused at once, which is why the
    count itself has to be visible.
    """

    __slots__ = ('value', '_waiters')

    def __init__(self, number: int) -> None:
        self.value: int = number
        self._waiters: Deque[asyncio.Future[Any]] = deque()

    def __repr__(self) -> str:
        return f'<_Semaphore value={self.value} waiters={len(self._waiters)}>'

    def locked(self) -> bool:
        return self.value <= 0

    def is_active(self) -> bool:
        return bool(self._waiters)

    def _wake_next(self) -> None:
        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result(None)
                break

    async def acquire(self, *, wait: bool = False) -> bool:
        if self.value <= 0 and not wait:
            return False

        while self.value <= 0:
            waiter = asyncio.get_running_loop().create_future()
            self._waiters.append(waiter)
            try:
                await waiter
            except BaseException:
                waiter.cancel()
                if self.value > 0:
                    self._wake_next()
                raise

        self.value -= 1
        return True

    def release(self) -> None:
        self.value += 1
        self._wake_next()


class MaxConcurrency:
    """Limits how many invocations of a command may run at once."""

    __slots__ = ('number', 'per', 'wait', '_mapping')

    def __init__(self, number: int, *, per: BucketType, wait: bool) -> None:
        self._mapping: Dict[Any, _Semaphore] = {}
        self.per: BucketType = per
        self.number: int = number
        self.wait: bool = wait

        if number <= 0:
            raise ValueError("max_concurrency 'number' cannot be less than 1")

        if not isinstance(per, BucketType):
            raise TypeError(f"max_concurrency 'per' must be of type BucketType not {type(per)!r}")

    def copy(self) -> Self:
        return self.__class__(self.number, per=self.per, wait=self.wait)

    def __repr__(self) -> str:
        return f'<MaxConcurrency per={self.per!r} number={self.number} wait={self.wait}>'

    def get_key(self, message: Any) -> Any:
        return self.per.get_key(message)

    async def acquire(self, message: Any) -> None:
        key = self.get_key(message)

        try:
            sem = self._mapping[key]
        except KeyError:
            self._mapping[key] = sem = _Semaphore(self.number)

        acquired = await sem.acquire(wait=self.wait)
        if not acquired:
            raise MaxConcurrencyReached(self.number, self.per)

    async def release(self, message: Any) -> None:
        key = self.get_key(message)

        try:
            sem = self._mapping[key]
        except KeyError:
            return
        else:
            sem.release()

        if sem.value >= self.number and not sem.is_active():
            del self._mapping[key]

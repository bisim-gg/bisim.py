"""
bisim.ext.tasks
~~~~~~~~~~~~~~~~

Background tasks that run on a schedule, with the discord.ext.tasks API.

:copyright: (c) 2026 Bisim
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import datetime
import inspect
import logging
from typing import (
    Any,
    Callable,
    Coroutine,
    Generic,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import aiohttp

import bisim
from bisim.backoff import ExponentialBackoff
from bisim.utils import MISSING, utcnow

_log = logging.getLogger(__name__)

__all__ = ('loop',)

T = TypeVar('T')
_func = Callable[..., Coroutine[Any, Any, Any]]
LF = TypeVar('LF', bound=_func)
FT = TypeVar('FT', bound=_func)
ET = TypeVar('ET', bound=Callable[[Any, BaseException], Coroutine[Any, Any, Any]])

_UTC = datetime.timezone.utc


def _as_utc_time(value: datetime.time) -> datetime.time:
    if value.tzinfo is None:
        return value.replace(tzinfo=_UTC)
    return value


class Loop(Generic[LF]):
    """A background task helper that abstracts the loop and reconnection logic for you.

    The main interface to create this is through :func:`loop`.
    """

    def __init__(
        self,
        coro: LF,
        seconds: float,
        hours: float,
        minutes: float,
        time: Union[datetime.time, Sequence[datetime.time]],
        count: Optional[int],
        reconnect: bool,
        name: Optional[str],
    ) -> None:
        self.coro: LF = coro
        self.reconnect: bool = reconnect
        self.count: Optional[int] = count
        self._current_loop: int = 0
        self._task: Optional[asyncio.Task[None]] = None
        self._injected: Any = None
        self._valid_exception: Tuple[Type[BaseException], ...] = (
            OSError,
            bisim.GatewayNotFound,
            bisim.ConnectionClosed,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        )

        self._before_loop: Optional[Callable[..., Any]] = None
        self._after_loop: Optional[Callable[..., Any]] = None
        self._is_being_cancelled: bool = False
        self._has_failed: bool = False
        self._stop_next_iteration: bool = False
        self._name: str = f'bisim-ext-tasks: {coro.__qualname__}' if name is None else name
        self._wakeup: Optional[asyncio.Event] = None

        if self.count is not None and self.count <= 0:
            raise ValueError('count must be greater than 0 or None.')

        self._seconds: float = 0
        self._minutes: float = 0
        self._hours: float = 0
        self._sleep: float = 0
        self._time: List[datetime.time] = MISSING
        self.change_interval(seconds=seconds, minutes=minutes, hours=hours, time=time)
        self._last_iteration_failed: bool = False
        self._last_iteration: Optional[datetime.datetime] = MISSING
        self._next_iteration: Optional[datetime.datetime] = None

        if not inspect.iscoroutinefunction(self.coro):
            raise TypeError(f'Expected coroutine function, not {type(self.coro).__name__!r}.')

    async def _call_loop_function(self, name: str, *args: Any, **kwargs: Any) -> None:
        coro = getattr(self, '_' + name)
        if coro is None:
            return

        if self._injected is not None:
            await coro(self._injected, *args, **kwargs)
        else:
            await coro(*args, **kwargs)

    async def _sleep_until(self, when: datetime.datetime) -> None:
        """Sleeps until ``when``; a change of interval wakes it to look again."""
        if self._wakeup is None:
            self._wakeup = asyncio.Event()
        while True:
            target = self._next_iteration if self._next_iteration is not None else when
            delay = (target - utcnow()).total_seconds()
            if delay <= 0:
                return
            self._wakeup.clear()
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=delay)
            except asyncio.TimeoutError:
                return

    def _is_relative_time(self) -> bool:
        return self._time is MISSING

    def _is_explicit_time(self) -> bool:
        return self._time is not MISSING

    async def _loop(self, *args: Any, **kwargs: Any) -> None:
        backoff = ExponentialBackoff()
        await self._call_loop_function('before_loop')
        self._last_iteration_failed = False
        if self._is_explicit_time():
            self._next_iteration = self._get_next_sleep_time()
        else:
            self._next_iteration = utcnow()
        try:
            if self._stop_next_iteration:  # stop() was called before the first run
                return
            while True:
                if self._is_explicit_time():
                    await self._sleep_until(self._next_iteration)  # type: ignore
                if not self._last_iteration_failed:
                    self._last_iteration = self._next_iteration
                    self._next_iteration = self._get_next_sleep_time()
                try:
                    await self.coro(*args, **kwargs)
                    self._last_iteration_failed = False
                except self._valid_exception:
                    self._last_iteration_failed = True
                    if not self.reconnect:
                        raise
                    await asyncio.sleep(backoff.delay())
                else:
                    if self._stop_next_iteration:
                        return

                    if self._is_relative_time():
                        await self._sleep_until(self._next_iteration)  # type: ignore

                    self._current_loop += 1
                    if self._current_loop == self.count:
                        break

        except asyncio.CancelledError:
            self._is_being_cancelled = True
            raise
        except Exception as exc:
            self._has_failed = True
            await self._call_loop_function('error', exc)
            raise exc
        finally:
            await self._call_loop_function('after_loop')
            self._is_being_cancelled = False
            self._current_loop = 0
            self._stop_next_iteration = False
            self._has_failed = False

    def __get__(self, obj: T, objtype: Type[T]) -> Loop[LF]:
        if obj is None:
            return self

        copy: Loop[LF] = Loop(
            self.coro,
            seconds=self._seconds,
            hours=self._hours,
            minutes=self._minutes,
            time=self._time,
            count=self.count,
            reconnect=self.reconnect,
            name=self._name,
        )
        copy._injected = obj
        copy._before_loop = self._before_loop
        copy._after_loop = self._after_loop
        copy._error = self._error  # type: ignore
        setattr(obj, self.coro.__name__, copy)
        return copy

    @property
    def seconds(self) -> Optional[float]:
        """Optional[:class:`float`]: Read-only value for the number of seconds
        between each iteration. ``None`` if an explicit ``time`` value was passed instead.
        """
        if self._seconds is not MISSING:
            return self._seconds
        return None

    @property
    def minutes(self) -> Optional[float]:
        """Optional[:class:`float`]: Read-only value for the number of minutes
        between each iteration. ``None`` if an explicit ``time`` value was passed instead.
        """
        if self._minutes is not MISSING:
            return self._minutes
        return None

    @property
    def hours(self) -> Optional[float]:
        """Optional[:class:`float`]: Read-only value for the number of hours
        between each iteration. ``None`` if an explicit ``time`` value was passed instead.
        """
        if self._hours is not MISSING:
            return self._hours
        return None

    @property
    def time(self) -> Optional[List[datetime.time]]:
        """Optional[List[:class:`datetime.time`]]: Read-only list for the exact times this loop runs at.
        ``None`` if relative times were passed instead.
        """
        if self._time is not MISSING:
            return self._time.copy()
        return None

    @property
    def current_loop(self) -> int:
        """:class:`int`: The current iteration of the loop."""
        return self._current_loop

    @property
    def next_iteration(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: When the next iteration of the loop will occur."""
        if self._task is None or self._task.done() or self._stop_next_iteration:
            return None
        return self._next_iteration

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        r"""|coro|

        Calls the internal callback that the task holds.

        Parameters
        ------------
        \*args
            The arguments to use.
        \*\*kwargs
            The keyword arguments to use.
        """
        if self._injected is not None:
            args = (self._injected, *args)

        return await self.coro(*args, **kwargs)

    def start(self, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        r"""Starts the internal task in the event loop.

        Parameters
        ------------
        \*args
            The arguments to use.
        \*\*kwargs
            The keyword arguments to use.

        Raises
        --------
        RuntimeError
            A task has already been launched and is running.

        Returns
        ---------
        :class:`asyncio.Task`
            The task that has been created.
        """
        if self._task is not None and not self._task.done():
            raise RuntimeError('Task is already launched and is not completed.')

        if self._injected is not None:
            args = (self._injected, *args)

        self._has_failed = False
        self._task = asyncio.get_running_loop().create_task(self._loop(*args, **kwargs), name=self._name)
        return self._task

    def stop(self) -> None:
        r"""Gracefully stops the task from running.

        Unlike :meth:`cancel`\, this allows the task to finish its
        current iteration before gracefully exiting.

        .. note::

            If the internal function raises an error that can be
            handled before finishing then it will retry until
            it succeeds.

            If this is undesirable, either remove the error handling
            before stopping via :meth:`clear_exception_types` or
            use :meth:`cancel` instead.
        """
        if self._task is not None and not self._task.done():
            self._stop_next_iteration = True

    def _can_be_cancelled(self) -> bool:
        return bool(not self._is_being_cancelled and self._task and not self._task.done())

    def cancel(self) -> None:
        """Cancels the internal task, if it is running."""
        if self._can_be_cancelled() and self._task:
            self._task.cancel()

    def restart(self, *args: Any, **kwargs: Any) -> None:
        r"""A convenience method to restart the internal task.

        .. note::

            Due to the way this function works, the task is not
            returned like :meth:`start`.

        Parameters
        ------------
        \*args
            The arguments to use.
        \*\*kwargs
            The keyword arguments to use.
        """

        def restart_when_over(fut: Any, *, args: Any = args, kwargs: Any = kwargs) -> None:
            if self._task:
                self._task.remove_done_callback(restart_when_over)
            self.start(*args, **kwargs)

        if self._can_be_cancelled() and self._task:
            self._task.add_done_callback(restart_when_over)
            self._task.cancel()

    def add_exception_type(self, *exceptions: Type[BaseException]) -> None:
        r"""Adds exception types to be handled during the reconnect logic.

        By default the exception types handled are those handled by
        :meth:`bisim.Client.connect`\, which includes a lot of internet disconnection
        errors.

        This function is useful if you're interacting with a 3rd party library that
        raises its own set of exceptions.

        Parameters
        ------------
        \*exceptions: Type[:class:`BaseException`]
            An argument list of exception classes to handle.

        Raises
        --------
        TypeError
            An exception passed is either not a class or not inherited from :class:`BaseException`.
        """

        for exc in exceptions:
            if not inspect.isclass(exc):
                raise TypeError(f'{exc!r} must be a class.')
            if not issubclass(exc, BaseException):
                raise TypeError(f'{exc!r} must inherit from BaseException.')

        self._valid_exception = (*self._valid_exception, *exceptions)

    def clear_exception_types(self) -> None:
        """Removes all exception types that are handled.

        .. note::

            This operation obviously cannot be undone!
        """
        self._valid_exception = tuple()

    def remove_exception_type(self, *exceptions: Type[BaseException]) -> bool:
        r"""Removes exception types from being handled during the reconnect logic.

        Parameters
        ------------
        \*exceptions: Type[:class:`BaseException`]
            An argument list of exception classes to handle.

        Returns
        ---------
        :class:`bool`
            Whether all exceptions were successfully removed.
        """
        old_length = len(self._valid_exception)
        self._valid_exception = tuple(x for x in self._valid_exception if x not in exceptions)
        return len(self._valid_exception) == old_length - len(exceptions)

    def get_task(self) -> Optional[asyncio.Task[None]]:
        """Optional[:class:`asyncio.Task`]: Fetches the internal task or ``None`` if there isn't one running."""
        return self._task if self._task is not MISSING else None

    def is_being_cancelled(self) -> bool:
        """Whether the task is being cancelled."""
        return self._is_being_cancelled

    def failed(self) -> bool:
        """:class:`bool`: Whether the internal task has failed."""
        return self._has_failed

    def is_running(self) -> bool:
        """:class:`bool`: Check if the task is currently running."""
        return not bool(self._task is None or self._task.done())

    async def _error(self, *args: Any) -> None:
        exception: Exception = args[-1]
        _log.error('Unhandled exception in internal background task %r.', self.coro.__name__, exc_info=exception)

    def before_loop(self, coro: FT) -> FT:
        """A decorator that registers a coroutine to be called before the loop starts running.

        This is useful if you want to wait for some bot state before the loop starts,
        such as :meth:`bisim.Client.wait_until_ready`.

        The coroutine must take no arguments (except ``self`` in a class context).

        .. warning::

            Calling :meth:`stop` in this coroutine will stop the loop before the initial iteration is run.

        Parameters
        ------------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register before the loop runs.

        Raises
        -------
        TypeError
            The function was not a coroutine.
        """

        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f'Expected coroutine function, received {coro.__class__.__name__}.')

        self._before_loop = coro
        return coro

    def after_loop(self, coro: FT) -> FT:
        """A decorator that registers a coroutine to be called after the loop finishes running.

        The coroutine must take no arguments (except ``self`` in a class context).

        .. note::

            This coroutine is called even during cancellation. If it is desirable
            to tell apart whether something was cancelled or not, check to see
            whether :meth:`is_being_cancelled` is ``True`` or not.

        Parameters
        ------------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register after the loop finishes.

        Raises
        -------
        TypeError
            The function was not a coroutine.
        """

        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f'Expected coroutine function, received {coro.__class__.__name__}.')

        self._after_loop = coro
        return coro

    def error(self, coro: ET) -> ET:
        """A decorator that registers a coroutine to be called if the task encounters an unhandled exception.

        The coroutine must take only one argument the exception raised (except ``self`` in a class context).

        By default this logs to the library logger, however it could be
        overridden to have a different implementation.

        Parameters
        ------------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register in the event of an unhandled exception.

        Raises
        -------
        TypeError
            The function was not a coroutine.
        """
        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f'Expected coroutine function, received {coro.__class__.__name__}.')

        self._error = coro  # type: ignore
        return coro

    def _get_next_sleep_time(self, now: datetime.datetime = MISSING) -> datetime.datetime:
        if self._sleep is not MISSING:
            base = self._last_iteration if self._last_iteration not in (MISSING, None) else utcnow()
            return base + datetime.timedelta(seconds=self._sleep)  # type: ignore

        if now is MISSING:
            now = utcnow()

        # The next listed time today that is still ahead, or the first one tomorrow.
        today = now.date()
        for when in self._time:
            candidate = datetime.datetime.combine(today, when)
            if candidate.tzinfo is None:
                candidate = candidate.replace(tzinfo=_UTC)
            candidate = candidate.astimezone(_UTC)
            if candidate > now and (self._last_iteration in (MISSING, None) or candidate > self._last_iteration):  # type: ignore
                return candidate
        first = datetime.datetime.combine(today + datetime.timedelta(days=1), self._time[0])
        if first.tzinfo is None:
            first = first.replace(tzinfo=_UTC)
        return first.astimezone(_UTC)

    def _get_time_parameter(
        self,
        time: Union[datetime.time, Sequence[datetime.time]],
    ) -> List[datetime.time]:
        if isinstance(time, datetime.time):
            return [_as_utc_time(time)]
        if not isinstance(time, Sequence):
            raise TypeError(
                f'Expected datetime.time or a sequence of datetime.time for ``time``, received {type(time)!r} instead.'
            )
        if not time:
            raise ValueError('time parameter must not be an empty sequence.')

        ret: List[datetime.time] = []
        for index, t in enumerate(time):
            if not isinstance(t, datetime.time):
                raise TypeError(
                    f'Expected a sequence of {datetime.time!r} for ``time``, received {type(t).__name__!r} at index {index} instead.'
                )
            ret.append(_as_utc_time(t))

        def utc_key(t: datetime.time) -> datetime.datetime:
            return datetime.datetime.combine(datetime.date(2000, 1, 3), t).astimezone(_UTC)

        return sorted(set(ret), key=utc_key)

    def change_interval(
        self,
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        time: Union[datetime.time, Sequence[datetime.time]] = MISSING,
    ) -> None:
        """Changes the interval for the sleep time.

        .. note::

            This only applies on the next loop iteration. If it is desirable for the change of interval
            to be applied right away, cancel the task with :meth:`cancel`.

        Parameters
        ------------
        seconds: :class:`float`
            The number of seconds between every iteration.
        minutes: :class:`float`
            The number of minutes between every iteration.
        hours: :class:`float`
            The number of hours between every iteration.
        time: Union[:class:`datetime.time`, Sequence[:class:`datetime.time`]]
            The exact times to run this loop at. Either a non-empty list or a single
            value of :class:`datetime.time` should be passed.
            This cannot be used in conjunction with the relative time parameters.

        Raises
        -------
        ValueError
            An invalid value was given.
        TypeError
            An invalid value for the ``time`` parameter was passed, or the
            ``time`` parameter was passed in conjunction with relative time parameters.
        """

        if time is MISSING:
            seconds = seconds or 0
            minutes = minutes or 0
            hours = hours or 0
            sleep = seconds + (minutes * 60.0) + (hours * 3600.0)
            if sleep < 0:
                raise ValueError('Total number of seconds cannot be less than zero.')

            self._sleep = sleep
            self._seconds = float(seconds)
            self._hours = float(hours)
            self._minutes = float(minutes)
            self._time = MISSING
        else:
            if any((seconds, minutes, hours)):
                raise TypeError('Cannot mix explicit time with relative time')
            self._time = self._get_time_parameter(time)
            self._sleep = self._seconds = self._minutes = self._hours = MISSING

        if self.is_running() and getattr(self, '_last_iteration', MISSING) is not MISSING:
            self._next_iteration = self._get_next_sleep_time()
            if self._wakeup is not None:
                self._wakeup.set()


def loop(
    *,
    seconds: float = MISSING,
    minutes: float = MISSING,
    hours: float = MISSING,
    time: Union[datetime.time, Sequence[datetime.time]] = MISSING,
    count: Optional[int] = None,
    reconnect: bool = True,
    name: Optional[str] = None,
) -> Callable[[LF], Loop[LF]]:
    """A decorator that schedules a task in the background for you with
    optional reconnect logic. The decorator returns a :class:`Loop`.

    Parameters
    ------------
    seconds: :class:`float`
        The number of seconds between every iteration.
    minutes: :class:`float`
        The number of minutes between every iteration.
    hours: :class:`float`
        The number of hours between every iteration.
    time: Union[:class:`datetime.time`, Sequence[:class:`datetime.time`]]
        The exact times to run this loop at. Either a non-empty list or a single
        value of :class:`datetime.time` should be passed. Timezones are supported.
        If no timezone is given for the times, it is assumed to represent UTC time.

        This cannot be used in conjunction with the relative time parameters.

        .. note::

            Duplicate times will be ignored, and only run once.

    count: Optional[:class:`int`]
        The number of loops to do, ``None`` if it should be an
        infinite loop.
    reconnect: :class:`bool`
        Whether to handle errors and restart the task
        using an exponential back-off algorithm similar to the
        one used in :meth:`bisim.Client.connect`.
    name: Optional[:class:`str`]
        The name to assign to the internal task. By default
        it is assigned a name based off of the callable name
        such as ``bisim-ext-tasks: function_name``.

    Raises
    --------
    ValueError
        An invalid value was given.
    TypeError
        The function was not a coroutine, an invalid value for the ``time`` parameter was passed,
        or ``time`` parameter was passed in conjunction with relative time parameters.
    """

    def decorator(func: LF) -> Loop[LF]:
        return Loop[LF](
            func,
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            count=count,
            time=time,
            reconnect=reconnect,
            name=name,
        )

    return decorator

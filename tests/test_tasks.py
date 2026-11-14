"""ext.tasks: background loops."""

from __future__ import annotations

import asyncio
import datetime

import pytest

from bisim.ext import tasks


async def test_count_before_and_after():
    events = []

    @tasks.loop(seconds=0.01, count=3)
    async def tick():
        events.append(('tick', tick.current_loop))

    @tick.before_loop
    async def before():
        events.append('before')

    @tick.after_loop
    async def after():
        events.append('after')

    task = tick.start()
    await asyncio.wait_for(task, 2)
    assert events == ['before', ('tick', 0), ('tick', 1), ('tick', 2), 'after']
    assert not tick.is_running()


async def test_loop_bound_to_an_object_and_stop():
    class Worker:
        def __init__(self):
            self.runs = 0

        @tasks.loop(seconds=0.01)
        async def work(self):
            self.runs += 1
            if self.runs == 2:
                self.work.stop()

    worker = Worker()
    other = Worker()
    assert worker.work is not other.work
    await asyncio.wait_for(worker.work.start(), 2)
    assert worker.runs == 2 and other.runs == 0


async def test_cancel_and_error_handler():
    errors = []

    @tasks.loop(seconds=0.01)
    async def failing():
        raise RuntimeError('broken')

    @failing.error
    async def on_error(error):
        errors.append((type(error), failing.failed()))

    task = failing.start()
    with pytest.raises(RuntimeError):
        await asyncio.wait_for(task, 2)
    assert errors == [(RuntimeError, True)]
    assert not failing.is_running()

    @tasks.loop(seconds=10)
    async def slow():
        pass

    task = slow.start()
    await asyncio.sleep(0.01)
    assert slow.is_running()
    slow.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not slow.is_running()


async def test_reconnect_errors_are_retried(monkeypatch):
    attempts = []

    @tasks.loop(seconds=0.01, count=2)
    async def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError('network hiccup')

    sleeps = []
    real_sleep = asyncio.sleep

    async def fast_sleep(delay, result=None):
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr('bisim.ext.tasks.asyncio.sleep', fast_sleep)
    await asyncio.wait_for(flaky.start(), 2)
    assert len(attempts) == 3  # the failed run is retried, then two good ones


def test_intervals_and_times():
    @tasks.loop(minutes=1, hours=1)
    async def hourly():
        pass

    assert hourly.minutes == 1 and hourly.hours == 1
    hourly.change_interval(seconds=30)
    assert hourly.seconds == 30 and hourly.minutes == 0

    at = [datetime.time(9, 0, tzinfo=datetime.timezone.utc), datetime.time(21, 0, tzinfo=datetime.timezone.utc)]

    @tasks.loop(time=at)
    async def twice_a_day():
        pass

    assert twice_a_day.time == at

    async def body():
        pass

    with pytest.raises(TypeError):
        tasks.loop(seconds=1, time=at)(body)
    with pytest.raises(ValueError):
        tasks.loop(seconds=-1)(body)


async def test_calling_the_loop_runs_the_body_once():
    calls = []

    @tasks.loop(seconds=60)
    async def once(value):
        calls.append(value)

    await once(5)
    assert calls == [5]
    assert not once.is_running()

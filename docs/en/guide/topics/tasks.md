# Background tasks

`bisim.ext.tasks` runs a coroutine on a schedule: every few minutes, at set times of day, or a fixed number of
times. It handles the bookkeeping for you: it keeps the loop running across reconnects, retries after network
errors, and waits for the previous run to finish before starting the next.

## A simple loop

```python
import bisim
from bisim.ext import tasks


class MyClient(bisim.Client):
    async def setup_hook(self) -> None:
        # Start the loop once, when the bot starts
        self.report.start()

    @tasks.loop(minutes=30)
    async def report(self) -> None:
        channel = self.get_channel(123456789012345678)
        if channel is not None:
            await channel.send('Half an hour has passed.')

    @report.before_loop
    async def before_report(self) -> None:
        # The cache is empty until the bot is ready
        await self.wait_until_ready()


client = MyClient(intents=bisim.Intents.default())
```

`@tasks.loop()` turns the coroutine into a `Loop`. It runs once right after `start()` and then every 30 minutes.
The interval is given with `seconds`, `minutes` and `hours`, which can be combined (`minutes=1, seconds=30`).

`before_loop` runs once before the first iteration. Waiting for `wait_until_ready()` there is the usual
pattern: a loop started in `setup_hook` would otherwise run before the servers are loaded.

## At set times of day

Pass `time` instead of an interval, as one `datetime.time` or a list of them. Times without a time zone are
in UTC:

```python
import datetime

from bisim.ext import tasks

tehran = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
times = [datetime.time(hour=9, tzinfo=tehran), datetime.time(hour=21, tzinfo=tehran)]


@tasks.loop(time=times)
async def twice_a_day() -> None:
    print('Good morning, or good evening.')
```

## A fixed number of runs

`count` stops the loop after that many iterations, and `current_loop` tells you which one is running:

```python
@tasks.loop(seconds=10, count=5)
async def countdown() -> None:
    print(f'Iteration {countdown.current_loop + 1} of 5')


@countdown.after_loop
async def after_countdown() -> None:
    if countdown.is_being_cancelled():
        print('Cancelled before the end.')
    else:
        print('Done.')
```

`after_loop` runs once when the loop ends, whether it finished, was stopped or was cancelled.

## Starting and stopping

| Method | What it does |
| --- | --- |
| `start(*args, **kwargs)` | Starts the loop; the arguments are passed to every iteration. Raises `RuntimeError` if it is already running |
| `stop()` | Lets the current iteration finish, then ends the loop |
| `cancel()` | Cancels the loop at once, in the middle of an iteration if need be |
| `restart(*args, **kwargs)` | Cancels the loop and starts it again |
| `change_interval(seconds=..., minutes=..., hours=..., time=...)` | Changes the schedule from the next iteration on |
| `is_running()` | Whether the loop is running |
| `next_iteration` | When the next iteration is due, as a `datetime` |

A loop on a plain function (not a method) can be started from `on_ready`. Check `is_running()` first, so that
starting it twice never raises:

```python
@client.event
async def on_ready():
    if not countdown.is_running():
        countdown.start()
```

## Errors

With the default `reconnect=True`, an iteration that fails with a network error (`OSError`,
`bisim.ConnectionClosed`, `aiohttp.ClientError` or `asyncio.TimeoutError`) is retried with an increasing delay.
`add_exception_type()` adds more exception types to that list.

Any other exception ends the loop. By default it is logged; register your own handler with `error`:

```python
# Inside MyClient, below report
@report.error
async def report_error(self, error: Exception) -> None:
    print(f'The report failed: {error!r}')
```

The `Loop` class and every option are in the [API reference](../../reference/ext-tasks.md).

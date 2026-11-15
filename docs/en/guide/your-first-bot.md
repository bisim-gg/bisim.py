# Your first bot

Create a file named `bot.py` in your project folder:

```python
import os

import bisim

intents = bisim.Intents.default()
# Privileged: switch Message Content on for the bot at bisim.gg/developers first
intents.message_content = True
client = bisim.Client(intents=intents)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')


@client.event
async def on_message(message: bisim.Message):
    # Ignore messages from bots, this one included
    if message.author.bot:
        return
    if message.content == '!ping':
        await message.reply(f'Pong! {round(client.latency * 1000)} ms')


# Read the token from the BISIM_TOKEN environment variable
client.run(os.environ['BISIM_TOKEN'])
```

Run it with the token in `BISIM_TOKEN` (see [creating your application](creating-an-application.md)):

```sh
python bot.py
```

You should see `Logged in as ...`. Type `!ping` in a channel the bot can see and it answers. Stop the bot with
Ctrl+C.

## What happened

- `bisim.Client` is the connection to Bisim. `intents` says which events the bot wants, as on discord.py.
  Reading the text of messages in servers takes the privileged `message_content` intent: switch it on at
  [bisim.gg/developers](https://bisim.gg/developers) (your application, **Bot**, **Privileged Gateway
  Intents**), or the bot fails to connect with `PrivilegedIntentsRequired`. The [events](topics/events.md#intents)
  page explains every intent.
- `@client.event` registers a coroutine as an event handler. The function's name says which event it handles,
  so it must be spelt exactly, as in `on_message`. The [events](topics/events.md) page lists the others.
- `client.run()` is a blocking call. It sets up logging, logs in with the token, calls `setup_hook` and then
  connects to Bisim's gateway, reconnecting by itself when the connection drops. Anything after it only runs
  once the bot has stopped.
- `message.author.bot` is `True` for bots. Without the check a bot could answer itself in a loop.
- `client.latency` is the time, in seconds, between a heartbeat and Bisim's answer to it.

## What happens at startup

Bisim's gateway has no READY event carrying the bot's servers, so bisim.py builds its cache itself before it
calls `on_ready`:

1. It reads the bot's user and its list of servers over the REST API.
2. For each server it loads the channels, roles, custom emoji, stickers and voice states, and the members
   when the bot has the `members` intent, then subscribes to the server's events. `on_guild_available` is dispatched for each one.
3. When every server is in, it dispatches `on_ready`. From then on `client.guilds`, `client.get_channel()`
   and the rest of the cache are filled in.

A bot in many servers therefore takes a little longer to become ready. `on_ready` is dispatched once. If the
connection drops, the library reconnects, loads the servers again and dispatches `on_resumed` instead.

!!! tip

    Code that must run once, before any event, belongs in `setup_hook`, not in `on_ready`. The
    [slash commands](slash-commands/syncing.md) pages use it to sync commands.

## Setting a status

`change_presence` sets the bot's status and activity. It works once the bot is connected, for example in
`on_ready`:

```python
@client.event
async def on_ready():
    await client.change_presence(status=bisim.Status.idle, activity=bisim.Game(name='with Python'))
```

To start with a presence instead, pass it to the client:

```python
client = bisim.Client(
    intents=bisim.Intents.default(),
    status=bisim.Status.online,
    activity=bisim.Activity(type=bisim.ActivityType.watching, name='the server'),
)
```

| Activity | Shows as |
| --- | --- |
| `bisim.Game(name='chess')` | Playing chess |
| `bisim.Streaming(name='a match', url='https://example.com/live')` | Streaming a match |
| `bisim.Activity(type=bisim.ActivityType.listening, name='music')` | Listening to music |
| `bisim.Activity(type=bisim.ActivityType.watching, name='the server')` | Watching the server |
| `bisim.Activity(type=bisim.ActivityType.competing, name='a quiz')` | Competing in a quiz |
| `bisim.CustomActivity(name='Ask me anything', emoji='👋')` | A custom status with an emoji |

The statuses are `bisim.Status.online`, `idle`, `dnd` and `invisible`.

## Next steps

- Answer slash commands instead of reading messages: [slash commands](slash-commands/index.md).
- Prefer `!commands`? Use [bisim.ext.commands](commands/index.md).
- See every event a bot can handle: [events](topics/events.md).

# A local Bisim server

By default bisim.py talks to Bisim itself: the REST API at `https://api.bisim.gg/api`, the gateway at
`wss://ws.bisim.gg/ws` and files at `https://cdn.bisim.gg`. If you work on Bisim, or have a Bisim server for
development, point the library at it instead. Nothing else in the bot changes.

## With client options

`Client`, and so `commands.Bot`, take the three addresses as keyword arguments:

```python
import os

import bisim

client = bisim.Client(
    intents=bisim.Intents.default(),
    api_url='http://localhost:3000/api',
    gateway_url='ws://localhost:4000/ws',
)

client.run(os.environ['BISIM_TOKEN'])
```

| Option | Default | A local server |
| --- | --- | --- |
| `api_url` | `https://api.bisim.gg/api` | `http://localhost:3000/api` |
| `gateway_url` | `wss://ws.bisim.gg/ws` | `ws://localhost:4000/ws` |
| `cdn_url` | `https://cdn.bisim.gg` | where that server's files are served |

Note `http://` and `ws://`: a local server usually has no TLS. `cdn_url` only changes the links the library
builds for avatars, icons, emoji and stickers, so it can stay as it is while you test commands.

## With environment variables

When an option is not passed, the library reads it from the environment. This runs the same bot against a
local server or against Bisim without touching the code:

=== "Linux and macOS"

    ```sh
    export BISIM_API_URL=http://localhost:3000/api
    export BISIM_GATEWAY_URL=ws://localhost:4000/ws
    export BISIM_TOKEN=the-token-from-your-local-server
    python bot.py
    ```

=== "Windows (PowerShell)"

    ```powershell
    $env:BISIM_API_URL = "http://localhost:3000/api"
    $env:BISIM_GATEWAY_URL = "ws://localhost:4000/ws"
    $env:BISIM_TOKEN = "the-token-from-your-local-server"
    python bot.py
    ```

| Variable | Option |
| --- | --- |
| `BISIM_API_URL` | `api_url` |
| `BISIM_GATEWAY_URL` | `gateway_url` |
| `BISIM_CDN_URL` | `cdn_url` |

An option passed in the code wins over the environment.

## The token

A token belongs to the server that issued it. Create the application on the local server, in its Settings,
Applications, and use that token: a token from bisim.gg is refused by a local server, and the other way round.

## Checking the connection

Turn on the library's logs to see each step of the startup: logging in, opening the gateway and loading each
server.

```python
import logging

client.run(os.environ['BISIM_TOKEN'], log_level=logging.DEBUG)
```

If logging in fails with `bisim.LoginFailure`, the token does not belong to that server. If the gateway
cannot be reached, check `gateway_url` and that the server's gateway is running.

## Receiving interactions on a local server

A bot that uses an [Interactions URL](topics/interactions-url.md) needs an address the server can reach. Give
that address in the application's settings on the local server, and use the public key that server shows.
Without an Interactions URL, interactions arrive through the gateway as usual.

# Interactions URL

By default interactions reach your bot over the gateway, the same connection that brings messages and every
other event. You can instead give your application an **Interactions URL**: Bisim then sends each
interaction (slash commands, context menus, buttons, select menus, modals and autocomplete) as a signed HTTP
`POST` to that address, and no longer over the gateway.

Use it when your bot is a web service that answers commands and has no reason to stay connected. bisim.py
handles the HTTP side in `bisim.http_interactions`, built on aiohttp's web server, and the rest of your
code (the command tree, views and modals) stays the same.

## Setting it up

1. Install the extra that checks signatures (it adds PyNaCl):

    ```sh
    pip install "bisim.py[http]"
    ```

2. In Bisim, open **Settings**, **Applications**, your application, and fill in **Interactions URL** with a
   public `https` address that reaches your bot.
3. Copy the **public key** from the same page: 64 hex characters.

When you save the address, Bisim checks it: it sends a PING that must be answered `{"type": 1}`, and a request
with a deliberately wrong signature that must be refused with status 401. bisim.py does both for you.

## A complete bot

```python
import asyncio
import os

from aiohttp import web

import bisim
from bisim import app_commands
from bisim.http_interactions import create_interactions_app

client = bisim.Client(intents=bisim.Intents.default())
tree = app_commands.CommandTree(client)


@tree.command(description='Check that the bot is alive')
async def ping(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('Pong!')


async def main() -> None:
    async with client:
        # Logging in is enough to answer interactions: no gateway connection is needed.
        await client.login(os.environ['BISIM_TOKEN'])
        await tree.sync()
        app = create_interactions_app(client, os.environ['BISIM_PUBLIC_KEY'])
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, host='0.0.0.0', port=8787).start()
        await asyncio.Event().wait()  # serve until the process is stopped


asyncio.run(main())
```

`create_interactions_app(client, public_key, path='/')` returns an `aiohttp.web.Application` that answers
`POST` requests on `path`. Put it behind your usual web server or proxy for `https`.

## What happens to a request

For each request, bisim.py:

1. checks the `X-Signature-Ed25519` and `X-Signature-Timestamp` headers against the raw body with your public
   key, and answers 401 when they do not match;
2. answers a PING with `{"type": 1}`;
3. hands any other interaction to the client exactly as if it had come over the gateway: the command tree,
   views and modals run, and `on_interaction` is dispatched.

Bisim waits about three seconds for the answer. When your code answers within `answer_timeout` seconds
(2.5 by default), the answer goes back in the body of the HTTP response, Discord's way. When it takes longer,
the request is acknowledged with 202 and your answer goes through Bisim's API instead. Either way you write
`interaction.response.send_message()`, `defer()` and the rest as usual; see
[Responding to commands](../slash-commands/responding.md).

## Your own web application

To serve the interactions next to other routes, call `handle_interaction_request()` from your own handler:

```python
from bisim.http_interactions import handle_interaction_request

PUBLIC_KEY = os.environ['BISIM_PUBLIC_KEY']


async def interactions(request: web.Request) -> web.Response:
    return await handle_interaction_request(client, request, PUBLIC_KEY)


async def health(request: web.Request) -> web.Response:
    return web.Response(text='ok')


app = web.Application()
app.router.add_post('/bisim/interactions', interactions)
app.router.add_get('/health', health)
```

`verify_key(body, signature, timestamp, public_key)` is the signature check on its own: it returns `True` or
`False` for a body exactly as received. It works with PyNaCl or, if that is missing, with the `cryptography`
package, and raises `RuntimeError` when neither is installed.

## Without the gateway

A bot that only serves its Interactions URL has nothing in its caches: `interaction.guild` is a server known
only by its id, `interaction.channel` is a `PartialMessageable` and `client.get_guild()` returns `None`. The
interaction itself still carries the member, their permissions and the resolved options. If you also want
events and caches, connect to the gateway as well (`client.connect()` after logging in); interactions keep
arriving on the Interactions URL.

To go back to the gateway, clear the Interactions URL in the application settings.

The functions are in the [API reference](../../reference/http-interactions.md).

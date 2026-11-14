"""Receiving interactions on an Interactions URL instead of the gateway.

An application with an Interactions URL gets each interaction as an HTTP
POST signed with Ed25519, exactly like Discord: the ``X-Signature-Ed25519``
header (hex) is a signature over ``X-Signature-Timestamp + body`` made with
the application's key, whose public half is shown in Bisim's settings as 64
hex characters.

Verifying needs PyNaCl (``pip install "bisim.py[http]"``) or ``cryptography``.

Example::

    import bisim
    from aiohttp import web
    from bisim import app_commands
    from bisim.http_interactions import create_interactions_app

    client = bisim.Client()
    tree = app_commands.CommandTree(client)

    @tree.command()
    async def ping(interaction: bisim.Interaction):
        await interaction.response.send_message('pong')

    async def main():
        async with client:
            await client.login(TOKEN)
            app = create_interactions_app(client, PUBLIC_KEY)
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, port=8787).start()
            await asyncio.Event().wait()
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from . import utils

if TYPE_CHECKING:
    from aiohttp import web

    from .client import Client

__all__ = (
    'verify_key',
    'handle_interaction_request',
    'create_interactions_app',
)

_log = logging.getLogger(__name__)


def verify_key(body: Union[bytes, str], signature: str, timestamp: str, public_key: str) -> bool:
    """Checks the signature of an interaction delivered to an Interactions URL.

    Parameters
    -----------
    body: Union[:class:`bytes`, :class:`str`]
        The raw request body, exactly as received.
    signature: :class:`str`
        The ``X-Signature-Ed25519`` header (hex).
    timestamp: :class:`str`
        The ``X-Signature-Timestamp`` header.
    public_key: :class:`str`
        The application's public key: 32 bytes as 64 hex characters.

    Returns
    --------
    :class:`bool`
        Whether the signature is valid. A request that fails this check must be
        answered with 401.

    Raises
    -------
    RuntimeError
        Neither PyNaCl nor cryptography is installed.
    """
    if not signature or not timestamp or not public_key:
        return False
    if isinstance(body, str):
        body = body.encode('utf-8')
    try:
        message = timestamp.encode('utf-8') + body
        sig = bytes.fromhex(signature)
        key = bytes.fromhex(public_key)
    except ValueError:
        return False

    try:
        from nacl.exceptions import BadSignatureError  # type: ignore
        from nacl.signing import VerifyKey  # type: ignore
    except ModuleNotFoundError:
        pass
    else:
        try:
            VerifyKey(key).verify(message, sig)
            return True
        except (BadSignatureError, ValueError, TypeError):
            return False
        except Exception:
            return False

    try:
        from cryptography.exceptions import InvalidSignature  # type: ignore
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # type: ignore
    except ModuleNotFoundError:
        raise RuntimeError('Verifying interactions needs PyNaCl or cryptography: pip install "bisim.py[http]"') from None

    try:
        Ed25519PublicKey.from_public_bytes(key).verify(sig, message)
        return True
    except (InvalidSignature, ValueError):
        return False


async def handle_interaction_request(
    client: Client,
    request: web.Request,
    public_key: str,
    *,
    answer_timeout: float = 2.5,
) -> web.Response:
    """|coro|

    Handles one POST to an Interactions URL with :mod:`aiohttp.web`.

    The signature is checked (401 when it is wrong), a PING is answered with
    ``{"type": 1}``, and any other interaction is dispatched to the client
    like one from the gateway: the command tree, views and modals, and
    :func:`on_interaction`. When the bot answers within ``answer_timeout``
    seconds the answer goes back in the HTTP response; otherwise the request
    is acknowledged with 202 and the bot answers through the REST callback.

    Parameters
    -----------
    client: :class:`~bisim.Client`
        A logged in client.
    request: :class:`aiohttp.web.Request`
        The incoming request.
    public_key: :class:`str`
        The application's public key (hex).
    answer_timeout: :class:`float`
        How long to wait for the bot's first answer before acknowledging with
        202. Bisim waits about 3 seconds in all.

    Returns
    --------
    :class:`aiohttp.web.Response`
        The response to send back.
    """
    from aiohttp import web

    body = await request.read()
    signature = request.headers.get('X-Signature-Ed25519', '')
    timestamp = request.headers.get('X-Signature-Timestamp', '')
    if not verify_key(body, signature, timestamp, public_key):
        return web.Response(status=401, text='invalid request signature')

    try:
        payload: Dict[str, Any] = utils._from_json(body)
    except ValueError:
        return web.Response(status=400, text='invalid body')

    if int(payload.get('type', 0) or 0) == 1:
        return web.json_response({'type': 1})

    state = client._connection
    if state.loop is None:
        state.loop = asyncio.get_running_loop()
    if client.loop is None or not isinstance(client.loop, asyncio.AbstractEventLoop):
        await client._async_setup_hook()

    interaction_id = int(payload['id'])
    future: asyncio.Future[Dict[str, Any]] = asyncio.get_running_loop().create_future()
    state._http_interaction_responses[interaction_id] = future
    try:
        state._handle_interaction_payload(payload)
        try:
            answer = await asyncio.wait_for(asyncio.shield(future), timeout=answer_timeout)
        except asyncio.TimeoutError:
            return web.Response(status=202)
        return web.json_response(answer)
    finally:
        state._http_interaction_responses.pop(interaction_id, None)


def create_interactions_app(
    client: Client,
    public_key: str,
    *,
    path: str = '/',
    answer_timeout: float = 2.5,
) -> web.Application:
    """Creates an :class:`aiohttp.web.Application` that serves an Interactions URL.

    Parameters
    -----------
    client: :class:`~bisim.Client`
        A logged in client (``await client.login(token)``).
    public_key: :class:`str`
        The application's public key (hex).
    path: :class:`str`
        The path to answer on. Defaults to ``/``.
    answer_timeout: :class:`float`
        See :func:`handle_interaction_request`.

    Returns
    --------
    :class:`aiohttp.web.Application`
        The application, ready for :class:`aiohttp.web.AppRunner`.
    """
    from aiohttp import web

    async def handler(request: web.Request) -> web.Response:
        return await handle_interaction_request(client, request, public_key, answer_timeout=answer_timeout)

    app = web.Application()
    app.router.add_post(path, handler)
    return app

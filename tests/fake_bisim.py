"""A small fake of Bisim's REST API and gateway, served with aiohttp on localhost."""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any, Dict, List, Optional

from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer

from . import payloads as p

TOKEN = 'test-bot-token'


class FakeBisim:
    def __init__(self) -> None:
        self.guild_rows: List[Dict[str, Any]] = [copy.deepcopy(p.GUILD_ROW)]
        self.guild_details: Dict[str, Dict[str, Any]] = {p.GUILD_ID: copy.deepcopy(p.GUILD_DETAIL)}
        self.members: Dict[str, List[Dict[str, Any]]] = {p.GUILD_ID: copy.deepcopy(p.MEMBERS)}
        self.requests: List[Dict[str, Any]] = []
        self.frames: List[Dict[str, Any]] = []
        self.sockets: List[web.WebSocketResponse] = []
        self.passes = 0
        # The intents of the last pass (None: taken without a body), and a close code to refuse them with.
        self.intents: Optional[int] = None
        self.refuse_code: Optional[int] = None
        self.connections = 0
        self.connected = asyncio.Event()
        self.subscribed: Dict[str, asyncio.Event] = {}
        self.server: Optional[TestServer] = None

        app = web.Application()
        app.router.add_route('*', '/api/{tail:.*}', self.handle_rest)
        app.router.add_get('/ws', self.handle_ws)
        self.app = app

    async def start(self) -> None:
        self.server = TestServer(self.app)
        await self.server.start_server()

    async def close(self) -> None:
        for ws in list(self.sockets):
            await ws.close()
        if self.server is not None:
            await self.server.close()

    @property
    def api_url(self) -> str:
        assert self.server is not None
        return str(self.server.make_url('/api'))

    @property
    def gateway_url(self) -> str:
        assert self.server is not None
        return str(self.server.make_url('/ws')).replace('http://', 'ws://')

    # -- REST ----------------------------------------------------------

    def _json(self, data: Any, status: int = 200) -> web.Response:
        return web.json_response(data, status=status)

    async def handle_rest(self, request: web.Request) -> web.Response:
        tail = request.match_info['tail']
        body: Any = None
        if request.can_read_body:
            raw = await request.read()
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = raw
        self.requests.append({'method': request.method, 'path': '/' + tail, 'query': dict(request.query), 'body': body})

        if request.headers.get('Authorization') != f'Bot {TOKEN}' and not tail.startswith('interactions/'):
            return self._json({'statusCode': 401, 'message': 'Unauthorized'}, status=401)

        parts = tail.split('/')
        method = request.method

        if tail == 'auth/me':
            return self._json(p.ME)
        if tail == 'client-config':
            return self._json({'uploads': {'enabled': True, 'maxBytes': 10 * 1024 * 1024}})
        if tail == 'dms':
            return self._json([])
        if parts[0] == 'applications' and parts[-1] == 'gateway' and method == 'POST':
            self.passes += 1
            self.intents = (body or {}).get('intents') if isinstance(body, dict) else None
            return self._json({'token': f'pass-{self.passes}', 'expiresInMs': 900000, 'intents': self.intents or 0})
        if tail == 'guilds' and method == 'GET':
            return self._json(self.guild_rows)
        if parts[0] == 'guilds' and len(parts) == 2 and method == 'GET':
            detail = self.guild_details.get(parts[1])
            if detail is None:
                return self._json({'statusCode': 404, 'message': 'Guild not found'}, status=404)
            return self._json(detail)
        if parts[0] == 'guilds' and len(parts) == 3 and parts[2] == 'members':
            if self.intents is not None and not self.intents & (1 << 1):
                return self._json({'statusCode': 403, 'code': 'MISSING_INTENT', 'message': 'Missing intent'}, status=403)
            return self._json(self.members.get(parts[1], []))
        if parts[0] == 'guilds' and len(parts) == 3 and parts[2] == 'voice-states':
            return self._json({'states': []})
        if parts[0] == 'guilds' and len(parts) == 3 and parts[2] in ('emojis', 'stickers'):
            return self._json([])
        if parts[0] == 'channels' and len(parts) == 3 and parts[2] == 'messages' and method == 'POST':
            message = p.message(
                id='60000000000009999',
                channelId=parts[1],
                authorId=p.BOT_ID,
                type='DEFAULT',
                content=(body or {}).get('content', ''),
                referencedMessageId=None,
                referencedMessage=None,
                author=p.user_ref(p.BOT_ID, 'helper_bot', 'Helper', bot=True),
                attachments=[],
                embeds=[],
                reactions=[],
                components=(body or {}).get('components', []),
            )
            return self._json(message, status=201)
        if parts[0] == 'channels' and len(parts) == 3 and parts[2] == 'typing':
            return web.Response(status=204)
        if parts[0] == 'interactions':
            return web.Response(status=204)
        return self._json({'statusCode': 404, 'message': f'Cannot {method} /api/{tail}'}, status=404)

    # -- Gateway -------------------------------------------------------

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        token = request.query.get('token', '')
        if not token.startswith('pass-'):
            raise web.HTTPUnauthorized()
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.append(ws)
        self.connections += 1
        self.connected.set()
        if self.refuse_code is not None:
            # Bisim judges the intents at the handshake and closes before HELLO.
            await ws.close(code=self.refuse_code, message=b'Disallowed intent(s).')
            self.sockets.remove(ws)
            return ws
        await ws.send_json({'op': 1, 'd': {'heartbeatIntervalMs': 45000}})
        try:
            async for msg in ws:
                if msg.type is not WSMsgType.TEXT:
                    continue
                frame = json.loads(msg.data)
                self.frames.append(frame)
                op = frame.get('op')
                if op == 2:
                    await ws.send_json({'op': 3})
                elif op == 4:
                    guild_id = frame['d']['guildId']
                    if self.intents is not None and not self.intents & (1 << 8):
                        # No presence snapshot without the presences intent.
                        self.subscribed.setdefault(guild_id, asyncio.Event()).set()
                        continue
                    presences = [
                        {'userId': p.MEMBER_ID, 'guildId': guild_id, 'status': 'online', 'customText': 'busy'},
                        {'userId': p.OWNER_ID, 'guildId': guild_id, 'status': 'idle', 'activityType': 2, 'activityName': 'music'},
                    ]
                    await ws.send_json(
                        {
                            'op': 0,
                            't': 'PRESENCE_SYNC',
                            'd': {'type': 'PRESENCE_SYNC', 'guildId': guild_id, 'presenceSync': {'presences': presences}},
                        }
                    )
                    self.subscribed.setdefault(guild_id, asyncio.Event()).set()
        finally:
            if ws in self.sockets:
                self.sockets.remove(ws)
        return ws

    async def send(self, frame: Dict[str, Any]) -> None:
        for ws in list(self.sockets):
            await ws.send_json(frame)

    async def ask_reconnect(self) -> None:
        for ws in list(self.sockets):
            await ws.send_json({'op': 9})
            await ws.close()

    def frames_with_op(self, op: int) -> List[Dict[str, Any]]:
        return [f for f in self.frames if f.get('op') == op]

    def requests_to(self, method: str, path: str) -> List[Dict[str, Any]]:
        return [r for r in self.requests if r['method'] == method and r['path'] == path]

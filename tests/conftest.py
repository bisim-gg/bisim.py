from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest

import bisim
from bisim.guild import Guild
from bisim.http import HTTPClient
from bisim.state import ConnectionState

from . import payloads as p


class RecordingHTTP(HTTPClient):
    """An HTTPClient whose request() records calls and answers from a script."""

    def __init__(self) -> None:
        super().__init__(api_url='https://api.test/api', cdn_url='https://cdn.test')
        self.calls: List[Dict[str, Any]] = []
        self.responses: Dict[str, Any] = {}
        self.token = 'token'

    def respond(self, method: str, path: str, data: Any) -> None:
        self.responses[f'{method} {path}'] = data

    async def request(self, route: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        self.calls.append({'method': route.method, 'path': route.url, **kwargs})
        key = f'{route.method} {route.url}'
        data = self.responses.get(key)
        if callable(data):
            return data(route, kwargs)
        return data

    def last(self, method: str, path: str) -> Dict[str, Any]:
        for call in reversed(self.calls):
            if call['method'] == method and call['path'] == path:
                return call
        raise AssertionError(f'no {method} {path} call; calls were {[(c["method"], c["path"]) for c in self.calls]}')


@pytest.fixture
def http() -> RecordingHTTP:
    return RecordingHTTP()


@pytest.fixture
def dispatched() -> List[Any]:
    return []


@pytest.fixture
def state(http: RecordingHTTP, dispatched: List[Any]) -> ConnectionState:
    def dispatch(event: str, *args: Any, **kwargs: Any) -> None:
        dispatched.append((event, args))

    st = ConnectionState(dispatch=dispatch, handlers={}, hooks={}, http=http)
    st._get_websocket = lambda *a, **k: None  # type: ignore
    st._get_client = lambda: None  # type: ignore
    st._update_self(p.ME)
    return st


@pytest.fixture
def guild(state: ConnectionState) -> Guild:
    g = Guild(data=p.GUILD_DETAIL, state=state)
    for member in p.MEMBERS:
        g._store_member(member)
    g._chunked = True
    state._add_guild(g)
    return g


def events(dispatched: List[Any], name: str) -> List[Any]:
    return [args for event, args in dispatched if event == name]


async def settle(rounds: int = 50) -> None:
    """Lets the tasks the library scheduled run to completion (no real I/O happens in tests)."""
    for _ in range(rounds):
        await asyncio.sleep(0)


async def make_client(cls: Any, http: RecordingHTTP, **options: Any) -> Any:
    """A client of ``cls`` that is logged in as the test bot and has the test server loaded."""
    options.setdefault('intents', bisim.Intents.default())
    client = cls(api_url='https://api.test/api', cdn_url='https://cdn.test', **options)
    await client._async_setup_hook()
    client.http = http
    state = client._connection
    state.http = http
    state._update_self(p.ME)
    g = Guild(data=p.GUILD_DETAIL, state=state)
    for member in p.MEMBERS:
        g._store_member(member)
    g._chunked = True
    state._add_guild(g)
    return client


async def finish_tasks() -> None:
    """Cancels what is still waiting (view timeouts and the like) so the loop closes cleanly."""
    await settle()
    current = asyncio.current_task()
    pending = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.fixture
async def bot_client(http: RecordingHTTP) -> Any:
    client = await make_client(bisim.Client, http)
    yield client
    await finish_tasks()

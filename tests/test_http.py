from __future__ import annotations

import asyncio
import io
import json
import re
from typing import Any, List

import pytest
from aioresponses import CallbackResult, aioresponses

import bisim
from bisim.http import HTTPClient, Route

API = 'https://api.test/api'


@pytest.fixture
async def client():
    http = HTTPClient(api_url=API, cdn_url='https://cdn.test')
    http.token = 'abc'
    yield http
    await http.close()


@pytest.fixture
def sleeps(monkeypatch):
    calls: List[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay, result=None):
        calls.append(delay)
        await real_sleep(0)
        return result

    monkeypatch.setattr('bisim.http.asyncio.sleep', fake_sleep)
    return calls


async def test_sends_bot_authorization_and_json(client):
    with aioresponses() as m:
        m.post(f'{API}/channels/1/messages', payload={'id': '5'}, status=201)
        data = await client.send_message(1, {'content': 'hi'})
        assert data == {'id': '5'}
        request = next(iter(m.requests.values()))[0]
        assert request.kwargs['headers']['Authorization'] == 'Bot abc'
        assert json.loads(request.kwargs['data']) == {'content': 'hi'}


async def test_route_429_uses_body_retry_after(client, sleeps):
    with aioresponses() as m:
        m.post(f'{API}/channels/1/messages', status=429, payload={'message': 'You are sending messages too fast', 'retryAfter': 3})
        m.post(f'{API}/channels/1/messages', payload={'id': '9'})
        data = await client.send_message(1, {'content': 'x'})
    assert data == {'id': '9'}
    assert sleeps == [3.0]
    assert client._global_over.is_set()


async def test_global_429_pauses_every_request(client, sleeps):
    seen_paused = []

    def first(url, **kwargs):
        return CallbackResult(
            status=429,
            payload={'message': 'Too many requests. Try again later.', 'code': 'RATE_LIMITED', 'retryAfter': 7},
            headers={'Retry-After': '7', 'X-RateLimit-Limit': '600', 'X-RateLimit-Remaining': '0'},
        )

    real_sleep = sleeps

    with aioresponses() as m:
        m.get(f'{API}/guilds', callback=first)
        m.get(f'{API}/guilds', payload=[])
        data = await client.get_guilds()
    assert data == []
    assert real_sleep == [7.0]


async def test_header_retry_after_when_body_has_none(client, sleeps):
    with aioresponses() as m:
        m.get(f'{API}/users/2', status=429, body='slow down', headers={'Retry-After': '2'})
        m.get(f'{API}/users/2', payload={'id': '2', 'username': 'x'})
        data = await client.get_user(2)
    assert data['username'] == 'x'
    assert sleeps == [2.0]


async def test_retries_server_errors_then_succeeds(client, sleeps):
    with aioresponses() as m:
        m.get(f'{API}/guilds', status=502, body='bad gateway')
        m.get(f'{API}/guilds', status=503, body='busy')
        m.get(f'{API}/guilds', payload=[{'id': '1'}])
        data = await client.get_guilds()
    assert data == [{'id': '1'}]
    assert sleeps == [1, 3]


async def test_server_error_after_retries(client, sleeps):
    client.max_retries = 2
    with aioresponses() as m:
        m.get(f'{API}/guilds', status=500, payload={'statusCode': 500, 'message': 'Internal server error'})
        m.get(f'{API}/guilds', status=500, payload={'statusCode': 500, 'message': 'Internal server error'})
        with pytest.raises(bisim.BisimServerError) as info:
            await client.get_guilds()
    assert info.value.status == 500


async def test_error_mapping(client):
    with aioresponses() as m:
        m.get(f'{API}/guilds/1', status=404, payload={'statusCode': 404, 'message': 'Guild not found', 'error': 'Not Found'})
        m.post(f'{API}/applications/5/token', status=403, payload={'message': 'Not allowed for bots', 'code': 'BOT_NOT_ALLOWED'})
        m.post(f'{API}/guilds/1/channels', status=400, payload={'statusCode': 400, 'message': ['name must be shorter'], 'error': 'Bad Request'})
        with pytest.raises(bisim.NotFound) as not_found:
            await client.get_guild(1)
        assert not_found.value.text == 'Guild not found'

        with pytest.raises(bisim.Forbidden) as forbidden:
            await client.request(Route('POST', '/applications/{app_id}/token', app_id='5'))
        assert forbidden.value.code == 'BOT_NOT_ALLOWED'

        with pytest.raises(bisim.HTTPException) as bad:
            await client.create_channel(1, {'name': 'x' * 200})
        assert bad.value.errors == ['name must be shorter']
        assert bad.value.status == 400


async def test_static_login_failure(client):
    with aioresponses() as m:
        m.get(f'{API}/auth/me', status=401, payload={'statusCode': 401, 'message': 'Unauthorized'})
        with pytest.raises(bisim.LoginFailure):
            await client.static_login('wrong')
    assert client.token == 'abc'


async def test_same_route_requests_are_serialised(client):
    order = []
    gate = asyncio.Event()

    async def slow(url, **kwargs):
        order.append('start')
        await gate.wait()
        order.append('end')
        return CallbackResult(payload={'ok': True})

    with aioresponses() as m:
        m.post(f'{API}/channels/1/messages', callback=slow)
        m.post(f'{API}/channels/1/messages', callback=slow)
        first = asyncio.ensure_future(client.send_message(1, {'content': 'a'}))
        second = asyncio.ensure_future(client.send_message(1, {'content': 'b'}))
        await asyncio.sleep(0.05)
        assert order == ['start']
        gate.set()
        await asyncio.gather(first, second)
    assert order == ['start', 'end', 'start', 'end']


async def test_interaction_routes_have_no_bot_token(client):
    with aioresponses() as m:
        m.post(f'{API}/interactions/7/tok/callback', status=204)
        await client.create_interaction_response(7, 'tok', type=4, data={'content': 'x'})
        request = next(iter(m.requests.values()))[0]
        assert 'Authorization' not in request.kwargs['headers']
        assert json.loads(request.kwargs['data']) == {'type': 4, 'data': {'content': 'x'}}


async def test_file_upload_flow(state, guild):
    http = HTTPClient(api_url=API, cdn_url='https://cdn.test')
    http.token = 'abc'
    state.http = http
    channel = guild.get_channel(60000000000000201)
    upload_url = 'https://s3.test/uploads/abc?sig=1'
    with aioresponses() as m:
        m.post(
            f'{API}/channels/{channel.id}/attachments',
            payload={'attachments': [{'id': '777', 'uploadUrl': upload_url, 'uploadFilename': 'uploads/abc'}]},
            status=201,
        )
        m.put(upload_url, status=200)
        sent = {}

        def on_send(url, **kwargs):
            sent.update(json.loads(kwargs['data']))
            return CallbackResult(
                status=201,
                payload={
                    'id': '888',
                    'channelId': str(channel.id),
                    'authorId': str(state.self_id),
                    'type': 'DEFAULT',
                    'content': 'look',
                    'createdAt': '2026-11-01T00:00:00Z',
                    'author': {'id': str(state.self_id), 'username': 'helper_bot'},
                    'attachments': [],
                    'reactions': [],
                },
            )

        m.post(f'{API}/channels/{channel.id}/messages', callback=on_send)
        message = await channel.send('look', file=bisim.File(io.BytesIO(b'hello world'), filename='SPOILER_note.txt'))

        presign = [r for (method, url), reqs in m.requests.items() for r in reqs if url.path.endswith('/attachments')][0]
        assert json.loads(presign.kwargs['data']) == {'files': [{'fileName': 'note.txt', 'contentType': 'text/plain', 'sizeBytes': 11}]}
        put = [r for (method, url), reqs in m.requests.items() for r in reqs if method == 'PUT'][0]
        assert put.kwargs['data'] == b'hello world'
        assert put.kwargs['headers']['Content-Type'] == 'text/plain'
        assert 'Authorization' not in put.kwargs['headers']
    await http.close()

    assert message.id == 888
    assert sent['content'] == 'look'
    assert sent['attachments'] == [
        {
            'id': '777',
            'uploadFilename': 'uploads/abc',
            'fileName': 'note.txt',
            'contentType': 'text/plain',
            'sizeBytes': 11,
            'spoiler': True,
        }
    ]

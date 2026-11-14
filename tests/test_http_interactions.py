"""Interactions URL: signature checks and answering in the HTTP response."""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

import bisim
from bisim import app_commands
from bisim.http_interactions import create_interactions_app, verify_key

from . import payloads as p
from .conftest import settle

signing = pytest.importorskip('nacl.signing')


@pytest.fixture
def keys():
    key = signing.SigningKey.generate()
    return key, key.verify_key.encode().hex()


def signed(key, payload: dict, *, tamper: bool = False):
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()))
    signature = key.sign(timestamp.encode() + body).signature.hex()
    if tamper:
        body = body.replace(b'1', b'2', 1)
    return body, {'X-Signature-Ed25519': signature, 'X-Signature-Timestamp': timestamp, 'Content-Type': 'application/json'}


def test_verify_key(keys):
    key, public = keys
    body, headers = signed(key, {'type': 1})
    assert verify_key(body, headers['X-Signature-Ed25519'], headers['X-Signature-Timestamp'], public)
    assert not verify_key(body + b' ', headers['X-Signature-Ed25519'], headers['X-Signature-Timestamp'], public)
    assert not verify_key(body, 'zz', headers['X-Signature-Timestamp'], public)
    assert not verify_key(body, headers['X-Signature-Ed25519'], headers['X-Signature-Timestamp'], '00' * 32)


async def test_interactions_url_answers_in_the_body(bot_client, http, keys):
    key, public = keys
    tree = app_commands.CommandTree(bot_client)
    release = asyncio.Event()

    @tree.command(description='Quick')
    async def quick(interaction: bisim.Interaction):
        await interaction.response.send_message('fast', ephemeral=True)

    @tree.command(description='Slow')
    async def slow(interaction: bisim.Interaction):
        await release.wait()
        await interaction.response.send_message('late')

    app = create_interactions_app(bot_client, public, path='/bisim', answer_timeout=0.2)
    async with TestClient(TestServer(app)) as web:
        body, headers = signed(key, {'type': 1})
        response = await web.post('/bisim', data=body, headers=headers)
        assert response.status == 200 and await response.json() == {'type': 1}

        body, headers = signed(key, {'type': 1}, tamper=True)
        response = await web.post('/bisim', data=body, headers=headers)
        assert response.status == 401

        body, headers = signed(key, p.interaction(2, {'id': '1', 'name': 'quick', 'type': 1, 'options': []}))
        response = await web.post('/bisim', data=body, headers=headers)
        assert response.status == 200
        assert await response.json() == {'type': 4, 'data': {'content': 'fast', 'flags': 64}}
        assert not [c for c in http.calls if c['path'].endswith('/callback')]

        # Too slow for the HTTP answer: acknowledged with 202, then answered by REST.
        body, headers = signed(key, p.interaction(2, {'id': '2', 'name': 'slow', 'type': 1, 'options': []}))
        response = await web.post('/bisim', data=body, headers=headers)
        assert response.status == 202
        release.set()
        await settle()
        assert http.last('POST', f'/interactions/{p.INTERACTION_ID}/{p.INTERACTION_TOKEN}/callback')['json'] == {'type': 4, 'data': {'content': 'late'}}

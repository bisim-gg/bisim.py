"""Guild.bans pages the ban list the way discord.py does: ascending user ids, 1000 at a time."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

import bisim

from . import payloads as p

BANS = f'/guilds/{p.GUILD_ID}/bans'


def serve_bans(http: Any, count: int) -> List[int]:
    """A ban list that pages as Bisim's does: by user id, ascending, at most 1000 a page."""
    ids = [5000 + i * 2 for i in range(count)]

    def answer(route: Any, kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
        params = kwargs.get('params') or {}
        limit = int(params.get('limit', 1000))
        before, after = params.get('before'), params.get('after')
        if before is not None and after is None:
            rows = [i for i in ids if i < int(before)][-limit:]
        else:
            rows = [i for i in ids if i > int(after or 0)][:limit]
        return [{'guildId': p.GUILD_ID, 'userId': str(i), 'reason': None, 'user': {'id': str(i), 'username': f'u{i}'}} for i in rows]

    http.respond('GET', BANS, answer)
    return ids


def ban_calls(http: Any) -> List[Dict[str, Any]]:
    return [c['params'] for c in http.calls if c['method'] == 'GET' and c['path'] == BANS]


async def test_limit_none_reads_every_ban(guild, http):
    ids = serve_bans(http, 2500)
    entries = [entry async for entry in guild.bans(limit=None)]
    assert [e.user.id for e in entries] == ids
    assert ban_calls(http) == [
        {'limit': 1000, 'after': 0},
        {'limit': 1000, 'after': ids[999]},
        {'limit': 1000, 'after': ids[1999]},
    ]


async def test_default_limit_is_one_page(guild, http):
    ids = serve_bans(http, 1500)
    entries = [entry async for entry in guild.bans()]
    assert [e.user.id for e in entries] == ids[:1000]
    assert len(ban_calls(http)) == 1


async def test_limit_over_a_page_spans_pages(guild, http):
    ids = serve_bans(http, 2500)
    entries = [entry async for entry in guild.bans(limit=1500)]
    assert [e.user.id for e in entries] == ids[:1500]
    assert ban_calls(http) == [{'limit': 1000, 'after': 0}, {'limit': 500, 'after': ids[999]}]


async def test_after(guild, http):
    ids = serve_bans(http, 50)
    entries = [entry async for entry in guild.bans(limit=5, after=bisim.Object(id=ids[9]))]
    assert [e.user.id for e in entries] == ids[10:15]
    assert ban_calls(http) == [{'limit': 5, 'after': ids[9]}]


async def test_before_pages_downwards(guild, http):
    ids = serve_bans(http, 2500)
    entries = [entry async for entry in guild.bans(limit=None, before=bisim.Object(id=ids[2200]))]
    # Each page reads ascending; the next one is just below its first id.
    assert [e.user.id for e in entries] == ids[1200:2200] + ids[200:1200] + ids[0:200]
    calls = ban_calls(http)
    assert calls[0] == {'limit': 1000, 'before': ids[2200]}
    assert calls[1] == {'limit': 1000, 'before': ids[1200]}


async def test_both_cursors_refused(guild, http):
    with pytest.raises(TypeError):
        [entry async for entry in guild.bans(before=bisim.Object(id=1), after=bisim.Object(id=2))]


async def test_a_server_that_ignores_the_cursor_does_not_loop(guild, http):
    rows = [{'guildId': p.GUILD_ID, 'userId': str(7000 + i), 'reason': 'spam'} for i in range(1000)]
    http.respond('GET', BANS, rows)
    entries = [entry async for entry in guild.bans(limit=None)]
    assert len(entries) == 1000
    assert len({e.user.id for e in entries}) == 1000
    assert len(ban_calls(http)) == 2
    assert entries[0].reason == 'spam'

"""The client against a fake gateway: bootstrap, events, resync, join and reconnect."""

from __future__ import annotations

import asyncio
import copy
from typing import Any, Dict, List

import pytest

import bisim

from . import payloads as p
from .fake_bisim import TOKEN, FakeBisim


class Recorder(bisim.Client):
    def __init__(self, *, intents: bisim.Intents = None, **kwargs: Any) -> None:
        # Every intent by default (the privileged ones load members and presences).
        super().__init__(intents=intents if intents is not None else bisim.Intents.all(), **kwargs)
        self.seen: List[tuple] = []
        self.waiters: Dict[str, asyncio.Event] = {}

    def dispatch(self, event: str, /, *args: Any, **kwargs: Any) -> None:
        self.seen.append((event, args))
        self.waiters.setdefault(event, asyncio.Event()).set()
        super().dispatch(event, *args, **kwargs)

    async def wait_event(self, name: str, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self.waiters.setdefault(name, asyncio.Event()).wait(), timeout)

    def events(self, name: str) -> List[tuple]:
        return [args for event, args in self.seen if event == name]


@pytest.fixture
async def fake():
    server = FakeBisim()
    await server.start()
    yield server
    await server.close()


@pytest.fixture
async def client(fake):
    bot = Recorder(api_url=fake.api_url, gateway_url=fake.gateway_url, guild_ready_timeout=1.0)
    task = asyncio.ensure_future(bot.start(TOKEN))
    await bot.wait_event('ready')
    yield bot
    await bot.close()
    try:
        await asyncio.wait_for(task, 5)
    except Exception:
        pass


async def test_bootstrap_then_ready(client, fake):
    assert client.is_ready()
    assert client.user.id == int(p.BOT_ID)
    assert client.application_id == int(p.BOT_ID)
    assert client.user.bot

    # The pass is minted with the bot's id, and the guild detail is read before op 4.
    assert fake.requests_to('POST', f'/applications/{p.BOT_ID}/gateway')
    detail_index = next(i for i, r in enumerate(fake.requests) if r['path'] == f'/guilds/{p.GUILD_ID}')
    assert fake.frames_with_op(4) == [{'op': 4, 'd': {'guildId': p.GUILD_ID}}]
    assert fake.frames_with_op(7)[0]['d']['status'] == 'online'
    assert fake.frames_with_op(2)
    assert detail_index >= 0

    guild = client.get_guild(int(p.GUILD_ID))
    assert guild is not None and guild.name == 'Test Server'
    assert [c.name for c in guild.text_channels] == ['chat', 'staff']
    assert [c.name for c in guild.voice_channels] == ['Lounge']
    assert guild.me.id == int(p.BOT_ID)
    assert len(guild.members) == 3
    sara = guild.get_member(int(p.MEMBER_ID))
    assert sara.display_name == 'Sara'
    assert sara.status is bisim.Status.online
    assert str(sara.activity) == 'busy'
    owner = guild.owner
    assert owner.status is bisim.Status.idle
    assert owner.activity.type is bisim.ActivityType.listening
    assert client.events('guild_available')
    assert len(client.events('ready')) == 1


async def test_message_events(client, fake):
    await fake.send(p.envelope('MESSAGE_CREATE', guildId=p.GUILD_ID, channelId=p.TEXT_ID, message={**p.message(), 'guildId': p.GUILD_ID}))
    await client.wait_event('message')
    (message,) = client.events('message')[0]
    assert message.channel.name == 'chat'
    assert isinstance(message.author, bisim.Member)
    assert message.reference.resolved.content == 'earlier message'

    edited = {**p.message(content='edited!', editedAt='2026-11-01T12:05:00.000Z'), 'guildId': p.GUILD_ID}
    await fake.send(p.envelope('MESSAGE_UPDATE', guildId=p.GUILD_ID, channelId=p.TEXT_ID, message=edited))
    await client.wait_event('message_edit')
    before, after = client.events('message_edit')[0]
    assert before.content.startswith('hi') and after.content == 'edited!'
    assert after is message
    assert client.events('raw_message_edit')[0][0].cached_message is before

    await fake.send(
        p.envelope(
            'MESSAGE_REACTION_ADD',
            guildId=p.GUILD_ID,
            channelId=p.TEXT_ID,
            reaction={'messageId': p.MESSAGE_ID, 'channelId': p.TEXT_ID, 'guildId': p.GUILD_ID, 'userId': p.OWNER_ID, 'emoji': '🎉'},
        )
    )
    await client.wait_event('reaction_add')
    reaction, user = client.events('reaction_add')[0]
    assert reaction.emoji == '🎉' and user.id == int(p.OWNER_ID)
    raw = client.events('raw_reaction_add')[0][0]
    assert raw.member.id == int(p.OWNER_ID) and raw.emoji.name == '🎉'

    await fake.send(p.envelope('MESSAGE_DELETE', guildId=p.GUILD_ID, channelId=p.TEXT_ID, messageDelete={'id': p.MESSAGE_ID, 'channelId': p.TEXT_ID, 'guildId': p.GUILD_ID}))
    await client.wait_event('message_delete')
    assert client.events('message_delete')[0][0] is message


async def test_member_role_presence_typing_voice_events(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    new_member = {'userId': '60000000000000009', 'roleIds': [p.GUILD_ID], 'joinedAt': '2026-11-10T00:00:00Z', 'user': p.user_ref('60000000000000009', 'newbie')}
    await fake.send(p.envelope('GUILD_MEMBER_ADD', guildId=p.GUILD_ID, guildMember={'member': new_member}))
    await client.wait_event('member_join')
    assert client.events('member_join')[0][0].name == 'newbie'

    updated = {'userId': p.MEMBER_ID, 'nickname': 'Sara the Mod', 'roleIds': [p.GUILD_ID, p.MOD_ROLE_ID], 'user': p.user_ref(p.MEMBER_ID, 'sara', 'Sara K')}
    await fake.send(p.envelope('GUILD_MEMBER_UPDATE', guildId=p.GUILD_ID, guildMember={'member': updated}))
    await client.wait_event('member_update')
    before, after = client.events('member_update')[0]
    assert before.nick == 'Sara' and after.nick == 'Sara the Mod'

    await fake.send(p.envelope('GUILD_ROLE_CREATE', guildId=p.GUILD_ID, guildRole={'role': {'id': '60000000000000109', 'name': 'VIP', 'position': 3, 'permissions': '0'}}))
    await client.wait_event('guild_role_create')
    assert guild.get_role(60000000000000109).name == 'VIP'

    await fake.send(p.envelope('GUILD_ROLE_DELETE', guildId=p.GUILD_ID, guildRoleDelete={'roleId': '60000000000000109'}))
    await client.wait_event('guild_role_delete')
    assert guild.get_role(60000000000000109) is None

    await fake.send(p.envelope('PRESENCE_UPDATE', guildId=p.GUILD_ID, presence={'userId': p.MEMBER_ID, 'guildId': p.GUILD_ID, 'status': 'dnd', 'activityName': 'chess'}))
    await client.wait_event('presence_update')
    before, after = client.events('presence_update')[0]
    assert before.status is bisim.Status.online and after.status is bisim.Status.dnd
    assert isinstance(after.activity, bisim.Game) and after.activity.name == 'chess'

    await fake.send(p.envelope('TYPING_START', guildId=p.GUILD_ID, channelId=p.TEXT_ID, typing={'channelId': p.TEXT_ID, 'guildId': p.GUILD_ID, 'userId': p.MEMBER_ID, 'timestamp': '1794600000000'}))
    await client.wait_event('typing')
    channel, user, when = client.events('typing')[0]
    assert channel.name == 'chat' and user.id == int(p.MEMBER_ID) and when.year == 2026

    await fake.send(p.envelope('VOICE_STATE_UPDATE', guildId=p.GUILD_ID, channelId=p.VOICE_ID, voiceState={'userId': p.MEMBER_ID, 'selfMuted': True}))
    await client.wait_event('voice_state_update')
    member, before, after = client.events('voice_state_update')[0]
    assert before.channel is None and after.channel.name == 'Lounge' and after.self_mute
    assert guild.get_channel(int(p.VOICE_ID)).members == [member]

    await fake.send(p.envelope('GUILD_MEMBER_REMOVE', guildId=p.GUILD_ID, guildMemberRemove={'userId': '60000000000000009'}))
    await client.wait_event('member_remove')
    assert guild.get_member(60000000000000009) is None


async def test_guild_resync_diffs_channels_and_roles(client, fake):
    detail = fake.guild_details[p.GUILD_ID]
    detail['channels'] = [c for c in detail['channels'] if c['id'] != p.PRIVATE_TEXT_ID]
    detail['channels'].append(p.channel('60000000000000209', 'announcements', 'GUILD_TEXT', 3))
    for c in detail['channels']:
        if c['id'] == p.TEXT_ID:
            c['topic'] = 'New topic'
    for r in detail['roles']:
        if r['id'] == p.MOD_ROLE_ID:
            r['name'] = 'Mods'

    await fake.send(p.envelope('GUILD_RESYNC', guildId=p.GUILD_ID, guildResync={}))
    await client.wait_event('guild_role_update')
    await client.wait_event('guild_channel_delete')
    created = client.events('guild_channel_create')[0][0]
    assert created.name == 'announcements'
    deleted = client.events('guild_channel_delete')[0][0]
    assert deleted.name == 'staff'
    updates = {after.name: (before, after) for before, after in client.events('guild_channel_update')}
    assert updates['chat'][0].topic == 'Talk here' and updates['chat'][1].topic == 'New topic'
    before, after = client.events('guild_role_update')[0]
    assert before.name == 'Moderators' and after.name == 'Mods'


async def test_resync_404_is_guild_remove(client, fake):
    del fake.guild_details[p.GUILD_ID]
    await fake.send(p.envelope('GUILD_RESYNC', guildId=p.GUILD_ID, guildResync={}))
    await client.wait_event('guild_remove')
    assert client.get_guild(int(p.GUILD_ID)) is None


async def test_guild_join_loads_and_subscribes(client, fake):
    new_id = '60000000000000700'
    detail = copy.deepcopy(p.GUILD_DETAIL)
    detail['id'] = new_id
    detail['name'] = 'Second Server'
    detail['channels'] = [p.channel('60000000000000701', 'welcome', 'GUILD_TEXT', 0, guildId=new_id)]
    detail['roles'] = [p.role(new_id, '@everyone', 0, p.EVERYONE_PERMS, guildId=new_id)]
    fake.guild_details[new_id] = detail
    fake.members[new_id] = []

    await fake.send(p.envelope('GUILD_JOIN', userId=p.BOT_ID, guildJoin={'guildId': new_id}))
    await client.wait_event('guild_join')
    guild = client.events('guild_join')[0][0]
    assert guild.name == 'Second Server'
    assert {'op': 4, 'd': {'guildId': new_id}} in fake.frames
    assert client.get_guild(int(new_id)) is guild


async def test_interaction_create_reaches_on_interaction(client, fake):
    payload = {
        'id': '60000000000000800',
        'type': 2,
        'token': 'itok',
        'applicationId': p.BOT_ID,
        'guildId': p.GUILD_ID,
        'channelId': p.TEXT_ID,
        'member': {'userId': p.MEMBER_ID, 'username': 'sara', 'displayName': 'Sara K', 'avatarKey': None, 'roleIds': [p.GUILD_ID], 'permissions': p.EVERYONE_PERMS},
        'user': p.user_ref(p.MEMBER_ID, 'sara', 'Sara K'),
        'locale': 'fa',
        'data': {'id': '1', 'name': 'ping', 'options': []},
    }
    import json

    await fake.send(p.envelope('INTERACTION_CREATE', userId=p.BOT_ID, interaction={'payloadJson': json.dumps(payload)}))
    await client.wait_event('interaction')
    (interaction,) = client.events('interaction')[0]
    assert interaction.type is bisim.InteractionType.application_command
    assert interaction.user.id == int(p.MEMBER_ID)
    assert interaction.locale is bisim.Locale.persian
    assert interaction.channel.name == 'chat'
    assert interaction.permissions.use_application_commands


async def test_reconnect_on_op9_resumes_without_second_ready(client, fake):
    await fake.ask_reconnect()
    await client.wait_event('resumed', timeout=10)
    assert fake.passes == 2
    assert fake.connections == 2
    assert len(client.events('ready')) == 1
    assert client.events('disconnect')


async def test_change_presence_sends_op7(client, fake):
    await client.change_presence(activity=bisim.Game('chess'), status=bisim.Status.idle)
    await client.change_presence(activity=bisim.CustomActivity('Working'), status=bisim.Status.dnd)
    await asyncio.sleep(0.1)
    frames = fake.frames_with_op(7)
    assert frames[-2]['d'] == {'status': 'idle', 'customText': '', 'customEmoji': '', 'expiresAt': 0, 'activity': {'type': 0, 'name': 'chess'}}
    assert frames[-1]['d'] == {'status': 'dnd', 'customText': 'Working', 'customEmoji': '', 'expiresAt': 0}
    assert client.latency >= 0

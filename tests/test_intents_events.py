"""Intents, their close codes, and the bot events Bisim sends since its gateway took Discord's intents."""

from __future__ import annotations

import asyncio
import copy
import datetime
import json
from typing import Any

import pytest

import bisim

from . import payloads as p
from .fake_bisim import TOKEN, FakeBisim
from .test_gateway import Recorder

STRANGER_ID = '60000000000000777'


def stranger(username: str = 'stranger') -> dict:
    return {'id': STRANGER_ID, 'username': username, 'displayName': 'Stranger Danger', 'avatarKey': 'avatars/s.webp'}


@pytest.fixture
async def fake():
    server = FakeBisim()
    await server.start()
    yield server
    await server.close()


async def start_bot(fake: FakeBisim, **options: Any) -> Recorder:
    options.setdefault('guild_ready_timeout', 5.0)
    bot = Recorder(api_url=fake.api_url, gateway_url=fake.gateway_url, **options)
    bot._test_task = asyncio.ensure_future(bot.start(TOKEN))  # type: ignore[attr-defined]
    await bot.wait_event('ready', timeout=3.0)
    return bot


async def stop_bot(bot: Recorder) -> None:
    await bot.close()
    try:
        await asyncio.wait_for(bot._test_task, 5)  # type: ignore[attr-defined]
    except Exception:
        pass


@pytest.fixture
async def client(fake):
    bot = await start_bot(fake)
    yield bot
    await stop_bot(bot)


@pytest.fixture
async def lean_client(fake):
    """A bot with the default intents: no members, presences or message content."""
    bot = await start_bot(fake, intents=bisim.Intents.default())
    yield bot
    await stop_bot(bot)


async def wait_until(predicate: Any, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError('timed out waiting')
        await asyncio.sleep(0.01)


# -- Intents -------------------------------------------------------------


async def test_the_pass_carries_the_intents(client, fake):
    (taken,) = fake.requests_to('POST', f'/applications/{p.BOT_ID}/gateway')
    assert taken['body'] == {'intents': bisim.Intents.all().value}


async def test_default_intents_do_not_chunk_or_wait_for_presences(lean_client, fake):
    (taken,) = fake.requests_to('POST', f'/applications/{p.BOT_ID}/gateway')
    assert taken['body'] == {'intents': bisim.Intents.default().value}
    # Ready came without a presence snapshot to wait for (guild_ready_timeout is 5 s, the wait above 3 s).
    assert not fake.requests_to('GET', f'/guilds/{p.GUILD_ID}/members')
    guild = lean_client.get_guild(int(p.GUILD_ID))
    assert guild is not None and not guild.chunked
    assert guild.get_member(int(p.MEMBER_ID)) is None
    assert guild.me.id == int(p.BOT_ID)

    with pytest.raises(bisim.ClientException):
        await guild.chunk()
    with pytest.raises(bisim.ClientException):
        [m async for m in guild.fetch_members(limit=10)]
    assert not fake.requests_to('GET', f'/guilds/{p.GUILD_ID}/members')


async def test_voice_and_reactions_carry_members_without_the_intent(lean_client, fake):
    """Discord gives the member of whoever is in voice or reacts, so a default-intents bot knows them as Members."""
    client = lean_client
    guild = client.get_guild(int(p.GUILD_ID))
    member = {'userId': '60000000000000901', 'nickname': 'Caz', 'roleIds': [p.GUILD_ID, p.MOD_ROLE_ID],
              'joinedAt': '2026-07-02T00:00:00.000Z',
              'user': {'id': '60000000000000901', 'username': 'carol', 'displayName': 'Carol'}}
    await fake.send(p.envelope('VOICE_STATE_UPDATE', guildId=p.GUILD_ID, channelId=p.VOICE_ID,
                               voiceState={'userId': member['userId'], 'user': member['user'], 'member': member}))
    await wait_until(lambda: guild.get_member(int(member['userId'])) is not None)
    carol = guild.get_member(int(member['userId']))
    assert isinstance(carol, bisim.Member) and carol.nick == 'Caz'
    assert any(r.id == int(p.MOD_ROLE_ID) for r in carol.roles)
    assert carol.voice is not None and carol.voice.channel is not None and carol.voice.channel.id == int(p.VOICE_ID)

    reacting = {'userId': '60000000000000902', 'roleIds': [p.GUILD_ID], 'joinedAt': '2026-07-03T00:00:00.000Z',
                'user': {'id': '60000000000000902', 'username': 'erin', 'displayName': 'Erin'}}
    await fake.send(p.envelope('MESSAGE_REACTION_ADD', guildId=p.GUILD_ID, channelId=p.TEXT_ID,
                               reaction={'messageId': p.MESSAGE_ID, 'channelId': p.TEXT_ID, 'guildId': p.GUILD_ID,
                                         'userId': reacting['userId'], 'emoji': '👍', 'member': reacting}))
    await client.wait_event('raw_reaction_add')
    raw = client.events('raw_reaction_add')[-1][0]
    assert isinstance(raw.member, bisim.Member) and raw.member.name == 'erin'
    assert guild.get_member(int(reacting['userId'])) is raw.member


async def test_the_members_intent_chunks(client, fake):
    assert fake.requests_to('GET', f'/guilds/{p.GUILD_ID}/members')
    assert client.get_guild(int(p.GUILD_ID)).chunked


def test_chunking_at_startup_needs_the_members_intent():
    with pytest.raises(ValueError):
        bisim.Client(intents=bisim.Intents.default(), chunk_guilds_at_startup=True)
    client = bisim.Client(intents=bisim.Intents.default())
    assert client._connection._chunk_guilds is False
    client = bisim.Client(intents=bisim.Intents.all(), chunk_guilds_at_startup=False)
    assert client._connection._chunk_guilds is False


async def test_4014_raises_privileged_intents_required_without_reconnecting(fake):
    fake.refuse_code = 4014
    bot = Recorder(api_url=fake.api_url, gateway_url=fake.gateway_url)
    with pytest.raises(bisim.PrivilegedIntentsRequired) as info:
        await asyncio.wait_for(bot.start(TOKEN), 10)
    assert 'bisim.gg/developers' in str(info.value)
    assert fake.passes == 1 and fake.connections == 1
    assert bot.is_closed()
    assert not bot.events('ready')


async def test_4013_raises_connection_closed_without_reconnecting(fake):
    fake.refuse_code = 4013
    bot = Recorder(api_url=fake.api_url, gateway_url=fake.gateway_url)
    with pytest.raises(bisim.ConnectionClosed) as info:
        await asyncio.wait_for(bot.start(TOKEN), 10)
    assert not isinstance(info.value, bisim.PrivilegedIntentsRequired)
    assert info.value.code == 4013
    assert fake.passes == 1 and fake.connections == 1
    assert bot.is_closed()


# -- Messages --------------------------------------------------------------


async def test_message_mentions_and_author_member_from_the_event(lean_client, fake):
    guild = lean_client.get_guild(int(p.GUILD_ID))
    assert guild.get_member(int(p.MEMBER_ID)) is None
    data = {
        **p.message(content=f'hey <@{STRANGER_ID}> and <@&{p.MOD_ROLE_ID}> @here'),
        'guildId': p.GUILD_ID,
        'mentions': [stranger()],
        'mentionRoleIds': [p.MOD_ROLE_ID],
        'mentionEveryone': True,
        'member': {'userId': p.MEMBER_ID, 'nickname': 'Sara', 'roleIds': [p.GUILD_ID, p.MOD_ROLE_ID], 'joinedAt': '2026-07-02T10:00:00.000Z'},
    }
    await fake.send(p.envelope('MESSAGE_CREATE', guildId=p.GUILD_ID, channelId=p.TEXT_ID, message=data))
    await lean_client.wait_event('message')
    (message,) = lean_client.events('message')[0]

    author = message.author
    assert isinstance(author, bisim.Member)
    assert author.id == int(p.MEMBER_ID) and author.nick == 'Sara' and author.name == 'sara'
    assert guild.get_role(int(p.MOD_ROLE_ID)) in author.roles
    assert author.joined_at == datetime.datetime(2026, 7, 2, 10, tzinfo=datetime.timezone.utc)
    # Built for the message, not cached: the bot did not ask for members.
    assert guild.get_member(int(p.MEMBER_ID)) is None

    (mentioned,) = message.mentions
    assert isinstance(mentioned, bisim.User) and mentioned.id == int(STRANGER_ID) and mentioned.name == 'stranger'
    assert [r.id for r in message.role_mentions] == [int(p.MOD_ROLE_ID)]
    assert message.raw_mentions == [int(STRANGER_ID)]
    assert message.raw_role_mentions == [int(p.MOD_ROLE_ID)]
    assert message.mention_everyone


async def test_a_message_without_content_parses(lean_client, fake):
    # Without the message content intent Bisim leaves out content, embeds, attachments, components and poll.
    data = {
        'id': '60000000000000301',
        'channelId': p.TEXT_ID,
        'guildId': p.GUILD_ID,
        'authorId': p.MEMBER_ID,
        'author': p.user_ref(p.MEMBER_ID, 'sara', 'Sara K'),
        'type': 'DEFAULT',
        'createdAt': '2026-11-15T12:00:00.000Z',
        'mentions': [stranger()],
        'member': {'userId': p.MEMBER_ID, 'roleIds': [p.GUILD_ID]},
    }
    await fake.send(p.envelope('MESSAGE_CREATE', guildId=p.GUILD_ID, channelId=p.TEXT_ID, message=data))
    await lean_client.wait_event('message')
    (message,) = lean_client.events('message')[0]
    assert message.content == ''
    assert message.embeds == [] and message.attachments == [] and message.components == []
    assert message.poll is None and message.stickers == []
    assert message.clean_content == '' and message.system_content == ''
    assert not message.mention_everyone and message.role_mentions == []
    assert [u.id for u in message.mentions] == [int(STRANGER_ID)]
    assert message.raw_mentions == [int(STRANGER_ID)]
    assert isinstance(message.author, bisim.Member) and message.author.nick is None


async def test_a_message_read_over_rest_takes_its_mention_ids(state, guild):
    data = p.message(
        content='',
        embeds=[],
        attachments=[],
        components=[],
        mentionIds=[p.OWNER_ID, STRANGER_ID],
        mentionRoleIds=[p.MOD_ROLE_ID],
        mentionEveryone=False,
    )
    message = bisim.Message(state=state, channel=guild.get_channel(int(p.TEXT_ID)), data=data)
    # The owner is cached; the stranger is not known, so only their id is there.
    assert [u.id for u in message.mentions] == [int(p.OWNER_ID)]
    assert message.raw_mentions == [int(p.OWNER_ID), int(STRANGER_ID)]
    assert [r.name for r in message.role_mentions] == ['Moderators']
    assert not message.mention_everyone


# -- Members, bans, invites, audit log, webhooks -----------------------------


async def test_member_remove_takes_the_user_from_the_payload(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    await fake.send(
        p.envelope('GUILD_MEMBER_REMOVE', guildId=p.GUILD_ID, guildMemberRemove={'userId': p.MEMBER_ID, 'user': p.user_ref(p.MEMBER_ID, 'sara', 'Sara K')})
    )
    await client.wait_event('raw_member_remove')
    (member,) = client.events('member_remove')[0]
    assert isinstance(member, bisim.Member) and member.nick == 'Sara'
    raw = client.events('raw_member_remove')[0][0]
    assert raw.user is member and raw.guild_id == guild.id
    assert guild.get_member(int(p.MEMBER_ID)) is None

    # Someone the cache never had: the payload's user is all there is.
    await fake.send(p.envelope('GUILD_MEMBER_REMOVE', guildId=p.GUILD_ID, guildMemberRemove={'userId': STRANGER_ID, 'user': stranger()}))
    await wait_until(lambda: len(client.events('raw_member_remove')) == 2)
    member = client.events('member_remove')[1][0]
    assert isinstance(member, bisim.Member) and member.name == 'stranger' and member.guild is guild
    raw = client.events('raw_member_remove')[1][0]
    assert isinstance(raw.user, bisim.User) and raw.user.name == 'stranger'


async def test_ban_and_unban(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    await fake.send(
        p.envelope('GUILD_BAN_ADD', guildId=p.GUILD_ID, guildBan={'guildId': p.GUILD_ID, 'user': p.user_ref(p.MEMBER_ID, 'sara', 'Sara K')})
    )
    await client.wait_event('member_ban')
    banned_guild, member = client.events('member_ban')[0]
    assert banned_guild is guild
    assert isinstance(member, bisim.Member) and member.id == int(p.MEMBER_ID)

    await fake.send(p.envelope('GUILD_BAN_REMOVE', guildId=p.GUILD_ID, guildBan={'guildId': p.GUILD_ID, 'user': stranger()}))
    await client.wait_event('member_unban')
    unbanned_guild, user = client.events('member_unban')[0]
    assert unbanned_guild is guild
    assert isinstance(user, bisim.User) and user.name == 'stranger'


async def test_invite_create_and_delete(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    invite = {
        'code': 'abc123',
        'guildId': p.GUILD_ID,
        'channelId': p.TEXT_ID,
        'inviter': p.user_ref(p.OWNER_ID, 'owner', 'The Owner'),
        'maxUses': 5,
        'maxAge': 3600,
        'createdAt': '2026-11-15T10:00:00.000Z',
        'expiresAt': '2026-11-15T11:00:00.000Z',
    }
    await fake.send(p.envelope('INVITE_CREATE', guildId=p.GUILD_ID, channelId=p.TEXT_ID, invite=invite))
    await client.wait_event('invite_create')
    (created,) = client.events('invite_create')[0]
    assert isinstance(created, bisim.Invite)
    assert created.code == 'abc123' and created.guild is guild and created.channel.name == 'chat'
    assert created.inviter.name == 'owner'
    assert created.max_uses == 5 and created.uses == 0 and created.max_age == 3600
    assert created.expires_at == datetime.datetime(2026, 11, 15, 11, tzinfo=datetime.timezone.utc)

    await fake.send(p.envelope('INVITE_DELETE', guildId=p.GUILD_ID, channelId=p.TEXT_ID, inviteDelete={'code': 'abc123', 'guildId': p.GUILD_ID, 'channelId': p.TEXT_ID}))
    await client.wait_event('invite_delete')
    (deleted,) = client.events('invite_delete')[0]
    assert deleted.code == 'abc123' and deleted.guild is guild and deleted.channel.id == int(p.TEXT_ID)


async def test_audit_log_entry_create(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    entry = {
        'id': '60000000000000900',
        'guildId': p.GUILD_ID,
        'userId': p.OWNER_ID,
        'action': 'MEMBER_BAN',
        'targetType': 'member',
        'targetId': p.MEMBER_ID,
        'metaJson': json.dumps({'reason': 'spam', 'deleteMessageSeconds': 0}),
        'createdAt': '2026-11-15T10:00:00.000Z',
        'reason': 'spam',
    }
    await fake.send(p.envelope('GUILD_AUDIT_LOG_ENTRY_CREATE', guildId=p.GUILD_ID, auditLogEntry=entry))
    await client.wait_event('audit_log_entry_create')
    (got,) = client.events('audit_log_entry_create')[0]
    assert isinstance(got, bisim.AuditLogEntry)
    assert got.action is bisim.AuditLogAction.ban
    assert got.guild is guild and got.user.id == int(p.OWNER_ID) and got.user_id == int(p.OWNER_ID)
    assert got.target.id == int(p.MEMBER_ID) and got.reason == 'spam'
    assert got.extra == {'reason': 'spam', 'deleteMessageSeconds': 0}

    # The server itself acted (AutoMod): no actor.
    automod = {**entry, 'id': '60000000000000901', 'action': 'AUTOMOD_ACTION', 'metaJson': '', 'reason': ''}
    del automod['userId']
    await fake.send(p.envelope('GUILD_AUDIT_LOG_ENTRY_CREATE', guildId=p.GUILD_ID, auditLogEntry=automod))
    await wait_until(lambda: len(client.events('audit_log_entry_create')) == 2)
    (got,) = client.events('audit_log_entry_create')[1]
    assert got.user is None and got.user_id is None and got.reason is None
    assert got.action is bisim.AuditLogAction.automod_block_message


async def test_webhooks_update(client, fake):
    await fake.send(p.envelope('WEBHOOKS_UPDATE', guildId=p.GUILD_ID, channelId=p.TEXT_ID, webhooksUpdate={'guildId': p.GUILD_ID, 'channelId': p.TEXT_ID}))
    await client.wait_event('webhooks_update')
    (channel,) = client.events('webhooks_update')[0]
    assert isinstance(channel, bisim.TextChannel) and channel.name == 'chat'


# -- AutoMod -----------------------------------------------------------------


AUTOMOD_RULE = {
    'id': '60000000000000950',
    'guildId': p.GUILD_ID,
    'name': 'No links',
    'creatorId': p.OWNER_ID,
    'eventType': 'MESSAGE_SEND',
    'triggerType': 'KEYWORD',
    'keywords': ['http*'],
    'regexPatterns': ['spam+'],
    'allowList': ['bisim.gg'],
    'blockMessage': True,
    'blockReason': 'No links here',
    'alertChannelId': p.PRIVATE_TEXT_ID,
    'timeoutSec': 600,
    'enabled': True,
    'exemptRoles': [p.MOD_ROLE_ID],
    'exemptChannels': [p.VOICE_ID],
}


async def test_automod_rule_events(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    await fake.send(p.envelope('AUTO_MODERATION_RULE_CREATE', guildId=p.GUILD_ID, automodRule=AUTOMOD_RULE))
    await client.wait_event('automod_rule_create')
    (rule,) = client.events('automod_rule_create')[0]
    assert isinstance(rule, bisim.AutoModRule)
    assert rule.id == int(AUTOMOD_RULE['id']) and rule.guild is guild and rule.name == 'No links'
    assert rule.creator.id == int(p.OWNER_ID)
    assert rule.event_type is bisim.AutoModRuleEventType.message_send
    assert rule.trigger.type is bisim.AutoModRuleTriggerType.keyword
    assert rule.trigger.keyword_filter == ['http*'] and rule.trigger.regex_patterns == ['spam+']
    assert rule.trigger.allow_list == ['bisim.gg']
    assert rule.enabled
    assert [r.name for r in rule.exempt_roles] == ['Moderators']
    assert [c.name for c in rule.exempt_channels] == ['Lounge']
    assert rule.is_exempt(guild.get_role(int(p.MOD_ROLE_ID)))
    kinds = {a.type: a for a in rule.actions}
    assert kinds[bisim.AutoModRuleActionType.block_message].custom_message == 'No links here'
    assert kinds[bisim.AutoModRuleActionType.send_alert_message].channel_id == int(p.PRIVATE_TEXT_ID)
    assert kinds[bisim.AutoModRuleActionType.timeout].duration == datetime.timedelta(minutes=10)

    preset = {
        'id': '60000000000000951',
        'guildId': p.GUILD_ID,
        'name': 'Words',
        'triggerType': 'KEYWORD_PRESET',
        'presets': ['PROFANITY', 'SLURS'],
        'blockMessage': True,
        'enabled': True,
    }
    await fake.send(p.envelope('AUTO_MODERATION_RULE_UPDATE', guildId=p.GUILD_ID, automodRule=preset))
    await client.wait_event('automod_rule_update')
    (rule,) = client.events('automod_rule_update')[0]
    assert rule.trigger.type is bisim.AutoModRuleTriggerType.keyword_preset
    assert rule.trigger.presets.profanity and rule.trigger.presets.slurs and not rule.trigger.presets.sexual_content
    assert rule.trigger.presets.to_array() == [1, 3]
    assert rule.creator_id is None and rule.exempt_role_ids == set()

    mention = {'id': '60000000000000952', 'guildId': p.GUILD_ID, 'name': 'Pings', 'triggerType': 'MENTION_SPAM', 'mentionLimit': 5}
    await fake.send(p.envelope('AUTO_MODERATION_RULE_DELETE', guildId=p.GUILD_ID, automodRule=mention))
    await client.wait_event('automod_rule_delete')
    (rule,) = client.events('automod_rule_delete')[0]
    assert rule.trigger.type is bisim.AutoModRuleTriggerType.mention_spam and rule.trigger.mention_limit == 5
    assert not rule.enabled and rule.actions == []


async def test_automod_profile_rule_reads_as_member_profile(client, fake):
    rule = {'id': '60000000000000953', 'guildId': p.GUILD_ID, 'name': 'Names', 'eventType': 'MEMBER_UPDATE',
            'triggerType': 'KEYWORD', 'keywords': ['admin'], 'enabled': True}
    await fake.send(p.envelope('AUTO_MODERATION_RULE_CREATE', guildId=p.GUILD_ID, automodRule=rule))
    await client.wait_event('automod_rule_create')
    (made,) = client.events('automod_rule_create')[-1]
    assert made.event_type is bisim.AutoModRuleEventType.member_update
    assert made.trigger.type is bisim.AutoModRuleTriggerType.member_profile
    assert made.trigger.keyword_filter == ['admin']
    action = {'guildId': p.GUILD_ID, 'actionType': 1, 'ruleId': rule['id'], 'ruleTriggerType': 'KEYWORD', 'userId': p.OWNER_ID, 'matchedKeyword': 'admin'}
    await fake.send(p.envelope('AUTO_MODERATION_ACTION_EXECUTION', guildId=p.GUILD_ID, automodAction=action))
    await client.wait_event('automod_action')
    (execution,) = client.events('automod_action')[-1]
    assert execution.rule_trigger_type is bisim.AutoModRuleTriggerType.member_profile


async def test_automod_action(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    actions = [
        {'actionType': 1, 'customMessage': 'No links here'},
        {'actionType': 2, 'alertChannelId': p.PRIVATE_TEXT_ID, 'alertSystemMessageId': '60000000000000960'},
        {'actionType': 3, 'durationSeconds': 600},
    ]
    for extra in actions:
        payload = {
            'guildId': p.GUILD_ID,
            'ruleId': AUTOMOD_RULE['id'],
            'ruleTriggerType': 'KEYWORD',
            'userId': p.MEMBER_ID,
            'channelId': p.TEXT_ID,
            'content': 'see http://spam.example',
            'matchedKeyword': 'http*',
            'matchedContent': 'http',
            **extra,
        }
        await fake.send(p.envelope('AUTO_MODERATION_ACTION_EXECUTION', guildId=p.GUILD_ID, channelId=p.TEXT_ID, automodAction=payload))
    await wait_until(lambda: len(client.events('automod_action')) == 3)
    block, alert, timeout = (args[0] for args in client.events('automod_action'))
    assert isinstance(block, bisim.AutoModAction)
    assert block.action.type is bisim.AutoModRuleActionType.block_message and block.action.custom_message == 'No links here'
    assert block.rule_id == int(AUTOMOD_RULE['id']) and block.rule_trigger_type is bisim.AutoModRuleTriggerType.keyword
    assert block.guild is guild and block.channel.name == 'chat' and block.member.id == int(p.MEMBER_ID)
    assert block.message_id is None
    assert block.content == 'see http://spam.example' and block.matched_keyword == 'http*' and block.matched_content == 'http'
    assert alert.action.type is bisim.AutoModRuleActionType.send_alert_message
    assert alert.action.channel_id == int(p.PRIVATE_TEXT_ID) and alert.alert_system_message_id == 60000000000000960
    assert timeout.action.type is bisim.AutoModRuleActionType.timeout and timeout.action.duration == datetime.timedelta(minutes=10)

    # Without the message content intent the text is left out.
    lean = {'guildId': p.GUILD_ID, 'ruleId': AUTOMOD_RULE['id'], 'ruleTriggerType': 'SPAM', 'userId': p.MEMBER_ID, 'actionType': 1}
    await fake.send(p.envelope('AUTO_MODERATION_ACTION_EXECUTION', guildId=p.GUILD_ID, automodAction=lean))
    await wait_until(lambda: len(client.events('automod_action')) == 4)
    (execution,) = client.events('automod_action')[3]
    assert execution.content == '' and execution.matched_content is None and execution.matched_keyword is None
    assert execution.channel_id is None and execution.channel is None
    assert execution.rule_trigger_type is bisim.AutoModRuleTriggerType.spam


async def test_automod_rule_edit_and_fetch_rule(state, guild, http):
    rule = bisim.AutoModRule(data=AUTOMOD_RULE, guild=guild, state=state)
    edited = dict(AUTOMOD_RULE, name='Fewer links', alertChannelId=None, timeoutSec=None)
    path = f'/guilds/{p.GUILD_ID}/automod/rules/{AUTOMOD_RULE["id"]}'
    http.respond('PATCH', path, edited)
    http.respond('GET', path, AUTOMOD_RULE)
    new = await rule.edit(
        name='Fewer links',
        actions=[bisim.AutoModRuleAction(custom_message='Nope')],
        trigger=bisim.AutoModTrigger(keyword_filter=['www*']),
        exempt_roles=[],
        reason='tidy',
    )
    call = http.last('PATCH', path)
    assert call['json'] == {
        'blockMessage': True,
        'blockReason': 'Nope',
        'alertChannelId': '',
        'timeoutSec': 0,
        'name': 'Fewer links',
        'keywords': ['www*'],
        'regexPatterns': [],
        'allowList': [],
        'exemptRoles': [],
    }
    assert call['reason'] == 'tidy'
    assert new.name == 'Fewer links' and [a.type for a in new.actions] == [bisim.AutoModRuleActionType.block_message]

    execution = bisim.AutoModAction(
        data={'guildId': p.GUILD_ID, 'ruleId': AUTOMOD_RULE['id'], 'userId': p.MEMBER_ID, 'actionType': 1}, state=state
    )
    fetched = await execution.fetch_rule()
    assert fetched.id == rule.id and fetched.guild is guild


# -- Channels: the real events, and the GUILD_RESYNC that follows them --------


async def resynced(fake: FakeBisim, client: Recorder, count: int) -> None:
    """Waits until the client has subscribed ``count`` times (each resync ends with op 4)."""
    await wait_until(lambda: len(fake.frames_with_op(4)) >= count)
    await asyncio.sleep(0.05)


async def test_channel_create_is_reported_once_with_the_resync_after_it(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    new = p.channel('60000000000000209', 'announcements', 'GUILD_TEXT', 3)
    fake.guild_details[p.GUILD_ID]['channels'].append(copy.deepcopy(new))
    event = {k: new[k] for k in ('id', 'guildId', 'name', 'type', 'position')}

    await fake.send(p.envelope('CHANNEL_CREATE', guildId=p.GUILD_ID, channelId=new['id'], channelUpdate=event))
    await fake.send(p.envelope('GUILD_RESYNC', guildId=p.GUILD_ID, guildResync={}))
    await client.wait_event('guild_channel_create')
    await resynced(fake, client, 2)

    created = client.events('guild_channel_create')
    assert len(created) == 1
    channel = created[0][0]
    assert isinstance(channel, bisim.TextChannel) and channel.name == 'announcements'
    assert guild.get_channel(int(new['id'])) is channel
    # The refetch filled the channel in without reporting it as changed.
    assert not client.events('guild_channel_update')
    assert channel._my_permissions is not None

    # The next resync diffs it as usual.
    fake.guild_details[p.GUILD_ID]['channels'][-1]['name'] = 'news'
    await fake.send(p.envelope('GUILD_RESYNC', guildId=p.GUILD_ID, guildResync={}))
    await client.wait_event('guild_channel_update')
    before, after = client.events('guild_channel_update')[0]
    assert before.name == 'announcements' and after is channel and after.name == 'news'


async def test_channel_create_after_the_resync_is_not_reported_twice(client, fake):
    new = p.channel('60000000000000210', 'later', 'GUILD_VOICE', 4)
    fake.guild_details[p.GUILD_ID]['channels'].append(copy.deepcopy(new))
    await fake.send(p.envelope('GUILD_RESYNC', guildId=p.GUILD_ID, guildResync={}))
    await client.wait_event('guild_channel_create')
    await resynced(fake, client, 2)
    event = {k: new[k] for k in ('id', 'guildId', 'name', 'type', 'position')}
    await fake.send(p.envelope('CHANNEL_CREATE', guildId=p.GUILD_ID, channelId=new['id'], channelUpdate=event))
    await asyncio.sleep(0.1)
    created = client.events('guild_channel_create')
    assert len(created) == 1 and isinstance(created[0][0], bisim.VoiceChannel)


async def test_channel_delete_is_reported_once_with_the_resync_after_it(client, fake):
    guild = client.get_guild(int(p.GUILD_ID))
    fake.guild_details[p.GUILD_ID]['channels'] = [c for c in fake.guild_details[p.GUILD_ID]['channels'] if c['id'] != p.PRIVATE_TEXT_ID]
    event = {'id': p.PRIVATE_TEXT_ID, 'guildId': p.GUILD_ID, 'name': 'staff', 'type': 'GUILD_TEXT', 'position': 2}
    await fake.send(p.envelope('CHANNEL_DELETE', guildId=p.GUILD_ID, channelId=p.PRIVATE_TEXT_ID, channelUpdate=event))
    await fake.send(p.envelope('GUILD_RESYNC', guildId=p.GUILD_ID, guildResync={}))
    await client.wait_event('guild_channel_delete')
    await resynced(fake, client, 2)
    deleted = client.events('guild_channel_delete')
    assert len(deleted) == 1 and deleted[0][0].name == 'staff'
    assert guild.get_channel(int(p.PRIVATE_TEXT_ID)) is None

"""The bot batch of 2026-11-15: files and polls in interaction answers, allowed mentions, message flags,
select default values, clearing one emoji's reactions, bulk bans, renaming emoji and stickers, a webhook's
own messages and picture, the bot's own picture, a voice channel's status, rate limit buckets and the
soundboard events."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any, Dict, List

import pytest
from aioresponses import CallbackResult, aioresponses

import bisim
from bisim import ui
from bisim.http import HTTPClient
from bisim.message import Message

from . import payloads as p
from .conftest import events

API = 'https://api.test/api'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16
INTERACTION_BASE = f'/interactions/{p.INTERACTION_ID}/{p.INTERACTION_TOKEN}'
WEBHOOK_ID = '60000000000000950'
WEBHOOK_TOKEN = 'secret-token-value-123456'


@pytest.fixture
def uploads(http, monkeypatch) -> List[Dict[str, Any]]:
    """Records the PUTs to presigned upload addresses instead of sending them."""
    puts: List[Dict[str, Any]] = []

    async def fake_upload(url: str, data: bytes, content_type: str) -> None:
        puts.append({'url': url, 'data': data, 'content_type': content_type})

    monkeypatch.setattr(http, 'upload_to_url', fake_upload)
    return puts


def presign(*ids: str) -> Any:
    def answer(route: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        files = kwargs['json']['files']
        return {
            'attachments': [
                {'id': ids[i], 'uploadUrl': f'https://s3.test/up/{ids[i]}', 'uploadFilename': f'uploads/{ids[i]}/{f["fileName"]}'}
                for i, f in enumerate(files)
            ]
        }

    return answer


def answer_message(**overrides: Any) -> Dict[str, Any]:
    data = p.message(id='60000000000000777', authorId=p.BOT_ID, author=p.user_ref(p.BOT_ID, 'helper_bot', 'Helper', bot=True))
    data.update(overrides)
    return data


def make_interaction(state: Any, kind: int = 2, data: Any = None, **extra: Any) -> bisim.Interaction:
    payload = p.interaction(kind, data or {'id': '60000000000000801', 'name': 'ping', 'type': 1}, **extra)
    return bisim.Interaction(data=payload, state=state)


# ---------------------------------------------------------------------------
# Allowed mentions and flags
# ---------------------------------------------------------------------------


async def test_send_carries_allowed_mentions_merged_with_the_clients(guild, http, state):
    channel = guild.get_channel(int(p.TEXT_ID))
    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', p.message())

    await channel.send('hi @everyone')
    assert 'allowedMentions' not in http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']

    state.allowed_mentions = bisim.AllowedMentions(everyone=False)
    await channel.send('hi @everyone')
    assert http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']['allowedMentions'] == {
        'parse': ['users', 'roles'],
        'repliedUser': True,
    }

    owner = guild.get_member(int(p.OWNER_ID))
    await channel.send(f'hi {owner.mention}', allowed_mentions=bisim.AllowedMentions(users=[owner]), mention_author=False)
    body = http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']
    assert body['allowedMentions'] == {'parse': ['roles'], 'users': [p.OWNER_ID], 'repliedUser': False}

    state.allowed_mentions = None
    await channel.send('quiet', allowed_mentions=bisim.AllowedMentions.none())
    assert http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']['allowedMentions'] == {'parse': []}


async def test_silent_and_suppress_embeds_flags(guild, http, state):
    channel = guild.get_channel(int(p.TEXT_ID))
    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', p.message())
    await channel.send('see https://example.com', silent=True, suppress_embeds=True)
    assert http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']['flags'] == 4 | 4096

    message = Message(state=state, channel=channel, data=p.message(flags=4 | 4096))
    assert message.flags.suppress_embeds and message.flags.silent

    path = f'/channels/{p.TEXT_ID}/messages/{p.MESSAGE_ID}'
    http.respond('PATCH', path, p.message())
    await message.edit(suppress=True)
    assert http.last('PATCH', path)['json'] == {'flags': 4}
    await message.edit(suppress=False)
    assert http.last('PATCH', path)['json'] == {'flags': 0}
    await message.edit(content='only text')
    assert http.last('PATCH', path)['json'] == {'content': 'only text'}


# ---------------------------------------------------------------------------
# Files: a bot's own message, interaction answers, attachment:// pictures
# ---------------------------------------------------------------------------


async def test_message_edit_keeps_and_adds_files(guild, http, state, uploads):
    channel = guild.get_channel(int(p.TEXT_ID))
    data = p.message(authorId=p.BOT_ID, author=p.user_ref(p.BOT_ID, 'helper_bot', bot=True))
    data['attachments'] = [
        {'id': '60000000000000601', 'fileName': 'old.png', 'sizeBytes': 3, 'url': 'https://cdn.test/a/old.png', 'contentType': 'image/png'},
        {'id': '60000000000000602', 'fileName': 'gone.txt', 'sizeBytes': 3, 'url': 'https://cdn.test/a/gone.txt'},
    ]
    message = Message(state=state, channel=channel, data=data)
    http.respond('POST', f'/channels/{p.TEXT_ID}/attachments', presign('900'))
    path = f'/channels/{p.TEXT_ID}/messages/{p.MESSAGE_ID}'
    http.respond('PATCH', path, data)

    embed = bisim.Embed(title='Chart').set_image(url='attachment://new.png').set_thumbnail(url='attachment://old.png')
    await message.edit(embed=embed, attachments=[message.attachments[0], bisim.File(io.BytesIO(PNG), filename='new.png')])
    body = http.last('PATCH', path)['json']
    assert body['attachments'] == [
        {'id': '60000000000000601'},
        {'id': '900', 'uploadFilename': 'uploads/900/new.png', 'fileName': 'new.png', 'contentType': 'image/png', 'sizeBytes': len(PNG)},
    ]
    assert body['embeds'][0]['image'] == {'url': 'attachment://new.png'}
    assert body['embeds'][0]['thumbnail'] == {'url': 'attachment://old.png'}
    assert uploads[0]['data'] == PNG and uploads[0]['content_type'] == 'image/png'

    # Without ``attachments`` the message keeps its files, so a picture may still name one of them.
    await message.edit(embed=bisim.Embed(title='x').set_image(url='attachment://gone.txt'))
    body = http.last('PATCH', path)['json']
    assert 'attachments' not in body and body['embeds'][0]['image'] == {'url': 'attachment://gone.txt'}

    await message.remove_attachments(message.attachments[1])
    assert http.last('PATCH', path)['json'] == {'attachments': [{'id': '60000000000000601'}]}


async def test_attachment_picture_without_its_file_is_left_out(guild, http, monkeypatch, caplog):
    monkeypatch.setattr(bisim.embeds, '_warned_picture', False)
    channel = guild.get_channel(int(p.TEXT_ID))
    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', p.message())
    with caplog.at_level(logging.WARNING, logger='bisim.embeds'):
        await channel.send(embed=bisim.Embed(title='x').set_image(url='attachment://nowhere.png'))
    assert 'image' not in http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']['embeds'][0]
    assert any('were left out' in r.getMessage() for r in caplog.records)


async def test_spoiler_file_name_maps_to_the_name_it_is_sent_under(guild, http, uploads):
    channel = guild.get_channel(int(p.TEXT_ID))
    http.respond('POST', f'/channels/{p.TEXT_ID}/attachments', presign('901'))
    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', p.message())
    file = bisim.File(io.BytesIO(PNG), filename='SPOILER_secret.png')
    await channel.send(file=file, embed=bisim.Embed(title='x').set_image(url=file.uri))
    body = http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']
    assert body['embeds'][0]['image'] == {'url': 'attachment://secret.png'}
    assert body['attachments'][0]['spoiler'] is True and body['attachments'][0]['fileName'] == 'secret.png'


async def test_interaction_answer_with_a_file_and_its_picture(guild, http, state, uploads):
    interaction = make_interaction(state)
    http.respond('POST', f'{INTERACTION_BASE}/attachments', presign('910'))
    http.respond('POST', f'{INTERACTION_BASE}/callback', answer_message())
    file = bisim.File(io.BytesIO(PNG), filename='chart.png')
    embed = bisim.Embed(title='Chart').set_image(url='attachment://chart.png')

    await interaction.response.send_message('here', file=file, embed=embed, silent=True)

    presigned = http.last('POST', f'{INTERACTION_BASE}/attachments')
    assert presigned['auth'] is False
    assert presigned['json'] == {'files': [{'fileName': 'chart.png', 'contentType': 'image/png', 'sizeBytes': len(PNG)}]}
    body = http.last('POST', f'{INTERACTION_BASE}/callback')['json']
    assert body['type'] == 4
    assert body['data']['attachments'][0]['id'] == '910'
    assert body['data']['embeds'][0]['image'] == {'url': 'attachment://chart.png'}
    assert body['data']['flags'] == 4096
    assert 'nonce' not in body['data']
    assert uploads[0]['url'] == 'https://s3.test/up/910'


async def test_defer_then_edit_original_with_a_file(guild, http, state, uploads):
    interaction = make_interaction(state)
    http.respond('POST', f'{INTERACTION_BASE}/callback', None)
    http.respond('POST', f'{INTERACTION_BASE}/attachments', presign('920'))
    http.respond('PATCH', f'{INTERACTION_BASE}/messages/@original', answer_message())
    await interaction.response.defer(thinking=True)
    await interaction.edit_original_response(
        content='done',
        attachments=[bisim.File(io.BytesIO(b'report'), filename='report.txt')],
        allowed_mentions=bisim.AllowedMentions(everyone=False, users=False, roles=False),
    )
    body = http.last('PATCH', f'{INTERACTION_BASE}/messages/@original')['json']
    assert body['content'] == 'done'
    assert [a['id'] for a in body['attachments']] == ['920']
    assert body['allowedMentions'] == {'parse': [], 'repliedUser': True}

    with pytest.raises(bisim.NotSupported):
        await interaction.edit_original_response(poll=bisim.Poll('Q?', duration=datetime_hours(1)))


def datetime_hours(hours: int) -> Any:
    import datetime

    return datetime.timedelta(hours=hours)


async def test_followup_with_a_poll_and_a_file(guild, http, state, uploads):
    interaction = make_interaction(state)
    interaction.response._response_type = bisim.InteractionResponseType.channel_message
    http.respond('POST', f'{INTERACTION_BASE}/followup', answer_message())
    poll = bisim.Poll('Lunch?', duration=datetime_hours(2))
    poll.add_answer(text='Rice').add_answer(text='Bread')
    await interaction.followup.send(poll=poll)
    body = http.last('POST', f'{INTERACTION_BASE}/followup')['json']
    assert body['poll']['question'] == 'Lunch?' and [a['text'] for a in body['poll']['answers']] == ['Rice', 'Bread']

    http.respond('POST', f'{INTERACTION_BASE}/attachments', presign('930'))
    await interaction.followup.send('log', file=bisim.File(io.BytesIO(b'x'), filename='log.txt'), ephemeral=True)
    body = http.last('POST', f'{INTERACTION_BASE}/followup')['json']
    assert body['flags'] == 64 and body['attachments'][0]['id'] == '930'


async def test_component_update_with_files(guild, http, state, uploads):
    message = answer_message()
    message['attachments'] = [{'id': '60000000000000611', 'fileName': 'a.png', 'sizeBytes': 1, 'url': 'https://cdn.test/a.png'}]
    interaction = make_interaction(state, 3, {'customId': 'x', 'componentType': 2}, message=message)
    http.respond('POST', f'{INTERACTION_BASE}/callback', None)
    await interaction.response.edit_message(attachments=[], suppress_embeds=True)
    body = http.last('POST', f'{INTERACTION_BASE}/callback')['json']
    assert body == {'type': 7, 'data': {'flags': 4, 'attachments': []}}


async def test_interaction_poll_answer(guild, http, state):
    interaction = make_interaction(state)
    http.respond('POST', f'{INTERACTION_BASE}/callback', answer_message())
    poll = bisim.Poll('Ready?', duration=datetime_hours(1))
    poll.add_answer(text='Yes').add_answer(text='No')
    await interaction.response.send_message(poll=poll)
    body = http.last('POST', f'{INTERACTION_BASE}/callback')['json']
    assert body['type'] == 4 and body['data']['poll']['question'] == 'Ready?'


# ---------------------------------------------------------------------------
# Select default values
# ---------------------------------------------------------------------------


def test_select_default_values_round_trip(guild):
    owner = guild.get_member(int(p.OWNER_ID))
    role = guild.get_role(int(p.MOD_ROLE_ID))
    channel = guild.get_channel(int(p.TEXT_ID))

    users = ui.UserSelect(custom_id='u', default_values=[owner], max_values=2)
    roles = ui.RoleSelect(custom_id='r', default_values=[bisim.Object(id=role.id)])
    mixed = ui.MentionableSelect(custom_id='m', default_values=[owner, role], max_values=2)
    channels = ui.ChannelSelect(custom_id='c', default_values=[channel])
    assert users.to_component_dict()['defaultValues'] == [{'id': p.OWNER_ID, 'type': 'user'}]
    assert roles.to_component_dict()['defaultValues'] == [{'id': p.MOD_ROLE_ID, 'type': 'role'}]
    assert mixed.to_component_dict()['defaultValues'] == [{'id': p.OWNER_ID, 'type': 'user'}, {'id': p.MOD_ROLE_ID, 'type': 'role'}]
    assert channels.to_component_dict()['defaultValues'] == [{'id': p.TEXT_ID, 'type': 'channel'}]

    with pytest.raises(ValueError):
        ui.MentionableSelect(default_values=[bisim.Object(id=1)])
    with pytest.raises(TypeError):
        ui.RoleSelect(default_values=[owner])

    menu = bisim.SelectMenu(users.to_component_dict())
    assert menu.default_values == [bisim.SelectDefaultValue(id=int(p.OWNER_ID), type=bisim.SelectDefaultValueType.user)]
    rebuilt = ui.UserSelect.from_component(menu)
    assert rebuilt.default_values == menu.default_values
    users.default_values = [bisim.SelectDefaultValue.from_user(owner), bisim.Object(id=7)]
    assert [v.id for v in users.default_values] == [int(p.OWNER_ID), 7]


# ---------------------------------------------------------------------------
# Reactions of one emoji
# ---------------------------------------------------------------------------


async def test_clear_reaction_and_its_event(guild, http, state, dispatched):
    channel = guild.get_channel(int(p.TEXT_ID))
    data = p.message()
    data['reactions'] = [{'emoji': '👍', 'count': 2, 'me': False}, {'emoji': '🎉', 'count': 1, 'me': True}]
    message = Message(state=state, channel=channel, data=data)
    state._messages.append(message)

    await message.clear_reaction('👍')
    assert http.last('DELETE', f'/channels/{p.TEXT_ID}/messages/{p.MESSAGE_ID}/reactions/%F0%9F%91%8D/all')
    await message.reactions[1].clear()
    assert http.last('DELETE', f'/channels/{p.TEXT_ID}/messages/{p.MESSAGE_ID}/reactions/%F0%9F%8E%89/all')

    state.parse_message_reaction_remove_emoji(
        {
            'type': 'MESSAGE_REACTION_REMOVE_EMOJI',
            'guildId': p.GUILD_ID,
            'channelId': p.TEXT_ID,
            'reactionRemoveEmoji': {'messageId': p.MESSAGE_ID, 'channelId': p.TEXT_ID, 'guildId': p.GUILD_ID, 'emoji': '👍'},
        }
    )
    raw = events(dispatched, 'raw_reaction_clear_emoji')[0][0]
    assert raw.message_id == int(p.MESSAGE_ID) and raw.emoji.name == '👍'
    (reaction,) = events(dispatched, 'reaction_clear_emoji')[0]
    assert str(reaction.emoji) == '👍' and reaction.count == 2
    assert [str(r.emoji) for r in message.reactions] == ['🎉']


# ---------------------------------------------------------------------------
# Bulk ban, emoji and stickers
# ---------------------------------------------------------------------------


async def test_bulk_ban(guild, http):
    http.respond('POST', f'/guilds/{p.GUILD_ID}/bulk-ban', {'bannedUsers': [p.MEMBER_ID], 'failedUsers': [p.OWNER_ID]})
    result = await guild.bulk_ban([bisim.Object(id=int(p.MEMBER_ID)), bisim.Object(id=int(p.OWNER_ID))], reason='raid', delete_message_seconds=60)
    call = http.last('POST', f'/guilds/{p.GUILD_ID}/bulk-ban')
    assert call['json'] == {'userIds': [p.MEMBER_ID, p.OWNER_ID], 'deleteMessageSeconds': 60, 'reason': 'raid'}
    assert call['reason'] == 'raid'
    assert [o.id for o in result.banned] == [int(p.MEMBER_ID)] and [o.id for o in result.failed] == [int(p.OWNER_ID)]
    with pytest.raises(ValueError):
        await guild.bulk_ban([bisim.Object(id=i) for i in range(201)])


async def test_emoji_and_sticker_rename_and_their_events(guild, http, state, dispatched):
    emoji_row = {'id': '60000000000000501', 'guildId': p.GUILD_ID, 'name': 'blob', 'objectKey': 'emojis/blob.png', 'creatorId': p.OWNER_ID}
    state.parse_guild_emoji_create({'type': 'GUILD_EMOJI_CREATE', 'guildId': p.GUILD_ID, 'emoji': emoji_row})
    emoji = guild.emojis[-1]
    http.respond('PATCH', f'/guilds/{p.GUILD_ID}/emojis/{emoji.id}', {**emoji_row, 'name': 'party_blob'})
    edited = await emoji.edit(name='party_blob', reason='nicer')
    call = http.last('PATCH', f'/guilds/{p.GUILD_ID}/emojis/{emoji.id}')
    assert call['json'] == {'name': 'party_blob'} and call['reason'] == 'nicer'
    assert edited.name == 'party_blob'
    with pytest.raises(bisim.NotSupported):
        await emoji.edit(roles=[])

    state.parse_guild_emoji_update({'type': 'GUILD_EMOJI_UPDATE', 'guildId': p.GUILD_ID, 'emoji': {**emoji_row, 'name': 'party_blob'}})
    _, before, after = events(dispatched, 'guild_emojis_update')[-1]
    assert [e.name for e in before] == ['blob'] and [e.name for e in after] == ['party_blob']

    sticker_row = {'id': '60000000000000502', 'guildId': p.GUILD_ID, 'name': 'cat', 'objectKey': 'stickers/cat.png'}
    state.parse_guild_sticker_create({'type': 'GUILD_STICKER_CREATE', 'guildId': p.GUILD_ID, 'sticker': sticker_row})
    sticker = guild.stickers[-1]
    http.respond('PATCH', f'/guilds/{p.GUILD_ID}/stickers/{sticker.id}', {**sticker_row, 'name': 'happy_cat'})
    renamed = await sticker.edit(name='happy_cat')
    assert http.last('PATCH', f'/guilds/{p.GUILD_ID}/stickers/{sticker.id}')['json'] == {'name': 'happy_cat'}
    assert renamed.name == 'happy_cat'
    with pytest.raises(bisim.NotSupported):
        await sticker.edit(description='x')

    state.parse_guild_sticker_update({'type': 'GUILD_STICKER_UPDATE', 'guildId': p.GUILD_ID, 'sticker': {**sticker_row, 'name': 'happy_cat'}})
    _, before, after = events(dispatched, 'guild_stickers_update')[-1]
    assert [s.name for s in before] == ['cat'] and [s.name for s in after] == ['happy_cat']


# ---------------------------------------------------------------------------
# Webhooks: files, their own messages, their picture
# ---------------------------------------------------------------------------


def webhook_row(**extra: Any) -> Dict[str, Any]:
    row = {'id': WEBHOOK_ID, 'guildId': p.GUILD_ID, 'channelId': p.TEXT_ID, 'name': 'CI', 'avatarKey': None, 'token': WEBHOOK_TOKEN, 'createdAt': '2026-11-01T00:00:00Z'}
    row.update(extra)
    return row


async def test_webhook_send_with_a_file_and_its_messages(state, guild, http, uploads):
    hook = bisim.Webhook.from_state(webhook_row(), state=state)
    base = f'/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}'
    http.respond('POST', f'{base}/attachments', presign('940'))
    sent = p.message(id='60000000000000960', webhookId=WEBHOOK_ID, author={'id': WEBHOOK_ID, 'username': 'CI', 'avatarKey': None})
    http.respond('POST', base, sent)

    message = await hook.send(
        'build ok',
        file=bisim.File(io.BytesIO(PNG), filename='badge.png'),
        embed=bisim.Embed(title='Build').set_thumbnail(url='attachment://badge.png'),
        allowed_mentions=bisim.AllowedMentions.none(),
        suppress_embeds=False,
        silent=True,
        wait=True,
    )
    call = http.last('POST', base)
    assert call['auth'] is False and call['params'] == {'wait': 'true'}
    assert call['json']['attachments'][0]['id'] == '940'
    assert call['json']['embeds'][0]['thumbnail'] == {'url': 'attachment://badge.png'}
    assert call['json']['flags'] == 4096 and call['json']['allowedMentions'] == {'parse': []}
    assert 'nonce' not in call['json']
    assert http.last('POST', f'{base}/attachments')['auth'] is False
    assert isinstance(message, bisim.WebhookMessage) and message.id == 60000000000000960

    path = f'{base}/messages/{message.id}'
    http.respond('GET', path, sent)
    http.respond('PATCH', path, {**sent, 'content': 'edited'})
    http.respond('DELETE', path, {'ok': True})
    fetched = await hook.fetch_message(message.id)
    assert fetched.content == sent['content'] and http.last('GET', path)['auth'] is False
    edited = await message.edit(content='edited', attachments=[])
    assert http.last('PATCH', path)['json'] == {'content': 'edited', 'attachments': []}
    assert edited.content == 'edited'
    await message.edit(suppress=True)
    assert http.last('PATCH', path)['json'] == {'flags': 4}
    await hook.delete_message(message.id)
    assert http.last('DELETE', path)['auth'] is False

    with pytest.raises(bisim.NotSupported):
        await hook.send('x', view=ui.View())


async def test_webhook_picture(state, guild, http):
    hook = bisim.Webhook.from_state(webhook_row(), state=state)
    http.respond('POST', f'/webhooks/{WEBHOOK_ID}/avatar', webhook_row(avatarKey='icons/webhook/1/2.webp'))
    await hook.edit(avatar=PNG, reason='logo')
    call = http.last('POST', f'/webhooks/{WEBHOOK_ID}/avatar')
    assert call['form'][0]['name'] == 'file' and call['form'][0]['value'] == PNG
    assert call['form'][0]['content_type'] == 'image/png' and call['reason'] == 'logo'
    assert hook.avatar is not None and hook.avatar.url.endswith('icons/webhook/1/2.webp')

    http.respond('DELETE', f'/webhooks/{WEBHOOK_ID}/avatar', webhook_row())
    await hook.edit(avatar=None)
    assert hook.avatar is None

    channel = guild.get_channel(int(p.TEXT_ID))
    http.respond('POST', f'/channels/{p.TEXT_ID}/webhooks', webhook_row())
    made = await channel.create_webhook(name='CI', avatar=PNG)
    assert http.last('POST', f'/webhooks/{WEBHOOK_ID}/avatar')
    assert made.id == int(WEBHOOK_ID)


def test_sync_webhook_send_with_a_file(monkeypatch):
    seen: List[Any] = []

    class Answer:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def read(self) -> bytes:
            return self.body

        def __enter__(self) -> 'Answer':
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    def fake_urlopen(request: Any, timeout: float = 0) -> Answer:
        seen.append((request.get_method(), request.full_url, request.data))
        if request.full_url.endswith('/attachments'):
            return Answer(json.dumps({'attachments': [{'id': '950', 'uploadUrl': 'https://s3.test/up/950', 'uploadFilename': 'uploads/950/a.txt'}]}).encode())
        if request.get_method() == 'PUT':
            return Answer(b'')
        return Answer(json.dumps(p.message(id='60000000000000961')).encode())

    monkeypatch.setattr('bisim.webhook.sync.urllib.request.urlopen', fake_urlopen)
    hook = bisim.SyncWebhook.from_url(f'https://api.test/api/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}')
    sent = hook.send('hi', file=bisim.File(io.BytesIO(b'abc'), filename='a.txt'), silent=True, wait=True)
    assert [s[0] for s in seen] == ['POST', 'PUT', 'POST']
    body = json.loads(seen[2][2])
    assert body['attachments'][0]['id'] == '950' and body['flags'] == 4096
    assert sent is not None and sent.id == 60000000000000961


# ---------------------------------------------------------------------------
# The bot's own profile and a voice channel's status
# ---------------------------------------------------------------------------


async def test_client_user_avatar_and_banner(state, http):
    http.respond('POST', '/users/@me/avatar', {'id': p.BOT_ID})
    http.respond('DELETE', '/users/@me/banner', {'id': p.BOT_ID})
    http.respond('GET', '/auth/me', {**p.ME, 'avatarKey': 'avatars/bot.webp'})
    await state.user.edit(avatar=PNG, banner=None)
    form = http.last('POST', '/users/@me/avatar')['form']
    assert form[0]['name'] == 'file' and form[0]['content_type'] == 'image/png'
    assert http.last('DELETE', '/users/@me/banner')
    assert state.user.avatar is not None
    with pytest.raises(ValueError):
        await state.user.edit(avatar=b'not a picture')
    with pytest.raises(bisim.NotSupported):
        await state.user.edit(bio='hi')


async def test_voice_channel_status(guild, http):
    voice = guild.get_channel(int(p.VOICE_ID))
    http.respond('PUT', f'/channels/{p.VOICE_ID}/voice-status', {'channelId': p.VOICE_ID, 'status': 'Now playing'})
    await voice.edit(status='Now playing')
    assert http.last('PUT', f'/channels/{p.VOICE_ID}/voice-status')['json'] == {'status': 'Now playing'}
    assert voice.status == 'Now playing'
    http.respond('PUT', f'/channels/{p.VOICE_ID}/voice-status', {'channelId': p.VOICE_ID, 'status': ''})
    await voice.edit(status=None)
    assert http.last('PUT', f'/channels/{p.VOICE_ID}/voice-status')['json'] == {'status': ''}
    assert voice.status is None


# ---------------------------------------------------------------------------
# Soundboard events
# ---------------------------------------------------------------------------


def sound_row(**extra: Any) -> Dict[str, Any]:
    row = {'id': '60000000000000550', 'guildId': p.GUILD_ID, 'name': 'airhorn', 'objectKey': 'sounds/airhorn.ogg', 'emojiName': '📯', 'volume': 80, 'durationMs': 1200, 'creatorId': p.OWNER_ID}
    row.update(extra)
    return row


def test_soundboard_events(state, guild, dispatched):
    state.parse_guild_sound_create({'type': 'GUILD_SOUND_CREATE', 'guildId': p.GUILD_ID, 'sound': sound_row()})
    (created,) = events(dispatched, 'soundboard_sound_create')[0]
    assert created.name == 'airhorn' and created.volume == 0.8 and guild.get_soundboard_sound(created.id) is created

    state.parse_guild_sound_update({'type': 'GUILD_SOUND_UPDATE', 'guildId': p.GUILD_ID, 'sound': sound_row(name='horn', volume=50)})
    before, after = events(dispatched, 'soundboard_sound_update')[0]
    assert before.name == 'airhorn' and after.name == 'horn' and after is created and after.volume == 0.5

    state.parse_soundboard_play(
        {'type': 'SOUNDBOARD_PLAY', 'guildId': p.GUILD_ID, 'channelId': p.VOICE_ID, 'soundboardPlay': {'userId': p.MEMBER_ID, 'sound': sound_row(volume=100)}}
    )
    (effect,) = events(dispatched, 'voice_channel_effect')[0]
    assert effect.channel.id == int(p.VOICE_ID) and effect.user.id == int(p.MEMBER_ID)
    assert effect.is_sound() and effect.sound.id == created.id and effect.sound.volume == 1.0
    assert effect.emoji.name == '📯' and effect.animation is None

    state.parse_guild_sound_delete({'type': 'GUILD_SOUND_DELETE', 'guildId': p.GUILD_ID, 'soundDelete': {'soundId': created.id}})
    (deleted,) = events(dispatched, 'soundboard_sound_delete')[0]
    assert deleted is created and guild.get_soundboard_sound(created.id) is None

    # A sound the library never saw still reports its update.
    state.parse_guild_sound_update({'type': 'GUILD_SOUND_UPDATE', 'guildId': p.GUILD_ID, 'sound': sound_row(id='60000000000000551', name='new')})
    before, after = events(dispatched, 'soundboard_sound_update')[1]
    assert before.name == after.name == 'new'


# ---------------------------------------------------------------------------
# Rate limit buckets
# ---------------------------------------------------------------------------


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


def limited(payload: Any, *, remaining: int, bucket: str = 'b1', limit: int = 5, reset_after: float = 4) -> CallbackResult:
    return CallbackResult(
        payload=payload,
        headers={
            'X-RateLimit-Limit': str(limit),
            'X-RateLimit-Remaining': str(remaining),
            'X-RateLimit-Reset-After': str(reset_after),
            'X-RateLimit-Reset': '1900000000',
            'X-RateLimit-Bucket': bucket,
        },
    )


async def test_a_used_up_bucket_waits_for_its_reset(client, sleeps):
    with aioresponses() as m:
        m.get(f'{API}/guilds', callback=lambda url, **kw: limited([], remaining=0))
        m.get(f'{API}/guilds', callback=lambda url, **kw: limited([{'id': '1'}], remaining=4))
        assert await client.get_guilds() == []
        assert sleeps == [4.0]
        assert await client.get_guilds() == [{'id': '1'}]
    assert client._bucket_hashes['GET /guilds'] == 'b1'


async def test_routes_with_one_bucket_name_share_a_queue(client, sleeps):
    with aioresponses() as m:
        m.get(f'{API}/guilds', callback=lambda url, **kw: limited([], remaining=3))
        m.get(f'{API}/users/2', callback=lambda url, **kw: limited({'id': '2'}, remaining=2))
        await client.get_guilds()
        await client.get_user(2)
    assert client._bucket_hashes == {'GET /guilds': 'b1', 'GET /users/{user_id}': 'b1'}
    assert list(client._buckets) == ['b1']
    assert client._buckets['b1'].remaining == 2
    assert sleeps == []


async def test_requests_go_out_together_while_the_bucket_has_room(client):
    started: List[str] = []
    gate = asyncio.Event()

    async def slow(url, **kwargs):
        started.append(str(url))
        await gate.wait()
        return limited({'ok': True}, remaining=8, limit=10)

    with aioresponses() as m:
        m.get(f'{API}/guilds', callback=lambda url, **kw: limited([], remaining=9, limit=10))
        await client.get_guilds()
        m.get(f'{API}/guilds', callback=slow, repeat=True)
        first = asyncio.ensure_future(client.get_guilds())
        second = asyncio.ensure_future(client.get_guilds())
        await asyncio.sleep(0.05)
        assert len(started) == 2
        gate.set()
        await asyncio.gather(first, second)


async def test_global_429_header_pauses_every_request(client, sleeps):
    with aioresponses() as m:
        m.get(
            f'{API}/guilds',
            status=429,
            payload={'message': 'Too many requests. Try again later.', 'code': 'RATE_LIMITED', 'retryAfter': 6, 'global': False},
            headers={'Retry-After': '6', 'X-RateLimit-Global': 'true', 'X-RateLimit-Scope': 'user'},
        )
        m.get(f'{API}/guilds', payload=[])
        assert await client.get_guilds() == []
    assert sleeps == [6.0]
    assert client._global_over.is_set()


async def test_audit_log_reason_header(client):
    with aioresponses() as m:
        m.post(f'{API}/guilds/5/bulk-ban', payload={'bannedUsers': ['7'], 'failedUsers': []})
        await client.bulk_ban(5, [7], 0, reason='spam bots ölü')
        request = next(iter(m.requests.values()))[0]
    assert request.kwargs['headers']['X-Audit-Log-Reason'] == 'spam bots %C3%B6l%C3%BC'


# ---------------------------------------------------------------------------
# AutoMod REST
# ---------------------------------------------------------------------------


def rule_row(**extra: Any) -> Dict[str, Any]:
    row = {
        'id': '60000000000000880',
        'guildId': p.GUILD_ID,
        'name': 'No spam words',
        'enabled': True,
        'eventType': 'MESSAGE_SEND',
        'triggerType': 'KEYWORD',
        'keywords': ['spam*'],
        'regexPatterns': [],
        'presets': [],
        'allowList': ['spammer'],
        'mentionLimit': None,
        'blockMessage': True,
        'blockReason': 'Not here',
        'alertChannelId': p.TEXT_ID,
        'timeoutSec': 60,
        'exemptRoles': [p.MOD_ROLE_ID],
        'exemptChannels': [],
        'creatorId': p.OWNER_ID,
        'createdAt': '2026-11-15T00:00:00.000Z',
        'updatedAt': '2026-11-15T00:00:00.000Z',
    }
    row.update(extra)
    return row


async def test_automod_rules_rest(guild, http):
    http.respond('GET', f'/guilds/{p.GUILD_ID}/automod/rules', [rule_row()])
    http.respond('GET', f'/guilds/{p.GUILD_ID}/automod/rules/60000000000000880', rule_row())
    (rule,) = await guild.fetch_automod_rules()
    assert rule.name == 'No spam words' and rule.trigger.type is bisim.AutoModRuleTriggerType.keyword
    assert {a.type for a in rule.actions} == {
        bisim.AutoModRuleActionType.block_message,
        bisim.AutoModRuleActionType.send_alert_message,
        bisim.AutoModRuleActionType.timeout,
    }
    assert (await guild.fetch_automod_rule(rule.id)).id == rule.id

    http.respond('POST', f'/guilds/{p.GUILD_ID}/automod/rules', rule_row())
    created = await guild.create_automod_rule(
        name='No spam words',
        event_type=bisim.AutoModRuleEventType.message_send,
        trigger=bisim.AutoModTrigger(keyword_filter=['spam*'], allow_list=['spammer']),
        actions=[
            bisim.AutoModRuleAction(custom_message='Not here'),
            bisim.AutoModRuleAction(channel_id=int(p.TEXT_ID)),
            bisim.AutoModRuleAction(duration=datetime_hours(1)),
        ],
        enabled=True,
        exempt_roles=[guild.get_role(int(p.MOD_ROLE_ID))],
        reason='cleanup',
    )
    call = http.last('POST', f'/guilds/{p.GUILD_ID}/automod/rules')
    assert call['reason'] == 'cleanup'
    assert call['json'] == {
        'name': 'No spam words',
        'triggerType': 'KEYWORD',
        'eventType': 'MESSAGE_SEND',
        'enabled': True,
        'keywords': ['spam*'],
        'regexPatterns': [],
        'allowList': ['spammer'],
        'blockMessage': True,
        'blockReason': 'Not here',
        'alertChannelId': p.TEXT_ID,
        'timeoutSec': 3600,
        'exemptRoles': [p.MOD_ROLE_ID],
    }
    assert created.id == rule.id

    await guild.create_automod_rule(
        name='Names',
        event_type=bisim.AutoModRuleEventType.message_send,
        trigger=bisim.AutoModTrigger(type=bisim.AutoModRuleTriggerType.member_profile, keyword_filter=['admin']),
        actions=[bisim.AutoModRuleAction()],
    )
    call = http.last('POST', f'/guilds/{p.GUILD_ID}/automod/rules')
    assert call['json']['triggerType'] == 'KEYWORD' and call['json']['eventType'] == 'MEMBER_UPDATE'

    with pytest.raises(bisim.NotSupported):
        await guild.create_automod_rule(
            name='Links',
            event_type=bisim.AutoModRuleEventType.message_send,
            trigger=bisim.AutoModTrigger(type=bisim.AutoModRuleTriggerType.harmful_link),
            actions=[bisim.AutoModRuleAction()],
        )

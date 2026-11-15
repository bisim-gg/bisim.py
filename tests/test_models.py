"""Models built from recorded Bisim payloads."""

from __future__ import annotations

import datetime

import pytest

import bisim
from bisim.message import Message

from . import payloads as p
from .conftest import events


def test_guild_from_detail(guild):
    assert guild.id == int(p.GUILD_ID)
    assert guild.name == 'Test Server'
    assert guild.description == 'A server for tests'
    assert guild.verification_level is bisim.VerificationLevel.low
    assert guild.owner_id == int(p.OWNER_ID)
    assert guild.icon.url == 'https://cdn.test/icons/server.webp'
    assert guild.system_channel.name == 'chat'
    assert guild.default_role.is_default()
    assert [r.name for r in guild.roles] == ['@everyone', 'Helper', 'Moderators']
    assert [c.name for c in guild.categories] == ['General']
    category = guild.categories[0]
    assert [c.name for c in category.channels] == ['chat', 'Lounge']
    assert guild.get_channel(int(p.TEXT_ID)).category is category
    assert guild.get_channel(int(p.TEXT_ID)).permissions_synced
    assert guild.chunked and guild.member_count == 3
    assert guild.get_member_named('Sara').id == int(p.MEMBER_ID)
    assert guild.get_member_named('sara').id == int(p.MEMBER_ID)
    assert guild.created_at.year == 2026


def test_member_attributes(guild):
    sara = guild.get_member(int(p.MEMBER_ID))
    assert sara.name == 'sara'
    assert sara.global_name == 'Sara K'
    assert sara.display_name == 'Sara'
    assert sara.mention == f'<@{p.MEMBER_ID}>'
    assert [r.name for r in sara.roles] == ['@everyone', 'Moderators']
    assert sara.top_role.name == 'Moderators'
    assert sara.colour.value == 0x3498DB
    assert sara.guild_permissions.manage_messages
    assert sara.guild_permissions.kick_members
    assert not sara.guild_permissions.ban_members
    assert sara.display_avatar.url == 'https://cdn.test/avatars/sara.webp'
    assert sara.joined_at == datetime.datetime(2026, 7, 2, 10, tzinfo=datetime.timezone.utc)
    assert not sara.is_timed_out()
    owner = guild.get_member(int(p.OWNER_ID))
    assert owner.guild_permissions == bisim.Permissions.all()


def test_bot_permissions_come_from_the_server(guild):
    me = guild.me
    text = guild.get_channel(int(p.TEXT_ID))
    assert text.permissions_for(me).value == int(text._my_permissions)
    assert me.guild_permissions.manage_messages


def test_permissions_for_other_members_use_overwrites(guild):
    staff = guild.get_channel(int(p.PRIVATE_TEXT_ID))
    staff._overwrites = [
        bisim.abc._Overwrites({'targetId': p.GUILD_ID, 'type': 0, 'allow': '0', 'deny': str(1 << 10)}),
        bisim.abc._Overwrites({'targetId': p.MOD_ROLE_ID, 'type': 0, 'allow': str(1 << 10), 'deny': '0'}),
    ]
    staff._overwrites_loaded = True
    sara = guild.get_member(int(p.MEMBER_ID))
    owner_role_less = guild.get_member(int(p.OWNER_ID))
    newbie = bisim.Member(data={'userId': '60000000000000009', 'roleIds': [], 'user': p.user_ref('60000000000000009', 'x')}, guild=guild, state=guild._state)
    assert staff.permissions_for(sara).read_messages
    assert not staff.permissions_for(newbie).read_messages
    assert not staff.permissions_for(newbie).send_messages
    owner_perms = staff.permissions_for(owner_role_less)
    assert owner_perms.administrator and owner_perms.manage_guild
    assert not owner_perms.connect  # text channels never carry voice permissions
    overwrites = staff.overwrites
    assert overwrites[guild.default_role].read_messages is False
    assert staff.overwrites_for(guild.get_role(int(p.MOD_ROLE_ID))).view_channel is True


def test_message_parsing(guild, state):
    channel = guild.get_channel(int(p.TEXT_ID))
    message = Message(state=state, channel=channel, data=p.message())
    assert message.id == int(p.MESSAGE_ID)
    assert message.type is bisim.MessageType.reply
    assert message.guild is guild
    assert isinstance(message.author, bisim.Member) and message.author.nick == 'Sara'
    assert message.mention_everyone
    assert [m.id for m in message.mentions] == [int(p.BOT_ID)]
    assert message.raw_mentions == [int(p.BOT_ID)]
    assert [r.name for r in message.role_mentions] == ['Moderators']
    assert [c.name for c in message.channel_mentions] == ['chat']
    assert message.clean_content.startswith('hi @Helper and @Moderators in #chat @​everyone')
    assert message.jump_url == f'https://bisim.gg/channels/{p.GUILD_ID}/{p.TEXT_ID}/{p.MESSAGE_ID}'
    assert message.created_at == datetime.datetime(2026, 11, 1, 12, tzinfo=datetime.timezone.utc)
    assert message.edited_at is None

    attachment = message.attachments[0]
    assert attachment.filename == 'cat.png' and attachment.size == 2048 and attachment.width == 64
    assert attachment.content_type == 'image/png' and not attachment.is_spoiler()

    embed = message.embeds[0]
    assert embed.title == 'Status' and embed.colour.value == 0x2ECC71
    assert embed.author.name == 'Monitor' and embed.footer.text == 'v1'
    assert embed.fields[0].name == 'Uptime' and embed.fields[0].inline

    thumbs, wave = message.reactions
    assert thumbs.emoji == '👍' and thumbs.count == 2 and not thumbs.me
    assert isinstance(wave.emoji, bisim.PartialEmoji) and wave.emoji.id == 60000000000000500 and wave.me

    assert message.reference.message_id == 60000000000000299
    assert message.reference.resolved.author.id == int(p.OWNER_ID)

    row = message.components[0]
    assert isinstance(row, bisim.ActionRow)
    yes, docs = row.children
    assert yes.custom_id == 'vote:yes' and yes.style is bisim.ButtonStyle.primary
    assert docs.url == 'https://docs.bisim.gg' and docs.style is bisim.ButtonStyle.link


def test_interaction_reply_message_type(guild, state):
    channel = guild.get_channel(int(p.TEXT_ID))
    data = p.message(type='DEFAULT', interaction={'name': 'ping', 'userId': p.MEMBER_ID, 'username': 'sara'}, referencedMessageId=None, referencedMessage=None)
    message = Message(state=state, channel=channel, data=data)
    assert message.type is bisim.MessageType.chat_input_command
    assert message.interaction.name == 'ping'
    assert message.interaction.user.id == int(p.MEMBER_ID)


def test_dm_channel_and_user(state):
    channel = state.add_dm_channel(
        {'id': p.DM_ID, 'type': 'DM', 'participants': [p.user_ref(p.BOT_ID, 'helper_bot', bot=True), p.user_ref(p.MEMBER_ID, 'sara')], 'createdAt': '2026-11-01T00:00:00Z'}
    )
    assert channel.type is bisim.ChannelType.private
    assert channel.recipient.name == 'sara'
    assert state.get_channel(int(p.DM_ID)) is channel
    assert channel.recipient.dm_channel is channel
    assert channel.permissions_for(None).send_messages


async def test_member_actions_use_bisim_routes(guild, http):
    sara = guild.get_member(int(p.MEMBER_ID))
    role = guild.get_role(int(p.MOD_ROLE_ID))
    await sara.add_roles(role, reason='promoted')
    assert http.last('PUT', f'/guilds/{p.GUILD_ID}/members/{p.MEMBER_ID}/roles/{p.MOD_ROLE_ID}')['reason'] == 'promoted'

    await sara.remove_roles(role)
    assert http.last('DELETE', f'/guilds/{p.GUILD_ID}/members/{p.MEMBER_ID}/roles/{p.MOD_ROLE_ID}')

    await sara.edit(nick='Sar', roles=[role])
    patch = http.last('PATCH', f'/guilds/{p.GUILD_ID}/members/{p.MEMBER_ID}')
    assert patch['json'] == {'nickname': 'Sar', 'roleIds': [p.MOD_ROLE_ID]}

    await sara.timeout(datetime.timedelta(minutes=10), reason='spam')
    timeout = http.last('PUT', f'/guilds/{p.GUILD_ID}/members/{p.MEMBER_ID}/timeout')
    assert timeout['json']['reason'] == 'spam'
    assert timeout['json']['until'].endswith('Z')

    await sara.kick(reason='bye')
    assert http.last('DELETE', f'/guilds/{p.GUILD_ID}/members/{p.MEMBER_ID}')['json'] == {'reason': 'bye'}

    await sara.ban(delete_message_days=2)
    assert http.last('PUT', f'/guilds/{p.GUILD_ID}/bans/{p.MEMBER_ID}')['json'] == {'deleteMessageSeconds': 172800}

    with pytest.raises(bisim.ClientException):
        await sara.edit(mute=True)


async def test_guild_create_channel_and_role(guild, http):
    http.respond('POST', f'/guilds/{p.GUILD_ID}/channels', p.channel('60000000000000250', 'new-chat', 'GUILD_TEXT', 5))
    channel = await guild.create_text_channel(
        'new-chat',
        topic='hello',
        category=guild.categories[0],
        overwrites={guild.default_role: bisim.PermissionOverwrite(read_messages=False)},
    )
    body = http.last('POST', f'/guilds/{p.GUILD_ID}/channels')['json']
    assert body == {
        'name': 'new-chat',
        'type': 'GUILD_TEXT',
        'permissionOverwrites': [{'id': p.GUILD_ID, 'allow': '0', 'deny': str(1 << 10), 'type': 0}],
        'parentId': p.CATEGORY_ID,
        'topic': 'hello',
    }
    assert guild.get_channel(channel.id) is channel

    http.respond('POST', f'/guilds/{p.GUILD_ID}/roles', p.role('60000000000000150', 'Helpers', 1, '8', color=0xFF0000))
    role = await guild.create_role(name='Helpers', permissions=bisim.Permissions(administrator=True), colour=bisim.Colour.red(), hoist=True)
    assert http.last('POST', f'/guilds/{p.GUILD_ID}/roles')['json'] == {'permissions': '8', 'color': 0xE74C3C, 'hoist': True, 'name': 'Helpers'}
    assert role.permissions.administrator

    with pytest.raises(bisim.NotSupported):
        await guild.create_voice_channel('music', bitrate=96000)
    with pytest.raises(bisim.NotSupported):
        await guild.create_forum('ideas')


async def test_send_with_embed_view_reply_poll(guild, http, state):
    channel = guild.get_channel(int(p.TEXT_ID))

    def answer(route, kwargs):
        return p.message(id='60000000000000999', type='DEFAULT', content=kwargs['json'].get('content', ''), referencedMessageId=None, referencedMessage=None, author=p.user_ref(p.BOT_ID, 'helper_bot', bot=True))

    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', answer)
    original = Message(state=state, channel=channel, data=p.message())
    view = bisim.ui.View(timeout=None)
    view.add_item(bisim.ui.Button(label='Go', custom_id='go'))
    poll = bisim.Poll(question='Lunch?', duration=datetime.timedelta(hours=2)).add_answer(text='Pizza', emoji='🍕').add_answer(text='Salad')
    sent = await original.reply('hello', embed=bisim.Embed(title='T', colour=5), view=view, silent=True, poll=poll)
    body = http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']
    assert body['content'] == 'hello'
    assert body['referencedMessageId'] == p.MESSAGE_ID
    assert body['embeds'] == [{'title': 'T', 'color': 5}]
    assert body['components'] == [{'type': 1, 'components': [{'type': 2, 'style': 2, 'disabled': False, 'label': 'Go', 'customId': 'go'}]}]
    assert body['poll'] == {'question': 'Lunch?', 'answers': [{'text': 'Pizza', 'emoji': '🍕'}, {'text': 'Salad'}], 'multiselect': False, 'durationHours': 2}
    assert body['flags'] == 4096
    assert body['nonce']
    assert sent.id == 60000000000000999
    assert state._view_store.is_message_tracked(sent.id)


async def test_history_pages_newest_first(guild, http, state):
    channel = guild.get_channel(int(p.TEXT_ID))
    pages = [
        [p.message(id=str(500 - i), referencedMessageId=None, referencedMessage=None) for i in range(100)],
        [p.message(id=str(400 - i), referencedMessageId=None, referencedMessage=None) for i in range(20)],
    ]

    def answer(route, kwargs):
        return pages.pop(0)

    http.respond('GET', f'/channels/{p.TEXT_ID}/messages', answer)
    messages = [m async for m in channel.history(limit=None)]
    assert len(messages) == 120
    assert messages[0].id == 500 and messages[-1].id == 381
    calls = [c for c in http.calls if c['path'] == f'/channels/{p.TEXT_ID}/messages']
    assert calls[0]['params'] == {'limit': 100}
    assert calls[1]['params'] == {'limit': 100, 'before': 401}


async def test_reactions_and_pins_routes(guild, http, state):
    channel = guild.get_channel(int(p.TEXT_ID))
    message = Message(state=state, channel=channel, data=p.message())
    await message.add_reaction('👍')
    assert http.last('PUT', f'/channels/{p.TEXT_ID}/messages/{p.MESSAGE_ID}/reactions/%F0%9F%91%8D')
    await message.add_reaction(bisim.PartialEmoji(name='wave', id=60000000000000500))
    assert http.last('PUT', f'/channels/{p.TEXT_ID}/messages/{p.MESSAGE_ID}/reactions/%3C%3Awave%3A60000000000000500%3E')
    await message.remove_reaction('👍', guild.get_member(int(p.OWNER_ID)))
    assert http.last('DELETE', f'/channels/{p.TEXT_ID}/messages/{p.MESSAGE_ID}/reactions/%F0%9F%91%8D/{p.OWNER_ID}')
    await message.clear_reactions()
    assert http.last('DELETE', f'/channels/{p.TEXT_ID}/messages/{p.MESSAGE_ID}/reactions')
    await message.pin(reason='important')
    assert http.last('PUT', f'/channels/{p.TEXT_ID}/pins/{p.MESSAGE_ID}')['reason'] == 'important'
    with pytest.raises(bisim.NotSupported):
        await message.create_thread(name='x')


def test_invite_and_webhook_models(state, guild):
    invite = bisim.Invite.from_incomplete(
        state=state,
        data={'code': 'abcDEF', 'guildId': p.GUILD_ID, 'channelId': p.TEXT_ID, 'inviterId': p.MEMBER_ID, 'maxUses': None, 'uses': 3, 'maxAgeSec': 86400, 'expiresAt': None, 'createdAt': '2026-11-01T00:00:00Z'},
    )
    assert invite.url == 'https://bisim.gg/abcDEF'
    assert invite.guild is guild and invite.channel.name == 'chat'
    assert invite.max_age == 86400 and invite.uses == 3
    resolved = bisim.Invite(state=state, data={'code': 'xyz', 'guild': {'id': '60000000000000900', 'name': 'Other', 'iconKey': None, 'description': None, 'splashKey': None, 'createdAt': '2026-11-01T00:00:00Z'}, 'inviter': p.user_ref(p.OWNER_ID, 'owner'), 'memberCount': 10, 'onlineCount': 4})
    assert isinstance(resolved.guild, bisim.PartialInviteGuild) and resolved.guild.name == 'Other'
    assert resolved.approximate_member_count == 10 and resolved.inviter.name == 'owner'

    hook = bisim.Webhook.from_state({'id': '60000000000000950', 'guildId': p.GUILD_ID, 'channelId': p.TEXT_ID, 'name': 'CI', 'avatarKey': None, 'token': 'secret-token-value-123456', 'createdAt': '2026-11-01T00:00:00Z'}, state=state)
    assert hook.url == 'https://api.test/api/webhooks/60000000000000950/secret-token-value-123456'
    assert hook.channel.name == 'chat'


def test_user_profile_and_assets(state):
    user = state.store_user({'id': '60000000000000042', 'username': 'neo', 'displayName': None, 'avatarKey': None})
    assert user.display_name == 'neo'
    assert user.avatar is None
    assert user.display_avatar.url.startswith('https://cdn.test/avatars/default/v1/m')
    assert str(user) == 'neo'
    assert user.created_at.year >= 2026
    sized = state.store_user({'id': '60000000000000043', 'username': 'x', 'avatarKey': 'avatars/x.webp'}).avatar.with_size(64)
    assert sized.url == 'https://cdn.test/avatars/x.webp?width=64&height=64'
    with pytest.raises(bisim.NotSupported):
        sized.with_format('png')


def test_raw_events_from_state(state, guild, dispatched):
    state.parse_message_delete_bulk({'type': 'MESSAGE_DELETE_BULK', 'guildId': p.GUILD_ID, 'channelId': p.TEXT_ID, 'messageDeleteBulk': {'ids': ['1', '2'], 'channelId': p.TEXT_ID, 'guildId': p.GUILD_ID}})
    raw = events(dispatched, 'raw_bulk_message_delete')[0][0]
    assert raw.message_ids == {1, 2} and raw.channel_id == int(p.TEXT_ID)

    state.parse_message_reaction_remove_all({'type': 'MESSAGE_REACTION_REMOVE_ALL', 'reactionRemoveAll': {'messageId': '5', 'channelId': p.TEXT_ID, 'guildId': p.GUILD_ID}})
    assert events(dispatched, 'raw_reaction_clear')[0][0].message_id == 5

    state.parse_guild_update({'type': 'GUILD_UPDATE', 'guildId': p.GUILD_ID, 'guildUpdate': {'id': p.GUILD_ID, 'name': 'Renamed', 'ownerId': p.OWNER_ID, 'verificationLevel': 2, 'afkTimeout': 600}})
    before, after = events(dispatched, 'guild_update')[0]
    assert before.name == 'Test Server' and after.name == 'Renamed'
    assert after.verification_level is bisim.VerificationLevel.medium
    assert after.system_channel is None

    state.parse_channel_update({'type': 'CHANNEL_UPDATE', 'guildId': p.GUILD_ID, 'channelId': p.TEXT_ID, 'channelUpdate': {'id': p.TEXT_ID, 'name': 'general-chat', 'slowmodeSec': 5}})
    before, after = events(dispatched, 'guild_channel_update')[0]
    assert before.name == 'chat' and after.name == 'general-chat' and after.slowmode_delay == 5 and after.topic is None

    state.parse_guild_member_remove({'type': 'GUILD_MEMBER_REMOVE', 'guildId': p.GUILD_ID, 'guildMemberRemove': {'userId': p.BOT_ID}})
    assert events(dispatched, 'guild_remove')[0][0] is guild
    assert state._get_guild(int(p.GUILD_ID)) is None


PICTURES = {
    'author': 'https://example.com/author.png',
    'footer': 'http://example.com/footer.png',
    'image': 'https://example.com/banner.png',
    'thumbnail': 'https://example.com/thumb.png',
}


def test_embed_sends_its_pictures():
    embed = (
        bisim.Embed(title='Pictures')
        .set_author(name='Sara', url='https://example.com/sara', icon_url=PICTURES['author'])
        .set_footer(text='Bisim', icon_url=PICTURES['footer'])
        .set_image(url=PICTURES['image'])
        .set_thumbnail(url=PICTURES['thumbnail'])
    )
    assert embed._to_bisim() == {
        'title': 'Pictures',
        'author': {'name': 'Sara', 'url': 'https://example.com/sara', 'iconUrl': PICTURES['author']},
        'footer': {'text': 'Bisim', 'iconUrl': PICTURES['footer']},
        'image': {'url': PICTURES['image']},
        'thumbnail': {'url': PICTURES['thumbnail']},
    }


def test_embed_leaves_out_a_picture_that_is_not_a_web_link(caplog, monkeypatch):
    monkeypatch.setattr(bisim.embeds, '_warned_picture', False)
    embed = (
        bisim.Embed(title='Chart')
        .set_image(url='attachment://chart.png')
        .set_thumbnail(url='https://example.com/' + 'x' * 2048)
        .set_footer(text='Footer', icon_url='data:image/png;base64,AAAA')
    )
    with caplog.at_level('WARNING', logger='bisim.embeds'):
        assert embed._to_bisim() == {'title': 'Chart', 'footer': {'text': 'Footer'}}
        embed._to_bisim()
    assert embed.image.url == 'attachment://chart.png'
    assert len([r for r in caplog.records if 'were left out' in r.getMessage()]) == 1


def test_embed_reads_the_pictures_bisim_sends_back():
    embed = bisim.Embed.from_dict(
        {
            'type': 'rich',
            'title': 'Back',
            'authorName': 'Bot',
            'authorIconUrl': PICTURES['author'],
            'footerText': 'Footer',
            'footerIconUrl': PICTURES['footer'],
            'imageUrl': PICTURES['image'],
            'thumbnailUrl': PICTURES['thumbnail'],
            'fields': [],
        }
    )
    assert embed.image.url == PICTURES['image']
    assert embed.thumbnail.url == PICTURES['thumbnail'] and embed.thumbnail.proxy_url == PICTURES['thumbnail']
    assert embed.author.icon_url == PICTURES['author']
    assert embed.footer.icon_url == PICTURES['footer']
    assert embed.copy()._to_bisim() == {
        'title': 'Back',
        'author': {'name': 'Bot', 'iconUrl': PICTURES['author']},
        'footer': {'text': 'Footer', 'iconUrl': PICTURES['footer']},
        'image': {'url': PICTURES['image']},
        'thumbnail': {'url': PICTURES['thumbnail']},
    }


async def test_send_carries_embed_pictures(guild, http):
    channel = guild.get_channel(int(p.TEXT_ID))
    http.respond('POST', f'/channels/{p.TEXT_ID}/messages', lambda route, kwargs: p.message(id='60000000000000998', type='DEFAULT'))
    await channel.send(embed=bisim.Embed(title='T').set_image(url=PICTURES['image']).set_thumbnail(url=PICTURES['thumbnail']))
    body = http.last('POST', f'/channels/{p.TEXT_ID}/messages')['json']
    assert body['embeds'] == [{'title': 'T', 'image': {'url': PICTURES['image']}, 'thumbnail': {'url': PICTURES['thumbnail']}}]

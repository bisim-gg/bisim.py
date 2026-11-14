"""Recorded and hand-written Bisim responses used by the tests."""

from __future__ import annotations

import copy
from typing import Any, Dict

BOT_ID = '60000000000000001'
OWNER_ID = '60000000000000002'
MEMBER_ID = '60000000000000003'
GUILD_ID = '60000000000000100'
EVERYONE_ROLE_ID = GUILD_ID
MOD_ROLE_ID = '60000000000000101'
BOT_ROLE_ID = '60000000000000102'
CATEGORY_ID = '60000000000000200'
TEXT_ID = '60000000000000201'
VOICE_ID = '60000000000000202'
PRIVATE_TEXT_ID = '60000000000000203'
MESSAGE_ID = '60000000000000300'
DM_ID = '60000000000000400'

ME = {
    'id': BOT_ID,
    'phoneE164': 'bot-' + BOT_ID,
    'username': 'helper_bot',
    'displayName': 'Helper',
    'avatarKey': None,
    'locale': 'en',
    'hasPassword': False,
    'totpEnabled': False,
    'bot': True,
}

GUILD_ROW = {
    'id': GUILD_ID,
    'name': 'Test Server',
    'iconKey': 'icons/server.webp',
    'description': 'A server for tests',
    'verificationLevel': 1,
    'ownerId': OWNER_ID,
    'systemChannelId': TEXT_ID,
    'afkChannelId': None,
    'afkTimeout': 300,
    'createdAt': '2026-07-01T10:00:00.000Z',
}


def role(role_id: str, name: str, position: int, permissions: str, **extra: Any) -> Dict[str, Any]:
    data = {
        'id': role_id,
        'guildId': GUILD_ID,
        'name': name,
        'color': extra.pop('color', 0),
        'position': position,
        'permissions': permissions,
        'hoist': False,
        'mentionable': False,
        'isEveryone': role_id == GUILD_ID,
        'createdAt': '2026-07-01T10:00:00.000Z',
    }
    data.update(extra)
    return data


def channel(channel_id: str, name: str, kind: str, position: int, **extra: Any) -> Dict[str, Any]:
    data = {
        'id': channel_id,
        'guildId': GUILD_ID,
        'type': kind,
        'name': name,
        'topic': None,
        'parentId': None,
        'permissionsSynced': False,
        'position': position,
        'nsfw': False,
        'slowmodeSec': 0,
        'lastMessageId': None,
        'createdAt': '2026-07-01T10:00:00.000Z',
        # What the bot may do here, as Bisim computes it: @everyone plus its Helper role (manage_messages).
        'permissions': str((1 << 10) | (1 << 11) | (1 << 16) | (1 << 6) | (1 << 13)),
        'isPrivate': False,
    }
    data.update(extra)
    return data


# view_channel | send_messages | read_message_history | add_reactions | use_application_commands
EVERYONE_PERMS = str((1 << 10) | (1 << 11) | (1 << 16) | (1 << 6) | (1 << 31))
# manage_messages | kick_members | moderate_members
MOD_PERMS = str((1 << 13) | (1 << 1) | (1 << 40))

GUILD_DETAIL = {
    **GUILD_ROW,
    'roles': [
        role(EVERYONE_ROLE_ID, '@everyone', 0, EVERYONE_PERMS),
        role(MOD_ROLE_ID, 'Moderators', 2, MOD_PERMS, color=0x3498DB, hoist=True),
        role(BOT_ROLE_ID, 'Helper', 1, str(1 << 13)),
    ],
    'channels': [
        channel(CATEGORY_ID, 'General', 'GUILD_CATEGORY', 0),
        channel(TEXT_ID, 'chat', 'GUILD_TEXT', 0, parentId=CATEGORY_ID, topic='Talk here', permissionsSynced=True),
        channel(VOICE_ID, 'Lounge', 'GUILD_VOICE', 1, parentId=CATEGORY_ID),
        channel(PRIVATE_TEXT_ID, 'staff', 'GUILD_TEXT', 2, isPrivate=True),
    ],
    'permissions': str(int(EVERYONE_PERMS) | (1 << 13)),
    'myRoleIds': [GUILD_ID, BOT_ROLE_ID],
}


def user_ref(user_id: str, username: str, display: str = None, bot: bool = False) -> Dict[str, Any]:
    return {'id': user_id, 'username': username, 'displayName': display, 'avatarKey': f'avatars/{username}.webp', 'bot': bot}


MEMBERS = [
    {
        'guildId': GUILD_ID,
        'userId': OWNER_ID,
        'nickname': None,
        'roleIds': [GUILD_ID],
        'joinedAt': '2026-07-01T10:00:00.000Z',
        'timeoutUntil': None,
        'user': user_ref(OWNER_ID, 'owner', 'The Owner'),
    },
    {
        'guildId': GUILD_ID,
        'userId': MEMBER_ID,
        'nickname': 'Sara',
        'roleIds': [GUILD_ID, MOD_ROLE_ID],
        'joinedAt': '2026-07-02T10:00:00.000Z',
        'timeoutUntil': None,
        'user': user_ref(MEMBER_ID, 'sara', 'Sara K'),
    },
    {
        'guildId': GUILD_ID,
        'userId': BOT_ID,
        'nickname': None,
        'roleIds': [GUILD_ID, BOT_ROLE_ID],
        'joinedAt': '2026-07-03T10:00:00.000Z',
        'timeoutUntil': None,
        'user': user_ref(BOT_ID, 'helper_bot', 'Helper', bot=True),
    },
]

MESSAGE = {
    'id': MESSAGE_ID,
    'channelId': TEXT_ID,
    'authorId': MEMBER_ID,
    'type': 'REPLY',
    'content': 'hi <@' + BOT_ID + '> and <@&' + MOD_ROLE_ID + '> in <#' + TEXT_ID + '> @everyone <:wave:60000000000000500>',
    'referencedMessageId': '60000000000000299',
    'referencedMessage': {
        'id': '60000000000000299',
        'channelId': TEXT_ID,
        'authorId': OWNER_ID,
        'content': 'earlier message',
        'deleted': False,
        'voice': False,
        'author': user_ref(OWNER_ID, 'owner', 'The Owner'),
    },
    'pinned': False,
    'editedAt': None,
    'createdAt': '2026-11-01T12:00:00.000Z',
    'author': user_ref(MEMBER_ID, 'sara', 'Sara K'),
    'attachments': [
        {
            'id': '60000000000000600',
            'kind': 'IMAGE',
            'fileName': 'cat.png',
            'contentType': 'image/png',
            'sizeBytes': '2048',
            'width': 64,
            'height': 48,
            'description': 'a cat',
            'spoiler': False,
            'url': 'https://cdn.bisim.gg/attachments/cat.png',
        }
    ],
    'embeds': [
        {
            'url': 'https://example.com',
            'type': 'rich',
            'title': 'Status',
            'description': 'All good',
            'siteName': None,
            'imageUrl': None,
            'color': 0x2ECC71,
            'authorName': 'Monitor',
            'authorUrl': None,
            'footerText': 'v1',
            'timestamp': '2026-11-01T12:00:00.000Z',
            'fields': [{'name': 'Uptime', 'value': '99%', 'inline': True}],
        }
    ],
    'reactions': [{'emoji': '👍', 'count': 2, 'me': False}, {'emoji': '<:wave:60000000000000500>', 'count': 1, 'me': True}],
    'poll': None,
    'webhookId': None,
    'interaction': None,
    'components': [
        {
            'type': 1,
            'components': [
                {'type': 2, 'style': 1, 'label': 'Yes', 'customId': 'vote:yes'},
                {'type': 2, 'style': 5, 'label': 'Docs', 'url': 'https://docs.bisim.gg'},
            ],
        }
    ],
}


def message(**overrides: Any) -> Dict[str, Any]:
    data = copy.deepcopy(MESSAGE)
    data.update(overrides)
    return data


def envelope(event: str, **fields: Any) -> Dict[str, Any]:
    return {'op': 0, 't': event, 'd': {'type': event, **fields}}


INTERACTION_ID = '60000000000000700'
INTERACTION_TOKEN = 'interaction-token'


def member_ref(user_id: str = MEMBER_ID, username: str = 'sara', **extra: Any) -> Dict[str, Any]:
    """A ``member`` block as an interaction payload carries it."""
    data = {
        'userId': user_id,
        'username': username,
        'displayName': None,
        'avatarKey': None,
        'user': user_ref(user_id, username),
        'nickname': None,
        'roleIds': [GUILD_ID],
        'joinedAt': '2026-07-02T10:00:00.000Z',
        'timeoutUntil': None,
        'permissions': EVERYONE_PERMS,
    }
    data.update(extra)
    return data


def interaction(kind: int, data: Dict[str, Any], *, guild: bool = True, **extra: Any) -> Dict[str, Any]:
    """An interaction payload, as INTERACTION_CREATE or an Interactions URL delivers it."""
    payload: Dict[str, Any] = {
        'id': INTERACTION_ID,
        'type': kind,
        'token': INTERACTION_TOKEN,
        'applicationId': BOT_ID,
        'guildId': GUILD_ID if guild else None,
        'channelId': TEXT_ID if guild else DM_ID,
        'locale': 'en',
        'appPermissions': GUILD_DETAIL['channels'][1]['permissions'] if guild else '',
        'user': user_ref(MEMBER_ID, 'sara', 'Sara K'),
        'member': member_ref(MEMBER_ID, 'sara', nickname='Sara', roleIds=[GUILD_ID, MOD_ROLE_ID], permissions=str(int(EVERYONE_PERMS) | int(MOD_PERMS))) if guild else None,
        'data': data,
    }
    payload.update(extra)
    return payload


def interaction_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """The ``d`` of an INTERACTION_CREATE frame carrying ``payload``."""
    import json

    return {'type': 'INTERACTION_CREATE', 'interaction': {'payloadJson': json.dumps(payload)}}

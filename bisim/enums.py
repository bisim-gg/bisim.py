"""Enumerations with discord.py's names and Discord's numbers.

Bisim uses Discord's numbers for types, flags and permission bits, and names
for a few of them on the wire (channel and message types). The mapping
between the two lives here, so the rest of the library deals only in these
enums.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, Optional, Type, TypeVar

__all__ = (
    'Enum',
    'ChannelType',
    'MessageType',
    'SpeakingState',
    'VerificationLevel',
    'ContentFilter',
    'Status',
    'DefaultAvatar',
    'NotificationLevel',
    'AuditLogAction',
    'AuditLogActionCategory',
    'UserFlags',
    'ActivityType',
    'WebhookType',
    'ExpireBehaviour',
    'ExpireBehavior',
    'StickerType',
    'StickerFormatType',
    'InviteTarget',
    'VideoQualityMode',
    'ComponentType',
    'ButtonStyle',
    'TextStyle',
    'PrivacyLevel',
    'InteractionType',
    'InteractionResponseType',
    'NSFWLevel',
    'MFALevel',
    'Locale',
    'EntityType',
    'EventStatus',
    'AppCommandType',
    'AppCommandOptionType',
    'AppCommandPermissionType',
    'SelectDefaultValueType',
    'MessageReferenceType',
    'PollLayoutType',
    'ReactionType',
    'InviteType',
    'AutoModRuleTriggerType',
    'AutoModRuleEventType',
    'AutoModRuleActionType',
    'try_enum',
)

E = TypeVar('E', bound='Enum')


class Enum(enum.Enum):
    """The base class of every enumeration in the library.

    Behaves like :class:`enum.Enum`. Looking up a value Bisim sends that the
    library does not know yet never fails: :func:`try_enum` returns a stand in
    with ``name`` ``unknown_<value>`` instead.
    """

    @classmethod
    def try_value(cls, value: Any) -> Any:
        try:
            return cls(value)
        except ValueError:
            return value


class _OrderedEnum(Enum):
    """An enum whose members compare by value with ``<`` and ``>``."""

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self.value < other.value
        return NotImplemented

    def __le__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self.value >= other.value
        return NotImplemented


class _UnknownValue:
    """A value Bisim sent that this version of the library does not know."""

    __slots__ = ('name', 'value', '_enum')

    def __init__(self, enum_cls: Type[Enum], value: Any) -> None:
        self._enum = enum_cls
        self.value = value
        self.name = f'unknown_{value}'

    def __repr__(self) -> str:
        return f'<{self._enum.__name__}.{self.name}: {self.value!r}>'

    def __str__(self) -> str:
        return f'{self._enum.__name__}.{self.name}'

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _UnknownValue) and other._enum is self._enum and other.value == self.value

    def __hash__(self) -> int:
        return hash((self._enum, self.value))

    def __int__(self) -> int:
        return int(self.value)


def try_enum(cls: Type[E], val: Any) -> E:
    """A function that tries to turn the value into enum ``cls``.

    If it fails it returns a proxy invalid value instead.
    """
    try:
        return cls(val)
    except (ValueError, TypeError, KeyError):
        return _UnknownValue(cls, val)  # type: ignore


class ChannelType(Enum):
    """Specifies the type of channel.

    Bisim has text, voice and category channels in servers, DMs and group
    DMs. The thread, news, stage, forum and media members are kept so code
    that compares against them still runs; no channel ever has those types.

    Attributes
    -----------
    text
        A text channel (Bisim's ``GUILD_TEXT``).
    voice
        A voice channel (``GUILD_VOICE``).
    private
        A private text channel. Also called a direct message (``DM``).
    group
        A private group text channel (``GROUP_DM``).
    category
        A category channel (``GUILD_CATEGORY``).
    news
        Not on Bisim.
    stage_voice
        Not on Bisim.
    news_thread
        Not on Bisim.
    public_thread
        Not on Bisim.
    private_thread
        Not on Bisim.
    forum
        Not on Bisim.
    media
        Not on Bisim.
    """

    text = 0
    private = 1
    voice = 2
    group = 3
    category = 4
    news = 5
    news_thread = 10
    public_thread = 11
    private_thread = 12
    stage_voice = 13
    forum = 15
    media = 16

    def __str__(self) -> str:
        return self.name

    @property
    def bisim_name(self) -> Optional[str]:
        """Optional[:class:`str`]: The name Bisim uses for this type, such as ``GUILD_TEXT``.

        ``None`` for the types Bisim does not have.
        """
        return _CHANNEL_TYPE_TO_BISIM.get(self)

    @classmethod
    def from_bisim(cls, value: Any) -> 'ChannelType':
        """Returns the channel type for one of Bisim's names (``GUILD_TEXT``), or a number."""
        if isinstance(value, ChannelType):
            return value
        if isinstance(value, int):
            return try_enum(cls, value)
        if isinstance(value, str) and value.isdigit():
            return try_enum(cls, int(value))
        return _BISIM_TO_CHANNEL_TYPE.get(str(value).upper(), ChannelType.text)


_CHANNEL_TYPE_TO_BISIM: Dict[ChannelType, str] = {
    ChannelType.text: 'GUILD_TEXT',
    ChannelType.private: 'DM',
    ChannelType.voice: 'GUILD_VOICE',
    ChannelType.group: 'GROUP_DM',
    ChannelType.category: 'GUILD_CATEGORY',
}
_BISIM_TO_CHANNEL_TYPE: Dict[str, ChannelType] = {v: k for k, v in _CHANNEL_TYPE_TO_BISIM.items()}


class MessageReferenceType(Enum):
    default = 0
    reply = 0
    forward = 1


class MessageType(Enum):
    """Specifies the type of :class:`Message`.

    Bisim sends ``DEFAULT``, ``REPLY``, ``SYSTEM_JOIN``, ``SYSTEM_PIN`` and
    ``SYSTEM_AUTOMOD``; they become :attr:`default`, :attr:`reply`,
    :attr:`new_member`, :attr:`pins_add` and :attr:`auto_moderation_action`.
    A bot's answer to a slash command is :attr:`chat_input_command`, and to a
    context menu command :attr:`context_menu_command`.
    """

    default = 0
    recipient_add = 1
    recipient_remove = 2
    call = 3
    channel_name_change = 4
    channel_icon_change = 5
    pins_add = 6
    new_member = 7
    premium_guild_subscription = 8
    premium_guild_tier_1 = 9
    premium_guild_tier_2 = 10
    premium_guild_tier_3 = 11
    channel_follow_add = 12
    guild_stream = 13
    guild_discovery_disqualified = 14
    guild_discovery_requalified = 15
    guild_discovery_grace_period_initial_warning = 16
    guild_discovery_grace_period_final_warning = 17
    thread_created = 18
    reply = 19
    chat_input_command = 20
    thread_starter_message = 21
    guild_invite_reminder = 22
    context_menu_command = 23
    auto_moderation_action = 24
    role_subscription_purchase = 25
    interaction_premium_upsell = 26
    stage_start = 27
    stage_end = 28
    stage_speaker = 29
    stage_raise_hand = 30
    stage_topic = 31
    guild_application_premium_subscription = 32
    guild_incident_alert_mode_enabled = 36
    guild_incident_alert_mode_disabled = 37
    guild_incident_report_raid = 38
    guild_incident_report_false_alarm = 39
    purchase_notification = 44
    poll_result = 46
    emoji_added = 63

    def is_deletable(self) -> bool:
        """Whether a message of this type can be deleted."""
        return self not in (
            MessageType.recipient_add,
            MessageType.recipient_remove,
            MessageType.call,
            MessageType.channel_name_change,
            MessageType.channel_icon_change,
            MessageType.thread_starter_message,
        )

    @classmethod
    def from_bisim(cls, value: Any) -> 'MessageType':
        """Returns the message type for one of Bisim's names (``DEFAULT``, ``REPLY``...)."""
        if isinstance(value, int):
            return try_enum(cls, value)
        return _BISIM_MESSAGE_TYPES.get(str(value or 'DEFAULT').upper(), MessageType.default)


_BISIM_MESSAGE_TYPES: Dict[str, MessageType] = {
    'DEFAULT': MessageType.default,
    'REPLY': MessageType.reply,
    'SYSTEM_JOIN': MessageType.new_member,
    'SYSTEM_PIN': MessageType.pins_add,
    'SYSTEM_AUTOMOD': MessageType.auto_moderation_action,
    'POLL_RESULT': MessageType.poll_result,
}


class SpeakingState(Enum):
    none = 0
    voice = 1
    soundshare = 2
    priority = 4

    def __str__(self) -> str:
        return self.name

    def __int__(self) -> int:
        return self.value


class VerificationLevel(_OrderedEnum):
    """Specifies a :class:`Guild`\\'s verification level, which is the criteria in
    which a member must meet before being able to send messages to the server.
    """

    none = 0
    low = 1
    medium = 2
    high = 3
    highest = 4

    def __str__(self) -> str:
        return self.name


class ContentFilter(_OrderedEnum):
    disabled = 0
    no_role = 1
    all_members = 2

    def __str__(self) -> str:
        return self.name


class Status(Enum):
    """Specifies a :class:`Member` 's status.

    Attributes
    -----------
    online
        The member is online.
    offline
        The member is offline.
    idle
        The member is idle.
    dnd
        The member is "Do Not Disturb".
    do_not_disturb
        An alias for :attr:`dnd`.
    invisible
        The member is "invisible". In reality, this is only used when sending
        a presence. When you receive a user's presence this will be
        :attr:`offline` instead.
    """

    online = 'online'
    offline = 'offline'
    idle = 'idle'
    dnd = 'dnd'
    do_not_disturb = 'dnd'
    invisible = 'invisible'

    def __str__(self) -> str:
        return self.value


class DefaultAvatar(Enum):
    blurple = 0
    grey = 1
    gray = 1
    green = 2
    orange = 3
    red = 4
    pink = 5

    def __str__(self) -> str:
        return self.name


class NotificationLevel(_OrderedEnum):
    all_messages = 0
    only_mentions = 1


class AuditLogActionCategory(Enum):
    create = 1
    delete = 2
    update = 3


class AuditLogAction(Enum):
    """Represents the type of action being done for an :class:`AuditLogEntry`.

    Bisim names its actions (``CHANNEL_CREATE``...); the ones with a
    Discord counterpart map to these members.
    """

    guild_update = 1
    channel_create = 10
    channel_update = 11
    channel_delete = 12
    overwrite_create = 13
    overwrite_update = 14
    overwrite_delete = 15
    kick = 20
    member_prune = 21
    ban = 22
    unban = 23
    member_update = 24
    member_role_update = 25
    member_move = 26
    member_disconnect = 27
    bot_add = 28
    role_create = 30
    role_update = 31
    role_delete = 32
    invite_create = 40
    invite_update = 41
    invite_delete = 42
    webhook_create = 50
    webhook_update = 51
    webhook_delete = 52
    emoji_create = 60
    emoji_update = 61
    emoji_delete = 62
    message_delete = 72
    message_bulk_delete = 73
    message_pin = 74
    message_unpin = 75
    integration_create = 80
    integration_update = 81
    integration_delete = 82
    sticker_create = 90
    sticker_update = 91
    sticker_delete = 92
    thread_create = 110
    thread_update = 111
    thread_delete = 112
    app_command_permission_update = 121
    soundboard_sound_create = 130
    soundboard_sound_update = 131
    soundboard_sound_delete = 132
    automod_rule_create = 140
    automod_rule_update = 141
    automod_rule_delete = 142
    automod_block_message = 143
    automod_flag_message = 144
    automod_timeout_member = 145

    @property
    def category(self) -> Optional[AuditLogActionCategory]:
        name = self.name
        if name.endswith('_create') or name in ('bot_add', 'ban', 'message_pin'):
            return AuditLogActionCategory.create
        if name.endswith('_delete') or name in ('kick', 'member_prune', 'unban', 'member_disconnect', 'message_unpin'):
            return AuditLogActionCategory.delete
        if name.endswith('_update') or name == 'member_move':
            return AuditLogActionCategory.update
        return None

    @property
    def target_type(self) -> Optional[str]:
        name = self.name
        if name.startswith('guild'):
            return 'guild'
        for prefix in ('channel', 'overwrite'):
            if name.startswith(prefix):
                return 'channel'
        for prefix, target in (
            ('member', 'user'),
            ('kick', 'user'),
            ('ban', 'user'),
            ('unban', 'user'),
            ('bot', 'user'),
            ('role', 'role'),
            ('invite', 'invite'),
            ('webhook', 'webhook'),
            ('emoji', 'emoji'),
            ('message', 'user'),
            ('sticker', 'sticker'),
            ('automod', 'auto_moderation'),
            ('soundboard', 'soundboard_sound'),
        ):
            if name.startswith(prefix):
                return target
        return None


class UserFlags(Enum):
    staff = 1
    partner = 2
    hypesquad = 4
    bug_hunter = 8
    mfa_sms = 16
    premium_promo_dismissed = 32
    hypesquad_bravery = 64
    hypesquad_brilliance = 128
    hypesquad_balance = 256
    early_supporter = 512
    team_user = 1024
    system = 4096
    has_unread_urgent_messages = 8192
    bug_hunter_level_2 = 16384
    verified_bot = 65536
    verified_bot_developer = 131072
    discord_certified_moderator = 262144
    bot_http_interactions = 524288
    spammer = 1048576
    active_developer = 4194304


class ActivityType(Enum):
    """Specifies the type of :class:`Activity`. This is used to check how to
    interpret the activity itself.

    Attributes
    -----------
    unknown
        An unknown activity type. This should generally not happen.
    playing
        A "Playing" activity type.
    streaming
        A "Streaming" activity type.
    listening
        A "Listening" activity type.
    watching
        A "Watching" activity type.
    custom
        A custom activity type (on Bisim, the custom status text).
    competing
        A competing activity type.
    """

    unknown = -1
    playing = 0
    streaming = 1
    listening = 2
    watching = 3
    custom = 4
    competing = 5

    def __int__(self) -> int:
        return self.value


class WebhookType(Enum):
    incoming = 1
    channel_follower = 2
    application = 3


class ExpireBehaviour(Enum):
    remove_role = 0
    kick = 1


ExpireBehavior = ExpireBehaviour


class StickerType(Enum):
    standard = 1
    guild = 2


class StickerFormatType(Enum):
    png = 1
    apng = 2
    lottie = 3
    gif = 4

    @property
    def file_extension(self) -> str:
        return {1: 'png', 2: 'png', 3: 'json', 4: 'gif'}[self.value]


class InviteTarget(Enum):
    unknown = 0
    stream = 1
    embedded_application = 2


class InviteType(Enum):
    guild = 0
    group_dm = 1
    friend = 2


class InteractionType(Enum):
    """Specifies the type of :class:`Interaction`.

    Attributes
    -----------
    ping
        Represents Bisim pinging an Interactions URL to see if it's alive.
    application_command
        Represents a slash command or context menu interaction.
    component
        Represents a component based interaction, i.e. using the Bisim Bot UI Kit.
    autocomplete
        Represents an auto complete interaction.
    modal_submit
        Represents submission of a modal interaction.
    """

    ping = 1
    application_command = 2
    component = 3
    autocomplete = 4
    modal_submit = 5


class InteractionResponseType(Enum):
    """Specifies the response type for the interaction.

    Attributes
    -----------
    pong
        Pongs the interaction when given a ping.
    channel_message
        Respond to the interaction with a message.
    deferred_channel_message
        Responds to the interaction with a message at a later time.
    deferred_message_update
        Acknowledges the component interaction with a promise that
        the message will update later (though there is no need to actually update the message).
    message_update
        Responds to the interaction by editing the message.
    autocomplete_result
        Responds to the autocomplete interaction with suggested choices.
    modal
        Responds to the interaction with a modal.
    premium_required
        Not on Bisim.
    launch_activity
        Not on Bisim.
    """

    pong = 1
    channel_message = 4
    deferred_channel_message = 5
    deferred_message_update = 6
    message_update = 7
    autocomplete_result = 8
    modal = 9
    premium_required = 10
    launch_activity = 12


class VideoQualityMode(Enum):
    auto = 1
    full = 2

    def __int__(self) -> int:
        return self.value


class ComponentType(Enum):
    """Represents the component type of a component.

    Attributes
    -----------
    action_row
        Represents the group component which holds different components in a row.
    button
        Represents a button component.
    select
        An alias to :attr:`string_select`.
    string_select
        Represents a string select component.
    text_input
        Represents a text box component.
    user_select
        Represents a user select component.
    role_select
        Represents a role select component.
    mentionable_select
        Represents a select in which both users and roles can be selected.
    channel_select
        Represents a channel select component.
    """

    action_row = 1
    button = 2
    select = 3
    string_select = 3
    text_input = 4
    user_select = 5
    role_select = 6
    mentionable_select = 7
    channel_select = 8
    section = 9
    text_display = 10
    thumbnail = 11
    media_gallery = 12
    file = 13
    separator = 14
    container = 17
    label = 18

    def __int__(self) -> int:
        return self.value


class ButtonStyle(Enum):
    """Represents the style of the button component.

    Attributes
    -----------
    primary
        Represents a blurple button for the primary action.
    secondary
        Represents a grey button for the secondary action.
    success
        Represents a green button for a successful action.
    danger
        Represents a red button for a dangerous action.
    link
        Represents a link button.
    premium
        Not on Bisim.
    blurple
        An alias for :attr:`primary`.
    grey
        An alias for :attr:`secondary`.
    gray
        An alias for :attr:`secondary`.
    green
        An alias for :attr:`success`.
    red
        An alias for :attr:`danger`.
    url
        An alias for :attr:`link`.
    """

    primary = 1
    secondary = 2
    success = 3
    danger = 4
    link = 5
    premium = 6

    # Aliases
    blurple = 1
    grey = 2
    gray = 2
    green = 3
    red = 4
    url = 5

    def __int__(self) -> int:
        return self.value


class TextStyle(Enum):
    """Represents the style of the text box component.

    Attributes
    -----------
    short
        Represents a short text box.
    paragraph
        Represents a long form text box.
    long
        An alias for :attr:`paragraph`.
    """

    short = 1
    paragraph = 2

    # Aliases
    long = 2

    def __int__(self) -> int:
        return self.value


class PrivacyLevel(Enum):
    guild_only = 2


class NSFWLevel(_OrderedEnum):
    default = 0
    explicit = 1
    safe = 2
    age_restricted = 3


class MFALevel(_OrderedEnum):
    disabled = 0
    require_2fa = 1


class Locale(Enum):
    """Supported locales.

    Bisim's own languages are :attr:`persian` (``fa``) and :attr:`english`
    (``en``); the rest are Discord's, kept for compatibility.
    """

    persian = 'fa'
    english = 'en'
    american_english = 'en-US'
    british_english = 'en-GB'
    bulgarian = 'bg'
    chinese = 'zh-CN'
    taiwan_chinese = 'zh-TW'
    croatian = 'hr'
    czech = 'cs'
    indonesian = 'id'
    danish = 'da'
    dutch = 'nl'
    finnish = 'fi'
    french = 'fr'
    german = 'de'
    greek = 'el'
    hindi = 'hi'
    hungarian = 'hu'
    italian = 'it'
    japanese = 'ja'
    korean = 'ko'
    latin_american_spanish = 'es-419'
    lithuanian = 'lt'
    norwegian = 'no'
    polish = 'pl'
    brazil_portuguese = 'pt-BR'
    romanian = 'ro'
    russian = 'ru'
    spain_spanish = 'es-ES'
    swedish = 'sv-SE'
    thai = 'th'
    turkish = 'tr'
    ukrainian = 'uk'
    vietnamese = 'vi'

    def __str__(self) -> str:
        return self.value

    @property
    def language_code(self) -> str:
        """:class:`str`: The language code of the locale (``fa``, ``en``, ``en-US``...)."""
        return self.value

    @property
    def bisim_code(self) -> str:
        """:class:`str`: The Bisim language this locale maps to: ``fa`` or ``en``."""
        return 'fa' if self is Locale.persian else 'en'


class EntityType(Enum):
    stage_instance = 1
    voice = 2
    external = 3


class EventStatus(Enum):
    scheduled = 1
    active = 2
    completed = 3
    canceled = 4
    ended = 3
    cancelled = 4


class AppCommandOptionType(Enum):
    """The application command's option type. Bisim sends these by name
    (``STRING``); the numbers are Discord's.
    """

    subcommand = 1
    sub_command = 1
    subcommand_group = 2
    sub_command_group = 2
    string = 3
    integer = 4
    boolean = 5
    user = 6
    channel = 7
    role = 8
    mentionable = 9
    number = 10
    attachment = 11

    def is_argument(self) -> bool:
        return 11 >= self.value >= 3

    @property
    def bisim_name(self) -> str:
        """:class:`str`: The name Bisim uses on the wire, such as ``STRING`` or ``SUB_COMMAND``."""
        return _OPTION_TYPE_NAMES[self.value]

    @classmethod
    def from_bisim(cls, value: Any) -> 'AppCommandOptionType':
        """Returns the option type for a Bisim name (``STRING``) or a number."""
        if isinstance(value, cls):
            return value
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return try_enum(cls, int(value))
        return try_enum(cls, _OPTION_TYPE_NUMBERS.get(str(value).upper(), -1))


_OPTION_TYPE_NAMES: Dict[int, str] = {
    1: 'SUB_COMMAND',
    2: 'SUB_COMMAND_GROUP',
    3: 'STRING',
    4: 'INTEGER',
    5: 'BOOLEAN',
    6: 'USER',
    7: 'CHANNEL',
    8: 'ROLE',
    9: 'MENTIONABLE',
    10: 'NUMBER',
    11: 'ATTACHMENT',
}
_OPTION_TYPE_NUMBERS: Dict[str, int] = {v: k for k, v in _OPTION_TYPE_NAMES.items()}
_OPTION_TYPE_NUMBERS['SUBCOMMAND'] = 1
_OPTION_TYPE_NUMBERS['SUBCOMMAND_GROUP'] = 2


class AppCommandType(Enum):
    """The type of application command.

    Attributes
    -----------
    chat_input
        A slash command.
    user
        A user context menu command.
    message
        A message context menu command.
    primary_entry_point
        Not on Bisim.
    """

    chat_input = 1
    user = 2
    message = 3
    primary_entry_point = 4

    @classmethod
    def from_bisim(cls, value: Any) -> 'AppCommandType':
        if isinstance(value, cls):
            return value
        if value is None or value == '':
            return cls.chat_input
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return try_enum(cls, int(value))
        return {'CHAT_INPUT': cls.chat_input, 'USER': cls.user, 'MESSAGE': cls.message}.get(str(value).upper(), cls.chat_input)


class AppCommandPermissionType(Enum):
    role = 1
    user = 2
    channel = 3


class SelectDefaultValueType(Enum):
    user = 'user'
    role = 'role'
    channel = 'channel'


class PollLayoutType(Enum):
    default = 1


class ReactionType(Enum):
    normal = 0
    burst = 1


class AutoModRuleTriggerType(Enum):
    """What an AutoMod rule looks for. Bisim's names map to Discord's numbers."""

    keyword = 1
    harmful_link = 2
    spam = 3
    keyword_preset = 4
    mention_spam = 5
    member_profile = 6

    @classmethod
    def from_bisim(cls, value: Any) -> 'AutoModRuleTriggerType':
        if isinstance(value, cls):
            return value
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return try_enum(cls, int(value))
        named = {
            'KEYWORD': cls.keyword,
            'SPAM': cls.spam,
            'KEYWORD_PRESET': cls.keyword_preset,
            'MENTION_SPAM': cls.mention_spam,
        }
        return named.get(str(value or '').upper(), cls.keyword)

    def to_bisim(self) -> str:
        return {
            AutoModRuleTriggerType.spam: 'SPAM',
            AutoModRuleTriggerType.keyword_preset: 'KEYWORD_PRESET',
            AutoModRuleTriggerType.mention_spam: 'MENTION_SPAM',
        }.get(self, 'KEYWORD')


class AutoModRuleEventType(Enum):
    """When an AutoMod rule runs. Bisim's names map to Discord's numbers."""

    message_send = 1
    member_update = 2

    @classmethod
    def from_bisim(cls, value: Any) -> 'AutoModRuleEventType':
        if isinstance(value, cls):
            return value
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return try_enum(cls, int(value))
        return cls.member_update if str(value or '').upper() == 'MEMBER_UPDATE' else cls.message_send

    def to_bisim(self) -> str:
        return 'MEMBER_UPDATE' if self is AutoModRuleEventType.member_update else 'MESSAGE_SEND'


class AutoModRuleActionType(Enum):
    """What an AutoMod rule does when it matches."""

    block_message = 1
    send_alert_message = 2
    timeout = 3
    block_member_interactions = 4

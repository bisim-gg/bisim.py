from __future__ import annotations

import asyncio
import copy
import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Dict,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from . import abc, utils
from .asset import Asset
from .audit_logs import AuditLogEntry
from .channel import (
    CategoryChannel,
    TextChannel,
    VoiceChannel,
    _guild_channel_factory,
)
from .colour import Colour
from .emoji import Emoji
from .enums import (
    AuditLogAction,
    ChannelType,
    ContentFilter,
    Locale,
    MFALevel,
    NotificationLevel,
    NSFWLevel,
    VerificationLevel,
    try_enum,
)
from .errors import ClientException, InvalidData, NotFound, NotSupported
from .file import File
from .flags import SystemChannelFlags
from .invite import Invite
from .member import Member, VoiceState
from .mixins import Hashable
from .object import Object
from .permissions import PermissionOverwrite, Permissions
from .role import Role
from .soundboard import SoundboardSound
from .sticker import GuildSticker
from .user import User
from .voice_client import VoiceClient, VoiceProtocol

if TYPE_CHECKING:
    from .abc import GuildChannel, Snowflake
    from .automod import AutoModRule, AutoModRuleAction, AutoModTrigger
    from .enums import AutoModRuleEventType
    from .state import ConnectionState
    from .webhook import Webhook

__all__ = (
    'Guild',
    'BanEntry',
    'BulkBanResult',
)


class BanEntry(NamedTuple):
    reason: Optional[str]
    user: User


class BulkBanResult(NamedTuple):
    banned: List[Object]
    failed: List[Object]


class _GuildLimit(NamedTuple):
    emoji: int
    stickers: int
    bitrate: float
    filesize: int
    soundboard: int


DEFAULT_FILESIZE_LIMIT = 10 * 1024 * 1024


class Guild(Hashable):
    """Represents a Bisim guild (a server).

    .. container:: operations

        .. describe:: x == y

            Checks if two guilds are equal.

        .. describe:: x != y

            Checks if two guilds are not equal.

        .. describe:: hash(x)

            Returns the guild's hash.

        .. describe:: str(x)

            Returns the guild's name.

    Attributes
    ----------
    name: :class:`str`
        The guild name.
    emojis: Tuple[:class:`Emoji`, ...]
        All emojis that the guild owns.
    stickers: Tuple[:class:`GuildSticker`, ...]
        All stickers that the guild owns.
    afk_timeout: :class:`int`
        The number of seconds until someone is moved to the AFK channel.
    id: :class:`int`
        The guild's ID.
    owner_id: :class:`int`
        The guild owner's ID.
    unavailable: :class:`bool`
        Always ``False`` on Bisim.
    max_presences: Optional[:class:`int`]
        Always ``None``.
    max_members: Optional[:class:`int`]
        Always ``None``.
    max_video_channel_users: Optional[:class:`int`]
        Always ``None``.
    description: Optional[:class:`str`]
        The guild's description.
    verification_level: :class:`VerificationLevel`
        The guild's verification level.
    vanity_url_code: Optional[:class:`str`]
        Always ``None`` (Bisim does not tell a bot).
    explicit_content_filter: :class:`ContentFilter`
        Always :attr:`ContentFilter.disabled` (Bisim has AutoMod instead).
    default_notifications: :class:`NotificationLevel`
        Always :attr:`NotificationLevel.all_messages`.
    features: List[:class:`str`]
        Always empty.
    premium_tier: :class:`int`
        Always ``0``.
    premium_subscription_count: :class:`int`
        Always ``0``.
    preferred_locale: :class:`Locale`
        Always :attr:`Locale.persian`.
    nsfw_level: :class:`NSFWLevel`
        Always :attr:`NSFWLevel.default`.
    mfa_level: :class:`MFALevel`
        Always :attr:`MFALevel.disabled`.
    approximate_member_count: Optional[:class:`int`]
        The approximate number of members in the guild, when known.
    approximate_presence_count: Optional[:class:`int`]
        The approximate number of members currently active in the guild.
    premium_progress_bar_enabled: :class:`bool`
        Always ``False``.
    widget_enabled: :class:`bool`
        Always ``False``.
    """

    __slots__ = (
        'afk_timeout',
        'name',
        'id',
        'unavailable',
        'owner_id',
        'emojis',
        'stickers',
        'features',
        'verification_level',
        'explicit_content_filter',
        'default_notifications',
        'description',
        'max_presences',
        'max_members',
        'max_video_channel_users',
        'premium_tier',
        'premium_subscription_count',
        'preferred_locale',
        'nsfw_level',
        'mfa_level',
        'vanity_url_code',
        'widget_enabled',
        'approximate_member_count',
        'approximate_presence_count',
        'premium_progress_bar_enabled',
        '_members',
        '_channels',
        '_icon',
        '_banner',
        '_splash',
        '_state',
        '_roles',
        '_member_count',
        '_large',
        '_afk_channel_id',
        '_system_channel_id',
        '_voice_states',
        '_my_permissions',
        '_my_role_ids',
        '_chunked',
        '_created_at',
        '_detail_loaded',
        '_subscribed',
        '_soundboard_sounds',
        '__weakref__',
    )

    def __init__(self, *, data: Dict[str, Any], state: ConnectionState) -> None:
        self._state: ConnectionState = state
        self._channels: Dict[int, GuildChannel] = {}
        self._members: Dict[int, Member] = {}
        self._roles: Dict[int, Role] = {}
        self._voice_states: Dict[int, VoiceState] = {}
        self.emojis: Tuple[Emoji, ...] = ()
        self.stickers: Tuple[GuildSticker, ...] = ()
        self._member_count: Optional[int] = None
        self._chunked: bool = False
        self._my_permissions: Optional[int] = None
        self._my_role_ids: Set[int] = set()
        self._detail_loaded: bool = False
        self._subscribed: bool = False
        # Sounds the library has seen: fetched, or announced since the bot connected.
        self._soundboard_sounds: Dict[int, SoundboardSound] = {}
        self.id: int = int(data['id'])
        self._from_data(data)

    def __str__(self) -> str:
        return self.name or ''

    def __repr__(self) -> str:
        attrs = (
            ('id', self.id),
            ('name', self.name),
            ('chunked', self.chunked),
            ('member_count', self.member_count),
        )
        inner = ' '.join('%s=%r' % t for t in attrs)
        return f'<Guild {inner}>'

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _from_data(self, data: Dict[str, Any]) -> None:
        self.name: str = data.get('name') or ''
        self._icon: Optional[str] = data.get('iconKey') or None
        self._banner: Optional[str] = data.get('bannerKey') or None
        self._splash: Optional[str] = data.get('splashKey') or None
        self.description: Optional[str] = data.get('description') or None
        self.verification_level: VerificationLevel = try_enum(VerificationLevel, utils._int(data.get('verificationLevel'), 0))
        self.owner_id: Optional[int] = utils._snowflake(data.get('ownerId'))
        self._system_channel_id: Optional[int] = utils._snowflake(data.get('systemChannelId'))
        self._afk_channel_id: Optional[int] = utils._snowflake(data.get('afkChannelId'))
        self.afk_timeout: int = utils._int(data.get('afkTimeout'), 300)
        self._created_at: Optional[datetime.datetime] = utils.parse_time(data.get('createdAt'))
        self.unavailable: bool = False
        self.features: List[str] = []
        self.explicit_content_filter: ContentFilter = ContentFilter.disabled
        self.default_notifications: NotificationLevel = NotificationLevel.all_messages
        self.max_presences: Optional[int] = None
        self.max_members: Optional[int] = None
        self.max_video_channel_users: Optional[int] = None
        self.premium_tier: int = 0
        self.premium_subscription_count: int = 0
        self.preferred_locale: Locale = Locale.persian
        self.nsfw_level: NSFWLevel = NSFWLevel.default
        self.mfa_level: MFALevel = MFALevel.disabled
        self.vanity_url_code: Optional[str] = None
        self.widget_enabled: bool = False
        self.approximate_member_count: Optional[int] = data.get('memberCount')
        self.approximate_presence_count: Optional[int] = data.get('onlineCount')
        self.premium_progress_bar_enabled: bool = False
        if data.get('memberCount') is not None:
            self._member_count = int(data['memberCount'])

        if 'roles' in data or 'channels' in data:
            self._load_detail(data)

    def _load_detail(self, data: Dict[str, Any]) -> None:
        """Builds roles and channels from ``GET /guilds/:id``."""
        state = self._state
        roles: Dict[int, Role] = {}
        for role_data in data.get('roles') or []:
            role_id = int(role_data['id'])
            existing = self._roles.get(role_id)
            if existing is not None:
                existing._update(role_data)
                roles[role_id] = existing
            else:
                roles[role_id] = Role(guild=self, state=state, data=role_data)
        self._roles = roles

        channels: Dict[int, GuildChannel] = {}
        for channel_data in data.get('channels') or []:
            cls, _ = _guild_channel_factory(channel_data.get('type'))
            if cls is None:
                continue
            channel_id = int(channel_data['id'])
            existing_channel = self._channels.get(channel_id)
            if existing_channel is not None and isinstance(existing_channel, cls):
                existing_channel._update(self, channel_data)  # type: ignore
                # Overwrites may have changed: load them again when needed.
                existing_channel._overwrites_loaded = False
                channels[channel_id] = existing_channel
            else:
                channels[channel_id] = cls(state=state, guild=self, data=channel_data)  # type: ignore
        self._channels = channels

        if data.get('permissions') not in (None, ''):
            self._my_permissions = int(data['permissions'])
        if data.get('myRoleIds') is not None:
            self._my_role_ids = {int(r) for r in data['myRoleIds'] if r and int(r) != self.id}
            me = self.me
            if me is not None:
                me._roles = utils.SnowflakeList(self._my_role_ids)
        self._detail_loaded = True

    def _update_from_event(self, data: Dict[str, Any]) -> None:
        """GUILD_UPDATE carries the current state; a missing field is empty."""
        self.name = data.get('name') or self.name
        self._icon = data.get('iconKey') or None
        self._banner = data.get('bannerKey') or None
        self._splash = data.get('splashKey') or None
        self.description = data.get('description') or None
        if data.get('ownerId'):
            self.owner_id = int(data['ownerId'])
        self.verification_level = try_enum(VerificationLevel, utils._int(data.get('verificationLevel'), 0))
        self._system_channel_id = utils._snowflake(data.get('systemChannelId'))
        self._afk_channel_id = utils._snowflake(data.get('afkChannelId'))
        self.afk_timeout = utils._int(data.get('afkTimeout'), 0)

    def _add_channel(self, channel: GuildChannel, /) -> None:
        self._channels[channel.id] = channel

    def _remove_channel(self, channel: Snowflake, /) -> None:
        self._channels.pop(channel.id, None)

    def _voice_state_for(self, user_id: int, /) -> Optional[VoiceState]:
        return self._voice_states.get(user_id)

    def _add_member(self, member: Member, /) -> None:
        self._members[member.id] = member

    def _store_member(self, data: Dict[str, Any]) -> Member:
        user_id = int(data.get('userId') or (data.get('user') or {}).get('id'))
        existing = self._members.get(user_id)
        if existing is not None:
            existing._update(data)
            user = data.get('user')
            if isinstance(user, dict) and user:
                existing._user._patch(user)
            return existing
        member = Member(data=data, guild=self, state=self._state)
        self._members[member.id] = member
        return member

    def _remove_member(self, member: Snowflake, /) -> None:
        self._members.pop(member.id, None)

    def _add_role(self, role: Role, /) -> None:
        self._roles[role.id] = role

    def _remove_role(self, role_id: int, /) -> Role:
        role = self._roles.pop(role_id)
        for member in self._members.values():
            member._roles.discard(role_id)
        return role

    def _load_voice_states(self, data: Any) -> None:
        states = data.get('states') if isinstance(data, dict) else data
        statuses = data.get('statuses') if isinstance(data, dict) else None
        self._voice_states = {}
        for raw in states or []:
            channel = self.get_channel(utils._snowflake(raw.get('channelId')) or 0)
            user_id = int(raw['userId'])
            self._voice_states[user_id] = VoiceState(data=raw, channel=channel)
            # Discord gives the member of everyone in voice, so they are known without the members intent.
            if user_id not in self._members and isinstance(raw.get('member'), dict):
                user = {
                    'id': str(user_id),
                    'username': raw.get('username'),
                    'displayName': raw.get('displayName'),
                    'avatarKey': raw.get('avatarKey'),
                    'bot': bool(raw['member'].get('bot')),
                }
                self._add_member(Member(data={**raw['member'], 'userId': str(user_id), 'user': user}, guild=self, state=self._state))
            elif user_id not in self._members and raw.get('username'):
                self._state.store_user(
                    {
                        'id': user_id,
                        'username': raw.get('username'),
                        'displayName': raw.get('displayName'),
                        'avatarKey': raw.get('avatarKey'),
                    }
                )
        for status in statuses or []:
            channel = self.get_channel(utils._snowflake(status.get('channelId')) or 0)
            if isinstance(channel, VoiceChannel):
                channel.status = status.get('status') or None

    def _update_voice_state(self, data: Dict[str, Any], channel_id: Optional[int]) -> Tuple[Optional[Member], VoiceState, VoiceState]:
        user_id = int(data['userId'])
        channel = self.get_channel(channel_id) if channel_id else None
        try:
            before = self._voice_states[user_id]
            before = copy.copy(before)
        except KeyError:
            before = VoiceState(data={}, channel=None)

        if data.get('left'):
            after = VoiceState(data=data, channel=None)
            self._voice_states.pop(user_id, None)
        else:
            after = VoiceState(data=data, channel=channel)
            self._voice_states[user_id] = after

        member = self.get_member(user_id)
        # Discord's member on a voice state: cache it, so whoever is in voice is a known Member without the members intent.
        if isinstance(data.get('member'), dict) and data['member'] and not data.get('left'):
            raw_member = data['member']
            if member is None:
                user_data = raw_member.get('user') or data.get('user') or {'id': str(user_id)}
                member = Member(data={**raw_member, 'userId': str(user_id), 'user': user_data}, guild=self, state=self._state)
                self._add_member(member)
            else:
                member._update(raw_member)
        if member is None and isinstance(data.get('user'), dict) and data['user']:
            user_data = data['user']
            member = Member(
                data={'userId': user_id, 'user': user_data, 'roleIds': []},
                guild=self,
                state=self._state,
            )
        return member, before, after

    def _load_emojis(self, data: Sequence[Dict[str, Any]]) -> None:
        self.emojis = tuple(Emoji(guild=self, state=self._state, data=e) for e in data or [])

    def _load_stickers(self, data: Sequence[Dict[str, Any]]) -> None:
        self.stickers = tuple(GuildSticker(state=self._state, data=s) for s in data or [])

    def _resolve_channel(self, id: Optional[int], /) -> Optional[GuildChannel]:
        if id is None:
            return None
        return self._channels.get(id)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    @property
    def channels(self) -> Sequence[GuildChannel]:
        """Sequence[:class:`abc.GuildChannel`]: A list of channels that belongs to this guild."""
        return utils.SequenceProxy(self._channels.values())

    @property
    def threads(self) -> Sequence[Any]:
        """Sequence[:class:`Thread`]: Always empty: Bisim has no threads."""
        return []

    @property
    def large(self) -> bool:
        """:class:`bool`: Indicates if the guild is a 'large' guild (250 members or more)."""
        count = self._member_count if self._member_count is not None else len(self._members)
        return count >= 250

    @property
    def voice_channels(self) -> List[VoiceChannel]:
        """List[:class:`VoiceChannel`]: A list of voice channels that belongs to this guild.

        This is sorted by the position and are in UI order from top to bottom.
        """
        r = [ch for ch in self._channels.values() if isinstance(ch, VoiceChannel)]
        r.sort(key=lambda c: (c.position, c.id))
        return r

    @property
    def stage_channels(self) -> List[Any]:
        """List[:class:`StageChannel`]: Always empty: Bisim has no stage channels."""
        return []

    @property
    def me(self) -> Member:
        """:class:`Member`: Similar to :attr:`Client.user` except an instance of :class:`Member`.
        This is essentially used to get the member version of yourself.
        """
        self_id = self._state.self_id
        member = self._members.get(self_id) if self_id is not None else None
        if member is None and self_id is not None and self._state.user is not None:
            # Built from what GET /guilds/:id says about the bot, when members are not loaded.
            member = Member(
                data={
                    'userId': str(self_id),
                    'user': self._state.user._to_minimal_user_json(),
                    'roleIds': [str(r) for r in self._my_role_ids],
                },
                guild=self,
                state=self._state,
            )
            self._members[self_id] = member
        return member  # type: ignore

    def is_dm_spam_detected(self) -> bool:
        """:class:`bool`: Always ``False``."""
        return False

    def is_raid_detected(self) -> bool:
        """:class:`bool`: Always ``False``."""
        return False

    @property
    def voice_client(self) -> Optional[VoiceProtocol]:
        """Optional[:class:`VoiceProtocol`]: Returns the :class:`VoiceProtocol` associated with this guild, if any."""
        return self._state._get_voice_client(self.id)

    @property
    def text_channels(self) -> List[TextChannel]:
        """List[:class:`TextChannel`]: A list of text channels that belongs to this guild.

        This is sorted by the position and are in UI order from top to bottom.
        """
        r = [ch for ch in self._channels.values() if isinstance(ch, TextChannel)]
        r.sort(key=lambda c: (c.position, c.id))
        return r

    @property
    def categories(self) -> List[CategoryChannel]:
        """List[:class:`CategoryChannel`]: A list of categories that belongs to this guild.

        This is sorted by the position and are in UI order from top to bottom.
        """
        r = [ch for ch in self._channels.values() if isinstance(ch, CategoryChannel)]
        r.sort(key=lambda c: (c.position, c.id))
        return r

    @property
    def forums(self) -> List[Any]:
        """List[:class:`ForumChannel`]: Always empty: Bisim has no forum channels."""
        return []

    def by_category(self) -> List[Tuple[Optional[CategoryChannel], List[GuildChannel]]]:
        """Returns every :class:`CategoryChannel` and their associated channels.

        These channels and categories are sorted in the official Bisim UI order.

        If the channels do not have a category, then the first element of the tuple is
        ``None``.

        Returns
        --------
        List[Tuple[Optional[:class:`CategoryChannel`], List[:class:`abc.GuildChannel`]]]:
            The categories and their associated channels.
        """
        grouped: Dict[Optional[int], List[GuildChannel]] = {}
        for channel in self._channels.values():
            if isinstance(channel, CategoryChannel):
                grouped.setdefault(channel.id, [])
                continue
            grouped.setdefault(channel.category_id, []).append(channel)

        def key(t: Tuple[Optional[int], List[GuildChannel]]) -> Tuple[Tuple[int, int], List[GuildChannel]]:
            k, v = t
            category = self._channels.get(k) if k is not None else None
            return ((category.position, category.id) if category else (-1, -1), v)

        as_list: List[Tuple[Optional[CategoryChannel], List[GuildChannel]]] = []
        for k, v in sorted(grouped.items(), key=key):
            v.sort(key=lambda c: (c._sorting_bucket, c.position, c.id))
            as_list.append((self._channels.get(k) if k is not None else None, v))  # type: ignore
        return as_list

    def get_channel_or_thread(self, channel_id: int, /) -> Optional[GuildChannel]:
        """Returns a channel with the given ID (Bisim has no threads).

        Parameters
        -----------
        channel_id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`abc.GuildChannel`]
            The returned channel or ``None`` if not found.
        """
        return self._channels.get(channel_id)

    def get_channel(self, channel_id: int, /) -> Optional[GuildChannel]:
        """Returns a channel with the given ID.

        .. note::

            This does *not* search for threads.

        Parameters
        -----------
        channel_id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`.abc.GuildChannel`]
            The returned channel or ``None`` if not found.
        """
        return self._channels.get(channel_id)

    def get_thread(self, thread_id: int, /) -> None:
        """Always ``None``: Bisim has no threads."""
        return None

    def get_emoji(self, emoji_id: int, /) -> Optional[Emoji]:
        """Returns an emoji with the given ID.

        Parameters
        ----------
        emoji_id: int
            The ID to search for.

        Returns
        --------
        Optional[:class:`Emoji`]
            The returned Emoji or ``None`` if not found.
        """
        return utils.get(self.emojis, id=emoji_id)

    @property
    def afk_channel(self) -> Optional[VoiceChannel]:
        """Optional[:class:`VoiceChannel`]: The channel that denotes the AFK channel.

        If no channel is set, then this returns ``None``.
        """
        return self._channels.get(self._afk_channel_id) if self._afk_channel_id else None  # type: ignore

    @property
    def system_channel(self) -> Optional[TextChannel]:
        """Optional[:class:`TextChannel`]: Returns the guild's channel used for system messages.

        If no channel is set, then this returns ``None``.
        """
        return self._channels.get(self._system_channel_id) if self._system_channel_id else None  # type: ignore

    @property
    def system_channel_flags(self) -> SystemChannelFlags:
        """:class:`SystemChannelFlags`: Returns the guild's system channel settings."""
        return SystemChannelFlags._from_value(1)

    @property
    def rules_channel(self) -> None:
        """Always ``None``: Bisim has no rules channel."""
        return None

    @property
    def public_updates_channel(self) -> None:
        """Always ``None``: Bisim has no community updates channel."""
        return None

    @property
    def safety_alerts_channel(self) -> None:
        """Always ``None``."""
        return None

    @property
    def widget_channel(self) -> None:
        """Always ``None``."""
        return None

    @property
    def emoji_limit(self) -> int:
        """:class:`int`: The maximum number of emoji slots this guild has."""
        return 100

    @property
    def sticker_limit(self) -> int:
        """:class:`int`: The maximum number of sticker slots this guild has."""
        return 30

    @property
    def bitrate_limit(self) -> float:
        """:class:`float`: Kept for compatibility."""
        return 96e3

    @property
    def filesize_limit(self) -> int:
        """:class:`int`: The maximum number of bytes files can have when uploaded."""
        return self._state._upload_limit or DEFAULT_FILESIZE_LIMIT

    @property
    def soundboard_sounds(self) -> List[SoundboardSound]:
        """List[:class:`SoundboardSound`]: The guild's sounds the library has seen.

        Bisim does not send a server's sounds when the bot connects: this holds
        the sounds :meth:`fetch_soundboard_sounds` returned and those created or
        changed since. Call :meth:`fetch_soundboard_sounds` once to load them all.
        """
        return list(self._soundboard_sounds.values())

    def get_soundboard_sound(self, sound_id: int, /) -> Optional[SoundboardSound]:
        """Returns a soundboard sound with the given ID, if the library has seen it.

        Parameters
        -----------
        sound_id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`SoundboardSound`]
            The soundboard sound or ``None`` if not found.
        """
        return self._soundboard_sounds.get(sound_id)

    def _add_soundboard_sound(self, sound: SoundboardSound, /) -> None:
        self._soundboard_sounds[sound.id] = sound

    def _remove_soundboard_sound(self, sound_id: int, /) -> Optional[SoundboardSound]:
        return self._soundboard_sounds.pop(sound_id, None)

    @property
    def members(self) -> Sequence[Member]:
        """Sequence[:class:`Member`]: A list of members that belong to this guild."""
        return utils.SequenceProxy(self._members.values())

    def get_member(self, user_id: int, /) -> Optional[Member]:
        """Returns a member with the given ID.

        Parameters
        -----------
        user_id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`Member`]
            The member or ``None`` if not found.
        """
        return self._members.get(user_id)

    @property
    def premium_subscribers(self) -> List[Member]:
        """List[:class:`Member`]: Always empty: Bisim has no boosts."""
        return []

    @property
    def roles(self) -> Sequence[Role]:
        """Sequence[:class:`Role`]: Returns a sequence of the guild's roles in hierarchy order.

        The first element of this sequence will be the lowest role in the
        hierarchy.
        """
        return utils.SequenceProxy(self._roles.values(), sorted=True)

    def get_role(self, role_id: int, /) -> Optional[Role]:
        """Returns a role with the given ID.

        Parameters
        -----------
        role_id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`Role`]
            The role or ``None`` if not found.
        """
        return self._roles.get(role_id)

    @property
    def default_role(self) -> Role:
        """:class:`Role`: Gets the @everyone role that all members have by default."""
        role = self._roles.get(self.id)
        if role is not None:
            return role
        for candidate in self._roles.values():
            if candidate._is_everyone:
                return candidate
        return None  # type: ignore

    @property
    def premium_subscriber_role(self) -> None:
        """Always ``None``: Bisim has no boosts."""
        return None

    @property
    def self_role(self) -> Optional[Role]:
        """Optional[:class:`Role`]: Gets the role associated with this client's user, if any."""
        self_id = self._state.self_id
        for role in self._roles.values():
            tags = role.tags
            if tags and tags.bot_id == self_id:
                return role
        return None

    @property
    def stage_instances(self) -> List[Any]:
        """List[:class:`StageInstance`]: Always empty."""
        return []

    def get_stage_instance(self, stage_instance_id: int, /) -> None:
        """Always ``None``."""
        return None

    @property
    def scheduled_events(self) -> List[Any]:
        """List[:class:`ScheduledEvent`]: Always empty: Bisim has no scheduled events."""
        return []

    def get_scheduled_event(self, scheduled_event_id: int, /) -> None:
        """Always ``None``."""
        return None

    @property
    def owner(self) -> Optional[Member]:
        """Optional[:class:`Member`]: The member that owns the guild."""
        return self.get_member(self.owner_id) if self.owner_id else None  # type: ignore

    @property
    def icon(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the guild's icon asset, if available."""
        if self._icon is None:
            return None
        return Asset._from_guild_icon(self._state, self.id, self._icon)

    @property
    def banner(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the guild's banner asset, if available."""
        if self._banner is None:
            return None
        return Asset._from_key(self._state, self._banner)

    @property
    def splash(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the guild's invite splash asset, if available."""
        if self._splash is None:
            return None
        return Asset._from_key(self._state, self._splash)

    @property
    def discovery_splash(self) -> None:
        """Always ``None``."""
        return None

    @property
    def member_count(self) -> Optional[int]:
        """Optional[:class:`int`]: Returns the member count if available.

        This is the number of members the library loaded, or the count Bisim
        reported.
        """
        if self._chunked or self._member_count is None:
            return len(self._members) if self._members else self._member_count
        return self._member_count

    @property
    def chunked(self) -> bool:
        """:class:`bool`: Returns a boolean indicating if the guild is "chunked".

        A chunked guild means that the whole member list is loaded.
        """
        return self._chunked

    @property
    def shard_id(self) -> int:
        """:class:`int`: Always ``0``: Bisim has no sharding."""
        return 0

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the guild's creation time in UTC."""
        return self._created_at or utils.snowflake_time(self.id)

    @property
    def vanity_url(self) -> Optional[str]:
        """Optional[:class:`str`]: The Bisim vanity invite URL for this guild, if available."""
        if self.vanity_url_code is None:
            return None
        return f'{Invite.BASE}/{self.vanity_url_code}'

    @property
    def invites_paused_until(self) -> None:
        """Always ``None``."""
        return None

    @property
    def dms_paused_until(self) -> None:
        """Always ``None``."""
        return None

    def invites_paused(self) -> bool:
        """:class:`bool`: Always ``False``."""
        return False

    def dms_paused(self) -> bool:
        """:class:`bool`: Always ``False``."""
        return False

    def get_member_named(self, name: str, /) -> Optional[Member]:
        """Returns the first member found that matches the name provided.

        The name is looked up in the following order:

        - Nickname
        - Global name
        - Username

        Bisim has no discriminators; ``name#0``, as in names copied from
        Discord, is looked up as ``name``.

        If no member is found, ``None`` is returned.

        Parameters
        -----------
        name: :class:`str`
            The name of the member to lookup.

        Returns
        --------
        Optional[:class:`Member`]
            The member in this guild with the associated name. If not found
            then ``None`` is returned.
        """
        members = self.members
        username, _, discriminator = name.rpartition('#')
        if username and discriminator == '0':
            found = utils.get(members, name=username)
            if found is not None:
                return found

        def pred(m: Member) -> bool:
            return m.nick == name or m.global_name == name or m.name == name

        return utils.find(pred, members)

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def _overwrites_payload(self, overwrites: Mapping[Any, PermissionOverwrite]) -> List[Dict[str, Any]]:
        if not isinstance(overwrites, Mapping):
            raise TypeError('overwrites parameter expects a dict.')
        perms = []
        for target, perm in overwrites.items():
            if not isinstance(perm, PermissionOverwrite):
                raise TypeError(f'Expected PermissionOverwrite received {perm.__class__.__name__}')
            allow, deny = perm.pair()
            if isinstance(target, Role):
                kind = 0
            elif isinstance(target, Object) and target.type is Role:
                kind = 0
            elif isinstance(target, Object) and self.get_role(target.id) is not None:
                kind = 0
            else:
                kind = 1
            perms.append({'id': str(target.id), 'allow': str(allow.value), 'deny': str(deny.value), 'type': kind})
        return perms

    async def _create_channel(
        self,
        name: str,
        channel_type: ChannelType,
        overwrites: Mapping[Any, PermissionOverwrite] = utils.MISSING,
        category: Optional[Snowflake] = None,
        position: int = utils.MISSING,
        topic: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {'name': name, 'type': channel_type.bisim_name}
        if overwrites is not utils.MISSING:
            payload['permissionOverwrites'] = self._overwrites_payload(overwrites)
        if category is not None:
            payload['parentId'] = str(category.id)
        if position is not utils.MISSING:
            payload['position'] = int(position)
        if topic:
            payload['topic'] = topic
        return await self._state.http.create_channel(self.id, payload, reason=reason)

    def _channel_from(self, data: Dict[str, Any], cls: Any) -> Any:
        channel = cls(state=self._state, guild=self, data=data)
        self._channels[channel.id] = channel
        return channel

    async def create_text_channel(
        self,
        name: str,
        *,
        reason: Optional[str] = None,
        category: Optional[CategoryChannel] = None,
        news: bool = False,
        position: int = utils.MISSING,
        topic: str = utils.MISSING,
        slowmode_delay: int = utils.MISSING,
        nsfw: bool = utils.MISSING,
        overwrites: Mapping[Union[Role, Member, Object], PermissionOverwrite] = utils.MISSING,
        default_auto_archive_duration: int = utils.MISSING,
        default_thread_slowmode_delay: int = utils.MISSING,
    ) -> TextChannel:
        """|coro|

        Creates a :class:`TextChannel` for the guild.

        Note that you must have :attr:`~Permissions.manage_channels` to create the channel.

        The ``overwrites`` parameter can be used to create a 'secret'
        channel upon creation. This parameter expects a :class:`dict` of
        overwrites with the target (either a :class:`Member` or a :class:`Role`)
        as the key and a :class:`PermissionOverwrite` as the value.

        Examples
        ----------

        Creating a basic channel:

        .. code-block:: python3

            channel = await guild.create_text_channel('cool-channel')

        Creating a "secret" channel:

        .. code-block:: python3

            overwrites = {
                guild.default_role: bisim.PermissionOverwrite(read_messages=False),
                guild.me: bisim.PermissionOverwrite(read_messages=True)
            }

            channel = await guild.create_text_channel('secret', overwrites=overwrites)

        Parameters
        -----------
        name: :class:`str`
            The channel's name.
        overwrites: Dict[Union[:class:`Role`, :class:`Member`], :class:`PermissionOverwrite`]
            A :class:`dict` of target (either a role or a member) to
            :class:`PermissionOverwrite` to apply upon creation of a channel.
            Useful for creating secret channels.
        category: Optional[:class:`CategoryChannel`]
            The category to place the newly created channel under.
            The permissions will be automatically synced to category if no
            overwrites are provided.
        position: :class:`int`
            The position in the channel list. This is a number that starts
            at 0. e.g. the top channel is position 0.
        topic: :class:`str`
            The new channel's topic.
        slowmode_delay: :class:`int`
            Specifies the slowmode rate limit for user in this channel, in seconds.
        nsfw: :class:`bool`
            To mark the channel as NSFW or not.
        news: :class:`bool`
            Not supported on Bisim (must be ``False``).
        reason: Optional[:class:`str`]
            The reason for creating this channel. Shows up on the audit log.
        default_auto_archive_duration: :class:`int`
            Not supported on Bisim (no threads).
        default_thread_slowmode_delay: :class:`int`
            Not supported on Bisim (no threads).

        Raises
        -------
        Forbidden
            You do not have the proper permissions to create this channel.
        HTTPException
            Creating the channel failed.
        TypeError
            The permission overwrite information is not in proper form.
        NotSupported
            An option Bisim does not have was given.

        Returns
        -------
        :class:`TextChannel`
            The channel that was just created.
        """
        if news:
            raise NotSupported('Announcement channels')
        if default_auto_archive_duration is not utils.MISSING or default_thread_slowmode_delay is not utils.MISSING:
            raise NotSupported('Threads')
        data = await self._create_channel(
            name,
            ChannelType.text,
            overwrites=overwrites,
            category=category,
            position=position,
            topic=topic if topic is not utils.MISSING else None,
            reason=reason,
        )
        extra: Dict[str, Any] = {}
        if slowmode_delay is not utils.MISSING:
            extra['slowmodeSec'] = int(slowmode_delay)
        if nsfw is not utils.MISSING:
            extra['nsfw'] = bool(nsfw)
        if extra:
            data = await self._state.http.edit_channel(self.id, data['id'], reason=reason, **extra) or data
        return self._channel_from(data, TextChannel)

    async def create_voice_channel(
        self,
        name: str,
        *,
        reason: Optional[str] = None,
        category: Optional[CategoryChannel] = None,
        position: int = utils.MISSING,
        bitrate: int = utils.MISSING,
        user_limit: int = utils.MISSING,
        rtc_region: Optional[Any] = utils.MISSING,
        video_quality_mode: Any = utils.MISSING,
        overwrites: Mapping[Union[Role, Member, Object], PermissionOverwrite] = utils.MISSING,
        nsfw: bool = utils.MISSING,
    ) -> VoiceChannel:
        """|coro|

        This is similar to :meth:`create_text_channel` except makes a :class:`VoiceChannel` instead.

        Parameters
        -----------
        name: :class:`str`
            The channel's name.
        overwrites: Dict[Union[:class:`Role`, :class:`Member`], :class:`PermissionOverwrite`]
            A :class:`dict` of target (either a role or a member) to
            :class:`PermissionOverwrite` to apply upon creation of a channel.
        category: Optional[:class:`CategoryChannel`]
            The category to place the newly created channel under.
        position: :class:`int`
            The position in the channel list.
        nsfw: :class:`bool`
            To mark the channel as NSFW or not.
        bitrate: :class:`int`
            Not supported on Bisim.
        user_limit: :class:`int`
            Not supported on Bisim.
        rtc_region: Optional[:class:`str`]
            Not supported on Bisim.
        video_quality_mode: :class:`VideoQualityMode`
            Not supported on Bisim.
        reason: Optional[:class:`str`]
            The reason for creating this channel. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have the proper permissions to create this channel.
        HTTPException
            Creating the channel failed.
        TypeError
            The permission overwrite information is not in proper form.
        NotSupported
            An option Bisim does not have was given.

        Returns
        -------
        :class:`VoiceChannel`
            The channel that was just created.
        """
        for value, feature in (
            (bitrate, 'Setting a voice channel bitrate'),
            (user_limit, 'Voice channel user limits'),
            (rtc_region, 'Voice regions'),
            (video_quality_mode, 'Video quality modes'),
        ):
            if value is not utils.MISSING:
                raise NotSupported(feature)
        data = await self._create_channel(
            name, ChannelType.voice, overwrites=overwrites, category=category, position=position, reason=reason
        )
        if nsfw is not utils.MISSING:
            data = await self._state.http.edit_channel(self.id, data['id'], reason=reason, nsfw=bool(nsfw)) or data
        return self._channel_from(data, VoiceChannel)

    async def create_stage_channel(self, name: str, **options: Any) -> Any:
        """|coro|

        Not supported on Bisim (no stage channels).
        """
        raise NotSupported('Stage channels')

    async def create_category(
        self,
        name: str,
        *,
        overwrites: Mapping[Union[Role, Member, Object], PermissionOverwrite] = utils.MISSING,
        reason: Optional[str] = None,
        position: int = utils.MISSING,
    ) -> CategoryChannel:
        """|coro|

        Same as :meth:`create_text_channel` except makes a :class:`CategoryChannel` instead.

        .. note::

            The ``category`` parameter is not supported in this function since categories
            cannot have categories.

        Raises
        ------
        Forbidden
            You do not have the proper permissions to create this channel.
        HTTPException
            Creating the channel failed.
        TypeError
            The permission overwrite information is not in proper form.

        Returns
        -------
        :class:`CategoryChannel`
            The channel that was just created.
        """
        data = await self._create_channel(name, ChannelType.category, overwrites=overwrites, position=position, reason=reason)
        return self._channel_from(data, CategoryChannel)

    create_category_channel = create_category

    async def create_forum(self, name: str, **options: Any) -> Any:
        """|coro|

        Not supported on Bisim (no forum channels).
        """
        raise NotSupported('Forum channels')

    async def fetch_channels(self) -> Sequence[GuildChannel]:
        """|coro|

        Retrieves all :class:`abc.GuildChannel` that the guild has.

        .. note::

            This method is an API call. For general usage, consider :attr:`channels` instead.

        Raises
        -------
        InvalidData
            An unknown channel type was received from Bisim.
        HTTPException
            Retrieving the channels failed.

        Returns
        -------
        Sequence[:class:`abc.GuildChannel`]
            All channels in the guild.
        """
        data = await self._state.http.get_all_guild_channels(self.id)
        result = []
        for d in data or []:
            cls, _ = _guild_channel_factory(d.get('type'))
            if cls is None:
                raise InvalidData('Unknown channel type {type} for channel ID {id}.'.format_map(d))
            result.append(cls(state=self._state, guild=self, data=d))
        return result

    async def fetch_channel(self, channel_id: int, /) -> GuildChannel:
        """|coro|

        Retrieves a :class:`.abc.GuildChannel` with the specified ID.

        .. note::

            This method is an API call. For general usage, consider :meth:`get_channel` instead.

        Raises
        -------
        InvalidData
            An unknown channel type was received from Bisim
            or the guild the channel belongs to is not the same
            as the one in this object points to.
        HTTPException
            Retrieving the channel failed.
        NotFound
            Invalid Channel ID.
        Forbidden
            You do not have permission to fetch this channel.

        Returns
        --------
        :class:`.abc.GuildChannel`
            The channel from the ID.
        """
        data = await self._state.http.get_channel(channel_id)
        cls, _ = _guild_channel_factory(data.get('type'))
        if cls is None:
            raise InvalidData('Unknown channel type {type} for channel ID {id}.'.format_map(data))
        guild_id = utils._snowflake(data.get('guildId'))
        if guild_id is not None and guild_id != self.id:
            raise InvalidData('Guild ID mismatch')
        return cls(state=self._state, guild=self, data=data)

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    async def fetch_members(self, *, limit: Optional[int] = 1000, after: Optional[Union[Snowflake, datetime.datetime]] = utils.MISSING) -> AsyncIterator[Member]:
        """Retrieves an :term:`asynchronous iterator` that enables receiving the guild's members.

        .. note::

            This method is an API call. For general usage, consider :attr:`members` instead.

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The number of members to retrieve. Defaults to 1000.
            Pass ``None`` to fetch all members. Note that this is potentially slow.
        after: Optional[Union[:class:`.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve members after this date or object.

        Raises
        ------
        ClientException
            The members intent is not enabled.
        HTTPException
            Getting the members failed.

        Yields
        ------
        :class:`.Member`
            The member with the member data parsed.

        Examples
        --------

        Usage ::

            async for member in guild.fetch_members(limit=150):
                print(member.name)

        Flattening into a list ::

            members = [member async for member in guild.fetch_members(limit=150)]
            # members is now a list of Member...
        """
        if not self._state._intents.members:
            raise ClientException('Intents.members must be enabled to use this.')

        cursor: Optional[int]
        if after is utils.MISSING or after is None:
            cursor = None
        elif isinstance(after, datetime.datetime):
            cursor = utils.time_snowflake(after, high=True)
        else:
            cursor = after.id

        remaining = limit
        seen: Set[int] = set()

        def user_id_of(raw: Dict[str, Any]) -> int:
            return int(raw.get('userId') or raw['user']['id'])

        while remaining is None or remaining > 0:
            batch = 1000 if remaining is None else min(remaining, 1000)
            data = await self._state.http.get_members(self.id, limit=batch, after=cursor)
            if not data:
                return
            rows = sorted(data, key=user_id_of)
            progressed = False
            for raw in rows:
                user_id = user_id_of(raw)
                if user_id in seen or (cursor is not None and user_id <= cursor):
                    continue
                seen.add(user_id)
                progressed = True
                yield Member(data=raw, guild=self, state=self._state)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return
            # A server that ignores paging answers with everyone at once.
            if not progressed or len(data) != batch:
                return
            cursor = user_id_of(rows[-1])

    async def fetch_member(self, member_id: int, /) -> Member:
        """|coro|

        Retrieves a :class:`Member` from a guild ID, and a member ID.

        .. note::

            This method is an API call. If you have members cached, consider :meth:`get_member` instead.

        Parameters
        -----------
        member_id: :class:`int`
            The member's ID to fetch from.

        Raises
        -------
        Forbidden
            You do not have access to the guild.
        HTTPException
            Fetching the member failed.
        NotFound
            The member could not be found.

        Returns
        --------
        :class:`Member`
            The member from the member ID.
        """
        data = await self._state.http.get_member(self.id, member_id)
        return Member(data=data, guild=self, state=self._state)

    async def chunk(self, *, cache: bool = True) -> List[Member]:
        """|coro|

        Loads every member of the guild.

        Bisim sends the member list over REST, so this is a REST call
        rather than a gateway request.

        Parameters
        -----------
        cache: :class:`bool`
            Whether to cache the members as well.

        Raises
        -------
        ClientException
            The members intent is not enabled.

        Returns
        --------
        List[:class:`Member`]
            The list of members in the guild.
        """
        if not self._state._intents.members:
            raise ClientException('Intents.members must be enabled to use this.')

        members = [member async for member in self.fetch_members(limit=None)]
        if cache:
            for member in members:
                existing = self._members.get(member.id)
                if existing is not None:
                    member._status = existing._status
                    member._activity = existing._activity
                    member._custom = existing._custom
                    member.activities = existing.activities
                self._members[member.id] = member
            self._chunked = True
            self._member_count = len(self._members)
        return members

    async def query_members(
        self,
        query: Optional[str] = None,
        *,
        limit: int = 5,
        user_ids: Optional[List[int]] = None,
        presences: bool = False,
        cache: bool = True,
    ) -> List[Member]:
        """|coro|

        Request members of this guild whose username or nickname starts with the given query.

        Parameters
        -----------
        query: Optional[:class:`str`]
            The string that the username or nickname should start with.
        limit: :class:`int`
            The maximum number of members to send back. This must be
            a number between 5 and 100.
        presences: :class:`bool`
            Accepted for compatibility.
        user_ids: Optional[List[:class:`int`]]
            List of user IDs to search for. If the user ID is not in the guild then it won't be returned.
        cache: :class:`bool`
            Whether to cache the members that are returned.

        Raises
        -------
        TypeError
            Invalid parameters were passed to the function

        Returns
        --------
        List[:class:`Member`]
            The list of members that have matched the query.
        """
        if query is None:
            if query == '':
                raise ValueError('Cannot pass empty query string.')
            if user_ids is None:
                raise TypeError('Must pass either query or user_ids')
        if user_ids is not None and query is not None:
            raise TypeError('Cannot pass both query and user_ids')
        if user_ids is not None and not user_ids:
            raise ValueError('user_ids must contain at least 1 value')

        limit = min(100, limit or 5)
        members: List[Member] = []
        if user_ids is not None:
            for user_id in user_ids[:limit]:
                try:
                    member = await self.fetch_member(user_id)
                except NotFound:
                    continue
                members.append(member)
        else:
            data = await self._state.http.search_members(self.id, query or '', limit)
            members = [Member(data=d, guild=self, state=self._state) for d in data or []]
        if cache:
            for member in members:
                self._members.setdefault(member.id, member)
        return members

    async def kick(self, user: Snowflake, *, reason: Optional[str] = None) -> None:
        """|coro|

        Kicks a user from the guild.

        The user must meet the :class:`abc.Snowflake` abc.

        You must have :attr:`~Permissions.kick_members` to do this.

        Parameters
        -----------
        user: :class:`abc.Snowflake`
            The user to kick from their guild.
        reason: Optional[:class:`str`]
            The reason the user got kicked.

        Raises
        -------
        Forbidden
            You do not have the proper permissions to kick.
        HTTPException
            Kicking failed.
        """
        await self._state.http.kick(user.id, self.id, reason=reason)

    async def ban(
        self,
        user: Snowflake,
        *,
        reason: Optional[str] = None,
        delete_message_days: int = utils.MISSING,
        delete_message_seconds: int = utils.MISSING,
    ) -> None:
        """|coro|

        Bans a user from the guild.

        The user must meet the :class:`abc.Snowflake` abc.

        You must have :attr:`~Permissions.ban_members` to do this.

        Parameters
        -----------
        user: :class:`abc.Snowflake`
            The user to ban from their guild.
        delete_message_days: :class:`int`
            The number of days worth of messages to delete from the user
            in the guild. The minimum is 0 and the maximum is 7.
        delete_message_seconds: :class:`int`
            The number of seconds worth of messages to delete from the user
            in the guild. The minimum is 0 and the maximum is 604800 (7 days).
            Defaults to 1 day if neither ``delete_message_days`` nor
            ``delete_message_seconds`` are passed.
        reason: Optional[:class:`str`]
            The reason the user got banned.

        Raises
        -------
        NotFound
            The requested user was not found.
        Forbidden
            You do not have the proper permissions to ban.
        HTTPException
            Banning failed.
        TypeError
            You specified both ``delete_message_days`` and ``delete_message_seconds``.
        """
        if delete_message_days is not utils.MISSING and delete_message_seconds is not utils.MISSING:
            raise TypeError('Cannot mix delete_message_days and delete_message_seconds keyword arguments.')

        if delete_message_days is not utils.MISSING:
            delete_message_seconds = delete_message_days * 86400
        elif delete_message_seconds is utils.MISSING:
            delete_message_seconds = 86400

        await self._state.http.ban(user.id, self.id, delete_message_seconds, reason=reason)

    async def unban(self, user: Snowflake, *, reason: Optional[str] = None) -> None:
        """|coro|

        Unbans a user from the guild.

        The user must meet the :class:`abc.Snowflake` abc.

        You must have :attr:`~Permissions.ban_members` to do this.

        Parameters
        -----------
        user: :class:`abc.Snowflake`
            The user to unban.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.

        Raises
        -------
        NotFound
            The requested unban was not found.
        Forbidden
            You do not have the proper permissions to unban.
        HTTPException
            Unbanning failed.
        """
        await self._state.http.unban(user.id, self.id, reason=reason)

    async def bulk_ban(
        self,
        users: Sequence[Snowflake],
        *,
        reason: Optional[str] = None,
        delete_message_seconds: int = 86400,
    ) -> BulkBanResult:
        """|coro|

        Bans multiple users from the guild.

        The users must meet the :class:`abc.Snowflake` abc.

        You must have :attr:`~Permissions.ban_members` and
        :attr:`~Permissions.manage_guild` to do this.

        Parameters
        -----------
        users: Iterable[:class:`abc.Snowflake`]
            The users to ban from their guild, up to 200.
        delete_message_seconds: :class:`int`
            The number of seconds worth of messages to delete from the user
            in the guild. The minimum is 0 and the maximum is 604800 (7 days).
            Defaults to 1 day.
        reason: Optional[:class:`str`]
            The reason the users got banned.

        Raises
        -------
        Forbidden
            You do not have the proper permissions to ban.
        HTTPException
            Banning failed (none of the users could be banned).
        ValueError
            More than 200 users, or none, were given.

        Returns
        --------
        :class:`BulkBanResult`
            The result of the bulk ban operation.
        """
        user_ids = [u.id for u in users]
        if not user_ids:
            raise ValueError('users must have at least one user.')
        if len(user_ids) > 200:
            raise ValueError('users has a maximum of 200 elements.')
        data = await self._state.http.bulk_ban(self.id, user_ids, delete_message_seconds, reason=reason)
        banned = [Object(id=int(u), type=User) for u in (data or {}).get('bannedUsers', [])]
        failed = [Object(id=int(u), type=User) for u in (data or {}).get('failedUsers', [])]
        return BulkBanResult(banned=banned, failed=failed)

    async def fetch_ban(self, user: Snowflake) -> BanEntry:
        """|coro|

        Retrieves the :class:`BanEntry` for a user.

        You must have :attr:`~Permissions.ban_members` to get this information.

        Parameters
        -----------
        user: :class:`abc.Snowflake`
            The user to get ban information from.

        Raises
        ------
        Forbidden
            You do not have proper permissions to get the information.
        NotFound
            This user is not banned.
        HTTPException
            An error occurred while fetching the information.

        Returns
        -------
        :class:`BanEntry`
            The :class:`BanEntry` object for the specified user.
        """
        data = await self._state.http.get_ban(user.id, self.id)
        return self._ban_entry(data)

    def _ban_entry(self, data: Dict[str, Any]) -> BanEntry:
        user_data = data.get('user')
        if isinstance(user_data, dict) and user_data.get('id'):
            user = self._state.create_user(user_data)
        else:
            user_id = int(data['userId'])
            user = self._state.get_user(user_id) or self._state.create_user({'id': user_id, 'username': ''})
        return BanEntry(user=user, reason=data.get('reason') or None)

    async def bans(
        self,
        *,
        limit: Optional[int] = 1000,
        before: Snowflake = utils.MISSING,
        after: Snowflake = utils.MISSING,
    ) -> AsyncIterator[BanEntry]:
        """Retrieves an :term:`asynchronous iterator` of the users that are banned from the guild as a :class:`BanEntry`.

        You must have :attr:`~Permissions.ban_members` to get this information.

        Examples
        ---------

        Usage ::

            async for entry in guild.bans(limit=150):
                print(entry.user, entry.reason)

        Flattening into a list ::

            bans = [entry async for entry in guild.bans(limit=2000)]
            # bans is now a list of BanEntry...

        All parameters are optional.

        Parameters
        -----------
        limit: Optional[:class:`int`]
            The number of bans to retrieve. If ``None``, it retrieves every ban in
            the guild. Defaults to ``1000``.
        before: :class:`.abc.Snowflake`
            Retrieves bans before this user.
        after: :class:`.abc.Snowflake`
            Retrieve bans after this user.

        Raises
        -------
        Forbidden
            You do not have proper permissions to get the information.
        HTTPException
            An error occurred while fetching the information.
        TypeError
            Both ``after`` and ``before`` were provided, as Bisim does not
            support this type of pagination.

        Yields
        --------
        :class:`BanEntry`
            The ban entry of the banned user.
        """
        if before is not utils.MISSING and after is not utils.MISSING:
            raise TypeError('bans pagination does not support both before and after')

        data = await self._state.http.get_bans(self.id)
        entries = sorted(data or [], key=lambda d: int(d.get('userId') or d.get('user', {}).get('id') or 0))
        if before is not utils.MISSING:
            entries = [d for d in entries if int(d.get('userId') or 0) < before.id]
            entries.reverse()
        elif after is not utils.MISSING:
            entries = [d for d in entries if int(d.get('userId') or 0) > after.id]
        count = 0
        for raw in entries:
            yield self._ban_entry(raw)
            count += 1
            if limit is not None and count >= limit:
                return

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    async def fetch_roles(self) -> List[Role]:
        """|coro|

        Retrieves all :class:`Role` that the guild has.

        .. note::

            This method is an API call. For general usage, consider :attr:`roles` instead.

        Raises
        -------
        HTTPException
            Retrieving the roles failed.

        Returns
        -------
        List[:class:`Role`]
            All roles in the guild.
        """
        data = await self._state.http.get_roles(self.id)
        return [Role(guild=self, state=self._state, data=d) for d in data or []]

    async def fetch_role(self, role_id: int, /) -> Role:
        """|coro|

        Retrieves a :class:`Role` with the specified ID.

        Raises
        -------
        NotFound
            The role was not found.
        HTTPException
            Retrieving the role failed.

        Returns
        -------
        :class:`Role`
            The role.
        """
        for role in await self.fetch_roles():
            if role.id == role_id:
                return role
        from .http import _ResponseLike

        raise NotFound(_ResponseLike(404, 'Not Found'), 'Unknown role')  # type: ignore

    async def create_role(
        self,
        *,
        name: str = utils.MISSING,
        permissions: Permissions = utils.MISSING,
        color: Union[Colour, int] = utils.MISSING,
        colour: Union[Colour, int] = utils.MISSING,
        secondary_color: Any = utils.MISSING,
        secondary_colour: Any = utils.MISSING,
        tertiary_color: Any = utils.MISSING,
        tertiary_colour: Any = utils.MISSING,
        hoist: bool = utils.MISSING,
        display_icon: Any = utils.MISSING,
        mentionable: bool = utils.MISSING,
        reason: Optional[str] = None,
    ) -> Role:
        """|coro|

        Creates a :class:`Role` for the guild.

        All fields are optional.

        You must have :attr:`~Permissions.manage_roles` to do this.

        Parameters
        -----------
        name: :class:`str`
            The role name. Defaults to 'new role'.
        permissions: :class:`Permissions`
            The permissions to have. Defaults to no permissions.
        colour: Union[:class:`Colour`, :class:`int`]
            The colour for the role. Defaults to :meth:`Colour.default`.
            This is aliased to ``color`` as well.
        hoist: :class:`bool`
            Indicates if the role should be shown separately in the member list.
            Defaults to ``False``.
        display_icon: Union[:class:`bytes`, :class:`str`]
            Not supported on Bisim.
        mentionable: :class:`bool`
            Indicates if the role should be mentionable by others.
            Defaults to ``False``.
        reason: Optional[:class:`str`]
            The reason for creating this role. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to create the role.
        HTTPException
            Creating the role failed.
        TypeError
            An invalid keyword argument was given.
        NotSupported
            A display icon or a gradient colour was given.

        Returns
        --------
        :class:`Role`
            The newly created role.
        """
        if display_icon is not utils.MISSING:
            raise NotSupported('Role icons')
        for extra in (secondary_color, secondary_colour, tertiary_color, tertiary_colour):
            if extra is not utils.MISSING and extra is not None:
                raise NotSupported('Gradient role colours')
        fields: Dict[str, Any] = {}
        if permissions is not utils.MISSING:
            fields['permissions'] = str(permissions.value)
        else:
            fields['permissions'] = '0'
        actual_colour = colour if colour is not utils.MISSING else color
        if actual_colour is not utils.MISSING:
            fields['color'] = actual_colour if isinstance(actual_colour, int) else actual_colour.value
        if hoist is not utils.MISSING:
            fields['hoist'] = hoist
        if mentionable is not utils.MISSING:
            fields['mentionable'] = mentionable
        fields['name'] = name if name is not utils.MISSING else 'new role'

        data = await self._state.http.create_role(self.id, reason=reason, **fields)
        role = Role(guild=self, data=data, state=self._state)
        self._roles[role.id] = role
        return role

    async def edit_role_positions(self, positions: Mapping[Snowflake, int], *, reason: Optional[str] = None) -> List[Role]:
        """|coro|

        Bulk edits a list of :class:`Role` in the guild.

        You must have :attr:`~Permissions.manage_roles` to do this.

        Parameters
        -----------
        positions
            A :class:`dict` of :class:`Role` to :class:`int` to change the positions
            of each given role.
        reason: Optional[:class:`str`]
            The reason for editing the role positions. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to move the roles.
        HTTPException
            Moving the roles failed.
        TypeError
            An invalid keyword argument was given.

        Returns
        --------
        List[:class:`Role`]
            A list of all the roles in the guild.
        """
        if not isinstance(positions, Mapping):
            raise TypeError('positions parameter expects a dict.')
        payload = [{'id': str(role.id), 'position': int(position)} for role, position in positions.items()]
        await self._state.http.move_role_position(self.id, payload, reason=reason)
        for role, position in positions.items():
            cached = self._roles.get(role.id)
            if cached is not None:
                cached.position = int(position)
        return list(self.roles)

    # ------------------------------------------------------------------
    # Emojis and stickers
    # ------------------------------------------------------------------

    async def fetch_emojis(self) -> List[Emoji]:
        """|coro|

        Retrieves all custom :class:`Emoji` from the guild.

        .. note::

            This method is an API call. For general usage, consider :attr:`emojis` instead.

        Raises
        ---------
        HTTPException
            An error occurred fetching the emojis.

        Returns
        --------
        List[:class:`Emoji`]
            The retrieved emojis.
        """
        data = await self._state.http.get_all_custom_emojis(self.id)
        return [Emoji(guild=self, state=self._state, data=d) for d in data or []]

    async def fetch_emoji(self, emoji_id: int, /) -> Emoji:
        """|coro|

        Retrieves a custom :class:`Emoji` from the guild.

        Parameters
        -------------
        emoji_id: :class:`int`
            The emoji's ID.

        Raises
        ---------
        NotFound
            The emoji requested could not be found.
        HTTPException
            An error occurred fetching the emoji.

        Returns
        --------
        :class:`Emoji`
            The retrieved emoji.
        """
        for emoji in await self.fetch_emojis():
            if emoji.id == emoji_id:
                return emoji
        from .http import _ResponseLike

        raise NotFound(_ResponseLike(404, 'Not Found'), 'Unknown emoji')  # type: ignore

    async def create_custom_emoji(
        self,
        *,
        name: str,
        image: bytes,
        roles: Sequence[Role] = utils.MISSING,
        reason: Optional[str] = None,
    ) -> Emoji:
        r"""|coro|

        Creates a custom :class:`Emoji` for the guild.

        You must have :attr:`~Permissions.create_expressions` to do this.

        Parameters
        -----------
        name: :class:`str`
            The emoji name. Must be at least 2 characters.
        image: :class:`bytes`
            The :term:`py:bytes-like object` representing the image data to use.
            Only JPG, PNG, WEBP and GIF images are supported.
        roles: List[:class:`Role`]
            Not supported on Bisim.
        reason: Optional[:class:`str`]
            The reason for creating this emoji. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You are not allowed to create emojis.
        HTTPException
            An error occurred creating an emoji.

        Returns
        --------
        :class:`Emoji`
            The created emoji.
        """
        if roles is not utils.MISSING and roles:
            raise NotSupported('Role-locked emoji')
        content_type = utils._get_mime_type_for_image(image)
        data = await self._state.http.create_custom_emoji(self.id, name, image, content_type, reason=reason)
        emoji = Emoji(guild=self, state=self._state, data=data)
        self.emojis = self.emojis + (emoji,)
        return emoji

    async def delete_emoji(self, emoji: Snowflake, /, *, reason: Optional[str] = None) -> None:
        """|coro|

        Deletes the custom :class:`Emoji` from the guild.

        You must have :attr:`~Permissions.manage_expressions` to do this.

        Parameters
        -----------
        emoji: :class:`abc.Snowflake`
            The emoji you are deleting.
        reason: Optional[:class:`str`]
            The reason for deleting this emoji. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You are not allowed to delete emojis.
        HTTPException
            An error occurred deleting the emoji.
        """
        await self._state.http.delete_custom_emoji(self.id, emoji.id, reason=reason)

    async def fetch_stickers(self) -> List[GuildSticker]:
        """|coro|

        Retrieves a list of all :class:`GuildSticker` for the guild.

        Raises
        ---------
        HTTPException
            An error occurred fetching the stickers.

        Returns
        --------
        List[:class:`GuildSticker`]
            The retrieved stickers.
        """
        data = await self._state.http.get_all_guild_stickers(self.id)
        return [GuildSticker(state=self._state, data=d) for d in data or []]

    async def fetch_sticker(self, sticker_id: int, /) -> GuildSticker:
        """|coro|

        Retrieves a custom :class:`GuildSticker` from the guild.

        Raises
        -------
        NotFound
            The sticker requested could not be found.
        HTTPException
            An error occurred fetching the sticker.

        Returns
        --------
        :class:`GuildSticker`
            The retrieved sticker.
        """
        for sticker in await self.fetch_stickers():
            if sticker.id == sticker_id:
                return sticker
        from .http import _ResponseLike

        raise NotFound(_ResponseLike(404, 'Not Found'), 'Unknown sticker')  # type: ignore

    async def create_sticker(
        self,
        *,
        name: str,
        description: str = '',
        emoji: str = '',
        file: File,
        reason: Optional[str] = None,
    ) -> GuildSticker:
        """|coro|

        Creates a :class:`GuildSticker` for the guild.

        You must have :attr:`~Permissions.create_expressions` to do this.

        Parameters
        -----------
        name: :class:`str`
            The sticker name. Must be at least 2 characters.
        description: :class:`str`
            Accepted for compatibility (Bisim keeps no sticker description).
        emoji: :class:`str`
            Accepted for compatibility.
        file: :class:`File`
            The file of the sticker to upload.
        reason: :class:`str`
            The reason for creating this sticker. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You are not allowed to create stickers.
        HTTPException
            An error occurred creating a sticker.

        Returns
        --------
        :class:`GuildSticker`
            The created sticker.
        """
        try:
            data = file._read_all()
        finally:
            file.close()
        result = await self._state.http.create_guild_sticker(self.id, name, data, file._filename, file.content_type, reason=reason)
        sticker = GuildSticker(state=self._state, data=result)
        self.stickers = self.stickers + (sticker,)
        return sticker

    async def delete_sticker(self, sticker: Snowflake, /, *, reason: Optional[str] = None) -> None:
        """|coro|

        Deletes the custom :class:`Sticker` from the guild.

        You must have :attr:`~Permissions.manage_expressions` to do this.

        Parameters
        -----------
        sticker: :class:`abc.Snowflake`
            The sticker you are deleting.
        reason: Optional[:class:`str`]
            The reason for deleting this sticker. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You are not allowed to delete stickers.
        HTTPException
            An error occurred deleting the sticker.
        """
        await self._state.http.delete_guild_sticker(self.id, sticker.id, reason=reason)

    async def fetch_soundboard_sounds(self) -> List[SoundboardSound]:
        """|coro|

        Retrieves all the soundboard sounds of this guild.

        Raises
        -------
        HTTPException
            Retrieving the sounds failed.

        Returns
        --------
        List[:class:`SoundboardSound`]
            The guild's sounds.
        """
        data = await self._state.http.get_soundboard_sounds(self.id)
        sounds = [SoundboardSound(guild=self, state=self._state, data=d) for d in data or []]
        self._soundboard_sounds = {sound.id: sound for sound in sounds}
        return sounds

    async def fetch_soundboard_sound(self, sound_id: int, /) -> SoundboardSound:
        """|coro|

        Retrieves one of this guild's soundboard sounds.

        Parameters
        -----------
        sound_id: :class:`int`
            The ID of the sound.

        Raises
        -------
        NotFound
            The sound is not one of this guild's.
        HTTPException
            Retrieving the sound failed.

        Returns
        --------
        :class:`SoundboardSound`
            The sound.
        """
        for sound in await self.fetch_soundboard_sounds():
            if sound.id == sound_id:
                return sound
        from .http import _ResponseLike

        raise NotFound(_ResponseLike(404, 'Not Found'), 'Unknown sound')  # type: ignore

    # ------------------------------------------------------------------
    # AutoMod
    # ------------------------------------------------------------------

    async def fetch_automod_rule(self, rule_id: int, /) -> AutoModRule:
        """|coro|

        Fetches an active automod rule from the guild.

        You must have :attr:`Permissions.manage_guild` to use this.

        Parameters
        -----------
        rule_id: :class:`int`
            The ID of the automod rule to fetch.

        Raises
        -------
        Forbidden
            You do not have permission to view the automod rule.

        Returns
        --------
        :class:`AutoModRule`
            The automod rule that was fetched.
        """
        from .automod import AutoModRule

        data = await self._state.http.get_auto_moderation_rule(self.id, rule_id)
        return AutoModRule(data=data, guild=self, state=self._state)

    async def fetch_automod_rules(self) -> List[AutoModRule]:
        """|coro|

        Fetches all automod rules from the guild.

        You must have :attr:`Permissions.manage_guild` to use this.

        Raises
        -------
        Forbidden
            You do not have permission to view the automod rule.
        NotFound
            There are no automod rules within this guild.

        Returns
        --------
        List[:class:`AutoModRule`]
            The automod rules that were fetched.
        """
        from .automod import AutoModRule

        data = await self._state.http.get_auto_moderation_rules(self.id)
        return [AutoModRule(data=d, guild=self, state=self._state) for d in data or []]

    async def create_automod_rule(
        self,
        *,
        name: str,
        event_type: AutoModRuleEventType,
        trigger: AutoModTrigger,
        actions: List[AutoModRuleAction],
        enabled: bool = False,
        exempt_roles: Sequence[Snowflake] = utils.MISSING,
        exempt_channels: Sequence[Snowflake] = utils.MISSING,
        reason: str = utils.MISSING,
    ) -> AutoModRule:
        """|coro|

        Create an automod rule.

        You must have :attr:`Permissions.manage_guild` to do this.

        Bisim's triggers are keyword, keyword preset, spam, mention spam and
        member profile (a keyword rule on :attr:`AutoModRuleEventType.member_update`);
        its actions are blocking the message, an alert in a channel and a
        timeout, one of each at most.

        Parameters
        -----------
        name: :class:`str`
            The name of the automod rule.
        event_type: :class:`AutoModRuleEventType`
            The type of event that the automod rule will trigger on.
        trigger: :class:`AutoModTrigger`
            The trigger that will trigger the automod rule.
        actions: List[:class:`AutoModRuleAction`]
            The actions that will be taken when the automod rule is triggered.
        enabled: :class:`bool`
            Whether the automod rule is enabled.
            Defaults to ``False``.
        exempt_roles: Sequence[:class:`abc.Snowflake`]
            A list of roles that will be exempt from the automod rule.
        exempt_channels: Sequence[:class:`abc.Snowflake`]
            A list of channels that will be exempt from the automod rule.
        reason: :class:`str`
            The reason for creating this automod rule. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to create an automod rule.
        HTTPException
            Creating the automod rule failed.
        NotSupported
            The trigger or an action is one Bisim does not have.

        Returns
        --------
        :class:`AutoModRule`
            The automod rule that was created.
        """
        from .automod import AutoModRule, _actions_to_bisim
        from .enums import AutoModRuleActionType, AutoModRuleEventType, AutoModRuleTriggerType

        if trigger.type is AutoModRuleTriggerType.harmful_link:
            raise NotSupported('Harmful link AutoMod rules')
        if any(a.type is AutoModRuleActionType.block_member_interactions for a in actions):
            raise NotSupported('Blocking member interactions from AutoMod')
        payload: Dict[str, Any] = {
            'name': name,
            'triggerType': trigger.type.to_bisim(),
            'eventType': event_type.to_bisim(),
            'enabled': enabled,
        }
        if trigger.type is AutoModRuleTriggerType.member_profile:
            # Discord's member profile trigger is Bisim's keyword rule on member updates.
            payload['eventType'] = AutoModRuleEventType.member_update.to_bisim()
        payload.update(trigger._to_bisim())
        payload.update(_actions_to_bisim(actions))
        if exempt_roles is not utils.MISSING:
            payload['exemptRoles'] = [str(x.id) for x in exempt_roles]
        if exempt_channels is not utils.MISSING:
            payload['exemptChannels'] = [str(x.id) for x in exempt_channels]
        data = await self._state.http.create_auto_moderation_rule(
            self.id, reason=reason if reason is not utils.MISSING else None, **payload
        )
        return AutoModRule(data=data, guild=self, state=self._state)

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    async def change_voice_state(
        self, *, channel: Optional[abc.Snowflake], self_mute: Optional[bool] = None, self_deaf: Optional[bool] = None
    ) -> None:
        """|coro|

        Changes client's voice state in the guild.

        On Bisim this joins the channel over REST (or leaves it, or changes
        the bot's own mute and deafen when it stays). With a
        :class:`VoiceClient` connected here, the voice client follows: a new
        channel moves it, ``None`` disconnects it. With a voice protocol of
        your own, the join's answer reaches its
        :meth:`VoiceProtocol.on_voice_server_update`.

        Parameters
        -----------
        channel: Optional[:class:`abc.Snowflake`]
            Channel the client wants to join. Use ``None`` to disconnect.
        self_mute: Optional[:class:`bool`]
            Indicates if the client should be self-muted. Left out, it
            stays as it is (not muted on a new join).
        self_deaf: Optional[:class:`bool`]
            Indicates if the client should be self-deafened. Left out, it
            stays as it is, and a new join is deafened: Bisim joins a bot
            deafened unless it asks to hear, and a deafened bot receives no
            audio (discord.py's defaults are ``False``).
        """
        state = self._state
        voice = state._get_voice_client(self.id)
        if isinstance(voice, VoiceClient):
            await voice._change_voice_state(channel, self_mute=self_mute, self_deaf=self_deaf)
            return

        http = state.http
        # Where the server last said the bot is.
        current: Optional[int] = None
        if state.self_id is not None:
            mine = self._voice_states.get(state.self_id)
            if mine is not None and mine.channel is not None:
                current = mine.channel.id

        if channel is None:
            if current is not None:
                await http.leave_voice(current)
            return

        if channel.id == current:
            changes = {'selfMuted': self_mute, 'selfDeafened': self_deaf}
            await http.edit_voice_state(channel.id, **{k: v for k, v in changes.items() if v is not None})
            return

        data = await http.join_voice(channel.id, self_muted=bool(self_mute), self_deafened=self_deaf)
        if voice is not None:
            payload = dict(data or {})
            payload.update(guild_id=str(self.id), channel_id=str(channel.id), endpoint=payload.get('url'))
            await voice.on_voice_server_update(payload)

    # ------------------------------------------------------------------
    # Server settings
    # ------------------------------------------------------------------

    async def edit(
        self,
        *,
        reason: Optional[str] = utils.MISSING,
        name: str = utils.MISSING,
        description: Optional[str] = utils.MISSING,
        icon: Optional[bytes] = utils.MISSING,
        banner: Optional[bytes] = utils.MISSING,
        splash: Optional[bytes] = utils.MISSING,
        discovery_splash: Optional[bytes] = utils.MISSING,
        community: bool = utils.MISSING,
        afk_channel: Optional[VoiceChannel] = utils.MISSING,
        owner: Snowflake = utils.MISSING,
        afk_timeout: int = utils.MISSING,
        default_notifications: NotificationLevel = utils.MISSING,
        verification_level: VerificationLevel = utils.MISSING,
        explicit_content_filter: ContentFilter = utils.MISSING,
        vanity_code: str = utils.MISSING,
        system_channel: Optional[TextChannel] = utils.MISSING,
        system_channel_flags: SystemChannelFlags = utils.MISSING,
        preferred_locale: Locale = utils.MISSING,
        rules_channel: Optional[TextChannel] = utils.MISSING,
        public_updates_channel: Optional[TextChannel] = utils.MISSING,
        premium_progress_bar_enabled: bool = utils.MISSING,
        discoverable: bool = utils.MISSING,
        invites_disabled: bool = utils.MISSING,
        widget_enabled: bool = utils.MISSING,
        widget_channel: Optional[Snowflake] = utils.MISSING,
        mfa_level: MFALevel = utils.MISSING,
        raid_alerts_disabled: bool = utils.MISSING,
        safety_alerts_channel: Optional[TextChannel] = utils.MISSING,
        invites_disabled_until: Optional[datetime.datetime] = utils.MISSING,
        dms_disabled_until: Optional[datetime.datetime] = utils.MISSING,
    ) -> Guild:
        r"""|coro|

        Edits the guild.

        You must have :attr:`~Permissions.manage_guild` to edit the guild.

        Bisim lets a bot change the name, description, verification level,
        system channel, AFK channel and AFK timeout. The other options raise
        :exc:`NotSupported`.

        Parameters
        ----------
        name: :class:`str`
            The new name of the guild.
        description: Optional[:class:`str`]
            The new description of the guild.
        afk_channel: Optional[:class:`VoiceChannel`]
            The new channel that is the AFK channel. Could be ``None`` for no AFK channel.
        afk_timeout: :class:`int`
            The number of seconds until someone is moved to the AFK channel
            (60, 300, 900, 1800 or 3600).
        verification_level: :class:`VerificationLevel`
            The new verification level for the guild.
        system_channel: Optional[:class:`TextChannel`]
            The new channel that is used for the system channel. Could be ``None`` for no system channel.
        reason: Optional[:class:`str`]
            The reason for editing this guild. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to edit the guild.
        HTTPException
            Editing the guild failed.
        NotSupported
            An option Bisim does not have for bots was given.

        Returns
        --------
        :class:`Guild`
            The newly updated guild.
        """
        unsupported = {
            'icon': icon,
            'banner': banner,
            'splash': splash,
            'discovery_splash': discovery_splash,
            'community': community,
            'owner': owner,
            'default_notifications': default_notifications,
            'explicit_content_filter': explicit_content_filter,
            'vanity_code': vanity_code,
            'system_channel_flags': system_channel_flags,
            'preferred_locale': preferred_locale,
            'rules_channel': rules_channel,
            'public_updates_channel': public_updates_channel,
            'premium_progress_bar_enabled': premium_progress_bar_enabled,
            'discoverable': discoverable,
            'invites_disabled': invites_disabled,
            'widget_enabled': widget_enabled,
            'widget_channel': widget_channel,
            'mfa_level': mfa_level,
            'raid_alerts_disabled': raid_alerts_disabled,
            'safety_alerts_channel': safety_alerts_channel,
            'invites_disabled_until': invites_disabled_until,
            'dms_disabled_until': dms_disabled_until,
        }
        for key, value in unsupported.items():
            if value is not utils.MISSING:
                raise NotSupported(f'Changing a server\'s {key.replace("_", " ")} from a bot')

        fields: Dict[str, Any] = {}
        if name is not utils.MISSING:
            fields['name'] = name
        if description is not utils.MISSING:
            fields['description'] = description or ''
        if verification_level is not utils.MISSING:
            fields['verificationLevel'] = verification_level.value
        if system_channel is not utils.MISSING:
            fields['systemChannelId'] = str(system_channel.id) if system_channel is not None else None
        if afk_channel is not utils.MISSING:
            fields['afkChannelId'] = str(afk_channel.id) if afk_channel is not None else None
        if afk_timeout is not utils.MISSING:
            fields['afkTimeout'] = int(afk_timeout)

        data = await self._state.http.edit_guild(self.id, reason=reason if reason is not utils.MISSING else None, **fields)
        if isinstance(data, dict) and data.get('id'):
            self._from_data({k: v for k, v in data.items() if k not in ('roles', 'channels')})
        return self

    async def leave(self) -> None:
        """|coro|

        Leaves the guild.

        Raises
        --------
        HTTPException
            Leaving the guild failed.
        """
        await self._state.http.leave_guild(self.id)

    async def delete(self) -> None:
        """|coro|

        Not supported on Bisim: a bot cannot own a server.
        """
        raise NotSupported('Deleting a server as a bot')

    async def invites(self) -> List[Invite]:
        """|coro|

        Returns a list of all active instant invites from the guild.

        You must have :attr:`~Permissions.manage_guild` to get this information.

        Raises
        -------
        Forbidden
            You do not have proper permissions to get the information.
        HTTPException
            An error occurred while fetching the information.

        Returns
        -------
        List[:class:`Invite`]
            The list of invites that are currently active.
        """
        data = await self._state.http.invites_from(self.id)
        result = []
        for invite in data or []:
            channel = self.get_channel(utils._snowflake(invite.get('channelId')) or 0)
            result.append(Invite(state=self._state, data=invite, guild=self, channel=channel))
        return result

    async def webhooks(self) -> List[Webhook]:
        """|coro|

        Gets the list of webhooks from this guild.

        You must have :attr:`~.Permissions.manage_webhooks` to do this.

        Raises
        -------
        Forbidden
            You don't have permissions to get the webhooks.

        Returns
        --------
        List[:class:`Webhook`]
            The webhooks for this guild.
        """
        from .webhook import Webhook

        data = await self._state.http.guild_webhooks(self.id)
        return [Webhook.from_state(d, state=self._state) for d in data or []]

    async def vanity_invite(self) -> Optional[Invite]:
        """|coro|

        Not supported for bots on Bisim.
        """
        raise NotSupported("Reading a server's vanity invite")

    async def audit_logs(
        self,
        *,
        limit: Optional[int] = 100,
        before: Union[Snowflake, datetime.datetime] = utils.MISSING,
        after: Union[Snowflake, datetime.datetime] = utils.MISSING,
        oldest_first: bool = utils.MISSING,
        user: Snowflake = utils.MISSING,
        action: AuditLogAction = utils.MISSING,
    ) -> AsyncIterator[AuditLogEntry]:
        """Returns an :term:`asynchronous iterator` that enables receiving the guild's audit logs.

        You must have :attr:`~Permissions.view_audit_log` to do this.

        Examples
        ----------

        Getting the first 100 entries: ::

            async for entry in guild.audit_logs(limit=100):
                print(f'{entry.user} did {entry.action} to {entry.target}')

        Getting entries made by a specific user: ::

            entries = [entry async for entry in guild.audit_logs(limit=None, user=guild.me)]
            await channel.send(f'I made {len(entries)} moderation actions.')

        Parameters
        -----------
        limit: Optional[:class:`int`]
            The number of entries to retrieve. If ``None`` retrieve all entries.
        before: Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]
            Retrieve entries before this date or entry.
        after: Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]
            Retrieve entries after this date or entry.
        oldest_first: :class:`bool`
            If set to ``True``, return entries in oldest->newest order.
        user: :class:`abc.Snowflake`
            The moderator to filter entries from.
        action: :class:`AuditLogAction`
            The action to filter with.

        Raises
        -------
        Forbidden
            You are not allowed to fetch audit logs
        HTTPException
            An error occurred while fetching the audit logs.

        Yields
        --------
        :class:`AuditLogEntry`
            The audit log entry.
        """

        def as_id(value: Any, high: bool) -> Optional[int]:
            if value is utils.MISSING or value is None:
                return None
            if isinstance(value, datetime.datetime):
                return utils.time_snowflake(value, high=high)
            return value.id

        before_id = as_id(before, False)
        after_id = as_id(after, True)
        collected: List[AuditLogEntry] = []
        cursor = before_id
        remaining = limit
        while True:
            data = await self._state.http.get_audit_logs(self.id, before=cursor, limit=100)
            rows = data.get('entries') if isinstance(data, dict) else data
            if not rows:
                break
            stop = False
            for raw in rows:
                entry = AuditLogEntry(guild=self, data=raw)
                if after_id is not None and entry.id <= after_id:
                    stop = True
                    break
                if user is not utils.MISSING and entry.user_id != user.id:
                    continue
                if action is not utils.MISSING and entry.action != action:
                    continue
                collected.append(entry)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        stop = True
                        break
            if stop or len(rows) < 100:
                break
            cursor = int(rows[-1]['id'])
        if oldest_first is True or (oldest_first is utils.MISSING and after_id is not None):
            collected.reverse()
        for entry in collected:
            yield entry

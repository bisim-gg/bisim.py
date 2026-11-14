from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

from . import abc, utils
from .activity import ActivityTypes, _activity_from_presence, _custom_from_presence
from .asset import Asset
from .colour import Colour
from .enums import Status, try_enum
from .errors import ClientException, NotSupported
from .flags import MemberFlags
from .object import Object
from .permissions import Permissions
from .user import BaseUser, ClientUser, User, _UserTag

if TYPE_CHECKING:
    from typing_extensions import Self

    from .channel import DMChannel, VoiceChannel
    from .flags import PublicUserFlags
    from .guild import Guild
    from .message import Message
    from .role import Role
    from .state import ConnectionState

__all__ = (
    'VoiceState',
    'Member',
)


class VoiceState:
    """Represents a Bisim user's voice state.

    Bisim reports who is in which voice channel and what they muted. A bot
    cannot join voice itself.

    Attributes
    ------------
    deaf: :class:`bool`
        Indicates if the user is currently deafened by the guild.
    mute: :class:`bool`
        Indicates if the user is currently muted by the guild.
    self_mute: :class:`bool`
        Indicates if the user is currently muted by their own accord.
    self_deaf: :class:`bool`
        Indicates if the user is currently deafened by their own accord.
    self_stream: :class:`bool`
        Indicates if the user is currently streaming via 'Go Live' feature.
    self_video: :class:`bool`
        Indicates if the user is currently broadcasting video.
    suppress: :class:`bool`
        Always ``False``: Bisim has no stage channels.
    requested_to_speak_at: Optional[:class:`datetime.datetime`]
        Always ``None``.
    afk: :class:`bool`
        Indicates if the user is currently in the AFK channel in the guild.
    channel: Optional[:class:`VoiceChannel`]
        The voice channel that the user is currently connected to. ``None`` if
        the user is not currently in a voice channel.
    session_id: Optional[:class:`str`]
        Always ``None``.
    """

    __slots__ = (
        'session_id',
        'deaf',
        'mute',
        'self_mute',
        'self_stream',
        'self_video',
        'self_deaf',
        'afk',
        'channel',
        'requested_to_speak_at',
        'suppress',
    )

    def __init__(self, *, data: Dict[str, Any], channel: Optional[Any] = None):
        self.session_id: Optional[str] = None
        self._update(data, channel)

    def _update(self, data: Dict[str, Any], channel: Optional[Any]) -> None:
        self.self_mute: bool = bool(data.get('selfMuted', False))
        self.self_deaf: bool = bool(data.get('selfDeafened', False))
        self.self_stream: bool = bool(data.get('selfStream', False))
        self.self_video: bool = bool(data.get('selfVideo', False))
        self.mute: bool = bool(data.get('serverMuted', False))
        self.deaf: bool = bool(data.get('serverDeafened', False))
        self.suppress: bool = False
        self.requested_to_speak_at: Optional[datetime.datetime] = None
        self.channel: Optional[Any] = channel
        guild = getattr(channel, 'guild', None)
        self.afk: bool = bool(guild is not None and channel is not None and guild._afk_channel_id == channel.id)

    def __repr__(self) -> str:
        attrs = [
            ('self_mute', self.self_mute),
            ('self_deaf', self.self_deaf),
            ('self_stream', self.self_stream),
            ('suppress', self.suppress),
            ('requested_to_speak_at', self.requested_to_speak_at),
            ('channel', self.channel),
        ]
        inner = ' '.join('%s=%r' % t for t in attrs)
        return f'<{self.__class__.__name__} {inner}>'


def _member_user_data(data: Dict[str, Any]) -> Dict[str, Any]:
    user = data.get('user')
    if isinstance(user, dict) and (user.get('id') or user.get('userId')):
        return user
    # Interaction payloads flatten the user into the member.
    return {
        'id': data.get('userId') or data.get('id'),
        'username': data.get('username'),
        'displayName': data.get('displayName'),
        'avatarKey': data.get('avatarKey'),
        'bot': data.get('bot', False),
    }


class Member(abc.Messageable, _UserTag):
    """Represents a Bisim member to a :class:`Guild`.

    This implements a lot of the functionality of :class:`User`.

    .. container:: operations

        .. describe:: x == y

            Checks if two members are equal.
            Note that this works with :class:`User` instances too.

        .. describe:: x != y

            Checks if two members are not equal.
            Note that this works with :class:`User` instances too.

        .. describe:: hash(x)

            Returns the member's hash.

        .. describe:: str(x)

            Returns the member's handle (e.g. ``name``).

    Attributes
    ----------
    joined_at: Optional[:class:`datetime.datetime`]
        An aware datetime object that specifies the date and time in UTC that the member joined the guild.
    activities: Tuple[Union[:class:`BaseActivity`, :class:`Spotify`]]
        The activities that the user is currently doing.
    guild: :class:`Guild`
        The guild that the member belongs to.
    nick: Optional[:class:`str`]
        The guild specific nickname of the user.
    pending: :class:`bool`
        Always ``False``: Bisim has no membership screening.
    premium_since: Optional[:class:`datetime.datetime`]
        Always ``None``.
    timed_out_until: Optional[:class:`datetime.datetime`]
        An aware datetime object that specifies the date and time in UTC that the member's time out will expire.
        This will be set to ``None`` if the user is not timed out.
    """

    __slots__ = (
        '_roles',
        'joined_at',
        'premium_since',
        'activities',
        'guild',
        'pending',
        'nick',
        'timed_out_until',
        '_permissions',
        '_status',
        '_user',
        '_state',
        '_activity',
        '_custom',
        '__weakref__',
    )

    if TYPE_CHECKING:
        name: str
        id: int
        discriminator: str
        global_name: Optional[str]
        bot: bool
        system: bool
        created_at: datetime.datetime
        default_avatar: Asset
        avatar: Optional[Asset]
        dm_channel: Optional[DMChannel]
        create_dm = User.create_dm
        mutual_guilds: List[Guild]
        public_flags: PublicUserFlags
        banner: Optional[Asset]
        accent_color: Optional[Colour]
        accent_colour: Optional[Colour]

    def __init__(self, *, data: Dict[str, Any], guild: Guild, state: ConnectionState):
        self._state: ConnectionState = state
        self.guild: Guild = guild
        self._user: User = state.store_user(_member_user_data(data))
        self.joined_at: Optional[datetime.datetime] = utils.parse_time(data.get('joinedAt'))
        self.premium_since: Optional[datetime.datetime] = None
        self.pending: bool = False
        self._status: str = 'offline'
        self._activity: Optional[ActivityTypes] = None
        self._custom: Optional[ActivityTypes] = None
        self.activities: Tuple[ActivityTypes, ...] = ()
        self._permissions: Optional[int] = None
        self._update(data)

    def __str__(self) -> str:
        return str(self._user)

    def __repr__(self) -> str:
        return (
            f'<Member id={self._user.id} name={self._user.name!r} global_name={self._user.global_name!r}'
            f' bot={self._user.bot} nick={self.nick!r} guild={self.guild!r}>'
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _UserTag) and other.id == self.id

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self._user)

    def _update(self, data: Dict[str, Any]) -> None:
        if 'nickname' in data or 'nick' in data:
            self.nick: Optional[str] = data.get('nickname', data.get('nick')) or None
        elif not hasattr(self, 'nick'):
            self.nick = None
        guild_id = self.guild.id
        role_ids = data.get('roleIds', data.get('roles'))
        if role_ids is not None or not hasattr(self, '_roles'):
            self._roles: utils.SnowflakeList = utils.SnowflakeList(
                int(r) for r in (role_ids or ()) if r not in (None, '') and int(r) != guild_id
            )
        if 'timeoutUntil' in data or not hasattr(self, 'timed_out_until'):
            self.timed_out_until: Optional[datetime.datetime] = utils.parse_time(data.get('timeoutUntil'))
        if 'joinedAt' in data and data.get('joinedAt'):
            self.joined_at = utils.parse_time(data['joinedAt'])
        if 'permissions' in data and data['permissions'] not in (None, ''):
            self._permissions = int(data['permissions'])

    def _update_from_event(self, data: Dict[str, Any]) -> None:
        """Applies a member event, where a missing field means "empty" (proto3-JSON)."""
        self.nick = data.get('nickname') or None
        guild_id = self.guild.id
        self._roles = utils.SnowflakeList(int(r) for r in (data.get('roleIds') or ()) if r and int(r) != guild_id)
        self.timed_out_until = utils.parse_time(data.get('timeoutUntil'))
        if data.get('joinedAt'):
            self.joined_at = utils.parse_time(data['joinedAt'])
        user = data.get('user')
        if isinstance(user, dict) and user:
            self._user._patch(user)

    def _presence_update(self, data: Dict[str, Any]) -> None:
        status = data.get('status') or 'offline'
        self._status = 'offline' if status == 'invisible' else status
        self._activity = _activity_from_presence(data.get('activityType'), data.get('activityName'))
        self._custom = _custom_from_presence(data.get('customText'), data.get('customEmoji'))
        self.activities = tuple(a for a in (self._activity, self._custom) if a is not None)

    @classmethod
    def _copy(cls, member: Member) -> Self:
        self = cls.__new__(cls)
        self._roles = utils.SnowflakeList(member._roles, is_sorted=True)
        self.joined_at = member.joined_at
        self.premium_since = member.premium_since
        self._status = member._status
        self._activity = member._activity
        self._custom = member._custom
        self.activities = member.activities
        self.guild = member.guild
        self.nick = member.nick
        self.pending = member.pending
        self.timed_out_until = member.timed_out_until
        self._permissions = member._permissions
        self._state = member._state
        # The user is copied too, so a before/after pair keeps the old name.
        self._user = User._copy(member._user)
        return self

    async def _get_channel(self) -> DMChannel:
        ch = await self.create_dm()
        return ch

    # -- Proxied user attributes -------------------------------------------

    @property
    def name(self) -> str:
        return self._user.name

    @property
    def id(self) -> int:  # type: ignore[override]
        return self._user.id

    @property
    def discriminator(self) -> str:
        return self._user.discriminator

    @property
    def global_name(self) -> Optional[str]:
        return self._user.global_name

    @property
    def bot(self) -> bool:
        return self._user.bot

    @property
    def system(self) -> bool:
        return self._user.system

    @property
    def created_at(self) -> datetime.datetime:
        return self._user.created_at

    @property
    def default_avatar(self) -> Asset:
        return self._user.default_avatar

    @property
    def avatar(self) -> Optional[Asset]:
        return self._user.avatar

    @property
    def banner(self) -> Optional[Asset]:
        return self._user.banner

    @property
    def accent_colour(self) -> Optional[Colour]:
        return None

    @property
    def accent_color(self) -> Optional[Colour]:
        return None

    @property
    def public_flags(self) -> PublicUserFlags:
        return self._user.public_flags

    @property
    def avatar_decoration(self) -> Optional[Asset]:
        return None

    @property
    def dm_channel(self) -> Optional[DMChannel]:
        return self._user.dm_channel

    @property
    def mutual_guilds(self) -> List[Guild]:
        return self._user.mutual_guilds

    async def create_dm(self) -> DMChannel:
        """|coro|

        Creates a :class:`DMChannel` with this member.

        Returns
        -------
        :class:`.DMChannel`
            The channel that was created.
        """
        return await self._user.create_dm()

    # -- Member attributes ---------------------------------------------------

    @property
    def status(self) -> Status:
        """:class:`Status`: The member's overall status. If the value is unknown, then it will be a :class:`str` instead."""
        return try_enum(Status, self._status)

    @property
    def raw_status(self) -> str:
        """:class:`str`: The member's overall status as a string value."""
        return self._status

    @status.setter
    def status(self, value: Status) -> None:
        self._status = str(value)

    @property
    def mobile_status(self) -> Status:
        """:class:`Status`: Bisim does not report per device; this is :attr:`status`."""
        return self.status

    @property
    def desktop_status(self) -> Status:
        """:class:`Status`: Bisim does not report per device; this is :attr:`status`."""
        return self.status

    @property
    def web_status(self) -> Status:
        """:class:`Status`: Bisim does not report per device; this is :attr:`status`."""
        return self.status

    def is_on_mobile(self) -> bool:
        """:class:`bool`: Always ``False``: Bisim does not report the device."""
        return False

    @property
    def colour(self) -> Colour:
        """:class:`Colour`: A property that returns a colour denoting the rendered colour
        for the member. If the default colour is the one rendered then an instance
        of :meth:`Colour.default` is returned.

        There is an alias for this named :attr:`color`.
        """
        roles = self.roles[1:]  # remove @everyone
        for role in reversed(roles):
            if role.colour.value:
                return role.colour
        return Colour.default()

    @property
    def color(self) -> Colour:
        """:class:`Colour`: A property that returns a color denoting the rendered color for
        the member. If the default color is the one rendered then an instance of :meth:`Colour.default`
        is returned.

        There is an alias for this named :attr:`colour`.
        """
        return self.colour

    @property
    def roles(self) -> List[Role]:
        """List[:class:`Role`]: A :class:`list` of :class:`Role` that the member belongs to. Note
        that the first element of this list is always the default '@everyone'
        role.

        These roles are sorted by their position in the role hierarchy.
        """
        result = []
        guild = self.guild
        for role_id in self._roles:
            role = guild.get_role(role_id)
            if role:
                result.append(role)
        default = guild.default_role
        if default is not None:
            result.append(default)
        result.sort()
        return result

    @property
    def display_icon(self) -> Optional[Union[str, Asset]]:
        """Optional[Union[:class:`str`, :class:`Asset`]]: Not on Bisim."""
        return None

    @property
    def mention(self) -> str:
        """:class:`str`: Returns a string that allows you to mention the member."""
        return f'<@{self._user.id}>'

    @property
    def display_name(self) -> str:
        """:class:`str`: Returns the user's display name.

        For regular users this is just their global name or their username,
        but if they have a guild specific nickname then that
        is returned instead.
        """
        return self.nick or self.global_name or self.name

    @property
    def display_avatar(self) -> Asset:
        """:class:`Asset`: Returns the member's display avatar.

        Bisim has no per-server avatars, so this is the user's avatar or
        their default avatar.
        """
        return self._user.display_avatar

    @property
    def guild_avatar(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Not on Bisim."""
        return None

    @property
    def guild_banner(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Not on Bisim."""
        return None

    @property
    def activity(self) -> Optional[ActivityTypes]:
        """Optional[Union[:class:`BaseActivity`, :class:`Spotify`]]: Returns the primary
        activity the user is currently doing. Could be ``None`` if no activity is being done.
        """
        if self.activities:
            return self.activities[0]
        return None

    def mentioned_in(self, message: Message) -> bool:
        """Checks if the member is mentioned in the specified message.

        Parameters
        -----------
        message: :class:`Message`
            The message to check if you're mentioned in.

        Returns
        -------
        :class:`bool`
            Indicates if the member is mentioned in the message.
        """
        if message.guild is None or message.guild.id != self.guild.id:
            return False
        if self._user.mentioned_in(message):
            return True
        return any(self._roles.has(role_id) for role_id in message.raw_role_mentions)

    @property
    def top_role(self) -> Role:
        """:class:`Role`: Returns the member's highest role.

        This is useful for figuring where a member stands in the role
        hierarchy chain.
        """
        guild = self.guild
        if len(self._roles) == 0:
            return guild.default_role  # type: ignore

        roles = [r for r in (guild.get_role(rid) for rid in self._roles) if r is not None]
        if not roles:
            return guild.default_role  # type: ignore
        return max(roles)

    @property
    def guild_permissions(self) -> Permissions:
        """:class:`Permissions`: Returns the member's guild permissions.

        This only takes into consideration the guild permissions
        and not most of the implied permissions or any of the
        channel permission overwrites. For 100% accurate permission
        calculation, please use :meth:`abc.GuildChannel.permissions_for`.

        This does take into consideration guild ownership, the
        administrator implication, and whether the member is timed out.
        """
        guild = self.guild
        state = self._state
        if (
            state.self_id is not None
            and self.id == state.self_id
            and guild._my_permissions is not None
            and guild._my_role_ids == set(self._roles)
        ):
            base = Permissions(guild._my_permissions)
            if base.administrator:
                return Permissions.all()
            return base

        if guild.owner_id == self.id:
            return Permissions.all()

        base = Permissions.none()
        for role in self.roles:
            base.value |= role._permissions

        if base.administrator:
            return Permissions.all()

        if self.is_timed_out():
            base.value &= Permissions._timeout_mask()

        return base

    @property
    def resolved_permissions(self) -> Optional[Permissions]:
        """Optional[:class:`Permissions`]: Returns the member's resolved permissions
        from an interaction.

        This is only available in interaction contexts and represents the resolved
        permissions of the member in the channel the interaction was executed in.
        This is more or less equivalent to calling :meth:`abc.GuildChannel.permissions_for`
        but stored and returned as an attribute by Bisim rather than computed.
        """
        if self._permissions is None:
            return None
        return Permissions(self._permissions)

    @property
    def voice(self) -> Optional[VoiceState]:
        """Optional[:class:`VoiceState`]: Returns the member's current voice state."""
        return self.guild._voice_state_for(self._user.id)

    @property
    def flags(self) -> MemberFlags:
        """:class:`MemberFlags`: Returns the member's flags."""
        return MemberFlags._from_value(0)

    def is_timed_out(self) -> bool:
        """Returns whether this member is timed out.

        Returns
        --------
        :class:`bool`
            ``True`` if the member is timed out. ``False`` otherwise.
        """
        if self.timed_out_until is not None:
            return utils.utcnow() < self.timed_out_until
        return False

    def get_role(self, role_id: int, /) -> Optional[Role]:
        """Returns a role with the given ID from roles which the member has.

        Parameters
        -----------
        role_id: :class:`int`
            The ID to search for.

        Returns
        --------
        Optional[:class:`Role`]
            The role or ``None`` if not found in the member's roles.
        """
        return self.guild.get_role(role_id) if self._roles.has(role_id) else None

    async def ban(
        self,
        *,
        delete_message_days: int = utils.MISSING,
        delete_message_seconds: int = utils.MISSING,
        reason: Optional[str] = None,
    ) -> None:
        """|coro|

        Bans this member. Equivalent to :meth:`Guild.ban`.
        """
        await self.guild.ban(
            self,
            reason=reason,
            delete_message_days=delete_message_days,
            delete_message_seconds=delete_message_seconds,
        )

    async def unban(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Unbans this member. Equivalent to :meth:`Guild.unban`.
        """
        await self.guild.unban(self, reason=reason)

    async def kick(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Kicks this member. Equivalent to :meth:`Guild.kick`.
        """
        await self.guild.kick(self, reason=reason)

    async def edit(
        self,
        *,
        nick: Optional[str] = utils.MISSING,
        mute: bool = utils.MISSING,
        deafen: bool = utils.MISSING,
        suppress: bool = utils.MISSING,
        roles: Sequence[abc.Snowflake] = utils.MISSING,
        voice_channel: Optional[abc.Snowflake] = utils.MISSING,
        timed_out_until: Optional[datetime.datetime] = utils.MISSING,
        bypass_verification: bool = utils.MISSING,
        reason: Optional[str] = None,
    ) -> Optional[Member]:
        """|coro|

        Edits the member's data.

        Depending on the parameter passed, this requires different permissions listed below:

        +---------------------+--------------------------------------+
        |   Parameter         |              Permission              |
        +---------------------+--------------------------------------+
        | nick                | :attr:`Permissions.manage_nicknames` |
        +---------------------+--------------------------------------+
        | mute                | :attr:`Permissions.mute_members`     |
        +---------------------+--------------------------------------+
        | deafen              | :attr:`Permissions.deafen_members`   |
        +---------------------+--------------------------------------+
        | roles               | :attr:`Permissions.manage_roles`     |
        +---------------------+--------------------------------------+
        | voice_channel       | :attr:`Permissions.move_members`     |
        +---------------------+--------------------------------------+
        | timed_out_until     | :attr:`Permissions.moderate_members` |
        +---------------------+--------------------------------------+

        All parameters are optional.

        Server mute, deafen and moving apply to the voice channel the member
        is in, so the member must be connected for those.

        Parameters
        -----------
        nick: Optional[:class:`str`]
            The member's new nickname. Use ``None`` to remove the nickname.
        mute: :class:`bool`
            Indicates if the member should be guild muted or un-muted.
        deafen: :class:`bool`
            Indicates if the member should be guild deafened or un-deafened.
        suppress: :class:`bool`
            Not supported on Bisim (no stage channels).
        roles: List[:class:`Role`]
            The member's new list of roles. This *replaces* the roles.
        voice_channel: Optional[:class:`VoiceChannel`]
            The voice channel to move the member to.
            Pass ``None`` to kick them from voice.
        timed_out_until: Optional[:class:`datetime.datetime`]
            The date the member's timeout should expire, or ``None`` to remove the timeout.
            This must be a timezone-aware datetime object. Consider using :func:`utils.utcnow`.
        bypass_verification: :class:`bool`
            Not supported on Bisim.
        reason: Optional[:class:`str`]
            The reason for editing this member. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have the proper permissions to the action requested.
        HTTPException
            The operation failed.
        TypeError
            The datetime object passed to ``timed_out_until`` was not timezone-aware.
        ClientException
            Mute, deafen or a move was asked for a member who is not in voice.

        Returns
        --------
        Optional[:class:`.Member`]
            The newly updated member, if applicable.
        """
        http = self._state.http
        guild_id = self.guild.id
        me = self._state.self_id == self.id
        if suppress is not utils.MISSING:
            raise NotSupported('Suppressing a member (stage channels)')
        if bypass_verification is not utils.MISSING:
            raise NotSupported('Bypassing verification')

        payload: Dict[str, Any] = {}
        if nick is not utils.MISSING:
            if me:
                await http.change_my_nickname(guild_id, nick, reason=reason)
            else:
                payload['nickname'] = nick or None

        if roles is not utils.MISSING:
            payload['roleIds'] = [str(r.id) for r in roles if r.id != guild_id]

        data: Any = None
        if payload:
            data = await http.edit_member(guild_id, self.id, reason=reason, **payload)

        if timed_out_until is not utils.MISSING:
            await self._set_timeout(timed_out_until, reason=reason)

        if mute is not utils.MISSING or deafen is not utils.MISSING:
            state = self.voice
            if state is None or state.channel is None:
                raise ClientException('Member is not connected to a voice channel.')
            fields: Dict[str, Any] = {}
            if mute is not utils.MISSING:
                fields['mute'] = bool(mute)
            if deafen is not utils.MISSING:
                fields['deafen'] = bool(deafen)
            await http.edit_voice_member(state.channel.id, self.id, **fields)

        if voice_channel is not utils.MISSING:
            await self.move_to(voice_channel, reason=reason)

        if isinstance(data, dict) and (data.get('userId') or data.get('user')):
            self._update(data)
            return self
        return None

    async def _set_timeout(self, until: Optional[datetime.datetime], *, reason: Optional[str]) -> None:
        if until is None:
            iso = None
        else:
            if until.tzinfo is None:
                raise TypeError(
                    'timed_out_until must be an aware datetime. Consider using bisim.utils.utcnow() or datetime.datetime.now().astimezone() for local time.'
                )
            iso = utils._isoformat(until)
        await self._state.http.timeout_member(self.guild.id, self.id, iso, reason=reason)
        self.timed_out_until = until

    async def request_to_speak(self) -> None:
        """|coro|

        Not supported on Bisim (no stage channels).
        """
        raise NotSupported('Stage channels')

    async def move_to(self, channel: Optional[abc.Snowflake], *, reason: Optional[str] = None) -> None:
        """|coro|

        Moves a member to a new voice channel (they must be connected first).

        You must have :attr:`~Permissions.move_members` to do this.

        Parameters
        -----------
        channel: Optional[:class:`VoiceChannel`]
            The new voice channel to move the member to.
            Pass ``None`` to kick them from voice.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.
        """
        state = self.voice
        if state is None or state.channel is None:
            raise ClientException('Member is not connected to a voice channel.')
        if channel is None:
            await self._state.http.disconnect_voice_member(state.channel.id, self.id)
        else:
            await self._state.http.move_voice_member(state.channel.id, self.id, channel.id)

    async def timeout(
        self, until: Optional[Union[datetime.timedelta, datetime.datetime]], /, *, reason: Optional[str] = None
    ) -> None:
        """|coro|

        Applies a time out to a member until the specified date time or for the
        given :class:`datetime.timedelta`.

        You must have :attr:`~Permissions.moderate_members` to do this.

        This raises the same exceptions as :meth:`edit`.

        Parameters
        -----------
        until: Optional[Union[:class:`datetime.timedelta`, :class:`datetime.datetime`]]
            If this is a :class:`datetime.timedelta` then it represents the amount of
            time the member should be timed out for. If this is a :class:`datetime.datetime`
            then it's when the member's timeout should expire. If ``None`` is passed then the
            timeout is removed. Note that the API only allows for timeouts up to 28 days.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.

        Raises
        -------
        TypeError
            The ``until`` parameter was the wrong type or the datetime was not timezone-aware.
        """
        if until is None:
            timed_out_until = None
        elif isinstance(until, datetime.timedelta):
            timed_out_until = utils.utcnow() + until
        elif isinstance(until, datetime.datetime):
            timed_out_until = until
        else:
            raise TypeError(f'expected None, datetime.datetime, or datetime.timedelta not {until.__class__.__name__}')
        await self._set_timeout(timed_out_until, reason=reason)

    async def add_roles(self, *roles: abc.Snowflake, reason: Optional[str] = None, atomic: bool = True) -> None:
        r"""|coro|

        Gives the member a number of :class:`Role`\s.

        You must have :attr:`~Permissions.manage_roles` to
        use this, and the added :class:`Role`\s must appear lower in the list
        of roles than the highest role of the client.

        Parameters
        -----------
        \*roles: :class:`abc.Snowflake`
            An argument list of :class:`abc.Snowflake` representing a :class:`Role`
            to give to the member.
        reason: Optional[:class:`str`]
            The reason for adding these roles. Shows up on the audit log.
        atomic: :class:`bool`
            Whether to atomically add roles. This will ensure that multiple
            operations will always be applied regardless of the current
            state of the cache.

        Raises
        -------
        Forbidden
            You do not have permissions to add these roles.
        HTTPException
            Adding roles failed.
        """
        if not atomic:
            new_roles = utils._unique(Object(id=r.id) for s in (self.roles[1:], roles) for r in s)
            await self.edit(roles=new_roles, reason=reason)
            return
        http = self._state.http
        guild_id = self.guild.id
        user_id = self.id
        for role in roles:
            await http.add_role(guild_id, user_id, role.id, reason=reason)
            self._roles.add(role.id)

    async def remove_roles(self, *roles: abc.Snowflake, reason: Optional[str] = None, atomic: bool = True) -> None:
        r"""|coro|

        Removes :class:`Role`\s from this member.

        You must have :attr:`~Permissions.manage_roles` to
        use this, and the removed :class:`Role`\s must appear lower in the list
        of roles than the highest role of the client.

        Parameters
        -----------
        \*roles: :class:`abc.Snowflake`
            An argument list of :class:`abc.Snowflake` representing a :class:`Role`
            to remove from the member.
        reason: Optional[:class:`str`]
            The reason for removing these roles. Shows up on the audit log.
        atomic: :class:`bool`
            Whether to atomically remove roles. This will ensure that multiple
            operations will always be applied regardless of the current
            state of the cache.

        Raises
        -------
        Forbidden
            You do not have permissions to remove these roles.
        HTTPException
            Removing the roles failed.
        """
        if not atomic:
            remove = {r.id for r in roles}
            new_roles = [Object(id=r.id) for r in self.roles[1:] if r.id not in remove]
            await self.edit(roles=new_roles, reason=reason)
            return
        http = self._state.http
        guild_id = self.guild.id
        user_id = self.id
        for role in roles:
            await http.remove_role(guild_id, user_id, role.id, reason=reason)
            self._roles.discard(role.id)

    async def fetch_voice(self) -> VoiceState:
        """|coro|

        Retrieves the current :class:`VoiceState` for this member.

        Raises
        -------
        NotFound
            The member is not in a voice channel.
        HTTPException
            Retrieving the voice state failed.

        Returns
        --------
        :class:`VoiceState`
            The voice state of the member.
        """
        data = await self._state.http.get_guild_voice_states(self.guild.id)
        self.guild._load_voice_states(data)
        state = self.voice
        if state is None:
            from .errors import NotFound
            from .http import _ResponseLike

            raise NotFound(_ResponseLike(404, 'Not Found'), 'Member is not in a voice channel')  # type: ignore
        return state

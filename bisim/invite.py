from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from . import utils
from .asset import Asset
from .enums import ChannelType, InviteTarget, InviteType, VerificationLevel, try_enum
from .mixins import Hashable
from .object import Object

if TYPE_CHECKING:
    from .abc import GuildChannel
    from .guild import Guild
    from .state import ConnectionState
    from .user import User

__all__ = (
    'PartialInviteChannel',
    'PartialInviteGuild',
    'Invite',
)


class PartialInviteChannel:
    """Represents a "partial" invite channel.

    This model will be given when the user is not part of the
    guild the :class:`Invite` resolves to.

    Attributes
    -----------
    name: :class:`str`
        The partial channel's name.
    id: :class:`int`
        The partial channel's ID.
    type: :class:`ChannelType`
        The partial channel's type.
    """

    __slots__ = ('id', 'name', 'type')

    def __init__(self, data: Dict[str, Any]):
        self.id: int = int(data['id'])
        self.name: str = data.get('name') or ''
        self.type: ChannelType = ChannelType.from_bisim(data.get('type', 'GUILD_TEXT'))

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<PartialInviteChannel id={self.id} name={self.name} type={self.type!r}>'

    @property
    def mention(self) -> str:
        """:class:`str`: The string that allows you to mention the channel."""
        return f'<#{self.id}>'

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the channel's creation time in UTC."""
        return utils.snowflake_time(self.id)


class PartialInviteGuild:
    """Represents a "partial" invite guild.

    This model will be given when the user is not part of the
    guild the :class:`Invite` resolves to.

    Attributes
    -----------
    name: :class:`str`
        The partial guild's name.
    id: :class:`int`
        The partial guild's ID.
    verification_level: :class:`VerificationLevel`
        The partial guild's verification level.
    features: List[:class:`str`]
        Always empty on Bisim.
    description: Optional[:class:`str`]
        The partial guild's description.
    """

    __slots__ = ('_state', 'features', '_icon', '_splash', 'id', 'name', 'verification_level', 'description', 'nsfw_level')

    def __init__(self, state: ConnectionState, data: Dict[str, Any], id: int):
        self._state: ConnectionState = state
        self.id: int = id
        self.name: str = data.get('name') or ''
        self.features: List[str] = []
        self._icon: Optional[str] = data.get('iconKey') or None
        self._splash: Optional[str] = data.get('splashKey') or None
        self.verification_level: VerificationLevel = try_enum(VerificationLevel, utils._int(data.get('verificationLevel'), 0))
        self.description: Optional[str] = data.get('description') or None
        self.nsfw_level: Any = None

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} id={self.id} name={self.name!r} features={self.features}>'

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the guild's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def icon(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the guild's icon asset, if available."""
        if self._icon is None:
            return None
        return Asset._from_guild_icon(self._state, self.id, self._icon)

    @property
    def banner(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Not available from an invite on Bisim."""
        return None

    @property
    def splash(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the guild's invite splash asset, if available."""
        if self._splash is None:
            return None
        return Asset._from_key(self._state, self._splash)


class Invite(Hashable):
    r"""Represents a Bisim :class:`Guild` or :class:`abc.GuildChannel` invite.

    Depending on the way this object was created, some of the attributes can
    have a value of ``None``.

    .. container:: operations

        .. describe:: x == y

            Checks if two invites are equal.

        .. describe:: x != y

            Checks if two invites are not equal.

        .. describe:: hash(x)

            Returns the invite hash.

        .. describe:: str(x)

            Returns the invite URL.

    Attributes
    -----------
    type: :class:`InviteType`
        The type of invite.
    max_age: Optional[:class:`int`]
        How long before the invite expires in seconds.
        A value of ``0`` indicates that it doesn't expire.
    code: :class:`str`
        The URL fragment used for the invite.
    guild: Optional[Union[:class:`Guild`, :class:`Object`, :class:`PartialInviteGuild`]]
        The guild the invite is for.
    revoked: Optional[:class:`bool`]
        Always ``False``: a revoked Bisim invite no longer exists.
    created_at: Optional[:class:`datetime.datetime`]
        An aware UTC datetime object denoting the time the invite was created.
    temporary: Optional[:class:`bool`]
        Always ``False`` on Bisim.
    uses: Optional[:class:`int`]
        How many times the invite has been used.
    max_uses: Optional[:class:`int`]
        How many times the invite can be used.
        A value of ``0`` indicates that it has unlimited uses.
    inviter: Optional[:class:`User`]
        The user who created the invite.
    approximate_member_count: Optional[:class:`int`]
        The approximate number of members in the guild.
    approximate_presence_count: Optional[:class:`int`]
        The approximate number of members currently active in the guild.
    expires_at: Optional[:class:`datetime.datetime`]
        The expiration date of the invite. If the value is ``None`` the invite
        will never expire.
    channel: Optional[Union[:class:`abc.GuildChannel`, :class:`Object`, :class:`PartialInviteChannel`]]
        The channel the invite is for.
    target_type: :class:`InviteTarget`
        Always :attr:`InviteTarget.unknown`.
    target_user: Optional[:class:`User`]
        Always ``None``.
    target_application: Optional[Any]
        Always ``None``.
    """

    __slots__ = (
        'max_age',
        'code',
        'guild',
        'revoked',
        'created_at',
        'uses',
        'temporary',
        'max_uses',
        'inviter',
        'channel',
        'target_user',
        'target_type',
        '_state',
        'approximate_member_count',
        'approximate_presence_count',
        'target_application',
        'expires_at',
        'scheduled_event',
        'scheduled_event_id',
        'type',
    )

    BASE = 'https://bisim.gg'

    def __init__(
        self,
        *,
        state: ConnectionState,
        data: Dict[str, Any],
        guild: Optional[Union[PartialInviteGuild, Guild, Object]] = None,
        channel: Optional[Union[PartialInviteChannel, GuildChannel, Object]] = None,
    ):
        self._state: ConnectionState = state
        self.type: InviteType = InviteType.guild
        self.code: str = data['code']
        self.max_age: Optional[int] = data.get('maxAgeSec') if 'maxAgeSec' in data else None
        if self.max_age is None and 'maxAgeSec' in data:
            self.max_age = 0
        self.max_uses: Optional[int] = data.get('maxUses') if 'maxUses' in data else None
        if self.max_uses is None and 'maxUses' in data:
            self.max_uses = 0
        self.uses: Optional[int] = data.get('uses')
        self.revoked: Optional[bool] = False
        self.created_at: Optional[datetime.datetime] = utils.parse_time(data.get('createdAt'))
        self.temporary: Optional[bool] = False
        self.approximate_member_count: Optional[int] = data.get('memberCount')
        self.approximate_presence_count: Optional[int] = data.get('onlineCount')
        self.expires_at: Optional[datetime.datetime] = utils.parse_time(data.get('expiresAt'))

        inviter_data = data.get('inviter')
        self.inviter: Optional[User] = None
        if isinstance(inviter_data, dict) and inviter_data.get('id'):
            self.inviter = state.create_user(inviter_data)
        elif data.get('inviterId'):
            self.inviter = state.get_user(int(data['inviterId']))

        self.guild: Optional[Union[PartialInviteGuild, Guild, Object]] = self._resolve_guild(data, guild)
        self.channel: Optional[Union[PartialInviteChannel, GuildChannel, Object]] = self._resolve_channel(data, channel)

        self.target_type: InviteTarget = InviteTarget.unknown
        self.target_user: Optional[User] = None
        self.target_application: Optional[Any] = None
        self.scheduled_event: Optional[Any] = None
        self.scheduled_event_id: Optional[int] = None

    @classmethod
    def from_incomplete(cls, *, state: ConnectionState, data: Dict[str, Any]) -> Invite:
        guild_id = utils._snowflake(data.get('guildId'))
        guild: Optional[Union[Guild, Object]] = None
        channel: Optional[Any] = None
        if guild_id is not None:
            guild = state._get_guild(guild_id) or Object(id=guild_id)
        channel_id = utils._snowflake(data.get('channelId'))
        if channel_id is not None:
            found = guild.get_channel(channel_id) if guild is not None and hasattr(guild, 'get_channel') else None  # type: ignore
            channel = found or Object(id=channel_id)
        return cls(state=state, data=data, guild=guild, channel=channel)

    def _resolve_guild(
        self,
        data: Dict[str, Any],
        guild: Optional[Union[PartialInviteGuild, Guild, Object]] = None,
    ) -> Optional[Union[PartialInviteGuild, Guild, Object]]:
        if guild is not None:
            return guild

        guild_data = data.get('guild')
        if isinstance(guild_data, dict) and guild_data.get('id'):
            guild_id = int(guild_data['id'])
            cached = self._state._get_guild(guild_id)
            return cached or PartialInviteGuild(self._state, guild_data, guild_id)

        guild_id = utils._snowflake(data.get('guildId'))
        if guild_id is None:
            return None
        return self._state._get_guild(guild_id) or Object(id=guild_id)

    def _resolve_channel(
        self,
        data: Dict[str, Any],
        channel: Optional[Union[PartialInviteChannel, GuildChannel, Object]] = None,
    ) -> Optional[Union[PartialInviteChannel, GuildChannel, Object]]:
        if channel is not None:
            return channel

        channel_data = data.get('channel')
        if isinstance(channel_data, dict) and channel_data.get('id'):
            return PartialInviteChannel(channel_data)

        channel_id = utils._snowflake(data.get('channelId'))
        if channel_id is None:
            return None
        guild = self.guild
        if guild is not None and hasattr(guild, 'get_channel'):
            found = guild.get_channel(channel_id)  # type: ignore
            if found is not None:
                return found
        if data.get('channelName'):
            return PartialInviteChannel({'id': channel_id, 'name': data['channelName']})
        return Object(id=channel_id)

    def __str__(self) -> str:
        return self.url

    def __repr__(self) -> str:
        return (
            f'<Invite code={self.code!r} guild={self.guild!r} '
            f'online={self.approximate_presence_count} '
            f'members={self.approximate_member_count}>'
        )

    def __hash__(self) -> int:
        return hash(self.code)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Invite) and other.code == self.code

    @property
    def id(self) -> str:  # type: ignore[override]
        """:class:`str`: Returns the proper code portion of the invite."""
        return self.code

    @property
    def url(self) -> str:
        """:class:`str`: A property that retrieves the invite URL."""
        return f'{self.BASE}/{self.code}'

    def set_scheduled_event(self, scheduled_event: Any, /) -> Invite:
        """Not supported on Bisim (no scheduled events)."""
        from .errors import NotSupported

        raise NotSupported('Scheduled events')

    async def delete(self, *, reason: Optional[str] = None) -> Invite:
        """|coro|

        Revokes the instant invite.

        You must have :attr:`~Permissions.manage_channels` to do this.

        Parameters
        -----------
        reason: Optional[:class:`str`]
            The reason for deleting this invite. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to revoke invites.
        NotFound
            The invite is invalid or expired.
        HTTPException
            Revoking the invite failed.

        Returns
        --------
        :class:`Invite`
            The deleted invite.
        """
        guild = self.guild
        if guild is None:
            data = await self._state.http.get_invite(self.code)
            guild_data = data.get('guild') if isinstance(data, dict) else None
            guild_id = int(guild_data['id']) if guild_data else 0
        else:
            guild_id = guild.id
        await self._state.http.delete_invite(guild_id, self.code, reason=reason)
        self.revoked = True
        return self

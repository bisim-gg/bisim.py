from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from . import abc, utils
from .asset import Asset
from .colour import Colour
from .enums import DefaultAvatar
from .errors import ClientException, NotSupported
from .flags import PublicUserFlags

if TYPE_CHECKING:
    from datetime import datetime

    from typing_extensions import Self

    from .channel import DMChannel
    from .guild import Guild
    from .message import Message
    from .state import ConnectionState

__all__ = (
    'User',
    'ClientUser',
)


class _UserTag:
    __slots__ = ()
    id: int


class BaseUser(_UserTag):
    __slots__ = (
        'name',
        'id',
        'discriminator',
        'global_name',
        '_avatar',
        '_banner',
        'bot',
        'system',
        '_public_flags',
        '_state',
        'bio',
        'pronouns',
    )

    if TYPE_CHECKING:
        name: str
        id: int
        discriminator: str
        global_name: Optional[str]
        bot: bool
        system: bool
        _state: ConnectionState
        _avatar: Optional[str]
        _banner: Optional[str]
        _public_flags: int

    def __init__(self, *, state: ConnectionState, data: Dict[str, Any]) -> None:
        self._state = state
        self._update(data)

    def __repr__(self) -> str:
        return (
            f'<BaseUser id={self.id} name={self.name!r} global_name={self.global_name!r}'
            f' bot={self.bot} system={self.system}>'
        )

    def __str__(self) -> str:
        if self.discriminator == '0':
            return self.name
        return f'{self.name}#{self.discriminator}'

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _UserTag) and other.id == self.id

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return self.id >> 22

    def _update(self, data: Dict[str, Any]) -> None:
        raw_id = data.get('id') or data.get('userId') or data.get('user_id')
        self.id = int(raw_id)
        self.name = data.get('username') or data.get('name') or ''
        self.discriminator = '0'
        self.global_name = data.get('displayName') or data.get('display_name') or None
        self._avatar = data.get('avatarKey') or data.get('avatar') or None
        self._banner = data.get('bannerKey') or None
        self.bot = bool(data.get('bot', False))
        self.system = bool(data.get('system', False))
        self._public_flags = int(data.get('publicFlags', 0) or 0)
        self.bio = data.get('bio') or None
        self.pronouns = data.get('pronouns') or None

    def _patch(self, data: Dict[str, Any]) -> bool:
        """Applies a partial update; returns True when anything changed."""
        before = (self.name, self.global_name, self._avatar, self.bot)
        if 'username' in data and data['username']:
            self.name = data['username']
        if 'displayName' in data:
            self.global_name = data.get('displayName') or None
        if 'avatarKey' in data:
            self._avatar = data.get('avatarKey') or None
        if 'bot' in data:
            self.bot = bool(data.get('bot'))
        return before != (self.name, self.global_name, self._avatar, self.bot)

    @classmethod
    def _copy(cls, user: BaseUser) -> Self:
        self = cls.__new__(cls)
        self.name = user.name
        self.id = user.id
        self.discriminator = user.discriminator
        self.global_name = user.global_name
        self._avatar = user._avatar
        self._banner = user._banner
        self.bot = user.bot
        self._state = user._state
        self._public_flags = user._public_flags
        self.system = user.system
        self.bio = user.bio
        self.pronouns = user.pronouns
        return self

    def _to_minimal_user_json(self) -> Dict[str, Any]:
        return {
            'id': str(self.id),
            'username': self.name,
            'displayName': self.global_name,
            'avatarKey': self._avatar,
            'bot': self.bot,
        }

    @property
    def public_flags(self) -> PublicUserFlags:
        """:class:`PublicUserFlags`: The publicly available flags the user has."""
        return PublicUserFlags._from_value(self._public_flags)

    @property
    def avatar(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns an :class:`Asset` for the avatar the user has.

        If the user has not uploaded a global avatar, ``None`` is returned.
        If you want the avatar that a user has displayed, consider :attr:`display_avatar`.
        """
        if self._avatar is not None:
            return Asset._from_avatar(self._state, self.id, self._avatar)
        return None

    @property
    def default_avatar(self) -> Asset:
        """:class:`Asset`: Returns the default avatar for a given user."""
        return Asset._from_default_avatar(self._state, (self.id >> 22) % 12)

    @property
    def display_avatar(self) -> Asset:
        """:class:`Asset`: Returns the user's display avatar.

        For regular users this is just their default avatar or uploaded avatar.
        """
        return self.avatar or self.default_avatar

    @property
    def avatar_decoration(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Not on Bisim."""
        return None

    @property
    def avatar_decoration_sku_id(self) -> Optional[int]:
        """Optional[:class:`int`]: Not on Bisim."""
        return None

    @property
    def banner(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the user's banner asset, if available.

        .. note::
            This information is only available via :meth:`Client.fetch_user`.
        """
        if self._banner is None:
            return None
        return Asset._from_key(self._state, self._banner)

    @property
    def accent_colour(self) -> Optional[Colour]:
        """Optional[:class:`Colour`]: Not on Bisim."""
        return None

    @property
    def accent_color(self) -> Optional[Colour]:
        """Optional[:class:`Colour`]: Not on Bisim."""
        return None

    @property
    def colour(self) -> Colour:
        """:class:`Colour`: A property that returns a colour denoting the rendered colour
        for the user. This always returns :meth:`Colour.default`.

        There is an alias for this named :attr:`color`.
        """
        return Colour.default()

    @property
    def color(self) -> Colour:
        """:class:`Colour`: A property that returns a color denoting the rendered color
        for the user. This always returns :meth:`Colour.default`.

        There is an alias for this named :attr:`colour`.
        """
        return self.colour

    @property
    def mention(self) -> str:
        """:class:`str`: Returns a string that allows you to mention the given user."""
        return f'<@{self.id}>'

    @property
    def created_at(self) -> datetime:
        """:class:`datetime.datetime`: Returns the user's creation time in UTC.

        This is when the user's Bisim account was created.
        """
        return utils.snowflake_time(self.id)

    @property
    def display_name(self) -> str:
        """:class:`str`: Returns the user's display name.

        For regular users this is just their global name or their username,
        but if they have a guild specific nickname then that
        is returned instead.
        """
        if self.global_name:
            return self.global_name
        return self.name

    def mentioned_in(self, message: Message) -> bool:
        """Checks if the user is mentioned in the specified message.

        Parameters
        -----------
        message: :class:`Message`
            The message to check if you're mentioned in.

        Returns
        -------
        :class:`bool`
            Indicates if the user is mentioned in the message.
        """
        if message.mention_everyone:
            return True
        return any(user.id == self.id for user in message.mentions) or self.id in message.raw_mentions


class ClientUser(BaseUser):
    """Represents your Bisim user (the bot).

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: x != y

            Checks if two users are not equal.

        .. describe:: hash(x)

            Return the user's hash.

        .. describe:: str(x)

            Returns the user's handle (e.g. ``name``).

    Attributes
    -----------
    name: :class:`str`
        The user's username.
    id: :class:`int`
        The user's unique ID, which is also the application's ID.
    discriminator: :class:`str`
        Always ``'0'``: Bisim usernames are unique.
    global_name: Optional[:class:`str`]
        The user's display name, if they have one.
    bot: :class:`bool`
        Specifies if the user is a bot account.
    system: :class:`bool`
        Specifies if the user is a system user.
    verified: :class:`bool`
        Specifies if the user's email is verified (always ``True`` for a bot).
    locale: Optional[:class:`Locale`]
        The IETF language tag used to identify the language the user is using.
    mfa_enabled: :class:`bool`
        Specifies if the user has MFA turned on and working.
    """

    __slots__ = ('locale', '_flags', 'verified', 'mfa_enabled', '__weakref__')

    if TYPE_CHECKING:
        verified: bool
        locale: Any
        mfa_enabled: bool
        _flags: int

    def __init__(self, *, state: ConnectionState, data: Dict[str, Any]) -> None:
        super().__init__(state=state, data=data)

    def __repr__(self) -> str:
        return (
            f'<ClientUser id={self.id} name={self.name!r} global_name={self.global_name!r}'
            f' bot={self.bot} verified={self.verified} mfa_enabled={self.mfa_enabled}>'
        )

    def _update(self, data: Dict[str, Any]) -> None:
        super()._update(data)
        from .enums import Locale, try_enum

        self.verified = bool(data.get('verified', True))
        locale = data.get('locale')
        self.locale = try_enum(Locale, locale) if locale else None
        self._flags = int(data.get('flags', 0) or 0)
        self.mfa_enabled = bool(data.get('totpEnabled', False))
        if 'bot' not in data:
            # Only a bot can log in with a bot token.
            self.bot = True

    async def edit(
        self,
        *,
        username: str = utils.MISSING,
        avatar: Optional[bytes] = utils.MISSING,
        banner: Optional[bytes] = utils.MISSING,
        bio: Optional[str] = utils.MISSING,
    ) -> ClientUser:
        """|coro|

        Edits the current profile of the client.

        On Bisim a bot's name is its application's name, so changing
        ``username`` renames the application (and the bot with it). Changing
        the avatar, banner or bio of a bot is not supported.

        Parameters
        -----------
        username: :class:`str`
            The new username you wish to change to.
        avatar: Optional[:class:`bytes`]
            Not supported on Bisim.
        banner: Optional[:class:`bytes`]
            Not supported on Bisim.
        bio: Optional[:class:`str`]
            Not supported on Bisim.

        Raises
        ------
        HTTPException
            Editing your profile failed.
        NotSupported
            An avatar, banner or bio was passed.

        Returns
        ---------
        :class:`ClientUser`
            The newly edited client user.
        """
        if avatar is not utils.MISSING:
            raise NotSupported("Changing a bot's avatar from the library")
        if banner is not utils.MISSING:
            raise NotSupported("Changing a bot's banner")
        if bio is not utils.MISSING:
            raise NotSupported("Changing a bot's bio")
        if username is not utils.MISSING:
            await self._state.http.edit_application(self.id, name=username)
            data = await self._state.http.get_me()
            self._update(data)
        return self

    @property
    def mutual_guilds(self) -> List[Guild]:
        """List[:class:`Guild`]: The guilds that the user shares with the client."""
        return list(self._state.guilds)


class User(BaseUser, abc.Messageable):
    """Represents a Bisim user.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: x != y

            Checks if two users are not equal.

        .. describe:: hash(x)

            Return the user's hash.

        .. describe:: str(x)

            Returns the user's handle (e.g. ``name``).

    Attributes
    -----------
    name: :class:`str`
        The user's username.
    id: :class:`int`
        The user's unique ID.
    discriminator: :class:`str`
        Always ``'0'``: Bisim usernames are unique.
    global_name: Optional[:class:`str`]
        The user's display name, if they have one.
    bot: :class:`bool`
        Specifies if the user is a bot account.
    system: :class:`bool`
        Specifies if the user is a system user.
    """

    __slots__ = ('__weakref__',)

    def __repr__(self) -> str:
        return f'<User id={self.id} name={self.name!r} global_name={self.global_name!r} bot={self.bot}>'

    async def _get_channel(self) -> DMChannel:
        ch = await self.create_dm()
        return ch

    @property
    def dm_channel(self) -> Optional[DMChannel]:
        """Optional[:class:`DMChannel`]: Returns the channel associated with this user if it exists.

        If this returns ``None``, you can create a DM channel by calling the
        :meth:`create_dm` coroutine function.
        """
        return self._state._get_private_channel_by_user(self.id)

    @property
    def mutual_guilds(self) -> List[Guild]:
        """List[:class:`Guild`]: The guilds that the user shares with the client.

        .. note::

            This will only return mutual guilds within the client's internal cache.
        """
        return [guild for guild in self._state._guilds.values() if guild.get_member(self.id)]

    async def create_dm(self) -> DMChannel:
        """|coro|

        Creates a :class:`DMChannel` with this user.

        This should be rarely called, as this is done transparently for most
        people.

        Returns
        -------
        :class:`.DMChannel`
            The channel that was created.
        """
        found = self.dm_channel
        if found is not None:
            return found

        state = self._state
        data = await state.http.start_private_message(self.id)
        return state.add_dm_channel(data)

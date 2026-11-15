from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple

from . import utils
from .asset import Asset, AssetMixin
from .errors import NotSupported
from .partial_emoji import PartialEmoji, _EmojiTag

if TYPE_CHECKING:
    from datetime import datetime

    from .guild import Guild
    from .role import Role
    from .state import ConnectionState
    from .user import User

__all__ = ('Emoji',)


class Emoji(_EmojiTag, AssetMixin):
    """Represents a custom emoji.

    Depending on the way this object was created, some of the attributes can
    have a value of ``None``.

    .. container:: operations

        .. describe:: x == y

            Checks if two emoji are the same.

        .. describe:: x != y

            Checks if two emoji are not the same.

        .. describe:: hash(x)

            Return the emoji's hash.

        .. describe:: iter(x)

            Returns an iterator of ``(field, value)`` pairs. This allows this class
            to be used as an iterable in list/dict/etc constructions.

        .. describe:: str(x)

            Returns the emoji rendered for Bisim.

    Attributes
    -----------
    name: :class:`str`
        The name of the emoji.
    id: :class:`int`
        The emoji's ID.
    require_colons: :class:`bool`
        Always ``True`` on Bisim.
    animated: :class:`bool`
        Whether an emoji is animated or not.
    managed: :class:`bool`
        Always ``False`` on Bisim.
    guild_id: :class:`int`
        The guild ID the emoji belongs to.
    available: :class:`bool`
        Always ``True`` on Bisim.
    user: Optional[:class:`User`]
        The user that created the emoji, when known.
    """

    __slots__: Tuple[str, ...] = (
        'require_colons',
        'animated',
        'managed',
        'id',
        'name',
        '_roles',
        'guild_id',
        '_state',
        'user',
        'available',
        '_object_key',
        'creator_id',
    )

    def __init__(self, *, guild: Any, state: ConnectionState, data: Dict[str, Any]):
        self.guild_id: int = guild.id
        self._state: ConnectionState = state
        self._from_data(data)

    def _from_data(self, emoji: Dict[str, Any]) -> None:
        self.require_colons: bool = True
        self.managed: bool = False
        self.id: int = int(emoji['id'])
        self.name: str = emoji.get('name') or ''
        self._object_key: str = emoji.get('objectKey') or emoji.get('object_key') or ''
        self.animated: bool = self._object_key.endswith('.gif') or bool(emoji.get('animated', False))
        self.available: bool = True
        self._roles: List[int] = []
        self.creator_id: Optional[int] = utils._snowflake(emoji.get('creatorId'))
        self.user: Optional[User] = self._state.get_user(self.creator_id) if self.creator_id else None

    def _to_partial(self) -> PartialEmoji:
        return PartialEmoji.with_state(self._state, name=self.name, animated=self.animated, id=self.id)

    def __iter__(self) -> Iterator[Tuple[str, Any]]:
        for key in self.__slots__:
            if key[0] != '_':
                value = getattr(self, key, None)
                if value is not None:
                    yield (key, value)

    def __str__(self) -> str:
        if self.animated:
            return f'<a:{self.name}:{self.id}>'
        return f'<:{self.name}:{self.id}>'

    def __repr__(self) -> str:
        return f'<Emoji id={self.id} name={self.name!r} animated={self.animated} managed={self.managed}>'

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _EmojiTag) and self.id == other.id

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return self.id >> 22

    @property
    def created_at(self) -> datetime:
        """:class:`datetime.datetime`: Returns the emoji's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def url(self) -> str:
        """:class:`str`: Returns the URL of the emoji."""
        if not self._object_key:
            return ''
        return Asset._from_key(self._state, self._object_key).url

    @property
    def roles(self) -> List[Role]:
        """List[:class:`Role`]: Always empty: Bisim emoji are usable by every member."""
        return []

    @property
    def guild(self) -> Optional[Guild]:
        """:class:`Guild`: The guild this emoji belongs to."""
        return self._state._get_guild(self.guild_id)

    def is_usable(self) -> bool:
        """:class:`bool`: Whether the bot can use this emoji."""
        return True

    async def delete(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Deletes the custom emoji.

        You must have :attr:`~Permissions.manage_expressions` to do this.

        Parameters
        -----------
        reason: Optional[:class:`str`]
            The reason for deleting this emoji. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You are not allowed to delete emojis.
        HTTPException
            An error occurred deleting the emoji.
        """
        await self._state.http.delete_custom_emoji(self.guild_id, self.id, reason=reason)

    async def edit(self, *, name: str = utils.MISSING, roles: Any = utils.MISSING, reason: Optional[str] = None) -> Emoji:
        r"""|coro|

        Edits the custom emoji.

        You must have :attr:`~Permissions.manage_expressions` to do this, or
        :attr:`~Permissions.create_expressions` for an emoji the bot made.

        Parameters
        -----------
        name: :class:`str`
            The new emoji name: 2 to 32 letters, digits or underscores.
        roles: List[:class:`~bisim.abc.Snowflake`]
            Not supported on Bisim: every member may use a server's emoji.
        reason: Optional[:class:`str`]
            The reason for editing this emoji. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You are not allowed to edit emojis.
        HTTPException
            An error occurred editing the emoji.
        NotSupported
            ``roles`` was given.

        Returns
        --------
        :class:`Emoji`
            The newly updated emoji.
        """
        if roles is not utils.MISSING:
            raise NotSupported('Role-locked emoji')
        payload: Dict[str, Any] = {}
        if name is not utils.MISSING:
            payload['name'] = name
        if not payload:
            return self
        data = await self._state.http.edit_custom_emoji(self.guild_id, self.id, payload=payload, reason=reason)
        guild = self.guild
        if guild is not None:
            return self._state.store_emoji(guild, data)  # type: ignore
        from .object import Object

        return Emoji(guild=Object(id=self.guild_id), state=self._state, data=data)

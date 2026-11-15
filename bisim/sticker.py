from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from . import utils
from .asset import Asset, AssetMixin
from .enums import StickerFormatType, StickerType
from .errors import NotSupported
from .mixins import Hashable

if TYPE_CHECKING:
    from .guild import Guild
    from .state import ConnectionState
    from .user import User

__all__ = (
    'StickerPack',
    'StickerItem',
    'Sticker',
    'StandardSticker',
    'GuildSticker',
)


def _format_of(key: str) -> StickerFormatType:
    lowered = key.lower()
    if lowered.endswith('.gif'):
        return StickerFormatType.gif
    if lowered.endswith('.json'):
        return StickerFormatType.lottie
    return StickerFormatType.png


class StickerPack:
    """Not on Bisim (no sticker packs); kept so the name imports."""


class StickerItem(Hashable, AssetMixin):
    """Represents a sticker item.

    On Bisim a sticker is sent as a whole message whose content is
    ``<sticker:id>``; this is what :attr:`Message.stickers` holds.

    .. container:: operations

        .. describe:: str(x)

            Returns the name of the sticker item.

        .. describe:: x == y

           Checks if the sticker item is equal to another sticker item.

        .. describe:: x != y

           Checks if the sticker item is not equal to another sticker item.

    Attributes
    -----------
    name: :class:`str`
        The sticker's name, when the library knows it.
    id: :class:`int`
        The id of the sticker.
    format: :class:`StickerFormatType`
        The format for the sticker's image.
    url: :class:`str`
        The URL for the sticker's image, when the library knows it.
    """

    __slots__ = ('_state', 'name', 'id', 'format', 'url', '_guild_id')

    def __init__(self, *, state: ConnectionState, data: Dict[str, Any]) -> None:
        self._state: ConnectionState = state
        self.name: str = data.get('name') or ''
        self.id: int = int(data['id'])
        key = data.get('objectKey') or ''
        self.format: StickerFormatType = _format_of(key)
        self.url: str = Asset._from_key(state, key).url if key else ''
        self._guild_id: Optional[int] = utils._snowflake(data.get('guildId'))

    @classmethod
    def _from_id(cls, state: ConnectionState, sticker_id: int, guild: Optional[Guild]) -> StickerItem:
        known = state._get_sticker(sticker_id)
        if known is not None:
            return cls(state=state, data={'id': known.id, 'name': known.name, 'objectKey': known._object_key, 'guildId': known.guild_id})
        return cls(state=state, data={'id': sticker_id})

    def __repr__(self) -> str:
        return f'<StickerItem id={self.id} name={self.name!r} format={self.format}>'

    def __str__(self) -> str:
        return self.name

    async def fetch(self) -> GuildSticker:
        """|coro|

        Attempts to retrieve the full sticker data of the sticker item.

        Raises
        --------
        NotFound
            The sticker is not one of a server the bot is in.

        Returns
        --------
        :class:`GuildSticker`
            The retrieved sticker.
        """
        known = self._state._get_sticker(self.id)
        if known is not None:
            return known
        from .errors import NotFound
        from .http import _ResponseLike

        raise NotFound(_ResponseLike(404, 'Not Found'), 'Unknown sticker')  # type: ignore


class Sticker(Hashable, AssetMixin):
    """Represents a sticker.

    Attributes
    ------------
    name: :class:`str`
        The sticker's name.
    id: :class:`int`
        The id of the sticker.
    description: :class:`str`
        Always empty on Bisim.
    format: :class:`StickerFormatType`
        The format for the sticker's image.
    url: :class:`str`
        The URL for the sticker's image.
    """

    __slots__ = ('_state', 'id', 'name', 'description', 'format', 'url', '_object_key')

    def __init__(self, *, state: ConnectionState, data: Dict[str, Any]) -> None:
        self._state: ConnectionState = state
        self._from_data(data)

    def _from_data(self, data: Dict[str, Any]) -> None:
        self.id: int = int(data['id'])
        self.name: str = data.get('name') or ''
        self.description: str = ''
        self._object_key: str = data.get('objectKey') or ''
        self.format: StickerFormatType = _format_of(self._object_key)
        self.url: str = Asset._from_key(self._state, self._object_key).url if self._object_key else ''

    def __repr__(self) -> str:
        return f'<Sticker id={self.id} name={self.name!r}>'

    def __str__(self) -> str:
        return self.name

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the sticker's creation time in UTC."""
        return utils.snowflake_time(self.id)


class StandardSticker(Sticker):
    """Not on Bisim (no standard stickers); kept so the name imports."""

    __slots__ = ()


class GuildSticker(Sticker):
    """Represents a sticker that belongs to a guild.

    Attributes
    ------------
    name: :class:`str`
        The sticker's name.
    id: :class:`int`
        The id of the sticker.
    format: :class:`StickerFormatType`
        The format for the sticker's image.
    available: :class:`bool`
        Always ``True``.
    guild_id: :class:`int`
        The ID of the guild that this sticker is from.
    user: Optional[:class:`User`]
        The user that created this sticker, when known.
    emoji: :class:`str`
        Always empty on Bisim.
    """

    __slots__ = ('available', 'guild_id', 'user', 'emoji', 'type', '_cs_guild', 'creator_id')

    def _from_data(self, data: Dict[str, Any]) -> None:
        super()._from_data(data)
        self.available: bool = True
        self.guild_id: int = int(data['guildId'])
        self.creator_id: Optional[int] = utils._snowflake(data.get('creatorId'))
        self.user: Optional[User] = self._state.get_user(self.creator_id) if self.creator_id else None
        self.emoji: str = ''
        self.type: StickerType = StickerType.guild

    def __repr__(self) -> str:
        return f'<GuildSticker name={self.name!r} id={self.id} guild_id={self.guild_id} user={self.user!r}>'

    @property
    def guild(self) -> Optional[Guild]:
        """Optional[:class:`Guild`]: The guild that this sticker is from."""
        return self._state._get_guild(self.guild_id)

    async def edit(
        self,
        *,
        name: str = utils.MISSING,
        description: str = utils.MISSING,
        emoji: str = utils.MISSING,
        reason: Optional[str] = None,
    ) -> GuildSticker:
        """|coro|

        Edits a :class:`GuildSticker` for the guild.

        You must have :attr:`~Permissions.manage_expressions` to do this, or
        :attr:`~Permissions.create_expressions` for a sticker the bot made.

        Parameters
        -----------
        name: :class:`str`
            The sticker's new name, 2 to 30 characters.
        description: :class:`str`
            Not supported on Bisim (stickers have no description).
        emoji: :class:`str`
            Not supported on Bisim (stickers have no related emoji).
        reason: :class:`str`
            The reason for editing this sticker. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You are not allowed to edit stickers.
        HTTPException
            An error occurred editing the sticker.
        NotSupported
            ``description`` or ``emoji`` was given.

        Returns
        --------
        :class:`GuildSticker`
            The newly modified sticker.
        """
        if description is not utils.MISSING:
            raise NotSupported('Sticker descriptions')
        if emoji is not utils.MISSING:
            raise NotSupported("A sticker's related emoji")
        payload: Dict[str, Any] = {}
        if name is not utils.MISSING:
            payload['name'] = name
        if not payload:
            return self
        data = await self._state.http.modify_guild_sticker(self.guild_id, self.id, payload, reason=reason)
        data = dict(data)
        data.setdefault('guildId', str(self.guild_id))
        sticker = GuildSticker(state=self._state, data=data)
        stickers = getattr(self._state, '_stickers', None)
        if isinstance(stickers, dict):
            stickers[sticker.id] = sticker
        return sticker

    async def delete(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Deletes the custom :class:`Sticker` from the guild.

        You must have :attr:`~Permissions.manage_expressions` to do this.

        Parameters
        -----------
        reason: Optional[:class:`str`]
            The reason for deleting this sticker. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You are not allowed to delete stickers.
        HTTPException
            An error occurred deleting the sticker.
        """
        await self._state.http.delete_guild_sticker(self.guild_id, self.id, reason=reason)

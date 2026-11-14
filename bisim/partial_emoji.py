from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from . import utils
from .asset import Asset, AssetMixin

if TYPE_CHECKING:
    from datetime import datetime

    from typing_extensions import Self

__all__ = ('PartialEmoji',)


class _EmojiTag:
    __slots__ = ()

    id: int

    def _to_partial(self) -> PartialEmoji:
        raise NotImplementedError


_CUSTOM_EMOJI_RE = re.compile(r'<?(?:(?P<animated>a)?:)?(?P<name>[A-Za-z0-9_]+):(?P<id>[0-9]{1,20})>?')


class PartialEmoji(_EmojiTag, AssetMixin):
    """Represents a "partial" emoji.

    This model will be given in two scenarios:

    - "Raw" data events such as :func:`on_raw_reaction_add`
    - Custom emoji that the bot cannot see from e.g. :attr:`Message.reactions`

    .. container:: operations

        .. describe:: x == y

            Checks if two emoji are the same.

        .. describe:: x != y

            Checks if two emoji are not the same.

        .. describe:: hash(x)

            Return the emoji's hash.

        .. describe:: str(x)

            Returns the emoji rendered for Bisim.

    Attributes
    -----------
    name: Optional[:class:`str`]
        The custom emoji name, if applicable, or the unicode codepoint
        of the non-custom emoji. This can be ``None`` if the emoji
        got deleted (e.g. removing a reaction with a deleted emoji).
    animated: :class:`bool`
        Whether the emoji is animated or not.
    id: Optional[:class:`int`]
        The ID of the custom emoji, if applicable.
    """

    __slots__ = ('animated', 'name', 'id', '_state')

    def __init__(self, *, name: str, animated: bool = False, id: Optional[int] = None):
        self.animated: bool = animated
        self.name: str = name
        self.id: Optional[int] = id
        self._state: Optional[Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Self:
        emoji_id = data.get('id')
        return cls(
            animated=bool(data.get('animated', False)),
            id=utils._snowflake(emoji_id),
            name=data.get('name') or '',
        )

    @classmethod
    def from_str(cls, value: str) -> Self:
        """Converts a Bisim string representation of an emoji to a :class:`PartialEmoji`.

        The formats accepted are:

        - ``a:name:id``
        - ``<a:name:id>``
        - ``name:id``
        - ``<:name:id>``

        If the format does not match then it is assumed to be a unicode emoji.

        Parameters
        ------------
        value: :class:`str`
            The string representation of an emoji.

        Returns
        --------
        :class:`PartialEmoji`
            The partial emoji from this string.
        """
        match = _CUSTOM_EMOJI_RE.fullmatch(value)
        if match is not None:
            groups = match.groupdict()
            return cls(name=groups['name'], animated=bool(groups['animated']), id=int(groups['id']))
        return cls(name=value, id=None, animated=False)

    @classmethod
    def with_state(cls, state: Any, *, name: str, animated: bool = False, id: Optional[int] = None) -> Self:
        self = cls(name=name, animated=animated, id=id)
        self._state = state
        return self

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {'name': self.name}
        if self.id is not None:
            payload['id'] = str(self.id)
        if self.animated:
            payload['animated'] = self.animated
        return payload

    def _to_partial(self) -> PartialEmoji:
        return self

    def _to_forum_tag_payload(self) -> Dict[str, Any]:
        return self.to_dict()

    def __str__(self) -> str:
        # Coerce empty names to "_" so the token still parses.
        name = self.name or '_'
        if self.id is None:
            return name
        if self.animated:
            return f'<a:{name}:{self.id}>'
        return f'<:{name}:{self.id}>'

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} animated={self.animated} name={self.name!r} id={self.id}>'

    def __eq__(self, other: object) -> bool:
        if self.is_unicode_emoji():
            return isinstance(other, PartialEmoji) and self.name == other.name
        if isinstance(other, _EmojiTag):
            return self.id == other.id
        return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash((self.id, self.name))

    def is_custom_emoji(self) -> bool:
        """:class:`bool`: Checks if this is a custom non-Unicode emoji."""
        return self.id is not None

    def is_unicode_emoji(self) -> bool:
        """:class:`bool`: Checks if this is a Unicode emoji."""
        return self.id is None

    def _as_reaction(self) -> str:
        if self.id is None:
            return self.name
        return f'<:{self.name}:{self.id}>'

    @property
    def created_at(self) -> Optional[datetime]:
        """Optional[:class:`datetime.datetime`]: Returns the emoji's creation time in UTC, or None if Unicode emoji."""
        if self.id is None:
            return None
        return utils.snowflake_time(self.id)

    @property
    def url(self) -> str:
        """:class:`str`: Returns the URL of the emoji, if it is custom.

        If this isn't a custom emoji then an empty string is returned. Bisim
        stores each emoji under its own key, so the URL is only known for the
        emoji of servers the bot is in.
        """
        if self.is_unicode_emoji():
            return ''
        state = self._state
        if state is not None:
            emoji = state.get_emoji(self.id)
            if emoji is not None:
                return emoji.url
        return ''

    async def read(self) -> bytes:
        """|coro|

        Retrieves the content of this asset as a :class:`bytes` object.

        Raises
        ------
        BisimException
            There was no internal connection state.
        HTTPException
            Downloading the asset failed.
        NotFound
            The asset was deleted.
        ValueError
            The PartialEmoji is not a custom emoji.

        Returns
        -------
        :class:`bytes`
            The content of the asset.
        """
        if self.is_unicode_emoji():
            raise ValueError('PartialEmoji is not a custom emoji')
        if not self.url:
            raise ValueError('The address of this emoji is not known')
        return await super().read()

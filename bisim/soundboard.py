"""A server's soundboard sounds, as far as a bot plays them."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from . import utils
from .asset import Asset
from .mixins import Hashable
from .partial_emoji import PartialEmoji

if TYPE_CHECKING:
    from .guild import Guild
    from .state import ConnectionState
    from .user import User

__all__ = ('SoundboardSound',)


class SoundboardSound(Hashable):
    """Represents one of a server's soundboard sounds.

    Get them with :meth:`Guild.fetch_soundboard_sounds` and play one with
    :meth:`VoiceChannel.send_sound` while the bot is in that channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two sounds are equal.

        .. describe:: x != y

            Checks if two sounds are not equal.

        .. describe:: hash(x)

            Returns the sound's hash.

        .. describe:: str(x)

            Returns the sound's name.

    Attributes
    ------------
    id: :class:`int`
        The ID of the sound.
    name: :class:`str`
        The name of the sound.
    volume: :class:`float`
        The volume of the sound, from 0.0 to 1.0.
    emoji: Optional[:class:`PartialEmoji`]
        The emoji on the sound's button, if any.
    guild: :class:`Guild`
        The guild the sound belongs to.
    available: :class:`bool`
        Always ``True``.
    user: Optional[:class:`User`]
        The user who added the sound, when known.
    duration: :class:`float`
        The length of the sound in seconds, as its uploader measured it.
    """

    __slots__ = ('_state', 'id', 'name', 'volume', 'emoji', 'guild', 'available', 'user', 'duration', '_object_key', '_creator_id')

    def __init__(self, *, guild: Guild, state: ConnectionState, data: Dict[str, Any]) -> None:
        self._state: ConnectionState = state
        self.guild: Guild = guild
        self.id: int = int(data['id'])
        self._update(data)

    def _update(self, data: Dict[str, Any]) -> None:
        self.name: str = data.get('name') or ''
        self.volume: float = max(0, min(100, utils._int(data.get('volume'), 100))) / 100.0
        emoji = data.get('emojiName')
        self.emoji: Optional[PartialEmoji] = PartialEmoji(name=emoji) if emoji else None
        self.available: bool = True
        self.duration: float = utils._int(data.get('durationMs'), 0) / 1000.0
        self._object_key: str = data.get('objectKey') or ''
        self._creator_id: Optional[int] = utils._snowflake(data.get('creatorId'))
        self.user: Optional[User] = self._state.get_user(self._creator_id) if self._creator_id else None

    def __repr__(self) -> str:
        return f'<SoundboardSound id={self.id} name={self.name!r} volume={self.volume} guild={self.guild!r}>'

    def __str__(self) -> str:
        return self.name

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the sound's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def file(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: The sound's audio file."""
        if not self._object_key:
            return None
        return Asset._from_key(self._state, self._object_key)

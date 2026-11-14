from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional, Union, overload

from .enums import ActivityType, try_enum
from .partial_emoji import PartialEmoji

__all__ = (
    'BaseActivity',
    'Activity',
    'Streaming',
    'Game',
    'Spotify',
    'CustomActivity',
)


class BaseActivity:
    """The base activity that all user-settable activities inherit from.
    A user-settable activity is one that can be used in :meth:`Client.change_presence`.

    The following types currently count as user-settable:

    - :class:`Activity`
    - :class:`Game`
    - :class:`Streaming`
    - :class:`CustomActivity`

    On Bisim, a :class:`Game`, :class:`Streaming` or :class:`Activity`
    becomes the bot's activity (type and name), and a :class:`CustomActivity`
    becomes its custom status text.
    """

    __slots__ = ('_created_at',)

    def __init__(self, **kwargs: Any) -> None:
        self._created_at: Optional[float] = kwargs.pop('created_at', None)

    @property
    def created_at(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: When the user started doing this activity in UTC."""
        if self._created_at is not None:
            return datetime.datetime.fromtimestamp(self._created_at / 1000, tz=datetime.timezone.utc)
        return None

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    def _to_bisim(self) -> Dict[str, Any]:
        """The ``activity`` object of a presence frame: ``{type, name}``."""
        return {'type': int(getattr(self, 'type', ActivityType.playing).value), 'name': getattr(self, 'name', '') or ''}


class Activity(BaseActivity):
    """Represents an activity in Bisim.

    This could be an activity such as streaming, playing, listening
    or watching.

    For memory optimisation purposes, some activities are offered in slimmed
    down versions:

    - :class:`Game`
    - :class:`Streaming`

    Parameters
    ------------
    name: Optional[:class:`str`]
        The name of the activity.
    type: :class:`ActivityType`
        The type of activity currently being done.
    url: Optional[:class:`str`]
        A stream URL that the activity could be doing. Bisim does not show it.
    state: Optional[:class:`str`]
        The user's current state. For example, "In Game".
    details: Optional[:class:`str`]
        The detail of the user's current activity.
    """

    __slots__ = (
        'state',
        'details',
        'timestamps',
        'assets',
        'party',
        'flags',
        'sync_id',
        'session_id',
        'type',
        'name',
        'url',
        'application_id',
        'emoji',
        'buttons',
        'platform',
        'status_display_type',
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.state: Optional[str] = kwargs.pop('state', None)
        self.details: Optional[str] = kwargs.pop('details', None)
        self.timestamps: Dict[str, Any] = kwargs.pop('timestamps', {})
        self.assets: Dict[str, Any] = kwargs.pop('assets', {})
        self.party: Dict[str, Any] = kwargs.pop('party', {})
        self.application_id: Optional[int] = None
        self.name: Optional[str] = kwargs.pop('name', None)
        self.url: Optional[str] = kwargs.pop('url', None)
        self.flags: int = kwargs.pop('flags', 0)
        self.sync_id: Optional[str] = kwargs.pop('sync_id', None)
        self.session_id: Optional[str] = kwargs.pop('session_id', None)
        self.buttons: Any = kwargs.pop('buttons', [])
        self.platform: Optional[str] = kwargs.pop('platform', None)
        self.status_display_type: Any = kwargs.pop('status_display_type', None)

        activity_type = kwargs.pop('type', -1)
        self.type: ActivityType = (
            activity_type if isinstance(activity_type, ActivityType) else try_enum(ActivityType, activity_type)
        )

        emoji = kwargs.pop('emoji', None)
        self.emoji: Optional[PartialEmoji] = PartialEmoji.from_dict(emoji) if emoji is not None else None

    def __repr__(self) -> str:
        attrs = (
            ('type', self.type),
            ('name', self.name),
            ('url', self.url),
            ('details', self.details),
        )
        inner = ' '.join('%s=%r' % t for t in attrs)
        return f'<Activity {inner}>'

    def to_dict(self) -> Dict[str, Any]:
        ret: Dict[str, Any] = {}
        for attr in self.__slots__:
            value = getattr(self, attr, None)
            if value is None:
                continue
            if isinstance(value, dict) and len(value) == 0:
                continue
            ret[attr] = value
        ret['type'] = int(self.type)
        if self.emoji:
            ret['emoji'] = self.emoji.to_dict()
        return ret

    @property
    def start(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: When the user started doing this activity in UTC, if applicable."""
        try:
            timestamp = self.timestamps['start'] / 1000
        except KeyError:
            return None
        return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)

    @property
    def end(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: When the user will stop doing this activity in UTC, if applicable."""
        try:
            timestamp = self.timestamps['end'] / 1000
        except KeyError:
            return None
        return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)

    @property
    def large_image_url(self) -> Optional[str]:
        """Optional[:class:`str`]: Not on Bisim."""
        return None

    @property
    def small_image_url(self) -> Optional[str]:
        """Optional[:class:`str`]: Not on Bisim."""
        return None

    @property
    def large_image_text(self) -> Optional[str]:
        return self.assets.get('large_text', None)

    @property
    def small_image_text(self) -> Optional[str]:
        return self.assets.get('small_text', None)


class Game(BaseActivity):
    """A slimmed down version of :class:`Activity` that represents a Bisim game.

    This is typically displayed via **Playing** on the official Bisim client.

    .. container:: operations

        .. describe:: x == y

            Checks if two games are equal.

        .. describe:: x != y

            Checks if two games are not equal.

        .. describe:: hash(x)

            Returns the game's hash.

        .. describe:: str(x)

            Returns the game's name.

    Parameters
    -----------
    name: :class:`str`
        The game's name.

    Attributes
    -----------
    name: :class:`str`
        The game's name.
    platform: Optional[:class:`str`]
        Where the user is playing from (ie. PS5, Xbox).
    assets: :class:`dict`
        A dictionary representing the images and their hover text of a game.
    """

    __slots__ = ('name', '_end', '_start', 'platform', 'assets')

    def __init__(self, name: str, **extra: Any) -> None:
        super().__init__(**extra)
        self.name: str = name
        self.platform: Optional[str] = extra.get('platform')
        self.assets: Dict[str, Any] = extra.get('assets', {}) or {}
        timestamps = extra.get('timestamps') or {}
        self._start: int = timestamps.get('start', 0)
        self._end: int = timestamps.get('end', 0)

    @property
    def type(self) -> ActivityType:
        """:class:`ActivityType`: Returns the game's type. This is for compatibility with :class:`Activity`.

        It always returns :attr:`ActivityType.playing`.
        """
        return ActivityType.playing

    @property
    def start(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: When the user started playing this game in UTC, if applicable."""
        if self._start:
            return datetime.datetime.fromtimestamp(self._start / 1000, tz=datetime.timezone.utc)
        return None

    @property
    def end(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: When the user will stop playing this game in UTC, if applicable."""
        if self._end:
            return datetime.datetime.fromtimestamp(self._end / 1000, tz=datetime.timezone.utc)
        return None

    def __str__(self) -> str:
        return str(self.name)

    def __repr__(self) -> str:
        return f'<Game name={self.name!r}>'

    def to_dict(self) -> Dict[str, Any]:
        return {'type': ActivityType.playing.value, 'name': str(self.name)}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Game) and other.name == self.name

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.name)


class Streaming(BaseActivity):
    """A slimmed down version of :class:`Activity` that represents a Bisim streaming status.

    This is typically displayed via **Streaming** on the official Bisim client.

    .. container:: operations

        .. describe:: x == y

            Checks if two streams are equal.

        .. describe:: x != y

            Checks if two streams are not equal.

        .. describe:: hash(x)

            Returns the stream's hash.

        .. describe:: str(x)

            Returns the stream's name.

    Attributes
    -----------
    platform: Optional[:class:`str`]
        Where the user is streaming from (ie. YouTube, Twitch).
    name: Optional[:class:`str`]
        The stream's name.
    details: Optional[:class:`str`]
        An alias for :attr:`name`
    game: Optional[:class:`str`]
        The game being streamed.
    url: :class:`str`
        The stream's URL. Bisim does not show it.
    assets: :class:`dict`
        A dictionary comprising of similar keys than those in :attr:`Activity.assets`.
    """

    __slots__ = ('platform', 'name', 'game', 'url', 'details', 'assets')

    def __init__(self, *, name: Optional[str], url: str, **extra: Any) -> None:
        super().__init__(**extra)
        self.platform: Optional[str] = name
        self.name: Optional[str] = extra.pop('details', name)
        self.game: Optional[str] = extra.pop('state', None)
        self.url: str = url
        self.details: Optional[str] = extra.pop('details', self.name)
        self.assets: Dict[str, Any] = extra.pop('assets', {})

    @property
    def type(self) -> ActivityType:
        """:class:`ActivityType`: Returns the game's type. This is for compatibility with :class:`Activity`.

        It always returns :attr:`ActivityType.streaming`.
        """
        return ActivityType.streaming

    def __str__(self) -> str:
        return str(self.name)

    def __repr__(self) -> str:
        return f'<Streaming name={self.name!r}>'

    @property
    def twitch_name(self) -> Optional[str]:
        """Optional[:class:`str`]: Not on Bisim."""
        return None

    def to_dict(self) -> Dict[str, Any]:
        ret: Dict[str, Any] = {'type': ActivityType.streaming.value, 'name': str(self.name), 'url': str(self.url)}
        if self.details:
            ret['details'] = self.details
        return ret

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Streaming) and other.name == self.name and other.url == self.url

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.name)


class Spotify:
    """Kept for compatibility with discord.py: Bisim has no Spotify integration,
    so no presence ever carries one."""

    __slots__ = ()

    @property
    def type(self) -> ActivityType:
        return ActivityType.listening


class CustomActivity(BaseActivity):
    """Represents a custom activity from Bisim.

    On Bisim this is the custom status: the text under the name, with an
    optional emoji.

    .. container:: operations

        .. describe:: x == y

            Checks if two activities are equal.

        .. describe:: x != y

            Checks if two activities are not equal.

        .. describe:: hash(x)

            Returns the activity's hash.

        .. describe:: str(x)

            Returns the custom status text.

    Attributes
    -----------
    name: Optional[:class:`str`]
        The custom activity's name.
    emoji: Optional[:class:`PartialEmoji`]
        The emoji to pass to the activity, if any.
    expires_at: Optional[:class:`datetime.datetime`]
        When the custom status disappears. ``None`` keeps it.
    """

    __slots__ = ('name', 'emoji', 'state', 'expires_at')

    def __init__(
        self,
        name: Optional[str],
        *,
        emoji: Optional[Union[PartialEmoji, Dict[str, Any], str]] = None,
        expires_at: Optional[datetime.datetime] = None,
        **extra: Any,
    ) -> None:
        super().__init__(**extra)
        self.name: Optional[str] = name
        self.state: Optional[str] = extra.pop('state', name)
        if self.name == 'Custom Status':
            self.name = self.state
        self.expires_at: Optional[datetime.datetime] = expires_at

        self.emoji: Optional[PartialEmoji]
        if emoji is None:
            self.emoji = emoji
        elif isinstance(emoji, dict):
            self.emoji = PartialEmoji.from_dict(emoji)
        elif isinstance(emoji, str):
            self.emoji = PartialEmoji.from_str(emoji)
        elif isinstance(emoji, PartialEmoji):
            self.emoji = emoji
        else:
            raise TypeError(f'Expected str, PartialEmoji, or None, received {type(emoji)!r} instead.')

    @property
    def type(self) -> ActivityType:
        """:class:`ActivityType`: Returns the activity's type. This is for compatibility with :class:`Activity`.

        It always returns :attr:`ActivityType.custom`.
        """
        return ActivityType.custom

    def to_dict(self) -> Dict[str, Any]:
        o: Dict[str, Any] = {'type': ActivityType.custom.value, 'state': self.name, 'name': 'Custom Status'}
        if self.emoji:
            o['emoji'] = self.emoji.to_dict()
        return o

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CustomActivity) and other.name == self.name and other.emoji == self.emoji

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash((self.name, str(self.emoji)))

    def __str__(self) -> str:
        if self.emoji:
            if self.name:
                return f'{self.emoji} {self.name}'
            return str(self.emoji)
        return str(self.name)

    def __repr__(self) -> str:
        return f'<CustomActivity name={self.name!r} emoji={self.emoji!r}>'


ActivityTypes = Union[Activity, CustomActivity, Game, Streaming, Spotify]


def create_activity(data: Optional[Dict[str, Any]], state: Any = None) -> Optional[ActivityTypes]:
    """Builds an activity from a Discord-shaped dict (used by tests and helpers)."""
    if not data:
        return None
    activity_type = try_enum(ActivityType, data.get('type', -1))
    if activity_type is ActivityType.playing and not ('application_id' in data or 'session_id' in data):
        return Game(**{k: v for k, v in data.items() if k != 'type'})
    if activity_type is ActivityType.custom:
        name = data.get('state') or data.get('name')
        return CustomActivity(name=name, emoji=data.get('emoji'))
    if activity_type is ActivityType.streaming and 'url' in data:
        return Streaming(name=data.get('name'), url=data['url'])
    return Activity(**data)


def _activity_from_presence(activity_type: Any, activity_name: Optional[str]) -> Optional[ActivityTypes]:
    """The activity a Bisim presence carries (``activityType``, ``activityName``)."""
    if not activity_name:
        return None
    kind = try_enum(ActivityType, int(activity_type or 0))
    if kind is ActivityType.playing:
        return Game(name=activity_name)
    if kind is ActivityType.streaming:
        return Streaming(name=activity_name, url='')
    return Activity(type=kind, name=activity_name)


def _custom_from_presence(text: Optional[str], emoji: Optional[str]) -> Optional[CustomActivity]:
    if not text and not emoji:
        return None
    return CustomActivity(name=text or None, emoji=emoji or None)

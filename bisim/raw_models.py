"""Raw event payloads: what ``on_raw_*`` events receive, whether or not the
message is in the cache."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Set, Tuple, Union

from . import utils
from .enums import ReactionType, Status, try_enum

if TYPE_CHECKING:
    from .member import Member
    from .message import Message
    from .partial_emoji import PartialEmoji
    from .user import User

ReactionActionEvent = Literal['REACTION_ADD', 'REACTION_REMOVE']

__all__ = (
    'RawMessageDeleteEvent',
    'RawBulkMessageDeleteEvent',
    'RawMessageUpdateEvent',
    'RawReactionActionEvent',
    'RawReactionClearEvent',
    'RawReactionClearEmojiEvent',
    'RawTypingEvent',
    'RawMemberRemoveEvent',
    'RawPollVoteActionEvent',
    'RawPresenceUpdateEvent',
    'RawAppCommandPermissionsUpdateEvent',
    'RawIntegrationDeleteEvent',
    'RawThreadUpdateEvent',
    'RawThreadMembersUpdate',
    'RawThreadDeleteEvent',
)


class _RawReprMixin:
    __slots__: Tuple[str, ...] = ()

    def __repr__(self) -> str:
        value = ' '.join(f'{attr}={getattr(self, attr)!r}' for attr in self.__slots__)
        return f'<{self.__class__.__name__} {value}>'


class RawMessageDeleteEvent(_RawReprMixin):
    """Represents the event payload for a :func:`on_raw_message_delete` event.

    Attributes
    ------------
    channel_id: :class:`int`
        The channel ID where the deletion took place.
    guild_id: Optional[:class:`int`]
        The guild ID where the deletion took place, if applicable.
    message_id: :class:`int`
        The message ID that got deleted.
    cached_message: Optional[:class:`Message`]
        The cached message, if found in the internal message cache.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id', 'cached_message')

    def __init__(self, data: Dict[str, Any]) -> None:
        self.message_id: int = int(data['id'])
        self.channel_id: int = int(data.get('channelId') or 0)
        self.cached_message: Optional[Message] = None
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))


class RawBulkMessageDeleteEvent(_RawReprMixin):
    """Represents the event payload for a :func:`on_raw_bulk_message_delete` event.

    Attributes
    -----------
    message_ids: Set[:class:`int`]
        A :class:`set` of the message IDs that were deleted.
    channel_id: :class:`int`
        The channel ID where the message got deleted.
    guild_id: Optional[:class:`int`]
        The guild ID where the message got deleted, if applicable.
    cached_messages: List[:class:`Message`]
        The cached messages, if found in the internal message cache.
    """

    __slots__ = ('message_ids', 'channel_id', 'guild_id', 'cached_messages')

    def __init__(self, data: Dict[str, Any]) -> None:
        self.message_ids: Set[int] = {int(x) for x in data.get('ids') or []}
        self.channel_id: int = int(data.get('channelId') or 0)
        self.cached_messages: List[Message] = []
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))


class RawMessageUpdateEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_message_edit` event.

    Attributes
    -----------
    message_id: :class:`int`
        The message ID that got updated.
    channel_id: :class:`int`
        The channel ID where the update took place.
    guild_id: Optional[:class:`int`]
        The guild ID where the message got updated, if applicable.
    data: :class:`dict`
        The raw data given by Bisim (the whole message).
    cached_message: Optional[:class:`Message`]
        The cached message, if found in the internal message cache. Represents the message before
        it is modified by the data in :attr:`RawMessageUpdateEvent.data`.
    message: :class:`Message`
        The updated message.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id', 'data', 'cached_message', 'message')

    def __init__(self, data: Dict[str, Any], message: Message) -> None:
        self.message_id: int = message.id
        self.channel_id: int = message.channel.id
        self.data: Dict[str, Any] = data
        self.message: Message = message
        self.cached_message: Optional[Message] = None
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId')) or getattr(message.guild, 'id', None)


class RawReactionActionEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_reaction_add` or
    :func:`on_raw_reaction_remove` event.

    Attributes
    -----------
    message_id: :class:`int`
        The message ID that got or lost a reaction.
    user_id: :class:`int`
        The user ID who added the reaction or whose reaction was removed.
    channel_id: :class:`int`
        The channel ID where the reaction got added or removed.
    guild_id: Optional[:class:`int`]
        The guild ID where the reaction got added or removed, if applicable.
    emoji: :class:`PartialEmoji`
        The custom or unicode emoji being used.
    member: Optional[:class:`Member`]
        The member who added the reaction. Only available if ``event_type`` is ``REACTION_ADD``
        and the reaction is inside a guild.
    message_author_id: Optional[:class:`int`]
        The author ID of the message being reacted to, when the message is cached.
    event_type: :class:`str`
        The event type that triggered this action. Can be
        ``REACTION_ADD`` for reaction addition or
        ``REACTION_REMOVE`` for reaction removal.
    burst: :class:`bool`
        Always ``False``.
    burst_colours: List[:class:`Colour`]
        Always empty.
    type: :class:`ReactionType`
        Always :attr:`ReactionType.normal`.
    """

    __slots__ = (
        'message_id',
        'user_id',
        'channel_id',
        'guild_id',
        'emoji',
        'event_type',
        'member',
        'message_author_id',
        'burst',
        'burst_colours',
        'type',
    )

    def __init__(self, data: Dict[str, Any], emoji: PartialEmoji, event_type: ReactionActionEvent) -> None:
        self.message_id: int = int(data['messageId'])
        self.channel_id: int = int(data.get('channelId') or 0)
        self.user_id: int = int(data['userId'])
        self.emoji: PartialEmoji = emoji
        self.event_type: ReactionActionEvent = event_type
        self.member: Optional[Member] = None
        self.message_author_id: Optional[int] = None
        self.burst: bool = False
        self.burst_colours: List[Any] = []
        self.type: ReactionType = ReactionType.normal
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))

    @property
    def burst_colors(self) -> List[Any]:
        """An alias of :attr:`burst_colours`."""
        return self.burst_colours


class RawReactionClearEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_reaction_clear` event.

    Attributes
    -----------
    message_id: :class:`int`
        The message ID that got its reactions cleared.
    channel_id: :class:`int`
        The channel ID where the reactions got cleared.
    guild_id: Optional[:class:`int`]
        The guild ID where the reactions got cleared.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id')

    def __init__(self, data: Dict[str, Any]) -> None:
        self.message_id: int = int(data['messageId'])
        self.channel_id: int = int(data.get('channelId') or 0)
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))


class RawReactionClearEmojiEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_reaction_clear_emoji` event (Bisim does not send one).

    Attributes
    -----------
    message_id: :class:`int`
        The message ID that got its reactions cleared.
    channel_id: :class:`int`
        The channel ID where the reactions got cleared.
    guild_id: Optional[:class:`int`]
        The guild ID where the reactions got cleared.
    emoji: :class:`PartialEmoji`
        The custom or unicode emoji being removed.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id', 'emoji')

    def __init__(self, data: Dict[str, Any], emoji: PartialEmoji) -> None:
        self.emoji: PartialEmoji = emoji
        self.message_id: int = int(data['messageId'])
        self.channel_id: int = int(data.get('channelId') or 0)
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))


class RawTypingEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_typing` event.

    Attributes
    -----------
    channel_id: :class:`int`
        The ID of the channel the user started typing in.
    user_id: :class:`int`
        The ID of the user that started typing.
    user: Optional[Union[:class:`bisim.User`, :class:`bisim.Member`]]
        The user that started typing, if they could be found in the internal cache.
    timestamp: :class:`datetime.datetime`
        When the typing started as an aware datetime in UTC.
    guild_id: Optional[:class:`int`]
        The ID of the guild the user started typing in, if applicable.
    """

    __slots__ = ('channel_id', 'user_id', 'user', 'timestamp', 'guild_id')

    def __init__(self, data: Dict[str, Any], /) -> None:
        self.channel_id: int = int(data.get('channelId') or 0)
        self.user_id: int = int(data['userId'])
        self.user: Optional[Union[User, Member]] = None
        raw = data.get('timestamp')
        if raw:
            millis = int(raw)
            # Bisim sends milliseconds.
            seconds = millis / 1000 if millis > 10**11 else millis
            self.timestamp: datetime.datetime = datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc)
        else:
            self.timestamp = utils.utcnow()
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))


class RawMemberRemoveEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_member_remove` event.

    Attributes
    ----------
    user: Union[:class:`bisim.User`, :class:`bisim.Member`]
        The user that left the guild.
    guild_id: :class:`int`
        The ID of the guild the user left.
    """

    __slots__ = ('user', 'guild_id')

    def __init__(self, guild_id: int, user: Union[User, Member], /) -> None:
        self.user: Union[User, Member] = user
        self.guild_id: int = guild_id


class RawPollVoteActionEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_poll_vote_add` or :func:`on_raw_poll_vote_remove`
    event.

    Attributes
    ----------
    user_id: :class:`int`
        The ID of the user that added or removed a vote.
    channel_id: :class:`int`
        The channel ID where the poll vote action took place.
    message_id: :class:`int`
        The message ID that contains the poll the user added or removed their vote on.
    guild_id: Optional[:class:`int`]
        The guild ID where the vote got added or removed, if applicable..
    answer_id: :class:`int`
        The poll answer's ID the user voted on.
    """

    __slots__ = ('user_id', 'channel_id', 'message_id', 'guild_id', 'answer_id')

    def __init__(self, data: Dict[str, Any], answer_id: int) -> None:
        self.user_id: int = int(data['userId'])
        self.channel_id: int = int(data.get('channelId') or 0)
        self.message_id: int = int(data['messageId'])
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))
        self.answer_id: int = int(answer_id)


class RawPresenceUpdateEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_presence_update` event.

    Attributes
    ----------
    user_id: :class:`int`
        The ID of the user that triggered the presence update.
    guild_id: Optional[:class:`int`]
        The guild ID for the users presence update.
    guild: Optional[:class:`Guild`]
        The guild associated with the presence update and user.
    status: :class:`Status`
        The updated status of the user.
    activities: Tuple[Union[:class:`BaseActivity`, :class:`Spotify`]]
        The activities the user is currently doing.
    """

    __slots__ = ('user_id', 'guild_id', 'guild', 'status', 'activities', 'client_status')

    def __init__(self, *, data: Dict[str, Any], state: Any) -> None:
        from .activity import _activity_from_presence, _custom_from_presence

        self.user_id: int = int(data['userId'])
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))
        self.guild: Any = state._get_guild(self.guild_id)
        status = data.get('status') or 'offline'
        self.status: Status = try_enum(Status, 'offline' if status == 'invisible' else status)
        activity = _activity_from_presence(data.get('activityType'), data.get('activityName'))
        custom = _custom_from_presence(data.get('customText'), data.get('customEmoji'))
        self.activities: Tuple[Any, ...] = tuple(a for a in (activity, custom) if a is not None)
        self.client_status: Any = None


class RawAppCommandPermissionsUpdateEvent(_RawReprMixin):
    """Not sent by Bisim; kept so the name imports."""

    __slots__ = ()


class RawIntegrationDeleteEvent(_RawReprMixin):
    """Not sent by Bisim; kept so the name imports."""

    __slots__ = ()


class RawThreadUpdateEvent(_RawReprMixin):
    """Not sent by Bisim (no threads); kept so the name imports."""

    __slots__ = ()


class RawThreadMembersUpdate(_RawReprMixin):
    """Not sent by Bisim (no threads); kept so the name imports."""

    __slots__ = ()


class RawThreadDeleteEvent(_RawReprMixin):
    """Not sent by Bisim (no threads); kept so the name imports."""

    __slots__ = ()

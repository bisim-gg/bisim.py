from __future__ import annotations

import asyncio
import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
    overload,
)

from . import abc, utils
from .asset import Asset
from .enums import ChannelType, VideoQualityMode, try_enum
from .errors import ClientException, NotSupported
from .flags import ChannelFlags
from .mixins import Hashable
from .object import Object
from .permissions import PermissionOverwrite, Permissions

if TYPE_CHECKING:
    from typing_extensions import Self

    from .guild import Guild
    from .member import Member, VoiceState
    from .message import Message, PartialMessage
    from .role import Role
    from .state import ConnectionState
    from .user import BaseUser, ClientUser, User
    from .webhook import Webhook

__all__ = (
    'TextChannel',
    'VoiceChannel',
    'StageChannel',
    'DMChannel',
    'CategoryChannel',
    'ForumTag',
    'ForumChannel',
    'GroupChannel',
    'PartialMessageable',
    'Thread',
    'ThreadMember',
    'MediaChannel',
)


async def _single_delete_strategy(messages: Iterable[Message], *, reason: Optional[str] = None) -> None:
    for m in messages:
        await m.delete()


class TextChannel(abc.Messageable, abc.GuildChannel, Hashable):
    """Represents a Bisim guild text channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns the channel's name.

    Attributes
    -----------
    name: :class:`str`
        The channel name.
    guild: :class:`Guild`
        The guild the channel belongs to.
    id: :class:`int`
        The channel ID.
    category_id: Optional[:class:`int`]
        The category channel ID this channel belongs to, if applicable.
    topic: Optional[:class:`str`]
        The channel's topic. ``None`` if it doesn't exist.
    position: :class:`int`
        The position in the channel list. This is a number that starts at 0. e.g. the
        top channel is position 0.
    last_message_id: Optional[:class:`int`]
        The last message ID of the message sent to this channel. It may
        *not* point to an existing or valid message.
    slowmode_delay: :class:`int`
        The number of seconds a member must wait between sending messages
        in this channel. A value of ``0`` denotes that it is disabled.
    nsfw: :class:`bool`
        If the channel is marked as "not safe for work" or "age restricted".
    default_auto_archive_duration: :class:`int`
        Kept for compatibility (Bisim has no threads).
    default_thread_slowmode_delay: :class:`int`
        Kept for compatibility (Bisim has no threads).
    """

    __slots__ = (
        'name',
        'id',
        'guild',
        'topic',
        '_state',
        'nsfw',
        'category_id',
        'position',
        'slowmode_delay',
        '_overwrites',
        '_overwrites_loaded',
        '_permissions_synced',
        '_my_permissions',
        '_is_private',
        '_type',
        'last_message_id',
        'default_auto_archive_duration',
        'default_thread_slowmode_delay',
        '_created_at',
    )

    def __init__(self, *, state: ConnectionState, guild: Guild, data: Dict[str, Any]):
        self._state: ConnectionState = state
        self.id: int = int(data['id'])
        self._type: int = ChannelType.text.value
        self._update(guild, data)

    def __repr__(self) -> str:
        attrs = [
            ('id', self.id),
            ('name', self.name),
            ('position', self.position),
            ('nsfw', self.nsfw),
            ('news', self.is_news()),
            ('category_id', self.category_id),
        ]
        joined = ' '.join('%s=%r' % t for t in attrs)
        return f'<{self.__class__.__name__} {joined}>'

    def _update(self, guild: Guild, data: Dict[str, Any]) -> None:
        self._update_common(guild, data)
        self.topic: Optional[str] = data.get('topic') or None
        self.nsfw: bool = bool(data.get('nsfw', False))
        self.slowmode_delay: int = utils._int(data.get('slowmodeSec'), 0)
        self.last_message_id: Optional[int] = utils._snowflake(data.get('lastMessageId'))
        self.default_auto_archive_duration: int = 1440
        self.default_thread_slowmode_delay: int = 0
        self._created_at = utils.parse_time(data.get('createdAt'))

    def _update_from_event(self, data: Dict[str, Any]) -> None:
        super()._update_from_event(data)
        self.topic = data.get('topic') or None
        self.nsfw = bool(data.get('nsfw', False))
        self.slowmode_delay = utils._int(data.get('slowmodeSec'), 0)

    async def _get_channel(self) -> Self:
        return self

    @property
    def type(self) -> ChannelType:
        """:class:`ChannelType`: The channel's Bisim type."""
        return ChannelType.text

    @property
    def _sorting_bucket(self) -> int:
        return ChannelType.text.value

    @property
    def _scheduled_event_entity_type(self) -> None:
        return None

    def permissions_for(self, obj: Union[Member, Role], /) -> Permissions:
        base = super().permissions_for(obj)
        # Text channels have no voice.
        denied = Permissions.voice()
        base.value &= ~denied.value
        return base

    permissions_for.__doc__ = abc.GuildChannel.permissions_for.__doc__

    @property
    def members(self) -> List[Member]:
        """List[:class:`Member`]: Returns all members that can see this channel."""
        return [m for m in self.guild.members if self.permissions_for(m).read_messages]

    @property
    def threads(self) -> List[Thread]:
        """List[:class:`Thread`]: Always empty: Bisim has no threads."""
        return []

    def is_nsfw(self) -> bool:
        """:class:`bool`: Checks if the channel is NSFW."""
        return self.nsfw

    def is_news(self) -> bool:
        """:class:`bool`: Always ``False``: Bisim has no announcement channels."""
        return False

    @property
    def last_message(self) -> Optional[Message]:
        """Retrieves the last message from this channel in cache.

        The message might not be valid or point to an existing message.

        Returns
        ---------
        Optional[:class:`Message`]
            The last message in this channel or ``None`` if not found.
        """
        return self._state._get_message(self.last_message_id) if self.last_message_id else None

    @property
    def flags(self) -> ChannelFlags:
        """:class:`ChannelFlags`: The flags associated with this channel."""
        return ChannelFlags._from_value(0)

    async def edit(
        self,
        *,
        reason: Optional[str] = None,
        name: str = utils.MISSING,
        topic: Optional[str] = utils.MISSING,
        position: int = utils.MISSING,
        nsfw: bool = utils.MISSING,
        sync_permissions: bool = utils.MISSING,
        category: Optional[CategoryChannel] = utils.MISSING,
        slowmode_delay: int = utils.MISSING,
        default_auto_archive_duration: int = utils.MISSING,
        default_thread_slowmode_delay: int = utils.MISSING,
        type: ChannelType = utils.MISSING,
        overwrites: Mapping[Union[Role, Member, abc.Snowflake], PermissionOverwrite] = utils.MISSING,
    ) -> Optional[TextChannel]:
        """|coro|

        Edits the channel.

        You must have :attr:`~Permissions.manage_channels` to do this.

        Parameters
        ----------
        name: :class:`str`
            The new channel name.
        topic: :class:`str`
            The new channel's topic.
        position: :class:`int`
            The new channel's position.
        nsfw: :class:`bool`
            To mark the channel as NSFW or not.
        sync_permissions: :class:`bool`
            Whether to sync permissions with the channel's new or pre-existing
            category. Defaults to ``False``.
        category: Optional[:class:`CategoryChannel`]
            The new category for this channel. Can be ``None`` to remove the
            category.
        slowmode_delay: :class:`int`
            Specifies the slowmode rate limit for user in this channel, in seconds.
            A value of ``0`` disables slowmode.
        type: :class:`ChannelType`
            Not supported on Bisim.
        reason: Optional[:class:`str`]
            The reason for editing this channel. Shows up on the audit log.
        overwrites: :class:`Mapping`
            A :class:`Mapping` of target (either a role or a member) to
            :class:`PermissionOverwrite` to apply to the channel.
        default_auto_archive_duration: :class:`int`
            Not supported on Bisim (no threads).
        default_thread_slowmode_delay: :class:`int`
            Not supported on Bisim (no threads).

        Raises
        ------
        ValueError
            The new ``position`` is less than 0 or greater than the number of channels.
        TypeError
            The permission overwrite information is not in proper form.
        Forbidden
            You do not have permissions to edit the channel.
        HTTPException
            Editing the channel failed.
        NotSupported
            An option Bisim does not have was given.

        Returns
        --------
        Optional[:class:`.TextChannel`]
            The newly edited text channel. If the edit was only positional
            then ``None`` is returned instead.
        """
        payload = await self._edit(
            {
                'name': name,
                'topic': topic,
                'position': position,
                'nsfw': nsfw,
                'sync_permissions': sync_permissions,
                'category': category,
                'slowmode_delay': slowmode_delay,
                'default_auto_archive_duration': default_auto_archive_duration,
                'default_thread_slowmode_delay': default_thread_slowmode_delay,
                'type': type,
                'overwrites': overwrites,
            },
            reason=reason,
        )
        if isinstance(payload, dict) and payload.get('id'):
            self._update(self.guild, payload)
            return self
        return None

    async def clone(
        self,
        *,
        name: Optional[str] = None,
        category: Optional[CategoryChannel] = utils.MISSING,
        reason: Optional[str] = None,
    ) -> TextChannel:
        base: Dict[str, Any] = {}
        if self.topic:
            base['topic'] = self.topic
        return await self._clone_impl(base, name=name, category=category, reason=reason)

    clone.__doc__ = abc.GuildChannel.clone.__doc__

    async def delete_messages(self, messages: Iterable[abc.Snowflake], *, reason: Optional[str] = None) -> None:
        """|coro|

        Deletes a list of messages. This is similar to :meth:`Message.delete`
        except it bulk deletes multiple messages.

        As a special case, if the number of messages is 0, then nothing
        is done. If the number of messages is 1 then single message
        delete is done. If it's more than two, then bulk delete is used.

        You cannot bulk delete more than 100 messages.

        You must have :attr:`~Permissions.manage_messages` to do this.

        Parameters
        -----------
        messages: Iterable[:class:`abc.Snowflake`]
            An iterable of messages denoting which ones to bulk delete.
        reason: Optional[:class:`str`]
            The reason for deleting the messages. Shows up on the audit log.

        Raises
        ------
        ClientException
            The number of messages to delete was more than 100.
        Forbidden
            You do not have proper permissions to delete the messages.
        NotFound
            If single delete, then the message was already deleted.
        HTTPException
            Deleting the messages failed.
        """
        if not isinstance(messages, (list, tuple)):
            messages = list(messages)

        if len(messages) == 0:
            return

        if len(messages) == 1:
            message_id: int = messages[0].id
            await self._state.http.delete_message(self.id, message_id, reason=reason)
            return

        if len(messages) > 100:
            raise ClientException('Can only bulk delete messages up to 100 messages')

        message_ids = [m.id for m in messages]
        await self._state.http.delete_messages(self.id, message_ids, reason=reason)

    async def purge(
        self,
        *,
        limit: Optional[int] = 100,
        check: Callable[[Message], bool] = utils.MISSING,
        before: Optional[Union[abc.Snowflake, datetime.datetime]] = None,
        after: Optional[Union[abc.Snowflake, datetime.datetime]] = None,
        around: Optional[Union[abc.Snowflake, datetime.datetime]] = None,
        oldest_first: Optional[bool] = None,
        bulk: bool = True,
        reason: Optional[str] = None,
    ) -> List[Message]:
        """|coro|

        Purges a list of messages that meet the criteria given by the predicate
        ``check``. If a ``check`` is not provided then all messages are deleted
        without discrimination.

        You must have :attr:`~Permissions.manage_messages` to
        delete messages even if they are your own.
        Having :attr:`~Permissions.read_message_history` is
        also needed to retrieve message history.

        Examples
        ---------

        Deleting bot's messages ::

            def is_me(m):
                return m.author == client.user

            deleted = await channel.purge(limit=100, check=is_me)
            await channel.send(f'Deleted {len(deleted)} message(s)')

        Parameters
        -----------
        limit: Optional[:class:`int`]
            The number of messages to search through. This is not the number
            of messages that will be deleted, though it can be.
        check: Callable[[:class:`Message`], :class:`bool`]
            The function used to check if a message should be deleted.
            It must take a :class:`Message` as its sole parameter.
        before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``before`` in :meth:`history`.
        after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``after`` in :meth:`history`.
        around: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``around`` in :meth:`history`.
        oldest_first: Optional[:class:`bool`]
            Same as ``oldest_first`` in :meth:`history`.
        bulk: :class:`bool`
            If ``True``, use bulk delete. Setting this to ``False`` is useful for mass-deleting
            a bot's own messages without :attr:`Permissions.manage_messages`.
        reason: Optional[:class:`str`]
            The reason for purging the messages. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have proper permissions to do the actions required.
        HTTPException
            Purging the messages failed.

        Returns
        --------
        List[:class:`.Message`]
            The list of messages that were deleted.
        """
        if check is utils.MISSING:
            check = lambda m: True

        iterator = self.history(limit=limit, before=before, after=after, oldest_first=oldest_first, around=around)
        ret: List[Message] = []
        to_delete: List[Message] = []

        async for message in iterator:
            if not check(message):
                continue
            to_delete.append(message)
            if bulk and len(to_delete) == 100:
                await self.delete_messages(to_delete, reason=reason)
                ret.extend(to_delete)
                to_delete = []

        if to_delete:
            if bulk:
                await self.delete_messages(to_delete, reason=reason)
            else:
                await _single_delete_strategy(to_delete, reason=reason)
            ret.extend(to_delete)

        return ret

    async def webhooks(self) -> List[Webhook]:
        """|coro|

        Gets the list of webhooks from this channel.

        You must have :attr:`~.Permissions.manage_webhooks` to do this.

        Raises
        -------
        Forbidden
            You don't have permissions to get the webhooks.

        Returns
        --------
        List[:class:`Webhook`]
            The webhooks for this channel.
        """
        from .webhook import Webhook

        data = await self._state.http.channel_webhooks(self.id)
        return [Webhook.from_state(d, state=self._state) for d in data or []]

    async def create_webhook(self, *, name: str, avatar: Optional[bytes] = None, reason: Optional[str] = None) -> Webhook:
        """|coro|

        Creates a webhook for this channel.

        You must have :attr:`~.Permissions.manage_webhooks` to do this.

        Parameters
        -------------
        name: :class:`str`
            The webhook's name.
        avatar: Optional[:class:`bytes`]
            Not supported on Bisim.
        reason: Optional[:class:`str`]
            The reason for creating this webhook. Shows up in the audit logs.

        Raises
        -------
        HTTPException
            Creating the webhook failed.
        Forbidden
            You do not have permissions to create a webhook.
        NotSupported
            An avatar was given.

        Returns
        --------
        :class:`Webhook`
            The created webhook.
        """
        from .webhook import Webhook

        if avatar is not None:
            raise NotSupported('Webhook avatars')
        data = await self._state.http.create_webhook(self.id, name=str(name), reason=reason)
        return Webhook.from_state(data, state=self._state)

    async def follow(self, *, destination: TextChannel, reason: Optional[str] = None) -> Webhook:
        """|coro|

        Not supported on Bisim (no announcement channels).
        """
        raise NotSupported('Following announcement channels')

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID.

        This is useful if you want to work with a message and only have its ID without
        doing an unnecessary API call.

        Parameters
        ------------
        message_id: :class:`int`
            The message ID to create a partial message for.

        Returns
        ---------
        :class:`PartialMessage`
            The partial message.
        """
        from .message import PartialMessage

        return PartialMessage(channel=self, id=message_id)

    def get_thread(self, thread_id: int, /) -> None:
        """Always ``None``: Bisim has no threads."""
        return None

    async def create_thread(self, **kwargs: Any) -> Thread:
        """|coro|

        Not supported on Bisim (no threads).
        """
        raise NotSupported('Threads')

    async def archived_threads(self, **kwargs: Any) -> AsyncIterator[Thread]:
        """Not supported on Bisim (no threads)."""
        raise NotSupported('Threads')
        yield  # pragma: no cover


class VoiceChannel(abc.Connectable, abc.GuildChannel, Hashable):
    """Represents a Bisim guild voice channel.

    A bot cannot join voice on Bisim, and Bisim's voice channels have no
    text chat, so :meth:`connect` and :meth:`send` raise
    :exc:`~bisim.NotSupported`. The bot can see who is in the channel and
    move, mute or disconnect them.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns the channel's name.

    Attributes
    -----------
    name: :class:`str`
        The channel name.
    guild: :class:`Guild`
        The guild the channel belongs to.
    id: :class:`int`
        The channel ID.
    nsfw: :class:`bool`
        If the channel is marked as "not safe for work" or "age restricted".
    category_id: Optional[:class:`int`]
        The category channel ID this channel belongs to, if applicable.
    position: :class:`int`
        The position in the channel list. This is a number that starts at 0. e.g. the
        top channel is position 0.
    bitrate: :class:`int`
        Kept for compatibility (Bisim does not expose it).
    user_limit: :class:`int`
        Kept for compatibility: ``0`` (no limit).
    rtc_region: Optional[:class:`str`]
        Always ``None``.
    video_quality_mode: :class:`VideoQualityMode`
        Always :attr:`VideoQualityMode.auto`.
    status: Optional[:class:`str`]
        The voice channel's status line, if any.
    """

    __slots__ = (
        'name',
        'id',
        'guild',
        'nsfw',
        'bitrate',
        'user_limit',
        '_state',
        'position',
        'slowmode_delay',
        '_overwrites',
        '_overwrites_loaded',
        '_permissions_synced',
        '_my_permissions',
        '_is_private',
        'category_id',
        'rtc_region',
        'video_quality_mode',
        'last_message_id',
        'status',
        '_created_at',
    )

    def __init__(self, *, state: ConnectionState, guild: Guild, data: Dict[str, Any]):
        self._state: ConnectionState = state
        self.id: int = int(data['id'])
        self._update(guild, data)

    def __repr__(self) -> str:
        attrs = [
            ('id', self.id),
            ('name', self.name),
            ('status', self.status),
            ('position', self.position),
            ('category_id', self.category_id),
        ]
        joined = ' '.join('%s=%r' % t for t in attrs)
        return f'<{self.__class__.__name__} {joined}>'

    def _update(self, guild: Guild, data: Dict[str, Any]) -> None:
        self._update_common(guild, data)
        self.nsfw: bool = bool(data.get('nsfw', False))
        self.bitrate: int = utils._int(data.get('bitrate'), 64000)
        self.user_limit: int = utils._int(data.get('userLimit'), 0)
        self.rtc_region: Optional[str] = None
        self.video_quality_mode: VideoQualityMode = VideoQualityMode.auto
        self.slowmode_delay: int = utils._int(data.get('slowmodeSec'), 0)
        self.last_message_id: Optional[int] = None
        if not hasattr(self, 'status'):
            self.status: Optional[str] = data.get('voiceStatus') or None
        self._created_at = utils.parse_time(data.get('createdAt'))

    def _update_from_event(self, data: Dict[str, Any]) -> None:
        super()._update_from_event(data)
        self.nsfw = bool(data.get('nsfw', False))

    @property
    def type(self) -> ChannelType:
        """:class:`ChannelType`: The channel's Bisim type."""
        return ChannelType.voice

    @property
    def _sorting_bucket(self) -> int:
        return ChannelType.voice.value

    def is_nsfw(self) -> bool:
        """:class:`bool`: Checks if the channel is NSFW."""
        return self.nsfw

    @property
    def members(self) -> List[Member]:
        """List[:class:`Member`]: Returns all members that are currently inside this voice channel."""
        ret = []
        for user_id, state in self.guild._voice_states.items():
            if state.channel and state.channel.id == self.id:
                member = self.guild.get_member(user_id)
                if member is not None:
                    ret.append(member)
        return ret

    @property
    def voice_states(self) -> Dict[int, VoiceState]:
        """Returns a mapping of member IDs who have voice states in this channel.

        Returns
        --------
        Mapping[:class:`int`, :class:`VoiceState`]
            The mapping of member ID to a voice state.
        """
        return {
            key: value
            for key, value in self.guild._voice_states.items()
            if value.channel and value.channel.id == self.id
        }

    @property
    def scheduled_events(self) -> List[Any]:
        """List[Any]: Always empty: Bisim has no scheduled events."""
        return []

    def permissions_for(self, obj: Union[Member, Role], /) -> Permissions:
        base = super().permissions_for(obj)
        # Without Connect, nothing else in a voice channel can be used.
        if not base.connect:
            denied = Permissions.voice()
            denied.update(manage_channels=True, manage_roles=True)
            base.value &= ~denied.value
        return base

    permissions_for.__doc__ = abc.GuildChannel.permissions_for.__doc__

    async def send(self, *args: Any, **kwargs: Any) -> Message:
        """|coro|

        Not supported on Bisim: voice channels have no text chat.
        """
        raise NotSupported('Text chat in voice channels')

    async def history(self, *args: Any, **kwargs: Any) -> AsyncIterator[Message]:
        """Not supported on Bisim: voice channels have no text chat."""
        raise NotSupported('Text chat in voice channels')
        yield  # pragma: no cover

    async def fetch_message(self, id: int, /) -> Message:
        """|coro|

        Not supported on Bisim: voice channels have no text chat.
        """
        raise NotSupported('Text chat in voice channels')

    def typing(self) -> Any:
        """Not supported on Bisim: voice channels have no text chat."""
        raise NotSupported('Text chat in voice channels')

    async def edit(
        self,
        *,
        reason: Optional[str] = None,
        name: str = utils.MISSING,
        nsfw: bool = utils.MISSING,
        bitrate: int = utils.MISSING,
        user_limit: int = utils.MISSING,
        position: int = utils.MISSING,
        sync_permissions: bool = utils.MISSING,
        category: Optional[CategoryChannel] = utils.MISSING,
        overwrites: Mapping[Union[Role, Member, abc.Snowflake], PermissionOverwrite] = utils.MISSING,
        rtc_region: Optional[Any] = utils.MISSING,
        video_quality_mode: VideoQualityMode = utils.MISSING,
        slowmode_delay: int = utils.MISSING,
        status: Optional[str] = utils.MISSING,
    ) -> Optional[VoiceChannel]:
        """|coro|

        Edits the channel.

        You must have :attr:`~Permissions.manage_channels` to do this.

        Parameters
        ----------
        name: :class:`str`
            The new channel's name.
        position: :class:`int`
            The new channel's position.
        nsfw: :class:`bool`
            To mark the channel as NSFW or not.
        sync_permissions: :class:`bool`
            Whether to sync permissions with the channel's new or pre-existing
            category. Defaults to ``False``.
        category: Optional[:class:`CategoryChannel`]
            The new category for this channel. Can be ``None`` to remove the
            category.
        reason: Optional[:class:`str`]
            The reason for editing this channel. Shows up on the audit log.
        overwrites: :class:`Mapping`
            A :class:`Mapping` of target (either a role or a member) to
            :class:`PermissionOverwrite` to apply to the channel.
        bitrate: :class:`int`
            Not supported on Bisim.
        user_limit: :class:`int`
            Not supported on Bisim.
        rtc_region: Optional[:class:`str`]
            Not supported on Bisim.
        video_quality_mode: :class:`VideoQualityMode`
            Not supported on Bisim.
        status: Optional[:class:`str`]
            Not supported for bots on Bisim.

        Raises
        ------
        TypeError
            If the permission overwrite information is not in proper form.
        Forbidden
            You do not have permissions to edit the channel.
        HTTPException
            Editing the channel failed.
        NotSupported
            An option Bisim does not have was given.

        Returns
        --------
        Optional[:class:`.VoiceChannel`]
            The newly edited voice channel. If the edit was only positional
            then ``None`` is returned instead.
        """
        payload = await self._edit(
            {
                'name': name,
                'nsfw': nsfw,
                'bitrate': bitrate,
                'user_limit': user_limit,
                'position': position,
                'sync_permissions': sync_permissions,
                'category': category,
                'overwrites': overwrites,
                'rtc_region': rtc_region,
                'video_quality_mode': video_quality_mode,
                'slowmode_delay': slowmode_delay,
                'status': status,
            },
            reason=reason,
        )
        if isinstance(payload, dict) and payload.get('id'):
            self._update(self.guild, payload)
            return self
        return None

    async def clone(
        self,
        *,
        name: Optional[str] = None,
        category: Optional[CategoryChannel] = utils.MISSING,
        reason: Optional[str] = None,
    ) -> VoiceChannel:
        return await self._clone_impl({}, name=name, category=category, reason=reason)

    clone.__doc__ = abc.GuildChannel.clone.__doc__


class StageChannel:
    """Not on Bisim (no stage channels); kept so ``isinstance`` checks still run."""

    __slots__ = ()


class ForumTag:
    """Not on Bisim (no forum channels); kept so the name imports."""

    __slots__ = ()


class ForumChannel:
    """Not on Bisim (no forum channels); kept so ``isinstance`` checks still run."""

    __slots__ = ()


class MediaChannel:
    """Not on Bisim (no media channels); kept so ``isinstance`` checks still run."""

    __slots__ = ()


class Thread:
    """Not on Bisim (no threads); kept so ``isinstance`` checks still run."""

    __slots__ = ()


class ThreadMember:
    """Not on Bisim (no threads); kept so the name imports."""

    __slots__ = ()


class CategoryChannel(abc.GuildChannel, Hashable):
    """Represents a Bisim channel category.

    These are useful to group channels to logical compartments.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the category's hash.

        .. describe:: str(x)

            Returns the category's name.

    Attributes
    -----------
    name: :class:`str`
        The category name.
    guild: :class:`Guild`
        The guild the category belongs to.
    id: :class:`int`
        The category channel ID.
    position: :class:`int`
        The position in the category list. This is a number that starts at 0. e.g. the
        top category is position 0.
    nsfw: :class:`bool`
        If the channel is marked as "not safe for work".
    """

    __slots__ = (
        'name',
        'id',
        'guild',
        'nsfw',
        '_state',
        'position',
        '_overwrites',
        '_overwrites_loaded',
        '_permissions_synced',
        '_my_permissions',
        '_is_private',
        'category_id',
        '_created_at',
    )

    def __init__(self, *, state: ConnectionState, guild: Guild, data: Dict[str, Any]):
        self._state: ConnectionState = state
        self.id: int = int(data['id'])
        self._update(guild, data)

    def __repr__(self) -> str:
        return f'<CategoryChannel id={self.id} name={self.name!r} position={self.position} nsfw={self.nsfw}>'

    def _update(self, guild: Guild, data: Dict[str, Any]) -> None:
        self._update_common(guild, data)
        self.category_id = None
        self.nsfw: bool = bool(data.get('nsfw', False))
        self._created_at = utils.parse_time(data.get('createdAt'))

    def _update_from_event(self, data: Dict[str, Any]) -> None:
        super()._update_from_event(data)
        self.category_id = None
        self.nsfw = bool(data.get('nsfw', False))

    @property
    def _sorting_bucket(self) -> int:
        return ChannelType.category.value

    @property
    def type(self) -> ChannelType:
        """:class:`ChannelType`: The channel's Bisim type."""
        return ChannelType.category

    def is_nsfw(self) -> bool:
        """:class:`bool`: Checks if the category is NSFW."""
        return self.nsfw

    async def clone(
        self,
        *,
        name: Optional[str] = None,
        category: Optional[CategoryChannel] = None,
        reason: Optional[str] = None,
    ) -> CategoryChannel:
        return await self._clone_impl({}, name=name, category=None, reason=reason)

    clone.__doc__ = abc.GuildChannel.clone.__doc__

    async def edit(
        self,
        *,
        reason: Optional[str] = None,
        name: str = utils.MISSING,
        position: int = utils.MISSING,
        nsfw: bool = utils.MISSING,
        overwrites: Mapping[Union[Role, Member, abc.Snowflake], PermissionOverwrite] = utils.MISSING,
    ) -> Optional[CategoryChannel]:
        """|coro|

        Edits the channel.

        You must have :attr:`~Permissions.manage_channels` to do this.

        Parameters
        ----------
        name: :class:`str`
            The new category's name.
        position: :class:`int`
            The new category's position.
        nsfw: :class:`bool`
            To mark the category as NSFW or not.
        reason: Optional[:class:`str`]
            The reason for editing this category. Shows up on the audit log.
        overwrites: :class:`Mapping`
            A :class:`Mapping` of target (either a role or a member) to
            :class:`PermissionOverwrite` to apply to the channel.

        Raises
        ------
        ValueError
            If position is less than 0 or greater than the number of categories.
        TypeError
            The overwrite information is not in proper form.
        Forbidden
            You do not have permissions to edit the category.
        HTTPException
            Editing the category failed.

        Returns
        --------
        Optional[:class:`.CategoryChannel`]
            The newly edited category channel. If the edit was only positional
            then ``None`` is returned instead.
        """
        payload = await self._edit(
            {'name': name, 'position': position, 'nsfw': nsfw, 'overwrites': overwrites}, reason=reason
        )
        if isinstance(payload, dict) and payload.get('id'):
            self._update(self.guild, payload)
            return self
        return None

    async def move(self, **kwargs: Any) -> None:
        kwargs.pop('category', None)
        await super().move(**kwargs)

    move.__doc__ = abc.GuildChannel.move.__doc__

    @property
    def channels(self) -> List[abc.GuildChannel]:
        """List[:class:`abc.GuildChannel`]: Returns the channels that are under this category.

        These are sorted by the official Bisim UI, which places voice channels below the text channels.
        """

        def comparator(channel: abc.GuildChannel) -> Tuple[bool, int]:
            return (not isinstance(channel, TextChannel), channel.position)

        ret = [c for c in self.guild.channels if c.category_id == self.id]
        ret.sort(key=comparator)
        return ret

    @property
    def text_channels(self) -> List[TextChannel]:
        """List[:class:`TextChannel`]: Returns the text channels that are under this category."""
        ret = [c for c in self.guild.channels if c.category_id == self.id and isinstance(c, TextChannel)]
        ret.sort(key=lambda c: (c.position, c.id))
        return ret

    @property
    def voice_channels(self) -> List[VoiceChannel]:
        """List[:class:`VoiceChannel`]: Returns the voice channels that are under this category."""
        ret = [c for c in self.guild.channels if c.category_id == self.id and isinstance(c, VoiceChannel)]
        ret.sort(key=lambda c: (c.position, c.id))
        return ret

    @property
    def stage_channels(self) -> List[StageChannel]:
        """List[:class:`StageChannel`]: Always empty: Bisim has no stage channels."""
        return []

    @property
    def forums(self) -> List[ForumChannel]:
        """List[:class:`ForumChannel`]: Always empty: Bisim has no forum channels."""
        return []

    async def create_text_channel(self, name: str, **options: Any) -> TextChannel:
        """|coro|

        A shortcut method to :meth:`Guild.create_text_channel` to create a :class:`TextChannel` in the category.

        Returns
        -------
        :class:`TextChannel`
            The channel that was just created.
        """
        return await self.guild.create_text_channel(name, category=self, **options)

    async def create_voice_channel(self, name: str, **options: Any) -> VoiceChannel:
        """|coro|

        A shortcut method to :meth:`Guild.create_voice_channel` to create a :class:`VoiceChannel` in the category.

        Returns
        -------
        :class:`VoiceChannel`
            The channel that was just created.
        """
        return await self.guild.create_voice_channel(name, category=self, **options)

    async def create_stage_channel(self, name: str, **options: Any) -> StageChannel:
        """|coro|

        Not supported on Bisim (no stage channels).
        """
        raise NotSupported('Stage channels')

    async def create_forum(self, name: str, **options: Any) -> ForumChannel:
        """|coro|

        Not supported on Bisim (no forum channels).
        """
        raise NotSupported('Forum channels')


class DMChannel(abc.Messageable, abc.PrivateChannel, Hashable):
    """Represents a Bisim direct message channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns a string representation of the channel

    Attributes
    ----------
    recipient: Optional[:class:`User`]
        The user you are participating with in the direct message channel.
        If this channel is received through the gateway, the recipient information
        may not be always available.
    recipients: List[:class:`User`]
        The users you are participating with in the DM channel.
    me: :class:`ClientUser`
        The user presenting yourself.
    id: :class:`int`
        The direct message channel ID.
    last_message_id: Optional[:class:`int`]
        The last message ID of the message sent to this channel.
    """

    __slots__ = ('id', 'recipients', 'me', '_state', 'last_message_id', '_created_at')

    def __init__(self, *, me: ClientUser, state: ConnectionState, data: Dict[str, Any]):
        self._state: ConnectionState = state
        self.recipients: List[User] = []
        for participant in data.get('participants') or data.get('recipients') or []:
            user = state.store_user(participant)
            if user.id != me.id:
                self.recipients.append(user)
        self.me: ClientUser = me
        self.id: int = int(data['id'])
        self.last_message_id: Optional[int] = utils._snowflake(data.get('lastMessageId'))
        self._created_at = utils.parse_time(data.get('createdAt'))

    def _update(self, data: Dict[str, Any]) -> None:
        participants = data.get('participants')
        if participants:
            self.recipients = [self._state.store_user(p) for p in participants if int(p['id']) != self.me.id]
        self.last_message_id = utils._snowflake(data.get('lastMessageId'))

    async def _get_channel(self) -> Self:
        return self

    def __str__(self) -> str:
        if self.recipient:
            return f'Direct Message with {self.recipient}'
        return 'Direct Message with Unknown User'

    def __repr__(self) -> str:
        return f'<DMChannel id={self.id} recipient={self.recipient!r}>'

    @classmethod
    def _from_message(cls, state: ConnectionState, channel_id: int, recipient: Optional[User] = None) -> Self:
        self = cls.__new__(cls)
        self._state = state
        self.id = channel_id
        self.recipients = [recipient] if recipient is not None else []
        self.me = state.user  # type: ignore
        self.last_message_id = None
        self._created_at = None
        return self

    @property
    def recipient(self) -> Optional[User]:
        """Optional[:class:`User`]: The user you are participating with in the direct message channel."""
        if self.recipients:
            return self.recipients[0]
        return None

    @property
    def type(self) -> ChannelType:
        """:class:`ChannelType`: The channel's Bisim type."""
        return ChannelType.private

    @property
    def guild(self) -> None:
        """Always ``None``: a DM is not in a server."""
        return None

    @property
    def jump_url(self) -> str:
        """:class:`str`: Returns a URL that allows the client to jump to the channel."""
        return f'{utils.WEB_URL}/channels/@me/{self.id}'

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the direct message channel's creation time in UTC."""
        return utils.snowflake_time(self.id)

    def permissions_for(self, obj: Any = None, /) -> Permissions:
        """Handles permission resolution for a :class:`User`.

        This function is there for compatibility with other channel types.

        Actual direct messages do not really have the concept of permissions.

        This returns all the Text related permissions set to ``True`` except:

        - :attr:`~Permissions.send_tts_messages`: You cannot send TTS messages in a DM.
        - :attr:`~Permissions.manage_messages`: You cannot delete others messages in a DM.

        Parameters
        -----------
        obj: :class:`User`
            The user to check permissions for. This parameter is ignored
            but kept for compatibility with other ``permissions_for`` methods.

        Returns
        --------
        :class:`Permissions`
            The resolved permissions.
        """
        return Permissions._dm_permissions()

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID.

        This is useful if you want to work with a message and only have its ID without
        doing an unnecessary API call.

        Parameters
        ------------
        message_id: :class:`int`
            The message ID to create a partial message for.

        Returns
        ---------
        :class:`PartialMessage`
            The partial message.
        """
        from .message import PartialMessage

        return PartialMessage(channel=self, id=message_id)


class GroupChannel(abc.Messageable, abc.PrivateChannel, Hashable):
    """Represents a Bisim group channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns a string representation of the channel

    Attributes
    ----------
    recipients: List[:class:`User`]
        The users you are participating with in the group channel.
    me: :class:`ClientUser`
        The user presenting yourself.
    id: :class:`int`
        The group channel ID.
    owner_id: :class:`int`
        The owner ID that owns the group channel.
    name: Optional[:class:`str`]
        The group channel's name if provided.
    """

    __slots__ = ('id', 'recipients', 'owner_id', '_icon', 'name', 'me', '_state', 'last_message_id')

    def __init__(self, *, me: ClientUser, state: ConnectionState, data: Dict[str, Any]):
        self._state: ConnectionState = state
        self.id: int = int(data['id'])
        self.me: ClientUser = me
        self._update(data)

    def _update(self, data: Dict[str, Any]) -> None:
        self.owner_id: Optional[int] = utils._snowflake(data.get('ownerId'))
        self._icon: Optional[str] = data.get('iconKey') or None
        self.name: Optional[str] = data.get('name') or None
        self.recipients: List[User] = [
            self._state.store_user(p) for p in (data.get('participants') or []) if int(p['id']) != self.me.id
        ]
        self.last_message_id: Optional[int] = utils._snowflake(data.get('lastMessageId'))

    async def _get_channel(self) -> Self:
        return self

    def __str__(self) -> str:
        if self.name:
            return self.name
        if len(self.recipients) == 0:
            return 'Unnamed'
        return ', '.join(map(lambda x: x.name, self.recipients))

    def __repr__(self) -> str:
        return f'<GroupChannel id={self.id} name={self.name!r}>'

    @property
    def type(self) -> ChannelType:
        """:class:`ChannelType`: The channel's Bisim type."""
        return ChannelType.group

    @property
    def guild(self) -> None:
        """Always ``None``: a group DM is not in a server."""
        return None

    @property
    def owner(self) -> Optional[BaseUser]:
        """Optional[:class:`User`]: The owner that owns the group channel."""
        if self.owner_id == self.me.id:
            return self.me
        return utils.get(self.recipients, id=self.owner_id)

    @property
    def icon(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the channel's icon asset if available."""
        if self._icon is None:
            return None
        return Asset._from_key(self._state, self._icon)

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the channel's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def jump_url(self) -> str:
        """:class:`str`: Returns a URL that allows the client to jump to the channel."""
        return f'{utils.WEB_URL}/channels/@me/{self.id}'

    def permissions_for(self, obj: Any, /) -> Permissions:
        """Handles permission resolution for a :class:`User`.

        This function is there for compatibility with other channel types.

        Actual direct messages do not really have the concept of permissions.

        Parameters
        -----------
        obj: :class:`~bisim.abc.Snowflake`
            The user to check permissions for.

        Returns
        --------
        :class:`Permissions`
            The resolved permissions for the user.
        """
        base = Permissions._dm_permissions()
        base.mention_everyone = True
        if obj.id == self.owner_id:
            base.kick_members = True
        return base

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID."""
        from .message import PartialMessage

        return PartialMessage(channel=self, id=message_id)

    async def leave(self) -> None:
        """|coro|

        Not supported on Bisim: a bot cannot leave a group DM.
        """
        raise NotSupported('Leaving a group DM as a bot')


class PartialMessageable(abc.Messageable, Hashable):
    """Represents a partial messageable to aid with working messageable channels when
    only a channel ID is present.

    The only way to construct this class is through :meth:`Client.get_partial_messageable`.

    Note that this class is trimmed down and has no rich attributes.

    .. container:: operations

        .. describe:: x == y

            Checks if two partial messageables are equal.

        .. describe:: x != y

            Checks if two partial messageables are not equal.

        .. describe:: hash(x)

            Returns the partial messageable's hash.

    Attributes
    -----------
    id: :class:`int`
        The channel ID associated with this partial messageable.
    guild_id: Optional[:class:`int`]
        The guild ID associated with this partial messageable.
    type: Optional[:class:`ChannelType`]
        The channel type associated with this partial messageable, if given.
    """

    def __init__(self, state: ConnectionState, id: int, guild_id: Optional[int] = None, type: Optional[ChannelType] = None):
        self._state: ConnectionState = state
        self.id: int = id
        self.guild_id: Optional[int] = guild_id
        self.type: Optional[ChannelType] = type
        self.last_message_id: Optional[int] = None

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} id={self.id} type={self.type!r}>'

    async def _get_channel(self) -> PartialMessageable:
        return self

    @property
    def guild(self) -> Optional[Guild]:
        """Optional[:class:`Guild`]: The guild this partial messageable is in."""
        return self._state._get_guild(self.guild_id)

    @property
    def jump_url(self) -> str:
        """:class:`str`: Returns a URL that allows the client to jump to the channel."""
        if self.guild_id is None:
            return f'{utils.WEB_URL}/channels/@me/{self.id}'
        return f'{utils.WEB_URL}/channels/{self.guild_id}/{self.id}'

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the channel's creation time in UTC."""
        return utils.snowflake_time(self.id)

    def permissions_for(self, obj: Any = None, /) -> Permissions:
        """Handles permission resolution for a :class:`User`.

        This function is there for compatibility with other channel types.

        Since partial messageables cannot reasonably have the concept of
        permissions, this will always return :meth:`Permissions.none`.

        Returns
        --------
        :class:`Permissions`
            The resolved permissions.
        """
        return Permissions.none()

    @property
    def mention(self) -> str:
        """:class:`str`: Returns a string that allows you to mention the channel."""
        return f'<#{self.id}>'

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID."""
        from .message import PartialMessage

        return PartialMessage(channel=self, id=message_id)


def _guild_channel_factory(channel_type: Any) -> Tuple[Optional[type], ChannelType]:
    value = ChannelType.from_bisim(channel_type)
    if value is ChannelType.text:
        return TextChannel, value
    if value is ChannelType.voice:
        return VoiceChannel, value
    if value is ChannelType.category:
        return CategoryChannel, value
    return None, value


def _private_channel_factory(channel_type: Any) -> Tuple[Optional[type], ChannelType]:
    value = ChannelType.from_bisim(channel_type)
    if value is ChannelType.private:
        return DMChannel, value
    if value is ChannelType.group:
        return GroupChannel, value
    return None, value


def _channel_factory(channel_type: Any) -> Tuple[Optional[type], ChannelType]:
    cls, value = _guild_channel_factory(channel_type)
    if cls is None:
        return _private_channel_factory(channel_type)
    return cls, value

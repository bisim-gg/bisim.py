from __future__ import annotations

import asyncio
import base64
import datetime
import io
import re
from os import PathLike
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple, Union, overload

from . import utils
from .components import ActionRow, Component, _component_factory
from .embeds import Embed
from .emoji import Emoji
from .enums import ChannelType, InteractionType, MessageReferenceType, MessageType, try_enum
from .errors import ClientException, HTTPException, InvalidData, NotFound, NotSupported
from .file import File
from .flags import AttachmentFlags, MessageFlags
from .mixins import Hashable
from .partial_emoji import PartialEmoji, _EmojiTag
from .reaction import Reaction
from .sticker import StickerItem

if TYPE_CHECKING:
    from typing_extensions import Self

    from .abc import GuildChannel, MessageableChannel, Snowflake
    from .channel import TextChannel
    from .guild import Guild
    from .member import Member
    from .mentions import AllowedMentions
    from .poll import Poll
    from .role import Role
    from .state import ConnectionState
    from .ui.view import View
    from .user import User

    EmojiInputType = Union[Emoji, PartialEmoji, str, Reaction]

__all__ = (
    'Attachment',
    'Message',
    'PartialMessage',
    'MessageInteraction',
    'MessageInteractionMetadata',
    'MessageReference',
    'DeletedReferencedMessage',
    'MessageApplication',
    'RoleSubscriptionInfo',
    'MessageSnapshot',
)

_USER_MENTION_RE = re.compile(r'<@!?([0-9]{1,20})>')
_ROLE_MENTION_RE = re.compile(r'<@&([0-9]{1,20})>')
_CHANNEL_MENTION_RE = re.compile(r'<#([0-9]{1,20})>')
_STICKER_RE = re.compile(r'<sticker:([0-9]{1,20})>')
_EVERYONE_RE = re.compile(r'(?<![\w`])@(everyone|here)\b')


def convert_emoji_reaction(emoji: Union[EmojiInputType, Reaction]) -> str:
    """The emoji as Bisim's reaction routes take it: unicode, or ``<:name:id>``."""
    if isinstance(emoji, Reaction):
        emoji = emoji.emoji

    if isinstance(emoji, Emoji):
        return f'<:{emoji.name}:{emoji.id}>'
    if isinstance(emoji, PartialEmoji):
        return emoji._as_reaction()
    if isinstance(emoji, str):
        emoji = emoji.strip('<>')
        if emoji.startswith('a:'):
            emoji = emoji[1:]
        if ':' in emoji:
            name, _, emoji_id = emoji.lstrip(':').partition(':')
            return f'<:{name}:{emoji_id}>'
        return emoji

    raise TypeError(f'emoji argument must be str, Emoji, or Reaction not {emoji.__class__.__name__}.')


class Attachment(Hashable):
    """Represents an attachment from Bisim.

    .. container:: operations

        .. describe:: str(x)

            Returns the URL of the attachment.

        .. describe:: x == y

            Checks if the attachment is equal to another attachment.

        .. describe:: x != y

            Checks if the attachment is not equal to another attachment.

        .. describe:: hash(x)

            Returns the hash of the attachment.

    Attributes
    ------------
    id: :class:`int`
        The attachment ID.
    size: :class:`int`
        The attachment size in bytes.
    height: Optional[:class:`int`]
        The attachment's height, in pixels. Only applicable to images and videos.
    width: Optional[:class:`int`]
        The attachment's width, in pixels. Only applicable to images and videos.
    filename: :class:`str`
        The attachment's filename.
    url: :class:`str`
        The attachment URL.
    proxy_url: :class:`str`
        The same as :attr:`url` on Bisim.
    content_type: Optional[:class:`str`]
        The attachment's `media type <https://en.wikipedia.org/wiki/Media_type>`_
    description: Optional[:class:`str`]
        The attachment's description. Only applicable to images.
    ephemeral: :class:`bool`
        Whether the attachment is ephemeral.
    duration: Optional[:class:`float`]
        The duration of the audio file in seconds. Returns ``None`` if it's not a voice message.
    waveform: Optional[:class:`bytes`]
        The waveform (amplitudes) of the audio in bytes. Returns ``None`` if it's not a voice message.
    title: Optional[:class:`str`]
        The normalised version of the attachment's filename.
    kind: :class:`str`
        Bisim's own kind for the file: ``IMAGE``, ``VIDEO``, ``AUDIO`` or ``FILE``.
    blocked: :class:`bool`
        Whether Bisim's content scanner took the file down (its URL is then empty).
    """

    __slots__ = (
        'id',
        'size',
        'height',
        'width',
        'filename',
        'url',
        'proxy_url',
        '_http',
        'content_type',
        'description',
        'ephemeral',
        'duration',
        'waveform',
        '_flags',
        'title',
        'kind',
        'blocked',
        '_spoiler',
        '_gif',
    )

    def __init__(self, *, data: Dict[str, Any], state: ConnectionState):
        self.id: int = int(data['id'])
        self.size: int = utils._int(data.get('sizeBytes'), 0)
        self.height: Optional[int] = data.get('height') or None
        self.width: Optional[int] = data.get('width') or None
        self.filename: str = data.get('fileName') or data.get('filename') or 'file'
        self.url: str = data.get('url') or ''
        self.proxy_url: str = self.url
        self._http = state.http
        self.content_type: Optional[str] = data.get('contentType') or None
        self.description: Optional[str] = data.get('description') or None
        self.ephemeral: bool = False
        self.duration: Optional[float] = data.get('durationSecs') or None
        waveform = data.get('waveform')
        self.waveform: Optional[bytes] = base64.b64decode(waveform) if waveform else None
        self._spoiler: bool = bool(data.get('spoiler', False))
        self._gif: bool = bool(data.get('gif', False))
        self._flags: int = 8 if self._spoiler else 0
        self.title: Optional[str] = self.filename
        self.kind: str = data.get('kind') or 'FILE'
        self.blocked: bool = bool(data.get('blocked', False))

    @property
    def flags(self) -> AttachmentFlags:
        """:class:`AttachmentFlags`: The attachment's flags."""
        return AttachmentFlags._from_value(self._flags)

    def is_spoiler(self) -> bool:
        """:class:`bool`: Whether this attachment contains a spoiler."""
        return self._spoiler or self.filename.startswith('SPOILER_')

    def is_voice_message(self) -> bool:
        """:class:`bool`: Whether this attachment is a voice message."""
        return self.duration is not None and self.waveform is not None

    def __repr__(self) -> str:
        return f'<Attachment id={self.id} filename={self.filename!r} url={self.url!r}>'

    def __str__(self) -> str:
        return self.url or ''

    async def save(
        self,
        fp: Union[io.BufferedIOBase, PathLike[Any], str],
        *,
        seek_begin: bool = True,
        use_cached: bool = False,
    ) -> int:
        """|coro|

        Saves this attachment into a file-like object.

        Parameters
        -----------
        fp: Union[:class:`io.BufferedIOBase`, :class:`os.PathLike`]
            The file-like object to save this attachment to or the filename
            to use. If a filename is passed then a file is created with that
            filename and used instead.
        seek_begin: :class:`bool`
            Whether to seek to the beginning of the file after saving is
            successfully done.
        use_cached: :class:`bool`
            Accepted for compatibility; Bisim serves attachments from one address.

        Raises
        --------
        HTTPException
            Saving the attachment failed.
        NotFound
            The attachment was deleted.

        Returns
        --------
        :class:`int`
            The number of bytes written.
        """
        data = await self.read(use_cached=use_cached)
        if isinstance(fp, io.BufferedIOBase) or hasattr(fp, 'write'):
            written = fp.write(data)  # type: ignore
            if seek_begin and hasattr(fp, 'seek'):
                fp.seek(0)  # type: ignore
            return written  # type: ignore
        with open(fp, 'wb') as f:  # type: ignore
            return f.write(data)

    async def read(self, *, use_cached: bool = False) -> bytes:
        """|coro|

        Retrieves the content of this attachment as a :class:`bytes` object.

        Parameters
        -----------
        use_cached: :class:`bool`
            Accepted for compatibility; Bisim serves attachments from one address.

        Raises
        ------
        HTTPException
            Downloading the attachment failed.
        Forbidden
            You do not have permissions to access this attachment
        NotFound
            The attachment was deleted.

        Returns
        -------
        :class:`bytes`
            The contents of the attachment.
        """
        if not self.url:
            raise NotFound(_FakeResponse(404), 'This attachment has no address (it may have been taken down).')  # type: ignore
        return await self._http.get_from_cdn(self.url)

    async def to_file(
        self,
        *,
        filename: Optional[str] = utils.MISSING,
        description: Optional[str] = utils.MISSING,
        use_cached: bool = False,
        spoiler: bool = utils.MISSING,
    ) -> File:
        """|coro|

        Converts the attachment into a :class:`File` suitable for sending via
        :meth:`abc.Messageable.send`.

        Parameters
        -----------
        filename: Optional[:class:`str`]
            The filename to use for the file. If not specified then the filename
            of the attachment is used instead.
        description: Optional[:class:`str`]
            The description to use for the file. If not specified then the
            description of the attachment is used instead.
        use_cached: :class:`bool`
            Accepted for compatibility.
        spoiler: :class:`bool`
            Whether the file is a spoiler. If not specified, the :attr:`spoiler`
            attribute of the attachment is used instead.

        Raises
        ------
        HTTPException
            Downloading the attachment failed.
        Forbidden
            You do not have permissions to access this attachment
        NotFound
            The attachment was deleted.

        Returns
        -------
        :class:`File`
            The attachment as a file suitable for sending.
        """
        data = await self.read(use_cached=use_cached)
        file_filename = filename if filename is not utils.MISSING else self.filename
        file_description = description if description is not utils.MISSING else self.description
        file_spoiler = spoiler if spoiler is not utils.MISSING else self.is_spoiler()
        return File(io.BytesIO(data), filename=file_filename, description=file_description, spoiler=file_spoiler)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'id': str(self.id),
            'fileName': self.filename,
            'sizeBytes': self.size,
            'url': self.url,
            'spoiler': self.is_spoiler(),
        }
        if self.width:
            result['width'] = self.width
        if self.height:
            result['height'] = self.height
        if self.content_type:
            result['contentType'] = self.content_type
        if self.description is not None:
            result['description'] = self.description
        return result


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status
        self.reason = 'Not Found'
        self.headers: Dict[str, str] = {}


class DeletedReferencedMessage:
    """A special sentinel type given when the resolved message reference
    points to a deleted message.

    The purpose of this class is to separate referenced messages that could not be
    fetched and those that were previously fetched but have since been deleted.
    """

    __slots__ = ('_parent',)

    def __init__(self, parent: MessageReference):
        self._parent: MessageReference = parent

    def __repr__(self) -> str:
        return f'<DeletedReferencedMessage id={self.id} channel_id={self.channel_id} guild_id={self.guild_id!r}>'

    @property
    def id(self) -> int:
        """:class:`int`: The message ID of the deleted referenced message."""
        return self._parent.message_id  # type: ignore

    @property
    def channel_id(self) -> int:
        """:class:`int`: The channel ID of the deleted referenced message."""
        return self._parent.channel_id

    @property
    def guild_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The guild ID of the deleted referenced message."""
        return self._parent.guild_id


class MessageReference:
    """Represents a reference to a :class:`~bisim.Message`.

    This class can be created by users.

    Attributes
    -----------
    type: :class:`MessageReferenceType`
        The type of message reference (always a reply on Bisim).
    message_id: Optional[:class:`int`]
        The id of the message referenced.
    channel_id: :class:`int`
        The channel id of the message referenced.
    guild_id: Optional[:class:`int`]
        The guild id of the message referenced.
    fail_if_not_exists: :class:`bool`
        Whether replying to the referenced message should raise :class:`HTTPException`
        if the message no longer exists or Bisim could not fetch the message.
    resolved: Optional[Union[:class:`Message`, :class:`DeletedReferencedMessage`]]
        The message that this reference resolved to. If this is ``None``
        then the original message was not fetched either due to the Bisim API
        not attempting to resolve it or it not being available at the time of creation.
        If the message was resolved at a prior point but has since been deleted then
        this will be of type :class:`DeletedReferencedMessage`.
    """

    __slots__ = ('type', 'message_id', 'channel_id', 'guild_id', 'fail_if_not_exists', 'resolved', '_state')

    def __init__(
        self,
        *,
        message_id: int,
        channel_id: int,
        guild_id: Optional[int] = None,
        fail_if_not_exists: bool = True,
        type: MessageReferenceType = MessageReferenceType.reply,
    ):
        self._state: Optional[ConnectionState] = None
        self.type: MessageReferenceType = type
        self.resolved: Optional[Union[Message, DeletedReferencedMessage]] = None
        self.message_id: Optional[int] = message_id
        self.channel_id: int = channel_id
        self.guild_id: Optional[int] = guild_id
        self.fail_if_not_exists: bool = fail_if_not_exists

    @classmethod
    def with_state(cls, state: ConnectionState, data: Dict[str, Any]) -> Self:
        self = cls.__new__(cls)
        self.type = MessageReferenceType.reply
        self.message_id = utils._snowflake(data.get('message_id'))
        self.channel_id = int(data['channel_id'])
        self.guild_id = utils._snowflake(data.get('guild_id'))
        self.fail_if_not_exists = bool(data.get('fail_if_not_exists', True))
        self._state = state
        self.resolved = None
        return self

    @classmethod
    def from_message(
        cls, message: PartialMessage, *, fail_if_not_exists: bool = True, type: MessageReferenceType = MessageReferenceType.reply
    ) -> Self:
        """Creates a :class:`MessageReference` from an existing :class:`~bisim.Message`.

        Parameters
        ----------
        message: :class:`~bisim.Message`
            The message to be converted into a reference.
        fail_if_not_exists: :class:`bool`
            Whether replying to the referenced message should raise :class:`HTTPException`
            if the message no longer exists or Bisim could not fetch the message.
        type: :class:`~bisim.MessageReferenceType`
            The type of message reference. Only replies exist on Bisim.

        Returns
        -------
        :class:`MessageReference`
            A reference to the message.
        """
        if type is MessageReferenceType.forward:
            raise NotSupported('Forwarding messages')
        self = cls(
            message_id=message.id,
            channel_id=message.channel.id,
            guild_id=getattr(message.guild, 'id', None),
            fail_if_not_exists=fail_if_not_exists,
            type=type,
        )
        self._state = message._state
        return self

    @property
    def cached_message(self) -> Optional[Message]:
        """Optional[:class:`~bisim.Message`]: The cached message, if found in the internal message cache."""
        return self._state and self._state._get_message(self.message_id)

    @property
    def jump_url(self) -> str:
        """:class:`str`: Returns a URL that allows the client to jump to the referenced message."""
        guild_id = self.guild_id if self.guild_id is not None else '@me'
        return f'{utils.WEB_URL}/channels/{guild_id}/{self.channel_id}/{self.message_id}'

    def __repr__(self) -> str:
        return f'<MessageReference message_id={self.message_id!r} channel_id={self.channel_id!r} guild_id={self.guild_id!r}>'

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {'type': self.type.value, 'channel_id': str(self.channel_id)}
        if self.message_id is not None:
            result['message_id'] = str(self.message_id)
        if self.guild_id is not None:
            result['guild_id'] = str(self.guild_id)
        if self.fail_if_not_exists is not None:
            result['fail_if_not_exists'] = self.fail_if_not_exists
        return result

    to_message_reference_dict = to_dict


class MessageInteraction(Hashable):
    """Represents the interaction that a :class:`Message` is a response to.

    Bisim records the command's name and who ran it.

    .. container:: operations

        .. describe:: x == y

            Checks if two message interactions are equal.

        .. describe:: x != y

            Checks if two message interactions are not equal.

        .. describe:: hash(x)

            Returns the message interaction's hash.

    Attributes
    -----------
    id: :class:`int`
        The interaction ID, or the message ID when Bisim did not record it.
    type: :class:`InteractionType`
        The interaction type.
    name: :class:`str`
        The name of the interaction.
    user: Union[:class:`User`, :class:`Member`]
        The user or member that invoked the interaction.
    """

    __slots__: Tuple[str, ...] = ('id', 'type', 'name', 'user')

    def __init__(self, *, state: ConnectionState, guild: Optional[Guild], data: Dict[str, Any], fallback_id: int) -> None:
        self.id: int = utils._snowflake(data.get('id')) or fallback_id
        self.type: InteractionType = InteractionType.application_command
        self.name: str = data.get('name') or ''
        user_id = utils._snowflake(data.get('userId'))
        user: Any = None
        if user_id is not None:
            if guild is not None:
                user = guild.get_member(user_id)
            if user is None:
                user = state.get_user(user_id)
            if user is None:
                user = state.create_user({'id': user_id, 'username': data.get('username') or ''})
        self.user: Union[User, Member] = user

    def __repr__(self) -> str:
        return f'<MessageInteraction id={self.id} name={self.name!r} type={self.type!r} user={self.user!r}>'

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: The interaction's creation time in UTC."""
        return utils.snowflake_time(self.id)


class MessageInteractionMetadata(MessageInteraction):
    """Represents the interaction metadata of a :class:`Message`.

    On Bisim it carries the same information as :class:`MessageInteraction`.
    """

    __slots__ = ()


class MessageApplication:
    """Not on Bisim; kept so the name imports."""


class RoleSubscriptionInfo:
    """Not on Bisim; kept so the name imports."""


class MessageSnapshot:
    """Not on Bisim (no forwarding); kept so the name imports."""


def flatten_handlers(cls: Any) -> Any:
    return cls


class PartialMessage(Hashable):
    """Represents a partial message to aid with working messages when only
    a message and channel ID are present.

    There are two ways to construct this class. The first one is through
    the constructor itself, and the second is via the following:

    - :meth:`TextChannel.get_partial_message`
    - :meth:`DMChannel.get_partial_message`
    - :meth:`PartialMessageable.get_partial_message`

    Note that this class is trimmed down and has no rich attributes.

    .. container:: operations

        .. describe:: x == y

            Checks if two partial messages are equal.

        .. describe:: x != y

            Checks if two partial messages are not equal.

        .. describe:: hash(x)

            Returns the partial message's hash.

    Attributes
    -----------
    channel: Union[:class:`TextChannel`, :class:`DMChannel`, :class:`PartialMessageable`]
        The channel associated with this partial message.
    id: :class:`int`
        The message ID.
    guild: Optional[:class:`Guild`]
        The guild that the partial message belongs to, if applicable.
    """

    __slots__ = ('channel', 'id', '_cs_guild', '_state', 'guild')

    def __init__(self, *, channel: MessageableChannel, id: int) -> None:
        if not isinstance(channel, _MESSAGEABLE_TYPES()):
            raise TypeError(f'expected PartialMessageable, TextChannel, DMChannel or GroupChannel not {type(channel)!r}')

        self.channel: MessageableChannel = channel
        self._state: ConnectionState = channel._state
        self.id: int = id
        self.guild: Optional[Guild] = getattr(channel, 'guild', None)

    def _update(self, data: Dict[str, Any]) -> None:
        pass

    pinned: Any = property(None, lambda x, y: None)

    def __repr__(self) -> str:
        return f'<PartialMessage id={self.id} channel={self.channel!r}>'

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: The partial message's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def jump_url(self) -> str:
        """:class:`str`: Returns a URL that allows the client to jump to this message."""
        guild_id = getattr(self.guild, 'id', '@me')
        return f'{utils.WEB_URL}/channels/{guild_id}/{self.channel.id}/{self.id}'

    @property
    def thread(self) -> None:
        """Always ``None``: Bisim has no threads."""
        return None

    async def fetch(self) -> Message:
        """|coro|

        Fetches the partial message to a full :class:`Message`.

        Raises
        --------
        NotFound
            The message was not found.
        Forbidden
            You do not have the permissions required to get a message.
        HTTPException
            Retrieving the message failed.

        Returns
        --------
        :class:`Message`
            The full message.
        """
        data = await self._state.http.get_message(self.channel.id, self.id)
        return self._state.create_message(channel=self.channel, data=data)

    async def delete(self, *, delay: Optional[float] = None) -> None:
        """|coro|

        Deletes the message.

        Your own messages could be deleted without any proper permissions. However to
        delete other people's messages, you must have :attr:`~Permissions.manage_messages`.

        Parameters
        -----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message. If the deletion fails then it is silently ignored.

        Raises
        ------
        Forbidden
            You do not have proper permissions to delete the message.
        NotFound
            The message was deleted already
        HTTPException
            Deleting the message failed.
        """
        if delay is not None:

            async def delete(delay: float) -> None:
                await asyncio.sleep(delay)
                try:
                    await self._state.http.delete_message(self.channel.id, self.id)
                except HTTPException:
                    pass

            asyncio.create_task(delete(delay))
        else:
            await self._state.http.delete_message(self.channel.id, self.id)

    async def edit(
        self,
        *,
        content: Optional[str] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        attachments: Sequence[Union[Any, File]] = utils.MISSING,
        delete_after: Optional[float] = None,
        allowed_mentions: Optional[AllowedMentions] = utils.MISSING,
        view: Optional[View] = utils.MISSING,
        suppress: bool = utils.MISSING,
    ) -> Message:
        """|coro|

        Edits the message.

        The content must be able to be transformed into a string via ``str(content)``.

        Parameters
        -----------
        content: Optional[:class:`str`]
            The new content to replace the message with.
            Could be ``None`` to remove the content.
        embed: Optional[:class:`Embed`]
            The new embed to replace the original with.
            Could be ``None`` to remove the embed.
        embeds: List[:class:`Embed`]
            The new embeds to replace the original with. Must be a maximum of 10.
            To remove all embeds ``[]`` should be passed.
        attachments: List[Union[:class:`Attachment`, :class:`File`]]
            Not supported on Bisim: a message's files cannot be changed.
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.
        allowed_mentions: Optional[:class:`~bisim.AllowedMentions`]
            Accepted for compatibility.
        view: Optional[:class:`~bisim.ui.View`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.
        suppress: :class:`bool`
            Whether to suppress embeds for the message.

        Raises
        -------
        HTTPException
            Editing the message failed.
        Forbidden
            Tried to suppress a message without permissions or
            edited a message's content or embed that isn't yours.
        TypeError
            You specified both ``embed`` and ``embeds``
        NotSupported
            Attachments were given.

        Returns
        --------
        :class:`Message`
            The newly edited message.
        """
        if attachments is not utils.MISSING:
            raise NotSupported("Changing a message's attachments")
        if embed is not utils.MISSING and embeds is not utils.MISSING:
            raise TypeError('Cannot mix embed and embeds keyword arguments.')

        from .abc import _message_payload

        payload = await _message_payload(
            self._state,
            self.channel.id,
            content=content,
            embed=embed,
            embeds=embeds,
            view=view,
            suppress_embeds=bool(suppress) if suppress is not utils.MISSING else False,
            editing=True,
        )
        data = await self._state.http.edit_message(self.channel.id, self.id, payload)
        message = Message(state=self._state, channel=self.channel, data=data)

        if view and not view.is_finished() and view.is_dispatchable():
            self._state.store_view(view, self.id)

        if delete_after is not None:
            await self.delete(delay=delete_after)

        return message

    async def publish(self) -> None:
        """|coro|

        Not supported on Bisim (no announcement channels).
        """
        raise NotSupported('Publishing messages')

    async def pin(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Pins the message.

        You must have :attr:`~Permissions.pin_messages` to do
        this in a non-private channel context.

        Parameters
        -----------
        reason: Optional[:class:`str`]
            The reason for pinning the message. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to pin the message.
        NotFound
            The message or channel was not found or deleted.
        HTTPException
            Pinning the message failed, probably due to the channel
            having more than 50 pinned messages.
        """
        await self._state.http.pin_message(self.channel.id, self.id, reason=reason)
        self.pinned = True

    async def unpin(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Unpins the message.

        You must have :attr:`~Permissions.pin_messages` to do
        this in a non-private channel context.

        Parameters
        -----------
        reason: Optional[:class:`str`]
            The reason for unpinning the message. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to unpin the message.
        NotFound
            The message or channel was not found or deleted.
        HTTPException
            Unpinning the message failed.
        """
        await self._state.http.unpin_message(self.channel.id, self.id, reason=reason)
        self.pinned = False

    async def add_reaction(self, emoji: EmojiInputType, /) -> None:
        """|coro|

        Adds a reaction to the message.

        The emoji may be a unicode emoji or a custom server :class:`Emoji`.

        You must have :attr:`~Permissions.read_message_history`
        to do this. If nobody else has reacted to the message using this
        emoji, :attr:`~Permissions.add_reactions` is required.

        Parameters
        ------------
        emoji: Union[:class:`Emoji`, :class:`Reaction`, :class:`PartialEmoji`, :class:`str`]
            The emoji to react with.

        Raises
        --------
        HTTPException
            Adding the reaction failed.
        Forbidden
            You do not have the proper permissions to react to the message.
        NotFound
            The emoji you specified was not found.
        TypeError
            The emoji parameter is invalid.
        """
        emoji = convert_emoji_reaction(emoji)
        await self._state.http.add_reaction(self.channel.id, self.id, emoji)

    async def remove_reaction(self, emoji: Union[EmojiInputType, Reaction], member: Snowflake) -> None:
        """|coro|

        Remove a reaction by the member from the message.

        The emoji may be a unicode emoji or a custom server :class:`Emoji`.

        If the reaction is not your own (i.e. ``member`` parameter is not you) then
        :attr:`~Permissions.manage_messages` is needed.

        The ``member`` parameter must represent a member and meet
        the :class:`abc.Snowflake` abc.

        Parameters
        ------------
        emoji: Union[:class:`Emoji`, :class:`Reaction`, :class:`PartialEmoji`, :class:`str`]
            The emoji to remove.
        member: :class:`abc.Snowflake`
            The member for which to remove the reaction.

        Raises
        --------
        HTTPException
            Removing the reaction failed.
        Forbidden
            You do not have the proper permissions to remove the reaction.
        NotFound
            The member or emoji you specified was not found.
        TypeError
            The emoji parameter is invalid.
        """
        emoji = convert_emoji_reaction(emoji)

        if member.id == self._state.self_id:
            await self._state.http.remove_own_reaction(self.channel.id, self.id, emoji)
        else:
            await self._state.http.remove_reaction(self.channel.id, self.id, emoji, member.id)

    async def clear_reaction(self, emoji: Union[EmojiInputType, Reaction]) -> None:
        """|coro|

        Clears a specific reaction from the message.

        The emoji may be a unicode emoji or a custom server :class:`Emoji`.

        You must have :attr:`~Permissions.manage_messages` to do this.

        Bisim removes reactions one person at a time, so this removes each
        person's reaction in turn.

        Parameters
        -----------
        emoji: Union[:class:`Emoji`, :class:`Reaction`, :class:`PartialEmoji`, :class:`str`]
            The emoji to clear.

        Raises
        --------
        HTTPException
            Clearing the reaction failed.
        Forbidden
            You do not have the proper permissions to clear the reaction.
        NotFound
            The emoji you specified was not found.
        TypeError
            The emoji parameter is invalid.
        """
        emoji = convert_emoji_reaction(emoji)
        http = self._state.http
        after: Optional[str] = None
        while True:
            data = await http.get_reaction_users(self.channel.id, self.id, emoji, 100, after=after)
            if not data:
                return
            for user in data:
                user_id = int(user['id'])
                if user_id == self._state.self_id:
                    await http.remove_own_reaction(self.channel.id, self.id, emoji)
                else:
                    await http.remove_reaction(self.channel.id, self.id, emoji, user_id)
            if len(data) < 100:
                return
            after = str(data[-1]['id'])

    async def clear_reactions(self) -> None:
        """|coro|

        Removes all the reactions from the message.

        You must have :attr:`~Permissions.manage_messages` to do this.

        Raises
        --------
        HTTPException
            Removing the reactions failed.
        Forbidden
            You do not have the proper permissions to remove all the reactions.
        """
        await self._state.http.clear_reactions(self.channel.id, self.id)

    async def create_thread(self, **kwargs: Any) -> Any:
        """|coro|

        Not supported on Bisim (no threads).
        """
        raise NotSupported('Threads')

    async def fetch_thread(self) -> Any:
        """|coro|

        Not supported on Bisim (no threads).
        """
        raise NotSupported('Threads')

    async def forward(self, destination: Any, *, fail_if_not_exists: bool = True) -> Message:
        """|coro|

        Not supported on Bisim (no forwarding).
        """
        raise NotSupported('Forwarding messages')

    async def reply(self, content: Optional[str] = None, **kwargs: Any) -> Message:
        """|coro|

        A shortcut method to :meth:`.abc.Messageable.send` to reply to the
        :class:`.Message`.

        Raises
        --------
        ~bisim.HTTPException
            Sending the message failed.
        ~bisim.Forbidden
            You do not have the proper permissions to send the message.
        ValueError
            The ``files`` list is not of the appropriate size
        TypeError
            You specified both ``file`` and ``files``.

        Returns
        ---------
        :class:`.Message`
            The message that was sent.
        """
        return await self.channel.send(content, reference=self, **kwargs)

    async def end_poll(self) -> Message:
        """|coro|

        Ends the poll attached to this message.

        This can only be done if you are the message author.

        Raises
        -------
        HTTPException
            Ending the poll failed.

        Returns
        -------
        :class:`.Message`
            The updated message.
        """
        data = await self._state.http.end_poll(self.channel.id, self.id)
        return Message(state=self._state, channel=self.channel, data=data)

    def to_reference(
        self, *, fail_if_not_exists: bool = True, type: MessageReferenceType = MessageReferenceType.reply
    ) -> MessageReference:
        """Creates a :class:`~bisim.MessageReference` from the current message.

        Parameters
        ----------
        fail_if_not_exists: :class:`bool`
            Whether replying using the message reference should raise :class:`HTTPException`
            if the message no longer exists or Bisim could not fetch the message.
        type: :class:`MessageReferenceType`
            The type of message reference.

        Returns
        ---------
        :class:`~bisim.MessageReference`
            The reference to this message.
        """
        return MessageReference.from_message(self, fail_if_not_exists=fail_if_not_exists, type=type)

    def to_message_reference_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {'message_id': str(self.id), 'channel_id': str(self.channel.id)}
        if self.guild is not None:
            data['guild_id'] = str(self.guild.id)
        return data


def _MESSAGEABLE_TYPES() -> Tuple[type, ...]:
    from .channel import DMChannel, GroupChannel, PartialMessageable, TextChannel, VoiceChannel

    return (TextChannel, VoiceChannel, DMChannel, GroupChannel, PartialMessageable)


class Message(PartialMessage, Hashable):
    r"""Represents a message from Bisim.

    .. container:: operations

        .. describe:: x == y

            Checks if two messages are equal.

        .. describe:: x != y

            Checks if two messages are not equal.

        .. describe:: hash(x)

            Returns the message's hash.

    Attributes
    -----------
    tts: :class:`bool`
        Always ``False``: Bisim has no text to speech.
    type: :class:`MessageType`
        The type of message. In most cases this should not be checked, but it is helpful
        in cases where it might be a system message for :attr:`system_content`.
    author: Union[:class:`Member`, :class:`abc.User`]
        A :class:`Member` that sent the message. If :attr:`channel` is a
        private channel or the user has the left the guild, then it is a :class:`User` instead.
    content: :class:`str`
        The actual contents of the message. Mentions are tokens inside it:
        ``<@id>``, ``<@&id>``, ``@everyone``, custom emoji ``<:name:id>`` and
        stickers ``<sticker:id>``.
    nonce: Optional[Union[:class:`str`, :class:`int`]]
        The value used by Bisim clients to verify that the message is successfully sent.
    embeds: List[:class:`Embed`]
        A list of embeds the message has.
    channel: Union[:class:`TextChannel`, :class:`DMChannel`, :class:`GroupChannel`, :class:`PartialMessageable`]
        The :class:`TextChannel` that the message was sent from.
        Could be a :class:`DMChannel` or :class:`GroupChannel` if it's a private message.
    reference: Optional[:class:`~bisim.MessageReference`]
        The message that this message references (a reply).
    mention_everyone: :class:`bool`
        Specifies if the message mentions everyone.
    mentions: List[:class:`abc.User`]
        A list of :class:`Member` that were mentioned. If the message is in a private message
        then the list will be of :class:`User` instead. Mentioned users the
        library does not know are left out (their ids are in :attr:`raw_mentions`).
    role_mentions: List[:class:`Role`]
        A list of :class:`Role` that were mentioned. If the message is in a private message
        then the list is always empty.
    id: :class:`int`
        The message ID.
    webhook_id: Optional[:class:`int`]
        If this message was sent by a webhook, then this is the webhook ID's that sent this
        message.
    attachments: List[:class:`Attachment`]
        A list of attachments given to a message.
    pinned: :class:`bool`
        Specifies if the message is currently pinned.
    flags: :class:`MessageFlags`
        Extra features of the message.
    reactions : List[:class:`Reaction`]
        Reactions to a message. Reactions can be either custom emoji or standard unicode emoji.
    activity: Optional[:class:`dict`]
        Always ``None``.
    application_id: Optional[:class:`int`]
        The application that sent this message, when it answers an interaction.
    stickers: List[:class:`StickerItem`]
        A list of sticker items given to the message.
    components: List[:class:`ActionRow`]
        A list of components in the message.
    interaction_metadata: Optional[:class:`.MessageInteractionMetadata`]
        The metadata of the interaction that this message is a response to.
    guild: Optional[:class:`Guild`]
        The guild that the message belongs to, if applicable.
    poll: Optional[:class:`Poll`]
        The poll attached to this message.
    """

    __slots__ = (
        '_edited_timestamp',
        '_cs_channel_mentions',
        '_cs_raw_mentions',
        '_cs_clean_content',
        '_cs_raw_channel_mentions',
        '_cs_raw_role_mentions',
        '_cs_system_content',
        '_thread',
        'tts',
        'content',
        'webhook_id',
        'mention_everyone',
        'embeds',
        'mentions',
        'author',
        'attachments',
        'nonce',
        'pinned',
        'role_mentions',
        'type',
        'flags',
        'reactions',
        'reference',
        'application',
        'activity',
        'stickers',
        'components',
        '_interaction',
        'interaction_metadata',
        'role_subscription',
        'application_id',
        'position',
        'poll',
        'call',
        'purchase_notification',
        'message_snapshots',
        '_created_at',
        'pinned_at',
        'ephemeral',
    )

    if TYPE_CHECKING:
        author: Union[User, Member]

    def __init__(
        self,
        *,
        state: ConnectionState,
        channel: MessageableChannel,
        data: Dict[str, Any],
    ) -> None:
        self._state: ConnectionState = state
        self.channel: MessageableChannel = channel
        self.id: int = int(data['id'])
        guild = getattr(channel, 'guild', None)
        if guild is None:
            guild_id = utils._snowflake(data.get('guildId'))
            guild = state._get_guild(guild_id) if guild_id else None
        self.guild: Optional[Guild] = guild
        self._from_data(data)

    def _from_data(self, data: Dict[str, Any]) -> None:
        state = self._state
        self.content: str = data.get('content') or ''
        self.nonce: Optional[Union[int, str]] = data.get('nonce') or None
        self.pinned: bool = bool(data.get('pinned', False))
        self.tts: bool = False
        self.webhook_id: Optional[int] = utils._snowflake(data.get('webhookId'))
        self._created_at: Optional[datetime.datetime] = utils.parse_time(data.get('createdAt'))
        self._edited_timestamp: Optional[datetime.datetime] = utils.parse_time(data.get('editedAt'))
        self.pinned_at: Optional[datetime.datetime] = None
        self.ephemeral: bool = bool(data.get('ephemeral', False))

        flags = utils._int(data.get('flags'), 0)
        if self.ephemeral:
            flags |= 64
        if data.get('loading'):
            flags |= 128
        self.flags: MessageFlags = MessageFlags._from_value(flags)

        self.embeds: List[Embed] = [Embed._from_bisim(e) for e in (data.get('embeds') or [])]
        self.attachments: List[Attachment] = [Attachment(data=a, state=state) for a in (data.get('attachments') or [])]
        self.reactions: List[Reaction] = [Reaction(message=self, data=r) for r in (data.get('reactions') or [])]
        self.components: List[Component] = []
        for row in data.get('components') or []:
            component = _component_factory(row)
            if component is not None:
                self.components.append(component)

        self.activity: Optional[Dict[str, Any]] = None
        self.application: Optional[Any] = None
        self.role_subscription: Optional[Any] = None
        self.position: Optional[int] = None
        self.call: Optional[Any] = None
        self.purchase_notification: Optional[Any] = None
        self.message_snapshots: List[Any] = []
        self._thread: Optional[Any] = None

        # Author
        author = data.get('author') or {}
        author_id = utils._snowflake(author.get('id') or data.get('authorId'))
        self.author = self._resolve_author(author, author_id)

        # Interaction this message answers
        interaction = data.get('interaction')
        self._interaction: Optional[MessageInteraction] = None
        self.interaction_metadata: Optional[MessageInteractionMetadata] = None
        self.application_id: Optional[int] = None
        if isinstance(interaction, dict) and interaction:
            self._interaction = MessageInteraction(state=state, guild=self.guild, data=interaction, fallback_id=self.id)
            self.interaction_metadata = MessageInteractionMetadata(
                state=state, guild=self.guild, data=interaction, fallback_id=self.id
            )
            self.application_id = author_id

        message_type = MessageType.from_bisim(data.get('type'))
        if message_type is MessageType.default and self._interaction is not None:
            message_type = MessageType.chat_input_command
        self.type: MessageType = message_type

        # Reply
        self.reference: Optional[MessageReference] = None
        ref_id = utils._snowflake(data.get('referencedMessageId'))
        ref_data = data.get('referencedMessage')
        if ref_id is not None or (isinstance(ref_data, dict) and ref_data.get('id')):
            if ref_id is None:
                ref_id = int(ref_data['id'])  # type: ignore
            ref_channel_id = utils._snowflake((ref_data or {}).get('channelId')) or self.channel.id
            reference = MessageReference.with_state(
                state,
                {
                    'message_id': ref_id,
                    'channel_id': ref_channel_id,
                    'guild_id': getattr(self.guild, 'id', None),
                },
            )
            if isinstance(ref_data, dict) and ref_data:
                if ref_data.get('deleted'):
                    reference.resolved = DeletedReferencedMessage(reference)
                else:
                    cached = state._get_message(ref_id)
                    if cached is not None:
                        reference.resolved = cached
                    else:
                        resolved_data = {
                            'id': str(ref_id),
                            'channelId': str(ref_channel_id),
                            'authorId': ref_data.get('authorId'),
                            'author': ref_data.get('author') or {'id': ref_data.get('authorId')},
                            'content': ref_data.get('content') or '',
                            'type': 'DEFAULT',
                        }
                        try:
                            reference.resolved = Message(state=state, channel=self.channel, data=resolved_data)
                        except Exception:
                            reference.resolved = None
            self.reference = reference

        # Poll
        poll_data = data.get('poll')
        self.poll: Optional[Poll] = None
        if isinstance(poll_data, dict) and poll_data:
            from .poll import Poll

            self.poll = Poll._from_data(data=poll_data, message=self, state=state)

        self._parse_mentions()

    def _resolve_author(self, author: Dict[str, Any], author_id: Optional[int]) -> Union[User, Member]:
        state = self._state
        if author_id is None:
            return state.create_user({'id': 0, 'username': 'Unknown'})
        if self.webhook_id is not None:
            # A webhook's name and picture belong to this message, not to a cached user.
            return state.create_user({**author, 'id': author_id, 'bot': True})
        if self.guild is not None:
            member = self.guild.get_member(author_id)
            if member is not None:
                if author:
                    member._user._patch(author)
                return member
        if author.get('id'):
            return state.store_user(author)
        user = state.get_user(author_id)
        if user is not None:
            return user
        return state.create_user({'id': author_id, 'username': ''})

    def _parse_mentions(self) -> None:
        content = self.content
        self.mention_everyone: bool = bool(_EVERYONE_RE.search(content))
        guild = self.guild
        state = self._state
        mentions: List[Union[User, Member]] = []
        seen = set()
        for raw in _USER_MENTION_RE.findall(content):
            user_id = int(raw)
            if user_id in seen:
                continue
            seen.add(user_id)
            found: Optional[Union[User, Member]] = None
            if guild is not None:
                found = guild.get_member(user_id)
            if found is None:
                found = state.get_user(user_id)
            if found is not None:
                mentions.append(found)
        self.mentions: List[Union[User, Member]] = mentions
        self.role_mentions: List[Role] = []
        if guild is not None:
            for raw in dict.fromkeys(_ROLE_MENTION_RE.findall(content)):
                role = guild.get_role(int(raw))
                if role is not None:
                    self.role_mentions.append(role)
        self.stickers: List[StickerItem] = [
            StickerItem._from_id(state, int(raw), guild) for raw in _STICKER_RE.findall(content)
        ]

    def _update(self, data: Dict[str, Any]) -> None:
        for attr in (
            '_cs_channel_mentions',
            '_cs_raw_mentions',
            '_cs_clean_content',
            '_cs_raw_channel_mentions',
            '_cs_raw_role_mentions',
            '_cs_system_content',
        ):
            try:
                delattr(self, attr)
            except AttributeError:
                pass
        self._from_data(data)

    def __repr__(self) -> str:
        name = self.__class__.__name__
        return (
            f'<{name} id={self.id} channel={self.channel!r} type={self.type!r} author={self.author!r} flags={self.flags!r}>'
        )

    def _add_reaction(self, data: Dict[str, Any], emoji: Any, user_id: int) -> Reaction:
        reaction = utils.find(lambda r: r.emoji == emoji, self.reactions)
        is_me = user_id == self._state.self_id

        if reaction is None:
            reaction = Reaction(message=self, data=data, emoji=emoji)
            self.reactions.append(reaction)
        else:
            reaction.count += 1
            if is_me:
                reaction.me = is_me
        return reaction

    def _remove_reaction(self, data: Dict[str, Any], emoji: Any, user_id: int) -> Reaction:
        reaction = utils.find(lambda r: r.emoji == emoji, self.reactions)

        if reaction is None:
            raise ValueError('Emoji already removed?')

        reaction.count -= 1
        if user_id == self._state.self_id:
            reaction.me = False
        if reaction.count == 0:
            self.reactions.remove(reaction)
        return reaction

    def _clear_emoji(self, emoji: Any) -> Optional[Reaction]:
        to_check = str(emoji)
        for index, reaction in enumerate(self.reactions):
            if str(reaction.emoji) == to_check:
                break
        else:
            return None
        del self.reactions[index]
        return reaction

    @property
    def interaction(self) -> Optional[MessageInteraction]:
        """Optional[:class:`~bisim.MessageInteraction`]: The interaction that this message is a response to."""
        return self._interaction

    @property
    def raw_mentions(self) -> List[int]:
        """List[:class:`int`]: A property that returns an array of user IDs matched with
        the syntax of ``<@user_id>`` in the message content.

        This allows you to receive the user IDs of mentioned users
        even in a private message context.
        """
        return [int(x) for x in _USER_MENTION_RE.findall(self.content)]

    @property
    def raw_channel_mentions(self) -> List[int]:
        """List[:class:`int`]: A property that returns an array of channel IDs matched with
        the syntax of ``<#channel_id>`` in the message content.
        """
        return [int(x) for x in _CHANNEL_MENTION_RE.findall(self.content)]

    @property
    def raw_role_mentions(self) -> List[int]:
        """List[:class:`int`]: A property that returns an array of role IDs matched with
        the syntax of ``<@&role_id>`` in the message content.
        """
        return [int(x) for x in _ROLE_MENTION_RE.findall(self.content)]

    @property
    def channel_mentions(self) -> List[Any]:
        """List[:class:`abc.GuildChannel`]: The channels mentioned in the message."""
        if self.guild is None:
            return []
        it = filter(None, map(self.guild._resolve_channel, self.raw_channel_mentions))
        return utils._unique(it)

    @property
    def clean_content(self) -> str:
        """:class:`str`: A property that returns the content in a "cleaned up"
        manner. This basically means that mentions are transformed
        into the way the client shows it. e.g. ``<#id>`` will transform
        into ``#name``.

        This will also transform @everyone and @here mentions into
        non-mentions.

        .. note::

            This *does not* affect markdown. If you want to escape
            or remove markdown then use :func:`utils.escape_markdown` or :func:`utils.remove_markdown`
            respectively, along with this function.
        """
        guild = self.guild

        def user_name(match: 're.Match[str]') -> str:
            user_id = int(match.group(1))
            member = guild.get_member(user_id) if guild is not None else None
            if member is not None:
                return '@' + member.display_name
            user = self._state.get_user(user_id)
            return '@' + user.display_name if user is not None else '@deleted-user'

        def role_name(match: 're.Match[str]') -> str:
            role = guild.get_role(int(match.group(1))) if guild is not None else None
            return '@' + role.name if role is not None else '@deleted-role'

        def channel_name(match: 're.Match[str]') -> str:
            channel = guild._resolve_channel(int(match.group(1))) if guild is not None else None
            return '#' + channel.name if channel is not None else '#deleted-channel'

        result = _USER_MENTION_RE.sub(user_name, self.content)
        result = _ROLE_MENTION_RE.sub(role_name, result)
        result = _CHANNEL_MENTION_RE.sub(channel_name, result)
        return utils.escape_mentions(result)

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: The message's creation time in UTC."""
        return self._created_at or utils.snowflake_time(self.id)

    @property
    def edited_at(self) -> Optional[datetime.datetime]:
        """Optional[:class:`datetime.datetime`]: An aware UTC datetime object containing the edited time of the message."""
        return self._edited_timestamp

    @property
    def thread(self) -> None:
        """Always ``None``: Bisim has no threads."""
        return None

    def is_system(self) -> bool:
        """:class:`bool`: Whether the message is a system message.

        A system message is a message that is constructed entirely by the Bisim API
        in response to something.
        """
        return self.type not in (
            MessageType.default,
            MessageType.reply,
            MessageType.chat_input_command,
            MessageType.context_menu_command,
            MessageType.thread_starter_message,
        )

    @property
    def system_content(self) -> str:
        r""":class:`str`: A property that returns the content that is rendered
        regardless of the :attr:`Message.type`.

        In the case of :attr:`MessageType.default` and :attr:`MessageType.reply`\,
        this just returns the regular :attr:`Message.content`. Otherwise this
        returns an English message denoting the contents of the system message.
        """
        if self.type in (MessageType.default, MessageType.reply, MessageType.chat_input_command):
            return self.content
        if self.type is MessageType.new_member:
            return f'{self.author.name} joined the server.'
        if self.type is MessageType.pins_add:
            return f'{self.author.name} pinned a message to this channel.'
        if self.type is MessageType.auto_moderation_action:
            return self.content or 'AutoMod blocked a message.'
        return self.content

    async def edit(
        self,
        *,
        content: Optional[str] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        attachments: Sequence[Union[Attachment, File]] = utils.MISSING,
        suppress: bool = False,
        delete_after: Optional[float] = None,
        allowed_mentions: Optional[AllowedMentions] = utils.MISSING,
        view: Optional[View] = utils.MISSING,
    ) -> Message:
        """|coro|

        Edits the message.

        The content must be able to be transformed into a string via ``str(content)``.

        Parameters
        -----------
        content: Optional[:class:`str`]
            The new content to replace the message with.
            Could be ``None`` to remove the content.
        embed: Optional[:class:`Embed`]
            The new embed to replace the original with.
            Could be ``None`` to remove the embed.
        embeds: List[:class:`Embed`]
            The new embeds to replace the original with. Must be a maximum of 10.
            To remove all embeds ``[]`` should be passed.
        attachments: List[Union[:class:`Attachment`, :class:`File`]]
            Not supported on Bisim.
        suppress: :class:`bool`
            Whether to suppress embeds for the message.
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.
        allowed_mentions: Optional[:class:`~bisim.AllowedMentions`]
            Accepted for compatibility.
        view: Optional[:class:`~bisim.ui.View`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.

        Raises
        -------
        HTTPException
            Editing the message failed.
        Forbidden
            Tried to suppress a message without permissions or
            edited a message's content or embed that isn't yours.
        TypeError
            You specified both ``embed`` and ``embeds``

        Returns
        --------
        :class:`Message`
            The newly edited message.
        """
        message = await super().edit(
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            delete_after=delete_after,
            allowed_mentions=allowed_mentions,
            view=view,
            suppress=suppress if suppress else utils.MISSING,
        )
        return message

    async def add_files(self, *files: File) -> Message:
        """|coro|

        Not supported on Bisim: a message's files cannot be changed.
        """
        raise NotSupported("Changing a message's attachments")

    async def remove_attachments(self, *attachments: Attachment) -> Message:
        """|coro|

        Not supported on Bisim: a message's files cannot be changed.
        """
        raise NotSupported("Changing a message's attachments")

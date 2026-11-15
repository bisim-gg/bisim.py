from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Union

import aiohttp

from .. import utils
from ..asset import Asset
from ..channel import PartialMessageable
from ..enums import ChannelType, WebhookType, try_enum
from ..errors import ClientException, HTTPException, NotSupported
from ..http import DEFAULT_API_URL, HTTPClient
from ..message import Message
from ..mixins import Hashable
from ..user import BaseUser, User

if TYPE_CHECKING:
    from ..abc import Snowflake
    from ..embeds import Embed
    from ..file import File
    from ..guild import Guild
    from ..mentions import AllowedMentions
    from ..state import ConnectionState

__all__ = (
    'Webhook',
    'WebhookMessage',
    'PartialWebhookChannel',
    'PartialWebhookGuild',
)

_log = logging.getLogger(__name__)

_WEBHOOK_URL_RE = re.compile(
    r'(?P<base>https?://[^\s]*?)/webhooks/(?P<id>[0-9]{1,20})/(?P<token>[A-Za-z0-9._-]{20,})'
)


class _WebhookState:
    """The little state a webhook needs to build messages when no client is around."""

    def __init__(self, webhook: Any, parent: Optional[ConnectionState], http: HTTPClient) -> None:
        self._webhook = webhook
        self._parent = parent
        self.http = http

    @property
    def self_id(self) -> Optional[int]:
        return self._parent.self_id if self._parent is not None else None

    @property
    def user(self) -> Any:
        return self._parent.user if self._parent is not None else None

    def _get_guild(self, guild_id: Optional[int]) -> Optional[Guild]:
        if self._parent is not None:
            return self._parent._get_guild(guild_id)
        return None

    def _get_message(self, message_id: Optional[int]) -> Optional[Message]:
        if self._parent is not None:
            return self._parent._get_message(message_id)
        return None

    def _get_sticker(self, sticker_id: int) -> Any:
        if self._parent is not None:
            return self._parent._get_sticker(sticker_id)
        return None

    def get_emoji(self, emoji_id: Optional[int]) -> Any:
        if self._parent is not None:
            return self._parent.get_emoji(emoji_id)
        return None

    def get_user(self, user_id: Optional[int]) -> Optional[User]:
        if self._parent is not None:
            return self._parent.get_user(user_id)
        return None

    def store_user(self, data: Dict[str, Any], *, cache: bool = True) -> User:
        if self._parent is not None:
            return self._parent.store_user(data, cache=cache)
        return User(state=self, data=data)  # type: ignore

    def create_user(self, data: Dict[str, Any]) -> User:
        if self._parent is not None:
            return self._parent.create_user(data)
        return User(state=self, data=data)  # type: ignore

    def _resolve_reaction_emoji(self, value: str) -> Any:
        from ..partial_emoji import PartialEmoji

        emoji = PartialEmoji.from_str(value)
        if emoji.id is None:
            return emoji.name
        return emoji

    def store_view(self, view: Any, message_id: Optional[int] = None) -> None:
        if self._parent is not None:
            self._parent.store_view(view, message_id)

    def create_message(self, *, channel: Any, data: Dict[str, Any]) -> Message:
        return Message(state=self, channel=channel, data=data)  # type: ignore

    def __getattr__(self, attr: str) -> Any:
        if self._parent is not None:
            return getattr(self._parent, attr)
        raise AttributeError(f'PartialWebhookState does not support {attr!r}.')


class PartialWebhookChannel(Hashable):
    """Represents a partial channel for webhooks.

    Attributes
    -----------
    id: :class:`int`
        The partial channel's ID.
    name: :class:`str`
        The partial channel's name.
    """

    __slots__ = ('id', 'name')

    def __init__(self, *, data: Dict[str, Any]) -> None:
        self.id: int = int(data['id'])
        self.name: str = data.get('name') or ''

    def __repr__(self) -> str:
        return f'<PartialWebhookChannel name={self.name!r} id={self.id}>'


class PartialWebhookGuild(Hashable):
    """Represents a partial guild for webhooks.

    Attributes
    -----------
    id: :class:`int`
        The partial guild's ID.
    name: :class:`str`
        The partial guild's name.
    """

    __slots__ = ('id', 'name', '_icon', '_state')

    def __init__(self, *, data: Dict[str, Any], state: Any) -> None:
        self._state = state
        self.id: int = int(data['id'])
        self.name: str = data.get('name') or ''
        self._icon: Optional[str] = data.get('iconKey') or None

    def __repr__(self) -> str:
        return f'<PartialWebhookGuild name={self.name!r} id={self.id}>'

    @property
    def icon(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns the guild's icon asset, if available."""
        if self._icon is None:
            return None
        return Asset._from_guild_icon(self._state, self.id, self._icon)


class WebhookMessage(Message):
    """Represents a message sent from your webhook.

    This allows you to edit or delete a message sent by your webhook, or by
    an interaction's followups.

    This inherits from :class:`bisim.Message` with changes to
    :meth:`edit` and :meth:`delete` to work.
    """

    __slots__ = ('_webhook',)

    async def edit(
        self,
        *,
        content: Optional[str] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        attachments: Sequence[Any] = utils.MISSING,
        view: Any = utils.MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
        **kwargs: Any,
    ) -> WebhookMessage:
        """|coro|

        Edits the message.

        Parameters
        ------------
        content: Optional[:class:`str`]
            The content to edit the message with or ``None`` to clear it.
        embeds: List[:class:`Embed`]
            A list of embeds to edit the message with.
        embed: Optional[:class:`Embed`]
            The embed to edit the message with. ``None`` suppresses the embeds.
            This should not be mixed with the ``embeds`` parameter.
        attachments: List[Union[:class:`Attachment`, :class:`File`]]
            A list of attachments to keep in the message as well as new files to upload. If ``[]`` is passed
            then all attachments are removed.

            .. note::

                New files will always appear after current attachments.
        view: Optional[:class:`~bisim.ui.View`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed. Only an interaction's followups carry a view.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.

        Raises
        -------
        HTTPException
            Editing the message failed.
        Forbidden
            Edited a message that is not yours.
        TypeError
            You specified both ``embed`` and ``embeds``

        Returns
        --------
        :class:`WebhookMessage`
            The newly edited message.
        """
        extra: Dict[str, Any] = {}
        suppress = kwargs.pop('suppress', utils.MISSING)
        if suppress is not utils.MISSING:
            # Message.edit's spelling, for a webhook's own message.
            extra['suppress_embeds'] = suppress
        delete_after = kwargs.pop('delete_after', None)
        if kwargs:
            raise TypeError(f'edit() got an unexpected keyword argument {next(iter(kwargs))!r}')
        message = await self._webhook.edit_message(
            self.id,
            content=content,
            embeds=embeds,
            embed=embed,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
            **extra,
        )
        if delete_after is not None:
            await self.delete(delay=delete_after)
        return message

    async def delete(self, *, delay: Optional[float] = None) -> None:
        """|coro|

        Deletes the message.

        Parameters
        -----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.
            The waiting is done in the background and deletion failures are ignored.

        Raises
        ------
        Forbidden
            You do not have proper permissions to delete the message.
        NotFound
            The message was deleted already.
        HTTPException
            Deleting the message failed.
        """
        if delay is not None:

            async def inner_call(delay: float = delay) -> None:
                await asyncio.sleep(delay)
                try:
                    await self._webhook.delete_message(self.id)
                except HTTPException:
                    pass

            asyncio.create_task(inner_call())
        else:
            await self._webhook.delete_message(self.id)


class BaseWebhook(Hashable):
    __slots__ = (
        'id',
        'type',
        'guild_id',
        'channel_id',
        'token',
        'auth_token',
        'user',
        'name',
        '_avatar',
        'source_channel',
        'source_guild',
        '_state',
    )

    def __init__(self, data: Dict[str, Any], token: Optional[str] = None, state: Optional[Any] = None) -> None:
        self.auth_token: Optional[str] = token
        self._state: Any = state
        self._update(data)

    def _update(self, data: Dict[str, Any]) -> None:
        self.id: int = int(data['id'])
        self.type: WebhookType = WebhookType.incoming
        self.channel_id: Optional[int] = utils._snowflake(data.get('channelId'))
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))
        self.name: Optional[str] = data.get('name')
        self._avatar: Optional[str] = data.get('avatarKey') or None
        self.token: Optional[str] = data.get('token') or None
        self.user: Optional[BaseUser] = None
        creator = data.get('creator')
        if isinstance(creator, dict) and creator.get('id') and self._state is not None:
            self.user = self._state.store_user(creator) if hasattr(self._state, 'store_user') else None
        self.source_channel: Optional[PartialWebhookChannel] = None
        self.source_guild: Optional[PartialWebhookGuild] = None

    def is_partial(self) -> bool:
        """:class:`bool`: Whether the webhook is a "partial" webhook."""
        return self.channel_id is None

    def is_authenticated(self) -> bool:
        """:class:`bool`: Whether the webhook is authenticated with a bot token."""
        return self.auth_token is not None

    @property
    def guild(self) -> Optional[Guild]:
        """Optional[:class:`Guild`]: The guild this webhook belongs to.

        If this is a partial webhook, then this will always return ``None``.
        """
        return self._state and self._state._get_guild(self.guild_id)

    @property
    def channel(self) -> Optional[Any]:
        """Optional[:class:`TextChannel`]: The channel this webhook belongs to.

        If this is a partial webhook, then this will always return ``None``.
        """
        guild = self.guild
        return guild and guild.get_channel(self.channel_id)  # type: ignore

    @property
    def created_at(self) -> Any:
        """:class:`datetime.datetime`: Returns the webhook's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def avatar(self) -> Optional[Asset]:
        """Optional[:class:`Asset`]: Returns an :class:`Asset` for the avatar the webhook has."""
        if self._avatar is not None:
            return Asset._from_key(self._state, self._avatar)
        return None

    @property
    def default_avatar(self) -> Asset:
        """:class:`Asset`: Returns the default avatar."""
        return Asset._from_default_avatar(self._state, 0)

    @property
    def display_avatar(self) -> Asset:
        """:class:`Asset`: Returns the webhook's display avatar."""
        return self.avatar or self.default_avatar


class Webhook(BaseWebhook):
    """Represents an asynchronous Bisim webhook.

    Webhooks are a form to send messages to channels in Bisim without a
    bot user or authentication.

    There are two main ways to use Webhooks. The first is through the ones
    received by the library such as :meth:`.Guild.webhooks` and
    :meth:`.TextChannel.webhooks`. The ones received by the library will
    automatically be bound using the library's internal HTTP session.

    The second form involves creating a webhook object manually using the
    :meth:`~.Webhook.from_url` or :meth:`~.Webhook.partial` classmethods.

    For example, creating a webhook from a URL and using :doc:`aiohttp <aio:index>`:

    .. code-block:: python3

        from bisim import Webhook
        import aiohttp

        async def foo():
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url('https://api.bisim.gg/api/webhooks/123/abc...', session=session)
                await webhook.send('Hello World', username='Foo')

    .. container:: operations

        .. describe:: x == y

            Checks if two webhooks are equal.

        .. describe:: x != y

            Checks if two webhooks are not equal.

        .. describe:: hash(x)

            Returns the webhooks's hash.

    Attributes
    ------------
    id: :class:`int`
        The webhook's ID
    type: :class:`WebhookType`
        The type of the webhook (always incoming on Bisim).
    token: Optional[:class:`str`]
        The authentication token of the webhook. If this is ``None``
        then the webhook cannot be used to make requests.
    guild_id: Optional[:class:`int`]
        The guild ID this webhook is for.
    channel_id: Optional[:class:`int`]
        The channel ID this webhook is for.
    user: Optional[:class:`abc.User`]
        The user this webhook was created by.
    name: Optional[:class:`str`]
        The default name of the webhook.
    """

    __slots__ = ('_http', '_api_url')

    def __init__(
        self,
        data: Dict[str, Any],
        session: Optional[aiohttp.ClientSession] = None,
        token: Optional[str] = None,
        state: Optional[Any] = None,
        *,
        http: Optional[HTTPClient] = None,
        api_url: Optional[str] = None,
    ) -> None:
        if http is None:
            http = HTTPClient(api_url=api_url)
            if session is not None:
                http._use_session(session)
            if token is not None:
                http.token = token
        self._http: HTTPClient = http
        self._api_url: str = (api_url or http.api_url).rstrip('/')
        super().__init__(data, token, state)
        if self._state is None or not hasattr(self._state, 'http'):
            self._state = _WebhookState(self, state, http)

    def __repr__(self) -> str:
        return f'<Webhook id={self.id!r} type={self.type!r} name={self.name!r}>'

    @property
    def url(self) -> str:
        """:class:`str` : Returns the webhook's url."""
        return f'{self._api_url}/webhooks/{self.id}/{self.token}'

    @classmethod
    def partial(
        cls,
        id: int,
        token: str,
        *,
        session: aiohttp.ClientSession = utils.MISSING,
        client: Any = utils.MISSING,
        bot_token: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> Webhook:
        """Creates a partial :class:`Webhook`.

        Parameters
        -----------
        id: :class:`int`
            The ID of the webhook.
        token: :class:`str`
            The authentication token of the webhook.
        session: :class:`aiohttp.ClientSession`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it.
        client: :class:`Client`
            The client to initialise this webhook with. This allows it to
            attach the client's internal state.
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.
        api_url: Optional[:class:`str`]
            Bisim's REST address, for a local server. Defaults to the client's,
            or ``https://api.bisim.gg/api``.

        Raises
        -------
        TypeError
            Neither ``session`` nor ``client`` were given.

        Returns
        --------
        :class:`Webhook`
            A partial :class:`Webhook`.
            A partial webhook is just a webhook object with an ID and a token.
        """
        data = {'id': id, 'type': 1, 'token': token}
        state = None
        http = None
        if client is not utils.MISSING:
            state = client._connection
            http = client.http
            bot_token = bot_token or client.http.token
        elif session is utils.MISSING:
            raise TypeError('session or client must be given')
        return cls(
            data,
            session=session if session is not utils.MISSING else None,
            token=bot_token,
            state=state,
            http=http,
            api_url=api_url,
        )

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        session: aiohttp.ClientSession = utils.MISSING,
        client: Any = utils.MISSING,
        bot_token: Optional[str] = None,
    ) -> Webhook:
        """Creates a partial :class:`Webhook` from a webhook URL.

        Parameters
        ------------
        url: :class:`str`
            The URL of the webhook, ``https://api.bisim.gg/api/webhooks/<id>/<token>``.
        session: :class:`aiohttp.ClientSession`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it.
        client: :class:`Client`
            The client to initialise this webhook with.
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

        Raises
        -------
        ValueError
            The URL is invalid.
        TypeError
            Neither ``session`` nor ``client`` were given.

        Returns
        --------
        :class:`Webhook`
            A partial :class:`Webhook`.
            A partial webhook is just a webhook object with an ID and a token.
        """
        match = _WEBHOOK_URL_RE.search(url)
        if match is None:
            raise ValueError('Invalid webhook URL given.')

        data: Dict[str, Any] = match.groupdict()
        api_url = data.pop('base')
        data['type'] = 1
        state = None
        http = None
        if client is not utils.MISSING:
            state = client._connection
            http = client.http
            bot_token = bot_token or client.http.token
        elif session is utils.MISSING:
            raise TypeError('session or client must be given')
        return cls(
            data,
            session=session if session is not utils.MISSING else None,
            token=bot_token,
            state=state,
            http=http,
            api_url=api_url,
        )

    @classmethod
    def from_state(cls, data: Dict[str, Any], state: ConnectionState) -> Webhook:
        return cls(data, state=state, http=state.http, token=state.http.token)

    def _authenticated(self) -> None:
        if self.auth_token is None and self._http.token is None:
            raise ValueError('This webhook is not authenticated with a bot token')

    async def fetch(self, *, prefer_auth: bool = True) -> Webhook:
        """|coro|

        Fetches the current webhook.

        This could be used to get a full webhook from a partial webhook.

        Parameters
        -----------
        prefer_auth: :class:`bool`
            Accepted for compatibility; Bisim reads a webhook with the bot token.

        Raises
        -------
        HTTPException
            Could not fetch the webhook
        NotFound
            Could not find the webhook by this ID
        ValueError
            This webhook does not have a bot token.

        Returns
        --------
        :class:`Webhook`
            The fetched webhook.
        """
        self._authenticated()
        data = await self._http.get_webhook(self.id)
        return Webhook(data, token=self.auth_token, state=self._state, http=self._http, api_url=self._api_url)

    async def delete(self, *, reason: Optional[str] = None, prefer_auth: bool = True) -> None:
        """|coro|

        Deletes this Webhook.

        Parameters
        ------------
        reason: Optional[:class:`str`]
            The reason for deleting this webhook. Shows up on the audit log.
        prefer_auth: :class:`bool`
            Accepted for compatibility.

        Raises
        -------
        HTTPException
            Deleting the webhook failed.
        NotFound
            This webhook does not exist.
        Forbidden
            You do not have permissions to delete this webhook.
        ValueError
            This webhook does not have a bot token.
        """
        self._authenticated()
        await self._http.delete_webhook(self.id, reason=reason)

    async def edit(
        self,
        *,
        reason: Optional[str] = None,
        name: Optional[str] = utils.MISSING,
        avatar: Optional[bytes] = utils.MISSING,
        channel: Optional[Snowflake] = None,
        prefer_auth: bool = True,
    ) -> Webhook:
        """|coro|

        Edits this Webhook.

        Parameters
        ------------
        name: Optional[:class:`str`]
            The webhook's new default name.
        avatar: Optional[:class:`bytes`]
            A :term:`py:bytes-like object` representing the webhook's new default avatar,
            or ``None`` to remove it. Messages the webhook posts afterwards show it;
            what it already posted keeps the picture it had.
        channel: Optional[:class:`abc.Snowflake`]
            The webhook's new channel.
        reason: Optional[:class:`str`]
            The reason for editing this webhook. Shows up on the audit log.

        Raises
        -------
        HTTPException
            Editing the webhook failed.
        NotFound
            This webhook does not exist.
        ValueError
            This webhook does not have a bot token.

        Returns
        --------
        :class:`Webhook`
            The newly edited webhook.
        """
        self._authenticated()
        fields: Dict[str, Any] = {}
        if name is not utils.MISSING:
            fields['name'] = str(name) if name is not None else None
        if channel is not None:
            fields['channelId'] = str(channel.id)
        data: Any = None
        if fields:
            data = await self._http.edit_webhook(self.id, reason=reason, **fields)
        if avatar is not utils.MISSING:
            if avatar is None:
                data = await self._http.delete_webhook_avatar(self.id, reason=reason)
            else:
                data = await self._http.edit_webhook_avatar(
                    self.id, bytes(avatar), utils._get_mime_type_for_image(bytes(avatar)), reason=reason
                )
        if isinstance(data, dict) and data.get('id'):
            self._update(data)
        return self

    def _create_message(self, data: Dict[str, Any]) -> WebhookMessage:
        state = self._state
        channel_id = utils._snowflake(data.get('channelId')) or self.channel_id or 0
        channel: Any = None
        guild = state._get_guild(self.guild_id) if self.guild_id else None
        if guild is not None:
            channel = guild.get_channel(channel_id)
        if channel is None:
            channel = PartialMessageable(state=state, id=channel_id, guild_id=self.guild_id, type=ChannelType.text)  # type: ignore
        message = WebhookMessage(state=state, channel=channel, data=data)  # type: ignore
        message._webhook = self
        return message

    def _need_token(self) -> str:
        if self.token is None:
            raise ValueError('This webhook does not have a token associated with it')
        return self.token

    async def _create_uploads(self, files: List[Dict[str, Any]]) -> Any:
        """Upload addresses for the webhook's message files, asked for with its token."""
        return await self._http.create_webhook_attachments(self.id, self._need_token(), files)

    async def send(
        self,
        content: str = utils.MISSING,
        *,
        username: str = utils.MISSING,
        avatar_url: Any = utils.MISSING,
        tts: bool = False,
        ephemeral: bool = False,
        file: File = utils.MISSING,
        files: Sequence[File] = utils.MISSING,
        embed: Embed = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        allowed_mentions: AllowedMentions = utils.MISSING,
        view: Any = utils.MISSING,
        thread: Snowflake = utils.MISSING,
        thread_name: str = utils.MISSING,
        wait: bool = False,
        suppress_embeds: bool = False,
        silent: bool = False,
        applied_tags: Any = utils.MISSING,
        poll: Any = utils.MISSING,
    ) -> Optional[WebhookMessage]:
        """|coro|

        Sends a message using the webhook.

        The content must be a type that can convert to a string through ``str(content)``.

        To upload a single file, the ``file`` parameter should be used with a
        single :class:`File` object.

        If the ``embed`` parameter is provided, it must be of type :class:`Embed` and
        it must be a rich embed type. You cannot mix the ``embed`` parameter with the
        ``embeds`` parameter, which must be a :class:`list` of :class:`Embed` objects to send.

        Parameters
        ------------
        content: :class:`str`
            The content of the message to send.
        wait: :class:`bool`
            Whether the server should wait before sending a response. This essentially
            means that the return type of this function changes from ``None`` to
            a :class:`WebhookMessage` if set to ``True``.
        username: :class:`str`
            The username to send with this message. If no username is provided
            then the default username for the webhook is used.
        avatar_url: :class:`str`
            Accepted for compatibility. Bisim never shows an outside picture on a
            webhook's message; give the webhook its own picture with :meth:`edit`.
        tts: :class:`bool`
            Accepted for compatibility.
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.
        embed: :class:`Embed`
            The rich embed for the content to send. This cannot be mixed with
            ``embeds`` parameter.
        embeds: List[:class:`Embed`]
            A list of embeds to send with the content. Maximum of 10. This cannot
            be mixed with the ``embed`` parameter.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.
        silent: :class:`bool`
            Whether to suppress push and desktop notifications for the message.
        view: :class:`bisim.ui.View`
            Not supported on Bisim webhooks.
        thread: :class:`~bisim.abc.Snowflake`
            Not supported on Bisim (no threads).
        poll: :class:`Poll`
            Not supported on Bisim webhooks.

        Raises
        --------
        HTTPException
            Sending the message failed.
        NotFound
            This webhook was not found.
        Forbidden
            The authorization token for the webhook is incorrect.
        TypeError
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``.
        ValueError
            The length of ``embeds`` was invalid, or there was no token
            associated with this webhook.
        NotSupported
            A view, a thread or a poll was given.

        Returns
        ---------
        Optional[:class:`WebhookMessage`]
            If ``wait`` is ``True`` then the message that was sent, otherwise ``None``.
        """
        token = self._need_token()
        if view is not utils.MISSING and view is not None:
            raise NotSupported('Components on webhook messages')
        if thread is not utils.MISSING or thread_name is not utils.MISSING or applied_tags is not utils.MISSING:
            raise NotSupported('Threads')
        if poll is not utils.MISSING and poll is not None:
            raise NotSupported('Polls through a webhook')
        if ephemeral:
            raise NotSupported('Ephemeral messages from a plain webhook')

        from ..abc import _message_payload

        payload = await _message_payload(
            self._state,
            None,
            content=content if content is not None else utils.MISSING,
            embed=embed if embed is not None else utils.MISSING,
            embeds=embeds if embeds is not None else utils.MISSING,
            file=file,
            files=files,
            silent=silent,
            suppress_embeds=suppress_embeds,
            allowed_mentions=allowed_mentions,
            create_uploads=self._create_uploads,
        )
        payload.pop('nonce', None)
        if username is not utils.MISSING and username:
            payload['username'] = username

        data = await self._http.execute_webhook(self.id, token, payload, wait=wait)
        if wait and isinstance(data, dict):
            return self._create_message(data)
        return None

    async def fetch_message(self, id: int, /, *, thread: Snowflake = utils.MISSING) -> WebhookMessage:
        """|coro|

        Retrieves a single :class:`~bisim.WebhookMessage` owned by this webhook.

        Parameters
        ------------
        id: :class:`int`
            The message ID to look for.
        thread: :class:`~bisim.abc.Snowflake`
            Not supported on Bisim (no threads).

        Raises
        --------
        ~bisim.NotFound
            The specified message was not found, or this webhook did not post it.
        ~bisim.Forbidden
            You do not have the permissions required to get a message.
        ~bisim.HTTPException
            Retrieving the message failed.
        ValueError
            There was no token associated with this webhook.

        Returns
        --------
        :class:`~bisim.WebhookMessage`
            The message asked for.
        """
        if thread is not utils.MISSING:
            raise NotSupported('Threads')
        data = await self._http.get_webhook_message(self.id, self._need_token(), id)
        return self._create_message(data)

    async def edit_message(
        self,
        message_id: int,
        *,
        content: Optional[str] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        attachments: Sequence[Any] = utils.MISSING,
        view: Any = utils.MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
        thread: Snowflake = utils.MISSING,
        suppress_embeds: bool = utils.MISSING,
    ) -> WebhookMessage:
        """|coro|

        Edits a message owned by this webhook.

        This is a lower level interface to :meth:`WebhookMessage.edit` in case
        you only have an ID.

        Parameters
        ------------
        message_id: :class:`int`
            The message ID to edit.
        content: Optional[:class:`str`]
            The content to edit the message with or ``None`` to clear it.
        embeds: List[:class:`Embed`]
            A list of embeds to edit the message with.
        embed: Optional[:class:`Embed`]
            The embed to edit the message with. ``None`` suppresses the embeds.
            This should not be mixed with the ``embeds`` parameter.
        attachments: List[Union[:class:`Attachment`, :class:`File`]]
            A list of attachments to keep in the message as well as new files to upload. If ``[]`` is passed
            then all attachments are removed.

            .. note::

                New files will always appear after current attachments.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~bisim.ui.View`]
            Not supported on Bisim webhooks.
        thread: :class:`~bisim.abc.Snowflake`
            Not supported on Bisim (no threads).
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message (``False`` brings them
            back). This is a Bisim addition.

        Raises
        -------
        HTTPException
            Editing the message failed.
        Forbidden
            Edited a message that is not yours.
        TypeError
            You specified both ``embed`` and ``embeds``
        ValueError
            The length of ``embeds`` was invalid,
            or there was no token associated with this webhook.

        Returns
        --------
        :class:`WebhookMessage`
            The newly edited webhook message.
        """
        if view is not utils.MISSING and view is not None:
            raise NotSupported('Components on webhook messages')
        if thread is not utils.MISSING:
            raise NotSupported('Threads')
        token = self._need_token()

        from ..abc import _message_payload

        payload = await _message_payload(
            self._state,
            None,
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            suppress_embeds=suppress_embeds,
            allowed_mentions=allowed_mentions,
            editing=True,
            create_uploads=self._create_uploads,
        )
        data = await self._http.edit_webhook_message(self.id, token, message_id, payload)
        return self._create_message(data)

    async def delete_message(self, message_id: int, /, *, thread: Snowflake = utils.MISSING) -> None:
        """|coro|

        Deletes a message owned by this webhook.

        This is a lower level interface to :meth:`WebhookMessage.delete` in case
        you only have an ID.

        Parameters
        ------------
        message_id: :class:`int`
            The message ID to delete.
        thread: :class:`~bisim.abc.Snowflake`
            Not supported on Bisim (no threads).

        Raises
        -------
        HTTPException
            Deleting the message failed.
        Forbidden
            Deleted a message that is not yours.
        ValueError
            There was no token associated with this webhook.
        """
        if thread is not utils.MISSING:
            raise NotSupported('Threads')
        await self._http.delete_webhook_message(self.id, self._need_token(), message_id)

"""Interactions: slash commands, buttons, select menus, modals and autocomplete.

An interaction reaches the bot over the gateway (``INTERACTION_CREATE``) or,
for an application with an Interactions URL, as a signed HTTP request (see
:mod:`bisim.http_interactions`). Either way it is answered with the
interaction's own token, within 15 minutes, once.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, Sequence, Tuple, TypeVar, Union

from . import utils
from .channel import DMChannel, PartialMessageable
from .enums import ChannelType, InteractionResponseType, InteractionType, Locale, try_enum
from .errors import ClientException, HTTPException, InteractionResponded, NotSupported
from .flags import AppCommandContext
from .member import Member
from .message import Attachment, Message
from .object import Object
from .permissions import Permissions
from .user import User
from .webhook.async_ import WebhookMessage

if TYPE_CHECKING:
    from .app_commands.commands import Command, ContextMenu
    from .app_commands.models import Choice
    from .app_commands.namespace import Namespace
    from .client import Client
    from .embeds import Embed
    from .file import File
    from .guild import Guild
    from .mentions import AllowedMentions
    from .poll import Poll
    from .state import ConnectionState
    from .ui.modal import Modal
    from .ui.view import View

__all__ = (
    'Interaction',
    'InteractionMessage',
    'InteractionResponse',
    'InteractionCallbackResponse',
    'InteractionCallbackActivityInstance',
    'InteractionFollowup',
)

_log = logging.getLogger(__name__)

ClientT = TypeVar('ClientT', bound='Client', covariant=True)

INTERACTION_LIFETIME = datetime.timedelta(minutes=15)


def _resolve_locale(value: Any) -> Locale:
    if not value:
        return Locale.persian
    return try_enum(Locale, value)


class Interaction(Generic[ClientT]):
    """Represents a Bisim interaction.

    An interaction happens when a user does an action that needs to
    be notified. Current examples are slash commands and components.

    Attributes
    -----------
    id: :class:`int`
        The interaction's ID.
    type: :class:`InteractionType`
        The interaction type.
    guild_id: Optional[:class:`int`]
        The guild ID the interaction was sent from.
    channel: Optional[Union[:class:`abc.GuildChannel`, :class:`abc.PrivateChannel`, :class:`PartialMessageable`]]
        The channel the interaction was sent from.
    application_id: :class:`int`
        The application ID that the interaction was for (the bot's user ID).
    user: Union[:class:`User`, :class:`Member`]
        The user or member that sent the interaction.
    message: Optional[:class:`Message`]
        The message that sent this interaction (for components).
    token: :class:`str`
        The token to continue the interaction. These are valid
        for 15 minutes.
    data: :class:`dict`
        The raw interaction data.
    locale: :class:`Locale`
        The locale of the user invoking the interaction (``fa`` or ``en`` on Bisim).
    guild_locale: Optional[:class:`Locale`]
        Always ``None``.
    extras: :class:`dict`
        A dictionary that can be used to store extraneous data for use during
        interaction processing. The library will not touch any values or keys
        within this dictionary.
    command_failed: :class:`bool`
        Whether the command associated with this interaction failed to execute.
        This includes checks and execution.
    context: :class:`AppCommandContext`
        The context of the interaction (a server or the DM with the bot).
    filesize_limit: :class:`int`
        The maximum number of bytes a file can have when responding to this interaction.
    """

    __slots__: Tuple[str, ...] = (
        'id',
        'type',
        'guild_id',
        'data',
        'application_id',
        'message',
        'user',
        'token',
        'version',
        'locale',
        'guild_locale',
        'extras',
        'command_failed',
        'entitlement_sku_ids',
        'entitlements',
        'context',
        'filesize_limit',
        '_permissions',
        '_app_permissions',
        '_state',
        '_client',
        '_original_response',
        '_cs_response',
        '_cs_followup',
        'channel',
        '_cs_namespace',
        '_cs_command',
        '_raw',
        '_guild',
    )

    def __init__(self, *, data: Dict[str, Any], state: ConnectionState) -> None:
        self._state: ConnectionState = state
        self._client: ClientT = state._get_client()  # type: ignore
        self._original_response: Optional[InteractionMessage] = None
        self._raw: Dict[str, Any] = data
        self._from_data(data)

    def __repr__(self) -> str:
        return f'<Interaction id={self.id} type={self.type!r} guild_id={self.guild_id!r} user={self.user!r}>'

    def _from_data(self, data: Dict[str, Any]) -> None:
        state = self._state
        self.id: int = int(data['id'])
        self.type: InteractionType = try_enum(InteractionType, int(data.get('type', 2)))
        self.data: Optional[Dict[str, Any]] = data.get('data')
        self.token: str = data['token']
        self.version: int = int(data.get('version', 1) or 1)
        self.application_id: int = int(data.get('applicationId') or state.application_id or 0)
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))
        self.locale: Locale = _resolve_locale(data.get('locale'))
        self.guild_locale: Optional[Locale] = None
        self.extras: Dict[Any, Any] = {}
        self.command_failed: bool = False
        self.entitlement_sku_ids: List[int] = []
        self.entitlements: List[Any] = []
        self.filesize_limit: int = state._upload_limit or 10 * 1024 * 1024
        self._app_permissions: int = utils._int(data.get('appPermissions'), 0)
        self._permissions: int = 0

        context = AppCommandContext()
        if self.guild_id is not None:
            context.guild = True
        else:
            context.dm_channel = True
        self.context: AppCommandContext = context

        guild: Optional[Guild] = state._get_guild(self.guild_id) if self.guild_id else None
        if guild is None and self.guild_id is not None:
            from .guild import Guild

            # An HTTP-only bot may not have the server loaded.
            guild = Guild(data={'id': self.guild_id}, state=state)
        self._guild: Optional[Guild] = guild

        # The user: a member in a server, a user elsewhere.
        user_data = data.get('user')
        member_data = data.get('member')
        self.user: Union[User, Member]
        if guild is not None and isinstance(member_data, dict) and member_data:
            payload = dict(member_data)
            if isinstance(user_data, dict) and user_data and 'user' not in payload:
                payload['user'] = user_data
            user_id = int(payload.get('userId') or (payload.get('user') or {}).get('id'))
            cached = guild.get_member(user_id) if self._state._get_guild(self.guild_id) is not None else None
            if cached is not None:
                cached._update(payload)
                if isinstance(payload.get('user'), dict):
                    cached._user._patch(payload['user'])
                elif payload.get('username'):
                    cached._user._patch(payload)
                self.user = cached
            else:
                self.user = Member(data=payload, guild=guild, state=state)
            self._permissions = self.user._permissions or 0
        elif isinstance(user_data, dict) and user_data:
            self.user = state.store_user(user_data)
        elif isinstance(member_data, dict) and member_data:
            self.user = state.store_user(
                {
                    'id': member_data.get('userId'),
                    'username': member_data.get('username'),
                    'displayName': member_data.get('displayName'),
                    'avatarKey': member_data.get('avatarKey'),
                }
            )
        else:
            self.user = state.create_user({'id': 0, 'username': ''})

        # The channel
        channel_id = utils._snowflake(data.get('channelId'))
        channel: Any = None
        if channel_id is not None:
            channel = state.get_channel(channel_id)
            if channel is None:
                if self.guild_id is not None:
                    channel = PartialMessageable(state=state, id=channel_id, guild_id=self.guild_id, type=ChannelType.text)
                else:
                    recipient = self.user if isinstance(self.user, User) else None
                    channel = DMChannel._from_message(state, channel_id, recipient)  # type: ignore
                    state._add_private_channel(channel)
        self.channel: Optional[Any] = channel

        # The message a component sits on
        self.message: Optional[Message] = None
        message_data = data.get('message')
        if isinstance(message_data, dict) and message_data and channel is not None:
            cached_message = state._get_message(int(message_data['id']))
            if cached_message is not None:
                cached_message._update(message_data)
                self.message = cached_message
            else:
                self.message = Message(state=state, channel=channel, data=message_data)

    @property
    def client(self) -> ClientT:
        """:class:`Client`: The client that is handling this interaction."""
        return self._client

    @property
    def guild(self) -> Optional[Guild]:
        """Optional[:class:`Guild`]: The guild the interaction was sent from."""
        return self._state._get_guild(self.guild_id) or self._guild

    @property
    def channel_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The ID of the channel the interaction was sent from."""
        return self.channel.id if self.channel is not None else None

    @property
    def permissions(self) -> Permissions:
        """:class:`Permissions`: The resolved permissions of the member in the channel, including overwrites.

        In a non-guild context where this doesn't apply, an empty permissions object is returned.
        """
        return Permissions(self._permissions)

    @property
    def app_permissions(self) -> Permissions:
        """:class:`Permissions`: The resolved permissions of the application or the bot, including overwrites."""
        return Permissions(self._app_permissions)

    @utils.cached_slot_property('_cs_namespace')
    def namespace(self) -> Namespace:
        """:class:`app_commands.Namespace`: The resolved namespace for this interaction.

        If the interaction is not an application command related interaction or the client does not have a
        tree attached to it then this returns an empty namespace.
        """
        from .app_commands.namespace import Namespace

        if self.type not in (InteractionType.application_command, InteractionType.autocomplete):
            return Namespace(self, {}, [])

        tree = self._state._command_tree
        if tree is None:
            return Namespace(self, {}, [])

        data = self.data or {}
        from .enums import AppCommandType as _AppCommandType

        if _AppCommandType.from_bisim(data.get('type')) is not _AppCommandType.chat_input:
            return Namespace(self, {}, [])
        try:
            command, options = tree._get_app_command_options(data, self.guild_id)  # type: ignore
        except Exception:
            return Namespace(self, {}, [])
        return Namespace(self, data.get('resolved', {}) or {}, options)

    @utils.cached_slot_property('_cs_command')
    def command(self) -> Optional[Union[Command[Any, ..., Any], ContextMenu]]:
        """Optional[Union[:class:`app_commands.Command`, :class:`app_commands.ContextMenu`]]: The command being called from
        this interaction.

        If the interaction is not an application command related interaction or the command is not found in the client's
        attached tree then ``None`` is returned.
        """
        if self.type not in (InteractionType.application_command, InteractionType.autocomplete):
            return None

        tree = self._state._command_tree
        if tree is None:
            return None

        data = self.data or {}
        from .enums import AppCommandType as _AppCommandType

        if _AppCommandType.from_bisim(data.get('type')) is not _AppCommandType.chat_input:
            return tree._get_context_menu(data, self.guild_id)  # type: ignore
        try:
            command, _ = tree._get_app_command_options(data, self.guild_id)  # type: ignore
        except Exception:
            return None
        return command

    @property
    def command_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The ID of the command being called from this interaction."""
        if self.type not in (InteractionType.application_command, InteractionType.autocomplete):
            return None
        return utils._snowflake((self.data or {}).get('id'))

    @utils.cached_slot_property('_cs_response')
    def response(self) -> InteractionResponse[ClientT]:
        """:class:`InteractionResponse`: Returns an object responsible for handling responding to the interaction.

        A response can only be done once. If secondary messages need to be sent, consider using :attr:`followup`
        instead.
        """
        return InteractionResponse(self)

    @utils.cached_slot_property('_cs_followup')
    def followup(self) -> InteractionFollowup:
        """:class:`InteractionFollowup`: Returns the follow up webhook for follow up interactions."""
        return InteractionFollowup(self)

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: When the interaction was created."""
        return utils.snowflake_time(self.id)

    @property
    def expires_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: When the interaction expires."""
        return self.created_at + INTERACTION_LIFETIME

    @property
    def custom_id(self) -> Optional[str]:
        """Optional[:class:`str`]: The custom ID of the component or modal that triggered the interaction."""
        if self.type not in (InteractionType.component, InteractionType.modal_submit):
            return None
        return (self.data or {}).get('customId')

    def is_expired(self) -> bool:
        """:class:`bool`: Returns ``True`` if the interaction is expired."""
        return utils.utcnow() >= self.expires_at

    def is_guild_integration(self) -> bool:
        """:class:`bool`: Returns ``True`` if the interaction is a guild integration (always on Bisim)."""
        return True

    def is_user_integration(self) -> bool:
        """:class:`bool`: Always ``False``: Bisim has no user-installed apps."""
        return False

    async def original_response(self) -> InteractionMessage:
        """|coro|

        Fetches the original interaction response message associated with the interaction.

        If the interaction response was a newly created message (i.e. through :meth:`InteractionResponse.send_message`
        or :meth:`InteractionResponse.defer`, where ``thinking`` is ``True``) then this returns the message that was sent
        using that response. Otherwise, this would return the message that triggered the interaction.

        Repeated calls to this will return a cached value.

        Raises
        -------
        HTTPException
            Fetching the original response message failed.
        ClientException
            The channel for the message could not be resolved.
        NotFound
            The interaction response message does not exist.

        Returns
        --------
        InteractionMessage
            The original interaction response message.
        """
        if self._original_response is not None:
            return self._original_response

        data = await self._state.http.get_original_interaction_response(self.id, self.token)
        message = self._make_message(data)
        self._original_response = message
        return message

    async def _create_uploads(self, files: List[Dict[str, Any]]) -> Any:
        """Upload addresses for files of this interaction's answers, asked for with its token."""
        return await self._state.http.create_interaction_attachments(self.id, self.token, files)

    def _make_message(self, data: Dict[str, Any]) -> InteractionMessage:
        channel = self.channel
        if channel is None:
            channel_id = utils._snowflake(data.get('channelId')) or 0
            channel = PartialMessageable(state=self._state, id=channel_id, guild_id=self.guild_id)
        message = InteractionMessage(state=self._state, channel=channel, data=data)
        message._interaction_parent = self
        return message

    async def edit_original_response(
        self,
        *,
        content: Optional[str] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        attachments: Sequence[Union[Attachment, File]] = utils.MISSING,
        view: Optional[View] = utils.MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
        poll: Poll = utils.MISSING,
        suppress_embeds: bool = utils.MISSING,
    ) -> InteractionMessage:
        """|coro|

        Edits the original interaction response message.

        This is a lower level interface to :meth:`InteractionMessage.edit` in case
        you do not want to fetch the message and save an HTTP request.

        This method is also the only way to edit the original message if
        the message sent was ephemeral. After a deferral, the first edit fills
        in the "thinking" message.

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
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~bisim.ui.View`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.
        poll: :class:`Poll`
            Not supported on Bisim: a poll is sent as a new answer
            (:meth:`InteractionResponse.send_message` or a followup).
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message (``False`` brings them
            back). This is a Bisim addition.

        Raises
        -------
        HTTPException
            Editing the message failed.
        NotFound
            The interaction response message does not exist.
        Forbidden
            Edited a message that is not yours.
        TypeError
            You specified both ``embed`` and ``embeds``
        ValueError
            The length of ``embeds`` was invalid.
        NotSupported
            A poll was given.

        Returns
        --------
        :class:`InteractionMessage`
            The newly edited message.
        """
        if poll is not utils.MISSING and poll is not None:
            raise NotSupported('A poll in an edited interaction response')
        from .abc import _message_payload

        known = self._original_response.attachments if self._original_response is not None else None
        payload = await _message_payload(
            self._state,
            None,
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            view=view,
            suppress_embeds=suppress_embeds,
            allowed_mentions=allowed_mentions,
            editing=True,
            create_uploads=self._create_uploads,
            known_files=known,
        )
        data = await self._state.http.edit_original_interaction_response(self.id, self.token, payload)
        message = self._make_message(data)
        if view and not view.is_finished() and view.is_dispatchable():
            self._state.store_view(view, message.id)
        self._original_response = message
        return message

    async def delete_original_response(self) -> None:
        """|coro|

        Deletes the original interaction response message.

        This is a lower level interface to :meth:`InteractionMessage.delete` in case
        you do not want to fetch the message and save an HTTP request.

        Raises
        -------
        HTTPException
            Deleting the message failed.
        NotFound
            The interaction response message does not exist or has already been deleted.
        Forbidden
            Deleted a message that is not yours.
        """
        await self._state.http.delete_original_interaction_response(self.id, self.token)

    async def translate(self, string: Any, *, locale: Locale = utils.MISSING, data: Any = utils.MISSING) -> Optional[str]:
        """|coro|

        Translates a string using the set :class:`~bisim.app_commands.Translator`.

        Parameters
        ----------
        string: Union[:class:`str`, :class:`~bisim.app_commands.locale_str`]
            The string to translate.
        locale: :class:`Locale`
            The locale to use, this is handy if you want the translation
            for a specific locale. Defaults to the user's :attr:`.locale`.
        data: Any
            The extraneous data that is being translated.

        Returns
        --------
        Optional[:class:`str`]
            The translated string, or ``None`` if a translator was not set.
        """
        from .app_commands.translator import TranslationContext, TranslationContextLocation, locale_str

        tree = self._state._command_tree
        if not tree:
            return None
        translator = tree.translator
        if not translator:
            return None
        if not isinstance(string, locale_str):
            string = locale_str(string)
        if locale is utils.MISSING:
            locale = self.locale
        if data is utils.MISSING:
            data = self.command
        context = TranslationContext(location=TranslationContextLocation.other, data=data)
        return await translator.translate(string, locale=locale, context=context)


class InteractionCallbackActivityInstance:
    """Kept for compatibility: Bisim has no activities."""

    __slots__ = ('id',)

    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: str = data.get('id', '')


class InteractionCallbackResponse(Generic[ClientT]):
    """Represents an interaction response callback.

    Attributes
    -----------
    id: :class:`int`
        The interaction ID.
    type: :class:`InteractionResponseType`
        The interaction callback response type.
    resource: Optional[Union[:class:`InteractionMessage`, :class:`InteractionCallbackActivityInstance`]]
        The resource that the interaction response created, when Bisim returned it.
    message_id: Optional[:class:`int`]
        The message ID of the resource. Only available if the resource is a message.
    """

    __slots__ = ('_state', '_parent', 'type', 'id', '_thinking', '_ephemeral', 'message_id', 'resource')

    def __init__(
        self,
        *,
        data: Optional[Dict[str, Any]],
        parent: Interaction[ClientT],
        state: ConnectionState,
        type: InteractionResponseType,
        thinking: bool = False,
        ephemeral: bool = False,
    ) -> None:
        self._state: ConnectionState = state
        self._parent: Interaction[ClientT] = parent
        self.type: InteractionResponseType = type
        self.id: int = parent.id
        self._thinking: bool = thinking
        self._ephemeral: bool = ephemeral
        self.message_id: Optional[int] = None
        self.resource: Optional[Union[InteractionMessage, InteractionCallbackActivityInstance]] = None
        if isinstance(data, dict) and data.get('id'):
            message = parent._make_message(data)
            self.resource = message
            self.message_id = message.id
            self._ephemeral = self._ephemeral or message.flags.ephemeral

    def __repr__(self) -> str:
        return f'<InteractionCallbackResponse id={self.id} type={self.type!r}>'

    def is_thinking(self) -> bool:
        """:class:`bool`: Whether the response was a thinking defer."""
        return self._thinking

    def is_ephemeral(self) -> bool:
        """:class:`bool`: Whether the response was ephemeral."""
        return self._ephemeral


class InteractionResponse(Generic[ClientT]):
    """Represents a Bisim interaction response.

    This type can be accessed through :attr:`Interaction.response`.
    """

    __slots__: Tuple[str, ...] = ('_response_type', '_parent')

    def __init__(self, parent: Interaction[ClientT]):
        self._parent: Interaction[ClientT] = parent
        self._response_type: Optional[InteractionResponseType] = None

    def is_done(self) -> bool:
        """:class:`bool`: Indicates whether an interaction response has been done before.

        An interaction can only be responded to once.
        """
        return self._response_type is not None

    @property
    def type(self) -> Optional[InteractionResponseType]:
        """:class:`InteractionResponseType`: The type of response that was sent, ``None`` if response is not done."""
        return self._response_type

    async def _callback(self, type: InteractionResponseType, data: Optional[Dict[str, Any]] = None) -> Any:
        parent = self._parent
        hook = parent._state._http_interaction_responses.get(parent.id)
        if hook is not None and not hook.done():
            # An Interactions URL bot answers in the HTTP response body.
            payload: Dict[str, Any] = {'type': type.value}
            if data is not None:
                payload['data'] = data
            hook.set_result(payload)
            return None
        return await parent._state.http.create_interaction_response(parent.id, parent.token, type=type.value, data=data)

    async def defer(self, *, ephemeral: bool = False, thinking: bool = False) -> Optional[InteractionCallbackResponse[ClientT]]:
        """|coro|

        Defers the interaction response.

        This is typically used when the interaction is acknowledged
        and a secondary action will be done later.

        This is only supported with the following interaction types:

        - :attr:`InteractionType.application_command`
        - :attr:`InteractionType.component`
        - :attr:`InteractionType.modal_submit`

        Parameters
        -----------
        ephemeral: :class:`bool`
            Indicates whether the deferred message will eventually be ephemeral.
            This only applies to :attr:`InteractionType.application_command` interactions, or if ``thinking`` is ``True``.
        thinking: :class:`bool`
            Indicates whether the deferred type should be :attr:`InteractionResponseType.deferred_channel_message`
            instead of the default :attr:`InteractionResponseType.deferred_message_update` if both are valid.
            In UI terms, this is represented as if the bot is thinking of a response. It is your responsibility to
            eventually send a followup message via :attr:`Interaction.followup` to make this thinking state go away.
            Application commands (AKA Slash commands) cannot use :attr:`InteractionResponseType.deferred_message_update`.

        Raises
        -------
        HTTPException
            Deferring the interaction failed.
        InteractionResponded
            This interaction has already been responded to before.

        Returns
        -------
        Optional[:class:`InteractionCallbackResponse`]
            The interaction callback resource, or ``None``.
        """
        if self._response_type:
            raise InteractionResponded(self._parent)

        defer_type: Optional[InteractionResponseType] = None
        data: Optional[Dict[str, Any]] = None
        parent = self._parent
        if parent.type is InteractionType.component or parent.type is InteractionType.modal_submit:
            if thinking:
                defer_type = InteractionResponseType.deferred_channel_message
                if ephemeral:
                    data = {'flags': 64}
            else:
                defer_type = InteractionResponseType.deferred_message_update
        elif parent.type is InteractionType.application_command:
            defer_type = InteractionResponseType.deferred_channel_message
            if ephemeral:
                data = {'flags': 64}

        if defer_type is None:
            return None

        response = await self._callback(defer_type, data)
        self._response_type = defer_type
        return InteractionCallbackResponse(
            data=response if isinstance(response, dict) else None,
            parent=parent,
            state=parent._state,
            type=defer_type,
            thinking=thinking or defer_type is InteractionResponseType.deferred_channel_message,
            ephemeral=ephemeral,
        )

    async def pong(self) -> None:
        """|coro|

        Pongs the ping interaction.

        This should rarely be used.

        Raises
        -------
        HTTPException
            Ponging the interaction failed.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._response_type:
            raise InteractionResponded(self._parent)

        parent = self._parent
        if parent.type is InteractionType.ping:
            await self._callback(InteractionResponseType.pong)
            self._response_type = InteractionResponseType.pong

    async def send_message(
        self,
        content: Optional[Any] = None,
        *,
        embed: Embed = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        file: File = utils.MISSING,
        files: Sequence[File] = utils.MISSING,
        view: View = utils.MISSING,
        tts: bool = False,
        ephemeral: bool = False,
        allowed_mentions: AllowedMentions = utils.MISSING,
        suppress_embeds: bool = False,
        silent: bool = False,
        delete_after: Optional[float] = None,
        poll: Poll = utils.MISSING,
    ) -> InteractionCallbackResponse[ClientT]:
        """|coro|

        Responds to this interaction by sending a message.

        Parameters
        -----------
        content: Optional[:class:`str`]
            The content of the message to send.
        embeds: List[:class:`Embed`]
            A list of embeds to send with the content. Maximum of 10. This cannot
            be mixed with the ``embed`` parameter.
        embed: :class:`Embed`
            The rich embed for the content to send. This cannot be mixed with
            ``embeds`` parameter.
        file: :class:`~bisim.File`
            The file to upload.
        files: List[:class:`~bisim.File`]
            A list of files to upload. Must be a maximum of 10.
        tts: :class:`bool`
            Accepted for compatibility.
        view: :class:`bisim.ui.View`
            The view to send with the message.
        ephemeral: :class:`bool`
            Indicates if the message should only be visible to the user who started the interaction.
            If a view is sent with an ephemeral message and it has no timeout set then the timeout
            is set to 15 minutes.
        allowed_mentions: :class:`~bisim.AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.
        silent: :class:`bool`
            Whether to suppress push and desktop notifications for the message.
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent. If the deletion fails,
            then it is silently ignored.
        poll: :class:`~bisim.Poll`
            The poll to send with this message. Bisim sends a poll on its own (no
            text, embeds, files or view with it) and never in an ephemeral answer.

        Raises
        -------
        HTTPException
            Sending the message failed.
        TypeError
            You specified both ``embed`` and ``embeds``.
        ValueError
            The length of ``embeds`` was invalid.
        InteractionResponded
            This interaction has already been responded to before.

        Returns
        -------
        :class:`InteractionCallbackResponse`
            The interaction callback data.
        """
        if self._response_type:
            raise InteractionResponded(self._parent)

        from .abc import _message_payload

        parent = self._parent
        payload = await _message_payload(
            parent._state,
            None,
            content=content if content is not None else utils.MISSING,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            view=view,
            poll=poll,
            tts=tts,
            silent=silent,
            suppress_embeds=suppress_embeds,
            ephemeral=ephemeral,
            allowed_mentions=allowed_mentions,
            create_uploads=parent._create_uploads,
        )
        payload.pop('nonce', None)

        response = await self._callback(InteractionResponseType.channel_message, payload)
        self._response_type = InteractionResponseType.channel_message

        callback = InteractionCallbackResponse(
            data=response if isinstance(response, dict) else None,
            parent=parent,
            state=parent._state,
            type=InteractionResponseType.channel_message,
            ephemeral=ephemeral,
        )
        if isinstance(callback.resource, InteractionMessage):
            parent._original_response = callback.resource
            if poll is not utils.MISSING and poll is not None:
                poll._update_from_message(callback.resource)

        if view is not utils.MISSING and not view.is_finished():
            if ephemeral and view.timeout is None:
                view.timeout = 15 * 60.0
            if view.is_dispatchable():
                parent._state.store_view(view, callback.message_id)

        if delete_after is not None:

            async def inner_call(delay: float = delete_after) -> None:
                await asyncio.sleep(delay)
                try:
                    await parent.delete_original_response()
                except HTTPException:
                    pass

            asyncio.create_task(inner_call())

        return callback

    async def edit_message(
        self,
        *,
        content: Optional[Any] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        attachments: Sequence[Union[Attachment, File]] = utils.MISSING,
        view: Optional[View] = utils.MISSING,
        allowed_mentions: Optional[AllowedMentions] = utils.MISSING,
        delete_after: Optional[float] = None,
        suppress_embeds: bool = utils.MISSING,
    ) -> Optional[InteractionCallbackResponse[ClientT]]:
        """|coro|

        Responds to this interaction by editing the original message of
        a component or modal interaction.

        Parameters
        -----------
        content: Optional[:class:`str`]
            The new content to replace the message with. ``None`` removes the content.
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
            the view is removed.
        allowed_mentions: Optional[:class:`~bisim.AllowedMentions`]
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.

        Raises
        -------
        HTTPException
            Editing the message failed.
        TypeError
            You specified both ``embed`` and ``embeds``.
        InteractionResponded
            This interaction has already been responded to before.

        Returns
        -------
        Optional[:class:`InteractionCallbackResponse`]
            The interaction callback data, or ``None`` if editing the message was not possible.
        """
        if self._response_type:
            raise InteractionResponded(self._parent)

        parent = self._parent
        msg = parent.message
        state = parent._state
        if msg is not None:
            message_id = msg.id
        else:
            message_id = None

        if parent.type not in (InteractionType.component, InteractionType.modal_submit):
            return None

        from .abc import _message_payload

        payload = await _message_payload(
            state,
            None,
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            view=view,
            suppress_embeds=suppress_embeds,
            allowed_mentions=allowed_mentions,
            editing=True,
            create_uploads=parent._create_uploads,
            known_files=msg.attachments if msg is not None else None,
        )

        response = await self._callback(InteractionResponseType.message_update, payload)
        self._response_type = InteractionResponseType.message_update

        if view and not view.is_finished() and view.is_dispatchable():
            state.store_view(view, message_id)

        if delete_after is not None:

            async def inner_call(delay: float = delete_after) -> None:
                await asyncio.sleep(delay)
                try:
                    await parent.delete_original_response()
                except HTTPException:
                    pass

            asyncio.create_task(inner_call())

        return InteractionCallbackResponse(
            data=response if isinstance(response, dict) else None,
            parent=parent,
            state=state,
            type=InteractionResponseType.message_update,
        )

    async def send_modal(self, modal: Modal, /) -> InteractionCallbackResponse[ClientT]:
        """|coro|

        Responds to this interaction by sending a modal.

        Parameters
        -----------
        modal: :class:`~bisim.ui.Modal`
            The modal to send.

        Raises
        -------
        HTTPException
            Sending the modal failed.
        InteractionResponded
            This interaction has already been responded to before.

        Returns
        -------
        :class:`InteractionCallbackResponse`
            The interaction callback data.
        """
        if self._response_type:
            raise InteractionResponded(self._parent)

        parent = self._parent
        response = await self._callback(InteractionResponseType.modal, modal.to_dict())
        if not modal.is_finished():
            parent._state.store_view(modal)
        self._response_type = InteractionResponseType.modal

        return InteractionCallbackResponse(
            data=response if isinstance(response, dict) else None,
            parent=parent,
            state=parent._state,
            type=InteractionResponseType.modal,
        )

    async def autocomplete(self, choices: Sequence[Choice[Any]]) -> None:
        """|coro|

        Responds to this interaction by giving the user the choices they can use.

        Parameters
        -----------
        choices: List[:class:`~bisim.app_commands.Choice`]
            The list of new choices as the user is typing.

        Raises
        -------
        HTTPException
            Sending the choices failed.
        ValueError
            This interaction cannot respond with autocomplete.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._response_type:
            raise InteractionResponded(self._parent)

        translator = self._parent._state._translator
        if translator is not None:
            user_locale = self._parent.locale
            payload: Dict[str, Any] = {
                'choices': [await option.get_translated_payload_for_locale(translator, user_locale) for option in choices],
            }
        else:
            payload = {'choices': [option.to_dict() for option in choices]}

        parent = self._parent
        if parent.type is not InteractionType.autocomplete:
            raise ValueError('cannot respond to this interaction with autocomplete.')

        await self._callback(InteractionResponseType.autocomplete_result, payload)
        self._response_type = InteractionResponseType.autocomplete_result

    async def launch_activity(self) -> InteractionCallbackResponse[ClientT]:
        """|coro|

        Not supported on Bisim (no activities).
        """
        raise NotSupported('Activities')

    async def require_premium(self) -> None:
        """|coro|

        Not supported on Bisim (no premium).
        """
        raise NotSupported('Premium interactions')


class InteractionMessage(Message):
    """Represents the original interaction response message.

    This allows you to edit or delete the message associated with
    the interaction response. To retrieve this object see :meth:`Interaction.original_response`.

    This inherits from :class:`bisim.Message` with changes to
    :meth:`edit` and :meth:`delete` to work.
    """

    __slots__ = ('_interaction_parent',)

    async def edit(
        self,
        *,
        content: Optional[str] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        attachments: Sequence[Union[Attachment, File]] = utils.MISSING,
        view: Optional[View] = utils.MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
        delete_after: Optional[float] = None,
        poll: Poll = utils.MISSING,
        **kwargs: Any,
    ) -> InteractionMessage:
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
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~bisim.ui.View`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent. If the deletion fails,
            then it is silently ignored.
        poll: :class:`Poll`
            Not supported on Bisim: a poll cannot be added in an edit.

        Raises
        -------
        HTTPException
            Editing the message failed.
        Forbidden
            Edited a message that is not yours.
        TypeError
            You specified both ``embed`` and ``embeds``
        ValueError
            The length of ``embeds`` was invalid.

        Returns
        ---------
        :class:`InteractionMessage`
            The newly edited message.
        """
        res = await self._interaction_parent.edit_original_response(
            content=content,
            embeds=embeds,
            embed=embed,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
            poll=poll,
            # Message.edit's spelling of the suppress embeds flag.
            suppress_embeds=kwargs.get('suppress', utils.MISSING),
        )
        if delete_after is not None:
            await self.delete(delay=delete_after)
        return res

    async def add_files(self, *files: File) -> InteractionMessage:
        r"""|coro|

        Adds new files to the end of the message attachments.

        Parameters
        -----------
        \*files: :class:`File`
            New files to add to the message.

        Raises
        -------
        HTTPException
            Editing the message failed.
        Forbidden
            Tried to edit a message that isn't yours.

        Returns
        --------
        :class:`InteractionMessage`
            The newly edited message.
        """
        return await self.edit(attachments=[*self.attachments, *files])

    async def remove_attachments(self, *attachments: Attachment) -> InteractionMessage:
        r"""|coro|

        Removes attachments from the message.

        Parameters
        -----------
        \*attachments: :class:`Attachment`
            Attachments to remove from the message.

        Raises
        -------
        HTTPException
            Editing the message failed.
        Forbidden
            Tried to edit a message that isn't yours.

        Returns
        --------
        :class:`InteractionMessage`
            The newly edited message.
        """
        return await self.edit(attachments=[a for a in self.attachments if a not in attachments])

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
                    await self._interaction_parent.delete_original_response()
                except HTTPException:
                    pass

            asyncio.create_task(inner_call())
        else:
            await self._interaction_parent.delete_original_response()


class InteractionFollowup:
    """Sends, edits and deletes an interaction's followup messages.

    This is what :attr:`Interaction.followup` returns. It behaves like the
    webhook discord.py gives there: :meth:`send` posts a further message
    within the interaction's 15 minutes.
    """

    __slots__ = ('_interaction',)

    def __init__(self, interaction: Interaction[Any]) -> None:
        self._interaction = interaction

    def __repr__(self) -> str:
        return f'<InteractionFollowup interaction_id={self._interaction.id}>'

    @property
    def id(self) -> int:
        """:class:`int`: The application ID (as a webhook, the followup carries the application's ID)."""
        return self._interaction.application_id

    @property
    def token(self) -> str:
        """:class:`str`: The interaction token."""
        return self._interaction.token

    def _make_message(self, data: Dict[str, Any]) -> WebhookMessage:
        interaction = self._interaction
        channel = interaction.channel
        if channel is None:
            channel_id = utils._snowflake(data.get('channelId')) or 0
            channel = PartialMessageable(state=interaction._state, id=channel_id, guild_id=interaction.guild_id)
        message = WebhookMessage(state=interaction._state, channel=channel, data=data)
        message._webhook = self  # type: ignore
        return message

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
        view: View = utils.MISSING,
        thread: Any = utils.MISSING,
        thread_name: str = utils.MISSING,
        wait: bool = True,
        suppress_embeds: bool = False,
        silent: bool = False,
        applied_tags: Any = utils.MISSING,
        poll: Poll = utils.MISSING,
    ) -> WebhookMessage:
        """|coro|

        Sends a followup message for the interaction.

        Parameters
        ------------
        content: :class:`str`
            The content of the message to send.
        ephemeral: :class:`bool`
            Indicates if the message should only be visible to the user who started the interaction.
        embed: :class:`Embed`
            The rich embed for the content to send. This cannot be mixed with
            ``embeds`` parameter.
        embeds: List[:class:`Embed`]
            A list of embeds to send with the content. Maximum of 10. This cannot
            be mixed with the ``embed`` parameter.
        view: :class:`bisim.ui.View`
            The view to send with the message.
        username: :class:`str`
            Accepted for compatibility (the message shows the bot).
        avatar_url: :class:`str`
            Accepted for compatibility.
        tts: :class:`bool`
            Accepted for compatibility.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.
        silent: :class:`bool`
            Whether to suppress push and desktop notifications for the message.
        wait: :class:`bool`
            Accepted for compatibility; the message is always returned.
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.
        thread: :class:`~bisim.abc.Snowflake`
            Not supported on Bisim (no threads).
        poll: :class:`Poll`
            The poll to send with this message. Bisim sends a poll on its own and
            never in an ephemeral message. After :meth:`InteractionResponse.defer`,
            the first followup fills the "thinking" message, which cannot become a
            poll: answer the thinking message first (with
            :meth:`Interaction.edit_original_response`), then send the poll.

        Raises
        --------
        HTTPException
            Sending the message failed.
        NotFound
            The interaction expired or was not found.
        TypeError
            You specified both ``embed`` and ``embeds``.
        ValueError
            The length of ``embeds`` was invalid.

        Returns
        ---------
        :class:`WebhookMessage`
            The message that was sent.
        """
        if thread is not utils.MISSING or thread_name is not utils.MISSING or applied_tags is not utils.MISSING:
            raise NotSupported('Threads')

        from .abc import _message_payload

        interaction = self._interaction
        state = interaction._state
        payload = await _message_payload(
            state,
            None,
            content=content,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            view=view,
            poll=poll,
            silent=silent,
            suppress_embeds=suppress_embeds,
            ephemeral=ephemeral,
            tts=tts,
            allowed_mentions=allowed_mentions,
            create_uploads=interaction._create_uploads,
        )
        payload.pop('nonce', None)
        data = await state.http.create_followup_message(interaction.id, interaction.token, payload)
        if not isinstance(data, dict) or not data.get('id'):
            # Bisim did not return the message; give back what is known.
            data = {
                'id': str(utils.time_snowflake(utils.utcnow())),
                'channelId': str(interaction.channel_id or 0),
                'content': payload.get('content') or '',
                'author': state.user._to_minimal_user_json() if state.user else {},
                'ephemeral': ephemeral,
            }
        message = self._make_message(data)
        if view is not utils.MISSING and view is not None and not view.is_finished() and view.is_dispatchable():
            state.store_view(view, message.id)
        if poll is not utils.MISSING and poll is not None:
            poll._update_from_message(message)
        return message

    async def fetch_message(self, id: int, /, *, thread: Any = utils.MISSING) -> WebhookMessage:
        """|coro|

        Retrieves a followup message sent for this interaction.

        Parameters
        ------------
        id: :class:`int`
            The message ID to look for.

        Raises
        --------
        NotFound
            The specified message was not found.
        HTTPException
            Retrieving the message failed.

        Returns
        --------
        :class:`WebhookMessage`
            The message asked for.
        """
        interaction = self._interaction
        data = await interaction._state.http.get_followup_message(interaction.id, interaction.token, id)
        return self._make_message(data)

    async def edit_message(
        self,
        message_id: int,
        *,
        content: Optional[str] = utils.MISSING,
        embeds: Sequence[Embed] = utils.MISSING,
        embed: Optional[Embed] = utils.MISSING,
        attachments: Sequence[Any] = utils.MISSING,
        view: Optional[View] = utils.MISSING,
        allowed_mentions: Optional[AllowedMentions] = None,
        thread: Any = utils.MISSING,
        suppress_embeds: bool = utils.MISSING,
    ) -> WebhookMessage:
        """|coro|

        Edits a followup message sent for this interaction.

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
        view: Optional[:class:`~bisim.ui.View`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.
        attachments: List[Union[:class:`Attachment`, :class:`File`]]
            A list of attachments to keep in the message as well as new files to upload. If ``[]`` is passed
            then all attachments are removed.

            .. note::

                New files will always appear after current attachments.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message (``False`` brings them
            back). This is a Bisim addition.

        Raises
        -------
        HTTPException
            Editing the message failed.
        Forbidden
            Edited a message that is not yours.

        Returns
        --------
        :class:`WebhookMessage`
            The newly edited message.
        """
        from .abc import _message_payload

        interaction = self._interaction
        state = interaction._state
        payload = await _message_payload(
            state,
            None,
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            view=view,
            suppress_embeds=suppress_embeds,
            allowed_mentions=allowed_mentions,
            editing=True,
            create_uploads=interaction._create_uploads,
        )
        data = await state.http.edit_followup_message(interaction.id, interaction.token, message_id, payload)
        message = self._make_message(data)
        if view and not view.is_finished() and view.is_dispatchable():
            state.store_view(view, message.id)
        return message

    async def delete_message(self, message_id: int, /, *, thread: Any = utils.MISSING) -> None:
        """|coro|

        Deletes a followup message sent for this interaction.

        Parameters
        ------------
        message_id: :class:`int`
            The message ID to delete.

        Raises
        -------
        HTTPException
            Deleting the message failed.
        Forbidden
            Deleted a message that is not yours.
        """
        interaction = self._interaction
        await interaction._state.http.delete_followup_message(interaction.id, interaction.token, message_id)

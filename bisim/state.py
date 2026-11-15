"""The connection state: caches, the bootstrap, and one parser per Bisim event.

Bisim's gateway has no READY. After the socket opens the library reads the
bot's servers over REST (``GET /guilds``, then ``GET /guilds/:id`` for each,
which also lets the gateway accept the subscription), subscribes to each
with op 4 and, once they are in, dispatches :func:`on_ready`.
"""

from __future__ import annotations

import asyncio
import copy
import datetime
import inspect
import logging
import weakref
from collections import deque
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Deque,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)

from . import utils
from .activity import BaseActivity, CustomActivity
from .audit_logs import AuditLogEntry
from .automod import AutoModAction, AutoModRule
from .channel import (
    DMChannel,
    GroupChannel,
    PartialMessageable,
    TextChannel,
    VoiceChannel,
    _guild_channel_factory,
    _private_channel_factory,
)
from .emoji import Emoji
from .enums import ChannelType, InteractionType, Status, try_enum
from .errors import Forbidden, HTTPException, NotFound
from .flags import Intents, MemberCacheFlags
from .guild import Guild
from .interactions import Interaction
from .invite import Invite
from .member import Member
from .message import Message
from .partial_emoji import PartialEmoji
from .raw_models import (
    RawBulkMessageDeleteEvent,
    RawMemberRemoveEvent,
    RawMessageDeleteEvent,
    RawMessageUpdateEvent,
    RawPollVoteActionEvent,
    RawPresenceUpdateEvent,
    RawReactionActionEvent,
    RawReactionClearEmojiEvent,
    RawReactionClearEvent,
    RawTypingEvent,
)
from .role import Role
from .soundboard import SoundboardSound
from .sticker import GuildSticker
from .ui.modal import _modal_fields
from .ui.view import View, ViewStore
from .user import ClientUser, User
from .voice_client import VoiceProtocol

if TYPE_CHECKING:
    from .abc import PrivateChannel
    from .app_commands import CommandTree, Translator
    from .client import Client
    from .gateway import BisimWebSocket
    from .http import HTTPClient

_log = logging.getLogger(__name__)

T = TypeVar('T')


def _channel_signature(channel: Any) -> Tuple[Any, ...]:
    return (
        channel.name,
        channel.position,
        channel.category_id,
        getattr(channel, 'topic', None),
        getattr(channel, 'nsfw', None),
        getattr(channel, 'slowmode_delay', None),
        getattr(channel, '_permissions_synced', None),
        getattr(channel, '_my_permissions', None),
        getattr(channel, '_is_private', None),
    )


def _role_signature(role: Role) -> Tuple[Any, ...]:
    return (role.name, role._permissions, role._colour, role.position, role.hoist, role.mentionable, role.managed)


class ConnectionState:
    """Holds the caches and turns gateway events into library events."""

    if TYPE_CHECKING:
        _get_websocket: Callable[..., Optional[BisimWebSocket]]
        _get_client: Callable[..., Client]
        _parsers: Dict[str, Callable[[Any], None]]

    def __init__(
        self,
        *,
        dispatch: Callable[..., Any],
        handlers: Dict[str, Callable[..., Any]],
        hooks: Dict[str, Callable[..., Coroutine[Any, Any, Any]]],
        http: HTTPClient,
        **options: Any,
    ) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.http: HTTPClient = http
        self.max_messages: Optional[int] = options.get('max_messages', 1000)
        if self.max_messages is not None and self.max_messages <= 0:
            self.max_messages = 1000

        self.dispatch: Callable[..., Any] = dispatch
        self.handlers: Dict[str, Callable[..., Any]] = handlers
        self.hooks: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = hooks
        self.shard_count: Optional[int] = None
        self.application_id: Optional[int] = utils._get_as_snowflake(options, 'application_id')
        self.heartbeat_timeout: float = options.get('heartbeat_timeout', 60.0)
        self.guild_ready_timeout: float = options.get('guild_ready_timeout', 2.0)
        if self.guild_ready_timeout < 0:
            raise ValueError('guild_ready_timeout cannot be negative')

        self.allowed_mentions: Any = options.get('allowed_mentions')

        activity = options.get('activity', None)
        if activity is not None and not isinstance(activity, BaseActivity):
            raise TypeError('activity parameter must derive from BaseActivity.')
        self._activity: Optional[BaseActivity] = activity

        status = options.get('status', None)
        self._status: Optional[str] = None
        if status is not None:
            self._status = 'invisible' if status is Status.offline else str(status)

        intents = options.get('intents', None)
        if intents is not None and intents is not utils.MISSING and not isinstance(intents, Intents):
            raise TypeError(f'intents parameter must be Intent not {type(intents)!r}')
        self._intents: Intents = intents if isinstance(intents, Intents) else Intents.default()

        # Bisim refuses the full member list without the members intent, as Discord refuses to chunk.
        self._chunk_guilds: bool = options.get('chunk_guilds_at_startup', self._intents.members)
        if not self._intents.members and self._chunk_guilds:
            raise ValueError('Intents.members must be enabled to chunk guilds at startup.')

        cache_flags = options.get('member_cache_flags', None)
        self.member_cache_flags: MemberCacheFlags = cache_flags if cache_flags is not None else MemberCacheFlags.all()

        self._enable_raw_presences: bool = options.get('enable_raw_presences', False)
        self._command_tree: Optional[CommandTree] = None
        self._translator: Optional[Translator] = None
        self._upload_limit: Optional[int] = None
        self._typing_via_gateway: bool = False
        self._http_interaction_responses: Dict[int, asyncio.Future[Dict[str, Any]]] = {}
        self._bootstrap_task: Optional[asyncio.Task[None]] = None
        self._background: Set[asyncio.Task[Any]] = set()

        self.parsers: Dict[str, Callable[[Any], None]] = {}
        for attr, func in inspect.getmembers(self):
            if attr.startswith('parse_'):
                self.parsers[attr[6:].upper()] = func

        self.clear()

    # ------------------------------------------------------------------
    # Cache basics
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self.user: Optional[ClientUser] = None
        self._users: weakref.WeakValueDictionary[int, User] = weakref.WeakValueDictionary()
        self._emojis: Dict[int, Emoji] = {}
        self._stickers: Dict[int, GuildSticker] = {}
        self._guilds: Dict[int, Guild] = {}
        self._view_store: ViewStore = ViewStore(self)
        self._private_channels: Dict[int, Any] = {}
        self._private_channels_by_user: Dict[int, DMChannel] = {}
        self._subscribe_waiters: Dict[int, asyncio.Future[bool]] = {}
        self._voice_clients: Dict[int, VoiceProtocol] = {}
        # Presence snapshots that arrive before a server's members are loaded.
        self._pending_presences: Dict[int, List[Dict[str, Any]]] = {}
        # Channels CHANNEL_CREATE added, per server: the GUILD_RESYNC that follows must not report them again.
        self._fresh_channels: Dict[int, Set[int]] = {}
        self._ready_state_done: bool = False
        if self.max_messages is not None:
            self._messages: Optional[Deque[Message]] = deque(maxlen=self.max_messages)
        else:
            self._messages = None

    def call_handlers(self, key: str, *args: Any, **kwargs: Any) -> None:
        try:
            func = self.handlers[key]
        except KeyError:
            pass
        else:
            func(*args, **kwargs)

    async def call_hooks(self, key: str, *args: Any, **kwargs: Any) -> None:
        try:
            coro = self.hooks[key]
        except KeyError:
            pass
        else:
            await coro(*args, **kwargs)

    @property
    def self_id(self) -> Optional[int]:
        u = self.user
        return u.id if u else None

    @property
    def intents(self) -> Intents:
        ret = Intents.none()
        ret.value = self._intents.value
        return ret

    @property
    def guilds(self) -> Sequence[Guild]:
        return utils.SequenceProxy(self._guilds.values())

    @property
    def emojis(self) -> Sequence[Emoji]:
        return utils.SequenceProxy(self._emojis.values())

    @property
    def stickers(self) -> Sequence[GuildSticker]:
        return utils.SequenceProxy(self._stickers.values())

    @property
    def private_channels(self) -> Sequence[Any]:
        return utils.SequenceProxy(self._private_channels.values())

    @property
    def persistent_views(self) -> Sequence[View]:
        return self._view_store.persistent_views

    @property
    def voice_clients(self) -> List[VoiceProtocol]:
        return list(self._voice_clients.values())

    def _get_voice_client(self, guild_id: Optional[int]) -> Optional[VoiceProtocol]:
        return self._voice_clients.get(guild_id)  # type: ignore

    def _add_voice_client(self, guild_id: int, voice: VoiceProtocol) -> None:
        self._voice_clients[guild_id] = voice

    def _remove_voice_client(self, guild_id: int, voice: Optional[VoiceProtocol] = None) -> None:
        if voice is not None and self._voice_clients.get(guild_id) is not voice:
            return
        self._voice_clients.pop(guild_id, None)

    async def close_voice_clients(self) -> None:
        for voice in self.voice_clients:
            try:
                await voice.disconnect(force=True)
            except Exception:
                # if an error happens during disconnects, disregard it.
                pass

    def _spawn(self, coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(coro, name=name)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        task.add_done_callback(self._log_task_exception)
        return task

    @staticmethod
    def _log_task_exception(task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _log.error('Background task %s failed', task.get_name(), exc_info=exc)

    def store_user(self, data: Dict[str, Any], *, cache: bool = True) -> User:
        user_id = int(data.get('id') or data.get('userId'))
        try:
            user = self._users[user_id]
        except KeyError:
            user = User(state=self, data=data)
            if cache and user.discriminator is not None:
                self._users[user_id] = user
            return user
        else:
            if isinstance(data, dict) and data.get('username'):
                user._patch(data)
            return user

    def create_user(self, data: Dict[str, Any]) -> User:
        return User(state=self, data=data)

    def get_user(self, id: Optional[int]) -> Optional[User]:
        if id is None:
            return None
        return self._users.get(id)

    def store_emoji(self, guild: Guild, data: Dict[str, Any]) -> Emoji:
        emoji = Emoji(guild=guild, state=self, data=data)
        self._emojis[emoji.id] = emoji
        return emoji

    def store_view(self, view: View, message_id: Optional[int] = None, interaction_id: Optional[int] = None) -> None:
        self._view_store.add_view(view, message_id)

    def prevent_view_updates_for(self, message_id: int) -> Optional[View]:
        return self._view_store.remove_message_tracking(message_id)

    def _get_guild(self, guild_id: Optional[int]) -> Optional[Guild]:
        if guild_id is None:
            return None
        return self._guilds.get(guild_id)

    def _add_guild(self, guild: Guild) -> None:
        self._guilds[guild.id] = guild
        for emoji in guild.emojis:
            self._emojis[emoji.id] = emoji
        for sticker in guild.stickers:
            self._stickers[sticker.id] = sticker

    def _remove_guild(self, guild: Guild) -> None:
        self._guilds.pop(guild.id, None)
        for emoji in guild.emojis:
            self._emojis.pop(emoji.id, None)
        for sticker in guild.stickers:
            self._stickers.pop(sticker.id, None)
        del guild

    def get_emoji(self, emoji_id: Optional[int]) -> Optional[Emoji]:
        if emoji_id is None:
            return None
        return self._emojis.get(emoji_id)

    def _get_sticker(self, sticker_id: Optional[int]) -> Optional[GuildSticker]:
        if sticker_id is None:
            return None
        return self._stickers.get(sticker_id)

    def _get_private_channel(self, channel_id: Optional[int]) -> Optional[Any]:
        if channel_id is None:
            return None
        return self._private_channels.get(channel_id)

    def _get_private_channel_by_user(self, user_id: Optional[int]) -> Optional[DMChannel]:
        if user_id is None:
            return None
        return self._private_channels_by_user.get(user_id)

    def _add_private_channel(self, channel: Any) -> None:
        self._private_channels[channel.id] = channel
        if isinstance(channel, DMChannel) and channel.recipient is not None:
            self._private_channels_by_user[channel.recipient.id] = channel

    def add_dm_channel(self, data: Dict[str, Any]) -> DMChannel:
        channel_id = int(data['id'])
        existing = self._private_channels.get(channel_id)
        if isinstance(existing, DMChannel):
            existing._update(data)
            self._add_private_channel(existing)
            return existing
        channel = DMChannel(me=self.user, state=self, data=data)  # type: ignore
        self._add_private_channel(channel)
        return channel

    def _remove_private_channel(self, channel: Any) -> None:
        self._private_channels.pop(channel.id, None)
        if isinstance(channel, DMChannel):
            recipient = channel.recipient
            if recipient is not None:
                self._private_channels_by_user.pop(recipient.id, None)

    def _get_message(self, msg_id: Optional[int]) -> Optional[Message]:
        if msg_id is None or not self._messages:
            return None
        for message in reversed(self._messages):
            if message.id == msg_id:
                return message
        return None

    def get_channel(self, id: Optional[int]) -> Optional[Any]:
        if id is None:
            return None
        pm = self._get_private_channel(id)
        if pm is not None:
            return pm
        for guild in self._guilds.values():
            channel = guild._resolve_channel(id)
            if channel is not None:
                return channel
        return None

    def create_message(self, *, channel: Any, data: Dict[str, Any]) -> Message:
        return Message(state=self, channel=channel, data=data)

    def _resolve_reaction_emoji(self, value: str) -> Union[str, Emoji, PartialEmoji]:
        emoji = PartialEmoji.from_str(value or '')
        if emoji.id is None:
            return emoji.name
        return self._emojis.get(emoji.id) or PartialEmoji.with_state(self, name=emoji.name, animated=emoji.animated, id=emoji.id)

    def _upgrade_partial_emoji(self, emoji: PartialEmoji) -> Union[Emoji, PartialEmoji, str]:
        emoji_id = emoji.id
        if not emoji_id:
            return emoji.name
        try:
            return self._emojis[emoji_id]
        except KeyError:
            return emoji

    def _get_reaction_user(self, channel: Any, user_id: int) -> Optional[Union[User, Member]]:
        guild = getattr(channel, 'guild', None)
        if guild is not None:
            member = guild.get_member(user_id)
            if member is not None:
                return member
        return self.get_user(user_id)

    def _channel_for(self, channel_id: Optional[int], guild_id: Optional[int], author: Optional[Dict[str, Any]] = None) -> Any:
        """Finds the channel an event happened in, making a stand in when it is not cached."""
        if channel_id is None:
            return None
        if guild_id is not None:
            guild = self._get_guild(guild_id)
            if guild is not None:
                channel = guild.get_channel(channel_id)
                if channel is not None:
                    return channel
            return PartialMessageable(state=self, id=channel_id, guild_id=guild_id, type=ChannelType.text)
        channel = self._get_private_channel(channel_id)
        if channel is not None:
            return channel
        channel = self.get_channel(channel_id)
        if channel is not None:
            return channel
        recipient: Optional[User] = None
        if author and author.get('id') and int(author['id']) != self.self_id:
            recipient = self.store_user(author)
        dm = DMChannel._from_message(self, channel_id, recipient)
        if recipient is not None:
            self._add_private_channel(dm)
        return dm

    def _update_self(self, data: Dict[str, Any]) -> ClientUser:
        if self.user is None:
            self.user = ClientUser(state=self, data=data)
        else:
            self.user._update(data)
        self._users[self.user.id] = self.user  # type: ignore
        if self.application_id is None:
            self.application_id = self.user.id
        return self.user

    # ------------------------------------------------------------------
    # Typing
    # ------------------------------------------------------------------

    async def _trigger_typing(self, channel: Any) -> None:
        if not self._typing_via_gateway:
            try:
                await self.http.send_typing(channel.id)
                return
            except NotFound:
                self._typing_via_gateway = True
            except Forbidden as exc:
                if exc.code != 'BOT_NOT_ALLOWED':
                    raise
                self._typing_via_gateway = True
        ws = self._get_websocket()
        if ws is None:
            return
        guild = getattr(channel, 'guild', None)
        await ws.send_typing(channel.id, guild.id if guild is not None else None)

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _start_bootstrap(self, ws: BisimWebSocket, *, initial: bool) -> None:
        self._cancel_bootstrap()
        self._bootstrap_task = asyncio.get_running_loop().create_task(
            self._bootstrap_wrapper(ws, initial=initial), name='bisim: bootstrap'
        )

    def _cancel_bootstrap(self) -> None:
        task = self._bootstrap_task
        if task is not None and not task.done():
            task.cancel()
        self._bootstrap_task = None
        for future in self._subscribe_waiters.values():
            if not future.done():
                future.cancel()
        self._subscribe_waiters.clear()

    async def _bootstrap_wrapper(self, ws: BisimWebSocket, *, initial: bool) -> None:
        try:
            await self.bootstrap(ws, initial=initial)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception('Loading the servers failed; reconnecting to try again.')
            await ws.close(code=4000)

    async def bootstrap(self, ws: BisimWebSocket, *, initial: bool) -> None:
        """Loads the bot's servers over REST and subscribes to each of them."""
        me = await self.http.get_me()
        self._update_self(me)

        if self._upload_limit is None:
            try:
                config = await self.http.get_client_config()
                uploads = config.get('uploads') if isinstance(config, dict) else None
                if isinstance(uploads, dict) and uploads.get('maxBytes'):
                    self._upload_limit = int(uploads['maxBytes'])
            except HTTPException:
                pass

        rows = await self.http.get_guilds()
        seen: Set[int] = set()
        first_ready = not self._ready_state_done
        for row in rows or []:
            guild_id = int(row['id'])
            seen.add(guild_id)
            existing = self._guilds.get(guild_id)
            try:
                guild = await self._load_guild(ws, guild_id, dispatch_diff=existing is not None and not first_ready)
            except asyncio.CancelledError:
                raise
            except (NotFound, Forbidden):
                continue
            except Exception:
                _log.exception('Loading server %s failed', guild_id)
                continue
            if existing is None and not first_ready:
                self.dispatch('guild_join', guild)
            else:
                self.dispatch('guild_available', guild)

        if not first_ready:
            for guild_id in list(self._guilds):
                if guild_id not in seen:
                    guild = self._guilds.get(guild_id)
                    if guild is not None:
                        self._remove_guild(guild)
                        self.dispatch('guild_remove', guild)

        try:
            dms = await self.http.get_private_channels()
            for data in dms or []:
                factory, _ = _private_channel_factory(data.get('type'))
                if factory is DMChannel:
                    self.add_dm_channel(data)
                elif factory is GroupChannel:
                    channel = GroupChannel(me=self.user, state=self, data=data)  # type: ignore
                    self._add_private_channel(channel)
        except HTTPException:
            pass

        if first_ready:
            self._ready_state_done = True
            self.call_handlers('ready')
            self.dispatch('ready')
        else:
            self.dispatch('resumed')

    async def _load_guild(self, ws: BisimWebSocket, guild_id: int, *, dispatch_diff: bool = False) -> Guild:
        # GET /guilds/:id also warms the gateway's permission cache, which the subscribe needs.
        detail = await self.http.get_guild(guild_id)
        guild = self._guilds.get(guild_id)
        if guild is None:
            guild = Guild(data=detail, state=self)
        else:
            self._sync_guild(guild, detail, dispatch=dispatch_diff)

        await self._subscribe(ws, guild_id)

        if self._chunk_guilds:
            try:
                await guild.chunk(cache=True)
            except HTTPException:
                _log.debug('Loading the members of %s failed', guild_id, exc_info=True)
        self._apply_pending_presences(guild)
        try:
            voice = await self.http.get_guild_voice_states(guild_id)
            guild._load_voice_states(voice)
        except HTTPException:
            pass
        try:
            emojis = await self.http.get_all_custom_emojis(guild_id)
            guild._load_emojis(emojis)
        except HTTPException:
            pass
        try:
            stickers = await self.http.get_all_guild_stickers(guild_id)
            guild._load_stickers(stickers)
        except HTTPException:
            pass

        self._add_guild(guild)
        return guild

    async def _subscribe(self, ws: BisimWebSocket, guild_id: int) -> bool:
        if not self._intents.presences:
            # Without the presences intent the gateway sends no snapshot to wait for.
            await ws.subscribe_guild(guild_id)
            return True
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._subscribe_waiters[guild_id] = future
        try:
            await ws.subscribe_guild(guild_id)
            return await asyncio.wait_for(future, timeout=self.guild_ready_timeout)
        except asyncio.TimeoutError:
            _log.debug('No presence snapshot for server %s within %.1fs.', guild_id, self.guild_ready_timeout)
            return False
        except PermissionError:
            _log.warning('The gateway refused to subscribe to server %s.', guild_id)
            return False
        finally:
            self._subscribe_waiters.pop(guild_id, None)

    def _on_gateway_error(self, message: Optional[str]) -> None:
        # The gateway's error carries no server id: it answers the subscribe in flight.
        for future in self._subscribe_waiters.values():
            if not future.done():
                future.set_exception(PermissionError(message or 'forbidden'))

    def _sync_guild(self, guild: Guild, detail: Dict[str, Any], *, dispatch: bool) -> None:
        old_channels = dict(guild._channels)
        old_roles = dict(guild._roles)
        channel_before = {cid: (copy.copy(ch), _channel_signature(ch)) for cid, ch in old_channels.items()}
        role_before = {rid: (copy.copy(r), _role_signature(r)) for rid, r in old_roles.items()}

        guild._from_data(detail)
        # Channels that CHANNEL_CREATE already reported: their first refetch only fills them in.
        fresh = self._fresh_channels.pop(guild.id, set())

        if not dispatch:
            return

        for channel_id, channel in guild._channels.items():
            if channel_id in fresh:
                continue
            previous = channel_before.get(channel_id)
            if previous is None:
                self.dispatch('guild_channel_create', channel)
            elif previous[1] != _channel_signature(channel) or type(previous[0]) is not type(channel):
                self.dispatch('guild_channel_update', previous[0], channel)
        for channel_id, channel in old_channels.items():
            if channel_id not in guild._channels:
                self.dispatch('guild_channel_delete', channel)

        for role_id, role in guild._roles.items():
            previous_role = role_before.get(role_id)
            if previous_role is None:
                self.dispatch('guild_role_create', role)
            elif previous_role[1] != _role_signature(role):
                self.dispatch('guild_role_update', previous_role[0], role)
        for role_id, role in old_roles.items():
            if role_id not in guild._roles:
                for member in guild._members.values():
                    member._roles.discard(role_id)
                self.dispatch('guild_role_delete', role)

    async def _resync_guild(self, guild_id: int) -> None:
        try:
            detail = await self.http.get_guild(guild_id)
        except (NotFound, Forbidden):
            guild = self._guilds.get(guild_id)
            if guild is not None:
                self._remove_guild(guild)
                self.dispatch('guild_remove', guild)
            return

        guild = self._guilds.get(guild_id)
        ws = self._get_websocket()
        if guild is None:
            if ws is None:
                return
            guild = await self._load_guild(ws, guild_id)
            self.dispatch('guild_join', guild)
            return

        self._sync_guild(guild, detail, dispatch=True)
        if ws is not None:
            await self._subscribe(ws, guild_id)

    async def _join_guild(self, guild_id: int) -> None:
        ws = self._get_websocket()
        if ws is None:
            return
        try:
            guild = await self._load_guild(ws, guild_id)
        except (NotFound, Forbidden):
            return
        self.dispatch('guild_join', guild)

    async def _refresh_private_channels(self) -> None:
        try:
            dms = await self.http.get_private_channels()
        except HTTPException:
            return
        for data in dms or []:
            factory, _ = _private_channel_factory(data.get('type'))
            if factory is DMChannel:
                self.add_dm_channel(data)
            elif factory is GroupChannel:
                existing = self._private_channels.get(int(data['id']))
                if isinstance(existing, GroupChannel):
                    before = copy.copy(existing)
                    existing._update(data)
                    self.dispatch('private_channel_update', before, existing)
                else:
                    self._add_private_channel(GroupChannel(me=self.user, state=self, data=data))  # type: ignore

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    def _handle_interaction_payload(self, payload: Dict[str, Any]) -> Interaction[Any]:
        interaction = Interaction(data=payload, state=self)
        data: Dict[str, Any] = interaction.data or {}  # type: ignore
        if interaction.type in (InteractionType.application_command, InteractionType.autocomplete):
            if self._command_tree is not None:
                self._command_tree._from_interaction(interaction)
        elif interaction.type is InteractionType.component:
            custom_id = data.get('customId') or ''
            component_type = data.get('componentType')
            if component_type is None:
                component_type = self._component_type_for(interaction, custom_id)
            self._view_store.dispatch_view(int(component_type), custom_id, interaction)
        elif interaction.type is InteractionType.modal_submit:
            custom_id = data.get('customId') or ''
            self._view_store.dispatch_modal(custom_id, interaction, _modal_fields(data))

        self.dispatch('interaction', interaction)
        return interaction

    @staticmethod
    def _component_type_for(interaction: Interaction[Any], custom_id: str) -> int:
        message = interaction.message
        if message is not None:
            for row in message.components:
                for child in getattr(row, 'children', [row]):
                    if getattr(child, 'custom_id', None) == custom_id:
                        return int(child.type.value)
        return 2

    # ------------------------------------------------------------------
    # Parsers: one per Bisim event type
    # ------------------------------------------------------------------

    def parse_message_create(self, data: Dict[str, Any]) -> None:
        message_data = data.get('message') or {}
        if not message_data:
            return
        channel_id = utils._snowflake(message_data.get('channelId') or data.get('channelId'))
        guild_id = utils._snowflake(message_data.get('guildId') or data.get('guildId'))
        channel = self._channel_for(channel_id, guild_id, message_data.get('author'))
        message = Message(state=self, channel=channel, data=message_data)
        if self._messages is not None:
            self._messages.append(message)
        if channel is not None and hasattr(channel, 'last_message_id'):
            try:
                channel.last_message_id = message.id
            except AttributeError:
                pass
        self.dispatch('message', message)

    def parse_message_update(self, data: Dict[str, Any]) -> None:
        message_data = data.get('message') or {}
        if not message_data:
            return
        message_id = int(message_data['id'])
        channel_id = utils._snowflake(message_data.get('channelId') or data.get('channelId'))
        guild_id = utils._snowflake(message_data.get('guildId') or data.get('guildId'))
        cached = self._get_message(message_id)
        channel = cached.channel if cached is not None else self._channel_for(channel_id, guild_id, message_data.get('author'))
        updated = Message(state=self, channel=channel, data=message_data)
        raw = RawMessageUpdateEvent(message_data, updated)
        if cached is not None:
            older = copy.copy(cached)
            raw.cached_message = older
            self.dispatch('raw_message_edit', raw)
            cached._update(message_data)
            self.dispatch('message_edit', older, cached)
        else:
            self.dispatch('raw_message_edit', raw)

        if 'components' in message_data and self._view_store.is_message_tracked(message_id):
            self._view_store.update_from_message(message_id, message_data['components'] or [])

    def parse_message_delete(self, data: Dict[str, Any]) -> None:
        payload = dict(data.get('messageDelete') or {})
        if not payload.get('id'):
            return
        payload.setdefault('channelId', data.get('channelId'))
        payload.setdefault('guildId', data.get('guildId'))
        raw = RawMessageDeleteEvent(payload)
        found = self._get_message(raw.message_id)
        raw.cached_message = found
        self.dispatch('raw_message_delete', raw)
        if self._messages is not None and found is not None:
            self.dispatch('message_delete', found)
            try:
                self._messages.remove(found)
            except ValueError:
                pass
        if self._view_store.is_message_tracked(raw.message_id):
            view = self._view_store.remove_message_tracking(raw.message_id)
            if view is not None:
                view.stop()

    def parse_message_delete_bulk(self, data: Dict[str, Any]) -> None:
        payload = dict(data.get('messageDeleteBulk') or {})
        payload.setdefault('channelId', data.get('channelId'))
        payload.setdefault('guildId', data.get('guildId'))
        raw = RawBulkMessageDeleteEvent(payload)
        if self._messages:
            found_messages = [message for message in self._messages if message.id in raw.message_ids]
        else:
            found_messages = []
        raw.cached_messages = found_messages
        self.dispatch('raw_bulk_message_delete', raw)
        if found_messages:
            self.dispatch('bulk_message_delete', found_messages)
            for msg in found_messages:
                try:
                    self._messages.remove(msg)  # type: ignore
                except ValueError:
                    pass

    def _reaction_payload(self, data: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
        payload = data.get(key)
        if not isinstance(payload, dict) or not payload.get('messageId'):
            return None
        payload = dict(payload)
        payload.setdefault('channelId', data.get('channelId'))
        payload.setdefault('guildId', data.get('guildId'))
        payload.setdefault('userId', data.get('userId'))
        return payload

    def parse_message_reaction_add(self, data: Dict[str, Any]) -> None:
        payload = self._reaction_payload(data, 'reaction')
        if payload is None or not payload.get('userId'):
            return
        partial = PartialEmoji.from_str(payload.get('emoji') or '')
        emoji = PartialEmoji.with_state(self, name=partial.name, animated=partial.animated, id=partial.id)
        raw = RawReactionActionEvent(payload, emoji, 'REACTION_ADD')

        guild = self._get_guild(raw.guild_id)
        if guild is not None:
            raw.member = guild.get_member(raw.user_id)
        message = self._get_message(raw.message_id)
        if message is not None:
            raw.message_author_id = message.author.id
        self.dispatch('raw_reaction_add', raw)

        if message is not None:
            reaction_emoji = self._upgrade_partial_emoji(emoji)
            reaction = message._add_reaction({'emoji': payload.get('emoji'), 'count': 1, 'me': raw.user_id == self.self_id}, reaction_emoji, raw.user_id)
            user = raw.member or self._get_reaction_user(message.channel, raw.user_id)
            if user:
                self.dispatch('reaction_add', reaction, user)

    def parse_message_reaction_remove(self, data: Dict[str, Any]) -> None:
        payload = self._reaction_payload(data, 'reaction')
        if payload is None or not payload.get('userId'):
            return
        partial = PartialEmoji.from_str(payload.get('emoji') or '')
        emoji = PartialEmoji.with_state(self, name=partial.name, animated=partial.animated, id=partial.id)
        raw = RawReactionActionEvent(payload, emoji, 'REACTION_REMOVE')
        message = self._get_message(raw.message_id)
        if message is not None:
            raw.message_author_id = message.author.id
        self.dispatch('raw_reaction_remove', raw)

        if message is not None:
            reaction_emoji = self._upgrade_partial_emoji(emoji)
            try:
                reaction = message._remove_reaction(payload, reaction_emoji, raw.user_id)
            except (AttributeError, ValueError):
                pass
            else:
                user = self._get_reaction_user(message.channel, raw.user_id)
                if user:
                    self.dispatch('reaction_remove', reaction, user)

    def parse_message_reaction_remove_all(self, data: Dict[str, Any]) -> None:
        payload = self._reaction_payload(data, 'reactionRemoveAll')
        if payload is None:
            return
        raw = RawReactionClearEvent(payload)
        self.dispatch('raw_reaction_clear', raw)

        message = self._get_message(raw.message_id)
        if message is not None:
            old_reactions = message.reactions.copy()
            message.reactions.clear()
            self.dispatch('reaction_clear', message, old_reactions)

    def parse_message_reaction_remove_emoji(self, data: Dict[str, Any]) -> None:
        # Every reaction of one emoji on a message is gone (Message.clear_reaction).
        payload = self._reaction_payload(data, 'reactionRemoveEmoji')
        if payload is None:
            return
        partial = PartialEmoji.from_str(payload.get('emoji') or '')
        emoji = PartialEmoji.with_state(self, name=partial.name, animated=partial.animated, id=partial.id)
        raw = RawReactionClearEmojiEvent(payload, emoji)
        self.dispatch('raw_reaction_clear_emoji', raw)

        message = self._get_message(raw.message_id)
        if message is not None:
            try:
                reaction = message._clear_emoji(self._upgrade_partial_emoji(emoji))
            except (AttributeError, ValueError):
                pass
            else:
                if reaction:
                    self.dispatch('reaction_clear_emoji', reaction)

    def parse_message_poll_vote(self, data: Dict[str, Any]) -> None:
        payload = data.get('pollVote')
        if not isinstance(payload, dict) or not payload.get('messageId') or not payload.get('userId'):
            return
        payload = dict(payload)
        payload.setdefault('channelId', data.get('channelId'))
        payload.setdefault('guildId', data.get('guildId'))
        user_id = int(payload['userId'])
        selection = {int(a) for a in payload.get('answerIds') or []}
        counts = {int(c.get('answerId', 0) or 0): int(c.get('count', 0) or 0) for c in payload.get('counts') or []}

        message = self._get_message(int(payload['messageId']))
        poll = message.poll if message is not None else None
        added: List[int] = []
        removed: List[int] = []
        if poll is not None:
            for answer in poll.answers:
                new_count = counts.get(answer.id, 0)
                if new_count > answer.vote_count:
                    added.append(answer.id)
                elif new_count < answer.vote_count:
                    removed.append(answer.id)
            poll._update({'counts': payload.get('counts') or [], 'total': payload.get('total', 0)})
            if user_id == self.self_id:
                for answer in poll.answers:
                    answer.self_voted = answer.id in selection
        else:
            added = sorted(selection)

        user: Optional[Union[User, Member]] = None
        guild = self._get_guild(utils._snowflake(payload.get('guildId')))
        if guild is not None:
            user = guild.get_member(user_id)
        if user is None:
            user = self.get_user(user_id)

        for answer_id in added:
            raw = RawPollVoteActionEvent(payload, answer_id)
            self.dispatch('raw_poll_vote_add', raw)
            if poll is not None and user is not None:
                answer = poll.get_answer(answer_id)
                if answer is not None:
                    self.dispatch('poll_vote_add', user, answer)
        for answer_id in removed:
            raw = RawPollVoteActionEvent(payload, answer_id)
            self.dispatch('raw_poll_vote_remove', raw)
            if poll is not None and user is not None:
                answer = poll.get_answer(answer_id)
                if answer is not None:
                    self.dispatch('poll_vote_remove', user, answer)

    def parse_pins_update(self, data: Dict[str, Any]) -> None:
        payload = data.get('pinsUpdate') or {}
        message_id = utils._snowflake(payload.get('messageId'))
        pinned = bool(payload.get('pinned', False))
        message = self._get_message(message_id)
        if message is not None:
            message.pinned = pinned
        channel_id = utils._snowflake(data.get('channelId'))
        guild_id = utils._snowflake(data.get('guildId'))
        channel = message.channel if message is not None else self._channel_for(channel_id, guild_id)
        if channel is None:
            return
        last_pin = utils.utcnow() if pinned else None
        if getattr(channel, 'guild', None) is not None and not isinstance(channel, PartialMessageable):
            self.dispatch('guild_channel_pins_update', channel, last_pin)
        else:
            self.dispatch('private_channel_pins_update', channel, last_pin)

    def parse_typing_start(self, data: Dict[str, Any]) -> None:
        payload = dict(data.get('typing') or {})
        if not payload.get('userId'):
            return
        payload.setdefault('channelId', data.get('channelId'))
        payload.setdefault('guildId', data.get('guildId'))
        raw = RawTypingEvent(payload)
        guild = self._get_guild(raw.guild_id)
        user: Optional[Union[User, Member]] = None
        if guild is not None:
            user = guild.get_member(raw.user_id)
        if user is None:
            user = self.get_user(raw.user_id)
        raw.user = user
        self.dispatch('raw_typing', raw)

        channel = self._channel_for(raw.channel_id, raw.guild_id)
        if user is not None and channel is not None and raw.user_id != self.self_id:
            self.dispatch('typing', channel, user, raw.timestamp)

    def parse_presence_update(self, data: Dict[str, Any]) -> None:
        payload = data.get('presence') or {}
        guild_id = utils._snowflake(payload.get('guildId') or data.get('guildId'))
        if guild_id is None or not payload.get('userId'):
            # Friend presence: a bot has no friends.
            return
        guild = self._get_guild(guild_id)
        if guild is None:
            return
        if self._enable_raw_presences:
            raw = RawPresenceUpdateEvent(data={**payload, 'guildId': str(guild_id)}, state=self)
            self.dispatch('raw_presence_update', raw)
        member = guild.get_member(int(payload['userId']))
        if member is None:
            return
        old_member = Member._copy(member)
        member._presence_update(payload)
        self.dispatch('presence_update', old_member, member)

    def parse_presence_sync(self, data: Dict[str, Any]) -> None:
        guild_id = utils._snowflake(data.get('guildId'))
        payload = data.get('presenceSync') or {}
        if guild_id is not None:
            guild = self._get_guild(guild_id)
            if guild is not None:
                for presence in payload.get('presences') or []:
                    user_id = utils._snowflake(presence.get('userId'))
                    member = guild.get_member(user_id) if user_id is not None else None
                    if member is not None:
                        member._presence_update(presence)
            waiter = self._subscribe_waiters.get(guild_id)
            if waiter is not None and not waiter.done():
                waiter.set_result(True)
            pending = self._pending_presences.setdefault(guild_id, [])
            pending.clear()
            pending.extend(payload.get('presences') or [])

    def _apply_pending_presences(self, guild: Guild) -> None:
        for presence in self._pending_presences.pop(guild.id, []):
            user_id = utils._snowflake(presence.get('userId'))
            member = guild.get_member(user_id) if user_id is not None else None
            if member is not None:
                member._presence_update(presence)

    def parse_guild_update(self, data: Dict[str, Any]) -> None:
        payload = data.get('guildUpdate') or {}
        guild_id = utils._snowflake(payload.get('id') or data.get('guildId'))
        guild = self._get_guild(guild_id)
        if guild is None:
            _log.debug('GUILD_UPDATE referencing an unknown guild ID: %s. Discarding.', guild_id)
            return
        old_guild = copy.copy(guild)
        guild._update_from_event(payload)
        self.dispatch('guild_update', old_guild, guild)

    def parse_channel_update(self, data: Dict[str, Any]) -> None:
        payload = data.get('channelUpdate') or {}
        channel_id = utils._snowflake(payload.get('id') or data.get('channelId'))
        guild_id = utils._snowflake(data.get('guildId'))
        guild = self._get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild is not None and channel_id is not None else None
        if channel is None:
            _log.debug('CHANNEL_UPDATE referencing an unknown channel ID: %s. Discarding.', channel_id)
            return
        old_channel = copy.copy(channel)
        channel._update_from_event(payload)
        self.dispatch('guild_channel_update', old_channel, channel)

    def parse_channel_create(self, data: Dict[str, Any]) -> None:
        payload = data.get('channelUpdate') or {}
        guild = self._get_guild(utils._snowflake(payload.get('guildId') or data.get('guildId')))
        channel_id = utils._snowflake(payload.get('id') or data.get('channelId'))
        if guild is None or channel_id is None:
            _log.debug('CHANNEL_CREATE referencing an unknown guild or channel. Discarding.')
            return
        if guild.get_channel(channel_id) is not None:
            # A GUILD_RESYNC that came first already reported it.
            return
        cls, _ = _guild_channel_factory(payload.get('type'))
        if cls is None:
            _log.debug('CHANNEL_CREATE with an unknown channel type %r. Discarding.', payload.get('type'))
            return
        channel_data = dict(payload)
        channel_data.setdefault('guildId', str(guild.id))
        channel = cls(state=self, guild=guild, data=channel_data)
        guild._add_channel(channel)
        self._fresh_channels.setdefault(guild.id, set()).add(channel.id)
        self.dispatch('guild_channel_create', channel)

    def parse_channel_delete(self, data: Dict[str, Any]) -> None:
        payload = data.get('channelUpdate') or {}
        guild = self._get_guild(utils._snowflake(payload.get('guildId') or data.get('guildId')))
        channel_id = utils._snowflake(payload.get('id') or data.get('channelId'))
        if guild is None or channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            # Already gone: a GUILD_RESYNC that came first reported it.
            return
        guild._remove_channel(channel)
        fresh = self._fresh_channels.get(guild.id)
        if fresh is not None:
            fresh.discard(channel_id)
        self.dispatch('guild_channel_delete', channel)

    def parse_guild_role_create(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        role_data = (data.get('guildRole') or {}).get('role') or {}
        if guild is None or not role_data.get('id'):
            return
        role = Role(guild=guild, data=role_data, state=self)
        guild._add_role(role)
        self.dispatch('guild_role_create', role)

    def parse_guild_role_update(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        role_data = (data.get('guildRole') or {}).get('role') or {}
        if guild is None or not role_data.get('id'):
            return
        role = guild.get_role(int(role_data['id']))
        if role is None:
            role = Role(guild=guild, data=role_data, state=self)
            guild._add_role(role)
            self.dispatch('guild_role_create', role)
            return
        old_role = copy.copy(role)
        role._update(role_data)
        self.dispatch('guild_role_update', old_role, role)

    def parse_guild_role_delete(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        role_id = utils._snowflake((data.get('guildRoleDelete') or {}).get('roleId'))
        if guild is None or role_id is None:
            return
        try:
            role = guild._remove_role(role_id)
        except KeyError:
            return
        self.dispatch('guild_role_delete', role)

    def parse_guild_role_positions(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        if guild is None:
            return
        for entry in (data.get('guildRolePositions') or {}).get('roles') or []:
            role = guild.get_role(int(entry['id']))
            if role is None:
                continue
            position = utils._int(entry.get('position'), 0)
            if role.position != position:
                old_role = copy.copy(role)
                role.position = position
                self.dispatch('guild_role_update', old_role, role)

    def parse_guild_member_add(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        member_data = (data.get('guildMember') or {}).get('member') or {}
        if guild is None or not (member_data.get('userId') or (member_data.get('user') or {}).get('id')):
            return
        member = Member(data=member_data, guild=guild, state=self)
        if member.id == self.self_id:
            # The bot itself: GUILD_JOIN carries the news.
            guild._add_member(member)
            return
        existed = member.id in guild._members
        guild._add_member(member)
        if not existed and guild._member_count is not None:
            guild._member_count += 1
        self.dispatch('member_join', member)

    def parse_guild_member_update(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        member_data = (data.get('guildMember') or {}).get('member') or {}
        user_id = utils._snowflake(member_data.get('userId') or (member_data.get('user') or {}).get('id'))
        if guild is None or user_id is None:
            return
        member = guild.get_member(user_id)
        if member is None:
            _log.debug('GUILD_MEMBER_UPDATE referencing an unknown member ID: %s. Adding it.', user_id)
            guild._add_member(Member(data=member_data, guild=guild, state=self))
            return
        old_member = Member._copy(member)
        member._update_from_event(member_data)
        if user_id == self.self_id:
            guild._my_role_ids = set(member._roles)

        old_user = old_member._user
        new_user = member._user
        if (old_user.name, old_user.global_name, old_user._avatar) != (new_user.name, new_user.global_name, new_user._avatar):
            self.dispatch('user_update', old_user, new_user)

        if (old_member.nick, list(old_member._roles), old_member.timed_out_until) != (
            member.nick,
            list(member._roles),
            member.timed_out_until,
        ):
            self.dispatch('member_update', old_member, member)

    def parse_guild_member_remove(self, data: Dict[str, Any]) -> None:
        guild_id = utils._snowflake(data.get('guildId'))
        guild = self._get_guild(guild_id)
        payload = data.get('guildMemberRemove') or {}
        user_data = payload.get('user') if isinstance(payload.get('user'), dict) else None
        user_id = utils._snowflake(payload.get('userId') or (user_data or {}).get('id'))
        if guild is None or user_id is None:
            return
        if user_id == self.self_id:
            self._remove_guild(guild)
            self.dispatch('guild_remove', guild)
            return
        # Who left, as Bisim sends it: the user is known even when the member was not cached.
        user: User
        if user_data and user_data.get('id'):
            user = self.store_user(user_data)
        else:
            user = self.get_user(user_id) or self.create_user({'id': user_id, 'username': ''})
        raw = RawMemberRemoveEvent(guild.id, user)
        member = guild.get_member(user_id)
        if member is not None:
            guild._remove_member(member)
            raw.user = member
        else:
            # Not cached: a member built from the user, without roles or a join date.
            member = Member(
                data={'userId': str(user_id), 'user': user._to_minimal_user_json(), 'roleIds': []},
                guild=guild,
                state=self,
            )
        if guild._member_count is not None:
            guild._member_count = max(guild._member_count - 1, 0)
        guild._voice_states.pop(user_id, None)
        self.dispatch('member_remove', member)
        self.dispatch('raw_member_remove', raw)

    def parse_guild_emoji_create(self, data: Dict[str, Any]) -> None:
        emoji_data = data.get('emoji') or {}
        guild = self._get_guild(utils._snowflake(emoji_data.get('guildId') or data.get('guildId')))
        if guild is None or not emoji_data.get('id'):
            return
        before = guild.emojis
        emoji = self.store_emoji(guild, emoji_data)
        guild.emojis = tuple(e for e in before if e.id != emoji.id) + (emoji,)
        self.dispatch('guild_emojis_update', guild, before, guild.emojis)

    def parse_guild_emoji_update(self, data: Dict[str, Any]) -> None:
        # A renamed emoji: the row's current state, in GUILD_EMOJI_CREATE's payload.
        emoji_data = data.get('emoji') or {}
        guild = self._get_guild(utils._snowflake(emoji_data.get('guildId') or data.get('guildId')))
        if guild is None or not emoji_data.get('id'):
            return
        before = guild.emojis
        emoji = self.store_emoji(guild, emoji_data)
        if any(e.id == emoji.id for e in before):
            guild.emojis = tuple(emoji if e.id == emoji.id else e for e in before)
        else:
            guild.emojis = before + (emoji,)
        self.dispatch('guild_emojis_update', guild, before, guild.emojis)

    def parse_guild_emoji_delete(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        emoji_id = utils._snowflake((data.get('emojiDelete') or {}).get('emojiId'))
        if guild is None or emoji_id is None:
            return
        before = guild.emojis
        guild.emojis = tuple(e for e in before if e.id != emoji_id)
        self._emojis.pop(emoji_id, None)
        self.dispatch('guild_emojis_update', guild, before, guild.emojis)

    def parse_guild_sticker_create(self, data: Dict[str, Any]) -> None:
        sticker_data = data.get('sticker') or {}
        guild = self._get_guild(utils._snowflake(sticker_data.get('guildId') or data.get('guildId')))
        if guild is None or not sticker_data.get('id'):
            return
        payload = dict(sticker_data)
        payload.setdefault('guildId', str(guild.id))
        before = guild.stickers
        sticker = GuildSticker(state=self, data=payload)
        self._stickers[sticker.id] = sticker
        guild.stickers = tuple(s for s in before if s.id != sticker.id) + (sticker,)
        self.dispatch('guild_stickers_update', guild, before, guild.stickers)

    def parse_guild_sticker_update(self, data: Dict[str, Any]) -> None:
        # A renamed sticker: the row's current state, in GUILD_STICKER_CREATE's payload.
        sticker_data = data.get('sticker') or {}
        guild = self._get_guild(utils._snowflake(sticker_data.get('guildId') or data.get('guildId')))
        if guild is None or not sticker_data.get('id'):
            return
        payload = dict(sticker_data)
        payload.setdefault('guildId', str(guild.id))
        before = guild.stickers
        sticker = GuildSticker(state=self, data=payload)
        self._stickers[sticker.id] = sticker
        if any(s.id == sticker.id for s in before):
            guild.stickers = tuple(sticker if s.id == sticker.id else s for s in before)
        else:
            guild.stickers = before + (sticker,)
        self.dispatch('guild_stickers_update', guild, before, guild.stickers)

    def parse_guild_sticker_delete(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        sticker_id = utils._snowflake((data.get('stickerDelete') or {}).get('stickerId'))
        if guild is None or sticker_id is None:
            return
        before = guild.stickers
        guild.stickers = tuple(s for s in before if s.id != sticker_id)
        self._stickers.pop(sticker_id, None)
        self.dispatch('guild_stickers_update', guild, before, guild.stickers)

    def parse_guild_ban_add(self, data: Dict[str, Any]) -> None:
        # GUILD_BAN_ADD may come before or after GUILD_MEMBER_REMOVE; it only reports the ban.
        payload = data.get('guildBan') or {}
        guild = self._get_guild(utils._snowflake(payload.get('guildId') or data.get('guildId')))
        user_data = payload.get('user')
        if guild is None or not isinstance(user_data, dict) or not user_data.get('id'):
            return
        user = self.store_user(user_data)
        member = guild.get_member(user.id) or user
        self.dispatch('member_ban', guild, member)

    def parse_guild_ban_remove(self, data: Dict[str, Any]) -> None:
        payload = data.get('guildBan') or {}
        guild = self._get_guild(utils._snowflake(payload.get('guildId') or data.get('guildId')))
        user_data = payload.get('user')
        if guild is None or not isinstance(user_data, dict) or not user_data.get('id'):
            return
        self.dispatch('member_unban', guild, self.store_user(user_data))

    def parse_invite_create(self, data: Dict[str, Any]) -> None:
        payload = data.get('invite') or {}
        if not payload.get('code'):
            return
        # The gateway counts max_age in seconds as ``maxAge`` (REST: ``maxAgeSec``); a 0 is left out.
        invite_data = {
            'code': payload['code'],
            'guildId': payload.get('guildId') or data.get('guildId'),
            'channelId': payload.get('channelId') or data.get('channelId') or None,
            'inviter': payload.get('inviter'),
            'maxUses': utils._int(payload.get('maxUses'), 0),
            'uses': utils._int(payload.get('uses'), 0),
            'maxAgeSec': utils._int(payload.get('maxAge'), 0),
            'createdAt': payload.get('createdAt'),
            'expiresAt': payload.get('expiresAt') or None,
        }
        self.dispatch('invite_create', Invite.from_incomplete(state=self, data=invite_data))

    def parse_invite_delete(self, data: Dict[str, Any]) -> None:
        payload = data.get('inviteDelete') or {}
        if not payload.get('code'):
            return
        invite_data = {
            'code': payload['code'],
            'guildId': payload.get('guildId') or data.get('guildId'),
            'channelId': payload.get('channelId') or data.get('channelId') or None,
        }
        self.dispatch('invite_delete', Invite.from_incomplete(state=self, data=invite_data))

    def parse_guild_audit_log_entry_create(self, data: Dict[str, Any]) -> None:
        payload = data.get('auditLogEntry') or {}
        guild = self._get_guild(utils._snowflake(payload.get('guildId') or data.get('guildId')))
        if guild is None or not payload.get('id'):
            _log.debug('GUILD_AUDIT_LOG_ENTRY_CREATE referencing an unknown guild. Discarding.')
            return
        self.dispatch('audit_log_entry_create', AuditLogEntry(guild=guild, data=payload))

    def parse_webhooks_update(self, data: Dict[str, Any]) -> None:
        payload = data.get('webhooksUpdate') or {}
        guild = self._get_guild(utils._snowflake(payload.get('guildId') or data.get('guildId')))
        channel_id = utils._snowflake(payload.get('channelId') or data.get('channelId'))
        channel = guild.get_channel(channel_id) if guild is not None and channel_id is not None else None
        if channel is None:
            _log.debug('WEBHOOKS_UPDATE referencing an unknown channel ID: %s. Discarding.', channel_id)
            return
        self.dispatch('webhooks_update', channel)

    def _parse_automod_rule(self, data: Dict[str, Any], event: str) -> None:
        payload = data.get('automodRule') or {}
        guild = self._get_guild(utils._snowflake(payload.get('guildId') or data.get('guildId')))
        if guild is None or not payload.get('id'):
            _log.debug('An AutoMod rule event referencing an unknown guild. Discarding.')
            return
        self.dispatch(event, AutoModRule(data=payload, guild=guild, state=self))

    def parse_auto_moderation_rule_create(self, data: Dict[str, Any]) -> None:
        self._parse_automod_rule(data, 'automod_rule_create')

    def parse_auto_moderation_rule_update(self, data: Dict[str, Any]) -> None:
        self._parse_automod_rule(data, 'automod_rule_update')

    def parse_auto_moderation_rule_delete(self, data: Dict[str, Any]) -> None:
        self._parse_automod_rule(data, 'automod_rule_delete')

    def parse_auto_moderation_action_execution(self, data: Dict[str, Any]) -> None:
        payload = dict(data.get('automodAction') or {})
        if not payload.get('guildId'):
            payload['guildId'] = data.get('guildId')
        if self._get_guild(utils._snowflake(payload.get('guildId'))) is None:
            _log.debug('AUTO_MODERATION_ACTION_EXECUTION referencing an unknown guild. Discarding.')
            return
        if not payload.get('ruleId') or not payload.get('userId'):
            return
        self.dispatch('automod_action', AutoModAction(data=payload, state=self))

    def parse_voice_state_update(self, data: Dict[str, Any]) -> None:
        payload = data.get('voiceState') or {}
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        if guild is None or not payload.get('userId'):
            return
        channel_id = utils._snowflake(data.get('channelId'))
        if int(payload['userId']) == self.self_id:
            voice = self._get_voice_client(guild.id)
            if voice is not None:
                raw = dict(payload, channelId=data.get('channelId'), guildId=data.get('guildId'))
                self._spawn(voice.on_voice_state_update(raw), name='bisim: voice state update')
        member, before, after = guild._update_voice_state(payload, channel_id)
        if member is not None:
            self.dispatch('voice_state_update', member, before, after)

    def parse_voice_channel_status_update(self, data: Dict[str, Any]) -> None:
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        channel_id = utils._snowflake(data.get('channelId'))
        channel = guild.get_channel(channel_id) if guild is not None and channel_id else None
        if not isinstance(channel, VoiceChannel):
            return
        before = channel.status
        channel.status = (data.get('voiceChannelStatus') or {}).get('status') or None
        self.dispatch('voice_channel_status_update', channel, before, channel.status)

    def parse_voice_move(self, data: Dict[str, Any]) -> None:
        # A moderator moved the bot; only the bot's own user room gets this.
        payload = data.get('voiceMove') or {}
        guild_id = utils._snowflake(payload.get('guildId') or data.get('guildId'))
        voice = self._get_voice_client(guild_id)
        if voice is None:
            return
        self._spawn(voice.on_voice_move(dict(payload)), name='bisim: voice move')

    def parse_user_update(self, data: Dict[str, Any]) -> None:
        payload = (data.get('userUpdate') or {}).get('user') or {}
        user_id = utils._snowflake(payload.get('id'))
        if user_id is None:
            return
        if user_id == self.self_id and self.user is not None:
            before = copy.copy(self.user)
            if self.user._patch(payload):
                self.dispatch('user_update', before, self.user)
            return
        user = self._users.get(user_id)
        if user is None:
            return
        before_user = User._copy(user)
        if user._patch(payload):
            self.dispatch('user_update', before_user, user)

    def parse_interaction_create(self, data: Dict[str, Any]) -> None:
        payload_json = (data.get('interaction') or {}).get('payloadJson')
        if not payload_json:
            return
        try:
            payload = utils._from_json(payload_json)
        except ValueError:
            _log.warning('INTERACTION_CREATE carried a payload that is not JSON. Discarding.')
            return
        self._handle_interaction_payload(payload)

    def parse_guild_resync(self, data: Dict[str, Any]) -> None:
        guild_id = utils._snowflake(data.get('guildId'))
        if guild_id is None:
            return
        self._spawn(self._resync_guild(guild_id), name=f'bisim: resync {guild_id}')

    def parse_guild_join(self, data: Dict[str, Any]) -> None:
        payload = data.get('guildJoin') or {}
        guild_id = utils._snowflake(payload.get('guildId') or data.get('guildId'))
        if guild_id is None:
            return
        if guild_id in self._guilds:
            self._spawn(self._resync_guild(guild_id), name=f'bisim: resync {guild_id}')
            return
        self._spawn(self._join_guild(guild_id), name=f'bisim: join {guild_id}')

    def parse_dm_channel_update(self, data: Dict[str, Any]) -> None:
        self._spawn(self._refresh_private_channels(), name='bisim: refresh dms')

    def parse_resumed(self, data: Dict[str, Any]) -> None:
        _log.debug('The gateway acknowledged a resume.')

    def _sound_guild(self, data: Dict[str, Any], sound: Dict[str, Any]) -> Optional[Guild]:
        return self._get_guild(utils._snowflake(sound.get('guildId') or data.get('guildId')))

    def parse_guild_sound_create(self, data: Dict[str, Any]) -> None:
        payload = data.get('sound') or {}
        guild = self._sound_guild(data, payload)
        if guild is None or not payload.get('id'):
            _log.debug('GUILD_SOUND_CREATE referencing an unknown guild. Discarding.')
            return
        sound = SoundboardSound(guild=guild, state=self, data=payload)
        guild._add_soundboard_sound(sound)
        self.dispatch('soundboard_sound_create', sound)

    def parse_guild_sound_update(self, data: Dict[str, Any]) -> None:
        payload = data.get('sound') or {}
        guild = self._sound_guild(data, payload)
        sound_id = utils._snowflake(payload.get('id'))
        if guild is None or sound_id is None:
            _log.debug('GUILD_SOUND_UPDATE referencing an unknown guild. Discarding.')
            return
        sound = guild.get_soundboard_sound(sound_id)
        if sound is None:
            # Bisim does not send the sounds at connect, so one the library has not seen
            # yet is reported with ``before`` the same as ``after``.
            sound = SoundboardSound(guild=guild, state=self, data=payload)
            guild._add_soundboard_sound(sound)
            before = copy.copy(sound)
        else:
            before = copy.copy(sound)
            sound._update(payload)
        self.dispatch('soundboard_sound_update', before, sound)

    def parse_guild_sound_delete(self, data: Dict[str, Any]) -> None:
        sound_id = utils._snowflake((data.get('soundDelete') or {}).get('soundId'))
        guild = self._get_guild(utils._snowflake(data.get('guildId')))
        if guild is None or sound_id is None:
            _log.debug('GUILD_SOUND_DELETE referencing an unknown guild. Discarding.')
            return
        sound = guild._remove_soundboard_sound(sound_id)
        if sound is None:
            # Not seen before: all that is known is its id.
            sound = SoundboardSound(guild=guild, state=self, data={'id': str(sound_id), 'guildId': str(guild.id)})
        self.dispatch('soundboard_sound_delete', sound)

    def parse_soundboard_play(self, data: Dict[str, Any]) -> None:
        # Someone pressed a sound in a voice channel: Discord's VOICE_CHANNEL_EFFECT_SEND.
        from .channel import VoiceChannelEffect

        payload = dict(data.get('soundboardPlay') or {})
        guild = self._get_guild(utils._snowflake(data.get('guildId') or (payload.get('sound') or {}).get('guildId')))
        channel_id = utils._snowflake(data.get('channelId'))
        if guild is None or channel_id is None or guild.get_channel(channel_id) is None:
            _log.debug('SOUNDBOARD_PLAY referencing an unknown guild or channel. Discarding.')
            return
        payload['channelId'] = str(channel_id)
        self.dispatch('voice_channel_effect', VoiceChannelEffect(state=self, data=payload, guild=guild))

    def _ignore(self, data: Dict[str, Any]) -> None:
        return None

    # Events that concern people, not bots, or that the library has no model for yet.
    parse_message_ack = _ignore
    parse_relationship_update = _ignore
    parse_call_update = _ignore
    parse_voice_poke = _ignore
    parse_user_layout_update = _ignore
    parse_guild_patch = _ignore

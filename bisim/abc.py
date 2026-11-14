"""Abstract base classes: :class:`Snowflake`, :class:`Messageable`, :class:`GuildChannel`..."""

from __future__ import annotations

import asyncio
import copy
import datetime
import secrets
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
    runtime_checkable,
)

from . import utils
from .context_managers import Typing
from .enums import ChannelType
from .errors import ClientException, InvalidData, NotSupported
from .file import File
from .invite import Invite
from .mentions import AllowedMentions
from .permissions import PermissionOverwrite, Permissions

if TYPE_CHECKING:
    from typing_extensions import Self

    from .asset import Asset
    from .channel import CategoryChannel, DMChannel, GroupChannel, PartialMessageable, TextChannel, VoiceChannel
    from .embeds import Embed
    from .guild import Guild
    from .member import Member
    from .message import Message, MessageReference, PartialMessage
    from .poll import Poll
    from .role import Role
    from .state import ConnectionState
    from .ui.view import View
    from .user import ClientUser

    MessageableChannel = Union[TextChannel, DMChannel, GroupChannel, PartialMessageable]
    SnowflakeTime = Union['Snowflake', datetime.datetime]

__all__ = (
    'Snowflake',
    'User',
    'PrivateChannel',
    'GuildChannel',
    'Messageable',
    'Connectable',
)

T = TypeVar('T', bound=type)


@runtime_checkable
class Snowflake(Protocol):
    """An ABC that details the common operations on a Bisim model.

    Almost all :ref:`Bisim models <bisim_api_models>` meet this
    abstract base class.

    If you want to create a snowflake on your own, consider using
    :class:`.Object`.

    Attributes
    -----------
    id: :class:`int`
        The model's unique ID.
    """

    id: int


@runtime_checkable
class User(Snowflake, Protocol):
    """An ABC that details the common operations on a Bisim user.

    The following implement this ABC:

    - :class:`~bisim.User`
    - :class:`~bisim.ClientUser`
    - :class:`~bisim.Member`

    This ABC must also implement :class:`~bisim.abc.Snowflake`.

    Attributes
    -----------
    name: :class:`str`
        The user's username.
    discriminator: :class:`str`
        Always ``'0'`` on Bisim.
    global_name: Optional[:class:`str`]
        The user's display name, if they have one.
    bot: :class:`bool`
        If the user is a bot account.
    system: :class:`bool`
        If the user is a system account.
    """

    name: str
    discriminator: str
    global_name: Optional[str]
    bot: bool
    system: bool

    @property
    def display_name(self) -> str:
        """:class:`str`: Returns the user's display name."""
        raise NotImplementedError

    @property
    def mention(self) -> str:
        """:class:`str`: Returns a string that allows you to mention the given user."""
        raise NotImplementedError

    @property
    def avatar(self) -> Optional[Asset]:
        """Optional[:class:`~bisim.Asset`]: Returns an Asset that represents the user's avatar, if present."""
        raise NotImplementedError

    @property
    def default_avatar(self) -> Asset:
        """:class:`~bisim.Asset`: Returns the default avatar for a given user."""
        raise NotImplementedError

    @property
    def display_avatar(self) -> Asset:
        """:class:`~bisim.Asset`: Returns the user's display avatar."""
        raise NotImplementedError

    def mentioned_in(self, message: Message) -> bool:
        """Checks if the user is mentioned in the specified message."""
        raise NotImplementedError


@runtime_checkable
class PrivateChannel(Protocol):
    """An ABC that details the common operations on a private Bisim channel.

    The following implement this ABC:

    - :class:`~bisim.DMChannel`
    - :class:`~bisim.GroupChannel`

    This ABC must also implement :class:`~bisim.abc.Snowflake`.

    Attributes
    -----------
    me: :class:`~bisim.ClientUser`
        The user presenting yourself.
    """

    __slots__ = ()

    id: int
    me: ClientUser


class _Overwrites:
    __slots__ = ('id', 'allow', 'deny', 'type')

    ROLE = 0
    MEMBER = 1

    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: int = int(data.get('targetId') or data.get('id'))
        self.allow: int = utils._int(data.get('allow'), 0)
        self.deny: int = utils._int(data.get('deny'), 0)
        raw_type = data.get('type', 0)
        if isinstance(raw_type, str) and not raw_type.isdigit():
            self.type: int = 0 if raw_type.lower() == 'role' else 1
        else:
            self.type = int(raw_type or 0)

    def _asdict(self) -> Dict[str, Any]:
        return {'id': str(self.id), 'allow': str(self.allow), 'deny': str(self.deny), 'type': self.type}

    def is_role(self) -> bool:
        return self.type == 0

    def is_member(self) -> bool:
        return self.type == 1


# ---------------------------------------------------------------------------
# Building what is sent
# ---------------------------------------------------------------------------


def _embeds_payload(embed: Optional[Embed], embeds: Optional[Sequence[Embed]]) -> Optional[List[Dict[str, Any]]]:
    if embed is not None and embed is not utils.MISSING and embeds is not None and embeds is not utils.MISSING:
        raise TypeError('Cannot mix embed and embeds keyword arguments.')
    if embeds is not None and embeds is not utils.MISSING:
        if len(embeds) > 10:
            raise ValueError('embeds has a maximum of 10 elements.')
        return [e._to_bisim() for e in embeds]
    if embed is not None and embed is not utils.MISSING:
        return [embed._to_bisim()]
    return None


async def _upload_files(state: ConnectionState, channel_id: int, files: Sequence[File]) -> List[Dict[str, Any]]:
    """The presigned upload flow: ask for addresses, PUT the bytes, return the attachment list."""
    if len(files) > 10:
        raise ValueError('files has a maximum of 10 elements.')
    blobs: List[Tuple[File, bytes]] = []
    for f in files:
        if not isinstance(f, File):
            raise TypeError(f'files must be a list of File, not {f.__class__.__name__}')
        blobs.append((f, f._read_all()))
    request = [{'fileName': f._filename, 'contentType': f.content_type, 'sizeBytes': len(data)} for f, data in blobs]
    response = await state.http.create_attachments(channel_id, request)
    slots = (response or {}).get('attachments') if isinstance(response, dict) else None
    if not isinstance(slots, list) or len(slots) != len(blobs):
        raise InvalidData('Bisim did not return an upload address for every file.')
    attachments: List[Dict[str, Any]] = []
    for (f, data), slot in zip(blobs, slots):
        await state.http.upload_to_url(slot['uploadUrl'], data, f.content_type)
        entry: Dict[str, Any] = {
            'id': str(slot['id']),
            'uploadFilename': slot['uploadFilename'],
            'fileName': f._filename,
            'contentType': f.content_type,
            'sizeBytes': len(data),
        }
        if f.description:
            entry['description'] = f.description
        if f.spoiler:
            entry['spoiler'] = True
        attachments.append(entry)
    return attachments


def _view_payload(view: Any) -> Optional[List[Dict[str, Any]]]:
    if view is None or view is utils.MISSING:
        return None
    return view.to_components()


def _flags_value(*, silent: bool = False, suppress_embeds: bool = False, ephemeral: bool = False) -> int:
    value = 0
    if suppress_embeds:
        value |= 4
    if ephemeral:
        value |= 64
    if silent:
        value |= 4096
    return value


async def _message_payload(
    state: ConnectionState,
    channel_id: Optional[int],
    *,
    content: Any = utils.MISSING,
    embed: Any = utils.MISSING,
    embeds: Any = utils.MISSING,
    file: Any = utils.MISSING,
    files: Any = utils.MISSING,
    attachments: Any = utils.MISSING,
    view: Any = utils.MISSING,
    poll: Any = utils.MISSING,
    reference: Any = None,
    stickers: Any = None,
    nonce: Any = None,
    tts: bool = False,
    silent: bool = False,
    suppress_embeds: bool = False,
    ephemeral: bool = False,
    editing: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}

    if content is not utils.MISSING:
        payload['content'] = str(content) if content is not None else ('' if editing else None)
        if payload['content'] is None:
            del payload['content']

    if stickers:
        tokens = ' '.join(f'<sticker:{s.id}>' for s in stickers)
        payload['content'] = f"{payload['content']} {tokens}" if payload.get('content') else tokens

    if embed is not utils.MISSING or embeds is not utils.MISSING:
        if embed is None and embeds is utils.MISSING:
            payload['embeds'] = []
        else:
            built = _embeds_payload(embed if embed is not utils.MISSING else None, embeds if embeds is not utils.MISSING else None)
            payload['embeds'] = built or []
        if not editing and not payload['embeds']:
            del payload['embeds']

    if view is not utils.MISSING:
        if view is None:
            payload['components'] = []
        else:
            payload['components'] = _view_payload(view) or []
        if not editing and not payload['components']:
            del payload['components']

    if poll is not None and poll is not utils.MISSING:
        payload['poll'] = poll._to_bisim()

    if reference is not None and reference is not utils.MISSING:
        ref_id = getattr(reference, 'message_id', None) or getattr(reference, 'id', None)
        if ref_id is None:
            raise TypeError('reference parameter must be Message, MessageReference, or PartialMessage')
        payload['referencedMessageId'] = str(ref_id)

    if not editing:
        payload['nonce'] = str(nonce) if nonce is not None else secrets.token_hex(8)

    flags = _flags_value(silent=silent, suppress_embeds=suppress_embeds, ephemeral=ephemeral)
    if flags:
        payload['flags'] = flags
    if tts:
        payload['tts'] = True

    if file is not utils.MISSING and files is not utils.MISSING and file is not None and files is not None:
        raise TypeError('Cannot mix file and files keyword arguments.')
    upload: List[File] = []
    if file is not utils.MISSING and file is not None:
        upload = [file]
    elif files is not utils.MISSING and files is not None:
        upload = list(files)

    kept: List[Dict[str, Any]] = []
    if attachments is not utils.MISSING and attachments is not None:
        for item in attachments:
            if isinstance(item, File):
                upload.append(item)
            else:
                kept.append(item.to_dict() if hasattr(item, 'to_dict') else item)

    if upload:
        if channel_id is None:
            raise NotSupported('Sending files here')
        try:
            payload['attachments'] = kept + await _upload_files(state, channel_id, upload)
        finally:
            for f in upload:
                f.close()
    elif attachments is not utils.MISSING:
        payload['attachments'] = kept

    return payload


# ---------------------------------------------------------------------------
# GuildChannel
# ---------------------------------------------------------------------------


class GuildChannel:
    """An ABC that details the common operations on a Bisim guild channel.

    The following implement this ABC:

    - :class:`~bisim.TextChannel`
    - :class:`~bisim.VoiceChannel`
    - :class:`~bisim.CategoryChannel`

    This ABC must also implement :class:`~bisim.abc.Snowflake`.

    Attributes
    -----------
    name: :class:`str`
        The channel name.
    guild: :class:`~bisim.Guild`
        The guild the channel belongs to.
    position: :class:`int`
        The position in the channel list. This is a number that starts at 0.
        e.g. the top channel is position 0.
    """

    __slots__ = ()

    id: int
    name: str
    guild: Guild
    type: ChannelType
    position: int
    category_id: Optional[int]
    _state: ConnectionState
    _overwrites: List[_Overwrites]
    _overwrites_loaded: bool
    _permissions_synced: bool
    _my_permissions: Optional[int]
    _is_private: bool

    if TYPE_CHECKING:

        def __init__(self, *, state: ConnectionState, guild: Guild, data: Dict[str, Any]):
            ...

    def __str__(self) -> str:
        return self.name

    @property
    def _sorting_bucket(self) -> int:
        raise NotImplementedError

    def _update_common(self, guild: Guild, data: Dict[str, Any]) -> None:
        self.guild = guild
        self.name = data.get('name') or ''
        self.category_id = utils._snowflake(data.get('parentId'))
        self.position = utils._int(data.get('position'), 0)
        if 'permissionsSynced' in data:
            self._permissions_synced = bool(data.get('permissionsSynced'))
        elif not hasattr(self, '_permissions_synced'):
            self._permissions_synced = False
        if data.get('permissions') not in (None, ''):
            self._my_permissions = int(data['permissions'])
        elif not hasattr(self, '_my_permissions'):
            self._my_permissions = None
        if 'isPrivate' in data:
            self._is_private = bool(data.get('isPrivate'))
        elif not hasattr(self, '_is_private'):
            self._is_private = False
        overwrites = data.get('permissionOverwrites')
        if overwrites is not None:
            self._overwrites = [_Overwrites(o) for o in overwrites]
            self._overwrites_loaded = True
        elif not hasattr(self, '_overwrites'):
            self._overwrites = []
            self._overwrites_loaded = False

    def _update_from_event(self, data: Dict[str, Any]) -> None:
        """CHANNEL_UPDATE carries the channel's current state; a missing field is empty."""
        self.name = data.get('name') or self.name
        self.category_id = utils._snowflake(data.get('parentId'))
        self.position = utils._int(data.get('position'), 0)
        self._permissions_synced = bool(data.get('permissionsSynced', False))

    async def _move(
        self,
        position: int,
        parent_id: Optional[Any] = None,
        lock_permissions: bool = False,
        *,
        reason: Optional[str],
    ) -> None:
        if position < 0:
            raise ValueError('Channel position cannot be less than 0.')

        bucket = self._sorting_bucket
        channels: List[GuildChannel] = [c for c in self.guild.channels if c._sorting_bucket == bucket]
        channels.sort(key=lambda c: c.position)

        try:
            channels.remove(self)
        except ValueError:
            return
        index = max(0, min(len(channels), position))
        channels.insert(index, self)

        payload = []
        for index, c in enumerate(channels):
            d: Dict[str, Any] = {'id': str(c.id), 'position': index}
            if parent_id is not utils.MISSING and c.id == self.id:
                d['parentId'] = str(parent_id) if parent_id is not None else None
            elif c.category_id is not None:
                d['parentId'] = str(c.category_id)
            payload.append(d)

        await self._state.http.bulk_channel_update(self.guild.id, payload, reason=reason)
        if lock_permissions:
            await self._state.http.edit_channel(self.guild.id, self.id, permissionsSynced=True, reason=reason)

    async def _edit(self, options: Dict[str, Any], reason: Optional[str]) -> Optional[Dict[str, Any]]:
        for unsupported, feature in (
            ('bitrate', 'Setting a voice channel bitrate'),
            ('user_limit', 'Voice channel user limits'),
            ('rtc_region', 'Voice regions'),
            ('video_quality_mode', 'Video quality modes'),
            ('default_auto_archive_duration', 'Threads'),
            ('default_thread_slowmode_delay', 'Threads'),
            ('type', 'Changing a channel type'),
            ('available_tags', 'Forum channels'),
            ('default_reaction_emoji', 'Forum channels'),
            ('default_layout', 'Forum channels'),
            ('default_sort_order', 'Forum channels'),
            ('default_forum_layout', 'Forum channels'),
            ('flags', 'Channel flags'),
            ('status', 'Setting a voice channel status from a bot'),
        ):
            if options.get(unsupported, utils.MISSING) is not utils.MISSING:
                raise NotSupported(feature)

        payload: Dict[str, Any] = {}
        if options.get('name', utils.MISSING) is not utils.MISSING:
            payload['name'] = options['name']
        if options.get('topic', utils.MISSING) is not utils.MISSING:
            payload['topic'] = options['topic'] or ''
        if options.get('nsfw', utils.MISSING) is not utils.MISSING:
            payload['nsfw'] = bool(options['nsfw'])
        if options.get('slowmode_delay', utils.MISSING) is not utils.MISSING:
            payload['slowmodeSec'] = int(options['slowmode_delay'])

        sync = options.get('sync_permissions', utils.MISSING)
        category = options.get('category', utils.MISSING)
        position = options.get('position', utils.MISSING)

        if position is not utils.MISSING:
            parent = category.id if category not in (utils.MISSING, None) else (None if category is None else utils.MISSING)
            await self._move(position, parent_id=parent, lock_permissions=bool(sync), reason=reason)
            category = utils.MISSING
            sync = utils.MISSING
        if category is not utils.MISSING:
            payload['parentId'] = str(category.id) if category is not None else None
        if sync is not utils.MISSING and sync:
            payload['permissionsSynced'] = True

        overwrites = options.get('overwrites', utils.MISSING)

        data: Optional[Dict[str, Any]] = None
        if payload:
            data = await self._state.http.edit_channel(self.guild.id, self.id, reason=reason, **payload)

        if overwrites is not utils.MISSING:
            if not isinstance(overwrites, dict):
                raise TypeError('overwrites parameter expects a dict.')
            await self._replace_overwrites(overwrites, reason=reason)

        return data

    async def _replace_overwrites(self, overwrites: Dict[Any, PermissionOverwrite], *, reason: Optional[str]) -> None:
        await self.fetch_overwrites()
        wanted: Dict[int, Tuple[Any, PermissionOverwrite]] = {}
        for target, perm in overwrites.items():
            if not isinstance(perm, PermissionOverwrite):
                raise TypeError(f'Expected PermissionOverwrite received {perm.__class__.__name__}')
            wanted[target.id] = (target, perm)
        http = self._state.http
        for existing in list(self._overwrites):
            if existing.id not in wanted:
                await http.delete_channel_permissions(self.guild.id, self.id, existing.id, reason=reason)
        for target_id, (target, perm) in wanted.items():
            allow, deny = perm.pair()
            kind = self._overwrite_type(target)
            await http.edit_channel_permissions(self.guild.id, self.id, target_id, allow.value, deny.value, kind, reason=reason)
        await self.fetch_overwrites()

    def _overwrite_type(self, target: Any) -> int:
        from .member import Member
        from .object import Object
        from .role import Role
        from .user import BaseUser

        if isinstance(target, Role):
            return _Overwrites.ROLE
        if isinstance(target, (Member, BaseUser)):
            return _Overwrites.MEMBER
        if isinstance(target, Object):
            if target.type is Role:
                return _Overwrites.ROLE
            if target.type in (Member, BaseUser) or (isinstance(target.type, type) and issubclass(target.type, BaseUser)):
                return _Overwrites.MEMBER
            if self.guild.get_role(target.id) is not None:
                return _Overwrites.ROLE
            return _Overwrites.MEMBER
        raise TypeError('target parameter must be either Member or Role')

    async def fetch_overwrites(self) -> Dict[Union[Role, Member, Any], PermissionOverwrite]:
        """|coro|

        Loads this channel's permission overwrites from Bisim.

        Bisim's server listing does not carry overwrites, so the library
        loads them when it needs them (for instance before a permission
        check on another member) and keeps them until the server says the
        channel changed. This is a Bisim addition.

        Returns
        --------
        Dict[Union[:class:`~bisim.Role`, :class:`~bisim.Member`, :class:`~bisim.Object`], :class:`~bisim.PermissionOverwrite`]
            The channel's overwrites.
        """
        data = await self._state.http.get_channel_overwrites(self.guild.id, self.id)
        self._overwrites = [_Overwrites(o) for o in (data or [])]
        self._overwrites_loaded = True
        return self.overwrites

    async def _ensure_overwrites(self) -> None:
        if not self._overwrites_loaded:
            try:
                await self.fetch_overwrites()
            except Exception:
                # Without overwrites, permissions come from roles alone.
                self._overwrites_loaded = True

    @property
    def changed_roles(self) -> List[Role]:
        """List[:class:`~bisim.Role`]: Returns a list of roles that have been overridden from
        their default values in the :attr:`~bisim.Guild.roles` attribute."""
        ret = []
        g = self.guild
        for overwrite in filter(lambda o: o.is_role(), self._overwrites):
            role = g.get_role(overwrite.id)
            if role is None:
                continue
            role = copy.copy(role)
            role._permissions = (role._permissions & ~overwrite.deny) | overwrite.allow
            ret.append(role)
        return ret

    @property
    def mention(self) -> str:
        """:class:`str`: The string that allows you to mention the channel."""
        return f'<#{self.id}>'

    @property
    def jump_url(self) -> str:
        """:class:`str`: Returns a URL that allows the client to jump to the channel."""
        return f'{utils.WEB_URL}/channels/{self.guild.id}/{self.id}'

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the channel's creation time in UTC."""
        return utils.snowflake_time(self.id)

    def overwrites_for(self, obj: Union[Role, User, Any]) -> PermissionOverwrite:
        """Returns the channel-specific overwrites for a member or a role.

        Parameters
        -----------
        obj: Union[:class:`~bisim.Role`, :class:`~bisim.abc.User`, :class:`~bisim.Object`]
            The role or user denoting whose overwrite to get.

        Returns
        ---------
        :class:`~bisim.PermissionOverwrite`
            The permission overwrites for this object.
        """
        from .role import Role

        predicate: Callable[[_Overwrites], bool]
        if isinstance(obj, Role):
            predicate = lambda p: p.is_role()
        else:
            predicate = lambda p: True

        for overwrite in filter(predicate, self._overwrites):
            if overwrite.id == obj.id:
                allow = Permissions(overwrite.allow)
                deny = Permissions(overwrite.deny)
                return PermissionOverwrite.from_pair(allow, deny)

        return PermissionOverwrite()

    @property
    def overwrites(self) -> Dict[Union[Role, Member, Any], PermissionOverwrite]:
        """Returns all of the channel's overwrites.

        This is returned as a dictionary where the key contains the target which
        can be either a :class:`~bisim.Role` or a :class:`~bisim.Member` and the value is the
        overwrite as a :class:`~bisim.PermissionOverwrite`.

        Bisim's server listing does not carry overwrites: this is empty until
        they are loaded with :meth:`fetch_overwrites` (the library loads them
        on its own before a permission check on another member).

        Returns
        --------
        Dict[Union[:class:`~bisim.Role`, :class:`~bisim.Member`, :class:`~bisim.Object`], :class:`~bisim.PermissionOverwrite`]
            The channel's permission overwrites.
        """
        from .object import Object
        from .role import Role

        ret: Dict[Any, PermissionOverwrite] = {}
        for ow in self._overwrites:
            allow = Permissions(ow.allow)
            deny = Permissions(ow.deny)
            overwrite = PermissionOverwrite.from_pair(allow, deny)
            target: Any = None
            if ow.is_role():
                target = self.guild.get_role(ow.id)
            elif ow.is_member():
                target = self.guild.get_member(ow.id)
            if target is None:
                from .member import Member

                target = Object(id=ow.id, type=Role if ow.is_role() else Member)  # type: ignore
            ret[target] = overwrite
        return ret

    @property
    def category(self) -> Optional[CategoryChannel]:
        """Optional[:class:`~bisim.CategoryChannel`]: The category this channel belongs to.

        If there is no category then this is ``None``.
        """
        if self.category_id is None:
            return None
        return self.guild.get_channel(self.category_id)  # type: ignore

    @property
    def permissions_synced(self) -> bool:
        """:class:`bool`: Whether or not the permissions for this channel are synced with the
        category it belongs to.

        If there is no category then this is ``False``.
        """
        if self.category_id is None:
            return False
        return self._permissions_synced

    def _apply_implicit_permissions(self, base: Permissions) -> None:
        # A channel nobody may send in cannot be used to mention, embed or attach.
        if not base.send_messages:
            base.send_tts_messages = False
            base.mention_everyone = False
            base.embed_links = False
            base.attach_files = False

    def permissions_for(self, obj: Union[Member, Role], /) -> Permissions:
        """Handles permission resolution for the :class:`~bisim.Member`
        or :class:`~bisim.Role`.

        This function takes into consideration the following cases:

        - Guild owner
        - Guild roles
        - Channel overrides
        - Member overrides
        - Implicit permissions
        - Member timeout

        If a :class:`~bisim.Role` is passed, then it checks the permissions
        someone with that role would have, which is essentially:

        - The default role permissions
        - The permissions of the role used as a parameter
        - The default role permission overwrites
        - The permission overwrites of the role used as a parameter

        For the bot itself, Bisim tells the library its permissions in each
        channel, and those are returned exactly. For other members the
        channel's overwrites are needed; see :meth:`fetch_overwrites`.

        Parameters
        ----------
        obj: Union[:class:`~bisim.Member`, :class:`~bisim.Role`]
            The object to resolve permissions for. This could be either
            a member or a role. If it's a role then member overwrites
            are not computed.

        Returns
        -------
        :class:`~bisim.Permissions`
            The resolved permissions for the member or role.
        """
        from .role import Role

        state = self._state
        guild = self.guild

        if (
            not isinstance(obj, Role)
            and state.self_id is not None
            and obj.id == state.self_id
            and self._my_permissions is not None
        ):
            return Permissions(self._my_permissions)

        if guild.owner_id == obj.id:
            return Permissions.all()

        default = guild.default_role
        if default is None:
            if state.self_id is not None and obj.id == state.self_id:
                return Permissions.none()
            return Permissions.none()
        base = Permissions(default._permissions)

        if isinstance(obj, Role):
            roles_ids = [obj.id] if obj.id != guild.id else []
            base.value |= obj._permissions
            member_id = None
            timed_out = False
        else:
            roles_ids = list(getattr(obj, '_roles', []))
            for role_id in roles_ids:
                role = guild.get_role(role_id)
                if role is not None:
                    base.value |= role._permissions
            member_id = obj.id
            is_timed_out = getattr(obj, 'is_timed_out', None)
            timed_out = bool(is_timed_out()) if callable(is_timed_out) else False

        if base.administrator:
            return Permissions.all()

        overwrites = {ow.id: ow for ow in self._overwrites}
        everyone = overwrites.get(guild.id)
        if everyone is not None:
            base.handle_overwrite(allow=everyone.allow, deny=everyone.deny)

        allow = 0
        deny = 0
        for ow in self._overwrites:
            if ow.is_role() and ow.id != guild.id and ow.id in roles_ids:
                allow |= ow.allow
                deny |= ow.deny
        base.handle_overwrite(allow=allow, deny=deny)

        if member_id is not None:
            member_ow = overwrites.get(member_id)
            if member_ow is not None and member_ow.is_member():
                base.handle_overwrite(allow=member_ow.allow, deny=member_ow.deny)

        if timed_out:
            base.value &= Permissions._timeout_mask()

        if not base.read_messages:
            denied = Permissions.all_channel()
            base.value &= ~denied.value

        self._apply_implicit_permissions(base)
        return base

    async def delete(self, *, reason: Optional[str] = None) -> None:
        """|coro|

        Deletes the channel.

        You must have :attr:`~bisim.Permissions.manage_channels` to do this.

        Parameters
        -----------
        reason: Optional[:class:`str`]
            The reason for deleting this channel.
            Shows up on the audit log.

        Raises
        -------
        ~bisim.Forbidden
            You do not have proper permissions to delete the channel.
        ~bisim.NotFound
            The channel was not found or was already deleted.
        ~bisim.HTTPException
            Deleting the channel failed.
        """
        await self._state.http.delete_channel(self.guild.id, self.id, reason=reason)

    async def set_permissions(
        self,
        target: Union[Member, Role, Any],
        *,
        overwrite: Optional[PermissionOverwrite] = utils.MISSING,
        reason: Optional[str] = None,
        **permissions: Optional[bool],
    ) -> None:
        r"""|coro|

        Sets the channel specific permission overwrites for a target in the
        channel.

        The ``target`` parameter should either be a :class:`~bisim.Member` or a
        :class:`~bisim.Role` that belongs to guild.

        The ``overwrite`` parameter, if given, must either be ``None`` or
        :class:`~bisim.PermissionOverwrite`. For convenience, you can pass in
        keyword arguments denoting :class:`~bisim.Permissions` attributes. If this is
        done, then you cannot mix the keyword arguments with the ``overwrite``
        parameter.

        If the ``overwrite`` parameter is ``None``, then the permission
        overwrites are deleted.

        You must have :attr:`~bisim.Permissions.manage_roles` to do this.

        .. note::

            This method *replaces* the old overwrites with the ones given.

        Examples
        ----------

        Setting allow and deny: ::

            await message.channel.set_permissions(message.author, read_messages=True,
                                                                  send_messages=False)

        Deleting overwrites ::

            await channel.set_permissions(member, overwrite=None)

        Using :class:`~bisim.PermissionOverwrite` ::

            overwrite = bisim.PermissionOverwrite()
            overwrite.send_messages = False
            overwrite.read_messages = True
            await channel.set_permissions(member, overwrite=overwrite)

        Parameters
        -----------
        target: Union[:class:`~bisim.Member`, :class:`~bisim.Role`]
            The member or role to overwrite permissions for.
        overwrite: Optional[:class:`~bisim.PermissionOverwrite`]
            The permissions to allow and deny to the target, or ``None`` to
            delete the overwrite.
        \*\*permissions
            A keyword argument list of permissions to set for ease of use.
            Cannot be mixed with ``overwrite``.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.

        Raises
        -------
        ~bisim.Forbidden
            You do not have permissions to edit channel specific permissions.
        ~bisim.HTTPException
            Editing channel specific permissions failed.
        ~bisim.NotFound
            The role or member being edited is not part of the guild.
        TypeError
            The ``overwrite`` parameter was invalid or the target type was not
            :class:`~bisim.Role` or :class:`~bisim.Member`.
        ValueError
            The ``target`` parameter was a :class:`~bisim.Role` that is not
            from this guild.
        """
        http = self._state.http
        perm_type = self._overwrite_type(target)
        from .role import Role

        if isinstance(target, Role) and target.guild.id != self.guild.id:
            raise ValueError('Target role must be from the same guild.')

        if overwrite is utils.MISSING:
            if len(permissions) == 0:
                raise TypeError('No overwrite provided.')
            try:
                overwrite = PermissionOverwrite(**permissions)
            except (ValueError, TypeError):
                raise TypeError('Invalid permissions given to keyword arguments.')
        else:
            if len(permissions) > 0:
                raise TypeError('Cannot mix overwrite and keyword arguments.')

        if overwrite is None:
            await http.delete_channel_permissions(self.guild.id, self.id, target.id, reason=reason)
            self._overwrites = [o for o in self._overwrites if o.id != target.id]
        elif isinstance(overwrite, PermissionOverwrite):
            (allow, deny) = overwrite.pair()
            await http.edit_channel_permissions(
                self.guild.id, self.id, target.id, allow.value, deny.value, perm_type, reason=reason
            )
            self._overwrites = [o for o in self._overwrites if o.id != target.id]
            self._overwrites.append(
                _Overwrites({'targetId': str(target.id), 'allow': str(allow.value), 'deny': str(deny.value), 'type': perm_type})
            )
        else:
            raise TypeError('Invalid overwrite type provided.')

    async def _clone_impl(
        self,
        base_attrs: Dict[str, Any],
        *,
        name: Optional[str] = None,
        category: Optional[Any] = utils.MISSING,
        reason: Optional[str] = None,
    ) -> Self:
        await self._ensure_overwrites()
        base_attrs['permissionOverwrites'] = [x._asdict() for x in self._overwrites]
        parent = self.category_id if category is utils.MISSING else (category.id if category else None)
        if parent is not None:
            base_attrs['parentId'] = str(parent)
        base_attrs['name'] = name or self.name
        channel_type = self.type.bisim_name
        base_attrs['type'] = channel_type
        data = await self._state.http.create_channel(self.guild.id, base_attrs, reason=reason)
        obj = self.__class__(state=self._state, guild=self.guild, data=data)  # type: ignore
        self.guild._channels[obj.id] = obj  # type: ignore
        return obj

    async def clone(
        self,
        *,
        name: Optional[str] = None,
        category: Optional[Any] = utils.MISSING,
        reason: Optional[str] = None,
    ) -> Self:
        """|coro|

        Clones this channel. This creates a channel with the same properties
        as this channel.

        You must have :attr:`~bisim.Permissions.manage_channels` to do this.

        Parameters
        ------------
        name: Optional[:class:`str`]
            The name of the new channel. If not provided, defaults to this
            channel name.
        category: Optional[:class:`~bisim.CategoryChannel`]
            The category the new channel belongs to.
        reason: Optional[:class:`str`]
            The reason for cloning this channel. Shows up on the audit log.

        Raises
        -------
        ~bisim.Forbidden
            You do not have the proper permissions to create this channel.
        ~bisim.HTTPException
            Creating the channel failed.

        Returns
        --------
        :class:`.abc.GuildChannel`
            The channel that was created.
        """
        raise NotImplementedError

    async def move(self, **kwargs: Any) -> None:
        """|coro|

        A rich interface to help move a channel relative to other channels.

        If exact position movement is required, ``edit`` should be used instead.

        You must have :attr:`~bisim.Permissions.manage_channels` to do this.

        .. note::

            Voice channels will always be sorted below text channels.
            This is a Bisim limitation.

        Parameters
        ------------
        beginning: :class:`bool`
            Whether to move the channel to the beginning of the
            channel list (or category if given).
            This is mutually exclusive with ``end``, ``before``, and ``after``.
        end: :class:`bool`
            Whether to move the channel to the end of the
            channel list (or category if given).
            This is mutually exclusive with ``beginning``, ``before``, and ``after``.
        before: :class:`~bisim.abc.Snowflake`
            The channel that should be before our current channel.
            This is mutually exclusive with ``beginning``, ``end``, and ``after``.
        after: :class:`~bisim.abc.Snowflake`
            The channel that should be after our current channel.
            This is mutually exclusive with ``beginning``, ``end``, and ``before``.
        offset: :class:`int`
            The number of channels to offset the move by. For example,
            an offset of ``2`` with ``beginning=True`` would move
            it 2 after the beginning. A positive number moves it below
            while a negative number moves it above. Note that this
            number is relative and computed after the ``beginning``,
            ``end``, ``before``, and ``after`` parameters.
        category: Optional[:class:`~bisim.abc.Snowflake`]
            The category to move this channel under.
            If ``None`` is given then it moves it out of the category.
            This parameter is ignored if moving a category channel.
        sync_permissions: :class:`bool`
            Whether to sync the permissions with the category (if given).
        reason: :class:`str`
            The reason for the move.

        Raises
        -------
        ValueError
            An invalid position was given.
        TypeError
            A bad mix of arguments were passed.
        Forbidden
            You do not have permissions to move the channel.
        HTTPException
            Moving the channel failed.
        """
        if not kwargs:
            return

        beginning, end = kwargs.get('beginning'), kwargs.get('end')
        before, after = kwargs.get('before'), kwargs.get('after')
        offset = kwargs.get('offset', 0)
        if sum(bool(a) for a in (beginning, end, before, after)) > 1:
            raise TypeError('Only one of [before, after, end, beginning] can be used.')

        bucket = self._sorting_bucket
        parent_id = kwargs.get('category', utils.MISSING)
        channels: List[GuildChannel]
        if parent_id not in (utils.MISSING, None):
            parent_id = parent_id.id
            channels = [
                ch for ch in self.guild.channels if ch._sorting_bucket == bucket and ch.category_id == parent_id
            ]
        else:
            channels = [
                ch for ch in self.guild.channels if ch._sorting_bucket == bucket and ch.category_id == self.category_id
            ]

        channels.sort(key=lambda c: (c.position, c.id))

        try:
            channels.remove(self)
        except ValueError:
            pass

        index: Optional[int] = None
        if beginning:
            index = 0
        elif end:
            index = len(channels)
        elif before:
            index = next((i for i, c in enumerate(channels) if c.id == before.id), None)
        elif after:
            index = next((i + 1 for i, c in enumerate(channels) if c.id == after.id), None)

        if index is None:
            raise ValueError('Could not resolve appropriate move position')

        channels.insert(max((index + offset), 0), self)
        payload = []
        lock_permissions = kwargs.get('sync_permissions', False)
        reason = kwargs.get('reason')
        for index, channel in enumerate(channels):
            d: Dict[str, Any] = {'id': str(channel.id), 'position': index}
            if parent_id is not utils.MISSING and channel.id == self.id:
                d['parentId'] = str(parent_id) if parent_id is not None else None
            elif channel.category_id is not None:
                d['parentId'] = str(channel.category_id)
            payload.append(d)

        await self._state.http.bulk_channel_update(self.guild.id, payload, reason=reason)
        if lock_permissions:
            await self._state.http.edit_channel(self.guild.id, self.id, permissionsSynced=True, reason=reason)

    async def create_invite(
        self,
        *,
        reason: Optional[str] = None,
        max_age: int = 0,
        max_uses: int = 0,
        temporary: bool = False,
        unique: bool = True,
        target_type: Any = None,
        target_user: Optional[User] = None,
        target_application_id: Optional[int] = None,
        guest: bool = False,
    ) -> Invite:
        """|coro|

        Creates an instant invite from a text or voice channel.

        You must have :attr:`~bisim.Permissions.create_instant_invite` to do this.

        Parameters
        ------------
        max_age: :class:`int`
            How long the invite should last in seconds. If it's 0 then the invite
            doesn't expire. Defaults to ``0``.
        max_uses: :class:`int`
            How many uses the invite could be used for. If it's 0 then there
            are unlimited uses. Defaults to ``0``.
        temporary: :class:`bool`
            Not supported on Bisim (must be ``False``).
        unique: :class:`bool`
            Accepted; Bisim always creates a new invite.
        reason: Optional[:class:`str`]
            The reason for creating this invite. Shows up on the audit log.

        Raises
        -------
        ~bisim.HTTPException
            Invite creation failed.
        ~bisim.NotFound
            The channel that was passed is a category or an invalid channel.
        NotSupported
            A temporary, targeted or guest invite was asked for.

        Returns
        --------
        :class:`~bisim.Invite`
            The invite that was created.
        """
        if temporary:
            raise NotSupported('Temporary membership invites')
        if target_type is not None or target_user is not None or target_application_id is not None:
            raise NotSupported('Targeted invites')
        if guest:
            raise NotSupported('Guest invites')

        data = await self._state.http.create_invite(
            self.guild.id, self.id, max_age=max_age, max_uses=max_uses, reason=reason
        )
        return Invite.from_incomplete(data=data, state=self._state)

    async def invites(self) -> List[Invite]:
        """|coro|

        Returns a list of all active instant invites from this channel.

        You must have :attr:`~bisim.Permissions.manage_channels` to get this information.

        Raises
        -------
        ~bisim.Forbidden
            You do not have proper permissions to get the information.
        ~bisim.HTTPException
            An error occurred while fetching the information.

        Returns
        -------
        List[:class:`~bisim.Invite`]
            The list of invites that are currently active.
        """
        state = self._state
        data = await state.http.invites_from(self.guild.id)
        return [
            Invite(state=state, data=invite, channel=self, guild=self.guild)
            for invite in data or []
            if utils._snowflake(invite.get('channelId')) == self.id
        ]


# ---------------------------------------------------------------------------
# Messageable
# ---------------------------------------------------------------------------


class _PinsIterator:
    """The result of :meth:`Messageable.pins`: iterate it with ``async for`` or ``await`` it for a list."""

    def __init__(self, iterator: AsyncIterator[Message]) -> None:
        self.__iterator = iterator

    def __await__(self) -> Generator[Any, None, List[Message]]:
        return self.__flatten().__await__()

    async def __flatten(self) -> List[Message]:
        return [message async for message in self.__iterator]

    def __aiter__(self) -> AsyncIterator[Message]:
        return self.__iterator

    async def __anext__(self) -> Message:
        return await self.__iterator.__anext__()


def _snowflake_of(value: Any, *, high: bool) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return utils.time_snowflake(value, high=high)
    return int(value.id)


class Messageable:
    """An ABC that details the common operations on a model that can send messages.

    The following classes implement this ABC:

    - :class:`~bisim.TextChannel`
    - :class:`~bisim.DMChannel`
    - :class:`~bisim.GroupChannel`
    - :class:`~bisim.PartialMessageable`
    - :class:`~bisim.User`
    - :class:`~bisim.Member`
    - :class:`~bisim.ext.commands.Context`
    """

    __slots__ = ()
    _state: ConnectionState

    async def _get_channel(self) -> MessageableChannel:
        raise NotImplementedError

    async def send(
        self,
        content: Optional[str] = None,
        *,
        tts: bool = False,
        embed: Optional[Embed] = None,
        embeds: Optional[Sequence[Embed]] = None,
        file: Optional[File] = None,
        files: Optional[Sequence[File]] = None,
        stickers: Optional[Sequence[Any]] = None,
        delete_after: Optional[float] = None,
        nonce: Optional[Union[str, int]] = None,
        allowed_mentions: Optional[AllowedMentions] = None,
        reference: Optional[Union[Message, MessageReference, PartialMessage]] = None,
        mention_author: Optional[bool] = None,
        view: Optional[View] = None,
        suppress_embeds: bool = False,
        silent: bool = False,
        poll: Optional[Poll] = None,
    ) -> Message:
        """|coro|

        Sends a message to the destination with the content given.

        The content must be a type that can convert to a string through ``str(content)``.
        If the content is set to ``None`` (the default), then the ``embed`` parameter must
        be provided.

        To upload a single file, the ``file`` parameter should be used with a
        single :class:`~bisim.File` object. To upload multiple files, the ``files``
        parameter should be used with a :class:`list` of :class:`~bisim.File` objects.
        **Specifying both parameters will lead to an exception**.

        To upload a single embed, the ``embed`` parameter should be used with a
        single :class:`~bisim.Embed` object. To upload multiple embeds, the ``embeds``
        parameter should be used with a :class:`list` of :class:`~bisim.Embed` objects.
        **Specifying both parameters will lead to an exception**.

        Parameters
        ------------
        content: Optional[:class:`str`]
            The content of the message to send. Up to 4000 characters.
        tts: :class:`bool`
            Accepted for compatibility; Bisim has no text to speech.
        embed: :class:`~bisim.Embed`
            The rich embed for the content.
        embeds: List[:class:`~bisim.Embed`]
            A list of embeds to upload. Must be a maximum of 10.
        file: :class:`~bisim.File`
            The file to upload.
        files: List[:class:`~bisim.File`]
            A list of files to upload. Must be a maximum of 10.
        nonce: :class:`int`
            The nonce to use for sending this message.
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent. If the deletion fails,
            then it is silently ignored.
        allowed_mentions: :class:`~bisim.AllowedMentions`
            Accepted for compatibility; Bisim does not filter mentions per message.
        reference: Union[:class:`~bisim.Message`, :class:`~bisim.MessageReference`, :class:`~bisim.PartialMessage`]
            A reference to the :class:`~bisim.Message` to which you are replying.
        mention_author: Optional[:class:`bool`]
            Accepted for compatibility.
        view: :class:`bisim.ui.View`
            A Bisim UI View to add to the message.
        stickers: Sequence[Union[:class:`~bisim.GuildSticker`, :class:`~bisim.StickerItem`]]
            A list of stickers to send with the message. Bisim sends a sticker as
            a whole message, so pass one.
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.
        silent: :class:`bool`
            Whether to suppress push and desktop notifications for the message.
        poll: :class:`~bisim.Poll`
            The poll to send with this message.

        Raises
        --------
        ~bisim.HTTPException
            Sending the message failed.
        ~bisim.Forbidden
            You do not have the proper permissions to send the message.
        ValueError
            The ``files`` or ``embeds`` list is not of the appropriate size.
        TypeError
            You specified both ``file`` and ``files``,
            or you specified both ``embed`` and ``embeds``,
            or the ``reference`` object is not a :class:`~bisim.Message`,
            :class:`~bisim.MessageReference` or :class:`~bisim.PartialMessage`.

        Returns
        ---------
        :class:`~bisim.Message`
            The message that was sent.
        """
        channel = await self._get_channel()
        state = self._state
        if embed is not None and embeds is not None:
            raise TypeError('Cannot mix embed and embeds keyword arguments.')
        if file is not None and files is not None:
            raise TypeError('Cannot mix file and files keyword arguments.')

        payload = await _message_payload(
            state,
            channel.id,
            content=content if content is not None else utils.MISSING,
            embed=embed if embed is not None else utils.MISSING,
            embeds=embeds if embeds is not None else utils.MISSING,
            file=file if file is not None else utils.MISSING,
            files=files if files is not None else utils.MISSING,
            view=view if view is not None else utils.MISSING,
            poll=poll,
            reference=reference,
            stickers=stickers,
            nonce=nonce,
            tts=tts,
            silent=silent,
            suppress_embeds=suppress_embeds,
        )
        if view is not None and not hasattr(view, '__bisim_ui_view__'):
            raise TypeError(f'view parameter must be View not {view.__class__.__name__}')

        data = await state.http.send_message(channel.id, payload)
        ret = state.create_message(channel=channel, data=data)
        if view is not None and not view.is_finished() and view.is_dispatchable():
            state.store_view(view, ret.id)
        if poll is not None:
            poll._update_from_message(ret)
        if delete_after is not None:
            await ret.delete(delay=delete_after)
        return ret

    def typing(self) -> Typing:
        """Returns an asynchronous context manager that allows you to send a typing indicator to
        the destination for an indefinite period of time, or 10 seconds if the context manager
        is called using ``await``.

        Example Usage: ::

            async with channel.typing():
                # simulate something heavy
                await asyncio.sleep(20)

            await channel.send('Done!')

        Example Usage: ::

            await channel.typing()
            # Do some computational magic for about 10 seconds
            await channel.send('Done!')
        """
        return Typing(self)

    async def fetch_message(self, id: int, /) -> Message:
        """|coro|

        Retrieves a single :class:`~bisim.Message` from the destination.

        Parameters
        ------------
        id: :class:`int`
            The message ID to look for.

        Raises
        --------
        ~bisim.NotFound
            The specified message was not found.
        ~bisim.Forbidden
            You do not have the permissions required to get a message.
        ~bisim.HTTPException
            Retrieving the message failed.

        Returns
        --------
        :class:`~bisim.Message`
            The message asked for.
        """
        channel = await self._get_channel()
        data = await self._state.http.get_message(channel.id, id)
        return self._state.create_message(channel=channel, data=data)

    def pins(
        self,
        *,
        limit: Optional[int] = 50,
        before: Optional[SnowflakeTime] = None,
        oldest_first: bool = False,
    ) -> _PinsIterator:
        """Retrieves an :term:`asynchronous iterator` of the pinned messages in the channel.

        For backwards compatibility, you can still retrieve a list of pinned
        messages by using ``await`` on the returned object.

        Examples
        ---------

        Usage ::

            counter = 0
            async for message in channel.pins(limit=250):
                counter += 1

        Flattening into a list: ::

            messages = [message async for message in channel.pins(limit=50)]
            # messages is now a list of Message...

        All parameters are optional.

        Parameters
        -----------
        limit: Optional[int]
            The number of pinned messages to retrieve. If ``None``, it retrieves
            every pinned message in the channel. Defaults to ``50``.
        before: Optional[Union[:class:`datetime.datetime`, :class:`.abc.Snowflake`]]
            Retrieve pinned messages before this time or snowflake.
        oldest_first: :class:`bool`
            If set to ``True``, return messages in oldest pin->newest pin order.
            Defaults to ``False``.

        Raises
        -------
        ~bisim.Forbidden
            You do not have the permission to retrieve pinned messages.
        ~bisim.HTTPException
            Retrieving the pinned messages failed.

        Yields
        -------
        :class:`~bisim.Message`
            The pinned message.
        """

        async def iterate() -> AsyncIterator[Message]:
            channel = await self._get_channel()
            state = self._state
            data = await state.http.pins_from(channel.id)
            messages = [state.create_message(channel=channel, data=m) for m in (data or [])]
            before_id = _snowflake_of(before, high=False)
            if before_id is not None:
                messages = [m for m in messages if m.id < before_id]
            messages.sort(key=lambda m: m.id, reverse=not oldest_first)
            if limit is not None:
                messages = messages[:limit]
            for message in messages:
                yield message

        return _PinsIterator(iterate())

    async def history(
        self,
        *,
        limit: Optional[int] = 100,
        before: Optional[SnowflakeTime] = None,
        after: Optional[SnowflakeTime] = None,
        around: Optional[SnowflakeTime] = None,
        oldest_first: Optional[bool] = None,
    ) -> AsyncIterator[Message]:
        """Returns an :term:`asynchronous iterator` that enables receiving the destination's message history.

        You must have :attr:`~bisim.Permissions.read_message_history` to do this.

        Examples
        ---------

        Usage ::

            counter = 0
            async for message in channel.history(limit=200):
                if message.author == client.user:
                    counter += 1

        Flattening into a list: ::

            messages = [message async for message in channel.history(limit=123)]
            # messages is now a list of Message...

        All parameters are optional.

        Parameters
        -----------
        limit: Optional[:class:`int`]
            The number of messages to retrieve.
            If ``None``, retrieves every message in the channel. Note, however,
            that this would make it a slow operation.
        before: Optional[Union[:class:`~bisim.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages before this date or message.
            If a datetime is provided, it is recommended to use a UTC aware datetime.
            If the datetime is naive, it is assumed to be local time.
        after: Optional[Union[:class:`~bisim.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages after this date or message.
            If a datetime is provided, it is recommended to use a UTC aware datetime.
            If the datetime is naive, it is assumed to be local time.
        around: Optional[Union[:class:`~bisim.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages around this date or message.
            If a datetime is provided, it is recommended to use a UTC aware datetime.
            If the datetime is naive, it is assumed to be local time.
            When using this argument, the maximum limit is 101. Note that if the limit is an
            even number then this will return at most limit + 1 messages.
        oldest_first: Optional[:class:`bool`]
            If set to ``True``, return messages in oldest->newest order. Defaults to ``True`` if
            ``after`` is specified, otherwise ``False``.

        Raises
        ------
        ~bisim.Forbidden
            You do not have permissions to get channel message history.
        ~bisim.HTTPException
            The request to get message history failed.

        Yields
        -------
        :class:`~bisim.Message`
            The message with the message data parsed.
        """
        channel = await self._get_channel()
        state = self._state
        http = state.http

        before_id = _snowflake_of(before, high=False)
        after_id = _snowflake_of(after, high=True)
        around_id = _snowflake_of(around, high=False)
        if oldest_first is None:
            oldest_first = after is not None

        if around_id is not None:
            if limit is None:
                raise ValueError('history does not support around with limit=None')
            if limit > 101:
                raise ValueError('history max limit 101 when specifying around parameter')
            data = await http.logs_from(channel.id, min(limit, 100), around=around_id)
            messages = sorted((state.create_message(channel=channel, data=m) for m in (data or [])), key=lambda m: m.id)
            if before_id is not None:
                messages = [m for m in messages if m.id < before_id]
            if after_id is not None:
                messages = [m for m in messages if m.id > after_id]
            if not oldest_first:
                messages.reverse()
            for message in messages:
                yield message
            return

        remaining = limit
        if oldest_first:
            cursor = after_id if after_id is not None else 0
            while remaining is None or remaining > 0:
                batch_size = 100 if remaining is None else min(remaining, 100)
                data = await http.logs_from(channel.id, batch_size, after=cursor)
                if not data:
                    return
                batch = sorted(data, key=lambda m: int(m['id']))
                done = len(data) < batch_size
                for raw in batch:
                    message_id = int(raw['id'])
                    if before_id is not None and message_id >= before_id:
                        return
                    yield state.create_message(channel=channel, data=raw)
                    if remaining is not None:
                        remaining -= 1
                        if remaining <= 0:
                            return
                cursor = int(batch[-1]['id'])
                if done:
                    return
        else:
            cursor_before = before_id
            while remaining is None or remaining > 0:
                batch_size = 100 if remaining is None else min(remaining, 100)
                data = await http.logs_from(channel.id, batch_size, before=cursor_before)
                if not data:
                    return
                batch = sorted(data, key=lambda m: int(m['id']), reverse=True)
                done = len(data) < batch_size
                for raw in batch:
                    message_id = int(raw['id'])
                    if after_id is not None and message_id <= after_id:
                        return
                    yield state.create_message(channel=channel, data=raw)
                    if remaining is not None:
                        remaining -= 1
                        if remaining <= 0:
                            return
                cursor_before = int(batch[-1]['id'])
                if done:
                    return


class Connectable(Protocol):
    """An ABC that details the common operations on a channel that can
    connect to a voice server.

    Bots cannot join voice on Bisim, so :meth:`connect` always raises
    :exc:`~bisim.NotSupported`.
    """

    __slots__ = ()

    async def connect(self, *, timeout: float = 30.0, reconnect: bool = True, cls: Any = None, self_deaf: bool = False, self_mute: bool = False) -> Any:
        """|coro|

        Not supported on Bisim: a bot cannot join voice.

        Raises
        -------
        NotSupported
            Always.
        """
        raise NotSupported('Joining voice channels as a bot')

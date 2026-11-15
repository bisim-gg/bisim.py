from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from . import utils
from .enums import AuditLogAction, AuditLogActionCategory, try_enum
from .mixins import Hashable
from .object import Object

if TYPE_CHECKING:
    from .guild import Guild
    from .member import Member
    from .user import User

__all__ = (
    'AuditLogDiff',
    'AuditLogChanges',
    'AuditLogEntry',
)

# Bisim names its audit actions; these are the ones with a Discord counterpart.
_BISIM_ACTIONS: Dict[str, AuditLogAction] = {
    'GUILD_UPDATE': AuditLogAction.guild_update,
    'CHANNEL_CREATE': AuditLogAction.channel_create,
    'CHANNEL_UPDATE': AuditLogAction.channel_update,
    'CHANNEL_DELETE': AuditLogAction.channel_delete,
    'CHANNEL_OVERWRITE_CREATE': AuditLogAction.overwrite_create,
    'CHANNEL_OVERWRITE_UPDATE': AuditLogAction.overwrite_update,
    'CHANNEL_OVERWRITE_DELETE': AuditLogAction.overwrite_delete,
    'CHANNEL_SYNC': AuditLogAction.channel_update,
    'MEMBER_KICK': AuditLogAction.kick,
    'MEMBER_BAN': AuditLogAction.ban,
    'MEMBER_UNBAN': AuditLogAction.unban,
    'MEMBER_UPDATE': AuditLogAction.member_update,
    'MEMBER_TIMEOUT': AuditLogAction.member_update,
    'MEMBER_TIMEOUT_REMOVE': AuditLogAction.member_update,
    'MEMBER_ROLE_UPDATE': AuditLogAction.member_role_update,
    'VOICE_MOVE': AuditLogAction.member_move,
    'VOICE_DISCONNECT': AuditLogAction.member_disconnect,
    'ROLE_CREATE': AuditLogAction.role_create,
    'ROLE_UPDATE': AuditLogAction.role_update,
    'ROLE_DELETE': AuditLogAction.role_delete,
    'INVITE_CREATE': AuditLogAction.invite_create,
    'INVITE_DELETE': AuditLogAction.invite_delete,
    'WEBHOOK_CREATE': AuditLogAction.webhook_create,
    'WEBHOOK_UPDATE': AuditLogAction.webhook_update,
    'WEBHOOK_DELETE': AuditLogAction.webhook_delete,
    'EMOJI_CREATE': AuditLogAction.emoji_create,
    'EMOJI_UPDATE': AuditLogAction.emoji_update,
    'EMOJI_DELETE': AuditLogAction.emoji_delete,
    'STICKER_CREATE': AuditLogAction.sticker_create,
    'STICKER_UPDATE': AuditLogAction.sticker_update,
    'STICKER_DELETE': AuditLogAction.sticker_delete,
    'SOUND_CREATE': AuditLogAction.soundboard_sound_create,
    'SOUND_UPDATE': AuditLogAction.soundboard_sound_update,
    'SOUND_DELETE': AuditLogAction.soundboard_sound_delete,
    'AUTOMOD_RULE_CREATE': AuditLogAction.automod_rule_create,
    'AUTOMOD_RULE_UPDATE': AuditLogAction.automod_rule_update,
    'AUTOMOD_RULE_DELETE': AuditLogAction.automod_rule_delete,
    'AUTOMOD_ACTION': AuditLogAction.automod_block_message,
    'MESSAGE_PIN': AuditLogAction.message_pin,
    'MESSAGE_UNPIN': AuditLogAction.message_unpin,
    'MESSAGE_DELETE': AuditLogAction.message_delete,
    'MESSAGE_BULK_DELETE': AuditLogAction.message_bulk_delete,
    'BOT_ADD': AuditLogAction.bot_add,
}


class AuditLogDiff:
    """Represents an audit log "change" object (a plain bag of attributes)."""

    def __len__(self) -> int:
        return len(self.__dict__)

    def __iter__(self) -> Any:
        yield from self.__dict__.items()

    def __repr__(self) -> str:
        values = ' '.join('%s=%r' % item for item in self.__dict__.items())
        return f'<AuditLogDiff {values}>'

    def __getattr__(self, item: str) -> Any:
        return None


class AuditLogChanges:
    """An audit log change set, with :attr:`before` and :attr:`after`."""

    def __init__(self, meta: Optional[Dict[str, Any]]):
        self.before: AuditLogDiff = AuditLogDiff()
        self.after: AuditLogDiff = AuditLogDiff()
        if not isinstance(meta, dict):
            return
        changes = meta.get('changes') if isinstance(meta.get('changes'), dict) else meta
        for key, value in changes.items():
            if isinstance(value, dict) and ('before' in value or 'after' in value):
                setattr(self.before, key, value.get('before'))
                setattr(self.after, key, value.get('after'))
            else:
                setattr(self.after, key, value)

    def __repr__(self) -> str:
        return f'<AuditLogChanges before={self.before!r} after={self.after!r}>'


class AuditLogEntry(Hashable):
    r"""Represents an Audit Log entry.

    You retrieve these via :meth:`Guild.audit_logs`, and receive new ones in
    :func:`on_audit_log_entry_create`.

    .. container:: operations

        .. describe:: x == y

            Checks if two entries are equal.

        .. describe:: x != y

            Checks if two entries are not equal.

        .. describe:: hash(x)

            Returns the entry's hash.

    Attributes
    -----------
    action: :class:`AuditLogAction`
        The action that was done. Bisim actions with no Discord counterpart
        come back as an unknown value whose ``name`` is ``unknown_<BISIM_NAME>``.
    user: Optional[:class:`abc.User`]
        The user who initiated this action.
    user_id: Optional[:class:`int`]
        The user ID who initiated this action.
    id: :class:`int`
        The entry ID.
    guild: :class:`Guild`
        The guild that this entry belongs to.
    target: Any
        The target that got changed, resolved from the cache when possible.
    reason: Optional[:class:`str`]
        The reason this action was done.
    extra: Any
        Extra information that this entry has (Bisim's raw ``meta``).
    bisim_action: :class:`str`
        Bisim's own name for the action (``MEMBER_BAN``...).
    """

    def __init__(self, *, guild: Guild, data: Dict[str, Any]) -> None:
        self.guild: Guild = guild
        self._state = guild._state
        self.id: int = int(data['id'])
        self.bisim_action: str = data.get('action') or ''
        action = _BISIM_ACTIONS.get(self.bisim_action.upper())
        self.action: AuditLogAction = action if action is not None else try_enum(AuditLogAction, self.bisim_action)
        # REST gives ``actorId`` and ``meta``; GUILD_AUDIT_LOG_ENTRY_CREATE gives ``userId`` and ``metaJson``.
        self.user_id: Optional[int] = utils._snowflake(data.get('actorId') or data.get('userId'))
        actor = data.get('actor')
        user: Optional[Union[User, Member]] = None
        if self.user_id is not None:
            user = guild.get_member(self.user_id) or self._state.get_user(self.user_id)
            if user is None and isinstance(actor, dict) and actor.get('id'):
                user = self._state.create_user(actor)
        self.user: Optional[Union[User, Member]] = user
        meta = data.get('meta')
        if meta is None and data.get('metaJson'):
            try:
                meta = utils._from_json(data['metaJson'])
            except ValueError:
                meta = None
        self.extra: Any = meta
        self.reason: Optional[str] = (meta.get('reason') if isinstance(meta, dict) else None) or data.get('reason') or None
        self._target_type: Optional[str] = data.get('targetType')
        self._target_id: Optional[int] = utils._snowflake(data.get('targetId'))
        self._created_at = utils.parse_time(data.get('createdAt'))
        self._changes = AuditLogChanges(meta if isinstance(meta, dict) else None)

    def __repr__(self) -> str:
        return f'<AuditLogEntry id={self.id} action={self.action} user={self.user!r}>'

    @property
    def created_at(self) -> datetime.datetime:
        """:class:`datetime.datetime`: Returns the entry's creation time in UTC."""
        return self._created_at or utils.snowflake_time(self.id)

    @property
    def target(self) -> Any:
        """The target that got changed (a channel, role, member, user or :class:`Object`)."""
        if self._target_id is None:
            return None
        target_type = (self._target_type or '').upper()
        guild = self.guild
        if target_type in ('CHANNEL', 'OVERWRITE'):
            return guild.get_channel(self._target_id) or Object(id=self._target_id)
        if target_type == 'ROLE':
            return guild.get_role(self._target_id) or Object(id=self._target_id)
        if target_type in ('USER', 'MEMBER'):
            return guild.get_member(self._target_id) or self._state.get_user(self._target_id) or Object(id=self._target_id)
        if target_type == 'GUILD':
            return guild
        return Object(id=self._target_id)

    @property
    def category(self) -> Optional[AuditLogActionCategory]:
        """Optional[:class:`AuditLogActionCategory`]: The category of the action, if applicable."""
        return getattr(self.action, 'category', None)

    @property
    def changes(self) -> AuditLogChanges:
        """:class:`AuditLogChanges`: The list of changes this entry has."""
        return self._changes

    @property
    def before(self) -> AuditLogDiff:
        """:class:`AuditLogDiff`: The target's prior state."""
        return self._changes.before

    @property
    def after(self) -> AuditLogDiff:
        """:class:`AuditLogDiff`: The target's subsequent state."""
        return self._changes.after

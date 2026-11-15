"""AutoMod: a server's rules and what they did, with discord.py's classes.

Bisim describes a rule in its own words (``triggerType`` ``KEYWORD``,
``eventType`` ``MESSAGE_SEND``, presets ``PROFANITY``...) and keeps its
actions as fields (``blockMessage``, ``alertChannelId``, ``timeoutSec``). This
module turns them into Discord's numbers and :class:`AutoModRuleAction` lists.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Set

from . import utils
from .enums import AutoModRuleActionType, AutoModRuleEventType, AutoModRuleTriggerType, try_enum
from .flags import AutoModPresets
from .utils import MISSING

if TYPE_CHECKING:
    from typing_extensions import Self

    from .abc import GuildChannel, Snowflake
    from .guild import Guild
    from .member import Member
    from .role import Role
    from .state import ConnectionState

__all__ = (
    'AutoModRuleAction',
    'AutoModTrigger',
    'AutoModRule',
    'AutoModAction',
)


class AutoModRuleAction:
    """Represents an auto moderation's rule action.

    .. note::
        Only one of ``channel_id``, ``duration``, or ``custom_message`` can be used.

    Attributes
    -----------
    type: :class:`AutoModRuleActionType`
        The type of action to take.
        Defaults to :attr:`~AutoModRuleActionType.block_message`.
    channel_id: Optional[:class:`int`]
        The ID of the channel to send the alert message to, if any.
        Passing this sets :attr:`type` to :attr:`~AutoModRuleActionType.send_alert_message`.
    duration: Optional[:class:`datetime.timedelta`]
        The duration of the timeout to apply, if any.
        Has a maximum of 28 days.
        Passing this sets :attr:`type` to :attr:`~AutoModRuleActionType.timeout`.
    custom_message: Optional[:class:`str`]
        A custom message which will be shown to a user when their message is blocked.
        Passing this sets :attr:`type` to :attr:`~AutoModRuleActionType.block_message`.
    """

    __slots__ = ('type', 'channel_id', 'duration', 'custom_message')

    def __init__(
        self,
        *,
        type: Optional[AutoModRuleActionType] = None,
        channel_id: Optional[int] = None,
        duration: Optional[datetime.timedelta] = None,
        custom_message: Optional[str] = None,
    ) -> None:
        if sum(v is None for v in (channel_id, duration, custom_message)) < 2:
            raise ValueError('Only one of channel_id, duration, or custom_message can be passed.')

        self.type: AutoModRuleActionType
        self.channel_id: Optional[int] = None
        self.duration: Optional[datetime.timedelta] = None
        self.custom_message: Optional[str] = None

        if type is not None:
            self.type = type
        elif channel_id is not None:
            self.type = AutoModRuleActionType.send_alert_message
        elif duration is not None:
            self.type = AutoModRuleActionType.timeout
        else:
            self.type = AutoModRuleActionType.block_message

        if self.type is AutoModRuleActionType.send_alert_message:
            if channel_id is None:
                raise ValueError('channel_id cannot be None if type is send_alert_message')
            self.channel_id = channel_id

        if self.type is AutoModRuleActionType.timeout:
            if duration is None:
                raise ValueError('duration cannot be None set if type is timeout')
            self.duration = duration

        if self.type is AutoModRuleActionType.block_message:
            self.custom_message = custom_message

    def __repr__(self) -> str:
        return f'<AutoModRuleAction type={self.type.value} channel={self.channel_id} duration={self.duration}>'

    @classmethod
    def _from_execution(cls, data: Dict[str, Any]) -> Self:
        # AUTO_MODERATION_ACTION_EXECUTION: Discord's action numbers, the details beside them.
        kind = utils._int(data.get('actionType'), 1)
        if kind == AutoModRuleActionType.timeout.value:
            return cls(duration=datetime.timedelta(seconds=utils._int(data.get('durationSeconds'), 0)))
        if kind == AutoModRuleActionType.send_alert_message.value:
            channel_id = utils._snowflake(data.get('alertChannelId'))
            if channel_id is not None:
                return cls(channel_id=channel_id)
            return cls(type=AutoModRuleActionType.send_alert_message, channel_id=0)
        if kind == AutoModRuleActionType.block_message.value:
            return cls(type=AutoModRuleActionType.block_message, custom_message=data.get('customMessage') or None)
        return cls(type=try_enum(AutoModRuleActionType, kind))

    @classmethod
    def _from_rule(cls, data: Dict[str, Any]) -> List[Self]:
        # A Bisim rule keeps its actions as fields.
        actions: List[Self] = []
        if data.get('blockMessage'):
            actions.append(cls(type=AutoModRuleActionType.block_message, custom_message=data.get('blockReason') or None))
        channel_id = utils._snowflake(data.get('alertChannelId'))
        if channel_id is not None:
            actions.append(cls(channel_id=channel_id))
        seconds = utils._int(data.get('timeoutSec'), 0)
        if seconds > 0:
            actions.append(cls(duration=datetime.timedelta(seconds=seconds)))
        return actions

    def to_dict(self) -> Dict[str, Any]:
        ret: Dict[str, Any] = {'type': self.type.value, 'metadata': {}}
        if self.type is AutoModRuleActionType.block_message and self.custom_message is not None:
            ret['metadata'] = {'custom_message': self.custom_message}
        elif self.type is AutoModRuleActionType.timeout:
            ret['metadata'] = {'duration_seconds': int(self.duration.total_seconds())}  # type: ignore
        elif self.type is AutoModRuleActionType.send_alert_message:
            ret['metadata'] = {'channel_id': str(self.channel_id)}
        return ret


def _actions_to_bisim(actions: Sequence[AutoModRuleAction]) -> Dict[str, Any]:
    block = next((a for a in actions if a.type is AutoModRuleActionType.block_message), None)
    alert = next((a for a in actions if a.type is AutoModRuleActionType.send_alert_message), None)
    timeout = next((a for a in actions if a.type is AutoModRuleActionType.timeout), None)
    return {
        'blockMessage': block is not None,
        'blockReason': (block.custom_message or '') if block is not None else '',
        'alertChannelId': str(alert.channel_id) if alert is not None and alert.channel_id else '',
        'timeoutSec': int(timeout.duration.total_seconds()) if timeout is not None and timeout.duration else 0,
    }


class AutoModTrigger:
    r"""Represents a trigger for an auto moderation rule.

    The following table illustrates relevant attributes for each :class:`AutoModRuleTriggerType`:

    +-----------------------------------------------+------------------------------------------------+
    |                    Type                       |                   Attributes                   |
    +===============================================+================================================+
    | :attr:`AutoModRuleTriggerType.keyword`        | :attr:`keyword_filter`, :attr:`regex_patterns`,|
    |                                               | :attr:`allow_list`                             |
    +-----------------------------------------------+------------------------------------------------+
    | :attr:`AutoModRuleTriggerType.spam`           |                                                |
    +-----------------------------------------------+------------------------------------------------+
    | :attr:`AutoModRuleTriggerType.keyword_preset` | :attr:`presets`\, :attr:`allow_list`           |
    +-----------------------------------------------+------------------------------------------------+
    | :attr:`AutoModRuleTriggerType.mention_spam`   | :attr:`mention_limit`                          |
    +-----------------------------------------------+------------------------------------------------+

    Attributes
    -----------
    type: :class:`AutoModRuleTriggerType`
        The type of trigger.
    keyword_filter: List[:class:`str`]
        The list of strings that will trigger the filter.

        This could be combined with :attr:`regex_patterns`.
    regex_patterns: List[:class:`str`]
        The regex pattern that will trigger the filter.

        This could be combined with :attr:`keyword_filter` and/or :attr:`allow_list`
    presets: :class:`AutoModPresets`
        The presets used with the preset keyword filter.
    allow_list: List[:class:`str`]
        The list of words that are exempt from the commonly flagged words.
    mention_limit: :class:`int`
        The total number of user and role mentions a message can contain.
    mention_raid_protection: :class:`bool`
        Always ``False``: Bisim has no mention raid protection.
    """

    __slots__ = (
        'type',
        'keyword_filter',
        'presets',
        'allow_list',
        'mention_limit',
        'regex_patterns',
        'mention_raid_protection',
    )

    def __init__(
        self,
        *,
        type: Optional[AutoModRuleTriggerType] = None,
        keyword_filter: Optional[List[str]] = None,
        presets: Optional[AutoModPresets] = None,
        allow_list: Optional[List[str]] = None,
        mention_limit: Optional[int] = None,
        regex_patterns: Optional[List[str]] = None,
        mention_raid_protection: Optional[bool] = None,
    ) -> None:
        unique_args = (keyword_filter or regex_patterns, presets, mention_limit or mention_raid_protection)
        if type is None and sum(arg is not None for arg in unique_args) > 1:
            raise ValueError(
                'Please pass only one of keyword_filter/regex_patterns, presets, or mention_limit/mention_raid_protection.'
            )

        if type is not None:
            self.type = type
        elif keyword_filter is not None or regex_patterns is not None:
            self.type = AutoModRuleTriggerType.keyword
        elif presets is not None:
            self.type = AutoModRuleTriggerType.keyword_preset
        elif mention_limit is not None or mention_raid_protection is not None:
            self.type = AutoModRuleTriggerType.mention_spam
        else:
            raise ValueError(
                'Please pass the trigger type explicitly if not using keyword_filter, regex_patterns, presets, mention_limit, or mention_raid_protection.'
            )

        self.keyword_filter: List[str] = keyword_filter if keyword_filter is not None else []
        self.presets: AutoModPresets = presets if presets is not None else AutoModPresets()
        self.allow_list: List[str] = allow_list if allow_list is not None else []
        self.mention_limit: int = mention_limit if mention_limit is not None else 0
        self.mention_raid_protection: bool = mention_raid_protection if mention_raid_protection is not None else False
        self.regex_patterns: List[str] = regex_patterns if regex_patterns is not None else []

    def __repr__(self) -> str:
        data = self.to_metadata_dict()
        if data:
            joined = ' '.join(f'{k}={v!r}' for k, v in data.items())
            return f'<AutoModTrigger type={self.type} {joined}>'

        return f'<AutoModTrigger type={self.type}>'

    @classmethod
    def _from_rule(cls, data: Dict[str, Any]) -> Self:
        type_ = AutoModRuleTriggerType.from_bisim(data.get('triggerType'))
        # Bisim stores a profile rule as a KEYWORD rule on MEMBER_UPDATE; Discord calls it member_profile (6).
        if type_ is AutoModRuleTriggerType.keyword and str(data.get('eventType') or '').upper() == 'MEMBER_UPDATE':
            type_ = AutoModRuleTriggerType.member_profile
        if type_ in (AutoModRuleTriggerType.keyword, AutoModRuleTriggerType.member_profile):
            return cls(
                type=type_,
                keyword_filter=list(data.get('keywords') or []),
                regex_patterns=list(data.get('regexPatterns') or []),
                allow_list=list(data.get('allowList') or []),
            )
        if type_ is AutoModRuleTriggerType.keyword_preset:
            return cls(
                type=type_,
                presets=AutoModPresets._from_bisim(data.get('presets') or []),
                allow_list=list(data.get('allowList') or []),
            )
        if type_ is AutoModRuleTriggerType.mention_spam:
            return cls(type=type_, mention_limit=utils._int(data.get('mentionLimit'), 0))
        return cls(type=type_)

    def to_metadata_dict(self) -> Optional[Dict[str, Any]]:
        if self.type in (AutoModRuleTriggerType.keyword, AutoModRuleTriggerType.member_profile):
            return {
                'keyword_filter': self.keyword_filter,
                'regex_patterns': self.regex_patterns,
                'allow_list': self.allow_list,
            }
        elif self.type is AutoModRuleTriggerType.keyword_preset:
            return {'presets': self.presets.to_array(), 'allow_list': self.allow_list}
        elif self.type is AutoModRuleTriggerType.mention_spam:
            return {
                'mention_total_limit': self.mention_limit,
                'mention_raid_protection_enabled': self.mention_raid_protection,
            }
        return None

    def _to_bisim(self) -> Dict[str, Any]:
        if self.type in (AutoModRuleTriggerType.keyword, AutoModRuleTriggerType.member_profile):
            return {'keywords': self.keyword_filter, 'regexPatterns': self.regex_patterns, 'allowList': self.allow_list}
        if self.type is AutoModRuleTriggerType.keyword_preset:
            return {'presets': self.presets._to_bisim(), 'allowList': self.allow_list}
        if self.type is AutoModRuleTriggerType.mention_spam:
            return {'mentionLimit': self.mention_limit}
        return {}


class AutoModRule:
    """Represents an auto moderation rule.

    Attributes
    -----------
    id: :class:`int`
        The ID of the rule.
    guild: :class:`Guild`
        The guild the rule is for.
    name: :class:`str`
        The name of the rule.
    creator_id: Optional[:class:`int`]
        The ID of the user that created the rule.
    trigger: :class:`AutoModTrigger`
        The rule's trigger.
    enabled: :class:`bool`
        Whether the rule is enabled.
    exempt_role_ids: Set[:class:`int`]
        The IDs of the roles that are exempt from the rule.
    exempt_channel_ids: Set[:class:`int`]
        The IDs of the channels that are exempt from the rule.
    event_type: :class:`AutoModRuleEventType`
        The type of event that will trigger the the rule.
    """

    __slots__ = (
        '_state',
        'id',
        'guild',
        'name',
        'creator_id',
        'event_type',
        'trigger',
        'enabled',
        'exempt_role_ids',
        'exempt_channel_ids',
        '_actions',
    )

    def __init__(self, *, data: Dict[str, Any], guild: Guild, state: ConnectionState) -> None:
        self._state: ConnectionState = state
        self.guild: Guild = guild
        self.id: int = int(data['id'])
        self.name: str = data.get('name') or ''
        self.creator_id: Optional[int] = utils._snowflake(data.get('creatorId'))
        self.event_type: AutoModRuleEventType = AutoModRuleEventType.from_bisim(data.get('eventType'))
        self.trigger: AutoModTrigger = AutoModTrigger._from_rule(data)
        self.enabled: bool = bool(data.get('enabled', False))
        self.exempt_role_ids: Set[int] = {int(role_id) for role_id in data.get('exemptRoles') or []}
        self.exempt_channel_ids: Set[int] = {int(channel_id) for channel_id in data.get('exemptChannels') or []}
        self._actions: List[AutoModRuleAction] = AutoModRuleAction._from_rule(data)

    def __repr__(self) -> str:
        return f'<AutoModRule id={self.id} name={self.name!r} guild={self.guild!r}>'

    def to_dict(self) -> Dict[str, Any]:
        """The rule in Discord's shape."""
        return {
            'id': str(self.id),
            'guild_id': str(self.guild.id),
            'name': self.name,
            'creator_id': str(self.creator_id) if self.creator_id is not None else None,
            'event_type': self.event_type.value,
            'trigger_type': self.trigger.type.value,
            'trigger_metadata': self.trigger.to_metadata_dict(),
            'actions': [action.to_dict() for action in self.actions],
            'enabled': self.enabled,
            'exempt_roles': [str(role_id) for role_id in self.exempt_role_ids],
            'exempt_channels': [str(channel_id) for channel_id in self.exempt_channel_ids],
        }

    @property
    def creator(self) -> Optional[Member]:
        """Optional[:class:`Member`]: The member that created this rule."""
        if self.creator_id is None:
            return None
        return self.guild.get_member(self.creator_id)

    @property
    def exempt_roles(self) -> List[Role]:
        """List[:class:`Role`]: The roles that are exempt from this rule."""
        result = []
        get_role = self.guild.get_role
        for role_id in self.exempt_role_ids:
            role = get_role(role_id)
            if role is not None:
                result.append(role)

        return utils._unique(result)

    @property
    def exempt_channels(self) -> List[GuildChannel]:
        """List[:class:`abc.GuildChannel`]: The channels that are exempt from this rule."""
        it = filter(None, map(self.guild._resolve_channel, self.exempt_channel_ids))
        return utils._unique(it)

    @property
    def actions(self) -> List[AutoModRuleAction]:
        """List[:class:`AutoModRuleAction`]: The actions that are taken when this rule is triggered."""
        return list(self._actions)

    def is_exempt(self, obj: Snowflake, /) -> bool:
        """Check if an object is exempt from the automod rule.

        Parameters
        -----------
        obj: :class:`abc.Snowflake`
            The role or channel to check.

        Returns
        --------
        :class:`bool`
            Whether the object is exempt from the automod rule.
        """
        return obj.id in self.exempt_channel_ids or obj.id in self.exempt_role_ids

    async def edit(
        self,
        *,
        name: str = MISSING,
        event_type: AutoModRuleEventType = MISSING,
        actions: List[AutoModRuleAction] = MISSING,
        trigger: AutoModTrigger = MISSING,
        enabled: bool = MISSING,
        exempt_roles: Sequence[Snowflake] = MISSING,
        exempt_channels: Sequence[Snowflake] = MISSING,
        reason: str = MISSING,
    ) -> Self:
        """|coro|

        Edits this auto moderation rule.

        You must have :attr:`Permissions.manage_guild` to edit rules.

        Parameters
        -----------
        name: :class:`str`
            The new name to change to.
        event_type: :class:`AutoModRuleEventType`
            Bisim fixes a rule's event when it is made: passing a different one
            raises :exc:`ValueError`.
        actions: List[:class:`AutoModRuleAction`]
            The new rule actions to update. Bisim keeps one action of each type.
        trigger: :class:`AutoModTrigger`
            The new trigger to update.
            You can only change the trigger metadata, not the type.
        enabled: :class:`bool`
            Whether the rule should be enabled or not.
        exempt_roles: Sequence[:class:`abc.Snowflake`]
            The new roles to exempt from the rule.
        exempt_channels: Sequence[:class:`abc.Snowflake`]
            The new channels to exempt from the rule.
        reason: :class:`str`
            The reason for updating this rule. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permission to edit this rule.
        HTTPException
            Editing the rule failed.

        Returns
        --------
        :class:`AutoModRule`
            The updated auto moderation rule.
        """
        payload: Dict[str, Any] = {}
        if actions is not MISSING:
            payload.update(_actions_to_bisim(actions))

        if name is not MISSING:
            payload['name'] = name

        if event_type is not MISSING and event_type is not self.event_type:
            raise ValueError('Bisim cannot change the event of a rule; make a new rule instead.')

        if trigger is not MISSING:
            payload.update(trigger._to_bisim())

        if enabled is not MISSING:
            payload['enabled'] = enabled

        if exempt_roles is not MISSING:
            payload['exemptRoles'] = [str(x.id) for x in exempt_roles]

        if exempt_channels is not MISSING:
            payload['exemptChannels'] = [str(x.id) for x in exempt_channels]

        data = await self._state.http.edit_auto_moderation_rule(
            self.guild.id,
            self.id,
            reason=reason if reason is not MISSING else None,
            **payload,
        )

        return self.__class__(data=data, guild=self.guild, state=self._state)

    async def delete(self, *, reason: str = MISSING) -> None:
        """|coro|

        Deletes the auto moderation rule.

        You must have :attr:`Permissions.manage_guild` to delete rules.

        Parameters
        -----------
        reason: :class:`str`
            The reason for deleting this rule. Shows up on the audit log.

        Raises
        -------
        Forbidden
            You do not have permissions to delete the rule.
        HTTPException
            Deleting the rule failed.
        """
        await self._state.http.delete_auto_moderation_rule(
            self.guild.id, self.id, reason=reason if reason is not MISSING else None
        )


class AutoModAction:
    """Represents an action that was taken as the result of a moderation rule.

    Attributes
    -----------
    action: :class:`AutoModRuleAction`
        The action that was taken.
    message_id: Optional[:class:`int`]
        Always ``None``: on Bisim a blocked message never existed.
    rule_id: :class:`int`
        The ID of the rule that was triggered.
    rule_trigger_type: :class:`AutoModRuleTriggerType`
        The trigger type of the rule that was triggered.
    guild_id: :class:`int`
        The ID of the guild where the rule was triggered.
    user_id: :class:`int`
        The ID of the user that triggered the rule.
    channel_id: Optional[:class:`int`]
        The ID of the channel where the rule was triggered, ``None`` for a
        profile rule (:attr:`AutoModRuleEventType.member_update`).
    alert_system_message_id: Optional[:class:`int`]
        The ID of the system message that was sent to the predefined alert channel.
    content: :class:`str`
        The content of the message that triggered the rule.
        Requires the :attr:`Intents.message_content` or it will always return an empty string.
    matched_keyword: Optional[:class:`str`]
        The matched keyword from the triggering message.
    matched_content: Optional[:class:`str`]
        The matched content from the triggering message.
        Requires the :attr:`Intents.message_content` or it will always return ``None``.
    """

    __slots__ = (
        '_state',
        'action',
        'rule_id',
        'rule_trigger_type',
        'guild_id',
        'user_id',
        'channel_id',
        'message_id',
        'alert_system_message_id',
        'content',
        'matched_keyword',
        'matched_content',
    )

    def __init__(self, *, data: Dict[str, Any], state: ConnectionState) -> None:
        self._state: ConnectionState = state
        self.message_id: Optional[int] = utils._snowflake(data.get('messageId'))
        self.action: AutoModRuleAction = AutoModRuleAction._from_execution(data)
        self.rule_id: int = int(data['ruleId'])
        self.rule_trigger_type: AutoModRuleTriggerType = AutoModRuleTriggerType.from_bisim(data.get('ruleTriggerType'))
        # A keyword match with no channel is a profile rule's (Discord's member_profile, 6).
        if self.rule_trigger_type is AutoModRuleTriggerType.keyword and not data.get('channelId'):
            self.rule_trigger_type = AutoModRuleTriggerType.member_profile
        self.guild_id: int = int(data['guildId'])
        self.channel_id: Optional[int] = utils._snowflake(data.get('channelId'))
        self.user_id: int = int(data['userId'])
        self.alert_system_message_id: Optional[int] = utils._snowflake(data.get('alertSystemMessageId'))
        self.content: str = data.get('content') or ''
        self.matched_keyword: Optional[str] = data.get('matchedKeyword') or None
        self.matched_content: Optional[str] = data.get('matchedContent') or None

    def __repr__(self) -> str:
        return f'<AutoModRuleExecution rule_id={self.rule_id} action={self.action!r}>'

    @property
    def guild(self) -> Guild:
        """:class:`Guild`: The guild this action was taken in."""
        return self._state._get_guild(self.guild_id)  # type: ignore

    @property
    def channel(self) -> Optional[GuildChannel]:
        """Optional[:class:`abc.GuildChannel`]: The channel this action was taken in."""
        guild = self.guild
        if self.channel_id and guild is not None:
            return guild.get_channel(self.channel_id)
        return None

    @property
    def member(self) -> Optional[Member]:
        """Optional[:class:`Member`]: The member this action was taken against /who triggered this rule."""
        guild = self.guild
        if guild is None:
            return None
        return guild.get_member(self.user_id)

    async def fetch_rule(self) -> AutoModRule:
        """|coro|

        Fetch the rule whose action was taken.

        You must have :attr:`Permissions.manage_guild` to do this.

        Raises
        -------
        Forbidden
            You do not have permissions to view the rule.
        HTTPException
            Fetching the rule failed.

        Returns
        --------
        :class:`AutoModRule`
            The rule that was executed.
        """
        data = await self._state.http.get_auto_moderation_rule(self.guild_id, self.rule_id)
        return AutoModRule(data=data, guild=self.guild, state=self._state)

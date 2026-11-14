from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, TypeVar, Union

from .. import utils
from ..enums import AppCommandOptionType, AppCommandType, ChannelType, Locale, try_enum
from ..errors import NotSupported
from ..flags import AppCommandContext, AppInstallationType
from ..mixins import Hashable
from ..object import Object
from ..permissions import Permissions
from .translator import TranslationContext, TranslationContextLocation, Translator, locale_str

if TYPE_CHECKING:
    from ..guild import Guild
    from ..state import ConnectionState

__all__ = (
    'AppCommand',
    'AppCommandGroup',
    'AppCommandChannel',
    'AppCommandThread',
    'AppCommandPermissions',
    'GuildAppCommandPermissions',
    'Argument',
    'Choice',
    'AllChannels',
)

ChoiceT = TypeVar('ChoiceT', str, int, float, Union[str, int, float])


def is_app_command_argument_type(value: int) -> bool:
    return 11 >= value >= 3


class AllChannels:
    """Represents all channels for application command permissions (not on Bisim)."""

    __slots__ = ('guild',)

    def __init__(self, guild: Guild):
        self.guild: Guild = guild

    @property
    def id(self) -> int:
        """:class:`int`: The ID sentinel used to represent all channels. Equivalent to the guild's ID minus 1."""
        return self.guild.id - 1

    def __repr__(self) -> str:
        return f'<AllChannels guild={self.guild}>'


def _localizations(data: Dict[str, Any], key: str) -> Dict[Locale, str]:
    raw = data.get(key) or {}
    if not isinstance(raw, dict):
        return {}
    return {try_enum(Locale, k): v for k, v in raw.items()}


class Choice(Generic[ChoiceT]):
    """Represents an application command argument choice.

    .. container:: operations

        .. describe:: x == y

            Checks if two choices are equal.

        .. describe:: x != y

            Checks if two choices are not equal.

        .. describe:: hash(x)

            Returns the choice's hash.

    Parameters
    -----------
    name: Union[:class:`str`, :class:`locale_str`]
        The name of the choice. Used for display purposes.
        Can only be up to 100 characters.
    name_localizations: Dict[:class:`~bisim.Locale`, :class:`str`]
        The localised names of the choice. Used for display purposes.
    value: Union[:class:`int`, :class:`str`, :class:`float`]
        The value of the choice. If it's a string, it can only be
        up to 100 characters long.
    """

    __slots__ = ('name', 'value', '_locale_name', 'name_localizations')

    def __init__(self, *, name: Union[str, locale_str], value: ChoiceT):
        name, locale = (name.message, name) if isinstance(name, locale_str) else (name, None)
        self.name: str = name
        self._locale_name: Optional[locale_str] = locale
        self.value: ChoiceT = value
        self.name_localizations: Dict[Locale, str] = {}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Choice[ChoiceT]:
        self = cls.__new__(cls)
        self.name = data['name']
        self.value = data['value']
        self.name_localizations = _localizations(data, 'nameLocalizations')
        self._locale_name = None
        return self

    def __eq__(self, o: object) -> bool:
        return isinstance(o, Choice) and self.name == o.name and self.value == o.value

    def __hash__(self) -> int:
        return hash((self.name, self.value))

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(name={self.name!r}, value={self.value!r})'

    @property
    def _option_type(self) -> AppCommandOptionType:
        if isinstance(self.value, bool):
            raise TypeError('invalid Choice value type given, expected int, str, or float')
        if isinstance(self.value, int):
            return AppCommandOptionType.integer
        if isinstance(self.value, float):
            return AppCommandOptionType.number
        if isinstance(self.value, str):
            return AppCommandOptionType.string
        raise TypeError(
            f'invalid Choice value type given, expected int, str, or float but received {self.value.__class__.__name__}'
        )

    async def get_translated_payload(self, translator: Translator) -> Dict[str, Any]:
        base = self.to_dict()
        name_localizations: Dict[str, str] = {}
        context = TranslationContext(location=TranslationContextLocation.choice_name, data=self)
        if self._locale_name:
            for locale in (Locale.persian, Locale.english):
                translation = await translator._checked_translate(self._locale_name, locale, context)
                if translation is not None:
                    name_localizations[locale.value] = translation

        if name_localizations:
            base['nameLocalizations'] = name_localizations

        return base

    async def get_translated_payload_for_locale(self, translator: Translator, locale: Locale) -> Dict[str, Any]:
        base = self.to_dict()
        if self._locale_name:
            context = TranslationContext(location=TranslationContextLocation.choice_name, data=self)
            translation = await translator._checked_translate(self._locale_name, locale, context)
            if translation is not None:
                base['name'] = translation

        return base

    def to_dict(self) -> Dict[str, Any]:
        base: Dict[str, Any] = {'name': self.name, 'value': self.value}
        if self.name_localizations:
            base['nameLocalizations'] = {str(k): v for k, v in self.name_localizations.items()}
        return base


class AppCommandChannel(Hashable):
    """Represents an application command partially resolved channel object.

    Attributes
    -----------
    id: :class:`int`
        The ID of the channel.
    type: :class:`~bisim.ChannelType`
        The type of channel.
    name: :class:`str`
        The name of the channel.
    permissions: :class:`~bisim.Permissions`
        The resolved permissions of the user who invoked
        the application command in that channel.
    guild_id: :class:`int`
        The guild ID this channel belongs to.
    """

    def __init__(self, *, state: ConnectionState, data: Dict[str, Any], guild_id: int):
        self._state: ConnectionState = state
        self.guild_id: int = guild_id
        self.id: int = int(data['id'])
        self.type: ChannelType = ChannelType.from_bisim(data.get('type', 'GUILD_TEXT'))
        self.name: str = data.get('name') or ''
        self.permissions: Permissions = Permissions(utils._int(data.get('permissions'), 0))

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} id={self.id!r} name={self.name!r} type={self.type!r}>'

    @property
    def guild(self) -> Optional[Guild]:
        """Optional[:class:`~bisim.Guild`]: The channel's guild, from cache, if found."""
        return self._state._get_guild(self.guild_id)

    def resolve(self) -> Optional[Any]:
        """Resolves the application command channel to the appropriate channel from cache if found."""
        guild = self._state._get_guild(self.guild_id)
        if guild is not None:
            return guild.get_channel(self.id)
        return None

    async def fetch(self) -> Any:
        """|coro|

        Fetches the partial channel to a full :class:`~bisim.abc.GuildChannel`.

        Raises
        --------
        NotFound
            The channel was not found.
        Forbidden
            You do not have the permissions required to get a channel.
        HTTPException
            Retrieving the channel failed.

        Returns
        --------
        :class:`~bisim.abc.GuildChannel`
            The full channel.
        """
        client = self._state._get_client()
        return await client.fetch_channel(self.id)

    @property
    def mention(self) -> str:
        """:class:`str`: The string that allows you to mention the channel."""
        return f'<#{self.id}>'

    @property
    def created_at(self) -> datetime:
        """:class:`datetime.datetime`: An aware timestamp of when this channel was created in UTC."""
        return utils.snowflake_time(self.id)


class AppCommandThread:
    """Not on Bisim (no threads); kept so the name imports."""


class AppCommandPermissions:
    """Not on Bisim (per command permissions are not exposed); kept so the name imports."""


class GuildAppCommandPermissions:
    """Not on Bisim (per command permissions are not exposed); kept so the name imports."""


class Argument:
    """Represents an application command argument.

    Attributes
    ------------
    type: :class:`~bisim.AppCommandOptionType`
        The type of argument.
    name: :class:`str`
        The name of the argument.
    description: :class:`str`
        The description of the argument.
    required: :class:`bool`
        Whether the argument is required.
    choices: List[:class:`Choice`]
        A list of choices for the command to choose from for this argument.
    parent: Union[:class:`AppCommand`, :class:`AppCommandGroup`]
        The parent application command that has this argument.
    channel_types: List[:class:`~bisim.ChannelType`]
        The channel types that are allowed for this parameter.
    min_value: Optional[Union[:class:`int`, :class:`float`]]
        The minimum supported value for this parameter.
    max_value: Optional[Union[:class:`int`, :class:`float`]]
        The maximum supported value for this parameter.
    min_length: Optional[:class:`int`]
        The minimum allowed length for this parameter.
    max_length: Optional[:class:`int`]
        The maximum allowed length for this parameter.
    autocomplete: :class:`bool`
        Whether the argument has autocomplete.
    """

    __slots__ = (
        'type',
        'name',
        'description',
        'required',
        'choices',
        'channel_types',
        'min_value',
        'max_value',
        'min_length',
        'max_length',
        'autocomplete',
        'parent',
        '_state',
        'name_localizations',
        'description_localizations',
    )

    def __init__(self, *, parent: Any, data: Dict[str, Any], state: Optional[ConnectionState] = None) -> None:
        self._state: Optional[ConnectionState] = state
        self.parent: Any = parent
        self.type: AppCommandOptionType = AppCommandOptionType.from_bisim(data.get('type'))
        self.name: str = data['name']
        self.description: str = data.get('description') or ''
        self.required: bool = bool(data.get('required', False))
        self.min_value: Optional[Union[int, float]] = data.get('minValue')
        self.max_value: Optional[Union[int, float]] = data.get('maxValue')
        self.min_length: Optional[int] = data.get('minLength')
        self.max_length: Optional[int] = data.get('maxLength')
        self.autocomplete: bool = bool(data.get('autocomplete', False))
        self.channel_types: List[ChannelType] = [ChannelType.from_bisim(d) for d in data.get('channelTypes', []) or []]
        self.choices: List[Choice[Union[int, float, str]]] = [Choice.from_dict(d) for d in data.get('choices', []) or []]
        self.name_localizations: Dict[Locale, str] = _localizations(data, 'nameLocalizations')
        self.description_localizations: Dict[Locale, str] = _localizations(data, 'descriptionLocalizations')

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} name={self.name!r} type={self.type!r} required={self.required}>'

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'name': self.name,
            'type': self.type.bisim_name,
            'description': self.description,
            'required': self.required,
        }
        if self.choices:
            result['choices'] = [choice.to_dict() for choice in self.choices]
        if self.channel_types:
            result['channelTypes'] = [t.bisim_name for t in self.channel_types if t.bisim_name]
        if self.min_value is not None:
            result['minValue'] = self.min_value
        if self.max_value is not None:
            result['maxValue'] = self.max_value
        if self.min_length is not None:
            result['minLength'] = self.min_length
        if self.max_length is not None:
            result['maxLength'] = self.max_length
        if self.autocomplete:
            result['autocomplete'] = True
        return result


class AppCommandGroup:
    """Represents an application command subcommand.

    Attributes
    ------------
    type: :class:`~bisim.AppCommandOptionType`
        The type of subcommand.
    name: :class:`str`
        The name of the subcommand.
    description: :class:`str`
        The description of the subcommand.
    options: List[Union[:class:`Argument`, :class:`AppCommandGroup`]]
        A list of options.
    parent: Union[:class:`AppCommand`, :class:`AppCommandGroup`]
        The parent application command.
    """

    __slots__ = ('type', 'name', 'description', 'options', 'parent', '_state', 'name_localizations', 'description_localizations')

    def __init__(self, *, parent: Any, data: Dict[str, Any], state: Optional[ConnectionState] = None) -> None:
        self.parent: Any = parent
        self._state: Optional[ConnectionState] = state
        self.type: AppCommandOptionType = AppCommandOptionType.from_bisim(data.get('type'))
        self.name: str = data['name']
        self.description: str = data.get('description') or ''
        self.options: List[Union[Argument, AppCommandGroup]] = _parse_options(self, data.get('options') or [], state)
        self.name_localizations: Dict[Locale, str] = _localizations(data, 'nameLocalizations')
        self.description_localizations: Dict[Locale, str] = _localizations(data, 'descriptionLocalizations')

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} name={self.name!r} type={self.type!r}>'

    @property
    def qualified_name(self) -> str:
        """:class:`str`: Returns the fully qualified command name."""
        names = [self.name]
        parent = self.parent
        while isinstance(parent, (AppCommandGroup, AppCommand)):
            names.append(parent.name)
            parent = getattr(parent, 'parent', None)
        return ' '.join(reversed(names))

    @property
    def mention(self) -> str:
        """:class:`str`: Returns a string that allows you to mention the given AppCommandGroup."""
        root = self.parent
        while isinstance(root, AppCommandGroup):
            root = root.parent
        return f'</{self.qualified_name}:{getattr(root, "id", 0)}>'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type.bisim_name,
            'description': self.description,
            'options': [opt.to_dict() for opt in self.options],
        }


def _parse_options(parent: Any, options: List[Dict[str, Any]], state: Optional[ConnectionState]) -> List[Union[Argument, AppCommandGroup]]:
    result: List[Union[Argument, AppCommandGroup]] = []
    for option in options:
        kind = AppCommandOptionType.from_bisim(option.get('type'))
        if getattr(kind, 'value', 0) in (1, 2):
            result.append(AppCommandGroup(parent=parent, data=option, state=state))
        else:
            result.append(Argument(parent=parent, data=option, state=state))
    return result


class AppCommand(Hashable):
    """Represents an application command.

    In common parlance this is referred to as a "Slash Command" or a
    "Context Menu Command".

    .. container:: operations

        .. describe:: x == y

            Checks if two application commands are equal.

        .. describe:: x != y

            Checks if two application commands are not equal.

        .. describe:: hash(x)

            Returns the application command's hash.

        .. describe:: str(x)

            Returns the application command's name.

    Attributes
    -----------
    id: :class:`int`
        The application command's ID.
    application_id: :class:`int`
        The application command's application's ID.
    type: :class:`~bisim.AppCommandType`
        The application command's type.
    name: :class:`str`
        The application command's name.
    description: :class:`str`
        The application command's description.
    options: List[Union[:class:`Argument`, :class:`AppCommandGroup`]]
        A list of options.
    default_member_permissions: Optional[:class:`~bisim.Permissions`]
        The default member permissions that can run this command.
    dm_permission: :class:`bool`
        A boolean that indicates whether this command can be run in the DM with the bot.
    allowed_contexts: Optional[:class:`~bisim.AppCommandContext`]
        The contexts that this command is allowed to be used in.
    allowed_installs: Optional[:class:`~bisim.AppInstallationType`]
        Always ``None`` on Bisim.
    nsfw: :class:`bool`
        Whether the command is NSFW and should only work in NSFW channels.
    guild_id: Optional[:class:`int`]
        The ID of the guild this command is registered in. A value of ``None``
        denotes that it is a global command.
    name_localizations: Dict[:class:`~bisim.Locale`, :class:`str`]
        The localised names of the application command.
    description_localizations: Dict[:class:`~bisim.Locale`, :class:`str`]
        The localised descriptions of the application command.
    """

    __slots__ = (
        'id',
        'type',
        'application_id',
        'name',
        'description',
        'guild_id',
        'options',
        'default_member_permissions',
        'dm_permission',
        'allowed_contexts',
        'allowed_installs',
        'nsfw',
        '_state',
        'name_localizations',
        'description_localizations',
    )

    def __init__(self, *, data: Dict[str, Any], state: ConnectionState) -> None:
        self._state: ConnectionState = state
        self._from_data(data)

    def _from_data(self, data: Dict[str, Any]) -> None:
        self.id: int = int(data['id'])
        self.application_id: int = int(data.get('appId') or data.get('applicationId') or 0)
        self.name: str = data['name']
        self.description: str = data.get('description') or ''
        self.guild_id: Optional[int] = utils._snowflake(data.get('guildId'))
        self.type: AppCommandType = AppCommandType.from_bisim(data.get('type'))
        self.options: List[Union[Argument, AppCommandGroup]] = _parse_options(self, data.get('options') or [], self._state)
        permissions = data.get('defaultMemberPermissions')
        self.default_member_permissions: Optional[Permissions] = (
            Permissions(int(permissions)) if permissions not in (None, '') else None
        )
        contexts = data.get('contexts')
        self.allowed_contexts: Optional[AppCommandContext] = (
            AppCommandContext.from_bisim(contexts) if contexts is not None else None
        )
        self.dm_permission: bool = self.allowed_contexts is None or self.allowed_contexts.dm_channel
        self.allowed_installs: Optional[AppInstallationType] = None
        self.nsfw: bool = bool(data.get('nsfw', False))
        self.name_localizations: Dict[Locale, str] = _localizations(data, 'nameLocalizations')
        self.description_localizations: Dict[Locale, str] = _localizations(data, 'descriptionLocalizations')

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'id': str(self.id),
            'type': self.type.value,
            'name': self.name,
            'description': self.description,
            'options': [opt.to_dict() for opt in self.options],
        }
        if self.default_member_permissions is not None:
            result['defaultMemberPermissions'] = str(self.default_member_permissions.value)
        if self.allowed_contexts is not None:
            result['contexts'] = self.allowed_contexts.to_bisim()
        return result

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} id={self.id!r} name={self.name!r} type={self.type!r}>'

    @property
    def mention(self) -> str:
        """:class:`str`: Returns a string that allows you to mention the given AppCommand."""
        return f'</{self.name}:{self.id}>'

    @property
    def guild(self) -> Optional[Guild]:
        """Optional[:class:`~bisim.Guild`]: Returns the guild this command is registered to
        if it exists.
        """
        return self._state._get_guild(self.guild_id)

    async def fetch(self) -> AppCommand:
        """|coro|

        Fetches this command again.

        Returns
        --------
        :class:`AppCommand`
            The command, as Bisim has it now.
        """
        http = self._state.http
        if self.guild_id:
            data = await http.get_guild_command(self.application_id, self.guild_id, self.id)
        else:
            data = await http.get_global_command(self.application_id, self.id)
        return AppCommand(data=data, state=self._state)

    async def delete(self) -> None:
        """|coro|

        Deletes the application command.

        Raises
        -------
        NotFound
            The application command was not found.
        Forbidden
            You do not have permission to delete this application command.
        HTTPException
            Deleting the application command failed.
        MissingApplicationID
            The client does not have an application ID.
        """
        http = self._state.http
        if self.guild_id:
            await http.delete_guild_command(self.application_id, self.guild_id, self.id)
        else:
            await http.delete_global_command(self.application_id, self.id)

    async def edit(
        self,
        *,
        name: str = utils.MISSING,
        description: str = utils.MISSING,
        default_member_permissions: Optional[Permissions] = utils.MISSING,
        dm_permission: bool = utils.MISSING,
        allowed_contexts: Optional[AppCommandContext] = utils.MISSING,
        allowed_installs: Optional[AppInstallationType] = utils.MISSING,
        options: List[Union[Argument, AppCommandGroup]] = utils.MISSING,
    ) -> AppCommand:
        """|coro|

        Edits the application command.

        Parameters
        -----------
        name: :class:`str`
            The new name for the application command.
        description: :class:`str`
            The new description for the application command.
        default_member_permissions: Optional[:class:`~bisim.Permissions`]
            The new default permissions needed to use this application command.
            Pass value of ``None`` to remove any permission requirements.
        dm_permission: :class:`bool`
            Indicates if the application command can be used in the DM with the bot.
        allowed_contexts: Optional[:class:`~bisim.AppCommandContext`]
            Indicates the new contexts the application command can be used in.
        options: List[Union[:class:`Argument`, :class:`AppCommandGroup`]]
            List of new options for this application command.

        Raises
        -------
        NotFound
            The application command was not found.
        Forbidden
            You do not have permission to edit this application command.
        HTTPException
            Editing the application command failed.

        Returns
        --------
        :class:`AppCommand`
            The newly edited application command.
        """
        payload: Dict[str, Any] = {}
        if name is not utils.MISSING:
            payload['name'] = name
        if description is not utils.MISSING:
            payload['description'] = description
        if default_member_permissions is not utils.MISSING:
            payload['defaultMemberPermissions'] = (
                str(default_member_permissions.value) if default_member_permissions is not None else None
            )
        if allowed_contexts is not utils.MISSING:
            payload['contexts'] = allowed_contexts.to_bisim() if allowed_contexts is not None else None
        elif dm_permission is not utils.MISSING:
            payload['contexts'] = ['GUILD', 'BOT_DM'] if dm_permission else ['GUILD']
        if options is not utils.MISSING:
            payload['options'] = [option.to_dict() for option in options]
        if not payload:
            return self

        http = self._state.http
        if self.guild_id:
            data = await http.edit_guild_command(self.application_id, self.guild_id, self.id, payload)
        else:
            data = await http.edit_global_command(self.application_id, self.id, payload)
        return AppCommand(data=data, state=self._state)

    async def fetch_permissions(self, guild: Any) -> Any:
        """|coro|

        Not supported on Bisim.
        """
        raise NotSupported('Per command permissions')

from __future__ import annotations

import inspect
import re
from copy import copy as shallow_copy
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Coroutine,
    Dict,
    Generator,
    Generic,
    List,
    MutableMapping,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from .. import utils
from ..enums import AppCommandOptionType, AppCommandType, ChannelType, Locale
from ..flags import AppCommandContext, AppInstallationType
from ..member import Member
from ..message import Message
from ..object import Object
from ..permissions import Permissions
from ..user import User
from ..utils import MISSING, is_inside_class, maybe_coroutine, resolve_annotation
from .errors import (
    AppCommandError,
    CheckFailure,
    CommandInvokeError,
    CommandSignatureMismatch,
    CommandAlreadyRegistered,
)
from .models import Choice
from .transformers import CommandParameter, annotation_to_parameter
from .translator import TranslationContext, TranslationContextLocation, Translator, locale_str

if TYPE_CHECKING:
    from ..abc import Snowflake
    from ..interactions import Interaction
    from .namespace import Namespace

__all__ = (
    'Command',
    'ContextMenu',
    'Group',
    'Parameter',
    'context_menu',
    'command',
    'describe',
    'check',
    'rename',
    'choices',
    'autocomplete',
    'guilds',
    'guild_only',
    'dm_only',
    'private_channel_only',
    'allowed_contexts',
    'guild_install',
    'user_install',
    'allowed_installs',
    'default_permissions',
)

T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])
GroupT = TypeVar('GroupT', bound='Binding')
try:
    from typing import ParamSpec

    P = ParamSpec('P')
except ImportError:  # Python 3.9
    P = TypeVar('P')  # type: ignore
Coro = Coroutine[Any, Any, T]
UnboundError = Callable[['Interaction[Any]', AppCommandError], Coro[Any]]
Error = Union[
    Callable[[GroupT, 'Interaction[Any]', AppCommandError], Coro[Any]],
    UnboundError,
]
Check = Callable[['Interaction[Any]'], Union[bool, Coro[bool]]]
Binding = Any
CommandCallback = Callable[..., Coro[Any]]
ContextMenuCallback = Callable[..., Coro[Any]]
AutocompleteCallback = Callable[..., Coro[List[Choice[Any]]]]

# Bisim's rule for command and option names.
VALID_SLASH_COMMAND_NAME = re.compile(r'^[a-z0-9_-]{1,32}$')
CAMEL_CASE_REGEX = re.compile(r'(?<!^)(?=[A-Z])')

ARG_NAME_SUBREGEX = r'(?:\\?\*){0,2}(?P<name>\w+)'
ARG_DESCRIPTION_SUBREGEX = r'(?P<description>(?:.|\n)+?(?:\Z|\r?\n(?=[\S\r\n])))'
ARG_TYPE_SUBREGEX = r'(?:.+)'
GOOGLE_DOCSTRING_ARG_REGEX = re.compile(
    rf'^{ARG_NAME_SUBREGEX}[ \t]*(?:\({ARG_TYPE_SUBREGEX}\))?[ \t]*:[ \t]*{ARG_DESCRIPTION_SUBREGEX}',
    re.MULTILINE,
)
SPHINX_DOCSTRING_ARG_REGEX = re.compile(
    rf'^:param {ARG_NAME_SUBREGEX}:[ \t]+{ARG_DESCRIPTION_SUBREGEX}',
    re.MULTILINE,
)
NUMPY_DOCSTRING_ARG_REGEX = re.compile(
    rf'^{ARG_NAME_SUBREGEX}(?:[ \t]*:)?(?:[ \t]+{ARG_TYPE_SUBREGEX})?[ \t]*\r?\n[ \t]+{ARG_DESCRIPTION_SUBREGEX}',
    re.MULTILINE,
)


def _shorten(input: str, *, _wrapper: Any = None) -> str:
    try:
        input, _ = re.split(r'\n\s*\n', input, maxsplit=1)
    except ValueError:
        pass
    text = ' '.join(input.split())
    if len(text) <= 100:
        return text
    return text[:99] + '…'


def _parse_args_from_docstring(func: Callable[..., Any], params: Dict[str, CommandParameter]) -> Dict[str, str]:
    docstring = inspect.getdoc(func)

    if docstring is None:
        return {}

    section_lines = inspect.cleandoc('\n'.join(line for line in docstring.splitlines() if line.startswith('  ')))
    docstring_styles = (
        GOOGLE_DOCSTRING_ARG_REGEX.finditer(section_lines),
        SPHINX_DOCSTRING_ARG_REGEX.finditer(docstring),
        NUMPY_DOCSTRING_ARG_REGEX.finditer(docstring),
    )

    return {
        m.group('name'): m.group('description') for matches in docstring_styles for m in matches if m.group('name') in params
    }


def _to_kebab_case(text: str) -> str:
    return CAMEL_CASE_REGEX.sub('-', text).lower()


def validate_name(name: str) -> str:
    """Checks a slash command, group or option name against Bisim's rule:
    1 to 32 lowercase letters, digits, ``-`` and ``_``."""
    match = VALID_SLASH_COMMAND_NAME.match(name)
    if match is None:
        raise ValueError(
            'names must be between 1-32 characters and contain only lower-case letters, numbers, hyphens, or underscores.'
        )

    if name.lower() != name:
        raise ValueError('names must be all lower-case')
    return name


def validate_context_menu_name(name: str) -> str:
    """A context menu name: 1 to 32 characters, any case, spaces allowed."""
    if not name or len(name) > 32:
        raise ValueError('context menu names must be between 1-32 characters')
    return name


def validate_auto_complete_callback(callback: AutocompleteCallback) -> AutocompleteCallback:

    binding = getattr(callback, '__self__', None)
    pass_command_binding = binding is None and is_inside_class(callback)

    if binding is None:
        callback.pass_command_binding = pass_command_binding  # type: ignore

    required_parameters = 2 + pass_command_binding
    params = inspect.signature(callback).parameters
    if len(params) != required_parameters:
        raise TypeError(f'autocomplete callback {callback.__qualname__!r} requires either 2 or 3 parameters to be passed')

    return callback


def _context_menu_annotation(annotation: Any, *, _none: type = type(None)) -> AppCommandType:
    from ..abc import User as UserProtocol

    if annotation is Message:
        return AppCommandType.message

    supported_types: Set[Any] = {Member, User, UserProtocol}
    if annotation in supported_types:
        return AppCommandType.user

    # Check if there's an origin
    origin = getattr(annotation, '__origin__', None)
    if origin is not Union and type(annotation).__name__ != 'UnionType':
        raise TypeError(
            f'unsupported type annotation {annotation!r} for context menu, expected Message, Member, User, or a Union of Member and User'
        )

    # Only Union[Member, User] is supported
    if not all(arg in supported_types for arg in annotation.__args__):
        raise TypeError(f'unsupported types given inside {annotation!r}')

    return AppCommandType.user


def _populate_descriptions(params: Dict[str, CommandParameter], descriptions: Dict[str, Any]) -> None:
    for name, param in params.items():
        description = descriptions.pop(name, MISSING)
        if description is MISSING:
            param.description = '…'
            continue

        if not isinstance(description, (str, locale_str)):
            raise TypeError('description must be a string')

        if isinstance(description, str):
            param.description = _shorten(description)
        else:
            param.description = description

    if descriptions:
        first = next(iter(descriptions))
        raise TypeError(f'unknown parameter given: {first}')


def _populate_renames(params: Dict[str, CommandParameter], renames: Dict[str, Union[str, locale_str]]) -> None:
    rename_map: Dict[str, Union[str, locale_str]] = {}


    for name in params.keys():
        new_name = renames.pop(name, MISSING)

        if new_name is MISSING:
            rename_map[name] = name
            continue

        if name in rename_map.values():
            raise ValueError(f'{new_name} is already used')

        if isinstance(new_name, str):
            new_name = validate_name(new_name)
        else:
            validate_name(new_name.message)

        rename_map[name] = new_name
        params[name]._rename = new_name

    if renames:
        first = next(iter(renames))
        raise ValueError(f'unknown parameter given: {first}')


def _populate_choices(params: Dict[str, CommandParameter], all_choices: Dict[str, List[Choice[Any]]]) -> None:
    for name, param in params.items():
        choices = all_choices.pop(name, MISSING)
        if choices is MISSING:
            continue

        if not isinstance(choices, list):
            raise TypeError('choices must be a list of Choice')

        if not all(isinstance(choice, Choice) for choice in choices):
            raise TypeError('choices must be a list of Choice')

        if param.type not in (AppCommandOptionType.string, AppCommandOptionType.number, AppCommandOptionType.integer):
            raise TypeError('choices are only supported for integer, string, or number option types')

        if not all(param.type == choice._option_type for choice in choices):
            raise TypeError('choices must all have the same inner option type as the parameter choice type')

        param.choices = choices

    if all_choices:
        first = next(iter(all_choices))
        raise TypeError(f'unknown parameter given: {first}')


def _populate_autocomplete(params: Dict[str, CommandParameter], autocomplete: Dict[str, Any]) -> None:
    for name, param in params.items():
        callback = autocomplete.pop(name, MISSING)
        if callback is MISSING:
            continue

        if not inspect.iscoroutinefunction(callback):
            raise TypeError('autocomplete callback must be a coroutine function')

        if param.type not in (AppCommandOptionType.string, AppCommandOptionType.number, AppCommandOptionType.integer):
            raise TypeError('autocomplete is only supported for integer, string, or number option types')

        if param.is_choice_annotation():
            raise TypeError(
                'Choice annotation unsupported for autocomplete parameters, consider using a regular annotation instead'
            )

        param.autocomplete = validate_auto_complete_callback(callback)

    if autocomplete:
        first = next(iter(autocomplete))
        raise TypeError(f'unknown parameter given: {first}')


def _extract_parameters_from_callback(func: Callable[..., Any], globalns: Dict[str, Any]) -> Dict[str, CommandParameter]:
    params = inspect.signature(func).parameters
    cache: Dict[str, Any] = {}
    required_params = is_inside_class(func) + 1
    if len(params) < required_params:
        raise TypeError(f'callback {func.__qualname__!r} must have more than {required_params - 1} parameter(s)')

    iterator = iter(params.values())
    for _ in range(0, required_params):
        next(iterator)

    parameters: List[CommandParameter] = []
    for parameter in iterator:
        if parameter.annotation is parameter.empty:
            raise TypeError(f'parameter {parameter.name!r} is missing a type annotation in callback {func.__qualname__!r}')

        resolved = resolve_annotation(parameter.annotation, globalns, globalns, cache)
        param = annotation_to_parameter(resolved, parameter)
        parameters.append(param)

    values = sorted(parameters, key=lambda a: a.required, reverse=True)
    result = {v.name: v for v in values}

    descriptions = _parse_args_from_docstring(func, result)

    try:
        descriptions.update(func.__bisim_app_commands_param_description__)
    except AttributeError:
        for param in values:
            if param.description is MISSING:
                param.description = '…'
    if descriptions:
        _populate_descriptions(result, descriptions)

    try:
        renames = func.__bisim_app_commands_param_rename__
    except AttributeError:
        pass
    else:
        _populate_renames(result, renames.copy())

    try:
        choices = func.__bisim_app_commands_param_choices__
    except AttributeError:
        pass
    else:
        _populate_choices(result, choices.copy())

    try:
        autocomplete = func.__bisim_app_commands_param_autocomplete__
    except AttributeError:
        pass
    else:
        _populate_autocomplete(result, autocomplete.copy())

    return result


def _get_context_menu_parameter(func: ContextMenuCallback) -> Tuple[str, Any, AppCommandType]:
    params = inspect.signature(func).parameters
    if is_inside_class(func) and not hasattr(func, '__self__'):
        raise TypeError('context menus cannot be defined inside a class')

    if len(params) != 2:
        msg = (
            f'context menu callback {func.__qualname__!r} requires 2 parameters, '
            'the first one being the interaction and the other one explicitly '
            'annotated with either Message, User, Member, or a Union of User and Member'
        )
        raise TypeError(msg)

    iterator = iter(params.values())
    next(iterator)  # skip interaction
    parameter = next(iterator)
    if parameter.annotation is parameter.empty:
        msg = (
            f'second parameter of context menu callback {func.__qualname__!r} must be explicitly '
            'annotated with either Message, User, Member, or a Union of User and Member'
        )
        raise TypeError(msg)

    resolved = resolve_annotation(parameter.annotation, func.__globals__, func.__globals__, {})
    type = _context_menu_annotation(resolved)
    return (parameter.name, resolved, type)


async def _call_checks(checks: List[Check], interaction: Interaction[Any]) -> bool:
    for predicate in checks:
        if not await maybe_coroutine(predicate, interaction):
            return False
    return True


def _contexts_payload(contexts: Optional[AppCommandContext]) -> Optional[List[str]]:
    if contexts is None:
        return None
    names = contexts.to_bisim()
    return names or None


class Parameter:
    """A class that contains the parameter information of a :class:`Command` callback.

    Attributes
    -----------
    name: :class:`str`
        The name of the parameter. This is the Python identifier for the parameter.
    display_name: :class:`str`
        The displayed name of the parameter on Bisim.
    description: :class:`str`
        The description of the parameter.
    autocomplete: :class:`bool`
        Whether the parameter has an autocomplete handler.
    locale_name: Optional[:class:`locale_str`]
        The display name's locale string, if available.
    locale_description: Optional[:class:`locale_str`]
        The description's locale string, if available.
    required: :class:`bool`
        Whether the parameter is required
    choices: List[:class:`~bisim.app_commands.Choice`]
        A list of choices this parameter takes, if any.
    type: :class:`~bisim.AppCommandOptionType`
        The underlying type of this parameter.
    channel_types: List[:class:`~bisim.ChannelType`]
        The channel types that are allowed for this parameter.
    min_value: Optional[Union[:class:`int`, :class:`float`]]
        The minimum supported value for this parameter.
    max_value: Optional[Union[:class:`int`, :class:`float`]]
        The maximum supported value for this parameter.
    default: Any
        The default value of the parameter, if given.
        If not given then this is :data:`~bisim.utils.MISSING`.
    command: :class:`Command`
        The command this parameter is attached to.
    """

    def __init__(self, parent: CommandParameter, command: Command[Any, ..., Any]) -> None:
        self.__parent: CommandParameter = parent
        self.__command: Command[Any, ..., Any] = command

    @property
    def command(self) -> Command[Any, ..., Any]:
        return self.__command

    @property
    def locale_name(self) -> Optional[locale_str]:
        if isinstance(self.__parent._rename, locale_str):
            return self.__parent._rename
        return None

    @property
    def locale_description(self) -> Optional[locale_str]:
        if isinstance(self.__parent.description, locale_str):
            return self.__parent.description
        return None

    @property
    def name(self) -> str:
        return self.__parent.name

    @property
    def display_name(self) -> str:
        return self.__parent.display_name

    @property
    def description(self) -> str:
        return str(self.__parent.description)

    @property
    def required(self) -> bool:
        return self.__parent.required

    @property
    def choices(self) -> List[Choice[Union[str, int, float]]]:
        choices = self.__parent.choices
        if choices is MISSING:
            return []
        return choices.copy()

    @property
    def channel_types(self) -> List[ChannelType]:
        channel_types = self.__parent.channel_types
        if channel_types is MISSING:
            return []
        return channel_types.copy()

    @property
    def min_value(self) -> Optional[Union[int, float]]:
        return self.__parent.min_value

    @property
    def max_value(self) -> Optional[Union[int, float]]:
        return self.__parent.max_value

    @property
    def default(self) -> Any:
        return self.__parent.default

    @property
    def autocomplete(self) -> bool:
        return self.__parent.autocomplete is not None

    @property
    def type(self) -> AppCommandOptionType:
        return self.__parent.type

    def __repr__(self) -> str:
        return f'<Parameter name={self.name!r} type={self.type!r} required={self.required}>'


class Command(Generic[GroupT, P, T]):  # type: ignore[misc]
    """A class that implements an application command.

    These are usually not created manually, instead they are created using
    one of the following decorators:

    - :func:`~bisim.app_commands.command`
    - :meth:`Group.command <bisim.app_commands.Group.command>`
    - :meth:`CommandTree.command <bisim.app_commands.CommandTree.command>`

    Attributes
    ------------
    name: :class:`str`
        The name of the application command.
    description: :class:`str`
        The description of the application command. This shows up in the UI to describe
        the application command.
    checks
        A list of predicates that take a :class:`~bisim.Interaction` parameter
        to indicate whether the command callback should be executed. If an exception
        is necessary to be thrown to signal failure, then one inherited from
        :exc:`AppCommandError` should be used. If all the checks fail without
        propagating an exception, :exc:`CheckFailure` is raised.
    default_permissions: Optional[:class:`~bisim.Permissions`]
        The default permissions that can execute this command on Bisim. Bisim
        checks them when the command is used; there are no per command overrides.
        Setting an empty permissions field will disallow anyone except server
        administrators from using the command in a guild.
    guild_only: :class:`bool`
        Whether the command should only be usable in guild contexts.
    allowed_contexts: Optional[:class:`~bisim.app_commands.AppCommandContext`]
        The contexts that the command is allowed to be used in.
        Overrides ``guild_only`` if this is set.
    allowed_installs: Optional[:class:`~bisim.app_commands.AppInstallationType`]
        Accepted for compatibility (Bisim apps are installed to servers).
    nsfw: :class:`bool`
        Accepted for compatibility. Bisim does not limit commands to
        age-restricted channels.
    parent: Optional[:class:`Group`]
        The parent application command. ``None`` if there isn't one.
    extras: :class:`dict`
        A dictionary that can be used to store extraneous data.
        The library will not touch any values or keys within this dictionary.
    """

    def __init__(
        self,
        *,
        name: Union[str, locale_str],
        description: Union[str, locale_str],
        callback: CommandCallback,
        nsfw: bool = False,
        parent: Optional[Group] = None,
        guild_ids: Optional[List[int]] = None,
        allowed_contexts: Optional[AppCommandContext] = None,
        allowed_installs: Optional[AppInstallationType] = None,
        auto_locale_strings: bool = True,
        extras: Dict[Any, Any] = MISSING,
    ):
        name, locale = (name.message, name) if isinstance(name, locale_str) else (name, None)
        self.name: str = validate_name(name)
        self._locale_name: Optional[locale_str] = locale
        description, locale = (
            (description.message, description) if isinstance(description, locale_str) else (description, None)
        )
        self.description: str = description
        self._locale_description: Optional[locale_str] = locale
        self._attr: Optional[str] = None
        self._callback: CommandCallback = callback
        self.parent: Optional[Group] = parent
        self.binding: Optional[GroupT] = None
        self.on_error: Optional[Error[GroupT]] = None
        self.module: Optional[str] = callback.__module__

        try:
            self.binding = callback.__self__  # type: ignore
            self._callback = callback = callback.__func__  # type: ignore
        except AttributeError:
            pass

        self._params: Dict[str, CommandParameter] = _extract_parameters_from_callback(callback, callback.__globals__)
        self.checks: List[Check] = getattr(callback, '__bisim_app_commands_checks__', [])
        self._guild_ids: Optional[List[int]] = guild_ids or getattr(callback, '__bisim_app_commands_default_guilds__', None)
        self.default_permissions: Optional[Permissions] = getattr(
            callback, '__bisim_app_commands_default_permissions__', None
        )
        self.guild_only: bool = getattr(callback, '__bisim_app_commands_guild_only__', False)
        self.allowed_contexts: Optional[AppCommandContext] = allowed_contexts or getattr(
            callback, '__bisim_app_commands_contexts__', None
        )
        self.allowed_installs: Optional[AppInstallationType] = allowed_installs or getattr(
            callback, '__bisim_app_commands_installation_types__', None
        )

        self.nsfw: bool = nsfw
        self.extras: Dict[Any, Any] = extras or {}

        if self._guild_ids is not None and self.parent is not None:
            raise ValueError('child commands cannot have default guilds set, consider setting them in the parent instead')

        if auto_locale_strings:
            self._convert_to_locale_strings()

    def _convert_to_locale_strings(self) -> None:
        if self._locale_name is None:
            self._locale_name = locale_str(self.name)
        if self._locale_description is None:
            self._locale_description = locale_str(self.description)

        for param in self._params.values():
            param._convert_to_locale_strings()

    def __set_name__(self, owner: Type[Any], name: str) -> None:
        self._attr = name

    def __repr__(self) -> str:
        return f'<Command name={self.name!r} parent={getattr(self.parent, "name", None)!r}>'

    @property
    def callback(self) -> CommandCallback:
        """:ref:`coroutine <coroutine>`: The coroutine that is executed when the command is called."""
        return self._callback

    def _copy_with(
        self,
        *,
        parent: Optional[Group],
        binding: GroupT,
        bindings: MutableMapping[GroupT, GroupT] = MISSING,
        set_on_binding: bool = True,
    ) -> Command[GroupT, Any, T]:
        bindings = {} if bindings is MISSING else bindings

        copy = shallow_copy(self)
        copy._params = self._params.copy()
        copy.parent = parent
        copy.binding = bindings.get(self.binding) if self.binding is not None else binding

        if copy._attr and set_on_binding:
            setattr(copy.binding, copy._attr, copy)

        return copy

    async def get_translated_payload(self, tree: Any, translator: Translator) -> Dict[str, Any]:
        base = self.to_dict(tree)
        name_localizations: Dict[str, str] = {}
        description_localizations: Dict[str, str] = {}

        name_context = TranslationContext(location=TranslationContextLocation.command_name, data=self)
        description_context = TranslationContext(location=TranslationContextLocation.command_description, data=self)

        for locale in (Locale.persian, Locale.english):
            if self._locale_name:
                translation = await translator._checked_translate(self._locale_name, locale, name_context)
                if translation is not None:
                    name_localizations[locale.value] = translation

            if self._locale_description:
                translation = await translator._checked_translate(self._locale_description, locale, description_context)
                if translation is not None:
                    description_localizations[locale.value] = translation

        if name_localizations:
            base['nameLocalizations'] = name_localizations
        if description_localizations:
            base['descriptionLocalizations'] = description_localizations
        base['options'] = [
            await param.get_translated_payload(translator, Parameter(param, self)) for param in self._params.values()
        ]
        return base

    def to_dict(self, tree: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            'name': self.name,
            'description': self.description,
            'options': [param.to_dict() for param in self._params.values()],
        }
        if self.parent is None:
            base['type'] = AppCommandType.chat_input.value
            if self.nsfw:
                base['nsfw'] = True
            base['defaultMemberPermissions'] = (
                None if self.default_permissions is None else str(self.default_permissions.value)
            )
            contexts = self.allowed_contexts if self.allowed_contexts is not None else getattr(tree, 'allowed_contexts', None)
            if self.guild_only and self.allowed_contexts is None:
                contexts = AppCommandContext(guild=True)
            payload = _contexts_payload(contexts) if contexts is not None and contexts.value else None
            if payload is not None:
                base['contexts'] = payload
        else:
            base['type'] = AppCommandOptionType.subcommand.bisim_name
        return base

    async def _invoke_error_handlers(self, interaction: Interaction[Any], error: AppCommandError) -> None:
        if self.on_error is not None:
            if self.binding is not None:
                await self.on_error(self.binding, interaction, error)  # type: ignore
            else:
                await self.on_error(interaction, error)  # type: ignore

        parent = self.parent
        if parent is not None:
            await parent.on_error(interaction, error)

            if parent.parent is not None:
                await parent.parent.on_error(interaction, error)

        binding_error_handler = getattr(self.binding, '__bisim_app_commands_error_handler__', None)
        if binding_error_handler is not None:
            await binding_error_handler(interaction, error)

    def _has_any_error_handlers(self) -> bool:
        if self.on_error is not None:
            return True

        parent = self.parent
        if parent is not None:
            if not hasattr(parent.on_error, '__bisim_app_commands_base_function__'):
                return True

            if parent.parent is not None:
                if not hasattr(parent.parent.on_error, '__bisim_app_commands_base_function__'):
                    return True

        if getattr(self.binding, '__bisim_app_commands_error_handler__', None) is not None:
            return True

        return False

    async def _transform_arguments(self, interaction: Interaction[Any], namespace: Namespace) -> Dict[str, Any]:
        values = namespace.__dict__
        transformed_values = {}

        for param in self._params.values():
            try:
                value = values[param.display_name]
            except KeyError:
                if not param.required:
                    transformed_values[param.name] = param.default
                else:
                    raise CommandSignatureMismatch(self) from None
            else:
                transformed_values[param.name] = await param.transform(interaction, value)

        return transformed_values

    def _bind_arguments(self, args: Tuple[Any, ...], params: Dict[str, Any]) -> None:
        signature = getattr(self, '_cached_signature', None)
        if signature is None:
            signature = inspect.signature(self._callback)
            self._cached_signature = signature
        try:
            signature.bind(*args, **params)
        except TypeError:
            # The options Bisim sent do not fit the function: the synced command is out of date.
            raise CommandSignatureMismatch(self) from None

    async def _do_call(self, interaction: Interaction[Any], params: Dict[str, Any]) -> T:
        args: Tuple[Any, ...] = (self.binding, interaction) if self.binding is not None else (interaction,)
        self._bind_arguments(args, params)
        try:
            return await self._callback(*args, **params)  # type: ignore
        except AppCommandError:
            raise
        except Exception as e:
            raise CommandInvokeError(self, e) from e

    async def _invoke_with_namespace(self, interaction: Interaction[Any], namespace: Namespace) -> T:
        if not await self._check_can_run(interaction):
            raise CheckFailure(f'The check functions for command {self.name!r} failed.')

        transformed_values = await self._transform_arguments(interaction, namespace)
        return await self._do_call(interaction, transformed_values)

    async def _invoke_autocomplete(self, interaction: Interaction[Any], name: str, namespace: Namespace) -> None:
        value = namespace.__dict__[name]

        try:
            param = self._params[name]
        except KeyError:
            params = {param.display_name: param for param in self._params.values()}
            try:
                param = params[name]
            except KeyError:
                raise CommandSignatureMismatch(self) from None

        if param.autocomplete is None:
            raise CommandSignatureMismatch(self)

        predicates = getattr(param.autocomplete, '__bisim_app_commands_checks__', [])
        if predicates:
            try:
                passed = await _call_checks(predicates, interaction)
            except Exception:
                passed = False

            if not passed:
                if not interaction.response.is_done():
                    await interaction.response.autocomplete([])
                return

        if getattr(param.autocomplete, 'pass_command_binding', False):
            binding = self.binding
            if binding is not None:
                choices = await param.autocomplete(binding, interaction, value)
            else:
                raise TypeError('autocomplete parameter expected a bound self parameter but one was not provided')
        else:
            choices = await param.autocomplete(interaction, value)

        if interaction.response.is_done():
            return

        await interaction.response.autocomplete(choices)

    def _get_internal_command(self, name: str) -> Optional[Union[Command[Any, ..., Any], Group]]:
        return None

    @property
    def parameters(self) -> List[Parameter]:
        """Returns a list of parameters for this command.

        This does not include the ``self`` or ``interaction`` parameters.

        Returns
        --------
        List[:class:`Parameter`]
            The parameters of this command.
        """
        return [Parameter(p, self) for p in self._params.values()]

    def get_parameter(self, name: str) -> Optional[Parameter]:
        """Retrieves a parameter by its name.

        The name must be the Python identifier rather than the renamed
        one for display on Bisim.

        Parameters
        -----------
        name: :class:`str`
            The parameter name in the callback function.

        Returns
        --------
        Optional[:class:`Parameter`]
            The parameter or ``None`` if not found.
        """
        parent = self._params.get(name)
        if parent is not None:
            return Parameter(parent, self)
        return None

    @property
    def root_parent(self) -> Optional[Group]:
        """Optional[:class:`Group`]: The root parent of this command."""
        if self.parent is None:
            return None
        parent = self.parent
        return parent.parent or parent

    @property
    def qualified_name(self) -> str:
        """:class:`str`: Returns the fully qualified command name.

        The qualified name includes the parent name as well. For example,
        in a command like ``/foo bar`` the qualified name is ``foo bar``.
        """
        if self.parent is None:
            return self.name

        names = [self.name, self.parent.name]
        grandparent = self.parent.parent
        if grandparent is not None:
            names.append(grandparent.name)

        return ' '.join(reversed(names))

    async def _check_can_run(self, interaction: Interaction[Any]) -> bool:
        if self.parent is not None and self.parent is not self.binding:
            if not await maybe_coroutine(self.parent.interaction_check, interaction):
                return False

        if self.binding is not None:
            check: Optional[Check] = getattr(self.binding, 'interaction_check', None)
            if check:
                ret = await maybe_coroutine(check, interaction)
                if not ret:
                    return False

        predicates = self.checks
        if not predicates:
            return True

        return await _call_checks(predicates, interaction)

    def error(self, coro: Error[GroupT]) -> Error[GroupT]:
        """A decorator that registers a coroutine as a local error handler.

        The local error handler is called whenever an exception is raised in the body
        of the command or during handling of the command. The error handler must take
        2 parameters, the interaction and the error.

        The error passed will be derived from :exc:`AppCommandError`.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the local error handler.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not inspect.iscoroutinefunction(coro):
            raise TypeError('The error handler must be a coroutine.')

        self.on_error = coro
        return coro

    def autocomplete(self, name: str) -> Callable[[AutocompleteCallback], AutocompleteCallback]:
        """A decorator that registers a coroutine as an autocomplete prompt for a parameter.

        The coroutine callback must have 2 parameters, the :class:`~bisim.Interaction`,
        and the current value by the user (the string currently being typed by the user).

        To get the values from other parameters that may be filled in, accessing
        :attr:`.Interaction.namespace` will give a :class:`Namespace` object with those
        values.

        Parent :func:`checks <check>` are ignored within an autocomplete. However, checks can be added
        to the autocomplete callback and the ones added will be called. If the checks fail for any reason
        then an empty list is sent as the interaction response.

        The coroutine decorator **must** return a list of :class:`~bisim.app_commands.Choice` objects.
        Only up to 25 objects are supported.

        Example:

        .. code-block:: python3

            @app_commands.command()
            async def fruits(interaction: bisim.Interaction, fruit: str):
                await interaction.response.send_message(f'Your favourite fruit seems to be {fruit}')

            @fruits.autocomplete('fruit')
            async def fruits_autocomplete(
                interaction: bisim.Interaction,
                current: str,
            ) -> List[app_commands.Choice[str]]:
                fruits = ['Banana', 'Pineapple', 'Apple', 'Watermelon', 'Melon', 'Cherry']
                return [
                    app_commands.Choice(name=fruit, value=fruit)
                    for fruit in fruits if current.lower() in fruit.lower()
                ]

        Parameters
        -----------
        name: :class:`str`
            The parameter name to register as autocomplete.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine or
            the parameter is not found or of an invalid type.
        """

        def decorator(coro: AutocompleteCallback) -> AutocompleteCallback:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError('The autocomplete callback must be a coroutine function.')

            try:
                param = self._params[name]
            except KeyError:
                raise TypeError(f'unknown parameter: {name!r}') from None

            if param.type not in (AppCommandOptionType.string, AppCommandOptionType.number, AppCommandOptionType.integer):
                raise TypeError('autocomplete is only supported for integer, string, or number option types')

            if param.is_choice_annotation():
                raise TypeError(
                    'Choice annotation unsupported for autocomplete parameters, consider using a regular annotation instead'
                )

            param.autocomplete = validate_auto_complete_callback(coro)
            return coro

        return decorator

    def add_check(self, func: Check, /) -> None:
        """Adds a check to the command.

        This is the non-decorator interface to :func:`check`.

        Parameters
        -----------
        func
            The function that will be used as a check.
        """
        self.checks.append(func)

    def remove_check(self, func: Check, /) -> None:
        """Removes a check from the command.

        This function is idempotent and will not raise an exception
        if the function is not in the command's checks.

        Parameters
        -----------
        func
            The function to remove from the checks.
        """
        try:
            self.checks.remove(func)
        except ValueError:
            pass


class ContextMenu:
    """A class that implements a context menu application command.

    These are usually not created manually, instead they are created using
    one of the following decorators:

    - :func:`~bisim.app_commands.context_menu`
    - :meth:`CommandTree.context_menu <bisim.app_commands.CommandTree.context_menu>`

    Attributes
    ------------
    name: :class:`str`
        The name of the context menu.
    type: :class:`.AppCommandType`
        The type of context menu application command. By default, this is inferred
        by the parameter of the callback.
    default_permissions: Optional[:class:`.Permissions`]
        The default permissions that can execute this command on Bisim.
    guild_only: :class:`bool`
        Whether the command should only be usable in guild contexts.
    allowed_contexts: Optional[:class:`~bisim.app_commands.AppCommandContext`]
        The contexts that this context menu is allowed to be used in.
    allowed_installs: Optional[:class:`~bisim.app_commands.AppInstallationType`]
        Accepted for compatibility.
    nsfw: :class:`bool`
        Accepted for compatibility. Bisim does not limit commands to
        age-restricted channels.
    checks
        A list of predicates that take a :class:`~bisim.Interaction` parameter
        to indicate whether the command callback should be executed.
    extras: :class:`dict`
        A dictionary that can be used to store extraneous data.
    """

    def __init__(
        self,
        *,
        name: Union[str, locale_str],
        callback: ContextMenuCallback,
        type: AppCommandType = MISSING,
        nsfw: bool = False,
        guild_ids: Optional[List[int]] = None,
        allowed_contexts: Optional[AppCommandContext] = None,
        allowed_installs: Optional[AppInstallationType] = None,
        auto_locale_strings: bool = True,
        extras: Dict[Any, Any] = MISSING,
    ):
        name, locale = (name.message, name) if isinstance(name, locale_str) else (name, None)
        self.name: str = validate_context_menu_name(name)
        self._locale_name: Optional[locale_str] = locale
        self._callback: ContextMenuCallback = callback
        (param, annotation, actual_type) = _get_context_menu_parameter(callback)
        if type is MISSING:
            type = actual_type

        if actual_type != type:
            raise ValueError(f'context menu callback implies a type of {actual_type} but {type} was passed.')

        self.type: AppCommandType = type
        self._param_name = param
        self._annotation = annotation
        self.module: Optional[str] = callback.__module__
        self._guild_ids = guild_ids or getattr(callback, '__bisim_app_commands_default_guilds__', None)
        self.on_error: Optional[UnboundError] = None
        self.default_permissions: Optional[Permissions] = getattr(
            callback, '__bisim_app_commands_default_permissions__', None
        )
        self.nsfw: bool = nsfw
        self.guild_only: bool = getattr(callback, '__bisim_app_commands_guild_only__', False)
        self.allowed_contexts: Optional[AppCommandContext] = allowed_contexts or getattr(
            callback, '__bisim_app_commands_contexts__', None
        )
        self.allowed_installs: Optional[AppInstallationType] = allowed_installs or getattr(
            callback, '__bisim_app_commands_installation_types__', None
        )
        self.checks: List[Check] = getattr(callback, '__bisim_app_commands_checks__', [])
        self.extras: Dict[Any, Any] = extras or {}

        if auto_locale_strings:
            if self._locale_name is None:
                self._locale_name = locale_str(self.name)

    def __repr__(self) -> str:
        return f'<ContextMenu name={self.name!r} type={self.type!r}>'

    @property
    def callback(self) -> ContextMenuCallback:
        """:ref:`coroutine <coroutine>`: The coroutine that is executed when the context menu is called."""
        return self._callback

    @property
    def qualified_name(self) -> str:
        """:class:`str`: Returns the fully qualified command name."""
        return self.name

    async def get_translated_payload(self, tree: Any, translator: Translator) -> Dict[str, Any]:
        base = self.to_dict(tree)
        context = TranslationContext(location=TranslationContextLocation.command_name, data=self)
        if self._locale_name:
            name_localizations: Dict[str, str] = {}
            for locale in (Locale.persian, Locale.english):
                translation = await translator._checked_translate(self._locale_name, locale, context)
                if translation is not None:
                    name_localizations[locale.value] = translation

            if name_localizations:
                base['nameLocalizations'] = name_localizations
        return base

    def to_dict(self, tree: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            'name': self.name,
            'type': self.type.value,
            'defaultMemberPermissions': None if self.default_permissions is None else str(self.default_permissions.value),
        }
        if self.nsfw:
            base['nsfw'] = True
        contexts = self.allowed_contexts if self.allowed_contexts is not None else getattr(tree, 'allowed_contexts', None)
        if self.guild_only and self.allowed_contexts is None:
            contexts = AppCommandContext(guild=True)
        payload = _contexts_payload(contexts) if contexts is not None and contexts.value else None
        if payload is not None:
            base['contexts'] = payload
        return base

    async def _check_can_run(self, interaction: Interaction[Any]) -> bool:
        predicates = self.checks
        if not predicates:
            return True

        return await _call_checks(predicates, interaction)

    def _has_any_error_handlers(self) -> bool:
        return self.on_error is not None

    async def _invoke(self, interaction: Interaction[Any], arg: Any) -> None:
        try:
            if not await self._check_can_run(interaction):
                raise CheckFailure(f'The check functions for context menu {self.name!r} failed.')

            await self._callback(interaction, arg)
        except AppCommandError:
            raise
        except Exception as e:
            raise CommandInvokeError(self, e) from e

    def error(self, coro: UnboundError) -> UnboundError:
        """A decorator that registers a coroutine as a local error handler.

        The local error handler is called whenever an exception is raised in the body
        of the command or during handling of the command. The error handler must take
        2 parameters, the interaction and the error.

        The error passed will be derived from :exc:`AppCommandError`.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the local error handler.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not inspect.iscoroutinefunction(coro):
            raise TypeError('The error handler must be a coroutine.')

        self.on_error = coro
        return coro

    def add_check(self, func: Check, /) -> None:
        """Adds a check to the command.

        This is the non-decorator interface to :func:`check`.

        Parameters
        -----------
        func
            The function that will be used as a check.
        """
        self.checks.append(func)

    def remove_check(self, func: Check, /) -> None:
        """Removes a check from the command.

        This function is idempotent and will not raise an exception
        if the function is not in the command's checks.

        Parameters
        -----------
        func
            The function to remove from the checks.
        """
        try:
            self.checks.remove(func)
        except ValueError:
            pass


class Group:
    """A class that implements an application command group.

    These are usually inherited rather than created manually.

    Decorators such as :func:`guild_only`, :func:`guilds`, and :func:`default_permissions`
    will apply to the group if used on top of a subclass. For example:

    .. code-block:: python3

        from bisim import app_commands

        @app_commands.guild_only()
        class MyGroup(app_commands.Group):
            pass

    Attributes
    ------------
    name: :class:`str`
        The name of the group.
    description: :class:`str`
        The description of the group. This shows up in the UI to describe
        the group.
    default_permissions: Optional[:class:`~bisim.Permissions`]
        The default permissions that can execute this group on Bisim.
    guild_only: :class:`bool`
        Whether the group should only be usable in guild contexts.
    allowed_contexts: Optional[:class:`~bisim.app_commands.AppCommandContext`]
        The contexts that this group is allowed to be used in.
    allowed_installs: Optional[:class:`~bisim.app_commands.AppInstallationType`]
        Accepted for compatibility.
    nsfw: :class:`bool`
        Accepted for compatibility. Bisim does not limit commands to
        age-restricted channels.
    parent: Optional[:class:`Group`]
        The parent group. ``None`` if there isn't one.
    extras: :class:`dict`
        A dictionary that can be used to store extraneous data.
    """

    __bisim_app_commands_group_children__: ClassVar[List[Union[Command[Any, ..., Any], Group]]] = []
    __bisim_app_commands_skip_init_binding__: bool = False
    __bisim_app_commands_group_name__: str = MISSING
    __bisim_app_commands_group_description__: str = MISSING
    __bisim_app_commands_group_locale_name__: Optional[locale_str] = None
    __bisim_app_commands_group_locale_description__: Optional[locale_str] = None
    __bisim_app_commands_group_nsfw__: bool = False
    __bisim_app_commands_guild_only__: bool = MISSING
    __bisim_app_commands_contexts__: Optional[AppCommandContext] = MISSING
    __bisim_app_commands_installation_types__: Optional[AppInstallationType] = MISSING
    __bisim_app_commands_default_permissions__: Optional[Permissions] = MISSING
    __bisim_app_commands_has_module__: bool = False
    __bisim_app_commands_error_handler__: Optional[Callable[[Interaction[Any], AppCommandError], Coroutine[Any, Any, None]]] = None

    def __init_subclass__(
        cls,
        *,
        name: Union[str, locale_str] = MISSING,
        description: Union[str, locale_str] = MISSING,
        guild_only: bool = MISSING,
        nsfw: bool = False,
        default_permissions: Optional[Permissions] = MISSING,
        extras: Dict[Any, Any] = MISSING,
    ) -> None:
        if not cls.__bisim_app_commands_group_children__:
            children: List[Union[Command[Any, ..., Any], Group]] = [
                member for member in cls.__dict__.values() if isinstance(member, (Group, Command)) and member.parent is None
            ]

            cls.__bisim_app_commands_group_children__ = children

            found = set()
            for child in children:
                if child.name in found:
                    raise TypeError(f'Command {child.name!r} is a duplicate')
                found.add(child.name)

            if len(children) > 25:
                raise TypeError('groups cannot have more than 25 commands')

        if name is MISSING:
            cls.__bisim_app_commands_group_name__ = validate_name(_to_kebab_case(cls.__name__))
        elif isinstance(name, str):
            cls.__bisim_app_commands_group_name__ = validate_name(name)
        else:
            cls.__bisim_app_commands_group_name__ = validate_name(name.message)
            cls.__bisim_app_commands_group_locale_name__ = name

        if description is MISSING:
            if cls.__doc__ is None:
                cls.__bisim_app_commands_group_description__ = '…'
            else:
                cls.__bisim_app_commands_group_description__ = _shorten(cls.__doc__)
        elif isinstance(description, str):
            cls.__bisim_app_commands_group_description__ = description
        else:
            cls.__bisim_app_commands_group_description__ = description.message
            cls.__bisim_app_commands_group_locale_description__ = description

        if cls.__module__ != __name__:
            cls.__bisim_app_commands_has_module__ = True

        if guild_only is not MISSING:
            cls.__bisim_app_commands_guild_only__ = guild_only

        if default_permissions is not MISSING:
            cls.__bisim_app_commands_default_permissions__ = default_permissions

        cls.__bisim_app_commands_group_nsfw__ = nsfw
        cls.__bisim_app_commands_group_extras__ = extras  # type: ignore

    def __init__(
        self,
        *,
        name: Union[str, locale_str] = MISSING,
        description: Union[str, locale_str] = MISSING,
        parent: Optional[Group] = None,
        guild_ids: Optional[List[int]] = None,
        guild_only: bool = MISSING,
        allowed_contexts: Optional[AppCommandContext] = MISSING,
        allowed_installs: Optional[AppInstallationType] = MISSING,
        nsfw: bool = MISSING,
        auto_locale_strings: bool = True,
        default_permissions: Optional[Permissions] = MISSING,
        extras: Dict[Any, Any] = MISSING,
    ):
        cls = self.__class__

        if name is MISSING:
            name, locale = cls.__bisim_app_commands_group_name__, cls.__bisim_app_commands_group_locale_name__
        elif isinstance(name, str):
            name, locale = name, None
        else:
            name, locale = name.message, name
        self.name: str = validate_name(name) if name is not MISSING else MISSING  # type: ignore
        self._locale_name: Optional[locale_str] = locale

        if description is MISSING:
            description, locale = cls.__bisim_app_commands_group_description__, cls.__bisim_app_commands_group_locale_description__
        elif isinstance(description, str):
            description, locale = description, None
        else:
            description, locale = description.message, description
        self.description: str = description or '…'
        self._locale_description: Optional[locale_str] = locale

        self._attr: Optional[str] = None
        self._owner_cls: Optional[Type[Any]] = None
        self._guild_ids: Optional[List[int]] = guild_ids or getattr(cls, '__bisim_app_commands_default_guilds__', None)

        if default_permissions is MISSING:
            if cls.__bisim_app_commands_default_permissions__ is MISSING:
                default_permissions = None
            else:
                default_permissions = cls.__bisim_app_commands_default_permissions__

        self.default_permissions: Optional[Permissions] = default_permissions

        if guild_only is MISSING:
            if cls.__bisim_app_commands_guild_only__ is MISSING:
                guild_only = False
            else:
                guild_only = cls.__bisim_app_commands_guild_only__

        self.guild_only: bool = guild_only

        if allowed_contexts is MISSING:
            if cls.__bisim_app_commands_contexts__ is MISSING:
                allowed_contexts = None
            else:
                allowed_contexts = cls.__bisim_app_commands_contexts__

        self.allowed_contexts: Optional[AppCommandContext] = allowed_contexts

        if allowed_installs is MISSING:
            if cls.__bisim_app_commands_installation_types__ is MISSING:
                allowed_installs = None
            else:
                allowed_installs = cls.__bisim_app_commands_installation_types__

        self.allowed_installs: Optional[AppInstallationType] = allowed_installs

        if nsfw is MISSING:
            nsfw = cls.__bisim_app_commands_group_nsfw__

        self.nsfw: bool = nsfw

        if not self.description:
            raise TypeError('groups must have a description')

        if not self.name:
            raise TypeError('groups must have a name')

        self.parent: Optional[Group] = parent
        self.module: Optional[str]
        if cls.__bisim_app_commands_has_module__:
            self.module = cls.__module__
        else:
            try:
                self.module = inspect.currentframe().f_back.f_globals['__name__']  # type: ignore
            except (AttributeError, IndexError, KeyError):
                self.module = None

        self._children: Dict[str, Union[Command[Any, ..., Any], Group]] = {}
        self.extras: Dict[Any, Any] = extras or getattr(cls, '__bisim_app_commands_group_extras__', None) or {}

        bindings: Dict[Group, Group] = {}

        for child in self.__bisim_app_commands_group_children__:
            copy = (
                child._copy_with(parent=self, binding=self, bindings=bindings, set_on_binding=False)
                if not cls.__bisim_app_commands_skip_init_binding__
                else child
            )

            self._children[copy.name] = copy
            if copy._attr and not cls.__bisim_app_commands_skip_init_binding__:
                setattr(self, copy._attr, copy)

        if parent is not None:
            if parent.parent is not None:
                raise ValueError('groups can only be nested at most one level')
            parent.add_command(self)

        if auto_locale_strings:
            self._convert_to_locale_strings()

    def _convert_to_locale_strings(self) -> None:
        if self._locale_name is None:
            self._locale_name = locale_str(self.name)
        if self._locale_description is None:
            self._locale_description = locale_str(self.description)


    def __set_name__(self, owner: Type[Any], name: str) -> None:
        self._attr = name
        self.module = owner.__module__
        self._owner_cls = owner

    def __repr__(self) -> str:
        return f'<Group name={self.name!r} parent={getattr(self.parent, "name", None)!r}>'

    def _copy_with(
        self,
        *,
        parent: Optional[Group],
        binding: Binding,
        bindings: MutableMapping[Group, Group] = MISSING,
        set_on_binding: bool = True,
    ) -> Group:
        bindings = {} if bindings is MISSING else bindings

        copy = shallow_copy(self)
        copy.parent = parent
        copy._children = {}

        bindings[self] = copy

        for child in self._children.values():
            child_copy = child._copy_with(parent=copy, binding=binding, bindings=bindings)
            child_copy.parent = copy
            copy._children[child_copy.name] = child_copy

            if isinstance(child_copy, Group) and child_copy._attr and set_on_binding:
                if binding.__class__ is child_copy._owner_cls:
                    setattr(binding, child_copy._attr, child_copy)
                elif child_copy._owner_cls is copy.__class__:
                    setattr(copy, child_copy._attr, child_copy)

        if copy._attr and set_on_binding:
            setattr(parent or binding, copy._attr, copy)

        return copy

    async def get_translated_payload(self, tree: Any, translator: Translator) -> Dict[str, Any]:
        base = self.to_dict(tree)
        name_localizations: Dict[str, str] = {}
        description_localizations: Dict[str, str] = {}

        name_context = TranslationContext(location=TranslationContextLocation.group_name, data=self)
        description_context = TranslationContext(location=TranslationContextLocation.group_description, data=self)
        for locale in (Locale.persian, Locale.english):
            if self._locale_name:
                translation = await translator._checked_translate(self._locale_name, locale, name_context)
                if translation is not None:
                    name_localizations[locale.value] = translation

            if self._locale_description:
                translation = await translator._checked_translate(self._locale_description, locale, description_context)
                if translation is not None:
                    description_localizations[locale.value] = translation

        if name_localizations:
            base['nameLocalizations'] = name_localizations
        if description_localizations:
            base['descriptionLocalizations'] = description_localizations
        base['options'] = [await child.get_translated_payload(tree, translator) for child in self._children.values()]
        return base

    def to_dict(self, tree: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            'name': self.name,
            'description': self.description,
            'options': [child.to_dict(tree) for child in self._children.values()],
        }
        if self.parent is None:
            base['type'] = AppCommandType.chat_input.value
            if self.nsfw:
                base['nsfw'] = True
            base['defaultMemberPermissions'] = (
                None if self.default_permissions is None else str(self.default_permissions.value)
            )
            contexts = self.allowed_contexts if self.allowed_contexts is not None else getattr(tree, 'allowed_contexts', None)
            if self.guild_only and self.allowed_contexts is None:
                contexts = AppCommandContext(guild=True)
            payload = _contexts_payload(contexts) if contexts is not None and contexts.value else None
            if payload is not None:
                base['contexts'] = payload
        else:
            base['type'] = AppCommandOptionType.subcommand_group.bisim_name

        return base

    @property
    def root_parent(self) -> Optional[Group]:
        """Optional[:class:`Group`]: The parent of this group."""
        return self.parent

    @property
    def qualified_name(self) -> str:
        """:class:`str`: Returns the fully qualified group name.

        The qualified name includes the parent name as well. For example,
        in a group like ``/foo bar`` the qualified name is ``foo bar``.
        """
        if self.parent is None:
            return self.name
        return f'{self.parent.name} {self.name}'

    def _get_internal_command(self, name: str) -> Optional[Union[Command[Any, ..., Any], Group]]:
        return self._children.get(name)

    @property
    def commands(self) -> List[Union[Command[Any, ..., Any], Group]]:
        """List[Union[:class:`Command`, :class:`Group`]]: The commands that this group contains."""
        return list(self._children.values())

    def walk_commands(self) -> Generator[Union[Command[Any, ..., Any], Group], None, None]:
        """An iterator that recursively walks through all commands that this group contains.

        Yields
        ---------
        Union[:class:`Command`, :class:`Group`]
            The commands in this group.
        """
        for command in self._children.values():
            yield command
            if isinstance(command, Group):
                yield from command.walk_commands()

    async def on_error(self, interaction: Interaction[Any], error: AppCommandError, /) -> None:
        """|coro|

        A callback that is called when a child's command raises an :exc:`AppCommandError`.

        To get the command that failed, :attr:`bisim.Interaction.command` should be used.

        The default implementation does nothing.

        Parameters
        -----------
        interaction: :class:`~bisim.Interaction`
            The interaction that is being handled.
        error: :exc:`AppCommandError`
            The exception that was raised.
        """
        pass

    on_error.__bisim_app_commands_base_function__ = None  # type: ignore

    def error(self, coro: Callable[..., Coro[Any]]) -> Callable[..., Coro[Any]]:
        """A decorator that registers a coroutine as a local error handler.

        The local error handler is called whenever an exception is raised in a child command.
        The error handler must take 2 parameters, the interaction and the error.

        The error passed will be derived from :exc:`AppCommandError`.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the local error handler.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine, or is an invalid coroutine.
        """
        if not inspect.iscoroutinefunction(coro):
            raise TypeError('The error handler must be a coroutine.')

        params = inspect.signature(coro).parameters
        if len(params) != 2:
            raise TypeError('The error handler must have 2 parameters.')

        self.on_error = coro  # type: ignore
        return coro

    async def interaction_check(self, interaction: Interaction[Any], /) -> bool:
        """|coro|

        A callback that is called when an interaction happens within the group
        that checks whether a command inside the group should be executed.

        This is useful to override if, for example, you want to ensure that the
        interaction author is a given user.

        The default implementation of this returns ``True``.

        .. note::

            If an exception occurs within the body then the check
            is considered a failure and error handlers such as
            :meth:`on_error` is called. See :exc:`AppCommandError`
            for more information.

        Parameters
        -----------
        interaction: :class:`~bisim.Interaction`
            The interaction that occurred.

        Returns
        ---------
        :class:`bool`
            Whether the view children's callbacks should be called.
        """
        return True

    def add_command(self, command: Union[Command[Any, ..., Any], Group], /, *, override: bool = False) -> None:
        """Adds a command or group to this group's internal list of commands.

        Parameters
        -----------
        command: Union[:class:`Command`, :class:`Group`]
            The command or group to add.
        override: :class:`bool`
            Whether to override a pre-existing command or group with the same name.
            If ``False`` then an exception is raised.

        Raises
        -------
        CommandAlreadyRegistered
            The command or group is already registered. Note that the :attr:`CommandAlreadyRegistered.guild_id`
            attribute will always be ``None`` in this case.
        ValueError
            There are too many commands already registered or the group is too
            deeply nested.
        TypeError
            The wrong command type was passed.
        """
        if not isinstance(command, (Command, Group)):
            raise TypeError(f'expected Command or Group not {command.__class__.__name__}')

        if isinstance(command, Group) and self.parent is not None:
            raise ValueError(f'{command.name!r} is too nested, groups can only be nested at most one level')

        if not override and command.name in self._children:
            raise CommandAlreadyRegistered(command.name, guild_id=None)

        self._children[command.name] = command
        command.parent = self
        if len(self._children) > 25:
            raise ValueError('maximum number of child commands exceeded')

    def remove_command(self, name: str, /) -> Optional[Union[Command[Any, ..., Any], Group]]:
        """Removes a command or group from the internal list of commands.

        Parameters
        -----------
        name: :class:`str`
            The name of the command or group to remove.

        Returns
        --------
        Optional[Union[:class:`~bisim.app_commands.Command`, :class:`~bisim.app_commands.Group`]]
            The command that was removed. If nothing was removed
            then ``None`` is returned instead.
        """
        self._children.pop(name, None)
        return None

    def get_command(self, name: str, /) -> Optional[Union[Command[Any, ..., Any], Group]]:
        """Retrieves a command or group from its name.

        Parameters
        -----------
        name: :class:`str`
            The name of the command or group to retrieve.

        Returns
        --------
        Optional[Union[:class:`~bisim.app_commands.Command`, :class:`~bisim.app_commands.Group`]]
            The command or group that was retrieved. If nothing was found
            then ``None`` is returned instead.
        """
        return self._children.get(name)

    def command(
        self,
        *,
        name: Union[str, locale_str] = MISSING,
        description: Union[str, locale_str] = MISSING,
        nsfw: bool = False,
        auto_locale_strings: bool = True,
        extras: Dict[Any, Any] = MISSING,
    ) -> Callable[[CommandCallback], Command[Any, ..., Any]]:
        """A decorator that creates an application command from a regular function under this group.

        Parameters
        ------------
        name: Union[:class:`str`, :class:`locale_str`]
            The name of the application command. If not given, it defaults to a lower-case
            version of the callback name.
        description: Union[:class:`str`, :class:`locale_str`]
            The description of the application command. This shows up in the UI to describe
            the application command. If not given, it defaults to the first line of the docstring
            of the callback shortened to 100 characters.
        nsfw: :class:`bool`
            Accepted for compatibility. Bisim does not limit commands to age-restricted channels.
        auto_locale_strings: :class:`bool`
            If this is set to ``True``, then all translatable strings will implicitly
            be wrapped into :class:`locale_str` rather than :class:`str`.
        extras: :class:`dict`
            A dictionary that can be used to store extraneous data.
            The library will not touch any values or keys within this dictionary.
        """

        def decorator(func: CommandCallback) -> Command[Any, ..., Any]:
            if not inspect.iscoroutinefunction(func):
                raise TypeError('command function must be a coroutine function')

            if description is MISSING:
                if func.__doc__ is None:
                    desc = '…'
                else:
                    desc = _shorten(func.__doc__)
            else:
                desc = description

            command = Command(
                name=name if name is not MISSING else func.__name__,
                description=desc,
                callback=func,
                nsfw=nsfw,
                parent=self,
                auto_locale_strings=auto_locale_strings,
                extras=extras,
            )
            self.add_command(command)
            return command

        return decorator


def command(
    *,
    name: Union[str, locale_str] = MISSING,
    description: Union[str, locale_str] = MISSING,
    nsfw: bool = False,
    auto_locale_strings: bool = True,
    extras: Dict[Any, Any] = MISSING,
) -> Callable[[CommandCallback], Command[Any, ..., Any]]:
    """Creates an application command from a regular function.

    Parameters
    ------------
    name: :class:`str`
        The name of the application command. If not given, it defaults to a lower-case
        version of the callback name.
    description: :class:`str`
        The description of the application command. This shows up in the UI to describe
        the application command. If not given, it defaults to the first line of the docstring
        of the callback shortened to 100 characters.
    nsfw: :class:`bool`
        Accepted for compatibility. Bisim does not limit commands to age-restricted channels.
    auto_locale_strings: :class:`bool`
        If this is set to ``True``, then all translatable strings will implicitly
        be wrapped into :class:`locale_str` rather than :class:`str`.
    extras: :class:`dict`
        A dictionary that can be used to store extraneous data.
        The library will not touch any values or keys within this dictionary.
    """

    def decorator(func: CommandCallback) -> Command[Any, ..., Any]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError('command function must be a coroutine function')

        if description is MISSING:
            if func.__doc__ is None:
                desc = '…'
            else:
                desc = _shorten(func.__doc__)
        else:
            desc = description

        return Command(
            name=name if name is not MISSING else func.__name__,
            description=desc,
            callback=func,
            parent=None,
            nsfw=nsfw,
            auto_locale_strings=auto_locale_strings,
            extras=extras,
        )

    return decorator


def context_menu(
    *,
    name: Union[str, locale_str] = MISSING,
    nsfw: bool = False,
    auto_locale_strings: bool = True,
    extras: Dict[Any, Any] = MISSING,
) -> Callable[[ContextMenuCallback], ContextMenu]:
    """Creates an application command context menu from a regular function.

    This function must have a signature of :class:`~bisim.Interaction` as its first parameter
    and taking either a :class:`~bisim.Member`, :class:`~bisim.User`, or :class:`~bisim.Message`,
    or a :obj:`typing.Union` of ``Member`` and ``User`` as its second parameter.

    Examples
    ---------

    .. code-block:: python3

        @app_commands.context_menu()
        async def react(interaction: bisim.Interaction, message: bisim.Message):
            await interaction.response.send_message('Very cool message!', ephemeral=True)

        @app_commands.context_menu()
        async def ban(interaction: bisim.Interaction, user: bisim.Member):
            await interaction.response.send_message(f'Should I actually ban {user}...', ephemeral=True)

    Parameters
    ------------
    name: Union[:class:`str`, :class:`locale_str`]
        The name of the context menu command. If not given, it defaults to a title-case
        version of the callback name. Note that unlike regular slash commands this can
        have spaces and upper case characters in the name.
    nsfw: :class:`bool`
        Accepted for compatibility. Bisim does not limit commands to age-restricted channels.
    auto_locale_strings: :class:`bool`
        If this is set to ``True``, then all translatable strings will implicitly
        be wrapped into :class:`locale_str` rather than :class:`str`.
    extras: :class:`dict`
        A dictionary that can be used to store extraneous data.
        The library will not touch any values or keys within this dictionary.
    """

    def decorator(func: ContextMenuCallback) -> ContextMenu:
        if not inspect.iscoroutinefunction(func):
            raise TypeError('context menu function must be a coroutine function')

        actual_name = func.__name__.title() if name is MISSING else name
        return ContextMenu(
            name=actual_name,
            nsfw=nsfw,
            callback=func,
            auto_locale_strings=auto_locale_strings,
            extras=extras,
        )

    return decorator


def describe(**parameters: Union[str, locale_str]) -> Callable[[T], T]:
    r'''Describes the given parameters by their name using the key of the keyword argument
    as the name.

    Example:

    .. code-block:: python3

        @app_commands.command(description='Bans a member')
        @app_commands.describe(member='the member to ban')
        async def ban(interaction: bisim.Interaction, member: bisim.Member):
            await interaction.response.send_message(f'Banned {member}')

    Alternatively, you can describe parameters using Google, Sphinx, or Numpy style docstrings.

    Parameters
    -----------
    \*\*parameters: Union[:class:`str`, :class:`locale_str`]
        The description of the parameters.

    Raises
    --------
    TypeError
        The parameter name is not found.
    '''

    def decorator(inner: T) -> T:
        if isinstance(inner, Command):
            _populate_descriptions(inner._params, parameters)
        else:
            try:
                inner.__bisim_app_commands_param_description__.update(parameters)  # type: ignore
            except AttributeError:
                inner.__bisim_app_commands_param_description__ = parameters  # type: ignore

        return inner

    return decorator


def rename(**parameters: Union[str, locale_str]) -> Callable[[T], T]:
    r"""Renames the given parameters by their name using the key of the keyword argument
    as the name.

    This renames the parameter within the Bisim UI. When referring to the parameter in other
    decorators, the parameter name used in the function is used instead of the renamed one.

    Example:

    .. code-block:: python3

        @app_commands.command()
        @app_commands.rename(the_member_to_ban='member')
        async def ban(interaction: bisim.Interaction, the_member_to_ban: bisim.Member):
            await interaction.response.send_message(f'Banned {the_member_to_ban}')

    Parameters
    -----------
    \*\*parameters: Union[:class:`str`, :class:`locale_str`]
        The name of the parameters.

    Raises
    --------
    ValueError
        The parameter name is already used by another parameter.
    TypeError
        The parameter name is not found.
    """

    def decorator(inner: T) -> T:
        if isinstance(inner, Command):
            _populate_renames(inner._params, parameters)
        else:
            try:
                inner.__bisim_app_commands_param_rename__.update(parameters)  # type: ignore
            except AttributeError:
                inner.__bisim_app_commands_param_rename__ = parameters  # type: ignore

        return inner

    return decorator


def choices(**parameters: List[Choice[Any]]) -> Callable[[T], T]:
    r"""Instructs the given parameters by their name to use the given choices for their choices.

    Example:

    .. code-block:: python3

        @app_commands.command()
        @app_commands.describe(fruits='fruits to choose from')
        @app_commands.choices(fruits=[
            Choice(name='apple', value=1),
            Choice(name='banana', value=2),
            Choice(name='cherry', value=3),
        ])
        async def fruit(interaction: bisim.Interaction, fruits: Choice[int]):
            await interaction.response.send_message(f'Your favourite fruit is {fruits.name}.')

    .. note::

        This is not the only way to provide choices to a command. There are two more ergonomic ways
        of doing this. The first one is to use a :obj:`typing.Literal` annotation:

        .. code-block:: python3

            @app_commands.command()
            @app_commands.describe(fruits='fruits to choose from')
            async def fruit(interaction: bisim.Interaction, fruits: Literal['apple', 'banana', 'cherry']):
                await interaction.response.send_message(f'Your favourite fruit is {fruits}.')

        The second way is to use an :class:`enum.Enum`:

        .. code-block:: python3

            class Fruits(enum.Enum):
                apple = 1
                banana = 2
                cherry = 3

            @app_commands.command()
            @app_commands.describe(fruits='fruits to choose from')
            async def fruit(interaction: bisim.Interaction, fruits: Fruits):
                await interaction.response.send_message(f'Your favourite fruit is {fruits}.')

    Parameters
    -----------
    \*\*parameters
        The choices of the parameters.

    Raises
    --------
    TypeError
        The parameter name is not found or the parameter type was incorrect.
    """

    def decorator(inner: T) -> T:
        if isinstance(inner, Command):
            _populate_choices(inner._params, parameters)
        else:
            try:
                inner.__bisim_app_commands_param_choices__.update(parameters)  # type: ignore
            except AttributeError:
                inner.__bisim_app_commands_param_choices__ = parameters  # type: ignore

        return inner

    return decorator


def autocomplete(**parameters: AutocompleteCallback) -> Callable[[T], T]:
    r"""Associates the given parameters with the given autocomplete callback.

    Autocomplete is only supported on types that have :class:`str`, :class:`int`, or :class:`float`
    values.

    :func:`Checks <check>` are supported, however they must be attached to the autocomplete
    callback in order to work. Checks attached to the command are ignored when invoking the autocomplete
    callback.

    Example:

    .. code-block:: python3

        async def fruit_autocomplete(
            interaction: bisim.Interaction,
            current: str,
        ) -> List[app_commands.Choice[str]]:
            fruits = ['Banana', 'Pineapple', 'Apple', 'Watermelon', 'Melon', 'Cherry']
            return [
                app_commands.Choice(name=fruit, value=fruit)
                for fruit in fruits if current.lower() in fruit.lower()
            ]

        @app_commands.command()
        @app_commands.autocomplete(fruit=fruit_autocomplete)
        async def fruits(interaction: bisim.Interaction, fruit: str):
            await interaction.response.send_message(f'Your favourite fruit seems to be {fruit}')

    Parameters
    -----------
    \*\*parameters
        The parameters to mark as autocomplete.

    Raises
    --------
    TypeError
        The parameter name is not found or the parameter type was incorrect.
    """

    def decorator(inner: T) -> T:
        if isinstance(inner, Command):
            _populate_autocomplete(inner._params, parameters)
        else:
            try:
                inner.__bisim_app_commands_param_autocomplete__.update(parameters)  # type: ignore
            except AttributeError:
                inner.__bisim_app_commands_param_autocomplete__ = parameters  # type: ignore

        return inner

    return decorator


def guilds(*guild_ids: Union[Snowflake, int]) -> Callable[[T], T]:
    r"""Associates the given guilds with the command.

    When the command instance is added to a :class:`CommandTree`, the guilds that are
    specified by this decorator become the default guilds that it's added to rather
    than being a global command.

    Example:

    .. code-block:: python3

        @app_commands.command()
        @app_commands.guilds(bisim.Object(id=123))
        async def test(interaction: bisim.Interaction):
            await interaction.response.send_message('Hello!')

    Parameters
    -----------
    \*guild_ids: Union[:class:`int`, :class:`~bisim.abc.Snowflake`]
        The guilds to associate this command with. The command tree will
        use this as the default when added rather than adding it as a global
        command.
    """

    defaults: List[int] = [g if isinstance(g, int) else g.id for g in guild_ids]

    def decorator(inner: T) -> T:
        if isinstance(inner, (Group, ContextMenu)):
            inner._guild_ids = defaults
        elif isinstance(inner, Command):
            if inner.parent is not None:
                raise ValueError('child commands of a group cannot have default guilds set')

            inner._guild_ids = defaults
        else:
            inner.__bisim_app_commands_default_guilds__ = defaults  # type: ignore

        return inner

    return decorator


def check(predicate: Check) -> Callable[[T], T]:
    r"""A decorator that adds a check to an application command.

    These checks should be predicates that take in a single parameter taking
    a :class:`~bisim.Interaction`. If the check returns a ``False``\-like value then
    during invocation a :exc:`CheckFailure` exception is raised and sent to
    the appropriate error handlers.

    These checks can be either a coroutine or not.

    Examples
    ---------

    Creating a basic check to see if the command invoker is you.

    .. code-block:: python3

        def check_if_it_is_me(interaction: bisim.Interaction) -> bool:
            return interaction.user.id == 85309593344815104

        @tree.command()
        @app_commands.check(check_if_it_is_me)
        async def only_for_me(interaction: bisim.Interaction):
            await interaction.response.send_message('I know you!', ephemeral=True)

    Transforming common checks into its own decorator:

    .. code-block:: python3

        def is_me():
            def predicate(interaction: bisim.Interaction) -> bool:
                return interaction.user.id == 85309593344815104
            return app_commands.check(predicate)

        @tree.command()
        @is_me()
        async def only_me(interaction: bisim.Interaction):
            await interaction.response.send_message('Only you!')

    Parameters
    -----------
    predicate: Callable[[:class:`~bisim.Interaction`], :class:`bool`]
        The predicate to check if the command should be invoked.
    """

    def decorator(func: T) -> T:
        if isinstance(func, (Command, ContextMenu)):
            func.checks.append(predicate)
        else:
            if not hasattr(func, '__bisim_app_commands_checks__'):
                func.__bisim_app_commands_checks__ = []  # type: ignore

            func.__bisim_app_commands_checks__.append(predicate)  # type: ignore

        return func

    return decorator


def _create_contexts(*, guilds: bool, dms: bool, private_channels: bool) -> AppCommandContext:
    return AppCommandContext(guild=guilds, dm_channel=dms, private_channel=private_channels)


def _apply_contexts(f: T, contexts: AppCommandContext, *, guild_only: bool = False) -> T:
    if isinstance(f, (Command, Group, ContextMenu)):
        f.allowed_contexts = contexts
        if guild_only:
            f.guild_only = True
    else:
        f.__bisim_app_commands_contexts__ = contexts  # type: ignore
        if guild_only:
            f.__bisim_app_commands_guild_only__ = True  # type: ignore
    return f


def guild_only(func: Optional[T] = None) -> Union[T, Callable[[T], T]]:
    """A decorator that indicates this command can only be used in a guild context.

    This is **not** implemented as a :func:`check`, and is instead verified by Bisim server side.
    Therefore, there is no error handler called when a command is used within a private message.

    This decorator can be called with or without parentheses.

    This decorator does nothing in subcommands and is ignored.

    Examples
    ---------

    .. code-block:: python3

        @app_commands.command()
        @app_commands.guild_only()
        async def my_guild_only_command(interaction: bisim.Interaction) -> None:
            await interaction.response.send_message('I am only available in guilds!')
    """

    def inner(f: T) -> T:
        return _apply_contexts(f, _create_contexts(guilds=True, dms=False, private_channels=False), guild_only=True)

    if func is None:
        return inner
    else:
        return inner(func)


def private_channel_only(func: Optional[T] = None) -> Union[T, Callable[[T], T]]:
    """A decorator that indicates this command can only be used in the context of DMs and group DMs.

    On Bisim a command runs in a server or in the DM with the bot, so this
    keeps the command to the DM with the bot.

    This decorator can be called with or without parentheses.
    """

    def inner(f: T) -> T:
        return _apply_contexts(f, _create_contexts(guilds=False, dms=True, private_channels=True))

    if func is None:
        return inner
    else:
        return inner(func)


def dm_only(func: Optional[T] = None) -> Union[T, Callable[[T], T]]:
    """A decorator that indicates this command can only be used in the context of the DM with the bot.

    This is **not** implemented as a :func:`check`, and is instead verified by Bisim server side.

    This decorator can be called with or without parentheses.

    Examples
    ---------

    .. code-block:: python3

        @app_commands.command()
        @app_commands.dm_only()
        async def my_dm_only_command(interaction: bisim.Interaction) -> None:
            await interaction.response.send_message('I am only available in DMs!')
    """

    def inner(f: T) -> T:
        return _apply_contexts(f, _create_contexts(guilds=False, dms=True, private_channels=False))

    if func is None:
        return inner
    else:
        return inner(func)


def allowed_contexts(guilds: bool = MISSING, dms: bool = MISSING, private_channels: bool = MISSING) -> Callable[[T], T]:
    """A decorator that indicates this command can only be used in certain contexts.

    Valid contexts on Bisim are guilds and the DM with the bot.

    Examples
    ---------

    .. code-block:: python3

        @app_commands.command()
        @app_commands.allowed_contexts(guilds=True, dms=False)
        async def my_command(interaction: bisim.Interaction) -> None:
            await interaction.response.send_message('I am only available in guilds!')
    """

    def inner(f: T) -> T:
        contexts = AppCommandContext()
        if guilds is not MISSING:
            contexts.guild = guilds
        if dms is not MISSING:
            contexts.dm_channel = dms
        if private_channels is not MISSING:
            contexts.private_channel = private_channels
        return _apply_contexts(f, contexts)

    return inner


def guild_install(func: Optional[T] = None) -> Union[T, Callable[[T], T]]:
    """A decorator that indicates this command should be installed in guilds.

    Bisim apps are always installed to servers, so this is accepted and changes nothing.
    """

    def inner(f: T) -> T:
        return f

    if func is None:
        return inner
    return inner(func)


def user_install(func: Optional[T] = None) -> Union[T, Callable[[T], T]]:
    """A decorator that indicates this command should be installed for users.

    Bisim has no user-installed apps, so this is accepted and changes nothing.
    """

    def inner(f: T) -> T:
        return f

    if func is None:
        return inner
    return inner(func)


def allowed_installs(guilds: bool = MISSING, users: bool = MISSING) -> Callable[[T], T]:
    """A decorator that indicates this command should be installed in certain contexts.

    Bisim apps are always installed to servers, so this is accepted and changes nothing.
    """

    def inner(f: T) -> T:
        return f

    return inner


def default_permissions(perms_obj: Optional[Permissions] = None, /, **perms: bool) -> Callable[[T], T]:
    r"""A decorator that sets the default permissions needed to execute this command.

    When this decorator is used, members must have these permissions to execute the command. Bisim
    checks them when the command is used, and server administrators can always use it. There are no per
    command overrides.

    Setting an empty permissions field, including via calling this with no arguments, will disallow anyone
    except server administrators from using the command in a guild.

    This is sent to Bisim server side, and is not a :func:`check`. Therefore, error handlers are not called.

    This decorator does nothing in subcommands and is ignored.

    .. note::

        To check permissions in the bot instead, with an error your error handler can answer, use
        :func:`~bisim.app_commands.checks.has_permissions`.

    Parameters
    -----------
    \*\*perms: :class:`bool`
        Keyword arguments denoting the permissions to set as the default.
    perms_obj: :class:`~bisim.Permissions`
        A permissions object as positional argument. This can be used in combination with ``**perms``.

    Example
    ---------

    .. code-block:: python3

        @app_commands.command()
        @app_commands.default_permissions(manage_messages=True)
        async def test(interaction: bisim.Interaction):
            await interaction.response.send_message('You may or may not have manage messages.')
    """

    if perms_obj is not None:
        permissions = perms_obj | Permissions(**perms)
    else:
        permissions = Permissions(**perms)

    def decorator(func: T) -> T:
        if isinstance(func, (Command, Group, ContextMenu)):
            func.default_permissions = permissions
        else:
            func.__bisim_app_commands_default_permissions__ = permissions  # type: ignore

        return func

    return decorator

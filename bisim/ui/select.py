from __future__ import annotations

import inspect
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from .. import utils
from ..components import SelectDefaultValue, SelectMenu, SelectOption
from ..enums import ChannelType, ComponentType, SelectDefaultValueType
from ..member import Member
from ..object import Object
from ..partial_emoji import PartialEmoji
from ..role import Role
from ..user import User
from .item import Item, ItemCallbackType

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..emoji import Emoji
    from ..interactions import Interaction
    from .view import View

__all__ = (
    'Select',
    'UserSelect',
    'RoleSelect',
    'MentionableSelect',
    'ChannelSelect',
    'select',
)

V = TypeVar('V', bound='View', covariant=True)
BaseSelectT = TypeVar('BaseSelectT', bound='BaseSelect[Any]')
SelectT = TypeVar('SelectT', bound='Select[Any]')


def _resolve_value(interaction: Interaction[Any], raw: str, resolved: Dict[str, Any], kinds: Sequence[str]) -> Any:
    """Turns one selected id into a member, user, role or channel."""
    state = interaction._state
    guild = interaction.guild
    try:
        value_id = int(raw)
    except (TypeError, ValueError):
        return raw

    if 'member' in kinds or 'user' in kinds:
        members = resolved.get('members') or {}
        users = resolved.get('users') or {}
        member_data = members.get(raw) if isinstance(members, dict) else None
        user_data = users.get(raw) if isinstance(users, dict) else None
        if guild is not None:
            cached = guild.get_member(value_id)
            if cached is not None:
                return cached
            if member_data is not None:
                payload = dict(member_data)
                payload.setdefault('userId', raw)
                if user_data is not None:
                    payload.setdefault('user', user_data)
                return Member(data=payload, guild=guild, state=state)
        if user_data is not None:
            return state.store_user(user_data)
        user = state.get_user(value_id)
        if user is not None:
            return user

    if 'role' in kinds and guild is not None:
        role = guild.get_role(value_id)
        if role is not None:
            return role
        roles = resolved.get('roles') or {}
        if isinstance(roles, dict) and raw in roles:
            return Role(guild=guild, state=state, data=roles[raw])

    if 'channel' in kinds:
        channel = state.get_channel(value_id)
        if channel is not None:
            return channel

    cls: Any = None
    if kinds == ('role',):
        cls = Role
    elif kinds in (('user',), ('member', 'user')):
        cls = User
    return Object(id=value_id, type=cls) if cls is not None else Object(id=value_id)


def _handle_select_defaults(defaults: Any, component_type: ComponentType) -> List[SelectDefaultValue]:
    """discord.py's rule for ``default_values``: users, members, roles, channels,
    :class:`~bisim.Object` (with a ``type`` where the select takes more than one
    kind) or :class:`~bisim.SelectDefaultValue`, each turned into an id and its kind."""
    if defaults is utils.MISSING or not defaults:
        return []

    from ..abc import GuildChannel
    from ..app_commands.models import AppCommandChannel, AppCommandThread
    from ..user import BaseUser

    supported: Dict[ComponentType, Tuple[type, ...]] = {
        ComponentType.user_select: (BaseUser, Member, Object),
        ComponentType.role_select: (Role, Object),
        ComponentType.channel_select: (GuildChannel, AppCommandChannel, AppCommandThread, Object),
        ComponentType.mentionable_select: (BaseUser, Member, Role, Object),
    }
    allowed = supported.get(component_type)
    if allowed is None:
        raise TypeError('only user, role, mentionable and channel selects take default_values')

    values: List[SelectDefaultValue] = []
    for obj in defaults:
        if isinstance(obj, SelectDefaultValue):
            values.append(obj)
            continue

        object_type: Any = obj.type if isinstance(obj, Object) else obj.__class__
        if not isinstance(object_type, type) or not issubclass(object_type, allowed):
            names = utils._human_join([c.__name__ for c in allowed])
            raise TypeError(f'Expected an instance of {names} not {getattr(object_type, "__name__", object_type)}')

        if object_type is Object:
            if component_type is ComponentType.mentionable_select:
                raise ValueError(
                    'Object must have a type specified for the chosen select type. Please pass one using the `type`` kwarg.'
                )
            kind = {
                ComponentType.user_select: SelectDefaultValueType.user,
                ComponentType.role_select: SelectDefaultValueType.role,
                ComponentType.channel_select: SelectDefaultValueType.channel,
            }[component_type]
        elif issubclass(object_type, Role):
            kind = SelectDefaultValueType.role
        elif issubclass(object_type, (BaseUser, Member)):
            kind = SelectDefaultValueType.user
        else:
            kind = SelectDefaultValueType.channel

        values.append(SelectDefaultValue(id=obj.id, type=kind))

    return values


class BaseSelect(Item[V]):
    """The base Select model that all other Select models inherit from.

    This class inherits from :class:`Item` and implements the common attributes.
    """

    __item_repr_attributes__: Tuple[str, ...] = (
        'placeholder',
        'min_values',
        'max_values',
        'disabled',
    )
    __component_attributes__: Tuple[str, ...] = (
        'custom_id',
        'placeholder',
        'min_values',
        'max_values',
        'disabled',
    )
    _resolve_kinds: Tuple[str, ...] = ()

    def __init__(
        self,
        type: ComponentType,
        *,
        custom_id: str = utils.MISSING,
        row: Optional[int] = None,
        placeholder: Optional[str] = None,
        min_values: Optional[int] = None,
        max_values: Optional[int] = None,
        disabled: bool = False,
        required: bool = False,
        options: List[SelectOption] = utils.MISSING,
        channel_types: List[ChannelType] = utils.MISSING,
        default_values: Sequence[SelectDefaultValue] = utils.MISSING,
        id: Optional[int] = None,
    ) -> None:
        super().__init__()
        self._provided_custom_id = custom_id is not utils.MISSING
        custom_id = os.urandom(16).hex() if custom_id is utils.MISSING else custom_id
        if not isinstance(custom_id, str):
            raise TypeError(f'expected custom_id to be str not {custom_id.__class__.__name__}')
        self._underlying = SelectMenu._raw_construct(
            type=type,
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values if min_values is not None else 1,
            max_values=max_values if max_values is not None else 1,
            disabled=disabled,
            channel_types=[] if channel_types is utils.MISSING else list(channel_types),
            options=[] if options is utils.MISSING else list(options),
            default_values=_handle_select_defaults(default_values, type),
            required=required,
            id=id,
        )

        self.row = row
        self.id = id
        self._values: List[Any] = []

    @property
    def values(self) -> List[Any]:
        """The values selected by the user (after an interaction)."""
        return list(self._values)

    @property
    def custom_id(self) -> str:
        """:class:`str`: The ID of the select menu that gets received during an interaction."""
        return self._underlying.custom_id

    @custom_id.setter
    def custom_id(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError('custom_id must be a str')

        self._underlying.custom_id = value
        self._provided_custom_id = True

    @property
    def placeholder(self) -> Optional[str]:
        """Optional[:class:`str`]: The placeholder text that is shown if nothing is selected, if any."""
        return self._underlying.placeholder

    @placeholder.setter
    def placeholder(self, value: Optional[str]) -> None:
        if value is not None and not isinstance(value, str):
            raise TypeError('placeholder must be None or str')

        self._underlying.placeholder = value

    @property
    def min_values(self) -> int:
        """:class:`int`: The minimum number of items that must be chosen for this select menu."""
        return self._underlying.min_values

    @min_values.setter
    def min_values(self, value: int) -> None:
        self._underlying.min_values = int(value)

    @property
    def max_values(self) -> int:
        """:class:`int`: The maximum number of items that can be chosen for this select menu."""
        return self._underlying.max_values

    @max_values.setter
    def max_values(self, value: int) -> None:
        self._underlying.max_values = int(value)

    @property
    def disabled(self) -> bool:
        """:class:`bool`: Whether the select is disabled or not."""
        return self._underlying.disabled

    @disabled.setter
    def disabled(self, value: bool) -> None:
        self._underlying.disabled = bool(value)

    @property
    def width(self) -> int:
        return 5

    @property
    def type(self) -> ComponentType:
        """:class:`.ComponentType`: The type of this component."""
        return self._underlying.type

    def to_component_dict(self) -> Dict[str, Any]:
        return self._underlying.to_dict()

    def _refresh_component(self, component: SelectMenu) -> None:
        self._underlying = component

    def _refresh_state(self, interaction: Interaction[Any], data: Dict[str, Any]) -> None:
        raw_values = data.get('values', []) or []
        if not self._resolve_kinds:
            self._values = list(raw_values)
            return
        resolved = data.get('resolved') or {}
        self._values = [_resolve_value(interaction, str(v), resolved, self._resolve_kinds) for v in raw_values]

    @classmethod
    def from_component(cls, component: SelectMenu) -> Self:
        kwargs = {key: getattr(component, key) for key in cls.__component_attributes__}
        return cls(**kwargs)

    def is_dispatchable(self) -> bool:
        return True


class Select(BaseSelect[V]):
    """Represents a UI select menu with a list of custom options. This is represented
    to the user as a dropdown menu.

    Parameters
    ------------
    custom_id: :class:`str`
        The ID of the select menu that gets received during an interaction.
        If not given then one is generated for you.
        Can only be up to 100 characters.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
        Can only be up to 150 characters.
    min_values: :class:`int`
        The minimum number of items that must be chosen for this select menu.
        Defaults to 1 and must be between 0 and 25.
    max_values: :class:`int`
        The maximum number of items that must be chosen for this select menu.
        Defaults to 1 and must be between 1 and 25.
    options: List[:class:`bisim.SelectOption`]
        A list of options that can be selected in this menu.
        Can only contain up to 25 items.
    disabled: :class:`bool`
        Whether the select is disabled or not.
    required: :class:`bool`
        Whether the select is required. Only applicable within modals.
    row: Optional[:class:`int`]
        The relative row this select menu belongs to. A Bisim component can only have 5
        rows. By default, items are arranged automatically into those 5 rows. If you'd
        like to control the relative positioning of the row then passing an index is advised.
        For example, row=1 will show up before row=2. Defaults to ``None``, which is automatic
        ordering. The row number must be between 0 and 4 (i.e. zero indexed).
    id: Optional[:class:`int`]
        Accepted for compatibility.
    """

    __component_attributes__ = BaseSelect.__component_attributes__ + ('options',)

    def __init__(
        self,
        *,
        custom_id: str = utils.MISSING,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        options: List[SelectOption] = utils.MISSING,
        disabled: bool = False,
        required: bool = True,
        row: Optional[int] = None,
        id: Optional[int] = None,
    ) -> None:
        super().__init__(
            self.type,
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            required=required,
            options=options,
            row=row,
            id=id,
        )

    @property
    def values(self) -> List[str]:
        """List[:class:`str`]: A list of values that have been selected by the user."""
        return list(self._values)

    @property
    def type(self) -> ComponentType:
        """:class:`.ComponentType`: The type of this component."""
        return ComponentType.string_select

    @property
    def options(self) -> List[SelectOption]:
        """List[:class:`bisim.SelectOption`]: A list of options that can be selected in this menu."""
        return self._underlying.options

    @options.setter
    def options(self, value: List[SelectOption]) -> None:
        if not isinstance(value, list):
            raise TypeError('options must be a list of SelectOption')
        if not all(isinstance(obj, SelectOption) for obj in value):
            raise TypeError('all list items must subclass SelectOption')

        self._underlying.options = value

    def add_option(
        self,
        *,
        label: str,
        value: str = utils.MISSING,
        description: Optional[str] = None,
        emoji: Optional[Union[str, Emoji, PartialEmoji]] = None,
        default: bool = False,
    ) -> None:
        """Adds an option to the select menu.

        To append a pre-existing :class:`bisim.SelectOption` use the
        :meth:`append_option` method instead.

        Parameters
        -----------
        label: :class:`str`
            The label of the option. This is displayed to users.
            Can only be up to 100 characters.
        value: :class:`str`
            The value of the option. This is not displayed to users.
            If not given, defaults to the label.
            Can only be up to 100 characters.
        description: Optional[:class:`str`]
            An additional description of the option, if any.
            Can only be up to 100 characters.
        emoji: Optional[Union[:class:`str`, :class:`.Emoji`, :class:`.PartialEmoji`]]
            The emoji of the option, if available.
        default: :class:`bool`
            Whether this option is selected by default.

        Raises
        -------
        ValueError
            The number of options exceeds 25.
        """
        option = SelectOption(label=label, value=value, description=description, emoji=emoji, default=default)
        self.append_option(option)

    def append_option(self, option: SelectOption) -> None:
        """Appends an option to the select menu.

        Parameters
        -----------
        option: :class:`bisim.SelectOption`
            The option to append to the select menu.

        Raises
        -------
        ValueError
            The number of options exceeds 25.
        """
        if len(self._underlying.options) >= 25:
            raise ValueError('maximum number of options already provided')

        self._underlying.options.append(option)


class UserSelect(BaseSelect[V]):
    """Represents a UI select menu with a list of predefined options with the current members of the guild.

    If this is sent a private message, it will only allow the user to select the client
    or themselves. Every selected option in a private message will resolve to
    a :class:`bisim.User`.

    Parameters
    ------------
    custom_id: :class:`str`
        The ID of the select menu that gets received during an interaction.
        If not given then one is generated for you.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
    min_values: :class:`int`
        The minimum number of items that must be chosen for this select menu.
    max_values: :class:`int`
        The maximum number of items that must be chosen for this select menu.
    disabled: :class:`bool`
        Whether the select is disabled or not.
    default_values: Sequence[:class:`~bisim.abc.Snowflake`]
        A list of objects representing the users that should be selected by default.
        Number of items must be in range of ``min_values`` and ``max_values``.
    row: Optional[:class:`int`]
        The relative row this select menu belongs to.
    id: Optional[:class:`int`]
        Accepted for compatibility.
    """

    __component_attributes__ = BaseSelect.__component_attributes__ + ('default_values',)
    _resolve_kinds = ('member', 'user')

    def __init__(
        self,
        *,
        custom_id: str = utils.MISSING,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        required: bool = True,
        row: Optional[int] = None,
        default_values: Sequence[Any] = utils.MISSING,
        id: Optional[int] = None,
    ) -> None:
        super().__init__(
            self.type,
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            required=required,
            row=row,
            default_values=default_values,
            id=id,
        )

    @property
    def type(self) -> ComponentType:
        """:class:`.ComponentType`: The type of this component."""
        return ComponentType.user_select

    @property
    def default_values(self) -> List[SelectDefaultValue]:
        """List[:class:`bisim.SelectDefaultValue`]: A list of default values for the select menu."""
        return self._underlying.default_values

    @default_values.setter
    def default_values(self, value: Sequence[Any]) -> None:
        self._underlying.default_values = _handle_select_defaults(value, self.type)

    @property
    def values(self) -> List[Union[Member, User]]:
        """List[Union[:class:`bisim.Member`, :class:`bisim.User`]]: A list of members
        and users that have been selected by the user.
        """
        return list(self._values)


class RoleSelect(BaseSelect[V]):
    """Represents a UI select menu with a list of predefined options with the current roles of the guild.

    Please note that if you use this in a private message with a user, no roles will be displayed to the user.

    Parameters
    ------------
    custom_id: :class:`str`
        The ID of the select menu that gets received during an interaction.
        If not given then one is generated for you.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
    min_values: :class:`int`
        The minimum number of items that must be chosen for this select menu.
    max_values: :class:`int`
        The maximum number of items that must be chosen for this select menu.
    disabled: :class:`bool`
        Whether the select is disabled or not.
    default_values: Sequence[:class:`~bisim.abc.Snowflake`]
        A list of objects representing the roles that should be selected by default.
        Number of items must be in range of ``min_values`` and ``max_values``.
    row: Optional[:class:`int`]
        The relative row this select menu belongs to.
    id: Optional[:class:`int`]
        Accepted for compatibility.
    """

    __component_attributes__ = BaseSelect.__component_attributes__ + ('default_values',)
    _resolve_kinds = ('role',)

    def __init__(
        self,
        *,
        custom_id: str = utils.MISSING,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        required: bool = True,
        row: Optional[int] = None,
        default_values: Sequence[Any] = utils.MISSING,
        id: Optional[int] = None,
    ) -> None:
        super().__init__(
            self.type,
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            required=required,
            row=row,
            default_values=default_values,
            id=id,
        )

    @property
    def type(self) -> ComponentType:
        """:class:`.ComponentType`: The type of this component."""
        return ComponentType.role_select

    @property
    def default_values(self) -> List[SelectDefaultValue]:
        """List[:class:`bisim.SelectDefaultValue`]: A list of default values for the select menu."""
        return self._underlying.default_values

    @default_values.setter
    def default_values(self, value: Sequence[Any]) -> None:
        self._underlying.default_values = _handle_select_defaults(value, self.type)

    @property
    def values(self) -> List[Role]:
        """List[:class:`bisim.Role`]: A list of roles that have been selected by the user."""
        return list(self._values)


class MentionableSelect(BaseSelect[V]):
    """Represents a UI select menu with a list of predefined options with the current members and roles in the guild.

    If this is sent in a private message, it will only allow the user to select
    the client or themselves.

    Parameters
    ------------
    custom_id: :class:`str`
        The ID of the select menu that gets received during an interaction.
        If not given then one is generated for you.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
    min_values: :class:`int`
        The minimum number of items that must be chosen for this select menu.
    max_values: :class:`int`
        The maximum number of items that must be chosen for this select menu.
    disabled: :class:`bool`
        Whether the select is disabled or not.
    default_values: Sequence[:class:`~bisim.abc.Snowflake`]
        A list of objects representing the users/roles that should be selected by default.
        if :class:`.Object` is passed, then the type must be specified in the constructor.
        Number of items must be in range of ``min_values`` and ``max_values``.
    row: Optional[:class:`int`]
        The relative row this select menu belongs to.
    id: Optional[:class:`int`]
        Accepted for compatibility.
    """

    __component_attributes__ = BaseSelect.__component_attributes__ + ('default_values',)
    _resolve_kinds = ('member', 'user', 'role')

    def __init__(
        self,
        *,
        custom_id: str = utils.MISSING,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        required: bool = True,
        row: Optional[int] = None,
        default_values: Sequence[Any] = utils.MISSING,
        id: Optional[int] = None,
    ) -> None:
        super().__init__(
            self.type,
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            required=required,
            row=row,
            default_values=default_values,
            id=id,
        )

    @property
    def type(self) -> ComponentType:
        """:class:`.ComponentType`: The type of this component."""
        return ComponentType.mentionable_select

    @property
    def default_values(self) -> List[SelectDefaultValue]:
        """List[:class:`bisim.SelectDefaultValue`]: A list of default values for the select menu."""
        return self._underlying.default_values

    @default_values.setter
    def default_values(self, value: Sequence[Any]) -> None:
        self._underlying.default_values = _handle_select_defaults(value, self.type)

    @property
    def values(self) -> List[Union[Member, User, Role]]:
        """List[Union[:class:`bisim.Role`, :class:`bisim.Member`, :class:`bisim.User`]]: A list of roles, members,
        and users that have been selected by the user.
        """
        return list(self._values)


class ChannelSelect(BaseSelect[V]):
    """Represents a UI select menu with a list of predefined options with the current channels in the guild.

    Please note that if you use this in a private message with a user, no channels will be displayed to the user.

    Parameters
    ------------
    custom_id: :class:`str`
        The ID of the select menu that gets received during an interaction.
        If not given then one is generated for you.
    channel_types: List[:class:`~bisim.ChannelType`]
        The types of channels to show in the select menu. Defaults to all channels.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
    min_values: :class:`int`
        The minimum number of items that must be chosen for this select menu.
    max_values: :class:`int`
        The maximum number of items that must be chosen for this select menu.
    disabled: :class:`bool`
        Whether the select is disabled or not.
    default_values: Sequence[:class:`~bisim.abc.Snowflake`]
        A list of objects representing the channels that should be selected by default.
        Number of items must be in range of ``min_values`` and ``max_values``.
    row: Optional[:class:`int`]
        The relative row this select menu belongs to.
    id: Optional[:class:`int`]
        Accepted for compatibility.
    """

    __component_attributes__ = BaseSelect.__component_attributes__ + ('channel_types', 'default_values')
    _resolve_kinds = ('channel',)

    def __init__(
        self,
        *,
        custom_id: str = utils.MISSING,
        channel_types: List[ChannelType] = utils.MISSING,
        placeholder: Optional[str] = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        required: bool = True,
        row: Optional[int] = None,
        default_values: Sequence[Any] = utils.MISSING,
        id: Optional[int] = None,
    ) -> None:
        super().__init__(
            self.type,
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            required=required,
            row=row,
            channel_types=channel_types,
            default_values=default_values,
            id=id,
        )

    @property
    def type(self) -> ComponentType:
        """:class:`.ComponentType`: The type of this component."""
        return ComponentType.channel_select

    @property
    def default_values(self) -> List[SelectDefaultValue]:
        """List[:class:`bisim.SelectDefaultValue`]: A list of default values for the select menu."""
        return self._underlying.default_values

    @default_values.setter
    def default_values(self, value: Sequence[Any]) -> None:
        self._underlying.default_values = _handle_select_defaults(value, self.type)

    @property
    def channel_types(self) -> List[ChannelType]:
        """List[:class:`~bisim.ChannelType`]: A list of channel types that can be selected."""
        return self._underlying.channel_types

    @channel_types.setter
    def channel_types(self, value: List[ChannelType]) -> None:
        if not isinstance(value, list):
            raise TypeError('channel_types must be a list of ChannelType')
        if not all(isinstance(obj, ChannelType) for obj in value):
            raise TypeError('all list items must be a ChannelType')

        self._underlying.channel_types = value

    @property
    def values(self) -> List[Any]:
        """List[:class:`~bisim.abc.GuildChannel`]: A list of channels selected by the user."""
        return list(self._values)


def select(
    *,
    cls: Type[BaseSelectT] = Select,
    options: List[SelectOption] = utils.MISSING,
    channel_types: List[ChannelType] = utils.MISSING,
    placeholder: Optional[str] = None,
    custom_id: str = utils.MISSING,
    min_values: int = 1,
    max_values: int = 1,
    disabled: bool = False,
    default_values: Sequence[Any] = utils.MISSING,
    row: Optional[int] = None,
    id: Optional[int] = None,
) -> Callable[[ItemCallbackType[V, BaseSelectT]], BaseSelectT]:
    """A decorator that attaches a select menu to a component.

    The function being decorated should have three parameters, ``self`` representing
    the :class:`bisim.ui.View`, the :class:`bisim.Interaction` you receive and
    the chosen select class.

    To obtain the selected values inside the callback, you can use the ``values`` attribute of the chosen class in the callback. The list of values
    will depend on the type of select menu used. View the table below for more information.

    +----------------------------------------+-----------------------------------------------------------------+
    | Select Type                            | Resolved Values                                                 |
    +========================================+=================================================================+
    | :class:`bisim.ui.Select`               | List[:class:`str`]                                              |
    +----------------------------------------+-----------------------------------------------------------------+
    | :class:`bisim.ui.UserSelect`           | List[Union[:class:`bisim.Member`, :class:`bisim.User`]]         |
    +----------------------------------------+-----------------------------------------------------------------+
    | :class:`bisim.ui.RoleSelect`           | List[:class:`bisim.Role`]                                       |
    +----------------------------------------+-----------------------------------------------------------------+
    | :class:`bisim.ui.MentionableSelect`    | List[Union[:class:`bisim.Role`, :class:`bisim.Member`, :class:`bisim.User`]] |
    +----------------------------------------+-----------------------------------------------------------------+
    | :class:`bisim.ui.ChannelSelect`        | List[:class:`bisim.abc.GuildChannel`]                           |
    +----------------------------------------+-----------------------------------------------------------------+

    Example
    ---------
    .. code-block:: python3

        class View(bisim.ui.View):

            @bisim.ui.select(cls=ChannelSelect, channel_types=[bisim.ChannelType.text])
            async def select_channels(self, interaction: bisim.Interaction, select: ChannelSelect):
                return await interaction.response.send_message(f'You selected {select.values[0].mention}')

    Parameters
    ------------
    cls: Union[Type[:class:`bisim.ui.Select`], Type[:class:`bisim.ui.UserSelect`], Type[:class:`bisim.ui.RoleSelect`], \\
        Type[:class:`bisim.ui.MentionableSelect`], Type[:class:`bisim.ui.ChannelSelect`]]
        The class to use for the select menu. Defaults to :class:`bisim.ui.Select`.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
    custom_id: :class:`str`
        The ID of the select menu that gets received during an interaction.
        It is recommended not to set this parameter to prevent conflicts.
    row: Optional[:class:`int`]
        The relative row this select menu belongs to.
    min_values: :class:`int`
        The minimum number of items that must be chosen for this select menu.
    max_values: :class:`int`
        The maximum number of items that must be chosen for this select menu.
    options: List[:class:`bisim.SelectOption`]
        A list of options that can be selected in this menu. This can only be used with
        :class:`Select` instances.
    channel_types: List[:class:`~bisim.ChannelType`]
        The types of channels to show in the select menu. Defaults to all channels. This can only be used
        with :class:`ChannelSelect` instances.
    disabled: :class:`bool`
        Whether the select is disabled or not. Defaults to ``False``.
    default_values: Sequence[:class:`~bisim.abc.Snowflake`]
        A list of objects representing the default values for the select menu. This cannot be used with regular :class:`Select` instances.
        If ``cls`` is :class:`MentionableSelect` and :class:`.Object` is passed, then the type must be specified in the constructor.
        Number of items must be in range of ``min_values`` and ``max_values``.
    id: Optional[:class:`int`]
        Accepted for compatibility.
    """

    def decorator(func: ItemCallbackType[V, BaseSelectT]) -> ItemCallbackType[V, BaseSelectT]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError('select function must be a coroutine function')
        callback_cls = getattr(cls, '__origin__', cls)
        if not issubclass(callback_cls, BaseSelect):
            supported_classes = ', '.join(['ChannelSelect', 'MentionableSelect', 'RoleSelect', 'Select', 'UserSelect'])
            raise TypeError(f'cls must be one of {supported_classes} or a subclass of one of them, not {cls.__name__}.')

        func.__bisim_ui_model_type__ = callback_cls  # type: ignore
        func.__bisim_ui_model_kwargs__ = {  # type: ignore
            'placeholder': placeholder,
            'custom_id': custom_id,
            'row': row,
            'min_values': min_values,
            'max_values': max_values,
            'disabled': disabled,
            'id': id,
        }
        if issubclass(callback_cls, Select):
            func.__bisim_ui_model_kwargs__['options'] = options  # type: ignore
        if issubclass(callback_cls, ChannelSelect):
            func.__bisim_ui_model_kwargs__['channel_types'] = channel_types  # type: ignore
        if not issubclass(callback_cls, Select) and default_values is not utils.MISSING:
            func.__bisim_ui_model_kwargs__['default_values'] = default_values  # type: ignore

        return func

    return decorator  # type: ignore

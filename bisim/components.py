"""Message components as received: rows, buttons, select menus and text inputs.

Bisim uses Discord's numbers for component types and styles, and camelCase
keys (``customId``, ``minValues``...).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Sequence, Tuple, Union

from . import utils
from .enums import ButtonStyle, ChannelType, ComponentType, SelectDefaultValueType, TextStyle, try_enum
from .partial_emoji import PartialEmoji, _EmojiTag

if TYPE_CHECKING:
    from typing_extensions import Self

    from .emoji import Emoji

__all__ = (
    'Component',
    'ActionRow',
    'Button',
    'SelectMenu',
    'SelectOption',
    'SelectDefaultValue',
    'TextInput',
)


def _emoji_payload(emoji: Any) -> Optional[Dict[str, Any]]:
    if emoji is None:
        return None
    if isinstance(emoji, str):
        emoji = PartialEmoji.from_str(emoji)
    if isinstance(emoji, _EmojiTag):
        emoji = emoji._to_partial()
    if isinstance(emoji, PartialEmoji):
        data: Dict[str, Any] = {'name': emoji.name}
        if emoji.id is not None:
            data['id'] = str(emoji.id)
        if emoji.animated:
            data['animated'] = True
        return data
    raise TypeError(f'expected emoji to be str, Emoji, or PartialEmoji not {emoji.__class__.__name__}')


class Component:
    """Represents a Bisim Bot UI Kit Component.

    The components supported by Bisim are:

    - :class:`ActionRow`
    - :class:`Button`
    - :class:`SelectMenu`
    - :class:`TextInput`

    This class is abstract and cannot be instantiated.
    """

    __slots__ = ()

    __repr_info__: ClassVar[Tuple[str, ...]]

    def __repr__(self) -> str:
        attrs = ' '.join(f'{key}={getattr(self, key)!r}' for key in self.__repr_info__)
        return f'<{self.__class__.__name__} {attrs}>'

    @property
    def type(self) -> ComponentType:
        """:class:`ComponentType`: The type of component."""
        raise NotImplementedError

    @classmethod
    def _raw_construct(cls, **kwargs: Any) -> Self:
        self = cls.__new__(cls)
        for slot in cls.__slots__:
            try:
                value = kwargs[slot]
            except KeyError:
                pass
            else:
                setattr(self, slot, value)
        return self

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError


class ActionRow(Component):
    """Represents a Bisim Bot UI Kit Action Row.

    This is a component that holds up to 5 children components in a row.

    This inherits from :class:`Component`.

    Attributes
    ------------
    children: List[Union[:class:`Button`, :class:`SelectMenu`, :class:`TextInput`]]
        The children components that this holds, if any.
    id: Optional[:class:`int`]
        Always ``None`` on Bisim.
    """

    __slots__: Tuple[str, ...] = ('children', 'id')

    __repr_info__: ClassVar[Tuple[str, ...]] = __slots__

    def __init__(self, data: Dict[str, Any], /) -> None:
        self.id: Optional[int] = None
        self.children: List[Component] = []
        for component_data in data.get('components', []) or []:
            component = _component_factory(component_data)
            if component is not None:
                self.children.append(component)

    @property
    def type(self) -> ComponentType:
        """:class:`ComponentType`: The type of component."""
        return ComponentType.action_row

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 1, 'components': [child.to_dict() for child in self.children]}


class Button(Component):
    """Represents a button from the Bisim Bot UI Kit.

    This inherits from :class:`Component`.

    .. note::

        The user constructible and usable type to create a button is :class:`bisim.ui.Button`
        not this one.

    Attributes
    -----------
    style: :class:`.ButtonStyle`
        The style of the button.
    custom_id: Optional[:class:`str`]
        The ID of the button that gets received during an interaction.
        If this button is for a URL, it does not have a custom ID.
    url: Optional[:class:`str`]
        The URL this button sends you to.
    disabled: :class:`bool`
        Whether the button is disabled or not.
    label: Optional[:class:`str`]
        The label of the button, if any.
    emoji: Optional[:class:`PartialEmoji`]
        The emoji of the button, if available.
    sku_id: Optional[:class:`int`]
        Always ``None`` on Bisim.
    id: Optional[:class:`int`]
        Always ``None`` on Bisim.
    """

    __slots__: Tuple[str, ...] = ('style', 'custom_id', 'url', 'disabled', 'label', 'emoji', 'sku_id', 'id')

    __repr_info__: ClassVar[Tuple[str, ...]] = __slots__

    def __init__(self, data: Dict[str, Any], /) -> None:
        self.style: ButtonStyle = try_enum(ButtonStyle, utils._int(data.get('style'), 1))
        self.custom_id: Optional[str] = data.get('customId') or data.get('custom_id') or None
        self.url: Optional[str] = data.get('url') or None
        self.disabled: bool = bool(data.get('disabled', False))
        self.label: Optional[str] = data.get('label') or None
        self.emoji: Optional[PartialEmoji]
        emoji = data.get('emoji')
        self.emoji = PartialEmoji.from_dict(emoji) if isinstance(emoji, dict) and emoji else None
        self.sku_id: Optional[int] = None
        self.id: Optional[int] = None

    @property
    def type(self) -> ComponentType:
        """:class:`ComponentType`: The type of component."""
        return ComponentType.button

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {'type': 2, 'style': self.style.value, 'disabled': self.disabled}
        if self.label:
            payload['label'] = self.label
        if self.custom_id:
            payload['customId'] = self.custom_id
        if self.url:
            payload['url'] = self.url
        if self.emoji:
            payload['emoji'] = _emoji_payload(self.emoji)
        return payload


class SelectOption:
    """Represents a select menu's option.

    These can be created by users.

    Parameters
    -----------
    label: :class:`str`
        The label of the option. This is displayed to users.
        Can only be up to 100 characters.
    value: :class:`str`
        The value of the option. This is not displayed to users.
        If not provided when constructed then it defaults to the label.
        Can only be up to 100 characters.
    description: Optional[:class:`str`]
        An additional description of the option, if any.
        Can only be up to 100 characters.
    emoji: Optional[Union[:class:`str`, :class:`Emoji`, :class:`PartialEmoji`]]
        The emoji of the option, if available.
    default: :class:`bool`
        Whether this option is selected by default.
    """

    __slots__: Tuple[str, ...] = ('label', 'value', 'description', '_emoji', 'default')

    def __init__(
        self,
        *,
        label: str,
        value: str = utils.MISSING,
        description: Optional[str] = None,
        emoji: Optional[Union[str, Emoji, PartialEmoji]] = None,
        default: bool = False,
    ) -> None:
        self.label: str = label
        self.value: str = label if value is utils.MISSING else value
        self.description: Optional[str] = description
        self.emoji = emoji
        self.default: bool = default

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} label={self.label!r} value={self.value!r} description={self.description!r} '
            f'emoji={self.emoji!r} default={self.default!r}>'
        )

    def __str__(self) -> str:
        if self.emoji:
            base = f'{self.emoji} {self.label}'
        else:
            base = self.label
        if self.description:
            return f'{base}\n{self.description}'
        return base

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SelectOption) and self.to_dict() == other.to_dict()

    @property
    def emoji(self) -> Optional[PartialEmoji]:
        """Optional[:class:`.PartialEmoji`]: The emoji of the option, if available."""
        return self._emoji

    @emoji.setter
    def emoji(self, value: Optional[Union[str, Emoji, PartialEmoji]]) -> None:
        if value is not None:
            if isinstance(value, str):
                self._emoji = PartialEmoji.from_str(value)
            elif isinstance(value, _EmojiTag):
                self._emoji = value._to_partial()
            else:
                raise TypeError(f'expected str, Emoji, or PartialEmoji, received {value.__class__.__name__} instead')
        else:
            self._emoji = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SelectOption:
        emoji = data.get('emoji')
        return cls(
            label=data.get('label') or '',
            value=data.get('value') or '',
            description=data.get('description') or None,
            emoji=PartialEmoji.from_dict(emoji) if isinstance(emoji, dict) and emoji else None,
            default=bool(data.get('default', False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {'label': self.label, 'value': self.value, 'default': self.default}
        if self.emoji:
            payload['emoji'] = _emoji_payload(self.emoji)
        if self.description:
            payload['description'] = self.description
        return payload

    def copy(self) -> SelectOption:
        return self.__class__.from_dict(self.to_dict())


class SelectDefaultValue:
    """Represents a select menu's default value: what a user, role, mentionable
    or channel select shows as picked when it is drawn.

    These can be created by users.

    Parameters
    -----------
    id: :class:`int`
        The id of a role, user, or channel.
    type: :class:`SelectDefaultValueType`
        The type of value that ``id`` represents.
    """

    def __init__(self, *, id: int, type: SelectDefaultValueType) -> None:
        self.id: int = id
        self._type: SelectDefaultValueType = type

    @property
    def type(self) -> SelectDefaultValueType:
        """:class:`SelectDefaultValueType`: The type of value that ``id`` represents."""
        return self._type

    @type.setter
    def type(self, value: SelectDefaultValueType) -> None:
        if not isinstance(value, SelectDefaultValueType):
            raise TypeError(f'expected SelectDefaultValueType, received {value.__class__.__name__} instead')
        self._type = value

    def __repr__(self) -> str:
        return f'<SelectDefaultValue id={self.id!r} type={self.type!r}>'

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SelectDefaultValue) and int(self.id) == int(other.id) and self._type is other._type

    def __hash__(self) -> int:
        return hash((int(self.id), self._type))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SelectDefaultValue:
        return cls(id=int(data['id']), type=try_enum(SelectDefaultValueType, data.get('type')))

    def to_dict(self) -> Dict[str, Any]:
        return {'id': str(self.id), 'type': self._type.value}

    @classmethod
    def from_channel(cls, channel: Any, /) -> Self:
        """Creates a :class:`SelectDefaultValue` with the type set to :attr:`~SelectDefaultValueType.channel`.

        Parameters
        -----------
        channel: :class:`~bisim.abc.Snowflake`
            The channel to create the default value for.

        Returns
        --------
        :class:`SelectDefaultValue`
            The default value created with the channel.
        """
        return cls(id=channel.id, type=SelectDefaultValueType.channel)

    @classmethod
    def from_role(cls, role: Any, /) -> Self:
        """Creates a :class:`SelectDefaultValue` with the type set to :attr:`~SelectDefaultValueType.role`.

        Parameters
        -----------
        role: :class:`~bisim.abc.Snowflake`
            The role to create the default value for.

        Returns
        --------
        :class:`SelectDefaultValue`
            The default value created with the role.
        """
        return cls(id=role.id, type=SelectDefaultValueType.role)

    @classmethod
    def from_user(cls, user: Any, /) -> Self:
        """Creates a :class:`SelectDefaultValue` with the type set to :attr:`~SelectDefaultValueType.user`.

        Parameters
        -----------
        user: :class:`~bisim.abc.Snowflake`
            The user to create the default value for.

        Returns
        --------
        :class:`SelectDefaultValue`
            The default value created with the user.
        """
        return cls(id=user.id, type=SelectDefaultValueType.user)


class SelectMenu(Component):
    """Represents a select menu from the Bisim Bot UI Kit.

    A select menu is functionally the same as a dropdown, however
    on mobile it renders a bit differently.

    .. note::

        The user constructible and usable type to create a select menu is
        :class:`bisim.ui.Select` not this one.

    Attributes
    ------------
    type: :class:`ComponentType`
        The type of component.
    custom_id: Optional[:class:`str`]
        The ID of the select menu that gets received during an interaction.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
    min_values: :class:`int`
        The minimum number of items that must be chosen for this select menu.
    max_values: :class:`int`
        The maximum number of items that must be chosen for this select menu.
    options: List[:class:`SelectOption`]
        A list of options that can be selected in this menu.
    disabled: :class:`bool`
        Whether the select is disabled or not.
    channel_types: List[:class:`.ChannelType`]
        A list of channel types that are allowed to be chosen in this select menu.
    default_values: List[:class:`.SelectDefaultValue`]
        A list of values that are selected by default for select menus of type user, role,
        mentionable and channel.
    id: Optional[:class:`int`]
        Always ``None`` on Bisim.
    """

    __slots__: Tuple[str, ...] = (
        'type',
        'custom_id',
        'placeholder',
        'min_values',
        'max_values',
        'options',
        'disabled',
        'channel_types',
        'default_values',
        'required',
        'id',
    )

    __repr_info__: ClassVar[Tuple[str, ...]] = __slots__

    def __init__(self, data: Dict[str, Any], /) -> None:
        self.type: ComponentType = try_enum(ComponentType, utils._int(data.get('type'), 3))
        self.custom_id: str = data.get('customId') or data.get('custom_id') or ''
        self.placeholder: Optional[str] = data.get('placeholder') or None
        self.min_values: int = utils._int(data.get('minValues'), 1) if 'minValues' in data else 1
        self.max_values: int = utils._int(data.get('maxValues'), 1) if 'maxValues' in data else 1
        self.options: List[SelectOption] = [SelectOption.from_dict(option) for option in data.get('options', []) or []]
        self.disabled: bool = bool(data.get('disabled', False))
        self.channel_types: List[ChannelType] = [ChannelType.from_bisim(t) for t in data.get('channelTypes', []) or []]
        self.default_values: List[SelectDefaultValue] = [
            SelectDefaultValue.from_dict(d) for d in data.get('defaultValues', []) or [] if isinstance(d, dict) and d.get('id')
        ]
        self.required: bool = bool(data.get('required', True))
        self.id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'type': self.type.value,
            'customId': self.custom_id,
            'minValues': self.min_values,
            'maxValues': self.max_values,
            'disabled': self.disabled,
        }
        if self.placeholder:
            payload['placeholder'] = self.placeholder
        if self.options:
            payload['options'] = [op.to_dict() for op in self.options]
        if self.channel_types:
            payload['channelTypes'] = [t.bisim_name for t in self.channel_types if t.bisim_name]
        if self.default_values:
            payload['defaultValues'] = [v.to_dict() for v in self.default_values]
        return payload


class TextInput(Component):
    """Represents a text input from the Bisim Bot UI Kit.

    .. note::
        The user constructible and usable type to create a text input is
        :class:`bisim.ui.TextInput` not this one.

    Attributes
    ------------
    custom_id: Optional[:class:`str`]
        The ID of the text input that gets received during an interaction.
    label: :class:`str`
        The label to display above the text input.
    style: :class:`TextStyle`
        The style of the text input.
    placeholder: Optional[:class:`str`]
        The placeholder text to display when the text input is empty.
    value: Optional[:class:`str`]
        The default value of the text input.
    required: :class:`bool`
        Whether the text input is required.
    min_length: Optional[:class:`int`]
        The minimum length of the text input.
    max_length: Optional[:class:`int`]
        The maximum length of the text input.
    id: Optional[:class:`int`]
        Always ``None`` on Bisim.
    """

    __slots__: Tuple[str, ...] = (
        'style',
        'label',
        'custom_id',
        'placeholder',
        'value',
        'required',
        'min_length',
        'max_length',
        'id',
    )

    __repr_info__: ClassVar[Tuple[str, ...]] = __slots__

    def __init__(self, data: Dict[str, Any], /) -> None:
        self.style: TextStyle = try_enum(TextStyle, utils._int(data.get('style'), 1))
        self.label: Optional[str] = data.get('label')
        self.custom_id: str = data.get('customId') or data.get('custom_id') or ''
        self.placeholder: Optional[str] = data.get('placeholder') or None
        self.value: Optional[str] = data.get('value') or None
        self.required: bool = bool(data.get('required', True))
        self.min_length: Optional[int] = data.get('minLength')
        self.max_length: Optional[int] = data.get('maxLength')
        self.id: Optional[int] = None

    @property
    def type(self) -> ComponentType:
        """:class:`ComponentType`: The type of component."""
        return ComponentType.text_input

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'type': 4,
            'style': self.style.value,
            'label': self.label,
            'customId': self.custom_id,
            'required': self.required,
        }
        if self.placeholder:
            payload['placeholder'] = self.placeholder
        if self.value:
            payload['value'] = self.value
        if self.min_length is not None:
            payload['minLength'] = self.min_length
        if self.max_length is not None:
            payload['maxLength'] = self.max_length
        return payload

    @property
    def default(self) -> Optional[str]:
        """Optional[:class:`str`]: The default value of the text input.

        This is an alias to :attr:`value`.
        """
        return self.value


def _component_factory(data: Dict[str, Any]) -> Optional[Component]:
    component_type = utils._int(data.get('type'), 0)
    if component_type == 1:
        return ActionRow(data)
    if component_type == 2:
        return Button(data)
    if component_type == 4:
        return TextInput(data)
    if component_type in (3, 5, 6, 7, 8):
        return SelectMenu(data)
    return None

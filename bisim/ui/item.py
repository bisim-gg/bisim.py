from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, Generic, Optional, Tuple, Type, TypeVar

from ..interactions import Interaction

if TYPE_CHECKING:
    from ..components import Component
    from ..enums import ComponentType
    from .view import View

__all__ = ('Item',)

I = TypeVar('I', bound='Item[Any]')
V = TypeVar('V', bound='View', covariant=True)
ItemCallbackType = Callable[[V, Interaction[Any], I], Coroutine[Any, Any, Any]]


class Item(Generic[V]):
    """Represents the base UI item that all UI components inherit from.

    The current UI items supported are:

    - :class:`bisim.ui.Button`
    - :class:`bisim.ui.Select`
    - :class:`bisim.ui.TextInput`
    - :class:`bisim.ui.UserSelect`
    - :class:`bisim.ui.RoleSelect`
    - :class:`bisim.ui.MentionableSelect`
    - :class:`bisim.ui.ChannelSelect`
    """

    __item_repr_attributes__: Tuple[str, ...] = ('row',)

    def __init__(self) -> None:
        self._view: Optional[V] = None
        self._row: Optional[int] = None
        self._rendered_row: Optional[int] = None
        self._provided_custom_id: bool = False
        self._id: Optional[int] = None
        self._max_row: int = 5

    def to_component_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    def _refresh_component(self, component: Component) -> None:
        return None

    def _refresh_state(self, interaction: Interaction, data: Dict[str, Any]) -> None:
        return None

    @classmethod
    def from_component(cls: Type[I], component: Component) -> I:
        return cls()

    @property
    def type(self) -> ComponentType:
        raise NotImplementedError

    def is_dispatchable(self) -> bool:
        return False

    def is_persistent(self) -> bool:
        return self._provided_custom_id

    def __repr__(self) -> str:
        attrs = ' '.join(f'{key}={getattr(self, key)!r}' for key in self.__item_repr_attributes__)
        return f'<{self.__class__.__name__} {attrs}>'

    @property
    def row(self) -> Optional[int]:
        return self._row

    @row.setter
    def row(self, value: Optional[int]) -> None:
        if value is None:
            self._row = None
        elif self._max_row > value >= 0:
            self._row = value
        else:
            raise ValueError(f'row cannot be negative or greater than or equal to {self._max_row}')

    @property
    def width(self) -> int:
        return 1

    @property
    def view(self) -> Optional[V]:
        """Optional[:class:`View`]: The underlying view for this item."""
        return self._view

    @property
    def id(self) -> Optional[int]:
        """Optional[:class:`int`]: Always ``None`` on Bisim (component ids are a newer Discord feature)."""
        return self._id

    @id.setter
    def id(self, value: Optional[int]) -> None:
        self._id = value

    async def callback(self, interaction: Interaction[Any]) -> Any:
        """|coro|

        The callback associated with this UI item.

        This can be overridden by subclasses.

        Parameters
        -----------
        interaction: :class:`.Interaction`
            The interaction that triggered this UI item.
        """
        pass

    async def interaction_check(self, interaction: Interaction[Any], /) -> bool:
        """|coro|

        A callback that is called when an interaction happens within this item
        that checks whether the callback should be processed.

        This is useful to override if, for example, you want to ensure that the
        interaction author is a given user.

        The default implementation of this returns ``True``.

        .. note::

            If an exception occurs within the body then the check
            is considered a failure and :meth:`bisim.ui.View.on_error` is called.

        Parameters
        -----------
        interaction: :class:`~bisim.Interaction`
            The interaction that occurred.

        Returns
        ---------
        :class:`bool`
            Whether the callback should be called.
        """
        return True

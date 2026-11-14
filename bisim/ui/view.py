from __future__ import annotations

import asyncio
import logging
import os
import time
from functools import partial
from itertools import groupby
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Coroutine,
    Dict,
    Generator,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
)

from ..components import ActionRow as ActionRowComponent
from ..components import Button as ButtonComponent
from ..components import Component
from ..components import SelectMenu as SelectComponent
from ..components import TextInput as TextInputComponent
from ..components import _component_factory
from ..enums import ComponentType
from .item import Item, ItemCallbackType

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..interactions import Interaction
    from ..message import Message
    from ..state import ConnectionState
    from .modal import Modal

__all__ = ('View',)

_log = logging.getLogger(__name__)


def _walk_all_components(components: List[Component]) -> Iterator[Component]:
    for item in components:
        if isinstance(item, ActionRowComponent):
            yield from item.children
        else:
            yield item


def _component_to_item(component: Component) -> Item[Any]:
    if isinstance(component, ButtonComponent):
        from .button import Button

        return Button.from_component(component)
    if isinstance(component, SelectComponent):
        from .select import ChannelSelect, MentionableSelect, RoleSelect, Select, UserSelect

        cls = {
            ComponentType.string_select: Select,
            ComponentType.user_select: UserSelect,
            ComponentType.role_select: RoleSelect,
            ComponentType.mentionable_select: MentionableSelect,
            ComponentType.channel_select: ChannelSelect,
        }.get(component.type, Select)
        return cls.from_component(component)  # type: ignore
    if isinstance(component, TextInputComponent):
        from .text_input import TextInput

        return TextInput.from_component(component)
    return Item.from_component(component)


class _ViewWeights:
    """Places items into the five rows of a message, five units wide each."""

    __slots__ = ('weights',)

    def __init__(self, children: List[Item[Any]]):
        self.weights: List[int] = [0, 0, 0, 0, 0]

        key = lambda i: 5 if i.row is None else i.row
        children = sorted(children, key=key)
        for _, group in groupby(children, key=key):
            for item in group:
                self.add_item(item)

    def find_open_space(self, item: Item[Any]) -> int:
        for index, weight in enumerate(self.weights):
            if weight + item.width <= 5:
                return index

        raise ValueError('could not find open space for item')

    def add_item(self, item: Item[Any]) -> None:
        if item.row is not None:
            total = self.weights[item.row] + item.width
            if total > 5:
                raise ValueError(f'item would not fit at row {item.row} ({total} > 5 width)')
            self.weights[item.row] = total
            item._rendered_row = item.row
        else:
            index = self.find_open_space(item)
            self.weights[index] += item.width
            item._rendered_row = index

    def remove_item(self, item: Item[Any]) -> None:
        if item._rendered_row is not None:
            self.weights[item._rendered_row] -= item.width
            item._rendered_row = None

    def clear(self) -> None:
        self.weights = [0, 0, 0, 0, 0]


class _ViewCallback:
    __slots__ = ('view', 'callback', 'item')

    def __init__(self, callback: ItemCallbackType[Any, Any], view: View, item: Item[View]) -> None:
        self.callback: ItemCallbackType[Any, Any] = callback
        self.view: View = view
        self.item: Item[View] = item

    def __call__(self, interaction: Interaction[Any]) -> Coroutine[Any, Any, Any]:
        return self.callback(self.view, interaction, self.item)


class View:
    """Represents a UI view.

    This object must be inherited to create a UI within Bisim.

    Parameters
    -----------
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    """

    __bisim_ui_view__: ClassVar[bool] = True
    __bisim_ui_modal__: ClassVar[bool] = False
    __view_children_items__: ClassVar[List[ItemCallbackType[Any, Any]]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        children: Dict[str, ItemCallbackType[Any, Any]] = {}
        for base in reversed(cls.__mro__):
            for name, member in base.__dict__.items():
                if hasattr(member, '__bisim_ui_model_type__'):
                    children[name] = member

        if len(children) > 25:
            raise TypeError('View cannot have more than 25 children')

        cls.__view_children_items__ = list(children.values())

    def _init_children(self) -> List[Item[Self]]:
        children = []
        for func in self.__view_children_items__:
            item: Item = func.__bisim_ui_model_type__(**func.__bisim_ui_model_kwargs__)  # type: ignore
            item.callback = _ViewCallback(func, self, item)  # type: ignore
            item._view = self
            setattr(self, func.__name__, item)
            children.append(item)
        return children

    def __init__(self, *, timeout: Optional[float] = 180.0):
        self.__timeout = timeout
        self._children: List[Item[Self]] = self._init_children()
        self.__weights = _ViewWeights(self._children)
        self.id: str = os.urandom(16).hex()
        self._cache_key: Optional[int] = None
        self.__cancel_callback: Optional[Callable[[View], None]] = None
        self.__timeout_expiry: Optional[float] = None
        self.__timeout_task: Optional[asyncio.Task[None]] = None
        self.__stopped: Optional[asyncio.Future[bool]] = None
        self.__finished: bool = False
        self.__timed_out: bool = False

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} timeout={self.timeout} children={len(self._children)}>'

    def _stopped_future(self) -> asyncio.Future[bool]:
        if self.__stopped is None:
            self.__stopped = asyncio.get_running_loop().create_future()
            if self.__finished:
                self.__stopped.set_result(self.__timed_out)
        return self.__stopped

    async def __timeout_task_impl(self) -> None:
        while True:
            if self.timeout is None:
                return

            if self.__timeout_expiry is None:
                return self._dispatch_timeout()

            now = time.monotonic()
            if now >= self.__timeout_expiry:
                return self._dispatch_timeout()

            await asyncio.sleep(self.__timeout_expiry - now)

    def is_dispatchable(self) -> bool:
        # A view with no dispatchable items (only links) does not need to be stored.
        return any(item.is_dispatchable() for item in self._children)

    def has_components_v2(self) -> bool:
        return False

    def to_components(self) -> List[Dict[str, Any]]:
        def key(item: Item[Any]) -> int:
            return item._rendered_row or 0

        children = sorted(self._children, key=key)
        components: List[Dict[str, Any]] = []
        for _, group in groupby(children, key=key):
            rendered = [item.to_component_dict() for item in group]
            if not rendered:
                continue
            components.append({'type': 1, 'components': rendered})
        return components

    def _refresh_timeout(self) -> None:
        if self.__timeout:
            self.__timeout_expiry = time.monotonic() + self.__timeout

    @property
    def timeout(self) -> Optional[float]:
        """Optional[:class:`float`]: The timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
        """
        return self.__timeout

    @timeout.setter
    def timeout(self, value: Optional[float]) -> None:
        if self.__timeout_task is not None:
            if value is not None:
                self.__timeout_expiry = time.monotonic() + value
            else:
                self.__timeout_expiry = None

        self.__timeout = value

    @property
    def children(self) -> List[Item[Self]]:
        """List[:class:`Item`]: The list of children attached to this view."""
        return self._children.copy()

    def walk_children(self) -> Generator[Item[Any], None, None]:
        """An iterator that recursively walks through all the children of this view."""
        yield from self._children

    @classmethod
    def from_message(cls, message: Message, /, *, timeout: Optional[float] = 180.0) -> View:
        """Converts a message's components into a :class:`View`.

        The :attr:`.Message.components` of a message are read-only
        and separate types from those in the ``bisim.ui`` namespace.
        In order to modify and edit message components they must be
        converted into a :class:`View` first.

        Parameters
        -----------
        message: :class:`bisim.Message`
            The message with components to convert into a view.
        timeout: Optional[:class:`float`]
            The timeout of the converted view.

        Returns
        --------
        :class:`View`
            The converted view. This always returns a :class:`View` and not
            one of its subclasses.
        """
        view = View(timeout=timeout)
        row = 0
        for component in message.components:
            if isinstance(component, ActionRowComponent):
                for child in component.children:
                    item = _component_to_item(child)
                    item.row = row
                    view.add_item(item)
                row += 1
                continue

            item = _component_to_item(component)
            item.row = row
            view.add_item(item)
            row += 1

        return view

    def add_item(self, item: Item[Any]) -> Self:
        """Adds an item to the view.

        This function returns the class instance to allow for fluent-style
        chaining.

        Parameters
        -----------
        item: :class:`Item`
            The item to add to the view.

        Raises
        --------
        TypeError
            An :class:`Item` was not passed.
        ValueError
            Maximum number of children has been exceeded (25)
            or the row the item is trying to be added to is full.
        """
        if len(self._children) >= 25:
            raise ValueError('maximum number of children exceeded')

        if not isinstance(item, Item):
            raise TypeError(f'expected Item not {item.__class__.__name__}')

        self.__weights.add_item(item)

        item._view = self
        self._children.append(item)
        return self

    def remove_item(self, item: Item[Any]) -> Self:
        """Removes an item from the view.

        This function returns the class instance to allow for fluent-style
        chaining.

        Parameters
        -----------
        item: :class:`Item`
            The item to remove from the view.
        """
        try:
            self._children.remove(item)
        except ValueError:
            pass
        else:
            self.__weights.remove_item(item)
        return self

    def clear_items(self) -> Self:
        """Removes all items from the view.

        This function returns the class instance to allow for fluent-style
        chaining.
        """
        self._children.clear()
        self.__weights.clear()
        return self

    def find_item(self, id: int, /) -> Optional[Item[Self]]:
        """Gets an item with :attr:`Item.id` set as ``id``, or ``None`` if not found."""
        for child in self.walk_children():
            if child.id == id:
                return child  # type: ignore
        return None

    async def interaction_check(self, interaction: Interaction[Any], /) -> bool:
        """|coro|

        A callback that is called when an interaction happens within the view
        that checks whether the view should process item callbacks for the interaction.

        This is useful to override if, for example, you want to ensure that the
        interaction author is a given user.

        The default implementation of this returns ``True``.

        .. note::

            If an exception occurs within the body then the check
            is considered a failure and :meth:`on_error` is called.

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

    async def on_timeout(self) -> None:
        """|coro|

        A callback that is called when a view's timeout elapses without being explicitly stopped.
        """
        pass

    async def on_error(self, interaction: Interaction[Any], error: Exception, item: Item[Any], /) -> None:
        """|coro|

        A callback that is called when an item's callback or :meth:`interaction_check`
        fails with an error.

        The default implementation logs to the library logger.

        Parameters
        -----------
        interaction: :class:`~bisim.Interaction`
            The interaction that led to the failure.
        error: :class:`Exception`
            The exception that was raised.
        item: :class:`Item`
            The item that failed the dispatch.
        """
        _log.error('Ignoring exception in view %r for item %r', self, item, exc_info=error)

    async def _scheduled_task(self, item: Item[Any], interaction: Interaction[Any]) -> None:
        try:
            item._refresh_state(interaction, interaction.data or {})  # type: ignore

            allow = await item.interaction_check(interaction) and await self.interaction_check(interaction)
            if not allow:
                return

            if self.timeout:
                self.__timeout_expiry = time.monotonic() + self.timeout

            await item.callback(interaction)
        except Exception as e:
            return await self.on_error(interaction, e, item)

    def _start_listening_from_store(self, store: ViewStore) -> None:
        self.__cancel_callback = partial(store.remove_view)  # type: ignore
        if self.timeout:
            if self.__timeout_task is not None:
                self.__timeout_task.cancel()

            self.__timeout_expiry = time.monotonic() + self.timeout
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            self.__timeout_task = loop.create_task(self.__timeout_task_impl())

    def _finish(self, timed_out: bool) -> None:
        self.__finished = True
        self.__timed_out = timed_out
        if self.__stopped is not None and not self.__stopped.done():
            self.__stopped.set_result(timed_out)

    def _dispatch_timeout(self) -> None:
        if self.__finished:
            return

        if self.__cancel_callback:
            self.__cancel_callback(self)
            self.__cancel_callback = None

        self._finish(True)
        asyncio.create_task(self.on_timeout(), name=f'bisim-ui-view-timeout-{self.id}')

    def _dispatch_item(self, item: Item[Any], interaction: Interaction[Any]) -> Optional[asyncio.Task[None]]:
        if self.__finished:
            return None

        return asyncio.create_task(self._scheduled_task(item, interaction), name=f'bisim-ui-view-dispatch-{self.id}')

    def _refresh(self, components: List[Component]) -> None:
        # Fix up the children from the message's components, matching by custom id.
        old_state: Dict[Tuple[int, str], Item[Any]] = {
            (item.type.value, item.custom_id): item  # type: ignore
            for item in self._children
            if item.is_dispatchable()
        }
        for component in _walk_all_components(components):
            custom_id = getattr(component, 'custom_id', None)
            if custom_id is None:
                continue
            try:
                older = old_state[(component.type.value, custom_id)]  # type: ignore
            except KeyError:
                continue
            older._refresh_component(component)

    def stop(self) -> None:
        """Stops listening to interaction events from this view.

        This operation cannot be undone.
        """
        if not self.__finished:
            self._finish(False)

        self.__timeout_expiry = None
        if self.__timeout_task is not None:
            self.__timeout_task.cancel()
            self.__timeout_task = None

        if self.__cancel_callback:
            self.__cancel_callback(self)
            self.__cancel_callback = None

    def is_finished(self) -> bool:
        """:class:`bool`: Whether the view has finished interacting."""
        return self.__finished

    def is_dispatching(self) -> bool:
        """:class:`bool`: Whether the view has been added for dispatching purposes."""
        return self.__cancel_callback is not None

    def is_persistent(self) -> bool:
        """:class:`bool`: Whether the view is set up as persistent.

        A persistent view has all their components with a set ``custom_id`` and
        a :attr:`timeout` set to ``None``.
        """
        return self.timeout is None and all(item.is_persistent() for item in self._children)

    async def wait(self) -> bool:
        """|coro|

        Waits until the view has finished interacting.

        A view is considered finished when :meth:`stop` is called
        or it times out.

        Returns
        --------
        :class:`bool`
            If ``True``, then the view timed out. If ``False`` then
            the view finished normally.
        """
        return await self._stopped_future()


class ViewStore:
    """Keeps the views (and modals) that wait for interactions."""

    def __init__(self, state: ConnectionState):
        self._views: Dict[Optional[int], Dict[Tuple[int, str], Item[Any]]] = {}
        self._synced_message_views: Dict[int, View] = {}
        self._modals: Dict[str, Modal] = {}
        self._state: ConnectionState = state

    @property
    def persistent_views(self) -> Sequence[View]:
        views = {
            item.view.id: item.view
            for items in self._views.values()
            for item in items.values()
            if item.view and item.view.is_persistent()
        }
        return list(views.values())

    def add_view(self, view: View, message_id: Optional[int] = None) -> None:
        view._start_listening_from_store(self)
        if view.__bisim_ui_modal__:
            self._modals[view.custom_id] = view  # type: ignore
            return

        dispatch_info = self._views.setdefault(message_id, {})
        for item in view.walk_children():
            if item.is_dispatchable():
                dispatch_info[(item.type.value, item.custom_id)] = item  # type: ignore

        view._cache_key = message_id
        if message_id is not None:
            self._synced_message_views[message_id] = view

    def remove_view(self, view: View) -> None:
        if view.__bisim_ui_modal__:
            self._modals.pop(view.custom_id, None)  # type: ignore
            return

        dispatch_info = self._views.get(view._cache_key)
        if dispatch_info:
            for item in view.walk_children():
                if item.is_dispatchable():
                    current = dispatch_info.get((item.type.value, item.custom_id))  # type: ignore
                    if current is item:
                        dispatch_info.pop((item.type.value, item.custom_id), None)  # type: ignore

            if len(dispatch_info) == 0:
                self._views.pop(view._cache_key, None)

        if view._cache_key is not None:
            self._synced_message_views.pop(view._cache_key, None)

    def dispatch_view(self, component_type: int, custom_id: str, interaction: Interaction[Any]) -> None:
        message_id: Optional[int] = None
        if interaction.message is not None:
            message_id = interaction.message.id

        key = (component_type, custom_id)
        item: Optional[Item[Any]] = None
        if message_id is not None:
            item = self._views.get(message_id, {}).get(key)
        if item is None:
            item = self._views.get(None, {}).get(key)
        if item is None:
            _log.debug('View interaction referencing unknown view %s %r. Discarding', component_type, custom_id)
            return

        view = item.view
        if view is None:
            return
        view._dispatch_item(item, interaction)

    def dispatch_modal(self, custom_id: str, interaction: Interaction[Any], fields: List[Dict[str, Any]]) -> None:
        modal = self._modals.get(custom_id)
        if modal is None:
            _log.debug('Modal interaction referencing unknown custom_id %s. Discarding', custom_id)
            return

        modal._dispatch_submit(interaction, fields)

    def remove_interaction_mapping(self, interaction_id: int) -> None:
        # Bisim gives the message right away, so there is no interaction-keyed mapping.
        return None

    def is_message_tracked(self, message_id: int) -> bool:
        return message_id in self._synced_message_views

    def remove_message_tracking(self, message_id: int) -> Optional[View]:
        return self._synced_message_views.pop(message_id, None)

    def update_from_message(self, message_id: int, data: List[Dict[str, Any]]) -> None:
        components: List[Component] = []
        for component_data in data:
            component = _component_factory(component_data)
            if component is not None:
                components.append(component)

        view = self._synced_message_views.get(message_id)
        if view is not None:
            view._refresh(components)

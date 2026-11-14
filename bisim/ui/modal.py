from __future__ import annotations

import asyncio
import copy
import logging
import os
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Tuple

from .. import utils
from .item import Item
from .view import View

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..interactions import Interaction

__all__ = ('Modal',)

_log = logging.getLogger(__name__)


class Modal(View):
    """Represents a UI modal.

    This object must be inherited to create a modal popup window within Bisim.

    Examples
    ----------

    .. code-block:: python3

        from bisim import ui

        class Questionnaire(ui.Modal, title='Questionnaire Response'):
            name = ui.TextInput(label='Name')
            answer = ui.TextInput(label='Answer', style=bisim.TextStyle.paragraph)

            async def on_submit(self, interaction: bisim.Interaction):
                await interaction.response.send_message(f'Thanks for your response, {self.name}!', ephemeral=True)

    Parameters
    -----------
    title: :class:`str`
        The title of the modal. Can only be up to 45 characters.
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    custom_id: :class:`str`
        The ID of the modal that gets received during an interaction.
        If not given then one is generated for you.
        Can only be up to 100 characters.

    Attributes
    ------------
    title: :class:`str`
        The title of the modal.
    custom_id: :class:`str`
        The ID of the modal that gets received during an interaction.
    """

    if TYPE_CHECKING:
        title: str

    __bisim_ui_modal__: ClassVar[bool] = True
    __modal_children_items__: ClassVar[Dict[str, Item[Self]]] = {}

    def __init_subclass__(cls, *, title: str = utils.MISSING, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        if title is not utils.MISSING:
            cls.title = title

        children: Dict[str, Item[Any]] = {}
        for base in reversed(cls.__mro__):
            for name, member in base.__dict__.items():
                if isinstance(member, Item):
                    children[name] = member

        cls.__modal_children_items__ = children

    def _init_children(self) -> List[Item[Self]]:
        children = []
        for name, item in self.__modal_children_items__.items():
            item = copy.deepcopy(item)
            setattr(self, name, item)
            item._view = self
            children.append(item)
        return children

    def __init__(
        self,
        *,
        title: str = utils.MISSING,
        timeout: Optional[float] = None,
        custom_id: str = utils.MISSING,
    ) -> None:
        if title is utils.MISSING and getattr(self, 'title', utils.MISSING) is utils.MISSING:
            raise ValueError('Modal must have a title')
        elif title is not utils.MISSING:
            self.title = title
        self.custom_id: str = os.urandom(16).hex() if custom_id is utils.MISSING else custom_id

        super().__init__(timeout=timeout)

    async def on_submit(self, interaction: Interaction[Any], /) -> None:
        """|coro|

        Called when the modal is submitted.

        Parameters
        -----------
        interaction: :class:`.Interaction`
            The interaction that submitted this modal.
        """
        pass

    async def on_error(self, interaction: Interaction[Any], error: Exception, /) -> None:  # type: ignore
        """|coro|

        A callback that is called when :meth:`on_submit`
        fails with an error.

        The default implementation logs to the library logger.

        Parameters
        -----------
        interaction: :class:`~bisim.Interaction`
            The interaction that led to the failure.
        error: :class:`Exception`
            The exception that was raised.
        """
        _log.error('Ignoring exception in modal %r:', self, exc_info=error)

    def _refresh_from_fields(self, interaction: Interaction[Any], fields: List[Dict[str, Any]]) -> None:
        by_id: Dict[str, Item[Any]] = {
            getattr(child, 'custom_id', None): child for child in self._children  # type: ignore
        }
        for field in fields:
            custom_id = field.get('customId') or field.get('custom_id')
            item = by_id.get(custom_id)
            if item is None:
                _log.debug('Modal interaction referencing unknown item custom_id %s. Discarding', custom_id)
                continue
            item._refresh_state(interaction, field)

    async def _scheduled_task(self, interaction: Interaction[Any], fields: List[Dict[str, Any]]) -> None:  # type: ignore
        try:
            self._refresh_timeout()
            self._refresh_from_fields(interaction, fields)

            allow = await self.interaction_check(interaction)
            if not allow:
                return

            await self.on_submit(interaction)
        except Exception as e:
            return await self.on_error(interaction, e)
        else:
            # A submitted modal is done: it cannot be answered twice.
            self.stop()

    def _dispatch_submit(self, interaction: Interaction[Any], fields: List[Dict[str, Any]]) -> asyncio.Task[None]:
        return asyncio.create_task(self._scheduled_task(interaction, fields), name=f'bisim-ui-modal-dispatch-{self.id}')

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            'customId': self.custom_id,
            'title': self.title,
            'components': self.to_components(),
        }
        return payload


def _modal_fields(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The submitted values: Bisim's ``fields``, or Discord's nested ``components``."""
    fields = data.get('fields')
    if isinstance(fields, list):
        return fields
    result: List[Dict[str, Any]] = []
    for row in data.get('components') or []:
        children = row.get('components') if isinstance(row, dict) else None
        if children:
            result.extend(c for c in children if isinstance(c, dict))
        elif isinstance(row, dict) and ('customId' in row or 'custom_id' in row):
            result.append(row)
    return result

from __future__ import annotations

from typing import Any, Callable, Coroutine, TypeVar, Union

T = TypeVar('T')

Coro = Coroutine[Any, Any, T]
MaybeCoro = Union[T, Coro[T]]
Check = Callable[..., MaybeCoro[bool]]


def _base_command_class() -> type:
    from .core import _BaseCommand

    return _BaseCommand


class _BaseCommandProxy(type):
    def __instancecheck__(cls, instance: Any) -> bool:
        return isinstance(instance, _base_command_class())


class _BaseCommand(metaclass=_BaseCommandProxy):
    """Stands in for the base class of text commands (used by the cog machinery)."""

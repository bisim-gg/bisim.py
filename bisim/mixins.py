from __future__ import annotations

from typing import Any

__all__ = (
    'EqualityComparable',
    'Hashable',
)


class EqualityComparable:
    """Objects that are equal when they are of the same kind with the same ``id``."""

    __slots__ = ()

    id: int

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and other.id == self.id

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class Hashable(EqualityComparable):
    """Like :class:`EqualityComparable`, and hashed by ``id``."""

    __slots__ = ()

    def __hash__(self) -> int:
        return self.id >> 22


def _id_key(value: Any) -> int:
    return int(getattr(value, 'id', value))

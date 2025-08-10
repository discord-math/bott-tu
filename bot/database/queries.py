from __future__ import annotations

from dataclasses import fields
from typing import Any, Callable, Generic, Iterable, Iterator, Type, TypeVar

import asyncpg.pool


T = TypeVar("T")
S = TypeVar("S")


class FieldOrder(Generic[T]):
    """
    This class helps convert dataclasses to and from ordered lists of fields, in order to help construct SQL queries in
    a way where one does not accidentally mess up the field names or the field order.

    An instance of FieldOrder holds onto one or more classes, and all its methods use the same order to talk about the
    classes and their fields.

    Given a dataclass:

    .. code-block:: python

        @dataclass
        class MyClass:
            x: int
            y: str

        fields = FieldOrder(MyClass)

    We can use the following idioms:

    .. code-block:: python

        row = await conn.execute(f"SELECT {fields.columns} FROM table")
        value = fields.from_tuple(row)

    .. code-block:: python

        await conn.execute(
            f"INSERT INTO table ({fields.columns}) VALUES ({fields.placeholders})",
            *fields.to_tuple(value),
        )

    .. code-block:: python

        await conn.execute(
            f"UPDATE table SET {fields.set_list}",
            *fields.to_tuple(value),
        )
    """

    _classes: list[tuple[str | None, Type[Any]]]
    _deconstruct: Callable[[T], list[Any]]
    _construct: Callable[[Iterator[Any]], T]

    def __init__(self, cls: Type[T], /, *, prefix: str | None = None):
        self._classes = [(prefix, cls)]
        self._deconstruct = lambda arg: [arg]
        self._construct = next

    @property
    def columns(self) -> str:
        """
        Comma-separated list of field names in the correct order, e.g. ``FieldOrder(MyClass).columns`` is ``"x, y"``.
        """
        return ", ".join(
            field.name if prefix is None else f"{prefix}.{field.name}"
            for prefix, cls in self._classes
            for field in fields(cls)
        )

    @property
    def placeholders(self) -> str:
        """
        Comma-separated list of numbered placeholders, e.g. ``FieldOrder(MyClass).placeholders`` is ``"$1, $2"``.
        """
        return ", ".join(
            f"${i}"
            for i, _ in enumerate(
                (None for _, cls in self._classes for _ in fields(cls)),
                start=1,
            )
        )

    @property
    def set_list(self) -> str:
        """
        Comma-separated list of assignments of field names to numbered placeholders, e.g.
        ``FieldOrder(MyClass).set_list`` is ``"x = $1, y = $2"``.
        """
        return ", ".join(
            f"{field.name} = ${i}" if prefix is None else f"{prefix}.{field.name} = ${i}"
            for i, (prefix, field) in enumerate(
                ((prefix, field) for prefix, cls in self._classes for field in fields(cls)),
                start=1,
            )
        )

    def to_tuple(self, arg: T) -> tuple[Any, ...]:
        """
        Convert a value of the dataclass into a tuple of its fields in the correct order.
        E.g. ``FieldOrder(MyClass).to_tuple(arg)`` is ``(arg.x, arg.y)``.
        """
        return tuple(
            getattr(obj, field.name)
            for (_, cls), obj in zip(self._classes, self._deconstruct(arg))
            for field in fields(cls)
        )

    def from_tuple(self, values: Iterable[Any]) -> T:
        """
        Convert a tuple of fields of a dataclass in the correct order into an instance of that dataclass.
        E.g. ``FieldOrder(MyClass).from_tuple(t)`` is ``MyClass(x=t[0], y=t[1])``.
        """
        inits: list[tuple[Type[Any], dict[str, Any]]]
        inits = [(cls, {}) for _, cls in self._classes]
        for value, (kwargs, field) in zip(values, ((kwargs, field) for cls, kwargs in inits for field in fields(cls))):
            kwargs[field.name] = value

        return self._construct(cls(**kwargs) for cls, kwargs in inits)

    def tupled(self, cls: Type[S], /, *, prefix: str | None = None) -> FieldOrder[tuple[T, S]]:
        """
        Construct a FieldOrder referencing more than one class at a time:

        .. code-block:: python

            @dataclass
            class OtherClass:
                z: int

            allFields = FieldOrder(MyClass).tupled(OtherClass)

            # allFields.columns is "x, y, z"
            # allFields.placeholders is "$1, $2, $3"
            # allFields.set_list is "x = $1, y = $2, z = $3"
            # allFields.to_tuple(arg) is (arg[0].x, arg[0].y, arg[1].z)
            # allFields.from_tuple(t) is (MyClass(x=t[0], y=t[1]), OtherClass(z=t[2]))

        The ``prefix`` arguments can be used to disambiguate column expressions:

        .. code-block:: python

            taggedFields = FieldOrder(MyClass, prefix="my").tupled(OtherClass, prefix="other")

            # taggedFields.columns is "my.x, my.y, other.z"

            row = await conn.execute(f"SELECT {taggedFields.columns} FROM table AS my, table2 AS other")
            my, other = taggedFields.from_tuple(row)

        """

        ty: type[FieldOrder[tuple[T, S]]] = FieldOrder  # type: ignore
        result = FieldOrder.__new__(ty)
        result._classes = self._classes + [(prefix, cls)]
        result._deconstruct = lambda arg: self._deconstruct(arg[0]) + [arg[1]]
        result._construct = lambda iter: (self._construct(iter), next(iter))
        return result


_Connected = asyncpg.Connection | asyncpg.pool.PoolConnectionProxy


async def select_single(connection: _Connected, table: str, cls: Type[T], condition: str | None = None, /) -> T | None:
    """
    Select the first row of the given table that satisfies the given condition, and build the given dataclass out of it.
    Returns None if no such row is found.
    """
    fields = FieldOrder(cls)
    row = await connection.fetchrow(
        f"SELECT {fields.columns} FROM {table}" + ("" if condition is None else f" WHERE ({condition})")
    )
    return None if row is None else fields.from_tuple(row)


async def insert(connection: _Connected, table: str, value: object, /) -> None:
    """
    Insert the given value (must be a dataclass) into the given table.
    """
    fields = FieldOrder(type(value))
    await connection.execute(
        f"INSERT INTO {table} ({fields.columns}) VALUES ({fields.placeholders})",
        *fields.to_tuple(value),
    )

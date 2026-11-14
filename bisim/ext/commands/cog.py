from __future__ import annotations

import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

from ... import app_commands
from ...utils import MISSING, maybe_coroutine
from ._types import _BaseCommand

if TYPE_CHECKING:
    from typing_extensions import Self

    from ...abc import Snowflake
    from .bot import BotBase
    from .context import Context
    from .core import Command

__all__ = (
    'CogMeta',
    'Cog',
    'GroupCog',
)

FuncT = TypeVar('FuncT', bound=Callable[..., Any])

_FORBIDDEN_PREFIXES = ('cog_', 'bot_')


def _check_name(owner: type, attr: str) -> None:
    if attr.startswith(_FORBIDDEN_PREFIXES):
        raise TypeError(f'Commands or listeners must not start with cog_ or bot_ (in method {owner.__name__}.{attr})')


class CogMeta(type):
    """A metaclass for defining a cog.

    Note that you should probably not use this directly. It is exposed
    purely for documentation purposes along with making custom metaclasses to intermix
    with other metaclasses such as the :class:`abc.ABCMeta` metaclass.

    The keyword arguments a cog class takes are ``name``, ``description``
    and ``command_attrs`` (attributes applied to every command in the cog).

    Attributes
    -----------
    name: :class:`str`
        The cog name. By default, it is the name of the class with no modification.
    description: :class:`str`
        The cog description. By default, it is the cleaned docstring of the class.
    command_attrs: :class:`dict`
        A list of attributes to apply to every command inside this cog.
    """

    __cog_name__: str
    __cog_description__: str
    __cog_settings__: Dict[str, Any]
    __cog_commands__: List[Command[Any, ..., Any]]
    __cog_is_app_commands_group__: bool
    __cog_app_commands__: List[Union[app_commands.Group, app_commands.Command[Any, ..., Any]]]
    __cog_listeners__: List[Tuple[str, str]]

    def __new__(cls, *args: Any, **kwargs: Any) -> CogMeta:
        name, bases, attrs = args
        if any(issubclass(base, app_commands.Group) for base in bases):
            raise TypeError(
                'Cannot inherit from app_commands.Group with commands.Cog, consider using commands.GroupCog instead'
            )

        cog_name = kwargs.pop('name', name)
        attrs['__cog_settings__'] = kwargs.pop('command_attrs', {})
        if '__cog_is_app_commands_group__' not in attrs:
            attrs['__cog_is_app_commands_group__'] = any(getattr(b, '__cog_is_app_commands_group__', False) for b in bases)

        description = kwargs.pop('description', None)
        if description is None:
            description = inspect.cleandoc(attrs.get('__doc__', '') or '')
        attrs['__cog_description__'] = description
        attrs['__cog_name__'] = cog_name

        group_kwargs = {key: kwargs.pop(key) for key in ('group_name', 'group_description', 'group_nsfw') if key in kwargs}
        attrs['__cog_group_kwargs__'] = group_kwargs

        new_cls = super().__new__(cls, name, bases, attrs, **kwargs)

        commands: Dict[str, Any] = {}
        app: Dict[str, Any] = {}
        listeners: Dict[str, Callable[..., Any]] = {}

        for klass in reversed(new_cls.__mro__):
            for attr, value in klass.__dict__.items():
                # A later definition of the same name replaces an earlier one.
                commands.pop(attr, None)
                app.pop(attr, None)
                listeners.pop(attr, None)

                is_static = isinstance(value, staticmethod)
                if is_static:
                    value = value.__func__

                if isinstance(value, _BaseCommand):
                    if is_static:
                        raise TypeError(f'Command in method {klass}.{attr!r} must not be staticmethod.')
                    _check_name(klass, attr)
                    commands[attr] = value
                elif isinstance(value, (app_commands.Group, app_commands.Command)) and value.parent is None:
                    _check_name(klass, attr)
                    app[attr] = value
                elif inspect.iscoroutinefunction(value) and hasattr(value, '__cog_listener__'):
                    _check_name(klass, attr)
                    listeners[attr] = value

        new_cls.__cog_commands__ = list(commands.values())
        new_cls.__cog_app_commands__ = list(app.values())
        new_cls.__cog_listeners__ = [
            (event_name, function.__name__) for function in listeners.values() for event_name in function.__cog_listener_names__
        ]
        return new_cls

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args)

    @classmethod
    def qualified_name(cls) -> str:
        return cls.__cog_name__


def _cog_special_method(func: FuncT) -> FuncT:
    func.__cog_special_method__ = None  # type: ignore
    return func


class Cog(metaclass=CogMeta):
    """The base class that all cogs must inherit from.

    A cog is a collection of commands, listeners, and optional state to
    help group commands together. More information on them can be found on
    the :ref:`ext_commands_cogs` page.

    When inheriting from this class, the options shown in :class:`CogMeta`
    are equally valid here.
    """

    __cog_name__: str
    __cog_description__: str
    __cog_settings__: Dict[str, Any]
    __cog_commands__: List[Command[Self, ..., Any]]
    __cog_app_commands__: List[Union[app_commands.Group, app_commands.Command[Self, ..., Any]]]
    __cog_listeners__: List[Tuple[str, str]]
    __cog_is_app_commands_group__: ClassVar[bool] = False
    __cog_app_commands_group__: Optional[app_commands.Group]

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        self = super().__new__(cls)
        command_attrs = cls.__cog_settings__

        # Every instance gets its own copies of the commands.
        copies = tuple(c._update_copy(command_attrs) for c in cls.__cog_commands__)
        by_name = {c.qualified_name: c for c in copies}
        for command in copies:
            setattr(self, command.callback.__name__, command)
            parent = command.parent
            if parent is not None:
                # Point the copied parent at this copy instead of the class's command.
                fresh_parent = by_name[parent.qualified_name]  # type: ignore
                fresh_parent.remove_command(command.name)  # type: ignore
                fresh_parent.add_command(command)  # type: ignore
        self.__cog_commands__ = copies  # type: ignore

        group: Optional[app_commands.Group] = None
        if cls.__cog_is_app_commands_group__:
            group_kwargs = getattr(cls, '__cog_group_kwargs__', {})
            group = app_commands.Group(
                name=group_kwargs.get('group_name', cls.__cog_name__.lower()),
                description=group_kwargs.get('group_description', cls.__cog_description__ or '…'),
                nsfw=group_kwargs.get('group_nsfw', False),
                parent=None,
            )
            group.module = cls.__module__
        self.__cog_app_commands_group__ = group

        app_copies: List[Any] = []
        for command in cls.__cog_app_commands__:
            copy = command._copy_with(parent=group, binding=self)
            if copy._attr:
                setattr(self, copy._attr, copy)
            if isinstance(copy, app_commands.Group):
                copy.__bisim_app_commands_error_handler__ = self.cog_app_command_error  # type: ignore
            app_copies.append(copy)
            if group is not None:
                group.add_command(copy, override=True)
        self.__cog_app_commands__ = app_copies  # type: ignore

        self.__bisim_app_commands_error_handler__ = (
            self.cog_app_command_error if cls._get_overridden_method(self.cog_app_command_error) is not None else None
        )
        return self

    def get_commands(self) -> List[Command[Self, ..., Any]]:
        r"""Returns the commands that are defined inside this cog.

        This does *not* include :class:`bisim.app_commands.Command` or :class:`bisim.app_commands.Group`
        instances.

        Returns
        --------
        List[:class:`.Command`]
            A :class:`list` of :class:`.Command`\s that are
            defined inside this cog, not including subcommands.
        """
        return [c for c in self.__cog_commands__ if c.parent is None]

    def get_app_commands(self) -> List[Union[app_commands.Command[Self, ..., Any], app_commands.Group]]:
        r"""Returns the app commands that are defined inside this cog.

        Returns
        --------
        List[Union[:class:`bisim.app_commands.Command`, :class:`bisim.app_commands.Group`]]
            A :class:`list` of :class:`bisim.app_commands.Command`\s and :class:`bisim.app_commands.Group`\s that are
            defined inside this cog, not including subcommands.
        """
        return [c for c in self.__cog_app_commands__ if c.parent is None]

    @property
    def qualified_name(self) -> str:
        """:class:`str`: Returns the cog's specified name, not the class name."""
        return self.__cog_name__

    @property
    def description(self) -> str:
        """:class:`str`: Returns the cog's description, typically the cleaned docstring."""
        return self.__cog_description__

    @description.setter
    def description(self, description: str) -> None:
        self.__cog_description__ = description

    def walk_commands(self) -> Generator[Command[Self, ..., Any], None, None]:
        """An iterator that recursively walks through this cog's commands and subcommands.

        Yields
        ------
        Union[:class:`.Command`, :class:`.Group`]
            A command or group from the cog.
        """
        from .core import GroupMixin

        for command in self.__cog_commands__:
            if command.parent is None:
                yield command
                if isinstance(command, GroupMixin):
                    yield from command.walk_commands()

    def walk_app_commands(self) -> Generator[Union[app_commands.Command[Self, ..., Any], app_commands.Group], None, None]:
        """An iterator that recursively walks through this cog's app commands and subcommands.

        Yields
        ------
        Union[:class:`bisim.app_commands.Command`, :class:`bisim.app_commands.Group`]
            An app command or group from the cog.
        """
        for command in self.__cog_app_commands__:
            yield command
            if isinstance(command, app_commands.Group):
                yield from command.walk_commands()

    @property
    def app_command(self) -> Optional[app_commands.Group]:
        """Optional[:class:`bisim.app_commands.Group`]: Returns the associated group with this cog.

        This is only available if inheriting from :class:`GroupCog`.
        """
        return self.__cog_app_commands_group__

    def get_listeners(self) -> List[Tuple[str, Callable[..., Any]]]:
        """Returns a :class:`list` of (name, function) listener pairs that are defined in this cog.

        Returns
        --------
        List[Tuple[:class:`str`, :ref:`coroutine <coroutine>`]]
            The listeners defined in this cog.
        """
        return [(name, getattr(self, method_name)) for name, method_name in self.__cog_listeners__]

    @classmethod
    def _get_overridden_method(cls, method: FuncT) -> Optional[FuncT]:
        """Return None if the method is not overridden. Otherwise returns the overridden method."""
        return getattr(getattr(method, '__func__', method), '__cog_special_method__', method)

    @classmethod
    def listener(cls, name: str = MISSING) -> Callable[[FuncT], FuncT]:
        """A decorator that marks a function as a listener.

        This is the cog equivalent of :meth:`.Bot.listen`.

        Parameters
        ------------
        name: :class:`str`
            The name of the event being listened to. If not provided, it
            defaults to the function's name.

        Raises
        --------
        TypeError
            The function is not a coroutine function or a string was not passed as
            the name.
        """

        if name is not MISSING and not isinstance(name, str):
            raise TypeError(f'Cog.listener expected str but received {name.__class__.__name__} instead.')

        def decorator(func: FuncT) -> FuncT:
            actual = func
            if isinstance(actual, staticmethod):
                actual = actual.__func__
            if not inspect.iscoroutinefunction(actual):
                raise TypeError('Listener function must be a coroutine function.')
            actual.__cog_listener__ = True  # type: ignore
            to_assign = name or actual.__name__
            try:
                actual.__cog_listener_names__.append(to_assign)  # type: ignore
            except AttributeError:
                actual.__cog_listener_names__ = [to_assign]  # type: ignore
            return func

        return decorator

    def has_error_handler(self) -> bool:
        """:class:`bool`: Checks whether the cog has an error handler."""
        return not hasattr(self.cog_command_error.__func__, '__cog_special_method__')  # type: ignore

    def has_app_command_error_handler(self) -> bool:
        """:class:`bool`: Checks whether the cog has an app error handler."""
        return not hasattr(self.cog_app_command_error.__func__, '__cog_special_method__')  # type: ignore

    @_cog_special_method
    async def cog_load(self) -> None:
        """|maybecoro|

        A special method that is called when the cog gets loaded.

        Subclasses must replace this if they want special asynchronous loading behaviour.
        Note that the ``__init__`` special method does not allow asynchronous code to run
        inside it, thus this is helpful for setting up code that needs to be asynchronous.
        """
        pass

    @_cog_special_method
    async def cog_unload(self) -> None:
        """|maybecoro|

        A special method that is called when the cog gets removed.

        Subclasses must replace this if they want special unloading behaviour.

        Exceptions raised in this method are ignored during extension unloading.
        """
        pass

    @_cog_special_method
    def bot_check_once(self, ctx: Context[Any]) -> bool:
        """A special method that registers as a :meth:`.Bot.check_once`
        check.

        This function **can** be a coroutine and must take a sole parameter,
        ``ctx``, to represent the :class:`.Context`.
        """
        return True

    @_cog_special_method
    def bot_check(self, ctx: Context[Any]) -> bool:
        """A special method that registers as a :meth:`.Bot.check`
        check.

        This function **can** be a coroutine and must take a sole parameter,
        ``ctx``, to represent the :class:`.Context`.
        """
        return True

    @_cog_special_method
    def cog_check(self, ctx: Context[Any]) -> bool:
        """A special method that registers as a :func:`~bisim.ext.commands.check`
        for every command and subcommand in this cog.

        This function **can** be a coroutine and must take a sole parameter,
        ``ctx``, to represent the :class:`.Context`.
        """
        return True

    @_cog_special_method
    def interaction_check(self, interaction: Any, /) -> bool:
        """A special method that registers as a :func:`bisim.app_commands.check`
        for every app command and subcommand in this cog.

        This function **can** be a coroutine and must take a sole parameter,
        ``interaction``, to represent the :class:`~bisim.Interaction`.
        """
        return True

    @_cog_special_method
    async def cog_command_error(self, ctx: Context[Any], error: Exception) -> None:
        """|coro|

        A special method that is called whenever an error
        is dispatched inside this cog.

        This is similar to :func:`.on_command_error` except only applying
        to the commands inside this cog.

        This **must** be a coroutine.

        Parameters
        -----------
        ctx: :class:`.Context`
            The invocation context where the error happened.
        error: :class:`CommandError`
            The error that happened.
        """
        pass

    @_cog_special_method
    async def cog_app_command_error(self, interaction: Any, error: Exception) -> None:
        """|coro|

        A special method that is called whenever an error within
        an application command is dispatched inside this cog.

        This is similar to :func:`bisim.app_commands.CommandTree.on_error` except
        only applying to the application commands inside this cog.

        This **must** be a coroutine.

        Parameters
        -----------
        interaction: :class:`~bisim.Interaction`
            The interaction that is being handled.
        error: :exc:`~bisim.app_commands.AppCommandError`
            The exception that was raised.
        """
        pass

    @_cog_special_method
    async def cog_before_invoke(self, ctx: Context[Any]) -> None:
        """|coro|

        A special method that acts as a cog local pre-invoke hook.

        This is similar to :meth:`.Command.before_invoke`.

        This **must** be a coroutine.

        Parameters
        -----------
        ctx: :class:`.Context`
            The invocation context.
        """
        pass

    @_cog_special_method
    async def cog_after_invoke(self, ctx: Context[Any]) -> None:
        """|coro|

        A special method that acts as a cog local post-invoke hook.

        This is similar to :meth:`.Command.after_invoke`.

        This **must** be a coroutine.

        Parameters
        -----------
        ctx: :class:`.Context`
            The invocation context.
        """
        pass

    async def _inject(self, bot: BotBase, override: bool, guild: Optional[Snowflake], guilds: Sequence[Snowflake]) -> Self:
        cls = self.__class__

        # Run the cog's own setup first so a failure leaves nothing half added.
        await maybe_coroutine(self.cog_load)

        added: List[Command[Any, ..., Any]] = []
        try:
            for command in self.__cog_commands__:
                command.cog = self
                if command.parent is None:
                    bot.add_command(command)
                    added.append(command)
        except Exception:
            for command in added:
                bot.remove_command(command.name)
            try:
                await maybe_coroutine(self.cog_unload)
            finally:
                raise

        tree = bot.tree
        if self.__cog_app_commands_group__ is not None:
            tree.add_command(self.__cog_app_commands_group__, override=override, guild=guild, guilds=guilds)
        else:
            for command in self.__cog_app_commands__:
                tree.add_command(command, override=override, guild=guild, guilds=guilds)

        if cls.bot_check is not Cog.bot_check:
            bot.add_check(self.bot_check)

        if cls.bot_check_once is not Cog.bot_check_once:
            bot.add_check(self.bot_check_once, call_once=True)

        for name, method_name in self.__cog_listeners__:
            bot.add_listener(getattr(self, method_name), name)

        return self

    async def _eject(self, bot: BotBase, guild_ids: Optional[Sequence[int]]) -> None:
        cls = self.__class__

        try:
            for command in self.__cog_commands__:
                if command.parent is None:
                    bot.remove_command(command.name)

            if self.__cog_app_commands_group__ is not None:
                if guild_ids is None:
                    bot.tree.remove_command(self.__cog_app_commands_group__.name)
                else:
                    for guild_id in guild_ids:
                        bot.tree.remove_command(self.__cog_app_commands_group__.name, guild=_Snowflake(guild_id))
            else:
                for command in self.__cog_app_commands__:
                    if guild_ids is None:
                        bot.tree.remove_command(command.name)
                    else:
                        for guild_id in guild_ids:
                            bot.tree.remove_command(command.name, guild=_Snowflake(guild_id))

            for name, method_name in self.__cog_listeners__:
                bot.remove_listener(getattr(self, method_name), name)

            if cls.bot_check is not Cog.bot_check:
                bot.remove_check(self.bot_check)

            if cls.bot_check_once is not Cog.bot_check_once:
                bot.remove_check(self.bot_check_once, call_once=True)
        finally:
            try:
                await maybe_coroutine(self.cog_unload)
            except Exception:
                pass


class _Snowflake:
    __slots__ = ('id',)

    def __init__(self, id: int) -> None:
        self.id = id


class GroupCog(Cog):
    """Represents a cog that also doubles as a parent :class:`bisim.app_commands.Group` for
    the application commands defined within it.

    This inherits from :class:`Cog` and the options in :class:`CogMeta` also apply to this.
    The group's name, description and NSFW setting come from the ``group_name``,
    ``group_description`` and ``group_nsfw`` class keyword arguments.

    .. warning::

        Hybrid commands are not built yet, so only app commands defined in
        the cog join the group.
    """

    __cog_is_app_commands_group__: ClassVar[bool] = True

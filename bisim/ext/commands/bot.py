from __future__ import annotations

import asyncio
import collections
import collections.abc
import importlib.util
import inspect
import logging
import sys
import types
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Type,
    TypeVar,
    Union,
)

import bisim

from ... import app_commands, utils
from ...utils import MISSING, maybe_coroutine
from . import errors
from .cog import Cog
from .context import Context
from .core import GroupMixin
from .help import DefaultHelpCommand, HelpCommand
from .view import StringView

if TYPE_CHECKING:
    from typing_extensions import Self

    from ...abc import Snowflake
    from ...message import Message
    from ...user import User

__all__ = (
    'when_mentioned',
    'when_mentioned_or',
    'Bot',
    'AutoShardedBot',
)

T = TypeVar('T')
CFT = TypeVar('CFT', bound=Callable[..., Any])

_log = logging.getLogger(__name__)


def when_mentioned(bot: Any, msg: Message, /) -> List[str]:
    """A callable that implements a command prefix equivalent to being mentioned.

    These are meant to be passed into the :attr:`.Bot.command_prefix` attribute.
    """
    return [f'<@{bot.user.id}> ', f'<@!{bot.user.id}> ']  # type: ignore


def when_mentioned_or(*prefixes: str) -> Callable[[Any, Message], List[str]]:
    """A callable that implements when mentioned or other prefixes provided.

    These are meant to be passed into the :attr:`.Bot.command_prefix` attribute.

    Example
    --------

    .. code-block:: python3

        bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'))

    .. note::

        This callable returns another callable, so if this is done inside a custom
        callable, you must call the returned callable, for example:

        .. code-block:: python3

            async def get_prefix(bot, message):
                extras = await prefixes_for(message.guild) # returns a list
                return commands.when_mentioned_or(*extras)(bot, message)
    """

    def inner(bot: Any, msg: Message) -> List[str]:
        r = list(prefixes)
        r = when_mentioned(bot, msg) + r
        return r

    return inner


def _is_submodule(parent: str, child: str) -> bool:
    return parent == child or child.startswith(parent + '.')


class _DefaultRepr:
    def __repr__(self) -> str:
        return '<default-help-command>'


_default: Any = _DefaultRepr()


class BotBase(GroupMixin[None]):
    def __init__(
        self,
        command_prefix: Any,
        *,
        help_command: Optional[HelpCommand] = _default,
        tree_cls: Type[app_commands.CommandTree[Any]] = app_commands.CommandTree,
        description: Optional[str] = None,
        allowed_contexts: app_commands.AppCommandContext = MISSING,
        allowed_installs: app_commands.AppInstallationType = MISSING,
        intents: bisim.Intents = MISSING,
        **options: Any,
    ) -> None:
        super().__init__(intents=intents, **options)
        self.command_prefix: Any = command_prefix
        self.extra_events: Dict[str, List[Callable[..., Any]]] = {}
        self.__tree: app_commands.CommandTree[Self] = tree_cls(self)  # type: ignore
        if allowed_contexts is not MISSING:
            self.__tree.allowed_contexts = allowed_contexts
        if allowed_installs is not MISSING:
            self.__tree.allowed_installs = allowed_installs
        self.__cogs: Dict[str, Cog] = {}
        self.__extensions: Dict[str, types.ModuleType] = {}
        self._checks: List[Callable[..., Any]] = []
        self._check_once: List[Callable[..., Any]] = []
        self._before_invoke: Optional[Callable[..., Any]] = None
        self._after_invoke: Optional[Callable[..., Any]] = None
        self._help_command: Optional[HelpCommand] = None
        self.description: str = inspect.cleandoc(description) if description else ''
        self.owner_id: Optional[int] = options.get('owner_id')
        self.owner_ids: Optional[Collection[int]] = options.get('owner_ids', set())  # type: ignore
        self.strip_after_prefix: bool = options.get('strip_after_prefix', False)

        if self.owner_id and self.owner_ids:
            raise TypeError('Both owner_id and owner_ids are set.')

        if self.owner_ids and not isinstance(self.owner_ids, collections.abc.Collection):
            raise TypeError(f'owner_ids must be a collection not {self.owner_ids.__class__.__name__}')

        if help_command is _default:
            self.help_command = DefaultHelpCommand()
        else:
            self.help_command = help_command

    # internal helpers

    async def _async_setup_hook(self) -> None:
        await super()._async_setup_hook()  # type: ignore
        prefix = self.command_prefix

        if not self.intents.message_content:  # type: ignore
            trigger_warning = (
                (callable(prefix) and prefix is not when_mentioned)
                or isinstance(prefix, str)
                or (isinstance(prefix, collections.abc.Iterable) and len(list(prefix)) >= 1)
            )
            if trigger_warning:
                _log.debug('Bisim always sends message content; the message_content intent changes nothing.')

    def dispatch(self, event_name: str, /, *args: Any, **kwargs: Any) -> None:
        super().dispatch(event_name, *args, **kwargs)  # type: ignore
        ev = 'on_' + event_name
        for event in self.extra_events.get(ev, []):
            self._schedule_event(event, ev, *args, **kwargs)  # type: ignore

    async def close(self) -> None:
        for extension in tuple(self.__extensions):
            try:
                await self.unload_extension(extension)
            except Exception:
                pass

        for cog in tuple(self.__cogs):
            try:
                await self.remove_cog(cog)
            except Exception:
                pass

        await super().close()  # type: ignore

    async def on_command_error(self, context: Context[Any], exception: errors.CommandError, /) -> None:
        """|coro|

        The default command error handler provided by the bot.

        By default this logs to the library logger, however it could be
        overridden to have a different implementation.

        This only fires if you do not specify any listeners for command error.
        """
        if self.extra_events.get('on_command_error', None):
            return

        command = context.command
        if command and command.has_error_handler():
            return

        cog = context.cog
        if cog and cog.has_error_handler():
            return

        _log.error('Ignoring exception in command %s', command, exc_info=exception)

    # global check registration

    def check(self, func: T, /) -> T:
        r"""A decorator that adds a global check to the bot.

        A global check is similar to a :func:`.check` that is applied
        on a per command basis except it is run before any command checks
        have been verified and applies to every command the bot has.

        .. note::

            This function can either be a regular function or a coroutine.

        Similar to a command :func:`.check`\, this takes a single parameter
        of type :class:`.Context` and can only raise exceptions inherited from
        :exc:`.CommandError`.

        Example
        ---------

        .. code-block:: python3

            @bot.check
            def check_commands(ctx):
                return ctx.command.qualified_name in allowed_commands
        """
        self.add_check(func)  # type: ignore
        return func

    def add_check(self, func: Callable[..., Any], /, *, call_once: bool = False) -> None:
        """Adds a global check to the bot.

        This is the non-decorator interface to :meth:`.check`
        and :meth:`.check_once`.

        Parameters
        -----------
        func
            The function that was used as a global check.
        call_once: :class:`bool`
            If the function should only be called once per
            :meth:`.invoke` call.
        """

        if call_once:
            self._check_once.append(func)
        else:
            self._checks.append(func)

    def remove_check(self, func: Callable[..., Any], /, *, call_once: bool = False) -> None:
        """Removes a global check from the bot.

        This function is idempotent and will not raise an exception
        if the function is not in the global checks.

        Parameters
        -----------
        func
            The function to remove from the global checks.
        call_once: :class:`bool`
            If the function was added with ``call_once=True`` in
            the :meth:`.Bot.add_check` call or using :meth:`.check_once`.
        """
        check_list = self._check_once if call_once else self._checks

        try:
            check_list.remove(func)
        except ValueError:
            pass

    def check_once(self, func: CFT, /) -> CFT:
        r"""A decorator that adds a "call once" global check to the bot.

        Unlike regular global checks, this one is called only once
        per :meth:`.invoke` call.

        Regular global checks are called whenever a command is called
        or :meth:`.Command.can_run` is called. This type of check
        bypasses that and ensures that it's called only once, even inside
        the default help command.
        """
        self.add_check(func, call_once=True)
        return func

    async def can_run(self, ctx: Context[Any], /, *, call_once: bool = False) -> bool:
        data = self._check_once if call_once else self._checks

        if len(data) == 0:
            return True

        return await utils.async_all(f(ctx) for f in data)  # type: ignore

    async def is_owner(self, user: Any, /) -> bool:
        """|coro|

        Checks if a :class:`~bisim.User` or :class:`~bisim.Member` is the owner of
        this bot.

        If an :attr:`owner_id` is not set, it is fetched automatically
        through the use of :meth:`~.Bot.application_info`.

        Parameters
        -----------
        user: :class:`.abc.User`
            The user to check for.

        Returns
        --------
        :class:`bool`
            Whether the user is the owner.
        """

        if self.owner_id:
            return user.id == self.owner_id
        elif self.owner_ids:
            return user.id in self.owner_ids
        else:
            app: bisim.AppInfo = await self.application_info()  # type: ignore
            self.owner_id = owner_id = app.owner.id
            return user.id == owner_id

    def before_invoke(self, coro: CFT, /) -> CFT:
        """A decorator that registers a coroutine as a pre-invoke hook.

        A pre-invoke hook is called directly before the command is
        called. This makes it a useful function to set up database
        connections or any type of set up required.

        This pre-invoke hook takes a sole parameter, a :class:`.Context`.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the pre-invoke hook.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('The pre-invoke hook must be a coroutine.')

        self._before_invoke = coro
        return coro

    def after_invoke(self, coro: CFT, /) -> CFT:
        r"""A decorator that registers a coroutine as a post-invoke hook.

        A post-invoke hook is called directly after the command is
        called. This makes it a useful function to clean-up database
        connections or any type of clean up required.

        This post-invoke hook takes a sole parameter, a :class:`.Context`.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the post-invoke hook.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('The post-invoke hook must be a coroutine.')

        self._after_invoke = coro
        return coro

    # listener registration

    def add_listener(self, func: Callable[..., Any], /, name: str = MISSING) -> None:
        """The non decorator alternative to :meth:`.listen`.

        Parameters
        -----------
        func: :ref:`coroutine <coroutine>`
            The function to call.
        name: :class:`str`
            The name of the event to listen for. Defaults to ``func.__name__``.

        Example
        --------

        .. code-block:: python3

            async def on_ready(): pass
            async def my_message(message): pass

            bot.add_listener(on_ready)
            bot.add_listener(my_message, 'on_message')
        """
        name = func.__name__ if name is MISSING else name

        if not asyncio.iscoroutinefunction(func):
            raise TypeError('Listeners must be coroutines')

        if name in self.extra_events:
            self.extra_events[name].append(func)
        else:
            self.extra_events[name] = [func]

    def remove_listener(self, func: Callable[..., Any], /, name: str = MISSING) -> None:
        """Removes a listener from the pool of listeners.

        Parameters
        -----------
        func
            The function that was used as a listener to remove.
        name: :class:`str`
            The name of the event we want to remove. Defaults to
            ``func.__name__``.
        """

        name = func.__name__ if name is MISSING else name

        if name in self.extra_events:
            try:
                self.extra_events[name].remove(func)
            except ValueError:
                pass

    def listen(self, name: str = MISSING) -> Callable[[CFT], CFT]:
        """A decorator that registers another function as an external
        event listener. Basically this allows you to listen to multiple
        events from different places e.g. such as :func:`.on_ready`

        The functions being listened to must be a :ref:`coroutine <coroutine>`.

        Example
        --------

        .. code-block:: python3

            @bot.listen()
            async def on_message(message):
                print('one')

            # in some other file...

            @bot.listen('on_message')
            async def my_message(message):
                print('two')

        Would print one and two in an unspecified order.

        Raises
        -------
        TypeError
            The function being listened to is not a coroutine.
        """

        def decorator(func: CFT) -> CFT:
            self.add_listener(func, name)
            return func

        return decorator

    # cogs

    async def add_cog(
        self,
        cog: Cog,
        /,
        *,
        override: bool = False,
        guild: Optional[Snowflake] = MISSING,
        guilds: Sequence[Snowflake] = MISSING,
    ) -> None:
        """|coro|

        Adds a "cog" to the bot.

        A cog is a class that has its own event listeners and commands.

        If the cog is a :class:`.app_commands.Group` then it is added to
        the bot's :class:`~bisim.app_commands.CommandTree` as well.

        Parameters
        -----------
        cog: :class:`.Cog`
            The cog to register to the bot.
        override: :class:`bool`
            If a previously loaded cog with the same name should be ejected
            instead of raising an error.
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            If the cog is an application command group, then this would be the
            guild where the cog group would be added to. If not given then
            it becomes a global command instead.
        guilds: List[:class:`~bisim.abc.Snowflake`]
            If the cog is an application command group, then this would be the
            guilds where the cog group would be added to. If not given then
            it becomes a global command instead. Cannot be mixed with
            ``guild``.

        Raises
        -------
        TypeError
            The cog does not inherit from :class:`.Cog`.
        CommandError
            An error happened during loading.
        ClientException
            A cog with the same name is already loaded.
        """

        if not isinstance(cog, Cog):
            raise TypeError('cogs must derive from Cog')

        cog_name = cog.__cog_name__
        existing = self.__cogs.get(cog_name)

        if existing is not None:
            if not override:
                raise bisim.ClientException(f'Cog named {cog_name!r} already loaded')
            await self.remove_cog(cog_name, guild=guild, guilds=guilds)

        cog = await cog._inject(self, override=override, guild=guild, guilds=guilds)  # type: ignore
        self.__cogs[cog_name] = cog

    def get_cog(self, name: str, /) -> Optional[Cog]:
        """Gets the cog instance requested.

        If the cog is not found, ``None`` is returned instead.

        Parameters
        -----------
        name: :class:`str`
            The name of the cog you are requesting.
            This is equivalent to the name passed via keyword
            argument in class creation or the class name if unspecified.

        Returns
        --------
        Optional[:class:`Cog`]
            The cog that was requested. If not found, returns ``None``.
        """
        return self.__cogs.get(name)

    async def remove_cog(
        self,
        name: str,
        /,
        *,
        guild: Optional[Snowflake] = MISSING,
        guilds: Sequence[Snowflake] = MISSING,
    ) -> Optional[Cog]:
        """|coro|

        Removes a cog from the bot and returns it.

        All registered commands and event listeners that the
        cog has registered will be removed as well.

        If no cog is found then this method has no effect.

        Parameters
        -----------
        name: :class:`str`
            The name of the cog to remove.
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            If the cog is an application command group, then this would be the
            guild where the cog group would be removed from.
        guilds: List[:class:`~bisim.abc.Snowflake`]
            If the cog is an application command group, then this would be the
            guilds where the cog group would be removed from.

        Returns
        -------
        Optional[:class:`.Cog`]
             The cog that was removed. ``None`` if not found.
        """

        cog = self.__cogs.pop(name, None)
        if cog is None:
            return None

        help_command = self._help_command
        if help_command and help_command.cog is cog:
            help_command.cog = None

        guild_ids = None
        if guild is not MISSING and guild is not None:
            guild_ids = [guild.id]
        elif guilds is not MISSING:
            guild_ids = [g.id for g in guilds]

        await cog._eject(self, guild_ids=guild_ids)  # type: ignore

        return cog

    @property
    def cogs(self) -> Mapping[str, Cog]:
        """Mapping[:class:`str`, :class:`Cog`]: A read-only mapping of cog name to cog."""
        return types.MappingProxyType(self.__cogs)

    # extensions

    async def _remove_module_references(self, name: str) -> None:
        for cogname, cog in self.__cogs.copy().items():
            if _is_submodule(name, cog.__module__):
                await self.remove_cog(cogname)

        for cmd in self.all_commands.copy().values():
            if cmd.module is not None and _is_submodule(name, cmd.module):
                if isinstance(cmd, GroupMixin):
                    cmd.recursively_remove_all_commands()
                self.remove_command(cmd.name)

        for event_list in self.extra_events.copy().values():
            remove = []
            for index, event in enumerate(event_list):
                if event.__module__ is not None and _is_submodule(name, event.__module__):
                    remove.append(index)

            for index in reversed(remove):
                del event_list[index]

        self.__tree._remove_with_module(name)

    async def _call_module_finalizers(self, lib: types.ModuleType, key: str) -> None:
        try:
            func = getattr(lib, 'teardown')
        except AttributeError:
            pass
        else:
            try:
                await maybe_coroutine(func, self)
            except Exception:
                pass
        finally:
            self.__extensions.pop(key, None)
            sys.modules.pop(key, None)
            name = lib.__name__
            for module in list(sys.modules.keys()):
                if _is_submodule(name, module):
                    del sys.modules[module]

    async def _load_from_module_spec(self, spec: importlib.machinery.ModuleSpec, key: str) -> None:
        # Load the module from the spec, keeping it out of sys.modules until setup succeeds.
        lib = importlib.util.module_from_spec(spec)
        sys.modules[key] = lib
        try:
            spec.loader.exec_module(lib)  # type: ignore
        except Exception as e:
            del sys.modules[key]
            raise errors.ExtensionFailed(key, e) from e

        try:
            setup = getattr(lib, 'setup')
        except AttributeError:
            del sys.modules[key]
            raise errors.NoEntryPointError(key)

        try:
            await maybe_coroutine(setup, self)
        except Exception as e:
            del sys.modules[key]
            await self._remove_module_references(lib.__name__)
            await self._call_module_finalizers(lib, key)
            raise errors.ExtensionFailed(key, e) from e
        else:
            self.__extensions[key] = lib

    def _resolve_name(self, name: str, package: Optional[str]) -> str:
        try:
            return importlib.util.resolve_name(name, package)
        except ImportError:
            raise errors.ExtensionNotFound(name)

    async def load_extension(self, name: str, *, package: Optional[str] = None) -> None:
        """|coro|

        Loads an extension.

        An extension is a python module that contains commands, cogs, or
        listeners.

        An extension must have a global function, ``setup`` defined as
        the entry point on what to do when the extension is loaded. This entry
        point must have a single argument, the ``bot``.

        Parameters
        ------------
        name: :class:`str`
            The extension name to load. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when loading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

        Raises
        --------
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionAlreadyLoaded
            The extension is already loaded.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension or its setup function had an execution error.
        """

        name = self._resolve_name(name, package)
        if name in self.__extensions:
            raise errors.ExtensionAlreadyLoaded(name)

        spec = importlib.util.find_spec(name)
        if spec is None:
            raise errors.ExtensionNotFound(name)

        await self._load_from_module_spec(spec, name)

    async def unload_extension(self, name: str, *, package: Optional[str] = None) -> None:
        """|coro|

        Unloads an extension.

        When the extension is unloaded, all commands, listeners, and cogs are
        removed from the bot and the module is un-imported.

        The extension can provide an optional global function, ``teardown``,
        to do miscellaneous clean-up if necessary. This function takes a single
        parameter, the ``bot``, similar to ``setup`` from
        :meth:`~.Bot.load_extension`.

        Parameters
        ------------
        name: :class:`str`
            The extension name to unload. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when unloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

        Raises
        -------
        ExtensionNotFound
            The name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionNotLoaded
            The extension was not loaded.
        """

        name = self._resolve_name(name, package)
        lib = self.__extensions.get(name)
        if lib is None:
            raise errors.ExtensionNotLoaded(name)

        await self._remove_module_references(lib.__name__)
        await self._call_module_finalizers(lib, name)

    async def reload_extension(self, name: str, *, package: Optional[str] = None) -> None:
        """|coro|

        Atomically reloads an extension.

        This replaces the extension with the same extension, only refreshed. This is
        equivalent to a :meth:`unload_extension` followed by a :meth:`load_extension`
        except done in an atomic way. That is, if an operation fails mid-reload then
        the bot will roll-back to the prior working state.

        Parameters
        ------------
        name: :class:`str`
            The extension name to reload. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when reloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

        Raises
        -------
        ExtensionNotLoaded
            The extension was not loaded.
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension setup function had an execution error.
        """

        name = self._resolve_name(name, package)
        lib = self.__extensions.get(name)
        if lib is None:
            raise errors.ExtensionNotLoaded(name)

        # Keep the old modules so a failed reload can put them back.
        modules = {name: module for name, module in sys.modules.items() if _is_submodule(lib.__name__, name)}

        try:
            await self._remove_module_references(lib.__name__)
            await self._call_module_finalizers(lib, name)
            await self.load_extension(name)
        except Exception:
            # Put the previous version back the way it was.
            await maybe_coroutine(lib.setup, self)  # type: ignore
            self.__extensions[name] = lib

            sys.modules.update(modules)
            raise

    @property
    def extensions(self) -> Mapping[str, types.ModuleType]:
        """Mapping[:class:`str`, :class:`py:types.ModuleType`]: A read-only mapping of extension name to extension."""
        return types.MappingProxyType(self.__extensions)

    # help command stuff

    @property
    def help_command(self) -> Optional[HelpCommand]:
        return self._help_command

    @help_command.setter
    def help_command(self, value: Optional[HelpCommand]) -> None:
        if value is not None:
            if not isinstance(value, HelpCommand):
                raise TypeError('help_command must be a subclass of HelpCommand')
            if self._help_command is not None:
                self._help_command._remove_from_bot(self)
            self._help_command = value
            value._add_to_bot(self)
        elif self._help_command is not None:
            self._help_command._remove_from_bot(self)
            self._help_command = None
        else:
            self._help_command = None

    # application command interop

    @property
    def tree(self) -> app_commands.CommandTree[Self]:  # type: ignore
        """:class:`~bisim.app_commands.CommandTree`: The command tree responsible for handling the application commands
        in this bot.
        """
        return self.__tree

    # command processing

    async def get_prefix(self, message: Message, /) -> Union[List[str], str]:
        """|coro|

        Retrieves the prefix the bot is listening to
        with the message as a context.

        Parameters
        -----------
        message: :class:`bisim.Message`
            The message context to get the prefix of.

        Returns
        --------
        Union[List[:class:`str`], :class:`str`]
            A list of prefixes or a single prefix that the bot is
            listening for.
        """
        prefix = ret = self.command_prefix

        if callable(prefix):
            ret = await maybe_coroutine(prefix, self, message)

        if not isinstance(ret, str):
            try:
                ret = list(ret)
            except TypeError:
                # A generator that failed must keep its own error.
                if isinstance(ret, collections.abc.Iterable):
                    raise

                raise TypeError(
                    'command_prefix must be plain string, iterable of strings, or callable '
                    f'returning either of these, not {ret.__class__.__name__}'
                )

            if not ret:
                raise ValueError('Iterable command_prefix must contain at least one prefix')

        return ret

    async def get_context(self, origin: Union[Message, Any], /, *, cls: Type[Any] = MISSING) -> Any:
        r"""|coro|

        Returns the invocation context from the message or interaction.

        This is a more low-level counter-part for :meth:`.process_commands`
        to allow users more fine grained control over the processing.

        The returned context is not guaranteed to be a valid invocation
        context, :attr:`.Context.valid` must be checked to make sure it is.
        If the context is not valid then it is not a valid candidate to be
        invoked under :meth:`~.Bot.invoke`.

        Parameters
        -----------
        origin: Union[:class:`bisim.Message`, :class:`bisim.Interaction`]
            The message or interaction to get the invocation context from.
        cls
            The factory class that will be used to create the context.
            By default, this is :class:`.Context`. Should a custom
            class be provided, it must be similar enough to :class:`.Context`\'s
            interface.

        Returns
        --------
        :class:`.Context`
            The invocation context. The type of this can change via the
            ``cls`` parameter.
        """
        if cls is MISSING:
            cls = Context

        if isinstance(origin, bisim.Interaction):
            return await cls.from_interaction(origin)

        view = StringView(origin.content)
        ctx = cls(prefix=None, view=view, bot=self, message=origin)

        if origin.author.id == self.user.id:  # type: ignore
            return ctx

        prefix = await self.get_prefix(origin)
        invoked_prefix = prefix

        if isinstance(prefix, str):
            if not view.skip_string(prefix):
                return ctx
        else:
            try:
                if origin.content.startswith(tuple(prefix)):
                    invoked_prefix = utils.find(view.skip_string, prefix)
                else:
                    return ctx

            except TypeError:
                if not isinstance(prefix, list):
                    raise TypeError(
                        'get_prefix must return either a string or a list of string, ' f'not {prefix.__class__.__name__}'
                    )

                for value in prefix:
                    if not isinstance(value, str):
                        raise TypeError(
                            'Iterable command_prefix or list returned from get_prefix must '
                            f'contain only strings, not {value.__class__.__name__}'
                        )

                raise

        if self.strip_after_prefix:
            view.skip_ws()

        invoker = view.get_word()
        ctx.invoked_with = invoker
        ctx.prefix = invoked_prefix
        ctx.command = self.all_commands.get(invoker)
        return ctx

    async def invoke(self, ctx: Context[Any], /) -> None:
        """|coro|

        Invokes the command given under the invocation context and
        handles all the internal event dispatch mechanisms.

        Parameters
        -----------
        ctx: :class:`.Context`
            The invocation context to invoke.
        """
        if ctx.command is not None:
            self.dispatch('command', ctx)
            try:
                if await self.can_run(ctx, call_once=True):
                    await ctx.command.invoke(ctx)
                else:
                    raise errors.CheckFailure('The global check once functions failed.')
            except errors.CommandError as exc:
                await ctx.command.dispatch_error(ctx, exc)
            else:
                self.dispatch('command_completion', ctx)
        elif ctx.invoked_with:
            exc = errors.CommandNotFound(f'Command "{ctx.invoked_with}" is not found')
            self.dispatch('command_error', ctx, exc)

    async def process_commands(self, message: Message, /) -> None:
        """|coro|

        This function processes the commands that have been registered
        to the bot and other groups. Without this coroutine, none of the
        commands will be triggered.

        By default, this coroutine is called inside the :func:`.on_message`
        event. If you choose to override the :func:`.on_message` event, then
        you should invoke this coroutine as well.

        This is built using other low level tools, and is equivalent to a
        call to :meth:`~.Bot.get_context` followed by a call to :meth:`~.Bot.invoke`.

        This also checks if the message's author is a bot and doesn't
        call :meth:`~.Bot.get_context` or :meth:`~.Bot.invoke` if so.

        Parameters
        -----------
        message: :class:`bisim.Message`
            The message to process commands for.
        """
        if message.author.bot:
            return

        ctx = await self.get_context(message)
        await self.invoke(ctx)

    async def on_message(self, message: Message, /) -> None:
        await self.process_commands(message)


Collection = collections.abc.Collection


class Bot(BotBase, bisim.Client):
    """Represents a Bisim bot.

    This class is a subclass of :class:`bisim.Client` and as a result
    anything that you can do with a :class:`bisim.Client` you can do with
    this bot.

    This class also subclasses :class:`.GroupMixin` to provide the functionality
    to manage commands.

    Unlike :class:`bisim.Client`, this class does not require manually setting
    a :class:`~bisim.app_commands.CommandTree` and is automatically set upon
    instantiating the class.

    .. container:: operations

        .. describe:: async with x

            Asynchronously initialises the bot and automatically cleans up.

    Attributes
    -----------
    command_prefix
        The command prefix is what the message content must contain initially
        to have a command invoked. This prefix could either be a string to
        indicate what the prefix should be, or a callable that takes in the bot
        as its first parameter and :class:`bisim.Message` as its second
        parameter and returns the prefix. This is to facilitate "dynamic"
        command prefixes. This callable can be either a regular function or
        a coroutine.

        An empty string as the prefix always matches, enabling prefix-less
        command invocation. While this may be useful in DMs it should be avoided
        in servers, as it's likely to cause performance issues and unintended
        command invocations.

        The command prefix could also be an iterable of strings indicating that
        multiple checks for the prefix should be used and the first one to
        match will be the invocation prefix. You can get this prefix via
        :attr:`.Context.prefix`.
    case_insensitive: :class:`bool`
        Whether the commands should be case insensitive. Defaults to ``False``. This
        attribute does not carry over to groups. You must set it to every group if
        you require group commands to be case insensitive as well.
    description: :class:`str`
        The content prefixed into the default help message.
    help_command: Optional[:class:`.HelpCommand`]
        The help command implementation to use. This can be dynamically
        set at runtime. To remove the help command pass ``None``. For more
        information on implementing a help command, see :ref:`ext_commands_help_command`.
    owner_id: Optional[:class:`int`]
        The user ID that owns the bot. If this is not set and is then queried via
        :meth:`.is_owner` then it is fetched automatically using
        :meth:`~.Bot.application_info`.
    owner_ids: Optional[Collection[:class:`int`]]
        The user IDs that owns the bot. This is similar to :attr:`owner_id`.
        If this is not set and the application is team based, then it is
        fetched automatically using :meth:`~.Bot.application_info`.
        For performance reasons it is recommended to use a :class:`set`
        for the collection. You cannot set both ``owner_id`` and ``owner_ids``.
    strip_after_prefix: :class:`bool`
        Whether to strip whitespace characters after encountering the command
        prefix. This allows for ``!   hello`` and ``!hello`` to both work if
        the ``command_prefix`` is set to ``!``. Defaults to ``False``.
    tree_cls: Type[:class:`~bisim.app_commands.CommandTree`]
        The type of application command tree to use. Defaults to :class:`~bisim.app_commands.CommandTree`.
    allowed_contexts: :class:`~bisim.app_commands.AppCommandContext`
        The default allowed contexts that applies to all application commands
        in the application command tree.
    allowed_installs: :class:`~bisim.app_commands.AppInstallationType`
        Accepted for compatibility.
    """

    pass


class AutoShardedBot(Bot):
    """Kept for compatibility: Bisim has no sharding, so this is a :class:`Bot`."""

    pass

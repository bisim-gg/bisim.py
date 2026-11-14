from __future__ import annotations

import asyncio
import inspect
import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Dict,
    Generator,
    Generic,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
    overload,
)

from .. import utils
from ..enums import AppCommandType, InteractionType
from ..errors import ClientException, HTTPException
from ..flags import AppCommandContext, AppInstallationType
from ..member import Member
from ..message import Message
from ..object import Object
from ..user import User
from ..utils import MISSING, _get_as_snowflake
from .commands import Command, ContextMenu, Group, _shorten
from .errors import (
    AppCommandError,
    CommandAlreadyRegistered,
    CommandInvokeError,
    CommandLimitReached,
    CommandNotFound,
    CommandSignatureMismatch,
    CommandSyncFailure,
    MissingApplicationID,
)
from .models import AppCommand
from .namespace import Namespace, ResolveKey
from .translator import Translator, locale_str

if TYPE_CHECKING:
    from ..abc import Snowflake
    from ..client import Client
    from ..interactions import Interaction
    from .commands import AutocompleteCallback, CommandCallback, ContextMenuCallback

    ErrorFunc = Callable[['Interaction[Any]', AppCommandError], Coroutine[Any, Any, Any]]

__all__ = ('CommandTree',)

ClientT = TypeVar('ClientT', bound='Client')

_log = logging.getLogger(__name__)


def _retrieve_guild_ids(
    command: Any, guild: Optional[Snowflake] = MISSING, guilds: Sequence[Snowflake] = MISSING
) -> Optional[Set[int]]:
    if guild is not MISSING and guilds is not MISSING:
        raise TypeError('cannot mix guild and guilds keyword arguments')

    if guild is MISSING:
        if guilds is MISSING:
            return getattr(command, '_guild_ids', None)

        if len(guilds) == 0:
            return None

        return {g.id for g in guilds}

    if guild is None:
        return None
    return {guild.id}


def _option_type_number(option: Dict[str, Any]) -> int:
    from ..enums import AppCommandOptionType

    kind = AppCommandOptionType.from_bisim(option.get('type'))
    return int(getattr(kind, 'value', 0))


class CommandTree(Generic[ClientT]):
    """Represents a container that holds application command information.

    Parameters
    -----------
    client: :class:`~bisim.Client`
        The client instance to get application command information from.
    fallback_to_global: :class:`bool`
        If a guild-specific command is not found when invoked, then try falling back into
        a global command in the tree. For example, if the tree locally has a ``/ping`` command
        under the global namespace but the guild has a guild-specific ``/ping``, instead of failing
        to find the guild-specific ``/ping`` command it will fall back to the global ``/ping`` command.
        This has the potential to raise more :exc:`~bisim.app_commands.CommandSignatureMismatch` errors
        than usual. Defaults to ``True``.
    allowed_contexts: :class:`~bisim.app_commands.AppCommandContext`
        The default allowed contexts that applies to all commands in this tree.
        Note that you can override this on a per command basis.
    allowed_installs: :class:`~bisim.app_commands.AppInstallationType`
        Accepted for compatibility.
    """

    def __init__(
        self,
        client: ClientT,
        *,
        fallback_to_global: bool = True,
        allowed_contexts: AppCommandContext = MISSING,
        allowed_installs: AppInstallationType = MISSING,
    ):
        self.client: ClientT = client
        self._http = client.http
        self._state = client._connection

        if self._state._command_tree is not None:
            raise ClientException('This client already has an associated command tree.')

        self._state._command_tree = self
        self.fallback_to_global: bool = fallback_to_global
        self.allowed_contexts = AppCommandContext() if allowed_contexts is MISSING else allowed_contexts
        self.allowed_installs = AppInstallationType() if allowed_installs is MISSING else allowed_installs
        self._guild_commands: Dict[int, Dict[str, Union[Command[Any, ..., Any], Group]]] = {}
        self._global_commands: Dict[str, Union[Command[Any, ..., Any], Group]] = {}
        self._context_menus: Dict[Tuple[str, Optional[int], int], ContextMenu] = {}

    async def fetch_command(self, command_id: int, /, *, guild: Optional[Snowflake] = None) -> AppCommand:
        """|coro|

        Fetches an application command from the application.

        Parameters
        -----------
        command_id: :class:`int`
            The ID of the command to fetch.
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to fetch the command from. If not passed then the global command
            is fetched instead.

        Raises
        -------
        HTTPException
            Fetching the command failed.
        MissingApplicationID
            The application ID could not be found.
        NotFound
            The application command was not found.

        Returns
        --------
        :class:`~bisim.app_commands.AppCommand`
            The application command.
        """
        if self.client.application_id is None:
            raise MissingApplicationID

        if guild is None:
            command = await self._http.get_global_command(self.client.application_id, command_id)
        else:
            command = await self._http.get_guild_command(self.client.application_id, guild.id, command_id)

        return AppCommand(data=command, state=self._state)

    async def fetch_commands(self, *, guild: Optional[Snowflake] = None) -> List[AppCommand]:
        """|coro|

        Fetches the application's current commands.

        If no guild is passed then global commands are fetched, otherwise
        the guild's commands are fetched instead.

        .. note::

            This includes context menu commands.

        Parameters
        -----------
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to fetch the commands from. If not passed then global commands
            are fetched instead.

        Raises
        -------
        HTTPException
            Fetching the commands failed.
        MissingApplicationID
            The application ID could not be found.

        Returns
        --------
        List[:class:`~bisim.app_commands.AppCommand`]
            The application's commands.
        """
        if self.client.application_id is None:
            raise MissingApplicationID

        if guild is None:
            commands = await self._http.get_global_commands(self.client.application_id)
        else:
            commands = await self._http.get_guild_commands(self.client.application_id, guild.id)

        rows = commands.get('commands') if isinstance(commands, dict) else commands
        return [AppCommand(data=data, state=self._state) for data in rows or []]

    def copy_global_to(self, *, guild: Snowflake) -> None:
        """Copies all global commands to the specified guild.

        This method is mainly available for development purposes, as it allows you
        to copy your global commands over to a testing guild easily.

        Note that this method will *override* pre-existing guild commands that would conflict.

        Parameters
        -----------
        guild: :class:`~bisim.abc.Snowflake`
            The guild to copy the commands to.

        Raises
        --------
        CommandLimitReached
            The maximum number of commands was reached for that guild.
            This is currently 100 for slash commands and 5 for context menu commands.
        """
        try:
            mapping = self._guild_commands[guild.id].copy()
        except KeyError:
            mapping = {}

        mapping.update(self._global_commands)
        if len(mapping) > 100:
            raise CommandLimitReached(guild_id=guild.id, limit=100)

        ctx_menu: Dict[Tuple[str, Optional[int], int], ContextMenu] = {
            (name, guild.id, cmd_type): cmd
            for ((name, g, cmd_type), cmd) in self._context_menus.items()
            if g is None or g == guild.id
        }

        for cmd_type, count in _count_context_menus(ctx_menu).items():
            if count > 5:
                raise CommandLimitReached(guild_id=guild.id, limit=5, type=AppCommandType(cmd_type))

        self._context_menus.update(ctx_menu)
        self._guild_commands[guild.id] = mapping

    def add_command(
        self,
        command: Union[Command[Any, ..., Any], ContextMenu, Group],
        /,
        *,
        guild: Optional[Snowflake] = MISSING,
        guilds: Sequence[Snowflake] = MISSING,
        override: bool = False,
    ) -> None:
        """Adds an application command to the tree.

        This only adds the command locally -- in order to sync the commands
        and enable them in the client, :meth:`sync` must be called.

        The root parent of the command is added regardless of the type passed.

        Parameters
        -----------
        command: Union[:class:`Command`, :class:`Group`]
            The application command or group to add.
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to add the command to. If not given or ``None`` then it
            becomes a global command instead.
        guilds: List[:class:`~bisim.abc.Snowflake`]
            The list of guilds to add the command to. This cannot be mixed
            with the ``guild`` parameter. If no guilds are given at all
            then it becomes a global command instead.
        override: :class:`bool`
            Whether to override a command with the same name. If ``False``
            an exception is raised. Default is ``False``.

        Raises
        --------
        ~bisim.app_commands.CommandAlreadyRegistered
            The command was already registered and no override was specified.
        TypeError
            The application command passed is not a valid application command.
            Or, ``guild`` and ``guilds`` were both given.
        CommandLimitReached
            The maximum number of commands was reached globally or for that guild.
            This is currently 100 for slash commands and 5 for context menu commands.
        """

        guild_ids = _retrieve_guild_ids(command, guild, guilds)
        if isinstance(command, ContextMenu):
            type = command.type.value
            name = command.name

            def _context_menu_add_helper(
                guild_id: Optional[int],
                data: Dict[Tuple[str, Optional[int], int], ContextMenu],
                name: str = name,
                type: int = type,
            ) -> None:
                key = (name, guild_id, type)
                found = key in self._context_menus
                if found and not override:
                    raise CommandAlreadyRegistered(name, guild_id)

                total = sum(1 for _, g, t in self._context_menus if g == guild_id and t == type)
                if total + found > 5:
                    raise CommandLimitReached(guild_id=guild_id, limit=5, type=AppCommandType(type))
                data[key] = command

            if guild_ids is None:
                _context_menu_add_helper(None, self._context_menus)
            else:
                current: Dict[Tuple[str, Optional[int], int], ContextMenu] = {}
                for guild_id in guild_ids:
                    _context_menu_add_helper(guild_id, current)

                self._context_menus.update(current)
            return
        elif not isinstance(command, (Command, Group)):
            raise TypeError(f'Expected an application command, received {command.__class__.__name__} instead')


        root = command.root_parent or command
        name = root.name
        if guild_ids is not None:
            for guild_id in guild_ids:
                commands = self._guild_commands.get(guild_id, {})
                found = name in commands
                if found and not override:
                    raise CommandAlreadyRegistered(name, guild_id)

                to_add = not (override and found)
                if len(commands) + to_add > 100:
                    raise CommandLimitReached(guild_id=guild_id, limit=100)

            for guild_id in guild_ids:
                commands = self._guild_commands.setdefault(guild_id, {})
                commands[name] = root
        else:
            found = name in self._global_commands
            if found and not override:
                raise CommandAlreadyRegistered(name, None)

            to_add = not (override and found)
            if len(self._global_commands) + to_add > 100:
                raise CommandLimitReached(guild_id=None, limit=100)
            self._global_commands[name] = root

    def remove_command(
        self,
        command: str,
        /,
        *,
        guild: Optional[Snowflake] = None,
        type: AppCommandType = AppCommandType.chat_input,
    ) -> Optional[Union[Command[Any, ..., Any], ContextMenu, Group]]:
        """Removes an application command from the tree.

        This only removes the command locally -- in order to sync the commands
        and remove them in the client, :meth:`sync` must be called.

        Parameters
        -----------
        command: :class:`str`
            The name of the root command to remove.
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to remove the command from. If not given or ``None`` then it
            removes a global command instead.
        type: :class:`~bisim.AppCommandType`
            The type of command to remove. Defaults to :attr:`~bisim.AppCommandType.chat_input`,
            i.e. slash commands.

        Returns
        ---------
        Optional[Union[:class:`Command`, :class:`ContextMenu`, :class:`Group`]]
            The application command that got removed.
            If nothing was removed then ``None`` is returned instead.
        """

        if type is AppCommandType.chat_input:
            if guild is None:
                return self._global_commands.pop(command, None)
            else:
                try:
                    commands = self._guild_commands[guild.id]
                except KeyError:
                    return None
                else:
                    return commands.pop(command, None)
        elif type in (AppCommandType.user, AppCommandType.message):
            guild_id = None if guild is None else guild.id
            key = (command, guild_id, type.value)
            return self._context_menus.pop(key, None)
        return None

    def clear_commands(self, *, guild: Optional[Snowflake], type: Optional[AppCommandType] = None) -> None:
        """Clears all application commands from the tree.

        This only removes the commands locally -- in order to sync the commands
        and remove them in the client, :meth:`sync` must be called.

        Parameters
        -----------
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to remove the commands from. If ``None`` then it
            removes all global commands instead.
        type: :class:`~bisim.AppCommandType`
            The type of command to clear. If not given or ``None`` then it removes all commands
            regardless of the type.
        """

        if type is None or type is AppCommandType.chat_input:
            if guild is None:
                self._global_commands.clear()
            else:
                try:
                    commands = self._guild_commands[guild.id]
                except KeyError:
                    pass
                else:
                    commands.clear()

        guild_id = None if guild is None else guild.id
        if type is None:
            self._context_menus = {
                (name, _guild_id, value): cmd
                for (name, _guild_id, value), cmd in self._context_menus.items()
                if _guild_id != guild_id
            }
        elif type in (AppCommandType.user, AppCommandType.message):
            self._context_menus = {
                (name, _guild_id, value): cmd
                for (name, _guild_id, value), cmd in self._context_menus.items()
                if _guild_id != guild_id or value != type.value
            }

    def get_command(
        self,
        command: str,
        /,
        *,
        guild: Optional[Snowflake] = None,
        type: AppCommandType = AppCommandType.chat_input,
    ) -> Optional[Union[Command[Any, ..., Any], ContextMenu, Group]]:
        """Gets an application command from the tree.

        Parameters
        -----------
        command: :class:`str`
            The name of the root command to get.
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to get the command from. If not given or ``None`` then it
            gets a global command instead.
        type: :class:`~bisim.AppCommandType`
            The type of command to get. Defaults to :attr:`~bisim.AppCommandType.chat_input`,
            i.e. slash commands.

        Returns
        ---------
        Optional[Union[:class:`Command`, :class:`ContextMenu`, :class:`Group`]]
            The application command that was found.
            If nothing was found then ``None`` is returned instead.
        """

        if type is AppCommandType.chat_input:
            if guild is None:
                return self._global_commands.get(command)
            else:
                try:
                    commands = self._guild_commands[guild.id]
                except KeyError:
                    return None
                else:
                    return commands.get(command)
        elif type in (AppCommandType.user, AppCommandType.message):
            guild_id = None if guild is None else guild.id
            key = (command, guild_id, type.value)
            return self._context_menus.get(key)
        return None

    def get_commands(
        self,
        *,
        guild: Optional[Snowflake] = None,
        type: Optional[AppCommandType] = None,
    ) -> List[Union[ContextMenu, Command[Any, ..., Any], Group]]:
        """Gets all application commands from the tree.

        Parameters
        -----------
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to get the commands from, not including global commands.
            If not given or ``None`` then only global commands are returned.
        type: Optional[:class:`~bisim.AppCommandType`]
            The type of commands to get. When not given or ``None``, then all
            command types are returned.

        Returns
        ---------
        List[Union[:class:`ContextMenu`, :class:`Command`, :class:`Group`]]
            The application commands from the tree.
        """
        if type is None:
            return self._get_all_commands(guild=guild)

        if type is AppCommandType.chat_input:
            if guild is None:
                return list(self._global_commands.values())
            else:
                try:
                    commands = self._guild_commands[guild.id]
                except KeyError:
                    return []
                else:
                    return list(commands.values())
        else:
            guild_id = None if guild is None else guild.id
            value = type.value
            return [command for ((_, g, t), command) in self._context_menus.items() if g == guild_id and t == value]

    def walk_commands(
        self,
        *,
        guild: Optional[Snowflake] = None,
        type: AppCommandType = AppCommandType.chat_input,
    ) -> Generator[Union[Command[Any, ..., Any], Group, ContextMenu], None, None]:
        """An iterator that recursively walks through all application commands and child commands from the tree.

        Parameters
        -----------
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to iterate the commands from, not including global commands.
            If not given or ``None`` then only global commands are iterated.
        type: :class:`~bisim.AppCommandType`
            The type of commands to iterate over. Defaults to :attr:`~bisim.AppCommandType.chat_input`,
            i.e. slash commands.

        Yields
        ---------
        Union[:class:`ContextMenu`, :class:`Command`, :class:`Group`]
            The application commands from the tree.
        """

        if type is AppCommandType.chat_input:
            if guild is None:
                for cmd in self._global_commands.values():
                    yield cmd
                    if isinstance(cmd, Group):
                        yield from cmd.walk_commands()
            else:
                try:
                    commands = self._guild_commands[guild.id]
                except KeyError:
                    return
                else:
                    for cmd in commands.values():
                        yield cmd
                        if isinstance(cmd, Group):
                            yield from cmd.walk_commands()
        else:
            guild_id = None if guild is None else guild.id
            value = type.value
            for (_, g, t), command in self._context_menus.items():
                if g == guild_id and t == value:
                    yield command

    def _get_all_commands(self, *, guild: Optional[Snowflake] = None) -> List[Union[ContextMenu, Command[Any, ..., Any], Group]]:
        if guild is None:
            base: List[Union[ContextMenu, Command[Any, ..., Any], Group]] = list(self._global_commands.values())
            base.extend(cmd for ((_, g, _), cmd) in self._context_menus.items() if g is None)
            return base
        else:
            try:
                commands = self._guild_commands[guild.id]
            except KeyError:
                guild_id = guild.id
                return [cmd for ((_, g, _), cmd) in self._context_menus.items() if g == guild_id]
            else:
                base = list(commands.values())
                guild_id = guild.id
                base.extend(cmd for ((_, g, _), cmd) in self._context_menus.items() if g == guild_id)
                return base

    def _remove_with_module(self, name: str) -> None:
        remove: List[Any] = []
        for key, cmd in self._context_menus.items():
            if cmd.module is not None and _is_submodule(name, cmd.module):
                remove.append(key)

        for key in remove:
            del self._context_menus[key]

        remove = []
        for key, cmd in self._global_commands.items():
            if cmd.module is not None and _is_submodule(name, cmd.module):
                remove.append(key)

        for key in remove:
            del self._global_commands[key]

        for mapping in self._guild_commands.values():
            remove = []
            for key, cmd in mapping.items():
                if cmd.module is not None and _is_submodule(name, cmd.module):
                    remove.append(key)

            for key in remove:
                del mapping[key]

    async def on_error(self, interaction: Interaction[ClientT], error: AppCommandError, /) -> None:
        """|coro|

        A callback that is called when any command raises an :exc:`AppCommandError`.

        The default implementation logs the exception using the library logger
        if the command does not have any error handlers attached to it.

        To get the command that failed, :attr:`bisim.Interaction.command` should
        be used.

        Parameters
        -----------
        interaction: :class:`~bisim.Interaction`
            The interaction that is being handled.
        error: :exc:`AppCommandError`
            The exception that was raised.
        """

        command = interaction.command
        if command is not None:
            if command._has_any_error_handlers():
                return

            _log.error('Ignoring exception in command %r', command.name, exc_info=error)
        else:
            _log.error('Ignoring exception in command tree', exc_info=error)

    def error(self, coro: ErrorFunc) -> ErrorFunc:
        """A decorator that registers a coroutine as a local error handler.

        This must match the signature of the :meth:`on_error` callback.

        The error passed will be derived from :exc:`AppCommandError`.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the local error handler.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine or does
            not match the signature.
        """

        if not inspect.iscoroutinefunction(coro):
            raise TypeError('The error handler must be a coroutine.')

        params = inspect.signature(coro).parameters
        if len(params) != 2:
            raise TypeError('error handler must have 2 parameters')

        self.on_error = coro  # type: ignore
        return coro

    def command(
        self,
        *,
        name: Union[str, locale_str] = MISSING,
        description: Union[str, locale_str] = MISSING,
        nsfw: bool = False,
        guild: Optional[Snowflake] = MISSING,
        guilds: Sequence[Snowflake] = MISSING,
        auto_locale_strings: bool = True,
        extras: Dict[Any, Any] = MISSING,
    ) -> Callable[[CommandCallback], Command[Any, ..., Any]]:
        """A decorator that creates an application command from a regular function directly under this tree.

        Parameters
        ------------
        name: Union[:class:`str`, :class:`locale_str`]
            The name of the application command. If not given, it defaults to a lower-case
            version of the callback name.
        description: Union[:class:`str`, :class:`locale_str`]
            The description of the application command. This shows up in the UI to describe
            the application command. If not given, it defaults to the first line of the docstring
            of the callback shortened to 100 characters.
        nsfw: :class:`bool`
            Whether the command is NSFW and should only work in NSFW channels. Defaults to ``False``.
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to add the command to. If not given or ``None`` then it
            becomes a global command instead.
        guilds: List[:class:`~bisim.abc.Snowflake`]
            The list of guilds to add the command to. This cannot be mixed
            with the ``guild`` parameter. If no guilds are given at all
            then it becomes a global command instead.
        auto_locale_strings: :class:`bool`
            If this is set to ``True``, then all translatable strings will implicitly
            be wrapped into :class:`locale_str` rather than :class:`str`.
        extras: :class:`dict`
            A dictionary that can be used to store extraneous data.
            The library will not touch any values or keys within this dictionary.
        """

        def decorator(func: CommandCallback) -> Command[Any, ..., Any]:
            if not inspect.iscoroutinefunction(func):
                raise TypeError('command function must be a coroutine function')

            if description is MISSING:
                if func.__doc__ is None:
                    desc = '…'
                else:
                    desc = _shorten(func.__doc__)
            else:
                desc = description

            command = Command(
                name=name if name is not MISSING else func.__name__,
                description=desc,
                callback=func,
                nsfw=nsfw,
                parent=None,
                auto_locale_strings=auto_locale_strings,
                extras=extras,
            )
            self.add_command(command, guild=guild, guilds=guilds)
            return command

        return decorator

    def context_menu(
        self,
        *,
        name: Union[str, locale_str] = MISSING,
        nsfw: bool = False,
        guild: Optional[Snowflake] = MISSING,
        guilds: Sequence[Snowflake] = MISSING,
        auto_locale_strings: bool = True,
        extras: Dict[Any, Any] = MISSING,
    ) -> Callable[[ContextMenuCallback], ContextMenu]:
        """A decorator that creates an application command context menu from a regular function directly under this tree.

        This function must have a signature of :class:`~bisim.Interaction` as its first parameter
        and taking either a :class:`~bisim.Member`, :class:`~bisim.User`, or :class:`~bisim.Message`,
        or a :obj:`typing.Union` of ``Member`` and ``User`` as its second parameter.

        Examples
        ---------

        .. code-block:: python3

            @app_commands.context_menu()
            async def react(interaction: bisim.Interaction, message: bisim.Message):
                await interaction.response.send_message('Very cool message!', ephemeral=True)

            @app_commands.context_menu()
            async def ban(interaction: bisim.Interaction, user: bisim.Member):
                await interaction.response.send_message(f'Should I actually ban {user}...', ephemeral=True)

        Parameters
        ------------
        name: Union[:class:`str`, :class:`locale_str`]
            The name of the context menu command. If not given, it defaults to a title-case
            version of the callback name. Note that unlike regular slash commands this can
            have spaces and upper case characters in the name.
        nsfw: :class:`bool`
            Whether the command is NSFW and should only work in NSFW channels. Defaults to ``False``.
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to add the command to. If not given or ``None`` then it
            becomes a global command instead.
        guilds: List[:class:`~bisim.abc.Snowflake`]
            The list of guilds to add the command to. This cannot be mixed
            with the ``guild`` parameter. If no guilds are given at all
            then it becomes a global command instead.
        auto_locale_strings: :class:`bool`
            If this is set to ``True``, then all translatable strings will implicitly
            be wrapped into :class:`locale_str` rather than :class:`str`.
        extras: :class:`dict`
            A dictionary that can be used to store extraneous data.
            The library will not touch any values or keys within this dictionary.
        """

        def decorator(func: ContextMenuCallback) -> ContextMenu:
            if not inspect.iscoroutinefunction(func):
                raise TypeError('context menu function must be a coroutine function')

            actual_name = func.__name__.title() if name is MISSING else name
            context_menu = ContextMenu(
                name=actual_name,
                nsfw=nsfw,
                callback=func,
                auto_locale_strings=auto_locale_strings,
                extras=extras,
            )
            self.add_command(context_menu, guild=guild, guilds=guilds)
            return context_menu

        return decorator

    @property
    def translator(self) -> Optional[Translator]:
        """Optional[:class:`Translator`]: The translator, if any, responsible for handling translation of commands.

        To change the translator, use :meth:`set_translator`.
        """
        return self._state._translator

    async def set_translator(self, translator: Optional[Translator]) -> None:
        """|coro|

        Sets the translator to use for translating commands.

        If a translator was previously set, it will be unloaded using its
        :meth:`Translator.unload` method.

        When a translator is set, it will be loaded using its :meth:`Translator.load` method.

        Parameters
        ------------
        translator: Optional[:class:`Translator`]
            The translator to use. If ``None`` then the translator is just removed and unloaded.

        Raises
        -------
        TypeError
            The translator was not ``None`` or a :class:`Translator` instance.
        """

        if translator is not None and not isinstance(translator, Translator):
            raise TypeError(f'expected None or Translator instance, received {translator.__class__.__name__} instead')

        old_translator = self._state._translator
        if old_translator is not None:
            await old_translator.unload()

        if translator is None:
            self._state._translator = None
        else:
            await translator.load()
            self._state._translator = translator

    async def sync(self, *, guild: Optional[Snowflake] = None) -> List[AppCommand]:
        """|coro|

        Syncs the application commands to Bisim.

        This also runs the translator to get the translated strings necessary for
        feeding back into Bisim.

        This must be called for the application commands to show up. Bisim
        replaces the whole set of commands in one request (global, or one
        server's).

        Parameters
        -----------
        guild: Optional[:class:`~bisim.abc.Snowflake`]
            The guild to sync the commands to. If ``None`` then it
            syncs all global commands instead.

        Raises
        -------
        HTTPException
            Syncing the commands failed.
        CommandSyncFailure
            Syncing the commands failed due to a user related error, typically because
            the command has invalid data. This is equivalent to an HTTP status code of
            400.
        Forbidden
            The client does not have the bot scope in the guild.
        MissingApplicationID
            The client does not have an application ID.
        TranslationError
            An error occurred while translating the commands.

        Returns
        --------
        List[:class:`AppCommand`]
            The application's commands that got synced.
        """

        if self.client.application_id is None:
            raise MissingApplicationID

        commands = self._get_all_commands(guild=guild)

        translator = self.translator
        if translator:
            payload = [await command.get_translated_payload(self, translator) for command in commands]
        else:
            payload = [command.to_dict(self) for command in commands]

        try:
            if guild is None:
                data = await self._http.bulk_upsert_global_commands(self.client.application_id, payload=payload)
            else:
                data = await self._http.bulk_upsert_guild_commands(self.client.application_id, guild.id, payload=payload)
        except HTTPException as e:
            if e.status == 400:
                raise CommandSyncFailure(e, commands) from None
            raise

        rows = data.get('commands') if isinstance(data, dict) else data
        return [AppCommand(data=d, state=self._state) for d in rows or []]

    async def _dispatch_error(self, interaction: Interaction[ClientT], error: AppCommandError, /) -> None:
        command = interaction.command
        interaction.command_failed = True
        try:
            if isinstance(command, Command):
                await command._invoke_error_handlers(interaction, error)
            elif isinstance(command, ContextMenu) and command.on_error is not None:
                await command.on_error(interaction, error)
        finally:
            await self.on_error(interaction, error)

    def _from_interaction(self, interaction: Interaction[ClientT]) -> None:
        async def wrapper() -> None:
            try:
                await self._call(interaction)
            except AppCommandError as e:
                await self._dispatch_error(interaction, e)

        self.client._schedule_event(wrapper, 'app_commands')  # type: ignore

    def _get_context_menu(self, data: Dict[str, Any], guild_id: Optional[int] = None) -> Optional[ContextMenu]:
        name = data['name']
        type = AppCommandType.from_bisim(data.get('type')).value
        command_guild = guild_id if guild_id is not None else _get_as_snowflake(data, 'guildId')
        if command_guild is not None:
            found = self._context_menus.get((name, command_guild, type))
            if found is not None or not self.fallback_to_global:
                return found
        return self._context_menus.get((name, None, type))

    def _get_app_command_options(
        self, data: Dict[str, Any], guild_id: Optional[int] = None
    ) -> Tuple[Union[Command[Any, ..., Any], Group], List[Dict[str, Any]]]:
        parents: List[str] = []
        name = data['name']

        command_guild_id = guild_id if guild_id is not None else _get_as_snowflake(data, 'guildId')
        command: Optional[Union[Command[Any, ..., Any], Group]] = None
        if command_guild_id:
            try:
                guild_commands = self._guild_commands[command_guild_id]
            except KeyError:
                command = None if not self.fallback_to_global else self._global_commands.get(name)
            else:
                command = guild_commands.get(name)
                if command is None and self.fallback_to_global:
                    command = self._global_commands.get(name)
        else:
            command = self._global_commands.get(name)

        if command is None:
            raise CommandNotFound(name, parents)

        searching = True
        options: List[Dict[str, Any]] = data.get('options', []) or []
        while searching:
            for option in options:
                if _option_type_number(option) in (1, 2):
                    parents.append(name)
                    name = option['name']
                    command = command._get_internal_command(name)  # type: ignore
                    if command is None:
                        raise CommandNotFound(name, parents)
                    options = option.get('options', []) or []
                    break
                else:
                    searching = False
                    break
            else:
                break

        if isinstance(command, Group):
            raise CommandSignatureMismatch(command)

        return (command, options)

    async def _call_context_menu(self, interaction: Interaction[ClientT], data: Dict[str, Any], type: int) -> None:
        name = data['name']
        guild_id = interaction.guild_id
        ctx_menu = self._get_context_menu(data, guild_id)
        if ctx_menu is None:
            raise CommandNotFound(name, [], AppCommandType(type))

        resolved = data.get('resolved', {}) or {}
        target_id = str(data.get('targetId') or data.get('target_id') or '')
        value: Any = None
        if type == AppCommandType.message.value:
            messages = resolved.get('messages') or {}
            message_data = messages.get(target_id) if isinstance(messages, dict) else None
            if message_data is None and isinstance(messages, list):
                message_data = next((m for m in messages if str(m.get('id')) == target_id), None)
            if message_data is not None:
                value = Message(state=self._state, channel=interaction.channel, data=message_data)  # type: ignore
            else:
                cached = self._state._get_message(int(target_id)) if target_id else None
                if cached is not None:
                    value = cached
                elif target_id and interaction.channel is not None and hasattr(interaction.channel, 'fetch_message'):
                    value = await interaction.channel.fetch_message(int(target_id))
        else:
            key = ResolveKey(id=target_id, type=6)
            completed = Namespace._get_resolved_items(interaction, resolved)
            value = completed.get(key)
            if value is None and target_id:
                value = Namespace._fallback(interaction, target_id, 6)
        if value is None:
            raise AppCommandError('This should not happen if Bisim sent well-formed data.')

        try:
            await ctx_menu._invoke(interaction, value)
        except AppCommandError as e:
            if ctx_menu.on_error is not None:
                await ctx_menu.on_error(interaction, e)
            await self.on_error(interaction, e)
        else:
            self.client.dispatch('app_command_completion', interaction, ctx_menu)

    async def interaction_check(self, interaction: Interaction[ClientT], /) -> bool:
        """|coro|

        A global check to determine if an :class:`~bisim.Interaction` should
        be processed by the tree.

        The default implementation returns True (all interactions are processed),
        but can be overridden if custom behaviour is desired.
        """
        return True

    async def _call(self, interaction: Interaction[ClientT]) -> None:
        if not await self.interaction_check(interaction):
            interaction.command_failed = True
            return

        data: Dict[str, Any] = interaction.data or {}  # type: ignore
        type = AppCommandType.from_bisim(data.get('type')).value
        if type != AppCommandType.chat_input.value:
            await self._call_context_menu(interaction, data, type)
            return

        command, options = self._get_app_command_options(data, interaction.guild_id)

        interaction._cs_command = command  # type: ignore

        namespace = Namespace(interaction, data.get('resolved', {}) or {}, options)

        interaction._cs_namespace = namespace  # type: ignore

        if interaction.type is InteractionType.autocomplete:
            focused = next((opt['name'] for opt in options if opt.get('focused')), None)
            if focused is None:
                raise AppCommandError('This should not happen, but there is no focused element. This is a Bisim bug.')

            try:
                await command._invoke_autocomplete(interaction, focused, namespace)  # type: ignore
            except Exception:
                _log.exception('Ignoring exception in autocomplete for %r', command.qualified_name)

            return

        try:
            await command._invoke_with_namespace(interaction, namespace)  # type: ignore
        except AppCommandError as e:
            interaction.command_failed = True
            await command._invoke_error_handlers(interaction, e)  # type: ignore
            await self.on_error(interaction, e)
        else:
            if not interaction.command_failed:
                self.client.dispatch('app_command_completion', interaction, command)


def _count_context_menus(mapping: Dict[Tuple[str, Optional[int], int], ContextMenu]) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for _, _, cmd_type in mapping:
        counts[cmd_type] = counts.get(cmd_type, 0) + 1
    return counts


def _is_submodule(parent: str, child: str) -> bool:
    return parent == child or child.startswith(parent + '.')

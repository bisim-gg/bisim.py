from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, Sequence, TypeVar, Union

import bisim

from ... import utils
from ...abc import Messageable
from ...errors import NotSupported
from ...permissions import Permissions
from ...utils import MISSING

if TYPE_CHECKING:
    from typing_extensions import Self

    from ...embeds import Embed
    from ...file import File
    from ...guild import Guild
    from ...interactions import Interaction
    from ...member import Member
    from ...message import Message
    from ...state import ConnectionState
    from ...user import ClientUser, User
    from .bot import Bot, BotBase
    from .cog import Cog
    from .core import Command
    from .parameters import Parameter
    from .view import StringView

__all__ = ('Context',)

BotT = TypeVar('BotT', bound='Union[Bot, BotBase]', covariant=True)


class Context(Messageable, Generic[BotT]):
    r"""Represents the context in which a command is being invoked under.

    This class contains a lot of meta data to help you understand more about
    the invocation context. This class is not created manually and is instead
    passed around to commands as the first parameter.

    This class implements the :class:`~bisim.abc.Messageable` ABC.

    Attributes
    -----------
    message: :class:`.Message`
        The message that triggered the command being executed.
    bot: :class:`.Bot`
        The bot that contains the command being executed.
    args: :class:`list`
        The list of transformed arguments that were passed into the command.
        If this is accessed during the :func:`.on_command_error` event
        then this list could be incomplete.
    kwargs: :class:`dict`
        A dictionary of transformed arguments that were passed into the command.
        Similar to :attr:`args`\, if this is accessed in the
        :func:`.on_command_error` event then this dict could be incomplete.
    current_parameter: Optional[:class:`Parameter`]
        The parameter that is currently being inspected and converted.
        This is only of use for within converters.
    current_argument: Optional[:class:`str`]
        The argument string of the :attr:`current_parameter` that is currently being converted.
        This is only of use for within converters.
    interaction: Optional[:class:`~bisim.Interaction`]
        The interaction associated with this context (``None``: hybrid
        commands are not built yet).
    prefix: Optional[:class:`str`]
        The prefix that was used to invoke the command.
    command: Optional[:class:`Command`]
        The command that is being invoked currently.
    invoked_with: Optional[:class:`str`]
        The command name that triggered this invocation. Useful for finding out
        which alias called the command.
    invoked_parents: List[:class:`str`]
        The command names of the parents that triggered this invocation. Useful for
        finding out which aliases called the command.
    invoked_subcommand: Optional[:class:`Command`]
        The subcommand that was invoked.
        If no valid subcommand was invoked then this is equal to ``None``.
    subcommand_passed: Optional[:class:`str`]
        The string that was attempted to call a subcommand. This does not have
        to point to a valid registered subcommand and could just point to a
        nonsense string. If nothing was passed to attempt a call to a
        subcommand then this is set to ``None``.
    command_failed: :class:`bool`
        A boolean that indicates if the command failed to be parsed, checked,
        or invoked.
    """

    def __init__(
        self,
        *,
        message: Message,
        bot: BotT,
        view: StringView,
        args: List[Any] = MISSING,
        kwargs: Dict[str, Any] = MISSING,
        prefix: Optional[str] = None,
        command: Optional[Command[Any, ..., Any]] = None,
        invoked_with: Optional[str] = None,
        invoked_parents: List[str] = MISSING,
        invoked_subcommand: Optional[Command[Any, ..., Any]] = None,
        subcommand_passed: Optional[str] = None,
        command_failed: bool = False,
        current_parameter: Optional[Parameter] = None,
        current_argument: Optional[str] = None,
        interaction: Optional[Interaction[BotT]] = None,
    ):
        self.message: Message = message
        self.bot: BotT = bot
        self.args: List[Any] = args or []
        self.kwargs: Dict[str, Any] = kwargs or {}
        self.prefix: Optional[str] = prefix
        self.command: Optional[Command[Any, ..., Any]] = command
        self.view: StringView = view
        self.invoked_with: Optional[str] = invoked_with
        self.invoked_parents: List[str] = invoked_parents or []
        self.invoked_subcommand: Optional[Command[Any, ..., Any]] = invoked_subcommand
        self.subcommand_passed: Optional[str] = subcommand_passed
        self.command_failed: bool = command_failed
        self.current_parameter: Optional[Parameter] = current_parameter
        self.current_argument: Optional[str] = current_argument
        self.interaction: Optional[Interaction[BotT]] = interaction
        self._state: ConnectionState = self.message._state

    @classmethod
    async def from_interaction(cls, interaction: Interaction[BotT], /) -> Self:
        """|coro|

        Creates a context from a :class:`bisim.Interaction`. Hybrid commands
        are not built yet, so this raises :exc:`~bisim.NotSupported`.
        """
        raise NotSupported('Hybrid commands')

    async def invoke(self, command: Command[Any, ..., Any], /, *args: Any, **kwargs: Any) -> Any:
        r"""|coro|

        Calls a command with the arguments given.

        This is useful if you want to just call the callback that a
        :class:`.Command` holds internally.

        .. note::

            This does not handle converters, checks, cooldowns, pre-invoke,
            or after-invoke hooks in any matter. It calls the internal callback
            directly as-if it was a regular function.

            You must take care in passing the proper arguments when
            using this function.

        Parameters
        -----------
        command: :class:`.Command`
            The command that is going to be called.
        \*args
            The arguments to use.
        \*\*kwargs
            The keyword arguments to use.

        Raises
        -------
        TypeError
            The command argument to invoke is missing.
        """
        return await command(self, *args, **kwargs)

    async def reinvoke(self, *, call_hooks: bool = False, restart: bool = True) -> None:
        """|coro|

        Calls the command again.

        This is similar to :meth:`~.Context.invoke` except that it bypasses
        checks, cooldowns, and error handlers.

        Parameters
        ------------
        call_hooks: :class:`bool`
            Whether to call the before and after invoke hooks.
        restart: :class:`bool`
            Whether to start the call chain from the very beginning
            or where we left off (i.e. the command that caused the error).
            The default is to start where we left off.

        Raises
        -------
        ValueError
            The context to reinvoke is not valid.
        """
        cmd = self.command
        view = self.view
        if cmd is None:
            raise ValueError('This context is not valid.')

        index, previous = view.index, view.previous
        invoked_with = self.invoked_with
        invoked_subcommand = self.invoked_subcommand
        invoked_parents = self.invoked_parents
        subcommand_passed = self.subcommand_passed

        if restart:
            to_call = cmd.root_parent or cmd
            view.index = len(self.prefix or '')
            view.previous = 0
            self.invoked_parents = []
            self.invoked_with = view.get_word()
        else:
            to_call = cmd

        try:
            await to_call.reinvoke(self, call_hooks=call_hooks)
        finally:
            self.command = cmd
            view.index = index
            view.previous = previous
            self.invoked_with = invoked_with
            self.invoked_subcommand = invoked_subcommand
            self.invoked_parents = invoked_parents
            self.subcommand_passed = subcommand_passed

    @property
    def valid(self) -> bool:
        """:class:`bool`: Checks if the invocation context is valid to be invoked with."""
        return self.prefix is not None and self.command is not None

    async def _get_channel(self) -> Any:
        return self.channel

    @property
    def clean_prefix(self) -> str:
        """:class:`str`: The cleaned up invoke prefix. i.e. mentions are ``@name`` instead of ``<@id>``."""
        if self.prefix is None:
            return ''

        user = self.me
        # A mention prefix becomes the bot's name.
        pattern = re.compile(r'<@!?%s>' % user.id)
        return pattern.sub('@%s' % user.display_name.replace('\\', r'\\'), self.prefix)

    @property
    def cog(self) -> Optional[Cog]:
        """Optional[:class:`.Cog`]: Returns the cog associated with this context's command. None if it does not exist."""
        if self.command is None:
            return None
        return self.command.cog

    @property
    def filesize_limit(self) -> int:
        """:class:`int`: Returns the maximum number of bytes files can have when uploaded."""
        return self.guild.filesize_limit if self.guild is not None else 10 * 1024 * 1024

    @property
    def guild(self) -> Optional[Guild]:
        """Optional[:class:`.Guild`]: Returns the guild associated with this context's command. None if not available."""
        return self.message.guild

    @property
    def channel(self) -> Any:
        """Union[:class:`.abc.Messageable`]: Returns the channel associated with this context's command.
        Shorthand for :attr:`.Message.channel`.
        """
        return self.message.channel

    @property
    def author(self) -> Union[User, Member]:
        """Union[:class:`~bisim.User`, :class:`.Member`]:
        Returns the author associated with this context's command. Shorthand for :attr:`.Message.author`
        """
        return self.message.author

    @property
    def me(self) -> Union[Member, ClientUser]:
        """Union[:class:`.Member`, :class:`.ClientUser`]:
        Similar to :attr:`.Guild.me` except it may return the :class:`.ClientUser` in private message contexts.
        """
        return self.guild.me if self.guild is not None else self.bot.user  # type: ignore

    @property
    def permissions(self) -> Permissions:
        """:class:`.Permissions`: Returns the resolved permissions for the invoking user in this channel.
        Shorthand for :meth:`.abc.GuildChannel.permissions_for` or :attr:`.Interaction.permissions`.
        """
        if self.channel.type is bisim.ChannelType.private:
            return Permissions._dm_permissions()
        return self.channel.permissions_for(self.author)  # type: ignore

    @property
    def bot_permissions(self) -> Permissions:
        """:class:`.Permissions`: Returns the resolved permissions for the bot in this channel.
        Shorthand for :meth:`.abc.GuildChannel.permissions_for` or :attr:`.Interaction.app_permissions`.
        """
        channel = self.channel
        if channel.type is bisim.ChannelType.private:
            return Permissions._dm_permissions()
        return channel.permissions_for(self.me)  # type: ignore

    async def _load_channel_overwrites(self) -> None:
        ensure = getattr(self.channel, '_ensure_overwrites', None)
        if ensure is not None:
            await ensure()

    @property
    def voice_client(self) -> None:
        r"""Always ``None``: a bot cannot join voice on Bisim."""
        return None

    async def send_help(self, *args: Any) -> Any:
        """send_help(entity=<bot>)

        |coro|

        Shows the help command for the specified entity if given.
        The entity can be a command or a cog.

        If no entity is given, then it'll show help for the
        entire bot.

        If the entity is a string, then it looks up whether it's a
        :class:`Cog` or a :class:`Command`.

        .. note::

            Due to the way this function works, instead of returning
            something similar to :meth:`~.commands.HelpCommand.command_not_found`
            this returns ``None`` on bad input or no help command.

        Parameters
        ------------
        entity: Optional[Union[:class:`Command`, :class:`Cog`, :class:`str`]]
            The entity to show help for.

        Returns
        --------
        Any
            The result of the help command, if any.
        """
        from .core import Command, Group, wrap_callback
        from .errors import CommandError

        bot = self.bot
        cmd = bot.help_command

        if cmd is None:
            return None

        cmd = cmd.copy()
        cmd.context = self

        if len(args) == 0:
            await cmd.prepare_help_command(self, None)
            mapping = cmd.get_bot_mapping()
            injected = wrap_callback(cmd.send_bot_help)
            try:
                return await injected(mapping)
            except CommandError as e:
                await cmd.on_help_command_error(self, e)
                return None

        entity = args[0]
        if isinstance(entity, str):
            entity = bot.get_cog(entity) or bot.get_command(entity)

        if entity is None:
            return None

        try:
            entity.qualified_name
        except AttributeError:
            return None

        await cmd.prepare_help_command(self, entity.qualified_name)

        try:
            if hasattr(entity, '__cog_commands__'):
                injected = wrap_callback(cmd.send_cog_help)
                return await injected(entity)
            elif isinstance(entity, Group):
                injected = wrap_callback(cmd.send_group_help)
                return await injected(entity)
            elif isinstance(entity, Command):
                injected = wrap_callback(cmd.send_command_help)
                return await injected(entity)
            else:
                return None
        except CommandError as e:
            await cmd.on_help_command_error(self, e)

    async def reply(self, content: Optional[str] = None, **kwargs: Any) -> Message:
        """|coro|

        A shortcut method to :meth:`send` to reply to the
        :class:`~bisim.Message` referenced by this context.

        Raises
        --------
        ~bisim.HTTPException
            Sending the message failed.
        ~bisim.Forbidden
            You do not have the proper permissions to send the message.
        ValueError
            The ``files`` list is not of the appropriate size
        TypeError
            You specified both ``file`` and ``files``.

        Returns
        ---------
        :class:`~bisim.Message`
            The message that was sent.
        """
        return await self.send(content, reference=self.message, **kwargs)

    async def defer(self, *, ephemeral: bool = False) -> None:
        """|coro|

        Defers the interaction based contexts. For a context made from a
        message this does nothing.

        Parameters
        -----------
        ephemeral: :class:`bool`
            Indicates whether the deferred message will eventually be ephemeral.
        """
        return None

    async def send(self, content: Optional[str] = None, **kwargs: Any) -> Message:
        """|coro|

        Sends a message to the destination with the content given.

        This works the same as :meth:`~bisim.abc.Messageable.send` and takes
        the same keyword arguments. ``ephemeral`` is accepted and ignored for
        contexts made from a message, as in discord.py.

        Returns
        ---------
        :class:`~bisim.Message`
            The message that was sent.
        """
        kwargs.pop('ephemeral', None)
        return await super().send(content, **kwargs)

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Literal, Optional, TypeVar, Union, overload

from ..enums import Enum, Locale

if TYPE_CHECKING:
    from .commands import Command, ContextMenu, Group, Parameter
    from .models import Choice

__all__ = (
    'TranslationContextLocation',
    'TranslationContextTypes',
    'TranslationContext',
    'Translator',
    'locale_str',
)


class TranslationContextLocation(Enum):
    command_name = 0
    command_description = 1
    group_name = 2
    group_description = 3
    parameter_name = 4
    parameter_description = 5
    choice_name = 6
    other = 7


_L = TypeVar('_L', bound=TranslationContextLocation)
_D = TypeVar('_D')


class TranslationContext(Generic[_L, _D]):
    """A class that provides context for the :class:`locale_str` being translated.

    This is useful to determine where exactly the string is located and aid in looking
    up the actual translation.

    Attributes
    -----------
    location: :class:`TranslationContextLocation`
        The location where this string is located.
    data: Any
        The extraneous data that is being translated.
    """

    __slots__ = ('location', 'data')

    def __init__(self, location: _L, data: _D) -> None:
        self.location: _L = location
        self.data: _D = data


TranslationContextTypes = TranslationContext[Any, Any]


class Translator:
    """A class that handles translations for commands, parameters, and choices.

    Translations are done lazily in order to allow for async enabled translations as well
    as supporting a wide array of translation systems such as :mod:`gettext` and
    `Project Fluent <https://projectfluent.org>`_.

    In order for a translator to be used, it must be set using the :meth:`CommandTree.set_translator`
    method. The translation flow for a string is as follows:

    1. Use :class:`locale_str` instead of :class:`str` in areas of a command you want to be translated.
        - Currently, these are command names, command descriptions, parameter names, parameter descriptions, and choice names.
        - This can also be used inside the :func:`~bisim.app_commands.describe` decorator.
    2. Call :meth:`CommandTree.set_translator` to the translator instance that will handle the translations.
    3. Call :meth:`CommandTree.sync`
    4. The library will call :meth:`Translator.translate` on all the relevant strings being translated.

    Bisim shows commands in Persian (``fa``) and English (``en``), so those
    are the two locales the library asks for.
    """

    async def load(self) -> None:
        """|coro|

        An asynchronous setup function for loading the translation system.

        The default implementation does nothing.

        This is invoked when :meth:`CommandTree.set_translator` is called.
        """
        pass

    async def unload(self) -> None:
        """|coro|

        An asynchronous teardown function for unloading the translation system.

        The default implementation does nothing.

        This is invoked when :meth:`CommandTree.set_translator` is called
        if a tree already has a translator or when :meth:`bisim.Client.close` is called.
        """
        pass

    async def _checked_translate(self, string: locale_str, locale: Locale, context: TranslationContextTypes) -> Optional[str]:
        from .errors import TranslationError

        try:
            return await self.translate(string, locale, context)
        except TranslationError:
            raise
        except Exception as e:
            raise TranslationError(string=string, locale=locale, context=context) from e

    async def translate(self, string: locale_str, locale: Locale, context: TranslationContextTypes) -> Optional[str]:
        """|coro|

        Translates the given string to the specified locale.

        If the string cannot be translated, ``None`` should be returned.

        The default implementation returns ``None``.

        If an exception is raised in this method, it should inherit from :exc:`TranslationError`.
        If it doesn't, then when this is called the exception will be chained with it instead.

        Parameters
        ------------
        string: :class:`locale_str`
            The string being translated.
        locale: :class:`~bisim.Locale`
            The locale being requested for translation.
        context: :class:`TranslationContext`
            The translation context where the string originated from.
        """
        return None


class locale_str:
    """Marks a string as ready for translation.

    This is done lazily and is not actually translated until :meth:`CommandTree.sync` is called.

    The sync method then ultimately defers the responsibility of translating to the :class:`Translator`
    instance used by the :class:`CommandTree`. For more information on the translation flow, see the
    :class:`Translator` documentation.

    .. container:: operations

        .. describe:: str(x)

            Returns the message passed to the string.

        .. describe:: x == y

            Checks if the string is equal to another string.

        .. describe:: x != y

            Checks if the string is not equal to another string.

        .. describe:: hash(x)

            Returns the hash of the string.

    Attributes
    ------------
    message: :class:`str`
        The message being translated. Once set, this cannot be changed.

        .. warning::

            This must be the default "message" that you send to Bisim.
            Since this is used for display when no translation is found.
    extras: :class:`dict`
        A dict of user provided extras to attach to the translated string.
        This can be used to add more context, information, or any metadata necessary
        to aid in actually translating the string.

        Since these are passed via keyword arguments, the keys are strings.
    """

    __slots__ = ('__message', 'extras')

    def __init__(self, message: str, /, **kwargs: Any) -> None:
        self.__message: str = message
        self.extras: dict[str, Any] = kwargs

    @property
    def message(self) -> str:
        return self.__message

    def __str__(self) -> str:
        return self.__message

    def __repr__(self) -> str:
        kwargs = ', '.join(f'{k}={v!r}' for k, v in self.extras.items())
        if kwargs:
            return f'{self.__class__.__name__}({self.__message!r}, {kwargs})'
        return f'{self.__class__.__name__}({self.__message!r})'

    def __eq__(self, obj: object) -> bool:
        return isinstance(obj, locale_str) and self.message == obj.message

    def __hash__(self) -> int:
        return hash(self.__message)

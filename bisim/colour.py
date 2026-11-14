from __future__ import annotations

import colorsys
import random
import re
from typing import TYPE_CHECKING, Any, Optional, Tuple, Union

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = (
    'Colour',
    'Color',
)

_HEX_RE = re.compile(r'^(?:#|0x)?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$')
_RGB_RE = re.compile(r'^rgb\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,]+?)\s*\)$', re.IGNORECASE)


def _parse_channel(text: str) -> int:
    text = text.strip()
    if text.endswith('%'):
        value = float(text[:-1])
        if not 0 <= value <= 100:
            raise ValueError('percentages must be between 0% and 100%')
        return round(255 * value / 100)
    value = int(text)
    if not 0 <= value <= 255:
        raise ValueError('channel values must be between 0 and 255')
    return value


class Colour:
    """Represents a Bisim role colour. This class is similar
    to a (red, green, blue) :class:`tuple`.

    There is an alias for this called Color.

    .. container:: operations

        .. describe:: x == y

             Checks if two colours are equal.

        .. describe:: x != y

             Checks if two colours are not equal.

        .. describe:: hash(x)

             Return the colour's hash.

        .. describe:: str(x)

             Returns the hex format for the colour.

        .. describe:: int(x)

             Returns the raw colour value.

    Attributes
    ------------
    value: :class:`int`
        The raw integer colour value.
    """

    __slots__ = ('value',)

    def __init__(self, value: int):
        if not isinstance(value, int):
            raise TypeError(f'Expected int parameter, received {value.__class__.__name__} instead.')
        self.value: int = value

    def _get_byte(self, byte: int) -> int:
        return (self.value >> (8 * byte)) & 0xFF

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Colour) and self.value == other.value

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __str__(self) -> str:
        return f'#{self.value:0>6x}'

    def __int__(self) -> int:
        return self.value

    def __repr__(self) -> str:
        return f'<Colour value={self.value}>'

    def __hash__(self) -> int:
        return hash(self.value)

    @property
    def r(self) -> int:
        """:class:`int`: Returns the red component of the colour."""
        return self._get_byte(2)

    @property
    def g(self) -> int:
        """:class:`int`: Returns the green component of the colour."""
        return self._get_byte(1)

    @property
    def b(self) -> int:
        """:class:`int`: Returns the blue component of the colour."""
        return self._get_byte(0)

    def to_rgb(self) -> Tuple[int, int, int]:
        """Tuple[:class:`int`, :class:`int`, :class:`int`]: Returns an (r, g, b) tuple representing the colour."""
        return (self.r, self.g, self.b)

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int) -> Self:
        """Constructs a :class:`Colour` from an RGB tuple."""
        return cls((r << 16) | (g << 8) | b)

    @classmethod
    def from_hsv(cls, h: float, s: float, v: float) -> Self:
        """Constructs a :class:`Colour` from an HSV tuple."""
        red, green, blue = colorsys.hsv_to_rgb(h, s, v)
        return cls.from_rgb(round(red * 255), round(green * 255), round(blue * 255))

    @classmethod
    def from_str(cls, value: str) -> Colour:
        """Constructs a :class:`Colour` from a string.

        The following formats are accepted:

        - ``0x<hex>``
        - ``#<hex>``
        - ``0x#<hex>``
        - ``rgb(<number>, <number>, <number>)``

        Like CSS, ``<number>`` can be either 0-255 or 0-100% and ``<hex>`` can be
        either a 6 digit hex number or a 3 digit hex shortcut (e.g. #FFF).

        Raises
        -------
        ValueError
            The string could not be converted into a colour.
        """
        if not value:
            raise ValueError('unknown colour format given')
        text = value.strip()
        if text.startswith('0x#'):
            text = text[2:]
        match = _HEX_RE.match(text)
        if match:
            digits = match.group(1)
            if len(digits) == 3:
                digits = ''.join(char * 2 for char in digits)
            return cls(int(digits, 16))
        match = _RGB_RE.match(text)
        if match:
            red, green, blue = (_parse_channel(part) for part in match.groups())
            return cls.from_rgb(red, green, blue)
        raise ValueError('unknown colour format given')

    @classmethod
    def default(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0``."""
        return cls(0)

    @classmethod
    def random(cls, *, seed: Optional[Union[int, str, float, bytes, bytearray]] = None) -> Self:
        """A factory method that returns a :class:`Colour` with a random hue.

        .. note::

            The random algorithm works by choosing a colour with a random hue but
            with maxed out saturation and value.

        Parameters
        ------------
        seed: Optional[Union[:class:`int`, :class:`str`, :class:`float`, :class:`bytes`, :class:`bytearray`]]
            The seed to initialize the RNG with. If ``None`` is passed the default RNG is used.
        """
        generator = random if seed is None else random.Random(seed)
        return cls.from_hsv(generator.random(), 1, 1)

    @classmethod
    def teal(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x1ABC9C``."""
        return cls(0x1ABC9C)

    @classmethod
    def dark_teal(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x11806A``."""
        return cls(0x11806A)

    @classmethod
    def brand_green(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x57F287``."""
        return cls(0x57F287)

    @classmethod
    def green(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x2ECC71``."""
        return cls(0x2ECC71)

    @classmethod
    def dark_green(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x1F8B4C``."""
        return cls(0x1F8B4C)

    @classmethod
    def blue(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x3498DB``."""
        return cls(0x3498DB)

    @classmethod
    def dark_blue(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x206694``."""
        return cls(0x206694)

    @classmethod
    def purple(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x9B59B6``."""
        return cls(0x9B59B6)

    @classmethod
    def dark_purple(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x71368A``."""
        return cls(0x71368A)

    @classmethod
    def magenta(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xE91E63``."""
        return cls(0xE91E63)

    @classmethod
    def dark_magenta(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xAD1457``."""
        return cls(0xAD1457)

    @classmethod
    def gold(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xF1C40F``."""
        return cls(0xF1C40F)

    @classmethod
    def dark_gold(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xC27C0E``."""
        return cls(0xC27C0E)

    @classmethod
    def orange(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xE67E22``."""
        return cls(0xE67E22)

    @classmethod
    def dark_orange(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xA84300``."""
        return cls(0xA84300)

    @classmethod
    def brand_red(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xED4245``."""
        return cls(0xED4245)

    @classmethod
    def red(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xE74C3C``."""
        return cls(0xE74C3C)

    @classmethod
    def dark_red(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x992D22``."""
        return cls(0x992D22)

    @classmethod
    def lighter_grey(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x95A5A6``."""
        return cls(0x95A5A6)

    lighter_gray = lighter_grey

    @classmethod
    def dark_grey(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x607D8B``."""
        return cls(0x607D8B)

    dark_gray = dark_grey

    @classmethod
    def light_grey(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x979C9F``."""
        return cls(0x979C9F)

    light_gray = light_grey

    @classmethod
    def darker_grey(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x546E7A``."""
        return cls(0x546E7A)

    darker_gray = darker_grey

    @classmethod
    def og_blurple(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x7289DA``."""
        return cls(0x7289DA)

    @classmethod
    def blurple(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x5865F2``."""
        return cls(0x5865F2)

    @classmethod
    def greyple(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x99AAB5``."""
        return cls(0x99AAB5)

    @classmethod
    def ash_theme(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x2E2E34``."""
        return cls(0x2E2E34)

    @classmethod
    def dark_theme(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x1A1A1E``."""
        return cls(0x1A1A1E)

    @classmethod
    def onyx_theme(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x070709``."""
        return cls(0x070709)

    @classmethod
    def light_theme(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xFBFBFB``."""
        return cls(0xFBFBFB)

    @classmethod
    def fuchsia(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xEB459E``."""
        return cls(0xEB459E)

    @classmethod
    def yellow(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xFEE75C``."""
        return cls(0xFEE75C)

    @classmethod
    def ash_embed(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x37373E``."""
        return cls(0x37373E)

    @classmethod
    def dark_embed(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x242429``."""
        return cls(0x242429)

    @classmethod
    def onyx_embed(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0x131416``."""
        return cls(0x131416)

    @classmethod
    def light_embed(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xFFFFFF``."""
        return cls(0xFFFFFF)

    @classmethod
    def pink(cls) -> Self:
        """A factory method that returns a :class:`Colour` with a value of ``0xEB459F``."""
        return cls(0xEB459F)


Color = Colour

from __future__ import annotations

from typing import Optional

from .errors import ExpectedClosingQuoteError, InvalidEndOfQuotedStringError, UnexpectedQuoteError

__all__ = ('StringView',)

# Opening quote marks and the mark that closes each.
_QUOTES = {
    '"': '"',
    '‘': '’',
    '‚': '‛',
    '“': '”',
    '„': '‟',
    '⹂': '⹂',
    '「': '」',
    '『': '』',
    '〝': '〞',
    '﹁': '﹂',
    '﹃': '﹄',
    '＂': '＂',
    '｢': '｣',
    '«': '»',
    '‹': '›',
    '《': '》',
    '〈': '〉',
}
_ALL_QUOTES = set(_QUOTES) | set(_QUOTES.values())


class StringView:
    """A cursor over a message's text, used to split it into arguments."""

    def __init__(self, buffer: str) -> None:
        self.index: int = 0
        self.buffer: str = buffer
        self.end: int = len(buffer)
        self.previous: int = 0

    @property
    def current(self) -> Optional[str]:
        return None if self.eof else self.buffer[self.index]

    @property
    def eof(self) -> bool:
        return self.index >= self.end

    def undo(self) -> None:
        self.index = self.previous

    def skip_ws(self) -> bool:
        position = self.index
        while position < self.end and self.buffer[position].isspace():
            position += 1
        self.previous = self.index
        self.index = position
        return self.previous != self.index

    def skip_string(self, string: str) -> bool:
        if self.buffer.startswith(string, self.index):
            self.previous = self.index
            self.index += len(string)
            return True
        return False

    def read_rest(self) -> str:
        result = self.buffer[self.index :]
        self.previous = self.index
        self.index = self.end
        return result

    def read(self, n: int) -> str:
        result = self.buffer[self.index : self.index + n]
        self.previous = self.index
        self.index += n
        return result

    def get(self) -> Optional[str]:
        try:
            result = self.buffer[self.index + 1]
        except IndexError:
            result = None

        self.previous = self.index
        self.index += 1
        return result

    def get_word(self) -> str:
        position = self.index
        while position < self.end and not self.buffer[position].isspace():
            position += 1
        result = self.buffer[self.index : position]
        self.previous = self.index
        self.index = position
        return result

    def get_quoted_word(self) -> Optional[str]:
        """Reads one argument: a quoted string (quotes removed) or a bare word.

        Inside quotes, a backslash escapes the quote marks. A quote mark in
        the middle of a bare word, a quoted string that is never closed, and a
        closing quote followed by something other than a space are errors.
        """
        if self.eof:
            return None

        buffer = self.buffer
        start = self.index
        first = buffer[start]
        closing = _QUOTES.get(first)
        escapable = (first, closing) if closing else _ALL_QUOTES
        position = start + 1 if closing else start
        pieces = []

        while True:
            if position >= self.end:
                if closing:
                    raise ExpectedClosingQuoteError(closing)
                break

            char = buffer[position]
            if char == '\\':
                following = buffer[position + 1] if position + 1 < self.end else None
                if following is None:
                    if closing:
                        raise ExpectedClosingQuoteError(closing)
                    position += 1
                    break
                if following in escapable:
                    pieces.append(following)
                    position += 2
                    continue
                pieces.append(char)
                position += 1
                continue

            if closing:
                if char == closing:
                    following = buffer[position + 1] if position + 1 < self.end else None
                    if following is not None and not following.isspace():
                        raise InvalidEndOfQuotedStringError(following)
                    position += 1
                    break
            else:
                if char.isspace():
                    break
                if char in _ALL_QUOTES and position != start:
                    raise UnexpectedQuoteError(char)

            pieces.append(char)
            position += 1

        self.previous = start
        self.index = position
        return ''.join(pieces)

    def __repr__(self) -> str:
        return f'<StringView pos: {self.index} prev: {self.previous} end: {self.end} eof: {self.eof}>'

"""A Griffe extension that turns bisim.py's docstrings into the Markdown mkdocstrings renders.

The docstrings are written the way discord.py writes them: reStructuredText for Sphinx, with numpy style
sections whose items read ``name: type``. This extension rewrites each docstring once the package is
loaded, before mkdocstrings parses it:

- roles such as ``:class:`~bisim.Guild``` and ``:meth:`send``` become links to the reference (optional
  autorefs, so a target that is not rendered anywhere becomes plain code instead of a broken link);
- inside Parameters, Attributes, Returns, Raises and Yields, the types become plain Python expressions
  that Griffe can resolve, and ``name: type`` becomes the numpy ``name : type``;
- ``.. note::`` and ``.. warning::`` become admonitions, ``.. code-block::`` and ``::`` literal blocks
  become fenced code, and ``.. container:: operations`` becomes a list of the supported operations;
- the substitutions ``|coro|`` and ``|maybecoro|`` become the sentences they stand for.

It is used only to build the documentation and is not part of the package.
"""

from __future__ import annotations

import ast
import re
from typing import Iterator, List, Optional, Tuple

import griffe
from griffe._internal import finder as _griffe_finder

PACKAGE = 'bisim'

# bisim/__init__.py keeps discord.py's ``__path__ = __import__('pkgutil').extend_path(...)`` line, which
# makes Griffe take the package for a namespace package and skip its __init__.py, where every public name
# is imported. bisim is a regular package, so it is exempted here.
_is_pkg_style_namespace = _griffe_finder._is_pkg_style_namespace


def _regular_bisim_package(init_module) -> bool:  # type: ignore[no-untyped-def]
    if init_module.parent.name == PACKAGE:
        return False
    return _is_pkg_style_namespace(init_module)


_griffe_finder._is_pkg_style_namespace = _regular_bisim_package

# Public namespaces, in the order a short name is looked up when it is not imported where it is used.
PUBLIC_NAMESPACES = (
    'bisim',
    'bisim.app_commands',
    'bisim.app_commands.checks',
    'bisim.ui',
    'bisim.ext.commands',
    'bisim.ext.tasks',
    'bisim.ext.voice_recv',
    'bisim.abc',
    'bisim.utils',
    'bisim.http_interactions',
)

# Short module names that docstrings use as a prefix, as in :class:`commands.Bot`.
MODULE_ALIASES = {
    'bisim': 'bisim',
    'commands': 'bisim.ext.commands',
    'ext.commands': 'bisim.ext.commands',
    'tasks': 'bisim.ext.tasks',
    'ext.tasks': 'bisim.ext.tasks',
    'voice_recv': 'bisim.ext.voice_recv',
    'ext.voice_recv': 'bisim.ext.voice_recv',
    'opus': 'bisim.opus',
    'app_commands': 'bisim.app_commands',
    'ui': 'bisim.ui',
    'abc': 'bisim.abc',
    'utils': 'bisim.utils',
    'checks': 'bisim.app_commands.checks',
}

# :ref: targets that have a heading in the documentation (see reference/events.md).
REF_ANCHORS = {
    'bisim-api-events': 'bisim-api-events',
    'bisim_api_models': 'bisim-api-models',
}

SUBSTITUTIONS = {
    '|coro|': 'This function is a coroutine.',
    '|maybecoro|': 'This function could be a coroutine.',
    '|coroutine_link|_': 'coroutine',
}

NUMPY_SECTIONS = {
    'parameters': 'Parameters',
    'other parameters': 'Other Parameters',
    'attributes': 'Attributes',
    'returns': 'Returns',
    'yields': 'Yields',
    'raises': 'Raises',
    'examples': 'Examples',
    'example': 'Examples',
}
NAMED_ITEM_SECTIONS = {'Parameters', 'Other Parameters', 'Attributes'}
TYPE_ITEM_SECTIONS = {'Returns', 'Yields', 'Raises'}

ADMONITIONS = {
    'note': 'note',
    'warning': 'warning',
    'tip': 'tip',
    'hint': 'tip',
    'important': 'warning',
    'caution': 'warning',
    'danger': 'danger',
    'seealso': 'info',
}

ROLE_RE = re.compile(r':(?:py:)?(class|attr|meth|func|exc|obj|data|mod|ref|term|doc|const):`([^`]+)`')
TITLED_TARGET_RE = re.compile(r'^(?P<title>.*?)\s*<(?P<target>[^<>]+)>$', re.DOTALL)
DIRECTIVE_RE = re.compile(r'^(?P<indent>\s*)\.\.\s+(?P<name>[\w-]+)::\s*(?P<arg>.*)$')
LINK_TARGET_RE = re.compile(r'^\s*\.\.\s+_[^:]+:\s*\S+\s*$')
ANONYMOUS_TARGET_RE = re.compile(r'^\s*__\s+\S+_\s*$')
RST_LINK_RE = re.compile(r'`([^`<>]+?)\s*<([^<>`]+)>`__?')
RST_REF_RE = re.compile(r'`([^`<>]+?)`__?(?![\w`])')
DOUBLE_BACKTICK_RE = re.compile(r'``(.+?)``')
GRID_BORDER_RE = re.compile(r'^\s*\+[-=+]+\+\s*$')
GRID_ROW_RE = re.compile(r'^\s*\|.*\|\s*$')
NAMED_ITEM_RE = re.compile(r'^(?P<indent>\s*)(?P<names>\\?\*{0,2}\\?\*?[A-Za-z_][\w]*(?:,\s*\\?\*{0,2}[A-Za-z_][\w]*)*)\s*:\s*(?P<type>.+?)\s*$')
BUILTINS = {
    'str', 'int', 'float', 'bool', 'bytes', 'dict', 'list', 'tuple', 'set', 'frozenset', 'object', 'type',
    'None', 'True', 'False', 'Any', 'Optional', 'Union', 'List', 'Dict', 'Tuple', 'Set', 'Callable',
    'Sequence', 'Mapping', 'Iterable', 'Iterator', 'Awaitable', 'Coroutine', 'Literal', 'Type', 'bytearray',
    'memoryview', 'range', 'slice', 'complex', 'Exception', 'BaseException', 'TypeError', 'ValueError',
    'KeyError', 'IndexError', 'AttributeError', 'RuntimeError', 'NotImplementedError', 'StopIteration',
    'asyncio', 'datetime', 'aiohttp', 'typing', 'collections', 'io', 'os', 'enum', 'inspect', 'logging',
}


class _Index:
    """Finds the public path of a name used in a docstring."""

    def __init__(self, package: griffe.Module) -> None:
        self.package = package
        self.public: dict[str, str] = {}
        self.short: dict[str, List[str]] = {}
        for namespace in PUBLIC_NAMESPACES:
            module = self._walk(namespace)
            if module is None:
                continue
            for name, member in list(module.members.items()):
                if name.startswith('_'):
                    continue
                target = _final(member)
                if target is None or target.is_module:
                    continue
                public_path = f'{namespace}.{name}'
                self.public.setdefault(target.path, public_path)
                self.short.setdefault(name, [])
                if public_path not in self.short[name]:
                    self.short[name].append(public_path)

    def _walk(self, path: str) -> Optional[griffe.Object]:
        parts = path.split('.')
        if parts[0] != self.package.name:
            return None
        current: Optional[griffe.Object] = self.package
        for part in parts[1:]:
            if current is None:
                return None
            members = current.all_members if current.is_class else current.members
            member = members.get(part)
            if member is None:
                return None
            current = _final(member)
        return current

    def exists(self, path: str) -> bool:
        return self._walk(path) is not None

    def public_path(self, obj: griffe.Object) -> str:
        """The path under which ``obj`` is documented, preferring the public namespaces."""
        if obj.path in self.public:
            return self.public[obj.path]
        parent = obj.parent
        if parent is not None and not parent.is_module:
            return f'{self.public_path(parent)}.{obj.name}'
        return obj.path

    def resolve(self, target: str, ctx: griffe.Object) -> Optional[str]:
        """The public path of ``target`` as written in ``ctx``'s docstring, or ``None`` outside bisim."""
        target = target.strip().lstrip('.').rstrip('()')
        if not target:
            return None

        if target == PACKAGE or target.startswith(PACKAGE + '.'):
            found = self._walk(target)
            return self.public_path(found) if found is not None else target

        for alias, module_path in sorted(MODULE_ALIASES.items(), key=lambda item: -len(item[0])):
            if target.startswith(alias + '.'):
                candidate = module_path + target[len(alias):]
                found = self._walk(candidate)
                if found is not None:
                    return self.public_path(found)

        head, _, rest = target.partition('.')

        # A member of the class the docstring belongs to.
        cls = _owning_class(ctx)
        while cls is not None:
            member = cls.all_members.get(head)
            if member is not None:
                found = _final(member)
                if found is not None:
                    path = self.public_path(found)
                    return self._descend(path, rest)
            cls = _owning_class(cls.parent) if cls.parent is not None and not cls.parent.is_module else None

        # A name imported or defined in the docstring's module.
        module = ctx.module
        member = module.members.get(head)
        if member is not None:
            found = _final(member)
            if found is not None and found.path.startswith(PACKAGE):
                return self._descend(self.public_path(found), rest)

        # A public name anywhere, preferring the part of the package the docstring is in.
        candidates = self.short.get(head, [])
        if candidates:
            here = ctx.path
            preferred = [c for c in candidates if here.startswith(c.rsplit('.', 1)[0] + '.')]
            preferred.sort(key=lambda c: -len(c))
            choice = (preferred or candidates)[0]
            return self._descend(choice, rest)
        return None

    def _descend(self, path: str, rest: str) -> str:
        if not rest:
            return path
        candidate = f'{path}.{rest}'
        found = self._walk(candidate)
        return self.public_path(found) if found is not None else candidate


def _final(obj: griffe.Object | griffe.Alias) -> Optional[griffe.Object]:
    if obj.is_alias:
        try:
            return obj.final_target  # type: ignore[union-attr]
        except (griffe.AliasResolutionError, griffe.CyclicAliasError):
            return None
    return obj  # type: ignore[return-value]


def _owning_class(obj: Optional[griffe.Object]) -> Optional[griffe.Object]:
    while obj is not None and not obj.is_module:
        if obj.is_class:
            return obj
        obj = obj.parent
    return None


def _walk_objects(obj: griffe.Object) -> Iterator[griffe.Object]:
    yield obj
    for member in obj.members.values():
        if member.is_alias:
            continue
        yield from _walk_objects(member)  # type: ignore[arg-type]


def _split_role(text: str) -> Tuple[Optional[str], str]:
    match = TITLED_TARGET_RE.match(text)
    if match and match.group('title'):
        return match.group('title').strip(), match.group('target').strip()
    return None, text.strip()


def _display(role: str, title: Optional[str], target: str) -> str:
    if title:
        return title
    shown = target
    if shown.startswith('~'):
        shown = shown[1:].rstrip('()').split('.')[-1]
    shown = shown.lstrip('.')
    if role in ('meth', 'func') and not shown.endswith(')'):
        shown += '()'
    return shown


def _autoref(identifier: str, html_title: str) -> str:
    return f'<autoref identifier="{identifier}" optional>{html_title}</autoref>'


def _code(text: str) -> str:
    return '<code>' + text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;') + '</code>'


class _Converter:
    def __init__(self, ctx: griffe.Object, index: _Index) -> None:
        self.ctx = ctx
        self.index = index

    # Inline text

    def prose_role(self, match: re.Match) -> str:
        role, body = match.group(1), match.group(2)
        title, target = _split_role(body)
        bare = target.lstrip('~')

        if role == 'term':
            text = title or bare
            return text.split(':', 1)[1] if ':' in text and not title else text
        if role == 'doc':
            return title or bare
        if role == 'ref':
            text = title or bare.replace('_', ' ')
            anchor = REF_ANCHORS.get(bare)
            return _autoref(anchor, text) if anchor else text

        shown = _display(role, title, target)
        if role == 'mod':
            path = bare if bare.startswith(PACKAGE) else None
            return _autoref(path, _code(shown)) if path else _code(shown)

        resolved = self.index.resolve(bare, self.ctx)
        if resolved is None and role == 'func':
            name = bare.split('.')[-1]
            if name.startswith('on_'):
                return _autoref(name, _code(shown))
        if resolved is None:
            return _code(shown)
        return _autoref(resolved, _code(shown))

    def inline(self, line: str) -> str:
        for key, value in SUBSTITUTIONS.items():
            line = line.replace(key, value)
        line = RST_LINK_RE.sub(lambda m: f'[{m.group(1).strip()}]({m.group(2).strip()})', line)
        line = ROLE_RE.sub(self.prose_role, line)
        line = DOUBLE_BACKTICK_RE.sub(lambda m: '`' + m.group(1) + '`', line)
        line = RST_REF_RE.sub(lambda m: m.group(1), line)
        return line

    # Types in section items

    def type_role(self, match: re.Match) -> str:
        role, body = match.group(1), match.group(2)
        title, target = _split_role(body)
        if role in ('ref', 'term', 'doc'):
            text = (title or target).split()[-1]
            return text
        bare = target.lstrip('~').lstrip('.').rstrip('()')
        short = bare.split('.')[-1]
        if '.' not in bare or bare.split('.')[0] in BUILTINS:
            return bare if bare.split('.')[0] in BUILTINS else short
        return short

    def type_text(self, text: str) -> str:
        text = ROLE_RE.sub(self.type_role, text)
        text = DOUBLE_BACKTICK_RE.sub(lambda m: m.group(1), text)
        return text.strip()

    def named_item(self, line: str) -> str:
        match = NAMED_ITEM_RE.match(line)
        if not match:
            return self.inline(line.replace('\\*', '*'))
        names = match.group('names').replace('\\*', '*')
        return f"{match.group('indent')}{names} : {self.type_text(match.group('type'))}"

    def type_item(self, line: str) -> str:
        indent = line[: len(line) - len(line.lstrip())]
        text = self.type_text(line)
        if text.startswith('~'):
            text = text[1:].split('.')[-1]
        return indent + text

    # Blocks

    def convert(self, text: str) -> str:
        lines = text.expandtabs(4).split('\n')
        out: List[str] = []
        deferred: List[str] = []
        section: Optional[str] = None
        section_indent = 0
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            indent = _indent(line)

            # Numpy section headers, and the reStructuredText titles of module docstrings.
            if stripped and i + 1 < len(lines) and _is_underline(lines[i + 1]) and _indent(lines[i + 1]) == indent:
                underline = lines[i + 1].strip()[0]
                title = NUMPY_SECTIONS.get(stripped.lower())
                if underline == '-' and title:
                    out.append(' ' * indent + title)
                    out.append(' ' * indent + '-' * len(title))
                    section, section_indent = title, indent
                    i += 2
                    continue
                if underline in '~=':
                    i += 2
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                    continue
                out.append(' ' * indent + f'**{self.inline(stripped)}**')
                i += 2
                continue

            if LINK_TARGET_RE.match(line) or ANONYMOUS_TARGET_RE.match(line):
                i += 1
                continue

            if GRID_BORDER_RE.match(line):
                table: List[str] = []
                while i < len(lines) and (GRID_BORDER_RE.match(lines[i]) or GRID_ROW_RE.match(lines[i])):
                    table.append(lines[i].strip())
                    i += 1
                out.extend(self.grid_table(table, indent))
                continue

            directive = DIRECTIVE_RE.match(line)
            if directive:
                block, i = _collect_block(lines, i + 1, indent)
                rendered = self.directive(directive.group('name'), directive.group('arg').strip(), block, indent)
                if section in NAMED_ITEM_SECTIONS | TYPE_ITEM_SECTIONS and indent == section_indent:
                    # A note between the items of a section would be read as one more item; it goes at the end.
                    deferred.extend(rendered)
                else:
                    out.extend(rendered)
                continue

            if stripped.endswith('::') and not stripped.startswith('..'):
                block, j = _collect_block(lines, i + 1, indent)
                if any(b.strip() for b in block):
                    lead = stripped[:-2].rstrip()
                    if lead:
                        if not lead.endswith(':'):
                            lead += ':'
                        out.append(' ' * indent + self.inline(lead))
                        out.append('')
                    out.extend(_fence(block, indent, 'python'))
                    i = j
                    continue

            if section in NAMED_ITEM_SECTIONS and stripped and indent == section_indent:
                out.append(self.named_item(line))
            elif section in TYPE_ITEM_SECTIONS and stripped and indent == section_indent:
                out.append(self.type_item(line))
            else:
                out.append(self.inline(line))
            i += 1
        if deferred:
            out.extend(['', *deferred])
        return '\n'.join(out)

    def grid_table(self, table: List[str], indent: int) -> List[str]:
        """A reStructuredText grid table as a Markdown table; the first row is the header."""
        rows: List[List[str]] = []
        current: Optional[List[str]] = None
        for line in table:
            if GRID_BORDER_RE.match(line):
                if current is not None:
                    rows.append(current)
                current = None
                continue
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            if current is None:
                current = cells
            else:
                current = [f'{a} {b}'.strip() for a, b in zip(current, cells)]
        if current is not None:
            rows.append(current)
        if not rows:
            return []
        pad = ' ' * indent
        out = ['']
        out.append(pad + '| ' + ' | '.join(self.inline(cell) for cell in rows[0]) + ' |')
        out.append(pad + '| ' + ' | '.join('---' for _ in rows[0]) + ' |')
        for row in rows[1:]:
            out.append(pad + '| ' + ' | '.join(self.inline(cell) for cell in row) + ' |')
        out.append('')
        return out

    def directive(self, name: str, arg: str, block: List[str], indent: int) -> List[str]:
        pad = ' ' * indent
        if name in ('code-block', 'code', 'sourcecode'):
            language = (arg or 'python').replace('python3', 'python').replace('py3', 'python')
            return _fence(block, indent, language)
        if name in ADMONITIONS:
            body = _dedent([b for b in block])
            converted = _Converter(self.ctx, self.index).convert('\n'.join(([arg] if arg else []) + body))
            lines = [pad + f'!!! {ADMONITIONS[name]}', '']
            lines.extend((pad + '    ' + b) if b.strip() else '' for b in converted.split('\n'))
            lines.append('')
            return lines
        if name in ('versionadded', 'versionchanged', 'deprecated'):
            # These name discord.py's versions, which mean nothing for bisim.py.
            return []
        if name == 'container':
            return self.operations(_dedent(block), indent)
        if name == 'describe':
            return self.operations([f'.. describe:: {arg}'] + [('    ' + b if b.strip() else '') for b in _dedent(block)], indent)
        if name == 'rubric':
            return [pad + f'**{self.inline(arg)}**', '']
        # Anything else: keep the text, drop the markup.
        body = _dedent(block)
        return [pad + self.inline(b) if b.strip() else '' for b in ([arg] if arg else []) + body]

    def operations(self, block: List[str], indent: int) -> List[str]:
        pad = ' ' * indent
        entries: List[Tuple[str, List[str]]] = []
        i = 0
        while i < len(block):
            match = DIRECTIVE_RE.match(block[i])
            if match and match.group('name') == 'describe':
                body, i = _collect_block(block, i + 1, _indent(block[i]))
                entries.append((match.group('arg').strip(), _dedent(body)))
                continue
            i += 1
        if not entries:
            return []
        out = [pad + '**Supported operations**', '']
        for expression, body in entries:
            text = ' '.join(self.inline(b.strip()) for b in body if b.strip())
            out.append(pad + f'`{expression}`')
            out.append(pad + f':   {text}')
            out.append('')
        return out


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip()) if line.strip() else 0


def _is_underline(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 3 and len(set(stripped)) == 1 and stripped[0] in '-~=^'


def _collect_block(lines: List[str], start: int, indent: int) -> Tuple[List[str], int]:
    """The lines after ``start`` that are blank or indented deeper than ``indent``."""
    block: List[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip() and _indent(line) <= indent:
            break
        block.append(line)
        i += 1
    while block and not block[-1].strip():
        block.pop()
        i -= 1
    return block, i


def _dedent(block: List[str]) -> List[str]:
    while block and not block[0].strip():
        block = block[1:]
    widths = [_indent(b) for b in block if b.strip()]
    cut = min(widths) if widths else 0
    return [b[cut:] if b.strip() else '' for b in block]


def _fence(block: List[str], indent: int, language: str) -> List[str]:
    pad = ' ' * indent
    body = _dedent(block)
    return [pad + f'```{language}', *[(pad + b) if b else '' for b in body], pad + '```', '']


def _mark_runtime(node: object, obj: griffe.Object) -> None:
    # Griffe treats both branches of ``if TYPE_CHECKING: ... else: ...`` as type-checking only, so the
    # classes bisim defines in the ``else`` branch (app_commands.Range, Transform, commands.Range) would
    # be left out of the public namespaces. They are what runs, so they are marked as such.
    parent = getattr(node, 'parent', None)
    if isinstance(parent, ast.If) and node in parent.orelse:
        obj.runtime = True


class RstDocstrings(griffe.Extension):
    """Rewrites every docstring in the bisim package from reStructuredText to Markdown."""

    def on_class_instance(self, *, node: object, cls: griffe.Class, **kwargs) -> None:
        _mark_runtime(node, cls)

    def on_function_instance(self, *, node: object, func: griffe.Function, **kwargs) -> None:
        _mark_runtime(node, func)

    def on_package(self, *, pkg: griffe.Module, **kwargs) -> None:
        if pkg.name != PACKAGE:
            return
        index = _Index(pkg)
        for obj in _walk_objects(pkg):
            if obj.docstring is not None and obj.docstring.value:
                obj.docstring.value = _Converter(obj, index).convert(obj.docstring.value)

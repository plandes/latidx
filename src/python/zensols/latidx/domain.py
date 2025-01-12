"""Application domain classes.

"""
__author__ = 'Paul Landes'

from typing import Tuple, Set, Dict, Any, Optional, ClassVar
from dataclasses import dataclass, field
import sys
from pathlib import Path
from io import TextIOBase
import textwrap as tw
from pylatexenc.latexwalker import (
    LatexNode, LatexMacroNode, LatexCharsNode, LatexGroupNode
)
from zensols.util import APIError
from zensols.config import Dictable
from zensols.persist import PersistableContainer, persisted


class LatidxError(APIError):
    """Thrown for any application level error.

    """
    pass


class ParseError(LatidxError):
    """Raised for Latex file parsing errors.

    """
    def __init__(self, path: Path, msg: str):
        super().__init__(f"{msg} in '{path}'")
        self.path = path


@dataclass
class LatexObject(PersistableContainer, Dictable):
    def __post_init__(self):
        super().__init__()


@dataclass
class UsePackage(LatexObject):
    """A parsed use of a Latex ``\\usepackage{<name>}``.

    """
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = {'name', 'span'}

    macro_node: LatexMacroNode = field(repr=False)
    """The node containing the macro."""

    options_node: LatexCharsNode = field(repr=False)
    """The node containing the package import options (if present)."""

    name_node: LatexCharsNode = field(repr=False)
    """The node with the name of the package to be imported."""

    @property
    def name(self) -> str:
        """The package to *use* (import)."""
        return self.name_node.chars

    @property
    def span(self) -> int:
        """The absolute 0-index character offset of the usepackage statement."""
        beg: int = self.macro_node.pos
        end: int = self.name_node.pos + self.name_node.len + 1
        return (beg, end)

    def __str__(self) -> str:
        return f'{self.name} @ {self.span}'

    def __repr__(self) -> str:
        opts: str = '' if self.options_node is None else self.options_node.chars
        macro: str = self.macro_node.latex_verbatim()
        return f'{macro}{opts}{{{self.name}}} @ {self.span}'


@dataclass
class NewCommand(LatexObject):
    """A parsed macro definition using ``\\{provide,new,renew}command``.

    """
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = {'name', 'span'}

    newcommand_node: LatexMacroNode = field(repr=False)
    """The ``\\newcommand`` node."""

    macro_node: LatexMacroNode = field(repr=False)
    """The node containing the macro."""

    arg_spec_nodes: Tuple[LatexNode, ...] = field(repr=False)
    """The node containing the package import options (if present)."""

    body_node: LatexGroupNode = field(repr=False)
    """The node with the name of the package to be imported."""

    definition: str = field()
    """The string definition of the command."""

    @property
    def name(self) -> str:
        """The name of the new macro defined."""
        return self.macro_node.macroname

    @property
    def span(self) -> Tuple[int, int]:
        """Get the 0-index character offset span of the definition."""
        begin: int = self.newcommand_node.pos
        end: int = self.body_node.pos + self.body_node.len
        return (begin, end)

    @property
    @persisted('_arg_spec', transient=True)
    def arg_spec(self) -> str:
        """The argument specification, which includes the argument count."""
        return ''.join(map(lambda n: n.latex_verbatim(), self.arg_spec_nodes))

    @property
    def body(self) -> Optional[str]:
        """The body of the macro definition."""
        if self.body_node is not None:
            return self.body_node.latex_verbatim()

    def write(self, depth: int = 0, writer: TextIOBase = sys.stdout):
        dct: Dict[str, Any] = self.asdict()
        dct['span'] = str(self.span)
        self._write_dict(dct, depth, writer)

    def __str__(self) -> str:
        return f'{self.name} @ {self.span}'

    def __repr__(self) -> str:
        body: str = self.body
        body = '' if body is None else body
        shortdef: str = f'\\{self.name}{self.arg_spec}{body}'.replace('\n', ' ')
        return tw.shorten(shortdef, 70) + f' @ {self.span}'

"""Application domain classes.

"""
__author__ = 'Paul Landes'

from typing import Tuple, Set, Optional, ClassVar
from dataclasses import dataclass, field
from pathlib import Path
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
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = {'name', 'char_offset'}

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
    def char_offset(self) -> int:
        """The absolute 0-index character offset of the usepackage statement."""
        return self.macro_node.pos

    def __str__(self) -> str:
        return f'{self.name} @ {self.char_offset}'

    def __repr__(self) -> str:
        opts: str = '' if self.options_node is None else self.options_node.chars
        macro: str = self.macro_node.latex_verbatim()
        return f'{macro}{opts}{{{self.name}}}@{self.char_offset}'


@dataclass
class NewCommand(LatexObject):
    """A parsed macro definition using ``\\{provide,new,renew}command``.

    """
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = {
        'name', 'char_offset', 'arg_spec', 'body'}

    macro_node: LatexMacroNode = field(repr=False)
    """The node containing the macro."""

    arg_spec_nodes: Tuple[LatexNode, ...] = field(repr=False)
    """The node containing the package import options (if present)."""

    body_node: Optional[LatexGroupNode] = field(repr=False)
    """The node with the name of the package to be imported."""

    @property
    def text(self) -> str:
        """The original text of the macro, which synthesized for now."""
        body: str = self.body
        body = '' if body is None else body
        return f'\\{self.name}{self.arg_spec}{body}'

    @property
    def name(self) -> str:
        """The name of the new macro defined."""
        return self.macro_node.macroname

    @property
    def char_offset(self) -> int:
        """The absolute 0-index character offset of the usepackage statement."""
        return self.macro_node.pos

    @property
    @persisted('_arg_spec')
    def arg_spec(self) -> str:
        """The argument specification, which includes the argument count."""
        return ''.join(map(lambda n: n.latex_verbatim(), self.arg_spec_nodes))

    @property
    def body(self) -> Optional[str]:
        """The body of the macro definition."""
        if self.body_node is not None:
            return self.body_node.latex_verbatim()

    def __str__(self) -> str:
        return f'{self.name} @ {self.char_offset}'

    def __repr__(self) -> str:
        s: str = self.text.replace('\n', ' ')
        return tw.shorten(s, 70) + f'@{self.char_offset}'

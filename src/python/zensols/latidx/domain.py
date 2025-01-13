"""Application domain classes.

"""
__author__ = 'Paul Landes'

from typing import Tuple, Set, Dict, Any, ClassVar
from dataclasses import dataclass, field
from abc import ABCMeta, abstractmethod
import sys
from pathlib import Path
from io import TextIOBase, StringIO
import textwrap as tw
from pylatexenc.latexwalker import (
    LatexNode, LatexMacroNode, LatexCharsNode, LatexGroupNode, LatexCommentNode
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
    """Any Latex data structure that is parsed, or composed of, parsed Latex.

    """
    def __post_init__(self):
        super().__init__()


@dataclass
class LatexSpannedObject(LatexObject, metaclass=ABCMeta):
    """Any Latex data structure that is parsed text from a Latex file.

    """
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = {'name', 'span'}

    @abstractmethod
    def _get_name(self) -> str:
        pass

    @abstractmethod
    def _get_span(self) -> Tuple[int, int]:
        pass

    @property
    def name(self) -> str:
        """The name of the object or text that makes it unique."""
        return self._get_name()

    @property
    def span(self) -> int:
        """The absolute 0-index character offset of the Latex statement."""
        return self._get_span()

    def __str__(self) -> str:
        return f'{self.name} @ {self.span}'

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class UsePackage(LatexSpannedObject):
    """A parsed use of a Latex ``\\usepackage{<name>}``.

    """
    macro_node: LatexMacroNode = field(repr=False)
    """The node containing the macro."""

    options_node: LatexCharsNode = field(repr=False)
    """The node containing the package import options (if present)."""

    name_node: LatexCharsNode = field(repr=False)
    """The node with the name of the package to be imported."""

    def _get_name(self) -> str:
        return self.name_node.chars

    def _get_span(self) -> Tuple[int, int]:
        beg: int = self.macro_node.pos
        end: int = self.name_node.pos + self.name_node.len + 1
        return (beg, end)

    def __repr__(self) -> str:
        opts: str = '' if self.options_node is None else self.options_node.chars
        macro: str = self.macro_node.latex_verbatim()
        return f'{macro}{opts}{{{self.name}}} @ {self.span}'


@dataclass
class NewCommand(LatexSpannedObject):
    """A parsed macro definition using ``\\{provide,new,renew}command``.

    """
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = \
        LatexSpannedObject._DICTABLE_ATTRIBUTES | {'macro_offset'}

    newcommand_node: LatexMacroNode = field(repr=False)
    """The ``\\newcommand`` node."""

    macro_node: LatexMacroNode = field(repr=False)
    """The node containing the macro."""

    arg_spec_nodes: Tuple[LatexNode, ...] = field(repr=False)
    """The node containing the package import options (if present)."""

    body_node: LatexGroupNode = field(repr=False)
    """The node with the name of the package to be imported."""

    comment_nodes: Tuple[LatexCommentNode, ...] = field(repr=False)
    """Any comment nodes that preceeded the ``newcommand`` statement."""

    definition: str = field()
    """The string definition of the command."""

    def _get_name(self) -> str:
        return self.macro_node.macroname

    def _get_span(self) -> Tuple[int, int]:
        begin: int = self.newcommand_node.pos
        end: int = self.body_node.pos + self.body_node.len
        return (begin, end)

    @property
    def macro_offset(self) -> int:
        return self.macro_node.pos

    @property
    @persisted('_arg_spec', transient=True)
    def arg_spec(self) -> str:
        """The argument specification, which includes the argument count."""
        return ''.join(map(lambda n: n.latex_verbatim(), self.arg_spec_nodes))

    @property
    def body(self) -> str:
        """The body of the macro definition."""
        return self.body_node.latex_verbatim()

    @property
    @persisted('_comment', transient=True)
    def comment(self) -> str:
        """The concatenated text from the parsed :obj:`comment_nodes`."""
        sio = StringIO()
        node: LatexCommentNode
        for node in self.comment_nodes:
            sio.write(node.comment.strip())
            sio.write(node.comment_post_space)
        return sio.getvalue().rstrip()

    def write(self, depth: int = 0, writer: TextIOBase = sys.stdout):
        dct: Dict[str, Any] = self.asdict()
        dct['span'] = str(self.span)
        dct['comment'] = '<' + self.comment.replace('\n', '\\n') + '>'
        self._write_dict(dct, depth, writer)

    def __repr__(self) -> str:
        body: str = self.body
        body = '' if body is None else body
        shortdef: str = f'\\{self.name}{self.arg_spec}{body}'.replace('\n', ' ')
        return tw.shorten(shortdef, 70) + f' @ {self.span}'

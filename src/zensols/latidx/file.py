"""Classes that represent text with parsable Latex content.

"""
__author__ = 'Paul Landes'

from typing import List, Tuple, Set, Dict, ClassVar
from dataclasses import dataclass, field
import logging
import sys
from pathlib import Path
from io import TextIOBase
from frozendict import frozendict
from pylatexenc.latexwalker import (
    LatexMacroNode, LatexGroupNode, LatexCharsNode, LatexCommentNode,
    LatexNode, LatexWalker
)
from pylatexenc.macrospec import LatexContextDb
from zensols.persist import persisted
from zensols.util import Failure
from . import LatexSpannedObject, ParseError, UsePackage, NewCommand

logger = logging.getLogger(__name__)


@dataclass
class LatexFile(LatexSpannedObject):
    """A Latex file (``.tex``, ``.sty``, etc) with parsed artifacts.

    """
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = {'usepackages', 'newcommands'}
    _PERSITABLE_PROPERTIES: ClassVar[Set[str]] = {'content'}
    _PERSITABLE_METHODS: ClassVar[Set[str]] = {'_get_package_objects'}

    path: Path = field()
    """The parsed latex ``.tex`` or ``.sty`` file."""

    def __post_init__(self):
        super().__post_init__()
        self._fails: List[Failure] = []

    def _get_name(self) -> str:
        return self.path.name

    def _get_span(self) -> Tuple[int, int]:
        return (0, len(self.content))

    @property
    @persisted('_content')
    def content(self) -> str:
        """The content of the Latex file :obj:`path`."""
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'reading: {self.path}')
        with open(self.path) as f:
            return f.read()

    @property
    @persisted('_walker', transient=True)
    def walker(self) -> LatexWalker:
        """Iterates over parsed Latex artifacts (such as macros)."""
        self._db = LatexContextDb()
        return LatexWalker(self.content, latex_context=self._db)

    @property
    def db(self) -> LatexContextDb:
        self.walker
        return self._db

    def _parse_package(self, n: LatexMacroNode, nodes: List[LatexNode],
                       nix: int) -> UsePackage:
        def get_char_node(n: LatexGroupNode) -> LatexCharsNode:
            for i in range(5):
                # iterate past embedded macros in []s until we find the group
                # nodes
                if isinstance(n, LatexGroupNode):
                    break
                n = nodes[nix + i]
            if not isinstance(n, LatexGroupNode):
                raise ParseError(self.path, f'Expecting group node: {n}')
            cn: LatexCharsNode = n.nodelist[0]
            if not isinstance(cn, LatexCharsNode):
                raise ParseError(self.path, f'Expecting char node: {cn}')
            return cn

        nn: LatexNode = nodes[nix + 1]
        options: LatexCharsNode = None
        name: LatexCharsNode
        if isinstance(nn, LatexGroupNode):
            name = get_char_node(nn)
        elif isinstance(nn, LatexCharsNode):
            options = nn
            name = get_char_node(nodes[nix + 2])
        else:
            raise ParseError(
                f"Unknown usepackage syntax '{n}'", self.path)
        return UsePackage(n, options, name)

    def _parse_command(self, n: LatexMacroNode, nodes: List[LatexNode],
                       nix: int) -> UsePackage:
        def get_macro_node(n: LatexGroupNode) -> LatexMacroNode:
            if not isinstance(n, LatexGroupNode):
                raise ParseError(self.path, f'Expecting group node: {n}')
            mn: LatexMacroNode = n.nodelist[0]
            if not isinstance(mn, LatexMacroNode):
                raise ParseError(self.path, f'Expecting char node: {mn}')
            return mn

        def get_char_nodes(nix: int) -> Tuple[int, List[LatexCharsNode]]:
            cnodes: List[LatexCharsNode] = []
            while nix < nlen:
                n = nodes[nix]
                if not isinstance(n, LatexGroupNode) and \
                   not isinstance(n, LatexCommentNode):
                    cnodes.append(n)
                else:
                    break
                nix += 1
            return nix, cnodes

        def get_comment_nodes():
            cnodes: List[LatexCommentNode] = []
            cnix: int = nix - 1
            while cnix > 0:
                cn: LatexNode = nodes[cnix]
                if isinstance(cn, LatexCommentNode):
                    cnodes.append(cn)
                else:
                    break
                cnix -= 1
            cnodes.reverse()
            return cnodes

        nlen: int = len(nodes)
        nn: LatexNode = nodes[nix + 1]
        if isinstance(nn, LatexGroupNode):
            # most cases start with a group node that has the macro in the first
            # of the arglist; only comments are supported for these nodes
            mn: LatexMacroNode = get_macro_node(nn)
            nn: LatexGroupNode = nodes[nix]
            bnix: int
            cnodes: List[LatexCharsNode]
            bnix, cnodes = get_char_nodes(nix + 2)
            bn: LatexGroupNode = nodes[bnix]
            if not isinstance(bn, LatexGroupNode):
                bn = None
            nc = NewCommand(nn, mn, cnodes, bn, None, None)
            span: Tuple[int, int] = nc.span
            nc.definition = self.content[span[0]:span[1]]
            nc.comment_nodes = get_comment_nodes()
            return nc
        else:
            # strange syntax commands are in the minority
            if logger.isEnabledFor(logging.INFO):
                s: str = f'{n.latex_verbatim()}{nn.latex_verbatim()} at {n.pos}'
                logger.info(f'Un-parsable macro: {s} in {self.path}')

    @persisted('_package_objects')
    def _get_package_objects(self) -> \
            Tuple[Dict[str, UsePackage], Dict[str, NewCommand]]:
        """Parse ``usepackage`` and ``newcommand``."""
        ups: Dict[str, UsePackage] = {}
        ncs: Dict[str, NewCommand] = {}
        nodes: List[LatexNode] = self.walker.get_latex_nodes(pos=0)[0]
        nix: int
        n: LatexNode
        for nix, n in enumerate(nodes):
            if isinstance(n, LatexMacroNode):
                up: UsePackage = None
                if n.macroname == 'usepackage':
                    try:
                        up = self._parse_package(n, nodes, nix)
                    except Exception as e:
                        self._fails.append(Failure(e))
                if up is not None:
                    prev: UsePackage = ups.get(up.name)
                    if prev is not None:
                        if logger.isEnabledFor(logging.INFO):
                            logger.info(f"replacing previously <{prev}> <{up}>")
                    ups[up.name] = up
                elif n.macroname.endswith('command'):
                    cmd: NewCommand = self._parse_command(n, nodes, nix)
                    if cmd is not None:
                        ncs[cmd.name] = cmd
        return frozendict(ups), frozendict(ncs)

    @property
    def usepackages(self) -> Dict[str, UsePackage]:
        """Get the ``usepackage`` declarations in the file."""
        return self._get_package_objects()[0]

    @property
    def newcommands(self) -> Dict[str, NewCommand]:
        """Get the ``usepackage`` declarations in the file."""
        return self._get_package_objects()[1]

    @property
    def failures(self) -> Tuple[Failure, ...]:
        """Write parse failures."""
        return tuple(self._fails)

    def write(self, depth: int = 0, writer: TextIOBase = sys.stdout,
              include_path: bool = True):
        if include_path:
            self._write_line(f'path: {self.path}', depth, writer)
        self._write_line('usepackages:', depth, writer)
        for pkg in self.usepackages.values():
            self._write_line(str(pkg), depth + 1, writer)
        self._write_line('newcommands:', depth, writer)
        for cmd in self.newcommands.values():
            self._write_line(str(cmd), depth + 1, writer)
        if len(self._fails) > 0:
            self._write_line('failures:', depth, writer)
            for fail in self._fails:
                self._write_line(fail, depth + 1, writer)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'{self.path}: {len(self.usepackages)}'


@dataclass
class NewCommandLocation(LatexSpannedObject):
    """A pairing of commands and the files they live in.

    """
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = {}

    command: NewCommand = field()
    """The command foiund in :obj:`file`."""

    file: LatexFile = field()
    """The file that contains :obj:`command`."""

    def _get_name(self) -> str:
        return self.command._get_name()

    def _get_span(self) -> Tuple[int, int]:
        return self.command._get_span()

    def write(self, depth: int = 0, writer: TextIOBase = sys.stdout):
        self._write_line('command:', depth, writer)
        self._write_object(self.command, depth + 1, writer)
        self._write_line(f'file: {self.file.path}', depth, writer)

    def __str__(self) -> str:
        return f'{self.command}: {self.file}'

    def __repr__(self) -> str:
        return f'{repr(self.command)} in {repr(self.file)}'

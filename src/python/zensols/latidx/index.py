"""Classes used to parse and index LaTeX files.

"""
from __future__ import annotations
__author__ = 'Paul Landes'
from typing import (
    List, Tuple, Set, Iterable, Dict, Any, Optional, Union, ClassVar
)
from dataclasses import dataclass, field
import logging
import sys
from itertools import chain
from collections import OrderedDict
from pathlib import Path
from io import TextIOBase
from frozendict import frozendict
from pylatexenc.latexwalker import (
    LatexMacroNode, LatexGroupNode, LatexCharsNode, LatexCommentNode,
    LatexNode, LatexWalker
)
from pylatexenc.macrospec import LatexContextDb
from zensols.config import Dictable
from zensols.persist import persisted, Primeable
from zensols.util import Failure
from . import LatidxError, LatexObject, ParseError, UsePackage, NewCommand

logger = logging.getLogger(__name__)


@dataclass
class LatexFile(LatexObject):
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

    @property
    def name(self) -> str:
        """The base name of :obj:`path`."""
        return self.path.name

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

        def post_create(nc: NewCommand):
            span: Tuple[int, int] = nc.span
            nc.definition = self.content[span[0]:span[1]]

        nlen: int = len(nodes)
        nn: LatexNode = nodes[nix + 1]
        if 0:
            for x in nodes:
                print(x)
            print('_' * 40)
        if isinstance(nn, LatexGroupNode):
            # most cases start with a group node that has the macro in the first
            # of the arglist; only comments are supported for these nodes
            mn: LatexMacroNode = get_macro_node(nn)
            nn: LatexGroupNode = nodes[nix]
            nix: int
            cnodes: List[LatexCharsNode]
            nix, cnodes = get_char_nodes(nix + 2)
            bn = nodes[nix]
            if not isinstance(bn, LatexGroupNode):
                bn = None
            nc = NewCommand(nn, mn, cnodes, bn, None)
            post_create(nc)
            return nc
        elif False and isinstance(nn, LatexMacroNode):  # later if needed
            # newcommand that use more traditional TeX syntax
            bn: LatexNode = nodes[nix + 2]
            if not isinstance(bn, LatexGroupNode):
                bn = None
            nc = NewCommand(nn, nn, (), bn, None)
            post_create(nc)
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
class NewCommandLocation(LatexObject):
    """A pairing of commands and the files they live in.

    """
    command: NewCommand = field()
    """The command foiund in :obj:`file`."""

    file: LatexFile = field()
    """The file that contains :obj:`command`."""

    def write(self, depth: int = 0, writer: TextIOBase = sys.stdout):
        self._write_line('command:', depth, writer)
        self._write_object(self.command, depth + 1, writer)
        self._write_line(f'file: {self.file.path}', depth, writer)

    def __str__(self) -> str:
        return f'{self.command}: {self.file}'

    def __repr__(self) -> str:
        return f'{repr(self.command)} in {repr(self.file)}'


@dataclass
class LatexDependency(LatexObject):
    """An import relationship given by Latex ``usepackage``.

    """
    _DICTABLE_WRITABLE_DESCENDANTS: ClassVar[bool] = True

    source: Union[LatexFile, str] = field()
    """"The source file that contains the import statement or the string
    ``root`` if the root of the aggregation of dependnecies.

    """
    targets: Optional[Dict[str, LatexDependency]] = field()
    """The imported files from :obj:`source`."""

    def get_files(self) -> Iterable[LatexFile]:
        """Return all target files recursively."""
        children: Iterable[LatexFile] = chain.from_iterable(
            map(lambda t: t.get_files(),
                filter(lambda x: x is not None, self.targets.values())))
        if self.source == 'root':
            return children
        else:
            return chain.from_iterable(((self.source,), children))

    @property
    @persisted('_base_dir', transient=True)
    def base_dir(self) -> Path:
        if isinstance(self.source, str):
            return None
        files = sorted(map(lambda f: f.path, self.get_files()),
                       key=lambda p: len(p.parts))
        if len(files) > 0:
            base = self.source.path
            for rel in files:
                rel = rel.absolute()
                while len(rel.parts) > 1:
                    if base.is_relative_to(rel):
                        base = rel
                        break
                    rel = rel.parent
                base = rel
            return base

    @property
    @persisted('_orphans', transient=True)
    def orphans(self) -> Tuple[str, ...]:
        """The target Latex packages that were imported by not found.  This will
        typically include installed base packages (i.e. ``hyperref``).

        """
        return tuple(map(lambda t: t[0],
                         filter(lambda t: t[1] is None, self.targets.items())))

    def _get_relative_dir(self, base_dir: Path = None):
        base_dir = self.base_dir if base_dir is None else base_dir
        if base_dir is not None:
            source_path: Path = self.source.path.absolute()
            return source_path.relative_to(base_dir)

    def _get_flat_tree(self, base_dir: Path) -> Dict[str, Any]:
        dct = OrderedDict()
        tname: str
        targ: LatexDependency
        for tname, targ in sorted(self.targets.items(), key=lambda t: t[0]):
            key = tname
            childs = {}
            if targ is not None:
                if base_dir is not None:
                    key = str(targ._get_relative_dir(base_dir))
                childs = targ._get_flat_tree(base_dir)
            dct[key] = childs
        return dct

    def tree(self, include_relative_path: bool = False) -> Dict[str, Any]:
        base_dir: Path = None
        if include_relative_path:
            base_dir = self.base_dir
        if base_dir is None:
            key = str(self.source)
        else:
            key = str(self._get_relative_dir(base_dir))
        dct = {key: self._get_flat_tree(base_dir)}
        return dct

    def write(self, depth: int = 0, writer: TextIOBase = sys.stdout,
              include_relative_path: bool = False, base_dir: Path = None):
        source_str: str = str(self.source)
        if include_relative_path:
            source_path: Path = self.source.path.absolute()
            base_dir = self.base_dir if base_dir is None else base_dir
            rel_path: Path = source_path.relative_to(base_dir)
            if rel_path != Path('.'):
                source_str = str(rel_path)
        orphs = self.orphans
        self._write_line(f'{source_str}: ({len(self.targets)})',
                         depth, writer)
        if len(orphs) > 0:
            ostr: str = ', '.join(orphs)
            self._write_line(f'orphans: {ostr}', depth + 1, writer)
        for targ in self.targets.values():
            if targ is not None:
                assert isinstance(targ, LatexDependency)
                targ.write(
                    depth + 1,
                    writer=writer,
                    include_relative_path=include_relative_path,
                    base_dir=base_dir)

    def __getitem__(self, target_name: str) -> LatexDependency:
        return self.targets[target_name]

    def __contains__(self, target_name: str) -> bool:
        return target_name in self.targets


@dataclass
class LatexProject(LatexObject, Primeable):
    """A collection of dependencies of a set of files used in a LaTeX
    compliation process.

    """
    _DICTABLE_WRITABLE_DESCENDANTS: ClassVar[bool] = True
    _DICTABLE_ATTRIBUTES: ClassVar[Set[str]] = {
        'dependencies', 'command_locations_by_name'}
    _PERSITABLE_PROPERTIES: ClassVar[Set[str]] = {'dependencies'}

    files: Tuple[Union[LatexFile, Path], ...] = field()
    """The files to parse or those that have already been parsed.  These are all
    :class:`LatexFile` instances after this object is instantiated.

    """
    def __post_init__(self):
        super().__post_init__()
        self.files = tuple(map(
            lambda f: LatexFile(f) if isinstance(f, Path) else f,
            self.files))

    @property
    @persisted('_files_by_name', transient=True)
    def files_by_name(self) -> Dict[str, LatexFile]:
        """The files as key names and :obj:`LatexFile` instances as values."""
        return frozendict(map(lambda f: (f.name, f), self.files))

    @property
    @persisted('_command_locations_by_name', transient=True)
    def command_locations_by_name(self) -> Dict[str, NewCommandLocation]:
        """All commands across all Latex files by command name."""
        cmds: Dict[str, NewCommand] = {}
        latfile: LatexFile
        for latfile in self.files_by_name.values():
            cmd: NewCommand
            for cmd in latfile.newcommands.values():
                cmds[cmd.name] = NewCommandLocation(cmd, latfile)
        return frozendict(cmds)

    @property
    @persisted('_command_locations', transient=True)
    def command_locations(self) -> Tuple[NewCommandLocation, ...]:
        """All commands across all Latex files."""
        return tuple(sorted(self.command_locations_by_name.values(),
                            key=lambda cl: cl.command.name))

    def _get_dependencies(self, src: LatexFile, deps) -> \
            Dict[str, Dict[str, Any]]:
        """Recursively parse dependencies in ``src`` sharing all dependencies in
        ``deps``.

        """
        dep = deps.get(src.name)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'desc deps: {src.name} -> {dep}')
        if dep is None:
            src_deps = {}
            dep = LatexDependency(src, src_deps)
            deps[src.name] = dep
            files: Dict[str, LatexFile] = self.files_by_name
            for targ_up in tuple(src.usepackages.values()):
                targ_sty: str = targ_up.name + '.sty'
                targ: Optional[LatexFile] = files.get(targ_sty)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f'{src} -> ({targ_up}) {targ}')
                if targ is None:
                    src_deps[targ_sty] = None
                else:
                    src_deps[targ_sty] = self._get_dependencies(targ, deps)
        return dep

    @property
    @persisted('_dependencies')
    def dependencies(self) -> Dict[str, Dict[str, Any]]:
        """A nested directory of string file names and their recursive
        ``usepackage`` includes as children.

        """
        deps: Dict[str, LatexFile] = {}
        for lf in self.files:
            self._get_dependencies(lf, deps)
        return LatexDependency('root', frozendict(deps))

    @property
    @persisted('_dependency_files', transient=True)
    def dependency_files(self) -> Tuple[LatexFile, ...]:
        """The parsed latex files in the project."""
        return tuple(map(lambda n: self.files_by_name[n],
                         self.dependencies.targets.keys()))

    def prime(self):
        self.dependencies

    def write(self, depth: int = 0, writer: TextIOBase = sys.stdout):
        self.prime()
        super().write(depth, writer)

    def write_files(self, depth: int = 0, writer: TextIOBase = sys.stdout):
        files: Iterable[LatexFile] = self.files_by_name.values()
        for lf in sorted(files, key=lambda t: t.path.name):
            self._write_line(f'{lf.path}:', depth, writer)
            lf.write(depth + 1, writer, include_path=False)

    def write_command_locations(self, depth: int = 0,
                                writer: TextIOBase = sys.stdout):
        for cl in self.command_locations:
            self._write_line(f'{cl.command.name}', depth, writer)
            self._write_object(cl, depth + 1, writer)


@dataclass
class LatexIndexer(Dictable):
    """Indexes and parses Latex files.  Candidate files refer to files we
    actually consider for parsing.

    """
    candidate_extensions: Set[str] = field()
    """The files extensions of files to parse (i.e. ``.tex``, ``.sty``)."""

    recurse_dirs: bool = field()
    """Whether to recursively descend directories in search for candidates."""

    def _get_candidate_files(self, path: Path) -> Iterable[Path]:
        """Return an iterable of paths to parse."""
        if path.is_file():
            if path.suffix[1:] in self.candidate_extensions:
                return (path,)
            else:
                return ()
        elif path.is_dir():
            paths: Iterable[Path] = path.iterdir()
            if not self.recurse_dirs:
                paths = filter(lambda p: not p.is_dir(), paths)
            return chain.from_iterable(
                map(self._get_candidate_files, paths))
        else:
            raise LatidxError(f'No such file or directory: {path}')

    def create_project(self, paths: Tuple[Path, ...]) -> LatexProject:
        """Create a latex project from the file ``paths`` of ``.tex`` and
        ``.sty`` files.

        """
        paths = chain.from_iterable(map(self._get_candidate_files, paths))
        return LatexProject(tuple(paths))

"""Classes used to parse and index LaTeX files.

"""
from __future__ import annotations
__author__ = 'Paul Landes'
from typing import Tuple, Set, Iterable, Dict, Any, Optional, Union, ClassVar
from dataclasses import dataclass, field
import logging
import sys
from itertools import chain
from collections import OrderedDict
from pathlib import Path
from io import TextIOBase
from frozendict import frozendict
from zensols.config import Dictable
from zensols.persist import persisted, Primeable
from . import (
    LatidxError, LatexObject, UsePackage, NewCommand,
    LatexFile, NewCommandLocation
)

logger = logging.getLogger(__name__)


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
            targ_up: UsePackage
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

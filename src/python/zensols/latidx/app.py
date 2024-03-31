"""Parse and index Latex files.

"""
__author__ = 'Paul Landes'

from typing import Iterable, Optional, Union
from dataclasses import dataclass, field
from enum import Enum, auto
import os
import logging
import json
import yaml
from pathlib import Path
from zensols.cli import LogConfigurator, ApplicationError
from . import LatexDependency, LatexIndexer

logger = logging.getLogger(__name__)


class _Format(Enum):
    txt = auto()
    json = auto()
    yaml = auto()
    list = auto()


@dataclass
class Application(object):
    """Parse and index Latex files.

    """
    indexer: LatexIndexer = field()
    """The file indexer."""

    log_config: LogConfigurator = field()
    """Used to update logging levels based on the ran action."""

    def _set_level(self, level: int):
        self.log_config.level = level
        self.log_config()

    def _to_paths(self, path: Union[str, Path]) -> Iterable[Path]:
        """Create a path sequence from a string, path or sequence of paths."""
        if path is None:
            path = ()
        if isinstance(path, Path):
            path = (path,)
        elif isinstance(path, str):
            path = tuple(map(Path, path.split(os.pathsep)))
        return path

    def _resolve_source(self, dep: LatexDependency, name: str) -> Optional[str]:
        if name in dep:
            return name
        else:
            path = Path(name)
            # match on more specific path
            targ: LatexDependency
            for targ in dep.targets.values():
                if targ.source.path == path:
                    return targ.source.name
            # match on path file name to be robust
            for targ in dep.targets.values():
                if targ.source.path.name == path.name:
                    return targ.source.name
        raise ApplicationError(f'No source found: {name}')

    def dump_dependencies(self, tex_path: str, source: str = None,
                          output_format: _Format = _Format.txt):
        """List dependencies.

        :param tex_path: a path separated (':' on Linux) list of files or
                         directories

        :param source: the source latex file dependency to print

        :param output_format: the output format

        """
        self._set_level(logging.WARNING)
        proj = self.indexer.create_project(self._to_paths(tex_path))
        dep: LatexDependency = proj.dependencies
        if source is not None:
            source = self._resolve_source(dep, source)
            dep = dep[source]
        if output_format == _Format.list:
            # if asking for just file list, default to target files
            print('\n'.join(set(map(lambda f: str(f.path.absolute()),
                                    dep.get_files()))))
        else:
            tree = dep.tree()
            if output_format == _Format.txt:
                from asciitree import LeftAligned
                tree_fmt = LeftAligned()
                print(tree_fmt(tree))
            elif output_format == _Format.json:
                print(json.dumps(tree, indent=4))
            else:
                raise ApplicationError(
                    f'Format not supported: {output_format.name}')

    def dump_files(self, tex_path: str, output_format: _Format = _Format.txt):
        """List dependencies.

        :param tex_path: a path separated (':' on Linux) list of files or
                         directories

        :param output_format: the output format

        """
        def files_by_name():
            files = {}
            for dct in proj.asflatdict()['files']:
                path = dct.pop('path')
                files[path] = dct
            return files

        self._set_level(logging.WARNING)
        proj = self.indexer.create_project(self._to_paths(tex_path))
        if output_format == _Format.txt:
            proj.write_files()
        if output_format == _Format.json:
            print(json.dumps(files_by_name(), indent=4))
        if output_format == _Format.yaml:
            print(yaml.dump(files_by_name()))
        if output_format == _Format.list:
            print('\n'.join(map(lambda f: str(f.path), proj.files)))

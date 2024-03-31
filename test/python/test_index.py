from typing import Dict, Any
import sys
import logging
import unittest
import json
from pathlib import Path
from zensols.latidx import (
    LatidxError, UsePackage, LatexFile, LatexDependency,
    LatexProject, LatexIndexer, ApplicationFactory
)


if 0:
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)


class TestApplication(unittest.TestCase):
    def setUp(self):
        self.idx: LatexIndexer = ApplicationFactory.get_indexer()
        self.maxDiff = sys.maxsize

    def _create_project(self) -> LatexProject:
        path = Path('test-resources/proj')
        return self.idx.create_project((path,))

    def test_bad_path(self):
        path = Path('nada-dir')
        with self.assertRaisesRegex(LatidxError, r'^No such file or'):
            self.idx.create_project((path,))

    def test_dep_structure(self):
        proj: LatexProject = self._create_project()
        self.assertTrue(isinstance(proj, LatexProject))

        dep: LatexDependency = proj.dependencies
        self.assertTrue(isinstance(dep, LatexDependency))
        self.assertEqual('root', dep.source)
        self.assertEqual((), dep.orphans)
        self.assertEqual(2, len(dep.targets))
        self.assertEqual(set('root.tex child.sty'.split()),
                         set(dep.targets.keys()))

        root = dep['root.tex']
        self.assertTrue(isinstance(root, LatexDependency))
        self.assertTrue(isinstance(root.source, LatexFile))
        self.assertTrue(isinstance(root.source.path, Path))
        self.assertEqual(Path('test-resources/proj/root.tex'), root.source.path)
        self.assertEqual('root.tex', root.source.name)
        self.assertEqual(2, len(root.source.usepackages))
        self.assertEqual(set('child orphan'.split()),
                         set(root.source.usepackages.keys()))

        child_pkg: UsePackage = root.source.usepackages['child']
        self.assertEqual(16, child_pkg.char_offset)

        self.assertEqual(id(dep['child.sty']), id(root['child.sty']))

    def test_dep_json(self):
        WRITE: bool = 0
        cmp_file = Path('test-resources/deps.json')
        proj: LatexProject = self._create_project()
        dep: LatexDependency = proj.dependencies
        if WRITE:
            with open(cmp_file, 'w') as f:
                f.write(dep.asjson(indent=4))
        with open(cmp_file) as f:
            should: Dict[str, Any] = json.load(f)
        self.assertEqual(should, dep.asflatdict())

    def test_dep(self):
        proj: LatexProject = self._create_project()
        self.assertEqual(set('child.sty root.tex'.split()),
                         set(map(lambda d: d.name, proj.dependency_files)))
        self.assertEqual(set([Path('test-resources/proj/root.tex'),
                              Path('test-resources/proj/child.sty')]),
                         set(map(lambda d: d.path, proj.dependency_files)))

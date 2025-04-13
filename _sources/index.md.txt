# Parse and index LaTeX files

[![PyPI][pypi-badge]][pypi-link]
[![Python 3.11][python311-badge]][python311-link]
[![Build Status][build-badge]][build-link]

This library parses and indexes includes and macros in latex files.  This
package can be [used](#usage) as a command line tool or an API.  The following
are parsed and reported:

* Package imports using `\usepackage` to create dependency trees.
* Macro defined with `\newcommand`.


## Documentation

See the [full documentation](https://plandes.github.io/latidx/index.html).
The [API reference](https://plandes.github.io/latidx/api.html) is also
available.


## Obtaining

The library can be installed with pip from the [pypi] repository:
```bash
pip3 install zensols.latidx
```

## Usage

This package can be used as a command line tool or an API.


### Command Line

To get the dependencies of a LaTeX project (in this case using the test case
project for the example), use

```bash
latidx deps test-resources/proj
```

Output:
```
root
 +-- child.sty
 +-- root.tex
     +-- child.sty
     +-- orphan.sty
```

### API

```python
>>> from pathlib import Path
from pathlib import Path
>>> from zensols.latidx import LatexIndexer, ApplicationFactory
from zensols.latidx import LatexIndexer, ApplicationFactory
>>> idx: LatexIndexer = ApplicationFactory.get_indexer()
idx: LatexIndexer = ApplicationFactory.get_indexer()
>>> proj = idx.create_project((Path('test-resources') / 'proj',))
proj = idx.create_project((Path('test-resources') / 'proj',))
>>> proj.write()
proj.write()
files:
    path: test-resources/proj/root.tex
    usepackages:
        child @ 16
        orphan @ 46
    newcommands:
        rootcmd @ 90
...
```


## Changelog

An extensive changelog is available [here](CHANGELOG.md).


## License

[MIT License](LICENSE.md)

Copyright (c) 2024 - 2025 Paul Landes


<!-- links -->
[pypi]: https://pypi.org/project/zensols.latidx/
[pypi-link]: https://pypi.python.org/pypi/zensols.latidx
[pypi-badge]: https://img.shields.io/pypi/v/zensols.latidx.svg
[python311-badge]: https://img.shields.io/badge/python-3.11-blue.svg
[python311-link]: https://www.python.org/downloads/release/python-3110
[build-badge]: https://github.com/plandes/latidx/workflows/CI/badge.svg
[build-link]: https://github.com/plandes/latidx/actions

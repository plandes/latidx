"""Command line entry point to the application.

"""
__author__ = 'Paul Landes'

from typing import List, Any, Dict
import sys
from zensols.cli import ActionResult, CliHarness
from zensols.cli import ApplicationFactory as CliApplicationFactory
from . import LatexIndexer


class ApplicationFactory(CliApplicationFactory):
    def __init__(self, *args, **kwargs):
        kwargs['package_resource'] = 'zensols.latidx'
        super().__init__(*args, **kwargs)

    @classmethod
    def get_indexer(self) -> LatexIndexer:
        """Get the indexer."""
        harness: CliHarness = ApplicationFactory.create_harness()
        return harness['ltx_indexer']


def main(args: List[str] = sys.argv, **kwargs: Dict[str, Any]) -> ActionResult:
    harness: CliHarness = ApplicationFactory.create_harness(relocate=False)
    harness.invoke(args, **kwargs)

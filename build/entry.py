"""PyInstaller entry point: a thin wrapper around the package's ``main``.

Kept separate from the package so the frozen binary has a single, import-graph
root that PyInstaller can analyze.
"""

import sys

from claude_wrapper.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

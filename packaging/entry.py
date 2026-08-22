"""Frozen-build entry point.

PyInstaller runs its entry script as a top-level module, with no parent
package, so `rpncalc/__main__.py` cannot be it: the relative imports in there
have nothing to be relative to. This imports the package properly instead.
"""

from rpncalc.__main__ import main

raise SystemExit(main())

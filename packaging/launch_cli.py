"""PyInstaller entry script for rita.exe (console CLI + module host).

Same reason as launch_gui.py: rita/__main__.py uses relative imports, so
it must be imported as part of the package, not run as the raw script.
"""

import sys

from rita.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

"""PyInstaller entry script for RitaApp.exe.

A package module can't be the Analysis script directly: run as __main__ it
has no parent package, so its relative imports crash at startup. This shim
imports the package absolutely and hands over.
"""

import sys

from rita.gui.app import main

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Ultimo Metro · punto di avvio.  python3 app.py  (oppure i file run_*.bat / .command / .sh)"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from um.server import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

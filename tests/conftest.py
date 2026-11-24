"""Test setup: load the integration's modules without Home Assistant.

`api.py`, `util.py` and `const.py` do not depend on Home Assistant. A stub
package keeps the integration's `__init__.py` (which does) from being run.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

PACKAGE = "coop_schweiz"
ROOT = Path(__file__).resolve().parents[1] / "custom_components" / PACKAGE

if PACKAGE not in sys.modules:
    stub = types.ModuleType(PACKAGE)
    stub.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = stub

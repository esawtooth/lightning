"""Compatibility package exposing :mod:`lightning_core.vextir_os`."""

import importlib
import pkgutil
import sys
from pathlib import Path

# Ensure the lightning_core package is importable
root = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(root))

from lightning_core import vextir_os as _vextir_os

# Re-export public attributes
for name in getattr(_vextir_os, "__all__", []):
    globals()[name] = getattr(_vextir_os, name)

__all__ = getattr(_vextir_os, "__all__", [])

# Lazily import submodules so old import paths continue to work
for finder, modname, ispkg in pkgutil.iter_modules(_vextir_os.__path__):
    if modname.startswith("_") or modname == "setup":
        continue
    module = importlib.import_module(f"lightning_core.vextir_os.{modname}")
    globals()[modname] = module
    sys.modules[f"{__name__}.{modname}"] = module

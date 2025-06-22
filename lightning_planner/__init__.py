"""Compatibility package exposing :mod:`lightning_core.planner`."""

import importlib
import pkgutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(root))

from lightning_core import planner as _planner

# Re-export public attributes
for name in getattr(_planner, "__all__", []):
    globals()[name] = getattr(_planner, name)

__all__ = getattr(_planner, "__all__", [])

for finder, modname, ispkg in pkgutil.iter_modules(_planner.__path__):
    if modname.startswith("_"):
        continue
    module = importlib.import_module(f"lightning_core.planner.{modname}")
    globals()[modname] = module
    sys.modules[f"{__name__}.{modname}"] = module

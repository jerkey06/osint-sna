"""Import plugin registry.

Every module in this package that sets PLUGIN = SomeImporterClass at module
level is auto-discovered and registered under its .platform name. To add a
new platform, drop a new plugins/whatever.py implementing Importer — no
changes needed anywhere else.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from .base import Connection, Importer

__all__ = ["Connection", "Importer", "get_importer", "available_platforms"]

_REGISTRY: dict[str, Importer] = {}


def _discover():
    if _REGISTRY:
        return
    package_dir = Path(__file__).parent
    for mod_info in pkgutil.iter_modules([str(package_dir)]):
        if mod_info.name in ("base",):
            continue
        module = importlib.import_module(f"{__name__}.{mod_info.name}")
        importer_cls = getattr(module, "PLUGIN", None)
        if importer_cls is None:
            continue
        instance = importer_cls()
        _REGISTRY[instance.platform] = instance


def get_importer(platform: str) -> Importer:
    _discover()
    try:
        return _REGISTRY[platform]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) or "(none found)"
        raise KeyError(f"Unknown platform '{platform}'. Available: {available}") from None


def available_platforms() -> list[str]:
    _discover()
    return sorted(_REGISTRY)

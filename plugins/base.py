"""Base interface every import plugin implements.

A plugin turns a platform's official data export (or, for the generic
plugin, an arbitrary CSV) into a list of Connection objects. osint_sna.py
takes it from there: it doesn't know anything about JSON, CSV or archive
formats, only about Connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Connection:
    """One connection discovered by an importer, before it becomes a vault note."""

    handle: str
    name: str = ""
    relationship: str = "observed_public"
    first_observed: str | None = None
    extra: dict = field(default_factory=dict)


class Importer:
    """Subclass this and set PLUGIN = YourClass at module level to register it."""

    platform: str = ""
    description: str = ""

    def parse(self, export_dir: Path, **options) -> list[Connection]:
        """Return the connections found under export_dir.

        Raise FileNotFoundError / ValueError with a user-facing message on
        anything that stops the import (missing files, bad columns, etc).
        """
        raise NotImplementedError

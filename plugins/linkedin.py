"""Official LinkedIn data export: Connections.csv.

LinkedIn -> Settings & Privacy -> Data privacy -> Get a copy of your data ->
"Connections" -> request archive, then unzip it.

LinkedIn connections are always mutual (both sides accepted the invite), so
every connection is recorded with relationship="mutual". The export has no
"handle" concept either — the closest thing is the public profile slug in
the URL column, which is what we use as the note's identifier.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from .base import Connection, Importer

_PROFILE_SLUG_RE = re.compile(r"/in/([^/?]+)")
_DATE_FORMATS = ("%d %b %Y", "%d-%b-%y", "%Y-%m-%d", "%m/%d/%y")


def _parse_connected_on(value: str) -> str:
    value = (value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return date.today().isoformat()


def _read_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()
    # LinkedIn prefixes the CSV with a few "Notes:" lines before the real header.
    header_idx = next(
        (i for i, line in enumerate(lines) if "first name" in line.lower() and "last name" in line.lower()),
        0,
    )
    return list(csv.DictReader(lines[header_idx:]))


class LinkedInImporter(Importer):
    platform = "linkedin"
    description = "Official LinkedIn export (Connections.csv)"

    def parse(self, export_dir: Path, **options) -> list[Connection]:
        csv_path = next(export_dir.rglob("Connections.csv"), None)
        if not csv_path:
            raise FileNotFoundError(
                f"Couldn't find Connections.csv under {export_dir}. Request it from "
                "LinkedIn: Settings & Privacy -> Data privacy -> Get a copy of your data -> Connections."
            )

        connections = []
        for row in _read_rows(csv_path):
            first = (row.get("First Name") or "").strip()
            last = (row.get("Last Name") or "").strip()
            name = f"{first} {last}".strip()
            url = (row.get("URL") or row.get("Profile URL") or "").strip()
            match = _PROFILE_SLUG_RE.search(url)
            handle = match.group(1) if match else name
            if not handle:
                continue
            connections.append(Connection(
                handle=handle,
                name=name,
                relationship="mutual",
                first_observed=_parse_connected_on(row.get("Connected On", "")),
                extra={
                    "company": row.get("Company", ""),
                    "position": row.get("Position", ""),
                    "profile url": url,
                },
            ))
        return connections


PLUGIN = LinkedInImporter

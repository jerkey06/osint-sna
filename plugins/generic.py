"""Generic CSV importer for any custom dataset.

For platforms without an official export, or your own hand-rolled list
(a spreadsheet of contacts, a scrape you did manually and legally, notes
from a conference, etc). Column names are configurable via CLI options
(--handle-col, --name-col, --relationship-col, --default-relationship) so
it can map onto whatever headers your CSV already has.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .base import Connection, Importer


class GenericImporter(Importer):
    platform = "generic"
    description = "Generic CSV importer for a custom dataset (you map the columns)"

    def parse(self, export_dir: Path, **options) -> list[Connection]:
        filename = options.get("file")
        if filename:
            csv_path = Path(filename)
            if not csv_path.is_absolute():
                csv_path = export_dir / csv_path
        else:
            candidates = list(export_dir.glob("*.csv"))
            csv_path = candidates[0] if len(candidates) == 1 else None

        if not csv_path or not csv_path.exists():
            raise FileNotFoundError(
                f"No CSV file to import. Pass --file name.csv, or drop exactly one .csv under {export_dir}."
            )

        handle_col = options.get("handle_col") or "handle"
        name_col = options.get("name_col") or "name"
        relationship_col = options.get("relationship_col") or "relationship"
        default_relationship = options.get("default_relationship") or "observed_public"

        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            if handle_col not in fieldnames:
                raise ValueError(
                    f"Column '{handle_col}' not found in {csv_path.name}. "
                    f"Available columns: {', '.join(fieldnames) or '(none)'}. "
                    "Use --handle-col to point at the right one."
                )
            connections = []
            for row in reader:
                handle = (row.get(handle_col) or "").strip()
                if not handle:
                    continue
                relationship = (row.get(relationship_col) or "").strip() or default_relationship
                connections.append(Connection(
                    handle=handle,
                    name=(row.get(name_col) or "").strip(),
                    relationship=relationship,
                    first_observed=date.today().isoformat(),
                ))
        return connections


PLUGIN = GenericImporter

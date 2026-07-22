"""Official Instagram data export: followers_1.json / following.json.

Instagram -> Settings -> Accounts Center -> Your information and permissions
-> Export your information -> "Followers and following" -> JSON format.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from .base import Connection, Importer


def _find(export_dir: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        matches = list(export_dir.rglob(pattern))
        if matches:
            return matches[0]
    return None


def _extract_entries(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def _load_usernames(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for entry in _extract_entries(data):
        for item in entry.get("string_list_data", []):
            username = item.get("value")
            ts = item.get("timestamp")
            if username:
                out[username] = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                    if ts
                    else date.today().isoformat()
                )
    return out


class InstagramImporter(Importer):
    platform = "instagram"
    description = "Official Instagram export (followers_1.json / following.json)"

    def parse(self, export_dir: Path, **options) -> list[Connection]:
        followers_path = _find(export_dir, ["followers_1.json", "followers*.json"])
        following_path = _find(export_dir, ["following.json"])
        if not followers_path or not following_path:
            raise FileNotFoundError(
                f"Couldn't find followers_*.json / following.json under {export_dir}. "
                "Make sure it's the unzipped export in JSON format."
            )
        followers = _load_usernames(followers_path)
        following = _load_usernames(following_path)
        all_usernames = set(followers) | set(following)

        connections = []
        for username in sorted(all_usernames):
            is_follower = username in followers
            is_following = username in following
            relationship = "mutual" if (is_follower and is_following) else (
                "follows_me" if is_follower else "i_follow"
            )
            connections.append(Connection(
                handle=username,
                relationship=relationship,
                first_observed=followers.get(username) or following.get(username),
            ))
        return connections


PLUGIN = InstagramImporter

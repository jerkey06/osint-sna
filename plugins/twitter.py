"""Official X/Twitter data archive: data/follower.js, data/following.js.

X -> Settings -> Your account -> Download an archive of your data.

Known limitation: X's archive only ships numeric account IDs in these
files, not the @handle — resolving a handle from an ID would need a live
API call (out of scope: this tool only ever reads the official export, it
never calls a platform's API). The note is created under the account ID
with the profile link in its context notes, ready for you to rename by hand
once you've identified who it is.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .base import Connection, Importer


def _load_js_array(path: Path) -> list:
    text = path.read_text(encoding="utf-8")
    start = text.find("[")
    if start == -1:
        raise ValueError(f"Couldn't parse {path.name}: expected a JSON array in a window.YTD.* assignment.")
    return json.loads(text[start:])


class TwitterImporter(Importer):
    platform = "twitter"
    description = "Official X/Twitter archive (data/follower.js, data/following.js)"

    def parse(self, export_dir: Path, **options) -> list[Connection]:
        follower_path = next(export_dir.rglob("follower.js"), None)
        following_path = next(export_dir.rglob("following.js"), None)
        if not follower_path or not following_path:
            raise FileNotFoundError(
                f"Couldn't find data/follower.js / data/following.js under {export_dir}. "
                "Make sure it's the unzipped official archive (Settings -> Download an archive of your data)."
            )

        followers = {e["follower"]["accountId"] for e in _load_js_array(follower_path) if "follower" in e}
        following = {e["following"]["accountId"] for e in _load_js_array(following_path) if "following" in e}
        all_ids = followers | following

        connections = []
        for account_id in sorted(all_ids):
            is_follower = account_id in followers
            is_following = account_id in following
            relationship = "mutual" if (is_follower and is_following) else (
                "follows_me" if is_follower else "i_follow"
            )
            connections.append(Connection(
                handle=account_id,
                relationship=relationship,
                first_observed=date.today().isoformat(),
                extra={
                    "profile link": f"https://twitter.com/intent/user?user_id={account_id}",
                    "note": "X's export only provides account IDs, not @handles — open the link "
                            "above to identify this account, then rename the note and update its "
                            "handle by hand.",
                },
            ))
        return connections


PLUGIN = TwitterImporter

#!/usr/bin/env python3
"""
osint-sna — tool for practicing OSINT / Social Network Analysis (SNA)
by mapping your own social network as a graph in Obsidian.

Subcommands:
  init              Creates a brand new vault (folders, templates, ME node).
  import-instagram  Imports your official Instagram export as level-1 nodes.
  add-node          Quick scaffolding for level-2/3 nodes (surveyed by hand).
  analyze           Computes degrees of separation, clustering and small-world metrics.

Each subcommand has its own --help with details.
"""

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import networkx as nx
import yaml

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
NODE_FOLDERS = ["01-Level-0", "02-Level-1", "03-Level-2", "04-Level-3"]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-")


def read_note(path: Path):
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
    return fm, m.group(2)


def write_note(path: Path, frontmatter: dict, body: str):
    fm_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    path.write_text(f"---\n{fm_text}---\n{body}", encoding="utf-8")


def require_vault(vault: Path):
    if not (vault / "01-Level-0").exists():
        sys.exit(
            f"{vault} doesn't look like a vault initialized by this tool "
            f"(missing 01-Level-0/). Run 'osint-sna init --vault {vault}' first."
        )


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

DASHBOARD_README_TEMPLATE = """---
tags: [dashboard]
---

# OSINT / SNA — {project_name}

Practice mapping your own social network: represent your network as a graph
in Obsidian and analyze it with graph theory (degrees of separation, Bacon
number, Watts-Strogatz small-world).

Platforms for this project: {platforms}.

## Vault structure

| Folder | Content |
|---|---|
| `01-Level-0/` | You (ego node, origin of all distances) |
| `02-Level-1/` | People you follow / who follow you (full data) |
| `03-Level-2/` | Contacts of your contacts (partial data, via a bridge node) |
| `04-Level-3/` | Indirect surroundings (only what's needed to measure reach) |
| `90-Templates/` | Person-node template |
| `00-Dashboard/` | This note + `Graph-Analysis.md` (auto-generated) |

The scripts live outside the vault, installed once as the `osint-sna`
command (see `osint-sna --help`). No need to copy them into every new vault.

## Workflow

1. Fill in your own node in `01-Level-0/ME.md`.
2. **Automated level 1 (Instagram only for now):**
   request your official export (Instagram → Settings → Accounts Center →
   Your information and permissions → Export your information → "Followers
   and following" → JSON format) and run:
   `osint-sna import-instagram --vault . --export-dir /path/to/export`
3. **Level 1 for other platforms / levels 2 and 3 (assisted manual):**
   no mainstream social network exposes a public API to see another
   account's connections — automating that would be scraping and would
   violate their Terms of Service. It's surveyed by looking at public
   profiles and recorded with:
   `osint-sna add-node --vault . --name "..." --handle ... --degree 2 --via bridge-node-slug`
4. **Analyze:** `osint-sna analyze --vault .` — writes
   `00-Dashboard/Graph-Analysis.md` with real BFS distances from you,
   clustering, comparison against a random graph, and the most central nodes.
5. **Visualize:** Obsidian's native Graph View (colored by level, see
   `.obsidian/graph.json`), or `--graphml` in the previous step to open in Gephi.

## Dataview queries

Requires the community plugin **Dataview** (Settings → Community
plugins → Search "Dataview" → Install and enable).

```dataview
TABLE degree AS "Level", relationship AS "Relationship"
FROM "02-Level-1" OR "03-Level-2" OR "04-Level-3"
SORT degree ASC
```

```dataview
TABLE length(rows) AS "Count"
FROM "02-Level-1" OR "03-Level-2" OR "04-Level-3"
GROUP BY degree
```

## Ethics and scope notes

- Level 1 is your own data, obtained from your own official export: no issue.
- Level 2/3 are people without explicit consent to be profiled —
  store the minimum needed for graph analysis (handle, relationship,
  bridge node), not an extended profile.
- No automated scraping of other people's profiles is done: the only data
  obtained by script is your own, via official export.
- If you're going to share this vault, consider anonymizing levels 2/3 first.
"""

PERSON_TEMPLATE = """---
name: ""
aliases: []
type: person
platforms: [{platforms}]
handles: {{}}
degree: 1
connected_via: []
relationship: []
first_observed: {today}
location: ""
bio: ""
tags: []
notes: ""
---

# {{name}}

## Profile
- **Handle:**
- **Platform:**
- **Stated location:**
- **Bio:**

## Position in the network
- **Degree:** <!-- 1, 2 or 3 -->
- **Relationship:** <!-- follows_me / i_follow / mutual / observed_public -->
- **Via (level 2/3 only):** <!-- [[name of bridge contact]] -->

## Connections
<!-- These links draw the edges in the Graph View. Level 1 always links to ME. -->
- [[ME]]

## Context notes
"""

GRAPH_JSON = """{
  "collapse-filter": true,
  "search": "",
  "showTags": false,
  "showAttachments": false,
  "hideUnresolved": false,
  "showOrphans": true,
  "collapse-color-groups": false,
  "colorGroups": [
    { "query": "path:01-Level-0", "color": { "a": 1, "rgb": 16711680 } },
    { "query": "path:02-Level-1", "color": { "a": 1, "rgb": 65280 } },
    { "query": "path:03-Level-2", "color": { "a": 1, "rgb": 255 } },
    { "query": "path:04-Level-3", "color": { "a": 1, "rgb": 16776960 } }
  ],
  "collapse-display": false,
  "showArrow": false,
  "textFadeMultiplier": 0,
  "nodeSizeMultiplier": 1,
  "lineSizeMultiplier": 1,
  "collapse-forces": false,
  "centerStrength": 0.5,
  "repelStrength": 10,
  "linkStrength": 1,
  "linkDistance": 250,
  "scale": 1,
  "close": false
}
"""


def cmd_init(args):
    vault = args.vault
    if vault.exists() and any(vault.iterdir()):
        sys.exit(f"{vault} already exists and is not empty. Pick another path or empty it first.")
    for folder in NODE_FOLDERS + ["90-Templates", "00-Dashboard", ".obsidian"]:
        (vault / folder).mkdir(parents=True, exist_ok=True)

    platforms = args.platforms
    platforms_yaml = ", ".join(platforms)

    write_note(
        vault / "01-Level-0" / "ME.md",
        {
            "name": args.name,
            "aliases": [],
            "type": "person",
            "node_role": "ego",
            "platforms": platforms,
            "handles": {p: "" for p in platforms},
            "degree": 0,
            "connected_via": [],
            "relationship": ["self"],
            "first_observed": date.today().isoformat(),
            "location": "",
            "tags": ["level-0", "ego"],
            "notes": "Origin node of the graph. All distances are computed from here.",
        },
        f"\n# {args.name} (origin node)\n\nSee [[00-Dashboard/README|README]] for the full workflow.\n",
    )

    (vault / "90-Templates" / "Person-Template.md").write_text(
        PERSON_TEMPLATE.format(platforms=platforms_yaml, today=date.today().isoformat()),
        encoding="utf-8",
    )

    (vault / "00-Dashboard" / "README.md").write_text(
        DASHBOARD_README_TEMPLATE.format(project_name=args.project_name or vault.name, platforms=platforms_yaml),
        encoding="utf-8",
    )

    (vault / ".obsidian" / "graph.json").write_text(GRAPH_JSON, encoding="utf-8")

    print(f"Vault created at {vault}")
    print(f"1. Fill in your handle at {vault / '01-Level-0' / 'ME.md'}")
    print(f"2. Read {vault / '00-Dashboard' / 'README.md'} for the workflow")


# ---------------------------------------------------------------------------
# import-instagram
# ---------------------------------------------------------------------------

def find_export_files(export_dir: Path):
    followers = list(export_dir.rglob("followers_1.json")) or list(export_dir.rglob("followers*.json"))
    following = list(export_dir.rglob("following.json"))
    if not followers or not following:
        sys.exit(
            f"Couldn't find followers_*.json / following.json under {export_dir}. "
            "Make sure it's the unzipped export in JSON format."
        )
    return followers[0], following[0]


def extract_entries(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def load_usernames(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for entry in extract_entries(data):
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


def default_person_body(username: str) -> str:
    return f"""
# {username}

## Profile
- **Handle:** @{username}
- **Platform:** Instagram
- **Stated location:**
- **Bio:**

## Position in the network
- **Degree:** 1
- **Relationship:** <!-- filled automatically in the frontmatter -->
- **Via (level 2/3 only):** n/a (level 1, direct connection)

## Connections
- [[ME]]

## Context notes
"""


def upsert_instagram_note(vault: Path, username: str, relationship: str, observed: str, dry_run: bool):
    path = vault / "02-Level-1" / f"{slugify(username)}.md"
    if path.exists():
        fm, body = read_note(path)
        fm["platforms"] = sorted(set(fm.get("platforms", []) + ["instagram"]))
        handles = fm.get("handles") or {}
        handles["instagram"] = f"@{username}"
        fm["handles"] = handles
        fm["relationship"] = [relationship]
        fm["degree"] = 1
        prev = fm.get("first_observed")
        fm["first_observed"] = min(prev, observed) if prev else observed
        action = "updated"
    else:
        fm = {
            "name": username,
            "aliases": [],
            "type": "person",
            "platforms": ["instagram"],
            "handles": {"instagram": f"@{username}"},
            "degree": 1,
            "connected_via": [],
            "relationship": [relationship],
            "first_observed": observed,
            "location": "",
            "bio": "",
            "tags": ["level-1", "instagram"],
            "notes": "",
        }
        body = default_person_body(username)
        action = "created"
    if not dry_run:
        write_note(path, fm, body)
    return action


def cmd_import_instagram(args):
    vault = args.vault
    require_vault(vault)
    followers_path, following_path = find_export_files(args.export_dir)
    followers = load_usernames(followers_path)
    following = load_usernames(following_path)
    all_usernames = set(followers) | set(following)
    stats = {"created": 0, "updated": 0}

    for username in sorted(all_usernames):
        is_follower = username in followers
        is_following = username in following
        relationship = "mutual" if (is_follower and is_following) else (
            "follows_me" if is_follower else "i_follow"
        )
        observed = followers.get(username) or following.get(username)
        action = upsert_instagram_note(vault, username, relationship, observed, args.dry_run)
        stats[action] += 1

    print(f"Total level-1 accounts: {len(all_usernames)}")
    print(f"  Mutual:          {sum(1 for u in all_usernames if u in followers and u in following)}")
    print(f"  Follow you only: {sum(1 for u in all_usernames if u in followers and u not in following)}")
    print(f"  You follow only: {sum(1 for u in all_usernames if u not in followers and u in following)}")
    print(f"Notes created: {stats['created']} | Notes updated: {stats['updated']}")
    if args.dry_run:
        print("(dry-run: nothing was written)")


# ---------------------------------------------------------------------------
# add-node
# ---------------------------------------------------------------------------

def cmd_add_node(args):
    vault = args.vault
    require_vault(vault)
    folder_name = "03-Level-2" if args.degree == 2 else "04-Level-3"
    folder = vault / folder_name
    folder.mkdir(exist_ok=True)
    path = folder / f"{slugify(args.handle)}.md"

    if path.exists():
        print(f"Already exists: {path}. Not overwriting.")
        return

    fm = {
        "name": args.name,
        "aliases": [],
        "type": "person",
        "platforms": [args.platform],
        "handles": {args.platform: f"@{args.handle}"},
        "degree": args.degree,
        "connected_via": [f"[[{args.via}]]"],
        "relationship": [args.relationship],
        "first_observed": date.today().isoformat(),
        "location": args.location,
        "bio": "",
        "tags": [f"level-{args.degree}", args.platform],
        "notes": args.notes,
    }
    body = f"""
# {args.name}

## Profile
- **Handle:** @{args.handle}
- **Platform:** {args.platform.capitalize()}
- **Stated location:** {args.location}

## Position in the network
- **Degree:** {args.degree}
- **Relationship:** {args.relationship}
- **Via:** [[{args.via}]]

## Connections
- [[{args.via}]]

## Context notes
{args.notes}
"""
    write_note(path, fm, body)
    print(f"Created: {path}")


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

def load_notes(vault: Path):
    notes = {}
    for folder in NODE_FOLDERS:
        for path in (vault / folder).glob("*.md"):
            fm, body = read_note(path)
            notes[path.stem] = {"fm": fm, "body": body, "path": path}
    return notes


def build_graph(notes: dict) -> nx.Graph:
    G = nx.Graph()
    name_lookup = {}
    for stem, data in notes.items():
        fm = data["fm"]
        G.add_node(stem, name=fm.get("name", stem), degree_manual=fm.get("degree"),
                    platforms=",".join(fm.get("platforms", []) or []))
        if fm.get("name"):
            name_lookup[str(fm["name"]).strip().lower()] = stem

    def resolve(target: str):
        target = target.strip()
        if target in notes:
            return target
        return name_lookup.get(target.lower())

    for stem, data in notes.items():
        fm = data["fm"]
        link_sources = list(WIKILINK_RE.findall(data["body"]))
        for raw in fm.get("connected_via", []) or []:
            link_sources += WIKILINK_RE.findall(str(raw)) or ([str(raw)] if "[[" not in str(raw) else [])
        for raw_target in link_sources:
            target = resolve(raw_target)
            if target and target != stem:
                G.add_edge(stem, target)
    return G


def find_ego(notes: dict) -> str:
    for stem, data in notes.items():
        if data["fm"].get("node_role") == "ego":
            return stem
    if "ME" in notes:
        return "ME"
    sys.exit("Couldn't find the ego node (node_role: ego in the frontmatter, or name it ME.md).")


def small_world_baseline(n, edges):
    if n < 3 or edges == 0:
        return None, None
    k = (2 * edges) / n
    c_rand = k / n if n else 0
    l_rand = math.log(n) / math.log(k) if k > 1 else float("inf")
    return c_rand, l_rand


def cmd_analyze(args):
    vault = args.vault
    require_vault(vault)
    notes = load_notes(vault)
    if not notes:
        sys.exit("Couldn't find any person notes in the vault yet.")

    G = build_graph(notes)
    ego = find_ego(notes)
    distances = nx.single_source_shortest_path_length(G, ego)
    unreachable = set(G.nodes) - set(distances)

    components = sorted(nx.connected_components(G), key=len, reverse=True)
    main_component = G.subgraph(components[0]).copy()
    clustering = nx.average_clustering(G)
    hubs = sorted(G.degree, key=lambda x: x[1], reverse=True)[:10]

    path_len, diameter = None, None
    if nx.is_connected(main_component) and main_component.number_of_nodes() > 1:
        path_len = nx.average_shortest_path_length(main_component)
        diameter = nx.diameter(main_component)

    c_rand, l_rand = small_world_baseline(main_component.number_of_nodes(), main_component.number_of_edges())

    lines = []
    lines.append("# Graph analysis\n")
    lines.append("*Automatically generated by `osint-sna analyze`. Do not edit by hand — it gets overwritten.*\n")
    lines.append(f"- Total nodes: **{G.number_of_nodes()}**")
    lines.append(f"- Total edges: **{G.number_of_edges()}**")
    lines.append(f"- Connected components: **{len(components)}** (sizes: {[len(c) for c in components]})")
    lines.append(f"- Nodes with no detected path to ME: **{len(unreachable)}**\n")

    lines.append("## Degrees of separation (Bacon number relative to you)\n")
    lines.append("| Node | Name | OSINT level (manual) | Real distance (BFS) |")
    lines.append("|---|---|---|---|")
    for stem, dist in sorted(distances.items(), key=lambda x: x[1]):
        fm = notes[stem]["fm"]
        lines.append(f"| [[{stem}]] | {fm.get('name', stem)} | {fm.get('degree', '?')} | {dist} |")
    if unreachable:
        lines.append("\n**No connection detected (check `[[...]]` links or `connected_via`):**")
        for stem in sorted(unreachable):
            lines.append(f"- [[{stem}]]")

    lines.append("\n## Small-world metric (Watts-Strogatz)\n")
    lines.append(f"- Average clustering coefficient (whole graph): **{clustering:.3f}**")
    if path_len is not None:
        lines.append(f"- Average path length (main component, {main_component.number_of_nodes()} nodes): **{path_len:.3f}**")
        lines.append(f"- Diameter of the main component: **{diameter}**")
    else:
        lines.append("- The main component is not fully connected or has only 1 node: average path length not computed.")
    if c_rand is not None:
        lines.append(f"- Equivalent random-graph baseline: C_rand ≈ **{c_rand:.4f}**, L_rand ≈ **{l_rand:.3f}**")
        lines.append(
            "- Interpretation: if your real clustering is *much higher* than C_rand and your path length "
            "is *similar to or somewhat higher* than L_rand, your network shows the 'small-world' "
            "signature (dense clusters + short shortcuts), just like Kevin Bacon's collaboration network."
        )

    lines.append("\n## Most central nodes (hubs)\n")
    lines.append("| Node | Name | Direct connections |")
    lines.append("|---|---|---|")
    for stem, deg in hubs:
        lines.append(f"| [[{stem}]] | {notes[stem]['fm'].get('name', stem)} | {deg} |")

    out_path = vault / "00-Dashboard" / "Graph-Analysis.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to {out_path}")

    if args.graphml:
        gpath = vault / "00-Dashboard" / "graph.graphml"
        nx.write_graphml(G, gpath)
        print(f"Gephi export: {gpath}")


# ---------------------------------------------------------------------------
# menu (interactive terminal interface)
# ---------------------------------------------------------------------------

def prompt(msg: str, default: str = None, required: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"{msg}{suffix}: ").strip()
        if val:
            return val
        if default is not None:
            return default
        if not required:
            return ""
        print("  This field is required.")


def prompt_yes_no(msg: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    val = input(f"{msg} {suffix}: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def menu_init():
    vault = Path(prompt("Path of the vault to create", required=True)).expanduser()
    name = prompt("Your name for the ego node", default="Me")
    project_name = prompt("Project name for the dashboard", default="") or None
    platforms_raw = prompt("Platforms to map (comma-separated)", default="instagram")
    platforms = [p.strip() for p in platforms_raw.split(",") if p.strip()]
    cmd_init(argparse.Namespace(vault=vault, name=name, project_name=project_name, platforms=platforms))


def menu_import_instagram():
    vault = Path(prompt("Vault path", required=True)).expanduser()
    export_dir = Path(prompt("Path to the unzipped Instagram export", required=True)).expanduser()
    dry_run = prompt_yes_no("Simulate without writing changes? (dry-run)", default=False)
    cmd_import_instagram(argparse.Namespace(vault=vault, export_dir=export_dir, dry_run=dry_run))


def menu_add_node():
    vault = Path(prompt("Vault path", required=True)).expanduser()
    name = prompt("Display name", required=True)
    handle = prompt("Handle (username)", required=True)
    platform = prompt("Platform", default="instagram")
    while True:
        degree_raw = prompt("Degree (2 or 3)", default="2")
        if degree_raw in ("2", "3"):
            degree = int(degree_raw)
            break
        print("  Enter 2 or 3.")
    via = prompt("Bridge node slug (filename without .md)", required=True)
    relationship = prompt("Relationship", default="observed_public")
    location = prompt("Stated location", default="")
    notes = prompt("Notes", default="")
    cmd_add_node(argparse.Namespace(
        vault=vault, name=name, handle=handle, platform=platform, degree=degree,
        via=via, relationship=relationship, location=location, notes=notes,
    ))


def menu_analyze():
    vault = Path(prompt("Vault path", required=True)).expanduser()
    graphml = prompt_yes_no("Also export graph.graphml for Gephi?", default=False)
    cmd_analyze(argparse.Namespace(vault=vault, graphml=graphml))


def cmd_menu(args):
    actions = {
        "1": ("Create a new vault", menu_init),
        "2": ("Import Instagram export (level 1)", menu_import_instagram),
        "3": ("Add a level 2/3 node by hand", menu_add_node),
        "4": ("Analyze graph", menu_analyze),
    }
    print("=== osint-sna — interactive menu ===")
    while True:
        print("\nOptions:")
        for key, (label, _) in actions.items():
            print(f"  {key}. {label}")
        print("  0. Exit")
        try:
            choice = input("\nChoose an option: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            return
        if choice in ("0", "q", "exit", "quit"):
            print("Bye!")
            return
        action = actions.get(choice)
        if not action:
            print("Invalid option.")
            continue
        _, func = action
        try:
            func()
        except SystemExit as e:
            if e.code:
                print(f"Error: {e.code}")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(prog="osint-sna", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=False)

    p_init = sub.add_parser("init", help="Create a brand new vault")
    p_init.add_argument("--vault", required=True, type=Path)
    p_init.add_argument("--name", default="Me", help="Your name for the ego node")
    p_init.add_argument("--project-name", default=None, help="Project name for the dashboard")
    p_init.add_argument("--platforms", nargs="+", default=["instagram"], help="Platforms to map (e.g. instagram twitter linkedin)")
    p_init.set_defaults(func=cmd_init)

    p_ig = sub.add_parser("import-instagram", help="Import an official Instagram export as level 1")
    p_ig.add_argument("--vault", required=True, type=Path)
    p_ig.add_argument("--export-dir", required=True, type=Path)
    p_ig.add_argument("--dry-run", action="store_true")
    p_ig.set_defaults(func=cmd_import_instagram)

    p_node = sub.add_parser("add-node", help="Add a level 2/3 node surveyed by hand")
    p_node.add_argument("--vault", required=True, type=Path)
    p_node.add_argument("--name", required=True)
    p_node.add_argument("--handle", required=True)
    p_node.add_argument("--platform", default="instagram")
    p_node.add_argument("--degree", type=int, choices=[2, 3], required=True)
    p_node.add_argument("--via", required=True, help="Bridge node slug (filename without .md)")
    p_node.add_argument("--relationship", default="observed_public")
    p_node.add_argument("--location", default="")
    p_node.add_argument("--notes", default="")
    p_node.set_defaults(func=cmd_add_node)

    p_analyze = sub.add_parser("analyze", help="Compute degrees of separation and small-world metrics")
    p_analyze.add_argument("--vault", required=True, type=Path)
    p_analyze.add_argument("--graphml", action="store_true", help="Also export graph.graphml for Gephi")
    p_analyze.set_defaults(func=cmd_analyze)

    p_menu = sub.add_parser("menu", help="Interactive menu (also activated if you pass no subcommand)")
    p_menu.set_defaults(func=cmd_menu)

    args = ap.parse_args()
    if args.command is None:
        cmd_menu(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()

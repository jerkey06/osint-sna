#!/usr/bin/env python3
"""
osint-sna — tool for practicing OSINT / Social Network Analysis (SNA)
by mapping your own social network as a graph in Obsidian.

Subcommands:
  init      Creates a brand new vault (folders, templates, ME node).
  import    Imports an official platform export (or a custom CSV) as level-1 nodes.
  add-node  Quick scaffolding for level-2/3 nodes (surveyed by hand).
  analyze   Computes degrees of separation, clustering and small-world metrics.

Import plugins live in plugins/ (one file per platform: instagram.py,
linkedin.py, twitter.py, generic.py for custom CSV datasets). Run
'osint-sna import --help' to see which platforms are available.

Each subcommand has its own --help with details.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import networkx as nx
import yaml
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal
    from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

    TEXTUAL_AVAILABLE = True
except ImportError:
    App = object
    ComposeResult = object
    Container = Horizontal = Footer = Header = Label = ListItem = ListView = Static = None
    TEXTUAL_AVAILABLE = False

from plugins import available_platforms, get_importer

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
NODE_FOLDERS = ["01-Level-0", "02-Level-1", "03-Level-2", "04-Level-3"]
PLATFORM_DISPLAY_NAMES = {"linkedin": "LinkedIn", "twitter": "X / Twitter"}


def platform_display_name(platform: str) -> str:
    return PLATFORM_DISPLAY_NAMES.get(platform, platform.capitalize())


console = Console()


def die(message: str):
    console.print(f"[bold red]✗[/bold red] {message}")
    sys.exit(1)


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
        die(
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
2. **Automated level 1:** request your official data export from the
   platform, then run one of its import plugins:
   `osint-sna import --platform instagram --vault . --export-dir /path/to/export`
   `osint-sna import --platform linkedin --vault . --export-dir /path/to/export`
   `osint-sna import --platform twitter --vault . --export-dir /path/to/export`
   Have a custom dataset (a spreadsheet, a CSV from somewhere else)? Use the
   generic plugin instead of writing your own parser:
   `osint-sna import --platform generic --vault . --export-dir /path/to/folder --handle-col handle`
   Run `osint-sna import --help` for the full list of available platforms —
   new ones are just a file dropped in `plugins/`.
3. **Level 1 for unsupported platforms / levels 2 and 3 (assisted manual):**
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
- **Relationship:** <!-- direction of the edge to whoever this note links to:
  follows_me / follows_them / follower (they follow the link target) ·
  i_follow / followed_by (the link target follows them) · mutual (both) ·
  observed_public or anything else (direction unknown, treated as mutual) -->
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
        die(f"{vault} already exists and is not empty. Pick another path or empty it first.")
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

    console.print(f"[green]✓[/green] Vault created at [bold]{vault}[/bold]")
    console.print(f"  [dim]1.[/dim] Fill in your handle at {vault / '01-Level-0' / 'ME.md'}")
    console.print(f"  [dim]2.[/dim] Read {vault / '00-Dashboard' / 'README.md'} for the workflow")


# ---------------------------------------------------------------------------
# import (plugin-based: instagram, linkedin, twitter, generic, ...)
# ---------------------------------------------------------------------------

def default_person_body(connection, platform: str) -> str:
    context_lines = "\n".join(
        f"- **{str(key).replace('_', ' ').title()}:** {value}"
        for key, value in (connection.extra or {}).items()
    )
    return f"""
# {connection.name or connection.handle}

## Profile
- **Handle:** @{connection.handle}
- **Platform:** {platform_display_name(platform)}
- **Stated location:**
- **Bio:**

## Position in the network
- **Degree:** 1
- **Relationship:** <!-- filled automatically in the frontmatter -->
- **Via (level 2/3 only):** n/a (level 1, direct connection)

## Connections
- [[ME]]

## Context notes
{context_lines}
"""


def upsert_connection_note(vault: Path, platform: str, connection, dry_run: bool) -> str:
    path = vault / "02-Level-1" / f"{slugify(connection.handle)}.md"
    if path.exists():
        fm, body = read_note(path)
        fm["platforms"] = sorted(set(fm.get("platforms", []) + [platform]))
        handles = fm.get("handles") or {}
        handles[platform] = f"@{connection.handle}"
        fm["handles"] = handles
        fm["relationship"] = [connection.relationship]
        fm["degree"] = 1
        if connection.name:
            fm["name"] = connection.name
        prev = fm.get("first_observed")
        fm["first_observed"] = (
            min(prev, connection.first_observed)
            if prev and connection.first_observed
            else (prev or connection.first_observed or date.today().isoformat())
        )
        action = "updated"
    else:
        fm = {
            "name": connection.name or connection.handle,
            "aliases": [],
            "type": "person",
            "platforms": [platform],
            "handles": {platform: f"@{connection.handle}"},
            "degree": 1,
            "connected_via": [],
            "relationship": [connection.relationship],
            "first_observed": connection.first_observed or date.today().isoformat(),
            "location": "",
            "bio": "",
            "tags": ["level-1", platform],
            "notes": "",
        }
        body = default_person_body(connection, platform)
        action = "created"
    if not dry_run:
        write_note(path, fm, body)
    return action


def cmd_import(args):
    vault = args.vault
    require_vault(vault)
    try:
        importer = get_importer(args.platform)
    except KeyError as e:
        die(str(e))

    try:
        connections = importer.parse(
            args.export_dir,
            file=getattr(args, "file", None),
            handle_col=getattr(args, "handle_col", None),
            name_col=getattr(args, "name_col", None),
            relationship_col=getattr(args, "relationship_col", None),
            default_relationship=getattr(args, "default_relationship", None),
        )
    except (FileNotFoundError, ValueError) as e:
        die(str(e))

    if not connections:
        console.print("[yellow]![/yellow] No connections found in that export.")
        return

    stats = {"created": 0, "updated": 0}
    for connection in connections:
        action = upsert_connection_note(vault, args.platform, connection, args.dry_run)
        stats[action] += 1

    relationship_counts = Counter(c.relationship for c in connections)

    table = Table(box=box.SIMPLE, show_header=False, border_style="dim")
    table.add_column(style="dim")
    table.add_column(justify="right", style="bold")
    table.add_row("Platform", args.platform)
    table.add_row("Total level-1 accounts", str(len(connections)))
    for relationship, count in sorted(relationship_counts.items()):
        table.add_row(relationship, str(count))
    table.add_row("Notes created", str(stats["created"]))
    table.add_row("Notes updated", str(stats["updated"]))
    console.print(table)
    if args.dry_run:
        console.print("[yellow]dry-run: nothing was written[/yellow]")
    else:
        console.print("[green]✓[/green] Level-1 notes are up to date")


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
        console.print(f"[yellow]![/yellow] Already exists: {path}. Not overwriting.")
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
- **Platform:** {platform_display_name(args.platform)}
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
    console.print(f"[green]✓[/green] Created: [bold]{path}[/bold]")


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


# Relationship tags are always phrased as "[stem] <verb> [target]": "follows_me" /
# "follows_them" mean the stem note's subject follows whoever it links to (target),
# and "i_follow" means the target follows the stem. Unknown/observational tags
# (e.g. "observed_public") default to a reciprocal edge rather than guessing a
# direction that isn't actually known.
FORWARD_RELATIONSHIPS = {"follows_me", "follows_them", "follower"}
BACKWARD_RELATIONSHIPS = {"i_follow", "followed_by"}
MUTUAL_RELATIONSHIPS = {"mutual"}


def edge_directions(relationship_values) -> set:
    values = {str(v).strip().lower() for v in (relationship_values or [])}
    if values & MUTUAL_RELATIONSHIPS:
        return {"forward", "backward"}
    directions = set()
    if values & FORWARD_RELATIONSHIPS:
        directions.add("forward")
    if values & BACKWARD_RELATIONSHIPS:
        directions.add("backward")
    return directions or {"forward", "backward"}


def build_graph(notes: dict) -> nx.DiGraph:
    G = nx.DiGraph()
    name_lookup = {}
    for stem, data in notes.items():
        fm = data["fm"]
        platforms_list = fm.get("platforms", []) or []
        G.add_node(
            stem,
            name=fm.get("name", stem),
            degree_manual=fm.get("degree"),
            platforms=",".join(platforms_list),
            primary_platform=platforms_list[0] if platforms_list else "unknown",
        )
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
        directions = edge_directions(fm.get("relationship"))
        for raw_target in link_sources:
            target = resolve(raw_target)
            if target and target != stem:
                if "forward" in directions:
                    G.add_edge(stem, target)
                if "backward" in directions:
                    G.add_edge(target, stem)
    return G


def find_ego(notes: dict) -> str:
    for stem, data in notes.items():
        if data["fm"].get("node_role") == "ego":
            return stem
    if "ME" in notes:
        return "ME"
    die("Couldn't find the ego node (node_role: ego in the frontmatter, or name it ME.md).")


def small_world_baseline(n, edges):
    if n < 3 or edges == 0:
        return None, None
    k = (2 * edges) / n
    c_rand = k / n if n else 0
    l_rand = math.log(n) / math.log(k) if k > 1 else float("inf")
    return c_rand, l_rand


def safe_assortativity(G, attribute: str):
    """Attribute (homophily) assortativity, or None when it isn't defined
    (fewer than 2 edges, or every node shares the same value)."""
    if G.number_of_edges() == 0:
        return None
    try:
        value = nx.attribute_assortativity_coefficient(G, attribute)
    except (ZeroDivisionError, nx.NetworkXError):
        return None
    return None if math.isnan(value) else value


def cmd_analyze(args):
    vault = args.vault
    require_vault(vault)
    notes = load_notes(vault)
    if not notes:
        die("Couldn't find any person notes in the vault yet.")

    G = build_graph(notes)
    ego = find_ego(notes)

    # Directed reachability: who you can reach by following outgoing edges, and
    # who can reach you by following edges backward (i.e. their outgoing chain
    # of "follows" ending at you).
    out_distances = nx.single_source_shortest_path_length(G, ego)
    in_distances = nx.single_source_shortest_path_length(G.reverse(copy=True), ego)
    unreachable = set(G.nodes) - (set(out_distances) | set(in_distances))

    # Small-world metrics (clustering, path length, diameter) are classically
    # defined on undirected graphs, so they're computed on the undirected
    # projection — direction only matters for reachability and reciprocity.
    UG = G.to_undirected()
    weak_components = sorted(nx.weakly_connected_components(G), key=len, reverse=True)
    main_component = UG.subgraph(weak_components[0]).copy()
    clustering = nx.average_clustering(UG)
    reciprocity = nx.overall_reciprocity(G) if G.number_of_edges() else None

    path_len, diameter = None, None
    if nx.is_connected(main_component) and main_component.number_of_nodes() > 1:
        path_len = nx.average_shortest_path_length(main_component)
        diameter = nx.diameter(main_component)

    c_rand, l_rand = small_world_baseline(main_component.number_of_nodes(), main_component.number_of_edges())

    # Community detection (Louvain modularity optimization) needs an undirected
    # graph, same as the clustering/small-world metrics above — it groups nodes
    # into densely-connected subgroups regardless of follow direction.
    communities = nx.community.louvain_communities(UG, seed=42) if UG.number_of_edges() else [{n} for n in UG.nodes]
    communities = sorted(communities, key=len, reverse=True)
    community_of = {stem: idx for idx, members in enumerate(communities) for stem in members}
    modularity = nx.community.modularity(UG, communities) if UG.number_of_edges() else None

    # "Bridge people" (betweenness) are a structural, direction-agnostic notion —
    # computed on the undirected projection like communities/clustering above.
    betweenness = nx.betweenness_centrality(UG)
    # Closeness here is deliberately computed on the *reversed* directed graph:
    # closeness_centrality(G) measures distance TO a node (how fast others reach
    # it); reversing first measures distance FROM a node (how fast it can reach
    # everyone else), which is what "influence outward" means.
    closeness = nx.closeness_centrality(G.reverse(copy=True))
    try:
        eigenvector = nx.eigenvector_centrality(G, max_iter=2000)
    except nx.PowerIterationFailedConvergence:
        eigenvector = {n: 0.0 for n in G.nodes}
    try:
        pagerank = nx.pagerank(G)
    except ImportError:
        # pagerank needs numpy/scipy; degrade gracefully instead of crashing analyze.
        pagerank = {n: 0.0 for n in G.nodes}

    density = nx.density(G)
    level_homophily = safe_assortativity(G, "degree_manual")
    platform_homophily = safe_assortativity(G, "primary_platform")

    lines = []
    lines.append("# Graph analysis\n")
    lines.append("*Automatically generated by `osint-sna analyze`. Do not edit by hand — it gets overwritten.*\n")
    lines.append(f"- Total nodes: **{G.number_of_nodes()}**")
    lines.append(f"- Total directed edges: **{G.number_of_edges()}**")
    lines.append(f"- Weakly connected components: **{len(weak_components)}** (sizes: {[len(c) for c in weak_components]})")
    lines.append(f"- Nodes with no directed path to/from you: **{len(unreachable)}**")
    if reciprocity is not None:
        lines.append(f"- Reciprocity (share of edges that are followed back): **{reciprocity:.1%}**\n")
    else:
        lines.append("- Reciprocity: not defined (no edges yet)\n")

    lines.append("## Degrees of separation (Bacon number relative to you)\n")
    lines.append("| Node | Name | OSINT level (manual) | You → them | Them → you |")
    lines.append("|---|---|---|---|---|")
    all_stems = sorted(
        set(out_distances) | set(in_distances),
        key=lambda s: (out_distances.get(s, math.inf), in_distances.get(s, math.inf)),
    )
    for stem in all_stems:
        fm = notes[stem]["fm"]
        out_d = out_distances.get(stem, "—")
        in_d = in_distances.get(stem, "—")
        lines.append(f"| [[{stem}]] | {fm.get('name', stem)} | {fm.get('degree', '?')} | {out_d} | {in_d} |")
    if unreachable:
        lines.append("\n**No directed path detected in either direction (check `[[...]]` links, `connected_via` or `relationship`):**")
        for stem in sorted(unreachable):
            lines.append(f"- [[{stem}]]")

    lines.append("\n## Centrality\n")
    lines.append(
        "*In/out-degree are direction-literal (followers vs. following). Betweenness runs on the "
        "undirected projection (bridge people, regardless of follow direction). Closeness measures "
        "how fast a node's influence reaches everyone else (computed on the reversed directed graph). "
        "Eigenvector and PageRank run on the directed graph — who's central because important people "
        "point at them, not just who has the most connections.*\n"
    )
    lines.append("| Node | Name | In-deg | Out-deg | Betweenness | Closeness (out) | Eigenvector | PageRank |")
    lines.append("|---|---|---|---|---|---|---|---|")
    centrality_order = sorted(G.nodes, key=lambda n: pagerank.get(n, 0), reverse=True)[:15]
    in_degree = dict(G.in_degree)
    out_degree = dict(G.out_degree)
    for stem in centrality_order:
        name = notes[stem]["fm"].get("name", stem)
        lines.append(
            f"| [[{stem}]] | {name} | {in_degree.get(stem, 0)} | {out_degree.get(stem, 0)} | "
            f"{betweenness.get(stem, 0):.3f} | {closeness.get(stem, 0):.3f} | "
            f"{eigenvector.get(stem, 0):.3f} | {pagerank.get(stem, 0):.3f} |"
        )
    if len(G.nodes) > 15:
        lines.append(f"\n*(showing top 15 of {len(G.nodes)} nodes by PageRank)*")

    lines.append("\n## Community detection (Louvain)\n")
    lines.append(
        f"- Communities found: **{len(communities)}** "
        + (f"— modularity: **{modularity:.3f}**" if modularity is not None else "")
    )
    lines.append(
        "*Modularity above ~0.3 usually means the communities are meaningfully denser internally than "
        "you'd expect by chance — real subgroups, not an artifact of the algorithm.*\n"
    )
    lines.append("| Community | Size | Members |")
    lines.append("|---|---|---|")
    for idx, members in enumerate(communities):
        member_links = ", ".join(f"[[{stem}]]" for stem in sorted(members, key=lambda s: notes[s]["fm"].get("name", s)))
        lines.append(f"| {idx} | {len(members)} | {member_links} |")

    lines.append("\n## Small-world metric (Watts-Strogatz)\n")
    lines.append("*Computed on the undirected projection of the graph (direction is ignored here).*\n")
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

    lines.append("\n## Network density & homophily\n")
    lines.append(
        f"- Density: **{density:.4f}** — share of all possible directed connections that actually exist "
        f"(1.0 would mean everyone follows everyone)."
    )
    if level_homophily is not None:
        lines.append(
            f"- Homophily by OSINT level: **{level_homophily:+.3f}** — positive means people mostly "
            "connect within their own level (1/2/3), negative means connections mostly cross levels."
        )
    else:
        lines.append("- Homophily by OSINT level: not defined (needs more than one level with edges between them).")
    if platform_homophily is not None:
        lines.append(
            f"- Homophily by platform: **{platform_homophily:+.3f}** — positive means people mostly "
            "connect within the same platform, negative means connections mostly cross platforms."
        )
    else:
        lines.append("- Homophily by platform: not defined (needs more than one platform with edges between them).")
    lines.append(
        "\n*Homophily here is the attribute assortativity coefficient (Newman): ranges from -1 (perfectly "
        "cross-cutting) to +1 (perfectly segregated by that attribute), 0 means the attribute doesn't "
        "predict who connects to whom.*"
    )

    out_path = vault / "00-Dashboard" / "Graph-Analysis.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = Table(title="Graph summary", box=box.ROUNDED, border_style="cyan", show_header=False)
    summary.add_column(style="dim")
    summary.add_column(justify="right", style="bold")
    summary.add_row("Nodes", str(G.number_of_nodes()))
    summary.add_row("Directed edges", str(G.number_of_edges()))
    summary.add_row("Weakly connected components", str(len(weak_components)))
    summary.add_row("Reciprocity", f"{reciprocity:.1%}" if reciprocity is not None else "n/a")
    summary.add_row("Density", f"{density:.4f}")
    summary.add_row("Communities (Louvain)", f"{len(communities)}" + (f" (Q={modularity:.3f})" if modularity is not None else ""))
    summary.add_row("Avg. clustering", f"{clustering:.3f}")
    if path_len is not None:
        summary.add_row("Avg. path length", f"{path_len:.3f}")
        summary.add_row("Diameter", str(diameter))
    if centrality_order:
        top_stem = centrality_order[0]
        summary.add_row("Top by PageRank", notes[top_stem]["fm"].get("name", top_stem))
    console.print(summary)

    console.print(f"[green]✓[/green] Report written to [bold]{out_path}[/bold]")

    if args.graphml:
        gpath = vault / "00-Dashboard" / "graph.graphml"
        nx.write_graphml(G, gpath)
        console.print(f"[green]✓[/green] Gephi export: [bold]{gpath}[/bold]")


# ---------------------------------------------------------------------------
# menu (interactive terminal interface)
# ---------------------------------------------------------------------------

MENU_ACCENT = "cyan"
MENU_MUTED = "bright_black"


class OsintMenuApp(App):
    CSS = """
    Screen {
        background: #071014;
        color: #d8f3dc;
    }

    Header {
        background: #0b2d2f;
        color: #d8f3dc;
        text-style: bold;
    }

    Footer {
        background: #0b2d2f;
        color: #95d5b2;
    }

    #shell {
        height: 1fr;
        padding: 2 4;
        background: #071014;
    }

    #hero {
        height: auto;
        margin-bottom: 1;
        padding: 1 2;
        border: heavy #2dd4bf;
        background: #092326;
        color: #d8f3dc;
    }

    #brand {
        text-style: bold;
        color: #5eead4;
    }

    #tagline {
        color: #95d5b2;
    }

    #workspace {
        height: 1fr;
    }

    #menu {
        width: 44;
        height: 1fr;
        border: round #2dd4bf;
        background: #0a1f24;
        padding: 1;
    }

    ListItem {
        height: 5;
        margin-bottom: 1;
        padding: 1 2;
        border: round #1f4f55;
        background: #0d2a30;
        color: #d8f3dc;
    }

    ListItem.--highlight {
        background: #123c45;
        border: tall #facc15;
        color: #ffffff;
    }

    #intel {
        width: 1fr;
        height: 1fr;
        margin-left: 2;
        padding: 1 2;
        border: round #3b82f6;
        background: #081827;
        color: #bfdbfe;
    }

    .label-title {
        text-style: bold;
        color: #f8fafc;
    }

    .label-desc {
        color: #99f6e4;
    }

    .signal {
        color: #facc15;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("q", "quit", "Salir"),
        ("escape", "quit", "Salir"),
        ("enter", "select_cursor", "Abrir"),
    ]

    def __init__(self, actions: dict):
        super().__init__()
        self.actions = actions
        self.title = "osint-sna"
        self.sub_title = "OSINT / Social Network Analysis"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="shell"):
            yield Static(
                "[#5eead4 bold]OSINT-SNA[/]\n"
                "[#95d5b2]Mapa, importa y analiza tu red social en un vault de Obsidian.[/]",
                id="hero",
            )
            with Horizontal(id="workspace"):
                yield ListView(
                    *[
                        ListItem(
                            Label(
                                f"[bold #f8fafc]{label}[/]\n[#99f6e4]{description}[/]",
                            ),
                            id=f"action-{key}",
                        )
                        for key, (label, description, _) in self.actions.items()
                    ],
                    ListItem(Label("[bold #f8fafc]Salir[/]\n[#99f6e4]Cerrar la herramienta.[/]"), id="action-0"),
                    id="menu",
                )
                yield Static(
                    "[#facc15 bold]OPERACION[/]\n\n"
                    "Usa flechas para moverte.\n"
                    "Enter ejecuta la accion seleccionada.\n"
                    "Esc o q cierra el panel.\n\n"
                    "[#facc15 bold]ALCANCE[/]\n\n"
                    "Nivel 0: ego node.\n"
                    "Nivel 1: exportaciones oficiales.\n"
                    "Nivel 2/3: observacion manual.\n\n"
                    "[#facc15 bold]ETICA[/]\n\n"
                    "Sin scraping automatizado. Mantiene el enfoque en datos propios y notas minimas.",
                    id="intel",
                )
        yield Footer()

    def on_mount(self):
        self.query_one("#menu", ListView).focus()

    def action_select_cursor(self):
        menu = self.query_one("#menu", ListView)
        if menu.highlighted is not None:
            self.exit(menu.children[menu.highlighted].id.removeprefix("action-"))

    def on_list_view_selected(self, event: ListView.Selected):
        self.exit(event.item.id.removeprefix("action-"))


def section_header(title: str, subtitle: str = ""):
    text = Text(title, style=f"bold {MENU_ACCENT}")
    if subtitle:
        text.append(f"\n{subtitle}", style=MENU_MUTED)
    console.print(Panel(text, border_style=MENU_ACCENT, box=box.ROUNDED, padding=(1, 2)))


def ask_text(msg: str, default: str = None, required: bool = False) -> str:
    label = f"  [bold {MENU_ACCENT}]›[/bold {MENU_ACCENT}] {msg}"
    while True:
        val = Prompt.ask(label, default=default) if default is not None else Prompt.ask(label)
        val = val.strip()
        if val:
            return val
        if default is not None:
            return default
        if not required:
            return ""
        console.print("    [red]Este campo es obligatorio.[/red]")


def ask_bool(msg: str, default: bool = False) -> bool:
    return Confirm.ask(f"  [bold {MENU_ACCENT}]›[/bold {MENU_ACCENT}] {msg}", default=default)


def ask_choice(msg: str, choices: list, default: str = None) -> str:
    return Prompt.ask(
        f"  [bold {MENU_ACCENT}]›[/bold {MENU_ACCENT}] {msg}",
        choices=choices,
        default=default,
        show_choices=True,
    )


def print_banner():
    console.print()
    body = Align.center(
        "[bold white]Mapea, importa y analiza tu red social[/bold white]\n"
        f"[{MENU_MUTED}]OSINT / Social Network Analysis para vaults de Obsidian[/{MENU_MUTED}]"
    )
    console.print(Panel(
        body,
        title=f"[bold {MENU_ACCENT}] OSINT-SNA [/bold {MENU_ACCENT}]",
        subtitle=f"[{MENU_MUTED}]menu interactivo[/{MENU_MUTED}]",
        border_style=MENU_ACCENT,
        box=box.DOUBLE,
        padding=(1, 4),
    ))


def print_menu(actions: dict):
    cards = []
    for key, (label, description, _) in actions.items():
        content = (
            f"[bold {MENU_ACCENT}]{key}[/bold {MENU_ACCENT}]  [bold white]{label}[/bold white]\n"
            f"[{MENU_MUTED}]{description}[/{MENU_MUTED}]"
        )
        cards.append(Panel(content, border_style="dim", box=box.ROUNDED, padding=(1, 2)))
    console.print(Columns(cards, equal=True, expand=True))
    console.print(
        Panel(
            f"[{MENU_MUTED}]0[/{MENU_MUTED}]  Salir",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )


def menu_init():
    section_header("Crear vault", "Genera carpetas, plantillas, dashboard y nodo ME.")
    vault = Path(ask_text("Ruta del vault a crear", required=True)).expanduser()
    name = ask_text("Tu nombre para el nodo principal", default="Me")
    project_name = ask_text("Nombre del proyecto para el dashboard", default="") or None
    platforms_raw = ask_text("Plataformas a mapear (separadas por coma)", default="instagram")
    platforms = [p.strip() for p in platforms_raw.split(",") if p.strip()]
    console.print()
    cmd_init(argparse.Namespace(vault=vault, name=name, project_name=project_name, platforms=platforms))


def menu_import():
    section_header("Importar exportacion", "Crea o actualiza nodos de nivel 1 desde tus datos oficiales.")
    platforms = available_platforms()
    default_platform = "instagram" if "instagram" in platforms else (platforms[0] if platforms else None)
    platform = ask_choice("Platform", choices=platforms, default=default_platform)
    vault = Path(ask_text("Ruta del vault", required=True)).expanduser()
    export_dir = Path(ask_text(
        "Ruta a la carpeta del CSV" if platform == "generic" else "Ruta a la exportacion descomprimida",
        required=True,
    )).expanduser()
    dry_run = ask_bool("Simular sin escribir cambios? (dry-run)", default=False)

    ns = argparse.Namespace(
        vault=vault, platform=platform, export_dir=export_dir, dry_run=dry_run,
        file=None, handle_col="handle", name_col="name",
        relationship_col="relationship", default_relationship="observed_public",
    )
    if platform == "generic":
        ns.file = ask_text("Archivo CSV (vacio para autodetectar un unico .csv)", default="") or None
        ns.handle_col = ask_text("Columna con handle/usuario", default="handle")
        ns.name_col = ask_text("Columna con nombre visible", default="name")
        ns.relationship_col = ask_text("Columna con etiqueta de relacion", default="relationship")
        ns.default_relationship = ask_text("Relacion por defecto si falta el valor", default="observed_public")
    console.print()
    cmd_import(ns)


def menu_add_node():
    section_header("Agregar nodo", "Registra manualmente contactos de nivel 2 o 3.")
    vault = Path(ask_text("Ruta del vault", required=True)).expanduser()
    name = ask_text("Nombre visible", required=True)
    handle = ask_text("Handle (usuario)", required=True)
    platform = ask_text("Plataforma", default="instagram")
    degree = int(ask_choice("Nivel", choices=["2", "3"], default="2"))
    via = ask_text("Nodo puente (archivo sin .md)", required=True)
    relationship = ask_text("Relacion", default="observed_public")
    location = ask_text("Ubicacion declarada", default="")
    notes = ask_text("Notas", default="")
    console.print()
    cmd_add_node(argparse.Namespace(
        vault=vault, name=name, handle=handle, platform=platform, degree=degree,
        via=via, relationship=relationship, location=location, notes=notes,
    ))


def menu_analyze():
    section_header("Analizar grafo", "Calcula distancias, centralidad, reciprocidad y metricas small-world.")
    vault = Path(ask_text("Ruta del vault", required=True)).expanduser()
    graphml = ask_bool("Exportar tambien graph.graphml para Gephi?", default=False)
    console.print()
    cmd_analyze(argparse.Namespace(vault=vault, graphml=graphml))


def cmd_menu(args):
    actions = {
        "1": ("Crear vault", "Inicializa un vault nuevo de Obsidian.", menu_init),
        "2": ("Importar datos", "Procesa una exportacion oficial o CSV.", menu_import),
        "3": ("Agregar nodo", "Captura conexiones indirectas a mano.", menu_add_node),
        "4": ("Analizar grafo", "Genera reporte y metricas de red.", menu_analyze),
    }
    if TEXTUAL_AVAILABLE:
        while True:
            try:
                choice = OsintMenuApp(actions).run()
            except (KeyboardInterrupt, EOFError):
                console.print(f"\n[{MENU_ACCENT}]Hasta luego.[/{MENU_ACCENT}]")
                return
            if not choice or choice == "0":
                console.print(f"\n[{MENU_ACCENT}]Hasta luego.[/{MENU_ACCENT}]")
                return
            label, _, func = actions[choice]
            console.rule(f"[bold {MENU_ACCENT}]{label}[/bold {MENU_ACCENT}]", style=MENU_ACCENT)
            console.print()
            try:
                func()
            except SystemExit:
                pass
            except (KeyboardInterrupt, EOFError):
                console.print(f"\n[yellow]Cancelado.[/yellow]")
            ask_text("Presiona Enter para volver al panel", default="")
        return

    print_banner()
    while True:
        console.print()
        print_menu(actions)
        try:
            choice = Prompt.ask(
                f"\n[bold {MENU_ACCENT}]›[/bold {MENU_ACCENT}] Elige una opcion",
                choices=list(actions) + ["0"],
                show_choices=False,
            )
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[{MENU_ACCENT}]Hasta luego.[/{MENU_ACCENT}]")
            return
        if choice == "0":
            console.print(f"\n[{MENU_ACCENT}]Hasta luego.[/{MENU_ACCENT}]")
            return
        label, _, func = actions[choice]
        console.rule(f"[bold {MENU_ACCENT}]{label}[/bold {MENU_ACCENT}]", style=MENU_ACCENT)
        console.print()
        try:
            func()
        except SystemExit:
            pass
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[yellow]Cancelado.[/yellow]")
        console.print()


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

    p_import = sub.add_parser(
        "import",
        help="Import an official platform export (or a custom CSV) as level 1",
        description=(
            "Import a platform's official data export as level-1 nodes. Available platforms: "
            + ", ".join(available_platforms())
            + ". See plugins/<platform>.py for what each one expects."
        ),
    )
    p_import.add_argument("--vault", required=True, type=Path)
    p_import.add_argument("--platform", required=True, choices=available_platforms(), help="Which import plugin to use")
    p_import.add_argument("--export-dir", required=True, type=Path, help="Folder with the unzipped export (or your CSV, for --platform generic)")
    p_import.add_argument("--dry-run", action="store_true")
    generic_group = p_import.add_argument_group("generic platform options")
    generic_group.add_argument("--file", default=None, help="[generic] CSV filename (default: the single .csv found in --export-dir)")
    generic_group.add_argument("--handle-col", default="handle", help="[generic] column with the handle/username (default: handle)")
    generic_group.add_argument("--name-col", default="name", help="[generic] column with the display name (default: name)")
    generic_group.add_argument("--relationship-col", default="relationship", help="[generic] column with the relationship tag (default: relationship)")
    generic_group.add_argument("--default-relationship", default="observed_public", help="[generic] relationship to use when the column is empty/missing")
    p_import.set_defaults(func=cmd_import)

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

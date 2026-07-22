"""
Presentation-agnostic core logic for osint-sna: vault I/O, importing,
node scaffolding and graph analysis. No Rich, no Flask, no argparse —
both osint_sna.py (CLI) and app.py (web app) call these same functions
and format the results however fits their surface.

Errors are raised as OsintError subclasses (each carrying an HTTP-ish
status_code) instead of printing and calling sys.exit, so callers decide
how to present a failure.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import networkx as nx
import yaml

from plugins import available_platforms, get_importer  # noqa: F401 (re-exported for callers)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
NODE_FOLDERS = ["01-Level-0", "02-Level-1", "03-Level-2", "04-Level-3"]
PLATFORM_DISPLAY_NAMES = {"linkedin": "LinkedIn", "twitter": "X / Twitter"}


def platform_display_name(platform: str) -> str:
    return PLATFORM_DISPLAY_NAMES.get(platform, platform.capitalize())


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class OsintError(Exception):
    """Base for all user-facing errors. status_code is HTTP-ish for the web app."""

    status_code = 400


class VaultExistsError(OsintError):
    status_code = 409


class VaultNotInitializedError(OsintError):
    status_code = 404


class EmptyVaultError(OsintError):
    status_code = 404


class EgoNotFoundError(OsintError):
    status_code = 422


class ImporterError(OsintError):
    status_code = 400


class NodeExistsError(OsintError):
    status_code = 409

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"Already exists: {path}. Not overwriting.")


# ---------------------------------------------------------------------------
# Note I/O
# ---------------------------------------------------------------------------

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
        raise VaultNotInitializedError(
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
and analyze it with graph theory (degrees of separation, Bacon number,
Watts-Strogatz small-world).

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

## Workflow

1. Fill in your own node in `01-Level-0/ME.md`.
2. **Automated level 1:** request your official data export from the
   platform, then run one of its import plugins (from the web app's
   "Import data" form, or `osint-sna import --platform instagram --vault . --export-dir /path/to/export`).
   Have a custom dataset (a spreadsheet, a CSV from somewhere else)? Use the
   generic plugin instead of writing your own parser.
3. **Level 1 for unsupported platforms / levels 2 and 3 (assisted manual):**
   no mainstream social network exposes a public API to see another
   account's connections — automating that would be scraping and would
   violate their Terms of Service. It's surveyed by looking at public
   profiles and recorded with the "Add node" form (or
   `osint-sna add-node --vault . --name "..." --handle ... --degree 2 --via bridge-node-slug`).
4. **Analyze & visualize:** run `osint-sna serve --vault .` and open the
   local web app — it shows the interactive graph and every metric
   (distances, centrality, communities, small-world signature, homophily)
   in one place, and writes `00-Dashboard/Graph-Analysis.md` as a byproduct.
   This vault is still plain markdown, so Obsidian's Graph View or a
   `.graphml` export to Gephi keep working too, if you want them.

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
<!-- These links draw the edges in the graph. Level 1 always links to ME. -->
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


def init_vault(vault: Path, name: str, project_name: str | None, platforms: list[str]) -> dict:
    if vault.exists() and any(vault.iterdir()):
        raise VaultExistsError(f"{vault} already exists and is not empty. Pick another path or empty it first.")
    for folder in NODE_FOLDERS + ["90-Templates", "00-Dashboard", ".obsidian"]:
        (vault / folder).mkdir(parents=True, exist_ok=True)

    platforms_yaml = ", ".join(platforms)

    me_path = vault / "01-Level-0" / "ME.md"
    write_note(
        me_path,
        {
            "name": name,
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
        f"\n# {name} (origin node)\n\nSee [[00-Dashboard/README|README]] for the full workflow.\n",
    )

    (vault / "90-Templates" / "Person-Template.md").write_text(
        PERSON_TEMPLATE.format(platforms=platforms_yaml, today=date.today().isoformat()),
        encoding="utf-8",
    )

    readme_path = vault / "00-Dashboard" / "README.md"
    readme_path.write_text(
        DASHBOARD_README_TEMPLATE.format(project_name=project_name or vault.name, platforms=platforms_yaml),
        encoding="utf-8",
    )

    (vault / ".obsidian" / "graph.json").write_text(GRAPH_JSON, encoding="utf-8")

    return {"vault": vault, "me_path": me_path, "readme_path": readme_path}


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


@dataclass
class ImportResult:
    platform: str
    total: int
    created: int
    updated: int
    relationship_counts: dict
    dry_run: bool


def import_connections(vault: Path, platform: str, export_dir: Path, dry_run: bool = False, **options) -> ImportResult:
    require_vault(vault)
    try:
        importer = get_importer(platform)
    except KeyError as e:
        raise ImporterError(str(e)) from e

    try:
        connections = importer.parse(
            export_dir,
            file=options.get("file"),
            handle_col=options.get("handle_col"),
            name_col=options.get("name_col"),
            relationship_col=options.get("relationship_col"),
            default_relationship=options.get("default_relationship"),
        )
    except (FileNotFoundError, ValueError) as e:
        raise ImporterError(str(e)) from e

    stats = {"created": 0, "updated": 0}
    for connection in connections:
        action = upsert_connection_note(vault, platform, connection, dry_run)
        stats[action] += 1

    relationship_counts = dict(sorted(Counter(c.relationship for c in connections).items()))

    return ImportResult(
        platform=platform,
        total=len(connections),
        created=stats["created"],
        updated=stats["updated"],
        relationship_counts=relationship_counts,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# add-node
# ---------------------------------------------------------------------------

def add_node(
    vault: Path, name: str, handle: str, platform: str, degree: int, via: str,
    relationship: str = "observed_public", location: str = "", notes: str = "",
) -> Path:
    require_vault(vault)
    folder_name = "03-Level-2" if degree == 2 else "04-Level-3"
    folder = vault / folder_name
    folder.mkdir(exist_ok=True)
    path = folder / f"{slugify(handle)}.md"

    if path.exists():
        raise NodeExistsError(path)

    fm = {
        "name": name,
        "aliases": [],
        "type": "person",
        "platforms": [platform],
        "handles": {platform: f"@{handle}"},
        "degree": degree,
        "connected_via": [f"[[{via}]]"],
        "relationship": [relationship],
        "first_observed": date.today().isoformat(),
        "location": location,
        "bio": "",
        "tags": [f"level-{degree}", platform],
        "notes": notes,
    }
    body = f"""
# {name}

## Profile
- **Handle:** @{handle}
- **Platform:** {platform_display_name(platform)}
- **Stated location:** {location}

## Position in the network
- **Degree:** {degree}
- **Relationship:** {relationship}
- **Via:** [[{via}]]

## Connections
- [[{via}]]

## Context notes
{notes}
"""
    write_note(path, fm, body)
    return path


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
    raise EgoNotFoundError("Couldn't find the ego node (node_role: ego in the frontmatter, or name it ME.md).")


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


@dataclass
class AnalysisResult:
    notes: dict
    G: nx.DiGraph
    ego: str
    out_distances: dict
    in_distances: dict
    unreachable: set
    weak_components: list
    main_component: nx.Graph
    clustering: float
    reciprocity: float | None
    path_len: float | None
    diameter: int | None
    c_rand: float | None
    l_rand: float | None
    communities: list
    community_of: dict
    modularity: float | None
    betweenness: dict
    closeness: dict
    eigenvector: dict
    pagerank: dict
    density: float
    level_homophily: float | None
    platform_homophily: float | None


def analyze_graph(vault: Path) -> AnalysisResult:
    require_vault(vault)
    notes = load_notes(vault)
    if not notes:
        raise EmptyVaultError("Couldn't find any person notes in the vault yet.")

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

    return AnalysisResult(
        notes=notes, G=G, ego=ego, out_distances=out_distances, in_distances=in_distances,
        unreachable=unreachable, weak_components=weak_components, main_component=main_component,
        clustering=clustering, reciprocity=reciprocity, path_len=path_len, diameter=diameter,
        c_rand=c_rand, l_rand=l_rand, communities=communities, community_of=community_of,
        modularity=modularity, betweenness=betweenness, closeness=closeness, eigenvector=eigenvector,
        pagerank=pagerank, density=density, level_homophily=level_homophily,
        platform_homophily=platform_homophily,
    )


def render_analysis_markdown(result: AnalysisResult) -> str:
    notes = result.notes
    G = result.G

    lines = []
    lines.append("# Graph analysis\n")
    lines.append("*Automatically generated by osint-sna. Do not edit by hand — it gets overwritten.*\n")
    lines.append(f"- Total nodes: **{G.number_of_nodes()}**")
    lines.append(f"- Total directed edges: **{G.number_of_edges()}**")
    lines.append(f"- Weakly connected components: **{len(result.weak_components)}** (sizes: {[len(c) for c in result.weak_components]})")
    lines.append(f"- Nodes with no directed path to/from you: **{len(result.unreachable)}**")
    if result.reciprocity is not None:
        lines.append(f"- Reciprocity (share of edges that are followed back): **{result.reciprocity:.1%}**\n")
    else:
        lines.append("- Reciprocity: not defined (no edges yet)\n")

    lines.append("## Degrees of separation (Bacon number relative to you)\n")
    lines.append("| Node | Name | OSINT level (manual) | You → them | Them → you |")
    lines.append("|---|---|---|---|---|")
    all_stems = sorted(
        set(result.out_distances) | set(result.in_distances),
        key=lambda s: (result.out_distances.get(s, math.inf), result.in_distances.get(s, math.inf)),
    )
    for stem in all_stems:
        fm = notes[stem]["fm"]
        out_d = result.out_distances.get(stem, "—")
        in_d = result.in_distances.get(stem, "—")
        lines.append(f"| [[{stem}]] | {fm.get('name', stem)} | {fm.get('degree', '?')} | {out_d} | {in_d} |")
    if result.unreachable:
        lines.append("\n**No directed path detected in either direction (check `[[...]]` links, `connected_via` or `relationship`):**")
        for stem in sorted(result.unreachable):
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
    centrality_order = sorted(G.nodes, key=lambda n: result.pagerank.get(n, 0), reverse=True)[:15]
    in_degree = dict(G.in_degree)
    out_degree = dict(G.out_degree)
    for stem in centrality_order:
        name = notes[stem]["fm"].get("name", stem)
        lines.append(
            f"| [[{stem}]] | {name} | {in_degree.get(stem, 0)} | {out_degree.get(stem, 0)} | "
            f"{result.betweenness.get(stem, 0):.3f} | {result.closeness.get(stem, 0):.3f} | "
            f"{result.eigenvector.get(stem, 0):.3f} | {result.pagerank.get(stem, 0):.3f} |"
        )
    if len(G.nodes) > 15:
        lines.append(f"\n*(showing top 15 of {len(G.nodes)} nodes by PageRank)*")

    lines.append("\n## Community detection (Louvain)\n")
    lines.append(
        f"- Communities found: **{len(result.communities)}** "
        + (f"— modularity: **{result.modularity:.3f}**" if result.modularity is not None else "")
    )
    lines.append(
        "*Modularity above ~0.3 usually means the communities are meaningfully denser internally than "
        "you'd expect by chance — real subgroups, not an artifact of the algorithm.*\n"
    )
    lines.append("| Community | Size | Members |")
    lines.append("|---|---|---|")
    for idx, members in enumerate(result.communities):
        member_links = ", ".join(f"[[{stem}]]" for stem in sorted(members, key=lambda s: notes[s]["fm"].get("name", s)))
        lines.append(f"| {idx} | {len(members)} | {member_links} |")

    lines.append("\n## Small-world metric (Watts-Strogatz)\n")
    lines.append("*Computed on the undirected projection of the graph (direction is ignored here).*\n")
    lines.append(f"- Average clustering coefficient (whole graph): **{result.clustering:.3f}**")
    if result.path_len is not None:
        lines.append(f"- Average path length (main component, {result.main_component.number_of_nodes()} nodes): **{result.path_len:.3f}**")
        lines.append(f"- Diameter of the main component: **{result.diameter}**")
    else:
        lines.append("- The main component is not fully connected or has only 1 node: average path length not computed.")
    if result.c_rand is not None:
        lines.append(f"- Equivalent random-graph baseline: C_rand ≈ **{result.c_rand:.4f}**, L_rand ≈ **{result.l_rand:.3f}**")
        lines.append(
            "- Interpretation: if your real clustering is *much higher* than C_rand and your path length "
            "is *similar to or somewhat higher* than L_rand, your network shows the 'small-world' "
            "signature (dense clusters + short shortcuts), just like Kevin Bacon's collaboration network."
        )

    lines.append("\n## Network density & homophily\n")
    lines.append(
        f"- Density: **{result.density:.4f}** — share of all possible directed connections that actually exist "
        f"(1.0 would mean everyone follows everyone)."
    )
    if result.level_homophily is not None:
        lines.append(
            f"- Homophily by OSINT level: **{result.level_homophily:+.3f}** — positive means people mostly "
            "connect within their own level (1/2/3), negative means connections mostly cross levels."
        )
    else:
        lines.append("- Homophily by OSINT level: not defined (needs more than one level with edges between them).")
    if result.platform_homophily is not None:
        lines.append(
            f"- Homophily by platform: **{result.platform_homophily:+.3f}** — positive means people mostly "
            "connect within the same platform, negative means connections mostly cross platforms."
        )
    else:
        lines.append("- Homophily by platform: not defined (needs more than one platform with edges between them).")
    lines.append(
        "\n*Homophily here is the attribute assortativity coefficient (Newman): ranges from -1 (perfectly "
        "cross-cutting) to +1 (perfectly segregated by that attribute), 0 means the attribute doesn't "
        "predict who connects to whom.*"
    )

    return "\n".join(lines) + "\n"


def write_analysis_report(vault: Path, text: str) -> Path:
    out_path = vault / "00-Dashboard" / "Graph-Analysis.md"
    out_path.write_text(text, encoding="utf-8")
    return out_path


def export_graphml(vault: Path, G: nx.DiGraph) -> Path:
    gpath = vault / "00-Dashboard" / "graph.graphml"
    nx.write_graphml(G, gpath)
    return gpath

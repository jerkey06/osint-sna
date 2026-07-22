# osint-sna

Tool for practicing OSINT and Social Network Analysis (SNA) by mapping your
own social network as a graph. Data lives as plain markdown notes (a vault,
compatible with [Obsidian](https://obsidian.md) if you want to open it there
too), and a local web app shows the interactive graph and every metric —
distances, centrality, communities, small-world signature, homophily — in
one page, instead of juggling Obsidian's Graph View and a separate Gephi
export. Built for exercises on degrees of separation, Bacon number, and
small-world theory (Watts-Strogatz) applied to your own social footprint.

## What it does

- **`serve`** — starts the local web app: an interactive graph (colored by
  OSINT level, community, or platform; sized by a centrality metric of your
  choice) alongside every metric `analyze` computes, plus forms to import
  data and add nodes without leaving the browser. Runs at
  `http://127.0.0.1:8765/` by default and opens automatically. Activates
  automatically if you run `osint-sna` without any subcommand.
- **`init`** — scaffolds a brand new vault: folders by degree of
  separation (level 0 = you, level 1 = direct connections, level 2 = contacts
  of your contacts, level 3 = indirect surroundings), a person-node template,
  a dashboard, and a Graph View colored by level.
- **`import`** — plugin-based importer: parses an official platform export
  (or a custom CSV) and automatically generates the level-1 notes, with the
  relationship computed per platform. It's idempotent: running it again
  refreshes the network data without overwriting what you edited by hand
  (bio, notes, tags). See [Import plugins](#import-plugins) below.
- **`add-node`** — quick scaffolding for level-2/3 nodes surveyed by hand
  (name, handle, degree, bridge node), without rewriting the YAML
  frontmatter every time.
- **`analyze`** — builds the real graph from the vault's `[[wikilinks]]` as a
  **directed graph** (with [networkx](https://networkx.org/)), since
  following someone on a real social network is asymmetric, and computes:
  - Directed distance (BFS) both ways: how many hops until you can *reach*
    each node by following outgoing edges, and how many hops until each node
    can *reach you* — your "Bacon number" in both directions.
  - Reciprocity: what share of edges are followed back.
  - **Centrality**, one table with six angles on "who matters": in-degree /
    out-degree (followers vs. following), betweenness (bridge people who
    connect otherwise-separate parts of your network), closeness (how fast
    a node's influence reaches everyone else), and eigenvector centrality /
    PageRank (importance by *who* points at you, not just how many —
    someone followed by a handful of very central people can outrank
    someone with more but less-connected followers).
  - **Community detection** (Louvain modularity optimization): groups nodes
    into densely-connected subgroups automatically, with a modularity score
    to tell whether those communities are real structure or noise.
  - **Density & homophily**: what share of possible connections actually
    exist, and whether people mostly connect within their own OSINT level
    or platform (homophily) or mostly cross those lines (heterophily) —
    the attribute assortativity coefficient, -1 to +1.
  - Average clustering coefficient and average path length (on the
    undirected projection of the graph), compared against an equivalent
    random graph, to check for the small-world signature.
  - Optional export to `.graphml` (directed) to open in
    [Gephi](https://gephi.org/).

## Import plugins

Every platform importer is a self-contained file under [`plugins/`](plugins/),
implementing a tiny `Importer` interface (see [`plugins/base.py`](plugins/base.py)):
given an export folder, return a list of `Connection(handle, name,
relationship, first_observed, extra)`. `osint-sna import` discovers them
automatically — no registration step, no changes anywhere else.

| Platform | File | What it reads | Relationship |
|---|---|---|---|
| `instagram` | `plugins/instagram.py` | `followers_1.json` / `following.json` | `follows_me` / `i_follow` / `mutual` |
| `linkedin` | `plugins/linkedin.py` | `Connections.csv` | always `mutual` (invites are accepted by both sides) |
| `twitter` | `plugins/twitter.py` | `data/follower.js` / `data/following.js` | `follows_me` / `i_follow` / `mutual` — X's export only has numeric account IDs, not handles, so notes are created under the ID with a profile link to identify them by hand |
| `generic` | `plugins/generic.py` | any CSV, with column names you choose | whatever's in your relationship column (or a fixed default) |

```bash
osint-sna import --platform instagram --vault ~/MySocialNetwork --export-dir /path/to/export
osint-sna import --platform linkedin  --vault ~/MySocialNetwork --export-dir /path/to/export
osint-sna import --platform twitter   --vault ~/MySocialNetwork --export-dir /path/to/export

# Custom dataset: any CSV, columns mapped via flags
osint-sna import --platform generic --vault ~/MySocialNetwork --export-dir ~/data \
  --file contacts.csv --handle-col handle --name-col name \
  --relationship-col relationship --default-relationship observed_public
```

Run `osint-sna import --help` to see the full list of installed platforms.

**Writing your own plugin:** drop a new `plugins/whatever.py` that subclasses
`Importer` (platform name, `parse(export_dir, **options) -> list[Connection]`)
and ends with `PLUGIN = YourClass`. It'll show up in `--platform` choices and
the web app's Import form automatically — see any existing plugin as a template.

## Why it exists

Instagram (and most social networks) don't expose a public API to see
another account's connections — automating that would be scraping and would
violate their Terms of Service. This tool only automates what's legitimate
to automate: **your own data**, obtained via the official export every
platform is required to offer you ("Download your information"). Levels 2
and 3 are surveyed by hand, by looking at public profiles, and the tool just
saves you the friction of writing the YAML frontmatter.

## Installation

```bash
git clone <this-repo-url> osint-sna-tool
cd osint-sna-tool
./install.sh
```

This creates a local virtual environment (`venv/`) with the dependencies
(`networkx`, `numpy`, `scipy`, `pyyaml`, `rich`, `flask`) and publishes an
executable wrapper at `~/.local/bin/osint-sna`. Make sure `~/.local/bin` is
on your `PATH`.

Requires Python 3.9+.

## Usage

### Web app

```bash
osint-sna
# or explicitly, with options:
osint-sna serve --vault ~/MySocialNetwork --port 8765
```

Starts a local Flask server at `http://127.0.0.1:8765/` and opens it in your
browser. One page shows the interactive graph (drag, zoom, click a node for
its profile and centrality figures; toggle coloring by OSINT level,
community, or platform; toggle sizing by any centrality metric) and the same
summary metrics `analyze` computes, side by side. "Import data" and "Add
node" buttons open forms for those workflows without touching the terminal.
Everything runs against the vault path typed in the top bar — point it at an
existing vault, or create one from the empty-state prompt. `--no-browser`
skips the automatic tab open (e.g. on a headless machine you're tunneling to).

### Command-line usage (scriptable)

```bash
# 1. Create a new vault
osint-sna init --vault ~/MySocialNetwork --name "Your Name" --platforms instagram

# 2. Import an official export (level 1, automated) — see Import plugins below
#    Instagram -> Settings -> Accounts Center -> Your information and
#    permissions -> Export your information -> "Followers and following" -> JSON
osint-sna import --platform instagram --vault ~/MySocialNetwork --export-dir /path/to/export

# 3. Add level 2/3 nodes (surveyed by hand)
osint-sna add-node --vault ~/MySocialNetwork \
  --name "Display name" --handle instagram_handle \
  --degree 2 --via bridge-node-slug --relationship follows_them

# 4. Analyze the graph
osint-sna analyze --vault ~/MySocialNetwork --graphml
```

Run `osint-sna serve --vault ~/MySocialNetwork` to see the graph and metrics.
The vault is still plain markdown, so it also opens fine in Obsidian if you
want its native Graph View (preconfigured with colors by level) or the
`--graphml` export in Gephi; for the dashboard tables, install the community
plugin [Dataview](https://github.com/blacksmithgu/obsidian-dataview).

## Ethics notes

- The only data obtained automatically is your own, via the platform's
  official export — no scraping of other people's accounts is done.
- For level 2/3 nodes (people without explicit consent to be profiled),
  store the minimum needed for graph analysis, not an extended profile.
- If you're going to share a vault generated with this tool, consider
  anonymizing levels 2/3 first.

## License

MIT — see [LICENSE](LICENSE).

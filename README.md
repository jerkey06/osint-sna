# osint-sna

CLI for practicing OSINT and Social Network Analysis (SNA) by mapping your own
social network as a graph in [Obsidian](https://obsidian.md). Built for
exercises on degrees of separation, Bacon number, and small-world theory
(Watts-Strogatz) applied to your own social footprint.

## What it does

- **`menu`** — interactive terminal interface: a full-screen TUI with keyboard
  navigation. Move with the arrow keys, press Enter to select an operation,
  then answer the prompts for that workflow. Activates automatically if you
  run `osint-sna` without any subcommand.
- **`init`** — scaffolds a brand new Obsidian vault: folders by degree of
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
  - In-degree vs. out-degree centrality: who's followed the most in your
    graph vs. who follows the most.
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
the interactive menu automatically — see any existing plugin as a template.

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
(`networkx`, `pyyaml`, `rich`) and publishes an executable wrapper at
`~/.local/bin/osint-sna`. Make sure `~/.local/bin` is on your `PATH`.

Requires Python 3.9+.

## Usage

### Interactive terminal interface

```bash
osint-sna
# or explicitly:
osint-sna menu
```

Shows a full-screen OSINT-style terminal menu. Move with the arrow keys,
press Enter to select an operation, or press `q` / Esc to exit. Each workflow
still prompts for the data it needs, so you don't have to remember the flags
for each subcommand.

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

Open the resulting vault in Obsidian. The Graph View comes preconfigured
with colors by level. For the dashboard tables, install the community
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

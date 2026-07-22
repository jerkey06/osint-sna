# osint-sna

CLI for practicing OSINT and Social Network Analysis (SNA) by mapping your own
social network as a graph in [Obsidian](https://obsidian.md). Built for
exercises on degrees of separation, Bacon number, and small-world theory
(Watts-Strogatz) applied to your own social footprint.

## What it does

- **`menu`** — interactive terminal interface: a numbered menu that prompts
  for the data each operation needs and calls the functions below. Activates
  automatically if you run `osint-sna` without any subcommand.
- **`init`** — scaffolds a brand new Obsidian vault: folders by degree of
  separation (level 0 = you, level 1 = direct connections, level 2 = contacts
  of your contacts, level 3 = indirect surroundings), a person-node template,
  a dashboard, and a Graph View colored by level.
- **`import-instagram`** — parses your official Instagram data export
  (followers/following) and automatically generates the level-1 notes, with
  the relationship computed (`mutual` / `follows_me` / `i_follow`). It's
  idempotent: running it again refreshes the network data without
  overwriting what you edited by hand (bio, notes, tags).
- **`add-node`** — quick scaffolding for level-2/3 nodes surveyed by hand
  (name, handle, degree, bridge node), without rewriting the YAML
  frontmatter every time.
- **`analyze`** — builds the real graph from the vault's `[[wikilinks]]`
  (with [networkx](https://networkx.org/)) and computes:
  - Real distance (BFS) from you to each node — your "Bacon number"
    relative to anyone in the vault.
  - Average clustering coefficient and average path length, compared
    against an equivalent random graph, to check for the small-world
    signature.
  - The most central nodes (hubs) of your network.
  - Optional export to `.graphml` to open in [Gephi](https://gephi.org/).

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
(`networkx`, `pyyaml`) and publishes an executable wrapper at
`~/.local/bin/osint-sna`. Make sure `~/.local/bin` is on your `PATH`.

Requires Python 3.9+.

## Usage

### Interactive terminal interface

```bash
osint-sna
# or explicitly:
osint-sna menu
```

Shows a numbered menu (create vault, import Instagram, add node, analyze)
that prompts for the data on the console, so you don't have to remember the
flags for each subcommand.

### Command-line usage (scriptable)

```bash
# 1. Create a new vault
osint-sna init --vault ~/MySocialNetwork --name "Your Name" --platforms instagram

# 2. Import your official Instagram export (level 1, automated)
#    Instagram -> Settings -> Accounts Center -> Your information and
#    permissions -> Export your information -> "Followers and following" -> JSON
osint-sna import-instagram --vault ~/MySocialNetwork --export-dir /path/to/export

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

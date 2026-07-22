#!/usr/bin/env python3
"""
osint-sna — tool for practicing OSINT / Social Network Analysis (SNA)
by mapping your own social network as a graph.

Subcommands:
  init      Creates a brand new vault (folders, templates, ME node).
  import    Imports an official platform export (or a custom CSV) as level-1 nodes.
  add-node  Quick scaffolding for level-2/3 nodes (surveyed by hand).
  analyze   Computes degrees of separation, clustering and small-world metrics.
  serve     Starts the local web app (interactive graph + metrics). Default
            action if no subcommand is given.

Import plugins live in plugins/ (one file per platform: instagram.py,
linkedin.py, twitter.py, generic.py for custom CSV datasets). Run
'osint-sna import --help' to see which platforms are available.

Vault data is plain markdown with YAML frontmatter (one file per person,
[[wikilinks]] for edges) so it stays git-friendly and hand-editable, and can
still be opened directly in Obsidian if you want its native Graph View too.

Each subcommand has its own --help with details.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

import core

console = Console()


def die(message: str):
    console.print(f"[bold red]✗[/bold red] {message}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def cmd_init(args):
    try:
        info = core.init_vault(args.vault, args.name, args.project_name, args.platforms)
    except core.OsintError as e:
        die(str(e))
        return
    console.print(f"[green]✓[/green] Vault created at [bold]{info['vault']}[/bold]")
    console.print(f"  [dim]1.[/dim] Fill in your handle at {info['me_path']}")
    console.print(f"  [dim]2.[/dim] Read {info['readme_path']} for the workflow")


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

def cmd_import(args):
    try:
        result = core.import_connections(
            args.vault, args.platform, args.export_dir, args.dry_run,
            file=getattr(args, "file", None),
            handle_col=getattr(args, "handle_col", None),
            name_col=getattr(args, "name_col", None),
            relationship_col=getattr(args, "relationship_col", None),
            default_relationship=getattr(args, "default_relationship", None),
        )
    except core.OsintError as e:
        die(str(e))
        return

    if result.total == 0:
        console.print("[yellow]![/yellow] No connections found in that export.")
        return

    table = Table(box=box.SIMPLE, show_header=False, border_style="dim")
    table.add_column(style="dim")
    table.add_column(justify="right", style="bold")
    table.add_row("Platform", result.platform)
    table.add_row("Total level-1 accounts", str(result.total))
    for relationship, count in result.relationship_counts.items():
        table.add_row(relationship, str(count))
    table.add_row("Notes created", str(result.created))
    table.add_row("Notes updated", str(result.updated))
    console.print(table)
    if result.dry_run:
        console.print("[yellow]dry-run: nothing was written[/yellow]")
    else:
        console.print("[green]✓[/green] Level-1 notes are up to date")


# ---------------------------------------------------------------------------
# add-node
# ---------------------------------------------------------------------------

def cmd_add_node(args):
    try:
        path = core.add_node(
            args.vault, args.name, args.handle, args.platform, args.degree,
            args.via, args.relationship, args.location, args.notes,
        )
    except core.NodeExistsError as e:
        console.print(f"[yellow]![/yellow] {e}")
        return
    except core.OsintError as e:
        die(str(e))
        return
    console.print(f"[green]✓[/green] Created: [bold]{path}[/bold]")


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

def cmd_analyze(args):
    try:
        result = core.analyze_graph(args.vault)
    except core.OsintError as e:
        die(str(e))
        return

    report = core.render_analysis_markdown(result)
    out_path = core.write_analysis_report(args.vault, report)

    summary = Table(title="Graph summary", box=box.ROUNDED, border_style="cyan", show_header=False)
    summary.add_column(style="dim")
    summary.add_column(justify="right", style="bold")
    summary.add_row("Nodes", str(result.G.number_of_nodes()))
    summary.add_row("Directed edges", str(result.G.number_of_edges()))
    summary.add_row("Weakly connected components", str(len(result.weak_components)))
    summary.add_row("Reciprocity", f"{result.reciprocity:.1%}" if result.reciprocity is not None else "n/a")
    summary.add_row("Density", f"{result.density:.4f}")
    summary.add_row(
        "Communities (Louvain)",
        f"{len(result.communities)}" + (f" (Q={result.modularity:.3f})" if result.modularity is not None else ""),
    )
    summary.add_row("Avg. clustering", f"{result.clustering:.3f}")
    if result.path_len is not None:
        summary.add_row("Avg. path length", f"{result.path_len:.3f}")
        summary.add_row("Diameter", str(result.diameter))
    if result.G.number_of_nodes():
        top_stem = max(result.G.nodes, key=lambda n: result.pagerank.get(n, 0))
        summary.add_row("Top by PageRank", result.notes[top_stem]["fm"].get("name", top_stem))
    console.print(summary)

    console.print(f"[green]✓[/green] Report written to [bold]{out_path}[/bold]")

    if args.graphml:
        gpath = core.export_graphml(args.vault, result.G)
        console.print(f"[green]✓[/green] Gephi export: [bold]{gpath}[/bold]")


# ---------------------------------------------------------------------------
# serve (local web app)
# ---------------------------------------------------------------------------

def cmd_serve(args):
    from app import run_server  # lazy import: keeps Flask off the hot path for other subcommands

    url = f"http://127.0.0.1:{args.port}/"
    console.print(f"[green]✓[/green] Starting osint-sna web app at [bold]{url}[/bold]")
    if args.vault:
        console.print(f"  [dim]Default vault:[/dim] {args.vault}")
    console.print("  [dim]Press Ctrl+C to stop.[/dim]")
    try:
        run_server(vault=args.vault, port=args.port, open_browser=not args.no_browser)
    except KeyboardInterrupt:
        console.print("\n[cyan]Stopped.[/cyan]")


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
            + ", ".join(core.available_platforms())
            + ". See plugins/<platform>.py for what each one expects."
        ),
    )
    p_import.add_argument("--vault", required=True, type=Path)
    p_import.add_argument("--platform", required=True, choices=core.available_platforms(), help="Which import plugin to use")
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

    p_serve = sub.add_parser("serve", help="Start the local web app (default if no subcommand is given)")
    p_serve.add_argument("--vault", type=Path, default=None, help="Vault to open by default (you can still switch it in the web app)")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--no-browser", action="store_true", help="Don't open a browser tab automatically")
    p_serve.set_defaults(func=cmd_serve)

    args = ap.parse_args()
    if args.command is None:
        cmd_serve(argparse.Namespace(vault=None, port=8765, no_browser=False))
    else:
        args.func(args)


if __name__ == "__main__":
    main()

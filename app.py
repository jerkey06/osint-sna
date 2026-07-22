"""
Local web app for osint-sna: a single Flask process serving a static
Cytoscape.js page plus a small JSON API. Stateless per request — the vault
path travels with every call (query param on GET, JSON body field on POST)
instead of living in a server-side session, since this is a single-user
tool meant to run on localhost.
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file

import core

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["DEFAULT_VAULT"] = None


@app.errorhandler(core.OsintError)
def handle_osint_error(err: core.OsintError):
    return jsonify({"error": str(err)}), err.status_code


def _vault_from(value: str | None) -> Path:
    if not value:
        raise core.OsintError("Missing 'vault' path.")
    return Path(value).expanduser()


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/default-vault")
def default_vault():
    vault = app.config["DEFAULT_VAULT"]
    return jsonify({"vault": str(vault) if vault else None})


@app.get("/api/platforms")
def platforms():
    return jsonify({"platforms": core.available_platforms()})


@app.get("/api/vault/status")
def vault_status():
    vault = _vault_from(request.args.get("vault"))
    exists = vault.exists()
    initialized = exists and (vault / "01-Level-0").exists()
    return jsonify({"vault": str(vault), "exists": exists, "initialized": initialized})


@app.post("/api/vault/init")
def vault_init():
    data = request.get_json(force=True)
    vault = _vault_from(data.get("vault"))
    platforms_list = [p.strip() for p in (data.get("platforms") or ["instagram"]) if str(p).strip()]
    info = core.init_vault(
        vault=vault,
        name=data.get("name") or "Me",
        project_name=data.get("project_name") or None,
        platforms=platforms_list or ["instagram"],
    )
    return jsonify({"ok": True, "vault": str(info["vault"]), "me_path": str(info["me_path"])})


@app.post("/api/import")
def do_import():
    data = request.get_json(force=True)
    vault = _vault_from(data.get("vault"))
    export_dir = _vault_from(data.get("export_dir"))
    result = core.import_connections(
        vault=vault,
        platform=data.get("platform"),
        export_dir=export_dir,
        dry_run=bool(data.get("dry_run", False)),
        file=data.get("file"),
        handle_col=data.get("handle_col") or "handle",
        name_col=data.get("name_col") or "name",
        relationship_col=data.get("relationship_col") or "relationship",
        default_relationship=data.get("default_relationship") or "observed_public",
    )
    return jsonify({
        "ok": True,
        "platform": result.platform,
        "total": result.total,
        "created": result.created,
        "updated": result.updated,
        "relationship_counts": result.relationship_counts,
        "dry_run": result.dry_run,
    })


@app.post("/api/add-node")
def do_add_node():
    data = request.get_json(force=True)
    vault = _vault_from(data.get("vault"))
    path = core.add_node(
        vault=vault,
        name=data.get("name"),
        handle=data.get("handle"),
        platform=data.get("platform") or "instagram",
        degree=int(data.get("degree", 2)),
        via=data.get("via"),
        relationship=data.get("relationship") or "observed_public",
        location=data.get("location") or "",
        notes=data.get("notes") or "",
    )
    return jsonify({"ok": True, "path": str(path)})


def to_cytoscape_json(result: core.AnalysisResult) -> dict:
    G = result.G
    notes = result.notes
    in_degree = dict(G.in_degree)
    out_degree = dict(G.out_degree)

    nodes = []
    for stem in G.nodes:
        fm = notes[stem]["fm"]
        nodes.append({
            "data": {
                "id": stem,
                "name": fm.get("name", stem),
                "is_ego": stem == result.ego,
                "level": fm.get("degree"),
                "platforms": fm.get("platforms", []) or [],
                "primary_platform": G.nodes[stem].get("primary_platform"),
                "handles": fm.get("handles", {}) or {},
                "location": fm.get("location", ""),
                "bio": fm.get("bio", ""),
                "notes": fm.get("notes", ""),
                "community": result.community_of.get(stem),
                "dist_from_ego": result.out_distances.get(stem),
                "dist_to_ego": result.in_distances.get(stem),
                "unreachable": stem in result.unreachable,
                "in_degree": in_degree.get(stem, 0),
                "out_degree": out_degree.get(stem, 0),
                "betweenness": result.betweenness.get(stem, 0.0),
                "closeness": result.closeness.get(stem, 0.0),
                "eigenvector": result.eigenvector.get(stem, 0.0),
                "pagerank": result.pagerank.get(stem, 0.0),
            }
        })

    edges = [
        {"data": {"id": f"{u}->{v}", "source": u, "target": v}}
        for u, v in G.edges
    ]

    summary = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "components": len(result.weak_components),
        "component_sizes": [len(c) for c in result.weak_components],
        "unreachable": len(result.unreachable),
        "reciprocity": result.reciprocity,
        "density": result.density,
        "clustering": result.clustering,
        "path_len": result.path_len,
        "diameter": result.diameter,
        "c_rand": result.c_rand,
        "l_rand": result.l_rand,
        "communities": len(result.communities),
        "modularity": result.modularity,
        "level_homophily": result.level_homophily,
        "platform_homophily": result.platform_homophily,
        "top_pagerank": notes[max(G.nodes, key=lambda n: result.pagerank.get(n, 0))]["fm"].get("name")
        if G.number_of_nodes() else None,
    }

    return {"elements": {"nodes": nodes, "edges": edges}, "summary": summary}


@app.post("/api/analyze")
def analyze():
    data = request.get_json(force=True)
    vault = _vault_from(data.get("vault"))
    result = core.analyze_graph(vault)
    report = core.render_analysis_markdown(result)
    core.write_analysis_report(vault, report)
    payload = to_cytoscape_json(result)
    if data.get("graphml"):
        gpath = core.export_graphml(vault, result.G)
        payload["graphml_path"] = str(gpath)
    return jsonify(payload)


@app.get("/api/export/graphml")
def export_graphml():
    vault = _vault_from(request.args.get("vault"))
    result = core.analyze_graph(vault)
    gpath = core.export_graphml(vault, result.G)
    return send_file(gpath, as_attachment=True, download_name="graph.graphml")


def run_server(vault: Path | None = None, port: int = 8765, open_browser: bool = True):
    app.config["DEFAULT_VAULT"] = vault
    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, use_reloader=False)

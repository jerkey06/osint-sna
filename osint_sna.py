#!/usr/bin/env python3
"""
osint-sna — herramienta para practicar OSINT / Análisis de Redes Sociales (SNA)
mapeando tu propia red social como grafo en Obsidian.

Subcomandos:
  init              Crea un vault nuevo desde cero (carpetas, plantillas, nodo YO).
  import-instagram  Importa tu export oficial de Instagram como nodos de nivel 1.
  add-node          Scaffolding rápido para nodos de nivel 2/3 (relevados a mano).
  analyze           Calcula grados de separación, clustering y métricas de mundo pequeño.

Cada subcomando tiene su propio --help con detalle.
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
NODE_FOLDERS = ["01-Nivel-0", "02-Nivel-1", "03-Nivel-2", "04-Nivel-3"]


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
    if not (vault / "01-Nivel-0").exists():
        sys.exit(
            f"{vault} no parece un vault inicializado por esta herramienta "
            f"(falta 01-Nivel-0/). Corré 'osint-sna init --vault {vault}' primero."
        )


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

DASHBOARD_README_TEMPLATE = """---
tags: [dashboard]
---

# OSINT / SNA — {project_name}

Práctica de mapeo de red social propia: representar tu red como grafo en
Obsidian y analizarla con teoría de grafos (grados de separación, número de
Bacon, mundo pequeño de Watts-Strogatz).

Plataformas de este proyecto: {platforms}.

## Estructura del vault

| Carpeta | Contenido |
|---|---|
| `01-Nivel-0/` | Vos (nodo ego, origen de todas las distancias) |
| `02-Nivel-1/` | Gente que seguís / te sigue (datos completos) |
| `03-Nivel-2/` | Contactos de tus contactos (datos parciales, vía un nodo puente) |
| `04-Nivel-3/` | Entorno indirecto (solo lo necesario para medir alcance) |
| `90-Plantillas/` | Plantilla de nodo-persona |
| `00-Dashboard/` | Esta nota + `Analisis-Grafo.md` (generado automáticamente) |

Los scripts viven fuera del vault, instalados una sola vez como el comando
`osint-sna` (ver `osint-sna --help`). No hace falta copiarlos a cada vault nuevo.

## Flujo de trabajo

1. Completá tu propio nodo en `01-Nivel-0/YO.md`.
2. **Nivel 1 automatizado (solo Instagram por ahora):**
   pedí tu export oficial (Instagram → Configuración → Centro de cuentas →
   Tu información y permisos → Exportar tu información → "Seguidores y
   seguidos" → formato JSON) y corré:
   `osint-sna import-instagram --vault . --export-dir /ruta/al/export`
3. **Nivel 1 de otras plataformas / nivel 2 y 3 (manual asistido):**
   ninguna red social mainstream expone API pública para ver las conexiones
   de una cuenta ajena — automatizar eso sería scraping y violaría sus
   Términos de Servicio. Se releva mirando perfiles públicos y se registra con:
   `osint-sna add-node --vault . --name "..." --handle ... --degree 2 --via slug-del-puente`
4. **Analizar:** `osint-sna analyze --vault .` — escribe
   `00-Dashboard/Analisis-Grafo.md` con distancias BFS reales desde vos,
   clustering, comparación con grafo aleatorio, y nodos más centrales.
5. **Visualizar:** Graph View nativo de Obsidian (coloreado por nivel, ver
   `.obsidian/graph.json`), o `--graphml` en el paso anterior para abrir en Gephi.

## Consultas Dataview

Requiere el plugin comunitario **Dataview** (Configuración → Plugins
comunitarios → Buscar "Dataview" → Instalar y activar).

```dataview
TABLE degree AS "Nivel", relationship AS "Relación"
FROM "02-Nivel-1" OR "03-Nivel-2" OR "04-Nivel-3"
SORT degree ASC
```

```dataview
TABLE length(rows) AS "Cantidad"
FROM "02-Nivel-1" OR "03-Nivel-2" OR "04-Nivel-3"
GROUP BY degree
```

## Notas éticas y de alcance

- Nivel 1 son datos tuyos, obtenidos de tu propio export oficial: sin problema.
- Nivel 2/3 son personas sin consentimiento explícito para ser perfiladas —
  guardá el mínimo necesario para el análisis de grafo (handle, relación,
  nodo puente), no un perfil extendido.
- No se hace scraping automatizado de perfiles ajenos: los únicos datos
  obtenidos por script son los tuyos propios, vía export oficial.
- Si vas a compartir este vault, considerá anonimizar nivel 2/3 antes.
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

## Perfil
- **Handle:**
- **Plataforma:**
- **Ubicación declarada:**
- **Bio:**

## Posición en la red
- **Grado:** <!-- 1, 2 o 3 -->
- **Relación:** <!-- follows_me / i_follow / mutual / observed_public -->
- **Vía (solo nivel 2/3):** <!-- [[nombre del contacto puente]] -->

## Conexiones
<!-- Estos enlaces dibujan las aristas en el Graph View. Nivel 1 siempre enlaza a YO. -->
- [[YO]]

## Notas de contexto
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
    { "query": "path:01-Nivel-0", "color": { "a": 1, "rgb": 16711680 } },
    { "query": "path:02-Nivel-1", "color": { "a": 1, "rgb": 65280 } },
    { "query": "path:03-Nivel-2", "color": { "a": 1, "rgb": 255 } },
    { "query": "path:04-Nivel-3", "color": { "a": 1, "rgb": 16776960 } }
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
        sys.exit(f"{vault} ya existe y no está vacío. Elegí otra ruta o vacialo primero.")
    for folder in NODE_FOLDERS + ["90-Plantillas", "00-Dashboard", ".obsidian"]:
        (vault / folder).mkdir(parents=True, exist_ok=True)

    platforms = args.platforms
    platforms_yaml = ", ".join(platforms)

    write_note(
        vault / "01-Nivel-0" / "YO.md",
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
            "tags": ["nivel-0", "ego"],
            "notes": "Nodo origen del grafo. Todas las distancias se calculan desde acá.",
        },
        f"\n# {args.name} (nodo origen)\n\nVer [[00-Dashboard/README|README]] para el flujo de trabajo completo.\n",
    )

    (vault / "90-Plantillas" / "Plantilla-Persona.md").write_text(
        PERSON_TEMPLATE.format(platforms=platforms_yaml, today=date.today().isoformat()),
        encoding="utf-8",
    )

    (vault / "00-Dashboard" / "README.md").write_text(
        DASHBOARD_README_TEMPLATE.format(project_name=args.project_name or vault.name, platforms=platforms_yaml),
        encoding="utf-8",
    )

    (vault / ".obsidian" / "graph.json").write_text(GRAPH_JSON, encoding="utf-8")

    print(f"Vault creado en {vault}")
    print(f"1. Completá tu handle en {vault / '01-Nivel-0' / 'YO.md'}")
    print(f"2. Leé {vault / '00-Dashboard' / 'README.md'} para el flujo de trabajo")


# ---------------------------------------------------------------------------
# import-instagram
# ---------------------------------------------------------------------------

def find_export_files(export_dir: Path):
    followers = list(export_dir.rglob("followers_1.json")) or list(export_dir.rglob("followers*.json"))
    following = list(export_dir.rglob("following.json"))
    if not followers or not following:
        sys.exit(
            f"No encontré followers_*.json / following.json bajo {export_dir}. "
            "Verificá que sea el export descomprimido y en formato JSON."
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

## Perfil
- **Handle:** @{username}
- **Plataforma:** Instagram
- **Ubicación declarada:**
- **Bio:**

## Posición en la red
- **Grado:** 1
- **Relación:** <!-- se completa automáticamente en el frontmatter -->
- **Vía (solo nivel 2/3):** n/a (nivel 1, conexión directa)

## Conexiones
- [[YO]]

## Notas de contexto
"""


def upsert_instagram_note(vault: Path, username: str, relationship: str, observed: str, dry_run: bool):
    path = vault / "02-Nivel-1" / f"{slugify(username)}.md"
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
        action = "actualizado"
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
            "tags": ["nivel-1", "instagram"],
            "notes": "",
        }
        body = default_person_body(username)
        action = "creado"
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
    stats = {"creado": 0, "actualizado": 0}

    for username in sorted(all_usernames):
        is_follower = username in followers
        is_following = username in following
        relationship = "mutual" if (is_follower and is_following) else (
            "follows_me" if is_follower else "i_follow"
        )
        observed = followers.get(username) or following.get(username)
        action = upsert_instagram_note(vault, username, relationship, observed, args.dry_run)
        stats[action] += 1

    print(f"Total cuentas nivel 1: {len(all_usernames)}")
    print(f"  Mutuas:         {sum(1 for u in all_usernames if u in followers and u in following)}")
    print(f"  Solo te siguen: {sum(1 for u in all_usernames if u in followers and u not in following)}")
    print(f"  Solo seguís:    {sum(1 for u in all_usernames if u not in followers and u in following)}")
    print(f"Notas creadas: {stats['creado']} | Notas actualizadas: {stats['actualizado']}")
    if args.dry_run:
        print("(dry-run: no se escribió nada)")


# ---------------------------------------------------------------------------
# add-node
# ---------------------------------------------------------------------------

def cmd_add_node(args):
    vault = args.vault
    require_vault(vault)
    folder_name = "03-Nivel-2" if args.degree == 2 else "04-Nivel-3"
    folder = vault / folder_name
    folder.mkdir(exist_ok=True)
    path = folder / f"{slugify(args.handle)}.md"

    if path.exists():
        print(f"Ya existe: {path}. No se sobreescribe.")
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
        "tags": [f"nivel-{args.degree}", args.platform],
        "notes": args.notes,
    }
    body = f"""
# {args.name}

## Perfil
- **Handle:** @{args.handle}
- **Plataforma:** {args.platform.capitalize()}
- **Ubicación declarada:** {args.location}

## Posición en la red
- **Grado:** {args.degree}
- **Relación:** {args.relationship}
- **Vía:** [[{args.via}]]

## Conexiones
- [[{args.via}]]

## Notas de contexto
{args.notes}
"""
    write_note(path, fm, body)
    print(f"Creado: {path}")


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
    if "YO" in notes:
        return "YO"
    sys.exit("No encontré el nodo ego (node_role: ego en el frontmatter, o llamalo YO.md).")


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
        sys.exit("No encontré notas de persona en el vault todavía.")

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
    lines.append("# Análisis de grafo\n")
    lines.append("*Generado automáticamente por `osint-sna analyze`. No editar a mano — se sobreescribe.*\n")
    lines.append(f"- Nodos totales: **{G.number_of_nodes()}**")
    lines.append(f"- Aristas totales: **{G.number_of_edges()}**")
    lines.append(f"- Componentes conexas: **{len(components)}** (tamaños: {[len(c) for c in components]})")
    lines.append(f"- Nodos sin camino detectado hacia YO: **{len(unreachable)}**\n")

    lines.append("## Grados de separación (número de Bacon respecto a vos)\n")
    lines.append("| Nodo | Nombre | Nivel OSINT (manual) | Distancia real (BFS) |")
    lines.append("|---|---|---|---|")
    for stem, dist in sorted(distances.items(), key=lambda x: x[1]):
        fm = notes[stem]["fm"]
        lines.append(f"| [[{stem}]] | {fm.get('name', stem)} | {fm.get('degree', '?')} | {dist} |")
    if unreachable:
        lines.append("\n**Sin conexión detectada (revisar enlaces `[[...]]` o `connected_via`):**")
        for stem in sorted(unreachable):
            lines.append(f"- [[{stem}]]")

    lines.append("\n## Métrica de mundo pequeño (Watts-Strogatz)\n")
    lines.append(f"- Coeficiente de clustering promedio (todo el grafo): **{clustering:.3f}**")
    if path_len is not None:
        lines.append(f"- Longitud de camino promedio (componente principal, {main_component.number_of_nodes()} nodos): **{path_len:.3f}**")
        lines.append(f"- Diámetro de la componente principal: **{diameter}**")
    else:
        lines.append("- La componente principal no está totalmente conectada o tiene 1 solo nodo: no se calcula longitud de camino promedio.")
    if c_rand is not None:
        lines.append(f"- Baseline de grafo aleatorio equivalente: C_rand ≈ **{c_rand:.4f}**, L_rand ≈ **{l_rand:.3f}**")
        lines.append(
            "- Interpretación: si tu clustering real es *mucho mayor* que C_rand y tu longitud de camino "
            "es *similar o algo mayor* que L_rand, tu red muestra la firma de 'mundo pequeño' "
            "(clusters densos + atajos cortos), igual que la red de colaboraciones de Kevin Bacon."
        )

    lines.append("\n## Nodos más centrales (hubs)\n")
    lines.append("| Nodo | Nombre | Conexiones directas |")
    lines.append("|---|---|---|")
    for stem, deg in hubs:
        lines.append(f"| [[{stem}]] | {notes[stem]['fm'].get('name', stem)} | {deg} |")

    out_path = vault / "00-Dashboard" / "Analisis-Grafo.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Reporte escrito en {out_path}")

    if args.graphml:
        gpath = vault / "00-Dashboard" / "grafo.graphml"
        nx.write_graphml(G, gpath)
        print(f"Export para Gephi: {gpath}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(prog="osint-sna", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Crear un vault nuevo desde cero")
    p_init.add_argument("--vault", required=True, type=Path)
    p_init.add_argument("--name", default="Yo", help="Tu nombre para el nodo ego")
    p_init.add_argument("--project-name", default=None, help="Nombre del proyecto para el dashboard")
    p_init.add_argument("--platforms", nargs="+", default=["instagram"], help="Plataformas a mapear (ej: instagram twitter linkedin)")
    p_init.set_defaults(func=cmd_init)

    p_ig = sub.add_parser("import-instagram", help="Importar export oficial de Instagram como nivel 1")
    p_ig.add_argument("--vault", required=True, type=Path)
    p_ig.add_argument("--export-dir", required=True, type=Path)
    p_ig.add_argument("--dry-run", action="store_true")
    p_ig.set_defaults(func=cmd_import_instagram)

    p_node = sub.add_parser("add-node", help="Agregar un nodo de nivel 2/3 relevado a mano")
    p_node.add_argument("--vault", required=True, type=Path)
    p_node.add_argument("--name", required=True)
    p_node.add_argument("--handle", required=True)
    p_node.add_argument("--platform", default="instagram")
    p_node.add_argument("--degree", type=int, choices=[2, 3], required=True)
    p_node.add_argument("--via", required=True, help="Slug del nodo puente (nombre de archivo sin .md)")
    p_node.add_argument("--relationship", default="observed_public")
    p_node.add_argument("--location", default="")
    p_node.add_argument("--notes", default="")
    p_node.set_defaults(func=cmd_add_node)

    p_analyze = sub.add_parser("analyze", help="Calcular grados de separación y métricas de mundo pequeño")
    p_analyze.add_argument("--vault", required=True, type=Path)
    p_analyze.add_argument("--graphml", action="store_true", help="También exportar grafo.graphml para Gephi")
    p_analyze.set_defaults(func=cmd_analyze)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

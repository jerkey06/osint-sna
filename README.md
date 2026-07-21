# osint-sna

CLI para practicar OSINT y Análisis de Redes Sociales (SNA) mapeando tu propia
red social como un grafo en [Obsidian](https://obsidian.md). Pensado para
ejercicios de grados de separación, número de Bacon, y la teoría del mundo
pequeño (Watts-Strogatz) aplicados a tu propia huella social.

## Qué hace

- **`init`** — scaffolda un vault de Obsidian nuevo: carpetas por grado de
  separación (nivel 0 = vos, nivel 1 = conexiones directas, nivel 2 = contactos
  de tus contactos, nivel 3 = entorno indirecto), plantilla de nodo-persona,
  dashboard, y un Graph View coloreado por nivel.
- **`import-instagram`** — parsea tu export oficial de datos de Instagram
  (followers/following) y genera automáticamente las notas de nivel 1, con la
  relación calculada (`mutual` / `follows_me` / `i_follow`). Es idempotente:
  correrlo de nuevo actualiza los datos de red sin pisar lo que hayas editado
  a mano (bio, notas, tags).
- **`add-node`** — scaffolding rápido para nodos de nivel 2/3 relevados a mano
  (nombre, handle, grado, nodo puente), sin reescribir el frontmatter YAML
  cada vez.
- **`analyze`** — construye el grafo real a partir de los `[[wikilinks]]` del
  vault (con [networkx](https://networkx.org/)) y calcula:
  - Distancia real (BFS) desde vos hacia cada nodo — tu "número de Bacon"
    respecto a cualquier persona del vault.
  - Coeficiente de clustering promedio y longitud de camino promedio,
    comparados contra un grafo aleatorio equivalente, para verificar la firma
    de mundo pequeño.
  - Los nodos más centrales (hubs) de tu red.
  - Export opcional a `.graphml` para abrir en [Gephi](https://gephi.org/).

## Por qué existe

Instagram (y la mayoría de las redes sociales) no exponen API pública para
ver las conexiones de una cuenta ajena — automatizar eso sería scraping y
violaría sus Términos de Servicio. Esta herramienta solo automatiza lo que es
legítimo automatizar: **tus propios datos**, obtenidos vía el export oficial
que cada plataforma te obliga a ofrecerte ("Descargá tu información"). Los
niveles 2 y 3 se relevan a mano, mirando perfiles públicos, y la herramienta
solo te ahorra la fricción de escribir el frontmatter YAML.

## Instalación

```bash
git clone <url-de-este-repo> osint-sna-tool
cd osint-sna-tool
./install.sh
```

Esto crea un entorno virtual local (`venv/`) con las dependencias
(`networkx`, `pyyaml`) y publica un wrapper ejecutable en `~/.local/bin/osint-sna`.
Asegurate de que `~/.local/bin` esté en tu `PATH`.

Requiere Python 3.9+.

## Uso

```bash
# 1. Crear un vault nuevo
osint-sna init --vault ~/MiRedSocial --name "Tu Nombre" --platforms instagram

# 2. Importar tu export oficial de Instagram (nivel 1, automatizado)
#    Instagram -> Configuración -> Centro de cuentas -> Tu información y
#    permisos -> Exportar tu información -> "Seguidores y seguidos" -> JSON
osint-sna import-instagram --vault ~/MiRedSocial --export-dir /ruta/al/export

# 3. Agregar nodos de nivel 2/3 (relevados a mano)
osint-sna add-node --vault ~/MiRedSocial \
  --name "Nombre visible" --handle handle_de_instagram \
  --degree 2 --via slug-del-nodo-puente --relationship follows_them

# 4. Analizar el grafo
osint-sna analyze --vault ~/MiRedSocial --graphml
```

Abrí el vault resultante en Obsidian. El Graph View viene preconfigurado con
colores por nivel. Para las tablas del dashboard instalá el plugin comunitario
[Dataview](https://github.com/blacksmithgu/obsidian-dataview).

## Notas éticas

- Los únicos datos obtenidos de forma automatizada son los tuyos propios, vía
  export oficial de la plataforma — no se hace scraping de cuentas ajenas.
- Para nodos de nivel 2/3 (personas sin consentimiento explícito para ser
  perfiladas), guardá el mínimo necesario para el análisis de grafo, no un
  perfil extendido.
- Si vas a compartir un vault generado con esta herramienta, considerá
  anonimizar los niveles 2/3 antes de hacerlo.

## Licencia

MIT — ver [LICENSE](LICENSE).

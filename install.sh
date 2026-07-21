#!/usr/bin/env bash
# Instala osint-sna: crea un venv local con las dependencias y publica un
# wrapper ejecutable en ~/.local/bin/osint-sna que apunta a este clon.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

echo "Creando entorno virtual en $DIR/venv ..."
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --upgrade pip
"$DIR/venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/osint-sna" <<EOF
#!/usr/bin/env bash
exec "$DIR/venv/bin/python" "$DIR/osint_sna.py" "\$@"
EOF
chmod +x "$BIN_DIR/osint-sna"

echo "Listo. Comando instalado en $BIN_DIR/osint-sna"
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  echo "Atención: $BIN_DIR no está en tu PATH. Agregalo a tu shell rc, ej:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
echo "Probá con: osint-sna --help"

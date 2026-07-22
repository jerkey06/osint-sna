#!/usr/bin/env bash
# Installs osint-sna: creates a local venv with the dependencies and
# publishes an executable wrapper at ~/.local/bin/osint-sna pointing at this clone.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

echo "Creating virtual environment at $DIR/venv ..."
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --upgrade pip
"$DIR/venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/osint-sna" <<EOF
#!/usr/bin/env bash
exec "$DIR/venv/bin/python" "$DIR/osint_sna.py" "\$@"
EOF
chmod +x "$BIN_DIR/osint-sna"

echo "Done. Command installed at $BIN_DIR/osint-sna"
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  echo "Warning: $BIN_DIR is not on your PATH. Add it to your shell rc, e.g.:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
echo "Try it with: osint-sna --help"
echo "Or just run 'osint-sna' with no arguments to launch the local web app."

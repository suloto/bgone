#!/usr/bin/env bash
# bgone installer — sets up a venv with rembg, installs the tool + command.
set -euo pipefail

PREFIX="${PREFIX:-/opt/bgone}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing bgone -> $PREFIX"
mkdir -p "$PREFIX"
python3 -m venv "$PREFIX/venv"
# --no-cache-dir: pip's cache lives in $HOME/.cache/pip. On a machine with an
# NFS-mounted home — or under `sudo` where NFS root_squash maps root to nobody —
# that path isn't writable and pip errors on it. Skipping the cache sidesteps it.
PIP="$PREFIX/venv/bin/pip"
"$PIP" install -q --no-cache-dir --upgrade pip
# rembg splits its runtime into extras: [cpu] pulls the onnxruntime backend,
# [cli] installs the `rembg` command used by the passthrough. Without these you
# get "No onnxruntime backend found". For an NVIDIA GPU use "rembg[gpu,cli]".
"$PIP" install -q --no-cache-dir "rembg[cpu,cli]"

install -m 755 "$HERE/bgone.sh"        "$PREFIX/bgone.sh"
install -m 644 "$HERE/bgone-worker.py" "$PREFIX/bgone-worker.py"
install -m 755 "$HERE/uninstall.sh"    "$PREFIX/uninstall.sh"  # so `sudo bgone --uninstall` works without the repo

# shared model cache next to the install — world-writable + sticky (like /tmp),
# so any user can populate it on first use without re-downloading per-home.
mkdir -p "$PREFIX/models"
chmod 1777 "$PREFIX/models"

# `bgone` command routing (honors a pre-set U2NET_HOME, else the shared cache):
#   no args / -h/--help / -V/--version / a directory  -> the tool
#   --uninstall                                        -> the uninstaller (needs sudo)
#   i|p|s|b|d ...                                      -> rembg CLI passthrough
cat > /usr/local/bin/bgone <<EOF
#!/usr/bin/env bash
export U2NET_HOME="\${U2NET_HOME:-$PREFIX/models}"
case "\${1:-}" in
  ""|-h|--help|-V|--version) exec "$PREFIX/bgone.sh" "\$@" ;;
  --uninstall)               exec "$PREFIX/uninstall.sh" "\${@:2}" ;;
  i|p|s|b|d)                 exec "$PREFIX/venv/bin/rembg" "\$@" ;;
  *) if [ -d "\$1" ]; then exec "$PREFIX/bgone.sh" "\$@"; else exec "$PREFIX/venv/bin/rembg" "\$@"; fi ;;
esac
EOF
chmod 755 /usr/local/bin/bgone

# bash completion (best effort)
if [ -d /etc/bash_completion.d ]; then
  install -m 644 "$HERE/completions/bgone" /etc/bash_completion.d/bgone || true
fi

echo "Done. Open a new shell (or 'source /etc/bash_completion.d/bgone'), then run: bgone"

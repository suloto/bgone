#!/usr/bin/env bash
# bgone installer — sets up a venv with rembg, installs the tool + command.
# Fleet/production friendly: idempotent, version-pinned, GPU-aware, conflict-guarded.
#
# Env knobs:
#   PREFIX=/opt/bgone   install location
#   BGONE_GPU=auto      cpu | gpu | auto  (auto installs the GPU runtime if an NVIDIA GPU is found)
#   BGONE_FORCE=0       1 = overwrite an unrelated /usr/local/bin/bgone
set -euo pipefail

PREFIX="${PREFIX:-/opt/bgone}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAP="/usr/local/bin/bgone"
BGONE_GPU="${BGONE_GPU:-auto}"
BGONE_FORCE="${BGONE_FORCE:-0}"

# ---- preflight: python3 with venv + ensurepip --------------------------------
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 not found." >&2; exit 1; }
if ! python3 -c 'import venv, ensurepip' >/dev/null 2>&1; then
  echo "Error: python3 venv/ensurepip is missing. Install it first:" >&2
  echo "  Debian/Ubuntu:    sudo apt install -y python3-venv" >&2
  echo "  RHEL/Rocky/Alma:  built in (ensure python3 is installed)" >&2
  exit 1
fi

# ---- conflict guard: never clobber an unrelated launcher ---------------------
if [ -e "$WRAP" ] && ! grep -q "$PREFIX" "$WRAP" 2>/dev/null; then
  if [ "$BGONE_FORCE" = 1 ]; then
    echo "Overwriting existing $WRAP (BGONE_FORCE=1)."
  else
    echo "Refusing: $WRAP exists and does not point at $PREFIX — another tool may own it." >&2
    echo "Re-run with BGONE_FORCE=1 to overwrite." >&2
    exit 1
  fi
fi

# ---- choose backend (GPU auto-detect, graceful CPU fallback) -----------------
case "$BGONE_GPU" in
  1|gpu|yes|true)  BACKEND=gpu ;;
  0|cpu|no|false)  BACKEND=cpu ;;
  *) # require a REAL NVIDIA GPU (a listed device), not just a leftover nvidia-smi binary
     if { nvidia-smi -L 2>/dev/null | grep -q '^GPU'; } || { lspci 2>/dev/null | grep -iE 'vga|3d|display' | grep -qi nvidia; }; then
       BACKEND=gpu; else BACKEND=cpu; fi ;;
esac
if [ "$BACKEND" = gpu ]; then EXTRAS="gpu,cli"; else EXTRAS="cpu,cli"; fi
echo "Backend: $BACKEND  (rembg[$EXTRAS])   [override: BGONE_GPU=cpu|gpu|auto]"

# ---- venv (idempotent / upgrade-in-place) ------------------------------------
if [ -d "$PREFIX/venv" ]; then
  echo "Existing install at $PREFIX — upgrading in place."
else
  echo "Installing bgone -> $PREFIX"
  mkdir -p "$PREFIX"
  python3 -m venv "$PREFIX/venv"
fi
PIP="$PREFIX/venv/bin/pip"

# --no-cache-dir: $HOME/.cache/pip is unwritable under sudo on NFS-home machines.
# -c constraints.txt: pin behaviour-affecting packages so the whole fleet matches.
CONSTRAINTS=""; [ -f "$HERE/constraints.txt" ] && CONSTRAINTS="-c $HERE/constraints.txt"
"$PIP" install -q --no-cache-dir --upgrade pip
# shellcheck disable=SC2086
"$PIP" install -q --no-cache-dir $CONSTRAINTS "rembg[$EXTRAS]"

# ---- install the tool + supply-chain manifest --------------------------------
install -m 755 "$HERE/bgone.sh"        "$PREFIX/bgone.sh"
install -m 644 "$HERE/bgone-worker.py" "$PREFIX/bgone-worker.py"
install -m 755 "$HERE/uninstall.sh"    "$PREFIX/uninstall.sh"   # so `sudo bgone --uninstall` works without the repo
install -m 644 "$HERE/models.sha256"   "$PREFIX/models.sha256"  # for `bgone --verify-models`

# shared model cache next to the install — world-writable + sticky (like /tmp),
# so any user populates it on first use without re-downloading per-home.
mkdir -p "$PREFIX/models"
chmod 1777 "$PREFIX/models"

# ---- `bgone` launcher --------------------------------------------------------
#   no args / -h/--help / -V/--version / --verify-models / a directory -> the tool
#   --uninstall -> uninstaller (sudo) ; i|p|s|b|d -> rembg CLI passthrough
cat > "$WRAP" <<EOF
#!/usr/bin/env bash
export U2NET_HOME="\${U2NET_HOME:-$PREFIX/models}"
case "\${1:-}" in
  ""|-h|--help|-V|--version|--verify-models) exec "$PREFIX/bgone.sh" "\$@" ;;
  --uninstall)               exec "$PREFIX/uninstall.sh" "\${@:2}" ;;
  i|p|s|b|d)                 exec "$PREFIX/venv/bin/rembg" "\$@" ;;
  *) if [ -d "\$1" ]; then exec "$PREFIX/bgone.sh" "\$@"; else exec "$PREFIX/venv/bin/rembg" "\$@"; fi ;;
esac
EOF
chmod 755 "$WRAP"

# bash completion (best effort)
if [ -d /etc/bash_completion.d ]; then
  install -m 644 "$HERE/completions/bgone" /etc/bash_completion.d/bgone || true
fi

echo "Done ($BACKEND backend)."
"$PREFIX/venv/bin/python" -c "import onnxruntime as o; print('ONNX providers available:', ', '.join(o.get_available_providers()))" 2>/dev/null || true
echo "Open a new shell (or 'source /etc/bash_completion.d/bgone'), then run: bgone"
echo "Verify model integrity any time with:  bgone --verify-models"

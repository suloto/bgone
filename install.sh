#!/usr/bin/env bash
# bgone installer — sets up a venv with rembg, installs the tool + command.
# Fleet/production friendly: idempotent, version-pinned, GPU-aware, conflict-guarded.
#
# Env knobs:
#   PREFIX=/opt/bgone   install location
#   BGONE_GPU=auto      cpu | gpu | auto  (auto installs the GPU runtime if an NVIDIA GPU is found)
#   BGONE_FORCE=0       1 = overwrite an unrelated /usr/local/bin/bgone
#   BGONE_GUI=1         1 = also install the Qt GUI (PySide6) + desktop launcher; 0 = terminal only
set -euo pipefail

PREFIX="${PREFIX:-/opt/bgone}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAP="/usr/local/bin/bgone"
BGONE_GPU="${BGONE_GPU:-auto}"
BGONE_FORCE="${BGONE_FORCE:-0}"
BGONE_GUI="${BGONE_GUI:-1}"

# ---- preflight: pick a Python >=3.11 with venv + ensurepip -------------------
# rembg/numpy/onnxruntime dropped 3.9/3.10, so a modern interpreter is required.
# RHEL/Rocky/Alma 9 ship 3.9 as the default python3 but offer python3.11/3.12 as
# parallel-installable packages; prefer those. Override with PYTHON=/path/to/python.
pick_python() {
  local c
  for c in "${PYTHON:-}" python3.12 python3.11 python3.13 python3; do
    [ -n "$c" ] || continue
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)' 2>/dev/null || continue
    "$c" -c 'import venv, ensurepip' >/dev/null 2>&1 || continue
    echo "$c"; return 0
  done
  return 1
}
PY="$(pick_python || true)"
if [ -z "$PY" ]; then
  echo "Error: bgone needs Python >=3.11 with venv+ensurepip (rembg/numpy dropped 3.9/3.10)." >&2
  echo "Install a modern Python, then re-run (or pass PYTHON=/path/to/python3.12):" >&2
  echo "  RHEL/Rocky/Alma:  sudo dnf install -y python3.12" >&2
  echo "  Debian/Ubuntu:    sudo apt install -y python3.12-venv  (or python3.11-venv)" >&2
  exit 1
fi
echo "Python: $("$PY" -V 2>&1)  ($(command -v "$PY"))"

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
# reuse the venv only if it already runs a supported Python; otherwise rebuild it
# (e.g. a venv first made with the system 3.9, then python3.12 was installed).
venv_ok() {
  [ -x "$PREFIX/venv/bin/python" ] || return 1
  "$PREFIX/venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)' 2>/dev/null
}
if [ -d "$PREFIX/venv" ] && venv_ok; then
  echo "Existing install at $PREFIX — upgrading in place."
else
  if [ -d "$PREFIX/venv" ]; then
    echo "Existing venv at $PREFIX runs an unsupported Python (<3.11) — rebuilding with $PY."
    rm -rf "$PREFIX/venv"
  else
    echo "Installing bgone -> $PREFIX"
  fi
  mkdir -p "$PREFIX"
  "$PY" -m venv "$PREFIX/venv"
fi
PIP="$PREFIX/venv/bin/pip"

# --no-cache-dir: $HOME/.cache/pip is unwritable under sudo on NFS-home machines.
# -c constraints.txt: pin behaviour-affecting packages so the whole fleet matches.
CONSTRAINTS=""; [ -f "$HERE/constraints.txt" ] && CONSTRAINTS="-c $HERE/constraints.txt"
"$PIP" install -q --no-cache-dir --upgrade pip
# shellcheck disable=SC2086
"$PIP" install -q --no-cache-dir $CONSTRAINTS "rembg[$EXTRAS]"
# pre-stage imageio's FreeImage backend so EXR output works offline after install (best-effort)
"$PREFIX/venv/bin/python" -c "import imageio; imageio.plugins.freeimage.download()" >/dev/null 2>&1 || true

# ---- optional GUI (PySide6 / Qt) ---------------------------------------------
if [ "$BGONE_GUI" != 0 ]; then
  echo "Installing GUI (PySide6/Qt) — set BGONE_GUI=0 for terminal-only."
  # platform libraries Qt's xcb plugin needs at runtime (best-effort; a desktop box
  # usually has most already — the commonly-missing one for Qt6 is xcb-util-cursor).
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y -q libxkbcommon-x11 xcb-util-cursor xcb-util-image xcb-util-keysyms \
      xcb-util-renderutil xcb-util-wm mesa-libGL mesa-libEGL fontconfig >/dev/null 2>&1 || true
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get install -y -q libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 \
      libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libgl1 libegl1 libfontconfig1 >/dev/null 2>&1 || true
  fi
  # shellcheck disable=SC2086
  if ! "$PIP" install -q --no-cache-dir $CONSTRAINTS PySide6; then
    echo "  ! PySide6 install failed — GUI unavailable; terminal bgone still works." >&2
    BGONE_GUI=0
  fi
fi

# ---- install the tool + supply-chain manifest --------------------------------
install -m 755 "$HERE/bgone.sh"        "$PREFIX/bgone.sh"
install -m 644 "$HERE/bgone-worker.py" "$PREFIX/bgone-worker.py"
[ "$BGONE_GUI" != 0 ] && [ -f "$HERE/bgone-gui.py" ] && install -m 644 "$HERE/bgone-gui.py" "$PREFIX/bgone-gui.py"
if [ "$BGONE_GUI" != 0 ] && [ -d "$HERE/assets/icons" ]; then   # Iconoir SVGs for the GUI
  mkdir -p "$PREFIX/icons"
  install -m 644 "$HERE/assets/icons/"*.svg "$PREFIX/icons/" 2>/dev/null || true
fi
install -m 755 "$HERE/uninstall.sh"    "$PREFIX/uninstall.sh"   # so `sudo bgone --uninstall` works without the repo
install -m 644 "$HERE/models.sha256"   "$PREFIX/models.sha256"  # for `bgone --verify-models`

# shared model cache next to the install — world-writable + sticky (like /tmp),
# so any user populates it on first use without re-downloading per-home.
mkdir -p "$PREFIX/models"
chmod 1777 "$PREFIX/models"

# ---- `bgone` launcher --------------------------------------------------------
#   no args / -h/--help / -V/--version / --verify-models / --check-updates / a directory -> the tool
#   -g/--gui/gui -> the Qt GUI ; --uninstall -> uninstaller ; i|p|s|b|d -> rembg CLI
cat > "$WRAP" <<EOF
#!/usr/bin/env bash
export U2NET_HOME="\${U2NET_HOME:-$PREFIX/models}"
case "\${1:-}" in
  ""|-h|--help|-V|--version|--verify-models|--check-updates) exec "$PREFIX/bgone.sh" "\$@" ;;
  -g|--gui|gui)              exec "$PREFIX/venv/bin/python" "$PREFIX/bgone-gui.py" "\${@:2}" ;;
  --uninstall)               exec "$PREFIX/uninstall.sh" "\${@:2}" ;;
  i|p|s|b|d)                 exec "$PREFIX/venv/bin/rembg" "\$@" ;;
  *) if [ -d "\$1" ]; then exec "$PREFIX/bgone.sh" "\$@"; else exec "$PREFIX/venv/bin/rembg" "\$@"; fi ;;
esac
EOF
chmod 755 "$WRAP"

# ---- desktop launcher + icon (GUI) -------------------------------------------
if [ "$BGONE_GUI" != 0 ] && [ -f "$HERE/assets/bgone.png" ]; then
  ICONDIR=/usr/share/icons/hicolor/256x256/apps
  mkdir -p "$ICONDIR" /usr/share/applications
  install -m 644 "$HERE/assets/bgone.png" "$ICONDIR/bgone.png"
  install -m 644 "$HERE/assets/bgone.png" "$PREFIX/bgone.png"
  cat > /usr/share/applications/bgone.desktop <<DESK
[Desktop Entry]
Type=Application
Name=bgone
GenericName=Background Remover
Comment=Batch-remove image backgrounds
Exec=$WRAP --gui
Icon=bgone
Terminal=false
Categories=Graphics;Photography;Utility;
Keywords=background;remove;cutout;rembg;transparent;
DESK
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
  command -v gtk-update-icon-cache  >/dev/null 2>&1 && gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

# bash completion (best effort)
if [ -d /etc/bash_completion.d ]; then
  install -m 644 "$HERE/completions/bgone" /etc/bash_completion.d/bgone || true
fi

echo "Done ($BACKEND backend$([ "$BGONE_GUI" != 0 ] && echo ', GUI'))."
"$PREFIX/venv/bin/python" -c "import onnxruntime as o; print('ONNX providers available:', ', '.join(o.get_available_providers()))" 2>/dev/null || true
echo "Open a new shell (or 'source /etc/bash_completion.d/bgone'), then run: bgone"
[ "$BGONE_GUI" != 0 ] && echo "Or launch the GUI:  bgone --gui   (also in your desktop's app menu)"
echo "Verify model integrity any time with:  bgone --verify-models"

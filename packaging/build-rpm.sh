#!/usr/bin/env bash
# Build a SELF-CONTAINED bgone RPM. It vendors its own relocatable Python 3.12
# (python-build-standalone) + all deps under /opt/bgone, so installing the package never
# installs or upgrades the system Python — the spec ships zero Python requires.
#
# Run on RHEL/Rocky/Alma 9 (x86_64). Needs: rpm-build, rpmdevtools, curl, git, internet.
#   sudo dnf install -y rpm-build rpmdevtools curl git
#   packaging/build-rpm.sh
# Output: ~/rpmbuild/RPMS/x86_64/bgone-<version>-1.*.rpm
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"     # repo root
VERSION="$(grep -m1 'VERSION="' "$SRC/bgone.sh" | cut -d'"' -f2)"
PYSIDE="$(grep -i '^PySide6==' "$SRC/constraints.txt" | cut -d= -f3)"
STAGE="$(mktemp -d)/stage"
PREFIX="$STAGE/opt/bgone"
mkdir -p "$PREFIX"
echo "==> bgone $VERSION  (PySide6-Essentials $PYSIDE)  staging in $STAGE"

echo "==> fetch relocatable CPython 3.12 (python-build-standalone, install_only)"
URL=$(curl -fsSL https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest \
  | grep -o 'https://github.com/[^"]*cpython-3\.12\.[0-9.]*%2B[0-9]*-x86_64-unknown-linux-gnu-install_only\.tar\.gz' | head -1)
curl -fsSL "$URL" | tar -xz -C "$PREFIX"          # -> $PREFIX/python
mv "$PREFIX/python" "$PREFIX/venv"
PY="$PREFIX/venv/bin/python3.12"

echo "==> install pinned deps into the bundled interpreter"
"$PY" -m pip install --no-cache-dir -q --upgrade pip
"$PY" -m pip install --no-cache-dir -q -c "$SRC/constraints.txt" \
    "rembg[cpu,cli]" "PySide6-Essentials==${PYSIDE}" imageio
"$PY" -c "import imageio; imageio.plugins.freeimage.download()" >/dev/null 2>&1 || true

echo "==> slim: drop unused tcl/tk + stdlib fat"
V="$PREFIX/venv"
rm -f  "$V"/lib/libtcl* "$V"/lib/libtk* "$V"/lib/libpython3.12.a 2>/dev/null || true
rm -rf "$V"/lib/tcl* "$V"/lib/tk* "$V"/lib/thread* "$V"/lib/itcl* "$V"/lib/tdbc* \
       "$V"/lib/python3.12/test "$V"/lib/python3.12/idlelib "$V"/lib/python3.12/turtledemo \
       "$V"/lib/python3.12/tkinter "$V"/lib/python3.12/lib2to3 "$V"/include "$V"/share 2>/dev/null || true
find "$V" -name '_tkinter*.so' -delete 2>/dev/null || true
find "$V" -depth -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "==> app files"
install -m644 "$SRC/bgone-worker.py" "$PREFIX/bgone-worker.py"
install -m644 "$SRC/bgone-gui.py"    "$PREFIX/bgone-gui.py"
install -m755 "$SRC/bgone.sh"        "$PREFIX/bgone.sh"
install -m644 "$SRC/models.sha256"   "$PREFIX/models.sha256"
mkdir -p "$PREFIX/icons"; install -m644 "$SRC/assets/icons/"*.svg "$PREFIX/icons/"
install -m644 "$SRC/assets/bgone.png" "$PREFIX/bgone.png"
mkdir -p "$PREFIX/models"; chmod 1777 "$PREFIX/models"

echo "==> relocate console-script shebangs to the install path"
for f in "$V"/bin/*; do
    head -c2 "$f" 2>/dev/null | grep -q '#!' && sed -i "1s#${PREFIX}#/opt/bgone#" "$f" || true
done

echo "==> launcher + desktop entry + completion"
mkdir -p "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/256x256/apps" "$STAGE/etc/bash_completion.d"
cat > "$STAGE/usr/bin/bgone" <<'WRAP'
#!/usr/bin/env bash
export U2NET_HOME="${U2NET_HOME:-/opt/bgone/models}"
case "${1:-}" in
  ""|-h|--help|-V|--version|--verify-models) exec "/opt/bgone/bgone.sh" "$@" ;;
  -g|--gui|gui)              exec "/opt/bgone/venv/bin/python" "/opt/bgone/bgone-gui.py" "${@:2}" ;;
  i|p|s|b|d)                 exec "/opt/bgone/venv/bin/rembg" "$@" ;;
  *) if [ -d "$1" ]; then exec "/opt/bgone/bgone.sh" "$@"; else exec "/opt/bgone/venv/bin/rembg" "$@"; fi ;;
esac
WRAP
chmod 755 "$STAGE/usr/bin/bgone"
cat > "$STAGE/usr/share/applications/bgone.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=bgone
GenericName=Background Remover
Comment=Batch-remove image backgrounds
Exec=/usr/bin/bgone --gui
Icon=bgone
Terminal=false
Categories=Graphics;Photography;Utility;
Keywords=background;remove;cutout;rembg;transparent;
DESK
install -m644 "$SRC/assets/bgone.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/bgone.png"
[ -f "$SRC/completions/bgone" ] && install -m644 "$SRC/completions/bgone" "$STAGE/etc/bash_completion.d/bgone"

echo "==> rpmbuild"
rpmdev-setuptree 2>/dev/null || mkdir -p ~/rpmbuild/{SPECS,RPMS,BUILD,BUILDROOT,SOURCES,SRPMS}
sed -e "s/@VERSION@/${VERSION}/g" -e "s#@STAGE@#${STAGE}#g" "$SRC/packaging/bgone.spec.in" > ~/rpmbuild/SPECS/bgone.spec
QA_RPATHS=$((0x0001|0x0002|0x0004|0x0008|0x0010)) rpmbuild -bb ~/rpmbuild/SPECS/bgone.spec
echo "==> done:"; ls -1 ~/rpmbuild/RPMS/x86_64/bgone-"${VERSION}"-*.rpm

#!/usr/bin/env bash
# bgone uninstaller — removes the tool, its venv + downloaded models, the `bgone`
# command, and the bash completion.   Usage:  sudo ./uninstall.sh [-y|--yes]
#   PREFIX=/opt/bgone by default (set PREFIX to match a custom install location).
set -euo pipefail

PREFIX="${PREFIX:-/opt/bgone}"
WRAP="/usr/local/bin/bgone"
COMP="/etc/bash_completion.d/bgone"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo — uninstall removes $PREFIX, $WRAP and $COMP." >&2
  exit 1
fi

# Only remove the launcher if it actually points at THIS PREFIX (never clobber an
# unrelated /usr/local/bin/bgone).
rm_wrap=no
if [ -f "$WRAP" ] && grep -q "$PREFIX" "$WRAP" 2>/dev/null; then rm_wrap=yes; fi

echo "bgone uninstall will remove:"
echo "  $PREFIX            (venv, tool, and any downloaded models)"
if [ "$rm_wrap" = yes ]; then echo "  $WRAP"; fi
if [ -f "$COMP" ]; then echo "  $COMP"; fi

if [ "${1:-}" != "-y" ] && [ "${1:-}" != "--yes" ]; then
  read -rp "Proceed? [y/N]: " ans
  case "$ans" in [Yy]*) ;; *) echo "Cancelled."; exit 1 ;; esac
fi

if [ "$rm_wrap" = yes ]; then rm -f "$WRAP"; echo "removed $WRAP"; fi
if [ -f "$COMP" ]; then rm -f "$COMP"; echo "removed $COMP"; fi
echo "Done — bgone uninstalled. Per-user settings, if any, remain at \"\${XDG_CONFIG_HOME:-\$HOME/.config}/bgone\"."
# Keep LAST: $PREFIX may hold this very script (the installed copy), and bash reads
# a script as it runs — deleting it earlier could truncate execution.
rm -rf "$PREFIX"

#!/usr/bin/env bash
#
# bgone — batch background remover (front-end for rembg). PURE TERMINAL.
#         Loads the model ONCE and processes N images in parallel ("streams").
#
# Usage:
#   bgone                   interactive: pick folder(s), model, options
#   bgone DIR [DIR ...]     process these folder(s) directly
#   bgone -h | --help
#   bgone -V | --version
#
set -uo pipefail
VERSION="0.7.1"

# presentation: colour only on a TTY without NO_COLOR; Unicode glyphs only in a UTF-8 locale
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  B=$'\033[1m'; G=$'\033[1;32m'; Y=$'\033[1;33m'; Rd=$'\033[1;31m'; Dim=$'\033[2m'; Z=$'\033[0m'
else
  B=''; G=''; Y=''; Rd=''; Dim=''; Z=''
fi
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in *[Uu][Tt][Ff]*) GLYPH=1 ;; *) GLYPH=0 ;; esac
[ -t 1 ] || GLYPH=0
if [ "$GLYPH" = 1 ]; then TICK='✓'; CROSS='✗'; ARROW='▸'; SEP='·'; BAR_F='█'; BAR_E='─'
else                     TICK='OK'; CROSS='x'; ARROW='>'; SEP='-'; BAR_F='#'; BAR_E='-'; fi
title(){ printf '\n%s%s %s%s\n' "$G" "$ARROW" "$1" "$Z"; }
die(){ printf '%s%s%s\n' "$Rd" "$1" "$Z" >&2; exit 1; }

# ---- locate ourselves + the shared model cache (no runtime deps yet) -----
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
BGONE_HOME="${BGONE_HOME:-$HERE}"
WORKER="$BGONE_HOME/bgone-worker.py"
[ -f "$WORKER" ] || WORKER="/opt/bgone/bgone-worker.py"
[ -f "$WORKER" ] || WORKER="/opt/rembg/bgone-worker.py"   # legacy path
MODELDIR="${U2NET_HOME:-$BGONE_HOME/models}"        # default: shared cache next to the install
mkdir -p "$MODELDIR" 2>/dev/null || true
[ -w "$MODELDIR" ] || MODELDIR="${HOME:-/root}/.u2net"  # fall back to ~/.u2net if not writable
export U2NET_HOME="$MODELDIR"                        # so the worker + rembg passthrough agree

# ---- commands that must work WITHOUT the rembg runtime -------------------
case "${1:-}" in
  -h|--help)
    cat <<EOF
bgone $VERSION — batch background remover (built on rembg)

  bgone                  interactive: pick folder(s), model, options
  bgone DIR [DIR ...]    process these folder(s) directly
  bgone --gui            launch the graphical version (PySide6/Qt)
  bgone --verify-models  check cached model weights vs the shipped SHA-256 manifest
  bgone -h | --help      this help
  bgone -V | --version   version

Each source FOLDER's images go to a "FOLDER_bgone" folder inside it; output folder + file
names are sanitised to be terminal-friendly (spaces/specials -> _).
Interactive options: recurse subfolders, model, alpha matting, trim-to-content,
background (transparent/white/black/#hex), resume-skip, parallel streams. Your last
choices are remembered in \${XDG_CONFIG_HOME:-\$HOME/.config}/bgone/config.
Env: U2NET_HOME (model cache dir), BGONE_HOME (install dir).
EOF
    exit 0 ;;
  -V|--version) echo "bgone $VERSION"; exit 0 ;;
  --verify-models)
    MAN="$BGONE_HOME/models.sha256"; [ -f "$MAN" ] || MAN="/opt/bgone/models.sha256"
    [ -f "$MAN" ] || die "Checksum manifest not found (looked in $BGONE_HOME and /opt/bgone)."
    echo "Verifying models in $MODELDIR against $MAN"
    rc=0; present=0
    while read -r want name; do
      [ -n "${name:-}" ] || continue
      f="$MODELDIR/$name"
      if [ ! -f "$f" ]; then printf '  %s·%s %s (not downloaded yet)\n' "$Dim" "$Z" "$name"; continue; fi
      present=$((present+1))
      got="$(sha256sum "$f" 2>/dev/null | awk '{print $1}')"
      if [ "$got" = "$want" ]; then printf '  %sOK%s       %s\n' "$G" "$Z" "$name"
      else printf '  %sMISMATCH%s %s\n' "$Rd" "$Z" "$name"; rc=1; fi
    done < "$MAN"
    if [ "$rc" -ne 0 ]; then printf '%sWARNING: a model failed checksum — possibly corrupt or tampered.%s\n' "$Rd" "$Z" >&2
    else echo "Verified $present present model(s); no mismatches."; fi
    exit "$rc" ;;
esac

# ---- locate the rembg runtime (required for processing from here on) -----
if   [ -x "$BGONE_HOME/venv/bin/rembg" ]; then REMBG="$BGONE_HOME/venv/bin/rembg"
elif [ -x /opt/bgone/venv/bin/rembg ];    then REMBG=/opt/bgone/venv/bin/rembg
elif [ -x /opt/rembg/venv/bin/rembg ];    then REMBG=/opt/rembg/venv/bin/rembg
elif command -v rembg >/dev/null 2>&1;    then REMBG="$(command -v rembg)"
else die "Cannot find rembg — run install.sh, or set BGONE_HOME to your install dir."; fi
PYTHON="$(dirname "$REMBG")/python"; [ -x "$PYTHON" ] || PYTHON="python3"

# ---- remembered defaults -------------------------------------------------
CFG="${XDG_CONFIG_HOME:-$HOME/.config}/bgone/config"
CFG_MODEL=1; CFG_STREAMS=4; CFG_ALPHA=off; CFG_TRIM=off; CFG_BG=transparent; CFG_SKIP=on
CFG_FMT=png; CFG_QUALITY=90; CFG_MATTE=off; CFG_FEATHER=0; CFG_SHRINK=0
# shellcheck source=/dev/null
[ -f "$CFG" ] && . "$CFG" 2>/dev/null || true

printf '\n%sbgone%s %s— batch background remover · model loads once%s\n' "$B" "$Z" "$Dim" "$Z"
[ -t 1 ] && [ -f "$BGONE_HOME/bgone-gui.py" ] && printf '%stip: run "bgone --gui" for the graphical version%s\n' "$Dim" "$Z"

# ---- step 1: source folders ----------------------------------------------
SRCS=()
if [ "$#" -gt 0 ]; then
  for d in "$@"; do [ -d "$d" ] || die "Not a folder: $d"; SRCS+=( "$(cd "$d" && pwd)" ); done
else
  title "Source folders"
  IFS= read -erp "Folder that contains your image folders [$PWD]: " parent
  parent="${parent:-$PWD}"; parent="${parent%/}"
  [ -d "$parent" ] || die "Not a folder: $parent"
  subs=()
  shopt -s nullglob nocaseglob
  while IFS= read -r dd; do subs+=( "$dd" ); done < <(find "$parent" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)
  pc=( "$parent"/*.jpg "$parent"/*.jpeg "$parent"/*.png "$parent"/*.webp )   # images directly in the parent
  if [ "${#subs[@]}" -eq 0 ]; then
    shopt -u nullglob nocaseglob
    printf '\n%sNo subfolders here — using this folder itself (%d images).%s\n' "$Dim" "${#pc[@]}" "$Z"
    SRCS=( "$parent" )
  else
    printf '\n  %s0%s   %s(use this folder itself — %d images)%s\n' "$Y" "$Z" "$Dim" "${#pc[@]}" "$Z"
    i=1
    for dd in "${subs[@]}"; do
      c=( "$dd"/*.jpg "$dd"/*.jpeg "$dd"/*.png "$dd"/*.webp )
      printf '  %s%2d%s  %s  %s(%d images)%s\n' "$Y" "$i" "$Z" "$(basename "$dd")" "$Dim" "${#c[@]}" "$Z"
      i=$((i+1))
    done
    shopt -u nullglob nocaseglob
    IFS= read -rp 'Select folders (e.g. "1 3 5-8", "all", "0"=this): ' picks
    picks="${picks//,/ }"; declare -A seen=()
    for tok in $picks; do
      case "$tok" in
        all|ALL|a) for ((k=1; k<=${#subs[@]}; k++)); do seen[$k]=1; done ;;
        0) SRCS+=( "$parent" ) ;;
        *-*) lo="${tok%-*}"; hi="${tok#*-}"
             if [[ "$lo" =~ ^[0-9]+$ && "$hi" =~ ^[0-9]+$ ]]; then
               for ((k=lo; k<=hi; k++)); do [ "$k" -ge 1 ] && [ "$k" -le "${#subs[@]}" ] && seen[$k]=1; done
             fi ;;
        *) [[ "$tok" =~ ^[0-9]+$ ]] && [ "$tok" -ge 1 ] && [ "$tok" -le "${#subs[@]}" ] && seen[$tok]=1 ;;
      esac
    done
    if [ "${#seen[@]}" -gt 0 ]; then
      for k in $(printf '%s\n' "${!seen[@]}" | sort -n); do SRCS+=( "${subs[$((k-1))]}" ); done
    fi
  fi
fi
[ "${#SRCS[@]}" -gt 0 ] || die "No folders selected."

IFS= read -rp "Include images in subfolders (recurse)? [y/N]: " rc; RECURSE=off; [[ "$rc" =~ ^[Yy] ]] && RECURSE=on

# ---- step 2: model -------------------------------------------------------
title "Model"
models=(birefnet-general-lite u2net isnet-general-use isnet-anime birefnet-general birefnet-portrait u2netp silueta)
declare -A mdesc=( [birefnet-general-lite]="photos / SOTA (recommended)" [birefnet-general]="photos / max quality" \
                   [birefnet-portrait]="people / hair" [u2net]="photos / realistic / 3D" \
                   [isnet-general-use]="general purpose" [isnet-anime]="anime / illustration" \
                   [u2netp]="lightweight, faster" [silueta]="u2net quality, smaller" )
declare -A msize=( [birefnet-general-lite]="~224MB" [birefnet-general]="~900MB" [birefnet-portrait]="~900MB" \
                   [u2net]="168MB" [isnet-general-use]="170MB" [isnet-anime]="168MB" [u2netp]="4MB" [silueta]="43MB" )
# sanitize remembered model choice — the config is user-editable; a bad value must
# not crash the unguarded array index below under `set -u`.
[[ "$CFG_MODEL" =~ ^[0-9]+$ ]] && [ "$CFG_MODEL" -ge 1 ] && [ "$CFG_MODEL" -le "${#models[@]}" ] || CFG_MODEL=1
i=1
for m in "${models[@]}"; do
  if [ -f "$MODELDIR/$m.onnx" ]; then tag="${G}[cached]${Z}"; else tag="${Dim}(downloads ~${msize[$m]})${Z}"; fi
  printf '  %s%d%s  %-18s %-26s %s\n' "$Y" "$i" "$Z" "$m" "${mdesc[$m]}" "$tag"; i=$((i+1))
done
IFS= read -rp "Model [${CFG_MODEL}=${models[$((CFG_MODEL-1))]}]: " mi; mi="${mi:-$CFG_MODEL}"
[[ "$mi" =~ ^[0-9]+$ ]] && [ "$mi" -ge 1 ] && [ "$mi" -le "${#models[@]}" ] || die "Invalid model choice."
MODEL="${models[$((mi-1))]}"

# ---- step 3: options (defaults from last run) ----------------------------
ad="[y/N]"; [ "$CFG_ALPHA" = on ] && ad="[Y/n]"
IFS= read -rp "Alpha matting? (softer edges, photos only) $ad: " a
ALPHA="$CFG_ALPHA"; [[ "$a" =~ ^[Yy] ]] && ALPHA=on; [[ "$a" =~ ^[Nn] ]] && ALPHA=off

td="[y/N]"; [ "$CFG_TRIM" = on ] && td="[Y/n]"
IFS= read -rp "Trim to content? (crop transparent margins) $td: " t
TRIM="$CFG_TRIM"; [[ "$t" =~ ^[Yy] ]] && TRIM=on; [[ "$t" =~ ^[Nn] ]] && TRIM=off

md="[y/N]"; [ "$CFG_MATTE" = on ] && md="[Y/n]"
IFS= read -rp "Output the B&W mask instead of the cutout? $md: " mt
MATTE="$CFG_MATTE"; [[ "$mt" =~ ^[Yy] ]] && MATTE=on; [[ "$mt" =~ ^[Nn] ]] && MATTE=off

IFS= read -rp "Feather edge — soften, px [${CFG_FEATHER}]: " fe; FEATHER="${fe:-$CFG_FEATHER}"
[[ "$FEATHER" =~ ^[0-9]+$ ]] || FEATHER=0
IFS= read -rp "Shrink edge — kill halo, px [${CFG_SHRINK}]: " sh; SHRINK="${sh:-$CFG_SHRINK}"
[[ "$SHRINK" =~ ^[0-9]+$ ]] || SHRINK=0

printf '%sFormats:%s alpha = png webp tiff tga dds jp2 avif · flat = jpg bmp · float/VFX = exr hdr dpx\n' "$Dim" "$Z"
IFS= read -rp "Output format [${CFG_FMT}]: " fmtin
FMT="${fmtin:-$CFG_FMT}"; FMT="${FMT,,}"
case "$FMT" in jpeg) FMT=jpg ;; tif) FMT=tiff ;; j2k|jpeg2000) FMT=jp2 ;; esac
case "$FMT" in png|webp|jpg|tiff|tga|bmp|avif|jp2|dds|exr|hdr|dpx) ;; *) FMT=png ;; esac
case "$FMT" in
  exr|hdr|dpx) "$PYTHON" -c "import imageio.v3" 2>/dev/null || die "$FMT output needs imageio — re-run install.sh." ;;
esac
QUALITY="$CFG_QUALITY"
case "$FMT" in
  jpg|webp|avif)
    IFS= read -rp "Quality 1-100 [${CFG_QUALITY}]: " qin; QUALITY="${qin:-$CFG_QUALITY}"
    [[ "$QUALITY" =~ ^[0-9]+$ ]] && [ "$QUALITY" -ge 1 ] && [ "$QUALITY" -le 100 ] || QUALITY="$CFG_QUALITY" ;;
esac

IFS= read -rp "Background — transparent / white / black / green / #hex [${CFG_BG}]: " bgin
BG="${bgin:-$CFG_BG}"
case "$BG" in
  transparent|white|black|green) ;;
  \#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]) ;;
  *) BG=transparent ;;
esac
case "$FMT" in
  jpg|bmp|hdr|dpx) [ "$BG" = transparent ] && { BG=white; printf '%s(%s has no alpha — compositing on white)%s\n' "$Dim" "$FMT" "$Z"; } ;;
esac

sd="[Y/n]"; [ "$CFG_SKIP" = off ] && sd="[y/N]"
IFS= read -rp "Skip files already done (resume)? $sd: " s
SKIP="$CFG_SKIP"; [[ "$s" =~ ^[Nn] ]] && SKIP=off; [[ "$s" =~ ^[Yy] ]] && SKIP=on

# ---- streams -------------------------------------------------------------
NPROC="$(nproc 2>/dev/null || echo 4)"
title "Parallel streams"
printf '%s%d CPU threads available — the model loads once and is shared.%s\n' "$Dim" "$NPROC" "$Z"
sopts=(1 2 4 6 8); case " ${sopts[*]} " in *" $NPROC "*) ;; *) sopts+=( "$NPROC" );; esac
for o in "${sopts[@]}"; do
  note=""; [ "$o" -eq 1 ] && note="sequential (lightest)"; [ "$o" -eq 4 ] && note="recommended"
  [ "$o" -eq "$NPROC" ] && note="${note:+$note, }max (all $NPROC threads)"
  printf '  %s%2d%s   %s%s%s\n' "$Y" "$o" "$Z" "$Dim" "$note" "$Z"
done
IFS= read -rp "How many streams? [${CFG_STREAMS}]: " st; STREAMS="${st:-$CFG_STREAMS}"
[[ "$STREAMS" =~ ^[0-9]+$ ]] && [ "$STREAMS" -ge 1 ] || STREAMS=4
THREADS=$(( NPROC / STREAMS )); [ "$THREADS" -lt 1 ] && THREADS=1

# ---- remember choices ----------------------------------------------------
if mkdir -p "$(dirname "$CFG")" 2>/dev/null; then
  { echo "CFG_MODEL=$mi"; echo "CFG_STREAMS=$STREAMS"; echo "CFG_ALPHA=$ALPHA"
    echo "CFG_TRIM=$TRIM"; echo "CFG_BG=$BG"; echo "CFG_SKIP=$SKIP"
    echo "CFG_FMT=$FMT"; echo "CFG_QUALITY=$QUALITY"; echo "CFG_MATTE=$MATTE"
    echo "CFG_FEATHER=$FEATHER"; echo "CFG_SHRINK=$SHRINK"; } > "$CFG" 2>/dev/null || true
fi

# ---- build work list (each FOLDER -> a '<name>_bgone' subfolder INSIDE it) -----
# Output folder + file names are sanitised to be terminal-friendly: only
# [A-Za-z0-9._-] survive, runs of anything else collapse to a single '_'.
PAIRS=(); OUTS=(); found=0; skipped=0; declare -A usedout=()
depth=1; [ "$RECURSE" = on ] && depth=999
for SRC in "${SRCS[@]}"; do
  ob="${SRC##*/}"; ob="${ob//[!A-Za-z0-9._-]/_}"          # terminal-safe output folder name
  while [[ "$ob" == *__* ]]; do ob="${ob//__/_}"; done; ob="${ob#_}"; ob="${ob%_}"
  OUT="${SRC%/}/${ob:-x}_bgone"; OUTS+=( "$OUT" )         # inside the source folder
  while IFS= read -r f; do
    found=$((found+1)); rel="${f#"$SRC"/}"; stem="${rel%.*}"; ext="${rel##*.}"
    san=""; IFS='/' read -ra _seg <<< "$stem"            # sanitise each path segment (keeps subfolders on recurse)
    for s in "${_seg[@]}"; do
      s="${s//[!A-Za-z0-9._-]/_}"; while [[ "$s" == *__* ]]; do s="${s//__/_}"; done
      s="${s#_}"; s="${s%_}"; san="${san:+$san/}${s:-x}"
    done
    san="${san:-x}"; out="$OUT/$san.$FMT"
    # disambiguate clashes (e.g. 'a b.jpg' + 'a-b.png' -> same name) by keeping the ext
    [ -n "${usedout["$out"]:-}" ] && out="$OUT/$san.${ext//[!A-Za-z0-9]/_}.$FMT"
    usedout["$out"]=1
    if [ "$SKIP" = on ] && [ -f "$out" ]; then skipped=$((skipped+1)); continue; fi
    PAIRS+=( "$f" "$out" )
  done < <(find "$SRC" -maxdepth "$depth" \( -type d -name '*_bgone' -prune \) -o -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) -print 2>/dev/null)
done
todo=$(( ${#PAIRS[@]} / 2 ))
[ "$found" -gt 0 ] || die "No images (jpg/jpeg/png/webp) found in the selected folder(s)."
[ "$todo" -gt 0 ] || die "Nothing to do — all $found image(s) already have outputs."

# ---- confirm -------------------------------------------------------------
title "Ready"
fmtlabel="$FMT"; case "$FMT" in jpg|webp|avif) fmtlabel="$FMT q$QUALITY" ;; esac
printf '  folders : %d   recurse : %s   model : %s   format : %s\n  alpha : %s   trim : %s   bg : %s   streams : %s\n  found : %d   skip : %d   to do : %d\n' \
  "${#SRCS[@]}" "$RECURSE" "$MODEL" "$fmtlabel" "$ALPHA" "$TRIM" "$BG" "$STREAMS" "$found" "$skipped" "$todo"
IFS= read -rp "Start? [Y/n]: " go; [[ "$go" =~ ^[Nn] ]] && { echo "Cancelled."; exit 1; }

# ---- process (load model ONCE, parallel; live bar w/ rate + ETA) ---------
total=$todo
LOG="$(mktemp 2>/dev/null || echo "/tmp/bgone.$$.log")"
export NBG_MODEL="$MODEL" NBG_STREAMS="$STREAMS" NBG_BG="$BG" NBG_FMT="$FMT" NBG_QUALITY="$QUALITY"
export NBG_ALPHA="$([ "$ALPHA" = on ] && echo 1 || echo 0)" NBG_TRIM="$([ "$TRIM" = on ] && echo 1 || echo 0)"
export NBG_MATTE="$([ "$MATTE" = on ] && echo 1 || echo 0)" NBG_FEATHER="$FEATHER" NBG_SHRINK="$SHRINK"
bar(){ local d=$1 cols w pct fill i fb='' eb=''
  cols=$(tput cols 2>/dev/null || echo "${COLUMNS:-80}")
  w=$(( cols - 58 )); [ "$w" -lt 8 ] && w=8; [ "$w" -gt 44 ] && w=44
  pct=$(( d * 100 / total )); fill=$(( pct * w / 100 ))
  for ((i=0; i<fill; i++)); do fb+="$BAR_F"; done
  for ((i=fill; i<w; i++)); do eb+="$BAR_E"; done
  printf '\r\033[K[%s%s%s%s%s] %3d%%  %d/%d %s %d.%d/s %s ~%ds  %s%.14s%s' \
    "$G" "$fb" "$Z$Dim" "$eb" "$Z" "$pct" "$d" "$total" "$SEP" \
    "$(( $2 / 10 ))" "$(( $2 % 10 ))" "$SEP" "$3" "$Dim" "$4" "$Z"
}
printf '\n%sProcessing%s — model loads once · %s stream(s)\n\n' "$G" "$Z" "$STREAMS"
START=$(date +%s); n=0
printf '%s\0' "${PAIRS[@]}" | OMP_NUM_THREADS="$THREADS" "$PYTHON" "$WORKER" 2>>"$LOG" \
  | while IFS= read -r nm; do
      n=$((n+1)); now=$(date +%s); el=$(( now - START )); [ "$el" -lt 1 ] && el=1
      rem=$(( total - n )); r10=$(( n * 10 / el )); eta=$(( el * rem / n ))
      bar "$n" "$r10" "$eta" "$nm"
    done

# ---- summary -------------------------------------------------------------
dl=$(grep '^__DONE__' "$LOG" 2>/dev/null | tail -1); rest="${dl#__DONE__ }"
okc="${rest%% *}"; failc="${rest#* }"; [[ "$okc" =~ ^[0-9]+$ ]] || okc=$total; [[ "$failc" =~ ^[0-9]+$ ]] || failc=0
elapsed=$(( $(date +%s) - START ))
printf '\n\n%s%s done%s — %s ok' "$G" "$TICK" "$Z" "$okc"
[ "$failc" -gt 0 ] && printf '  %s%s %s failed%s' "$Rd" "$CROSS" "$failc" "$Z"
printf '  %s  %d folder(s)  %s  %ds\n' "$SEP" "${#SRCS[@]}" "$SEP" "$elapsed"
if [ "$failc" -gt 0 ]; then printf '%sfailed:%s\n' "$Rd" "$Z"; grep '^ERR ' "$LOG" 2>/dev/null | sed 's/^ERR /  /' | head -10; fi
rm -f "$LOG"
exit 0

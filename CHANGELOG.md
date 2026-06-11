# Changelog

All notable changes to bgone are documented here.
Format: [Keep a Changelog](https://keepachangelog.com); versioning: [SemVer](https://semver.org).

## [0.7.0] - 2026-06-11
### Added
- **BiRefNet models** — `birefnet-general-lite` (new default · SOTA quality, ~224 MB),
  `birefnet-general` (max quality), and `birefnet-portrait` (people/hair) joined the model
  menu, a big step up in edge/hair quality over U²-Net/ISNet.
- **Matte output** — a toggle to export the **black-&-white mask** instead of the cutout
  (for compositing), and a **greenscreen** background preset (`green` → chroma key).
- **Edge cleanup** — **Feather** (soften the mask edge) and **Shrink** (erode to kill the
  white halo) controls, in px.
- **Graphical version (PySide6/Qt).** A second front-end alongside the terminal tool —
  `bgone --gui`, plus a desktop launcher / app-menu icon. Dark, modern UI: pick whole
  folders (per-folder image counts + multi-select) **or individual images**, with
  model/format/background/quality/streams
  controls, alpha-matting / trim / resume toggles, a live progress bar with rate + ETA, and
  a **large preview pane with a draggable before/after split slider**: the cutout renders
  **on demand** when you pick an image (current settings), so you can judge it *before*
  committing to the full export — drag the handle to compare (full-left = cutout,
  full-right = original). Plus a clickable results filmstrip —
  each cutout rendered on a transparency checkerboard, with
  [Iconoir](https://iconoir.com) icons throughout. It reuses
  `bgone-worker.py` unchanged and shares settings with the terminal version via
  `~/.config/bgone/config`, so the two stay in lock-step. Installed by default;
  `BGONE_GUI=0 ./install.sh` keeps a terminal-only (headless/server) install.

### Changed
- **Output folder is now created *inside* each source folder** (`FOLDER/FOLDER_bgone/…`)
  instead of as a sibling (`FOLDER_bgone/` next to it), so cutouts live with the images
  they came from. Recursive scans skip any `*_bgone` folder, so re-runs never reprocess a
  previous run's output.
- **Installer now requires Python ≥3.11 and auto-selects a suitable interpreter.** It
  prefers the parallel-installable `python3.12`/`3.11` on RHEL/Rocky/Alma 9 (whose default
  `python3` is 3.9), leaving the system Python untouched, and rebuilds a venv that was
  created with an unsupported Python. Clear `dnf`/`apt` hint if none is present.
  (rembg/numpy/onnxruntime dropped 3.9/3.10 upstream, so the previous "Python 3.9+" claim
  was incorrect.)

## [0.6.0] - 2026-06-10
### Changed
- Output folder **and** file names are sanitised to be terminal-friendly: only
  `[A-Za-z0-9._-]` survive, and runs of anything else (spaces, parentheses, `&`, etc.)
  collapse to a single `_`. Subfolder structure is preserved when recursing; the source
  files are never touched.

## [0.5.1] - 2026-06-10
### Changed
- Output folders are now named **`FOLDER_bgone`** (no space) instead of `FOLDER _bgone`.
  The space tripped up downstream tooling and path handling; the name is now space-free.

## [0.5.0] - 2026-06-10
### Changed
- **Terminal UI polish** — colored Unicode block progress bar (`█`/`─`), `▸` section
  headers, and `✓`/`✗` summary glyphs.
- **Robust everywhere** — color is emitted only on a TTY with `NO_COLOR` unset, and
  Unicode glyphs only in a UTF-8 locale; otherwise output degrades to clean ASCII
  (`#`/`-`, `OK`/`x`), so it's safe in pipes, cron logs, and minimal terminals.
- **Outputs inherit the source folder's permissions** — cutouts are now as manageable
  as the originals (e.g. deletable over an open SMB share) even when produced as a
  different uid inside an unprivileged container.

## [0.4.0] - 2026-06-10
### Added
- **Expanded export formats for VFX/editing.** Beyond png/webp/jpg, the format menu now
  offers **tiff, tga, dds, jp2, avif** (alpha preserved), **bmp** (flat), and float/film
  formats **exr, hdr, dpx** (via imageio). Alpha-capable formats keep the cutout's
  transparency; the rest auto-composite onto the background. The quality prompt covers
  jpg/webp/avif. Aliases accepted: jpeg→jpg, tif→tiff, j2k/jpeg2000→jp2.

## [0.3.0] - 2026-06-10
### Added
- **Output format choice** — pick `png` (default), `webp`, `jpg`, or `exr` in the
  interactive flow (remembered like the other options). PNG/WebP/JPG via Pillow; EXR
  (32-bit float RGBA, alpha preserved) via imageio — handy for VFX/compositing pipelines.
  A quality prompt (1-100) appears for the lossy formats (jpg/webp). JPG has no
  transparency, so it auto-composites onto the chosen background (white if you left it
  transparent). Output extensions and the resume/skip + collision logic follow the format.
- Installer pre-stages imageio's FreeImage backend so EXR works offline after install;
  `imageio` is now pinned in `constraints.txt`.

## [0.2.0] - 2026-06-10
### Added
- **GPU install path with auto-detection.** `BGONE_GPU=auto|cpu|gpu` selects the rembg
  backend; `auto` (default) installs the GPU runtime when an NVIDIA GPU is detected and
  falls back to CPU otherwise. The worker now prints the ONNX execution provider it
  actually uses, so fleet operators can confirm GPU vs CPU per machine.
- **`bgone --verify-models`** — checks cached model weights against a shipped SHA-256
  manifest (`models.sha256`). Supply-chain integrity check for fleet deployments.
- **Reproducible installs.** Dependency versions are pinned via `constraints.txt`
  (rembg, onnxruntime, numpy, Pillow) so every workstation runs identical, vetted packages.
- `--help`/`--version`/`--verify-models` now work **without** the rembg runtime installed.

### Changed
- Installer is **idempotent / upgrade-in-place**, preflights `python3-venv`/`ensurepip`
  with a clear error, and **refuses to clobber** an unrelated `/usr/local/bin/bgone`
  unless `BGONE_FORCE=1`.
- CI now also shellchecks `uninstall.sh`, enforces VERSION/CHANGELOG consistency, and
  smoke-tests that `--version`/`--help` run with no runtime present.

## [0.1.0] - 2026-06-08
### Added
- Initial release: pure-terminal batch background remover built on
  [rembg](https://github.com/danielgatis/rembg). Bulk multi-folder select with image
  counts, recurse, 5-model menu, alpha matting, trim-to-content, background
  (transparent/white/black/#hex), resume/skip, remembered settings, per-folder `_bgone`
  output with collision disambiguation, parallel "streams" (load model once), live
  progress bar with throughput + ETA, tab-completion, install/uninstall scripts, CI.

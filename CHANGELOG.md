# Changelog

All notable changes to bgone are documented here.
Format: [Keep a Changelog](https://keepachangelog.com); versioning: [SemVer](https://semver.org).

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

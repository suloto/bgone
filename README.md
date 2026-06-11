# bgone

[![ci](https://github.com/suloto/bgone/actions/workflows/ci.yml/badge.svg)](https://github.com/suloto/bgone/actions/workflows/ci.yml)

A friendly, **pure-terminal** batch background remover — built on
[rembg](https://github.com/danielgatis/rembg).

Point it at folders of images and it strips their backgrounds — keep them transparent or
composite onto a color — and writes the cutouts to a `FOLDER_bgone` subfolder inside each
source folder, in your choice of format (PNG, WebP, JPG, TIFF, EXR, and more). It loads the
model once and processes many images in parallel, picks up a GPU when there is one, and
resumes where it left off.

![before and after](docs/before-after.png)

![bgone demo](docs/demo.gif)

<details>
<summary>Full interactive flow</summary>

![bgone flow](docs/screenshot.png)

</details>

## Features
- **Bulk multi-folder select** — numbered picklist (`1 3 5-8`, `all`, `0`=this folder), with optional **recurse** into subfolders
- **Per-folder output** — each `FOLDER` → a `FOLDER_bgone` subfolder **inside it** (subfolder tree mirrored when recursing; the `_bgone` folder is skipped on re-runs); output folder + file names are sanitised to be **terminal-friendly** (spaces/specials → `_`)
- **Loads the model once** and processes N images in parallel ("streams") — one model in RAM
- **Trim to content** — crop each cutout to the subject's bounding box
- **Edge cleanup** — **feather** (soften the mask edge) and **shrink** (erode to kill a white halo), in px
- **Matte output** — export the **B&W mask** instead of the cutout (for compositing)
- **Background** — keep it transparent, or composite onto white / black / **green (chroma key)** / a custom `#hex`
- **Output formats** — `png` (default) plus alpha-capable `webp` `tiff` `tga` `dds` `jp2` `avif`, flat `jpg` `bmp`, and float/film `exr` `hdr` `dpx` (VFX/compositing); quality knob for the lossy ones
- **Live progress** — bar with throughput + ETA, plus a pass/fail summary
- **Remembers your last settings** (model, streams, options)
- **Tab-completion** for the `bgone` command and the folder prompt
- **GPU-ready** — uses a hardware execution provider if onnxruntime exposes one, else CPU
- Models: **`birefnet-general-lite`** (default · SOTA quality), `birefnet-general`, `birefnet-portrait`, `u2net`, `isnet-general-use`, `isnet-anime`, `u2netp`, `silueta`

## Install
**Requirements:** Linux, **Python 3.11+**, and `sudo`. (RHEL/Rocky/Alma 9 default to Python 3.9 — install a newer one with `sudo dnf install -y python3.12`; Debian/Ubuntu may need `python3.12-venv`/`python3.11-venv`.) The installer auto-selects the newest suitable Python on the box, or pass `PYTHON=/path/to/python3.12 sudo -E ./install.sh`.
```bash
sudo ./install.sh                 # installs to /opt/bgone
# or pick a location:
sudo PREFIX=/opt/myplace ./install.sh
```
Creates a Python venv, installs `rembg` (versions pinned via `constraints.txt`), drops in the tool, and registers the `bgone` command + bash completion. The installer is **idempotent** (re-run it to upgrade in place) and **won't overwrite** an unrelated `/usr/local/bin/bgone` unless you pass `BGONE_FORCE=1`.

**GPU:** the installer **auto-detects** an NVIDIA GPU and installs the GPU runtime, else CPU. Force it with `sudo BGONE_GPU=gpu ./install.sh` (or `BGONE_GPU=cpu`). At runtime bgone prints which ONNX execution provider it actually used, so you can confirm GPU vs CPU per machine.

**Fleet / production:** versions are pinned in `constraints.txt` so every workstation runs identical, vetted packages, and you can verify model-weight integrity on any machine with `bgone --verify-models` (checks the cached `.onnx` files against the shipped `models.sha256`).

## Usage
```bash
bgone                    # interactive: pick folders, model, options
bgone /path/to/images    # run directly on one or more folders
bgone --gui              # graphical version (PySide6/Qt) — also in your desktop app menu
bgone i in.png out.png   # passthrough to the underlying rembg CLI
bgone --verify-models    # check cached model weights vs the shipped checksums
bgone --help
```

## GUI vs terminal
bgone ships **two front-ends over the same engine**, so use whichever fits:
- **Terminal** — `bgone` (the default). Great over SSH, in cron, or on headless servers.
- **Graphical** — `bgone --gui`, or click **bgone** in your desktop's app menu. A dark,
  modern Qt window: pick whole folders (with image counts) **or individual images**, choose
  model / format / background / quality / streams, toggle alpha-matting / trim / resume,
  and use the **before/after preview** — including a **draggable split slider** — to render
  a single image's cutout on demand and judge it *before* exporting the whole batch — then
  watch a live progress bar and a clickable filmstrip of cutouts on a transparency checkerboard.

Both reuse the same worker and **share settings** (`~/.config/bgone/config`), so your last
choices carry across. The GUI is installed by default; `BGONE_GUI=0 ./install.sh` gives a
terminal-only install (no PySide6) for headless boxes.

## Uninstall
```bash
sudo ./uninstall.sh            # from the cloned repo
sudo /opt/bgone/uninstall.sh   # or the installed copy — no repo needed
sudo bgone --uninstall         # or straight from the command
```
Removes the venv, the `bgone` command, bash completion, and the downloaded models under `/opt/bgone`. Add `-y` to skip the confirmation; per-user settings in `~/.config/bgone` are left in place.

## Models
Each model's ONNX weights are downloaded from upstream the first time you use it, then
cached and reused offline. By default `bgone` keeps them in a shared `models/` folder
next to the install (`$PREFIX/models`, made world-writable so every user populates the
same cache instead of re-downloading per home). Set `U2NET_HOME` to point elsewhere
(e.g. the classic `~/.u2net`). Each model carries its **own** upstream license — check
those before redistributing weights or using output commercially.

## Credits & license
Built on **[rembg](https://github.com/danielgatis/rembg)** by Daniel Gatis (MIT).
GUI icons from **[Iconoir](https://iconoir.com)** by Luca Burgio (MIT).
`bgone` is released under the MIT License — see [LICENSE](./LICENSE).

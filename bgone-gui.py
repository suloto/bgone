#!/usr/bin/env python3
"""bgone GUI — a polished Qt (PySide6) front-end for the bgone background remover.

It is a *second front-end* alongside the terminal `bgone`: it builds the exact same
per-folder work list (each FOLDER -> a sibling `FOLDER_bgone`, terminal-friendly
names, resume-skip) and drives `bgone-worker.py` as a subprocess — the same worker
the terminal uses (NUL-delimited input/output pairs in; completed basenames and a
final `__DONE__ <ok> <fail>` out). Settings are shared with the terminal version via
``$XDG_CONFIG_HOME/bgone/config`` so switching between the two keeps your choices.

Run via:  bgone --gui     (or the desktop launcher)
Self-test: QT_QPA_PLATFORM=offscreen python bgone-gui.py --selftest [DIR]
"""
import os
import re
import signal
import sys
import tempfile
import time

from PySide6.QtCore import (Qt, QByteArray, QPoint, QProcess, QProcessEnvironment,
                            QRect, QSize, QUrl, QTimer)
from PySide6.QtGui import (QColor, QFont, QIcon, QImage, QPainter, QPalette, QPen,
                           QPixmap, QDesktopServices)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMenu, QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

VERSION = "0.7.2"

# ---- catalogue (kept in lock-step with bgone.sh) ----------------------------
MODELS = [
    ("birefnet-general-lite", "photos · SOTA quality (recommended)", "~224MB"),
    ("u2net",                 "photos / realistic / 3D",             "168MB"),
    ("isnet-general-use",     "general purpose",                     "170MB"),
    ("isnet-anime",           "anime / illustration",                "168MB"),
    ("birefnet-general",      "photos · max quality (large)",        "~900MB"),
    ("birefnet-portrait",     "people / hair",                       "~900MB"),
    ("u2netp",                "lightweight, fast",                   "4MB"),
    ("silueta",               "u2net quality, smaller",              "43MB"),
]
FORMATS = ["png", "webp", "jpg", "tiff", "tga", "bmp", "avif", "jp2", "dds", "exr", "hdr", "dpx"]
LOSSY = {"jpg", "webp", "avif"}          # quality slider applies
FLAT = {"jpg", "bmp", "hdr", "dpx"}      # no alpha channel -> must composite a bg
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
PV_LOADABLE = {"png", "webp", "jpg", "jpeg", "tiff", "tga", "bmp", "jp2"}  # previewable formats
THUMB = 116
MAX_THUMBS = 30

# ---- theme (flat dark · photo-editor) ---------------------------------------
BG0 = "#0f1115"     # window / canvas area
BG1 = "#16181d"     # tool-rail panel
BG2 = "#1c1f26"     # inputs / buttons
CANVAS = "#0b0c0f"  # preview canvas inset
BORDER = "#2a2e37"
TEXT, MUTED = "#e7e9ee", "#8b909c"
ACCENT, ACCENT_H, ACCENT_P = "#4f8cff", "#6ba0ff", "#3f78e6"
OK_C, ERR_C = "#46d19e", "#ff6b6b"

QSS = f"""
* {{ outline: 0; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}
QLabel {{ background: transparent; }}
QWidget#rail {{ background: {BG1}; border-right: 1px solid {BORDER}; }}
QFrame#appbar {{ background: {BG0}; border-bottom: 1px solid {BORDER}; }}
QFrame#canvas {{ background: {CANVAS}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#divider {{ background: {BORDER}; border: 0; }}
QLabel#wordmark {{ font-size: 21px; font-weight: 800; color: {TEXT}; }}
QLabel#tag {{ color: {MUTED}; font-size: 12px; }}
QLabel#section {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; }}
QLabel#hint {{ color: {MUTED}; font-size: 11px; }}
QLabel#fieldlabel {{ color: {MUTED}; font-size: 11px; }}
QLineEdit, QComboBox, QSpinBox {{
    background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 10px; min-height: 20px; color: {TEXT}; selection-background-color: {ACCENT};
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover {{ border-color: #3a3f4b; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px;
    selection-background-color: {ACCENT}; selection-color: white; padding: 4px;
}}
QListWidget {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background: #242832; }}
QListWidget::item:selected {{ background: #25304a; color: {TEXT}; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px;
    border: 1.5px solid #353a45; background: {BG2}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QPushButton {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 12px; color: {TEXT}; }}
QPushButton:hover {{ background: #242832; border-color: #3a3f4b; }}
QPushButton:pressed {{ background: #191c22; }}
QPushButton:disabled {{ color: #565b66; }}
QPushButton#primary {{ background: {ACCENT}; border: 0; color: white; font-weight: 700;
    padding: 13px 18px; border-radius: 10px; font-size: 14px; }}
QPushButton#primary:hover {{ background: {ACCENT_H}; }}
QPushButton#primary:pressed {{ background: {ACCENT_P}; }}
QPushButton#primary:disabled {{ background: #2b3550; color: #8b90a3; }}
QPushButton#seg {{ padding: 8px 18px; border-radius: 8px; min-height: 16px; }}
QPushButton#seg:checked {{ background: {ACCENT}; border: 0; color: white; }}
QPushButton#seg:disabled {{ color: #565b66; }}
QPushButton#swatch {{ border-radius: 8px; min-width: 30px; max-width: 30px; min-height: 30px; }}
QSlider::groove:horizontal {{ height: 6px; background: {BG2}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; height: 16px;
    margin: -6px 0; border-radius: 8px; }}
QProgressBar {{ background: {BG2}; border: 0; border-radius: 6px; height: 10px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QScrollArea {{ border: 0; background: transparent; }}
QLabel#preview {{ background: transparent; color: {MUTED}; }}
QPlainTextEdit {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px;
    color: {MUTED}; font-family: monospace; font-size: 12px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #353a45; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #353a45; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
"""


# ---- icons (Iconoir SVGs, tinted to the theme) ------------------------------
_ICON_CACHE = {}


def _icon_dir():
    env = os.environ.get("BGONE_ICONS")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "icons"), os.path.join(here, "assets", "icons"), "/opt/bgone/icons"):
        if os.path.isdir(c):
            return c
    return None


def icon_pixmap(name, color=TEXT, size=18):
    key = (name, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    dpr = 2                                  # render at 2x for crisp icons on HiDPI
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.transparent)
    d = _icon_dir()
    if d:
        try:
            with open(os.path.join(d, name + ".svg"), encoding="utf-8") as fh:
                svg = fh.read().replace("currentColor", color)
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            p = QPainter(pm)
            renderer.render(p)
            p.end()
        except Exception:
            pass
    pm.setDevicePixelRatio(dpr)
    _ICON_CACHE[key] = pm
    return pm


def icon(name, color=TEXT, size=18):
    return QIcon(icon_pixmap(name, color, size))


# ---- shared config (same file/keys as bgone.sh) ----------------------------
def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "bgone", "config")


def read_config():
    cfg = {}
    try:
        with open(config_path()) as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return cfg


def write_config(model_idx, streams, alpha, trim, bg, skip, fmt, quality, matte, feather, shrink):
    p = config_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(f"CFG_MODEL={model_idx}\nCFG_STREAMS={streams}\n"
                     f"CFG_ALPHA={'on' if alpha else 'off'}\nCFG_TRIM={'on' if trim else 'off'}\n"
                     f"CFG_BG={bg}\nCFG_SKIP={'on' if skip else 'off'}\n"
                     f"CFG_FMT={fmt}\nCFG_QUALITY={quality}\n"
                     f"CFG_MATTE={'on' if matte else 'off'}\n"
                     f"CFG_FEATHER={feather}\nCFG_SHRINK={shrink}\n")
    except OSError:
        pass


def model_dir():
    d = os.environ.get("U2NET_HOME")
    if d:
        return d
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "models")
    return cand if os.path.isdir(cand) else "/opt/bgone/models"


# ---- work-list builder (mirrors bgone.sh's sanitising rules) ----------------
def _san(s):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
    return s or "x"


def list_subfolders(parent):
    """Return [(path, image_count)] for immediate subfolders, sorted by name."""
    out = []
    try:
        for name in sorted(os.listdir(parent)):
            p = os.path.join(parent, name)
            if os.path.isdir(p):
                out.append((p, count_images(p, recurse=False)))
    except OSError:
        pass
    return out


def count_images(folder, recurse):
    n = 0
    if recurse:
        for _root, _dirs, files in os.walk(folder):
            n += sum(1 for f in files if f.lower().endswith(IMG_EXT))
    else:
        try:
            n = sum(1 for f in os.listdir(folder)
                    if f.lower().endswith(IMG_EXT) and os.path.isfile(os.path.join(folder, f)))
        except OSError:
            pass
    return n


def scan_folder(folder, recurse):
    """Image files in `folder` (recursively if asked), sorted, full paths. Never descends
    into a `*_bgone` output folder, so re-runs don't treat last run's cutouts as inputs."""
    files = []
    if recurse:
        for root, dirs, fs in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.endswith("_bgone")]
            for f in sorted(fs):
                if f.lower().endswith(IMG_EXT):
                    files.append(os.path.join(root, f))
    else:
        try:
            for f in sorted(os.listdir(folder)):
                fp = os.path.join(folder, f)
                if f.lower().endswith(IMG_EXT) and os.path.isfile(fp):
                    files.append(fp)
        except OSError:
            pass
    return files


def build_pairs(jobs, fmt, skip):
    """jobs: list of (src_root, [file paths under src_root]). Each src_root gets a
    `<name>_bgone` subfolder *inside it*; a file keeps its (sanitised) path relative to
    its src_root, so a single picked image lands in the same place its folder would
    produce. Returns (pairs, out_paths, found, skipped) — `pairs` is the flat
    [src, dst, ...] the worker consumes; `out_paths` is the output list for thumbnails."""
    pairs, out_paths = [], []
    found = skipped = 0
    used = set()
    for src_root, files in jobs:
        root = src_root.rstrip("/")
        ob = _san(os.path.basename(root))
        out_dir = os.path.join(root, ob + "_bgone")   # inside the source folder
        for f in files:
            found += 1
            rel = os.path.relpath(f, root)
            stem, ext = os.path.splitext(rel)
            san = "/".join(_san(seg) for seg in stem.split(os.sep)) or "x"
            out = os.path.join(out_dir, f"{san}.{fmt}")
            if out in used:                       # disambiguate name clashes by keeping the ext
                out = os.path.join(out_dir, f"{san}.{_san(ext.lstrip('.'))}.{fmt}")
            used.add(out)
            if skip and os.path.exists(out):
                skipped += 1
                continue
            pairs += [f, out]
            out_paths.append(out)
    return pairs, out_paths, found, skipped


# ---- thumbnails -------------------------------------------------------------
def checker_pixmap(w, h, cell=11):
    pm = QPixmap(w, h)
    p = QPainter(pm)
    p.fillRect(0, 0, w, h, QColor("#3a3d46"))
    p.fillRect(0, 0, w, h, QColor("#33363e"))
    c2 = QColor("#3f424c")
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if ((x // cell) + (y // cell)) % 2 == 0:
                p.fillRect(x, y, cell, cell, c2)
    p.end()
    return pm


def thumb_pixmap(path):
    """Render an output image onto a checkerboard tile (so alpha shows). PIL loads
    everything bgone writes except the float/film formats; those get no preview."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None
    im.thumbnail((THUMB - 12, THUMB - 12))
    data = im.tobytes("raw", "RGBA")
    qi = QImage(data, im.width, im.height, QImage.Format_RGBA8888).copy()
    tile = checker_pixmap(THUMB, THUMB)
    p = QPainter(tile)
    p.drawImage((THUMB - im.width) // 2, (THUMB - im.height) // 2, qi)
    p.setPen(QColor(0, 0, 0, 60))
    p.drawRect(0, 0, THUMB - 1, THUMB - 1)
    p.end()
    return tile


def render_fit(path, w, h, checker, crop=None):
    """Scale an image to fit w×h (keeping aspect) and composite it: cutouts onto a
    transparency checkerboard, source images onto a flat dark panel. `crop` (a bbox)
    trims both sides of a comparison to the same region (used for Trim-to-content)."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None
    if crop:
        im = im.crop(crop)
    im.thumbnail((max(16, w), max(16, h)))
    data = im.tobytes("raw", "RGBA")
    qi = QImage(data, im.width, im.height, QImage.Format_RGBA8888).copy()
    if checker:
        canvas = checker_pixmap(im.width, im.height)
    else:
        canvas = QPixmap(im.width, im.height)
        canvas.fill(QColor("#101114"))
    p = QPainter(canvas)
    p.drawImage(0, 0, qi)
    p.setPen(QColor(0, 0, 0, 70))
    p.drawRect(0, 0, im.width - 1, im.height - 1)
    p.end()
    return canvas


def _crop_bbox(path):
    """Bounding box of the subject (alpha for a cutout, luminance for a matte) — used to
    crop a comparison to the trimmed region so both sides line up."""
    try:
        from PIL import Image
        im = Image.open(path)
        a = im.getchannel("A") if "A" in im.getbands() else im.convert("L")
        return a.getbbox()
    except Exception:
        return None


class ClickableLabel(QLabel):
    """A QLabel that calls on_click(payload) when pressed (for filmstrip thumbs)."""
    def __init__(self, on_click, payload):
        super().__init__()
        self._on_click = on_click
        self._payload = payload
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, _e):
        self._on_click(self._payload)


class PreviewLabel(QLabel):
    """Large preview that re-renders its current image to fit whenever it's resized."""
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(360, 240)
        self._path = None
        self._checker = True
        self.clear_preview()

    def show_image(self, path, checker):
        self._path = path
        self._checker = checker
        self._render()

    def clear_preview(self):
        self._path = None
        size = 220
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.drawPixmap(int((size - 56) / 2), 62, icon_pixmap("media-image", MUTED, 56))
        p.setPen(QColor(MUTED))
        p.drawText(QRect(0, 130, size, 24), Qt.AlignHCenter, "preview will appear here")
        p.end()
        self.setText("")
        self.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._path:
            self._render()

    def _render(self):
        pm = render_fit(self._path, max(60, self.width() - 10), max(60, self.height() - 10), self._checker)
        if pm is None:
            self.setText("(no preview for this format)")
        else:
            self.setText("")
            self.setPixmap(pm)


class ComparePreview(QWidget):
    """Preview pane: shows the source, the cutout, or a draggable before/after split.
    In split view the left of the handle is the original, the right is the cutout."""
    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 240)
        self._before = None          # source path
        self._after = None           # cutout path
        self._view = "after"         # before | after | split
        self._split = 0.5
        self._message = None
        self._cache = {}
        self._img_rect = None
        self._crop = None            # bbox to crop both sides to (Trim-to-content)

    def set_single(self, path, checker):
        self._message = None
        self._crop = None
        if checker:
            self._after = path
            self._view = "after"
        else:
            self._before = path
            self._view = "before"
        self._cache.clear()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def set_compare(self, before, after, crop=None):
        self._message = None
        self._before, self._after, self._view = before, after, "split"
        self._crop = crop
        self._cache.clear()
        self.setCursor(Qt.SplitHCursor)
        self.update()

    def show_message(self, text):
        self._message = text
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def clear_preview(self):
        self._before = self._after = self._message = None
        self._view = "after"
        self._crop = None
        self._cache.clear()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._cache.clear()
        self.update()

    def _pm(self, which):
        if which in self._cache:
            return self._cache[which]
        path = self._before if which == "before" else self._after
        pm = (render_fit(path, max(60, self.width() - 10), max(60, self.height() - 10),
                         checker=(which == "after"), crop=self._crop) if path else None)
        self._cache[which] = pm
        return pm

    def paintEvent(self, e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        if self._message is not None:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, self._message)
            p.end()
            return
        if self._view == "split":
            pb, pa = self._pm("before"), self._pm("after")
            if pb and pa:
                iw, ih = pa.width(), pa.height()
                x, y = (w - iw) // 2, (h - ih) // 2
                sx = x + int(iw * self._split)
                p.drawPixmap(x, y, pb)                                  # original (full)
                p.save()
                p.setClipRect(sx, y, x + iw - sx, ih)
                p.drawPixmap(x, y, pa)                                  # cutout (right of handle)
                p.restore()
                p.setPen(QPen(QColor("white"), 2))
                p.drawLine(sx, y, sx, y + ih)
                p.setBrush(QColor(255, 255, 255))
                p.setPen(QPen(QColor(0, 0, 0, 90), 1))
                p.drawEllipse(QPoint(sx, y + ih // 2), 9, 9)
                self._img_rect = (x, y, iw, ih)
                p.end()
                return
        elif self._view in ("before", "after"):
            pm = self._pm(self._view)
            if pm:
                p.drawPixmap((w - pm.width()) // 2, (h - pm.height()) // 2, pm)
                p.end()
                return
        p.drawPixmap((w - 56) // 2, h // 2 - 44, icon_pixmap("media-image", MUTED, 56))
        p.setPen(QColor(MUTED))
        p.drawText(QRect(0, h // 2 + 18, w, 24), Qt.AlignHCenter, "preview will appear here")
        p.end()

    def mousePressEvent(self, e):
        self._drag(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._drag(e)

    def _drag(self, e):
        if self._view != "split" or not self._img_rect:
            return
        x, y, iw, ih = self._img_rect
        if iw > 0:
            self._split = min(1.0, max(0.0, (e.position().x() - x) / iw))
            self.update()


class SourceList(QListWidget):
    """Source folders/images list; Delete/Backspace removes the highlighted row."""
    def __init__(self, remove_cb):
        super().__init__()
        self._remove_cb = remove_cb

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            it = self.currentItem()
            if it is not None:
                self._remove_cb(it)
                return
        super().keyPressEvent(e)


# ---- UI helpers -------------------------------------------------------------
def card(title=None, icon_name=None):
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(11)
    if title:
        head = QHBoxLayout()
        head.setSpacing(8)
        if icon_name:
            ic = QLabel()
            ic.setPixmap(icon_pixmap(icon_name, MUTED, 15))
            head.addWidget(ic)
        lbl = QLabel(title.upper())
        lbl.setObjectName("section")
        head.addWidget(lbl)
        head.addStretch(1)
        lay.addLayout(head)
    return f, lay


def row(*widgets, stretch_last=False):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(9)
    for i, x in enumerate(widgets):
        if isinstance(x, str):
            x = QLabel(x)
        h.addWidget(x)
        if stretch_last and i == 0:
            h.addStretch(1)
    return w


def section_label(text, icon_name=None):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 4, 0, 2)
    h.setSpacing(8)
    if icon_name:
        ic = QLabel()
        ic.setPixmap(icon_pixmap(icon_name, MUTED, 14))
        h.addWidget(ic)
    lbl = QLabel(text.upper())
    lbl.setObjectName("section")
    h.addWidget(lbl)
    h.addStretch(1)
    return w


def divider():
    f = QFrame()
    f.setObjectName("divider")
    f.setFixedHeight(1)
    return f


class Bgone(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("bgone — background remover")
        self.setMinimumSize(1040, 680)
        self.proc = None
        self._obuf = b""
        self._errbuf = ""
        self._pending = []      # output paths awaiting a thumbnail
        self._thumbs = []       # (widget) FIFO
        self._done = 0
        self._total = 0
        self._t0 = 0.0
        self._out_dirs = []
        self._out_to_src = {}        # output path -> source path (for before/after)
        self._preview_src = None
        self._preview_out = None
        self.pvproc = None           # one-off worker that renders the on-demand cutout
        self._pv_cache = {}          # preview key -> rendered temp path
        self._pv_pending = None
        self._pv_dir = None          # per-user temp dir for preview outputs (lazy)
        self._pv_timer = QTimer(self)        # debounce auto-render on selection
        self._pv_timer.setSingleShot(True)
        self._pv_timer.timeout.connect(self._auto_render)
        self._build_ui()
        self._load_settings()

    # ---- layout ----
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- app bar ----
        appbar = QFrame()
        appbar.setObjectName("appbar")
        ab = QHBoxLayout(appbar)
        ab.setContentsMargins(18, 11, 18, 11)
        ab.setSpacing(9)
        brand = QLabel()
        brand.setPixmap(icon_pixmap("magic-wand", ACCENT, 22))
        ab.addWidget(brand)
        mark = QLabel("bgone")
        mark.setObjectName("wordmark")
        sub = QLabel("background remover")
        sub.setObjectName("tag")
        sub.setContentsMargins(4, 7, 0, 0)
        ab.addWidget(mark)
        ab.addWidget(sub)
        ab.addStretch(1)
        self.provider_lbl = QLabel("")
        self.provider_lbl.setObjectName("tag")
        ab.addWidget(self.provider_lbl)
        root.addWidget(appbar)

        # ---- main: tool rail | preview canvas ----
        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        root.addLayout(main, 1)

        # === LEFT: tool rail (controls scroll, so they never squash) ===
        rail = QWidget()
        rail.setObjectName("rail")
        rail.setFixedWidth(396)
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(16, 14, 16, 16)
        rl.setSpacing(12)
        main.addWidget(rail)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")
        scroll.viewport().setAutoFillBackground(False)   # show the rail grey, not the dark window bg
        inner = QWidget()
        cl = QVBoxLayout(inner)
        cl.setContentsMargins(0, 0, 4, 0)
        cl.setSpacing(7)
        scroll.setWidget(inner)
        rl.addWidget(scroll, 1)

        # --- SOURCE ---
        cl.addWidget(section_label("source", "folder"))
        self.parent_edit = QLineEdit()
        self.parent_edit.setPlaceholderText("folder of image folders")
        self.parent_edit.returnPressed.connect(lambda: self._scan(self.parent_edit.text()))
        cl.addWidget(self.parent_edit)
        pick = QPushButton("Choose folder…")
        pick.setIcon(icon("folder", TEXT, 16))
        pick.setIconSize(QSize(16, 16))
        pick.clicked.connect(self._browse)
        cl.addWidget(pick)
        pick_img = QPushButton("Choose images…")
        pick_img.setIcon(icon("media-image", TEXT, 16))
        pick_img.setIconSize(QSize(16, 16))
        pick_img.clicked.connect(self._browse_images)
        cl.addWidget(pick_img)
        self.folders = SourceList(self._remove_source)
        self.folders.setSelectionMode(QListWidget.SingleSelection)
        self.folders.setFixedHeight(78)
        self.folders.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.folders.setTextElideMode(Qt.ElideRight)
        self.folders.setWordWrap(False)
        self.folders.itemClicked.connect(self._on_source_clicked)
        self.folders.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folders.customContextMenuRequested.connect(self._folders_menu)
        cl.addWidget(self.folders)
        selrow = QHBoxLayout()
        for txt, ic, fn in (("Select all", "check", lambda: self._check_all(True)),
                            ("Clear", "xmark", lambda: self._check_all(False))):
            b = QPushButton(txt)
            b.setIcon(icon(ic, TEXT, 15))
            b.setIconSize(QSize(15, 15))
            b.clicked.connect(fn)
            selrow.addWidget(b)
        selrow.addStretch(1)
        cl.addLayout(selrow)
        self.recurse = QCheckBox("Recurse into subfolders")
        cl.addWidget(self.recurse)

        cl.addSpacing(5)
        cl.addWidget(divider())
        cl.addSpacing(5)

        # --- OPTIONS (compact label-beside-field; in the scroll area it can't squash) ---
        cl.addWidget(section_label("options", "settings"))
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(1, 1)

        def gfield(r, text, widget):
            lab = QLabel(text)
            lab.setObjectName("fieldlabel")
            grid.addWidget(lab, r, 0)
            grid.addWidget(widget, r, 1)

        self.model = QComboBox()
        for name, desc, size in MODELS:
            self.model.addItem(f"{name}  ·  {desc}")
        gfield(0, "Model", self.model)

        self.fmt = QComboBox()
        self.fmt.addItems(FORMATS)
        self.fmt.currentTextChanged.connect(self._fmt_changed)
        gfield(1, "Format", self.fmt)

        self.quality = QSlider(Qt.Horizontal)
        self.quality.setRange(1, 100)
        self.quality.setValue(90)
        self.qval = QLabel("90")
        self.qval.setMinimumWidth(26)
        self.quality.valueChanged.connect(lambda v: self.qval.setText(str(v)))
        self.qrow = row(self.quality, self.qval)
        self.qlabel = QLabel("Quality")
        self.qlabel.setObjectName("fieldlabel")
        grid.addWidget(self.qlabel, 2, 0)
        grid.addWidget(self.qrow, 2, 1)

        self.bg = QComboBox()
        self.bg.addItems(["transparent", "white", "black", "green", "custom…"])
        self.bg.currentTextChanged.connect(self._bg_changed)
        self.swatch = QPushButton()
        self.swatch.setObjectName("swatch")
        self.swatch.clicked.connect(self._pick_color)
        self.swatch.hide()
        self._custom_hex = "#888888"
        self.bgrow = row(self.bg, self.swatch)
        gfield(3, "Background", self.bgrow)

        self.streams = QSpinBox()
        self.streams.setRange(1, max(1, os.cpu_count() or 4))
        self.streams.setValue(min(4, self.streams.maximum()))
        gfield(4, "Streams", self.streams)
        self.feather = QSpinBox()
        self.feather.setRange(0, 20)
        gfield(5, "Feather px", self.feather)
        self.shrink = QSpinBox()
        self.shrink.setRange(0, 20)
        gfield(6, "Shrink px", self.shrink)
        # don't let the long model name force the column wider than the rail (it would
        # overflow and get clipped by the divider) — let combos shrink and elide instead
        for _c in (self.model, self.fmt, self.bg):
            _c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            _c.setMinimumContentsLength(6)
        cl.addLayout(grid)

        cl.addSpacing(2)
        self.alpha = QCheckBox("Alpha matting  (softer edges, photos)")
        self.trim = QCheckBox("Trim to content  (crop margins)")
        self.matte = QCheckBox("Matte  (output the B&W mask)")
        self.skip = QCheckBox("Skip files already done  (resume)")
        self.skip.setChecked(True)
        for c in (self.alpha, self.trim, self.matte, self.skip):
            cl.addWidget(c)
        cl.addStretch(1)

        # rail bottom (fixed): status + progress + primary action
        self.status = QLabel("Pick folders or images to begin.")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        rl.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.hide()                 # only shown while a batch is actually running
        rl.addWidget(self.bar)
        self.run_btn = QPushButton("Remove backgrounds")
        self.run_btn.setObjectName("primary")
        self.run_btn.setIcon(icon("magic-wand", "#ffffff", 18))
        self.run_btn.setIconSize(QSize(18, 18))
        self.run_btn.clicked.connect(self._run)
        rl.addWidget(self.run_btn)

        # === RIGHT: preview canvas ===
        cv = QWidget()
        cvl = QVBoxLayout(cv)
        cvl.setContentsMargins(16, 14, 16, 16)
        cvl.setSpacing(10)
        main.addWidget(cv, 1)

        topbar = QHBoxLayout()
        topbar.setSpacing(8)
        self.caption = QLabel("")
        self.caption.setObjectName("hint")
        topbar.addWidget(self.caption)
        topbar.addStretch(1)
        self.details_btn = QPushButton("Details")
        self.details_btn.setIcon(icon("list", TEXT, 15))
        self.details_btn.setIconSize(QSize(15, 15))
        self.details_btn.setCheckable(True)
        self.details_btn.toggled.connect(self._toggle_log)
        topbar.addWidget(self.details_btn)
        self.open_btn = QPushButton("Open output")
        self.open_btn.setIcon(icon("open-new-window", TEXT, 15))
        self.open_btn.setIconSize(QSize(15, 15))
        self.open_btn.clicked.connect(self._open_out)
        self.open_btn.setEnabled(False)
        topbar.addWidget(self.open_btn)
        cvl.addLayout(topbar)

        canvas = QFrame()
        canvas.setObjectName("canvas")
        canl = QVBoxLayout(canvas)
        canl.setContentsMargins(12, 12, 12, 12)
        self.preview = ComparePreview()
        self.preview.setObjectName("preview")
        canl.addWidget(self.preview)
        cvl.addWidget(canvas, 1)

        self.strip_area = QScrollArea()
        self.strip_area.setWidgetResizable(True)
        self.strip_area.setFixedHeight(THUMB + 22)
        self.strip_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.strip_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        stripw = QWidget()
        self.strip = QHBoxLayout(stripw)
        self.strip.setContentsMargins(2, 2, 2, 2)
        self.strip.setSpacing(8)
        self.strip.addStretch(1)
        self.strip_area.setWidget(stripw)
        self.strip_area.hide()
        cvl.addWidget(self.strip_area)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(96)
        self.log.hide()
        cvl.addWidget(self.log)

        # re-render the After preview when a cutout-affecting setting changes
        self.model.currentIndexChanged.connect(self._invalidate_preview)
        self.fmt.currentTextChanged.connect(self._invalidate_preview)
        self.bg.currentTextChanged.connect(self._invalidate_preview)
        self.alpha.toggled.connect(self._invalidate_preview)
        self.matte.toggled.connect(self._invalidate_preview)
        self.trim.toggled.connect(lambda *_: self._apply_preview())   # re-crop preview, no re-render
        self.feather.valueChanged.connect(self._invalidate_preview)
        self.shrink.valueChanged.connect(self._invalidate_preview)

        self._fmt_changed(self.fmt.currentText())
        self._bg_changed(self.bg.currentText())

    # ---- settings ----
    def _load_settings(self):
        c = read_config()
        try:
            mi = int(c.get("CFG_MODEL", "1"))
            if 1 <= mi <= len(MODELS):
                self.model.setCurrentIndex(mi - 1)
        except ValueError:
            pass
        fmt = c.get("CFG_FMT", "png").lower()
        if fmt in FORMATS:
            self.fmt.setCurrentText(fmt)
        try:
            q = int(c.get("CFG_QUALITY", "90"))
            self.quality.setValue(max(1, min(100, q)))
        except ValueError:
            pass
        try:
            s = int(c.get("CFG_STREAMS", "4"))
            self.streams.setValue(max(1, min(self.streams.maximum(), s)))
        except ValueError:
            pass
        self.alpha.setChecked(c.get("CFG_ALPHA") == "on")
        self.trim.setChecked(c.get("CFG_TRIM") == "on")
        self.matte.setChecked(c.get("CFG_MATTE") == "on")
        self.skip.setChecked(c.get("CFG_SKIP", "on") != "off")
        for key, spin in (("CFG_FEATHER", self.feather), ("CFG_SHRINK", self.shrink)):
            try:
                spin.setValue(max(0, min(20, int(c.get(key, "0")))))
            except ValueError:
                pass
        bg = c.get("CFG_BG", "transparent")
        if bg in ("transparent", "white", "black", "green"):
            self.bg.setCurrentText(bg)
        elif re.fullmatch(r"#[0-9A-Fa-f]{6}", bg or ""):
            self._custom_hex = bg
            self.bg.setCurrentText("custom…")
        self._refresh_model_badges()

    def _save_settings(self):
        write_config(self.model.currentIndex() + 1, self.streams.value(),
                     self.alpha.isChecked(), self.trim.isChecked(), self._bg_value(),
                     self.skip.isChecked(), self.fmt.currentText(), self.quality.value(),
                     self.matte.isChecked(), self.feather.value(), self.shrink.value())

    def _refresh_model_badges(self):
        md = model_dir()
        for i, (name, desc, size) in enumerate(MODELS):
            cached = os.path.isfile(os.path.join(md, f"{name}.onnx"))
            tag = "  ✓ cached" if cached else f"  · downloads ~{size}"
            self.model.setItemText(i, f"{name}  ·  {desc}{tag}")

    # ---- source picking ----
    def _browse(self):
        start = self.parent_edit.text() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Choose the folder with your image folders", start)
        if d:
            self.parent_edit.setText(d)
            self._scan(d)

    def _browse_images(self):
        start = self.parent_edit.text() or os.path.expanduser("~")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Choose one or more images", start,
            "Images (*.jpg *.jpeg *.png *.webp);;All files (*)")
        if not files:
            return
        existing = {self.folders.item(i).data(Qt.UserRole) for i in range(self.folders.count())}
        added = 0
        for f in reversed(files):                 # insert at top, preserving pick order
            if f in existing or not os.path.isfile(f):
                continue
            it = QListWidgetItem(f"{os.path.basename(f)}   ·  single image")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)           # picked explicitly -> ticked, ready to run
            it.setData(Qt.UserRole, f)
            self.folders.insertItem(0, it)
            added += 1
        if added:
            self._preview_source(files[0], auto=True)   # show + auto-render the first
            self.status.setText(f"Added {added} image(s) — previewing the first. (Select + Del, or right-click, to remove.)")
        else:
            self.status.setText("Those image(s) are already in the list.")

    def _scan(self, parent):
        self.folders.clear()
        if not parent or not os.path.isdir(parent):
            self.status.setText("That folder doesn't exist.")
            return
        subs = list_subfolders(parent)
        own = count_images(parent, recurse=False)
        item = QListWidgetItem(f"▸ this folder itself   ({own} images)")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        item.setData(Qt.UserRole, parent)
        self.folders.addItem(item)
        for path, n in subs:
            it = QListWidgetItem(f"{os.path.basename(path)}   ({n} images)")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            it.setData(Qt.UserRole, path)
            self.folders.addItem(it)
        self.status.setText(f"{len(subs)} subfolder(s) found — tick the ones to process.")
        self._autopreview_first()

    def _check_all(self, on):
        st = Qt.Checked if on else Qt.Unchecked
        for i in range(self.folders.count()):
            self.folders.item(i).setCheckState(st)

    def _remove_source(self, item):
        self.folders.takeItem(self.folders.row(item))
        self._source_changed()

    def _remove_all_sources(self):
        self.folders.clear()
        self._source_changed()

    def _folders_menu(self, pos):
        item = self.folders.itemAt(pos)
        menu = QMenu(self)
        if item is not None:
            menu.addAction("Remove", lambda: self._remove_source(item))
        if self.folders.count():
            menu.addAction("Remove all", self._remove_all_sources)
        if menu.actions():
            menu.exec(self.folders.viewport().mapToGlobal(pos))

    def _source_changed(self):
        # after removing item(s): refresh the preview to match what's left
        self._preview_out = None
        self._preview_src = None
        if self.folders.count() == 0:
            self.preview.clear_preview()
            self.caption.setText("")
            self.status.setText("Pick folders or images to begin.")
        else:
            self._autopreview_first()

    def _checked_sources(self):
        out = []
        for i in range(self.folders.count()):
            it = self.folders.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out

    # ---- option widgets ----
    def _fmt_changed(self, fmt):
        is_lossy = fmt in LOSSY
        self.qlabel.setVisible(is_lossy)
        self.qrow.setVisible(is_lossy)
        if fmt in FLAT and self.bg.currentText() == "transparent":
            self.status.setText(f"{fmt} has no transparency — it'll composite onto white.")

    def _bg_changed(self, val):
        self.swatch.setVisible(val == "custom…")
        if val == "custom…":
            self._update_swatch()

    def _bg_value(self):
        v = self.bg.currentText()
        if v == "custom…":
            return self._custom_hex
        return v

    def _update_swatch(self):
        self.swatch.setStyleSheet(f"background:{self._custom_hex}; border:1px solid {BORDER};")

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._custom_hex), self, "Background colour")
        if c.isValid():
            self._custom_hex = c.name()
            self._update_swatch()
            self._invalidate_preview()

    def _toggle_log(self, on):
        self.log.setVisible(on)

    # ---- preview ----
    def _src_of(self, path):
        if path and os.path.isfile(path):
            return path
        if path and os.path.isdir(path):
            imgs = scan_folder(path, False)
            return imgs[0] if imgs else None
        return None

    def _preview_source(self, src, auto=False):
        self._preview_src = src
        self._preview_out = None
        self._apply_preview()              # show the original right away
        if auto:                           # render the cutout shortly (debounced)
            self._pv_timer.start(300)

    def _on_source_clicked(self, item):
        src = self._src_of(item.data(Qt.UserRole))
        if src:
            self._preview_source(src, auto=True)

    def _autopreview_first(self):
        """Show the first available source image (no auto-render — just browsing)."""
        if self._preview_out is not None:
            return                       # a result is already on display; leave it
        for i in range(self.folders.count()):
            src = self._src_of(self.folders.item(i).data(Qt.UserRole))
            if src:
                self._preview_source(src, auto=False)
                return

    def _show_result(self, out):
        self._preview_out = out
        self._preview_src = self._out_to_src.get(out)
        self._apply_preview()              # before/after split for this result

    def _apply_preview(self):
        have_out = self._preview_out and os.path.exists(self._preview_out)
        if self._preview_src and have_out:
            crop = _crop_bbox(self._preview_out) if self.trim.isChecked() else None
            self.preview.set_compare(self._preview_src, self._preview_out, crop)
            self.caption.setText("before ⇄ after · " + os.path.basename(self._preview_src))
        elif self._preview_src:
            self.preview.set_single(self._preview_src, checker=False)
            self.caption.setText(os.path.basename(self._preview_src))
        else:
            self.preview.clear_preview()
            self.caption.setText("")

    def _pv_key(self, src):
        # NB: trim is intentionally excluded — the preview never trims (see _render_preview)
        return (src, MODELS[self.model.currentIndex()][0], self._bg_value(),
                self.alpha.isChecked(), self.fmt.currentText(),
                self.matte.isChecked(), self.feather.value(), self.shrink.value())

    def _auto_render(self):
        """Debounce target: render the focused image's cutout so the split appears."""
        if self._preview_src and self._preview_out is None and self.proc is None and self.pvproc is None:
            self._render_preview()

    def _render_preview(self):
        """Render the focused image's cutout on demand (this one image, current settings),
        then show the before/after split. Cached per (image + settings)."""
        src = self._preview_src
        if not src:
            return
        key = self._pv_key(src)
        cached = self._pv_cache.get(key)
        if cached and os.path.exists(cached):
            self._preview_out = cached
            self._apply_preview()
            return
        if self.proc is not None or self.pvproc is not None:
            return
        fmt = self.fmt.currentText()
        pvfmt = fmt if fmt in PV_LOADABLE else "png"
        if not self._pv_dir or not os.path.isdir(self._pv_dir):
            self._pv_dir = tempfile.mkdtemp(prefix="bgone-pv-")   # owned by THIS user, 0700
        out = os.path.join(self._pv_dir, "pv_%08x.%s" % (abs(hash(key)) & 0xFFFFFFFF, pvfmt))
        self._pv_pending = (key, src, out)        # src lets us ignore stale renders
        self.caption.setText("rendering cutout…")
        self.status.setText("Rendering this image with your current settings…")
        bg = self._bg_value()
        if fmt in FLAT and bg == "transparent":
            bg = "white"
        env = QProcessEnvironment.systemEnvironment()
        env.insert("NBG_MODEL", MODELS[self.model.currentIndex()][0])
        env.insert("NBG_STREAMS", "1")
        env.insert("NBG_BG", bg)
        env.insert("NBG_FMT", pvfmt)
        env.insert("NBG_QUALITY", str(self.quality.value()))
        env.insert("NBG_ALPHA", "1" if self.alpha.isChecked() else "0")
        env.insert("NBG_TRIM", "0")   # never trim the preview — keeps the before/after split aligned
        env.insert("NBG_MATTE", "1" if self.matte.isChecked() else "0")
        env.insert("NBG_FEATHER", str(self.feather.value()))
        env.insert("NBG_SHRINK", str(self.shrink.value()))
        env.insert("U2NET_HOME", model_dir())
        worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bgone-worker.py")
        if not os.path.isfile(worker):
            worker = "/opt/bgone/bgone-worker.py"
        self.pvproc = QProcess(self)
        self.pvproc.setProcessEnvironment(env)
        self.pvproc.finished.connect(self._preview_done)
        self.pvproc.readyReadStandardError.connect(self._pv_stderr)
        self.pvproc.start(sys.executable, [worker])
        self.pvproc.write((src + "\0" + out + "\0").encode("utf-8", "surrogateescape"))
        self.pvproc.closeWriteChannel()

    def _pv_stderr(self):
        # the worker downloads an uncached model on first use (rembg prints "Downloading");
        # surface that so a long one-time download doesn't look like a hang or a failure.
        if self.pvproc is None:
            return
        txt = bytes(self.pvproc.readAllStandardError()).decode("utf-8", "replace")
        if "Downloading" in txt:
            self.status.setText("Downloading the model (one-time, up to ~900 MB for BiRefNet)… preview follows.")
            self.caption.setText("downloading model…")

    def _preview_done(self, *_):
        pend = self._pv_pending
        self._pv_pending = None
        self.pvproc = None
        if pend and os.path.exists(pend[2]):
            key, psrc, out = pend
            self._pv_cache[key] = out
            if psrc == self._preview_src:             # still the focused image -> show split
                self._preview_out = out
                self._apply_preview()
                self.status.setText("Drag the handle to compare before/after. Remove backgrounds to export.")
        else:
            self.status.setText("Couldn't render the preview — try again in a moment.")
        # the selection may have moved on while rendering; catch up to the current image
        if self._preview_src and self._preview_out is None and self.proc is None and self.pvproc is None \
                and self._pv_cache.get(self._pv_key(self._preview_src)) is None:
            self._pv_timer.start(150)

    def _invalidate_preview(self, *_):
        # a cutout-affecting setting changed: drop the stale result, show the source, and
        # re-render the cutout (debounced) so the split reflects the new settings.
        self._preview_out = None
        self._apply_preview()
        if self._preview_src and self.proc is None and self.pvproc is None:
            self._pv_timer.start(300)

    # ---- run ----
    def _run(self):
        if self.proc is not None:
            return
        srcs = self._checked_sources()
        if not srcs:
            self.status.setText("Tick at least one folder or image first.")
            return
        fmt = self.fmt.currentText()
        bg = self._bg_value()
        if fmt in FLAT and bg == "transparent":
            bg = "white"
        # folders are scanned (recurse-aware); loose images are grouped by their parent
        # dir so each lands in that dir's sibling `<name>_bgone` — same as folder mode.
        jobs = [(d, scan_folder(d, self.recurse.isChecked()))
                for d in srcs if os.path.isdir(d)]
        loose = {}
        for f in (p for p in srcs if os.path.isfile(p)):
            loose.setdefault(os.path.dirname(f), []).append(f)
        jobs += list(loose.items())
        pairs, outs, found, skipped = build_pairs(jobs, fmt, self.skip.isChecked())
        if found == 0:
            self.status.setText("No jpg/jpeg/png/webp images in the selected folder(s).")
            return
        if not pairs:
            self.status.setText(f"Nothing to do — all {found} image(s) already have outputs.")
            return
        self._save_settings()

        self._total = len(pairs) // 2
        self._done = 0
        self._pending = list(outs)
        self._out_to_src = {pairs[i + 1]: pairs[i] for i in range(0, len(pairs), 2)}
        self._out_dirs = sorted({os.path.dirname(o) for o in outs})
        self._clear_strip()
        self.strip_area.show()
        self.log.clear()
        self.open_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Working…")
        self.bar.show()
        self.bar.setRange(0, 0)   # indeterminate until the model loads + first result
        self.status.setText(f"Loading model… ({self._total} image(s) queued)")

        worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bgone-worker.py")
        if not os.path.isfile(worker):
            worker = "/opt/bgone/bgone-worker.py"
        nproc = os.cpu_count() or 4
        streams = self.streams.value()
        env = QProcessEnvironment.systemEnvironment()
        env.insert("NBG_MODEL", MODELS[self.model.currentIndex()][0])
        env.insert("NBG_STREAMS", str(streams))
        env.insert("NBG_BG", bg)
        env.insert("NBG_FMT", fmt)
        env.insert("NBG_QUALITY", str(self.quality.value()))
        env.insert("NBG_ALPHA", "1" if self.alpha.isChecked() else "0")
        env.insert("NBG_TRIM", "1" if self.trim.isChecked() else "0")
        env.insert("NBG_MATTE", "1" if self.matte.isChecked() else "0")
        env.insert("NBG_FEATHER", str(self.feather.value()))
        env.insert("NBG_SHRINK", str(self.shrink.value()))
        env.insert("OMP_NUM_THREADS", str(max(1, nproc // streams)))
        env.insert("U2NET_HOME", model_dir())

        self.proc = QProcess(self)
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QProcess.SeparateChannels)
        self.proc.readyReadStandardOutput.connect(self._on_stdout)
        self.proc.readyReadStandardError.connect(self._on_stderr)
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_proc_error)
        self._obuf = b""
        self._errbuf = ""
        self._t0 = time.monotonic()
        self.proc.start(sys.executable, [worker])
        blob = b"".join(p.encode("utf-8", "surrogateescape") + b"\0" for p in pairs)
        self.proc.write(blob)
        self.proc.closeWriteChannel()

    def _on_stdout(self):
        self._obuf += bytes(self.proc.readAllStandardOutput())
        *lines, self._obuf = self._obuf.split(b"\n")
        if not lines:
            return
        if self.bar.maximum() == 0:                 # leave the indeterminate state
            self.bar.setRange(0, self._total)
        for _ in lines:
            self._done += 1
        self.bar.setValue(self._done)
        el = max(1e-3, time.monotonic() - self._t0)
        rate = self._done / el
        rem = self._total - self._done
        eta = int(rem / rate) if rate > 0 else 0
        self.status.setText(f"{self._done}/{self._total}  ·  {rate:.1f}/s  ·  ~{eta}s left")
        self._drain_thumbs()

    def _drain_thumbs(self):
        # show newly-written outputs (decoupled from worker ordering)
        still = []
        added = 0
        for path in self._pending:
            if added < 8 and os.path.exists(path):
                pm = thumb_pixmap(path)
                if pm is not None:
                    self._add_thumb(pm, path)
                    added += 1
                    continue
                # unpreviewable (exr/hdr/dpx) -> drop silently, count as handled
                continue
            still.append(path)
        self._pending = still

    def _add_thumb(self, pm, out):
        lbl = ClickableLabel(self._show_result, out)
        lbl.setPixmap(pm)
        lbl.setFixedSize(THUMB, THUMB)
        lbl.setToolTip(os.path.basename(out))
        self.strip.insertWidget(self.strip.count() - 1, lbl)   # before the trailing stretch
        self._thumbs.append(lbl)
        if len(self._thumbs) > MAX_THUMBS:
            old = self._thumbs.pop(0)
            self.strip.removeWidget(old)
            old.deleteLater()
        self._show_result(out)        # the preview follows the latest result
        QTimer.singleShot(0, lambda: self.strip_area.horizontalScrollBar().setValue(
            self.strip_area.horizontalScrollBar().maximum()))

    def _clear_strip(self):
        for w in self._thumbs:
            self.strip.removeWidget(w)
            w.deleteLater()
        self._thumbs = []

    def _on_stderr(self):
        self._errbuf += bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")
        for line in self._errbuf.splitlines():
            if line.startswith("bgone: execution provider"):
                self.provider_lbl.setText(line.split("=", 1)[-1].strip())
            if "Downloading" in line and self.bar.maximum() == 0:
                self.status.setText("Downloading model… (first use)")
            if line.startswith("ERR ") or line.startswith("bgone:"):
                self.log.appendPlainText(line)

    def _on_proc_error(self, _err):
        self.status.setText("Failed to start the worker — is bgone installed?")
        self.log.appendPlainText(self.proc.errorString() if self.proc else "process error")

    def _on_finished(self, _code, _status):
        self._drain_thumbs()
        if self.bar.maximum() == 0:
            self.bar.setRange(0, self._total or 1)
        self.bar.setValue(self._total)
        ok, fail = self._total, 0
        m = re.findall(r"__DONE__ (\d+) (\d+)", self._errbuf)
        if m:
            ok, fail = int(m[-1][0]), int(m[-1][1])
        el = int(time.monotonic() - self._t0)
        msg = f"✓ Done — {ok} ok"
        if fail:
            msg += f"  ·  {fail} failed"
            self.details_btn.setChecked(True)
        msg += f"  ·  {len(self._out_dirs)} folder(s)  ·  {el}s"
        self.status.setText(msg)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Remove backgrounds")
        self.open_btn.setEnabled(bool(self._out_dirs))
        self._refresh_model_badges()
        self.bar.hide()
        self.proc = None

    def _open_out(self):
        if self._out_dirs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._out_dirs[0]))


def _demo_state(win, results=False):
    """Populate the window with sample content for an off-screen screenshot."""
    d = "/tmp/bgtest"
    if os.path.isdir(d):
        win.parent_edit.setText(d)
        win._scan(d)                     # auto-previews the first source image (before state)
    if results:
        out = "/tmp/bgtest/in/in_bgone/img_0001.png"
        src = "/tmp/bgtest/in/img_0001.png"
        if os.path.exists(out):
            win.strip_area.show()
            win._out_to_src[out] = src if os.path.exists(src) else None
            pm = thumb_pixmap(out)
            if pm:
                for _ in range(6):
                    win._add_thumb(pm, out)


def _apply_theme(app):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG0))
    pal.setColor(QPalette.Base, QColor(BG2))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(BG2))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipBase, QColor(BG1))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor(MUTED))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    app.setApplicationName("bgone")


def main():
    args = sys.argv[1:]
    selftest = "--selftest" in args
    if "--shot" in args:
        i = args.index("--shot")
        shot = args[i + 1] if i + 1 < len(args) else "/tmp/bgone-shot.png"
        app = QApplication(sys.argv)
        _apply_theme(app)
        win = Bgone()
        win.resize(1200, 920)
        win.show()

        res = "--results" in args
        do_after = "--after" in args

        def _grab():
            for _ in range(4):
                app.processEvents()
            win.grab().save(shot)
            app.quit()

        def _cap():
            try:
                _demo_state(win, results=res)
            except Exception as e:
                print("demo err:", e)
            if do_after and win._preview_src:
                win._render_preview()          # render the cutout on demand, then grab
                if win.pvproc is not None:
                    win.pvproc.finished.connect(lambda *_: QTimer.singleShot(250, _grab))
                else:
                    _grab()
            else:
                _grab()
        QTimer.singleShot(200, _cap)
        return app.exec()
    app = QApplication(sys.argv)
    _apply_theme(app)
    icon_path = "/usr/share/icons/hicolor/256x256/apps/bgone.png"
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = Bgone()
    win.resize(1200, 820)
    win.show()

    # debug hook: `kill -USR1 <pid>` saves a screenshot of the live window
    _grab = {"req": False}
    try:
        signal.signal(signal.SIGUSR1, lambda *a: _grab.__setitem__("req", True))
        _ka = QTimer(win)
        _ka.setInterval(250)
        _ka.timeout.connect(lambda: _grab["req"] and (_grab.__setitem__("req", False),
                                                      win.grab().save("/tmp/bgone-live.png")))
        _ka.start()
    except Exception:
        pass

    if selftest:
        rest = [a for a in args if a != "--selftest"]
        if rest and os.path.isdir(rest[0]):
            # headless end-to-end: drive a real job and quit when the worker finishes
            win.parent_edit.setText(rest[0])
            win._scan(rest[0])
            win.folders.item(0).setCheckState(Qt.Checked)   # "this folder itself"
            def _go():
                win._run()
                if win.proc is not None:
                    win.proc.finished.connect(lambda *_: app.quit())
                else:
                    app.quit()
            QTimer.singleShot(50, _go)
            return app.exec()
        QTimer.singleShot(150, app.quit)
        return app.exec()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""bgone-worker — load the rembg model ONCE, process NUL-delimited (input,output)
PAIRS from stdin concurrently via a thread pool. Prints each finished basename to
stdout (so the bar advances); failures go to stderr as 'ERR <name>: <msg>'. A
final '__DONE__ <ok> <fail>' line is printed to stderr for the summary.

Env:
  NBG_MODEL    rembg model name                       [isnet-anime]
  NBG_ALPHA    "1" enable alpha matting                [0]
  NBG_STREAMS  images processed at once (threads)      [4]
  NBG_TRIM     "1" crop to the subject's bounding box  [0]
  NBG_BG       transparent | white | black | #RRGGBB   [transparent]
"""
import os
import sys
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
from rembg import remove, new_session

MODEL   = os.environ.get("NBG_MODEL", "isnet-anime")
ALPHA   = os.environ.get("NBG_ALPHA", "0") == "1"
WORKERS = max(1, int(os.environ.get("NBG_STREAMS", "4")))
TRIM    = os.environ.get("NBG_TRIM", "0") == "1"
BG      = os.environ.get("NBG_BG", "transparent").strip().lower()


def _bg_rgba():
    if BG in ("", "transparent", "none"):
        return None
    if BG == "white":
        return (255, 255, 255, 255)
    if BG == "black":
        return (0, 0, 0, 255)
    if len(BG) == 7 and BG[0] == "#":
        try:
            return (int(BG[1:3], 16), int(BG[3:5], 16), int(BG[5:7], 16), 255)
        except ValueError:
            return None
    return None


BGRGBA = _bg_rgba()


def _make_session():
    # GPU-ready: prefer a hardware execution provider if onnxruntime exposes one
    # (CUDA/ROCm/OpenVINO/DirectML), else fall back to CPU. No-op on CPU-only boxes.
    requested, sess = None, None
    try:
        import onnxruntime as ort
        avail = ort.get_available_providers()
        prefer = [p for p in ("CUDAExecutionProvider", "ROCMExecutionProvider",
                              "OpenVINOExecutionProvider", "DmlExecutionProvider")
                  if p in avail]
        requested = prefer[0] if prefer else "CPUExecutionProvider"
        try:
            sess = new_session(MODEL, providers=prefer + ["CPUExecutionProvider"])
        except TypeError:
            sess = new_session(MODEL)
    except Exception as e:
        print("bgone: provider detection error (%s); using default" % e, file=sys.stderr, flush=True)
    if sess is None:
        sess = new_session(MODEL)
    # report the actually-active provider so fleet operators can confirm GPU vs CPU
    active = requested or "CPUExecutionProvider"
    try:
        active = sess.inner_session.get_providers()[0]
    except Exception:
        pass
    print("bgone: execution provider = %s" % active, file=sys.stderr, flush=True)
    return sess


session = _make_session()


def process(pair):
    src, dst = pair
    with open(src, "rb") as fh:
        data = fh.read()
    out = remove(data, session=session, alpha_matting=ALPHA)
    if TRIM or BGRGBA is not None:
        im = Image.open(BytesIO(out)).convert("RGBA")
        if TRIM:
            bbox = im.getchannel("A").getbbox()   # tight box around non-transparent pixels
            if bbox:
                im = im.crop(bbox)
        if BGRGBA is not None:
            canvas = Image.new("RGBA", im.size, BGRGBA)
            canvas.alpha_composite(im)
            im = canvas.convert("RGB")            # flatten onto solid bg
        buf = BytesIO()
        im.save(buf, "PNG")
        out = buf.getvalue()
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "wb") as fh:
        fh.write(out)
    return os.path.splitext(os.path.basename(src))[0]


def main():
    toks = [p.decode("utf-8", "surrogateescape")
            for p in sys.stdin.buffer.read().split(b"\0") if p]
    if len(toks) % 2:
        print(f"ERR (worker): odd token count {len(toks)} — last path dropped",
              file=sys.stderr, flush=True)
    pairs = list(zip(toks[0::2], toks[1::2]))
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(process, pr): pr for pr in pairs}
        for fut in as_completed(futs):
            name = os.path.splitext(os.path.basename(futs[fut][0]))[0]
            try:
                name = fut.result()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"ERR {name}: {e}", file=sys.stderr, flush=True)
            print(name, flush=True)
    print(f"__DONE__ {ok} {fail}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()

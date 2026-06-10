#!/usr/bin/env python3
"""
PhotoConverter – Web UI
One unified tool: colour-correct + optional resize for any image format.
HIF/HEIF/HEIC: HDR tone-mapping applied automatically.
Other formats: ICC profile converted to sRGB.

Platforms: Windows, macOS, Linux
Run:  python image_resizer.py  →  http://localhost:5000
"""

import base64
import io as _io
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

try:
    from flask import Flask, jsonify, render_template, request, send_from_directory
    from PIL import Image, ImageOps, UnidentifiedImageError
    import pillow_heif
except ImportError:
    print("Missing packages. Run: pip install flask pillow pillow-heif numpy")
    sys.exit(1)

pillow_heif.register_heif_opener()

from convert_hif_to_jpg import (
    _hdr_pq_to_srgb, _icc_to_srgb, _auto_levels,
    _apply_style, _is_pq_hdr, _STYLES,
    SUPPORTED_EXTENSIONS as _HIF_EXT,
)

__version__ = "2.0.0"

app = Flask(__name__)

# ── Supported formats ────────────────────────────────────────────────────────
SUPPORTED_INPUT = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".bmp", ".tiff", ".tif", ".gif",
} | _HIF_EXT

FORMAT_EXT = {"same": None, "jpg": ".jpg", "png": ".png", "webp": ".webp"}

# ── Job state ────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_job: dict = dict(running=False, total=0, done=0,
                   current="", results=[], cancelled=False, error=None)

# ── Preview cache (path → data-URL JPEG, survives for the server session) ────
_preview_cache: dict = {}


def _snapshot():
    with _lock:
        j = dict(_job)
        j["results"] = list(_job["results"])
    return j


# ── Cross-platform folder browser ────────────────────────────────────────────
def _browse_folder() -> str:
    # Write the path as raw UTF-8 bytes to stdout.buffer so it survives any
    # system code-page (e.g. cp950 / cp1252 can't encode Chinese characters).
    script = (
        "import sys, tkinter as tk; from tkinter import filedialog; "
        "root=tk.Tk(); root.withdraw(); root.attributes('-topmost',True); "
        "path=filedialog.askdirectory(title='Select Folder'); "
        "root.destroy(); "
        "sys.stdout.buffer.write((path or '').encode('utf-8'))"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, timeout=120,   # capture_output=True, no text=True → raw bytes
        )
        return r.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


# ── Validation helpers ────────────────────────────────────────────────────────
_MAX_DIM = 32000


def _safe_int(v, name, lo=1, hi=_MAX_DIM):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be an integer (got {v!r})")
    if not lo <= n <= hi:
        raise ValueError(f"'{name}' must be {lo}–{hi} (got {n})")
    return n


def _safe_path(raw, must_exist=False):
    p = Path(raw).resolve()
    if must_exist and not p.exists():
        raise ValueError(f"Path does not exist: {p}")
    return p


# ── Unified processing pipeline ───────────────────────────────────────────────
def _out_ext(src: Path, fmt: str) -> str:
    if fmt == "same":
        ext = src.suffix.lower()
        return ".jpg" if ext in _HIF_EXT else ext
    return FORMAT_EXT[fmt]


def _process_file(src: Path, dst_base: Path, params: dict) -> None:
    """
    One function handles everything:
      1. Open  (any format, HIF via pillow-heif)
      2. Colour correct  (HIF → HDR pipeline; others → ICC→sRGB)
      3. Style  (contrast / saturation)
      4. Resize  (optional)
      5. Save
    """
    # ── 1. Open & colour-correct ──────────────────────────────────────────────
    if src.suffix.lower() in _HIF_EXT:
        heif_file = pillow_heif.read_heif(str(src))
        heif_img  = heif_file[0]
        nclx      = heif_img.info.get("nclx_profile")
        img       = heif_img.to_pillow()
        img       = _hdr_pq_to_srgb(img) if _is_pq_hdr(nclx) else _auto_levels(_icc_to_srgb(img))
    else:
        try:
            img = Image.open(src)
        except UnidentifiedImageError:
            raise ValueError(f"Unrecognised image: {src.name}")
        img = _icc_to_srgb(img)

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # ── 2. Style ──────────────────────────────────────────────────────────────
    style    = params.get("style", "accurate")
    contrast, saturation = _STYLES.get(style, (1.0, 1.0))
    # Allow per-job fine-tuning overrides (from the web UI sliders)
    if "contrast"   in params:
        contrast   = max(0.01, min(10.0, float(params["contrast"])))
    if "saturation" in params:
        saturation = max(0.01, min(10.0, float(params["saturation"])))
    img = _apply_style(img, contrast, saturation)

    # ── 3. Resize (optional) ──────────────────────────────────────────────────
    rp = params.get("resize")   # None = no resize
    if rp:
        mode = rp.get("mode", "width")
        ow, oh = img.size
        if ow <= 0 or oh <= 0:
            raise ValueError(f"Invalid source dimensions: {ow}×{oh}")

        if mode == "width":
            w = _safe_int(rp["target_w"], "width")
            img = img.resize((w, max(1, round(oh * w / ow))), Image.LANCZOS)
        elif mode == "height":
            h = _safe_int(rp["target_h"], "height")
            img = img.resize((max(1, round(ow * h / oh)), h), Image.LANCZOS)
        elif mode == "percent":
            p = max(0.01, float(rp.get("percent", 50))) / 100
            img = img.resize((max(1, round(ow * p)), max(1, round(oh * p))), Image.LANCZOS)
        elif mode == "exact":
            tw  = _safe_int(rp["target_w"], "width")
            th  = _safe_int(rp["target_h"], "height")
            fit = rp.get("fit", "contain")
            if fit == "stretch":
                img = img.resize((tw, th), Image.LANCZOS)
            elif fit == "cover":
                img = ImageOps.fit(img, (tw, th), Image.LANCZOS)
            else:
                img.thumbnail((tw, th), Image.LANCZOS)

    # ── 4. Save ───────────────────────────────────────────────────────────────
    ext     = _out_ext(src, params.get("fmt", "jpg"))
    dst     = dst_base.with_suffix(ext)
    out_fmt = ext.lstrip(".").upper()
    if out_fmt == "JPG":
        out_fmt = "JPEG"
    if out_fmt in ("JPEG", "WEBP") and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif out_fmt == "PNG" and img.mode == "P":
        img = img.convert("RGBA")

    quality = _safe_int(params.get("quality", 90), "quality", lo=1, hi=95)
    kw = ({"quality": quality, "subsampling": 0} if out_fmt == "JPEG"
          else {"quality": quality}               if out_fmt == "WEBP"
          else {})

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, format=out_fmt, **kw)


# ── Background worker ─────────────────────────────────────────────────────────
def _worker(input_dir: Path, output_dir: Path,
            params: dict, files: list[Path]) -> None:
    global _job
    overwrite = params.get("overwrite", False)

    for i, src in enumerate(files):
        with _lock:
            if _job["cancelled"]:
                break
            _job["done"]    = i
            _job["current"] = src.name

        rel      = src.relative_to(input_dir)
        dst_base = output_dir / rel.parent / rel.stem

        try:
            ext   = _out_ext(src, params.get("fmt", "jpg"))
            final = dst_base.with_suffix(ext)
            if final.exists() and not overwrite:
                with _lock:
                    _job["results"].append({"name": src.name, "status": "skipped"})
                continue

            _process_file(src, dst_base, params)
            with _lock:
                _job["results"].append({"name": src.name, "status": "ok"})
        except Exception as exc:
            with _lock:
                _job["results"].append({"name": src.name, "status": "error",
                                         "msg": type(exc).__name__})

    with _lock:
        _job["done"]    = len(files)
        _job["current"] = ""
        _job["running"] = False


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/browse", methods=["POST"])
def browse():
    try:
        path = _browse_folder()
        return jsonify({"ok": bool(path), "path": path})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/api/scan", methods=["POST"])
def scan():
    data    = request.json or {}
    recurse = data.get("recurse", False)
    try:
        folder = _safe_path(data.get("folder", ""), must_exist=True)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)})

    pattern   = "**/*" if recurse else "*"
    files     = [f for f in folder.glob(pattern)
                 if f.is_file() and f.suffix.lower() in SUPPORTED_INPUT]
    hif_files = [f for f in files if f.suffix.lower() in _HIF_EXT]
    hif_count = len(hif_files)
    preview   = [f.name for f in files[:5]]

    # Return up to 20 HIF relative paths for the preview selector in the UI
    _MAX_HIF_SEL = 20
    hif_rel = [str(f.relative_to(folder)).replace("\\", "/")
               for f in hif_files[:_MAX_HIF_SEL]]

    return jsonify({
        "ok":       True,
        "count":    len(files),
        "hif_count": hif_count,
        "preview":  preview,
        "extra":    max(0, len(files) - 5),
        "hif_files": hif_rel,
        "hif_extra": max(0, hif_count - _MAX_HIF_SEL),
    })


@app.route("/api/preview", methods=["POST"])
def preview_image():
    """
    Process a single image through the colour-correction pipeline
    (HDR tone-map for HIF, ICC→sRGB for others) and return it as a
    base64-encoded JPEG data-URL — no style applied, so the browser
    can layer CSS filter on top for live fine-tuning preview.

    Results are cached for the lifetime of the server session so that
    switching between files is instant after the first load.
    """
    data = request.json or {}
    try:
        src = _safe_path(data.get("file", ""), must_exist=True)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)})

    if src.suffix.lower() not in SUPPORTED_INPUT:
        return jsonify({"ok": False, "error": f"Unsupported format: {src.suffix}"})

    cache_key = str(src)
    if cache_key in _preview_cache:
        return jsonify({"ok": True, "data": _preview_cache[cache_key], "cached": True})

    try:
        # ── Colour-correct (identical to _process_file step 1) ──────────────
        if src.suffix.lower() in _HIF_EXT:
            heif_file = pillow_heif.read_heif(str(src))
            heif_img  = heif_file[0]
            nclx      = heif_img.info.get("nclx_profile")
            img       = heif_img.to_pillow()
            img       = _hdr_pq_to_srgb(img) if _is_pq_hdr(nclx) else _auto_levels(_icc_to_srgb(img))
        else:
            img = Image.open(src)
            img = _icc_to_srgb(img)

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # ── Downscale for preview (max 1200 px on the long side) ────────────
        w, h   = img.size
        max_px = 1200
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img   = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                               Image.LANCZOS)

        # ── Encode as base64 JPEG data-URL ───────────────────────────────────
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=85, subsampling=0)
        data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        _preview_cache[cache_key] = data_url
        return jsonify({"ok": True, "data": data_url})

    except Exception as exc:
        return jsonify({"ok": False, "error": type(exc).__name__})


@app.route("/api/convert", methods=["POST"])
def start_convert():
    global _job
    with _lock:
        if _job["running"]:
            return jsonify({"ok": False, "error": "A job is already running"})

    data    = request.json or {}
    params  = data.get("params", {})
    recurse = data.get("recurse", False)

    try:
        input_dir  = _safe_path(data.get("input_folder", ""), must_exist=True)
        output_dir = _safe_path(data.get("output_folder", ""))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)})

    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = "**/*" if recurse else "*"
    files   = [f for f in input_dir.glob(pattern)
               if f.is_file() and f.suffix.lower() in SUPPORTED_INPUT]

    if not files:
        return jsonify({"ok": False, "error": "No supported images found"})

    with _lock:
        _job = dict(running=True, total=len(files), done=0,
                    current="", results=[], cancelled=False, error=None)

    threading.Thread(
        target=_worker, args=(input_dir, output_dir, params, files), daemon=True
    ).start()

    return jsonify({"ok": True, "total": len(files)})


@app.route("/api/status")
def status():
    return jsonify(_snapshot())


@app.route("/api/cancel", methods=["POST"])
def cancel():
    with _lock:
        _job["cancelled"] = True
    return jsonify({"ok": True})


@app.route("/api/styles")
def styles():
    return jsonify({
        "ok": True,
        "styles": [{"id": k, "contrast": v[0], "saturation": v[1]}
                   for k, v in _STYLES.items()]
    })


@app.route("/samples/<path:filename>")
def samples(filename):
    return send_from_directory("static/samples", filename)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    url = "http://localhost:5000"
    print("=" * 42)
    print("  PhotoConverter  v" + __version__)
    print(f"  {url}")
    print("  Browser opening automatically…")
    print("  Close this window to stop the server")
    print("=" * 42)
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(debug=False, port=5000, threaded=True)

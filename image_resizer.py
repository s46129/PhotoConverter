#!/usr/bin/env python3
"""
Image Batch Resizer – Web UI
Supports: JPG, PNG, WEBP, BMP, TIFF, GIF, HEIF/HEIC/HIF
Platforms: Windows, macOS, Linux

Run:  python image_resizer.py
Then open:  http://localhost:5000
"""

import threading
import subprocess
import webbrowser
import sys
from pathlib import Path

try:
    from flask import Flask, jsonify, render_template, request, send_from_directory
    from PIL import Image, ImageOps, UnidentifiedImageError
    import pillow_heif
except ImportError:
    print("Missing packages. Run: pip install flask pillow pillow-heif")
    sys.exit(1)

pillow_heif.register_heif_opener()

# Import HIF converter pipeline
try:
    from convert_hif_to_jpg import (
        _hdr_pq_to_srgb, _icc_to_srgb, _auto_levels,
        _apply_style, _is_pq_hdr, _STYLES,
        SUPPORTED_EXTENSIONS as HIF_EXTENSIONS,
    )
    _HIF_AVAILABLE = True
except ImportError:
    _HIF_AVAILABLE = False

__version__ = "1.2.0"

app = Flask(__name__)

# ── Supported input formats ──────────────────────────────────────────────────
SUPPORTED_INPUT = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".bmp", ".tiff", ".tif", ".gif",
    ".hif", ".heif", ".heic",
}

FORMAT_EXT = {"same": None, "jpg": ".jpg", "png": ".png", "webp": ".webp"}

# ── Global job state ─────────────────────────────────────────────────────────
_lock = threading.Lock()
_job: dict = dict(
    running=False, total=0, done=0,
    current="", results=[], cancelled=False, error=None,
)


def _snapshot():
    with _lock:
        j = dict(_job)
        j["results"] = list(_job["results"])
    return j


# ── Cross-platform folder browser (tkinter subprocess) ───────────────────────
def _browse_folder() -> str:
    """
    Open a native folder-picker dialog.
    Runs tkinter in a subprocess so it is safe to call from Flask worker threads.
    Works on Windows, macOS, and Linux (requires tkinter, which ships with Python).
    """
    script = (
        "import tkinter as tk; from tkinter import filedialog; "
        "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True); "
        "path = filedialog.askdirectory(title='Select Folder'); "
        "root.destroy(); print(path or '', end='')"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        return r.stdout.strip()
    except Exception:
        return ""


# ── Input validation ─────────────────────────────────────────────────────────
_MAX_DIMENSION = 32000   # pixels – guards against memory-bomb inputs
_MAX_PERCENT   = 500


def _safe_int(value, name: str, lo: int = 1, hi: int = _MAX_DIMENSION) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be an integer (got {value!r})")
    if not lo <= v <= hi:
        raise ValueError(f"'{name}' must be between {lo} and {hi} (got {v})")
    return v


def _safe_float(value, name: str, lo: float = 0.1, hi: float = _MAX_PERCENT) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a number (got {value!r})")
    if not lo <= v <= hi:
        raise ValueError(f"'{name}' must be between {lo} and {hi} (got {v})")
    return v


def _safe_path(raw: str, must_exist: bool = False) -> Path:
    """Resolve and validate a user-supplied path (prevents path traversal)."""
    p = Path(raw).resolve()
    if must_exist and not p.exists():
        raise ValueError(f"Path does not exist: {p}")
    return p


# ── Core resize logic ─────────────────────────────────────────────────────────
def _compute_new_size(orig_w: int, orig_h: int, params: dict) -> tuple[int, int] | None:
    """Return (new_w, new_h) or None (when thumbnail/fit handles it)."""
    if orig_w <= 0 or orig_h <= 0:
        raise ValueError(f"Invalid source dimensions: {orig_w}×{orig_h}")
    mode = params["mode"]
    if mode == "width":
        w = _safe_int(params["target_w"], "width")
        return (w, max(1, round(orig_h * w / orig_w)))
    if mode == "height":
        h = _safe_int(params["target_h"], "height")
        return (max(1, round(orig_w * h / orig_h)), h)
    if mode == "percent":
        p = _safe_float(params["percent"], "percent") / 100
        return (max(1, round(orig_w * p)), max(1, round(orig_h * p)))
    if mode == "exact":
        return None   # handled inline in _resize_one
    raise ValueError(f"Unknown resize mode: {mode!r}")


def _out_ext(src: Path, fmt: str) -> str:
    if fmt == "same":
        ext = src.suffix.lower()
        return ".jpg" if ext in {".hif", ".heif", ".heic"} else ext
    return FORMAT_EXT[fmt]


def _resize_one(src: Path, dst_base: Path, params: dict) -> None:
    ext     = _out_ext(src, params["fmt"])
    dst     = dst_base.with_suffix(ext)
    quality = _safe_int(params.get("quality", 90), "quality", lo=1, hi=95)
    mode    = params["mode"]

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = Image.open(src)
    except UnidentifiedImageError:
        raise ValueError(f"Unrecognised image format: {src.name}")

    if mode == "exact":
        tw       = _safe_int(params["target_w"], "width")
        th       = _safe_int(params["target_h"], "height")
        fit_mode = params.get("fit", "contain")
        if fit_mode == "stretch":
            img = img.resize((tw, th), Image.LANCZOS)
        elif fit_mode == "cover":
            img = ImageOps.fit(img, (tw, th), Image.LANCZOS)
        else:                          # contain / letterbox
            img.thumbnail((tw, th), Image.LANCZOS)
    else:
        new_size = _compute_new_size(*img.size, params)
        img = img.resize(new_size, Image.LANCZOS)

    out_fmt = ext.lstrip(".").upper()
    if out_fmt == "JPG":
        out_fmt = "JPEG"

    if out_fmt in ("JPEG", "WEBP") and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif out_fmt == "PNG" and img.mode == "P":
        img = img.convert("RGBA")

    kw: dict = {}
    if out_fmt == "JPEG":
        kw = {"quality": quality, "subsampling": 0}
    elif out_fmt == "WEBP":
        kw = {"quality": quality}

    img.save(dst, format=out_fmt, **kw)


# ── Background worker ────────────────────────────────────────────────────────
def _worker(input_dir: Path, output_dir: Path, params: dict, files: list[Path]) -> None:
    global _job
    for i, src in enumerate(files):
        with _lock:
            if _job["cancelled"]:
                break
            _job["done"]    = i
            _job["current"] = src.name

        rel      = src.relative_to(input_dir)
        dst_base = output_dir / rel.parent / rel.stem

        try:
            ext       = _out_ext(src, params["fmt"])
            dst_final = dst_base.with_suffix(ext)

            if dst_final.exists() and not params.get("overwrite"):
                with _lock:
                    _job["results"].append({"name": src.name, "status": "skipped"})
                continue

            _resize_one(src, dst_base, params)
            with _lock:
                _job["results"].append({"name": src.name, "status": "ok"})
        except Exception as exc:
            with _lock:
                _job["results"].append({"name": src.name, "status": "error", "msg": str(exc)})

    with _lock:
        _job["done"]    = len(files)
        _job["current"] = ""
        _job["running"] = False


# ── Flask routes ─────────────────────────────────────────────────────────────
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
    folder  = Path(data.get("folder", ""))
    recurse = data.get("recurse", False)
    if not folder.is_dir():
        return jsonify({"ok": False, "error": "Folder not found"})
    pattern = "**/*" if recurse else "*"
    files   = [f for f in folder.glob(pattern)
               if f.is_file() and f.suffix.lower() in SUPPORTED_INPUT]
    preview = [f.name for f in files[:5]]
    extra   = max(0, len(files) - 5)
    return jsonify({"ok": True, "count": len(files), "preview": preview, "extra": extra})


@app.route("/api/resize", methods=["POST"])
def start_resize():
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

    if not input_dir.is_dir():
        return jsonify({"ok": False, "error": "Input folder not found"})

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
        target=_worker,
        args=(input_dir, output_dir, params, files),
        daemon=True,
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


# ════════════════════════════════════════════════════════════════════════════
#  HIF Converter routes
# ════════════════════════════════════════════════════════════════════════════

_hif_lock = threading.Lock()
_hif_job: dict = dict(running=False, total=0, done=0,
                       current="", results=[], cancelled=False, error=None)


def _hif_snapshot():
    with _hif_lock:
        j = dict(_hif_job)
        j["results"] = list(_hif_job["results"])
    return j


def _hif_convert_one(src: Path, dst: Path, style: str, quality: int) -> None:
    heif_file = pillow_heif.read_heif(str(src))
    heif_img  = heif_file[0]
    nclx      = heif_img.info.get("nclx_profile")
    image     = heif_img.to_pillow()

    if _is_pq_hdr(nclx):
        image = _hdr_pq_to_srgb(image)
    else:
        image = _icc_to_srgb(image)
        image = _auto_levels(image)

    contrast, saturation = _STYLES[style]
    image = _apply_style(image, contrast, saturation)

    if image.mode != "RGB":
        image = image.convert("RGB")

    dst.parent.mkdir(parents=True, exist_ok=True)
    image.save(dst, format="JPEG", quality=quality, subsampling=0)


def _hif_worker(input_dir: Path, output_dir: Path,
                style: str, quality: int, files: list[Path]) -> None:
    global _hif_job
    for i, src in enumerate(files):
        with _hif_lock:
            if _hif_job["cancelled"]:
                break
            _hif_job["done"]    = i
            _hif_job["current"] = src.name

        rel = src.relative_to(input_dir)
        dst = output_dir / rel.with_suffix(".jpg")

        try:
            if dst.exists() and not _hif_job.get("overwrite"):
                with _hif_lock:
                    _hif_job["results"].append({"name": src.name, "status": "skipped"})
                continue
            _hif_convert_one(src, dst, style, quality)
            with _hif_lock:
                _hif_job["results"].append({"name": src.name, "status": "ok"})
        except Exception as exc:
            with _hif_lock:
                _hif_job["results"].append({"name": src.name, "status": "error",
                                             "msg": type(exc).__name__})

    with _hif_lock:
        _hif_job["done"]    = len(files)
        _hif_job["current"] = ""
        _hif_job["running"] = False


@app.route("/api/hif/styles")
def hif_styles():
    styles = [{"id": k, "contrast": v[0], "saturation": v[1]}
              for k, v in _STYLES.items()]
    return jsonify({"ok": True, "styles": styles,
                    "available": _HIF_AVAILABLE})


@app.route("/api/hif/scan", methods=["POST"])
def hif_scan():
    data    = request.json or {}
    folder  = Path(data.get("folder", ""))
    recurse = data.get("recurse", False)
    if not folder.is_dir():
        return jsonify({"ok": False, "error": "Folder not found"})
    pattern = "**/*" if recurse else "*"
    files   = [f for f in folder.glob(pattern)
               if f.is_file() and f.suffix.lower() in HIF_EXTENSIONS]
    preview = [f.name for f in files[:5]]
    return jsonify({"ok": True, "count": len(files),
                    "preview": preview, "extra": max(0, len(files) - 5)})


@app.route("/api/hif/convert", methods=["POST"])
def hif_convert():
    global _hif_job
    if not _HIF_AVAILABLE:
        return jsonify({"ok": False, "error": "convert_hif_to_jpg.py not found"})
    with _hif_lock:
        if _hif_job["running"]:
            return jsonify({"ok": False, "error": "A job is already running"})

    data    = request.json or {}
    style   = data.get("style", "standard")
    quality = _safe_int(data.get("quality", 90), "quality", lo=1, hi=95)
    recurse = data.get("recurse", False)

    if style not in _STYLES:
        return jsonify({"ok": False, "error": f"Unknown style: {style!r}"})

    try:
        input_dir  = _safe_path(data.get("input_folder", ""), must_exist=True)
        output_dir = _safe_path(data.get("output_folder", ""))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)})

    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = "**/*" if recurse else "*"
    files   = [f for f in input_dir.glob(pattern)
               if f.is_file() and f.suffix.lower() in HIF_EXTENSIONS]
    if not files:
        return jsonify({"ok": False, "error": "No HIF/HEIF/HEIC files found"})

    with _hif_lock:
        _hif_job = dict(running=True, total=len(files), done=0,
                        current="", results=[], cancelled=False,
                        overwrite=data.get("overwrite", False), error=None)

    threading.Thread(
        target=_hif_worker,
        args=(input_dir, output_dir, style, quality, files),
        daemon=True,
    ).start()

    return jsonify({"ok": True, "total": len(files)})


@app.route("/api/hif/status")
def hif_status():
    return jsonify(_hif_snapshot())


@app.route("/api/hif/cancel", methods=["POST"])
def hif_cancel():
    with _hif_lock:
        _hif_job["cancelled"] = True
    return jsonify({"ok": True})


@app.route("/samples/<path:filename>")
def samples(filename):
    return send_from_directory("static/samples", filename)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    url = "http://localhost:5000"
    print("=" * 40)
    print("  圖片批次縮放工具")
    print(f"  網址: {url}")
    print("  瀏覽器即將自動開啟...")
    print("  關閉此視窗即可停止伺服器")
    print("=" * 40)
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(debug=False, port=5000, threaded=True)

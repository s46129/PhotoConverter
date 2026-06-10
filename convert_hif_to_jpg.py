#!/usr/bin/env python3
"""
HIF to JPG Batch Converter  (Canon R8 / HDR10-aware)
Converts all HIF/HEIF/HEIC files in a folder to JPG format.

Usage:
  python convert_hif_to_jpg.py <input_folder> <output_folder> [options]

Options:
  --quality     JPG quality (1-95), default: 90
  --style       Color rendering style (see below), default: standard
  --recurse     Also process subfolders
  --overwrite   Overwrite existing JPG files

--style choices:
  accurate   Pure colour conversion, no Picture Style simulation.
  natural    Light enhancement: contrast x1.05, saturation x1.10.
  standard   Mimics Canon 'Standard' Picture Style.  (recommended)
  vivid      Stronger contrast & saturation, like Canon 'Vivid'.
"""

import argparse
import io
import sys
from pathlib import Path

# ── dependency check ────────────────────────────────────────────────────────
try:
    import numpy as np
    from PIL import Image, ImageCms, ImageEnhance
    import pillow_heif
except ImportError:
    print("Missing required packages. Please run:")
    print("  pip install pillow pillow-heif numpy")
    sys.exit(1)

pillow_heif.register_heif_opener()

SUPPORTED_EXTENSIONS = {".hif", ".heif", ".heic"}

# Canon Picture Style presets  (contrast_factor, saturation_factor)
_STYLES = {
    "accurate": (1.0,  1.0),
    "natural":  (0.8, 1.15),
    "standard": (1.12, 1.20),
    "vivid":    (1.20, 1.40),
}

_SRGB_PROFILE = ImageCms.createProfile("sRGB")


# ════════════════════════════════════════════════════════════════════════════
#  HDR10 / PQ pathway
#  Canon R8 HIF stores 10-bit BT.2020 + PQ (SMPTE ST 2084).
#  NCLX metadata: color_primaries=9, transfer_characteristics=16
# ════════════════════════════════════════════════════════════════════════════

def _pq_eotf(signal: np.ndarray) -> np.ndarray:
    """
    PQ Electro-Optical Transfer Function (SMPTE ST 2084).
    signal [0,1]  →  linear light [0,1]  (where 1.0 = 10 000 nits)
    """
    m1 = 2610.0 / 16384
    m2 = 2523.0 / 32
    c1 = 3424.0 / 4096
    c2 = 2413.0 / 128
    c3 = 2392.0 / 128
    V  = np.clip(signal, 0.0, 1.0)
    Vp = V ** (1.0 / m2)
    return (np.maximum(Vp - c1, 0.0) / (c2 - c3 * Vp)) ** (1.0 / m1)


# BT.2020 → BT.709 (= sRGB primaries) linear-light matrix
_M_2020_TO_709 = np.array([
    [ 1.6605, -0.5876, -0.0728],
    [-0.1246,  1.1329, -0.0083],
    [-0.0182, -0.1006,  1.1187],
], dtype=np.float32)


def _srgb_oetf(linear: np.ndarray) -> np.ndarray:
    """sRGB gamma encoding: linear [0,1] → signal [0,1]"""
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(np.maximum(linear, 0.0), 1.0 / 2.4) - 0.055,
    )


def _hdr_pq_to_srgb(image: Image.Image) -> Image.Image:
    """
    Full HDR10 → sRGB conversion pipeline for Canon R8 HIF.

    Why this was needed:
    • Canon R8 stores HIF as BT.2020 + PQ (HDR10), NOT sRGB.
    • PQ encodes luminance perceptually (0 = 0 nit, 1.0 = 10 000 nits).
    • Treating PQ values as sRGB gamma makes everything look flat/grey.

    Pipeline:
      8-bit proxy  →  PQ signal [0,1]
      →  PQ EOTF  →  linear light (nits-normalised)
      →  normalise to SDR reference white (203 nit)
      →  ACES filmic tone-map  (smooth shoulder for highlights)
      →  BT.2020 primaries  →  BT.709/sRGB primaries
      →  sRGB gamma (OETF)
    """
    if image.mode != "RGB":
        image = image.convert("RGB")

    arr = np.array(image, dtype=np.float32) / 255.0   # PQ signal, [0,1]

    # 1. PQ → linear light (0-1, 1=10 000 nits)
    linear = _pq_eotf(arr)

    # 2. Normalise to SDR reference white.
    #    In the PQ/HLG world, 203 nits is the "diffuse white" reference for
    #    SDR content lifted into a PQ container (ITU-R BT.2408).
    L = linear * (10000.0 / 203.0)

    # 3. ACES filmic tone mapping
    #    Maps [0, +∞) → [0, 1) with a natural filmic shoulder.
    #    Widely used in games/film for HDR→SDR conversion.
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    L_tone = np.clip((L * (a * L + b)) / (L * (c * L + d) + e), 0.0, 1.0)

    # 4. BT.2020 → BT.709 colour primaries (linear RGB)
    shape   = L_tone.shape
    L_709   = np.clip(L_tone.reshape(-1, 3) @ _M_2020_TO_709.T, 0.0, 1.0)
    L_709   = L_709.reshape(shape)

    # 5. sRGB gamma
    srgb = _srgb_oetf(L_709)

    return Image.fromarray((np.clip(srgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8))


# ════════════════════════════════════════════════════════════════════════════
#  Standard ICC pathway  (for sRGB / P3 HEIF, non-Canon sources)
# ════════════════════════════════════════════════════════════════════════════

def _icc_to_srgb(image: Image.Image) -> Image.Image:
    """
    Convert embedded ICC profile → sRGB with PERCEPTUAL rendering intent.
    (Perceptual compresses the whole gamut proportionally; the old default
     RELATIVE_COLORIMETRIC clips out-of-sRGB colours to grey.)
    """
    raw_icc = image.info.get("icc_profile")
    if image.mode != "RGB":
        image = image.convert("RGB")
    if not raw_icc:
        return image
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(raw_icc))
        return ImageCms.profileToProfile(
            image, src, _SRGB_PROFILE,
            renderingIntent=ImageCms.Intent.PERCEPTUAL,
            outputMode="RGB",
        )
    except Exception:
        return image


def _auto_levels(image: Image.Image) -> Image.Image:
    """
    Per-channel histogram stretch.
    Used for the ICC pathway where tonal range may be compressed.
    Not applied after PQ tone-mapping (levels are already correct there).
    """
    r, g, b = image.split()
    stretched = []
    for ch in (r, g, b):
        lo, hi = ch.getextrema()
        if hi > lo:
            ch = ch.point(lambda v, lo=lo, s=255.0/(hi-lo): int((v - lo) * s))
        stretched.append(ch)
    return Image.merge("RGB", stretched)


# ════════════════════════════════════════════════════════════════════════════
#  Canon Picture Style simulation
# ════════════════════════════════════════════════════════════════════════════

def _apply_style(image: Image.Image, contrast: float, saturation: float) -> Image.Image:
    if saturation != 1.0:
        image = ImageEnhance.Color(image).enhance(saturation)
    if contrast != 1.0:
        image = ImageEnhance.Contrast(image).enhance(contrast)
    return image


# ════════════════════════════════════════════════════════════════════════════
#  Main conversion  (chooses pipeline automatically)
# ════════════════════════════════════════════════════════════════════════════

def _is_pq_hdr(nclx: dict | None) -> bool:
    """Return True when the NCLX profile indicates PQ HDR (transfer=16)."""
    if not nclx:
        return False
    # transfer_characteristics == 16  →  SMPTE ST 2084 (PQ)
    return nclx.get("transfer_characteristics") == 16


def convert_file(src: Path, dst: Path, quality: int, style: str) -> bool:
    contrast, saturation = _STYLES[style]
    try:
        # Use pillow_heif's low-level API to read NCLX colour metadata
        heif_file = pillow_heif.read_heif(src)
        heif_img  = heif_file[0]
        nclx      = heif_img.info.get("nclx_profile")
        image     = heif_img.to_pillow()

        if _is_pq_hdr(nclx):
            # ── HDR10 path (Canon R8 HIF, BT.2020 + PQ) ──────────────────
            image = _hdr_pq_to_srgb(image)
        else:
            # ── Standard ICC path (sRGB / P3 HEIC / other HEIF) ──────────
            image = _icc_to_srgb(image)
            image = _auto_levels(image)

        # Canon Picture Style simulation on top
        image = _apply_style(image, contrast, saturation)

        if image.mode != "RGB":
            image = image.convert("RGB")

        dst.parent.mkdir(parents=True, exist_ok=True)
        image.save(dst, format="JPEG", quality=quality, subsampling=0)
        return True

    except Exception as exc:
        print(f"  [ERROR] {src.name}: {exc}")
        return False


# ════════════════════════════════════════════════════════════════════════════
#  File discovery
# ════════════════════════════════════════════════════════════════════════════

def collect_files(input_folder: Path, recurse: bool) -> list[Path]:
    pattern = "**/*" if recurse else "*"
    return [
        f for f in input_folder.glob(pattern)
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


# ════════════════════════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Batch convert HIF/HEIF/HEIC to JPG (Canon R8 HDR10-aware)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_folder",  help="Folder containing HIF files")
    parser.add_argument("output_folder", help="Folder to save JPG files")
    parser.add_argument("--quality",  type=int, default=90, metavar="1-95",
                        help="JPG quality (default: 90)")
    parser.add_argument("--style",    choices=_STYLES.keys(), default="standard",
                        help="Colour rendering style (default: standard)")
    parser.add_argument("--recurse",  action="store_true",
                        help="Process subfolders recursively")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing JPG files")
    args = parser.parse_args()

    input_folder  = Path(args.input_folder).resolve()
    output_folder = Path(args.output_folder).resolve()

    if not input_folder.exists():
        print(f"Error: Input folder does not exist: {input_folder}")
        sys.exit(1)
    if not 1 <= args.quality <= 95:
        print("Error: Quality must be between 1 and 95")
        sys.exit(1)

    files = collect_files(input_folder, args.recurse)
    if not files:
        print(f"No HIF/HEIF/HEIC files found in: {input_folder}")
        sys.exit(0)

    contrast, saturation = _STYLES[args.style]
    print(f"Found {len(files)} file(s) to convert")
    print(f"Output folder : {output_folder}")
    print(f"JPG quality   : {args.quality}")
    print(f"Style         : {args.style}  "
          f"(contrast ×{contrast}, saturation ×{saturation})")
    print("-" * 55)

    ok = skip = fail = 0
    for src in files:
        rel = src.relative_to(input_folder)
        dst = output_folder / rel.with_suffix(".jpg")

        if dst.exists() and not args.overwrite:
            print(f"  [SKIP] {rel}")
            skip += 1
            continue

        print(f"  [CONV] {rel}", end=" ... ", flush=True)
        if convert_file(src, dst, args.quality, args.style):
            print("OK")
            ok += 1
        else:
            fail += 1

    print("-" * 55)
    print(f"Done: {ok} converted, {skip} skipped, {fail} failed")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

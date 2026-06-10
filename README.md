# PhotoConverter

A collection of two practical image tools built with Python.

---

## Tools

### 1. HIF / HEIF → JPG Batch Converter (`convert_hif_to_jpg.py`)

A command-line batch converter that correctly handles **HDR10-encoded HEIF files** (BT.2020 + PQ transfer function) — common in modern cameras such as the Canon EOS R8.

**Why does this exist?**  
Most converters treat HEIF files as sRGB and produce flat, desaturated results. This tool detects the NCLX colour metadata, applies the full **PQ EOTF → ACES tone-mapping → BT.2020→BT.709 matrix → sRGB gamma** pipeline, so the output looks as vivid as the camera's in-camera JPEG.

**Supported input:** `.hif` `.heif` `.heic`  
**Output:** `.jpg`

#### Usage

```bash
python convert_hif_to_jpg.py <input_folder> <output_folder> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--quality` | `90` | JPG quality (1–95) |
| `--style` | `standard` | Colour rendering style (see below) |
| `--recurse` | off | Process subfolders recursively |
| `--overwrite` | off | Overwrite existing output files |

**Styles:**

| Style | Contrast | Saturation | Description |
|-------|----------|------------|-------------|
| `accurate` | ×1.00 | ×1.00 | Pure colour-space conversion only |
| `natural` | ×1.05 | ×1.10 | Subtle enhancement |
| `standard` | ×1.12 | ×1.20 | Mimics Canon Standard Picture Style |
| `vivid` | ×1.20 | ×1.40 | Strong pop, similar to Canon Vivid |

#### Examples

```bash
# Basic conversion (standard style, quality 90)
python convert_hif_to_jpg.py ./input ./output

# Vivid style, overwrite existing files
python convert_hif_to_jpg.py ./input ./output --style vivid --overwrite

# Recurse subfolders, lower quality for smaller files
python convert_hif_to_jpg.py ./input ./output --recurse --quality 75
```

---

### 2. Image Batch Resizer (`image_resizer.py`)

A **web-based** batch image resizer with a clean browser UI. Supports all common formats including HEIF/HIF.

**Supported input:** `.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tiff` `.gif` `.heif` `.heic` `.hif`  
**Supported output:** JPG, PNG, WEBP, or keep original format

#### Features

- **4 resize modes:** By Width / By Height / Percentage / Exact Size
- **3 fit options** for Exact Size: Contain (letterbox), Cover & Crop, Stretch
- Adjustable JPG/WEBP quality
- Optional subfolders recursion
- Real-time progress bar and per-file status
- EN / 中文 UI toggle
- **Cross-platform** folder browser dialog (Windows, macOS, Linux)

#### Usage

**Windows:**
```bat
start_resizer.bat
```
or
```bash
python image_resizer.py
```

**macOS / Linux:**
```bash
chmod +x start_resizer.sh
./start_resizer.sh
```

The browser opens automatically at `http://localhost:5000`.  
Close the terminal window (or press `Ctrl+C`) to stop the server.

---

## Installation

**Requirements:** Python 3.10+

```bash
pip install -r requirements.txt
```

| Package | Purpose |
|---------|---------|
| `pillow` | Image processing |
| `pillow-heif` | HEIF/HIF/HEIC support |
| `numpy` | HDR colour-space math |
| `flask` | Web server for the resizer UI |

---

## How the HDR Conversion Works

Canon R8 (and other modern cameras) store HIF files in **HDR10** format:

```
NCLX metadata
  color_primaries        = 9   → BT.2020
  transfer_characteristics = 16  → PQ / SMPTE ST 2084
```

Without proper handling, converters output flat/grey images because they misinterpret PQ-encoded luminance values as sRGB.

This tool applies the correct pipeline:

```
10-bit PQ signal
  → PQ EOTF        (signal → linear nits)
  → Normalise      (203-nit SDR reference white)
  → ACES filmic    (HDR highlights compressed gracefully)
  → BT.2020→BT.709 (colour primaries matrix)
  → sRGB OETF      (gamma encoding)
  → 8-bit JPG
```

---

## Project Structure

```
PhotoConverter/
├── convert_hif_to_jpg.py      # CLI: HIF/HEIF → JPG batch converter
├── image_resizer.py           # Web: batch image resizer + HIF converter UI
├── templates/
│   └── index.html             # Web UI (EN / 中文)
├── static/
│   └── samples/
│       ├── IMG_1436.HIF       # Sample source photo (© Rex Ying, for demo only)
│       ├── sample_accurate.jpg
│       ├── sample_natural.jpg
│       ├── sample_standard.jpg
│       └── sample_vivid.jpg
├── start_resizer.bat          # Windows launcher
├── start_resizer.sh           # macOS/Linux launcher
├── requirements.txt
└── LICENSE                    # MIT
```

> **Note:** The sample photo (`IMG_1436.HIF`) is copyright © Rex Ying and is included
> solely to demonstrate the HDR colour conversion pipeline. It may not be redistributed
> or used outside of this project.

---

## License

MIT © 2026 Rex Ying (ted56129@gmail.com)

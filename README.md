# PhotoConverter

[English](#-english) | [繁體中文](#-繁體中文)

---

## 🇬🇧 English

A Python toolkit for **colour-correct batch conversion and resizing** of photos in any format — with first-class support for HDR10-encoded HIF / HEIF / HEIC files from cameras such as the Canon EOS R8.

### Tools

| Tool | Type | Purpose |
|------|------|---------|
| `image_resizer.py` | **Web UI** | Unified colour + resize tool — main interface |
| `convert_hif_to_jpg.py` | CLI | Batch HIF → JPG converter (scriptable / headless) |

---

### Web UI — `image_resizer.py`

#### Step 1 — Download

1. Click the green **Code** button near the top of this page → **Download ZIP**
2. Extract the ZIP to any folder (e.g. your Desktop)
3. Open the extracted `PhotoConverter` folder — the launcher files are right inside:

```
PhotoConverter/
├── start_resizer.bat   ← double-click this on Windows
├── start_resizer.sh    ← run this on macOS / Linux
└── ...
```

#### Step 2 — One-time setup (first run only)

**a) Install Python 3.10+**  
Download from [python.org/downloads](https://www.python.org/downloads/) and run the installer.  
On Windows: tick **"Add Python to PATH"** before clicking Install.

**b) Install dependencies**  
Open a terminal inside the `PhotoConverter` folder and run:
```bash
pip install -r requirements.txt
```

> **Windows tip:** hold `Shift` and right-click inside the folder → *Open PowerShell window here*, then paste the command above.  
> **macOS tip:** open Terminal, type `cd ` (with a space), then drag the `PhotoConverter` folder into the Terminal window and press Enter.

#### Step 3 — Launch

**Windows** — double-click `start_resizer.bat`

**macOS / Linux**
```bash
chmod +x start_resizer.sh   # one-time only
./start_resizer.sh
```

The browser opens automatically at `http://localhost:5000`.  
Press `Ctrl+C` (or close the terminal window) to stop the server.

#### Supported formats

| | Formats |
|-|---------|
| **Input** | `.hif` `.heif` `.heic` `.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tiff` `.gif` |
| **Output** | JPG · PNG · WEBP · Keep original |

#### Workflow

The page guides you through four steps in order:

**① Folders**  
Choose your input and output folders with the Browse button or by typing a path directly.  
Tick *Include subfolders* to process nested directories.  
Click **Scan** — the tool counts all supported images and shows a preview of filenames.

**② Colour Style** *(appears automatically when HIF / HEIF / HEIC files are detected)*  
Four preset styles shown as sample thumbnails — click one to select it.  
The **comparison slider** lets you drag to compare *Accurate* (pure conversion, left) against the selected style (right) in real time.  
Use the **Contrast** and **Saturation** sliders to fine-tune beyond the presets; a *Custom* badge appears when your values no longer match any preset.

| Preset | Contrast | Saturation | Character |
|--------|----------|------------|-----------|
| `Accurate` | ×1.00 | ×1.00 | Pure colour-space conversion, no enhancement |
| `Natural` | ×0.80 | ×1.15 | Softer contrast, slightly lifted saturation |
| `Standard` | ×1.12 | ×1.20 | Mimics Canon Standard Picture Style |
| `Vivid` | ×1.20 | ×1.40 | Strong pop, similar to Canon Vivid |

> HIF / HEIF / HEIC files are HDR10-encoded. PhotoConverter automatically applies the full **PQ EOTF → ACES tone-mapping → BT.2020→BT.709 → sRGB** pipeline before any style adjustment — no manual configuration required.  
> All other formats (JPG, PNG, …) receive ICC → sRGB conversion.

**③ Resize** *(optional — off by default)*  
Toggle on to resize during conversion. Four modes:

| Mode | Description |
|------|-------------|
| By Width | Scale to target width; height calculated automatically |
| By Height | Scale to target height; width calculated automatically |
| Percentage | Scale by a percentage (e.g. 50 % = half size) |
| Exact Size | Fixed W × H with Contain / Cover / Stretch fitting |

**④ Output Settings**  
Choose output format (JPG / PNG / WEBP / Keep original), JPG/WEBP quality (1–95), and whether to overwrite existing files.

Press **Start Processing** — a real-time progress bar and per-file status list appear below.

---

### CLI — `convert_hif_to_jpg.py`

Headless batch converter, useful for scripting or automation.

```bash
python convert_hif_to_jpg.py <input_folder> <output_folder> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--quality` | `90` | JPG quality (1–95) |
| `--style` | `standard` | Colour style: `accurate` `natural` `standard` `vivid` |
| `--recurse` | off | Process subfolders recursively |
| `--overwrite` | off | Overwrite existing output files |

**Examples**

```bash
# Basic conversion
python convert_hif_to_jpg.py ./input ./output

# Vivid style, overwrite existing
python convert_hif_to_jpg.py ./input ./output --style vivid --overwrite

# Recurse, lower quality for smaller files
python convert_hif_to_jpg.py ./input ./output --recurse --quality 75
```

---

### Installation

**Requirements:** Python 3.10+

```bash
pip install -r requirements.txt
```

| Package | Purpose |
|---------|---------|
| `pillow` | Image processing |
| `pillow-heif` | HEIF / HIF / HEIC decoding |
| `numpy` | HDR colour-space math |
| `flask` | Web server for the browser UI |

---

### How the HDR Conversion Works

Canon R8 (and other modern cameras) store HIF files with **HDR10** metadata:

```
NCLX metadata
  color_primaries          = 9   → BT.2020
  transfer_characteristics = 16  → PQ / SMPTE ST 2084
```

Without correct handling, converters misread PQ-encoded values as sRGB gamma and output flat, washed-out images.  
PhotoConverter applies the full industry-standard pipeline:

```
10-bit PQ signal
  → PQ EOTF         (signal → absolute linear nits)
  → Normalise       (map 203-nit SDR reference white to 1.0)
  → ACES filmic     (graceful highlight compression)
  → BT.2020→BT.709  (colour primaries matrix)
  → sRGB OETF       (gamma encoding)
  → 8-bit output
```

---

### Project Structure

```
PhotoConverter/
├── convert_hif_to_jpg.py      # CLI: HIF/HEIF → JPG batch converter
├── image_resizer.py           # Web: unified colour + resize UI (v2.0.0)
├── templates/
│   └── index.html             # Single-page web UI (EN / 中文)
├── static/
│   └── samples/
│       ├── IMG_1436.HIF       # Sample source photo (© Rex Ying, demo only)
│       ├── sample_accurate.jpg
│       ├── sample_natural.jpg
│       ├── sample_standard.jpg
│       └── sample_vivid.jpg
├── start_resizer.bat          # Windows launcher
├── start_resizer.sh           # macOS / Linux launcher
├── requirements.txt
└── LICENSE                    # MIT
```

> **Note:** `IMG_1436.HIF` is copyright © Rex Ying and is included solely to demonstrate the HDR colour conversion pipeline. It may not be redistributed or used outside of this project.

---

### License

MIT © 2026 Rex Ying (ted56129@gmail.com)

---
---

## 🇹🇼 繁體中文

以 Python 打造的圖片批次處理工具，支援**色彩校正與縮放**，並對 Canon EOS R8 等相機輸出的 HDR10 編碼 HIF / HEIF / HEIC 檔案提供完整支援。

### 工具一覽

| 工具 | 類型 | 用途 |
|------|------|------|
| `image_resizer.py` | **網頁介面** | 色彩校正 + 縮放的統一工具，主要操作介面 |
| `convert_hif_to_jpg.py` | 命令列 | HIF → JPG 批次轉換（可用於腳本自動化） |

---

### 網頁介面 — `image_resizer.py`

#### 步驟一：下載程式

1. 點擊本頁上方綠色的 **Code** 按鈕 → **Download ZIP**
2. 將 ZIP 解壓縮到任意位置（例如桌面）
3. 開啟解壓縮後的 `PhotoConverter` 資料夾，啟動器就在裡面：

```
PhotoConverter/
├── start_resizer.bat   ← Windows 請雙擊這個檔案
├── start_resizer.sh    ← macOS / Linux 請執行這個
└── ...
```

#### 步驟二：一次性設定（首次使用才需要）

**a) 安裝 Python 3.10+**  
前往 [python.org/downloads](https://www.python.org/downloads/) 下載並執行安裝程式。  
Windows 安裝時請務必勾選 **「Add Python to PATH」** 再點擊 Install。

**b) 安裝相依套件**  
在 `PhotoConverter` 資料夾內開啟終端機，執行：
```bash
pip install -r requirements.txt
```

> **Windows 小技巧：** 在資料夾內按住 `Shift` 鍵並右鍵點擊空白處 → 選擇「在此處開啟 PowerShell 視窗」，貼上上方指令即可。  
> **macOS 小技巧：** 開啟 Terminal，輸入 `cd `（注意後面有空格），再把 `PhotoConverter` 資料夾拖曳到 Terminal 視窗中，按 Enter 確認，再執行安裝指令。

#### 步驟三：啟動

**Windows** — 直接雙擊 `start_resizer.bat`

**macOS / Linux**
```bash
chmod +x start_resizer.sh   # 只需執行一次
./start_resizer.sh
```

瀏覽器會自動開啟 `http://localhost:5000`。  
按 `Ctrl+C` 或直接關閉終端機視窗即可停止伺服器。

#### 支援格式

| | 格式 |
|-|------|
| **輸入** | `.hif` `.heif` `.heic` `.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tiff` `.gif` |
| **輸出** | JPG · PNG · WEBP · 保留原始格式 |

#### 操作流程

頁面引導你依序完成四個步驟：

**① 資料夾**  
點擊「瀏覽」按鈕或直接輸入路徑，選擇來源與輸出資料夾。  
勾選「遞迴子資料夾」可處理子目錄中的圖片。  
點擊「掃描」— 工具會統計所有支援的圖片數量並預覽檔名。

**② 色彩風格** *（偵測到 HIF / HEIF / HEIC 檔案時自動顯示）*  
四種預設風格以縮圖顯示 — 點擊即可選擇。  
**比較滑桿**可拖曳即時對比左側「精確」（純轉換）與右側所選風格的效果。  
使用**對比度**與**飽和度**滑桿進一步微調；數值不符合任何預設時，會顯示「自訂」標籤。

| 預設 | 對比度 | 飽和度 | 風格特色 |
|------|--------|--------|---------|
| `精確 Accurate` | ×1.00 | ×1.00 | 純色彩空間轉換，不做任何增強 |
| `自然 Natural` | ×0.80 | ×1.15 | 較柔和的對比，略微提升飽和度 |
| `標準 Standard` | ×1.12 | ×1.20 | 模擬 Canon 標準相片風格 |
| `鮮艷 Vivid` | ×1.20 | ×1.40 | 強烈飽和感，類似 Canon 鮮艷模式 |

> HIF / HEIF / HEIC 為 HDR10 編碼。PhotoConverter 會自動套用完整的 **PQ EOTF → ACES 色調映射 → BT.2020→BT.709 → sRGB** 流程，無需手動設定。  
> 其他格式（JPG、PNG 等）則會進行 ICC → sRGB 色彩轉換。

**③ 縮放** *（選用，預設關閉）*  
開啟後可在轉換同時縮放圖片。四種模式：

| 模式 | 說明 |
|------|------|
| 依寬度 | 縮放至目標寬度，高度自動計算 |
| 依高度 | 縮放至目標高度，寬度自動計算 |
| 百分比 | 依比例縮放（例如 50% = 半尺寸） |
| 指定尺寸 | 固定 W × H，支援保持比例 / 填滿裁切 / 強制拉伸 |

**④ 輸出設定**  
選擇輸出格式（JPG / PNG / WEBP / 原始格式）、JPG/WEBP 品質（1–95），以及是否覆蓋已存在的檔案。

按下「開始處理」— 下方即時顯示進度條與每個檔案的處理狀態。

---

### 命令列工具 — `convert_hif_to_jpg.py`

無介面的批次轉換器，適合腳本或自動化流程。

```bash
python convert_hif_to_jpg.py <來源資料夾> <輸出資料夾> [選項]
```

| 選項 | 預設值 | 說明 |
|------|--------|------|
| `--quality` | `90` | JPG 品質（1–95） |
| `--style` | `standard` | 色彩風格：`accurate` `natural` `standard` `vivid` |
| `--recurse` | 關閉 | 遞迴處理子資料夾 |
| `--overwrite` | 關閉 | 覆蓋已存在的輸出檔案 |

**使用範例**

```bash
# 基本轉換（standard 風格，品質 90）
python convert_hif_to_jpg.py ./input ./output

# 鮮艷風格，覆蓋已存在的檔案
python convert_hif_to_jpg.py ./input ./output --style vivid --overwrite

# 遞迴子資料夾，降低品質以縮小檔案大小
python convert_hif_to_jpg.py ./input ./output --recurse --quality 75
```

---

### 安裝

**需求：** Python 3.10+

```bash
pip install -r requirements.txt
```

| 套件 | 用途 |
|------|------|
| `pillow` | 圖片處理 |
| `pillow-heif` | HEIF / HIF / HEIC 解碼 |
| `numpy` | HDR 色彩空間運算 |
| `flask` | 網頁介面伺服器 |

---

### HDR 轉換原理

Canon R8 等現代相機將 HIF 檔案儲存為 **HDR10** 格式：

```
NCLX 元資料
  color_primaries          = 9   → BT.2020 色域
  transfer_characteristics = 16  → PQ / SMPTE ST 2084 傳遞函數
```

若未正確處理，轉換器會將 PQ 編碼的亮度值誤解為 sRGB gamma，導致輸出影像灰暗失真。  
PhotoConverter 套用完整的業界標準流程：

```
10-bit PQ 訊號
  → PQ EOTF          （訊號 → 絕對線性亮度 nits）
  → 標準化            （以 203 nit SDR 參考白為基準）
  → ACES filmic       （高光壓縮，保留細節）
  → BT.2020→BT.709   （色域矩陣轉換）
  → sRGB OETF         （gamma 編碼）
  → 8-bit 輸出
```

---

### 專案結構

```
PhotoConverter/
├── convert_hif_to_jpg.py      # 命令列：HIF/HEIF → JPG 批次轉換
├── image_resizer.py           # 網頁：統一色彩校正 + 縮放介面（v2.0.0）
├── templates/
│   └── index.html             # 單頁網頁介面（EN / 中文）
├── static/
│   └── samples/
│       ├── IMG_1436.HIF       # 示意照片（© Rex Ying，僅供示範）
│       ├── sample_accurate.jpg
│       ├── sample_natural.jpg
│       ├── sample_standard.jpg
│       └── sample_vivid.jpg
├── start_resizer.bat          # Windows 啟動器
├── start_resizer.sh           # macOS / Linux 啟動器
├── requirements.txt
└── LICENSE                    # MIT 授權
```

> **注意：** `IMG_1436.HIF` 版權歸 Rex Ying 所有，僅作為 HDR 色彩轉換流程的示意用途，不得轉載或用於本專案以外之用途。

---

### 授權

MIT © 2026 Rex Ying (ted56129@gmail.com)

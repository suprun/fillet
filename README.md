<div align="center">

# Fillet & Chamfer for QGIS 3.x (Interactive & Batch)

<p align="center">
  <img src="icon.png" alt="Fillet and Chamfer Logo" width="96" height="96" />
</p>

**Interactive CAD-style Fillet (corner rounding) & Chamfer (corner beveling) digitizing tools for QGIS 3.x, plus instant Batch Processing for QGIS 3.x & 4.x.**

[![QGIS Compatibility](https://img.shields.io/badge/QGIS-3.16%20--%204.99-brightgreen.svg?logo=qgis)](https://plugins.qgis.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%20%7C%203.12-blue.svg?logo=python)](https://python.org)
[![PyQt](https://img.shields.io/badge/UI-PyQt5%20%7C%20PyQt6-orange.svg?logo=qt)](https://riverbankcomputing.com/software/pyqt/)
[![Multi-Version Tests](https://img.shields.io/badge/Tests-5%20QGIS%20Versions%20Passed-success.svg)](#multi-version-testing)
[![Languages](https://img.shields.io/badge/Languages-40%20Locales-blueviolet.svg)](#localization)

</div>

---

## 🌟 Overview

The **Fillet & Chamfer** plugin backports the interactive CAD-like digitizing tool introduced in the upcoming **QGIS 4.0** directly into the **QGIS 3.x LTR series** (from QGIS 3.16 up to QGIS 3.44+), complete with a floating on-canvas CAD HUD widget.

In addition, it provides a dedicated **Batch Processing Dock Panel** compatible with both **QGIS 3.x** and **QGIS 4.0+**, allowing users to round or bevel all vertices across selected features and complex polygon rings with a single click.

---

## 🚀 Key Features

### 1. 🎯 Interactive CAD Digitizing Tool (QGIS 3.x)
- **On-Canvas CAD HUD Control**: Floating panel on the map canvas providing instant control over radius, distances, and arc segments.
- **Fillet Mode (Corner Rounding)**:
  - Precise circular arc discretization with customizable **Fillet segments** count ($N$ segments = $N+1$ vertices).
  - Clean analytical interpolation ensuring exact tangent intersection with adjacent edges.
- **Chamfer Mode (Corner Beveling)**:
  - Symmetric beveling ($d_1 = d_2$) or independent dual-distance beveling ($d_1 \neq d_2$) with link toggle.
- **Lock / Unlock Numeric Control**:
  - **Locked (Default)**: Click any vertex to instantly apply the exact configured numeric value.
  - **Unlocked**: Move the mouse interactively across the canvas to adjust the radius or distance in real time.
- **Live Preview & Visual Feedback**:
  - Tangent snap markers on adjacent segments.
  - Live dashed rubberband preview of the resulting fillet arc or chamfer segment.
- **Full CRS & Units Awareness**:
  - Automatic dynamic adaptation for **Projected CRS** (meters: 3 decimal places, step 1.0, default 5.0m) and **Geographic CRS** (degrees / EPSG:4326: 6 decimal places, step 0.00005°, default 0.0001°).
- **Native Transaction Integration**:
  - Full Undo/Redo (`Ctrl+Z` / `Ctrl+Y`) support within QGIS edit sessions.

### 2. ⚡ Batch Processing Dock Panel (QGIS 3.x & QGIS 4.x)
- Dockable panel on the right sidebar for instant batch processing.
- Automatically processes all vertices of all parts in selected features (`LineString`, `Polygon`, `MultiLineString`, `MultiPolygon`).
- Supports exterior rings as well as all interior hole rings.

### 3. 🛡️ Edit-Mode Safety
- Toolbar action buttons (`actionFilletChamfer` and `actionFilletChamferBatch`) are **automatically enabled only when an active vector layer is in Edit Mode** (`layer.isEditable() == True`).
- If editing is saved or rolled back while the map tool is active, the tool automatically unsets and hides the on-canvas widget to prevent unintended edits.

---

## 📦 Compatibility Matrix

| QGIS Version | Platform | UI Framework | Interactive Map Tool | Batch Dock Widget | Test Status |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **QGIS 3.16 LTR** | Windows / Linux / macOS | Qt5 / PyQt5 | ✅ Included | ✅ Included | ✅ Passed |
| **QGIS 3.28 LTR** | Windows / Linux / macOS | Qt5 / PyQt5 | ✅ Included | ✅ Included | ✅ Passed |
| **QGIS 3.34 LTR** | Windows / Linux / macOS | Qt5 / PyQt5 | ✅ Included | ✅ Included | ✅ Passed |
| **QGIS 3.40 LTR** | Windows / Linux / macOS | Qt5 / PyQt5 | ✅ Included | ✅ Included | ✅ Passed |
| **QGIS 4.0.x** | Windows / Linux / macOS | Qt6 / PyQt6 | *Native QGIS 4 tool* | ✅ Included | ✅ Passed |

---

## 📥 Installation

### Method 1: Official QGIS Plugin Repository
1. Open QGIS.
2. Go to **Plugins** → **Manage and Install Plugins...**
3. Search for **Fillet & Chamfer**.
4. Click **Install Plugin**.

### Method 2: Custom Plugin Repository
1. In QGIS, open **Plugins** → **Manage and Install Plugins...** → **Settings**.
2. Under *Plugin Repositories*, click **Add...**.
3. Set Name: `Suprun QGIS Plugins`
4. Set URL: `https://raw.githubusercontent.com/suprun/fillet/master/repo/plugins.xml`
5. Click **OK**, then install **Fillet & Chamfer for QGIS 3.x**.

### Method 3: Manual Installation (from ZIP)
1. Download `fillet.zip` from [Latest Releases](https://github.com/suprun/fillet/releases/latest).
2. Unzip into your QGIS active profile plugin folder:
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\fillet`
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/fillet`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/fillet`
3. Restart QGIS or enable the plugin in **Plugins Manager**.

---

## 📖 Usage Guide

### 🛠️ Interactive Digitizing Workflow
1. Select a Line or Polygon vector layer in the Layers panel.
2. Click **Toggle Editing** (`Ctrl+E` or pencil icon).
3. Click the **Fillet / Chamfer Tool** button on the *Advanced Digitizing Toolbar* or in the *Vector* menu.
4. The floating CAD HUD control appears on the canvas:
   - Choose **Fillet** (enter Radius $R$ and number of Arc Segments) or **Chamfer** (enter Distance $d_1$ and $d_2$).
   - Toggle the **Lock Icon** (locked to click-apply fixed value; unlocked to drag interactively).
5. Hover over any vertex of the feature to view the tangent cut markers and live preview.
6. Left-click to commit the fillet or chamfer. Press `Ctrl+Z` to undo at any time.

### ⚡ Batch Processing Workflow
1. Put your target layer into edit mode.
2. Select one or more features using the QGIS selection tool.
3. Click the **Fillet / Chamfer (Batch Processing)** button to open the dock panel.
4. Set the desired Radius or Chamfer distances.
5. Click **Apply to Selected Features**. All corners of the selected features will be rounded or beveled immediately.

---

## 🧪 Development & Multi-Version Testing

The plugin includes an automated test suite covering geometry precision, plugin lifecycle, translation loading, and settings persistence.

To run automated smoke tests across all installed QGIS versions on your machine:

```powershell
python scripts/smoke_test_all_qgis.py
```

### Packaging for Release
To package a clean, repository-compliant release ZIP without test caches or ignored files:

```powershell
python scripts/package_plugin.py
```

---

## 🌐 Localization

The plugin is fully translated into **40 locales (all official QGIS GUI languages)**:
- Arabic (`ar`), Bulgarian (`bg`), Catalan (`ca`), Czech (`cs`), Danish (`da`), German (`de`), Greek (`el`), English (`en`), Spanish (`es`), Estonian (`et`), Basque (`eu`), Finnish (`fi`), French (`fr`), Galician (`gl`), Hindi (`hi`), Croatian (`hr`), Hungarian (`hu`), Indonesian (`id`), Italian (`it`), Japanese (`ja`), Korean (`ko`), Lithuanian (`lt`), Latvian (`lv`), Norwegian (`nb`), Dutch (`nl`), Polish (`pl`), Portuguese (`pt`, `pt_BR`), Romanian (`ro`), Slovak (`sk`), Slovenian (`sl`), Serbian (`sr`), Swedish (`sv`), Thai (`th`), Turkish (`tr`), Ukrainian (`uk`), Vietnamese (`vi`), Chinese (`zh`, `zh_CN`, `zh_TW`).

Translations are automatically compiled from `.ts` to `.qm` via:
```powershell
python scripts/compile_translations.py
```

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 👤 Author

**Serhiy Suprun**
- GitHub: [@suprun](https://github.com/suprun)
- Email: `suprun.serhiy+qgis@gmail.com`
- Issues & Suggestions: [GitHub Issues](https://github.com/suprun/fillet/issues)

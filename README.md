<div align="center">

# Fillet, Chamfer & Corner Restore for QGIS (Interactive & Batch)

<p align="center">
  <img src="icon.png" alt="Fillet, Chamfer & Corner Restore Logo" width="96" height="96" />
</p>

**Comprehensive CAD editing suite for QGIS: Interactive Fillet (corner rounding), Chamfer (corner beveling), and Two-Edge Corner Restoration (Unfillet / Unchamfer), plus instant Batch Processing for QGIS 3.x & 4.x.**

[![QGIS Compatibility](https://img.shields.io/badge/QGIS-3.16%20--%204.99-brightgreen.svg?logo=qgis)](https://plugins.qgis.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%20%7C%203.12-blue.svg?logo=python)](https://python.org)
[![PyQt](https://img.shields.io/badge/UI-PyQt5%20%7C%20PyQt6-orange.svg?logo=qt)](https://riverbankcomputing.com/software/pyqt/)
[![Multi-Version Tests](https://img.shields.io/badge/Tests-5%20QGIS%20Versions%20Passed-success.svg)](#multi-version-testing)
[![Languages](https://img.shields.io/badge/Languages-40%20Locales-blueviolet.svg)](#localization)

</div>

---

## 🌟 Overview

The **Fillet, Chamfer & Corner Restore** plugin brings professional CAD-style corner manipulation tools to QGIS:

1. **Backports the QGIS 4.0 Interactive Fillet/Chamfer CAD Tool** directly into the **QGIS 3.x LTR series** (from QGIS 3.16 up to QGIS 3.44+), complete with a floating on-canvas CAD HUD widget.
2. **Introduces an Interactive Corner Restoration (Unfillet / Unchamfer) CAD Tool** for both **QGIS 3.x and QGIS 4.0+**, allowing users to select two adjacent edges, remove any intermediate arc or bevel vertices, and reconstruct the exact sharp intersection corner ($V_{\text{sharp}}$).
3. **Provides a dedicated Batch Processing Dock Panel** compatible with both **QGIS 3.x and QGIS 4.0+**, allowing users to round, bevel, or restore corners across selected features with a single click.

---

## 🚀 Key Features

### 1. 🎯 Interactive Fillet & Chamfer Tool (QGIS 3.x)
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

---

### 2. 📐 Interactive Corner Restoration / Unfillet & Unchamfer (QGIS 3.x & QGIS 4.x)
- **CAD Two-Edge Selection Workflow**:
  - **Step 1**: Hover over any straight edge $E_1$ adjacent to the corner and left-click to select.
  - **Step 2**: Hover over the second adjacent edge $E_2$. The tool analytically computes the infinite ray intersection $V_{\text{sharp}}$, automatically detects all intermediate arc chords or bevel segments, and renders a live rubberband preview of the reconstructed geometry.
  - **Step 3**: Left-click $E_2$ to commit the sharp corner reconstruction into the layer edit history.
  - Right-click or press `Escape` at any time to cancel edge selection.
- **Handles Any Arc Complexity**:
  - Works on arcs with any number of vertices (e.g., 2, 8, 16, or 64 chords) as well as complex chamfered angles and polygon closure vertices.
- **Dedicated Toolbar Action**:
  - Available on the *Advanced Digitizing Toolbar* with a dedicated icon featuring the standard QGIS delete badge.

---

### 3. ⚡ Batch Processing Dock Panel (QGIS 3.x & QGIS 4.x)
- Dockable panel on the right sidebar for instant batch processing.
- Automatically processes all vertices of all parts in selected features (`LineString`, `Polygon`, `MultiLineString`, `MultiPolygon`).
- Supports exterior rings as well as all interior hole rings.
- Offers three batch operations:
  - **Batch Fillet**: Rounds all corners across selected features.
  - **Batch Chamfer**: Bevels all corners across selected features.
  - **Batch Corner Restore**: Automatically detects all rounded arcs and bevels across selected features and restores sharp corners.

---

### 4. 🛡️ Edit-Mode Safety & Transactions
- Toolbar action buttons are **automatically enabled only when an active vector layer is in Edit Mode** (`layer.isEditable() == True`).
- If editing is saved or rolled back while a map tool is active, the tool automatically unsets and hides canvas widgets to prevent unintended edits.
- Native Undo/Redo (`Ctrl+Z` / `Ctrl+Y`) support for all interactive and batch operations.

---

## 📦 Compatibility Matrix

| QGIS Version | Platform | UI Framework | Fillet & Chamfer Tool | Corner Restore Tool | Batch Dock Widget | Test Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **QGIS 3.16 LTR** | Windows / Linux / macOS | Qt5 / PyQt5 | ✅ Included | ✅ Included | ✅ Included | ✅ Passed |
| **QGIS 3.28 LTR** | Windows / Linux / macOS | Qt5 / PyQt5 | ✅ Included | ✅ Included | ✅ Included | ✅ Passed |
| **QGIS 3.34 LTR** | Windows / Linux / macOS | Qt5 / PyQt5 | ✅ Included | ✅ Included | ✅ Included | ✅ Passed |
| **QGIS 3.40 LTR** | Windows / Linux / macOS | Qt5 / PyQt5 | ✅ Included | ✅ Included | ✅ Included | ✅ Passed |
| **QGIS 4.0.x** | Windows / Linux / macOS | Qt6 / PyQt6 | *Native QGIS 4 tool* | ✅ Included | ✅ Included | ✅ Passed |

---

## 📥 Installation

### Method 1: Official QGIS Plugin Repository
1. Open QGIS.
2. Go to **Plugins** → **Manage and Install Plugins...**
3. Search for **Fillet, Chamfer & Corner Restore**.
4. Click **Install Plugin**.

### Method 2: Custom Plugin Repository
1. In QGIS, open **Plugins** → **Manage and Install Plugins...** → **Settings**.
2. Under *Plugin Repositories*, click **Add...**.
3. Set Name: `Suprun QGIS Plugins`
4. Set URL: `https://raw.githubusercontent.com/suprun/fillet/master/repo/plugins.xml`
5. Click **OK**, then install the plugin.

### Method 3: Manual Installation (from ZIP)
1. Download `fillet.zip` from [Latest Releases](https://github.com/suprun/fillet/releases/latest).
2. Unzip into your QGIS active profile plugin folder:
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\fillet`
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/fillet`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/fillet`
3. Restart QGIS or enable the plugin in **Plugins Manager**.

---

## 📖 Usage Guide

### 🛠️ Interactive Fillet / Chamfer Workflow
1. Select a Line or Polygon vector layer in the Layers panel.
2. Click **Toggle Editing** (`Ctrl+E` or pencil icon).
3. Click the **Fillet / Chamfer Tool** button on the *Advanced Digitizing Toolbar* or in the *Vector* menu.
4. The floating CAD HUD control appears on the canvas:
   - Choose **Fillet** (enter Radius $R$ and number of Arc Segments) or **Chamfer** (enter Distance $d_1$ and $d_2$).
   - Toggle the **Lock Icon** (locked to click-apply fixed value; unlocked to drag interactively).
5. Hover over any vertex of the feature to view tangent cut markers and live preview.
6. Left-click to commit the fillet or chamfer.

### 📐 Interactive Corner Restore (Unfillet / Unchamfer) Workflow
1. Put your target layer into edit mode.
2. Click the **Corner Restore Tool** button on the *Advanced Digitizing Toolbar*.
3. Click the first straight edge of the corner.
4. Hover over the adjacent second straight edge to see the intersection preview and reconstructed sharp corner.
5. Click the second edge to commit the corner reconstruction. Right-click to cancel at any time.

### ⚡ Batch Processing Workflow
1. Put your target layer into edit mode.
2. Select one or more features using the QGIS selection tool.
3. Click the **Fillet / Chamfer (Batch Processing)** button to open the dock panel.
4. Choose **Fillet**, **Chamfer**, or **Restore Sharp Corners**.
5. Click **Apply to Selected Features**. All corners of the selected features will be processed immediately.

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

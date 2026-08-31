<div align="center">

# Fillet & Chamfer for QGIS 3.x (Interactive & Batch)

<p align="center">
  <img src="icon.png" alt="Fillet & Chamfer Logo" width="96" height="96" />
</p>

**CAD editing toolkit for QGIS with Fillet, Chamfer, Align Feature, Match Edge, Array Along Path, Extract Part, Subtract, Clip, Rotate, Mirror, Scale & Rotate, arrays, topology repair, and batch processing.**

[![QGIS Compatibility](https://img.shields.io/badge/QGIS-3.16%20--%204.99-brightgreen.svg?logo=qgis)](https://plugins.qgis.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%20%7C%203.12-blue.svg?logo=python)](https://python.org)
[![PyQt](https://img.shields.io/badge/UI-PyQt5%20%7C%20PyQt6-orange.svg?logo=qt)](https://riverbankcomputing.com/software/pyqt/)
[![Multi-Version Tests](https://img.shields.io/badge/Tests-5%20QGIS%20Versions%20Passed-success.svg)](#multi-version-testing)
[![Languages](https://img.shields.io/badge/Languages-40%20Locales-blueviolet.svg)](#localization)

</div>

---

## 🌟 Overview

The **Fillet & Chamfer for QGIS 3.x** plugin brings a complete suite of CAD-grade digitizing tools into QGIS:

1. **Interactive Fillet & Chamfer CAD Tool (QGIS 3.x)**: Backports the interactive digitizing workflow introduced in QGIS 4.0 directly into the **QGIS 3.x LTR series** (from QGIS 3.16 to 3.44+), complete with an on-canvas CAD HUD widget.
2. **Two-Line Fillet / Chamfer Tool with Merge (QGIS 3.x & QGIS 4.x)**: Select any two intersecting or non-intersecting line features or segments to connect them with a fillet arc or chamfer bevel, automatically merging geometries and preserving feature attributes.
3. **Interactive Corner Restoration Tool / Unfillet & Unchamfer (QGIS 3.x & QGIS 4.x)**: A dedicated CAD Two-Edge selection tool allowing you to select two adjacent straight edges, remove intermediate arc chords or bevel segments, and reconstruct the exact sharp intersection corner ($V_{\text{sharp}}$).
4. **Interactive CAD 3-Point Rotation Tool (QGIS 3.x & QGIS 4.x)**: Precise CAD rotation tool for selected features using interactive 3-step pivot center, reference baseline, and target angle with angle snap presets and copy mode.
5. **Interactive CAD 2-Point Mirror Tool (QGIS 3.x & QGIS 4.x)**: Interactive CAD mirror tool reflecting selected features across a 2-point symmetry axis line with axis angle snapping (`Free`, `15°`, `45°`, `90° (Ortho)`) and duplicate copy mode.
6. **CAD Scale & Rotate**: Scale and rotate selected features from an origin, reference point, and target point, with exact numeric control and copy mode.
7. **CAD Edge Offset**: Shift a selected edge in Extend or Step mode while keeping adjacent topology coherent.
8. **Feature Array and Circular Array**: Create linear copies along a vector or polar copies around an interactive center and baseline.
9. **Align Feature and Match Edge**: Place an entire selected group using point/edge references, or locally reshape one clicked edge without moving the feature's other vertices.
10. **Array Along Path**: Place an exact count or spaced copies along one clicked path part, with subranges, stable offset side, reverse traversal, and tangent orientation.
11. **Extract Part**: Move or copy individual or pending sets of native multipart geometry parts while preserving attributes and dimensionality.
12. **Subtract Feature and Clip Feature**: Apply safe polygon difference/intersection against one or several cross-layer cutters without changing cutter features.
13. **Divide / Measure Line**: Split lines by count or fixed length, in separate-feature or multipart form.
14. **Ortho Angles**: Orthogonalize polygon or line vertices relative to a selected base edge, optionally preserving area or creating a copy.
15. **Clean & Repair**: Detect duplicate nodes and self-intersections and apply targeted or whole-feature repair.
16. **Explode Line**: Convert eligible polylines to individual segments or multipart segment collections.
17. **Batch Processing Dock Panel**: Round or bevel all eligible vertices across selected features and rings with one action.

---

## 🚀 Key Features

### 1. 🎯 Interactive Fillet & Chamfer Digitizing Tool (QGIS 3.x)
- **On-Canvas CAD HUD Control**: Floating panel on the map canvas providing instant control over radius, distances, and arc segments count.
- **Fillet Mode (Corner Rounding)**:
  - Precise circular arc discretization with customizable **Fillet segments** count ($N$ segments = $N+1$ vertices).
  - Clean analytical interpolation ensuring exact tangent intersection with adjacent edges.
  - Radius `0` keeps or creates a sharp corner represented by one vertex.
- **Chamfer Mode (Corner Beveling)**:
  - Symmetric beveling ($d_1 = d_2$) or independent dual-distance beveling ($d_1 \neq d_2$) with link toggle.
  - Distances `0 / 0` create one sharp vertex; an unlinked `0 / positive` pair creates a literal one-sided chamfer.
- **Lock / Unlock Numeric Mode**:
  - **Locked (Default)**: Click any vertex to instantly apply the exact configured numeric value.
  - **Unlocked**: Move the mouse interactively across the canvas to adjust the radius or distance dynamically in real time.
- **Visual Feedback & Live Snapping**:
  - Tangent snap markers on adjacent segments.
  - Live dashed rubberband preview of the resulting fillet arc or chamfer segment.
- **Full CRS & Units Adaptation**:
  - Automatic dynamic adaptation for **Projected CRS** (meters: 3 decimal places, step 1.0, default 5.0m) and **Geographic CRS** (degrees / EPSG:4326: 6 decimal places, step 0.00005°, default 0.0001°).

---

### 2. 🔄 Two-Line Fillet / Chamfer with Feature Merge (QGIS 3.x & QGIS 4.x)
- Connect any two separate line features or two segments of a closed/open polyline with a fillet curve or chamfer bevel.
- Automatically calculates infinite ray intersections, shortens or extends line segments, and performs seamless topological feature merging.
- A zero radius or zero pair of chamfer distances joins the lines at their exact intersection using one sharp vertex.
- Native integration with QGIS `QgsMergeAttributesDialog` and option to always keep first feature attributes.

---

### 3. 📐 Interactive Corner Restoration / Unfillet & Unchamfer (QGIS 3.x & QGIS 4.x)
- **CAD Two-Edge Selection Workflow**:
  - **Step 1**: Hover over any straight edge $E_1$ adjacent to the corner (highlighted in amber) and left-click to select.
  - **Step 2**: Hover over the second adjacent straight edge $E_2$. The tool computes the infinite ray intersection $V_{\text{sharp}}$, automatically detects all intermediate arc chords or bevel segments, and renders a live rubberband preview of the reconstructed geometry.
  - **Step 3**: Left-click $E_2$ to commit the sharp corner reconstruction into the layer edit history.
  - Right-click or press `Escape` at any time to step back or cancel.

---

### 4. 🧭 Interactive CAD 3-Point Rotation Tool (QGIS 3.x & QGIS 4.x)
- **3-Point CAD Workflow**:
  - **Step 1**: Select pivot / rotation center point with native snapping.
  - **Step 2**: Select reference baseline direction.
  - **Step 3**: Rotate interactively to target angle or enter exact numeric degrees in floating HUD.
- **Angle Snap Steps**: Free, 5°, 15°, 45°, 90°.
- **Copy Mode**: Option to create rotated duplicate features while preserving the original.

---

### 5. 🪞 Interactive CAD 2-Point Mirror Tool (QGIS 3.x & QGIS 4.x)
- **2-Point CAD Workflow**:
  - **Step 1**: Click first point of symmetry mirror axis $P_1$ with native snapping.
  - **Step 2**: Move cursor to position second axis point $P_2$, viewing the live projected symmetry axis line and real-time preview of mirrored geometries.
  - Left-click $P_2$ to apply the mirror reflection.
- **Axis Snap Steps**: Free, 15°, 45°, 90° (Ortho / horizontal & vertical constraint).
- **Copy Mode**: Option to create mirrored duplicate features while preserving the original.

---

### 6. ⚡ Batch Processing Dock Panel (QGIS 3.x & QGIS 4.x)
- Dockable panel in the main window for rapid batch processing.
- Automatically processes all vertices of all parts in selected features (`LineString`, `Polygon`, `MultiLineString`, `MultiPolygon`).
- Supports exterior rings as well as all interior hole rings.
- **Batch Fillet**: Rounds all corners across selected features with the specified radius and segment count.
- **Batch Chamfer**: Bevels all corners across selected features with the specified distances.
- Zero size is accepted consistently; already sharp input remains unchanged and does not create a redundant geometry edit.

---

### 7. 🛡️ Edit-Mode Safety & Native Transactions
- All toolbar action buttons and tools are **automatically enabled only when an active vector layer is in Edit Mode** (`layer.isEditable() == True`).
- If editing is toggled off while a tool is active, the tool automatically unsets and closes on-canvas widgets to prevent unintended changes.
- Full native Undo/Redo (`Ctrl+Z` / `Ctrl+Y`) transaction support for all interactive and batch operations.

### Cross-layer alignment, path, part, and polygon tools

- **Align Feature** moves or copies the entire selected group using point (`S1 → S2 → T1 → T2`) or edge references. `Shift` fits scale, `Ctrl` creates copies, and `F` flips orientation.
- **Match Edge** locally rebuilds one clicked straight edge. A click makes it collinear with Target; `Shift` makes it parallel through the old midpoint, `Ctrl` creates an adjusted copy, and `F` reverses terminal LineString orientation. Adjacent edges are extended or trimmed while every other vertex and selected feature stays fixed.
- **Array Along Path** uses a manual group anchor and only the clicked line/multiline part. The HUD controls Count/Spacing, Whole path/Subrange, offset, and inclusion of the start; `Shift` enables tangent orientation and `Ctrl` reverses traversal.
- **Extract Part** moves a clicked part, copies with `Ctrl`, and builds a pending set with `Shift`; press `Enter` to apply the set.
- **Subtract Feature / Clip Feature** use a shared Target/Cutter workflow. `Shift` accumulates cutters, `Enter` applies their union, and `Ctrl` keeps Target active for a continuous session. Version 1 supports valid XY/Z Polygon and MultiPolygon geometries; M/ZM and native curves are rejected without editing data.
- All six tools use visible-layer snapping, canvas/layer CRS transforms, one atomic QGIS edit command per result, and native Undo/Redo.

### Geometry dimensions and native curves

- Fillet, Chamfer, Batch, Two-Line, Corner Restore, Edge Offset, Ortho Angles, and Clean/Repair preserve finite Z, M, and ZM ordinates. New points receive values interpolated or extrapolated from their source segments; fillet arc ordinates are interpolated between tangent points.
- Rotate, Mirror, Scale & Rotate, Align Feature, Match Edge, Array Along Path, Extract Part, Feature Array, Circular Array, and Divide preserve native `CircularString`, `CompoundCurve`, and `CurvePolygon` geometry where QGIS supports the corresponding transform or substring.
- Operations which rebuild topology manually—Fillet/Chamfer, Batch, Two-Line, Corner Restore, Edge Offset, Ortho Angles, Clean/Repair, and Explode—refuse existing curved geometries with a warning instead of silently segmentizing them.
- Rotate, Scale & Rotate, Circular Array, and Ortho Angles calculate both preview and commit in the map canvas CRS, then transform the accepted result back to the layer CRS.

---

## 📦 Compatibility Matrix

| Tested QGIS build | Test platform | UI framework | Result |
| :--- | :--- | :--- | :---: |
| **3.16.16** | Windows | Qt5 / PyQt5 | ✅ Passed |
| **3.28.2** | Windows | Qt5 / PyQt5 | ✅ Passed |
| **3.34.10** | Windows | Qt5 / PyQt5 | ✅ Passed |
| **3.40.4** | Windows | Qt5 / PyQt5 | ✅ Passed |
| **4.0.2** | Windows | Qt6 / PyQt6 | ✅ Passed |

The declared compatibility range is QGIS 3.16–4.99. Linux and macOS are supported targets, but this release does not claim a completed platform smoke run unless their QGIS Python launchers are supplied explicitly as described below.

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
4. Set URL: `https://raw.githubusercontent.com/suprun/fillet/master/dist/plugins.xml`
5. Click **OK**, then install the plugin.

### Method 3: Manual Installation (from ZIP)
1. Download `fillet.zip` from [Latest Releases](https://github.com/suprun/fillet/releases/latest).
2. Unzip into your QGIS active profile plugin directory:
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\fillet`
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/fillet`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/fillet`
3. Restart QGIS or activate the plugin in the **Plugins Manager**.

---

## 📖 Usage Guide

### 🛠️ 1. Interactive Fillet / Chamfer (QGIS 3.x)
1. Select a Line or Polygon vector layer in the Layers panel.
2. Click **Toggle Editing** (`Ctrl+E` or pencil icon).
3. Click the **Fillet / Chamfer Tool** button on the *Advanced Digitizing Toolbar* or in the *Vector* menu.
4. The floating CAD HUD control appears on the canvas:
   - Choose **Fillet** (enter Radius $R$ and number of Arc Segments) or **Chamfer** (enter Distance $d_1$ and $d_2$).
   - Toggle the **Lock Icon** (locked to click-apply fixed value; unlocked to drag interactively).
5. Hover over any vertex of the feature to view tangent cut markers and live preview.
6. Left-click to commit the fillet or chamfer.

### 📐 2. Interactive Corner Restoration / Unfillet & Unchamfer (QGIS 3.x & QGIS 4.x)
1. Put your target layer into edit mode.
2. Click the **Corner Restore Tool** button on the *Advanced Digitizing Toolbar*.
3. Click the first straight edge $E_1$ adjacent to the rounded or beveled corner.
4. Hover over the second adjacent straight edge $E_2$ to see the intersection preview and reconstructed sharp corner.
5. Click the second edge $E_2$ to commit the corner reconstruction. Right-click or press `Escape` to cancel.

### ⚡ 3. Batch Processing Panel (QGIS 3.x & QGIS 4.x)
1. Put your target layer into edit mode.
2. Select one or more features using the QGIS selection tool.
3. Click the **Fillet / Chamfer (Batch Processing)** button to open the dock panel.
4. Choose **Fillet** or **Chamfer** and configure your parameters.
5. Click **Apply to Selected Features**. All corners of the selected features will be rounded or beveled immediately.

---

## 🧪 Development & Multi-Version Testing

The automated suite covers geometry and Z/M/ZM precision, multipart Two-Line merges, native-curve policy, CRS-consistent preview/commit, transactional rollback, HUD keyboard routing, plugin lifecycle, package import, translation loading, and settings persistence.

To run automated smoke tests across all installed QGIS versions on your machine:

```powershell
python scripts/smoke_test_all_qgis.py
```

Windows QGIS installations are discovered automatically. On Linux, macOS, or a custom installation, pass every tested launcher explicitly so the summary only reports environments that actually ran:

```bash
python scripts/smoke_test_all_qgis.py \
  --no-windows-autodiscovery \
  --qgis-python "QGIS-3.40=/opt/qgis/bin/python-qgis" \
  --qgis-python "QGIS-4.0=/Applications/QGIS.app/Contents/MacOS/bin/python3"
```

### Packaging for Release
To package a clean release ZIP from the explicit runtime manifest (without tests, scripts, translation sources, caches, ignored files, or unrelated repository files):

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

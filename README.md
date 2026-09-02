<div align="center">

# Fillet & Chamfer for QGIS (Interactive & Batch)

<p align="center">
  <img src="icon.png" alt="Fillet & Chamfer Logo" width="96" height="96" />
</p>

**Dedicated CAD digitizing toolkit for QGIS with Interactive Fillet, Chamfer, Two-Line Merge, Corner Restoration (Unfillet/Unchamfer), and Batch Processing.**

[![QGIS Compatibility](https://img.shields.io/badge/QGIS-3.16%20--%204.99-brightgreen.svg?logo=qgis)](https://plugins.qgis.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%20%7C%203.12-blue.svg?logo=python)](https://python.org)
[![PyQt](https://img.shields.io/badge/UI-PyQt5%20%7C%20PyQt6-orange.svg?logo=qt)](https://riverbankcomputing.com/software/pyqt/)
[![Languages](https://img.shields.io/badge/Languages-40%20Locales-blueviolet.svg)](#localization)

</div>

---

## 🌟 Overview

The **Fillet & Chamfer for QGIS** plugin brings precise CAD-grade corner rounding, beveling, restoration, and line-merging tools into QGIS:

1. **Interactive Fillet & Chamfer CAD Tool (QGIS 3.x)**: Backports the interactive digitizing workflow introduced in QGIS 4.0 directly into the **QGIS 3.x LTR series** (from QGIS 3.16 to 3.44+), complete with an on-canvas CAD HUD widget and integrated batch processing for selected features.
2. **Interactive Corner Restoration Tool / Unfillet & Unchamfer (QGIS 3.x & QGIS 4.x)**: A dedicated CAD Two-Edge selection tool allowing you to select two adjacent straight edges, remove intermediate arc chords or bevel segments, and reconstruct the exact sharp intersection corner ($V_{\text{sharp}}$). In QGIS 3.x, it is integrated with the Fillet tool into a convenient drop-down menu on the Advanced Digitizing toolbar.
3. **Two-Line Fillet / Chamfer Tool with Merge (QGIS 3.x & QGIS 4.x)**: Select any two intersecting or non-intersecting line features or segments to connect them with a fillet arc or chamfer bevel, automatically merging geometries and preserving feature attributes.
4. **Batch Processing (QGIS 3.x & QGIS 4.x)**: Round or bevel all eligible vertices across selected polygon and polyline features in a single click directly from the HUD panel (QGIS 3.x) or dedicated Dock widget (QGIS 4.x).

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

### 4. ⚡ Batch Fillet & Chamfer Dock Panel (QGIS 3.x & QGIS 4.x)
- Dockable panel in the main QGIS window.
- Apply uniform Fillet radius or Chamfer distances across all vertices of all currently selected polygon and line features.
- Atomic edit commands ensuring a single clean Undo/Redo step in the edit history.
- Automatically skips unchanged zero-size geometries to avoid redundant transactions.

---

## 🌐 Localization

Full native translations for **40 official QGIS languages**:
- Arabic (`ar`), Bulgarian (`bg`), Catalan (`ca`), Czech (`cs`), Danish (`da`), German (`de`), Greek (`el`), English (`en`), Spanish (`es`), Estonian (`et`), Basque (`eu`), Finnish (`fi`), French (`fr`), Galician (`gl`), Hindi (`hi`), Croatian (`hr`), Hungarian (`hu`), Indonesian (`id`), Italian (`it`), Japanese (`ja`), Korean (`ko`), Lithuanian (`lt`), Latvian (`lv`), Norwegian (`nb`), Dutch (`nl`), Polish (`pl`), Portuguese (`pt`, `pt_BR`), Romanian (`ro`), Slovak (`sk`), Slovenian (`sl`), Serbian (`sr`), Swedish (`sv`), Thai (`th`), Turkish (`tr`), Ukrainian (`uk`), Vietnamese (`vi`), Chinese (`zh`, `zh_CN`, `zh_TW`).

---

## 📄 License

This plugin is open source and distributed under the **MIT License**.

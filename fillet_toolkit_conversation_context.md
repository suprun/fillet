# Fillet Toolkit — Conversation Context for IDE

Date: 2026-08-28  
Repository: `https://github.com/suprun/fillet`  
Branch: `toolkit`

## 1. Goal

Analyze the `toolkit` branch of the QGIS plugin `suprun/fillet`, identify architectural/release issues, and define which additional CAD tools can be added without duplicating the actual logic already present in QGIS 4+ Advanced Digitizing or in the current plugin.

## 2. Repository / branch state

- Repository: `suprun/fillet`
- Default branch: `master`
- Working branch: `toolkit`
- `toolkit` HEAD: `e7eb241913348947d4671f0a465cfbd4c73fd6b9`
- Commit message: `feat: update plugin to v1.0.0.71 with redesigned icon and updated metadata.`
- `toolkit` is 41 commits ahead of `master`, 0 behind.
- Merge base: `99890112ed832fc42292bc260a53ff4da59d2c3c`
- Plugin version: `1.0.0.71`
- QGIS range: `3.16–4.99`

Main files/modules:

- `plugin.py`
- `core/geometry_engine.py`
- `gui/`
- `tests/`
- `scripts/`
- `resources/`
- `i18n/`
- `dist/`

## 3. Existing toolkit tools

The `toolkit` branch already contains or develops:

- Fillet / Chamfer
- Two-Line Fillet / Chamfer
- Corner Restore
- Rotate
- Mirror
- Scale & Rotate
- Edge Offset
- Array
- Explode
- Clean / Repair / duplicate-node cleanup

Relevant map tool/widget modules include:

- `array_canvas_widget.py`
- `array_map_tool.py`
- `clean_duplicate_nodes_map_tool.py`
- `edge_offset_canvas_widget.py`
- `edge_offset_map_tool.py`
- `explode_canvas_widget.py`
- `explode_map_tool.py`
- `mirror_canvas_widget.py`
- `mirror_map_tool.py`
- `rotate_map_tool.py`
- `rotation_canvas_widget.py`
- `scale_rotate_canvas_widget.py`
- `scale_rotate_map_tool.py`
- `two_line_map_tool.py`

# 4. Code-review findings

## P0 — Batch Fillet/Chamfer package-import bug

In `plugin.py`, the normal package import branch does not import:

```python
from .core.geometry_engine import GeometryEngine
```

Later the code calls:

```python
GeometryEngine.batch_apply_geometry(...)
```

QGIS loads the plugin through the package `__init__.py`, so a successful batch operation can reach:

```text
NameError: name 'GeometryEngine' is not defined
```

### Why current tests can miss it

Tests use a top-level import similar to:

```python
from plugin import FilletPlugin
```

This causes relative imports to fail and activates the fallback import path, where `GeometryEngine` is imported. That masks the real QGIS package-loading behavior.

### Required fix

Add:

```python
from .core.geometry_engine import GeometryEngine
```

to the normal package-import branch.

Also add a package/integration test which loads the plugin the same way QGIS does.

Batch edit transactions should additionally be hardened with `try/except`, `destroyEditCommand()` on failure, and checking the return value of `layer.changeGeometry()`.

## P0/P1 — Two-Line multipart handling can be destructive

`SnappingHelper.SegmentMatch` tracks:

- `part_idx`
- `ring_idx`
- `segment_idx`

but `TwoLineMapTool` passes only `segment_idx` into the geometry engine.

The engine currently reduces `QgsMultiLineString` to:

```python
curve.geometryN(0)
```

So part `0` is always processed.

Possible consequences:

- selecting a segment in part > 0 edits the wrong part;
- multipart geometry can be replaced by one `QgsLineString`;
- untouched parts can be discarded.

### Required design

Make Two-Line operations part-aware:

```text
part1_idx
part2_idx
```

or pass extracted selected parts into the engine.

After processing, rebuild the original multipart geometry and preserve all untouched parts.

Explicitly test:

- part > 0;
- two parts of the same feature;
- two different multipart features;
- merge mode;
- delete-original behavior.

This is a release blocker.

## P1 — QGIS 4 signal lifecycle leak

`initGui()` connects:

```python
self.canvas.mapToolSet.connect(self.on_map_tool_changed)
```

but `unload()` conditionally disconnects it only outside QGIS 4.

This can leave callbacks connected after plugin unload/reload under QGIS 4.

### Fix

Disconnect unconditionally inside `try/except`.

## P1/P2 — Z/M and curved geometry fidelity

Several custom operations construct coordinates as:

```python
QgsPoint(x, y)
```

and manually reconstruct `QgsLineString`, `QgsPolygon`, multipart geometries, etc.

Risks:

- Z loss;
- M loss;
- ZM loss;
- curve downgrading;
- loss of `CircularString`, `CompoundCurve`, `CurvePolygon` subtype fidelity.

Add explicit tests for:

- Z
- M
- ZM
- CircularString
- CompoundCurve
- CurvePolygon

## P2 — CRS inconsistency in Rotate / Scale & Rotate

Defining points are captured in canvas/project CRS while geometry transforms can be applied in layer CRS.

If canvas CRS != layer CRS, especially projected ↔ geographic:

- angle can differ;
- Euclidean scale can differ;
- pivot/reference behavior can be inconsistent.

### Better rule

Use one computational CRS consistently.

Preferred designs:

1. transform geometry into project/canvas CRS, perform CAD operation, transform back;

or

2. transform all defining points into layer CRS before calculating transform parameters.

## Testing / CI gaps

Add tests for:

- successful Batch Fillet/Chamfer;
- package import via package / `classFactory`;
- MultiLineString `part_idx > 0`;
- same feature / different parts;
- Z/M/ZM;
- curved geometry;
- canvas CRS != layer CRS;
- QGIS 4 `initGui → unload → reload`;
- native merge-dialog path.

The current `scripts/smoke_test_all_qgis.py` is Windows-oriented and is not equivalent to reproducible cross-platform CI.

## Documentation drift

`metadata.txt` reflects the expanded CAD toolkit better than `README.md`.

README should explicitly document:

- Scale & Rotate
- Edge Offset
- Array
- Explode
- Clean / Repair

The plugin name still emphasizes Fillet & Chamfer although the branch is becoming a broader CAD toolkit.

# 5. Existing QGIS 4+ logic to avoid duplicating

When designing new tools, compare by behavior, not button names.

QGIS 4+ Advanced Digitizing / Advanced Editing already covers, directly or effectively:

- Move Feature
- Copy and Move
- Rotate Feature
- Scale Feature
- linear Copy Features in an Array
- Simplify
- Offset Curve
- Reshape
- Split Features
- Split Parts
- Merge
- Reverse
- Trim / Extend
- Chamfer / Fillet
- vertex editing
- parallel construction
- perpendicular construction
- line extension construction
- X/Y point construction
- circle intersections
- angle / distance / X / Y / Z / M constraints

Therefore avoid tools which only wrap these operations with a different button name.

# 6. Best genuinely new CAD tools

Recommended order:

1. CAD Stretch
2. 2-Point Align
3. Edge Rotate / Set Edge Angle
4. Lengthen / Shorten
5. Array Along Path
6. Polar Array
7. Interactive Orthogonalize / Rectify
8. Divide / Stations
9. Distribute Features
10. Arcify / Fit Arc
11. Shear / Skew

# 7. CAD Stretch — highest priority

## Purpose

Move only vertices captured by a crossing selection window while leaving the rest of the geometry fixed.

This is not equivalent to:

- Move Feature — moves the whole feature;
- Vertex Tool — manual node-selection workflow;
- Reshape — replaces a geometry section with newly captured geometry.

## Suggested workflow

1. Activate `Stretch`.
2. Draw crossing rectangle/polygon.
3. Highlight affected vertices.
4. Pick base point.
5. Pick destination point or enter distance/angle.
6. Move only captured vertices.

Suggested modes:

- crossing rectangle;
- crossing polygon;
- selected features only;
- all editable features;
- topological stretch;
- X-only;
- Y-only;
- free vector;
- distance + angle.

# 8. 2-Point Align

Apply one transform based on correspondence:

```text
P1 → Q1
P2 → Q2
```

The operation may combine:

1. translation;
2. rotation;
3. optional scale.

Scale:

```text
|Q1Q2| / |P1P2|
```

This differs from existing `Scale & Rotate` because Align includes translation as part of the same correspondence transform.

Suggested HUD:

```text
ALIGN

[x] Move
[x] Rotate
[ ] Scale to target

Source 1 → Target 1
Source 2 → Target 2
```

# 9. Edge Rotate / Set Edge Angle

Natural companion to existing `Edge Offset`.

Select one edge and rotate it around:

- first vertex;
- second vertex;
- midpoint.

Then trim/extend neighboring edges to their new intersection.

Modes:

- absolute angle;
- relative delta angle;
- parallel to reference edge;
- perpendicular to reference edge.

This modifies existing geometry, so it is logically different from QGIS's construction constraints for drawing new vertices.

# 10. Lengthen / Shorten

Set an exact line length numerically.

Modes:

- Delta;
- Total;
- Percent.

Endpoint choices:

- nearest;
- start;
- end.

This differs from Trim/Extend, which operates relative to another target geometry.

# 11. Array Along Path

QGIS 4 already has a linear array, so another linear-array tool is not a useful new class.

A path array is different:

1. select source feature(s);
2. select guide line/curve;
3. choose count or spacing;
4. calculate positions by chainage;
5. optionally rotate copies to local path tangent.

Suggested parameters:

```text
Mode:
- Count
- Spacing
- Count + spacing

Rotate to path tangent
Keep original orientation

Start offset
End offset
Normal offset
```

# 12. Polar Array

Circular/radial array.

Parameters:

```text
Center
Count
Total angle
Start angle

Rotate items
Keep orientation
```

Useful for supports, trees, lights, equipment, parking and radial layouts.

# 13. Interactive Orthogonalize / Rectify

The useful new value is the interactive CAD workflow rather than a generic Processing orthogonalization.

Possible modes:

### Corner mode

```text
89.43° → preview 90.00°
```

Click to apply.

### Feature mode

```text
ORTHOGONALIZE

Angle tolerance: 8°
Iterations: Auto

Preserve area as far as possible
Fix first edge
```

Strong use case: building footprints.

# 14. Divide / Stations

Do not add a basic `Break at Point`, because it mostly overlaps Split Features.

Instead implement chainage/station logic.

Examples:

### By count

```text
A────●────●────●────B
```

### By spacing

Insert vertices at regular distances along geometry.

Possible scopes:

- whole feature;
- selected segment;
- selected chain;
- polygon ring.

# 15. Distribute Selected Features

Reposition existing features uniformly without creating copies.

Modes:

- horizontal;
- vertical;
- picked axis;
- along picked line;
- equal center spacing;
- equal gap.

This differs from Array because it does not generate new features.

# 16. Arcify / Fit Arc

Replace a selected polyline chain with true curved geometry.

Possible modes:

- fit through 3 points;
- best-fit selected vertices;
- radius + endpoints;
- tangent to neighboring edges.

This is not Fillet: Fillet creates a tangent corner transition, while Arcify replaces an arbitrary selected chain.

# 17. Shear / Skew

Affine shear of selected geometry along a chosen axis.

Distinct from:

- Move
- Rotate
- Scale
- Mirror

Lower priority but still genuinely new transform logic.

# 18. Tools not recommended

Avoid because their logic is already covered:

- Linear Array
- Move by vector
- Copy by vector
- Generic Rotate
- Generic Scale
- whole-feature parallel offset
- Break at point
- Join touching lines
- Extend to object
- Trim to object
- generic Smooth
- Make Valid
- Remove duplicate nodes
- multipart explode
- draw parallel/perpendicular
- construction extension ray

Lower priority:

### Rectangular Array

Formally different, but logically mostly a two-dimensional composition of linear Array.

### Multiple Parallel Offsets

Mostly repeated Offset Curve behavior, not a fundamentally new edit class.

# 19. Recommended implementation order

First stabilize existing branch:

```text
1. GeometryEngine package import bug
2. Two-Line multipart handling
3. QGIS 4 mapToolSet disconnect
4. Z/M + curved geometry tests
5. CRS consistency
6. package-import / integration CI tests
7. README synchronization
```

Then add:

```text
1. CAD Stretch
2. 2-Point Align
3. Edge Rotate / Set Angle
4. Lengthen
5. Array Along Path
6. Polar Array
7. Interactive Orthogonalize
8. Divide / Stations
```

If only three new tools are selected:

```text
Stretch
Align
Edge Rotate
```

# 20. Suggested conceptual toolbar structure

```text
TRANSFORM
    Move                     [QGIS]
    Rotate                   [QGIS / toolkit CAD]
    Scale                    [QGIS]
    Mirror                   [toolkit]
    Scale & Rotate           [toolkit]
    Align                    [NEW]
    Stretch                  [NEW]

EDGE / CORNER
    Offset Curve             [QGIS]
    Edge Offset              [toolkit]
    Edge Rotate              [NEW]
    Lengthen                 [NEW]
    Trim / Extend            [QGIS]
    Fillet / Chamfer         [QGIS]
    Two-Line Fillet          [toolkit]
    Restore Corner           [toolkit]

ARRAY
    Linear Array             [QGIS 4]
    Array Along Path         [NEW]
    Polar Array              [NEW]

GEOMETRY
    Reshape                  [QGIS]
    Split                    [QGIS]
    Explode                  [toolkit]
    Clean / Repair           [toolkit]
    Orthogonalize            [NEW]
    Divide / Stations        [NEW]
    Arcify                   [NEW]
```

# 21. IDE starting point

Recommended immediate branches/tasks:

```text
fix/package-import-geometry-engine
fix/two-line-multipart
fix/qgis4-signal-lifecycle
test/geometry-fidelity
test/crs-transforms
```

After stabilization, likely first feature branch:

```text
feature/cad-stretch
```

Suggested architecture for new CAD tools:

```text
gui/<tool>_map_tool.py
gui/<tool>_canvas_widget.py
core/geometry_engine.py
tests/test_<tool>.py
resources/icons/<tool>.svg
```

Keep these principles:

- geometry math in `core/geometry_engine.py`;
- UI/state machine in map tools/widgets;
- native QGIS edit commands for undo/redo;
- snapping through existing snapping infrastructure;
- package-import-compatible tests;
- multipart behavior explicit;
- Z/M behavior explicit;
- curved-geometry behavior explicit;
- CRS strategy explicit from the start.

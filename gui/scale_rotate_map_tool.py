# -*- coding: utf-8 -*-
"""
Map tool for interactive CAD 3-Point Scale with Rotation in QGIS.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).

Workflow (Variant 2):
1. Click on map / vertex / edge to set Origin/Pivot Point (P_origin).
2. Click on map / vertex to set Base Reference Point (P_ref).
3. Move cursor to scale and rotate interactively or enter numeric values -> Click / Enter to commit.
"""

import math
from typing import List, Optional, Tuple

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPointLocator,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import (
    QgsMapCanvas,
    QgsMapMouseEvent,
    QgsMapToolEdit,
    QgsRubberBand,
    QgsSnapIndicator,
)
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor, QCursor

# Safe cross-version Qt constants
_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_DashLine = getattr(Qt.PenStyle, "DashLine", getattr(Qt, "DashLine", 2))
_DotLine = getattr(Qt.PenStyle, "DotLine", getattr(Qt, "DotLine", 3))
_LeftButton = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RightButton = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_Key_Escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
_Key_Tab = getattr(Qt.Key, "Key_Tab", getattr(Qt, "Key_Tab", 0x01000001))
_Key_Backspace = getattr(Qt.Key, "Key_Backspace", getattr(Qt, "Key_Backspace", 0x01000003))
_Key_Return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
_Key_Enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))
_Key_Space = getattr(Qt.Key, "Key_Space", getattr(Qt, "Key_Space", 0x20))
_ShiftModifier = getattr(Qt.KeyboardModifier, "ShiftModifier", getattr(Qt, "ShiftModifier", 0x02000000))

try:
    from ..core.geometry_engine import GeometryEngine
    from .scale_rotate_canvas_widget import ScaleRotateCanvasWidget
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from gui.scale_rotate_canvas_widget import ScaleRotateCanvasWidget


class ScaleRotateMapTool(QgsMapToolEdit):
    """
    Interactive CAD Scale with Rotation Map Tool for QGIS 3.x and 4.x.
    3-step reference workflow:
      1. Click / Snap Origin Center (Pivot)
      2. Click / Snap Base Reference Point (Ref)
      3. Move mouse to select Target Scale & Angle (or type in HUD), Click to Confirm.
    """

    STATE_SET_ORIGIN = 1
    STATE_SET_REFERENCE = 2
    STATE_TRANSFORMING = 3

    def __init__(self, canvas: QgsMapCanvas, widget: ScaleRotateCanvasWidget):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget

        self.state = self.STATE_SET_ORIGIN
        self.origin_point: Optional[QgsPointXY] = None
        self.ref_point: Optional[QgsPointXY] = None
        self.current_scale: float = 1.0
        self.current_angle: float = 0.0

        # Snapping indicator
        self.snap_indicator = QgsSnapIndicator(self.canvas)

        # Visual rubberbands
        # 1. Origin Center Marker
        self.origin_marker = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.origin_marker.setIcon(QgsRubberBand.IconType.ICON_CROSS)
        self.origin_marker.setIconSize(12)
        self.origin_marker.setWidth(2)
        self.origin_marker.setColor(QColor(234, 88, 12, 255))  # Amber/orange

        # 2. Baseline Ray (from origin to reference)
        self.baseline_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.baseline_rubberband.setWidth(2)
        if _DashLine is not None:
            self.baseline_rubberband.setLineStyle(_DashLine)
        self.baseline_rubberband.setColor(QColor(79, 70, 229, 220))  # Indigo

        # 3. Target Ray (from origin to current mouse target)
        self.target_ray_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.target_ray_rubberband.setWidth(2)
        if _DotLine is not None:
            self.target_ray_rubberband.setLineStyle(_DotLine)
        self.target_ray_rubberband.setColor(QColor(234, 88, 12, 220))  # Amber

        # 4. Geometry Preview Rubberband
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_rubberband.setWidth(3)
        if _DashLine is not None:
            self.preview_rubberband.setLineStyle(_DashLine)
        self.preview_rubberband.setColor(QColor(16, 185, 129, 230))  # Emerald green
        self.preview_rubberband.setFillColor(QColor(16, 185, 129, 50))

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        # Connect widget signals
        self.widget.scaleChanged.connect(self._on_widget_scale_changed)
        self.widget.angleChanged.connect(self._on_widget_angle_changed)
        self.widget.commitRequested.connect(self.commit_transformation)
        self.widget.resetRequested.connect(self.reset_state)

    def activate(self):
        super().activate()
        self.reset_state()
        self.widget.show_on_canvas()
        from qgis.PyQt.QtCore import QTimer
        QTimer.singleShot(0, self.widget.focus_primary_input)
        QTimer.singleShot(50, self.widget.focus_primary_input)

    def deactivate(self):
        self.widget.save_settings()
        self.widget.hide()
        self.reset_state()
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        for rb in (
            self.origin_marker,
            self.baseline_rubberband,
            self.target_ray_rubberband,
            self.preview_rubberband,
        ):
            if rb:
                rb.reset()
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def reset_state(self):
        """Resets the tool state to Step 1: Set Origin."""
        self.state = self.STATE_SET_ORIGIN
        self.origin_point = None
        self.ref_point = None
        self.current_scale = 1.0
        self.current_angle = 0.0
        self.widget.set_step(ScaleRotateCanvasWidget.STEP_ORIGIN)
        self._clear_visuals()

    def _clear_visuals(self):
        self.origin_marker.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.baseline_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.target_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable():
            return layer
        return None

    def _get_target_features(self, layer: QgsVectorLayer) -> List[QgsFeature]:
        """Returns selected features or empty list."""
        if not layer:
            return []
        return layer.selectedFeatures()

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_visuals()
            return

        # 1. Native snapping
        match = self.canvas.snappingUtils().snapToMap(event.pos())
        self.snap_indicator.setMatch(match)
        map_pt = match.point() if match.isValid() else self.toMapCoordinates(event.pos())

        # 2. State handling
        if self.state == self.STATE_SET_ORIGIN:
            pass

        elif self.state == self.STATE_SET_REFERENCE:
            if self.origin_point:
                self.baseline_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.origin_point, map_pt]),
                    None,
                )

        elif self.state == self.STATE_TRANSFORMING:
            if self.origin_point and self.ref_point:
                self.baseline_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.origin_point, self.ref_point]),
                    None,
                )
                self.target_ray_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.origin_point, map_pt]),
                    None,
                )

                snap_step = self.widget.snap_step
                modifiers = event.modifiers()
                if _ShiftModifier is not None and (modifiers & _ShiftModifier):
                    snap_step = 15.0 if snap_step == 0.0 else snap_step

                calc_scale, calc_angle = GeometryEngine.compute_3point_scale_and_rotation(
                    self.origin_point,
                    self.ref_point,
                    map_pt,
                    snap_step_deg=snap_step if snap_step > 0.0 else None,
                )

                if self.widget.is_scale_locked:
                    self.current_scale = self.widget.scale_factor
                else:
                    self.current_scale = calc_scale
                    self.widget.set_scale(self.current_scale, block_signals=True)

                if self.widget.is_angle_locked:
                    self.current_angle = self.widget.angle
                else:
                    self.current_angle = calc_angle
                    self.widget.set_angle(self.current_angle, block_signals=True)

                self._update_preview(self.current_scale, self.current_angle)

        # Keep focus on HUD panel
        if self.widget:
            from qgis.PyQt.QtWidgets import QApplication
            focused_widget = QApplication.focusWidget()
            is_on_panel = False
            if focused_widget:
                w = focused_widget
                while w is not None:
                    if w == self.widget:
                        is_on_panel = True
                        break
                    w = w.parent()
            if not is_on_panel:
                self.widget.focus_primary_input()

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == _RightButton:
            # Right click steps back or cancels
            if self.state == self.STATE_TRANSFORMING:
                self.state = self.STATE_SET_REFERENCE
                self.ref_point = None
                self.widget.set_step(ScaleRotateCanvasWidget.STEP_REFERENCE)
                self.target_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            elif self.state == self.STATE_SET_REFERENCE:
                self.reset_state()
            else:
                self.reset_state()
            return

        if event.button() != _LeftButton:
            return

        layer = self.current_vector_layer()
        if not layer:
            return

        match = self.canvas.snappingUtils().snapToMap(event.pos())
        map_pt = match.point() if match.isValid() else self.toMapCoordinates(event.pos())

        if self.state == self.STATE_SET_ORIGIN:
            self.origin_point = map_pt
            self.origin_marker.setToGeometry(QgsGeometry.fromPointXY(self.origin_point), None)
            self.state = self.STATE_SET_REFERENCE
            self.widget.set_step(ScaleRotateCanvasWidget.STEP_REFERENCE)

        elif self.state == self.STATE_SET_REFERENCE:
            if self.origin_point and GeometryEngine.distance(self.origin_point, map_pt) > 1e-6:
                self.ref_point = map_pt
                self.baseline_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.origin_point, self.ref_point]),
                    None,
                )
                self.state = self.STATE_TRANSFORMING
                self.widget.set_step(ScaleRotateCanvasWidget.STEP_TARGET)
                self._update_preview(self.current_scale, self.current_angle)

        elif self.state == self.STATE_TRANSFORMING:
            if self.origin_point and self.ref_point:
                snap_step = self.widget.snap_step
                modifiers = event.modifiers()
                if _ShiftModifier is not None and (modifiers & _ShiftModifier):
                    snap_step = 15.0 if snap_step == 0.0 else snap_step

                calc_scale, calc_angle = GeometryEngine.compute_3point_scale_and_rotation(
                    self.origin_point,
                    self.ref_point,
                    map_pt,
                    snap_step_deg=snap_step if snap_step > 0.0 else None,
                )
                if not self.widget.is_scale_locked:
                    self.current_scale = calc_scale
                    self.widget.set_scale(self.current_scale, block_signals=True)
                if not self.widget.is_angle_locked:
                    self.current_angle = calc_angle
                    self.widget.set_angle(self.current_angle, block_signals=True)

            self.commit_transformation()

        # Restore focus to numeric inputs after click
        if self.widget:
            from qgis.PyQt.QtCore import QTimer
            QTimer.singleShot(0, self.widget.focus_primary_input)

    def _on_widget_scale_changed(self, scale_val: float):
        if self.state == self.STATE_TRANSFORMING and self.origin_point:
            self.current_scale = scale_val
            self._update_preview(self.current_scale, self.current_angle)

    def _on_widget_angle_changed(self, angle_val: float):
        if self.state == self.STATE_TRANSFORMING and self.origin_point:
            self.current_angle = angle_val
            self._update_preview(self.current_scale, self.current_angle)

    def _update_preview(self, scale_factor: float, angle_deg_ccw: float):
        """Updates rubberband preview of transformed selected features."""
        layer = self.current_vector_layer()
        if not layer or not self.origin_point:
            return

        features = self._get_target_features(layer)
        if not features:
            self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return

        # CRS Transform from Map Canvas to Layer CRS
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()

        origin_in_layer = self.origin_point
        transform_to_layer: Optional[QgsCoordinateTransform] = None
        transform_to_canvas: Optional[QgsCoordinateTransform] = None

        if canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs:
            transform_to_layer = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            transform_to_canvas = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            origin_in_layer = transform_to_layer.transform(self.origin_point)

        combined_geoms: List[QgsGeometry] = []
        for feat in features:
            geom = feat.geometry()
            if geom.isEmpty() or geom.isNull():
                continue
            transformed_geom = GeometryEngine.scale_and_rotate_geometry(
                geom,
                origin_in_layer,
                scale_factor,
                angle_deg_ccw,
            )
            if transform_to_canvas:
                transformed_geom.transform(transform_to_canvas)
            combined_geoms.append(transformed_geom)

        if combined_geoms:
            display_geom = QgsGeometry.unaryUnion(combined_geoms) if len(combined_geoms) > 1 else combined_geoms[0]
            geom_type = display_geom.type()
            if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
            else:
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.preview_rubberband.setToGeometry(display_geom, None)
        else:
            self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def keyPressEvent(self, event):
        key = event.key()

        # If user types digits or math symbols, redirect to numeric stepper
        if event.text() and (event.text().isdigit() or event.text() in ".-+," or key == _Key_Backspace):
            if self.widget:
                from qgis.PyQt.QtWidgets import QApplication
                focused_widget = QApplication.focusWidget()
                is_on_panel = False
                if focused_widget:
                    w = focused_widget
                    while w is not None:
                        if w == self.widget:
                            is_on_panel = True
                            break
                        w = w.parent()
                if not is_on_panel:
                    self.widget.focus_primary_input()
                    focused = QApplication.focusWidget()
                    if focused:
                        QApplication.sendEvent(focused, event)
                    event.accept()
                    return

        if key == _Key_Escape:
            if self.state == self.STATE_TRANSFORMING:
                self.state = self.STATE_SET_REFERENCE
                self.ref_point = None
                self.widget.set_step(ScaleRotateCanvasWidget.STEP_REFERENCE)
                self.target_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            elif self.state == self.STATE_SET_REFERENCE:
                self.reset_state()
            else:
                self.reset_state()
            event.accept()
            return

        elif key in (_Key_Return, _Key_Enter):
            if self.state == self.STATE_TRANSFORMING:
                self.commit_transformation()
                event.accept()
                return

        elif key == _Key_Tab:
            if self.widget:
                from qgis.PyQt.QtWidgets import QApplication
                focused_widget = QApplication.focusWidget()
                is_on_panel = False
                if focused_widget:
                    w = focused_widget
                    while w is not None:
                        if w == self.widget:
                            is_on_panel = True
                            break
                        w = w.parent()
                if not is_on_panel:
                    self.widget.focus_primary_input()
                    event.accept()
                    return
                else:
                    super().keyPressEvent(event)

        elif key == _Key_Space:
            if self.widget:
                self.widget.toggle_active_lock()
                event.accept()
                return

        else:
            super().keyPressEvent(event)

    def commit_transformation(self):
        """Applies scale and rotation to selected features in a single undoable transaction."""
        layer = self.current_vector_layer()
        if not layer or not self.origin_point:
            self.reset_state()
            return

        features = self._get_target_features(layer)
        if not features:
            self.reset_state()
            return

        scale_val = self.widget.scale_factor if self.widget.is_scale_locked else self.current_scale
        angle_deg = self.widget.angle if self.widget.is_angle_locked else self.current_angle

        if abs(scale_val - 1.0) < 1e-7 and abs(angle_deg) < 1e-7:
            self.reset_state()
            return

        # CRS Transform
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        origin_in_layer = self.origin_point
        if canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            origin_in_layer = transform.transform(self.origin_point)

        is_copy = self.widget.is_copy_mode

        layer.beginEditCommand(self.tr("CAD Scale & Rotate Feature(s)"))
        try:
            if is_copy:
                new_features: List[QgsFeature] = []
                for feat in features:
                    orig_geom = feat.geometry()
                    if orig_geom.isEmpty() or orig_geom.isNull():
                        continue
                    new_geom = GeometryEngine.scale_and_rotate_geometry(
                        orig_geom,
                        origin_in_layer,
                        scale_val,
                        angle_deg,
                    )
                    new_feat = QgsFeature(feat)
                    new_feat.setGeometry(new_geom)
                    new_features.append(new_feat)
                if new_features:
                    layer.addFeatures(new_features)
                    new_fids = [f.id() for f in new_features if f.id() != 0]
                    if new_fids:
                        layer.selectByIds(new_fids)
            else:
                for feat in features:
                    orig_geom = feat.geometry()
                    if orig_geom.isEmpty() or orig_geom.isNull():
                        continue
                    new_geom = GeometryEngine.scale_and_rotate_geometry(
                        orig_geom,
                        origin_in_layer,
                        scale_val,
                        angle_deg,
                    )
                    layer.changeGeometry(feat.id(), new_geom)

            layer.endEditCommand()
        except Exception:
            layer.destroyEditCommand()
            raise

        layer.updateExtents()
        layer.triggerRepaint()
        if hasattr(self.canvas.snappingUtils(), "clearAllLocators"):
            self.canvas.snappingUtils().clearAllLocators()
        self.canvas.refresh()
        self.reset_state()

# -*- coding: utf-8 -*-
"""
Map tool for interactive CAD 3-Point Rotation in QGIS.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).

Workflow (Variant 1):
1. Click on map / vertex / edge to set Pivot Point (P_center).
2. Click on map / vertex to set Reference Direction (P_ref).
3. Move cursor to rotate interactively or enter numeric angle -> Click / Enter to commit.
"""

import math
from typing import List, Optional, Tuple

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPointLocator,
    QgsPointXY,
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
_Key_Shift = getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020))
_ShiftModifier = getattr(Qt.KeyboardModifier, "ShiftModifier", getattr(Qt, "ShiftModifier", 0x02000000))

try:
    from ..core.geometry_engine import GeometryEngine
    from .gui_utils import (
        checked_edit_command,
        confirm_features_in_canvas_extent,
        require_edit_success,
        transform_geometry_copy,
    )
    from .rotation_canvas_widget import RotationCanvasWidget
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from gui.gui_utils import (
        checked_edit_command,
        confirm_features_in_canvas_extent,
        require_edit_success,
        transform_geometry_copy,
    )
    from gui.rotation_canvas_widget import RotationCanvasWidget


class RotateMapTool(QgsMapToolEdit):
    """
    Interactive CAD Rotation Map Tool for QGIS 3.x and 4.x.
    3-step workflow:
      1. Click / Snap Pivot Center
      2. Click / Snap Baseline Reference Point
      3. Move mouse to select Target Angle (or type numeric angle in HUD), Click to Confirm.
    """

    STATE_SET_PIVOT = 1
    STATE_SET_REFERENCE = 2
    STATE_ROTATING = 3

    def __init__(
        self,
        canvas: QgsMapCanvas,
        widget: RotationCanvasWidget,
        iface=None,
    ):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.iface = iface

        self.state = self.STATE_SET_PIVOT
        self.pivot_point: Optional[QgsPointXY] = None
        self.ref_point: Optional[QgsPointXY] = None
        self.current_angle: float = 0.0
        self._last_mouse_angle_rad: Optional[float] = None
        self._accumulated_angle_deg: float = 0.0

        # Snapping indicator
        self.snap_indicator = QgsSnapIndicator(self.canvas)

        # Visual rubberbands
        # 1. Pivot Center Marker
        self.pivot_marker = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.pivot_marker.setIcon(QgsRubberBand.IconType.ICON_CROSS)
        self.pivot_marker.setIconSize(12)
        self.pivot_marker.setWidth(2)
        self.pivot_marker.setColor(QColor(234, 88, 12, 255))  # Amber/orange

        # 2. Baseline Ray (from pivot to reference)
        self.baseline_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.baseline_rubberband.setWidth(2)
        if _DashLine is not None:
            self.baseline_rubberband.setLineStyle(_DashLine)
        self.baseline_rubberband.setColor(QColor(79, 70, 229, 220))  # Indigo

        # 3. Target Ray (from pivot to current mouse target)
        self.target_ray_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.target_ray_rubberband.setWidth(2)
        if _DotLine is not None:
            self.target_ray_rubberband.setLineStyle(_DotLine)
        self.target_ray_rubberband.setColor(QColor(234, 88, 12, 220))  # Amber

        # 4. Angle Sector Arc
        self.angle_arc_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.angle_arc_rubberband.setWidth(2)
        self.angle_arc_rubberband.setColor(QColor(245, 158, 11, 220))  # Light Amber

        # 5. Geometry Preview Rubberband
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_rubberband.setWidth(3)
        if _DashLine is not None:
            self.preview_rubberband.setLineStyle(_DashLine)
        self.preview_rubberband.setColor(QColor(37, 99, 235, 230))  # Blue
        self.preview_rubberband.setFillColor(QColor(59, 130, 246, 50))

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        # Connect widget signals
        self.widget.angleChanged.connect(self._on_widget_angle_changed)
        self.widget.commitRequested.connect(self.commit_rotation)
        self.widget.resetRequested.connect(self.reset_state)

    def activate(self):
        super().activate()
        self.reset_state()
        self.widget.show_on_canvas()
        from qgis.PyQt.QtCore import QTimer
        QTimer.singleShot(0, self.widget.focus_angle_input)
        QTimer.singleShot(50, self.widget.focus_angle_input)

    def deactivate(self):
        if self.widget:
            self.widget.set_shift_override(False)
            self.widget.save_settings()
            self.widget.hide()
        self.reset_state()
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        for rb in (
            self.pivot_marker,
            self.baseline_rubberband,
            self.target_ray_rubberband,
            self.angle_arc_rubberband,
            self.preview_rubberband,
        ):
            if rb:
                rb.reset()
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def reset_state(self):
        """Resets the tool state to Step 1: Set Pivot."""
        self.state = self.STATE_SET_PIVOT
        self.pivot_point = None
        self.ref_point = None
        self.current_angle = 0.0
        self._last_mouse_angle_rad = None
        self._accumulated_angle_deg = 0.0
        self.widget.set_step(RotationCanvasWidget.STEP_PIVOT)
        self._clear_visuals()

    def _clear_visuals(self):
        self.pivot_marker.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.baseline_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.target_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.angle_arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
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
        if self.state == self.STATE_SET_PIVOT:
            pass

        elif self.state == self.STATE_SET_REFERENCE:
            if self.pivot_point:
                self.baseline_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.pivot_point, map_pt]),
                    None,
                )

                if self.widget.is_angle_locked:
                    dx = map_pt.x() - self.pivot_point.x()
                    dy = map_pt.y() - self.pivot_point.y()
                    dist = math.hypot(dx, dy)
                    if dist > 1e-6:
                        base_rad = math.atan2(dy, dx)
                        rot_rad = base_rad + math.radians(self.widget.angle)
                        target_pt = QgsPointXY(
                            self.pivot_point.x() + dist * math.cos(rot_rad),
                            self.pivot_point.y() + dist * math.sin(rot_rad),
                        )
                        self.target_ray_rubberband.setToGeometry(
                            QgsGeometry.fromPolylineXY([self.pivot_point, target_pt]),
                            None,
                        )
                        self._update_preview(self.widget.angle)
                        self._update_angle_arc(target_pt, self.widget.angle, base_point=map_pt)
                else:
                    self.target_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                    self.angle_arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                    self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

        elif self.state == self.STATE_ROTATING:
            if self.pivot_point and self.ref_point:
                self.baseline_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.pivot_point, self.ref_point]),
                    None,
                )
                self.target_ray_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.pivot_point, map_pt]),
                    None,
                )

                if not self.widget.is_angle_locked:
                    dx = map_pt.x() - self.pivot_point.x()
                    dy = map_pt.y() - self.pivot_point.y()
                    if math.hypot(dx, dy) > 1e-6:
                        cur_rad = math.atan2(dy, dx)
                        if self._last_mouse_angle_rad is not None:
                            d_rad = (cur_rad - self._last_mouse_angle_rad + math.pi) % (2.0 * math.pi) - math.pi
                            self._accumulated_angle_deg += math.degrees(d_rad)
                        else:
                            base_rad = math.atan2(self.ref_point.y() - self.pivot_point.y(), self.ref_point.x() - self.pivot_point.x())
                            d_rad = (cur_rad - base_rad + math.pi) % (2.0 * math.pi) - math.pi
                            self._accumulated_angle_deg = math.degrees(d_rad)
                        self._last_mouse_angle_rad = cur_rad

                    raw_angle = self._accumulated_angle_deg
                    shift_pressed = bool(_ShiftModifier is not None and (event.modifiers() & _ShiftModifier))
                    eff_snap = self.widget.get_effective_snap_step(shift_pressed)

                    if eff_snap is not None and eff_snap > 0.0:
                        angle_deg = round(raw_angle / eff_snap) * eff_snap
                    else:
                        angle_deg = raw_angle

                    self.current_angle = angle_deg
                    self.widget.set_angle(angle_deg, block_signals=True)
                else:
                    self.current_angle = self.widget.angle

                self._update_preview(self.current_angle)
                self._update_angle_arc(map_pt, self.current_angle)

        # Keep focus on the HUD panel's numeric stepper if focus moved away
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
                self.widget.focus_angle_input()

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == _RightButton:
            # Right click steps back or cancels
            if self.state == self.STATE_ROTATING:
                self.state = self.STATE_SET_REFERENCE
                self.ref_point = None
                self.widget.set_step(RotationCanvasWidget.STEP_REFERENCE)
                self.target_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.angle_arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
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

        if self.state == self.STATE_SET_PIVOT:
            target_features = self._get_target_features(layer)
            if not confirm_features_in_canvas_extent(self.canvas, layer, target_features, self.tr("CAD Обертання")):
                return
            self.pivot_point = map_pt
            self.pivot_marker.setToGeometry(QgsGeometry.fromPointXY(self.pivot_point), None)
            self.state = self.STATE_SET_REFERENCE
            self.widget.set_step(RotationCanvasWidget.STEP_REFERENCE)

        elif self.state == self.STATE_SET_REFERENCE:
            if self.pivot_point and GeometryEngine.distance(self.pivot_point, map_pt) > 1e-6:
                self.ref_point = map_pt
                self.baseline_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.pivot_point, self.ref_point]),
                    None,
                )
                if self.widget.is_angle_locked:
                    self.commit_rotation()
                else:
                    self.state = self.STATE_ROTATING
                    self.widget.set_step(RotationCanvasWidget.STEP_ROTATING)
                    dx = self.ref_point.x() - self.pivot_point.x()
                    dy = self.ref_point.y() - self.pivot_point.y()
                    self._last_mouse_angle_rad = math.atan2(dy, dx)
                    self._accumulated_angle_deg = 0.0
                    self.current_angle = 0.0
                    self._update_preview(self.current_angle)

        elif self.state == self.STATE_ROTATING:
            if not self.widget.is_angle_locked and self.pivot_point and self.ref_point:
                # Update angle one last time with current map_pt before committing
                dx = map_pt.x() - self.pivot_point.x()
                dy = map_pt.y() - self.pivot_point.y()
                if math.hypot(dx, dy) > 1e-6:
                    cur_rad = math.atan2(dy, dx)
                    if self._last_mouse_angle_rad is not None:
                        d_rad = (cur_rad - self._last_mouse_angle_rad + math.pi) % (2.0 * math.pi) - math.pi
                        self._accumulated_angle_deg += math.degrees(d_rad)
                    self._last_mouse_angle_rad = cur_rad

                raw_angle = self._accumulated_angle_deg
                shift_pressed = bool(_ShiftModifier is not None and (event.modifiers() & _ShiftModifier))
                eff_snap = self.widget.get_effective_snap_step(shift_pressed)
                if eff_snap is not None and eff_snap > 0.0:
                    angle_deg = round(raw_angle / eff_snap) * eff_snap
                else:
                    angle_deg = raw_angle
                self.current_angle = angle_deg
                self.widget.set_angle(angle_deg, block_signals=True)

            self.commit_rotation()

        # Always restore focus to the numeric stepper after mouse click
        if self.widget:
            from qgis.PyQt.QtCore import QTimer
            QTimer.singleShot(0, self.widget.focus_angle_input)

    def _on_widget_angle_changed(self, angle: float):
        if self.state == self.STATE_ROTATING and self.pivot_point:
            self.current_angle = angle
            self._accumulated_angle_deg = angle
            self._update_preview(self.current_angle)
            if self.ref_point:
                base_rad = math.atan2(self.ref_point.y() - self.pivot_point.y(), self.ref_point.x() - self.pivot_point.x())
                r = GeometryEngine.distance(self.pivot_point, self.ref_point)
                target_rad = base_rad + math.radians(angle)
                target_pt = QgsPointXY(
                    self.pivot_point.x() + r * math.cos(target_rad),
                    self.pivot_point.y() + r * math.sin(target_rad),
                )
                self.target_ray_rubberband.setToGeometry(
                    QgsGeometry.fromPolylineXY([self.pivot_point, target_pt]),
                    None,
                )
                self._update_angle_arc(target_pt, self.current_angle)

    def _update_preview(self, angle_deg_ccw: float):
        """Updates rubberband preview of rotated selected features."""
        layer = self.current_vector_layer()
        if not layer or not self.pivot_point:
            return

        features = self._get_target_features(layer)
        if not features:
            self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return

        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()

        combined_geoms: List[QgsGeometry] = []
        try:
            for feat in features:
                geom = feat.geometry()
                if geom.isEmpty() or geom.isNull():
                    continue
                canvas_geom = transform_geometry_copy(geom, layer_crs, canvas_crs)
                rotated_geom = GeometryEngine.rotate_geometry(
                    canvas_geom,
                    self.pivot_point,
                    angle_deg_ccw,
                )
                combined_geoms.append(rotated_geom)
        except (RuntimeError, TypeError):
            self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return

        if combined_geoms:
            # Combine all for display
            display_geom = QgsGeometry.unaryUnion(combined_geoms) if len(combined_geoms) > 1 else combined_geoms[0]
            geom_type = display_geom.type()
            if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
            else:
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.preview_rubberband.setToGeometry(display_geom, None)
        else:
            self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def _update_angle_arc(self, target_pt: QgsPointXY, angle_deg: float, base_point: Optional[QgsPointXY] = None):
        """Draws an arc from reference direction to target direction."""
        ref_pt = base_point or self.ref_point
        if not self.pivot_point or not ref_pt:
            return

        r = min(
            GeometryEngine.distance(self.pivot_point, ref_pt),
            GeometryEngine.distance(self.pivot_point, target_pt),
        )
        if r < 1e-4:
            self.angle_arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
            return

        base_angle_rad = math.atan2(ref_pt.y() - self.pivot_point.y(), ref_pt.x() - self.pivot_point.x())
        delta_rad = math.radians(angle_deg)

        num_segments = max(4, int(abs(angle_deg) / 5.0))
        pts: List[QgsPointXY] = []
        for i in range(num_segments + 1):
            t = i / float(num_segments)
            cur_a = base_angle_rad + t * delta_rad
            x = self.pivot_point.x() + (r * 0.7) * math.cos(cur_a)
            y = self.pivot_point.y() + (r * 0.7) * math.sin(cur_a)
            pts.append(QgsPointXY(x, y))

        if len(pts) >= 2:
            self.angle_arc_rubberband.setToGeometry(QgsGeometry.fromPolylineXY(pts), None)
        else:
            self.angle_arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)

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
                    self.widget.focus_angle_input()
                    focused = QApplication.focusWidget()
                    if focused:
                        QApplication.sendEvent(focused, event)
                    event.accept()
                    return

        if key == _Key_Escape:
            if self.state == self.STATE_ROTATING:
                self.state = self.STATE_SET_REFERENCE
                self.ref_point = None
                self.widget.set_step(RotationCanvasWidget.STEP_REFERENCE)
                self.target_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.angle_arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            elif self.state == self.STATE_SET_REFERENCE:
                self.reset_state()
            else:
                self.reset_state()
            event.accept()
            return

        elif key in (_Key_Return, _Key_Enter):
            if self.state == self.STATE_ROTATING or (self.pivot_point and self.widget.is_angle_locked):
                self.commit_rotation()
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
                    self.widget.focus_angle_input()
                    event.accept()
                    return
                else:
                    super().keyPressEvent(event)

        elif key == _Key_Space:
            if self.widget:
                self.widget.toggle_active_lock()
                event.accept()
                return

        elif key == _Key_Shift:
            if self.widget:
                self.widget.set_shift_override(True)

        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        key = event.key()
        if key == _Key_Shift:
            if self.widget:
                self.widget.set_shift_override(False)
        super().keyReleaseEvent(event)

    def commit_rotation(self):
        """Applies rotation to selected features in a single undoable transaction."""
        layer = self.current_vector_layer()
        if not layer or not self.pivot_point:
            self.reset_state()
            return

        features = self._get_target_features(layer)
        if not features:
            self.reset_state()
            return

        angle_deg = self.widget.angle if self.widget.is_angle_locked else self.current_angle
        if abs(angle_deg) < 1e-7:
            self.reset_state()
            return

        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        is_copy = self.widget.is_copy_mode

        try:
            new_features: List[QgsFeature] = []
            geometry_changes = []
            for feat in features:
                orig_geom = feat.geometry()
                if orig_geom.isEmpty() or orig_geom.isNull():
                    continue
                canvas_geom = transform_geometry_copy(orig_geom, layer_crs, canvas_crs)
                rotated_canvas_geom = GeometryEngine.rotate_geometry(
                    canvas_geom,
                    self.pivot_point,
                    angle_deg,
                )
                new_geom = transform_geometry_copy(rotated_canvas_geom, canvas_crs, layer_crs)
                if is_copy:
                    new_feat = QgsFeature(feat)
                    new_feat.setGeometry(new_geom)
                    new_features.append(new_feat)
                else:
                    geometry_changes.append((feat.id(), new_geom))

            with checked_edit_command(layer, self.tr("CAD Rotate Feature(s)")):
                if is_copy and new_features:
                    require_edit_success(
                        layer.addFeatures(new_features),
                        self.tr("Не вдалося додати повернуті копії."),
                    )
                else:
                    for feature_id, new_geom in geometry_changes:
                        require_edit_success(
                            layer.changeGeometry(feature_id, new_geom),
                            self.tr("Не вдалося змінити геометрію об'єкта."),
                        )

            if is_copy:
                new_fids = [feature.id() for feature in new_features if feature.id() != 0]
                if new_fids:
                    layer.selectByIds(new_fids)
        except (RuntimeError, TypeError) as error:
            if self.iface and hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushWarning(self.tr("Помилка"), str(error))
            return

        layer.updateExtents()
        layer.triggerRepaint()
        if hasattr(self.canvas.snappingUtils(), "clearAllLocators"):
            self.canvas.snappingUtils().clearAllLocators()
        self.canvas.refresh()
        self.reset_state()

# -*- coding: utf-8 -*-
"""
Map tool for interactive Fillet & Chamfer editing in QGIS.
Supports on-canvas CAD HUD widget, two-step CAD interaction model (QGIS 4.0 style),
native QgsSnapIndicator system snapping, tangent touch points visualization,
live preview with polygon transparency, and full keyboard navigation (Tab, Enter, Escape, Space).
"""

from typing import Optional, Union

from qgis.core import (
    Qgis,
    QgsGeometry,
    QgsPointLocator,
    QgsPointXY,
    QgsSettings,
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
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QApplication

# Safe cross-version Qt5 / Qt6 constants
_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_DashLine = getattr(Qt.PenStyle, "DashLine", getattr(Qt, "DashLine", 2))
_LeftButton = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RightButton = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_Key_Backspace = getattr(Qt.Key, "Key_Backspace", getattr(Qt, "Key_Backspace", 0x01000003))
_Key_Return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
_Key_Enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))
_Key_Escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
_Key_Tab = getattr(Qt.Key, "Key_Tab", getattr(Qt, "Key_Tab", 0x01000001))
_Key_Space = getattr(Qt.Key, "Key_Space", getattr(Qt, "Key_Space", 0x20))
_Key_Shift = getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020))
_ShiftModifier = getattr(Qt.KeyboardModifier, "ShiftModifier", getattr(Qt, "ShiftModifier", 0x02000000))

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import SegmentMatch, SnappingHelper, VertexMatch
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import SegmentMatch, SnappingHelper, VertexMatch
from .canvas_widget import FilletCanvasWidget
from .settings_widget import FilletSettingsWidget


class FilletMapTool(QgsMapToolEdit):
    """Interactive Map Tool for filleting and chamfering vertices in QGIS 4.0 CAD style."""

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    STATE_HOVER = "hover"
    STATE_ADJUSTING = "adjusting"

    def __init__(self, canvas: QgsMapCanvas, widget: Union[FilletCanvasWidget, FilletSettingsWidget]):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget

        self.state = self.STATE_HOVER
        self.current_match: Optional[VertexMatch] = None
        self.first_segment_match: Optional[SegmentMatch] = None
        self.current_segment_match: Optional[SegmentMatch] = None
        self.preview_geom: Optional[QgsGeometry] = None

        # 1. Native QGIS system snapping indicator (100% native styling and snapping engine integration)
        self.snap_indicator = QgsSnapIndicator(self.canvas)

        # 2. Tangent / touch point markers (T1, T2 rendered in map canvas CRS)
        self.tangent_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.tangent_rubberband.setIcon(QgsRubberBand.IconType.ICON_CROSS)
        self.tangent_rubberband.setIconSize(10)
        self.tangent_rubberband.setWidth(2)
        self.tangent_rubberband.setColor(QColor(255, 140, 0, 240))

        # 3. Geometry preview rubberband (configured dynamically for Polygon / Line)
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_rubberband.setWidth(4)
        if _DashLine is not None:
            self.preview_rubberband.setLineStyle(_DashLine)

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))
        self.widget.parametersChanged.connect(self._update_preview)
        if hasattr(self.widget, "commitRequested"):
            self.widget.commitRequested.connect(self._commit_change)
        if hasattr(self.widget, "resetRequested"):
            self.widget.resetRequested.connect(self._cancel_operation)

    def activate(self):
        super().activate()
        layer = self.current_vector_layer()
        if layer and hasattr(self.widget, "adapt_to_crs"):
            self.widget.adapt_to_crs(layer.crs())
        self.state = self.STATE_HOVER
        self._clear_preview()
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.show_on_canvas()
            QTimer.singleShot(0, self.widget.focus_primary_input)
            QTimer.singleShot(50, self.widget.focus_primary_input)

    def deactivate(self):
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.set_shift_override(False)
            self.widget.hide()
        self.state = self.STATE_HOVER
        self._clear_preview()
        super().deactivate()

    def cleanup(self):
        """Cleans up rubberbands, indicators, and disconnected signals."""
        self.deactivate()
        try:
            self.widget.parametersChanged.disconnect(self._update_preview)
        except (TypeError, RuntimeError):
            pass  # nosec B110
        if hasattr(self.widget, "commitRequested"):
            try:
                self.widget.commitRequested.disconnect(self._commit_change)
            except (TypeError, RuntimeError):
                pass  # nosec B110
        if hasattr(self.widget, "resetRequested"):
            try:
                self.widget.resetRequested.disconnect(self._cancel_operation)
            except (TypeError, RuntimeError):
                pass  # nosec B110

        if hasattr(self, "snap_indicator") and self.snap_indicator:
            self.snap_indicator.setVisible(False)
            del self.snap_indicator
            self.snap_indicator = None

        if hasattr(self, "tangent_rubberband") and self.tangent_rubberband:
            self.tangent_rubberband.reset()
            del self.tangent_rubberband
            self.tangent_rubberband = None

        if hasattr(self, "preview_rubberband") and self.preview_rubberband:
            self.preview_rubberband.reset()
            del self.preview_rubberband
            self.preview_rubberband = None

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable():
            return layer
        return None

    def _is_current_parameter_locked(self) -> bool:
        if isinstance(self.widget, FilletCanvasWidget):
            if self.widget.mode == FilletCanvasWidget.MODE_FILLET:
                return self.widget.is_radius_locked
            elif self.widget.mode == FilletCanvasWidget.MODE_CHAMFER:
                if self.widget.is_linked:
                    return self.widget.is_dist1_locked
                else:
                    return self.widget.is_dist1_locked and self.widget.is_dist2_locked
            else:
                return True
        return True

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_preview()
            return

        shift_pressed = bool(_ShiftModifier is not None and (event.modifiers() & _ShiftModifier))
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.set_shift_override(shift_pressed)

        mode = (
            self.widget.mode
            if isinstance(self.widget, FilletCanvasWidget)
            else FilletCanvasWidget.MODE_FILLET
        )
        map_point = event.mapPoint()
        self.last_mouse_point = map_point

        # Regular FILLET and CHAMFER vertex hover / adjust workflow
        if self.state == self.STATE_HOVER:
            match = SnappingHelper.find_vertex_at_position(layer, self.canvas, map_point)
            if match:
                self.current_match = match
                self._show_vertex_marker(layer, match)
                if self._is_current_parameter_locked():
                    self._update_preview()
                else:
                    self.preview_rubberband.reset()
                    self.tangent_rubberband.reset()
            else:
                self._clear_preview()

        elif self.state == self.STATE_ADJUSTING:
            snap_match = self.canvas.snappingUtils().snapToMap(event.pos())
            if snap_match.isValid():
                map_point = snap_match.point()
                self.snap_indicator.setMatch(snap_match)
                self.snap_indicator.setVisible(True)
            else:
                map_point = event.mapPoint()
                self.snap_indicator.setVisible(False)
            self.last_mouse_point = map_point

            if self.current_match and isinstance(self.widget, FilletCanvasWidget):
                self._update_values_from_point(layer, map_point, shift_pressed)
            self._update_preview()

        # Keep focus on the HUD panel's numeric stepper if focus moved away
        if isinstance(self.widget, FilletCanvasWidget):
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

    def _update_values_from_point(self, layer: QgsVectorLayer, map_point: QgsPointXY, shift_pressed: bool = False):
        """Calculates distance/radius from cursor point and updates active parameters in HUD widget."""
        if not self.current_match or not isinstance(self.widget, FilletCanvasWidget):
            return

        is_geo = layer.crs().isGeographic() if layer and layer.crs().isValid() else False
        min_limit = 1e-6 if is_geo else 0.0001
        min_clamp = 1e-6 if is_geo else 0.001

        layer_point = self.toLayerCoordinates(layer, map_point)
        dist = GeometryEngine.distance(self.current_match.point, layer_point)
        p_prev, v, p_next = GeometryEngine.get_adjacent_points(
            self.current_match.geometry,
            self.current_match.part_idx,
            self.current_match.ring_idx,
            self.current_match.vertex_idx,
        )

        if self.widget.mode == FilletCanvasWidget.MODE_FILLET:
            if p_prev and v and p_next:
                max_r = GeometryEngine.max_fillet_radius(p_prev, v, p_next)
                if max_r > 0:
                    dist = min(dist, max_r * 0.9999)
            rounded_dist = max(min_limit, round(dist, 6 if is_geo else (4 if dist < 1.0 else 3)))
            if not self.widget.is_radius_locked:
                self.widget.set_radius(rounded_dist, block_signals=True)
        elif self.widget.mode == FilletCanvasWidget.MODE_CHAMFER:
            is_eff_linked = self.widget.get_effective_is_linked(shift_pressed)
            if p_prev and v and p_next:
                u1x, u1y, len1 = GeometryEngine.normalize_vector(p_prev.x() - v.x(), p_prev.y() - v.y())
                u2x, u2y, len2 = GeometryEngine.normalize_vector(p_next.x() - v.x(), p_next.y() - v.y())
                if is_eff_linked:
                    # Isosceles chamfer: strictly bounded by shorter edge
                    max_d = min(len1, len2) * 0.9999
                    dist = min(dist, max_d)
                    rounded_dist = max(min_limit, round(dist, 6 if is_geo else (4 if dist < 1.0 else 3)))
                    if not self.widget.is_dist1_locked:
                        self.widget.set_distance1(rounded_dist, block_signals=True)
                    if not self.widget.is_dist2_locked:
                        self.widget.set_distance2(rounded_dist, block_signals=True)
                else:
                    wx = layer_point.x() - v.x()
                    wy = layer_point.y() - v.y()
                    proj1 = wx * u1x + wy * u1y
                    proj2 = wx * u2x + wy * u2y
                    d1 = min(len1 * 0.9999, max(min_clamp, abs(proj1)))
                    d2 = min(len2 * 0.9999, max(min_clamp, abs(proj2)))
                    if not self.widget.is_dist1_locked:
                        self.widget.set_distance1(round(d1, 6 if is_geo else (4 if d1 < 1.0 else 3)), block_signals=True)
                    if not self.widget.is_dist2_locked:
                        self.widget.set_distance2(round(d2, 6 if is_geo else (4 if d2 < 1.0 else 3)), block_signals=True)
            else:
                rounded_dist = max(min_limit, round(dist, 6 if is_geo else (4 if dist < 1.0 else 3)))
                if not self.widget.is_dist1_locked:
                    self.widget.set_distance1(rounded_dist, block_signals=True)
                if not self.widget.is_dist2_locked:
                    self.widget.set_distance2(rounded_dist, block_signals=True)

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            return

        mode = (
            self.widget.mode
            if isinstance(self.widget, FilletCanvasWidget)
            else FilletCanvasWidget.MODE_FILLET
        )

        if event.button() == _LeftButton:
            if self.state == self.STATE_HOVER:
                map_point = event.mapPoint()
                match = SnappingHelper.find_vertex_at_position(layer, self.canvas, map_point)
                if match:
                    self.current_match = match
                    self._show_vertex_marker(layer, match)

                    # If parameters are locked, single click can commit directly
                    if self._is_current_parameter_locked():
                        self._update_preview()
                        self._commit_change()
                    else:
                        self.state = self.STATE_ADJUSTING
                        # Calculate value directly from cursor position at first click
                        self._update_values_from_point(layer, map_point)
                        self._update_preview()

            elif self.state == self.STATE_ADJUSTING:
                snap_match = self.canvas.snappingUtils().snapToMap(event.pos())
                if snap_match.isValid():
                    map_point = snap_match.point()
                else:
                    map_point = event.mapPoint()
                if self.current_match and isinstance(self.widget, FilletCanvasWidget):
                    self._update_values_from_point(layer, map_point)
                    self._update_preview()
                # Second click commits the modification (Two-step CAD workflow)
                self._commit_change()

            # Always restore focus to the primary numeric stepper after mouse click
            if isinstance(self.widget, FilletCanvasWidget):
                QTimer.singleShot(0, self.widget.focus_primary_input)

        elif event.button() == _RightButton:
            # Right click cancels active adjustment or clears preview
            self._cancel_operation()

    def _show_vertex_marker(self, layer: QgsVectorLayer, match: VertexMatch):
        """Displays the native QGIS system snapping indicator on vertex."""
        map_point = self.toMapCoordinates(layer, match.point)
        loc_match = QgsPointLocator.Match(
            QgsPointLocator.Type.Vertex,
            layer,
            match.fid,
            0.0,
            map_point,
            match.vertex_idx,
        )
        self.snap_indicator.setMatch(loc_match)
        self.snap_indicator.setVisible(True)

    def _update_preview(self):
        if not self.current_match or not self.isActive():
            return

        match = self.current_match
        layer = self.current_vector_layer()
        if not layer:
            return

        mode = (
            self.widget.mode
            if isinstance(self.widget, FilletCanvasWidget)
            else FilletCanvasWidget.MODE_FILLET
        )

        t1, t2 = None, None

        if mode == FilletCanvasWidget.MODE_FILLET:
            radius = self.widget.radius
            segments = self.widget.segments_count
            new_geom = GeometryEngine.apply_fillet_to_geometry(
                match.geometry,
                part_idx=match.part_idx,
                ring_idx=match.ring_idx,
                vertex_idx=match.vertex_idx,
                radius=radius,
                segments_count=segments,
            )
            t1, t2 = GeometryEngine.compute_tangent_points_for_vertex(
                match.geometry,
                match.part_idx,
                match.ring_idx,
                match.vertex_idx,
                is_fillet=True,
                val1=radius,
                val2=radius,
            )
            stroke_color = QColor(37, 99, 235, 230)  # Blue #2563EB
            fill_color = QColor(37, 99, 235, 65)
        else:
            dist1 = self.widget.distance1
            dist2 = self.widget.distance2
            new_geom = GeometryEngine.apply_chamfer_to_geometry(
                match.geometry,
                part_idx=match.part_idx,
                ring_idx=match.ring_idx,
                vertex_idx=match.vertex_idx,
                dist1=dist1,
                dist2=dist2,
            )
            t1, t2 = GeometryEngine.compute_tangent_points_for_vertex(
                match.geometry,
                match.part_idx,
                match.ring_idx,
                match.vertex_idx,
                is_fillet=False,
                val1=dist1,
                val2=dist2,
            )
            stroke_color = QColor(5, 150, 105, 230)  # Green #059669
            fill_color = QColor(5, 150, 105, 65)

        # 1. Update geometry rubberband
        if new_geom and not new_geom.isEmpty():
            self.preview_geom = new_geom
            if layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry:
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
                self.preview_rubberband.setFillColor(fill_color)
                self.preview_rubberband.setStrokeColor(stroke_color)
                self.preview_rubberband.setWidth(4)
            else:
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.preview_rubberband.setFillColor(QColor(0, 0, 0, 0))
                self.preview_rubberband.setColor(stroke_color)
                self.preview_rubberband.setWidth(4)

            if _DashLine is not None:
                self.preview_rubberband.setLineStyle(_DashLine)
            self.preview_rubberband.setToGeometry(new_geom, layer)
            self.preview_rubberband.show()
        else:
            self.preview_geom = None
            self.preview_rubberband.reset()

        # 2. Update tangent touch markers
        if t1 and t2:
            t1_map = self.toMapCoordinates(layer, t1)
            t2_map = self.toMapCoordinates(layer, t2)
            self.tangent_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.tangent_rubberband.setColor(stroke_color)
            self.tangent_rubberband.addPoint(t1_map, False)
            self.tangent_rubberband.addPoint(t2_map, True)
            self.tangent_rubberband.show()
        else:
            self.tangent_rubberband.reset()

    def _commit_change(self):
        """Applies the current preview geometry modification to the layer."""
        layer = self.current_vector_layer()
        if not layer or not self.current_match or not self.preview_geom:
            return

        mode = (
            self.widget.mode
            if isinstance(self.widget, FilletCanvasWidget)
            else FilletCanvasWidget.MODE_FILLET
        )
        if mode == FilletCanvasWidget.MODE_FILLET:
            mode_name = self.tr("Скруглення вершини")
        else:
            mode_name = self.tr("Фаска вершини")

        layer.beginEditCommand(mode_name)
        success = layer.changeGeometry(self.current_match.fid, self.preview_geom)
        if success:
            layer.endEditCommand()
            self.canvas.refresh()
        else:
            layer.destroyEditCommand()

        self._clear_preview()
        self.state = self.STATE_HOVER

    def _cancel_operation(self):
        """Cancels current operation and returns to hovering state."""
        self._clear_preview()
        self.state = self.STATE_HOVER

    def keyPressEvent(self, event):
        key = event.key()

        # If user types digits or math symbols before first click or while hovering, redirect to numeric stepper
        if event.text() and (event.text().isdigit() or event.text() in ".-+," or key == _Key_Backspace):
            if isinstance(self.widget, FilletCanvasWidget):
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

        if key in (_Key_Return, _Key_Enter):
            # Commit with Enter
            self._commit_change()
            event.accept()

        elif key == _Key_Escape:
            # Cancel with Escape
            self._cancel_operation()
            event.accept()

        elif key == _Key_Tab:
            # When Tab is pressed, if focus is not on the HUD panel, jump to primary numeric stepper
            if isinstance(self.widget, FilletCanvasWidget):
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
            # Space toggles lock
            if isinstance(self.widget, FilletCanvasWidget):
                self.widget.toggle_active_lock()
                event.accept()

        elif key == _Key_Shift:
            if isinstance(self.widget, FilletCanvasWidget):
                self.widget.set_shift_override(True)
                if self.state == self.STATE_ADJUSTING and getattr(self, "last_mouse_point", None):
                    layer = self.current_vector_layer()
                    if layer:
                        self._update_values_from_point(layer, self.last_mouse_point, shift_pressed=True)
                        self._update_preview()

        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        key = event.key()
        if key == _Key_Shift:
            if isinstance(self.widget, FilletCanvasWidget):
                self.widget.set_shift_override(False)
                if self.state == self.STATE_ADJUSTING and getattr(self, "last_mouse_point", None):
                    layer = self.current_vector_layer()
                    if layer:
                        self._update_values_from_point(layer, self.last_mouse_point, shift_pressed=False)
                        self._update_preview()
        super().keyReleaseEvent(event)

    def _clear_preview(self):
        self.snap_indicator.setVisible(False)
        self.tangent_rubberband.reset()
        self.preview_rubberband.reset()
        self.current_match = None
        self.preview_geom = None

# -*- coding: utf-8 -*-
"""
Map tool for interactive CAD Edge Offset (Parallel Shift) in QGIS.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
from typing import Optional

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsMessageLog,
    QgsPoint,
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
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QApplication

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
    from ..core.snapping_helper import SegmentMatch, SnappingHelper
    from .edge_offset_canvas_widget import EdgeOffsetCanvasWidget
    from .gui_utils import checked_edit_command, require_edit_success
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import SegmentMatch, SnappingHelper
    from gui.edge_offset_canvas_widget import EdgeOffsetCanvasWidget
    from gui.gui_utils import checked_edit_command, require_edit_success


class EdgeOffsetMapTool(QgsMapToolEdit):
    """
    Interactive CAD Edge Offset Map Tool for QGIS 3.x and 4.x.
    Supports system snapping to map layers, vertices, segments, and guides.
    """

    STATE_HOVER_EDGE = 1
    STATE_ADJUSTING_OFFSET = 2

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas, widget: EdgeOffsetCanvasWidget, iface=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.iface = iface

        self.state = self.STATE_HOVER_EDGE
        self.current_match: Optional[SegmentMatch] = None
        self.preview_geom: Optional[QgsGeometry] = None
        self.last_mouse_point: Optional[QgsPointXY] = None
        self._current_side_sign: float = 1.0

        # System snapping indicator
        self.snap_indicator = QgsSnapIndicator(self.canvas)

        # 1. Hovered/Selected Edge Rubberband
        self.edge_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.edge_rubberband.setWidth(4)
        self.edge_rubberband.setColor(QColor(37, 99, 235, 240))  # Royal blue

        # 2. Normal Guide Rubberband (dashed line from edge midpoint to cursor offset)
        self.normal_guide_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.normal_guide_rubberband.setWidth(2)
        if _DashLine is not None:
            self.normal_guide_rubberband.setLineStyle(_DashLine)
        self.normal_guide_rubberband.setColor(QColor(234, 88, 12, 220))  # Orange

        # 3. Geometry Preview Rubberband
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_rubberband.setWidth(3)
        if _DashLine is not None:
            self.preview_rubberband.setLineStyle(_DashLine)
        self.preview_rubberband.setColor(QColor(16, 185, 129, 230))  # Emerald green
        self.preview_rubberband.setFillColor(QColor(16, 185, 129, 50))

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        # Connect widget signals
        self.widget.distanceChanged.connect(self._on_widget_distance_changed)
        self.widget.modeChanged.connect(self._on_widget_mode_changed)
        self.widget.commitRequested.connect(self._commit_preview)
        self.widget.resetRequested.connect(self._cancel_operation)

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isEditable()
            and layer.geometryType() in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry)
        ):
            return layer
        return None

    def activate(self):
        super().activate()
        layer = self.current_vector_layer()
        if layer:
            self.widget.adapt_to_crs(layer.crs())
        self.state = self.STATE_HOVER_EDGE
        self.current_match = None
        self._clear_preview()
        self.widget.set_step(EdgeOffsetCanvasWidget.STEP_SELECT_EDGE)
        self.widget.show_on_canvas()
        QTimer.singleShot(0, self.widget.focus_primary_input)
        QTimer.singleShot(50, self.widget.focus_primary_input)

    def deactivate(self):
        self._clear_preview()
        if self.widget:
            self.widget.set_shift_override(False)
            self.widget.hide()
        if hasattr(self.canvas.snappingUtils(), "clearAllLocators"):
            self.canvas.snappingUtils().clearAllLocators()
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        if self.widget:
            try:
                self.widget.distanceChanged.disconnect(self._on_widget_distance_changed)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            try:
                self.widget.modeChanged.disconnect(self._on_widget_mode_changed)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            try:
                self.widget.commitRequested.disconnect(self._commit_preview)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            try:
                self.widget.resetRequested.disconnect(self._cancel_operation)
            except (TypeError, RuntimeError):
                pass  # nosec B110

        for rb in (self.edge_rubberband, self.normal_guide_rubberband, self.preview_rubberband):
            if rb:
                rb.reset()
        if self.snap_indicator:
            self.snap_indicator.setVisible(False)

    def _clear_preview(self):
        self.edge_rubberband.reset()
        self.normal_guide_rubberband.reset()
        self.preview_rubberband.reset()
        if self.snap_indicator:
            self.snap_indicator.setVisible(False)
        self.preview_geom = None

    def _on_widget_distance_changed(self, dist: float):
        if self.state == self.STATE_ADJUSTING_OFFSET and self.current_match:
            layer = self.current_vector_layer()
            if layer:
                self._update_preview(layer, self.current_match, dist * self._current_side_sign, self.widget.mode)

    def _on_widget_mode_changed(self, mode: str):
        if self.state == self.STATE_ADJUSTING_OFFSET and self.current_match:
            layer = self.current_vector_layer()
            if layer:
                self._update_preview(layer, self.current_match, self.widget.distance * self._current_side_sign, mode)

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_preview()
            return

        # 1. System snapping to map canvas
        snap_match = self.canvas.snappingUtils().snapToMap(event.pos())
        if snap_match.isValid():
            self.snap_indicator.setMatch(snap_match)
            self.snap_indicator.setVisible(True)
            map_point = snap_match.point()
        else:
            self.snap_indicator.setVisible(False)
            map_point = event.mapPoint()

        shift_pressed = bool(_ShiftModifier is not None and (event.modifiers() & _ShiftModifier))
        if self.widget:
            self.widget.set_shift_override(shift_pressed)

        self.last_mouse_point = map_point

        if self.state == self.STATE_HOVER_EDGE:
            match = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if match:
                self.current_match = match
                p1_map = self.toMapCoordinates(layer, match.p1)
                p2_map = self.toMapCoordinates(layer, match.p2)

                self.edge_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.edge_rubberband.setColor(QColor(37, 99, 235, 240))
                self.edge_rubberband.setWidth(4)
                self.edge_rubberband.addPoint(p1_map, False)
                self.edge_rubberband.addPoint(p2_map, True)
                self.edge_rubberband.show()
            else:
                self.current_match = None
                self.edge_rubberband.reset()

        elif self.state == self.STATE_ADJUSTING_OFFSET:
            if self.current_match:
                self._update_interactive_offset(layer, map_point, shift_pressed)

    def _update_interactive_offset(self, layer: QgsVectorLayer, map_point: QgsPointXY, shift_pressed: bool = False):
        if not self.current_match or not self.widget:
            return

        m = self.current_match
        layer_pt = self.toLayerCoordinates(layer, map_point)

        # Calculate unit normal of the edge
        dx = m.p2.x() - m.p1.x()
        dy = m.p2.y() - m.p1.y()
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return

        nx = -dy / length
        ny = dx / length

        # Vector from p1 to cursor/snap point
        wx = layer_pt.x() - m.p1.x()
        wy = layer_pt.y() - m.p1.y()

        # Signed distance along normal vector
        signed_dist = wx * nx + wy * ny
        dist_mag = abs(signed_dist)
        self._current_side_sign = 1.0 if signed_dist >= 0 else -1.0

        is_geo = layer.crs().isGeographic() if layer and layer.crs().isValid() else False
        min_limit = 1e-6 if is_geo else 0.0001
        rounded_dist = max(min_limit, round(dist_mag, 6 if is_geo else (4 if dist_mag < 1.0 else 3)))

        eff_mode = self.widget.get_effective_mode(shift_pressed)

        # In extend mode, clamp the distance if a blocking node or apex limit is reached
        if eff_mode == "extend" and m.geometry and not m.geometry.isEmpty():
            curve = GeometryEngine.get_curve_from_geometry(m.geometry, m.part_idx, m.ring_idx)
            if curve:
                d_max = GeometryEngine.get_max_extend_distance(curve, m.segment_idx, self._current_side_sign)
                if d_max is not None:
                    d_max_rounded = round(d_max, 6 if is_geo else (4 if d_max < 1.0 else 3))
                    rounded_dist = min(rounded_dist, d_max_rounded)

        if not self.widget.is_distance_locked:
            self.widget.set_distance(rounded_dist, block_signals=True)

        eff_dist = (self.widget.distance if self.widget.is_distance_locked else rounded_dist) * self._current_side_sign

        self._update_preview(layer, m, eff_dist, eff_mode)

    def _update_preview(self, layer: QgsVectorLayer, match: SegmentMatch, distance: float, mode: str):
        # 1. Update normal guide rubberband (midpoint to offset point)
        p1_map = self.toMapCoordinates(layer, match.p1)
        p2_map = self.toMapCoordinates(layer, match.p2)

        mid_layer = QgsPointXY((match.p1.x() + match.p2.x()) * 0.5, (match.p1.y() + match.p2.y()) * 0.5)
        dx = match.p2.x() - match.p1.x()
        dy = match.p2.y() - match.p1.y()
        length = math.hypot(dx, dy)
        if length > 1e-9:
            nx = -dy / length
            ny = dx / length
            target_layer = QgsPointXY(mid_layer.x() + distance * nx, mid_layer.y() + distance * ny)
            mid_map = self.toMapCoordinates(layer, mid_layer)
            target_map = self.toMapCoordinates(layer, target_layer)

            self.normal_guide_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self.normal_guide_rubberband.setColor(QColor(234, 88, 12, 220))
            self.normal_guide_rubberband.setWidth(2)
            if _DashLine is not None:
                self.normal_guide_rubberband.setLineStyle(_DashLine)
            self.normal_guide_rubberband.addPoint(mid_map, False)
            self.normal_guide_rubberband.addPoint(target_map, True)
            self.normal_guide_rubberband.show()

        # 2. Calculate offset geometry (with automatic non-self-intersection guarantee)
        new_geom = GeometryEngine.offset_segment(
            match.geometry,
            match.part_idx,
            match.ring_idx,
            match.segment_idx,
            distance,
            mode=mode,
        )

        if new_geom and not new_geom.isEmpty():
            self.preview_geom = new_geom
            is_poly = layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry
            self.preview_rubberband.reset(
                QgsWkbTypes.GeometryType.PolygonGeometry if is_poly else QgsWkbTypes.GeometryType.LineGeometry
            )
            self.preview_rubberband.setColor(QColor(16, 185, 129, 230))
            if is_poly:
                self.preview_rubberband.setFillColor(QColor(16, 185, 129, 50))
            self.preview_rubberband.setWidth(3)
            if _DashLine is not None:
                self.preview_rubberband.setLineStyle(_DashLine)

            # Transform geometry to map canvas coordinates
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            if canvas_crs != layer_crs and canvas_crs.isValid() and layer_crs.isValid():
                xform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                geom_disp = QgsGeometry(new_geom)
                geom_disp.transform(xform)
                self.preview_rubberband.setToGeometry(geom_disp, None)
            else:
                self.preview_rubberband.setToGeometry(new_geom, None)
            self.preview_rubberband.show()
        else:
            self.preview_rubberband.reset()
            self.preview_geom = None

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            return

        button = event.button()
        if button == _LeftButton:
            # Check system snapping
            snap_match = self.canvas.snappingUtils().snapToMap(event.pos())
            map_point = snap_match.point() if snap_match.isValid() else event.mapPoint()

            if self.state == self.STATE_HOVER_EDGE:
                if self.current_match:
                    if GeometryEngine.has_curved_segments(self.current_match.geometry):
                        self._show_curved_geometry_warning()
                        return
                    self.state = self.STATE_ADJUSTING_OFFSET
                    self.widget.set_step(EdgeOffsetCanvasWidget.STEP_ADJUST_OFFSET)
                    self.widget.focus_primary_input()
                    self._update_interactive_offset(layer, map_point)
            elif self.state == self.STATE_ADJUSTING_OFFSET:
                self._commit_preview()

        elif button == _RightButton:
            self._cancel_operation()

    def _commit_preview(self):
        layer = self.current_vector_layer()
        if not layer or not self.current_match or not self.preview_geom:
            return

        try:
            with checked_edit_command(layer, self.tr("Зсув ребра")):
                if self.widget.copy_mode:
                    new_feat = QgsFeature(layer.fields())
                    orig_feat = layer.getFeature(self.current_match.fid)
                    if orig_feat.isValid():
                        new_feat.setAttributes(orig_feat.attributes())
                    new_feat.setGeometry(self.preview_geom)
                    require_edit_success(layer.addFeature(new_feat), "addFeature")
                else:
                    require_edit_success(
                        layer.changeGeometry(
                            self.current_match.fid,
                            self.preview_geom,
                        ),
                        "changeGeometry",
                    )
        except (RuntimeError, TypeError) as error:
            self._show_write_error(error)
            return
        layer.triggerRepaint()

        self._clear_preview()
        self.state = self.STATE_HOVER_EDGE
        self.current_match = None
        self.widget.set_step(EdgeOffsetCanvasWidget.STEP_SELECT_EDGE)

    def _show_write_error(self, error: Exception):
        message = self.tr("Не вдалося записати зміни: {error}").format(error=error)
        if self.iface and hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushMessage(
                self.tr("Fillet Toolkit"),
                message,
                level=Qgis.Critical,
                duration=5,
            )
        else:
            QgsMessageLog.logMessage(message, "Fillet Toolkit", Qgis.Critical)

    def _show_curved_geometry_warning(self):
        message = self.tr(
            "Ця операція недоступна для геометрій із кривими сегментами."
        )
        if self.iface and hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushMessage(
                self.tr("Fillet Toolkit"),
                message,
                level=Qgis.Warning,
                duration=5,
            )
        else:
            QgsMessageLog.logMessage(message, "Fillet Toolkit", Qgis.Warning)

    def _cancel_operation(self):
        self._clear_preview()
        self.state = self.STATE_HOVER_EDGE
        self.current_match = None
        self.widget.set_step(EdgeOffsetCanvasWidget.STEP_SELECT_EDGE)

    def keyPressEvent(self, event):
        key = event.key()

        # Keystroke redirection to numeric distance stepper
        if event.text() and (event.text().isdigit() or event.text() in ".-+," or key == _Key_Backspace):
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

        if key in (_Key_Escape,):
            self._cancel_operation()
            event.accept()
            return

        elif key in (_Key_Return, _Key_Enter):
            if self.state == self.STATE_ADJUSTING_OFFSET and self.preview_geom:
                self._commit_preview()
                event.accept()
                return

        elif key == _Key_Tab:
            if self.widget:
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

        elif key == _Key_Shift:
            if self.widget:
                self.widget.set_shift_override(True)
                if self.state == self.STATE_ADJUSTING_OFFSET and self.last_mouse_point:
                    layer = self.current_vector_layer()
                    if layer:
                        self._update_interactive_offset(layer, self.last_mouse_point, shift_pressed=True)

        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        key = event.key()
        if key == _Key_Shift:
            if self.widget:
                self.widget.set_shift_override(False)
                if self.state == self.STATE_ADJUSTING_OFFSET and self.last_mouse_point:
                    layer = self.current_vector_layer()
                    if layer:
                        self._update_interactive_offset(layer, self.last_mouse_point, shift_pressed=False)
        super().keyReleaseEvent(event)

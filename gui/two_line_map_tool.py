# -*- coding: utf-8 -*-
"""
Map tool for interactive Two-Line Fillet & Chamfer with feature merging.
Uses FilletCanvasWidget with step-by-step guidance and dynamic cursor radius drag.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
from typing import Optional

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsMessageLog,
    QgsPoint,
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
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QObject, Qt
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QAbstractButton, QAction, QApplication, QDialog

# Safe cross-version Qt5 / Qt6 constants
_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_DashLine = getattr(Qt.PenStyle, "DashLine", getattr(Qt, "DashLine", 2))
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
_Key_L = getattr(Qt.Key, "Key_L", getattr(Qt, "Key_L", 0x4C))
_Key_F = getattr(Qt.Key, "Key_F", getattr(Qt, "Key_F", 0x46))
_Key_C = getattr(Qt.Key, "Key_C", getattr(Qt, "Key_C", 0x43))

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import SegmentMatch, SnappingHelper
    from .canvas_widget import FilletCanvasWidget
    from .gui_utils import checked_edit_command, require_edit_success
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import SegmentMatch, SnappingHelper
    from gui.canvas_widget import FilletCanvasWidget
    from gui.gui_utils import checked_edit_command, require_edit_success


class _MergeDialogWatcher(QObject):
    """Watches QApplication for QDialog results during native merge attribute dialog execution."""

    def __init__(self):
        super().__init__()
        self.dialog_detected = False
        self.accepted = False
        self._disabled_buttons = []

    def eventFilter(self, obj, event):
        if isinstance(obj, QDialog):
            evt_type = event.type()
            evt_show = getattr(QEvent.Type, "Show", getattr(QEvent, "Show", 17))
            evt_hide = getattr(QEvent.Type, "Hide", getattr(QEvent, "Hide", 18))
            evt_close = getattr(QEvent.Type, "Close", getattr(QEvent, "Close", 19))
            if evt_type == evt_show:
                self.dialog_detected = True
                # Disable 'Remove feature from selection' button on this specific dialog instance
                for btn in obj.findChildren(QAbstractButton):
                    name = btn.objectName().lower()
                    text = btn.text().lower()
                    tip = btn.toolTip().lower()
                    if (
                        "remove" in name
                        or "remove" in tip
                        or "remove" in text
                        or "видалити" in text
                        or "видалити" in tip
                    ):
                        if btn.isEnabled():
                            btn.setEnabled(False)
                            self._disabled_buttons.append(btn)
            elif evt_type in (evt_hide, evt_close):
                self.dialog_detected = True
                res = obj.result()
                accepted_code = getattr(getattr(QDialog, "DialogCode", QDialog), "Accepted", 1)
                if res == accepted_code:
                    self.accepted = True
                # Restore button state if dialog instance is reused
                for btn in self._disabled_buttons:
                    try:
                        btn.setEnabled(True)
                    except (RuntimeError, TypeError):
                        pass
                self._disabled_buttons.clear()
        return False


class TwoLineMapTool(QgsMapToolEdit):
    """Dedicated CAD Map Tool for Filleting/Chamfering two lines with dynamic cursor drag and feature merging."""

    STEP_FIRST_LINE = 1
    STEP_SECOND_LINE = 2
    STEP_SET_RADIUS = 3

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(
        self,
        canvas: QgsMapCanvas,
        widget: Optional[FilletCanvasWidget] = None,
        iface=None,
    ):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget or FilletCanvasWidget(self.canvas)
        self.iface = iface

        self.step = self.STEP_FIRST_LINE
        self.first_segment_match: Optional[SegmentMatch] = None
        self.current_segment_match: Optional[SegmentMatch] = None
        self.v_sharp: Optional[QgsPoint] = None
        self.preview_geom: Optional[QgsGeometry] = None

        # 1. Edge selection rubberbands
        self.edge1_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.edge1_rubberband.setWidth(4)
        self.edge1_rubberband.setColor(QColor(30, 58, 138, 230))  # Blue

        self.edge2_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.edge2_rubberband.setWidth(4)
        self.edge2_rubberband.setColor(QColor(59, 130, 246, 230))  # Light Blue

        # 2. Geometry preview rubberband
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.preview_rubberband.setWidth(4)
        self.preview_rubberband.setColor(QColor(37, 99, 235, 230))
        if _DashLine is not None:
            self.preview_rubberband.setLineStyle(_DashLine)

        # 3. Corner intersection marker rubberband
        self.corner_marker = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.corner_marker.setIcon(QgsRubberBand.IconType.ICON_CROSS)
        self.corner_marker.setIconSize(12)
        self.corner_marker.setWidth(2)
        self.corner_marker.setColor(QColor(234, 88, 12, 255))  # Amber

        # 4. Tangent touch points marker rubberband
        self.tangent_marker = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.tangent_marker.setIcon(QgsRubberBand.IconType.ICON_BOX)
        self.tangent_marker.setIconSize(8)
        self.tangent_marker.setWidth(2)
        self.tangent_marker.setColor(QColor(37, 99, 235, 255))

        # 5. Snapping indicator
        self.snap_indicator = QgsSnapIndicator(self.canvas)

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        # Recompute preview on parameter change
        if self.widget:
            self.widget.parametersChanged.connect(self._on_parameters_changed)
            if hasattr(self.widget, "commitRequested"):
                self.widget.commitRequested.connect(self._commit_current_preview)
            if hasattr(self.widget, "resetRequested"):
                self.widget.resetRequested.connect(self._handle_step_back)

    def activate(self):
        super().activate()
        self._clear_preview()
        if self.widget:
            self.widget.set_two_line_mode(True)
            self.widget.set_step(self.STEP_FIRST_LINE)
            self.widget.show_on_canvas()
            from qgis.PyQt.QtCore import QTimer
            QTimer.singleShot(0, self.widget.focus_primary_input)
            QTimer.singleShot(50, self.widget.focus_primary_input)

    def deactivate(self):
        self._clear_preview()
        if hasattr(self, "snap_indicator") and self.snap_indicator:
            self.snap_indicator.setVisible(False)
        if self.widget:
            self.widget.set_shift_override(False)
            self.widget.set_two_line_mode(False)
            self.widget.hide()
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        if self.widget:
            try:
                self.widget.parametersChanged.disconnect(self._on_parameters_changed)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if hasattr(self.widget, "commitRequested"):
                try:
                    self.widget.commitRequested.disconnect(self._commit_current_preview)
                except (TypeError, RuntimeError):
                    pass  # nosec B110
            if hasattr(self.widget, "resetRequested"):
                try:
                    self.widget.resetRequested.disconnect(self._handle_step_back)
                except (TypeError, RuntimeError):
                    pass  # nosec B110
        if hasattr(self, "snap_indicator") and self.snap_indicator:
            self.snap_indicator.setVisible(False)
            del self.snap_indicator
            self.snap_indicator = None
        for rb in (
            self.edge1_rubberband,
            self.edge2_rubberband,
            self.preview_rubberband,
            self.corner_marker,
            self.tangent_marker,
        ):
            if rb:
                rb.reset()

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isEditable()
            and layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry
        ):
            return layer
        return None

    def _on_parameters_changed(self):
        """Recalculates preview when parameters are edited in spinboxes."""
        if self.step in (self.STEP_SECOND_LINE, self.STEP_SET_RADIUS) and self.first_segment_match and self.current_segment_match:
            layer = self.current_vector_layer()
            if layer:
                self._update_preview(layer, self.first_segment_match, self.current_segment_match)

    def _update_interactive_radius(self, layer: QgsVectorLayer, map_point: QgsPointXY, shift_pressed: bool = False):
        """Calculates radius or chamfer distances from cursor point during Step 3."""
        if not (self.first_segment_match and self.current_segment_match and self.v_sharp and self.widget):
            return

        layer_pt = self.toLayerCoordinates(layer, map_point)
        cursor_pt = QgsPoint(layer_pt.x(), layer_pt.y())
        dist = GeometryEngine.distance(self.v_sharp, cursor_pt)

        is_geo = layer.crs().isGeographic() if layer and layer.crs().isValid() else False
        if self.widget.mode == FilletCanvasWidget.MODE_FILLET:
            rounded_dist = max(0.0, round(dist, 6 if is_geo else (4 if dist < 1.0 else 3)))
            if not self.widget.is_radius_locked:
                self.widget.set_radius(rounded_dist, block_signals=True)
        else:
            m1 = self.first_segment_match
            m2 = self.current_segment_match

            # Ray 1 direction from v_sharp
            d1x = m1.p2.x() - m1.p1.x()
            d1y = m1.p2.y() - m1.p1.y()
            len1 = math.hypot(d1x, d1y)
            ud1x, ud1y = (d1x / len1, d1y / len1) if len1 > 1e-9 else (1.0, 0.0)
            t_click1 = (m1.point.x() - self.v_sharp.x()) * ud1x + (m1.point.y() - self.v_sharp.y()) * ud1y
            u1x = ud1x if t_click1 > 0 else -ud1x
            u1y = ud1y if t_click1 > 0 else -ud1y

            # Ray 2 direction from v_sharp
            d2x = m2.p2.x() - m2.p1.x()
            d2y = m2.p2.y() - m2.p1.y()
            len2 = math.hypot(d2x, d2y)
            ud2x, ud2y = (d2x / len2, d2y / len2) if len2 > 1e-9 else (1.0, 0.0)
            t_click2 = (m2.point.x() - self.v_sharp.x()) * ud2x + (m2.point.y() - self.v_sharp.y()) * ud2y
            u2x = ud2x if t_click2 > 0 else -ud2x
            u2y = ud2y if t_click2 > 0 else -ud2y

            is_eff_linked = self.widget.get_effective_is_linked(shift_pressed)
            if is_eff_linked:
                # Symmetrical linked chamfer: both distances scale identically
                rounded_dist = max(0.0, round(dist, 6 if is_geo else (4 if dist < 1.0 else 3)))
                if not self.widget.is_dist1_locked:
                    self.widget.set_distance1(rounded_dist, block_signals=True)
                if not self.widget.is_dist2_locked:
                    self.widget.set_distance2(rounded_dist, block_signals=True)
            else:
                # Asymmetrical unlinked chamfer: cursor position independently projects on rays
                wx = cursor_pt.x() - self.v_sharp.x()
                wy = cursor_pt.y() - self.v_sharp.y()
                proj1 = wx * u1x + wy * u1y
                proj2 = wx * u2x + wy * u2y
                d1 = max(0.0, abs(proj1))
                d2 = max(0.0, abs(proj2))
                rounded_d1 = round(d1, 6 if is_geo else (4 if d1 < 1.0 else 3))
                rounded_d2 = round(d2, 6 if is_geo else (4 if d2 < 1.0 else 3))
                if not self.widget.is_dist1_locked:
                    self.widget.set_distance1(rounded_d1, block_signals=True)
                if not self.widget.is_dist2_locked:
                    self.widget.set_distance2(rounded_d2, block_signals=True)

        self._update_preview(layer, self.first_segment_match, self.current_segment_match)

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_preview()
            return

        shift_pressed = bool(_ShiftModifier is not None and (event.modifiers() & _ShiftModifier))
        if self.widget:
            self.widget.set_shift_override(shift_pressed)

        map_point = event.mapPoint()
        self.last_mouse_point = map_point

        if self.step == self.STEP_FIRST_LINE:
            if getattr(self, "snap_indicator", None):
                self.snap_indicator.setVisible(False)
            # Step 1: Hovering over first line
            match = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if match:
                self.current_segment_match = match
                p1_map = self.toMapCoordinates(layer, match.p1)
                p2_map = self.toMapCoordinates(layer, match.p2)
                self.edge1_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.edge1_rubberband.setColor(QColor(30, 58, 138, 230))
                self.edge1_rubberband.setWidth(4)
                self.edge1_rubberband.addPoint(p1_map, False)
                self.edge1_rubberband.addPoint(p2_map, True)
                self.edge1_rubberband.show()
            else:
                self.current_segment_match = None
                self.edge1_rubberband.reset()
            self.edge2_rubberband.reset()
            self.preview_rubberband.reset()
            self.corner_marker.reset()
            self.tangent_marker.reset()

        elif self.step == self.STEP_SECOND_LINE:
            if getattr(self, "snap_indicator", None):
                self.snap_indicator.setVisible(False)
            # Step 2: Hovering over second line
            m1 = self.first_segment_match
            m2 = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if m2 and (m2.fid != m1.fid or m2.part_idx != m1.part_idx or m2.segment_idx != m1.segment_idx):
                self.current_segment_match = m2
                p1_map = self.toMapCoordinates(layer, m2.p1)
                p2_map = self.toMapCoordinates(layer, m2.p2)
                self.edge2_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.edge2_rubberband.setColor(QColor(59, 130, 246, 230))
                self.edge2_rubberband.setWidth(4)
                self.edge2_rubberband.addPoint(p1_map, False)
                self.edge2_rubberband.addPoint(p2_map, True)
                self.edge2_rubberband.show()

                self._update_preview(layer, m1, m2)
            else:
                self.edge2_rubberband.reset()
                self.preview_rubberband.reset()
                self.corner_marker.reset()
                self.tangent_marker.reset()
                self.preview_geom = None

        elif self.step == self.STEP_SET_RADIUS:
            # Step 3: Interactive cursor drag to adjust radius / chamfer distance with system snapping
            snap_match = self.canvas.snappingUtils().snapToMap(event.pos())
            if snap_match.isValid():
                map_point = snap_match.point()
                if getattr(self, "snap_indicator", None):
                    self.snap_indicator.setMatch(snap_match)
                    self.snap_indicator.setVisible(True)
            else:
                map_point = event.mapPoint()
                if getattr(self, "snap_indicator", None):
                    self.snap_indicator.setVisible(False)
            self.last_mouse_point = map_point
            self._update_interactive_radius(layer, map_point, shift_pressed)

        # Keep focus on the HUD panel's numeric stepper if focus moved away
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

    def _update_preview(self, layer: QgsVectorLayer, m1: SegmentMatch, m2: SegmentMatch):
        """Calculates and renders rubberband preview connecting two lines."""
        mode = self.widget.mode if self.widget else "fillet"
        radius = self.widget.radius if self.widget else 1.0
        dist1 = self.widget.distance1 if self.widget else 1.0
        dist2 = self.widget.distance2 if self.widget else 1.0
        segments = self.widget.segments_count if self.widget else 12

        res = GeometryEngine.fillet_or_chamfer_two_lines(
            m1.geometry,
            m1.segment_idx,
            m1.point,
            m2.geometry,
            m2.segment_idx,
            m2.point,
            mode=mode,
            radius=radius,
            dist1=dist1,
            dist2=dist2,
            segments_count=segments,
            part1_idx=m1.part_idx,
            part2_idx=m2.part_idx,
        )
        if res:
            joined_geom, v_sharp, t1, t2 = res
            new_geom = GeometryEngine.rebuild_two_line_geometry(
                m1.geometry,
                m1.part_idx,
                m2.geometry,
                m2.part_idx,
                joined_geom,
                same_feature=m1.fid == m2.fid,
            )
            if new_geom is None:
                self.preview_geom = None
                self.v_sharp = None
                self.preview_rubberband.reset()
                self.corner_marker.reset()
                self.tangent_marker.reset()
                return
            self.v_sharp = v_sharp
            self.preview_geom = new_geom

            if mode == "fillet":
                stroke_color = QColor(37, 99, 235, 230)  # Blue #2563EB
                fill_color = QColor(37, 99, 235, 65)
            else:
                stroke_color = QColor(5, 150, 105, 230)  # Emerald Green #059669
                fill_color = QColor(5, 150, 105, 65)

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

            # Intersection point marker
            v_xy = QgsPointXY(v_sharp.x(), v_sharp.y())
            v_map = self.toMapCoordinates(layer, v_xy)
            self.corner_marker.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.corner_marker.addPoint(v_map, True)
            self.corner_marker.show()

            # Tangent touch markers
            t1_xy = QgsPointXY(t1.x(), t1.y())
            t2_xy = QgsPointXY(t2.x(), t2.y())
            t1_map = self.toMapCoordinates(layer, t1_xy)
            t2_map = self.toMapCoordinates(layer, t2_xy)
            self.tangent_marker.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.tangent_marker.setColor(stroke_color)
            self.tangent_marker.addPoint(t1_map, False)
            self.tangent_marker.addPoint(t2_map, True)
            self.tangent_marker.show()
        else:
            self.preview_geom = None
            self.v_sharp = None
            self.preview_rubberband.reset()
            self.corner_marker.reset()
            self.tangent_marker.reset()

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == _RightButton:
            self._handle_step_back()
            return

        if event.button() != _LeftButton:
            return

        layer = self.current_vector_layer()
        if not layer:
            return

        if self.step == self.STEP_FIRST_LINE:
            # Step 1: Select first line
            map_point = event.mapPoint()
            match = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if match:
                if GeometryEngine.has_curved_segments(match.geometry):
                    self._show_curved_geometry_warning()
                    return
                self.first_segment_match = match
                p1_map = self.toMapCoordinates(layer, match.p1)
                p2_map = self.toMapCoordinates(layer, match.p2)
                self.edge1_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.edge1_rubberband.setColor(QColor(30, 58, 138, 230))
                self.edge1_rubberband.setWidth(4)
                self.edge1_rubberband.addPoint(p1_map, False)
                self.edge1_rubberband.addPoint(p2_map, True)
                self.edge1_rubberband.show()

                self.step = self.STEP_SECOND_LINE
                if self.widget:
                    self.widget.set_step(self.STEP_SECOND_LINE)

        elif self.step == self.STEP_SECOND_LINE:
            # Step 2: Select second line
            if self.current_segment_match and GeometryEngine.has_curved_segments(
                self.current_segment_match.geometry
            ):
                self._show_curved_geometry_warning()
                return
            if self.current_segment_match and self.preview_geom:
                # If parameter is locked, commit directly!
                is_locked = (
                    self.widget.is_radius_locked
                    if (self.widget and self.widget.mode == FilletCanvasWidget.MODE_FILLET)
                    else (self.widget.is_dist1_locked if self.widget else True)
                )
                if is_locked:
                    self._commit_current_preview()
                else:
                    # Parameter is unlocked: enter Step 3 for interactive cursor drag
                    self.step = self.STEP_SET_RADIUS
                    if self.widget:
                        self.widget.set_step(self.STEP_SET_RADIUS)

        elif self.step == self.STEP_SET_RADIUS:
            # Step 3: Confirm radius and commit with snapping
            snap_match = self.canvas.snappingUtils().snapToMap(event.pos())
            if snap_match.isValid():
                map_point = snap_match.point()
            else:
                map_point = event.mapPoint()
            self._update_interactive_radius(layer, map_point)
            self._commit_current_preview()

        # Always restore focus to the primary numeric stepper after mouse click
        if self.widget:
            from qgis.PyQt.QtCore import QTimer
            QTimer.singleShot(0, self.widget.focus_primary_input)

    def keyPressEvent(self, event):
        key = event.key()

        # If user types digits or math symbols before first click or while hovering, redirect to numeric stepper
        if event.text() and (event.text().isdigit() or event.text() in ".-+," or key == _Key_Backspace):
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
                    focused = QApplication.focusWidget()
                    if focused:
                        QApplication.sendEvent(focused, event)
                    event.accept()
                    return

        if key in (_Key_Escape,):
            self._handle_step_back()
            event.accept()
            return

        elif key in (_Key_Return, _Key_Enter):
            if self.step == self.STEP_SET_RADIUS or (self.step == self.STEP_SECOND_LINE and self.preview_geom):
                self._commit_current_preview()
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

        elif key == _Key_L:
            if self.widget:
                self.widget.toggle_active_lock()
                event.accept()
                return

        elif key == _Key_F:
            if self.widget:
                self.widget.mode = FilletCanvasWidget.MODE_FILLET
                event.accept()
                return

        elif key == _Key_C:
            if self.widget:
                self.widget.mode = FilletCanvasWidget.MODE_CHAMFER
                event.accept()
                return

        elif key == _Key_Shift:
            if self.widget:
                self.widget.set_shift_override(True)
                if self.step == self.STEP_SET_RADIUS and getattr(self, "last_mouse_point", None):
                    layer = self.current_vector_layer()
                    if layer:
                        self._update_interactive_radius(layer, self.last_mouse_point, shift_pressed=True)

        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        key = event.key()
        if key == _Key_Shift:
            if self.widget:
                self.widget.set_shift_override(False)
                if self.step == self.STEP_SET_RADIUS and getattr(self, "last_mouse_point", None):
                    layer = self.current_vector_layer()
                    if layer:
                        self._update_interactive_radius(layer, self.last_mouse_point, shift_pressed=False)
        super().keyReleaseEvent(event)

    def _handle_step_back(self):
        """Step back through CAD workflow or clear selection."""
        if self.step == self.STEP_SET_RADIUS:
            self.step = self.STEP_SECOND_LINE
            if self.widget:
                self.widget.set_step(self.STEP_SECOND_LINE)
        elif self.step == self.STEP_SECOND_LINE:
            self.first_segment_match = None
            self.current_segment_match = None
            self.preview_geom = None
            self.v_sharp = None
            self.edge1_rubberband.reset()
            self.edge2_rubberband.reset()
            self.preview_rubberband.reset()
            self.corner_marker.reset()
            self.tangent_marker.reset()
            self.step = self.STEP_FIRST_LINE
            if self.widget:
                self.widget.set_step(self.STEP_FIRST_LINE)
        else:
            self._clear_preview()

    def _commit_current_preview(self):
        """Applies the current preview geometry modification to the layer with feature merging."""
        layer = self.current_vector_layer()
        if not layer or not self.first_segment_match or not self.current_segment_match or not self.preview_geom:
            return

        m1 = self.first_segment_match
        m2 = self.current_segment_match
        new_geom = self.preview_geom

        if not self._apply_two_line_operation(layer, m1.fid, m2.fid, new_geom):
            return
        self._clear_preview()
        self.step = self.STEP_FIRST_LINE
        if self.widget:
            self.widget.set_step(self.STEP_FIRST_LINE)

    def _apply_two_line_operation(
        self,
        layer: QgsVectorLayer,
        fid1: int,
        fid2: int,
        new_geom: QgsGeometry,
    ) -> bool:
        """Applies the joined geometry to the vector layer with feature merging."""
        if fid1 == fid2:
            try:
                with checked_edit_command(layer, self.tr("Скруглення / фаска лінії")):
                    require_edit_success(
                        layer.changeGeometry(fid1, new_geom),
                        "changeGeometry",
                    )
            except (RuntimeError, TypeError) as error:
                self._show_write_error(error)
                return False
            layer.triggerRepaint()
            return True

        # Separate features: Check settings
        always_first = QgsSettings().value("plugins/fillet/merge_always_first_feature", False, type=bool)

        if always_first or not self.iface or not hasattr(self.iface, "mainWindow") or not self.iface.mainWindow():
            try:
                with checked_edit_command(
                    layer,
                    self.tr("Скруглення / фаска двох ліній з об'єднанням"),
                ):
                    require_edit_success(
                        layer.changeGeometry(fid1, new_geom),
                        "changeGeometry",
                    )
                    require_edit_success(layer.deleteFeature(fid2), "deleteFeature")
            except (RuntimeError, TypeError) as error:
                self._show_write_error(error)
                return False
            layer.triggerRepaint()
            return True

        # Safe launch of QGIS native merge attributes dialog
        initial_fids = set(layer.allFeatureIds())
        initial_undo_count = layer.undoStack().count() if layer.undoStack() else 0
        layer.selectByIds([fid1, fid2])

        # Prefer mActionMergeFeatureAttributes to prevent multipart errors on singlepart line layers
        merge_action = self.iface.mainWindow().findChild(QAction, "mActionMergeFeatureAttributes")
        if not merge_action:
            merge_action = self.iface.mainWindow().findChild(QAction, "mActionMergeFeatures")

        if merge_action:
            watcher = _MergeDialogWatcher()
            app_inst = QApplication.instance()
            if app_inst:
                app_inst.installEventFilter(watcher)

            try:
                # Execute QGIS native dialog
                merge_action.trigger()
            finally:
                if app_inst:
                    app_inst.removeEventFilter(watcher)

            current_fids = set(layer.allFeatureIds())
            current_undo_count = layer.undoStack().count() if layer.undoStack() else 0
            added_fids = current_fids - initial_fids
            selected_ids = layer.selectedFeatureIds()

            if watcher.dialog_detected:
                is_confirmed = watcher.accepted
            else:
                is_confirmed = (
                    current_undo_count > initial_undo_count
                    or len(current_fids) < len(initial_fids)
                    or bool(added_fids)
                    or (fid2 not in current_fids and fid1 in current_fids)
                )

            if is_confirmed:
                # User confirmed OK: determine target feature ID and feature to delete
                if added_fids:
                    target_id = list(added_fids)[0]
                    delete_id = None
                elif len(selected_ids) == 1 and selected_ids[0] in current_fids:
                    target_id = selected_ids[0]
                    delete_id = fid2 if target_id == fid1 else fid1
                else:
                    target_id = fid1 if fid1 in current_fids else fid2
                    delete_id = fid2 if target_id == fid1 else fid1

                try:
                    with checked_edit_command(
                        layer,
                        self.tr("Скруглення / фаска двох ліній з об'єднанням"),
                    ):
                        if target_id not in current_fids:
                            raise RuntimeError("merge target feature is missing")
                        require_edit_success(
                            layer.changeGeometry(target_id, new_geom),
                            "changeGeometry",
                        )
                        if delete_id is not None and delete_id in current_fids:
                            require_edit_success(
                                layer.deleteFeature(delete_id),
                                "deleteFeature",
                            )
                except (RuntimeError, TypeError) as error:
                    self._rollback_to_undo_count(layer, initial_undo_count)
                    self._show_write_error(error)
                    return False
                finally:
                    layer.removeSelection()
                layer.triggerRepaint()
                return True
            else:
                # User cancelled (Cancel): do not modify geometry, layer remains clean
                layer.removeSelection()
                return False
        else:
            # Fallback when no GUI merge action exists
            try:
                with checked_edit_command(
                    layer,
                    self.tr("Скруглення / фаска двох ліній з об'єднанням"),
                ):
                    require_edit_success(
                        layer.changeGeometry(fid1, new_geom),
                        "changeGeometry",
                    )
                    require_edit_success(layer.deleteFeature(fid2), "deleteFeature")
            except (RuntimeError, TypeError) as error:
                self._show_write_error(error)
                return False
            finally:
                layer.removeSelection()
            layer.triggerRepaint()
            return True

    def _rollback_to_undo_count(self, layer: QgsVectorLayer, initial_count: int):
        """Undo native merge commands created before a failed geometry update."""
        stack = layer.undoStack()
        while stack and stack.count() > initial_count and stack.canUndo():
            stack.undo()

    def _show_write_error(self, error: Exception):
        if self.iface and hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushMessage(
                self.tr("Fillet Toolkit"),
                self.tr("Не вдалося записати зміни: {error}").format(error=error),
                level=Qgis.Critical,
                duration=5,
            )
        else:
            QgsMessageLog.logMessage(
                self.tr("Не вдалося записати зміни: {error}").format(error=error),
                "Fillet Toolkit",
                Qgis.Critical,
            )

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

    def _clear_preview(self):
        self.step = self.STEP_FIRST_LINE
        self.first_segment_match = None
        self.current_segment_match = None
        self.preview_geom = None
        self.v_sharp = None
        self.edge1_rubberband.reset()
        self.edge2_rubberband.reset()
        self.preview_rubberband.reset()
        self.corner_marker.reset()
        self.tangent_marker.reset()
        if getattr(self, "snap_indicator", None):
            self.snap_indicator.setVisible(False)

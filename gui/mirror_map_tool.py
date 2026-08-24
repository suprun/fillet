# -*- coding: utf-8 -*-
"""
Map tool for interactive CAD Mirror (reflection across 2-point axis) in QGIS.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
from typing import List, Optional, Tuple

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
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
    from .mirror_canvas_widget import MirrorCanvasWidget
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from gui.mirror_canvas_widget import MirrorCanvasWidget


class MirrorMapTool(QgsMapToolEdit):
    """CAD-like 2-point interactive mirror map tool."""

    STATE_FIRST_POINT = 0
    STATE_SECOND_POINT = 1

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas, widget: Optional[MirrorCanvasWidget] = None):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget or MirrorCanvasWidget(self.canvas)

        self.state = self.STATE_FIRST_POINT
        self.p1: Optional[QgsPointXY] = None
        self.p2: Optional[QgsPointXY] = None

        # Native QGIS snap indicator
        self.snap_indicator = QgsSnapIndicator(self.canvas)

        # Visual rubberbands
        # 1. P1 Anchor Point Marker
        self.p1_marker = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.p1_marker.setIcon(QgsRubberBand.IconType.ICON_CROSS)
        self.p1_marker.setIconSize(12)
        self.p1_marker.setWidth(2)
        self.p1_marker.setColor(QColor(234, 88, 12, 255))  # Amber/orange

        # 2. Mirror Axis Line Rubberband
        self.axis_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.axis_rubberband.setWidth(2)
        if _DashLine is not None:
            self.axis_rubberband.setLineStyle(_DashLine)
        self.axis_rubberband.setColor(QColor(234, 88, 12, 240))  # Amber/orange

        # 3. Geometry Preview Rubberband
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
        self.widget.commitRequested.connect(self.commit_mirror)
        self.widget.resetRequested.connect(self.reset_state)
        self.widget.copyModeChanged.connect(self._on_copy_mode_changed)

    def activate(self):
        super().activate()
        self.reset_state()
        self.widget.show_on_canvas()
        from qgis.PyQt.QtCore import QTimer
        QTimer.singleShot(0, self.widget.focus_angle_input)
        QTimer.singleShot(50, self.widget.focus_angle_input)

    def deactivate(self):
        self.widget.save_settings()
        self.widget.hide()
        self.reset_state()
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        for rb in (self.p1_marker, self.axis_rubberband, self.preview_rubberband):
            if rb:
                rb.reset()
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def reset_state(self):
        """Resets mirror tool to initial step (select first axis point)."""
        self.state = self.STATE_FIRST_POINT
        self.p1 = None
        self.p2 = None
        self.widget.set_step(MirrorCanvasWidget.STEP_FIRST_POINT)
        if not self.widget.is_angle_locked:
            self.widget.set_angle(0.0, block_signals=True)
        self._clear_visuals()

    def _clear_visuals(self):
        self.p1_marker.reset()
        self.axis_rubberband.reset()
        self.preview_rubberband.reset()
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def _on_copy_mode_changed(self, is_copy: bool):
        if self.state == self.STATE_SECOND_POINT and self.p1 and self.p2:
            self._update_preview(self.p2)

    def _on_widget_angle_changed(self, angle_deg: float):
        if self.state == self.STATE_SECOND_POINT and self.p1:
            rad = math.radians(angle_deg)
            dist = math.hypot(self.p2.x() - self.p1.x(), self.p2.y() - self.p1.y()) if self.p2 else 10.0
            if dist < 1e-6:
                dist = 10.0
            p2 = QgsPointXY(self.p1.x() + dist * math.cos(rad), self.p1.y() + dist * math.sin(rad))
            self.p2 = p2
            self._update_preview(p2)

    def _get_snapped_point(self, event: QgsMapMouseEvent) -> QgsPointXY:
        """Extracts snapped coordinate from canvas snapping utils or falls back to map point."""
        match = self.canvas.snappingUtils().snapToMap(event.pos())
        if match.isValid():
            self.snap_indicator.setMatch(match)
            self.snap_indicator.setVisible(True)
            return match.point()
        else:
            self.snap_indicator.setVisible(False)
            return self.toMapCoordinates(event.pos())

    def _apply_angle_snap(self, p1: QgsPointXY, p_raw: QgsPointXY, snap_step: float) -> QgsPointXY:
        """Snaps target point angle relative to p1 to the nearest angular step."""
        dx = p_raw.x() - p1.x()
        dy = p_raw.y() - p1.y()
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            return p_raw

        angle_deg = math.degrees(math.atan2(dy, dx))
        snapped_angle = round(angle_deg / snap_step) * snap_step
        rad = math.radians(snapped_angle)
        return QgsPointXY(p1.x() + dist * math.cos(rad), p1.y() + dist * math.sin(rad))

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == _RightButton:
            self._handle_step_back()
            return

        if event.button() != _LeftButton:
            return

        layer = self.currentVectorLayer()
        if not layer or not layer.isEditable():
            return

        pt = self._get_snapped_point(event)

        if self.state == self.STATE_FIRST_POINT:
            # Step 1: Set P1 (first axis point)
            self.p1 = pt
            self.p1_marker.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.p1_marker.addPoint(pt, True)
            self.p1_marker.show()

            self.state = self.STATE_SECOND_POINT
            self.widget.set_step(MirrorCanvasWidget.STEP_SECOND_POINT)

        elif self.state == self.STATE_SECOND_POINT:
            # Step 2: Set P2 and commit mirror
            if self.widget.is_angle_locked and self.p1:
                rad = math.radians(self.widget.angle)
                dx = pt.x() - self.p1.x()
                dy = pt.y() - self.p1.y()
                dist = max(1.0, math.hypot(dx, dy))
                pt = QgsPointXY(self.p1.x() + dist * math.cos(rad), self.p1.y() + dist * math.sin(rad))
            else:
                shift_pressed = bool(_ShiftModifier is not None and (event.modifiers() & _ShiftModifier))
                eff_snap = self.widget.get_effective_snap_step(shift_pressed)
                if eff_snap is not None and eff_snap > 0.0 and self.p1:
                    pt = self._apply_angle_snap(self.p1, pt, eff_snap)

            if self.p1 and (abs(pt.x() - self.p1.x()) > 1e-9 or abs(pt.y() - self.p1.y()) > 1e-9):
                self.p2 = pt
                self.commit_mirror()

        # Always restore focus to the numeric stepper after mouse click
        if self.widget:
            from qgis.PyQt.QtCore import QTimer
            QTimer.singleShot(0, self.widget.focus_angle_input)

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        pt = self._get_snapped_point(event)

        if self.state == self.STATE_SECOND_POINT and self.p1:
            if self.widget.is_angle_locked:
                rad = math.radians(self.widget.angle)
                dx = pt.x() - self.p1.x()
                dy = pt.y() - self.p1.y()
                dist = max(1.0, math.hypot(dx, dy))
                pt = QgsPointXY(self.p1.x() + dist * math.cos(rad), self.p1.y() + dist * math.sin(rad))
            else:
                shift_pressed = bool(_ShiftModifier is not None and (event.modifiers() & _ShiftModifier))
                eff_snap = self.widget.get_effective_snap_step(shift_pressed)
                if eff_snap is not None and eff_snap > 0.0 and self.p1:
                    pt = self._apply_angle_snap(self.p1, pt, eff_snap)

                dx = pt.x() - self.p1.x()
                dy = pt.y() - self.p1.y()
                if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                    axis_deg = math.degrees(math.atan2(dy, dx))
                    self.widget.set_angle(axis_deg, block_signals=True)

            self.p2 = pt
            self._update_preview(pt)

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

    def _update_preview(self, p2: QgsPointXY):
        layer = self.currentVectorLayer()
        if not layer or not self.p1 or not p2:
            return

        # 1. Update Axis Rubberband with extended line
        dx = p2.x() - self.p1.x()
        dy = p2.y() - self.p1.y()
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            return

        ext_len = max(dist * 2.0, self.canvas.extent().width() * 0.5)
        ux, uy = dx / dist, dy / dist
        ext_p1 = QgsPointXY(self.p1.x() - ext_len * ux, self.p1.y() - ext_len * uy)
        ext_p2 = QgsPointXY(self.p1.x() + (dist + ext_len) * ux, self.p1.y() + (dist + ext_len) * uy)

        self.axis_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.axis_rubberband.addPoint(ext_p1, False)
        self.axis_rubberband.addPoint(ext_p2, True)
        self.axis_rubberband.show()

        # 2. Update Geometry Previews
        p1_layer = self.toLayerCoordinates(layer, self.p1)
        p2_layer = self.toLayerCoordinates(layer, p2)

        is_poly = layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry
        rb_type = QgsWkbTypes.GeometryType.PolygonGeometry if is_poly else QgsWkbTypes.GeometryType.LineGeometry

        self.preview_rubberband.reset(rb_type)
        if is_poly:
            self.preview_rubberband.setColor(QColor(37, 99, 235, 230))
            self.preview_rubberband.setFillColor(QColor(59, 130, 246, 60))
        else:
            self.preview_rubberband.setFillColor(QColor(0, 0, 0, 0))
            self.preview_rubberband.setColor(QColor(37, 99, 235, 230))

        if _DashLine is not None:
            self.preview_rubberband.setLineStyle(_DashLine)

        selected_features = list(layer.getSelectedFeatures())
        for feat in selected_features:
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                mirrored_geom = GeometryEngine.mirror_geometry(geom, p1_layer, p2_layer)
                if mirrored_geom and not mirrored_geom.isEmpty():
                    self.preview_rubberband.addGeometry(mirrored_geom, layer)

        self.preview_rubberband.show()

    def commit_mirror(self):
        """Applies the mirror transformation to selected features in the active layer."""
        layer = self.currentVectorLayer()
        if not layer or not layer.isEditable() or not self.p1 or not self.p2:
            self.reset_state()
            return

        selected_features = list(layer.getSelectedFeatures())
        if not selected_features:
            self.reset_state()
            return

        p1_layer = self.toLayerCoordinates(layer, self.p1)
        p2_layer = self.toLayerCoordinates(layer, self.p2)

        is_copy = self.widget.is_copy_mode
        cmd_name = self.tr("CAD Дзеркальне копіювання") if is_copy else self.tr("CAD Дзеркальне відображення")

        layer.beginEditCommand(cmd_name)
        success = True

        if is_copy:
            new_features = []
            for feat in selected_features:
                geom = feat.geometry()
                if geom and not geom.isEmpty():
                    mirrored_geom = GeometryEngine.mirror_geometry(geom, p1_layer, p2_layer)
                    new_feat = QgsFeature(feat)
                    new_feat.setGeometry(mirrored_geom)
                    new_features.append(new_feat)

            if new_features:
                success = layer.addFeatures(new_features)
                if success:
                    new_fids = [f.id() for f in new_features if f.id() != 0]
                    if new_fids:
                        layer.selectByIds(new_fids)
        else:
            for feat in selected_features:
                geom = feat.geometry()
                if geom and not geom.isEmpty():
                    mirrored_geom = GeometryEngine.mirror_geometry(geom, p1_layer, p2_layer)
                    res = layer.changeGeometry(feat.id(), mirrored_geom)
                    if not res:
                        success = False

        if success:
            layer.endEditCommand()
            layer.updateExtents()
            layer.triggerRepaint()
            if hasattr(self.canvas.snappingUtils(), "clearAllLocators"):
                self.canvas.snappingUtils().clearAllLocators()
            self.canvas.refresh()
        else:
            layer.destroyEditCommand()

        self.reset_state()

    def _handle_step_back(self):
        """Steps back one level or cancels."""
        if self.state == self.STATE_SECOND_POINT:
            self.reset_state()
        else:
            self.canvas.unsetMapTool(self)

    def keyPressEvent(self, event):
        key = event.key()

        # If user types digits or math symbols, redirect to angle stepper
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

        if key == _Key_Escape or key == _Key_Backspace:
            self._handle_step_back()
            event.accept()
            return

        elif key in (_Key_Return, _Key_Enter):
            if self.state == self.STATE_SECOND_POINT and self.p1 and self.p2:
                self.commit_mirror()
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

        else:
            super().keyPressEvent(event)

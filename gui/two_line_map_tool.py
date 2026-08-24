# -*- coding: utf-8 -*-
"""
Map tool for interactive Two-Line Fillet & Chamfer with feature merging.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
from typing import Optional

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import (
    QgsMapCanvas,
    QgsMapMouseEvent,
    QgsMapToolEdit,
    QgsRubberBand,
)
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QAction

# Safe cross-version Qt5 / Qt6 constants
_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_DashLine = getattr(Qt.PenStyle, "DashLine", getattr(Qt, "DashLine", 2))
_LeftButton = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RightButton = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_Key_Escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import SegmentMatch, SnappingHelper
    from .two_line_canvas_widget import TwoLineCanvasWidget
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import SegmentMatch, SnappingHelper
    from gui.two_line_canvas_widget import TwoLineCanvasWidget


class TwoLineMapTool(QgsMapToolEdit):
    """Dedicated interactive CAD Map Tool for Filleting/Chamfering two separate lines and merging features."""

    STATE_SELECT_FIRST = 1
    STATE_SELECT_SECOND = 2
    STATE_ADJUSTING = 3

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(
        self,
        canvas: QgsMapCanvas,
        widget: Optional[TwoLineCanvasWidget] = None,
        iface=None,
    ):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.widget = widget or TwoLineCanvasWidget(self.canvas)
        self.state = self.STATE_SELECT_FIRST

        self.first_segment_match: Optional[SegmentMatch] = None
        self.current_segment_match: Optional[SegmentMatch] = None
        self.preview_geom: Optional[QgsGeometry] = None
        self.intersection_point: Optional[QgsPoint] = None

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
        self.preview_rubberband.setColor(QColor(16, 185, 129, 230))  # Emerald green
        if _DashLine is not None:
            self.preview_rubberband.setLineStyle(_DashLine)

        # 3. Corner intersection marker rubberband
        self.corner_marker = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.corner_marker.setIcon(QgsRubberBand.IconType.ICON_CROSS)
        self.corner_marker.setIconSize(10)
        self.corner_marker.setWidth(2)
        self.corner_marker.setColor(QColor(234, 88, 12, 255))  # Amber

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        # Connect widget parameter change signals for real-time updates
        if hasattr(self.widget, "parametersChanged"):
            self.widget.parametersChanged.connect(self._on_parameters_changed)
        if hasattr(self.widget, "modeChanged"):
            self.widget.modeChanged.connect(lambda _: self._on_parameters_changed())
        if hasattr(self.widget, "commitRequested"):
            self.widget.commitRequested.connect(self._commit_change)

    def activate(self):
        super().activate()
        self._clear_preview()
        self.state = self.STATE_SELECT_FIRST
        if self.widget:
            self.widget.set_step(TwoLineCanvasWidget.STEP_FIRST_LINE)
            self.widget.show_on_canvas()

    def deactivate(self):
        self._clear_preview()
        if self.widget:
            self.widget.hide()
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        for rb in (self.edge1_rubberband, self.edge2_rubberband, self.preview_rubberband, self.corner_marker):
            if rb:
                rb.reset()

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable() and layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
            return layer
        return None

    def _is_current_parameter_locked(self) -> bool:
        if isinstance(self.widget, TwoLineCanvasWidget):
            if self.widget.mode == TwoLineCanvasWidget.MODE_FILLET:
                return self.widget.is_radius_locked
            else:
                if self.widget.is_linked:
                    return self.widget.is_dist1_locked
                return self.widget.is_dist1_locked and self.widget.is_dist2_locked
        return False

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_preview()
            return

        map_point = event.mapPoint()

        if self.state == self.STATE_SELECT_FIRST:
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

        elif self.state == self.STATE_SELECT_SECOND:
            # Step 2: Hovering over second line
            m1 = self.first_segment_match
            m2 = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if (
                m2
                and (m2.fid != m1.fid or m2.part_idx != m1.part_idx or m2.segment_idx != m1.segment_idx)
            ):
                self.current_segment_match = m2
                p1_map = self.toMapCoordinates(layer, m2.p1)
                p2_map = self.toMapCoordinates(layer, m2.p2)
                self.edge2_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.edge2_rubberband.setColor(QColor(59, 130, 246, 230))
                self.edge2_rubberband.setWidth(4)
                self.edge2_rubberband.addPoint(p1_map, False)
                self.edge2_rubberband.addPoint(p2_map, True)
                self.edge2_rubberband.show()

                # Preview intersection and geometry
                self._update_preview(layer)
            else:
                self.edge2_rubberband.reset()
                self.preview_rubberband.reset()
                self.corner_marker.reset()
                self.preview_geom = None
                self.intersection_point = None

        elif self.state == self.STATE_ADJUSTING:
            # Step 3: Interactive dragging of radius/chamfer distance
            self._update_values_from_cursor(layer, map_point)
            self._update_preview(layer)

    def _update_values_from_cursor(self, layer: QgsVectorLayer, map_point: QgsPointXY):
        """Calculates radius or distance dynamically from cursor position relative to intersection V."""
        if not self.first_segment_match or not self.current_segment_match:
            return

        m1 = self.first_segment_match
        m2 = self.current_segment_match
        curve1 = m1.geometry.constGet()
        curve2 = m2.geometry.constGet()
        if not curve1 or not curve2:
            return

        a1, b1 = curve1.pointN(m1.segment_idx), curve1.pointN(m1.segment_idx + 1)
        a2, b2 = curve2.pointN(m2.segment_idx), curve2.pointN(m2.segment_idx + 1)
        v = GeometryEngine.compute_line_intersection(a1, b1, a2, b2)
        if not v:
            return

        layer_pt = self.toLayerCoordinates(layer, map_point)
        dx = layer_pt.x() - v.x()
        dy = layer_pt.y() - v.y()
        cursor_dist = math.hypot(dx, dy)

        is_geo = layer.crs().isGeographic() if layer.crs().isValid() else False
        min_limit = 0.000001 if is_geo else 0.01

        # Calculate unit ray directions
        len1 = math.hypot(b1.x() - a1.x(), b1.y() - a1.y())
        len2 = math.hypot(b2.x() - a2.x(), b2.y() - a2.y())
        if len1 < 1e-9 or len2 < 1e-9:
            return

        ud1x = (b1.x() - a1.x()) / len1
        ud1y = (b1.y() - a1.y()) / len1
        t_click1 = (m1.point.x() - v.x()) * ud1x + (m1.point.y() - v.y()) * ud1y
        u1x = ud1x if t_click1 > 0 else -ud1x
        u1y = ud1y if t_click1 > 0 else -ud1y

        ud2x = (b2.x() - a2.x()) / len2
        ud2y = (b2.y() - a2.y()) / len2
        t_click2 = (m2.point.x() - v.x()) * ud2x + (m2.point.y() - v.y()) * ud2y
        u2x = ud2x if t_click2 > 0 else -ud2x
        u2y = ud2y if t_click2 > 0 else -ud2y

        dot = max(-1.0, min(1.0, u1x * u2x + u1y * u2y))
        angle = math.acos(dot)
        if angle < 1e-4 or angle > (math.pi - 1e-4):
            return

        if self.widget.mode == TwoLineCanvasWidget.MODE_FILLET:
            if not self.widget.is_radius_locked:
                # Tangent distance projection along rays
                proj1 = max(0.0, dx * u1x + dy * u1y)
                proj2 = max(0.0, dx * u2x + dy * u2y)
                tan_dist = max(proj1, proj2, cursor_dist * 0.707)
                calc_r = tan_dist * math.tan(angle / 2.0)
                rounded_r = max(min_limit, round(calc_r, 6 if is_geo else (4 if calc_r < 1.0 else 3)))
                self.widget.set_radius(rounded_r, block_signals=True)
        else:
            proj1 = max(0.0, dx * u1x + dy * u1y)
            proj2 = max(0.0, dx * u2x + dy * u2y)
            if self.widget.is_linked:
                d = max(proj1, proj2, cursor_dist * 0.707)
                rounded_d = max(min_limit, round(d, 6 if is_geo else (4 if d < 1.0 else 3)))
                if not self.widget.is_dist1_locked:
                    self.widget.set_distance1(rounded_d, block_signals=True)
            else:
                d1 = max(min_limit, round(proj1, 6 if is_geo else (4 if proj1 < 1.0 else 3)))
                d2 = max(min_limit, round(proj2, 6 if is_geo else (4 if proj2 < 1.0 else 3)))
                if not self.widget.is_dist1_locked:
                    self.widget.set_distance1(d1, block_signals=True)
                if not self.widget.is_dist2_locked:
                    self.widget.set_distance2(d2, block_signals=True)

    def _update_preview(self, layer: Optional[QgsVectorLayer] = None):
        """Recomputes and displays the fillet/chamfer preview."""
        if not layer:
            layer = self.current_vector_layer()
        if not layer or not self.first_segment_match or not self.current_segment_match:
            return

        m1 = self.first_segment_match
        m2 = self.current_segment_match

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
        )

        if res:
            new_geom, v_sharp, t1, t2 = res
            self.preview_geom = new_geom
            self.intersection_point = v_sharp

            self.preview_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self.preview_rubberband.setToGeometry(new_geom, layer)
            self.preview_rubberband.setColor(QColor(16, 185, 129, 230))
            self.preview_rubberband.setWidth(4)
            if _DashLine is not None:
                self.preview_rubberband.setLineStyle(_DashLine)
            self.preview_rubberband.show()

            v_xy = QgsPointXY(v_sharp.x(), v_sharp.y())
            v_map = self.toMapCoordinates(layer, v_xy)
            self.corner_marker.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.corner_marker.addPoint(v_map, True)
            self.corner_marker.show()
        else:
            self.preview_geom = None
            self.intersection_point = None
            self.preview_rubberband.reset()
            self.corner_marker.reset()

    def _on_parameters_changed(self):
        layer = self.current_vector_layer()
        if layer and self.first_segment_match and self.current_segment_match:
            self._update_preview(layer)

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == _RightButton:
            self._handle_step_back()
            return

        if event.button() != _LeftButton:
            return

        layer = self.current_vector_layer()
        if not layer:
            return

        map_point = event.mapPoint()

        if self.state == self.STATE_SELECT_FIRST:
            # Step 1: Select first line
            match = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if match:
                self.first_segment_match = match
                p1_map = self.toMapCoordinates(layer, match.p1)
                p2_map = self.toMapCoordinates(layer, match.p2)
                self.edge1_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.edge1_rubberband.setColor(QColor(30, 58, 138, 230))
                self.edge1_rubberband.setWidth(4)
                self.edge1_rubberband.addPoint(p1_map, False)
                self.edge1_rubberband.addPoint(p2_map, True)
                self.edge1_rubberband.show()

                self.state = self.STATE_SELECT_SECOND
                if self.widget:
                    self.widget.set_step(TwoLineCanvasWidget.STEP_SECOND_LINE)

        elif self.state == self.STATE_SELECT_SECOND:
            # Step 2: Select second line
            match = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if (
                match
                and (
                    match.fid != self.first_segment_match.fid
                    or match.part_idx != self.first_segment_match.part_idx
                    or match.segment_idx != self.first_segment_match.segment_idx
                )
            ):
                self.current_segment_match = match
                self._update_preview(layer)

                if self._is_current_parameter_locked():
                    # If locked -> commit immediately
                    self._commit_change()
                else:
                    # If unlocked -> switch to interactive adjusting (Step 3)
                    self.state = self.STATE_ADJUSTING
                    if self.widget:
                        self.widget.set_step(TwoLineCanvasWidget.STEP_ADJUST)
                    self._update_values_from_cursor(layer, map_point)
                    self._update_preview(layer)

        elif self.state == self.STATE_ADJUSTING:
            # Step 3: Click commits the final fillet/chamfer geometry
            self._commit_change()

    def keyPressEvent(self, event):
        if event.key() == _Key_Escape:
            self._handle_step_back()
            return
        super().keyPressEvent(event)

    def _handle_step_back(self):
        """Reverts Step 3 -> Step 2 -> Step 1 -> Clear."""
        if self.state == self.STATE_ADJUSTING:
            self.state = self.STATE_SELECT_SECOND
            self.preview_rubberband.reset()
            self.preview_geom = None
            if self.widget:
                self.widget.set_step(TwoLineCanvasWidget.STEP_SECOND_LINE)
        elif self.state == self.STATE_SELECT_SECOND:
            self.first_segment_match = None
            self.current_segment_match = None
            self.preview_geom = None
            self.intersection_point = None
            self.edge1_rubberband.reset()
            self.edge2_rubberband.reset()
            self.preview_rubberband.reset()
            self.corner_marker.reset()
            self.state = self.STATE_SELECT_FIRST
            if self.widget:
                self.widget.set_step(TwoLineCanvasWidget.STEP_FIRST_LINE)
        else:
            self._clear_preview()

    def _commit_change(self):
        """Commits the final preview geometry to the vector layer with robust dialog cancellation handling."""
        layer = self.current_vector_layer()
        if not layer or not self.first_segment_match or not self.current_segment_match or not self.preview_geom:
            return

        m1 = self.first_segment_match
        m2 = self.current_segment_match
        new_geom = self.preview_geom

        self._apply_two_line_operation(layer, m1.fid, m2.fid, new_geom)

        self._clear_preview()
        self.state = self.STATE_SELECT_FIRST
        if self.widget:
            self.widget.set_step(TwoLineCanvasWidget.STEP_FIRST_LINE)

    def _apply_two_line_operation(
        self,
        layer: QgsVectorLayer,
        fid1: int,
        fid2: int,
        new_geom: QgsGeometry,
    ):
        """Applies the joined geometry to the vector layer with feature merging and transactional cancel check."""
        if fid1 == fid2:
            # Intra-feature join: update geometry directly
            layer.beginEditCommand(self.tr("Скруглення / фаска лінії"))
            layer.changeGeometry(fid1, new_geom)
            layer.endEditCommand()
            layer.triggerRepaint()
            return

        # Check merge settings
        always_first = self.widget.always_use_first_feature if self.widget else False

        if always_first or not self.iface or not hasattr(self.iface, "mainWindow") or not self.iface.mainWindow():
            # Apply merge directly: update fid1 and delete fid2
            layer.beginEditCommand(self.tr("Скруглення / фаска двох ліній з об'єднанням"))
            layer.changeGeometry(fid1, new_geom)
            layer.deleteFeature(fid2)
            layer.endEditCommand()
            layer.triggerRepaint()
            return

        # Launch QGIS native merge dialog
        layer.selectByIds([fid1, fid2])
        merge_action = self.iface.mainWindow().findChild(QAction, "mActionMergeFeatureAttributes")
        if not merge_action:
            merge_action = self.iface.mainWindow().findChild(QAction, "mActionMergeFeatures")

        if merge_action:
            # Execute QGIS native dialog
            merge_action.trigger()

            # Transactional Check: did user confirm or cancel?
            # When QGIS merges features, fid2 is deleted (or count of features drops and selection has 1 feature).
            remaining_selected = layer.selectedFeatureIds()
            f2_valid = layer.getFeature(fid2).isValid()

            if not f2_valid or (len(remaining_selected) == 1 and fid2 not in remaining_selected):
                # User confirmed OK in QGIS merge dialog
                surviving_id = remaining_selected[0] if remaining_selected else fid1
                layer.changeGeometry(surviving_id, new_geom)
                layer.triggerRepaint()
            else:
                # User clicked Cancel in dialog -> do NOT modify geometry or delete features!
                layer.removeSelection()
                layer.triggerRepaint()
        else:
            # Fallback
            layer.beginEditCommand(self.tr("Скруглення / фаска двох ліній з об'єднанням"))
            layer.changeGeometry(fid1, new_geom)
            layer.deleteFeature(fid2)
            layer.endEditCommand()
            layer.triggerRepaint()

    def _clear_preview(self):
        self.first_segment_match = None
        self.current_segment_match = None
        self.preview_geom = None
        self.intersection_point = None
        self.edge1_rubberband.reset()
        self.edge2_rubberband.reset()
        self.preview_rubberband.reset()
        self.corner_marker.reset()

# -*- coding: utf-8 -*-
"""
Map tool for interactive Unfillet / Unchamfer (Corner Restoration) in QGIS.
Uses CAD Two-Edge selection workflow:
1. Click on first edge
2. Hover over second edge -> live intersection preview
3. Click on second edge -> commits corner reconstruction
"""

from typing import Optional

from qgis.core import (
    Qgis,
    QgsGeometry,
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
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QCursor

# Safe cross-version Qt5 / Qt6 constants
_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_DashLine = getattr(Qt.PenStyle, "DashLine", getattr(Qt, "DashLine", 2))
_LeftButton = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RightButton = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_Key_Escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import SegmentMatch, SnappingHelper
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import SegmentMatch, SnappingHelper


class RestoreMapTool(QgsMapToolEdit):
    """Dedicated interactive CAD Map Tool for restoring sharp corners."""

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas

        self.first_segment_match: Optional[SegmentMatch] = None
        self.current_segment_match: Optional[SegmentMatch] = None
        self.preview_geom: Optional[QgsGeometry] = None

        # 1. Edge selection rubberbands
        self.edge1_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.edge1_rubberband.setWidth(4)
        self.edge1_rubberband.setColor(QColor(234, 88, 12, 230))  # Amber

        self.edge2_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.edge2_rubberband.setWidth(4)
        self.edge2_rubberband.setColor(QColor(245, 158, 11, 230))  # Light Amber

        # 2. Geometry preview rubberband
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.preview_rubberband.setWidth(4)
        if _DashLine is not None:
            self.preview_rubberband.setLineStyle(_DashLine)

        # 3. Corner intersection marker rubberband
        self.corner_marker = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.corner_marker.setIcon(QgsRubberBand.ICON_CROSS)
        self.corner_marker.setIconSize(10)
        self.corner_marker.setWidth(2)
        self.corner_marker.setColor(QColor(234, 88, 12, 255))

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

    def activate(self):
        super().activate()
        self._clear_preview()

    def deactivate(self):
        self._clear_preview()
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        for rb in (self.edge1_rubberband, self.edge2_rubberband, self.preview_rubberband, self.corner_marker):
            if rb:
                rb.reset()

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable():
            return layer
        return None

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_preview()
            return

        map_point = event.mapPoint()

        if self.first_segment_match is None:
            # Step 1: Hovering over first edge
            match = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if match:
                self.current_segment_match = match
                p1_map = self.toMapCoordinates(layer, match.p1)
                p2_map = self.toMapCoordinates(layer, match.p2)
                self.edge1_rubberband.reset(QgsWkbTypes.LineGeometry)
                self.edge1_rubberband.setColor(QColor(234, 88, 12, 230))
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
        else:
            # Step 2: Hovering over second adjacent edge
            m1 = self.first_segment_match
            m2 = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)
            if (
                m2
                and m2.fid == m1.fid
                and m2.part_idx == m1.part_idx
                and m2.ring_idx == m1.ring_idx
                and m2.segment_idx != m1.segment_idx
            ):
                self.current_segment_match = m2
                p1_map = self.toMapCoordinates(layer, m2.p1)
                p2_map = self.toMapCoordinates(layer, m2.p2)
                self.edge2_rubberband.reset(QgsWkbTypes.LineGeometry)
                self.edge2_rubberband.setColor(QColor(245, 158, 11, 230))
                self.edge2_rubberband.setWidth(4)
                self.edge2_rubberband.addPoint(p1_map, False)
                self.edge2_rubberband.addPoint(p2_map, True)
                self.edge2_rubberband.show()

                restore_res = GeometryEngine.restore_sharp_corner_between_segments(
                    m1.geometry, m1.part_idx, m1.ring_idx, m1.segment_idx, m2.segment_idx
                )
                if restore_res:
                    new_geom, v_sharp = restore_res
                    self.preview_geom = new_geom
                    stroke_color = QColor(234, 88, 12, 230)
                    fill_color = QColor(234, 88, 12, 65)
                    if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                        self.preview_rubberband.reset(QgsWkbTypes.PolygonGeometry)
                        self.preview_rubberband.setFillColor(fill_color)
                        self.preview_rubberband.setStrokeColor(stroke_color)
                        self.preview_rubberband.setWidth(4)
                    else:
                        self.preview_rubberband.reset(QgsWkbTypes.LineGeometry)
                        self.preview_rubberband.setFillColor(QColor(0, 0, 0, 0))
                        self.preview_rubberband.setColor(stroke_color)
                        self.preview_rubberband.setWidth(4)
                    if _DashLine is not None:
                        self.preview_rubberband.setLineStyle(_DashLine)
                    self.preview_rubberband.setToGeometry(new_geom, layer)
                    self.preview_rubberband.show()

                    v_xy = QgsPointXY(v_sharp.x(), v_sharp.y())
                    v_map = self.toMapCoordinates(layer, v_xy)
                    self.corner_marker.reset(QgsWkbTypes.PointGeometry)
                    self.corner_marker.setColor(stroke_color)
                    self.corner_marker.addPoint(v_map, True)
                    self.corner_marker.show()
                else:
                    self.preview_geom = None
                    self.preview_rubberband.reset()
                    self.corner_marker.reset()
            else:
                self.current_segment_match = None
                self.edge2_rubberband.reset()
                self.preview_geom = None
                self.preview_rubberband.reset()
                self.corner_marker.reset()

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            return

        if event.button() == _LeftButton:
            if self.first_segment_match is None:
                if self.current_segment_match:
                    self.first_segment_match = self.current_segment_match
            else:
                if self.preview_geom and self.first_segment_match:
                    fid = self.first_segment_match.fid
                    new_geom = self.preview_geom
                    layer.beginEditCommand(self.tr("Відновлення кута"))
                    layer.changeGeometry(fid, new_geom)
                    layer.endEditCommand()
                    self._clear_preview()

        elif event.button() == _RightButton:
            self._cancel_operation()

    def keyPressEvent(self, event):
        if event.key() == _Key_Escape:
            self._cancel_operation()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _cancel_operation(self):
        self._clear_preview()

    def _clear_preview(self):
        self.edge1_rubberband.reset()
        self.edge2_rubberband.reset()
        self.preview_rubberband.reset()
        self.corner_marker.reset()
        self.first_segment_match = None
        self.current_segment_match = None
        self.preview_geom = None

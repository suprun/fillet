# -*- coding: utf-8 -*-
"""
Map tool for interactive Fillet & Chamfer editing in QGIS.
Supports on-canvas CAD HUD widget, dynamic preview with polygon transparency,
and system-style snapping square marker.
"""

from typing import Optional, Union

from qgis.core import (
    Qgis,
    QgsGeometry,
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
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QCursor

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import SnappingHelper, VertexMatch
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import SnappingHelper, VertexMatch
from .canvas_widget import FilletCanvasWidget
from .settings_widget import FilletSettingsWidget


class FilletMapTool(QgsMapToolEdit):
    """Interactive Map Tool for filleting and chamfering vertices."""

    def __init__(self, canvas: QgsMapCanvas, widget: Union[FilletCanvasWidget, FilletSettingsWidget]):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.current_match: Optional[VertexMatch] = None
        self.preview_geom: Optional[QgsGeometry] = None

        # System snapping square marker on vertex
        self.marker_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.marker_rubberband.setIcon(QgsRubberBand.ICON_BOX)
        self.marker_rubberband.setIconSize(12)
        self.marker_rubberband.setWidth(2)
        self.marker_rubberband.setColor(self._get_snap_color())

        # Geometry preview rubberband (configured dynamically for Polygon / Line)
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.preview_rubberband.setWidth(4)
        self.preview_rubberband.setLineStyle(Qt.DashLine)

        self.setCursor(QCursor(Qt.CrossCursor))
        self.widget.parametersChanged.connect(self._update_preview)

    def _get_snap_color(self) -> QColor:
        """Reads the system snapping color from QGIS settings."""
        try:
            s = QgsSettings()
            val = s.value("digitizing/snap_color", QColor(255, 0, 255))
            if isinstance(val, QColor):
                return val
            elif isinstance(val, str):
                return QColor(val)
        except Exception:
            pass
        return QColor(255, 0, 255)

    def activate(self):
        super().activate()
        self.marker_rubberband.reset()
        self.marker_rubberband.setColor(self._get_snap_color())
        self.preview_rubberband.reset()
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.show_on_canvas()

    def deactivate(self):
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.hide()
        self.marker_rubberband.reset()
        self.preview_rubberband.reset()
        self.current_match = None
        self.preview_geom = None
        super().deactivate()

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
        match = SnappingHelper.find_vertex_at_position(layer, self.canvas, map_point)

        if match:
            self.current_match = match

            # Show system snapping square marker on vertex
            self.marker_rubberband.reset(QgsWkbTypes.PointGeometry)
            self.marker_rubberband.setIcon(QgsRubberBand.ICON_BOX)
            self.marker_rubberband.setIconSize(12)
            self.marker_rubberband.setWidth(2)
            self.marker_rubberband.setColor(self._get_snap_color())
            self.marker_rubberband.addPoint(match.point, True)
            self.marker_rubberband.show()

            # If radius/distance is unlocked, dynamically update value from mouse distance
            if isinstance(self.widget, FilletCanvasWidget):
                dist = GeometryEngine.distance(match.point, map_point)
                if dist > 0.0001:
                    if self.widget.mode == FilletCanvasWidget.MODE_FILLET and not self.widget.is_radius_locked:
                        self.widget.set_radius(round(dist, 3), block_signals=True)
                    elif self.widget.mode == FilletCanvasWidget.MODE_CHAMFER and not self.widget.is_dist1_locked:
                        self.widget.set_distance1(round(dist, 3), block_signals=True)

            # Calculate and show preview
            self._update_preview()
        else:
            self._clear_preview()

    def _update_preview(self):
        if not self.current_match or not self.isActive():
            return

        match = self.current_match
        layer = self.current_vector_layer()
        if not layer:
            return

        mode = self.widget.mode

        if mode == FilletCanvasWidget.MODE_FILLET:
            new_geom = GeometryEngine.apply_fillet_to_geometry(
                match.geometry,
                part_idx=match.part_idx,
                ring_idx=match.ring_idx,
                vertex_idx=match.vertex_idx,
                radius=self.widget.radius,
                segments_count=self.widget.segments_count,
            )
        else:
            new_geom = GeometryEngine.apply_chamfer_to_geometry(
                match.geometry,
                part_idx=match.part_idx,
                ring_idx=match.ring_idx,
                vertex_idx=match.vertex_idx,
                dist1=self.widget.distance1,
                dist2=self.widget.distance2,
            )

        if mode == FilletCanvasWidget.MODE_FILLET:
            stroke_color = QColor(37, 99, 235, 230)  # Blue as in fillet.svg
            fill_color = QColor(37, 99, 235, 65)
        else:
            stroke_color = QColor(5, 150, 105, 230)  # Green #059669 as in chamfer.svg
            fill_color = QColor(5, 150, 105, 65)

        if new_geom and not new_geom.isEmpty():
            self.preview_geom = new_geom

            # Setup styling based on geometry type (semi-transparent fill for polygons)
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

            self.preview_rubberband.setLineStyle(Qt.DashLine)
            self.preview_rubberband.setToGeometry(new_geom, layer)
            self.preview_rubberband.show()
        else:
            self.preview_geom = None
            self.preview_rubberband.reset()

    def canvasReleaseEvent(self, event: QgsMapMouseEvent):
        if event.button() == Qt.LeftButton:
            layer = self.current_vector_layer()
            if not layer or not self.current_match or not self.preview_geom:
                return

            mode_name = (
                self.tr("Скруглення вершини")
                if self.widget.mode == FilletCanvasWidget.MODE_FILLET
                else self.tr("Фаска вершини")
            )

            layer.beginEditCommand(mode_name)
            success = layer.changeGeometry(self.current_match.fid, self.preview_geom)
            if success:
                layer.endEditCommand()
                self.canvas.refresh()
            else:
                layer.destroyEditCommand()

            self._clear_preview()

        elif event.button() == Qt.RightButton:
            self._clear_preview()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._clear_preview()
        else:
            super().keyPressEvent(event)

    def _clear_preview(self):
        self.marker_rubberband.reset()
        self.preview_rubberband.reset()
        self.current_match = None
        self.preview_geom = None

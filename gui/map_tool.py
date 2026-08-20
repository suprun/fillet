# -*- coding: utf-8 -*-
"""
Map tool for interactive Fillet & Chamfer editing in QGIS.
Supports on-canvas CAD HUD widget, two-step CAD interaction model (QGIS 4.0 style),
CRS-aware snapping square marker, tangent touch points visualization,
live preview with polygon transparency, and full keyboard navigation (Tab, Enter, Escape, Space).
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
    """Interactive Map Tool for filleting and chamfering vertices in QGIS 4.0 CAD style."""

    STATE_HOVER = "hover"
    STATE_ADJUSTING = "adjusting"

    def __init__(self, canvas: QgsMapCanvas, widget: Union[FilletCanvasWidget, FilletSettingsWidget]):
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget

        self.state = self.STATE_HOVER
        self.current_match: Optional[VertexMatch] = None
        self.preview_geom: Optional[QgsGeometry] = None

        # 1. System snapping square marker on vertex (rendered in map canvas CRS)
        self.marker_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.marker_rubberband.setIcon(QgsRubberBand.ICON_BOX)
        self.marker_rubberband.setIconSize(12)
        self.marker_rubberband.setWidth(2)
        self.marker_rubberband.setColor(self._get_snap_color())

        # 2. Tangent / touch point markers (T1, T2 rendered in map canvas CRS)
        self.tangent_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.tangent_rubberband.setIcon(QgsRubberBand.ICON_CROSS)
        self.tangent_rubberband.setIconSize(10)
        self.tangent_rubberband.setWidth(2)
        self.tangent_rubberband.setColor(QColor(255, 140, 0, 240))

        # 3. Geometry preview rubberband (configured dynamically for Polygon / Line)
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.preview_rubberband.setWidth(4)
        self.preview_rubberband.setLineStyle(Qt.DashLine)

        self.setCursor(QCursor(Qt.CrossCursor))
        self.widget.parametersChanged.connect(self._update_preview)
        if hasattr(self.widget, "commitRequested"):
            self.widget.commitRequested.connect(self._commit_change)

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
        self.state = self.STATE_HOVER
        self._clear_preview()
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.show_on_canvas()

    def deactivate(self):
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.hide()
        self.state = self.STATE_HOVER
        self._clear_preview()
        super().deactivate()

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable():
            return layer
        return None

    def _is_current_parameter_locked(self) -> bool:
        if isinstance(self.widget, FilletCanvasWidget):
            if self.widget.mode == FilletCanvasWidget.MODE_FILLET:
                return self.widget.is_radius_locked
            else:
                if self.widget.is_linked:
                    return self.widget.is_dist1_locked
                else:
                    return self.widget.is_dist1_locked and self.widget.is_dist2_locked
        return True

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_preview()
            return

        map_point = event.mapPoint()

        if self.state == self.STATE_HOVER:
            match = SnappingHelper.find_vertex_at_position(layer, self.canvas, map_point)
            if match:
                self.current_match = match
                self._show_vertex_marker(layer, match.point)
                # If parameter is locked, show preview; if unlocked, only show snap marker until clicked
                if self._is_current_parameter_locked():
                    self._update_preview()
                else:
                    self.preview_rubberband.reset()
                    self.tangent_rubberband.reset()
            else:
                self._clear_preview()

        elif self.state == self.STATE_ADJUSTING:
            if self.current_match and isinstance(self.widget, FilletCanvasWidget):
                # Convert mouse point to layer CRS for correct distance calculation
                layer_point = self.toLayerCoordinates(layer, map_point)
                dist = GeometryEngine.distance(self.current_match.point, layer_point)
                if dist > 0.000001:
                    rounded_dist = round(dist, 4 if dist < 1.0 else 3)
                    if self.widget.mode == FilletCanvasWidget.MODE_FILLET:
                        if not self.widget.is_radius_locked:
                            self.widget.set_radius(rounded_dist, block_signals=True)
                    else:
                        if self.widget.is_linked:
                            if not self.widget.is_dist1_locked:
                                self.widget.set_distance1(rounded_dist, block_signals=True)
                        else:
                            if not self.widget.is_dist1_locked:
                                self.widget.set_distance1(rounded_dist, block_signals=True)
                            elif not self.widget.is_dist2_locked:
                                self.widget.set_distance2(rounded_dist, block_signals=True)
            self._update_preview()

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == Qt.LeftButton:
            layer = self.current_vector_layer()
            if not layer:
                return

            if self.state == self.STATE_HOVER:
                map_point = event.mapPoint()
                match = SnappingHelper.find_vertex_at_position(layer, self.canvas, map_point)
                if match:
                    self.current_match = match
                    self._show_vertex_marker(layer, match.point)

                    # If parameters are locked, single click can commit directly
                    if self._is_current_parameter_locked():
                        self._update_preview()
                        self._commit_change()
                    else:
                        self.state = self.STATE_ADJUSTING
                        self._update_preview()

            elif self.state == self.STATE_ADJUSTING:
                # Second click commits the modification (Two-step CAD workflow)
                self._commit_change()

        elif event.button() == Qt.RightButton:
            # Right click cancels active adjustment or clears preview
            self._cancel_operation()

    def _show_vertex_marker(self, layer: QgsVectorLayer, point: QgsPointXY):
        """Displays the snapping square marker transformed to map coordinates."""
        map_pt = self.toMapCoordinates(layer, point)
        self.marker_rubberband.reset(QgsWkbTypes.PointGeometry)
        self.marker_rubberband.setIcon(QgsRubberBand.ICON_BOX)
        self.marker_rubberband.setIconSize(12)
        self.marker_rubberband.setWidth(2)
        self.marker_rubberband.setColor(self._get_snap_color())
        self.marker_rubberband.addPoint(map_pt, True)
        self.marker_rubberband.show()

    def _update_preview(self):
        if not self.current_match or not self.isActive():
            return

        match = self.current_match
        layer = self.current_vector_layer()
        if not layer:
            return

        is_fillet = (
            self.widget.mode == FilletCanvasWidget.MODE_FILLET
            if isinstance(self.widget, FilletCanvasWidget)
            else True
        )

        if is_fillet:
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
            # Tangent points
            t1, t2 = GeometryEngine.compute_tangent_points_for_vertex(
                match.geometry,
                match.part_idx,
                match.ring_idx,
                match.vertex_idx,
                is_fillet=True,
                val1=radius,
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
            # Tangent points
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

        # 1. Update geometry preview
        if new_geom and not new_geom.isEmpty():
            self.preview_geom = new_geom
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

        # 2. Update tangent touch markers (transformed to map coordinates)
        if t1 and t2:
            t1_map = self.toMapCoordinates(layer, t1)
            t2_map = self.toMapCoordinates(layer, t2)
            self.tangent_rubberband.reset(QgsWkbTypes.PointGeometry)
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

        is_fillet = (
            self.widget.mode == FilletCanvasWidget.MODE_FILLET
            if isinstance(self.widget, FilletCanvasWidget)
            else True
        )
        mode_name = self.tr("Скруглення вершини") if is_fillet else self.tr("Фаска вершини")

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

        if key in (Qt.Key_Return, Qt.Key_Enter):
            # Commit with Enter
            self._commit_change()
            event.accept()

        elif key == Qt.Key_Escape:
            # Cancel with Escape
            self._cancel_operation()
            event.accept()

        elif key == Qt.Key_Tab:
            # Tab focuses primary input in HUD widget
            if isinstance(self.widget, FilletCanvasWidget):
                self.widget.focus_primary_input()
                event.accept()

        elif key == Qt.Key_Space:
            # Space toggles lock
            if isinstance(self.widget, FilletCanvasWidget):
                self.widget.toggle_active_lock()
                event.accept()

        else:
            super().keyPressEvent(event)

    def _clear_preview(self):
        self.marker_rubberband.reset()
        self.tangent_rubberband.reset()
        self.preview_rubberband.reset()
        self.current_match = None
        self.preview_geom = None

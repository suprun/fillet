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

        # 1. Native QGIS system snapping indicator (100% native styling and snapping engine integration)
        self.snap_indicator = QgsSnapIndicator(self.canvas)

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

    def activate(self):
        super().activate()
        self.state = self.STATE_HOVER
        self._clear_preview()
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.show_on_canvas()
            self.widget.focus_primary_input()

    def deactivate(self):
        if isinstance(self.widget, FilletCanvasWidget):
            self.widget.hide()
        self.state = self.STATE_HOVER
        self._clear_preview()
        super().deactivate()

    def cleanup(self):
        """Cleans up rubberbands, indicators, and disconnected signals."""
        self.deactivate()
        try:
            self.widget.parametersChanged.disconnect(self._update_preview)
        except Exception:
            pass
        if hasattr(self.widget, "commitRequested"):
            try:
                self.widget.commitRequested.disconnect(self._commit_change)
            except Exception:
                pass

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
                self._show_vertex_marker(layer, match)
                # If parameter is locked, show preview; if unlocked, only show snap indicator until clicked
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
                        rounded_dist = round(dist, 4 if dist < 1.0 else 3)
                        if not self.widget.is_radius_locked:
                            self.widget.set_radius(rounded_dist, block_signals=True)
                    else:
                        if p_prev and v and p_next:
                            u1x, u1y, len1 = GeometryEngine.normalize_vector(p_prev.x() - v.x(), p_prev.y() - v.y())
                            u2x, u2y, len2 = GeometryEngine.normalize_vector(p_next.x() - v.x(), p_next.y() - v.y())
                            if self.widget.is_linked:
                                # Isosceles chamfer: strictly bounded by shorter edge
                                max_d = min(len1, len2) * 0.9999
                                dist = min(dist, max_d)
                                rounded_dist = round(dist, 4 if dist < 1.0 else 3)
                                if not self.widget.is_dist1_locked:
                                    self.widget.set_distance1(rounded_dist, block_signals=True)
                            else:
                                wx = layer_point.x() - v.x()
                                wy = layer_point.y() - v.y()
                                proj1 = wx * u1x + wy * u1y
                                proj2 = wx * u2x + wy * u2y
                                d1 = min(len1 * 0.9999, max(0.001, abs(proj1)))
                                d2 = min(len2 * 0.9999, max(0.001, abs(proj2)))
                                if not self.widget.is_dist1_locked:
                                    self.widget.set_distance1(round(d1, 4 if d1 < 1.0 else 3), block_signals=True)
                                if not self.widget.is_dist2_locked:
                                    self.widget.set_distance2(round(d2, 4 if d2 < 1.0 else 3), block_signals=True)
                        else:
                            rounded_dist = round(dist, 4 if dist < 1.0 else 3)
                            if not self.widget.is_dist1_locked:
                                self.widget.set_distance1(rounded_dist, block_signals=True)
                            if not self.widget.is_dist2_locked:
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
                    self._show_vertex_marker(layer, match)

                    # If parameters are locked, single click can commit directly
                    if self._is_current_parameter_locked():
                        self._update_preview()
                        self._commit_change()
                    else:
                        self.state = self.STATE_ADJUSTING
                        self._update_preview()
                        # Maintain focus on numeric stepper after first click
                        if isinstance(self.widget, FilletCanvasWidget):
                            self.widget.focus_primary_input()

            elif self.state == self.STATE_ADJUSTING:
                # Second click commits the modification (Two-step CAD workflow)
                self._commit_change()

        elif event.button() == Qt.RightButton:
            # Right click cancels active adjustment or clears preview
            self._cancel_operation()

    def _show_vertex_marker(self, layer: QgsVectorLayer, match: VertexMatch):
        """Displays the native QGIS system snapping indicator on vertex."""
        loc_match = QgsPointLocator.Match(
            QgsPointLocator.Vertex,
            layer,
            match.fid,
            0.0,
            match.point,
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
        self.snap_indicator.setVisible(False)
        self.tangent_rubberband.reset()
        self.preview_rubberband.reset()
        self.current_match = None
        self.preview_geom = None

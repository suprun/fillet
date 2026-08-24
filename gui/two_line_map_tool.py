# -*- coding: utf-8 -*-
"""
Map tool for interactive Two-Line Fillet & Chamfer with feature merging.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

from typing import Optional

from qgis.core import (
    Qgis,
    QgsFeature,
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
from qgis.PyQt.QtCore import QCoreApplication, Qt
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

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(
        self,
        canvas: QgsMapCanvas,
        settings_provider=None,
        widget: Optional[TwoLineCanvasWidget] = None,
        iface=None,
    ):
        super().__init__(canvas)
        self.canvas = canvas
        self.settings_provider = settings_provider
        self.iface = iface
        self.widget = widget or TwoLineCanvasWidget(self.canvas)

        self.first_segment_match: Optional[SegmentMatch] = None
        self.current_segment_match: Optional[SegmentMatch] = None
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

    def activate(self):
        super().activate()
        self._clear_preview()
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

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_preview()
            return

        map_point = event.mapPoint()

        if self.first_segment_match is None:
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
        else:
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

                # Calculate preview
                mode = getattr(self.settings_provider, "mode", "fillet") if self.settings_provider else "fillet"
                radius = getattr(self.settings_provider, "radius", 1.0) if self.settings_provider else 1.0
                dist1 = getattr(self.settings_provider, "distance1", 1.0) if self.settings_provider else 1.0
                dist2 = getattr(self.settings_provider, "distance2", 1.0) if self.settings_provider else 1.0
                segments = getattr(self.settings_provider, "segments_count", 12) if self.settings_provider else 12

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
                    self.preview_rubberband.reset()
                    self.corner_marker.reset()
            else:
                self.edge2_rubberband.reset()
                self.preview_rubberband.reset()
                self.corner_marker.reset()
                self.preview_geom = None

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == _RightButton:
            self._handle_step_back()
            return

        if event.button() != _LeftButton:
            return

        layer = self.current_vector_layer()
        if not layer:
            return

        if self.first_segment_match is None:
            # Step 1: Select first line
            map_point = event.mapPoint()
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
                if self.widget:
                    self.widget.set_step(TwoLineCanvasWidget.STEP_SECOND_LINE)
        else:
            # Step 2: Confirm second line and execute operation
            if self.current_segment_match and self.preview_geom:
                m1 = self.first_segment_match
                m2 = self.current_segment_match
                new_geom = self.preview_geom

                self._apply_two_line_operation(layer, m1.fid, m2.fid, new_geom)

                self._clear_preview()
                if self.widget:
                    self.widget.set_step(TwoLineCanvasWidget.STEP_FIRST_LINE)

    def keyPressEvent(self, event):
        if event.key() == _Key_Escape:
            self._handle_step_back()
            return
        super().keyPressEvent(event)

    def _handle_step_back(self):
        """Reverts Step 2 back to Step 1, or clears Step 1."""
        if self.first_segment_match is not None:
            self.first_segment_match = None
            self.current_segment_match = None
            self.preview_geom = None
            self.edge1_rubberband.reset()
            self.edge2_rubberband.reset()
            self.preview_rubberband.reset()
            self.corner_marker.reset()
            if self.widget:
                self.widget.set_step(TwoLineCanvasWidget.STEP_FIRST_LINE)
        else:
            self._clear_preview()

    def _apply_two_line_operation(
        self,
        layer: QgsVectorLayer,
        fid1: int,
        fid2: int,
        new_geom: QgsGeometry,
    ):
        """Applies the joined geometry to the vector layer with feature merging."""
        if fid1 == fid2:
            # Intra-feature join: update geometry directly
            layer.beginEditCommand(self.tr("Скруглення / фаска лінії"))
            layer.changeGeometry(fid1, new_geom)
            layer.endEditCommand()
            layer.triggerRepaint()
            return

        # Separate features: Check settings
        always_first = QgsSettings().value("plugins/fillet/merge_always_first_feature", False, type=bool)

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
            # When QGIS merges features, it triggers layer changes. We ensure the resulting feature receives new_geom.
            def on_features_merged():
                # Update surviving feature geometry
                selected_ids = layer.selectedFeatureIds()
                target_id = selected_ids[0] if selected_ids else fid1
                if target_id in [f.id() for f in layer.getFeatures([target_id])]:
                    layer.changeGeometry(target_id, new_geom)
                    layer.triggerRepaint()

            # Execute QGIS native dialog
            merge_action.trigger()
            on_features_merged()
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
        self.edge1_rubberband.reset()
        self.edge2_rubberband.reset()
        self.preview_rubberband.reset()
        self.corner_marker.reset()

# -*- coding: utf-8 -*-
"""
Interactive Map Tool for CAD Divide / Measure Line operations.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
from typing import List, Optional

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointLocator,
    QgsPointXY,
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
from qgis.PyQt.QtCore import QCoreApplication, QEvent, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QApplication

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import SnappingHelper
    from .divide_line_canvas_widget import DivideLineCanvasWidget, DivideLineMode
    from .gui_utils import (
        checked_edit_command,
        confirm_features_in_canvas_extent,
        require_edit_success,
    )
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import SnappingHelper
    from gui.divide_line_canvas_widget import DivideLineCanvasWidget, DivideLineMode
    from gui.gui_utils import (
        checked_edit_command,
        confirm_features_in_canvas_extent,
        require_edit_success,
    )

_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_LeftButton = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RightButton = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))


class CADDivideLineMapTool(QgsMapToolEdit):
    """
    Interactive map tool to divide polylines into equal parts or fixed length segments.
    Provides real-time interactive preview, segment division markers, reverse direction,
    extent safety verification, and single-transaction undo/redo.
    """

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas, widget: Optional[DivideLineCanvasWidget] = None, iface=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.widget = widget or DivideLineCanvasWidget(self.canvas)

        self.selected_feature: Optional[QgsFeature] = None
        self.selected_layer: Optional[QgsVectorLayer] = None
        self.hovered_feature: Optional[QgsFeature] = None

        # Visual rubberbands
        # 1. Main line highlight
        self.highlight_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.highlight_rubberband.setColor(QColor(249, 115, 22, 220))  # Orange
        self.highlight_rubberband.setWidth(3)

        # 2. Alternating segment rubberbands for visual distinction
        self.seg1_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.seg1_rubberband.setColor(QColor(37, 99, 235, 240))  # Royal Blue
        self.seg1_rubberband.setWidth(3)

        self.seg2_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.seg2_rubberband.setColor(QColor(5, 150, 105, 240))  # Emerald Green
        self.seg2_rubberband.setWidth(3)

        # 3. Division cut points marker
        self.cut_points_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.cut_points_rubberband.setIcon(QgsRubberBand.IconType.ICON_CIRCLE)
        self.cut_points_rubberband.setIconSize(8)
        self.cut_points_rubberband.setWidth(2)
        self.cut_points_rubberband.setColor(QColor(239, 68, 68, 240))  # Red circle

        # 4. Start point indicator
        self.start_point_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.start_point_rubberband.setIcon(QgsRubberBand.IconType.ICON_BOX)
        self.start_point_rubberband.setIconSize(10)
        self.start_point_rubberband.setWidth(2)
        self.start_point_rubberband.setColor(QColor(234, 88, 12, 255))  # Amber box

        self.snap_indicator = QgsSnapIndicator(self.canvas)

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        # Widget signal connections
        self.widget.commitRequested.connect(self.commit_divide)
        self.widget.resetRequested.connect(self.reset_state)
        self.widget.segmentsCountChanged.connect(self._on_parameters_changed)
        self.widget.segmentLengthChanged.connect(self._on_parameters_changed)
        self.widget.reverseDirectionChanged.connect(self._on_parameters_changed)
        self.widget.modeChanged.connect(self._on_parameters_changed)

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        if not self.canvas:
            return None
        layer = self.canvas.currentLayer()
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isEditable()
            and layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry
        ):
            return layer
        return None

    def activate(self):
        super().activate()
        layer = self.current_vector_layer()
        if layer:
            if hasattr(self.widget, "adapt_to_crs"):
                self.widget.adapt_to_crs(layer.crs())
            if hasattr(self.widget, "update_layer_capabilities"):
                self.widget.update_layer_capabilities(layer)
        self.reset_state()
        if self.widget:
            self.widget.show_on_canvas()

    def deactivate(self):
        self.reset_state()
        if self.widget:
            self.widget.hide()
        super().deactivate()

    def reset_state(self):
        self.selected_feature = None
        self.selected_layer = None
        self.hovered_feature = None
        self._reset_rubberbands()
        if self.widget:
            self.widget.set_step(DivideLineCanvasWidget.STEP_SELECT)

    def _reset_rubberbands(self):
        if self.highlight_rubberband:
            self.highlight_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        if self.seg1_rubberband:
            self.seg1_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        if self.seg2_rubberband:
            self.seg2_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        if self.cut_points_rubberband:
            self.cut_points_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        if self.start_point_rubberband:
            self.start_point_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def _find_line_feature_at(self, map_point: QgsPointXY, layer: QgsVectorLayer) -> Optional[QgsFeature]:
        """Finds nearest line feature to cursor within tolerance radius."""
        if not layer or not self.canvas:
            return None

        match = SnappingHelper.find_segment_at_position(
            layer,
            self.canvas,
            map_point,
        )
        if match is None:
            return None
        feature = layer.getFeature(match.fid)
        return feature if feature.isValid() else None

    def _update_preview(self, feat: QgsFeature):
        """Draws divided segments and cut markers on the canvas."""
        self._reset_rubberbands()
        if not feat or not feat.hasGeometry():
            return

        geom = feat.geometry()
        if geom.isNull() or geom.isEmpty():
            return

        is_rev = self.widget.reverse_direction if self.widget else False
        mode = self.widget.mode if self.widget else DivideLineMode.SegmentsCount
        count = self.widget.segments_count if mode == DivideLineMode.SegmentsCount else None
        length = self.widget.segment_length if mode == DivideLineMode.SegmentLength else None

        sub_geoms = GeometryEngine.divide_line_geometries(
            geom=geom,
            count=count,
            step_length=length,
            reverse_direction=is_rev,
        )

        cut_points = GeometryEngine.get_division_points(
            geom=geom,
            count=count,
            step_length=length,
            reverse_direction=is_rev,
        )

        # Draw alternating colored segments
        for i, sub_g in enumerate(sub_geoms):
            target_rb = self.seg1_rubberband if (i % 2 == 0) else self.seg2_rubberband
            target_rb.addGeometry(sub_g, None)

        # Draw cut points
        for pt in cut_points:
            self.cut_points_rubberband.addPoint(pt)

        # Draw start endpoint
        p_start = None
        if geom.isMultipart():
            multi_pts = geom.asMultiPolyline()
            if multi_pts and multi_pts[0]:
                p_start = multi_pts[-1][-1] if is_rev else multi_pts[0][0]
        else:
            poly_pts = geom.asPolyline()
            if poly_pts:
                p_start = poly_pts[-1] if is_rev else poly_pts[0]

        if p_start is not None:
            self.start_point_rubberband.addPoint(p_start)

    def _on_parameters_changed(self, *args):
        target_feat = self.selected_feature or self.hovered_feature
        if target_feat:
            self._update_preview(target_feat)

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            return

        map_pt = e.mapPoint()

        if self.selected_feature is None:
            # Step 1: Hover mode
            found_feat = self._find_line_feature_at(map_pt, layer)
            if found_feat:
                self.hovered_feature = found_feat
                self._update_preview(found_feat)
            else:
                self.hovered_feature = None
                self._reset_rubberbands()
        else:
            # Step 2: Feature already selected
            pass

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            return

        if e.button() == _LeftButton:
            map_pt = e.mapPoint()
            if self.selected_feature is None:
                feat = self._find_line_feature_at(map_pt, layer)
                if feat:
                    self.selected_feature = feat
                    self.selected_layer = layer
                    self.hovered_feature = None

                    # Check proximity to endpoints to set intuitive initial direction
                    geom = feat.geometry()
                    p_first = None
                    p_last = None
                    if geom.isMultipart():
                        multi_pts = geom.asMultiPolyline()
                        if multi_pts and multi_pts[0] and multi_pts[-1]:
                            p_first = multi_pts[0][0]
                            p_last = multi_pts[-1][-1]
                    else:
                        poly_pts = geom.asPolyline()
                        if poly_pts and len(poly_pts) >= 2:
                            p_first = poly_pts[0]
                            p_last = poly_pts[-1]

                    if p_first and p_last and self.widget:
                        d_first = p_first.sqrDist(map_pt)
                        d_last = p_last.sqrDist(map_pt)
                        if d_last < d_first:
                            self.widget.chk_reverse_direction.setChecked(True)

                    if self.widget:
                        self.widget.set_step(DivideLineCanvasWidget.STEP_DIVIDE)
                        self.widget.focus_count_input()
                    self._update_preview(feat)
            else:
                # Second click confirms division
                self.commit_divide()
        elif e.button() == _RightButton:
            if self.selected_feature is not None:
                self.reset_state()

    def commit_divide(self):
        """Applies line division in a single undoable edit command."""
        layer = self.selected_layer or self.current_vector_layer()
        feat = self.selected_feature

        if not layer or not feat:
            # If nothing selected yet, try dividing selected features in layer
            if layer and layer.selectedFeatureCount() == 1:
                feat = next(layer.getSelectedFeatures())
                self.selected_feature = feat
                self.selected_layer = layer
            else:
                return

        if not layer.isEditable():
            return

        geom = feat.geometry()
        if geom.isNull() or geom.isEmpty():
            return

        # Canvas extent safety check
        if not confirm_features_in_canvas_extent(self.canvas, layer, [feat], self.tr("CAD Divide Line")):
            return

        is_rev = self.widget.reverse_direction if self.widget else False
        mode = self.widget.mode if self.widget else DivideLineMode.SegmentsCount
        count = self.widget.segments_count if mode == DivideLineMode.SegmentsCount else None
        length = self.widget.segment_length if mode == DivideLineMode.SegmentLength else None

        is_multi_layer = QgsWkbTypes.isMultiType(layer.wkbType())
        separate = self.widget.separate_features if (self.widget and is_multi_layer) else True
        if not is_multi_layer:
            separate = True

        sub_geoms = GeometryEngine.divide_line_geometries(
            geom=geom,
            count=count,
            step_length=length,
            reverse_direction=is_rev,
        )

        if not sub_geoms or len(sub_geoms) <= 1:
            if self.iface and hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushWarning(
                    self.tr("CAD Divide Line"),
                    self.tr("Параметри поділу не призвели до створення нових сегментів.")
                )
            return

        try:
            with checked_edit_command(layer, self.tr("CAD Divide Line")):
                if separate:
                    orig_attrs = feat.attributes()
                    new_feats = []
                    for sub_g in sub_geoms:
                        new_f = QgsFeature(layer.fields())
                        new_f.setAttributes(orig_attrs)
                        new_f.setGeometry(sub_g)
                        new_feats.append(new_f)

                    require_edit_success(
                        layer.deleteFeature(feat.id()),
                        "deleteFeature",
                    )
                    require_edit_success(
                        layer.addFeatures(new_feats),
                        "addFeatures",
                    )
                else:
                    multi_geom = QgsGeometry.collectGeometry(sub_geoms)
                    if multi_geom.isNull() or multi_geom.isEmpty():
                        raise RuntimeError("divided geometry is empty")
                    require_edit_success(
                        layer.changeGeometry(feat.id(), multi_geom),
                        "changeGeometry",
                    )
        except (RuntimeError, TypeError) as error:
            if self.iface and hasattr(self.iface, "messageBar"):
                self.iface.messageBar().pushMessage(
                    self.tr("CAD Divide Line"),
                    self.tr("Не вдалося записати зміни: {error}").format(
                        error=error
                    ),
                    level=Qgis.Critical,
                    duration=5,
                )
            return

        self.reset_state()
        if self.canvas:
            self.canvas.refresh()

    def keyPressEvent(self, e):
        key = e.key()
        key_escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
        key_return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
        key_enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))
        key_space = getattr(Qt.Key, "Key_Space", getattr(Qt, "Key_Space", 0x20))

        if key == key_escape:
            self.reset_state()
            e.accept()
            return
        elif key in (key_return, key_enter, key_space):
            if self.selected_feature:
                self.commit_divide()
                e.accept()
                return

        super().keyPressEvent(e)

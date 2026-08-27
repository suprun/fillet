# -*- coding: utf-8 -*-
"""
Map tool for interactive CAD Ortho Angles (orthogonalization of polygon/line vertices relative to a reference base edge).
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
from typing import List, Optional, Tuple

from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointLocator,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import (
    QgisInterface,
    QgsMapCanvas,
    QgsMapMouseEvent,
    QgsMapToolEdit,
    QgsRubberBand,
    QgsSnapIndicator,
)
from qgis.PyQt.QtCore import QCoreApplication, QEvent, Qt
from qgis.PyQt.QtGui import QColor, QCursor

try:
    from ..core.geometry_engine import GeometryEngine
    from .gui_utils import confirm_features_in_canvas_extent
    from .ortho_angles_canvas_widget import OrthoAnglesCanvasWidget
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from gui.gui_utils import confirm_features_in_canvas_extent
    from gui.ortho_angles_canvas_widget import OrthoAnglesCanvasWidget

try:
    _CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
    _DashLine = getattr(Qt.PenStyle, "DashLine", getattr(Qt, "DashLine", None))
    _DotLine = getattr(Qt.PenStyle, "DotLine", getattr(Qt, "DotLine", None))
except Exception:
    _CrossCursor = None
    _DashLine = None
    _DotLine = None


class CADOrthoAnglesMapTool(QgsMapToolEdit):
    """
    Interactive Map Tool to orthogonalize polygon and linestring geometries
    relative to a selected reference base edge (facade/wall).
    """

    STATE_SELECT_FEATURE = 1
    STATE_SET_BASE_EDGE = 2
    STATE_ADJUST = 3

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(
        self,
        canvas: QgsMapCanvas,
        widget: Optional[OrthoAnglesCanvasWidget] = None,
        iface: Optional[QgisInterface] = None,
    ):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.state = self.STATE_SELECT_FEATURE

        if hasattr(self, "setToolName"):
            self.setToolName(self.tr("CAD Ортогоналізація кутів (Ortho Angles)"))
        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        self.widget = widget or OrthoAnglesCanvasWidget(self.canvas)

        self.featureList: List[QgsFeature] = []
        self.featureLayer: Optional[QgsVectorLayer] = None
        self._preselected_features: bool = False

        self.base_segment: Optional[Tuple[QgsPointXY, QgsPointXY]] = None
        self.base_angle_rad: float = 0.0

        # Rubberbands
        self.base_edge_rubberband: Optional[QgsRubberBand] = None
        self.preview_rubberbands: List[QgsRubberBand] = []
        self.modified_nodes_rubberband: Optional[QgsRubberBand] = None
        self.snap_indicator: Optional[QgsSnapIndicator] = None

        self._init_visuals()

        if self.widget is not None:
            self.widget.toleranceChanged.connect(self._on_widget_param_changed)
            self.widget.toleranceLockToggled.connect(self._on_widget_param_changed)
            self.widget.preserveAreaChanged.connect(self._on_widget_param_changed)
            self.widget.createCopyChanged.connect(self._on_widget_param_changed)
            self.widget.commitRequested.connect(self.commit_orthogonalize)
            self.widget.resetRequested.connect(self.step_back)

    def _init_visuals(self) -> None:
        if self.canvas is not None:
            try:
                self.snap_indicator = QgsSnapIndicator(self.canvas)
            except Exception:
                self.snap_indicator = None

            # Base edge rubberband (indigo)
            self.base_edge_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
            self.base_edge_rubberband.setColor(QColor(79, 70, 229, 220))  # Indigo
            self.base_edge_rubberband.setWidth(3)
            if hasattr(self.base_edge_rubberband, "setLineStyle") and _DashLine is not None:
                self.base_edge_rubberband.setLineStyle(_DashLine)

            # Modified nodes indicator (amber cross markers)
            self.modified_nodes_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
            self.modified_nodes_rubberband.setIcon(QgsRubberBand.ICON_CROSS)
            self.modified_nodes_rubberband.setIconSize(10)
            self.modified_nodes_rubberband.setColor(QColor(234, 88, 12, 230))  # Orange/Amber
            self.modified_nodes_rubberband.setWidth(2)

            # Selected feature highlight rubberband (amber/orange outline)
            self.selection_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
            self.selection_rubberband.setColor(QColor(255, 170, 0, 40))
            self.selection_rubberband.setStrokeColor(QColor(255, 140, 0, 220))
            self.selection_rubberband.setWidth(2)

    def _get_preview_rubberband(self, index: int, geom_type: QgsWkbTypes.GeometryType) -> QgsRubberBand:
        while len(self.preview_rubberbands) <= index:
            rb = QgsRubberBand(self.canvas, geom_type)
            rb.setColor(QColor(37, 99, 235, 65))
            rb.setStrokeColor(QColor(29, 78, 216, 220))
            rb.setWidth(2)
            self.preview_rubberbands.append(rb)
        return self.preview_rubberbands[index]

    def _update_selection_highlight(self) -> None:
        if not self.selection_rubberband or not self.canvas:
            return
        if not self.featureList or not self.featureLayer:
            self.selection_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return

        canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
        layer_crs = self.featureLayer.crs()
        needs_transform = canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs
        to_canvas = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance()) if needs_transform else None

        geoms = []
        for feat in self.featureList:
            g = QgsGeometry(feat.geometry())
            if not g.isEmpty() and not g.isNull():
                if to_canvas:
                    try:
                        g.transform(to_canvas)
                    except Exception:
                        pass
                geoms.append(g)

        if geoms:
            geom_type = self.featureLayer.geometryType()
            self.selection_rubberband.reset(geom_type)
            for g in geoms:
                self.selection_rubberband.addGeometry(g, None)
        else:
            self.selection_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def activate(self) -> None:
        super().activate()
        layer = self.currentVectorLayer()
        self._preselected_features = bool(layer and layer.isEditable() and layer.selectedFeatureCount() > 0)
        if self.widget:
            self.widget.show_on_canvas()
        self.reset_state()

    def deactivate(self) -> None:
        self._reset_rubberbands()
        if self.widget:
            self.widget.hide()
        super().deactivate()

    def step_back(self) -> None:
        """Step back in 3-step CAD state machine, or cleanly deactivate tool."""
        if self.state == self.STATE_ADJUST:
            self.state = self.STATE_SET_BASE_EDGE
            self.base_segment = None
            self.base_angle_rad = 0.0
            for rb in self.preview_rubberbands:
                rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            if self.modified_nodes_rubberband:
                self.modified_nodes_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
            if self.base_edge_rubberband and hasattr(self.base_edge_rubberband, "setLineStyle") and _DashLine is not None:
                self.base_edge_rubberband.setLineStyle(_DashLine)
            if self.widget:
                self.widget.set_step(OrthoAnglesCanvasWidget.STEP_BASE_EDGE)
        elif self.state == self.STATE_SET_BASE_EDGE:
            if self._preselected_features:
                self._deactivate_tool()
            else:
                self.state = self.STATE_SELECT_FEATURE
                self.featureList = []
                self.base_segment = None
                self._reset_rubberbands()
                if self.widget:
                    self.widget.set_step(OrthoAnglesCanvasWidget.STEP_SELECT)
        elif self.state == self.STATE_SELECT_FEATURE:
            self._deactivate_tool()

    def _deactivate_tool(self) -> None:
        self._reset_rubberbands()
        if self.widget:
            self.widget.hide()
        if self.canvas:
            self.canvas.unsetMapTool(self)
        if self.iface:
            try:
                pan_action = self.iface.actionPan()
                if pan_action and hasattr(pan_action, "trigger"):
                    pan_action.trigger()
            except Exception:
                pass

    def reset_state(self) -> None:
        layer = self.currentVectorLayer()
        self.base_segment = None
        self.base_angle_rad = 0.0

        if layer and layer.isEditable() and layer.selectedFeatureCount() > 0:
            self.featureLayer = layer
            self.featureList = list(layer.selectedFeatures())
            self.state = self.STATE_SET_BASE_EDGE
            self._update_selection_highlight()
            if self.widget:
                self.widget.set_step(OrthoAnglesCanvasWidget.STEP_BASE_EDGE)
        else:
            self.featureList = []
            self.featureLayer = layer
            self.state = self.STATE_SELECT_FEATURE
            if self.widget:
                self.widget.set_step(OrthoAnglesCanvasWidget.STEP_SELECT)

        self._reset_rubberbands()

    def _reset_rubberbands(self) -> None:
        if self.selection_rubberband and not self.featureList:
            self.selection_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        if self.base_edge_rubberband:
            self.base_edge_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        if self.modified_nodes_rubberband:
            self.modified_nodes_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        for rb in self.preview_rubberbands:
            rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def _snap_point(self, e: QgsMapMouseEvent) -> QgsPointXY:
        point = e.mapPoint()
        if self.canvas is not None:
            snapper = self.canvas.snappingUtils()
            if snapper:
                match = snapper.snapToMap(point)
                if match.isValid():
                    point = match.point()
                    if self.snap_indicator:
                        self.snap_indicator.setMatch(match)
                    return point
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())
        return point

    def _get_target_features(self, layer: QgsVectorLayer, point: QgsPointXY) -> List[QgsFeature]:
        if not layer or not layer.isEditable():
            return []
        if layer.selectedFeatureCount() > 0:
            return list(layer.selectedFeatures())

        # Click tolerance search
        tol = 10.0
        if self.canvas:
            mupp = self.canvas.mapUnitsPerPixel()
            tol = mupp * 12.0
        search_rect = QgsRectangle(point.x() - tol, point.y() - tol, point.x() + tol, point.y() + tol)
        canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
        layer_crs = layer.crs()
        if canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            search_rect = transform.transformBoundingBox(search_rect)

        req = layer.getFeatures(search_rect)
        pt_geom = QgsGeometry.fromPointXY(point)
        found = []
        for feat in req:
            g = feat.geometry()
            if not g.isEmpty():
                found.append(feat)
                break
        return found

    def _find_closest_segment(self, geom: QgsGeometry, map_pt: QgsPointXY) -> Optional[Tuple[QgsPointXY, QgsPointXY, float]]:
        """
        Finds the closest segment on geom to map_pt in canvas coordinates.
        Returns (p1, p2, azimuth_rad).
        """
        if geom.isEmpty() or geom.isNull():
            return None

        # Extract all segments from geometry
        best_seg = None
        min_dist_sq = float("inf")

        pt_x, pt_y = map_pt.x(), map_pt.y()
        rings = []
        geom_type = geom.type()
        if geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if geom.isMultipart():
                for poly in geom.asMultiPolygon():
                    rings.extend(poly)
            else:
                rings.extend(geom.asPolygon())
        elif geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if geom.isMultipart():
                rings.extend(geom.asMultiPolyline())
            else:
                rings.append(geom.asPolyline())

        for ring in rings:
            if len(ring) < 2:
                continue
            for i in range(len(ring) - 1):
                p1 = ring[i]
                p2 = ring[i + 1]
                dx = p2.x() - p1.x()
                dy = p2.y() - p1.y()
                len_sq = dx * dx + dy * dy
                if len_sq < 1e-12:
                    continue

                # Point-to-segment distance squared
                t = max(0.0, min(1.0, ((pt_x - p1.x()) * dx + (pt_y - p1.y()) * dy) / len_sq))
                proj_x = p1.x() + t * dx
                proj_y = p1.y() + t * dy
                dist_sq = (pt_x - proj_x) ** 2 + (pt_y - proj_y) ** 2
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    azimuth = math.atan2(dy, dx)
                    best_seg = (p1, p2, azimuth)

        return best_seg

    def canvasPressEvent(self, e: QgsMapMouseEvent) -> None:
        button = e.button()
        _left_btn = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
        _right_btn = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))

        if button == _right_btn:
            self.step_back()
            return
        if button != _left_btn:
            return

        point = self._snap_point(e)
        layer = self.currentVectorLayer()
        if not layer or not layer.isEditable():
            if self.iface:
                self.iface.messageBar().pushWarning(
                    self.tr("CAD Ортогоналізація кутів"),
                    self.tr("Оберіть шар у режимі редагування.")
                )
            return

        if self.state == self.STATE_SELECT_FEATURE:
            feats = self._get_target_features(layer, point)
            if not feats:
                return
            self.featureLayer = layer
            self.featureList = feats
            self._update_selection_highlight()

            if self.canvas and not confirm_features_in_canvas_extent(
                self.canvas, layer, self.featureList, self.tr("CAD Ортогоналізація кутів")
            ):
                self.reset_state()
                return

            self.state = self.STATE_SET_BASE_EDGE
            if self.widget:
                self.widget.set_step(OrthoAnglesCanvasWidget.STEP_BASE_EDGE)

        elif self.state == self.STATE_SET_BASE_EDGE:
            if not self.featureList:
                feats = self._get_target_features(layer, point)
                if not feats:
                    return
                self.featureLayer = layer
                self.featureList = feats
                self._update_selection_highlight()

            # Transform feature geometry to canvas to find base segment
            canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
            layer_crs = layer.crs()
            to_canvas = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance()) if (canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs) else None

            feat_geom = QgsGeometry(self.featureList[0].geometry())
            if to_canvas:
                try:
                    feat_geom.transform(to_canvas)
                except Exception:
                    pass

            seg_info = self._find_closest_segment(feat_geom, point)
            if not seg_info:
                return

            p1, p2, azimuth = seg_info
            self.base_segment = (p1, p2)
            self.base_angle_rad = azimuth

            self.state = self.STATE_ADJUST
            if self.widget:
                self.widget.set_step(OrthoAnglesCanvasWidget.STEP_ADJUST)

            # Solid style for locked base edge
            if self.base_edge_rubberband:
                from qgis.PyQt.QtCore import Qt as _Qt
                solid_style = getattr(_Qt.PenStyle, "SolidLine", getattr(_Qt, "SolidLine", 1))
                if hasattr(self.base_edge_rubberband, "setLineStyle") and solid_style is not None:
                    self.base_edge_rubberband.setLineStyle(solid_style)
                self.base_edge_rubberband.setToGeometry(QgsGeometry.fromPolylineXY([p1, p2]), None)

            self._update_preview()

        elif self.state == self.STATE_ADJUST:
            self.commit_orthogonalize()

    def canvasMoveEvent(self, e: QgsMapMouseEvent) -> None:
        point = self._snap_point(e)
        layer = self.featureLayer or self.currentVectorLayer()

        if self.state == self.STATE_SET_BASE_EDGE and self.featureList and layer:
            canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
            layer_crs = layer.crs()
            to_canvas = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance()) if (canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs) else None

            feat_geom = QgsGeometry(self.featureList[0].geometry())
            if to_canvas:
                try:
                    feat_geom.transform(to_canvas)
                except Exception:
                    pass

            seg_info = self._find_closest_segment(feat_geom, point)
            if seg_info and self.base_edge_rubberband:
                p1, p2, _ = seg_info
                self.base_edge_rubberband.setToGeometry(QgsGeometry.fromPolylineXY([p1, p2]), None)

        elif self.state == self.STATE_ADJUST:
            pass

    def _on_widget_param_changed(self, *args) -> None:
        if self.state == self.STATE_ADJUST:
            self._update_preview()

    def _update_preview(self) -> None:
        if not self.featureList or not self.featureLayer or self.base_segment is None:
            return

        layer = self.featureLayer
        canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
        layer_crs = layer.crs()
        needs_transform = canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs

        to_layer = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance()) if needs_transform else None
        to_canvas = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance()) if needs_transform else None

        # Base azimuth in layer CRS
        p1, p2 = self.base_segment
        if to_layer:
            p1_l = to_layer.transform(p1)
            p2_l = to_layer.transform(p2)
            base_angle_in_layer = math.atan2(p2_l.y() - p1_l.y(), p2_l.x() - p1_l.x())
        else:
            base_angle_in_layer = self.base_angle_rad

        tolerance = self.widget.tolerance if self.widget else 15.0
        preserve_area = self.widget.preserve_area if self.widget else True

        all_previews: List[QgsGeometry] = []
        all_modified_points: List[QgsPointXY] = []

        for feat in self.featureList:
            orig_geom = feat.geometry()
            if orig_geom.isEmpty() or orig_geom.isNull():
                continue

            ortho_geom = GeometryEngine.orthogonalize_geometry(
                geom=orig_geom,
                base_angle_rad=base_angle_in_layer,
                tolerance_deg=tolerance,
                preserve_area=preserve_area,
            )

            # Transform to canvas for display
            ortho_disp = QgsGeometry(ortho_geom)
            if to_canvas:
                try:
                    ortho_disp.transform(to_canvas)
                except Exception:
                    pass
            all_previews.append(ortho_disp)

            # Find modified vertices for markers
            orig_disp = QgsGeometry(orig_geom)
            if to_canvas:
                try:
                    orig_disp.transform(to_canvas)
                except Exception:
                    pass
            v_orig = [QgsPointXY(p.x(), p.y()) for p in orig_disp.vertices()]
            v_ortho = [QgsPointXY(p.x(), p.y()) for p in ortho_disp.vertices()]
            for vo, vn in zip(v_orig, v_ortho):
                if math.hypot(vo.x() - vn.x(), vo.y() - vn.y()) > 1e-4:
                    all_modified_points.append(vn)

        geom_type = layer.geometryType()
        for i, g in enumerate(all_previews):
            rb = self._get_preview_rubberband(i, geom_type)
            rb.setToGeometry(g, None)

        for j in range(len(all_previews), len(self.preview_rubberbands)):
            self.preview_rubberbands[j].reset(geom_type)

        # Modified vertices markers
        if self.modified_nodes_rubberband:
            if all_modified_points:
                mp_geom = QgsGeometry.fromMultiPointXY(all_modified_points)
                self.modified_nodes_rubberband.setToGeometry(mp_geom, None)
            else:
                self.modified_nodes_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)

    def commit_orthogonalize(self) -> None:
        if not self.featureList or not self.featureLayer or self.base_segment is None:
            return

        layer = self.featureLayer
        if not layer.isEditable():
            return

        canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
        layer_crs = layer.crs()
        needs_transform = canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs
        to_layer = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance()) if needs_transform else None

        p1, p2 = self.base_segment
        if to_layer:
            p1_l = to_layer.transform(p1)
            p2_l = to_layer.transform(p2)
            base_angle_in_layer = math.atan2(p2_l.y() - p1_l.y(), p2_l.x() - p1_l.x())
        else:
            base_angle_in_layer = self.base_angle_rad

        tolerance = self.widget.tolerance if self.widget else 15.0
        preserve_area = self.widget.preserve_area if self.widget else True
        create_copy = self.widget.create_copy if self.widget else False

        layer.beginEditCommand(self.tr("CAD Ортогоналізація кутів"))

        new_features: List[QgsFeature] = []
        for feat in self.featureList:
            orig_geom = feat.geometry()
            if orig_geom.isEmpty() or orig_geom.isNull():
                continue

            ortho_geom = GeometryEngine.orthogonalize_geometry(
                geom=orig_geom,
                base_angle_rad=base_angle_in_layer,
                tolerance_deg=tolerance,
                preserve_area=preserve_area,
            )

            if create_copy:
                new_f = QgsFeature(layer.fields())
                new_f.setAttributes(feat.attributes())
                new_f.setGeometry(ortho_geom)
                new_features.append(new_f)
            else:
                layer.changeGeometry(feat.id(), ortho_geom)

        if new_features:
            layer.addFeatures(new_features)

        layer.endEditCommand()

        self.reset_state()
        if self.canvas:
            self.canvas.refresh()

    def keyPressEvent(self, e) -> None:
        key = e.key()
        key_int = int(key)
        key_escape = int(getattr(Qt.Key, "Key_Escape", 0x01000000))
        key_return = int(getattr(Qt.Key, "Key_Return", 0x01000004))
        key_enter = int(getattr(Qt.Key, "Key_Enter", 0x01000005))

        # If user types digits or math symbols, redirect focus to HUD spinbox
        if e.text() and (e.text().isdigit() or e.text() in ".-+," or key_int == 0x01000003):
            if self.widget:
                from qgis.PyQt.QtWidgets import QApplication
                focused = QApplication.focusWidget()
                is_on_panel = False
                if focused:
                    w = focused
                    while w is not None:
                        if w == self.widget:
                            is_on_panel = True
                            break
                        w = w.parent()
                if not is_on_panel:
                    self.widget.focus_primary_input()
                    focused = QApplication.focusWidget()
                    if focused:
                        QApplication.sendEvent(focused, e)
                    e.accept()
                    return

        if key_int in (0x01000000, key_escape):
            self.step_back()
            e.accept()
            return
        elif key_int in (0x01000004, 0x01000005, key_return, key_enter):
            if self.state == self.STATE_ADJUST:
                self.commit_orthogonalize()
                e.accept()
                return

        super().keyPressEvent(e)

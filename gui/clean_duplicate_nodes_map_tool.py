# -*- coding: utf-8 -*-
"""
Map tool for interactive Quick Cleaning of Duplicate Nodes and Topology Self-Intersections in QGIS.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).

Interaction Model:
1. Hovering over a feature highlights its geometry, marking duplicate nodes (red) and self-intersections (amber).
   Cursor remains constant crosshair (no pointer hand on hover).
2. Left-click on a specific duplicate node or intersection point -> Native Context Menu with Live Preview on hover,
   including SinglePart vs MultiPart layer protection.
3. Left-click on feature body -> Fast one-click clean; if a SinglePart layer polygon splits into multiple parts,
   displays an instant 2-choice micro-menu at cursor (Keep Largest vs Split into separate features).
"""

import math
from typing import Dict, List, Optional, Tuple

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
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
from qgis.PyQt.QtCore import QCoreApplication, QPoint, Qt
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QAction, QApplication, QMenu, QMessageBox

# Safe cross-version Qt constants
_LeftButton = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RightButton = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_Key_Escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))

try:
    from ..core.geometry_engine import GeometryEngine
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine


class CleanDuplicateNodesMapTool(QgsMapToolEdit):
    """
    Interactive map tool for detecting, previewing, and cleaning duplicate nodes
    and self-intersections in vector geometries with SinglePart/MultiPart safety.
    """

    SNAP_PIXELS = 10.0
    GEOM_TOLERANCE = 1e-5

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas

        # State & cached data
        self.hovered_feature: Optional[QgsFeature] = None
        self.hovered_layer: Optional[QgsVectorLayer] = None
        self.duplicate_nodes: List[Dict] = []
        self.self_intersections: List[Dict] = []
        self.active_item: Optional[Tuple[str, Dict]] = None  # ("duplicate" | "intersection", data_dict)

        # RubberBands
        self.hover_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.hover_rubberband.setColor(QColor(37, 99, 235, 60))
        self.hover_rubberband.setStrokeColor(QColor(37, 99, 235, 200))
        self.hover_rubberband.setWidth(2)

        # Duplicate node markers (Red)
        self.dup_markers_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.dup_markers_rubberband.setColor(QColor(239, 68, 68, 240))
        self.dup_markers_rubberband.setWidth(8)
        self.dup_markers_rubberband.setIcon(getattr(QgsRubberBand, "ICON_X", 1))

        # Self-intersection markers (Amber / Orange)
        self.inter_markers_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.inter_markers_rubberband.setColor(QColor(245, 158, 11, 240))
        self.inter_markers_rubberband.setWidth(10)
        self.inter_markers_rubberband.setIcon(getattr(QgsRubberBand, "ICON_BOX", 2))

        # Active highlighted error under cursor (Cyan highlight)
        self.active_node_marker = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.active_node_marker.setColor(QColor(6, 182, 212, 255))
        self.active_node_marker.setWidth(14)
        self.active_node_marker.setIcon(getattr(QgsRubberBand, "ICON_CIRCLE", 3))

        # Preview rubberband for live preview (Green dashed)
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_rubberband.setColor(QColor(16, 185, 129, 70))
        self.preview_rubberband.setStrokeColor(QColor(16, 185, 129, 230))
        self.preview_rubberband.setWidth(2)
        dash_style = getattr(Qt.PenStyle, "DashLine", getattr(Qt, "DashLine", 2))
        self.preview_rubberband.setLineStyle(dash_style)

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

    def activate(self):
        super().activate()
        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

    def deactivate(self):
        self._clear_visuals()
        self.hovered_feature = None
        self.hovered_layer = None
        self.duplicate_nodes = []
        self.self_intersections = []
        self.active_item = None
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        for rb in (
            self.hover_rubberband,
            self.dup_markers_rubberband,
            self.inter_markers_rubberband,
            self.active_node_marker,
            self.preview_rubberband,
        ):
            if rb:
                rb.reset()

    def _clear_visuals(self):
        self.hover_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.dup_markers_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.inter_markers_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.active_node_marker.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable():
            return layer
        return None

    def _identify_feature_at(self, map_pt: QgsPointXY, layer: QgsVectorLayer) -> Optional[QgsFeature]:
        """Identifies a feature under the given point in layer coordinates."""
        if not layer or not layer.isEditable():
            return None

        tol_px = QgsSettings().value("qgis/digitizing/snap_tolerance", self.SNAP_PIXELS, type=float)
        map_tol = self.canvas.mapUnitsPerPixel() * tol_px

        layer_pt = self.toLayerCoordinates(layer, map_pt)
        search_rect = QgsRectangle(
            layer_pt.x() - map_tol,
            layer_pt.y() - map_tol,
            layer_pt.x() + map_tol,
            layer_pt.y() + map_tol,
        )

        req = layer.getFeatures(search_rect)
        for feat in req:
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            if geom.type() == QgsWkbTypes.GeometryType.PolygonGeometry:
                if geom.contains(layer_pt) or geom.distance(QgsGeometry.fromPointXY(layer_pt)) <= map_tol:
                    return feat
            elif geom.type() == QgsWkbTypes.GeometryType.LineGeometry:
                if geom.distance(QgsGeometry.fromPointXY(layer_pt)) <= map_tol:
                    return feat
        return None

    def _update_errors_for_feature(self, feat: QgsFeature, layer: QgsVectorLayer):
        geom = feat.geometry()
        self.duplicate_nodes = GeometryEngine.find_duplicate_nodes(geom, tolerance=self.GEOM_TOLERANCE)
        self.self_intersections = GeometryEngine.find_self_intersections(geom)

        # Update duplicate markers (Red)
        self.dup_markers_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        for dup in self.duplicate_nodes:
            pt = dup["point"]
            map_pt = self.toMapCoordinates(layer, QgsPointXY(pt.x(), pt.y()))
            self.dup_markers_rubberband.addPoint(map_pt, True)
        self.dup_markers_rubberband.show()

        # Update self-intersection markers (Amber)
        self.inter_markers_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        for inter in self.self_intersections:
            pt = inter["point"]
            map_pt = self.toMapCoordinates(layer, QgsPointXY(pt.x(), pt.y()))
            self.inter_markers_rubberband.addPoint(map_pt, True)
        self.inter_markers_rubberband.show()

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_visuals()
            return

        map_pt = self.toMapCoordinates(event.pos())
        feat = self._identify_feature_at(map_pt, layer)

        if not feat:
            self._clear_visuals()
            self.hovered_feature = None
            self.hovered_layer = None
            self.duplicate_nodes = []
            self.self_intersections = []
            self.active_item = None
            return

        # Check if hovered feature changed
        if not self.hovered_feature or self.hovered_feature.id() != feat.id():
            self.hovered_feature = feat
            self.hovered_layer = layer
            self.hover_rubberband.setToGeometry(feat.geometry(), layer)
            self.hover_rubberband.show()
            self._update_errors_for_feature(feat, layer)

        # Hit test for duplicate nodes or self-intersections (within SNAP_PIXELS)
        self.active_item = None
        self.active_node_marker.reset(QgsWkbTypes.GeometryType.PointGeometry)

        # Check duplicate nodes first
        for dup in self.duplicate_nodes:
            pt = dup["point"]
            map_pt_dup = self.toMapCoordinates(layer, QgsPointXY(pt.x(), pt.y()))
            screen_pt = self.toCanvasCoordinates(map_pt_dup)
            dx = screen_pt.x() - event.pos().x()
            dy = screen_pt.y() - event.pos().y()
            if math.hypot(dx, dy) <= self.SNAP_PIXELS:
                self.active_item = ("duplicate", dup)
                self.active_node_marker.addPoint(map_pt_dup, True)
                self.active_node_marker.show()
                break

        # Check self-intersections if no duplicate node matched
        if not self.active_item:
            for inter in self.self_intersections:
                pt = inter["point"]
                map_pt_inter = self.toMapCoordinates(layer, QgsPointXY(pt.x(), pt.y()))
                screen_pt = self.toCanvasCoordinates(map_pt_inter)
                dx = screen_pt.x() - event.pos().x()
                dy = screen_pt.y() - event.pos().y()
                if math.hypot(dx, dy) <= self.SNAP_PIXELS:
                    self.active_item = ("intersection", inter)
                    self.active_node_marker.addPoint(map_pt_inter, True)
                    self.active_node_marker.show()
                    break

    def _apply_split_features(
        self,
        layer: QgsVectorLayer,
        orig_feat: QgsFeature,
        parts: List[QgsGeometry],
        command_name: str,
    ):
        """Replaces orig_feat geometry with first part, and adds remaining parts as new features."""
        if not parts:
            return
        layer.beginEditCommand(command_name)
        layer.changeGeometry(orig_feat.id(), parts[0])
        new_features = []
        for p in parts[1:]:
            new_f = QgsFeature(layer.fields())
            new_f.setAttributes(orig_feat.attributes())
            new_f.setGeometry(p)
            new_features.append(new_f)
        if new_features:
            layer.addFeatures(new_features)
        layer.endEditCommand()
        layer.triggerRepaint()
        self.canvas.refresh()

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        if event.button() == _RightButton:
            self._clear_visuals()
            self.hovered_feature = None
            self.hovered_layer = None
            self.duplicate_nodes = []
            self.self_intersections = []
            self.active_item = None
            return

        if event.button() != _LeftButton:
            return

        layer = self.current_vector_layer()
        if not layer or not self.hovered_feature:
            return

        feat = self.hovered_feature
        is_multi_layer = QgsWkbTypes.isMultiType(layer.wkbType())
        total_errors = len(self.duplicate_nodes) + len(self.self_intersections)

        # CASE 1: Clicked on a specific error -> Native System Context Menu with Live Preview
        if self.active_item:
            item_type, item_data = self.active_item
            menu = QMenu(self.canvas)

            if item_type == "duplicate":
                part_idx = item_data["part_idx"]
                ring_idx = item_data["ring_idx"]
                v1_idx = item_data["v1_idx"]
                v2_idx = item_data["v2_idx"]

                act_merge = QAction(self.tr("Злити дублі у вершині (залишити 1 вузол)"), menu)
                act_merge.setData({"type": "merge_point", "point": item_data["point"]})

                act_keep_v1 = QAction(self.tr("Залишити вузол #{0} (видалити #{1})").format(v1_idx + 1, v2_idx + 1), menu)
                act_keep_v1.setData({"type": "remove_idx", "idx": v2_idx})

                act_keep_v2 = QAction(self.tr("Залишити вузол #{0} (видалити #{1})").format(v2_idx + 1, v1_idx + 1), menu)
                act_keep_v2.setData({"type": "remove_idx", "idx": v1_idx})

                act_clean_all = QAction(self.tr("Очистити всі дублі та помилки в об'єкті ({0})").format(total_errors), menu)
                act_clean_all.setData({"type": "clean_all"})

                menu.addAction(act_merge)
                menu.addAction(act_keep_v1)
                menu.addAction(act_keep_v2)
                menu.addSeparator()
                menu.addAction(act_clean_all)

                def _on_hover_dup(action: QAction):
                    if not action:
                        self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
                        return
                    data = action.data()
                    if not data:
                        return
                    action_type = data.get("type")
                    if action_type == "merge_point":
                        pt = data.get("point")
                        cand_geom = GeometryEngine.merge_duplicate_nodes_at_point(
                            feat.geometry(), pt, tolerance=self.GEOM_TOLERANCE
                        )
                        cand_geom = GeometryEngine.coerce_geometry_to_layer(cand_geom, layer)
                        self.preview_rubberband.setToGeometry(cand_geom, layer)
                        self.preview_rubberband.show()
                    elif action_type == "remove_idx":
                        idx_to_remove = data.get("idx")
                        cand_geom = GeometryEngine.remove_duplicate_node_at_index(
                            feat.geometry(), part_idx, ring_idx, idx_to_remove
                        )
                        cand_geom = GeometryEngine.coerce_geometry_to_layer(cand_geom, layer)
                        self.preview_rubberband.setToGeometry(cand_geom, layer)
                        self.preview_rubberband.show()
                    elif action_type == "clean_all":
                        cand_geom, _ = GeometryEngine.clean_all_topology_errors(feat.geometry(), tolerance=self.GEOM_TOLERANCE)
                        cand_geom = GeometryEngine.coerce_geometry_to_layer(cand_geom, layer)
                        self.preview_rubberband.setToGeometry(cand_geom, layer)
                        self.preview_rubberband.show()

                menu.hovered.connect(_on_hover_dup)

            elif item_type == "intersection":
                part_idx = item_data["part_idx"]
                ring_idx = item_data["ring_idx"]
                seg1_idx = item_data["seg1_idx"]
                seg2_idx = item_data["seg2_idx"]
                inter_pt = item_data["point"]

                # Check if makeValid yields multiple parts
                valid_geom = feat.geometry().makeValid()
                parts = GeometryEngine.extract_singlepart_geometries(valid_geom, layer.geometryType())

                if is_multi_layer:
                    act_untangle = QAction(self.tr("Розплутати петлю самоперетину"), menu)
                    act_untangle.setData({"type": "untangle"})

                    act_make_valid = QAction(self.tr("Розбити на мультиполігон (MultiPart)"), menu)
                    act_make_valid.setData({"type": "make_valid_multi"})

                    act_clean_all = QAction(self.tr("Очистити всі дублі та помилки в об'єкті ({0})").format(total_errors), menu)
                    act_clean_all.setData({"type": "clean_all"})

                    menu.addAction(act_untangle)
                    menu.addAction(act_make_valid)
                    menu.addSeparator()
                    menu.addAction(act_clean_all)
                else:
                    if len(parts) > 1:
                        act_untangle = QAction(self.tr("Розплутати / залишити основне тіло"), menu)
                        act_untangle.setData({"type": "untangle"})

                        act_split = QAction(self.tr("Розділити на {0} окремих об'єктів").format(len(parts)), menu)
                        act_split.setData({"type": "split_features", "parts": parts})

                        act_clean_all = QAction(self.tr("Очистити всі дублі та помилки в об'єкті ({0})").format(total_errors), menu)
                        act_clean_all.setData({"type": "clean_all"})

                        menu.addAction(act_untangle)
                        menu.addAction(act_split)
                        menu.addSeparator()
                        menu.addAction(act_clean_all)
                    else:
                        act_untangle = QAction(self.tr("Розплутати петлю самоперетину"), menu)
                        act_untangle.setData({"type": "untangle"})

                        act_make_valid = QAction(self.tr("Автоматично виправити геометрію (Make Valid)"), menu)
                        act_make_valid.setData({"type": "make_valid_single"})

                        act_clean_all = QAction(self.tr("Очистити всі дублі та помилки в об'єкті ({0})").format(total_errors), menu)
                        act_clean_all.setData({"type": "clean_all"})

                        menu.addAction(act_untangle)
                        menu.addAction(act_make_valid)
                        menu.addSeparator()
                        menu.addAction(act_clean_all)

                def _on_hover_inter(action: QAction):
                    if not action:
                        self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
                        return
                    data = action.data()
                    if not data:
                        return
                    action_type = data.get("type")
                    if action_type == "untangle":
                        cand_geom = GeometryEngine.untangle_self_intersection(
                            feat.geometry(), part_idx, ring_idx, seg1_idx, seg2_idx, inter_pt, keep_loop=0
                        )
                        cand_geom = GeometryEngine.coerce_geometry_to_layer(cand_geom, layer)
                        self.preview_rubberband.setToGeometry(cand_geom, layer)
                        self.preview_rubberband.show()
                    elif action_type in ("make_valid_multi", "make_valid_single"):
                        cand_geom = GeometryEngine.coerce_geometry_to_layer(valid_geom, layer)
                        self.preview_rubberband.setToGeometry(cand_geom, layer)
                        self.preview_rubberband.show()
                    elif action_type == "split_features":
                        self.preview_rubberband.setToGeometry(valid_geom, layer)
                        self.preview_rubberband.show()
                    elif action_type == "clean_all":
                        cand_geom, _ = GeometryEngine.clean_all_topology_errors(feat.geometry(), tolerance=self.GEOM_TOLERANCE)
                        cand_geom = GeometryEngine.coerce_geometry_to_layer(cand_geom, layer)
                        self.preview_rubberband.setToGeometry(cand_geom, layer)
                        self.preview_rubberband.show()

                menu.hovered.connect(_on_hover_inter)

            def _on_hide():
                self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

            menu.aboutToHide.connect(_on_hide)

            chosen_action = menu.exec_(self.canvas.mapToGlobal(event.pos()))

            if chosen_action:
                data = chosen_action.data()
                if data:
                    action_type = data.get("type")
                    if action_type == "merge_point":
                        pt = data.get("point")
                        new_geom = GeometryEngine.merge_duplicate_nodes_at_point(
                            feat.geometry(), pt, tolerance=self.GEOM_TOLERANCE
                        )
                        new_geom = GeometryEngine.coerce_geometry_to_layer(new_geom, layer)
                        layer.beginEditCommand(self.tr("Очищення дубльованих вузлів"))
                        layer.changeGeometry(feat.id(), new_geom)
                        layer.endEditCommand()
                        layer.triggerRepaint()
                        self.canvas.refresh()
                    elif action_type == "remove_idx":
                        idx_to_remove = data.get("idx")
                        new_geom = GeometryEngine.remove_duplicate_node_at_index(
                            feat.geometry(), part_idx, ring_idx, idx_to_remove
                        )
                        new_geom = GeometryEngine.coerce_geometry_to_layer(new_geom, layer)
                        layer.beginEditCommand(self.tr("Очищення дубльованих вузлів"))
                        layer.changeGeometry(feat.id(), new_geom)
                        layer.endEditCommand()
                        layer.triggerRepaint()
                        self.canvas.refresh()
                    elif action_type == "untangle":
                        new_geom = GeometryEngine.untangle_self_intersection(
                            feat.geometry(), part_idx, ring_idx, seg1_idx, seg2_idx, inter_pt, keep_loop=0
                        )
                        new_geom = GeometryEngine.coerce_geometry_to_layer(new_geom, layer)
                        layer.beginEditCommand(self.tr("Розплутування самоперетину"))
                        layer.changeGeometry(feat.id(), new_geom)
                        layer.endEditCommand()
                        layer.triggerRepaint()
                        self.canvas.refresh()
                    elif action_type in ("make_valid_multi", "make_valid_single"):
                        new_geom = GeometryEngine.coerce_geometry_to_layer(feat.geometry().makeValid(), layer)
                        layer.beginEditCommand(self.tr("Виправлення геометрії"))
                        layer.changeGeometry(feat.id(), new_geom)
                        layer.endEditCommand()
                        layer.triggerRepaint()
                        self.canvas.refresh()
                    elif action_type == "split_features":
                        parts = data.get("parts", [])
                        self._apply_split_features(layer, feat, parts, self.tr("Розділення на окремі об'єкти"))
                    elif action_type == "clean_all":
                        new_geom, _ = GeometryEngine.clean_all_topology_errors(feat.geometry(), tolerance=self.GEOM_TOLERANCE)
                        new_geom = GeometryEngine.coerce_geometry_to_layer(new_geom, layer)
                        layer.beginEditCommand(self.tr("Очищення топологічних помилок"))
                        layer.changeGeometry(feat.id(), new_geom)
                        layer.endEditCommand()
                        layer.triggerRepaint()
                        self.canvas.refresh()

                    # Re-scan errors
                    fresh_feat = layer.getFeature(feat.id())
                    if fresh_feat and fresh_feat.isValid():
                        self.hovered_feature = fresh_feat
                        self.hover_rubberband.setToGeometry(fresh_feat.geometry(), layer)
                        self._update_errors_for_feature(fresh_feat, layer)
                    else:
                        self._clear_visuals()

        # CASE 2: Clicked on feature body -> Fast One-Click Clean with SinglePart split safety (Variant A)
        else:
            if total_errors == 0:
                return

            cleaned_geom, count = GeometryEngine.clean_all_topology_errors(feat.geometry(), tolerance=self.GEOM_TOLERANCE)
            if count == 0:
                return

            parts = GeometryEngine.extract_singlepart_geometries(cleaned_geom, layer.geometryType())

            # If layer is SinglePart and geometry split into multiple parts -> show system prompt
            if not is_multi_layer and len(parts) > 1:
                _AcceptRole = getattr(QMessageBox.ButtonRole, "AcceptRole", getattr(QMessageBox, "AcceptRole", 0))
                _ActionRole = getattr(QMessageBox.ButtonRole, "ActionRole", getattr(QMessageBox, "ActionRole", 3))

                msg = QMessageBox(self.canvas.window() if self.canvas else None)
                msg.setIcon(getattr(QMessageBox.Icon, "Question", getattr(QMessageBox, "Question", 4)))
                msg.setWindowTitle(self.tr("Тип геометрії шару"))
                msg.setText(
                    self.tr(
                        "Поточний шар не підтримує багаточастинні геометрії (MultiPart).\n\n"
                        "Результат виправлення містить декілька частин ({0}). Оберіть варіант збереження:"
                    ).format(len(parts))
                )

                btn_split = msg.addButton(
                    self.tr("Розбити на окремі SinglePart об'єкти"),
                    _AcceptRole,
                )
                btn_keep_multi = msg.addButton(
                    self.tr("Залишити як MultiPart"),
                    _ActionRole,
                )
                btn_cancel = msg.addButton(
                    getattr(QMessageBox.StandardButton, "Cancel", getattr(QMessageBox, "Cancel", 0x00400000))
                )
                msg.setDefaultButton(btn_split)

                msg.exec_()
                clicked_button = msg.clickedButton()

                if clicked_button == btn_split:
                    self._apply_split_features(
                        layer, feat, parts, self.tr("Очищення та розбиття на окремі об'єкти")
                    )
                elif clicked_button == btn_keep_multi:
                    layer.beginEditCommand(self.tr("Очищення геометрії (MultiPart)"))
                    layer.changeGeometry(feat.id(), cleaned_geom)
                    layer.endEditCommand()
                    layer.triggerRepaint()
                    self.canvas.refresh()
                else:
                    # Cancelled
                    return

                fresh_feat = layer.getFeature(feat.id())
                if fresh_feat and fresh_feat.isValid():
                    self.hovered_feature = fresh_feat
                    self.hover_rubberband.setToGeometry(fresh_feat.geometry(), layer)
                    self._update_errors_for_feature(fresh_feat, layer)
                else:
                    self._clear_visuals()
            else:
                # Direct 1-click execution (Single geometry or MultiPart layer)
                coerced_geom = GeometryEngine.coerce_geometry_to_layer(cleaned_geom, layer)
                layer.beginEditCommand(self.tr("Швидке очищення дубльованих вузлів та помилок"))
                layer.changeGeometry(feat.id(), coerced_geom)
                layer.endEditCommand()
                layer.triggerRepaint()
                self.canvas.refresh()

                fresh_feat = layer.getFeature(feat.id())
                if fresh_feat and fresh_feat.isValid():
                    self.hovered_feature = fresh_feat
                    self.hover_rubberband.setToGeometry(fresh_feat.geometry(), layer)
                    self._update_errors_for_feature(fresh_feat, layer)
                else:
                    self._clear_visuals()

    def keyPressEvent(self, event):
        if event.key() == _Key_Escape:
            self._clear_visuals()
            self.hovered_feature = None
            self.hovered_layer = None
            self.duplicate_nodes = []
            self.self_intersections = []
            self.active_item = None
            return
        super().keyPressEvent(event)

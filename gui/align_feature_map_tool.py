# -*- coding: utf-8 -*-
"""Interactive point/edge Align Feature map tool."""

import math
from typing import List, Optional, Set, Tuple

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointLocator,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapMouseEvent, QgsMapToolEdit, QgsRubberBand, QgsSnapIndicator
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor, QCursor

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import LayerSegmentMatch, SnappingHelper
    from .align_feature_canvas_widget import AlignFeatureCanvasWidget, AlignReferenceMode
    from .gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import LayerSegmentMatch, SnappingHelper
    from gui.align_feature_canvas_widget import AlignFeatureCanvasWidget, AlignReferenceMode
    from gui.gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy


_LEFT_BUTTON = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RIGHT_BUTTON = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_SHIFT_MODIFIER = getattr(Qt.KeyboardModifier, "ShiftModifier", getattr(Qt, "ShiftModifier", 0x02000000))
_CTRL_MODIFIER = getattr(Qt.KeyboardModifier, "ControlModifier", getattr(Qt, "ControlModifier", 0x04000000))
_KEY_ESCAPE = int(getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000)))
_KEY_BACKSPACE = int(getattr(Qt.Key, "Key_Backspace", getattr(Qt, "Key_Backspace", 0x01000003)))
_KEY_RETURN = int(getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004)))
_KEY_ENTER = int(getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005)))
_KEY_F = int(getattr(Qt.Key, "Key_F", getattr(Qt, "Key_F", 0x46)))
_CROSS_CURSOR = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))


class AlignFeatureMapTool(QgsMapToolEdit):
    """Align selected features using two points or two edges."""

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas, widget: AlignFeatureCanvasWidget, iface=None) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.iface = iface
        self.source_layer: Optional[QgsVectorLayer] = None
        self.source_features: List[QgsFeature] = []
        self.stage = 0
        self.source_start: Optional[QgsPointXY] = None
        self.source_end: Optional[QgsPointXY] = None
        self.target_start: Optional[QgsPointXY] = None
        self.target_end: Optional[QgsPointXY] = None
        self.source_edge: Optional[LayerSegmentMatch] = None
        self.target_edge: Optional[LayerSegmentMatch] = None
        self.hover_target_end: Optional[QgsPointXY] = None
        self.hover_target_edge: Optional[LayerSegmentMatch] = None
        self.shift_pressed = False
        self.ctrl_pressed = False
        self.flip = False
        self.snap_indicator = QgsSnapIndicator(canvas)
        self.source_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.source_band.setColor(QColor(234, 88, 12, 220))
        self.source_band.setWidth(3)
        self.target_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.target_band.setColor(QColor(79, 70, 229, 220))
        self.target_band.setWidth(3)
        self.preview_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_band.setColor(QColor(37, 99, 235, 60))
        self.preview_band.setStrokeColor(QColor(29, 78, 216, 220))
        self.preview_band.setWidth(2)
        if _CROSS_CURSOR is not None:
            self.setCursor(QCursor(_CROSS_CURSOR))
        if hasattr(self, "setToolName"):
            self.setToolName(self.tr("CAD Вирівнювання (Align Feature)"))

        self.widget.modeChanged.connect(self._on_mode_changed)
        self.widget.stepBackRequested.connect(self.step_back)
        self.widget.resetRequested.connect(self._escape)
        self.widget.commitRequested.connect(self.commit_alignment)
        self.widget.shortcutRequested.connect(self._on_shortcut)
        self.widget.modifierChanged.connect(self._on_modifier_changed)

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable():
            return layer
        return None

    def activate(self) -> None:
        super().activate()
        self._capture_source_selection()
        self.reset_state()
        self.widget.show_on_canvas()

    def deactivate(self) -> None:
        self.cleanup()
        super().deactivate()

    def cleanup(self) -> None:
        self.widget.hide()
        self._clear_bands()
        self.snap_indicator.setMatch(QgsPointLocator.Match())

    def _capture_source_selection(self) -> bool:
        layer = self.current_vector_layer()
        features = layer.selectedFeatures() if layer else []
        if not layer or not features:
            self.source_layer = None
            self.source_features = []
            return False
        self.source_layer = layer
        self.source_features = features
        return True

    def _source_keys(self) -> Set[Tuple[str, int]]:
        if not self.source_layer:
            return set()
        return {(self.source_layer.id(), feature.id()) for feature in self.source_features}

    def reset_state(self) -> None:
        self.stage = 0
        self.source_start = None
        self.source_end = None
        self.target_start = None
        self.target_end = None
        self.source_edge = None
        self.target_edge = None
        self.hover_target_end = None
        self.hover_target_edge = None
        self.flip = False
        self._clear_bands()
        if self.widget.reference_mode() == AlignReferenceMode.Edges:
            self.widget.set_stage("source_edge")
        else:
            self.widget.set_stage("source_first")
        self.widget.set_preview(0.0, 1.0, self.ctrl_pressed, self.shift_pressed)

    def _clear_bands(self) -> None:
        self.source_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.target_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def _snapped_point(self, event: QgsMapMouseEvent) -> QgsPointXY:
        match = self.canvas.snappingUtils().snapToMap(event.pos())
        self.snap_indicator.setMatch(match)
        return QgsPointXY(match.point()) if match.isValid() else self.toMapCoordinates(event.pos())

    def canvasMoveEvent(self, event: QgsMapMouseEvent) -> None:
        if not self.source_features and not self._capture_source_selection():
            return
        map_point = self._snapped_point(event)
        if self.widget.reference_mode() == AlignReferenceMode.Points:
            self._move_points(map_point)
        else:
            self._move_edges(map_point)

    def _move_points(self, map_point: QgsPointXY) -> None:
        if self.stage == 1 and self.source_start:
            self.source_band.setToGeometry(
                QgsGeometry.fromPolylineXY([self.source_start, map_point]),
                None,
            )
        elif self.stage == 3 and self.target_start:
            self.hover_target_end = QgsPointXY(map_point)
            self.target_band.setToGeometry(
                QgsGeometry.fromPolylineXY([self.target_start, map_point]),
                None,
            )
            self._update_preview()

    def _move_edges(self, map_point: QgsPointXY) -> None:
        if self.stage == 0:
            match = SnappingHelper.find_segment_across_visible_layers(
                self.canvas,
                map_point,
                included_features=self._source_keys(),
            )
            if match:
                self.source_band.setToGeometry(
                    QgsGeometry.fromPolylineXY([match.p1, match.p2]),
                    None,
                )
        else:
            self.hover_target_edge = SnappingHelper.find_segment_across_visible_layers(
                self.canvas,
                map_point,
                excluded_features=self._source_keys(),
            )
            if self.hover_target_edge:
                self.target_band.setToGeometry(
                    QgsGeometry.fromPolylineXY(
                        [self.hover_target_edge.p1, self.hover_target_edge.p2]
                    ),
                    None,
                )
                self._update_preview()
            else:
                self.target_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
                self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:
        if event.button() == _RIGHT_BUTTON:
            self.step_back()
            return
        if event.button() != _LEFT_BUTTON:
            return
        if not self._capture_source_selection():
            self._show_warning(self.tr("Виберіть об'єкти в редагованому шарі."))
            return
        map_point = self._snapped_point(event)
        modifiers = event.modifiers()
        self.shift_pressed = bool(modifiers & _SHIFT_MODIFIER)
        self.ctrl_pressed = bool(modifiers & _CTRL_MODIFIER)
        if self.widget.reference_mode() == AlignReferenceMode.Points:
            self._press_points(map_point)
        else:
            self._press_edges(map_point)

    def _press_points(self, map_point: QgsPointXY) -> None:
        if self.stage == 0:
            self.source_start = QgsPointXY(map_point)
            self.stage = 1
            self.widget.set_stage("source_second")
        elif self.stage == 1:
            if GeometryEngine.distance(self.source_start, map_point) < GeometryEngine.EPSILON:
                self._show_warning(self.tr("Опорні точки Source мають відрізнятися."))
                return
            self.source_end = QgsPointXY(map_point)
            self.source_band.setToGeometry(
                QgsGeometry.fromPolylineXY([self.source_start, self.source_end]),
                None,
            )
            self.stage = 2
            self.widget.set_stage("target_first")
        elif self.stage == 2:
            self.target_start = QgsPointXY(map_point)
            self.stage = 3
            self.widget.set_stage("target_second")
        else:
            self.target_end = QgsPointXY(map_point)
            self.hover_target_end = self.target_end
            self.commit_alignment()

    def _press_edges(self, map_point: QgsPointXY) -> None:
        if self.stage == 0:
            match = SnappingHelper.find_segment_across_visible_layers(
                self.canvas,
                map_point,
                included_features=self._source_keys(),
            )
            if not match:
                self._show_warning(self.tr("Вкажіть ребро одного з вибраних об'єктів."))
                return
            self.source_edge = match
            self.source_band.setToGeometry(
                QgsGeometry.fromPolylineXY([match.p1, match.p2]),
                None,
            )
            self.stage = 1
            self.widget.set_stage("target_edge")
        else:
            match = SnappingHelper.find_segment_across_visible_layers(
                self.canvas,
                map_point,
                excluded_features=self._source_keys(),
            )
            if not match:
                self._show_warning(self.tr("Вкажіть ребро Target з видимого шару."))
                return
            self.target_edge = match
            self.hover_target_edge = match
            self.commit_alignment()

    @staticmethod
    def _target_edge_order(
        source_start: QgsPointXY,
        source_end: QgsPointXY,
        target_start: QgsPointXY,
        target_end: QgsPointXY,
        flip: bool,
    ) -> Tuple[QgsPointXY, QgsPointXY]:
        source_angle = math.atan2(
            source_end.y() - source_start.y(),
            source_end.x() - source_start.x(),
        )

        def delta(first: QgsPointXY, second: QgsPointXY) -> float:
            value = math.degrees(
                math.atan2(second.y() - first.y(), second.x() - first.x())
                - source_angle
            )
            while value <= -180.0:
                value += 360.0
            while value > 180.0:
                value -= 360.0
            return abs(value)

        normal = (target_start, target_end)
        reversed_order = (target_end, target_start)
        ordered = normal if delta(*normal) <= delta(*reversed_order) else reversed_order
        return (ordered[1], ordered[0]) if flip else ordered

    def _current_references(self):
        if self.widget.reference_mode() == AlignReferenceMode.Points:
            target_end = self.target_end or self.hover_target_end
            if not all((self.source_start, self.source_end, self.target_start, target_end)):
                return None
            return self.source_start, self.source_end, self.target_start, target_end
        target_edge = self.target_edge or self.hover_target_edge
        if not self.source_edge or not target_edge:
            return None
        target_start, target_end = self._target_edge_order(
            self.source_edge.p1,
            self.source_edge.p2,
            target_edge.p1,
            target_edge.p2,
            self.flip,
        )
        return self.source_edge.p1, self.source_edge.p2, target_start, target_end

    def _update_preview(self) -> None:
        references = self._current_references()
        if not references or not self.source_layer:
            return
        try:
            angle, scale, move_x, move_y = GeometryEngine.compute_alignment_transform(
                *references,
                fit=self.shift_pressed,
                flip=(self.flip and self.widget.reference_mode() == AlignReferenceMode.Points),
            )
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            self.preview_band.reset(self.source_layer.geometryType())
            for feature in self.source_features:
                canvas_geom = transform_geometry_copy(
                    feature.geometry(),
                    self.source_layer.crs(),
                    canvas_crs,
                )
                transformed = GeometryEngine.apply_similarity_transform(
                    canvas_geom,
                    references[0],
                    angle,
                    scale,
                    move_x,
                    move_y,
                )
                self.preview_band.addGeometry(transformed, None)
            self.widget.set_preview(
                angle,
                scale,
                self.ctrl_pressed,
                self.shift_pressed,
            )
        except (RuntimeError, TypeError, ValueError):
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def commit_alignment(self) -> None:
        references = self._current_references()
        layer = self.source_layer
        if not references or not layer or not layer.isEditable():
            return
        try:
            angle, scale, move_x, move_y = GeometryEngine.compute_alignment_transform(
                *references,
                fit=self.shift_pressed,
                flip=(self.flip and self.widget.reference_mode() == AlignReferenceMode.Points),
            )
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            new_features: List[QgsFeature] = []
            geometry_changes = []
            for feature in self.source_features:
                canvas_geom = transform_geometry_copy(
                    feature.geometry(),
                    layer.crs(),
                    canvas_crs,
                )
                transformed = GeometryEngine.apply_similarity_transform(
                    canvas_geom,
                    references[0],
                    angle,
                    scale,
                    move_x,
                    move_y,
                )
                layer_geom = transform_geometry_copy(transformed, canvas_crs, layer.crs())
                if self.ctrl_pressed:
                    copied = QgsFeature(feature)
                    copied.setGeometry(layer_geom)
                    new_features.append(copied)
                else:
                    geometry_changes.append((feature.id(), layer_geom))
            with checked_edit_command(layer, self.tr("CAD Align Feature(s)")):
                if self.ctrl_pressed:
                    require_edit_success(
                        layer.addFeatures(new_features),
                        self.tr("Не вдалося додати вирівняні копії."),
                    )
                else:
                    for feature_id, geometry in geometry_changes:
                        require_edit_success(
                            layer.changeGeometry(feature_id, geometry),
                            self.tr("Не вдалося вирівняти геометрію."),
                        )
            if self.ctrl_pressed:
                new_ids = [feature.id() for feature in new_features if feature.id() >= 0]
                if new_ids:
                    layer.selectByIds(new_ids)
            layer.updateExtents()
            layer.triggerRepaint()
            self.canvas.refresh()
            self._capture_source_selection()
            self.reset_state()
        except (RuntimeError, TypeError, ValueError) as error:
            self._show_warning(str(error))

    def step_back(self) -> None:
        if self.widget.reference_mode() == AlignReferenceMode.Edges:
            if self.stage > 0:
                self.reset_state()
            else:
                self._deactivate_tool()
            return
        if self.stage == 3:
            self.target_start = None
            self.target_end = None
            self.hover_target_end = None
            self.stage = 2
            self.target_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.set_stage("target_first")
        elif self.stage == 2:
            self.source_end = None
            self.stage = 1
            self.widget.set_stage("source_second")
        elif self.stage == 1:
            self.reset_state()
        else:
            self._deactivate_tool()

    def _escape(self) -> None:
        if self.stage > 0:
            self.reset_state()
        else:
            self._deactivate_tool()

    def _deactivate_tool(self) -> None:
        if self.iface and hasattr(self.iface, "actionPan") and self.iface.actionPan():
            self.iface.actionPan().trigger()
        elif self.canvas.mapTool() == self:
            self.canvas.unsetMapTool(self)

    def _on_mode_changed(self, mode: int) -> None:
        self.reset_state()

    def _on_shortcut(self, shortcut: str) -> None:
        if shortcut == "flip":
            self.flip = not self.flip
            self._update_preview()

    def _on_modifier_changed(self, name: str, pressed: bool) -> None:
        if name == "shift":
            self.shift_pressed = pressed
        elif name == "ctrl":
            self.ctrl_pressed = pressed
        self._update_preview()

    def keyPressEvent(self, event) -> None:
        key = int(event.key())
        if key in (_KEY_ESCAPE, _KEY_BACKSPACE):
            self.step_back()
            event.accept()
            return
        if key in (_KEY_RETURN, _KEY_ENTER):
            self.commit_alignment()
            event.accept()
            return
        if key == _KEY_F:
            self.flip = not self.flip
            self._update_preview()
            event.accept()
            return
        if key == int(getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020))):
            self.shift_pressed = True
            self._update_preview()
        elif key == int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021))):
            self.ctrl_pressed = True
            self._update_preview()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        key = int(event.key())
        if key == int(getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020))):
            self.shift_pressed = False
            self._update_preview()
        elif key == int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021))):
            self.ctrl_pressed = False
            self._update_preview()
        super().keyReleaseEvent(event)

    def _show_warning(self, text: str) -> None:
        if self.iface and hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushWarning(
                self.tr("Align Feature"),
                self.tr(text),
            )

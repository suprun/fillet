# -*- coding: utf-8 -*-
"""Interactive Array Along Path map tool."""

from typing import List, Optional, Set, Tuple

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapMouseEvent, QgsMapToolEdit, QgsRubberBand, QgsSnapIndicator
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor, QCursor

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import LayerFeatureMatch, SnappingHelper
    from .array_along_path_canvas_widget import (
        ArrayAlongPathCanvasWidget,
        PathDistributionMode,
        PathRangeMode,
    )
    from .gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import LayerFeatureMatch, SnappingHelper
    from gui.array_along_path_canvas_widget import (
        ArrayAlongPathCanvasWidget,
        PathDistributionMode,
        PathRangeMode,
    )
    from gui.gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy


_LEFT_BUTTON = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RIGHT_BUTTON = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_SHIFT_MODIFIER = getattr(Qt.KeyboardModifier, "ShiftModifier", getattr(Qt, "ShiftModifier", 0x02000000))
_CTRL_MODIFIER = getattr(Qt.KeyboardModifier, "ControlModifier", getattr(Qt, "ControlModifier", 0x04000000))
_CROSS_CURSOR = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))


class ArrayAlongPathMapTool(QgsMapToolEdit):
    """Copy one selected feature group along a clicked line part."""

    STATE_ANCHOR = 0
    STATE_PATH = 1
    STATE_RANGE_START = 2
    STATE_RANGE_END = 3
    STATE_PREVIEW = 4

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas, widget: ArrayAlongPathCanvasWidget, iface=None) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.iface = iface
        self.source_layer: Optional[QgsVectorLayer] = None
        self.source_features: List[QgsFeature] = []
        self.anchor: Optional[QgsPointXY] = None
        self.path_layer: Optional[QgsVectorLayer] = None
        self.path_fid: Optional[int] = None
        self.path_geometry: Optional[QgsGeometry] = None
        self.start_measure: Optional[float] = None
        self.end_measure: Optional[float] = None
        self.state = self.STATE_ANCHOR
        self.shift_pressed = False
        self.ctrl_pressed = False
        self.hover_path: Optional[QgsGeometry] = None
        self.snap_indicator = QgsSnapIndicator(canvas)
        self.anchor_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.anchor_band.setIcon(QgsRubberBand.ICON_CROSS)
        self.anchor_band.setIconSize(12)
        self.anchor_band.setColor(QColor(234, 88, 12, 230))
        self.path_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.path_band.setColor(QColor(79, 70, 229, 220))
        self.path_band.setWidth(3)
        self.range_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.range_band.setIcon(QgsRubberBand.ICON_CIRCLE)
        self.range_band.setIconSize(10)
        self.range_band.setColor(QColor(5, 150, 105, 230))
        self.preview_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_band.setColor(QColor(37, 99, 235, 55))
        self.preview_band.setStrokeColor(QColor(29, 78, 216, 210))
        self.preview_band.setWidth(2)
        if _CROSS_CURSOR is not None:
            self.setCursor(QCursor(_CROSS_CURSOR))
        if hasattr(self, "setToolName"):
            self.setToolName(self.tr("CAD Масив уздовж шляху"))
        self.widget.parametersChanged.connect(self._on_parameters_changed)
        self.widget.stepBackRequested.connect(self.step_back)
        self.widget.resetRequested.connect(self._escape)
        self.widget.commitRequested.connect(self.commit_array)
        self.widget.modifierChanged.connect(self._on_modifier_changed)

    def _capture_source_selection(self) -> bool:
        layer = self.canvas.currentLayer()
        if not isinstance(layer, QgsVectorLayer) or not layer.isEditable() or not layer.isSpatial():
            self.source_layer = None
            self.source_features = []
            return False
        features = layer.selectedFeatures()
        if not features:
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

    def activate(self) -> None:
        super().activate()
        self._capture_source_selection()
        if self.source_layer:
            self.widget.adapt_to_crs(self.canvas.mapSettings().destinationCrs())
        self.reset_state()
        self.widget.show_on_canvas()

    def deactivate(self) -> None:
        self.cleanup()
        super().deactivate()

    def cleanup(self) -> None:
        self.widget.hide()
        self.anchor_band.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.path_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.range_band.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def reset_state(self) -> None:
        self.anchor = None
        self.path_layer = None
        self.path_fid = None
        self.path_geometry = None
        self.start_measure = None
        self.end_measure = None
        self.hover_path = None
        self.state = self.STATE_ANCHOR
        self.cleanup()
        self.widget.set_stage("anchor")
        self.widget.set_calculated_count(0)
        self.widget.set_modifier_state(self.shift_pressed, self.ctrl_pressed)
        if self.canvas.mapTool() == self:
            self.widget.show_on_canvas()

    def _snapped_point(self, event: QgsMapMouseEvent) -> QgsPointXY:
        match = self.canvas.snappingUtils().snapToMap(event.pos())
        self.snap_indicator.setMatch(match)
        return QgsPointXY(match.point()) if match.isValid() else self.toMapCoordinates(event.pos())

    def canvasMoveEvent(self, event: QgsMapMouseEvent) -> None:
        point = self._snapped_point(event)
        if self.state == self.STATE_ANCHOR:
            return
        if self.state == self.STATE_PATH:
            match = SnappingHelper.find_feature_across_visible_layers(
                self.canvas,
                point,
                geometry_types=[QgsWkbTypes.GeometryType.LineGeometry],
                excluded_features=self._source_keys(),
            )
            self.hover_path = self._clicked_path_part(match, point) if match else None
            if self.hover_path:
                self.path_band.setToGeometry(self.hover_path, None)
            else:
                self.path_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
        elif self.state in (self.STATE_RANGE_START, self.STATE_RANGE_END):
            measure, projected = self._project_to_path(point)
            if measure is not None and projected is not None:
                self.range_band.reset(QgsWkbTypes.GeometryType.PointGeometry)
                if self.start_measure is not None:
                    start_point = self.path_geometry.interpolate(self.start_measure).asPoint()
                    self.range_band.addPoint(QgsPointXY(start_point), False)
                self.range_band.addPoint(projected, True)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:
        if event.button() == _RIGHT_BUTTON:
            self.step_back()
            return
        if event.button() != _LEFT_BUTTON:
            return
        if not self._capture_source_selection():
            self._show_warning(self.tr("Виберіть об'єкти в редагованому шарі."))
            return
        modifiers = event.modifiers()
        self.shift_pressed = bool(modifiers & _SHIFT_MODIFIER)
        self.ctrl_pressed = bool(modifiers & _CTRL_MODIFIER)
        point = self._snapped_point(event)
        if self.state == self.STATE_ANCHOR:
            self.anchor = QgsPointXY(point)
            self.anchor_band.addPoint(self.anchor, True)
            self.state = self.STATE_PATH
            self.widget.set_stage("path")
            return
        if self.state == self.STATE_PATH:
            match = SnappingHelper.find_feature_across_visible_layers(
                self.canvas,
                point,
                geometry_types=[QgsWkbTypes.GeometryType.LineGeometry],
                excluded_features=self._source_keys(),
            )
            path_part = self._clicked_path_part(match, point) if match else None
            if not match or not path_part or path_part.length() < GeometryEngine.EPSILON:
                self._show_warning(self.tr("Вкажіть непорожню лінійну частину Path."))
                return
            self.path_layer = match.layer
            self.path_fid = match.fid
            self.path_geometry = path_part
            self.path_band.setToGeometry(path_part, None)
            if self.widget.range_mode() == PathRangeMode.Subrange:
                self.state = self.STATE_RANGE_START
                self.widget.set_stage("range_start")
            else:
                self.start_measure = 0.0
                self.end_measure = path_part.length()
                self.state = self.STATE_PREVIEW
                self.widget.set_stage("preview")
                self._update_preview()
            return
        if self.state == self.STATE_RANGE_START:
            measure, projected = self._project_to_path(point)
            if measure is None:
                return
            self.start_measure = measure
            self.range_band.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.range_band.addPoint(projected, True)
            self.state = self.STATE_RANGE_END
            self.widget.set_stage("range_end")
            return
        if self.state == self.STATE_RANGE_END:
            measure, projected = self._project_to_path(point)
            if measure is None or abs(measure - self.start_measure) < GeometryEngine.EPSILON:
                self._show_warning(self.tr("Початок і кінець піддіапазону мають відрізнятися."))
                return
            self.end_measure = measure
            self.range_band.addPoint(projected, True)
            self.state = self.STATE_PREVIEW
            self.widget.set_stage("preview")
            self._update_preview()
            return
        self.commit_array()

    def _clicked_path_part(
        self,
        match: Optional[LayerFeatureMatch],
        map_point: QgsPointXY,
    ) -> Optional[QgsGeometry]:
        if not match:
            return None
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        geometry = transform_geometry_copy(
            match.geometry,
            match.layer.crs(),
            canvas_crs,
        )
        parts = geometry.asGeometryCollection() if geometry.isMultipart() else [geometry]
        point_geom = QgsGeometry.fromPointXY(map_point)
        candidates = [part for part in parts if part.type() == QgsWkbTypes.GeometryType.LineGeometry]
        if not candidates:
            return None
        return QgsGeometry(min(candidates, key=lambda part: part.distance(point_geom)))

    def _project_to_path(self, point: QgsPointXY):
        if not self.path_geometry:
            return None, None
        point_geom = QgsGeometry.fromPointXY(point)
        measure = self.path_geometry.lineLocatePoint(point_geom)
        if measure < 0:
            return None, None
        projected_geom = self.path_geometry.interpolate(measure)
        if projected_geom.isEmpty():
            return None, None
        return measure, QgsPointXY(projected_geom.asPoint())

    def _placements(self):
        if (
            not self.path_geometry
            or self.start_measure is None
            or self.end_measure is None
        ):
            return []
        mode = (
            "spacing"
            if self.widget.distribution_mode() == PathDistributionMode.Spacing
            else "count"
        )
        value = (
            self.widget.spacing_value()
            if mode == "spacing"
            else float(self.widget.count_value())
        )
        return GeometryEngine.compute_path_placements(
            self.path_geometry,
            self.start_measure,
            self.end_measure,
            mode,
            value,
            include_start=self.widget.include_start(),
            offset=self.widget.offset_value(),
            tangent_orientation=self.shift_pressed,
            reverse=self.ctrl_pressed,
        )

    def _update_preview(self) -> None:
        if self.state != self.STATE_PREVIEW or not self.source_layer or not self.anchor:
            return
        try:
            placements = self._placements()
            self.widget.set_calculated_count(len(placements))
            self.widget.set_modifier_state(self.shift_pressed, self.ctrl_pressed)
            self.preview_band.reset(self.source_layer.geometryType())
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            canvas_geometries = [
                transform_geometry_copy(
                    feature.geometry(),
                    self.source_layer.crs(),
                    canvas_crs,
                )
                for feature in self.source_features
            ]
            for position, angle in placements:
                move_x = position.x() - self.anchor.x()
                move_y = position.y() - self.anchor.y()
                for geometry in canvas_geometries:
                    transformed = GeometryEngine.apply_similarity_transform(
                        geometry,
                        self.anchor,
                        angle,
                        1.0,
                        move_x,
                        move_y,
                    )
                    self.preview_band.addGeometry(transformed, None)
        except (RuntimeError, TypeError, ValueError):
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.set_calculated_count(0)

    def commit_array(self) -> None:
        layer = self.source_layer
        if self.state != self.STATE_PREVIEW or not layer or not self.anchor:
            return
        try:
            placements = self._placements()
            if not placements:
                self._show_warning(self.tr("Поточні параметри не створюють жодної копії."))
                return
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            new_features: List[QgsFeature] = []
            for source_feature in self.source_features:
                canvas_geom = transform_geometry_copy(
                    source_feature.geometry(),
                    layer.crs(),
                    canvas_crs,
                )
                for position, angle in placements:
                    transformed = GeometryEngine.apply_similarity_transform(
                        canvas_geom,
                        self.anchor,
                        angle,
                        1.0,
                        position.x() - self.anchor.x(),
                        position.y() - self.anchor.y(),
                    )
                    copied = QgsFeature(source_feature)
                    copied.setGeometry(
                        transform_geometry_copy(transformed, canvas_crs, layer.crs())
                    )
                    new_features.append(copied)
            with checked_edit_command(layer, self.tr("CAD Array Along Path")):
                require_edit_success(
                    layer.addFeatures(new_features),
                    self.tr("Не вдалося створити масив уздовж шляху."),
                )
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

    def _on_parameters_changed(self) -> None:
        if not self.path_geometry:
            return
        if self.widget.range_mode() == PathRangeMode.WholePath:
            self.start_measure = 0.0
            self.end_measure = self.path_geometry.length()
            self.state = self.STATE_PREVIEW
            self.widget.set_stage("preview")
        elif self.start_measure is None or self.end_measure is None:
            self.start_measure = None
            self.end_measure = None
            self.state = self.STATE_RANGE_START
            self.widget.set_stage("range_start")
        self._update_preview()

    def _on_modifier_changed(self, name: str, pressed: bool) -> None:
        if name == "shift":
            self.shift_pressed = pressed
        elif name == "ctrl":
            self.ctrl_pressed = pressed
        self._update_preview()

    def step_back(self) -> None:
        if self.state == self.STATE_PREVIEW and self.widget.range_mode() == PathRangeMode.Subrange:
            self.end_measure = None
            self.state = self.STATE_RANGE_END
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.set_stage("range_end")
        elif self.state in (self.STATE_RANGE_START, self.STATE_RANGE_END, self.STATE_PREVIEW):
            self.path_layer = None
            self.path_fid = None
            self.path_geometry = None
            self.start_measure = None
            self.end_measure = None
            self.state = self.STATE_PATH
            self.path_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self.range_band.reset(QgsWkbTypes.GeometryType.PointGeometry)
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.set_stage("path")
        elif self.state == self.STATE_PATH:
            self.reset_state()
        else:
            self._deactivate_tool()

    def _escape(self) -> None:
        self.step_back()

    def _deactivate_tool(self) -> None:
        if self.iface and hasattr(self.iface, "actionPan") and self.iface.actionPan():
            self.iface.actionPan().trigger()
        elif self.canvas.mapTool() == self:
            self.canvas.unsetMapTool(self)

    def keyPressEvent(self, event) -> None:
        key = int(event.key())
        key_escape = int(getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000)))
        key_backspace = int(getattr(Qt.Key, "Key_Backspace", getattr(Qt, "Key_Backspace", 0x01000003)))
        key_return = int(getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004)))
        key_enter = int(getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005)))
        key_shift = int(getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020)))
        key_ctrl = int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021)))
        if key in (key_escape, key_backspace):
            self.step_back()
            event.accept()
            return
        if key in (key_return, key_enter):
            self.commit_array()
            event.accept()
            return
        if key == key_shift:
            self.shift_pressed = True
            self._update_preview()
        elif key == key_ctrl:
            self.ctrl_pressed = True
            self._update_preview()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        key = int(event.key())
        key_shift = int(getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020)))
        key_ctrl = int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021)))
        if key == key_shift:
            self.shift_pressed = False
            self._update_preview()
        elif key == key_ctrl:
            self.ctrl_pressed = False
            self._update_preview()
        super().keyReleaseEvent(event)

    def _show_warning(self, text: str) -> None:
        if self.iface and hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushWarning(
                self.tr("Array Along Path"),
                self.tr(text),
            )

# -*- coding: utf-8 -*-
"""Shared interactive Subtract Feature and Clip Feature map tool."""

from typing import List, Optional, Tuple

from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapMouseEvent, QgsMapToolEdit, QgsRubberBand
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor, QCursor

try:
    from ..core.geometry_engine import BooleanOperation, GeometryEngine
    from ..core.snapping_helper import LayerFeatureMatch, SnappingHelper
    from .boolean_feature_canvas_widget import BooleanFeatureCanvasWidget
    from .gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy
except (ImportError, ValueError):
    from core.geometry_engine import BooleanOperation, GeometryEngine
    from core.snapping_helper import LayerFeatureMatch, SnappingHelper
    from gui.boolean_feature_canvas_widget import BooleanFeatureCanvasWidget
    from gui.gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy


_LEFT_BUTTON = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RIGHT_BUTTON = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_SHIFT_MODIFIER = getattr(Qt.KeyboardModifier, "ShiftModifier", getattr(Qt, "ShiftModifier", 0x02000000))
_CTRL_MODIFIER = getattr(Qt.KeyboardModifier, "ControlModifier", getattr(Qt, "ControlModifier", 0x04000000))
_CROSS_CURSOR = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))


class BooleanFeatureMapTool(QgsMapToolEdit):
    """Edit one polygon target using feature-to-feature boolean operations."""

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(
        self,
        canvas,
        widget: BooleanFeatureCanvasWidget,
        operation: str,
        iface=None,
    ) -> None:
        super().__init__(canvas)
        try:
            operation_mode = BooleanOperation(operation)
        except ValueError as error:
            raise ValueError("Unsupported boolean feature operation") from error
        self.canvas = canvas
        self.widget = widget
        self.operation = operation_mode
        self.iface = iface
        self.target_layer: Optional[QgsVectorLayer] = None
        self.target_fid: Optional[int] = None
        self.pending_cutters: List[LayerFeatureMatch] = []
        self.pending_continuous = False
        self.ctrl_pressed = False
        self.hover_cutter: Optional[LayerFeatureMatch] = None
        self.commit_indices: List[int] = []
        self.target_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.target_band.setColor(QColor(234, 88, 12, 40))
        self.target_band.setStrokeColor(QColor(234, 88, 12, 220))
        self.target_band.setWidth(3)
        self.cutter_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.cutter_band.setColor(QColor(5, 150, 105, 45))
        self.cutter_band.setStrokeColor(QColor(5, 150, 105, 220))
        self.cutter_band.setWidth(2)
        self.preview_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_band.setColor(QColor(37, 99, 235, 70))
        self.preview_band.setStrokeColor(QColor(29, 78, 216, 230))
        self.preview_band.setWidth(3)
        if _CROSS_CURSOR is not None:
            self.setCursor(QCursor(_CROSS_CURSOR))
        if hasattr(self, "setToolName"):
            title = (
                self.tr("CAD Віднімання об'єкта (Subtract Feature)")
                if operation_mode == BooleanOperation.Subtract
                else self.tr("CAD Обрізання об'єкта (Clip Feature)")
            )
            self.setToolName(title)
        self.widget.commitRequested.connect(self.commit_pending)
        self.widget.stepBackRequested.connect(self.step_back)
        self.widget.resetRequested.connect(self._escape)
        self.widget.modifierChanged.connect(self._on_modifier_changed)

    @property
    def command_text(self) -> str:
        return self.tr(
            "CAD Subtract Feature"
            if self.operation == BooleanOperation.Subtract
            else "CAD Clip Feature"
        )

    def current_polygon_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isEditable()
            and layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry
        ):
            return layer
        return None

    def activate(self) -> None:
        super().activate()
        self.reset_state(clear_history=True)
        self.widget.show_on_canvas()

    def deactivate(self) -> None:
        self.cleanup()
        super().deactivate()

    def cleanup(self) -> None:
        self.widget.hide()
        self.target_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.cutter_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def reset_state(self, clear_history: bool = False) -> None:
        self.target_layer = None
        self.target_fid = None
        self.pending_cutters = []
        self.pending_continuous = False
        self.hover_cutter = None
        if clear_history:
            self.commit_indices = []
        self.cleanup()
        self.widget.set_stage(False)
        self.widget.update_state(None, 0, False)
        if self.canvas.mapTool() == self:
            self.widget.show_on_canvas()

    def canvasMoveEvent(self, event: QgsMapMouseEvent) -> None:
        point = self.toMapCoordinates(event.pos())
        if self.target_fid is None:
            target = self._target_at(point)
            if target:
                self._show_geometry_band(self.target_band, target)
            else:
                self.target_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return
        self.hover_cutter = self._cutter_at(point)
        self._update_cutter_band()
        self._update_preview()

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:
        if event.button() == _RIGHT_BUTTON:
            self.step_back()
            return
        if event.button() != _LEFT_BUTTON:
            return
        point = self.toMapCoordinates(event.pos())
        if self.target_fid is None:
            target = self._target_at(point)
            if not target:
                self._show_warning(self.tr("Вкажіть полігон Target у поточному редагованому шарі."))
                return
            try:
                self._validate_supported_geometry(target.geometry)
            except ValueError as error:
                self._show_warning(str(error))
                return
            self.target_layer = target.layer
            self.target_fid = target.fid
            self._show_geometry_band(self.target_band, target)
            self.widget.set_stage(True)
            self.widget.update_state(self.target_fid, 0, False)
            return

        cutter = self._cutter_at(point)
        if not cutter:
            self._show_warning(self.tr("Вкажіть полігон Cutter з видимого шару."))
            return
        try:
            self._validate_supported_geometry(cutter.geometry)
        except ValueError as error:
            self._show_warning(str(error))
            return
        modifiers = event.modifiers()
        shift = bool(modifiers & _SHIFT_MODIFIER)
        ctrl = bool(modifiers & _CTRL_MODIFIER)
        self.ctrl_pressed = ctrl
        if shift:
            key = (cutter.layer.id(), cutter.fid)
            if all((item.layer.id(), item.fid) != key for item in self.pending_cutters):
                self.pending_cutters.append(cutter)
            if ctrl:
                self.pending_continuous = True
            self.hover_cutter = None
            self._update_cutter_band()
            self._update_preview()
            self.widget.update_state(
                self.target_fid,
                len(self.pending_cutters),
                self.pending_continuous,
            )
            return
        cutters = list(self.pending_cutters)
        if all(
            (item.layer.id(), item.fid) != (cutter.layer.id(), cutter.fid)
            for item in cutters
        ):
            cutters.append(cutter)
        self._commit(cutters, keep_target=ctrl or self.pending_continuous)

    def _target_at(self, point: QgsPointXY) -> Optional[LayerFeatureMatch]:
        layer = self.current_polygon_layer()
        if not layer:
            return None
        return SnappingHelper.find_feature_across_visible_layers(
            self.canvas,
            point,
            geometry_types=[QgsWkbTypes.GeometryType.PolygonGeometry],
            require_editable=True,
            included_layer_ids={layer.id()},
        )

    def _cutter_at(self, point: QgsPointXY) -> Optional[LayerFeatureMatch]:
        excluded = set()
        if self.target_layer and self.target_fid is not None:
            excluded.add((self.target_layer.id(), self.target_fid))
        return SnappingHelper.find_feature_across_visible_layers(
            self.canvas,
            point,
            geometry_types=[QgsWkbTypes.GeometryType.PolygonGeometry],
            excluded_features=excluded,
        )

    @staticmethod
    def _validate_supported_geometry(geometry: QgsGeometry) -> None:
        if geometry.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
            raise ValueError("Geometry must be polygonal")
        if GeometryEngine.has_curved_segments(geometry) or QgsWkbTypes.hasM(
            geometry.wkbType()
        ):
            raise ValueError("M/ZM and curved polygon geometries are not supported")
        if not geometry.isGeosValid():
            raise ValueError("Geometry is invalid")

    def _show_geometry_band(
        self,
        band: QgsRubberBand,
        match: LayerFeatureMatch,
    ) -> None:
        canvas_geom = transform_geometry_copy(
            match.geometry,
            match.layer.crs(),
            self.canvas.mapSettings().destinationCrs(),
        )
        band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        band.addGeometry(canvas_geom, None)

    def _update_cutter_band(self) -> None:
        self.cutter_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        matches = list(self.pending_cutters)
        if self.hover_cutter and all(
            (item.layer.id(), item.fid)
            != (self.hover_cutter.layer.id(), self.hover_cutter.fid)
            for item in matches
        ):
            matches.append(self.hover_cutter)
        for match in matches:
            geometry = transform_geometry_copy(
                match.geometry,
                match.layer.crs(),
                canvas_crs,
            )
            self.cutter_band.addGeometry(geometry, None)

    def _target_geometry(self) -> Optional[QgsGeometry]:
        if not self.target_layer or self.target_fid is None:
            return None
        feature = self.target_layer.getFeature(self.target_fid)
        return feature.geometry() if feature.isValid() else None

    def _cutters_in_target_crs(
        self,
        cutters: List[LayerFeatureMatch],
    ) -> List[QgsGeometry]:
        if not self.target_layer:
            return []
        return [
            transform_geometry_copy(
                cutter.geometry,
                cutter.layer.crs(),
                self.target_layer.crs(),
            )
            for cutter in cutters
        ]

    def _preview_cutters(self) -> List[LayerFeatureMatch]:
        cutters = list(self.pending_cutters)
        if self.hover_cutter and all(
            (item.layer.id(), item.fid)
            != (self.hover_cutter.layer.id(), self.hover_cutter.fid)
            for item in cutters
        ):
            cutters.append(self.hover_cutter)
        return cutters

    def _update_preview(self) -> None:
        target = self._target_geometry()
        cutters = self._preview_cutters()
        if not target or not cutters or not self.target_layer:
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return
        try:
            result = GeometryEngine.apply_polygon_boolean(
                target,
                self._cutters_in_target_crs(cutters),
                self.operation,
            )
            if result.isEmpty():
                self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
                return
            canvas_result = transform_geometry_copy(
                result,
                self.target_layer.crs(),
                self.canvas.mapSettings().destinationCrs(),
            )
            self.preview_band.setToGeometry(canvas_result, None)
        except (RuntimeError, TypeError, ValueError):
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def commit_pending(self) -> None:
        if self.pending_cutters:
            self._commit(
                list(self.pending_cutters),
                keep_target=self.ctrl_pressed or self.pending_continuous,
            )

    def _commit(self, cutters: List[LayerFeatureMatch], keep_target: bool) -> None:
        layer = self.target_layer
        target = self._target_geometry()
        if not layer or self.target_fid is None or target is None or not cutters:
            return
        try:
            result = GeometryEngine.apply_polygon_boolean(
                target,
                self._cutters_in_target_crs(cutters),
                self.operation,
            )
            if result.isEmpty():
                message = (
                    self.tr("Результат був би порожнім; Target не змінено.")
                    if self.operation == BooleanOperation.Subtract
                    else self.tr("Геометрії не перекриваються; Target не змінено.")
                )
                self._show_warning(message)
                return
            if result.isMultipart() and not QgsWkbTypes.isMultiType(layer.wkbType()):
                self._show_warning(
                    self.tr("Multipart результат несумісний із singlepart Target layer.")
                )
                return
            if QgsWkbTypes.isMultiType(layer.wkbType()) and not result.isMultipart():
                result.convertToMultiType()
            with checked_edit_command(layer, self.command_text):
                require_edit_success(
                    layer.changeGeometry(self.target_fid, result),
                    self.tr("Не вдалося змінити геометрію Target."),
                )
            self.commit_indices.append(layer.undoStack().index())
            self.pending_cutters = []
            self.pending_continuous = False
            self.hover_cutter = None
            self.cutter_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            layer.updateExtents()
            layer.triggerRepaint()
            self.canvas.refresh()
            if keep_target:
                feature = layer.getFeature(self.target_fid)
                if feature.isValid():
                    self._show_geometry_band(
                        self.target_band,
                        LayerFeatureMatch(layer, feature.id(), QgsPointXY(), feature.geometry()),
                    )
                    self.widget.update_state(self.target_fid, 0, True)
                    self.widget.set_stage(True)
            else:
                self.target_layer = None
                self.target_fid = None
                self.target_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
                self.widget.update_state(None, 0, False)
                self.widget.set_stage(False)
        except (RuntimeError, TypeError, ValueError) as error:
            self._show_warning(str(error))

    def _undo_last_tool_command(self) -> bool:
        layer = self.target_layer or self.current_polygon_layer()
        if not layer or not self.commit_indices:
            return False
        undo_stack = layer.undoStack()
        expected_index = self.commit_indices[-1]
        if undo_stack.index() != expected_index or expected_index <= 0:
            self.commit_indices = []
            return False
        command = undo_stack.command(expected_index - 1)
        if command is None or self.command_text not in command.text():
            self.commit_indices = []
            return False
        undo_stack.undo()
        self.commit_indices.pop()
        layer.triggerRepaint()
        self.canvas.refresh()
        if self.target_fid is not None:
            feature = layer.getFeature(self.target_fid)
            if feature.isValid():
                self._show_geometry_band(
                    self.target_band,
                    LayerFeatureMatch(layer, feature.id(), QgsPointXY(), feature.geometry()),
                )
        return True

    def step_back(self) -> None:
        if self.pending_cutters:
            self.pending_cutters.pop()
            self._update_cutter_band()
            self._update_preview()
            self.widget.update_state(
                self.target_fid,
                len(self.pending_cutters),
                self.pending_continuous,
            )
        elif self._undo_last_tool_command():
            return
        elif self.target_fid is not None:
            self.target_layer = None
            self.target_fid = None
            self.target_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.set_stage(False)
            self.widget.update_state(None, 0, False)
        else:
            self._deactivate_tool()

    def _escape(self) -> None:
        if self.pending_cutters:
            self.pending_cutters = []
            self.pending_continuous = False
            self.cutter_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.update_state(self.target_fid, 0, False)
        elif self.target_fid is not None:
            self.target_layer = None
            self.target_fid = None
            self.target_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.set_stage(False)
            self.widget.update_state(None, 0, False)
        else:
            self._deactivate_tool()

    def _on_modifier_changed(self, name: str, pressed: bool) -> None:
        if name == "ctrl":
            self.ctrl_pressed = pressed
            self.widget.update_state(
                self.target_fid,
                len(self.pending_cutters),
                pressed or self.pending_continuous,
            )

    def keyPressEvent(self, event) -> None:
        key = int(event.key())
        key_escape = int(getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000)))
        key_backspace = int(getattr(Qt.Key, "Key_Backspace", getattr(Qt, "Key_Backspace", 0x01000003)))
        key_return = int(getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004)))
        key_enter = int(getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005)))
        key_ctrl = int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021)))
        if key == key_escape:
            self._escape()
            event.accept()
            return
        if key == key_backspace:
            self.step_back()
            event.accept()
            return
        if key in (key_return, key_enter):
            self.commit_pending()
            event.accept()
            return
        if key == key_ctrl:
            self.ctrl_pressed = True
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        key_ctrl = int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021)))
        if int(event.key()) == key_ctrl:
            self.ctrl_pressed = False
        super().keyReleaseEvent(event)

    def _deactivate_tool(self) -> None:
        if self.iface and hasattr(self.iface, "actionPan") and self.iface.actionPan():
            self.iface.actionPan().trigger()
        elif self.canvas.mapTool() == self:
            self.canvas.unsetMapTool(self)

    def _show_warning(self, text: str) -> None:
        if self.iface and hasattr(self.iface, "messageBar"):
            title = (
                self.tr("Subtract Feature")
                if self.operation == BooleanOperation.Subtract
                else self.tr("Clip Feature")
            )
            self.iface.messageBar().pushWarning(title, self.tr(text))

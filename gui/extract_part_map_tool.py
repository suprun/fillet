# -*- coding: utf-8 -*-
"""Interactive Extract Part map tool."""

from typing import List, Optional, Tuple

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapMouseEvent, QgsMapToolEdit, QgsRubberBand
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor, QCursor

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import LayerFeatureMatch, SnappingHelper
    from .extract_part_canvas_widget import ExtractPartCanvasWidget
    from .gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import LayerFeatureMatch, SnappingHelper
    from gui.extract_part_canvas_widget import ExtractPartCanvasWidget
    from gui.gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy


_LEFT_BUTTON = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RIGHT_BUTTON = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_SHIFT_MODIFIER = getattr(Qt.KeyboardModifier, "ShiftModifier", getattr(Qt, "ShiftModifier", 0x02000000))
_CTRL_MODIFIER = getattr(Qt.KeyboardModifier, "ControlModifier", getattr(Qt, "ControlModifier", 0x04000000))
_CROSS_CURSOR = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))


class ExtractPartMapTool(QgsMapToolEdit):
    """Move or copy individual parts from multipart features."""

    COMMAND_TEXT = "CAD Extract Part"

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas, widget: ExtractPartCanvasWidget, iface=None) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.iface = iface
        self.source_layer: Optional[QgsVectorLayer] = None
        self.source_fid: Optional[int] = None
        self.hovered: Optional[Tuple[int, QgsGeometry]] = None
        self.pending_indices: List[int] = []
        self.commit_indices: List[int] = []
        self.ctrl_pressed = False
        self.source_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.source_band.setColor(QColor(234, 88, 12, 35))
        self.source_band.setStrokeColor(QColor(234, 88, 12, 190))
        self.source_band.setWidth(2)
        self.hover_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.hover_band.setColor(QColor(37, 99, 235, 75))
        self.hover_band.setStrokeColor(QColor(29, 78, 216, 230))
        self.hover_band.setWidth(3)
        self.pending_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.pending_band.setColor(QColor(5, 150, 105, 70))
        self.pending_band.setStrokeColor(QColor(5, 150, 105, 230))
        self.pending_band.setWidth(3)
        if _CROSS_CURSOR is not None:
            self.setCursor(QCursor(_CROSS_CURSOR))
        if hasattr(self, "setToolName"):
            self.setToolName(self.tr("CAD Вилучення частини (Extract Part)"))
        self.widget.commitRequested.connect(self.commit_pending)
        self.widget.stepBackRequested.connect(self.step_back)
        self.widget.resetRequested.connect(self._escape)
        self.widget.modifierChanged.connect(self._on_modifier_changed)

    def current_layer(self) -> Optional[QgsVectorLayer]:
        layer = self.canvas.currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable() and layer.isSpatial():
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
        self.source_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.hover_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.pending_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def reset_state(self, clear_history: bool = False) -> None:
        self.source_layer = None
        self.source_fid = None
        self.hovered = None
        self.pending_indices = []
        if clear_history:
            self.commit_indices = []
        self.cleanup()
        self.widget.update_state(None, 0, self.ctrl_pressed)
        if self.canvas.mapTool() == self:
            self.widget.show_on_canvas()

    def canvasMoveEvent(self, event: QgsMapMouseEvent) -> None:
        layer = self.current_layer()
        if not layer:
            self.hovered = None
            self.hover_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return
        point = self.toMapCoordinates(event.pos())
        match = SnappingHelper.find_feature_across_visible_layers(
            self.canvas,
            point,
            geometry_types=[layer.geometryType()],
            require_editable=True,
            included_layer_ids={layer.id()},
        )
        if not match or not match.geometry.isMultipart():
            self.hovered = None
            self.hover_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return
        part = self._part_at_point(match, point)
        if part is None:
            self.hovered = None
            self.hover_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            return
        part_index, canvas_part = part
        self.hovered = (part_index, canvas_part)
        self.hover_band.reset(layer.geometryType())
        self.hover_band.addGeometry(canvas_part, None)

    def _part_at_point(
        self,
        match: LayerFeatureMatch,
        map_point: QgsPointXY,
    ) -> Optional[Tuple[int, QgsGeometry]]:
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        canvas_geom = transform_geometry_copy(
            match.geometry,
            match.layer.crs(),
            canvas_crs,
        )
        parts = canvas_geom.asGeometryCollection()
        if len(parts) < 2:
            return None
        point_geom = QgsGeometry.fromPointXY(map_point)
        distances = []
        for index, part in enumerate(parts):
            distance = 0.0 if part.contains(point_geom) else part.distance(point_geom)
            distances.append((distance, index, part))
        _, index, part = min(distances, key=lambda item: item[0])
        return index, QgsGeometry(part)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:
        if event.button() == _RIGHT_BUTTON:
            self.step_back()
            return
        if event.button() != _LEFT_BUTTON:
            return
        layer = self.current_layer()
        if not layer:
            return
        point = self.toMapCoordinates(event.pos())
        match = SnappingHelper.find_feature_across_visible_layers(
            self.canvas,
            point,
            geometry_types=[layer.geometryType()],
            require_editable=True,
            included_layer_ids={layer.id()},
        )
        if not match or not match.geometry.isMultipart():
            self._show_warning(self.tr("Вкажіть multipart feature у поточному шарі."))
            return
        part = self._part_at_point(match, point)
        if part is None:
            return
        part_index, _ = part
        modifiers = event.modifiers()
        shift = bool(modifiers & _SHIFT_MODIFIER)
        copy = bool(modifiers & _CTRL_MODIFIER)
        self.ctrl_pressed = copy

        if self.source_fid is not None and match.fid != self.source_fid:
            if self.pending_indices:
                self._show_warning(self.tr("Завершіть або скасуйте поточний набір частин."))
                return
            self.source_fid = None
        if self.source_fid is None:
            self.source_layer = layer
            self.source_fid = match.fid
            self._show_source(match)

        if shift:
            if part_index in self.pending_indices:
                self.pending_indices.remove(part_index)
            else:
                self.pending_indices.append(part_index)
            self._update_pending_band()
            self.widget.update_state(self.source_fid, len(self.pending_indices), copy)
            return
        if self.pending_indices:
            if part_index in self.pending_indices:
                self._commit(self.pending_indices, copy=copy)
            return
        self._commit([part_index], copy=copy)

    def _show_source(self, match: LayerFeatureMatch) -> None:
        canvas_geom = transform_geometry_copy(
            match.geometry,
            match.layer.crs(),
            self.canvas.mapSettings().destinationCrs(),
        )
        self.source_band.reset(match.layer.geometryType())
        self.source_band.addGeometry(canvas_geom, None)
        self.widget.update_state(match.fid, len(self.pending_indices), self.ctrl_pressed)

    def _update_pending_band(self) -> None:
        layer = self.source_layer
        if not layer or self.source_fid is None:
            return
        feature = layer.getFeature(self.source_fid)
        if not feature.isValid():
            return
        canvas_geom = transform_geometry_copy(
            feature.geometry(),
            layer.crs(),
            self.canvas.mapSettings().destinationCrs(),
        )
        parts = canvas_geom.asGeometryCollection()
        self.pending_band.reset(layer.geometryType())
        for index in self.pending_indices:
            if 0 <= index < len(parts):
                self.pending_band.addGeometry(parts[index], None)

    def commit_pending(self) -> None:
        if self.pending_indices:
            self._commit(self.pending_indices, copy=self.ctrl_pressed)

    def _commit(self, indices: List[int], copy: bool) -> None:
        layer = self.source_layer
        if not layer or self.source_fid is None or not layer.isEditable():
            return
        source = layer.getFeature(self.source_fid)
        if not source.isValid() or not source.geometry().isMultipart():
            self.reset_state()
            return
        all_parts = source.geometry().asGeometryCollection()
        selected = sorted(set(indices))
        if not copy and len(selected) >= len(all_parts):
            self._show_warning(self.tr("Щонайменше одна частина має залишитися у Source."))
            return
        try:
            remaining, extracted = GeometryEngine.extract_geometry_parts(
                source.geometry(),
                selected,
            )
            new_features: List[QgsFeature] = []
            for part in extracted:
                new_feature = QgsFeature(source)
                output_part = QgsGeometry(part)
                if QgsWkbTypes.isMultiType(layer.wkbType()) and not output_part.isMultipart():
                    output_part.convertToMultiType()
                new_feature.setGeometry(output_part)
                new_features.append(new_feature)
            command_text = self.tr(self.COMMAND_TEXT)
            with checked_edit_command(layer, command_text):
                if not copy:
                    require_edit_success(
                        layer.changeGeometry(
                            source.id(),
                            remaining,
                        ),
                        self.tr("Не вдалося оновити multipart Source."),
                    )
                require_edit_success(
                    layer.addFeatures(new_features),
                    self.tr("Не вдалося створити вилучені частини."),
                )
            self.commit_indices.append(layer.undoStack().index())
            self.pending_indices = []
            self.pending_band.reset(layer.geometryType())
            layer.updateExtents()
            layer.triggerRepaint()
            self.canvas.refresh()
            if copy or len(all_parts) - len(selected) > 1:
                refreshed = layer.getFeature(source.id())
                match = LayerFeatureMatch(
                    layer=layer,
                    fid=source.id(),
                    point=QgsPointXY(),
                    geometry=refreshed.geometry(),
                )
                self._show_source(match)
                self.widget.update_state(source.id(), 0, copy)
            else:
                self.source_fid = None
                self.source_layer = None
                self.source_band.reset(layer.geometryType())
                self.widget.update_state(None, 0, copy)
        except (IndexError, RuntimeError, TypeError, ValueError) as error:
            self._show_warning(str(error))

    def _undo_last_tool_command(self) -> bool:
        layer = self.source_layer or self.current_layer()
        if not layer or not self.commit_indices:
            return False
        undo_stack = layer.undoStack()
        expected_index = self.commit_indices[-1]
        if undo_stack.index() != expected_index or expected_index <= 0:
            self.commit_indices = []
            return False
        command = undo_stack.command(expected_index - 1)
        if command is None or self.tr(self.COMMAND_TEXT) not in command.text():
            self.commit_indices = []
            return False
        undo_stack.undo()
        self.commit_indices.pop()
        layer.triggerRepaint()
        self.canvas.refresh()
        if self.source_fid is not None:
            feature = layer.getFeature(self.source_fid)
            if feature.isValid() and feature.geometry().isMultipart():
                self._show_source(
                    LayerFeatureMatch(layer, feature.id(), QgsPointXY(), feature.geometry())
                )
            else:
                self.source_fid = None
        return True

    def step_back(self) -> None:
        if self.pending_indices:
            self.pending_indices.pop()
            self._update_pending_band()
            self.widget.update_state(
                self.source_fid,
                len(self.pending_indices),
                self.ctrl_pressed,
            )
        elif self._undo_last_tool_command():
            return
        elif self.source_fid is not None:
            self.source_fid = None
            self.source_layer = None
            self.source_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.hover_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.update_state(None, 0, self.ctrl_pressed)
        else:
            self._deactivate_tool()

    def _escape(self) -> None:
        if self.pending_indices:
            self.pending_indices = []
            self._update_pending_band()
            self.widget.update_state(self.source_fid, 0, self.ctrl_pressed)
        elif self.source_fid is not None:
            self.source_fid = None
            self.source_layer = None
            self.source_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.widget.update_state(None, 0, self.ctrl_pressed)
        else:
            self._deactivate_tool()

    def _on_modifier_changed(self, name: str, pressed: bool) -> None:
        if name == "ctrl":
            self.ctrl_pressed = pressed
            self.widget.update_state(
                self.source_fid,
                len(self.pending_indices),
                self.ctrl_pressed,
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
            self.widget.update_state(self.source_fid, len(self.pending_indices), True)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        key_ctrl = int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021)))
        if int(event.key()) == key_ctrl:
            self.ctrl_pressed = False
            self.widget.update_state(self.source_fid, len(self.pending_indices), False)
        super().keyReleaseEvent(event)

    def _deactivate_tool(self) -> None:
        if self.iface and hasattr(self.iface, "actionPan") and self.iface.actionPan():
            self.iface.actionPan().trigger()
        elif self.canvas.mapTool() == self:
            self.canvas.unsetMapTool(self)

    def _show_warning(self, text: str) -> None:
        if self.iface and hasattr(self.iface, "messageBar"):
            self.iface.messageBar().pushWarning(
                self.tr("Extract Part"),
                self.tr(text),
            )

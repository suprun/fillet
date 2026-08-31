# -*- coding: utf-8 -*-
"""Interactive local edge matching tool for QGIS."""

import math
from typing import List, Optional, Set, Tuple

from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapMouseEvent, QgsMapToolEdit, QgsRubberBand
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor, QCursor

try:
    from ..core.geometry_engine import GeometryEngine
    from ..core.snapping_helper import LayerSegmentMatch, SnappingHelper
    from .gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy
    from .match_edge_canvas_widget import MatchEdgeCanvasWidget
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import LayerSegmentMatch, SnappingHelper
    from gui.gui_utils import checked_edit_command, require_edit_success, transform_geometry_copy
    from gui.match_edge_canvas_widget import MatchEdgeCanvasWidget


_LEFT_BUTTON = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RIGHT_BUTTON = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_SHIFT_MODIFIER = getattr(Qt.KeyboardModifier, "ShiftModifier", getattr(Qt, "ShiftModifier", 0x02000000))
_CTRL_MODIFIER = getattr(Qt.KeyboardModifier, "ControlModifier", getattr(Qt, "ControlModifier", 0x04000000))
_CROSS_CURSOR = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))

_SOURCE_COLOR = QColor(234, 88, 12, 220)
_TARGET_COLOR = QColor(79, 70, 229, 220)
_PREVIEW_STROKE = QColor(29, 78, 216, 220)
_PREVIEW_FILL = QColor(37, 99, 235, 60)
_ERROR_STROKE = QColor(220, 38, 38, 230)
_ERROR_FILL = QColor(239, 68, 68, 45)


class MatchEdgeMapTool(QgsMapToolEdit):
    """Locally make one selected source edge parallel or collinear to a target."""

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas, widget: MatchEdgeCanvasWidget, iface=None) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.widget = widget
        self.iface = iface
        self.source_layer: Optional[QgsVectorLayer] = None
        self.source_features: List[QgsFeature] = []
        self.source_feature: Optional[QgsFeature] = None
        self.source_edge: Optional[LayerSegmentMatch] = None
        self.target_edge: Optional[LayerSegmentMatch] = None
        self.hover_edge: Optional[LayerSegmentMatch] = None
        self.preview_geometry: Optional[QgsGeometry] = None
        self.preview_error: Optional[str] = None
        self.shift_pressed = False
        self.ctrl_pressed = False
        self.flip = False
        self.source_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.source_band.setColor(_SOURCE_COLOR)
        self.source_band.setWidth(3)
        self.target_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.target_band.setColor(_TARGET_COLOR)
        self.target_band.setWidth(3)
        self.preview_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.preview_band.setColor(_PREVIEW_FILL)
        self.preview_band.setStrokeColor(_PREVIEW_STROKE)
        self.preview_band.setFillColor(_PREVIEW_FILL)
        self.preview_band.setWidth(2)
        if _CROSS_CURSOR is not None:
            self.setCursor(QCursor(_CROSS_CURSOR))
        if hasattr(self, "setToolName"):
            self.setToolName(self.tr("CAD Суміщення ребра (Match Edge)"))
        self.widget.stepBackRequested.connect(self.step_back)
        self.widget.resetRequested.connect(self._escape)
        self.widget.commitRequested.connect(self.commit_match)
        self.widget.shortcutRequested.connect(self._on_shortcut)
        self.widget.modifierChanged.connect(self._on_modifier_changed)

    def _capture_source_selection(self) -> bool:
        layer = self.canvas.currentLayer()
        if (
            not isinstance(layer, QgsVectorLayer)
            or not layer.isEditable()
            or layer.geometryType()
            not in (
                QgsWkbTypes.GeometryType.LineGeometry,
                QgsWkbTypes.GeometryType.PolygonGeometry,
            )
        ):
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

    def _excluded_source_segment(self) -> Set[Tuple[str, int, int, int, int]]:
        if not self.source_edge:
            return set()
        return {
            (
                self.source_edge.layer.id(),
                self.source_edge.fid,
                self.source_edge.part_idx,
                self.source_edge.ring_idx,
                self.source_edge.segment_idx,
            )
        }

    @staticmethod
    def _has_native_curves(match: LayerSegmentMatch) -> bool:
        return GeometryEngine.has_curved_segments(match.geometry) or bool(
            QgsWkbTypes.isCurvedType(match.geometry.wkbType())
        )

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
        self.source_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.target_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)

    def reset_state(self) -> None:
        self.source_feature = None
        self.source_edge = None
        self.target_edge = None
        self.hover_edge = None
        self.preview_geometry = None
        self.preview_error = None
        self.flip = False
        self.cleanup()
        self.target_band.setColor(_TARGET_COLOR)
        self._set_preview_style(valid=True)
        self.widget.set_stage("source")
        self.widget.set_preview(
            0.0,
            0.0,
            0.0,
            self.ctrl_pressed,
            self.shift_pressed,
        )
        if self.canvas.mapTool() == self:
            self.widget.show_on_canvas()

    def canvasMoveEvent(self, event: QgsMapMouseEvent) -> None:
        map_point = self.toMapCoordinates(event.pos())
        if not self.source_edge:
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
                self.source_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
            return
        self.target_edge = None
        self.hover_edge = SnappingHelper.find_segment_across_visible_layers(
            self.canvas,
            map_point,
            excluded_segments=self._excluded_source_segment(),
        )
        if self.hover_edge:
            self.target_band.setToGeometry(
                QgsGeometry.fromPolylineXY([self.hover_edge.p1, self.hover_edge.p2]),
                None,
            )
            self._update_preview()
        else:
            self._clear_target_preview()

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:
        if event.button() == _RIGHT_BUTTON:
            self.step_back()
            return
        if event.button() != _LEFT_BUTTON:
            return
        if not self._capture_source_selection():
            self._show_warning(
                self.tr("Виберіть лінійні або полігональні об'єкти в редагованому шарі.")
            )
            return
        map_point = self.toMapCoordinates(event.pos())
        modifiers = event.modifiers()
        self.shift_pressed = bool(modifiers & _SHIFT_MODIFIER)
        self.ctrl_pressed = bool(modifiers & _CTRL_MODIFIER)
        if not self.source_edge:
            match = SnappingHelper.find_segment_across_visible_layers(
                self.canvas,
                map_point,
                included_features=self._source_keys(),
            )
            if not match:
                self._show_warning(
                    self.tr("Вкажіть пряме ребро одного з вибраних об'єктів.")
                )
                return
            if self._has_native_curves(match):
                self._show_warning(
                    self.tr("Криволінійна геометрія Source не підтримується.")
                )
                return
            feature = self.source_layer.getFeature(match.fid)
            if not feature.isValid():
                self._show_warning(self.tr("Не вдалося прочитати Source feature."))
                return
            self.source_feature = feature
            self.source_edge = match
            self.source_band.setToGeometry(
                QgsGeometry.fromPolylineXY([match.p1, match.p2]),
                None,
            )
            self.widget.set_stage("target")
            return
        match = SnappingHelper.find_segment_across_visible_layers(
            self.canvas,
            map_point,
            excluded_segments=self._excluded_source_segment(),
        )
        if not match:
            self._show_warning(
                self.tr("Вкажіть інше пряме ребро Target з видимого шару.")
            )
            return
        if self._has_native_curves(match):
            self._show_warning(
                self.tr("Криволінійна геометрія Target не підтримується.")
            )
            return
        self.target_edge = match
        self.hover_edge = match
        self.commit_match()

    def _current_target(self) -> Optional[LayerSegmentMatch]:
        return self.target_edge or self.hover_edge

    def _source_canvas_geometry(self) -> QgsGeometry:
        if not self.source_layer or not self.source_feature:
            raise ValueError("Source feature is not selected")
        feature = self.source_layer.getFeature(self.source_feature.id())
        if not feature.isValid():
            raise ValueError("Source feature is not available")
        return transform_geometry_copy(
            feature.geometry(),
            self.source_layer.crs(),
            self.canvas.mapSettings().destinationCrs(),
        )

    def _calculate_match(self) -> Tuple[QgsGeometry, float, float, float]:
        target = self._current_target()
        if not self.source_edge or not target:
            raise ValueError("Source and Target edges are required")
        if self._has_native_curves(target):
            raise ValueError("Native curved target geometries are not supported")

        canvas_geometry = self._source_canvas_geometry()
        result = GeometryEngine.match_segment_to_reference(
            canvas_geometry,
            self.source_edge.part_idx,
            self.source_edge.ring_idx,
            self.source_edge.segment_idx,
            target.p1,
            target.p2,
            collinear=not self.shift_pressed,
            flip=self.flip,
        )
        result_curve = GeometryEngine.get_curve_from_geometry(
            result,
            self.source_edge.part_idx,
            self.source_edge.ring_idx,
        )
        if result_curve is None:
            raise ValueError("Could not read the matched source edge")
        new_start = result_curve.pointN(self.source_edge.segment_idx)
        new_end = result_curve.pointN(self.source_edge.segment_idx + 1)
        old_dx = self.source_edge.p2.x() - self.source_edge.p1.x()
        old_dy = self.source_edge.p2.y() - self.source_edge.p1.y()
        new_dx = new_end.x() - new_start.x()
        new_dy = new_end.y() - new_start.y()
        angle = math.degrees(
            math.atan2(new_dy, new_dx) - math.atan2(old_dy, old_dx)
        )
        while angle <= -180.0:
            angle += 360.0
        while angle > 180.0:
            angle -= 360.0
        return (
            result,
            angle,
            math.hypot(old_dx, old_dy),
            math.hypot(new_dx, new_dy),
        )

    def _set_preview_style(self, valid: bool) -> None:
        self.preview_band.setStrokeColor(
            _PREVIEW_STROKE if valid else _ERROR_STROKE
        )
        self.preview_band.setFillColor(_PREVIEW_FILL if valid else _ERROR_FILL)
        self.target_band.setColor(_TARGET_COLOR if valid else _ERROR_STROKE)

    def _clear_target_preview(self) -> None:
        self.target_edge = None
        self.hover_edge = None
        self.preview_geometry = None
        self.preview_error = None
        self.target_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.preview_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self._set_preview_style(valid=True)
        self.widget.set_stage("target")

    def _update_preview(self) -> None:
        if not self.source_layer:
            return
        try:
            result, angle, old_length, new_length = self._calculate_match()
            self.preview_geometry = result
            self.preview_error = None
            self.preview_band.reset(self.source_layer.geometryType())
            self._set_preview_style(valid=True)
            self.preview_band.addGeometry(result, None)
            self.widget.set_stage("target")
            self.widget.set_preview(
                angle,
                old_length,
                new_length,
                self.ctrl_pressed,
                self.shift_pressed,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            self.preview_geometry = None
            self.preview_error = str(error)
            self.preview_band.reset(self.source_layer.geometryType())
            self._set_preview_style(valid=False)
            try:
                self.preview_band.addGeometry(self._source_canvas_geometry(), None)
            except (RuntimeError, TypeError, ValueError):
                pass
            self.widget.set_error(self.tr(str(error)))

    def commit_match(self) -> None:
        layer = self.source_layer
        if not layer or not layer.isEditable() or not self.source_feature:
            return
        try:
            canvas_geometry, _, _, _ = self._calculate_match()
            layer_geometry = transform_geometry_copy(
                canvas_geometry,
                self.canvas.mapSettings().destinationCrs(),
                layer.crs(),
            )
            if (
                layer_geometry.type() == QgsWkbTypes.GeometryType.PolygonGeometry
                and not layer_geometry.isGeosValid()
            ):
                raise ValueError("Matched source geometry is invalid")

            source_feature = layer.getFeature(self.source_feature.id())
            if not source_feature.isValid():
                raise ValueError("Source feature is not available")
            with checked_edit_command(layer, self.tr("CAD Match Edge")):
                if self.ctrl_pressed:
                    copied = QgsFeature(source_feature)
                    copied.setGeometry(layer_geometry)
                    require_edit_success(
                        layer.addFeatures([copied]),
                        self.tr("Не вдалося додати локально виправлену копію."),
                    )
                    if copied.id() >= 0:
                        layer.selectByIds([copied.id()])
                else:
                    require_edit_success(
                        layer.changeGeometry(source_feature.id(), layer_geometry),
                        self.tr("Не вдалося локально виправити ребро."),
                    )
            layer.updateExtents()
            layer.triggerRepaint()
            self.canvas.refresh()
            self._capture_source_selection()
            self.reset_state()
        except (RuntimeError, TypeError, ValueError) as error:
            self._show_warning(str(error))

    def step_back(self) -> None:
        if self.source_edge:
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
        key_escape = int(getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000)))
        key_backspace = int(getattr(Qt.Key, "Key_Backspace", getattr(Qt, "Key_Backspace", 0x01000003)))
        key_f = int(getattr(Qt.Key, "Key_F", getattr(Qt, "Key_F", 0x46)))
        key_shift = int(getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020)))
        key_ctrl = int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021)))
        if key in (key_escape, key_backspace):
            self.step_back()
            event.accept()
            return
        if key == key_f:
            self.flip = not self.flip
            self._update_preview()
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
                self.tr("Match Edge"),
                self.tr(text),
            )

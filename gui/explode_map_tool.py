# -*- coding: utf-8 -*-
"""
Map tool for interactive and batch CAD Explode Line operations.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

from typing import List, Optional

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
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
    from .explode_canvas_widget import ExplodeCanvasWidget
    from .gui_utils import checked_edit_command, require_edit_success
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from core.snapping_helper import SnappingHelper
    from gui.explode_canvas_widget import ExplodeCanvasWidget
    from gui.gui_utils import checked_edit_command, require_edit_success

_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_LeftButton = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RightButton = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_Key_Escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
_Key_Space = getattr(Qt.Key, "Key_Space", getattr(Qt, "Key_Space", 0x20))
_Key_Return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
_Key_Enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))


class ExplodeLineMapTool(QgsMapToolEdit):
    """Interactive map tool for splitting polylines into individual 2-point segments or multipart."""

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas, widget: Optional[ExplodeCanvasWidget] = None, iface=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.widget = widget or ExplodeCanvasWidget(self.canvas)

        self.hovered_feature_id: Optional[int] = None
        self.hovered_geometry: Optional[QgsGeometry] = None

        # Rubberbands
        # 1. Feature highlight line
        self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.preview_rubberband.setColor(QColor(234, 88, 12, 230))  # Orange/Amber
        self.preview_rubberband.setWidth(3)

        # 2. Node markers showing where segments will be split
        self.nodes_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
        self.nodes_rubberband.setIcon(QgsRubberBand.IconType.ICON_CROSS)
        self.nodes_rubberband.setIconSize(8)
        self.nodes_rubberband.setWidth(2)
        self.nodes_rubberband.setColor(QColor(37, 99, 235, 240))  # Blue

        self.snap_indicator = QgsSnapIndicator(self.canvas)

        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        self.widget.commitRequested.connect(self.explode_selected_features)
        self.widget.resetRequested.connect(self._clear_preview)

    def current_vector_layer(self) -> Optional[QgsVectorLayer]:
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
            self.widget.update_layer_capabilities(layer)
            try:
                layer.selectionChanged.connect(self._on_layer_selection_changed)
            except (TypeError, RuntimeError):
                pass
        self._clear_preview()
        self.widget.show_on_canvas()

    def deactivate(self):
        layer = self.current_vector_layer()
        if layer:
            try:
                layer.selectionChanged.disconnect(self._on_layer_selection_changed)
            except (TypeError, RuntimeError):
                pass
        if self.widget:
            self.widget.save_settings()
            self.widget.hide()
        self._clear_preview()
        super().deactivate()

    def cleanup(self):
        self.deactivate()
        if self.widget:
            try:
                self.widget.commitRequested.disconnect(self.explode_selected_features)
            except (TypeError, RuntimeError):
                pass
            try:
                self.widget.resetRequested.disconnect(self._clear_preview)
            except (TypeError, RuntimeError):
                pass
        for rb in (self.preview_rubberband, self.nodes_rubberband):
            if rb:
                rb.reset()
        if self.snap_indicator:
            self.snap_indicator.setVisible(False)

    def _on_layer_selection_changed(self):
        layer = self.current_vector_layer()
        if self.widget and layer:
            self.widget.update_layer_capabilities(layer)

    def _clear_preview(self):
        self.hovered_feature_id = None
        self.hovered_geometry = None
        self.preview_rubberband.reset()
        self.nodes_rubberband.reset()
        if self.snap_indicator:
            self.snap_indicator.setVisible(False)

    def canvasMoveEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            self._clear_preview()
            return

        map_point = event.mapPoint()
        match = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)

        if match and match.fid is not None:
            self.hovered_feature_id = match.fid
            self.hovered_geometry = match.geometry
            self._show_feature_preview(layer, match.geometry)
        else:
            self._clear_preview()

    def _show_feature_preview(self, layer: QgsVectorLayer, geom: QgsGeometry):
        """Displays rubberband highlight and vertex markers for candidate line to explode."""
        self.preview_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.preview_rubberband.setColor(QColor(234, 88, 12, 230))
        self.preview_rubberband.setWidth(3)
        self.preview_rubberband.setToGeometry(geom, layer)
        self.preview_rubberband.show()

        self.nodes_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        self.nodes_rubberband.setIcon(QgsRubberBand.IconType.ICON_CROSS)
        self.nodes_rubberband.setIconSize(8)
        self.nodes_rubberband.setWidth(2)
        self.nodes_rubberband.setColor(QColor(37, 99, 235, 240))

        # Add vertex markers
        abstract_geom = geom.constGet()
        if abstract_geom:
            for pt in geom.vertices():
                pt_map = self.toMapCoordinates(layer, QgsPointXY(pt.x(), pt.y()))
                self.nodes_rubberband.addPoint(pt_map, False)
        self.nodes_rubberband.show()

    def _show_message(self, title: str, text: str, level=None, duration: int = 4):
        """Displays notification message in the QGIS messageBar strip."""
        if level is None:
            level = getattr(Qgis.MessageLevel, "Info", getattr(Qgis, "Info", 0))
        if self.iface:
            try:
                self.iface.messageBar().pushMessage(title, text, level, duration)
            except Exception:
                return

    def canvasPressEvent(self, event: QgsMapMouseEvent):
        layer = self.current_vector_layer()
        if not layer:
            return

        if event.button() == _LeftButton:
            map_point = event.mapPoint()
            match = SnappingHelper.find_segment_at_position(layer, self.canvas, map_point)

            if match and match.fid is not None:
                feat = layer.getFeature(match.fid)
                if feat.isValid():
                    if GeometryEngine.has_curved_segments(feat.geometry()):
                        self._show_curved_geometry_warning()
                        return
                    as_multipart = self.widget.is_save_as_multipart if self.widget else False
                    if not GeometryEngine.can_explode_line(feat.geometry(), as_multipart=as_multipart):
                        self._clear_preview()
                        self._show_message(
                            self.tr("CAD Explode Line"),
                            self.tr("Об'єкт вже є простим відрізком (2 точки) і не може бути розділений"),
                            getattr(Qgis.MessageLevel, "Info", getattr(Qgis, "Info", 0)),
                            duration=4,
                        )
                        return
                    self.explode_features(layer, [feat])
        elif event.button() == _RightButton:
            self._clear_preview()

    def keyPressEvent(self, event):
        key = event.key()
        if key == _Key_Escape:
            self._clear_preview()
        elif key == _Key_Space:
            if self.widget:
                self.widget.toggle_multipart()
        elif key in (_Key_Return, _Key_Enter):
            self.explode_selected_features()
        else:
            super().keyPressEvent(event)

    def explode_selected_features(self):
        """Batch explodes all currently selected line features in the active layer."""
        layer = self.current_vector_layer()
        if not layer:
            return

        selected_features = list(layer.selectedFeatures())
        if not selected_features:
            return

        if any(
            GeometryEngine.has_curved_segments(feature.geometry())
            for feature in selected_features
        ):
            self._show_curved_geometry_warning()
            return

        as_multipart = self.widget.is_save_as_multipart if self.widget else False
        splittable_features = [
            f for f in selected_features
            if GeometryEngine.can_explode_line(f.geometry(), as_multipart=as_multipart)
        ]

        if not splittable_features:
            self._show_message(
                self.tr("CAD Explode Line"),
                self.tr("Усі виділені об'єкти вже є простими відрізками (2 точки) і не можуть бути розділені"),
                getattr(Qgis.MessageLevel, "Info", getattr(Qgis, "Info", 0)),
                duration=4,
            )
            return

        self.explode_features(layer, splittable_features, total_selected_count=len(selected_features))

    def explode_features(self, layer: QgsVectorLayer, features: List[QgsFeature], total_selected_count: Optional[int] = None):
        """Splits given features into segments (either individual features or multipart)."""
        if not layer or not features:
            return

        as_multipart = self.widget.is_save_as_multipart if self.widget else False
        if any(
            GeometryEngine.has_curved_segments(feature.geometry())
            for feature in features
        ):
            self._show_curved_geometry_warning()
            return
        total_created_segments = 0
        new_features = []

        try:
            command_name = (
                self.tr("Розбиття ліній на складові частини (multipart)")
                if as_multipart
                else self.tr("Розбиття ліній на окремі відрізки")
            )
            with checked_edit_command(layer, command_name):
                for feat in features:
                    geom = feat.geometry()
                    if not geom or geom.isEmpty():
                        continue

                    exploded_geoms = GeometryEngine.explode_line(
                        geom,
                        as_multipart=as_multipart,
                    )
                    if not exploded_geoms:
                        raise RuntimeError("exploded geometry is empty")

                    if as_multipart:
                        multi_geom = exploded_geoms[0]
                        require_edit_success(
                            layer.changeGeometry(feat.id(), multi_geom),
                            "changeGeometry",
                        )
                        total_created_segments += (
                            multi_geom.constGet().numGeometries()
                            if multi_geom.constGet()
                            else 1
                        )
                    else:
                        total_created_segments += len(exploded_geoms)
                        require_edit_success(
                            layer.changeGeometry(feat.id(), exploded_geoms[0]),
                            "changeGeometry",
                        )

                        for seg_geom in exploded_geoms[1:]:
                            new_feat = QgsFeature(layer.fields())
                            new_feat.setAttributes(feat.attributes())
                            new_feat.setGeometry(seg_geom)
                            new_features.append(new_feat)

                for new_feature in new_features:
                    require_edit_success(
                        layer.addFeature(new_feature),
                        "addFeature",
                    )

            layer.triggerRepaint()
            self._clear_preview()

            # Message bar notification
            if total_selected_count is not None and total_selected_count > len(features):
                skipped_count = total_selected_count - len(features)
                msg = self.tr("Успішно розбито {} об'єктів на {} відрізків (пропущено {} одинарних відрізків)").format(
                    len(features), total_created_segments, skipped_count
                )
            else:
                msg = self.tr("Успішно розбито {} об'єктів на {} відрізків").format(
                    len(features), total_created_segments
                )
            self._show_message(
                self.tr("CAD Explode Line"),
                msg,
                getattr(Qgis.MessageLevel, "Info", getattr(Qgis, "Info", 0)),
                duration=3,
            )
        except (RuntimeError, TypeError) as err:
            self._show_message(
                self.tr("CAD Explode Line"),
                str(err),
                getattr(Qgis.MessageLevel, "Warning", getattr(Qgis, "Warning", 1)),
                duration=5,
            )

    def _show_curved_geometry_warning(self):
        self._show_message(
            self.tr("CAD Explode Line"),
            self.tr("Ця операція недоступна для геометрій із кривими сегментами."),
            getattr(Qgis.MessageLevel, "Warning", getattr(Qgis, "Warning", 1)),
            duration=5,
        )

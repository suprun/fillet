# -*- coding: utf-8 -*-
"""
Interactive CAD Copy Features in an Array along a Reference Line Map Tool.
Backport and CAD module for QGIS 3.16 to 3.44 (and compatible up to 4.x).
"""

import math
import os
from typing import List, Optional, Tuple

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointLocator,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSettings,
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
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor, QCursor, QKeyEvent

# Safe cross-version Qt constants
_CrossCursor = getattr(Qt.CursorShape, "CrossCursor", getattr(Qt, "CrossCursor", None))
_DashLine = getattr(Qt.PenStyle, "DashLine", getattr(Qt, "DashLine", 2))
_DotLine = getattr(Qt.PenStyle, "DotLine", getattr(Qt, "DotLine", 3))
_LeftButton = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
_RightButton = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
_Key_Escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
_Key_Return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
_Key_Enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))

try:
    from .array_canvas_widget import ArrayCanvasWidget, ArrayMode
    from .gui_utils import checked_edit_command, confirm_features_in_canvas_extent, require_edit_success
except (ImportError, ValueError):
    from gui.array_canvas_widget import ArrayCanvasWidget, ArrayMode
    from gui.gui_utils import checked_edit_command, confirm_features_in_canvas_extent, require_edit_success


class CADArrayMapTool(QgsMapToolEdit):
    """
    Interactive Map Tool to copy vector features in an array along a line.
    Provides 3 modes:
      1. FeatureCount: Fixed count, spacing dynamically computed from line length.
      2. FeatureSpacing: Fixed spacing, count dynamically computed from line length.
      3. FeatureCountAndSpacing: Fixed count and fixed spacing along reference direction.
    """

    STATE_SET_START = 1
    STATE_SET_END = 2

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(
        self,
        canvas: QgsMapCanvas,
        widget: Optional[ArrayCanvasWidget] = None,
        iface: Optional[QgisInterface] = None,
    ):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.state = self.STATE_SET_START

        if hasattr(self, "setToolName"):
            self.setToolName(self.tr("CAD Масив об'єктів (Feature Array)"))
        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        self.userInputWidget = widget or ArrayCanvasWidget(self.canvas)

        # Load persisted settings
        settings = QgsSettings()
        self._mode = ArrayMode(settings.value("FilletPlugin/ArrayMode", ArrayMode.FeatureCount.value, type=int))
        self._featureCount = max(1, settings.value("FilletPlugin/ArrayCount", 3, type=int))
        self._featureSpacing = max(0.0001, settings.value("FilletPlugin/ArraySpacing", 1.0, type=float))

        self.startPointMapCoords = QgsPointXY()
        self.endPointMapCoords = QgsPointXY()

        self.featureList: List[QgsFeature] = []
        self.featureLayer: Optional[QgsVectorLayer] = None

        # Rubberbands & Indicators
        self.baseline_rubberband: Optional[QgsRubberBand] = None
        self.preview_rubberband: Optional[QgsRubberBand] = None
        self.snap_indicator: Optional[QgsSnapIndicator] = None

        self._init_visuals()

        # Wire widget signals
        if self.userInputWidget is not None:
            self.userInputWidget.modeChanged.connect(self.setMode)
            self.userInputWidget.featureCountChanged.connect(self.setFeatureCount)
            self.userInputWidget.featureSpacingChanged.connect(self.setFeatureSpacing)
            self.userInputWidget.commitRequested.connect(self.commit_array)
            self.userInputWidget.resetRequested.connect(self.reset_state)

    def _init_visuals(self) -> None:
        if self.canvas is not None:
            try:
                self.snap_indicator = QgsSnapIndicator(self.canvas)
            except Exception:
                self.snap_indicator = None

            try:
                # 1. Baseline Ray Rubberband
                self.baseline_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
                self.baseline_rubberband.setWidth(2)
                if _DashLine is not None:
                    self.baseline_rubberband.setLineStyle(_DashLine)
                self.baseline_rubberband.setColor(QColor(234, 88, 12, 220))  # Orange/Amber

                # 2. Geometry Preview RubberBand
                self.preview_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
                self.preview_rubberband.setWidth(2)
                if _DotLine is not None:
                    self.preview_rubberband.setLineStyle(_DotLine)
                self.preview_rubberband.setColor(QColor(37, 99, 235, 230))  # Blue
                self.preview_rubberband.setFillColor(QColor(59, 130, 246, 60))
            except Exception:
                self.baseline_rubberband = None
                self.preview_rubberband = None

    def activate(self) -> None:
        """Activate the map tool, load settings and show HUD."""
        super().activate()
        self.reset_state()

        # Refresh settings
        settings = QgsSettings()
        self._mode = ArrayMode(settings.value("FilletPlugin/ArrayMode", self._mode.value, type=int))
        self._featureCount = max(1, settings.value("FilletPlugin/ArrayCount", self._featureCount, type=int))
        self._featureSpacing = max(0.0001, settings.value("FilletPlugin/ArraySpacing", self._featureSpacing, type=float))

        if self.userInputWidget is not None:
            self.userInputWidget.setMode(self._mode)
            self.userInputWidget.setFeatureCount(self._featureCount)
            self.userInputWidget.setFeatureSpacing(self._featureSpacing)
            self.userInputWidget.set_step(ArrayCanvasWidget.STEP_START)
            self.userInputWidget.show_on_canvas()

    def deactivate(self) -> None:
        """Deactivate the map tool, save settings and clean preview."""
        # Save settings
        settings = QgsSettings()
        settings.setValue("FilletPlugin/ArrayMode", int(self._mode.value))
        settings.setValue("FilletPlugin/ArrayCount", int(self._featureCount))
        settings.setValue("FilletPlugin/ArraySpacing", float(self._featureSpacing))

        if self.userInputWidget is not None:
            self.userInputWidget.hide()
            self.userInputWidget.save_settings()

        self.reset_state()
        super().deactivate()

    def cleanup(self) -> None:
        """Complete teardown on plugin unload."""
        self.deactivate()
        self._clear_visuals()
        self.userInputWidget = None
        self.snap_indicator = None
        self.baseline_rubberband = None
        self.preview_rubberband = None

    def reset_state(self) -> None:
        """Resets the state machine back to Step 1: Start Point."""
        self.state = self.STATE_SET_START
        self.startPointMapCoords = QgsPointXY()
        self.endPointMapCoords = QgsPointXY()
        self.featureList.clear()
        self.featureLayer = None
        self._clear_visuals()
        if self.userInputWidget is not None:
            self.userInputWidget.set_step(ArrayCanvasWidget.STEP_START)

    def _clear_visuals(self) -> None:
        if self.baseline_rubberband is not None:
            self.baseline_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        if self.preview_rubberband is not None:
            self.preview_rubberband.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        if self.snap_indicator is not None:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def snap_point(self, e: QgsMapMouseEvent) -> Tuple[QgsPointXY, Optional[QgsPointLocator.Match]]:
        """Snaps mouse event to active snapping grid / layers."""
        if self.canvas is None:
            return e.mapPoint(), None
        try:
            match = self.canvas.snappingUtils().snapToMap(e.mapPoint())
            if match.isValid():
                return match.point(), match
        except Exception:
            return e.mapPoint(), None
        return e.mapPoint(), None

    def canvasPressEvent(self, e: Optional[QgsMapMouseEvent]) -> None:
        """Handles map click interactions."""
        if e is None or self.canvas is None:
            return

        if e.button() == _RightButton:
            # Right-click cancels or steps back
            if self.state == self.STATE_SET_END:
                self.reset_state()
            return

        if e.button() != _LeftButton:
            return

        point, match = self.snap_point(e)

        if self.state == self.STATE_SET_START:
            # Step 1: Resolve layer & features to copy
            layer = self.canvas.currentLayer()
            if not isinstance(layer, QgsVectorLayer) or not layer.isEditable() or not layer.isSpatial():
                return

            self.featureLayer = layer
            selected_features = list(layer.selectedFeatures())

            if len(selected_features) > 0:
                self.featureList = selected_features
            else:
                # Identify single feature under click / snap
                feature_found = None
                if match and match.isValid() and match.layer() == layer and match.featureId() >= 0:
                    feat = layer.getFeature(match.featureId())
                    if feat.isValid() and not feat.geometry().isEmpty():
                        feature_found = feat

                if feature_found is None:
                    # Bounding box search around click point
                    search_radius = self.canvas.mapUnitsPerPixel() * 8.0
                    rect = QgsRectangle(
                        point.x() - search_radius,
                        point.y() - search_radius,
                        point.x() + search_radius,
                        point.y() + search_radius,
                    )
                    layer_rect = self.toLayerCoordinates(layer, rect)
                    req = QgsFeatureRequest().setFilterRect(layer_rect)
                    for f in layer.getFeatures(req):
                        if f.geometry() and not f.geometry().isEmpty():
                            feature_found = f
                            break

                if feature_found is None:
                    return
                self.featureList = [feature_found]

            # Verify if any feature to copy is outside canvas extent (matching Rotate & Mirror tools)
            if self.canvas and not confirm_features_in_canvas_extent(
                self.canvas, layer, self.featureList, self.tr("CAD Масив об'єктів")
            ):
                self.reset_state()
                return

            self.startPointMapCoords = point
            self.state = self.STATE_SET_END
            if self.userInputWidget is not None:
                self.userInputWidget.set_step(ArrayCanvasWidget.STEP_END)

        elif self.state == self.STATE_SET_END:
            # Step 2: Finalize reference vector and commit
            self.endPointMapCoords = point
            self.commit_array()

    def canvasMoveEvent(self, e: Optional[QgsMapMouseEvent]) -> None:
        """Live feedback of reference line, duplicated geometries, and hints."""
        if e is None or self.canvas is None:
            return

        point, match = self.snap_point(e)

        if self.snap_indicator is not None:
            if match and match.isValid():
                self.snap_indicator.setMatch(match)
            else:
                self.snap_indicator.setMatch(QgsPointLocator.Match())

        if self.state == self.STATE_SET_END and not self.startPointMapCoords.isEmpty():
            self.endPointMapCoords = point
            self.update_visuals()

    def update_visuals(self) -> None:
        """Updates baseline line rubberband and duplicated feature geometries."""
        if self.canvas is None or self.startPointMapCoords.isEmpty() or self.endPointMapCoords.isEmpty():
            return

        # 1. Update baseline rubberband
        if self.baseline_rubberband is not None:
            self.baseline_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self.baseline_rubberband.addPoint(self.startPointMapCoords, False)
            self.baseline_rubberband.addPoint(self.endPointMapCoords, True)
            self.baseline_rubberband.show()

        # 2. Update widget calculated values
        mode = self.mode()
        if self.userInputWidget is not None:
            if mode == ArrayMode.FeatureCount:
                self.userInputWidget.set_calculated_spacing(self.featureSpacing())
            elif mode == ArrayMode.FeatureSpacing:
                self.userInputWidget.set_calculated_count(self.featureCount())

        # 3. Update preview rubberband
        self.updateRubberBand()

    def updateRubberBand(self) -> None:
        """Updates the rubberband preview with all translated duplicate features."""
        count = self.featureCount()
        if (
            self.featureLayer is None
            or len(self.featureList) == 0
            or self.startPointMapCoords.isEmpty()
            or self.endPointMapCoords.isEmpty()
            or count <= 0
            or self.canvas is None
        ):
            if self.preview_rubberband is not None:
                self.preview_rubberband.reset()
            return

        start_layer_pt = self.toLayerCoordinates(self.featureLayer, self.startPointMapCoords)
        first_layer_pt = self.toLayerCoordinates(self.featureLayer, self.firstFeatureMapPoint())

        dx = first_layer_pt.x() - start_layer_pt.x()
        dy = first_layer_pt.y() - start_layer_pt.y()

        geom_type = self.featureLayer.geometryType()
        if self.preview_rubberband is not None:
            self.preview_rubberband.reset(geom_type)

            for i in range(1, count + 1):
                for feat in self.featureList:
                    if feat.geometry() and not feat.geometry().isEmpty():
                        geom = QgsGeometry(feat.geometry())
                        geom.translate(dx * i, dy * i)
                        self.preview_rubberband.addGeometry(geom, self.featureLayer)

            self.preview_rubberband.show()

    def firstFeatureMapPoint(self) -> QgsPointXY:
        """Returns the map coordinate for the first duplicated feature along the reference line."""
        if self.startPointMapCoords.isEmpty() or self.endPointMapCoords.isEmpty():
            return QgsPointXY()

        spacing = self.featureSpacing()
        if spacing <= 0:
            return QgsPointXY()

        dx = self.endPointMapCoords.x() - self.startPointMapCoords.x()
        dy = self.endPointMapCoords.y() - self.startPointMapCoords.y()
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            return QgsPointXY()

        factor = spacing / length
        return QgsPointXY(self.startPointMapCoords.x() + dx * factor, self.startPointMapCoords.y() + dy * factor)

    def keyPressEvent(self, e: Optional[QKeyEvent]) -> None:
        """Cancel on Escape key, Commit on Enter."""
        if e is None or e.isAutoRepeat():
            return

        if e.key() == _Key_Escape:
            self.reset_state()
        elif e.key() in (_Key_Return, _Key_Enter):
            if self.state == self.STATE_SET_END:
                self.commit_array()

    def commit_array(self) -> None:
        """Creates duplicates and commits edit command."""
        count = self.featureCount()
        if (
            self.featureLayer is None
            or not self.featureLayer.isEditable()
            or len(self.featureList) == 0
            or self.startPointMapCoords.isEmpty()
            or self.endPointMapCoords.isEmpty()
            or count <= 0
        ):
            self.reset_state()
            return

        # Verification of features outside canvas extent
        if self.canvas and not confirm_features_in_canvas_extent(
            self.canvas, self.featureLayer, self.featureList, self.tr("CAD Масив об'єктів")
        ):
            self.reset_state()
            return

        start_layer_pt = self.toLayerCoordinates(self.featureLayer, self.startPointMapCoords)
        first_layer_pt = self.toLayerCoordinates(self.featureLayer, self.firstFeatureMapPoint())

        dx = first_layer_pt.x() - start_layer_pt.x()
        dy = first_layer_pt.y() - start_layer_pt.y()

        new_features = []
        for i in range(1, count + 1):
            for feat in self.featureList:
                if feat.geometry() and not feat.geometry().isEmpty():
                    geom = QgsGeometry(feat.geometry())
                    geom.translate(dx * i, dy * i)
                    new_feat = QgsFeature(feat)
                    new_feat.setGeometry(geom)
                    new_features.append(new_feat)

        try:
            with checked_edit_command(self.featureLayer, self.tr("CAD Масив об'єктів")):
                require_edit_success(
                    self.featureLayer.addFeatures(new_features),
                    self.tr("Не вдалося додати елементи масиву."),
                )
        except (RuntimeError, TypeError):
            return

        if self.canvas is not None:
            self.canvas.refresh()

        self.reset_state()

    def mode(self) -> ArrayMode:
        """Returns the current array mode."""
        return self._mode

    def setMode(self, mode: ArrayMode, propagate_to_widget: bool = False) -> None:
        """Sets the array mode."""
        self._mode = mode if isinstance(mode, ArrayMode) else ArrayMode(mode)
        if propagate_to_widget and self.userInputWidget is not None:
            self.userInputWidget.blockSignals(True)
            self.userInputWidget.setMode(self._mode)
            self.userInputWidget.blockSignals(False)
        self.update_visuals()

    def featureCount(self) -> int:
        """Returns the count of new feature copies according to the active mode."""
        mode = self.mode()
        if mode in (ArrayMode.FeatureCount, ArrayMode.FeatureCountAndSpacing):
            return self._featureCount

        if mode == ArrayMode.FeatureSpacing:
            if self.startPointMapCoords.isEmpty() or self.endPointMapCoords.isEmpty():
                return 0
            dx = self.endPointMapCoords.x() - self.startPointMapCoords.x()
            dy = self.endPointMapCoords.y() - self.startPointMapCoords.y()
            length = math.hypot(dx, dy)
            spacing = self.featureSpacing()
            if spacing <= 0:
                return 0
            return int(length / spacing)

        return 0

    def setFeatureCount(self, count: int, propagate_to_widget: bool = False) -> None:
        """Sets the feature count."""
        val = max(1, int(count))
        self._featureCount = val
        if propagate_to_widget and self.userInputWidget is not None:
            self.userInputWidget.blockSignals(True)
            self.userInputWidget.setFeatureCount(val)
            self.userInputWidget.blockSignals(False)
        self.update_visuals()

    def featureSpacing(self) -> float:
        """Returns the spacing between feature copies according to the active mode."""
        mode = self.mode()
        if mode in (ArrayMode.FeatureSpacing, ArrayMode.FeatureCountAndSpacing):
            return self._featureSpacing

        if mode == ArrayMode.FeatureCount:
            if self.startPointMapCoords.isEmpty() or self.endPointMapCoords.isEmpty():
                return 0.0
            dx = self.endPointMapCoords.x() - self.startPointMapCoords.x()
            dy = self.endPointMapCoords.y() - self.startPointMapCoords.y()
            length = math.hypot(dx, dy)
            count = self.featureCount()
            if count <= 0:
                return 0.0
            return length / count

        return 0.0

    def setFeatureSpacing(self, spacing: float, propagate_to_widget: bool = False) -> None:
        """Sets the feature spacing."""
        val = max(0.0001, float(spacing))
        self._featureSpacing = val
        if propagate_to_widget and self.userInputWidget is not None:
            self.userInputWidget.blockSignals(True)
            self.userInputWidget.setFeatureSpacing(val)
            self.userInputWidget.blockSignals(False)
        self.update_visuals()

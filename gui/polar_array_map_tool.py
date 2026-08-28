# -*- coding: utf-8 -*-
"""
Interactive CAD Polar (Circular) Feature Array Map Tool.
Provides interactive circular array duplication with live canvas HUD,
rubberband preview, snapping, angle step/fill angle control and feature rotation.
Compatible with QGIS 3.16 to 4.x.
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
_Key_Tab = getattr(Qt.Key, "Key_Tab", getattr(Qt, "Key_Tab", 0x01000001))
_Key_Backspace = getattr(Qt.Key, "Key_Backspace", getattr(Qt, "Key_Backspace", 0x01000003))

try:
    from ..core.geometry_engine import GeometryEngine
    from .polar_array_canvas_widget import PolarArrayCanvasWidget, PolarArrayMode
    from .gui_utils import (
        checked_edit_command,
        confirm_features_in_canvas_extent,
        require_edit_success,
        transform_geometry_copy,
    )
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from gui.polar_array_canvas_widget import PolarArrayCanvasWidget, PolarArrayMode
    from gui.gui_utils import (
        checked_edit_command,
        confirm_features_in_canvas_extent,
        require_edit_success,
        transform_geometry_copy,
    )


class CADPolarArrayMapTool(QgsMapToolEdit):
    """
    Interactive Map Tool to copy vector features in a circular (polar) array around a center pivot point.
    """

    STATE_SELECT_FEATURE = 1
    STATE_SET_CENTER = 2
    STATE_SET_BASE_RAY = 3
    STATE_SET_ANGLE = 4

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(
        self,
        canvas: QgsMapCanvas,
        widget: Optional[PolarArrayCanvasWidget] = None,
        iface: Optional[QgisInterface] = None,
    ):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.state = self.STATE_SELECT_FEATURE

        if hasattr(self, "setToolName"):
            self.setToolName(self.tr("CAD Полярний масив (Polar Array)"))
        if _CrossCursor is not None:
            self.setCursor(QCursor(_CrossCursor))

        self.widget = widget or PolarArrayCanvasWidget(self.canvas)

        self.center_point: Optional[QgsPointXY] = None
        self.ref_point: Optional[QgsPointXY] = None
        self.ref_angle_rad: float = 0.0
        self._last_mouse_angle_rad: Optional[float] = None
        self._accumulated_fill_angle_deg: float = 360.0

        self.featureList: List[QgsFeature] = []
        self.featureLayer: Optional[QgsVectorLayer] = None

        # Rubberbands
        self.center_rubberband: Optional[QgsRubberBand] = None
        self.baseline_rubberband: Optional[QgsRubberBand] = None
        self.radius_ray_rubberband: Optional[QgsRubberBand] = None
        self.arc_rubberband: Optional[QgsRubberBand] = None
        self.preview_rubberbands: List[QgsRubberBand] = []
        self.snap_indicator: Optional[QgsSnapIndicator] = None
        self._preselected_features: bool = False

        self._init_visuals()

        if self.widget is not None:
            self.widget.featureCountChanged.connect(self._on_widget_param_changed)
            self.widget.stepAngleChanged.connect(self._on_widget_param_changed)
            self.widget.fillAngleChanged.connect(self._on_widget_param_changed)
            self.widget.rotateFeaturesChanged.connect(self._on_widget_param_changed)
            self.widget.fillAngleLockToggled.connect(self._on_widget_param_changed)
            self.widget.stepAngleLockToggled.connect(self._on_widget_param_changed)
            self.widget.commitRequested.connect(self.commit_array)
            self.widget.resetRequested.connect(self.step_back)

    def _init_visuals(self) -> None:
        if self.canvas is not None:
            try:
                self.snap_indicator = QgsSnapIndicator(self.canvas)
            except Exception:
                self.snap_indicator = None

            self.center_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PointGeometry)
            self.center_rubberband.setIcon(QgsRubberBand.ICON_CROSS)
            self.center_rubberband.setIconSize(12)
            self.center_rubberband.setColor(QColor(234, 88, 12))  # Amber/orange
            self.center_rubberband.setWidth(2)

            # Baseline 0° ray (indigo dashed line)
            self.baseline_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
            self.baseline_rubberband.setColor(QColor(79, 70, 229, 200))  # Indigo
            self.baseline_rubberband.setWidth(2)
            if hasattr(self.baseline_rubberband, "setLineStyle") and _DashLine is not None:
                self.baseline_rubberband.setLineStyle(_DashLine)

            # Radius ray line (center to mouse)
            self.radius_ray_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
            self.radius_ray_rubberband.setColor(QColor(234, 88, 12, 220))
            self.radius_ray_rubberband.setWidth(2)

            # Arc / Circle guide
            self.arc_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.LineGeometry)
            self.arc_rubberband.setColor(QColor(234, 88, 12, 180))
            self.arc_rubberband.setWidth(1)
            if hasattr(self.arc_rubberband, "setLineStyle") and _DotLine is not None:
                self.arc_rubberband.setLineStyle(_DotLine)

            # Selected feature highlight rubberband (amber/orange outline)
            self.selection_rubberband = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
            self.selection_rubberband.setColor(QColor(255, 170, 0, 40))
            self.selection_rubberband.setStrokeColor(QColor(255, 140, 0, 220))
            self.selection_rubberband.setWidth(2)

    def _get_preview_rubberband(self, index: int, geom_type: QgsWkbTypes.GeometryType) -> QgsRubberBand:
        while len(self.preview_rubberbands) <= index:
            rb = QgsRubberBand(self.canvas, geom_type)
            rb.setColor(QColor(37, 99, 235, 75))
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
        geoms = []
        for feat in self.featureList:
            g = QgsGeometry(feat.geometry())
            if not g.isEmpty() and not g.isNull():
                try:
                    g = transform_geometry_copy(g, layer_crs, canvas_crs)
                except Exception:
                    self.selection_rubberband.reset(
                        QgsWkbTypes.GeometryType.PolygonGeometry
                    )
                    return
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
        """Step back in 4-step CAD state machine, or cleanly deactivate tool at initial step."""
        if self.state == self.STATE_SET_ANGLE:
            self.state = self.STATE_SET_BASE_RAY
            self.ref_point = None
            self._last_mouse_angle_rad = None
            for rb in self.preview_rubberbands:
                rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            if self.radius_ray_rubberband:
                self.radius_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
            if self.arc_rubberband:
                self.arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
            if self.widget:
                self.widget.set_step(PolarArrayCanvasWidget.STEP_BASE_RAY)
        elif self.state == self.STATE_SET_BASE_RAY:
            self.state = self.STATE_SET_CENTER
            self.center_point = None
            self.ref_point = None
            self.ref_angle_rad = 0.0
            self._last_mouse_angle_rad = None
            self._reset_rubberbands()
            if self.widget:
                self.widget.set_step(PolarArrayCanvasWidget.STEP_CENTER)
        elif self.state == self.STATE_SET_CENTER:
            if self._preselected_features:
                self._deactivate_tool()
            else:
                self.state = self.STATE_SELECT_FEATURE
                self.featureList = []
                self.center_point = None
                self.ref_point = None
                self.ref_angle_rad = 0.0
                self._last_mouse_angle_rad = None
                self._reset_rubberbands()
                if self.widget:
                    self.widget.set_step(PolarArrayCanvasWidget.STEP_SELECT)
        elif self.state == self.STATE_SELECT_FEATURE:
            self._deactivate_tool()

    def _deactivate_tool(self) -> None:
        """Cleanly deactivates tool and returns canvas to default map tool."""
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
                return

    def reset_state(self) -> None:
        layer = self.currentVectorLayer()
        self.center_point = None
        self.ref_point = None
        self.ref_angle_rad = 0.0
        self._last_mouse_angle_rad = None
        self._accumulated_fill_angle_deg = self.widget.fill_angle if self.widget else 360.0

        if layer and layer.isEditable() and layer.selectedFeatureCount() > 0:
            self.featureLayer = layer
            self.featureList = list(layer.selectedFeatures())
            self.state = self.STATE_SET_CENTER
            if self.widget:
                self.widget.set_step(PolarArrayCanvasWidget.STEP_CENTER)
        else:
            self.featureList = []
            self.featureLayer = layer
            self.state = self.STATE_SELECT_FEATURE
            if self.widget:
                self.widget.set_step(PolarArrayCanvasWidget.STEP_SELECT)

        self._reset_rubberbands()

    def _reset_rubberbands(self) -> None:
        if self.center_rubberband:
            self.center_rubberband.reset(QgsWkbTypes.GeometryType.PointGeometry)
        if self.baseline_rubberband:
            self.baseline_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        if self.radius_ray_rubberband:
            self.radius_ray_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        if self.arc_rubberband:
            self.arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)
        for rb in self.preview_rubberbands:
            rb.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        if self.snap_indicator:
            self.snap_indicator.setMatch(QgsPointLocator.Match())

    def _snap_point(self, e: QgsMapMouseEvent) -> QgsPointXY:
        if self.canvas and hasattr(self.canvas, "snappingUtils"):
            match = self.canvas.snappingUtils().snapToMap(e.pos())
            if self.snap_indicator:
                self.snap_indicator.setMatch(match)
            if match.isValid():
                return match.point()
        return e.mapPoint()

    def _get_target_features(self, layer: QgsVectorLayer, point: QgsPointXY) -> List[QgsFeature]:
        if not layer or not layer.isEditable():
            return []
        if layer.selectedFeatureCount() > 0:
            return list(layer.selectedFeatures())

        tol = 10.0
        if self.canvas:
            mupp = self.canvas.mapUnitsPerPixel()
            tol = mupp * 12.0
        search_rect = QgsRectangle(point.x() - tol, point.y() - tol, point.x() + tol, point.y() + tol)
        canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
        layer_crs = layer.crs()
        if canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs:
            try:
                transform = QgsCoordinateTransform(
                    canvas_crs,
                    layer_crs,
                    QgsProject.instance(),
                )
                search_rect = transform.transformBoundingBox(search_rect)
            except Exception as error:
                if self.iface and hasattr(self.iface, "messageBar"):
                    self.iface.messageBar().pushWarning(
                        self.tr("Помилка"),
                        str(error),
                    )
                return []

        req = layer.getFeatures(QgsFeatureRequest().setFilterRect(search_rect))
        pt_geom = QgsGeometry.fromPointXY(point)
        found = []
        for feat in req:
            g = feat.geometry()
            if not g.isEmpty():
                found.append(feat)
                break
        return found

    def canvasPressEvent(self, e: QgsMapMouseEvent) -> None:
        button = e.button()
        if button == _RightButton:
            self.step_back()
            return
        if button != _LeftButton:
            return

        point = self._snap_point(e)
        layer = self.currentVectorLayer()
        if not layer or not layer.isEditable():
            return

        if self.state == self.STATE_SELECT_FEATURE:
            feats = self._get_target_features(layer, point)
            if not feats:
                return
            self.featureLayer = layer
            self.featureList = feats
            self._update_selection_highlight()

            if self.canvas and not confirm_features_in_canvas_extent(
                self.canvas, layer, self.featureList, self.tr("CAD Полярний масив")
            ):
                self.reset_state()
                return

            self.state = self.STATE_SET_CENTER
            if self.widget:
                self.widget.set_step(PolarArrayCanvasWidget.STEP_CENTER)
            return

        elif self.state == self.STATE_SET_CENTER:
            if not self.featureList:
                feats = self._get_target_features(layer, point)
                if not feats:
                    return
                self.featureLayer = layer
                self.featureList = feats
                self._update_selection_highlight()

            if self.canvas and not confirm_features_in_canvas_extent(
                self.canvas, layer, self.featureList, self.tr("CAD Полярний масив")
            ):
                self.reset_state()
                return

            self.center_point = point
            self.state = self.STATE_SET_BASE_RAY
            if self.widget:
                self.widget.set_step(PolarArrayCanvasWidget.STEP_BASE_RAY)

            # Center marker (cross)
            if self.center_rubberband:
                self.center_rubberband.setToGeometry(QgsGeometry.fromPointXY(point), None)

        elif self.state == self.STATE_SET_BASE_RAY:
            if self.center_point is None:
                return
            dx = point.x() - self.center_point.x()
            dy = point.y() - self.center_point.y()
            if math.hypot(dx, dy) < 1e-6:
                self.ref_angle_rad = 0.0
                self.ref_point = QgsPointXY(self.center_point.x() + 10.0, self.center_point.y())
            else:
                self.ref_angle_rad = math.atan2(dy, dx)
                self.ref_point = point

            self.state = self.STATE_SET_ANGLE
            if self.widget:
                self.widget.set_step(PolarArrayCanvasWidget.STEP_ANGLE)

            self._last_mouse_angle_rad = self.ref_angle_rad
            self._accumulated_fill_angle_deg = 0.0
            self._update_preview(point)

        elif self.state == self.STATE_SET_ANGLE:
            self.commit_array()

    def canvasMoveEvent(self, e: QgsMapMouseEvent) -> None:
        point = self._snap_point(e)

        if self.state == self.STATE_SET_BASE_RAY and self.center_point is not None:
            dx = point.x() - self.center_point.x()
            dy = point.y() - self.center_point.y()
            if math.hypot(dx, dy) > 1e-4:
                if self.baseline_rubberband:
                    self.baseline_rubberband.setToGeometry(
                        QgsGeometry.fromPolylineXY([self.center_point, point]), None
                    )
            else:
                if self.baseline_rubberband:
                    self.baseline_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)

        elif self.state == self.STATE_SET_ANGLE and self.center_point is not None:
            dx = point.x() - self.center_point.x()
            dy = point.y() - self.center_point.y()
            radius = math.hypot(dx, dy)
            if radius > 1e-6:
                cur_rad = math.atan2(dy, dx)
                if self.widget and not self.widget.is_fill_angle_locked:
                    if self._last_mouse_angle_rad is not None:
                        d_rad = (cur_rad - self._last_mouse_angle_rad + math.pi) % (2.0 * math.pi) - math.pi
                        new_accum = self._accumulated_fill_angle_deg + math.degrees(d_rad)
                    else:
                        d_rad = (cur_rad - self.ref_angle_rad + math.pi) % (2.0 * math.pi) - math.pi
                        new_accum = math.degrees(d_rad)

                    # Clamp accumulation strictly to [-360.0, 360.0] and align _last_mouse_angle_rad without phase drift
                    if new_accum >= 360.0:
                        self._accumulated_fill_angle_deg = 360.0
                        self._last_mouse_angle_rad = self.ref_angle_rad
                    elif new_accum <= -360.0:
                        self._accumulated_fill_angle_deg = -360.0
                        self._last_mouse_angle_rad = self.ref_angle_rad
                    else:
                        self._accumulated_fill_angle_deg = new_accum
                        self._last_mouse_angle_rad = cur_rad

                    # Smooth magnetic snap only when very close to 360° or -360° (>= 358.5°)
                    if abs(self._accumulated_fill_angle_deg) >= 358.5:
                        effective_fill = 360.0 if self._accumulated_fill_angle_deg >= 0 else -360.0
                    else:
                        effective_fill = round(self._accumulated_fill_angle_deg, 1)

                    mode = self.widget.mode
                    if mode == PolarArrayMode.CountAndFillAngle:
                        self.widget.set_calculated_fill_angle(effective_fill)
                        fill = self.widget.fill_angle
                        count = self.widget.feature_count
                        step = fill / count if count > 0 else 0.0
                        self.widget.set_calculated_step_angle(abs(step))
                    elif mode == PolarArrayMode.StepAndFillAngle:
                        self.widget.set_calculated_fill_angle(effective_fill)
                        fill = self.widget.fill_angle
                        step = self.widget.step_angle
                        calc_count = max(1, int(round(abs(fill) / max(0.001, step))))
                        self.widget.set_calculated_count(calc_count)
                    elif mode == PolarArrayMode.CountAndStep:
                        pass

            self._update_preview(point)

    def _on_widget_param_changed(self, *args) -> None:
        if self.state == self.STATE_SET_ANGLE and self.center_point is not None:
            self._update_preview(None)

    def _update_preview(self, mouse_point: Optional[QgsPointXY]) -> None:
        if not self.center_point or not self.featureList or not self.featureLayer:
            return

        layer = self.featureLayer
        canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
        layer_crs = layer.crs()

        count = self.widget.feature_count if self.widget else 4
        fill_angle = self.widget.fill_angle if self.widget else 360.0
        step_angle = self.widget.step_angle if (self.widget and self.widget.chk_step.isChecked()) else None
        rotate_features = self.widget.rotate_features if self.widget else True

        all_preview_geoms: List[QgsGeometry] = []
        try:
            for feat in self.featureList:
                orig_geom = feat.geometry()
                if orig_geom.isEmpty() or orig_geom.isNull():
                    continue
                canvas_geom = transform_geometry_copy(orig_geom, layer_crs, canvas_crs)
                copies = GeometryEngine.create_polar_array_geometries(
                    geom=canvas_geom,
                    center=self.center_point,
                    count=count,
                    fill_angle_deg=fill_angle,
                    rotate_features=rotate_features,
                    include_original=False,
                    step_angle_deg=step_angle,
                )
                all_preview_geoms.extend(copies)
        except (RuntimeError, TypeError):
            for rubberband in self.preview_rubberbands:
                rubberband.reset(layer.geometryType())
            return

        geom_type = layer.geometryType()
        for i, geom_c in enumerate(all_preview_geoms):
            rb = self._get_preview_rubberband(i, geom_type)
            rb.setToGeometry(geom_c, None)

        for j in range(len(all_preview_geoms), len(self.preview_rubberbands)):
            self.preview_rubberbands[j].reset(geom_type)

        # Visual rays, baseline, and arc
        if mouse_point is not None:
            radius = math.hypot(mouse_point.x() - self.center_point.x(), mouse_point.y() - self.center_point.y())
        else:
            radius = 10.0
        if radius < 1e-4:
            radius = 10.0

        # Base ray end point at angle self.ref_angle_rad
        base_pt = QgsPointXY(
            self.center_point.x() + radius * math.cos(self.ref_angle_rad),
            self.center_point.y() + radius * math.sin(self.ref_angle_rad),
        )

        # Target angle ray end point at angle (self.ref_angle_rad + math.radians(fill_angle))
        target_angle_rad = self.ref_angle_rad + math.radians(fill_angle)
        cur_pt = QgsPointXY(
            self.center_point.x() + radius * math.cos(target_angle_rad),
            self.center_point.y() + radius * math.sin(target_angle_rad),
        )

        # 0° Baseline Ray (indigo dashed line from center through ref_angle_rad)
        if self.baseline_rubberband:
            self.baseline_rubberband.setToGeometry(
                QgsGeometry.fromPolylineXY([self.center_point, base_pt]), None
            )

        # Current angle ray line (center to end of sweep angle)
        if self.radius_ray_rubberband:
            self.radius_ray_rubberband.setToGeometry(
                QgsGeometry.fromPolylineXY([self.center_point, cur_pt]), None
            )

        # Guide circle/arc
        if self.arc_rubberband:
            if abs(fill_angle) > 1e-3:
                num_pts = max(16, int(abs(fill_angle) / 5.0))
                arc_pts: List[QgsPointXY] = []
                step_rad = math.radians(fill_angle) / float(num_pts)
                for i in range(num_pts + 1):
                    a = self.ref_angle_rad + i * step_rad
                    arc_pts.append(QgsPointXY(
                        self.center_point.x() + radius * math.cos(a),
                        self.center_point.y() + radius * math.sin(a),
                    ))
                if len(arc_pts) >= 2:
                    self.arc_rubberband.setToGeometry(QgsGeometry.fromPolylineXY(arc_pts), None)
            else:
                self.arc_rubberband.reset(QgsWkbTypes.GeometryType.LineGeometry)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        key_int = int(key)
        key_escape = int(getattr(Qt.Key, "Key_Escape", 0x01000000))
        key_return = int(getattr(Qt.Key, "Key_Return", 0x01000004))
        key_enter = int(getattr(Qt.Key, "Key_Enter", 0x01000005))
        key_tab = int(getattr(Qt.Key, "Key_Tab", 0x01000001))

        # If user types numbers, redirect focus to HUD spinbox
        if event.text() and (event.text().isdigit() or event.text() in ".-+," or key_int == 0x01000003):
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
                    self.widget.focus_count_input()
                    focused = QApplication.focusWidget()
                    if focused:
                        QApplication.sendEvent(focused, event)
                    event.accept()
                    return

        if key_int in (0x01000000, key_escape):
            self.step_back()
            event.accept()
            return
        elif key_int in (0x01000004, 0x01000005, key_return, key_enter):
            if self.state == self.STATE_SET_ANGLE:
                self.commit_array()
                event.accept()
                return
        elif key_int in (0x01000001, key_tab):
            if self.widget:
                from qgis.PyQt.QtWidgets import QApplication
                focused = QApplication.focusWidget()
                if focused == self.widget.spin_count:
                    self.widget.focus_step_input()
                    event.accept()
                    return
                elif focused == self.widget.spin_step:
                    self.widget.focus_fill_angle_input()
                    event.accept()
                    return
                else:
                    self.widget.focus_count_input()
                    event.accept()
                    return

        super().keyPressEvent(event)

    def commit_array(self) -> None:
        """Applies the polar feature array in a single undoable transaction."""
        layer = self.featureLayer or self.currentVectorLayer()
        if not layer or not layer.isEditable() or not self.center_point or not self.featureList:
            self.reset_state()
            return

        canvas_crs = self.canvas.mapSettings().destinationCrs() if self.canvas else QgsProject.instance().crs()
        layer_crs = layer.crs()

        count = self.widget.feature_count if self.widget else 4
        fill_angle = self.widget.fill_angle if self.widget else 360.0
        step_angle = self.widget.step_angle if (self.widget and self.widget.chk_step.isChecked()) else None
        rotate_features = self.widget.rotate_features if self.widget else True

        try:
            new_features: List[QgsFeature] = []
            for feat in self.featureList:
                orig_geom = feat.geometry()
                if orig_geom.isEmpty() or orig_geom.isNull():
                    continue
                canvas_geom = transform_geometry_copy(orig_geom, layer_crs, canvas_crs)
                copies = GeometryEngine.create_polar_array_geometries(
                    geom=canvas_geom,
                    center=self.center_point,
                    count=count,
                    fill_angle_deg=fill_angle,
                    rotate_features=rotate_features,
                    include_original=False,
                    step_angle_deg=step_angle,
                )
                for canvas_geometry in copies:
                    geom = transform_geometry_copy(canvas_geometry, canvas_crs, layer_crs)
                    new_feat = QgsFeature(feat)
                    new_feat.setGeometry(geom)
                    new_features.append(new_feat)

            if not new_features:
                return

            with checked_edit_command(layer, self.tr("CAD Polar Array Feature(s)")):
                require_edit_success(
                    layer.addFeatures(new_features),
                    self.tr("Не вдалося додати елементи кругового масиву."),
                )

            new_fids = [feature.id() for feature in new_features if feature.id() != 0]
            if new_fids:
                layer.selectByIds(new_fids)
        except (RuntimeError, TypeError) as err:
            if self.iface:
                self.iface.messageBar().pushWarning(self.tr("Помилка"), str(err))
            return

        self.reset_state()

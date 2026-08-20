# -*- coding: utf-8 -*-
"""
Main plugin class for Fillet & Chamfer Tool.
Compatible with QGIS 3.16 to 3.99 (Qt5).
"""

import os
from typing import Optional

from qgis.core import (
    Qgis,
    QgsGeometry,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QDockWidget

try:
    from .core.geometry_engine import GeometryEngine
    from .gui.canvas_widget import FilletCanvasWidget
    from .gui.map_tool import FilletMapTool
    from .gui.settings_widget import FilletSettingsWidget
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from gui.canvas_widget import FilletCanvasWidget
    from gui.map_tool import FilletMapTool
    from gui.settings_widget import FilletSettingsWidget


class FilletPlugin:
    """QGIS Plugin for Fillet and Chamfer editing operations."""

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)

        self.action: Optional[QAction] = None
        self.map_tool: Optional[FilletMapTool] = None
        self.canvas_widget: Optional[FilletCanvasWidget] = None
        self.dock_widget: Optional[QDockWidget] = None
        self.settings_widget: Optional[FilletSettingsWidget] = None

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def initGui(self):
        # 0. Clean up any leftover duplicate dock widgets from previous unloads/reloads
        main_win = self.iface.mainWindow()
        if main_win:
            for old_dock in main_win.findChildren(QDockWidget, "FilletChamferDockWidget"):
                self.iface.removeDockWidget(old_dock)
                old_dock.setParent(None)
                old_dock.deleteLater()

        # 1. Create on-canvas CAD HUD widget
        self.canvas_widget = FilletCanvasWidget(self.canvas)
        self.canvas_widget.hide()

        # 2. Create settings widget for batch operations dock
        self.settings_widget = FilletSettingsWidget()
        self.dock_widget = QDockWidget(self.tr("Fillet / Chamfer (Пакетна обробка)"), self.iface.mainWindow())
        self.dock_widget.setObjectName("FilletChamferDockWidget")
        self.dock_widget.setWidget(self.settings_widget)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
        self.dock_widget.hide()

        # Connect batch apply
        self.settings_widget.applyToSelectedRequested.connect(self.apply_to_selected_features)

        # 3. Create map tool with on-canvas widget
        self.map_tool = FilletMapTool(self.canvas, self.canvas_widget)

        # 4. Create action
        icon_path = os.path.join(self.plugin_dir, "resources", "icons", "fillet.svg")
        self.action = QAction(
            QIcon(icon_path),
            self.tr("Інструмент Fillet / Chamfer"),
            self.iface.mainWindow(),
        )
        self.action.setCheckable(True)
        self.action.setObjectName("actionFilletChamfer")
        self.action.setToolTip(self.tr("Інструмент для створення скруглень (Fillet) та фасок (Chamfer)"))
        self.action.triggered.connect(self.toggle_tool)

        # Add to Advanced Digitizing toolbar and Vector menu
        if self.iface.advancedDigitizeToolBar():
            self.iface.advancedDigitizeToolBar().addAction(self.action)
        else:
            self.iface.addVectorToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.action)

        # Track layer changes
        self.iface.currentLayerChanged.connect(self.update_action_state)
        self.canvas.mapToolSet.connect(self.on_map_tool_changed)

        self.update_action_state()

    def unload(self):
        # 1. Disconnect global signals
        try:
            self.iface.currentLayerChanged.disconnect(self.update_action_state)
        except Exception:
            pass
        try:
            self.canvas.mapToolSet.disconnect(self.on_map_tool_changed)
        except Exception:
            pass

        # 2. Clean up action
        if self.action:
            try:
                self.action.triggered.disconnect(self.toggle_tool)
            except Exception:
                pass
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.action)
            self.iface.removeVectorToolBarIcon(self.action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.action)
            self.action.setParent(None)
            self.action.deleteLater()
            self.action = None

        # 3. Clean up map tool
        if self.map_tool:
            if self.canvas.mapTool() == self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)
            if hasattr(self.map_tool, "cleanup"):
                self.map_tool.cleanup()
            else:
                self.map_tool.deactivate()
            self.map_tool.deleteLater()
            self.map_tool = None

        # 4. Clean up canvas widget
        if self.canvas_widget:
            try:
                self.canvas.removeEventFilter(self.canvas_widget)
            except Exception:
                pass
            self.canvas_widget.hide()
            self.canvas_widget.setParent(None)
            self.canvas_widget.deleteLater()
            self.canvas_widget = None

        # 5. Clean up settings widget and dock widget
        if self.settings_widget:
            try:
                self.settings_widget.applyToSelectedRequested.disconnect(self.apply_to_selected_features)
            except Exception:
                pass
            self.settings_widget.setParent(None)
            self.settings_widget.deleteLater()
            self.settings_widget = None

        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.setParent(None)
            self.dock_widget.deleteLater()
            self.dock_widget = None

        # Purge any remaining duplicate dock widgets
        main_win = self.iface.mainWindow()
        if main_win:
            for old_dock in main_win.findChildren(QDockWidget, "FilletChamferDockWidget"):
                self.iface.removeDockWidget(old_dock)
                old_dock.setParent(None)
                old_dock.deleteLater()

    def toggle_tool(self, checked: bool):
        if checked:
            if self.map_tool:
                self.canvas.setMapTool(self.map_tool)
        else:
            if self.canvas.mapTool() == self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)

    def on_map_tool_changed(self, tool):
        if self.action:
            is_active = tool == self.map_tool
            self.action.setChecked(is_active)
            if not is_active and self.canvas_widget:
                self.canvas_widget.hide()

    def update_action_state(self):
        layer = self.canvas.currentLayer()
        enabled = False
        if isinstance(layer, QgsVectorLayer):
            if layer.geometryType() in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                enabled = True

        if self.action:
            self.action.setEnabled(enabled)

    def apply_to_selected_features(self):
        """Batch apply fillet or chamfer to all corners of selected features."""
        layer = self.canvas.currentLayer()
        if not isinstance(layer, QgsVectorLayer) or not layer.isEditable():
            self.iface.messageBar().pushWarning(
                self.tr("Увага"),
                self.tr("Активний шар повинен бути векторним і перебувати в режимі редагування."),
            )
            return

        selected_fids = layer.selectedFeatureIds()
        if not selected_fids:
            self.iface.messageBar().pushInfo(
                self.tr("Інфо"),
                self.tr("Немає виділених об'єктів для обробки."),
            )
            return

        mode = self.settings_widget.mode
        radius = self.settings_widget.radius
        segments = self.settings_widget.segments_count
        d1 = self.settings_widget.distance1
        d2 = self.settings_widget.distance2

        layer.beginEditCommand(
            self.tr("Пакетне скруглення") if mode == FilletSettingsWidget.MODE_FILLET else self.tr("Пакетна фаска")
        )

        modified_count = 0
        for fid in selected_fids:
            feat = layer.getFeature(fid)
            geom = feat.geometry()
            if geom.isEmpty() or geom.isNull():
                continue

            new_geom = self._batch_process_geometry(geom, mode, radius, segments, d1, d2)
            if new_geom and not new_geom.isEmpty():
                layer.changeGeometry(fid, new_geom)
                modified_count += 1

        layer.endEditCommand()
        self.canvas.refresh()
        self.iface.messageBar().pushSuccess(
            self.tr("Успіх"),
            self.tr("Оброблено {} об'єкт(ів).").format(modified_count),
        )

    def _batch_process_geometry(
        self,
        geom: QgsGeometry,
        mode: str,
        radius: float,
        segments: int,
        d1: float,
        d2: float,
    ) -> Optional[QgsGeometry]:
        """Applies fillet/chamfer to all vertices of a geometry."""
        curr_geom = QgsGeometry(geom)
        v_count = curr_geom.constGet().numPoints() if curr_geom.constGet() else 0
        if v_count < 3:
            return None

        for v_idx in range(v_count - 1, -1, -1):
            if mode == FilletSettingsWidget.MODE_FILLET:
                res = GeometryEngine.apply_fillet_to_geometry(
                    curr_geom, part_idx=0, ring_idx=0, vertex_idx=v_idx, radius=radius, segments_count=segments
                )
            else:
                res = GeometryEngine.apply_chamfer_to_geometry(
                    curr_geom, part_idx=0, ring_idx=0, vertex_idx=v_idx, dist1=d1, dist2=d2
                )
            if res and not res.isEmpty():
                curr_geom = res

        return curr_geom

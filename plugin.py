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
    QgsSettings,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator, Qt
from qgis.PyQt.QtGui import QIcon
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QDockWidget

try:
    from .core.geometry_engine import GeometryEngine
    from .gui.canvas_widget import FilletCanvasWidget
    from .gui.map_tool import FilletMapTool
    from .gui.restore_map_tool import RestoreMapTool
    from .gui.settings_widget import FilletSettingsWidget
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from gui.canvas_widget import FilletCanvasWidget
    from gui.map_tool import FilletMapTool
    from gui.restore_map_tool import RestoreMapTool
    from gui.settings_widget import FilletSettingsWidget


class FilletPlugin:
    """QGIS Plugin for Fillet and Chamfer editing operations."""

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)

        # Initialize translation
        self.translator: Optional[QTranslator] = None
        self._init_translator()

        self.action: Optional[QAction] = None
        self.restore_action: Optional[QAction] = None
        self.batch_action: Optional[QAction] = None
        self.map_tool: Optional[FilletMapTool] = None
        self.restore_map_tool: Optional[RestoreMapTool] = None
        self.canvas_widget: Optional[FilletCanvasWidget] = None
        self.dock_widget: Optional[QDockWidget] = None
        self.settings_widget: Optional[FilletSettingsWidget] = None
        self._tracked_layer: Optional[QgsVectorLayer] = None

    @staticmethod
    def is_qgis_4() -> bool:
        if hasattr(Qgis, "QGIS_VERSION_INT"):
            return Qgis.QGIS_VERSION_INT >= 40000
        if hasattr(Qgis, "versionInt"):
            return Qgis.versionInt() >= 40000
        return False

    def _init_translator(self):
        locale_name = QgsSettings().value("locale/userLocale", "")
        if not locale_name:
            locale_name = QLocale().name()

        candidates = [locale_name, locale_name.replace("-", "_"), locale_name[:2]]
        i18n_dir = os.path.join(self.plugin_dir, "i18n")

        for cand in candidates:
            qm_path = os.path.join(i18n_dir, f"fillet_{cand}.qm")
            if os.path.exists(qm_path):
                translator = QTranslator()
                if translator.load(qm_path):
                    self.translator = translator
                    QCoreApplication.installTranslator(self.translator)
                    break

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

        # 1. Create settings widget for batch operations dock
        self.settings_widget = FilletSettingsWidget()
        self.dock_widget = QDockWidget(self.tr("Fillet / Chamfer (Пакетна обробка)"), self.iface.mainWindow())
        self.dock_widget.setObjectName("FilletChamferDockWidget")
        self.dock_widget.setWidget(self.settings_widget)
        right_dock = getattr(Qt.DockWidgetArea, "RightDockWidgetArea", getattr(Qt, "RightDockWidgetArea", None))
        self.iface.addDockWidget(right_dock, self.dock_widget)
        self.dock_widget.hide()

        # Connect batch apply
        self.settings_widget.applyToSelectedRequested.connect(self.apply_to_selected_features)

        # 2. Create batch toggle action (for QGIS 3.x and QGIS 4.x)
        batch_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionChamferFilletBatch.svg")
        self.batch_action = QAction(
            QIcon(batch_icon_path),
            self.tr("Fillet / Chamfer (Пакетна обробка)"),
            self.iface.mainWindow(),
        )
        self.batch_action.setCheckable(True)
        self.batch_action.setObjectName("actionFilletChamferBatch")
        self.batch_action.setToolTip(self.tr("Панель пакетного скруглення (Fillet) та фаски (Chamfer) для виділених об'єктів"))
        self.batch_action.triggered.connect(self.toggle_batch_panel)
        self.dock_widget.visibilityChanged.connect(self.on_dock_visibility_changed)

        # 3. Create interactive Corner Restore (Unfillet/Unchamfer) CAD Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.restore_map_tool = RestoreMapTool(self.canvas)

        restore_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionRestoreCorners.svg")
        self.restore_action = QAction(
            QIcon(restore_icon_path),
            self.tr("Відновлення кутів (Unfillet / Unchamfer)"),
            self.iface.mainWindow(),
        )
        self.restore_action.setCheckable(True)
        self.restore_action.setObjectName("actionRestoreCorners")
        self.restore_action.setToolTip(self.tr("Інструмент відновлення гострих кутів (видалення скруглень та фасок)"))
        self.restore_action.triggered.connect(self.toggle_restore_tool)

        adv_tb = self.iface.advancedDigitizeToolBar()

        # 4. Create interactive Fillet / Chamfer MapTool ONLY in QGIS 3.x (native in QGIS 4.0+)
        if not self.is_qgis_4():
            self.canvas_widget = FilletCanvasWidget(self.canvas)
            self.canvas_widget.hide()
            self.map_tool = FilletMapTool(self.canvas, self.canvas_widget)

            icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionChamferFillet.svg")
            self.action = QAction(
                QIcon(icon_path),
                self.tr("Інструмент Fillet / Chamfer"),
                self.iface.mainWindow(),
            )
            self.action.setCheckable(True)
            self.action.setObjectName("actionFilletChamfer")
            self.action.setToolTip(self.tr("Інструмент для створення скруглень (Fillet) та фасок (Chamfer)"))
            self.action.triggered.connect(self.toggle_tool)

            if adv_tb:
                actions = adv_tb.actions()
                if len(actions) >= 13:
                    adv_tb.insertAction(actions[12], self.action)
                else:
                    adv_tb.addAction(self.action)
            else:
                self.iface.addVectorToolBarIcon(self.action)
            self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.action)

        # 5. Insert restore_action and batch_action on toolbar
        if adv_tb:
            anchor_act = self.action
            if not anchor_act:
                # In QGIS 4.x, locate native fillet action as anchor
                for act in adv_tb.actions():
                    name_lower = act.objectName().lower()
                    if "chamfer" in name_lower or "fillet" in name_lower:
                        anchor_act = act
                        break

            if anchor_act:
                actions_now = adv_tb.actions()
                try:
                    idx = actions_now.index(anchor_act)
                    if idx + 1 < len(actions_now):
                        adv_tb.insertAction(actions_now[idx + 1], self.restore_action)
                    else:
                        adv_tb.addAction(self.restore_action)
                except ValueError:
                    adv_tb.addAction(self.restore_action)
            else:
                adv_tb.addAction(self.restore_action)

            # Insert batch_action after restore_action
            actions_now = adv_tb.actions()
            try:
                idx = actions_now.index(self.restore_action)
                if idx + 1 < len(actions_now):
                    adv_tb.insertAction(actions_now[idx + 1], self.batch_action)
                else:
                    adv_tb.addAction(self.batch_action)
            except ValueError:
                adv_tb.addAction(self.batch_action)
        else:
            self.iface.addVectorToolBarIcon(self.restore_action)
            self.iface.addVectorToolBarIcon(self.batch_action)

        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.restore_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.batch_action)

        if self.canvas:
            self.canvas.mapToolSet.connect(self.on_map_tool_changed)

        # Track layer changes
        self.iface.currentLayerChanged.connect(self._on_current_layer_changed)

        self.update_action_state()

    def unload(self):
        # 1. Disconnect global signals & tracked layer signals
        try:
            self.iface.currentLayerChanged.disconnect(self._on_current_layer_changed)
        except (TypeError, RuntimeError):
            pass  # nosec B110

        if self._tracked_layer is not None:
            try:
                self._tracked_layer.editingStarted.disconnect(self.update_action_state)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            try:
                self._tracked_layer.editingStopped.disconnect(self.update_action_state)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self._tracked_layer = None

        if not self.is_qgis_4():
            try:
                self.canvas.mapToolSet.disconnect(self.on_map_tool_changed)
            except (TypeError, RuntimeError):
                pass  # nosec B110

        # 2. Clean up interactive fillet action
        if self.action:
            try:
                self.action.triggered.disconnect(self.toggle_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.action)
            self.iface.removeVectorToolBarIcon(self.action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.action)
            self.action.setParent(None)
            self.action.deleteLater()
            self.action = None

        # 3. Clean up restore action
        if self.restore_action:
            try:
                self.restore_action.triggered.disconnect(self.toggle_restore_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.restore_action)
            self.iface.removeVectorToolBarIcon(self.restore_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.restore_action)
            self.restore_action.setParent(None)
            self.restore_action.deleteLater()
            self.restore_action = None

        # 4. Clean up batch action
        if self.batch_action:
            try:
                self.batch_action.triggered.disconnect(self.toggle_batch_panel)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.batch_action)
            self.iface.removeVectorToolBarIcon(self.batch_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.batch_action)
            self.batch_action.setParent(None)
            self.batch_action.deleteLater()
            self.batch_action = None

        # 5. Clean up map tools
        if self.map_tool:
            if self.canvas and self.canvas.mapTool() == self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)
            if hasattr(self.map_tool, "cleanup"):
                self.map_tool.cleanup()
            else:
                self.map_tool.deactivate()
            self.map_tool.deleteLater()
            self.map_tool = None

        if self.restore_map_tool:
            if self.canvas and self.canvas.mapTool() == self.restore_map_tool:
                self.canvas.unsetMapTool(self.restore_map_tool)
            if hasattr(self.restore_map_tool, "cleanup"):
                self.restore_map_tool.cleanup()
            else:
                self.restore_map_tool.deactivate()
            self.restore_map_tool.deleteLater()
            self.restore_map_tool = None

        # 6. Clean up canvas widgets
        if self.canvas_widget:
            try:
                self.canvas.removeEventFilter(self.canvas_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.canvas_widget.hide()
            self.canvas_widget.setParent(None)
            self.canvas_widget.deleteLater()
            self.canvas_widget = None

        # 7. Clean up settings widget and dock widget
        if self.settings_widget:
            try:
                self.settings_widget.applyToSelectedRequested.disconnect(self.apply_to_selected_features)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.settings_widget.setParent(None)
            self.settings_widget.deleteLater()
            self.settings_widget = None

        if self.dock_widget:
            try:
                self.dock_widget.visibilityChanged.disconnect(self.on_dock_visibility_changed)
            except (TypeError, RuntimeError):
                pass  # nosec B110
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

        # 8. Remove translator
        if self.translator:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def toggle_tool(self, checked: bool):
        if checked:
            if self.map_tool:
                self.canvas.setMapTool(self.map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)

    def toggle_restore_tool(self, checked: bool):
        if checked:
            if self.restore_map_tool:
                self.canvas.setMapTool(self.restore_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.restore_map_tool:
                self.canvas.unsetMapTool(self.restore_map_tool)

    def toggle_batch_panel(self, checked: bool):
        if self.dock_widget:
            self.dock_widget.setVisible(checked)

    def on_dock_visibility_changed(self, visible: bool):
        if self.batch_action and self.batch_action.isChecked() != visible:
            self.batch_action.setChecked(visible)

    def on_map_tool_changed(self, tool):
        if self.action:
            is_active = tool == self.map_tool
            self.action.setChecked(is_active)
            if not is_active and self.canvas_widget:
                self.canvas_widget.hide()

        if self.restore_action:
            is_restore_active = tool == self.restore_map_tool
            self.restore_action.setChecked(is_restore_active)

    def _on_current_layer_changed(self, layer=None):
        self.update_action_state()

    def update_action_state(self):
        layer = self.canvas.currentLayer() if self.canvas else None

        # Re-bind editing state signals if current layer changed
        if layer != self._tracked_layer:
            if self._tracked_layer is not None:
                try:
                    self._tracked_layer.editingStarted.disconnect(self.update_action_state)
                except (TypeError, RuntimeError):
                    pass  # nosec B110
                try:
                    self._tracked_layer.editingStopped.disconnect(self.update_action_state)
                except (TypeError, RuntimeError):
                    pass  # nosec B110
            self._tracked_layer = layer
            if isinstance(layer, QgsVectorLayer):
                try:
                    layer.editingStarted.connect(self.update_action_state)
                    layer.editingStopped.connect(self.update_action_state)
                except (TypeError, RuntimeError):
                    pass  # nosec B110

        is_vector = isinstance(layer, QgsVectorLayer)
        is_supported_geom = (
            is_vector
            and layer.geometryType()
            in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry)
        )
        is_editable = bool(is_supported_geom and layer.isEditable())

        if is_vector and is_supported_geom:
            if self.settings_widget and hasattr(self.settings_widget, "adapt_to_crs"):
                self.settings_widget.adapt_to_crs(layer.crs())
            if self.canvas_widget and hasattr(self.canvas_widget, "adapt_to_crs"):
                self.canvas_widget.adapt_to_crs(layer.crs())

        if self.action:
            self.action.setEnabled(is_editable)
        if self.restore_action:
            self.restore_action.setEnabled(is_editable)
        if self.batch_action:
            self.batch_action.setEnabled(is_editable)

        if self.settings_widget and hasattr(self.settings_widget, "set_editable_state"):
            self.settings_widget.set_editable_state(is_editable)

        # If editing was stopped while an interactive tool is active on canvas, deactivate it
        if not is_editable and self.canvas:
            if self.map_tool and self.canvas.mapTool() == self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)
                if self.canvas_widget:
                    self.canvas_widget.hide()
                if self.action:
                    self.action.setChecked(False)

            if self.restore_map_tool and self.canvas.mapTool() == self.restore_map_tool:
                self.canvas.unsetMapTool(self.restore_map_tool)
                if self.restore_action:
                    self.restore_action.setChecked(False)

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

        if mode == FilletSettingsWidget.MODE_CHAMFER:
            cmd_title = self.tr("Пакетна фаска")
        else:
            cmd_title = self.tr("Пакетне скруглення")

        layer.beginEditCommand(cmd_title)

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
        """Applies fillet or chamfer to all vertices of a geometry."""
        engine_mode = "chamfer" if mode == FilletSettingsWidget.MODE_CHAMFER else "fillet"

        return GeometryEngine.batch_apply_geometry(
            geom=geom,
            mode=engine_mode,
            radius=radius,
            segments_count=segments,
            dist1=d1,
            dist2=d2,
        )

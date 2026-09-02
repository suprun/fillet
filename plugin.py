# -*- coding: utf-8 -*-
"""
Main plugin class for Fillet & Chamfer Tool.
Compatible with QGIS 3.16 to 4.99 (Qt5 and Qt6).
"""

import os
from typing import Optional

from qgis.core import (
    Qgis,
    QgsApplication,
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
from qgis.PyQt.QtWidgets import QDockWidget, QMenu, QToolButton

try:
    from .core import constants
    from .core.geometry_engine import GeometryEngine
    from .gui.canvas_widget import FilletCanvasWidget
    from .gui.gui_utils import checked_edit_command, require_edit_success
    from .gui.map_tool import FilletMapTool
    from .gui.restore_canvas_widget import RestoreCanvasWidget
    from .gui.restore_map_tool import RestoreMapTool
    from .gui.settings_widget import FilletSettingsWidget
    from .gui.two_line_map_tool import TwoLineMapTool
except (ImportError, ValueError):
    from core import constants
    from core.geometry_engine import GeometryEngine
    from gui.canvas_widget import FilletCanvasWidget
    from gui.gui_utils import checked_edit_command, require_edit_success
    from gui.map_tool import FilletMapTool
    from gui.restore_canvas_widget import RestoreCanvasWidget
    from gui.restore_map_tool import RestoreMapTool
    from gui.settings_widget import FilletSettingsWidget
    from gui.two_line_map_tool import TwoLineMapTool


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
        self.two_line_action: Optional[QAction] = None

        self.map_tool: Optional[FilletMapTool] = None
        self.canvas_widget: Optional[FilletCanvasWidget] = None
        self.restore_map_tool: Optional[RestoreMapTool] = None
        self.restore_canvas_widget: Optional[RestoreCanvasWidget] = None
        self.two_line_map_tool: Optional[TwoLineMapTool] = None

        self.tool_button: Optional[QToolButton] = None
        self.tool_button_action: Optional[QAction] = None
        self.fillet_restore_menu: Optional[QMenu] = None

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
        override_flag = QgsSettings().value("locale/overrideFlag", False, type=bool)
        user_locale = QgsSettings().value("locale/userLocale", "")
        locale_name = ""
        if override_flag and user_locale:
            locale_name = user_locale
        elif hasattr(QgsApplication, "locale"):
            locale_name = QgsApplication.locale()
        elif user_locale:
            locale_name = user_locale
        else:
            locale_name = QLocale().name()

        candidates = [locale_name, locale_name.replace("-", "_"), locale_name[:2], "en"]
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

        # 1. Create shared canvas widget for Fillet/Chamfer and Two-Line tools
        self.canvas_widget = FilletCanvasWidget(self.canvas)
        self.canvas_widget.hide()
        self.canvas_widget.applyToSelectedRequested.connect(self.apply_to_selected_features)

        # 2. Create interactive Corner Restore (Unfillet/Unchamfer) CAD Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.restore_canvas_widget = RestoreCanvasWidget(self.canvas)
        self.restore_canvas_widget.hide()
        self.restore_map_tool = RestoreMapTool(
            self.canvas,
            self.restore_canvas_widget,
            self.iface,
        )

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

        # 3. Create interactive Two-Line Fillet/Chamfer CAD Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.two_line_map_tool = TwoLineMapTool(
            self.canvas,
            widget=self.canvas_widget,
            iface=self.iface,
        )

        two_line_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionTwoLineFillet.svg")
        self.two_line_action = QAction(
            QIcon(two_line_icon_path),
            self.tr("Скруглення / фаска двох ліній (Merge)"),
            self.iface.mainWindow(),
        )
        self.two_line_action.setCheckable(True)
        self.two_line_action.setObjectName("actionTwoLineFillet")
        self.two_line_action.setToolTip(self.tr("<b>З'єднання двох ліній скругленням або фаскою</b><br><br>Утримуйте Alt для перемикання скруглення/фаски.<br><br>Утримуйте Shift для рівних відстаней."))
        self.two_line_action.triggered.connect(self.toggle_two_line_tool)

        adv_tb = self.iface.advancedDigitizeToolBar()

        # 4. Helper functions for inserting actions relative to standard QGIS actions
        def _find_adv_action(predicate):
            if not adv_tb:
                return None
            for act in adv_tb.actions():
                name_lower = act.objectName().lower()
                if predicate(name_lower, act.objectName()):
                    return act
            return None

        def _insert_after_action(target_act, action_to_insert):
            if not adv_tb or not action_to_insert:
                return
            actions_now = adv_tb.actions()
            if target_act and target_act in actions_now:
                try:
                    idx = actions_now.index(target_act)
                    if idx + 1 < len(actions_now):
                        adv_tb.insertAction(actions_now[idx + 1], action_to_insert)
                        return
                except (ValueError, IndexError):
                    pass
            adv_tb.addAction(action_to_insert)

        # 5. QGIS < 4.0 Setup (Combine Fillet & Restore into drop-down menu on toolbar, no separate batch action)
        if not self.is_qgis_4():
            self.map_tool = FilletMapTool(
                self.canvas,
                self.canvas_widget,
                self.iface,
            )

            icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionChamferFillet.svg")
            self.action = QAction(
                QIcon(icon_path),
                self.tr("Інструмент Fillet / Chamfer"),
                self.iface.mainWindow(),
            )
            self.action.setCheckable(True)
            self.action.setObjectName("actionFilletChamfer")
            self.action.setToolTip(self.tr("<b>Створення скруглень та фасок</b><br><br>Утримуйте Alt для перемикання скруглення/фаски.<br><br>Утримуйте Shift для рівних відстаней."))
            self.action.triggered.connect(self.toggle_tool)

            # Create drop-down menu tool button on advancedDigitizeToolBar
            popup_mode = getattr(QToolButton.ToolButtonPopupMode, "MenuButtonPopup", getattr(QToolButton, "MenuButtonPopup", 1))
            self.tool_button = QToolButton(adv_tb)
            self.tool_button.setPopupMode(popup_mode)
            self.tool_button.setDefaultAction(self.action)
            self.tool_button.setObjectName("toolButtonFilletRestore")

            self.fillet_restore_menu = QMenu(self.tool_button)
            self.fillet_restore_menu.addAction(self.action)
            self.fillet_restore_menu.addAction(self.restore_action)
            self.tool_button.setMenu(self.fillet_restore_menu)

            if adv_tb:
                actions = adv_tb.actions()
                if len(actions) >= 13:
                    self.tool_button_action = adv_tb.insertWidget(actions[12], self.tool_button)
                else:
                    self.tool_button_action = adv_tb.addWidget(self.tool_button)
                _insert_after_action(self.tool_button_action, self.two_line_action)
            else:
                self.iface.addVectorToolBarIcon(self.action)
                self.iface.addVectorToolBarIcon(self.restore_action)
                self.iface.addVectorToolBarIcon(self.two_line_action)

            self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.action)
            self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.restore_action)
            self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.two_line_action)

        else:
            # 6. QGIS 4.0+ Setup (Fillet is native, Restore is separate action, Batch Panel dock is active)
            self.settings_widget = FilletSettingsWidget()
            self.dock_widget = QDockWidget(self.tr("Fillet / Chamfer (Пакетна обробка)"), self.iface.mainWindow())
            self.dock_widget.setObjectName("FilletChamferDockWidget")
            self.dock_widget.setWidget(self.settings_widget)
            right_dock = getattr(Qt.DockWidgetArea, "RightDockWidgetArea", getattr(Qt, "RightDockWidgetArea", None))
            self.iface.addDockWidget(right_dock, self.dock_widget)
            self.dock_widget.hide()

            self.settings_widget.applyToSelectedRequested.connect(self.apply_to_selected_features)

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

            if adv_tb:
                anchor_act = _find_adv_action(lambda nl, n: "chamfer" in nl or "fillet" in nl)
                if anchor_act:
                    _insert_after_action(anchor_act, self.restore_action)
                    _insert_after_action(self.restore_action, self.batch_action)
                    _insert_after_action(self.batch_action, self.two_line_action)
                else:
                    adv_tb.addAction(self.restore_action)
                    adv_tb.addAction(self.batch_action)
                    adv_tb.addAction(self.two_line_action)
            else:
                self.iface.addVectorToolBarIcon(self.restore_action)
                self.iface.addVectorToolBarIcon(self.batch_action)
                self.iface.addVectorToolBarIcon(self.two_line_action)

            self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.restore_action)
            self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.batch_action)
            self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.two_line_action)

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
            try:
                self._tracked_layer.selectionChanged.disconnect(self.update_action_state)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self._tracked_layer = None

        try:
            self.canvas.mapToolSet.disconnect(self.on_map_tool_changed)
        except (TypeError, RuntimeError):
            pass  # nosec B110

        # 2. Clean up tool button widget
        if self.tool_button_action and self.iface.advancedDigitizeToolBar():
            self.iface.advancedDigitizeToolBar().removeAction(self.tool_button_action)
            self.tool_button_action = None

        if self.tool_button:
            self.tool_button.setParent(None)
            self.tool_button.deleteLater()
            self.tool_button = None

        if self.fillet_restore_menu:
            self.fillet_restore_menu.setParent(None)
            self.fillet_restore_menu.deleteLater()
            self.fillet_restore_menu = None

        # 3. Clean up interactive fillet action
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

        # 4. Clean up restore action
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

        # 5. Clean up two line action
        if self.two_line_action:
            try:
                self.two_line_action.triggered.disconnect(self.toggle_two_line_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.two_line_action)
            self.iface.removeVectorToolBarIcon(self.two_line_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.two_line_action)
            self.two_line_action.setParent(None)
            self.two_line_action.deleteLater()
            self.two_line_action = None

        # 6. Clean up batch action
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

        # 7. Clean up map tools
        if self.map_tool:
            if self.canvas and self.canvas.mapTool() == self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)
            if hasattr(self.map_tool, "cleanup"):
                self.map_tool.cleanup()
            else:
                self.map_tool.deactivate()
            self.map_tool.deleteLater()
            self.map_tool = None

        if self.two_line_map_tool:
            if self.canvas and self.canvas.mapTool() == self.two_line_map_tool:
                self.canvas.unsetMapTool(self.two_line_map_tool)
            if hasattr(self.two_line_map_tool, "cleanup"):
                self.two_line_map_tool.cleanup()
            else:
                self.two_line_map_tool.deactivate()
            self.two_line_map_tool.deleteLater()
            self.two_line_map_tool = None

        if self.restore_map_tool:
            if self.canvas and self.canvas.mapTool() == self.restore_map_tool:
                self.canvas.unsetMapTool(self.restore_map_tool)
            if hasattr(self.restore_map_tool, "cleanup"):
                self.restore_map_tool.cleanup()
            else:
                self.restore_map_tool.deactivate()
            self.restore_map_tool.deleteLater()
            self.restore_map_tool = None

        # 8. Clean up canvas widgets
        if self.canvas_widget:
            try:
                self.canvas.removeEventFilter(self.canvas_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.canvas_widget.hide()
            self.canvas_widget.setParent(None)
            self.canvas_widget.deleteLater()
            self.canvas_widget = None

        if self.restore_canvas_widget:
            try:
                self.canvas.removeEventFilter(self.restore_canvas_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.restore_canvas_widget.hide()
            self.restore_canvas_widget.setParent(None)
            self.restore_canvas_widget.deleteLater()
            self.restore_canvas_widget = None

        # 9. Clean up settings widget and dock widget
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

        # 10. Remove translator
        if self.translator:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def _show_message(self, title: str, text: str, level=Qgis.MessageLevel.Info, duration: int = 5):
        """Displays temporary notification message with auto-dismiss duration timer."""
        if self.iface and self.iface.messageBar():
            self.iface.messageBar().pushMessage(title, text, level, duration)

    def toggle_tool(self, checked: bool):
        if checked:
            if self.map_tool:
                self.canvas.setMapTool(self.map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)

    def toggle_two_line_tool(self, checked: bool):
        if checked:
            if self.two_line_map_tool:
                self.canvas.setMapTool(self.two_line_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.two_line_map_tool:
                self.canvas.unsetMapTool(self.two_line_map_tool)

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
            if is_active and self.tool_button:
                self.tool_button.setDefaultAction(self.action)

        if self.restore_action:
            is_restore_active = tool == self.restore_map_tool
            self.restore_action.setChecked(is_restore_active)
            if is_restore_active and self.tool_button:
                self.tool_button.setDefaultAction(self.restore_action)
            if not is_restore_active and self.restore_canvas_widget:
                self.restore_canvas_widget.hide()

        if self.two_line_action:
            is_two_line_active = tool == self.two_line_map_tool
            self.two_line_action.setChecked(is_two_line_active)

        if self.canvas_widget:
            if tool != self.map_tool and tool != self.two_line_map_tool:
                self.canvas_widget.hide()

    def _on_current_layer_changed(self, layer=None):
        self.update_action_state()

    def update_action_state(self):
        layer = self.canvas.currentLayer() if self.canvas else None

        # Re-bind editing state signals if current layer changed
        if layer != self._tracked_layer:
            if self._tracked_layer is not None:
                if isinstance(self._tracked_layer, QgsVectorLayer):
                    try:
                        self._tracked_layer.editingStarted.disconnect(self.update_action_state)
                    except (TypeError, RuntimeError, AttributeError):
                        pass  # nosec B110
                    try:
                        self._tracked_layer.editingStopped.disconnect(self.update_action_state)
                    except (TypeError, RuntimeError, AttributeError):
                        pass  # nosec B110
                    try:
                        self._tracked_layer.selectionChanged.disconnect(self.update_action_state)
                    except (TypeError, RuntimeError, AttributeError):
                        pass  # nosec B110
            self._tracked_layer = layer
            if isinstance(layer, QgsVectorLayer):
                try:
                    layer.editingStarted.connect(self.update_action_state)
                    layer.editingStopped.connect(self.update_action_state)
                    layer.selectionChanged.connect(self.update_action_state)
                except (TypeError, RuntimeError, AttributeError):
                    pass  # nosec B110

        is_vector = isinstance(layer, QgsVectorLayer)
        is_supported_geom = (
            is_vector
            and layer.geometryType()
            in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry)
        )
        is_editable = bool(is_supported_geom and layer.isEditable())
        is_line_editable = bool(
            is_vector
            and layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry
            and layer.isEditable()
        )
        has_selection = bool(layer.selectedFeatureCount() > 0) if is_vector else False
        is_batch_enabled = bool(is_editable and has_selection)

        if is_vector and is_supported_geom:
            if self.settings_widget and hasattr(self.settings_widget, "adapt_to_crs"):
                self.settings_widget.adapt_to_crs(layer.crs())
            if self.canvas_widget and hasattr(self.canvas_widget, "adapt_to_crs"):
                self.canvas_widget.adapt_to_crs(layer.crs())

        if self.action:
            self.action.setEnabled(is_editable)
        if self.two_line_action:
            self.two_line_action.setEnabled(is_line_editable)
        if self.restore_action:
            self.restore_action.setEnabled(is_editable)
        if self.batch_action:
            self.batch_action.setEnabled(is_editable)
        if self.tool_button:
            self.tool_button.setEnabled(is_editable)

        if self.canvas_widget and hasattr(self.canvas_widget, "set_apply_selected_enabled"):
            self.canvas_widget.set_apply_selected_enabled(is_batch_enabled)

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
                if self.restore_canvas_widget:
                    self.restore_canvas_widget.hide()
                if self.restore_action:
                    self.restore_action.setChecked(False)

        if not is_line_editable and self.canvas:
            if self.two_line_map_tool and self.canvas.mapTool() == self.two_line_map_tool:
                self.canvas.unsetMapTool(self.two_line_map_tool)
                if self.canvas_widget:
                    self.canvas_widget.hide()
                if self.two_line_action:
                    self.two_line_action.setChecked(False)

    def apply_to_selected_features(self):
        """Batch apply fillet or chamfer to all corners of selected features."""
        layer = self.canvas.currentLayer()
        if not isinstance(layer, QgsVectorLayer) or not layer.isEditable():
            self._show_message(
                self.tr("Увага"),
                self.tr("Активний шар повинен бути векторним і перебувати в режимі редагування."),
                level=Qgis.MessageLevel.Warning,
                duration=4,
            )
            return

        selected_fids = layer.selectedFeatureIds()
        if not selected_fids:
            self._show_message(
                self.tr("Інфо"),
                self.tr("Немає виділених об'єктів для обробки."),
                level=Qgis.MessageLevel.Info,
                duration=4,
            )
            return

        # Read parameters from canvas_widget (if visible/available) or settings_widget (dock panel in QGIS 4)
        if self.canvas_widget and (not self.settings_widget or not (self.dock_widget and self.dock_widget.isVisible())):
            mode = self.canvas_widget.mode
            radius = self.canvas_widget.radius
            segments = self.canvas_widget.segments_count
            d1 = self.canvas_widget.distance1
            d2 = self.canvas_widget.distance2
        elif self.settings_widget:
            mode = self.settings_widget.mode
            radius = self.settings_widget.radius
            segments = self.settings_widget.segments_count
            d1 = self.settings_widget.distance1
            d2 = self.settings_widget.distance2
        else:
            return

        is_chamfer = mode == constants.MODE_CHAMFER or (hasattr(FilletSettingsWidget, "MODE_CHAMFER") and mode == FilletSettingsWidget.MODE_CHAMFER)
        if is_chamfer:
            cmd_title = self.tr("Пакетна фаска")
        else:
            cmd_title = self.tr("Пакетне скруглення")

        geometry_changes = []
        curved_count = 0
        for fid in selected_fids:
            feat = layer.getFeature(fid)
            geom = feat.geometry()
            if geom.isEmpty() or geom.isNull():
                continue
            if GeometryEngine.has_curved_segments(geom):
                curved_count += 1
                continue

            new_geom = self._batch_process_geometry(geom, mode, radius, segments, d1, d2)
            if (
                new_geom
                and not new_geom.isEmpty()
                and new_geom.asWkb() != geom.asWkb()
            ):
                geometry_changes.append((fid, new_geom))

        try:
            if geometry_changes:
                with checked_edit_command(layer, cmd_title):
                    for fid, new_geom in geometry_changes:
                        require_edit_success(
                            layer.changeGeometry(fid, new_geom),
                            self.tr("Не вдалося змінити геометрію об'єкта."),
                        )
        except (RuntimeError, TypeError) as error:
            self._show_message(
                self.tr("Помилка"),
                str(error),
                level=Qgis.MessageLevel.Warning,
                duration=5,
            )
            return

        modified_count = len(geometry_changes)
        self.canvas.refresh()
        if curved_count:
            self._show_message(
                self.tr("Увага"),
                self.tr("Пропущено об'єктів із кривими сегментами: {}.").format(curved_count),
                level=Qgis.MessageLevel.Warning,
                duration=5,
            )
        self._show_message(
            self.tr("Успіх"),
            self.tr("Оброблено {} об'єкт(ів).").format(modified_count),
            level=Qgis.MessageLevel.Success,
            duration=5,
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
        is_chamfer = mode == constants.MODE_CHAMFER or (hasattr(FilletSettingsWidget, "MODE_CHAMFER") and mode == FilletSettingsWidget.MODE_CHAMFER)
        engine_mode = "chamfer" if is_chamfer else "fillet"

        return GeometryEngine.batch_apply_geometry(
            geom=geom,
            mode=engine_mode,
            radius=radius,
            segments_count=segments,
            dist1=d1,
            dist2=d2,
        )

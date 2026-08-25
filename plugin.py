# -*- coding: utf-8 -*-
"""
Main plugin class for Fillet & Chamfer Tool.
Compatible with QGIS 3.16 to 3.99 (Qt5).
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
from qgis.PyQt.QtWidgets import QDockWidget

try:
    from .gui.canvas_widget import FilletCanvasWidget
    from .gui.clean_duplicate_nodes_map_tool import CleanDuplicateNodesMapTool
    from .gui.edge_offset_canvas_widget import EdgeOffsetCanvasWidget
    from .gui.edge_offset_map_tool import EdgeOffsetMapTool
    from .gui.map_tool import FilletMapTool
    from .gui.mirror_canvas_widget import MirrorCanvasWidget
    from .gui.mirror_map_tool import MirrorMapTool
    from .gui.restore_canvas_widget import RestoreCanvasWidget
    from .gui.restore_map_tool import RestoreMapTool
    from .gui.rotate_map_tool import RotateMapTool
    from .gui.rotation_canvas_widget import RotationCanvasWidget
    from .gui.scale_rotate_canvas_widget import ScaleRotateCanvasWidget
    from .gui.scale_rotate_map_tool import ScaleRotateMapTool
    from .gui.settings_widget import FilletSettingsWidget
    from .gui.two_line_map_tool import TwoLineMapTool
except (ImportError, ValueError):
    from core.geometry_engine import GeometryEngine
    from gui.canvas_widget import FilletCanvasWidget
    from gui.clean_duplicate_nodes_map_tool import CleanDuplicateNodesMapTool
    from gui.edge_offset_canvas_widget import EdgeOffsetCanvasWidget
    from gui.edge_offset_map_tool import EdgeOffsetMapTool
    from gui.map_tool import FilletMapTool
    from gui.mirror_canvas_widget import MirrorCanvasWidget
    from gui.mirror_map_tool import MirrorMapTool
    from gui.restore_canvas_widget import RestoreCanvasWidget
    from gui.restore_map_tool import RestoreMapTool
    from gui.rotate_map_tool import RotateMapTool
    from gui.rotation_canvas_widget import RotationCanvasWidget
    from gui.scale_rotate_canvas_widget import ScaleRotateCanvasWidget
    from gui.scale_rotate_map_tool import ScaleRotateMapTool
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
        self.two_line_action: Optional[QAction] = None
        self.restore_action: Optional[QAction] = None
        self.rotate_action: Optional[QAction] = None
        self.mirror_action: Optional[QAction] = None
        self.scale_rotate_action: Optional[QAction] = None
        self.edge_offset_action: Optional[QAction] = None
        self.clean_duplicates_action: Optional[QAction] = None
        self.batch_action: Optional[QAction] = None
        self.map_tool: Optional[FilletMapTool] = None
        self.two_line_map_tool: Optional[TwoLineMapTool] = None
        self.restore_map_tool: Optional[RestoreMapTool] = None
        self.restore_canvas_widget: Optional[RestoreCanvasWidget] = None
        self.rotate_map_tool: Optional[RotateMapTool] = None
        self.rotation_widget: Optional[RotationCanvasWidget] = None
        self.mirror_map_tool: Optional[MirrorMapTool] = None
        self.mirror_widget: Optional[MirrorCanvasWidget] = None
        self.scale_rotate_map_tool: Optional[ScaleRotateMapTool] = None
        self.scale_rotate_widget: Optional[ScaleRotateCanvasWidget] = None
        self.edge_offset_map_tool: Optional[EdgeOffsetMapTool] = None
        self.edge_offset_widget: Optional[EdgeOffsetCanvasWidget] = None
        self.clean_duplicates_map_tool: Optional[CleanDuplicateNodesMapTool] = None
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
        self.restore_canvas_widget = RestoreCanvasWidget(self.canvas)
        self.restore_canvas_widget.hide()
        self.restore_map_tool = RestoreMapTool(self.canvas, self.restore_canvas_widget)

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

        # 4. Create shared canvas widget for Fillet/Chamfer tools
        self.canvas_widget = FilletCanvasWidget(self.canvas)
        self.canvas_widget.hide()

        # 5. Create interactive Two-Line Fillet/Chamfer CAD Map Tool (available in QGIS 3.x and QGIS 4.x)
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
        self.two_line_action.setToolTip(self.tr("З'єднання двох ліній скругленням або фаскою з об'єднанням об'єктів"))
        self.two_line_action.triggered.connect(self.toggle_two_line_tool)

        # 6. Create interactive CAD 3-Point Rotation Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.rotation_widget = RotationCanvasWidget(self.canvas)
        self.rotation_widget.hide()
        self.rotate_map_tool = RotateMapTool(self.canvas, self.rotation_widget)

        rotate_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionRotateCAD.svg")
        self.rotate_action = QAction(
            QIcon(rotate_icon_path),
            self.tr("CAD Обертання (Rotate)"),
            self.iface.mainWindow(),
        )
        self.rotate_action.setCheckable(True)
        self.rotate_action.setObjectName("actionRotateCAD")
        self.rotate_action.setToolTip(self.tr("Інтерактивний CAD інструмент обертання геометрій із вибором центру (Pivot)"))
        self.rotate_action.triggered.connect(self.toggle_rotate_tool)

        # 7. Create interactive CAD 2-Point Mirror Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.mirror_widget = MirrorCanvasWidget(self.canvas)
        self.mirror_widget.hide()
        self.mirror_map_tool = MirrorMapTool(self.canvas, self.mirror_widget)

        mirror_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionMirrorCAD.svg")
        self.mirror_action = QAction(
            QIcon(mirror_icon_path),
            self.tr("CAD Дзеркало (Mirror)"),
            self.iface.mainWindow(),
        )
        self.mirror_action.setCheckable(True)
        self.mirror_action.setObjectName("actionMirrorCAD")
        self.mirror_action.setToolTip(self.tr("Інтерактивний CAD інструмент дзеркального відображення геометрій відносно осі з 2 точок"))
        self.mirror_action.triggered.connect(self.toggle_mirror_tool)

        # 7.5. Create interactive CAD 3-Point Scale with Rotation Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.scale_rotate_widget = ScaleRotateCanvasWidget(self.canvas)
        self.scale_rotate_widget.hide()
        self.scale_rotate_map_tool = ScaleRotateMapTool(self.canvas, self.scale_rotate_widget)

        scale_rotate_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionScaleRotateCAD.svg")
        self.scale_rotate_action = QAction(
            QIcon(scale_rotate_icon_path),
            self.tr("CAD Масштаб та Обертання (Scale & Rotate)"),
            self.iface.mainWindow(),
        )
        self.scale_rotate_action.setCheckable(True)
        self.scale_rotate_action.setObjectName("actionScaleRotateCAD")
        self.scale_rotate_action.setToolTip(self.tr("Інтерактивний CAD інструмент масштабування та обертання геометрій відносно опорних точок"))
        self.scale_rotate_action.triggered.connect(self.toggle_scale_rotate_tool)

        # 7.6. Create interactive CAD Edge Offset (Parallel Shift) Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.edge_offset_widget = EdgeOffsetCanvasWidget(self.canvas)
        self.edge_offset_widget.hide()
        self.edge_offset_map_tool = EdgeOffsetMapTool(self.canvas, self.edge_offset_widget)

        edge_offset_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionEdgeOffsetCAD.svg")
        self.edge_offset_action = QAction(
            QIcon(edge_offset_icon_path),
            self.tr("CAD Зсув ребра (Edge Offset)"),
            self.iface.mainWindow(),
        )
        self.edge_offset_action.setCheckable(True)
        self.edge_offset_action.setObjectName("actionEdgeOffsetCAD")
        self.edge_offset_action.setToolTip(self.tr("Інтерактивний CAD інструмент паралельного зсуву відрізка полігона чи полілінії"))
        self.edge_offset_action.triggered.connect(self.toggle_edge_offset_tool)

        # 7.7. Create interactive Quick Clean Duplicate Nodes Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.clean_duplicates_map_tool = CleanDuplicateNodesMapTool(self.canvas)

        clean_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionCleanDuplicateNodes.svg")
        self.clean_duplicates_action = QAction(
            QIcon(clean_icon_path),
            self.tr("CAD Очищення дубльованих вузлів"),
            self.iface.mainWindow(),
        )
        self.clean_duplicates_action.setCheckable(True)
        self.clean_duplicates_action.setObjectName("actionCleanDuplicateNodes")
        self.clean_duplicates_action.setToolTip(self.tr("Швидке очищення та виправлення дубльованих вузлів геометрій"))
        self.clean_duplicates_action.triggered.connect(self.toggle_clean_duplicates_tool)

        adv_tb = self.iface.advancedDigitizeToolBar()

        # 8. Create interactive Fillet / Chamfer MapTool ONLY in QGIS 3.x (native in QGIS 4.0+)
        if not self.is_qgis_4():
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

        # 9. Insert rotate_action, mirror_action, scale_rotate_action, edge_offset_action, clean_duplicates_action on toolbar
        if adv_tb:
            rotate_feature_act = None
            for act in adv_tb.actions():
                name_lower = act.objectName().lower()
                if "rotatefeature" in name_lower or act.objectName() == "mActionRotateFeature":
                    rotate_feature_act = act
                    break

            actions_now = adv_tb.actions()
            if rotate_feature_act and rotate_feature_act in actions_now:
                try:
                    idx = actions_now.index(rotate_feature_act)
                    if idx + 1 < len(actions_now):
                        adv_tb.insertAction(actions_now[idx + 1], self.rotate_action)
                    else:
                        adv_tb.addAction(self.rotate_action)
                except (ValueError, IndexError):
                    adv_tb.addAction(self.rotate_action)
            elif len(actions_now) >= 4:
                adv_tb.insertAction(actions_now[3], self.rotate_action)
            else:
                adv_tb.addAction(self.rotate_action)

            # Insert mirror_action after rotate_action
            actions_now = adv_tb.actions()
            try:
                idx = actions_now.index(self.rotate_action)
                if idx + 1 < len(actions_now):
                    adv_tb.insertAction(actions_now[idx + 1], self.mirror_action)
                else:
                    adv_tb.addAction(self.mirror_action)
            except (ValueError, IndexError):
                adv_tb.addAction(self.mirror_action)

            # Insert scale_rotate_action after mirror_action
            actions_now = adv_tb.actions()
            try:
                idx = actions_now.index(self.mirror_action)
                if idx + 1 < len(actions_now):
                    adv_tb.insertAction(actions_now[idx + 1], self.scale_rotate_action)
                else:
                    adv_tb.addAction(self.scale_rotate_action)
            except (ValueError, IndexError):
                adv_tb.addAction(self.scale_rotate_action)

            # Insert edge_offset_action after scale_rotate_action
            actions_now = adv_tb.actions()
            try:
                idx = actions_now.index(self.scale_rotate_action)
                if idx + 1 < len(actions_now):
                    adv_tb.insertAction(actions_now[idx + 1], self.edge_offset_action)
                else:
                    adv_tb.addAction(self.edge_offset_action)
            except (ValueError, IndexError):
                adv_tb.addAction(self.edge_offset_action)

            # Insert clean_duplicates_action after edge_offset_action
            actions_now = adv_tb.actions()
            try:
                idx = actions_now.index(self.edge_offset_action)
                if idx + 1 < len(actions_now):
                    adv_tb.insertAction(actions_now[idx + 1], self.clean_duplicates_action)
                else:
                    adv_tb.addAction(self.clean_duplicates_action)
            except (ValueError, IndexError):
                adv_tb.addAction(self.clean_duplicates_action)
        else:
            self.iface.addVectorToolBarIcon(self.rotate_action)
            self.iface.addVectorToolBarIcon(self.mirror_action)
            self.iface.addVectorToolBarIcon(self.scale_rotate_action)
            self.iface.addVectorToolBarIcon(self.edge_offset_action)
            self.iface.addVectorToolBarIcon(self.clean_duplicates_action)

        # 10. Insert two_line_action, restore_action and batch_action on toolbar
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
                        adv_tb.insertAction(actions_now[idx + 1], self.two_line_action)
                    else:
                        adv_tb.addAction(self.two_line_action)
                except (ValueError, IndexError):
                    adv_tb.addAction(self.two_line_action)
            else:
                adv_tb.addAction(self.two_line_action)

            # Insert restore_action after two_line_action
            actions_now = adv_tb.actions()
            try:
                idx = actions_now.index(self.two_line_action)
                if idx + 1 < len(actions_now):
                    adv_tb.insertAction(actions_now[idx + 1], self.restore_action)
                else:
                    adv_tb.addAction(self.restore_action)
            except (ValueError, IndexError):
                adv_tb.addAction(self.restore_action)

            # Insert batch_action after restore_action
            actions_now = adv_tb.actions()
            try:
                idx = actions_now.index(self.restore_action)
                if idx + 1 < len(actions_now):
                    adv_tb.insertAction(actions_now[idx + 1], self.batch_action)
                else:
                    adv_tb.addAction(self.batch_action)
            except (ValueError, IndexError):
                adv_tb.addAction(self.batch_action)
        else:
            self.iface.addVectorToolBarIcon(self.two_line_action)
            self.iface.addVectorToolBarIcon(self.restore_action)
            self.iface.addVectorToolBarIcon(self.batch_action)

        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.two_line_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.restore_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.rotate_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.mirror_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.scale_rotate_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.edge_offset_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.clean_duplicates_action)
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
            try:
                self._tracked_layer.selectionChanged.disconnect(self.update_action_state)
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

        # 4. Clean up rotate action
        if self.rotate_action:
            try:
                self.rotate_action.triggered.disconnect(self.toggle_rotate_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.rotate_action)
            self.iface.removeVectorToolBarIcon(self.rotate_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.rotate_action)
            self.rotate_action.setParent(None)
            self.rotate_action.deleteLater()
            self.rotate_action = None

        # 5. Clean up mirror action
        if self.mirror_action:
            try:
                self.mirror_action.triggered.disconnect(self.toggle_mirror_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.mirror_action)
            self.iface.removeVectorToolBarIcon(self.mirror_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.mirror_action)
            self.mirror_action.setParent(None)
            self.mirror_action.deleteLater()
            self.mirror_action = None

        # 5.5. Clean up scale rotate action
        if self.scale_rotate_action:
            try:
                self.scale_rotate_action.triggered.disconnect(self.toggle_scale_rotate_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.scale_rotate_action)
            self.iface.removeVectorToolBarIcon(self.scale_rotate_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.scale_rotate_action)
            self.scale_rotate_action.setParent(None)
            self.scale_rotate_action.deleteLater()
            self.scale_rotate_action = None

        # 5.6. Clean up edge offset action
        if self.edge_offset_action:
            try:
                self.edge_offset_action.triggered.disconnect(self.toggle_edge_offset_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.edge_offset_action)
            self.iface.removeVectorToolBarIcon(self.edge_offset_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.edge_offset_action)
            self.edge_offset_action.setParent(None)
            self.edge_offset_action.deleteLater()
            self.edge_offset_action = None

        # 5.7. Clean up clean duplicates action
        if self.clean_duplicates_action:
            try:
                self.clean_duplicates_action.triggered.disconnect(self.toggle_clean_duplicates_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.clean_duplicates_action)
            self.iface.removeVectorToolBarIcon(self.clean_duplicates_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.clean_duplicates_action)
            self.clean_duplicates_action.setParent(None)
            self.clean_duplicates_action.deleteLater()
            self.clean_duplicates_action = None

        # 6. Clean up two line action
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

        # 7. Clean up batch action
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

        # 8. Clean up map tools
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

        if self.rotate_map_tool:
            if self.canvas and self.canvas.mapTool() == self.rotate_map_tool:
                self.canvas.unsetMapTool(self.rotate_map_tool)
            if hasattr(self.rotate_map_tool, "cleanup"):
                self.rotate_map_tool.cleanup()
            else:
                self.rotate_map_tool.deactivate()
            self.rotate_map_tool.deleteLater()
            self.rotate_map_tool = None

        if self.mirror_map_tool:
            if self.canvas and self.canvas.mapTool() == self.mirror_map_tool:
                self.canvas.unsetMapTool(self.mirror_map_tool)
            if hasattr(self.mirror_map_tool, "cleanup"):
                self.mirror_map_tool.cleanup()
            else:
                self.mirror_map_tool.deactivate()
            self.mirror_map_tool.deleteLater()
            self.mirror_map_tool = None

        if self.scale_rotate_map_tool:
            if self.canvas and self.canvas.mapTool() == self.scale_rotate_map_tool:
                self.canvas.unsetMapTool(self.scale_rotate_map_tool)
            if hasattr(self.scale_rotate_map_tool, "cleanup"):
                self.scale_rotate_map_tool.cleanup()
            else:
                self.scale_rotate_map_tool.deactivate()
            self.scale_rotate_map_tool.deleteLater()
            self.scale_rotate_map_tool = None

        if self.edge_offset_map_tool:
            if self.canvas and self.canvas.mapTool() == self.edge_offset_map_tool:
                self.canvas.unsetMapTool(self.edge_offset_map_tool)
            if hasattr(self.edge_offset_map_tool, "cleanup"):
                self.edge_offset_map_tool.cleanup()
            else:
                self.edge_offset_map_tool.deactivate()
            self.edge_offset_map_tool.deleteLater()
            self.edge_offset_map_tool = None

        if self.clean_duplicates_map_tool:
            if self.canvas and self.canvas.mapTool() == self.clean_duplicates_map_tool:
                self.canvas.unsetMapTool(self.clean_duplicates_map_tool)
            if hasattr(self.clean_duplicates_map_tool, "cleanup"):
                self.clean_duplicates_map_tool.cleanup()
            else:
                self.clean_duplicates_map_tool.deactivate()
            self.clean_duplicates_map_tool.deleteLater()
            self.clean_duplicates_map_tool = None

        # 9. Clean up canvas widgets
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

        if self.rotation_widget:
            try:
                self.canvas.removeEventFilter(self.rotation_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.rotation_widget.hide()
            self.rotation_widget.setParent(None)
            self.rotation_widget.deleteLater()
            self.rotation_widget = None

        if self.mirror_widget:
            try:
                self.canvas.removeEventFilter(self.mirror_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.mirror_widget.hide()
            self.mirror_widget.setParent(None)
            self.mirror_widget.deleteLater()
            self.mirror_widget = None

        if self.scale_rotate_widget:
            try:
                self.canvas.removeEventFilter(self.scale_rotate_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.scale_rotate_widget.hide()
            self.scale_rotate_widget.setParent(None)
            self.scale_rotate_widget.deleteLater()
            self.scale_rotate_widget = None

        if self.edge_offset_widget:
            try:
                self.canvas.removeEventFilter(self.edge_offset_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.edge_offset_widget.hide()
            self.edge_offset_widget.setParent(None)
            self.edge_offset_widget.deleteLater()
            self.edge_offset_widget = None

        # 10. Clean up settings widget and dock widget
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

        # 11. Remove translator
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

    def toggle_rotate_tool(self, checked: bool):
        if checked:
            if self.rotate_map_tool:
                self.canvas.setMapTool(self.rotate_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.rotate_map_tool:
                self.canvas.unsetMapTool(self.rotate_map_tool)

    def toggle_mirror_tool(self, checked: bool):
        if checked:
            if self.mirror_map_tool:
                self.canvas.setMapTool(self.mirror_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.mirror_map_tool:
                self.canvas.unsetMapTool(self.mirror_map_tool)

    def toggle_scale_rotate_tool(self, checked: bool):
        if checked:
            if self.scale_rotate_map_tool:
                self.canvas.setMapTool(self.scale_rotate_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.scale_rotate_map_tool:
                self.canvas.unsetMapTool(self.scale_rotate_map_tool)

    def toggle_edge_offset_tool(self, checked: bool):
        if checked:
            if self.edge_offset_map_tool:
                self.canvas.setMapTool(self.edge_offset_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.edge_offset_map_tool:
                self.canvas.unsetMapTool(self.edge_offset_map_tool)

    def toggle_clean_duplicates_tool(self, checked: bool):
        if checked:
            if self.clean_duplicates_map_tool:
                self.canvas.setMapTool(self.clean_duplicates_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.clean_duplicates_map_tool:
                self.canvas.unsetMapTool(self.clean_duplicates_map_tool)

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

        if self.two_line_action:
            is_two_line_active = tool == self.two_line_map_tool
            self.two_line_action.setChecked(is_two_line_active)

        if self.canvas_widget:
            if tool != self.map_tool and tool != self.two_line_map_tool:
                self.canvas_widget.hide()

        if self.restore_action:
            is_restore_active = tool == self.restore_map_tool
            self.restore_action.setChecked(is_restore_active)
            if not is_restore_active and self.restore_canvas_widget:
                self.restore_canvas_widget.hide()

        if self.rotate_action:
            is_rotate_active = tool == self.rotate_map_tool
            self.rotate_action.setChecked(is_rotate_active)
            if not is_rotate_active and self.rotation_widget:
                self.rotation_widget.hide()

        if self.mirror_action:
            is_mirror_active = tool == self.mirror_map_tool
            self.mirror_action.setChecked(is_mirror_active)
            if not is_mirror_active and self.mirror_widget:
                self.mirror_widget.hide()

        if self.scale_rotate_action:
            is_sr_active = tool == self.scale_rotate_map_tool
            self.scale_rotate_action.setChecked(is_sr_active)
            if not is_sr_active and self.scale_rotate_widget:
                self.scale_rotate_widget.hide()

        if self.edge_offset_action:
            is_eo_active = tool == self.edge_offset_map_tool
            self.edge_offset_action.setChecked(is_eo_active)
            if not is_eo_active and self.edge_offset_widget:
                self.edge_offset_widget.hide()

        if self.clean_duplicates_action:
            is_cd_active = tool == self.clean_duplicates_map_tool
            self.clean_duplicates_action.setChecked(is_cd_active)

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
        is_line_editable = bool(is_vector and layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry and layer.isEditable())
        has_selection = bool(layer.selectedFeatureCount() > 0) if is_vector else False
        is_rotate_enabled = bool(is_editable and has_selection)
        is_mirror_enabled = bool(is_editable and has_selection)
        is_scale_rotate_enabled = bool(is_editable and has_selection)

        if is_vector and is_supported_geom:
            if self.settings_widget and hasattr(self.settings_widget, "adapt_to_crs"):
                self.settings_widget.adapt_to_crs(layer.crs())
            if self.canvas_widget and hasattr(self.canvas_widget, "adapt_to_crs"):
                self.canvas_widget.adapt_to_crs(layer.crs())
            if self.edge_offset_widget and hasattr(self.edge_offset_widget, "adapt_to_crs"):
                self.edge_offset_widget.adapt_to_crs(layer.crs())

        if self.action:
            self.action.setEnabled(is_editable)
        if self.two_line_action:
            self.two_line_action.setEnabled(is_line_editable)
        if self.restore_action:
            self.restore_action.setEnabled(is_editable)
        if self.rotate_action:
            self.rotate_action.setEnabled(is_rotate_enabled)
        if self.mirror_action:
            self.mirror_action.setEnabled(is_mirror_enabled)
        if self.scale_rotate_action:
            self.scale_rotate_action.setEnabled(is_scale_rotate_enabled)
        if self.edge_offset_action:
            self.edge_offset_action.setEnabled(is_editable)
        if self.clean_duplicates_action:
            self.clean_duplicates_action.setEnabled(is_editable)
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
                if self.restore_canvas_widget:
                    self.restore_canvas_widget.hide()
                if self.restore_action:
                    self.restore_action.setChecked(False)

            if self.edge_offset_map_tool and self.canvas.mapTool() == self.edge_offset_map_tool:
                self.canvas.unsetMapTool(self.edge_offset_map_tool)
                if self.edge_offset_widget:
                    self.edge_offset_widget.hide()
                if self.edge_offset_action:
                    self.edge_offset_action.setChecked(False)

            if self.clean_duplicates_map_tool and self.canvas.mapTool() == self.clean_duplicates_map_tool:
                self.canvas.unsetMapTool(self.clean_duplicates_map_tool)
                if self.clean_duplicates_action:
                    self.clean_duplicates_action.setChecked(False)

        if not is_rotate_enabled and self.canvas:
            if self.rotate_map_tool and self.canvas.mapTool() == self.rotate_map_tool:
                self.canvas.unsetMapTool(self.rotate_map_tool)
                if self.rotation_widget:
                    self.rotation_widget.hide()
                if self.rotate_action:
                    self.rotate_action.setChecked(False)

        if not is_mirror_enabled and self.canvas:
            if self.mirror_map_tool and self.canvas.mapTool() == self.mirror_map_tool:
                self.canvas.unsetMapTool(self.mirror_map_tool)
                if self.mirror_widget:
                    self.mirror_widget.hide()
                if self.mirror_action:
                    self.mirror_action.setChecked(False)

        if not is_scale_rotate_enabled and self.canvas:
            if self.scale_rotate_map_tool and self.canvas.mapTool() == self.scale_rotate_map_tool:
                self.canvas.unsetMapTool(self.scale_rotate_map_tool)
                if self.scale_rotate_widget:
                    self.scale_rotate_widget.hide()
                if self.scale_rotate_action:
                    self.scale_rotate_action.setChecked(False)

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
        engine_mode = "chamfer" if mode == FilletSettingsWidget.MODE_CHAMFER else "fillet"

        return GeometryEngine.batch_apply_geometry(
            geom=geom,
            mode=engine_mode,
            radius=radius,
            segments_count=segments,
            dist1=d1,
            dist2=d2,
        )

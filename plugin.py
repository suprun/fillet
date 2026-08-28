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
    from .core.geometry_engine import GeometryEngine
    from .gui.array_canvas_widget import ArrayCanvasWidget
    from .gui.array_map_tool import CADArrayMapTool
    from .gui.canvas_widget import FilletCanvasWidget
    from .gui.clean_duplicate_nodes_map_tool import CleanDuplicateNodesMapTool
    from .gui.divide_line_canvas_widget import DivideLineCanvasWidget
    from .gui.divide_line_map_tool import CADDivideLineMapTool
    from .gui.edge_offset_canvas_widget import EdgeOffsetCanvasWidget
    from .gui.edge_offset_map_tool import EdgeOffsetMapTool
    from .gui.explode_canvas_widget import ExplodeCanvasWidget
    from .gui.explode_map_tool import ExplodeLineMapTool
    from .gui.gui_utils import checked_edit_command, require_edit_success
    from .gui.map_tool import FilletMapTool
    from .gui.mirror_canvas_widget import MirrorCanvasWidget
    from .gui.mirror_map_tool import MirrorMapTool
    from .gui.ortho_angles_canvas_widget import OrthoAnglesCanvasWidget
    from .gui.ortho_angles_map_tool import CADOrthoAnglesMapTool
    from .gui.polar_array_canvas_widget import PolarArrayCanvasWidget
    from .gui.polar_array_map_tool import CADPolarArrayMapTool
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
    from gui.array_canvas_widget import ArrayCanvasWidget
    from gui.array_map_tool import CADArrayMapTool
    from gui.canvas_widget import FilletCanvasWidget
    from gui.clean_duplicate_nodes_map_tool import CleanDuplicateNodesMapTool
    from gui.divide_line_canvas_widget import DivideLineCanvasWidget
    from gui.divide_line_map_tool import CADDivideLineMapTool
    from gui.edge_offset_canvas_widget import EdgeOffsetCanvasWidget
    from gui.edge_offset_map_tool import EdgeOffsetMapTool
    from gui.explode_canvas_widget import ExplodeCanvasWidget
    from gui.explode_map_tool import ExplodeLineMapTool
    from gui.gui_utils import checked_edit_command, require_edit_success
    from gui.map_tool import FilletMapTool
    from gui.mirror_canvas_widget import MirrorCanvasWidget
    from gui.mirror_map_tool import MirrorMapTool
    from gui.ortho_angles_canvas_widget import OrthoAnglesCanvasWidget
    from gui.ortho_angles_map_tool import CADOrthoAnglesMapTool
    from gui.polar_array_canvas_widget import PolarArrayCanvasWidget
    from gui.polar_array_map_tool import CADPolarArrayMapTool
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
        self.array_action: Optional[QAction] = None
        self.polar_array_action: Optional[QAction] = None
        self.two_line_action: Optional[QAction] = None
        self.restore_action: Optional[QAction] = None
        self.rotate_action: Optional[QAction] = None
        self.mirror_action: Optional[QAction] = None
        self.scale_rotate_action: Optional[QAction] = None
        self.edge_offset_action: Optional[QAction] = None
        self.clean_duplicates_action: Optional[QAction] = None
        self.explode_action: Optional[QAction] = None
        self.divide_line_action: Optional[QAction] = None
        self.ortho_angles_action: Optional[QAction] = None
        self.batch_action: Optional[QAction] = None
        self.map_tool: Optional[FilletMapTool] = None
        self.array_map_tool: Optional[CADArrayMapTool] = None
        self.array_widget: Optional[ArrayCanvasWidget] = None
        self.polar_array_map_tool: Optional[CADPolarArrayMapTool] = None
        self.polar_array_widget: Optional[PolarArrayCanvasWidget] = None
        self.divide_line_map_tool: Optional[CADDivideLineMapTool] = None
        self.divide_line_widget: Optional[DivideLineCanvasWidget] = None
        self.ortho_angles_map_tool: Optional[CADOrthoAnglesMapTool] = None
        self.ortho_angles_widget: Optional[OrthoAnglesCanvasWidget] = None
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
        self.explode_map_tool: Optional[ExplodeLineMapTool] = None
        self.explode_widget: Optional[ExplodeCanvasWidget] = None
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
        self.rotate_map_tool = RotateMapTool(
            self.canvas,
            self.rotation_widget,
            self.iface,
        )

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
        self.mirror_map_tool = MirrorMapTool(
            self.canvas,
            self.mirror_widget,
            self.iface,
        )

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
        self.scale_rotate_map_tool = ScaleRotateMapTool(
            self.canvas,
            self.scale_rotate_widget,
            self.iface,
        )

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
        self.edge_offset_map_tool = EdgeOffsetMapTool(
            self.canvas,
            self.edge_offset_widget,
            self.iface,
        )

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
        self.clean_duplicates_map_tool = CleanDuplicateNodesMapTool(self.canvas, self.iface)

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

        # 7.8. Create interactive CAD Explode Line Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.explode_widget = ExplodeCanvasWidget(self.canvas)
        self.explode_widget.hide()
        self.explode_map_tool = ExplodeLineMapTool(self.canvas, self.explode_widget, self.iface)

        explode_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionExplodeLine.svg")
        self.explode_action = QAction(
            QIcon(explode_icon_path),
            self.tr("CAD Розбиття лінії (Explode)"),
            self.iface.mainWindow(),
        )
        self.explode_action.setCheckable(True)
        self.explode_action.setObjectName("actionExplodeLineCAD")
        self.explode_action.setToolTip(self.tr("Інтерактивний CAD інструмент розбиття ліній на окремі сегменти або складові частини (multipart)"))
        self.explode_action.triggered.connect(self.toggle_explode_tool)

        # 7.85. Create interactive CAD Divide / Measure Line Map Tool
        self.divide_line_widget = DivideLineCanvasWidget(self.canvas)
        self.divide_line_widget.hide()
        self.divide_line_map_tool = CADDivideLineMapTool(self.canvas, self.divide_line_widget, self.iface)

        divide_line_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionDivideLine.svg")
        self.divide_line_action = QAction(
            QIcon(divide_line_icon_path),
            self.tr("CAD Поділ лінії (Divide / Measure Line)"),
            self.iface.mainWindow(),
        )
        self.divide_line_action.setCheckable(True)
        self.divide_line_action.setObjectName("actionDivideLineCAD")
        self.divide_line_action.setToolTip(self.tr("Інтерактивний CAD поділ ліній на рівні частини або за фіксованим кроком довжини"))
        self.divide_line_action.triggered.connect(self.toggle_divide_line_tool)

        # 7.9. Create interactive CAD Polar (Circular) Array Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.polar_array_widget = PolarArrayCanvasWidget(self.canvas)
        self.polar_array_widget.hide()
        self.polar_array_map_tool = CADPolarArrayMapTool(self.canvas, self.polar_array_widget, self.iface)

        polar_array_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionPolarArray.svg")
        self.polar_array_action = QAction(
            QIcon(polar_array_icon_path),
            self.tr("CAD Полярний масив (Polar Array)"),
            self.iface.mainWindow(),
        )
        self.polar_array_action.setCheckable(True)
        self.polar_array_action.setObjectName("actionPolarArrayCAD")
        self.polar_array_action.setToolTip(self.tr("Створення кругового (полярного) масиву копій виділених об'єктів навколо центру"))
        self.polar_array_action.triggered.connect(self.toggle_polar_array_tool)

        # 7.95. Create interactive CAD Ortho Angles Map Tool (available in QGIS 3.x and QGIS 4.x)
        self.ortho_angles_widget = OrthoAnglesCanvasWidget(self.canvas)
        self.ortho_angles_widget.hide()
        self.ortho_angles_map_tool = CADOrthoAnglesMapTool(self.canvas, self.ortho_angles_widget, self.iface)

        ortho_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionOrthoAngles.svg")
        self.ortho_angles_action = QAction(
            QIcon(ortho_icon_path),
            self.tr("CAD Ортогоналізація кутів (Ortho Angles)"),
            self.iface.mainWindow(),
        )
        self.ortho_angles_action.setCheckable(True)
        self.ortho_angles_action.setObjectName("actionOrthoAnglesCAD")
        self.ortho_angles_action.setToolTip(self.tr("Інтерактивне вирівнювання кутів будівель і полігонів до прямих кутів (90°) за опорним фасадом"))
        self.ortho_angles_action.triggered.connect(self.toggle_ortho_angles_tool)

        adv_tb = self.iface.advancedDigitizeToolBar()

        # 8. Create interactive Fillet / Chamfer and Array MapTools ONLY in QGIS 3.x (native in QGIS 4.0+)
        if not self.is_qgis_4():
            # 8.1. Fillet / Chamfer Tool
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

            # 8.2. Copy Features in an Array Tool (Backport for QGIS 3.16 - 3.44)
            self.array_widget = ArrayCanvasWidget(self.canvas)
            self.array_widget.hide()
            self.array_map_tool = CADArrayMapTool(self.canvas, self.array_widget, self.iface)

            array_icon_path = os.path.join(self.plugin_dir, "resources", "icons", "mActionFeatureArrayPolygon.svg")
            self.array_action = QAction(
                QIcon(array_icon_path),
                self.tr("CAD Масив об'єктів (Copy in Array)"),
                self.iface.mainWindow(),
            )
            self.array_action.setCheckable(True)
            self.array_action.setObjectName("actionFeatureArrayCAD")
            self.array_action.setToolTip(self.tr("Створення масиву копій виділених об'єктів уздовж напрямної лінії"))
            self.array_action.triggered.connect(self.toggle_array_tool)

            if adv_tb:
                move_copy_act = None
                for act in adv_tb.actions():
                    name_lower = act.objectName().lower()
                    if "movefeaturecopy" in name_lower or act.objectName() == "mActionMoveFeatureCopy":
                        move_copy_act = act
                        break
                    if move_copy_act is None and ("movefeature" in name_lower or act.objectName() == "mActionMoveFeature"):
                        move_copy_act = act

                actions_now = adv_tb.actions()
                if move_copy_act and move_copy_act in actions_now:
                    try:
                        idx = actions_now.index(move_copy_act)
                        if idx + 1 < len(actions_now):
                            adv_tb.insertAction(actions_now[idx + 1], self.array_action)
                        else:
                            adv_tb.addAction(self.array_action)
                    except (ValueError, IndexError):
                        adv_tb.addAction(self.array_action)
                elif len(actions_now) >= 3:
                    adv_tb.insertAction(actions_now[2], self.array_action)
                else:
                    adv_tb.addAction(self.array_action)
            else:
                self.iface.addVectorToolBarIcon(self.array_action)
            self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.array_action)

        # 9. Helper functions for inserting actions relative to standard QGIS actions
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

        def _insert_before_action(target_act, action_to_insert):
            if not adv_tb or not action_to_insert:
                return
            actions_now = adv_tb.actions()
            if target_act and target_act in actions_now:
                try:
                    adv_tb.insertAction(target_act, action_to_insert)
                    return
                except (ValueError, IndexError):
                    pass
            adv_tb.addAction(action_to_insert)

        # 10. Position toolbar actions according to standard CAD workflow
        if adv_tb:
            # 10.1. Polar array tool: після linear array_action, або перед rotate_action
            if self.array_action:
                _insert_after_action(self.array_action, self.polar_array_action)
            else:
                _rotate_ref = _find_adv_action(lambda nl, n: "rotatefeature" in nl or n == "mActionRotateFeature" or "rotate" in nl)
                _insert_before_action(_rotate_ref or self.rotate_action, self.polar_array_action)

            # 10.2. Fillet & Chamfer group: Anchor (Fillet) -> restore_action -> batch_action -> two_line_action (Join lines)
            anchor_act = self.action
            if not anchor_act:
                anchor_act = _find_adv_action(lambda nl, n: "chamfer" in nl or "fillet" in nl)

            _insert_after_action(anchor_act, self.restore_action)
            _insert_after_action(self.restore_action, self.batch_action)
            # кнопка join two lines with fillet/chamfer після batch fillet/chamfer
            _insert_after_action(self.batch_action, self.two_line_action)

            # 10.3. Rotate tool: after system rotate feature
            rotate_act = _find_adv_action(lambda nl, n: "rotatefeature" in nl or n == "mActionRotateFeature" or "rotate" in nl)
            _insert_after_action(rotate_act, self.rotate_action)

            # 10.4. Scale and Rotate tool: після системного scale feature
            scale_act = _find_adv_action(lambda nl, n: "scalefeature" in nl or n == "mActionScaleFeature" or "scale" in nl)
            _insert_after_action(scale_act, self.scale_rotate_action)

            # 10.5. Mirror tool: перед системною simplify feature
            simplify_act = _find_adv_action(lambda nl, n: "simplifyfeature" in nl or n == "mActionSimplifyFeature" or "simplify" in nl)
            _insert_before_action(simplify_act, self.mirror_action)

            # 10.6. Edge buffer (Offset) tool: після системного offset curve
            offset_act = _find_adv_action(lambda nl, n: "offsetcurve" in nl or n == "mActionOffsetCurve" or "offset" in nl)
            _insert_after_action(offset_act, self.edge_offset_action)

            # 10.7. Split lines (Explode) and Divide line tools: після стандартної trim/extend feature
            trim_extend_act = _find_adv_action(lambda nl, n: "trimextend" in nl or n == "mActionTrimExtend" or "trim" in nl or "extend" in nl)
            _insert_after_action(trim_extend_act, self.explode_action)
            _insert_after_action(self.explode_action, self.divide_line_action)

            # 10.8. Ortho Angles tool: перед clean duplicate nodes
            _insert_after_action(self.divide_line_action, self.ortho_angles_action)

            # 10.9. Clean and repair tool: в кінець тулбара
            adv_tb.addAction(self.clean_duplicates_action)
        else:
            self.iface.addVectorToolBarIcon(self.polar_array_action)
            self.iface.addVectorToolBarIcon(self.restore_action)
            self.iface.addVectorToolBarIcon(self.batch_action)
            self.iface.addVectorToolBarIcon(self.two_line_action)
            self.iface.addVectorToolBarIcon(self.rotate_action)
            self.iface.addVectorToolBarIcon(self.scale_rotate_action)
            self.iface.addVectorToolBarIcon(self.mirror_action)
            self.iface.addVectorToolBarIcon(self.edge_offset_action)
            self.iface.addVectorToolBarIcon(self.explode_action)
            self.iface.addVectorToolBarIcon(self.divide_line_action)
            self.iface.addVectorToolBarIcon(self.ortho_angles_action)
            self.iface.addVectorToolBarIcon(self.clean_duplicates_action)

        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.polar_array_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.restore_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.batch_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.two_line_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.rotate_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.scale_rotate_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.mirror_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.edge_offset_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.explode_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.divide_line_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.ortho_angles_action)
        self.iface.addPluginToVectorMenu(self.tr("Fillet & Chamfer"), self.clean_duplicates_action)

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

        # 2.5. Clean up array action
        if self.array_action:
            try:
                self.array_action.triggered.disconnect(self.toggle_array_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.array_action)
            self.iface.removeVectorToolBarIcon(self.array_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.array_action)
            self.array_action.setParent(None)
            self.array_action.deleteLater()
            self.array_action = None

        # 2.6. Clean up polar array action
        if self.polar_array_action:
            try:
                self.polar_array_action.triggered.disconnect(self.toggle_polar_array_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.polar_array_action)
            self.iface.removeVectorToolBarIcon(self.polar_array_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.polar_array_action)
            self.polar_array_action.setParent(None)
            self.polar_array_action.deleteLater()
            self.polar_array_action = None

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

        # 5.8. Clean up explode action
        if self.explode_action:
            try:
                self.explode_action.triggered.disconnect(self.toggle_explode_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.explode_action)
            self.iface.removeVectorToolBarIcon(self.explode_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.explode_action)
            self.explode_action.setParent(None)
            self.explode_action.deleteLater()
            self.explode_action = None

        # 5.9. Clean up divide line action
        if self.divide_line_action:
            try:
                self.divide_line_action.triggered.disconnect(self.toggle_divide_line_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.divide_line_action)
            self.iface.removeVectorToolBarIcon(self.divide_line_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.divide_line_action)
            self.divide_line_action.setParent(None)
            self.divide_line_action.deleteLater()
            self.divide_line_action = None

        # 5.95. Clean up ortho angles action
        if self.ortho_angles_action:
            try:
                self.ortho_angles_action.triggered.disconnect(self.toggle_ortho_angles_tool)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            if self.iface.advancedDigitizeToolBar():
                self.iface.advancedDigitizeToolBar().removeAction(self.ortho_angles_action)
            self.iface.removeVectorToolBarIcon(self.ortho_angles_action)
            self.iface.removePluginVectorMenu(self.tr("Fillet & Chamfer"), self.ortho_angles_action)
            self.ortho_angles_action.setParent(None)
            self.ortho_angles_action.deleteLater()
            self.ortho_angles_action = None

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

        if self.array_map_tool:
            if self.canvas and self.canvas.mapTool() == self.array_map_tool:
                self.canvas.unsetMapTool(self.array_map_tool)
            if hasattr(self.array_map_tool, "cleanup"):
                self.array_map_tool.cleanup()
            else:
                self.array_map_tool.deactivate()
            self.array_map_tool.deleteLater()
            self.array_map_tool = None

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

        if self.explode_map_tool:
            if self.canvas and self.canvas.mapTool() == self.explode_map_tool:
                self.canvas.unsetMapTool(self.explode_map_tool)
            if hasattr(self.explode_map_tool, "cleanup"):
                self.explode_map_tool.cleanup()
            else:
                self.explode_map_tool.deactivate()
            self.explode_map_tool.deleteLater()
            self.explode_map_tool = None

        if self.divide_line_map_tool:
            if self.canvas and self.canvas.mapTool() == self.divide_line_map_tool:
                self.canvas.unsetMapTool(self.divide_line_map_tool)
            if hasattr(self.divide_line_map_tool, "cleanup"):
                self.divide_line_map_tool.cleanup()
            else:
                self.divide_line_map_tool.deactivate()
            self.divide_line_map_tool.deleteLater()
            self.divide_line_map_tool = None

        if self.polar_array_map_tool:
            if self.canvas and self.canvas.mapTool() == self.polar_array_map_tool:
                self.canvas.unsetMapTool(self.polar_array_map_tool)
            if hasattr(self.polar_array_map_tool, "cleanup"):
                self.polar_array_map_tool.cleanup()
            else:
                self.polar_array_map_tool.deactivate()
            self.polar_array_map_tool.deleteLater()
            self.polar_array_map_tool = None

        if self.ortho_angles_map_tool:
            if self.canvas and self.canvas.mapTool() == self.ortho_angles_map_tool:
                self.canvas.unsetMapTool(self.ortho_angles_map_tool)
            if hasattr(self.ortho_angles_map_tool, "cleanup"):
                self.ortho_angles_map_tool.cleanup()
            else:
                self.ortho_angles_map_tool.deactivate()
            self.ortho_angles_map_tool.deleteLater()
            self.ortho_angles_map_tool = None

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

        if self.explode_widget:
            try:
                self.canvas.removeEventFilter(self.explode_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.explode_widget.hide()
            self.explode_widget.setParent(None)
            self.explode_widget.deleteLater()
            self.explode_widget = None

        if self.divide_line_widget:
            try:
                self.canvas.removeEventFilter(self.divide_line_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.divide_line_widget.hide()
            self.divide_line_widget.setParent(None)
            self.divide_line_widget.deleteLater()
            self.divide_line_widget = None

        if self.array_widget:
            self.array_widget.hide()
            self.array_widget.setParent(None)
            self.array_widget.deleteLater()
            self.array_widget = None

        if self.polar_array_widget:
            try:
                self.canvas.removeEventFilter(self.polar_array_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.polar_array_widget.hide()
            self.polar_array_widget.setParent(None)
            self.polar_array_widget.deleteLater()
            self.polar_array_widget = None

        if self.ortho_angles_widget:
            try:
                self.canvas.removeEventFilter(self.ortho_angles_widget)
            except (TypeError, RuntimeError):
                pass  # nosec B110
            self.ortho_angles_widget.hide()
            self.ortho_angles_widget.setParent(None)
            self.ortho_angles_widget.deleteLater()
            self.ortho_angles_widget = None

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

    def toggle_array_tool(self, checked: bool):
        if checked:
            if self.array_map_tool:
                self.canvas.setMapTool(self.array_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.array_map_tool:
                self.canvas.unsetMapTool(self.array_map_tool)

    def toggle_polar_array_tool(self, checked: bool):
        if checked:
            if self.polar_array_map_tool:
                self.canvas.setMapTool(self.polar_array_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.polar_array_map_tool:
                self.canvas.unsetMapTool(self.polar_array_map_tool)

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

    def toggle_explode_tool(self, checked: bool):
        if checked:
            if self.explode_map_tool:
                self.canvas.setMapTool(self.explode_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.explode_map_tool:
                self.canvas.unsetMapTool(self.explode_map_tool)

    def toggle_divide_line_tool(self, checked: bool):
        if checked:
            if self.divide_line_map_tool:
                self.canvas.setMapTool(self.divide_line_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.divide_line_map_tool:
                self.canvas.unsetMapTool(self.divide_line_map_tool)

    def toggle_ortho_angles_tool(self, checked: bool):
        if checked:
            if self.ortho_angles_map_tool:
                self.canvas.setMapTool(self.ortho_angles_map_tool)
        else:
            if self.canvas and self.canvas.mapTool() == self.ortho_angles_map_tool:
                self.canvas.unsetMapTool(self.ortho_angles_map_tool)

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

        if self.explode_action:
            is_explode_active = tool == self.explode_map_tool
            self.explode_action.setChecked(is_explode_active)
            if not is_explode_active and self.explode_widget:
                self.explode_widget.hide()

        if self.divide_line_action:
            is_divide_active = tool == self.divide_line_map_tool
            self.divide_line_action.setChecked(is_divide_active)
            if not is_divide_active and self.divide_line_widget:
                self.divide_line_widget.hide()

        if self.array_action:
            is_array_active = tool == self.array_map_tool
            self.array_action.setChecked(is_array_active)
            if not is_array_active and self.array_widget:
                self.array_widget.hide()

        if self.polar_array_action:
            is_polar_active = tool == self.polar_array_map_tool
            self.polar_array_action.setChecked(is_polar_active)
            if not is_polar_active and self.polar_array_widget:
                self.polar_array_widget.hide()

        if self.ortho_angles_action:
            is_oa_active = tool == self.ortho_angles_map_tool
            self.ortho_angles_action.setChecked(is_oa_active)
            if not is_oa_active and self.ortho_angles_widget:
                self.ortho_angles_widget.hide()

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
        is_spatial_vector = bool(is_vector and layer.isSpatial())
        is_editable = bool(is_supported_geom and layer.isEditable())
        is_array_editable = bool(is_spatial_vector and layer.isEditable())
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

        if is_vector and is_spatial_vector:
            if self.array_widget and hasattr(self.array_widget, "adapt_to_crs"):
                self.array_widget.adapt_to_crs(layer.crs())

        if is_vector and is_line_editable:
            if self.explode_widget:
                self.explode_widget.update_layer_capabilities(layer)
            if self.divide_line_widget and hasattr(self.divide_line_widget, "adapt_to_crs"):
                self.divide_line_widget.adapt_to_crs(layer.crs())

        if self.action:
            self.action.setEnabled(is_editable)
        if self.array_action:
            self.array_action.setEnabled(is_array_editable)
            if is_vector and is_spatial_vector:
                geom_type = layer.geometryType()
                if geom_type == QgsWkbTypes.GeometryType.PointGeometry:
                    icon_name = "mActionFeatureArrayPoint.svg"
                elif geom_type == QgsWkbTypes.GeometryType.LineGeometry:
                    icon_name = "mActionFeatureArrayLine.svg"
                else:
                    icon_name = "mActionFeatureArrayPolygon.svg"
                icon_path = os.path.join(self.plugin_dir, "resources", "icons", icon_name)
                if os.path.exists(icon_path):
                    self.array_action.setIcon(QIcon(icon_path))
        if self.polar_array_action:
            self.polar_array_action.setEnabled(is_array_editable)
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
        if self.explode_action:
            self.explode_action.setEnabled(is_line_editable)
        if self.divide_line_action:
            self.divide_line_action.setEnabled(is_line_editable)
        if self.ortho_angles_action:
            self.ortho_angles_action.setEnabled(is_editable)
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

            if self.ortho_angles_map_tool and self.canvas.mapTool() == self.ortho_angles_map_tool:
                self.canvas.unsetMapTool(self.ortho_angles_map_tool)
                if self.ortho_angles_widget:
                    self.ortho_angles_widget.hide()
                if self.ortho_angles_action:
                    self.ortho_angles_action.setChecked(False)

        if not is_line_editable and self.canvas:
            if self.explode_map_tool and self.canvas.mapTool() == self.explode_map_tool:
                self.canvas.unsetMapTool(self.explode_map_tool)
                if self.explode_widget:
                    self.explode_widget.hide()
                if self.explode_action:
                    self.explode_action.setChecked(False)

            if self.divide_line_map_tool and self.canvas.mapTool() == self.divide_line_map_tool:
                self.canvas.unsetMapTool(self.divide_line_map_tool)
                if self.divide_line_widget:
                    self.divide_line_widget.hide()
                if self.divide_line_action:
                    self.divide_line_action.setChecked(False)

        if not is_array_editable and self.canvas:
            if self.array_map_tool and self.canvas.mapTool() == self.array_map_tool:
                self.canvas.unsetMapTool(self.array_map_tool)
                if self.array_widget:
                    self.array_widget.hide()
                if self.array_action:
                    self.array_action.setChecked(False)

            if self.polar_array_map_tool and self.canvas.mapTool() == self.polar_array_map_tool:
                self.canvas.unsetMapTool(self.polar_array_map_tool)
                if self.polar_array_widget:
                    self.polar_array_widget.hide()
                if self.polar_array_action:
                    self.polar_array_action.setChecked(False)

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
            if new_geom and not new_geom.isEmpty():
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
        engine_mode = "chamfer" if mode == FilletSettingsWidget.MODE_CHAMFER else "fillet"

        return GeometryEngine.batch_apply_geometry(
            geom=geom,
            mode=engine_mode,
            radius=radius,
            segments_count=segments,
            dist1=d1,
            dist2=d2,
        )

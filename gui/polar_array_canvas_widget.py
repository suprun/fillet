# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Polar (Circular) Array tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

from enum import IntEnum
import os
from typing import List, Optional

from qgis.core import QgsCoordinateReferenceSystem, QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas, QgsSpinBox
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPixmap,
)
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class PolarArrayMode(IntEnum):
    """Modes of generating polar feature arrays around a center pivot."""
    CountAndFillAngle = 0
    StepAndFillAngle = 1
    CountAndStep = 2


class PolarArrayCanvasWidget(QFrame):
    """
    Floating CAD HUD widget pinned on the map canvas for CAD Polar Array tool.
    Provides controls for:
      - [x] Items Count
      - [x] Step Angle + Presets/History Menu
      - Fill Angle (Total span) + Lock Button
      - [x] Rotate Features
    """

    modeChanged = pyqtSignal(int)
    featureCountChanged = pyqtSignal(int)
    stepAngleChanged = pyqtSignal(float)
    fillAngleChanged = pyqtSignal(float)
    rotateFeaturesChanged = pyqtSignal(bool)
    fillAngleLockToggled = pyqtSignal(bool)
    stepAngleLockToggled = pyqtSignal(bool)
    commitRequested = pyqtSignal()
    resetRequested = pyqtSignal()

    STEP_SELECT = 1
    STEP_CENTER = 2
    STEP_BASE_RAY = 3
    STEP_ANGLE = 4

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: Optional[QgsMapCanvas] = None):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("PolarArrayCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_SELECT
        self._is_syncing_checkboxes = False
        self._is_loading = False

        # Persistent user-configured values (restored upon re-enabling checkboxes)
        self._stored_count: int = 4
        self._stored_step: float = 90.0

        self._init_ui()
        self._apply_style()

        if self.canvas is not None:
            self.canvas.installEventFilter(self)

    def _get_icon(self, name: str) -> QIcon:
        path = os.path.join(self._icons_dir, name)
        if os.path.exists(path):
            return QIcon(path)
        return QIcon()

    def _init_ui(self):
        sub_window = getattr(Qt.WindowType, "SubWindow", getattr(Qt, "SubWindow", 0))
        frameless = getattr(Qt.WindowType, "FramelessWindowHint", getattr(Qt, "FramelessWindowHint", 0))
        if sub_window or frameless:
            self.setWindowFlags(sub_window | frameless)
        wa_show = getattr(Qt.WidgetAttribute, "WA_ShowWithoutActivating", getattr(Qt, "WA_ShowWithoutActivating", None))
        if wa_show is not None:
            self.setAttribute(wa_show, True)
        self.setMinimumWidth(250)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(4)

        # 1. Header Label (Step prompt)
        self.lbl_step = QLabel(self.tr("2. Вкажіть центр обертання"), self)
        font = self.lbl_step.font()
        font.setBold(True)
        self.lbl_step.setFont(font)
        self.lbl_step.setAlignment(getattr(Qt.AlignmentFlag, "AlignCenter", getattr(Qt, "AlignCenter", None)))
        main_layout.addWidget(self.lbl_step)

        # 2. Grid for Checkboxes and Inputs (4 columns: Label, SpinBox, Lock Button, Menu Button)
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnMinimumWidth(0, 118)

        # Row 0: Items Count Checkbox + SpinBox
        self.chk_count = QCheckBox(self.tr("Кількість (Count):"), self)
        self.chk_count.setChecked(True)
        self.chk_count.setToolTip(self.tr("Фіксована кількість елементів у полярному масиві"))

        if hasattr(QgsSpinBox, "setMinimum"):
            self.spin_count = QgsSpinBox(self)
        else:
            self.spin_count = QSpinBox(self)
        self.spin_count.setRange(1, 99999)
        self.spin_count.setValue(4)
        self.spin_count.setSingleStep(1)
        if hasattr(self.spin_count, "setShowClearButton"):
            self.spin_count.setShowClearButton(False)

        grid.addWidget(self.chk_count, 0, 0)
        grid.addWidget(self.spin_count, 0, 1, 1, 3)

        instant_popup = getattr(getattr(QToolButton, "ToolButtonPopupMode", None), "InstantPopup", getattr(QToolButton, "InstantPopup", 2))

        # Row 1: Step Angle Checkbox + DoubleSpinBox + Lock Button + Presets/History Menu Button
        self.chk_step = QCheckBox(self.tr("Крок (Step angle):"), self)
        self.chk_step.setChecked(False)
        self.chk_step.setToolTip(self.tr("Фіксований кутовий крок між елементами масиву"))

        if hasattr(QgsDoubleSpinBox, "setMinimum"):
            self.spin_step = QgsDoubleSpinBox(self)
        else:
            self.spin_step = QDoubleSpinBox(self)
        self.spin_step.setRange(0.001, 360.0)
        self.spin_step.setValue(90.0)
        self.spin_step.setDecimals(2)
        self.spin_step.setSingleStep(5.0)
        self.spin_step.setSuffix("°")
        if hasattr(self.spin_step, "setShowClearButton"):
            self.spin_step.setShowClearButton(False)

        self.btn_lock_step_angle = QToolButton(self)
        self.btn_lock_step_angle.setCheckable(True)
        self.btn_lock_step_angle.setChecked(False)
        self.btn_lock_step_angle.setAutoRaise(True)
        self.btn_lock_step_angle.setToolTip(self.tr("Блокувати кутовий крок"))
        self.btn_lock_step_angle.toggled.connect(self._on_lock_step_angle_toggled)

        self.btn_step_menu = QToolButton(self)
        self.btn_step_menu.setAutoRaise(True)
        self.btn_step_menu.setPopupMode(instant_popup)
        self.btn_step_menu.setToolTip(self.tr("Вибрати стандартний кутовий крок або з історії"))
        self.btn_step_menu.setIcon(self._get_icon("mActionLink.svg"))
        self.step_menu = QMenu(self.btn_step_menu)
        self.btn_step_menu.setMenu(self.step_menu)
        self.step_menu.aboutToShow.connect(self._rebuild_step_menu)

        grid.addWidget(self.chk_step, 1, 0)
        grid.addWidget(self.spin_step, 1, 1)
        grid.addWidget(self.btn_lock_step_angle, 1, 2)
        grid.addWidget(self.btn_step_menu, 1, 3)

        # Row 2: Fill Angle Label + DoubleSpinBox + Lock Button + Presets/History Menu Button
        self.lbl_fill_angle = QLabel(self.tr("Кут (Fill angle):"), self)
        self.lbl_fill_angle.setToolTip(self.tr("Загальний кут заповнення полярного масиву (360° = повне коло)"))

        if hasattr(QgsDoubleSpinBox, "setMinimum"):
            self.spin_fill_angle = QgsDoubleSpinBox(self)
        else:
            self.spin_fill_angle = QDoubleSpinBox(self)
        self.spin_fill_angle.setRange(-360.0, 360.0)
        self.spin_fill_angle.setValue(360.0)
        self.spin_fill_angle.setDecimals(2)
        self.spin_fill_angle.setSingleStep(15.0)
        self.spin_fill_angle.setSuffix("°")
        if hasattr(self.spin_fill_angle, "setShowClearButton"):
            self.spin_fill_angle.setShowClearButton(False)

        self.btn_lock_fill_angle = QToolButton(self)
        self.btn_lock_fill_angle.setCheckable(True)
        self.btn_lock_fill_angle.setChecked(False)
        self.btn_lock_fill_angle.setAutoRaise(True)
        self.btn_lock_fill_angle.setToolTip(self.tr("Блокувати кут заповнення (фіксований сектор)"))
        self.btn_lock_fill_angle.toggled.connect(self._on_lock_fill_angle_toggled)

        self.btn_fill_angle_menu = QToolButton(self)
        self.btn_fill_angle_menu.setAutoRaise(True)
        self.btn_fill_angle_menu.setPopupMode(instant_popup)
        self.btn_fill_angle_menu.setToolTip(self.tr("Вибрати стандартний кут заповнення або з історії"))
        self.btn_fill_angle_menu.setIcon(self._get_icon("mActionLink.svg"))
        self.fill_angle_menu = QMenu(self.btn_fill_angle_menu)
        self.btn_fill_angle_menu.setMenu(self.fill_angle_menu)
        self.fill_angle_menu.aboutToShow.connect(self._rebuild_fill_angle_menu)

        grid.addWidget(self.lbl_fill_angle, 2, 0)
        grid.addWidget(self.spin_fill_angle, 2, 1)
        grid.addWidget(self.btn_lock_fill_angle, 2, 2)
        grid.addWidget(self.btn_fill_angle_menu, 2, 3)

        self._update_lock_icons()

        # Row 3: Rotate Features Checkbox
        self.chk_rotate_features = QCheckBox(self.tr("Обертати об'єкти (Rotate):"), self)
        self.chk_rotate_features.setChecked(True)
        self.chk_rotate_features.setToolTip(self.tr("Якщо увімкнено, кожна копія повертається за рухом кола; якщо вимкнено — зберігає вихідний азимут"))
        grid.addWidget(self.chk_rotate_features, 3, 0, 1, 4)

        main_layout.addLayout(grid)

        # Cursors
        arrow_cursor = getattr(Qt.CursorShape, "ArrowCursor", getattr(Qt, "ArrowCursor", None))
        ibeam_cursor = getattr(Qt.CursorShape, "IBeamCursor", getattr(Qt, "IBeamCursor", None))
        if arrow_cursor is not None:
            self.setCursor(QCursor(arrow_cursor))
            self.chk_count.setCursor(QCursor(arrow_cursor))
            self.spin_count.setCursor(QCursor(arrow_cursor))
            self.chk_step.setCursor(QCursor(arrow_cursor))
            self.spin_step.setCursor(QCursor(arrow_cursor))
            self.spin_fill_angle.setCursor(QCursor(arrow_cursor))
        # Event filters
        self.installEventFilter(self)
        self.spin_count.installEventFilter(self)
        self.spin_step.installEventFilter(self)
        self.spin_fill_angle.installEventFilter(self)
        if hasattr(self.spin_step, "lineEdit") and self.spin_step.lineEdit() and ibeam_cursor is not None:
            self.spin_step.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_step.lineEdit().installEventFilter(self)
        if hasattr(self.spin_count, "lineEdit") and self.spin_count.lineEdit() and ibeam_cursor is not None:
            self.spin_count.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_count.lineEdit().installEventFilter(self)
        if hasattr(self.spin_fill_angle, "lineEdit") and self.spin_fill_angle.lineEdit() and ibeam_cursor is not None:
            self.spin_fill_angle.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_fill_angle.lineEdit().installEventFilter(self)

        # Connections
        self.chk_count.toggled.connect(self._on_count_checkbox_toggled)
        self.chk_step.toggled.connect(self._on_step_checkbox_toggled)
        self.spin_count.valueChanged.connect(self._on_count_value_changed)
        self.spin_step.valueChanged.connect(self._on_step_value_changed)
        self.spin_fill_angle.valueChanged.connect(self._on_fill_angle_changed)
        self.chk_rotate_features.toggled.connect(self._on_rotate_features_toggled)

        # Return pressed commit
        if hasattr(self.spin_count, "returnPressed"):
            self.spin_count.returnPressed.connect(self.commitRequested.emit)
        if hasattr(self.spin_step, "returnPressed"):
            self.spin_step.returnPressed.connect(self.commitRequested.emit)
        if hasattr(self.spin_fill_angle, "returnPressed"):
            self.spin_fill_angle.returnPressed.connect(self.commitRequested.emit)

        self._load_settings()
        self._sync_mode_and_states()

    def _apply_style(self):
        """Unified visual style matching Fillet & Chamfer, Rotate, and Mirror widgets."""
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_plain = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_plain is not None:
            self.setFrameShadow(shadow_plain)
        self.setAutoFillBackground(True)

    def _update_lock_icons(self):
        if hasattr(self, "btn_lock_step_angle"):
            if self.btn_lock_step_angle.isChecked():
                self.btn_lock_step_angle.setIcon(self._get_icon("locked.svg"))
            else:
                self.btn_lock_step_angle.setIcon(self._get_icon("unlocked.svg"))
        if hasattr(self, "btn_lock_fill_angle"):
            if self.btn_lock_fill_angle.isChecked():
                self.btn_lock_fill_angle.setIcon(self._get_icon("locked.svg"))
            else:
                self.btn_lock_fill_angle.setIcon(self._get_icon("unlocked.svg"))

    def _on_lock_step_angle_toggled(self, checked: bool):
        self._update_lock_icons()
        self._save_settings()
        self.stepAngleLockToggled.emit(checked)

    def _on_lock_fill_angle_toggled(self, checked: bool):
        self._update_lock_icons()
        self._save_settings()
        self.fillAngleLockToggled.emit(checked)

    def _rebuild_step_menu(self):
        self.step_menu.clear()

        # Presets section
        presets_title = self.step_menu.addAction(self.tr("Стандартні кути:"))
        presets_title.setEnabled(False)

        presets = [15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 180.0]
        for p in presets:
            act = self.step_menu.addAction(f"{p:g}°")
            act.triggered.connect(lambda checked, val=p: self._on_step_preset_selected(val))

        # Recent values section
        recent = self._get_recent_steps()
        filtered_recent = [r for r in recent if r not in presets]
        if filtered_recent:
            self.step_menu.addSeparator()
            recent_title = self.step_menu.addAction(self.tr("Останні значення:"))
            recent_title.setEnabled(False)
            for r in filtered_recent:
                act = self.step_menu.addAction(f"{r:g}°")
                act.triggered.connect(lambda checked, val=r: self._on_step_preset_selected(val))

    def _on_step_preset_selected(self, val: float):
        self.chk_step.setChecked(True)
        self.spin_step.setValue(val)
        self.add_recent_step(val)
        self.stepAngleChanged.emit(val)

    def add_recent_step(self, val: float):
        recent = self._get_recent_steps()
        if val in recent:
            recent.remove(val)
        recent.insert(0, val)
        recent = recent[:5]
        settings = QgsSettings()
        settings.setValue("Fillet/PolarArrayRecentSteps", [str(v) for v in recent])

    def _get_recent_steps(self) -> List[float]:
        settings = QgsSettings()
        raw = settings.value("Fillet/PolarArrayRecentSteps", [], type=list)
        result = []
        if isinstance(raw, list):
            for item in raw:
                try:
                    result.append(float(item))
                except (ValueError, TypeError):
                    pass
        return result

    def _rebuild_fill_angle_menu(self):
        self.fill_angle_menu.clear()

        # Presets section
        presets_title = self.fill_angle_menu.addAction(self.tr("Стандартні кути:"))
        presets_title.setEnabled(False)

        presets = [360.0, 270.0, 180.0, 120.0, 90.0, 60.0, 45.0, 30.0]
        for p in presets:
            label = f"{p:g}°"
            if abs(p - 360.0) < 1e-4:
                label += f" ({self.tr('Повне коло')})"
            elif abs(p - 180.0) < 1e-4:
                label += f" ({self.tr('Півколо')})"
            elif abs(p - 90.0) < 1e-4:
                label += f" ({self.tr('Чверть')})"
            act = self.fill_angle_menu.addAction(label)
            act.triggered.connect(lambda checked, val=p: self._on_fill_angle_preset_selected(val))

        # Recent values section
        recent = self._get_recent_fill_angles()
        filtered_recent = [r for r in recent if r not in presets]
        if filtered_recent:
            self.fill_angle_menu.addSeparator()
            recent_title = self.fill_angle_menu.addAction(self.tr("Останні значення:"))
            recent_title.setEnabled(False)
            for r in filtered_recent:
                act = self.fill_angle_menu.addAction(f"{r:g}°")
                act.triggered.connect(lambda checked, val=r: self._on_fill_angle_preset_selected(val))

    def _on_fill_angle_preset_selected(self, val: float):
        self.spin_fill_angle.setValue(val)
        self.add_recent_fill_angle(val)
        self.fillAngleChanged.emit(val)

    def add_recent_fill_angle(self, val: float):
        recent = self._get_recent_fill_angles()
        if val in recent:
            recent.remove(val)
        recent.insert(0, val)
        recent = recent[:5]
        settings = QgsSettings()
        settings.setValue("Fillet/PolarArrayRecentFillAngles", [str(v) for v in recent])

    def _get_recent_fill_angles(self) -> List[float]:
        settings = QgsSettings()
        raw = settings.value("Fillet/PolarArrayRecentFillAngles", [], type=list)
        result = []
        if isinstance(raw, list):
            for item in raw:
                try:
                    result.append(float(item))
                except (ValueError, TypeError):
                    pass
        return result

    def _load_settings(self):
        self._is_loading = True
        settings = QgsSettings()
        mode_val = settings.value("Fillet/PolarArrayMode", int(PolarArrayMode.CountAndFillAngle), type=int)
        count_val = settings.value("Fillet/PolarArrayCount", 4, type=int)
        step_val = settings.value("Fillet/PolarArrayStepAngle", 90.0, type=float)
        fill_val = settings.value("Fillet/PolarArrayFillAngle", 360.0, type=float)
        rotate_val = settings.value("Fillet/PolarArrayRotateFeatures", True, type=bool)
        step_locked_val = settings.value("Fillet/PolarArrayStepAngleLocked", False, type=bool)
        fill_locked_val = settings.value("Fillet/PolarArrayFillAngleLocked", False, type=bool)

        self._stored_count = max(1, count_val)
        self._stored_step = max(0.001, step_val)

        self.spin_count.setValue(self._stored_count)
        self.spin_step.setValue(self._stored_step)
        self.spin_fill_angle.setValue(fill_val)
        self.chk_rotate_features.setChecked(rotate_val)
        self.btn_lock_step_angle.setChecked(step_locked_val)
        self.btn_lock_fill_angle.setChecked(fill_locked_val)
        self._update_lock_icons()

        if mode_val == PolarArrayMode.StepAndFillAngle:
            self.chk_count.setChecked(False)
            self.chk_step.setChecked(True)
        elif mode_val == PolarArrayMode.CountAndStep:
            self.chk_count.setChecked(True)
            self.chk_step.setChecked(True)
        else:
            self.chk_count.setChecked(True)
            self.chk_step.setChecked(False)

        self._is_loading = False

    def _save_settings(self):
        if self._is_loading:
            return
        settings = QgsSettings()
        settings.setValue("Fillet/PolarArrayMode", int(self.mode))
        settings.setValue("Fillet/PolarArrayCount", int(self.spin_count.value()))
        settings.setValue("Fillet/PolarArrayStepAngle", float(self.spin_step.value()))
        settings.setValue("Fillet/PolarArrayFillAngle", float(self.spin_fill_angle.value()))
        settings.setValue("Fillet/PolarArrayRotateFeatures", bool(self.chk_rotate_features.isChecked()))
        settings.setValue("Fillet/PolarArrayStepAngleLocked", bool(self.btn_lock_step_angle.isChecked()))
        settings.setValue("Fillet/PolarArrayFillAngleLocked", bool(self.btn_lock_fill_angle.isChecked()))

    def _on_count_checkbox_toggled(self, checked: bool):
        if self._is_syncing_checkboxes:
            return
        # Mutual exclusion guard: At least one must be checked
        if not checked and not self.chk_step.isChecked():
            self._is_syncing_checkboxes = True
            self.chk_step.setChecked(True)
            self._is_syncing_checkboxes = False
        self._sync_mode_and_states()

    def _on_step_checkbox_toggled(self, checked: bool):
        if self._is_syncing_checkboxes:
            return
        # Mutual exclusion guard: At least one must be checked
        if not checked and not self.chk_count.isChecked():
            self._is_syncing_checkboxes = True
            self.chk_count.setChecked(True)
            self._is_syncing_checkboxes = False
        self._sync_mode_and_states()

    def _sync_mode_and_states(self):
        count_checked = self.chk_count.isChecked()
        step_checked = self.chk_step.isChecked()

        self.spin_count.setEnabled(count_checked)
        self.spin_step.setEnabled(step_checked)

        if count_checked:
            self.spin_count.setValue(self._stored_count)
            self.featureCountChanged.emit(self._stored_count)

        if step_checked:
            self.spin_step.setValue(self._stored_step)
            self.stepAngleChanged.emit(self._stored_step)

        self.modeChanged.emit(int(self.mode))
        self._save_settings()

    def _on_count_value_changed(self, val: int):
        if self.chk_count.isChecked():
            self._stored_count = val
            self._save_settings()
            self.featureCountChanged.emit(val)

    def _on_step_value_changed(self, val: float):
        if self.chk_step.isChecked():
            self._stored_step = val
            self.add_recent_step(val)
            self._save_settings()
            self.stepAngleChanged.emit(val)

    def _on_fill_angle_changed(self, val: float):
        self.add_recent_fill_angle(val)
        self._save_settings()
        self.fillAngleChanged.emit(val)

    def _on_rotate_features_toggled(self, val: bool):
        self._save_settings()
        self.rotateFeaturesChanged.emit(val)

    @property
    def mode(self) -> PolarArrayMode:
        count_checked = self.chk_count.isChecked()
        step_checked = self.chk_step.isChecked()
        if count_checked and step_checked:
            return PolarArrayMode.CountAndStep
        elif step_checked:
            return PolarArrayMode.StepAndFillAngle
        else:
            return PolarArrayMode.CountAndFillAngle

    @property
    def feature_count(self) -> int:
        return self.spin_count.value()

    @property
    def step_angle(self) -> float:
        return self.spin_step.value()

    @property
    def fill_angle(self) -> float:
        return self.spin_fill_angle.value()

    @property
    def is_step_angle_locked(self) -> bool:
        return self.btn_lock_step_angle.isChecked() if hasattr(self, "btn_lock_step_angle") else False

    @property
    def is_fill_angle_locked(self) -> bool:
        return self.btn_lock_fill_angle.isChecked() if hasattr(self, "btn_lock_fill_angle") else False

    @property
    def rotate_features(self) -> bool:
        return self.chk_rotate_features.isChecked()

    def set_calculated_count(self, val: int):
        """Displays real-time calculated count when count checkbox is disabled."""
        if not self.chk_count.isChecked():
            self.spin_count.blockSignals(True)
            self.spin_count.setValue(max(1, val))
            self.spin_count.blockSignals(False)

    def set_calculated_step_angle(self, val: float):
        """Displays real-time calculated step angle when step checkbox is disabled."""
        if not self.chk_step.isChecked() and not self.is_step_angle_locked:
            self.spin_step.blockSignals(True)
            self.spin_step.setValue(max(0.001, val))
            self.spin_step.blockSignals(False)

    def set_calculated_fill_angle(self, val: float):
        """Displays real-time calculated fill angle from mouse movement."""
        if not self.is_fill_angle_locked:
            self.spin_fill_angle.blockSignals(True)
            self.spin_fill_angle.setValue(val)
            self.spin_fill_angle.blockSignals(False)

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_SELECT:
            self.lbl_step.setText(self.tr("1. Оберіть об'єкт(и) для масиву"))
        elif step == self.STEP_CENTER:
            self.lbl_step.setText(self.tr("2. Вкажіть центр обертання"))
        elif step == self.STEP_BASE_RAY:
            self.lbl_step.setText(self.tr("3. Вкажіть базовий напрямок 0°"))
        elif step == self.STEP_ANGLE:
            self.lbl_step.setText(self.tr("4. Задайте кут або підтвердіть Enter"))
        self.reposition_to_default()

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas."""
        if self.canvas is None:
            return
        self.lbl_step.adjustSize()
        self.adjustSize()
        hint = self.sizeHint()
        lbl_hint = self.lbl_step.sizeHint()
        w = max(hint.width(), lbl_hint.width() + 20, 260)
        h = max(hint.height(), lbl_hint.height() + 16)
        self.resize(w, h)
        self.adjustSize()
        x = max(0, self.canvas.width() - self.width())
        y = 0
        self.move(x, y)

    def show_on_canvas(self):
        """Shows and repositions widget on canvas."""
        self.reposition_to_default()
        self.show()
        self.raise_()

    def eventFilter(self, obj, event):
        ev_type = event.type()
        resize_type = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", 14))
        key_press_type = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6))

        if obj == self.canvas and ev_type == resize_type:
            self.reposition_to_default()
        elif ev_type == key_press_type:
            key_int = int(event.key())
            key_escape = int(getattr(Qt.Key, "Key_Escape", 0x01000000))
            key_return = int(getattr(Qt.Key, "Key_Return", 0x01000004))
            key_enter = int(getattr(Qt.Key, "Key_Enter", 0x01000005))
            key_space = int(getattr(Qt.Key, "Key_Space", 0x20))

            if key_int in (0x01000000, key_escape):
                self.resetRequested.emit()
                return True
            if key_int in (0x01000004, 0x01000005, key_return, key_enter):
                self.commitRequested.emit()
                return True
            if key_int in (0x20, key_space):
                from qgis.PyQt.QtWidgets import QApplication
                focused = QApplication.focusWidget()
                step_line_edit = getattr(self.spin_step, "lineEdit", lambda: None)()
                if focused in (self.spin_step, step_line_edit):
                    self.btn_lock_step_angle.toggle()
                else:
                    self.btn_lock_fill_angle.toggle()
                return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        key_int = int(event.key())
        key_escape = int(getattr(Qt.Key, "Key_Escape", 0x01000000))
        key_return = int(getattr(Qt.Key, "Key_Return", 0x01000004))
        key_enter = int(getattr(Qt.Key, "Key_Enter", 0x01000005))
        key_space = int(getattr(Qt.Key, "Key_Space", 0x20))

        if key_int in (0x01000000, key_escape):
            self.resetRequested.emit()
            event.accept()
            return
        if key_int in (0x01000004, 0x01000005, key_return, key_enter):
            self.commitRequested.emit()
            event.accept()
            return
        if key_int in (0x20, key_space):
            from qgis.PyQt.QtWidgets import QApplication
            focused = QApplication.focusWidget()
            step_line_edit = getattr(self.spin_step, "lineEdit", lambda: None)()
            if focused in (self.spin_step, step_line_edit):
                self.btn_lock_step_angle.toggle()
            else:
                self.btn_lock_fill_angle.toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    def focus_count_input(self):
        self.spin_count.setFocus()
        self.spin_count.selectAll()

    def focus_step_input(self):
        self.spin_step.setFocus()
        self.spin_step.selectAll()

    def focus_fill_angle_input(self):
        self.spin_fill_angle.setFocus()
        self.spin_fill_angle.selectAll()

# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Edge Offset tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import os
from typing import Optional

from qgis.core import QgsCoordinateReferenceSystem, QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, QRegularExpression, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPixmap,
    QRegularExpressionValidator,
    QTransform,
)
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class EdgeOffsetCanvasWidget(QFrame):
    """Floating CAD HUD widget on the map canvas for interactive edge offset."""

    distanceChanged = pyqtSignal(float)
    modeChanged = pyqtSignal(str)
    distanceLockChanged = pyqtSignal(bool)
    copyModeChanged = pyqtSignal(bool)
    commitRequested = pyqtSignal()
    resetRequested = pyqtSignal()

    MODE_EXTEND = "extend"
    MODE_STEP = "step"

    STEP_SELECT_EDGE = 0
    STEP_ADJUST_OFFSET = 1

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("EdgeOffsetCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_SELECT_EDGE
        self._base_mode = self.MODE_EXTEND
        self._shift_pressed = False
        self._is_updating_shift_override = False
        self._is_loading = False

        self._init_ui()
        self._apply_style()
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
        self.setMinimumWidth(235)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Step indicator label for multi-step workflow (hidden by default, consistent with Fillet/Chamfer)
        self.lbl_step = QLabel(self)
        self.lbl_step.setWordWrap(False)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet("color: #1e3a8a; background-color: #dbeafe; border-radius: 4px; padding: 4px 8px;")
        self.lbl_step.hide()
        main_layout.addWidget(self.lbl_step)

        # Mode selection row on top (matching FilletCanvasWidget radio buttons)
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)

        self.radio_extend = QRadioButton(self.tr("Подовження (Extend)"), self)
        self.radio_extend.setChecked(True)

        self.radio_step = QRadioButton(self.tr("Сходинка (Step)"), self)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_extend)
        self.mode_group.addButton(self.radio_step)

        mode_layout.addWidget(self.radio_extend)
        mode_layout.addWidget(self.radio_step)
        mode_layout.addStretch()

        main_layout.addLayout(mode_layout)

        # Grid for Distance parameter
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnMinimumWidth(0, 95)

        # Row 0: Distance
        self.lbl_dist = QLabel(self.tr("Відстань:"), self)
        self.spin_distance = QgsDoubleSpinBox(self)
        self.spin_distance.setRange(0.0001, 1000000.0)
        self.spin_distance.setValue(1.0)
        self.spin_distance.setDecimals(3)
        self.spin_distance.setSingleStep(0.5)
        self.spin_distance.setShowClearButton(True)

        self.btn_lock_distance = QToolButton(self)
        self.btn_lock_distance.setCheckable(True)
        self.btn_lock_distance.setChecked(False)
        self.btn_lock_distance.setAutoRaise(True)
        self.btn_lock_distance.setToolTip(self.tr("Блокувати відстань / вільний розрахунок"))
        self._update_distance_lock_icon()
        self.btn_lock_distance.toggled.connect(self._on_distance_lock_toggled)

        grid.addWidget(self.lbl_dist, 0, 0)
        grid.addWidget(self.spin_distance, 0, 1)
        grid.addWidget(self.btn_lock_distance, 0, 2)

        main_layout.addLayout(grid)

        # Horizontal Separator
        self.sep_copy = QFrame(self)
        hline = getattr(QFrame.Shape, "HLine", getattr(QFrame, "HLine", None))
        sunken = getattr(QFrame.Shadow, "Sunken", getattr(QFrame, "Shadow", None))
        if hline is not None:
            self.sep_copy.setFrameShape(hline)
        if sunken is not None:
            self.sep_copy.setFrameShadow(sunken)
        main_layout.addWidget(self.sep_copy)

        # Checkbox: Save copy
        self.chk_copy = QCheckBox(self.tr("Зберегти копію (Copy)"), self)
        self.chk_copy.setToolTip(self.tr("Створити новий об'єкт зі зміщеним ребром замість модифікації оригінального"))
        self.chk_copy.setChecked(QgsSettings().value("plugins/fillet/edge_offset_copy_mode", False, type=bool))
        self.chk_copy.toggled.connect(self._on_copy_toggled)
        main_layout.addWidget(self.chk_copy)

        # Tab order
        s_dist = self.spin_distance.lineEdit() if hasattr(self.spin_distance, "lineEdit") and self.spin_distance.lineEdit() else self.spin_distance
        QWidget.setTabOrder(s_dist, self.btn_lock_distance)
        QWidget.setTabOrder(self.btn_lock_distance, self.radio_extend)
        QWidget.setTabOrder(self.radio_extend, self.radio_step)
        QWidget.setTabOrder(self.radio_step, self.chk_copy)

        # Connect signals
        self.spin_distance.valueChanged.connect(self.distanceChanged.emit)
        self.radio_extend.toggled.connect(self._on_radio_mode_toggled)
        self.radio_step.toggled.connect(self._on_radio_mode_toggled)

        # Enter in spinbox requests commit
        if hasattr(self.spin_distance, "lineEdit") and self.spin_distance.lineEdit():
            self.spin_distance.lineEdit().returnPressed.connect(self.commitRequested.emit)

        # Cursors
        arrow_cursor = getattr(Qt.CursorShape, "ArrowCursor", getattr(Qt, "ArrowCursor", None))
        ibeam_cursor = getattr(Qt.CursorShape, "IBeamCursor", getattr(Qt, "IBeamCursor", None))
        if arrow_cursor is not None:
            self.setCursor(QCursor(arrow_cursor))
            self.spin_distance.setCursor(QCursor(arrow_cursor))
            self.radio_extend.setCursor(QCursor(arrow_cursor))
            self.radio_step.setCursor(QCursor(arrow_cursor))
            self.btn_lock_distance.setCursor(QCursor(arrow_cursor))
            self.chk_copy.setCursor(QCursor(arrow_cursor))
        if hasattr(self.spin_distance, "lineEdit") and self.spin_distance.lineEdit() and ibeam_cursor is not None:
            self.spin_distance.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_distance.lineEdit().installEventFilter(self)

        self._configure_numeric_validators()
        self._load_settings()

    def _apply_style(self):
        """Unified visual style matching Fillet & Chamfer, Rotate, and Mirror widgets."""
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_plain = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_plain is not None:
            self.setFrameShadow(shadow_plain)
        self.setAutoFillBackground(True)

    def _update_distance_lock_icon(self):
        is_locked = self.btn_lock_distance.isChecked()
        icon = self._get_icon("locked.svg" if is_locked else "unlocked.svg")
        self.btn_lock_distance.setIcon(icon)

    def _on_distance_lock_toggled(self, checked: bool):
        self._update_distance_lock_icon()
        self.distanceLockChanged.emit(checked)
        self._save_settings()

    def _on_radio_mode_toggled(self):
        if self._is_updating_shift_override or self._is_loading:
            return
        mode = self.MODE_EXTEND if self.radio_extend.isChecked() else self.MODE_STEP
        self._base_mode = mode
        self.modeChanged.emit(mode)
        self._save_settings()

    def _on_copy_toggled(self, checked: bool):
        self.copyModeChanged.emit(checked)
        s = QgsSettings()
        s.setValue("plugins/fillet/edge_offset_copy_mode", checked)

    def _configure_numeric_validators(self):
        double_regex = QRegularExpression(r"^[0-9]*[.,]?[0-9]*$")
        if hasattr(self.spin_distance, "lineEdit") and self.spin_distance.lineEdit():
            val = QRegularExpressionValidator(double_regex, self.spin_distance.lineEdit())
            self.spin_distance.lineEdit().setValidator(val)

    def _load_settings(self):
        self._is_loading = True
        try:
            s = QgsSettings()
            self.spin_distance.setValue(float(s.value("plugins/fillet/edge_offset_distance", 1.0)))
            self.btn_lock_distance.setChecked(s.value("plugins/fillet/edge_offset_lock_dist", False, type=bool))
            self._base_mode = s.value("plugins/fillet/edge_offset_mode", self.MODE_EXTEND)
            if self._base_mode == self.MODE_STEP:
                self.radio_step.setChecked(True)
            else:
                self.radio_extend.setChecked(True)
            self._update_distance_lock_icon()
        finally:
            self._is_loading = False

    def _save_settings(self):
        if self._is_updating_shift_override or self._is_loading:
            return
        s = QgsSettings()
        s.setValue("plugins/fillet/edge_offset_distance", self.spin_distance.value())
        s.setValue("plugins/fillet/edge_offset_lock_dist", self.btn_lock_distance.isChecked())
        s.setValue("plugins/fillet/edge_offset_mode", self._base_mode)

    def set_step(self, step: int):
        """Updates step label text and style."""
        self._current_step = step
        if step == self.STEP_SELECT_EDGE:
            self.lbl_step.setText(self.tr("1. Вкажіть ребро (оберіть відрізок)"))
        elif step == self.STEP_ADJUST_OFFSET:
            self.lbl_step.setText(self.tr("2. Вкажіть зміщення або клікніть для підтвердження"))

    def set_shift_override(self, shift_pressed: bool):
        """Temporarily inverts mode between Extend and Step when Shift is held."""
        if self._shift_pressed == shift_pressed:
            return
        self._shift_pressed = shift_pressed

        target_mode = (
            (self.MODE_STEP if self._base_mode == self.MODE_EXTEND else self.MODE_EXTEND)
            if shift_pressed
            else self._base_mode
        )

        self._is_updating_shift_override = True
        try:
            if target_mode == self.MODE_STEP:
                self.radio_step.setChecked(True)
            else:
                self.radio_extend.setChecked(True)
        finally:
            self._is_updating_shift_override = False

        self.modeChanged.emit(target_mode)

    def get_effective_mode(self, shift_pressed: bool = False) -> str:
        """Returns the active mode considering Shift key inversion."""
        self.set_shift_override(shift_pressed)
        if shift_pressed:
            return self.MODE_STEP if self._base_mode == self.MODE_EXTEND else self.MODE_EXTEND
        return self._base_mode

    def adapt_to_crs(self, crs: QgsCoordinateReferenceSystem):
        """Adapts distance precision and step for Geographic (degrees) vs Metric CRS."""
        is_geo = crs.isGeographic() if crs and crs.isValid() else False
        if is_geo:
            self.spin_distance.setDecimals(6)
            self.spin_distance.setRange(1e-6, 180.0)
            self.spin_distance.setSingleStep(0.001)
            if self.spin_distance.value() > 1.0:
                self.spin_distance.setValue(0.01)
        else:
            self.spin_distance.setDecimals(3)
            self.spin_distance.setRange(0.0001, 1000000.0)
            self.spin_distance.setSingleStep(0.5)

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas without margin (matching toolkit standard)."""
        if not self.canvas:
            return
        self.adjustSize()
        self.resize(self.minimumSizeHint())
        self.adjustSize()
        x = max(0, self.canvas.width() - self.width())
        y = 0
        self.move(x, y)

    def show_on_canvas(self):
        """Displays and repositions the widget at the top-right corner."""
        self.show()
        self.raise_()
        self.reposition_to_default()

    def focus_primary_input(self):
        """Focuses and auto-selects distance spinbox."""
        self.spin_distance.setFocus()
        if hasattr(self.spin_distance, "lineEdit") and self.spin_distance.lineEdit():
            self.spin_distance.lineEdit().selectAll()

    def toggle_active_lock(self):
        """Toggles distance lock on Space bar press."""
        self.btn_lock_distance.setChecked(not self.btn_lock_distance.isChecked())

    @property
    def mode(self) -> str:
        return self.MODE_STEP if self.radio_step.isChecked() else self.MODE_EXTEND

    @mode.setter
    def mode(self, val: str):
        self._base_mode = val
        if val == self.MODE_STEP:
            self.radio_step.setChecked(True)
        else:
            self.radio_extend.setChecked(True)

    @property
    def distance(self) -> float:
        return self.spin_distance.value()

    def set_distance(self, val: float, block_signals: bool = False):
        if block_signals:
            self.spin_distance.blockSignals(True)
        self.spin_distance.setValue(val)
        if block_signals:
            self.spin_distance.blockSignals(False)

    @property
    def is_distance_locked(self) -> bool:
        return self.btn_lock_distance.isChecked()

    @property
    def copy_mode(self) -> bool:
        return self.chk_copy.isChecked()

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        evt_key_press = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None))
        evt_key_release = getattr(QEvent.Type, "KeyRelease", getattr(QEvent, "KeyRelease", None))

        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()

        elif event.type() == evt_key_press:
            key = event.key()
            key_shift = getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020))
            if key == key_shift:
                self.set_shift_override(True)

            key_tab = getattr(Qt.Key, "Key_Tab", getattr(Qt, "Key_Tab", 0x01000001))
            key_backtab = getattr(Qt.Key, "Key_Backtab", getattr(Qt, "Key_Backtab", 0x01000002))
            key_return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
            key_enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))
            key_space = getattr(Qt.Key, "Key_Space", getattr(Qt, "Key_Space", 0x20))

            if key in (key_return, key_enter):
                self.commitRequested.emit()
                return True

            if key == key_space:
                self.toggle_active_lock()
                return True

            if key == key_tab:
                self.focusNextChild()
                return True
            elif key == key_backtab:
                self.focusPreviousChild()
                return True

        elif event.type() == evt_key_release:
            key = event.key()
            key_shift = getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020))
            if key == key_shift:
                self.set_shift_override(False)

        return super().eventFilter(obj, event)

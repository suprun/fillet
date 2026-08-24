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
    QGraphicsDropShadowEffect,
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
        self.setMinimumWidth(250)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # Step indicator label
        self.lbl_step = QLabel(self)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet("color: #1e3a8a; background-color: #dbeafe; border-radius: 4px; padding: 3px 6px;")
        self.set_step(self.STEP_SELECT_EDGE)
        main_layout.addWidget(self.lbl_step)

        # Grid for Distance and Mode
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        # Row 0: Distance
        self.lbl_dist = QLabel(self.tr("Відстань:"), self)
        self.spin_distance = QgsDoubleSpinBox(self)
        self.spin_distance.setRange(0.0001, 1000000.0)
        self.spin_distance.setValue(1.0)
        self.spin_distance.setDecimals(3)
        self.spin_distance.setSingleStep(0.5)
        self.spin_distance.setShowClearButton(False)

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

        # Mode Selection Block (Extend vs Step)
        mode_box = QVBoxLayout()
        mode_box.setSpacing(2)
        mode_box.setContentsMargins(0, 0, 0, 0)

        self.lbl_mode_title = QLabel(self.tr("Режим зсуву:"), self)
        self.lbl_mode_title.setStyleSheet("font-size: 11px; color: #475569; font-weight: 500;")
        mode_box.addWidget(self.lbl_mode_title)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.setContentsMargins(0, 0, 0, 0)

        self.btn_group_mode = QButtonGroup(self)
        self.radio_extend = QRadioButton(self.tr("Подовження (Extend)"), self)
        self.radio_step = QRadioButton(self.tr("Сходинка (Step)"), self)
        self.radio_extend.setChecked(True)

        self.btn_group_mode.addButton(self.radio_extend)
        self.btn_group_mode.addButton(self.radio_step)

        mode_row.addWidget(self.radio_extend)
        mode_row.addWidget(self.radio_step)
        mode_row.addStretch()

        mode_box.addLayout(mode_row)
        main_layout.addLayout(mode_box)

        # Horizontal Separator
        self.sep_copy = QFrame(self)
        self.sep_copy.setFrameShape(QFrame.Shape.HLine if hasattr(QFrame, "Shape") else QFrame.HLine)
        self.sep_copy.setFrameShadow(QFrame.Shadow.Sunken if hasattr(QFrame, "Shadow") else QFrame.Sunken)
        self.sep_copy.setStyleSheet("margin-top: 2px; margin-bottom: 2px; color: #cbd5e1;")
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

        self._configure_numeric_validators()
        self._load_settings()

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#EdgeOffsetCanvasWidget {
                background-color: rgba(255, 255, 255, 242);
                border: 1px solid #94a3b8;
                border-radius: 8px;
            }
            QLabel {
                color: #1e293b;
                font-size: 11px;
                font-weight: 500;
            }
            QgsDoubleSpinBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 2px 4px;
                min-height: 22px;
                color: #0f172a;
                font-size: 11px;
            }
            QgsDoubleSpinBox:focus {
                border: 1.5px solid #2563eb;
                background-color: #eff6ff;
            }
            QToolButton {
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 2px;
                background: transparent;
            }
            QToolButton:hover {
                background-color: #e2e8f0;
                border-color: #cbd5e1;
            }
            QToolButton:checked {
                background-color: #fee2e2;
                border: 1px solid #ef4444;
            }
            QRadioButton, QCheckBox {
                font-size: 11px;
                color: #1e293b;
            }
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 3)
        self.setGraphicsEffect(shadow)

    def _update_distance_lock_icon(self):
        is_locked = self.btn_lock_distance.isChecked()
        icon = self._get_icon("locked.svg" if is_locked else "unlocked.svg")
        self.btn_lock_distance.setIcon(icon)

    def _on_distance_lock_toggled(self, checked: bool):
        self._update_distance_lock_icon()
        self.distanceLockChanged.emit(checked)
        self._save_settings()

    def _on_radio_mode_toggled(self):
        if self._is_updating_shift_override:
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
        s = QgsSettings()
        self.spin_distance.setValue(float(s.value("plugins/fillet/edge_offset_distance", 1.0)))
        self.btn_lock_distance.setChecked(s.value("plugins/fillet/edge_offset_lock_dist", False, type=bool))
        self._base_mode = s.value("plugins/fillet/edge_offset_mode", self.MODE_EXTEND)
        if self._base_mode == self.MODE_STEP:
            self.radio_step.setChecked(True)
        else:
            self.radio_extend.setChecked(True)
        self._update_distance_lock_icon()

    def _save_settings(self):
        if self._is_updating_shift_override:
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
        self.reposition_to_default()

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
        """Positions the widget at the top-left corner of the canvas with a standard margin."""
        if not self.canvas:
            return
        self.adjustSize()
        margin = 16
        self.move(margin, margin)

    def show_on_canvas(self):
        """Displays and repositions the widget."""
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

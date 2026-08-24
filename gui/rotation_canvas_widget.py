# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Rotation tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import os
from typing import Optional

from qgis.core import QgsSettings
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
    QComboBox,
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


class RotationCanvasWidget(QFrame):
    """Floating CAD HUD widget on the map canvas for interactive rotation."""

    angleChanged = pyqtSignal(float)
    commitRequested = pyqtSignal()
    resetRequested = pyqtSignal()
    copyModeChanged = pyqtSignal(bool)
    stepSnapChanged = pyqtSignal(float)

    STEP_PIVOT = 0
    STEP_REFERENCE = 1
    STEP_ROTATING = 2

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("RotationCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_PIVOT
        self._base_snap_mode = "free"  # "free" or "angle"
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
        self.setMinimumWidth(240)

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
        self.set_step(self.STEP_PIVOT)
        main_layout.addWidget(self.lbl_step)

        # Grid for Angle input and controls
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        # Row 0: Angle
        self.lbl_angle = QLabel(self.tr("Кут (Angle):"), self)
        self.spin_angle = QgsDoubleSpinBox(self)
        self.spin_angle.setRange(-360.0, 360.0)
        self.spin_angle.setValue(0.0)
        self.spin_angle.setDecimals(2)
        self.spin_angle.setSingleStep(5.0)
        self.spin_angle.setSuffix("°")
        self.spin_angle.setShowClearButton(False)

        self.btn_lock_angle = QToolButton(self)
        self.btn_lock_angle.setCheckable(True)
        self.btn_lock_angle.setChecked(False)
        self.btn_lock_angle.setAutoRaise(True)
        self.btn_lock_angle.setToolTip(self.tr("Блокувати кут / інтерактивне обертання"))
        self._update_lock_icon()
        self.btn_lock_angle.toggled.connect(self._update_lock_icon)

        grid.addWidget(self.lbl_angle, 0, 0)
        grid.addWidget(self.spin_angle, 0, 1)
        grid.addWidget(self.btn_lock_angle, 0, 2)

        # Row 1: Snapping Parameter Header
        self.lbl_snap = QLabel(self.tr("Крок кута:"), self)
        grid.addWidget(self.lbl_snap, 1, 0, 1, 3)

        # Row 2: Radio button free, radio button angle with short-widthed dropdown menu
        snap_layout = QHBoxLayout()
        snap_layout.setContentsMargins(0, 0, 0, 0)
        snap_layout.setSpacing(6)

        self.rb_snap_free = QRadioButton(self.tr("Вільний (Free)"), self)
        self.rb_snap_angle = QRadioButton(self.tr("Кут:"), self)
        self.combo_snap = QComboBox(self)
        self.combo_snap.setMaximumWidth(70)
        self.combo_snap.addItem("5°", 5.0)
        self.combo_snap.addItem("15°", 15.0)
        self.combo_snap.addItem("45°", 45.0)
        self.combo_snap.addItem("90°", 90.0)

        snap_layout.addWidget(self.rb_snap_free)
        snap_layout.addWidget(self.rb_snap_angle)
        snap_layout.addWidget(self.combo_snap)
        snap_layout.addStretch()

        grid.addLayout(snap_layout, 2, 0, 1, 3)

        self.bg_snap = QButtonGroup(self)
        self.bg_snap.addButton(self.rb_snap_free)
        self.bg_snap.addButton(self.rb_snap_angle)

        main_layout.addLayout(grid)

        # Checkbox: Copy original feature
        self.chk_copy = QCheckBox(self.tr("Зберегти копію (Copy)"), self)
        self.chk_copy.setToolTip(self.tr("Створює повернуту копію виділених об'єктів, залишаючи оригінал"))
        self.chk_copy.setChecked(False)
        self.chk_copy.toggled.connect(self.copyModeChanged.emit)
        main_layout.addWidget(self.chk_copy)

        # Cursors and filters
        arrow_cursor = getattr(Qt.CursorShape, "ArrowCursor", getattr(Qt, "ArrowCursor", None))
        ibeam_cursor = getattr(Qt.CursorShape, "IBeamCursor", getattr(Qt, "IBeamCursor", None))
        if arrow_cursor is not None:
            self.setCursor(QCursor(arrow_cursor))
            self.spin_angle.setCursor(QCursor(arrow_cursor))
            self.btn_lock_angle.setCursor(QCursor(arrow_cursor))
            self.rb_snap_free.setCursor(QCursor(arrow_cursor))
            self.rb_snap_angle.setCursor(QCursor(arrow_cursor))
            self.combo_snap.setCursor(QCursor(arrow_cursor))
            self.chk_copy.setCursor(QCursor(arrow_cursor))

        self.spin_angle.installEventFilter(self)
        if hasattr(self.spin_angle, "lineEdit") and self.spin_angle.lineEdit():
            if ibeam_cursor is not None:
                self.spin_angle.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_angle.lineEdit().installEventFilter(self)
            self.spin_angle.lineEdit().returnPressed.connect(self.commitRequested.emit)

        # Tab order
        target_spin = self.spin_angle.lineEdit() if hasattr(self.spin_angle, "lineEdit") and self.spin_angle.lineEdit() else self.spin_angle
        self.setTabOrder(target_spin, self.btn_lock_angle)
        self.setTabOrder(self.btn_lock_angle, self.rb_snap_free)
        self.setTabOrder(self.rb_snap_free, self.rb_snap_angle)
        self.setTabOrder(self.rb_snap_angle, self.combo_snap)
        self.setTabOrder(self.combo_snap, self.chk_copy)

        # Signal connections
        self.spin_angle.valueChanged.connect(self.angleChanged.emit)
        self.rb_snap_free.toggled.connect(self._on_snap_mode_toggled)
        self.rb_snap_angle.toggled.connect(self._on_snap_mode_toggled)
        self.combo_snap.currentIndexChanged.connect(self._on_snap_changed)

        self._configure_numeric_validators()
        self._load_settings()

    def _apply_style(self):
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_plain = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_plain is not None:
            self.setFrameShadow(shadow_plain)
        self.setAutoFillBackground(True)

    def _update_lock_icon(self):
        if self.btn_lock_angle.isChecked():
            self.btn_lock_angle.setIcon(self._get_icon("locked.svg"))
        else:
            self.btn_lock_angle.setIcon(self._get_icon("unlocked.svg"))

    def _configure_numeric_validators(self):
        """Sets strict numeric validator on angle spinbox lineEdit."""
        regex = QRegularExpression(r"^-?[0-9]*[.,]?[0-9]*$")
        if hasattr(self.spin_angle, "lineEdit") and self.spin_angle.lineEdit():
            val = QRegularExpressionValidator(regex, self.spin_angle.lineEdit())
            self.spin_angle.lineEdit().setValidator(val)

    def _handle_spin_key_press(self, event) -> bool:
        """Restricts text input to numeric digits, minus sign, and normalizes decimal separator."""
        text = event.text()
        if not text:
            return False

        modifiers = event.modifiers()
        control_mod = getattr(Qt.KeyboardModifier, "ControlModifier", getattr(Qt, "ControlModifier", 0x04000000))
        if modifiers and (modifiers & control_mod):
            return False

        if text.isdigit():
            return False

        line_edit = self.spin_angle.lineEdit() if hasattr(self.spin_angle, "lineEdit") else None
        if not line_edit:
            return False

        curr_text = line_edit.text()
        sel_start = line_edit.selectionStart()
        sel_len = len(line_edit.selectedText())
        unselected = (
            curr_text[:sel_start] + curr_text[sel_start + sel_len :]
            if sel_start >= 0
            else curr_text
        )

        if text == "-":
            if "-" not in unselected and (sel_start == 0 or not curr_text):
                line_edit.insert("-")
            return True

        if text in (".", ","):
            if "." in unselected or "," in unselected:
                return True
            dec_sep = self.spin_angle.locale().decimalPoint() if hasattr(self.spin_angle, "locale") else "."
            line_edit.insert(dec_sep)
            return True

        return True

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        evt_focus_in = getattr(QEvent.Type, "FocusIn", getattr(QEvent, "FocusIn", None))
        evt_key_press = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None))
        evt_key_release = getattr(QEvent.Type, "KeyRelease", getattr(QEvent, "KeyRelease", None))

        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        elif event.type() == evt_focus_in:
            if obj == self.spin_angle or (hasattr(self.spin_angle, "lineEdit") and obj == self.spin_angle.lineEdit()):
                QTimer.singleShot(0, self._select_all_angle)
        elif event.type() == evt_key_press:
            key = event.key()
            key_shift = getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020))
            if key == key_shift:
                self.set_shift_override(True)

            key_tab = getattr(Qt.Key, "Key_Tab", getattr(Qt, "Key_Tab", 0x01000001))
            key_backtab = getattr(Qt.Key, "Key_Backtab", getattr(Qt, "Key_Backtab", 0x01000002))
            key_return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
            key_enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))

            if key in (key_return, key_enter):
                self.commitRequested.emit()
                return True

            if key == key_tab:
                self.focusNextChild()
                return True
            elif key == key_backtab:
                self.focusPreviousChild()
                return True

            if hasattr(self.spin_angle, "lineEdit") and obj == self.spin_angle.lineEdit():
                if self._handle_spin_key_press(event):
                    return True
        elif event.type() == evt_key_release:
            key = event.key()
            key_shift = getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020))
            if key == key_shift:
                self.set_shift_override(False)

        return super().eventFilter(obj, event)

    def _select_all_angle(self):
        if hasattr(self.spin_angle, "lineEdit") and self.spin_angle.lineEdit():
            self.spin_angle.lineEdit().selectAll()
        else:
            self.spin_angle.selectAll()

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_PIVOT:
            self.lbl_step.setText(self.tr("1. Вкажіть центр обертання"))
        elif step == self.STEP_REFERENCE:
            self.lbl_step.setText(self.tr("2. Вкажіть базовий орієнтир"))
        elif step == self.STEP_ROTATING:
            self.lbl_step.setText(self.tr("3. Вкажіть цільовий кут"))
        self.reposition_to_default()

    def set_snap_mode(self, mode: str):
        self._base_snap_mode = mode
        self._shift_pressed = False
        self._is_updating_shift_override = True
        try:
            if mode == "angle":
                self.rb_snap_angle.setChecked(True)
                self.combo_snap.setEnabled(True)
            else:
                self.rb_snap_free.setChecked(True)
                self.combo_snap.setEnabled(False)
        finally:
            self._is_updating_shift_override = False
        self.save_settings()
        self.stepSnapChanged.emit(self.snap_step if mode == "angle" else 0.0)

    def _on_snap_mode_toggled(self, checked: bool):
        if self._is_updating_shift_override:
            return
        if self.rb_snap_angle.isChecked():
            self._base_snap_mode = "angle"
        else:
            self._base_snap_mode = "free"
        self._shift_pressed = False
        self.combo_snap.setEnabled(self._base_snap_mode == "angle")
        self.save_settings()
        self.stepSnapChanged.emit(self.snap_step if self._base_snap_mode == "angle" else 0.0)

    def _on_snap_changed(self):
        if self.is_snap_enabled:
            self.stepSnapChanged.emit(self.snap_step)

    def set_shift_override(self, shift_pressed: bool):
        """Temporarily inverts radio button selection and enables/disables combobox on Shift press/release."""
        if self._shift_pressed == shift_pressed:
            return
        self._shift_pressed = shift_pressed
        target_mode = "angle" if (self._base_snap_mode == "free" if shift_pressed else self._base_snap_mode == "angle") else "free"

        self._is_updating_shift_override = True
        try:
            if target_mode == "angle":
                self.rb_snap_angle.setChecked(True)
                self.combo_snap.setEnabled(True)
            else:
                self.rb_snap_free.setChecked(True)
                self.combo_snap.setEnabled(False)
        finally:
            self._is_updating_shift_override = False

    @property
    def angle(self) -> float:
        return self.spin_angle.value()

    def set_angle(self, val: float, block_signals: bool = False):
        if block_signals:
            self.spin_angle.blockSignals(True)
        self.spin_angle.setValue(val)
        if self.spin_angle.hasFocus() or (hasattr(self.spin_angle, "lineEdit") and self.spin_angle.lineEdit() and self.spin_angle.lineEdit().hasFocus()):
            self._select_all_angle()
        if block_signals:
            self.spin_angle.blockSignals(False)

    @property
    def is_angle_locked(self) -> bool:
        return self.btn_lock_angle.isChecked()

    @property
    def is_copy_mode(self) -> bool:
        return self.chk_copy.isChecked()

    @property
    def is_snap_enabled(self) -> bool:
        return self.rb_snap_angle.isChecked()

    @property
    def snap_step(self) -> float:
        return float(self.combo_snap.currentData())

    def get_effective_snap_step(self, shift_pressed: bool = False) -> Optional[float]:
        """
        Returns effective snap angle in degrees based on radio button state and Shift modifier:
        - If 'Angle snap' radio is checked: snap by selected angle, unless Shift is held (temporarily free).
        - If 'Free' radio is checked: free angle, unless Shift is held (temporarily snap by selected angle).
        """
        self.set_shift_override(shift_pressed)
        is_eff_angle = (self._base_snap_mode == "angle" and not shift_pressed) or (self._base_snap_mode == "free" and shift_pressed)
        return self.snap_step if is_eff_angle else None

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas."""
        self.lbl_step.adjustSize()
        self.adjustSize()
        hint = self.sizeHint()
        lbl_hint = self.lbl_step.sizeHint()
        w = max(hint.width(), lbl_hint.width() + 20)
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

    def focus_angle_input(self):
        self.spin_angle.setFocus()
        if hasattr(self.spin_angle, "lineEdit") and self.spin_angle.lineEdit():
            self.spin_angle.lineEdit().setFocus()
            self.spin_angle.lineEdit().selectAll()
        else:
            self.spin_angle.selectAll()

    def focus_primary_input(self):
        self.focus_angle_input()

    def toggle_active_lock(self):
        self.btn_lock_angle.toggle()

    def _load_settings(self):
        s = QgsSettings()
        mode = s.value("plugins/fillet/rotate_snap_mode", "free")
        self._base_snap_mode = mode
        if mode == "angle":
            self.rb_snap_angle.setChecked(True)
        else:
            self.rb_snap_free.setChecked(True)
        self.combo_snap.setEnabled(self.rb_snap_angle.isChecked())

        snap_val = float(s.value("plugins/fillet/rotate_snap_step", 15.0))
        idx = self.combo_snap.findData(snap_val)
        if idx >= 0:
            self.combo_snap.setCurrentIndex(idx)
        else:
            self.combo_snap.setCurrentIndex(1)  # Default 15°

        self.chk_copy.setChecked(s.value("plugins/fillet/rotate_copy_mode", False, type=bool))

    def save_settings(self):
        s = QgsSettings()
        s.setValue("plugins/fillet/rotate_snap_mode", self._base_snap_mode)
        s.setValue("plugins/fillet/rotate_snap_step", self.snap_step)
        s.setValue("plugins/fillet/rotate_copy_mode", self.is_copy_mode)

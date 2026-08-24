# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Rotation tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import os
from typing import Optional

from qgis.core import QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas
from qgis.PyQt.QtCore import QEvent, QPoint, QRegularExpression, QSize, Qt, QTimer, pyqtSignal
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
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
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

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("RotationCanvasWidget")

        self._drag_pos: Optional[QPoint] = None
        self._user_moved = False
        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_PIVOT

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

        # Row 1: Snap step angle
        self.lbl_snap = QLabel(self.tr("Крок кута:"), self)
        self.combo_snap = QComboBox(self)
        self.combo_snap.addItem(self.tr("Вільний (Free)"), 0.0)
        self.combo_snap.addItem("5°", 5.0)
        self.combo_snap.addItem("15°", 15.0)
        self.combo_snap.addItem("45°", 45.0)
        self.combo_snap.addItem("90°", 90.0)

        grid.addWidget(self.lbl_snap, 1, 0)
        grid.addWidget(self.combo_snap, 1, 1, 1, 2)

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
            self.combo_snap.setCursor(QCursor(arrow_cursor))
            self.chk_copy.setCursor(QCursor(arrow_cursor))

        self.spin_angle.installEventFilter(self)
        if hasattr(self.spin_angle, "lineEdit") and self.spin_angle.lineEdit():
            if ibeam_cursor is not None:
                self.spin_angle.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_angle.lineEdit().installEventFilter(self)
            self.spin_angle.lineEdit().returnPressed.connect(self.commitRequested.emit)

        # Signal connections
        self.spin_angle.valueChanged.connect(self.angleChanged.emit)
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
        # Allows optional minus sign, digits, and one decimal separator
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
            # Minus is only allowed at the beginning if not already present
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

        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        elif event.type() == evt_focus_in:
            if obj == self.spin_angle or (hasattr(self.spin_angle, "lineEdit") and obj == self.spin_angle.lineEdit()):
                QTimer.singleShot(0, self._select_all_angle)
        elif event.type() == evt_key_press:
            if hasattr(self.spin_angle, "lineEdit") and obj == self.spin_angle.lineEdit():
                if self._handle_spin_key_press(event):
                    return True

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

    def _on_snap_changed(self):
        step_val = float(self.combo_snap.currentData())
        self.stepSnapChanged.emit(step_val)

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
    def snap_step(self) -> float:
        return float(self.combo_snap.currentData())

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas."""
        self.adjustSize()
        self.resize(self.minimumSizeHint())
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
        self._select_all_angle()

    def _load_settings(self):
        s = QgsSettings()
        snap_val = float(s.value("plugins/fillet/rotate_snap_step", 0.0))
        idx = self.combo_snap.findData(snap_val)
        if idx >= 0:
            self.combo_snap.setCurrentIndex(idx)
        self.chk_copy.setChecked(s.value("plugins/fillet/rotate_copy_mode", False, type=bool))

    def save_settings(self):
        s = QgsSettings()
        s.setValue("plugins/fillet/rotate_snap_step", self.snap_step)
        s.setValue("plugins/fillet/rotate_copy_mode", self.is_copy_mode)

    # Draggable canvas widget support
    def mousePressEvent(self, event):
        left_btn = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
        if event.button() == left_btn:
            pos_accessor = getattr(event, "position", None)
            local_pos = pos_accessor() if callable(pos_accessor) else event.pos()
            self._drag_pos = local_pos.toPoint() if hasattr(local_pos, "toPoint") else local_pos
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        left_btn_mask = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
        if self._drag_pos is not None and (event.buttons() & left_btn_mask):
            pos_accessor = getattr(event, "position", None)
            local_pos = pos_accessor() if callable(pos_accessor) else event.pos()
            pt = local_pos.toPoint() if hasattr(local_pos, "toPoint") else local_pos
            delta = pt - self._drag_pos
            new_pos = self.pos() + delta
            x = max(0, min(new_pos.x(), self.canvas.width() - self.width()))
            y = max(0, min(new_pos.y(), self.canvas.height() - self.height()))
            self.move(x, y)
            self._user_moved = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

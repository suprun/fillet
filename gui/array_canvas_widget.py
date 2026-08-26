# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Copy Features in an Array tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

from enum import IntEnum
import os
from typing import Optional

from qgis.core import QgsCoordinateReferenceSystem, QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas, QgsSpinBox
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
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ArrayMode(IntEnum):
    """Modes of generating feature arrays along a reference vector."""
    FeatureCount = 0
    FeatureSpacing = 1
    FeatureCountAndSpacing = 2


class ArrayCanvasWidget(QFrame):
    """
    Floating CAD HUD widget pinned on the map canvas for CAD Feature Array tool.
    Provides two interdependent checkboxes:
      - [x] Feature Count
      - [x] Spacing
    At least one checkbox is always guaranteed to be active.
    When a checkbox is disabled, it displays real-time calculated values from map movement.
    When re-enabled, it restores the previous explicitly configured user value.
    """

    modeChanged = pyqtSignal(int)
    featureCountChanged = pyqtSignal(int)
    featureSpacingChanged = pyqtSignal(float)
    commitRequested = pyqtSignal()
    resetRequested = pyqtSignal()

    STEP_START = 0
    STEP_END = 1

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: Optional[QgsMapCanvas] = None):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("ArrayCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_START
        self._is_syncing_checkboxes = False
        self._is_loading = False

        # Persistent user-configured values (restored upon re-enabling checkboxes)
        self._stored_count: int = 3
        self._stored_spacing: float = 1.0

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
        self.setMinimumWidth(235)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # 1. Step indicator label
        self.lbl_step = QLabel(self)
        self.lbl_step.setWordWrap(False)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet("color: #1e3a8a; background-color: #dbeafe; border-radius: 4px; padding: 4px 8px;")
        self.set_step(self.STEP_START)
        main_layout.addWidget(self.lbl_step)

        # 2. Grid for Checkboxes and Inputs
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnMinimumWidth(0, 115)

        # Row 0: Feature Count Checkbox + SpinBox
        self.chk_count = QCheckBox(self.tr("Кількість (Count):"), self)
        self.chk_count.setChecked(True)
        self.chk_count.setToolTip(self.tr("Фіксована кількість нових копій об'єктів у масиві"))

        if hasattr(QgsSpinBox, "setMinimum"):
            self.spin_count = QgsSpinBox(self)
        else:
            self.spin_count = QSpinBox(self)
        self.spin_count.setRange(1, 99999)
        self.spin_count.setValue(3)
        self.spin_count.setSingleStep(1)
        if hasattr(self.spin_count, "setShowClearButton"):
            self.spin_count.setShowClearButton(False)

        grid.addWidget(self.chk_count, 0, 0)
        grid.addWidget(self.spin_count, 0, 1)

        # Row 1: Spacing Checkbox + DoubleSpinBox
        self.chk_spacing = QCheckBox(self.tr("Крок (Spacing):"), self)
        self.chk_spacing.setChecked(False)
        self.chk_spacing.setToolTip(self.tr("Фіксована відстань (крок) між копіями об'єктів у масиві"))

        if hasattr(QgsDoubleSpinBox, "setMinimum"):
            self.spin_spacing = QgsDoubleSpinBox(self)
        else:
            self.spin_spacing = QDoubleSpinBox(self)
        self.spin_spacing.setRange(0.0001, 999999999.0)
        self.spin_spacing.setValue(1.0)
        self.spin_spacing.setDecimals(3)
        self.spin_spacing.setSingleStep(1.0)
        if hasattr(self.spin_spacing, "setShowClearButton"):
            self.spin_spacing.setShowClearButton(False)

        grid.addWidget(self.chk_spacing, 1, 0)
        grid.addWidget(self.spin_spacing, 1, 1)

        main_layout.addLayout(grid)

        # Cursors
        arrow_cursor = getattr(Qt.CursorShape, "ArrowCursor", getattr(Qt, "ArrowCursor", None))
        ibeam_cursor = getattr(Qt.CursorShape, "IBeamCursor", getattr(Qt, "IBeamCursor", None))
        if arrow_cursor is not None:
            self.setCursor(QCursor(arrow_cursor))
            self.chk_count.setCursor(QCursor(arrow_cursor))
            self.spin_count.setCursor(QCursor(arrow_cursor))
            self.chk_spacing.setCursor(QCursor(arrow_cursor))
            self.spin_spacing.setCursor(QCursor(arrow_cursor))
        if hasattr(self.spin_spacing, "lineEdit") and self.spin_spacing.lineEdit() and ibeam_cursor is not None:
            self.spin_spacing.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_spacing.lineEdit().installEventFilter(self)
        if hasattr(self.spin_count, "lineEdit") and self.spin_count.lineEdit() and ibeam_cursor is not None:
            self.spin_count.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_count.lineEdit().installEventFilter(self)

        self._configure_numeric_validators()
        self._load_settings()

        # Connect signals
        self.chk_count.toggled.connect(self._on_chk_count_toggled)
        self.chk_spacing.toggled.connect(self._on_chk_spacing_toggled)
        self.spin_count.valueChanged.connect(self._on_spin_count_changed)
        self.spin_spacing.valueChanged.connect(self._on_spin_spacing_changed)

        # Return pressed in spinboxes triggers commit
        if hasattr(self.spin_count, "lineEdit") and self.spin_count.lineEdit():
            self.spin_count.lineEdit().returnPressed.connect(self.commitRequested.emit)
        if hasattr(self.spin_spacing, "lineEdit") and self.spin_spacing.lineEdit():
            self.spin_spacing.lineEdit().returnPressed.connect(self.commitRequested.emit)

    def _apply_style(self):
        """Unified visual style matching Fillet & Chamfer, Rotate, and Mirror widgets."""
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_plain = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_plain is not None:
            self.setFrameShadow(shadow_plain)
        self.setAutoFillBackground(True)

    def _configure_numeric_validators(self):
        regex = QRegularExpression(r"^[0-9]*[.,]?[0-9]*$")
        if hasattr(self.spin_spacing, "lineEdit") and self.spin_spacing.lineEdit():
            val = QRegularExpressionValidator(regex, self.spin_spacing.lineEdit())
            self.spin_spacing.lineEdit().setValidator(val)

    def _on_spin_count_changed(self, val: int):
        if self.chk_count.isChecked():
            self._stored_count = max(1, int(val))
            self._save_settings()
        self.featureCountChanged.emit(int(val))

    def _on_spin_spacing_changed(self, val: float):
        if self.chk_spacing.isChecked():
            self._stored_spacing = max(0.0001, float(val))
            self._save_settings()
        self.featureSpacingChanged.emit(float(val))

    def _on_chk_count_toggled(self, checked: bool):
        if self._is_syncing_checkboxes or self._is_loading:
            return

        # Enforce rule: at least one checkbox must always remain checked
        if not checked and not self.chk_spacing.isChecked():
            self._is_syncing_checkboxes = True
            try:
                self.chk_spacing.setChecked(True)
            finally:
                self._is_syncing_checkboxes = False

        self._sync_mode_and_states()

    def _on_chk_spacing_toggled(self, checked: bool):
        if self._is_syncing_checkboxes or self._is_loading:
            return

        # Enforce rule: at least one checkbox must always remain checked
        if not checked and not self.chk_count.isChecked():
            self._is_syncing_checkboxes = True
            try:
                self.chk_count.setChecked(True)
            finally:
                self._is_syncing_checkboxes = False

        self._sync_mode_and_states()

    def _sync_mode_and_states(self):
        """Updates enabled state of inputs, restores previously stored values when re-enabled, and emits mode change."""
        is_count = self.chk_count.isChecked()
        is_spacing = self.chk_spacing.isChecked()

        was_count_enabled = self.spin_count.isEnabled()
        was_spacing_enabled = self.spin_spacing.isEnabled()

        # Restore stored user-configured value when becoming enabled
        if is_count and not was_count_enabled:
            self.spin_count.blockSignals(True)
            self.spin_count.setValue(self._stored_count)
            self.spin_count.blockSignals(False)
            self.featureCountChanged.emit(self._stored_count)

        if is_spacing and not was_spacing_enabled:
            self.spin_spacing.blockSignals(True)
            self.spin_spacing.setValue(self._stored_spacing)
            self.spin_spacing.blockSignals(False)
            self.featureSpacingChanged.emit(self._stored_spacing)

        self.spin_count.setEnabled(is_count)
        self.spin_spacing.setEnabled(is_spacing)

        if is_count and not is_spacing:
            m = ArrayMode.FeatureCount
        elif not is_count and is_spacing:
            m = ArrayMode.FeatureSpacing
        else:
            m = ArrayMode.FeatureCountAndSpacing

        self._save_settings()
        self.modeChanged.emit(int(m.value))

    def mode(self) -> ArrayMode:
        is_count = self.chk_count.isChecked()
        is_spacing = self.chk_spacing.isChecked()
        if is_count and not is_spacing:
            return ArrayMode.FeatureCount
        if not is_count and is_spacing:
            return ArrayMode.FeatureSpacing
        return ArrayMode.FeatureCountAndSpacing

    def setMode(self, mode: ArrayMode) -> None:
        val = mode if isinstance(mode, ArrayMode) else ArrayMode(mode)
        self._is_syncing_checkboxes = True
        try:
            if val == ArrayMode.FeatureCount:
                self.chk_count.setChecked(True)
                self.chk_spacing.setChecked(False)
            elif val == ArrayMode.FeatureSpacing:
                self.chk_count.setChecked(False)
                self.chk_spacing.setChecked(True)
            else:  # FeatureCountAndSpacing
                self.chk_count.setChecked(True)
                self.chk_spacing.setChecked(True)
        finally:
            self._is_syncing_checkboxes = False

        self._sync_mode_and_states()

    def featureCount(self) -> int:
        return self.spin_count.value()

    def setFeatureCount(self, count: int) -> None:
        self._stored_count = max(1, int(count))
        if self.chk_count.isChecked():
            self.spin_count.blockSignals(True)
            self.spin_count.setValue(self._stored_count)
            self.spin_count.blockSignals(False)
        self._save_settings()

    def featureSpacing(self) -> float:
        return self.spin_spacing.value()

    def setFeatureSpacing(self, spacing: float) -> None:
        self._stored_spacing = max(0.0001, float(spacing))
        if self.chk_spacing.isChecked():
            self.spin_spacing.blockSignals(True)
            self.spin_spacing.setValue(self._stored_spacing)
            self.spin_spacing.blockSignals(False)
        self._save_settings()

    def set_calculated_count(self, count: int) -> None:
        """Sets dynamically calculated count when count checkbox is disabled without altering stored user value."""
        if not self.chk_count.isChecked():
            self.spin_count.blockSignals(True)
            self.spin_count.setValue(max(0, int(count)))
            self.spin_count.blockSignals(False)

    def set_calculated_spacing(self, spacing: float) -> None:
        """Sets dynamically calculated spacing when spacing checkbox is disabled without altering stored user value."""
        if not self.chk_spacing.isChecked():
            self.spin_spacing.blockSignals(True)
            self.spin_spacing.setValue(max(0.0, float(spacing)))
            self.spin_spacing.blockSignals(False)

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_START:
            self.lbl_step.setText(self.tr("1. Вкажіть початкову точку / об'єкт"))
        elif step == self.STEP_END:
            self.lbl_step.setText(self.tr("2. Вкажіть кінцеву точку / крок"))
        self.reposition_to_default()

    def adapt_to_crs(self, crs: QgsCoordinateReferenceSystem):
        """Adapts decimals and step size for geographic vs metric coordinate systems."""
        if crs.isGeographic():
            self.spin_spacing.setDecimals(6)
            self.spin_spacing.setSingleStep(0.0001)
        else:
            self.spin_spacing.setDecimals(3)
            self.spin_spacing.setSingleStep(1.0)

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas."""
        if self.canvas is None:
            return
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

    def _load_settings(self):
        self._is_loading = True
        try:
            s = QgsSettings()
            mode_val = s.value("FilletPlugin/ArrayMode", ArrayMode.FeatureCount.value, type=int)
            count_val = s.value("FilletPlugin/ArrayCount", 3, type=int)
            spacing_val = s.value("FilletPlugin/ArraySpacing", 1.0, type=float)

            self._stored_count = max(1, int(count_val))
            self._stored_spacing = max(0.0001, float(spacing_val))

            self.setMode(ArrayMode(mode_val))
            self.spin_count.setValue(self._stored_count)
            self.spin_spacing.setValue(self._stored_spacing)
        finally:
            self._is_loading = False

    def _save_settings(self):
        if self._is_loading:
            return
        s = QgsSettings()
        s.setValue("FilletPlugin/ArrayMode", int(self.mode().value))
        s.setValue("FilletPlugin/ArrayCount", int(self._stored_count))
        s.setValue("FilletPlugin/ArraySpacing", float(self._stored_spacing))

    def save_settings(self):
        self._save_settings()

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        evt_key_press = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None))

        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()

        elif event.type() == evt_key_press:
            key = event.key()
            key_tab = getattr(Qt.Key, "Key_Tab", getattr(Qt, "Key_Tab", 0x01000001))
            key_backtab = getattr(Qt.Key, "Key_Backtab", getattr(Qt, "Key_Backtab", 0x01000002))
            key_return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
            key_enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))
            key_escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))

            if key in (key_return, key_enter):
                self.commitRequested.emit()
                return True
            if key == key_escape:
                self.resetRequested.emit()
                return True
            if key == key_tab:
                self.focusNextChild()
                return True
            elif key == key_backtab:
                self.focusPreviousChild()
                return True

        return super().eventFilter(obj, event)

# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Divide / Measure Line tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

from enum import IntEnum
import os
from typing import Optional

from qgis.core import QgsCoordinateReferenceSystem, QgsSettings, QgsVectorLayer, QgsWkbTypes
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
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class DivideLineMode(IntEnum):
    """Modes of dividing line features."""
    SegmentsCount = 0
    SegmentLength = 1


class DivideLineCanvasWidget(QFrame):
    """
    Floating CAD HUD widget pinned on the map canvas for CAD Divide / Measure Line tool.
    Positions firmly in the top-right corner of the canvas matching plugin design aesthetics.
    """

    modeChanged = pyqtSignal(int)
    segmentsCountChanged = pyqtSignal(int)
    segmentLengthChanged = pyqtSignal(float)
    reverseDirectionChanged = pyqtSignal(bool)
    separateFeaturesChanged = pyqtSignal(bool)
    commitRequested = pyqtSignal()
    resetRequested = pyqtSignal()

    STEP_SELECT = 0
    STEP_DIVIDE = 1

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: Optional[QgsMapCanvas] = None):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("DivideLineCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_SELECT
        self._is_syncing_checkboxes = False
        self._is_loading = False

        # Persistent user-configured values
        self._stored_count: int = 4
        self._stored_length: float = 10.0

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
        self.setMinimumWidth(240)

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
        self.set_step(self.STEP_SELECT)
        main_layout.addWidget(self.lbl_step)

        # 2. Grid for Checkboxes and Inputs
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnMinimumWidth(0, 118)

        # Row 0: Segments Count Checkbox + SpinBox
        self.chk_count = QCheckBox(self.tr("Кількість (Count):"), self)
        self.chk_count.setChecked(True)
        self.chk_count.setToolTip(self.tr("Поділ лінії на вказану кількість рівних частин"))

        if hasattr(QgsSpinBox, "setMinimum"):
            self.spin_count = QgsSpinBox(self)
        else:
            self.spin_count = QSpinBox(self)
        self.spin_count.setRange(2, 99999)
        self.spin_count.setValue(4)
        self.spin_count.setSingleStep(1)
        if hasattr(self.spin_count, "setShowClearButton"):
            self.spin_count.setShowClearButton(False)

        grid.addWidget(self.chk_count, 0, 0)
        grid.addWidget(self.spin_count, 0, 1)

        # Row 1: Segment Length Checkbox + DoubleSpinBox
        self.chk_length = QCheckBox(self.tr("Довжина (Length):"), self)
        self.chk_length.setChecked(False)
        self.chk_length.setToolTip(self.tr("Поділ лінії за фіксованим кроком довжини сегмента"))

        if hasattr(QgsDoubleSpinBox, "setMinimum"):
            self.spin_length = QgsDoubleSpinBox(self)
        else:
            self.spin_length = QDoubleSpinBox(self)
        self.spin_length.setRange(0.000001, 999999999.0)
        self.spin_length.setValue(10.0)
        self.spin_length.setDecimals(3)
        self.spin_length.setSingleStep(1.0)
        if hasattr(self.spin_length, "setShowClearButton"):
            self.spin_length.setShowClearButton(False)

        grid.addWidget(self.chk_length, 1, 0)
        grid.addWidget(self.spin_length, 1, 1)

        # Row 2: Reverse Direction Checkbox
        self.chk_reverse_direction = QCheckBox(self.tr("Зворотний напрямок:"), self)
        self.chk_reverse_direction.setChecked(False)
        self.chk_reverse_direction.setToolTip(self.tr("Починати поділ або відлік довжини сегментів з протилежного кінця лінії"))
        grid.addWidget(self.chk_reverse_direction, 2, 0, 1, 2)

        # Row 3: Separate Features Checkbox
        self.chk_separate_features = QCheckBox(self.tr("Окремі об'єкти (Separate):"), self)
        self.chk_separate_features.setChecked(True)
        self.chk_separate_features.setToolTip(self.tr("Зберегти кожен сегмент як окремий векторний об'єкт (якщо вимкнено — як MultiLineString)"))
        grid.addWidget(self.chk_separate_features, 3, 0, 1, 2)

        main_layout.addLayout(grid)

        # Cursors
        arrow_cursor = getattr(Qt.CursorShape, "ArrowCursor", getattr(Qt, "ArrowCursor", None))
        ibeam_cursor = getattr(Qt.CursorShape, "IBeamCursor", getattr(Qt, "IBeamCursor", None))
        if arrow_cursor is not None:
            self.setCursor(QCursor(arrow_cursor))
            self.chk_count.setCursor(QCursor(arrow_cursor))
            self.spin_count.setCursor(QCursor(arrow_cursor))
            self.chk_length.setCursor(QCursor(arrow_cursor))
            self.spin_length.setCursor(QCursor(arrow_cursor))
            self.chk_reverse_direction.setCursor(QCursor(arrow_cursor))
            self.chk_separate_features.setCursor(QCursor(arrow_cursor))
        if hasattr(self.spin_length, "lineEdit") and self.spin_length.lineEdit() and ibeam_cursor is not None:
            self.spin_length.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_length.lineEdit().installEventFilter(self)
        if hasattr(self.spin_count, "lineEdit") and self.spin_count.lineEdit() and ibeam_cursor is not None:
            self.spin_count.lineEdit().setCursor(QCursor(ibeam_cursor))
            self.spin_count.lineEdit().installEventFilter(self)

        # Connections
        self.chk_count.toggled.connect(self._on_count_checkbox_toggled)
        self.chk_length.toggled.connect(self._on_length_checkbox_toggled)
        self.spin_count.valueChanged.connect(self._on_count_value_changed)
        self.spin_length.valueChanged.connect(self._on_length_value_changed)
        self.chk_reverse_direction.toggled.connect(self._on_reverse_direction_toggled)
        self.chk_separate_features.toggled.connect(self._on_separate_features_toggled)

        # Return pressed commit
        if hasattr(self.spin_count, "returnPressed"):
            self.spin_count.returnPressed.connect(self.commitRequested.emit)
        if hasattr(self.spin_length, "returnPressed"):
            self.spin_length.returnPressed.connect(self.commitRequested.emit)

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

    def _load_settings(self):
        self._is_loading = True
        try:
            settings = QgsSettings()
            mode_val = settings.value("Fillet/DivideLineMode", int(DivideLineMode.SegmentsCount), type=int)
            count_val = settings.value("Fillet/DivideLineCount", 4, type=int)
            len_val = settings.value("Fillet/DivideLineLength", 10.0, type=float)
            rev_val = settings.value("Fillet/DivideLineReverse", False, type=bool)
            sep_val = settings.value("Fillet/DivideLineSeparate", True, type=bool)

            self._stored_count = max(2, count_val)
            self._stored_length = max(0.000001, len_val)

            self.spin_count.setValue(self._stored_count)
            self.spin_length.setValue(self._stored_length)
            self.chk_reverse_direction.setChecked(rev_val)
            self.chk_separate_features.setChecked(sep_val)

            if mode_val == int(DivideLineMode.SegmentLength):
                self.chk_count.setChecked(False)
                self.chk_length.setChecked(True)
            else:
                self.chk_count.setChecked(True)
                self.chk_length.setChecked(False)
        finally:
            self._is_loading = False

    def _save_settings(self):
        if self._is_loading:
            return
        settings = QgsSettings()
        settings.setValue("Fillet/DivideLineMode", int(self.mode))
        settings.setValue("Fillet/DivideLineCount", int(self._stored_count))
        settings.setValue("Fillet/DivideLineLength", float(self._stored_length))
        settings.setValue("Fillet/DivideLineReverse", bool(self.chk_reverse_direction.isChecked()))
        settings.setValue("Fillet/DivideLineSeparate", bool(self.chk_separate_features.isChecked()))

    def _sync_mode_and_states(self):
        count_active = self.chk_count.isChecked()
        length_active = self.chk_length.isChecked()

        self.spin_count.setEnabled(count_active)
        self.spin_length.setEnabled(length_active)

        if count_active and not length_active:
            self.spin_count.setValue(self._stored_count)
        elif length_active and not count_active:
            self.spin_length.setValue(self._stored_length)

        self._save_settings()
        self.modeChanged.emit(int(self.mode))

    def _on_count_checkbox_toggled(self, checked: bool):
        if self._is_syncing_checkboxes or self._is_loading:
            return

        if not checked and not self.chk_length.isChecked():
            self._is_syncing_checkboxes = True
            try:
                self.chk_length.setChecked(True)
            finally:
                self._is_syncing_checkboxes = False

        self._sync_mode_and_states()

    def _on_length_checkbox_toggled(self, checked: bool):
        if self._is_syncing_checkboxes or self._is_loading:
            return

        if not checked and not self.chk_count.isChecked():
            self._is_syncing_checkboxes = True
            try:
                self.chk_count.setChecked(True)
            finally:
                self._is_syncing_checkboxes = False

        self._sync_mode_and_states()

    def _on_count_value_changed(self, val: int):
        if self.chk_count.isChecked() and not self._is_loading:
            self._stored_count = max(2, int(val))
            self._save_settings()
        self.segmentsCountChanged.emit(int(val))

    def _on_length_value_changed(self, val: float):
        if self.chk_length.isChecked() and not self._is_loading:
            self._stored_length = max(0.000001, float(val))
            self._save_settings()
        self.segmentLengthChanged.emit(float(val))

    def _on_reverse_direction_toggled(self, checked: bool):
        self._save_settings()
        self.reverseDirectionChanged.emit(checked)

    def _on_separate_features_toggled(self, checked: bool):
        self._save_settings()
        self.separateFeaturesChanged.emit(checked)

    @property
    def mode(self) -> DivideLineMode:
        if self.chk_length.isChecked():
            return DivideLineMode.SegmentLength
        return DivideLineMode.SegmentsCount

    @property
    def segments_count(self) -> int:
        return self.spin_count.value()

    @property
    def segment_length(self) -> float:
        return self.spin_length.value()

    @property
    def reverse_direction(self) -> bool:
        return self.chk_reverse_direction.isChecked()

    @property
    def separate_features(self) -> bool:
        return self.chk_separate_features.isChecked()

    def set_calculated_count(self, val: int):
        """Displays real-time calculated count when count checkbox is disabled."""
        if not self.chk_count.isChecked():
            self.spin_count.blockSignals(True)
            self.spin_count.setValue(max(2, val))
            self.spin_count.blockSignals(False)

    def set_calculated_length(self, val: float):
        """Displays real-time calculated segment length when length checkbox is disabled."""
        if not self.chk_length.isChecked():
            self.spin_length.blockSignals(True)
            self.spin_length.setValue(max(0.000001, val))
            self.spin_length.blockSignals(False)

    def adapt_to_crs(self, crs: QgsCoordinateReferenceSystem):
        """Adapts decimals and step of the length input according to map CRS units."""
        if crs and crs.isGeographic():
            self.spin_length.setDecimals(6)
            self.spin_length.setSingleStep(0.0001)
        else:
            self.spin_length.setDecimals(3)
            self.spin_length.setSingleStep(1.0)

    def update_layer_capabilities(self, layer: Optional[QgsVectorLayer]):
        """Updates capabilities based on active layer type (SinglePart vs MultiPart)."""
        if not layer or not layer.isValid():
            self.chk_separate_features.setEnabled(True)
            self.reposition_to_default()
            return

        is_multi = QgsWkbTypes.isMultiType(layer.wkbType())
        if not is_multi:
            self.chk_separate_features.setChecked(True)
            self.chk_separate_features.setEnabled(False)
            self.chk_separate_features.setToolTip(self.tr("Шар є простим (LineString) і не підтримує складені об'єкти (MultiLineString)"))
        else:
            self.chk_separate_features.setEnabled(True)
            self.chk_separate_features.setToolTip(self.tr("Зберегти кожен сегмент як окремий векторний об'єкт (якщо вимкнено — як MultiLineString)"))

        self.reposition_to_default()

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_SELECT:
            self.lbl_step.setText(self.tr("1. Оберіть лінію для поділу"))
        elif step == self.STEP_DIVIDE:
            self.lbl_step.setText(self.tr("2. Налаштуйте параметри поділу"))
        self.reposition_to_default()

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas."""
        if self.canvas is None:
            return
        self.lbl_step.adjustSize()
        self.adjustSize()
        hint = self.sizeHint()
        lbl_hint = self.lbl_step.sizeHint()
        w = max(hint.width(), lbl_hint.width() + 20, 240)
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
        if obj == self.canvas and self.isHidden():
            return super().eventFilter(obj, event)

        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        evt_key_press = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None))

        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        elif event.type() == evt_key_press:
            key = event.key()
            key_return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
            key_enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))
            key_escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))

            if key in (key_return, key_enter):
                self.commitRequested.emit()
                return True
            if key == key_escape:
                self.resetRequested.emit()
                return True

        return super().eventFilter(obj, event)

    def focus_count_input(self):
        self.spin_count.setFocus()
        self.spin_count.selectAll()

    def focus_length_input(self):
        self.spin_length.setFocus()
        self.spin_length.selectAll()

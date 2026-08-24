# -*- coding: utf-8 -*-
"""
Floating CAD-style settings and HUD panel for Two-Line Fillet & Chamfer with Join / Merge.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

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
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from ..core import constants
except (ImportError, ValueError):
    from core import constants


class TwoLineCanvasWidget(QFrame):
    """Floating on-canvas settings & step-by-step HUD widget for Two-Line Fillet & Chamfer."""

    parametersChanged = pyqtSignal()
    modeChanged = pyqtSignal(str)
    commitRequested = pyqtSignal()

    STEP_FIRST_LINE = 1
    STEP_SECOND_LINE = 2
    STEP_ADJUST = 3

    MODE_FILLET = constants.MODE_FILLET
    MODE_CHAMFER = constants.MODE_CHAMFER

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("TwoLineCanvasWidget")
        self._current_step = self.STEP_FIRST_LINE
        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")

        self._init_ui()
        self._apply_style()

        # Canvas resize tracker
        self.canvas.installEventFilter(self)

    def _get_icon(self, name: str) -> QIcon:
        path = os.path.join(self._icons_dir, name)
        if os.path.exists(path):
            return QIcon(path)
        return QIcon()

    def _get_rotated_icon(self, name: str, angle: float, target_size: int = 32) -> QIcon:
        path = os.path.join(self._icons_dir, name)
        if os.path.exists(path):
            pm = QPixmap(path)
            if not pm.isNull():
                aspect = getattr(Qt.AspectRatioMode, "KeepAspectRatio", getattr(Qt, "KeepAspectRatio", 1))
                smooth = getattr(Qt.TransformationMode, "SmoothTransformation", getattr(Qt, "SmoothTransformation", 1))
                if pm.width() < target_size or pm.height() < target_size:
                    pm = pm.scaled(target_size, target_size, aspect, smooth)
                transform = QTransform().rotate(angle)
                rotated_pm = pm.transformed(transform, smooth)
                return QIcon(rotated_pm)
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

        # 1. Step indicator badge
        self.lbl_step = QLabel(self)
        self.lbl_step.setWordWrap(False)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet("color: #1e3a8a; background-color: #dbeafe; border-radius: 4px; padding: 4px 8px;")
        self.set_step(self.STEP_FIRST_LINE)
        main_layout.addWidget(self.lbl_step)

        # 2. Mode selection radio buttons
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)

        self.radio_group = QButtonGroup(self)
        self.radio_fillet = QRadioButton(self.tr("Fillet"), self)
        self.radio_chamfer = QRadioButton(self.tr("Chamfer"), self)

        self.radio_group.addButton(self.radio_fillet)
        self.radio_group.addButton(self.radio_chamfer)
        self.radio_fillet.setChecked(True)

        mode_layout.addWidget(self.radio_fillet)
        mode_layout.addWidget(self.radio_chamfer)
        mode_layout.addStretch()
        main_layout.addLayout(mode_layout)

        # 3. Stacked controls for Fillet and Chamfer parameters
        self.stacked_controls = QStackedWidget(self)

        # --- FILLET CONTROLS ---
        self.widget_fillet = QWidget(self)
        grid_fillet = QGridLayout(self.widget_fillet)
        grid_fillet.setHorizontalSpacing(6)
        grid_fillet.setVerticalSpacing(4)
        grid_fillet.setContentsMargins(0, 0, 0, 0)
        grid_fillet.setColumnMinimumWidth(0, 95)

        self.lbl_radius = QLabel(self.tr("Radius (R):"), self.widget_fillet)
        self.spin_radius = QgsDoubleSpinBox(self.widget_fillet)
        self.spin_radius.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_radius.setValue(constants.DEFAULT_RADIUS_METRIC)
        self.spin_radius.setDecimals(constants.DECIMALS_METRIC)
        self.spin_radius.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_radius.setShowClearButton(True)

        self.btn_lock_radius = QToolButton(self.widget_fillet)
        self.btn_lock_radius.setCheckable(True)
        self.btn_lock_radius.setChecked(False)
        self.btn_lock_radius.setAutoRaise(True)
        self.btn_lock_radius.setToolTip(self.tr("Блокувати / розблокувати радіус"))
        self._update_lock_icon(self.btn_lock_radius)
        self.btn_lock_radius.toggled.connect(lambda: self._update_lock_icon(self.btn_lock_radius))

        grid_fillet.addWidget(self.lbl_radius, 0, 0)
        grid_fillet.addWidget(self.spin_radius, 0, 1)
        grid_fillet.addWidget(self.btn_lock_radius, 0, 2)

        self.lbl_segments = QLabel(self.tr("Кількість сегментів дуги:"), self.widget_fillet)
        self.spin_segments = QgsSpinBox(self.widget_fillet)
        self.spin_segments.setRange(constants.MIN_SEGMENTS_COUNT, constants.MAX_SEGMENTS_COUNT)
        self.spin_segments.setValue(constants.DEFAULT_SEGMENTS_COUNT)
        self.spin_segments.setShowClearButton(True)

        grid_fillet.addWidget(self.lbl_segments, 1, 0)
        grid_fillet.addWidget(self.spin_segments, 1, 1, 1, 2)

        self.stacked_controls.addWidget(self.widget_fillet)

        # --- CHAMFER CONTROLS ---
        self.widget_chamfer = QWidget(self)
        grid_chamfer = QGridLayout(self.widget_chamfer)
        grid_chamfer.setHorizontalSpacing(6)
        grid_chamfer.setVerticalSpacing(4)
        grid_chamfer.setContentsMargins(0, 0, 0, 0)
        grid_chamfer.setColumnMinimumWidth(0, 95)

        self.lbl_dist1 = QLabel(self.tr("Відстань 1 (d1):"), self.widget_chamfer)
        self.spin_dist1 = QgsDoubleSpinBox(self.widget_chamfer)
        self.spin_dist1.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_dist1.setValue(constants.DEFAULT_DIST1_METRIC)
        self.spin_dist1.setDecimals(constants.DECIMALS_METRIC)
        self.spin_dist1.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_dist1.setShowClearButton(True)

        self.btn_lock_dist1 = QToolButton(self.widget_chamfer)
        self.btn_lock_dist1.setCheckable(True)
        self.btn_lock_dist1.setChecked(False)
        self.btn_lock_dist1.setAutoRaise(True)
        self.btn_lock_dist1.setToolTip(self.tr("Блокувати / розблокувати відстань 1"))
        self._update_lock_icon(self.btn_lock_dist1)
        self.btn_lock_dist1.toggled.connect(self._on_lock_dist1_toggled)

        grid_chamfer.addWidget(self.lbl_dist1, 0, 0)
        grid_chamfer.addWidget(self.spin_dist1, 0, 1)
        grid_chamfer.addWidget(self.btn_lock_dist1, 0, 2)

        self.lbl_dist2 = QLabel(self.tr("Відстань 2 (d2):"), self.widget_chamfer)
        self.spin_dist2 = QgsDoubleSpinBox(self.widget_chamfer)
        self.spin_dist2.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_dist2.setValue(constants.DEFAULT_DIST2_METRIC)
        self.spin_dist2.setDecimals(constants.DECIMALS_METRIC)
        self.spin_dist2.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_dist2.setShowClearButton(True)
        self.spin_dist2.setEnabled(False)

        self.btn_lock_dist2 = QToolButton(self.widget_chamfer)
        self.btn_lock_dist2.setCheckable(True)
        self.btn_lock_dist2.setChecked(False)
        self.btn_lock_dist2.setEnabled(False)
        self.btn_lock_dist2.setAutoRaise(True)
        self.btn_lock_dist2.setToolTip(self.tr("Блокувати / розблокувати відстань 2"))
        self._update_lock_icon(self.btn_lock_dist2)
        self.btn_lock_dist2.toggled.connect(lambda: self._update_lock_icon(self.btn_lock_dist2))

        grid_chamfer.addWidget(self.lbl_dist2, 1, 0)
        grid_chamfer.addWidget(self.spin_dist2, 1, 1)
        grid_chamfer.addWidget(self.btn_lock_dist2, 1, 2)

        policy_fixed = getattr(QSizePolicy.Policy, "Fixed", getattr(QSizePolicy, "Fixed", None))
        policy_expanding = getattr(QSizePolicy.Policy, "Expanding", getattr(QSizePolicy, "Expanding", None))

        self.btn_link = QToolButton(self.widget_chamfer)
        self.btn_link.setCheckable(True)
        self.btn_link.setChecked(True)
        self.btn_link.setAutoRaise(True)
        self.btn_link.setFixedWidth(28)
        self.btn_link.setIconSize(QSize(24, 24))
        if policy_fixed is not None and policy_expanding is not None:
            self.btn_link.setSizePolicy(policy_fixed, policy_expanding)
        self._update_link_icon()
        self.btn_link.toggled.connect(self._on_link_toggled)

        grid_chamfer.addWidget(self.btn_link, 0, 3, 2, 1)

        self.stacked_controls.addWidget(self.widget_chamfer)
        main_layout.addWidget(self.stacked_controls)

        # 4. Merge attributes option checkbox
        self.chk_always_first = QCheckBox(self.tr("Завжди використовувати атрибути першого об'єкта"), self)
        self.chk_always_first.setToolTip(
            self.tr("При об'єднанні двох ліній автоматично зберігати атрибути першого об'єкта без показу діалогу QGIS")
        )
        main_layout.addWidget(self.chk_always_first)

        # Cursor styling
        arrow_cursor = getattr(Qt.CursorShape, "ArrowCursor", getattr(Qt, "ArrowCursor", None))
        ibeam_cursor = getattr(Qt.CursorShape, "IBeamCursor", getattr(Qt, "IBeamCursor", None))
        for spin in (self.spin_radius, self.spin_segments, self.spin_dist1, self.spin_dist2):
            if arrow_cursor is not None:
                spin.setCursor(QCursor(arrow_cursor))
            spin.installEventFilter(self)
            if hasattr(spin, "lineEdit") and spin.lineEdit():
                if ibeam_cursor is not None:
                    spin.lineEdit().setCursor(QCursor(ibeam_cursor))
                spin.lineEdit().installEventFilter(self)
            for child in spin.findChildren(QWidget):
                if child != spin.lineEdit() and arrow_cursor is not None:
                    child.setCursor(QCursor(arrow_cursor))
        if arrow_cursor is not None:
            self.btn_link.setCursor(QCursor(arrow_cursor))

        # Initial visibility & load settings
        self._update_mode_visibility(self.MODE_FILLET)
        self._load_settings()

        # Signal connections
        self.radio_fillet.toggled.connect(self._on_radio_mode_toggled)
        self.radio_chamfer.toggled.connect(self._on_radio_mode_toggled)
        self.spin_radius.valueChanged.connect(self.parametersChanged)
        self.spin_segments.valueChanged.connect(self.parametersChanged)
        self.spin_dist1.valueChanged.connect(self._on_dist1_changed)
        self.spin_dist2.valueChanged.connect(self.parametersChanged)

        self.parametersChanged.connect(self._save_settings)
        self.btn_lock_radius.toggled.connect(lambda _: self._save_settings())
        self.btn_lock_dist1.toggled.connect(lambda _: self._save_settings())
        self.btn_lock_dist2.toggled.connect(lambda _: self._save_settings())
        self.btn_link.toggled.connect(lambda _: self._save_settings())
        self.chk_always_first.toggled.connect(lambda _: self._save_settings())

        self._configure_numeric_validators()

    def _apply_style(self):
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_plain = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_plain is not None:
            self.setFrameShadow(shadow_plain)
        self.setAutoFillBackground(True)

    def _configure_numeric_validators(self):
        reg = QRegularExpression(r"^[0-9]*[.,]?[0-9]*$")
        for spin in (self.spin_radius, self.spin_dist1, self.spin_dist2):
            if hasattr(spin, "lineEdit") and spin.lineEdit():
                val = QRegularExpressionValidator(reg, spin.lineEdit())
                spin.lineEdit().setValidator(val)

        reg_int = QRegularExpression(r"^[0-9]*$")
        if hasattr(self.spin_segments, "lineEdit") and self.spin_segments.lineEdit():
            val_int = QRegularExpressionValidator(reg_int, self.spin_segments.lineEdit())
            self.spin_segments.lineEdit().setValidator(val_int)

    def _update_lock_icon(self, button: QToolButton):
        if button.isChecked():
            button.setIcon(self._get_icon("locked.svg"))
        else:
            button.setIcon(self._get_icon("unlocked.svg"))

    def _update_link_icon(self):
        if self.btn_link.isChecked():
            self.btn_link.setIcon(self._get_rotated_icon("mActionLink.svg", 90))
            self.btn_link.setToolTip(self.tr("Зберегти рівні відстані"))
        else:
            self.btn_link.setIcon(self._get_rotated_icon("mActionUnlink.svg", 90))
            self.btn_link.setToolTip(self.tr("Встановити різні відстані"))

    def _on_link_toggled(self, checked: bool):
        self._update_link_icon()
        self.spin_dist2.setEnabled(not checked)
        self.btn_lock_dist2.setEnabled(not checked)
        if checked:
            self.spin_dist2.setValue(self.spin_dist1.value())
            self.btn_lock_dist2.setChecked(self.btn_lock_dist1.isChecked())
            self._update_lock_icon(self.btn_lock_dist2)
        self.parametersChanged.emit()

    def _on_lock_dist1_toggled(self, checked: bool):
        self._update_lock_icon(self.btn_lock_dist1)
        if self.is_linked:
            self.btn_lock_dist2.setChecked(checked)
            self._update_lock_icon(self.btn_lock_dist2)

    def _on_dist1_changed(self, value: float):
        if self.is_linked:
            self.spin_dist2.setValue(value)
        self.parametersChanged.emit()

    def _on_radio_mode_toggled(self):
        if self.radio_fillet.isChecked():
            self._update_mode_visibility(self.MODE_FILLET)
            self.modeChanged.emit(self.MODE_FILLET)
        elif self.radio_chamfer.isChecked():
            self._update_mode_visibility(self.MODE_CHAMFER)
            self.modeChanged.emit(self.MODE_CHAMFER)
        self._save_settings()
        self.reposition_to_default()

    def _update_mode_visibility(self, mode: str):
        if mode == self.MODE_FILLET:
            self.stacked_controls.setCurrentWidget(self.widget_fillet)
        else:
            self.stacked_controls.setCurrentWidget(self.widget_chamfer)

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_FIRST_LINE:
            self.lbl_step.setText(self.tr("1. Вкажіть першу лінію"))
        elif step == self.STEP_SECOND_LINE:
            self.lbl_step.setText(self.tr("2. Вкажіть другу лінію"))
        elif step == self.STEP_ADJUST:
            self.lbl_step.setText(self.tr("3. Задайте радіус/фаску курсором або зафіксуйте кліком"))
        self.reposition_to_default()

    @property
    def mode(self) -> str:
        return self.MODE_FILLET if self.radio_fillet.isChecked() else self.MODE_CHAMFER

    @property
    def radius(self) -> float:
        return self.spin_radius.value()

    def set_radius(self, value: float, block_signals: bool = False):
        if block_signals:
            self.spin_radius.blockSignals(True)
        self.spin_radius.setValue(value)
        if block_signals:
            self.spin_radius.blockSignals(False)

    @property
    def segments_count(self) -> int:
        return self.spin_segments.value()

    @property
    def distance1(self) -> float:
        return self.spin_dist1.value()

    def set_distance1(self, value: float, block_signals: bool = False):
        if block_signals:
            self.spin_dist1.blockSignals(True)
        self.spin_dist1.setValue(value)
        if block_signals:
            self.spin_dist1.blockSignals(False)
        if self.is_linked:
            self.set_distance2(value, block_signals=block_signals)

    @property
    def distance2(self) -> float:
        return self.spin_dist2.value() if not self.is_linked else self.spin_dist1.value()

    def set_distance2(self, value: float, block_signals: bool = False):
        if block_signals:
            self.spin_dist2.blockSignals(True)
        self.spin_dist2.setValue(value)
        if block_signals:
            self.spin_dist2.blockSignals(False)

    @property
    def is_radius_locked(self) -> bool:
        return self.btn_lock_radius.isChecked()

    @property
    def is_dist1_locked(self) -> bool:
        return self.btn_lock_dist1.isChecked()

    @property
    def is_dist2_locked(self) -> bool:
        return self.btn_lock_dist2.isChecked() if not self.is_linked else self.btn_lock_dist1.isChecked()

    @property
    def is_linked(self) -> bool:
        return self.btn_link.isChecked()

    @property
    def always_use_first_feature(self) -> bool:
        return self.chk_always_first.isChecked()

    def adapt_to_crs(self, crs: QgsCoordinateReferenceSystem):
        if not crs or not crs.isValid():
            return
        is_geo = crs.isGeographic()
        decimals = constants.DECIMALS_GEO if is_geo else constants.DECIMALS_METRIC
        min_val = constants.MIN_GEO_VALUE if is_geo else constants.MIN_METRIC_VALUE
        max_val = constants.MAX_GEO_VALUE if is_geo else constants.MAX_METRIC_VALUE
        step = constants.STEP_GEO_VALUE if is_geo else constants.STEP_METRIC_VALUE

        for spin in (self.spin_radius, self.spin_dist1, self.spin_dist2):
            spin.blockSignals(True)
            spin.setDecimals(decimals)
            spin.setRange(min_val, max_val)
            spin.setSingleStep(step)
            spin.blockSignals(False)

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas without clipping."""
        self.lbl_step.adjustSize()
        self.adjustSize()
        hint = self.sizeHint()
        lbl_hint = self.lbl_step.sizeHint()
        w = max(hint.width(), lbl_hint.width() + 20, 250)
        h = max(hint.height(), lbl_hint.height() + 16)
        self.resize(w, h)
        self.adjustSize()
        x = max(0, self.canvas.width() - self.width())
        y = 0
        self.move(x, y)

    def show_on_canvas(self):
        self.reposition_to_default()
        self.show()
        self.raise_()

    def focus_primary_input(self):
        if self.mode == self.MODE_FILLET:
            self.spin_radius.setFocus()
            self.spin_radius.selectAll()
        else:
            self.spin_dist1.setFocus()
            self.spin_dist1.selectAll()

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        evt_key_press = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None))

        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        elif event.type() == evt_key_press:
            key = event.key()
            k_ret = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
            k_ent = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))
            if key in (k_ret, k_ent):
                self.commitRequested.emit()
                return True
        return super().eventFilter(obj, event)

    def _load_settings(self):
        s = QgsSettings()
        mode = s.value("plugins/fillet/two_line_mode", self.MODE_FILLET, type=str)
        if mode == self.MODE_CHAMFER:
            self.radio_chamfer.setChecked(True)
        else:
            self.radio_fillet.setChecked(True)

        self.spin_radius.setValue(float(s.value("plugins/fillet/two_line_radius", constants.DEFAULT_RADIUS_METRIC)))
        self.spin_segments.setValue(int(s.value("plugins/fillet/two_line_segments", constants.DEFAULT_SEGMENTS_COUNT)))
        self.spin_dist1.setValue(float(s.value("plugins/fillet/two_line_dist1", constants.DEFAULT_DIST1_METRIC)))
        self.spin_dist2.setValue(float(s.value("plugins/fillet/two_line_dist2", constants.DEFAULT_DIST2_METRIC)))

        self.btn_lock_radius.setChecked(s.value("plugins/fillet/two_line_lock_radius", False, type=bool))
        self.btn_lock_dist1.setChecked(s.value("plugins/fillet/two_line_lock_dist1", False, type=bool))
        self.btn_lock_dist2.setChecked(s.value("plugins/fillet/two_line_lock_dist2", False, type=bool))
        self.btn_link.setChecked(s.value("plugins/fillet/two_line_link_dist", True, type=bool))

        self.chk_always_first.setChecked(s.value("plugins/fillet/merge_always_first_feature", False, type=bool))

        self._update_lock_icon(self.btn_lock_radius)
        self._update_lock_icon(self.btn_lock_dist1)
        self._update_lock_icon(self.btn_lock_dist2)
        self._update_link_icon()
        self.spin_dist2.setEnabled(not self.btn_link.isChecked())
        self.btn_lock_dist2.setEnabled(not self.btn_link.isChecked())

    def _save_settings(self):
        s = QgsSettings()
        s.setValue("plugins/fillet/two_line_mode", self.mode)
        s.setValue("plugins/fillet/two_line_radius", self.spin_radius.value())
        s.setValue("plugins/fillet/two_line_segments", self.spin_segments.value())
        s.setValue("plugins/fillet/two_line_dist1", self.spin_dist1.value())
        s.setValue("plugins/fillet/two_line_dist2", self.spin_dist2.value())
        s.setValue("plugins/fillet/two_line_lock_radius", self.btn_lock_radius.isChecked())
        s.setValue("plugins/fillet/two_line_lock_dist1", self.btn_lock_dist1.isChecked())
        s.setValue("plugins/fillet/two_line_lock_dist2", self.btn_lock_dist2.isChecked())
        s.setValue("plugins/fillet/two_line_link_dist", self.btn_link.isChecked())
        s.setValue("plugins/fillet/merge_always_first_feature", self.chk_always_first.isChecked())

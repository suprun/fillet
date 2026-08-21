import os
from typing import Optional

from qgis.core import QgsCoordinateReferenceSystem, QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas, QgsSpinBox
from qgis.PyQt.QtCore import QEvent, QPoint, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QFont, QIcon, QPixmap, QTransform
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
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


class FilletCanvasWidget(QFrame):
    """Floating CAD-style panel inside the QGIS map canvas."""

    parametersChanged = pyqtSignal()
    modeChanged = pyqtSignal(str)
    commitRequested = pyqtSignal()

    MODE_FILLET = constants.MODE_FILLET
    MODE_CHAMFER = constants.MODE_CHAMFER
    MODE_RESTORE = constants.MODE_RESTORE

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("FilletCanvasWidget")

        self._drag_pos: Optional[QPoint] = None
        self._user_moved = False
        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._last_focused_spin = None

        self._init_ui()
        self._apply_style()
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
                    pm = pm.scaled(
                        target_size,
                        target_size,
                        aspect,
                        smooth,
                    )
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
        self.setMinimumWidth(235)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Mode selection row
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)

        self.radio_fillet = QRadioButton(self.tr("Fillet"), self)
        self.radio_fillet.setIcon(self._get_icon("fillet.svg"))
        self.radio_fillet.setChecked(True)

        self.radio_chamfer = QRadioButton(self.tr("Chamfer"), self)
        self.radio_chamfer.setIcon(self._get_icon("chamfer.svg"))

        self.radio_restore = QRadioButton(self.tr("Restore"), self)
        self.radio_restore.setToolTip(self.tr("Відновити гострий кут (видалити скруглення або фаску)"))

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_fillet)
        self.mode_group.addButton(self.radio_chamfer)
        self.mode_group.addButton(self.radio_restore)

        mode_layout.addWidget(self.radio_fillet)
        mode_layout.addWidget(self.radio_chamfer)
        mode_layout.addWidget(self.radio_restore)
        mode_layout.addStretch()

        main_layout.addLayout(mode_layout)

        # Stacked container for mode-specific controls
        self.stacked_controls = QStackedWidget(self)

        # --- 1. FILLET SUB-WIDGET ---
        self.widget_fillet = QWidget(self)
        grid_fillet = QGridLayout(self.widget_fillet)
        grid_fillet.setHorizontalSpacing(6)
        grid_fillet.setVerticalSpacing(4)
        grid_fillet.setContentsMargins(0, 0, 0, 0)
        grid_fillet.setColumnMinimumWidth(0, 95)

        # Row 0: Radius
        self.lbl_radius = QLabel(self.tr("Radius"), self.widget_fillet)
        self.spin_radius = QgsDoubleSpinBox(self.widget_fillet)
        self.spin_radius.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_radius.setValue(constants.DEFAULT_RADIUS_METRIC)
        self.spin_radius.setDecimals(constants.DECIMALS_METRIC)
        self.spin_radius.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_radius.setShowClearButton(True)

        self.btn_lock_radius = QToolButton(self.widget_fillet)
        self.btn_lock_radius.setCheckable(True)
        self.btn_lock_radius.setChecked(True)
        self.btn_lock_radius.setAutoRaise(True)
        self.btn_lock_radius.setToolTip(self.tr("Блокувати / розблокувати радіус"))
        self._update_lock_icon(self.btn_lock_radius)
        self.btn_lock_radius.toggled.connect(lambda: self._update_lock_icon(self.btn_lock_radius))

        grid_fillet.addWidget(self.lbl_radius, 0, 0)
        grid_fillet.addWidget(self.spin_radius, 0, 1)
        grid_fillet.addWidget(self.btn_lock_radius, 0, 2)

        # Row 1: Fillet segments
        self.lbl_segments = QLabel(self.tr("Fillet segments"), self.widget_fillet)
        self.spin_segments = QgsSpinBox(self.widget_fillet)
        self.spin_segments.setRange(constants.MIN_SEGMENTS_COUNT, constants.MAX_SEGMENTS_COUNT)
        self.spin_segments.setValue(constants.DEFAULT_SEGMENTS_COUNT)
        self.spin_segments.setShowClearButton(True)

        self.btn_lock_segments = QToolButton(self.widget_fillet)
        self.btn_lock_segments.setCheckable(True)
        self.btn_lock_segments.setChecked(True)
        self.btn_lock_segments.setEnabled(False)
        self.btn_lock_segments.setAutoRaise(True)
        self._update_lock_icon(self.btn_lock_segments)

        grid_fillet.addWidget(self.lbl_segments, 1, 0)
        grid_fillet.addWidget(self.spin_segments, 1, 1)
        grid_fillet.addWidget(self.btn_lock_segments, 1, 2)

        self.stacked_controls.addWidget(self.widget_fillet)

        # --- 2. CHAMFER SUB-WIDGET ---
        self.widget_chamfer = QWidget(self)
        grid_chamfer = QGridLayout(self.widget_chamfer)
        grid_chamfer.setHorizontalSpacing(6)
        grid_chamfer.setVerticalSpacing(4)
        grid_chamfer.setContentsMargins(0, 0, 0, 0)
        grid_chamfer.setColumnMinimumWidth(0, 95)

        # Row 0: Distance 1
        self.lbl_dist1 = QLabel(self.tr("Distance 1"), self.widget_chamfer)
        self.spin_dist1 = QgsDoubleSpinBox(self.widget_chamfer)
        self.spin_dist1.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_dist1.setValue(constants.DEFAULT_DIST1_METRIC)
        self.spin_dist1.setDecimals(constants.DECIMALS_METRIC)
        self.spin_dist1.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_dist1.setShowClearButton(True)

        self.btn_lock_dist1 = QToolButton(self.widget_chamfer)
        self.btn_lock_dist1.setCheckable(True)
        self.btn_lock_dist1.setChecked(True)
        self.btn_lock_dist1.setAutoRaise(True)
        self.btn_lock_dist1.setToolTip(self.tr("Блокувати / розблокувати відстань 1"))
        self._update_lock_icon(self.btn_lock_dist1)
        self.btn_lock_dist1.toggled.connect(self._on_lock_dist1_toggled)

        grid_chamfer.addWidget(self.lbl_dist1, 0, 0)
        grid_chamfer.addWidget(self.spin_dist1, 0, 1)
        grid_chamfer.addWidget(self.btn_lock_dist1, 0, 2)

        # Row 1: Distance 2
        self.lbl_dist2 = QLabel(self.tr("Distance 2"), self.widget_chamfer)
        self.spin_dist2 = QgsDoubleSpinBox(self.widget_chamfer)
        self.spin_dist2.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_dist2.setValue(constants.DEFAULT_DIST2_METRIC)
        self.spin_dist2.setDecimals(constants.DECIMALS_METRIC)
        self.spin_dist2.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_dist2.setShowClearButton(True)
        self.spin_dist2.setEnabled(False)

        self.btn_lock_dist2 = QToolButton(self.widget_chamfer)
        self.btn_lock_dist2.setCheckable(True)
        self.btn_lock_dist2.setChecked(True)
        self.btn_lock_dist2.setEnabled(False)
        self.btn_lock_dist2.setAutoRaise(True)
        self.btn_lock_dist2.setToolTip(self.tr("Блокувати / розблокувати відстань 2"))
        self._update_lock_icon(self.btn_lock_dist2)
        self.btn_lock_dist2.toggled.connect(lambda: self._update_lock_icon(self.btn_lock_dist2))

        grid_chamfer.addWidget(self.lbl_dist2, 1, 0)
        grid_chamfer.addWidget(self.spin_dist2, 1, 1)
        grid_chamfer.addWidget(self.btn_lock_dist2, 1, 2)

        # Tall narrow Link button spanning across Distance 1 and Distance 2 rows (rotated 90 degrees)
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

        # --- 3. RESTORE SUB-WIDGET ---
        self.widget_restore = QWidget(self)
        layout_restore = QVBoxLayout(self.widget_restore)
        layout_restore.setContentsMargins(4, 4, 4, 4)
        layout_restore.setSpacing(2)
        self.lbl_restore_info = QLabel(self.tr("Клікніть на дугу або фаску для відновлення гострого кута"), self.widget_restore)
        self.lbl_restore_info.setStyleSheet("color: #718096; font-size: 11px; font-style: italic;")
        self.lbl_restore_info.setWordWrap(True)
        layout_restore.addWidget(self.lbl_restore_info)
        self.stacked_controls.addWidget(self.widget_restore)

        main_layout.addWidget(self.stacked_controls)

        # Initial visibility & load persisted settings from user profile
        self._update_mode_visibility(self.MODE_FILLET)
        self._load_settings()

        # Signal connections
        self.radio_fillet.toggled.connect(self._on_radio_mode_toggled)
        self.radio_chamfer.toggled.connect(self._on_radio_mode_toggled)
        self.radio_restore.toggled.connect(self._on_radio_mode_toggled)
        self.spin_radius.valueChanged.connect(self.parametersChanged)
        self.spin_segments.valueChanged.connect(self.parametersChanged)
        self.spin_dist1.valueChanged.connect(self._on_dist1_changed)
        self.spin_dist2.valueChanged.connect(self.parametersChanged)

        # Save settings on any change
        self.parametersChanged.connect(self._save_settings)
        self.btn_lock_radius.toggled.connect(lambda _: self._save_settings())
        self.btn_lock_dist1.toggled.connect(lambda _: self._save_settings())
        self.btn_lock_dist2.toggled.connect(lambda _: self._save_settings())
        self.btn_link.toggled.connect(lambda _: self._save_settings())

        # Enter key in spinboxes requests commit
        if hasattr(self.spin_radius, "lineEdit") and self.spin_radius.lineEdit():
            self.spin_radius.lineEdit().returnPressed.connect(self.commitRequested.emit)
        if hasattr(self.spin_dist1, "lineEdit") and self.spin_dist1.lineEdit():
            self.spin_dist1.lineEdit().returnPressed.connect(self.commitRequested.emit)
        if hasattr(self.spin_dist2, "lineEdit") and self.spin_dist2.lineEdit():
            self.spin_dist2.lineEdit().returnPressed.connect(self.commitRequested.emit)

        # Standard arrow cursor over panel, buttons, and spinboxes; I-beam ONLY on text lineEdit
        arrow_cursor = getattr(Qt.CursorShape, "ArrowCursor", getattr(Qt, "ArrowCursor", None))
        ibeam_cursor = getattr(Qt.CursorShape, "IBeamCursor", getattr(Qt, "IBeamCursor", None))
        if arrow_cursor is not None:
            self.setCursor(QCursor(arrow_cursor))
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
        for btn in (
            self.radio_fillet,
            self.radio_chamfer,
            self.radio_restore,
            self.btn_lock_radius,
            self.btn_lock_segments,
            self.btn_lock_dist1,
            self.btn_lock_dist2,
            self.btn_link,
        ):
            if arrow_cursor is not None:
                btn.setCursor(QCursor(arrow_cursor))

    def _apply_style(self):
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_raised = getattr(QFrame.Shadow, "Raised", getattr(QFrame, "Raised", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_raised is not None:
            self.setFrameShadow(shadow_raised)
        self.setAutoFillBackground(True)

        # Drop shadow effect for floating on canvas
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def _update_lock_icon(self, btn: QToolButton):
        if btn.isChecked():
            btn.setIcon(self._get_icon("locked.svg"))
        else:
            btn.setIcon(self._get_icon("unlocked.svg"))

    def _update_link_icon(self):
        if self.btn_link.isChecked():
            self.btn_link.setIcon(self._get_rotated_icon("mActionLink.svg", 90, 32))
            self.btn_link.setToolTip(self.tr("Відстані зв'язані (d1 = d2)"))
        else:
            self.btn_link.setIcon(self._get_rotated_icon("mActionUnlink.svg", 90, 32))
            self.btn_link.setToolTip(self.tr("Відстані роздільні (d1 ≠ d2)"))

    def _load_settings(self):
        self._is_loading = True
        try:
            s = QgsSettings()
            mode = s.value("plugins/fillet/mode", self.MODE_FILLET, type=str)
            if mode == self.MODE_CHAMFER:
                self.radio_chamfer.setChecked(True)
            elif mode == self.MODE_RESTORE:
                self.radio_restore.setChecked(True)
            else:
                self.radio_fillet.setChecked(True)

            self.spin_radius.setValue(float(s.value("plugins/fillet/radius", constants.DEFAULT_RADIUS_METRIC)))
            self.btn_lock_radius.setChecked(s.value("plugins/fillet/lock_radius", True, type=bool))
            self.spin_segments.setValue(int(s.value("plugins/fillet/segments", constants.DEFAULT_SEGMENTS_COUNT)))

            self.spin_dist1.setValue(float(s.value("plugins/fillet/dist1", constants.DEFAULT_DIST1_METRIC)))
            self.btn_lock_dist1.setChecked(s.value("plugins/fillet/lock_dist1", True, type=bool))
            self.spin_dist2.setValue(float(s.value("plugins/fillet/dist2", constants.DEFAULT_DIST2_METRIC)))
            self.btn_lock_dist2.setChecked(s.value("plugins/fillet/lock_dist2", True, type=bool))
            self.btn_link.setChecked(s.value("plugins/fillet/link_dist", constants.DEFAULT_LINK_DISTANCES, type=bool))

            self._update_link_icon()
            self._update_lock_icon(self.btn_lock_radius)
            self._update_lock_icon(self.btn_lock_dist1)
            self._update_lock_icon(self.btn_lock_dist2)
            self._update_mode_visibility(self.mode)
        finally:
            self._is_loading = False

    def _save_settings(self):
        if getattr(self, "_is_loading", False):
            return
        s = QgsSettings()
        s.setValue("plugins/fillet/mode", self.mode)
        s.setValue("plugins/fillet/radius", self.spin_radius.value())
        s.setValue("plugins/fillet/lock_radius", self.btn_lock_radius.isChecked())
        s.setValue("plugins/fillet/segments", self.spin_segments.value())

        s.setValue("plugins/fillet/dist1", self.spin_dist1.value())
        s.setValue("plugins/fillet/lock_dist1", self.btn_lock_dist1.isChecked())
        s.setValue("plugins/fillet/dist2", self.spin_dist2.value())
        s.setValue("plugins/fillet/lock_dist2", self.btn_lock_dist2.isChecked())
        s.setValue("plugins/fillet/link_dist", self.btn_link.isChecked())

    def _on_radio_mode_toggled(self):
        mode = self.mode
        is_fillet = mode == self.MODE_FILLET
        is_chamfer = mode == self.MODE_CHAMFER

        # Transfer value between primary inputs (Radius <-> Distance 1)
        if not getattr(self, "_is_loading", False):
            if is_fillet:
                self.spin_radius.setValue(self.spin_dist1.value())
            elif is_chamfer:
                self.spin_dist1.setValue(self.spin_radius.value())
                if self.btn_link.isChecked():
                    self.spin_dist2.setValue(self.spin_radius.value())

        self._update_mode_visibility(mode)
        self.modeChanged.emit(mode)
        self.parametersChanged.emit()
        self.focus_primary_input()

    def _update_mode_visibility(self, mode: str):
        if mode == self.MODE_FILLET:
            idx = 0
        elif mode == self.MODE_CHAMFER:
            idx = 1
        else:
            idx = 2
        self.stacked_controls.setCurrentIndex(idx)
        self._update_tab_order(mode)
        self.reposition_to_default()

    def _update_tab_order(self, mode: str):
        if mode == self.MODE_FILLET:
            QWidget.setTabOrder(self.spin_radius, self.spin_segments)
            QWidget.setTabOrder(self.spin_segments, self.btn_lock_radius)
            QWidget.setTabOrder(self.btn_lock_radius, self.radio_fillet)
            QWidget.setTabOrder(self.radio_fillet, self.radio_chamfer)
            QWidget.setTabOrder(self.radio_chamfer, self.radio_restore)
        elif mode == self.MODE_CHAMFER:
            QWidget.setTabOrder(self.spin_dist1, self.spin_dist2)
            QWidget.setTabOrder(self.spin_dist2, self.btn_link)
            QWidget.setTabOrder(self.btn_link, self.btn_lock_dist1)
            QWidget.setTabOrder(self.btn_lock_dist1, self.btn_lock_dist2)
            QWidget.setTabOrder(self.btn_lock_dist2, self.radio_fillet)
            QWidget.setTabOrder(self.radio_fillet, self.radio_chamfer)
            QWidget.setTabOrder(self.radio_chamfer, self.radio_restore)
        else:
            QWidget.setTabOrder(self.radio_restore, self.radio_fillet)
            QWidget.setTabOrder(self.radio_fillet, self.radio_chamfer)

    def _on_link_toggled(self, checked: bool):
        self._update_link_icon()
        self.spin_dist2.setEnabled(not checked)
        self.btn_lock_dist2.setEnabled(not checked)
        if checked:
            self.spin_dist2.setValue(self.spin_dist1.value())
            self.btn_lock_dist2.setChecked(self.btn_lock_dist1.isChecked())
            self._last_focused_spin = self.spin_dist1
            self.focus_primary_input()
        else:
            self.btn_lock_dist2.setChecked(False)
        self.parametersChanged.emit()

    def _on_lock_dist1_toggled(self, checked: bool):
        self._update_lock_icon(self.btn_lock_dist1)
        if self.btn_link.isChecked():
            self.btn_lock_dist2.setChecked(checked)

    def _on_dist1_changed(self, val: float):
        if self.btn_link.isChecked():
            self.spin_dist2.blockSignals(True)
            self.spin_dist2.setValue(val)
            self.spin_dist2.blockSignals(False)
        self.parametersChanged.emit()

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        evt_focus_in = getattr(QEvent.Type, "FocusIn", getattr(QEvent, "FocusIn", None))
        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        elif event.type() == evt_focus_in:
            for spin in (self.spin_radius, self.spin_segments, self.spin_dist1, self.spin_dist2):
                if obj == spin or (hasattr(spin, "lineEdit") and obj == spin.lineEdit()):
                    self._last_focused_spin = spin
                    for other in (self.spin_radius, self.spin_segments, self.spin_dist1, self.spin_dist2):
                        if other != spin and hasattr(other, "lineEdit") and other.lineEdit():
                            other.lineEdit().deselect()
                    QTimer.singleShot(0, lambda s=spin: self._select_all_spin(s))
        return super().eventFilter(obj, event)

    def _select_all_spin(self, spin):
        """Selects the entire text in a numeric stepper."""
        if hasattr(spin, "lineEdit") and spin.lineEdit():
            spin.lineEdit().selectAll()
        else:
            spin.selectAll()

    def _select_if_focused(self, spin):
        """Keeps text fully selected only if this spinbox currently has keyboard focus."""
        if spin.hasFocus() or (hasattr(spin, "lineEdit") and spin.lineEdit() and spin.lineEdit().hasFocus()):
            self._select_all_spin(spin)
        elif hasattr(spin, "lineEdit") and spin.lineEdit():
            spin.lineEdit().deselect()

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas without margin."""
        self.adjustSize()
        self.resize(self.minimumSizeHint())
        self.adjustSize()
        x = max(0, self.canvas.width() - self.width())
        y = 0
        self.move(x, y)

    def show_on_canvas(self):
        """Shows the widget on canvas and repositions to the top-right corner."""
        self.adapt_to_crs()
        self.reposition_to_default()
        self.show()
        self.raise_()
        self.focus_primary_input()

    def adapt_to_crs(self, crs: Optional[QgsCoordinateReferenceSystem] = None):
        """Adapts spinbox decimals, range, and step to geographic or projected CRS."""
        if crs is None and self.canvas:
            layer = self.canvas.currentLayer()
            if layer:
                crs = layer.crs()
            else:
                crs = self.canvas.mapSettings().destinationCrs()

        is_geo = crs.isGeographic() if crs and crs.isValid() else False

        if is_geo:
            decimals = constants.DECIMALS_GEO
            step = constants.STEP_GEO_VALUE
            min_val = constants.MIN_GEO_VALUE
            max_val = constants.MAX_GEO_VALUE
            for spin in (self.spin_radius, self.spin_dist1, self.spin_dist2):
                spin.setDecimals(decimals)
                spin.setRange(min_val, max_val)
                spin.setSingleStep(step)
                if spin.value() >= 0.5:
                    spin.setValue(constants.DEFAULT_RADIUS_GEO)
        else:
            decimals = constants.DECIMALS_METRIC
            step = constants.STEP_METRIC_VALUE
            min_val = constants.MIN_METRIC_VALUE
            max_val = constants.MAX_METRIC_VALUE
            for spin in (self.spin_radius, self.spin_dist1, self.spin_dist2):
                spin.setDecimals(decimals)
                spin.setRange(min_val, max_val)
                spin.setSingleStep(step)
                if spin.value() < constants.MIN_METRIC_VALUE:
                    spin.setValue(constants.DEFAULT_RADIUS_METRIC)

    # --- Properties & Methods ---
    @property
    def mode(self) -> str:
        if self.radio_fillet.isChecked():
            return self.MODE_FILLET
        elif self.radio_chamfer.isChecked():
            return self.MODE_CHAMFER
        return self.MODE_RESTORE

    @mode.setter
    def mode(self, value: str):
        if value == self.MODE_FILLET:
            self.radio_fillet.setChecked(True)
        elif value == self.MODE_CHAMFER:
            self.radio_chamfer.setChecked(True)
        elif value == self.MODE_RESTORE:
            self.radio_restore.setChecked(True)

    @property
    def radius(self) -> float:
        return self.spin_radius.value()

    def set_radius(self, val: float, block_signals: bool = False):
        if block_signals:
            self.spin_radius.blockSignals(True)
        self.spin_radius.setValue(val)
        self._select_if_focused(self.spin_radius)
        if block_signals:
            self.spin_radius.blockSignals(False)

    @property
    def segments_count(self) -> int:
        return self.spin_segments.value()

    @property
    def distance1(self) -> float:
        return self.spin_dist1.value()

    def set_distance1(self, val: float, block_signals: bool = False):
        if block_signals:
            self.spin_dist1.blockSignals(True)
            if self.btn_link.isChecked():
                self.spin_dist2.blockSignals(True)
        self.spin_dist1.setValue(val)
        self._select_if_focused(self.spin_dist1)
        if self.btn_link.isChecked():
            self.spin_dist2.setValue(val)
            self._select_if_focused(self.spin_dist2)
        if block_signals:
            self.spin_dist1.blockSignals(False)
            if self.btn_link.isChecked():
                self.spin_dist2.blockSignals(False)

    @property
    def distance2(self) -> float:
        return self.spin_dist1.value() if self.btn_link.isChecked() else self.spin_dist2.value()

    def set_distance2(self, val: float, block_signals: bool = False):
        if block_signals:
            self.spin_dist2.blockSignals(True)
        self.spin_dist2.setValue(val)
        self._select_if_focused(self.spin_dist2)
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
        return self.btn_lock_dist2.isChecked()

    @property
    def is_linked(self) -> bool:
        return self.btn_link.isChecked()

    def focus_primary_input(self):
        """Focuses and selects text in the active primary input box."""
        if self.mode == self.MODE_FILLET:
            spin = getattr(self, "_last_focused_spin", None)
            if spin not in (self.spin_radius, self.spin_segments):
                spin = self.spin_radius
        else:
            spin = getattr(self, "_last_focused_spin", None)
            if self.btn_link.isChecked() or spin not in (self.spin_dist1, self.spin_dist2):
                spin = self.spin_dist1

        self._last_focused_spin = spin

        # Clear selection on all other spinboxes so only the focused one is selected
        for other in (self.spin_radius, self.spin_segments, self.spin_dist1, self.spin_dist2):
            if other != spin and hasattr(other, "lineEdit") and other.lineEdit():
                other.lineEdit().deselect()

        spin.setFocus()
        if hasattr(spin, "lineEdit") and spin.lineEdit():
            spin.lineEdit().setFocus()
            spin.lineEdit().selectAll()
        else:
            spin.selectAll()

    def toggle_active_lock(self):
        """Toggles lock on the primary parameter."""
        if self.mode == self.MODE_FILLET:
            self.btn_lock_radius.toggle()
        else:
            self.btn_lock_dist1.toggle()

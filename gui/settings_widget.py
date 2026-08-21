import os
from typing import Optional

from qgis.core import QgsCoordinateReferenceSystem, QgsSettings
from qgis.PyQt.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QCursor, QIcon, QPixmap, QTransform
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from ..core import constants
except (ImportError, ValueError):
    from core import constants


class FilletSettingsWidget(QWidget):
    """Floating or dockable settings widget for Fillet & Chamfer parameters."""

    parametersChanged = pyqtSignal()
    applyToSelectedRequested = pyqtSignal()

    MODE_FILLET = constants.MODE_FILLET
    MODE_CHAMFER = constants.MODE_CHAMFER
    MODE_RESTORE = constants.MODE_RESTORE

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icons_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "resources", "icons"
        )
        self.setWindowTitle(self.tr("Параметри Fillet / Chamfer"))
        self._init_ui()

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

    def _update_link_icon(self):
        if self.btn_link.isChecked():
            self.btn_link.setIcon(self._get_rotated_icon("mActionLink.svg", 90, 32))
            self.btn_link.setToolTip(self.tr("Відстані зв'язані (d1 = d2)"))
        else:
            self.btn_link.setIcon(self._get_rotated_icon("mActionUnlink.svg", 90, 32))
            self.btn_link.setToolTip(self.tr("Відстані роздільні (d1 ≠ d2)"))

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Mode selection group
        mode_group = QGroupBox(self.tr("Режим операції"), self)
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(6, 6, 6, 6)
        mode_layout.setSpacing(12)

        self.radio_fillet = QRadioButton(self.tr("Скруглення (Fillet)"), mode_group)
        self.radio_fillet.setIcon(self._get_icon("fillet.svg"))
        self.radio_fillet.setChecked(True)

        self.radio_chamfer = QRadioButton(self.tr("Фаска (Chamfer)"), mode_group)
        self.radio_chamfer.setIcon(self._get_icon("chamfer.svg"))

        self.radio_restore = QRadioButton(self.tr("Відновлення кутів"), mode_group)
        self.radio_restore.setToolTip(self.tr("Видалити скруглення та фаски, відновивши гострі кути"))

        self.btn_group_mode = QButtonGroup(self)
        self.btn_group_mode.addButton(self.radio_fillet)
        self.btn_group_mode.addButton(self.radio_chamfer)
        self.btn_group_mode.addButton(self.radio_restore)

        mode_layout.addWidget(self.radio_fillet)
        mode_layout.addWidget(self.radio_chamfer)
        mode_layout.addWidget(self.radio_restore)
        mode_layout.addStretch()
        main_layout.addWidget(mode_group)

        # Stacked container for parameters
        policy_preferred = getattr(QSizePolicy.Policy, "Preferred", getattr(QSizePolicy, "Preferred", None))
        policy_maximum = getattr(QSizePolicy.Policy, "Maximum", getattr(QSizePolicy, "Maximum", None))
        policy_fixed = getattr(QSizePolicy.Policy, "Fixed", getattr(QSizePolicy, "Fixed", None))

        self.stacked_params = QStackedWidget(self)
        if policy_preferred is not None and policy_maximum is not None:
            self.stacked_params.setSizePolicy(policy_preferred, policy_maximum)

        # Fillet parameters page
        self.group_fillet = QGroupBox(self.tr("Параметри скруглення"), self)
        fillet_layout = QGridLayout(self.group_fillet)
        fillet_layout.setContentsMargins(6, 6, 6, 6)
        fillet_layout.setHorizontalSpacing(6)
        fillet_layout.setVerticalSpacing(6)

        lbl_radius = QLabel(self.tr("Радіус (R):"), self.group_fillet)
        self.spin_radius = QDoubleSpinBox(self.group_fillet)
        self.spin_radius.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_radius.setValue(constants.DEFAULT_RADIUS_METRIC)
        self.spin_radius.setDecimals(constants.DECIMALS_METRIC)
        self.spin_radius.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_radius.setMaximumWidth(160)
        fillet_layout.addWidget(lbl_radius, 0, 0)
        fillet_layout.addWidget(self.spin_radius, 0, 1)

        lbl_segments = QLabel(self.tr("Кількість сегментів дуги:"), self.group_fillet)
        self.spin_segments = QSpinBox(self.group_fillet)
        self.spin_segments.setRange(constants.MIN_SEGMENTS_COUNT, constants.MAX_SEGMENTS_COUNT)
        self.spin_segments.setValue(constants.DEFAULT_SEGMENTS_COUNT)
        self.spin_segments.setMaximumWidth(160)
        fillet_layout.addWidget(lbl_segments, 1, 0)
        fillet_layout.addWidget(self.spin_segments, 1, 1)

        self.stacked_params.addWidget(self.group_fillet)

        # Chamfer parameters page
        self.group_chamfer = QGroupBox(self.tr("Параметри фаски"), self)
        chamfer_layout = QGridLayout(self.group_chamfer)
        chamfer_layout.setContentsMargins(6, 6, 6, 6)
        chamfer_layout.setHorizontalSpacing(6)
        chamfer_layout.setVerticalSpacing(6)

        lbl_dist1 = QLabel(self.tr("Відстань 1 (d1):"), self.group_chamfer)
        self.spin_dist1 = QDoubleSpinBox(self.group_chamfer)
        self.spin_dist1.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_dist1.setValue(constants.DEFAULT_DIST1_METRIC)
        self.spin_dist1.setDecimals(constants.DECIMALS_METRIC)
        self.spin_dist1.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_dist1.setMaximumWidth(160)
        chamfer_layout.addWidget(lbl_dist1, 0, 0)
        chamfer_layout.addWidget(self.spin_dist1, 0, 1)

        lbl_dist2 = QLabel(self.tr("Відстань 2 (d2):"), self.group_chamfer)
        self.spin_dist2 = QDoubleSpinBox(self.group_chamfer)
        self.spin_dist2.setRange(constants.MIN_METRIC_VALUE, constants.MAX_METRIC_VALUE)
        self.spin_dist2.setValue(constants.DEFAULT_DIST2_METRIC)
        self.spin_dist2.setDecimals(constants.DECIMALS_METRIC)
        self.spin_dist2.setSingleStep(constants.STEP_METRIC_VALUE)
        self.spin_dist2.setMaximumWidth(160)
        self.spin_dist2.setEnabled(False)
        chamfer_layout.addWidget(lbl_dist2, 1, 0)
        chamfer_layout.addWidget(self.spin_dist2, 1, 1)

        # Link button spanning across Distance 1 and Distance 2 rows (rotated 90 degrees)
        self.btn_link = QToolButton(self.group_chamfer)
        self.btn_link.setCheckable(True)
        self.btn_link.setChecked(True)
        self.btn_link.setAutoRaise(True)
        self.btn_link.setFixedWidth(28)
        self.btn_link.setIconSize(QSize(24, 24))
        if policy_fixed is not None and policy_preferred is not None:
            self.btn_link.setSizePolicy(policy_fixed, policy_preferred)
        self._update_link_icon()
        chamfer_layout.addWidget(self.btn_link, 0, 2, 2, 1)

        self.stacked_params.addWidget(self.group_chamfer)

        # Restore parameters page
        self.group_restore = QGroupBox(self.tr("Параметри відновлення кутів"), self)
        restore_layout = QVBoxLayout(self.group_restore)
        restore_layout.setContentsMargins(6, 6, 6, 6)
        self.lbl_restore_desc = QLabel(
            self.tr("Видаляє всі виявлені скруглення та фаски, відновлюючи вихідні гострі кути для всіх вершин виділених об'єктів."),
            self.group_restore,
        )
        self.lbl_restore_desc.setWordWrap(True)
        self.lbl_restore_desc.setStyleSheet("color: #718096; font-size: 11px;")
        restore_layout.addWidget(self.lbl_restore_desc)
        self.stacked_params.addWidget(self.group_restore)

        main_layout.addWidget(self.stacked_params)

        # Batch apply button
        self.btn_apply_selected = QPushButton(self.tr("Застосувати до виділених об'єктів"), self)
        self.btn_apply_selected.setToolTip(self.tr("Застосувати скруглення або фаску до всіх вершин виділених об'єктів"))
        main_layout.addWidget(self.btn_apply_selected)

        # Bottom stretch to prevent elements stretching vertically
        main_layout.addStretch()

        # Spinbox cursors: arrow over buttons, I-beam only on lineEdit
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

        # Connections
        self.radio_fillet.toggled.connect(self._on_mode_changed)
        self.radio_chamfer.toggled.connect(self._on_mode_changed)
        self.radio_restore.toggled.connect(self._on_mode_changed)
        self.btn_link.toggled.connect(self._on_link_toggled)
        self.spin_dist1.valueChanged.connect(self._on_dist1_changed)

        self.spin_radius.valueChanged.connect(self.parametersChanged)
        self.spin_segments.valueChanged.connect(self.parametersChanged)
        self.spin_dist1.valueChanged.connect(self.parametersChanged)
        self.spin_dist2.valueChanged.connect(self.parametersChanged)
        self.btn_apply_selected.clicked.connect(self.applyToSelectedRequested)

        # Save settings on any parameter change
        self.parametersChanged.connect(self._save_settings)
        self.btn_link.toggled.connect(lambda _: self._save_settings())

        # Load persisted settings from user profile
        self._load_settings()

    def eventFilter(self, obj, event):
        focus_in = getattr(QEvent.Type, "FocusIn", getattr(QEvent, "FocusIn", None))
        if event.type() == focus_in:
            for spin in (self.spin_radius, self.spin_segments, self.spin_dist1, self.spin_dist2):
                if obj == spin or (hasattr(spin, "lineEdit") and obj == spin.lineEdit()):
                    QTimer.singleShot(0, lambda s=spin: self._select_all_spin(s))
        return super().eventFilter(obj, event)

    def _select_all_spin(self, spin):
        """Selects the entire text in a numeric stepper."""
        if hasattr(spin, "lineEdit") and spin.lineEdit():
            spin.lineEdit().selectAll()
        else:
            spin.selectAll()

    def _load_settings(self):
        self._is_loading = True
        try:
            s = QgsSettings()
            mode = s.value("plugins/fillet/batch_mode", self.MODE_FILLET, type=str)
            if mode == self.MODE_CHAMFER:
                self.radio_chamfer.setChecked(True)
            elif mode == self.MODE_RESTORE:
                self.radio_restore.setChecked(True)
            else:
                self.radio_fillet.setChecked(True)

            self.spin_radius.setValue(float(s.value("plugins/fillet/batch_radius", constants.DEFAULT_RADIUS_METRIC)))
            self.spin_segments.setValue(int(s.value("plugins/fillet/batch_segments", constants.DEFAULT_SEGMENTS_COUNT)))
            self.spin_dist1.setValue(float(s.value("plugins/fillet/batch_dist1", constants.DEFAULT_DIST1_METRIC)))
            self.spin_dist2.setValue(float(s.value("plugins/fillet/batch_dist2", constants.DEFAULT_DIST2_METRIC)))
            
            # Load link state (support either key)
            is_linked = s.value("plugins/fillet/batch_equal_dist", constants.DEFAULT_LINK_DISTANCES, type=bool)
            self.btn_link.setChecked(is_linked)
            self._update_link_icon()

            self._update_stacked_index()
            self.spin_dist2.setEnabled(not self.btn_link.isChecked())
        finally:
            self._is_loading = False

    def _save_settings(self):
        if getattr(self, "_is_loading", False):
            return
        s = QgsSettings()
        s.setValue("plugins/fillet/batch_mode", self.mode)
        s.setValue("plugins/fillet/batch_radius", self.spin_radius.value())
        s.setValue("plugins/fillet/batch_segments", self.spin_segments.value())
        s.setValue("plugins/fillet/batch_dist1", self.spin_dist1.value())
        s.setValue("plugins/fillet/batch_dist2", self.spin_dist2.value())
        s.setValue("plugins/fillet/batch_equal_dist", self.btn_link.isChecked())

    def _update_stacked_index(self):
        if self.mode == self.MODE_FILLET:
            self.stacked_params.setCurrentIndex(0)
        elif self.mode == self.MODE_CHAMFER:
            self.stacked_params.setCurrentIndex(1)
        else:
            self.stacked_params.setCurrentIndex(2)

    def _on_mode_changed(self):
        mode = self.mode
        if not getattr(self, "_is_loading", False):
            if mode == self.MODE_FILLET:
                self.spin_radius.setValue(self.spin_dist1.value())
            elif mode == self.MODE_CHAMFER:
                self.spin_dist1.setValue(self.spin_radius.value())
                if self.btn_link.isChecked():
                    self.spin_dist2.setValue(self.spin_radius.value())

        self._update_stacked_index()
        self._save_settings()
        self.parametersChanged.emit()

    def _on_link_toggled(self, checked: bool):
        self._update_link_icon()
        self.spin_dist2.setEnabled(not checked)
        if checked:
            self.spin_dist2.setValue(self.spin_dist1.value())
        self._save_settings()
        self.parametersChanged.emit()

    def _on_dist1_changed(self, val: float):
        if self.btn_link.isChecked():
            self.spin_dist2.setValue(val)

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

    @property
    def segments_count(self) -> int:
        return self.spin_segments.value()

    @property
    def distance1(self) -> float:
        return self.spin_dist1.value()

    @property
    def is_linked(self) -> bool:
        return self.btn_link.isChecked()

    @property
    def distance2(self) -> float:
        return self.spin_dist1.value() if self.btn_link.isChecked() else self.spin_dist2.value()

    def adapt_to_crs(self, crs: Optional[QgsCoordinateReferenceSystem] = None):
        """Adapts spinbox decimals, range, and step to geographic or projected CRS."""
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

    def set_editable_state(self, is_editable: bool):
        """Enables or disables the batch apply button based on layer editability."""
        self.btn_apply_selected.setEnabled(is_editable)
        if is_editable:
            self.btn_apply_selected.setToolTip(
                self.tr("Застосувати скруглення або фаску до всіх вершин виділених об'єктів")
            )
        else:
            self.btn_apply_selected.setToolTip(
                self.tr("Для пакетної обробки шар має бути у режимі редагування та містити виділені об'єкти")
            )

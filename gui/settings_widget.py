import os

from qgis.core import QgsSettings
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


class FilletSettingsWidget(QWidget):
    """Floating or dockable settings widget for Fillet & Chamfer parameters."""

    parametersChanged = pyqtSignal()
    applyToSelectedRequested = pyqtSignal()

    MODE_FILLET = "fillet"
    MODE_CHAMFER = "chamfer"

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
                if pm.width() < target_size or pm.height() < target_size:
                    pm = pm.scaled(
                        target_size,
                        target_size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                transform = QTransform().rotate(angle)
                rotated_pm = pm.transformed(transform, Qt.SmoothTransformation)
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

        self.btn_group_mode = QButtonGroup(self)
        self.btn_group_mode.addButton(self.radio_fillet)
        self.btn_group_mode.addButton(self.radio_chamfer)

        mode_layout.addWidget(self.radio_fillet)
        mode_layout.addWidget(self.radio_chamfer)
        mode_layout.addStretch()
        main_layout.addWidget(mode_group)

        # Stacked container for parameters
        self.stacked_params = QStackedWidget(self)

        # Fillet parameters page
        self.group_fillet = QGroupBox(self.tr("Параметри скруглення"), self)
        fillet_layout = QGridLayout(self.group_fillet)
        fillet_layout.setContentsMargins(6, 6, 6, 6)
        fillet_layout.setHorizontalSpacing(6)
        fillet_layout.setVerticalSpacing(6)

        lbl_radius = QLabel(self.tr("Радіус (R):"), self.group_fillet)
        self.spin_radius = QDoubleSpinBox(self.group_fillet)
        self.spin_radius.setRange(0.0001, 9999999.0)
        self.spin_radius.setValue(5.0)
        self.spin_radius.setDecimals(3)
        self.spin_radius.setSingleStep(1.0)
        self.spin_radius.setMaximumWidth(160)
        fillet_layout.addWidget(lbl_radius, 0, 0)
        fillet_layout.addWidget(self.spin_radius, 0, 1)

        lbl_segments = QLabel(self.tr("Кількість сегментів дуги:"), self.group_fillet)
        self.spin_segments = QSpinBox(self.group_fillet)
        self.spin_segments.setRange(2, 64)
        self.spin_segments.setValue(12)
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
        self.spin_dist1.setRange(0.0001, 9999999.0)
        self.spin_dist1.setValue(5.0)
        self.spin_dist1.setDecimals(3)
        self.spin_dist1.setSingleStep(1.0)
        self.spin_dist1.setMaximumWidth(160)
        chamfer_layout.addWidget(lbl_dist1, 0, 0)
        chamfer_layout.addWidget(self.spin_dist1, 0, 1)

        lbl_dist2 = QLabel(self.tr("Відстань 2 (d2):"), self.group_chamfer)
        self.spin_dist2 = QDoubleSpinBox(self.group_chamfer)
        self.spin_dist2.setRange(0.0001, 9999999.0)
        self.spin_dist2.setValue(5.0)
        self.spin_dist2.setDecimals(3)
        self.spin_dist2.setSingleStep(1.0)
        self.spin_dist2.setMaximumWidth(160)
        self.spin_dist2.setEnabled(False)
        chamfer_layout.addWidget(lbl_dist2, 1, 0)
        chamfer_layout.addWidget(self.spin_dist2, 1, 1)

        # Tall narrow Link button spanning across Distance 1 and Distance 2 rows (rotated 90 degrees)
        self.btn_link = QToolButton(self.group_chamfer)
        self.btn_link.setCheckable(True)
        self.btn_link.setChecked(True)
        self.btn_link.setAutoRaise(True)
        self.btn_link.setFixedWidth(28)
        self.btn_link.setIconSize(QSize(24, 24))
        self.btn_link.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._update_link_icon()
        chamfer_layout.addWidget(self.btn_link, 0, 2, 2, 1)

        self.stacked_params.addWidget(self.group_chamfer)
        main_layout.addWidget(self.stacked_params)

        # Batch apply button
        self.btn_apply_selected = QPushButton(self.tr("Застосувати до виділених об'єктів"), self)
        self.btn_apply_selected.setToolTip(self.tr("Застосувати скруглення або фаску до всіх вершин виділених об'єктів"))
        main_layout.addWidget(self.btn_apply_selected)

        # Spinbox cursors: arrow over buttons, I-beam only on lineEdit
        for spin in (self.spin_radius, self.spin_segments, self.spin_dist1, self.spin_dist2):
            spin.setCursor(QCursor(Qt.ArrowCursor))
            spin.installEventFilter(self)
            if hasattr(spin, "lineEdit") and spin.lineEdit():
                spin.lineEdit().setCursor(QCursor(Qt.IBeamCursor))
                spin.lineEdit().installEventFilter(self)
            for child in spin.findChildren(QWidget):
                if child != spin.lineEdit():
                    child.setCursor(QCursor(Qt.ArrowCursor))
        self.btn_link.setCursor(QCursor(Qt.ArrowCursor))

        # Connections
        self.radio_fillet.toggled.connect(self._on_mode_changed)
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
        if event.type() == QEvent.FocusIn:
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
            else:
                self.radio_fillet.setChecked(True)

            self.spin_radius.setValue(float(s.value("plugins/fillet/batch_radius", 5.0)))
            self.spin_segments.setValue(int(s.value("plugins/fillet/batch_segments", 12)))
            self.spin_dist1.setValue(float(s.value("plugins/fillet/batch_dist1", 5.0)))
            self.spin_dist2.setValue(float(s.value("plugins/fillet/batch_dist2", 5.0)))
            
            # Load link state (support either key)
            is_linked = s.value("plugins/fillet/batch_equal_dist", True, type=bool)
            self.btn_link.setChecked(is_linked)
            self._update_link_icon()

            self.stacked_params.setCurrentIndex(0 if self.mode == self.MODE_FILLET else 1)
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

    def _on_mode_changed(self, is_fillet: bool):
        self.stacked_params.setCurrentIndex(0 if is_fillet else 1)
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
        return self.MODE_FILLET if self.radio_fillet.isChecked() else self.MODE_CHAMFER

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

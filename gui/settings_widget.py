import os
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QSpinBox,
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

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Mode selection group
        mode_group = QGroupBox(self.tr("Режим операції"), self)
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(8, 8, 8, 8)
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

        # Fillet parameters
        self.group_fillet = QGroupBox(self.tr("Параметри скруглення"), self)
        fillet_layout = QFormLayout(self.group_fillet)
        fillet_layout.setContentsMargins(8, 8, 8, 8)
        fillet_layout.setSpacing(6)

        self.spin_radius = QDoubleSpinBox(self.group_fillet)
        self.spin_radius.setRange(0.0001, 9999999.0)
        self.spin_radius.setValue(5.0)
        self.spin_radius.setDecimals(3)
        self.spin_radius.setSingleStep(1.0)
        self.spin_radius.setMaximumWidth(160)
        fillet_layout.addRow(self.tr("Радіус (R):"), self.spin_radius)

        self.spin_segments = QSpinBox(self.group_fillet)
        self.spin_segments.setRange(2, 64)
        self.spin_segments.setValue(12)
        self.spin_segments.setMaximumWidth(160)
        fillet_layout.addRow(self.tr("Кількість сегментів дуги:"), self.spin_segments)

        main_layout.addWidget(self.group_fillet)

        # Chamfer parameters
        self.group_chamfer = QGroupBox(self.tr("Параметри фаски"), self)
        chamfer_layout = QFormLayout(self.group_chamfer)
        chamfer_layout.setContentsMargins(8, 8, 8, 8)
        chamfer_layout.setSpacing(6)

        self.spin_dist1 = QDoubleSpinBox(self.group_chamfer)
        self.spin_dist1.setRange(0.0001, 9999999.0)
        self.spin_dist1.setValue(5.0)
        self.spin_dist1.setDecimals(3)
        self.spin_dist1.setSingleStep(1.0)
        self.spin_dist1.setMaximumWidth(160)
        chamfer_layout.addRow(self.tr("Відстань 1 (d1):"), self.spin_dist1)

        self.spin_dist2 = QDoubleSpinBox(self.group_chamfer)
        self.spin_dist2.setRange(0.0001, 9999999.0)
        self.spin_dist2.setValue(5.0)
        self.spin_dist2.setDecimals(3)
        self.spin_dist2.setSingleStep(1.0)
        self.spin_dist2.setMaximumWidth(160)
        chamfer_layout.addRow(self.tr("Відстань 2 (d2):"), self.spin_dist2)

        self.chk_equal_dist = QCheckBox(self.tr("Однакові відстані (d1 = d2)"), self.group_chamfer)
        self.chk_equal_dist.setChecked(True)
        self.spin_dist2.setEnabled(False)
        chamfer_layout.addRow("", self.chk_equal_dist)

        main_layout.addWidget(self.group_chamfer)
        self.group_chamfer.setVisible(False)

        # Batch apply button
        self.btn_apply_selected = QPushButton(self.tr("Застосувати до виділених об'єктів"), self)
        self.btn_apply_selected.setToolTip(self.tr("Застосувати скруглення або фаску до всіх вершин виділених об'єктів"))
        main_layout.addWidget(self.btn_apply_selected)

        # Push everything to the top so it doesn't stretch vertically
        main_layout.addStretch(1)

        # Connections
        self.radio_fillet.toggled.connect(self._on_mode_changed)
        self.chk_equal_dist.toggled.connect(self._on_equal_dist_toggled)
        self.spin_dist1.valueChanged.connect(self._on_dist1_changed)

        self.spin_radius.valueChanged.connect(self.parametersChanged)
        self.spin_segments.valueChanged.connect(self.parametersChanged)
        self.spin_dist1.valueChanged.connect(self.parametersChanged)
        self.spin_dist2.valueChanged.connect(self.parametersChanged)
        self.btn_apply_selected.clicked.connect(self.applyToSelectedRequested)

    def _on_mode_changed(self, is_fillet: bool):
        self.group_fillet.setVisible(is_fillet)
        self.group_chamfer.setVisible(not is_fillet)
        self.parametersChanged.emit()

    def _on_equal_dist_toggled(self, checked: bool):
        self.spin_dist2.setEnabled(not checked)
        if checked:
            self.spin_dist2.setValue(self.spin_dist1.value())
        self.parametersChanged.emit()

    def _on_dist1_changed(self, val: float):
        if self.chk_equal_dist.isChecked():
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
    def distance2(self) -> float:
        return self.spin_dist2.value() if not self.chk_equal_dist.isChecked() else self.spin_dist1.value()

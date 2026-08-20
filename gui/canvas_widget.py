import os
from typing import Optional

from qgis.core import QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas, QgsSpinBox
from qgis.PyQt.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
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


class FilletCanvasWidget(QFrame):
    """Floating CAD-style panel inside the QGIS map canvas."""

    parametersChanged = pyqtSignal()
    modeChanged = pyqtSignal(str)
    commitRequested = pyqtSignal()

    MODE_FILLET = "fillet"
    MODE_CHAMFER = "chamfer"

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("FilletCanvasWidget")

        self._drag_pos: Optional[QPoint] = None
        self._user_moved = False
        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")

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

    def _init_ui(self):
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMinimumWidth(235)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Mode selection row
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(12)

        self.radio_fillet = QRadioButton(self.tr("Fillet"), self)
        self.radio_fillet.setIcon(self._get_icon("fillet.svg"))
        self.radio_fillet.setChecked(True)

        self.radio_chamfer = QRadioButton(self.tr("Chamfer"), self)
        self.radio_chamfer.setIcon(self._get_icon("chamfer.svg"))

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_fillet)
        self.mode_group.addButton(self.radio_chamfer)

        mode_layout.addWidget(self.radio_fillet)
        mode_layout.addWidget(self.radio_chamfer)
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
        self.spin_radius.setRange(0.001, 9999999.0)
        self.spin_radius.setValue(5.0)
        self.spin_radius.setDecimals(3)
        self.spin_radius.setSingleStep(1.0)
        self.spin_radius.setShowClearButton(True)

        self.btn_lock_radius = QToolButton(self.widget_fillet)
        self.btn_lock_radius.setCheckable(True)
        self.btn_lock_radius.setChecked(True)
        self.btn_lock_radius.setAutoRaise(True)
        self.btn_lock_radius.setToolTip(self.tr("Блокувати / розблокувати радіус"))
        self._update_lock_icon(self.btn_lock_radius)
        self.btn_lock_radius.toggled.connect(lambda: self._update_lock_icon(self.btn_lock_radius))

        grid_fillet.addWidget(self.lbl_radius, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        grid_fillet.addWidget(self.spin_radius, 0, 1)
        grid_fillet.addWidget(self.btn_lock_radius, 0, 2)

        # Row 1: Fillet segments
        self.lbl_segments = QLabel(self.tr("Fillet segments"), self.widget_fillet)
        self.spin_segments = QgsSpinBox(self.widget_fillet)
        self.spin_segments.setRange(2, 64)
        self.spin_segments.setValue(20)
        self.spin_segments.setShowClearButton(True)

        self.btn_lock_segments = QToolButton(self.widget_fillet)
        self.btn_lock_segments.setCheckable(True)
        self.btn_lock_segments.setChecked(True)
        self.btn_lock_segments.setEnabled(False)
        self.btn_lock_segments.setAutoRaise(True)
        self._update_lock_icon(self.btn_lock_segments)

        grid_fillet.addWidget(self.lbl_segments, 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
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
        self.spin_dist1.setRange(0.001, 9999999.0)
        self.spin_dist1.setValue(5.0)
        self.spin_dist1.setDecimals(3)
        self.spin_dist1.setSingleStep(1.0)
        self.spin_dist1.setShowClearButton(True)

        self.btn_lock_dist1 = QToolButton(self.widget_chamfer)
        self.btn_lock_dist1.setCheckable(True)
        self.btn_lock_dist1.setChecked(True)
        self.btn_lock_dist1.setAutoRaise(True)
        self.btn_lock_dist1.setToolTip(self.tr("Блокувати / розблокувати відстань 1"))
        self._update_lock_icon(self.btn_lock_dist1)
        self.btn_lock_dist1.toggled.connect(self._on_lock_dist1_toggled)

        grid_chamfer.addWidget(self.lbl_dist1, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        grid_chamfer.addWidget(self.spin_dist1, 0, 1)
        grid_chamfer.addWidget(self.btn_lock_dist1, 0, 2)

        # Row 1: Distance 2
        self.lbl_dist2 = QLabel(self.tr("Distance 2"), self.widget_chamfer)
        self.spin_dist2 = QgsDoubleSpinBox(self.widget_chamfer)
        self.spin_dist2.setRange(0.001, 9999999.0)
        self.spin_dist2.setValue(5.0)
        self.spin_dist2.setDecimals(3)
        self.spin_dist2.setSingleStep(1.0)
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

        grid_chamfer.addWidget(self.lbl_dist2, 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
        grid_chamfer.addWidget(self.spin_dist2, 1, 1)
        grid_chamfer.addWidget(self.btn_lock_dist2, 1, 2)

        # Tall narrow Link button spanning across Distance 1 and Distance 2 rows (rotated 90 degrees)
        self.btn_link = QToolButton(self.widget_chamfer)
        self.btn_link.setCheckable(True)
        self.btn_link.setChecked(True)
        self.btn_link.setAutoRaise(True)
        self.btn_link.setFixedWidth(28)
        self.btn_link.setIconSize(QSize(24, 24))
        self.btn_link.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._update_link_icon()
        self.btn_link.toggled.connect(self._on_link_toggled)

        grid_chamfer.addWidget(self.btn_link, 0, 3, 2, 1)

        self.stacked_controls.addWidget(self.widget_chamfer)
        main_layout.addWidget(self.stacked_controls)

        # Initial visibility & load persisted settings from user profile
        self._update_mode_visibility(self.MODE_FILLET)
        self._load_settings()

        # Signal connections
        self.radio_fillet.toggled.connect(self._on_radio_mode_toggled)
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
        self.setCursor(QCursor(Qt.ArrowCursor))
        for spin in (self.spin_radius, self.spin_segments, self.spin_dist1, self.spin_dist2):
            spin.setCursor(QCursor(Qt.ArrowCursor))
            if hasattr(spin, "lineEdit") and spin.lineEdit():
                spin.lineEdit().setCursor(QCursor(Qt.IBeamCursor))
            for child in spin.findChildren(QWidget):
                if child != spin.lineEdit():
                    child.setCursor(QCursor(Qt.ArrowCursor))
        for btn in (
            self.radio_fillet,
            self.radio_chamfer,
            self.btn_lock_radius,
            self.btn_lock_segments,
            self.btn_lock_dist1,
            self.btn_lock_dist2,
            self.btn_link,
        ):
            btn.setCursor(QCursor(Qt.ArrowCursor))

    def _apply_style(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
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
            else:
                self.radio_fillet.setChecked(True)

            self.spin_radius.setValue(float(s.value("plugins/fillet/radius", 5.0)))
            self.btn_lock_radius.setChecked(s.value("plugins/fillet/lock_radius", True, type=bool))
            self.spin_segments.setValue(int(s.value("plugins/fillet/segments", 20)))

            self.spin_dist1.setValue(float(s.value("plugins/fillet/dist1", 5.0)))
            self.btn_lock_dist1.setChecked(s.value("plugins/fillet/lock_dist1", True, type=bool))
            self.spin_dist2.setValue(float(s.value("plugins/fillet/dist2", 5.0)))
            self.btn_lock_dist2.setChecked(s.value("plugins/fillet/lock_dist2", True, type=bool))
            self.btn_link.setChecked(s.value("plugins/fillet/link_dist", True, type=bool))

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
        mode = self.MODE_FILLET if self.radio_fillet.isChecked() else self.MODE_CHAMFER
        self._update_mode_visibility(mode)
        self.modeChanged.emit(mode)
        self.parametersChanged.emit()
        self.focus_primary_input()

    def _update_mode_visibility(self, mode: str):
        is_fillet = mode == self.MODE_FILLET
        self.stacked_controls.setCurrentIndex(0 if is_fillet else 1)
        self._update_tab_order(is_fillet)
        self.reposition_to_default()

    def _update_tab_order(self, is_fillet: bool):
        if is_fillet:
            QWidget.setTabOrder(self.spin_radius, self.spin_segments)
            QWidget.setTabOrder(self.spin_segments, self.btn_lock_radius)
            QWidget.setTabOrder(self.btn_lock_radius, self.radio_fillet)
            QWidget.setTabOrder(self.radio_fillet, self.radio_chamfer)
        else:
            QWidget.setTabOrder(self.spin_dist1, self.spin_dist2)
            QWidget.setTabOrder(self.spin_dist2, self.btn_link)
            QWidget.setTabOrder(self.btn_link, self.btn_lock_dist1)
            QWidget.setTabOrder(self.btn_lock_dist1, self.btn_lock_dist2)
            QWidget.setTabOrder(self.btn_lock_dist2, self.radio_fillet)
            QWidget.setTabOrder(self.radio_fillet, self.radio_chamfer)

    def _on_link_toggled(self, checked: bool):
        self._update_link_icon()
        self.spin_dist2.setEnabled(not checked)
        self.btn_lock_dist2.setEnabled(not checked)
        if checked:
            self.spin_dist2.setValue(self.spin_dist1.value())
            self.btn_lock_dist2.setChecked(self.btn_lock_dist1.isChecked())
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
        if obj == self.canvas and event.type() == QEvent.Resize:
            self.reposition_to_default()
        return super().eventFilter(obj, event)

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
        self.reposition_to_default()
        self.show()
        self.raise_()
        self.focus_primary_input()

    # --- Properties & Methods ---
    @property
    def mode(self) -> str:
        return self.MODE_FILLET if self.radio_fillet.isChecked() else self.MODE_CHAMFER

    @mode.setter
    def mode(self, value: str):
        if value == self.MODE_FILLET:
            self.radio_fillet.setChecked(True)
        else:
            self.radio_chamfer.setChecked(True)

    @property
    def radius(self) -> float:
        return self.spin_radius.value()

    def set_radius(self, val: float, block_signals: bool = False):
        if block_signals:
            self.spin_radius.blockSignals(True)
        self.spin_radius.setValue(val)
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
        if self.btn_link.isChecked():
            self.spin_dist2.setValue(val)
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
        spin = self.spin_radius if self.mode == self.MODE_FILLET else self.spin_dist1
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

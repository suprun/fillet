# -*- coding: utf-8 -*-
"""
On-canvas CAD HUD widget for Fillet & Chamfer tool.
Displays directly inside the map canvas area with native theme styling.
"""

import os
from typing import Optional

from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas, QgsSpinBox
from qgis.PyQt.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont, QIcon, QPixmap, QTransform
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
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

        # Listen to canvas resize
        self.canvas.installEventFilter(self)

    def _get_icon(self, name: str) -> QIcon:
        try:
            from qgis.core import QgsApplication
            icon = QgsApplication.getThemeIcon(name)
            if not icon.isNull():
                return icon
        except Exception:
            pass

        path = os.path.join(self._icons_dir, name)
        if os.path.exists(path):
            return QIcon(path)
        return QIcon()

    def _get_rotated_icon(self, name: str, angle: float = 90.0, size: int = 32) -> QIcon:
        """Returns the theme icon rotated by given degrees."""
        icon = self._get_icon(name)
        if icon.isNull():
            return QIcon()
        pix = icon.pixmap(size, size)
        transform = QTransform().rotate(angle)
        rotated_pix = pix.transformed(transform, Qt.SmoothTransformation)
        return QIcon(rotated_pix)

    def _init_ui(self):
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMinimumWidth(235)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # Operation selection with horizontal radio buttons & icons
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

        # Grid for controls
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(4)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setColumnMinimumWidth(0, 95)

        # --- FILLET CONTROLS ---
        # Row 0: Radius
        self.lbl_radius = QLabel(self.tr("Radius"), self)
        self.spin_radius = QgsDoubleSpinBox(self)
        self.spin_radius.setRange(0.001, 9999999.0)
        self.spin_radius.setValue(5.0)
        self.spin_radius.setDecimals(3)
        self.spin_radius.setSingleStep(1.0)
        self.spin_radius.setShowClearButton(True)

        self.btn_lock_radius = QToolButton(self)
        self.btn_lock_radius.setCheckable(True)
        self.btn_lock_radius.setChecked(True)
        self.btn_lock_radius.setAutoRaise(True)
        self.btn_lock_radius.setToolTip(self.tr("Блокувати / розблокувати радіус"))
        self._update_lock_icon(self.btn_lock_radius)
        self.btn_lock_radius.toggled.connect(lambda: self._update_lock_icon(self.btn_lock_radius))

        self.grid.addWidget(self.lbl_radius, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.grid.addWidget(self.spin_radius, 0, 1)
        self.grid.addWidget(self.btn_lock_radius, 0, 2)

        # Row 1: Fillet segments
        self.lbl_segments = QLabel(self.tr("Fillet segments"), self)
        self.spin_segments = QgsSpinBox(self)
        self.spin_segments.setRange(2, 64)
        self.spin_segments.setValue(20)
        self.spin_segments.setShowClearButton(True)

        self.btn_lock_segments = QToolButton(self)
        self.btn_lock_segments.setCheckable(True)
        self.btn_lock_segments.setChecked(True)
        self.btn_lock_segments.setEnabled(False)
        self.btn_lock_segments.setAutoRaise(True)
        self._update_lock_icon(self.btn_lock_segments)

        self.grid.addWidget(self.lbl_segments, 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.grid.addWidget(self.spin_segments, 1, 1)
        self.grid.addWidget(self.btn_lock_segments, 1, 2)

        # --- CHAMFER CONTROLS ---
        # Row 0 (Chamfer): Distance 1
        self.lbl_dist1 = QLabel(self.tr("Distance 1"), self)
        self.spin_dist1 = QgsDoubleSpinBox(self)
        self.spin_dist1.setRange(0.001, 9999999.0)
        self.spin_dist1.setValue(5.0)
        self.spin_dist1.setDecimals(3)
        self.spin_dist1.setSingleStep(1.0)
        self.spin_dist1.setShowClearButton(True)

        self.btn_lock_dist1 = QToolButton(self)
        self.btn_lock_dist1.setCheckable(True)
        self.btn_lock_dist1.setChecked(True)
        self.btn_lock_dist1.setAutoRaise(True)
        self.btn_lock_dist1.setToolTip(self.tr("Блокувати / розблокувати відстань 1"))
        self._update_lock_icon(self.btn_lock_dist1)
        self.btn_lock_dist1.toggled.connect(self._on_lock_dist1_toggled)

        self.grid.addWidget(self.lbl_dist1, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.grid.addWidget(self.spin_dist1, 0, 1)
        self.grid.addWidget(self.btn_lock_dist1, 0, 2)

        # Row 1 (Chamfer): Distance 2
        self.lbl_dist2 = QLabel(self.tr("Distance 2"), self)
        self.spin_dist2 = QgsDoubleSpinBox(self)
        self.spin_dist2.setRange(0.001, 9999999.0)
        self.spin_dist2.setValue(5.0)
        self.spin_dist2.setDecimals(3)
        self.spin_dist2.setSingleStep(1.0)
        self.spin_dist2.setShowClearButton(True)
        self.spin_dist2.setEnabled(False)

        self.btn_lock_dist2 = QToolButton(self)
        self.btn_lock_dist2.setCheckable(True)
        self.btn_lock_dist2.setChecked(True)
        self.btn_lock_dist2.setEnabled(False)
        self.btn_lock_dist2.setAutoRaise(True)
        self.btn_lock_dist2.setToolTip(self.tr("Блокувати / розблокувати відстань 2"))
        self._update_lock_icon(self.btn_lock_dist2)
        self.btn_lock_dist2.toggled.connect(lambda: self._update_lock_icon(self.btn_lock_dist2))

        self.grid.addWidget(self.lbl_dist2, 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.grid.addWidget(self.spin_dist2, 1, 1)
        self.grid.addWidget(self.btn_lock_dist2, 1, 2)

        # Tall narrow Link button spanning across Distance 1 and Distance 2 rows (rotated 90 degrees, 2x enlarged icon)
        self.btn_link = QToolButton(self)
        self.btn_link.setCheckable(True)
        self.btn_link.setChecked(True)
        self.btn_link.setAutoRaise(True)
        self.btn_link.setFixedWidth(28)
        self.btn_link.setIconSize(QSize(24, 24))
        self.btn_link.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._update_link_icon()
        self.btn_link.toggled.connect(self._on_link_toggled)

        self.grid.addWidget(self.btn_link, 0, 3, 2, 1)

        main_layout.addLayout(self.grid)

        # Initial visibility
        self._update_mode_visibility(self.MODE_FILLET)

        # Signal connections
        self.radio_fillet.toggled.connect(self._on_radio_mode_toggled)
        self.spin_radius.valueChanged.connect(self.parametersChanged)
        self.spin_segments.valueChanged.connect(self.parametersChanged)
        self.spin_dist1.valueChanged.connect(self._on_dist1_changed)
        self.spin_dist2.valueChanged.connect(self.parametersChanged)

        # Enter key in spinboxes requests commit
        if hasattr(self.spin_radius, "lineEdit") and self.spin_radius.lineEdit():
            self.spin_radius.lineEdit().returnPressed.connect(self.commitRequested.emit)
        if hasattr(self.spin_dist1, "lineEdit") and self.spin_dist1.lineEdit():
            self.spin_dist1.lineEdit().returnPressed.connect(self.commitRequested.emit)
        if hasattr(self.spin_dist2, "lineEdit") and self.spin_dist2.lineEdit():
            self.spin_dist2.lineEdit().returnPressed.connect(self.commitRequested.emit)

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

    def _on_radio_mode_toggled(self, checked: bool):
        mode = self.MODE_FILLET if self.radio_fillet.isChecked() else self.MODE_CHAMFER
        self._update_mode_visibility(mode)
        self.modeChanged.emit(mode)
        self.parametersChanged.emit()

    def _update_mode_visibility(self, mode: str):
        is_fillet = mode == self.MODE_FILLET

        # Fillet elements
        self.lbl_radius.setVisible(is_fillet)
        self.spin_radius.setVisible(is_fillet)
        self.btn_lock_radius.setVisible(is_fillet)
        self.lbl_segments.setVisible(is_fillet)
        self.spin_segments.setVisible(is_fillet)
        self.btn_lock_segments.setVisible(is_fillet)

        # Chamfer elements
        self.lbl_dist1.setVisible(not is_fillet)
        self.spin_dist1.setVisible(not is_fillet)
        self.btn_lock_dist1.setVisible(not is_fillet)
        self.lbl_dist2.setVisible(not is_fillet)
        self.spin_dist2.setVisible(not is_fillet)
        self.btn_lock_dist2.setVisible(not is_fillet)
        self.btn_link.setVisible(not is_fillet)

        self.reposition_to_default()

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
        x = max(0, self.canvas.width() - self.width())
        y = 0
        self.move(x, y)

    def show_on_canvas(self):
        """Shows the widget on canvas and repositions to the top-right corner."""
        self.reposition_to_default()
        self.show()
        self.raise_()

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
        return self.spin_dist2.value() if not self.btn_link.isChecked() else self.spin_dist1.value()

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
        if self.mode == self.MODE_FILLET:
            self.spin_radius.setFocus()
            self.spin_radius.selectAll()
        else:
            self.spin_dist1.setFocus()
            self.spin_dist1.selectAll()

    def toggle_active_lock(self):
        """Toggles lock on the primary parameter."""
        if self.mode == self.MODE_FILLET:
            self.btn_lock_radius.toggle()
        else:
            self.btn_lock_dist1.toggle()

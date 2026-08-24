# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Mirror tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import os
from typing import Optional

from qgis.core import QgsSettings
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QFont, QIcon
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class MirrorCanvasWidget(QFrame):
    """Floating CAD HUD widget on the map canvas for interactive geometry mirroring."""

    commitRequested = pyqtSignal()
    resetRequested = pyqtSignal()
    copyModeChanged = pyqtSignal(bool)
    stepSnapChanged = pyqtSignal(float)

    STEP_FIRST_POINT = 0
    STEP_SECOND_POINT = 1

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("MirrorCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_FIRST_POINT

        self._init_ui()
        self._apply_style()
        self.canvas.installEventFilter(self)

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
        self.set_step(self.STEP_FIRST_POINT)
        main_layout.addWidget(self.lbl_step)

        # Grid for Snap Angle and Options
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        # Row 0: Snap axis step
        self.lbl_snap = QLabel(self.tr("Прив'язка осі:"), self)
        self.combo_snap = QComboBox(self)
        self.combo_snap.addItem(self.tr("Вільний (Free)"), 0.0)
        self.combo_snap.addItem(self.tr("15°"), 15.0)
        self.combo_snap.addItem(self.tr("45°"), 45.0)
        self.combo_snap.addItem(self.tr("90° (Орто)"), 90.0)

        grid.addWidget(self.lbl_snap, 0, 0)
        grid.addWidget(self.combo_snap, 0, 1)

        main_layout.addLayout(grid)

        # Checkbox: Copy original feature
        self.chk_copy = QCheckBox(self.tr("Зберегти копію (Copy)"), self)
        self.chk_copy.setToolTip(self.tr("Створює дзеркальну копію виділених об'єктів, залишаючи оригінал"))
        self.chk_copy.setChecked(False)
        self.chk_copy.toggled.connect(self.copyModeChanged.emit)
        main_layout.addWidget(self.chk_copy)

        # Cursors
        arrow_cursor = getattr(Qt.CursorShape, "ArrowCursor", getattr(Qt, "ArrowCursor", None))
        if arrow_cursor is not None:
            self.setCursor(QCursor(arrow_cursor))
            self.combo_snap.setCursor(QCursor(arrow_cursor))
            self.chk_copy.setCursor(QCursor(arrow_cursor))

        self.combo_snap.currentIndexChanged.connect(self._on_snap_changed)
        self._load_settings()

    def _apply_style(self):
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_plain = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_plain is not None:
            self.setFrameShadow(shadow_plain)
        self.setAutoFillBackground(True)

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        return super().eventFilter(obj, event)

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_FIRST_POINT:
            self.lbl_step.setText(self.tr("1. Вкажіть першу точку осі"))
        elif step == self.STEP_SECOND_POINT:
            self.lbl_step.setText(self.tr("2. Вкажіть другу точку осі"))
        self.reposition_to_default()

    def _on_snap_changed(self):
        step_val = float(self.combo_snap.currentData())
        self.stepSnapChanged.emit(step_val)

    @property
    def is_copy_mode(self) -> bool:
        return self.chk_copy.isChecked()

    @property
    def snap_step(self) -> float:
        return float(self.combo_snap.currentData())

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas."""
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
        s = QgsSettings()
        snap_val = float(s.value("plugins/fillet/mirror_snap_step", 0.0))
        idx = self.combo_snap.findData(snap_val)
        if idx >= 0:
            self.combo_snap.setCurrentIndex(idx)
        self.chk_copy.setChecked(s.value("plugins/fillet/mirror_copy_mode", False, type=bool))

    def save_settings(self):
        s = QgsSettings()
        s.setValue("plugins/fillet/mirror_snap_step", self.snap_step)
        s.setValue("plugins/fillet/mirror_copy_mode", self.is_copy_mode)

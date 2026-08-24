# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for Two-Line Fillet & Chamfer with Join / Merge.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

from typing import Optional

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QEvent, Qt
from qgis.PyQt.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class TwoLineCanvasWidget(QFrame):
    """Floating on-canvas step-by-step HUD widget for Two-Line Fillet & Chamfer."""

    STEP_FIRST_LINE = 1
    STEP_SECOND_LINE = 2

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("TwoLineCanvasWidget")
        self._current_step = self.STEP_FIRST_LINE

        self._init_ui()
        self._apply_style()

        # Canvas resize tracker
        self.canvas.installEventFilter(self)

    def _init_ui(self):
        sub_window = getattr(Qt.WindowType, "SubWindow", getattr(Qt, "SubWindow", 0))
        frameless = getattr(Qt.WindowType, "FramelessWindowHint", getattr(Qt, "FramelessWindowHint", 0))
        if sub_window or frameless:
            self.setWindowFlags(sub_window | frameless)
        wa_show = getattr(Qt.WidgetAttribute, "WA_ShowWithoutActivating", getattr(Qt, "WA_ShowWithoutActivating", None))
        if wa_show is not None:
            self.setAttribute(wa_show, True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(4)

        # Step indicator label
        self.lbl_step = QLabel(self)
        self.lbl_step.setWordWrap(False)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet("color: #1e3a8a; background-color: #dbeafe; border-radius: 4px; padding: 4px 8px;")
        self.set_step(self.STEP_FIRST_LINE)
        main_layout.addWidget(self.lbl_step)

    def _apply_style(self):
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_plain = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_plain is not None:
            self.setFrameShadow(shadow_plain)
        self.setAutoFillBackground(True)

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_FIRST_LINE:
            self.lbl_step.setText(self.tr("1. Вкажіть першу лінію"))
        elif step == self.STEP_SECOND_LINE:
            self.lbl_step.setText(self.tr("2. Вкажіть другу лінію"))
        self.reposition_to_default()

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas without clipping."""
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
        """Shows the widget on canvas and repositions to the top-right corner."""
        self.reposition_to_default()
        self.show()
        self.raise_()

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        return super().eventFilter(obj, event)

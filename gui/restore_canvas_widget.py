# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for Corner Restoration (Unfillet / Unchamfer) tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

from typing import Optional

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class RestoreCanvasWidget(QFrame):
    """Floating on-canvas step-by-step HUD widget for Two-Edge Corner Restoration."""

    STEP_FIRST_EDGE = 1
    STEP_SECOND_EDGE = 2

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("RestoreCanvasWidget")
        self._current_step = self.STEP_FIRST_EDGE
        self._drag_pos: Optional[QPoint] = None
        self._user_moved = False

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
        self.setMinimumWidth(230)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(4)

        # Step indicator label
        self.lbl_step = QLabel(self)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet(
            "color: #7c2d12; background-color: #ffedd5; border: 1px solid #fed7aa; border-radius: 4px; padding: 4px 8px;"
        )
        self.set_step(self.STEP_FIRST_EDGE)
        main_layout.addWidget(self.lbl_step)

        # Hint subtext
        self.lbl_hint = QLabel(self.tr("ПКМ / Esc — скасувати / крок назад"), self)
        hint_font = self.lbl_hint.font()
        hint_font.setPointSize(max(7, hint_font.pointSize() - 2))
        self.lbl_hint.setFont(hint_font)
        self.lbl_hint.setStyleSheet("color: #64748b; padding-left: 2px;")
        main_layout.addWidget(self.lbl_hint)

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
        if step == self.STEP_FIRST_EDGE:
            self.lbl_step.setText(self.tr("1. Вкажіть перше ребро кута"))
        elif step == self.STEP_SECOND_EDGE:
            self.lbl_step.setText(self.tr("2. Вкажіть суміжне друге ребро"))

    def reposition_to_default(self):
        """Positions the widget firmly at top-right corner of the map canvas."""
        self.adjustSize()
        self.resize(self.minimumSizeHint())
        self.adjustSize()
        x = max(0, self.canvas.width() - self.width())
        y = 0
        self.move(x, y)

    def show_on_canvas(self):
        """Shows and repositions widget on canvas."""
        if not self._user_moved:
            self.reposition_to_default()
        self.show()
        self.raise_()

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        if obj == self.canvas and event.type() == evt_resize:
            if not self._user_moved:
                self.reposition_to_default()
        return super().eventFilter(obj, event)

    # Draggable canvas widget support
    def mousePressEvent(self, event):
        left_btn = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
        if event.button() == left_btn:
            pos_accessor = getattr(event, "position", None)
            local_pos = pos_accessor() if callable(pos_accessor) else event.pos()
            self._drag_pos = local_pos.toPoint() if hasattr(local_pos, "toPoint") else local_pos
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        left_btn_mask = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
        if self._drag_pos is not None and (event.buttons() & left_btn_mask):
            pos_accessor = getattr(event, "position", None)
            local_pos = pos_accessor() if callable(pos_accessor) else event.pos()
            pt = local_pos.toPoint() if hasattr(local_pos, "toPoint") else local_pos
            delta = pt - self._drag_pos
            new_pos = self.pos() + delta
            x = max(0, min(new_pos.x(), self.canvas.width() - self.width()))
            y = max(0, min(new_pos.y(), self.canvas.height() - self.height()))
            self.move(x, y)
            self._user_moved = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

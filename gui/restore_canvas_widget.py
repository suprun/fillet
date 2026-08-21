# -*- coding: utf-8 -*-
"""
Floating on-canvas HUD widget for the Restore (Unfillet / Unchamfer) CAD tool.
"""

import os
from typing import Optional

from qgis.core import QgsSettings
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QIcon
from qgis.PyQt.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RestoreCanvasWidget(QFrame):
    """Floating CAD HUD on map canvas for Corner Restoration."""

    cancelRequested = pyqtSignal()

    def __init__(self, canvas: QgsMapCanvas, parent: Optional[QWidget] = None):
        super().__init__(parent if parent else canvas)
        self.canvas = canvas

        self.setObjectName("RestoreCanvasWidget")
        self._apply_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.lbl_icon = QLabel(self)
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "resources",
            "icons",
            "mActionRestoreCorners.svg",
        )
        if os.path.exists(icon_path):
            self.lbl_icon.setPixmap(QIcon(icon_path).pixmap(QSize(18, 18)))
        header_layout.addWidget(self.lbl_icon)

        self.lbl_title = QLabel(self.tr("Відновлення гострого кута"), self)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #1e293b;")
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Step instruction prompt
        self.lbl_prompt = QLabel(self.tr("Крок 1: Клікніть на перше ребро кута"), self)
        self.lbl_prompt.setStyleSheet("color: #475569; font-size: 11px;")
        self.lbl_prompt.setWordWrap(True)
        main_layout.addWidget(self.lbl_prompt)

        # Bottom row with hint / cancel button
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)

        self.lbl_hint = QLabel(self.tr("ПКМ або Esc — скасувати"), self)
        self.lbl_hint.setStyleSheet("color: #94a3b8; font-size: 10px; font-style: italic;")
        btn_layout.addWidget(self.lbl_hint)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(self.tr("Скасувати"), self)
        self.btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus if hasattr(Qt, "FocusPolicy") else Qt.NoFocus)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                color: #334155;
            }
            QPushButton:hover {
                background: #e2e8f0;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background: #cbd5e1;
            }
        """)
        self.btn_cancel.clicked.connect(self.cancelRequested.emit)
        btn_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(btn_layout)

        if self.canvas:
            self.canvas.installEventFilter(self)

    def _apply_style(self):
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_raised = getattr(QFrame.Shadow, "Raised", getattr(QFrame, "Raised", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_raised is not None:
            self.setFrameShadow(shadow_raised)
        self.setAutoFillBackground(True)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        self.setStyleSheet("""
            QFrame#RestoreCanvasWidget {
                background-color: rgba(255, 255, 255, 0.94);
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)

    def set_step(self, step: int):
        """Updates the step instruction text."""
        if step == 1:
            self.lbl_prompt.setText(self.tr("Крок 1: Клікніть на перше ребро кута"))
            self.btn_cancel.setEnabled(False)
        elif step == 2:
            self.lbl_prompt.setText(self.tr("Крок 2: Клікніть на суміжне друге ребро для зведення в кут"))
            self.btn_cancel.setEnabled(True)

    def show_on_canvas(self):
        self.set_step(1)
        self.reposition_to_default()
        self.show()
        self.raise_()

    def reposition_to_default(self):
        if not self.canvas:
            return
        self.adjustSize()
        x = max(10, self.canvas.width() - self.width() - 20)
        y = 20
        self.move(x, y)

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        return super().eventFilter(obj, event)

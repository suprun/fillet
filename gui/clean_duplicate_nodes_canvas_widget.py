# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for Clean Duplicate Nodes tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import os
from typing import Optional

from qgis.core import QgsCoordinateReferenceSystem, QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, QRegularExpression, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPixmap,
    QRegularExpressionValidator,
    QTransform,
)
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class CleanDuplicateNodesCanvasWidget(QFrame):
    """Floating CAD HUD widget on the map canvas for interactive duplicate nodes cleaning."""

    toleranceChanged = pyqtSignal(float)
    resetRequested = pyqtSignal()

    STEP_HOVER_SELECT = 0
    STEP_CONTEXT_MENU = 1

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("CleanDuplicateNodesCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_HOVER_SELECT
        self._is_loading = False

        self._init_ui()
        self._apply_style()
        self.canvas.installEventFilter(self)

    def _get_icon(self, name: str) -> QIcon:
        path = os.path.join(self._icons_dir, name)
        if os.path.exists(path):
            return QIcon(path)
        return QIcon()

    def _init_ui(self):
        sub_window = getattr(Qt.WindowType, "SubWindow", getattr(Qt, "SubWindow", 0))
        frameless = getattr(Qt.WindowType, "FramelessWindowHint", getattr(Qt, "FramelessWindowHint", 0))
        if sub_window or frameless:
            self.setWindowFlags(sub_window | frameless)
        wa_show = getattr(Qt.WidgetAttribute, "WA_ShowWithoutActivating", getattr(Qt, "WA_ShowWithoutActivating", None))
        if wa_show is not None:
            self.setAttribute(wa_show, True)
        self.setMinimumWidth(250)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Step indicator label
        self.lbl_step = QLabel(self)
        self.lbl_step.setWordWrap(False)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet("color: #1e3a8a; background-color: #dbeafe; border-radius: 4px; padding: 4px 8px;")
        self.set_step(self.STEP_HOVER_SELECT)
        main_layout.addWidget(self.lbl_step)

        # Tolerance row
        row_tol = QHBoxLayout()
        row_tol.setSpacing(4)

        self.lbl_tol = QLabel(self.tr("Толерантність:"), self)
        self.lbl_tol.setStyleSheet("color: #334155; font-size: 11px; font-weight: 500;")
        row_tol.addWidget(self.lbl_tol)

        self.spn_tolerance = QgsDoubleSpinBox(self)
        self.spn_tolerance.setRange(0.000001, 1000.0)
        self.spn_tolerance.setDecimals(6)
        self.spn_tolerance.setSingleStep(0.001)
        self.spn_tolerance.setValue(0.0001)
        self.spn_tolerance.setSuffix(" " + self.tr("м"))
        self.spn_tolerance.setToolTip(self.tr("Максимальна відстань між вузлами для вважання їх дублями"))
        self.spn_tolerance.valueChanged.connect(self._on_tolerance_changed)
        row_tol.addWidget(self.spn_tolerance, 1)

        main_layout.addLayout(row_tol)

        # Info tip label
        self.lbl_info = QLabel(self)
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: #64748b; font-size: 10px; padding: 2px 4px;")
        self.lbl_info.setText(self.tr("ЛКМ по тілу: видалити всі дублі\nЛКМ по вузлу: меню вибору з прев'ю"))
        main_layout.addWidget(self.lbl_info)

        self.adjustSize()

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#CleanDuplicateNodesCanvasWidget {
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
            QgsDoubleSpinBox {
                border: 1px solid #94a3b8;
                border-radius: 3px;
                padding: 2px 4px;
                background: #ffffff;
                font-weight: 600;
                color: #0f172a;
            }
            QgsDoubleSpinBox:focus {
                border: 1px solid #2563eb;
            }
        """)

    @property
    def tolerance(self) -> float:
        return self.spn_tolerance.value()

    def set_tolerance(self, val: float, block_signals: bool = False):
        if block_signals:
            self.spn_tolerance.blockSignals(True)
        self.spn_tolerance.setValue(val)
        if block_signals:
            self.spn_tolerance.blockSignals(False)

    def _on_tolerance_changed(self, val: float):
        self.toleranceChanged.emit(val)

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_HOVER_SELECT:
            self.lbl_step.setText(self.tr("Крок 1: Наведіть на об'єкт або вузол"))
        elif step == self.STEP_CONTEXT_MENU:
            self.lbl_step.setText(self.tr("Крок 2: Оберіть варіант у меню"))
        self.adjustSize()
        self.update_position()

    def update_position(self):
        if not self.canvas:
            return
        canvas_width = self.canvas.width()
        w = self.sizeHint().width()
        x = max(10, canvas_width - w - 20)
        y = 20
        self.move(x, y)

    def eventFilter(self, obj, event):
        if obj == self.canvas and event.type() == QEvent.Type.Resize:
            self.update_position()
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.update_position()

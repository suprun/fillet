# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Explode Line tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import os
from typing import Optional

from qgis.core import QgsSettings, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPixmap,
    QTransform,
)
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ExplodeCanvasWidget(QFrame):
    """Floating CAD HUD widget on the map canvas for interactive Explode Line tool."""

    saveAsMultipartChanged = pyqtSignal(bool)
    commitRequested = pyqtSignal()
    resetRequested = pyqtSignal()

    STEP_SELECT_LINE = 0

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("ExplodeCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_SELECT_LINE
        self._supports_multipart = False

        self._init_ui()
        self._apply_style()
        self.canvas.installEventFilter(self)
        self.load_settings()

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
        self.setMinimumWidth(240)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # Step indicator label
        self.lbl_step = QLabel(self)
        self.lbl_step.setWordWrap(False)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet("color: #1e3a8a; background-color: #dbeafe; border-radius: 4px; padding: 4px 8px;")
        self.lbl_step.setText(self.tr("1. Оберіть лінію для розбиття на відрізки"))
        main_layout.addWidget(self.lbl_step)

        # Multipart checkbox row
        self.chk_multipart = QCheckBox(self.tr("Зберегти як складену геометрію (multipart)"), self)
        self.chk_multipart.setToolTip(self.tr("Зберегти розбиті відрізки як частини єдиного об'єкта (MultiLineString)"))
        self.chk_multipart.toggled.connect(self._on_multipart_toggled)
        main_layout.addWidget(self.chk_multipart)

        # Batch button for selected features
        self.btn_explode_selected = QPushButton(self.tr("Розбити виділені лінії"), self)
        self.btn_explode_selected.setCursor(QCursor(getattr(Qt.CursorShape, "PointingHandCursor", getattr(Qt, "PointingHandCursor", 13))))
        self.btn_explode_selected.clicked.connect(self.commitRequested.emit)
        self.btn_explode_selected.hide()
        main_layout.addWidget(self.btn_explode_selected)

    def _apply_style(self):
        shape_panel = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow_plain = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape_panel is not None:
            self.setFrameShape(shape_panel)
        if shadow_plain is not None:
            self.setFrameShadow(shadow_plain)
        self.setAutoFillBackground(True)

    def update_layer_capabilities(self, layer: Optional[QgsVectorLayer]):
        """Updates multipart checkbox availability based on current layer geometry type."""
        if not layer or not layer.isValid():
            self._supports_multipart = False
            self.chk_multipart.setEnabled(False)
            self.chk_multipart.setToolTip(self.tr("Немає активного шару"))
            self.btn_explode_selected.hide()
            self.reposition_to_default()
            return

        is_multi = QgsWkbTypes.isMultiType(layer.wkbType())
        self._supports_multipart = is_multi
        self.chk_multipart.setEnabled(is_multi)
        if is_multi:
            self.chk_multipart.setToolTip(self.tr("Зберегти розбиті відрізки як частини єдиного складеного об'єкта (MultiLineString)"))
        else:
            self.chk_multipart.setChecked(False)
            self.chk_multipart.setToolTip(self.tr("Шар є SinglePart (LineString) і не підтримує multipart"))

        # Update selected count
        sel_count = layer.selectedFeatureCount()
        if sel_count > 0:
            self.btn_explode_selected.setText(self.tr("Розбити виділені лінії ({})").format(sel_count))
            self.btn_explode_selected.show()
        else:
            self.btn_explode_selected.hide()

        self.reposition_to_default()

    def _on_multipart_toggled(self, checked: bool):
        self.saveAsMultipartChanged.emit(checked)
        self.save_settings()

    @property
    def is_save_as_multipart(self) -> bool:
        return self.chk_multipart.isChecked() and self.chk_multipart.isEnabled()

    def set_save_as_multipart(self, enabled: bool):
        if self.chk_multipart.isEnabled():
            self.chk_multipart.setChecked(enabled)

    def toggle_multipart(self):
        if self.chk_multipart.isEnabled():
            self.chk_multipart.setChecked(not self.chk_multipart.isChecked())

    def save_settings(self):
        s = QgsSettings()
        s.setValue("FilletPlugin/Explode/SaveAsMultipart", self.chk_multipart.isChecked())

    def load_settings(self):
        s = QgsSettings()
        saved = s.value("FilletPlugin/Explode/SaveAsMultipart", False, type=bool)
        if self.chk_multipart.isEnabled():
            self.chk_multipart.setChecked(saved)

    def reposition_to_default(self):
        """Positions widget firmly at top-right corner of the canvas."""
        self.adjustSize()
        hint = self.sizeHint()
        lbl_hint = self.lbl_step.sizeHint()
        chk_hint = self.chk_multipart.sizeHint()
        w = max(hint.width(), lbl_hint.width() + 24, chk_hint.width() + 24, 240)
        h = max(hint.height(), 80)
        self.resize(w, h)
        self.adjustSize()
        x = max(0, self.canvas.width() - self.width())
        y = 0
        self.move(x, y)

    def show_on_canvas(self):
        self.reposition_to_default()
        self.show()
        self.raise_()

    def eventFilter(self, obj, event):
        evt_resize = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        evt_key_press = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None))

        if obj == self.canvas and event.type() == evt_resize:
            self.reposition_to_default()
        elif event.type() == evt_key_press:
            key = event.key()
            key_return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
            key_enter = getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005))
            key_escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
            key_space = getattr(Qt.Key, "Key_Space", getattr(Qt, "Key_Space", 0x20))

            if key in (key_return, key_enter):
                self.commitRequested.emit()
                return True

            if key == key_escape:
                self.resetRequested.emit()
                return True

            if key == key_space:
                self.toggle_multipart()
                return True

        return super().eventFilter(obj, event)

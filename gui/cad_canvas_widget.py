# -*- coding: utf-8 -*-
"""Shared lightweight floating HUD base for interactive CAD tools."""

from typing import Dict, Optional

from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QEvent, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAbstractSpinBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class CadCanvasWidget(QFrame):
    """Top-right HUD with shared status rows and keyboard forwarding."""

    commitRequested = pyqtSignal()
    stepBackRequested = pyqtSignal()
    resetRequested = pyqtSignal()
    shortcutRequested = pyqtSignal(str)
    modifierChanged = pyqtSignal(str, bool)

    def __init__(
        self,
        canvas: Optional[QgsMapCanvas],
        object_name: str,
    ) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName(object_name)
        self._status_labels: Dict[str, QLabel] = {}

        sub_window = getattr(
            Qt.WindowType,
            "SubWindow",
            getattr(Qt, "SubWindow", 0),
        )
        frameless = getattr(
            Qt.WindowType,
            "FramelessWindowHint",
            getattr(Qt, "FramelessWindowHint", 0),
        )
        if sub_window or frameless:
            self.setWindowFlags(sub_window | frameless)
        show_without_activating = getattr(
            Qt.WidgetAttribute,
            "WA_ShowWithoutActivating",
            getattr(Qt, "WA_ShowWithoutActivating", None),
        )
        if show_without_activating is not None:
            self.setAttribute(show_without_activating, True)
        self.setMinimumWidth(245)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        self.main_layout.setSpacing(4)
        self.lbl_step = QLabel(self)
        self.lbl_step.setWordWrap(True)
        step_font = self.lbl_step.font()
        step_font.setBold(True)
        step_font.setPointSize(max(8, step_font.pointSize() - 1))
        self.lbl_step.setFont(step_font)
        self.lbl_step.setStyleSheet(
            "color: #1e3a8a; background-color: #dbeafe; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        self.main_layout.addWidget(self.lbl_step)

        self.status_layout = QFormLayout()
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setHorizontalSpacing(8)
        self.status_layout.setVerticalSpacing(3)
        self.main_layout.addLayout(self.status_layout)

        shape = getattr(QFrame.Shape, "StyledPanel", getattr(QFrame, "StyledPanel", None))
        shadow = getattr(QFrame.Shadow, "Plain", getattr(QFrame, "Plain", None))
        if shape is not None:
            self.setFrameShape(shape)
        if shadow is not None:
            self.setFrameShadow(shadow)
        self.setAutoFillBackground(True)

        if self.canvas is not None:
            self.canvas.installEventFilter(self)

    def add_status_row(self, key: str, label: str, value: str = "—") -> QLabel:
        """Add a named status row and return its value label."""
        value_label = QLabel(value, self)
        self.status_layout.addRow(label, value_label)
        self._status_labels[key] = value_label
        return value_label

    def set_status(self, key: str, value: str) -> None:
        """Set a status value when the row exists."""
        label = self._status_labels.get(key)
        if label is not None:
            label.setText(value)
            self.reposition_to_default()

    def set_step_text(self, text: str) -> None:
        """Update the current workflow instruction."""
        self.lbl_step.setText(text)
        self.reposition_to_default()

    def register_interactive_widget(self, widget: QWidget) -> None:
        """Forward keyboard modifiers and shortcuts from a child control."""
        widget.installEventFilter(self)
        line_edit = getattr(widget, "lineEdit", lambda: None)()
        if line_edit is not None:
            line_edit.installEventFilter(self)

    def reposition_to_default(self) -> None:
        """Pin the HUD to the top-right corner of the canvas."""
        if self.canvas is None:
            return
        self.adjustSize()
        self.move(max(0, self.canvas.width() - self.width()), 0)

    def show_on_canvas(self) -> None:
        """Show and raise the HUD at its default position."""
        self.reposition_to_default()
        self.show()
        self.raise_()

    def eventFilter(self, obj, event):
        """Handle resizing and route CAD keyboard actions from canvas/HUD."""
        resize_type = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", None))
        key_press_type = getattr(
            QEvent.Type,
            "KeyPress",
            getattr(QEvent, "KeyPress", None),
        )
        key_release_type = getattr(
            QEvent.Type,
            "KeyRelease",
            getattr(QEvent, "KeyRelease", None),
        )
        if obj == self.canvas and event.type() == resize_type:
            self.reposition_to_default()
            return super().eventFilter(obj, event)
        if self.isHidden() or event.type() not in (key_press_type, key_release_type):
            return super().eventFilter(obj, event)

        pressed = event.type() == key_press_type
        key = int(event.key())
        key_shift = int(getattr(Qt.Key, "Key_Shift", getattr(Qt, "Key_Shift", 0x01000020)))
        key_control = int(getattr(Qt.Key, "Key_Control", getattr(Qt, "Key_Control", 0x01000021)))
        if key == key_shift:
            self.modifierChanged.emit("shift", pressed)
            return False
        if key == key_control:
            self.modifierChanged.emit("ctrl", pressed)
            return False
        if not pressed:
            return super().eventFilter(obj, event)

        key_escape = int(getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000)))
        key_return = int(getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004)))
        key_enter = int(getattr(Qt.Key, "Key_Enter", getattr(Qt, "Key_Enter", 0x01000005)))
        key_backspace = int(getattr(Qt.Key, "Key_Backspace", getattr(Qt, "Key_Backspace", 0x01000003)))
        key_f = int(getattr(Qt.Key, "Key_F", getattr(Qt, "Key_F", 0x46)))
        if key == key_escape:
            self.resetRequested.emit()
            return True
        if key in (key_return, key_enter):
            self.commitRequested.emit()
            return True
        if key == key_f:
            self.shortcutRequested.emit("flip")
            return True
        if key == key_backspace and not isinstance(obj, (QLineEdit, QAbstractSpinBox)):
            self.stepBackRequested.emit()
            return True
        return super().eventFilter(obj, event)

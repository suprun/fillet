# -*- coding: utf-8 -*-
"""Floating HUD for Align Feature."""

from enum import IntEnum

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QCoreApplication, pyqtSignal
from qgis.PyQt.QtWidgets import QButtonGroup, QHBoxLayout, QRadioButton

try:
    from .cad_canvas_widget import CadCanvasWidget
except (ImportError, ValueError):
    from cad_canvas_widget import CadCanvasWidget


class AlignReferenceMode(IntEnum):
    """Available Align Feature reference workflows."""

    Points = 0
    Edges = 1


class AlignFeatureCanvasWidget(CadCanvasWidget):
    """Point/edge mode selector and live alignment status."""

    modeChanged = pyqtSignal(int)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas=None) -> None:
        super().__init__(canvas, "AlignFeatureCanvasWidget")
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        self.radio_points = QRadioButton(self.tr("Точки (Points)"), self)
        self.radio_edges = QRadioButton(self.tr("Ребра (Edges)"), self)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_points, int(AlignReferenceMode.Points))
        self.mode_group.addButton(self.radio_edges, int(AlignReferenceMode.Edges))
        mode_layout.addWidget(self.radio_points)
        mode_layout.addWidget(self.radio_edges)
        self.main_layout.insertLayout(1, mode_layout)

        self.add_status_row(
            "scope",
            self.tr("Об'єкти:"),
            self.tr("Уся вибрана група"),
        )
        self.add_status_row("angle", self.tr("Кут:"), "0.00°")
        self.add_status_row("scale", self.tr("Масштаб:"), "1.000")
        self.add_status_row("mode", self.tr("Режим:"), self.tr("Переміщення"))
        stored_mode = QgsSettings().value(
            "FilletPlugin/AlignReferenceMode",
            int(AlignReferenceMode.Points),
            type=int,
        )
        self.set_reference_mode(AlignReferenceMode(stored_mode))
        self.radio_points.toggled.connect(self._on_mode_toggled)
        self.radio_edges.toggled.connect(self._on_mode_toggled)
        self.register_interactive_widget(self.radio_points)
        self.register_interactive_widget(self.radio_edges)
        self.set_stage("source_first")

    def _on_mode_toggled(self, checked: bool) -> None:
        if not checked:
            return
        mode = self.reference_mode()
        QgsSettings().setValue("FilletPlugin/AlignReferenceMode", int(mode))
        self.modeChanged.emit(int(mode))

    def reference_mode(self) -> AlignReferenceMode:
        """Return the selected reference workflow."""
        return (
            AlignReferenceMode.Edges
            if self.radio_edges.isChecked()
            else AlignReferenceMode.Points
        )

    def set_reference_mode(self, mode: AlignReferenceMode) -> None:
        """Select the reference workflow."""
        self.radio_edges.setChecked(mode == AlignReferenceMode.Edges)
        self.radio_points.setChecked(mode == AlignReferenceMode.Points)

    def set_stage(self, stage: str) -> None:
        """Show a workflow instruction."""
        messages = {
            "source_first": self.tr("1. Вкажіть першу опорну точку Source"),
            "source_second": self.tr("2. Вкажіть другу опорну точку Source"),
            "source_edge": self.tr("1. Вкажіть ребро вибраного Source"),
            "target_first": self.tr("3. Вкажіть першу опорну точку Target"),
            "target_second": self.tr("4. Вкажіть другу точку Target для підтвердження"),
            "target_edge": self.tr("2. Вкажіть ребро Target для підтвердження"),
        }
        self.set_step_text(messages.get(stage, self.tr("CAD Вирівнювання (Align Feature)")))

    def set_preview(self, angle: float, scale: float, copy: bool, fit: bool) -> None:
        """Update live transform values."""
        self.set_status("angle", "{:.2f}°".format(angle))
        self.set_status("scale", "{:.3f}".format(scale))
        if copy and fit:
            mode = self.tr("Копія + масштаб")
        elif copy:
            mode = self.tr("Копія")
        elif fit:
            mode = self.tr("Переміщення + масштаб")
        else:
            mode = self.tr("Переміщення")
        self.set_status("mode", mode)

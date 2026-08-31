# -*- coding: utf-8 -*-
"""Floating HUD for Match Edge."""

from qgis.PyQt.QtCore import QCoreApplication

try:
    from .cad_canvas_widget import CadCanvasWidget
except (ImportError, ValueError):
    from cad_canvas_widget import CadCanvasWidget


class MatchEdgeCanvasWidget(CadCanvasWidget):
    """Live status panel for the two-click Match Edge workflow."""

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas=None) -> None:
        super().__init__(canvas, "MatchEdgeCanvasWidget")
        self.add_status_row("mode", self.tr("Режим:"), self.tr("Колінеарний"))
        self.add_status_row("angle", self.tr("Кут:"), "0.00°")
        self.add_status_row("length", self.tr("Довжина:"), "0.000 → 0.000")
        self.set_stage("source")

    def set_stage(self, stage: str) -> None:
        messages = {
            "source": self.tr("1. Вкажіть пряме ребро вибраного Source"),
            "target": self.tr("2. Вкажіть інше пряме ребро Target"),
        }
        self.lbl_step.setStyleSheet(
            "color: #1e3a8a; background-color: #dbeafe; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        self.set_step_text(messages.get(stage, self.tr("CAD Суміщення ребра (Match Edge)")))

    def set_preview(
        self,
        angle: float,
        old_length: float,
        new_length: float,
        copy: bool,
        parallel: bool,
    ) -> None:
        self.set_status("angle", "{:.2f}°".format(angle))
        self.set_status(
            "length",
            "{:.3f} → {:.3f}".format(old_length, new_length),
        )
        mode = self.tr("Паралельний") if parallel else self.tr("Колінеарний")
        if copy:
            mode = self.tr("Копія / ") + mode
        else:
            mode = self.tr("Редагування / ") + mode
        self.set_status("mode", mode)

    def set_error(self, message: str) -> None:
        """Show a local validation error using the shared red palette."""
        self.lbl_step.setStyleSheet(
            "color: #991b1b; background-color: #fee2e2; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        self.set_step_text(message)

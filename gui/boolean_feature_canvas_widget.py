# -*- coding: utf-8 -*-
"""Shared floating HUD for Subtract Feature and Clip Feature."""

from qgis.PyQt.QtCore import QCoreApplication

try:
    from .cad_canvas_widget import CadCanvasWidget
except (ImportError, ValueError):
    from cad_canvas_widget import CadCanvasWidget


class BooleanFeatureCanvasWidget(CadCanvasWidget):
    """Target/cutter status panel for an in-place polygon boolean tool."""

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas=None, operation: str = "subtract") -> None:
        object_name = (
            "SubtractFeatureCanvasWidget"
            if operation == "subtract"
            else "ClipFeatureCanvasWidget"
        )
        super().__init__(canvas, object_name)
        self.operation = operation
        self.add_status_row("target", self.tr("Target:"), "—")
        self.add_status_row("cutters", self.tr("Cutters:"), "0")
        self.add_status_row("mode", self.tr("Режим:"), self.tr("Одиночний"))
        self.set_stage(False)

    def set_stage(self, has_target: bool) -> None:
        if has_target:
            text = self.tr("2. Вкажіть Cutter або Shift-кліком додайте набір")
        elif self.operation == "subtract":
            text = self.tr("1. Вкажіть Target для віднімання")
        else:
            text = self.tr("1. Вкажіть Target для обрізання")
        self.set_step_text(text)

    def update_state(
        self,
        target_fid=None,
        cutter_count: int = 0,
        continuous: bool = False,
    ) -> None:
        self.set_status(
            "target",
            "#{}".format(target_fid) if target_fid is not None else "—",
        )
        self.set_status("cutters", str(cutter_count))
        self.set_status(
            "mode",
            self.tr("Безперервний") if continuous else self.tr("Одиночний"),
        )

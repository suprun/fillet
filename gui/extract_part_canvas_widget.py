# -*- coding: utf-8 -*-
"""Floating HUD for Extract Part."""

from qgis.PyQt.QtCore import QCoreApplication

try:
    from .cad_canvas_widget import CadCanvasWidget
except (ImportError, ValueError):
    from cad_canvas_widget import CadCanvasWidget


class ExtractPartCanvasWidget(CadCanvasWidget):
    """Status panel for multipart extraction and pending selection."""

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas=None) -> None:
        super().__init__(canvas, "ExtractPartCanvasWidget")
        self.add_status_row("source", self.tr("Source:"), "—")
        self.add_status_row("selected", self.tr("Вибрано частин:"), "0")
        self.add_status_row("mode", self.tr("Режим:"), self.tr("Переміщення"))
        self.set_step_text(self.tr("Клацніть частину; Shift — множинний вибір"))

    def update_state(self, source_fid=None, selected_count: int = 0, copy: bool = False) -> None:
        self.set_status(
            "source",
            "#{}".format(source_fid) if source_fid is not None else "—",
        )
        self.set_status("selected", str(selected_count))
        self.set_status("mode", self.tr("Копія") if copy else self.tr("Переміщення"))

# -*- coding: utf-8 -*-
"""Floating HUD for Array Along Path."""

from enum import IntEnum

from qgis.core import QgsCoordinateReferenceSystem, QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsSpinBox
from qgis.PyQt.QtCore import QCoreApplication, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QLabel,
    QRadioButton,
)

try:
    from .cad_canvas_widget import CadCanvasWidget
except (ImportError, ValueError):
    from cad_canvas_widget import CadCanvasWidget


class PathDistributionMode(IntEnum):
    """Ways to distribute copies along a path."""

    Count = 0
    Spacing = 1


class PathRangeMode(IntEnum):
    """Whole-path or user-selected subrange mode."""

    WholePath = 0
    Subrange = 1


class ArrayAlongPathCanvasWidget(CadCanvasWidget):
    """Controls and live values for path-based feature arrays."""

    parametersChanged = pyqtSignal()

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas=None) -> None:
        super().__init__(canvas, "ArrayAlongPathCanvasWidget")
        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(6)
        controls.setVerticalSpacing(3)

        self.radio_count = QRadioButton(self.tr("Кількість"), self)
        self.radio_spacing = QRadioButton(self.tr("Крок"), self)
        self.distribution_group = QButtonGroup(self)
        self.distribution_group.addButton(self.radio_count, int(PathDistributionMode.Count))
        self.distribution_group.addButton(self.radio_spacing, int(PathDistributionMode.Spacing))
        self.spin_count = QgsSpinBox(self)
        self.spin_count.setRange(1, 99999)
        self.spin_count.setValue(5)
        self.spin_spacing = QgsDoubleSpinBox(self)
        self.spin_spacing.setRange(0.000001, 999999999.0)
        self.spin_spacing.setDecimals(3)
        self.spin_spacing.setValue(5.0)
        controls.addWidget(self.radio_count, 0, 0)
        controls.addWidget(self.spin_count, 0, 1)
        controls.addWidget(self.radio_spacing, 1, 0)
        controls.addWidget(self.spin_spacing, 1, 1)

        self.radio_whole = QRadioButton(self.tr("Весь шлях"), self)
        self.radio_subrange = QRadioButton(self.tr("Піддіапазон"), self)
        self.range_group = QButtonGroup(self)
        self.range_group.addButton(self.radio_whole, int(PathRangeMode.WholePath))
        self.range_group.addButton(self.radio_subrange, int(PathRangeMode.Subrange))
        controls.addWidget(self.radio_whole, 2, 0)
        controls.addWidget(self.radio_subrange, 2, 1)

        controls.addWidget(QLabel(self.tr("Зсув (Offset):"), self), 3, 0)
        self.spin_offset = QgsDoubleSpinBox(self)
        self.spin_offset.setRange(-999999999.0, 999999999.0)
        self.spin_offset.setDecimals(3)
        self.spin_offset.setValue(0.0)
        controls.addWidget(self.spin_offset, 3, 1)
        self.chk_include_start = QCheckBox(self.tr("Включити початкову позицію"), self)
        self.chk_include_start.setChecked(True)
        controls.addWidget(self.chk_include_start, 4, 0, 1, 2)
        self.main_layout.insertLayout(1, controls)

        self.add_status_row("copies", self.tr("Копій:"), "0")
        self.add_status_row("orientation", self.tr("Орієнтація:"), self.tr("Фіксована"))
        self.add_status_row("direction", self.tr("Напрямок:"), self.tr("Прямий"))

        self._load_settings()
        for control in (
            self.radio_count,
            self.radio_spacing,
            self.spin_count,
            self.spin_spacing,
            self.radio_whole,
            self.radio_subrange,
            self.spin_offset,
            self.chk_include_start,
        ):
            self.register_interactive_widget(control)
        self.radio_count.toggled.connect(self._on_parameters_changed)
        self.radio_spacing.toggled.connect(self._on_parameters_changed)
        self.spin_count.valueChanged.connect(self._on_parameters_changed)
        self.spin_spacing.valueChanged.connect(self._on_parameters_changed)
        self.radio_whole.toggled.connect(self._on_parameters_changed)
        self.radio_subrange.toggled.connect(self._on_parameters_changed)
        self.spin_offset.valueChanged.connect(self._on_parameters_changed)
        self.chk_include_start.toggled.connect(self._on_parameters_changed)
        self._sync_enabled_controls()
        self.set_stage("anchor")

    def _load_settings(self) -> None:
        settings = QgsSettings()
        distribution = settings.value(
            "FilletPlugin/PathArrayDistribution",
            int(PathDistributionMode.Count),
            type=int,
        )
        range_mode = settings.value(
            "FilletPlugin/PathArrayRange",
            int(PathRangeMode.WholePath),
            type=int,
        )
        self.radio_spacing.setChecked(distribution == int(PathDistributionMode.Spacing))
        self.radio_count.setChecked(distribution != int(PathDistributionMode.Spacing))
        self.radio_subrange.setChecked(range_mode == int(PathRangeMode.Subrange))
        self.radio_whole.setChecked(range_mode != int(PathRangeMode.Subrange))
        self.spin_count.setValue(
            max(1, settings.value("FilletPlugin/PathArrayCount", 5, type=int))
        )
        self.spin_spacing.setValue(
            max(
                0.000001,
                settings.value("FilletPlugin/PathArraySpacing", 5.0, type=float),
            )
        )
        self.spin_offset.setValue(
            settings.value("FilletPlugin/PathArrayOffset", 0.0, type=float)
        )
        self.chk_include_start.setChecked(
            settings.value("FilletPlugin/PathArrayIncludeStart", True, type=bool)
        )

    def _save_settings(self) -> None:
        settings = QgsSettings()
        settings.setValue("FilletPlugin/PathArrayDistribution", int(self.distribution_mode()))
        settings.setValue("FilletPlugin/PathArrayRange", int(self.range_mode()))
        settings.setValue("FilletPlugin/PathArrayCount", self.count_value())
        settings.setValue("FilletPlugin/PathArraySpacing", self.spacing_value())
        settings.setValue("FilletPlugin/PathArrayOffset", self.offset_value())
        settings.setValue("FilletPlugin/PathArrayIncludeStart", self.include_start())

    def _on_parameters_changed(self, *args) -> None:
        self._sync_enabled_controls()
        self._save_settings()
        self.parametersChanged.emit()

    def _sync_enabled_controls(self) -> None:
        self.spin_count.setEnabled(self.distribution_mode() == PathDistributionMode.Count)
        self.spin_spacing.setEnabled(self.distribution_mode() == PathDistributionMode.Spacing)

    def distribution_mode(self) -> PathDistributionMode:
        return (
            PathDistributionMode.Spacing
            if self.radio_spacing.isChecked()
            else PathDistributionMode.Count
        )

    def range_mode(self) -> PathRangeMode:
        return (
            PathRangeMode.Subrange
            if self.radio_subrange.isChecked()
            else PathRangeMode.WholePath
        )

    def count_value(self) -> int:
        return int(self.spin_count.value())

    def spacing_value(self) -> float:
        return float(self.spin_spacing.value())

    def offset_value(self) -> float:
        return float(self.spin_offset.value())

    def include_start(self) -> bool:
        return self.chk_include_start.isChecked()

    def set_calculated_count(self, count: int) -> None:
        self.set_status("copies", str(max(0, int(count))))

    def set_modifier_state(self, tangent: bool, reverse: bool) -> None:
        self.set_status(
            "orientation",
            self.tr("Дотична") if tangent else self.tr("Фіксована"),
        )
        self.set_status(
            "direction",
            self.tr("Зворотний") if reverse else self.tr("Прямий"),
        )

    def set_stage(self, stage: str) -> None:
        messages = {
            "anchor": self.tr("1. Вкажіть Anchor вибраної групи"),
            "path": self.tr("2. Вкажіть лінійний Path"),
            "range_start": self.tr("3. Вкажіть початок піддіапазону"),
            "range_end": self.tr("4. Вкажіть кінець піддіапазону"),
            "preview": self.tr("Enter або клік — створити масив"),
        }
        self.set_step_text(messages.get(stage, self.tr("CAD Масив уздовж шляху")))

    def adapt_to_crs(self, crs: QgsCoordinateReferenceSystem) -> None:
        decimals = 6 if crs.isGeographic() else 3
        step = 0.0001 if crs.isGeographic() else 1.0
        self.spin_spacing.setDecimals(decimals)
        self.spin_spacing.setSingleStep(step)
        self.spin_offset.setDecimals(decimals)
        self.spin_offset.setSingleStep(step)

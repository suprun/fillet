# -*- coding: utf-8 -*-
"""
Floating CAD-style HUD panel for CAD Ortho Angles tool.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import os
from typing import List, Optional

from qgis.core import QgsSettings
from qgis.gui import QgsDoubleSpinBox, QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPixmap,
)
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class OrthoAnglesCanvasWidget(QFrame):
    """
    Floating CAD HUD widget pinned on the map canvas for CAD Ortho Angles tool.
    Provides controls for:
      - Angle Tolerance (° + Lock Button + Presets/History Menu)
      - [x] Preserve Area (Uniform scaling around centroid)
      - [ ] Create copy (Preserves original feature)
    """

    toleranceChanged = pyqtSignal(float)
    toleranceLockToggled = pyqtSignal(bool)
    preserveAreaChanged = pyqtSignal(bool)
    createCopyChanged = pyqtSignal(bool)
    commitRequested = pyqtSignal()
    resetRequested = pyqtSignal()

    STEP_SELECT = 1
    STEP_BASE_EDGE = 2
    STEP_ADJUST = 3

    DEFAULT_PRESETS: List[float] = [5.0, 10.0, 15.0, 20.0, 30.0, 45.0]

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("FilletPlugin", message)

    def __init__(self, canvas: Optional[QgsMapCanvas] = None):
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("OrthoAnglesCanvasWidget")

        self._icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons")
        self._current_step = self.STEP_SELECT
        self._is_loading = False

        self._init_ui()
        self._apply_style()
        self._load_settings()

        if self.canvas is not None:
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
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(4)

        # 1. Header Label (Step prompt)
        self.lbl_step = QLabel(self.tr("1. Оберіть об'єкт для вирівнювання"), self)
        font = self.lbl_step.font()
        font.setBold(True)
        self.lbl_step.setFont(font)
        self.lbl_step.setAlignment(getattr(Qt.AlignmentFlag, "AlignCenter", getattr(Qt, "AlignCenter", None)))
        main_layout.addWidget(self.lbl_step)

        # 2. Grid for inputs and controls (4 columns: Label, SpinBox, Lock Button, Menu Button)
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnMinimumWidth(0, 120)

        # Row 0: Tolerance Label + SpinBox + Lock + Presets Menu
        self.lbl_tolerance = QLabel(self.tr("Допуск (Tolerance):"), self)
        self.lbl_tolerance.setToolTip(self.tr("Максимальне відхилення від прямого кута для ортогоналізації (1°–45°)"))

        if hasattr(QgsDoubleSpinBox, "setMinimum"):
            self.spin_tolerance = QgsDoubleSpinBox(self)
        else:
            self.spin_tolerance = QDoubleSpinBox(self)
        self.spin_tolerance.setRange(1.0, 45.0)
        self.spin_tolerance.setValue(15.0)
        self.spin_tolerance.setSingleStep(1.0)
        self.spin_tolerance.setDecimals(1)
        self.spin_tolerance.setSuffix("°")
        if hasattr(self.spin_tolerance, "setShowClearButton"):
            self.spin_tolerance.setShowClearButton(False)
        self.spin_tolerance.setToolTip(self.tr("Кутовий допуск ортогоналізації"))

        # Lock button for Tolerance
        self.btn_lock_tolerance = QToolButton(self)
        self.btn_lock_tolerance.setCheckable(True)
        self.btn_lock_tolerance.setChecked(False)
        self.btn_lock_tolerance.setFixedSize(22, 22)
        self.btn_lock_tolerance.setCursor(QCursor(getattr(Qt.CursorShape, "PointingHandCursor", getattr(Qt, "PointingHandCursor", 13))))
        self.btn_lock_tolerance.setToolTip(self.tr("Заблокувати допуск від випадкової зміни"))
        self._update_lock_tolerance_icon(False)
        self.btn_lock_tolerance.toggled.connect(self._on_lock_tolerance_toggled)

        # Presets & Recent values menu button
        self.btn_presets_tolerance = QToolButton(self)
        self.btn_presets_tolerance.setFixedSize(22, 22)
        self.btn_presets_tolerance.setCursor(QCursor(getattr(Qt.CursorShape, "PointingHandCursor", getattr(Qt, "PointingHandCursor", 13))))
        self.btn_presets_tolerance.setToolTip(self.tr("Швидкі пресети кутового допуску та останні використані значення"))
        self.btn_presets_tolerance.setIcon(self._create_menu_icon())
        self.btn_presets_tolerance.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup if hasattr(QToolButton, "ToolButtonPopupMode") else QToolButton.InstantPopup)

        self.tolerance_menu = QMenu(self.btn_presets_tolerance)
        self.btn_presets_tolerance.setMenu(self.tolerance_menu)
        self.tolerance_menu.aboutToShow.connect(self._rebuild_tolerance_menu)

        grid.addWidget(self.lbl_tolerance, 0, 0)
        grid.addWidget(self.spin_tolerance, 0, 1)
        grid.addWidget(self.btn_lock_tolerance, 0, 2)
        grid.addWidget(self.btn_presets_tolerance, 0, 3)

        main_layout.addLayout(grid)

        # 3. Checkboxes (Preserve Area, Create Copy)
        self.chk_preserve_area = QCheckBox(self.tr("Зберегти площу (Preserve Area)"), self)
        self.chk_preserve_area.setChecked(True)
        self.chk_preserve_area.setToolTip(self.tr("Масштабувати контур відносно центроїда для збереження початкової площі"))
        main_layout.addWidget(self.chk_preserve_area)

        self.chk_create_copy = QCheckBox(self.tr("Створити копію (Create copy)"), self)
        self.chk_create_copy.setChecked(False)
        self.chk_create_copy.setToolTip(self.tr("Створювати новий об'єкт, не змінюючи вихідний"))
        main_layout.addWidget(self.chk_create_copy)

        # Connect signals
        self.spin_tolerance.valueChanged.connect(self._on_tolerance_changed)
        self.chk_preserve_area.toggled.connect(self._on_preserve_area_toggled)
        self.chk_create_copy.toggled.connect(self._on_create_copy_toggled)

        # Event filters
        self.installEventFilter(self)
        self.spin_tolerance.installEventFilter(self)
        line_edit = self.spin_tolerance.lineEdit() if hasattr(self.spin_tolerance, "lineEdit") else None
        if line_edit is not None:
            line_edit.installEventFilter(self)

    def focus_primary_input(self):
        self.spin_tolerance.setFocus()
        self.spin_tolerance.selectAll()

    def _create_lock_icon(self, locked: bool) -> QIcon:
        """Draws a clean vector lock icon."""
        pix = QPixmap(16, 16)
        pix.fill(getattr(Qt.GlobalColor, "transparent", getattr(Qt, "transparent", None)))
        from qgis.PyQt.QtGui import QPainter, QPen
        p = QPainter(pix)
        p.setRenderHint(getattr(QPainter.RenderHint, "Antialiasing", getattr(QPainter, "Antialiasing", None)))
        color = QColor(220, 38, 38) if locked else QColor(100, 116, 139)  # Red when locked, slate when unlocked
        p.setPen(QPen(color, 1.4))
        p.setBrush(getattr(Qt.BrushStyle, "NoBrush", getattr(Qt, "NoBrush", 0)))

        if locked:
            p.drawRoundedRect(3, 7, 10, 8, 2, 2)
            p.drawArc(5, 2, 6, 8, 0, 180 * 16)
        else:
            p.drawRoundedRect(3, 7, 10, 8, 2, 2)
            p.drawArc(7, 1, 6, 8, 0, 180 * 16)

        p.end()
        return QIcon(pix)

    def _create_menu_icon(self) -> QIcon:
        """Draws a dropdown triangle menu icon."""
        pix = QPixmap(16, 16)
        pix.fill(getattr(Qt.GlobalColor, "transparent", getattr(Qt, "transparent", None)))
        from qgis.PyQt.QtGui import QPainter, QPolygonF
        from qgis.PyQt.QtCore import QPointF
        p = QPainter(pix)
        p.setRenderHint(getattr(QPainter.RenderHint, "Antialiasing", getattr(QPainter, "Antialiasing", None)))
        p.setPen(getattr(Qt.PenStyle, "NoPen", getattr(Qt, "NoPen", 0)))
        p.setBrush(QColor(100, 116, 139))
        poly = QPolygonF([QPointF(4.0, 6.0), QPointF(12.0, 6.0), QPointF(8.0, 11.0)])
        p.drawPolygon(poly)
        p.end()
        return QIcon(pix)

    def _update_lock_tolerance_icon(self, locked: bool):
        self.btn_lock_tolerance.setIcon(self._create_lock_icon(locked))

    def _on_lock_tolerance_toggled(self, checked: bool):
        self._update_lock_tolerance_icon(checked)
        self.toleranceLockToggled.emit(checked)
        self._save_settings()

    def _rebuild_tolerance_menu(self):
        self.tolerance_menu.clear()

        # Preset section
        header_preset = self.tolerance_menu.addAction(self.tr("Стандартні допуски:"))
        header_preset.setEnabled(False)

        for val in self.DEFAULT_PRESETS:
            act = self.tolerance_menu.addAction(f"± {val:g}°")
            act.triggered.connect(lambda checked, v=val: self._on_tolerance_preset_selected(v))

        # Recent section
        recent = self._get_recent_tolerances()
        if recent:
            self.tolerance_menu.addSeparator()
            header_recent = self.tolerance_menu.addAction(self.tr("Останні значення:"))
            header_recent.setEnabled(False)
            for val in recent:
                act = self.tolerance_menu.addAction(f"{val:g}°")
                act.triggered.connect(lambda checked, v=val: self._on_tolerance_preset_selected(v))

    def _on_tolerance_preset_selected(self, val: float):
        self.spin_tolerance.setValue(val)
        self._save_recent_tolerance(val)

    def _get_recent_tolerances(self) -> List[float]:
        settings = QgsSettings()
        raw = settings.value("fillet/ortho_angles_recent_tolerances", "", type=str)
        if not raw:
            return []
        try:
            return [float(x) for x in str(raw).split(",") if x.strip()][:5]
        except Exception:
            return []

    def _save_recent_tolerance(self, val: float):
        recent = [v for v in self._get_recent_tolerances() if abs(v - val) > 1e-4]
        recent.insert(0, val)
        recent = recent[:5]
        settings = QgsSettings()
        settings.setValue("fillet/ortho_angles_recent_tolerances", ",".join(str(v) for v in recent))

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#OrthoAnglesCanvasWidget {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid rgba(0, 0, 0, 0.18);
                border-radius: 6px;
            }
            QLabel {
                font-size: 9pt;
                color: #1e293b;
            }
            QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 3px;
                padding: 1px 4px;
                font-size: 9pt;
                color: #0f172a;
            }
            QDoubleSpinBox:focus {
                border-color: #3b82f6;
            }
            QCheckBox {
                font-size: 8.5pt;
                color: #334155;
            }
            QToolButton {
                border: 1px solid #cbd5e1;
                border-radius: 3px;
                background: #f8fafc;
            }
            QToolButton:hover {
                background: #e2e8f0;
                border-color: #94a3b8;
            }
            QToolButton:checked {
                background: #fee2e2;
                border-color: #ef4444;
            }
            QMenu {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 2px;
            }
            QMenu::item {
                padding: 4px 16px;
                font-size: 8.5pt;
                color: #1e293b;
            }
            QMenu::item:selected {
                background: #eff6ff;
                color: #1d4ed8;
            }
        """)

    def _load_settings(self):
        self._is_loading = True
        settings = QgsSettings()
        self.spin_tolerance.setValue(float(settings.value("fillet/ortho_angles_tolerance", 15.0, type=float)))
        self.btn_lock_tolerance.setChecked(bool(settings.value("fillet/ortho_angles_lock_tolerance", False, type=bool)))
        self.chk_preserve_area.setChecked(bool(settings.value("fillet/ortho_angles_preserve_area", True, type=bool)))
        self.chk_create_copy.setChecked(bool(settings.value("fillet/ortho_angles_create_copy", False, type=bool)))
        self._is_loading = False

    def _save_settings(self):
        if self._is_loading:
            return
        settings = QgsSettings()
        settings.setValue("fillet/ortho_angles_tolerance", float(self.spin_tolerance.value()))
        settings.setValue("fillet/ortho_angles_lock_tolerance", bool(self.btn_lock_tolerance.isChecked()))
        settings.setValue("fillet/ortho_angles_preserve_area", bool(self.chk_preserve_area.isChecked()))
        settings.setValue("fillet/ortho_angles_create_copy", bool(self.chk_create_copy.isChecked()))

    @property
    def tolerance(self) -> float:
        return float(self.spin_tolerance.value())

    @property
    def is_tolerance_locked(self) -> bool:
        return self.btn_lock_tolerance.isChecked()

    @property
    def preserve_area(self) -> bool:
        return self.chk_preserve_area.isChecked()

    @property
    def create_copy(self) -> bool:
        return self.chk_create_copy.isChecked()

    def set_calculated_tolerance(self, val: float):
        if not self.is_tolerance_locked:
            self.spin_tolerance.blockSignals(True)
            self.spin_tolerance.setValue(max(1.0, min(45.0, val)))
            self.spin_tolerance.blockSignals(False)

    def _on_tolerance_changed(self, val: float):
        if not self._is_loading:
            self._save_settings()
            self._save_recent_tolerance(val)
            self.toleranceChanged.emit(val)

    def _on_preserve_area_toggled(self, checked: bool):
        if not self._is_loading:
            self._save_settings()
            self.preserveAreaChanged.emit(checked)

    def _on_create_copy_toggled(self, checked: bool):
        if not self._is_loading:
            self._save_settings()
            self.createCopyChanged.emit(checked)

    def set_step(self, step: int):
        self._current_step = step
        if step == self.STEP_SELECT:
            self.lbl_step.setText(self.tr("1. Оберіть об'єкт для вирівнювання"))
        elif step == self.STEP_BASE_EDGE:
            self.lbl_step.setText(self.tr("2. Вкажіть опорний сегмент (фасад)"))
        elif step == self.STEP_ADJUST:
            self.lbl_step.setText(self.tr("3. Налаштуйте допуск або підтвердіть Enter"))

    def show_on_canvas(self):
        if self.canvas is None:
            self.show()
            return
        self.show()
        self.raise_()
        self.reposition_on_canvas()

    def reposition_on_canvas(self):
        if self.canvas is None or not self.isVisible():
            return
        canvas_size = self.canvas.size()
        widget_size = self.sizeHint()
        x = max(10, canvas_size.width() - widget_size.width() - 20)
        y = 20
        self.move(x, y)

    def eventFilter(self, obj, event):
        ev_type = event.type()
        resize_type = getattr(QEvent.Type, "Resize", getattr(QEvent, "Resize", 14))
        key_press_type = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6))

        if obj == self.canvas and ev_type == resize_type:
            QTimer.singleShot(0, self.reposition_on_canvas)

        if ev_type == key_press_type:
            key = event.key()
            key_int = int(key)
            if key_int in (0x01000000, int(getattr(Qt.Key, "Key_Escape", 0x01000000))):
                self.resetRequested.emit()
                return True
            if key_int in (
                0x01000004,
                0x01000005,
                int(getattr(Qt.Key, "Key_Return", 0x01000004)),
                int(getattr(Qt.Key, "Key_Enter", 0x01000005)),
            ):
                self.commitRequested.emit()
                return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        key = event.key()
        key_int = int(key)
        if key_int in (0x01000000, int(getattr(Qt.Key, "Key_Escape", 0x01000000))):
            self.resetRequested.emit()
            event.accept()
            return
        if key_int in (
            0x01000004,
            0x01000005,
            int(getattr(Qt.Key, "Key_Return", 0x01000004)),
            int(getattr(Qt.Key, "Key_Enter", 0x01000005)),
        ):
            self.commitRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

# -*- coding: utf-8 -*-
"""
Unit tests for CAD Polar (Circular) Feature Array tool.
Tests PolarArrayCanvasWidget, CADPolarArrayMapTool, and GeometryEngine.create_polar_array_geometries.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsSettings,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas, QgsRubberBand
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow, QToolBar

app = QgsApplication([], False)
app.initQgis()

from core.geometry_engine import GeometryEngine
from gui.polar_array_canvas_widget import PolarArrayCanvasWidget, PolarArrayMode
from gui.polar_array_map_tool import CADPolarArrayMapTool
from plugin import FilletPlugin


class MockMessageBar(QObject):
    def __init__(self):
        super().__init__()
        self.messages = []

    def pushMessage(self, title, text, level=0, duration=0):
        self.messages.append((title, text, level, duration))

    def pushWarning(self, title, text):
        self.messages.append((title, text, 1, 0))


class MockIface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def __init__(self, win, canvas, tb):
        super().__init__()
        self._win = win
        self._canvas = canvas
        self._tb = tb
        self._message_bar = MockMessageBar()

    def messageBar(self):
        return self._message_bar

    def mainWindow(self):
        return self._win

    def mapCanvas(self):
        return self._canvas

    def advancedDigitizeToolBar(self):
        return self._tb

    def addVectorToolBarIcon(self, a):
        self._tb.addAction(a)

    def removeVectorToolBarIcon(self, a):
        self._tb.removeAction(a)

    def addPluginToVectorMenu(self, n, a):
        pass

    def removePluginVectorMenu(self, n, a):
        pass

    def addDockWidget(self, area, d):
        self._win.addDockWidget(area, d)

    def removeDockWidget(self, d):
        self._win.removeDockWidget(d)

    def currentLayer(self):
        return self._canvas.currentLayer()

    def cadDockWidget(self):
        return None

    def vectorLayerTools(self):
        return None


class TestCADPolarArrayTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canvas = QgsMapCanvas()
        cls.win = QMainWindow()
        cls.tb = QToolBar(cls.win)
        cls.win.addToolBar(cls.tb)
        cls.iface = MockIface(cls.win, cls.canvas, cls.tb)

    def setUp(self):
        settings = QgsSettings()
        settings.remove("Fillet/PolarArrayMode")
        settings.remove("Fillet/PolarArrayCount")
        settings.remove("Fillet/PolarArrayStepAngle")
        settings.remove("Fillet/PolarArrayFillAngle")
        settings.remove("Fillet/PolarArrayRotateFeatures")
        settings.remove("Fillet/PolarArrayStepAngleLocked")
        settings.remove("Fillet/PolarArrayFillAngleLocked")
        settings.remove("Fillet/PolarArrayRecentSteps")
        settings.remove("Fillet/PolarArrayRecentFillAngles")
        self.point_layer = QgsVectorLayer("Point?crs=EPSG:3857", "TestPoints", "memory")
        self.polygon_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "TestPolygons", "memory")
        QgsProject.instance().addMapLayers([self.point_layer, self.polygon_layer])

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()
        settings = QgsSettings()
        settings.remove("Fillet/PolarArrayMode")
        settings.remove("Fillet/PolarArrayCount")
        settings.remove("Fillet/PolarArrayStepAngle")
        settings.remove("Fillet/PolarArrayFillAngle")
        settings.remove("Fillet/PolarArrayRotateFeatures")
        settings.remove("Fillet/PolarArrayStepAngleLocked")
        settings.remove("Fillet/PolarArrayFillAngleLocked")
        settings.remove("Fillet/PolarArrayRecentSteps")
        settings.remove("Fillet/PolarArrayRecentFillAngles")

    def test_polar_array_geometry_math_rotated(self):
        """Test circular 360 degree 4-item array with rotation around (0,0)."""
        center = QgsPointXY(0.0, 0.0)
        # Point at (10, 0)
        pt_geom = QgsGeometry.fromPointXY(QgsPointXY(10.0, 0.0))

        # 4 items on 360 deg circle -> steps of 90 deg (0, 90, 180, 270)
        # include_original=False returns 3 items for i=1,2,3
        copies = GeometryEngine.create_polar_array_geometries(
            geom=pt_geom,
            center=center,
            count=4,
            fill_angle_deg=360.0,
            rotate_features=True,
            include_original=False,
        )
        self.assertEqual(len(copies), 3)

        # 1: 90 deg CCW -> (0, 10)
        p1 = copies[0].asPoint()
        self.assertAlmostEqual(p1.x(), 0.0, places=4)
        self.assertAlmostEqual(p1.y(), 10.0, places=4)

        # 2: 180 deg CCW -> (-10, 0)
        p2 = copies[1].asPoint()
        self.assertAlmostEqual(p2.x(), -10.0, places=4)
        self.assertAlmostEqual(p2.y(), 0.0, places=4)

        # 3: 270 deg CCW -> (0, -10)
        p3 = copies[2].asPoint()
        self.assertAlmostEqual(p3.x(), 0.0, places=4)
        self.assertAlmostEqual(p3.y(), -10.0, places=4)

    def test_polar_array_geometry_without_rotation(self):
        """Test that rotate_features=False translates copies without altering internal orientation."""
        center = QgsPointXY(0.0, 0.0)
        # Horizontal line from (9, 0) to (11, 0)
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(9.0, 0.0), QgsPointXY(11.0, 0.0)])

        copies = GeometryEngine.create_polar_array_geometries(
            geom=line_geom,
            center=center,
            count=4,
            fill_angle_deg=360.0,
            rotate_features=False,
            include_original=False,
        )
        self.assertEqual(len(copies), 3)

        # Copy 1 at 90 deg CCW: centroid moves from (10, 0) to (0, 10), line remains horizontal: (-1, 10) to (1, 10)
        pts1 = copies[0].asPolyline()
        self.assertAlmostEqual(pts1[0].x(), -1.0, places=4)
        self.assertAlmostEqual(pts1[0].y(), 10.0, places=4)
        self.assertAlmostEqual(pts1[1].x(), 1.0, places=4)
        self.assertAlmostEqual(pts1[1].y(), 10.0, places=4)

    def test_polar_array_partial_fill_angle(self):
        """Test partial fill angle (e.g. 180 deg with count=3 -> 0, 90, 180)."""
        center = QgsPointXY(0.0, 0.0)
        pt_geom = QgsGeometry.fromPointXY(QgsPointXY(5.0, 0.0))

        copies = GeometryEngine.create_polar_array_geometries(
            geom=pt_geom,
            center=center,
            count=3,
            fill_angle_deg=180.0,
            rotate_features=True,
            include_original=False,
        )
        self.assertEqual(len(copies), 2)

        # Copy 1 at 90 deg -> (0, 5)
        p1 = copies[0].asPoint()
        self.assertAlmostEqual(p1.x(), 0.0, places=4)
        self.assertAlmostEqual(p1.y(), 5.0, places=4)

        # Copy 2 at 180 deg -> (-5, 0)
        p2 = copies[1].asPoint()
        self.assertAlmostEqual(p2.x(), -5.0, places=4)
        self.assertAlmostEqual(p2.y(), 0.0, places=4)

    def test_widget_checkbox_guard_and_restoration(self):
        """Test mutual exclusion guard and stored value restoration on re-enabling checkboxes."""
        widget = PolarArrayCanvasWidget(self.canvas)
        widget.chk_count.setChecked(True)
        widget.chk_step.setChecked(False)
        widget.spin_count.setValue(6)

        # Unchecking count when step is off should automatically activate step
        widget.chk_count.setChecked(False)
        self.assertTrue(widget.chk_step.isChecked())
        self.assertEqual(widget.mode, PolarArrayMode.StepAndFillAngle)

        # In StepAndFillAngle mode, calculated count is updated on mouse move without losing user configured 6
        widget.set_calculated_count(12)
        self.assertEqual(widget.spin_count.value(), 12)

        # Re-enabling count restores user value 6
        widget.chk_count.setChecked(True)
        self.assertEqual(widget.spin_count.value(), 6)

    def test_map_tool_commit_and_undo_stack(self):
        """Test CADPolarArrayMapTool feature creation and undoability."""
        self.polygon_layer.startEditing()

        # Add a polygon box at (10, 0)
        feat = QgsFeature()
        box_geom = QgsGeometry.fromPolygonXY([[
            QgsPointXY(8.0, -1.0),
            QgsPointXY(12.0, -1.0),
            QgsPointXY(12.0, 1.0),
            QgsPointXY(8.0, 1.0),
            QgsPointXY(8.0, -1.0),
        ]])
        feat.setGeometry(box_geom)
        self.polygon_layer.addFeature(feat)
        self.polygon_layer.selectAll()
        self.assertEqual(self.polygon_layer.featureCount(), 1)

        self.canvas.setCurrentLayer(self.polygon_layer)

        widget = PolarArrayCanvasWidget(self.canvas)
        tool = CADPolarArrayMapTool(self.canvas, widget, self.iface)
        tool.center_point = QgsPointXY(0.0, 0.0)
        tool.featureList = list(self.polygon_layer.getFeatures())
        tool.featureLayer = self.polygon_layer

        widget.spin_count.setValue(4)
        widget.spin_fill_angle.setValue(360.0)
        widget.chk_rotate_features.setChecked(True)

        tool.commit_array()

        # Layer should now have 1 (original) + 3 (new) = 4 features
        self.assertEqual(self.polygon_layer.featureCount(), 4)

        # Test Undo
        self.polygon_layer.undoStack().undo()
        self.assertEqual(self.polygon_layer.featureCount(), 1)

        # Test Redo
        self.polygon_layer.undoStack().redo()
        self.assertEqual(self.polygon_layer.featureCount(), 4)

        self.polygon_layer.rollBack()

    def test_click_select_highlights_without_layer_selection(self):
        """Clicking a feature in STATE_SELECT_FEATURE highlights it without changing QGIS selection."""
        self.polygon_layer.startEditing()
        feat = QgsFeature()
        box_geom = QgsGeometry.fromPolygonXY([[
            QgsPointXY(5.0, 5.0),
            QgsPointXY(7.0, 5.0),
            QgsPointXY(7.0, 7.0),
            QgsPointXY(5.0, 7.0),
            QgsPointXY(5.0, 5.0),
        ]])
        feat.setGeometry(box_geom)
        self.polygon_layer.addFeature(feat)
        self.polygon_layer.removeSelection()
        self.assertEqual(self.polygon_layer.selectedFeatureCount(), 0)

        self.canvas.setCurrentLayer(self.polygon_layer)
        widget = PolarArrayCanvasWidget(self.canvas)
        tool = CADPolarArrayMapTool(self.canvas, widget, self.iface)
        tool.activate()
        self.assertEqual(tool.state, CADPolarArrayMapTool.STATE_SELECT_FEATURE)

        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPointF, Qt
        from qgis.PyQt.QtGui import QMouseEvent

        mouse_ev = QMouseEvent(
            getattr(QEvent.Type, "MouseButtonPress", getattr(QEvent, "MouseButtonPress", 2)),
            QPointF(6.0, 6.0),
            getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1)),
            getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1)),
            getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
        )
        ev = QgsMapMouseEvent(self.canvas, mouse_ev)
        tool._snap_point = lambda e: QgsPointXY(6.0, 6.0)
        tool.canvasPressEvent(ev)

        self.assertEqual(tool.state, CADPolarArrayMapTool.STATE_SET_CENTER)
        self.assertEqual(len(tool.featureList), 1)
        self.assertEqual(self.polygon_layer.selectedFeatureCount(), 0)
        self.assertIsNotNone(tool.selection_rubberband)
        self.assertFalse(tool.selection_rubberband.asGeometry().isEmpty())

        tool.deactivate()
        tool.deleteLater()
        widget.deleteLater()
        self.polygon_layer.rollBack()

    def test_escape_key_step_back_and_deactivate(self):
        """Verify Esc key steps back through all 4 CAD states and deactivates."""
        widget = PolarArrayCanvasWidget(self.canvas)
        tool = CADPolarArrayMapTool(self.canvas, widget, self.iface)
        tool.activate()
        tool.featureList = [QgsFeature()]
        tool.featureLayer = self.polygon_layer
        tool.center_point = QgsPointXY(0, 0)
        tool.ref_point = QgsPointXY(10, 0)
        tool.state = CADPolarArrayMapTool.STATE_SET_ANGLE

        from qgis.PyQt.QtCore import QEvent, Qt
        from qgis.PyQt.QtGui import QKeyEvent

        def send_key(key_code):
            ev = QKeyEvent(
                getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6)),
                key_code,
                getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
            )
            tool.keyPressEvent(ev)

        esc_code = int(getattr(Qt.Key, "Key_Escape", 0x01000000))

        # 1. From STATE_SET_ANGLE -> STATE_SET_BASE_RAY
        send_key(esc_code)
        self.assertEqual(tool.state, CADPolarArrayMapTool.STATE_SET_BASE_RAY)

        # 2. From STATE_SET_BASE_RAY -> STATE_SET_CENTER
        send_key(esc_code)
        self.assertEqual(tool.state, CADPolarArrayMapTool.STATE_SET_CENTER)

        # 3. From STATE_SET_CENTER -> STATE_SELECT_FEATURE
        send_key(esc_code)
        self.assertEqual(tool.state, CADPolarArrayMapTool.STATE_SELECT_FEATURE)
        self.assertEqual(len(tool.featureList), 0)

        # 4. From STATE_SELECT_FEATURE -> deactivate
        send_key(esc_code)
        self.assertNotEqual(self.canvas.mapTool(), tool)

        tool.deleteLater()
        widget.deleteLater()

    def test_escape_key_in_hud_widget(self):
        """Verify Esc key inside HUD spinbox emits resetRequested and steps back."""
        widget = PolarArrayCanvasWidget(self.canvas)
        tool = CADPolarArrayMapTool(self.canvas, widget, self.iface)
        tool.activate()
        tool.state = CADPolarArrayMapTool.STATE_SET_ANGLE
        tool.center_point = QgsPointXY(0, 0)

        from qgis.PyQt.QtCore import QEvent, Qt
        from qgis.PyQt.QtGui import QKeyEvent

        ev = QKeyEvent(
            getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6)),
            int(getattr(Qt.Key, "Key_Escape", 0x01000000)),
            getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
        )
        handled = widget.eventFilter(widget.spin_count, ev)
        self.assertTrue(handled)
        self.assertEqual(tool.state, CADPolarArrayMapTool.STATE_SET_BASE_RAY)

        tool.deleteLater()
        widget.deleteLater()

    def test_plugin_initgui_unload_lifecycle(self):
        """Test plugin initGui, polar array action creation and unload cleanup."""
        plugin = FilletPlugin(self.iface)
        plugin.initGui()

        self.assertIsNotNone(plugin.polar_array_action)
        self.assertIsNotNone(plugin.polar_array_map_tool)
        self.assertIsNotNone(plugin.polar_array_widget)

        # Verify toggle tool sets and unsets map tool
        plugin.toggle_polar_array_tool(True)
        self.assertEqual(self.canvas.mapTool(), plugin.polar_array_map_tool)

        plugin.toggle_polar_array_tool(False)
        self.assertNotEqual(self.canvas.mapTool(), plugin.polar_array_map_tool)

        plugin.unload()
        self.assertIsNone(plugin.polar_array_action)
        self.assertIsNone(plugin.polar_array_widget)

    def test_polar_array_canvas_move_angle_tracking(self):
        """Verify that PolarArrayMapTool tracks angle smoothly past 180 deg (e.g. 270 deg) without flipping."""
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPointF, Qt
        from qgis.PyQt.QtGui import QMouseEvent

        widget = PolarArrayCanvasWidget(self.canvas)
        widget.chk_count.setChecked(True)
        widget.chk_step.setChecked(False)
        tool = CADPolarArrayMapTool(self.canvas, widget, self.iface)
        tool.center_point = QgsPointXY(0.0, 0.0)
        tool.ref_angle_rad = 0.0
        tool.state = tool.STATE_SET_ANGLE
        tool.featureList = [QgsFeature()]
        tool.featureLayer = self.polygon_layer

        def make_map_mouse_event(map_pt: QgsPointXY):
            screen_qpt = QPointF(float(map_pt.x()), float(map_pt.y()))
            mouse_ev = QMouseEvent(
                getattr(QEvent.Type, "MouseMove", getattr(QEvent, "MouseMove", 5)),
                screen_qpt,
                getattr(Qt.MouseButton, "NoButton", getattr(Qt, "NoButton", 0)),
                getattr(Qt.MouseButton, "NoButton", getattr(Qt, "NoButton", 0)),
                getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
            )
            map_ev = QgsMapMouseEvent(self.canvas, mouse_ev)
            tool._snap_point = lambda e: map_pt
            return map_ev

        # Move to 90 deg (0, 10)
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, 10.0)))
        self.assertAlmostEqual(widget.fill_angle, 90.0, delta=1.0)

        # Move to 180 deg (-10, 0.0)
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(-10.0, 0.0)))
        self.assertAlmostEqual(widget.fill_angle, 180.0, delta=1.0)

        # Move past 180 deg to 270 deg (0, -10) -> MUST NOT flip to negative, must be 270
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, -10.0)))
        self.assertAlmostEqual(widget.fill_angle, 270.0, delta=1.0)

        # Move to 360 deg: from 270 deg (0, -10) through 315 deg (7, -7) to 360 deg (10, 0.05)
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(7.0, -7.0)))
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(10.0, 0.05)))
        self.assertEqual(widget.fill_angle, 360.0)
        self.assertEqual(tool._accumulated_fill_angle_deg, 360.0)

        # Move extra full circle (0 -> 90 -> 180 -> 270 -> 360) -> MUST stay clamped at 360.0, not accumulate 720.0
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, 10.0)))
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(-10.0, 0.0)))
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, -10.0)))
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(10.0, 0.05)))
        self.assertEqual(widget.fill_angle, 360.0)
        self.assertEqual(tool._accumulated_fill_angle_deg, 360.0)

        # Immediately reverse direction to (0, -10) (270 deg) -> must immediately decrease below 360
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, -10.0)))
        self.assertAlmostEqual(widget.fill_angle, 270.0, delta=1.0)

        # Verify baseline rubberband is non-empty
        self.assertIsNotNone(tool.baseline_rubberband)
        self.assertFalse(tool.baseline_rubberband.asGeometry().isEmpty())

        # Test Clockwise movement: reset and rotate clockwise (-90 -> -180 -> -270 -> -360)
        tool._last_mouse_angle_rad = None
        tool._accumulated_fill_angle_deg = 0.0
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, -10.0)))
        self.assertAlmostEqual(widget.fill_angle, -90.0, delta=1.0)

        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(-10.0, 0.0)))
        self.assertAlmostEqual(widget.fill_angle, -180.0, delta=1.0)

        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, 10.0)))
        self.assertAlmostEqual(widget.fill_angle, -270.0, delta=1.0)

        # Move to -360 deg: through (7.0, 7.0) to (10.0, -0.05)
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(7.0, 7.0)))
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(10.0, -0.05)))
        self.assertEqual(widget.fill_angle, -360.0)
        self.assertEqual(tool._accumulated_fill_angle_deg, -360.0)

        # Over-wind CW beyond -360 and reverse back to -270 (0, 10)
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, -10.0)))
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(-10.0, 0.0)))
        self.assertEqual(widget.fill_angle, -360.0)
        self.assertEqual(tool._accumulated_fill_angle_deg, -360.0)

        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, 10.0)))
        self.assertAlmostEqual(widget.fill_angle, -270.0, delta=1.0)

        # Verify radius ray and arc rubberbands are non-empty and well-formed
        self.assertIsNotNone(tool.radius_ray_rubberband)
        self.assertFalse(tool.radius_ray_rubberband.asGeometry().isEmpty())
        self.assertIsNotNone(tool.arc_rubberband)
        self.assertFalse(tool.arc_rubberband.asGeometry().isEmpty())

    def test_fill_angle_lock_and_step_presets(self):
        """Test both step & fill angle lock buttons and presets/recent menus."""
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPointF, Qt
        from qgis.PyQt.QtGui import QMouseEvent

        widget = PolarArrayCanvasWidget(self.canvas)
        self.assertFalse(widget.is_fill_angle_locked)
        self.assertFalse(widget.is_step_angle_locked)

        # Toggle fill angle lock on
        widget.btn_lock_fill_angle.setChecked(True)
        self.assertTrue(widget.is_fill_angle_locked)
        widget.spin_fill_angle.setValue(180.0)

        # Toggle step angle lock on
        widget.btn_lock_step_angle.setChecked(True)
        self.assertTrue(widget.is_step_angle_locked)
        widget.spin_step.setValue(60.0)

        tool = CADPolarArrayMapTool(self.canvas, widget, self.iface)
        tool.center_point = QgsPointXY(0.0, 0.0)
        tool.ref_angle_rad = 0.0
        tool.state = tool.STATE_SET_ANGLE
        tool.featureList = [QgsFeature()]
        tool.featureLayer = self.polygon_layer

        def make_map_mouse_event(map_pt: QgsPointXY):
            screen_qpt = QPointF(float(map_pt.x()), float(map_pt.y()))
            mouse_ev = QMouseEvent(
                getattr(QEvent.Type, "MouseMove", getattr(QEvent, "MouseMove", 5)),
                screen_qpt,
                getattr(Qt.MouseButton, "NoButton", getattr(Qt, "NoButton", 0)),
                getattr(Qt.MouseButton, "NoButton", getattr(Qt, "NoButton", 0)),
                getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
            )
            map_ev = QgsMapMouseEvent(self.canvas, mouse_ev)
            tool._snap_point = lambda e: map_pt
            return map_ev

        # Move mouse to 90 deg -> fill_angle MUST stay locked at 180.0
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, 10.0)))
        self.assertEqual(widget.fill_angle, 180.0)
        self.assertEqual(widget.step_angle, 60.0)

        # Test step presets menu rebuild and selection
        widget._rebuild_step_menu()
        self.assertGreater(len(widget.step_menu.actions()), 5)
        widget._on_step_preset_selected(45.0)
        self.assertEqual(widget.step_angle, 45.0)
        self.assertTrue(widget.chk_step.isChecked())

        # Test recent steps storage
        recent_steps = widget._get_recent_steps()
        self.assertIn(45.0, recent_steps)

        # Test fill angle presets menu rebuild and selection
        widget._rebuild_fill_angle_menu()
        self.assertGreater(len(widget.fill_angle_menu.actions()), 5)
        widget._on_fill_angle_preset_selected(270.0)
        self.assertEqual(widget.fill_angle, 270.0)

        # Test recent fill angles storage
        recent_fills = widget._get_recent_fill_angles()
        self.assertIn(270.0, recent_fills)

    def test_4step_workflow_and_center_marker(self):
        """Test step 1 (select), step 2 (set center), step 3 (set base ray), step 4 (set angle), and step-back with Esc."""
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPointF, Qt
        from qgis.PyQt.QtGui import QKeyEvent, QMouseEvent

        self.polygon_layer.startEditing()
        feat = QgsFeature()
        box_geom = QgsGeometry.fromPolygonXY([[
            QgsPointXY(5.0, 5.0),
            QgsPointXY(7.0, 5.0),
            QgsPointXY(7.0, 7.0),
            QgsPointXY(5.0, 7.0),
            QgsPointXY(5.0, 5.0),
        ]])
        feat.setGeometry(box_geom)
        self.polygon_layer.addFeature(feat)
        self.polygon_layer.removeSelection()
        self.canvas.setCurrentLayer(self.polygon_layer)

        widget = PolarArrayCanvasWidget(self.canvas)
        tool = CADPolarArrayMapTool(self.canvas, widget, self.iface)
        tool.activate()

        # Step 1: No preselected features -> STATE_SELECT_FEATURE
        self.assertEqual(tool.state, tool.STATE_SELECT_FEATURE)
        self.assertEqual(widget._current_step, PolarArrayCanvasWidget.STEP_SELECT)

        _left_btn = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
        _right_btn = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))

        def make_click_event(pt: QgsPointXY, button=_left_btn):
            screen_qpt = QPointF(float(pt.x()), float(pt.y()))
            mouse_ev = QMouseEvent(
                getattr(QEvent.Type, "MouseButtonPress", getattr(QEvent, "MouseButtonPress", 2)),
                screen_qpt,
                button,
                button,
                getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
            )
            map_ev = QgsMapMouseEvent(self.canvas, mouse_ev)
            tool._snap_point = lambda e: pt
            return map_ev

        def make_esc_event():
            key_escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
            return QKeyEvent(
                getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6)),
                key_escape,
                getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
            )

        # Click on feature at (6, 6) -> Selects feature, moves to STEP_CENTER
        tool.canvasPressEvent(make_click_event(QgsPointXY(6.0, 6.0)))
        self.assertEqual(tool.state, tool.STATE_SET_CENTER)
        self.assertEqual(widget._current_step, PolarArrayCanvasWidget.STEP_CENTER)
        self.assertEqual(len(tool.featureList), 1)

        # Click at (0, 0) -> Sets center, moves to STEP_BASE_RAY
        tool.canvasPressEvent(make_click_event(QgsPointXY(0.0, 0.0)))
        self.assertEqual(tool.state, tool.STATE_SET_BASE_RAY)
        self.assertEqual(widget._current_step, PolarArrayCanvasWidget.STEP_BASE_RAY)
        self.assertEqual(tool.center_point, QgsPointXY(0.0, 0.0))
        self.assertEqual(tool.center_rubberband.icon(), QgsRubberBand.ICON_CROSS)

        # Click at (10, 0) -> Sets 0° base ray, moves to STEP_ANGLE
        tool.canvasPressEvent(make_click_event(QgsPointXY(10.0, 0.0)))
        self.assertEqual(tool.state, tool.STATE_SET_ANGLE)
        self.assertEqual(widget._current_step, PolarArrayCanvasWidget.STEP_ANGLE)
        self.assertEqual(tool.ref_point, QgsPointXY(10.0, 0.0))
        self.assertAlmostEqual(tool.ref_angle_rad, 0.0, places=4)

        # Press Esc at Step 4 -> steps back to Step 3 (clears ref_point, keeps center & feature)
        tool.keyPressEvent(make_esc_event())
        self.assertEqual(tool.state, tool.STATE_SET_BASE_RAY)
        self.assertEqual(widget._current_step, PolarArrayCanvasWidget.STEP_BASE_RAY)
        self.assertIsNone(tool.ref_point)
        self.assertEqual(tool.center_point, QgsPointXY(0.0, 0.0))

        # Click at (10, 0) again to move to Step 4
        tool.canvasPressEvent(make_click_event(QgsPointXY(10.0, 0.0)))
        self.assertEqual(tool.state, tool.STATE_SET_ANGLE)

        # Right-click at Step 4 -> Steps back to STEP_BASE_RAY
        tool.canvasPressEvent(make_click_event(QgsPointXY(0.0, 0.0), button=_right_btn))
        self.assertEqual(tool.state, tool.STATE_SET_BASE_RAY)
        self.assertIsNone(tool.ref_point)

        # Press Esc at Step 3 -> steps back to Step 2 (clears center, keeps feature)
        tool.keyPressEvent(make_esc_event())
        self.assertEqual(tool.state, tool.STATE_SET_CENTER)
        self.assertEqual(widget._current_step, PolarArrayCanvasWidget.STEP_CENTER)
        self.assertIsNone(tool.center_point)
        self.assertEqual(len(tool.featureList), 1)

        # Press Esc at Step 2 -> steps back to Step 1 (clears feature selection)
        tool.keyPressEvent(make_esc_event())
        self.assertEqual(tool.state, tool.STATE_SELECT_FEATURE)
        self.assertEqual(widget._current_step, PolarArrayCanvasWidget.STEP_SELECT)
        self.assertEqual(len(tool.featureList), 0)

        self.polygon_layer.rollBack()


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Unit tests for CAD 3-Point Scale with Rotation Map Tool and Geometry Engine.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
import os
import sys
import unittest

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QObject, QPoint, QPointF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QKeyEvent, QMouseEvent
from qgis.PyQt.QtWidgets import QMainWindow, QWidget

# Initialize QGIS Application
app = QgsApplication([], False)
app.initQgis()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.geometry_engine import GeometryEngine
from gui.scale_rotate_canvas_widget import ScaleRotateCanvasWidget
from gui.scale_rotate_map_tool import ScaleRotateMapTool
from plugin import FilletPlugin


class MockMessageBar(QObject):
    def __init__(self):
        super().__init__()
        self.messages = []

    def pushMessage(self, title, text, level=None, duration=0):
        self.messages.append((title, text, level, duration))


class MockIface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def __init__(self, map_canvas, main_win):
        super().__init__()
        self._canvas = map_canvas
        self._main_win = main_win
        self.message_bar = MockMessageBar()

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return self._main_win

    def addVectorToolBarIcon(self, action):
        pass

    def removeVectorToolBarIcon(self, action):
        pass

    def addPluginToVectorMenu(self, name, action):
        pass

    def removePluginVectorMenu(self, name, action):
        pass

    def addDockWidget(self, area, dock):
        pass

    def removeDockWidget(self, dock):
        pass

    def advancedDigitizeToolBar(self):
        return None

    def messageBar(self):
        return self.message_bar


win = QMainWindow()
canvas = QgsMapCanvas(win)
canvas.resize(QSize(800, 600))


class TestScaleRotateTool(unittest.TestCase):
    """Test suite for 3-Point Scale with Rotation geometry engine, widget, and map tool."""

    @classmethod
    def setUpClass(cls):
        cls.canvas = canvas

    def test_compute_3point_scale_and_rotation(self):
        """Verify mathematical calculation of scale factor and delta angle from 3 points."""
        p_origin = QgsPointXY(0.0, 0.0)
        p_ref = QgsPointXY(10.0, 0.0)  # Length = 10, Angle = 0 deg
        p_target = QgsPointXY(0.0, 20.0)  # Length = 20, Angle = 90 deg

        scale, angle = GeometryEngine.compute_3point_scale_and_rotation(p_origin, p_ref, p_target)
        self.assertAlmostEqual(scale, 2.0, places=5)
        self.assertAlmostEqual(angle, 90.0, places=5)

        # Negative rotation test: target at (0, -30) -> Length = 30, Angle = -90 deg
        p_target2 = QgsPointXY(0.0, -30.0)
        scale2, angle2 = GeometryEngine.compute_3point_scale_and_rotation(p_origin, p_ref, p_target2)
        self.assertAlmostEqual(scale2, 3.0, places=5)
        self.assertAlmostEqual(angle2, -90.0, places=5)

        # Step snapping test (e.g. 45 deg)
        p_target_snap = QgsPointXY(10.0, 9.0)  # ~42 deg -> snaps to 45 deg
        scale_s, angle_s = GeometryEngine.compute_3point_scale_and_rotation(
            p_origin, p_ref, p_target_snap, snap_step_deg=45.0
        )
        self.assertAlmostEqual(angle_s, 45.0, places=5)

    def test_scale_and_rotate_geometry_point_line_polygon(self):
        """Verify scale and rotate on Points, LineStrings, and Polygons."""
        origin = QgsPointXY(0.0, 0.0)

        # 1. Point
        pt = QgsGeometry.fromPointXY(QgsPointXY(5.0, 0.0))
        res_pt = GeometryEngine.scale_and_rotate_geometry(pt, origin, 2.0, 90.0)
        p = res_pt.asPoint()
        self.assertAlmostEqual(p.x(), 0.0, places=4)
        self.assertAlmostEqual(p.y(), 10.0, places=4)

        # 2. LineString
        line = QgsGeometry.fromPolylineXY([QgsPointXY(2.0, 0.0), QgsPointXY(6.0, 0.0)])
        res_line = GeometryEngine.scale_and_rotate_geometry(line, origin, 1.5, 180.0)
        pts = res_line.asPolyline()
        self.assertAlmostEqual(pts[0].x(), -3.0, places=4)
        self.assertAlmostEqual(pts[0].y(), 0.0, places=4)
        self.assertAlmostEqual(pts[1].x(), -9.0, places=4)
        self.assertAlmostEqual(pts[1].y(), 0.0, places=4)

        # 3. Polygon
        poly = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0.0, 0.0),
            QgsPointXY(4.0, 0.0),
            QgsPointXY(4.0, 4.0),
            QgsPointXY(0.0, 4.0),
            QgsPointXY(0.0, 0.0)
        ]])
        res_poly = GeometryEngine.scale_and_rotate_geometry(poly, origin, 2.0, 0.0)
        poly_pts = res_poly.asPolygon()[0]
        self.assertAlmostEqual(poly_pts[1].x(), 8.0, places=4)
        self.assertAlmostEqual(poly_pts[2].y(), 8.0, places=4)

    def test_widget_controls_and_locks(self):
        """Verify widget controls, spinboxes, lock states, and copy mode."""
        widget = ScaleRotateCanvasWidget(self.canvas)
        widget.show_on_canvas()
        self.assertEqual(widget._current_step, ScaleRotateCanvasWidget.STEP_ORIGIN)

        # Set values
        widget.set_scale(1.75)
        self.assertAlmostEqual(widget.scale_factor, 1.75, places=4)
        widget.set_angle(45.0)
        self.assertAlmostEqual(widget.angle, 45.0, places=2)

        # Locks
        self.assertFalse(widget.is_scale_locked)
        self.assertFalse(widget.is_angle_locked)
        widget.btn_lock_scale.setChecked(True)
        widget.btn_lock_angle.setChecked(True)
        self.assertTrue(widget.is_scale_locked)
        self.assertTrue(widget.is_angle_locked)

        # Snap mode radio buttons and Shift inversion
        widget.set_snap_mode("free")
        self.assertFalse(widget.is_snap_enabled)
        self.assertFalse(widget.combo_snap.isEnabled())
        self.assertIsNone(widget.get_effective_snap_step(shift_pressed=False))
        self.assertEqual(widget.get_effective_snap_step(shift_pressed=True), widget.snap_step)
        widget.set_shift_override(False)
        self.assertFalse(widget.combo_snap.isEnabled())

        widget.set_snap_mode("angle")
        self.assertTrue(widget.is_snap_enabled)
        self.assertTrue(widget.combo_snap.isEnabled())
        self.assertEqual(widget.get_effective_snap_step(shift_pressed=False), widget.snap_step)
        self.assertIsNone(widget.get_effective_snap_step(shift_pressed=True))
        widget.set_shift_override(False)
        self.assertTrue(widget.combo_snap.isEnabled())

        # Step changes
        widget.set_step(ScaleRotateCanvasWidget.STEP_REFERENCE)
        self.assertEqual(widget._current_step, ScaleRotateCanvasWidget.STEP_REFERENCE)
        widget.set_step(ScaleRotateCanvasWidget.STEP_TARGET)
        self.assertEqual(widget._current_step, ScaleRotateCanvasWidget.STEP_TARGET)
        widget.hide()

    def test_scale_rotate_state_machine_and_workflow(self):
        """Test tool state transitions: ORIGIN -> REFERENCE -> TRANSFORMING -> COMMIT."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "temp_poly", "memory")
        pr = layer.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        pr.addFeatures([feat])
        layer.updateExtents()

        layer.startEditing()
        layer.selectByIds([1])
        self.canvas.setCurrentLayer(layer)

        widget = ScaleRotateCanvasWidget(self.canvas)
        widget.chk_copy.setChecked(False)
        tool = ScaleRotateMapTool(self.canvas, widget)
        tool.activate()

        self.assertEqual(tool.state, ScaleRotateMapTool.STATE_SET_ORIGIN)

        # Step 1: Set Origin
        tool.origin_point = QgsPointXY(0, 0)
        tool.state = ScaleRotateMapTool.STATE_SET_REFERENCE
        widget.set_step(ScaleRotateCanvasWidget.STEP_REFERENCE)

        # Step 2: Set Reference Point
        tool.ref_point = QgsPointXY(10, 0)
        tool.state = ScaleRotateMapTool.STATE_TRANSFORMING
        widget.set_step(ScaleRotateCanvasWidget.STEP_TARGET)

        # Step 3: Compute Scale & Rotation to target (0, 20)
        target = QgsPointXY(0, 20)
        scale, angle = GeometryEngine.compute_3point_scale_and_rotation(tool.origin_point, tool.ref_point, target)
        self.assertAlmostEqual(scale, 2.0)
        self.assertAlmostEqual(angle, 90.0)

        tool.current_scale = scale
        tool.current_angle = angle

        # Commit in place
        tool.commit_transformation()

        # Check transformed feature
        f_after = layer.getFeature(1)
        pts_after = f_after.geometry().asPolygon()[0]
        self.assertAlmostEqual(pts_after[1].x(), 0.0, places=3)
        self.assertAlmostEqual(pts_after[1].y(), 20.0, places=3)

        tool.cleanup()
        layer.rollBack()

    def test_scale_rotate_tool_copy_mode(self):
        """Test 3-step workflow with Duplicate (copy) mode enabled."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "temp_poly", "memory")
        pr = layer.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        pr.addFeatures([feat])
        layer.updateExtents()

        layer.startEditing()
        layer.selectByIds([1])
        self.canvas.setCurrentLayer(layer)
        self.assertEqual(layer.featureCount(), 1)

        widget = ScaleRotateCanvasWidget(self.canvas)
        widget.chk_copy.setChecked(True)
        tool = ScaleRotateMapTool(self.canvas, widget)
        tool.activate()

        tool.origin_point = QgsPointXY(0, 0)
        tool.ref_point = QgsPointXY(10, 0)
        tool.current_scale = 1.5
        tool.current_angle = 45.0
        tool.state = ScaleRotateMapTool.STATE_TRANSFORMING

        tool.commit_transformation()

        # A new feature should have been added
        self.assertEqual(layer.featureCount(), 2)

        tool.cleanup()
        layer.rollBack()

    def test_preview_and_commit_use_canvas_crs(self):
        previous_crs = self.canvas.mapSettings().destinationCrs()
        canvas_crs = QgsCoordinateReferenceSystem("EPSG:3857")
        layer_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        self.canvas.setDestinationCrs(canvas_crs)

        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "crs_poly", "memory")
        source = QgsGeometry.fromPolygonXY([[
            QgsPointXY(1.0, 45.0),
            QgsPointXY(1.1, 45.0),
            QgsPointXY(1.1, 45.1),
            QgsPointXY(1.0, 45.1),
            QgsPointXY(1.0, 45.0),
        ]])
        feature = QgsFeature(layer.fields())
        feature.setGeometry(source)
        layer.dataProvider().addFeatures([feature])
        layer.startEditing()
        layer.selectAll()
        self.canvas.setCurrentLayer(layer)

        to_canvas = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
        origin = to_canvas.transform(QgsPointXY(0.0, 45.0))
        expected_canvas = QgsGeometry(source)
        expected_canvas.transform(to_canvas)
        expected_canvas = GeometryEngine.scale_and_rotate_geometry(
            expected_canvas,
            origin,
            1.5,
            30.0,
        )

        widget = ScaleRotateCanvasWidget(self.canvas)
        tool = ScaleRotateMapTool(self.canvas, widget)
        tool.origin_point = origin
        tool.current_scale = 1.5
        tool.current_angle = 30.0
        tool.state = ScaleRotateMapTool.STATE_TRANSFORMING
        tool._update_preview(1.5, 30.0)

        preview_first = next(tool.preview_rubberband.asGeometry().vertices())
        expected_first = next(expected_canvas.vertices())
        self.assertAlmostEqual(preview_first.x(), expected_first.x(), places=3)
        self.assertAlmostEqual(preview_first.y(), expected_first.y(), places=3)

        tool.commit_transformation()
        committed = next(layer.getFeatures()).geometry()
        committed.transform(to_canvas)
        committed_first = next(committed.vertices())
        self.assertAlmostEqual(committed_first.x(), expected_first.x(), places=3)
        self.assertAlmostEqual(committed_first.y(), expected_first.y(), places=3)

        tool.cleanup()
        layer.rollBack()
        self.canvas.setDestinationCrs(previous_crs)

    def test_scale_rotate_space_toggle_lock(self):
        """Verify Space key toggles lock for scale and rotation."""
        widget = ScaleRotateCanvasWidget(self.canvas)
        tool = ScaleRotateMapTool(self.canvas, widget)
        tool.activate()

        evt_type = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6))
        key_space = getattr(Qt.Key, "Key_Space", getattr(Qt, "Key_Space", 0x20))
        no_mod = getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0))

        self.assertFalse(widget.is_scale_locked)
        tool.keyPressEvent(QKeyEvent(evt_type, key_space, no_mod))
        self.assertTrue(widget.is_scale_locked)

        tool.cleanup()
        widget.hide()

    def test_scale_rotate_escape_key_and_rollback(self):
        """Test Escape key step back and widget resetRequested emission."""
        widget = ScaleRotateCanvasWidget(self.canvas)
        tool = ScaleRotateMapTool(self.canvas, widget)
        tool.activate()

        # Step 1: Set Origin
        tool.origin_point = QgsPointXY(0, 0)
        tool.state = ScaleRotateMapTool.STATE_SET_REFERENCE
        widget.set_step(ScaleRotateCanvasWidget.STEP_REFERENCE)

        # Step 2: Set Reference Point
        tool.ref_point = QgsPointXY(10, 0)
        tool.state = ScaleRotateMapTool.STATE_TRANSFORMING
        widget.set_step(ScaleRotateCanvasWidget.STEP_TARGET)

        evt_type = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6))
        key_esc = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
        no_mod = getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0))
        esc_event = QKeyEvent(evt_type, key_esc, no_mod)

        # 1. Escape key on Step 3 -> steps back to Step 2
        tool.keyPressEvent(esc_event)
        self.assertEqual(tool.state, ScaleRotateMapTool.STATE_SET_REFERENCE)
        self.assertEqual(widget._current_step, ScaleRotateCanvasWidget.STEP_REFERENCE)
        self.assertIsNone(tool.ref_point)
        self.assertIsNotNone(tool.origin_point)

        # 2. Escape key on Step 2 -> steps back to Step 1
        tool.keyPressEvent(esc_event)
        self.assertEqual(tool.state, ScaleRotateMapTool.STATE_SET_ORIGIN)
        self.assertEqual(widget._current_step, ScaleRotateCanvasWidget.STEP_ORIGIN)
        self.assertIsNone(tool.origin_point)

        # 3. Widget eventFilter emits resetRequested on Escape
        reset_emitted = []
        widget.resetRequested.connect(lambda: reset_emitted.append(True))
        line_edit = widget.spin_scale.lineEdit() if hasattr(widget.spin_scale, "lineEdit") else widget.spin_scale
        widget.eventFilter(line_edit, esc_event)
        self.assertGreater(len(reset_emitted), 0)

        tool.cleanup()

    def test_plugin_lifecycle_integration(self):
        """Verify plugin initGui, action enablement, and unload cleanup for Scale & Rotate tool."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "test_poly", "memory")
        pr = layer.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.0, 0.0),
            QgsPointXY(10.0, 10.0),
            QgsPointXY(0.0, 10.0),
            QgsPointXY(0.0, 0.0)
        ]]))
        pr.addFeatures([feat])
        layer.updateExtents()

        QgsProject.instance().addMapLayer(layer)
        self.canvas.setLayers([layer])
        self.canvas.setCurrentLayer(layer)
        layer.startEditing()

        mock_iface = MockIface(self.canvas, win)
        plugin = FilletPlugin(mock_iface)
        plugin.initGui()

        self.assertIsNotNone(plugin.scale_rotate_action)
        self.assertIsNotNone(plugin.scale_rotate_map_tool)
        self.assertIsNotNone(plugin.scale_rotate_widget)

        # Action is enabled when layer is editable with selection
        layer.selectAll()
        plugin.update_action_state()
        self.assertTrue(plugin.scale_rotate_action.isEnabled())

        # Action is disabled when no selection
        layer.removeSelection()
        plugin.update_action_state()
        self.assertFalse(plugin.scale_rotate_action.isEnabled())

        # Unload cleanup
        plugin.unload()
        self.assertIsNone(plugin.scale_rotate_action)
        self.assertIsNone(plugin.scale_rotate_map_tool)
        self.assertIsNone(plugin.scale_rotate_widget)

        layer.rollBack()
        QgsProject.instance().removeMapLayer(layer.id())

    def test_scale_rotate_continuous_past_180_degrees(self):
        """Verify that dragging the mouse past 180 deg does not flip and smoothly tracks continuous rotation."""
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPointF, Qt
        from qgis.PyQt.QtGui import QMouseEvent

        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "temp_poly", "memory")
        pr = layer.dataProvider()
        feat = QgsFeature()
        geom = QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10)]])
        feat.setGeometry(geom)
        pr.addFeatures([feat])
        layer.updateExtents()

        layer.startEditing()
        layer.selectByIds([1])
        self.canvas.setCurrentLayer(layer)

        widget = ScaleRotateCanvasWidget(self.canvas)
        tool = ScaleRotateMapTool(self.canvas, widget)
        tool.activate()

        tool.origin_point = QgsPointXY(0.0, 0.0)
        tool.ref_point = QgsPointXY(10.0, 0.0)
        tool.state = tool.STATE_TRANSFORMING
        tool._last_mouse_angle_rad = 0.0
        tool._accumulated_angle_deg = 0.0

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
            tool.toMapCoordinates = lambda pos: map_pt
            return map_ev

        # Move to 90 deg (0, 10)
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, 10.0)))
        self.assertAlmostEqual(tool.current_angle, 90.0, delta=1.0)

        # Move to 180 deg (-10, 0.1)
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(-10.0, 0.1)))
        self.assertAlmostEqual(tool.current_angle, 180.0, delta=2.0)

        # Move past 180 to 270 deg (0, -10) -> MUST NOT FLIP to -90, must be +270
        tool.canvasMoveEvent(make_map_mouse_event(QgsPointXY(0.0, -10.0)))
        self.assertAlmostEqual(tool.current_angle, 270.0, delta=2.0)

        layer.rollBack()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestScaleRotateTool)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if res.wasSuccessful() else 1)

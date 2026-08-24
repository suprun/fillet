# -*- coding: utf-8 -*-
"""
Tests for CAD Rotate tool (RotateMapTool, RotationCanvasWidget, and GeometryEngine rotation methods).
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
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas

app = QgsApplication([], False)
app.initQgis()

from core.geometry_engine import GeometryEngine
from gui.rotate_map_tool import RotateMapTool
from gui.rotation_canvas_widget import RotationCanvasWidget


class TestCADRotateTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canvas = QgsMapCanvas()

    @classmethod
    def tearDownClass(cls):
        cls.canvas = None

    def test_calculate_bearing_and_rotation_angle(self):
        center = QgsPointXY(0, 0)
        p_east = QgsPointXY(10, 0)
        p_north = QgsPointXY(0, 10)
        p_west = QgsPointXY(-10, 0)
        p_south = QgsPointXY(0, -10)

        # Bearing
        self.assertAlmostEqual(GeometryEngine.calculate_bearing(center, p_east), 0.0)
        self.assertAlmostEqual(GeometryEngine.calculate_bearing(center, p_north), 90.0)
        self.assertAlmostEqual(GeometryEngine.calculate_bearing(center, p_west), 180.0)
        self.assertAlmostEqual(GeometryEngine.calculate_bearing(center, p_south), -90.0)

        # Delta angle from East to North (+90 CCW)
        self.assertAlmostEqual(GeometryEngine.calculate_rotation_angle(center, p_east, p_north), 90.0)
        # Delta angle from North to East (-90 CCW / 90 CW)
        self.assertAlmostEqual(GeometryEngine.calculate_rotation_angle(center, p_north, p_east), -90.0)
        # Delta angle from South to North (180)
        self.assertAlmostEqual(GeometryEngine.calculate_rotation_angle(center, p_south, p_north), 180.0)

    def test_rotate_geometry_types(self):
        center = QgsPointXY(0, 0)

        # 1. Point rotation
        pt_geom = QgsGeometry.fromPointXY(QgsPointXY(10, 0))
        rot_pt = GeometryEngine.rotate_geometry(pt_geom, center, 90.0)
        self.assertAlmostEqual(rot_pt.asPoint().x(), 0.0)
        self.assertAlmostEqual(rot_pt.asPoint().y(), 10.0)

        # 2. LineString rotation
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(10, 0)])
        rot_line = GeometryEngine.rotate_geometry(line_geom, center, 45.0)
        pts = rot_line.asPolyline()
        self.assertAlmostEqual(pts[0].x(), 0.0)
        self.assertAlmostEqual(pts[0].y(), 0.0)
        self.assertAlmostEqual(pts[1].x(), 10.0 * math.cos(math.radians(45.0)))
        self.assertAlmostEqual(pts[1].y(), 10.0 * math.sin(math.radians(45.0)))

        # 3. Polygon rotation
        poly_geom = QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10)]])
        rot_poly = GeometryEngine.rotate_geometry(poly_geom, center, 180.0)
        ring = rot_poly.asPolygon()[0]
        self.assertAlmostEqual(ring[1].x(), -10.0)
        self.assertAlmostEqual(ring[1].y(), 0.0)

    def test_rotation_canvas_widget_ui(self):
        widget = RotationCanvasWidget(self.canvas)
        widget.set_step(RotationCanvasWidget.STEP_PIVOT)
        self.assertEqual(widget._current_step, RotationCanvasWidget.STEP_PIVOT)

        widget.set_step(RotationCanvasWidget.STEP_ROTATING)
        self.assertEqual(widget._current_step, RotationCanvasWidget.STEP_ROTATING)

        widget.set_angle(45.5)
        self.assertAlmostEqual(widget.angle, 45.5)

        widget.btn_lock_angle.setChecked(True)
        self.assertTrue(widget.is_angle_locked)

        widget.chk_copy.setChecked(True)
        self.assertTrue(widget.is_copy_mode)

        # Snap mode radio buttons and Shift inversion
        widget.rb_snap_free.setChecked(True)
        self.assertFalse(widget.is_snap_enabled)
        self.assertFalse(widget.combo_snap.isEnabled())
        self.assertIsNone(widget.get_effective_snap_step(shift_pressed=False))
        self.assertEqual(widget.get_effective_snap_step(shift_pressed=True), widget.snap_step)

        widget.rb_snap_angle.setChecked(True)
        self.assertTrue(widget.is_snap_enabled)
        self.assertTrue(widget.combo_snap.isEnabled())
        self.assertEqual(widget.get_effective_snap_step(shift_pressed=False), widget.snap_step)
        self.assertIsNone(widget.get_effective_snap_step(shift_pressed=True))

    def test_rotate_map_tool_lifecycle_and_state_machine(self):
        widget = RotationCanvasWidget(self.canvas)
        tool = RotateMapTool(self.canvas, widget)

        self.assertEqual(tool.state, RotateMapTool.STATE_SET_PIVOT)
        self.assertIsNone(tool.pivot_point)

        # Step 1: Set Pivot
        tool.pivot_point = QgsPointXY(5, 5)
        tool.state = RotateMapTool.STATE_SET_REFERENCE
        widget.set_step(RotationCanvasWidget.STEP_REFERENCE)

        # Step 2: Set Reference
        tool.ref_point = QgsPointXY(15, 5)
        tool.state = RotateMapTool.STATE_ROTATING
        widget.set_step(RotationCanvasWidget.STEP_ROTATING)

        # Step 3: Calculate rotation angle to (5, 15) -> 90 degrees
        target = QgsPointXY(5, 15)
        angle = GeometryEngine.calculate_rotation_angle(tool.pivot_point, tool.ref_point, target)
        self.assertAlmostEqual(angle, 90.0)

        # Reset
        tool.reset_state()
        self.assertEqual(tool.state, RotateMapTool.STATE_SET_PIVOT)
        self.assertIsNone(tool.pivot_point)
        self.assertIsNone(tool.ref_point)

    def test_rotate_tool_commit_transaction(self):
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

        widget = RotationCanvasWidget(self.canvas)
        tool = RotateMapTool(self.canvas, widget)

        tool.pivot_point = QgsPointXY(0, 0)
        tool.ref_point = QgsPointXY(10, 0)
        tool.current_angle = 90.0
        tool.state = RotateMapTool.STATE_ROTATING

        # Commit rotation
        tool.commit_rotation()

        # Verify geometry in layer
        feat_after = layer.getFeature(1)
        poly_after = feat_after.geometry().asPolygon()[0]
        self.assertAlmostEqual(poly_after[1].x(), 0.0)
        self.assertAlmostEqual(poly_after[1].y(), 10.0)

        layer.rollBack()

    def test_rotate_tool_copy_mode(self):
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

        widget = RotationCanvasWidget(self.canvas)
        widget.chk_copy.setChecked(True)
        tool = RotateMapTool(self.canvas, widget)

        tool.pivot_point = QgsPointXY(0, 0)
        tool.ref_point = QgsPointXY(10, 0)
        tool.current_angle = 45.0
        tool.state = RotateMapTool.STATE_ROTATING

        tool.commit_rotation()

        # Should have 2 features now (original + copy)
        self.assertEqual(layer.featureCount(), 2)

        layer.rollBack()

    def test_step_back_and_deactivate_cleanup(self):
        """Test Escape/Right-click step back (Variant 1) and clean deactivation."""
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPoint, Qt
        from qgis.PyQt.QtGui import QKeyEvent

        _KeyPress = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6))
        _Key_Escape = getattr(Qt.Key, "Key_Escape", getattr(Qt, "Key_Escape", 0x01000000))
        _NoModifier = getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0))

        widget = RotationCanvasWidget(self.canvas)
        tool = RotateMapTool(self.canvas, widget)

        # Set up to Step 3
        tool.pivot_point = QgsPointXY(0, 0)
        tool.ref_point = QgsPointXY(10, 0)
        tool.state = RotateMapTool.STATE_ROTATING
        widget.set_step(RotationCanvasWidget.STEP_ROTATING)

        # 1. Escape key on Step 3 -> steps back to Step 2
        esc_event = QKeyEvent(_KeyPress, _Key_Escape, _NoModifier)
        tool.keyPressEvent(esc_event)
        self.assertEqual(tool.state, RotateMapTool.STATE_SET_REFERENCE)
        self.assertEqual(widget._current_step, RotationCanvasWidget.STEP_REFERENCE)
        self.assertIsNone(tool.ref_point)
        self.assertIsNotNone(tool.pivot_point)

        # 2. Escape key on Step 2 -> steps back to Step 1 (full reset)
        tool.keyPressEvent(esc_event)
        self.assertEqual(tool.state, RotateMapTool.STATE_SET_PIVOT)
        self.assertEqual(widget._current_step, RotationCanvasWidget.STEP_PIVOT)
        self.assertIsNone(tool.pivot_point)

        # 3. Deactivate -> clean state and hidden widget
        tool.pivot_point = QgsPointXY(5, 5)
        tool.state = RotateMapTool.STATE_SET_REFERENCE
        widget.show()
        tool.deactivate()
        self.assertEqual(tool.state, RotateMapTool.STATE_SET_PIVOT)
        self.assertIsNone(tool.pivot_point)
        self.assertFalse(widget.isVisible())

    def test_rotate_baseline_rendering(self):
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPointF, Qt
        from qgis.PyQt.QtGui import QMouseEvent

        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "temp_poly", "memory")
        feat = QgsFeature()
        geom = QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10)]])
        feat.setGeometry(geom)
        layer.dataProvider().addFeatures([feat])
        layer.startEditing()
        layer.selectByIds([1])
        self.canvas.setCurrentLayer(layer)

        widget = RotationCanvasWidget(self.canvas)
        tool = RotateMapTool(self.canvas, widget)
        tool.activate()

        # Step 1: Set Pivot at (0, 0)
        tool.pivot_point = QgsPointXY(0, 0)
        tool.state = RotateMapTool.STATE_SET_REFERENCE

        evt_move = getattr(QEvent.Type, "MouseMove", getattr(QEvent, "MouseMove", 5))
        no_btn = getattr(Qt.MouseButton, "NoButton", getattr(Qt, "NoButton", 0))
        no_mod = getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0))

        # Move mouse to (100, 100) using QPointF for Qt5/Qt6 compatibility
        try:
            native_evt = QMouseEvent(evt_move, QPointF(100.0, 100.0), no_btn, no_btn, no_mod)
        except Exception:
            # Fallback for Qt6 positional signatures
            native_evt = QMouseEvent(evt_move, QPointF(100.0, 100.0), QPointF(100.0, 100.0), no_btn, no_btn, no_mod)

        move_evt = QgsMapMouseEvent(self.canvas, native_evt)
        tool.canvasMoveEvent(move_evt)

        # Baseline rubberband should be active with 2 vertices and not inf
        self.assertEqual(tool.baseline_rubberband.numberOfVertices(), 2)
        p0 = tool.baseline_rubberband.getPoint(0, 0)
        self.assertFalse(math.isinf(p0.x()))
        self.assertFalse(math.isinf(p0.y()))

    def test_rotate_space_toggle_lock(self):
        from qgis.PyQt.QtCore import QEvent, Qt
        from qgis.PyQt.QtGui import QKeyEvent

        widget = RotationCanvasWidget(self.canvas)
        tool = RotateMapTool(self.canvas, widget)
        tool.activate()

        evt_type = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6))
        key_space = getattr(Qt.Key, "Key_Space", getattr(Qt, "Key_Space", 0x20))
        no_mod = getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0))

        self.assertFalse(widget.is_angle_locked)
        tool.keyPressEvent(QKeyEvent(evt_type, key_space, no_mod))
        self.assertTrue(widget.is_angle_locked)
        tool.keyPressEvent(QKeyEvent(evt_type, key_space, no_mod))
        self.assertFalse(widget.is_angle_locked)


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCADRotateTool)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if res.wasSuccessful() else 1)

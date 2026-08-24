# -*- coding: utf-8 -*-
"""
Tests for CAD Mirror tool (MirrorMapTool, MirrorCanvasWidget, and GeometryEngine mirror methods).
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
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas

app = QgsApplication([], False)
app.initQgis()

from core.geometry_engine import GeometryEngine
from gui.mirror_canvas_widget import MirrorCanvasWidget
from gui.mirror_map_tool import MirrorMapTool


class TestCADMirrorTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canvas = QgsMapCanvas()

    @classmethod
    def tearDownClass(cls):
        cls.canvas = None

    def test_mirror_point(self):
        # 1. Reflection across Y-axis (line x=0 from (0,0) to (0,10))
        p1 = QgsPointXY(0, 0)
        p2 = QgsPointXY(0, 10)
        p = QgsPointXY(5, 3)
        mp = GeometryEngine.mirror_point(p, p1, p2)
        self.assertAlmostEqual(mp.x(), -5.0)
        self.assertAlmostEqual(mp.y(), 3.0)

        # 2. Reflection across X-axis (line y=0 from (0,0) to (10,0))
        p1 = QgsPointXY(0, 0)
        p2 = QgsPointXY(10, 0)
        p = QgsPointXY(5, 3)
        mp = GeometryEngine.mirror_point(p, p1, p2)
        self.assertAlmostEqual(mp.x(), 5.0)
        self.assertAlmostEqual(mp.y(), -3.0)

        # 3. Reflection across diagonal y=x (line from (0,0) to (10,10))
        p1 = QgsPointXY(0, 0)
        p2 = QgsPointXY(10, 10)
        p = QgsPointXY(2, 7)
        mp = GeometryEngine.mirror_point(p, p1, p2)
        self.assertAlmostEqual(mp.x(), 7.0)
        self.assertAlmostEqual(mp.y(), 2.0)

    def test_mirror_geometry_types(self):
        p1 = QgsPointXY(0, 0)
        p2 = QgsPointXY(0, 10)  # Y-axis

        # 1. Point reflection
        pt_geom = QgsGeometry.fromPointXY(QgsPointXY(10, 5))
        m_pt = GeometryEngine.mirror_geometry(pt_geom, p1, p2)
        self.assertAlmostEqual(m_pt.asPoint().x(), -10.0)
        self.assertAlmostEqual(m_pt.asPoint().y(), 5.0)

        # 2. LineString reflection
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(2, 2), QgsPointXY(8, 6)])
        m_line = GeometryEngine.mirror_geometry(line_geom, p1, p2)
        pts = m_line.asPolyline()
        self.assertAlmostEqual(pts[0].x(), -2.0)
        self.assertAlmostEqual(pts[0].y(), 2.0)
        self.assertAlmostEqual(pts[1].x(), -8.0)
        self.assertAlmostEqual(pts[1].y(), 6.0)

        # 3. Polygon reflection with hole
        exterior = [QgsPointXY(2, 2), QgsPointXY(10, 2), QgsPointXY(10, 10), QgsPointXY(2, 10), QgsPointXY(2, 2)]
        hole = [QgsPointXY(4, 4), QgsPointXY(6, 4), QgsPointXY(6, 6), QgsPointXY(4, 6), QgsPointXY(4, 4)]
        poly_geom = QgsGeometry.fromPolygonXY([exterior, hole])
        m_poly = GeometryEngine.mirror_geometry(poly_geom, p1, p2)
        rings = m_poly.asPolygon()
        self.assertEqual(len(rings), 2)
        self.assertAlmostEqual(rings[0][0].x(), -2.0)
        self.assertAlmostEqual(rings[0][0].y(), 2.0)
        self.assertAlmostEqual(rings[1][0].x(), -4.0)
        self.assertAlmostEqual(rings[1][0].y(), 4.0)

        # 4. MultiPolygon reflection
        mpoly_geom = QgsGeometry.fromMultiPolygonXY([[exterior]])
        m_mpoly = GeometryEngine.mirror_geometry(mpoly_geom, p1, p2)
        self.assertTrue(m_mpoly.isMultipart())
        self.assertAlmostEqual(m_mpoly.asMultiPolygon()[0][0][0].x(), -2.0)

    def test_mirror_canvas_widget_ui(self):
        widget = MirrorCanvasWidget(self.canvas)
        widget.set_step(MirrorCanvasWidget.STEP_FIRST_POINT)
        self.assertEqual(widget._current_step, MirrorCanvasWidget.STEP_FIRST_POINT)

        widget.set_step(MirrorCanvasWidget.STEP_SECOND_POINT)
        self.assertEqual(widget._current_step, MirrorCanvasWidget.STEP_SECOND_POINT)

        widget.chk_copy.setChecked(True)
        self.assertTrue(widget.is_copy_mode)

        widget.chk_copy.setChecked(False)
        self.assertFalse(widget.is_copy_mode)

        widget.save_settings()

    def test_mirror_map_tool_lifecycle(self):
        widget = MirrorCanvasWidget(self.canvas)
        tool = MirrorMapTool(self.canvas, widget)

        tool.activate()
        self.assertEqual(tool.state, MirrorMapTool.STATE_FIRST_POINT)

        tool.p1 = QgsPointXY(0, 0)
        tool.state = MirrorMapTool.STATE_SECOND_POINT
        tool.reset_state()
        self.assertEqual(tool.state, MirrorMapTool.STATE_FIRST_POINT)
        self.assertIsNone(tool.p1)

        tool.cleanup()

    def test_mirror_map_tool_commit_modify_original(self):
        # Create in-memory editable polygon layer
        layer = QgsVectorLayer("Polygon?crs=epsg:3857", "test_layer", "memory")
        self.assertTrue(layer.isValid())
        self.canvas.setLayers([layer])
        self.canvas.setCurrentLayer(layer)

        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(2, 2), QgsPointXY(6, 2), QgsPointXY(6, 6), QgsPointXY(2, 6), QgsPointXY(2, 2)]]))
        layer.dataProvider().addFeatures([feat])

        # Select feature
        fids = [f.id() for f in layer.getFeatures()]
        layer.selectByIds(fids)

        layer.startEditing()

        widget = MirrorCanvasWidget(self.canvas)
        widget.chk_copy.setChecked(False)
        tool = MirrorMapTool(self.canvas, widget)
        tool.activate()

        # Mirror across line x=0 (Y-axis)
        tool.p1 = QgsPointXY(0, 0)
        tool.p2 = QgsPointXY(0, 10)
        tool.commit_mirror()

        self.assertEqual(layer.featureCount(), 1)
        mod_feat = next(layer.getFeatures())
        ring = mod_feat.geometry().asPolygon()[0]
        self.assertAlmostEqual(ring[0].x(), -2.0)
        self.assertAlmostEqual(ring[0].y(), 2.0)

        layer.rollBack()

    def test_mirror_map_tool_commit_copy_mode(self):
        layer = QgsVectorLayer("Polygon?crs=epsg:3857", "test_copy_layer", "memory")
        self.assertTrue(layer.isValid())
        self.canvas.setLayers([layer])
        self.canvas.setCurrentLayer(layer)

        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(2, 2), QgsPointXY(6, 2), QgsPointXY(6, 6), QgsPointXY(2, 6), QgsPointXY(2, 2)]]))
        layer.dataProvider().addFeatures([feat])

        fids = [f.id() for f in layer.getFeatures()]
        layer.selectByIds(fids)

        layer.startEditing()

        widget = MirrorCanvasWidget(self.canvas)
        widget.chk_copy.setChecked(True)
        tool = MirrorMapTool(self.canvas, widget)
        tool.activate()

        # Mirror across line x=0 (Y-axis) in copy mode
        tool.p1 = QgsPointXY(0, 0)
        tool.p2 = QgsPointXY(0, 10)
        tool.commit_mirror()

        # Layer should now contain 2 features (original + mirrored copy)
        self.assertEqual(layer.featureCount(), 2)

        layer.rollBack()

    def test_mirror_angle_input_and_locking(self):
        widget = MirrorCanvasWidget(self.canvas)
        widget.set_angle(45.0)
        self.assertAlmostEqual(widget.angle, 45.0)

        widget.btn_lock_angle.setChecked(True)
        self.assertTrue(widget.is_angle_locked)

        # Tab order test
        spin_line_edit = widget.spin_angle.lineEdit() if hasattr(widget.spin_angle, "lineEdit") and widget.spin_angle.lineEdit() else widget.spin_angle
        self.assertEqual(spin_line_edit.nextInFocusChain(), widget.btn_lock_angle)

        widget.btn_lock_angle.setChecked(False)
        self.assertFalse(widget.is_angle_locked)

    def test_mirror_keypress_event_and_snapping(self):
        from qgis.PyQt.QtCore import QEvent, Qt
        from qgis.PyQt.QtGui import QKeyEvent

        widget = MirrorCanvasWidget(self.canvas)
        tool = MirrorMapTool(self.canvas, widget)
        tool.activate()

        tool.p1 = QgsPointXY(0, 0)
        tool.p2 = QgsPointXY(0, 10)
        tool.state = MirrorMapTool.STATE_SECOND_POINT

        evt_type = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6))
        key_return = getattr(Qt.Key, "Key_Return", getattr(Qt, "Key_Return", 0x01000004))
        no_mod = getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0))

        # Simulate Return key press
        key_evt = QKeyEvent(evt_type, key_return, no_mod)
        tool.keyPressEvent(key_evt)
        # Should not raise NameError and reset state
        self.assertEqual(tool.state, MirrorMapTool.STATE_FIRST_POINT)

    def test_mirror_space_toggle_lock(self):
        from qgis.PyQt.QtCore import QEvent, Qt
        from qgis.PyQt.QtGui import QKeyEvent

        widget = MirrorCanvasWidget(self.canvas)
        tool = MirrorMapTool(self.canvas, widget)
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
    unittest.main()

# -*- coding: utf-8 -*-
"""
Unit tests for CAD Edge Offset (Parallel Shift) Tool.
Tests geometry engine algorithms, canvas widget, map tool, Shift inversion, and lifecycle.
"""

import math
import os
import unittest

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsLineString,
    QgsMultiLineString,
    QgsMultiPolygon,
    QgsPoint,
    QgsPointXY,
    QgsPolygon,
    QgsSettings,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QEvent, Qt
from qgis.PyQt.QtGui import QKeyEvent

from core.geometry_engine import GeometryEngine
from core.snapping_helper import SegmentMatch
from gui.edge_offset_canvas_widget import EdgeOffsetCanvasWidget
from gui.edge_offset_map_tool import EdgeOffsetMapTool
from plugin import FilletPlugin


class DummyInterface:
    def __init__(self, canvas):
        self._canvas = canvas
        self._actions = []

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return self._canvas

    def advancedDigitizeToolBar(self):
        return None

    def addVectorToolBarIcon(self, action):
        self._actions.append(action)

    def removeVectorToolBarIcon(self, action):
        if action in self._actions:
            self._actions.remove(action)

    def addPluginToVectorMenu(self, name, action):
        pass

    def removePluginVectorMenu(self, name, action):
        pass

    def addDockWidget(self, area, dock):
        pass

    def removeDockWidget(self, dock):
        pass

    def messageBar(self):
        return None

    currentLayerChanged = type("Signal", (), {"connect": lambda self, f: None, "disconnect": lambda self, f: None})()


class TestEdgeOffsetTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance()
        if cls.app is None:
            cls.app = QgsApplication([], False)
            cls.app.initQgis()

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.canvas.resize(800, 600)
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        QgsSettings().clear()

    def tearDown(self):
        self.canvas.deleteLater()
        QgsSettings().clear()

    def test_geometry_engine_polygon_extend(self):
        # Square: (0,0) -> (10,0) -> (10,10) -> (0,10) -> (0,0)
        poly = QgsPolygon()
        ext = QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(0, 10), QgsPoint(0, 0)])
        poly.setExteriorRing(ext)
        geom = QgsGeometry(poly)

        # Shift right edge (segment 1: (10,0) -> (10,10)) outward to X=12
        # Normal of (10,0)->(10,10) is (-1, 0). Outward distance = -2.0
        res = GeometryEngine.offset_segment(geom, 0, 0, 1, -2.0, mode="extend")
        self.assertIsNotNone(res)
        pts = res.asPolygon()[0]
        self.assertEqual(len(pts), 5)
        self.assertAlmostEqual(pts[1].x(), 12.0, places=4)
        self.assertAlmostEqual(pts[2].x(), 12.0, places=4)

        # Shift closing edge (segment 3: (0,10) -> (0,0)) outward to X=-3
        # Normal of (0,10)->(0,0) is (1, 0). Outward distance = -3.0
        res_closing = GeometryEngine.offset_segment(geom, 0, 0, 3, -3.0, mode="extend")
        self.assertIsNotNone(res_closing)
        pts_c = res_closing.asPolygon()[0]
        self.assertAlmostEqual(pts_c[3].x(), -3.0, places=4)
        self.assertAlmostEqual(pts_c[0].x(), -3.0, places=4)
        self.assertAlmostEqual(pts_c[4].x(), -3.0, places=4)

    def test_geometry_engine_prevent_bowtie_self_intersection(self):
        # Polygon with converging adjacent edges that would criss-cross / flip if not prevented
        p_prev = QgsPoint(2, 2)
        v_i = QgsPoint(3, 5)
        v_next = QgsPoint(6, 5.5)
        p_after = QgsPoint(8, 3.5)
        p_bottom1 = QgsPoint(7, 1)
        p_bottom2 = QgsPoint(4, 0.5)

        poly = QgsPolygon()
        ext = QgsLineString([p_prev, v_i, v_next, p_after, p_bottom1, p_bottom2, p_prev])
        poly.setExteriorRing(ext)
        geom = QgsGeometry(poly)

        # Shift segment 1 (v_i -> v_next) outward past the apex
        res = GeometryEngine.offset_segment(geom, 0, 0, 1, 5.0, mode="extend")
        self.assertIsNotNone(res)
        self.assertTrue(res.isGeosValid())
        pts = res.asPolygon()[0]
        # Should collapse the edge to a single sharp corner at the apex (6 points total including closed ring)
        self.assertEqual(len(pts), 6)
        # Check apex coordinate
        self.assertAlmostEqual(pts[1].x(), 3.875, places=3)
        self.assertAlmostEqual(pts[1].y(), 7.625, places=3)

    def test_geometry_engine_polygon_step(self):
        # Square: (0,0) -> (10,0) -> (10,10) -> (0,10) -> (0,0)
        poly = QgsPolygon()
        ext = QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(0, 10), QgsPoint(0, 0)])
        poly.setExteriorRing(ext)
        geom = QgsGeometry(poly)

        res_step = GeometryEngine.offset_segment(geom, 0, 0, 1, -2.0, mode="step")
        self.assertIsNotNone(res_step)
        pts = res_step.asPolygon()[0]
        self.assertEqual(len(pts), 7)  # 5 original vertices + 2 new step vertices

    def test_geometry_engine_polyline(self):
        # Open polyline: (0,0) -> (10,0) -> (10,10) -> (20,10)
        line = QgsGeometry(QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(20, 10)]))

        # Shift first segment (0,0)->(10,0) upward by +2 (extend mode)
        res_l1 = GeometryEngine.offset_segment(line, 0, 0, 0, 2.0, mode="extend")
        self.assertIsNotNone(res_l1)
        pts1 = res_l1.asPolyline()
        self.assertAlmostEqual(pts1[0].y(), 2.0, places=4)
        self.assertAlmostEqual(pts1[1].y(), 2.0, places=4)

        # Shift middle segment (10,0)->(10,10) rightward by -3 (extend mode)
        res_l2 = GeometryEngine.offset_segment(line, 0, 0, 1, -3.0, mode="extend")
        self.assertIsNotNone(res_l2)
        pts2 = res_l2.asPolyline()
        self.assertAlmostEqual(pts2[1].x(), 13.0, places=4)
        self.assertAlmostEqual(pts2[2].x(), 13.0, places=4)

        # Shift middle segment in step mode (jog inserted at both internal joints)
        res_l_step_mid = GeometryEngine.offset_segment(line, 0, 0, 1, -3.0, mode="step")
        self.assertIsNotNone(res_l_step_mid)
        pts_step_mid = res_l_step_mid.asPolyline()
        self.assertEqual(len(pts_step_mid), 6)  # 4 + 2 new vertices

        # Shift first segment in step mode (no perpendicular end cap at outer start V0)
        res_l_step_first = GeometryEngine.offset_segment(line, 0, 0, 0, 2.0, mode="step")
        self.assertIsNotNone(res_l_step_first)
        pts_first = res_l_step_first.asPolyline()
        self.assertEqual(len(pts_first), 5)  # [P1, P2, V1, V2, V3]
        self.assertAlmostEqual(pts_first[0].x(), 0.0)
        self.assertAlmostEqual(pts_first[0].y(), 2.0)

        # Shift last segment in step mode (no perpendicular end cap at outer end V3)
        res_l_step_last = GeometryEngine.offset_segment(line, 0, 0, 2, 2.0, mode="step")
        self.assertIsNotNone(res_l_step_last)
        pts_last = res_l_step_last.asPolyline()
        self.assertEqual(len(pts_last), 5)  # [V0, V1, V2, P1, P2]
        self.assertAlmostEqual(pts_last[4].x(), 20.0)
        self.assertAlmostEqual(pts_last[4].y(), 12.0)

    def test_geometry_engine_polyline_terminal_extend(self):
        # Open polyline: (1, 2) -> (3.5, 4.5) -> (6.5, 3.2) -> (8.0, 0.5)
        v0 = QgsPoint(1.0, 2.0)
        v1 = QgsPoint(3.5, 4.5)
        v2 = QgsPoint(6.5, 3.2)
        v3 = QgsPoint(8.0, 0.5)
        line = QgsGeometry(QgsLineString([v0, v1, v2, v3]))

        # Shift last segment (v2 -> v3) outward with distance=3.0 (extend mode)
        res = GeometryEngine.offset_segment(line, 0, 0, 2, 3.0, mode="extend")
        self.assertIsNotNone(res)
        pts = res.asPolyline()
        self.assertEqual(len(pts), 4)
        self.assertAlmostEqual(pts[0].x(), 1.0)
        self.assertAlmostEqual(pts[0].y(), 2.0)
        self.assertAlmostEqual(pts[1].x(), 3.5)
        self.assertAlmostEqual(pts[1].y(), 4.5)
        # Shifted joint is extended
        self.assertAlmostEqual(pts[2].x(), 11.020, places=3)
        self.assertAlmostEqual(pts[2].y(), 1.241, places=3)
        # Terminal end maintains segment length and direction
        self.assertAlmostEqual(pts[3].x(), 12.520, places=3)
        self.assertAlmostEqual(pts[3].y(), -1.459, places=3)

    def test_canvas_widget_and_shift_inversion(self):
        widget = EdgeOffsetCanvasWidget(self.canvas)
        widget.show()

        self.assertEqual(widget.mode, EdgeOffsetCanvasWidget.MODE_EXTEND)
        self.assertEqual(widget.get_effective_mode(shift_pressed=False), EdgeOffsetCanvasWidget.MODE_EXTEND)

        # Holding Shift inverts to STEP
        self.assertEqual(widget.get_effective_mode(shift_pressed=True), EdgeOffsetCanvasWidget.MODE_STEP)
        self.assertEqual(widget.mode, EdgeOffsetCanvasWidget.MODE_STEP)

        # Releasing Shift restores EXTEND
        self.assertEqual(widget.get_effective_mode(shift_pressed=False), EdgeOffsetCanvasWidget.MODE_EXTEND)
        self.assertEqual(widget.mode, EdgeOffsetCanvasWidget.MODE_EXTEND)

        # Switch base mode to STEP
        widget.mode = EdgeOffsetCanvasWidget.MODE_STEP
        self.assertEqual(widget.get_effective_mode(shift_pressed=False), EdgeOffsetCanvasWidget.MODE_STEP)
        self.assertEqual(widget.get_effective_mode(shift_pressed=True), EdgeOffsetCanvasWidget.MODE_EXTEND)

        # Test step label
        self.assertFalse(widget.lbl_step.isHidden())
        self.assertIn("1", widget.lbl_step.text())
        widget.set_step(EdgeOffsetCanvasWidget.STEP_ADJUST_OFFSET)
        self.assertIn("2", widget.lbl_step.text())
        self.assertFalse(widget.lbl_step.isHidden())

        # Test CRS adaptation
        widget.adapt_to_crs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.assertEqual(widget.spin_distance.decimals(), 6)
        widget.adapt_to_crs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.assertEqual(widget.spin_distance.decimals(), 3)

        widget.deleteLater()

    def test_map_tool_lifecycle_and_plugin_integration(self):
        iface = DummyInterface(self.canvas)
        plugin = FilletPlugin(iface)
        plugin.initGui()

        self.assertIsNotNone(plugin.edge_offset_action)
        self.assertIsNotNone(plugin.edge_offset_map_tool)
        self.assertIsNotNone(plugin.edge_offset_widget)

        # Create editable vector layer
        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "test_layer", "memory")
        self.assertTrue(layer.isValid())
        feat = QgsFeature()
        poly = QgsPolygon()
        ext = QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(0, 10), QgsPoint(0, 0)])
        poly.setExteriorRing(ext)
        feat.setGeometry(QgsGeometry(poly))
        layer.dataProvider().addFeatures([feat])
        layer.startEditing()

        self.canvas.setCurrentLayer(layer)
        plugin.update_action_state()
        self.assertTrue(plugin.edge_offset_action.isEnabled())

        # Activate tool
        plugin.toggle_edge_offset_tool(True)
        self.assertEqual(self.canvas.mapTool(), plugin.edge_offset_map_tool)
        self.assertTrue(plugin.edge_offset_action.isChecked())

        # Deactivate
        plugin.toggle_edge_offset_tool(False)
        self.assertFalse(plugin.edge_offset_action.isChecked())

        # Unload plugin cleanly
        plugin.unload()
        self.assertIsNone(plugin.edge_offset_action)
        self.assertIsNone(plugin.edge_offset_map_tool)
        self.assertIsNone(plugin.edge_offset_widget)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Tests for Quick Clean Duplicate Nodes tool (CleanDuplicateNodesMapTool, CleanDuplicateNodesCanvasWidget, and GeometryEngine methods).
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
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsPolygon,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas

app = QgsApplication([], False)
app.initQgis()

from core.geometry_engine import GeometryEngine
from gui.clean_duplicate_nodes_canvas_widget import CleanDuplicateNodesCanvasWidget
from gui.clean_duplicate_nodes_map_tool import CleanDuplicateNodesMapTool


class TestCleanDuplicateNodesTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canvas = QgsMapCanvas()
        cls.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

    @classmethod
    def tearDownClass(cls):
        cls.canvas = None

    def test_find_duplicate_nodes_polygon(self):
        # Square with duplicate vertex at (10, 10)
        poly = QgsPolygon()
        ring = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(10, 0),
            QgsPoint(10, 10),
            QgsPoint(10, 10),  # Duplicate
            QgsPoint(0, 10),
            QgsPoint(0, 0),
        ])
        poly.setExteriorRing(ring)
        geom = QgsGeometry(poly)

        dups = GeometryEngine.find_duplicate_nodes(geom, tolerance=1e-6)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["v1_idx"], 2)
        self.assertEqual(dups[0]["v2_idx"], 3)
        self.assertAlmostEqual(dups[0]["point"].x(), 10.0)
        self.assertAlmostEqual(dups[0]["point"].y(), 10.0)

    def test_find_duplicate_nodes_polyline(self):
        # Line with duplicate vertex at (5, 5)
        line = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(5, 5),
            QgsPoint(5, 5),  # Duplicate
            QgsPoint(10, 10),
        ])
        geom = QgsGeometry(line)

        dups = GeometryEngine.find_duplicate_nodes(geom, tolerance=1e-6)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["v1_idx"], 1)
        self.assertEqual(dups[0]["v2_idx"], 2)

    def test_remove_duplicate_node_at_index(self):
        poly = QgsPolygon()
        ring = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(10, 0),
            QgsPoint(10, 10),
            QgsPoint(10, 10),  # Duplicate at idx 3
            QgsPoint(0, 10),
            QgsPoint(0, 0),
        ])
        poly.setExteriorRing(ring)
        geom = QgsGeometry(poly)

        res = GeometryEngine.remove_duplicate_node_at_index(geom, 0, 0, 3)
        self.assertIsNotNone(res)
        pts = res.asPolygon()[0]
        self.assertEqual(len(pts), 5)
        self.assertTrue(res.isGeosValid())

    def test_remove_all_duplicate_nodes(self):
        poly = QgsPolygon()
        ring = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(0, 0),    # Duplicate 1
            QgsPoint(10, 0),
            QgsPoint(10, 10),
            QgsPoint(10, 10),  # Duplicate 2
            QgsPoint(0, 10),
            QgsPoint(0, 0),
        ])
        poly.setExteriorRing(ring)
        geom = QgsGeometry(poly)

        cleaned, count = GeometryEngine.remove_all_duplicate_nodes(geom, tolerance=1e-6)
        self.assertEqual(count, 2)
        pts = cleaned.asPolygon()[0]
        self.assertEqual(len(pts), 5)
        self.assertTrue(cleaned.isGeosValid())

    def test_canvas_widget_and_tool_lifecycle(self):
        widget = CleanDuplicateNodesCanvasWidget(self.canvas)
        widget.show()
        self.assertEqual(widget.tolerance, 0.0001)

        widget.set_tolerance(0.005)
        self.assertAlmostEqual(widget.tolerance, 0.005)

        widget.set_step(CleanDuplicateNodesCanvasWidget.STEP_CONTEXT_MENU)
        self.assertEqual(widget._current_step, CleanDuplicateNodesCanvasWidget.STEP_CONTEXT_MENU)

        tool = CleanDuplicateNodesMapTool(self.canvas, widget)
        tool.activate()
        self.assertIsNotNone(tool.hover_rubberband)
        self.assertIsNotNone(tool.dup_markers_rubberband)
        self.assertIsNotNone(tool.active_node_marker)
        self.assertIsNotNone(tool.preview_rubberband)

        tool.deactivate()
        tool.cleanup()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCleanDuplicateNodesTool)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if res.wasSuccessful() else 1)

# -*- coding: utf-8 -*-
"""
Tests for Quick Clean Duplicate Nodes & Self-Intersections tool (CleanDuplicateNodesMapTool and GeometryEngine methods).
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
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsPolygon,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QVariant

app = QgsApplication([], False)
app.initQgis()

from core.geometry_engine import GeometryEngine
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

    def test_find_self_intersections_bowtie(self):
        # Bowtie polygon crossing at (5, 5)
        poly = QgsPolygon()
        ring = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(10, 0),
            QgsPoint(0, 10),
            QgsPoint(10, 10),
            QgsPoint(0, 0),
        ])
        poly.setExteriorRing(ring)
        geom = QgsGeometry(poly)

        intersections = GeometryEngine.find_self_intersections(geom)
        self.assertEqual(len(intersections), 1)
        self.assertAlmostEqual(intersections[0]["point"].x(), 5.0)
        self.assertAlmostEqual(intersections[0]["point"].y(), 5.0)

    def test_untangle_self_intersection(self):
        poly = QgsPolygon()
        ring = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(10, 0),
            QgsPoint(0, 10),
            QgsPoint(10, 10),
            QgsPoint(0, 0),
        ])
        poly.setExteriorRing(ring)
        geom = QgsGeometry(poly)

        inter = QgsPoint(5, 5)
        untangled = GeometryEngine.untangle_self_intersection(geom, 0, 0, 1, 3, inter, keep_loop=1)
        self.assertIsNotNone(untangled)
        self.assertTrue(untangled.isGeosValid())

    def test_clean_all_topology_errors(self):
        poly = QgsPolygon()
        ring = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(10, 0),
            QgsPoint(10, 0),  # Duplicate
            QgsPoint(0, 10),
            QgsPoint(10, 10),
            QgsPoint(0, 0),
        ])
        poly.setExteriorRing(ring)
        geom = QgsGeometry(poly)

        cleaned, total = GeometryEngine.clean_all_topology_errors(geom, tolerance=1e-6)
        self.assertGreater(total, 0)
        self.assertTrue(cleaned.isGeosValid())

    def test_singlepart_and_multipart_coercion(self):
        # Singlepart layer
        single_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "single_poly", "memory")
        # Multipart layer
        multi_layer = QgsVectorLayer("MultiPolygon?crs=EPSG:3857", "multi_poly", "memory")

        poly = QgsPolygon()
        ring = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(10, 0),
            QgsPoint(0, 10),
            QgsPoint(10, 10),
            QgsPoint(0, 0),
        ])
        poly.setExteriorRing(ring)
        geom = QgsGeometry(poly)
        valid_multi = geom.makeValid()

        self.assertTrue(valid_multi.isMultipart())

        # Test extract_singlepart_geometries
        parts = GeometryEngine.extract_singlepart_geometries(valid_multi, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.assertEqual(len(parts), 2)

        # Test get_largest_singlepart_geometry
        largest = GeometryEngine.get_largest_singlepart_geometry(valid_multi, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.assertFalse(largest.isMultipart())

        # Coerce to singlepart layer
        single_res = GeometryEngine.coerce_geometry_to_layer(valid_multi, single_layer)
        self.assertFalse(single_res.isMultipart())

        # Coerce to multipart layer
        multi_res = GeometryEngine.coerce_geometry_to_layer(largest, multi_layer)
        self.assertTrue(multi_res.isMultipart())

    def test_merge_duplicate_cluster_multiple_vertices(self):
        # 3 identical duplicate vertices at (10, 10)
        poly = QgsPolygon()
        ring = QgsLineString([
            QgsPoint(0, 0),
            QgsPoint(10, 0),
            QgsPoint(10, 10),
            QgsPoint(10, 10),
            QgsPoint(10, 10),
            QgsPoint(0, 10),
            QgsPoint(0, 0),
        ])
        poly.setExteriorRing(ring)
        geom = QgsGeometry(poly)

        merged = GeometryEngine.merge_duplicate_nodes_at_point(geom, QgsPoint(10, 10), tolerance=1e-5)
        dups = GeometryEngine.find_duplicate_nodes(merged, tolerance=1e-5)
        self.assertEqual(len(dups), 0)
        self.assertEqual(len(merged.asPolygon()[0]), 5)

    def test_map_tool_lifecycle(self):
        tool = CleanDuplicateNodesMapTool(self.canvas)
        tool.activate()
        self.assertIsNotNone(tool.hover_rubberband)
        self.assertIsNotNone(tool.dup_markers_rubberband)
        self.assertIsNotNone(tool.inter_markers_rubberband)
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

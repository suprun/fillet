# -*- coding: utf-8 -*-
"""
Unit tests for GeometryEngine in Fillet / Chamfer plugin.
Compatible with QGIS 3.x and QGIS 4.x test runners.
"""

import math
import sys
import unittest

from qgis.core import (
    QgsApplication,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsPolygon,
)

from core.geometry_engine import GeometryEngine


class TestGeometryEngine(unittest.TestCase):
    """Test suite for fillet and chamfer geometric operations."""

    def test_compute_fillet_points_right_angle(self):
        """Test fillet calculation on a 90-degree right angle."""
        p_prev = QgsPoint(0, 10)
        v = QgsPoint(0, 0)
        p_next = QgsPoint(10, 0)
        radius = 2.0

        success, t1, arc_mid, t2, tangent_dist = GeometryEngine.compute_fillet_points(p_prev, v, p_next, radius)
        self.assertTrue(success)
        self.assertIsNotNone(t1)
        self.assertIsNotNone(arc_mid)
        self.assertIsNotNone(t2)

        # For 90 degree angle, half angle is 45, tan(45) = 1, so tangent_dist = radius
        self.assertAlmostEqual(tangent_dist, 2.0, places=5)
        self.assertAlmostEqual(t1.x(), 0.0, places=5)
        self.assertAlmostEqual(t1.y(), 2.0, places=5)
        self.assertAlmostEqual(t2.x(), 2.0, places=5)
        self.assertAlmostEqual(t2.y(), 0.0, places=5)

        # Bisector is (1/sqrt(2), 1/sqrt(2)), center is at (2, 2)
        # Midpoint of arc is at (2 - 2/sqrt(2), 2 - 2/sqrt(2)) = (2 - sqrt(2), 2 - sqrt(2)) ~ (0.585786, 0.585786)
        expected_mid = 2.0 - math.sqrt(2)
        self.assertAlmostEqual(arc_mid.x(), expected_mid, places=4)
        self.assertAlmostEqual(arc_mid.y(), expected_mid, places=4)

    def test_compute_chamfer_points(self):
        """Test chamfer calculation."""
        p_prev = QgsPoint(0, 10)
        v = QgsPoint(0, 0)
        p_next = QgsPoint(10, 0)

        success, c1, c2 = GeometryEngine.compute_chamfer_points(p_prev, v, p_next, 3.0, 4.0)
        self.assertTrue(success)
        self.assertAlmostEqual(c1.x(), 0.0, places=5)
        self.assertAlmostEqual(c1.y(), 3.0, places=5)
        self.assertAlmostEqual(c2.x(), 4.0, places=5)
        self.assertAlmostEqual(c2.y(), 0.0, places=5)

    def test_max_fillet_radius(self):
        """Test calculation of maximum allowed fillet radius."""
        p_prev = QgsPoint(0, 5)
        v = QgsPoint(0, 0)
        p_next = QgsPoint(10, 0)

        # For 90-degree corner, tan(45) = 1, max radius is min(5, 10) * 1 = 5.0
        max_r = GeometryEngine.max_fillet_radius(p_prev, v, p_next)
        self.assertAlmostEqual(max_r, 5.0, places=5)

    def test_apply_fillet_to_linestring(self):
        """Test applying fillet to a vertex in a LineString."""
        # L-shape line: (0, 10) -> (0, 0) -> (10, 0)
        geom = QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(0, 0), QgsPointXY(10, 0)])
        new_geom = GeometryEngine.apply_fillet_to_geometry(
            geom, part_idx=0, ring_idx=0, vertex_idx=1, radius=2.0, segments_count=8
        )
        self.assertIsNotNone(new_geom)
        self.assertTrue(new_geom.isGeosValid())
        # The new geometry should have more points than the original 3
        ls = new_geom.asPolyline()
        self.assertGreater(len(ls), 3)
        # Start point and end point should be preserved
        self.assertAlmostEqual(ls[0].x(), 0.0, places=5)
        self.assertAlmostEqual(ls[0].y(), 10.0, places=5)
        self.assertAlmostEqual(ls[-1].x(), 10.0, places=5)
        self.assertAlmostEqual(ls[-1].y(), 0.0, places=5)

    def test_apply_fillet_to_polygon(self):
        """Test applying fillet to a polygon corner."""
        # Square: (0,0) -> (0,10) -> (10,10) -> (10,0) -> (0,0)
        geom = QgsGeometry.fromPolygonXY(
            [[QgsPointXY(0, 0), QgsPointXY(0, 10), QgsPointXY(10, 10), QgsPointXY(10, 0), QgsPointXY(0, 0)]]
        )

        # Fillet corner (0, 10) which is vertex index 1
        new_geom = GeometryEngine.apply_fillet_to_geometry(
            geom, part_idx=0, ring_idx=0, vertex_idx=1, radius=2.0, segments_count=8
        )
        self.assertIsNotNone(new_geom)
        self.assertTrue(new_geom.isGeosValid())

        # Fillet closure vertex (0, 0) which is vertex index 0
        new_geom_closure = GeometryEngine.apply_fillet_to_geometry(
            geom, part_idx=0, ring_idx=0, vertex_idx=0, radius=2.0, segments_count=8
        )
        self.assertIsNotNone(new_geom_closure)
        self.assertTrue(new_geom_closure.isGeosValid())

    def test_apply_chamfer_to_polygon(self):
        """Test applying chamfer to a polygon corner."""
        geom = QgsGeometry.fromPolygonXY(
            [[QgsPointXY(0, 0), QgsPointXY(0, 10), QgsPointXY(10, 10), QgsPointXY(10, 0), QgsPointXY(0, 0)]]
        )
        new_geom = GeometryEngine.apply_chamfer_to_geometry(
            geom, part_idx=0, ring_idx=0, vertex_idx=2, dist1=2.0, dist2=2.0
        )
        self.assertIsNotNone(new_geom)
        self.assertTrue(new_geom.isGeosValid())


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    suite = unittest.TestLoader().loadTestsFromTestCase(TestGeometryEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)

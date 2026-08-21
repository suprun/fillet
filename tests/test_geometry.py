# -*- coding: utf-8 -*-
"""
Unit tests for GeometryEngine in Fillet / Chamfer plugin.
Compatible with QGIS 3.x and QGIS 4.x test runners.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
        # The new geometry with 8 segments replaces 1 vertex with 9 arc points: total = 1 + 9 + 1 = 11 points
        ls = new_geom.asPolyline()
        self.assertEqual(len(ls), 11)
        # Start point and end point should be preserved
        self.assertAlmostEqual(ls[0].x(), 0.0, places=5)
        self.assertAlmostEqual(ls[0].y(), 10.0, places=5)
        self.assertAlmostEqual(ls[-1].x(), 10.0, places=5)
        self.assertAlmostEqual(ls[-1].y(), 0.0, places=5)

        # Test with 4 segments (total 1 + 5 + 1 = 7 points)
        geom4 = GeometryEngine.apply_fillet_to_geometry(
            geom, part_idx=0, ring_idx=0, vertex_idx=1, radius=2.0, segments_count=4
        )
        self.assertEqual(len(geom4.asPolyline()), 7)

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

    def test_isosceles_chamfer_bounded_by_shorter_edge(self):
        """Test that equal-distance chamfer is strictly capped by the shorter edge."""
        # Edge 1 is length 3, Edge 2 is length 10
        p_prev = QgsPoint(0, 3)
        v = QgsPoint(0, 0)
        p_next = QgsPoint(10, 0)

        # Requesting dist1 = dist2 = 8.0, should be capped at min(3, 10) * 0.9999 ~ 2.9997
        success, c1, c2 = GeometryEngine.compute_chamfer_points(p_prev, v, p_next, 8.0, 8.0)
        self.assertTrue(success)
        self.assertAlmostEqual(c1.y(), 3.0 * 0.9999, places=3)
        self.assertAlmostEqual(c2.x(), 3.0 * 0.9999, places=3)
        # Both distances must remain equal (isosceles)
        self.assertAlmostEqual(c1.y(), c2.x(), places=4)

    def test_batch_process_polygon(self):
        """Test batch applying fillet and chamfer to all vertices of a polygon."""
        # Square: (0,0) -> (0,10) -> (10,10) -> (10,0) -> (0,0)
        geom = QgsGeometry.fromPolygonXY(
            [[QgsPointXY(0, 0), QgsPointXY(0, 10), QgsPointXY(10, 10), QgsPointXY(10, 0), QgsPointXY(0, 0)]]
        )
        # Batch fillet
        fillet_geom = GeometryEngine.batch_process_geometry(geom, mode="fillet", radius=2.0, segments_count=8)
        self.assertIsNotNone(fillet_geom)
        self.assertTrue(fillet_geom.isGeosValid())
        # Polygon should now have significantly more vertices due to 4 filleted corners
        ext_ring = fillet_geom.constGet().exteriorRing()
        self.assertGreater(ext_ring.numPoints(), 10)

        # Batch chamfer
        chamfer_geom = GeometryEngine.batch_process_geometry(geom, mode="chamfer", dist1=2.0, dist2=2.0)
        self.assertIsNotNone(chamfer_geom)
        self.assertTrue(chamfer_geom.isGeosValid())
        # Square (4 corners) -> 8 corners + 1 closure = 9 points
        chamfer_ring = chamfer_geom.constGet().exteriorRing()
        self.assertEqual(chamfer_ring.numPoints(), 9)

    def test_batch_process_linestring(self):
        """Test batch applying fillet to all internal vertices of a linestring."""
        # Zig-zag line: (0,0) -> (5,10) -> (10,0) -> (15,10)
        geom = QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(5, 10), QgsPointXY(10, 0), QgsPointXY(15, 10)]
        )
        fillet_geom = GeometryEngine.batch_process_geometry(geom, mode="fillet", radius=1.0, segments_count=4)
        self.assertIsNotNone(fillet_geom)
    def test_compute_line_intersection(self):
        """Test analytical infinite line intersection."""
        p1 = QgsPoint(0, 10)
        p2 = QgsPoint(0, 2)
        p3 = QgsPoint(10, 0)
        p4 = QgsPoint(2, 0)
        pt = GeometryEngine.compute_line_intersection(p1, p2, p3, p4)
        self.assertIsNotNone(pt)
        self.assertAlmostEqual(pt.x(), 0.0, places=6)
        self.assertAlmostEqual(pt.y(), 0.0, places=6)

        # Parallel lines
        p_par1 = QgsPoint(0, 0)
        p_par2 = QgsPoint(0, 5)
        p_par3 = QgsPoint(2, 0)
        p_par4 = QgsPoint(2, 5)
        self.assertIsNone(GeometryEngine.compute_line_intersection(p_par1, p_par2, p_par3, p_par4))

    def test_restore_sharp_corner_linestring_roundtrip(self):
        """Test round-trip: L-shape line -> fillet/chamfer -> restore sharp corner."""
        orig_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(0, 0), QgsPointXY(10, 0)])

        # 1. Fillet round-trip
        fillet_geom = GeometryEngine.apply_fillet_to_geometry(
            orig_geom, part_idx=0, ring_idx=0, vertex_idx=1, radius=2.5, segments_count=8
        )
        self.assertEqual(len(fillet_geom.asPolyline()), 11)

        # Restore from any vertex of the arc (e.g. vertex 4)
        restored_geom = GeometryEngine.restore_sharp_corner_at_vertex(
            fillet_geom, part_idx=0, ring_idx=0, vertex_idx=4
        )
        self.assertIsNotNone(restored_geom)
        res_pts = restored_geom.asPolyline()
        self.assertEqual(len(res_pts), 3)
        self.assertAlmostEqual(res_pts[0].x(), 0.0, places=5)
        self.assertAlmostEqual(res_pts[0].y(), 10.0, places=5)
        self.assertAlmostEqual(res_pts[1].x(), 0.0, places=5)
        self.assertAlmostEqual(res_pts[1].y(), 0.0, places=5)
        self.assertAlmostEqual(res_pts[2].x(), 10.0, places=5)
        self.assertAlmostEqual(res_pts[2].y(), 0.0, places=5)

        # 2. Chamfer round-trip
        chamfer_geom = GeometryEngine.apply_chamfer_to_geometry(
            orig_geom, part_idx=0, ring_idx=0, vertex_idx=1, dist1=3.0, dist2=4.0
        )
        self.assertEqual(len(chamfer_geom.asPolyline()), 4)

        restored_ch = GeometryEngine.restore_sharp_corner_at_vertex(
            chamfer_geom, part_idx=0, ring_idx=0, vertex_idx=1
        )
        self.assertIsNotNone(restored_ch)
        res_ch_pts = restored_ch.asPolyline()
        self.assertEqual(len(res_ch_pts), 3)
        self.assertAlmostEqual(res_ch_pts[1].x(), 0.0, places=5)
        self.assertAlmostEqual(res_ch_pts[1].y(), 0.0, places=5)

    def test_restore_sharp_corner_polygon_roundtrip(self):
        """Test round-trip on a polygon corner and closure vertex."""
        poly_geom = QgsGeometry.fromPolygonXY(
            [[QgsPointXY(0, 0), QgsPointXY(0, 10), QgsPointXY(10, 10), QgsPointXY(10, 0), QgsPointXY(0, 0)]]
        )

        # Fillet corner 1 (0, 10)
        fpoly = GeometryEngine.apply_fillet_to_geometry(
            poly_geom, part_idx=0, ring_idx=0, vertex_idx=1, radius=2.0, segments_count=6
        )
        restored_poly = GeometryEngine.restore_sharp_corner_at_vertex(
            fpoly, part_idx=0, ring_idx=0, vertex_idx=3
        )
        self.assertIsNotNone(restored_poly)
        ring_pts = restored_poly.asPolygon()[0]
        self.assertEqual(len(ring_pts), 5)
        self.assertAlmostEqual(ring_pts[1].x(), 0.0, places=5)
        self.assertAlmostEqual(ring_pts[1].y(), 10.0, places=5)

        # Fillet closure corner 0 (0, 0)
        fpoly_close = GeometryEngine.apply_fillet_to_geometry(
            poly_geom, part_idx=0, ring_idx=0, vertex_idx=0, radius=2.0, segments_count=6
        )
        restored_close = GeometryEngine.restore_sharp_corner_at_vertex(
            fpoly_close, part_idx=0, ring_idx=0, vertex_idx=0
        )
        self.assertIsNotNone(restored_close)
        close_pts = restored_close.asPolygon()[0]
        self.assertEqual(len(close_pts), 5)
        self.assertAlmostEqual(close_pts[0].x(), 0.0, places=5)
        self.assertAlmostEqual(close_pts[0].y(), 0.0, places=5)

    def test_batch_restore_polygon_corners(self):
        """Test batch restoring all filleted corners of a polygon to sharp corners."""
        orig_poly = QgsGeometry.fromPolygonXY(
            [[QgsPointXY(0, 0), QgsPointXY(0, 20), QgsPointXY(20, 20), QgsPointXY(20, 0), QgsPointXY(0, 0)]]
        )
        # 1. Batch fillet all 4 corners
        filleted = GeometryEngine.batch_apply_geometry(orig_poly, mode="fillet", radius=3.0, segments_count=6)
        self.assertTrue(filleted.isGeosValid())
        self.assertGreater(filleted.constGet().exteriorRing().numPoints(), 15)

        # 2. Batch restore all corners
        restored = GeometryEngine.batch_apply_geometry(filleted, mode="restore")
        self.assertTrue(restored.isGeosValid())
        ext_ring = restored.constGet().exteriorRing()
        self.assertEqual(ext_ring.numPoints(), 5)

    def test_two_edge_restore_linestring(self):
        """Test CAD Two-Edge corner restoration on LineString with multi-segment fillet."""
        orig_line = QgsGeometry.fromPolylineXY([QgsPointXY(0, 20), QgsPointXY(0, 0), QgsPointXY(20, 0)])
        f_line = GeometryEngine.apply_fillet_to_geometry(orig_line, 0, 0, 1, radius=5.0, segments_count=8)
        self.assertEqual(len(f_line.asPolyline()), 11)

        # Segment 1 is 0->1, Segment 2 is 9->10 (last segment)
        last_seg_idx = len(f_line.asPolyline()) - 2
        res = GeometryEngine.restore_sharp_corner_between_segments(f_line, 0, 0, 0, last_seg_idx)
        self.assertIsNotNone(res)
        new_geom, v_sharp = res
        pts = new_geom.asPolyline()
        self.assertEqual(len(pts), 3)
        self.assertAlmostEqual(v_sharp.x(), 0.0, places=5)
        self.assertAlmostEqual(v_sharp.y(), 0.0, places=5)
        self.assertAlmostEqual(pts[1].x(), 0.0, places=5)
        self.assertAlmostEqual(pts[1].y(), 0.0, places=5)

    def test_two_edge_restore_polygon_and_closure(self):
        """Test CAD Two-Edge corner restoration on Polygon across regular edges and closure vertex."""
        orig_poly = QgsGeometry.fromPolygonXY(
            [[QgsPointXY(0, 0), QgsPointXY(0, 20), QgsPointXY(20, 20), QgsPointXY(20, 0), QgsPointXY(0, 0)]]
        )
        filleted = GeometryEngine.batch_apply_geometry(orig_poly, mode="fillet", radius=3.0, segments_count=6)
        
        # 1. Restore corner (0, 20)
        res_corner = GeometryEngine.restore_sharp_corner_between_segments(filleted, 0, 0, 0, 7)
        self.assertIsNotNone(res_corner)
        geom_c, v_c = res_corner
        self.assertAlmostEqual(v_c.x(), 0.0, places=5)
        self.assertAlmostEqual(v_c.y(), 20.0, places=5)

        # 2. Restore wrap-around closure corner (0, 0)
        f_pts_count = len(filleted.asPolygon()[0])
        res_wrap = GeometryEngine.restore_sharp_corner_between_segments(filleted, 0, 0, f_pts_count - 8, 0)
        self.assertIsNotNone(res_wrap)
        geom_w, v_w = res_wrap
        self.assertAlmostEqual(v_w.x(), 0.0, places=5)
        self.assertAlmostEqual(v_w.y(), 0.0, places=5)


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    suite = unittest.TestLoader().loadTestsFromTestCase(TestGeometryEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)

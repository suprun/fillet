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
    QgsWkbTypes,
)

from core.geometry_engine import GeometryEngine


class TestGeometryEngine(unittest.TestCase):
    """Test suite for fillet and chamfer geometric operations."""

    def assert_finite_dimensions(self, geometry):
        points = list(geometry.vertices())
        self.assertTrue(points)
        for point in points:
            self.assertTrue(point.is3D())
            self.assertTrue(point.isMeasure())
            self.assertTrue(math.isfinite(point.z()))
            self.assertTrue(math.isfinite(point.m()))

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

    def test_zero_size_keeps_one_sharp_vertex(self):
        """Zero fillet/chamfer sizes keep the source corner exactly once."""
        source = QgsGeometry(
            QgsLineString(
                [
                    QgsPoint(0, 10, 10, 100),
                    QgsPoint(0, 0, 20, 200),
                    QgsPoint(10, 0, 30, 300),
                ]
            )
        )

        success, t1, arc_mid, t2, tangent_dist = (
            GeometryEngine.compute_fillet_points(
                QgsPoint(0, 10, 10, 100),
                QgsPoint(0, 0, 20, 200),
                QgsPoint(10, 0, 30, 300),
                0.0,
            )
        )
        self.assertTrue(success)
        self.assertEqual(tangent_dist, 0.0)
        for point in (t1, arc_mid, t2):
            self.assertEqual((point.x(), point.y()), (0.0, 0.0))
            self.assertEqual((point.z(), point.m()), (20.0, 200.0))

        fillet = GeometryEngine.apply_fillet_to_geometry(
            source, 0, 0, 1, radius=0.0, segments_count=8
        )
        chamfer = GeometryEngine.apply_chamfer_to_geometry(
            source, 0, 0, 1, dist1=0.0, dist2=0.0
        )
        self.assertEqual(fillet.asWkb(), source.asWkb())
        self.assertEqual(chamfer.asWkb(), source.asWkb())
        self.assertEqual(fillet.constGet().numPoints(), 3)
        self.assertEqual(chamfer.constGet().numPoints(), 3)
        self.assert_finite_dimensions(fillet)
        self.assert_finite_dimensions(chamfer)

    def test_one_sided_zero_chamfer_is_literal(self):
        """An unlinked zero distance creates a one-sided chamfer."""
        source = QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 10), QgsPointXY(0, 0), QgsPointXY(10, 0)]
        )
        result = GeometryEngine.apply_chamfer_to_geometry(
            source, 0, 0, 1, dist1=0.0, dist2=2.0
        )

        self.assertIsNotNone(result)
        points = result.asPolyline()
        self.assertEqual(len(points), 4)
        self.assertEqual((points[1].x(), points[1].y()), (0.0, 0.0))
        self.assertEqual((points[2].x(), points[2].y()), (2.0, 0.0))

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

    def test_batch_zero_size_returns_unchanged_geometry(self):
        """Batch zero is an idempotent sharp-corner operation."""
        source = QgsGeometry.fromPolygonXY(
            [[
                QgsPointXY(0, 0),
                QgsPointXY(0, 10),
                QgsPointXY(10, 10),
                QgsPointXY(10, 0),
                QgsPointXY(0, 0),
            ]]
        )

        fillet = GeometryEngine.batch_apply_geometry(
            source, mode="fillet", radius=0.0
        )
        chamfer = GeometryEngine.batch_apply_geometry(
            source, mode="chamfer", dist1=0.0, dist2=0.0
        )
        self.assertEqual(fillet.asWkb(), source.asWkb())
        self.assertEqual(chamfer.asWkb(), source.asWkb())
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

    def test_zm_is_preserved_by_topology_rebuild_operations(self):
        points = [
            QgsPoint(0, 10, 10, 100),
            QgsPoint(0, 0, 20, 200),
            QgsPoint(10, 0, 30, 300),
        ]
        source = QgsGeometry(QgsLineString(points))

        fillet = GeometryEngine.apply_fillet_to_geometry(
            source,
            0,
            0,
            1,
            radius=2.0,
            segments_count=8,
        )
        chamfer = GeometryEngine.apply_chamfer_to_geometry(
            source,
            0,
            0,
            1,
            dist1=2.0,
            dist2=2.0,
        )
        batch = GeometryEngine.batch_apply_geometry(
            source,
            mode="fillet",
            radius=2.0,
            segments_count=8,
        )
        offset = GeometryEngine.offset_segment(source, 0, 0, 0, 1.0)
        orthogonalized = GeometryEngine.orthogonalize_geometry(
            source,
            base_angle_rad=0.0,
            tolerance_deg=45.0,
        )

        for result in (fillet, chamfer, batch, offset, orthogonalized):
            self.assertIsNotNone(result)
            self.assert_finite_dimensions(result)

        restored = GeometryEngine.restore_sharp_corner_between_segments(
            fillet,
            0,
            0,
            0,
            fillet.constGet().numPoints() - 2,
        )
        self.assertIsNotNone(restored)
        restored_geometry, intersection = restored
        self.assertTrue(intersection.is3D())
        self.assertTrue(intersection.isMeasure())
        self.assert_finite_dimensions(restored_geometry)

        duplicate_source = QgsGeometry(
            QgsLineString(
                [
                    QgsPoint(0, 0, 1, 10),
                    QgsPoint(5, 0, 2, 20),
                    QgsPoint(5, 0, 2, 20),
                    QgsPoint(10, 0, 3, 30),
                ]
            )
        )
        cleaned, cleaned_count = GeometryEngine.clean_all_topology_errors(
            duplicate_source,
            tolerance=1e-8,
        )
        self.assertGreater(cleaned_count, 0)
        self.assert_finite_dimensions(cleaned)

    def test_curves_are_preserved_or_rejected_by_policy(self):
        curved = QgsGeometry.fromWkt(
            "COMPOUNDCURVE (CIRCULARSTRING (0 0, 5 5, 10 0), "
            "(10 0, 20 0))"
        )
        curve_polygon = QgsGeometry.fromWkt(
            "CURVEPOLYGON (CIRCULARSTRING "
            "(0 0, 5 5, 10 0, 5 -5, 0 0))"
        )
        self.assertTrue(GeometryEngine.has_curved_segments(curved))
        self.assertTrue(GeometryEngine.has_curved_segments(curve_polygon))

        allowed = [
            GeometryEngine.rotate_geometry(curved, QgsPointXY(0, 0), 30.0),
            GeometryEngine.mirror_geometry(
                curved,
                QgsPointXY(0, -1),
                QgsPointXY(0, 1),
            ),
            GeometryEngine.scale_and_rotate_geometry(
                curved,
                QgsPointXY(0, 0),
                2.0,
                15.0,
            ),
        ]
        allowed.extend(
            GeometryEngine.create_polar_array_geometries(
                curved,
                QgsPointXY(0, 0),
                count=3,
                fill_angle_deg=360.0,
            )
        )
        allowed.extend(
            GeometryEngine.divide_line_geometries(curved, count=2)
        )
        self.assertTrue(allowed)
        self.assertTrue(
            all(GeometryEngine.has_curved_segments(result) for result in allowed)
        )
        for source in (curve_polygon,):
            transformed = [
                GeometryEngine.rotate_geometry(source, QgsPointXY(0, 0), 30.0),
                GeometryEngine.mirror_geometry(
                    source,
                    QgsPointXY(0, -1),
                    QgsPointXY(0, 1),
                ),
                GeometryEngine.scale_and_rotate_geometry(
                    source,
                    QgsPointXY(0, 0),
                    2.0,
                    15.0,
                ),
            ]
            transformed.extend(
                GeometryEngine.create_polar_array_geometries(
                    source,
                    QgsPointXY(0, 0),
                    count=3,
                    fill_angle_deg=360.0,
                )
            )
            self.assertTrue(
                all(
                    GeometryEngine.has_curved_segments(result)
                    for result in transformed
                )
            )

        self.assertIsNone(
            GeometryEngine.apply_fillet_to_geometry(
                curved,
                0,
                0,
                1,
                radius=1.0,
            )
        )
        self.assertIsNone(
            GeometryEngine.apply_chamfer_to_geometry(
                curved,
                0,
                0,
                1,
                dist1=1.0,
                dist2=1.0,
            )
        )
        self.assertIsNone(
            GeometryEngine.batch_apply_geometry(curved, mode="fillet", radius=1.0)
        )
        self.assertIsNone(GeometryEngine.offset_segment(curved, 0, 0, 0, 1.0))
        self.assertEqual(
            GeometryEngine.orthogonalize_geometry(curved, 0.0).asWkt(),
            curved.asWkt(),
        )
        cleaned, count = GeometryEngine.clean_all_topology_errors(curved)
        self.assertEqual(count, 0)
        self.assertEqual(cleaned.asWkt(), curved.asWkt())
        self.assertFalse(GeometryEngine.can_explode_line(curved))
        self.assertEqual(GeometryEngine.explode_line(curved), [])


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    suite = unittest.TestLoader().loadTestsFromTestCase(TestGeometryEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)

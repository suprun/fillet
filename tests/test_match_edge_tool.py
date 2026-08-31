# -*- coding: utf-8 -*-
"""Tests for Match Edge minimal rotation and group editing."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas

from core.geometry_engine import GeometryEngine
from core.snapping_helper import LayerSegmentMatch, SnappingHelper
from gui.match_edge_canvas_widget import MatchEdgeCanvasWidget
from gui.match_edge_map_tool import MatchEdgeMapTool
from research_tool_test_utils import TestIface, add_geometry_feature

app = QgsApplication([], False)
app.initQgis()


class TestMatchEdgeTool(unittest.TestCase):
    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.layer = QgsVectorLayer("LineString?crs=EPSG:3857&field=code:int", "source", "memory")
        self.fid = add_geometry_feature(self.layer, QgsGeometry.fromWkt("LINESTRING (0 0, 4 0)"), [7])
        self.layer.startEditing()
        self.layer.selectByIds([self.fid])
        self.canvas.setCurrentLayer(self.layer)
        self.widget = MatchEdgeCanvasWidget(self.canvas)
        self.tool = MatchEdgeMapTool(self.canvas, self.widget, TestIface(self.canvas))

    def tearDown(self):
        self.tool.cleanup()
        self.layer.rollBack()

    def test_legacy_rigid_transform_remains_available(self):
        angle, pivot, dx, dy = GeometryEngine.compute_match_edge_transform(
            QgsPointXY(0, 0), QgsPointXY(4, 0), QgsPointXY(10, 3), QgsPointXY(10, 9)
        )
        self.assertAlmostEqual(angle, 90.0)
        self.assertEqual((pivot.x(), pivot.y()), (2.0, 0.0))
        rotated_midpoint = GeometryEngine.apply_similarity_transform(
            QgsGeometry.fromPointXY(pivot), pivot, angle, 1.0, dx, dy
        ).asPoint()
        self.assertAlmostEqual(rotated_midpoint.x(), 10.0)
        self.assertAlmostEqual(rotated_midpoint.y(), 0.0)
        parallel = GeometryEngine.compute_match_edge_transform(
            QgsPointXY(0, 0), QgsPointXY(4, 0), QgsPointXY(10, 3), QgsPointXY(10, 9), collinear=False
        )
        self.assertEqual(parallel[2:], (0.0, 0.0))

    def test_polygon_exterior_and_hole_are_rebuilt_locally(self):
        geometry = QgsGeometry.fromWkt(
            "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), "
            "(3 3, 7 3, 7 7, 3 7, 3 3))"
        )
        exterior = GeometryEngine.match_segment_to_reference(
            geometry,
            0,
            0,
            2,
            QgsPointXY(0, 12),
            QgsPointXY(10, 12),
        )
        exterior_ring = GeometryEngine.get_curve_from_geometry(exterior, 0, 0)
        hole_ring = GeometryEngine.get_curve_from_geometry(exterior, 0, 1)
        self.assertEqual((exterior_ring.pointN(2).x(), exterior_ring.pointN(2).y()), (10.0, 12.0))
        self.assertEqual((exterior_ring.pointN(3).x(), exterior_ring.pointN(3).y()), (0.0, 12.0))
        self.assertEqual((exterior_ring.pointN(0).x(), exterior_ring.pointN(0).y()), (0.0, 0.0))
        self.assertEqual(hole_ring.asWkt(), GeometryEngine.get_curve_from_geometry(geometry, 0, 1).asWkt())

        hole = GeometryEngine.match_segment_to_reference(
            exterior,
            0,
            1,
            2,
            QgsPointXY(0, 6),
            QgsPointXY(10, 6),
        )
        changed_hole = GeometryEngine.get_curve_from_geometry(hole, 0, 1)
        self.assertEqual((changed_hole.pointN(2).x(), changed_hole.pointN(2).y()), (7.0, 6.0))
        self.assertEqual((changed_hole.pointN(3).x(), changed_hole.pointN(3).y()), (3.0, 6.0))
        self.assertTrue(hole.isGeosValid())

    def test_internal_terminal_single_and_flip_line_rules(self):
        internal = GeometryEngine.match_segment_to_reference(
            QgsGeometry.fromWkt("LINESTRING (0 0, 2 2, 4 2, 6 0)"),
            0,
            0,
            1,
            QgsPointXY(0, 1),
            QgsPointXY(6, 1),
        )
        points = list(internal.vertices())
        self.assertEqual([(point.x(), point.y()) for point in points], [(0.0, 0.0), (1.0, 1.0), (5.0, 1.0), (6.0, 0.0)])
        parallel_internal = GeometryEngine.match_segment_to_reference(
            QgsGeometry.fromWkt("LINESTRING (0 0, 2 2, 4 2, 7 0)"),
            0,
            0,
            1,
            QgsPointXY(0, 0),
            QgsPointXY(2, 1),
            collinear=False,
        )
        parallel_points = list(parallel_internal.vertices())
        self.assertEqual((parallel_points[0].x(), parallel_points[0].y()), (0.0, 0.0))
        self.assertEqual((parallel_points[3].x(), parallel_points[3].y()), (7.0, 0.0))
        self.assertAlmostEqual(
            (parallel_points[2].y() - parallel_points[1].y())
            / (parallel_points[2].x() - parallel_points[1].x()),
            0.5,
        )

        terminal_source = QgsGeometry.fromWkt("LINESTRING (0 0, 2 0, 2 2)")
        terminal = GeometryEngine.match_segment_to_reference(
            terminal_source,
            0,
            0,
            0,
            QgsPointXY(0, 1),
            QgsPointXY(4, 1),
        )
        terminal_points = list(terminal.vertices())
        self.assertEqual([(point.x(), point.y()) for point in terminal_points], [(0.0, 1.0), (2.0, 1.0), (2.0, 2.0)])
        flipped = GeometryEngine.match_segment_to_reference(
            terminal_source,
            0,
            0,
            0,
            QgsPointXY(0, 1),
            QgsPointXY(4, 1),
            flip=True,
        )
        flipped_points = list(flipped.vertices())
        self.assertEqual([(point.x(), point.y()) for point in flipped_points], [(4.0, 1.0), (2.0, 1.0), (2.0, 2.0)])

        single_source = QgsGeometry.fromWkt("LINESTRING (0 0, 4 0)")
        single = GeometryEngine.match_segment_to_reference(
            single_source,
            0,
            0,
            0,
            QgsPointXY(10, -5),
            QgsPointXY(10, 5),
        )
        single_points = list(single.vertices())
        self.assertAlmostEqual(single.length(), 4.0)
        self.assertEqual([(point.x(), point.y()) for point in single_points], [(10.0, -2.0), (10.0, 2.0)])
        parallel = GeometryEngine.match_segment_to_reference(
            single_source,
            0,
            0,
            0,
            QgsPointXY(10, -5),
            QgsPointXY(10, 5),
            collinear=False,
        )
        parallel_points = list(parallel.vertices())
        self.assertEqual([(point.x(), point.y()) for point in parallel_points], [(2.0, -2.0), (2.0, 2.0)])

    def test_multipart_and_zm_dimensions_are_preserved(self):
        multipart = QgsGeometry.fromWkt(
            "MULTILINESTRING ((0 0, 2 0, 2 2), (10 0, 12 0, 12 2))"
        )
        result = GeometryEngine.match_segment_to_reference(
            multipart,
            1,
            0,
            0,
            QgsPointXY(10, 1),
            QgsPointXY(14, 1),
        )
        first_part = GeometryEngine.get_curve_from_geometry(result, 0, 0)
        second_part = GeometryEngine.get_curve_from_geometry(result, 1, 0)
        self.assertEqual(first_part.asWkt(), GeometryEngine.get_curve_from_geometry(multipart, 0, 0).asWkt())
        self.assertEqual((second_part.pointN(0).x(), second_part.pointN(0).y()), (10.0, 1.0))
        self.assertEqual((second_part.pointN(1).x(), second_part.pointN(1).y()), (12.0, 1.0))

        zm = QgsGeometry.fromWkt(
            "LINESTRING ZM (0 0 1 10, 2 0 2 20, 2 2 3 30)"
        )
        zm_result = GeometryEngine.match_segment_to_reference(
            zm,
            0,
            0,
            0,
            QgsPointXY(0, 1),
            QgsPointXY(4, 1),
        )
        zm_points = list(zm_result.vertices())
        self.assertTrue(QgsWkbTypes.hasZ(zm_result.wkbType()))
        self.assertTrue(QgsWkbTypes.hasM(zm_result.wkbType()))
        self.assertAlmostEqual(zm_points[0].z(), 1.0)
        self.assertAlmostEqual(zm_points[0].m(), 10.0)
        self.assertAlmostEqual(zm_points[1].z(), 2.5)
        self.assertAlmostEqual(zm_points[1].m(), 25.0)
        self.assertAlmostEqual(zm_points[2].z(), 3.0)
        self.assertAlmostEqual(zm_points[2].m(), 30.0)

    def test_invalid_collapse_parallel_adjacent_and_curves_are_blocked(self):
        with self.assertRaisesRegex(ValueError, "adjacent source edge"):
            GeometryEngine.match_segment_to_reference(
                QgsGeometry.fromWkt("LINESTRING (0 0, 2 0, 4 0)"),
                0,
                0,
                0,
                QgsPointXY(0, 1),
                QgsPointXY(4, 1),
            )
        with self.assertRaisesRegex(ValueError, "collapse"):
            GeometryEngine.match_segment_to_reference(
                QgsGeometry.fromWkt("POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"),
                0,
                0,
                2,
                QgsPointXY(0, 0),
                QgsPointXY(10, 0),
            )
        with self.assertRaisesRegex(ValueError, "curved"):
            GeometryEngine.match_segment_to_reference(
                QgsGeometry.fromWkt("CIRCULARSTRING (0 0, 1 1, 2 0)"),
                0,
                0,
                0,
                QgsPointXY(0, 1),
                QgsPointXY(2, 1),
            )

    def test_commit_changes_only_clicked_feature_and_supports_copy_undo(self):
        second_fid = add_geometry_feature(
            self.layer,
            QgsGeometry.fromWkt("LINESTRING (20 0, 24 0)"),
            [8],
        )
        self.layer.selectByIds([self.fid, second_fid])
        feature = self.layer.getFeature(self.fid)
        source_edge = LayerSegmentMatch(
            self.layer, self.fid, 0, 0, 0, QgsPointXY(2, 0), QgsPointXY(0, 0), QgsPointXY(4, 0), feature.geometry()
        )
        target_layer = QgsVectorLayer("LineString?crs=EPSG:3857", "target", "memory")
        target_geometry = QgsGeometry.fromWkt("LINESTRING (10 -5, 10 5)")
        target_fid = add_geometry_feature(target_layer, target_geometry)
        target_edge = LayerSegmentMatch(
            target_layer, target_fid, 0, 0, 0, QgsPointXY(10, 0), QgsPointXY(10, -5), QgsPointXY(10, 5), target_geometry
        )
        self.tool.source_layer = self.layer
        self.tool.source_features = [feature, self.layer.getFeature(second_fid)]
        self.tool.source_feature = feature
        self.tool.source_edge = source_edge
        self.tool.target_edge = target_edge
        self.tool.commit_match()
        moved = self.layer.getFeature(self.fid)
        self.assertAlmostEqual(moved.geometry().centroid().asPoint().x(), 10.0, places=6)
        self.assertEqual(moved["code"], 7)
        self.assertEqual(
            self.layer.getFeature(second_fid).geometry().asWkt(),
            "LineString (20 0, 24 0)",
        )

        self.layer.undoStack().undo()
        self.assertEqual(self.layer.getFeature(self.fid).geometry().asWkt(), "LineString (0 0, 4 0)")

        feature = self.layer.getFeature(self.fid)
        self.tool.source_layer = self.layer
        self.tool.source_features = [feature]
        self.tool.source_feature = feature
        self.tool.source_edge = LayerSegmentMatch(
            self.layer, self.fid, 0, 0, 0, QgsPointXY(2, 0), QgsPointXY(0, 0), QgsPointXY(4, 0), feature.geometry()
        )
        self.tool.target_edge = target_edge
        self.tool.ctrl_pressed = True
        self.tool.commit_match()
        self.assertEqual(self.layer.featureCount(), 3)
        self.assertEqual(sorted(feature["code"] for feature in self.layer.getFeatures()), [7, 7, 8])

    def test_same_feature_target_is_allowed_but_source_segment_is_excluded(self):
        polygon = QgsVectorLayer("Polygon?crs=EPSG:3857", "polygon", "memory")
        fid = add_geometry_feature(
            polygon,
            QgsGeometry.fromWkt("POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0))"),
        )
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.canvas.setLayers([polygon])
        self.canvas.setExtent(QgsRectangle(-1, -1, 5, 5))
        excluded = {(polygon.id(), fid, 0, 0, 0)}

        other_edge = SnappingHelper.find_segment_across_visible_layers(
            self.canvas,
            QgsPointXY(4, 2),
            excluded_segments=excluded,
        )
        self.assertIsNotNone(other_edge)
        self.assertEqual(other_edge.fid, fid)
        self.assertEqual(other_edge.segment_idx, 1)
        source_edge = SnappingHelper.find_segment_across_visible_layers(
            self.canvas,
            QgsPointXY(2, 0),
            excluded_segments=excluded,
        )
        self.assertIsNone(source_edge)

    def test_hud_reports_local_length_and_error_state(self):
        self.widget.set_preview(12.5, 4.0, 6.25, False, False)
        self.assertEqual(self.widget._status_labels["angle"].text(), "12.50°")
        self.assertEqual(self.widget._status_labels["length"].text(), "4.000 → 6.250")
        self.assertIn("Редагування", self.widget._status_labels["mode"].text())
        self.widget.set_error("invalid")
        self.assertEqual(self.widget.lbl_step.text(), "invalid")
        self.assertIn("#fee2e2", self.widget.lbl_step.styleSheet())

    def test_cross_layer_segment_match_returns_canvas_crs_and_honors_exclusion(self):
        projected = QgsVectorLayer("LineString?crs=EPSG:3857", "projected", "memory")
        to_projected = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            projected.crs(),
            QgsProject.instance(),
        )
        first = to_projected.transform(QgsPointXY(0.9, 0.0))
        second = to_projected.transform(QgsPointXY(1.1, 0.0))
        geometry = QgsGeometry.fromPolylineXY([first, second])
        fid = add_geometry_feature(projected, geometry)
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.canvas.setLayers([projected])
        self.canvas.setExtent(QgsRectangle(0.5, -0.5, 1.5, 0.5))

        match = SnappingHelper.find_segment_across_visible_layers(
            self.canvas,
            QgsPointXY(1.0, 0.0),
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.layer.id(), projected.id())
        self.assertAlmostEqual(match.point.x(), 1.0, places=5)
        self.assertAlmostEqual(match.p1.x(), 0.9, places=5)
        excluded = SnappingHelper.find_segment_across_visible_layers(
            self.canvas,
            QgsPointXY(1.0, 0.0),
            excluded_features={(projected.id(), fid)},
        )
        self.assertIsNone(excluded)

    def test_commit_is_calculated_in_canvas_crs_and_returned_to_source_crs(self):
        geographic = QgsVectorLayer(
            "LineString?crs=EPSG:4326&field=code:int",
            "geographic",
            "memory",
        )
        fid = add_geometry_feature(
            geographic,
            QgsGeometry.fromWkt("LINESTRING (0 0, 0.01 0)"),
            [9],
        )
        geographic.startEditing()
        geographic.selectByIds([fid])
        self.canvas.setCurrentLayer(geographic)
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        feature = geographic.getFeature(fid)
        to_canvas = QgsCoordinateTransform(
            geographic.crs(),
            self.canvas.mapSettings().destinationCrs(),
            QgsProject.instance(),
        )
        source_start = to_canvas.transform(QgsPointXY(0, 0))
        source_end = to_canvas.transform(QgsPointXY(0.01, 0))
        source_edge = LayerSegmentMatch(
            geographic,
            fid,
            0,
            0,
            0,
            QgsPointXY((source_start.x() + source_end.x()) * 0.5, 0),
            QgsPointXY(source_start),
            QgsPointXY(source_end),
            feature.geometry(),
        )
        target_layer = QgsVectorLayer("LineString?crs=EPSG:3857", "target", "memory")
        target_geometry = QgsGeometry.fromWkt("LINESTRING (10000 -2000, 10000 2000)")
        target_fid = add_geometry_feature(target_layer, target_geometry)
        target_edge = LayerSegmentMatch(
            target_layer,
            target_fid,
            0,
            0,
            0,
            QgsPointXY(10000, 0),
            QgsPointXY(10000, -2000),
            QgsPointXY(10000, 2000),
            target_geometry,
        )
        tool = self.tool
        tool.source_layer = geographic
        tool.source_features = [feature]
        tool.source_feature = feature
        tool.source_edge = source_edge
        tool.target_edge = target_edge
        tool.commit_match()
        moved_canvas = QgsGeometry(geographic.getFeature(fid).geometry())
        moved_canvas.transform(to_canvas)
        self.assertAlmostEqual(moved_canvas.centroid().asPoint().x(), 10000.0, places=5)
        self.assertEqual(geographic.getFeature(fid)["code"], 9)
        geographic.rollBack()


if __name__ == "__main__":
    unittest.main(verbosity=2)

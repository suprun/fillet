# -*- coding: utf-8 -*-
"""Tests for Extract Part multipart preservation, sessions, and undo."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas

from core.geometry_engine import GeometryEngine
from core.snapping_helper import SnappingHelper
from gui.extract_part_canvas_widget import ExtractPartCanvasWidget
from gui.extract_part_map_tool import ExtractPartMapTool
from research_tool_test_utils import TestIface, add_geometry_feature

app = QgsApplication([], False)
app.initQgis()


class TestExtractPartTool(unittest.TestCase):
    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.layer = QgsVectorLayer("MultiPolygon?crs=EPSG:3857&field=name:string", "parts", "memory")
        geometry = QgsGeometry.fromWkt(
            "MULTIPOLYGON (((0 0, 2 0, 2 2, 0 2, 0 0)), "
            "((5 0, 7 0, 7 2, 5 2, 5 0)), ((10 0, 12 0, 12 2, 10 2, 10 0)))"
        )
        self.fid = add_geometry_feature(self.layer, geometry, ["parcel"])
        self.layer.startEditing()
        self.canvas.setCurrentLayer(self.layer)
        self.widget = ExtractPartCanvasWidget(self.canvas)
        self.iface = TestIface(self.canvas)
        self.tool = ExtractPartMapTool(self.canvas, self.widget, self.iface)
        self.tool.source_layer = self.layer
        self.tool.source_fid = self.fid

    def tearDown(self):
        self.tool.cleanup()
        self.layer.rollBack()

    def test_move_preserves_source_fid_attributes_and_undo(self):
        self.tool._commit([0], copy=False)
        self.assertEqual(self.layer.featureCount(), 2)
        source = self.layer.getFeature(self.fid)
        self.assertTrue(source.isValid())
        self.assertEqual(source["name"], "parcel")
        self.assertEqual(len(source.geometry().asGeometryCollection()), 2)
        self.assertTrue(all(feature["name"] == "parcel" for feature in self.layer.getFeatures()))
        self.assertTrue(self.tool._undo_last_tool_command())
        self.assertEqual(self.layer.featureCount(), 1)
        self.assertEqual(len(self.layer.getFeature(self.fid).geometry().asGeometryCollection()), 3)

    def test_copy_all_allowed_but_move_all_blocked(self):
        self.tool._commit([0, 1, 2], copy=False)
        self.assertEqual(self.layer.featureCount(), 1)
        self.assertTrue(self.iface.messages.messages)
        self.tool._commit([0, 1, 2], copy=True)
        self.assertEqual(self.layer.featureCount(), 4)
        self.assertEqual(len(self.layer.getFeature(self.fid).geometry().asGeometryCollection()), 3)

    def test_zm_and_native_curved_parts_are_not_segmentized(self):
        geometry = QgsGeometry.fromWkt(
            "MULTICURVE ZM (CIRCULARSTRING ZM (0 0 1 2, 1 1 2 3, 2 0 3 4), "
            "LINESTRING ZM (3 0 4 5, 4 0 5 6))"
        )
        remaining, extracted = GeometryEngine.extract_geometry_parts(geometry, [0])
        self.assertEqual(len(extracted), 1)
        self.assertTrue(GeometryEngine.has_curved_segments(extracted[0]))
        self.assertTrue(QgsWkbTypes.hasZ(extracted[0].wkbType()))
        self.assertTrue(QgsWkbTypes.hasM(extracted[0].wkbType()))
        self.assertFalse(remaining.isEmpty())

    def test_cross_layer_feature_hover_uses_nearest_point_api(self):
        path_layer = QgsVectorLayer("MultiLineString?crs=EPSG:3857", "path", "memory")
        path_fid = add_geometry_feature(
            path_layer,
            QgsGeometry.fromWkt("MULTILINESTRING ((0 0, 4 0), (10 0, 14 0))"),
        )
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.canvas.setLayers([path_layer])
        self.canvas.setExtent(QgsRectangle(-1, -1, 15, 1))

        match = SnappingHelper.find_feature_across_visible_layers(
            self.canvas,
            QgsPointXY(2, 0),
            geometry_types=[QgsWkbTypes.GeometryType.LineGeometry],
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.layer, path_layer)
        self.assertEqual(match.fid, path_fid)
        self.assertAlmostEqual(match.point.x(), 2.0)
        self.assertAlmostEqual(match.point.y(), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

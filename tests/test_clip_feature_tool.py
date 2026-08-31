# -*- coding: utf-8 -*-
"""Tests for Clip Feature intersection, cutter union, and Z support."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from qgis.core import QgsApplication, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapCanvas

from core.geometry_engine import GeometryEngine
from core.snapping_helper import LayerFeatureMatch
from gui.boolean_feature_canvas_widget import BooleanFeatureCanvasWidget
from gui.boolean_feature_map_tool import BooleanFeatureMapTool
from research_tool_test_utils import TestIface, add_geometry_feature

app = QgsApplication([], False)
app.initQgis()


class TestClipFeatureTool(unittest.TestCase):
    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.layer = QgsVectorLayer("MultiPolygon?crs=EPSG:3857&field=value:int", "target", "memory")
        target = QgsGeometry.fromWkt("MULTIPOLYGON (((0 0, 10 0, 10 10, 0 10, 0 0)))")
        self.target_fid = add_geometry_feature(self.layer, target, [42])
        self.layer.startEditing()
        self.canvas.setCurrentLayer(self.layer)
        self.cutter_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "cutters", "memory")
        self.cutters = [
            QgsGeometry.fromWkt("POLYGON ((0 0, 4 0, 4 10, 0 10, 0 0))"),
            QgsGeometry.fromWkt("POLYGON ((6 0, 10 0, 10 10, 6 10, 6 0))"),
        ]
        self.cutter_fids = [add_geometry_feature(self.cutter_layer, geometry) for geometry in self.cutters]
        self.widget = BooleanFeatureCanvasWidget(self.canvas, "clip")
        self.iface = TestIface(self.canvas)
        self.tool = BooleanFeatureMapTool(self.canvas, self.widget, "clip", self.iface)
        self.tool.target_layer = self.layer
        self.tool.target_fid = self.target_fid

    def tearDown(self):
        self.tool.cleanup()
        self.layer.rollBack()

    def test_union_cutters_clip_and_preserve_target_identity(self):
        matches = [
            LayerFeatureMatch(self.cutter_layer, fid, QgsPointXY(), QgsGeometry(geometry))
            for fid, geometry in zip(self.cutter_fids, self.cutters)
        ]
        self.tool._commit(matches, keep_target=False)
        target = self.layer.getFeature(self.target_fid)
        self.assertTrue(target.isValid())
        self.assertEqual(target["value"], 42)
        self.assertAlmostEqual(target.geometry().area(), 80.0)
        self.assertTrue(target.geometry().isMultipart())
        self.assertEqual(self.cutter_layer.featureCount(), 2)

    def test_non_overlap_is_empty_and_target_remains_unchanged(self):
        far = QgsGeometry.fromWkt("POLYGON ((20 20, 21 20, 21 21, 20 21, 20 20))")
        far_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "far", "memory")
        far_fid = add_geometry_feature(far_layer, far)
        before = self.layer.getFeature(self.target_fid).geometry().asWkt()
        self.tool._commit(
            [LayerFeatureMatch(far_layer, far_fid, QgsPointXY(), far)],
            keep_target=False,
        )
        self.assertEqual(self.layer.getFeature(self.target_fid).geometry().asWkt(), before)
        self.assertTrue(self.iface.messages.messages)

    def test_z_polygon_boolean_is_supported(self):
        target_z = QgsGeometry.fromWkt("POLYGON Z ((0 0 5, 5 0 5, 5 5 5, 0 5 5, 0 0 5))")
        cutter_z = QgsGeometry.fromWkt("POLYGON Z ((2 0 8, 4 0 8, 4 5 8, 2 5 8, 2 0 8))")
        result = GeometryEngine.apply_polygon_boolean(target_z, [cutter_z], "clip")
        self.assertAlmostEqual(result.area(), 10.0)
        self.assertTrue(QgsWkbTypes.hasZ(result.wkbType()))


if __name__ == "__main__":
    unittest.main(verbosity=2)

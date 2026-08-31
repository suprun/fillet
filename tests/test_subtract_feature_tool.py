# -*- coding: utf-8 -*-
"""Tests for Subtract Feature polygon safety and atomic target editing."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from qgis.core import QgsApplication, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.gui import QgsMapCanvas

from core.geometry_engine import GeometryEngine
from core.snapping_helper import LayerFeatureMatch
from gui.boolean_feature_canvas_widget import BooleanFeatureCanvasWidget
from gui.boolean_feature_map_tool import BooleanFeatureMapTool
from research_tool_test_utils import TestIface, add_geometry_feature

app = QgsApplication([], False)
app.initQgis()


class TestSubtractFeatureTool(unittest.TestCase):
    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.layer = QgsVectorLayer("Polygon?crs=EPSG:3857&field=name:string", "target", "memory")
        self.target_fid = add_geometry_feature(
            self.layer, QgsGeometry.fromWkt("POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"), ["lot"]
        )
        self.layer.startEditing()
        self.canvas.setCurrentLayer(self.layer)
        self.cutter_layer = QgsVectorLayer("Polygon?crs=EPSG:3857&field=name:string", "cutter", "memory")
        self.cutter_geometry = QgsGeometry.fromWkt("POLYGON ((2 2, 8 2, 8 8, 2 8, 2 2))")
        self.cutter_fid = add_geometry_feature(self.cutter_layer, self.cutter_geometry, ["mask"])
        self.widget = BooleanFeatureCanvasWidget(self.canvas, "subtract")
        self.iface = TestIface(self.canvas)
        self.tool = BooleanFeatureMapTool(self.canvas, self.widget, "subtract", self.iface)
        self.tool.target_layer = self.layer
        self.tool.target_fid = self.target_fid

    def tearDown(self):
        self.tool.cleanup()
        self.layer.rollBack()

    def cutter_match(self):
        return LayerFeatureMatch(
            self.cutter_layer, self.cutter_fid, QgsPointXY(3, 3), QgsGeometry(self.cutter_geometry)
        )

    def test_subtract_hole_preserves_fid_attributes_and_cutter(self):
        cutter_before = self.cutter_layer.getFeature(self.cutter_fid).geometry().asWkt()
        self.tool._commit([self.cutter_match()], keep_target=True)
        target = self.layer.getFeature(self.target_fid)
        self.assertTrue(target.isValid())
        self.assertEqual(target["name"], "lot")
        self.assertAlmostEqual(target.geometry().area(), 64.0)
        self.assertEqual(self.cutter_layer.getFeature(self.cutter_fid).geometry().asWkt(), cutter_before)
        self.assertEqual(self.tool.target_fid, self.target_fid)
        self.assertTrue(self.tool._undo_last_tool_command())
        self.assertAlmostEqual(self.layer.getFeature(self.target_fid).geometry().area(), 100.0)

    def test_empty_invalid_and_singlepart_split_are_blocked(self):
        target = self.layer.getFeature(self.target_fid).geometry()
        empty = GeometryEngine.apply_polygon_boolean(target, [QgsGeometry(target)], "subtract")
        self.assertTrue(empty.isEmpty())
        invalid = QgsGeometry.fromWkt("POLYGON ((0 0, 4 4, 0 4, 4 0, 0 0))")
        with self.assertRaises(ValueError):
            GeometryEngine.apply_polygon_boolean(invalid, [self.cutter_geometry], "subtract")

        split = QgsGeometry.fromWkt("POLYGON ((4 -1, 6 -1, 6 11, 4 11, 4 -1))")
        split_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "split", "memory")
        split_fid = add_geometry_feature(split_layer, split)
        before = target.asWkt()
        self.tool._commit(
            [LayerFeatureMatch(split_layer, split_fid, QgsPointXY(5, 5), split)],
            keep_target=False,
        )
        self.assertEqual(self.layer.getFeature(self.target_fid).geometry().asWkt(), before)
        self.assertTrue(self.iface.messages.messages)

    def test_m_and_curved_inputs_are_rejected(self):
        polygon_m = QgsGeometry.fromWkt("POLYGON M ((0 0 1, 4 0 1, 4 4 1, 0 4 1, 0 0 1))")
        with self.assertRaises(ValueError):
            GeometryEngine.apply_polygon_boolean(polygon_m, [self.cutter_geometry], "subtract")
        curved = QgsGeometry.fromWkt("CURVEPOLYGON (CIRCULARSTRING (0 0, 2 2, 4 0, 2 -2, 0 0))")
        with self.assertRaises(ValueError):
            GeometryEngine.apply_polygon_boolean(curved, [self.cutter_geometry], "subtract")


if __name__ == "__main__":
    unittest.main(verbosity=2)

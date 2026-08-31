# -*- coding: utf-8 -*-
"""Tests for Array Along Path placement and atomic copy creation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from qgis.core import QgsApplication, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.gui import QgsMapCanvas

from core.geometry_engine import GeometryEngine
from gui.array_along_path_canvas_widget import ArrayAlongPathCanvasWidget, PathDistributionMode
from gui.array_along_path_map_tool import ArrayAlongPathMapTool
from research_tool_test_utils import TestIface, add_geometry_feature

app = QgsApplication([], False)
app.initQgis()


class TestArrayAlongPathTool(unittest.TestCase):
    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.layer = QgsVectorLayer("Point?crs=EPSG:3857&field=name:string", "source", "memory")
        self.fid = add_geometry_feature(self.layer, QgsGeometry.fromWkt("POINT (0 0)"), ["tree"])
        self.layer.startEditing()
        self.layer.selectByIds([self.fid])
        self.canvas.setCurrentLayer(self.layer)
        self.widget = ArrayAlongPathCanvasWidget(self.canvas)
        self.tool = ArrayAlongPathMapTool(self.canvas, self.widget, TestIface(self.canvas))

    def tearDown(self):
        self.tool.cleanup()
        self.layer.rollBack()

    def test_count_spacing_reverse_offset_and_tangent_contract(self):
        straight = QgsGeometry.fromWkt("LINESTRING (0 0, 10 0)")
        count = GeometryEngine.compute_path_placements(straight, 0, 10, "count", 3, True)
        self.assertEqual([round(item[0].x(), 6) for item in count], [0.0, 5.0, 10.0])
        no_start = GeometryEngine.compute_path_placements(straight, 0, 10, "count", 2, False)
        self.assertEqual([item[0].x() for item in no_start], [5.0, 10.0])
        spacing = GeometryEngine.compute_path_placements(straight, 0, 10, "spacing", 4, False)
        self.assertEqual([item[0].x() for item in spacing], [4.0, 8.0])
        reverse = GeometryEngine.compute_path_placements(straight, 0, 10, "count", 2, True, offset=2, reverse=True)
        self.assertEqual([(item[0].x(), item[0].y()) for item in reverse], [(10.0, 2.0), (0.0, 2.0)])

        bent = QgsGeometry.fromWkt("LINESTRING (0 0, 5 0, 5 5)")
        oriented = GeometryEngine.compute_path_placements(
            bent, 0, 10, "count", 3, False, tangent_orientation=True
        )
        self.assertAlmostEqual(oriented[0][1], 0.0)
        self.assertGreater(abs(oriented[-1][1]), 80.0)

    def test_commit_creates_exact_number_of_new_copies(self):
        self.widget.radio_count.setChecked(True)
        self.widget.spin_count.setValue(4)
        self.widget.chk_include_start.setChecked(True)
        self.tool.source_layer = self.layer
        self.tool.source_features = list(self.layer.getSelectedFeatures())
        self.tool.anchor = QgsPointXY(0, 0)
        self.tool.path_geometry = QgsGeometry.fromWkt("LINESTRING (0 0, 9 0)")
        self.tool.start_measure = 0.0
        self.tool.end_measure = 9.0
        self.tool.state = self.tool.STATE_PREVIEW
        self.tool.commit_array()
        self.assertEqual(self.layer.featureCount(), 5)
        xs = sorted(round(feature.geometry().asPoint().x(), 6) for feature in self.layer.getFeatures())
        self.assertEqual(xs, [0.0, 0.0, 3.0, 6.0, 9.0])
        self.assertTrue(all(feature["name"] == "tree" for feature in self.layer.getFeatures()))

    def test_clicked_multipart_part_is_not_stitched(self):
        path_layer = QgsVectorLayer("MultiLineString?crs=EPSG:3857", "path", "memory")
        geometry = QgsGeometry.fromWkt("MULTILINESTRING ((0 0, 5 0), (100 0, 110 0))")
        fid = add_geometry_feature(path_layer, geometry)
        from core.snapping_helper import LayerFeatureMatch

        selected = self.tool._clicked_path_part(
            LayerFeatureMatch(path_layer, fid, QgsPointXY(102, 0), geometry),
            QgsPointXY(102, 0),
        )
        self.assertAlmostEqual(selected.length(), 10.0)
        self.assertGreater(selected.boundingBox().xMinimum(), 90.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""
Tests for Two-Line Fillet and Chamfer geometry algorithm.
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
)

app = QgsApplication([], False)
app.initQgis()

from core.geometry_engine import GeometryEngine


class TestTwoLineFillet(unittest.TestCase):

    def test_orthogonal_fillet(self):
        # Line 1: (0, 10) -> (10, 10)
        # Line 2: (10, 0) -> (10, 20)
        # V = (10, 10), radius = 2.0
        l1 = QgsGeometry(QgsLineString([QgsPoint(0, 10), QgsPoint(10, 10)]))
        l2 = QgsGeometry(QgsLineString([QgsPoint(10, 0), QgsPoint(10, 20)]))

        res = GeometryEngine.fillet_or_chamfer_two_lines(
            l1, 0, QgsPoint(2, 10),
            l2, 0, QgsPoint(10, 2),
            mode="fillet", radius=2.0, segments_count=8
        )
        self.assertIsNotNone(res)
        geom, v, t1, t2 = res
        self.assertFalse(geom.isEmpty())
        pts = geom.asPolyline()
        # Start at (0, 10), End at (10, 0)
        self.assertAlmostEqual(pts[0].x(), 0.0, places=4)
        self.assertAlmostEqual(pts[0].y(), 10.0, places=4)
        self.assertAlmostEqual(pts[-1].x(), 10.0, places=4)
        self.assertAlmostEqual(pts[-1].y(), 0.0, places=4)
        # Tangent points: t1=(8, 10), t2=(10, 8)
        self.assertAlmostEqual(t1.x(), 8.0, places=4)
        self.assertAlmostEqual(t1.y(), 10.0, places=4)
        self.assertAlmostEqual(t2.x(), 10.0, places=4)
        self.assertAlmostEqual(t2.y(), 8.0, places=4)

    def test_orthogonal_chamfer(self):
        l1 = QgsGeometry(QgsLineString([QgsPoint(0, 10), QgsPoint(10, 10)]))
        l2 = QgsGeometry(QgsLineString([QgsPoint(10, 0), QgsPoint(10, 20)]))

        res = GeometryEngine.fillet_or_chamfer_two_lines(
            l1, 0, QgsPoint(2, 10),
            l2, 0, QgsPoint(10, 2),
            mode="chamfer", dist1=3.0, dist2=3.0
        )
        self.assertIsNotNone(res)
        geom, v, t1, t2 = res
        pts = geom.asPolyline()
        self.assertEqual(len(pts), 4)
        self.assertAlmostEqual(pts[0].x(), 0.0, places=4)
        self.assertAlmostEqual(pts[1].x(), 7.0, places=4)
        self.assertAlmostEqual(pts[2].x(), 10.0, places=4)
        self.assertAlmostEqual(pts[3].y(), 0.0, places=4)

    def test_extend_short_lines(self):
        # Short lines that do not touch, but their extensions meet at (10, 10)
        l1_short = QgsGeometry(QgsLineString([QgsPoint(0, 10), QgsPoint(5, 10)]))
        l2_short = QgsGeometry(QgsLineString([QgsPoint(10, 0), QgsPoint(10, 5)]))

        res = GeometryEngine.fillet_or_chamfer_two_lines(
            l1_short, 0, QgsPoint(2, 10),
            l2_short, 0, QgsPoint(10, 2),
            mode="fillet", radius=2.0, segments_count=8
        )
        self.assertIsNotNone(res)
        geom, v, t1, t2 = res
        pts = geom.asPolyline()
        self.assertAlmostEqual(pts[0].x(), 0.0, places=4)
        self.assertAlmostEqual(pts[-1].y(), 0.0, places=4)

    def test_parallel_lines_returns_none(self):
        # Parallel lines never intersect
        l1 = QgsGeometry(QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0)]))
        l2 = QgsGeometry(QgsLineString([QgsPoint(0, 5), QgsPoint(10, 5)]))

        res = GeometryEngine.fillet_or_chamfer_two_lines(
            l1, 0, QgsPoint(5, 0),
            l2, 0, QgsPoint(5, 5),
            mode="fillet", radius=1.0
        )
        self.assertIsNone(res)

    def test_two_line_hud_widget(self):
        from qgis.gui import QgsMapCanvas
        from gui.two_line_canvas_widget import TwoLineCanvasWidget

        canvas = QgsMapCanvas()
        canvas.resize(800, 600)
        widget = TwoLineCanvasWidget(canvas)

        widget.set_step(TwoLineCanvasWidget.STEP_FIRST_LINE)
        self.assertIn("1.", widget.lbl_step.text())
        self.assertGreater(widget.width(), 50)

        widget.set_step(TwoLineCanvasWidget.STEP_SECOND_LINE)
        self.assertIn("2.", widget.lbl_step.text())
        self.assertGreater(widget.width(), 50)

    def test_two_line_map_tool_feature_merge(self):
        from qgis.core import (
            QgsFeature,
            QgsField,
            QgsFields,
            QgsVectorLayer,
            QgsSettings,
        )
        from qgis.gui import QgsMapCanvas
        from qgis.PyQt.QtCore import QVariant
        from gui.two_line_map_tool import TwoLineMapTool

        canvas = QgsMapCanvas()
        canvas.resize(800, 600)

        # Create memory layer with two lines
        layer = QgsVectorLayer("LineString?crs=EPSG:3857", "test_lines", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", getattr(QVariant, "String", 10))])
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(10, 10)]))
        f1.setAttribute("name", "Line 1")

        f2 = QgsFeature(layer.fields())
        f2.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(10, 0), QgsPointXY(10, 20)]))
        f2.setAttribute("name", "Line 2")

        pr.addFeatures([f1, f2])
        layer.startEditing()
        canvas.setCurrentLayer(layer)

        initial_feats = list(layer.getFeatures())
        f1_actual = initial_feats[0]
        f2_actual = initial_feats[1]

        tool = TwoLineMapTool(canvas, iface=None)
        tool.activate()

        # Always first setting
        s = QgsSettings()
        s.setValue("plugins/fillet/merge_always_first_feature", True)

        # Compute merged geometry
        res = GeometryEngine.fillet_or_chamfer_two_lines(
            f1_actual.geometry(), 0, QgsPoint(2, 10),
            f2_actual.geometry(), 0, QgsPoint(10, 2),
            mode="fillet", radius=2.0
        )
        self.assertIsNotNone(res)
        new_geom, v, t1, t2 = res

        # Apply merge operation
        tool._apply_two_line_operation(layer, f1_actual.id(), f2_actual.id(), new_geom)

        # Verify only 1 feature remains with merged geometry
        feats = list(layer.getFeatures())
        self.assertEqual(len(feats), 1)
        self.assertEqual(feats[0].id(), f1_actual.id())
        self.assertEqual(feats[0]["name"], "Line 1")
        self.assertFalse(feats[0].geometry().isEmpty())

        tool.cleanup()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTwoLineFillet)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)

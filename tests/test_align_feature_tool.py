# -*- coding: utf-8 -*-
"""Tests for Align Feature geometry and atomic move/copy behavior."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from qgis.core import QgsApplication, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QEvent, Qt
from qgis.PyQt.QtGui import QKeyEvent

from core.geometry_engine import GeometryEngine
from gui.align_feature_canvas_widget import AlignFeatureCanvasWidget, AlignReferenceMode
from gui.align_feature_map_tool import AlignFeatureMapTool
from research_tool_test_utils import TestIface, add_geometry_feature

app = QgsApplication([], False)
app.initQgis()


class TestAlignFeatureTool(unittest.TestCase):
    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.layer = QgsVectorLayer("LineString?crs=EPSG:3857&field=name:string", "source", "memory")
        self.fid = add_geometry_feature(
            self.layer,
            QgsGeometry.fromWkt("LINESTRING (0 0, 2 0)"),
            ["road"],
        )
        self.layer.startEditing()
        self.layer.selectByIds([self.fid])
        self.canvas.setCurrentLayer(self.layer)
        self.widget = AlignFeatureCanvasWidget(self.canvas)
        self.widget.set_reference_mode(AlignReferenceMode.Points)
        self.tool = AlignFeatureMapTool(self.canvas, self.widget, TestIface(self.canvas))

    def tearDown(self):
        self.tool.cleanup()
        self.layer.rollBack()

    def test_alignment_math_fit_flip_and_zero_reference(self):
        angle, scale, dx, dy = GeometryEngine.compute_alignment_transform(
            QgsPointXY(0, 0), QgsPointXY(2, 0), QgsPointXY(10, 5), QgsPointXY(10, 9), fit=True
        )
        self.assertAlmostEqual(angle, 90.0)
        self.assertAlmostEqual(scale, 2.0)
        self.assertEqual((dx, dy), (10.0, 5.0))
        flipped = GeometryEngine.compute_alignment_transform(
            QgsPointXY(0, 0), QgsPointXY(2, 0), QgsPointXY(10, 5), QgsPointXY(10, 9), flip=True
        )
        self.assertAlmostEqual(abs(flipped[0]), 90.0)
        with self.assertRaises(ValueError):
            GeometryEngine.compute_alignment_transform(
                QgsPointXY(0, 0), QgsPointXY(0, 0), QgsPointXY(1, 1), QgsPointXY(2, 2)
            )

    def test_move_and_copy_preserve_geometry_contract(self):
        self.tool.source_layer = self.layer
        self.tool.source_features = list(self.layer.getSelectedFeatures())
        self.tool.source_start = QgsPointXY(0, 0)
        self.tool.source_end = QgsPointXY(2, 0)
        self.tool.target_start = QgsPointXY(10, 5)
        self.tool.target_end = QgsPointXY(10, 9)
        self.tool.shift_pressed = True
        self.tool.commit_alignment()

        moved = self.layer.getFeature(self.fid)
        points = list(moved.geometry().vertices())
        self.assertAlmostEqual(points[0].x(), 10.0, places=6)
        self.assertAlmostEqual(points[0].y(), 5.0, places=6)
        self.assertAlmostEqual(points[-1].x(), 10.0, places=6)
        self.assertAlmostEqual(points[-1].y(), 9.0, places=6)
        self.assertEqual(moved["name"], "road")

        self.tool.source_layer = self.layer
        self.tool.source_features = [moved]
        self.tool.source_start = QgsPointXY(10, 5)
        self.tool.source_end = QgsPointXY(10, 9)
        self.tool.target_start = QgsPointXY(20, 0)
        self.tool.target_end = QgsPointXY(20, 4)
        self.tool.shift_pressed = False
        self.tool.ctrl_pressed = True
        self.tool.commit_alignment()
        self.assertEqual(self.layer.featureCount(), 2)
        self.assertTrue(all(feature["name"] == "road" for feature in self.layer.getFeatures()))

    def test_similarity_transform_preserves_z_and_native_curve(self):
        curved = QgsGeometry.fromWkt("CIRCULARSTRING Z (0 0 3, 1 1 4, 2 0 5)")
        transformed = GeometryEngine.apply_similarity_transform(
            curved, QgsPointXY(0, 0), 90.0, 2.0, 4.0, 5.0
        )
        self.assertTrue(GeometryEngine.has_curved_segments(transformed))
        self.assertTrue(QgsWkbTypes.hasZ(transformed.wkbType()))
        self.assertAlmostEqual(transformed.vertexAt(0).z(), 3.0)

    def test_shared_hud_keyboard_routing_is_qt5_qt6_compatible(self):
        shortcuts = []
        modifiers = []
        steps = []
        self.widget.shortcutRequested.connect(shortcuts.append)
        self.widget.modifierChanged.connect(lambda name, pressed: modifiers.append((name, pressed)))
        self.widget.stepBackRequested.connect(lambda: steps.append(True))
        self.widget.show_on_canvas()
        event_press = getattr(QEvent.Type, "KeyPress", None)
        event_release = getattr(QEvent.Type, "KeyRelease", None)
        if event_press is None:
            event_press = getattr(QEvent, "KeyPress")
            event_release = getattr(QEvent, "KeyRelease")
        no_modifier = getattr(Qt.KeyboardModifier, "NoModifier", None)
        if no_modifier is None:
            no_modifier = getattr(Qt, "NoModifier", 0)

        def key_value(name, fallback):
            value = getattr(Qt.Key, name, None)
            return value if value is not None else getattr(Qt, name, fallback)

        self.assertTrue(
            self.widget.eventFilter(
                self.widget,
                QKeyEvent(event_press, key_value("Key_F", 0x46), no_modifier),
            )
        )
        self.widget.eventFilter(
            self.widget,
            QKeyEvent(event_press, key_value("Key_Shift", 0x01000020), no_modifier),
        )
        self.widget.eventFilter(
            self.widget,
            QKeyEvent(event_release, key_value("Key_Shift", 0x01000020), no_modifier),
        )
        self.assertTrue(
            self.widget.eventFilter(
                self.widget,
                QKeyEvent(event_press, key_value("Key_Backspace", 0x01000003), no_modifier),
            )
        )
        self.assertEqual(shortcuts, ["flip"])
        self.assertEqual(modifiers, [("shift", True), ("shift", False)])
        self.assertEqual(steps, [True])


if __name__ == "__main__":
    unittest.main(verbosity=2)

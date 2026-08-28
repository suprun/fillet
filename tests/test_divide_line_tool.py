# -*- coding: utf-8 -*-
"""
Unit tests for CAD Divide / Measure Line tool.
Tests DivideLineCanvasWidget, CADDivideLineMapTool, and GeometryEngine.divide_line_geometries.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow, QToolBar

app = QgsApplication([], False)
app.initQgis()

from core.geometry_engine import GeometryEngine
from core.snapping_helper import SnappingHelper
from gui.divide_line_canvas_widget import DivideLineCanvasWidget, DivideLineMode
from gui.divide_line_map_tool import CADDivideLineMapTool
from plugin import FilletPlugin


class MockMessageBar(QObject):
    def __init__(self):
        super().__init__()
        self.messages = []

    def pushMessage(self, title, text, level=0, duration=0):
        self.messages.append((title, text, level, duration))

    def pushWarning(self, title, text):
        self.messages.append((title, text, 1, 0))


class MockIface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def __init__(self, win, canvas, tb):
        super().__init__()
        self._win = win
        self._canvas = canvas
        self._tb = tb
        self._message_bar = MockMessageBar()

    def messageBar(self):
        return self._message_bar

    def mainWindow(self):
        return self._win

    def mapCanvas(self):
        return self._canvas

    def advancedDigitizeToolBar(self):
        return self._tb

    def addVectorToolBarIcon(self, a):
        self._tb.addAction(a)

    def removeVectorToolBarIcon(self, a):
        self._tb.removeAction(a)

    def addPluginToVectorMenu(self, n, a):
        pass

    def removePluginVectorMenu(self, n, a):
        pass

    def addDockWidget(self, area, d):
        self._win.addDockWidget(area, d)

    def removeDockWidget(self, d):
        self._win.removeDockWidget(d)

    def currentLayer(self):
        return self._canvas.currentLayer()

    def cadDockWidget(self):
        return None

    def vectorLayerTools(self):
        return None


class TestCADDivideLineTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canvas = QgsMapCanvas()
        cls.win = QMainWindow()
        cls.tb = QToolBar(cls.win)
        cls.win.addToolBar(cls.tb)
        cls.iface = MockIface(cls.win, cls.canvas, cls.tb)

    def setUp(self):
        self.line_layer = QgsVectorLayer("LineString?crs=EPSG:3857", "TestLines", "memory")
        QgsProject.instance().addMapLayers([self.line_layer])

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()

    def test_divide_line_by_count(self):
        """Test dividing 10m line into 4 equal segments of 2.5m each."""
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 0.0)])

        sub_geoms = GeometryEngine.divide_line_geometries(line_geom, count=4)
        self.assertEqual(len(sub_geoms), 4)

        for i, g in enumerate(sub_geoms):
            self.assertAlmostEqual(g.length(), 2.5, places=4)
            pts = g.asPolyline()
            self.assertAlmostEqual(pts[0].x(), i * 2.5, places=4)
            self.assertAlmostEqual(pts[1].x(), (i + 1) * 2.5, places=4)

    def test_divide_line_by_step_length(self):
        """Test dividing 10m line with fixed step 3.0m -> 3.0, 3.0, 3.0, 1.0."""
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 0.0)])

        sub_geoms = GeometryEngine.divide_line_geometries(line_geom, step_length=3.0)
        self.assertEqual(len(sub_geoms), 4)
        self.assertAlmostEqual(sub_geoms[0].length(), 3.0, places=4)
        self.assertAlmostEqual(sub_geoms[1].length(), 3.0, places=4)
        self.assertAlmostEqual(sub_geoms[2].length(), 3.0, places=4)
        self.assertAlmostEqual(sub_geoms[3].length(), 1.0, places=4)

    def test_divide_line_reverse_direction(self):
        """Test dividing with reversed direction starting from opposite endpoint."""
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 0.0)])

        sub_geoms = GeometryEngine.divide_line_geometries(line_geom, step_length=3.0, reverse_direction=True)
        self.assertEqual(len(sub_geoms), 4)
        self.assertAlmostEqual(sub_geoms[0].length(), 3.0, places=4)
        self.assertAlmostEqual(sub_geoms[3].length(), 1.0, places=4)

        # First segment should be from (10, 0) to (7, 0)
        pts0 = sub_geoms[0].asPolyline()
        self.assertAlmostEqual(pts0[0].x(), 10.0, places=4)
        self.assertAlmostEqual(pts0[1].x(), 7.0, places=4)

    def test_get_division_points(self):
        """Test calculation of division cut points along the line."""
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 0.0)])

        pts = GeometryEngine.get_division_points(line_geom, count=4)
        self.assertEqual(len(pts), 3)
        self.assertAlmostEqual(pts[0].x(), 2.5, places=4)
        self.assertAlmostEqual(pts[1].x(), 5.0, places=4)
        self.assertAlmostEqual(pts[2].x(), 7.5, places=4)

    def test_canvas_move_uses_existing_snapping_helper(self):
        """Hover selection uses the shared segment snapping API without crashing."""
        self.line_layer.startEditing()
        feature = QgsFeature()
        feature.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0.0, 0.0), QgsPointXY(100.0, 0.0)]
            )
        )
        self.assertTrue(self.line_layer.addFeature(feature))
        feature = next(self.line_layer.getFeatures())
        self.canvas.setCurrentLayer(self.line_layer)

        widget = DivideLineCanvasWidget(self.canvas)
        tool = CADDivideLineMapTool(self.canvas, widget, self.iface)
        map_point = QgsPointXY(50.0, 0.0)
        event = SimpleNamespace(mapPoint=lambda: map_point)

        try:
            with patch.object(
                SnappingHelper,
                "find_segment_at_position",
                return_value=SimpleNamespace(fid=feature.id()),
            ) as find_segment:
                tool.canvasMoveEvent(event)

            find_segment.assert_called_once_with(
                self.line_layer,
                self.canvas,
                map_point,
            )
            self.assertIsNotNone(tool.hovered_feature)
            self.assertEqual(tool.hovered_feature.id(), feature.id())
        finally:
            tool.deactivate()
            widget.deleteLater()
            self.line_layer.rollBack()

    def test_widget_modes_and_restoration(self):
        """Test DivideLineCanvasWidget mutual exclusion and value restoration."""
        widget = DivideLineCanvasWidget(self.canvas)
        widget.chk_count.setChecked(True)
        widget.chk_length.setChecked(False)
        widget.spin_count.setValue(6)

        # Unchecking count automatically enables length
        widget.chk_count.setChecked(False)
        self.assertTrue(widget.chk_length.isChecked())
        self.assertEqual(widget.mode, DivideLineMode.SegmentLength)

        # Re-enabling count restores user value 6
        widget.chk_count.setChecked(True)
        self.assertEqual(widget.spin_count.value(), 6)

        # Verify top-right positioning
        self.canvas.resize(800, 600)
        widget.reposition_to_default()
        self.assertEqual(widget.y(), 0)
        self.assertGreaterEqual(widget.x(), 0)

    def test_map_tool_commit_separate_and_undo(self):
        """Test CADDivideLineMapTool execution with separate features output and undo."""
        self.line_layer.startEditing()

        feat = QgsFeature()
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0.0, 0.0), QgsPointXY(100.0, 0.0)])
        feat.setGeometry(line_geom)
        self.line_layer.addFeature(feat)
        self.assertEqual(self.line_layer.featureCount(), 1)

        self.canvas.setCurrentLayer(self.line_layer)

        widget = DivideLineCanvasWidget(self.canvas)
        widget.chk_count.setChecked(True)
        widget.chk_length.setChecked(False)
        tool = CADDivideLineMapTool(self.canvas, widget, self.iface)

        tool.selected_feature = list(self.line_layer.getFeatures())[0]
        tool.selected_layer = self.line_layer
        widget.spin_count.setValue(5)
        widget.chk_separate_features.setChecked(True)

        tool.commit_divide()

        # Original feature replaced by 5 separate features
        self.assertEqual(self.line_layer.featureCount(), 5)

        # Test Undo
        self.line_layer.undoStack().undo()
        self.assertEqual(self.line_layer.featureCount(), 1)

        # Test Redo
        self.line_layer.undoStack().redo()
        self.assertEqual(self.line_layer.featureCount(), 5)

        self.line_layer.rollBack()

    def test_map_tool_commit_multipart(self):
        """Test CADDivideLineMapTool with MultiLineString output on a MultiLineString layer."""
        multi_layer = QgsVectorLayer("MultiLineString?crs=EPSG:3857", "TestMultiLines", "memory")
        QgsProject.instance().addMapLayers([multi_layer])
        multi_layer.startEditing()

        feat = QgsFeature()
        line_geom = QgsGeometry.fromMultiPolylineXY([[QgsPointXY(0.0, 0.0), QgsPointXY(60.0, 0.0)]])
        feat.setGeometry(line_geom)
        multi_layer.addFeature(feat)
        self.assertEqual(multi_layer.featureCount(), 1)

        self.canvas.setCurrentLayer(multi_layer)

        widget = DivideLineCanvasWidget(self.canvas)
        widget.update_layer_capabilities(multi_layer)
        widget.chk_count.setChecked(True)
        widget.chk_length.setChecked(False)
        tool = CADDivideLineMapTool(self.canvas, widget, self.iface)

        tool.selected_feature = list(multi_layer.getFeatures())[0]
        tool.selected_layer = multi_layer
        widget.spin_count.setValue(3)
        widget.chk_separate_features.setChecked(False)

        tool.commit_divide()

        # Single feature maintained, geometry is multipart
        self.assertEqual(multi_layer.featureCount(), 1)
        res_feat = list(multi_layer.getFeatures())[0]
        self.assertTrue(res_feat.geometry().isMultipart())
        self.assertEqual(len(res_feat.geometry().asMultiPolyline()), 3)

        multi_layer.rollBack()

    def test_plugin_initgui_unload_lifecycle(self):
        """Test plugin initGui, divide line action and unload cleanup."""
        plugin = FilletPlugin(self.iface)
        plugin.initGui()

        self.assertIsNotNone(plugin.divide_line_action)
        self.assertIsNotNone(plugin.divide_line_map_tool)
        self.assertIsNotNone(plugin.divide_line_widget)

        # Toggle tool
        plugin.toggle_divide_line_tool(True)
        self.assertEqual(self.canvas.mapTool(), plugin.divide_line_map_tool)

        plugin.toggle_divide_line_tool(False)
        self.assertNotEqual(self.canvas.mapTool(), plugin.divide_line_map_tool)

        plugin.unload()
        self.assertIsNone(plugin.divide_line_action)
        self.assertIsNone(plugin.divide_line_widget)


if __name__ == "__main__":
    unittest.main()

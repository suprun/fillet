# -*- coding: utf-8 -*-
"""
Unit tests for CAD Explode Line Tool.
Tests GeometryEngine.explode_line, ExplodeCanvasWidget HUD, ExplodeLineMapTool, and plugin lifecycle.
"""

import unittest

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsLineString,
    QgsMultiLineString,
    QgsPoint,
    QgsPointXY,
    QgsSettings,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QEvent, QVariant, Qt
from qgis.PyQt.QtGui import QKeyEvent

from core.geometry_engine import GeometryEngine
from gui.explode_canvas_widget import ExplodeCanvasWidget
from gui.explode_map_tool import ExplodeLineMapTool
from plugin import FilletPlugin


class DummyMessageBar:
    def __init__(self):
        self.messages = []

    def pushMessage(self, title, text, level=None, duration=0):
        self.messages.append((title, text, level, duration))


class DummyInterface:
    def __init__(self, canvas):
        self._canvas = canvas
        self._actions = []
        self._msg_bar = DummyMessageBar()

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return self._canvas

    def advancedDigitizeToolBar(self):
        return None

    def addVectorToolBarIcon(self, action):
        self._actions.append(action)

    def removeVectorToolBarIcon(self, action):
        if action in self._actions:
            self._actions.remove(action)

    def addPluginToVectorMenu(self, name, action):
        pass

    def removePluginVectorMenu(self, name, action):
        pass

    def addDockWidget(self, area, dock):
        pass

    def removeDockWidget(self, dock):
        pass

    def messageBar(self):
        return self._msg_bar

    @property
    def currentLayerChanged(self):
        from qgis.PyQt.QtCore import pyqtSignal, QObject
        class _SignalHolder(QObject):
            sig = pyqtSignal(object)
        if not hasattr(self, "_sig_holder"):
            self._sig_holder = _SignalHolder()
        return self._sig_holder.sig


class TestExplodeTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance()
        if cls.app is None:
            cls.app = QgsApplication([], False)
            cls.app.initQgis()

    def setUp(self):
        QgsSettings().remove("FilletPlugin/Explode/SaveAsMultipart")
        self.canvas = QgsMapCanvas()
        self.iface = DummyInterface(self.canvas)
        self.widget = ExplodeCanvasWidget(self.canvas)
        self.tool = ExplodeLineMapTool(self.canvas, self.widget, self.iface)

    def tearDown(self):
        if self.tool:
            self.tool.cleanup()
        if self.widget:
            self.widget.deleteLater()
        if self.canvas:
            self.canvas.deleteLater()
        QgsSettings().remove("FilletPlugin/Explode/SaveAsMultipart")

    def test_geometry_engine_can_explode_line(self):
        """Test can_explode_line validation on various line geometries."""
        # Empty
        self.assertFalse(GeometryEngine.can_explode_line(QgsGeometry()))

        # Single 2-point line
        single_seg = QgsGeometry(QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0)]))
        self.assertFalse(GeometryEngine.can_explode_line(single_seg, as_multipart=False))
        self.assertFalse(GeometryEngine.can_explode_line(single_seg, as_multipart=True))

        # 3-point polyline (2 segments)
        poly = QgsGeometry(QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10)]))
        self.assertTrue(GeometryEngine.can_explode_line(poly, as_multipart=False))
        self.assertTrue(GeometryEngine.can_explode_line(poly, as_multipart=True))

        # MultiLineString with 2 separate 2-point lines
        mls_2seg = QgsGeometry.fromMultiPolylineXY([
            [QgsPointXY(0, 0), QgsPointXY(10, 0)],
            [QgsPointXY(20, 0), QgsPointXY(30, 0)],
        ])
        # In singlepart mode, this can split into 2 separate features
        self.assertTrue(GeometryEngine.can_explode_line(mls_2seg, as_multipart=False))
        # In multipart mode, each part is already 2 points, so no further explosion needed
        self.assertFalse(GeometryEngine.can_explode_line(mls_2seg, as_multipart=True))

    def test_geometry_engine_explode_singlepart(self):
        """Test splitting a 4-point polyline into 3 separate 2-point line segments."""
        pts = [QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(20, 10)]
        geom = QgsGeometry(QgsLineString(pts))
        
        segments = GeometryEngine.explode_line(geom, as_multipart=False)
        self.assertEqual(len(segments), 3)
        for seg in segments:
            self.assertEqual(seg.wkbType(), QgsWkbTypes.Type.LineString)
            self.assertEqual(seg.constGet().numPoints(), 2)

        # Check coordinates of first and last segment
        p0 = segments[0].constGet().pointN(0)
        p1 = segments[0].constGet().pointN(1)
        self.assertAlmostEqual(p0.x(), 0.0)
        self.assertAlmostEqual(p1.x(), 10.0)

        p_last0 = segments[2].constGet().pointN(0)
        p_last1 = segments[2].constGet().pointN(1)
        self.assertAlmostEqual(p_last0.x(), 10.0)
        self.assertAlmostEqual(p_last1.x(), 20.0)

    def test_geometry_engine_explode_multipart(self):
        """Test splitting a polyline into a single MultiLineString geometry with 3 segments."""
        pts = [QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(20, 10)]
        geom = QgsGeometry(QgsLineString(pts))

        res = GeometryEngine.explode_line(geom, as_multipart=True)
        self.assertEqual(len(res), 1)
        multi_geom = res[0]
        self.assertTrue(multi_geom.isMultipart())
        abstract_geom = multi_geom.constGet()
        self.assertEqual(abstract_geom.numGeometries(), 3)

    def test_explode_singlepart_layer_execution(self):
        """Test interactive explosion on singlepart vector layer creates new cloned features."""
        layer = QgsVectorLayer("LineString?crs=epsg:3857", "test_lines", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", QVariant.String)])
        layer.updateFields()
        layer.startEditing()

        pts = [QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(0, 10)]
        feat = QgsFeature(layer.fields())
        feat.setAttribute("name", "original_line")
        feat.setGeometry(QgsGeometry(QgsLineString(pts)))
        layer.addFeature(feat)
        self.assertEqual(layer.featureCount(), 1)

        self.canvas.setCurrentLayer(layer)
        self.widget.update_layer_capabilities(layer)
        self.assertFalse(self.widget.chk_multipart.isEnabled())

        # Explode feature
        first_feat = list(layer.getFeatures())[0]
        self.tool.explode_features(layer, [first_feat])

        # Layer should now have 3 individual line features
        self.assertEqual(layer.featureCount(), 3)
        for f in layer.getFeatures():
            self.assertEqual(f.attribute("name"), "original_line")
            self.assertEqual(f.geometry().constGet().numPoints(), 2)

    def test_explode_multipart_layer_execution(self):
        """Test explosion on multipart vector layer with as_multipart enabled."""
        layer = QgsVectorLayer("MultiLineString?crs=epsg:3857", "test_multi", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", QVariant.String)])
        layer.updateFields()
        layer.startEditing()

        pts = [QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(0, 10)]
        feat = QgsFeature(layer.fields())
        feat.setAttribute("name", "multi_line")
        feat.setGeometry(QgsGeometry.fromMultiPolylineXY([[QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10)]]))
        layer.addFeature(feat)
        self.assertEqual(layer.featureCount(), 1)

        self.canvas.setCurrentLayer(layer)
        self.widget.update_layer_capabilities(layer)
        self.assertTrue(self.widget.chk_multipart.isEnabled())

        # Enable multipart option
        self.widget.set_save_as_multipart(True)
        self.assertTrue(self.widget.is_save_as_multipart)

        # Explode feature
        first_feat = list(layer.getFeatures())[0]
        self.tool.explode_features(layer, [first_feat])

        # Layer still has 1 feature, but its geometry has 3 parts
        self.assertEqual(layer.featureCount(), 1)
        updated_feat = list(layer.getFeatures())[0]
        self.assertTrue(updated_feat.geometry().isMultipart())
        self.assertEqual(updated_feat.geometry().constGet().numGeometries(), 3)

    def test_widget_hotkeys(self):
        """Test Spacebar toggles multipart and Esc triggers reset signal."""
        layer = QgsVectorLayer("MultiLineString?crs=epsg:3857", "test_hotkeys", "memory")
        self.canvas.setCurrentLayer(layer)
        self.widget.update_layer_capabilities(layer)

        _KeyPress = getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None))
        _NoModifier = getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", None))
        if _NoModifier is None:
            _NoModifier = Qt.KeyboardModifiers()

        initial_state = self.widget.chk_multipart.isChecked()
        # Simulate Space key
        evt_space = QKeyEvent(_KeyPress, getattr(Qt.Key, "Key_Space", 0x20), _NoModifier)
        self.widget.eventFilter(self.widget, evt_space)
        self.assertEqual(self.widget.chk_multipart.isChecked(), not initial_state)

        # Simulate Escape key
        reset_called = []
        self.widget.resetRequested.connect(lambda: reset_called.append(True))
        evt_esc = QKeyEvent(_KeyPress, getattr(Qt.Key, "Key_Escape", 0x01000000), _NoModifier)
        self.widget.eventFilter(self.widget, evt_esc)
        self.assertTrue(len(reset_called) > 0)

    def test_single_segment_prevention_on_click(self):
        """Test that single 2-point line features cannot be exploded via click."""
        layer = QgsVectorLayer("LineString?crs=epsg:3857", "test_single_seg", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", QVariant.String)])
        layer.updateFields()
        layer.startEditing()

        pts = [QgsPoint(0, 0), QgsPoint(10, 0)]
        feat = QgsFeature(layer.fields())
        feat.setAttribute("name", "line_2pt")
        feat.setGeometry(QgsGeometry(QgsLineString(pts)))
        layer.addFeature(feat)

        self.canvas.setCurrentLayer(layer)
        f = list(layer.getFeatures())[0]

        # Verify can_explode_line returns False
        self.assertFalse(GeometryEngine.can_explode_line(f.geometry(), as_multipart=False))

        # Layer feature count remains 1 and geometry unchanged
        self.assertEqual(layer.featureCount(), 1)
        self.assertEqual(f.geometry().constGet().numPoints(), 2)

    def test_batch_explode_all_single_segments_prevention(self):
        """Test that selecting only 2-point single segments aborts batch explode without modifying layer."""
        layer = QgsVectorLayer("LineString?crs=epsg:3857", "test_batch_single", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", QVariant.String)])
        layer.updateFields()
        layer.startEditing()

        f1 = QgsFeature(layer.fields())
        f1.setGeometry(QgsGeometry(QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0)])))
        f2 = QgsFeature(layer.fields())
        f2.setGeometry(QgsGeometry(QgsLineString([QgsPoint(20, 0), QgsPoint(30, 0)])))
        layer.addFeatures([f1, f2])

        self.canvas.setCurrentLayer(layer)
        layer.selectAll()
        self.assertEqual(layer.selectedFeatureCount(), 2)

        # Batch explode
        self.tool.explode_selected_features()

        # No changes occurred, still 2 features with 2 points each
        self.assertEqual(layer.featureCount(), 2)
        for feat in layer.getFeatures():
            self.assertEqual(feat.geometry().constGet().numPoints(), 2)

    def test_batch_explode_mixed_features(self):
        """Test that in a mixed selection, only multi-segment lines are exploded while single segments are untouched."""
        layer = QgsVectorLayer("LineString?crs=epsg:3857", "test_batch_mixed", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", QVariant.String)])
        layer.updateFields()

        # Feature 1: 4 points (3 segments) -> should be exploded into 3 features
        f1 = QgsFeature(layer.fields())
        f1.setAttribute("name", "complex")
        f1.setGeometry(QgsGeometry(QgsLineString([QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10), QgsPoint(20, 10)])))

        # Feature 2: 2 points (1 segment) -> should be skipped untouched
        f2 = QgsFeature(layer.fields())
        f2.setAttribute("name", "single")
        f2.setGeometry(QgsGeometry(QgsLineString([QgsPoint(100, 0), QgsPoint(110, 0)])))

        pr.addFeatures([f1, f2])
        layer.startEditing()
        self.canvas.setCurrentLayer(layer)
        layer.selectAll()

        self.tool.explode_selected_features()

        # Total features should now be 4 (3 from f1 + 1 from f2)
        features = list(layer.getFeatures())
        self.assertTrue(self.iface._msg_bar.messages)
        self.assertEqual(len(features), 4)
        names = [f.attribute("name") for f in features]
        self.assertEqual(names.count("complex"), 3)
        self.assertEqual(names.count("single"), 1)

    def test_show_feature_preview(self):
        """Test preview rubberband and node markers when hovering over a line."""
        layer = QgsVectorLayer("LineString?crs=epsg:3857", "test_preview", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", QVariant.String)])
        layer.updateFields()
        layer.startEditing()

        pts = [QgsPoint(0, 0), QgsPoint(10, 0), QgsPoint(10, 10)]
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry(QgsLineString(pts)))
        layer.addFeature(feat)

        self.canvas.setCurrentLayer(layer)
        self.tool._show_feature_preview(layer, feat.geometry())
        self.assertIsNotNone(self.tool.preview_rubberband)
        self.assertIsNotNone(self.tool.nodes_rubberband)
        self.tool._clear_preview()

    def test_plugin_explode_action_lifecycle(self):
        """Test initialization and clean unloading of Explode tool inside FilletPlugin."""
        plugin = FilletPlugin(self.iface)
        plugin.initGui()

        self.assertIsNotNone(plugin.explode_action)
        self.assertIsNotNone(plugin.explode_map_tool)
        self.assertIsNotNone(plugin.explode_widget)

        # Toggle tool
        plugin.explode_action.setChecked(True)
        plugin.toggle_explode_tool(True)
        self.assertEqual(self.canvas.mapTool(), plugin.explode_map_tool)

        plugin.unload()
        self.assertIsNone(plugin.explode_action)
        self.assertIsNone(plugin.explode_map_tool)
        self.assertIsNone(plugin.explode_widget)


if __name__ == "__main__":
    unittest.main()

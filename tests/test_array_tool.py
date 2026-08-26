# -*- coding: utf-8 -*-
"""
Tests for CAD Copy Features in an Array tool (CADArrayMapTool, ArrayCanvasWidget, and ArrayMode).
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPoint,
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

from gui.array_canvas_widget import ArrayCanvasWidget, ArrayMode
from gui.array_map_tool import CADArrayMapTool
from plugin import FilletPlugin


class MockMessageBar(QObject):
    def __init__(self):
        super().__init__()
        self.messages = []

    def pushMessage(self, title, text, level=0, duration=0):
        self.messages.append((title, text, level, duration))


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


class TestCADArrayTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canvas = QgsMapCanvas()

    @classmethod
    def tearDownClass(cls):
        cls.canvas = None

    def test_widget_two_checkboxes_logic_and_modes(self):
        """Test HUD panel checkbox interdependency and mode transitions."""
        widget = ArrayCanvasWidget(self.canvas)

        modes_received = []
        counts_received = []
        spacings_received = []

        widget.modeChanged.connect(modes_received.append)
        widget.featureCountChanged.connect(counts_received.append)
        widget.featureSpacingChanged.connect(spacings_received.append)

        # 1. Default state: Count is checked, Spacing is unchecked -> FeatureCount mode
        widget.setMode(ArrayMode.FeatureCount)
        self.assertEqual(widget.mode(), ArrayMode.FeatureCount)
        self.assertTrue(widget.chk_count.isChecked())
        self.assertFalse(widget.chk_spacing.isChecked())
        self.assertTrue(widget.spin_count.isEnabled())
        self.assertFalse(widget.spin_spacing.isEnabled())

        # 2. Check Spacing -> Mode becomes FeatureCountAndSpacing
        widget.chk_spacing.setChecked(True)
        self.assertEqual(widget.mode(), ArrayMode.FeatureCountAndSpacing)
        self.assertTrue(widget.chk_count.isChecked())
        self.assertTrue(widget.chk_spacing.isChecked())
        self.assertTrue(widget.spin_count.isEnabled())
        self.assertTrue(widget.spin_spacing.isEnabled())

        # 3. Uncheck Count -> Mode becomes FeatureSpacing
        widget.chk_count.setChecked(False)
        self.assertEqual(widget.mode(), ArrayMode.FeatureSpacing)
        self.assertFalse(widget.chk_count.isChecked())
        self.assertTrue(widget.chk_spacing.isChecked())
        self.assertFalse(widget.spin_count.isEnabled())
        self.assertTrue(widget.spin_spacing.isEnabled())

        # 4. Attempt to uncheck Spacing while Count is already False
        # Rule: At least one checkbox must always remain checked -> Automatically checks Count
        widget.chk_spacing.setChecked(False)
        self.assertTrue(widget.chk_count.isChecked() or widget.chk_spacing.isChecked())
        self.assertEqual(widget.mode(), ArrayMode.FeatureCount)
        self.assertTrue(widget.chk_count.isChecked())
        self.assertFalse(widget.chk_spacing.isChecked())

        # 5. Programmatic setMode()
        widget.setMode(ArrayMode.FeatureSpacing)
        self.assertEqual(widget.mode(), ArrayMode.FeatureSpacing)
        self.assertFalse(widget.chk_count.isChecked())
        self.assertTrue(widget.chk_spacing.isChecked())

        widget.setMode(ArrayMode.FeatureCountAndSpacing)
        self.assertEqual(widget.mode(), ArrayMode.FeatureCountAndSpacing)
        self.assertTrue(widget.chk_count.isChecked())
        self.assertTrue(widget.chk_spacing.isChecked())

        # 6. Values & dynamic calculated setters
        widget.setFeatureCount(5)
        self.assertEqual(widget.featureCount(), 5)
        widget.setFeatureSpacing(2.5)
        self.assertAlmostEqual(widget.featureSpacing(), 2.5)

        # Dynamic calculated value updates when field is disabled
        widget.setMode(ArrayMode.FeatureCount)  # Spacing disabled
        widget.set_calculated_spacing(3.75)
        self.assertAlmostEqual(widget.spin_spacing.value(), 3.75)

        widget.setMode(ArrayMode.FeatureSpacing)  # Count disabled
        widget.set_calculated_count(8)
        self.assertEqual(widget.spin_count.value(), 8)

        # 7. Step text and CRS adaptation
        widget.set_step(ArrayCanvasWidget.STEP_START)
        self.assertIn("1.", widget.lbl_step.text())
        widget.set_step(ArrayCanvasWidget.STEP_END)
        self.assertIn("2.", widget.lbl_step.text())

        geo_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        widget.adapt_to_crs(geo_crs)
        self.assertEqual(widget.spin_spacing.decimals(), 6)

        metric_crs = QgsCoordinateReferenceSystem("EPSG:3857")
        widget.adapt_to_crs(metric_crs)
        self.assertEqual(widget.spin_spacing.decimals(), 3)

    def test_feature_count_and_spacing_calculations(self):
        """Test mathematical count and spacing derivations across modes."""
        widget = ArrayCanvasWidget(self.canvas)
        tool = CADArrayMapTool(self.canvas, widget)

        tool.startPointMapCoords = QgsPointXY(0, 0)
        tool.endPointMapCoords = QgsPointXY(10, 0)  # Length = 10

        # Mode 0: FeatureCount = 4 -> Spacing should be 10 / 4 = 2.5
        tool.setMode(ArrayMode.FeatureCount)
        tool.setFeatureCount(4)
        self.assertEqual(tool.featureCount(), 4)
        self.assertAlmostEqual(tool.featureSpacing(), 2.5)

        # Mode 1: FeatureSpacing = 3.0 -> Count should be floor(10 / 3) = 3
        tool.setMode(ArrayMode.FeatureSpacing)
        tool.setFeatureSpacing(3.0)
        self.assertAlmostEqual(tool.featureSpacing(), 3.0)
        self.assertEqual(tool.featureCount(), 3)

        # Mode 2: Count = 5, Spacing = 2.0 -> Both are fixed
        tool.setMode(ArrayMode.FeatureCountAndSpacing)
        tool.setFeatureCount(5)
        tool.setFeatureSpacing(2.0)
        self.assertEqual(tool.featureCount(), 5)
        self.assertAlmostEqual(tool.featureSpacing(), 2.0)

    def test_first_feature_map_point(self):
        """Test calculation of step vector along reference line."""
        widget = ArrayCanvasWidget(self.canvas)
        tool = CADArrayMapTool(self.canvas, widget)

        tool.startPointMapCoords = QgsPointXY(0, 0)
        tool.endPointMapCoords = QgsPointXY(0, 10)  # Vertical line length 10

        # Mode 0: Count 2 -> spacing = 5
        tool.setMode(ArrayMode.FeatureCount)
        tool.setFeatureCount(2)
        p1 = tool.firstFeatureMapPoint()
        self.assertAlmostEqual(p1.x(), 0.0)
        self.assertAlmostEqual(p1.y(), 5.0)

        # Diagonal line: (0, 0) to (10, 10), length = sqrt(200) ≈ 14.142
        tool.endPointMapCoords = QgsPointXY(10, 10)
        tool.setMode(ArrayMode.FeatureSpacing)
        tool.setFeatureSpacing(math.sqrt(2.0))  # step = (1, 1)
        p_diag = tool.firstFeatureMapPoint()
        self.assertAlmostEqual(p_diag.x(), 1.0)
        self.assertAlmostEqual(p_diag.y(), 1.0)

    def test_array_creation_points(self):
        """Test array duplication on Point vector layer."""
        layer = QgsVectorLayer("Point?crs=EPSG:3857", "test_points", "memory")
        pr = layer.dataProvider()
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(100, 200)))
        pr.addFeatures([f])

        self.canvas.setCurrentLayer(layer)
        layer.startEditing()
        layer.selectAll()

        widget = ArrayCanvasWidget(self.canvas)
        tool = CADArrayMapTool(self.canvas, widget)
        tool.setMode(ArrayMode.FeatureCount)
        tool.setFeatureCount(3)

        # Simulate clicks: start at (100, 200), end at (100, 500) -> dy = 100 per feature
        tool.featureList = list(layer.getFeatures())
        tool.featureLayer = layer
        tool.startPointMapCoords = QgsPointXY(100, 200)
        tool.endPointMapCoords = QgsPointXY(100, 500)

        # Call tool.commit_array() directly to test complete execution path
        tool.commit_array()

        # Check resulting count and coordinates
        self.assertEqual(layer.featureCount(), 4)
        all_pts = [f.geometry().asPoint() for f in layer.getFeatures()]
        y_coords = sorted([p.y() for p in all_pts])
        self.assertEqual(y_coords, [200.0, 300.0, 400.0, 500.0])

        # Test Undo
        layer.undoStack().undo()
        self.assertEqual(layer.featureCount(), 1)

    def test_array_creation_polygons_multi_feature(self):
        """Test array duplication of multiple selected polygon features."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "test_polys", "memory")
        pr = layer.dataProvider()

        # Poly 1 at (0, 0)-(10, 10)
        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)]]))
        # Poly 2 at (20, 0)-(30, 10)
        f2 = QgsFeature()
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(20, 0), QgsPointXY(30, 0), QgsPointXY(30, 10), QgsPointXY(20, 10), QgsPointXY(20, 0)]]))
        pr.addFeatures([f1, f2])

        layer.startEditing()
        layer.selectAll()

        widget = ArrayCanvasWidget(self.canvas)
        tool = CADArrayMapTool(self.canvas, widget)
        tool.featureList = list(layer.getFeatures())
        tool.featureLayer = layer
        tool.setMode(ArrayMode.FeatureCountAndSpacing)
        tool.setFeatureCount(2)
        tool.setFeatureSpacing(50.0)

        # Direction vector along X-axis
        tool.startPointMapCoords = QgsPointXY(0, 0)
        tool.endPointMapCoords = QgsPointXY(100, 0)

        # Execute complete commit logic
        tool.commit_array()

        # Original: 2, Added: 2 * 2 = 4 -> Total: 6
        self.assertEqual(layer.featureCount(), 6)

    def test_plugin_lifecycle_and_qgis4_condition(self):
        """Test array tool creation on QGIS 3.x and omission on QGIS 4.+."""
        win = QMainWindow()
        tb = QToolBar("Digitize", win)
        win.addToolBar(tb)
        iface = MockIface(win, self.canvas, tb)
        plugin = FilletPlugin(iface)

        if plugin.is_qgis_4():
            plugin.initGui()
            # In QGIS 4.+, array_action must NOT be created
            self.assertIsNone(plugin.array_action)
            self.assertIsNone(plugin.array_map_tool)
            plugin.unload()
        else:
            plugin.initGui()
            # In QGIS 3.x, array_action and tools MUST be created
            self.assertIsNotNone(plugin.array_action)
            self.assertIsNotNone(plugin.array_map_tool)
            self.assertIsNotNone(plugin.array_widget)

            # Test layer states
            layer = QgsVectorLayer("Point?crs=EPSG:3857", "test_pt", "memory")
            self.canvas.setCurrentLayer(layer)
            plugin.update_action_state()
            self.assertFalse(plugin.array_action.isEnabled())

            layer.startEditing()
            plugin.update_action_state()
            self.assertTrue(plugin.array_action.isEnabled())

            layer.rollBack()
            plugin.update_action_state()
            self.assertFalse(plugin.array_action.isEnabled())

            plugin.unload()
            self.assertIsNone(plugin.array_action)
            self.assertIsNone(plugin.array_map_tool)
            self.assertIsNone(plugin.array_widget)

    def test_stepper_value_restoration_on_reenable(self):
        """Test that disabled spinbox values overwritten by live calculation restore user values when re-enabled."""
        widget = ArrayCanvasWidget(self.canvas)

        # 1. User sets Count = 7 and Spacing = 15.0 in FeatureCountAndSpacing mode
        widget.setMode(ArrayMode.FeatureCountAndSpacing)
        widget.spin_count.setValue(7)
        widget.spin_spacing.setValue(15.0)
        self.assertEqual(widget.spin_count.value(), 7)
        self.assertAlmostEqual(widget.spin_spacing.value(), 15.0)

        # 2. Switch to FeatureSpacing (Count becomes disabled)
        widget.setMode(ArrayMode.FeatureSpacing)
        self.assertFalse(widget.chk_count.isChecked())
        self.assertTrue(widget.chk_spacing.isChecked())
        self.assertFalse(widget.spin_count.isEnabled())

        # Live calculation overwrites spin_count to 42 while moving mouse
        widget.set_calculated_count(42)
        self.assertEqual(widget.spin_count.value(), 42)

        # Re-enable Count checkbox -> Must restore 7!
        widget.chk_count.setChecked(True)
        self.assertTrue(widget.spin_count.isEnabled())
        self.assertEqual(widget.spin_count.value(), 7)

        # 3. Switch to FeatureCount (Spacing becomes disabled)
        widget.setMode(ArrayMode.FeatureCount)
        self.assertTrue(widget.chk_count.isChecked())
        self.assertFalse(widget.chk_spacing.isChecked())
        self.assertFalse(widget.spin_spacing.isEnabled())

        # Live calculation overwrites spin_spacing to 99.5 while moving mouse
        widget.set_calculated_spacing(99.5)
        self.assertAlmostEqual(widget.spin_spacing.value(), 99.5)

        # Re-enable Spacing checkbox -> Must restore 15.0!
        widget.chk_spacing.setChecked(True)
        self.assertTrue(widget.spin_spacing.isEnabled())
        self.assertAlmostEqual(widget.spin_spacing.value(), 15.0)

    def test_extent_check_logic(self):
        """Test confirmation utility with features inside and outside canvas extent."""
        from gui.gui_utils import confirm_features_in_canvas_extent

        layer = QgsVectorLayer("Point?crs=EPSG:3857", "test_ext", "memory")
        pr = layer.dataProvider()
        f_inside = QgsFeature()
        f_inside.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(10, 10)))
        pr.addFeatures([f_inside])

        # Feature inside canvas extent -> confirm returns True without dialog
        self.assertTrue(confirm_features_in_canvas_extent(self.canvas, layer, [f_inside], "CAD Feature Array"))


if __name__ == "__main__":
    unittest.main()

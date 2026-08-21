# -*- coding: utf-8 -*-
"""Test plugin initGui, unload lifecycle, and action enablement based on layer editing mode."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qgis.core import QgsApplication, QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import pyqtSignal, QObject
from qgis.PyQt.QtWidgets import QMainWindow, QDockWidget, QToolBar

app = QgsApplication([], False)
app.initQgis()

win = QMainWindow()
canvas = QgsMapCanvas(win)
tb = QToolBar("Digitize", win)
win.addToolBar(tb)


class MockIface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def mainWindow(self):
        return win

    def mapCanvas(self):
        return canvas

    def advancedDigitizeToolBar(self):
        return tb

    def addVectorToolBarIcon(self, a):
        tb.addAction(a)

    def removeVectorToolBarIcon(self, a):
        tb.removeAction(a)

    def addPluginToVectorMenu(self, n, a):
        pass

    def removePluginVectorMenu(self, n, a):
        pass

    def addDockWidget(self, area, d):
        win.addDockWidget(area, d)

    def removeDockWidget(self, d):
        win.removeDockWidget(d)

    def currentLayer(self):
        return canvas.currentLayer()


from plugin import FilletPlugin


class TestPluginLifecycleAndEditState(unittest.TestCase):
    def setUp(self):
        self.iface = MockIface()
        self.plugin = FilletPlugin(self.iface)
        self.plugin.initGui()

    def tearDown(self):
        self.plugin.unload()
        app.processEvents()
        canvas.setCurrentLayer(None)

    def test_dock_lifecycle_no_duplicates(self):
        """Test repeated initGui/unload cycles do not leave duplicate docks."""
        self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 1)
        self.plugin.unload()
        app.processEvents()
        self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 0)

        # Reload
        self.plugin = FilletPlugin(self.iface)
        self.plugin.initGui()
        self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 1)

    def test_actions_disabled_when_no_layer(self):
        """Actions must be disabled when there is no active layer."""
        canvas.setCurrentLayer(None)
        self.iface.currentLayerChanged.emit(None)
        self.plugin.update_action_state()

        if self.plugin.action:
            self.assertFalse(self.plugin.action.isEnabled())
        if self.plugin.batch_action:
            self.assertFalse(self.plugin.batch_action.isEnabled())
        self.assertFalse(self.plugin.settings_widget.btn_apply_selected.isEnabled())

    def test_actions_disabled_when_layer_not_editable(self):
        """Actions must remain disabled for a vector layer that is NOT in editing mode."""
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "temp_lines", "memory")
        self.assertTrue(layer.isValid())
        self.assertFalse(layer.isEditable())

        canvas.setCurrentLayer(layer)
        self.iface.currentLayerChanged.emit(layer)

        if self.plugin.action:
            self.assertFalse(self.plugin.action.isEnabled())
        if self.plugin.batch_action:
            self.assertFalse(self.plugin.batch_action.isEnabled())
        self.assertFalse(self.plugin.settings_widget.btn_apply_selected.isEnabled())

    def test_actions_enabled_when_editing_starts_and_disabled_on_stop(self):
        """Actions become enabled when editing starts and disabled when editing stops."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "temp_poly", "memory")
        self.assertTrue(layer.isValid())

        canvas.setCurrentLayer(layer)
        self.iface.currentLayerChanged.emit(layer)

        # 1. Not editable yet -> disabled
        if self.plugin.action:
            self.assertFalse(self.plugin.action.isEnabled())
        self.assertFalse(self.plugin.batch_action.isEnabled())

        # 2. Start editing -> enabled
        layer.startEditing()
        if self.plugin.action:
            self.assertTrue(self.plugin.action.isEnabled())
        self.assertTrue(self.plugin.batch_action.isEnabled())
        self.assertTrue(self.plugin.settings_widget.btn_apply_selected.isEnabled())

        # 3. Roll back (stop editing) -> disabled
        layer.rollBack()
        if self.plugin.action:
            self.assertFalse(self.plugin.action.isEnabled())
        self.assertFalse(self.plugin.batch_action.isEnabled())
        self.assertFalse(self.plugin.settings_widget.btn_apply_selected.isEnabled())

    def test_interactive_tool_auto_deactivation_on_editing_stop(self):
        """If interactive tool is active on map canvas, it must unset when layer stops editing."""
        if self.plugin.is_qgis_4():
            return  # Interactive tool only in QGIS 3.x

        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "temp_lines", "memory")
        layer.startEditing()
        canvas.setCurrentLayer(layer)
        self.iface.currentLayerChanged.emit(layer)

        # Activate map tool
        self.plugin.toggle_tool(True)
        self.assertEqual(canvas.mapTool(), self.plugin.map_tool)
        self.assertTrue(self.plugin.action.isChecked())

        # Stop editing
        layer.rollBack()

        # Tool should be automatically unset
        self.assertNotEqual(canvas.mapTool(), self.plugin.map_tool)
        self.assertFalse(self.plugin.action.isChecked())
        self.assertFalse(self.plugin.action.isEnabled())


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPluginLifecycleAndEditState)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if res.wasSuccessful() else 1)

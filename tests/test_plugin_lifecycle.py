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


class MockMessageBar(QObject):
    def __init__(self):
        super().__init__()
        self.messages = []

    def pushMessage(self, title, text, level=None, duration=0):
        self.messages.append({"title": title, "text": text, "level": level, "duration": duration})

    def pushInfo(self, title, text, duration=0):
        self.messages.append({"title": title, "text": text, "level": "info", "duration": duration})

    def pushWarning(self, title, text, duration=0):
        self.messages.append({"title": title, "text": text, "level": "warning", "duration": duration})

    def pushSuccess(self, title, text, duration=0):
        self.messages.append({"title": title, "text": text, "level": "success", "duration": duration})


class MockIface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._msg_bar = MockMessageBar()

    def mainWindow(self):
        return win

    def mapCanvas(self):
        return canvas

    def messageBar(self):
        return self._msg_bar

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
        if self.plugin.restore_action:
            self.assertFalse(self.plugin.restore_action.isEnabled())
        if self.plugin.rotate_action:
            self.assertFalse(self.plugin.rotate_action.isEnabled())
        if self.plugin.batch_action:
            self.assertFalse(self.plugin.batch_action.isEnabled())
        self.assertFalse(self.plugin.settings_widget.btn_apply_selected.isEnabled())

    def test_actions_enabled_when_editing_starts_and_disabled_on_stop(self):
        """Actions become enabled when editing starts, and rotate requires active selection."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "temp_poly", "memory")
        pr = layer.dataProvider()
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(1,0), QgsPointXY(1,1), QgsPointXY(0,1)]]))
        pr.addFeatures([feat])
        layer.updateExtents()
        self.assertTrue(layer.isValid())

        canvas.setCurrentLayer(layer)
        self.iface.currentLayerChanged.emit(layer)

        # 1. Not editable yet -> disabled
        if self.plugin.action:
            self.assertFalse(self.plugin.action.isEnabled())
        if self.plugin.restore_action:
            self.assertFalse(self.plugin.restore_action.isEnabled())
        if self.plugin.rotate_action:
            self.assertFalse(self.plugin.rotate_action.isEnabled())
        self.assertFalse(self.plugin.batch_action.isEnabled())

        # 2. Start editing with NO selection -> fillet/restore/batch enabled, rotate disabled
        layer.startEditing()
        if self.plugin.action:
            self.assertTrue(self.plugin.action.isEnabled())
        if self.plugin.restore_action:
            self.assertTrue(self.plugin.restore_action.isEnabled())
        if self.plugin.rotate_action:
            self.assertFalse(self.plugin.rotate_action.isEnabled())
        self.assertTrue(self.plugin.batch_action.isEnabled())
        self.assertTrue(self.plugin.settings_widget.btn_apply_selected.isEnabled())

        # 3. Select feature -> rotate action becomes ENABLED
        layer.selectByIds([1])
        if self.plugin.rotate_action:
            self.assertTrue(self.plugin.rotate_action.isEnabled())

        # 4. Deselect feature -> rotate action becomes DISABLED
        layer.removeSelection()
        if self.plugin.rotate_action:
            self.assertFalse(self.plugin.rotate_action.isEnabled())

        # 5. Roll back (stop editing) -> all disabled
        layer.rollBack()
        if self.plugin.action:
            self.assertFalse(self.plugin.action.isEnabled())
        if self.plugin.restore_action:
            self.assertFalse(self.plugin.restore_action.isEnabled())
        if self.plugin.rotate_action:
            self.assertFalse(self.plugin.rotate_action.isEnabled())
        self.assertFalse(self.plugin.batch_action.isEnabled())
        self.assertFalse(self.plugin.settings_widget.btn_apply_selected.isEnabled())

    def test_interactive_tool_auto_deactivation_on_editing_stop(self):
        """If interactive tool is active on map canvas, it must unset when layer stops editing or selection removed."""
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "temp_lines", "memory")
        pr = layer.dataProvider()
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0,0), QgsPointXY(1,0)]))
        pr.addFeatures([feat])
        layer.updateExtents()

        layer.startEditing()
        canvas.setCurrentLayer(layer)
        self.iface.currentLayerChanged.emit(layer)

        if not self.plugin.is_qgis_4():
            # Activate fillet map tool
            self.plugin.toggle_tool(True)
            self.assertEqual(canvas.mapTool(), self.plugin.map_tool)
            self.assertTrue(self.plugin.action.isChecked())

            # Stop editing
            layer.rollBack()
            self.assertNotEqual(canvas.mapTool(), self.plugin.map_tool)
            self.assertFalse(self.plugin.action.isChecked())
            self.assertFalse(self.plugin.action.isEnabled())

        # Test Restore tool deactivation
        layer.startEditing()
        self.plugin.toggle_restore_tool(True)
        self.assertEqual(canvas.mapTool(), self.plugin.restore_map_tool)
        self.assertTrue(self.plugin.restore_action.isChecked())

        layer.rollBack()
        self.assertNotEqual(canvas.mapTool(), self.plugin.restore_map_tool)
        self.assertFalse(self.plugin.restore_action.isChecked())
        self.assertFalse(self.plugin.restore_action.isEnabled())

        # Test Rotate tool deactivation when editing rolls back
        layer.startEditing()
        layer.selectByIds([1])
        self.plugin.toggle_rotate_tool(True)
        self.assertEqual(canvas.mapTool(), self.plugin.rotate_map_tool)
        self.assertTrue(self.plugin.rotate_action.isChecked())

        layer.rollBack()
        self.assertNotEqual(canvas.mapTool(), self.plugin.rotate_map_tool)
        self.assertFalse(self.plugin.rotate_action.isChecked())
        self.assertFalse(self.plugin.rotate_action.isEnabled())

        # Test Rotate tool deactivation when selection is removed while editing
        layer.startEditing()
        layer.selectByIds([1])
        self.plugin.toggle_rotate_tool(True)
        self.assertEqual(canvas.mapTool(), self.plugin.rotate_map_tool)
        self.assertTrue(self.plugin.rotate_action.isChecked())

        layer.removeSelection()
        self.assertNotEqual(canvas.mapTool(), self.plugin.rotate_map_tool)
        self.assertFalse(self.plugin.rotate_action.isChecked())
        self.assertFalse(self.plugin.rotate_action.isEnabled())

        layer.rollBack()

    def test_map_tool_preview_in_all_modes(self):
        """Verify that _update_preview works without errors in fillet and chamfer modes."""
        if self.plugin.is_qgis_4():
            return

        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
        from core.geometry_engine import GeometryEngine
        from gui.map_tool import VertexMatch

        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "temp_lines", "memory")
        pr = layer.dataProvider()
        feat = QgsFeature()
        geom = QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(0, 0), QgsPointXY(10, 0)])
        feat.setGeometry(geom)
        pr.addFeatures([feat])
        layer.updateExtents()
        layer.startEditing()
        canvas.setCurrentLayer(layer)
        self.iface.currentLayerChanged.emit(layer)

        tool = self.plugin.map_tool
        self.plugin.toggle_tool(True)
        match = VertexMatch(point=QgsPointXY(0, 0), vertex_idx=1, part_idx=0, ring_idx=0, fid=1, geometry=geom)
        tool.current_match = match

        # 1. Fillet mode
        self.plugin.canvas_widget.radio_fillet.setChecked(True)
        tool._update_preview()
        self.assertIsNotNone(tool.preview_geom)

        # 2. Chamfer mode
        self.plugin.canvas_widget.radio_chamfer.setChecked(True)
        tool._update_preview()
        self.assertIsNotNone(tool.preview_geom)

        layer.rollBack()

    def test_restore_map_tool_interaction(self):
        """Verify dedicated RestoreMapTool with Two-Edge CAD corner restoration."""
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
        from core.geometry_engine import GeometryEngine
        from core.snapping_helper import SegmentMatch

        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "temp_lines", "memory")
        pr = layer.dataProvider()
        feat = QgsFeature()
        geom = QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(0, 0), QgsPointXY(10, 0)])
        f_geom = GeometryEngine.apply_fillet_to_geometry(geom, part_idx=0, ring_idx=0, vertex_idx=1, radius=2.0, segments_count=6)
        feat.setGeometry(f_geom)
        pr.addFeatures([feat])
        layer.updateExtents()
        layer.startEditing()
        canvas.setCurrentLayer(layer)
        self.iface.currentLayerChanged.emit(layer)

        r_tool = self.plugin.restore_map_tool
        self.plugin.toggle_restore_tool(True)
        self.assertEqual(canvas.mapTool(), r_tool)
        self.assertIsNotNone(self.plugin.restore_canvas_widget)
        self.assertEqual(self.plugin.restore_canvas_widget._current_step, 1)

        # Test step advance
        self.plugin.restore_canvas_widget.set_step(2)
        self.assertEqual(self.plugin.restore_canvas_widget._current_step, 2)
        r_tool._cancel_operation()
        self.assertEqual(self.plugin.restore_canvas_widget._current_step, 1)

        last_seg = len(f_geom.asPolyline()) - 2
        r_tool.first_segment_match = SegmentMatch(
            fid=1, part_idx=0, ring_idx=0, segment_idx=0,
            point=QgsPointXY(0, 5), p1=QgsPointXY(0, 10), p2=QgsPointXY(0, 2),
            geometry=f_geom
        )
        r_tool.current_segment_match = SegmentMatch(
            fid=1, part_idx=0, ring_idx=0, segment_idx=last_seg,
            point=QgsPointXY(5, 0), p1=QgsPointXY(2, 0), p2=QgsPointXY(10, 0),
            geometry=f_geom
        )
        restore_res = GeometryEngine.restore_sharp_corner_between_segments(f_geom, 0, 0, 0, last_seg)
        self.assertIsNotNone(restore_res)
        new_g, v_pt = restore_res
        self.assertEqual(len(new_g.asPolyline()), 3)
        self.assertAlmostEqual(v_pt.x(), 0.0)
        self.assertAlmostEqual(v_pt.y(), 0.0)

        layer.rollBack()

    def test_message_bar_auto_dismiss_timer(self):
        """Verify that notification strips are posted with a non-zero duration timer."""
        self.plugin._show_message("Test Title", "Test Message", duration=5)
        self.assertGreater(len(self.iface.messageBar().messages), 0)
        last_msg = self.iface.messageBar().messages[-1]
        self.assertEqual(last_msg["title"], "Test Title")
        self.assertEqual(last_msg["text"], "Test Message")
        self.assertEqual(last_msg["duration"], 5)


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPluginLifecycleAndEditState)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if res.wasSuccessful() else 1)

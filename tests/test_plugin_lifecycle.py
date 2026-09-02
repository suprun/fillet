# -*- coding: utf-8 -*-
"""Test plugin initGui, unload lifecycle, and action enablement based on layer editing mode."""

import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer
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

    def pushMessage(self, title, text, level=0, duration=0):
        self.messages.append((title, text, level, duration))


class MockIface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._message_bar = MockMessageBar()

    def messageBar(self):
        return self._message_bar

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
        if self.plugin.is_qgis_4():
            self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 1)
            self.plugin.unload()
            app.processEvents()
            self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 0)

            # Reload
            self.plugin = FilletPlugin(self.iface)
            self.plugin.initGui()
            self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 1)
        else:
            # In QGIS < 4, separate dock widget is not created
            self.assertIsNone(self.plugin.dock_widget)
            self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 0)

    def test_map_tool_signal_disconnects_on_reload(self):
        """Unload must remove its mapToolSet callback in QGIS 3 and QGIS 4."""
        connected_count = canvas.receivers(canvas.mapToolSet)
        self.assertGreaterEqual(connected_count, 1)

        self.plugin.unload()
        app.processEvents()
        disconnected_count = canvas.receivers(canvas.mapToolSet)
        self.assertLess(disconnected_count, connected_count)

        self.plugin = FilletPlugin(self.iface)
        self.plugin.initGui()
        reloaded_count = canvas.receivers(canvas.mapToolSet)
        self.assertEqual(reloaded_count, connected_count)

    def test_package_import_and_class_factory(self):
        """The plugin package entry point must construct a plugin instance."""
        repository_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        parent_directory = os.path.dirname(repository_root)
        sys.path.insert(0, parent_directory)
        try:
            package = importlib.import_module(os.path.basename(repository_root))
            instance = package.classFactory(self.iface)
            self.assertEqual(instance.__class__.__name__, "FilletPlugin")
            self.assertIs(instance.iface, self.iface)
        finally:
            sys.path.remove(parent_directory)

    def test_actions_disabled_when_no_layer(self):
        """Actions must be disabled when there is no active layer."""
        canvas.setCurrentLayer(None)
        self.iface.currentLayerChanged.emit(None)
        self.plugin.update_action_state()

        if self.plugin.action:
            self.assertFalse(self.plugin.action.isEnabled())
        if self.plugin.restore_action:
            self.assertFalse(self.plugin.restore_action.isEnabled())
        if self.plugin.two_line_action:
            self.assertFalse(self.plugin.two_line_action.isEnabled())
        if self.plugin.batch_action:
            self.assertFalse(self.plugin.batch_action.isEnabled())
        if self.plugin.tool_button:
            self.assertFalse(self.plugin.tool_button.isEnabled())
        if self.plugin.canvas_widget:
            self.assertFalse(self.plugin.canvas_widget.btn_apply_selected.isEnabled())
        if self.plugin.settings_widget:
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
        if self.plugin.two_line_action:
            self.assertFalse(self.plugin.two_line_action.isEnabled())
        if self.plugin.batch_action:
            self.assertFalse(self.plugin.batch_action.isEnabled())
        if self.plugin.tool_button:
            self.assertFalse(self.plugin.tool_button.isEnabled())
        if self.plugin.canvas_widget:
            self.assertFalse(self.plugin.canvas_widget.btn_apply_selected.isEnabled())
        if self.plugin.settings_widget:
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
        if self.plugin.restore_action:
            self.assertFalse(self.plugin.restore_action.isEnabled())
        if self.plugin.batch_action:
            self.assertFalse(self.plugin.batch_action.isEnabled())
        if self.plugin.canvas_widget:
            self.assertFalse(self.plugin.canvas_widget.btn_apply_selected.isEnabled())

        # 2. Start editing -> enabled for Polygon
        layer.startEditing()
        if self.plugin.action:
            self.assertTrue(self.plugin.action.isEnabled())
        if self.plugin.restore_action:
            self.assertTrue(self.plugin.restore_action.isEnabled())
        if self.plugin.batch_action:
            self.assertTrue(self.plugin.batch_action.isEnabled())
        if self.plugin.settings_widget:
            self.assertTrue(self.plugin.settings_widget.btn_apply_selected.isEnabled())

        # Two-line action is disabled for polygons
        if self.plugin.two_line_action:
            self.assertFalse(self.plugin.two_line_action.isEnabled())

        # When feature is selected, batch apply button on canvas_widget becomes enabled
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(0, 5), QgsPointXY(5, 5), QgsPointXY(5, 0), QgsPointXY(0, 0)]]))
        layer.dataProvider().addFeature(feat)
        layer.selectAll()
        self.plugin.update_action_state()
        if self.plugin.canvas_widget:
            self.assertTrue(self.plugin.canvas_widget.btn_apply_selected.isEnabled())

        # Now test with line layer
        line_layer = QgsVectorLayer("LineString?crs=EPSG:4326", "temp_lines", "memory")
        line_layer.startEditing()
        canvas.setCurrentLayer(line_layer)
        self.iface.currentLayerChanged.emit(line_layer)
        if self.plugin.two_line_action:
            self.assertTrue(self.plugin.two_line_action.isEnabled())

        # 3. Roll back (stop editing) -> disabled
        line_layer.rollBack()
        if self.plugin.action:
            self.assertFalse(self.plugin.action.isEnabled())
        if self.plugin.two_line_action:
            self.assertFalse(self.plugin.two_line_action.isEnabled())
        if self.plugin.restore_action:
            self.assertFalse(self.plugin.restore_action.isEnabled())
        if self.plugin.batch_action:
            self.assertFalse(self.plugin.batch_action.isEnabled())
        if self.plugin.canvas_widget:
            self.assertFalse(self.plugin.canvas_widget.btn_apply_selected.isEnabled())
        if self.plugin.settings_widget:
            self.assertFalse(self.plugin.settings_widget.btn_apply_selected.isEnabled())

    def test_interactive_tool_auto_deactivation_on_editing_stop(self):
        """If interactive tool is active on map canvas, it must unset when layer stops editing."""
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "temp_lines", "memory")
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

        # Test Two-Line tool deactivation
        layer.startEditing()
        self.plugin.toggle_two_line_tool(True)
        self.assertEqual(canvas.mapTool(), self.plugin.two_line_map_tool)
        self.assertTrue(self.plugin.two_line_action.isChecked())

        layer.rollBack()
        self.assertNotEqual(canvas.mapTool(), self.plugin.two_line_map_tool)
        self.assertFalse(self.plugin.two_line_action.isChecked())
        self.assertFalse(self.plugin.two_line_action.isEnabled())

        # Test Restore tool deactivation
        layer.startEditing()
        self.plugin.toggle_restore_tool(True)
        self.assertEqual(canvas.mapTool(), self.plugin.restore_map_tool)
        self.assertTrue(self.plugin.restore_action.isChecked())

        layer.rollBack()
        self.assertNotEqual(canvas.mapTool(), self.plugin.restore_map_tool)
        self.assertFalse(self.plugin.restore_action.isChecked())
        self.assertFalse(self.plugin.restore_action.isEnabled())

    def test_map_tool_preview_in_all_modes(self):
        """Verify that _update_preview works without errors in fillet and chamfer modes."""
        if self.plugin.is_qgis_4():
            return

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
        # 1. Test warning when no layer / not editable
        canvas.setCurrentLayer(None)
        self.plugin.apply_to_selected_features()
        self.assertTrue(len(self.iface.messageBar().messages) > 0)
        last_msg = self.iface.messageBar().messages[-1]
        self.assertGreaterEqual(last_msg[3], 4)  # duration >= 4s

        # 2. Test info when no selected features
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "temp_lines", "memory")
        layer.startEditing()
        canvas.setCurrentLayer(layer)
        self.plugin.apply_to_selected_features()
        last_msg = self.iface.messageBar().messages[-1]
        self.assertGreaterEqual(last_msg[3], 4)
        layer.rollBack()

    def test_batch_zero_size_does_not_create_an_edit_command(self):
        """An unchanged zero-size batch result must not touch the undo stack."""
        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "zero_batch", "memory")
        feature = QgsFeature()
        feature.setGeometry(
            QgsGeometry.fromPolygonXY(
                [[
                    QgsPointXY(0, 0),
                    QgsPointXY(0, 10),
                    QgsPointXY(10, 10),
                    QgsPointXY(10, 0),
                    QgsPointXY(0, 0),
                ]]
            )
        )
        self.assertTrue(layer.dataProvider().addFeature(feature))
        layer.startEditing()
        layer.selectAll()
        canvas.setCurrentLayer(layer)

        source_wkb = next(layer.getFeatures()).geometry().asWkb()
        undo_index = layer.undoStack().index()

        target_widget = self.plugin.canvas_widget if self.plugin.canvas_widget else self.plugin.settings_widget
        target_widget.mode = target_widget.MODE_FILLET
        target_widget.spin_radius.setValue(0.0)
        self.plugin.apply_to_selected_features()
        self.assertEqual(layer.undoStack().index(), undo_index)
        self.assertEqual(next(layer.getFeatures()).geometry().asWkb(), source_wkb)

        target_widget.mode = target_widget.MODE_CHAMFER
        target_widget.spin_dist1.setValue(0.0)
        target_widget.spin_dist2.setValue(0.0)
        self.plugin.apply_to_selected_features()
        self.assertEqual(layer.undoStack().index(), undo_index)
        self.assertEqual(next(layer.getFeatures()).geometry().asWkb(), source_wkb)
        layer.rollBack()

    def test_toolbar_actions_setup(self):
        """Test relative placement of Fillet actions in Advanced Digitize toolbar."""
        custom_win = QMainWindow()
        custom_tb = QToolBar("AdvDigitizeMock", custom_win)

        class OrderMockIface(MockIface):
            def advancedDigitizeToolBar(self):
                return custom_tb

        order_iface = OrderMockIface()
        plugin = FilletPlugin(order_iface)
        plugin.initGui()

        if not plugin.is_qgis_4():
            self.assertIsNotNone(plugin.tool_button)
            self.assertIsNotNone(plugin.fillet_restore_menu)
            self.assertIn(plugin.action, plugin.fillet_restore_menu.actions())
            self.assertIn(plugin.restore_action, plugin.fillet_restore_menu.actions())
            self.assertIsNone(plugin.batch_action)
        else:
            actions = custom_tb.actions()
            self.assertEqual(actions[actions.index(plugin.restore_action) + 1], plugin.batch_action)
            self.assertEqual(actions[actions.index(plugin.batch_action) + 1], plugin.two_line_action)

        plugin.unload()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPluginLifecycleAndEditState)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if res.wasSuccessful() else 1)

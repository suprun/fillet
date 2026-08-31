# -*- coding: utf-8 -*-
"""Test plugin initGui, unload lifecycle, and action enablement based on layer editing mode."""

import os
import importlib
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
        self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 1)
        self.plugin.unload()
        app.processEvents()
        self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 0)

        # Reload
        self.plugin = FilletPlugin(self.iface)
        self.plugin.initGui()
        self.assertEqual(len(win.findChildren(QDockWidget, "FilletChamferDockWidget")), 1)

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
        if self.plugin.restore_action:
            self.assertFalse(self.plugin.restore_action.isEnabled())
        self.assertFalse(self.plugin.batch_action.isEnabled())

        # 2. Start editing -> enabled for Polygon
        layer.startEditing()
        if self.plugin.action:
            self.assertTrue(self.plugin.action.isEnabled())
        if self.plugin.restore_action:
            self.assertTrue(self.plugin.restore_action.isEnabled())
        self.assertTrue(self.plugin.batch_action.isEnabled())
        self.assertTrue(self.plugin.settings_widget.btn_apply_selected.isEnabled())
        # Two-line action is disabled for polygons
        if self.plugin.two_line_action:
            self.assertFalse(self.plugin.two_line_action.isEnabled())

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
        self.assertFalse(self.plugin.batch_action.isEnabled())
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

        # Test Rotate tool deactivation (requires editing AND selection)
        feat = QgsFeature()
        geom = QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(10, 10)])
        feat.setGeometry(geom)
        layer.dataProvider().addFeatures([feat])
        layer.selectAll()
        layer.startEditing()
        self.plugin.update_action_state()
        self.assertTrue(self.plugin.rotate_action.isEnabled())

        self.plugin.toggle_rotate_tool(True)
        self.assertEqual(canvas.mapTool(), self.plugin.rotate_map_tool)
        self.assertTrue(self.plugin.rotate_action.isChecked())

        layer.rollBack()
        self.assertNotEqual(canvas.mapTool(), self.plugin.rotate_map_tool)
        self.assertFalse(self.plugin.rotate_action.isChecked())
        self.assertFalse(self.plugin.rotate_action.isEnabled())

        # Test Mirror tool deactivation (requires editing AND selection)
        layer.selectAll()
        layer.startEditing()
        self.plugin.update_action_state()
        self.assertTrue(self.plugin.mirror_action.isEnabled())

        self.plugin.toggle_mirror_tool(True)
        self.assertEqual(canvas.mapTool(), self.plugin.mirror_map_tool)
        self.assertTrue(self.plugin.mirror_action.isChecked())

        layer.rollBack()
        self.assertNotEqual(canvas.mapTool(), self.plugin.mirror_map_tool)
        self.assertFalse(self.plugin.mirror_action.isChecked())
        self.assertFalse(self.plugin.mirror_action.isEnabled())

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

        self.plugin.settings_widget.mode = self.plugin.settings_widget.MODE_FILLET
        self.plugin.settings_widget.spin_radius.setValue(0.0)
        self.plugin.apply_to_selected_features()
        self.assertEqual(layer.undoStack().index(), undo_index)
        self.assertEqual(next(layer.getFeatures()).geometry().asWkb(), source_wkb)

        self.plugin.settings_widget.mode = self.plugin.settings_widget.MODE_CHAMFER
        self.plugin.settings_widget.spin_dist1.setValue(0.0)
        self.plugin.settings_widget.spin_dist2.setValue(0.0)
        self.plugin.apply_to_selected_features()
        self.assertEqual(layer.undoStack().index(), undo_index)
        self.assertEqual(next(layer.getFeatures()).geometry().asWkb(), source_wkb)
        layer.rollBack()

    def test_toolbar_actions_order(self):
        """Test relative placement of CAD actions in Advanced Digitize toolbar."""
        custom_win = QMainWindow()
        custom_tb = QToolBar("AdvDigitizeMock", custom_win)

        act_move_copy = custom_tb.addAction("mActionMoveFeatureCopy")
        act_move_copy.setObjectName("mActionMoveFeatureCopy")

        act_rotate = custom_tb.addAction("mActionRotateFeature")
        act_rotate.setObjectName("mActionRotateFeature")

        act_scale = custom_tb.addAction("mActionScaleFeature")
        act_scale.setObjectName("mActionScaleFeature")

        act_simplify = custom_tb.addAction("mActionSimplifyFeature")
        act_simplify.setObjectName("mActionSimplifyFeature")

        act_offset = custom_tb.addAction("mActionOffsetCurve")
        act_offset.setObjectName("mActionOffsetCurve")

        act_trim_extend = custom_tb.addAction("mActionTrimExtend")
        act_trim_extend.setObjectName("mActionTrimExtend")

        class OrderMockIface(MockIface):
            def advancedDigitizeToolBar(self):
                return custom_tb

        order_iface = OrderMockIface()
        plugin = FilletPlugin(order_iface)
        plugin.initGui()

        actions = custom_tb.actions()
        # 1. explode_action after trim/extend
        self.assertEqual(actions[actions.index(act_trim_extend) + 1], plugin.explode_action)
        # 2. scale_rotate_action after scale
        self.assertEqual(actions[actions.index(act_scale) + 1], plugin.scale_rotate_action)
        # 3. mirror_action before simplify
        self.assertEqual(actions[actions.index(act_simplify) - 1], plugin.mirror_action)
        # 4. edge_offset_action after offset
        self.assertEqual(actions[actions.index(act_offset) + 1], plugin.edge_offset_action)
        # 5. two_line_action after batch_action
        self.assertEqual(actions[actions.index(plugin.batch_action) + 1], plugin.two_line_action)
        # 6. clean_duplicates_action at the end
        self.assertEqual(actions[-1], plugin.clean_duplicates_action)
        # 7. Move Feature -> Align Feature -> Match Edge
        self.assertEqual(actions[actions.index(act_move_copy) + 1], plugin.align_feature_action)
        self.assertEqual(actions[actions.index(plugin.align_feature_action) + 1], plugin.match_edge_action)
        # 8. Linear Array -> Array Along Path -> Polar Array
        if plugin.array_action is not None:
            self.assertEqual(actions[actions.index(plugin.array_action) + 1], plugin.array_along_path_action)
        self.assertEqual(actions[actions.index(plugin.array_along_path_action) + 1], plugin.polar_array_action)
        # 9. Explode -> Extract -> Subtract -> Clip -> Divide -> Ortho -> Clean
        editing_group = [
            plugin.explode_action,
            plugin.extract_part_action,
            plugin.subtract_feature_action,
            plugin.clip_feature_action,
            plugin.divide_line_action,
            plugin.ortho_angles_action,
            plugin.clean_duplicates_action,
        ]
        self.assertEqual(
            [actions.index(action) for action in editing_group],
            sorted(actions.index(action) for action in editing_group),
        )

        plugin.unload()

    def test_ortho_angles_action_and_widget_init(self):
        """Verify CAD Ortho Angles action, map tool, and widget are initialized in initGui."""
        self.assertIsNotNone(self.plugin.ortho_angles_action)
        self.assertIsNotNone(self.plugin.ortho_angles_map_tool)
        self.assertIsNotNone(self.plugin.ortho_angles_widget)
        self.assertFalse(self.plugin.ortho_angles_widget.isVisible())

    def test_research_tools_init_enablement_and_unload(self):
        """All six tools are initialized once and follow layer capability rules."""
        action_names = (
            "align_feature_action",
            "match_edge_action",
            "array_along_path_action",
            "extract_part_action",
            "subtract_feature_action",
            "clip_feature_action",
        )
        for name in action_names:
            self.assertIsNotNone(getattr(self.plugin, name))

        layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "target", "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))"))
        layer.dataProvider().addFeature(feature)
        layer.startEditing()
        canvas.setCurrentLayer(layer)
        self.iface.currentLayerChanged.emit(layer)
        self.assertFalse(self.plugin.align_feature_action.isEnabled())
        self.assertFalse(self.plugin.match_edge_action.isEnabled())
        self.assertFalse(self.plugin.array_along_path_action.isEnabled())
        self.assertTrue(self.plugin.extract_part_action.isEnabled())
        self.assertTrue(self.plugin.subtract_feature_action.isEnabled())
        self.assertTrue(self.plugin.clip_feature_action.isEnabled())

        layer.selectAll()
        self.assertTrue(self.plugin.align_feature_action.isEnabled())
        self.assertTrue(self.plugin.match_edge_action.isEnabled())
        self.assertTrue(self.plugin.array_along_path_action.isEnabled())
        align_tooltip = self.plugin.align_feature_action.toolTip().lower()
        match_tooltip = self.plugin.match_edge_action.toolTip().lower()
        self.assertTrue(
            "всю вибрану групу" in align_tooltip
            or "entire selected group" in align_tooltip
        )
        self.assertTrue(
            "локально виправити" in match_tooltip
            or "locally reshape" in match_tooltip
        )

        point_layer = QgsVectorLayer("Point?crs=EPSG:3857", "points", "memory")
        point_feature = QgsFeature(point_layer.fields())
        point_feature.setGeometry(QgsGeometry.fromWkt("POINT (0 0)"))
        point_layer.dataProvider().addFeature(point_feature)
        point_layer.startEditing()
        point_layer.selectAll()
        canvas.setCurrentLayer(point_layer)
        self.iface.currentLayerChanged.emit(point_layer)
        self.assertTrue(self.plugin.align_feature_action.isEnabled())
        self.assertFalse(self.plugin.match_edge_action.isEnabled())
        self.assertTrue(self.plugin.array_along_path_action.isEnabled())

        self.plugin.unload()
        app.processEvents()
        for name in action_names:
            self.assertIsNone(getattr(self.plugin, name))
        for name in (
            "align_feature_map_tool",
            "match_edge_map_tool",
            "array_along_path_map_tool",
            "extract_part_map_tool",
            "subtract_feature_map_tool",
            "clip_feature_map_tool",
        ):
            self.assertIsNone(getattr(self.plugin, name))
        self.plugin = FilletPlugin(self.iface)
        self.plugin.initGui()
        layer.rollBack()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPluginLifecycleAndEditState)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if res.wasSuccessful() else 1)

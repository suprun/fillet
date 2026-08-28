# -*- coding: utf-8 -*-
"""
Unit tests for CAD Ortho Angles tool (orthogonalization of polygon/line vertices relative to a reference base edge).
Tests OrthoAnglesCanvasWidget, CADOrthoAnglesMapTool, and GeometryEngine.orthogonalize_geometry.
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
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsSettings,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow, QToolBar

app = QgsApplication([], False)
app.initQgis()

from core.geometry_engine import GeometryEngine
from gui.ortho_angles_canvas_widget import OrthoAnglesCanvasWidget
from gui.ortho_angles_map_tool import CADOrthoAnglesMapTool
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


class TestGeometryEngineOrthoAngles(unittest.TestCase):
    """Test suite for GeometryEngine.orthogonalize_geometry."""

    def test_distorted_rectangle_squaring(self):
        """Distorted 4-sided polygon should become a right-angled polygon."""
        # Slightly skewed rectangle (angles ~87-93 deg)
        poly_pts = [
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.0, 0.5),   # ~2.86 deg tilt
            QgsPointXY(9.5, 10.2),   # ~92.8 deg
            QgsPointXY(-0.4, 9.8),   # ~182 deg
            QgsPointXY(0.0, 0.0),
        ]
        geom = QgsGeometry.fromPolygonXY([poly_pts])
        self.assertTrue(geom.isGeosValid())

        # Base facade is segment (0, 0) -> (10, 0.5) with angle ~0.0499 rad
        base_angle = math.atan2(0.5, 10.0)
        ortho_geom = GeometryEngine.orthogonalize_geometry(
            geom,
            base_angle_rad=base_angle,
            tolerance_deg=15.0,
            preserve_area=False,
        )

        self.assertFalse(ortho_geom.isEmpty())
        self.assertTrue(ortho_geom.isGeosValid())

        # Verify corner angles are all multiples of 90 deg relative to base_angle
        ring = ortho_geom.asPolygon()[0]
        self.assertEqual(len(ring), 5)

        for i in range(len(ring) - 1):
            p1 = ring[i]
            p2 = ring[i + 1]
            seg_angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            diff = (seg_angle - base_angle + math.pi / 4.0) % (math.pi / 2.0) - math.pi / 4.0
            self.assertAlmostEqual(diff, 0.0, places=4, msg=f"Segment {i} angle diff is not 0: {diff}")

    def test_preserve_area(self):
        """Area of orthogonalized polygon should match original when preserve_area=True."""
        poly_pts = [
            QgsPointXY(0.0, 0.0),
            QgsPointXY(20.0, 1.0),
            QgsPointXY(19.0, 15.0),
            QgsPointXY(-1.0, 14.0),
            QgsPointXY(0.0, 0.0),
        ]
        geom = QgsGeometry.fromPolygonXY([poly_pts])
        orig_area = geom.area()

        base_angle = math.atan2(1.0, 20.0)
        ortho_geom = GeometryEngine.orthogonalize_geometry(
            geom,
            base_angle_rad=base_angle,
            tolerance_deg=15.0,
            preserve_area=True,
        )

        ortho_area = ortho_geom.area()
        self.assertAlmostEqual(orig_area, ortho_area, places=3)

    def test_bay_window_preserved(self):
        """Segments with angles > tolerance (e.g. 45 deg bay window) should be preserved."""
        # Building with 45-degree bay window corner:
        poly_pts = [
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.0, 0.0),
            QgsPointXY(10.0, 5.0),
            QgsPointXY(7.0, 8.0),   # 45-degree angled wall
            QgsPointXY(0.0, 8.0),
            QgsPointXY(0.0, 0.0),
        ]
        geom = QgsGeometry.fromPolygonXY([poly_pts])
        ortho_geom = GeometryEngine.orthogonalize_geometry(
            geom,
            base_angle_rad=0.0,
            tolerance_deg=15.0,
            preserve_area=False,
        )
        self.assertTrue(ortho_geom.isGeosValid())
        ring = ortho_geom.asPolygon()[0]
        self.assertEqual(len(ring), 6)

    def test_polyline_orthogonalization(self):
        """Linestring should also be cleanly orthogonalized."""
        line_pts = [
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.2, 0.3),
            QgsPointXY(10.0, 9.8),
            QgsPointXY(0.2, 10.1),
        ]
        geom = QgsGeometry.fromPolylineXY(line_pts)
        ortho_geom = GeometryEngine.orthogonalize_geometry(
            geom,
            base_angle_rad=0.0,
            tolerance_deg=15.0,
        )
        self.assertFalse(ortho_geom.isEmpty())
        pts = ortho_geom.asPolyline()
        self.assertEqual(len(pts), 4)


class TestOrthoAnglesCanvasWidget(unittest.TestCase):
    """Test suite for OrthoAnglesCanvasWidget UI and settings persistence."""

    def setUp(self):
        settings = QgsSettings()
        settings.setValue("fillet/ortho_angles_preserve_area", True)
        settings.setValue("fillet/ortho_angles_create_copy", False)
        self.widget = OrthoAnglesCanvasWidget(None)

    def tearDown(self):
        self.widget.deleteLater()
        settings = QgsSettings()
        settings.remove("fillet/ortho_angles_preserve_area")
        settings.remove("fillet/ortho_angles_create_copy")

    def test_initial_values(self):
        self.assertGreaterEqual(self.widget.tolerance, 1.0)
        self.assertLessEqual(self.widget.tolerance, 45.0)
        self.assertFalse(self.widget.is_tolerance_locked)
        self.assertTrue(self.widget.preserve_area)
        self.assertFalse(self.widget.create_copy)

    def test_lock_toggle(self):
        self.widget.btn_lock_tolerance.setChecked(True)
        self.assertTrue(self.widget.is_tolerance_locked)
        self.widget.btn_lock_tolerance.setChecked(False)
        self.assertFalse(self.widget.is_tolerance_locked)

    def test_presets_menu(self):
        self.widget._rebuild_tolerance_menu()
        actions = self.widget.tolerance_menu.actions()
        self.assertGreater(len(actions), 2)
        # Select preset
        self.widget._on_tolerance_preset_selected(20.0)
        self.assertEqual(self.widget.tolerance, 20.0)

    def test_steps(self):
        self.widget.set_step(OrthoAnglesCanvasWidget.STEP_SELECT)
        self.assertIn("1", self.widget.lbl_step.text())
        self.widget.set_step(OrthoAnglesCanvasWidget.STEP_BASE_EDGE)
        self.assertIn("2", self.widget.lbl_step.text())
        self.widget.set_step(OrthoAnglesCanvasWidget.STEP_ADJUST)
        self.assertIn("3", self.widget.lbl_step.text())


class TestCADOrthoAnglesMapTool(unittest.TestCase):
    """Test suite for CADOrthoAnglesMapTool lifecycle, snapping, and commit."""

    def setUp(self):
        self.win = QMainWindow()
        self.canvas = QgsMapCanvas(self.win)
        self.canvas.resize(800, 600)
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.tb = QToolBar(self.win)
        self.iface = MockIface(self.win, self.canvas, self.tb)

        # Create temporary memory polygon layer
        self.layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "test_poly_layer", "memory")
        QgsProject.instance().addMapLayer(self.layer)
        self.layer.startEditing()

        # Add skewed feature
        f = QgsFeature(self.layer.fields())
        poly_pts = [
            QgsPointXY(0.0, 0.0),
            QgsPointXY(10.0, 0.5),
            QgsPointXY(9.5, 10.0),
            QgsPointXY(-0.2, 9.8),
            QgsPointXY(0.0, 0.0),
        ]
        f.setGeometry(QgsGeometry.fromPolygonXY([poly_pts]))
        self.layer.addFeature(f)
        self.canvas.setCurrentLayer(self.layer)

        self.widget = OrthoAnglesCanvasWidget(self.canvas)
        self.tool = CADOrthoAnglesMapTool(self.canvas, self.widget, self.iface)

    def tearDown(self):
        if self.tool:
            self.tool.deactivate()
            self.tool.deleteLater()
            self.tool = None
        if self.widget:
            self.widget.deleteLater()
            self.widget = None
        QgsProject.instance().removeMapLayer(self.layer)
        self.win.deleteLater()

    def test_find_closest_segment(self):
        geom = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0),
            QgsPointXY(10, 0),
            QgsPointXY(10, 10),
            QgsPointXY(0, 10),
            QgsPointXY(0, 0)
        ]])
        seg_info = self.tool._find_closest_segment(geom, QgsPointXY(5, 0.1))
        self.assertIsNotNone(seg_info)
        p1, p2, azimuth = seg_info
        self.assertEqual(p1, QgsPointXY(0, 0))
        self.assertEqual(p2, QgsPointXY(10, 0))
        self.assertAlmostEqual(azimuth, 0.0, places=4)

    def test_tool_workflow_and_commit(self):
        self.tool.activate()
        self.assertEqual(self.tool.state, CADOrthoAnglesMapTool.STATE_SELECT_FEATURE)

        # Select feature
        self.layer.selectAll()
        self.tool.reset_state()
        self.assertEqual(self.tool.state, CADOrthoAnglesMapTool.STATE_SET_BASE_EDGE)

        # Simulate base edge assignment
        base_angle = math.atan2(0.5, 10.0)
        self.tool.base_segment = (QgsPointXY(0.0, 0.0), QgsPointXY(10.0, 0.5))
        self.tool.base_angle_rad = base_angle
        self.tool.state = CADOrthoAnglesMapTool.STATE_ADJUST

        # Commit orthogonalization (which resets map tool state back)
        self.tool.commit_orthogonalize()

        # Verify geometry updated in layer
        feat = next(self.layer.getFeatures())
        ring = feat.geometry().asPolygon()[0]
        self.assertEqual(len(ring), 5)
        # Check angle of second segment is orthogonal to base_angle
        p1, p2 = ring[1], ring[2]
        seg_angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
        diff = (seg_angle - base_angle + math.pi / 4.0) % (math.pi / 2.0) - math.pi / 4.0
        self.assertAlmostEqual(diff, 0.0, places=3)

    def test_preview_and_commit_use_canvas_crs(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "crs_ortho", "memory")
        source = QgsGeometry.fromPolygonXY([[
            QgsPointXY(1.0, 45.0),
            QgsPointXY(1.1, 45.005),
            QgsPointXY(1.095, 45.1),
            QgsPointXY(0.998, 45.098),
            QgsPointXY(1.0, 45.0),
        ]])
        feature = QgsFeature(layer.fields())
        feature.setGeometry(source)
        layer.dataProvider().addFeatures([feature])
        layer.startEditing()
        source_feature = next(layer.getFeatures())
        self.canvas.setCurrentLayer(layer)

        to_canvas = QgsCoordinateTransform(
            layer.crs(),
            self.canvas.mapSettings().destinationCrs(),
            QgsProject.instance(),
        )
        source_canvas = QgsGeometry(source)
        source_canvas.transform(to_canvas)
        canvas_ring = source_canvas.asPolygon()[0]
        base_segment = (canvas_ring[0], canvas_ring[1])
        base_angle = math.atan2(
            base_segment[1].y() - base_segment[0].y(),
            base_segment[1].x() - base_segment[0].x(),
        )
        expected = GeometryEngine.orthogonalize_geometry(
            source_canvas,
            base_angle_rad=base_angle,
            tolerance_deg=15.0,
            preserve_area=False,
        )

        widget = OrthoAnglesCanvasWidget(self.canvas)
        widget.chk_preserve_area.setChecked(False)
        widget.spin_tolerance.setValue(15.0)
        tool = CADOrthoAnglesMapTool(self.canvas, widget, self.iface)
        tool.featureLayer = layer
        tool.featureList = [source_feature]
        tool.base_segment = base_segment
        tool.base_angle_rad = base_angle
        tool.state = CADOrthoAnglesMapTool.STATE_ADJUST
        tool._update_preview()

        self.assertTrue(tool.preview_rubberbands)
        preview_first = next(tool.preview_rubberbands[0].asGeometry().vertices())
        expected_first = next(expected.vertices())
        self.assertAlmostEqual(preview_first.x(), expected_first.x(), places=3)
        self.assertAlmostEqual(preview_first.y(), expected_first.y(), places=3)

        tool.commit_orthogonalize()
        committed = next(layer.getFeatures()).geometry()
        committed.transform(to_canvas)
        committed_first = next(committed.vertices())
        self.assertAlmostEqual(committed_first.x(), expected_first.x(), places=3)
        self.assertAlmostEqual(committed_first.y(), expected_first.y(), places=3)

        widget.chk_preserve_area.setChecked(True)
        tool.deactivate()
        tool.deleteLater()
        widget.deleteLater()
        layer.rollBack()
        self.canvas.setCurrentLayer(self.layer)

    def test_click_select_highlights_without_layer_selection(self):
        """Clicking on a feature in STATE_SELECT_FEATURE should highlight it without changing layer selection."""
        self.layer.removeSelection()
        self.assertEqual(self.layer.selectedFeatureCount(), 0)
        self.tool.activate()
        self.assertEqual(self.tool.state, CADOrthoAnglesMapTool.STATE_SELECT_FEATURE)

        # Simulate clicking on feature at (5, 5)
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPointF, Qt
        from qgis.PyQt.QtGui import QMouseEvent

        mouse_ev = QMouseEvent(
            getattr(QEvent.Type, "MouseButtonPress", getattr(QEvent, "MouseButtonPress", 2)),
            QPointF(5.0, 5.0),
            getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1)),
            getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1)),
            getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
        )
        ev = QgsMapMouseEvent(self.canvas, mouse_ev)
        self.tool._snap_point = lambda e: QgsPointXY(5.0, 5.0)
        self.tool.canvasPressEvent(ev)

        # Should transition to STATE_SET_BASE_EDGE
        self.assertEqual(self.tool.state, CADOrthoAnglesMapTool.STATE_SET_BASE_EDGE)
        self.assertEqual(len(self.tool.featureList), 1)
        # Layer selection in QGIS should remain empty (0 features selected)
        self.assertEqual(self.layer.selectedFeatureCount(), 0)
        # Visual selection rubberband should have geometry
        self.assertIsNotNone(self.tool.selection_rubberband)
        self.assertFalse(self.tool.selection_rubberband.asGeometry().isEmpty())

    def test_escape_key_step_back_and_deactivate(self):
        """Verify Esc key steps back through states and deactivates at initial state."""
        self.tool.activate()
        self.tool.featureList = [next(self.layer.getFeatures())]
        self.tool.featureLayer = self.layer
        self.tool.base_segment = (QgsPointXY(0, 0), QgsPointXY(10, 0))
        self.tool.state = CADOrthoAnglesMapTool.STATE_ADJUST

        from qgis.PyQt.QtCore import QEvent, Qt
        from qgis.PyQt.QtGui import QKeyEvent

        def send_key(key_code):
            ev = QKeyEvent(
                getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6)),
                key_code,
                getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
            )
            self.tool.keyPressEvent(ev)

        esc_code = int(getattr(Qt.Key, "Key_Escape", 0x01000000))

        # 1. From STATE_ADJUST -> STATE_SET_BASE_EDGE
        send_key(esc_code)
        self.assertEqual(self.tool.state, CADOrthoAnglesMapTool.STATE_SET_BASE_EDGE)

        # 2. From STATE_SET_BASE_EDGE -> STATE_SELECT_FEATURE
        send_key(esc_code)
        self.assertEqual(self.tool.state, CADOrthoAnglesMapTool.STATE_SELECT_FEATURE)
        self.assertEqual(len(self.tool.featureList), 0)

        # 3. From STATE_SELECT_FEATURE -> deactivate (unset map tool)
        send_key(esc_code)
        self.assertNotEqual(self.canvas.mapTool(), self.tool)

    def test_escape_key_in_hud_widget(self):
        """Verify Esc key inside HUD spinbox or widget emits resetRequested."""
        self.tool.activate()
        self.tool.state = CADOrthoAnglesMapTool.STATE_ADJUST
        self.tool.base_segment = (QgsPointXY(0, 0), QgsPointXY(10, 0))

        from qgis.PyQt.QtCore import QEvent, Qt
        from qgis.PyQt.QtGui import QKeyEvent

        ev = QKeyEvent(
            getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", 6)),
            int(getattr(Qt.Key, "Key_Escape", 0x01000000)),
            getattr(Qt.KeyboardModifier, "NoModifier", getattr(Qt, "NoModifier", 0)),
        )
        # Send to HUD spinbox
        handled = self.widget.eventFilter(self.widget.spin_tolerance, ev)
        self.assertTrue(handled)
        self.assertEqual(self.tool.state, CADOrthoAnglesMapTool.STATE_SET_BASE_EDGE)


class TestFilletPluginOrthoAnglesIntegration(unittest.TestCase):
    """Test suite for FilletPlugin registering and cleaning up Ortho Angles action."""

    def setUp(self):
        self.win = QMainWindow()
        self.canvas = QgsMapCanvas(self.win)
        self.tb = QToolBar(self.win)
        self.iface = MockIface(self.win, self.canvas, self.tb)
        self.plugin = FilletPlugin(self.iface)

    def tearDown(self):
        if self.plugin:
            self.plugin.unload()
            self.plugin = None
        self.win.deleteLater()

    def test_plugin_init_and_unload(self):
        self.plugin.initGui()
        self.assertIsNotNone(self.plugin.ortho_angles_action)
        self.assertIsNotNone(self.plugin.ortho_angles_map_tool)
        self.assertIsNotNone(self.plugin.ortho_angles_widget)

        # Test toggle
        self.plugin.toggle_ortho_angles_tool(True)
        self.assertEqual(self.canvas.mapTool(), self.plugin.ortho_angles_map_tool)
        self.plugin.toggle_ortho_angles_tool(False)
        self.assertNotEqual(self.canvas.mapTool(), self.plugin.ortho_angles_map_tool)

        # Unload
        self.plugin.unload()
        self.assertIsNone(self.plugin.ortho_angles_action)
        self.assertIsNone(self.plugin.ortho_angles_map_tool)
        self.assertIsNone(self.plugin.ortho_angles_widget)


if __name__ == "__main__":
    unittest.main()

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
    @classmethod
    def setUpClass(cls):
        from qgis.gui import QgsMapCanvas
        cls.canvas = QgsMapCanvas()
        cls.canvas.resize(800, 600)

    @classmethod
    def tearDownClass(cls):
        cls.canvas = None

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
        from qgis.core import QgsCoordinateReferenceSystem
        from gui.two_line_canvas_widget import TwoLineCanvasWidget

        canvas = self.canvas
        widget = TwoLineCanvasWidget(canvas)

        widget.set_step(TwoLineCanvasWidget.STEP_FIRST_LINE)
        self.assertIn("1.", widget.lbl_step.text())

        widget.set_step(TwoLineCanvasWidget.STEP_SECOND_LINE)
        self.assertIn("2.", widget.lbl_step.text())

        widget.set_step(TwoLineCanvasWidget.STEP_ADJUST)
        self.assertIn("3.", widget.lbl_step.text())
        self.assertGreater(widget.width(), 200)

        # Mode switching
        widget.radio_chamfer.setChecked(True)
        self.assertEqual(widget.mode, TwoLineCanvasWidget.MODE_CHAMFER)
        widget.radio_fillet.setChecked(True)
        self.assertEqual(widget.mode, TwoLineCanvasWidget.MODE_FILLET)

        # Linking
        widget.radio_chamfer.setChecked(True)
        widget.btn_link.setChecked(True)
        widget.set_distance1(5.0)
        self.assertEqual(widget.distance2, 5.0)

        # CRS adaptation
        widget.adapt_to_crs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.assertEqual(widget.spin_radius.decimals(), 6)

        widget.adapt_to_crs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.assertEqual(widget.spin_radius.decimals(), 3)

    def test_two_line_map_tool_feature_merge(self):
        from qgis.core import (
            QgsFeature,
            QgsField,
            QgsFields,
            QgsVectorLayer,
            QgsSettings,
        )
        from qgis.PyQt.QtCore import QVariant
        from gui.two_line_map_tool import TwoLineMapTool
        from gui.two_line_canvas_widget import TwoLineCanvasWidget

        canvas = self.canvas

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

        widget = TwoLineCanvasWidget(canvas)
        widget.chk_always_first.setChecked(True)

        tool = TwoLineMapTool(canvas, widget=widget, iface=None)
        tool.activate()

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

    def test_two_line_map_tool_cancel_rollback(self):
        """Verify that when QGIS merge dialog is cancelled, no layer changes or deletions occur."""
        from qgis.core import QgsFeature, QgsField, QgsVectorLayer
        from qgis.PyQt.QtCore import QVariant
        from gui.two_line_map_tool import TwoLineMapTool
        from gui.two_line_canvas_widget import TwoLineCanvasWidget
        from unittest.mock import MagicMock

        canvas = self.canvas
        layer = QgsVectorLayer("LineString?crs=EPSG:3857", "test_cancel", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", getattr(QVariant, "String", 10))])
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(10, 10)]))
        f2 = QgsFeature(layer.fields())
        f2.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(10, 0), QgsPointXY(10, 20)]))
        pr.addFeatures([f1, f2])
        layer.startEditing()
        canvas.setCurrentLayer(layer)

        widget = TwoLineCanvasWidget(canvas)
        widget.chk_always_first.setChecked(False)

        # Mock iface with simulated cancelled merge dialog (trigger does not delete fid2)
        mock_iface = MagicMock()
        mock_merge_action = MagicMock()
        mock_iface.mainWindow.return_value.findChild.return_value = mock_merge_action

        tool = TwoLineMapTool(canvas, widget=widget, iface=mock_iface)
        tool.activate()

        new_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(8, 10), QgsPointXY(10, 8), QgsPointXY(10, 0)])

        # Trigger operation with simulated dialog cancel (fid2 is still valid and not deleted)
        f1_id = f1.id()
        f2_id = f2.id()
        tool._apply_two_line_operation(layer, f1_id, f2_id, new_geom)

        # Verify BOTH features still exist and f1 geometry was NOT altered to new_geom
        feats = list(layer.getFeatures())
        self.assertEqual(len(feats), 2)
        self.assertAlmostEqual(feats[0].geometry().asPolyline()[1].x(), 10.0, places=2)

        tool.cleanup()

    def test_two_line_map_tool_canvas_events(self):
        from qgis.core import (
            QgsFeature,
            QgsField,
            QgsVectorLayer,
        )
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPoint, Qt, QVariant
        from gui.two_line_map_tool import TwoLineMapTool
        from gui.two_line_canvas_widget import TwoLineCanvasWidget
        from core.snapping_helper import SegmentMatch

        canvas = self.canvas

        layer = QgsVectorLayer("LineString?crs=EPSG:3857", "test_lines_events", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField("name", getattr(QVariant, "String", 10))])
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(10, 10)]))
        f2 = QgsFeature(layer.fields())
        f2.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(10, 0), QgsPointXY(10, 20)]))
        pr.addFeatures([f1, f2])
        layer.startEditing()
        canvas.setCurrentLayer(layer)

        widget = TwoLineCanvasWidget(canvas)
        widget.btn_lock_radius.setChecked(False)

        tool = TwoLineMapTool(canvas, widget=widget, iface=None)
        tool.activate()

        # Step 1: Select first segment
        m1 = SegmentMatch(fid=1, part_idx=0, ring_idx=0, segment_idx=0, point=QgsPointXY(2, 10), p1=QgsPointXY(0, 10), p2=QgsPointXY(10, 10), geometry=f1.geometry())
        tool.first_segment_match = m1
        tool.state = TwoLineMapTool.STATE_SELECT_SECOND

        # Step 2: Hover over second segment
        m2 = SegmentMatch(fid=2, part_idx=0, ring_idx=0, segment_idx=0, point=QgsPointXY(10, 2), p1=QgsPointXY(10, 0), p2=QgsPointXY(10, 20), geometry=f2.geometry())

        evt_mouse_move = getattr(QEvent.Type, "MouseMove", getattr(QEvent, "MouseMove", None))
        evt_mouse_press = getattr(QEvent.Type, "MouseButtonPress", getattr(QEvent, "MouseButtonPress", None))

        from unittest.mock import patch
        with patch("core.snapping_helper.SnappingHelper.find_segment_at_position", return_value=m2):
            left_btn = getattr(Qt.MouseButton, "NoButton", getattr(Qt, "NoButton", 0))
            mouse_evt = QgsMapMouseEvent(canvas, evt_mouse_move, QPoint(100, 100), left_btn)
            tool.canvasMoveEvent(mouse_evt)
            self.assertIsNotNone(tool.preview_geom)
            self.assertIsNotNone(tool.current_segment_match)

        # Left click to enter Step 3 (adjusting)
        left_click = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
        with patch("core.snapping_helper.SnappingHelper.find_segment_at_position", return_value=m2):
            press_evt = QgsMapMouseEvent(canvas, evt_mouse_press, QPoint(100, 100), left_click)
            tool.canvasPressEvent(press_evt)
            self.assertEqual(tool.state, TwoLineMapTool.STATE_ADJUSTING)
            self.assertEqual(tool.widget._current_step, TwoLineCanvasWidget.STEP_ADJUST)

        # Right click step-back from Step 3 to Step 2
        right_btn = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
        press_evt = QgsMapMouseEvent(canvas, evt_mouse_press, QPoint(100, 100), right_btn)
        tool.canvasPressEvent(press_evt)
        self.assertEqual(tool.state, TwoLineMapTool.STATE_SELECT_SECOND)

        # Right click again from Step 2 to Step 1
        tool.canvasPressEvent(press_evt)
        self.assertEqual(tool.state, TwoLineMapTool.STATE_SELECT_FIRST)
        self.assertIsNone(tool.first_segment_match)

        tool.cleanup()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTwoLineFillet)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)

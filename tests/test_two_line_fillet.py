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
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow

app = QgsApplication([], False)
app.initQgis()

win = QMainWindow()
canvas = QgsMapCanvas(win)

from core.geometry_engine import GeometryEngine


class TestTwoLineFillet(unittest.TestCase):

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

    def test_two_line_canvas_widget(self):
        from qgis.core import QgsSettings
        from gui.canvas_widget import FilletCanvasWidget

        widget = FilletCanvasWidget(canvas)

        # Single vertex mode by default
        self.assertTrue(widget.lbl_step.isHidden())
        self.assertTrue(widget.chk_always_first.isHidden())

        # Switch to two-line mode
        widget.set_two_line_mode(True)
        self.assertFalse(widget.lbl_step.isHidden())
        self.assertFalse(widget.chk_always_first.isHidden())

        widget.set_step(1)
        self.assertIn("1.", widget.lbl_step.text())

        widget.set_step(2)
        self.assertIn("2.", widget.lbl_step.text())

        widget.set_step(3)
        self.assertIn("3.", widget.lbl_step.text())

        # Always first checkbox toggle
        widget.chk_always_first.setChecked(True)
        self.assertTrue(QgsSettings().value("plugins/fillet/merge_always_first_feature", False, type=bool))

        widget.chk_always_first.setChecked(False)
        self.assertFalse(QgsSettings().value("plugins/fillet/merge_always_first_feature", True, type=bool))

        widget.set_two_line_mode(False)
        self.assertTrue(widget.lbl_step.isHidden())
        self.assertTrue(widget.chk_always_first.isHidden())

        try:
            canvas.removeEventFilter(widget)
        except (TypeError, RuntimeError):
            pass
        widget.deleteLater()

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

        tool = TwoLineMapTool(canvas, iface=None)
        tool.activate()

        # Always first setting
        s = QgsSettings()
        s.setValue("plugins/fillet/merge_always_first_feature", True)

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
        if tool.widget:
            try:
                canvas.removeEventFilter(tool.widget)
            except (TypeError, RuntimeError):
                pass
            tool.widget.deleteLater()
        layer.rollBack()

    def test_two_line_map_tool_canvas_events_and_cursor_drag(self):
        from qgis.core import (
            QgsFeature,
            QgsField,
            QgsVectorLayer,
        )
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPoint, Qt, QVariant
        from gui.two_line_map_tool import TwoLineMapTool
        from core.snapping_helper import SegmentMatch

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

        tool = TwoLineMapTool(canvas, iface=None)
        tool.activate()

        # Unlock radius on widget so it enters Step 3
        tool.widget.btn_lock_radius.setChecked(False)

        # Step 1: Click first segment
        m1 = SegmentMatch(fid=1, part_idx=0, ring_idx=0, segment_idx=0, point=QgsPointXY(2, 10), p1=QgsPointXY(0, 10), p2=QgsPointXY(10, 10), geometry=f1.geometry())
        tool.first_segment_match = m1
        tool.step = tool.STEP_SECOND_LINE

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

        # Left click on Step 2 with unlocked radius moves to Step 3
        left_click_btn = getattr(Qt.MouseButton, "LeftButton", getattr(Qt, "LeftButton", 1))
        press_evt = QgsMapMouseEvent(canvas, evt_mouse_press, QPoint(100, 100), left_click_btn)
        tool.canvasPressEvent(press_evt)
        self.assertEqual(tool.step, tool.STEP_SET_RADIUS)

        # Step 3: Move cursor dynamically updates radius
        mouse_evt_drag = QgsMapMouseEvent(canvas, evt_mouse_move, QPoint(150, 150), left_btn)
        tool.canvasMoveEvent(mouse_evt_drag)
        self.assertIsNotNone(tool.preview_geom)

        # Right click step-back from Step 3 -> Step 2
        right_btn = getattr(Qt.MouseButton, "RightButton", getattr(Qt, "RightButton", 2))
        press_right = QgsMapMouseEvent(canvas, evt_mouse_press, QPoint(100, 100), right_btn)
        tool.canvasPressEvent(press_right)
        self.assertEqual(tool.step, tool.STEP_SECOND_LINE)

        # Right click step-back from Step 2 -> Step 1
        tool.canvasPressEvent(press_right)
        self.assertEqual(tool.step, tool.STEP_FIRST_LINE)
        self.assertIsNone(tool.first_segment_match)

        tool.cleanup()
        if tool.widget:
            try:
                canvas.removeEventFilter(tool.widget)
            except (TypeError, RuntimeError):
                pass
            tool.widget.deleteLater()
        layer.rollBack()

    def test_large_radius_clamped_to_segment_length(self):
        # Line 1: (0, 10) -> (5, 10), length from V(5, 10) is 5.0
        # Line 2: (5, 0) -> (5, 10), length from V(5, 10) is 10.0
        l1 = QgsGeometry(QgsLineString([QgsPoint(0, 10), QgsPoint(5, 10)]))
        l2 = QgsGeometry(QgsLineString([QgsPoint(5, 0), QgsPoint(5, 10)]))

        # Request radius = 100.0, which would exceed the 5.0 line length
        res = GeometryEngine.fillet_or_chamfer_two_lines(
            l1, 0, QgsPoint(2, 10),
            l2, 0, QgsPoint(5, 2),
            mode="fillet", radius=100.0, segments_count=8
        )
        self.assertIsNotNone(res)
        geom, v, t1, t2 = res
        pts = geom.asPolyline()
        # Verify tangent points are strictly within [0, 5]
        self.assertGreaterEqual(t1.x(), 0.0)
        self.assertLessEqual(t1.x(), 5.0)
        self.assertGreaterEqual(t2.y(), 0.0)
        self.assertLessEqual(t2.y(), 10.0)
        # Verify first point is (0, 10) and last point is (5, 0)
        self.assertAlmostEqual(pts[0].x(), 0.0, places=4)
        self.assertAlmostEqual(pts[0].y(), 10.0, places=4)
        self.assertAlmostEqual(pts[-1].x(), 5.0, places=4)
        self.assertAlmostEqual(pts[-1].y(), 0.0, places=4)

    def test_chamfer_unlinked_cursor_drag(self):
        from qgis.core import (
            QgsFeature,
            QgsField,
            QgsVectorLayer,
        )
        from qgis.gui import QgsMapMouseEvent
        from qgis.PyQt.QtCore import QEvent, QPoint, Qt, QVariant
        from gui.two_line_map_tool import TwoLineMapTool
        from gui.canvas_widget import FilletCanvasWidget
        from core.snapping_helper import SegmentMatch

        layer = QgsVectorLayer("LineString?crs=EPSG:3857", "test_chamfer_drag", "memory")
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

        tool = TwoLineMapTool(canvas, iface=None)
        tool.activate()

        # Switch to Chamfer and unlock distance links
        tool.widget.radio_chamfer.setChecked(True)
        tool.widget.btn_link.setChecked(False)
        tool.widget.btn_lock_dist1.setChecked(False)
        tool.widget.btn_lock_dist2.setChecked(False)

        # Step 1: Click first segment
        m1 = SegmentMatch(fid=1, part_idx=0, ring_idx=0, segment_idx=0, point=QgsPointXY(2, 10), p1=QgsPointXY(0, 10), p2=QgsPointXY(10, 10), geometry=f1.geometry())
        tool.first_segment_match = m1
        tool.step = tool.STEP_SECOND_LINE

        # Step 2: Set second segment and transition to Step 3
        m2 = SegmentMatch(fid=2, part_idx=0, ring_idx=0, segment_idx=0, point=QgsPointXY(10, 2), p1=QgsPointXY(10, 0), p2=QgsPointXY(10, 20), geometry=f2.geometry())
        tool.current_segment_match = m2
        tool.step = tool.STEP_SET_RADIUS
        tool.v_sharp = QgsPoint(10, 10)

        # Step 3: Move cursor to (8, 7), which is offset (-2, -3) from V(10, 10)
        # Ray 1 is towards (0, 10) [-X direction], proj1 = 2.0
        # Ray 2 is towards (10, 0) [-Y direction], proj2 = 3.0
        evt_mouse_move = getattr(QEvent.Type, "MouseMove", getattr(QEvent, "MouseMove", None))
        left_btn = getattr(Qt.MouseButton, "NoButton", getattr(Qt, "NoButton", 0))
        from unittest.mock import patch
        with patch.object(tool, "toLayerCoordinates", return_value=QgsPointXY(8, 7)):
            mouse_evt = QgsMapMouseEvent(canvas, evt_mouse_move, QPoint(100, 100), left_btn)
            tool.canvasMoveEvent(mouse_evt)

        # Verify Distance 1 and Distance 2 both updated dynamically
        self.assertAlmostEqual(tool.widget.distance1, 2.0, places=2)
        self.assertAlmostEqual(tool.widget.distance2, 3.0, places=2)

        tool.cleanup()
        if tool.widget:
            try:
                canvas.removeEventFilter(tool.widget)
            except (TypeError, RuntimeError):
                pass
            tool.widget.deleteLater()
        layer.rollBack()

    def test_merge_dialog_watcher_and_confirmation(self):
        from qgis.core import (
            QgsFeature,
            QgsField,
            QgsVectorLayer,
            QgsSettings,
        )
        from qgis.PyQt.QtCore import QEvent, QObject, QVariant, pyqtSignal
        from qgis.PyQt.QtWidgets import QAction, QDialog, QApplication, QPushButton
        from gui.two_line_map_tool import TwoLineMapTool, _MergeDialogWatcher

        # 1. Test _MergeDialogWatcher on Accepted, Rejected, and Button Disabling
        watcher = _MergeDialogWatcher()
        d_accept = QDialog()
        btn_remove = QPushButton("Remove feature from selection", d_accept)
        btn_remove.setObjectName("mButtonRemoveFeature")
        btn_remove.setToolTip("Remove feature from selection")

        app_inst = QApplication.instance()
        app_inst.installEventFilter(watcher)
        d_accept.show()

        self.assertFalse(btn_remove.isEnabled())

        d_accept.accept()
        d_accept.hide()
        app_inst.removeEventFilter(watcher)

        self.assertTrue(btn_remove.isEnabled())
        self.assertTrue(watcher.dialog_detected)
        self.assertTrue(watcher.accepted)

        watcher_reject = _MergeDialogWatcher()
        d_reject = QDialog()
        app_inst.installEventFilter(watcher_reject)
        d_reject.show()
        d_reject.reject()
        d_reject.hide()
        app_inst.removeEventFilter(watcher_reject)
        self.assertTrue(watcher_reject.dialog_detected)
        self.assertFalse(watcher_reject.accepted)

        # 2. Test _apply_two_line_operation with dialog simulation
        layer = QgsVectorLayer("LineString?crs=EPSG:3857", "test_merge_dialog", "memory")
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

        # Disable always_first to test dialog path
        s = QgsSettings()
        s.setValue("plugins/fillet/merge_always_first_feature", False)

        class MockIface(QObject):
            def __init__(self, main_win):
                super().__init__()
                self._win = main_win

            def mainWindow(self):
                return self._win

        # Mock action that simulates accepted QDialog
        mock_action = QAction("Merge", win)
        mock_action.setObjectName("mActionMergeFeatureAttributes")

        def simulate_dialog():
            dlg = QDialog(win)
            dlg.show()
            dlg.accept()
            dlg.hide()

        mock_action.triggered.connect(simulate_dialog)
        win.addAction(mock_action)

        mock_iface = MockIface(win)
        tool = TwoLineMapTool(canvas, iface=mock_iface)
        tool.activate()

        new_geom = QgsGeometry.fromPolylineXY([QgsPointXY(0, 10), QgsPointXY(8, 10), QgsPointXY(10, 8), QgsPointXY(10, 0)])
        tool._apply_two_line_operation(layer, 1, 2, new_geom)

        # Verify target feature 1 received new geometry and feature 2 was deleted
        feats = list(layer.getFeatures())
        self.assertEqual(len(feats), 1)
        self.assertEqual(feats[0].id(), 1)
        self.assertFalse(feats[0].geometry().isEmpty())

        win.removeAction(mock_action)
        tool.cleanup()
        if tool.widget:
            try:
                canvas.removeEventFilter(tool.widget)
            except (TypeError, RuntimeError):
                pass
            tool.widget.deleteLater()
        layer.rollBack()

    def test_extended_lines_have_no_duplicate_intermediate_endpoints(self):
        # Two short lines: (0, 10)->(5, 10) and (10, 0)->(10, 5)
        # Extensions meet at (10, 10). Tangent points: (8, 10) and (10, 8).
        l1 = QgsGeometry(QgsLineString([QgsPoint(0, 10), QgsPoint(5, 10)]))
        l2 = QgsGeometry(QgsLineString([QgsPoint(10, 0), QgsPoint(10, 5)]))

        res = GeometryEngine.fillet_or_chamfer_two_lines(
            l1, 0, QgsPoint(2, 10),
            l2, 0, QgsPoint(10, 2),
            mode="fillet", radius=2.0, segments_count=8
        )
        self.assertIsNotNone(res)
        geom, v, t1, t2 = res
        pts = geom.asPolyline()
        # Old endpoints (5, 10) and (10, 5) must not be in the resulting polyline
        for p in pts:
            self.assertFalse(abs(p.x() - 5.0) < 1e-4 and abs(p.y() - 10.0) < 1e-4)
            self.assertFalse(abs(p.x() - 10.0) < 1e-4 and abs(p.y() - 5.0) < 1e-4)

    def test_multisegment_polyline_intermediate_segment_preserves_topology(self):
        # Multi-segment line 1: (0, 0) -> (0, 5) -> (5, 10)
        # Line 2: (10, 0) -> (10, 20)
        l1_multi = QgsGeometry(QgsLineString([QgsPoint(0, 0), QgsPoint(0, 5), QgsPoint(5, 10)]))
        l2_multi = QgsGeometry(QgsLineString([QgsPoint(10, 0), QgsPoint(10, 20)]))

        res = GeometryEngine.fillet_or_chamfer_two_lines(
            l1_multi, 1, QgsPoint(2, 7),
            l2_multi, 0, QgsPoint(10, 5),
            mode="fillet", radius=2.0, segments_count=8
        )
        self.assertIsNotNone(res)
        geom, v, t1, t2 = res
        pts = geom.asPolyline()
        # Polyline start must preserve (0, 0) -> (0, 5)
        self.assertAlmostEqual(pts[0].x(), 0.0, places=4)
        self.assertAlmostEqual(pts[0].y(), 0.0, places=4)
        self.assertAlmostEqual(pts[1].x(), 0.0, places=4)
        self.assertAlmostEqual(pts[1].y(), 5.0, places=4)
        self.assertAlmostEqual(pts[-1].x(), 10.0, places=4)
        self.assertAlmostEqual(pts[-1].y(), 0.0, places=4)


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTwoLineFillet)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)

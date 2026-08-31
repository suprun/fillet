# -*- coding: utf-8 -*-
"""
Tests for settings persistence across sessions in FilletCanvasWidget and FilletSettingsWidget.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsSettings
from qgis.gui import QgsMapCanvas

app = QgsApplication([], False)
app.initQgis()

from gui.canvas_widget import FilletCanvasWidget
from gui.settings_widget import FilletSettingsWidget
from gui.align_feature_canvas_widget import AlignFeatureCanvasWidget, AlignReferenceMode
from gui.array_along_path_canvas_widget import (
    ArrayAlongPathCanvasWidget,
    PathDistributionMode,
    PathRangeMode,
)


class TestSettingsPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canvas = QgsMapCanvas()

    @classmethod
    def tearDownClass(cls):
        cls.canvas = None

    def setUp(self):
        self.settings = QgsSettings()
        # Clean settings prefix
        self.settings.remove("plugins/fillet")
        self.settings.remove("FilletPlugin/AlignReferenceMode")
        self.settings.remove("FilletPlugin/PathArrayDistribution")
        self.settings.remove("FilletPlugin/PathArrayRange")
        self.settings.remove("FilletPlugin/PathArrayCount")
        self.settings.remove("FilletPlugin/PathArraySpacing")
        self.settings.remove("FilletPlugin/PathArrayOffset")
        self.settings.remove("FilletPlugin/PathArrayIncludeStart")

    def tearDown(self):
        self.settings.remove("plugins/fillet")
        self.settings.remove("FilletPlugin/AlignReferenceMode")
        self.settings.remove("FilletPlugin/PathArrayDistribution")
        self.settings.remove("FilletPlugin/PathArrayRange")
        self.settings.remove("FilletPlugin/PathArrayCount")
        self.settings.remove("FilletPlugin/PathArraySpacing")
        self.settings.remove("FilletPlugin/PathArrayOffset")
        self.settings.remove("FilletPlugin/PathArrayIncludeStart")

    def test_align_and_path_array_settings_persistence(self):
        align = AlignFeatureCanvasWidget(self.canvas)
        align.set_reference_mode(AlignReferenceMode.Edges)
        second_align = AlignFeatureCanvasWidget(self.canvas)
        self.assertEqual(second_align.reference_mode(), AlignReferenceMode.Edges)

        path = ArrayAlongPathCanvasWidget(self.canvas)
        path.radio_spacing.setChecked(True)
        path.radio_subrange.setChecked(True)
        path.spin_count.setValue(9)
        path.spin_spacing.setValue(12.5)
        path.spin_offset.setValue(-3.25)
        path.chk_include_start.setChecked(False)
        restored = ArrayAlongPathCanvasWidget(self.canvas)
        self.assertEqual(restored.distribution_mode(), PathDistributionMode.Spacing)
        self.assertEqual(restored.range_mode(), PathRangeMode.Subrange)
        self.assertEqual(restored.count_value(), 9)
        self.assertAlmostEqual(restored.spacing_value(), 12.5)
        self.assertAlmostEqual(restored.offset_value(), -3.25)
        self.assertFalse(restored.include_start())

    def test_canvas_widget_persistence(self):
        # 1. Create first widget and change values
        w1 = FilletCanvasWidget(self.canvas)
        w1.radio_chamfer.setChecked(True)
        w1.spin_dist1.setValue(15.75)
        w1.spin_dist2.setValue(15.75)
        w1.btn_lock_dist1.setChecked(False)
        w1.btn_link.setChecked(False)
        w1.spin_radius.setValue(42.5)
        w1.spin_segments.setValue(32)
        w1.btn_lock_radius.setChecked(False)

        # Explicitly save
        w1._save_settings()

        # 2. Create second widget and verify it loads the persisted values
        w2 = FilletCanvasWidget(self.canvas)
        self.assertEqual(w2.mode, FilletCanvasWidget.MODE_CHAMFER)
        self.assertAlmostEqual(w2.spin_dist1.value(), 15.75, places=2)
        self.assertFalse(w2.btn_lock_dist1.isChecked())
        self.assertFalse(w2.btn_link.isChecked())
        self.assertAlmostEqual(w2.spin_radius.value(), 42.5, places=2)
        self.assertEqual(w2.spin_segments.value(), 32)
        self.assertFalse(w2.btn_lock_radius.isChecked())

    def test_settings_widget_persistence(self):
        # 1. Create first settings widget and change values
        sw1 = FilletSettingsWidget()
        sw1.radio_chamfer.setChecked(True)
        sw1.spin_dist1.setValue(25.5)
        sw1.spin_dist2.setValue(12.3)
        sw1.btn_link.setChecked(False)
        sw1.spin_radius.setValue(7.5)
        sw1.spin_segments.setValue(16)

        sw1._save_settings()

        # 2. Create second settings widget and verify values
        sw2 = FilletSettingsWidget()
        self.assertEqual(sw2.mode, FilletSettingsWidget.MODE_CHAMFER)
        self.assertAlmostEqual(sw2.distance1, 25.5, places=2)
        self.assertAlmostEqual(sw2.distance2, 12.3, places=2)
        self.assertFalse(sw2.btn_link.isChecked())
        self.assertAlmostEqual(sw2.radius, 7.5, places=2)
        self.assertEqual(sw2.segments_count, 16)

    def test_zero_values_persist_across_hud_and_crs_changes(self):
        canvas_widget = FilletCanvasWidget(self.canvas)
        canvas_widget.btn_link.setChecked(False)
        canvas_widget.spin_radius.setValue(0.0)
        canvas_widget.spin_dist1.setValue(0.0)
        canvas_widget.spin_dist2.setValue(0.0)
        canvas_widget._save_settings()

        restored_canvas = FilletCanvasWidget(self.canvas)
        for crs_auth_id in ("EPSG:4326", "EPSG:3857"):
            restored_canvas.adapt_to_crs(
                QgsCoordinateReferenceSystem(crs_auth_id)
            )
            self.assertEqual(restored_canvas.spin_radius.minimum(), 0.0)
            self.assertEqual(restored_canvas.spin_dist1.minimum(), 0.0)
            self.assertEqual(restored_canvas.spin_dist2.minimum(), 0.0)
            self.assertEqual(restored_canvas.radius, 0.0)
            self.assertEqual(restored_canvas.distance1, 0.0)
            self.assertEqual(restored_canvas.distance2, 0.0)

        settings_widget = FilletSettingsWidget()
        settings_widget.btn_link.setChecked(False)
        settings_widget.spin_radius.setValue(0.0)
        settings_widget.spin_dist1.setValue(0.0)
        settings_widget.spin_dist2.setValue(0.0)
        settings_widget._save_settings()

        restored_settings = FilletSettingsWidget()
        for crs_auth_id in ("EPSG:4326", "EPSG:3857"):
            restored_settings.adapt_to_crs(
                QgsCoordinateReferenceSystem(crs_auth_id)
            )
            self.assertEqual(restored_settings.spin_radius.minimum(), 0.0)
            self.assertEqual(restored_settings.spin_dist1.minimum(), 0.0)
            self.assertEqual(restored_settings.spin_dist2.minimum(), 0.0)
            self.assertEqual(restored_settings.radius, 0.0)
            self.assertEqual(restored_settings.distance1, 0.0)
            self.assertEqual(restored_settings.distance2, 0.0)

    def test_mode_switching_value_transfer(self):
        # Canvas widget transfer
        cw = FilletCanvasWidget(self.canvas)
        cw.radio_fillet.setChecked(True)
        cw.spin_radius.setValue(18.5)
        # Switch to chamfer
        cw.radio_chamfer.setChecked(True)
        self.assertAlmostEqual(cw.spin_dist1.value(), 18.5, places=2)
        # Change dist1 and switch back to fillet
        cw.spin_dist1.setValue(33.25)
        cw.radio_fillet.setChecked(True)
        self.assertAlmostEqual(cw.spin_radius.value(), 33.25, places=2)

        # Settings dock widget transfer
        sw = FilletSettingsWidget()
        sw.radio_fillet.setChecked(True)
        sw.spin_radius.setValue(14.2)
        # Switch to chamfer
        sw.radio_chamfer.setChecked(True)
        self.assertAlmostEqual(sw.spin_dist1.value(), 14.2, places=2)
        # Change dist1 and switch back to fillet
        sw.spin_dist1.setValue(45.0)
        sw.radio_fillet.setChecked(True)
        self.assertAlmostEqual(sw.spin_radius.value(), 45.0, places=2)


    def test_crs_adaptation(self):
        # Geographic CRS (degrees)
        geo_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        # Projected CRS (meters)
        proj_crs = QgsCoordinateReferenceSystem("EPSG:3857")

        cw = FilletCanvasWidget(self.canvas)
        cw.adapt_to_crs(geo_crs)
        self.assertEqual(cw.spin_radius.decimals(), 6)
        self.assertEqual(cw.spin_radius.minimum(), 0.0)
        self.assertAlmostEqual(cw.spin_radius.singleStep(), 0.00005, places=6)

        cw.adapt_to_crs(proj_crs)
        self.assertEqual(cw.spin_radius.decimals(), 3)
        self.assertEqual(cw.spin_radius.minimum(), 0.0)
        self.assertAlmostEqual(cw.spin_radius.singleStep(), 1.0, places=3)

        sw = FilletSettingsWidget()
        sw.adapt_to_crs(geo_crs)
        self.assertEqual(sw.spin_dist1.decimals(), 6)

        sw.adapt_to_crs(proj_crs)
        self.assertEqual(sw.spin_dist1.decimals(), 3)

    def test_numeric_input_validation(self):
        from qgis.PyQt.QtCore import QEvent, Qt
        from qgis.PyQt.QtGui import QKeyEvent, QValidator

        cw = FilletCanvasWidget(self.canvas)

        # 1. Test validator on lineEdit of spin_radius
        val_double = cw.spin_radius.lineEdit().validator()
        self.assertIsNotNone(val_double)
        # Check validation states
        res, _, _ = val_double.validate("12.34", 0)
        self.assertIn(res, (QValidator.State.Acceptable if hasattr(QValidator, "State") else QValidator.Acceptable,
                            QValidator.State.Intermediate if hasattr(QValidator, "State") else QValidator.Intermediate))
        res, _, _ = val_double.validate("abc", 0)
        self.assertEqual(res, QValidator.State.Invalid if hasattr(QValidator, "State") else QValidator.Invalid)

        # 2. Test validator on spin_segments
        val_int = cw.spin_segments.lineEdit().validator()
        self.assertIsNotNone(val_int)
        res, _, _ = val_int.validate("16", 0)
        self.assertIn(res, (QValidator.State.Acceptable if hasattr(QValidator, "State") else QValidator.Acceptable,
                            QValidator.State.Intermediate if hasattr(QValidator, "State") else QValidator.Intermediate))
        res, _, _ = val_int.validate("12.5", 0)
        self.assertEqual(res, QValidator.State.Invalid if hasattr(QValidator, "State") else QValidator.Invalid)

        # 3. Test key filtering on canvas widget
        key_a = QKeyEvent(getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None)), Qt.Key.Key_A if hasattr(Qt, "Key") else Qt.Key_A, Qt.KeyboardModifier.NoModifier if hasattr(Qt, "KeyboardModifier") else Qt.NoModifier, "a")
        key_5 = QKeyEvent(getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None)), Qt.Key.Key_5 if hasattr(Qt, "Key") else Qt.Key_5, Qt.KeyboardModifier.NoModifier if hasattr(Qt, "KeyboardModifier") else Qt.NoModifier, "5")
        key_dot = QKeyEvent(getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None)), Qt.Key.Key_Period if hasattr(Qt, "Key") else Qt.Key_Period, Qt.KeyboardModifier.NoModifier if hasattr(Qt, "KeyboardModifier") else Qt.NoModifier, ".")
        key_comma = QKeyEvent(getattr(QEvent.Type, "KeyPress", getattr(QEvent, "KeyPress", None)), Qt.Key.Key_Comma if hasattr(Qt, "Key") else Qt.Key_Comma, Qt.KeyboardModifier.NoModifier if hasattr(Qt, "KeyboardModifier") else Qt.NoModifier, ",")

        # Letters must be blocked (returns True)
        self.assertTrue(cw._handle_spin_key_press(cw.spin_radius, key_a))
        self.assertTrue(cw._handle_spin_key_press(cw.spin_segments, key_a))

        # Digits must be allowed (returns False)
        self.assertFalse(cw._handle_spin_key_press(cw.spin_radius, key_5))
        self.assertFalse(cw._handle_spin_key_press(cw.spin_segments, key_5))

        # Dot / Comma must be blocked for integer spin_segments
        self.assertTrue(cw._handle_spin_key_press(cw.spin_segments, key_dot))
        self.assertTrue(cw._handle_spin_key_press(cw.spin_segments, key_comma))

        # Dot / Comma for double spinbox: normalized and handled
        cw.spin_radius.lineEdit().setText("10")
        cw.spin_radius.lineEdit().selectAll()
        self.assertTrue(cw._handle_spin_key_press(cw.spin_radius, key_comma))


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSettingsPersistence)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)


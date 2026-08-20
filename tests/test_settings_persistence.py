# -*- coding: utf-8 -*-
"""
Tests for settings persistence across sessions in FilletCanvasWidget and FilletSettingsWidget.
"""

import unittest
from qgis.core import QgsCoordinateReferenceSystem, QgsSettings
from qgis.gui import QgsMapCanvas
from qgis.testing import start_app

start_app()

from gui.canvas_widget import FilletCanvasWidget
from gui.settings_widget import FilletSettingsWidget


class TestSettingsPersistence(unittest.TestCase):
    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.settings = QgsSettings()
        # Clean settings prefix
        self.settings.remove("plugins/fillet")

    def tearDown(self):
        self.settings.remove("plugins/fillet")

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
        self.assertAlmostEqual(cw.spin_radius.minimum(), 0.000001, places=6)

        cw.adapt_to_crs(proj_crs)
        self.assertEqual(cw.spin_radius.decimals(), 3)
        self.assertAlmostEqual(cw.spin_radius.minimum(), 0.001, places=3)

        sw = FilletSettingsWidget()
        sw.adapt_to_crs(geo_crs)
        self.assertEqual(sw.spin_dist1.decimals(), 6)

        sw.adapt_to_crs(proj_crs)
        self.assertEqual(sw.spin_dist1.decimals(), 3)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Tests for translation files and loading.
"""

import os
import unittest
from qgis.PyQt.QtCore import QCoreApplication, QTranslator
from qgis.testing import start_app

start_app()

from scripts.compile_translations import LANGUAGES, STRINGS


class TestTranslations(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.i18n_dir = os.path.join(self.base_dir, "i18n")

    def test_all_qm_files_exist_and_load(self):
        for lang in LANGUAGES:
            qm_path = os.path.join(self.i18n_dir, f"fillet_{lang}.qm")
            self.assertTrue(os.path.exists(qm_path), f"Missing {qm_path}")

            translator = QTranslator()
            loaded = translator.load(qm_path)
            self.assertTrue(loaded, f"Failed to load {qm_path}")

    def test_translation_resolution(self):
        # Test German
        de_qm = os.path.join(self.i18n_dir, "fillet_de.qm")
        translator = QTranslator()
        self.assertTrue(translator.load(de_qm))
        QCoreApplication.installTranslator(translator)

        res = QCoreApplication.translate("FilletSettingsWidget", "Параметри скруглення")
        self.assertEqual(res, "Abrundungsparameter")

        res_lock = QCoreApplication.translate("FilletCanvasWidget", "Блокувати / розблокувати радіус")
        self.assertEqual(res_lock, "Radius sperren / entsperren")

        QCoreApplication.removeTranslator(translator)

        # Test French
        fr_qm = os.path.join(self.i18n_dir, "fillet_fr.qm")
        translator_fr = QTranslator()
        self.assertTrue(translator_fr.load(fr_qm))
        QCoreApplication.installTranslator(translator_fr)

        res_fr = QCoreApplication.translate("FilletSettingsWidget", "Режим операції")
        self.assertEqual(res_fr, "Mode d'opération")

        QCoreApplication.removeTranslator(translator_fr)


if __name__ == "__main__":
    unittest.main()

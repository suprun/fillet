# -*- coding: utf-8 -*-
"""
Tests for translation files and loading.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication, QTranslator

app = QgsApplication([], False)
app.initQgis()

from scripts.compile_translations import LANGUAGES, STRINGS
from scripts.research_tools_translations import RESEARCH_STRINGS


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

    def test_research_tool_strings_are_present_in_all_catalogs(self):
        """Every new action, HUD, and message string is emitted to all 40 TS files."""
        import xml.etree.ElementTree as ET

        self.assertTrue(set(RESEARCH_STRINGS).issubset(STRINGS["FilletPlugin"]))
        required = set(RESEARCH_STRINGS)
        for lang in LANGUAGES:
            ts_path = os.path.join(self.i18n_dir, f"fillet_{lang}.ts")
            root = ET.parse(ts_path).getroot()
            sources = {
                source.text
                for source in root.findall("./context/message/source")
                if source.text
            }
            self.assertTrue(
                required.issubset(sources),
                f"Missing research-tool translations in {lang}",
            )

    def test_research_tool_english_resolution(self):
        translator = QTranslator()
        self.assertTrue(translator.load(os.path.join(self.i18n_dir, "fillet_en.qm")))
        QCoreApplication.installTranslator(translator)
        try:
            self.assertEqual(
                QCoreApplication.translate(
                    "FilletPlugin",
                    "CAD Вирівнювання об'єктів (Align Feature)",
                ),
                "CAD Align Feature",
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Весь шлях"),
                "Whole path",
            )
            self.assertEqual(
                QCoreApplication.translate(
                    "FilletPlugin",
                    "M/ZM and curved polygon geometries are not supported",
                ),
                "M/ZM and curved polygon geometries are not supported",
            )
        finally:
            QCoreApplication.removeTranslator(translator)

    def test_translation_resolution(self):
        # Test German
        de_qm = os.path.join(self.i18n_dir, "fillet_de.qm")
        translator = QTranslator()
        self.assertTrue(translator.load(de_qm))
        QCoreApplication.installTranslator(translator)

        res = QCoreApplication.translate("FilletPlugin", "Параметри скруглення")
        self.assertEqual(res, "Abrundungsparameter")

        res_lock = QCoreApplication.translate("FilletPlugin", "Блокувати / розблокувати радіус")
        self.assertEqual(res_lock, "Radius sperren / entsperren")

        QCoreApplication.removeTranslator(translator)

        # Test English
        en_qm = os.path.join(self.i18n_dir, "fillet_en.qm")
        translator_en = QTranslator()
        self.assertTrue(translator_en.load(en_qm))
        QCoreApplication.installTranslator(translator_en)

        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Відновлення кутів (Unfillet / Unchamfer)"),
            "Corner Restoration (Unfillet / Unchamfer)"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "1. Вкажіть перше ребро кута"),
            "1. Specify first corner edge"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "2. Вкажіть суміжне друге ребро"),
            "2. Specify adjacent second edge"
        )

        # Test Dock Panel translations in English
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Параметри Fillet / Chamfer"),
            "Fillet / Chamfer Settings"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Режим операції"),
            "Operation Mode"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Радіус (R):"),
            "Radius (R):"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Кількість сегментів дуги:"),
            "Arc segments count:"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Параметри фаски"),
            "Chamfer Parameters"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Відстань 1 (d1):"),
            "Distance 1 (d1):"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Відстань 2 (d2):"),
            "Distance 2 (d2):"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Застосувати до виділених об'єктів"),
            "Apply to Selected Features"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Застосувати скруглення або фаску до всіх вершин виділених об'єктів"),
            "Apply fillet or chamfer to all vertices of selected features"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Для пакетної обробки шар має бути у режимі редагування та містити виділені об'єкти"),
            "For batch processing, layer must be editable and contain selected features"
        )

        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Скруглення / фаска двох ліній (Merge)"),
            "Two-Line Fillet / Chamfer (Merge)"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "1. Вкажіть першу лінію"),
            "1. Specify first line"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "2. Вкажіть другу лінію"),
            "2. Specify second line"
        )
        self.assertEqual(
            QCoreApplication.translate("FilletPlugin", "Завжди використовувати атрибути першого об'єкта"),
            "Always use attributes of first feature"
        )
        self.assertEqual(
            QCoreApplication.translate(
                "FilletPlugin",
                "Ця операція недоступна для геометрій із кривими сегментами.",
            ),
            "This operation is unavailable for geometries with curved segments.",
        )
        self.assertEqual(
            QCoreApplication.translate(
                "FilletPlugin",
                "Не вдалося записати зміни: {error}",
            ),
            "Could not write changes: {error}",
        )

        QCoreApplication.removeTranslator(translator_en)

        # Test French
        fr_qm = os.path.join(self.i18n_dir, "fillet_fr.qm")
        translator_fr = QTranslator()
        self.assertTrue(translator_fr.load(fr_qm))
        QCoreApplication.installTranslator(translator_fr)

        res_fr = QCoreApplication.translate("FilletPlugin", "Режим операції")
        self.assertEqual(res_fr, "Mode d'opération")

        QCoreApplication.removeTranslator(translator_fr)

    def test_restore_hud_autosizing(self):
        from qgis.gui import QgsMapCanvas
        from gui.restore_canvas_widget import RestoreCanvasWidget

        canvas = QgsMapCanvas()
        canvas.resize(800, 600)

        # Install English translator
        en_qm = os.path.join(self.i18n_dir, "fillet_en.qm")
        translator_en = QTranslator()
        self.assertTrue(translator_en.load(en_qm))
        QCoreApplication.installTranslator(translator_en)

        try:
            hud = RestoreCanvasWidget(canvas)
            hud.set_step(RestoreCanvasWidget.STEP_FIRST_EDGE)
            self.assertEqual(hud.lbl_step.text(), "1. Specify first corner edge")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            hud.set_step(RestoreCanvasWidget.STEP_SECOND_EDGE)
            self.assertEqual(hud.lbl_step.text(), "2. Specify adjacent second edge")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())
            self.assertLessEqual(hud.x() + hud.width(), 800)
            self.assertGreaterEqual(hud.x(), 0)
        finally:
            QCoreApplication.removeTranslator(translator_en)
            canvas.deleteLater()

    def test_two_line_hud_autosizing(self):
        from qgis.gui import QgsMapCanvas
        from gui.canvas_widget import FilletCanvasWidget

        canvas = QgsMapCanvas()
        canvas.resize(800, 600)

        en_qm = os.path.join(self.i18n_dir, "fillet_en.qm")
        translator_en = QTranslator()
        self.assertTrue(translator_en.load(en_qm))
        QCoreApplication.installTranslator(translator_en)

        try:
            widget = FilletCanvasWidget(canvas)
            widget.set_two_line_mode(True)
            widget.mode = FilletCanvasWidget.MODE_FILLET
            widget.set_step(1)
            self.assertEqual(widget.lbl_step.text(), "1. Specify first line")
            self.assertGreaterEqual(widget.width(), widget.lbl_step.sizeHint().width())
            self.assertEqual(widget.x() + widget.width(), canvas.width())

            widget.set_step(2)
            self.assertEqual(widget.lbl_step.text(), "2. Specify second line")
            self.assertGreaterEqual(widget.width(), widget.lbl_step.sizeHint().width())
            self.assertEqual(widget.x() + widget.width(), canvas.width())

            widget.set_step(3)
            self.assertEqual(widget.lbl_step.text(), "3. Specify radius or click to confirm")

            widget.mode = FilletCanvasWidget.MODE_CHAMFER
            widget.set_step(3)
            self.assertEqual(widget.lbl_step.text(), "3. Specify chamfer or click to confirm")
        finally:
            QCoreApplication.removeTranslator(translator_en)
            canvas.deleteLater()

    def test_rotation_hud_translations_and_autosizing(self):
        from qgis.gui import QgsMapCanvas
        from gui.rotation_canvas_widget import RotationCanvasWidget

        canvas = QgsMapCanvas()
        canvas.resize(800, 600)

        en_qm = os.path.join(self.i18n_dir, "fillet_en.qm")
        translator_en = QTranslator()
        self.assertTrue(translator_en.load(en_qm))
        QCoreApplication.installTranslator(translator_en)

        try:
            hud = RotationCanvasWidget(canvas)
            hud.set_step(RotationCanvasWidget.STEP_PIVOT)
            self.assertEqual(hud.lbl_step.text(), "1. Specify center pivot")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            hud.set_step(RotationCanvasWidget.STEP_REFERENCE)
            self.assertEqual(hud.lbl_step.text(), "2. Specify reference baseline")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            hud.set_step(RotationCanvasWidget.STEP_ROTATING)
            self.assertEqual(hud.lbl_step.text(), "3. Specify rotation angle")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "CAD Обертання (Rotate)"),
                "CAD Rotate"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Кут (Angle):"),
                "Angle:"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Крок кута:"),
                "Snap step:"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Вільний (Free)"),
                "Free"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Зберегти копію (Copy)"),
                "Save copy (Copy)"
            )
        finally:
            QCoreApplication.removeTranslator(translator_en)
            canvas.deleteLater()

    def test_mirror_hud_translations_and_autosizing(self):
        """Verify CAD Mirror HUD step texts, labels, and auto-sizing in English."""
        from gui.mirror_canvas_widget import MirrorCanvasWidget

        canvas = QgsMapCanvas()
        canvas.resize(800, 600)

        en_qm = os.path.join(self.i18n_dir, "fillet_en.qm")
        translator_en = QTranslator()
        self.assertTrue(translator_en.load(en_qm))
        QCoreApplication.installTranslator(translator_en)

        try:
            hud = MirrorCanvasWidget(canvas)
            hud.set_step(MirrorCanvasWidget.STEP_FIRST_POINT)
            self.assertEqual(hud.lbl_step.text(), "1. Specify first axis point")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            hud.set_step(MirrorCanvasWidget.STEP_SECOND_POINT)
            self.assertEqual(hud.lbl_step.text(), "2. Specify second axis point")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "CAD Дзеркало (Mirror)"),
                "CAD Mirror"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Кут осі:"),
                "Axis angle:"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Блокувати кут осі / інтерактивне обрання"),
                "Lock axis angle / interactive pick"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Прив'язка осі:"),
                "Axis snap:"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "90° (Орто)"),
                "90° (Ortho)"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "CAD Дзеркальне відображення"),
                "CAD Mirror"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "CAD Дзеркальне копіювання"),
                "CAD Mirror Copy"
            )
        finally:
            QCoreApplication.removeTranslator(translator_en)
            canvas.deleteLater()

    def test_scale_rotate_hud_translations_and_autosizing(self):
        """Verify CAD Scale & Rotate HUD step texts, labels, and auto-sizing in English."""
        from gui.scale_rotate_canvas_widget import ScaleRotateCanvasWidget

        canvas = QgsMapCanvas()
        canvas.resize(800, 600)

        en_qm = os.path.join(self.i18n_dir, "fillet_en.qm")
        translator_en = QTranslator()
        self.assertTrue(translator_en.load(en_qm))
        QCoreApplication.installTranslator(translator_en)

        try:
            hud = ScaleRotateCanvasWidget(canvas)
            hud.set_step(ScaleRotateCanvasWidget.STEP_ORIGIN)
            self.assertEqual(hud.lbl_step.text(), "1. Click origin pivot point")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            hud.set_step(ScaleRotateCanvasWidget.STEP_REFERENCE)
            self.assertEqual(hud.lbl_step.text(), "2. Click reference base point")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            hud.set_step(ScaleRotateCanvasWidget.STEP_TARGET)
            self.assertEqual(hud.lbl_step.text(), "3. Click target scale & angle")
            self.assertGreaterEqual(hud.width(), hud.lbl_step.sizeHint().width())
            self.assertEqual(hud.x() + hud.width(), canvas.width())

            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "CAD Масштаб та Обертання (Scale & Rotate)"),
                "CAD Scale & Rotate"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Масштаб (Scale):"),
                "Scale:"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Блокувати масштаб / вільний розрахунок"),
                "Lock scale / free interactive calculation"
            )
            self.assertEqual(
                QCoreApplication.translate("FilletPlugin", "Кут:"),
                "Angle:"
            )
        finally:
            QCoreApplication.removeTranslator(translator_en)
            canvas.deleteLater()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTranslations)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    app.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)

# Структура проєкту Fillet Toolkit for QGIS

Плагін розроблений за модульною архітектурою з чітким розділенням ядра геометричних алгоритмів, графічного інтерфейсу (CAD Map Tools & HUD Canvas Widgets), тестів, локалізацій та скриптів автоматизації.

> [!TIP]
> **Для AI-асистентів:** Використовуйте цю мапу для точкового доступу до файлів. Не вичитуйте великі файли повністю без потреби, застосовуйте `grep_search` та читання діапазонів рядків.

---

## 1. Кореневі файли (Root)

- `plugin.py` — головний клас плагіна (`FilletPlugin`), життєвий цикл (`initGui`, `unload`), реєстрація панелей інструментів (Advanced Digitizing), меню, підключення сигналів шарів та ініціалізація інструментів.
- `__init__.py` — фабрика плагіна для QGIS (`classFactory`).
- `metadata.txt` — метадані плагіна для QGIS Plugin Repository (версія, опис, сумісність QGIS 3.16–4.99, changelog, авторство).
- `AGENTS.md` — інструкції та правила для AI-асистентів і розробки.
- `STRUCTURE.md` — цей документ (актуальна мапа файлів та модулів проєкту).
- `README.md` — документація користувача, опис можливостей та історія змін.
- `LICENSE` — ліцензія (MIT / GPL).
- `icon.png` / `icon.svg` — головна іконка плагіна (CAD PRO badge).
- `symbology-style.db` — вбудована база стилів умовних знаків.
- `dist/` — директорія готових пакетів:
  - `dist/fillet.zip` — скомпільований runtime-архів плагіна (без кешу та тестових файлів).
  - `dist/plugins.xml` — локальний репозиторій для тестування встановлення та оновлення у QGIS.

---

## 2. `core/` — Ядро та геометричні алгоритми

Центральний математичний та топологічний рушій плагіна:

- `core/geometry_engine.py` — головний файл математики геометрії (~150 КБ). Містить алгоритми:
  - скруглення кутів (Fillet) та фаски (Chamfer);
  - злиття двох ліній (Two-Line Fillet/Chamfer);
  - відновлення гострих кутів (Unfillet / Unchamfer);
  - паралельний зсув ребер (Edge Offset у режимах Extend та Step);
  - 3-точкова ротація (CAD Rotate), 2-точкове віддзеркалення (CAD Mirror), масштабування з поворотом (Scale & Rotate);
  - лінійне тиражування (Feature Array) та круговий масив (Polar Array);
  - поділ та вимірювання ліній (Divide / Measure Line);
  - розбиття ліній на сегменти (Explode Line);
  - ортогоналізація кутів будівель відносно фасаду (Ortho Angles);
  - очищення дублікатів вузлів та усунення самоперетинів (Clean Duplicate Nodes / Untangle);
  - робота з Z/M/ZM координатами та політиками кривих (CompoundCurve/CircularString).
- `core/snapping_helper.py` — інтеграція із системою прив'язки QGIS (point/segment snapping, `QgsSnapIndicator`, трансформації CRS).
- `core/constants.py` — глобальні константи режимів, кольори гумових стрічок (RubberBand) та налаштування за замовчуванням.

---

## 3. `gui/` — Інструменти карти (Map Tools) та плаваючі HUD-панелі

Кожен інтерактивний CAD-інструмент складається з пари: `*_map_tool.py` (логіка взаємодії з картою та подіями миші) та `*_canvas_widget.py` (плаваючий HUD-віджет з числовими полями, гарячими клавішами та пресетами).

- `gui/gui_utils.py` — допоміжні утиліти UI, завантаження іконок, DPI-масштабування, стиль панелей QGIS.
- `gui/settings_widget.py` — бічна панель (DockWidget) пакетної обробки (Batch Fillet & Chamfer).
- **Fillet & Chamfer (класичний):**
  - `gui/map_tool.py` — базовий та інтерактивний інструмент скруглення кутів полігонів/ліній.
  - `gui/canvas_widget.py` — HUD-панель налаштування радіуса та фаски.
- **Two-Line Fillet/Chamfer (Merge):**
  - `gui/two_line_map_tool.py` — злиття та скруглення двох окремих ліній з підтримкою діалогу об'єднання атрибутів.
- **Corner Restoration:**
  - `gui/restore_map_tool.py` — інструмент відновлення кутів (Unfillet/Unchamfer).
  - `gui/restore_canvas_widget.py` — HUD-підказки кроків відновлення.
- **CAD Rotate:**
  - `gui/rotate_map_tool.py` — 3-точкова ротація об'єктів.
  - `gui/rotation_canvas_widget.py` — HUD кута повороту, прив'язки та збереження копії.
- **CAD Mirror:**
  - `gui/mirror_map_tool.py` — 2-точкове симетричне віддзеркалення.
  - `gui/mirror_canvas_widget.py` — HUD осі симетрії.
- **CAD Scale & Rotate:**
  - `gui/scale_rotate_map_tool.py` — 3-точкове масштабування з поворотом.
  - `gui/scale_rotate_canvas_widget.py` — HUD коефіцієнта масштабу та кута.
- **CAD Edge Offset:**
  - `gui/edge_offset_map_tool.py` — паралельний зсув ребер (Extend / Step).
  - `gui/edge_offset_canvas_widget.py` — HUD відстані зсуву та перемикання режимів.
- **CAD Feature Array:**
  - `gui/array_map_tool.py` — копіювання об'єктів масивом вздовж лінії.
  - `gui/array_canvas_widget.py` — HUD кількості копій та інтервалу.
- **CAD Polar Array:**
  - `gui/polar_array_map_tool.py` — круговий масив об'єктів навколо центру.
  - `gui/polar_array_canvas_widget.py` — HUD кутового кроку, кута заповнення та обертання копій.
- **CAD Divide Line:**
  - `gui/divide_line_map_tool.py` — поділ та вимірювання ліній.
  - `gui/divide_line_canvas_widget.py` — HUD кількості частин або фіксованої довжини сегмента.
- **CAD Explode Line:**
  - `gui/explode_map_tool.py` — розбиття ліній на 2-точкові сегменти.
  - `gui/explode_canvas_widget.py` — HUD пакетного розбиття виділених ліній.
- **CAD Ortho Angles:**
  - `gui/ortho_angles_map_tool.py` — ортогоналізація кутів будівель (прямі кути 90°) відносно опорного ребра.
  - `gui/ortho_angles_canvas_widget.py` — HUD толерантності кута та збереження площі.
- **Clean Duplicate Nodes:**
  - `gui/clean_duplicate_nodes_map_tool.py` — пошук та усунення дублікатів вершин і вузлів самоперетинів.

---

## 4. `research/` — Дослідження та специфікації майбутніх інструментів

Директорія містить аналітику, архітектурні концепції та специфікації для проектування нових CAD-інструментів:

- `align_feature_ctrl_shift_qgis_tool.md` — дослідження інструмента вирівнювання об'єктів (Align Feature) за опорними точками/ребрами.
- `array_along_path_qgis_tool.md` — специфікація тиражування об'єктів вздовж складних криволінійних траєкторій (Array along path).
- `extract_part_ctrl_shift_qgis_tool.md` — концепція швидкого вилучення/відокремлення частин складених геометрій (Extract Part).
- `match_edge_qgis_tool.md` — дослідження інструмента точного підгону та сполучення суміжних ребер (Match Edge).
- `subtract_clip_feature_qgis_tools.md` — аналіз інструментів просторового віднімання, вирізання та обрізки геометрій (Subtract / Clip Feature).

---

## 5. `tests/` — Модульні та інтеграційні тести

- `tests/test_geometry.py` — перевірка математики `geometry_engine` та граничних випадків.
- `tests/test_plugin_lifecycle.py` — тести життєвого циклу плагіна (`initGui`/`unload`), меню, відсутності витоків пам'яті.
- `tests/test_settings_persistence.py` — збереження параметрів у `QgsSettings`.
- `tests/test_translations.py` — валідність завантаження файлів перекладу `.qm`.
- `tests/test_*_tool.py` — ізольовані тести для кожного CAD-інструмента (array, clean duplicates, divide line, edge offset, explode, mirror, ortho angles, polar array, rotate, scale rotate, two-line fillet).

---

## 6. `scripts/` — Автоматизація, пакування та збірка

- `scripts/package_plugin.py` — збірка чистого `dist/fillet.zip` із переліком тільки runtime-файлів.
- `scripts/sync_to_profiles.py` — синхронізація плагіна у профілі QGIS3 та QGIS4 (`%APPDATA%/QGIS/...`).
- `scripts/smoke_test_all_qgis.py` — крос-версійний запуск тестів у всіх знайдених версіях QGIS (Windows).
- `scripts/compile_translations.py` — компіляція `.ts` $\rightarrow$ `.qm`.
- `scripts/add_*_translations.py` — допоміжні генератори перекладів нових інструментів для всіх 40 мов.

---

## 7. `resources/` та `i18n/` — Ресурси та локалізація

- `resources/icons/` — робочі векторні SVG-іконки дій, інструментів панелі та HUD-віджетів.
- `resources/` — вихідні іконки та графічні елементи.
- `i18n/` — повна локалізація плагіна на 40 офіційних мов QGIS (`fillet_<код>.ts` та скомпільовані `fillet_<код>.qm`).

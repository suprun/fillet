# Структура проєкту Fillet & Chamfer Toolkit for QGIS

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
- `icon.png` / `icon.svg` — головна іконка плагіна.
- `dist/` — директорія готових пакетів:
  - `dist/fillet.zip` — скомпільований runtime-архів плагіна (без кешу та тестових файлів).
  - `dist/plugins.xml` — локальний репозиторій для тестування встановлення та оновлення у QGIS.

---

## 2. `core/` — Ядро та геометричні алгоритми

Центральний математичний та топологічний рушій плагіна:

- `core/geometry_engine.py` — головний файл математики геометрії. Містить алгоритми:
  - скруглення кутів (Fillet) та фаски (Chamfer) для полігонів та поліліній;
  - єдину zero-size семантику: гострий кут з одним вузлом та односторонню фаску для незв'язаних `0 / positive` відстаней;
  - злиття та скруглення двох ліній (Two-Line Fillet/Chamfer);
  - відновлення гострих кутів (Two-Edge Corner Restoration / Unfillet & Unchamfer);
  - пакетну обробку кутів (Batch Fillet & Chamfer);
  - роботу з Z/M/ZM координатами та політиками кривих (CompoundCurve/CircularString).
- `core/snapping_helper.py` — інтеграція із системою прив'язки QGIS (point/segment snapping, `QgsSnapIndicator`, міжшарові `LayerFeatureMatch` / `LayerSegmentMatch`, трансформації CRS).
- `core/constants.py` — глобальні константи режимів, кольори гумових стрічок (RubberBand) та налаштування за замовчуванням.

---

## 3. `gui/` — Інструменти карти (Map Tools) та плаваючі HUD-панелі

Інтерактивні інструменти плагіна:

- `gui/gui_utils.py` — допоміжні утиліти UI, контекстні менеджери атомарних транзакцій (`checked_edit_command`), DPI-масштабування, стиль панелей QGIS.
- `gui/settings_widget.py` — бічна панель (DockWidget) пакетної обробки (Batch Fillet & Chamfer) для QGIS >= 4.
- **Fillet & Chamfer (класичний інструмент вершин):**
  - `gui/map_tool.py` — інтерактивний інструмент скруглення / фаски окремих вершин полігонів та поліліній у реальному часі.
  - `gui/canvas_widget.py` — плаваюча HUD-панель налаштування радіуса та фаски з блокуванням, перемиканням режимів та кнопкою пакетного застосування до виділених об'єктів.
- **Two-Line Fillet/Chamfer (Merge):**
  - `gui/two_line_map_tool.py` — злиття та скруглення двох окремих ліній з підтримкою діалогу об'єднання атрибутів.
- **Corner Restoration:**
  - `gui/restore_map_tool.py` — інструмент відновлення гострих кутів (Unfillet/Unchamfer) за двома суміжними сегментами (для QGIS < 4 об'єднаний у випадаюче меню з Fillet/Chamfer).
  - `gui/restore_canvas_widget.py` — HUD-підказки кроків відновлення.

---

## 4. `tests/` — Модульні та інтеграційні тести

- `tests/test_geometry.py` — перевірка математики `geometry_engine`, zero-size семантики, Z/M збереження та граничних випадків.
- `tests/test_plugin_lifecycle.py` — тести життєвого циклу плагіна (`initGui`/`unload`), стану дій, меню, відсутності витоків пам'яті.
- `tests/test_settings_persistence.py` — збереження параметрів у `QgsSettings`.
- `tests/test_two_line_fillet.py` — повне тестування інструменту злиття та скруглення двох ліній.
- `tests/test_translations.py` — валідність завантаження файлів перекладу `.qm`.

---

## 5. `scripts/` — Автоматизація, пакування та збірка

- `scripts/package_plugin.py` — збірка чистого `dist/fillet.zip` із переліком тільки runtime-файлів.
- `scripts/sync_to_profiles.py` — синхронізація плагіна у профілі QGIS3 та QGIS4 (`%APPDATA%/QGIS/...`).
- `scripts/smoke_test_all_qgis.py` — крос-версійний запуск тестів у всіх знайдених версіях QGIS (Windows).
- `scripts/compile_translations.py` — компіляція `.ts` $\rightarrow$ `.qm`.

---

## 6. `resources/` та `i18n/` — Ресурси та локалізація

- `resources/icons/` — векторні SVG-іконки дій та HUD-віджетів:
  - `mActionChamferFillet.svg` — інтерактивний інструмент Fillet/Chamfer;
  - `mActionChamferFilletBatch.svg` — панель пакетної обробки;
  - `mActionRestoreCorners.svg` — відновлення кутів;
  - `mActionTwoLineFillet.svg` — скруглення/фаска двох ліній;
  - `fillet.svg`, `chamfer.svg`, `locked.svg`, `unlocked.svg`, `mActionLink.svg`, `mActionUnlink.svg` — іконки HUD-панелей.
- `i18n/` — повна локалізація плагіна на 40 офіційних мов QGIS (`fillet_<код>.ts` та скомпільовані `fillet_<код>.qm`).

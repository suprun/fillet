# -*- coding: utf-8 -*-
"""Translations introduced by the six CAD research tools.

The repository translation builder uses English as the established fallback
when a locale has no dedicated wording.  Every entry is therefore emitted to
all 40 TS/QM catalogs while Ukrainian and English remain explicit.
"""


def _localized(english, ukrainian=None):
    return {
        "uk": ukrainian if ukrainian is not None else english,
        "en": english,
    }


RESEARCH_STRINGS = {
    # Actions and tooltips
    "CAD Вирівнювання об'єктів (Align Feature)": _localized("CAD Align Feature"),
    "Вирівнювання вибраних об'єктів за двома точками або ребрами": _localized(
        "Align selected features using two points or edges"
    ),
    "Перемістити, повернути або масштабувати всю вибрану групу за двома точками чи ребрами": _localized(
        "Move, rotate, or scale the entire selected group using two points or edges"
    ),
    "CAD Суміщення ребра (Match Edge)": _localized("CAD Match Edge"),
    "Паралельне або колінеарне суміщення ребра вибраних об'єктів": _localized(
        "Match an edge of selected features in parallel or collinear mode"
    ),
    "Локально виправити одне ребро без переміщення інших вершин об'єкта": _localized(
        "Locally reshape one edge without moving the feature's other vertices"
    ),
    "CAD Масив уздовж шляху (Array Along Path)": _localized("CAD Array Along Path"),
    "Створення копій вибраної групи вздовж лінійної траєкторії": _localized(
        "Create copies of the selected group along a line path"
    ),
    "CAD Вилучення частини (Extract Part)": _localized("CAD Extract Part"),
    "Вилучення або копіювання частини multipart feature": _localized(
        "Extract or copy a part of a multipart feature"
    ),
    "CAD Віднімання об'єкта (Subtract Feature)": _localized("CAD Subtract Feature"),
    "Віднімання геометрії Cutter від полігона Target": _localized(
        "Subtract Cutter geometry from the Target polygon"
    ),
    "CAD Обрізання об'єкта (Clip Feature)": _localized("CAD Clip Feature"),
    "Збереження частини полігона Target всередині Cutter": _localized(
        "Keep the part of the Target polygon inside Cutter"
    ),
    # Shared labels and modes
    "Align Feature": _localized("Align Feature"),
    "Match Edge": _localized("Match Edge"),
    "Array Along Path": _localized("Array Along Path"),
    "Extract Part": _localized("Extract Part"),
    "Subtract Feature": _localized("Subtract Feature"),
    "Clip Feature": _localized("Clip Feature"),
    "Source:": _localized("Source:"),
    "Target:": _localized("Target:"),
    "Cutters:": _localized("Cutters:"),
    "Режим:": _localized("Mode:"),
    "Кут:": _localized("Angle:"),
    "Довжина:": _localized("Length:"),
    "Об'єкти:": _localized("Features:"),
    "Уся вибрана група": _localized("Entire selected group"),
    "Масштаб:": _localized("Scale:"),
    "Зсув:": _localized("Offset:"),
    "Переміщення": _localized("Move"),
    "Переміщення + масштаб": _localized("Move + scale"),
    "Копія": _localized("Copy"),
    "Копія + масштаб": _localized("Copy + scale"),
    "Копія / ": _localized("Copy / "),
    "Редагування / ": _localized("Edit / "),
    "Колінеарний": _localized("Collinear"),
    "Паралельний": _localized("Parallel"),
    "Одиночний": _localized("Single"),
    "Безперервний": _localized("Continuous"),
    # Align Feature HUD and messages
    "Точки (Points)": _localized("Points"),
    "Ребра (Edges)": _localized("Edges"),
    "1. Вкажіть першу опорну точку Source": _localized("1. Specify first Source reference point"),
    "2. Вкажіть другу опорну точку Source": _localized("2. Specify second Source reference point"),
    "1. Вкажіть ребро вибраного Source": _localized("1. Specify an edge of the selected Source"),
    "3. Вкажіть першу опорну точку Target": _localized("3. Specify first Target reference point"),
    "4. Вкажіть другу точку Target для підтвердження": _localized(
        "4. Specify second Target point to confirm"
    ),
    "2. Вкажіть ребро Target для підтвердження": _localized("2. Specify Target edge to confirm"),
    "CAD Вирівнювання (Align Feature)": _localized("CAD Align Feature"),
    "Виберіть об'єкти в редагованому шарі.": _localized("Select features in the editable layer."),
    "Опорні точки Source мають відрізнятися.": _localized("Source reference points must be different."),
    "Вкажіть ребро одного з вибраних об'єктів.": _localized(
        "Specify an edge of one of the selected features."
    ),
    "Вкажіть ребро Target з видимого шару.": _localized("Specify a Target edge from a visible layer."),
    "CAD Align Feature(s)": _localized("CAD Align Feature(s)"),
    "Не вдалося додати вирівняні копії.": _localized("Could not add aligned copies."),
    "Не вдалося вирівняти геометрію.": _localized("Could not align geometry."),
    # Match Edge HUD and messages
    "CAD Суміщення ребра (Match Edge)": _localized("CAD Match Edge"),
    "1. Вкажіть пряме ребро вибраного Source": _localized(
        "1. Specify a straight edge of the selected Source"
    ),
    "2. Вкажіть інше пряме ребро Target": _localized(
        "2. Specify another straight Target edge"
    ),
    "Виберіть лінійні або полігональні об'єкти в редагованому шарі.": _localized(
        "Select line or polygon features in the editable layer."
    ),
    "Вкажіть пряме ребро одного з вибраних об'єктів.": _localized(
        "Specify a straight edge of one of the selected features."
    ),
    "Криволінійна геометрія Source не підтримується.": _localized(
        "Curved Source geometry is not supported."
    ),
    "Не вдалося прочитати Source feature.": _localized(
        "Could not read the Source feature."
    ),
    "Вкажіть інше пряме ребро Target з видимого шару.": _localized(
        "Specify another straight Target edge from a visible layer."
    ),
    "Криволінійна геометрія Target не підтримується.": _localized(
        "Curved Target geometry is not supported."
    ),
    "Не вдалося додати локально виправлену копію.": _localized(
        "Could not add the locally reshaped copy."
    ),
    "Не вдалося локально виправити ребро.": _localized(
        "Could not locally reshape the edge."
    ),
    "Не вдалося додати суміщені копії.": _localized("Could not add matched copies."),
    "Не вдалося сумістити геометрію.": _localized("Could not match geometry."),
    "CAD Match Edge": _localized("CAD Match Edge"),
    # Array Along Path HUD and messages
    "Кількість": _localized("Count"),
    "Крок": _localized("Spacing"),
    "Весь шлях": _localized("Whole path"),
    "Піддіапазон": _localized("Subrange"),
    "Зсув (Offset):": _localized("Offset:"),
    "Включити початкову позицію": _localized("Include start position"),
    "Копій:": _localized("Copies:"),
    "Орієнтація:": _localized("Orientation:"),
    "Напрямок:": _localized("Direction:"),
    "Фіксована": _localized("Fixed"),
    "Дотична": _localized("Tangent"),
    "Прямий": _localized("Forward"),
    "Зворотний": _localized("Reverse"),
    "1. Вкажіть Anchor вибраної групи": _localized("1. Specify the selected group's Anchor"),
    "2. Вкажіть лінійний Path": _localized("2. Specify a line Path"),
    "3. Вкажіть початок піддіапазону": _localized("3. Specify subrange start"),
    "4. Вкажіть кінець піддіапазону": _localized("4. Specify subrange end"),
    "Enter або клік — створити масив": _localized("Press Enter or click to create the array"),
    "CAD Масив уздовж шляху": _localized("CAD Array Along Path"),
    "Вкажіть непорожню лінійну частину Path.": _localized("Specify a non-empty line part for Path."),
    "Початок і кінець піддіапазону мають відрізнятися.": _localized(
        "Subrange start and end must be different."
    ),
    "Поточні параметри не створюють жодної копії.": _localized(
        "The current parameters do not create any copies."
    ),
    "CAD Array Along Path": _localized("CAD Array Along Path"),
    "Не вдалося створити масив уздовж шляху.": _localized("Could not create the array along the path."),
    # Extract Part HUD and messages
    "Вибрано частин:": _localized("Selected parts:"),
    "Клацніть частину; Shift — множинний вибір": _localized(
        "Click a part; use Shift for multiple selection"
    ),
    "Вкажіть multipart feature у поточному шарі.": _localized(
        "Specify a multipart feature in the current layer."
    ),
    "Завершіть або скасуйте поточний набір частин.": _localized(
        "Complete or cancel the current set of parts."
    ),
    "Щонайменше одна частина має залишитися у Source.": _localized(
        "At least one part must remain in Source."
    ),
    "Не вдалося оновити multipart Source.": _localized("Could not update multipart Source."),
    "Не вдалося створити вилучені частини.": _localized("Could not create the extracted parts."),
    "CAD Extract Part": _localized("CAD Extract Part"),
    # Boolean HUD and messages
    "1. Вкажіть Target для віднімання": _localized("1. Specify Target for subtraction"),
    "1. Вкажіть Target для обрізання": _localized("1. Specify Target for clipping"),
    "2. Вкажіть Cutter або Shift-кліком додайте набір": _localized(
        "2. Specify Cutter or Shift-click to build a set"
    ),
    "Вкажіть полігон Target у поточному редагованому шарі.": _localized(
        "Specify a Target polygon in the current editable layer."
    ),
    "Вкажіть полігон Cutter з видимого шару.": _localized("Specify a Cutter polygon from a visible layer."),
    "Результат був би порожнім; Target не змінено.": _localized(
        "The result would be empty; Target was not changed."
    ),
    "Геометрії не перекриваються; Target не змінено.": _localized(
        "The geometries do not overlap; Target was not changed."
    ),
    "Multipart результат несумісний із singlepart Target layer.": _localized(
        "A multipart result is incompatible with the singlepart Target layer."
    ),
    "Не вдалося змінити геометрію Target.": _localized("Could not change Target geometry."),
    "CAD Subtract Feature": _localized("CAD Subtract Feature"),
    "CAD Clip Feature": _localized("CAD Clip Feature"),
    # Geometry-engine errors translated at the map-tool boundary
    "Source reference must have a non-zero length": _localized(
        "Source reference must have a non-zero length",
        "Опорний відрізок Source повинен мати ненульову довжину",
    ),
    "Target reference must have a non-zero length": _localized(
        "Target reference must have a non-zero length",
        "Опорний відрізок Target повинен мати ненульову довжину",
    ),
    "Scale factor must be greater than zero": _localized(
        "Scale factor must be greater than zero",
        "Коефіцієнт масштабу повинен бути більшим за нуль",
    ),
    "Geometry translation failed": _localized(
        "Geometry translation failed", "Не вдалося перемістити геометрію"
    ),
    "Source edge must have a non-zero length": _localized(
        "Source edge must have a non-zero length", "Ребро Source повинно мати ненульову довжину"
    ),
    "Target edge must have a non-zero length": _localized(
        "Target edge must have a non-zero length", "Ребро Target повинно мати ненульову довжину"
    ),
    "Source edge index is out of range": _localized(
        "Source edge index is out of range", "Індекс ребра Source поза діапазоном"
    ),
    "Source geometry must be linear or polygonal": _localized(
        "Source geometry must be linear or polygonal",
        "Геометрія Source повинна бути лінійною або полігональною",
    ),
    "Source geometry is empty": _localized(
        "Source geometry is empty", "Геометрія Source порожня"
    ),
    "Target line does not intersect the adjacent source edge": _localized(
        "Target line does not intersect the adjacent source edge",
        "Пряма Target не перетинає суміжне ребро Source",
    ),
    "Could not construct the matched source edge": _localized(
        "Could not construct the matched source edge",
        "Не вдалося побудувати виправлене ребро Source",
    ),
    "Matched source edge would collapse": _localized(
        "Matched source edge would collapse", "Виправлене ребро Source виродиться"
    ),
    "Matched source edge would reverse": _localized(
        "Matched source edge would reverse", "Виправлене ребро Source змінить порядок вершин"
    ),
    "Matched source edge would collapse an adjacent edge": _localized(
        "Matched source edge would collapse an adjacent edge",
        "Виправлене ребро Source виродить суміжне ребро",
    ),
    "Native curved source geometries are not supported": _localized(
        "Native curved source geometries are not supported",
        "Нативні криволінійні геометрії Source не підтримуються",
    ),
    "Native curved target geometries are not supported": _localized(
        "Native curved target geometries are not supported",
        "Нативні криволінійні геометрії Target не підтримуються",
    ),
    "Source geometry is invalid": _localized(
        "Source geometry is invalid", "Геометрія Source невалідна"
    ),
    "Source edge must be a straight segment": _localized(
        "Source edge must be a straight segment", "Ребро Source повинно бути прямим сегментом"
    ),
    "Matched source geometry is empty": _localized(
        "Matched source geometry is empty", "Виправлена геометрія Source порожня"
    ),
    "Matched source geometry is invalid": _localized(
        "Matched source geometry is invalid", "Виправлена геометрія Source невалідна"
    ),
    "Source feature is not selected": _localized(
        "Source feature is not selected", "Feature Source не вибрано"
    ),
    "Source feature is not available": _localized(
        "Source feature is not available", "Feature Source недоступний"
    ),
    "Source and Target edges are required": _localized(
        "Source and Target edges are required", "Потрібно вказати ребра Source і Target"
    ),
    "Could not read the matched source edge": _localized(
        "Could not read the matched source edge", "Не вдалося прочитати виправлене ребро Source"
    ),
    "Path must have a non-zero length": _localized(
        "Path must have a non-zero length", "Path повинен мати ненульову довжину"
    ),
    "Could not interpolate the selected path": _localized(
        "Could not interpolate the selected path", "Не вдалося інтерполювати вибраний Path"
    ),
    "Could not determine the path tangent": _localized(
        "Could not determine the path tangent", "Не вдалося визначити дотичну до Path"
    ),
    "Array path must be a line geometry": _localized(
        "Array path must be a line geometry", "Path масиву повинен бути лінійною геометрією"
    ),
    "Unsupported path distribution mode": _localized(
        "Unsupported path distribution mode", "Непідтримуваний режим розподілу вздовж Path"
    ),
    "Geometry part index is out of range": _localized(
        "Geometry part index is out of range", "Індекс частини геометрії поза діапазоном"
    ),
    "Target geometry is empty": _localized("Target geometry is empty", "Геометрія Target порожня"),
    "Target geometry must be polygonal": _localized(
        "Target geometry must be polygonal", "Геометрія Target повинна бути полігональною"
    ),
    "M/ZM and curved polygon geometries are not supported": _localized(
        "M/ZM and curved polygon geometries are not supported",
        "Полігональні геометрії M/ZM і з кривими сегментами не підтримуються",
    ),
    "Target geometry is invalid": _localized("Target geometry is invalid", "Геометрія Target невалідна"),
    "At least one cutter is required": _localized(
        "At least one cutter is required", "Потрібен щонайменше один Cutter"
    ),
    "Cutter geometry must be polygonal": _localized(
        "Cutter geometry must be polygonal", "Геометрія Cutter повинна бути полігональною"
    ),
    "Cutter geometry is invalid": _localized("Cutter geometry is invalid", "Геометрія Cutter невалідна"),
    "At least one non-empty cutter is required": _localized(
        "At least one non-empty cutter is required", "Потрібен щонайменше один непорожній Cutter"
    ),
    "Cutter union is invalid": _localized("Cutter union is invalid", "Об'єднання Cutter невалідне"),
    "Unsupported polygon boolean operation": _localized(
        "Unsupported polygon boolean operation", "Непідтримувана булева операція над полігонами"
    ),
    "Polygon boolean operation failed": _localized(
        "Polygon boolean operation failed", "Булева операція над полігонами не виконана"
    ),
    "Polygon boolean result is invalid": _localized(
        "Polygon boolean result is invalid", "Результат булевої операції над полігонами невалідний"
    ),
    "Geometry must be polygonal": _localized(
        "Geometry must be polygonal", "Геометрія повинна бути полігональною"
    ),
    "Geometry is invalid": _localized("Geometry is invalid", "Геометрія невалідна"),
}

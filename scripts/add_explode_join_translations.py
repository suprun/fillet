# -*- coding: utf-8 -*-
"""
Helper script to merge CAD Explode Line and CAD Join Lines strings into compile_translations.py and compile QM files.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

EXPLODE_JOIN_STRINGS = {
    "CAD Розбиття лінії (Explode)": {
        'uk': "CAD Розбиття лінії (Explode)",
        'en': "CAD Explode Line",
        'de': "CAD Linie auflösen (Explode)",
        'fr': "Décomposer la ligne CAD (Explode)",
        'es': "Descomponer línea CAD (Explode)",
        'it': "Esplodi linea CAD (Explode)",
        'pl': "Rozbij linię CAD (Explode)",
    },
    "Інтерактивний CAD інструмент розбиття ліній на окремі сегменти або складові частини (multipart)": {
        'uk': "Інтерактивний CAD інструмент розбиття ліній на окремі сегменти або складові частини (multipart)",
        'en': "Interactive CAD tool to split lines into individual segments or multipart components",
        'de': "Interaktives CAD-Werkzeug zum Teilen von Linien in einzelne Segmente oder mehrteilige Komponenten",
        'fr': "Outil CAD interactif pour diviser des lignes en segments individuels ou composants multi-parties",
        'es': "Herramienta CAD interactiva para dividir líneas en segmentos individuales o componentes multiparte",
        'it': "Strumento CAD interattivo per dividere linee in segmenti individuali o parti composte",
        'pl': "Interaktywne narzędzie CAD do rozbijania linii na pojedyncze segmenty lub obiekty wieloczęściowe",
    },
    "CAD З'єднання ліній (Join)": {
        'uk': "CAD З'єднання ліній (Join)",
        'en': "CAD Join Lines",
        'de': "CAD Linien verbinden (Join)",
        'fr': "Joindre des lignes CAD (Join)",
        'es': "Unir líneas CAD (Join)",
        'it': "Unisci linee CAD (Join)",
        'pl': "Połącz linie CAD (Join)",
    },
    "Інтерактивний CAD інструмент топологічного з'єднання суміжних ліній у неперервні полілінії": {
        'uk': "Інтерактивний CAD інструмент топологічного з'єднання суміжних ліній у неперервні полілінії",
        'en': "Interactive CAD tool to topologically chain and join adjacent lines into continuous polylines",
        'de': "Interaktives CAD-Werkzeug zum topologischen Verbinden benachbarter Linien zu durchgehenden Polylinien",
        'fr': "Outil CAD interactif pour enchaîner et joindre topologiquement des lignes adjacentes en polylignes continues",
        'es': "Herramienta CAD interactiva para encadenar y unir topológicamente líneas adyacentes en polilíneas continuas",
        'it': "Strumento CAD interattivo per unire topologicamente linee adiacenti in polilinee continue",
        'pl': "Interaktywne narzędzie CAD do topologicznego łączenia sąsiednich linii w ciągłe polilinie",
    },
    "1. Оберіть лінію для розбиття на відрізки": {
        'uk': "1. Оберіть лінію для розбиття на відрізки",
        'en': "1. Select a line to explode into segments",
        'de': "1. Linie zum Auflösen in Segmente auswählen",
        'fr': "1. Sélectionnez une ligne à décomposer en segments",
        'es': "1. Seleccione una línea para descomponer en segmentos",
        'it': "1. Seleziona una linea da esplodere in segmenti",
        'pl': "1. Wybierz linię do rozbicia na segmenty",
    },
    "Зберегти як складену геометрію (multipart)": {
        'uk': "Зберегти як складену геометрію (multipart)",
        'en': "Save as multipart geometry",
        'de': "Als mehrteilige Geometrie speichern (multipart)",
        'fr': "Enregistrer comme géométrie multi-parties",
        'es': "Guardar como geometría multiparte",
        'it': "Salva come geometria multiparte",
        'pl': "Zapisz jako geometrię wieloczęściową (multipart)",
    },
    "Зберегти розбиті відрізки як частини єдиного об'єкта (MultiLineString)": {
        'uk': "Зберегти розбиті відрізки як частини єдиного об'єкта (MultiLineString)",
        'en': "Save exploded segments as parts of a single object (MultiLineString)",
        'de': "Aufgelöste Segmente als Teile eines einzelnen Objekts (MultiLineString) speichern",
        'fr': "Enregistrer les segments décomposés comme parties d'un objet unique (MultiLineString)",
        'es': "Guardar segmentos descompuestos como partes de un solo objeto (MultiLineString)",
        'it': "Salva i segmenti esplosi come parti di un singolo oggetto (MultiLineString)",
        'pl': "Zapisz rozbite segmenty jako części pojedynczego obiektu (MultiLineString)",
    },
    "Зберегти розбиті відрізки як частини єдиного складеного об'єкта (MultiLineString)": {
        'uk': "Зберегти розбиті відрізки як частини єдиного складеного об'єкта (MultiLineString)",
        'en': "Save exploded segments as parts of a single multipart object (MultiLineString)",
        'de': "Aufgelöste Segmente als Teile eines einzelnen mehrteiligen Objekts (MultiLineString) speichern",
        'fr': "Enregistrer les segments décomposés comme parties d'un objet multi-parties unique (MultiLineString)",
        'es': "Guardar segmentos descompuestos como partes de un solo objeto multiparte (MultiLineString)",
        'it': "Salva i segmenti esplosi come parti di un singolo oggetto multiparte (MultiLineString)",
        'pl': "Zapisz rozbite segmenty jako części pojedynczego obiektu wieloczęściowego (MultiLineString)",
    },
    "Шар є SinglePart (LineString) і не підтримує multipart": {
        'uk': "Шар є SinglePart (LineString) і не підтримує multipart",
        'en': "Layer is SinglePart (LineString) and does not support multipart",
        'de': "Layer ist SinglePart (LineString) und unterstützt keine mehrteiligen Geometrien",
        'fr': "La couche est SinglePart (LineString) et ne prend pas en charge le multi-parties",
        'es': "La capa es SinglePart (LineString) y no admite multiparte",
        'it': "Il layer è SinglePart (LineString) e non supporta il multiparte",
        'pl': "Warstwa jest SinglePart (LineString) i nie obsługuje obiektów wieloczęściowych",
    },
    "Розбити виділені лінії": {
        'uk': "Розбити виділені лінії",
        'en': "Explode selected lines",
        'de': "Ausgewählte Linien auflösen",
        'fr': "Décomposer les lignes sélectionnées",
        'es': "Descomponer líneas seleccionadas",
        'it': "Esplodi linee selezionate",
        'pl': "Rozbij zaznaczone linie",
    },
    "Розбити виділені лінії ({})": {
        'uk': "Розбити виділені лінії ({})",
        'en': "Explode selected lines ({})",
        'de': "Ausgewählte Linien auflösen ({})",
        'fr': "Décomposer les lignes sélectionnées ({})",
        'es': "Descomponer líneas seleccionadas ({})",
        'it': "Esplodi linee selezionate ({})",
        'pl': "Rozbij zaznaczone linie ({})",
    },
    "Розбиття ліній на складові частини (multipart)": {
        'uk': "Розбиття ліній на складові частини (multipart)",
        'en': "Explode lines to multipart components",
        'de': "Linien in mehrteilige Komponenten auflösen",
        'fr': "Décomposer des lignes en composants multi-parties",
        'es': "Descomponer líneas en componentes multiparte",
        'it': "Esplodi linee in componenti multiparte",
        'pl': "Rozbicie linii na części składowe (multipart)",
    },
    "Розбиття ліній на окремі відрізки": {
        'uk': "Розбиття ліній на окремі відрізки",
        'en': "Explode lines into separate segments",
        'de': "Linien in separate Segmente auflösen",
        'fr': "Décomposer des lignes en segments séparés",
        'es': "Descomponer líneas en segmentos separados",
        'it': "Esplodi linee in segmenti separati",
        'pl': "Rozbicie linii na osobne segmenty",
    },
    "Успішно розбито {} об'єктів на {} відрізків": {
        'uk': "Успішно розбито {} об'єктів на {} відрізків",
        'en': "Successfully exploded {} feature(s) into {} segments",
        'de': "{} Objekt(e) erfolgreich in {} Segmente aufgelöst",
        'fr': "{} entité(s) décomposée(s) avec succès en {} segments",
        'es': "{} entidad(es) descompuesta(s) con éxito en {} segmentos",
        'it': "{} elemento/i esploso/i con successo in {} segmenti",
        'pl': "Pomyślnie rozbito {} obiekt(ów) na {} segmentów",
    },
    "CAD Explode Line": {
        'uk': "CAD Explode Line",
        'en': "CAD Explode Line",
        'de': "CAD Explode Line",
        'fr': "CAD Explode Line",
        'es': "CAD Explode Line",
        'it': "CAD Explode Line",
        'pl': "CAD Explode Line",
    },
    "1. Оберіть першу лінію для з'єднання": {
        'uk': "1. Оберіть першу лінію для з'єднання",
        'en': "1. Select first line to join",
        'de': "1. Erste Linie zum Verbinden auswählen",
        'fr': "1. Sélectionnez la première ligne à joindre",
        'es': "1. Seleccione la primera línea para unir",
        'it': "1. Seleziona la prima linea da unire",
        'pl': "1. Wybierz pierwszą linię do połączenia",
    },
    "2. Оберіть суміжні лінії (Enter для фіксації)": {
        'uk': "2. Оберіть суміжні лінії (Enter для фіксації)",
        'en': "2. Select adjacent lines (Enter to commit)",
        'de': "2. Angrenzende Linien auswählen (Eingabetaste zum Bestätigen)",
        'fr': "2. Sélectionnez les lignes adjacentes (Entrée pour valider)",
        'es': "2. Seleccione líneas adyacentes (Enter para confirmar)",
        'it': "2. Seleziona linee adiacenti (Invio per confermare)",
        'pl': "2. Wybierz sąsiednie linie (Enter, aby zatwierdzić)",
    },
    "Допуск вузлів:": {
        'uk': "Допуск вузлів:",
        'en': "Node tolerance:",
        'de': "Knotentoleranz:",
        'fr': "Tolérance des nœuds :",
        'es': "Tolerancia de nodos:",
        'it': "Tolleranza nodi:",
        'pl': "Tolerancja węzłów:",
    },
    "З'єднати виділені лінії": {
        'uk': "З'єднати виділені лінії",
        'en': "Join selected lines",
        'de': "Ausgewählte Linien verbinden",
        'fr': "Joindre les lignes sélectionnées",
        'es': "Unir líneas seleccionadas",
        'it': "Unisci linee selezionate",
        'pl': "Połącz zaznaczone linie",
    },
    "З'єднати виділені лінії ({})": {
        'uk': "З'єднати виділені лінії ({})",
        'en': "Join selected lines ({})",
        'de': "Ausgewählte Linien verbinden ({})",
        'fr': "Joindre les lignes sélectionnées ({})",
        'es': "Unir líneas seleccionadas ({})",
        'it': "Unisci linee selezionate ({})",
        'pl': "Połącz zaznaczone linie ({})",
    },
    "З'єднання ліній у полілінію": {
        'uk': "З'єднання ліній у полілінію",
        'en': "Join lines into polyline",
        'de': "Linien zu Polylinie verbinden",
        'fr': "Joindre des lignes en polyligne",
        'es': "Unir líneas en polilínea",
        'it': "Unisci linee in polilinea",
        'pl': "Połączenie linii w polilinię",
    },
    "З'єднання виділених ліній": {
        'uk': "З'єднання виділених ліній",
        'en': "Join selected lines",
        'de': "Ausgewählte Linien verbinden",
        'fr': "Joindre les lignes sélectionnées",
        'es': "Unir líneas seleccionadas",
        'it': "Unisci linee selezionate",
        'pl': "Połączenie zaznaczonych linii",
    },
    "CAD Join Lines": {
        'uk': "CAD Join Lines",
        'en': "CAD Join Lines",
        'de': "CAD Join Lines",
        'fr': "CAD Join Lines",
        'es': "CAD Join Lines",
        'it': "CAD Join Lines",
        'pl': "CAD Join Lines",
    },
    "Успішно з'єднано {} ліній в єдину полілінію": {
        'uk': "Успішно з'єднано {} ліній в єдину полілінію",
        'en': "Successfully joined {} lines into a single polyline",
        'de': "{} Linien erfolgreich zu einer einzigen Polylinie verbunden",
        'fr': "{} lignes jointes avec succès en une seule polyligne",
        'es': "{} líneas unidas con éxito en una sola polilínea",
        'it': "{} linee unite con successo in una singola polilinea",
        'pl': "Pomyślnie połączono {} linii w jedną polilinię",
    },
    "Успішно з'єднано {} виділених ліній в {} поліліній": {
        'uk': "Успішно з'єднано {} виділених ліній в {} поліліній",
        'en': "Successfully joined {} selected lines into {} polylines",
        'de': "{} ausgewählte Linien erfolgreich zu {} Polylinien verbunden",
        'fr': "{} lignes sélectionnées jointes avec succès en {} polylignes",
        'es': "{} líneas seleccionadas unidas con éxito en {} polilíneas",
        'it': "{} linee selezionate unite con successo in {} polilinee",
        'pl': "Pomyślnie połączono {} zaznaczonych linii w {} polilinii",
    },
}

def main():
    compile_script = os.path.join(os.path.dirname(__file__), "compile_translations.py")
    with open(compile_script, "r", encoding="utf-8") as f:
        content = f.read()

    target_anchor = 'STRINGS = {\n    "FilletPlugin": {'
    if target_anchor not in content:
        print("Could not find STRINGS anchor in compile_translations.py")
        return 1

    # Format new strings
    entries = []
    for source_text, lang_dict in EXPLODE_JOIN_STRINGS.items():
        escaped_source = source_text.replace('"', '\\"')
        if f'"{escaped_source}":' in content or f"'{escaped_source}':" in content:
            continue
        entry = f'        "{escaped_source}": {{\n'
        for lang, trans in lang_dict.items():
            escaped_trans = trans.replace('"', '\\"')
            entry += f'            "{lang}": "{escaped_trans}",\n'
        entry += "        },\n"
        entries.append(entry)

    if entries:
        replacement = target_anchor + "\n" + "".join(entries)
        content = content.replace(target_anchor, replacement, 1)
        with open(compile_script, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Added {len(entries)} translation keys to compile_translations.py")
    else:
        print("All explode/join translation keys are already present in compile_translations.py")

    import compile_translations
    compile_translations.compile_all()
    print("Recompiled all .qm translation files.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

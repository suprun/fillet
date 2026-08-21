# -*- coding: utf-8 -*-
import sys
import os

STEP_TRANSLATIONS = {
    "FilletCanvasWidget": {
        "Крок 1: Клікніть на перше ребро кута": {
            "en": "Step 1: Click on the first edge of corner",
            "uk": "Крок 1: Клікніть на перше ребро кута",
            "de": "Schritt 1: Klicken Sie auf die erste Kante der Ecke",
            "fr": "Étape 1 : Cliquez sur le premier bord de l'angle",
            "es": "Paso 1: Haga clic en el primer borde de la esquina",
            "it": "Passaggio 1: Fai clic sul primo bordo dell'angolo",
            "pl": "Krok 1: Kliknij pierwszą krawędź narożnika",
            "pt": "Passo 1: Clique na primeira aresta do canto",
            "pt_BR": "Passo 1: Clique na primeira aresta do canto",
            "nl": "Stap 1: Klik op de eerste rand van de hoek",
            "zh": "步骤 1：单击角的第一个边",
            "zh_CN": "步骤 1：单击角的第一个边",
            "zh_TW": "步驟 1：點擊角的第一個邊",
            "ja": "ステップ1：角の最初の辺をクリック",
            "cs": "Krok 1: Klikněte na první hranu rohu",
            "hu": "1. lépés: Kattintson a sarok első élére",
            "ro": "Pasul 1: Faceți clic pe prima latură a colțului",
            "fi": "Vaihe 1: Napsauta kulman ensimmäistä reunaa",
            "sv": "Steg 1: Klicka på hörnets första segment",
            "da": "Trin 1: Klik på hjørnets første kant",
            "tr": "Adım 1: Köşenin ilk kenarına tıklayın",
            "ko": "1단계: 모서리의 첫 번째 가장자리를 클릭하세요",
            "el": "Βήμα 1: Κάντε κλικ στην πρώτη ακμή της γωνίας",
            "lt": "1 žingsnis: spustelėkite pirmąją kampo briauną",
            "lv": "1. solis: noklikšķiniet uz stūra pirmās malas",
            "et": "1. samm: klõpsake nurga esimesel serval",
            "sk": "Krok 1: Kliknite na prvú hranu rohu",
            "sl": "1. korak: Kliknite prvi rob vogala",
            "bg": "Стъпка 1: Щракнете върху първия ръб на ъгъла",
            "hr": "1. korak: Kliknite na prvi rub kuta",
            "sr": "Корак 1: Кликните на прву ивицу угла",
            "ca": "Pas 1: Feu clic a la primera aresta de la cantonada",
            "eu": "1. urratsa: Egin klik izkinaren lehen ertzean",
            "gl": "Paso 1: Prema na primeira aresta da esquina",
            "nb": "Trinn 1: Klikk på det første segmentet av hjørnet",
            "ar": "الخطوة 1: انقر فوق الحافة الأولى للزاوية",
            "id": "Langkah 1: Klik tepi pertama sudut",
            "vi": "Bước 1: Nhấp vào cạnh đầu tiên của góc",
            "th": "ขั้นตอนที่ 1: คลิกที่ขอบแรกของมุม",
            "hi": "चरण 1: कोने के पहले किनारे पर क्लिक करें",
        },
        "Крок 2: Клікніть на суміжне друге ребро (ПКМ — скасувати)": {
            "en": "Step 2: Click on the adjacent second edge (RMB to cancel)",
            "uk": "Крок 2: Клікніть на суміжне друге ребро (ПКМ — скасувати)",
            "de": "Schritt 2: Klicken Sie auf die benachbarte zweite Kante (RMB zum Abbrechen)",
            "fr": "Étape 2 : Cliquez sur le deuxième bord adjacent (Clic droit pour annuler)",
            "es": "Paso 2: Haga clic en el segundo borde adyacente (Clic derecho para cancelar)",
            "it": "Passaggio 2: Fai clic sul secondo bordo adiacente (Tasto destro per annullare)",
            "pl": "Krok 2: Kliknij sąsiednią drugą krawędź (PPM, aby anulować)",
            "pt": "Passo 2: Clique na segunda aresta adjacente (Botão direito para cancelar)",
            "pt_BR": "Passo 2: Clique na segunda aresta adjacente (Botão direito para cancelar)",
            "nl": "Stap 2: Klik op de aangrenzende tweede rand (RMB om te annuleren)",
            "zh": "步骤 2：单击相邻的第二个边（右键取消）",
            "zh_CN": "步骤 2：单击相邻的第二个边（右键取消）",
            "zh_TW": "步驟 2：點擊相鄰的第二個邊（右鍵取消）",
            "ja": "ステップ2：隣接する2番目の辺をクリック（右クリックでキャンセル）",
            "cs": "Krok 2: Klikněte na sousední druhou hranu (Pravé tlačítko pro zrušení)",
            "hu": "2. lépés: Kattintson a szomszédos második élre (Jobb gomb a megszakításhoz)",
            "ro": "Pasul 2: Faceți clic pe a doua latură adiacentă (Clic dreapta pentru anulare)",
            "fi": "Vaihe 2: Napsauta viereistä toista reunaa (Oikea painike peruu)",
            "sv": "Steg 2: Klicka på det intilliggande andra segmentet (Högerklicka för att avbryta)",
            "da": "Trin 2: Klik på den tilstødende anden kant (Højreklik for at annullere)",
            "tr": "Adım 2: Bitişik ikinci kenara tıklayın (İptal için sağ tıklayın)",
            "ko": "2단계: 인접한 두 번째 가장자리를 클릭하세요 (취소하려면 마우스 오른쪽 버튼 클릭)",
            "el": "Βήμα 2: Κάντε κλικ στη γειτονική δεύτερη ακμή (Δεξί κλικ για ακύρωση)",
            "lt": "2 žingsnis: spustelėkite gretimą antrąją briauną (Dešinysis pelės mygtukas atšaukti)",
            "lv": "2. solis: noklikšķiniet uz blakus esošās otrās malas (Labais klikšķis, lai atceltu)",
            "et": "2. samm: klõpsake külgneval teisel serval (Tühistamiseks paremklõps)",
            "sk": "Krok 2: Kliknite na susednú druhú hranu (Pravé tlačidlo pre zrušenie)",
            "sl": "2. korak: Kliknite sosednji drugi rob (Desni klik za preklic)",
            "bg": "Стъпка 2: Щракнете върху съседния втори ръб (Десен бутон за отказ)",
            "hr": "2. korak: Kliknite na susjedni drugi rub (Desni klik za odustajanje)",
            "sr": "Корак 2: Кликните на суседну другу ивицу (Десни клик за отказивање)",
            "ca": "Pas 2: Feu clic a la segona aresta adjacent (Clic dret per cancel·lar)",
            "eu": "2. urratsa: Egin klik ondoko bigarren ertzean (Eskuin-klika bertan behera uzteko)",
            "gl": "Paso 2: Prema na segunda aresta adxacente (Botón dereito para cancelar)",
            "nb": "Trinn 2: Klikk på det tilstøtende andre segmentet (Høyreklikk for å avbryte)",
            "ar": "الخطوة 2: انقر فوق الحافة المجاورة الثانية (زر الفأرة الأيمن للإلغاء)",
            "id": "Langkah 2: Klik tepi kedua yang berdekatan (Klik kanan untuk membatalkan)",
            "vi": "Bước 2: Nhấp vào cạnh thứ hai liền kề (Nhấp chuột phải để hủy)",
            "th": "ขั้นตอนที่ 2: คลิกที่ขอบที่สองที่อยู่ติดกัน (คลิกขวาเพื่อยกเลิก)",
            "hi": "चरण 2: आसन्न दूसरे किनारे पर क्लिक करें (रद्द करने के लिए दायां क्लिक करें)",
        },
    }
}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compile_translations

for ctx, items in STEP_TRANSLATIONS.items():
    if ctx not in compile_translations.STRINGS:
        compile_translations.STRINGS[ctx] = {}
    for src, trans in items.items():
        compile_translations.STRINGS[ctx][src] = trans

compile_translations.compile_all()
print("Successfully compiled all step translations!")

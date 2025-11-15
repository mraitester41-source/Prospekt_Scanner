# penny_perplexity_only.py
# NUR Perplexity → 100% Produktname, Preis, Grundpreis, App-Preis
# Kein OpenCV, kein OCR, kein Box-Matching

import requests
from PIL import Image
import json
import base64
import sqlite3
import pandas as pd
import os
import re
import io
from datetime import datetime

# === CONFIG ===
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    print("FEHLER: config.json nicht gefunden!")
    exit(1)

API_KEY = config["perplexity_api_key"]
MODEL = config["model"]
DB_PATH = config.get("db_path", "penny_perplexity.sqlite")
CSV_PATH = config.get("csv_path", "penny_perplexity.csv")

print("PENNY PERPLEXITY ONLY – Maximale Produktabdeckung")

# === DATENBANK MIGRATION ===
def migrate_database():
    """Fügt fehlende Spalten zur bestehenden Datenbank hinzu"""
    if not os.path.exists(DB_PATH):
        return  # Neue DB, keine Migration nötig

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Prüfe, ob angebote-Tabelle existiert
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='angebote'")
        if not cursor.fetchone():
            conn.close()
            return

        # Hole bestehende Spalten
        cursor.execute("PRAGMA table_info(angebote)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        # Füge fehlende Spalten hinzu
        new_columns = {
            'gueltig_von': 'TEXT',
            'gueltig_bis': 'TEXT',
            'gueltigkeitstext': 'TEXT',
            'bild_beschreibung': 'TEXT'
        }

        for col_name, col_type in new_columns.items():
            if col_name not in existing_columns:
                print(f"  Migration: Füge Spalte '{col_name}' hinzu...")
                cursor.execute(f"ALTER TABLE angebote ADD COLUMN {col_name} {col_type}")

        conn.commit()
        print("  ✓ Datenbank-Migration abgeschlossen")
    except Exception as e:
        print(f"  Fehler bei Migration: {e}")
    finally:
        conn.close()

# === BILD LADEN ===
def download_image(url, path):
    if not os.path.exists(path):
        print(f"  Lade: {path}")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(path, 'wb') as f:
            f.write(r.content)

# === PERPLEXITY: ALLE PRODUKTE + DETAILS ===
def get_products_perplexity(image_path):
    pil_image = Image.open(image_path).convert("RGB")
    w, h = pil_image.size
    buffer = io.BytesIO()
    pil_image.save(buffer, format='JPEG', quality=95)
    b64 = base64.b64encode(buffer.getvalue()).decode()

    prompt = f"""
Du bist ein Experte für visuelle Produktbeschreibungen. Analysiere dieses PENNY-Prospekt ({w}x{h} Pixel).

Finde **ALLE** Produkte – auch kleine, auch oben/unten.
Für jedes Produkt:
- name: voller Name (z. B. "Mühlenhof Frisches Hackfleisch gemischt")
- preis: Aktionspreis (z. B. "5,99 €")
- app_preis: mit App (z. B. "3,49 €" oder leer)
- grundpreis: 1 kg = ... (z. B. "1 kg = 7,99 €" oder leer)
- bild_beschreibung: SEHR DETAILLIERTE Beschreibung für KI-Bildgenerierung (siehe Beispiele unten)
- seite: Seitenzahl aus Dateinamen (z. B. "4")

WICHTIG für bild_beschreibung - Beschreibe ALLE visuellen Details:

1. VERPACKUNG:
   - Exakte Farben (Hauptfarbe, Akzentfarben, Farbverläufe)
   - Material-Optik (glänzend, matt, transparent, Folie)
   - Form und Größe der Verpackung
   - Logo-Position, Schriftarten, Textelemente
   - Muster, Illustrationen auf der Verpackung

2. PRODUKT-DARSTELLUNG:
   - Wenn MEHRERE Ansichten (z.B. roh UND gekocht):
     * Beschreibe JEDE Ansicht separat
     * Gib Position an (links/rechts, oben/unten)
     * Größenverhältnis zwischen den Ansichten
   - Farbe, Textur, Aussehen des Produkts
   - Zustand (roh, gekocht, gebraten, garniert)
   - Arrangement, Platzierung

3. LAYOUT & KOMPOSITION:
   - Wo befindet sich was im Bild (Vordergrund/Hintergrund)
   - Größenverhältnisse
   - Hintergrundfarbe oder -gestaltung
   - Schatten, Lichteffekte

4. ZUSÄTZLICHE ELEMENTE:
   - Garnierung, Beilagen
   - Dekorative Elemente
   - Dampf, Frische-Indikatoren
   - Qualitätssiegel, Badges

BEISPIELE für gute Beschreibungen:

Beispiel 1 (einfach):
"Rechteckige Verpackung in kräftigem Rot mit weißem Markenlogo oben links. Transparentes Sichtfenster in der Mitte zeigt frisches, rosa-rotes Hackfleisch mit feiner Körnung. Gelbes Gewichts-Label '400g' unten rechts. Verpackung hat glänzende Folien-Optik. Weißer Hintergrund, leichter Schlagschatten unter der Verpackung."

Beispiel 2 (mit mehreren Ansichten):
"Zwei Produktdarstellungen: LINKS (60% der Bildfläche): Tiefgefrorenes Schnitzel in hellblauer Frostverpackung mit silbernem Schriftzug, liegt flach, eisige Kristalle sichtbar. RECHTS (40% der Bildfläche): Fertig gebratenes goldbraunes Schnitzel auf weißem Teller, knusprige Panade mit Luftblasen, dampfend, garniert mit Zitronenscheibe und Petersilie. Beide auf hellem Untergrund, leichte Überlappung in der Mitte. Warme Beleuchtung beim gebratenen Schnitzel, kühles Licht beim gefrorenen."

Beispiel 3 (komplex):
"Quadratische Premium-Verpackung, tiefes Bordeauxrot mit goldenen Verzierungen an den Ecken. Großes kreisförmiges Sichtfenster (Durchmesser ca. 40% der Vorderseite) zeigt drei Teilstücke Fleisch in sattem Dunkelrot mit weißer Marmorierung. Goldener Schriftzug 'Premium Selection' in verschnörkelter Schrift oben mittig. Kleine grüne Rosmarin-Illustration unten links. Verpackung steht leicht schräg (15° gedreht), wodurch auch die rechte Seite sichtbar ist. Hintergrund: dunkler Holztisch mit sichtbarer Maserung. Weiches Studiolicht von links oben, erzeugt Glanzpunkte auf der Folie."

- Ignoriere Werbung, Logos, Überschriften
- Nur echte Produkte mit Preis
- Beschreibung MUSS mindestens 100 Wörter haben
- Je mehr Details, desto besser für KI-Bildgenerierung
- Kein Code-Block, kein Markdown → NUR reines JSON
- Format: {{"products": [{{ "name": "...", "preis": "...", "app_preis": "...", "grundpreis": "...", "bild_beschreibung": "...", "seite": "..." }}]}}

Bild: {os.path.basename(image_path)}
"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}],
        "max_tokens": 6000,  # Erhöht für ausführliche Bildbeschreibungen
        "temperature": 0.0
    }

    try:
        print(f"  Sende Anfrage an Perplexity...")
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
            timeout=180
        )
        r.raise_for_status()
        raw = r.json()['choices'][0]['message']['content']

        # Robuster JSON-Extraktor
        start = raw.find('{')
        end = raw.rfind('}') + 1
        if start == -1 or end == 0:
            print(f"  KEIN JSON gefunden in: {raw[:200]}...")
            return []

        json_str = raw[start:end]
        data = json.loads(json_str)
        products = data.get("products", [])

        # Seite aus Dateinamen
        page_num = os.path.basename(image_path).split('_')[1].split('.')[0]
        for p in products:
            p["seite"] = page_num

        return products

    except Exception as e:
        print(f"  Perplexity Fehler: {e}")
        return []

# === SPEICHERN: DB + CSV ===
def save_results(results, validity_info=None):
    if not results:
        return
    df = pd.DataFrame(results)
    df['scraped_at'] = datetime.now().isoformat()

    # Gültigkeit zu jedem Produkt hinzufügen
    if validity_info:
        df['gueltig_von'] = validity_info.get('gueltig_von', '')
        df['gueltig_bis'] = validity_info.get('gueltig_bis', '')
        df['gueltigkeitstext'] = validity_info.get('text', '')
    else:
        df['gueltig_von'] = ''
        df['gueltig_bis'] = ''
        df['gueltigkeitstext'] = ''

    conn = sqlite3.connect(DB_PATH)
    df.to_sql('angebote', conn, if_exists='append', index=False)
    conn.close()

    header = not os.path.exists(CSV_PATH)
    df.to_csv(CSV_PATH, mode='a', header=header, index=False)
    print(f"  DB + CSV aktualisiert (+{len(df)})")

# === HAUPTPROZESS ===
def process_page(page_num, validity_info=None):
    url = f"https://penny-publish.blaetterkatalog.de/frontend/mvc/api/catalogs/1178651/v1/normal/bk_{page_num}.jpg"
    path = f"bk_{page_num}.jpg"

    print(f"\n=== Seite {page_num} ===")
    download_image(url, path)

    products = get_products_perplexity(path)
    print(f"  Perplexity: {len(products)} Produkte erkannt")

    if products:
        for p in products[:3]:
            desc = p.get('bild_beschreibung', '')
            desc_preview = desc[:150] + "..." if len(desc) > 150 else desc
            print(f"    → {p['name']} | {p['preis']}")
            if desc:
                print(f"      🖼️ {desc_preview}")
                print(f"      📏 Länge: {len(desc)} Zeichen")

    save_results(products, validity_info)

# === GÜLTIGKEIT EXTRAHIEREN ===
def extract_validity():
    """Extrahiert Prospekt-Gültigkeit aus den ersten Seiten"""
    pages_to_check = [1, 18, 2, 3]

    for page_num in pages_to_check:
        image_path = f"bk_{page_num}.jpg"
        if not os.path.exists(image_path):
            continue

        try:
            pil_image = Image.open(image_path).convert("RGB")
            w, h = pil_image.size
            buffer = io.BytesIO()
            pil_image.save(buffer, format='JPEG', quality=95)
            b64 = base64.b64encode(buffer.getvalue()).decode()

            prompt = f"""
Analysiere diese PENNY-Prospekt-Seite ({w}x{h} Pixel).

Finde die Gültigkeitsinformationen des Prospekts (meist oben auf der Seite):
- "Gültig von ... bis ..."
- "Angebote gültig vom ... - ..."

Gib NUR ein JSON zurück:
{{"gueltig_von": "DD.MM.YYYY", "gueltig_bis": "DD.MM.YYYY", "text": "vollständiger Text"}}

Falls keine Gültigkeit gefunden: {{"gueltig_von": "", "gueltig_bis": "", "text": ""}}
WICHTIG: Kein Code-Block, kein Markdown → NUR reines JSON
"""

            payload = {
                "model": MODEL,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]}],
                "max_tokens": 300,
                "temperature": 0.0
            }

            print(f"\n=== Prüfe Seite {page_num} für Gültigkeit ===")
            r = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json=payload,
                timeout=60
            )
            r.raise_for_status()
            raw = r.json()['choices'][0]['message']['content']

            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = raw[start:end]
                data = json.loads(json_str)

                if data.get('text') and data['text'].strip():
                    # In DB speichern
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS prospekt_info (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            gueltig_von TEXT,
                            gueltig_bis TEXT,
                            gueltigkeitstext TEXT,
                            extracted_at TEXT
                        )
                    ''')
                    cursor.execute('DELETE FROM prospekt_info')
                    cursor.execute('''
                        INSERT INTO prospekt_info (gueltig_von, gueltig_bis, gueltigkeitstext, extracted_at)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        data.get('gueltig_von', ''),
                        data.get('gueltig_bis', ''),
                        data.get('text', ''),
                        datetime.now().isoformat()
                    ))
                    conn.commit()
                    conn.close()
                    print(f"  ✓ Gültigkeit gefunden und gespeichert: {data.get('text', '')}")
                    return data
        except Exception as e:
            print(f"  Fehler bei Seite {page_num}: {e}")
            continue

    print("  ⚠ Keine Gültigkeitsinformationen gefunden")
    return None

# === START ===
if __name__ == "__main__":
    # Datenbank migrieren (Spalten hinzufügen falls nötig)
    print("\n" + "="*60)
    print("Datenbank-Check & Migration")
    print("="*60)
    migrate_database()

    print("\n" + "="*60)
    print("SCHRITT 1: Erste Seiten laden für Gültigkeitsextraktion")
    print("="*60)

    # Erst die ersten paar Seiten herunterladen (ohne zu scannen)
    for page in [1, 18, 2, 3]:
        url = f"https://penny-publish.blaetterkatalog.de/frontend/mvc/api/catalogs/1178651/v1/normal/bk_{page}.jpg"
        path = f"bk_{page}.jpg"
        try:
            download_image(url, path)
        except Exception as e:
            print(f"  Fehler beim Laden von Seite {page}: {e}")

    print("\n" + "="*60)
    print("SCHRITT 2: Gültigkeit extrahieren")
    print("="*60)

    # Gültigkeit extrahieren
    validity_info = extract_validity()

    if validity_info:
        print("\n" + "="*60)
        print(f"✓ GÜLTIGKEIT GEFUNDEN:")
        print(f"  Von: {validity_info.get('gueltig_von', 'N/A')}")
        print(f"  Bis: {validity_info.get('gueltig_bis', 'N/A')}")
        print(f"  Text: {validity_info.get('text', 'N/A')}")
        print("="*60 + "\n")
    else:
        print("\n⚠ Keine Gültigkeit gefunden - fahre ohne fort\n")

    print("="*60)
    print("SCHRITT 3: Alle Seiten scannen")
    print("="*60)

    # Alle Seiten scannen mit Gültigkeit
    for page in range(1, 41):
        try:
            process_page(page, validity_info)
        except Exception as e:
            print(f"  ABBRUCH Seite {page}: {e}")

    print("\n" + "="*60)
    print("✓ SCAN ABGESCHLOSSEN")
    if validity_info:
        print(f"✓ Gültigkeit: {validity_info.get('text', 'N/A')}")
    print("="*60)
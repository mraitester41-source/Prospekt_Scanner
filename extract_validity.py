# extract_validity.py
# Separate Funktion zum Extrahieren der Prospekt-Gültigkeit

import requests
from PIL import Image
import json
import base64
import sqlite3
import io
import os
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

def extract_validity_from_page(image_path):
    """Extrahiert Gültigkeitsdaten aus einer Prospekt-Seite"""
    pil_image = Image.open(image_path).convert("RGB")
    w, h = pil_image.size
    buffer = io.BytesIO()
    pil_image.save(buffer, format='JPEG', quality=95)
    b64 = base64.b64encode(buffer.getvalue()).decode()

    prompt = f"""
Analysiere diese PENNY-Prospekt-Seite ({w}x{h} Pixel).

Finde die Gültigkeitsinformationen des Prospekts. Diese stehen meist oben auf der Seite und sehen z.B. so aus:
- "Gültig von 17.11. bis 23.11.2024"
- "Angebote gültig vom 17.11. - 23.11."
- oder ähnlich

Gib NUR ein JSON zurück mit:
- gueltig_von: Startdatum (z.B. "17.11.2024")
- gueltig_bis: Enddatum (z.B. "23.11.2024")
- text: Vollständiger Text (z.B. "Gültig von 17.11. bis 23.11.2024")

Falls keine Gültigkeitsinformation gefunden wird, gib leere Strings zurück.

WICHTIG: Kein Code-Block, kein Markdown → NUR reines JSON
Format: {{"gueltig_von": "...", "gueltig_bis": "...", "text": "..."}}
"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}],
        "max_tokens": 500,
        "temperature": 0.0
    }

    try:
        print(f"  Analysiere {image_path} für Gültigkeit...")
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
            timeout=60
        )
        r.raise_for_status()
        raw = r.json()['choices'][0]['message']['content']

        # JSON extrahieren
        start = raw.find('{')
        end = raw.rfind('}') + 1
        if start == -1 or end == 0:
            return None

        json_str = raw[start:end]
        data = json.loads(json_str)

        # Prüfe, ob wirklich Daten gefunden wurden
        if data.get('text') and data['text'].strip():
            return data
        return None

    except Exception as e:
        print(f"  Fehler bei Gültigkeitsextraktion: {e}")
        return None

def save_validity_to_db(validity_data):
    """Speichert Gültigkeitsdaten in der Datenbank"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Tabelle erstellen falls nicht vorhanden
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prospekt_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gueltig_von TEXT,
            gueltig_bis TEXT,
            gueltigkeitstext TEXT,
            extracted_at TEXT
        )
    ''')

    # Alte Einträge löschen (wir wollen nur die aktuelle Gültigkeit)
    cursor.execute('DELETE FROM prospekt_info')

    # Neue Gültigkeit einfügen
    cursor.execute('''
        INSERT INTO prospekt_info (gueltig_von, gueltig_bis, gueltigkeitstext, extracted_at)
        VALUES (?, ?, ?, ?)
    ''', (
        validity_data.get('gueltig_von', ''),
        validity_data.get('gueltig_bis', ''),
        validity_data.get('text', ''),
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()
    print(f"  ✓ Gültigkeit gespeichert: {validity_data.get('text', '')}")

def extract_validity():
    """Hauptfunktion: Sucht in mehreren Seiten nach Gültigkeit"""
    # Versuche erst Seite 1, dann 18, dann andere
    pages_to_check = [1, 18, 2, 3, 4]

    for page_num in pages_to_check:
        image_path = f"bk_{page_num}.jpg"
        if not os.path.exists(image_path):
            print(f"  Seite {page_num} nicht gefunden, überspringe...")
            continue

        validity = extract_validity_from_page(image_path)
        if validity:
            print(f"  ✓ Gültigkeit gefunden auf Seite {page_num}!")
            save_validity_to_db(validity)
            return validity

    print("  ⚠ Keine Gültigkeitsinformationen gefunden")
    return None

if __name__ == "__main__":
    print("=== PENNY PROSPEKT GÜLTIGKEIT EXTRAHIEREN ===")
    result = extract_validity()
    if result:
        print(f"\nErgebnis:")
        print(f"  Von: {result['gueltig_von']}")
        print(f"  Bis: {result['gueltig_bis']}")
        print(f"  Text: {result['text']}")

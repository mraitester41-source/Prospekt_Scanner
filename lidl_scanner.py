#!/usr/bin/env python3
"""
LIDL Prospekt Scanner
Scannt LIDL Prospekte mit einer Liste von Bild-URLs
"""

import json
import sys
from pathlib import Path

# Config laden
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print("❌ config.json nicht gefunden!")
    print("Erstelle eine config.json mit deinem Perplexity API Key")
    sys.exit(1)

# Basis-Imports
import requests
import sqlite3
import base64
from datetime import datetime

# Config
API_KEY = config["perplexity_api_key"]
MODEL = config.get("model", "llama-3.1-sonar-large-128k-online")
DB_PATH = config.get("db_path", "penny_perplexity.sqlite")

# LIDL spezifisch
KETTE = "LIDL"
CATALOG_ID = config.get("lidl_catalog_id", datetime.now().strftime("%Y%m%d"))
IMAGE_DIR = Path(f"{KETTE}/{CATALOG_ID}")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# URL-Datei
URL_FILE = config.get("lidl_url_file", "lidl_urls.txt")

print("="*60)
print(f"LIDL PROSPEKT SCANNER")
print("="*60)
print(f"Kette: {KETTE}")
print(f"Katalog ID: {CATALOG_ID}")
print(f"Bildverzeichnis: {IMAGE_DIR}")
print(f"URL-Datei: {URL_FILE}")
print(f"Datenbank: {DB_PATH}")
print("="*60 + "\n")

def download_image(url, path):
    """Lädt ein Bild herunter"""
    if Path(path).exists():
        print(f"  ℹ Überspringe {Path(path).name} (existiert bereits)")
        return

    try:
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()

        with open(path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = Path(path).stat().st_size / 1024 / 1024
        print(f"  ✓ Gespeichert: {Path(path).name} ({size_mb:.2f} MB)")
    except Exception as e:
        print(f"  ✗ Fehler beim Laden: {e}")
        raise

def get_products_perplexity(image_path):
    """Extrahiert Produkte mit Perplexity"""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    prompt = """Du bist ein Experte für Supermarkt-Prospekte. Analysiere dieses LIDL Angebots-Bild.

AUFGABE:
Extrahiere ALLE Produkte mit:
- Name (exakt wie im Prospekt)
- Preis (mit €, z.B. "2.99")
- Grundpreis falls vorhanden (z.B. "1 kg = 4.99")
- APP-Preis falls vorhanden (z.B. "APP 1.99")

REGELN:
- Nur ECHTE Produkte (keine Logos, Texte, Dekoration)
- Grundpreis NUR wenn explizit angegeben
- APP-Preis NUR wenn "APP" oder "mit LIDL Plus" dabei steht

FORMAT (JSON):
{
  "produkte": [
    {"name": "Produktname", "preis": "2.99", "grundpreis": "1 kg = 4.99", "app_preis": ""}
  ]
}

WICHTIG: NUR JSON zurückgeben, keine Erklärungen!"""

    try:
        print(f"  Sende Anfrage an Perplexity...")
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]}],
                "max_tokens": 4000,
                "temperature": 0.0
            },
            timeout=120
        )
        r.raise_for_status()

        raw = r.json()['choices'][0]['message']['content']

        # JSON extrahieren
        start = raw.find('{')
        end = raw.rfind('}') + 1
        if start != -1 and end > start:
            json_str = raw[start:end]
            data = json.loads(json_str)
            products = data.get('produkte', [])
            print(f"  ✓ {len(products)} Produkte erkannt")
            return products
        else:
            print(f"  ✗ Kein JSON in Antwort gefunden")
            return []

    except Exception as e:
        print(f"  ✗ Perplexity Fehler: {e}")
        return []

def save_to_db(page_num, products):
    """Speichert Produkte in Datenbank"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Tabelle erstellen
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS angebote (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            preis TEXT,
            grundpreis TEXT,
            app_preis TEXT,
            seite INTEGER,
            kette TEXT,
            katalog_id TEXT,
            extracted_at TEXT
        )
    ''')

    # Prospekte-Tabelle
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prospekte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kette TEXT NOT NULL,
            katalog_id TEXT NOT NULL,
            gueltig_von TEXT,
            gueltig_bis TEXT,
            created_at TEXT,
            UNIQUE(kette, katalog_id)
        )
    ''')

    # Migration: created_at Spalte hinzufügen falls nicht vorhanden
    try:
        cursor.execute("ALTER TABLE prospekte ADD COLUMN created_at TEXT")
        print("  ℹ Migration: created_at Spalte hinzugefügt")
    except sqlite3.OperationalError:
        # Spalte existiert bereits
        pass

    # Prospekt eintragen (falls noch nicht vorhanden)
    cursor.execute('''
        INSERT OR IGNORE INTO prospekte (kette, katalog_id, created_at)
        VALUES (?, ?, ?)
    ''', (KETTE, CATALOG_ID, datetime.now().isoformat()))

    # Produkte eintragen
    for p in products:
        cursor.execute('''
            INSERT INTO angebote (name, preis, grundpreis, app_preis, seite, kette, katalog_id, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            p.get('name', ''),
            p.get('preis', ''),
            p.get('grundpreis', ''),
            p.get('app_preis', ''),
            page_num,
            KETTE,
            CATALOG_ID,
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()
    print(f"  ✓ {len(products)} Produkte in DB gespeichert")

def main():
    """Hauptfunktion"""

    # URLs laden
    if not Path(URL_FILE).exists():
        print(f"\n❌ URL-Datei '{URL_FILE}' nicht gefunden!")
        print("\nErstelle eine Datei mit einer URL pro Zeile, z.B.:")
        print("  https://imgproxy.leaflets.schwarz/...page-01_...jpg")
        print("  https://imgproxy.leaflets.schwarz/...page-02_...jpg")
        print("\nOder nutze extract_lidl_urls.js im Browser zum Extrahieren.")
        sys.exit(1)

    with open(URL_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    print(f"✓ {len(urls)} URLs geladen\n")

    # Bilder herunterladen und scannen
    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] Seite {i}")
        print(f"URL: {url[:80]}...")

        # Dateiname
        filename = f"page_{i:03d}.jpg"
        filepath = IMAGE_DIR / filename

        # Download
        try:
            download_image(url, filepath)
        except Exception as e:
            print(f"  ⚠️ Überspringe Seite {i}")
            continue

        # Scannen
        products = get_products_perplexity(str(filepath))

        if products:
            save_to_db(i, products)
        else:
            print(f"  ⚠️ Keine Produkte erkannt")

    print(f"\n{'='*60}")
    print("✅ SCAN ABGESCHLOSSEN")
    print(f"{'='*60}")
    print(f"Bilder: {IMAGE_DIR}")
    print(f"Datenbank: {DB_PATH}")
    print(f"\nStarte die Web-App: python app.py")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()

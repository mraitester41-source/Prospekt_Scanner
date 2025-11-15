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
Du bist ein Supermarkt-Experte. Analysiere dieses PENNY-Prospekt ({w}x{h} Pixel).

Finde **ALLE** Produkte – auch kleine, auch oben/unten.
Für jedes Produkt:
- name: voller Name (z. B. "Mühlenhof Frisches Hackfleisch gemischt")
- preis: Aktionspreis (z. B. "5,99 €")
- app_preis: mit App (z. B. "3,49 €" oder leer)
- grundpreis: 1 kg = ... (z. B. "1 kg = 7,99 €" oder leer)
- seite: Seitenzahl aus Dateinamen (z. B. "4")

WICHTIG:
- Ignoriere Werbung, Logos, Überschriften
- Nur echte Produkte mit Preis
- Kein Code-Block, kein Markdown → NUR reines JSON
- Format: {{"products": [{{ "name": "...", "preis": "...", "app_preis": "...", "grundpreis": "...", "seite": "..." }}]}}

Bild: {os.path.basename(image_path)}
"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}],
        "max_tokens": 3000,
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
def save_results(results):
    if not results:
        return
    df = pd.DataFrame(results)
    df['scraped_at'] = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    df.to_sql('angebote', conn, if_exists='append', index=False)
    conn.close()

    header = not os.path.exists(CSV_PATH)
    df.to_csv(CSV_PATH, mode='a', header=header, index=False)
    print(f"  DB + CSV aktualisiert (+{len(df)})")

# === HAUPTPROZESS ===
def process_page(page_num):
    url = f"https://penny-publish.blaetterkatalog.de/frontend/mvc/api/catalogs/1178651/v1/normal/bk_{page_num}.jpg"
    path = f"bk_{page_num}.jpg"
    
    print(f"\n=== Seite {page_num} ===")
    download_image(url, path)
    
    products = get_products_perplexity(path)
    print(f"  Perplexity: {len(products)} Produkte erkannt")

    if products:
        for p in products[:3]:
            print(f"    → {p['name']} | {p['preis']} | {p['app_preis']} | {p['grundpreis']}")
    
    save_results(products)

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
    # Erst die ersten paar Seiten scannen, dann Gültigkeit extrahieren
    for page in range(1, 5):
        try:
            process_page(page)
        except Exception as e:
            print(f"  ABBRUCH Seite {page}: {e}")

    # Gültigkeit extrahieren (nachdem Seite 1 geladen ist)
    extract_validity()

    # Rest der Seiten scannen
    for page in range(5, 41):
        try:
            process_page(page)
        except Exception as e:
            print(f"  ABBRUCH Seite {page}: {e}")
# app.py
# Flask Web-App zur Anzeige von gescannten Prospekt-Seiten und Produkten

from flask import Flask, render_template, jsonify, request, send_file
import sqlite3
import json
import os
from pathlib import Path
import replicate
import requests
from datetime import datetime
import re

app = Flask(__name__)

# Konfiguration laden
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {"db_path": "penny_perplexity.sqlite"}

DB_PATH = config.get("db_path", "penny_perplexity.sqlite")
IMAGES_DIR = Path(".")
GENERATED_IMAGES_DIR = Path("generated_images")
REPLICATE_API_TOKEN = config.get("replicate_api_token", "")

# Erstelle Ordner für generierte Bilder
GENERATED_IMAGES_DIR.mkdir(exist_ok=True)

def get_db_connection():
    """Verbindung zur SQLite-Datenbank herstellen"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def table_exists():
    """Prüft, ob die angebote-Tabelle existiert"""
    if not os.path.exists(DB_PATH):
        return False
    try:
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='angebote'"
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception:
        return False

def parse_grundpreis(grundpreis_str):
    """
    Extrahiert Zahl und Einheit aus Grundpreis-String
    z.B. "2,99 €/kg" -> (2.99, "kg")
         "1.49 € / 100g" -> (1.49, "100g")
    """
    if not grundpreis_str or grundpreis_str.strip() == '':
        return None, None

    # Entferne € und Whitespace
    cleaned = grundpreis_str.replace('€', '').replace(' ', '')

    # Suche nach Zahl (mit Komma oder Punkt) und Einheit
    match = re.match(r'([0-9]+[,.]?[0-9]*)/(.+)', cleaned)
    if match:
        zahl_str = match.group(1).replace(',', '.')
        einheit = match.group(2).strip().lower()
        try:
            zahl = float(zahl_str)
            return zahl, einheit
        except ValueError:
            return None, None

    return None, None

def get_available_pages():
    """Liste aller vorhandenen Prospekt-Seiten"""
    image_files = list(IMAGES_DIR.glob("bk_*.jpg"))
    pages = []
    for img in image_files:
        page_num = img.stem.split('_')[1]
        pages.append({
            'number': page_num,
            'filename': img.name,
            'path': str(img)
        })
    # Sortiere nach numerischer Seitenzahl statt String
    pages.sort(key=lambda x: int(x['number']))
    return pages

@app.route('/')
def index():
    """Hauptseite: Übersicht aller Seiten"""
    pages = get_available_pages()
    validity = None

    # Prüfe, ob Datenbank existiert
    if not table_exists():
        stats = {
            'total_products': 0,
            'total_pages': len(pages)
        }
        for page in pages:
            page['product_count'] = 0
        return render_template('index.html', pages=pages, stats=stats, validity=validity, no_database=True)

    # Anzahl Produkte pro Seite aus DB
    try:
        conn = get_db_connection()

        # Gültigkeit laden
        try:
            cursor = conn.execute("SELECT * FROM prospekt_info ORDER BY id DESC LIMIT 1")
            validity_row = cursor.fetchone()
            if validity_row:
                validity = {
                    'von': validity_row['gueltig_von'],
                    'bis': validity_row['gueltig_bis'],
                    'text': validity_row['gueltigkeitstext']
                }
        except Exception:
            validity = None

        for page in pages:
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM angebote WHERE seite = ?",
                (page['number'],)
            )
            result = cursor.fetchone()
            page['product_count'] = result['count'] if result else 0

        # Gesamtstatistiken
        total_products = conn.execute("SELECT COUNT(*) as count FROM angebote").fetchone()
        total_pages = len(pages)
        conn.close()

        stats = {
            'total_products': total_products['count'] if total_products else 0,
            'total_pages': total_pages
        }
    except Exception as e:
        print(f"Datenbankfehler: {e}")
        stats = {
            'total_products': 0,
            'total_pages': len(pages)
        }
        for page in pages:
            page['product_count'] = 0

    return render_template('index.html', pages=pages, stats=stats, validity=validity)

@app.route('/page/<page_num>')
def page_detail(page_num):
    """Detailansicht einer einzelnen Seite"""
    # Bild-Info
    image_file = f"bk_{page_num}.jpg"
    image_path = IMAGES_DIR / image_file

    if not image_path.exists():
        return "Seite nicht gefunden", 404

    # Produkte aus Datenbank
    products = []
    if table_exists():
        try:
            conn = get_db_connection()
            cursor = conn.execute(
                "SELECT rowid, * FROM angebote WHERE seite = ? ORDER BY rowid",
                (page_num,)
            )
            products = [dict(row) for row in cursor.fetchall()]

            if products:
                # Alle generierten Bilder für diese Seite auf einmal laden
                product_ids = [p['rowid'] for p in products]
                placeholders = ','.join('?' * len(product_ids))

                images_by_product = {}
                try:
                    img_cursor = conn.execute(
                        f"SELECT product_id, filename, created_at FROM generated_images WHERE product_id IN ({placeholders}) ORDER BY created_at DESC",
                        product_ids
                    )
                    for img in img_cursor.fetchall():
                        pid = img['product_id']
                        if pid not in images_by_product:
                            images_by_product[pid] = []
                        images_by_product[pid].append(dict(img))
                except:
                    pass

                # Alle Kategorien für diese Seite auf einmal laden
                categories_by_product = {}
                try:
                    cat_cursor = conn.execute(f"""
                        SELECT pc.product_id, c.name, c.level
                        FROM categories c
                        JOIN product_categories pc ON c.id = pc.category_id
                        WHERE pc.product_id IN ({placeholders})
                        ORDER BY c.level
                    """, product_ids)
                    for cat in cat_cursor.fetchall():
                        pid = cat['product_id']
                        if pid not in categories_by_product:
                            categories_by_product[pid] = []
                        categories_by_product[pid].append({'name': cat['name'], 'level': cat['level']})
                except:
                    pass

                # Bilder und Kategorien zu Produkten hinzufügen
                for product in products:
                    product['generated_images'] = images_by_product.get(product['rowid'], [])
                    product['categories'] = categories_by_product.get(product['rowid'], [])

            conn.close()
        except Exception as e:
            print(f"Datenbankfehler: {e}")
            products = []

    return render_template('page_detail.html',
                          page_num=page_num,
                          image_file=image_file,
                          products=products)

@app.route('/search')
def search():
    """Produktsuche"""
    query = request.args.get('q', '').strip()

    if not query:
        return render_template('search.html', products=[], query='')

    products = []
    if table_exists():
        try:
            conn = get_db_connection()
            cursor = conn.execute(
                "SELECT rowid, * FROM angebote WHERE name LIKE ? ORDER BY seite, rowid",
                (f'%{query}%',)
            )
            products = [dict(row) for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            print(f"Datenbankfehler: {e}")
            products = []

    return render_template('search.html', products=products, query=query)

@app.route('/api/stats')
def api_stats():
    """API-Endpunkt für Statistiken"""
    if not table_exists():
        return jsonify({
            'total_products': 0,
            'with_app_price': 0,
            'per_page': []
        })

    try:
        conn = get_db_connection()

        # Gesamtzahl Produkte
        total = conn.execute("SELECT COUNT(*) as count FROM angebote").fetchone()

        # Produkte mit App-Preis
        app_price = conn.execute(
            "SELECT COUNT(*) as count FROM angebote WHERE app_preis != '' AND app_preis IS NOT NULL"
        ).fetchone()

        # Produkte pro Seite
        per_page = conn.execute(
            "SELECT seite, COUNT(*) as count FROM angebote GROUP BY seite ORDER BY seite"
        ).fetchall()

        conn.close()

        return jsonify({
            'total_products': total['count'],
            'with_app_price': app_price['count'],
            'per_page': [{'page': row['seite'], 'count': row['count']} for row in per_page]
        })
    except Exception as e:
        print(f"Datenbankfehler: {e}")
        return jsonify({
            'total_products': 0,
            'with_app_price': 0,
            'per_page': []
        })

@app.route('/images/<filename>')
def serve_image(filename):
    """Bilder bereitstellen"""
    image_path = IMAGES_DIR / filename
    if image_path.exists():
        return send_file(image_path, mimetype='image/jpeg')
    return "Bild nicht gefunden", 404

@app.route('/generated/<filename>')
def serve_generated_image(filename):
    """Generierte Bilder bereitstellen"""
    image_path = GENERATED_IMAGES_DIR / filename
    if image_path.exists():
        return send_file(image_path, mimetype='image/png')
    return "Generiertes Bild nicht gefunden", 404

@app.route('/api/generate-image/<int:product_id>', methods=['POST'])
def generate_image(product_id):
    """Generiert ein Produktbild mit Replicate/Stable Diffusion"""
    if not REPLICATE_API_TOKEN:
        return jsonify({'error': 'Replicate API Token nicht konfiguriert'}), 400

    try:
        # Produkt aus Datenbank laden
        conn = get_db_connection()
        cursor = conn.execute("SELECT * FROM angebote WHERE rowid = ?", (product_id,))
        product = cursor.fetchone()
        conn.close()

        if not product:
            return jsonify({'error': 'Produkt nicht gefunden'}), 404

        description = product['bild_beschreibung']
        if not description:
            return jsonify({'error': 'Keine Bildbeschreibung vorhanden'}), 400

        # Prompt für Google Imagen 4 optimieren (für fotorealistische Produktbilder)
        prompt = f"Professional product photography: {description}. High quality studio lighting, commercial photography, sharp focus, photorealistic, detailed textures."

        # Bild mit Google Imagen 4 generieren
        os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN
        output = replicate.run(
            "google/imagen-4",
            input={
                "prompt": prompt,
                "aspect_ratio": "1:1",
                "output_format": "png",
                "safety_filter_level": "block_only_high"
            }
        )

        # Bild herunterladen und speichern (Imagen 4 gibt direkt eine URL zurück)
        image_url = str(output) if hasattr(output, '__str__') else output
        response = requests.get(image_url)
        response.raise_for_status()

        # Dateiname generieren
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"product_{product_id}_{timestamp}.png"
        filepath = GENERATED_IMAGES_DIR / filename

        # Bild speichern
        with open(filepath, 'wb') as f:
            f.write(response.content)

        # In Datenbank vermerken
        conn = get_db_connection()
        cursor = conn.cursor()

        # Tabelle für generierte Bilder erstellen falls nicht vorhanden
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS generated_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                filename TEXT,
                prompt TEXT,
                created_at TEXT,
                FOREIGN KEY (product_id) REFERENCES angebote(rowid)
            )
        ''')

        cursor.execute('''
            INSERT INTO generated_images (product_id, filename, prompt, created_at)
            VALUES (?, ?, ?, ?)
        ''', (product_id, filename, prompt, datetime.now().isoformat()))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'filename': filename,
            'url': f'/generated/{filename}'
        })

    except Exception as e:
        print(f"Fehler bei Bildgenerierung: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/product/<int:product_id>/generated-images')
def get_generated_images(product_id):
    """Ruft alle generierten Bilder für ein Produkt ab"""
    try:
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT * FROM generated_images WHERE product_id = ? ORDER BY created_at DESC",
            (product_id,)
        )
        images = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({'images': images})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/product/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Löscht ein einzelnes Produkt"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Produkt löschen
        cursor.execute("DELETE FROM angebote WHERE rowid = ?", (product_id,))

        # Generierte Bilder für dieses Produkt löschen (falls Tabelle existiert)
        try:
            cursor.execute("SELECT filename FROM generated_images WHERE product_id = ?", (product_id,))
            images = cursor.fetchall()

            for img in images:
                img_path = GENERATED_IMAGES_DIR / img['filename']
                if img_path.exists():
                    img_path.unlink()

            cursor.execute("DELETE FROM generated_images WHERE product_id = ?", (product_id,))
        except sqlite3.OperationalError:
            # Tabelle existiert noch nicht bei älteren Produkten
            pass

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Produkt gelöscht'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset-all', methods=['POST'])
def reset_all():
    """Löscht ALLE Daten (Datenbank + Bilder)"""
    try:
        import shutil

        conn = get_db_connection()
        cursor = conn.cursor()

        # Alle Tabellen leeren
        cursor.execute("DELETE FROM angebote")

        try:
            cursor.execute("DELETE FROM generated_images")
        except:
            pass  # Tabelle existiert ggf. noch nicht

        try:
            cursor.execute("DELETE FROM prospekt_info")
        except:
            pass  # Tabelle existiert ggf. noch nicht

        conn.commit()
        conn.close()

        # Generierte Bilder löschen
        if GENERATED_IMAGES_DIR.exists():
            for file in GENERATED_IMAGES_DIR.glob('*'):
                if file.is_file():
                    file.unlink()

        # Optional: Prospekt-Bilder löschen
        for file in IMAGES_DIR.glob('bk_*.jpg'):
            file.unlink()

        return jsonify({'success': True, 'message': 'Alle Daten wurden gelöscht'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/categorize-page/<int:page_num>', methods=['POST'])
def categorize_page(page_num):
    """Kategorisiert alle Produkte einer Seite mit Perplexity"""
    try:
        # Produkte von dieser Seite laden
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT rowid, name, preis, grundpreis FROM angebote WHERE seite = ?",
            (page_num,)
        )
        products = [dict(row) for row in cursor.fetchall()]

        if not products:
            conn.close()
            return jsonify({'error': 'Keine Produkte auf dieser Seite'}), 404

        # Perplexity API Key laden
        perplexity_api_key = config.get("perplexity_api_key", "")
        if not perplexity_api_key:
            conn.close()
            return jsonify({'error': 'Perplexity API Key nicht konfiguriert'}), 400

        # Prompt für Perplexity erstellen
        products_text = "\n".join([
            f"- {p['name']} ({p['preis']}, {p['grundpreis'] or 'kein Grundpreis'})"
            for p in products
        ])

        prompt = f"""Kategorisiere diese PENNY Produkte hierarchisch für einen Preisvergleich.

PRODUKTE:
{products_text}

AUFGABE:
Erstelle eine hierarchische Kategorisierung (max. 3 Ebenen):
- Ebene 1: Hauptkategorie (z.B. "Fleisch", "Milchprodukte", "Obst & Gemüse")
- Ebene 2: Unterkategorie (z.B. "Hähnchen", "Rind", "Schwein")
- Ebene 3: Spezifisch (z.B. "mit Knochen", "ohne Knochen", "Filet")

WICHTIG:
- Kategorien müssen vergleichbar sein (gleiche Einheit: kg, 100g, Stück)
- Nur Kategorien, die für Preisvergleich sinnvoll sind
- Deutsche Namen, präzise und eindeutig

AUSGABEFORMAT (JSON):
{{
  "categories": [
    {{"name": "Fleisch", "parent": null, "level": 1}},
    {{"name": "Hähnchen", "parent": "Fleisch", "level": 2}},
    {{"name": "Hähnchen mit Knochen", "parent": "Hähnchen", "level": 3}}
  ],
  "assignments": [
    {{"product": "Hähnchenschenkel", "categories": ["Fleisch", "Hähnchen", "Hähnchen mit Knochen"]}}
  ]
}}

Gib NUR das JSON zurück, keine Erklärungen."""

        # Perplexity API aufrufen
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {perplexity_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": config.get("model", "llama-3.1-sonar-large-128k-online"),
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 4000,
                "temperature": 0.1
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        # JSON aus Antwort extrahieren
        content = result['choices'][0]['message']['content']

        # Falls Markdown-Code-Block, extrahieren
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()

        categorization = json.loads(content)

        # Kategorien in DB anlegen
        category_ids = {}

        for cat in categorization['categories']:
            cat_name = cat['name']
            parent_name = cat.get('parent')
            level = cat.get('level', 0)

            # Parent-ID ermitteln
            parent_id = category_ids.get(parent_name) if parent_name else None

            # Kategorie anlegen (oder bestehende holen)
            cursor.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
            existing = cursor.fetchone()

            if existing:
                category_ids[cat_name] = existing['id']
            else:
                cursor.execute(
                    "INSERT INTO categories (name, parent_id, level) VALUES (?, ?, ?)",
                    (cat_name, parent_id, level)
                )
                category_ids[cat_name] = cursor.lastrowid

        # Produkte verknüpfen
        assignments_count = 0
        for assignment in categorization.get('assignments', []):
            product_name = assignment['product']
            category_names = assignment['categories']

            # Produkt finden (fuzzy match)
            product_id = None
            for p in products:
                if product_name.lower() in p['name'].lower() or p['name'].lower() in product_name.lower():
                    product_id = p['rowid']
                    break

            if not product_id:
                continue

            # Kategorien verknüpfen
            for cat_name in category_names:
                if cat_name in category_ids:
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO product_categories (product_id, category_id) VALUES (?, ?)",
                            (product_id, category_ids[cat_name])
                        )
                        assignments_count += 1
                    except:
                        pass

        # Grundpreise parsen und aktualisieren
        for p in products:
            if p['grundpreis']:
                zahl, einheit = parse_grundpreis(p['grundpreis'])
                if zahl and einheit:
                    cursor.execute(
                        "UPDATE angebote SET grundpreis_zahl = ?, grundpreis_einheit = ? WHERE rowid = ?",
                        (zahl, einheit, p['rowid'])
                    )

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'categories_created': len(category_ids),
            'assignments': assignments_count,
            'message': f'{len(category_ids)} Kategorien erstellt, {assignments_count} Zuordnungen'
        })

    except Exception as e:
        print(f"Fehler bei Kategorisierung: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("PENNY PROSPEKT SCANNER - WEB INTERFACE")
    print("=" * 60)
    print(f"Datenbank: {DB_PATH}")
    print(f"Bilder-Verzeichnis: {IMAGES_DIR}")
    print("\nÖffne in deinem Browser: http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)

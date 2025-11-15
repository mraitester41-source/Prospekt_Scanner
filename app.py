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
                "SELECT * FROM angebote WHERE seite = ? ORDER BY rowid",
                (page_num,)
            )
            products = [dict(row) for row in cursor.fetchall()]
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
                "SELECT * FROM angebote WHERE name LIKE ? ORDER BY seite, rowid",
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

        # Prompt für Stable Diffusion optimieren
        prompt = f"Professional product photography: {description}. High quality, studio lighting, commercial photography, sharp focus, detailed."

        # Bild mit Replicate generieren (SDXL)
        os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN
        output = replicate.run(
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "num_outputs": 1,
                "guidance_scale": 7.5,
                "num_inference_steps": 50
            }
        )

        # Bild herunterladen und speichern
        image_url = output[0]
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

if __name__ == '__main__':
    print("=" * 60)
    print("PENNY PROSPEKT SCANNER - WEB INTERFACE")
    print("=" * 60)
    print(f"Datenbank: {DB_PATH}")
    print(f"Bilder-Verzeichnis: {IMAGES_DIR}")
    print("\nÖffne in deinem Browser: http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)

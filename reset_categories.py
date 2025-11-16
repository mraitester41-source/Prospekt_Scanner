#!/usr/bin/env python3
"""
Löscht alle Kategorien und Zuordnungen aus der Datenbank.
Beim nächsten Kategorisieren werden neue Kategorien erstellt.
"""

import sqlite3
import json

# Config laden
with open('config.json', 'r') as f:
    config = json.load(f)

DB_PATH = config.get("db_path", "penny_perplexity.sqlite")

print(f"\n{'='*60}")
print(f"KATEGORIEN RESET - Datenbank: {DB_PATH}")
print(f"{'='*60}\n")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Prüfen ob Tabellen existieren
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = [t[0] for t in cursor.fetchall()]

print(f"Vorhandene Tabellen: {', '.join(tables) if tables else 'keine'}\n")

if 'categories' in tables:
    cursor.execute("SELECT COUNT(*) FROM categories")
    cat_count = cursor.fetchone()[0]
    print(f"Kategorien vor Löschung: {cat_count}")

    # Alle Kategorien anzeigen
    cursor.execute("SELECT id, name, parent_id FROM categories ORDER BY id")
    cats = cursor.fetchall()
    for c in cats:
        parent = f" (unter ID {c[2]})" if c[2] else ""
        print(f"  - ID {c[0]}: {c[1]}{parent}")

    print("\nLösche Kategorien...")
    cursor.execute("DROP TABLE IF EXISTS product_categories")
    cursor.execute("DROP TABLE IF EXISTS categories")
    conn.commit()
    print("✓ Kategorien gelöscht")
else:
    print("ℹ Keine Kategorien-Tabelle gefunden (schon leer)")

conn.close()

print(f"\n{'='*60}")
print("FERTIG - Beim nächsten Kategorisieren werden neue Kategorien erstellt")
print(f"{'='*60}\n")

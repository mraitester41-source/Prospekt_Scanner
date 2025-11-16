#!/usr/bin/env python3
"""
Findet verfügbare PENNY Prospekt-Kataloge
"""
import requests
import sys

def check_catalog(catalog_id):
    """Prüft, ob ein Katalog existiert"""
    url = f"https://penny-publish.blaetterkatalog.de/frontend/mvc/api/catalogs/{catalog_id}/v1/normal/bk_1.jpg"
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except:
        return False

def find_catalogs(start_id, end_id):
    """Findet alle verfügbaren Kataloge in einem Bereich"""
    print(f"Suche nach Katalogen zwischen {start_id} und {end_id}...")
    print("=" * 60)

    found_catalogs = []

    for catalog_id in range(start_id, end_id + 1):
        if check_catalog(catalog_id):
            print(f"✓ Katalog {catalog_id} gefunden")
            found_catalogs.append(catalog_id)
        else:
            # Zeige Fortschritt alle 100 IDs
            if catalog_id % 100 == 0:
                print(f"  Suche bei {catalog_id}...", end='\r')

    print("\n" + "=" * 60)
    print(f"\nGefundene Kataloge: {len(found_catalogs)}")
    for cat_id in found_catalogs:
        print(f"  - {cat_id}")

    if found_catalogs:
        print(f"\nNEUESTER Katalog: {max(found_catalogs)}")
        print(f"\nUm diesen Katalog zu verwenden:")
        print(f'  1. Öffne config.json')
        print(f'  2. Setze "catalog_id": {max(found_catalogs)}')
        print(f'  3. Führe penny_perplexity_only.py aus')

    return found_catalogs

if __name__ == "__main__":
    # Standard-Bereich: letzten 1000 IDs
    current = 1178966  # Bekannter neuester Katalog

    if len(sys.argv) == 3:
        start = int(sys.argv[1])
        end = int(sys.argv[2])
    else:
        # Suche im Bereich der letzten bekannten +/- 500
        start = current - 500
        end = current + 500
        print(f"Verwende Standard-Bereich: {start} bis {end}")
        print(f"Hinweis: Rufe mit 'python find_catalogs.py START END' für eigenen Bereich auf\n")

    find_catalogs(start, end)

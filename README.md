# Prospekt_Scanner

Python-Tool zum automatischen Scannen und Extrahieren von Produktdaten aus PENNY-Prospekten mittels Perplexity AI.

## Features

- Automatischer Download von PENNY-Prospekt-Seiten
- KI-gestützte Produkterkennung mit Perplexity API
- Extraktion von: Produktname, Preis, App-Preis, Grundpreis
- Speicherung in SQLite-Datenbank und CSV

## Installation

1. Repository klonen
2. Dependencies installieren:
   ```bash
   pip install -r requirements.txt
   ```

3. Konfigurationsdatei erstellen:
   ```bash
   cp config.json.example config.json
   ```

4. `config.json` mit deinem Perplexity API-Key bearbeiten

## Konfiguration

Erstelle eine `config.json` mit folgenden Parametern:

```json
{
  "perplexity_api_key": "YOUR_API_KEY_HERE",
  "model": "llama-3.1-sonar-huge-128k-online",
  "db_path": "penny_perplexity.sqlite",
  "csv_path": "penny_perplexity.csv"
}
```

## Verwendung

```bash
python penny_perplexity_only.py
```

Das Skript verarbeitet automatisch Seiten 1-40 des aktuellen PENNY-Prospekts.

## Ausgabe

- **SQLite-Datenbank**: `penny_perplexity.sqlite` (Tabelle: `angebote`)
- **CSV-Datei**: `penny_perplexity.csv`

## Abhängigkeiten

- Python 3.8+
- requests
- Pillow
- pandas

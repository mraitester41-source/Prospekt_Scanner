# Prospekt_Scanner

Python-Tool zum automatischen Scannen und Extrahieren von Produktdaten aus PENNY-Prospekten mittels Perplexity AI.

## Features

- Automatischer Download von PENNY-Prospekt-Seiten
- KI-gestützte Produkterkennung mit Perplexity API
- Extraktion von: Produktname, Preis, App-Preis, Grundpreis
- Speicherung in SQLite-Datenbank und CSV
- **Web-Interface** zur Anzeige von Prospekt-Seiten und Produkten

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

### 1. Prospekt scannen

```bash
python penny_perplexity_only.py
```

Das Skript verarbeitet automatisch Seiten 1-40 des aktuellen PENNY-Prospekts.

### 2. Web-Interface starten

Nach dem Scannen kannst du die Ergebnisse im Browser ansehen:

```bash
python app.py
```

Öffne dann im Browser: **http://localhost:5000**

**Features der Web-App:**
- Übersicht aller gescannten Prospekt-Seiten
- Detailansicht mit Bild und allen gefundenen Produkten
- Produktsuche über alle Seiten
- Statistiken (Anzahl Produkte, Seiten)

## Ausgabe

- **SQLite-Datenbank**: `penny_perplexity.sqlite` (Tabelle: `angebote`)
- **CSV-Datei**: `penny_perplexity.csv`
- **Web-Interface**: http://localhost:5000

## Abhängigkeiten

- Python 3.8+
- requests
- Pillow
- pandas
- Flask

## Projektstruktur

```
Prospekt_Scanner/
├── penny_perplexity_only.py  # Scanner-Skript
├── app.py                     # Flask Web-App
├── config.json                # Konfiguration (nicht im Repo)
├── config.json.example        # Konfigurations-Template
├── requirements.txt           # Python-Dependencies
├── templates/                 # HTML-Templates
│   ├── base.html
│   ├── index.html
│   ├── page_detail.html
│   └── search.html
├── static/                    # CSS & Statische Dateien
│   └── style.css
├── bk_*.jpg                   # Heruntergeladene Bilder (nicht im Repo)
├── penny_perplexity.sqlite    # SQLite-Datenbank (nicht im Repo)
└── penny_perplexity.csv       # CSV-Export (nicht im Repo)
```

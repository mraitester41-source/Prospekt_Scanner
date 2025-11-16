# LIDL Prospekt URLs Extrahieren

## Option 1: Browser Developer Tools (EINFACHSTE METHODE)

1. Öffne die LIDL Prospekt-Seite:
   https://www.lidl.de/l/prospekte/aktionsprospekt-17-11-2025-22-11-2025-f76ed7/view/flyer/page/1

2. Drücke **F12** um Developer Tools zu öffnen

3. Gehe zum **Network** Tab

4. Filter setze auf "img" oder "jpg"

5. **Blättere durch ALLE Seiten** im Prospekt
   - Jede Seite die du anschaust wird ein Bild laden
   - Im Network Tab siehst du die imgproxy.leaflets.schwarz URLs

6. Rechtsklick auf eine URL → **Copy → Copy URL**

7. Sammle alle URLs in eine Textdatei: `lidl_urls.txt`

## Option 2: JavaScript Console Script

1. Öffne die LIDL Prospekt-Seite

2. Drücke **F12** und gehe zum **Console** Tab

3. Kopiere und führe dieses Script aus:

```javascript
// URLs sammeln
const urls = [];
const images = document.querySelectorAll('img');

images.forEach(img => {
    if (img.src.includes('leaflets.schwarz') || img.src.includes('imgproxy')) {
        urls.push(img.src);
    }
});

console.log(`Gefunden: ${urls.length} URLs`);
urls.forEach(url => console.log(url));

// Als Datei speichern
const blob = new Blob([urls.join('\n')], { type: 'text/plain' });
const a = document.createElement('a');
a.href = URL.createObjectURL(blob);
a.download = 'lidl_urls.txt';
a.click();
```

## Option 3: Alle Seiten automatisch durchgehen

```javascript
// WICHTIG: Öffne erst die LIDL Prospekt-Seite

(async function() {
    const urls = [];
    const totalPages = 64; // Anpassen an Prospekt

    for (let i = 1; i <= totalPages; i++) {
        console.log(`Lade Seite ${i}...`);

        // URL der Seite
        const pageUrl = `https://www.lidl.de/l/prospekte/aktionsprospekt-17-11-2025-22-11-2025-f76ed7/view/flyer/page/${i}`;

        // Warte kurz
        await new Promise(r => setTimeout(r, 1000));

        // Suche Bild
        const img = document.querySelector('img[src*="leaflets.schwarz"], img[src*="imgproxy"]');
        if (img && img.src) {
            urls.push(img.src);
            console.log(`  ✓ ${img.src.substring(0, 60)}...`);
        }

        // Zur nächsten Seite (falls Navigation-Button existiert)
        const nextBtn = document.querySelector('[data-testid="next"], .next-page, button:contains("Weiter")');
        if (nextBtn) {
            nextBtn.click();
        }
    }

    console.log(`\n✅ ${urls.length} URLs gefunden`);

    // Speichern
    const blob = new Blob([urls.join('\n')], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'lidl_urls.txt';
    a.click();

    console.log("📥 Datei lidl_urls.txt heruntergeladen!");
})();
```

## Option 4: CURL + Reverse Engineering (FORTGESCHRITTEN)

Wenn die Seite eine API hat, können wir sie direkt abfragen.

Prüfe im Network Tab nach Requests an:
- `/api/`
- `/leaflets/`
- JSON responses

Kopiere den Request als cURL und analysiere die Response.

## Nach dem Extrahieren

1. Speichere alle URLs in `lidl_urls.txt` (eine URL pro Zeile)

2. Führe den Scanner aus:
   ```bash
   python lidl_scanner.py
   ```

3. Die Bilder werden nach `LIDL/{katalog_id}/` heruntergeladen

4. Produkte werden in die Datenbank extrahiert

5. Web-App starten: `python app.py`

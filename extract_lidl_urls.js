/**
 * LIDL URL Extraktor - Browser Console Script
 *
 * Anleitung:
 * 1. Gehe auf eine LIDL Prospekt-Seite im Browser
 * 2. Öffne Developer Tools (F12)
 * 3. Gehe zum "Console" Tab
 * 4. Kopiere dieses gesamte Script und führe es aus
 * 5. Es wird eine urls.txt Datei erstellen die du herunterladen kannst
 */

(function() {
    console.log("🔍 LIDL URL Extraktor gestartet...\n");

    // Methode 1: Suche nach img tags mit leaflets.schwarz
    const images = Array.from(document.querySelectorAll('img'))
        .map(img => img.src)
        .filter(src => src.includes('leaflets.schwarz') || src.includes('imgproxy'));

    console.log(`Gefunden (img tags): ${images.length} Bilder`);

    // Methode 2: Suche nach background-images
    const allElements = document.querySelectorAll('*');
    const backgroundImages = Array.from(allElements)
        .map(el => {
            const bg = window.getComputedStyle(el).backgroundImage;
            const match = bg.match(/url\(["']?([^"')]+)["']?\)/);
            return match ? match[1] : null;
        })
        .filter(url => url && (url.includes('leaflets.schwarz') || url.includes('imgproxy')));

    console.log(`Gefunden (backgrounds): ${backgroundImages.length} Bilder`);

    // Methode 3: Durchsuche alle Scripts nach URLs
    const scripts = Array.from(document.querySelectorAll('script'))
        .map(script => script.textContent)
        .join('\n');

    const urlPattern = /https?:\/\/[^\s"']+(?:leaflets\.schwarz|imgproxy)[^\s"']*/g;
    const scriptUrls = [...new Set(scripts.match(urlPattern) || [])];

    console.log(`Gefunden (in scripts): ${scriptUrls.length} URLs`);

    // Alle URLs kombinieren und deduplizieren
    const allUrls = [...new Set([...images, ...backgroundImages, ...scriptUrls])];

    console.log(`\n✓ Gesamt: ${allUrls.length} eindeutige URLs gefunden\n`);

    if (allUrls.length === 0) {
        console.log("❌ Keine URLs gefunden!");
        console.log("Versuche:");
        console.log("1. Durch alle Seiten im Prospekt zu blättern");
        console.log("2. Das Script erneut auszuführen");
        console.log("3. Die Network-Tab zu checken während du durch die Seiten blätterst");
        return;
    }

    // Sortiere URLs nach Seitennummer (falls erkennbar)
    const sortedUrls = allUrls.sort((a, b) => {
        const pageA = a.match(/page-(\d+)/);
        const pageB = b.match(/page-(\d+)/);
        if (pageA && pageB) {
            return parseInt(pageA[1]) - parseInt(pageB[1]);
        }
        return a.localeCompare(b);
    });

    // Zeige erste 5 URLs als Beispiel
    console.log("Beispiel URLs:");
    sortedUrls.slice(0, 5).forEach((url, i) => {
        console.log(`${i+1}. ${url.substring(0, 100)}...`);
    });

    // Erstelle Download-Datei
    const content = sortedUrls.join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'lidl_urls.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    console.log("\n✅ URLs in 'lidl_urls.txt' exportiert!");
    console.log(`📥 Check deinen Downloads-Ordner`);

    // Auch in Zwischenablage kopieren (wenn möglich)
    if (navigator.clipboard) {
        navigator.clipboard.writeText(content).then(() => {
            console.log("📋 URLs auch in Zwischenablage kopiert!");
        }).catch(() => {
            console.log("⚠️ Zwischenablage-Zugriff verweigert (normal in manchen Browsern)");
        });
    }

    return sortedUrls;
})();

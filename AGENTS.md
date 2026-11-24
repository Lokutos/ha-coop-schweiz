# Projekt: ha-coop-schweiz

Home-Assistant-Custom-Integration, die die Einkaufsliste der Coop-App in beide Richtungen mit einer To-do-Liste in Home Assistant abgleicht. Öffentliches Repository `Lokutos/ha-coop-schweiz`, HACS-tauglich (Custom Repository). Massgebend ist dieses Git-Repository.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `custom_components/coop_schweiz/` | Die Integration (nur dieser Ordner wird von HACS installiert) |
| `custom_components/coop_schweiz/api.py`, `util.py`, `const.py` | Client und Helfer ohne Abhängigkeit zu Home Assistant |
| `custom_components/coop_schweiz/frontend/coop-schweiz-card.js` | Dashboard-Karte mit Vorschlägen aus dem Coop-Sortiment; wird von der Integration ausgeliefert und im Frontend automatisch geladen (kein Build, reines JavaScript) |
| `tests/` | `test_api.py`, `test_util.py`: Client und Helfer, ohne Home Assistant und ohne Netz. `test_ha.py`: Einrichtung, Entität, Aktionen und Suche gegen einen HA-Kern; braucht `pytest-homeassistant-custom-component` (sonst übersprungen), lokal nur in WSL lauffähig |
| `docs/protocol.md` | Beschreibung der genutzten Schnittstelle |
| `tools/` | Privat, nicht im Git (`.gitignore`): Analyse-Skripte und `deploy.ps1` zum Einspielen auf die eigene Installation |

## Regeln

- Öffentliches Repository: keine persönlichen Daten (Mailadressen, Namen, Tokens, Benutzer-IDs, Listen-IDs, Artikel echter Listen, lokale Pfade) in Code, Doku, Tests oder Commits.
- Fehlermeldungen, Logs und Diagnosedaten enthalten nie Antwortkörper, Tokens, Benutzer-IDs, Listen-IDs oder Artikelnamen.
- Kein Logo und keine Bildmarke von Coop oder Supercard; das Symbol in `brand/` ist ein eigenes, neutrales.
- Commits mit der GitHub-noreply-Adresse des Kontos.
- Veröffentlichen (Repository anlegen, Push, Release) nur nach ausdrücklicher Freigabe.
- Keine Anfragen an die Coop-, Supercard- oder Firebase-Endpunkte ohne Auftrag; Schreibtests nur mit Testartikeln.
- Version steht in `manifest.json` und `const.py` (`VERSION`), ein Test prüft die Gleichheit; Release-Tag `vX.Y.Z` gleichlautend.
- Ändern sich die Daten im Config-Entry, `VERSION`/`MINOR_VERSION` im Config-Flow erhöhen und `async_migrate_entry` ergänzen.
- Schreibvorgänge an der Liste folgen dem Muster der Coop-App (Felder, Änderungsstempel `activity` je Artikel, `status`); Abweichungen nur mit Beleg aus dem App-Verhalten.
- Die Sortimentssuche nutzt nur die App-Schnittstelle (`/rest/v2/coopathome/…`). Die bot-geschützten Website-Adressen von coop.ch werden nicht benutzt und der Schutz nicht umgangen.
- Beispiele in Tests und Doku verwenden neutrale Artikel, keine Artikel echter Listen.
- Vor jedem Commit: `pytest` grün, einschliesslich `test_ha.py` (nicht übersprungen).

# Coop Schweiz für Home Assistant (inoffiziell)

[English version](README.md)

Gleicht die Einkaufsliste der **Coop-App** («Einkaufszettel», die Liste, die
auch am Passabene-Scanner erscheint) in beide Richtungen mit einer To-do-Liste
in Home Assistant ab.

> **Inoffiziell.** Dieses Projekt ist nicht mit der Coop Genossenschaft
> verbunden und wird von ihr weder unterstützt noch gebilligt. «Coop» und
> «Supercard» sind Marken ihrer Inhaber. Die Integration spricht mit demselben
> Backend wie die Coop-App, über eine nicht öffentliche Schnittstelle. Sie kann
> jederzeit ausfallen. Nutzung auf eigene Gefahr, privat und nur mit dem
> eigenen Konto. Die Bedingungen der Coop-Dienste (Supercard, digitale
> Einkaufsliste, coop.ch; gelesen im November 2026) erwähnen Drittprogramme
> nicht, beschränken die Dienste aber auf die private, nicht kommerzielle
> Nutzung und erlauben Coop, Konten nach eigenem Ermessen auszuschliessen.
> Wünscht Coop eine Anpassung oder
> Entfernung dieses Projekts, genügt ein Issue; dem wird entsprochen.

## Stand

Frühe Version (0.x). Von einer Person mit einem Konto entwickelt und getestet.

## Funktionen

- Pro Coop-Einkaufsliste eine To-do-Liste in Home Assistant.
- Artikel in Home Assistant hinzufügen, abhaken, wieder öffnen, umbenennen
  und löschen (Dashboard, Automationen, Sprachassistent).
- Änderungen aus der Coop-App erscheinen nach höchstens 5 Minuten (Abfrage
  im Intervall).
- Mengen: `2x Milch` legt zweimal «Milch» an; die Liste zeigt `2× Milch`.
- **Artikel aus dem Coop-Sortiment:** Die mitgelieferte Dashboard-Karte
  schlägt beim Tippen Artikel aus dem ganzen Coop-Sortiment vor. So
  hinzugefügte Artikel tragen die Coop-Artikelnummer; die Coop-App und der
  Passabene-Scanner wissen damit genau, welcher Artikel gemeint ist.
- **Keine Dubletten:** Wird ein Name hinzugefügt, der schon bekannt ist (auf
  der Liste, abgehakt oder im Verlauf der App), wird dieser Artikel wieder
  verwendet, statt einen zweiten Freitext-Eintrag anzulegen.

## Voraussetzungen

- Home Assistant 2024.11 oder neuer
- Eine Supercard ID mit mindestens einer Einkaufsliste in der Coop-App
- Ein Computer mit Browser für die einmalige Anmeldung

## Installation

### HACS (benutzerdefiniertes Repository)

1. HACS → Menü → *Benutzerdefinierte Repositories*
2. Repository `https://github.com/Lokutos/ha-coop-schweiz`, Typ *Integration*
3. In HACS «Coop Schweiz» suchen, öffnen und *Herunterladen* wählen, danach Home Assistant neu starten

### Von Hand

Den Ordner `custom_components/coop_schweiz` in den Ordner
`custom_components` der Home-Assistant-Konfiguration kopieren und neu starten.

## Einrichtung

1. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Coop Schweiz*
2. Den Anmeldelink aus dem Dialog **am Computer** öffnen (am Handy übernimmt
   die Coop-App die Anmeldung) und mit der Supercard ID anmelden.
3. Es erscheint eine Fehlerseite. Das ist so vorgesehen. Die **ganze Adresse**
   aus der Adresszeile kopieren (sie enthält `code=`) und **sofort** in den
   Dialog einfügen: Der Code ist nur kurz gültig.
4. Liste wählen.

Für weitere Listen die Integration nochmals hinzufügen.

## Dashboard-Karte

Die Integration liefert ihre Karte selbst mit, es muss nichts separat
installiert werden. Im Dashboard eine Karte *Manuell* hinzufügen:

```yaml
type: custom:coop-schweiz-card
entity: todo.coop_schweiz_einkaufszettel
```

Ab zwei Buchstaben erscheinen Vorschläge aus dem Coop-Sortiment. Einen
Vorschlag wählen fügt diesen Artikel hinzu, Enter übernimmt den Text so,
wie er dasteht. Jeder offene Artikel zeigt seine Menge mit den Knöpfen − und +.
Optionen: `title` (Überschrift) und
`show_completed: false` (Abgehaktes ausblenden). Ist die Karte direkt nach
der Installation unbekannt, die Browserseite einmal neu laden.

## Aktion `coop_schweiz.add_product`

Fügt einen Sortimentsartikel über seine Coop-Artikelnummer hinzu, für
Automationen und Skripte:

```yaml
action: coop_schweiz.add_product
target:
  entity_id: todo.coop_schweiz_einkaufszettel
data:
  code: "6554381"
  quantity: 2
```

## Bekannte Grenzen

- Abfrage alle 5 Minuten, keine Push-Aktualisierung.
- Artikel aus dem Coop-Sortiment lassen sich in Home Assistant nicht
  umbenennen, nur ihre Menge lässt sich ändern.
- Text, der ohne Auswahl eines Vorschlags hinzugefügt wird (z. B. per
  Sprache), wird ein Freitext-Artikel, ausser ein Artikel mit genau diesem
  Namen ist schon bekannt.
- Die Artikelsuche nutzt den Katalog der Coop-App; Vorschläge brauchen eine
  Internetverbindung und werden 10 Minuten zwischengespeichert.
- Ein Artikelname, der selbst mit Zahl und «x» beginnt (z. B. `6 x Eier`),
  wird beim Hinzufügen in Home Assistant als Menge gelesen.
- Die Anmeldeseite ist deutsch. Artikelnamen erscheinen in der Sprache von
  Home Assistant, sofern die Liste sie enthält (Deutsch, Französisch,
  Italienisch, Englisch).
- Wird die Liste in der Coop-App gelöscht: Eintrag entfernen und neu
  einrichten.

## Datenschutz und Sicherheit

- Die Integration spricht nur mit Servern von Coop (`login.supercard.ch`,
  `www.coop.ch`) und mit Google Firebase, wo Coop die Liste speichert. Sonst
  geht nichts irgendwohin. Was du ins Feld der Karte tippst (ab zwei
  Zeichen), geht als Suchbegriff an `www.coop.ch`, ohne dein Konto.
  Artikelbilder in der Karte lädt dein Browser direkt von `www.coop.ch`.
- Home Assistant sieht dein Passwort nie. Die Anmeldung liefert einen
  **Refresh-Token**, der im Konfigurationseintrag liegt. Home Assistant
  speichert diese Einträge **unverschlüsselt** in `.storage`, der Token steckt
  damit auch in deinen Backups. Wer den Token hat, kann gegenüber den
  Coop-Diensten als du auftreten. Backups und den Ordner `.storage` nicht
  weitergeben.
- Zugriff entziehen: Integration entfernen und das Passwort der Supercard ID
  ändern.
- Protokollmeldungen und Diagnosedaten dieser Integration enthalten keine
  Tokens, Benutzer-IDs, Listen-IDs oder Artikelnamen. Protokolle trotzdem
  prüfen, bevor du sie veröffentlichst. **Die Adresse mit `code=` nie
  veröffentlichen.**

## Fehlersuche

| Anzeichen | Vorgehen |
|---|---|
| «Die Anmeldung wurde abgelehnt oder der Code ist abgelaufen» | Link erneut öffnen und die Adresse sofort einfügen. |
| Home Assistant verlangt eine erneute Anmeldung | Der Refresh-Token gilt nicht mehr (z. B. nach einem Passwortwechsel). Dem Dialog folgen. |
| Liste ist «nicht verfügbar» | Die Coop-Server antworten nicht wie erwartet; die Integration versucht es mit wachsenden Pausen erneut (bis 1 Stunde). Siehe Protokoll. |

## Support

Privates Freizeitprojekt ohne Zusage für Support. Fehlermeldungen gern als
GitHub-Issue. Wie die Schnittstelle funktioniert, steht in
[docs/protocol.md](docs/protocol.md) (englisch).

## Lizenz

[MIT](LICENSE). Die Lizenz gilt für den Code dieses Projekts, nicht für die
festen Werte der Coop-App in `const.py`.

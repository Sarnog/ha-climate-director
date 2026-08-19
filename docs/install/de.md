# Climate Director — Installationsanleitung (Deutsch)

[![Kauf mir einen Kaffee auf Ko-fi](https://img.shields.io/badge/Ko--fi-Kauf%20mir%20einen%20Kaffee-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

Diese Anleitung erklärt Schritt für Schritt, wie du Climate Director
installierst und einrichtest. Geh die Schritte einfach von oben nach unten
durch; jeder Schritt baut auf dem vorherigen auf.

## Inhalt

- [Was ist Climate Director](#was-ist-climate-director)
- [Was du brauchst](#was-du-brauchst)
- [Schritt 1 — Installieren](#schritt-1--installieren)
- [Schritt 2 — Die Integration hinzufügen](#schritt-2--die-integration-hinzufügen)
- [Das Hauptmenü](#das-hauptmenü)
- [Schritt 3 — Allgemeine Einstellungen](#schritt-3--allgemeine-einstellungen)
- [Schritt 4 — Zonen](#schritt-4--zonen)
- [Schritt 5 — Quellen](#schritt-5--quellen)
- [Schritt 6 — Klimakreisläufe](#schritt-6--klimakreisläufe)
- [Schritt 7 — Gemeinsame Wärmequellen](#schritt-7--gemeinsame-wärmequellen)
- [Schritt 8 — Exklusive Gruppen](#schritt-8--exklusive-gruppen)
- [Schritt 9 — Ruhefenster](#schritt-9--ruhefenster)
- [Schritt 10 — Bewohner](#schritt-10--bewohner)
- [Schritt 11 — Türen und Fenster](#schritt-11--türen-und-fenster)
- [Schritt 12 — Speichern und schließen](#schritt-12--speichern-und-schließen)
- [Was du in Home Assistant bekommst](#was-du-in-home-assistant-bekommst)
- [Die Schalter und Tasten](#die-schalter-und-tasten)
- [Aktionen](#aktionen)
- [Vorheizen und Vorkühlen](#vorheizen-und-vorkühlen)
- [Selbst das Kommando übernehmen](#selbst-das-kommando-übernehmen)
- [Einen Schattenlauf beurteilen](#einen-schattenlauf-beurteilen)
- [Blueprints und Meldungen](#blueprints-und-meldungen)
- [Probleme lösen](#probleme-lösen)
- [Sprachen](#sprachen)

## Was ist Climate Director

Climate Director ist eine Home-Assistant-Integration, die vorhandene
Klimageräte steuert. Sie besitzt selbst keine Hardware: Sie dirigiert die
`climate`-Entitäten, die du bereits hast — einen Gas-Brennwertkessel, eine
Wärmepumpe, Klimaanlagen. In jedem Moment berechnet sie einen einzigen
stimmigen Endzustand für das ganze Haus und setzt ihn in Service Calls um.

**Der Schattenmodus ist standardmäßig an.** Die Integration berechnet dann
jede Entscheidung und zeigt, was sie getan hätte, steuert aber nichts an. So
kannst du sie wochenlang neben deinen bestehenden Automatisierungen mitlaufen
lassen und erst umsteigen, wenn du ihr vertraust.

Drei Begriffe bilden die Grundlage:

| Begriff | Bedeutung |
|---|---|
| **Zone** | Ein Raum. Beschreibt *was du willst*: Zieltemperatur, wann Heizen oder Kühlen beginnen darf und in welcher Jahreszeit. |
| **Quelle** | Ein Gerät, das eine Zone bedienen kann, mit einer Aufgabe (Heizen, Kühlen oder beides), einer Vorzugsreihenfolge und einem Außentemperaturfenster. |
| **Klimakreislauf** | Ein Außengerät mit den Innengeräten, die daran hängen. Beschreibt *was technisch gleichzeitig geht*. |

Die Faustregel für ein gemeinsames Außengerät: Alle Innengeräte an einem
Kreislauf tragen dieselbe Aufgabe — Heizen, Kühlen, Aus oder nur Lüften. Zwei
Innengeräte an einem Außengerät können also nicht gleichzeitig das eine heizen
und das andere kühlen. Climate Director weiß, welche Geräte zusammengehören,
und löst diesen Konflikt für dich.

## Was du brauchst

| Entität | Erforderlich | Wofür |
|---|---|---|
| Eine `climate.*` pro Zone | **ja** | ohne Gerät gibt es nichts zu steuern |
| Ein Temperatursensor pro Zone | **ja** | ohne Messwert kann die Integration zu kalt nicht von zu warm unterscheiden; eine `climate.*` mit `current_temperature` geht auch |
| `sensor.*` oder `weather.*` Außentemperatur | nein | nur nötig, wenn du Grenzen auf die Außentemperatur setzt — Gas unter 3 °C, Wärmepumpe darüber, zum Beispiel |
| `person.*` oder `device_tracker.*` pro Bewohner | ja, sobald du Bewohner anlegst | sonst kann dieser Bewohner nie zu Hause sein |
| Ein Schlafsensor pro Bewohner | nein | ohne ihn zählt niemand jemals als schlafend |
| `binary_sensor.*` Anwesenheit pro Zone | nur wenn eine Zone auf *den Raum selbst* läuft | dann ist es das einzige Tor der Zone |
| `binary_sensor.*` Tür oder Fenster | nein | setzt die verbundenen Zonen aus, solange es offen ist |
| `calendar.*` | nein | schaltet den Ferienplan von selbst ein; funktioniert nur mit einem Stichwort |
| Eine Jahreszeiten-Entität | nein | nur wenn du die Jahreszeit nicht aus dem Monat ableiten willst |

Helfer musst du dafür nirgends anlegen. Alle Schalter und Regler erstellt die
Integration selbst.

## Schritt 1 — Installieren

**Mindestversion:** Home Assistant **2025.3** oder neuer. Die Integration fügt
ihre Entitäten über eine API hinzu, die es seit 2025.3 gibt.

**Über HACS** (empfohlen):

1. Öffne HACS.
2. Gehe oben rechts auf die drei Punkte und wähle **Benutzerdefinierte
   Repositories**.
3. Füge diese URL mit der Kategorie **Integration** hinzu:

   ```
   https://github.com/Sarnog/ha-climate-director
   ```

4. Suche in HACS nach **Climate Director**, installiere und starte Home
   Assistant neu.

**Manuell:**

1. Lade dieses Repository herunter oder klone es.
2. Kopiere den Ordner `custom_components/climate_director` in den Ordner
   `custom_components` deiner Home-Assistant-Konfiguration.
3. Starte Home Assistant neu.

## Schritt 2 — Die Integration hinzufügen

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**.
2. Suche **Climate Director** und wähle ihn.
3. Gib der Installation einen **Namen**. Dieser Name wird der Titel und steht
   vor dem Namen jeder Entität, die die Integration erstellt.
4. Lass den **Schattenmodus** an. So schaust du erst zu, bevor wirklich etwas
   gesteuert wird.
5. Speichere. Die Installation erscheint auf dem Tab **Integrationen**.

Alles Weitere baust du unter **Konfigurieren** bei dieser Integration auf.

## Das Hauptmenü

Unter **Konfigurieren** findest du das Hauptmenü, in dieser Reihenfolge:

| Menü | Wofür |
|---|---|
| **Allgemeine Einstellungen** | Außentemperatur, Jahreszeit, Tore, Fenster, Kalender, Schattenmodus |
| **Zonen und Quellen** | pro Raum: Temperatur, Ein- und Ausschaltpunkte und die zugehörigen Geräte |
| **Klimakreisläufe** | welche Innengeräte sich ein Außengerät teilen |
| **Gemeinsame Wärmequellen** | ein Kessel oder eine Wärmepumpe, an dem/der mehrere Räume hängen |
| **Exklusive Gruppen** | Geräte, die nie gleichzeitig laufen dürfen |
| **Ruhefenster** | Stunden, in denen der Director von sich aus nichts beginnt |
| **Bewohner** | wer zu Hause ist, wer schläft, und jedermanns Zeitplan |
| **Türen und Fenster** | welche Öffnungen welche Zonen stilllegen |
| **✅ Speichern und schließen** | erst hier wird wirklich alles gespeichert |

Zwei Dinge machen das Menü angenehm:

- Jeder Bildschirm endet mit **Wenn du hier fertig bist**, mit der Wahl *Diese
  Änderungen behalten und zurück* oder *Verwerfen und zurück*.
- Jede Auswahlliste hat eine Zeile **← Zurück zum Hauptmenü**.

Es gibt also keine Sackgasse. Zurückgehen geht immer, auch mit einem halb
ausgefüllten Bildschirm — was du eingetippt hast, geht dann verloren. Und es
wird **nichts** gespeichert, bis du im Hauptmenü **Speichern und schließen**
wählst.

## Schritt 3 — Allgemeine Einstellungen

| Einstellung | Was sie tut |
|---|---|
| **Außentemperatursensor** | speist jede Außengrenze. Ohne Sensor gilt jede gesetzte Grenze als nicht erreicht und die Installation steht still |
| **Heizsystem** | *Zentral* oder *Pro Zone*, siehe unten |
| **Jahreszeitenquelle** | woher die Jahreszeit kommt: der Monat, eine Entität oder fest Sommer/Winter |
| **Jahreszeiten-Entität** | nur nötig, wenn die Quelle auf *Entität* steht; auch die eingebaute `season.*`-Entität ist wählbar |
| **Hemisphäre** | welche Monate als Sommer zählen, wenn die Jahreszeit aus dem Monat kommt: Nord April–September, Süd Oktober–März |
| **Jemand zu Hause muss wach sein** | an = das Haus wartet auf jemanden zu Hause *und* wach; aus = Schlaf zählt nicht |
| **Der Zeitplan eines Bewohners muss offen sein** | an = das Haus wartet auf das erste Zeitfenster; aus = Anwesenheit allein entscheidet |
| **Ferienkalender** | welche Kalender Ferien ankündigen dürfen; mehrere erlaubt |
| **Wort, das Ferien kennzeichnet** | das Stichwort, das ein Ereignis tragen muss; leer = Kalender werden ignoriert |
| **Vorheizen von / bis** | das Fenster, in dem eine Vorheiz-Anfrage zählt; Standard 06:00–23:00 |
| **Vorheizdauer** | die Obergrenze einer einzelnen Anfrage; Standard 120 Minuten |
| **Gastmodus von / bis** | das Fenster, in dem der Gastmodus gilt; beide leer = den ganzen Tag |
| **Zone nach … Minuten als festgefahren melden** | nach wie vielen Minuten Wartezeit eine Zone als festgefahren gilt; 0 schaltet den Sensor aus |
| **Schattenmodus** | an = alles durchrechnen, nichts steuern |

### Heizsystem: zentral oder pro Zone

| Wahl | Was sie bedeutet | So füllst du sie aus |
|---|---|---|
| **Zentral** | Eine Wärmequelle für das ganze Haus. Einschalten für einen Raum wärmt den Rest mit. Denk an ein einziges smartes Thermostat, mit oder ohne Heizkörperregler. | Setze **dasselbe** Thermostat als Quelle unter jede Zone |
| **Pro Zone** | Jeder Teil des Hauses kann seine Wärme separat bekommen, über ein Zonenventil oder eine eigene Wärmequelle. | Gib jeder Zone ihr **eigenes** Ventil oder Gerät als Quelle; gibt es einen gemeinsamen Kessel, trage ihn als gemeinsame Wärmequelle ein |

Smarte Heizkörperregler allein sind keine Zonierung: Das Haus hat dann immer
noch einen Kreislauf und eine Wärmequelle, die für alle gleichzeitig an- oder
ausgeht. Wähle dann **Zentral**. Ein Kessel mit drei Zonenventilen ist
hingegen **Pro Zone**.

Diese Einstellung ändert nichts daran, wer laufen darf. Sie hält fest, was
deine Installation ist, damit die Konfigurationsprüfung warnen kann, wenn dein
Aufbau nicht dazu passt.

## Schritt 4 — Zonen

Eine Zone ist ein Raum. Pro Zone stellst du ein:

| Einstellung | Was sie tut |
|---|---|
| **Name** | das Label, das überall erscheint |
| **Innentemperatursensor** | worauf die Totzone rechnet; eine `climate.*`, die selbst misst, geht auch |
| **Vorrang an einem gemeinsamen Außengerät** | wie stark diese Zone ein gemeinsames Außengerät beansprucht; **niedriger gewinnt**. An einem Kreislauf darf keine Nummer doppelt vorkommen |
| **Was entscheidet, ob diese Zone läuft** | *der Haushalt* (Zeitplan, Schlaf, jemand zu Hause) oder *der Raum selbst* (nur der Anwesenheitssensor) |
| **Anwesenheitssensor + Status + Nachlaufzeit** | wann der Raum als belegt zählt; die Nachlaufzeit fängt flackernde Melder auf |
| **Diese Zone darf heizen** | aus = dieser Raum wird nie geheizt |
| **Zieltemperatur Heizen** | der Sollwert, den das Gerät beim Heizen bekommt — nicht der Startpunkt |
| **Heizen starten bei** | Heizen startet bei dieser Innentemperatur oder darunter |
| **Totzone Heizen** | wie weit über dem Startpunkt das Heizen stoppt |
| **Nur unter dieser Außentemperatur heizen** | darüber bleibt Heizen aus; leer = keine Grenze |
| **Diese Zone darf kühlen** | aus = dieser Raum wird nie gekühlt |
| **Zieltemperatur Kühlen** | der Sollwert, den das Gerät beim Kühlen bekommt |
| **Kühlen starten bei** | Kühlen startet bei dieser Innentemperatur oder darüber |
| **Totzone Kühlen** | wie weit unter dem Startpunkt das Kühlen stoppt |
| **Nur über dieser Außentemperatur kühlen** | darunter bleibt Kühlen aus; leer = keine Grenze |
| **Nur im Sommer kühlen** | koppelt Kühlen an die Jahreszeit aus den allgemeinen Einstellungen |

### So funktioniert die Totzone

Ein- und Ausschalten geschehen bei zwei verschiedenen Temperaturen, damit ein
Gerät nicht auf ein Zehntelgrad flattert:

- Heizen startet bei `innen ≤ Startpunkt` und stoppt bei `innen ≥ Startpunkt + Totzone`;
- Kühlen startet bei `innen ≥ Startpunkt` und stoppt bei `innen ≤ Startpunkt − Totzone`.

Der Startpunkt gilt als erreicht, der Stopppunkt als überschritten. Ein Grad
Totzone ist ein vernünftiger Anfang.

### Was der Bildschirm verweigert

Drei Kombinationen werden beim Speichern abgelehnt, weil sie eine Zone
ergeben, die zwar da ist, aber nie etwas tut:

- eine **Zieltemperatur auf der falschen Seite des Startpunkts** — das Gerät
  bekommt dann eine Temperatur, für die es nichts tun muss;
- **Kühlen, das am oder unter dem Punkt startet, an dem Heizen startet** — dann
  verlangen beide gleichzeitig denselben Raum;
- die Zone auf **den Raum selbst ohne Anwesenheitssensor**, oder eine Zone, die
  **weder heizen noch kühlen darf**.

### Haushalt oder der Raum selbst

- **Der Haushalt** (Standard): Zeitplan, Schlaf und Jemand-zu-Hause zählen.
  Setzt du zusätzlich einen Anwesenheitssensor, gilt der als Extra-Bedingung:
  Der Haushalt muss es erlauben **und** der Raum muss belegt sein.
- **Der Raum selbst**: Zeitplan, Schlaf und Jemand-zu-Hause werden
  übersprungen. Nur der Anwesenheitssensor entscheidet. Das erfordert also
  einen Anwesenheitssensor, sonst kann die Zone nie laufen.

So kann ein Raum nach Zeitplan laufen und ein anderer nach Anwesenheit.

## Schritt 5 — Quellen

Eine Quelle ist ein Gerät, das die Zone bedienen kann. Nachdem du eine Zone
gespeichert hast, wählst du sofort ihre Quellen.

| Einstellung | Was sie tut |
|---|---|
| **Klima-Entität** | das Gerät selbst |
| **Was dieses Gerät kann** | nur heizen, nur kühlen oder beides. Ein Kessel ist *nur heizen* |
| **Dieses Gerät automatisch starten** | aus lässt es in Ruhe, siehe unten |
| **Reihenfolge innerhalb dieser Zone** | welche Quelle bevorzugt wird; **niedriger gewinnt** |
| **Verwenden ab dieser Außentemperatur** | die Untergrenze; gehört zum Fenster |
| **Verwenden bis zu dieser Außentemperatur** | die Obergrenze; gehört nicht zum Fenster |

### Außengrenzen: halboffen

Die Untergrenze gehört zum Fenster, die Obergrenze nicht. Zwei benachbarte
Quellen decken so die ganze Skala ab, ohne Lücke und ohne Überlappung.

Willst du Gas unter 3 °C und die Klimaanlage darüber, setze die Grenze dann
**nicht** auf 3,0:

| Grenze | 2,9 °C | 3,0 °C | 3,1 °C |
|---|---|---|---|
| beide auf `3.0` | Gas | **Klimaanlage** | Klimaanlage |
| beide auf `3.1` | Gas | **Gas** | Klimaanlage |

Setze die Grenze bei **jeder** Quelle gleich und nie unterschiedlich — sonst
entsteht eine Überlappung, in der beide erlaubt sind.

### Ein Gerät, das du selbst einschaltest

Schalte **Dieses Gerät automatisch starten** aus für ein Gerät, das du von Hand
bedienst (zum Beispiel eine Klimaanlage in einem Schlafzimmer ohne
Anwesenheitssensor). Der Director:

- **schaltet es nie ein**, egal wie kalt oder warm dieser Raum wird;
- **lässt es so**, wie du es stellst;
- **schaltet es nur aus**, wenn es eine Aufgabe fährt, die das gemeinsame
  Außengerät nicht zulässt.

## Schritt 6 — Klimakreisläufe

Nur nötig, wenn Innengeräte sich ein Außengerät teilen. Hat jedes Gerät sein
eigenes Außengerät, lass das leer.

| Einstellung | Was sie tut |
|---|---|
| **Name** | ein Label, um Kreisläufe auseinanderzuhalten |
| **Innengeräte** | welche `climate.*`-Entitäten an diesem Außengerät hängen. Nimm auch Geräte auf, die der Director nicht verwaltet: Sie beanspruchen den Kompressor ebenfalls |
| **Kann gleichzeitig heizen und kühlen** | aus für ein gewöhnliches Multi-Split; an für ein Single-Split oder Drei-Leiter-VRF mit Wärmerückgewinnung |
| **Konfliktregel** | wer gewinnt, wenn zwei Räume gegensätzliche Aufgaben wollen |
| **Eine verlierende Zone darf lüften** | an = der Verlierer geht auf `fan_only` statt auf aus |
| **Pause beim Aufgabenwechsel** | wie lange alles aus ist vor dem Umschalten |
| **Mindestlaufzeit vor einem Aufgabenwechsel** | wie lange eine Aufgabe gelaufen sein muss, bevor die andere übernehmen darf |
| **Ruhe, bevor ein Gerät neu starten darf** | verzögert nur Starten, nie Stoppen; Standard 180 Sekunden |
| **Maximale Anzahl gleichzeitig laufender Geräte** | die Kapazitätsgrenze des Außengeräts; leer = keine Grenze |

### Konfliktregeln

| Regel | Verhalten |
|---|---|
| **Priorität** (Standard) | die Zone mit der niedrigsten Prioritätsnummer gewinnt |
| **Wer zuerst kam** | die bereits laufende Aufgabe behält den Kreislauf; eine neue Anfrage wartet |
| **Größte Abweichung** | die größte Abweichung vom Sollwert gewinnt |
| **Jahreszeit** | die Jahreszeit bestimmt die Aufgabe; alles in die andere Richtung tritt ab |

## Schritt 7 — Gemeinsame Wärmequellen

Ein Kessel oder eine Wärmepumpe, an dem/der mehrere Räume über ihre eigenen
Ventile hängen. Lass das leer, wenn das System seinen eigenen Brenner startet,
sobald ein Ventil darum bittet.

| Einstellung | Was sie tut |
|---|---|
| **Name** | ein Label, um Wärmequellen auseinanderzuhalten |
| **Klima-Entität** | der Kessel oder die Wärmepumpe selbst; darf nicht auch Quelle einer Zone sein, sonst bekäme er zwei Befehle |
| **Zonen, die er bedient** | leer = alle Räume |
| **Feste Zieltemperatur** | leer = er folgt dem wärmsten Ziel der fragenden Räume |

Die Wärmequelle läuft, solange ein Raum, den sie bedient, geheizt wird, und
stoppt, sobald keiner mehr übrig ist.

## Schritt 8 — Exklusive Gruppen

Sollen zwei Geräte **nie** gleichzeitig laufen — ein Gaskessel und eine
Wärmepumpe, zum Beispiel? Verlass dich dafür nicht auf die Außengrenzen allein.
Ein zurückgebliebener Wert genügt, um beide gemeinsam anspringen zu lassen.
Setze sie stattdessen in eine exklusive Gruppe: Von den Geräten einer Gruppe
läuft immer nur eines.

Bedenke, was eine Gruppe bedeutet: **ein** Gerät aus der Gruppe zur Zeit. Soll
der Gaskessel keiner Klimaanlage im Weg stehen, während zwei Klimaanlagen am
selben Kreislauf durchaus gemeinsam kühlen dürfen, dann mach eine Gruppe pro
Paar — Gas mit der einen, Gas mit der anderen.

Eine Gruppe bindet auch Geräte, die du selbst einschaltest: Kommt ein anderes
Mitglied der Gruppe an die Reihe, geht das handbediente Gerät aus.

## Schritt 9 — Ruhefenster

Stunden, in denen der Director **von sich aus nichts beginnt**. Wer um elf Uhr
abends heimkommt und gleich ins Bett geht, muss das Haus nicht hochheizen
lassen.

Es ist eine Bremse fürs **Starten**, nicht fürs Weitermachen:

- was bereits läuft, bleibt geregelt;
- schaltest du selbst etwas ein, wird das aufgegriffen;
- was aus ist, bleibt aus, bis das Fenster vorbei ist.

Fenster dürfen über Mitternacht laufen und kennen Wochentage. Ein Haushalt, der
werktags um neun ins Bett geht und am Wochenende um elf, setzt zwei:

| Von | Bis | Tage |
|---|---|---|
| 21:00 | 09:00 | Mo Di Mi Do So |
| 23:00 | 09:00 | Fr Sa |

Setzt du keine Fenster, greift die Bremse nicht.

## Schritt 10 — Bewohner

Lass das leer für ein Gebäude, in dem niemand verfolgt wird; die
Anwesenheitstore werden dann übersprungen, statt alles dauerhaft zu blockieren.

| Einstellung | Was sie tut |
|---|---|
| **Name** | ein Label, um Bewohner auseinanderzuhalten |
| **Anwesenheitssensor** | meist eine `person.*`; sagt, ob dieser Bewohner zu Hause ist |
| **Schlafsensor** | wann dieser Bewohner schläft; leer = Schlaf wird nicht verfolgt |
| **Status, der Schlafen bedeutet** | der Zustand, den der Schlafsensor beim Schlafen meldet |
| **Schlafsensor zählt von / bis** | die Stunden, in denen dieser Sensor etwas bedeutet; beide leer = rund um die Uhr |

### Zeitpläne

Nachdem du einen Bewohner gespeichert hast, legst du seine Zeitpläne an:

| Einstellung | Was sie tut |
|---|---|
| **Dies ist ein Ferienfenster** | gilt nur während des Ferienplans und ersetzt dann die normalen Fenster |
| **Von / Bis** | das Fenster; darf über Mitternacht laufen |
| **Tage** | leer = jeden Tag |

Ein Bewohner ohne Zeitplan nimmt nicht am Zeitplantor teil. Wer an einem Tag
kein Fenster hat, hält das Haus an diesem Tag nicht auf.

### Schlafsensor: kein Sensor, aber eine Taste?

Eine Taste (`button` oder `input_button`) kann nicht sagen, ob du schläfst —
ihr Zustand ist der Zeitpunkt des letzten Drucks. Was funktioniert, ist ein
`input_boolean`, den du mit einer Taste umschaltest: Lege den Schalter an,
wähle ihn als Schlafsensor mit `on` als Schlafzustand und lass eine Taste ihn
umschalten. Wer einen echten Schlafsensor hat (einen Bettsensor, ein kabelloses
Ladegerät), nutzt den: Das ist genauer.

Lässt du den Schlafsensor leer, zählt dieser Bewohner nie als schlafend.

## Schritt 11 — Türen und Fenster

Eine Öffnung, die lange genug offen steht, legt die betroffenen Zonen still.

| Einstellung | Was sie tut |
|---|---|
| **Sensor** | der Tür- oder Fensterkontakt; offen zählt als `on` |
| **Betroffene Zonen** | leer = die ganze Installation |
| **Verzögerung vor dem Stilllegen** | leer oder 0 = sofort beim Öffnen |

## Schritt 12 — Speichern und schließen

Wähle im Hauptmenü **✅ Speichern und schließen**. Erst dann wird die
Installation weggeschrieben.

Ist etwas strukturell falsch — eine Zone ohne brauchbare Quelle, zwei Quellen
auf derselben Entität, ein Außenfenster, das nichts zulässt — bekommst du
zuerst eine Liste, mit der Wahl *Trotzdem speichern* oder *Zurück, um etwas zu
ändern*. Es ist eine **Warnung, keine Weigerung**: Eine Installation darf mit
Absicht ungewöhnlich sein, und nur du weißt, ob das so ist. Dieselbe Liste
steht, solange sie gilt, auch unter **Reparaturen**.

## Was du in Home Assistant bekommst

Ein Gerät pro Installation, darunter:

| Entität | Wofür |
|---|---|
| `sensor.*_last_decision` | wie viele Zonen bedient werden, mit dem vollständigen Plan als Attributen |
| `sensor.*_would_command_<entity>` | der Modus, in den der Director dieses Gerät setzen würde — ein Sensor pro Gerät |
| `sensor.*_mismatch` | wie viele Geräte gerade anders stehen als der Plan will; 0 = Director und Haus sind einig |
| `sensor.*_<zone>_source` | welche Quelle diese Zone bedient, mit dem, was die Zone wollte, bekam und warum |
| `binary_sensor.*_<zone>_blocked` | an, wenn eine Zone weniger bekam als verlangt, mit den geschlossenen Toren als Attributen |
| `binary_sensor.*_<zone>_on_stand_in` | an, wenn eine Zone auf einem Ersatzgerät läuft, weil die erste Wahl unerreichbar ist |
| `binary_sensor.*_stuck` | an, wenn eine Zone zu lange auf demselben Wartegrund sitzt |
| `switch.*_director` | der Hauptschalter; aus = es wird nichts geregelt |
| `switch.*_holiday_schedule` | lässt jeden Tag als Samstag zählen, oder als eigenen Ferienplan |
| `switch.*_guest_mode` | regelt weiter, während die Bewohner weg sind |
| `switch.*_<zone>_override` | übergibt eine Zone vollständig an dich |
| `number.*_<zone>_priority` | der Vorrang dieser Zone; auch aus einer Automatisierung setzbar |
| `number.*_pre_conditioning_duration` | wie lange ein Druck auf eine Vorheiz-Taste dauert |
| `button.*_<zone>_pre_condition` | heizt oder kühlt diese Zone vor |

Außerdem gibt es einen herunterladbaren Diagnose-Export mit der Konfiguration,
dem zuletzt gelesenen Schnappschuss und dem letzten Plan.

## Die Schalter und Tasten

- **Hauptschalter** (`switch.*_director`): aus = der Director tut gar nichts.
- **Gastmodus** (`switch.*_guest_mode`): Jemand Unverfolgtes wohnt da, also
  sagt „Haus leer“ nichts. Schlaf der Anwesenden gilt weiter, und außerhalb des
  Gastfensters übernehmen die normalen Tore.
- **Ferienplan** (`switch.*_holiday_schedule`): Jeder Tag zählt als Samstag
  oder als eigenes Ferienfenster. Schaltet sich auch von selbst ein, sobald ein
  eingerichteter Kalender ein laufendes Ereignis mit dem Stichwort hat. Ohne
  Stichwort werden die Kalender ignoriert.
- **Override** (`switch.*_<zone>_override`): übergibt eine Zone vollständig an
  dich. Der Director sendet dieser Zone nichts mehr — auch kein Aus. Die
  Kreislaufregeln gelten für die anderen Räume weiter. Der Override erlischt
  von selbst, sobald alle Anwesenden ins Bett gehen oder das Haus leer ist.
- **Vorheiz-Taste** (`button.*_<zone>_pre_condition`) und **Dauer**
  (`number.*_pre_conditioning_duration`): siehe unten.

## Aktionen

| Aktion | Wofür |
|---|---|
| `climate_director.evaluate` | sofort neu entscheiden, ohne auf eine Zustandsänderung zu warten |
| `climate_director.precondition` | Vorheizen oder Vorkühlen starten |
| `climate_director.cancel_precondition` | eine laufende Vorheiz-Anfrage abbrechen |

`climate_director.evaluate` ist praktisch beim Einrichten. Im Schattenmodus
führt er weiterhin nichts aus — er rechnet nur neu.

## Vorheizen und Vorkühlen

Die einzige Möglichkeit, ein leeres Haus laufen zu lassen, und mit Absicht die
einzige, die du von Hand einschalten musst.

- **Mit einer Taste**: Jede Zone hat `button.*_<zone>_pre_condition`. Wie lange
  so ein Druck dauert, steht in `number.*_pre_conditioning_duration` (Standard
  60 Minuten, eine Viertelstunde bis zwei Stunden).
- **Mit der Aktion**:

  ```yaml
  action: climate_director.precondition
  data:
    zone_ids: [<zone>]
    minutes: 45
  ```

**Wichtig:** Du sagst nicht, was passieren soll. Die Anfrage öffnet nur die
Tür; danach entscheidet die Integration genau wie sonst — die Totzone prüft,
ob es zu kalt oder zu warm ist, die Jahreszeit und das Außenfenster pro Quelle
wählen das Gerät. Liegt der Raum bereits richtig, bleibt das Gerät aus.

Während einer Vorheiz-Anfrage gelten Hauptschalter, ein Override, die Totzone,
die Jahreszeit, das Außenfenster pro Quelle, Fenster und Türen, der Kreislauf
und die exklusiven Gruppen weiter. Übersprungen werden: *jemand zu Hause*,
*wach*, *Zeitplan*, *Anwesenheit im Raum*, das Außenfenster pro Zone und das
Ruhefenster.

Ein offenes Fenster oder eine offene Tür **verweigert** eine Anfrage. Wer das
Fenster selbst geöffnet hat, darf sagen: trotzdem tun.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 90
  ignore_openings: true
```

Zwei Grenzen, die du nicht vergessen kannst:

- **Sie läuft von selbst ab.** Fragst du länger als das eingestellte Maximum,
  wird deine Anfrage gekürzt. Keine Zeit anzugeben gibt dir das Maximum.
- **Sie gilt nur innerhalb des Fensters** (Standard 06:00–23:00). Außerhalb
  zählt eine Anfrage nicht.

Abbrechen geht mit `climate_director.cancel_precondition`.

## Selbst das Kommando übernehmen

- **Ein Gerät selbst ausschalten** (am Gerät oder auf der Fernbedienung) legt
  diese Zone still. Der Director schaltet es nicht zwei Sekunden später wieder
  ein. Die Zone macht wieder mit, sobald du sie selbst einschaltest, sobald
  alle Anwesenden ins Bett gehen oder sobald der nächste Tag ist.
- **Ein Gerät für ein paar Stunden von Hand einschalten** geht mit einem
  Script daneben, solange du diese Zone für die Dauer mit dem Override an dich
  zurückgibst. Ohne Override rechnet der Director bei der nächsten Auswertung
  seinen eigenen Plan durch und schaltet dein Gerät wieder aus. Ein Gerät mit
  *Dieses Gerät automatisch starten* aus braucht keinen Override.
- **Ein Raum, den du immer selbst bedienst**: Mach trotzdem eine Zone daraus
  (sonst kennt die Integration dieses Gerät nicht), wähle als
  Innentemperatursensor die `climate.*`-Entität des Geräts selbst und schalte
  bei der Quelle *Dieses Gerät automatisch starten* aus.

## Einen Schattenlauf beurteilen

Drei Sensoren machen einen Schattenlauf hinterher beurteilbar:

- **`sensor.*_mismatch`** ist die Kennzahl. Null bedeutet, der Director ist
  einig mit dem, was gerade läuft. Eine kurze Spitze ist normal; ein Wert, der
  stehen bleibt, ist eine echte Meinungsverschiedenheit. Setze diesen Sensor in
  ein Verlaufsdiagramm.
- **`sensor.*_would_command_<entity>`** legst du neben den Verlauf der
  gleichnamigen `climate`-Entität. Zwei Linien, die einander folgen = der
  Director entschied dasselbe wie deine Automatisierungen.
- **`sensor.*_<zone>_source`** und **`binary_sensor.*_<zone>_blocked`** sagen
  danach *warum*: welche Quelle gewählt wurde und welches Tor eine Zone
  zurückhielt.

## Blueprints und Meldungen

Climate Director versendet selbst keine Nachrichten. Wohin eine Meldung geht,
wie sie klingt und ob sie nachts kommen darf, ist von Haushalt zu Haushalt
verschieden. Stattdessen legt die Integration Ereignisse und Melder bereit, an
die du deine eigene Automatisierung hängst. Drei davon solltest du nicht
auslassen:

| Blueprint | Warum du ihn nicht missen kannst | Import-Link |
|---|---|---|
| **Überwachung** | meldet stilles Versagen: eine Zone, die festhängt, oder eine Zone, die auf einem teureren Ersatzgerät läuft | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| **Abgelehntes Vorheizen** | du hast eine Taste gedrückt und nichts passierte; dieser meldet es, mit einer *Trotzdem tun*-Taste | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| **Was entschieden wurde** | das praktischste Werkzeug beim Einrichten und beim Schattenlauf | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

Importieren geht über **Einstellungen → Automatisierungen und Szenen →
Blueprints → Blueprint importieren**, mit dem Link oben.

> **Nur Importieren reicht nicht.** Ein Blueprint ist eine Vorlage; es hört
> erst etwas zu, wenn du eine Automatisierung daraus baust. Tu das sofort nach
> dem Importieren.

Solange niemand auf eine abgelehnte Vorheiz-Anfrage hört, steht dazu ein
Reparaturhinweis in Home Assistant. Der verschwindet von selbst, sobald eine
Automatisierung auf diesem Ereignis steht.

## Probleme lösen

- **`binary_sensor.*_stuck`** geht an, wenn eine Zone zu lange auf demselben
  Wartegrund sitzt (Standard 15 Minuten) oder wenn eine eingerichtete Entität
  nicht lesbar ist — vertippt, gelöscht oder vorübergehend `unavailable`.
  Welche Entitäten es sind, steht im Attribut `unusable_entities`.
- **`binary_sensor.*_<zone>_on_stand_in`** geht an, wenn eine Zone auf einer
  Quelle läuft, die nicht die erste Wahl war, weil die erste Wahl unerreichbar
  ist. Der Raum wird einfach warm — und genau deshalb merkst du ohne Melder
  nichts, bis die Energierechnung kommt.
- **Reparaturhinweise** unter *Reparaturen* zeigen strukturelle Fehler in der
  Konfiguration. Die Zonen, die stimmen, werden derweil normal geregelt; eine
  kaputte Zone legt die Installation nicht still.
- **Die Diagnose** (bei der Integration herunterladbar) enthält die
  Konfiguration, den zuletzt gelesenen Schnappschuss und den letzten Plan. Mit
  diesen dreien ist jede Entscheidung exakt nachvollziehbar.

## Sprachen

Die Erklärung unter jedem Eingabefeld folgt der Sprache deines Home Assistant.
Mitgeliefert: Niederländisch, Englisch, Deutsch, Französisch, Spanisch und
Arabisch.

[![Kauf mir einen Kaffee auf Ko-fi](https://img.shields.io/badge/Ko--fi-Kauf%20mir%20einen%20Kaffee-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

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
| `weather.*` oder `sensor.*` Niederschlag | nein | nur wenn Niederschlag die „Fenster-öffnen“-Grenze aufheben darf |
| `person.*` oder `device_tracker.*` pro Bewohner | ja, sobald du Bewohner anlegst | sonst kann dieser Bewohner nie zu Hause sein |
| Ein Schlafsensor pro Bewohner | nein | ohne ihn zählt niemand jemals als schlafend |
| `binary_sensor.*` Anwesenheit pro Zone | nur wenn eine Zone auf *den Raum selbst* läuft | dann ist es das einzige Tor der Zone |
| `binary_sensor.*`, `cover.*` oder `sensor.*` Tür, Fenster oder Dachfenster | nein | setzt die verbundenen Zonen aus, solange es offen ist |
| `calendar.*` | nein | schaltet den Ferienplan von selbst ein; funktioniert nur mit einem Stichwort |
| Eine Jahreszeiten-Entität | nein | nur wenn du die Jahreszeit nicht aus dem Monat ableiten willst |

Helfer musst du dafür nirgends anlegen. Alle Schalter und Regler erstellt die
Integration selbst.

**Einheit:** Die Integration folgt dem Einheitensystem von Home Assistant. Du
musst nichts umrechnen: Messwerte und Sollwerte erscheinen in der Einheit, die
du in Home Assistant eingestellt hast.

Eine Entität, die ihre eigene Einheit nennt, wird in dieser Einheit gelesen —
ein Sensor über `unit_of_measurement`, eine Wetterquelle über
`temperature_unit`. Genau das brauchst du bei einem Sensor ohne
`device_class: temperature`: den rechnet Home Assistant selbst nicht um.

## Schritt 1 — Installieren

**Mindestversion:** Home Assistant **2025.3** oder neuer. Die Integration fügt
ihre Entitäten über `AddConfigEntryEntitiesCallback` hinzu, und diese API gibt
es seit 2025.3.

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
| **Totband Außentemperatur** | wie viele Grad eine laufende Betriebsart über ihre Außengrenze hinaus weiterlaufen darf, bevor gewechselt wird; standardmäßig 0,5, null schaltet es ab |
| **Heizsystem** | *Zentral* oder *Pro Zone*, siehe unten |
| **Jahreszeitenquelle** | woher die Jahreszeit kommt: der Monat, eine Entität oder fest Sommer/Winter |
| **Jahreszeiten-Entität** | nur nötig, wenn die Quelle auf *Entität* steht; auch die eingebaute `season.*`-Entität ist wählbar |
| **Hemisphäre** | welche Monate als Sommer zählen, wenn die Jahreszeit aus dem Monat kommt: Nord April–September, Süd Oktober–März |
| **Jahreszeitenwahl** | die `select.*`-Entität *Jahreszeit* stellt die Jahreszeit von Hand auf Automatisch, Sommer oder Winter; die Wahl überlebt einen Neustart |
| **Jemand zu Hause muss wach sein** | an = das Haus wartet auf jemanden zu Hause *und* wach; aus = Schlaf zählt nicht |
| **Der Zeitplan eines Bewohners muss offen sein** | an = das Haus wartet auf das erste Zeitfenster; aus = Anwesenheit allein entscheidet |
| **Ferienkalender** | welche Kalender Ferien ankündigen dürfen; mehrere erlaubt |
| **Wort, das Ferien kennzeichnet** | das Stichwort, das ein Ereignis tragen muss; leer = Kalender werden ignoriert |
| **Vorheizdauer** | die Obergrenze einer einzelnen Anfrage; Standard 120 Minuten |
| **Gastmodus von / bis** | das Fenster, in dem der Gastmodus gilt; beide leer = den ganzen Tag |
| **Zone nach … Minuten als festgefahren melden** | nach wie vielen Minuten Wartezeit eine Zone als festgefahren gilt; 0 schaltet den Sensor aus |
| **Niederschlagsquelle** | eine `weather.*`- oder `sensor.*`-Entität, die sagt, ob Niederschlag fällt; leer = die Niederschlagsregel macht nicht mit |
| **Zustände, die als Niederschlag zählen** | welche Zustände dieser Entität Niederschlag bedeuten; standardmäßig Regen, Schnee und Hagel |
| **Wie lange Niederschlag weiter zählt (Minuten)** | Nachlaufzeit nach dem Aufhören des Niederschlags; Standard 15 Minuten |
| **Schattenmodus** | an = alles durchrechnen, nichts steuern |

### Niederschlag setzt die Außengrenze außer Kraft

Die Außengrenze pro Zone ist eine Sparregel mit einer Annahme darunter: Ist es
draußen angenehmer als drinnen, öffnest du besser ein Fenster, als die
Klimaanlage einzuschalten. Fällt Niederschlag, bleibt das Fenster zu, also
passiert nichts, während es drinnen zu warm oder zu kalt bleibt.

Richte deshalb eine **Niederschlagsquelle** ein. Solange sie Niederschlag
meldet, überspringt Climate Director die **Außengrenze pro Zone** — genau wie
eine Vorheiz-Anfrage. Die Totzone, die Jahreszeit und die Außengrenze **pro
Quelle** gelten weiter; die wählen immer noch das Gerät. Die Nachlaufzeit
sorgt dafür, dass ein Fünf-Minuten-Schauer die Regelung nicht ins Schwingen
bringt. Ohne Quelle macht die Niederschlagsregel nicht mit.

Ein Raum ohne Fenster hat nichts davon. Dort schaltest du in der Zone
**Niederschlag hebt die 'Fenster-öffnen'-Regel nicht auf** ein, und die
Außengrenze gilt auch bei Niederschlag weiter.

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
| **Niederschlag hebt die 'Fenster-öffnen'-Regel nicht auf** | an für einen Raum ohne Fenster; dort gilt die Außengrenze auch bei Niederschlag weiter |
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

Vier Dinge werden beim Speichern abgelehnt, weil sie eine Zone ergeben, die
zwar da ist, aber nie etwas tut:

- ein **leerer Name** — der Name legt die interne ID einer neuen Zone fest;
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

Kann eine Aufgabe nur von so einem Gerät erledigt werden, meldet die
Integration das einmal unter *Reparaturen*. Bestätigst du den Hinweis, bleibt
er weg — auch nach einem Neustart. Kommt später eine neue handbediente Aufgabe
in der Zone dazu, folgt ein neuer Hinweis.

## Schritt 6 — Klimakreisläufe

Nur nötig, wenn Innengeräte sich ein Außengerät teilen. Hat jedes Gerät sein
eigenes Außengerät, lass das leer.

| Einstellung | Was sie tut |
|---|---|
| **Name** | ein Label, um Kreisläufe auseinanderzuhalten |
| **Innengeräte** | welche `climate.*`-Entitäten an diesem Außengerät hängen. Nimm auch Geräte auf, die der Director nicht verwaltet: Sie beanspruchen den Kompressor ebenfalls |
| **Kann gleichzeitig heizen und kühlen** | aus für ein gewöhnliches Multi-Split; an für ein Single-Split oder Drei-Leiter-VRF mit Wärmerückgewinnung |
| **Konfliktregel** | wer gewinnt, wenn zwei Räume gegensätzliche Aufgaben wollen |
| **Eine verlierende Zone darf lüften** | an = der Verlierer geht auf `fan_only` statt auf aus, aber nur wenn das Gerät diesen Modus kennt; sonst geht es aus |
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

### Der Vorrang, vom Kreislauf aus

Speicherst du einen Kreislauf, landest du auf **Prioritäten auf diesem
Kreislauf**: die Zonen an diesem Außengerät, in der Reihenfolge, in der sie
derzeit gewinnen, mit ihrer Nummer dahinter. Wähle eine aus, um ihren Vorrang
zu ändern.

Das ist **dasselbe Feld** wie *Vorrang an einem gemeinsamen Außengerät* auf dem
Zonenbildschirm — zwei Wege hinein, eine Einstellung, die beiden können sich
also nie widersprechen. Hier siehst du nur sofort, wer gegen wen steht. Zwei
Zonen auf einem Kreislauf dürfen nicht dieselbe Nummer haben; der Bildschirm
lehnt das ab.

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

Eine Gruppe betrifft das **Gerät**, nicht den Raum. Hängt derselbe Kessel
unter drei Räumen, musst du ihn nur einmal ankreuzen - woher du ihn auch wählst,
er zählt überall. Und zwei Räume, die denselben Kessel anfordern, stehen sich
nicht im Weg: das ist ein Gerät, das läuft.

Eine Gruppe bindet auch Geräte, die du selbst einschaltest: Kommt ein anderes
Mitglied der Gruppe an die Reihe, geht das handbediente Gerät aus. Und
umgekehrt: Läuft so ein Gerät schon, belegt es die Gruppe, und ein anderes
Mitglied wartet.

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

Jedes Fenster hat außerdem ein Häkchen **Dies ist ein Urlaubsfenster**. So ein
Fenster gilt nur bei eingeschaltetem Urlaubsplan und ersetzt dann die
gewöhnlichen; seine Wochentage zählen nicht mit. Setzt du gar keines, zählt ein
Urlaubstag als Samstag.

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
| **Tage des Schlaffensters** | an welchen Tagen dieses Fenster gilt; leer = jeden Tag |
| **Ausschlafen bis** | bis wann der Schlafsensor morgens noch zählt; leer = das Schlaffenster ist die ganze Geschichte |
| **Morgen, an denen du ausschläfst** | die Morgen selbst, nicht die Abende davor; leer = jeden Tag |
| **Auch an Feiertagen ausschlafen** | ein = gilt an jedem Tag, den dein Urlaubskalender markiert |
| **Auf diese schlafende Person warten bis** | bis wann diese Person das Haus im Schlaf aufhält; leer = sie hält niemanden auf |
| **Tage, an denen gewartet wird** | an welchen Tagen diese Uhrzeit gilt; leer = jeden Tag |
| **Auch an Feiertagen auf diese Person warten** | aus = die Tage oben gelten wörtlich; ein = die Uhrzeit gilt an jedem Feiertag |

### Ausschlafen, und warum das nicht einfach ein längeres Schlaffenster ist

Das Schlaffenster erledigt zwei Aufgaben zugleich: Es sagt, wann "Telefon am
Ladegerät" bedeutet, dass jemand im Bett liegt, und schaltet damit abends das
Haus aus, sobald alle Anwesenden zu Bett gegangen sind.

Dehnst du dieses Fenster bis ein Uhr mittags, zählt das Ladegerät auch an einem
gewöhnlichen Mittwoch als Schlaf: Wer um zehn nach Hause kommt oder von zu Hause
arbeitet, bekommt ein kaltes Haus. Kürzt du das Fenster auf das Wochenende, so
schaltet werktags nachts nichts mehr das Haus aus, und es heizt weiter, bis
jemand geht.

Deshalb steht das Ausschlafen für sich. Das Schlaffenster bleibt die Nacht - bei
den meisten etwa 21:00-08:00, jeden Tag. *Ausschlafen bis* dehnt nur den Morgen,
an den Morgen, die du ankreuzt. Achte auf den Unterschied: Ein Schlaffenster
läuft über Mitternacht und hängt daher am Tag seines Beginns, das Ausschlafen
dagegen am Morgen selbst. Ausschlafen am Samstag ist also Samstag.

Mit dem Häkchen **Auch an Feiertagen ausschlafen** gilt es an jedem Tag, den dein
Urlaubskalender markiert. Du trägst *Urlaub* in den Kalender ein, und das
Ausschlafen folgt von selbst.

Ausschlafen und die *späteste Aufstehzeit* leisten Verschiedenes und ergänzen
einander: Das Ausschlafen sagt, wie lange dem Schlafsensor geglaubt wird, die
späteste Zeit, wie lange das Haus auf eine schlafende Person wartet. Schlaft ihr
beide weiter, bleibt das Haus aus, bis die erste Person wirklich aufsteht - die
späteste Zeit tut dann nichts, denn es gibt niemanden, auf den zu warten wäre.

### Nach Hause kommen ist kein Schlafen

Der Schlafsensor kennt das Aufstehen, nicht das Nachhausekommen. Kommst du
herein, während dein Telefon noch am Ladegerät im Auto hängt, ist diese Meldung
älter als deine Ankunft und sagt nichts über jetzt. Die Integration zählt eine
Schlafmeldung deshalb nur, wenn sie nach der Ankunft liegt: Wer hereinkommt, ist
wach, bis er sein Telefon zu Hause wieder auf das Ladegerät legt.

### Auf den letzten Schläfer warten

Ohne Uhrzeit beginnt das Haus, sobald der erste Bewohner auf ist. Mit einer
Uhrzeit wartet das Haus: Ist jemand auf, während diese Person zu Hause noch
schläft, passiert nichts. Nach der eingetragenen Uhrzeit entfällt das Warten,
und das Haus richtet sich nach denen, die auf sind.

Zwei Bewohner, die beide 11:00 für Samstag und Sonntag eintragen, bekommen also:
Einer ist um 10:00 auf und nichts passiert; wacht der andere um 10:30 auf,
beginnt es um 10:30; schläft er weiter, beginnt es um 11:00. Es wirkt in beide
Richtungen - wer von beiden ausschläft, spielt keine Rolle.

Das steht getrennt vom Zeitplan. Ein Zeitplan sagt auch, wann das Haus wieder
*aus* soll; diese Uhrzeit sagt nur, wann man nicht länger auf jemanden warten
muss. Schlafen alle Anwesenden, bleibt das Haus aus - das ist das Schlaftor,
nicht diese Uhrzeit, und das Haus beginnt somit erst, wenn der Erste wirklich
aufsteht.

**Ein Feiertag zählt hier nicht von selbst als Samstag**, anders als bei den
Zeitplänen. Der freie Tag des einen ist der Arbeitstag des anderen: Zählten die
Schulferien als Samstag, hielte der Langschläfer das Haus auf, während der
andere zu Hause arbeitet. Die Tage bedeuten hier also wörtlich, was dort steht.
Wer auch an einem freien Wochentag erwartet werden möchte, setzt das Häkchen
*Auch an Feiertagen auf diese Person warten*; dann gilt die Uhrzeit an jedem
Feiertag, unabhängig vom Wochentag. Ein Feiertag, der auf einen Samstag fällt,
bleibt in jedem Fall ein Samstag.

Achten Sie auf das Schlaffenster: Liegt die Uhrzeit außerhalb, gilt diese Person
ohnehin nicht mehr als schlafend und hält niemanden auf. Lassen Sie das
Schlaffenster also über die Uhrzeit hinaus laufen.

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
| **Sensor** | der Tür-, Fenster- oder Dachfensterkontakt; ein `binary_sensor.*`, `cover.*` oder `sensor.*` |
| **Zustand, der „offen“ bedeutet** | bei einem Fensterkontakt meist `on`, bei einem Dachfenster oder Rollladen `open`; Standard `on` |
| **Betroffene Zonen** | leer = die ganze Installation |
| **Verzögerung vor dem Stilllegen** | leer oder 0 = sofort beim Öffnen |

Wählst du `open` als Offen-Zustand, zählen auch `opening` und `closing` als
offen: Ein Rollladen unterwegs ist nicht zu.

**Ein geteiltes Gerät folgt der Anforderung, nicht der Stille.** Steht derselbe
Kessel als Quelle unter mehreren Zonen, hält er nicht an, sobald eine dieser
Zonen stillgelegt wird: Fordert eine andere Zone in diesem Moment Wärme an,
gewinnt diese Anforderung und der Kessel läuft weiter. Ein geschlossenes System
kann nun einmal nicht den einen Raum heizen und den anderen nicht.

Dafür gibt es auf der Listenansicht der Öffnungen ein zweites Feld:

| Feld | Bedeutung |
| --- | --- |
| **Geräte, die bei jeder Öffnung stillstehen** | leer = alles bleibt pro Zone geregelt |

Was du dort ankreuzt, steht still, sobald irgendeine Öffnung der Anlage offen
steht, wo auch immer und mit ihrer eigenen Verzögerung — während alles Übrige
weiter pro Zone geregelt wird. Genau für den Kessel gedacht: diese Öffnung mit
**allen** Zonen zu verknüpfen legt auch die Klimageräte in jenen Räumen still,
das ganze Jahr über, obwohl die pro Raum gehören. Lässt du es leer, ändert sich
nichts am heutigen Verhalten deiner Anlage.

Der Raum nennt dann `opening_open_elsewhere` als Grund, sodass du siehst, warum
nichts geschieht. Zwei Dinge bleiben wie immer: Eine Zone mit Übersteuerung und
eine handbediente Quelle werden nicht gesteuert, auch von dieser Liste nicht.

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
| `binary_sensor.*_<zone>_blocked` | an, wenn eine Zone weniger bekam als verlangt oder laufen wollte, aber ein Umstand sie zurückhielt; die geschlossenen Tore stehen in den Attributen |
| `binary_sensor.*_<zone>_on_stand_in` | an, wenn eine Zone auf einem Ersatzgerät läuft, weil die erste Wahl unerreichbar ist |
| `binary_sensor.*_stuck` | an, wenn eine Zone zu lange auf demselben Wartegrund sitzt |
| `switch.*_director` | der Hauptschalter; aus = es wird nichts geregelt |
| `switch.*_holiday_schedule` | lässt jeden Tag als Samstag zählen, oder als eigenen Ferienplan |
| `switch.*_guest_mode` | regelt weiter, während die Bewohner weg sind |
| `switch.*_<zone>_override` | übergibt eine Zone vollständig an dich |
| `number.*_<zone>_priority` | der Vorrang dieser Zone; auch aus einer Automatisierung setzbar |
| `number.*_pre_conditioning_duration` | wie lange ein Druck auf eine Vorheiz-Taste dauert |
| `button.*_<zone>_pre_condition` | heizt oder kühlt diese Zone vor |
| `select.*_season` | stellt die Jahreszeit von Hand auf Automatisch, Sommer oder Winter |

Die Namen dieser Entitäten werden übersetzt, und Home Assistant leitet die
Entitäts-ID vom Namen ab. Steht dein Home Assistant in einer anderen Sprache,
heißen sie dort anders; suche dann nach dem Namen, wie er in der Oberfläche
steht.

Außerdem gibt es einen herunterladbaren Diagnose-Export mit der Konfiguration,
dem zuletzt gelesenen Schnappschuss und dem letzten Plan.

## Die Schalter und Tasten

- **Hauptschalter** (`switch.*_director`): aus = der Director tut gar nichts.
  Er lässt alles los und sendet nichts mehr — auch kein Aus. Was in dem Moment
  läuft, läuft also einfach weiter; willst du alles aus, schalte es selbst aus.
- **Gastmodus** (`switch.*_guest_mode`): Jemand Unverfolgtes wohnt da, also
  sagt „Haus leer“ nichts. Schlaf der Anwesenden gilt weiter, und außerhalb des
  Gastfensters übernehmen die normalen Tore.
- **Ferienplan** (`switch.*_holiday_schedule`): Jeder Tag zählt als Samstag
  oder als eigenes Ferienfenster. Schaltet sich auch von selbst ein, sobald ein
  eingerichteter Kalender ein laufendes Ereignis mit dem Stichwort hat. Ohne
  Stichwort werden die Kalender ignoriert.
- **Override** (`switch.*_<zone>_override`): übergibt eine Zone vollständig an
  dich. Der Director sendet dieser Zone nichts mehr — auch kein Aus. Die
  Kreislaufregeln gelten für die anderen Räume weiter. Er bleibt stehen, bis du
  ihn selbst wieder ausschaltest, auch über die Nacht und über ein leeres Haus
  hinweg: Es ist eine Entscheidung, die du zurücknimmst, nicht die von heute
  Abend. Damit lässt sich eine Zone tagelang eigenen Automationen überlassen.
  Ein Gerät, das du am Gerät *selbst* ausschaltest, erlischt sehr wohl zur
  Schlafenszeit oder bei leerem Haus; das steht weiter unten.
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

Eine Grenze, die du nicht vergessen kannst: **sie läuft von selbst ab.** Fragst
du länger als das eingestellte Maximum, wird deine Anfrage gekürzt. Keine Zeit
anzugeben gibt dir das Maximum; null oder weniger wird abgelehnt, denn das ist
keine Anfrage, sondern ein Tippfehler.

Eine Anfrage geht immer vor, zu jeder Stunde des Tages. Nur eine offene Tür
verlangt eine Bestätigung: ohne *Trotzdem tun* weist die Tür die Anfrage ab.

Abbrechen geht mit `climate_director.cancel_precondition`.

## Selbst das Kommando übernehmen

- **Ein Gerät selbst ausschalten** (am Gerät oder auf der Fernbedienung) legt
  diese Zone still. Der Director schaltet es nicht zwei Sekunden später wieder
  ein. Die Zone macht wieder mit, sobald du sie selbst einschaltest, sobald
  jemand in ein leeres Haus zurückkommt, sobald alle Anwesenden ins Bett gehen
  oder sobald der nächste Tag ist (nach Mitternacht).
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
  Wartegrund sitzt (Standard 15 Minuten) — und nur dafür. Eine volle
  Außeneinheit zählt nicht mit: Die wird erst frei, wenn ein anderer Raum
  aufhört zu fragen, und das darf Stunden dauern. Dieser Raum gilt sehr wohl als
  blockiert. Im Attribut `unusable_entities` steht daneben, welche
  eingerichteten Entitäten nicht lesbar sind — vertippt, gelöscht oder
  vorübergehend `unavailable`, und ebenso ein Sensor, der lesbar ist, aber keine
  Zahl liefert (`no number`). Das schaltet den Melder nicht ein; dafür kommt
  nach fünf Minuten ein Reparaturhinweis.
- **`binary_sensor.*_<zone>_on_stand_in`** geht an, wenn eine Zone auf einer
  Quelle läuft, die nicht die erste Wahl war, weil die erste Wahl unerreichbar
  ist. Der Raum wird einfach warm — und genau deshalb merkst du ohne Melder
  nichts, bis die Energierechnung kommt.
- **Reparaturhinweise** unter *Reparaturen* zeigen strukturelle Fehler in der
  Konfiguration. Die Zonen, die stimmen, werden derweil normal geregelt; eine
  kaputte Zone legt die Installation nicht still.
- **Eine Entität, die fünf Minuten lang nicht lesbar ist**, steht ebenfalls
  dort, samt Liste. Das ist kein Fehler in der Konfiguration, sondern in der
  Wirklichkeit: ein Sensor mit leerer Batterie, ein Gerät ohne Netz oder eine
  umbenannte Entität. Die Wartezeit hält ein kurzes Stocken beim Neustart
  heraus. Besonders bei einer unlesbaren Raumtemperatur zählt das, denn dann
  lässt der Director ein laufendes Gerät in Ruhe und dieses Gerät hält seine
  Außeneinheit auf seiner Betriebsart fest.
- **Eine Rolle, die einen Modus verlangt, den das Gerät nicht fahren kann**,
  erscheint dort nach fünf Minuten ebenfalls. Etwa eine Quelle mit der Rolle
  *Heizen und Kühlen* an einem Gerät, das nur `heat` und `off` meldet: Der
  Director überspringt sie fürs Kühlen, und von außen sieht das aus wie ein
  Raum ohne Bedarf. Prüfe die Rolle unter *Konfigurieren* oder die `hvac_modes`
  des Geräts unter *Entwicklerwerkzeuge*.
- **Ein Gerät, das seinen Befehl nicht ausführt**, meldet sich nach etwa zehn
  Minuten. Der Director verlangt die ganze Zeit dasselbe und das Gerät meldet
  weiterhin etwas anderes: Der Aufruf wird angenommen und nichts passiert, oder
  das Gerät stellt sich sofort zurück. Prüfe, ob das Gerät erreichbar ist, ob es
  den Modus annimmt, und ob etwas anderes es zurückstellt — ein
  Thermostatzeitplan oder eine andere Automatisierung. Im Schattenmodus kommt
  diese Meldung nie: Dort wird absichtlich nichts ausgeführt.
- **Ein gespeicherter Zustand, der beiseitegelegt werden musste**, meldet sich
  ebenfalls unter *Reparaturen*. In dieser Datei stehen die laufenden
  Vorheiz-Anfragen und die Geräte, die du von Hand ausgeschaltet hast. Ist sie
  unlesbar, wird sie umbenannt und der Director beginnt mit leerem Zustand:
  diese Anfragen und Abschaltungen sind weg, der Rest deiner Anlage nicht.
  Willst du sie zurück, stelle die Datei aus einem Backup wieder her und lade
  die Integration neu.
- **Die Diagnose** (bei der Integration herunterladbar) enthält die
  Konfiguration, den zuletzt gelesenen Schnappschuss und den letzten Plan. Mit
  diesen dreien ist jede Entscheidung exakt nachvollziehbar.

## Sprachen

Die Erklärung unter jedem Eingabefeld folgt der Sprache deines Home Assistant.
Mitgeliefert: Niederländisch, Englisch, Deutsch, Französisch, Spanisch und
Arabisch.

[![Kauf mir einen Kaffee auf Ko-fi](https://img.shields.io/badge/Ko--fi-Kauf%20mir%20einen%20Kaffee-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

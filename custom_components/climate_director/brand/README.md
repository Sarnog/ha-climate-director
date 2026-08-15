🇳🇱 [Nederlands](#merklogo) | 🇬🇧 [English](#brand-logo)

---

# Merklogo

Sinds **Home Assistant 2026.3** kan een custom integratie zijn eigen merklogo gewoon
meeleveren — een externe pull request naar
[home-assistant/brands](https://github.com/home-assistant/brands) is niet meer nodig. Home
Assistant leest de afbeeldingen automatisch uit deze `brand/`-map binnen de integratie en
geeft die voorrang boven de centrale brands-CDN. Er is geen aanpassing in `manifest.json`
voor nodig.

De bestanden die Home Assistant gebruikt:

- `icon.png` (256×256)
- `icon@2x.png` (512×512)
- `logo.png` (256×256)
- `logo@2x.png` (512×512)

## Het ontwerp

Een cirkel die uit twee helften bestaat. Links een halve sneeuwvlok in wit op ijsblauw,
rechts een halve zon in geel met stralen. Daar iets links van het midden overheen een
thermometer, die van rood onderin naar wit bovenin verloopt.

Drie keuzes zitten er bewust in:

- **De sneeuwvlok staat links, de zon rechts.** De thermometer staat links van het midden en
  is onderin rood; op geel zou dat rood wegvallen, op blauw springt het eruit.
- **Stralen en vlokarmen stoppen bij de rand.** Niets steekt buiten de cirkel uit, zodat het
  silhouet één ronde vorm blijft.
- **De rand is zwart op lage dekking, geen kleur.** Een blauwe rand kleedt de ijshelft mooi
  aan maar maakt van de gele helft een modderig olijfgroen.

## Opnieuw genereren

`generate.py` is de enige bron: het tekent de figuur één keer en schrijft daar zowel de
PNG's als `icon-source.svg` uit. Beide komen dus altijd overeen; `icon-source.svg` zelf
wordt door Home Assistant niet gebruikt en is er alleen als vectorbron.

```bash
python -m pip install pycairo
python generate.py
```

Wil je de kleuren of de vormen aanpassen, doe dat in `generate.py` en draai het script
opnieuw. De maten bovenin dat bestand (straal, armlengte, positie van de thermometer) zijn
de knoppen waar je aan draait.

---

# Brand logo

Since **Home Assistant 2026.3**, a custom integration can simply bundle its own brand logo —
an external pull request to [home-assistant/brands](https://github.com/home-assistant/brands)
is no longer needed. Home Assistant automatically reads the images from this `brand/` folder
inside the integration and gives them priority over the central brands CDN. No change to
`manifest.json` is required.

The files Home Assistant uses:

- `icon.png` (256×256)
- `icon@2x.png` (512×512)
- `logo.png` (256×256)
- `logo@2x.png` (512×512)

## The design

A circle made of two halves. On the left half a snowflake in white on ice blue, on the right
half a sun in yellow with rays. Over them, slightly left of centre, a thermometer running
from red at the bottom to white at the top.

Three choices are deliberate:

- **The snowflake sits left, the sun right.** The thermometer sits left of centre and is red
  at the bottom; on yellow that red would wash out, on blue it stands out.
- **Rays and flake arms stop at the rim.** Nothing sticks out beyond the circle, so the
  silhouette stays one round shape.
- **The rim is black at low opacity, not a colour.** A blue rim dresses the ice half nicely
  but turns the yellow half a muddy olive.

## Regenerating

`generate.py` is the only source: it draws the figure once and writes both the PNGs and
`icon-source.svg` from it. The two therefore always match; `icon-source.svg` itself is not
used by Home Assistant and exists only as a vector source.

```bash
python -m pip install pycairo
python generate.py
```

To change the colours or the shapes, edit `generate.py` and run it again. The measurements
at the top of that file (radius, arm length, the thermometer's position) are the dials.

"""Genereert het merklogo van Climate Director.

Generates Climate Director's brand logo.

Dit script is de enige bron van het icoon: het tekent de figuur één keer en
schrijft daar zowel de PNG's uit die Home Assistant gebruikt (in
`custom_components/climate_director/brand/`) als de SVG die hiernaast als
vectorbron bewaard blijft. Daardoor kunnen die twee niet uit elkaar lopen.

This script is the icon's only source: it draws the figure once and writes both
the PNGs Home Assistant uses (into `custom_components/climate_director/brand/`)
and the SVG kept beside it as a vector source. The two therefore cannot drift
apart.

    python -m pip install pycairo
    python brand/generate.py
"""

from __future__ import annotations

import math
from pathlib import Path

import cairo

HERE = Path(__file__).parent

# De PNG's horen in de integratie, want Home Assistant leest ze daar uit. Dit
# script en zijn vectorbron horen daar juist niet: die zijn gereedschap en gaan
# elke gebruiker die de integratie installeert alleen maar mee als ballast.
#
# The PNGs belong inside the integration, because that is where Home Assistant
# reads them. This script and its vector source do not: they are tooling, and
# would only ride along as ballast with every user who installs the integration.
ICONS = HERE.parent / "custom_components" / "climate_director" / "brand"

# Alles wordt getekend op een vierkant van 512, en daarna geschaald naar het
# gevraagde formaat. Elke maat hieronder is dus in die eenheid.
#
# Everything is drawn on a 512 square and scaled to the requested size
# afterwards. Every measurement below is in that unit.
CANVAS = 512.0
CX = CY = 256.0
RADIUS = 232.0

# De thermometer staat iets links van het midden, zodat hij over beide helften
# valt en de twee aan elkaar knoopt in plaats van in één helft te verdwijnen.
#
# The thermometer sits slightly left of centre, so it crosses both halves and
# ties them together instead of disappearing into one of them.
THERMOMETER_OFFSET = -34.0

STEM_HALF = 44.0
STEM_TOP = 128.0
FLAKE_CX = 250.0
ARM = 200.0
BULB_Y = 382.0
BULB_R = 74.0

FLUID_HALF = 24.0
FLUID_TOP = 124.0
FLUID_BULB_R = 48.0


def _ice() -> cairo.LinearGradient:
    """Return the snowflake half's background: ice blue, darker at the rim."""
    gradient = cairo.LinearGradient(24, 24, 256, 488)
    gradient.add_color_stop_rgb(0.0, 0.29, 0.66, 0.93)
    gradient.add_color_stop_rgb(0.55, 0.16, 0.50, 0.82)
    gradient.add_color_stop_rgb(1.0, 0.08, 0.36, 0.65)
    return gradient


def _sun() -> cairo.LinearGradient:
    """Return the sun half's background: warm yellow into orange."""
    gradient = cairo.LinearGradient(256, 24, 488, 488)
    gradient.add_color_stop_rgb(0.0, 1.00, 0.88, 0.30)
    gradient.add_color_stop_rgb(0.55, 1.00, 0.76, 0.10)
    gradient.add_color_stop_rgb(1.0, 0.98, 0.62, 0.04)
    return gradient


def _mercury() -> cairo.LinearGradient:
    """Return the thermometer fluid: red at the bottom, white at the top."""
    gradient = cairo.LinearGradient(0, BULB_Y + BULB_R, 0, FLUID_TOP)
    gradient.add_color_stop_rgb(0.0, 0.78, 0.06, 0.18)
    gradient.add_color_stop_rgb(0.35, 0.91, 0.07, 0.18)
    gradient.add_color_stop_rgb(0.70, 1.00, 0.54, 0.48)
    gradient.add_color_stop_rgb(1.0, 1.00, 1.00, 1.00)
    return gradient


def _clip_disc(context: cairo.Context) -> None:
    """Clip to the circle the whole icon lives in."""
    context.arc(CX, CY, RADIUS, 0, 2 * math.pi)
    context.clip()


def _draw_halves(context: cairo.Context) -> None:
    """Fill the two semicircles that together form the disc."""
    context.save()
    _clip_disc(context)

    # Eerst de hele schijf blauw, daarna de rechterhelft geel eroverheen. Twee
    # rechthoeken die elkaar op de middenlijn raken laten allebei een
    # antialiasrand achter, en samen geeft dat een witte haarlijn dwars door
    # het icoon.
    #
    # The whole disc blue first, then the right half painted over it. Two
    # rectangles meeting on the centre line each leave an antialiased edge,
    # and together those show up as a white hairline across the icon.
    context.rectangle(0, 0, CANVAS, CANVAS)
    context.set_source(_ice())
    context.fill()

    context.rectangle(CX, 0, CANVAS - CX, CANVAS)
    context.set_source(_sun())
    context.fill()

    context.restore()


def _draw_sun(context: cairo.Context) -> None:
    """Draw the rays and the disc on the right half."""
    context.save()
    _clip_disc(context)
    context.rectangle(CX, 0, CANVAS - CX, CANVAS)
    context.clip()

    # Stralen als taps toelopende wiggen vanuit het midden; ze stoppen bij de
    # rand, zodat de cirkel als silhouet heel blijft.
    #
    # Rays as tapering wedges out of the centre; they stop at the rim, so the
    # circle stays whole as a silhouette.
    context.set_source_rgba(1.0, 0.96, 0.79, 0.95)
    for angle in (-72, -36, 0, 36, 72):
        radians = math.radians(angle)
        half = math.radians(9)
        context.move_to(CX, CY)
        context.line_to(
            CX + RADIUS * math.cos(radians - half), CY + RADIUS * math.sin(radians - half)
        )
        context.line_to(CX + RADIUS * math.cos(radians), CY + RADIUS * math.sin(radians))
        context.line_to(
            CX + RADIUS * math.cos(radians + half), CY + RADIUS * math.sin(radians + half)
        )
        context.close_path()
        context.fill()

    context.arc(CX, CY, 104, 0, 2 * math.pi)
    context.set_source_rgb(1.0, 0.95, 0.68)
    context.fill_preserve()
    context.set_source_rgb(1.0, 0.85, 0.30)
    context.set_line_width(10)
    context.stroke()

    context.restore()


def _draw_snowflake(context: cairo.Context) -> None:
    """Draw the six-armed flake on the left half.

    Six arms about the same centre, cut off on the centre line, so the flake
    fills exactly half the circle and the two halves meet as one shape.
    """
    context.save()
    _clip_disc(context)
    context.rectangle(0, 0, CX, CANVAS)
    context.clip()

    context.set_source_rgb(1.0, 1.0, 1.0)
    context.set_line_width(24)
    context.set_line_cap(cairo.LINE_CAP_ROUND)

    # De vlok staat 30 graden gedraaid. Met armen recht om de zes ligt er geen
    # enkele arm naar links, en blijven in deze helft alleen twee schuine takken
    # over die als pijlpunten lezen. Gedraaid waaieren er drie armen naar links.
    #
    # The flake is turned by 30 degrees. With arms straight on the sixths, not
    # one of them points left, and this half keeps only two slanted branches
    # that read as arrowheads. Turned, three arms fan out to the left.
    for turn in range(6):
        context.save()
        context.translate(FLAKE_CX, CY)
        context.rotate(math.radians(60 * turn + 30))
        context.translate(-FLAKE_CX, -CY)

        tip = CY - ARM
        context.move_to(FLAKE_CX, CY)
        context.line_to(FLAKE_CX, tip)
        context.stroke()

        # Twee paar baarden, ruim uit elkaar. Dicht op elkaar vormen ze samen
        # met de arm een pijlpunt in plaats van een tak.
        #
        # Two pairs of barbs, well apart. Close together they and the arm add up
        # to an arrowhead rather than a branch.
        for along, spread in ((40, 46), (108, 36)):
            for side in (-1, 1):
                context.move_to(FLAKE_CX, tip + along)
                context.line_to(FLAKE_CX + side * spread, tip + along - 38)
                context.stroke()

        context.restore()

    context.arc(FLAKE_CX, CY, 28, 0, 2 * math.pi)
    context.set_source_rgb(0.92, 0.96, 1.0)
    context.fill()

    context.restore()


def _draw_rim(context: cairo.Context) -> None:
    """Outline the disc, for definition on light and dark backgrounds alike.

    Deliberately black at low opacity rather than a colour: a blue-tinted rim
    darkens the ice half nicely but turns the yellow half a muddy olive. A rim
    should read as a shadow on both halves, not as a third colour.
    """
    context.arc(CX, CY, RADIUS - 4.5, 0, 2 * math.pi)
    context.set_source_rgba(0.0, 0.0, 0.0, 0.16)
    context.set_line_width(9)
    context.stroke()


def _casing_path(context: cairo.Context) -> None:
    """Trace the thermometer's outline as one closed path.

    Built as a single path rather than a stem plus a bulb: two overlapping
    shapes would each carry their own outline, leaving a seam straight across
    the middle of the thermometer.
    """
    # Waar de rechte zijkant de bol raakt.
    # Where the straight side meets the bulb.
    drop = math.sqrt(BULB_R**2 - STEM_HALF**2)
    meet_y = BULB_Y - drop
    meet_angle = math.atan2(-drop, STEM_HALF)

    context.new_path()
    context.move_to(CX - STEM_HALF, STEM_TOP)
    context.arc(CX, STEM_TOP, STEM_HALF, math.pi, 2 * math.pi)
    context.line_to(CX + STEM_HALF, meet_y)
    context.arc(CX, BULB_Y, BULB_R, meet_angle, math.pi - meet_angle)
    context.close_path()


def _draw_thermometer(context: cairo.Context) -> None:
    """Draw the thermometer over both halves."""
    context.save()
    context.translate(THERMOMETER_OFFSET, 0)

    # Witte behuizing: houdt de thermometer leesbaar op geel én op blauw.
    # White casing: keeps the thermometer readable on yellow and on blue.
    _casing_path(context)
    context.set_source_rgb(1.0, 1.0, 1.0)
    context.fill_preserve()
    context.set_source_rgb(0.48, 0.55, 0.60)
    context.set_line_width(9)
    context.set_line_join(cairo.LINE_JOIN_ROUND)
    context.stroke()

    fluid = _mercury()
    context.arc(CX, BULB_Y, FLUID_BULB_R, 0, 2 * math.pi)
    context.set_source(fluid)
    context.fill()

    context.new_path()
    context.arc(CX, FLUID_TOP + FLUID_HALF, FLUID_HALF, math.pi, 2 * math.pi)
    context.line_to(CX + FLUID_HALF, BULB_Y)
    context.line_to(CX - FLUID_HALF, BULB_Y)
    context.close_path()
    context.set_source(fluid)
    context.fill()

    context.set_source_rgb(0.48, 0.55, 0.60)
    context.set_line_width(8)
    context.set_line_cap(cairo.LINE_CAP_ROUND)
    for y, length in ((168, 22), (212, 16), (256, 22), (300, 16)):
        context.move_to(CX + STEM_HALF - 10, y)
        context.line_to(CX + STEM_HALF - 10 + length, y)
        context.stroke()

    context.restore()


def draw(context: cairo.Context) -> None:
    """Draw the complete icon onto a 512 square."""
    _draw_halves(context)
    _draw_sun(context)
    _draw_snowflake(context)
    _draw_rim(context)
    _draw_thermometer(context)


def write_png(path: Path, size: int) -> None:
    """Render the icon to a square PNG with a transparent background."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    context = cairo.Context(surface)
    context.scale(size / CANVAS, size / CANVAS)
    draw(context)
    surface.write_to_png(str(path))


def write_svg(path: Path) -> None:
    """Render the same drawing to SVG, kept as the vector source."""
    surface = cairo.SVGSurface(str(path), CANVAS, CANVAS)
    context = cairo.Context(surface)
    draw(context)
    surface.finish()


def main() -> None:
    """Write every file Home Assistant looks for, plus the vector source."""
    for name, size in (
        ("icon.png", 256),
        ("icon@2x.png", 512),
        ("logo.png", 256),
        ("logo@2x.png", 512),
    ):
        write_png(ICONS / name, size)
        print(f"wrote {name} ({size}x{size})")

    write_svg(HERE / "icon-source.svg")
    print("wrote icon-source.svg")


if __name__ == "__main__":
    main()

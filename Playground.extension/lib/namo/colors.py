# -*- coding: utf-8 -*-
"""Colour maths and the Playground palettes. Pure: no Navisworks, no .NET.

Hex colours are 'RRGGBB' text, upper case, no '#'. Every function that takes a hex
also accepts '#RRGGBB', 'RGB' shorthand and lower case, so values typed by people or
read from old settings files work. Channels are 0..255 ints, or 0..1 floats where
the name says so (rgb01, which is what Navisworks' Api.Color wants).

PALETTE is 12 categorical colours: mid tones that stay readable as fills on the
white light theme and on the #202020 dark theme, ordered so neighbours differ most.
for_values() hands them out in the order values arrive and keeps going past twelve
with generated hues (golden-angle steps), so a value never shares a colour inside
one call.

STATUS maps clash statuses (the five Navisworks Clash Detective uses, coloured as
Navisworks colours its own status icons) and common construction statuses to hex.
"""

import math

PALETTE = [
    '4E79A7',   # blue
    'F28E2B',   # orange
    'E15759',   # red
    '59A14F',   # green
    'B07AA1',   # purple
    'EDC948',   # yellow
    '76B7B2',   # teal
    'FF9DA7',   # pink
    '9C755F',   # brown
    'A0CBE8',   # light blue
    '8CD17D',   # light green
    'B6992D',   # olive gold
]

# The ramp sequential() walks, light to strong, single hue (blue).
SEQUENTIAL_STOPS = ['DCE8F5', 'A9C8E8', '6FA3D6', '3B78B8', '1D4E89']

# The ramp diverging() walks: blue (0.0), neutral grey (0.5), red (1.0).
DIVERGING_STOPS = ['2166AC', '67A9CF', 'E0E0E0', 'EF8A62', 'B2182B']

# Neutral used to ghost "everything else" and to mark missing values.
GHOST = 'BFBFBF'
MISSING = '9AA5B1'

STATUS = {
    # Clash Detective result statuses.
    'New': 'D9302C',
    'Active': 'F28E2B',
    'Reviewed': '4E79A7',
    'Approved': '59A14F',
    'Resolved': 'EDC948',
    # Construction / task statuses.
    'Not started': 'BAB0AC',
    'Planned': 'A0CBE8',
    'In progress': '4E79A7',
    'Complete': '59A14F',
    'Delayed': 'E15759',
    'On hold': 'F28E2B',
    'Demolish': '9C755F',
    'Temporary': 'B07AA1',
    'Existing': '9AA5B1',
}


# ---- parsing and conversion -------------------------------------------------


def parse_hex(text):
    """'RRGGBB' for anything that reads as a hex colour, else None.

    Accepts 'RRGGBB', '#RRGGBB', 'RGB', '#RGB' (shorthand doubles each digit),
    'AARRGGBB' / '#AARRGGBB' (alpha dropped, the form WPF prints), any case and
    surrounding spaces. Never raises.
    """
    if text is None:
        return None
    try:
        value = str(text).strip()
    except Exception:
        return None
    if value.startswith('#'):
        value = value[1:]
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    elif len(value) == 8:
        value = value[2:]
    if len(value) != 6:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value.upper()


def _need(hex_value):
    parsed = parse_hex(hex_value)
    if parsed is None:
        raise ValueError('not a hex colour: %r' % (hex_value,))
    return parsed


def hex_to_rgb(hex_value):
    """(r, g, b) ints 0..255. Raises ValueError for text that is not a colour."""
    value = _need(hex_value)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _channel(value):
    value = int(round(float(value)))
    return 0 if value < 0 else 255 if value > 255 else value


def rgb_to_hex(r, g=None, b=None):
    """'RRGGBB' from three 0..255 numbers (or one (r, g, b) tuple). Clamps and rounds."""
    if g is None and b is None:
        r, g, b = r
    return '%02X%02X%02X' % (_channel(r), _channel(g), _channel(b))


def rgb01(hex_value):
    """(r, g, b) floats 0..1: what Api.Color(r, g, b) takes."""
    r, g, b = hex_to_rgb(hex_value)
    return (r / 255.0, g / 255.0, b / 255.0)


def from_rgb01(r, g=None, b=None):
    """'RRGGBB' from 0..1 floats (or one tuple): the reverse of rgb01."""
    if g is None and b is None:
        r, g, b = r
    return rgb_to_hex(float(r) * 255.0, float(g) * 255.0, float(b) * 255.0)


# ---- perception ---------------------------------------------------------------


def _linear(channel):
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_value):
    """WCAG relative luminance, 0.0 (black) to 1.0 (white)."""
    r, g, b = hex_to_rgb(hex_value)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(hex_a, hex_b):
    """WCAG contrast ratio between two colours, 1.0 to 21.0."""
    la, lb = luminance(hex_a), luminance(hex_b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def contrast_text(hex_value):
    """'000000' or 'FFFFFF': whichever text colour reads better on this fill."""
    if contrast_ratio(hex_value, '000000') >= contrast_ratio(hex_value, 'FFFFFF'):
        return '000000'
    return 'FFFFFF'


def distance(hex_a, hex_b):
    """Plain RGB distance, 0 to about 441. Good enough to tell 'too close' apart."""
    a, b = hex_to_rgb(hex_a), hex_to_rgb(hex_b)
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


# ---- mixing -------------------------------------------------------------------


def blend(hex_a, hex_b, t):
    """The colour t of the way from a to b (t clamped to 0..1), mixed in RGB."""
    t = _clamp01(t)
    a, b = hex_to_rgb(hex_a), hex_to_rgb(hex_b)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def lighten(hex_value, amount=0.2):
    """Towards white by amount (0..1)."""
    return blend(hex_value, 'FFFFFF', amount)


def darken(hex_value, amount=0.2):
    """Towards black by amount (0..1)."""
    return blend(hex_value, '000000', amount)


def _clamp01(t):
    try:
        t = float(t)
    except (TypeError, ValueError):
        return 0.0
    if t != t:                      # NaN
        return 0.0
    return 0.0 if t < 0.0 else 1.0 if t > 1.0 else t


def ramp(stops, t):
    """The colour at t (0..1) along evenly spaced hex stops, linear in RGB."""
    if not stops:
        raise ValueError('a ramp needs at least one stop')
    if len(stops) == 1:
        return _need(stops[0])
    t = _clamp01(t)
    span = t * (len(stops) - 1)
    index = int(math.floor(span))
    if index >= len(stops) - 1:
        return _need(stops[-1])
    return blend(stops[index], stops[index + 1], span - index)


def sequential(t):
    """0..1 light-to-strong blue ramp: heatmaps, ordered quantities, pick order."""
    return ramp(SEQUENTIAL_STOPS, t)


def diverging(t):
    """0..1 blue, through neutral grey at 0.5, to red: deltas around a midpoint."""
    return ramp(DIVERGING_STOPS, t)


def bands(n, stops=None):
    """n colours light to strong for n ordered bands (n=1 gives the strong end).

    Band i sits at t = (i + 1) / n, so even the first band is a visible tint rather
    than the palest stop.
    """
    n = int(n)
    if n <= 0:
        return []
    stops = stops or SEQUENTIAL_STOPS
    return [ramp(stops, float(i + 1) / n) for i in range(n)]


# ---- categorical --------------------------------------------------------------


def hsl_to_hex(h, s, l):
    """'RRGGBB' from hue in degrees and saturation/lightness 0..1."""
    h = (float(h) % 360.0) / 360.0
    s = _clamp01(s)
    l = _clamp01(l)
    if s == 0:
        return rgb_to_hex(l * 255, l * 255, l * 255)
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def hue(t):
        t %= 1.0
        if t < 1.0 / 6:
            return p + (q - p) * 6 * t
        if t < 0.5:
            return q
        if t < 2.0 / 3:
            return p + (q - p) * (2.0 / 3 - t) * 6
        return p

    return rgb_to_hex(hue(h + 1.0 / 3) * 255, hue(h) * 255, hue(h - 1.0 / 3) * 255)


def generated(index):
    """The index-th colour after the palette runs out: golden-angle hue steps at a
    fixed mid saturation and lightness, so they stay readable in both themes."""
    return hsl_to_hex(17.0 + index * 137.508, 0.55, 0.52)


def color_at(index, palette=None):
    """The palette colour for a position, continuing with generated() past its end."""
    palette = palette or PALETTE
    if index < len(palette):
        return _need(palette[index])
    return generated(index - len(palette))


def for_values(values, palette=None):
    """[(value, hex)] for each DISTINCT value, in the order they first appear.

    Stable: the same values in the same order always get the same colours, and a
    repeated value keeps its first colour (it is listed once). Values may be any
    hashable (text, numbers, None).
    """
    out = []
    seen = {}
    for value in values:
        key = _hashable(value)
        if key in seen:
            continue
        seen[key] = True
        out.append((value, color_at(len(out), palette)))
    return out


def _hashable(value):
    try:
        hash(value)
        return value
    except TypeError:
        return repr(value)


def status_color(name, default=None):
    """STATUS colour for a status name, matched case-insensitively and with
    surrounding spaces ignored; default (or MISSING) when unknown."""
    if name is not None:
        wanted = str(name).strip().lower()
        for key in sorted(STATUS):
            if key.lower() == wanted:
                return STATUS[key]
    return default if default is not None else MISSING

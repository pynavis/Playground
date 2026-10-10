# -*- coding: utf-8 -*-
"""Glyphs for the Look panel.

Family marks: the rounded swatch square is a colour (filled accent = what the
tool paints, ink outline = an object or a value left alone), so the three
colour tools read as one family: a grid sorted into colours, a fanned deck of
saved chips, a legend card listing them. The rest keep one idea each: a roller
for status painting, an eyedropper for matching, a solid block between faded
dashed ones for ghosting, blocks pushed out from a centre for exploding, an
eraser for resetting, a framed horizon for the background and a projection
screen for presenting.
"""
import math

import make_icons as pn  # noqa: F401  (pyNavis' generator: Ctx and the shared marks)

S = 4
TAB = 'Model.tab/Look.panel/'


def _rotated_rect(cx, cy, w, h, angle, pivot=None):
    """Corners of a w x h rectangle centred on (cx, cy), turned by angle
    degrees about pivot (default its centre)."""
    px, py = pivot or (cx, cy)
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for dx, dy in ((-w / 2.0, -h / 2.0), (w / 2.0, -h / 2.0), (w / 2.0, h / 2.0), (-w / 2.0, h / 2.0)):
        x, y = cx + dx - px, cy + dy - py
        pts.append((px + x * ca - y * sa, py + x * sa + y * ca))
    return pts


def _dashed(c, pts, dash, gap, color=None, w=None, closed=True):
    """A dashed polyline (closed by default): the faded, see-through outline."""
    path = list(pts) + ([pts[0]] if closed else [])
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        if not length:
            continue
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        t = 0.0
        while t < length:
            end = min(length, t + dash)
            c.line([(x0 + ux * t, y0 + uy * t), (x0 + ux * end, y0 + uy * end)], color=color, w=w)
            t = end + gap


def _swatch(c, x0, y0, x1, y1, filled, rad=6, w=None):
    if filled:
        c.rrect(x0, y0, x1, y1, rad=rad, w=0, fill=c.t['accent'])
    else:
        c.rrect(x0, y0, x1, y1, rad=rad, w=w)


# ---- the colour family ------------------------------------------------------------


def ic_color_by_property(c):
    """A grid of objects sorted into colours: two painted, two left as they are."""
    if c.small:
        _swatch(c, 4, 4, 44, 44, True, rad=8)
        _swatch(c, 52, 4, 92, 44, False, rad=8)
        _swatch(c, 4, 52, 44, 92, False, rad=8)
        _swatch(c, 52, 52, 92, 92, True, rad=8)
    else:
        _swatch(c, 10, 10, 44, 44, True, rad=7)
        _swatch(c, 52, 10, 86, 44, False, rad=7)
        _swatch(c, 10, 52, 44, 86, False, rad=7)
        _swatch(c, 52, 52, 86, 86, True, rad=7)


def _chip(c, angle, pivot, width, height, rivet=10, **kw):
    """One colour chip of the deck: a width x height card riveted at pivot,
    `rivet` above its bottom edge, turned about it by angle degrees."""
    px, py = pivot
    c.poly(_rotated_rect(px, py - height / 2.0 + rivet, width, height, angle, pivot), **kw)


def ic_color_presets(c):
    """A fan deck of colour chips on one rivet: saved schemes, the front one
    in accent being applied."""
    paper = c.t['paper']
    if c.small:
        pivot = (30, 80)
        _chip(c, -6, pivot, 30, 80, 12, fill=paper, w=12)
        _chip(c, 38, pivot, 30, 80, 12, fill=c.t['accent'], w=0)
    else:
        pivot = (32, 78)
        _chip(c, -12, pivot, 24, 70, 10, fill=paper, w=7)
        _chip(c, 14, pivot, 24, 70, 10, fill=paper, w=7)
        _chip(c, 40, pivot, 24, 70, 10, fill=c.t['accent'], w=0)
        c.disc(pivot[0], pivot[1], 4.5, paper)


def ic_legend_maker(c):
    """A legend card: accent swatches, each with its ink label line."""
    if c.small:
        _swatch(c, 4, 8, 36, 40, True, rad=7)
        c.line([(50, 24), (92, 24)], w=14)
        _swatch(c, 4, 56, 36, 88, True, rad=7)
        c.line([(50, 72), (80, 72)], w=14)
    else:
        c.rrect(8, 8, 88, 88, rad=9)
        for y, end in ((22, 72), (42, 66), (62, 74)):
            _swatch(c, 20, y, 34, y + 14, True, rad=3)
            c.line([(44, y + 7), (end, y + 7)], w=6)


# ---- the other look tools --------------------------------------------------------------


def ic_trade_ghost(c):
    """The focus trade solid in ink between two faded, dashed neighbours."""
    if c.small:
        c.rrect(32, 6, 64, 90, rad=8, w=0, fill=c.t['ink'])
        _dashed(c, [(4, 22), (22, 22), (22, 74), (4, 74)], 9, 9, c.t['accent'], 10, closed=False)
        _dashed(c, [(92, 22), (74, 22), (74, 74), (92, 74)], 9, 9, c.t['accent'], 10, closed=False)
    else:
        c.rrect(36, 12, 60, 84, rad=6, w=0, fill=c.t['ink'])
        _dashed(c, [(8, 26), (26, 26), (26, 70), (8, 70)], 6, 6, c.t['accent'], 5)
        _dashed(c, [(70, 26), (88, 26), (88, 70), (70, 70)], 6, 6, c.t['accent'], 5)


def ic_status_painter(c):
    """A paint roller: the accent sleeve lays the status colour."""
    if c.small:
        c.rrect(4, 6, 72, 38, rad=10, w=0, fill=c.t['accent'])
        c.line([(72, 22), (90, 22), (90, 54), (50, 54), (50, 66)], w=12)
        c.rrect(40, 64, 60, 94, rad=6, w=0, fill=c.t['ink'])
    else:
        c.rrect(10, 10, 68, 36, rad=9, w=0, fill=c.t['accent'])
        c.line([(68, 23), (84, 23), (84, 50), (48, 50), (48, 60)], w=7)
        c.rrect(41, 58, 55, 90, rad=5, w=0, fill=c.t['ink'])


def ic_match_appearance(c):
    """An eyedropper: the ink pipette has taken up the accent drop it lets fall."""
    if c.small:
        c.line([(22, 74), (60, 36)], w=16)
        c.disc(70, 26, 18, c.t['ink'])
        c.disc(14, 84, 11, c.t['accent'])
    else:
        c.line([(30, 66), (58, 38)], w=10)
        c.line([(48, 30), (66, 48)], w=8)
        c.disc(70, 26, 14, c.t['ink'])
        c.poly([(13, 78), (27, 78), (20, 64)], fill=c.t['accent'], w=0)
        c.disc(20, 80, 8, c.t['accent'])


def _arrow_out(c, x0, y0, x1, y1, w, head):
    """A short accent arrow from (x0, y0) to (x1, y1) with a filled head."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    bx, by = x1 - ux * head, y1 - uy * head
    c.line([(x0, y0), (bx, by)], color=c.t['accent'], w=w)
    px, py = -uy, ux
    c.poly([(x1, y1), (bx + px * head * 0.62, by + py * head * 0.62),
            (bx - px * head * 0.62, by - py * head * 0.62)], color=c.t['accent'], fill=c.t['accent'], w=0)


def ic_exploded_view(c):
    """Four blocks pushed out from the centre along the accent arrows."""
    if c.small:
        for x0, y0 in ((2, 2), (62, 2), (2, 62), (62, 62)):
            c.rrect(x0, y0, x0 + 32, y0 + 32, rad=6, w=12)
        c.disc(48, 48, 10, c.t['accent'])
    else:
        for x0, y0 in ((6, 6), (64, 6), (6, 64), (64, 64)):
            c.rrect(x0, y0, x0 + 26, y0 + 26, rad=5)
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            _arrow_out(c, 48 + sx * 4, 48 + sy * 4, 48 + sx * 15, 48 + sy * 15, 5, 8)


def ic_reset_overrides(c):
    """An eraser lifting the accent override off: back to the model's own look."""
    body = _rotated_rect(52, 42, 30, 64, 45)
    if c.small:
        body = _rotated_rect(50, 44, 40, 76, 45)
        c.poly(body, w=13)
        tip = _rotated_rect(32, 62, 40, 26, 45, (50, 44))
        c.poly([body[3], body[0]] and tip, fill=c.t['accent'], w=0)
        c.line([(8, 92), (90, 92)], w=12)
    else:
        c.poly(body, w=7)
        mid_a = ((body[0][0] + body[3][0]) / 2.0, (body[0][1] + body[3][1]) / 2.0)
        mid_b = ((body[1][0] + body[2][0]) / 2.0, (body[1][1] + body[2][1]) / 2.0)
        c.poly([body[3], mid_a, mid_b, body[2]], fill=c.t['accent'], w=0)
        c.line([(10, 88), (86, 88)], w=7)


def _cube(c, cx, cy, r, body, edges, w):
    """An isometric block: the model standing in front of the backdrop."""
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in (-90, -30, 30, 90, 150, 210)]
    c.poly(pts, fill=body, w=0)
    c.line([pts[5], (cx, cy), pts[1]], color=edges, w=w)
    c.line([(cx, cy), pts[3]], color=edges, w=w)


def ic_background(c):
    """The view frame filled with an accent backdrop, the model block in front."""
    if c.small:
        c.rrect(4, 8, 92, 88, rad=10, w=0, fill=c.t['accent'])
        _cube(c, 48, 50, 30, c.t['ink'], c.t['accent'], 7)
    else:
        c.rrect(8, 12, 88, 84, rad=9, w=0, fill=c.t['accent'])
        c.rrect(8, 12, 88, 84, rad=9)
        _cube(c, 48, 50, 22, c.t['ink'], c.t['accent'], 5)


# ---- presenting ------------------------------------------------------------------------


def _screen(c, fill=None):
    """A projection screen on its stand: bar, screen, three legs."""
    c.line([(8, 12), (88, 12)], w=7)
    if fill:
        c.rrect(14, 16, 82, 64, rad=4, w=0, fill=fill)
    c.rrect(14, 16, 82, 64, rad=4, w=6)
    c.line([(48, 64), (48, 76)], w=6)
    c.line([(48, 76), (34, 90)], w=6)
    c.line([(48, 76), (62, 90)], w=6)


def _corners(c, x0, y0, x1, y1, arm, inward, color, w):
    """Four L corners: pointing out (enter full screen) or in (leave it)."""
    for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        if inward:
            tip = (cx + sx * arm, cy + sy * arm)
            c.line([(tip[0] - sx * arm, tip[1]), tip, (tip[0], tip[1] - sy * arm)], color=color, w=w)
        else:
            c.line([(cx + sx * arm, cy), (cx, cy), (cx, cy + sy * arm)], color=color, w=w)


def ic_presentation_off(c):
    """The screen with accent corners opening out: present full width. Also the
    small file."""
    if c.small:
        c.rrect(4, 8, 92, 70, rad=6, w=12)
        c.line([(48, 70), (48, 92)], w=12)
        _corners(c, 22, 24, 74, 54, 12, False, c.t['accent'], 11)
    else:
        _screen(c)
        _corners(c, 26, 26, 70, 54, 9, False, c.t['accent'], 6)


def ic_presentation_on(c):
    """The screen filled accent with paper corners closing in: presenting now,
    click to come back."""
    _screen(c, fill=c.t['accent'])
    _corners(c, 26, 26, 70, 54, 9, True, c.t['paper'], 6)


def ic_exit_presentation(c):
    """The corners closing in on the screen: put everything back."""
    if c.small:
        c.rrect(4, 8, 92, 70, rad=6, w=0, fill=c.t['accent'])
        c.line([(48, 70), (48, 92)], w=12)
        _corners(c, 22, 24, 74, 54, 12, True, c.t['paper'], 11)
    else:
        ic_presentation_on(c)


ICONS = {
    TAB + 'Color_by_Property.pushbutton': ic_color_by_property,
    TAB + 'Color_Presets.pushbutton': ic_color_presets,
    TAB + 'Trade_Ghost.pushbutton': ic_trade_ghost,
    TAB + 'Status_Painter.pushbutton': ic_status_painter,
    TAB + 'Look_Tools.stack/Legend_Maker.pushbutton': ic_legend_maker,
    TAB + 'Look_Tools.stack/Match_Appearance.pushbutton': ic_match_appearance,
    TAB + 'Look_Tools.stack/Exploded_View.pushbutton': ic_exploded_view,
    TAB + 'View_Tools.stack/Reset_All_Overrides.pushbutton': ic_reset_overrides,
    TAB + 'View_Tools.stack/Background.pushbutton': ic_background,
    TAB + 'Exit_Presentation.nobutton': ic_exit_presentation,
}
TOGGLES = {
    TAB + 'Presentation_Mode.toggle': (ic_presentation_off, ic_presentation_on),
}
DOCKPANE_ON = {}

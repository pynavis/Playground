# -*- coding: utf-8 -*-
"""Glyphs for the Clash Setup and Clash Results panels (and the pyRevit companion).

Family rules, kept with pyNavis' own clash glyphs: the accent spark is a collision and
appears wherever the tool acts on clashes; ink draws the thing (a matrix, a card, a
person, an element), accent draws what the tool does to it. Small 32 px drawings are
separate, heavier, simpler versions.

Run this file directly (python dev/icons/clash_setup_results.py) to write the pyRevit
companion's icons too; dev/make_icons.py only writes into the Playground extension.
"""
import math
import os
import sys

_PYNAVIS_TOOLS = os.path.join(os.environ.get('PYNAVIS_SRC') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'pyNavis'), 'tools')
if _PYNAVIS_TOOLS not in sys.path:
    sys.path.insert(0, _PYNAVIS_TOOLS)

import make_icons as pn  # noqa: E402  (pyNavis' generator)


def _spark(c, cx, cy, arm, w):
    pn.spark(c, cx, cy, arm, w)


def _arrow(c, p0, p1, w, head):
    """A straight accent arrow from p0 to p1 with a filled head at p1."""
    col = c.t['accent']
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    base = (p1[0] - ux * head, p1[1] - uy * head)
    c.line([p0, (p1[0] - ux * head * 0.6, p1[1] - uy * head * 0.6)], color=col, w=w)
    px, py = -uy, ux
    c.poly([p1, (base[0] + px * head * 0.6, base[1] + py * head * 0.6),
            (base[0] - px * head * 0.6, base[1] - py * head * 0.6)], color=col, fill=col, w=0)


def _double_arrow(c, x0, x1, y, w, head):
    col = c.t['accent']
    c.line([(x0 + head * 0.6, y), (x1 - head * 0.6, y)], color=col, w=w)
    c.poly([(x0, y), (x0 + head, y - head * 0.6), (x0 + head, y + head * 0.6)], color=col, fill=col, w=0)
    c.poly([(x1, y), (x1 - head, y - head * 0.6), (x1 - head, y + head * 0.6)], color=col, fill=col, w=0)


# ---- Clash Setup ----------------------------------------------------------------------------


def ic_clash_matrix(c):
    """A trade matrix in ink; accent sparks in the cells that become tests."""
    if c.small:
        c.rrect(6, 6, 90, 90, rad=10, w=11)
        c.line([(48, 12), (48, 84)], w=9)
        c.line([(12, 48), (84, 48)], w=9)
        _spark(c, 69, 69, 13, 10)
        return
    c.rrect(10, 10, 86, 86, rad=8, w=7)
    for p in (35.3, 60.7):
        c.line([(p, 14), (p, 82)], w=5)
        c.line([(14, p), (82, p)], w=5)
    _spark(c, 73, 48, 8, 5)
    _spark(c, 48, 73, 8, 5)


def ic_clash_templates(c):
    """Two stacked cards (saved definitions) with the clash spark on the front one."""
    paper = c.t['paper']
    if c.small:
        c.rrect(32, 6, 90, 62, rad=8, w=11)
        c.rrect(6, 32, 64, 90, rad=8, w=11, fill=paper)
        _spark(c, 35, 61, 14, 10)
        return
    c.rrect(26, 8, 86, 64, rad=7, w=7)
    c.rrect(10, 30, 70, 86, rad=7, w=7, fill=paper)
    _spark(c, 40, 58, 14, 7)


def ic_scan_vs_model(c):
    """Scan points beside a design element; the accent gap between them is measured."""
    ink = c.t['ink']
    if c.small:
        for y in (18, 48, 78):
            c.disc(12, y, 8, ink)
        c.rrect(58, 8, 90, 88, rad=6, w=11)
        _double_arrow(c, 24, 52, 48, 10, 14)
        return
    jitter = (0, 5, -2, 4, 1)
    for x in (10, 24):
        for row, y in enumerate((18, 34, 50, 66, 82)):
            c.disc(x + jitter[row] * (1 if x < 20 else -1), y, 4.5, ink)
    c.rrect(64, 12, 88, 84, rad=5, w=7)
    _double_arrow(c, 33, 57, 48, 7, 12)


# ---- Clash Results ----------------------------------------------------------------------------


def ic_clash_namer(c):
    """A label tag in ink; the accent name written on it."""
    if c.small:
        c.poly([(6, 22), (58, 22), (90, 48), (58, 74), (6, 74)], w=11)
        c.line([(20, 48), (52, 48)], color=c.t['accent'], w=11)
        return
    c.poly([(8, 28), (60, 28), (88, 48), (60, 68), (8, 68)], w=7)
    c.circle(68, 48, 4, w=4)
    c.line([(20, 42), (50, 42)], color=c.t['accent'], w=6)
    c.line([(20, 55), (40, 55)], color=c.t['accent'], w=6)


def ic_status_rules(c):
    """Rule rows in ink; the accent light marks the rule that decides."""
    accent = c.t['accent']
    if c.small:
        c.disc(16, 28, 12, accent)
        c.line([(38, 28), (90, 28)], w=11)
        c.circle(16, 68, 9, w=8)
        c.line([(38, 68), (90, 68)], w=11)
        return
    c.disc(16, 26, 8, accent)
    c.line([(32, 26), (86, 26)], w=6)
    for y in (48, 70):
        c.circle(16, y, 6, w=4)
        c.line([(32, y), (86, y)], w=6)


def ic_clash_assigner(c):
    """A person in ink; the accent spark is the clash in their court."""
    ww = (11 if c.small else 7) * pn.S
    if c.small:
        c.circle(32, 30, 15, w=11)
        c.d.arc([6 * pn.S, 54 * pn.S, 60 * pn.S, 108 * pn.S], start=180, end=360,
                fill=c.t['ink'], width=int(ww))
        _spark(c, 72, 30, 16, 10)
        return
    c.circle(38, 32, 14, w=7)
    c.d.arc([14 * pn.S, 56 * pn.S, 62 * pn.S, 104 * pn.S], start=180, end=360,
            fill=c.t['ink'], width=int(ww))
    _spark(c, 72, 26, 14, 7)


def ic_clash_to_viewpoints(c):
    """The pyNavis viewpoint eye with a clash spark for its pupil."""
    pn.eye(c)
    if c.small:
        _spark(c, 48, 48, 15, 11)
    else:
        _spark(c, 48, 48, 12, 7)


def ic_clash_heatmap(c):
    """An element in ink with an accent hotspot glowing on it."""
    accent = c.t['accent']
    if c.small:
        c.rrect(6, 22, 90, 74, rad=6, w=11)
        c.disc(56, 48, 15, accent)
        return
    c.rrect(8, 22, 88, 74, rad=6, w=7)
    c.disc(58, 48, 9, accent)
    c.circle(58, 48, 18, color=accent, w=5)


def ic_show_in_revit(c):
    """An element in ink sent out by the accent arrow."""
    if c.small:
        c.rrect(6, 40, 54, 88, rad=6, w=11)
        _arrow(c, (34, 58), (88, 8), 11, 24)
        return
    c.rrect(10, 38, 56, 84, rad=6, w=7)
    _arrow(c, (36, 58), (86, 10), 7, 18)


def ic_show_from_revit(c):
    """The accent arrow brings an element in and lands on it."""
    if c.small:
        c.rrect(6, 40, 54, 88, rad=6, w=11)
        _arrow(c, (90, 6), (44, 52), 11, 24)
        return
    c.rrect(10, 38, 56, 84, rad=6, w=7)
    _arrow(c, (88, 8), (46, 50), 7, 18)


SETUP = 'Coordinate.tab/Clash_Setup.panel/'
RESULTS = 'Coordinate.tab/Clash_Results.panel/'

ICONS = {
    SETUP + 'Clash_Matrix.pushbutton': ic_clash_matrix,
    SETUP + 'Clash_Templates.pushbutton': ic_clash_templates,
    SETUP + 'Scan_vs_Model.pushbutton': ic_scan_vs_model,
    RESULTS + 'Clash_Namer.pushbutton': ic_clash_namer,
    RESULTS + 'Status_Rules.pushbutton': ic_status_rules,
    RESULTS + 'Clash_Assigner.pushbutton': ic_clash_assigner,
    RESULTS + 'Clash_to_Viewpoints.pushbutton': ic_clash_to_viewpoints,
    RESULTS + 'Clash_Heatmap.pushbutton': ic_clash_heatmap,
    RESULTS + 'Revit_Link.stack/Show_in_Revit.pushbutton': ic_show_in_revit,
    RESULTS + 'Revit_Link.stack/Show_from_Revit.pushbutton': ic_show_from_revit,
}
TOGGLES = {}
DOCKPANE_ON = {}

# The pyRevit companion: in Revit, Show from Navisworks brings elements in, Send to
# Navisworks sends them out.
COMPANION = {
    'Show from Navisworks.pushbutton': ic_show_from_revit,
    'Send to Navisworks.pushbutton': ic_show_in_revit,
}


def write_companion_icons():
    """icon.png and icon.dark.png (96 px) for each companion button."""
    here = os.path.dirname(os.path.abspath(__file__))
    panel = os.path.join(os.path.dirname(os.path.dirname(here)), 'companions',
                         'PlaygroundLink.extension', 'Playground.tab', 'Navisworks.panel')
    written = 0
    for folder, fn in sorted(COMPANION.items()):
        target = os.path.join(panel, folder)
        for suffix, theme in pn.THEMES:
            pn.render(fn, theme, False).png(pn.LARGE_PX).save(os.path.join(target, 'icon%s.png' % suffix))
            written += 1
    return written


if __name__ == '__main__':
    print('companion icons: %d files' % write_companion_icons())

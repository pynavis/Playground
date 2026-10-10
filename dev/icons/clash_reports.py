# -*- coding: utf-8 -*-
"""Glyphs for the Clash Reports panel.

Family rules, shared with pyNavis' Clash Report and the Clash Setup / Clash Results glyphs:
the accent spark is a collision; ink draws the document or chart the report becomes
(a workbook grid, a ring chart, a count grid, a camera, a delta, a burn-down, a set of
trade sheets) and accent draws the clashes in it or what the tool does. Small 32 px
drawings are separate, heavier and simpler.
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


def _arc(c, cx, cy, r, start, end, color, w):
    """An arc stroke (degrees, 0 = 3 o'clock, clockwise) with round caps."""
    s = pn.S
    width = int(w * s)
    c.d.arc([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], start=start, end=end, fill=color, width=width)
    for angle in (start, end):
        a = math.radians(angle)
        x = cx + (r - w / 2.0) * math.cos(a)
        y = cy + (r - w / 2.0) * math.sin(a)
        c.disc(x, y, w / 2.0, color)


# ---- large buttons ------------------------------------------------------------------------------


def ic_clash_excel(c):
    """A workbook grid in ink with the clash spark on it."""
    if c.small:
        c.rrect(6, 6, 56, 90, rad=7, w=12)
        c.line([(12, 34), (50, 34)], w=9)
        c.line([(28, 40), (28, 84)], w=9)
        _spark(c, 72, 66, 19, 12)
        return
    c.rrect(8, 10, 64, 86, rad=6, w=7)
    c.line([(13, 32), (59, 32)], w=6)
    c.line([(13, 54), (59, 54)], w=5)
    c.line([(30, 37), (30, 81)], w=5)
    _spark(c, 74, 64, 18, 8)


def ic_clash_dashboard(c):
    """A ring chart in ink; the accent share of it is the open clashes, the spark in the
    middle says what is counted."""
    ink = c.t['ink']
    accent = c.t['accent']
    if c.small:
        _arc(c, 48, 48, 42, 0, 360, ink, 14)
        _arc(c, 48, 48, 42, -90, 30, accent, 14)
        return
    _arc(c, 48, 48, 38, 0, 360, ink, 9)
    _arc(c, 48, 48, 38, -90, 40, accent, 9)
    _spark(c, 48, 48, 11, 6)


def ic_clash_count_matrix(c):
    """A count grid in ink; the busiest cells filled in accent."""
    accent = c.t['accent']
    if c.small:
        c.rrect(6, 6, 90, 90, rad=10, w=11)
        c.line([(48, 12), (48, 84)], w=9)
        c.line([(12, 48), (84, 48)], w=9)
        c.rrect(56, 14, 82, 40, rad=4, w=0, fill=accent)
        return
    c.rrect(10, 10, 86, 86, rad=8, w=7)
    for p in (35.3, 60.7):
        c.line([(p, 14), (p, 82)], w=5)
        c.line([(14, p), (82, p)], w=5)
    c.rrect(65, 15, 81, 31, rad=3, w=0, fill=accent)
    c.rrect(43, 19, 53, 29, rad=2, w=0, fill=accent)
    c.rrect(68, 43, 78, 53, rad=2, w=0, fill=accent)


def ic_per_trade_reports(c):
    """The clashes (accent spark) sent out along accent lines to one ink sheet per trade."""
    accent = c.t['accent']
    if c.small:
        _spark(c, 18, 48, 15, 11)
        for y in (14, 48, 82):
            c.line([(36, 48), (52, y)], color=accent, w=8)
        for y0 in (4, 38, 72):
            c.rrect(58, y0, 92, y0 + 20, rad=4, w=9)
        return
    _spark(c, 16, 48, 11, 6)
    for y in (21, 48, 75):
        c.line([(30, 48), (50, y)], color=accent, w=5)
    for y0 in (10, 37, 64):
        c.rrect(56, y0, 88, y0 + 22, rad=4, w=6)
        c.line([(63, y0 + 11), (81, y0 + 11)], w=4)


# ---- History stack (small rows; the large art is drawn too) ------------------------------------


def ic_snapshot(c):
    """A camera in ink whose lens holds the clash spark: the clashes captured now."""
    ink = c.t['ink']
    if c.small:
        c.rrect(4, 30, 92, 88, rad=10, w=10)
        c.poly([(30, 31), (38, 14), (58, 14), (66, 31)], w=0, fill=ink)
        _spark(c, 48, 59, 16, 10)
        return
    c.rrect(8, 30, 88, 82, rad=8, w=7)
    c.poly([(32, 31), (39, 18), (57, 18), (64, 31)], w=0, fill=ink)
    c.circle(48, 56, 18, w=6)
    _spark(c, 48, 56, 9, 6)


def ic_clash_delta(c):
    """The delta sign in ink, the clash spark beside it: what changed since the snapshot."""
    if c.small:
        c.poly([(30, 6), (56, 58), (4, 58)], w=11)
        _spark(c, 76, 76, 15, 11)
        return
    c.poly([(32, 10), (58, 62), (6, 62)], w=7)
    _spark(c, 76, 76, 14, 8)


def ic_clash_trends(c):
    """Chart axes in ink; the accent line burns down."""
    accent = c.t['accent']
    if c.small:
        c.line([(8, 6), (8, 88), (90, 88)], w=11)
        c.line([(22, 18), (44, 44), (60, 36), (86, 72)], color=accent, w=11)
        return
    c.line([(12, 10), (12, 84), (88, 84)], w=7)
    c.line([(24, 22), (42, 44), (58, 38), (80, 68)], color=accent, w=7)
    c.disc(80, 68, 7, accent)


PANEL = 'Coordinate.tab/Clash_Reports.panel/'
STACK = PANEL + 'History.stack/'

ICONS = {
    PANEL + 'Clash_Excel_Report.pushbutton': ic_clash_excel,
    PANEL + 'Clash_Dashboard.pushbutton': ic_clash_dashboard,
    PANEL + 'Clash_Count_Matrix.pushbutton': ic_clash_count_matrix,
    PANEL + 'Per_Trade_Reports.pushbutton': ic_per_trade_reports,
    STACK + 'Snapshot_Clashes.pushbutton': ic_snapshot,
    STACK + 'Clash_Delta.pushbutton': ic_clash_delta,
    STACK + 'Clash_Trends.pushbutton': ic_clash_trends,
}
TOGGLES = {}
DOCKPANE_ON = {}

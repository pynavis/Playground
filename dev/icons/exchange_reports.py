# -*- coding: utf-8 -*-
"""Glyphs for the Exchange panel (Project) and the Reports panel (Dev).

The pyNavis language: neutral ink draws the THING, one solid accent mark draws what the
tool DOES. The two exporters share the accent verb (an arrow leaving up and to the
right: out of Navisworks) and differ in the thing: a triangulated box for raw geometry,
a building with storeys for IFC. The two report tools share the template page: Report
Templates runs it (the accent play mark), Scheduled Reports runs it on a calendar (the
accent clock). Small 32 px files are separate, simpler drawings with fewer parts.
"""
import math

import make_icons as pn  # noqa: F401  (pyNavis' generator: Ctx helpers and shared marks)

PROJECT = 'Project.tab/Exchange.panel/'
DEV = 'Dev.tab/Reports.panel/'


# ---- shared marks -------------------------------------------------------------------------


def _head(c, tip, angle_deg, size, color):
    """A filled arrow head with its tip at `tip`, pointing along angle_deg (0 = right,
    90 = up on screen)."""
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), -math.sin(a)
    px, py = -dy, dx
    base = (tip[0] - dx * size, tip[1] - dy * size)
    pts = [tip, (base[0] + px * size * 0.62, base[1] + py * size * 0.62),
           (base[0] - px * size * 0.62, base[1] - py * size * 0.62)]
    c.poly(pts, color=color, fill=color, w=0)


def _arrow_out(c, start, end, w=None, head=14):
    """The export verb: an accent arrow from start to end, head at end."""
    color = c.t['accent']
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    stop = (end[0] - ux * head * 0.8, end[1] - uy * head * 0.8)
    c.line([start, stop], color=color, w=w)
    _head(c, end, math.degrees(math.atan2(-dy, dx)), head, color)


def _page(c, x0, y0, x1, y1, fold=12, w=None, fill=None):
    """A document outline with a folded top-right corner."""
    pts = [(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)]
    c.poly(pts, w=w, fill=fill)
    c.line([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], w=w)


def _play(c, cx, cy, size):
    """The run verb: a solid accent triangle pointing right."""
    color = c.t['accent']
    c.poly([(cx - size * 0.55, cy - size), (cx + size * 0.85, cy), (cx - size * 0.55, cy + size)],
           color=color, fill=color, w=0)


def _clock(c, cx, cy, r, w, fill):
    """The time verb: an accent clock face with its hands at ten past."""
    color = c.t['accent']
    c.circle(cx, cy, r, color=color, w=w, fill=fill)
    c.line([(cx, cy), (cx, cy - r * 0.55)], color=color, w=w)
    c.line([(cx, cy), (cx + r * 0.45, cy + r * 0.12)], color=color, w=w)


def _clock_solid(c, cx, cy, r, w):
    """The small clock: a solid accent face with paper hands (an outline closes up at
    32 px)."""
    c.disc(cx, cy, r, c.t['accent'])
    c.line([(cx, cy), (cx, cy - r * 0.6)], color=c.t['paper'], w=w)
    c.line([(cx, cy), (cx + r * 0.5, cy + r * 0.15)], color=c.t['paper'], w=w)


# ---- Exchange panel -------------------------------------------------------------------------


def ic_geometry_exporter(c):
    """A box drawn as its triangles (one face split by its diagonal) and the export
    arrow leaving it."""
    if c.small:
        c.poly([(6, 40), (24, 22), (60, 22), (60, 58), (42, 76), (6, 76)], w=11)
        c.line([(6, 40), (42, 40), (60, 22)], w=11)
        c.line([(42, 40), (42, 76)], w=11)
        _arrow_out(c, (58, 92), (92, 58), w=12, head=22)
        return
    c.poly([(8, 38), (24, 22), (62, 22), (62, 60), (46, 76), (8, 76)])
    c.line([(8, 38), (46, 38), (62, 22)])
    c.line([(46, 38), (46, 76)])
    c.line([(8, 76), (46, 38)], w=5)
    _arrow_out(c, (62, 88), (92, 58), w=8, head=17)


def ic_ifc_exporter(c):
    """A building with its storeys drawn as floor lines (what IFC carries that raw
    geometry does not), and the export arrow."""
    if c.small:
        c.poly([(6, 86), (6, 30), (34, 12), (62, 30), (62, 86)], w=11)
        c.line([(6, 58), (62, 58)], w=10)
        _arrow_out(c, (62, 92), (92, 62), w=12, head=22)
        return
    c.poly([(8, 86), (8, 32), (34, 12), (60, 32), (60, 86)])
    c.line([(8, 50), (60, 50)], w=6)
    c.line([(8, 68), (60, 68)], w=6)
    _arrow_out(c, (64, 88), (92, 60), w=8, head=17)


# ---- Reports panel --------------------------------------------------------------------------


def ic_report_templates(c):
    """A template page (blocks waiting for data) and the accent play mark: run it."""
    if c.small:
        _page(c, 8, 6, 58, 84, fold=16, w=11)
        c.line([(20, 34), (44, 34)], w=10)
        c.line([(20, 54), (36, 54)], w=10)
        _play(c, 72, 70, 20)
        return
    _page(c, 12, 8, 60, 86, fold=12)
    c.rrect(22, 28, 50, 44, rad=3, w=5)
    c.line([(22, 56), (50, 56)], w=5)
    c.line([(22, 68), (40, 68)], w=5)
    _play(c, 74, 70, 17)


def ic_scheduled_reports(c):
    """A calendar page and the accent clock: templates that run on a timetable."""
    if c.small:
        c.rrect(6, 14, 64, 78, rad=6, w=11)
        c.line([(6, 34), (64, 34)], w=11)
        c.line([(22, 6), (22, 20)], w=11)
        c.line([(48, 6), (48, 20)], w=11)
        c.disc(70, 70, 27, c.t['paper'])
        _clock_solid(c, 70, 70, 23, 7)
        return
    c.rrect(8, 16, 66, 80, rad=6)
    c.line([(8, 34), (66, 34)], w=6)
    c.line([(24, 8), (24, 22)])
    c.line([(50, 8), (50, 22)])
    for x in (22, 37):
        for y in (48, 64):
            c.disc(x, y, 4, c.t['ink'])
    _clock(c, 70, 68, 19, 7, c.t['paper'])


ICONS = {
    PROJECT + 'Geometry_Exporter.pushbutton': ic_geometry_exporter,
    PROJECT + 'IFC_Exporter.pushbutton': ic_ifc_exporter,
    DEV + 'Report_Templates.pushbutton': ic_report_templates,
    DEV + 'Scheduled_Reports.pushbutton': ic_scheduled_reports,
}
TOGGLES = {}
DOCKPANE_ON = {}

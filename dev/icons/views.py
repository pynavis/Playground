# -*- coding: utf-8 -*-
"""Glyphs for the Viewpoints, Capture and Navigate panels (tab Views).

Family marks, so each panel reads as one set:
  * Viewpoints: the pyNavis viewpoints eye (pn.eye) is the saved view; the accent
    says what happens to it: many made (a plus), read from a table, sent out
    (an arrow), kept in step (two arrows chasing), or where you stand (a compass).
  * Capture: the picture (a frame with a hill) is an image; the accent hill is the
    one being made, on a page for the PDF.
  * Navigate: floors are stacked horizontal slabs; the accent is the cutting plane
    or the direction the cut moves. The spotter's mark is a cross, the sheet a
    tilted plan; clearing them is an accent stroke across the ink mark.
"""
import math

import make_icons as pn  # noqa: F401  (pyNavis' generator: Ctx and the shared marks)

VP = 'Views.tab/Viewpoints.panel/'
CAP = 'Views.tab/Capture.panel/'
NAV = 'Views.tab/Navigate.panel/'


# ---- shared helpers ------------------------------------------------------------------


def _eye(c, cx=48, cy=48, rx=38, ry=34, w=None, pupil=True):
    """The viewpoints eye at any place and size: two arcs and an ink pupil."""
    S = pn.S
    ww = int((w or (13 if c.small else 8)) * S)
    box = [(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S]
    c.d.arc(box, start=200, end=340, fill=c.t['ink'], width=ww)
    c.d.arc(box, start=20, end=160, fill=c.t['ink'], width=ww)
    if pupil:
        c.disc(cx, cy, ry * 0.3, c.t['ink'])


def _arrow(c, x0, y0, x1, y1, w, head, color=None):
    """A straight accent arrow from (x0, y0) to (x1, y1)."""
    col = color or c.t['accent']
    length = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    bx, by = x1 - ux * head * 0.9, y1 - uy * head * 0.9
    c.line([(x0, y0), (bx, by)], color=col, w=w)
    nx, ny = -uy, ux
    c.poly([(x1, y1), (bx + nx * head * 0.6, by + ny * head * 0.6), (bx - nx * head * 0.6, by - ny * head * 0.6)],
           color=col, fill=col, w=0)


def _picture(c, x0, y0, x1, y1, w, hill=None, rad=6):
    """A picture frame with a hill line inside; hill colour None = ink."""
    c.rrect(x0, y0, x1, y1, rad=rad, w=w)
    col = hill or c.t['ink']
    h = y1 - y0
    wdt = x1 - x0
    pts = [(x0 + wdt * 0.16, y1 - h * 0.22), (x0 + wdt * 0.42, y0 + h * 0.42),
           (x0 + wdt * 0.6, y0 + h * 0.62), (x0 + wdt * 0.72, y0 + h * 0.5), (x1 - wdt * 0.16, y1 - h * 0.22)]
    c.line(pts, color=col, w=w)


def _floors(c, ys, x0=14, x1=82, w=None):
    """Stacked floor slabs: horizontal ink lines."""
    for y in ys:
        c.line([(x0, y), (x1, y)], w=w)


def _cross(c, cx, cy, arm, w, color=None):
    c.line([(cx - arm, cy), (cx + arm, cy)], color=color, w=w)
    c.line([(cx, cy - arm), (cx, cy + arm)], color=color, w=w)


def _sheet(c, color=None, w=None, fill=None):
    """A plan sheet lying flat, seen in perspective: a parallelogram."""
    pts = [(24, 28), (90, 28), (72, 72), (6, 72)]
    c.poly(pts, color=color, w=w, fill=fill)
    return pts


# ---- Viewpoints panel ---------------------------------------------------------------------


def ic_batch_viewpoints(c):
    """The eye with an accent plus: many saved views made at once."""
    if c.small:
        _eye(c, cx=40, cy=40, rx=36, ry=30)
        pn.plus(c, 74, 74, 18, 14)
    else:
        _eye(c, cx=42, cy=42, rx=36, ry=30)
        pn.plus(c, 76, 76, 15, 9)


def ic_viewpoints_from_excel(c):
    """A table (rows and a header) in ink, the accent eye reading it in."""
    if c.small:
        c.rrect(4, 40, 58, 92, rad=7, w=12)
        c.line([(4, 58), (58, 58)], w=12)
        c.line([(4, 75), (58, 75)], w=12)
        c.d.arc([46 * pn.S, 6 * pn.S, 94 * pn.S, 46 * pn.S], start=200, end=340, fill=c.t['ink'], width=12 * pn.S)
        c.d.arc([46 * pn.S, 6 * pn.S, 94 * pn.S, 46 * pn.S], start=20, end=160, fill=c.t['ink'], width=12 * pn.S)
        c.disc(70, 26, 9, c.t['accent'])
    else:
        c.rrect(8, 38, 62, 88, rad=5, w=7)
        c.line([(8, 54), (62, 54)], w=7)
        c.line([(8, 71), (62, 71)], w=7)
        c.line([(30, 38), (30, 88)], w=7)
        _eye(c, cx=66, cy=26, rx=24, ry=18, w=7, pupil=False)
        c.disc(66, 26, 7, c.t['accent'])


def ic_export_viewpoints(c):
    """The eye with an accent arrow leaving it: views sent out to a file."""
    if c.small:
        _eye(c, cx=38, cy=50, rx=34, ry=28)
        _arrow(c, 52, 44, 90, 8, 14, 26)
    else:
        _eye(c, cx=40, cy=52, rx=34, ry=28)
        _arrow(c, 56, 40, 88, 8, 8, 18)


def ic_viewpoint_sync(c):
    """Two view frames with accent arrows chasing between them: the same folders
    in both files."""
    if c.small:
        c.rrect(4, 8, 44, 44, rad=7, w=12)
        c.rrect(52, 52, 92, 88, rad=7, w=12)
        _arrow(c, 52, 26, 78, 26, 12, 20)
        c.line([(78, 26), (78, 40)], color=c.t['accent'], w=12)
        _arrow(c, 44, 70, 18, 70, 12, 20)
        c.line([(18, 70), (18, 56)], color=c.t['accent'], w=12)
    else:
        c.rrect(8, 10, 44, 42, rad=5, w=7)
        c.rrect(52, 54, 88, 86, rad=5, w=7)
        c.line([(52, 26), (72, 26)], color=c.t['accent'], w=7)
        _arrow(c, 72, 26, 72, 46, 7, 14)
        c.line([(44, 70), (24, 70)], color=c.t['accent'], w=7)
        _arrow(c, 24, 70, 24, 50, 7, 14)


def ic_where_am_i(c):
    """A compass: the ink ring and its north tick, the accent needle pointing
    the way the camera looks."""
    if c.small:
        c.circle(48, 48, 40, w=12)
        c.poly([(70, 18), (58, 58), (26, 78), (38, 38)], color=c.t['accent'], fill=c.t['accent'], w=0)
    else:
        c.circle(48, 48, 38, w=7)
        for angle in (90, 180, 270):
            a = math.radians(angle)
            c.line([(48 + math.sin(a) * 30, 48 - math.cos(a) * 30), (48 + math.sin(a) * 38, 48 - math.cos(a) * 38)],
                   w=6)
        tip = (66, 22)
        tail = (30, 74)
        c.poly([tip, (54, 52), tail, (42, 44)], color=c.t['accent'], fill=c.t['accent'], w=0)
        c.disc(48, 48, 5, c.t['paper'])


# ---- Capture panel --------------------------------------------------------------------------


def ic_viewpoints_to_images(c):
    """The eye over a picture whose accent hill is the image being made."""
    if c.small:
        _picture(c, 6, 14, 90, 82, 13, hill=c.t['accent'], rad=8)
    else:
        _picture(c, 12, 38, 84, 86, 7, hill=c.t['accent'], rad=5)
        _eye(c, cx=48, cy=18, rx=24, ry=14, w=7, pupil=False)
        c.disc(48, 18, 5, c.t['ink'])


def ic_batch_image_export(c):
    """Four pictures in a grid, one with the accent hill: many images at once."""
    if c.small:
        for x, y in ((4, 6), (52, 6), (4, 52)):
            c.rrect(x, y, x + 40, y + 38, rad=6, w=12)
        _picture(c, 52, 52, 92, 90, 12, hill=c.t['accent'], rad=6)
    else:
        for x, y in ((8, 8), (52, 8), (8, 52)):
            _picture(c, x, y, x + 36, y + 34, 6, rad=4)
        _picture(c, 52, 52, 88, 86, 7, hill=c.t['accent'], rad=4)


def ic_batch_pdf(c):
    """A page with a turned corner holding an accent picture and text lines."""
    if c.small:
        c.poly([(14, 6), (62, 6), (84, 28), (84, 90), (14, 90)], w=12)
        c.rrect(26, 34, 72, 64, rad=4, w=0, fill=c.t['accent'])
        c.line([(28, 78), (70, 78)], w=12)
    else:
        c.poly([(18, 8), (60, 8), (78, 26), (78, 88), (18, 88)], w=7)
        c.line([(60, 8), (60, 26), (78, 26)], w=6)
        c.rrect(28, 34, 68, 62, rad=3, w=0, fill=c.t['accent'])
        c.line([(28, 72), (68, 72)], w=6)
        c.line([(28, 80), (54, 80)], w=6)


# ---- Navigate panel ---------------------------------------------------------------------------


def ic_level_sectioner(c):
    """Three floors in ink cut by the accent section plane."""
    if c.small:
        _floors(c, (16, 48, 80), 6, 90, 12)
        c.poly([(18, 30), (92, 30), (78, 40), (4, 40)], color=c.t['accent'], fill=c.t['accent'], w=0)
    else:
        _floors(c, (16, 46, 76), 12, 84, 7)
        c.poly([(24, 27), (90, 27), (74, 37), (8, 37)], color=c.t['accent'], fill=c.t['accent'], w=0)


def ic_level_up(c):
    """Floors with the accent arrow lifting the cut a level."""
    if c.small:
        _floors(c, (30, 60, 90), 4, 56, 12)
        c.arrow_v(78, 90, 6, w=14, head=26)
    else:
        _floors(c, (32, 58, 84), 8, 58, 7)
        c.arrow_v(78, 88, 10, w=8, head=18)


def ic_level_down(c):
    """Floors with the accent arrow dropping the cut a level."""
    if c.small:
        _floors(c, (6, 36, 66), 4, 56, 12)
        c.arrow_v(78, 6, 90, w=14, head=26)
    else:
        _floors(c, (12, 38, 64), 8, 58, 7)
        c.arrow_v(78, 8, 86, w=8, head=18)


def _two_views(c, w):
    c.rrect(4, 24, 42, 66, rad=6, w=w)
    c.rrect(54, 24, 92, 66, rad=6, w=w)


def ic_camera_sync_off(c):
    """Two views side by side, linked by an ink double arrow: sync is off."""
    w = 12 if c.small else 7
    _two_views(c, w)
    col = c.t['ink']
    _arrow(c, 32, 82, 64, 82, w, 18 if c.small else 14, color=col)
    _arrow(c, 64, 82, 32, 82, w, 18 if c.small else 14, color=col)


def ic_camera_sync_on(c):
    """The same views, the link in accent and a dot in each: one camera in both."""
    w = 12 if c.small else 7
    _two_views(c, w)
    _arrow(c, 32, 82, 64, 82, w, 18 if c.small else 14)
    _arrow(c, 64, 82, 32, 82, w, 18 if c.small else 14)
    c.disc(23, 45, 7 if c.small else 6, c.t['accent'])
    c.disc(73, 45, 7 if c.small else 6, c.t['accent'])


def ic_coordinate_spotter(c):
    """An ink marker already dropped and the accent one being dropped, each with
    its label tag hanging off it."""
    if c.small:
        _cross(c, 22, 30, 18, 13, color=c.t['accent'])
        c.rrect(44, 44, 92, 74, rad=6, w=12)
        c.line([(30, 38), (44, 50)], w=12)
    else:
        _cross(c, 18, 76, 10, 7)
        c.rrect(34, 72, 66, 90, rad=4, w=6)
        _cross(c, 26, 26, 14, 8, color=c.t['accent'])
        c.rrect(46, 34, 88, 56, rad=5, w=7)
        c.line([(32, 32), (46, 40)], w=6)


def ic_clear_spots(c):
    """A marker struck through by the accent stroke."""
    if c.small:
        _cross(c, 42, 42, 32, 13)
        c.line([(52, 88), (90, 50)], color=c.t['accent'], w=14)
    else:
        _cross(c, 40, 40, 26, 8)
        c.line([(52, 86), (88, 50)], color=c.t['accent'], w=9)


def ic_sheet_overlay(c):
    """A plan sheet laid flat in accent with ink plan lines on it."""
    if c.small:
        c.poly([(26, 20), (92, 20), (70, 76), (4, 76)], color=c.t['accent'], w=13)
        c.line([(48, 20), (36, 76)], w=12)
    else:
        _sheet(c, color=c.t['accent'], w=7)
        c.line([(46, 28), (34, 72)], w=6)
        c.line([(16, 50), (80, 50)], w=6)
        c.line([(66, 28), (54, 50)], w=6)


def ic_clear_sheet(c):
    """The sheet in ink with the accent stroke taking it away."""
    if c.small:
        c.poly([(24, 16), (90, 16), (72, 56), (6, 56)], w=12)
        c.line([(52, 90), (90, 60)], color=c.t['accent'], w=14)
    else:
        c.poly([(24, 18), (88, 18), (70, 56), (6, 56)], w=7)
        c.line([(30, 18), (22, 56)], w=6)
        c.line([(54, 86), (88, 60)], color=c.t['accent'], w=9)


ICONS = {
    VP + 'Batch_Viewpoints.pushbutton': ic_batch_viewpoints,
    VP + 'Viewpoints_from_Excel.pushbutton': ic_viewpoints_from_excel,
    VP + 'Export_Viewpoints.pushbutton': ic_export_viewpoints,
    VP + 'Viewpoint_Sync.pushbutton': ic_viewpoint_sync,
    VP + 'Where_Am_I.pushbutton': ic_where_am_i,
    CAP + 'Viewpoints_to_Images.pushbutton': ic_viewpoints_to_images,
    CAP + 'Batch_Image_Export.pushbutton': ic_batch_image_export,
    CAP + 'Batch_PDF.pushbutton': ic_batch_pdf,
    NAV + 'Level_Sectioner.pushbutton': ic_level_sectioner,
    NAV + 'Level_Up.nobutton': ic_level_up,
    NAV + 'Level_Down.nobutton': ic_level_down,
    NAV + 'Spotter.stack/Coordinate_Spotter.pushbutton': ic_coordinate_spotter,
    NAV + 'Spotter.stack/Clear_Spots.pushbutton': ic_clear_spots,
    NAV + 'Sheet.stack/Sheet_Overlay.pushbutton': ic_sheet_overlay,
    NAV + 'Sheet.stack/Clear_Sheet.pushbutton': ic_clear_sheet,
}

TOGGLES = {
    NAV + 'Camera_Sync.toggle': (ic_camera_sync_off, ic_camera_sync_on),
}

DOCKPANE_ON = {}

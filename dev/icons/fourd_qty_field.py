# -*- coding: utf-8 -*-
"""Glyphs for the 4D, Quantities and Field panels (Project tab).

Family marks, so a panel reads as one set:
  * 4D: three staggered schedule bars in ink (the TimeLiner schedule); the accent is
    what the tool does with it.
  * Quantities: an accent sum sign; the ink is what gets measured.
  * Field: things you carry on site in ink (a code, a camera, photos, a clipboard).
"""
import make_icons as pn


def bars(c, x0=12, y0=18, gap=22, w=None, rows=((0, 40), (18, 58), (34, 74))):
    """The schedule mark: staggered horizontal bars (start, end) on rows."""
    ww = w or (13 if c.small else 8)
    for index, (start, end) in enumerate(rows):
        y = y0 + index * gap
        c.line([(x0 + start, y), (x0 + end, y)], w=ww)


def sigma(c, x0, y0, x1, y1, w=None, color=None):
    """An accent sum sign inside the box."""
    col = color or c.t['accent']
    mid = (y0 + y1) / 2.0
    c.line([(x1, y0), (x0, y0), (x0 + (x1 - x0) * 0.55, mid), (x0, y1), (x1, y1)], color=col, w=w)


def cube(c, cx, cy, s, w=None, color=None):
    """An isometric box outline: the model item."""
    col = color or c.t['ink']
    h = s * 0.5
    top = [(cx, cy - s), (cx + s, cy - h), (cx, cy), (cx - s, cy - h)]
    c.poly(top, color=col, w=w)
    c.line([(cx - s, cy - h), (cx - s, cy + h), (cx, cy + s), (cx + s, cy + h), (cx + s, cy - h)], color=col, w=w)
    c.line([(cx, cy), (cx, cy + s)], color=col, w=w)


# ---- 4D -------------------------------------------------------------------------------------------


def ic_timeliner_from_excel(c):
    """A sheet's rows in ink with the accent schedule bars laid on them: tasks built
    from the rows."""
    if c.small:
        c.rrect(6, 6, 90, 90, rad=8, w=11)
        c.line([(30, 32), (60, 32)], color=c.t['accent'], w=14)
        c.line([(44, 62), (78, 62)], color=c.t['accent'], w=14)
    else:
        c.rrect(8, 10, 88, 86, rad=6, w=7)
        for y in (34, 54):
            c.line([(8, y), (88, y)], w=5)
        c.line([(26, 10), (26, 86)], w=5)
        c.line([(34, 22), (56, 22)], color=c.t['accent'], w=8)
        c.line([(46, 44), (70, 44)], color=c.t['accent'], w=8)
        c.line([(60, 70), (80, 70)], color=c.t['accent'], w=8)


def ic_auto_attach(c):
    """A schedule bar in ink, a model box in ink, the accent link joining them."""
    if c.small:
        c.line([(8, 14), (56, 14)], w=14)
        c.rrect(48, 48, 90, 90, rad=8, w=12)
        c.line([(26, 14), (26, 69), (42, 69)], color=c.t['accent'], w=13)
    else:
        c.line([(10, 16), (50, 16)], w=8)
        c.line([(10, 34), (34, 34)], w=8)
        cube(c, 64, 62, 22, w=7)
        c.line([(30, 16), (30, 56), (42, 63)], color=c.t['accent'], w=7)
        c.disc(30, 16, 7, c.t['accent'])
        c.disc(44, 64, 6, c.t['accent'])


def ic_progress_painter(c):
    """A box filling with accent paint up to its progress mark."""
    if c.small:
        c.rrect(10, 8, 86, 88, rad=8, w=12)
        c.rrect(10, 46, 86, 88, rad=8, w=0, fill=c.t['accent'])
    else:
        c.rrect(14, 10, 82, 86, rad=6, w=7)
        c.rrect(14, 46, 82, 86, rad=6, w=0, fill=c.t['accent'])
        for y in (28, 46, 64):
            c.line([(86, y), (94, y)], w=5)


def ic_movie_maker(c):
    """A film frame in ink with the accent play mark: the sequence as a movie."""
    if c.small:
        c.rrect(6, 14, 90, 82, rad=8, w=12)
        c.poly([(36, 30), (36, 66), (66, 48)], color=c.t['accent'], fill=c.t['accent'], w=0)
    else:
        c.rrect(8, 14, 88, 82, rad=6, w=7)
        for x in (20, 36, 52, 68, 84):
            c.disc(x - 4, 22, 3, c.t['ink'])
            c.disc(x - 4, 74, 3, c.t['ink'])
        c.poly([(38, 34), (38, 62), (62, 48)], color=c.t['accent'], fill=c.t['accent'], w=0)


def ic_timeliner_export(c):
    """The schedule bars with the accent export arrow below."""
    if c.small:
        c.line([(8, 14), (48, 14)], w=14)
        c.line([(30, 38), (82, 38)], w=14)
        c.arrow_v(48, 56, 92, color=c.t['accent'], w=14, head=22)
    else:
        bars(c, x0=8, y0=12, gap=16, w=7)
        c.arrow_v(48, 62, 90, color=c.t['accent'], w=8, head=16)


def ic_schedule_health(c):
    """The schedule bars crossed by an accent pulse: the schedule checked."""
    if c.small:
        c.line([(8, 10), (50, 10)], w=13)
        c.line([(44, 88), (88, 88)], w=13)
        c.line([(6, 50), (28, 50), (40, 28), (56, 72), (68, 50), (90, 50)], color=c.t['accent'], w=11)
    else:
        bars(c, x0=8, y0=12, gap=72, w=7, rows=((0, 40), (36, 80)))
        c.line([(6, 48), (28, 48), (38, 28), (52, 68), (62, 48), (90, 48)], color=c.t['accent'], w=7)


# ---- Quantities -------------------------------------------------------------------------------------


def ic_quick_takeoff(c):
    """Stacked items in ink, the accent sum beside them."""
    if c.small:
        for y in (14, 44, 74):
            c.rrect(6, y - 10, 42, y + 10, rad=4, w=11)
        sigma(c, 56, 12, 90, 84, w=12)
    else:
        for y in (20, 46, 72):
            c.rrect(8, y - 10, 42, y + 10, rad=4, w=6)
        sigma(c, 54, 16, 88, 80, w=8)


def ic_zone_takeoff(c):
    """A plan cut into zones in ink, one zone summed in accent."""
    if c.small:
        c.rrect(6, 6, 90, 90, rad=8, w=11)
        c.line([(48, 6), (48, 90)], w=11)
        c.line([(6, 48), (90, 48)], w=11)
        c.rrect(48, 48, 90, 90, rad=8, w=0, fill=c.t['accent'])
    else:
        c.rrect(8, 8, 88, 88, rad=6, w=6)
        c.line([(48, 8), (48, 88)], w=6)
        c.line([(8, 48), (88, 48)], w=6)
        c.rrect(48, 48, 88, 88, rad=6, w=0, fill=c.t['accent'])
        sigma(c, 58, 58, 78, 78, w=5, color=c.t['paper'])


def ic_takeoff_templates(c):
    """A stack of saved cards in ink, the accent sum on the front card."""
    if c.small:
        c.line([(28, 22), (28, 6), (90, 6), (90, 66), (74, 66)], w=11)
        c.rrect(6, 26, 70, 90, rad=8, w=11)
        sigma(c, 24, 42, 52, 74, w=10)
    else:
        c.line([(30, 24), (30, 10), (86, 10), (86, 64), (72, 64)], w=6)
        c.rrect(10, 28, 68, 86, rad=6, w=6)
        sigma(c, 26, 42, 52, 72, w=7)


def ic_cog_calculator(c):
    """An L-shaped part in ink with the accent centre-of-gravity symbol."""
    col = c.t['accent']
    if c.small:
        c.poly([(6, 6), (40, 6), (40, 52), (90, 52), (90, 90), (6, 90)], w=11)
        cx, cy, r = 44, 71, 15
    else:
        c.poly([(8, 8), (40, 8), (40, 54), (88, 54), (88, 88), (8, 88)], w=6)
        cx, cy, r = 42, 71, 13
    c.circle(cx, cy, r, color=col, w=5 if not c.small else 7)
    box = [(cx - r) * pn.S, (cy - r) * pn.S, (cx + r) * pn.S, (cy + r) * pn.S]
    c.d.pieslice(box, start=270, end=360, fill=col)
    c.d.pieslice(box, start=90, end=180, fill=col)


# ---- Field ----------------------------------------------------------------------------------------


def _finder(c, x, y, s, w):
    c.rrect(x, y, x + s, y + s, rad=3, w=w)
    inner = s * 0.32
    c.rrect(x + inner, y + inner, x + s - inner, y + s - inner, rad=1, w=0, fill=c.t['ink'])


def ic_qr_tagger(c):
    """Three finder squares in ink, the accent data between them."""
    col = c.t['accent']
    if c.small:
        _finder(c, 6, 6, 36, 10)
        _finder(c, 54, 6, 36, 10)
        _finder(c, 6, 54, 36, 10)
        for x, y in ((56, 56), (76, 56), (66, 70), (56, 82), (80, 80)):
            c.rrect(x, y, x + 12, y + 12, rad=2, w=0, fill=col)
    else:
        _finder(c, 8, 8, 30, 6)
        _finder(c, 58, 8, 30, 6)
        _finder(c, 8, 58, 30, 6)
        for x, y in ((58, 58), (72, 58), (65, 68), (58, 78), (78, 78), (44, 44), (44, 20), (20, 44)):
            c.rrect(x, y, x + 9, y + 9, rad=2, w=0, fill=col)


def _camera(c, x0, y0, x1, y1, w, lens):
    c.rrect(x0, y0, x1, y1, rad=6, w=w)
    c.line([(x0 + 10, y0), (x0 + 16, y0 - 7), (x0 + 30, y0 - 7), (x0 + 36, y0)], w=w)
    c.circle((x0 + x1) / 2.0, (y0 + y1) / 2.0 + 2, lens, w=w)


def ic_photo_pins(c):
    """A camera in ink, the accent map pin where the photo belongs."""
    if c.small:
        _camera(c, 6, 46, 72, 90, 10, 11)
        pn._pin(c, 26, 18, 52)
        return
    _camera(c, 8, 48, 70, 88, 6, 10)
    pn._pin(c, 24, 15, 50)


def _thumb(c, x0, y0, x1, y1, w, color=None):
    c.rrect(x0, y0, x1, y1, rad=4, w=w, color=color)
    c.line([(x0 + 6, y1 - 7), (x0 + (x1 - x0) * 0.42, y0 + (y1 - y0) * 0.45), (x1 - 6, y1 - 7)],
           w=max(4, w - 2), color=color)


def ic_photo_browser(c):
    """Four photo thumbnails in ink, the selected one in accent."""
    if c.small:
        for x0, y0 in ((6, 6), (52, 6), (6, 52)):
            c.rrect(x0, y0, x0 + 38, y0 + 38, rad=6, w=10)
        c.rrect(52, 52, 90, 90, rad=6, w=0, fill=c.t['accent'])
    else:
        _thumb(c, 8, 10, 44, 42, 6)
        _thumb(c, 52, 10, 88, 42, 6)
        _thumb(c, 8, 52, 44, 84, 6)
        _thumb(c, 52, 52, 88, 84, 7, color=c.t['accent'])


def ic_field_checklists(c):
    """A clipboard in ink with accent ticks on its lines."""
    col = c.t['accent']
    if c.small:
        c.rrect(10, 10, 86, 90, rad=8, w=11)
        c.rrect(32, 4, 64, 18, rad=4, w=0, fill=c.t['ink'])
        c.line([(24, 46), (36, 58), (58, 34)], color=col, w=12)
        c.line([(24, 74), (72, 74)], w=11)
    else:
        c.rrect(14, 12, 82, 88, rad=6, w=6)
        c.rrect(34, 6, 62, 18, rad=3, w=0, fill=c.t['ink'])
        c.line([(24, 38), (30, 44), (40, 32)], color=col, w=6)
        c.line([(48, 38), (72, 38)], w=5)
        c.line([(24, 60), (30, 66), (40, 54)], color=col, w=6)
        c.line([(48, 60), (72, 60)], w=5)
        c.line([(48, 78), (66, 78)], w=5)


BASE = 'Project.tab/'
ICONS = {
    BASE + '4D.panel/TimeLiner_from_Excel.pushbutton': ic_timeliner_from_excel,
    BASE + '4D.panel/Auto_Attach.pushbutton': ic_auto_attach,
    BASE + '4D.panel/Progress_Painter.pushbutton': ic_progress_painter,
    BASE + '4D.panel/Movie_Maker.pushbutton': ic_movie_maker,
    BASE + '4D.panel/Schedule_Tools.stack/TimeLiner_Export.pushbutton': ic_timeliner_export,
    BASE + '4D.panel/Schedule_Tools.stack/Schedule_Health.pushbutton': ic_schedule_health,
    BASE + 'Quantities.panel/Quick_Takeoff.pushbutton': ic_quick_takeoff,
    BASE + 'Quantities.panel/Zone_Takeoff.pushbutton': ic_zone_takeoff,
    BASE + 'Quantities.panel/Takeoff_Templates.pushbutton': ic_takeoff_templates,
    BASE + 'Quantities.panel/COG_Calculator.pushbutton': ic_cog_calculator,
    BASE + 'Field.panel/QR_Tagger.pushbutton': ic_qr_tagger,
    BASE + 'Field.panel/Photo_Pins.pushbutton': ic_photo_pins,
    BASE + 'Field.panel/Photo_Browser.pushbutton': ic_photo_browser,
    BASE + 'Field.panel/Field_Checklists.pushbutton': ic_field_checklists,
}
TOGGLES = {}
DOCKPANE_ON = {}

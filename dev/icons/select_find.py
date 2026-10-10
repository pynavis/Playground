# -*- coding: utf-8 -*-
"""Glyphs for the Select and Find panels (Model tab).

Family marks, so the two panels read as two families:
  * Select: the ELEMENT (a rounded square) and the PICK PATH (discs joined in order).
  * Find:   the LENS (a magnifier) for searching, the PAGE for set files.
Ink draws the thing, accent draws what the tool does to it. Stack rows and menu items
show the 32 px art, so every small drawing is its own simplified glyph with two ideas
at most.
"""
import make_icons as pn  # noqa: F401  (pyNavis' generator: Ctx helpers and shared marks)

S = pn.S


def _blend(a, b, t):
    """Colour t of the way from a to b (RGBA tuples)."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(4))


def _pie(c, cx, cy, r, start, end, color):
    c.d.pieslice([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S],
                 start=start, end=end, fill=color)


def _arrow(c, x0, x1, y, w, head, color=None):
    """A horizontal accent arrow from x0 to x1 (head at x1)."""
    col = color or c.t['accent']
    d = 1 if x1 > x0 else -1
    end = x1 - d * head * 0.9
    c.line([(x0, y), (end, y)], color=col, w=w)
    c.poly([(end, y - head * 0.62), (end, y + head * 0.62), (x1, y)], color=col, fill=col, w=0)


def _lens(c, cx, cy, r, w, handle, color=None, hw=None):
    """The magnifier: a ring and a handle to the lower right."""
    col = color or c.t['ink']
    c.circle(cx, cy, r, color=col, w=w)
    k = 0.7071
    x0, y0 = cx + r * k + w * 0.35, cy + r * k + w * 0.35
    c.line([(x0, y0), (x0 + handle, y0 + handle)], color=col, w=hw or w + 2)


def _page(c, x0, y0, x1, y1, w, fold):
    """A document with a folded top-right corner."""
    c.poly([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)], w=w)
    c.line([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], w=w)


def _path(c, pts, r, w, discs, line=None):
    """The pick path: a line through the points in order, a disc on each (discs: one
    colour per point)."""
    c.line(pts, color=line or c.t['ink'], w=w)
    for (x, y), col in zip(pts, discs):
        c.disc(x, y, r, col)


# ---- Select panel ------------------------------------------------------------------


def ic_select_similar(c):
    """The reference element in ink; the two like it the tool finds, in accent."""
    if c.small:
        c.rrect(6, 30, 42, 66, rad=6, w=12)
        c.rrect(54, 30, 90, 66, rad=6, w=0, fill=c.t['accent'])
    else:
        c.rrect(8, 32, 40, 64, rad=6)
        c.rrect(56, 10, 88, 42, rad=6, w=0, fill=c.t['accent'])
        c.rrect(56, 54, 88, 86, rad=6, w=0, fill=c.t['accent'])


def ic_filter_selection(c):
    """Items in ink falling into the accent funnel that keeps some of them."""
    acc = c.t['accent']
    if c.small:
        for x in (26, 70):
            c.disc(x, 12, 9, c.t['ink'])
        c.poly([(6, 28), (90, 28), (58, 58), (58, 90), (38, 80), (38, 58)], color=acc, fill=acc, w=0)
    else:
        for x in (24, 48, 72):
            c.disc(x, 14, 7, c.t['ink'])
        c.poly([(10, 30), (86, 30), (57, 58), (57, 88), (39, 78), (39, 58)], color=acc, fill=acc, w=0)


def ic_invert(c):
    """A whole in ink with the other half taken in accent: the selection flipped."""
    if c.small:
        c.circle(48, 48, 38, w=12)
        _pie(c, 48, 48, 31, -90, 90, c.t['accent'])
    else:
        c.circle(48, 48, 36, w=8)
        _pie(c, 48, 48, 31, -90, 90, c.t['accent'])


def ic_select_by_file(c):
    """An appended file in ink; its contents taken in accent."""
    if c.small:
        _page(c, 12, 6, 84, 90, 12, 18)
        c.rrect(32, 44, 64, 76, rad=4, w=0, fill=c.t['accent'])
    else:
        _page(c, 18, 8, 78, 88, 7, 18)
        c.rrect(32, 44, 64, 76, rad=4, w=0, fill=c.t['accent'])


def ic_save_as_set(c):
    """The selection gathered in an ink frame, tagged by the accent bookmark."""
    acc = c.t['accent']
    if c.small:
        c.rrect(6, 30, 90, 90, rad=10, w=12)
        c.poly([(54, 4), (84, 4), (84, 50), (69, 38), (54, 50)], color=acc, fill=acc, w=0)
    else:
        c.rrect(8, 28, 88, 88, rad=10)
        c.disc(28, 62, 8, c.t['ink'])
        c.disc(50, 62, 8, c.t['ink'])
        c.poly([(58, 6), (82, 6), (82, 46), (70, 36), (58, 46)], color=acc, fill=acc, w=0)


def ic_back(c):
    if c.small:
        _arrow(c, 86, 8, 48, 15, 36)
    else:
        pn.dots(c, 82, 6)
        _arrow(c, 80, 14, 40, 9, 26)


def ic_forward(c):
    if c.small:
        _arrow(c, 10, 88, 48, 15, 36)
    else:
        pn.dots(c, 82, 6)
        _arrow(c, 16, 82, 40, 9, 26)


def ic_history(c):
    """A clock in ink, its hands in accent: the selections over time."""
    acc = c.t['accent']
    if c.small:
        c.circle(48, 48, 38, w=12)
        c.line([(48, 48), (48, 24)], color=acc, w=13)
        c.line([(48, 48), (66, 60)], color=acc, w=13)
    else:
        c.circle(48, 48, 36, w=8)
        c.line([(48, 48), (48, 24)], color=acc, w=8)
        c.line([(48, 48), (66, 58)], color=acc, w=8)


# The pick path: where the discs sit in the large toggle art and in the menu items.
_TOGGLE_PTS = [(16, 74), (44, 22), (80, 62)]
_SMALL_PTS = [(14, 76), (48, 20), (82, 70)]
_SIDE_PTS = [(12, 72), (32, 22), (52, 60)]          # path on the left, accent mark right


def ic_pick_order_off(c):
    """The pick path in ink with the first disc in accent: picking starts here."""
    ink, acc = c.t['ink'], c.t['accent']
    if c.small:
        _path(c, _SMALL_PTS, 13, 10, [acc, ink, ink])
    else:
        _path(c, _TOGGLE_PTS, 11, 6, [acc, ink, ink])


def ic_pick_order_on(c):
    """Recording: the path punched out of an accent tile (large only)."""
    paper = c.t['paper']
    c.rrect(4, 4, 92, 92, rad=14, w=0, fill=c.t['accent'])
    _path(c, [(18, 72), (44, 24), (78, 62)], 10, 6, [paper, paper, paper], line=paper)


def ic_picked_menu(c):
    """The pick path with the accent menu chevron: what to do with the picks."""
    ink, acc = c.t['ink'], c.t['accent']
    if c.small:
        _path(c, [(12, 58), (36, 14), (62, 46)], 12, 10, [ink, ink, ink])
        c.line([(56, 68), (72, 84), (88, 68)], color=acc, w=13)
    else:
        _path(c, [(14, 58), (38, 18), (64, 46)], 10, 6, [ink, ink, ink])
        c.line([(58, 70), (72, 84), (86, 70)], color=acc, w=9)


def ic_select_picked(c):
    acc = c.t['accent']
    if c.small:
        _path(c, _SMALL_PTS, 15, 10, [acc, acc, acc])
    else:
        _path(c, _TOGGLE_PTS, 12, 6, [acc, acc, acc])


def ic_number_picked(c):
    """The path and an accent number sign: a sequence written onto the picks."""
    ink, acc = c.t['ink'], c.t['accent']
    if c.small:
        _path(c, _SIDE_PTS, 11, 9, [ink, ink, ink])
        for x0, x1 in ((70, 64), (86, 80)):
            c.line([(x0, 26), (x1, 74)], color=acc, w=8)
        c.line([(60, 40), (92, 40)], color=acc, w=8)
        c.line([(58, 60), (90, 60)], color=acc, w=8)
    else:
        _path(c, _SIDE_PTS, 9, 6, [ink, ink, ink])
        for x0, x1 in ((70, 64), (84, 78)):
            c.line([(x0, 30), (x1, 70)], color=acc, w=6)
        c.line([(60, 42), (90, 42)], color=acc, w=6)
        c.line([(58, 58), (88, 58)], color=acc, w=6)


def ic_export_picked(c):
    ink = c.t['ink']
    if c.small:
        _path(c, _SIDE_PTS, 11, 9, [ink, ink, ink])
        _arrow(c, 58, 92, 48, 12, 26)
    else:
        _path(c, _SIDE_PTS, 9, 6, [ink, ink, ink])
        _arrow(c, 60, 90, 48, 8, 20)


def ic_color_picked(c):
    """The picks shaded light to strong along the path."""
    acc = c.t['accent']
    white = (255, 255, 255, 255)            # light to strong on either theme
    shades = [_blend(acc, white, 0.62), _blend(acc, white, 0.32), acc]
    if c.small:
        _path(c, _SMALL_PTS, 16, 10, shades)
    else:
        _path(c, _TOGGLE_PTS, 13, 6, shades)


def ic_clear_picked(c):
    ink, acc = c.t['ink'], c.t['accent']
    if c.small:
        _path(c, _SIDE_PTS, 11, 9, [ink, ink, ink])
        c.line([(62, 30), (90, 62)], color=acc, w=12)
        c.line([(90, 30), (62, 62)], color=acc, w=12)
    else:
        _path(c, _SIDE_PTS, 9, 6, [ink, ink, ink])
        c.line([(64, 32), (88, 60)], color=acc, w=8)
        c.line([(88, 32), (64, 60)], color=acc, w=8)


# ---- Find panel ---------------------------------------------------------------------


def ic_quick_find(c):
    """The accent lens finds; ink speed lines say it does so as you type."""
    acc = c.t['accent']
    if c.small:
        c.line([(4, 30), (22, 30)], w=11)
        c.line([(4, 56), (16, 56)], w=11)
        _lens(c, 52, 42, 24, 12, 22, color=acc, hw=15)
    else:
        c.line([(6, 28), (26, 28)], w=6)
        c.line([(2, 44), (22, 44)], w=6)
        c.line([(6, 60), (26, 60)], w=6)
        _lens(c, 54, 42, 24, 9, 22, color=acc, hw=11)


def ic_search_set_wizard(c):
    """A search (ink lens) built for you (accent sparkle)."""
    if c.small:
        _lens(c, 38, 52, 24, 12, 20, hw=14)
        pn.sparkle(c, 74, 20, 18)
    else:
        _lens(c, 38, 52, 24, 8, 22, hw=10)
        pn.sparkle(c, 74, 22, 16)


def ic_batch_sets(c):
    """One search (ink lens) fanning out into a set per value (accent bars)."""
    acc = c.t['accent']
    if c.small:
        _lens(c, 26, 38, 18, 11, 14, hw=13)
        c.rrect(58, 12, 92, 36, rad=4, w=0, fill=acc)
        c.rrect(58, 54, 92, 78, rad=4, w=0, fill=acc)
    else:
        _lens(c, 26, 40, 16, 7, 14, hw=8)
        for y in (12, 40, 68):
            c.rrect(58, y, 90, y + 18, rad=4, w=0, fill=acc)


def ic_sets_library(c):
    """Sets kept as books on a shelf; the accent one is published to the team."""
    acc = c.t['accent']
    if c.small:
        c.rrect(8, 14, 30, 86, rad=4, w=11)
        c.rrect(38, 14, 60, 86, rad=4, w=11)
        c.rrect(68, 14, 90, 86, rad=4, w=0, fill=acc)
    else:
        c.rrect(10, 20, 28, 84, rad=4, w=6)
        c.rrect(34, 12, 52, 84, rad=4, w=6)
        c.rrect(60, 18, 80, 84, rad=4, w=0, fill=acc)
        c.line([(4, 90), (92, 90)], w=6)


def ic_export_sets(c):
    if c.small:
        _page(c, 6, 6, 56, 90, 11, 14)
        _arrow(c, 36, 94, 56, 13, 28)
    else:
        _page(c, 8, 8, 56, 88, 7, 14)
        _arrow(c, 38, 92, 56, 9, 22)


def ic_import_sets(c):
    if c.small:
        _page(c, 40, 6, 90, 90, 11, 14)
        _arrow(c, 2, 62, 56, 13, 28)
    else:
        _page(c, 40, 8, 88, 88, 7, 14)
        _arrow(c, 4, 64, 56, 9, 22)


def ic_search_in_repair(c):
    """The ink lens with an accent tick in it: the search finds things again."""
    acc = c.t['accent']
    if c.small:
        _lens(c, 40, 40, 30, 12, 22, hw=15)
        c.line([(26, 42), (36, 52), (54, 30)], color=acc, w=11)
    else:
        _lens(c, 40, 40, 28, 8, 24, hw=11)
        c.line([(26, 41), (37, 52), (55, 30)], color=acc, w=8)


_SEL = 'Model.tab/Select.panel/'
_FIND = 'Model.tab/Find.panel/'

ICONS = {
    _SEL + 'Select_Similar.pushbutton': ic_select_similar,
    _SEL + 'Filter_Selection.pushbutton': ic_filter_selection,
    _SEL + 'Quick.stack/Invert.pushbutton': ic_invert,
    _SEL + 'Quick.stack/Select_by_File.pushbutton': ic_select_by_file,
    _SEL + 'Quick.stack/Save_as_Set.pushbutton': ic_save_as_set,
    _SEL + 'History.stack/Back.pushbutton': ic_back,
    _SEL + 'History.stack/Forward.pushbutton': ic_forward,
    _SEL + 'History.stack/History_List.pushbutton': ic_history,
    _SEL + 'Pick_Order_Actions.pulldown': ic_picked_menu,
    _SEL + 'Pick_Order_Actions.pulldown/Select_Picked.pushbutton': ic_select_picked,
    _SEL + 'Pick_Order_Actions.pulldown/Number_Picked.pushbutton': ic_number_picked,
    _SEL + 'Pick_Order_Actions.pulldown/Export_Picked.pushbutton': ic_export_picked,
    _SEL + 'Pick_Order_Actions.pulldown/Color_Picked.pushbutton': ic_color_picked,
    _SEL + 'Pick_Order_Actions.pulldown/Clear_Picked.pushbutton': ic_clear_picked,
    _FIND + 'Quick_Find.pushbutton': ic_quick_find,
    _FIND + 'Search_Set_Wizard.pushbutton': ic_search_set_wizard,
    _FIND + 'Batch_Sets.pushbutton': ic_batch_sets,
    _FIND + 'Sets_Library.pushbutton': ic_sets_library,
    _FIND + 'Set_Exchange.stack/Export_Sets.pushbutton': ic_export_sets,
    _FIND + 'Set_Exchange.stack/Import_Sets.pushbutton': ic_import_sets,
    _FIND + 'Set_Exchange.stack/Search_In_Repair.pushbutton': ic_search_in_repair,
}
TOGGLES = {
    _SEL + 'Pick_Order.toggle': (ic_pick_order_off, ic_pick_order_on),
}
DOCKPANE_ON = {}

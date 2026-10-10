# -*- coding: utf-8 -*-
"""Glyphs for the Inspect and Data panels (G2 inspect_data).

Two family marks carry the set:
  * the property card: a rounded sheet with label and value rows. It is "properties"
    wherever it appears (Properties Plus, Property Exporter, the Write Data tools).
  * the object box: a small isometric box, the element being inspected or labelled.
Ink draws the thing, the accent draws what the tool does to it: the lens that
inspects, the plus that pins, the arrow that exports, the pencil that writes, the
picked row, the tick that passes. No alert red here (it belongs to Model Wipe).
"""
import math

import make_icons as pn          # pyNavis' generator: Ctx helpers and shared marks

PANEL = 'Model.tab/'


# --- shared marks ------------------------------------------------------------------


def _box(c, cx, cy, s, color=None, w=None):
    """A small isometric box centred on (cx, cy), half-width s."""
    h = s * 0.55
    top = [(cx, cy - s), (cx + s, cy - s + h), (cx, cy - s + 2 * h), (cx - s, cy - s + h)]
    c.poly(top, color=color, w=w)
    c.line([(cx - s, cy - s + h), (cx - s, cy + s * 0.6), (cx, cy + s * 0.6 + h),
            (cx + s, cy + s * 0.6), (cx + s, cy - s + h)], color=color, w=w)
    c.line([(cx, cy - s + 2 * h), (cx, cy + s * 0.6 + h)], color=color, w=w)


def _card(c, x0, y0, x1, y1, rows, w=None, value_color=None, label_w=None):
    """The property card: a sheet with label (short) and value (long) rows."""
    c.rrect(x0, y0, x1, y1, rad=7, w=w)
    lw = label_w or (w or 7) * 0.8
    span = (y1 - y0) / float(rows + 1)
    mid = x0 + (x1 - x0) * 0.42
    for i in range(rows):
        y = y0 + span * (i + 1)
        c.line([(x0 + 9, y), (mid - 4, y)], w=lw)
        c.line([(mid + 4, y), (x1 - 9, y)], w=lw, color=value_color)


def _lens(c, cx, cy, r, w, color=None):
    """A magnifier: ring and handle (accent unless told otherwise)."""
    col = color or c.t['accent']
    c.circle(cx, cy, r, w=w, color=col)
    k = r * 0.72
    c.line([(cx + k, cy + k), (cx + r * 1.75, cy + r * 1.75)], color=col, w=w * 1.25)


def _pencil(c, x0, y0, x1, y1, w):
    """The accent pencil: a stroke with a pointed tip at (x1, y1)."""
    col = c.t['accent']
    ang = math.atan2(y1 - y0, x1 - x0)
    tip = w * 1.6
    bx, by = x1 - math.cos(ang) * tip, y1 - math.sin(ang) * tip
    c.line([(x0, y0), (bx, by)], color=col, w=w)
    px, py = -math.sin(ang) * w * 0.62, math.cos(ang) * w * 0.62
    c.poly([(bx + px, by + py), (bx - px, by - py), (x1, y1)], color=col, fill=col, w=0)


def _arrow_h(c, x0, x1, y, w, head, color=None):
    col = color or c.t['accent']
    d = 1 if x1 > x0 else -1
    end = x1 - d * head * 0.9
    c.line([(x0, y), (end, y)], color=col, w=w)
    c.poly([(end, y - head * 0.6), (end, y + head * 0.6), (x1, y)], color=col, fill=col, w=0)


def _grid(c, x0, y0, x1, y1, w, rows=2, cols=1):
    c.rrect(x0, y0, x1, y1, rad=6, w=w)
    for i in range(1, rows + 1):
        y = y0 + (y1 - y0) * i / float(rows + 1)
        c.line([(x0, y), (x1, y)], w=w * 0.75)
    for i in range(1, cols + 1):
        x = x0 + (x1 - x0) * i / float(cols + 1)
        c.line([(x, y0), (x, y1)], w=w * 0.75)


# --- Inspect panel -------------------------------------------------------------------


def ic_what_is_it(c):
    """The object box in ink, the accent lens inspecting it."""
    if c.small:
        _box(c, 36, 40, 26, w=12)
        _lens(c, 64, 64, 15, 11)
    else:
        _box(c, 38, 40, 26, w=7)
        _lens(c, 64, 62, 14, 7)


def ic_properties_plus(c):
    """The property card with the accent plus: more than the native panel."""
    if c.small:
        c.rrect(6, 14, 70, 90, rad=8, w=12)
        c.line([(20, 40), (56, 40)], w=12)
        c.line([(20, 66), (56, 66)], w=12)
        pn.plus(c, 76, 22, 16, 13)
    else:
        _card(c, 8, 18, 70, 88, 3, w=7)
        pn.plus(c, 78, 20, 13, 8)


def _hud_frame(c):
    """The Navisworks window in ink: frame and title bar."""
    c.rrect(6, 10, 90, 86, rad=8, w=7)
    c.line([(6, 26), (90, 26)], w=6)


def ic_selection_hud_off(c):
    """The window with an empty readout in its bottom-left corner: HUD off."""
    if c.small:
        c.rrect(4, 8, 92, 88, rad=8, w=12)
        c.rrect(14, 54, 54, 78, rad=4, w=11)
        return
    _hud_frame(c)
    c.rrect(14, 58, 52, 78, rad=4, w=6)
    c.line([(22, 68), (42, 68)], w=5)


def ic_selection_hud_on(c):
    """The readout filled in accent: the HUD is showing."""
    _hud_frame(c)
    c.rrect(14, 58, 52, 78, rad=4, w=0, fill=c.t['accent'])
    c.line([(22, 68), (42, 68)], w=5, color=c.t['paper'])


def ic_copy_ids(c):
    """The element-id brackets (pyNavis' family mark) holding accent rows: a
    table of ids going to the clipboard."""
    if c.small:
        pn.brackets(c, w=12)
        c.line([(32, 36), (64, 36)], color=c.t['accent'], w=12)
        c.line([(32, 60), (64, 60)], color=c.t['accent'], w=12)
    else:
        pn.brackets(c, w=7)
        for y in (36, 48, 60):
            c.line([(32, y), (64, y)], color=c.t['accent'], w=6)


def ic_open_in_explorer(c):
    """A folder in ink, the accent arrow leaving it: show the file on disk."""
    w = 12 if c.small else 7
    c.rrect(6, 34, 74, 88, rad=6, w=w)
    c.line([(6, 34), (10, 22), (34, 22), (42, 34)], w=w)
    col = c.t['accent']
    if c.small:
        c.line([(52, 52), (86, 18)], color=col, w=12)
        c.poly([(64, 12), (92, 12), (92, 40)], color=col, fill=col, w=0)
    else:
        c.line([(50, 54), (82, 22)], color=col, w=7)
        c.poly([(66, 14), (90, 14), (90, 38)], color=col, fill=col, w=0)


# --- Data panel ----------------------------------------------------------------------


def ic_property_explorer(c):
    """Three linked lists in ink; the accent row is the value picked in the last."""
    if c.small:
        for x0, x1 in ((4, 30), (35, 61), (66, 92)):
            c.rrect(x0, 10, x1, 86, rad=5, w=10)
        c.line([(72, 48), (86, 48)], color=c.t['accent'], w=13)
        return
    for x0, x1 in ((6, 32), (36, 62), (66, 92)):
        c.rrect(x0, 12, x1, 84, rad=5, w=6)
    for x0, x1 in ((6, 32), (36, 62)):
        for y in (30, 44, 58):
            c.line([(x0 + 7, y), (x1 - 7, y)], w=5)
    c.line([(73, 30), (85, 30)], w=5)
    c.rrect(69, 39, 89, 51, rad=3, w=0, fill=c.t['accent'])
    c.line([(73, 60), (85, 60)], w=5)


def ic_count_by_property(c):
    """Groups counted: a sorted bar list, the largest bar in accent."""
    if c.small:
        c.line([(10, 8), (10, 88)], w=12)
        c.line([(22, 28), (80, 28)], color=c.t['accent'], w=16)
        c.line([(22, 52), (66, 52)], w=16)
        c.line([(22, 76), (44, 76)], w=16)
        return
    c.line([(12, 10), (12, 86)], w=7)
    c.line([(24, 26), (84, 26)], color=c.t['accent'], w=12)
    c.line([(24, 46), (66, 46)], w=12)
    c.line([(24, 66), (48, 66)], w=12)
    c.line([(24, 82), (34, 82)], w=8)


def ic_property_exporter(c):
    """The property card with the accent arrow carrying it out to a file."""
    if c.small:
        c.rrect(4, 8, 58, 88, rad=7, w=12)
        c.line([(16, 34), (46, 34)], w=11)
        c.line([(16, 60), (46, 60)], w=11)
        _arrow_h(c, 60, 94, 48, 12, 20)
    else:
        _card(c, 6, 10, 62, 86, 3, w=7)
        _arrow_h(c, 66, 94, 48, 7, 15)


def ic_data_validator(c):
    """A list of rules in ink, the accent tick passing them."""
    if c.small:
        c.rrect(6, 6, 70, 90, rad=7, w=12)
        c.line([(18, 30), (56, 30)], w=11)
        c.line([(46, 74), (62, 88), (92, 52)], color=c.t['accent'], w=14)
        return
    c.rrect(8, 8, 70, 88, rad=6, w=7)
    for y in (28, 44, 60):
        c.line([(20, y), (56, y)], w=5)
    c.line([(48, 70), (62, 84), (90, 54)], color=c.t['accent'], w=9)


def ic_write_data(c):
    """A value field in ink, the accent pencil writing into it."""
    if c.small:
        c.rrect(4, 52, 70, 88, rad=6, w=12)
        _pencil(c, 88, 10, 50, 62, 13)
    else:
        c.rrect(6, 54, 72, 86, rad=6, w=7)
        c.line([(16, 70), (36, 70)], w=6)
        _pencil(c, 88, 10, 50, 62, 8)


def ic_bulk_property_writer(c):
    """Several value fields, the accent pencil writing to all of them."""
    if c.small:
        c.rrect(4, 34, 60, 56, rad=5, w=11)
        c.rrect(4, 66, 60, 88, rad=5, w=11)
        _pencil(c, 90, 8, 62, 42, 12)
    else:
        for y0 in (30, 48, 66):
            c.rrect(6, y0, 60, y0 + 13, rad=4, w=6)
        _pencil(c, 90, 8, 64, 40, 8)


def ic_find_and_replace(c):
    """A line of text with the ink lens over it (found), the accent arrow putting
    the new value in its place. The line stops at the lens rim, so no paper fill
    is needed behind it."""
    if c.small:
        c.line([(4, 28), (14, 28)], w=11)
        c.line([(64, 28), (92, 28)], w=11)
        _lens(c, 39, 28, 17, 11, color=c.t['ink'])
        _arrow_h(c, 8, 92, 80, 12, 22)
    else:
        c.line([(8, 26), (20, 26)], w=6)
        c.line([(64, 26), (88, 26)], w=6)
        _lens(c, 42, 26, 15, 7, color=c.t['ink'])
        _arrow_h(c, 12, 90, 78, 7, 16)


def ic_property_mapper(c):
    """Several source properties (ink dots) converging into one accent field."""
    col = c.t['accent']
    if c.small:
        for y in (16, 48, 80):
            c.disc(14, y, 10, c.t['ink'])
            c.line([(22, y), (58, 48)], w=9)
        c.rrect(60, 34, 92, 62, rad=5, w=0, fill=col)
        return
    for y in (20, 48, 76):
        c.disc(14, y, 8, c.t['ink'])
        c.line([(22, y), (60, 48)], w=5)
    c.rrect(60, 36, 90, 60, rad=5, w=0, fill=col)


def ic_external_data_link(c):
    """A spreadsheet in ink tied to the model by an accent chain link."""
    col = c.t['accent']
    if c.small:
        _grid(c, 4, 6, 54, 62, 11, rows=1, cols=0)
        c.rrect(40, 52, 72, 76, rad=12, w=11, color=col)
        c.rrect(60, 66, 92, 90, rad=12, w=11, color=col)
        return
    _grid(c, 6, 8, 58, 58, 6, rows=2, cols=1)
    c.rrect(44, 54, 72, 74, rad=10, w=7, color=col)
    c.rrect(62, 68, 90, 88, rad=10, w=7, color=col)


def ic_model_tree_export(c):
    """The selection tree in ink, the accent arrow exporting it."""
    w = 12 if c.small else 7
    c.rrect(6, 6, 26, 24, rad=4, w=w)
    c.line([(16, 24), (16, 80)], w=w)
    for y in (46, 80):
        c.line([(16, y), (34, y)], w=w)
        c.rrect(34, y - 9, 52, y + 9, rad=4, w=w)
    if c.small:
        _arrow_h(c, 60, 94, 46, 12, 20)
    else:
        c.line([(58, 64), (62, 64)], w=w)
        _arrow_h(c, 62, 94, 46, 7, 15)


def _tag(c, x0, y0, x1, y1, w, color=None, fill=None):
    """A label tag: a rounded body with a notch point on the left."""
    mid = (y0 + y1) / 2.0
    pts = [(x0 + 12, y0), (x1, y0), (x1, y1), (x0 + 12, y1), (x0, mid)]
    if fill:
        c.poly(pts, fill=fill, w=0)
    else:
        c.poly(pts, color=color, w=w)


def ic_clear_labels(c):
    """A label tag in ink, the accent cross taking it away."""
    col = c.t['accent']
    if c.small:
        _tag(c, 4, 10, 68, 50, 12)
        c.line([(56, 58), (88, 90)], color=col, w=13)
        c.line([(88, 58), (56, 90)], color=col, w=13)
    else:
        _tag(c, 6, 12, 70, 46, 7)
        c.disc(22, 29, 4, c.t['ink'])
        c.line([(58, 58), (86, 86)], color=col, w=9)
        c.line([(86, 58), (58, 86)], color=col, w=9)


def ic_property_labels(c):
    """The object box in ink; the accent leader rises from it to an accent tag:
    its value written in the view."""
    col = c.t['accent']
    if c.small:
        _box(c, 30, 64, 24, w=11)
        c.line([(30, 40), (30, 30), (44, 22)], color=col, w=10)
        _tag(c, 44, 4, 92, 38, 0, fill=col)
        return
    _box(c, 32, 66, 22, w=6)
    c.line([(32, 44), (32, 34), (46, 26)], color=col, w=6)
    _tag(c, 44, 10, 90, 40, 0, fill=col)
    c.line([(60, 25), (80, 25)], w=5, color=c.t['paper'])


ICONS = {
    PANEL + 'Inspect.panel/What_Is_It.pushbutton': ic_what_is_it,
    PANEL + 'Inspect.panel/Properties_Plus.pushbutton': ic_properties_plus,
    PANEL + 'Inspect.panel/Inspect_Tools.stack/Copy_IDs.pushbutton': ic_copy_ids,
    PANEL + 'Inspect.panel/Inspect_Tools.stack/Open_in_Explorer.pushbutton': ic_open_in_explorer,
    PANEL + 'Data.panel/Property_Explorer.pushbutton': ic_property_explorer,
    PANEL + 'Data.panel/Count_by_Property.pushbutton': ic_count_by_property,
    PANEL + 'Data.panel/Property_Exporter.pushbutton': ic_property_exporter,
    PANEL + 'Data.panel/Data_Validator.pushbutton': ic_data_validator,
    PANEL + 'Data.panel/Write_Data.pulldown': ic_write_data,
    PANEL + 'Data.panel/Write_Data.pulldown/Bulk_Property_Writer.pushbutton': ic_bulk_property_writer,
    PANEL + 'Data.panel/Write_Data.pulldown/Find_and_Replace.pushbutton': ic_find_and_replace,
    PANEL + 'Data.panel/Write_Data.pulldown/Property_Mapper.pushbutton': ic_property_mapper,
    PANEL + 'Data.panel/Write_Data.pulldown/External_Data_Link.pushbutton': ic_external_data_link,
    PANEL + 'Data.panel/Data_Tools.stack/Model_Tree_Export.pushbutton': ic_model_tree_export,
    PANEL + 'Data.panel/Data_Tools.stack/Clear_Labels.pushbutton': ic_clear_labels,
    PANEL + 'Data.panel/Property_Labels.pushbutton': ic_property_labels,
}
TOGGLES = {
    PANEL + 'Inspect.panel/Selection_HUD.toggle': (ic_selection_hud_off, ic_selection_hud_on),
}
DOCKPANE_ON = {}

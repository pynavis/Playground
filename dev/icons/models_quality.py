# -*- coding: utf-8 -*-
"""Glyphs for the Models, Quality and Publish panels (Project tab).

The pyNavis language: neutral ink draws the THING (a page, a folder, a model box, a
list of models), one solid accent mark draws what the tool DOES to it (adds, links,
moves, watches, checks, finds, compares, publishes). Small 32 px files are separate,
simpler drawings with fewer parts. Model Wipe carries THE one alert red of Playground.
"""
import math

import make_icons as pn  # noqa: F401  (pyNavis' generator: Ctx helpers and shared marks)

TAB = 'Project.tab/'


# ---- shared marks -------------------------------------------------------------------------


def _page(c, x0, y0, x1, y1, fold=14, color=None, w=None, fill=None):
    """A document outline with a folded top-right corner."""
    pts = [(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)]
    c.poly(pts, color=color, w=w, fill=fill)
    c.line([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], color=color, w=w)


def _folder(c, x0, y0, x1, y1, color=None, w=None, fill=None):
    """A folder: a body with a tab on its top-left."""
    tab = (x1 - x0) * 0.38
    pts = [(x0, y0), (x0 + tab, y0), (x0 + tab + 8, y0 + 8), (x1, y0 + 8), (x1, y1), (x0, y1)]
    c.poly(pts, color=color, w=w, fill=fill)


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


def _arrow(c, start, end, color, w=None, head=14):
    """A straight arrow from start to end (head at end)."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    stop = (end[0] - ux * head * 0.8, end[1] - uy * head * 0.8)
    c.line([start, stop], color=color, w=w)
    _head(c, end, math.degrees(math.atan2(-dy, dx)), head, color)


def _rotated_rect(cx, cy, hx, hy, angle_deg):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for dx, dy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
        out.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
    return out


# ---- Models panel ----------------------------------------------------------------------------


def ic_batch_append(c):
    """Pages stacked up and the accent plus: many files in at once. The pages behind
    are only their edges peeking out, so nothing is filled."""
    if c.small:
        c.line([(18, 24), (18, 8), (46, 8), (58, 20), (58, 68), (48, 68)], w=11)
        _page(c, 6, 24, 48, 88, fold=14, w=11)
        pn.plus(c, 76, 76, 14, 13)
        return
    c.line([(28, 20), (28, 8), (58, 8), (68, 18), (68, 66), (58, 66)])
    c.line([(18, 32), (18, 20), (48, 20), (58, 30), (58, 78), (48, 78)])
    _page(c, 8, 32, 48, 90, fold=10)
    pn.plus(c, 77, 75, 13, 8)


def _list_glyph(c, filled):
    ink, accent = c.t['ink'], c.t['accent']
    if c.small:
        c.rrect(8, 10, 88, 86, rad=10, w=11)
        for y in (34, 62):
            c.rrect(20, y - 8, 36, y + 8, rad=3, w=0 if filled else 9, fill=accent if filled else None)
            c.line([(46, y), (76, y)], w=11)
        return
    c.rrect(8, 10, 88, 86, rad=8)
    for y in (32, 50, 68):
        if filled:
            c.rrect(20, y - 6, 32, y + 6, rad=2, w=0, fill=accent)
        else:
            c.rrect(20, y - 6, 32, y + 6, rad=2, w=5)
        c.line([(42, y), (76, y)], w=6)


def ic_source_files(c):
    """The list of appended models, each row with its show/hide box: the panel at rest."""
    _list_glyph(c, False)


def ic_source_files_on(c):
    """The same list with the boxes in accent: the panel is open."""
    _list_glyph(c, True)


def ic_link_navigator(c):
    """From an element (the small box) up to the file it came from: the accent path."""
    accent, paper = c.t['accent'], c.t['paper']
    if c.small:
        c.rrect(6, 54, 40, 88, rad=6, w=11)
        _page(c, 52, 6, 90, 52, fold=12, w=11)
        c.line([(23, 46), (23, 24), (34, 24)], color=accent, w=11)
        _head(c, (48, 24), 0, 16, accent)
        return
    c.rrect(10, 54, 42, 86, rad=5)
    c.line([(18, 70), (34, 70)], w=5)
    _page(c, 54, 10, 88, 56, fold=11)
    c.line([(26, 46), (26, 26), (40, 26)], color=accent, w=7)
    _head(c, (50, 26), 0, 13, accent)


def ic_transform_fixer(c):
    """The model where it was (ink) and where it goes, turned (accent), with the move."""
    accent = c.t['accent']
    if c.small:
        c.rrect(6, 52, 40, 88, rad=5, w=11)
        pn.tilted_box(c, 15, 15, 22, color=accent, w=11, cx=68, cy=28)
        _arrow(c, (30, 60), (50, 42), accent, w=9, head=14)
        return
    c.rrect(8, 54, 40, 86, rad=5)
    pn.tilted_box(c, 16, 16, 20, color=accent, w=7, cx=68, cy=30)
    _arrow(c, (34, 60), (52, 44), accent, w=6, head=12)


def _folder_watch(c, engaged):
    """A folder with a lens on it: ring and pupil in ink at rest, in accent when watching."""
    ink, accent = c.t['ink'], c.t['accent']
    color = accent if engaged else ink
    if c.small:
        _folder(c, 6, 14, 90, 84, w=11)
        c.circle(48, 52, 16, color=color, w=9)
        c.disc(48, 52, 6, color)
        return
    _folder(c, 8, 18, 88, 82)
    c.circle(48, 54, 15, color=color, w=6)
    c.disc(48, 54, 6, color)


def ic_folder_watch_off(c):
    """A folder with an eye at rest: Folder Watch is off."""
    _folder_watch(c, False)


def ic_folder_watch_on(c):
    """The eye in accent: the folder is being watched."""
    _folder_watch(c, True)


def ic_stale_files(c):
    """A model file and the accent clock beside it: which file is older than its source."""
    accent = c.t['accent']
    if c.small:
        _page(c, 4, 4, 46, 70, fold=14, w=11)
        c.circle(68, 68, 21, color=accent, w=11)
        c.line([(68, 58), (68, 68), (76, 73)], color=accent, w=9)
        return
    _page(c, 8, 6, 46, 72, fold=10)
    c.line([(17, 34), (36, 34)], w=5)
    c.line([(17, 48), (30, 48)], w=5)
    c.circle(68, 68, 20, color=accent, w=7)
    c.line([(68, 56), (68, 68), (77, 74)], color=accent, w=6)


# ---- Quality panel -----------------------------------------------------------------------------


def ic_model_health_check(c):
    """The pulse across a model: how healthy each appended model is."""
    accent = c.t['accent']
    pulse = [(14, 52), (32, 52), (40, 34), (52, 70), (60, 46), (66, 52), (82, 52)]
    if c.small:
        c.rrect(4, 14, 92, 84, rad=10, w=11)
        c.line([(14, 52), (34, 52), (44, 30), (56, 72), (66, 52), (82, 52)], color=accent, w=11)
        return
    c.rrect(6, 16, 90, 82, rad=8)
    c.line(pulse, color=accent, w=7)


def ic_duplicate_finder(c):
    """Two copies of the same object, the found one (accent) in front of the other."""
    accent = c.t['accent']
    if c.small:
        c.line([(38, 58), (6, 58), (6, 6), (58, 6), (58, 38)], w=11)
        c.rrect(38, 38, 90, 90, rad=8, color=accent, w=11)
        return
    c.line([(38, 58), (10, 58), (10, 10), (58, 10), (58, 38)])
    c.rrect(38, 38, 86, 86, rad=7, color=accent, w=7)


def ic_model_compare(c):
    """Two versions of a model side by side; the accent block is what moved between them."""
    accent = c.t['accent']
    if c.small:
        c.rrect(4, 18, 44, 78, rad=6, w=11)
        c.rrect(52, 18, 92, 78, rad=6, w=11)
        c.rrect(64, 30, 80, 46, rad=3, w=0, fill=accent)
        return
    c.rrect(6, 20, 44, 76, rad=6)
    c.rrect(52, 20, 90, 76, rad=6)
    c.rrect(16, 50, 32, 66, rad=3, w=5)
    c.rrect(62, 30, 80, 48, rad=3, w=0, fill=accent)


def ic_preflight(c):
    """The checklist on a clipboard with the accent tick: ready to share or not."""
    accent, paper = c.t['accent'], c.t['paper']
    if c.small:
        c.rrect(12, 12, 84, 90, rad=8, w=11)
        c.rrect(32, 4, 64, 22, rad=4, w=0, fill=c.t['ink'])
        c.line([(28, 54), (42, 68), (70, 38)], color=accent, w=13)
        return
    c.rrect(16, 14, 80, 90, rad=7)
    c.rrect(34, 6, 62, 22, rad=4, fill=paper)
    c.line([(28, 46), (38, 56), (56, 36)], color=accent, w=7)
    c.line([(30, 74), (66, 74)], w=5)


def ic_session_stats(c):
    """Bars per model with the heaviest in accent."""
    ink, accent = c.t['ink'], c.t['accent']
    if c.small:
        c.rrect(8, 50, 28, 86, rad=3, w=0, fill=ink)
        c.rrect(38, 30, 58, 86, rad=3, w=0, fill=ink)
        c.rrect(68, 8, 88, 86, rad=3, w=0, fill=accent)
        return
    c.line([(8, 88), (88, 88)], w=6)
    c.rrect(14, 56, 30, 82, rad=3, w=0, fill=ink)
    c.rrect(40, 36, 56, 82, rad=3, w=0, fill=ink)
    c.rrect(66, 12, 82, 82, rad=3, w=0, fill=accent)


# ---- Publish panel -------------------------------------------------------------------------------


def ic_nwd_publisher(c):
    """The finished model file and the accent arrow sending the next version out."""
    accent = c.t['accent']
    if c.small:
        _page(c, 6, 24, 54, 92, fold=14, w=11)
        c.arrow_v(74, 84, 6, w=13, head=24)
        return
    _page(c, 10, 26, 56, 90, fold=12)
    c.line([(20, 56), (44, 56)], w=5)
    c.line([(20, 70), (38, 70)], w=5)
    c.arrow_v(74, 82, 8, w=8, head=18)


def ic_model_wipe(c):
    """The model and the eraser taking its added data away: the one red glyph in Playground."""
    alert, paper = c.t['alert'], c.t['paper']
    if c.small:
        c.rrect(6, 6, 54, 54, rad=8, w=11)
        c.poly(_rotated_rect(64, 66, 26, 13, -40), color=alert, fill=alert, w=0)
        return
    c.rrect(8, 8, 56, 56, rad=7)
    c.line([(18, 26), (44, 26)], w=5)
    c.line([(18, 38), (36, 38)], w=5)
    body = _rotated_rect(62, 66, 28, 13, -40)
    c.poly(body, color=alert, fill=alert, w=0)
    # the eraser's sleeve line
    a = math.radians(-40)
    mx, my = 62 + 6 * math.cos(a), 66 + 6 * math.sin(a)
    px, py = -math.sin(a), math.cos(a)
    c.line([(mx - px * 10, my - py * 10), (mx + px * 10, my + py * 10)], color=paper, w=4)
    c.line([(30, 88), (86, 88)], color=alert, w=6)


ICONS = {
    TAB + 'Models.panel/Batch_Append.pushbutton': ic_batch_append,
    TAB + 'Models.panel/Source_Files.dockpane': ic_source_files,
    TAB + 'Models.panel/Link_Navigator.pushbutton': ic_link_navigator,
    TAB + 'Models.panel/Transform_Fixer.pushbutton': ic_transform_fixer,
    TAB + 'Models.panel/Stale_File_Alert.pushbutton': ic_stale_files,
    TAB + 'Quality.panel/Model_Health_Check.pushbutton': ic_model_health_check,
    TAB + 'Quality.panel/Duplicate_Finder.pushbutton': ic_duplicate_finder,
    TAB + 'Quality.panel/Model_Compare.pushbutton': ic_model_compare,
    TAB + 'Quality.panel/Preflight.pushbutton': ic_preflight,
    TAB + 'Quality.panel/Session_Stats.pushbutton': ic_session_stats,
    TAB + 'Publish.panel/NWD_Publisher.pushbutton': ic_nwd_publisher,
    TAB + 'Publish.panel/Model_Wipe.pushbutton': ic_model_wipe,
}

TOGGLES = {
    TAB + 'Models.panel/Folder_Watch.toggle': (ic_folder_watch_off, ic_folder_watch_on),
}

DOCKPANE_ON = {
    TAB + 'Models.panel/Source_Files.dockpane': ic_source_files_on,
}

# -*- coding: utf-8 -*-
"""Glyphs for the Issues and BCF panels.

Family rule: the ISSUE MARKER is a diamond, the same head the Issue Pins draw in the view,
so every issue tool carries one. Ink draws the thing (a register, a stamp, a box, a page),
accent draws what the tool does (the marker it adds, the symbol it stamps, the arrow that
moves data). Small 32 px drawings are separate, heavier and simpler. No alert red: a
Safety issue is marked in accent like every other stamp.
"""
import os
import sys

_PYNAVIS_TOOLS = os.path.join(os.environ.get('PYNAVIS_SRC') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'pyNavis'), 'tools')
if _PYNAVIS_TOOLS not in sys.path:
    sys.path.insert(0, _PYNAVIS_TOOLS)

import make_icons as pn  # noqa: E402,F401  (pyNavis' generator)

PANEL = 'Coordinate.tab/Issues.panel/'
BCF = 'Coordinate.tab/BCF.panel/'


# ---- shared marks ------------------------------------------------------------------------------


def diamond(c, cx, cy, r, color=None, w=None, fill=None):
    """The issue marker: a diamond, outlined (w) and/or filled."""
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    if fill is not None:
        c.poly(pts, color=fill, fill=fill, w=0)
    if w != 0:
        c.poly(pts, color=color, w=w)


def pin(c, x, foot, height, r, color, w, fill=None):
    """A stem from foot up `height`, a diamond head on top (the overlay pin)."""
    head = foot - height
    c.line([(x, foot), (x, head + r)], color=color, w=w)
    diamond(c, x, head, r, color=color, w=w, fill=fill)


def stamp_body(c, x0, y0, x1, y1, knob_r, w, base_h=18):
    """A rubber stamp: knob, neck, a solid block and the rubber pad under it, in ink."""
    ink = c.t['ink']
    cx = (x0 + x1) / 2.0
    c.disc(cx, y0 + knob_r, knob_r, ink)
    c.line([(cx, y0 + knob_r * 2), (cx, y1 - base_h)], w=w)
    c.rrect(x0, y1 - base_h, x1, y1 - w * 0.6, rad=4, fill=ink, w=0)
    c.line([(x0 + w, y1), (x1 - w, y1)], w=w)


def _qmark(c, cx, cy, s, w, color):
    """A question mark centred at (cx, cy), s = half height."""
    c.line([(cx - s * 0.55, cy - s * 0.45), (cx - s * 0.35, cy - s * 0.85), (cx, cy - s),
            (cx + s * 0.4, cy - s * 0.85), (cx + s * 0.55, cy - s * 0.45),
            (cx + s * 0.3, cy - s * 0.1), (cx, cy + s * 0.15), (cx, cy + s * 0.4)],
           color=color, w=w)
    c.disc(cx, cy + s * 0.85, w * 0.62, color)


# ---- Issues register (dock pane) ------------------------------------------------------------


def ic_issues(c):
    """The register: a sheet with rows, each led by an issue marker; the first marker is
    accent (the issue you are on). The panel's OFF art."""
    acc = c.t['accent']
    if c.small:
        c.rrect(6, 6, 90, 90, rad=10, w=11)
        for y, fill in ((34, acc), (62, None)):
            diamond(c, 28, y, 10, color=c.t['ink'], w=0 if fill else 9, fill=fill)
            c.line([(46, y), (76, y)], w=10)
        return
    c.rrect(10, 10, 86, 86, rad=8, w=7)
    for index, y in enumerate((31, 49, 67)):
        if index == 0:
            diamond(c, 27, y, 7, fill=acc, w=0)
        else:
            diamond(c, 27, y, 6, w=5)
        c.line([(41, y), (74 if index != 1 else 66, y)], w=6)


def ic_issues_on(c):
    """The same register filled with accent, rows punched out in paper: the panel is open."""
    paper = c.t['paper']
    c.rrect(10, 10, 86, 86, rad=8, fill=c.t['accent'], w=0)
    for index, y in enumerate((31, 49, 67)):
        diamond(c, 27, y, 7 if index == 0 else 6, fill=paper, w=0)
        c.line([(41, y), (74 if index != 1 else 66, y)], color=paper, w=6)


# ---- stamps ---------------------------------------------------------------------------------------


def ic_issue_stamps(c):
    """A rubber stamp in ink leaving an accent issue marker."""
    acc = c.t['accent']
    if c.small:
        stamp_body(c, 14, 4, 82, 60, 12, 11, base_h=24)
        diamond(c, 48, 81, 13, fill=acc, w=0)
        return
    stamp_body(c, 20, 6, 76, 58, 10, 7, base_h=20)
    diamond(c, 48, 79, 11, fill=acc, w=0)


def _stamp_frame(c):
    """The diamond outline every stamp child shares; returns (stroke, inner scale)."""
    if c.small:
        diamond(c, 48, 48, 43, w=10)
        return 12, 1.0
    diamond(c, 48, 48, 40, w=7)
    return 8, 1.0


def ic_rfi(c):
    """A request for information: an accent question mark on the issue marker."""
    w, _k = _stamp_frame(c)
    _qmark(c, 48, 44, 19 if c.small else 17, w, c.t['accent'])


def ic_hold(c):
    """Hold: accent pause bars on the issue marker."""
    w, _k = _stamp_frame(c)
    acc = c.t['accent']
    h = 15 if c.small else 14
    for x in (40, 56):
        c.line([(x, 48 - h), (x, 48 + h)], color=acc, w=w)


def ic_verify(c):
    """Verify: an accent check mark on the issue marker."""
    w, _k = _stamp_frame(c)
    c.line([(32, 50), (44, 61), (64, 36)], color=c.t['accent'], w=w)


def ic_safety(c):
    """Safety: an accent exclamation mark on the issue marker (accent, never alert red)."""
    w, _k = _stamp_frame(c)
    acc = c.t['accent']
    c.line([(48, 28), (48, 54)], color=acc, w=w)
    c.disc(48, 66, w * 0.62, acc)


def ic_stamp_from_template(c):
    """The stamp printing an accent template card: any template, chosen first."""
    acc = c.t['accent']
    if c.small:
        stamp_body(c, 14, 4, 82, 54, 12, 11, base_h=22)
        c.rrect(20, 66, 76, 92, rad=5, color=acc, w=10)
        return
    stamp_body(c, 20, 6, 76, 52, 10, 7, base_h=18)
    c.rrect(26, 64, 70, 90, rad=4, color=acc, w=6)
    c.line([(35, 77), (61, 77)], color=acc, w=5)


# ---- pins ---------------------------------------------------------------------------------------------


def _pins(c, fill_heads):
    ink = c.t['ink']
    acc = c.t['accent']
    if c.small:
        pin(c, 30, 90, 48, 14, ink, 11, fill=acc if fill_heads else None)
        pin(c, 68, 76, 44, 14, ink, 11, fill=acc if fill_heads else None)
        return
    c.line([(10, 86), (86, 86)], w=5)
    pin(c, 32, 86, 50, 12, acc if fill_heads else ink, 7, fill=acc if fill_heads else None)
    pin(c, 66, 86, 36, 12, acc if fill_heads else ink, 7, fill=acc if fill_heads else None)


def ic_issue_pins_off(c):
    """Two issue pins standing on the model, outlined in ink: pins hidden (click shows)."""
    _pins(c, False)


def ic_issue_pins_on(c):
    """The same pins in accent: shown in the view."""
    _pins(c, True)


# ---- meeting, templates, clash to issues --------------------------------------------------------------


def ic_meeting_mode(c):
    """A meeting screen in ink with the accent 'next' arrow: step through the agenda."""
    acc = c.t['accent']
    if c.small:
        c.rrect(4, 10, 92, 70, rad=8, w=11)
        c.line([(48, 70), (48, 88)], w=11)
        c.poly([(38, 26), (62, 40), (38, 54)], color=acc, fill=acc, w=0)
        return
    c.rrect(8, 12, 88, 66, rad=6, w=7)
    c.line([(48, 66), (48, 82)], w=7)
    c.line([(30, 84), (66, 84)], w=7)
    c.poly([(40, 26), (60, 39), (40, 52)], color=acc, fill=acc, w=0)


def ic_issue_templates(c):
    """Two stacked template cards with the accent issue marker on the front one."""
    paper = c.t['paper']
    acc = c.t['accent']
    if c.small:
        c.rrect(32, 6, 90, 62, rad=8, w=11)
        c.rrect(6, 32, 64, 90, rad=8, w=11, fill=paper)
        diamond(c, 35, 61, 14, fill=acc, w=0)
        return
    c.rrect(26, 8, 86, 64, rad=7, w=7)
    c.rrect(10, 30, 70, 86, rad=7, w=7, fill=paper)
    diamond(c, 40, 58, 12, fill=acc, w=0)


def ic_clash_to_issues(c):
    """A clash spark (the clash tools' accent mark) becoming an issue marker in ink."""
    if c.small:
        pn.spark(c, 26, 28, 18, 11)
        diamond(c, 62, 62, 26, w=11)
        return
    pn.spark(c, 26, 26, 15, 7)
    acc = c.t['accent']
    c.line([(42, 42), (52, 52)], color=acc, w=6)
    c.poly([(58, 58), (46, 54), (54, 46)], color=acc, fill=acc, w=0)
    diamond(c, 64, 64, 22, w=7)


# ---- reports -----------------------------------------------------------------------------------------


def ic_coordination_report(c):
    """A report page: bars in ink, the longest in accent, issue marker at the top."""
    acc = c.t['accent']
    if c.small:
        c.rrect(10, 4, 86, 92, rad=8, w=11)
        c.line([(28, 34), (68, 34)], color=acc, w=11)
        c.line([(28, 56), (56, 56)], w=10)
        c.line([(28, 76), (46, 76)], w=10)
        return
    c.rrect(16, 6, 80, 90, rad=6, w=7)
    diamond(c, 30, 22, 6, fill=acc, w=0)
    c.line([(42, 22), (66, 22)], w=5)
    c.line([(28, 44), (66, 44)], color=acc, w=8)
    c.line([(28, 59), (56, 59)], w=8)
    c.line([(28, 74), (44, 74)], w=8)


def ic_kpi_export(c):
    """A data table in ink with the accent arrow taking it out (to Power BI)."""
    acc = c.t['accent']
    if c.small:
        c.rrect(4, 4, 70, 70, rad=8, w=11)
        c.line([(4, 32), (70, 32)], w=10)
        c.line([(30, 32), (30, 70)], w=10)
        c.line([(60, 60), (88, 88)], color=acc, w=12)
        c.poly([(92, 92), (68, 90), (90, 68)], color=acc, fill=acc, w=0)
        return
    c.rrect(8, 8, 68, 68, rad=6, w=7)
    c.line([(8, 28), (68, 28)], w=6)
    c.line([(8, 48), (68, 48)], w=5)
    c.line([(30, 28), (30, 68)], w=5)
    c.line([(60, 60), (80, 80)], color=acc, w=7)
    c.poly([(90, 90), (70, 88), (88, 70)], color=acc, fill=acc, w=0)


# ---- BCF ---------------------------------------------------------------------------------------------


def _bcf_box(c, top):
    """The BCF file: a box (a zip of topics) with the issue marker on its front."""
    if c.small:
        c.rrect(8, top, 88, 92, rad=8, w=11)
        c.line([(8, top + 16), (88, top + 16)], w=10)
        return
    c.rrect(14, top, 82, 88, rad=6, w=7)
    c.line([(14, top + 12), (82, top + 12)], w=6)
    diamond(c, 48, (top + 12 + 88) / 2.0 + 1, 8, w=5)


def ic_bcf_export(c):
    """The BCF box with the accent arrow leaving it: issues go out."""
    if c.small:
        _bcf_box(c, 48)
        c.arrow_v(48, 50, 4, w=12, head=24)
        return
    _bcf_box(c, 44)
    c.arrow_v(48, 52, 6, w=7, head=18)


def ic_bcf_import(c):
    """The BCF box with the accent arrow coming into it: topics come in."""
    if c.small:
        _bcf_box(c, 48)
        c.arrow_v(48, 4, 50, w=12, head=24)
        return
    _bcf_box(c, 44)
    c.arrow_v(48, 4, 56, w=7, head=18)


ICONS = {
    PANEL + 'Issues.dockpane': ic_issues,
    PANEL + 'Issue_Stamps.pulldown': ic_issue_stamps,
    PANEL + 'Issue_Stamps.pulldown/RFI.pushbutton': ic_rfi,
    PANEL + 'Issue_Stamps.pulldown/Hold.pushbutton': ic_hold,
    PANEL + 'Issue_Stamps.pulldown/Verify.pushbutton': ic_verify,
    PANEL + 'Issue_Stamps.pulldown/Safety.pushbutton': ic_safety,
    PANEL + 'Issue_Stamps.pulldown/Stamp_from_Template.pushbutton': ic_stamp_from_template,
    PANEL + 'Meeting_Mode.pushbutton': ic_meeting_mode,
    PANEL + 'Issue_Tools.stack/Issue_Templates.pushbutton': ic_issue_templates,
    PANEL + 'Issue_Tools.stack/Clash_to_Issues.pushbutton': ic_clash_to_issues,
    PANEL + 'Coordination_Report.pushbutton': ic_coordination_report,
    PANEL + 'KPI_Export.pushbutton': ic_kpi_export,
    BCF + 'BCF_Export.pushbutton': ic_bcf_export,
    BCF + 'BCF_Import.pushbutton': ic_bcf_import,
}
TOGGLES = {PANEL + 'Issue_Pins.toggle': (ic_issue_pins_off, ic_issue_pins_on)}
DOCKPANE_ON = {PANEL + 'Issues.dockpane': ic_issues_on}

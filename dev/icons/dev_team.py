# -*- coding: utf-8 -*-
"""Glyphs for the Dev tab's Automate, Build, Team and Tools panels.

Family marks, so the power-user layer reads as one set:
  * the STEP LIST (three short ink bars, the first led by a dot) is a macro: Play Macro
    puts the accent play triangle before it, Manage Macros the accent reorder arrows,
    the Macros menu the accent dots that chain the steps, Macro to Button sets the play
    triangle inside a ribbon button.
  * the BUTTON (an ink rounded square) is a ribbon button: Button Maker adds an accent
    plus to its corner.
  * the KEYCAP is a shortcut, the RULER a length, the WINDOW FRAME a tool window.
Ink draws the thing, accent the action. No alert red anywhere here (Model Wipe owns it).
"""

import make_icons as pn  # noqa: F401  (pyNavis' generator: Ctx and the shared marks)

AUTO = 'Dev.tab/Automate.panel/'
BUILD = 'Dev.tab/Build.panel/'
TEAM = 'Dev.tab/Team.panel/'
TOOLS = 'Dev.tab/Tools.panel/'


def _w(c, large=7, small=12):
    return small if c.small else large


def _triangle(c, x0, y0, size, color=None):
    """A play triangle pointing right, top-left corner at (x0, y0)."""
    col = color or c.t['accent']
    c.poly([(x0, y0), (x0 + size * 0.9, y0 + size / 2.0), (x0, y0 + size)], fill=col, w=0)


def _steps(c, x0, x1, ys, w, lead=True):
    """The step list: short ink bars, each led by a small ink dot."""
    for y in ys:
        if lead:
            c.disc(x0, y, w * 0.75, c.t['ink'])
            c.line([(x0 + w * 2.2, y), (x1, y)], w=w)
        else:
            c.line([(x0, y), (x1, y)], w=w)


# ---- Automate -----------------------------------------------------------------------------


def ic_command_palette(c):
    """A search field with an accent prompt chevron, results listed below it."""
    if c.small:
        c.rrect(6, 12, 90, 46, rad=8, w=12)
        c.line([(20, 20), (32, 29), (20, 38)], color=c.t['accent'], w=11)
        c.line([(8, 68), (88, 68)], w=12)
        c.line([(8, 88), (60, 88)], w=12)
    else:
        c.rrect(8, 12, 88, 40, rad=7)
        c.line([(20, 19), (31, 26), (20, 33)], color=c.t['accent'], w=7)
        c.line([(40, 26), (70, 26)], w=6)
        c.line([(12, 56), (84, 56)], w=6)
        c.line([(12, 70), (72, 70)], w=6)
        c.line([(12, 84), (60, 84)], w=6)


def ic_record_off(c):
    """Record: an accent dot inside an ink ring (the toggle at rest; also its small art)."""
    if c.small:
        c.circle(48, 48, 38, w=11)
        c.disc(48, 48, 21, c.t['accent'])
    else:
        c.circle(48, 48, 34, w=7)
        c.disc(48, 48, 18, c.t['accent'])


def ic_record_on(c):
    """Recording: the stop square punched out of an accent tile (large only)."""
    c.rrect(6, 6, 90, 90, rad=16, w=0, fill=c.t['accent'])
    c.rrect(32, 32, 64, 64, rad=5, w=0, fill=c.t['paper'])


def ic_macros_menu(c):
    """The step list with accent links chaining one step to the next."""
    if c.small:
        for y in (18, 48, 78):
            c.disc(16, y, 10, c.t['accent'])
            c.line([(36, y), (90, y)], w=12)
        c.line([(16, 18), (16, 78)], color=c.t['accent'], w=6)
    else:
        for y in (20, 48, 76):
            c.disc(18, y, 8, c.t['accent'])
            c.line([(36, y), (84, y)], w=7)
        c.line([(18, 20), (18, 76)], color=c.t['accent'], w=4)


def ic_play_macro(c):
    """The accent play triangle before the step list."""
    if c.small:
        _triangle(c, 4, 26, 44)
        for y in (24, 48, 72):
            c.line([(56, y), (92, y)], w=12)
    else:
        _triangle(c, 8, 26, 44)
        for y in (26, 48, 70):
            c.line([(56, y), (88, y)], w=7)


def ic_manage_macros(c):
    """The step list with accent arrows that move a step up or down."""
    if c.small:
        for y in (20, 48, 76):
            c.line([(6, y), (54, y)], w=12)
        c.arrow_v(76, 46, 6, w=10, head=20)
        c.arrow_v(76, 50, 90, w=10, head=20)
    else:
        _steps(c, 12, 56, (24, 48, 72), 7)
        c.arrow_v(76, 44, 12, w=7, head=16)
        c.arrow_v(76, 52, 84, w=7, head=16)


def ic_macro_to_button(c):
    """The play triangle set inside a ribbon button (an ink rounded square)."""
    if c.small:
        c.rrect(8, 8, 88, 88, rad=16, w=12)
        _triangle(c, 34, 26, 44)
    else:
        c.rrect(10, 10, 86, 86, rad=16)
        _triangle(c, 36, 30, 36)
        c.line([(24, 74), (72, 74)], w=5)


# ---- Build ---------------------------------------------------------------------------------


def ic_button_maker(c):
    """A ribbon button in ink and an accent plus at its corner: a new button."""
    if c.small:
        c.rrect(4, 18, 66, 80, rad=12, w=12)
        pn.plus(c, 74, 22, 17, 12)
    else:
        c.rrect(8, 24, 64, 80, rad=12)
        c.line([(22, 66), (50, 66)], w=5)
        pn.plus(c, 72, 24, 15, 8)


def ic_script_editor(c):
    """A code page: indented ink lines and an accent text cursor."""
    if c.small:
        c.line([(6, 18), (62, 18)], w=12)
        c.line([(22, 46), (70, 46)], w=12)
        c.line([(6, 74), (46, 74)], w=12)
        c.line([(84, 34), (84, 86)], color=c.t['accent'], w=11)
    else:
        c.rrect(6, 10, 90, 86, rad=8)
        c.line([(18, 28), (56, 28)], w=6)
        c.line([(30, 44), (70, 44)], w=6)
        c.line([(30, 60), (60, 60)], w=6)
        c.line([(18, 74), (44, 74)], w=6)
        c.line([(70, 54), (70, 78)], color=c.t['accent'], w=6)


def ic_hotkey_manager(c):
    """A keycap in ink, an accent arrow, and the small ribbon button the key runs."""
    if c.small:
        c.rrect(2, 22, 46, 74, rad=10, w=12)
        c.line([(52, 48), (66, 48)], color=c.t['accent'], w=10)
        c.poly([(62, 36), (76, 48), (62, 60)], fill=c.t['accent'], w=0)
        c.rrect(80, 34, 94, 62, rad=4, w=0, fill=c.t['ink'])
    else:
        c.rrect(4, 26, 44, 66, rad=8)
        c.line([(16, 56), (32, 56)], w=5)
        c.line([(50, 46), (60, 46)], color=c.t['accent'], w=7)
        c.poly([(58, 36), (70, 46), (58, 56)], fill=c.t['accent'], w=0)
        c.rrect(74, 32, 92, 60, rad=5, w=6)


# ---- Team ----------------------------------------------------------------------------------


def _box(c, cx, top, half, depth, w):
    """An open-top package seen from the front-right: the extension being installed."""
    left, right = cx - half, cx + half
    c.line([(left, top), (left, top + depth), (right, top + depth), (right, top)], w=w)
    c.line([(left, top), (left + half * 0.45, top - half * 0.3)], w=w)
    c.line([(right, top), (right - half * 0.45, top - half * 0.3)], w=w)


def ic_extension_manager(c):
    """An open package in ink with an accent arrow dropping into it: install."""
    if c.small:
        _box(c, 48, 48, 38, 40, 12)
        c.arrow_v(48, 2, 60, w=12, head=24)
    else:
        _box(c, 48, 50, 34, 34, 7)
        c.arrow_v(48, 6, 62, w=8, head=18)


def ic_team_sync(c):
    """Two folders in ink with accent arrows passing between them."""
    w = _w(c)
    if c.small:
        c.rrect(2, 8, 38, 40, rad=6, w=w)
        c.rrect(58, 56, 94, 88, rad=6, w=w)
        c.line([(46, 24), (72, 24), (72, 42)], color=c.t['accent'], w=10)
        c.poly([(62, 40), (82, 40), (72, 54)], fill=c.t['accent'], w=0)
        c.line([(50, 72), (24, 72), (24, 54)], color=c.t['accent'], w=10)
        c.poly([(14, 56), (34, 56), (24, 42)], fill=c.t['accent'], w=0)
    else:
        c.rrect(6, 10, 40, 40, rad=5)
        c.line([(6, 18), (10, 10), (22, 10), (26, 16)], w=5)
        c.rrect(56, 56, 90, 86, rad=5)
        c.line([(46, 25), (72, 25), (72, 42)], color=c.t['accent'], w=6)
        c.poly([(64, 40), (80, 40), (72, 52)], fill=c.t['accent'], w=0)
        c.line([(50, 71), (24, 71), (24, 54)], color=c.t['accent'], w=6)
        c.poly([(16, 56), (32, 56), (24, 44)], fill=c.t['accent'], w=0)


def ic_usage_analytics(c):
    """Three accent bars rising on ink axes."""
    if c.small:
        c.line([(6, 6), (6, 90), (92, 90)], w=11)
        for x, top in ((28, 60), (52, 38), (76, 14)):
            c.rrect(x - 8, top, x + 8, 82, rad=3, w=0, fill=c.t['accent'])
    else:
        c.line([(10, 10), (10, 86), (88, 86)], w=6)
        for x, top in ((30, 58), (52, 38), (74, 18)):
            c.rrect(x - 8, top, x + 8, 78, rad=3, w=0, fill=c.t['accent'])


def ic_environment_doctor(c):
    """A pulse line in accent across an ink window: the health of the setup."""
    pts = [(10, 52), (30, 52), (38, 34), (48, 70), (58, 26), (66, 52), (86, 52)]
    if c.small:
        c.rrect(4, 10, 92, 86, rad=10, w=11)
        c.line([(8, 50), (26, 50), (36, 28), (48, 72), (60, 26), (70, 50), (88, 50)],
               color=c.t['accent'], w=9)
    else:
        c.rrect(6, 14, 90, 82, rad=8)
        c.line(pts, color=c.t['accent'], w=6)


def ic_playground_settings(c):
    """Three upright sliders, accent knobs at different heights: settings to set."""
    if c.small:
        for x, knob in ((18, 62), (48, 30), (78, 54)):
            c.line([(x, 8), (x, 88)], w=11)
            c.disc(x, knob, 14, c.t['accent'])
    else:
        for x, knob in ((22, 60), (48, 32), (74, 52)):
            c.line([(x, 12), (x, 84)], w=6)
            c.disc(x, knob, 11, c.t['accent'])


# ---- Tools ---------------------------------------------------------------------------------


def ic_unit_converter(c):
    """A ruler in ink with an accent two-way arrow above it: one unit to another."""
    if c.small:
        c.rrect(4, 56, 92, 88, rad=5, w=11)
        for x in (24, 48, 72):
            c.line([(x, 56), (x, 70)], w=9)
        c.line([(18, 26), (78, 26)], color=c.t['accent'], w=10)
        c.poly([(28, 12), (10, 26), (28, 40)], fill=c.t['accent'], w=0)
        c.poly([(68, 12), (86, 26), (68, 40)], fill=c.t['accent'], w=0)
    else:
        c.rrect(6, 54, 90, 84, rad=5)
        for x, tall in ((20, 1), (34, 0), (48, 1), (62, 0), (76, 1)):
            c.line([(x, 54), (x, 68 if tall else 62)], w=5)
        c.line([(22, 28), (74, 28)], color=c.t['accent'], w=7)
        c.poly([(30, 16), (14, 28), (30, 40)], fill=c.t['accent'], w=0)
        c.poly([(66, 16), (82, 28), (66, 40)], fill=c.t['accent'], w=0)


ICONS = {
    AUTO + 'Command_Palette.pushbutton': ic_command_palette,
    AUTO + 'Macros.pulldown': ic_macros_menu,
    AUTO + 'Macros.pulldown/Play_Macro.pushbutton': ic_play_macro,
    AUTO + 'Macros.pulldown/Manage_Macros.pushbutton': ic_manage_macros,
    AUTO + 'Macros.pulldown/Macro_to_Button.pushbutton': ic_macro_to_button,
    BUILD + 'Button_Maker.pushbutton': ic_button_maker,
    BUILD + 'Script_Editor.pushbutton': ic_script_editor,
    BUILD + 'Hotkey_Manager.pushbutton': ic_hotkey_manager,
    TEAM + 'Extension_Manager.pushbutton': ic_extension_manager,
    TEAM + 'Team_Sync.pushbutton': ic_team_sync,
    TEAM + 'Usage_Analytics.pushbutton': ic_usage_analytics,
    TEAM + 'Team_Tools.stack/Environment_Doctor.pushbutton': ic_environment_doctor,
    TEAM + 'Team_Tools.stack/Playground_Settings.pushbutton': ic_playground_settings,
    TOOLS + 'Unit_Converter.pushbutton': ic_unit_converter,
}
TOGGLES = {
    AUTO + 'Macro_Record.toggle': (ic_record_off, ic_record_on),
}
DOCKPANE_ON = {}

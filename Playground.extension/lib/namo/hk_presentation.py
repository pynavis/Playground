# -*- coding: utf-8 -*-
"""Puts the ribbon, panels, window and background back if Navisworks closes while
Presentation Mode is on (Navisworks would otherwise remember the minimized ribbon and
closed add-in panels into the next session)."""


def handle(name, event):
    try:
        from namo import presentation
        if presentation.is_on():
            presentation.leave()
    except Exception:
        pass

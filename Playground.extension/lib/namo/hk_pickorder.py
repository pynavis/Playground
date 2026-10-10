# -*- coding: utf-8 -*-
"""Pick Order hook: appends newly clicked items to the pick list (see namo.sel_pickorder).

Runs after every debounced 'selection-changed', so the off case must cost nothing: the
on/off flag is read straight off the session holder (a module object in sys.modules)
before any other Playground module is imported. Only while the Pick Order toggle is on does
it import namo.sel_pickorder and look at the selection. Selections of more than 500 items
are not tracked item by item; added sets of more than 20 items are not picks. Never
raises.
"""
import sys

HOLDER_MODULE = 'playground_pickorder'      # namo.session.PREFIX + namo.sel_pickorder.HOLDER


def is_on():
    """True while the Pick Order toggle is on. Imports nothing."""
    return bool(getattr(sys.modules.get(HOLDER_MODULE), 'on', False))


def handle(name, event):
    if name != 'selection-changed' or not is_on():
        return
    try:
        from namo import sel_pickorder
        sel_pickorder.on_selection()
    except Exception as error:
        try:
            from namo import session
            session.log('warning', 'Pick Order could not record a pick: %s' % error)
        except Exception:
            pass

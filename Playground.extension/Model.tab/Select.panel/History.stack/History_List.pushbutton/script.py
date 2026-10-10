# -*- coding: utf-8 -*-
"""Lists the selections made in this model and restores the one you choose."""
from pynavis import toast

from namo import sel_history, ui

if not sel_history.settings().get('enabled', True):
    toast.show(*sel_history.OFF)
else:
    history = sel_history.sync()
    if not history['states']:
        toast.show(*sel_history.EMPTY)
    else:
        picked = ui.choose('Selection History', sel_history.list_rows(history),
                           ['#', 'Time', 'Items', 'Mostly', ''], multiselect=False,
                           checked=[history['cursor']], ok='Restore', width=600, height=520,
                           prompt='Newest first. Back (Alt+Left) and Forward (Alt+Right) step through '
                                  'the same list.')
        if picked is not None:
            index = picked[0]
            resolved, missing = sel_history.restore(history, index)
            message, detail = sel_history.describe(history, index, resolved, missing)
            if history['states'][index]['count'] and not resolved:
                toast.warning(message, 'None of its items are in the model any more.')
            else:
                toast.show('warning' if missing else 'success', message, detail)

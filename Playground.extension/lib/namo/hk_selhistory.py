# -*- coding: utf-8 -*-
"""Selection History hook: records each selection change (see namo.sel_history).

Runs on the UI thread after every debounced 'selection-changed'. Checks its on/off
switch first (cached in a session holder, so no file is read per event), keeps at most
5,000 item references per state and 50 states per document, and never raises.
"""


def handle(name, event):
    if name != 'selection-changed':
        return
    try:
        from namo import sel_history
        if not sel_history.settings().get('enabled', True):
            return
        from pynavis._api import Application
        document = Application.ActiveDocument
        if document is None:
            return
        if document.CurrentSelection.SelectedItems.Count == 0 and \
                not sel_history.settings().get('record_empty', False):
            history = sel_history.history_for(document)
            history['expected'] = None
            return
        state = sel_history.capture(document)
        sel_history.record(sel_history.history_for(document), state)
    except Exception as error:
        try:
            from namo import session
            session.log('warning', 'Selection History could not record a selection: %s' % error)
        except Exception:
            pass

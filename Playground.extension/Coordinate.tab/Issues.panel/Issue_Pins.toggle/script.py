# -*- coding: utf-8 -*-
"""Shows every open issue with a location as a pin in the view, or hides the pins.

On: pins are drawn with pynavis.overlay (one item per issue, tagged
'playground-issues:<id>'), each a real 1.2 m tall whatever the model's units; a session
flag makes hk_issuepins redraw them when another document opens, and an issue listener
redraws them after any edit made in this session. Off: every issue pin in the view is
cleared and both stop.

Pins that are on, by the button or by the session flag, decide what a click does, so a
click on Hide Pins always hides: the two can never disagree for longer than one click.
"""
from pynavis import overlay, script, toast

from namo import issueapi, issuestore


def _overlay_redraw():
    """Redraws the overlay through namo.overlayfix, so labels land on their points."""
    from namo import overlayfix
    return overlayfix.redraw()


def run():
    if script.get_toggle_state() or issueapi.pins_on():
        issueapi.unwatch_pins()
        issueapi.set_pins_on(False)
        issueapi.clear_pins()
        script.set_toggle_state(False)
        toast.info('Issue pins hidden')
        return
    doc = issuestore.active_doc()
    if doc is None or not issueapi.has_model(doc):
        script.set_toggle_state(False)
        toast.info('No model open', 'Open the model the issues belong to, then show the pins.')
        return
    store = issuestore.for_doc(doc)
    rows = store.list()
    if rows:
        count = issueapi.draw_pins(rows, doc)
    else:
        count = 0
        issueapi.clear_pins()
    if not _overlay_redraw():
        # Nothing can be drawn, so the button stays off rather than claim pins are showing.
        script.set_toggle_state(False)
        toast.error('Could not show the issue pins',
                    'The pyNavis view overlay is not loaded. Restart Navisworks, then try again.')
        return
    issueapi.set_pins_on(True)
    issueapi.watch_pins()
    script.set_toggle_state(True)
    if count:
        toast.success('%s issue pin%s shown' % ('{:,}'.format(count), '' if count == 1 else 's'),
                      'Open and in progress issues with a location.')
    elif not store.saved:
        toast.info('Issue pins are on', 'Save the model, then raise issues: their pins appear here.')
    elif not rows:
        toast.info('Issue pins are on', 'No issues yet. Raise one with Issue Stamps and its pin '
                   'appears here.')
    else:
        toast.info('Issue pins are on', 'No open issue has a location yet. Use Set pin in the '
                   'Issues panel, or Issue Stamps.')


run()

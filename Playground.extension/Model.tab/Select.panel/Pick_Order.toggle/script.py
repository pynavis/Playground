# -*- coding: utf-8 -*-
"""Turns Pick Order on (record the items you click, in order) or off.

Whether picks are being recorded decides, not the button's own on/off state, so the two
can never disagree (the way the shipped Hide Tabs toggle works). While it is on, the
running count sits on the banner along the bottom of the window.
"""
from pynavis import forms, script, toast

from namo import sel_pickorder


def run():
    if sel_pickorder.is_on():
        count = sel_pickorder.stop()
        script.set_toggle_state(False)
        toast.info('Pick order off: %s picked' % '{:,}'.format(count),
                   'Use Picked to select, number, export or color them in order.' if count else
                   'No items were picked.')
        return

    picks = sel_pickorder.load()
    if picks:
        choice = forms.ask_options(
            'This model already has a pick list of %s %s.' % (
                '{:,}'.format(len(picks)), 'item' if len(picks) == 1 else 'items'),
            ['Continue the list', 'Start a new list'], title='Pick Order')
        if choice is None:
            script.set_toggle_state(False)
            return                          # cancelled: say nothing
        if choice == 'Start a new list':
            sel_pickorder.clear()
    shown = sel_pickorder.start()           # puts the prompt on the banner
    script.set_toggle_state(True)
    if not shown:
        toast.info(*sel_pickorder.status_text(len(sel_pickorder.load())))


run()

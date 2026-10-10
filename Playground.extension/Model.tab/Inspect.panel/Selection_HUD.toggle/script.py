# -*- coding: utf-8 -*-
"""Turns the Selection HUD on and off: a live readout of the selection in the corner of the window."""
from pynavis import script, toast

from namo import hud, ui

DEFAULTS = {'sum_property': ''}


def run():
    if ui.is_runner():
        toast.info('The Selection HUD needs the Navisworks window', 'It cannot open under pynavis run.')
        return
    # The window decides, not the button's own on/off state, so the two can never
    # disagree (after a Reload the button forgets while the HUD is still showing).
    if hud.is_running():
        hud.stop()
        script.set_toggle_state(False)
        toast.info('Selection HUD off')
        return
    config = script.get_config(DEFAULTS)
    try:
        hud.start(config, ui.pinned_logger())
    except Exception as error:
        hud.stop()
        script.set_toggle_state(False)
        toast.error('Could not show the Selection HUD', str(error))
        return
    script.set_toggle_state(True)
    detail = 'Bottom left of the Navisworks window. Click again to hide it.'
    if config.get('sum_property'):
        detail = 'It also sums %s. Click again to hide it.' % config['sum_property']
    toast.info('Selection HUD on', detail)


run()

# -*- coding: utf-8 -*-
"""Chooses the property the Selection HUD sums over the selected objects."""
from pynavis import script, toast

from namo import data_common, hud, propindex, ui

DEFAULTS = {'sum_property': ''}
NOTHING = '(nothing)'


def run():
    if ui.is_runner():
        toast.info('Settings need the Navisworks window', 'They cannot open under pynavis run.')
        return
    values = script.get_config(DEFAULTS)
    rows = [{'cells': ['Sum nothing', '', ''], 'value': NOTHING}]
    if data_common.has_models():
        has_selection = data_common.selected_count() > 0
        for category, prop, count in propindex.property_choices(scope='selection' if has_selection else 'model'):
            rows.append({'cells': [category, prop, count], 'value': propindex.pair_text(category, prop)})
    current = values.get('sum_property') or NOTHING
    picked = ui.choose('Selection HUD', rows, ['Tab', 'Property', 'Items'], multiselect=False, checked=[current],
                       prompt='Sum which property over the selected objects? Lengths, areas and volumes show in '
                              'Playground report units.', ok='Use')
    if picked is None:
        return
    choice = '' if picked[0] == NOTHING else picked[0]
    values['sum_property'] = choice
    script.save_config(values)
    hud.update_config({'sum_property': choice})
    if choice:
        toast.success('Selection HUD sums %s' % choice)
    else:
        toast.success('Selection HUD sums nothing')


run()

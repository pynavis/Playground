# -*- coding: utf-8 -*-
"""Measures objects by zone (grid levels, rooms or areas, grid bays or tiles) and by group, with an Excel pivot."""
from pynavis import script, toast

from namo import fourd_common, items, qty_run, qty_ui, reports, takeoff, ui

TITLE = 'Zone Takeoff'
PIVOTS = [('Count', 'count'), ('Length', 'length'), ('Area', 'area'), ('Volume', 'volume'), ('Weight', 'weight')]


def run():
    if ui.is_runner():
        result = reports.run('zone_takeoff', script.get_config(takeoff.default_zone_config()),
                             interactive=False)
        toast.show(result['level'], result['message'], result['detail'])
        return
    doc = fourd_common.active_doc()
    if not fourd_common.has_models(doc):
        toast.info('No model is open', 'Open or append a model first.')
        return
    values = script.get_config(takeoff.default_zone_config())
    selected = items.selected(doc)
    sample = items.objects(selected if selected else items.roots(doc), budget=300)
    choices, specs = qty_ui.group_choices(takeoff.property_options(sample))
    levels = takeoff.grid_levels(doc)
    fields = qty_ui.zone_fields(values)
    fields += qty_ui.quick_fields(values, bool(selected), choices, zone=True)
    fields.append({'kind': 'choice', 'key': 'pivot', 'label': 'Pivot sheet shows', 'options': PIVOTS,
                   'default': values.get('pivot_measure') or 'count', 'fallback': 'count'})
    intro = ('The active grid has %s.' % fourd_common.plural(len(levels), 'level') if levels
             else 'The model has no grid levels; use zone objects, grid bays or tiles.')
    answer = ui.form(TITLE, fields, intro=intro, ok='Measure', width=580, validate=qty_ui.validate_zone)
    if answer is None:
        return
    config = qty_ui.config_from(answer, specs, zone=True)
    script.save_config(config)
    qty_run.run_zone(doc, config)


run()

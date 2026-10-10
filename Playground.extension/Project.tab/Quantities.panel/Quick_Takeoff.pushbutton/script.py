# -*- coding: utf-8 -*-
"""Counts and measures objects grouped by one or two properties, with subtotals, totals and Excel export."""
from pynavis import script, toast

from namo import fourd_common, items, qty_run, qty_ui, reports, takeoff, ui

TITLE = 'Quick Takeoff'


def run():
    if ui.is_runner():
        result = reports.run('quick_takeoff', script.get_config(takeoff.default_quick_config()),
                             interactive=False)
        toast.show(result['level'], result['message'], result['detail'])
        return
    doc = fourd_common.active_doc()
    if not fourd_common.has_models(doc):
        toast.info('No model is open', 'Open or append a model first.')
        return
    values = script.get_config(takeoff.default_quick_config())
    selected = items.selected(doc)
    sample = items.objects(selected if selected else items.roots(doc), budget=300)
    choices, specs = qty_ui.group_choices(takeoff.property_options(sample))
    fields = qty_ui.quick_fields(values, bool(selected), choices)
    answer = ui.form(TITLE, fields, ok='Measure', width=560, validate=qty_ui.validate_quick)
    if answer is None:
        return
    config = qty_ui.config_from(answer, specs)
    script.save_config(config)
    qty_run.run_quick(doc, config)


run()

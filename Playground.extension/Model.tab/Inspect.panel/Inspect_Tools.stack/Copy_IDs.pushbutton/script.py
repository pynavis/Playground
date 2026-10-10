# -*- coding: utf-8 -*-
"""Copies the identifiers of every selected element to the clipboard as a tab-separated table."""
from pynavis import script, toast

from namo import data_common, inspect, items, progress, propindex, ui

DEFAULTS = {'columns': list(inspect.ID_KEYS)}
PROGRESS_FROM = 2000        # selections larger than this get a progress window


def run():
    doc = data_common.active_doc()
    selected = items.selected(doc) if data_common.has_models(doc) else []
    if not selected:
        toast.info('Nothing selected', 'Select the elements whose IDs you want, then run Copy IDs again.')
        return
    columns = script.get_config(DEFAULTS).get('columns') or list(inspect.ID_KEYS)
    if len(selected) > PROGRESS_FROM and not ui.is_runner():
        records = progress.run('Copy IDs', lambda report: inspect.id_records(
            selected, doc, tick=data_common.stage(report, 0.0, 1.0, 'Reading %s')))
        if records is progress.CANCELLED:
            return
    else:
        records = inspect.id_records(selected, doc)
    headers, rows = inspect.id_table(records, columns)
    if not ui.copy(propindex.tsv(rows, headers)):
        toast.error('Could not copy', 'Another program is holding the clipboard; try again.')
        return
    toast.success('Copied %s %s' % ('{:,}'.format(len(rows)), 'row' if len(rows) == 1 else 'rows'),
                  ', '.join(headers))


run()

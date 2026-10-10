# -*- coding: utf-8 -*-
"""Options for KPI Export: a fixed folder for scheduled refreshes, the tables and formats."""
from pynavis import script, toast

from namo import rep_kpi_export, ui

DEFAULTS = dict(rep_kpi_export.default_config(), fixed_folder='', last_folder='')

values = script.get_config(dict(DEFAULTS))
fields = [
    {'kind': 'folder', 'key': 'fixed_folder', 'label': 'Always export to',
     'default': values.get('fixed_folder') or '',
     'hint': 'Blank: ask for a folder each time. Point Power BI at this folder for scheduled refresh.'},
    {'kind': 'text', 'key': 'name_template', 'label': 'Subfolder',
     'default': values.get('name_template') or '',
     'hint': '{file} KPI keeps one subfolder per model; blank writes straight into the folder.'},
    {'kind': 'multi', 'key': 'tables', 'label': 'Tables',
     'options': [(name.replace('_', ' ').capitalize(), name) for name in rep_kpi_export.TABLE_NAMES],
     'default': values.get('tables') or list(rep_kpi_export.TABLE_NAMES)},
    {'kind': 'multi', 'key': 'formats', 'label': 'Formats',
     'options': [('CSV (UTF-8 with BOM)', 'csv'), ('JSON', 'json')],
     'default': values.get('formats') or ['csv', 'json']},
    {'kind': 'int', 'key': 'max_clash_rows', 'label': 'Clash results, at most', 'min': 1000,
     'max': 5000000, 'default': values.get('max_clash_rows')},
]


def check(answers):
    if not answers['tables']:
        return {'tables': 'Tick at least one table.'}
    if not answers['formats']:
        return {'formats': 'Tick at least one format.'}
    return None


answers = ui.form('KPI Export options', fields, ok='Save', width=540, validate=check)
if answers is not None:
    values.update(answers)
    script.save_config(values)
    where = values['fixed_folder'] or 'a folder you choose each time'
    toast.success('Saved KPI Export options', 'Tables go to %s.' % where)

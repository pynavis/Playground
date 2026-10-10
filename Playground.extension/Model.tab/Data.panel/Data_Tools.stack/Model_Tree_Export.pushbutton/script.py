# -*- coding: utf-8 -*-
"""Exports the selection tree to a chosen depth as an Excel workbook, one sheet per model."""
from pynavis import script, toast

from namo import data_common, items, progress, reports, ui
from namo import rep_model_tree as rep

DEFAULTS = {'depth': rep.DEFAULT_DEPTH, 'models': [], 'open': True}


def run():
    if ui.is_runner():
        result = reports.run('model_tree', script.get_config(DEFAULTS), interactive=False)
        if not result.get('cancelled'):
            toast.show(result['level'], result['message'], result['detail'])
        return
    doc = data_common.active_doc()
    if not data_common.has_models(doc):
        data_common.no_model_toast()
        return
    values = script.get_config(DEFAULTS)
    names = [m['name'] for m in items.models(doc)]
    chosen = [n for n in values.get('models') or [] if n in names] or names
    fields = [{'kind': 'int', 'key': 'depth', 'label': 'Depth', 'default': int(values.get('depth') or 4),
               'min': 0, 'max': 20, 'hint': '0 is the model files themselves; 4 usually reaches Revit types.'},
              {'kind': 'multi', 'key': 'models', 'label': 'Models', 'options': names, 'default': chosen},
              {'kind': 'check', 'key': 'open', 'label': 'Open the workbook when done',
               'default': bool(values.get('open'))}]
    answer = ui.form('Model Tree Export', fields, ok='Export')
    if answer is None:
        return
    if not answer['models']:
        toast.info('No models ticked', 'Tick at least one model to export.')
        return
    config = {'depth': answer['depth'], 'models': answer['models'], 'open': bool(answer['open'])}
    script.save_config(config)
    path = data_common.ask_save('{file} - Model tree - {date}', 'xlsx', 'Export the model tree', doc)
    if path is None:
        return
    run_config = dict(config, path=path, models=[] if len(answer['models']) == len(names) else answer['models'])
    result = progress.run('Model Tree Export', lambda report: reports.run(
        'model_tree', run_config, doc=doc, interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])
    if config['open'] and result.get('paths') and result['level'] in ('success', 'warning'):
        try:
            ui.open_path(result['paths'][0])
        except Exception as error:
            toast.warning('Could not open the workbook', str(error))


run()

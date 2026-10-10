# -*- coding: utf-8 -*-
"""Exports chosen properties of the selected objects to Excel or CSV."""
from pynavis import forms, script, toast

from namo import data_common, items, progress, propindex, reports, templates, ui
from namo import rep_property_export as rep

TEMPLATES = 'property_export'
LAST = '(last used)'
DEFAULTS = {'properties': [], 'identity': list(rep.DEFAULT_IDENTITY), 'level': 'objects', 'format': 'xlsx',
            'open': True}
SAMPLE = 2000                # objects whose property names make up the choice list


def pick_template(store, values):
    """The saved choice to start from: the last run, or a named template."""
    names = store.names()
    if not names:
        return values
    choice = forms.select_from_list([LAST] + names, title='Property Exporter',
                                    prompt='Start from the last export or from a saved template?', checked=[LAST])
    if choice is None:
        return None
    if choice == LAST:
        return values
    saved = store.get(choice) or {}
    merged = dict(values)
    merged.update(saved)
    return merged


def pick_properties(doc, values):
    sample = propindex.scope_items('selection', 'objects', doc, budget=SAMPLE)
    choices = items.sample_properties(sample, limit=SAMPLE)
    if not choices:
        toast.info('No properties on the selection', 'Select elements that carry properties.')
        return None
    rows = [{'cells': [c, p, n], 'value': propindex.pair_text(c, p)} for c, p, n in choices]
    known = [r['value'] for r in rows]
    ticked = [propindex.pair_text(c, p) for c, p in values.get('properties') or []]
    missing = [t for t in ticked if t not in known]
    for text in missing:
        category, prop = propindex.split_pair(text)
        rows.append({'cells': [category, prop, 0], 'value': text})
    prompt = 'Tick the properties to export, one column each.'
    if sample.sampled:
        prompt += ' The list comes from the first %s selected objects.' % '{:,}'.format(SAMPLE)
    picked = ui.choose('Property Exporter', rows, ['Tab', 'Property', 'Selected objects with it'],
                       multiselect=True, checked=ticked, ok='Next', prompt=prompt)
    if picked is None:
        return None
    return [list(propindex.split_pair(text)) for text in picked]


def ask_options(values, count):
    fields = [
        {'kind': 'label', 'text': '%s selected. Rows are one per object, or one per geometry item.'
                                  % '{:,}'.format(count)},
        {'kind': 'radio', 'key': 'level', 'label': 'Rows', 'default': values.get('level') or 'objects', 'fallback': 'objects',
         'options': [(label, value) for value, label in propindex.LEVELS]},
        {'kind': 'multi', 'key': 'identity', 'label': 'Identity columns', 'default': values.get('identity') or [],
         'options': [(label, key) for key, label in rep.IDENTITY]},
        {'kind': 'radio', 'key': 'format', 'label': 'Format', 'inline': True,
         'default': values.get('format') or 'xlsx', 'fallback': 'xlsx', 'options': [('Excel workbook', 'xlsx'), ('CSV file', 'csv')]},
        {'kind': 'check', 'key': 'open', 'label': 'Open the file when done', 'default': bool(values.get('open'))},
        {'kind': 'text', 'key': 'template', 'label': 'Save these choices as a template (optional)',
         'placeholder': 'Template name'},
    ]
    return ui.form('Property Exporter', fields, ok='Export')


def run():
    if ui.is_runner():
        config = dict(script.get_config(DEFAULTS), scope='selection')
        result = reports.run('property_export', config, interactive=False)
        if not result.get('cancelled'):
            toast.show(result['level'], result['message'], result['detail'])
        return
    doc = data_common.active_doc()
    count = data_common.selected_count(doc) if data_common.has_models(doc) else 0
    if not count:
        toast.info('Nothing selected', 'Select the elements to export, then run Property Exporter again.')
        return
    store = templates.Templates(TEMPLATES)
    values = pick_template(store, script.get_config(DEFAULTS))
    if values is None:
        return
    properties = pick_properties(doc, values)
    if properties is None:
        return
    answer = ask_options(values, count)
    if answer is None:
        return
    config = {'properties': properties, 'identity': answer['identity'], 'level': answer['level'],
              'format': answer['format'], 'open': bool(answer['open'])}
    if not config['properties'] and not config['identity']:
        toast.info('Nothing to export', 'Tick at least one property or identity column.')
        return
    script.save_config(config)
    saved_as = None
    if answer.get('template', '').strip():
        try:
            saved_as = store.save(answer['template'].strip(), dict(config))
        except (ValueError, IOError, OSError) as error:
            toast.warning('Could not save the template', str(error))
    path = data_common.ask_save('{file} - Properties - {date}', config['format'], 'Export properties', doc)
    if path is None:
        return
    run_config = dict(config, scope='selection', path=path)
    result = progress.run('Property Exporter', lambda report: reports.run(
        'property_export', run_config, doc=doc, interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    detail = result['detail']
    if saved_as:
        detail = '%s. Saved as template %s.' % (detail, saved_as)
    toast.show(result['level'], result['message'], detail)
    if result['level'] in ('success', 'warning') and config['open'] and result.get('paths'):
        try:
            ui.open_path(result['paths'][0])
        except Exception as error:
            toast.warning('Could not open the file', str(error))


run()

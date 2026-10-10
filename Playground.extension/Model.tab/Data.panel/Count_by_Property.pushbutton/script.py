# -*- coding: utf-8 -*-
"""Counts objects by the values of one or two properties and lets you select a group."""
from pynavis import script, toast

from namo import data_common, items, progress, propindex, reports, ui
from namo import rep_count_by_property as rep

NONE = '(none)'
DEFAULTS = {'category': 'Element', 'property': 'Category', 'category2': '', 'property2': '',
            'scope': 'model', 'level': 'objects', 'xlsx': False}


def ask(doc, values):
    """The config for this run, or None when cancelled."""
    has_selection = data_common.selected_count(doc) > 0
    choices = propindex.property_choices(doc, scope='selection' if has_selection else 'model')
    if not choices:
        toast.info('No properties found', 'The items in scope carry no properties to count.')
        return None
    rows = [{'cells': [c, p, n], 'value': propindex.pair_text(c, p)} for c, p, n in choices]
    first = propindex.pair_text(values['category'], values['property'])
    picked = ui.choose('Count by Property', rows, ['Tab', 'Property', 'Items seen'], multiselect=False,
                       checked=[first], prompt='Count objects by which property?', ok='Next')
    if picked is None:
        return None
    category, prop = propindex.split_pair(picked[0])
    seconds = [(NONE, NONE)] + [(r['value'], r['value']) for r in rows if r['value'] != picked[0]]
    second = propindex.pair_text(values['category2'], values['property2']) if values.get('property2') else NONE
    fields = [{'kind': 'label', 'text': 'Counting by %s.' % picked[0]},
              {'kind': 'choice', 'key': 'second', 'label': 'Then by (optional, for a two-level pivot)',
               'options': seconds, 'default': second if second in [s[1] for s in seconds] else NONE}]
    fields += data_common.scope_fields(has_selection, values.get('scope'), values.get('level'))
    fields.append({'kind': 'check', 'key': 'xlsx', 'label': 'Also save an Excel workbook',
                   'default': bool(values.get('xlsx'))})
    answer = ui.form('Count by Property', fields, ok='Count')
    if answer is None:
        return None
    config = {'category': category, 'property': prop, 'category2': '', 'property2': '',
              'scope': answer['scope'], 'level': answer['level'], 'xlsx': bool(answer['xlsx'])}
    if answer['second'] != NONE:
        config['category2'], config['property2'] = propindex.split_pair(answer['second'])
    return config


def pick_group(result):
    groups = result.get('groups') or []
    if len(groups) < 2:
        return
    rows = []
    for index, group in enumerate(groups):
        rows.append({'cells': list(group['key']) + [group['count']], 'value': index})
    headers = rep.headers_of(result.get('config') or {})[:-1]
    picked = ui.choose('Select a group', rows, headers, multiselect=False,
                       prompt='Pick a group to select its items, or Cancel to keep the counts.', ok='Select')
    if picked is None:
        return
    group = groups[picked[0]]
    count = items.select(group['items'])
    toast.success('Selected %s %s' % ('{:,}'.format(count), 'item' if count == 1 else 'items'),
                  ' / '.join(group['key']))


def run():
    if ui.is_runner():
        result = reports.run('count_by_property', script.get_config(DEFAULTS), interactive=False)
        if not result.get('cancelled'):
            toast.show(result['level'], result['message'], result['detail'])
        return
    doc = data_common.active_doc()
    if not data_common.has_models(doc):
        data_common.no_model_toast()
        return
    values = script.get_config(DEFAULTS)
    config = ask(doc, values)
    if config is None:
        return
    script.save_config(config)
    if config['xlsx']:
        path = data_common.ask_save('{file} - Count by property - {date}', 'xlsx', 'Save the counts', doc)
        if path is None:
            return
        config['path'] = path
    result = progress.run('Count by Property', lambda report: reports.run(
        'count_by_property', config, doc=doc, interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])
    if result['level'] in ('success', 'warning'):
        result['config'] = config
        pick_group(result)


run()

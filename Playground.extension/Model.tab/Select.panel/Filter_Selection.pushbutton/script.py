# -*- coding: utf-8 -*-
"""Keeps or removes the selected items whose property passes a test, without a new search."""
from pynavis import script, toast

from namo import find_query, items, progress, rules, selecttools, ui

cfg = script.get_config(selecttools.FILTER_DEFAULTS)
selected = items.selected()


def ask_property():
    rows = [{'value': (c, p), 'cells': [c, p, n]} for c, p, n in selecttools.property_rows(selected)]
    if not rows:
        toast.info('Nothing to test', 'The selected items carry no properties.')
        return None
    picked = ui.choose('Filter Selection', rows, ['Category', 'Property', 'Sampled items carrying it'],
                       multiselect=False, checked=[(cfg['category'], cfg['property'])],
                       prompt='Choose the property to test. Listed from the first 200 selected '
                              'items and their elements.', width=660)
    return None if picked is None else picked[0]


def ask_test(category, prop):
    sample = selected[:2000]
    observed = [find_query.read(item, category, prop, True)[1] for item in sample]
    tally = find_query.tally_values([v for v in observed if v is not None])
    options = selecttools.value_options(tally)
    needs = [op for op, _label, need in rules.OPS if need]

    def validate(values):
        if values['op'] in needs and values['value'] == selecttools.OTHER and \
                not values['typed'].strip():
            return {'typed': 'Type the value to compare with.'}
        return None
    fields = [
        {'kind': 'label', 'text': '%s > %s, tested on %s selected items.' % (
            category, prop, '{:,}'.format(len(selected)))},
        {'kind': 'choice', 'key': 'op', 'label': 'Test',
         'options': [(label, op) for op, label in selecttools.filter_ops()], 'default': cfg['op'], 'fallback': None},
        {'kind': 'choice', 'key': 'value', 'label': 'Value', 'options': options,
         'default': options[0][1], 'enabled_if': ('op', needs),
         'hint': 'Values seen on the first %s items, most common first.' % '{:,}'.format(len(sample))},
        {'kind': 'text', 'key': 'typed', 'label': 'Typed value',
         'enabled_if': ('value', selecttools.OTHER),
         'hint': 'For between type 1 and 3; for is one of, separate values with commas.'},
        {'kind': 'radio', 'key': 'mode', 'label': 'Items that pass',
         'options': [('Keep them', 'keep'), ('Remove them', 'remove')], 'inline': True,
         'default': cfg['mode'], 'fallback': None},
        {'kind': 'check', 'key': 'use_object', 'default': cfg['use_object'],
         'label': "Test the element's properties when an item has none of its own"},
    ]
    answer = ui.form('Filter Selection', fields, ok='Filter', validate=validate, width=500)
    if answer is None:
        return None
    return answer, selecttools.picked_condition(category, prop, answer['op'], answer['value'],
                                               answer['typed'], tally)


if not selected:
    toast.info('Nothing selected', 'Select the items to filter first.')
else:
    picked = ask_property()
    if picked is not None:
        category, prop = picked
        asked = ask_test(category, prop)
        if asked is not None:
            answer, cond = asked
            keep = answer['mode'] == 'keep'
            script.save_config({'category': category, 'property': prop, 'op': answer['op'],
                                'mode': answer['mode'], 'use_object': answer['use_object']})
            if len(selected) > selecttools.FILTER_PROGRESS_OVER:
                kept = progress.run('Filtering the selection', lambda report: selecttools.run_filter(
                    selected, cond, keep, answer['use_object'], report))
            else:
                kept = selecttools.run_filter(selected, cond, keep, answer['use_object'])
            if kept is not progress.CANCELLED:
                level, message, detail = selecttools.filter_summary(
                    len(kept), len(selected), keep, rules.describe(cond))
                if 0 < len(kept) < len(selected):
                    items.select(kept)
                toast.show(level, message, detail)

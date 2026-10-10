# -*- coding: utf-8 -*-
"""Creates one search set per value of a property, named and foldered from templates."""
from pynavis import forms, script, toast
from pynavis._api import Application

from namo import find_batch, find_query, find_sets, items, progress, ui

cfg = script.get_config(find_batch.DEFAULTS)
document = Application.ActiveDocument


def pick_property(selected):
    if selected:
        sample = items.dedupe([items.object_of(i) for i in selected[:find_batch.SAMPLE_SIZE]])
        where = 'the selected elements'
    else:
        sample = find_query.sample_objects(items.roots(document), find_batch.SAMPLE_SIZE)
        where = '%d elements sampled across the model' % len(sample)
    rows = [{'value': (c, p), 'cells': [c, p, n]} for c, p, n in items.sample_properties(sample, None)]
    if not rows:
        toast.info('No properties found', 'The model has no element properties to make sets from.')
        return None
    picked = ui.choose('Batch Sets', rows, ['Category', 'Property', 'Elements carrying it'],
                       multiselect=False, checked=[(cfg['category'], cfg['property'])],
                       prompt='Choose the property to make one search set per value of. Listed from %s.'
                              % where, width=660)
    return None if picked is None else picked[0]


def collect_values(selected, category, prop):
    if selected:
        source = forms.ask_options('Collect the values of %s > %s from:' % (category, prop),
                                   ['The selection', 'The whole model'], title='Batch Sets')
        if source is None:
            return None
        if source == 'The selection':
            elements = items.dedupe([items.object_of(i) for i in selected])
            return progress.run('Collecting values', lambda report: find_batch.collect(
                elements, category, prop, report))
    return progress.run('Collecting values from the whole model', lambda report: find_batch.collect(
        find_batch.carriers(category, prop, doc=document), category, prop, report))


def ask_options(category, prop, tally):
    choices = find_batch.value_choices(tally)

    def validate(values):
        try:
            find_batch.extra_conditions(values['extra'])
        except ValueError as error:
            return {'extra': str(error)}
        if not values['values']:
            return {'values': 'Tick at least one value.'}
        return None
    return ui.form('Batch Sets', [
        {'kind': 'label', 'text': '%s > %s has %d values. Each ticked value becomes a search set.'
                                  % (category, prop, len(choices))},
        {'kind': 'multi', 'key': 'values', 'label': 'Values', 'options': choices,
         'default': [v for _l, v in choices]},
        {'kind': 'text', 'key': 'name_template', 'label': 'Set name', 'default': cfg['name_template'],
         'required': True, 'hint': 'Tokens: {value}, {property}, {category}, {count}.'},
        {'kind': 'text', 'key': 'folder_template', 'label': 'Folder',
         'default': cfg['folder_template'], 'hint': 'Same tokens; / makes subfolders; blank is the top level.'},
        {'kind': 'text', 'key': 'extra', 'label': 'Also require (optional)', 'default': cfg['extra'],
         'placeholder': 'Element > Category = Ducts',
         'hint': 'One condition every set adds, written as Category > Property, operator, value.'},
        {'kind': 'check', 'key': 'ignore_case', 'label': 'Ignore case when matching text values',
         'default': cfg['ignore_case']},
        {'kind': 'check', 'key': 'replace', 'label': 'Replace sets that already exist (otherwise skip them)',
         'default': cfg['replace']},
    ], ok='Create sets', validate=validate, width=520)


if document is None or document.Models.Count == 0:
    toast.info('Nothing to search', 'Open or append a model first.')
else:
    selected = items.selected(document)
    picked = pick_property(selected)
    if picked is not None:
        category, prop = picked
        values = collect_values(selected, category, prop)
        if values is not None and values is not progress.CANCELLED:
            tally = find_query.tally_values(values)
            if not find_batch.value_choices(tally):
                toast.info('No values to make sets from',
                           '%s > %s is blank or missing on every item searched.' % (category, prop))
            else:
                answer = ask_options(category, prop, tally)
                if answer is not None:
                    cfg.update({'category': category, 'property': prop,
                                'name_template': answer['name_template'].strip(),
                                'folder_template': answer['folder_template'].strip(),
                                'extra': answer['extra'].strip(), 'replace': answer['replace'],
                                'ignore_case': answer['ignore_case']})
                    script.save_config(cfg)
                    existing = find_sets.existing_index(find_sets.snapshot(document))
                    plan = find_batch.plan(category, prop, answer['values'], tally,
                                           cfg['name_template'], cfg['folder_template'],
                                           find_batch.extra_conditions(cfg['extra']), existing,
                                           cfg['replace'], cfg['ignore_case'])
                    outcome = progress.run('Creating search sets', lambda report: find_batch.apply(
                        plan, document, report))
                    created, replaced, skipped, errors, stopped = outcome
                    folder = plan[0]['folder'] if plan else ''
                    level, message, detail = find_batch.summary(created, replaced, skipped, errors, folder)
                    if not stopped:
                        toast.show(level, message, detail)
                    elif created or replaced:
                        # Cancel stops the batch but keeps what was written: say what exists.
                        toast.info(message, 'Stopped after %d of %d values.' % (
                            created + replaced + skipped, len(plan)))

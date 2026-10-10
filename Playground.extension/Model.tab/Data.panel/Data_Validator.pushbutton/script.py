# -*- coding: utf-8 -*-
"""Validates model properties against the JSON rule files in the team rules folder."""
from pynavis import script, toast

from namo import data_common, progress, reports, ui, validator

DEFAULTS = {'rule_files': [], 'scope': 'model', 'level': 'objects', 'xlsx': False, 'sets': False}


def pick_files(rulesets, values):
    rows = []
    for ruleset in rulesets:
        problems = len(ruleset.get('problems') or [])
        rows.append({'cells': [ruleset['name'], len(ruleset['rules']), ruleset['file'],
                               '%d %s' % (problems, 'problem' if problems == 1 else 'problems') if problems else ''],
                     'value': ruleset['file']})
    remembered = [f for f in values.get('rule_files') or [] if f in [r['file'] for r in rulesets]]
    checked = remembered or [r['file'] for r in rulesets]
    return ui.choose('Data Validator', rows, ['Rule set', 'Rules', 'File', 'Problems'], multiselect=True,
                     checked=checked, ok='Next',
                     prompt='Run which rule files? They live in %s (Shift+Click the button to open the folder).'
                            % validator.rules_folder())


def run():
    if ui.is_runner():
        result = reports.run('data_validation', script.get_config(DEFAULTS), interactive=False)
        if not result.get('cancelled'):
            toast.show(result['level'], result['message'], result['detail'])
        return
    doc = data_common.active_doc()
    if not data_common.has_models(doc):
        data_common.no_model_toast()
        return
    folder = validator.rules_folder()
    created = validator.ensure_starter(folder)
    rulesets = validator.load_folder(folder)
    if not rulesets:
        toast.warning('No rule files', 'Add .json rule files to %s, then run this again.' % folder)
        return
    values = script.get_config(DEFAULTS)
    files = pick_files(rulesets, values)
    if files is None:
        return
    has_selection = data_common.selected_count(doc) > 0
    fields = data_common.scope_fields(has_selection, values.get('scope'), values.get('level'))
    fields.append({'kind': 'check', 'key': 'xlsx', 'label': 'Also save an Excel workbook (every failure)',
                   'default': bool(values.get('xlsx'))})
    fields.append({'kind': 'check', 'key': 'sets', 'label': 'Save a selection set per failing rule (in %s)'
                                                            % validator.SET_FOLDER,
                   'default': bool(values.get('sets'))})
    intro = None
    if created:
        intro = 'A starter rule file was added to the rules folder; copy and edit it for your BEP.'
    answer = ui.form('Data Validator', fields, intro=intro, ok='Validate')
    if answer is None:
        return
    config = {'rule_files': files, 'scope': answer['scope'], 'level': answer['level'],
              'xlsx': bool(answer['xlsx']), 'sets': bool(answer['sets'])}
    script.save_config(config)
    if config['xlsx']:
        path = data_common.ask_save('{file} - Data validation - {date}', 'xlsx', 'Save the validation report', doc)
        if path is None:
            return
        config['path'] = path
    result = progress.run('Data Validator', lambda report: reports.run(
        'data_validation', config, doc=doc, interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])


run()

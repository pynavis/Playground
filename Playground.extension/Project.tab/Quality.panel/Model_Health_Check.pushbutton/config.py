# -*- coding: utf-8 -*-
"""Settings for Model Health Check: thresholds, report formats and where the reports go."""
from pynavis import script, toast

from namo import health, ui


def run():
    values = health.settings(script.get_config(health.DEFAULTS))
    fields = [
        {'kind': 'label', 'text': 'Distance of a model centre from 0,0,0', 'muted': True},
        {'kind': 'number', 'key': 'warn_km', 'label': 'Warn beyond', 'default': values['warn_km'],
         'min': 0.001, 'suffix': 'km', 'required': True},
        {'kind': 'number', 'key': 'fail_km', 'label': 'Fail beyond', 'default': values['fail_km'],
         'min': 0.001, 'suffix': 'km', 'required': True},
        {'kind': 'number', 'key': 'outlier_factor', 'label': 'Far-away object', 'default': values['outlier_factor'],
         'min': 2, 'max': 1000, 'suffix': 'x typical distance', 'required': True,
         'hint': 'An object farther than this many times the typical object distance from the model centre.'},
        {'kind': 'int', 'key': 'age_days', 'label': 'Old file after', 'default': values['age_days'],
         'min': 1, 'max': 3650, 'suffix': 'days', 'required': True},
        {'kind': 'int', 'key': 'item_budget', 'label': 'Items read per model', 'default': values['item_budget'],
         'min': 10000, 'max': 20000000, 'required': True,
         'hint': 'Counting stops here on very large models, and the report says so.'},
        {'kind': 'separator'},
        {'kind': 'multi', 'key': 'formats', 'label': 'Reports',
         'options': [('HTML report', 'html'), ('Excel workbook', 'xlsx')], 'default': values['formats']},
        {'kind': 'folder', 'key': 'folder', 'label': 'Save reports in', 'default': values['folder'],
         'hint': 'Blank: the document\'s folder, or Playground\'s reports folder for an unsaved document.'},
        {'kind': 'check', 'key': 'open_report', 'label': 'Open the HTML report when done',
         'default': values['open_report']},
    ]

    def check(answer):
        if answer.get('warn_km') is not None and answer.get('fail_km') is not None \
                and answer['fail_km'] < answer['warn_km']:
            return {'fail_km': 'Fail must be at least the warning distance.'}
        return None

    answer = ui.form('Health check settings', fields, validate=check)
    if answer is None:
        return
    saved = health.settings(answer)
    script.save_config(saved)
    toast.success('Health check settings saved',
                  'Warn at %s km, fail at %s km.' % (health.num_text(saved['warn_km']), health.num_text(saved['fail_km'])))


run()

# -*- coding: utf-8 -*-
"""Options for Clash to Issues: priority by penetration depth, due days, template."""
from pynavis import script, toast

from namo import issue_clash, issue_templates, ui

values = script.get_config(dict(issue_clash.DEFAULTS))
due = dict(issue_clash.DEFAULT_DUE)
due.update(values.get('due_days') or {})
bands = issue_clash.bands_of(values.get('bands'))
templates = [t['type'] for t in issue_templates.load()]
order = issue_clash.who_moves(values)
fields = [
    {'kind': 'choice', 'key': 'template', 'label': 'Issue template',
     'options': templates or ['Clash'], 'default': values.get('template') or 'Clash', 'fallback': None,
     'hint': 'Type, number prefix, title pattern and labels come from it.'},
    {'kind': 'label', 'muted': True,
     'text': 'Who moves follows Clash Assigner: %s. The trade lower in that list moves and gets '
             'the issue. Change it with Shift+Click on Clash Assigner.' % ' > '.join(order)},
    {'kind': 'textarea', 'key': 'bands', 'label': 'Priority by penetration depth', 'rows': 3,
     'default': '\n'.join('%g = %s' % (depth, priority) for depth, priority in bands),
     'hint': 'One per line: depth in metres = priority. Shallower clashes and clearance clashes '
             'are Low.'},
    {'kind': 'int', 'key': 'due_critical', 'label': 'Due after (Critical)', 'suffix': 'days',
     'min': 0, 'max': 365, 'default': due.get('Critical')},
    {'kind': 'int', 'key': 'due_high', 'label': 'Due after (High)', 'suffix': 'days', 'min': 0,
     'max': 365, 'default': due.get('High')},
    {'kind': 'int', 'key': 'due_normal', 'label': 'Due after (Normal)', 'suffix': 'days',
     'min': 0, 'max': 365, 'default': due.get('Normal')},
    {'kind': 'int', 'key': 'due_low', 'label': 'Due after (Low)', 'suffix': 'days', 'min': 0,
     'max': 365, 'default': due.get('Low'), 'hint': 'Leave a priority blank for no due date.'},
    {'kind': 'int', 'key': 'max_snapshots', 'label': 'Snapshots per run, at most', 'min': 0,
     'max': 5000, 'default': values.get('max_snapshots'),
     'hint': 'Each clash image takes a moment to render.'},
]


def check(answers):
    pairs, bad = issue_clash.parse_bands(answers['bands'])
    if bad or not pairs:
        return {'bands': 'Write each line as depth = priority, for example 0.05 = High.'}
    return None


answers = ui.form('Clash to Issues options', fields, ok='Save', width=560, validate=check)
if answers is not None:
    values['template'] = answers['template']
    values['bands'] = [[depth, priority] for depth, priority in issue_clash.bands_of(answers['bands'])]
    values['due_days'] = {'Critical': answers['due_critical'], 'High': answers['due_high'],
                          'Normal': answers['due_normal'], 'Low': answers['due_low']}
    values['max_snapshots'] = answers['max_snapshots'] or 0
    script.save_config(values)
    toast.success('Saved Clash to Issues options',
                  'Who moves (from Clash Assigner): %s.' % ' > '.join(order))

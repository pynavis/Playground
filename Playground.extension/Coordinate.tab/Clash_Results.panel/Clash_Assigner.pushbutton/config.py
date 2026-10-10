"""Options for Clash Assigner: who moves first, who stands for each trade, and reassignment."""
from pynavis import script, toast

from namo import clashassign, ui

DEFAULTS = {'tests': [], 'priority': list(clashassign.DEFAULT_PRIORITY), 'names': '',
            'reassign': False, 'mode': 'auto'}

values = script.get_config(DEFAULTS)
fields = [
    {'kind': 'textarea', 'key': 'priority', 'label': 'Who moves (highest priority first)',
     'default': '\n'.join(clashassign.priority_list(values['priority'])), 'rows': 7,
     'hint': 'One trade per line. In a clash, the trade lower in this list moves; a trade not '
             'listed moves before every listed one.'},
    {'kind': 'textarea', 'key': 'names', 'label': 'Assign trades to people', 'rows': 4,
     'default': values['names'] if isinstance(values['names'], str) else '',
     'hint': 'Optional, one per line: Mechanical = Jane Smith. Without a line the trade name is used.'},
    {'kind': 'check', 'key': 'reassign', 'label': 'Auto mode also reassigns items that already have an assignee',
     'default': values['reassign']},
]


def validate(answers):
    if not clashassign.priority_list(answers['priority']):
        return {'priority': 'List at least one trade.'}
    return None


answers = ui.form('Clash Assigner options', fields, ok='Save', width=520, validate=validate)
if answers is not None:
    values['priority'] = clashassign.priority_list(answers['priority'])
    values['names'] = answers['names']
    values['reassign'] = answers['reassign']
    script.save_config(values)
    toast.success('Saved Clash Assigner options', 'Who moves: %s.' % ' > '.join(values['priority']))

"""Options for Clash Namer: when to rebuild tests instead of renaming one by one."""
from pynavis import script, toast

from namo import clashname, ui

DEFAULTS = {'clash_template': clashname.DEFAULT_CLASH, 'group_template': clashname.DEFAULT_GROUP,
            'scope': 'clashes', 'tests': [], 'threshold': clashname.DEFAULT_THRESHOLD}

values = script.get_config(DEFAULTS)
fields = [
    {'kind': 'int', 'key': 'threshold', 'label': 'Rename one by one up to',
     'default': clashname.threshold_of(values),
     'min': 1, 'max': 1000000, 'suffix': 'names', 'required': True,
     'hint': 'Above this, each test is rebuilt once with the new names, which stays fast on '
             'big tests. One by one takes longer the larger the model is.'},
    {'kind': 'text', 'key': 'clash_template', 'label': 'Starting clash template',
     'default': values['clash_template']},
    {'kind': 'text', 'key': 'group_template', 'label': 'Starting group template',
     'default': values['group_template']},
]
answers = ui.form('Clash Namer options', fields, ok='Save')
if answers is not None:
    values.update(answers)
    script.save_config(values)
    toast.success('Saved Clash Namer options',
                  'One by one up to {:,} names, then a rebuild.'.format(values['threshold']))

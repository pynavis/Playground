# -*- coding: utf-8 -*-
"""Loads a saved Auto Attach rule template as the current rules, or deletes one."""
from pynavis import forms, script, toast

from namo import templates, ui

TITLE = 'Auto Attach templates'


def run():
    if ui.is_runner():
        return
    store = templates.Templates('auto_attach')
    names = store.names()
    if not names:
        toast.info('No saved rule templates', 'In Auto Attach, type a template name under the rules to save them.')
        return
    name = forms.select_from_list(names, title=TITLE, prompt='Pick a rule template.')
    if name is None:
        return
    action = forms.ask_options('What should happen to %s?' % name,
                               ['Use as the current rules', 'Delete the template'], title=TITLE)
    if action is None:
        return
    if action == 'Delete the template':
        if not forms.confirm('Delete the rule template %s for everyone who shares it?' % name, title=TITLE):
            return
        store.delete(name)
        toast.success('Deleted the rule template', name)
        return
    config = store.get(name) or {}
    values = script.get_config({'rules': '', 'mode': 'skip', 'leaf_only': True})
    values['rules'] = config.get('rules', '')
    script.save_config(values)
    toast.success('Loaded the rules of %s' % name, 'Click Auto Attach to preview them.')


run()

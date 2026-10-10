# -*- coding: utf-8 -*-
"""Edits the team's checklist templates: new, change, delete (the QA and safety examples can be copied)."""
from pynavis import forms, toast

from namo import checklists, ui

TITLE = 'Checklist templates'
NEW = '(new template)'


def validate_items(text):
    try:
        checklists.parse_template_text(text)
    except ValueError as error:
        return str(error)
    return None


def run():
    if ui.is_runner():
        return
    store = checklists.templates()
    team = store.names()
    every = checklists.available_templates()
    options = [NEW] + sorted(every)
    picked = forms.select_from_list(options, title=TITLE, prompt='Pick a template to change or copy.')
    if picked is None:
        return
    builtin = picked in checklists.BUILTIN and picked not in team
    config = every.get(picked) or {'text': '# Section\nFirst item to check'}
    text = checklists.template_text(checklists.template_items(config)) if picked != NEW else config['text']
    name = '' if picked == NEW else ('%s (team copy)' % picked if builtin else picked)
    fields = [
        {'kind': 'text', 'key': 'name', 'label': 'Name', 'default': name, 'required': True},
        {'kind': 'text', 'key': 'description', 'label': 'Description', 'default': config.get('description', '')},
        {'kind': 'textarea', 'key': 'text', 'label': 'Items, one per line; # starts a section', 'rows': 14,
         'default': text, 'validate': validate_items},
    ]
    if picked in team:
        fields.append({'kind': 'check', 'key': 'delete', 'label': 'Delete this template instead', 'default': False})
    intro = ('A built-in example: saving makes a team copy.' if builtin
             else 'Checklists already attached keep their answers; new items are added when you reopen them.')
    answer = ui.form(TITLE, fields, intro=intro, ok='Save', width=600)
    if answer is None:
        return
    if answer.get('delete'):
        if not forms.confirm('Delete the checklist template %s for everyone who shares it?' % picked, title=TITLE):
            return
        store.delete(picked)
        toast.success('Deleted the checklist template', picked)
        return
    if picked in team and answer['name'].strip() != picked:
        store.delete(picked)
    stored = store.save(answer['name'], {'text': answer['text'], 'description': answer['description']})
    count = len(checklists.parse_template_text(answer['text']))
    toast.success('Saved the checklist template %s' % stored, '%d items.' % count)


run()

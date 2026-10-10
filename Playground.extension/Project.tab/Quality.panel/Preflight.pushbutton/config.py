# -*- coding: utf-8 -*-
"""Edits, creates and deletes preflight profiles (shared with the team when Playground uses a shared folder)."""
from pynavis import forms, toast

from namo import preflight, ui

NEW = '__new_profile__'


def run():
    items = []
    for name in preflight.profile_names():
        built_in = name == preflight.DEFAULT_NAME and not preflight.is_saved(name)
        items.append(('%s (built in)' % name if built_in else name, name))
    items.append(('New profile', NEW))
    picked = forms.select_from_list(items, title='Preflight profiles',
                                    prompt='Pick a profile to edit, or start a new one.')
    if picked is None:
        return
    if picked == NEW:
        base = preflight.normalize_profile(preflight.DEFAULT_PROFILE)
        base['name'] = 'New profile'
        existing = False
    else:
        base = preflight.load_profile(picked) or preflight.normalize_profile(preflight.DEFAULT_PROFILE)
        existing = preflight.is_saved(picked)
    label = ('Go back to the built-in Standard profile' if picked == preflight.DEFAULT_NAME
             else 'Delete this profile')
    values = ui.form('Preflight profile', preflight.profile_form_fields(base, existing, label),
                     ok='Save', width=520)
    if values is None:
        return
    if values.get('delete'):
        preflight.delete_profile(picked)
        if picked == preflight.DEFAULT_NAME:
            toast.success('Standard is back to the built-in checks')
        else:
            toast.success('Deleted profile %s' % picked)
        return
    profile = preflight.profile_from_form(values, base)
    try:
        stored = preflight.save_profile(profile)
    except (IOError, OSError, ValueError) as error:
        toast.error('Could not save the profile', str(error))
        return
    detail = '%s.' % preflight.describe_profile(profile)
    if existing and stored.lower() != str(picked).lower():
        detail += ' %s is still there under its old name.' % picked
    toast.success('Saved profile %s' % stored, detail)


run()

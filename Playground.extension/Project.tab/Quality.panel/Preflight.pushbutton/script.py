# -*- coding: utf-8 -*-
"""Checks the document against a preflight profile and lists every check as pass, warning or fail."""
from pynavis import forms, output, script, toast

from namo import preflight, progress


def run():
    config = script.get_config({'profile': preflight.DEFAULT_NAME})
    names = preflight.profile_names()
    name = names[0]
    if len(names) > 1:
        last = config.get('profile') if config.get('profile') in names else names[0]
        name = forms.select_from_list(names, title='Preflight',
                                      prompt='Check the document against which profile?',
                                      checked=[last])
        if name is None:
            return
    profile = preflight.load_profile(name)
    if profile is None:
        toast.error('Profile %s is gone' % name, 'Pick another profile, or save one with Shift+Click.')
        return
    checks = progress.run('Preflight', lambda report: preflight.run_profile(profile, progress=report),
                          'Reading the models')
    if checks is progress.CANCELLED:
        return
    script.save_config({'profile': name})
    output.print_html(preflight.output_html(checks, profile['name'], preflight.document_name()))
    level, message, detail = preflight.toast_text(checks)
    toast.show(level, message, detail)


run()

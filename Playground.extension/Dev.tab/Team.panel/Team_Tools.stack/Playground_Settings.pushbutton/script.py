# -*- coding: utf-8 -*-
"""Edits the settings every Playground tool shares."""
from pynavis import toast

from namo import config, paths, team_settings, ui

if globals().get('__runner__'):
    toast.info('The settings window needs Navisworks', 'It cannot open under pynavis run.')
else:
    values = ui.form('Playground Settings', team_settings.fields(config.load()), ok='Save', width=560,
                     validate=lambda v: team_settings.validate(v))
    if values is not None:
        try:
            saved = config.save(team_settings.to_config(values))
        except (IOError, OSError) as error:
            toast.error('Could not save the settings', str(error))
        else:
            paths.forget_reachability()
            toast.success('Saved the Playground settings', team_settings.summary(saved))

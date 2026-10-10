# -*- coding: utf-8 -*-
"""Manages the issue templates new issues, stamps and Clash to Issues start from."""
from pynavis import toast

from namo import issue_templates, ui

if ui.is_runner():
    toast.info('Issue Templates needs the Navisworks window', 'It cannot run under pynavis run.')
else:
    try:
        issue_templates.open_editor()
    except (IOError, OSError) as error:
        toast.error('Could not save the templates', '%s Check the shared folder, then try again.' % error)

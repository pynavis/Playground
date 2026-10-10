# -*- coding: utf-8 -*-
"""Runs the Environment Doctor and copies its report as plain text (for a support email)."""
import datetime

from pynavis import toast

from namo import doctor, ui

results = doctor.checks(doctor.gather())
text = doctor.text_report(results, datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
if ui.copy(text):
    level, message = doctor.headline(results)
    toast.success('Environment report copied', '%s. Paste it into an email or a ticket.' % message)
else:
    toast.error('The clipboard is busy', 'Another program is holding it; try again.')

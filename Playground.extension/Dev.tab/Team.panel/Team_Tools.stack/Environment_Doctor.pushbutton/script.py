# -*- coding: utf-8 -*-
"""Checks everything pyNavis and Playground depend on and reports pass, warning or fail."""
from pynavis import toast

from namo import doctor

results = doctor.checks(doctor.gather())
doctor.print_report(results)
level, message = doctor.headline(results)
toast.show(level, message, 'The details are in the output window.')

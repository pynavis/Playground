# -*- coding: utf-8 -*-
"""Lists the appended models live: visibility, type, units, file time, out-of-date files and item counts.

All of the behaviour is in lib/namo/sourcefiles.py. Reload re-runs this script
against fresh controls; attach() first detaches the previous run's timer and event
subscriptions, which it keeps in a session holder, the way the shipped Viewpoint
Tracker does.
"""
from namo import sourcefiles

from pynavis import script

sourcefiles.attach(__pane__, script.get_logger())

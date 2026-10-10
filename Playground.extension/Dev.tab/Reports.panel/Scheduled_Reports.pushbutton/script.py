# -*- coding: utf-8 -*-
"""Creates, runs and removes Windows scheduled tasks that run report templates on a model with no one at the desk."""
from pynavis import script

from namo import sched_ui, xchg_common


def run():
    if xchg_common.under_runner():
        return
    try:
        from pynavis import doc as nwdoc
        document = nwdoc.get_doc()
    except Exception:
        document = None                 # no model open: schedules can still be managed
    sched_ui.open_window(document, script.get_bundle_file('scheduled_runner.py'))


run()

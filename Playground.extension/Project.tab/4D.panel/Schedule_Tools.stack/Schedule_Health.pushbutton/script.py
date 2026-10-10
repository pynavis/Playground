# -*- coding: utf-8 -*-
"""Checks the TimeLiner schedule (attachments, dates, overlaps, coverage) and opens a scored report."""
from pynavis import script, toast

from namo import fourd_common, progress, reports, ui

TITLE = 'Schedule Health'
DEFAULTS = {'coverage': True, 'create_set': True}


def run():
    values = script.get_config(DEFAULTS)
    if ui.is_runner():
        result = reports.run('schedule_health', values, interactive=False)
        toast.show(result['level'], result['message'], result['detail'])
        return
    doc = fourd_common.active_doc()
    config = fourd_common.report_config(reports.default_config('schedule_health'),
                                        fourd_common.default_path(doc, 'Schedule health', 'html'))
    config.update(values)
    result = progress.run(TITLE, lambda report: reports.run('schedule_health', config, doc=doc,
                                                            interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])
    if result['level'] in ('success', 'warning') and result['paths']:
        fourd_common.open_file(result['paths'][0])


run()

# -*- coding: utf-8 -*-
"""Exports every TimeLiner task to a styled Excel workbook with outline, dates, status and attachments."""
from pynavis import toast

from namo import fourd_common, progress, reports, ui

TITLE = 'TimeLiner Export'


def run():
    if ui.is_runner():
        result = reports.run('timeliner_export', {}, interactive=False)
        toast.show(result['level'], result['message'], result['detail'])
        return
    doc = fourd_common.active_doc()
    path = fourd_common.ask_save(doc, 'TimeLiner tasks', 'xlsx', 'Export TimeLiner tasks')
    if path is None:
        return
    config = fourd_common.report_config(reports.default_config('timeliner_export'), path)
    result = progress.run(TITLE, lambda report: reports.run('timeliner_export', config, doc=doc,
                                                            interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])
    if result['level'] == 'success' and result['paths']:
        fourd_common.open_file(result['paths'][0])


run()

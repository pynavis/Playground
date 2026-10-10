# -*- coding: utf-8 -*-
"""Opens the inspection checklist of the current saved viewpoint: Pass, Fail or N/A per item, notes and sign-off."""
from pynavis import toast

from namo import checklists, config as namo_config, field_checklistwin, fourd_common, ui


def run():
    if ui.is_runner():
        toast.info('Field Checklists is a window', 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    views = checklists.viewpoint_list(doc)
    if not views:
        toast.info('No saved viewpoints', 'Save a viewpoint for each place you inspect, then open Field Checklists.')
        return
    records = checklists.records_store(doc)
    field_checklistwin.show(doc, records, views, checklists.available_templates(),
                            checklists.current_guid(doc), namo_config.user_name())
    if records.note:
        toast.info('Checklists from local data', records.note)


run()

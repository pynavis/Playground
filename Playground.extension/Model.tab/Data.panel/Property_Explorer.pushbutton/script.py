# -*- coding: utf-8 -*-
"""Opens Property Explorer: every category, property and value of the scanned items in three linked lists."""
from pynavis import script, toast

from namo import data_common, data_explorer, propindex, ui


def run():
    if ui.is_runner():
        toast.info('Property Explorer needs the Navisworks window', 'It cannot open under pynavis run.')
        return
    doc = data_common.active_doc()
    if not data_common.has_models(doc):
        data_common.no_model_toast()
        return
    existing = ui.Modeless.get(data_explorer.KEY)
    if existing is not None:
        existing.Activate()
        return
    me = script.bind()
    logger = ui.pinned_logger()
    entry = propindex.cached(doc)
    if entry is None:
        entry = data_explorer.scan_flow(me, doc)
        if entry is None:
            return
    data_explorer.show(entry, me, logger)
    if entry.get('sampled'):
        toast.warning('Scan sampled', 'It stopped at %s items; Rescan with a larger budget to read them all.'
                      % '{:,}'.format(entry['index'].total))


run()

# -*- coding: utf-8 -*-
"""Writes custom properties to the selection, or from a spreadsheet matched to model items."""
from pynavis import script, toast

from namo import data_common, data_write, ui


def run():
    if ui.is_runner():
        toast.info('Bulk Property Writer needs the Navisworks window', 'It cannot open under pynavis run.')
        return
    doc = data_common.active_doc()
    if not data_common.has_models(doc):
        data_common.no_model_toast()
        return
    data_write.bulk_flow(script.bind(), doc)


run()

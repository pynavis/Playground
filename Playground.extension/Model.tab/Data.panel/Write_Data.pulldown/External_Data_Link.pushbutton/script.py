# -*- coding: utf-8 -*-
"""Manages spreadsheet links that write their columns to custom tabs on matched objects."""
from pynavis import script, toast

from namo import data_common, data_write, ui


def run():
    if ui.is_runner():
        toast.info('External Data Link needs the Navisworks window', 'It cannot open under pynavis run.')
        return
    doc = data_common.active_doc()
    if not data_common.has_models(doc):
        data_common.no_model_toast()
        return
    data_write.link_flow(script.bind(), doc)


run()

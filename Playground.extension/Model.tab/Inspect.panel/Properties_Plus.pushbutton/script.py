# -*- coding: utf-8 -*-
"""Opens Properties Plus, a window that follows the selection and compares pinned properties across it."""
from pynavis import script, toast

from namo import data_common, insp_propsplus, ui


def run():
    if ui.is_runner():
        toast.info('Properties Plus needs the Navisworks window', 'It cannot open under pynavis run.')
        return
    doc = data_common.active_doc()
    if not data_common.has_models(doc):
        data_common.no_model_toast()
        return
    insp_propsplus.show(script.bind(), ui.pinned_logger())


run()

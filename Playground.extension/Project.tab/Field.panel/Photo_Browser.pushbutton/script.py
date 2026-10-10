# -*- coding: utf-8 -*-
"""Opens the photo pins of this model as thumbnails grouped by level, grid or object, with Go to and a report."""
from pynavis import toast

from namo import field_photobrowser, fourd_common, photopins, ui


def run():
    if ui.is_runner():
        toast.info('Photo Browser is a window', 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    records = photopins.store(doc)
    pins = records.list()
    if not pins:
        toast.info('No photo pins in this model', 'Use Photo Pins to pin site photos to points in the model.')
        return
    field_photobrowser.show(doc, records, pins)
    if records.note:
        toast.info('Photo pins from local data', records.note)


run()

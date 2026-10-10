# -*- coding: utf-8 -*-
"""Starts or stops watching the appended models' files for changes."""
from namo import folderwatch

from pynavis import script, toast


def run():
    if folderwatch.is_on():
        folderwatch.stop(save=True)
        script.set_toggle_state(False)
        toast.info('Folder Watch is off')
        return
    result = folderwatch.start(logger=script.get_logger())
    script.set_toggle_state(bool(result['ok']))
    toast.show(result['level'], result['message'], result['detail'])


run()

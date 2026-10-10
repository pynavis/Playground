# -*- coding: utf-8 -*-
"""Shows the selected item's model file, or this document's file, in Windows Explorer."""
import os

from pynavis import forms, toast

from namo import data_common, inspect, items, ui


def show(path):
    ui.show_in_explorer(path)
    toast.success('Opened in Explorer', path)


def document_file(doc):
    path = str(doc.FileName or '')
    if not path:
        toast.info('This document is not saved yet', 'Save it, or select an item to find its model file.')
        return
    if not os.path.exists(path):
        toast.warning('The document file is gone', path)
        return
    show(path)


def run():
    doc = data_common.active_doc()
    selected = items.selected(doc) if data_common.has_models(doc) else []
    if not selected:
        document_file(doc)
        return
    model = items.model_of(selected[0])
    if model is None:
        toast.info('No model file for this item', 'Select an item inside an appended model.')
        return
    targets = inspect.explorer_targets(model.FileName, model.SourceFileName, os.path.exists)
    if not targets:
        toast.info('No model file for this item', 'Its model carries no file name.')
        return
    present = [t for t in targets if t[2]]
    if not present:
        toast.warning('The model file is gone', targets[0][1])
        return
    if len(present) == 1:
        gone = [t for t in targets if not t[2]]
        ui.show_in_explorer(present[0][1])
        if gone:
            toast.warning('Opened the %s' % present[0][0].lower(), '%s is gone: %s' % (gone[0][0], gone[0][1]))
        else:
            toast.success('Opened in Explorer', present[0][1])
        return
    if ui.is_runner():
        show(present[0][1])
        return
    labels = ['%s: %s' % (label, os.path.basename(path)) for label, path, _present in present]
    choice = forms.ask_options('Show which file in Explorer?', labels, title='Open in Explorer')
    if choice is None:
        return
    show(present[labels.index(choice)][1])


run()

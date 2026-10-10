# -*- coding: utf-8 -*-
"""Writes the selected objects to an IFC4 file with storeys, classes, colours, GlobalIds and property sets."""
import os

from pynavis import doc as nwdoc
from pynavis import script, toast

from namo import config, ifc, ifcexport, items, progress, store, ui, xchg_common

NAME_TEMPLATE = '{file} - {date}'
IFC_FILTER = 'IFC files (*.ifc)|*.ifc'


def class_overrides():
    """The team's category -> IFC class overrides (Shift+Click to edit)."""
    return ifcexport.stored_overrides(store.Store('ifc-class-map', scope='global').load({}))


def run():
    if xchg_common.under_runner():
        return
    document = nwdoc.get_doc()
    selected = items.selected(document)
    if not selected:
        toast.info('Nothing selected', 'Select the objects to export, then run IFC Exporter again.')
        return
    values = dict(ifcexport.DEFAULT_OPTIONS)
    values.update(script.get_config(ifcexport.DEFAULT_OPTIONS))
    stem = os.path.splitext(xchg_common.doc_title(document))[0]
    fields = ifcexport.form_fields(values, config.get('project_name') or stem, stem)
    answer = ui.form('IFC exporter', fields, ok='Export', width=560, intro=ifcexport.FORM_INTRO)
    if answer is None:
        return
    values.update(answer)
    script.save_config(dict((k, values[k]) for k in ifcexport.DEFAULT_OPTIONS))
    path = xchg_common.ask_save(document, NAME_TEMPLATE, '.ifc', IFC_FILTER, 'Export IFC')
    if path is None:
        return
    overrides = class_overrides()
    seed = (xchg_common.doc_path(document) or xchg_common.doc_title(document)).lower()

    def work(report):
        read = ifcexport.collect(selected, document, values, progress=lambda f, label: report(f * 0.6, label))
        if not read['records']:
            return read, None, []
        report(0.62, 'Placing objects on storeys')
        model, dropped = ifcexport.model_for(read, document, values, os.path.basename(path), seed, overrides)
        if not model['elements']:
            return read, model, dropped
        ifc.write(path, model, progress=lambda f, label: report(0.65 + 0.35 * f, label))
        return read, model, dropped

    try:
        outcome = progress.run('Exporting IFC', work)
    except (IOError, OSError) as error:
        toast.error('Could not write the IFC file', '%s. Close it in any program that has it open, then try again.'
                    % error)
        return
    if outcome is progress.CANCELLED:
        return
    read, model, dropped = outcome
    xchg_common.show_skipped('IFC exporter', read['skipped'], dropped)
    written = len(model['elements']) if model else 0
    storeys = len(set(e['storey'] for e in model['elements'])) if written else 0
    level, message, detail = ifcexport.summary(written, len(read['skipped']) + len(dropped), read['sampled'],
                                               storeys)
    if written:
        detail = xchg_common.where_text(detail, path)
    toast.show(level, message, detail)
    if written:
        xchg_common.reveal(path)


run()

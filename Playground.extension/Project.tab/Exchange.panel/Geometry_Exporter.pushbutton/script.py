# -*- coding: utf-8 -*-
"""Exports the selected objects' triangles to glTF (.glb), OBJ, STL or DXF 3D faces."""
import os

from pynavis import doc as nwdoc
from pynavis import script, toast

from namo import items, meshexport, paths, progress, ui, xchg_common

NAME_TEMPLATE = '{file} - Geometry - {date}'


def property_options(selected):
    """Chooser options for the property names on the first objects of the selection."""
    try:
        sample = items.objects(selected, budget=150)
        names = items.sample_properties(sample, limit=150)
    except Exception:
        return []
    return [meshexport.property_option(cat, prop) for cat, prop, _n in names][:400]


def run():
    if xchg_common.under_runner():
        return
    document = nwdoc.get_doc()
    selected = items.selected(document)
    if not selected:
        toast.info('Nothing selected', 'Select the objects to export, then run Geometry Exporter again.')
        return
    doc_units = str(document.Units)
    values = dict(meshexport.DEFAULT_OPTIONS)
    values.update(script.get_config(meshexport.DEFAULT_OPTIONS))
    fields = meshexport.form_fields(values, doc_units, property_options(selected))
    answer = ui.form('Geometry exporter', fields, ok='Export', width=560)
    if answer is None:
        return
    values.update(answer)
    script.save_config(dict((k, values[k]) for k in meshexport.DEFAULT_OPTIONS))
    fmt = values['format']
    ext = meshexport.EXTENSIONS[fmt]
    path = xchg_common.ask_save(document, NAME_TEMPLATE, ext, meshexport.FILTERS[fmt], 'Export geometry')
    if path is None:
        return
    pairs = meshexport.property_pairs(values.get('properties'))
    title = xchg_common.doc_title(document)
    y_up = fmt == 'glb' or (fmt == 'obj' and values['obj_y_up'])

    def work(report):
        read = meshexport.read_objects(selected, per_object=values['per_object'], total=values['total'],
                                       progress=lambda f, label: report(f * 0.85, label),
                                       identity=values['identity'] and fmt == 'glb',
                                       property_pairs=pairs if fmt == 'glb' else None, doc_units=doc_units)
        records = read['records']
        if not records:
            return read, [], [], []
        shift = meshexport.local_origin(meshexport.union_box(records), doc_units) if values['shift'] else None
        report(0.87, 'Preparing %s objects' % '{:,}'.format(len(records)))
        meshes, dropped = meshexport.build_meshes(records, fmt, doc_units, shift, values['units'],
                                                  values['obj_y_up'])
        _scale, word = meshexport.target_units(fmt, values['units'], doc_units)
        header = ['Source: %s' % title, 'Units: %s' % word, 'Up axis: %s' % ('Y' if y_up else 'Z')]
        extras = {'source': title, 'units': 'metres', 'up': 'Y', 'model_units': doc_units}
        if shift:
            header.append('Local origin subtracted (model units): %s' % ', '.join(
                meshexport.num_text(v, 12) for v in shift))
            extras['local_origin_model_units'] = list(shift)
        report(0.94, 'Writing %s' % os.path.basename(path))
        written = meshexport.write_files(path, fmt, meshes, title=title, extras=extras,
                                         layer_by=values['layers'], header_lines=header)
        if shift:
            note = meshexport.offset_note(shift, doc_units, fmt, word, title, axes_y_up=y_up)
            written.append(paths.atomic_write_text(meshexport.sidecar_path(path), note))
        report(1.0, 'Done')
        return read, meshes, dropped, written

    try:
        outcome = progress.run('Exporting geometry', work)
    except (IOError, OSError) as error:
        toast.error('Could not write the file', '%s. Close it in any program that has it open, then try again.' % error)
        return
    if outcome is progress.CANCELLED:
        return
    read, meshes, dropped, written = outcome
    xchg_common.show_skipped('Geometry exporter', read['skipped'], dropped)
    level, message, detail = meshexport.summary(meshes, read['skipped'], dropped, fmt, read['sampled'])
    if written:
        # Say where the file is whatever else there is to say, and show it in Explorer.
        detail = written[0] if level == 'success' else xchg_common.where_text(detail, written[0])
    toast.show(level, message, detail)
    if written:
        xchg_common.reveal(written[0])


run()

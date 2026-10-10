# -*- coding: utf-8 -*-
"""Weighs the selected objects and marks their combined centre of gravity in the view."""
from pynavis import script, toast

from namo import cog, fourd_common, items, progress, ui, units

TITLE = 'COG Calculator'
KEY = 'playground-cog'


def measure(objects, doc_units, values, report):
    table, _errors = cog.parse_densities(values.get('densities'))
    out = []
    for index, obj in enumerate(objects):
        report(index / float(len(objects) or 1), 'Measuring %s of %s objects'
               % ('{:,}'.format(index + 1), '{:,}'.format(len(objects))))
        out.append(cog.measure_object(obj, doc_units, table, values.get('fill_factor') or 0.6,
                                      values.get('default_density')))
    return out


def show(doc, results, combined, imperial, doc_units):
    unit = units.doc_unit_symbol(doc_units)
    volume = 'ft³' if imperial else 'm³'
    headers = ['Object', 'Mass', 'Volume (%s)' % volume, 'Density (kg/m³)', 'X (%s)' % unit,
               'Y (%s)' % unit, 'Z (%s)' % unit, 'Method']

    def copy(selected):
        if combined['cog'] is None:
            toast.info('No centre of gravity', 'No object has a weight.')
            return
        text = cog.format_point(combined['cog'])
        ui.copy(text)
        toast.success('Centre of gravity copied', '%s %s' % (text, unit))

    def select(selected):
        count = items.select([results[i]['item'] for i in selected], doc=doc)
        toast.success('Selected %s' % fourd_common.plural(count, 'object'))

    def export(selected):
        path = fourd_common.ask_save(doc, 'Centre of gravity', 'xlsx', 'Export the weights')
        if path is None:
            return
        try:
            cog.write_xlsx(path, results, combined, imperial, doc_units, 'Centre of gravity')
        except (IOError, OSError) as error:
            toast.error('Could not write the workbook', 'Close it in Excel, then try again. %s' % error)
            return
        toast.success('Exported the weights', path)
        fourd_common.open_file(path)

    def remove_marker(selected):
        cog.clear_marker()
        toast.success('Removed the COG marker')

    if combined['cog'] is not None:
        status = 'Total %s, centre of gravity %s %s' % (cog.format_mass(combined['mass'], imperial),
                                                       cog.format_point(combined['cog']), unit)
    else:
        status = 'No object has a weight.'
    actions = [{'label': 'Copy COG', 'fn': copy, 'needs_selection': False, 'primary': True},
               {'label': 'Select objects', 'fn': select},
               {'label': 'Export to Excel', 'fn': export, 'needs_selection': False},
               {'label': 'Remove marker', 'fn': remove_marker, 'needs_selection': False}]
    ui.Modeless.close(KEY)
    ui.table_window('Centre of gravity', headers, cog.result_rows(results, imperial, doc_units),
                    actions=actions, modeless=True, key=KEY, status=status, width=980)


def run():
    if ui.is_runner():
        toast.info('%s works on the selection' % TITLE, 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    # Stop the walk one past the limit: a whole-model selection must not be walked in full
    # just to be refused.
    objects = items.objects(items.selected(doc), budget=cog.MAX_OBJECTS + 1)
    if not objects:
        toast.info('Nothing selected', 'Select the objects to weigh, then run COG Calculator.')
        return
    if len(objects) > cog.MAX_OBJECTS:
        toast.info('Too many objects selected', 'Select at most %s objects; more are selected.'
                   % '{:,}'.format(cog.MAX_OBJECTS))
        return
    values = script.get_config(cog.DEFAULTS)
    doc_units = str(doc.Units)
    imperial = units.is_imperial(doc_units)
    results = progress.run(TITLE, lambda report: measure(objects, doc_units, values, report))
    if results is progress.CANCELLED:
        return
    combined = cog.combine([(r['mass_kg'], r['centroid']) for r in results])
    estimated = len([r for r in results if r['method'] == 'bbox'])
    weightless = len([r for r in results if r['mass_kg'] is None])
    notes = []
    if estimated:
        notes.append('%s estimated from bounding boxes' % fourd_common.plural(estimated, 'object'))
    if weightless:
        notes.append('%s without a weight' % fourd_common.plural(weightless, 'object'))
    if combined['cog'] is None:
        toast.warning('No weight found', 'No object matched a density or carries a weight. '
                      'Shift+Click to set densities or a default.')
    else:
        to_m = units.to_meters(1.0, doc_units)
        drawn = cog.show_marker(combined['cog'], combined['mass'], imperial,
                                cog.marker_size(items.bbox(objects), to_m))
        detail = '%s %s' % (cog.format_point(combined['cog']), units.doc_unit_symbol(doc_units))
        if not drawn:
            notes.append('the marker could not be drawn in the view')
        if notes:
            detail += '; ' + ', '.join(notes)
        message = 'Centre of gravity of %s, %s' % (fourd_common.plural(combined['count'], 'object'),
                                                   cog.format_mass(combined['mass'], imperial))
        if notes:
            toast.warning(message, detail)
        else:
            toast.success(message, detail)
    show(doc, results, combined, imperial, doc_units)


run()

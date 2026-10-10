# -*- coding: utf-8 -*-
"""Compares two versions of a model, or a model with a saved snapshot, and colours what was added, changed and removed."""
import datetime
import os

from pynavis import doc as nwdoc
from pynavis import forms, output, script, toast

from namo import duplicates, health, mdl_output, modelcompare, modelmgmt, progress, reports, ui, units

TWO_MODELS = 'Compare two appended models'
SAVE_SNAPSHOT = 'Save a snapshot of a model'
WITH_SNAPSHOT = 'Compare a model with a snapshot'
MAX_ROWS = 200


def length_text(doc_units):
    imperial = units.is_imperial(doc_units)

    def text(value):
        meters = units.to_meters(value, doc_units)
        if imperial:
            return units.format_feet_inches(meters / 0.3048)
        return health.fmt_m(meters)
    return text


def model_options(infos):
    return [('%s (model %d)' % (info['name'], info['index'] + 1), info['index']) for info in infos]


def property_fields(cfg):
    return [
        {'kind': 'check', 'key': 'compare_properties', 'label': 'Also compare properties',
         'default': cfg['compare_properties']},
        {'kind': 'textarea', 'key': 'properties', 'label': 'Properties', 'rows': 3,
         'default': cfg['properties'], 'enabled_if': ('compare_properties', True),
         'hint': 'One Category > Property per line, as the Properties window names them.'},
    ]


def result_fields(cfg, doc_units):
    return [
        {'kind': 'length', 'key': 'tolerance', 'label': 'Tolerance', 'required': True,
         'default': duplicates.default_tolerance(cfg['tolerance_m'], doc_units),
         'validate': lambda v: None if v is None or v > 0 else 'The tolerance must be more than zero.',
         'hint': 'Moves and size changes smaller than this count as unchanged.'},
        {'kind': 'check', 'key': 'paint', 'label': 'Colour the result on the model', 'default': cfg['paint']},
        {'kind': 'check', 'key': 'sets', 'label': 'Update the Compare selection sets', 'default': cfg['sets']},
    ]


def check_properties(values):
    if values.get('compare_properties'):
        pairs, problems = modelcompare.parse_property_lines(values.get('properties'))
        if problems:
            return {'properties': problems[0]}
        if not pairs:
            return {'properties': 'Name at least one property, like Element > Type.'}
    return None


def chosen_properties(values):
    if not values.get('compare_properties'):
        return []
    return modelcompare.parse_property_lines(values.get('properties'))[0]


def remember(cfg, values, doc_units):
    saved = dict(cfg)
    if values.get('tolerance') is not None:
        saved['tolerance_m'] = duplicates.kept_tolerance_m(
            values['tolerance'], duplicates.default_tolerance(cfg['tolerance_m'], doc_units),
            cfg['tolerance_m'], doc_units)
    for key in ('compare_properties', 'properties', 'paint', 'sets'):
        if key in values:
            saved[key] = values[key]
    script.save_config(saved)


def workbook_path(document):
    filename = nwdoc.get_filename(document) or ''
    folder = os.path.dirname(filename) if filename and os.path.isdir(os.path.dirname(filename)) else ''
    values = {} if filename else {'file': 'Untitled'}
    config = {'folder': folder, 'name_template': '{file} - Model compare - {date}'}
    return reports.output_path(config, 'Model compare', 'xlsx', values, unique=True)


def compare(old_records, new_data, tol, compare_hash):
    # Far from the origin the boxes may be coarser than the tolerance asked for (see
    # namo.duplicates.box_precision): compare at whichever is larger, and say so.
    boxes = [(None, None, None, rec.get('box'), None) for rec in new_data['records']]
    tol, widened = duplicates.effective_tolerance(tol, duplicates.box_precision(boxes))
    pairs, removed, added = modelcompare.match(old_records, new_data['records'], tol)
    changed, unchanged = modelcompare.diff(old_records, new_data['records'], pairs, tol, compare_hash)
    return {'pairs': pairs, 'removed': removed, 'added': added, 'changed': changed,
            'unchanged': unchanged, 'tolerance': tol, 'widened': widened}


def link(objects, index, rec):
    label = rec.get('name') or rec.get('cls') or 'Object'
    if objects is None:
        return mdl_output.esc(label)
    return output.element_link(objects[index], label)


def present(document, title, old_records, old_objects, new_data, found, values, sampled):
    doc_units = str(document.Units)
    fmt = length_text(doc_units)
    new_records = new_data['records']
    new_objects = new_data['objects']
    stats = modelcompare.counts(found['pairs'], found['removed'], found['added'],
                                found['changed'], found['unchanged'])
    compared = max(len(old_records), len(new_records))
    level, message, detail = modelcompare.summary(stats, compared, sampled)
    if level == 'info':
        toast.info(message, detail)
        return
    added_items = [new_objects[j] for j in found['added']]
    changed_items = [new_objects[j] for _i, j, _s, _r in found['changed']]
    unchanged_items = [new_objects[j] for _i, j, _s in found['unchanged']]
    removed_items = [old_objects[i] for i in found['removed']] if old_objects is not None else []
    if old_objects is not None:
        # Two appended versions sit on top of each other: fade the old side of every
        # matched pair too, or it would show through the coloured new model.
        unchanged_items += [old_objects[i] for i, _j, _s in found['unchanged']]
        unchanged_items += [old_objects[i] for i, _j, _s, _r in found['changed']]
    written, skipped, failed = [], [], []
    if values.get('paint') or values.get('sets'):
        written, skipped, failed = modelcompare.apply_results(
            added_items, changed_items, removed_items, unchanged_items,
            values.get('paint'), values.get('sets'), document)

    by_scheme = ', '.join('%s %s' % ('{:,}'.format(stats['by_scheme'][s]), modelcompare.SCHEME_LABEL[s])
                          for s in modelcompare.SCHEMES if stats['by_scheme'].get(s))
    html = [mdl_output.heading(title, 1),
            mdl_output.kpis([('Added', stats['added'], 'pass' if stats['added'] else None),
                             ('Changed', stats['changed'], 'warn' if stats['changed'] else None),
                             ('Removed', stats['removed'], 'fail' if stats['removed'] else None),
                             ('Unchanged', stats['unchanged'], None)]),
            mdl_output.note('Matched by %s. Changed: %s moved, %s resized, %s with other properties.'
                            % (by_scheme or 'nothing', '{:,}'.format(stats['moved']),
                               '{:,}'.format(stats['resized']), '{:,}'.format(stats['properties'])))]
    if sampled:
        html.append(mdl_output.note('Compared the first %s objects: the object budget stopped the read.'
                                    % '{:,}'.format(compared)))
    if found.get('widened'):
        html.append(mdl_output.note('Moves and size changes under %s count as unchanged, more than the '
                                    'tolerance asked for: this far from the origin the bounding boxes '
                                    'are only that precise.' % fmt(found['tolerance'])))
    if old_objects is None and found['removed']:
        html.append(mdl_output.note('Removed objects are only in the snapshot, so they are listed, not coloured.'))

    added_rows = [[link(new_objects, j, new_records[j]), new_records[j]['cls'],
                   new_records[j]['eid'] or '', new_records[j]['uid'] or ''] for j in found['added']]
    changed_rows = [[link(new_objects, j, new_records[j]), new_records[j]['cls'],
                     modelcompare.reason_text(reasons, fmt), modelcompare.SCHEME_LABEL[scheme]]
                    for _i, j, scheme, reasons in found['changed']]
    removed_rows = [[link(old_objects, i, old_records[i]), old_records[i]['cls'],
                     old_records[i]['eid'] or '', old_records[i]['uid'] or ''] for i in found['removed']]
    for caption, headers, rows in (('Added', ['Object', 'Class', 'Element ID', 'UniqueId'], added_rows),
                                   ('Changed', ['Object', 'Class', 'What changed', 'Matched by'], changed_rows),
                                   ('Removed', ['Object', 'Class', 'Element ID', 'UniqueId'], removed_rows)):
        if rows:
            html.append(mdl_output.heading('%s (%s)' % (caption, '{:,}'.format(len(rows))), 2))
            html.append(mdl_output.table(headers, rows, raw=set([0]), numeric=[], max_rows=MAX_ROWS))
    output.print_html(''.join(html))

    sheets = [
        ('Added', ['Object', 'Class', 'Element ID', 'UniqueId', 'IFC GlobalId'],
         [[new_records[j]['name'], new_records[j]['cls'], new_records[j]['eid'], new_records[j]['uid'],
           new_records[j]['ifc']] for j in found['added']]),
        ('Changed', ['Object', 'Class', 'What changed', 'Matched by', 'Element ID', 'UniqueId'],
         [[new_records[j]['name'], new_records[j]['cls'], modelcompare.reason_text(reasons, fmt),
           modelcompare.SCHEME_LABEL[scheme], new_records[j]['eid'], new_records[j]['uid']]
          for _i, j, scheme, reasons in found['changed']]),
        ('Removed', ['Object', 'Class', 'Element ID', 'UniqueId', 'IFC GlobalId'],
         [[old_records[i]['name'], old_records[i]['cls'], old_records[i]['eid'], old_records[i]['uid'],
           old_records[i]['ifc']] for i in found['removed']]),
    ]
    saved = None
    try:
        path = workbook_path(document)
        saved = modelcompare.write_xlsx(path, stats, sheets, subtitle=title)
        output.print_html(mdl_output.path_line('Saved:', saved))
    except (IOError, OSError) as error:
        output.print_html(mdl_output.note('The workbook could not be saved: %s' % error))

    parts = [detail[:-1] if detail.endswith('.') else detail]
    if values.get('paint'):
        parts.append('coloured on the model')
    if written:
        parts.append('sets %s/%s' % (modelcompare.SET_FOLDER, ', '.join(written)))
    if failed:
        parts.append('could not update %s' % ', '.join(failed))
    text = '; '.join(parts) + '.'
    if saved is None or failed:
        toast.warning(message, text)
    else:
        toast.success(message, text)


def compare_two(document, cfg):
    doc_units = str(document.Units)
    infos = modelmgmt.models_info(document)
    if len(infos) < 2:
        toast.info('Compare needs two models',
                   'Append the old and the new version of the model, then run Model Compare again.')
        return
    options = model_options(infos)
    fields = [
        {'kind': 'choice', 'key': 'old', 'label': 'Old version', 'options': options,
         'default': infos[-2]['index'], 'fallback': None},
        {'kind': 'choice', 'key': 'new', 'label': 'New version', 'options': options,
         'default': infos[-1]['index'], 'fallback': None},
    ] + result_fields(cfg, doc_units) + property_fields(cfg)

    def check(values):
        if values.get('old') == values.get('new'):
            return {'new': 'Choose a different model from the old version.'}
        return check_properties(values)

    values = ui.form('Model compare', fields, ok='Compare', units=doc_units, validate=check,
                     intro='Added objects turn green, changed amber, removed red on the old model; '
                           'unchanged objects fade.')
    if values is None:
        return
    remember(cfg, values, doc_units)
    old_info = infos[values['old']]
    new_info = infos[values['new']]
    prop_pairs = chosen_properties(values)
    tol = values['tolerance']

    def work(report):
        old = modelcompare.collect(old_info['root'], prop_pairs=prop_pairs, label=old_info['name'],
                                   progress=lambda f, label: report(0.45 * f, label))
        new = modelcompare.collect(new_info['root'], prop_pairs=prop_pairs, label=new_info['name'],
                                   progress=lambda f, label: report(0.45 + 0.45 * f, label))
        report(0.92, 'Matching objects')
        found = compare(old['records'], new, tol, bool(prop_pairs))
        report(1.0, 'Done')
        return old, new, found

    outcome = progress.run('Model compare', work)
    if outcome is progress.CANCELLED:
        return
    old, new, found = outcome
    present(document, 'Model compare: %s to %s' % (old_info['name'], new_info['name']),
            old['records'], old['objects'], new, found, values, old['sampled'] or new['sampled'])


def save_snapshot(document, cfg):
    doc_units = str(document.Units)
    infos = modelmgmt.models_info(document)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    fields = [
        {'kind': 'choice', 'key': 'model', 'label': 'Model', 'options': model_options(infos),
         'default': infos[-1]['index'], 'fallback': None},
        {'kind': 'text', 'key': 'label', 'label': 'Name', 'default': stamp, 'required': True},
    ] + property_fields(cfg)
    values = ui.form('Save a snapshot', fields, ok='Save', units=doc_units, validate=check_properties,
                     intro='A snapshot keeps each object\'s identity, box and chosen properties, so '
                           'the next version can be compared with this one.')
    if values is None:
        return
    remember(cfg, values, doc_units)
    info = infos[values['model']]
    prop_pairs = chosen_properties(values)
    outcome = progress.run('Save a snapshot', lambda report: modelcompare.collect(
        info['root'], prop_pairs=prop_pairs, label=info['name'], progress=report))
    if outcome is progress.CANCELLED:
        return
    snapshot = modelcompare.snapshot_record(values['label'].strip(), info['name'], doc_units,
                                            outcome['records'], prop_pairs, stamp, outcome['sampled'])
    try:
        stored, note = modelcompare.save_snapshot(snapshot, document)
    except (IOError, OSError) as error:
        toast.error('Could not save the snapshot', str(error))
        return
    detail = '%s objects of %s.' % ('{:,}'.format(stored['count']), info['name'])
    if outcome['sampled']:
        detail = 'The first %s objects of %s (the object budget stopped the read).' % (
            '{:,}'.format(stored['count']), info['name'])
    if note:
        detail += ' ' + note
    elif not nwdoc.get_filename(document):
        detail += ' Save the document so the snapshot stays with it.'
    toast.success('Saved snapshot %s' % stored['label'], detail)


def compare_snapshot(document, cfg):
    doc_units = str(document.Units)
    snapshots = modelcompare.list_snapshots(document)
    if not snapshots:
        toast.info('No snapshots yet',
                   'Save a snapshot of a model first, then compare against it after the next update.')
        return
    rows = [{'value': s['id'], 'cells': [s.get('label') or s['id'], s.get('model') or '',
                                         s.get('time') or '', s.get('count') or 0]} for s in snapshots]
    picked = ui.choose('Choose a snapshot', rows, ['Snapshot', 'Model', 'Saved', 'Objects'],
                       multiselect=False, prompt='Pick the snapshot to compare with.')
    if picked is None or not picked:
        return
    snapshot = modelcompare.load_snapshot(picked[0], document)
    problem = modelcompare.check_snapshot(snapshot)
    if problem:
        toast.error('Could not use that snapshot', problem)
        return
    infos = modelmgmt.models_info(document)
    default = infos[-1]['index']
    for info in infos:
        if info['name'].lower() == str(snapshot.get('model') or '').lower():
            default = info['index']
            break
    fields = [{'kind': 'choice', 'key': 'model', 'label': 'Compare with', 'options': model_options(infos),
               'default': default, 'fallback': None}] + result_fields(cfg, doc_units)
    values = ui.form('Model compare', fields, ok='Compare', units=doc_units,
                     intro='Snapshot %s of %s, saved %s.' % (snapshot.get('label'), snapshot.get('model'),
                                                             snapshot.get('time')))
    if values is None:
        return
    remember(cfg, values, doc_units)
    info = infos[values['model']]
    scale = 1.0
    snap_units = snapshot.get('units') or doc_units
    if snap_units != doc_units:
        try:
            scale = units.to_meters(1.0, snap_units) / units.to_meters(1.0, doc_units)
        except ValueError:
            scale = 1.0
    old_records = modelcompare.decode_records(snapshot['objects'], scale)
    prop_pairs = [tuple(p) for p in snapshot.get('properties') or []]
    tol = values['tolerance']

    def work(report):
        new = modelcompare.collect(info['root'], prop_pairs=prop_pairs, label=info['name'],
                                   progress=lambda f, label: report(0.9 * f, label))
        report(0.92, 'Matching objects')
        found = compare(old_records, new, tol, bool(prop_pairs))
        report(1.0, 'Done')
        return new, found

    outcome = progress.run('Model compare', work)
    if outcome is progress.CANCELLED:
        return
    new, found = outcome
    present(document, 'Model compare: %s to snapshot %s' % (info['name'], snapshot.get('label')),
            old_records, None, new, found, values, new['sampled'] or bool(snapshot.get('sampled')))


def run():
    document = nwdoc.get_doc()
    cfg = script.get_config(modelcompare.DEFAULTS)
    mode = forms.ask_options('What do you want to compare?', [TWO_MODELS, SAVE_SNAPSHOT, WITH_SNAPSHOT],
                             title='Model compare')
    if mode is None:
        return
    if mode == TWO_MODELS:
        compare_two(document, cfg)
    elif mode == SAVE_SNAPSHOT:
        save_snapshot(document, cfg)
    else:
        compare_snapshot(document, cfg)


run()

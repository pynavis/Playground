# -*- coding: utf-8 -*-
"""Moves, turns, re-units or resets whole models, by typed values or two picked points, with presets per model file."""
from namo import modelmgmt, picking, transforms, ui

from pynavis import app, script, selection, toast

UNITS = ['Meters', 'Centimeters', 'Millimeters', 'Feet', 'Inches', 'Yards', 'Kilometers', 'Miles',
         'Micrometers', 'Mils', 'Microinches']
DEFAULTS = {'mode': 'values', 'pivot': 'center'}


def states(infos, doc_units):
    out = {}
    convention = transforms.convention()
    for info in infos:
        try:
            state = transforms.read_state(info['model'])
            factor = transforms.unit_factor(doc_units, state['units'], convention)
            out[info['key']] = (state, transforms.describe(state, doc_units, factor))
        except Exception:
            out[info['key']] = (None, ['Could not read the transform'])
    return out


def choose_models(infos, described, doc):
    if len(infos) == 1:
        return [infos[0]['key']]
    picked = modelmgmt.models_of_items(selection.get_items(doc), doc)
    checked = [i['key'] for i in picked]
    rows = []
    for info in infos:
        lines = described[info['key']][1]
        cells = [info['name'], info['units']] + [line.split(': ', 1)[-1] for line in lines[:3]]
        rows.append({'value': info['key'], 'cells': cells})
    prompt = ('Tick the models to change. The models of the selection are ticked.' if checked
              else 'Tick the models to change.')
    return ui.choose('Transform Fixer', rows, ['Model', 'Units', 'Offset', 'Rotation', 'Scale'],
                     multiselect=True, checked=checked, prompt=prompt, ok='Next', width=820)


def ask(cfg, chosen, described, doc_units):
    first = chosen[0]
    intro = '%s: %s.' % (first['name'], '; '.join(described[first['key']][1]))
    if len(chosen) > 1:
        intro += ' %d models chosen; values apply to each.' % len(chosen)
    hint = 'Signed, in document units unless you type a unit: -1500mm, 2\' 6", -3.5'

    def length_ok(text):
        return None if transforms.parse_signed_length(text, doc_units) is not None else \
            'Type a length such as -1500mm or 2\' 6".'
    fields = [
        {'kind': 'radio', 'key': 'mode', 'label': 'What to do', 'default': cfg['mode'], 'fallback': None, 'options': [
            ('Move and turn by values', 'values'), ('Move by two picked points', 'points'),
            ('Change the model units', 'units'), ('Apply the saved preset for this file', 'preset'),
            ('Save the current transform as a preset', 'save'), ('Reset to no transform', 'reset')]},
        {'kind': 'text', 'key': 'dx', 'label': 'Move X', 'default': '0', 'hint': hint,
         'validate': length_ok, 'enabled_if': ('mode', 'values')},
        {'kind': 'text', 'key': 'dy', 'label': 'Move Y', 'default': '0', 'validate': length_ok,
         'enabled_if': ('mode', 'values')},
        {'kind': 'text', 'key': 'dz', 'label': 'Move Z', 'default': '0', 'validate': length_ok,
         'enabled_if': ('mode', 'values')},
        {'kind': 'number', 'key': 'angle', 'label': 'Turn about Z', 'default': 0.0, 'suffix': 'degrees',
         'min': -360.0, 'max': 360.0, 'hint': 'Counter-clockwise seen from above.',
         'enabled_if': ('mode', 'values')},
        {'kind': 'choice', 'key': 'pivot', 'label': 'Turn about', 'default': cfg['pivot'], 'fallback': None, 'options': [
            ('The centre of each model', 'center'), ('The project origin (0, 0, 0)', 'zero'),
            ('A point I pick', 'point')], 'enabled_if': ('mode', 'values')},
        {'kind': 'choice', 'key': 'units', 'label': 'Model units', 'default': first['units'] or 'Meters', 'fallback': 'Meters',
         'options': UNITS, 'hint': 'The geometry rescales about each model\'s origin.',
         'enabled_if': ('mode', 'units')},
        {'kind': 'check', 'key': 'auto_apply', 'default': False,
         'label': 'Apply it automatically whenever this file is appended',
         'enabled_if': ('mode', 'save')},
    ]
    return ui.form('Transform Fixer', fields, intro=intro, ok='Apply', width=560)


def report_move(result, names, what):
    if result['failed'] and not result['moved']:
        name, why = result['failed'][0]
        toast.error('Could not transform %s' % name, why)
        return
    unverified = [n for n, verdict in result['checked'] if verdict == 'unverified']
    detail = what + ' Ctrl+Z undoes it.'
    if result['corrected']:
        detail = ('%s Navisworks reads model offsets in %s units here, so Playground corrected the move and '
                  'will use that from now on (two undo steps this time).' % (what, result['convention']))
    if result['failed']:
        toast.warning('Moved %s, %d failed' % (modelmgmt.join_names(result['moved']), len(result['failed'])),
                      '%s: %s' % result['failed'][0])
    elif unverified:
        toast.info('Moved %s' % modelmgmt.join_names(result['moved']),
                   '%s Could not confirm where %s landed; check it in the view.'
                   % (what, modelmgmt.join_names(unverified)))
    else:
        toast.success('Moved %s' % modelmgmt.join_names(result['moved']), detail)


def describe_move(move, angle, doc_units):
    parts = []
    for axis, value in zip('XYZ', move):
        if abs(value) > 1e-12:
            parts.append('%s %s' % (axis, transforms.format_length(value, doc_units)))
    if abs(angle) > 1e-12:
        parts.append('turned %s' % transforms.format_angle(angle))
    return (', '.join(parts) + '.') if parts else ''


def run_values(answer, keys, doc, doc_units):
    move = tuple(transforms.parse_signed_length(answer[k], doc_units) for k in ('dx', 'dy', 'dz'))
    angle = float(answer['angle'] or 0.0)
    if max(abs(v) for v in move) < 1e-12 and abs(angle) < 1e-12:
        toast.info('Nothing to move', 'Type a distance or an angle.')
        return
    point = None
    if answer['pivot'] == 'point' and abs(angle) > 1e-12:
        hit = picking.point('Click the point to turn the models about', doc=doc)
        if hit is None:
            return                          # Esc, right-click or another tool: say nothing
        point = hit.point
    result = transforms.move_models(keys, angle, answer['pivot'], point, move, doc=doc)
    report_move(result, keys, describe_move(move, angle, doc_units))


def run_points(keys, doc, doc_units):
    picked = picking.points('Click the point to move from', 'Now click where that point should go',
                            doc=doc)
    if picked is None:
        return                              # Esc, right-click or another tool: say nothing
    start, end = picked
    move = tuple(float(end[i]) - float(start[i]) for i in range(3))
    if max(abs(v) for v in move) <= transforms.point_noise((start, end)):
        toast.info('Nothing to move', 'The two points are the same.')
        return
    result = transforms.move_models(keys, 0.0, 'zero', None, move, doc=doc)
    report_move(result, keys, describe_move(move, 0.0, doc_units))


def run_preset(chosen, doc):
    presets = transforms.all_presets()
    pairs = []
    missing = []
    for info in chosen:
        hits = transforms.match_presets(presets, [info['source'] or info['file'] or info['name']])
        if not hits and info['file']:
            hits = transforms.match_presets(presets, [info['file']])
        if hits:
            pairs.append((info['key'], hits[0][2]))
        else:
            missing.append(info['name'])
    if not pairs:
        toast.info('No preset for %s' % modelmgmt.join_names(missing),
                   'Save one first with "Save the current transform as a preset".')
        return
    applied, failed = transforms.apply_presets(pairs, doc)
    if failed:
        toast.warning('Could not apply every preset', '%s: %s' % failed[0])
    elif not applied:
        toast.info('Already in place', 'The models already have their preset transforms.')
    else:
        detail = 'Ctrl+Z undoes it.'
        if missing:
            detail = 'No preset for %s. %s' % (modelmgmt.join_names(missing), detail)
        toast.success('Applied the preset to %s' % modelmgmt.join_names(applied), detail)


def run():
    doc = app.get_doc()
    infos = modelmgmt.models_info(doc)
    if not infos:
        toast.info('No models', 'Append a model first.')
        return
    doc_units = str(doc.Units)
    described = states(infos, doc_units)
    keys = choose_models(infos, described, doc)
    if keys is None:
        return
    if not keys:
        toast.info('No models chosen', 'Tick the models to change.')
        return
    chosen = [i for i in infos if i['key'] in set(keys)]
    cfg = script.get_config(DEFAULTS)
    answer = ask(cfg, chosen, described, doc_units)
    if answer is None:
        return
    cfg['mode'] = answer['mode']
    cfg['pivot'] = answer['pivot']
    script.save_config(cfg)
    mode = answer['mode']
    if mode == 'values':
        run_values(answer, keys, doc, doc_units)
    elif mode == 'points':
        run_points(keys, doc, doc_units)
    elif mode == 'units':
        try:
            done = transforms.set_units(keys, answer['units'])
        except Exception as error:
            toast.error('Could not change the model units', str(error) or type(error).__name__)
            return
        if done:
            toast.success('%s now in %s' % (modelmgmt.join_names(done), answer['units']),
                          'The geometry rescaled about each model\'s origin. Ctrl+Z undoes it.')
        else:
            toast.info('Nothing changed', 'The chosen models are no longer in the document.')
    elif mode == 'preset':
        run_preset(chosen, doc)
    elif mode == 'save':
        try:
            saved = [transforms.save_preset(info, answer['auto_apply']) for info in chosen]
        except Exception as error:
            toast.error('Could not save the transform preset', str(error) or type(error).__name__)
            return
        toast.success('Saved the transform preset for %s' % modelmgmt.join_names(saved),
                      'Applied automatically whenever the file is appended.' if answer['auto_apply']
                      else 'Apply it later with Transform Fixer.')
    elif mode == 'reset':
        try:
            done = transforms.reset_models(keys, doc)
        except Exception as error:
            toast.error('Could not reset the transform', str(error) or type(error).__name__)
            return
        if done:
            toast.success('Reset %s' % modelmgmt.join_names(done),
                          'No offset, rotation or scale now. Ctrl+Z undoes it.')
        else:
            toast.info('Nothing to reset', 'The chosen models are no longer in the document.')


run()

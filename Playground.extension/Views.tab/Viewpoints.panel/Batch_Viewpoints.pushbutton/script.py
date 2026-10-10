"""Generates saved viewpoints per level, per grid intersection, per selection or search set, or per model, in one undo step."""
import os

from namo import items, levels, progress, ui, vp_common, vpbatch
from pynavis import forms, script, toast

TITLE = 'Batch Viewpoints'
INTROS = {
    'level': 'One viewpoint per level. A plan looks straight down with the level cut at the '
             'height below; an eye-level view stands in from the south-west corner of the floor.',
    'grid': 'One viewpoint per grid intersection on the level you choose.',
    'set': 'One viewpoint per set, zoomed to its items. Each view looks the way the current view looks.',
    'model': 'One viewpoint per model, zoomed to it. Each view looks the way the current view looks.',
}


def load_levels(document):
    """Levels (estimated ones read with a progress window), or None when cancelled."""
    found = levels.cached_or_none(document)
    if found is not None:
        return found
    outcome = progress.run(TITLE, lambda report: levels.find(document, report), 'Looking for levels')
    return None if outcome is progress.CANCELLED else outcome


def choose_levels(level_list, units):
    rows = [{'value': i, 'cells': [lv['name'], vp_common.length_text(lv['elevation'], units),
                                   'Estimated' if lv.get('approximate') else 'Grid']}
            for i, lv in enumerate(level_list)]
    picked = ui.choose('%s: levels' % TITLE, rows, ['Level', 'Elevation', 'Source'],
                       checked=list(range(len(level_list))), ok='Save viewpoints')
    return None if picked is None else [level_list[i] for i in picked]


def level_run(document, cfg, level_list):
    chosen = choose_levels(level_list, str(document.Units))
    if chosen is None:
        return None
    return vpbatch.level_jobs(document, level_list, chosen, cfg)


def grid_run(document, cfg, level_list, values):
    lv = None
    for candidate in level_list:
        if candidate['name'] == values.get('grid_level'):
            lv = candidate
    grid_level = vpbatch.grid_level_object(document, values.get('grid_level'))
    box = levels.model_box(document)
    if lv is None or grid_level is None or box is None:
        toast.error('Could not read that grid level', 'Check the grid system in Grids and Levels.')
        return None
    k = 1.0 / vp_common.to_meters_factor(str(document.Units))
    outcome = progress.run(TITLE, lambda report: vpbatch.find_intersections(
        document, grid_level, box, cfg['grid_spacing_m'] * k, report), 'Finding grid intersections')
    if outcome is progress.CANCELLED:
        return None
    found, _step = outcome
    if not found:
        toast.info('No grid intersections found', 'The grid lines on %s do not cross inside the model.' % lv['name'])
        return None
    rows = [{'value': i, 'cells': [r['name'], r['line1'], r['line2']]} for i, r in enumerate(found)]
    picked = ui.choose('%s: intersections on %s' % (TITLE, lv['name']), rows, ['Intersection', 'Line', 'Line'],
                       checked=list(range(len(found))), ok='Save viewpoints')
    if picked is None:
        return None
    return vpbatch.grid_jobs(document, level_list, lv, [found[i] for i in picked], cfg), False


def set_run(document, cfg, entries):
    rows = [{'value': i, 'cells': [vp_common.folder_label(e['folder']), e['name']]} for i, e in enumerate(entries)]
    picked = ui.choose('%s: sets' % TITLE, rows, ['Folder', 'Set'], checked=list(range(len(entries))),
                       ok='Save viewpoints')
    if picked is None:
        return None

    def resolve(report):
        targets = []
        for n, i in enumerate(picked):
            if vp_common.report_step(report, float(n) / len(picked), 'Reading %s' % entries[i]['name']):
                raise items.Cancelled()
            found = vpbatch.set_items(document, entries[i])
            if found:
                targets.append({'name': entries[i]['name'], 'folder': entries[i]['folder'], 'items': found})
        return targets
    targets = progress.run(TITLE, resolve, 'Reading the sets')
    if targets is progress.CANCELLED:
        return None
    if not targets:
        toast.info('The chosen sets are empty', 'Nothing in the model matches them.')
        return None
    return vpbatch.zoom_jobs(document, targets, 'set', cfg), False


def model_run(document, cfg):
    models = items.models(document)
    rows = [{'value': m['index'], 'cells': [m['name'], m['file']]} for m in models]
    picked = ui.choose('%s: models' % TITLE, rows, ['Model', 'File'], checked=[m['index'] for m in models],
                       ok='Save viewpoints')
    if picked is None:
        return None
    targets = [{'name': os.path.splitext(m['name'])[0] or m['name'], 'items': [m['root']]}
               for m in models if m['index'] in picked]
    return vpbatch.zoom_jobs(document, targets, 'model', cfg), False


def run():
    document = vp_common.active_doc()
    if not vp_common.has_models(document):
        toast.info('No model open', 'Open or append a model, then run Batch Viewpoints again.')
        return
    cfg = vpbatch.settings(script.get_config(vpbatch.DEFAULTS))
    labels = [label for _g, label in vpbatch.GENERATORS]
    picked = forms.ask_options(None, labels, title=TITLE)
    if picked is None:
        return
    generator = vpbatch.GENERATORS[labels.index(picked)][0]
    units = str(document.Units)
    level_list = []
    entries = []
    level_options = None
    if generator in ('level', 'grid'):
        level_list = load_levels(document)
        if level_list is None:
            return
        if not level_list:
            toast.info('No levels found', 'Add a grid system with levels (Grids and Levels), or open a model '
                                          'whose objects carry a Level property.')
            return
        if generator == 'grid':
            level_list = [lv for lv in level_list if lv.get('source') == 'grid']
            if not level_list:
                toast.info('No grid system', 'Per grid intersection needs grids and levels. Turn them on in '
                                             'Grids and Levels, then run this again.')
                return
            level_options = [('%s (%s)' % (lv['name'], vp_common.length_text(lv['elevation'], units)), lv['name'])
                             for lv in level_list]
    elif generator == 'set':
        entries = vpbatch.selection_sets(document)
        if not entries:
            toast.info('No selection or search sets', 'Save some sets in the Sets window, then run this again.')
            return
    values = ui.form(TITLE, vpbatch.fields_for(generator, cfg, units, level_options),
                     intro=INTROS[generator], ok='Next', width=500, units=units)
    if values is None:
        return
    cfg = vpbatch.update_settings(cfg, generator, values, units)
    script.save_config(cfg)
    if generator == 'level':
        made = level_run(document, cfg, level_list)
    elif generator == 'grid':
        made = grid_run(document, cfg, level_list, values)
    elif generator == 'set':
        made = set_run(document, cfg, entries)
    else:
        made = model_run(document, cfg)
    if made is None:
        return
    jobs, sampled = made
    if not jobs:
        toast.info('Nothing chosen', 'Tick at least one row, then run Batch Viewpoints again.')
        return
    result = progress.run(TITLE, lambda report: vpbatch.run(document, jobs, cfg, report), 'Saving viewpoints')
    if result is progress.CANCELLED:
        return
    level, message, detail = vpbatch.summary(result)
    if sampled and level == 'success':
        detail += ' Very large model: some level frames were estimated from part of the tree.'
    toast.show(level, message, detail)


run()

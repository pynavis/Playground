"""Sections the view at the level you choose: cut above the floor, optional slab view and plan camera."""
from namo import levels, progress, ui, vp_common
from pynavis import toast

TITLE = 'Level Sectioner'


def run():
    document = vp_common.active_doc()
    if not vp_common.has_models(document):
        toast.info('No model open', 'Open or append a model, then run Level Sectioner again.')
        return
    found = levels.cached_or_none(document)
    if found is None:
        found = progress.run(TITLE, lambda report: levels.find(document, report), 'Looking for levels')
        if found is progress.CANCELLED:
            return
    if not found:
        toast.info('No levels found', 'Add a grid system with levels (Grids and Levels), or open a model '
                                      'whose objects carry a Level property.')
        return
    units = str(document.Units)
    cfg = levels.load_settings()
    current = levels.current_index(found, document, cfg)
    rows = [{'value': i, 'cells': [lv['name'], vp_common.length_text(lv['elevation'], units),
                                   'Estimated' if lv.get('approximate') else 'Grid']}
            for i, lv in enumerate(found)]
    k = 1.0 / vp_common.to_meters_factor(units)
    prompt = 'Cut %s above the level%s%s. Shift+Click changes these.' % (
        vp_common.length_text(cfg['cut_height_m'] * k, units),
        ', floors below hidden' if cfg['slab'] else '', ', plan view' if cfg['plan'] else '')
    picked = ui.choose(TITLE, rows, ['Level', 'Elevation', 'Source'], multiselect=False,
                       checked=[current] if current is not None else None, prompt=prompt, ok='Section')
    if picked is None:
        return
    lv = found[picked[0]]
    levels.apply(lv, document, cfg)
    cut = lv['elevation'] + cfg['cut_height_m'] * k
    detail = 'Cut at %s.' % vp_common.length_text(cut, units)
    if lv.get('approximate'):
        detail += ' ' + levels.source_note(found)
    detail += ' Alt+PgUp and Alt+PgDn step between levels.'
    toast.success('Section at %s' % lv['name'], detail)


run()

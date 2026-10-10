"""Copies saved-viewpoint folders between Navisworks files through a viewpoint package."""
import os

from namo import progress, ui, vp_common, vp_sync, vpexport
from pynavis import forms, output, script, toast

TITLE = 'Viewpoint Sync'
ACTIONS = ['Export package', 'Import package']
DEFAULTS = {'target': '', 'keep_paths': True, 'policy': 'skip', 'clip': True, 'comments': True}


def export_package(document):
    rows = vp_common.view_rows(document)
    if not rows:
        toast.info('No saved viewpoints', 'Save some viewpoints, then export a package.')
        return
    folders = vp_common.folder_paths(rows)
    table = [{'value': path, 'cells': [vp_common.folder_label(path), count]} for path, count in folders]
    picked = ui.choose('%s: folders to export' % TITLE, table, ['Folder', 'Viewpoints'],
                       checked=[path for path, _c in folders], ok='Next',
                       prompt='A folder takes its subfolders with it. (top level) is the viewpoints '
                              'outside any folder.')
    if picked is None:
        return
    chosen = vp_common.select_rows(rows, {'mode': 'folders', 'folders': picked})
    if not chosen:
        toast.info('Nothing to export', 'The chosen folders hold no viewpoints.')
        return
    path = forms.save_file(filter='Playground viewpoint packages (*.nvp.json)|*.nvp.json',
                           default_name=vp_sync.package_path_default(document), title=TITLE)
    if path is None:
        return
    if not path.lower().endswith('.nvp.json'):
        path = (path[:-5] if path.lower().endswith('.json') else path) + '.nvp.json'
    try:
        vpexport.write_package(path, vpexport.records_from(chosen, document, include_clip=True), document)
    except (IOError, OSError) as error:
        toast.error('Could not write the package', '%s. Check the folder is writable, then try again.' % error)
        return
    toast.success('Exported %s' % vp_common.plural(len(chosen), 'viewpoint'),
                  '%s. Open the other model and choose Import package.' % path)


def import_package(document):
    path = forms.open_file(filter='Viewpoint packages and Navisworks XML (*.nvp.json;*.json;*.xml)|'
                                  '*.nvp.json;*.json;*.xml', title=TITLE)
    if path is None:
        return
    try:
        records, units_from, notes = vpexport.read_file(path)
    except ValueError as error:
        toast.error('Could not read the package', str(error))
        return
    if not records:
        toast.info('The file holds no viewpoints', notes[0] if notes else os.path.basename(path))
        return
    counts = vpexport.folder_counts(records)
    table = [{'value': folder, 'cells': [vp_common.folder_label(folder), count]} for folder, count in counts]
    picked = ui.choose('%s: folders to import' % TITLE, table, ['Folder', 'Viewpoints'],
                       checked=[folder for folder, _c in counts], ok='Next')
    if picked is None:
        return
    chosen = vp_sync.chosen(records, picked)
    if not chosen:
        toast.info('No folders chosen', 'Tick at least one folder, then import the package again.')
        return
    cfg = script.get_config(DEFAULTS)
    units = str(document.Units)
    same = abs(vp_common.unit_factor(units_from, units) - 1.0) < 1e-12
    intro = '%s from %s.' % (vp_common.plural(len(chosen), 'viewpoint'), os.path.basename(path))
    if not same:
        intro += ' The package is in %s and will be converted to %s.' % (units_from.lower(), units.lower())
    values = ui.form(TITLE, vp_sync.import_fields(cfg), intro=intro, ok='Import')
    if values is None:
        return
    cfg.update(values)
    script.save_config(cfg)
    steps = vp_sync.plan(chosen, values['target'], values['policy'], vp_sync.existing_lookup(document),
                         values['keep_paths'])
    counts_now = vp_sync.plan_counts(steps)
    if counts_now['replace'] and not forms.confirm('%s\n\nReplaced viewpoints lose their own camera, section and '
                                                   'comments. One Ctrl+Z undoes the import.'
                                                   % vp_sync.plan_sentence(steps), TITLE):
        return
    outcome = progress.run(TITLE, lambda report: vp_sync.apply(document, steps, units_from, values['clip'],
                                                               values['comments'], report), 'Importing')
    if outcome is progress.CANCELLED:
        return
    results, stopped = outcome
    if results:
        output.set_title('%s: import report' % TITLE)
        output.print_md('## Imported from %s' % os.path.basename(path))
        for note in notes:
            output.print_md(note)
        output.print_table(vp_sync.report_rows(results), ['Folder', 'Name', 'Result'])
    level, message, detail = vp_sync.summary(results, stopped, len(steps))
    toast.show(level, message, detail)


def run():
    document = vp_common.active_doc()
    if not vp_common.has_models(document):
        toast.info('No model open', 'Open or append a model, then run Viewpoint Sync again.')
        return
    action = forms.ask_options(None, ACTIONS, title=TITLE)
    if action == ACTIONS[0]:
        export_package(document)
    elif action == ACTIONS[1]:
        import_package(document)


run()

# -*- coding: utf-8 -*-
"""Runs, renames, duplicates, deletes, exports and imports saved Quick and Zone Takeoff templates."""
import os

from pynavis import forms, toast

from namo import fourd_common, naming, paths, qty_run, qty_ui, templates, ui

TITLE = 'Takeoff Templates'


def run():
    if ui.is_runner():
        toast.info('%s needs a person at the screen' % TITLE, 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    entries = qty_ui.collect_templates()
    chosen = {'run': None}
    holder = {}

    def refresh(message=None):
        fresh = qty_ui.collect_templates()
        holder['win'].Tag.update(qty_ui.template_rows(fresh), message)

    def store(tool):
        return templates.Templates(tool)

    def run_selected(selected):
        chosen['run'] = selected[0]
        holder['win'].Tag.close()

    def rename(selected):
        tool, name = selected[0]
        new = forms.ask_string('New name for %s:' % name, default=name, title=TITLE)
        if new is None or new.strip() == name:
            return
        try:
            stored = store(tool).rename(name, new)
        except ValueError as error:
            toast.error('Could not rename the template', str(error))
            return
        refresh('Renamed %s to %s.' % (name, stored))

    def duplicate(selected):
        tool, name = selected[0]
        config = store(tool).get(name)
        if config is None:
            return
        new = naming.unique('%s copy' % name, store(tool).names())
        store(tool).save(new, config)
        refresh('Made %s.' % new)

    def delete(selected):
        names = ', '.join(name for _tool, name in selected)
        if not forms.confirm('Delete %s for everyone who shares these templates?\n\n%s'
                             % (fourd_common.plural(len(selected), 'template'), names), title=TITLE):
            return
        for tool, name in selected:
            store(tool).delete(name)
        refresh('Deleted %s.' % fourd_common.plural(len(selected), 'template'))

    def export(selected):
        picked = selected or [(tool, name) for tool, name, _info, _config in qty_ui.collect_templates()]
        if not picked:
            toast.info('No templates to export', 'Save a template from Quick or Zone Takeoff first.')
            return
        path = forms.save_file(filter='Playground templates (*.json)|*.json',
                               default_name=os.path.join(fourd_common.documents_folder(), 'Takeoff templates.json'),
                               title='Export takeoff templates')
        if path is None:
            return
        tools = sorted(set(tool for tool, _name in picked))
        written = 0
        files = qty_ui.export_paths(path, tools)
        for tool in tools:
            written += store(tool).export(files[tool], [name for t, name in picked if t == tool])
        toast.success('Exported %s' % fourd_common.plural(written, 'template'), ', '.join(sorted(files.values())))

    def import_(selected):
        path = forms.open_file(filter='Playground templates (*.json)|*.json|All files (*.*)|*.*',
                               title='Import takeoff templates')
        if path is None:
            return
        data = paths.load_json(path, None, move_aside=False)
        tool = data.get('tool') if isinstance(data, dict) else None
        if tool not in (qty_ui.QUICK_TOOL, qty_ui.ZONE_TOOL):
            toast.error('Not a takeoff templates file', '%s holds no Quick or Zone Takeoff templates.'
                        % os.path.basename(path))
            return
        try:
            count = store(tool).import_file(path)
        except ValueError as error:
            toast.error('Could not import the templates', str(error))
            return
        refresh('Imported %s.' % fourd_common.plural(count, 'template'))

    actions = [{'label': 'Run', 'fn': run_selected, 'primary': True},
               {'label': 'Rename', 'fn': rename}, {'label': 'Duplicate', 'fn': duplicate},
               {'label': 'Delete', 'fn': delete},
               {'label': 'Export', 'fn': export, 'needs_selection': False},
               {'label': 'Import', 'fn': import_, 'needs_selection': False}]
    win = qty_ui.build_templates(entries, actions)
    holder['win'] = win
    ui.show_modal(win)
    if chosen['run'] is None:
        return
    tool, name = chosen['run']
    config = store(tool).get(name)
    if config is None:
        toast.error('The template is gone', name)
        return
    if not fourd_common.has_models(doc):
        toast.info('No model is open', 'Open or append a model first.')
        return
    if config.get('scope') == 'selection' and not doc.CurrentSelection.SelectedItems.Count:
        config['scope'] = 'model'
    if tool == qty_ui.ZONE_TOOL:
        qty_run.run_zone(doc, config)
    else:
        qty_run.run_quick(doc, config)


run()

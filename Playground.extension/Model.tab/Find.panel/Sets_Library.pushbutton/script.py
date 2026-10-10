# -*- coding: utf-8 -*-
"""Publishes search sets to a shared library, imports them into this model, or manages libraries."""
import os

from pynavis import forms, output, script, sets, toast
from pynavis._api import Application

from namo import find_library, find_sets, paths, progress, ui

PUBLISH = 'Publish sets to a library'
IMPORT = 'Import sets from a library'
MANAGE = 'Manage libraries'
document = Application.ActiveDocument
cfg = script.get_config({'library': ''})


def where_note():
    if paths.team_available():
        return 'Libraries live in the shared folder, so your team sees them.'
    return ('Libraries live in your local Playground folder; set a shared folder in Playground settings to '
            'share them with your team.')


def publish():
    spec = find_sets.export_search_sets(document)
    if not spec['sets']:
        toast.info('No search sets to publish',
                   'This model has no search sets. Selection sets of items cannot travel between models.')
        return
    picked = ui.choose('Publish to a library', find_library.choose_rows(spec['sets']),
                       ['Folder', 'Set', 'Conditions'], multiselect=True,
                       checked=list(range(len(spec['sets']))), ok='Next', width=760,
                       prompt='Tick the search sets to publish.')
    if picked is None:
        return
    names = [lib['name'] for lib in find_library.list_libraries()]
    values = ui.form('Publish to a library', [
        {'kind': 'text', 'key': 'name', 'label': 'Library name', 'required': True,
         'default': cfg['library'] or os.path.splitext(os.path.basename(document.FileName or ''))[0]
         or 'Search sets',
         'hint': 'Existing: %s' % ', '.join(names) if names else 'A new library is created.'},
        {'kind': 'radio', 'key': 'mode', 'label': 'When the library exists',
         'options': [('Add these sets to it (same names are updated)', 'merge'),
                     ('Replace its sets with these', 'replace')], 'default': 'merge'},
        {'kind': 'label', 'text': where_note(), 'muted': True},
    ], ok='Publish', width=520)
    if values is None:
        return
    chosen = [spec['sets'][i] for i in picked]
    try:
        path, total, added = find_library.publish(values['name'], chosen, values['mode'] == 'replace')
    except (IOError, OSError) as error:
        toast.error('Could not write the library', str(error))
        return
    script.save_config({'library': values['name'].strip()})
    toast.success("Published %d %s to '%s'" % (added, 'set' if added == 1 else 'sets', values['name'].strip()),
                  'The library now holds %d sets. %s' % (total, path))


def choose_library(title, prompt):
    libraries = find_library.list_libraries()
    if not libraries:
        toast.info('No libraries yet', 'Publish search sets from a model first. %s' % where_note())
        return None
    picked = ui.choose(title, find_library.library_rows(libraries), ['Library', 'Sets', 'Updated', 'By'],
                       multiselect=False, checked=[lib['path'] for lib in libraries
                                                   if lib['name'] == cfg['library']][:1],
                       prompt=prompt, width=640)
    return None if picked is None else picked[0]


def import_sets():
    path = choose_library('Import from a library', 'Choose the library to import from.')
    if path is None:
        return
    library = find_library.load(path)
    if library is None or not library['sets']:
        toast.warning('Nothing to import', 'That library holds no readable search sets.')
        return
    picked = ui.choose("Import from '%s'" % library['name'], find_library.choose_rows(library['sets']),
                       ['Folder', 'Set', 'Conditions'], multiselect=True,
                       checked=list(range(len(library['sets']))), ok='Next', width=760,
                       prompt='Tick the search sets to import.')
    if picked is None:
        return
    mode = forms.ask_options('When this model already has a set with the same name and folder:',
                             ['Add the imported one beside it', 'Replace it'], title='Import sets')
    if mode is None:
        return
    chosen = find_library.import_spec(library, picked)
    spec, problems = find_library.split_importable(chosen)
    if problems:
        output.print_md('## Sets that cannot be imported')
        output.print_table([[p] for p in problems], ['Problem'])
    if not spec['sets']:
        toast.error('Nothing was imported', '%d %s; see the output window.' % (
            len(problems), 'problem' if len(problems) == 1 else 'problems'))
        return

    def work(report):
        return sets.import_dict(spec, document, replace=(mode == 'Replace it'),
                                progress=lambda done, total: report(float(done) / max(1, total),
                                                                    '%d of %d sets' % (done, total)))
    outcome = progress.run('Importing sets', work)
    if outcome is progress.CANCELLED:
        return
    created, errors = outcome
    script.save_config({'library': library['name']})
    if errors:
        output.print_md("## Import from '%s'" % library['name'])
        output.print_table([[e] for e in errors], ['Not imported'])
    if errors or problems:
        toast.warning('Imported %d of %d sets' % (created, len(chosen['sets'])),
                      'The output window lists the sets that were left out.')
    else:
        toast.success("Imported %d %s from '%s'" % (created, 'set' if created == 1 else 'sets',
                                                    library['name']))


def manage():
    libraries = find_library.list_libraries()
    if not libraries:
        toast.info('No libraries yet', 'Publish search sets from a model first. %s' % where_note())
        return
    holder = {}

    def refresh():
        holder['win'].Tag.update(find_library.library_rows(find_library.list_libraries()),
                                 status=find_library.folder())

    def rename(paths_):
        old = find_library.load(paths_[0])
        new = forms.ask_string('New name for the library:', old['name'] if old else '', 'Rename library')
        if new is None:
            return
        try:
            find_library.rename(paths_[0], new)
        except ValueError as error:
            toast.error('Could not rename the library', str(error))
            return
        refresh()
        toast.success("Renamed to '%s'" % new.strip())

    def delete(paths_):
        names = [os.path.splitext(os.path.basename(p))[0] for p in paths_]
        if not forms.confirm('Delete %s? Everyone using the shared folder loses %s.' % (
                ', '.join(names), 'it' if len(names) == 1 else 'them'), 'Delete libraries'):
            return
        for p in paths_:
            find_library.delete(p)
        refresh()
        toast.success('Deleted %d %s' % (len(names), 'library' if len(names) == 1 else 'libraries'))

    holder['win'] = ui.build_table('Sets libraries', ['Library', 'Sets', 'Updated', 'By'],
                                   find_library.library_rows(libraries),
                                   actions=[('Rename', rename), ('Delete', delete),
                                            {'label': 'Open folder', 'needs_selection': False,
                                             'fn': lambda values: ui.show_in_explorer(find_library.folder())}],
                                   status=find_library.folder(), width=760, height=480)
    ui.show_modal(holder['win'])


if document is None:
    toast.info('No model open', 'Open a model first.')
else:
    choice = forms.ask_options('Share search sets between models and with your team.',
                               [PUBLISH, IMPORT, MANAGE], title='Sets Library')
    if choice == PUBLISH:
        publish()
    elif choice == IMPORT:
        import_sets()
    elif choice == MANAGE:
        manage()

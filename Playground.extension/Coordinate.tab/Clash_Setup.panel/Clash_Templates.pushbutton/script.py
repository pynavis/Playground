"""Saves clash test definitions as named templates and builds them again in other models."""
from pynavis import forms, output, script, toast

from namo import clashtemplates, naming, paths, progress, ui
from namo import clashset_common as common
from namo import clashset_tests as defs
from namo.htmlreport import escape

ACTIONS = [('Save tests as a template', 'save'), ('Apply a template to this model', 'apply'),
           ('Import templates from a file', 'import'), ('Export templates to a file', 'export'),
           ('Delete templates', 'delete')]
DEFAULTS = {'tests': [], 'existing': 'skip', 'run': False, 'last': ''}
JSON_FILTER = 'Playground templates (*.json)|*.json|All files (*.*)|*.*'
TITLE = 'Clash Templates'


def template_rows(store):
    rows = []
    for name in store.names():
        info = store.info(name) or {}
        rows.append({'value': name, 'cells': [name, clashtemplates.describe(store.get(name)),
                                              (info.get('updated') or '')[:10], info.get('user') or '']})
    return rows


def pick_templates(store, prompt, multiselect, checked=None, ok='OK'):
    rows = template_rows(store)
    if not rows:
        toast.info('No clash templates yet', 'Save tests as a template first, or import a template file.')
        return None
    return ui.choose(TITLE, rows, ['Template', 'Tests', 'Saved', 'By'], multiselect=multiselect,
                     checked=checked, prompt=prompt, ok=ok)


def save(values, doc):
    problem = common.clash_problem(doc)
    if problem:
        toast.show(*problem)
        return
    tests = common.choose_tests(TITLE, 'Tick the tests to keep in the template.', values['tests'],
                                only_with_results=False, doc=doc)
    if tests is None:
        return
    if not tests:
        toast.info('No tests ticked', 'Tick the tests to keep, then save the template.')
        return
    definitions, unread = clashtemplates.read_tests(tests, doc, with_failures=True)
    custom = [d for d in definitions if d['type'] not in defs.TYPE_KEYS]
    definitions = [d for d in definitions if d['type'] in defs.TYPE_KEYS]
    if not definitions:
        if unread and not custom:
            toast.error('Could not read the tests', 'Navisworks would not give the settings of %s.'
                        % unread[0])
        else:
            toast.warning('Nothing to save', 'Custom (plugin) clash tests cannot be kept in a template.')
        return
    store = clashtemplates.store()
    text, _missing = naming.render('{file} clash tests', naming.standard_values(doc))
    default = naming.sanitize(text)
    if default.lower() == 'clash tests':
        default = 'Clash tests'
    name = forms.ask_string('Name of the template:', default, TITLE)
    if name is None:
        return
    name = name.strip()
    if not name:
        toast.info('The template needs a name', 'Run Clash Templates again and type one.')
        return
    if store.info(name) is not None and not forms.confirm('Replace the template "%s"?' % name, TITLE):
        return
    from pynavis import doc as pdoc
    config = clashtemplates.template_config(definitions, pdoc.get_title(doc), defs.doc_units(doc))
    try:
        stored = store.save(name, config)
    except (IOError, OSError, ValueError) as error:
        toast.error('Could not save the template', str(error))
        return
    values['tests'] = [t.DisplayName for t in tests]
    values['last'] = stored
    script.save_config(values)
    notes = clashtemplates.portability_notes(definitions)
    if custom:
        notes.insert(0, '%s left out (custom tests).' % common.plural(len(custom), 'plugin test'))
    if unread:
        notes.insert(0, '%s could not be read and %s left out, starting with %s.' % (
            common.plural(len(unread), 'test'), 'was' if len(unread) == 1 else 'were', unread[0]))
    where = 'the team folder' if paths.team_available() else 'your templates'
    if notes:
        toast.warning('Saved "%s" with %s' % (stored, common.plural(len(definitions), 'test')), notes[0])
    else:
        toast.success('Saved "%s" with %s' % (stored, common.plural(len(definitions), 'test')),
                      'Kept in %s; apply it in any model with Clash Templates.' % where)


def report_failures(results, name):
    output.set_title(TITLE)
    output.print_md('# %s' % name)
    lines = ['<table class="pynavis"><tr><th>Test</th><th>Result</th><th>Why</th></tr>']
    for result in results:
        if result['outcome'] in ('created', 'updated'):
            continue
        lines.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            escape(result['name']), 'Left as it was' if result['outcome'] == 'skipped' else 'Not built',
            escape(result['detail'])))
    lines.append('</table>')
    output.print_html(''.join(lines))


def apply_template(values, doc):
    if not defs.available(doc):
        toast.error('Clash Detective is not available', 'Clash Templates needs Navisworks Manage.')
        return
    store = clashtemplates.store()
    picked = pick_templates(store, 'Choose the template to apply to this model.', False,
                            [values['last']] if values['last'] else None, 'Next')
    if picked is None:
        return
    name = picked[0]
    plan_rows = clashtemplates.plan(store.get(name), doc)
    if not plan_rows:
        toast.info('"%s" holds no tests' % name, 'Save tests into it first.')
        return
    units = defs.doc_units(doc)
    table = [{'value': i, 'cells': clashtemplates.plan_cells(row, units)} for i, row in enumerate(plan_rows)]
    ready = [i for i, row in enumerate(plan_rows) if row['status'] in ('ready', 'recreate')]
    chosen_ids = ui.choose('Apply %s' % name, table,
                           ['Test', 'Type', 'Tolerance', 'Selection A', 'Selection B', 'Status'],
                           multiselect=True, checked=ready, ok='Next', width=1000,
                           prompt='Tick the tests to build. The Status column names anything missing '
                                  'from this model.')
    if chosen_ids is None:
        return
    chosen = [plan_rows[i] for i in chosen_ids]
    blocked = [row for row in chosen if not clashtemplates.buildable(row)]
    chosen = [row for row in chosen if clashtemplates.buildable(row)]
    if not chosen:
        reason = blocked[0]['problems'][0] if blocked and blocked[0]['problems'] else \
            'Every chosen test is missing selection sets or models in this model.'
        toast.warning('None of the chosen tests can be built', reason)
        return
    fields = []
    if any(row['status'] == 'exists' for row in chosen):
        fields.append({'kind': 'radio', 'key': 'existing', 'label': 'Tests that already exist',
                       'default': values['existing'], 'fallback': None,
                       'options': [('Leave them as they are', 'skip'),
                                   ('Update their settings (their results are kept)', 'update')]})
    fields.append({'kind': 'check', 'key': 'run', 'label': 'Run the tests after building them',
                   'default': values['run']})
    recreate = sum(len(row['recreate']) for row in chosen)
    intro = 'Build %s from "%s".' % (common.plural(len(chosen), 'clash test'), name)
    if recreate:
        intro += ' Missing search sets are rebuilt from the template.'
    answers = ui.form('Apply %s' % name, fields, intro=intro, ok='Build')
    if answers is None:
        return
    values.update(answers)
    values['last'] = name
    script.save_config(values)
    results, recreated = common.write_progress('Applying %s' % name, lambda report_to: clashtemplates.apply(
        chosen, answers.get('existing', 'skip'), doc, report_to))
    built = [r['test'] for r in results if r['outcome'] in ('created', 'updated') and r['test'] is not None]
    found = None
    run_problem = None
    if answers['run'] and built:
        try:
            outcome = progress.run('Running clash tests',
                                   lambda report_to: defs.run_tests(built, doc, report_to))
        except Exception as error:
            outcome = progress.CANCELLED
            run_problem = str(error)
        if outcome is not progress.CANCELLED:
            found = sum(outcome.values())
    created = sum(1 for r in results if r['outcome'] == 'created')
    updated = sum(1 for r in results if r['outcome'] == 'updated')
    failed = [r for r in results if r['outcome'] not in ('created', 'updated')]
    parts = []
    if updated:
        parts.append('%s updated' % '{:,}'.format(updated))
    if recreated:
        parts.append('%s rebuilt' % common.plural(recreated, 'selection set'))
    if found is not None:
        parts.append('%s found' % common.plural(found, 'clash', 'clashes'))
    if blocked:
        parts.append('%s missing items' % common.plural(len(blocked), 'test'))
    if failed:
        report_failures(failed, name)
        parts.append('%s not built (see the list)' % '{:,}'.format(len(failed)))
    headline = 'Built %s from "%s"' % (common.plural(created + updated, 'clash test'), name)
    if run_problem:
        parts.append('Navisworks could not run them (%s)' % run_problem)
    if failed or blocked or run_problem:
        toast.warning(headline, '; '.join(parts))
    else:
        toast.success(headline, '; '.join(parts) or None)


def import_templates():
    path = forms.open_file(filter=JSON_FILTER, title='Import clash templates')
    if path is None:
        return
    try:
        count = clashtemplates.store().import_file(path)
    except ValueError as error:
        toast.error('Could not import the templates', str(error))
        return
    except (IOError, OSError) as error:
        toast.error('Could not save the templates', str(error))
        return
    if not count:
        toast.info('The file holds no clash templates')
    else:
        toast.success('Imported %s' % common.plural(count, 'clash template'),
                      'A name already in use gets a number, like "Name (2)".')


def export_templates(doc):
    store = clashtemplates.store()
    names = pick_templates(store, 'Tick the templates to export.', True, ok='Export')
    if names is None:
        return
    path = common.ask_save_path('Export clash templates', '{file} - Clash templates', '.json',
                                JSON_FILTER, doc)
    if path is None:
        return
    try:
        count = store.export(path, names)
    except (IOError, OSError) as error:
        toast.error('Could not write the file', str(error))
        return
    toast.success('Exported %s' % common.plural(count, 'clash template'), path)


def delete_templates():
    store = clashtemplates.store()
    names = pick_templates(store, 'Tick the templates to delete.', True, ok='Delete')
    if names is None:
        return
    shared = ' Everyone using the team folder loses them too.' if paths.team_available() else ''
    if not forms.confirm('Delete %s?%s' % (common.plural(len(names), 'clash template'), shared), TITLE):
        return
    removed = 0
    for name in names:
        try:
            if store.delete(name):
                removed += 1
        except (IOError, OSError) as error:
            toast.error('Could not delete "%s"' % name, str(error))
            return
    toast.success('Deleted %s' % common.plural(removed, 'clash template'))


def run():
    from pynavis import doc as pdoc
    doc = pdoc.get_doc()
    picked = forms.ask_options('What do you want to do with clash templates?',
                               [label for label, _value in ACTIONS], TITLE)
    if picked is None:
        return
    action = dict(ACTIONS)[picked]
    values = script.get_config(DEFAULTS)
    if action == 'save':
        save(values, doc)
    elif action == 'apply':
        apply_template(values, doc)
    elif action == 'import':
        import_templates()
    elif action == 'export':
        export_templates(doc)
    else:
        delete_templates()


if globals().get('__runner__'):
    toast.warning(*common.RUNNER_MESSAGE)
else:
    run()

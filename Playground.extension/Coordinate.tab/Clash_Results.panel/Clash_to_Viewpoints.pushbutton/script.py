"""Saves a viewpoint for every chosen clash or group, in folders by test and group, with a comment."""
from pynavis import forms, script, toast

from namo import clashassign, naming, progress, ui
from namo import clashres_views as views
from namo import clashset_common as common
from namo import clashset_tests as defs

DEFAULTS = {'tests': [], 'statuses': ['New', 'Active'], 'mode': 'group',
            'folder': views.DEFAULT_FOLDER, 'name': views.DEFAULT_NAME, 'replace': False}
TITLE = 'Clash to Viewpoints'


def ask(values):
    fields = [
        {'kind': 'multi', 'key': 'statuses', 'label': 'Clashes with these statuses',
         'options': [(s, s) for s in common.STATUS_NAMES], 'default': values['statuses']},
        {'kind': 'radio', 'key': 'mode', 'label': 'Viewpoints', 'options': views.MODES,
         'default': values['mode'], 'fallback': None},
        {'kind': 'text', 'key': 'folder', 'label': 'Folders', 'default': values['folder'],
         'hint': '/ makes a folder. Tokens: {test} {group} {status} {level} {grid} {date}'},
        {'kind': 'text', 'key': 'name', 'label': 'Names', 'default': values['name'],
         'hint': 'Tokens: {name} {n:000} {status} {grid} {level} {distance} {model_a} {model_b}'},
        {'kind': 'check', 'key': 'replace', 'label': 'Replace viewpoints that already have the name',
         'default': values['replace']},
    ]

    def validate(answers):
        if not answers['statuses']:
            return {'statuses': 'Tick at least one status.'}
        if not answers['name'].strip():
            return {'name': 'Enter a name template, like {name}.'}
        return None

    return ui.form(TITLE, fields, ok='Next', validate=validate, width=520)


def run():
    from pynavis import doc as pdoc
    doc = pdoc.get_doc()
    problem = common.clash_problem(doc, need_results=True)
    if problem:
        toast.show(*problem)
        return
    values = script.get_config(DEFAULTS)
    tests = common.choose_tests(TITLE, 'Tick the tests to save viewpoints for.', values['tests'], doc=doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    answers = ask(values)
    if answers is None:
        return
    values.update(answers)
    values['tests'] = [t.DisplayName for t in tests]
    script.save_config(values)
    try:
        entries = common.read_entries(tests, doc)
    except RuntimeError as error:
        toast.error('Could not read the clashes', str(error))
        return
    if entries is progress.CANCELLED:
        return
    units_by_test = [(key, entry['name'], clashassign.units_of(entry)) for key, entry in enumerate(entries)]
    planned = views.plan(units_by_test, answers['mode'], answers['statuses'], answers['folder'],
                         answers['name'], defs.doc_units(doc), views.existing_names(doc),
                         naming.standard_values(doc))
    if not planned:
        toast.info('No clashes match', 'None of the chosen tests has %s clashes.'
                   % ' or '.join(answers['statuses']))
        return
    counts = views.counts(planned, answers['replace'])
    if not counts['create'] and not counts['replace']:
        toast.info('Every viewpoint already exists', 'Tick Replace to save them again.')
        return
    total = counts['create'] + counts['replace']
    if total > views.CONFIRM_ABOVE and not forms.confirm(
            'Save %s? A file with thousands of viewpoints opens and saves more slowly.'
            % common.plural(total, 'viewpoint'), TITLE):
        return
    items = views.items_by_ref(entries)
    totals = common.write_progress('Saving viewpoints', lambda report_to: views.create(
        planned, items, answers['replace'], doc, report_to))
    saved = totals['created'] + totals['replaced']
    where = views.top_folder(planned)
    parts = []
    if totals['replaced']:
        parts.append('%s replaced' % '{:,}'.format(totals['replaced']))
    if totals['skipped']:
        parts.append('%s skipped (the name exists)' % '{:,}'.format(totals['skipped']))
    if totals['failed']:
        parts.append('%s could not be saved' % '{:,}'.format(totals['failed']))
    headline = 'Saved %s%s' % (common.plural(saved, 'viewpoint'), ' in %s' % where if where else '')
    if not saved and totals['failed']:
        toast.error('Could not save the clash viewpoints',
                    'Navisworks gave no view for %s. Open Clash Detective, click a result of the '
                    'test once, then try again.' % common.plural(totals['failed'], 'clash', 'clashes'))
    elif totals['failed'] or not saved:
        toast.warning(headline, '; '.join(parts) or None)
    else:
        toast.success(headline, '; '.join(parts) or None)


if globals().get('__runner__'):
    toast.warning(*common.RUNNER_MESSAGE)
else:
    run()

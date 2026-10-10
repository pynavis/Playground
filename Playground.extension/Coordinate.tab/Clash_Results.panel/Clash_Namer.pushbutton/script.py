"""Renames clash results and result groups from a name template, with a live preview."""
from pynavis import script, toast

from namo import clashname, naming, progress, ui
from namo import clashset_common as common
from namo import clashset_tests as defs

DEFAULTS = {'clash_template': clashname.DEFAULT_CLASH, 'group_template': clashname.DEFAULT_GROUP,
            'scope': 'clashes', 'tests': [], 'threshold': clashname.DEFAULT_THRESHOLD}
TITLE = 'Clash Namer'


def run():
    from pynavis import doc as pdoc
    doc = pdoc.get_doc()
    problem = common.clash_problem(doc, need_results=True)
    if problem:
        toast.show(*problem)
        return
    values = script.get_config(DEFAULTS)
    tests = common.choose_tests(TITLE, 'Tick the tests whose clashes you want to rename.',
                                values['tests'], doc=doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    try:
        entries = common.read_entries(tests, doc)
    except RuntimeError as error:
        toast.error('Could not read the clashes', str(error))
        return
    if entries is progress.CANCELLED:
        return
    units = defs.doc_units(doc)
    standard = naming.standard_values(doc)
    readers = [clashname.category_reader(entry) for entry in entries]

    def preview(clash_template, group_template, scope):
        return clashname.preview(entries, clash_template, group_template, scope, units, readers,
                                 standard)

    win = clashname.build_window(preview, values, TITLE)
    ui.show_modal(win)
    state = win.Tag
    if not state.accepted:
        return
    choice = state.result
    values.update(choice)
    values['tests'] = [t.DisplayName for t in tests]
    script.save_config(values)
    plans = progress.run('Planning names', lambda report_to: clashname.plan_all(
        entries, choice['clash_template'], choice['group_template'], choice['scope'], units,
        readers, standard, report_to))
    if plans is progress.CANCELLED:
        return
    if not any(p['clashes'] or p['groups'] for p in plans):
        toast.info('Every name already matches this template')
        return
    try:
        result = common.write_progress('Renaming clashes', lambda report_to: clashname.apply(
            entries, plans, clashname.threshold_of(values), doc, report_to))
    except ValueError as error:
        toast.error('Could not rename the clashes', str(error))
        return
    detail = None
    if result['mode'] == 'rebuild':
        detail = 'Each test was rebuilt once with the new names. One undo step.'
    toast.success(clashname.result_text(result['clashes'], result['groups'], result['tests']), detail)


if globals().get('__runner__'):
    toast.warning(*common.RUNNER_MESSAGE)
else:
    run()

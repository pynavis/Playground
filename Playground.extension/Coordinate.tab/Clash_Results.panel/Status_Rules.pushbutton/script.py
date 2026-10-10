"""Sets clash statuses, assignees and notes with ordered rules that a team keeps and shares."""
import datetime

from pynavis import forms, script, toast

from namo import clashrules, progress, ui
from namo import clashset_common as common
from namo import clashset_tests as defs

DEFAULTS = {'tests': [], 'set': clashrules.EXAMPLES_NAME}
TITLE = 'Status Rules'
NEW_SET = '\x00new'


def run():
    from pynavis import doc as pdoc
    doc = pdoc.get_doc()
    problem = common.clash_problem(doc, need_results=True)
    if problem:
        toast.show(*problem)
        return
    values = script.get_config(DEFAULTS)
    tests = common.choose_tests(TITLE, 'Tick the tests the rules should look at.', values['tests'],
                                doc=doc)
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
    values['tests'] = [t.DisplayName for t in tests]
    units = defs.doc_units(doc)
    today = datetime.datetime.now()
    rows_by_test = dict((entry['name'], entry['rows']) for entry in entries)
    readers = dict((entry['name'], clashrules.element_reader(entry['leaves'])) for entry in entries)
    store = clashrules.store()
    names = clashrules.ensure_examples(store)
    set_name = values['set'] if values['set'] in names else (names[0] if names else 'My rules')
    rules = clashrules.rules_of(store.get(set_name)) if set_name in names else []

    def preview(rule_list):
        if not rule_list:
            return None
        compiled = [clashrules.compile_rule(rule, units)[0] for rule in rule_list]
        return clashrules.plan(rows_by_test, compiled, units, today, lambda name: readers[name])

    def edit_rule(rule):
        start = rule or {'name': 'New rule', 'conditions': [], 'status': 'Reviewed'}
        answers = ui.form('Status rule', clashrules.rule_form_fields(start), ok='OK', width=560,
                          validate=lambda answered: clashrules.validate_form(answered, units))
        return None if answers is None else clashrules.normalise_rule(answers)

    def save_set(state):
        try:
            store.save(state.set_name, clashrules.rule_set_config(state.rules))
        except (IOError, OSError, ValueError) as error:
            toast.error('Could not save the rule set', str(error))
            return False
        state.dirty = False
        state.refresh()
        return True

    def on_save(state):
        if save_set(state):
            toast.success('Saved the rule set "%s"' % state.set_name)

    def on_switch(state):
        if state.dirty and not forms.confirm('Discard your changes to "%s"?' % state.set_name, TITLE):
            return
        rows = [{'value': name, 'cells': [name, common.plural(len(clashrules.rules_of(store.get(name))),
                                                             'rule')]} for name in store.names()]
        rows.append({'value': NEW_SET, 'cells': ['New rule set', '']})
        picked = ui.choose('Rule sets', rows, ['Rule set', 'Rules'], multiselect=False,
                           checked=[state.set_name], ok='Open', width=480, height=420)
        if picked is None:
            return
        if picked[0] == NEW_SET:
            name = forms.ask_string('Name of the new rule set:', '', TITLE)
            if name is None or not name.strip():
                return
            state.load(name.strip(), [])
            state.dirty = True
            state.refresh()
        else:
            state.load(picked[0], clashrules.rules_of(store.get(picked[0])))

    win = clashrules.build_window(set_name, rules, preview, units, edit_rule, on_save, on_switch, TITLE)
    ui.show_modal(win)
    state = win.Tag
    values['set'] = state.set_name
    script.save_config(values)
    if not state.accepted:
        if state.dirty and forms.confirm('Save your changes to the rule set "%s"?' % state.set_name, TITLE):
            if save_set(state):
                toast.success('Saved the rule set "%s"' % state.set_name)
        return
    if state.dirty:
        save_set(state)
    planned = preview(state.result['rules'])
    if not planned or not planned['changed']:
        toast.info('No clash needs a change', 'Every matching clash already has what its rule sets.')
        return
    entries_by_name = dict((entry['name'], entry) for entry in entries)
    try:
        totals = common.write_progress('Applying status rules', lambda report_to: clashrules.apply(
            entries_by_name, planned, doc, report_to))
    except ValueError as error:
        toast.error('Could not update the clashes', str(error))
        return
    parts = []
    if totals['status']:
        parts.append('%s changed' % common.plural(totals['status'], 'status', 'statuses'))
    if totals['assign']:
        parts.append('%s assigned' % '{:,}'.format(totals['assign']))
    if totals['notes']:
        parts.append('%s added' % common.plural(totals['notes'], 'comment'))
    toast.success('Updated %s in %s' % (common.plural(planned['changed'], 'clash', 'clashes'),
                                        common.plural(totals['tests'], 'test')),
                  ', '.join(parts) + '. One undo step.')


if globals().get('__runner__'):
    toast.warning(*common.RUNNER_MESSAGE)
else:
    run()

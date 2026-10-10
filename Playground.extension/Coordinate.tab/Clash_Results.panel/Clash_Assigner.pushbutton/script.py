"""Assigns clash groups and ungrouped clashes to the trade that moves, and tracks ball in court."""
import datetime

from pynavis import forms, script, toast

from namo import clashassign, config, progress, ui
from namo import clashset_common as common

DEFAULTS = {'tests': [], 'priority': list(clashassign.DEFAULT_PRIORITY), 'names': '',
            'reassign': False, 'mode': 'auto'}
TITLE = 'Clash Assigner'
MODES = [('Auto: the lower-priority trade of each clash moves', 'auto'),
         ('Manual: pick a trade or person for chosen items', 'manual'),
         ('Show the ball-in-court dashboard', 'dashboard')]
SOMEONE = '\x00someone'


def pick_assignee(values, units):
    """A trade or person for manual mode, or None."""
    names = clashassign.names_map(values['names'])
    choices = []
    for trade in config.get('trades') or clashassign.DEFAULT_PRIORITY:
        person = names.get(trade.lower())
        choices.append((trade if not person else person, trade))
    for unit in units:
        current = unit.get('assigned')
        if current and current not in [c[0] for c in choices]:
            choices.append((current, 'already used'))
    rows = [{'value': name, 'cells': [name, note if note != name else '']} for name, note in choices]
    rows.append({'value': SOMEONE, 'cells': ['Someone else...', 'type a name']})
    picked = ui.choose(TITLE, rows, ['Assign to', 'Trade'], multiselect=False, ok='Assign',
                       prompt='Who has the ball for these items?', width=520, height=480)
    if picked is None:
        return None
    if picked[0] != SOMEONE:
        return picked[0]
    typed = forms.ask_string('Assign to:', '', TITLE)
    if typed is None or not typed.strip():
        return None
    return typed.strip()


def write(pairs, mode, doc):
    changes = common.write_progress('Assigning clashes', lambda report_to: clashassign.assign(pairs, doc))
    try:
        note = clashassign.save_history(changes, mode, doc)
    except (IOError, OSError) as error:
        return 'The ball-in-court history could not be saved (%s).' % error
    if note:
        return note
    return 'Ball-in-court history saved in the model; save the file to keep it.'


def run():
    from pynavis import doc as pdoc
    doc = pdoc.get_doc()
    problem = common.clash_problem(doc, need_results=True)
    if problem:
        toast.show(*problem)
        return
    values = script.get_config(DEFAULTS)
    tests = common.choose_tests(TITLE, 'Tick the tests to assign.', values['tests'], doc=doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    labels = [label for label, _value in MODES]
    picked = forms.ask_options('How do you want to assign?', labels, TITLE)
    if picked is None:
        return
    mode = dict(MODES)[picked]
    values['mode'] = mode
    values['tests'] = [t.DisplayName for t in tests]
    script.save_config(values)
    try:
        entries = common.read_entries(tests, doc)
    except RuntimeError as error:
        toast.error('Could not read the clashes', str(error))
        return
    if entries is progress.CANCELLED:
        return
    units = []
    for entry in entries:
        units.extend(clashassign.units_of(entry))
    title = 'Ball in court: %s' % (pdoc.get_title(doc) or 'this model')
    today = datetime.datetime.now()
    if mode == 'dashboard':
        board = clashassign.show_dashboard(units, clashassign.load_owners(doc), today, title)
        toast.info('%s open across %s' % (common.plural(board['open'], 'item'),
                                          common.plural(len(board['by_assignee']), 'assignee')))
        return
    if mode == 'auto':
        planned = clashassign.plan_auto(units, clashassign.priority_list(values['priority']),
                                        clashassign.names_map(values['names']), values['reassign'])
        if not planned['assign']:
            reason = 'Every open item already has an assignee.' if planned['kept'] else \
                'No trade could be decided; add trade rules in Playground settings.'
            toast.info('Nothing to assign', reason)
            return
        if not forms.confirm(clashassign.confirm_text(planned), TITLE):
            return
        pairs = planned['assign']
    else:
        rows = [{'value': i, 'cells': clashassign.unit_cells(unit)} for i, unit in enumerate(units)
                if unit['open']]
        if not rows:
            toast.info('Nothing to assign', 'Every item in these tests is resolved or approved.')
            return
        chosen = ui.choose(TITLE, rows, ['Test', 'Item', 'Kind', 'Clashes', 'Status', 'Assigned to',
                                         'Trades'], multiselect=True, ok='Next', width=980,
                           prompt='Tick the groups and clashes to assign.')
        if chosen is None:
            return
        who = pick_assignee(values, units)
        if who is None:
            return
        pairs = [(units[i], who) for i in chosen]
    try:
        note = write(pairs, mode, doc)
    except ValueError as error:
        toast.error('Could not assign the clashes', str(error))
        return
    clashassign.show_dashboard(units, clashassign.load_owners(doc), today, title)
    tally = clashassign.tally_names(pairs)
    detail = '%s. %s' % (', '.join('%s %s' % (name, '{:,}'.format(n)) for name, n in tally[:4]), note)
    toast.success('Assigned %s' % common.plural(len(pairs), 'item'), detail)


if globals().get('__runner__'):
    toast.warning(*common.RUNNER_MESSAGE)
else:
    run()

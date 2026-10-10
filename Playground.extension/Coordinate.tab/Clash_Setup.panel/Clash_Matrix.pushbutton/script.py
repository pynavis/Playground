"""Builds a battery of clash tests from a workbook of trades and a test matrix."""
import os

from pynavis import forms, output, script, toast

from namo import clashmatrix, config, naming, progress, ui
from namo import clashset_common as common
from namo import clashset_tests as defs
from namo.htmlreport import escape

DEFAULTS = {'action': 'build', 'workbook': '', 'name_template': clashmatrix.DEFAULT_NAME,
            'existing': 'skip', 'run': False}
FILTER = 'Excel workbooks (*.xlsx)|*.xlsx'
OUTCOMES = {'created': 'Created', 'updated': 'Updated', 'skipped': 'Left as it was',
            'failed': 'Not built'}


def ask(values):
    # Nothing to build from yet (first run, or the workbook has gone): start on the
    # template, which is the only thing that can work.
    action = values['action']
    if not values['workbook'] or not os.path.isfile(values['workbook']):
        action = 'template'
    fields = [
        {'kind': 'radio', 'key': 'action', 'label': 'What to do', 'default': action, 'fallback': None,
         'options': [('Build clash tests from a workbook', 'build'),
                     ('Write a template workbook to fill in', 'template')]},
        {'kind': 'file_open', 'key': 'workbook', 'label': 'Workbook', 'default': values['workbook'],
         'filter': FILTER, 'title': 'Open the clash matrix workbook', 'enabled_if': ('action', 'build')},
        {'kind': 'text', 'key': 'name_template', 'label': 'Test names',
         'default': values['name_template'], 'enabled_if': ('action', 'build'),
         'hint': 'Tokens: {a} {b} {type} {tolerance} {code} {n:00}'},
        {'kind': 'radio', 'key': 'existing', 'label': 'Tests that already exist',
         'default': values['existing'], 'fallback': None, 'enabled_if': ('action', 'build'),
         'options': [('Leave them as they are', 'skip'),
                     ('Update their settings (their results are kept)', 'update')]},
        {'kind': 'check', 'key': 'run', 'label': 'Run the tests after building them',
         'default': values['run'], 'enabled_if': ('action', 'build')},
    ]

    def validate(answers):
        if answers['action'] == 'build' and not answers['workbook']:
            return {'workbook': 'Choose the workbook to build from, or write a template first.'}
        if answers['action'] == 'build' and not answers['name_template'].strip():
            return {'name_template': 'Enter a name template, like {a} vs {b}.'}
        return None

    return ui.form('Clash Matrix', fields, ok='Continue', validate=validate,
                   intro='Trades on one sheet, a test matrix on another: each code builds a test.')


def write_template(doc):
    path = common.ask_save_path('Save the clash matrix template', '{file} - Clash matrix', '.xlsx',
                                FILTER, doc)
    if path is None:
        return
    rows = clashmatrix.template_rows(doc)
    try:
        clashmatrix.write_template(path, rows, defs.doc_units(doc), author=config.user_name())
    except (IOError, OSError):
        toast.error('Could not write the template', 'Close the file in Excel, then try again.')
        return
    ui.open_path(path)
    toast.success('Wrote a clash matrix template with %s' % common.plural(len(rows), 'trade'),
                  'Fill in the Matrix sheet with codes like H or C 50mm, save it, then build.')


def confirm_text(tests, existing_mode, doc, workbook, problems):
    present = set(n.lower() for n in defs.test_names(doc))
    already = sum(1 for t in tests if t['name'].lower() in present)
    lines = ['Build %s from %s?' % (common.plural(len(tests), 'clash test'), os.path.basename(workbook))]
    if already:
        lines.append('%s already exist%s and will be %s.' % (
            common.plural(already, 'test'), 's' if already == 1 else '',
            'updated (results kept)' if existing_mode == 'update' else 'left as they are'))
    if problems:
        lines.append('')
        lines.append('%s will be skipped, starting with:' % common.plural(len(problems), 'problem'))
        lines.append(problems[0])
    return '\n'.join(lines)


def report(rows, counts, problems, notes, workbook, doc):
    units = defs.doc_units(doc)
    output.set_title('Clash Matrix')
    output.print_md('# Clash Matrix')
    output.print_md('Built from %s.' % os.path.basename(workbook))
    cells = ['<table class="pynavis"><tr><th>Test</th><th>Selection A</th><th>Selection B</th>'
             '<th>Type</th><th>Tolerance</th><th>Result</th><th>Follows sets</th>'
             '<th class="num">Clashes</th><th>Note</th></tr>']
    for row in rows:
        clashes = ''
        if row['test'] is not None and counts:
            try:
                clashes = counts.get(str(row['test'].Guid), '')
            except Exception:
                clashes = ''
        cells.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                     '<td>%s</td><td class="num">%s</td><td>%s</td></tr>' % (
                         escape(row['name']), escape(row['a']), escape(row['b']),
                         escape(defs.TYPE_LABELS.get(row['type'], row['type'])),
                         escape(defs.tolerance_text(row['tolerance_m'], units) or '0'),
                         escape(OUTCOMES[row['outcome']]),
                         'Yes' if row['linked'] else ('' if row['outcome'] in ('failed', 'skipped') else 'No'),
                         '' if clashes == '' else '{:,}'.format(clashes), escape(row['detail'])))
    cells.append('</table>')
    output.print_html(''.join(cells))
    if problems:
        output.print_md('## Skipped')
        output.print_md('\n'.join('- %s' % p for p in problems[:200]))
    if notes:
        output.print_md('\n'.join('- %s' % n for n in notes))


def build(values, doc):
    units = defs.doc_units(doc)
    workbook = values['workbook']
    try:
        trades, entries, problems = clashmatrix.read_workbook(workbook, units)
    except Exception as error:
        toast.error('Could not read the workbook', '%s: %s' % (os.path.basename(workbook), error))
        return
    if not trades and problems:
        toast.error('The workbook cannot be used', problems[0])
        return
    tests, plan_problems, notes = clashmatrix.plan_tests(trades, entries, values['name_template'],
                                                        units, naming.standard_values(doc))
    problems = problems + plan_problems
    if not tests:
        if problems:
            toast.warning('No clash tests to build', problems[0])
        else:
            toast.info('No clash tests to build',
                       'Put codes like H or C 50mm in the Matrix sheet, save it, and build again.')
        return
    if not forms.confirm(confirm_text(tests, values['existing'], doc, workbook, problems), 'Clash Matrix'):
        return
    rows = common.write_progress('Building clash tests', lambda report_to: clashmatrix.build(
        tests, trades, values['existing'], doc, report_to))
    built = [r['test'] for r in rows if r['outcome'] in ('created', 'updated') and r['test'] is not None]
    counts = {}
    stopped = False
    run_problem = None
    if values['run'] and built:
        try:
            outcome = progress.run('Running clash tests',
                                   lambda report_to: defs.run_tests(built, doc, report_to))
        except Exception as error:
            outcome = None
            run_problem = str(error)
        if outcome is progress.CANCELLED:
            stopped = True
        elif outcome is not None:
            counts = outcome
    report(rows, counts, problems, notes, workbook, doc)
    tally = dict((key, sum(1 for r in rows if r['outcome'] == key)) for key in OUTCOMES)
    parts = []
    if tally['created']:
        headline = 'Built %s' % common.plural(tally['created'], 'clash test')
        if tally['updated']:
            parts.append('%s updated' % '{:,}'.format(tally['updated']))
    else:
        headline = 'Updated %s' % common.plural(tally['updated'], 'clash test')
    if tally['skipped']:
        parts.append('%s left as they were' % '{:,}'.format(tally['skipped']))
    if tally['failed']:
        parts.append('%s could not be built' % '{:,}'.format(tally['failed']))
    if run_problem:
        parts.append('Navisworks could not run them (%s)' % run_problem)
    elif stopped:
        parts.append('running was stopped')
    elif counts:
        parts.append('%s found' % common.plural(sum(counts.values()), 'clash', 'clashes'))
    detail = '; '.join(parts) or None
    if not tally['created'] and not tally['updated']:
        toast.warning('No clash tests were built', detail)
    elif tally['failed'] or run_problem:
        toast.warning(headline, detail)
    else:
        toast.success(headline, detail)


def run():
    from pynavis import doc as pdoc
    doc = pdoc.get_doc()
    if not defs.available(doc):
        toast.error('Clash Detective is not available', 'Clash Matrix needs Navisworks Manage.')
        return
    values = script.get_config(DEFAULTS)
    answers = ask(values)
    if answers is None:
        return
    values.update(answers)
    script.save_config(values)
    if answers['action'] == 'template':
        write_template(doc)
    else:
        build(values, doc)


if globals().get('__runner__'):
    toast.warning(*common.RUNNER_MESSAGE)
else:
    run()

# -*- coding: utf-8 -*-
"""Writes Playground issues or clash results to a BCF 2.1 or 3.0 file."""
import datetime
import os

from pynavis import forms, script, toast

from namo import bcf_exchange, issue_clash, issueapi, issues, issuestore, naming, progress, ui

DEFAULTS = {'source': 'issues', 'version': '2.1', 'statuses': ['Open', 'In progress', 'Resolved'],
            'tests': [], 'clash_statuses': list(issue_clash.OPEN_CLASH), 'snapshots': True}
CLASH_STATUSES = ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']


def _test_names(doc):
    try:
        from namo import clashdata
        return [clashdata.test_path(t) for t in clashdata.tests(doc)]
    except Exception:
        return []


def _default_path(store, source):
    stem = os.path.splitext(os.path.basename(store.doc_path))[0] if store.saved else 'Navisworks'
    name = naming.sanitize('%s - %s - %s.bcf' % (stem, 'Issues' if source == 'issues' else 'Clashes',
                                                     datetime.date.today().strftime('%Y-%m-%d')),
                           for_file=True)
    folder = os.path.dirname(store.doc_path) if store.saved else ''
    return os.path.join(folder, name) if folder and os.path.isdir(folder) else name


def run():
    doc = issuestore.active_doc()
    if doc is None or not issueapi.has_model(doc):
        toast.info('No model open', 'Open the model to export from.')
        return
    store = issuestore.for_doc(doc)
    me = script.bind()
    values = me.get_config(dict(DEFAULTS))
    tests = _test_names(doc)
    sources = [('Issues from the register', 'issues')]
    if tests:
        sources.append(('Clash results (groups and ungrouped clashes)', 'clash'))
    source = values['source'] if values['source'] in [v for _l, v in sources] else 'issues'
    fields = [
        {'kind': 'radio', 'key': 'source', 'label': 'Export', 'options': sources, 'default': source, 'fallback': None},
        {'kind': 'radio', 'key': 'version', 'label': 'BCF version', 'inline': True,
         'options': [('2.1 (read by most tools)', '2.1'), ('3.0', '3.0')], 'default': values['version'], 'fallback': None},
        {'kind': 'multi', 'key': 'statuses', 'label': 'Issues with status', 'options': issues.STATUSES,
         'default': [s for s in values['statuses'] if s in issues.STATUSES],
         'enabled_if': ('source', 'issues')},
    ]
    if tests:
        # ui.form refuses a multi field without options, so the clash fields only exist
        # when the model has clash tests.
        fields += [
            {'kind': 'multi', 'key': 'tests', 'label': 'Clash tests', 'options': tests,
             'default': [t for t in values['tests'] if t in tests] or tests,
             'enabled_if': ('source', 'clash')},
            {'kind': 'multi', 'key': 'clash_statuses', 'label': 'Clashes with status',
             'options': CLASH_STATUSES,
             'default': [s for s in values['clash_statuses'] if s in CLASH_STATUSES],
             'enabled_if': ('source', 'clash')},
        ]
    elif not store.saved:
        toast.info('Save the model first', issuestore.NOT_SAVED)
        return
    fields.append({'kind': 'check', 'key': 'snapshots', 'label': 'Include snapshots',
                   'default': bool(values['snapshots'])})

    def check(answers):
        if answers['source'] == 'issues':
            if not store.saved:
                return {'source': 'Save the model first: issues are kept with the model file.'}
            if not answers['statuses']:
                return {'statuses': 'Tick at least one status.'}
        else:
            if not answers.get('tests'):
                return {'tests': 'Tick at least one clash test.'}
            if not answers.get('clash_statuses'):
                return {'clash_statuses': 'Tick at least one status.'}
        return None

    answers = ui.form('BCF Export', fields, ok='Choose file', width=540, validate=check)
    if answers is None:
        return
    values.update(answers)
    me.save_config(values)
    rows = []
    if answers['source'] == 'issues':
        rows = issues.filter_issues(store.list(), status=answers['statuses'])
        if not rows:
            toast.info('No issues to export', 'No issue has the ticked statuses.')
            return
    # .bcf is the extension of BCF 2.1 and 3.0 (.bcfzip was 2.0's); every reader takes both.
    path = forms.save_file(filter='BCF files (*.bcf)|*.bcf|BCF zip files (*.bcfzip)|*.bcfzip|All files (*.*)|*.*',
                           default_name=_default_path(store, answers['source']), title='Export BCF')
    if path is None:
        return
    version = answers['version']
    try:
        if answers['source'] == 'issues':
            outcome = progress.run('BCF export', lambda report: bcf_exchange.export_issues(
                path, rows, version, doc, answers['snapshots'], report))
        else:
            outcome = progress.run('BCF export', lambda report: bcf_exchange.export_clashes(
                path, answers['tests'], answers['clash_statuses'], version, doc,
                answers['snapshots'], report))
    except (IOError, OSError) as error:
        toast.error('Could not write the BCF file', '%s Close it in other programs, then try again.' % error)
        return
    if outcome is progress.CANCELLED:
        return
    if not outcome['topics']:
        toast.info('Nothing to export', 'No clash group or clash had the ticked statuses.')
        return
    notes = list(outcome.get('notes') or [])
    if outcome.get('skipped_components'):
        notes.insert(0, '%d element%s without an IFC GUID left out of the components.'
                     % (outcome['skipped_components'], '' if outcome['skipped_components'] == 1 else 's'))
    detail = '%s, %d snapshot%s.' % (os.path.basename(path), outcome['snapshots'],
                                     '' if outcome['snapshots'] == 1 else 's')
    if notes:
        detail += ' ' + notes[0]
    elif (outcome.get('adjusted') or {}).get('fov'):
        # Not a loss: the camera stands and looks where it did, through a lens BCF 2.1 allows.
        detail += ' Views were written with a 45 to 60 degree lens, the range BCF 2.1 allows.'
    toast.show('warning' if notes else 'success',
               'Exported %s topic%s to BCF %s' % ('{:,}'.format(outcome['topics']),
                                                  '' if outcome['topics'] == 1 else 's', version),
               detail)


run()

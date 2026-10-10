# -*- coding: utf-8 -*-
"""The questions the Clash Reports buttons ask, in one place.

Field lists for namo.ui.form are built by pure functions (so dev/tests/smoke_clashrep_forms
builds every one of them under IronPython + WPF); the helpers below them run the dialogs:
picking tests (namo.clashset_common.choose_tests, the same picker as the Clash Results
tools, remembering the choice by test path), the thumbnail confirm, and the report run
behind Playground's cancellable progress window.

Cancelling any question returns None and the button exits without a toast.
"""

from namo import clashreport as cr

STATUS_OPTIONS = [(s, s) for s in cr.STATUSES]
XLSX_FILTER = 'Excel workbooks (*.xlsx)|*.xlsx'
HTML_FILTER = 'Web pages (*.html)|*.html'
IMAGES_CAPPED = 'capped'
IMAGES_ALL = 'all'
IMAGES_NONE = 'none'


def _statuses_field(values, label='List clashes with these statuses'):
    return {'kind': 'multi', 'key': 'statuses', 'label': label, 'options': STATUS_OPTIONS,
            'default': cr.ordered_statuses(values.get('statuses') or cr.OPEN)}


def need_status(answers):
    """ui.form validate: at least one status ticked."""
    if 'statuses' in answers and not answers['statuses']:
        return {'statuses': 'Tick at least one status.'}
    return None


def excel_fields(values, path):
    return [
        _statuses_field(values),
        {'kind': 'check', 'key': 'images', 'label': 'Add a thumbnail of each clash (160 x 90)',
         'default': bool(values.get('images', True))},
        {'kind': 'file_save', 'key': 'path', 'label': 'Save the workbook as', 'default': path,
         'filter': XLSX_FILTER, 'default_name': '', 'required': True, 'title': 'Save the clash report'},
        {'kind': 'check', 'key': 'open', 'label': 'Open it when it is saved', 'default': bool(values.get('open', True))},
    ]


def dashboard_fields(values, path):
    return [
        _statuses_field(values, 'List clashes with these statuses in the table'),
        {'kind': 'label', 'text': 'The headline numbers and charts always count every status.', 'muted': True},
        {'kind': 'check', 'key': 'images', 'label': 'Show a thumbnail of each listed clash',
         'default': bool(values.get('images', True))},
        {'kind': 'file_save', 'key': 'path', 'label': 'Save the dashboard as', 'default': path,
         'filter': HTML_FILTER, 'required': True, 'title': 'Save the clash dashboard'},
    ]


def matrix_fields(values, path):
    return [
        {'kind': 'radio', 'key': 'axis', 'label': 'Count clashes between', 'inline': True,
         'options': [('Trades', 'trade'), ('Models', 'model')], 'default': values.get('axis') or 'trade', 'fallback': 'trade'},
        {'kind': 'check', 'key': 'xlsx', 'label': 'Also save an Excel workbook', 'default': bool(values.get('xlsx'))},
        {'kind': 'file_save', 'key': 'path', 'label': 'Workbook', 'default': path, 'filter': XLSX_FILTER,
         'required': True, 'enabled_if': ('xlsx', True), 'title': 'Save the clash matrix'},
    ]


def delta_fields(values, choices, chosen, path):
    """choices: [(text, snapshot id)] newest first; chosen: the default id."""
    return [
        {'kind': 'choice', 'key': 'baseline', 'label': 'Compare now with the snapshot', 'options': choices,
         'default': chosen, 'fallback': None},
        {'kind': 'check', 'key': 'select', 'label': 'Select the items of the new clashes when done',
         'default': bool(values.get('select'))},
        {'kind': 'check', 'key': 'xlsx', 'label': 'Also save an Excel workbook', 'default': bool(values.get('xlsx'))},
        {'kind': 'file_save', 'key': 'path', 'label': 'Workbook', 'default': path, 'filter': XLSX_FILTER,
         'required': True, 'enabled_if': ('xlsx', True), 'title': 'Save the clash delta'},
    ]


def trends_fields(values, path):
    return [
        {'kind': 'radio', 'key': 'series', 'label': 'Draw',
         'options': [('Open and resolved, the chosen tests together', 'total'), ('Open clashes per test', 'per_test')],
         'default': values.get('series') or 'total', 'fallback': 'total'},
        {'kind': 'check', 'key': 'current', 'label': 'Add the current state as the last point (reads the tests now)',
         'default': bool(values.get('current', True))},
        {'kind': 'radio', 'key': 'export', 'label': 'Also save', 'inline': True,
         'options': [('Nothing', 'none'), ('Excel workbook', 'xlsx'), ('CSV file', 'csv'), ('Both', 'both')],
         'default': export_of(values)},
        {'kind': 'file_save', 'key': 'path', 'label': 'File', 'default': path, 'filter': XLSX_FILTER,
         'required': True, 'enabled_if': ('export', ['xlsx', 'csv', 'both']), 'title': 'Save the clash trends',
         'hint': 'A CSV takes the same name with .csv.'},
    ]


def export_of(values):
    """'none' | 'xlsx' | 'csv' | 'both' from saved xlsx / csv flags."""
    xlsx_on, csv_on = bool(values.get('xlsx')), bool(values.get('csv'))
    return 'both' if (xlsx_on and csv_on) else ('xlsx' if xlsx_on else ('csv' if csv_on else 'none'))


def per_trade_fields(values, folder, priority):
    return [
        _statuses_field(values),
        {'kind': 'check', 'key': 'html', 'label': 'Also write a dashboard (HTML) for each trade',
         'default': bool(values.get('html'))},
        {'kind': 'check', 'key': 'images', 'label': 'Add a thumbnail of each clash',
         'default': bool(values.get('images'))},
        {'kind': 'folder', 'key': 'folder', 'label': 'Write the files into', 'default': folder, 'required': True,
         'title': 'Folder for the trade reports'},
        {'kind': 'check', 'key': 'subfolder', 'label': 'In a new dated folder there',
         'default': bool(values.get('subfolder', True))},
        {'kind': 'label', 'muted': True,
         'text': 'A clash goes to its Assigned to; unassigned clashes go to the trade that moves (%s, the later '
                 'trade moves; set it with Shift+Click on Clash Assigner), or to both trades.' % ' > '.join(priority)},
    ]


def snapshot_settings_fields(values, test_names, data_mode):
    fields = [
        {'kind': 'check', 'key': 'auto_on_save', 'label': 'Take a snapshot automatically when the model is saved',
         'default': bool(values.get('auto_on_save'))},
        {'kind': 'number', 'key': 'min_hours', 'label': 'At most one automatic snapshot every', 'suffix': 'hours',
         'min': 0, 'max': 720, 'default': values.get('min_hours', 4.0), 'enabled_if': ('auto_on_save', True),
         'required': True},
        {'kind': 'int', 'key': 'max_results', 'label': 'Skip it when the tests hold more than', 'suffix': 'clashes',
         'min': 1, 'max': 5000000, 'default': values.get('max_results', 50000), 'enabled_if': ('auto_on_save', True),
         'required': True},
    ]
    if test_names:
        fields.append({'kind': 'multi', 'key': 'tests', 'label': 'Tests to record (none ticked: every test with results)',
                       'options': [(n, n) for n in test_names],
                       'default': [t for t in values.get('tests') or [] if t in test_names],
                       'enabled_if': ('auto_on_save', True)})
    if data_mode == 'model':
        fields.append({'kind': 'label', 'muted': True,
                       'text': 'Automatic snapshots are skipped while Playground data is kept in the model: writing into '
                               'the model right after a save would mark it changed again. Use Snapshot by hand.'})
    else:
        fields.append({'kind': 'label', 'muted': True,
                       'text': 'Automatic snapshots are skipped when the clash counts have not changed since the last one.'})
    return fields


def image_choices(listed_by_test, cap):
    """[(label, value)] for the thumbnail question when a test lists more than `cap`."""
    total = sum(int(n) for n in listed_by_test.values())
    capped = sum(cr.image_counts(listed_by_test, cap).values())
    return [('Thumbnails for the first %s clashes of each test (%s images)' % ('{:,}'.format(cap), '{:,}'.format(capped)),
             IMAGES_CAPPED),
            ('Thumbnails for every listed clash (%s images)' % '{:,}'.format(total), IMAGES_ALL),
            ('No thumbnails', IMAGES_NONE)]


# ==== dialogs (Navisworks / WPF; lazy imports) ====================================================


def runner_active():
    from namo import ui
    return ui.is_runner()


def start(doc=None):
    """The (level, message, detail) to toast when the clash tools cannot start, else None."""
    from namo import clashset_common as common
    return common.clash_problem(doc, need_results=True)


def pick_tests(title, prompt, remembered, doc=None):
    """[live ClashTest] ticked (remembering by test path), [] when no test has results, or
    None when cancelled."""
    from namo import clashset_common as common
    return common.choose_tests(title, prompt, remembered, doc=doc)


def test_paths(tests):
    from namo import clashdata
    return [clashdata.test_path(t) for t in tests]


def listed_counts(tests, statuses):
    """{test name: clashes with the statuses} by Clash Detective's own counter."""
    from namo import clashdata
    wanted = cr.ordered_statuses(statuses)
    names = clashdata.unique_names([t.DisplayName for t in tests])
    out = {}
    for name, test in zip(names, tests):
        counts = cr.status_counts(test)
        out[name] = sum(counts.get(s, 0) for s in wanted)
    return out


def ask_images(title, tests, statuses, cap=cr.IMAGE_CAP):
    """The thumbnail cap for this run: cap (or 0 = every listed clash) when the user agrees,
    -1 for no thumbnails, None when cancelled. Asks only when some test lists more than
    `cap` clashes."""
    from pynavis import forms
    listed = listed_counts(tests, statuses)
    if not cr.over_cap(listed, cap):
        return cap
    choices = image_choices(listed, cap)
    picked = forms.ask_options('Some tests list more than %s clashes. Thumbnails take a moment each.'
                               % '{:,}'.format(cap), [label for label, _value in choices], title)
    if picked is None:
        return None
    value = dict(choices)[picked]
    if value == IMAGES_NONE:
        return -1
    return 0 if value == IMAGES_ALL else cap


def run_report(report_id, config, title, doc=None):
    """reports.run behind the cancellable progress window; None when cancelled."""
    from namo import progress, reports
    result = progress.run(title, lambda report: reports.run(report_id, config, doc=doc, interactive=True,
                                                            progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return None
    # The report left its output-window page for us: printing it while the progress window
    # was up would have opened an empty window behind it.
    page = result.pop('output', None)
    if page is not None:
        page.show()
    return result


def reveal(result):
    """Shows the first file a finished report wrote in Explorer (selected), so the user
    sees where it went. Nothing for a failed report or one that wrote no file; a toast when
    Explorer cannot be opened."""
    paths = (result or {}).get('paths') or []
    if not paths or result.get('level') not in ('success', 'warning'):
        return False
    try:
        from namo import ui
        ui.show_in_explorer(paths[0])
        return True
    except Exception:
        from pynavis import toast
        toast.warning('Could not open the folder', paths[0])
        return False


def run_saved(report_id, values, extra=None):
    """Under `pynavis run`: the report from the saved options, no dialogs, toasted."""
    from pynavis import toast
    from namo import reports
    config = dict(values)
    config.update(extra or {})
    config.pop('path', None)
    result = reports.run(report_id, config, interactive=False)
    if not result.get('cancelled'):
        toast.show(result['level'], result['message'], result['detail'])
    return result

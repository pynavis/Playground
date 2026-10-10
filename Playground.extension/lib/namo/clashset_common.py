# -*- coding: utf-8 -*-
"""Small things every Clash Setup and Clash Results tool shares.

  * clash_problem(doc): the sentence to toast when Clash Detective cannot be used
    (no Manage licence, or no tests / no results yet), or None when it can.
  * choose_tests(...): the test picker (namo.ui.choose) with counts, remembering the
    last choice by test NAME (indexes move when tests are added).
  * write_progress(title, work): runs a document write behind pyNavis' ProgressScope.
    Writes are never cancellable halfway (a cancel inside a transaction would leave
    half an edit), so this window has no Cancel button; reads use namo.progress.run,
    which has one.
  * thickness(...) / close_window(...): WPF helpers for the custom windows.
  * plural(n, word, words): '1 test' / '3 tests' with thousands separators.

Pure helpers first; the rest lazy-imports pynavis / WPF.
"""

STATUS_NAMES = ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']
OPEN_STATUSES = ['New', 'Active', 'Reviewed']


def plural(count, word, words=None):
    """'1 test', '1,240 clashes' (words defaults to word + 's')."""
    count = int(count)
    return '{:,} {}'.format(count, word if count == 1 else (words or word + 's'))


def remembered(values, names, wanted):
    """The values whose names are in wanted (case-insensitive), order of values.
    For re-ticking the tests chosen last time."""
    lowered = set(str(w).strip().lower() for w in (wanted or []))
    return [v for v, n in zip(values, names) if str(n).strip().lower() in lowered]


def wpf():
    """References the WPF and pyNavis runtime assemblies (before importing
    System.Windows names in a module that builds a window)."""
    import clr
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase', 'System.Xaml',
                 'System.Data', 'PyNavis.Runtime'):
        try:
            clr.AddReference(name)
        except Exception:
            pass


def thickness(*values):
    """System.Windows.Thickness from 1, 2 or 4 numbers."""
    wpf()
    from System.Windows import Thickness
    if len(values) == 1:
        return Thickness(float(values[0]))
    if len(values) == 2:
        return Thickness(float(values[0]), float(values[1]), float(values[0]), float(values[1]))
    return Thickness(float(values[0]), float(values[1]), float(values[2]), float(values[3]))


def close_window(win, result):
    """Closes a modal window with a DialogResult (falls back to Close)."""
    try:
        win.DialogResult = result
    except Exception:
        try:
            win.Close()
        except Exception:
            pass


# ==== API half (Navisworks only; lazy imports) ============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def clash_problem(doc=None, need_results=False):
    """(level, message, detail) to toast when the tool cannot start, else None."""
    from namo import clashset_tests as defs
    document = _doc(doc)
    if not defs.available(document):
        return ('error', 'Clash Detective is not available',
                'These tools need Navisworks Manage with a model open.')
    tests = list(defs._clash().walk_tests(document))
    if not tests:
        return ('info', 'No clash tests in this model',
                'Create tests in Clash Detective (or with Clash Matrix), then run them.')
    if need_results and not any(defs.has_results(test) for test in tests):
        return ('info', 'No clash results yet', 'Run your clash tests in Clash Detective first.')
    return None


def choose_tests(title, prompt=None, checked_names=None, only_with_results=True, doc=None,
                 multiselect=True):
    """[live ClashTest] the user ticked, or None when cancelled ([] when there is no
    test to offer). Rows show the test path, type and result count; checked_names
    re-ticks the last choice. A single candidate is returned without asking."""
    from namo import clashset_tests as defs
    from namo import ui
    rows = defs.test_rows(doc)
    if only_with_results:
        rows = [r for r in rows if r['cells'][2]]
    if not rows:
        return []
    if len(rows) == 1:
        return [rows[0]['test']]          # one test to choose from: no question to ask
    names = [r['cells'][0] for r in rows]
    values = [r['value'] for r in rows]
    checked = remembered(values, names, checked_names)
    table_rows = [{'value': r['value'], 'cells': r['cells']} for r in rows]
    picked = ui.choose(title, table_rows, ['Test', 'Type', 'Results'], multiselect=multiselect,
                       checked=checked, prompt=prompt, ok='Next')
    if picked is None:
        return None
    by_value = dict((r['value'], r['test']) for r in rows)
    return [by_value[v] for v in picked if v in by_value]


def read_entries(tests, doc=None, title='Reading clashes'):
    """namo.clashname.read_test for each test behind a cancellable progress window;
    entry names made unique (' (2)'). Returns the entries, or namo.progress.CANCELLED.
    Raises RuntimeError (with a sentence) when a test changed while it was read."""
    from namo import clashdata, clashname, progress
    document = _doc(doc)

    def work(report_to):
        entries = []
        count = len(tests) or 1
        for index, test in enumerate(tests):
            def scaled(fraction, label, _i=index):
                return report_to((_i + fraction) / count, label)
            entries.append(clashname.read_test(test, document, scaled))
        return entries

    entries = progress.run(title, work)
    if entries is progress.CANCELLED:
        return entries
    for entry, name in zip(entries, clashdata.unique_names([e['name'] for e in entries])):
        entry['name'] = name
    return entries


def runner_active():
    try:
        from PyNavis.Runtime.Execution.Runner import RunnerContext
        return bool(RunnerContext.IsActive)
    except Exception:
        return False


RUNNER_MESSAGE = ('This tool asks questions, so it cannot run under pynavis run',
                  'Click it on the ribbon instead.')


def doc_folder(doc=None):
    """The open document's folder when it is saved, else Documents."""
    import os
    try:
        from pynavis import doc as _pdoc
        filename = _pdoc.get_filename(_doc(doc))
        if filename and os.path.isdir(os.path.dirname(filename)):
            return os.path.dirname(filename)
    except Exception:
        pass
    documents = os.path.join(os.path.expanduser('~'), 'Documents')
    return documents if os.path.isdir(documents) else os.path.expanduser('~')


def file_name(template, extension, doc=None, values=None):
    """A file name from a namo.naming template ('{file} - Clash matrix'), made safe,
    with the extension."""
    from namo import naming
    tokens = naming.standard_values(doc)
    tokens.update(values or {})
    text, _missing = naming.render(template, tokens)
    name = naming.sanitize(text, for_file=True) or 'Playground'
    if not extension.startswith('.'):
        extension = '.' + extension
    if not name.lower().endswith(extension.lower()):
        name += extension
    return name


def ask_save_path(title, template, extension, file_filter, doc=None):
    """The save dialog started in the document's folder with a templated name. Returns
    a path with the extension, or None when cancelled."""
    import os
    from pynavis import forms
    suggested = os.path.join(doc_folder(doc), file_name(template, extension, doc))
    path = forms.save_file(filter=file_filter, default_name=suggested, title=title)
    if path is None:
        return None
    if not path.lower().endswith(extension.lower()):
        path += extension
    return path


def write_progress(title, work, first_label='Starting'):
    """Runs work(report) behind pyNavis' ProgressScope (no Cancel: see the module
    docstring). report(fraction, label) returns True. Returns work's result."""
    if runner_active():
        return work(lambda fraction=None, label=None: True)
    import clr
    clr.AddReference('PyNavis.Runtime')
    from PyNavis.Runtime.Forms import ProgressScope
    scope = ProgressScope.Begin(title, first_label)

    def report(fraction, label=''):
        try:
            value = max(0.0, min(1.0, float(fraction)))
        except (TypeError, ValueError):
            value = 0.0
        scope.Report(value, label or '')
        return True

    try:
        return work(report)
    finally:
        scope.Dispose()

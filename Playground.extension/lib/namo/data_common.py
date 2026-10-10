# -*- coding: utf-8 -*-
"""Shared plumbing for the Inspect and Data panel tools: progress stages, where files
go by default, the scope dialog fields, and the small checks every button starts with.

Pure (tested): stage() progress mapping, default_name(), filters, scope fields.
API/UI: active_doc(), has_models(), doc_folder(), ask_save(), selected_count().
"""

import os

from namo import naming, propindex

XLSX_FILTER = 'Excel workbooks (*.xlsx)|*.xlsx|All files (*.*)|*.*'
CSV_FILTER = 'CSV files (*.csv)|*.csv|All files (*.*)|*.*'
TABLE_FILTER = 'Spreadsheets (*.xlsx;*.csv)|*.xlsx;*.csv|All files (*.*)|*.*'
JSON_FILTER = 'JSON files (*.json)|*.json|All files (*.*)|*.*'
LOCKED = 'Close the file in Excel, then try again.'


# =============================================================================
# Pure half
# =============================================================================


def stage(progress, start, span, label):
    """An items-style tick(done, total) driving progress(fraction, label) over the
    slice start..start+span. label may hold '%s' for the count text. Returns what
    progress returns (False cancels a namo.items walk; namo.progress raises instead)."""
    def tick(done, total=None):
        if progress is None:
            return True
        if total:
            fraction = start + span * (float(done) / float(total))
            text = '%s of %s' % ('{:,}'.format(done), '{:,}'.format(total))
        else:
            fraction = start
            text = '{:,}'.format(done)
        return progress(min(1.0, fraction), label % text if '%s' in label else label)
    return tick


def report(progress, fraction, label):
    """Calls progress(fraction, label) when there is one; returns its answer."""
    if progress is None:
        return True
    return progress(fraction, label)


def default_name(template, values, ext):
    """A file name from a naming template ('{file} - Properties - {date}') with the
    extension, made safe for Windows. A blank {file} drops its separator."""
    name, _missing = naming.render(template, values)
    name = name.strip(' -')
    while '  ' in name:
        name = name.replace('  ', ' ')
    if name.startswith('- '):
        name = name[2:]
    name = naming.sanitize(name, for_file=True) or 'export'
    ext = ext if ext.startswith('.') else '.' + ext
    return name + ext


def scope_fields(has_selection, remembered=None, level=None, levels=True, budget=None):
    """namo.ui form fields for scope (+ level, + budget)."""
    fields = [{'kind': 'radio', 'key': 'scope', 'label': 'Scope',
               'options': propindex.scope_options(has_selection),
               'default': propindex.default_scope(has_selection, remembered), 'fallback': None}]
    if levels:
        fields.append({'kind': 'radio', 'key': 'level', 'label': 'Read', 'inline': False,
                       'options': [(label, value) for value, label in propindex.LEVELS],
                       'default': level if level in propindex.LEVEL_NAMES else 'objects'})
    if budget is not None:
        fields.append({'kind': 'int', 'key': 'budget', 'label': 'Stop after this many items',
                       'default': int(budget), 'min': 100, 'max': 5000000,
                       'hint': 'Huge models are sampled at this count, and the result says so.'})
    return fields


def nothing_text(scope):
    """(message, detail) when a scope holds nothing to work on."""
    if scope == 'selection':
        return ('Nothing selected', 'Select items in the model, or choose another scope.')
    if scope == 'visible':
        return ('Nothing visible', 'Every item in the model is hidden. Unhide some, or choose the whole model.')
    return ('No geometry in the model', 'Append a model with geometry, then run this again.')


# =============================================================================
# API half
# =============================================================================


def active_doc():
    from pynavis._api import Application
    return Application.ActiveDocument


def has_models(doc=None):
    """True when the document holds at least one model."""
    document = doc or active_doc()
    try:
        return document is not None and document.Models.Count > 0
    except Exception:
        return False


def no_model_toast():
    from pynavis import toast
    toast.info('No model is open', 'Open or append a model, then try again.')


def selected_count(doc=None):
    document = doc or active_doc()
    try:
        return int(document.CurrentSelection.SelectedItems.Count)
    except Exception:
        return 0


def documents_folder():
    try:
        from System import Environment
        folder = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)
        if folder:
            return folder
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def doc_folder(doc=None):
    """The document's folder when it is saved, else Documents."""
    try:
        document = doc or active_doc()
        filename = str(document.FileName or '')
        if filename:
            folder = os.path.dirname(filename)
            if os.path.isdir(folder):
                return folder
    except Exception:
        pass
    return documents_folder()


def default_path(template, ext, doc=None, values=None):
    """doc_folder() joined with default_name(template) (standard naming tokens)."""
    tokens = naming.standard_values(doc)
    tokens.update(values or {})
    return os.path.join(doc_folder(doc), default_name(template, tokens, ext))


def ask_save(template, ext, title, doc=None, values=None):
    """A save dialog opened on the default path; the chosen path or None."""
    from pynavis import forms
    path = default_path(template, ext, doc, values)
    filters = {'xlsx': XLSX_FILTER, 'csv': CSV_FILTER, 'json': JSON_FILTER}
    return forms.save_file(filter=filters.get(ext.lstrip('.'), XLSX_FILTER), default_name=path, title=title)

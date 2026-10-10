# -*- coding: utf-8 -*-
"""Helpers the 4D, Quantities and Field tools share: scopes, default files, text.

Pure: scope labels and the default-scope rule, output file names, count phrases.
API (lazy): the objects in a scope, the document folder, opening a file.
"""

import os

SCOPES = [('selection', 'Current selection'), ('visible', 'Visible items'), ('model', 'Whole model')]
SCOPE_LABELS = dict(SCOPES)


def default_scope(remembered, has_selection):
    """The scope to preselect: the selection whenever there is one, else what the user
    chose last (never 'selection' when nothing is selected), else the whole model."""
    if has_selection:
        return 'selection'
    if remembered in ('visible', 'model'):
        return remembered
    return 'model'


def scope_options(has_selection):
    """(label, value) choices; the selection only when something is selected."""
    return [(label, value) for value, label in SCOPES if value != 'selection' or has_selection]


def plural(count, singular, plural_word=None):
    """'1 task', '1,234 tasks'."""
    word = singular if count == 1 else (plural_word or singular + 's')
    return '%s %s' % ('{:,}'.format(count), word)


def sampled_note(kept, total):
    """'Sampled 20,000 of 54,321 objects.' or ''."""
    if total is None or kept >= total:
        return ''
    return 'Sampled %s of %s objects.' % ('{:,}'.format(kept), '{:,}'.format(total))


def file_name(doc_title, label, ext):
    """'Hospital - Quick takeoff - 2026-10-05.xlsx' from the document title (stem)."""
    from namo import dates, naming
    stem = os.path.splitext(os.path.basename(doc_title or ''))[0] or 'Untitled'
    name = '%s - %s - %s' % (stem, label, dates.today().strftime('%Y-%m-%d'))
    return naming.sanitize(name, for_file=True) + '.' + ext.lstrip('.')


def documents_folder():
    """%USERPROFILE%\\Documents (or the home folder)."""
    home = os.path.expanduser('~')
    docs = os.path.join(home, 'Documents')
    return docs if os.path.isdir(docs) else home


# ---- API half -------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def active_doc():
    """The active Navisworks document."""
    return _doc(None)


def doc_path(doc=None):
    """The active document's file path, or ''."""
    try:
        from pynavis import doc as _pdoc
        return _pdoc.get_filename(_doc(doc)) or ''
    except Exception:
        return ''


def doc_title(doc=None):
    path = doc_path(doc)
    if path:
        return os.path.basename(path)
    try:
        return str(_doc(doc).Title or '')
    except Exception:
        return ''


def doc_folder(doc=None):
    """The document's folder when it is saved, else Documents."""
    path = doc_path(doc)
    folder = os.path.dirname(path) if path else ''
    return folder if folder and os.path.isdir(folder) else documents_folder()


def default_path(doc, label, ext):
    """doc_folder + file_name: the prefilled Save As path."""
    return os.path.join(doc_folder(doc), file_name(doc_title(doc), label, ext))


def has_models(doc=None):
    try:
        return _doc(doc).Models.Count > 0
    except Exception:
        return False


def selection_objects(doc=None):
    """The element-level objects of the current selection."""
    from namo import items
    return items.objects(items.selected(doc))


def scope_objects(scope, doc=None, tick=None, budget=None):
    """ItemList of element-level objects in a scope ('selection', 'visible', 'model').
    'visible' drops objects with a hidden item on their ancestor chain. budget caps the
    list (.sampled True); .total is how many there were when known."""
    from namo import items
    document = _doc(doc)
    if scope == 'selection':
        found = items.objects(items.selected(document), tick=tick, budget=budget)
    else:
        found = items.objects(items.roots(document), tick=tick,
                              budget=None if scope == 'visible' else budget)
    if scope == 'visible':
        kept = items.ItemList()
        for obj in found:
            if items.visible(obj):
                kept.append(obj)
                if budget is not None and len(kept) >= budget:
                    kept.sampled = True
                    break
        kept.sampled = kept.sampled or found.sampled
        found = kept
    return found


def report_config(config, path):
    """config with 'folder' and 'name_template' pointing reports.output_path at path
    (braces in the file name escaped so namo.naming leaves them alone)."""
    out = dict(config)
    folder, name = os.path.split(str(path))
    stem = os.path.splitext(name)[0]
    out['folder'] = folder
    out['name_template'] = stem.replace('{', '{{').replace('}', '}}')
    return out


def ask_save(doc, label, ext, title, filter_text=None):
    """Save As prefilled with the document folder and '<file> - <label> - <date>.<ext>';
    the chosen path, or None on cancel."""
    from pynavis import forms
    filters = {'xlsx': 'Excel workbook (*.xlsx)|*.xlsx', 'html': 'HTML report (*.html)|*.html',
               'csv': 'CSV file (*.csv)|*.csv'}
    path = forms.save_file(filter=filter_text or filters.get(ext, 'All files (*.*)|*.*'),
                           default_name=default_path(doc, label, ext), title=title)
    if path is None:
        return None
    if not str(path).lower().endswith('.' + ext):
        path = str(path) + '.' + ext
    return path


def open_file(path):
    """Opens a file with its default program; False when Windows refuses."""
    try:
        os.startfile(path)
        return True
    except Exception:
        pass
    try:
        from System.Diagnostics import Process, ProcessStartInfo
        info = ProcessStartInfo(str(path))
        info.UseShellExecute = True
        Process.Start(info)
        return True
    except Exception:
        return False

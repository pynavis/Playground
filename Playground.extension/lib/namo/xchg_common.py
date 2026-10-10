# -*- coding: utf-8 -*-
"""Small pieces the Geometry and IFC exporters share: where files go, default names,
and the list of skipped objects in the output window."""
import os

from namo import naming

SKIPPED_SHOWN = 500


def doc_path(doc):
    try:
        return str(doc.FileName or '')
    except Exception:
        return ''


def doc_title(doc):
    try:
        title = str(doc.Title or '')
    except Exception:
        title = ''
    if title:
        return title
    path = doc_path(doc)
    return os.path.basename(path) if path else 'Untitled'


def doc_folder(doc):
    """The document's folder when it is saved, else Documents."""
    path = doc_path(doc)
    folder = os.path.dirname(path) if path else ''
    if folder and os.path.isdir(folder):
        return folder
    documents = os.path.join(os.path.expanduser('~'), 'Documents')
    return documents if os.path.isdir(documents) else os.path.expanduser('~')


def default_name(template, ext, values):
    """A file name from a naming template ('{file} - Geometry - {date}') and its
    extension; '{file}' falls back to 'Untitled'."""
    tokens = dict(values)
    if not tokens.get('file'):
        tokens['file'] = 'Untitled'
    text, _missing = naming.render(template, tokens)
    name = naming.sanitize(text, for_file=True)
    if not name.lower().endswith(ext.lower()):
        name += ext
    return name


def default_path(doc, template, ext):
    return os.path.join(doc_folder(doc), default_name(template, ext, naming.standard_values(doc)))


def ask_save(doc, template, ext, file_filter, title):
    """The Save As dialog on the default path; the chosen path (with ext) or None."""
    from pynavis import forms
    path = forms.save_file(filter=file_filter, default_name=default_path(doc, template, ext), title=title)
    if path is None:
        return None
    path = str(path)
    if not path.lower().endswith(ext.lower()):
        path += ext
    return path


RUNNER_MESSAGE = ('This tool asks questions, so it cannot run under pynavis run',
                  'Click it on the ribbon instead.')


def under_runner():
    """True (after a toast into the run's transcript) when the script runs under
    `pynavis run`, where no window may open: the caller returns at once."""
    try:
        from pynavis import script
        active = bool(script.is_runner())
    except Exception:
        active = False
    if active:
        from pynavis import toast
        toast.warning(*RUNNER_MESSAGE)
    return active


def where_text(detail, path):
    """A toast detail that always ends with where the file is: 'detail path' (pure)."""
    detail = str(detail or '').strip()
    return ('%s %s' % (detail, path)).strip() if path else detail


def reveal(path):
    """Shows the exported file in Explorer, selected. Never raises: the toast already
    names the path."""
    try:
        from namo import ui
        ui.show_in_explorer(path)
        return True
    except Exception:
        return False


def skipped_rows(skipped):
    """[(name, reason)] sorted by reason then name, for the output table (pure)."""
    rows = [(str(name or 'Object'), str(reason or '')) for name, reason, _item in skipped]
    rows.sort(key=lambda r: (r[1].lower(), naming.natural_key(r[0])))
    return rows


def show_skipped(title, skipped, dropped=()):
    """Lists skipped objects in the output window, with links that select them."""
    from pynavis import output
    from namo import htmlreport
    if not skipped and not dropped:
        return
    output.set_title(title)
    total = len(skipped) + len(dropped)
    output.print_md('### %s skipped' % ('{:,}'.format(total) + (' object' if total == 1 else ' objects')))
    ordered = sorted(skipped, key=lambda s: (str(s[1]).lower(), naming.natural_key(s[0])))
    parts = ['<table class="pynavis"><tr><th>Object</th><th>Why</th></tr>']
    for name, reason, item in ordered[:SKIPPED_SHOWN]:
        try:
            link = output.element_link(item, str(name or 'Object'))
        except Exception:
            link = htmlreport.escape(name)
        parts.append('<tr><td>%s</td><td>%s</td></tr>' % (link, htmlreport.escape(reason)))
    for name in list(dropped)[:max(0, SKIPPED_SHOWN - len(ordered))]:
        parts.append('<tr><td>%s</td><td>%s</td></tr>' % (
            htmlreport.escape(name), 'Every triangle was too small to keep'))
    parts.append('</table>')
    output.print_html(''.join(parts))
    if total > SKIPPED_SHOWN:
        output.print_md('The first %s are listed.' % '{:,}'.format(SKIPPED_SHOWN))

# -*- coding: utf-8 -*-
"""Playground Link for pyRevit: hand elements between Revit and Navisworks.

Two small JSON files in %APPDATA%\\pyNavis\\playground\\revit-link, shared with the Playground extension
for Navisworks (its namo.revitlink module):

    to-revit.json        written by Navisworks (Playground > Show in Revit), read by
                         Show from Navisworks here
    to-navisworks.json   written by Send to Navisworks here, read by Navisworks
                         (Playground > Show from Revit)

    {"format": "playground-revit-link", "version": 1, "direction": "to-revit",
     "sent": "2026-10-05T14:30:00", "from": "Hospital.nwf",
     "elements": [{"file": "Hospital_MEP.rvt", "element_id": "123456",
                   "unique_id": "...", "name": "Duct", "category": "Ducts"}]}

The pure helpers (stem, same_file, loose_match, message, read_message, age_text,
group_by_file) are kept identical to namo.revitlink; a Playground test checks they agree.
Written for pyRevit's IronPython 2.7 engine (and CPython 3): no f-strings, no
keyword-only arguments, Revit imports only inside functions.
"""

import datetime
import io
import json
import os

FORMAT = 'playground-revit-link'
VERSION = 1
TO_REVIT = 'to-revit.json'
TO_NAVISWORKS = 'to-navisworks.json'
FOLDER_NAME = 'revit-link'
_EXTENSIONS = ('.rvt', '.nwc', '.nwd', '.nwf', '.rfa', '.ifc', '.dwg')


# ---- pure (kept identical to namo.revitlink) ----------------------------------------------


def stem(name):
    """The lowercase file name without folder or a known extension."""
    text = ('%s' % (name or '')).strip().replace('\\', '/').split('/')[-1]
    lowered = text.lower()
    for ext in _EXTENSIONS:
        if lowered.endswith(ext):
            return lowered[:-len(ext)].strip()
    return lowered.strip()


def same_file(a, b, user=None):
    """True when two file names are the same Revit model: equal stems, or one is the
    other's local copy ('<central>_<user>')."""
    sa, sb = stem(a), stem(b)
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    if user:
        suffix = '_' + ('%s' % user).strip().lower()
        if sa == sb + suffix or sb == sa + suffix:
            return True
    return False


def loose_match(a, b):
    """One stem starts or ends the other at a separator."""
    sa, sb = stem(a), stem(b)
    if not sa or not sb or sa == sb:
        return bool(sa) and sa == sb
    if len(sa) < len(sb):
        short, long_ = sa, sb
    else:
        short, long_ = sb, sa
    if long_.startswith(short) and long_[len(short)] in '_- .':
        return True
    if long_.endswith(short) and long_[-len(short) - 1] in '_- .':
        return True
    return False


def message(direction, source, elements, now=None):
    """A message dict ready for JSON."""
    stamp = now or datetime.datetime.now()
    clean = []
    for element in elements:
        clean.append({'file': '%s' % (element.get('file') or ''),
                      'element_id': '%s' % (element.get('element_id') or ''),
                      'unique_id': '%s' % (element.get('unique_id') or ''),
                      'name': '%s' % (element.get('name') or ''),
                      'category': '%s' % (element.get('category') or '')})
    return {'format': FORMAT, 'version': VERSION, 'direction': direction,
            'sent': stamp.strftime('%Y-%m-%dT%H:%M:%S'), 'from': '%s' % (source or ''),
            'elements': clean}


def read_message(data, direction):
    """(elements, problem sentence or None) from a loaded message."""
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        return [], 'The link file is not a Playground Revit link file.'
    if data.get('direction') not in (None, direction):
        return [], 'The link file holds elements going the other way.'
    elements = []
    for element in data.get('elements') or []:
        if not isinstance(element, dict):
            continue
        element_id = ('%s' % (element.get('element_id') or '')).strip()
        unique_id = ('%s' % (element.get('unique_id') or '')).strip()
        if not element_id and not unique_id:
            continue
        elements.append({'file': '%s' % (element.get('file') or ''), 'element_id': element_id,
                         'unique_id': unique_id, 'name': '%s' % (element.get('name') or ''),
                         'category': '%s' % (element.get('category') or '')})
    if not elements:
        return [], 'The link file holds no elements.'
    return elements, None


def age_text(sent, now=None):
    """'just now', '5 minutes ago', '3 hours ago', '2 days ago' ('' when unreadable)."""
    try:
        when = datetime.datetime.strptime(('%s' % sent)[:19], '%Y-%m-%dT%H:%M:%S')
    except Exception:
        return ''
    seconds = ((now or datetime.datetime.now()) - when).total_seconds()
    if seconds < 90:
        return 'just now'
    minutes = int(seconds // 60)
    if minutes < 90:
        return '%d minutes ago' % minutes
    hours = int(minutes // 60)
    if hours < 36:
        return '%d hours ago' % hours
    return '%d days ago' % int(hours // 24)


def group_by_file(elements):
    """[(file, [elements])] in first-seen order, files compared by stem."""
    order = []
    groups = {}
    for element in elements:
        key = stem(element.get('file'))
        if key not in groups:
            groups[key] = (element.get('file') or '', [])
            order.append(key)
        groups[key][1].append(element)
    return [groups[key] for key in order]


# ---- files ------------------------------------------------------------------------------------


def folder():
    """%APPDATA%\\pyNavis\\playground\\revit-link (created)."""
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    path = os.path.join(base, 'pyNavis', 'playground', FOLDER_NAME)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def read_file(name):
    """(data dict or None, problem or None) from a link file in the folder."""
    path = os.path.join(folder(), name)
    if not os.path.exists(path):
        return None, None
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as handle:
            return json.loads(handle.read()), None
    except Exception:
        return None, 'The link file %s could not be read.' % name


def write_file(name, data):
    """Writes a link file atomically (temp file, then rename). Returns the path."""
    path = os.path.join(folder(), name)
    temp = path + '.tmp'
    text = json.dumps(data, indent=2, sort_keys=True)
    if not isinstance(text, type(u'')):
        text = text.decode('utf-8')
    with io.open(temp, 'w', encoding='utf-8') as handle:
        handle.write(text)
        handle.write(u'\n')
    if os.path.exists(path):
        os.remove(path)
    os.rename(temp, path)
    return path


# ---- Revit (imports inside the functions) -------------------------------------------------------


def id_value(element_id):
    """The integer behind an ElementId (Value from Revit 2024, IntegerValue before)."""
    try:
        return int(element_id.Value)
    except Exception:
        return int(element_id.IntegerValue)


def make_id(value):
    """An ElementId from a number (the Int64 constructor from Revit 2024, Int32 before)."""
    from Autodesk.Revit import DB
    number = int(value)
    try:
        from System import Int64
        return DB.ElementId(Int64(number))
    except Exception:
        return DB.ElementId(number)


def file_names(doc):
    """Every name this document may be known by in Navisworks: the central model's file
    (workshared), the file on disk, and the title."""
    names = []
    try:
        if doc.IsWorkshared:
            from Autodesk.Revit import DB
            central = doc.GetWorksharingCentralModelPath()
            if central is not None:
                visible = DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(central)
                if visible:
                    names.append(visible.replace('\\', '/').split('/')[-1])
    except Exception:
        pass
    try:
        if doc.PathName:
            names.append(doc.PathName.replace('\\', '/').split('/')[-1])
    except Exception:
        pass
    try:
        if doc.Title:
            names.append(doc.Title)
    except Exception:
        pass
    out = []
    for name in names:
        if name and name not in out:
            out.append(name)
    return out


def user_name(doc):
    try:
        return doc.Application.Username
    except Exception:
        return os.environ.get('USERNAME', '')


def matches_doc(file_name, doc):
    """True when a file name from Navisworks is this Revit document."""
    if not file_name:
        return True
    user = user_name(doc)
    return any(same_file(file_name, name, user) for name in file_names(doc))


def resolve(doc, element):
    """The Revit element for a link entry (UniqueId first, then the id), or None."""
    found = None
    unique_id = element.get('unique_id')
    if unique_id:
        try:
            found = doc.GetElement(unique_id)
        except Exception:
            found = None
    if found is None and element.get('element_id'):
        try:
            found = doc.GetElement(make_id(element['element_id']))
        except Exception:
            found = None
    return found


def describe(element, doc):
    """A link entry for one Revit element."""
    try:
        category = element.Category.Name if element.Category is not None else ''
    except Exception:
        category = ''
    try:
        name = element.Name or ''
    except Exception:
        name = ''
    names = file_names(doc)
    central = names[0] if names else ''
    if central and not central.lower().endswith('.rvt'):
        central = central + '.rvt'
    return {'file': central, 'element_id': '%d' % id_value(element.Id),
            'unique_id': element.UniqueId or '', 'name': name, 'category': category}


def notify(message_text, detail=None, title='Playground Link'):
    """A Windows toast through pyRevit when it has one, else an alert."""
    from pyrevit import forms
    text = message_text if not detail else '%s\n%s' % (message_text, detail)
    toast = getattr(forms, 'toast', None)
    if toast is not None:
        try:
            toast(text, title=title)
            return
        except Exception:
            pass
    forms.alert(text, title=title)

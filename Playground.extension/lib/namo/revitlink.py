# -*- coding: utf-8 -*-
"""Revit Link: hand elements between Navisworks and Revit through two small JSON files.

    %APPDATA%\\pyNavis\\playground\\revit-link\\to-revit.json        written by Show in Revit
    %APPDATA%\\pyNavis\\playground\\revit-link\\to-navisworks.json   written by Revit (Send to Navisworks)

    {"format": "playground-revit-link", "version": 1, "direction": "to-revit",
     "sent": "2026-10-05T14:30:00", "from": "Hospital.nwf",
     "elements": [{"file": "Hospital_MEP.rvt", "element_id": "123456",
                   "unique_id": "...", "name": "Duct", "category": "Ducts"}]}

The pyRevit companion (this repo\\companions\\PlaygroundLink.extension) reads and
writes the same files; its lib/playgroundlink.py repeats the pure helpers below (file name
matching, message checks) and a test keeps the two in step.

Navisworks side:
  * the Revit element of a selected item is the nearest item (itself or an ancestor)
    carrying the exporter's element category, LcRevitData_Element by internal name.
    Nested family parts carry the TYPE's id in their 'Element ID' tab, so reading the
    id off them would send the wrong element (pyNavis' Select by IDs field notes).
  * finding an id searches only the models whose source file matches the Revit file,
    with 'Element ID > Value' = id AND the element category, then the '[123456]'
    name suffix design-coordination models use (pynavis.sets.find_first, scoped).

Pure first (unit tested); the API half after.
"""

import datetime
import os
import re

FORMAT = 'playground-revit-link'
VERSION = 1
TO_REVIT = 'to-revit.json'
TO_NAVISWORKS = 'to-navisworks.json'
ELEMENT_CATEGORY = 'LcRevitData_Element'
FOLDER_NAME = 'revit-link'
MAX_ELEMENTS = 5000
_EXTENSIONS = ('.rvt', '.nwc', '.nwd', '.nwf', '.rfa', '.ifc', '.dwg')


# ---- pure (kept identical to companions/PlaygroundLink.extension/lib/playgroundlink.py) --------------


def stem(name):
    """The lowercase file name without folder or a known extension: 'C:\\P\\Hospital_MEP.rvt'
    -> 'hospital_mep'."""
    text = str(name or '').strip().replace('\\', '/').split('/')[-1]
    lowered = text.lower()
    for ext in _EXTENSIONS:
        if lowered.endswith(ext):
            return lowered[:-len(ext)].strip()
    return lowered.strip()


def same_file(a, b, user=None):
    """True when two file names are the same Revit model: equal stems, or one is the
    other's local copy ('<central>_<user>', Revit's workshared naming)."""
    sa, sb = stem(a), stem(b)
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    if user:
        suffix = '_' + str(user).strip().lower()
        if sa == sb + suffix or sb == sa + suffix:
            return True
    return False


def loose_match(a, b):
    """A weaker match for model names that grew a suffix or prefix on the way to
    Navisworks ('Hospital_MEP' and 'Hospital_MEP_R24'): one stem starts or ends the
    other at a separator."""
    sa, sb = stem(a), stem(b)
    if not sa or not sb or sa == sb:
        return bool(sa) and sa == sb
    short, long_ = (sa, sb) if len(sa) < len(sb) else (sb, sa)
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
        clean.append({'file': str(element.get('file') or ''),
                      'element_id': str(element.get('element_id') or ''),
                      'unique_id': str(element.get('unique_id') or ''),
                      'name': str(element.get('name') or ''),
                      'category': str(element.get('category') or '')})
    return {'format': FORMAT, 'version': VERSION, 'direction': direction,
            'sent': stamp.strftime('%Y-%m-%dT%H:%M:%S'), 'from': str(source or ''),
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
        element_id = str(element.get('element_id') or '').strip()
        unique_id = str(element.get('unique_id') or '').strip()
        if not element_id and not unique_id:
            continue
        elements.append({'file': str(element.get('file') or ''), 'element_id': element_id,
                         'unique_id': unique_id, 'name': str(element.get('name') or ''),
                         'category': str(element.get('category') or '')})
    if not elements:
        return [], 'The link file holds no elements.'
    return elements, None


def age_text(sent, now=None):
    """'just now', '5 minutes ago', '3 hours ago', '2 days ago' ('' when unreadable)."""
    try:
        when = datetime.datetime.strptime(str(sent)[:19], '%Y-%m-%dT%H:%M:%S')
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


# ---- pure: Navisworks side --------------------------------------------------------------------


def match_models(file_name, models, user=None):
    """(model indexes, how) for a Revit file among models [{'index', 'names': [...]}]:
    how is 'exact', 'loose' or 'all' (nothing matched: search everything)."""
    exact = [m['index'] for m in models if any(same_file(file_name, n, user) for n in m['names'])]
    if exact:
        return exact, 'exact'
    loose = [m['index'] for m in models if any(loose_match(file_name, n) for n in m['names'])]
    if loose:
        return loose, 'loose'
    return [m['index'] for m in models], 'all'


ID_SETTINGS_KEY = 'cfg_element_ids'       # pyNavis' Select by IDs / IDs of Selection settings
ID_CATEGORY = 'Element ID'
ID_PROPERTY = 'Value'


def id_queries(element_id, elements_only=True, category=ID_CATEGORY, prop=ID_PROPERTY):
    """pynavis query dicts to try in order for one element id: the exporter's
    'Element ID > Value' text (AND the element category when the model marks
    elements), then the '[id]' name suffix. category/prop: where this firm's models
    keep the id (pyNavis' Element ID settings)."""
    text = str(element_id or '').strip()
    if not re.match(r'^\d+$', text):
        return []
    first = [{'category': category or ID_CATEGORY, 'prop': prop or ID_PROPERTY, 'op': 'equals',
              'value': text}]
    if elements_only:
        first.append({'category': ELEMENT_CATEGORY, 'op': 'has_category', 'by_display': False})
    return [{'or': [{'and': first}]},
            {'or': [{'and': [{'category': 'Item', 'prop': 'Name', 'op': 'contains',
                              'value': '[%s]' % text}]}]}]


def is_element(categories):
    """True when (display, internal) category pairs include the element category."""
    return any(name == ELEMENT_CATEGORY for _display, name in categories)


def short_list(values, limit=6):
    values = [str(v) for v in values]
    if len(values) <= limit:
        return ', '.join(values)
    return '%s and %d more' % (', '.join(values[:limit]), len(values) - limit)


# ==== API half (Navisworks only; lazy imports) ============================================


def folder():
    from namo import paths
    return paths.ensure_dir(os.path.join(paths.data_root(), FOLDER_NAME))


def path_of(name):
    return os.path.join(folder(), name)


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def revit_element(item):
    """The Revit element for a selected item: itself or the nearest ancestor carrying
    the element category; else its object ancestor."""
    from pynavis import props
    from namo import items as _items
    node = item
    while node is not None:
        try:
            if is_element(props.categories(node)):
                return node
        except Exception:
            pass
        node = node.Parent
    return _items.object_of(item)


def source_file(item):
    """The source file name of the item's model (the .rvt when exported from Revit)."""
    from namo import items as _items
    model = _items.model_of(item)
    if model is None:
        return ''
    name = model.SourceFileName or model.FileName or ''
    return str(name).replace('\\', '/').split('/')[-1]


def selected_elements(doc=None):
    """(elements for the message, skipped count) from the current selection."""
    from namo import items as _items
    seen = set()
    out = []
    skipped = 0
    for item in _items.selected(doc):
        element = revit_element(item)
        if element in seen:
            continue
        seen.add(element)
        ids = _items.revit_ids(element)
        if not ids.get('element_id') and not ids.get('unique_id'):
            skipped += 1
            continue
        out.append({'file': source_file(element), 'element_id': ids.get('element_id') or '',
                    'unique_id': ids.get('unique_id') or '', 'name': element.DisplayName or '',
                    'category': ids.get('category') or ''})
        if len(out) >= MAX_ELEMENTS:
            break
    return out, skipped


def send_to_revit(elements, doc=None):
    """Writes to-revit.json; returns its path. IOError when it cannot be written."""
    from namo import paths
    from pynavis import doc as _pdoc
    document = _doc(doc)
    title = ''
    try:
        title = _pdoc.get_title(document) or ''
    except Exception:
        title = ''
    path = path_of(TO_REVIT)
    paths.write_json(path, message('to-revit', title, elements))
    return path


def read_from_revit():
    """(elements, sent text, source, problem) from to-navisworks.json."""
    from namo import paths
    path = path_of(TO_NAVISWORKS)
    if not os.path.exists(path):
        return [], '', '', None
    data = paths.load_json(path, None, move_aside=False)
    elements, problem = read_message(data, 'to-navisworks')
    if data is None and problem:
        problem = 'The link file from Revit could not be read.'
    sent = data.get('sent', '') if isinstance(data, dict) else ''
    source = data.get('from', '') if isinstance(data, dict) else ''
    return elements, sent, source, problem


def model_table(doc=None):
    """[{'index', 'names', 'root'}] for match_models."""
    from namo import items as _items
    out = []
    for model in _items.models(doc):
        names = [n for n in (model['name'], model['source'], model['file']) if n]
        out.append({'index': model['index'], 'names': names, 'root': model['root']})
    return out


def _marks_elements(scope, document):
    from pynavis import sets
    probe = {'or': [{'and': [{'category': ELEMENT_CATEGORY, 'op': 'has_category', 'by_display': False}]}]}
    try:
        return sets.find_first(probe, document, scope=scope) is not None
    except Exception:
        return False


def id_property(loader=None):
    """(category, property) holding the Revit element id: what the user set for pyNavis'
    own Select by IDs (Shift+Click on it), so both tools look in the same place.
    loader(key, defaults) is a test seam for pynavis.settings.load. Never raises."""
    defaults = {'id_category': ID_CATEGORY, 'id_property': ID_PROPERTY}
    try:
        if loader is None:
            from pynavis import settings
            loader = settings.load
        stored = loader(ID_SETTINGS_KEY, defaults)
        category = str(stored.get('id_category') or '').strip() or ID_CATEGORY
        prop = str(stored.get('id_property') or '').strip() or ID_PROPERTY
        return category, prop
    except Exception:
        return ID_CATEGORY, ID_PROPERTY


def find_elements(elements, doc=None, progress=None, user=None):
    """(found ModelItems, missing [element ids], notes) for the elements from Revit.
    progress(fraction, label): a False answer raises namo.items.Cancelled (nothing is
    written by this search)."""
    from pynavis import sets
    from namo import items as _items
    document = _doc(doc)
    models = model_table(document)
    id_category, id_prop = id_property()
    found = []
    seen = set()
    missing = []
    notes = []
    done = 0
    total = len(elements) or 1
    for file_name, group in group_by_file(elements):
        indexes, how = match_models(file_name, models, user)
        if how == 'all' and file_name:
            notes.append('No model is named like %s; every model was searched.' % file_name)
        scope = [m['root'] for m in models if m['index'] in indexes]
        elements_only = _marks_elements(scope, document)
        for element in group:
            if progress is not None and progress(float(done) / total, 'Finding %s' % (
                    element['element_id'] or element['name'])) == False:  # noqa: E712
                raise _items.Cancelled()
            done += 1
            hit = None
            for query in id_queries(element['element_id'], elements_only, id_category, id_prop):
                try:
                    hit = sets.find_first(query, document, scope=scope)
                except Exception:
                    hit = None
                if hit is not None:
                    break
            if hit is None:
                missing.append(element['element_id'] or element['unique_id'])
                continue
            if hit not in seen:
                seen.add(hit)
                found.append(hit)
    if progress is not None:
        progress(1.0, 'Done')
    return found, missing, notes

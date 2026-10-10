# -*- coding: utf-8 -*-
"""Sets Library: search sets published to shared JSON libraries and imported into models.

A library is one file in <team root>\\libraries\\sets\\<name>.json (namo.paths.team_root:
the shared folder when Playground settings name one, else the local data folder):

    {"format": "playground-sets-library", "version": 1, "name": "MEP coordination",
     "updated": "2026-10-05T14:30:00", "user": "amol",
     "sets": [{"name": "Ducts", "folder": "Systems", "query": {"or": [{"and": [...]}]}}]}

Entries use pynavis.sets.export_all's shape, so an import goes through
sets.import_dict (validated whole before anything is written, one undo step). Only
SEARCH sets travel: a static set is a list of items in one model and means nothing in
another (Set Exchange carries those). Writes are atomic and locked.
"""

import datetime
import os

FORMAT = 'playground-sets-library'
VERSION = 1
SUBFOLDER = os.path.join('libraries', 'sets')


# ---- pure half ----------------------------------------------------------------------


def set_key(entry):
    """(folder lower, name lower): what makes two library entries the same set."""
    return (str(entry.get('folder') or '').strip().lower(), str(entry.get('name') or '').strip().lower())


def clean_entry(entry):
    """A library entry {'name', 'folder', 'query'} or None when it is not a search set.
    Condition values lose the 'DisplayString:' style prefix pynavis.sets.export_all leaves
    on them (find_query.stored_value), so a published set finds what it found here."""
    from namo import find_query
    if not isinstance(entry, dict):
        return None
    name = str(entry.get('name') or '').strip()
    query = entry.get('query')
    if not name or not isinstance(query, dict) or not query.get('or'):
        return None
    folder = entry.get('folder')
    return {'name': name, 'folder': (str(folder).strip() or None) if folder else None,
            'query': find_query.stored_query(query)}


def merge(existing, incoming, replace=False):
    """The library's new set list. replace=True: incoming only. Merge: existing entries
    in their order (same-keyed ones replaced by the incoming version), then new ones in
    incoming order."""
    incoming = [e for e in (clean_entry(x) for x in incoming) if e is not None]
    if replace:
        return incoming
    by_key = dict((set_key(e), e) for e in incoming)
    out = []
    used = set()
    for entry in existing:
        entry = clean_entry(entry)
        if entry is None:
            continue
        key = set_key(entry)
        if key in used:
            continue
        used.add(key)
        out.append(by_key.get(key, entry))
    for entry in incoming:
        key = set_key(entry)
        if key not in used:
            used.add(key)
            out.append(entry)
    return out


def make_library(name, sets_list, user='', now=None):
    stamp = (now or datetime.datetime.now()).replace(microsecond=0).isoformat()
    return {'format': FORMAT, 'version': VERSION, 'name': str(name).strip(), 'updated': stamp,
            'user': user or '', 'sets': list(sets_list)}


def read_library(data):
    """A library dict from parsed JSON (entries cleaned), or None when the file is not a
    Playground sets library of this version."""
    if not isinstance(data, dict) or data.get('format') != FORMAT or data.get('version') != VERSION:
        return None
    sets_list = [e for e in (clean_entry(x) for x in data.get('sets') or []) if e is not None]
    return {'format': FORMAT, 'version': VERSION, 'name': str(data.get('name') or ''),
            'updated': str(data.get('updated') or ''), 'user': str(data.get('user') or ''),
            'sets': sets_list}


def path_for(folder, name):
    from namo import paths
    return os.path.join(folder, paths.safe_filename(name) + '.json')


def choose_rows(sets_list):
    """ui.choose rows for a library's (or a document's) search sets: value = index."""
    from namo import find_query
    rows = []
    for index, entry in enumerate(sets_list):
        conds = []
        for group in (entry.get('query') or {}).get('or') or []:
            conds.extend(group.get('and') or [])
        text = find_query.join_descriptions([find_query.describe_condition(c) for c in conds], 2)
        rows.append({'value': index, 'cells': [entry.get('folder') or '', entry['name'], text]})
    return rows


def library_rows(libraries):
    """ui table rows for library summaries: value = path."""
    return [{'value': lib['path'], 'cells': [lib['name'], lib['count'], lib['updated'].replace('T', ' '),
                                             lib['user']]} for lib in libraries]


# ---- files ----------------------------------------------------------------------------------


def folder():
    """The libraries folder (created)."""
    from namo import paths
    return paths.ensure_dir(os.path.join(paths.team_root(), SUBFOLDER))


def list_libraries(where=None):
    """[{'name', 'path', 'count', 'updated', 'user'}] of readable libraries, natural
    order. Damaged files are skipped (and moved aside by paths.load_json)."""
    from namo import naming, paths
    where = where or folder()
    out = []
    try:
        names = os.listdir(where)
    except OSError:
        return out
    for file_name in names:
        if not file_name.lower().endswith('.json'):
            continue
        path = os.path.join(where, file_name)
        library = read_library(paths.load_json(path, None))
        if library is None:
            continue
        out.append({'name': library['name'] or os.path.splitext(file_name)[0], 'path': path,
                    'count': len(library['sets']), 'updated': library['updated'],
                    'user': library['user']})
    out.sort(key=lambda lib: naming.natural_key(lib['name']))
    return out


def load(path):
    """The library at path, or None."""
    from namo import paths
    return read_library(paths.load_json(path, None))


def publish(name, sets_list, replace=False, where=None, user=None):
    """Writes (merging into an existing same-named library unless replace). Returns
    (path, total sets in the library, sets added or updated)."""
    from namo import config, paths
    where = where or folder()
    path = path_for(where, name)
    user = user if user is not None else config.user_name()
    with paths.FileLock(path):
        current = load(path)
        existing = current['sets'] if current else []
        merged = merge(existing, sets_list, replace)
        paths.write_json(path, make_library(name, merged, user))
    return path, len(merged), len([e for e in sets_list if clean_entry(e) is not None])


def rename(path, new_name):
    """Renames a library (file and inner name). Returns the new path. ValueError when the
    name is empty or taken."""
    from namo import paths
    new_name = str(new_name or '').strip()
    if not new_name:
        raise ValueError('Type a name for the library.')
    target = path_for(os.path.dirname(path), new_name)
    if os.path.normcase(target) != os.path.normcase(path) and os.path.exists(target):
        raise ValueError("A library named '%s' already exists." % new_name)
    library = load(path)
    if library is None:
        raise ValueError('That library can no longer be read.')
    library['name'] = new_name
    paths.write_json(target, library)
    if os.path.normcase(target) != os.path.normcase(path):
        os.remove(path)
    return target


def delete(path):
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def import_spec(library, indices):
    """{'sets': [...]} for pynavis.sets.import_dict from the chosen entries."""
    chosen = [library['sets'][i] for i in indices if 0 <= i < len(library['sets'])]
    return {'sets': [{'name': e['name'], 'folder': e.get('folder'), 'query': e['query']} for e in chosen]}


def problems(spec):
    """pynavis' own whole-payload validation (empty list when importable)."""
    from pynavis import sets
    return sets._validate_import(spec)


def split_importable(spec, validate=None):
    """(importable spec, [problem sentences]): pynavis rejects a whole payload when one
    entry is bad, so each entry is validated on its own and only the good ones are kept.
    One set Navisworks did not expose readably must not block the rest of a library."""
    if validate is None:
        from pynavis import sets
        validate = sets._validate_import
    good = []
    found = []
    for entry in spec.get('sets') or []:
        issues = validate({'sets': [entry]})
        if issues:
            found.extend(issues)
        else:
            good.append(entry)
    return {'sets': good}, found

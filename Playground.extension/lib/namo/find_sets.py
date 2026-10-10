# -*- coding: utf-8 -*-
"""The saved-sets tree, shared by the Find tools: paths, lookups and creating sets.

pynavis.sets is the base. Two things it does not do are added here:

  * Names are made unique among the target folder's own children (Navisworks allows the
    same name in different folders; 'By Level/Level 1' and 'By Zone/Level 1' are
    natural). pynavis.sets.create dedupes against the whole document instead, which would
    turn a batch's 'Level 1' into 'Level 1 (2)' because a set elsewhere has that name.
  * A search set can keep a 'Search In' scope (models or items), which sets.create never
    writes. Without a scope the search uses Selection.SelectAll(), exactly like
    sets.create (a search with an empty Selection matches nothing).

Folder paths are '/'-separated; a literal '/' inside one folder name is written '\\/'
(pynavis.sets' own convention, see escape()).
"""


def escape(name):
    """One path segment with '/' escaped for pynavis.sets paths."""
    return str(name or '').replace('/', '\\/')


def join(folder, name):
    """'Folder/Sub/Name' (folder already escaped, name escaped here)."""
    return ('%s/%s' % (folder, escape(name))) if folder else escape(name)


def folder_of_rows(rows):
    """{key: escaped folder path of that row ('' at the root)} for sets.snapshot rows."""
    names = dict((r['key'], r['name']) for r in rows if r['is_folder'])
    parent = dict((r['key'], r['parent_key']) for r in rows)
    out = {}
    for row in rows:
        parts = []
        key = row['parent_key']
        while key:
            parts.append(escape(names.get(key, '')))
            key = parent.get(key, '')
        out[row['key']] = '/'.join(reversed(parts))
    return out


def set_rows(rows):
    """Snapshot rows of sets only (no folders), each with 'folder' (escaped path) and
    'path' ('Folder/Name'), in tree order."""
    folders = folder_of_rows(rows)
    out = []
    for row in rows:
        if row['is_folder']:
            continue
        entry = dict(row)
        entry['folder'] = folders.get(row['key'], '')
        entry['path'] = join(entry['folder'], row['name'])
        out.append(entry)
    return out


def folder_paths(rows):
    """Every folder as an escaped path, tree order."""
    folders = folder_of_rows(rows)
    return [join(folders.get(r['key'], ''), r['name']) for r in rows if r['is_folder']]


def existing_index(rows):
    """{(folder path lower, name lower): guid} for every set, to find same-named sets in a
    target folder."""
    out = {}
    for row in set_rows(rows):
        out[(row['folder'].lower(), row['name'].lower())] = row['guid']
    return out


def unique_among(name, siblings):
    """name, or 'name (2)', 'name (3)'... free among sibling names (case-insensitive)."""
    from namo import naming
    return naming.unique(name, siblings)


def is_query(source):
    """True for a pynavis query (dict, Query or Builder) rather than items."""
    return isinstance(source, dict) or hasattr(source, 'build') or hasattr(source, 'groups')


def plain_folder(path):
    """A folder path with the escape removed, for messages."""
    return str(path or '').replace('\\/', '/')


def with_options(cond, ignore_case=False, negated=False, or_group=False, text=''):
    """One exported condition dict with what its SearchConditionOptions add.

    pynavis.sets.to_dict reads a condition's category, property, comparison and value but
    not its options. Ignore-case is put back on the dict (the 'ignore_case' key pynavis
    compiles). A negated condition, or one that starts an OR group (Find Items' "Or
    condition"), has no pynavis form: writing it back as a plain AND condition would
    quietly change what the set finds, so it becomes the non-portable 'raw' marker with
    its text, which every importer reports instead of importing."""
    if cond.get('op') == 'raw':
        return cond
    if negated or or_group:
        what = 'negated' if negated else 'starts an OR group'
        return {'op': 'raw', 'text': '%s (%s)' % (text or 'condition', what)}
    out = dict(cond)
    if ignore_case and out.get('op') in ('equals', 'not_equals', 'contains', 'wildcard') \
            and isinstance(out.get('value'), str):
        out['ignore_case'] = True
    return out


# ---- API half ----------------------------------------------------------------------


def _doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def snapshot(doc=None):
    from pynavis import sets
    return sets.snapshot(_doc(doc))


def resolve_guid(guid_text, doc=None):
    """The live set or folder with this Guid, or None."""
    from System import Guid
    try:
        return _doc(doc).SelectionSets.ResolveGuid(Guid(str(guid_text)))
    except Exception:
        return None


def _option_flags(condition):
    """(ignore_case, negated, or_group) of a live SearchCondition, or None when its
    Options cannot be read."""
    from pynavis._api import Api
    try:
        value = int(condition.Options)
        flags = Api.SearchConditionOptions
        return (bool(value & int(flags.IgnoreDisplayStringValueCase)),
                bool(value & int(flags.NegateCondition)),
                bool(value & int(flags.StartGroup)))
    except Exception:
        return None


def set_conditions(saved, doc=None):
    """The conditions of a search set as pynavis condition dicts: pynavis.sets.to_dict,
    values cleaned of the data-type prefix (find_query.stored_value) and each condition's
    options added (with_options). The first condition's StartGroup flag is ignored: the
    first condition always starts the one group there is."""
    from pynavis import sets
    from namo import find_query
    document = _doc(doc)
    data = sets.to_dict(saved, document)
    conds = []
    for group in data.get('or') or []:
        conds.extend(find_query.stored_conditions(group.get('and') or []))
    try:
        live = list(saved.Search.SearchConditions)
    except Exception:
        live = []
    if len(live) != len(conds):
        return conds
    out = []
    for position, (cond, condition) in enumerate(zip(conds, live)):
        flags = _option_flags(condition)
        if flags is None:
            out.append(cond)
            continue
        try:
            text = condition.ToString() or ''
        except Exception:
            text = ''
        out.append(with_options(cond, flags[0], flags[1], flags[2] and position > 0, text))
    return out


def export_search_sets(doc=None):
    """Every search set of the document as {'sets': [{'name', 'folder', 'query'}]}, the
    shape pynavis.sets.export_all returns and sets.import_dict reads, with each
    condition's value cleaned and its options kept (set_conditions). folder is the
    escaped '/' path pynavis.sets.create_folder splits, or None at the root."""
    document = _doc(doc)
    entries = []
    for row in set_rows(snapshot(document)):
        if not row.get('has_search'):
            continue
        saved = resolve_guid(row['guid'], document)
        if saved is None:
            continue
        entries.append({'name': row['name'], 'folder': row['folder'] or None,
                        'query': {'or': [{'and': set_conditions(saved, document)}]}})
    return {'sets': entries}


def create_set(name, source, folder=None, scope=None, doc=None):
    """Adds a set and returns (tree-resident item or None, final name).

    source: a pynavis query dict/Builder (a SEARCH set; exactly one OR group) or an
    iterable of ModelItems (a static set). folder: escaped path, created when missing.
    scope: for a search set, the items or model roots its Search In holds (None: the
    whole model). The name is made unique among the folder's children."""
    from pynavis import sets, viewpoints
    from pynavis._api import Api
    document = _doc(doc)
    if is_query(source):
        searches = sets.compile_search(source, document, scope=scope)
        if len(searches) != 1:
            raise ValueError('A search set holds one list of conditions; this one has %d.'
                             % len(searches))
        saved = Api.SelectionSet(searches[0])
    else:
        collection = Api.ModelItemCollection()
        for item in source:
            collection.Add(item)
        saved = Api.SelectionSet(collection)
    container = document.SelectionSets
    with viewpoints.transaction('pyNavis sets', document):
        group = sets.create_folder(folder, document) if folder else None
        parent = group if group is not None else container.RootItem
        siblings = [child.DisplayName for child in parent.Children]
        final = unique_among(name, siblings)
        saved.DisplayName = final
        before = set(str(child.Guid) for child in parent.Children)
        if group is None:
            container.AddCopy(saved)
        else:
            container.AddCopy(group, saved)
        added = None
        for child in parent.Children:
            if str(child.Guid) not in before:
                added = child
                break
    return added, final


def update_set(item, source, doc=None):
    """Replaces a set's content in place (pynavis.sets.update: same name, position,
    Guid). Returns the live item."""
    from pynavis import sets
    return sets.update(item, source, _doc(doc))

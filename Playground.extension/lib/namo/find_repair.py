# -*- coding: utf-8 -*-
"""Search-In Repair: search sets whose 'Search In' scope finds nothing any more.

A search set stores, besides its conditions, WHERE it searches (Find Items' Search In):
the whole model, or chosen models/items. Search sets moved between projects (exported
and imported as XML, copied between NWFs) keep pointing at items of the old project, so
they silently find nothing. This tool reads every search set's scope
(SelectionSet.Search.Selection: its SelectionSources and ExplicitSelection), lists the
ones that are empty or point at things that no longer resolve, says what they pointed at,
and re-scopes them: to the models whose file names the old scope mentions, to models
chosen by hand, or to the whole model. A rewrite copies the set, gives its Search the
new Selection and swaps it in place (DocumentSelectionSets.ReplaceWithCopy, same name,
position and Guid), all re-scopes of one click in ONE undo step.

MANUAL = what the user does when the API refuses a rewrite.
"""

import os
import re

MANUAL = ('Click the set in the Sets window, choose the models in the Search In tree of Find '
          'Items, then right-click the set and choose Update.')
STATUS_TEXT = {'ok': 'Working', 'empty': 'Search In is empty', 'missing': 'Points at missing items',
               'partial': 'Partly missing', 'repaired': 'Repaired', 'failed': 'Could not rewrite'}
WHOLE = None          # a scope of None means the whole model


# ---- pure half ------------------------------------------------------------------------


def classify(info):
    """'ok' | 'empty' | 'missing' | 'partial' for a scope description:
    {'is_clear', 'sources': [(text, resolved_count or None)], 'explicit': int or None,
     'resolved': int (items the scope resolves to now), 'whole': bool (the scope is
     Navisworks' own "everything", which always works)}."""
    if info.get('whole'):
        return 'ok'
    sources = info.get('sources') or []
    explicit = info.get('explicit')
    if info.get('is_clear') or (not sources and not explicit):
        return 'empty'
    if not info.get('resolved'):
        return 'missing'
    counts = [count for _text, count in sources]
    if len(counts) > 1 and any(counts) and not all(counts):
        return 'partial'          # some models found, others gone
    return 'ok'


def pointed_text(info, limit=90):
    """What the scope pointed at, for the table: source texts, else an item count."""
    texts = [t for t, _count in info.get('sources') or [] if t]
    if texts:
        text = '; '.join(texts)
    elif info.get('explicit'):
        text = '%s items' % '{:,}'.format(info['explicit'])
    else:
        text = 'Nothing'
    return text if len(text) <= limit else text[:limit - 3].rstrip() + '...'


def _stem(name):
    base = os.path.basename(str(name or '').replace('\\', '/'))
    return os.path.splitext(base)[0].lower()


def match_models(texts, model_names):
    """Models whose file name (with or without extension) appears in the scope texts,
    longest names first so 'Arch-L1' wins over 'Arch'. Returns names in model order."""
    blob = ' '.join(str(t or '') for t in texts).lower()
    if not blob:
        return []
    hits = set()
    taken = []
    for name in sorted(model_names, key=lambda n: -len(_stem(n))):
        stem = _stem(name)
        if not stem:
            continue
        for candidate in (os.path.basename(str(name)).lower(), stem):
            pattern = r'(?<![0-9a-z])' + re.escape(candidate) + r'(?![0-9a-z])'
            match = re.search(pattern, blob)
            if match and not any(a <= match.start() < b for a, b in taken):
                hits.add(name)
                taken.append((match.start(), match.end()))
                break
    return [n for n in model_names if n in hits]


def scope_label(models):
    """'Whole model' or the model names."""
    if models is WHOLE:
        return 'Whole model'
    if not models:
        return 'No models'
    if len(models) <= 3:
        return ', '.join(models)
    return '%s and %d more' % (', '.join(models[:2]), len(models) - 2)


def table_rows(entries):
    """ui.table_window rows: value = guid."""
    rows = []
    for entry in entries:
        rows.append({'value': entry['guid'],
                     'cells': [entry['name'], entry['folder'], STATUS_TEXT.get(entry['status'], entry['status']),
                               entry['pointed'], scope_label(entry['suggest']) if entry['suggest'] else
                               'No file name to match', entry.get('after', '')]})
    return rows


def status_line(entries, total):
    broken = [e for e in entries if e['status'] in ('empty', 'missing', 'partial')]
    fixed = [e for e in entries if e['status'] == 'repaired']
    text = '%d of %d search sets need a new Search In scope' % (len(broken), total)
    if fixed:
        text += '; %d repaired' % len(fixed)
    return text


# ---- API half ----------------------------------------------------------------------------


def _doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _whole_model_selection():
    """A Selection holding Navisworks' "everything" source: what a search set made by
    Find Items over the whole model (or by pynavis.sets.create) stores."""
    from pynavis._api import Api
    selection = Api.Selection()
    selection.SelectAll()
    return selection


def _is_whole(selection, whole):
    """True when a scope is the whole model. Decided by comparing it with a fresh
    SelectAll scope, never by counting what it resolves to: whether an "everything"
    source expands to items outside a running search is not something to bet a healthy
    set's status on."""
    if whole is None:
        return False
    try:
        return bool(selection.ValueEquals(whole))
    except Exception:
        return False


def inspect(saved, doc=None, whole=None):
    """The scope description classify() reads, for one search set. whole: a
    _whole_model_selection() to compare with (scan() makes one for all sets)."""
    document = _doc(doc)
    selection = saved.Search.Selection
    info = {'is_clear': bool(selection.IsClear), 'sources': [], 'explicit': None, 'resolved': 0,
            'whole': _is_whole(selection, whole)}
    if info['whole']:
        return info
    if selection.HasSelectionSources:
        for source in selection.SelectionSources:
            try:
                text = source.ToString() or ''
            except Exception:
                text = ''
            try:
                got = source.TryGetSelectedItems(document)
                count = got.Count if got is not None else 0
            except Exception:
                count = 0
            info['sources'].append((text, count))
            info['resolved'] += count
    if selection.HasExplicitSelection:
        try:
            explicit = selection.ExplicitSelection.Count
        except Exception:
            explicit = 0
        info['explicit'] = explicit
        info['resolved'] += explicit
    # What the scope resolves to as a whole is the deciding number; the per-source
    # counts above only say which part is gone.
    try:
        info['resolved'] = selection.GetSelectedItems(document).Count
    except Exception:
        pass
    return info


def scan(doc=None):
    """[entry] for every search set: {'guid', 'name', 'folder', 'status', 'pointed',
    'suggest' (model names or None), 'info'}; plus the total number of search sets."""
    from namo import find_sets, items
    document = _doc(doc)
    names = [m['name'] for m in items.models(document)]
    rows = find_sets.set_rows(find_sets.snapshot(document))
    out = []
    searches = 0
    try:
        whole = _whole_model_selection()
    except Exception:
        whole = None
    for row in rows:
        if not row.get('has_search'):
            continue
        searches += 1
        saved = find_sets.resolve_guid(row['guid'], document)
        if saved is None:
            continue
        try:
            info = inspect(saved, document, whole)
        except Exception as error:
            info = {'is_clear': False, 'sources': [('Unreadable scope: %s' % error, 0)],
                    'explicit': None, 'resolved': 0}
        status = classify(info)
        if status == 'ok':
            continue
        texts = [t for t, _c in info['sources']]
        out.append({'guid': row['guid'], 'name': row['name'],
                    'folder': find_sets.plain_folder(row['folder']), 'status': status,
                    'pointed': pointed_text(info), 'suggest': match_models(texts, names) or None,
                    'info': info, 'before': '%s: %s' % (STATUS_TEXT[status], pointed_text(info))})
    return out, searches


def _same(a, b):
    try:
        return bool(a.Equals(b))
    except Exception:
        return False


def _index_in(parent, saved):
    """Position of the set among its folder's children: the very same item first, then
    the same Guid AND name (a Guid alone could be shared by copies)."""
    children = list(parent.Children)
    for index, child in enumerate(children):
        if _same(child, saved):
            return index
    for index, child in enumerate(children):
        if str(child.Guid) == str(saved.Guid) and child.DisplayName == saved.DisplayName:
            return index
    raise LookupError('the set is no longer under its folder')


def rescope(guid, models, doc=None):
    """Rewrites one set's Search In: models None = whole model, else the named models'
    roots. Returns the live set. Raises with a sentence when it cannot."""
    from pynavis._api import Api
    from namo import find_sets, items
    document = _doc(doc)
    saved = find_sets.resolve_guid(guid, document)
    if saved is None:
        raise ValueError('The set is no longer in the model.')
    search = Api.Search(saved.Search)
    if models is WHOLE:
        search.Selection.SelectAll()
    else:
        wanted = set(n.lower() for n in models)
        roots = [m['root'] for m in items.models(document) if m['name'].lower() in wanted]
        if not roots:
            raise ValueError('None of the chosen models is in this file.')
        search.Selection.CopyFrom(items.collection(roots))
    copy = saved.CreateCopy()
    copy.CopyFrom(search)
    try:
        copy.Guid = saved.Guid
    except Exception:
        pass
    container = document.SelectionSets
    parent = saved.Parent
    root = container.RootItem
    # The root is recognised as the very same item, never by Guid: a folder and the root
    # could both carry an empty Guid, and the wrong parent means the wrong set replaced.
    at_root = parent is None or _same(parent, root)
    group = root if at_root else parent
    index = _index_in(group, saved)
    if at_root:
        container.ReplaceWithCopy(index, copy)
    else:
        container.ReplaceWithCopy(group, index, copy)
    try:
        return list(group.Children)[index]
    except Exception:
        return find_sets.resolve_guid(guid, document)


def rescope_many(entries, models_for, doc=None):
    """Re-scopes several sets in ONE undo step. models_for(entry) -> model names, WHOLE,
    or False to skip. Updates each entry ('status', 'after'). Returns (done, failed)."""
    from pynavis import viewpoints
    document = _doc(doc)
    done = failed = 0
    try:
        whole = _whole_model_selection()
    except Exception:
        whole = None
    with viewpoints.transaction('Repair Search In', document):
        for entry in entries:
            models = models_for(entry)
            if models is False:
                continue
            try:
                live = rescope(entry['guid'], models, document)
                info = inspect(live, document, whole) if live is not None else None
                ok = info is not None and classify(info) == 'ok'
                entry['status'] = 'repaired' if ok else 'failed'
                entry['after'] = scope_label(models) if ok else \
                    'Rewritten but still finds nothing. %s' % MANUAL
                done += 1 if ok else 0
                failed += 0 if ok else 1
            except Exception as error:
                entry['status'] = 'failed'
                entry['after'] = '%s %s' % (str(error).rstrip('.') + '.', MANUAL)
                failed += 1
    return done, failed

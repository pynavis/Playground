# -*- coding: utf-8 -*-
"""Model Wipe: purge chosen kinds of data from the document, counted first, confirmed twice.

What can go, in the order it is offered (OPTIONS): saved viewpoints, selection sets,
clash tests, comments on saved viewpoints, appearance overrides, hidden state,
permanent item transforms, TimeLiner tasks and Playground data stored in the document.
Redlines are listed but never wiped: the Navisworks .NET API has no route to them
(only internal Interop members mention redlines), so they are always reported as left.

Every document edit runs in ONE transaction named 'Model Wipe', each step in its own
try so one refusal does not stop the others. Playground data (namo.docdb, the document's
own database) is wiped AFTER that transaction because docdb writes must not run
inside one, and they are not undoable.

Nothing is reported as wiped on trust: after the edits every kind that can be counted
is counted again, and a kind that is still there is reported as not wiped, with how
many are left. Only the open document in memory changes; no file is written, so the
NWF or NWD on disk stays as it was until the user saves.

Pure half (labels, the confirmation sentence, the result summary) first; the API half
counts and executes.
"""

OPTIONS = [
    ('viewpoints', 'Saved viewpoints'),
    ('sets', 'Selection sets'),
    ('clash_tests', 'Clash tests'),
    ('comments', 'Comments on saved viewpoints'),
    ('redlines', 'Redlines'),
    ('overrides', 'Appearance overrides'),
    ('hidden', 'Hidden state'),
    ('transforms', 'Item transforms (moves made with Item Tools)'),
    ('timeliner', 'TimeLiner tasks'),
    ('playground_data', 'Playground data stored in the document'),
]
OPTION_IDS = [o[0] for o in OPTIONS]
LABELS = dict(OPTIONS)
NO_ROUTE = ('redlines',)
REDLINE_NOTE = ('Redlines cannot be wiped by a script: Navisworks offers no way to reach '
                'them. Erase them in Navisworks with Review > Redline > Erase.')

# Kinds removed one by one (with a count) vs. kinds reset as a whole.
_COUNTED = {
    'viewpoints': ('saved viewpoint', 'saved viewpoints'),
    'sets': ('selection set', 'selection sets'),
    'clash_tests': ('clash test', 'clash tests'),
    'comments': ('comment', 'comments'),
    'timeliner': ('TimeLiner task', 'TimeLiner tasks'),
    'playground_data': ('Playground record', 'Playground records'),
}
_RESETS = {
    'overrides': 'appearance overrides',
    'hidden': 'hidden state',
    'transforms': 'item transforms',
}


def _n(count):
    return '{:,}'.format(int(count))


def _join(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ''
    if len(parts) == 1:
        return parts[0]
    return '%s and %s' % (', '.join(parts[:-1]), parts[-1])


def phrase(option_id, count, approx=False):
    """How one option reads in a sentence: '24 saved viewpoints', 'all clash tests',
    'appearance overrides', 'hidden state (at least 12 hidden items)'."""
    if option_id in _COUNTED:
        one, many = _COUNTED[option_id]
        if count is None:
            return 'all %s' % many
        if approx:
            return 'at least %s %s' % (_n(count), many)
        return '%s %s' % (_n(count), one if count == 1 else many)
    if option_id == 'hidden' and count:
        return 'hidden state (%s%s hidden item%s)' % ('at least ' if approx else '', _n(count),
                                                     '' if count == 1 else 's')
    return _RESETS.get(option_id, LABELS.get(option_id, option_id).lower())


def label_with_count(option_id, count, approx=False):
    """The option's line in the chooser: 'Saved viewpoints (24)', 'Clash tests (none)',
    'Appearance overrides (all)', 'Hidden state (at least 12 items)'."""
    label = LABELS[option_id]
    if option_id in NO_ROUTE:
        return '%s (not reachable by scripts)' % label
    if option_id == 'hidden':
        if count is None:
            return '%s (unhide everything)' % label
        if count == 0:
            return '%s (none found%s)' % (label, ' in the items checked' if approx else '')
        return '%s (%s%s item%s)' % (label, 'at least ' if approx else '', _n(count),
                                     '' if count == 1 else 's')
    if count is None:
        return '%s (all)' % label
    if count == 0:
        return '%s (none)' % label
    return '%s (%s%s)' % (label, 'at least ' if approx else '', _n(count))


def option_rows(counts, approx=()):
    """[(label, id)] for the chooser: every option except the ones with no route."""
    return [(label_with_count(o, counts.get(o), o in approx), o) for o in OPTION_IDS
            if o not in NO_ROUTE]


def form_fields(counts, approx=(), doc_name='this document'):
    """The chooser form (namo.ui.form fields): one 'multi' of every option with its
    count, nothing ticked, and the redline note."""
    return [
        {'kind': 'label', 'text': 'Choose what to remove from %s. Nothing is ticked to start with.'
                                  % doc_name},
        {'kind': 'multi', 'key': 'chosen', 'label': 'Remove or reset',
         'options': option_rows(counts, approx), 'default': []},
        {'kind': 'label', 'text': REDLINE_NOTE, 'muted': True},
    ]


def confirm_text(chosen, counts, approx=(), doc_name='this document'):
    """The second confirmation, naming exact counts:
    'Remove 24 saved viewpoints, 3 selection sets and 5 clash tests from Model.nwf?
    Also reset appearance overrides. ...'"""
    chosen = [o for o in OPTION_IDS if o in chosen and o not in NO_ROUTE]
    removes = [phrase(o, counts.get(o), o in approx) for o in chosen if o in _COUNTED]
    resets = [phrase(o, counts.get(o), o in approx) for o in chosen if o in _RESETS]
    sentences = []
    if removes:
        sentences.append('Remove %s from %s?' % (_join(removes), doc_name))
        if resets:
            sentences.append('Also reset %s.' % _join(resets))
    elif resets:
        sentences.append('Reset %s in %s?' % (_join(resets), doc_name))
    if 'comments' in chosen and 'viewpoints' in chosen:
        sentences.append('The comments go with the viewpoints.')
    if 'playground_data' in chosen:
        sentences.append('Playground data cannot be brought back with Ctrl+Z.')
    sentences.append('Save a copy first if you may need any of it.')
    return ' '.join(sentences)


def summary(result, counts, approx=()):
    """(toast level, message, detail) from execute()'s result {'done', 'failed', 'left'}:
    success when everything chosen went, warning when something failed or was left."""
    done = [o for o in OPTION_IDS if o in result.get('done', [])]
    failed = list(result.get('failed', []))
    left = list(result.get('left', []))
    done_text = [phrase(o, counts.get(o), o in approx) for o in done]
    if not done and failed:
        first_id, reason = failed[0]
        return ('error', 'Nothing was wiped',
                '%s: %s' % (LABELS.get(first_id, first_id), reason))
    if not done:
        return ('info', 'Nothing was wiped', 'Nothing chosen could be removed.')
    if len(done_text) <= 2:
        message = 'Wiped %s' % _join(done_text)
    else:
        message = 'Wiped %s kinds of data' % len(done_text)
    details = []
    if len(done_text) > 2:
        details.append('Removed %s.' % _join(done_text))
    if failed:
        details.append('Could not wipe %s.' % _join(
            ['%s (%s)' % (LABELS.get(o, o).lower(), reason) for o, reason in failed]))
    if left:
        details.append(' '.join(reason for _o, reason in left))
    level = 'warning' if failed else 'success'
    return (level, message, ' '.join(details) or None)


# ---- API half ------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _is(item, type_name):
    from pynavis._api import Api
    kind = getattr(Api, type_name, None)
    return kind is not None and isinstance(item, kind)


def saved_tree_counts(root):
    """(items, folders, comments) under a saved-items root: viewpoints (or sets) and
    animations count as items, their cuts do not; comments on every node are summed."""
    items = folders = comments = 0
    stack = list(root.Children)
    while stack:
        node = stack.pop()
        try:
            comments += int(node.Comments.Count)
        except Exception:
            pass
        if _is(node, 'FolderItem'):
            folders += 1
            stack.extend(list(node.Children))
        else:
            items += 1
    return items, folders, comments


def _commented_items(root):
    out = []
    stack = list(root.Children)
    while stack:
        node = stack.pop()
        try:
            if int(node.Comments.Count) > 0:
                out.append(node)
        except Exception:
            pass
        if _is(node, 'GroupItem'):
            try:
                stack.extend(list(node.Children))
            except Exception:
                pass
    return out


def _clash_tests(doc):
    try:
        from namo import clashdata
        return clashdata.tests(doc)
    except Exception:
        return None


def _hidden_count(doc, budget, report=None):
    count = walked = 0
    models = doc.Models
    for index in range(models.Count):
        for item in models[index].RootItem.DescendantsAndSelf:
            walked += 1
            try:
                if item.IsHidden:
                    count += 1
            except Exception:
                pass
            if report is not None and walked % 5000 == 0:
                report(0.5, 'Counting hidden items (%s)' % _n(walked))
            if walked >= budget:
                return count, True
    return count, False


def _docdb_count(doc):
    from namo import docdb
    if not docdb.available(doc):
        return 0
    total = len(docdb.kv_keys(doc=doc))
    for collection in docdb.collections(doc=doc):
        total += len(docdb.records(collection, doc=doc))
    return total


def counts(doc=None, progress=None, hidden_budget=300000):
    """({option id: count or None}, approx ids): what each option would remove now.
    None means it cannot be counted (overrides, transforms) or is not reachable.
    approx holds ids whose count is a lower bound (a budgeted walk)."""
    document = _doc(doc)
    out = {}
    approx = []
    if progress is not None:
        progress(0.0, 'Counting saved viewpoints')
    try:
        views, _folders, comments = saved_tree_counts(document.SavedViewpoints.RootItem)
        out['viewpoints'], out['comments'] = views, comments
    except Exception:
        out['viewpoints'], out['comments'] = None, None
    try:
        out['sets'] = saved_tree_counts(document.SelectionSets.RootItem)[0]
    except Exception:
        out['sets'] = None
    tests = _clash_tests(document)
    out['clash_tests'] = 0 if tests is None else len(tests)
    out['redlines'] = None
    out['overrides'] = None
    out['transforms'] = None
    if progress is not None:
        progress(0.3, 'Counting hidden items')
    try:
        hidden, cut = _hidden_count(document, hidden_budget, progress)
        out['hidden'] = hidden
        if cut:
            approx.append('hidden')
    except Exception:
        out['hidden'] = None
    if progress is not None:
        progress(0.8, 'Counting TimeLiner tasks')
    from namo import preflight
    timeliner = preflight.timeliner_of(document)
    try:
        out['timeliner'] = 0 if timeliner is None else int(timeliner.TaskTotalTasks())
    except Exception:
        out['timeliner'] = None
    try:
        out['playground_data'] = _docdb_count(document)
    except Exception:
        out['playground_data'] = None
    if progress is not None:
        progress(1.0, 'Done')
    return out, approx


def _clear_timeliner(timeliner):
    """Removes every task: TasksClear(), then, if any task is still there, one
    TasksCopyFrom of an empty list, then TaskRemoveAt on the top-level tasks from the
    last one back."""
    try:
        timeliner.TasksClear()
    except Exception:
        pass
    if int(timeliner.TaskTotalTasks()) == 0:
        return
    try:
        from System.Collections.Generic import List
        from pynavis._api import Api
        timeliner.TasksCopyFrom(List[Api.SavedItem]())
    except Exception:
        pass
    if int(timeliner.TaskTotalTasks()) == 0:
        return
    count = int(timeliner.TasksRoot.Children.Count)
    for index in range(count - 1, -1, -1):
        timeliner.TaskRemoveAt(index)


def _clear_saved(part):
    """Empties a saved-items part of the document (saved viewpoints or selection sets):
    Clear(), then, if anything is left, Remove() on each top-level item, the way the
    shipped viewpoint Deleter removes them."""
    try:
        part.Clear()
    except Exception:
        pass
    left = list(part.RootItem.Children)
    for item in left:
        part.Remove(item)


def remaining(doc, option_id):
    """How many of a counted kind are in the document now, or None when it cannot be
    counted (the check after a wipe)."""
    document = _doc(doc)
    try:
        if option_id == 'viewpoints':
            return saved_tree_counts(document.SavedViewpoints.RootItem)[0]
        if option_id == 'comments':
            return saved_tree_counts(document.SavedViewpoints.RootItem)[2]
        if option_id == 'sets':
            return saved_tree_counts(document.SelectionSets.RootItem)[0]
        if option_id == 'clash_tests':
            tests = _clash_tests(document)
            return None if tests is None else len(tests)
        if option_id == 'timeliner':
            from namo import preflight
            timeliner = preflight.timeliner_of(document)
            return None if timeliner is None else int(timeliner.TaskTotalTasks())
        if option_id == 'playground_data':
            return _docdb_count(document)
    except Exception:
        return None
    return None


def verify(doc, done, failed):
    """Moves every kind in `done` that is still in the document to `failed`, saying how
    many are left. Returns (done, failed)."""
    kept = []
    for option_id in done:
        left = remaining(doc, option_id)
        if left:
            one, many = _COUNTED.get(option_id, ('item', 'items'))
            failed.append((option_id, '%s %s still there' % (_n(left), one if left == 1 else many)))
        else:
            kept.append(option_id)
    return kept, failed


def execute(doc, chosen):
    """Wipes the chosen options. Returns {'done': [ids], 'failed': [(id, reason)],
    'left': [(id, sentence)]}. Document edits are one transaction; Playground data after it."""
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    chosen = [o for o in OPTION_IDS if o in chosen]
    done, failed, left = [], [], []

    def step(option_id, work):
        try:
            work()
            done.append(option_id)
        except Exception as error:
            failed.append((option_id, str(error) or type(error).__name__))

    def clear_comments():
        from pynavis._api import Api
        for item in _commented_items(document.SavedViewpoints.RootItem):
            document.SavedViewpoints.EditComments(item, Api.CommentCollection())

    def clear_clash():
        from pynavis import clash
        clash.get_clash(document).TestsData.TestsClear()

    def clear_timeliner():
        from namo import preflight
        timeliner = preflight.timeliner_of(document)
        if timeliner is None:
            raise RuntimeError('TimeLiner is not available')
        _clear_timeliner(timeliner)

    document_steps = [
        ('comments', clear_comments),
        ('viewpoints', lambda: _clear_saved(document.SavedViewpoints)),
        ('sets', lambda: _clear_saved(document.SelectionSets)),
        ('clash_tests', clear_clash),
        ('overrides', lambda: document.Models.ResetAllPermanentMaterials()),
        ('hidden', lambda: document.Models.ResetAllHidden()),
        ('transforms', lambda: document.Models.ResetAllPermanentTransforms()),
        ('timeliner', clear_timeliner),
    ]
    wanted = [(o, fn) for o, fn in document_steps if o in chosen]
    comments_with_views = 'comments' in chosen and 'viewpoints' in chosen
    if comments_with_views:
        wanted = [(o, fn) for o, fn in wanted if o != 'comments']
    if wanted:
        with transaction('Model Wipe', document):
            for option_id, work in wanted:
                step(option_id, work)
    if 'playground_data' in chosen:
        step('playground_data', lambda: _wipe_docdb(document))
    done, failed = verify(document, done, failed)
    if comments_with_views:
        if 'viewpoints' in done:
            done.append('comments')
        else:
            failed.append(('comments', 'they stay with the viewpoints that could not be removed'))
    if 'redlines' in chosen:
        left.append(('redlines', 'Redlines were left: Navisworks has no script route to them.'))
    return {'done': done, 'failed': failed, 'left': left}


def _wipe_docdb(doc):
    from namo import docdb
    if not docdb.available(doc):
        return
    for key in docdb.kv_keys(doc=doc):
        docdb.kv_delete(key, doc=doc)
    for collection in docdb.collections(doc=doc):
        for record in docdb.records(collection, doc=doc):
            docdb.record_delete(collection, record.get('id'), doc=doc)

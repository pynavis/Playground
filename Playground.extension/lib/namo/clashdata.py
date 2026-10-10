# -*- coding: utf-8 -*-
"""One reader for every clash tool: snapshots, groups, run-to-run comparison,
history, images, and the per-result edits that are safe at scale.

Reading never edits anything. snapshot() builds on pynavis.clash.snapshot_results
(element/grid memos, field-measured) and enriches each row from the live result in
ONE extra pass over the same leaves:

  ORDER CLAIM (verified in pynavis/clash.py source): snapshot_results walks
  test.Children depth first, recursing into a ClashResultGroup BEFORE moving to the
  next sibling and appending only ClashResult leaves; row['id'] is the index in that
  walk. results() below walks with exactly the same two isinstance tests in exactly
  the same order (clash.walk_results uses _util.flatten, which would also yield a
  non-group non-result child, so it is NOT used for alignment). snapshot() still
  checks every pair: equal counts and equal DisplayName per id, or it raises.

Row keys: pynavis' own (id, name, center, item_a, item_b, item_a_name,
item_b_name, level, grid, model_a, model_b, status, assigned, group) plus:
  test, test_guid, guid, distance (model units, negative = penetration),
  distance_m, center_m, created / approved_time / resolved_time (ISO text or None),
  approved_by, description, priority, comments (count), trade_a, trade_b
  (namo.trades of the model names), group_guid (innermost group or None), key
  (pair_key). model_a/model_b are filled from the element's model root when
  pynavis left them blank.

Edits (set_assigned, set_description, set_priority, add_comment) use the per-result
TestsEditResult* calls inside one transaction: fine for hundreds of results; measure
before running them over tens of thousands. Restructuring results (grouping) is
pynavis.clash.apply_plan's job, never this module's.

progress callbacks here are progress(fraction 0..1, label) like namo.reports; a
callback that returns exactly False cancels and raises Cancelled.
"""

import datetime

from namo.items import Cancelled  # noqa: F401  (one Cancelled for every namo walk)

STATUSES = ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']
CLOSED = ('Resolved', 'Approved')

# The compact row kept in history (a list per row, in this order).
HISTORY_FIELDS = ['key', 'test', 'status', 'distance_m', 'created', 'trade_a', 'trade_b',
                  'name', 'grid', 'level']
HISTORY_STORE = 'clash-history'
HISTORY_INDEX = 'clash-history-index'

KEY_CELL_M = 0.1      # pair_key rounds clash centres to this many metres


# ---- pure: keys and comparison ---------------------------------------------------


def pair_key(row):
    """Stable text identifying a clash across runs: the two element keys sorted
    (so A/B swaps match) and the centre rounded to KEY_CELL_M metres
    ('<a>|<b>@x,y,z' in decimetres). Uses row['center_m'] when present (snapshot
    rows), else row['center'] read as metres. A row that already carries 'key'
    (history rows) keeps it."""
    if row.get('key') and not (row.get('item_a') or row.get('item_b')):
        return row['key']
    a = str(row.get('item_a') or '')
    b = str(row.get('item_b') or '')
    pair = '|'.join(sorted([a, b]))
    center = row.get('center_m')
    if center is None:
        center = row.get('center')
    if center is None:
        return pair + '@-'
    cell = tuple(int(round(float(v) / KEY_CELL_M)) for v in center)
    return '%s@%d,%d,%d' % (pair, cell[0], cell[1], cell[2])


def split_key(key):
    """(pair_text, (cx, cy, cz) or None) from a pair_key."""
    if '@' not in key:
        return key, None
    pair, _sep, cell = key.rpartition('@')
    if cell == '-':
        return pair, None
    try:
        parts = tuple(int(p) for p in cell.split(','))
        return pair, parts if len(parts) == 3 else None
    except ValueError:
        return pair, None


def is_closed(row):
    return str(row.get('status') or '') in CLOSED


def _key_of(row):
    return row.get('key') or pair_key(row)


def compare(old_rows, new_rows):
    """Matches two snapshots (or history loads) clash by clash. PURE.

    Matching: exact pair_key first; then, for what is left, the same element pair
    with a centre no more than one KEY_CELL_M cell away on each axis (a centre that
    sat on a rounding boundary). Rows with no element keys match on the cell alone.

    Returns {
      'new':        new rows with no match that are open (not Resolved/Approved),
      'fixed':      OLD rows that were open and are now gone or Resolved/Approved,
      'persisting': new rows matched to an open old row and still open,
      'status_changed': [(old, new)] matched pairs whose status differs,
      'closed_new': new rows with no match that are already Resolved/Approved,
      'matched':    how many pairs matched,
    } Each list keeps the order of the snapshot it came from.
    """
    old_rows = list(old_rows or [])
    new_rows = list(new_rows or [])
    by_key = {}
    for index, row in enumerate(old_rows):
        by_key.setdefault(_key_of(row), []).append(index)

    match_of_new = [None] * len(new_rows)
    old_taken = [False] * len(old_rows)
    for index, row in enumerate(new_rows):
        bucket = by_key.get(_key_of(row))
        while bucket:
            # Several old clashes can share a key (the same two elements within one cell):
            # prefer the one with the same name, which Clash Detective keeps across runs,
            # so a status change is reported on the right clash.
            pick = 0
            for position, old_index in enumerate(bucket):
                if (not old_taken[old_index]
                        and old_rows[old_index].get('name') == row.get('name')):
                    pick = position
                    break
            candidate = bucket.pop(pick)
            if not old_taken[candidate]:
                old_taken[candidate] = True
                match_of_new[index] = candidate
                break

    # Tolerant pass: same pair, neighbouring cell.
    loose = {}
    for index, row in enumerate(old_rows):
        if old_taken[index]:
            continue
        pair, cell = split_key(_key_of(row))
        if cell is not None:
            loose.setdefault(pair, []).append((index, cell))
    if loose:
        for index, row in enumerate(new_rows):
            if match_of_new[index] is not None:
                continue
            pair, cell = split_key(_key_of(row))
            if cell is None or pair not in loose:
                continue
            best = None
            for old_index, old_cell in loose[pair]:
                if old_taken[old_index]:
                    continue
                gap = max(abs(cell[i] - old_cell[i]) for i in range(3))
                if gap <= 1 and (best is None or gap < best[0]):
                    best = (gap, old_index)
            if best is not None:
                old_taken[best[1]] = True
                match_of_new[index] = best[1]

    result = {'new': [], 'fixed': [], 'persisting': [], 'status_changed': [],
              'closed_new': [], 'matched': 0}
    fixed_by_old = set()
    for index, row in enumerate(new_rows):
        old_index = match_of_new[index]
        if old_index is None:
            (result['closed_new'] if is_closed(row) else result['new']).append(row)
            continue
        result['matched'] += 1
        old = old_rows[old_index]
        if str(old.get('status')) != str(row.get('status')):
            result['status_changed'].append((old, row))
        if not is_closed(old):
            if is_closed(row):
                fixed_by_old.add(old_index)
            else:
                result['persisting'].append(row)
    for index, row in enumerate(old_rows):
        if is_closed(row):
            continue
        if not old_taken[index] or index in fixed_by_old:
            result['fixed'].append(row)
    return result


def counts(rows):
    """{'total': n, 'by_status': {status: n}} for a list of rows."""
    by_status = {}
    for row in rows:
        status = str(row.get('status') or '')
        by_status[status] = by_status.get(status, 0) + 1
    return {'total': len(rows), 'by_status': by_status}


def iso(value):
    """ISO 'YYYY-MM-DDTHH:MM:SS' from a .NET DateTime, a python datetime, or None."""
    if value is None:
        return None
    try:
        if isinstance(value, datetime.datetime):
            return value.strftime('%Y-%m-%dT%H:%M:%S')
        return '%04d-%02d-%02dT%02d:%02d:%02d' % (int(value.Year), int(value.Month), int(value.Day),
                                                  int(value.Hour), int(value.Minute), int(value.Second))
    except Exception:
        return None


def unique_names(names):
    """names made unique by appending ' (2)', ' (3)'... in order (for test names
    used as dict keys)."""
    seen = {}
    out = []
    for name in names:
        name = str(name)
        if name not in seen:
            seen[name] = 1
            out.append(name)
            continue
        n = seen[name] + 1
        while '%s (%d)' % (name, n) in seen:
            n += 1
        seen[name] = n
        candidate = '%s (%d)' % (name, n)
        seen[candidate] = 1
        out.append(candidate)
    return out


# ---- pure: history records ---------------------------------------------------------


def compact_rows(rows):
    """Rows as lists in HISTORY_FIELDS order (key filled from pair_key)."""
    out = []
    for row in rows:
        values = []
        for field in HISTORY_FIELDS:
            if field == 'key':
                values.append(_key_of(row))
            else:
                values.append(row.get(field))
        out.append(values)
    return out


def expand_rows(fields, rows):
    """Compact lists back to dicts (fields: the record's own field list)."""
    return [dict(zip(fields, values)) for values in rows]


def history_record(rows_by_test, label=None, now=None):
    """A history record ready for the store: {'id', 'label', 'time', 'counts':
    {test: counts()}, 'fields', 'tests': {test: compact rows}}."""
    stamp = now or datetime.datetime.now()
    time_text = stamp.strftime('%Y-%m-%dT%H:%M:%S')
    record_id = 'h-' + stamp.strftime('%Y%m%d-%H%M%S-') + ('%06d' % stamp.microsecond)
    tests = {}
    totals = {}
    for name in sorted(rows_by_test):
        rows = rows_by_test[name]
        tests[name] = compact_rows(rows)
        totals[name] = counts(rows)
    return {'id': record_id, 'label': label or time_text.replace('T', ' '), 'time': time_text,
            'counts': totals, 'fields': list(HISTORY_FIELDS), 'tests': tests}


def history_entry(record):
    """The index entry for a record: {'id', 'label', 'time', 'counts'}."""
    return {'id': record['id'], 'label': record.get('label'), 'time': record.get('time'),
            'counts': record.get('counts') or {}}


def record_rows(record):
    """{test: [row dicts]} from a stored record."""
    fields = record.get('fields') or HISTORY_FIELDS
    tests = record.get('tests') or {}
    return dict((name, expand_rows(fields, tests[name])) for name in tests)


# ---- history stores (namo.store; replaceable in tests) -------------------------------


def _stores(doc_path):
    from namo import store
    return (store.Store(HISTORY_INDEX, doc_path=doc_path, scope='doc'),
            store.RecordStore(HISTORY_STORE, doc_path=doc_path, scope='doc'))


_STORES = _stores          # test seam: replace with a function returning fakes


def _rebuilt_index(records):
    entries = [history_entry(r) for r in records.list() if isinstance(r, dict) and r.get('id')]
    entries.sort(key=lambda e: (e.get('time') or '', e.get('id') or ''))
    return entries


def save_history(doc_path, rows_by_test, label=None):
    """Keeps one snapshot of every test as a history record for the document at
    doc_path (local/shared/model per namo.config data_mode). Returns its index
    entry {'id', 'label', 'time', 'counts'}."""
    index_store, records = _STORES(doc_path)
    record = history_record(rows_by_test, label)
    base = record['id']
    n = 2
    while records.get(record['id']) is not None:      # two saves in one clock tick
        record['id'] = '%s-%d' % (base, n)
        n += 1
    records.put(record)
    entry = history_entry(record)

    def add(entries):
        if not isinstance(entries, list):
            entries = _rebuilt_index(records)
        entries = [e for e in entries if e.get('id') != entry['id']]
        entries.append(entry)
        entries.sort(key=lambda e: (e.get('time') or '', e.get('id') or ''))
        return entries

    index_store.update(add, default=None)
    return entry


def list_history(doc_path):
    """[{'id', 'label', 'time', 'counts'}] oldest first. Rebuilt from the records
    themselves when the index is missing."""
    index_store, records = _STORES(doc_path)
    entries = index_store.load(None)
    if not isinstance(entries, list):
        entries = _rebuilt_index(records)
    return entries


def load_history(doc_path, history_id):
    """{test: [rows]} (HISTORY_FIELDS keys) of one history record, or None."""
    _index_store, records = _STORES(doc_path)
    record = records.get(history_id)
    if not isinstance(record, dict):
        return None
    return record_rows(record)


def delete_history(doc_path, history_id):
    """Forgets one history record. True when it existed."""
    index_store, records = _STORES(doc_path)
    existed = records.get(history_id) is not None
    records.delete(history_id)

    def drop(entries):
        if not isinstance(entries, list):
            entries = _rebuilt_index(records)
        return [e for e in entries if e.get('id') != history_id]

    index_store.update(drop, default=None)
    return existed


# ==== API half (Navisworks only; lazy imports) ======================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _clash():
    from pynavis import clash
    return clash


def _clash_api():
    """Autodesk.Navisworks.Api.Clash, imported AFTER pynavis.clash has added the
    assembly reference (IronPython only sees namespaces of referenced assemblies)."""
    _clash()
    import Autodesk.Navisworks.Api.Clash as ClashApi
    return ClashApi


def _list_tests(doc):
    return list(_clash().walk_tests(_doc(doc)))


def tests(doc=None):
    """Every ClashTest in the document, test folders flattened, tree order."""
    return _list_tests(doc)


def test_path(test):
    """'Folder/Sub/Test name' for a test (just the name at the top level)."""
    names = []
    node = test
    while node is not None:
        try:
            name = node.DisplayName
        except Exception:
            break
        names.append(name)
        node = node.Parent
    names.reverse()
    # the clash tests root folder, when it shows up as a parent, has no name
    return '/'.join(n for n in names if n)


def test_by_name(name, doc=None):
    """The first test named `name` (exact, then case-insensitive, then as a
    'Folder/Test' path), or None."""
    all_tests = _list_tests(doc)
    for test in all_tests:
        if test.DisplayName == name:
            return test
    lowered = str(name).strip().lower()
    for test in all_tests:
        if test.DisplayName.strip().lower() == lowered:
            return test
    for test in all_tests:
        if test_path(test).lower() == lowered:
            return test
    return None


def _walk_leaves(test):
    """[(ClashResult, innermost ClashResultGroup or None)] in snapshot_results' order."""
    ClashApi = _clash_api()
    out = []

    def walk(children, group):
        for child in children:
            if isinstance(child, ClashApi.ClashResultGroup):
                walk(child.Children, child)
            elif isinstance(child, ClashApi.ClashResult):
                out.append((child, group))

    walk(test.Children, None)
    return out


def results(test):
    """Every ClashResult leaf of a test, groups flattened, in snapshot order:
    results(test)[row['id']] is the live result behind a snapshot row."""
    return [result for result, _group in _walk_leaves(test)]


def groups(test):
    """Top-level result groups: [{'name', 'guid', 'result' (the ClashResultGroup),
    'count' (leaves at any depth), 'statuses' {status: n}}], tree order."""
    ClashApi = _clash_api()
    out = []
    for child in test.Children:
        if not isinstance(child, ClashApi.ClashResultGroup):
            continue
        statuses = {}
        total = [0]

        def walk(children):
            for node in children:
                if isinstance(node, ClashApi.ClashResultGroup):
                    walk(node.Children)
                elif isinstance(node, ClashApi.ClashResult):
                    total[0] += 1
                    status = str(node.Status)
                    statuses[status] = statuses.get(status, 0) + 1

        walk(child.Children)
        out.append({'name': child.DisplayName, 'guid': str(child.Guid), 'result': child,
                    'count': total[0], 'statuses': statuses})
    return out


def _assignee_name(assignee):
    try:
        if assignee is not None and assignee.Assigned:
            return assignee.DisplayName or ''
    except Exception:
        pass
    return ''


def _trade_lookup():
    """trade_of(model name) with namo.trades and the configured rules, memoised;
    'Unassigned' when trades is unavailable."""
    memo = {}
    try:
        from namo import config, trades
        rules = trades.rules_from_config(config.load())
    except Exception:
        trades = None
        rules = None

    def lookup(name):
        name = name or ''
        if name not in memo:
            try:
                memo[name] = trades.trade_of(name, rules) if trades is not None else 'Unassigned'
            except Exception:
                memo[name] = 'Unassigned'
        return memo[name]
    return lookup


def _element_model(result, side):
    from namo import items
    composite = result.CompositeItem1 if side == 'a' else result.CompositeItem2
    if composite is not None:
        return items.model_name(composite)
    leaf = result.Item1 if side == 'a' else result.Item2
    if leaf is None:
        return ''
    return items.model_name(leaf)


def _report(progress, fraction, label):
    if progress is not None and progress(fraction, label) == False:   # noqa: E712
        raise Cancelled()


def snapshot(test, doc=None, progress=None):
    """Plain-dict rows for every clash in the test (see the module docstring for
    the keys), read-only. progress(fraction, label) is called through the read; a
    callback returning False raises Cancelled (discard the partial read)."""
    clash = _clash()
    document = _doc(doc)
    name = test.DisplayName
    test_guid = str(test.Guid)
    leaves = _walk_leaves(test)
    total = len(leaves) or 1
    u2m = clash.units_to_meters(document)
    _report(progress, 0.0, 'Reading %s' % name)

    def on_read(done):
        if progress is None:
            return None
        if progress(0.7 * done / float(total), 'Reading %s: %s of %s' % (name, '{:,}'.format(done),
                                                                         '{:,}'.format(len(leaves)))) == False:  # noqa: E712
            return False
        return None

    try:
        rows = clash.snapshot_results(test, document, on_read)
    except clash.Cancelled:
        raise Cancelled()
    if len(rows) != len(leaves):
        raise RuntimeError('The clash results of %s changed while they were read; run it again.' % name)

    trade_of = _trade_lookup()
    models = {}
    step = max(1, len(rows) // 50)
    for index, row in enumerate(rows):
        result, group = leaves[index]
        if result.DisplayName != row['name']:
            raise RuntimeError('The clash results of %s are out of order; run it again.' % name)
        if not row.get('model_a') or not row.get('model_b'):
            for side in ('a', 'b'):
                field = 'model_' + side
                if not row.get(field):
                    memo_key = (side, row.get('item_' + side))
                    if memo_key not in models:
                        models[memo_key] = _element_model(result, side)
                    row[field] = models[memo_key]
        distance = float(result.Distance)
        center = row.get('center')
        row['test'] = name
        row['test_guid'] = test_guid
        row['guid'] = str(result.Guid)
        row['distance'] = distance
        row['distance_m'] = distance * u2m
        row['center_m'] = None if center is None else tuple(v * u2m for v in center)
        row['created'] = iso(result.CreatedTime)
        row['approved_time'] = iso(result.ApprovedTime)
        row['resolved_time'] = iso(result.ResolvedTime)
        row['approved_by'] = _assignee_name(result.ApprovedBy)
        row['description'] = result.Description or ''
        row['priority'] = int(result.Priority)
        row['comments'] = int(result.Comments.Count)
        row['trade_a'] = trade_of(row.get('model_a'))
        row['trade_b'] = trade_of(row.get('model_b'))
        row['group_guid'] = str(group.Guid) if group is not None else None
        row['key'] = pair_key(row)
        if progress is not None and index % step == 0:
            _report(progress, 0.7 + 0.3 * index / float(total), 'Reading %s' % name)
    _report(progress, 1.0, 'Read %s' % name)
    return rows


def snapshot_all(tests=None, doc=None, progress=None):
    """{test name: rows} for several tests (None = every test), names made unique
    with ' (2)' when two tests share one. progress(fraction, label) spans them all."""
    document = _doc(doc)
    chosen = _list_tests(document) if tests is None else list(tests)
    names = unique_names([t.DisplayName for t in chosen])
    out = {}
    count = len(chosen) or 1
    for position, test in enumerate(chosen):
        def scaled(fraction, label, _p=position):
            if progress is None:
                return None
            return progress((_p + fraction) / float(count), label)
        out[names[position]] = snapshot(test, document, scaled if progress is not None else None)
    return out


def image(result, path, width=640, height=360, doc=None, style='scene', quality=90):
    """The result's image (TestsImageForResult) saved to path; returns path."""
    from namo import images
    return images.clash(result, path, width, height, doc, style, quality)


def viewpoint(result, doc=None):
    """The result's Viewpoint (TestsViewpointForResult): apply it with
    doc.CurrentViewpoint.CopyFrom(vp) or namo.camera.from_viewpoint(vp)."""
    return _clash().get_clash(_doc(doc)).TestsData.TestsViewpointForResult(result)


def show(result, doc=None):
    """Moves the view to the result's viewpoint and selects its two items."""
    from pynavis._api import Api
    document = _doc(doc)
    document.CurrentViewpoint.CopyFrom(viewpoint(result, document))
    coll = Api.ModelItemCollection()
    for item in (result.Item1, result.Item2):
        if item is not None:
            coll.Add(item)
    document.CurrentSelection.CopyFrom(coll)


def _results_list(results_):
    """A list from one result/group or many."""
    if results_ is None:
        return []
    ClashApi = _clash_api()
    if isinstance(results_, (ClashApi.ClashResult, ClashApi.ClashResultGroup)):
        return [results_]
    try:
        return list(results_)
    except TypeError:
        return [results_]


def _edit_all(results_, doc, label, edit):
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    data = _clash().get_clash(document).TestsData
    targets = _results_list(results_)
    if not targets:
        return 0
    done = 0
    with transaction(label, document):
        for result in targets:
            edit(data, result)
            done += 1
    return done


def set_assigned(results, name, doc=None):
    """Assigns every result to `name` ('' or None unassigns). One undo step.
    Returns how many were edited."""
    from pynavis._api import Api

    def edit(data, result):
        if name:
            who = Api.Assignee(str(name))
        else:
            who = Api.Assignee()
            try:
                who.Unassign()
            except Exception:
                pass
        data.TestsEditResultAssignedTo(result, who)
    return _edit_all(results, doc, 'Assign clashes', edit)


def set_description(results, text, doc=None):
    """Sets the description of every result. One undo step."""
    return _edit_all(results, doc, 'Describe clashes',
                     lambda data, result: data.TestsEditResultDescription(result, str(text or '')))


def set_priority(results, priority, doc=None):
    """Sets the priority (an int, Navisworks shows 1..5) of every result."""
    value = int(priority)
    return _edit_all(results, doc, 'Prioritise clashes',
                     lambda data, result: data.TestsEditResultPriority(result, value))


def _comment_status(Api, status):
    return getattr(Api.CommentStatus, str(status or 'New').strip().title(), Api.CommentStatus.New)


def _user_name():
    try:
        from namo import config
        name = config.user_name()
        if name:
            return name
    except Exception:
        pass
    import os
    return os.environ.get('USERNAME', '')


def add_comment(result, text, doc=None, author=None, status='New'):
    """Adds one comment to a result (its existing comments plus the new one,
    TestsEditResultComments). author defaults to the Playground user name. One undo
    step. Returns the new comment count."""
    from pynavis._api import Api
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    data = _clash().get_clash(document).TestsData
    comments = Api.CommentCollection(result.Comments)
    status_value = _comment_status(Api, status)
    author = author if author is not None else _user_name()
    try:
        comment = Api.Comment(str(text), status_value, str(author)) if author \
            else Api.Comment(str(text), status_value)
    except Exception:
        comment = Api.Comment(str(text), status_value)
    comments.Add(comment)
    with transaction('Comment on clash', document):
        data.TestsEditResultComments(result, comments)
    return comments.Count


def _inside(item, test):
    """True when item sits somewhere under test (compared by Guid)."""
    target = str(test.Guid)
    node = item.Parent
    while node is not None:
        if str(node.Guid) == target:
            return True
        node = node.Parent
    return False


def resolve_guid(test, guid_text, doc=None):
    """The live ClashResult with that Guid text inside test, or None. Tries the
    document's own Guid index first, then walks the test."""
    ClashApi = _clash_api()
    clash = _clash()
    wanted = str(guid_text or '').strip().lower()
    if not wanted:
        return None
    try:
        from System import Guid
        found = clash.get_clash(_doc(doc)).TestsData.ResolveGuid(Guid(wanted))
        if isinstance(found, ClashApi.ClashResult) and _inside(found, test):
            return found
    except Exception:
        pass
    for result in results(test):
        if str(result.Guid).lower() == wanted:
            return result
    return None

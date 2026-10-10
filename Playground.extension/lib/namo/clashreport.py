# -*- coding: utf-8 -*-
"""Clash reports: the row shaping, summaries and tallies every Clash Reports tool shares.

Data flows one way. The API half reads the chosen tests through namo.clashdata into a
plain `data` dict; every report builder (rep_clash_*.py, rep_per_trade.py) is pure and
turns that dict into a workbook, an HTML page or output-window HTML:

    data = {'title', 'project', 'file', 'doc_title', 'user', 'generated' (datetime),
            'doc_units', 'unit' (report length symbol: mm, cm, m, ft or in),
            'tests': [{'name', 'path', 'type', 'state', 'tolerance_m', 'last_run'
                       (datetime or None), 'rows': [row]}],
            'notes': [sentence], 'live': {test name: [ClashResult]} (API runs only)}

Rows are clashdata.snapshot rows (id, name, status, distance_m, level, grid, item_a_name,
model_a, trade_a, assigned, group, group_guid, created, approved_by, approved_time,
description, comments, key ...) plus cat_a / cat_b (element categories, '' when unread)
and image (a thumbnail path or None). shape_rows() adds what the reports print: dist
(the distance in report units), found / approved (datetimes), age (days since found),
open (New, Active or Reviewed).

Words used everywhere: OPEN is New + Active + Reviewed, CLOSED is Approved + Resolved
(Clash Detective's own sense of "still needs work"). Distances keep Clash Detective's
sign: negative is a penetration.

Pure first (unit tested on both engines); the API half lazy-imports Navisworks.
"""

import os

from namo import dates, naming, units

STATUSES = ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']
OPEN = ['New', 'Active', 'Reviewed']
CLOSED = ['Approved', 'Resolved']
AGE_BUCKETS = (7, 14, 30)
THUMB_W = 160
THUMB_H = 90
IMAGE_CAP = 300                 # thumbnails per test before the tool asks
NO_LEVEL = 'No level'
NO_GRID = 'No grid'
NOT_ASSIGNED = 'Not assigned'
UNASSIGNED = 'Unassigned'
UNKNOWN_AGE = 'Unknown'

UNIT_DECIMALS = {'mm': 1, 'cm': 2, 'm': 3, 'ft': 3, 'in': 2}
UNIT_FORMATS = {'mm': '#,##0.0', 'cm': '#,##0.00', 'm': '#,##0.000', 'ft': '#,##0.000',
                'in': '#,##0.00'}
TEST_TYPES = {'hard': 'Hard', 'hardconservative': 'Hard (conservative)', 'clearance': 'Clearance',
              'duplicate': 'Duplicates', 'custom': 'Custom'}
TEST_STATES = {'new': 'Not run', 'old': 'Out of date', 'partial': 'Partly run',
               'complete': 'Up to date'}


# ---- pure: statuses and units ----------------------------------------------------------------


def status_name(value):
    """'New'.. from any spelling or enum text; other text as given, None as ''."""
    text = str(value if value is not None else '').strip()
    lowered = text.lower()
    for status in STATUSES:
        if status.lower() == lowered:
            return status
    return text


def is_open(status):
    return status_name(status) in OPEN


def ordered_statuses(statuses):
    """The known statuses among `statuses`, in Clash Detective's order (defaults to all)."""
    if not statuses:
        return list(STATUSES)
    wanted = set(status_name(s) for s in statuses)
    return [s for s in STATUSES if s in wanted]


def statuses_text(statuses):
    """'all statuses', 'open clashes (New, Active, Reviewed)' or 'New, Active'."""
    chosen = ordered_statuses(statuses)
    if chosen == STATUSES:
        return 'all statuses'
    if chosen == OPEN:
        return 'open clashes (New, Active, Reviewed)'
    return ', '.join(chosen)


def listed_text(count, statuses):
    """'162 clashes listed (New, Active, Reviewed)' or 'All 220 clashes listed'."""
    chosen = ordered_statuses(statuses)
    noun = plural(count, 'clash', 'clashes')
    if chosen == STATUSES:
        return 'All %s listed' % noun if count != 1 else '1 clash listed'
    return '%s listed (%s)' % (noun, ', '.join(chosen))


def report_unit(report_units=None, doc_units='Meters'):
    """The length symbol reports show distances in: config 'report_units' ('auto' follows the
    document: mm for millimetres, ft for feet...)."""
    try:
        return units.report_units_for(report_units or 'auto', doc_units or 'Meters')['length']
    except Exception:
        return 'm'


def decimals_of(unit):
    return UNIT_DECIMALS.get(unit, 3)


def to_unit(value_m, unit):
    """A length in metres in `unit`, rounded to that unit's decimals; None stays None."""
    if value_m is None:
        return None
    try:
        value = units.from_meters(float(value_m), unit)
    except (TypeError, ValueError):
        return None
    value = round(value, decimals_of(unit))
    return 0.0 if value == 0 else value


def number_text(value, unit):
    """'-42.0', '1,250.5': fixed decimals for the unit, thousands separators."""
    if value is None:
        return ''
    text = ('{:,.%df}' % decimals_of(unit)).format(float(value))
    if text.startswith('-') and float(text[1:].replace(',', '') or 0) == 0:
        text = text[1:]
    return text


def length_text(value_m, unit):
    """'10 mm', '0.025 m', '0.083 ft' (trailing zeros trimmed); '' for None."""
    value = to_unit(value_m, unit)
    if value is None:
        return ''
    text = number_text(value, unit)
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return '%s %s' % (text or '0', unit)


def test_type_label(value):
    text = str(value or '').strip().lower().replace(' ', '').replace('_', '')
    return TEST_TYPES.get(text, str(value or '') or 'Custom')


def test_state_label(value):
    return TEST_STATES.get(str(value or '').strip().lower(), str(value or ''))


# ---- pure: rows --------------------------------------------------------------------------------


def shape_row(row, unit, today=None):
    """A copy of a snapshot row with status normalised and dist, found, approved, age, open
    added (see the module docstring)."""
    out = dict(row)
    out['status'] = status_name(row.get('status'))
    out['open'] = out['status'] in OPEN
    value_m = row.get('distance_m')
    out['dist'] = to_unit(value_m, unit) if value_m is not None else None
    found = dates.parse(row.get('created')) if row.get('created') else None
    out['found'] = found
    out['approved'] = dates.parse(row.get('approved_time')) if row.get('approved_time') else None
    out['age'] = dates.days_between(found, today) if (found is not None and today is not None) else None
    for key in ('cat_a', 'cat_b', 'image'):
        out.setdefault(key, '' if key != 'image' else None)
    return out


def shape_rows(rows, unit, today=None):
    return [shape_row(r, unit, today) for r in rows]


def filter_rows(rows, statuses):
    """Rows whose status is one of `statuses` (all rows when statuses is empty)."""
    if not statuses:
        return list(rows)
    wanted = set(status_name(s) for s in statuses)
    return [r for r in rows if status_name(r.get('status')) in wanted]


def counts(rows):
    """{'total', 'open', 'closed', 'by_status': {status: n for every STATUS}, 'other'}."""
    by_status = dict((s, 0) for s in STATUSES)
    other = 0
    for row in rows:
        status = status_name(row.get('status'))
        if status in by_status:
            by_status[status] += 1
        else:
            other += 1
    open_count = sum(by_status[s] for s in OPEN)
    return {'total': len(rows), 'open': open_count, 'closed': by_status['Approved'] + by_status['Resolved'],
            'by_status': by_status, 'other': other}


def oldest_open(rows):
    """The open row found longest ago (ties: tree order), or None."""
    best = None
    for row in rows:
        if not is_open(row.get('status')) or row.get('age') is None:
            continue
        if best is None or row['age'] > best['age']:
            best = row
    return best


def all_rows(data):
    out = []
    for test in data.get('tests') or []:
        out.extend(test.get('rows') or [])
    return out


def kpis(data):
    """Totals over every test: counts() plus 'oldest' (row or None), 'tests' (count)."""
    rows = all_rows(data)
    out = counts(rows)
    out['oldest'] = oldest_open(rows)
    out['tests'] = len(data.get('tests') or [])
    return out


def _label(value, blank):
    text = str(value if value is not None else '').strip()
    return text or blank


def tally(rows, key, open_only=True, blank='(none)', limit=None):
    """[(label, count)] most first, ties in natural order. key: a row field name or a
    function(row) -> text. Blank values count under `blank`."""
    getter = key if callable(key) else (lambda r: r.get(key))
    found = {}
    for row in rows:
        if open_only and not is_open(row.get('status')):
            continue
        label = _label(getter(row), blank)
        found[label] = found.get(label, 0) + 1
    ranked = sorted(found.items(), key=lambda p: (-p[1], naming.natural_key(p[0])))
    return ranked[:limit] if limit else ranked


def age_tally(rows, buckets=AGE_BUCKETS):
    """[(bucket label, open count)] in bucket order (0-7 days ... Over 30 days), plus
    'Unknown' when some open clashes have no found date."""
    labels = dates.bucket_labels(buckets)
    found = dict((label, 0) for label in labels)
    unknown = 0
    for row in rows:
        if not is_open(row.get('status')):
            continue
        if row.get('age') is None:
            unknown += 1
        else:
            found[dates.age_bucket(row['age'], buckets)] += 1
    out = [(label, found[label]) for label in labels]
    if unknown:
        out.append((UNKNOWN_AGE, unknown))
    return out


def axis_of(row, axis, side):
    """The trade or model of one side ('a' or 'b') of a clash; blanks read as Unassigned
    (trades) or '(no model)'."""
    if axis == 'model':
        return _label(row.get('model_' + side), '(no model)')
    return _label(row.get('trade_' + side), UNASSIGNED)


def pair_tally(rows, axis='trade', open_only=True, limit=None):
    """[(a, b, open, new)] for unordered pairs (a <= b naturally), most open first."""
    found = {}
    for row in rows:
        status = status_name(row.get('status'))
        if open_only and status not in OPEN:
            continue
        pair = tuple(sorted([axis_of(row, axis, 'a'), axis_of(row, axis, 'b')], key=naming.natural_key))
        entry = found.setdefault(pair, [0, 0])
        if status in OPEN:
            entry[0] += 1
        if status == 'New':
            entry[1] += 1
    ranked = sorted(found.items(), key=lambda p: (-p[1][0], -p[1][1], naming.natural_key(p[0][0]),
                                                  naming.natural_key(p[0][1])))
    out = [(pair[0], pair[1], value[0], value[1]) for pair, value in ranked]
    return out[:limit] if limit else out


def matrix(rows, axis='trade', statuses=None, order=None, labels=None):
    """Unordered pair counts as a square grid.

    Returns {'labels': [...], 'grid': [[n or None]], 'involving': [n], 'total': n}: cell
    [i][j] (i <= j) counts the clashes between labels i and j among rows whose status is
    in `statuses` (default OPEN); cells below the diagonal are None. 'involving' counts
    each clash once for every label it touches (a same-label clash once). Labels follow
    `order` (e.g. the configured trades) for those present, then the rest naturally;
    `labels` forces the label list (to draw a second matrix on the first one's axes)."""
    wanted = set(ordered_statuses(statuses or OPEN))
    pairs = {}
    present = set()
    total = 0
    for row in rows:
        if status_name(row.get('status')) not in wanted:
            continue
        a = axis_of(row, axis, 'a')
        b = axis_of(row, axis, 'b')
        present.add(a)
        present.add(b)
        pairs[(a, b)] = pairs.get((a, b), 0) + 1
        total += 1
    lowered = [str(o).lower() for o in (order or [])]

    def rank(label):
        low = label.lower()
        return (0, lowered.index(low), '') if low in lowered else (1, 0, naming.natural_key(label))
    if labels is None:
        labels = sorted(present, key=rank)
    else:
        labels = list(labels) + sorted([p for p in present if p not in labels], key=rank)
    index = dict((label, i) for i, label in enumerate(labels))
    size = len(labels)
    grid = [[(0 if c >= r else None) for c in range(size)] for r in range(size)]
    involving = [0] * size
    for (a, b), n in pairs.items():
        i, j = sorted((index[a], index[b]))
        grid[i][j] += n
        involving[i] += n
        if j != i:
            involving[j] += n
    return {'labels': labels, 'grid': grid, 'involving': involving, 'total': total}


def oriented_matrix(rows, axis='model', statuses=None, order=None):
    """Counts as tested: rows are side A labels, columns side B labels (a model can be on
    both sides across tests). {'rows', 'cols', 'grid' [[n or None]], 'total'}; a cell
    with no clashes is None. Labels follow `order` first, then natural order."""
    wanted = set(ordered_statuses(statuses or OPEN))
    cells = {}
    side_a = set()
    side_b = set()
    total = 0
    for row in rows:
        if status_name(row.get('status')) not in wanted:
            continue
        a = axis_of(row, axis, 'a')
        b = axis_of(row, axis, 'b')
        side_a.add(a)
        side_b.add(b)
        cells[(a, b)] = cells.get((a, b), 0) + 1
        total += 1
    lowered = [str(o).lower() for o in (order or [])]

    def rank(label):
        low = label.lower()
        return (0, lowered.index(low), '') if low in lowered else (1, 0, naming.natural_key(label))
    row_labels = sorted(side_a, key=rank)
    col_labels = sorted(side_b, key=rank)
    grid = [[cells.get((a, b)) for b in col_labels] for a in row_labels]
    return {'rows': row_labels, 'cols': col_labels, 'grid': grid, 'total': total}


def heat_step(value, peak, steps=6):
    """0 for nothing, else 1..steps by share of the peak (for fills)."""
    if not value or not peak or value <= 0:
        return 0
    step = int(-(-float(value) * steps // float(peak)))       # ceil without math
    return max(1, min(steps, step))


def dominant(values):
    """The most common non-empty value (ties: natural order), or ''."""
    found = {}
    for value in values:
        text = str(value if value is not None else '').strip()
        if text:
            found[text] = found.get(text, 0) + 1
    if not found:
        return ''
    return sorted(found.items(), key=lambda p: (-p[1], naming.natural_key(p[0])))[0][0]


def groups_view(rows):
    """Result groups as they stand in the rows (innermost group of each clash):
    [{'test', 'group', 'count', 'open', 'by_status', 'assigned', 'level', 'grid',
    'worst' (smallest dist: deepest or tightest), 'oldest' (largest open age)}], test order then natural
    group order. Ungrouped clashes are left out."""
    found = {}
    order = []
    for row in rows:
        if not row.get('group'):
            continue
        key = (row.get('test') or '', row.get('group_guid') or row.get('group'))
        if key not in found:
            found[key] = {'test': row.get('test') or '', 'group': row.get('group'), 'rows': []}
            order.append(key)
        found[key]['rows'].append(row)
    tests_order = []
    for key in order:
        if key[0] not in tests_order:
            tests_order.append(key[0])
    out = []
    for key in order:
        entry = found[key]
        members = entry.pop('rows')
        tally_ = counts(members)
        dists = [r['dist'] for r in members if r.get('dist') is not None]
        ages = [r['age'] for r in members if r.get('age') is not None and is_open(r.get('status'))]
        entry.update({'count': len(members), 'open': tally_['open'], 'by_status': tally_['by_status'],
                      'assigned': dominant(r.get('assigned') for r in members),
                      'level': dominant(r.get('level') for r in members),
                      'grid': dominant(r.get('grid') for r in members),
                      'worst': min(dists) if dists else None,
                      'oldest': max(ages) if ages else None})
        out.append(entry)
    out.sort(key=lambda e: (tests_order.index(e['test']), naming.natural_key(e['group'] or '')))
    return out


def status_mix_text(by_status):
    """'12 New, 3 Active' for the non-zero statuses, Clash Detective order."""
    return ', '.join('%s %s' % ('{:,}'.format(by_status[s]), s) for s in STATUSES if by_status.get(s))


def test_line(test, unit):
    """'Hard, tolerance 10 mm, last run 2026-10-05 14:30 (up to date)'."""
    parts = [test.get('type') or 'Custom']
    if test.get('tolerance_m') is not None:
        parts.append('tolerance %s' % length_text(test['tolerance_m'], unit))
    if test.get('last_run') is not None:
        when = 'last run %s' % test['last_run'].strftime('%Y-%m-%d %H:%M')
        state = test.get('state')
        parts.append('%s (%s)' % (when, state.lower()) if state else when)
    elif test.get('state'):
        parts.append(test['state'].lower())
    return ', '.join(parts)


def counts_line(tally_):
    """'1,240 clashes: 120 New, 300 Active, ...' (or 'No clashes')."""
    if not tally_['total']:
        return 'No clashes'
    mix = status_mix_text(tally_['by_status'])
    noun = 'clash' if tally_['total'] == 1 else 'clashes'
    return '%s %s: %s' % ('{:,}'.format(tally_['total']), noun, mix) if mix else \
        '%s %s' % ('{:,}'.format(tally_['total']), noun)


def plural(n, word, words=None):
    n = int(n)
    return '{:,} {}'.format(n, word if n == 1 else (words or word + 's'))


def image_counts(listed_by_test, cap):
    """{test: thumbnails} for listed counts {test: n} under a per-test cap (None = no cap)."""
    out = {}
    for name in listed_by_test:
        n = int(listed_by_test[name] or 0)
        out[name] = n if not cap else min(n, int(cap))
    return out


def over_cap(listed_by_test, cap):
    """True when some test lists more clashes than the thumbnail cap."""
    return bool(cap) and any(int(n or 0) > int(cap) for n in listed_by_test.values())


def tests_text(names):
    """'Every test with results', 'Ducts vs Beams' or '3 tests' (starts a sentence)."""
    names = [n for n in (names or []) if n]
    if not names:
        return 'Every test with results'
    if len(names) == 1:
        return names[0]
    return plural(len(names), 'test')


def file_values(stem):
    """naming values for report file names: {file} falls back to 'Untitled' for an unsaved
    model so names never start with a separator."""
    return {'file': stem or 'Untitled'}


def subset(data, rows_filter):
    """A shallow copy of data whose tests keep only rows for which rows_filter(row) is
    True (tests left empty are kept, so summaries still show them)."""
    out = dict(data)
    out['tests'] = []
    for test in data.get('tests') or []:
        copy = dict(test)
        copy['rows'] = [r for r in test.get('rows') or [] if rows_filter(r)]
        out['tests'].append(copy)
    out['notes'] = list(data.get('notes') or [])
    return out


def report_values(data):
    """Tokens for output names: {'file': ...} with the Untitled fallback."""
    return file_values(data.get('file'))


class Stage(object):
    """Maps a progress(fraction, label) callback onto a slice [start, start + span) of it.
    Calls go through only `if progress`; a False answer raises namo.items.Cancelled."""

    def __init__(self, progress, start=0.0, span=1.0):
        self.progress = progress
        self.start = float(start)
        self.span = float(span)

    def __call__(self, fraction, label=''):
        if self.progress is None:
            return True
        value = self.start + self.span * max(0.0, min(1.0, float(fraction or 0.0)))
        if self.progress(value, label) == False:  # noqa: E712  (only an explicit False stops)
            from namo.items import Cancelled
            raise Cancelled()
        return True

    def sub(self, start, span):
        return Stage(self.progress, self.start + self.span * start, self.span * span)


# ==== API half (Navisworks only; lazy imports) ===================================================


def active_doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def doc_units(doc=None):
    try:
        return str(active_doc(doc).Units)
    except Exception:
        return 'Meters'


def file_info(doc=None):
    """(full path or '', file stem or '', title or '') of the document."""
    document = active_doc(doc)
    path = ''
    title = ''
    try:
        path = document.FileName or ''
    except Exception:
        path = ''
    try:
        title = document.Title or ''
    except Exception:
        title = ''
    stem = os.path.splitext(os.path.basename(path))[0] if path else ''
    return path, stem, title


def doc_folder(doc=None):
    """The document's folder when it is saved, else Documents."""
    path, _stem, _title = file_info(doc)
    if path and os.path.isdir(os.path.dirname(path)):
        return os.path.dirname(path)
    documents = os.path.join(os.path.expanduser('~'), 'Documents')
    return documents if os.path.isdir(documents) else os.path.expanduser('~')


def default_path(template, ext, doc=None, folder=None):
    """A full path in the document's folder (or `folder`) from a naming template."""
    _path, stem, _title = file_info(doc)
    values = naming.standard_values(doc)
    values.update(file_values(stem))
    text, _missing = naming.render(template, values)
    name = naming.sanitize(text, for_file=True) or 'Clash report'
    if not ext.startswith('.'):
        ext = '.' + ext
    if not name.lower().endswith(ext.lower()):
        name += ext
    return os.path.join(folder or doc_folder(doc), name)


def context(doc=None, report_units=None):
    """The data dict without tests: title, project, file, user, units, generated."""
    import datetime
    from namo import config
    document = active_doc(doc)
    _path, stem, title = file_info(document)
    try:
        cfg = config.load()
    except Exception:
        cfg = {}
    try:
        user = config.user_name()
    except Exception:
        user = ''
    d_units = doc_units(document)
    chosen = report_units if report_units else cfg.get('report_units', 'auto')
    return {'title': 'Clash report', 'project': cfg.get('project_name') or '',
            'project_number': cfg.get('project_number') or '', 'company': cfg.get('company') or '',
            'file': stem, 'doc_title': title or stem, 'user': user,
            'generated': datetime.datetime.now().replace(microsecond=0),
            'doc_units': d_units, 'unit': report_unit(chosen, d_units),
            'trades_order': list(cfg.get('trades') or []), 'tests': [], 'notes': [], 'live': {}}


def tests_with_results(doc=None):
    """Every test that holds at least one result, tree order."""
    from namo import clashdata
    out = []
    for test in clashdata.tests(active_doc(doc)):
        try:
            if total_count(test) > 0:
                out.append(test)
        except Exception:
            out.append(test)
    return out


def resolve_tests(names, doc=None):
    """(tests, missing names): tests named in `names` (names, or 'Folder/Test' paths), or
    every test with results when names is empty. Duplicates are dropped."""
    from namo import clashdata
    document = active_doc(doc)
    if not names:
        return tests_with_results(document), []
    found = []
    seen = set()
    missing = []
    for name in names:
        test = clashdata.test_by_name(name, document)
        if test is None:
            missing.append(name)
            continue
        guid = str(test.Guid)
        if guid not in seen:
            seen.add(guid)
            found.append(test)
    return found, missing


def status_counts(test):
    """{status: n} for a test. Clash Detective's own counter
    (Interop.LcOclClashUtils.CountByStatus(group, status, recurse=True); the 2026 API has
    both a two- and a three-argument overload, and only recurse=True reaches the results
    inside result groups) answers without walking the results; when it is unavailable the
    results are walked. UNVERIFIED in-app: the recurse flag's exact meaning; a zero total
    for a test that has children is re-counted by walking, so a fully grouped test is
    never taken for an empty one."""
    out = dict((s, 0) for s in STATUSES)
    try:
        from namo import clashdata
        clashdata._clash_api()
        import Autodesk.Navisworks.Api.Clash as ClashApi
        from Autodesk.Navisworks.Api.Interop import LcOclClashUtils
        for status in STATUSES:
            out[status] = int(LcOclClashUtils.CountByStatus(
                test, getattr(ClashApi.ClashResultStatus, status), True))
        if sum(out.values()) or not _has_children(test):
            return out
        out = dict((s, 0) for s in STATUSES)
    except Exception:
        out = dict((s, 0) for s in STATUSES)
    from namo import clashdata
    for result in clashdata.results(test):
        name = status_name(str(result.Status))
        if name in out:
            out[name] += 1
    return out


def _has_children(test):
    try:
        return int(test.Children.Count) > 0
    except Exception:
        try:
            return len(list(test.Children)) > 0
        except Exception:
            return True


def total_count(test):
    return sum(status_counts(test).values())


def _when(value):
    """datetime from a .NET Nullable<DateTime> (None when unset)."""
    if value is None:
        return None
    try:
        return dates.from_net(value)
    except Exception:
        return None


def test_info(test, doc=None):
    """{'name', 'path', 'type', 'state', 'tolerance_m', 'last_run'} of a live test; every
    field is best effort (None or '' when the API does not answer)."""
    from namo import clashdata
    info = {'name': test.DisplayName, 'path': clashdata.test_path(test), 'type': 'Custom',
            'state': '', 'tolerance_m': None, 'last_run': None, 'guid': str(test.Guid)}
    try:
        info['type'] = test_type_label(str(test.TestType))
    except Exception:
        pass
    try:
        info['state'] = test_state_label(str(test.Status))
    except Exception:
        pass
    try:
        u2m = clashdata._clash().units_to_meters(active_doc(doc))
        info['tolerance_m'] = float(test.Tolerance) * u2m
    except Exception:
        pass
    try:
        info['last_run'] = _when(test.LastRun)
    except Exception:
        pass
    return info


def _element(result, side):
    composite = result.CompositeItem1 if side == 'a' else result.CompositeItem2
    if composite is not None:
        return composite
    return result.Item1 if side == 'a' else result.Item2


def collect(tests, doc=None, progress=None, categories=True, report_units=None):
    """Reads tests into the data dict (module docstring). progress(fraction, label) spans
    the read; returning False raises namo.items.Cancelled. Raises RuntimeError (with a
    sentence) when a test changed while it was read."""
    from namo import clashdata, items
    document = active_doc(doc)
    data = context(document, report_units)
    today = dates.today()
    stage = Stage(progress)
    names = clashdata.unique_names([t.DisplayName for t in tests])
    count = len(tests) or 1
    memo = {}
    for index, test in enumerate(tests):
        slice_ = stage.sub(float(index) / count, 1.0 / count)
        info = test_info(test, document)
        info['name'] = names[index]
        rows = clashdata.snapshot(test, document, slice_.sub(0.0, 0.8))
        live = clashdata.results(test)
        if len(live) != len(rows):
            raise RuntimeError('The clash results of %s changed while they were read; run it again.'
                               % info['name'])
        if categories and rows:
            step = max(1, len(rows) // 40)
            for position, row in enumerate(rows):
                result = live[row['id']]
                for side in ('a', 'b'):
                    key = row.get('item_' + side) or ('%s:%s:%s' % (index, side, row['id']))
                    if key not in memo:
                        try:
                            element = _element(result, side)
                            memo[key] = items.category(element) if element is not None else ''
                        except Exception:
                            memo[key] = ''
                    row['cat_' + side] = memo[key]
                if position % step == 0:
                    slice_(0.8 + 0.2 * position / float(len(rows)), 'Reading categories in %s' % info['name'])
        for row in rows:
            row['test'] = info['name']
        info['rows'] = shape_rows(rows, data['unit'], today)
        data['tests'].append(info)
        data['live'][info['name']] = live
    stage(1.0, 'Read %s' % plural(len(tests), 'test'))
    return data


def thumbnails(data, rows_by_test, folder, doc=None, progress=None, quality=80):
    """Writes a THUMB_W x THUMB_H JPEG for each row in rows_by_test {test name: [rows]}
    (rows of `data`, live results from data['live']) into folder and sets row['image'].
    A failed image leaves row['image'] None; after three failures in a row with no success
    yet, the rest are skipped (Navisworks cannot render clash images here). The camera is
    put back afterwards. Returns {'made', 'failed', 'skipped'}."""
    from namo import clashdata, images
    document = active_doc(doc)
    stage = Stage(progress)
    total = sum(len(rows_by_test[name]) for name in rows_by_test) or 1
    done = 0
    made = failed = skipped = 0
    streak = 0
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with images.ViewKeeper(document):
        for t_index, test in enumerate(data.get('tests') or []):
            wanted = rows_by_test.get(test['name']) or []
            live = (data.get('live') or {}).get(test['name']) or []
            for row in wanted:
                done += 1
                if made == 0 and streak >= 3:
                    skipped += 1
                    continue
                path = os.path.join(folder, 't%d-%d.jpg' % (t_index, int(row['id'])))
                try:
                    clashdata.image(live[row['id']], path, THUMB_W, THUMB_H, document, 'scene', quality)
                    row['image'] = path
                    made += 1
                    streak = 0
                except Exception:
                    row['image'] = None
                    failed += 1
                    streak += 1
                if done % 5 == 0 or done == total:
                    stage(float(done) / total, 'Clash images: %s of %s' % ('{:,}'.format(done),
                                                                          '{:,}'.format(total)))
    return {'made': made, 'failed': failed, 'skipped': skipped}


def thumbnail_plan(data, statuses, cap):
    """{test name: [rows to picture]}: the first `cap` listed rows of each test (all when
    cap is None or 0)."""
    out = {}
    for test in data.get('tests') or []:
        listed = filter_rows(test.get('rows') or [], statuses)
        out[test['name']] = listed[:int(cap)] if cap else listed
    return out


def image_note(stats, planned, cap, capped):
    """A sentence about thumbnails for the report notes, or ''."""
    parts = []
    if capped and cap:
        parts.append('Thumbnails show the first %s listed clashes of each test.' % '{:,}'.format(int(cap)))
    if stats.get('failed') or stats.get('skipped'):
        missing = stats.get('failed', 0) + stats.get('skipped', 0)
        parts.append('%s of %s could not be made (Navisworks returned no image).' % (
            '{:,}'.format(missing), plural(planned, 'thumbnail')))
    return ' '.join(parts)


def temp_folder(prefix='playground-clash-'):
    import tempfile
    return tempfile.mkdtemp(prefix=prefix)


def remove_folder(folder):
    import shutil
    if folder and os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)


def history_place(doc_path, doc=None):
    """Where clash snapshots of this model are kept, as a sentence for a toast."""
    try:
        from namo import clashdata, store
        held = store.Store(clashdata.HISTORY_INDEX, doc_path=doc_path, scope='doc', doc=doc)
        if held.note:
            return held.note
        return {'local': 'Kept on this computer.', 'shared': 'Kept in the team folder.',
                'model': 'Kept in the model; save the model to keep it.'}.get(held.mode, '')
    except Exception:
        return ''


def record_snapshot(tests, label=None, doc=None, progress=None):
    """Reads tests and keeps them as one clash history snapshot of the saved model.
    Returns (index entry, where sentence). Raises ValueError for an unsaved model."""
    from namo import clashdata
    document = active_doc(doc)
    doc_path, _stem, _title = file_info(document)
    if not doc_path:
        raise ValueError('Save the model first: clash snapshots are kept per model file.')
    stage = Stage(progress)
    rows_by_test = clashdata.snapshot_all(tests, document, stage.sub(0.0, 0.9))
    stage(0.95, 'Saving the snapshot')
    entry = clashdata.save_history(doc_path, rows_by_test, (label or '').strip() or None)
    stage(1.0, 'Saved')
    return entry, history_place(doc_path, document)

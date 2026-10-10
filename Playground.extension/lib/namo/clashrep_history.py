# -*- coding: utf-8 -*-
"""Clash history maths for Clash Delta, Clash Trends and the automatic snapshot: which
snapshot to compare with, what changed since, and the series over time. Pure.

History comes from namo.clashdata: list_history(doc_path) gives index entries
{'id', 'label', 'time' ISO, 'counts': {test: {'total', 'by_status'}}} oldest first, and
load_history(doc_path, id) gives {test: [rows]} with clashdata.HISTORY_FIELDS keys
(key, test, status, distance_m, created, trade_a, trade_b, name, grid, level). Matching
is clashdata.compare (element pair plus clash centre in 0.1 m cells).

Words: open = New, Active or Reviewed; closed (shown as "resolved" in trends) = Approved
or Resolved. A delta's "fixed" is an open clash of the snapshot that is now gone or
closed; "new" is an open clash with no match in the snapshot.
"""

import datetime

from namo import clashreport as cr
from namo import dates

NOW_LABEL = 'Now'


# ---- snapshots ----------------------------------------------------------------------------------


def entry_time(entry):
    """The snapshot's datetime, or None."""
    return dates.parse((entry or {}).get('time')) if (entry or {}).get('time') else None


def open_closed(counts):
    """(open, closed, total) from clashdata.counts() output {'total', 'by_status'}."""
    by_status = {}
    for status, n in ((counts or {}).get('by_status') or {}).items():
        name = cr.status_name(status)
        by_status[name] = by_status.get(name, 0) + int(n or 0)
    open_n = sum(by_status.get(s, 0) for s in cr.OPEN)
    closed_n = sum(by_status.get(s, 0) for s in cr.CLOSED)
    total = int((counts or {}).get('total') or (open_n + closed_n))
    return open_n, closed_n, total


def entry_totals(entry, tests=None):
    """{'tests': n present, 'open', 'closed', 'total'} of a snapshot over `tests` (all its
    tests when None)."""
    counts = (entry or {}).get('counts') or {}
    names = sorted(counts) if not tests else [t for t in tests if t in counts]
    out = {'tests': len(names), 'open': 0, 'closed': 0, 'total': 0}
    for name in names:
        o, c, t = open_closed(counts[name])
        out['open'] += o
        out['closed'] += c
        out['total'] += t
    return out


def entry_text(entry, tests=None):
    """'Before the meeting, 2026-10-04 17:30: 3 tests, 1,240 clashes, 842 open'."""
    when = entry_time(entry)
    stamp = when.strftime('%Y-%m-%d %H:%M') if when else ''
    label = (entry.get('label') or '').strip()
    totals = entry_totals(entry, tests)
    head = stamp if (not label or label.replace('T', ' ')[:16] == stamp) else '%s, %s' % (label, stamp)
    return '%s: %s, %s, %s open' % (head, cr.plural(totals['tests'], 'test'),
                                    cr.plural(totals['total'], 'clash', 'clashes'), '{:,}'.format(totals['open']))


def snapshot_message(entry, where=''):
    """(message, detail) for the toast after a snapshot: 'Snapshot saved: 3 tests, 1,240
    clashes', '842 open. Kept on this computer. Clash Delta and ...'."""
    totals = entry_totals(entry)
    message = 'Snapshot saved: %s, %s' % (cr.plural(totals['tests'], 'test'),
                                          cr.plural(totals['total'], 'clash', 'clashes'))
    parts = ['%s open.' % '{:,}'.format(totals['open'])]
    if where:
        parts.append(where)
    parts.append('Clash Delta and Clash Trends can compare with it.')
    return message, ' '.join(parts)


def pick_baseline(entries, today=None):
    """The snapshot to compare with by default: the latest taken before today, else the
    latest. None when there are none."""
    entries = sorted([e for e in entries or [] if e.get('id')], key=lambda e: (e.get('time') or '', e['id']))
    if not entries:
        return None
    start = (today or dates.today()).replace(hour=0, minute=0, second=0, microsecond=0)
    before = [e for e in entries if entry_time(e) is not None and entry_time(e) < start]
    return before[-1] if before else entries[-1]


def find_entry(entries, ref, today=None):
    """A snapshot by reference: '' / 'auto' (pick_baseline), 'latest', 'previous' (the one
    before the latest), an id, or a label (case-insensitive, latest such). None when
    nothing matches."""
    entries = sorted([e for e in entries or [] if e.get('id')], key=lambda e: (e.get('time') or '', e['id']))
    text = str(ref or '').strip()
    if not entries:
        return None
    if text.lower() in ('', 'auto'):
        return pick_baseline(entries, today)
    if text.lower() == 'latest':
        return entries[-1]
    if text.lower() == 'previous':
        return entries[-2] if len(entries) > 1 else None
    for entry in entries:
        if entry['id'] == text:
            return entry
    matches = [e for e in entries if (e.get('label') or '').strip().lower() == text.lower()]
    return matches[-1] if matches else None


def age_text(then, now):
    """'today', '1 day ago', '12 days ago'."""
    if then is None or now is None:
        return ''
    days = dates.days_between(then, now)
    if days is None or days <= 0:
        return 'today'
    return '1 day ago' if days == 1 else '%s days ago' % '{:,}'.format(days)


# ---- delta --------------------------------------------------------------------------------------


def _count_open(rows):
    return sum(1 for r in rows if cr.is_open(r.get('status')))


def test_delta(name, old_rows, new_rows):
    """What changed in one test. old_rows None means the snapshot does not hold the test:
    then only now_open is filled (none of its clashes is called new).
    {'test', 'baseline' bool, 'then_open', 'now_open', 'new' [rows], 'fixed' [(old row, how)],
    'persisting' [rows], 'changed' [(old, new)], 'closed_new' [rows], 'net'}; how is
    'Resolved' / 'Approved' (closed in Clash Detective) or 'Gone' (no longer found)."""
    from namo import clashdata
    new_rows = list(new_rows or [])
    out = {'test': name, 'baseline': old_rows is not None, 'now_open': _count_open(new_rows),
           'then_open': None, 'new': [], 'fixed': [], 'persisting': [], 'changed': [], 'closed_new': [],
           'net': None}
    if old_rows is None:
        return out          # nothing to compare with: its open clashes are counted, not called new
    old_rows = list(old_rows)
    result = clashdata.compare(old_rows, new_rows)
    closed_by = {}
    for old, new in result['status_changed']:
        if cr.is_open(old.get('status')) and not cr.is_open(new.get('status')):
            closed_by[id(old)] = cr.status_name(new.get('status'))
    out['then_open'] = _count_open(old_rows)
    out['new'] = result['new']
    out['fixed'] = [(row, closed_by.get(id(row), 'Gone')) for row in result['fixed']]
    out['persisting'] = result['persisting']
    out['changed'] = result['status_changed']
    out['closed_new'] = result['closed_new']
    out['net'] = out['now_open'] - out['then_open']
    return out


def delta(old_by_test, new_by_test, names=None):
    """{'tests': [test_delta...] in `names` order (default: the current tests, sorted
    naturally), 'totals': {'then_open', 'now_open', 'new', 'fixed', 'persisting',
    'changed', 'net'} over tests the snapshot holds, 'without_baseline': [names],
    'dropped': [tests the snapshot holds that are not in this model now; only when names
    is None]}."""
    from namo import naming
    old_by_test = old_by_test or {}
    order = list(names) if names else sorted(new_by_test, key=naming.natural_key)
    tests = [test_delta(name, old_by_test.get(name), new_by_test.get(name) or []) for name in order]
    totals = {'then_open': 0, 'now_open': 0, 'new': 0, 'fixed': 0, 'persisting': 0, 'changed': 0, 'net': 0}
    for t in tests:
        if not t['baseline']:
            continue
        totals['then_open'] += t['then_open']
        totals['now_open'] += t['now_open']
        totals['new'] += len(t['new'])
        totals['fixed'] += len(t['fixed'])
        totals['persisting'] += len(t['persisting'])
        totals['changed'] += len(t['changed'])
        totals['net'] += t['net']
    dropped = sorted([n for n in old_by_test if n not in order], key=naming.natural_key) if not names else []
    return {'tests': tests, 'totals': totals,
            'without_baseline': [t['test'] for t in tests if not t['baseline']], 'dropped': dropped}


def delta_headline(d):
    """'42 new, 118 fixed, 724 still open': the toast line."""
    t = d['totals']
    return '%s new, %s fixed, %s still open' % ('{:,}'.format(t['new']), '{:,}'.format(t['fixed']),
                                                 '{:,}'.format(t['persisting']))


# ---- trends -------------------------------------------------------------------------------------


def trend_points(entries, tests=None, current=None):
    """Points oldest first, one per snapshot (and `current` last when given:
    {'counts': {test: counts}, 'time': datetime}). Each point: {'id', 'label', 'time',
    'open', 'closed', 'total', 'present', 'expected', 'partial', 'per_test': {test: open or
    None}}. tests None = every test any snapshot holds."""
    entries = sorted([e for e in entries or [] if e.get('id')], key=lambda e: (e.get('time') or '', e['id']))
    names = list(tests or [])
    if not names:
        seen = set()
        for entry in entries:
            seen.update((entry.get('counts') or {}).keys())
        if current:
            seen.update((current.get('counts') or {}).keys())
        from namo import naming
        names = sorted(seen, key=naming.natural_key)
    sources = [(e.get('id'), e.get('label') or '', entry_time(e), e.get('counts') or {}) for e in entries]
    if current is not None:
        sources.append((None, NOW_LABEL, current.get('time'), current.get('counts') or {}))
    points = []
    for point_id, label, when, counts in sources:
        point = {'id': point_id, 'label': label, 'time': when, 'open': 0, 'closed': 0, 'total': 0,
                 'present': 0, 'expected': len(names), 'per_test': {}}
        for name in names:
            if name not in counts:
                point['per_test'][name] = None
                continue
            o, c, t = open_closed(counts[name])
            point['per_test'][name] = o
            point['open'] += o
            point['closed'] += c
            point['total'] += t
            point['present'] += 1
        point['partial'] = point['present'] < point['expected']
        points.append(point)
    return points, names


def flows(rows_per_point, names):
    """[(new, fixed) or None] per point: what changed since the previous point, from the
    rows of each point ({test: rows} or None when not loaded). The first point and any
    point next to an unloaded one get None. Only tests both points hold are compared."""
    from namo import clashdata
    out = []
    for index, rows in enumerate(rows_per_point):
        previous = rows_per_point[index - 1] if index else None
        if rows is None or previous is None:
            out.append(None)
            continue
        new_n = fixed_n = 0
        for name in names:
            if name in rows and name in previous:
                result = clashdata.compare(previous[name], rows[name])
                new_n += len(result['new'])
                fixed_n += len(result['fixed'])
        out.append((new_n, fixed_n))
    return out


def point_labels(points):
    """Axis labels: '2026-10-04', with the time added when one day holds several points;
    the live point reads 'Now'."""
    days = {}
    for p in points:
        if p['time'] is not None and p['id'] is not None:
            key = p['time'].strftime('%Y-%m-%d')
            days[key] = days.get(key, 0) + 1
    out = []
    for p in points:
        if p['id'] is None:
            out.append(NOW_LABEL)
        elif p['time'] is None:
            out.append(p['label'] or '?')
        else:
            day = p['time'].strftime('%Y-%m-%d')
            out.append(day if days.get(day, 0) < 2 else p['time'].strftime('%Y-%m-%d %H:%M'))
    return out


def thin(labels, keep=8):
    """Labels with all but about `keep` evenly spaced ones blanked (first and last kept),
    so a crowded axis stays readable."""
    n = len(labels)
    if n <= keep:
        return list(labels)
    step = int(-(-n // keep))
    return [label if (i % step == 0 or i == n - 1) else '' for i, label in enumerate(labels)]


def own_label(label, when):
    """A snapshot's label unless it is just its own timestamp (the default), else ''."""
    text = (label or '').strip()
    if when is not None and text.replace('T', ' ')[:16] == when.strftime('%Y-%m-%d %H:%M'):
        return ''
    return text


def burndown_rows(points, labels, flow):
    """Table rows: [when, label, tests, open, resolved, total, new, fixed, net change]
    (None where unknown). net change = open now minus open at the previous point."""
    rows = []
    previous_open = None
    for p, label, f in zip(points, labels, flow):
        tests = '{:,}'.format(p['present']) if not p['partial'] else '%s of %s' % (
            '{:,}'.format(p['present']), '{:,}'.format(p['expected']))
        rows.append([label, own_label(p['label'], p['time']) if p['id'] is not None else 'Current state', tests,
                     p['open'], p['closed'],
                     p['total'], f[0] if f else None, f[1] if f else None,
                     (p['open'] - previous_open) if previous_open is not None else None])
        previous_open = p['open']
    return rows


def trend_summary(points):
    """'Open went from 842 to 610 over 12 snapshots (down 232).' or ''."""
    if len(points) < 2:
        return ''
    first, last = points[0], points[-1]
    change = last['open'] - first['open']
    way = 'down' if change < 0 else ('up' if change > 0 else 'unchanged')
    tail = ' (%s %s)' % (way, '{:,}'.format(abs(change))) if change else ' (unchanged)'
    return 'Open clashes went from %s to %s over %s%s.' % ('{:,}'.format(first['open']), '{:,}'.format(last['open']),
                                                            cr.plural(len(points), 'point'), tail)


def due_for_auto(entries, now, min_hours):
    """True when the newest snapshot is at least min_hours old (or there is none)."""
    times = [entry_time(e) for e in entries or []]
    times = [t for t in times if t is not None]
    if not times:
        return True
    return (now - max(times)) >= datetime.timedelta(hours=max(0.0, float(min_hours or 0)))

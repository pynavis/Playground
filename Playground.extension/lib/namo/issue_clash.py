# -*- coding: utf-8 -*-
"""Clash results to issues (Clash to Issues) and to BCF topics (BCF Export).

The unit of work is a TOP-LEVEL item of a clash test: each result group, and each clash
that is not in a group (the same units Clash Assigner works on). A unit is converted
when any of its clashes has one of the chosen statuses, and only once: the issue keeps
source {'kind': 'clash', 'ref': '<test guid>|<unit guid>'} and later runs skip refs that
already have an issue.

Fields by rule (configurable in Clash to Issues' Shift+Click options, except who moves):
  * trade: AssignedTo when it names a configured trade; otherwise the trade that MOVES
    of the unit's most common trade pair (namo.trades of the two models; the trade lower
    in the "who moves" list moves, a trade not listed moves first, unassigned models
    cannot be decided and leave the trade blank). The "who moves" list is Clash
    Assigner's (who_moves(): namo.clashassign.saved_settings), so both tools agree.
    AssignedTo that is a person becomes the assignee.
  * priority: from the deepest penetration in the unit (distance bands in metres:
    0.20 m and deeper Critical, 0.05 m High, 0.01 m Normal, else Low; clearance clashes
    are Low).
  * due: today + days for that priority (Critical 3, High 7, Normal 14, Low 28).
  * title: the Clash template's pattern ('{clash}: {a} vs {b}' by default; tokens
    {clash} {test} {a} {b} plus the usual ones).
  * camera: the unit's own clash viewpoint (TestsViewpointForResult); snapshot: its
    clash image (TestsImageForResult); elements: both sides (a group's up to 50).
  * location: the centre of the deepest clash, with its grid and level.

Pure half first (unit tested), then the API half.
"""

import datetime

DEFAULT_MOVE_ORDER = ['Structure', 'Architecture', 'Mechanical', 'Plumbing', 'Electrical',
                      'Fire Protection']
DEFAULT_BANDS = [[0.20, 'Critical'], [0.05, 'High'], [0.01, 'Normal']]
DEFAULT_DUE = {'Critical': 3, 'High': 7, 'Normal': 14, 'Low': 28}
OPEN_CLASH = ['New', 'Active', 'Reviewed']
UNASSIGNED = 'Unassigned'
GROUP_ELEMENT_LIMIT = 50

DEFAULTS = {'tests': [], 'statuses': list(OPEN_CLASH), 'who_moves': list(DEFAULT_MOVE_ORDER),
            'bands': [list(b) for b in DEFAULT_BANDS], 'due_days': dict(DEFAULT_DUE),
            'template': 'Clash', 'snapshots': True, 'max_snapshots': 300}


def _text(value):
    return '' if value is None else (u'%s' % (value,)).strip()


# ---- pure: rules ------------------------------------------------------------------------


def move_order(text_or_list):
    """A clean who-moves list from a list or text (one per line, or '>' / ',' separated)."""
    if isinstance(text_or_list, (list, tuple)):
        parts = [_text(p) for p in text_or_list]
    else:
        text = _text(text_or_list)
        sep = '\n' if '\n' in text else ('>' if '>' in text else ',')
        parts = [p.strip() for p in text.split(sep)]
    out = []
    seen = set()
    for part in parts:
        if part and part.lower() not in seen:
            seen.add(part.lower())
            out.append(part)
    return out


def who_moves(options=None, loader=None):
    """The who-moves list (highest priority first) Clash to Issues and BCF Export use:
    Clash Assigner's saved order (namo.clashassign.saved_settings, which gives its own
    default when nothing is saved), so the two tools cannot drift apart. Only when that
    cannot be read: options['who_moves'], else DEFAULT_MOVE_ORDER. loader: the test seam
    saved_settings takes."""
    try:
        from namo import clashassign
        order = move_order(clashassign.saved_settings(loader)[0])
        if order:
            return order
    except Exception:
        pass
    return move_order((options or {}).get('who_moves')) or list(DEFAULT_MOVE_ORDER)


def rank(trade, order):
    lowered = [o.lower() for o in order]
    text = _text(trade).lower()
    return lowered.index(text) if text in lowered else len(order)


def mover(trade_a, trade_b, order):
    """The trade that moves, or '' when it cannot be decided (an unassigned model)."""
    from namo import naming
    a, b = _text(trade_a), _text(trade_b)
    if not a or not b or a.lower() == UNASSIGNED.lower() or b.lower() == UNASSIGNED.lower():
        return ''
    if a.lower() == b.lower():
        return a
    ra, rb = rank(a, order), rank(b, order)
    if ra == rb:
        return sorted([a, b], key=naming.natural_key)[0]
    return a if ra > rb else b


def parse_bands(text):
    """(pairs, bad lines) from 'depth = priority' lines (metres; priority any spelling
    namo.issues knows). Blank lines are ignored."""
    from namo import issues
    pairs = []
    bad = []
    for line in _text(text).split('\n'):
        if not line.strip():
            continue
        left, sep, right = line.partition('=')
        priority = issues.canonical_priority(right, default=None) if sep else None
        try:
            depth = float(left.strip())
        except ValueError:
            depth = None
        if depth is None or priority is None or depth < 0:
            bad.append(line.strip())
            continue
        pairs.append((depth, priority))
    return pairs, bad


def bands_of(value):
    """[(depth_m, priority)] deepest first from config (pairs or 'depth=priority' lines);
    the defaults when nothing usable is given."""
    from namo import issues
    pairs = []
    if isinstance(value, (list, tuple)):
        for item in value:
            try:
                pairs.append((float(item[0]), issues.canonical_priority(item[1])))
            except (TypeError, ValueError, IndexError):
                continue
    else:
        pairs, _bad = parse_bands(value)
    return sorted(pairs, key=lambda p: -p[0]) or [tuple(b) for b in DEFAULT_BANDS]


def priority_for(distance_m, bands=None):
    """Priority from a clash distance in metres (negative = penetration)."""
    if distance_m is None:
        return 'Normal'
    depth = -float(distance_m) if float(distance_m) < 0 else 0.0
    for limit, priority in bands_of(bands if bands is not None else DEFAULT_BANDS):
        if depth >= limit and depth > 0:
            return priority
    return 'Low'


def due_for(priority, due_days=None, today=None):
    """'YYYY-MM-DD' = today + days for the priority ('' when that priority has none)."""
    days = (due_days or DEFAULT_DUE).get(priority)
    if days is None:
        return ''
    day = today or datetime.date.today()
    if isinstance(day, datetime.datetime):
        day = day.date()
    return (day + datetime.timedelta(days=int(days))).strftime('%Y-%m-%d')


def dominant_pair(rows):
    """(trade_a, trade_b) most common among rows (first seen wins ties), or ('', '')."""
    counts = {}
    order = []
    for row in rows:
        pair = (_text(row.get('trade_a')), _text(row.get('trade_b')))
        key = tuple(sorted(p.lower() for p in pair))
        if key not in counts:
            counts[key] = [0, pair]
            order.append(key)
        counts[key][0] += 1
    if not order:
        return ('', '')
    best = sorted(order, key=lambda k: (-counts[k][0], order.index(k)))[0]
    return counts[best][1]


def build_units(rows, top_of):
    """Top-level units from snapshot rows in test order. top_of: {clash guid: (group
    guid, group name)} for clashes inside a top-level group. Returns
    [{'kind': 'group'|'clash', 'guid', 'name', 'rows'}]."""
    units = []
    by_group = {}
    for row in rows:
        guid = _text(row.get('guid')).lower()
        top = top_of.get(guid)
        if top is None:
            units.append({'kind': 'clash', 'guid': guid, 'name': _text(row.get('name')),
                          'rows': [row]})
            continue
        group_guid, group_name = top
        unit = by_group.get(group_guid)
        if unit is None:
            unit = {'kind': 'group', 'guid': _text(group_guid).lower(), 'name': _text(group_name),
                    'rows': []}
            by_group[group_guid] = unit
            units.append(unit)
        unit['rows'].append(row)
    return units


def wanted(unit, statuses):
    """True when any clash of the unit has one of the statuses."""
    chosen = set(_text(s).lower() for s in statuses or OPEN_CLASH)
    return any(_text(r.get('status')).lower() in chosen for r in unit['rows'])


def worst_row(unit):
    """The deepest clash (smallest distance) of the unit."""
    def key(row):
        d = row.get('distance_m')
        return float(d) if d is not None else float('inf')
    return sorted(unit['rows'], key=key)[0]


def source_ref(test_guid, unit_guid):
    return '%s|%s' % (_text(test_guid).lower(), _text(unit_guid).lower())


def distance_text(distance_m, doc_units):
    """'45 mm' / '1.8 in' (clearance shown as '+12 mm'); '' when unknown."""
    from namo import units
    if distance_m is None:
        return ''
    value = float(distance_m)
    if units.is_imperial(doc_units):
        inches = abs(value) / 0.0254
        text = '%.1f in' % inches
    else:
        text = '%d mm' % int(round(abs(value) * 1000.0))
    return ('+' if value > 0 else '') + text


def unit_fields(unit, test_name, test_guid, options=None, trade_names=None, template=None,
                today=None, doc_units=''):
    """(fields, title_values, ref) for one unit: what create() gets (pure)."""
    from namo import issue_templates
    options = dict(DEFAULTS, **(options or {}))
    template = issue_templates.normalise(template or issue_templates.default('Clash'))
    worst = worst_row(unit)
    trade_a, trade_b = dominant_pair(unit['rows'])
    trades_lower = dict((t.lower(), t) for t in (trade_names or []))
    assigned = _text(worst.get('assigned'))
    for row in unit['rows']:
        if _text(row.get('assigned')):
            assigned = _text(row.get('assigned'))
            break
    trade = ''
    assignee = ''
    if assigned and assigned.lower() in trades_lower:
        trade = trades_lower[assigned.lower()]
    else:
        assignee = assigned
        trade = mover(trade_a, trade_b, move_order(options['who_moves']))
    if not trade and template['trade']:
        trade = template['trade']
    priority = priority_for(worst.get('distance_m'), options['bands'])
    due_days = dict(DEFAULT_DUE)
    due_days.update(options.get('due_days') or {})
    count = len(unit['rows'])
    a_name = _text(worst.get('item_a_name')) or 'Item 1'
    b_name = _text(worst.get('item_b_name')) or 'Item 2'
    lines = ['Clash test: %s' % test_name,
             ('%d clashes, deepest %s' % (count, distance_text(worst.get('distance_m'), doc_units))
              if count > 1 else 'Distance: %s' % distance_text(worst.get('distance_m'), doc_units)),
             'Between: %s (%s) and %s (%s)' % (a_name, _text(worst.get('model_a')) or 'unknown model',
                                               b_name, _text(worst.get('model_b')) or 'unknown model')]
    where = ', '.join(p for p in (('Grid %s' % worst['grid']) if worst.get('grid') else '',
                                  ('Level %s' % worst['level']) if worst.get('level') else '') if p)
    if where:
        lines.append(where)
    description = (template['description'] + '\n' if template['description'] else '') + '\n'.join(lines)
    location = None
    centre = worst.get('center')
    if centre:
        location = {'point': [float(c) for c in centre], 'units': doc_units,
                    'level': _text(worst.get('level')), 'grid': _text(worst.get('grid'))}
    ref = source_ref(test_guid, unit['guid'])
    fields = {'type': template['type'], 'priority': priority, 'trade': trade,
              'assignee': assignee or template['assignee'],
              'due': due_for(priority, due_days, today), 'description': description,
              'labels': list(template['labels']), 'location': location,
              'source': {'kind': 'clash', 'ref': ref, 'test': test_name,
                         'test_guid': _text(test_guid).lower(), 'result_guid': unit['guid'],
                         'unit': unit['kind'], 'clashes': count,
                         'distance_m': worst.get('distance_m')}}
    values = {'clash': unit['name'] or _text(worst.get('name')), 'test': test_name,
              'a': a_name, 'b': b_name, 'level': _text(worst.get('level')),
              'grid': _text(worst.get('grid')), 'type': template['type']}
    return fields, values, ref


def topic_for_unit(unit, test_name, test_guid, options=None, trade_names=None, user='',
                   doc_units=''):
    """A BCF topic dict for a unit (BCF Export straight from clashes; no issue made).
    Camera, components and snapshot are added by the caller."""
    from namo import bcf, issues
    fields, values, ref = unit_fields(unit, test_name, test_guid, options, trade_names,
                                      doc_units=doc_units)
    worst = worst_row(unit)
    open_any = any(_text(r.get('status')) in OPEN_CLASH for r in unit['rows'])
    resolved = all(_text(r.get('status')) == 'Resolved' for r in unit['rows'])
    status = 'Open' if open_any else ('Resolved' if resolved else 'Closed')
    created = _text(worst.get('created')) or issues.stamp()
    return {
        'guid': bcf.guid(unit['guid']), 'type': 'Clash', 'status': issues.bcf_status(status),
        'title': '%s: %s vs %s' % (values['clash'], values['a'], values['b']),
        'priority': fields['priority'], 'labels': [l for l in [test_name, fields['trade']] if l],
        'creation_date': created, 'creation_author': user or 'Navisworks',
        'modified_date': issues.stamp(), 'modified_author': user,
        'due_date': fields['due'], 'assigned_to': fields['assignee'] or fields['trade'],
        'description': fields['description'], 'comments': [], 'viewpoints': [],
        'reference_links': [], 'document_references': [],
    }


# ---- API half ---------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def top_groups_map(test):
    """{clash guid: (top group guid, top group name)} and {top group guid: group object}."""
    from namo import clashdata
    ClashApi = clashdata._clash_api()
    top_of = {}
    objects = {}
    for entry in clashdata.groups(test):
        group = entry['result']
        guid = entry['guid'].lower()
        objects[guid] = group
        stack = [group]
        while stack:
            node = stack.pop()
            for child in node.Children:
                if isinstance(child, ClashApi.ClashResultGroup):
                    stack.append(child)
                elif isinstance(child, ClashApi.ClashResult):
                    top_of[str(child.Guid).lower()] = (guid, entry['name'])
    return top_of, objects


def read_units(test, doc=None, progress=None):
    """(units, live objects {unit guid: ClashResult or ClashResultGroup}) of one test."""
    from namo import clashdata
    rows = clashdata.snapshot(test, doc, progress)
    leaves = clashdata.results(test)
    top_of, objects = top_groups_map(test)
    units = build_units(rows, top_of)
    for unit in units:
        if unit['kind'] == 'clash':
            index = unit['rows'][0]['id']
            if 0 <= index < len(leaves):
                objects[unit['guid']] = leaves[index]
    return units, objects


def unit_items(obj):
    """The ModelItems a unit involves: a clash's two items, a group's selections."""
    from namo import items
    out = []
    try:
        for item in (obj.Item1, obj.Item2):
            if item is not None:
                out.append(item)
        return out
    except Exception:
        pass
    for attr in ('Selection1', 'Selection2'):
        try:
            for item in getattr(obj, attr):
                out.append(item)
                if len(out) >= GROUP_ELEMENT_LIMIT:
                    return items.dedupe(out)
        except Exception:
            continue
    return items.dedupe(out)


def unit_camera(obj, doc=None):
    from namo import camera, clashdata
    try:
        return camera.from_viewpoint(clashdata.viewpoint(obj, doc))
    except Exception:
        try:
            return camera.from_viewpoint(clashdata.viewpoint(obj.RepresentativeResult, doc))
        except Exception:
            return None


def unit_image(obj, path, doc=None, width=1280, height=720):
    from namo import images
    try:
        return images.clash(obj, path, width, height, doc, quality=88)
    except Exception:
        return images.clash(obj.RepresentativeResult, path, width, height, doc, quality=88)


def convert(test_names, options=None, doc=None, progress=None):
    """Creates an issue per new unit of the named tests. Returns
    {'created': [ids], 'skipped': n (already converted), 'filtered': n (status),
     'snapshots': n, 'snapshot_errors': n, 'tests': n}.
    progress(fraction, label); False cancels (items.Cancelled; issues made so far stay)."""
    from namo import clashdata, config, issue_templates, issueapi, issuestore, items
    document = _doc(doc)
    options = dict(DEFAULTS, **(options or {}))
    options['who_moves'] = who_moves(options)
    store = issuestore.for_doc(document)
    store.require_saved()
    existing = store.sources('clash')
    template = issue_templates.resolve(options.get('template') or 'Clash') or \
        issue_templates.default('Clash')
    trade_names = config.get('trades') or []
    units_name = issueapi.doc_units(document)
    out = {'created': [], 'skipped': 0, 'filtered': 0, 'snapshots': 0, 'snapshot_errors': 0,
           'tests': 0}
    tests = [clashdata.test_by_name(n, document) for n in test_names]
    tests = [t for t in tests if t is not None]
    span = 1.0 / (len(tests) or 1)
    snapshots_left = int(options.get('max_snapshots') or 0) if options.get('snapshots') else 0
    try:
        for index, test in enumerate(tests):
            name = test.DisplayName
            test_guid = str(test.Guid)
            base = index * span

            def read_progress(fraction, label, base=base):
                if progress is None:
                    return True
                return progress(base + span * 0.3 * fraction, 'Reading %s' % name)
            units, objects = read_units(test, document, read_progress)
            out['tests'] += 1
            todo = []
            for unit in units:
                if not wanted(unit, options['statuses']):
                    out['filtered'] += 1
                    continue
                if source_ref(test_guid, unit['guid']) in existing:
                    out['skipped'] += 1
                    continue
                todo.append(unit)
            for number, unit in enumerate(todo):
                if progress is not None and progress(
                        base + span * (0.3 + 0.7 * float(number) / (len(todo) or 1)),
                        '%s: issue %d of %d' % (name, number + 1, len(todo))) == False:  # noqa: E712
                    raise items.Cancelled()
                fields, values, ref = unit_fields(unit, name, test_guid, options, trade_names,
                                                  template, doc_units=units_name)
                obj = objects.get(unit['guid'])
                if obj is not None:
                    cam = unit_camera(obj, document)
                    if cam is not None:
                        fields['camera'] = cam
                        fields['camera_units'] = units_name
                    records, _objs, _total = issueapi.elements_of(unit_items(obj), document,
                                                                  GROUP_ELEMENT_LIMIT)
                    fields['elements'] = records
                issue = store.create(fields, prefix=template['prefix'],
                                     title_pattern=template['title_pattern'],
                                     title_values=values, notify_now=False)
                existing[ref] = issue['id']
                out['created'].append(issue['id'])
                if obj is not None and snapshots_left > 0:
                    snapshots_left -= 1
                    try:
                        path = unit_image(obj, issueapi.temp_path('.jpg', 'clash'), document)
                        store.add_image(issue['id'], path, kind='snapshot', move=True,
                                        notify_now=False)
                        out['snapshots'] += 1
                    except Exception:
                        out['snapshot_errors'] += 1
    finally:
        if out['created']:
            issuestore.notify('created', out['created'], store.key)
    return out

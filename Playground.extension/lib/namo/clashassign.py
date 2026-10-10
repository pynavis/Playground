# -*- coding: utf-8 -*-
"""Clash Assigner: ball in court for clash groups and ungrouped clashes.

Units of work are the TOP-LEVEL items of a test: each result group, and each clash not
in a group. Auto mode assigns each unit to the trade that moves: of the unit's trade
pair (the most common pair among its clashes, namo.trades of the model names), the
trade LOWER in the "who moves" list moves (config, default Structure, Architecture,
Mechanical, Plumbing, Electrical, Fire Protection). A trade missing from the list
counts as lowest (it moves); 'Unassigned' models cannot be decided and are reported.
Manual mode assigns chosen units to a chosen trade or person. A trade can map to a
person's name (config 'names').

AssignedTo is written per unit, all in ONE undo step: TestsEditResultAssignedTo on the
group or the clash for up to namo.clashset_edit.EDIT_LIMIT units; above that each test
is rebuilt once on a copy and swapped in (the shipped Clash Grouper's route, because
every document-side clash edit costs a fixed amount that grows with the model). A
rebuilt group hands its assignee to the clashes inside it, as assigning a group in
Clash Detective does. Every run that assigns appends a history record to the
document database (namo.store RecordStore 'clash-ball-in-court', mode 'model' so it
travels with the NWF; local files when the database is unavailable, and the tool says
so):

    {'id': 'bic-20261005-143000-123456', 'time': ISO, 'user', 'mode': 'auto'|'manual',
     'changes': [[test, guid, name, kind, from, to], ...]}

The dashboard (output window) counts open units per assignee with their ages, and
lists the oldest open units first with how long the current assignee has held them.

Pure first (unit tested); the API half after.
"""

import datetime

from namo import naming

STORE = 'clash-ball-in-court'
DEFAULT_PRIORITY = ['Structure', 'Architecture', 'Mechanical', 'Plumbing', 'Electrical',
                    'Fire Protection']
# pynavis.script.get_config keys a bundle's settings by its extension-relative path
# ('cfg_' + the path lowercased, non-alphanumerics as underscores): this tool's button.
SETTINGS_KEY = 'cfg_coordinate_tab_clash_results_panel_clash_assigner_pushbutton'
UNASSIGNED = 'Unassigned'
CLOSED = ('Resolved', 'Approved')
AGE_BUCKETS = (7, 14, 30)


# ---- pure: who moves ---------------------------------------------------------------------------


def priority_list(text_or_list):
    """A clean priority list from config (a list, or text with one trade per line or
    separated by '>' or ','). Duplicates dropped (case-insensitive)."""
    if isinstance(text_or_list, (list, tuple)):
        parts = [str(p) for p in text_or_list]
    else:
        text = str(text_or_list or '')
        sep = '\n' if '\n' in text else ('>' if '>' in text else ',')
        parts = text.split(sep)
    out = []
    seen = set()
    for part in parts:
        name = part.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def rank(trade, priority):
    """Position in the priority list (case-insensitive); unknown trades rank last."""
    lowered = [p.lower() for p in priority]
    text = str(trade or '').strip().lower()
    return lowered.index(text) if text in lowered else len(priority)


def mover(trade_a, trade_b, priority):
    """The trade that moves for a clash between trade_a and trade_b, or None when it
    cannot be decided (both unassigned). Same trade: that trade."""
    a = str(trade_a or '').strip()
    b = str(trade_b or '').strip()
    known = [t for t in (a, b) if t and t.lower() != UNASSIGNED.lower()]
    if len(known) < 2:
        return None
    if a.lower() == b.lower():
        return a
    ra, rb = rank(a, priority), rank(b, priority)
    if ra == rb:
        return sorted([a, b], key=naming.natural_key)[0]
    return a if ra > rb else b


def dominant_pair(rows):
    """(trade_a, trade_b) most common among rows (order as in the clash), or ('', '')."""
    counts = {}
    order = []
    for row in rows:
        pair = (str(row.get('trade_a') or ''), str(row.get('trade_b') or ''))
        key = tuple(sorted(p.lower() for p in pair))
        if key not in counts:
            counts[key] = [0, pair]
            order.append(key)
        counts[key][0] += 1
    if not order:
        return ('', '')
    best = sorted(order, key=lambda k: (-counts[k][0], order.index(k)))[0]
    return counts[best][1]


def names_map(text_or_dict):
    """{trade lower: person} from config: a dict, or lines 'Trade = Person'."""
    out = {}
    if isinstance(text_or_dict, dict):
        items = text_or_dict.items()
    else:
        items = []
        for line in str(text_or_dict or '').split('\n'):
            if '=' in line:
                left, _sep, right = line.partition('=')
                items.append((left, right))
    for trade, person in items:
        trade, person = str(trade).strip(), str(person).strip()
        if trade and person:
            out[trade.lower()] = person
    return out


def saved_settings(loader=None):
    """(priority list, {trade lower: person}) as Clash Assigner's Shift+Click saved them
    (SETTINGS_KEY), for other tools that follow its who-moves order. Never raises: an
    unreadable or missing file, or an empty list, gives DEFAULT_PRIORITY and no names.
    loader(key, defaults) is a test seam for pynavis.settings.load."""
    defaults = {'priority': list(DEFAULT_PRIORITY), 'names': ''}
    try:
        if loader is None:
            from pynavis import settings
            loader = settings.load
        stored = loader(SETTINGS_KEY, defaults)
        priority = priority_list(stored.get('priority') or defaults['priority'])
        names = names_map(stored.get('names') or '')
    except Exception:
        return list(DEFAULT_PRIORITY), {}
    return priority or list(DEFAULT_PRIORITY), names


def assignee_for(trade, names):
    """The name written to AssignedTo for a trade (its person, else the trade)."""
    if not trade:
        return None
    return names.get(str(trade).lower(), trade)


def is_open(status):
    return str(status or '') not in CLOSED


def plan_auto(units, priority, names, reassign=False):
    """{'assign': [(unit, name)], 'undecided': [unit], 'kept': [unit], 'closed': [unit]}
    for units [{'kind', 'rows', 'assigned', 'status', ...}]. Closed units are left alone;
    units that already have an assignee are kept unless reassign."""
    out = {'assign': [], 'undecided': [], 'kept': [], 'closed': []}
    for unit in units:
        if not unit.get('open', True):
            out['closed'].append(unit)
            continue
        pair = dominant_pair(unit['rows'])
        trade = mover(pair[0], pair[1], priority)
        if trade is None:
            out['undecided'].append(unit)
            continue
        name = assignee_for(trade, names)
        current = unit.get('assigned') or ''
        if current and (not reassign or current == name):
            out['kept'].append(unit)
            continue
        out['assign'].append((unit, name))
    return out


def tally_names(pairs):
    """[(name, count)] most first (ties by name) for [(unit, name)]."""
    counts = {}
    for _unit, name in pairs:
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda p: (-p[1], naming.natural_key(p[0])))


def confirm_text(planned):
    """The question asked before Auto writes anything."""
    lines = ['Assign {:,} item{}:'.format(len(planned['assign']), '' if len(planned['assign']) == 1 else 's')]
    for name, count in tally_names(planned['assign'])[:12]:
        lines.append('  %s: %s' % (name, '{:,}'.format(count)))
    if planned['undecided']:
        lines.append('{:,} could not be decided (a model has no trade; add a trade rule in '
                     'Playground settings).'.format(len(planned['undecided'])))
    if planned['kept']:
        lines.append('{:,} already have an assignee and are left alone.'.format(len(planned['kept'])))
    return '\n'.join(lines)


# ---- pure: history and dashboard ----------------------------------------------------------------


def new_record(changes, user, mode, now=None):
    """A history record (see the module docstring)."""
    stamp = now or datetime.datetime.now()
    return {'id': 'bic-' + stamp.strftime('%Y%m%d-%H%M%S-') + ('%06d' % stamp.microsecond),
            'time': stamp.strftime('%Y-%m-%dT%H:%M:%S'), 'user': user or '', 'mode': mode,
            'changes': [list(c) for c in changes]}


def ownership(records):
    """{guid: {'to', 'from', 'since', 'test', 'name', 'by'}}: the latest change per item,
    records taken in time order."""
    out = {}
    for record in sorted([r for r in records if isinstance(r, dict)],
                         key=lambda r: (r.get('time') or '', r.get('id') or '')):
        for change in record.get('changes') or []:
            if not isinstance(change, (list, tuple)) or len(change) < 6:
                continue
            test, guid, name, _kind, before, after = change[:6]
            owner = {'to': after, 'from': before, 'since': record.get('time'),
                     'test': test, 'name': name, 'by': record.get('user', '')}
            out[str(guid)] = owner
            out[owner_key(test, name)] = owner
    return out


def owner_key(test, name):
    """The by-name key of an ownership entry: a test rebuilt by Clash Grouper, Clash
    Namer or a big assignment may hand its results new ids, so the history is also
    found by test and item name."""
    return 'n:%s|%s' % (test or '', name or '')


def unit_age(unit, today):
    """Days since the oldest clash in the unit was found, or None."""
    from namo import dates
    created = [dates.parse(r.get('created')) for r in unit['rows'] if r.get('created')]
    created = [c for c in created if c is not None]
    if not created or today is None:
        return None
    return dates.days_between(min(created), today)


def held_days(unit, owners, today):
    """Days the current assignee has held the unit (from the history), or None."""
    from namo import dates
    owner = owners.get(str(unit.get('guid'))) or \
        owners.get(owner_key(unit.get('test'), unit.get('name')))
    if not owner or not unit.get('assigned') or owner.get('to') != unit.get('assigned'):
        return None
    since = dates.parse(owner.get('since'))
    return dates.days_between(since, today) if since is not None else None


def dashboard(units, owners, today):
    """{'by_assignee': [{'assignee', 'items', 'clashes', 'oldest', 'average', 'buckets'}]
    (most items first), 'oldest': [{'unit', 'age', 'held'}] oldest first, 'open': n,
    'clashes': n}. Only open units count; an empty assignee shows as 'Not assigned'."""
    from namo import dates
    groups = {}
    rows = []
    for unit in units:
        if not unit.get('open', True):
            continue
        age = unit_age(unit, today)
        held = held_days(unit, owners, today)
        rows.append({'unit': unit, 'age': age, 'held': held})
        key = unit.get('assigned') or 'Not assigned'
        entry = groups.setdefault(key, {'assignee': key, 'items': 0, 'clashes': 0, 'ages': []})
        entry['items'] += 1
        entry['clashes'] += sum(1 for r in unit['rows'] if is_open(r.get('status')))
        if age is not None:
            entry['ages'].append(age)
    labels = dates.bucket_labels(AGE_BUCKETS)
    by_assignee = []
    for key in groups:
        entry = groups[key]
        ages = entry.pop('ages')
        buckets = dict((label, 0) for label in labels)
        for age in ages:
            buckets[dates.age_bucket(age, AGE_BUCKETS)] += 1
        entry['oldest'] = max(ages) if ages else None
        entry['average'] = (float(sum(ages)) / len(ages)) if ages else None
        entry['buckets'] = [buckets[label] for label in labels]
        by_assignee.append(entry)
    by_assignee.sort(key=lambda e: (-e['items'], naming.natural_key(e['assignee'])))
    rows.sort(key=lambda r: (-(r['age'] if r['age'] is not None else -1),
                             naming.natural_key(r['unit'].get('name', ''))))
    return {'by_assignee': by_assignee, 'oldest': rows, 'open': len(rows),
            'clashes': sum(e['clashes'] for e in by_assignee), 'labels': labels}


def unit_cells(unit):
    """Table cells for the manual chooser: Test, Item, Kind, Clashes, Status, Assigned,
    Trades."""
    pair = dominant_pair(unit['rows'])
    trades = ' / '.join(t for t in pair if t) if any(pair) else ''
    return [unit.get('test', ''), unit.get('name', ''), 'Group' if unit['kind'] == 'group' else 'Clash',
            len(unit['rows']), unit.get('status', ''), unit.get('assigned') or '', trades]


# ==== API half (Navisworks only; lazy imports) =============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _assignee_name(assignee):
    try:
        if assignee is not None and assignee.Assigned:
            return assignee.DisplayName or ''
    except Exception:
        pass
    return ''


def units_of(entry):
    """Top-level units of a namo.clashname.read_test entry: groups and ungrouped clashes,
    tree order, each {'kind', 'item' (live), 'guid', 'name', 'rows', 'assigned',
    'status', 'open', 'test', 'link' (a ModelItem to show), 'node' and 'entry' (where
    it sits, for assign's rebuild route)}."""
    from namo import clashname
    out = []
    rows = entry['rows']
    for node in entry['nodes']:
        if node[0] == 'leaf':
            row = rows[node[2]]
            item = node[1]
            unit_rows = [row]
            name = row.get('name') or ''
            status = row.get('status') or ''
            kind = 'clash'
        else:
            item = node[1]
            ids = []
            stack = [node]
            while stack:
                current = stack.pop()
                for child in current[3]:
                    if child[0] == 'leaf':
                        ids.append(child[2])
                    else:
                        stack.append(child)
            ids.sort()
            unit_rows = [rows[i] for i in ids]
            name = item.DisplayName or ''
            status = clashname.dominant(r.get('status') for r in unit_rows) or str(item.Status)
            kind = 'group'
        link = None
        try:
            first = entry['leaves'][unit_rows[0]['id']] if unit_rows else None
            link = first.Item1 if first is not None else None
        except Exception:
            link = None
        out.append({'kind': kind, 'item': item, 'guid': str(item.Guid), 'name': name,
                    'rows': unit_rows, 'assigned': _assignee_name(item.AssignedTo),
                    'status': status, 'open': any(is_open(r.get('status')) for r in unit_rows),
                    'test': entry['name'], 'link': link, 'node': node, 'entry': entry})
    return out


def assign(pairs, doc=None, limit=None):
    """Writes AssignedTo for [(unit, name)] in ONE undo step. Returns the history
    changes [[test, guid, name, kind, from, to]]. Up to `limit` units
    (namo.clashset_edit.EDIT_LIMIT) are edited in place; more are written by rebuilding
    each test once (see the module docstring). After a rebuild the units' live items
    are dead: use only their plain values."""
    from namo import clashdata, clashset_edit
    document = _doc(doc)
    pairs = list(pairs)
    mode = clashset_edit.mode_for(len(pairs), clashset_edit.EDIT_LIMIT if limit is None else limit)
    if any(unit.get('entry') is None or unit.get('node') is None for unit, _name in pairs):
        mode = 'edit'
    changes = []
    swaps = len(set(id(unit.get('entry')) for unit, _name in pairs))
    with clashset_edit.one_step('Assign clashes', document, mode, swaps):
        if mode == 'edit':
            by_name = {}
            order = []
            for unit, name in pairs:
                if name not in by_name:
                    by_name[name] = []
                    order.append(name)
                by_name[name].append(unit)
            for name in order:
                clashdata.set_assigned([u['item'] for u in by_name[name]], name, document)
        else:
            _assign_by_rebuild(pairs, document)
        for unit, name in pairs:
            changes.append([unit['test'], unit['guid'], unit['name'], unit['kind'],
                            unit.get('assigned') or '', name])
            unit['assigned'] = name
    return changes


def _assign_by_rebuild(pairs, document):
    from pynavis._api import Api
    from namo import clashset_edit
    from namo import clashset_tests as defs
    data = defs._clash().get_clash(document).TestsData

    def setter(name):
        def edit(copy):
            copy.AssignedTo = clashset_edit.assignee(Api, name)
        return edit

    entries = []
    edits = {}
    for unit, name in pairs:
        entry = unit['entry']
        key = id(entry)
        if key not in edits:
            edits[key] = ({}, {})
            entries.append(entry)
        leaf_edits, group_edits = edits[key]
        node = unit['node']
        if node[0] == 'leaf':
            leaf_edits[node[2]] = setter(name)
        else:
            group_edits[node[2]] = setter(name)
            for rid in clashset_edit.leaf_ids_under(node):
                leaf_edits[rid] = setter(name)
    for entry in entries:
        leaf_edits, group_edits = edits[id(entry)]
        new_test = clashset_edit.rebuild(entry, leaf_edits, group_edits)
        clashset_edit.commit(data, entry['test'], new_test)


def history_store(doc=None):
    """The ball-in-court RecordStore for the active document (model mode, local fallback
    with .note set)."""
    from namo import store
    return store.records_for_active_doc(STORE, mode='model', doc=doc)


def save_history(changes, mode, doc=None):
    """Appends a history record; returns the store's fallback note (None when it went
    into the model). Raises IOError when nothing could be written."""
    from namo import config
    records = history_store(doc)
    records.put(new_record(changes, config.user_name(), mode))
    return records.note


def load_owners(doc=None):
    try:
        return ownership(history_store(doc).list())
    except Exception:
        return {}


def show_dashboard(units, owners, today, title, doc_units=None):
    """Writes the dashboard to the output window."""
    from pynavis import output
    from namo.clashset_common import plural
    board = dashboard(units, owners, today)
    output.set_title('Clash Assigner')
    output.print_md('# %s' % title)
    if not board['open']:
        output.print_md('Every item in these tests is resolved or approved.')
        return board
    output.print_md('%s and %s are open across %s.' % (
        plural(board['open'], 'item'), plural(board['clashes'], 'clash', 'clashes'),
        plural(len(board['by_assignee']), 'assignee')))
    headers = ['Assigned to', 'Open items', 'Open clashes', 'Oldest (days)', 'Average age (days)'] + \
        list(board['labels'])
    rows = []
    for entry in board['by_assignee']:
        rows.append([entry['assignee'], entry['items'], entry['clashes'],
                     '' if entry['oldest'] is None else entry['oldest'],
                     '' if entry['average'] is None else '%.1f' % entry['average']] + entry['buckets'])
    output.print_table(rows, headers)
    output.chart_bar([e['assignee'] for e in board['by_assignee'][:20]],
                     [e['items'] for e in board['by_assignee'][:20]], title='Open items by assignee')
    output.print_md('## Oldest open items')
    from namo.htmlreport import escape
    lines = ['<table class="pynavis"><tr><th>Test</th><th>Item</th><th>Assigned to</th>'
             '<th class="num">Age (days)</th><th class="num">Held (days)</th><th>Status</th>'
             '<th></th></tr>']
    for row in board['oldest'][:50]:
        unit = row['unit']
        link = output.element_link(unit['link'], 'Show') if unit.get('link') is not None else ''
        lines.append('<tr><td>%s</td><td>%s</td><td>%s</td><td class="num">%s</td>'
                     '<td class="num">%s</td><td>%s</td><td>%s</td></tr>' % (
                         escape(unit['test']), escape(unit['name']),
                         escape(unit.get('assigned') or 'Not assigned'),
                         '' if row['age'] is None else row['age'],
                         '' if row['held'] is None else row['held'],
                         escape(unit.get('status', '')), link))
    lines.append('</table>')
    output.print_html(''.join(lines))
    if len(board['oldest']) > 50:
        output.print_md('The 50 oldest of %s are shown.' % plural(len(board['oldest']), 'open item'))
    return board

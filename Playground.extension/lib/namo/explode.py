# -*- coding: utf-8 -*-
"""Exploded View: pull objects (or whole models) apart from their common centre.

Every object moves by (its centre - the common centre) x (factor - 1), along
all axes, vertically only, or along X or Y only. The moves are permanent
transform overrides (DocumentModels.OverridePermanentTransform with a
Transform3D.CreateTranslation, the Item Tools > Move route that composes with
a transform already there and never touches the source files), all in ONE
transaction, so one Ctrl+Z puts everything back.

What moved is recorded per document (session and the document's store): each
item's entry (namo.items.entries), its total offset and its centre after the
move as read back. Collapse moves each item back by its offset, but only when
it still sits where the explode left it (centre within a float32-aware
tolerance), so an item someone moved since is reported and left alone rather
than thrown somewhere new. Explode more adds to the offsets.

The pure half is tested on both engines; the API half lazy-imports pynavis.
"""

import datetime
import math

from namo import colorize

STORE = 'exploded-view'
HOLDER = 'explode'
MODES = (('radial', 'Away from the center'), ('vertical', 'Up and down only'),
         ('x', 'Along X only'), ('y', 'Along Y only'))
UNITS = (('items', 'The selected items'), ('models', 'Their whole models'))
DEFAULTS = {'factor': 1.5, 'mode': 'radial', 'units': 'items'}
MIN_FACTOR = 1.05
MAX_FACTOR = 10.0
MAX_UNITS = 5000             # one transform call each, inside one transaction

COLLAPSE = 'Collapse'
MORE = 'Explode more'


# =============================================================================
# Pure half
# =============================================================================


def normalize_options(values):
    values = values or {}
    try:
        factor = float(values.get('factor', DEFAULTS['factor']))
    except (TypeError, ValueError):
        factor = DEFAULTS['factor']
    factor = max(MIN_FACTOR, min(MAX_FACTOR, factor))
    mode = values.get('mode') if values.get('mode') in [m for m, _l in MODES] else DEFAULTS['mode']
    units = values.get('units') if values.get('units') in [u for u, _l in UNITS] else DEFAULTS['units']
    return {'factor': factor, 'mode': mode, 'units': units}


def option_fields(defaults, models_count=None):
    opts = normalize_options(defaults)
    unit_options = [(label, key) for key, label in UNITS]
    if models_count:
        unit_options[1] = ('Their whole models (%s)' % colorize.plural(models_count, 'model'), 'models')
    return [
        {'kind': 'number', 'key': 'factor', 'label': 'Spread', 'min': MIN_FACTOR, 'max': MAX_FACTOR,
         'suffix': 'x', 'default': opts['factor'],
         'hint': 'How far each object ends up from the common center: 1.5 is half as far again.'},
        {'kind': 'radio', 'key': 'mode', 'label': 'Direction',
         'options': [(label, key) for key, label in MODES], 'default': opts['mode'], 'fallback': None},
        {'kind': 'radio', 'key': 'units', 'label': 'Move', 'options': unit_options,
         'default': opts['units'], 'fallback': None},
    ]


def union_center(boxes):
    """Centre of the box enclosing every ((min), (max)) box; None for none."""
    low = [None, None, None]
    high = [None, None, None]
    for box in boxes:
        if box is None:
            continue
        for axis in range(3):
            if low[axis] is None or box[0][axis] < low[axis]:
                low[axis] = box[0][axis]
            if high[axis] is None or box[1][axis] > high[axis]:
                high[axis] = box[1][axis]
    if low[0] is None:
        return None
    return tuple((low[i] + high[i]) / 2.0 for i in range(3))


def box_center(box):
    if box is None:
        return None
    return tuple((box[0][i] + box[1][i]) / 2.0 for i in range(3))


def offsets(centers, origin, factor, mode='radial'):
    """[(dx, dy, dz)] moving each centre to origin + (centre - origin) x
    factor, restricted to the mode's axes. A None centre does not move."""
    mask = {'radial': (1, 1, 1), 'vertical': (0, 0, 1), 'x': (1, 0, 0), 'y': (0, 1, 0)}[mode]
    scale = float(factor) - 1.0
    out = []
    for center in centers:
        if center is None:
            out.append((0.0, 0.0, 0.0))
            continue
        out.append(tuple(mask[i] * (center[i] - origin[i]) * scale for i in range(3)))
    return out


def add(a, b):
    return tuple(float(a[i]) + float(b[i]) for i in range(3))


def negate(v):
    return tuple(-float(x) for x in v)


def is_zero(v, eps=1e-12):
    return all(abs(float(x)) <= eps for x in v)


def distance(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def tolerance(centers):
    """How far apart two reads of the same centre may be: one float32 step at
    the largest coordinate (the worst case pynavis.geometry.float_noise gives
    for world coordinates: about 2 inches on a model 1,370,000 ft from the
    origin) and a millionth of the spread, never below 1e-6. Two reads of an
    item nobody touched are the same numbers, so this only has to cover
    storage noise; anything wider would hide a small move or an undo."""
    largest = 0.0
    low = [None] * 3
    high = [None] * 3
    for c in centers:
        if c is None:
            continue
        for i in range(3):
            largest = max(largest, abs(float(c[i])))
            low[i] = c[i] if low[i] is None else min(low[i], c[i])
            high[i] = c[i] if high[i] is None else max(high[i], c[i])
    spread = 0.0
    if low[0] is not None:
        spread = math.sqrt(sum((high[i] - low[i]) ** 2 for i in range(3)))
    return max(1e-6, largest * 2.0 ** -23, spread * 1e-6)


def drop_nested(nodes, parent_of):
    """nodes without any whose ancestor is also in nodes (moving both would
    move the child twice). Order kept."""
    chosen = set(nodes)
    out = []
    for node in nodes:
        parent = parent_of(node)
        nested = False
        while parent is not None:
            if parent in chosen:
                nested = True
                break
            parent = parent_of(parent)
        if not nested:
            out.append(node)
    return out


def _now(now=None):
    return (now or datetime.datetime.now()).strftime('%Y-%m-%dT%H:%M:%S')


def tracks_moves(before, after, moves):
    """True when the read-back centres followed the moves (BoundingBox()
    reflects a permanent transform), so drift checks mean something; False
    when no moved item's centre changed. None when nothing moved."""
    tol = tolerance([c for c in before if c] + [c for c in after if c])
    seen = False
    for then, now, move in zip(before, after, moves):
        if then is None or now is None or is_zero(move):
            continue
        seen = True
        if distance(then, now) > tol:
            return True
    return False if seen else None


def make_record(entries, moves, centers_after, opts, now=None, tracks=None):
    """The stored record: [{'entry', 'offset', 'center'}] plus the options and
    'tracks' (tracks_moves: whether centres can show an item moved since)."""
    rows = []
    for entry, move, center in zip(entries, moves, centers_after):
        rows.append({'entry': entry, 'offset': [float(x) for x in move],
                     'center': None if center is None else [float(x) for x in center]})
    return {'version': 1, 'mode': opts['mode'], 'factor': float(opts['factor']),
            'units': opts['units'], 'time': _now(now), 'items': rows, 'tracks': tracks}


def merge_record(record, moves, centers_after, factor, now=None):
    """record with each item's offset grown by moves (parallel to
    record['items']) and its centre updated."""
    rows = []
    for row, move, center in zip(record['items'], moves, centers_after):
        rows.append({'entry': row['entry'], 'offset': list(add(row['offset'], move)),
                     'center': None if center is None else [float(x) for x in center]})
    out = dict(record)
    out['items'] = rows
    out['factor'] = float(record.get('factor') or 1.0) * float(factor)
    out['time'] = _now(now)
    return out


def collapse_plan(rows, current_centers, tracks=True):
    """[(index, inverse offset)] for record rows still where the explode left
    them, plus the count that moved since. current_centers is parallel to rows
    (None for an item not found). tracks False (centres cannot show a move)
    trusts every found row."""
    drift = drifted(rows, current_centers) if tracks is not False else [False] * len(rows)
    moves = []
    moved = 0
    for index, (row, now, gone) in enumerate(zip(rows, current_centers, drift)):
        if now is None:
            continue
        if gone:
            moved += 1
            continue
        if not is_zero(row['offset']):
            moves.append((index, negate(row['offset'])))
    return moves, moved


def drifted(rows, current_centers):
    """[bool] parallel to rows: True when an item that was found (current
    centre not None) no longer sits where the record left it."""
    recorded = [r.get('center') for r in rows]
    tol = tolerance([c for c in recorded if c] + [c for c in current_centers if c])
    out = []
    for row, now in zip(rows, current_centers):
        then = row.get('center')
        out.append(now is not None and then is not None and distance(then, now) > tol)
    return out


def rebase(record, drift):
    """record with the offsets of drifted rows set to zero: an item that is no
    longer where the explode left it (undone, or moved by hand) must not be
    moved back by an offset it may no longer carry."""
    out = dict(record)
    out['items'] = [dict(row, offset=[0.0, 0.0, 0.0]) if gone else dict(row)
                    for row, gone in zip(record['items'], drift)]
    return out


def is_stale(rows, current_centers, tracks=True):
    """True when no recorded item is where the explode left it (all undone,
    moved or gone): the record no longer describes the model. With tracks
    False only 'all gone' counts."""
    drift = drifted(rows, current_centers) if tracks is not False else [False] * len(rows)
    for now, gone in zip(current_centers, drift):
        if now is not None and not gone:
            return False
    return True


def valid_record(record):
    return (isinstance(record, dict) and isinstance(record.get('items'), list)
            and bool(record['items']))


def factor_text(factor):
    """'1.5x', '1.05x', '10x': two decimals at most, no trailing zeros."""
    text = '%.2f' % float(factor)
    return text.rstrip('0').rstrip('.') + 'x'


def describe(record):
    """'12 objects, spread 1.5x'."""
    count = len(record.get('items') or [])
    noun = 'model' if record.get('units') == 'models' else 'object'
    return '%s, spread %s' % (colorize.plural(count, noun), factor_text(record.get('factor') or 1.0))


def collapse_route(record):
    """How Collapse puts the items back. 'inverse': move each item back by its
    recorded offset, which keeps any move it carried before the explode; safe
    only when the centres read back showed the explode ('tracks' True), since
    then an undone or hand-moved item is seen and left alone. 'reset': drop
    the items' transform overrides altogether, which lands every item where
    its file has it whether or not the explode was undone in between; used
    when Navisworks' bounding boxes did not follow the move, because an
    inverse move after a Ctrl+Z would throw the items somewhere new."""
    return 'inverse' if record.get('tracks') is True else 'reset'


# =============================================================================
# API half
# =============================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _doc_path(document):
    try:
        return str(document.FileName or '')
    except Exception:
        return ''


def units_of(selected, units):
    """What moves: the selected items (nested ones dropped), or the distinct
    model roots they belong to."""
    from namo import items
    if units == 'models':
        roots = []
        for item in selected:
            node = item
            while node.Parent is not None:
                node = node.Parent
            roots.append(node)
        return items.dedupe(roots)
    return drop_nested(items.dedupe(list(selected)), lambda node: node.Parent)


def centers(nodes):
    from namo import items
    return [box_center(items.bbox(node)) for node in nodes]


def _move_all(document, nodes, moves, name):
    from pynavis._api import Api
    from pynavis.viewpoints import transaction
    moved = 0
    with transaction(name, document):
        for node, move in zip(nodes, moves):
            if is_zero(move):
                continue
            coll = Api.ModelItemCollection()
            coll.Add(node)
            transform = Api.Transform3D.CreateTranslation(
                Api.Vector3D(float(move[0]), float(move[1]), float(move[2])))
            document.Models.OverridePermanentTransform(coll, transform, False)
            moved += 1
    return moved


def explode(nodes, opts, doc=None):
    """Moves nodes apart (ONE undo step). Returns (moved, record)."""
    from namo import items
    document = _doc(doc)
    before = centers(nodes)
    origin = union_center([items.bbox(node) for node in nodes])
    if origin is None:
        return 0, None
    moves = offsets(before, origin, opts['factor'], opts['mode'])
    moved = _move_all(document, nodes, moves, 'Exploded view')
    after = centers(nodes)
    record = make_record(items.entries(nodes, document), moves, after, opts,
                         tracks=tracks_moves(before, after, moves))
    return moved, record


def check(record, doc=None):
    """Where the recorded items are now: {'nodes' [ModelItem or None],
    'current' [centre or None], 'drift' [bool], 'missing' count, 'stale'}."""
    document = _doc(doc)
    nodes, missing = _resolve_rows(record, document)
    current = [None if node is None else box_center(_bbox(node)) for node in nodes]
    tracks = record.get('tracks')
    drift = drifted(record['items'], current) if tracks is not False else [False] * len(current)
    return {'nodes': nodes, 'current': current, 'drift': drift, 'missing': missing,
            'stale': is_stale(record['items'], current, tracks)}


def explode_more(record, factor, doc=None):
    """Spreads the recorded items further from their current common centre
    (items no longer where the explode left them restart from zero). Returns
    (moved, new record, missing)."""
    from namo import items
    document = _doc(doc)
    state = check(record, document)
    record = rebase(record, state['drift'])
    found = state['nodes']
    nodes = [node for node in found if node is not None]
    if not nodes:
        return 0, record, state['missing']
    now = [c for node, c in zip(found, state['current']) if node is not None]
    origin = union_center([items.bbox(node) for node in nodes])
    moves_found = offsets(now, origin, factor, record.get('mode') or 'radial')
    moved = _move_all(document, nodes, moves_found, 'Exploded view')
    after = centers(nodes)
    if record.get('tracks') is not True:
        record['tracks'] = tracks_moves(now, after, moves_found)
    moves_all = []
    centers_all = []
    position = 0
    for index, row in enumerate(record['items']):
        if found[index] is not None:
            moves_all.append(moves_found[position])
            centers_all.append(after[position])
            position += 1
        else:
            moves_all.append((0.0, 0.0, 0.0))
            centers_all.append(row.get('center'))
    return moved, merge_record(record, moves_all, centers_all, factor), state['missing']


def _resolve_rows(record, document):
    """[ModelItem or None] parallel to record['items'], and the missing count."""
    from namo import items
    out = []
    missing = 0
    for row in record['items']:
        found, _lost = items.resolve([row['entry']], document)
        if found:
            out.append(found[0])
        else:
            out.append(None)
            missing += 1
    return out, missing


def collapse(record, doc=None):
    """Puts recorded items back (collapse_route), ONE undo step. Returns
    (moved back, moved since, missing)."""
    document = _doc(doc)
    state = check(record, document)
    if collapse_route(record) == 'reset':
        from namo import items
        from pynavis.viewpoints import transaction
        nodes = [node for node in state['nodes'] if node is not None]
        if nodes:
            with transaction('Collapse exploded view', document):
                document.Models.ResetPermanentTransform(items.collection(nodes))
        return len(nodes), 0, state['missing']
    plan, moved_since = collapse_plan(record['items'], state['current'], record.get('tracks'))
    nodes = [state['nodes'][index] for index, _move in plan]
    moves = [move for _index, move in plan]
    moved = _move_all(document, nodes, moves, 'Collapse exploded view') if nodes else 0
    return moved, moved_since, state['missing']


def _bbox(node):
    from namo import items
    return items.bbox(node)


def _holder():
    from namo import session
    return session.holder(HOLDER)


def load_record(doc=None):
    """The exploded-view record for the active document (session first, then
    the document's store), or None."""
    from namo import store
    document = _doc(doc)
    key = _doc_path(document).lower()
    records = getattr(_holder(), 'records', None) or {}
    if key in records:
        return records[key] if valid_record(records[key]) else None
    try:
        record = store.for_active_doc(STORE, doc=document).load(None)
    except Exception:
        record = None
    return record if valid_record(record) else None


def save_record(record, doc=None):
    """Keeps (or with None forgets) the record in the session and the
    document's store; a store failure is logged."""
    from namo import session, store
    document = _doc(doc)
    key = _doc_path(document).lower()
    holder = _holder()
    records = getattr(holder, 'records', None)
    if records is None:
        records = {}
        holder.records = records
    records[key] = record
    try:
        target = store.for_active_doc(STORE, doc=document)
        if record is None:
            target.delete()
        else:
            target.save(record)
    except Exception as error:
        session.log('warning', 'exploded view record not stored: %s' % error)

# -*- coding: utf-8 -*-
"""Model Compare: what was added, removed and changed between two versions of a model.

Two sources of "old": another appended model (the previous version appended beside
the new one) or a snapshot saved earlier with the document's Playground data.

Pure half (unit tested):
  * records: one dict per element-level object, {'uid', 'ifc', 'eid', 'guid', 'name',
    'cls', 'box', 'hash'} (missing values None);
  * match(): the chain Revit UniqueId -> IFC GlobalId -> Element ID -> instance GUID ->
    name + class + rounded box. A key is used only when it is unique on BOTH sides
    among the objects still unmatched; an ambiguous key falls through to the next
    scheme, so two walls sharing an Element ID never pair up by accident;
  * diff(): matched pairs become changed (moved: box centre moved more than the
    tolerance; resized: a box dimension changed more than the tolerance; properties:
    the hash of the chosen properties differs) or unchanged;
  * snapshots: compact, versioned, rounded (encode_snapshot / decode_snapshot).

API half: collect() reads the records of a model (keys probed once on 60 objects,
then one property read per key per object), paint() colours the result in one undo
step, write_sets() keeps the Compare/Added, Changed and Removed sets up to date, and
the snapshot store lives with the document's Playground data (namo.store).
"""

import hashlib
import math

FIELDS = ('uid', 'ifc', 'eid', 'guid')
SCHEMES = ('uid', 'ifc', 'eid', 'guid', 'shape')
SCHEME_LABEL = {'uid': 'Revit UniqueId', 'ifc': 'IFC GlobalId', 'eid': 'Element ID',
                'guid': 'Instance GUID', 'shape': 'Name and box'}
ID_FIELDS = (('uid', 'unique_id'), ('ifc', 'ifc_guid'), ('eid', 'element_id'))
EMPTY_GUID = '00000000-0000-0000-0000-000000000000'

DEFAULT_PROPERTIES = 'Element > Category\nElement > Family\nElement > Type'
DEFAULTS = {'tolerance_m': 0.002, 'compare_properties': False, 'properties': DEFAULT_PROPERTIES,
            'paint': True, 'sets': True}
OBJECT_BUDGET = 150000
PROBE = 60
SNAPSHOT_VERSION = 1
SET_FOLDER = 'Compare'
SET_NAMES = ('Added', 'Changed', 'Removed')

ADDED_HEX = '59A14F'        # green: new in the new version
CHANGED_HEX = 'F28E2B'      # amber: still there, but moved, resized or edited
REMOVED_HEX = 'D9302C'      # red: gone from the new version (painted on the OLD model)
GHOST_TRANSPARENCY = 0.8    # unchanged objects fade back


# ---- pure: records, keys, matching -----------------------------------------------------


def record(uid=None, ifc=None, eid=None, guid=None, name='', cls='', box=None, prop_hash=None):
    def clean(value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    guid = clean(guid)
    if guid is not None and guid.lower().strip('{}') == EMPTY_GUID:
        guid = None
    return {'uid': clean(uid), 'ifc': clean(ifc), 'eid': clean(eid), 'guid': guid,
            'name': str(name or ''), 'cls': str(cls or ''),
            'box': (tuple(box[0]), tuple(box[1])) if box else None, 'hash': prop_hash}


def _grid(value, size):
    return int(math.floor(float(value) / size + 0.5))


def shape_key(rec, tol):
    """'name|class|x0,y0,z0,x1,y1,z1' with the box rounded to the tolerance grid, or
    None when the object has no box."""
    if rec.get('box') is None:
        return None
    size = max(float(tol), 1e-9)
    corners = [_grid(v, size) for corner in rec['box'] for v in corner]
    return '%s|%s|%s' % (rec.get('name', '').strip().lower(), rec.get('cls', ''),
                         ','.join(str(c) for c in corners))


def key_of(rec, scheme, tol):
    if scheme == 'shape':
        return shape_key(rec, tol)
    value = rec.get(scheme)
    if value is None:
        return None
    return value.lower() if scheme in ('uid', 'ifc', 'guid') else value


def match(old, new, tol):
    """(pairs, removed, added): pairs [(old_index, new_index, scheme)] sorted by old
    index; removed / added are the unmatched indexes, sorted."""
    left = set(range(len(old)))
    right = set(range(len(new)))
    pairs = []
    for scheme in SCHEMES:
        if not left or not right:
            break
        old_keys = {}
        for i in sorted(left):
            key = key_of(old[i], scheme, tol)
            if key is not None:
                old_keys.setdefault(key, []).append(i)
        new_keys = {}
        for j in sorted(right):
            key = key_of(new[j], scheme, tol)
            if key is not None:
                new_keys.setdefault(key, []).append(j)
        for key in sorted(old_keys):
            olds = old_keys[key]
            news = new_keys.get(key)
            if news is None or len(olds) != 1 or len(news) != 1:
                continue
            pairs.append((olds[0], news[0], scheme))
            left.discard(olds[0])
            right.discard(news[0])
    pairs.sort()
    return pairs, sorted(left), sorted(right)


def _center(box):
    return tuple((box[0][i] + box[1][i]) / 2.0 for i in range(3))


def _size(box):
    return tuple(box[1][i] - box[0][i] for i in range(3))


def diff(old, new, pairs, tol, compare_hash=True):
    """(changed, unchanged): changed [(old_index, new_index, scheme, reasons)] with
    reasons [('moved', distance) | ('resized', largest size change) |
    ('properties', None)]; unchanged [(old_index, new_index, scheme)]."""
    changed = []
    unchanged = []
    for i, j, scheme in pairs:
        a, b = old[i], new[j]
        reasons = []
        if a.get('box') is not None and b.get('box') is not None:
            ca, cb = _center(a['box']), _center(b['box'])
            moved = math.sqrt(sum((ca[k] - cb[k]) ** 2 for k in range(3)))
            if moved > tol:
                reasons.append(('moved', moved))
            sa, sb = _size(a['box']), _size(b['box'])
            resized = max(abs(sa[k] - sb[k]) for k in range(3))
            if resized > tol:
                reasons.append(('resized', resized))
        if compare_hash and a.get('hash') is not None and b.get('hash') is not None \
                and a['hash'] != b['hash']:
            reasons.append(('properties', None))
        if reasons:
            changed.append((i, j, scheme, reasons))
        else:
            unchanged.append((i, j, scheme))
    return changed, unchanged


def counts(pairs, removed, added, changed, unchanged):
    """{'added', 'removed', 'changed', 'unchanged', 'matched', 'moved', 'resized',
    'properties', 'by_scheme': {scheme: n}}."""
    out = {'added': len(added), 'removed': len(removed), 'changed': len(changed),
           'unchanged': len(unchanged), 'matched': len(pairs), 'moved': 0, 'resized': 0,
           'properties': 0, 'by_scheme': {}}
    for _i, _j, _scheme, reasons in changed:
        for code, _value in reasons:
            out[code] += 1
    for _i, _j, scheme in pairs:
        out['by_scheme'][scheme] = out['by_scheme'].get(scheme, 0) + 1
    return out


def reason_text(reasons, length_text):
    """'Moved 120 mm, resized 15 mm, properties changed' (length_text formats a length
    in document units)."""
    parts = []
    for code, value in reasons:
        if code == 'moved':
            parts.append('moved %s' % length_text(value))
        elif code == 'resized':
            parts.append('resized %s' % length_text(value))
        elif code == 'properties':
            parts.append('properties changed')
    text = ', '.join(parts)
    return text[:1].upper() + text[1:] if text else ''


def summary(stats, objects_compared, sampled=False):
    """(level, message, detail) for the toast."""
    total = '{:,}'.format(objects_compared)
    if not (stats['added'] or stats['removed'] or stats['changed']):
        detail = '%s objects match.' % total
        if sampled:
            detail = 'The first %s objects match (the object budget stopped the read).' % total
        return ('info', 'No differences found', detail)
    message = '%s added, %s changed, %s removed' % (
        '{:,}'.format(stats['added']), '{:,}'.format(stats['changed']), '{:,}'.format(stats['removed']))
    detail = 'Compared %s objects.' % total
    if sampled:
        detail = 'Compared the first %s objects (the object budget stopped the read).' % total
    return ('success', message, detail)


# ---- pure: properties ----------------------------------------------------------------------


def parse_property_lines(text):
    """([(category, property)], problems) from 'Category > Property' lines (newlines
    or semicolons). Blank lines are skipped; a line without '>' is a problem."""
    pairs = []
    problems = []
    for raw in str(text or '').replace(';', '\n').splitlines():
        line = raw.strip()
        if not line:
            continue
        if '>' not in line:
            problems.append('"%s" needs a category and a property, like Element > Type.' % line)
            continue
        category, prop = line.split('>', 1)
        category, prop = category.strip(), prop.strip()
        if not category or not prop:
            problems.append('"%s" needs a category and a property, like Element > Type.' % line)
            continue
        if (category, prop) not in pairs:
            pairs.append((category, prop))
    return pairs, problems


def property_hash(values):
    """A short stable hash of [(category, property, value text)] (order does not
    matter); None when there are no values at all."""
    if not values:
        return None
    lines = sorted(u'%s\x1f%s\x1f%s' % (c, p, '' if v is None else v) for c, p, v in values)
    digest = hashlib.sha1(u'\n'.join(lines).encode('utf-8')).hexdigest()
    return digest[:16]


# ---- pure: snapshots -------------------------------------------------------------------------


def _round(value):
    return round(float(value), 4)


def encode_records(records):
    """Compact JSON-safe lists: [uid, ifc, eid, guid, name, cls, [6 floats] or None, hash]."""
    out = []
    for rec in records:
        box = rec.get('box')
        flat = [_round(v) for corner in box for v in corner] if box else None
        out.append([rec.get('uid'), rec.get('ifc'), rec.get('eid'), rec.get('guid'),
                    rec.get('name', ''), rec.get('cls', ''), flat, rec.get('hash')])
    return out


def decode_records(rows, scale=1.0):
    """Records back from encode_records, boxes multiplied by scale (unit change)."""
    out = []
    for row in rows or []:
        row = list(row) + [None] * (8 - len(row))
        flat = row[6]
        box = None
        if flat and len(flat) == 6:
            box = ((flat[0] * scale, flat[1] * scale, flat[2] * scale),
                   (flat[3] * scale, flat[4] * scale, flat[5] * scale))
        out.append(record(row[0], row[1], row[2], row[3], row[4], row[5], box, row[7]))
    return out


def snapshot_record(label, model, units, records, properties, when, sampled=False):
    """The stored snapshot: {'label', 'model', 'units', 'time', 'count', 'sampled',
    'properties': [[category, property]], 'version', 'objects'} (no 'id': the store
    assigns it)."""
    return {'label': str(label), 'model': str(model), 'units': str(units), 'time': str(when),
            'count': len(records), 'sampled': bool(sampled),
            'properties': [[c, p] for c, p in properties], 'version': SNAPSHOT_VERSION,
            'objects': encode_records(records)}


def snapshot_meta(snapshot):
    """The index entry for a snapshot (everything but the objects)."""
    return dict((k, snapshot.get(k)) for k in ('id', 'label', 'model', 'units', 'time', 'count',
                                               'sampled', 'properties', 'version'))


def check_snapshot(snapshot):
    """None when a stored snapshot can be compared, else a sentence."""
    if not isinstance(snapshot, dict):
        return 'The snapshot could not be read.'
    if snapshot.get('version') != SNAPSHOT_VERSION:
        return 'The snapshot was saved by another version of Playground.'
    if not isinstance(snapshot.get('objects'), list):
        return 'The snapshot holds no objects.'
    return None


# ---- pure: workbook ----------------------------------------------------------------------------


def write_xlsx(path, stats, sheets, title='Model compare', subtitle=None, author=None):
    """Summary plus one sheet per list. sheets: [(name, headers, rows)]. Returns path."""
    from namo import xlsx
    wb = xlsx.Workbook(title=title, author=author)
    ws = wb.sheet('Summary')
    ws.title(title, span=2)
    if subtitle:
        ws.subtitle(subtitle, span=2)
    ws.columns([('Result', 28, None), ('Objects', 12, 'int')])
    for label, key in (('Added', 'added'), ('Changed', 'changed'), ('Removed', 'removed'),
                       ('Unchanged', 'unchanged'), ('Moved', 'moved'), ('Resized', 'resized'),
                       ('Properties changed', 'properties')):
        ws.row([label, stats[key]])
    for scheme in SCHEMES:
        if stats['by_scheme'].get(scheme):
            ws.row(['Matched by %s' % SCHEME_LABEL[scheme], stats['by_scheme'][scheme]])
    for name, headers, rows in sheets:
        sheet = wb.sheet(name)
        sheet.columns([(h, None, None) for h in headers])
        for row in rows:
            sheet.row(row)
        sheet.autofilter()
    return wb.save(path)


# ---- API half ------------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _prop(node, category, name):
    from namo import variants
    try:
        value = variants.get(node, category, name)
    except Exception:
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def probe_pairs(objects, probe=PROBE):
    """{'uid' | 'ifc' | 'eid': (category, property) or None}: the REVIT_PROPERTIES pair
    found on most of the first `probe` objects, so the full read asks one property per
    key per object."""
    from namo import items
    sample = list(objects[:probe])
    out = {}
    for short, field in ID_FIELDS:
        best, best_hits = None, 0
        for pair in items.REVIT_PROPERTIES[field]:
            hits = sum(1 for obj in sample if _prop(obj, pair[0], pair[1]) is not None)
            if hits > best_hits:
                best, best_hits = pair, hits
        out[short] = best
    return out


def read_record(obj, pairs, prop_pairs):
    from namo import items
    values = {}
    for short in ('uid', 'ifc', 'eid'):
        pair = pairs.get(short)
        values[short] = _prop(obj, pair[0], pair[1]) if pair else None
    try:
        guid = str(obj.InstanceGuid)
    except Exception:
        guid = None
    try:
        box = items.bbox(obj)
    except Exception:
        box = None
    prop_hash = None
    if prop_pairs:
        prop_hash = property_hash([(c, p, _prop(obj, c, p)) for c, p in prop_pairs])
    return record(values['uid'], values['ifc'], values['eid'], guid,
                  obj.DisplayName or '', obj.ClassDisplayName or '', box, prop_hash)


def collect(root, budget=OBJECT_BUDGET, prop_pairs=None, progress=None, label='Reading'):
    """{'records', 'objects', 'sampled', 'pairs'} for the element-level objects under
    root (namo.items.objects), at most `budget` of them. progress(fraction, label) may
    raise a Cancelled."""
    from namo import items

    def tick(done, total):
        if progress is not None:
            progress(0.0, '%s: %s items walked' % (label, '{:,}'.format(done)))
        return True
    objects = items.objects([root], tick=tick, budget=budget)
    pairs = probe_pairs(objects)
    records = []
    total = max(1, len(objects))
    for index, obj in enumerate(objects):
        if progress is not None and index % 500 == 0:
            progress(float(index) / total, '%s: %s of %s objects' % (
                label, '{:,}'.format(index), '{:,}'.format(len(objects))))
        records.append(read_record(obj, pairs, prop_pairs or []))
    return {'records': records, 'objects': list(objects), 'sampled': bool(objects.sampled),
            'pairs': pairs}


def paint(added, changed, removed, unchanged, doc=None):
    """Colours the result as ONE undo step: groups [(items, hex, transparency)]."""
    from namo import paint as _paint
    groups = [(unchanged, None, GHOST_TRANSPARENCY), (added, ADDED_HEX, None),
              (changed, CHANGED_HEX, None), (removed, REMOVED_HEX, None)]
    return _paint.apply(groups, _doc(doc), name='Compare models')


def write_sets(lists, doc=None):
    """lists {'Added': items, 'Changed': items, 'Removed': items}. Updates the set
    Compare/<name> in place when it exists, else creates it. Empty lists are skipped
    (an existing set of that name is left as it was). Returns (written, skipped,
    failed) name lists. Call inside one transaction for one undo step."""
    from pynavis import sets
    document = _doc(doc)
    written, skipped, failed = [], [], []
    for name in SET_NAMES:
        found = list(lists.get(name) or [])
        if not found:
            skipped.append(name)
            continue
        try:
            existing = sets.find('%s/%s' % (SET_FOLDER, name), document)
            if existing is not None:
                sets.update(existing, found, document)
            else:
                sets.create(name, found, folder=SET_FOLDER, doc=document)
            written.append(name)
        except Exception:
            failed.append(name)
    return written, skipped, failed


def apply_results(added, changed, removed, unchanged, colour, make_sets, doc=None):
    """Colours and sets in ONE transaction ('Compare models'). Returns
    (written, skipped, failed) set names."""
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    result = ([], [], [])
    with transaction('Compare models', document):
        if colour:
            paint(added, changed, removed, unchanged, document)
        if make_sets:
            result = write_sets({'Added': added, 'Changed': changed, 'Removed': removed}, document)
    return result


INDEX_STORE = 'model-snapshot-index'
RECORD_STORE = 'model-snapshots'


def snapshot_stores(doc=None):
    """(index Store, RecordStore) for the active document's snapshots."""
    from namo import store
    document = _doc(doc)
    return (store.for_active_doc(INDEX_STORE, doc=document),
            store.records_for_active_doc(RECORD_STORE, doc=document))


def list_snapshots(doc=None):
    """Index entries (newest first). Rebuilt from the records when the index is gone."""
    index, records = snapshot_stores(doc)
    entries = index.load(None)
    if not isinstance(entries, list):
        entries = [snapshot_meta(r) for r in records.list()]
    entries = [e for e in entries if isinstance(e, dict) and e.get('id')]
    entries.sort(key=lambda e: (str(e.get('time') or ''), str(e.get('id'))), reverse=True)
    return entries


def save_snapshot(snapshot, doc=None):
    """Stores a snapshot_record() and its index entry; returns (stored record, note)
    where note is the store's fallback sentence or None. Raises IOError."""
    index, records = snapshot_stores(doc)
    stored = records.add(dict(snapshot), prefix='S-', width=3)
    meta = snapshot_meta(stored)

    def add(entries):
        entries = [e for e in (entries or []) if isinstance(e, dict) and e.get('id') != meta['id']]
        entries.append(meta)
        return entries
    index.update(add, default=[])
    return stored, records.note or index.note


def load_snapshot(snapshot_id, doc=None):
    _index, records = snapshot_stores(doc)
    return records.get(snapshot_id)

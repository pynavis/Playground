# -*- coding: utf-8 -*-
"""Session Stats: what each appended model weighs (files, items, geometry, primitives,
fragments, extent) and when and how fast it arrived this session.

Items and geometry items are always counted exactly (a native walk of each model's
DescendantsAndSelf). Primitives and fragments need ModelItem.Geometry on every
geometry item, which is the slow part on a big federation, so they are read exactly
for the first `budget` geometry items of a model and then on a systematic sample whose
stride doubles each time another `budget` readings have been taken; each reading is
weighted by the stride in force when it was taken. The estimate is marked as such in
every output ("estimated from 40,000 of 1,250,000").

Arrival times come from hk_sessionstats (doc-opened and model-appended stamps); load
seconds are known only for files appended with Batch Append, which times each file.
Everything else says "not recorded".
"""

import time

DEFAULT_BUDGET = 40000


class PrimitiveSampler(object):
    """Exact sums for the first `budget` items, then a doubling-stride sample.

    add(read) is called once per geometry item; read() -> (primitives, fragments) is
    only called for the items that are read. total() -> (primitives, fragments)."""

    def __init__(self, budget=DEFAULT_BUDGET):
        self.budget = max(1, int(budget))
        self.count = 0
        self.read_count = 0
        self.stride = 1
        self.taken_at_stride = 0
        self.primitives = 0.0
        self.fragments = 0.0
        self.failed = 0

    def add(self, read):
        index = self.count
        self.count += 1
        if index % self.stride:
            return False
        try:
            primitives, fragments = read()
        except Exception:
            self.failed += 1
            return False
        self.primitives += float(primitives) * self.stride
        self.fragments += float(fragments) * self.stride
        self.read_count += 1
        self.taken_at_stride += 1
        if self.taken_at_stride >= self.budget:
            self.stride *= 2
            self.taken_at_stride = 0
        return True

    @property
    def sampled(self):
        return self.read_count < self.count

    def total(self):
        return int(round(self.primitives)), int(round(self.fragments))


def size_text(box, doc_units):
    """'84.2 x 36.0 x 52.1 m' from a box in document units ('' for None)."""
    if box is None:
        return ''
    from namo import units
    symbol = units.doc_unit_symbol(doc_units)
    dims = [box[1][i] - box[0][i] for i in range(3)]
    return '%s x %s x %s %s' % tuple(['{:,.1f}'.format(d) for d in dims] + [symbol])


def load_text(entry):
    """How long a model took to load, or how it arrived."""
    if not entry:
        return 'not recorded'
    seconds = entry.get('load_seconds')
    if seconds is not None:
        return '%.1f s' % float(seconds)
    return 'not recorded'


def arrived_text(entry):
    if not entry:
        return 'not recorded'
    when = entry.get('appended_at')
    via = entry.get('via') or ''
    if when is None:
        return via or 'not recorded'
    stamp = time.strftime('%H:%M:%S', time.localtime(float(when)))
    return '%s (%s)' % (stamp, via) if via else stamp


def estimate_note(row):
    """'' when primitives are exact, else 'estimated from N of M geometry items'."""
    if not row.get('sampled'):
        return ''
    return 'estimated from {:,} of {:,} geometry items'.format(row['read'], row['geometry'])


def totals(rows):
    out = {'models': len(rows), 'items': 0, 'geometry': 0, 'primitives': 0, 'fragments': 0,
           'cache_bytes': 0, 'sampled': False}
    for row in rows:
        for key in ('items', 'geometry', 'primitives', 'fragments'):
            out[key] += int(row.get(key) or 0)
        out['cache_bytes'] += int(row.get('cache_size') or 0)
        out['sampled'] = out['sampled'] or bool(row.get('sampled'))
    return out


def table_rows(rows):
    """Rows for the output window and the workbook, in model order."""
    from namo import modelmgmt
    out = []
    for row in rows:
        out.append([row['name'], row['kind'], row['units'], modelmgmt.format_size(row.get('cache_size')),
                    modelmgmt.format_size(row.get('source_size')), row['items'], row['geometry'],
                    row['primitives'], row['fragments'], row['size'], row['arrived'], row['load'],
                    estimate_note(row)])
    return out


HEADERS = ['Model', 'Type', 'Units', 'File size', 'Source size', 'Items', 'Geometry items',
           'Primitives', 'Fragments', 'Extent', 'Arrived', 'Load time', 'Note']


# ---- API half -----------------------------------------------------------------------------------


def collect(doc=None, budget=DEFAULT_BUDGET, progress=None):
    """One row per model: {'name', 'kind', 'units', 'cache_size', 'source_size', 'items',
    'geometry', 'primitives', 'fragments', 'read', 'sampled', 'size', 'box', 'arrived',
    'load', 'load_seconds'}. progress(fraction, label) may raise a Cancelled."""
    from namo import hk_sessionstats, items as _items, modelmgmt
    from pynavis._api import Application
    document = doc if doc is not None else Application.ActiveDocument
    infos = modelmgmt.models_info(document)
    stale = dict((r['key'], r) for r in modelmgmt.stale_rows(document, infos))
    stamps = hk_sessionstats.stamps_for(document)
    doc_units = str(document.Units)
    rows = []
    total = len(infos)
    for number, info in enumerate(infos):
        label = '%s (%d of %d)' % (info['name'], number + 1, total)
        if progress is not None:
            progress(float(number) / max(1, total), label)
        sampler = PrimitiveSampler(budget)
        count = geometry = 0

        def read(item):
            g = item.Geometry
            return g.PrimitiveCount, g.FragmentCount

        for item in info['root'].DescendantsAndSelf:
            count += 1
            if item.HasGeometry:
                geometry += 1
                sampler.add(lambda: read(item))
            if progress is not None and count % 20000 == 0:
                progress(float(number) / max(1, total), '%s: %s items' % (label, '{:,}'.format(count)))
        primitives, fragments = sampler.total()
        try:
            box = _items.bbox(info['root'])
        except Exception:
            box = None
        entry = stamps.get(info['key'])
        file_row = stale.get(info['key']) or {}
        rows.append({'name': info['name'], 'kind': info['kind'], 'units': info['units'],
                     'cache_size': file_row.get('cache_size'), 'source_size': file_row.get('source_size'),
                     'items': count, 'geometry': geometry, 'primitives': primitives,
                     'fragments': fragments, 'read': sampler.read_count, 'sampled': sampler.sampled,
                     'box': [list(box[0]), list(box[1])] if box else None,
                     'size': size_text(box, doc_units), 'arrived': arrived_text(entry),
                     'load': load_text(entry),
                     'load_seconds': entry.get('load_seconds') if entry else None})
    if progress is not None:
        progress(1.0, 'Done')
    return rows


def write_workbook(path, rows, title=None):
    from namo import xlsx
    widths = [32, 8, 12, 12, 12, 12, 14, 14, 12, 26, 22, 12, 40]
    styles = [None, None, None, None, None, 'int', 'int', 'int', 'int', None, None, None, 'muted']
    sheet = {'name': 'Session stats', 'headers': HEADERS, 'rows': table_rows(rows),
             'widths': widths, 'styles': styles}
    if title:
        sheet['title'] = title
    return xlsx.write_simple(path, [sheet], title='Session stats')

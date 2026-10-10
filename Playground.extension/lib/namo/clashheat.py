# -*- coding: utf-8 -*-
"""Clash Heatmap: which elements clash most, coloured by count, plus density markers.

Counting: every chosen clash (by status) counts once for each element it names (side A
and side B; a clash of an element with itself counts once). Elements are what Clash
Detective calls them (the composite item, else the first object ancestor), the same
identity pynavis.clash.snapshot_results groups by.

Bands: up to five, light to strong blue (namo.colors.bands), with geometric lower
bounds from 1 to the highest count (max ** (i / 5), rounded, de-duplicated), so a few
hotspots never wash the rest into one colour: highest 100 gives 1-2, 3-5, 6-15, 16-39,
40-100. Painting is one undo step (namo.paint), optionally ghosting everything else.

Markers: clash centres binned into cubic cells (default 2 m, in document units), each
cell drawn with pynavis.overlay as a 3D cross sized by its count with the count as a
label, under tags 'playground-heat:<n>' (pynavis.overlay keeps ONE item per tag, so every
marker needs its own). Only the MAX_MARKERS densest cells are drawn: the overlay redraws
every item and label on every frame, and a few hundred crosses are already more than
anyone reads. The tags live in a session holder, so the next run (or Shift+Click) clears
them; the painted items are remembered there too so Shift+Click can put their colours
back.

Pure first (unit tested); the API half after.
"""

import math

from namo import colors, naming
from namo import overlayfix as _overlayfix

MAX_BANDS = 5
TAG_PREFIX = 'playground-heat'
HOLDER = 'clashheat'
TOP = 20
DEFAULT_CELL_M = 2.0
MAX_MARKERS = 150


# ---- pure ------------------------------------------------------------------------------------


def count_elements(rows, sides='both'):
    """{element key: clash count} over rows (item_a / item_b keys). sides: 'both',
    'a' or 'b'. Rows without a key on a side are skipped on that side."""
    counts = {}
    for row in rows:
        keys = []
        if sides in ('both', 'a') and row.get('item_a'):
            keys.append(row['item_a'])
        if sides in ('both', 'b') and row.get('item_b'):
            keys.append(row['item_b'])
        for key in set(keys):
            counts[key] = counts.get(key, 0) + 1
    return counts


def band_lows(max_count, bands=MAX_BANDS):
    """Ascending lower bounds of the bands for counts 1..max_count (see the module
    docstring)."""
    max_count = int(max_count or 0)
    if max_count <= 0:
        return []
    if max_count <= bands:
        return list(range(1, max_count + 1))
    lows = []
    for i in range(bands):
        value = int(math.floor(max_count ** (float(i) / bands) + 0.5))
        value = max(1, value)
        if not lows or value > lows[-1]:
            lows.append(value)
    return lows


def band_index(count, lows):
    """The band a count falls in (the last low it reaches), or None below the first."""
    index = None
    for i, low in enumerate(lows):
        if count >= low:
            index = i
    return index


def band_labels(lows, max_count):
    """'1', '2 to 3', ..., '16 to 39', '40 to 100'."""
    out = []
    for i, low in enumerate(lows):
        high = (lows[i + 1] - 1) if i + 1 < len(lows) else int(max_count)
        out.append(str(low) if high <= low else '%d to %d' % (low, high))
    return out


def band_colors(count):
    return colors.bands(count)


def legend(counts):
    """[{'label', 'hex', 'elements'}] for a counts dict, one per band."""
    if not counts:
        return []
    top = max(counts.values())
    lows = band_lows(top)
    palette = band_colors(len(lows))
    labels = band_labels(lows, top)
    tally = [0] * len(lows)
    for value in counts.values():
        index = band_index(value, lows)
        if index is not None:
            tally[index] += 1
    return [{'label': labels[i], 'hex': palette[i], 'elements': tally[i]} for i in range(len(lows))]


def ranked(counts, names=None, limit=TOP):
    """[(key, count)] most clashes first (ties by name, then key)."""
    names = names or {}
    order = sorted(counts, key=lambda k: (-counts[k], naming.natural_key(names.get(k, '')), str(k)))
    return [(k, counts[k]) for k in order[:limit]]


def cell_of(point, size):
    if point is None or not size or size <= 0:
        return None
    return tuple(int(math.floor(float(v) / size)) for v in point)


def bin_centres(points, size):
    """[{'cell', 'count', 'center' (mean of the points)}] for clash centres binned into
    cubes of `size` (model units), most crowded first (ties by cell)."""
    cells = {}
    for point in points:
        key = cell_of(point, size)
        if key is None:
            continue
        entry = cells.setdefault(key, [0, 0.0, 0.0, 0.0])
        entry[0] += 1
        for axis in range(3):
            entry[axis + 1] += float(point[axis])
    out = []
    for key in cells:
        count, sx, sy, sz = cells[key]
        out.append({'cell': key, 'count': count, 'center': (sx / count, sy / count, sz / count)})
    out.sort(key=lambda c: (-c['count'], c['cell']))
    return out


def marker_segments(center, count, max_count, size):
    """Three axis-aligned arms through center, half-length 0.15..0.5 of the cell size
    by count; returns (segments, label point)."""
    share = float(count) / max_count if max_count else 1.0
    arm = size * (0.15 + 0.35 * share)
    x, y, z = center
    segments = [((x - arm, y, z), (x + arm, y, z), False),
                ((x, y - arm, z), (x, y + arm, z), False),
                ((x, y, z - arm), (x, y, z + arm), False)]
    return segments, (x, y, z + arm)


def tags_for(count):
    return ['%s:%d' % (TAG_PREFIX, i + 1) for i in range(count)]


def summary_text(colored, bands, markers):
    parts = ['Coloured {:,} element{} in {} band{}'.format(colored, '' if colored == 1 else 's',
                                                        bands, '' if bands == 1 else 's')]
    if markers:
        parts.append('{:,} marker{}'.format(markers, '' if markers == 1 else 's'))
    return ', '.join(parts)


# ==== API half (Navisworks only; lazy imports) ============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _element(result, side):
    from namo import items as _items
    composite = result.CompositeItem1 if side == 'a' else result.CompositeItem2
    if composite is not None:
        return composite
    item = result.Item1 if side == 'a' else result.Item2
    return _items.object_of(item) if item is not None else None


def collect(entries, statuses):
    """(counts {key: n}, elements {key: ModelItem}, names {key: text}, centres [(x,y,z)])
    over the chosen statuses of namo.clashname.read_test entries."""
    wanted = set(str(s) for s in statuses or [])
    rows_all = []
    elements = {}
    names = {}
    centres = []
    for entry in entries:
        for row in entry['rows']:
            if str(row.get('status')) not in wanted:
                continue
            rows_all.append(row)
            if row.get('center') is not None:
                centres.append(row['center'])
            for side in ('a', 'b'):
                key = row.get('item_' + side)
                if key and key not in elements:
                    item = _element(entry['leaves'][row['id']], side)
                    if item is not None:
                        elements[key] = item
                        names[key] = row.get('item_%s_name' % side) or item.DisplayName or ''
    counts = count_elements(rows_all)
    counts = dict((k, v) for k, v in counts.items() if k in elements)
    return counts, elements, names, centres


def holder():
    from namo import session
    return session.holder(HOLDER)


def clear_markers():
    """Removes the markers of the last heatmap; returns how many there were."""
    from pynavis import overlay
    state = holder()
    tags = list(getattr(state, 'tags', None) or [])
    for tag in tags:
        overlay.clear(tag)
    state.tags = []
    if tags:
        _overlayfix.redraw()
    return len(tags)


def paint(counts, elements, ghost=False, doc=None):
    """Colours elements by band (and ghosts the rest) in ONE undo step; remembers what
    it touched for clear(). Returns the number of elements coloured."""
    from pynavis.viewpoints import transaction
    from namo import items as _items
    from namo import paint as _paint
    document = _doc(doc)
    if not counts:
        return 0
    top = max(counts.values())
    lows = band_lows(top)
    palette = band_colors(len(lows))
    groups = {}
    for key, value in counts.items():
        index = band_index(value, lows)
        if index is not None:
            groups.setdefault(index, []).append(elements[key])
    planned = [(groups[i], palette[i], None) for i in sorted(groups)]
    kept = [item for i in sorted(groups) for item in groups[i]]
    ghosted = []
    with transaction('Clash heatmap', document):
        count = _paint.apply(planned, document, 'Clash heatmap')
        if ghost and kept:
            ghosted = _items.complement(kept, document)
            if ghosted:
                _paint.apply([(ghosted, None, 0.85)], document, 'Clash heatmap')
    state = holder()
    state.painted = kept
    state.ghosted = ghosted
    state.doc_title = str(getattr(document, 'Title', '') or '')
    return count


def show(counts, elements, ghost=False, doc=None):
    """Clears the previous heatmap's colours and paints this one, as ONE undo step.
    Returns the number of elements coloured."""
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    with transaction('Clash heatmap', document):
        clear(document)
        return paint(counts, elements, ghost, document)


def densest(cells, limit=MAX_MARKERS):
    """The cells to draw: the `limit` most crowded (bin_centres order). Pure."""
    return list(cells[:max(0, int(limit))])


def draw_markers(centres, cell_size, limit=MAX_MARKERS):
    """Draws density markers for the `limit` densest cells; returns (markers drawn,
    overlay available). holder().cells is how many cells there were in all."""
    from pynavis import overlay
    cells = bin_centres(centres, cell_size)
    clear_markers()
    holder().cells = len(cells)
    cells = densest(cells, limit)
    if not cells:
        return 0, True
    top = cells[0]['count']
    tags = tags_for(len(cells))
    ok = True
    for tag, cell in zip(tags, cells):
        segments, label_at = marker_segments(cell['center'], cell['count'], top, cell_size)
        ok = overlay.add(tag, segments, label='{:,}'.format(cell['count']), label_at=label_at) and ok
    holder().tags = tags
    _overlayfix.redraw()
    return len(cells), bool(ok)


def clear(doc=None):
    """Shift+Click: removes markers and resets the colours the last heatmap applied
    (one undo step). Returns (markers removed, elements reset)."""
    from pynavis.viewpoints import transaction
    from namo import paint as _paint
    document = _doc(doc)
    state = holder()
    markers = clear_markers()
    items_list = list(getattr(state, 'painted', None) or []) + list(getattr(state, 'ghosted', None) or [])
    if str(getattr(state, 'doc_title', '') or '') != str(getattr(document, 'Title', '') or ''):
        items_list = []            # painted in a model that is no longer open
    state.painted = []
    state.ghosted = []
    reset = 0
    if items_list:
        try:
            with transaction('Clear clash heatmap', document):
                reset = _paint.reset(items_list, document, 'Clear clash heatmap')
        except Exception:
            reset = 0              # items of a model that was closed or reloaded since
    return markers, reset


def cells_found():
    """How many marker cells the last draw_markers found (it draws the densest)."""
    try:
        return int(getattr(holder(), 'cells', 0) or 0)
    except Exception:
        return 0


def report(counts, elements, names, legend_rows, markers, title, doc=None):
    """Writes the legend and the top hotspots to the output window."""
    from pynavis import output
    from namo import items as _items
    from namo.htmlreport import escape
    output.set_title('Clash Heatmap')
    output.print_md('# %s' % title)
    swatches = ['<table class="pynavis"><tr><th>Clashes per element</th><th></th>'
                '<th class="num">Elements</th></tr>']
    for row in legend_rows:
        swatches.append('<tr><td>%s</td><td><span style="display:inline-block;width:28px;height:12px;'
                        'background:#%s;border:1px solid var(--line)"></span></td><td class="num">%s</td></tr>'
                        % (escape(row['label']), row['hex'], '{:,}'.format(row['elements'])))
    swatches.append('</table>')
    output.print_html(''.join(swatches))
    output.print_md('## Top %d hotspots' % min(TOP, len(counts)))
    lines = ['<table class="pynavis"><tr><th class="num">Clashes</th><th>Element</th><th>Model</th>'
             '<th>Category</th><th></th></tr>']
    for key, value in ranked(counts, names):
        item = elements[key]
        try:
            model = _items.model_name(item)
            category = _items.category(item)
        except Exception:
            model, category = '', ''
        lines.append('<tr><td class="num">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            '{:,}'.format(value), escape(names.get(key, '')), escape(model), escape(category),
            output.element_link(item, 'Show')))
    lines.append('</table>')
    output.print_html(''.join(lines))
    if markers:
        found = cells_found()
        which = 'The %s densest of %s spots are marked in the view' % (
            '{:,}'.format(markers), '{:,}'.format(found)) if found > markers else \
            '%s marked in the view' % ('{:,} spots are'.format(markers) if markers != 1
                                        else '1 spot is')
        output.print_md('%s, each with its clash count. Shift+Click Clash Heatmap to clear the '
                        'colours and markers.' % which)
    else:
        output.print_md('Shift+Click Clash Heatmap to clear the colours.')

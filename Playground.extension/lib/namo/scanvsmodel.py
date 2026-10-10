# -*- coding: utf-8 -*-
"""Scan vs Model: how close the scanned existing conditions come to the design.

One clearance test: side A is the design (surfaces), side B the scan models with only
POINTS enabled (ClashSelection.PrimitiveTypes = Points), tolerance = the largest
deviation band. Every result pairs a design element with a scan; its Distance is how
near the scan points come (negative: points inside the element). Per design element
the closest result decides its band:

    Intrudes           distance < 0        (scan points inside the element)
    Within 25 mm       0 .. band 1
    25 to 50 mm        band 1 .. band 2    ...

Elements are coloured by band (one undo step, namo.paint), optionally with everything
else ghosted, and the output window lists counts per band and the closest elements.

UNVERIFIED in-app (see dev/notes/clash_setup_results.md): that Clash Detective reports
point-to-surface clearances through the API exactly as in its UI, which item of a scan
a result names, and the sign of Distance for points inside a solid.

Pure first (unit tested), API half after.
"""

import re

from namo import colors, units

SCAN_EXTENSIONS = ('.rcp', '.rcs', '.e57', '.pts', '.ptx', '.ptg', '.las', '.laz', '.xyz',
                   '.asc', '.pcg', '.fls', '.zfs', '.rds')
DEFAULT_BANDS_M = (0.025, 0.05, 0.1)
DEFAULT_TEST_NAME = 'Scan vs Model'
INTRUDES = 'Intrudes'
INTRUDE_COLOR = '8E1B1B'
BAND_STOPS = ['E15759', 'F28E2B', 'EDC948']


# ---- pure -----------------------------------------------------------------------------------


def looks_like_scan(name):
    """True for a model file name with a point-cloud extension."""
    text = str(name or '').strip().lower()
    return any(text.endswith(ext) for ext in SCAN_EXTENSIONS)


def default_bands_text(doc_units):
    """'25, 50, 100 mm' in a metric document, '1", 2", 4"' in a feet-and-inches one."""
    if units.is_imperial(doc_units):
        return '1", 2", 4"'
    return '25, 50, 100 mm'


_TRAILING_UNIT = re.compile(r'(mm|cm|m|ft|in|"|\')\s*$', re.IGNORECASE)


def parse_bands(text, doc_units):
    """Band limits in DOCUMENT units, ascending, from text like '25, 50, 100 mm'
    (a unit at the end applies to bare numbers), '1", 2", 4"' or '0.025, 0.05 m'.
    Raises ValueError with a sentence when it does not read."""
    raw = str(text or '').strip()
    if not raw:
        raise ValueError('Enter at least one band, like 25, 50, 100 mm.')
    parts = [p.strip() for p in re.split(r'[;,]', raw) if p.strip()]
    suffix = None
    match = _TRAILING_UNIT.search(parts[-1])
    if match:
        suffix = match.group(1)
    out = []
    for part in parts:
        candidate = part
        if suffix and units.parse_number(part) is not None:
            candidate = part + suffix
        value = units.parse_length(candidate, doc_units)
        if value is None:
            raise ValueError('"%s" is not a length; write bands like 25, 50, 100 mm.' % part)
        if value <= 0:
            raise ValueError('Bands must be greater than zero.')
        out.append(float(value))
    out = sorted(set(round(v, 12) for v in out))
    if len(out) > 8:
        raise ValueError('Use at most 8 bands.')
    return out


def band_labels(bands, doc_units):
    """['Intrudes', 'Within 25 mm', '25 to 50 mm', ...] for bands in document units."""
    from namo import clashset_tests as defs
    labels = [INTRUDES]
    previous = None
    suffix = '' if units.is_imperial(doc_units) else ' ' + units.doc_unit_symbol(doc_units)
    for limit in bands:
        text = defs.length_text(limit, doc_units)
        if previous is None:
            labels.append('Within %s' % text)
        else:
            low = defs.length_text(previous, doc_units)
            if suffix and low.endswith(suffix):
                low = low[:-len(suffix)]
            labels.append('%s to %s' % (low, text))
        previous = limit
    return labels


def band_colors(count):
    """Colours for [Intrudes] + count bands: dark red, then red to yellow."""
    out = [INTRUDE_COLOR]
    if count <= 0:
        return out
    if count == 1:
        return out + [BAND_STOPS[0]]
    for index in range(count):
        out.append(colors.ramp(BAND_STOPS, float(index) / (count - 1)))
    return out


def band_of(distance, bands):
    """Band index for a distance in document units: 0 = intrudes (< 0), i = within
    band i (limit inclusive), None beyond the largest band."""
    if distance is None:
        return None
    if distance < 0:
        return 0
    for index, limit in enumerate(bands):
        if distance <= limit + 1e-9 * max(1.0, abs(limit)):
            return index + 1
    return None


def summarize(hits, bands):
    """Per design element: hits [(element_key, name, distance)] -> {'elements': [{'key',
    'name', 'distance' (closest), 'hits', 'band'}] closest first (ties by name),
    'counts': [elements per band, Intrudes first], 'beyond': elements past every band}."""
    best = {}
    order = []
    for key, name, distance in hits:
        if key not in best:
            best[key] = {'key': key, 'name': name or '', 'distance': distance, 'hits': 0}
            order.append(key)
        entry = best[key]
        entry['hits'] += 1
        if distance is not None and (entry['distance'] is None or distance < entry['distance']):
            entry['distance'] = distance
    elements = []
    counts = [0] * (len(bands) + 1)
    beyond = 0
    for key in order:
        entry = best[key]
        entry['band'] = band_of(entry['distance'], bands)
        if entry['band'] is None:
            beyond += 1
        else:
            counts[entry['band']] += 1
        elements.append(entry)
    elements.sort(key=lambda e: (e['distance'] if e['distance'] is not None else float('inf'),
                                 e['name'].lower()))
    return {'elements': elements, 'counts': counts, 'beyond': beyond}


def scan_suggestions(models):
    """Indexes of models that look like scans: [{'name', 'points'}] -> [index]."""
    return [i for i, m in enumerate(models) if m.get('points') or looks_like_scan(m.get('name'))]


def validate_choice(scans, design_models):
    """A sentence when the chosen scans and design models cannot make a test, else None."""
    if not scans:
        return 'Choose at least one scan model.'
    overlap = set(scans) & set(design_models or [])
    if overlap:
        return 'A model cannot be both a scan and the design.'
    return None


# ==== API half (Navisworks only; lazy imports) =============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def has_points(root, budget=60):
    """True when one of the first `budget` geometry items under root draws points."""
    from pynavis._api import Api
    from namo import items as _items
    try:
        points = int(Api.PrimitiveTypes.Points)
    except Exception:
        return False
    for item in _items.geometry_items([root], budget=budget):
        try:
            if int(item.Geometry.PrimitiveTypes) & points:
                return True
        except Exception:
            continue
    return False


def models_info(doc=None):
    """[{'index', 'name', 'points', 'root'}] for every model, with the point probe."""
    from namo import items as _items
    out = []
    for model in _items.models(doc):
        out.append({'index': model['index'], 'name': model['name'] or 'Model %d' % (model['index'] + 1),
                    'points': looks_like_scan(model['name']) or has_points(model['root']),
                    'root': model['root']})
    return out


def definition(name, scan_names, design_side, bands, doc_units):
    """The clearance test definition (tolerance = the largest band, in metres)."""
    from namo import clashset_tests as defs
    scan_side = defs.new_side([{'kind': 'model', 'name': n} for n in scan_names], ['points'])
    return defs.new_definition(name, 'clearance', units.to_meters(max(bands), doc_units),
                               design_side, scan_side)


def build_and_run(test_definition, doc=None):
    """Creates (or updates) the test in one undo step and runs it. Returns
    (live test, outcome). Raises ValueError with a sentence when a side is missing."""
    from pynavis.viewpoints import transaction
    from namo import clashset_tests as defs
    document = _doc(doc)
    resolved_a = defs.resolve_side(test_definition['a'], document)
    resolved_b = defs.resolve_side(test_definition['b'], document)
    problems = resolved_a['missing'] + resolved_b['missing']
    if problems:
        raise ValueError(problems[0])
    with transaction('Scan vs Model', document):
        outcome, live = defs.write_test(test_definition, resolved_a, resolved_b, 'update', document)
    if live is None:
        raise ValueError('The clash test could not be created.')
    if not points_only(live.SelectionB):
        # Without points on the scan side the test would compare surfaces with surfaces
        # and every band below would be wrong: stop here and say what to do.
        raise ValueError('Navisworks did not switch the scan side of "%s" to points. In Clash '
                         'Detective, tick only Points for Selection B of that test and run it '
                         'there.' % live.DisplayName)
    guid = str(live.Guid)
    defs.run_tests([live], document)
    data = defs._clash().get_clash(document).TestsData
    fresh = defs._by_guid(data, guid)
    return (fresh if fresh is not None else live), outcome


def points_only(clash_selection):
    """True when a live ClashSelection has Points switched on and Surfaces off."""
    from pynavis._api import Api
    from namo import clashset_tests as defs
    try:
        keys = defs.decode_primitives(clash_selection.PrimitiveTypes, defs._primitive_members(Api))
    except Exception:
        return False
    return 'points' in keys and 'triangles' not in keys


def collect(test, doc=None, progress=None):
    """(hits [(key, name, distance)], items {key: ModelItem}) for the design side of
    every result; distance in document units. progress(fraction, label)."""
    from namo import clashdata
    from namo import items as _items
    results = clashdata.results(test)
    hits = []
    elements = {}
    keys = {}
    total = len(results) or 1
    step = max(1, len(results) // 50)
    for index, result in enumerate(results):
        if progress is not None and index % step == 0:
            if progress(float(index) / total, 'Reading %s of %s results' % (
                    '{:,}'.format(index), '{:,}'.format(len(results)))) == False:  # noqa: E712
                raise clashdata.Cancelled()
        item = result.CompositeItem1
        if item is None:
            item = result.Item1
        if item is None:
            continue
        element = _items.object_of(item)
        key = keys.get(element)
        if key is None:
            key = str(element.InstanceGuid)
            if key == '00000000-0000-0000-0000-000000000000':
                key = 'h:%d' % element.InstanceHashCode
            keys[element] = key
            elements[key] = element
        hits.append((key, element.DisplayName or item.DisplayName, float(result.Distance)))
    return hits, elements


def paint(summary, elements, ghost=False, doc=None):
    """Colours the elements by band in one undo step; ghosts the rest when asked.
    Returns how many elements were coloured."""
    from pynavis.viewpoints import transaction
    from namo import paint as _paint
    document = _doc(doc)
    groups = {}
    for entry in summary['elements']:
        if entry['band'] is None:
            continue
        groups.setdefault(entry['band'], []).append(elements[entry['key']])
    palette = band_colors(len(summary['counts']) - 1)
    planned = [(groups[band], palette[band], None) for band in sorted(groups)]
    if not planned:
        return 0
    with transaction('Scan vs Model colours', document):
        count = _paint.apply(planned, document, 'Scan vs Model colours')
        if ghost:
            kept = [item for band in sorted(groups) for item in groups[band]]
            _paint.ghost(kept, doc=document, name='Scan vs Model colours')
    return count

# -*- coding: utf-8 -*-
"""Quantity takeoff: measures from properties (and geometry), grouping, zones, workbooks.

Pure half (tested on both engines):
  * choose_pairs: which (category, property) pairs carry length, area, volume and weight,
    picked from a sample of the objects' property NAMES (Revit 'Element > Volume', IFC
    'Qto_WallBaseQuantities > NetVolume', 'BaseQuantities > GrossArea' ...), so each
    object then costs a few direct lookups instead of a walk over all its properties.
  * to_si: a property value in SI (m, m2, m3, kg): display strings with units through
    namo.units.parse_quantity ("12' - 6\"", "3.20 m2", "250 SF"); bare numbers are in the
    MODEL's units (the item's own Model.Units, for DoubleLength/Area/Volume values) and
    bare weights in kg for metric models, lb for imperial ones.
  * aggregate: groups by one or two keys with subtotals and a total, counting where each
    value came from (property, geometric, bounding box) and how many objects had none.
  * zones: level bands, zone boxes (centre inside, ties by largest overlap), fixed tiles,
    and grid bays rebuilt from grid intersections (lines grouped into families by
    direction, ordered by offset): 'A-B / 3-4'.
  * the workbooks (namo.xlsx) and the table rows the result windows show.
API half: collect() walks the scope once, reads groups and measures, measures geometry
for missing volumes/lengths when asked (budgeted, flagged 'geometric'), assigns zones.
"""

import math

from namo import naming, units

MEASURES = ['count', 'length', 'area', 'volume', 'weight', 'surface']
LABELS = {'count': 'Count', 'length': 'Length', 'area': 'Area', 'volume': 'Volume',
          'weight': 'Weight', 'surface': 'Surface area'}
KIND = {'length': 'length', 'area': 'area', 'volume': 'volume', 'weight': 'mass', 'surface': 'area'}
DIMENSION = {'length': 1, 'area': 2, 'volume': 3, 'surface': 2}
PROPERTY_MEASURES = ('length', 'area', 'volume', 'weight')
NO_VALUE = '(no value)'
NO_ZONE = '(no zone)'
SPECIAL_GROUPS = [('@category', 'Category'), ('@model', 'Model file')]
GEOMETRY_BUDGET = 2000          # objects measured from triangles per run
TRIANGLE_BUDGET = 200000        # triangles per object

NAMES = {
    'length': ['length', 'cut length', 'netlength', 'net length', 'grosslength', 'gross length',
               'overall length'],
    'area': ['area', 'netarea', 'net area', 'grossarea', 'gross area', 'netsidearea', 'net side area',
             'grosssidearea', 'gross side area', 'netfootprintarea', 'net footprint area',
             'grossfootprintarea', 'gross footprint area'],
    'volume': ['volume', 'netvolume', 'net volume', 'grossvolume', 'gross volume'],
    'weight': ['weight', 'mass', 'netweight', 'net weight', 'grossweight', 'gross weight',
               'netmass', 'grossmass'],
}

IMPERIAL = ('Feet', 'Inches', 'Yards', 'Miles', 'Mils', 'Microinches')


def _norm(text):
    return ' '.join(str(text or '').lower().split())


def category_rank(category):
    """Which tab to trust first: Element, then quantity sets, then type tabs, then any."""
    c = _norm(category)
    if c == 'element':
        return 0
    if 'quantit' in c or c.startswith('qto') or 'dimension' in c:
        return 1
    if c in ('revit type', 'element type', 'type'):
        return 2
    return 3


def choose_pairs(sampled, measures=PROPERTY_MEASURES):
    """{measure: [(category, property)]} best first, from items.sample_properties rows
    [(category, property, count)]."""
    out = {}
    for measure in measures:
        if measure not in NAMES:
            continue
        names = NAMES[measure]
        found = []
        for category, prop, count in sampled:
            key = _norm(prop)
            if key in names:
                found.append((names.index(key), category_rank(category), -int(count),
                              str(category), str(prop)))
        found.sort()
        out[measure] = [(f[3], f[4]) for f in found]
    return out


def unit_factor(model_units, dimension):
    """SI per model unit to the given power (1 length, 2 area, 3 volume)."""
    try:
        return units.to_meters(1.0, model_units) ** dimension
    except (ValueError, TypeError):
        return 1.0


def is_imperial(model_units):
    return str(model_units) in IMPERIAL


def to_si(measure, value, model_units):
    """A property value as SI (m, m2, m3, kg), or None when it does not read as one."""
    if value is None or isinstance(value, bool):
        return None
    kind = KIND[measure]
    number = None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        parsed = units.parse_quantity(str(value))
        if parsed is None:
            return None
        amount, unit, found_kind = parsed
        if unit is not None:
            if found_kind != kind:
                return None
            return units.convert(amount, unit, units.BASE[kind])
        number = float(amount)
    if math.isnan(number) or math.isinf(number):
        return None
    if kind == 'mass':
        return number * (0.45359237 if is_imperial(model_units) else 1.0)
    return number * unit_factor(model_units, DIMENSION[measure])


def group_text(value):
    """A group key as text: None '(no value)', 3.0 '3', True 'Yes'."""
    from namo import rules
    if value is None:
        return NO_VALUE
    text = rules.text_of(value)
    return text if text.strip() else NO_VALUE


def _key(values):
    return tuple(naming.natural_key(v) for v in values)


def _empty_row(kind, keys, measures):
    return {'kind': kind, 'keys': list(keys), 'count': 0, 'values': dict((m, None) for m in measures),
            'missing': dict((m, 0) for m in measures), 'sources': dict((m, {}) for m in measures),
            'members': []}


def _add(row, record, index, measures):
    row['count'] += 1
    row['members'].append(index)
    for measure in measures:
        if measure == 'count':
            continue
        value = record['measures'].get(measure)
        if value is None:
            row['missing'][measure] += 1
            continue
        row['values'][measure] = (row['values'][measure] or 0.0) + value
        source = record.get('sources', {}).get(measure, 'property')
        row['sources'][measure][source] = row['sources'][measure].get(source, 0) + 1


def aggregate(records, levels=1, measures=MEASURES):
    """Rows for a takeoff table: 'group' rows (natural order), a 'subtotal' after each
    first-level key when levels == 2, and a 'total' row last."""
    measures = [m for m in measures if m != 'count']
    groups = {}
    for index, record in enumerate(records):
        keys = tuple((list(record['groups']) + [NO_VALUE, NO_VALUE])[:levels])
        row = groups.get(keys)
        if row is None:
            row = groups[keys] = _empty_row('group', keys, measures)
        _add(row, record, index, measures)
    ordered = sorted(groups.values(), key=lambda r: _key(r['keys']))
    out = []
    total = _empty_row('total', ['Total'] + [''] * (levels - 1), measures)
    if levels == 2:
        current = None
        sub = None
        for row in ordered:
            if current is None or row['keys'][0] != current:
                if sub is not None:
                    out.append(sub)
                current = row['keys'][0]
                sub = _empty_row('subtotal', [current, 'Subtotal'], measures)
            out.append(row)
            for index in row['members']:
                _add(sub, records[index], index, measures)
        if sub is not None:
            out.append(sub)
    else:
        out.extend(ordered)
    for index, record in enumerate(records):
        _add(total, record, index, measures)
    out.append(total)
    return out


def display_units(report_units, doc_units):
    """{'length', 'area', 'volume', 'surface', 'weight'} display units for a report."""
    chosen = units.report_units_for(report_units or 'auto', doc_units)
    imperial = chosen['area'] == 'ft2'
    chosen['surface'] = chosen['area']
    chosen['weight'] = 'lb' if imperial else 'kg'
    return chosen


def from_si(measure, value, unit_set):
    if value is None:
        return None
    if measure == 'count':
        return value
    return units.convert(value, units.BASE[KIND[measure]], unit_set[measure])


def header(measure, unit_set):
    if measure == 'count':
        return 'Count'
    return '%s (%s)' % (LABELS[measure], units.symbol(unit_set[measure]))


def source_note(row, measure):
    """'12 geometric' style note for a row's measure, '' when all came from properties."""
    parts = []
    sources = row['sources'].get(measure) or {}
    for source in ('geometric', 'bbox'):
        if sources.get(source):
            parts.append('%s %s' % ('{:,}'.format(sources[source]),
                                    'geometric' if source == 'geometric' else 'from bounding box'))
    if row['missing'].get(measure):
        parts.append('%s without' % '{:,}'.format(row['missing'][measure]))
    return ', '.join(parts)


def table_rows(rows, measures, unit_set, group_titles):
    """[{'cells', 'value'}] for ui tables: group keys, count and measures (rounded to 3
    decimals), then a Notes cell."""
    out = []
    for index, row in enumerate(rows):
        cells = list(row['keys'])
        for measure in measures:
            if measure == 'count':
                cells.append(row['count'])
                continue
            value = from_si(measure, row['values'].get(measure), unit_set)
            cells.append(round(value, 3) if value is not None else '')
        notes = '; '.join('%s: %s' % (LABELS[m], source_note(row, m)) for m in measures
                          if m != 'count' and source_note(row, m))
        cells.append(notes)
        out.append({'cells': cells, 'value': index})
    return out


def table_headers(measures, unit_set, group_titles):
    return list(group_titles) + [header(m, unit_set) for m in measures] + ['Notes']


# ---- solids from triangles --------------------------------------------------------------------

def solid_measure(tris):
    """{'volume', 'centroid'} of the solid a triangle mesh encloses (model units), or None
    when the mesh does not enclose one. The geometric closure test, which accepts a
    watertight solid whose faces do not share vertices: it started here and now lives in
    namo.mesh.solid_measure, where every mesh caller gets it."""
    from namo import mesh
    return mesh.solid_measure(tris)


# ---- zones -----------------------------------------------------------------------------------


def level_bands(levels):
    """Bands from [(name, elevation)]: below the first level, one per level up to the
    next, the last level and above. [{'name', 'zmin', 'zmax'}] bottom up."""
    ordered = sorted(levels, key=lambda pair: pair[1])
    if not ordered:
        return []
    bands = [{'name': 'Below %s' % ordered[0][0], 'zmin': -float('inf'), 'zmax': ordered[0][1]}]
    for index, (name, elevation) in enumerate(ordered):
        top = ordered[index + 1][1] if index + 1 < len(ordered) else float('inf')
        bands.append({'name': name, 'zmin': elevation, 'zmax': top})
    return bands


def assign_band(z, bands):
    for band in bands:
        if band['zmin'] <= z < band['zmax']:
            return band['name']
    return NO_ZONE


def _overlap(a, b):
    total = 1.0
    for axis in range(3):
        low = max(a[0][axis], b[0][axis])
        high = min(a[1][axis], b[1][axis])
        if high <= low:
            return 0.0
        total *= high - low
    return total


def _inside(point, box):
    return all(box[0][axis] <= point[axis] <= box[1][axis] for axis in range(3))


def assign_box(obj_box, zones):
    """The zone whose box holds obj_box's centre; ties go to the largest overlap; a centre
    in no zone falls back to the zone it overlaps most; else NO_ZONE."""
    center = tuple((obj_box[0][a] + obj_box[1][a]) / 2.0 for a in range(3))
    inside = [z for z in zones if _inside(center, z['box'])]
    pool = inside if inside else zones
    best = None
    for zone in pool:
        amount = _overlap(obj_box, zone['box'])
        if inside or amount > 0.0:
            score = (amount, -zones.index(zone))
            if best is None or score > best[0]:
                best = (score, zone)
    return best[1]['name'] if best is not None else NO_ZONE


def unique_names(names):
    """names with repeats made unique: 'Room', 'Room (2)'."""
    out = []
    for name in names:
        out.append(naming.unique(name or 'Zone', out))
    return out


def tile_name(ix, iy, nx=None, ny=None):
    width_x = max(2, len(str(nx or 0)))
    width_y = max(2, len(str(ny or 0)))
    return 'X%0*d Y%0*d' % (width_x, ix + 1, width_y, iy + 1)


def assign_tile(point, origin, spacing, counts=(None, None)):
    if spacing <= 0:
        raise ValueError('The tile size must be more than zero.')
    ix = int(math.floor((point[0] - origin[0]) / spacing))
    iy = int(math.floor((point[1] - origin[1]) / spacing))
    return tile_name(max(0, ix), max(0, iy), counts[0], counts[1])


def _angle(direction):
    angle = math.degrees(math.atan2(direction[1], direction[0])) % 180.0
    return angle


def grid_families(intersections, tolerance_deg=5.0):
    """Grid line families from intersections [{'line1', 'line2', 'dir1', 'dir2', 'pos'}]
    (directions and position in plan, model units).

    Returns [{'normal': (nx, ny), 'lines': [(offset, name)] sorted by offset}] with the
    families ordered by their first line name (letters before numbers)."""
    lines = {}
    for hit in intersections:
        for name, direction in ((hit['line1'], hit['dir1']), (hit['line2'], hit['dir2'])):
            if not name:
                continue
            entry = lines.setdefault(name, {'dirs': [], 'points': []})
            entry['dirs'].append(direction)
            entry['points'].append(hit['pos'])
    families = []
    for name in sorted(lines, key=naming.natural_key):
        entry = lines[name]
        dx, dy = entry['dirs'][0][0], entry['dirs'][0][1]
        size = math.hypot(dx, dy) or 1.0
        dx, dy = dx / size, dy / size
        angle = _angle((dx, dy))
        family = None
        for candidate in families:
            diff = abs(candidate['angle'] - angle) % 180.0
            if min(diff, 180.0 - diff) <= tolerance_deg:
                family = candidate
                break
        if family is None:
            radians = math.radians(angle)
            family = {'angle': angle, 'normal': (-math.sin(radians), math.cos(radians)), 'names': []}
            families.append(family)
        family['names'].append(name)
    out = []
    for family in families:
        nx, ny = family['normal']
        placed = []
        for name in family['names']:
            points = lines[name]['points']
            offset = sum(p[0] * nx + p[1] * ny for p in points) / float(len(points))
            placed.append((offset, name))
        placed.sort()
        if len(placed) > 1 and naming.natural_key(placed[0][1]) > naming.natural_key(placed[-1][1]):
            # Point the normal the way the names count up, so bays read 'A-B', not 'B-A'.
            nx, ny = -nx, -ny
            placed = sorted((-offset, name) for offset, name in placed)
        out.append({'normal': (nx, ny), 'lines': placed})
    out.sort(key=lambda f: (0 if f['lines'] and not f['lines'][0][1][:1].isdigit() else 1,
                            naming.natural_key(f['lines'][0][1]) if f['lines'] else ()))
    return out


def bay_of(point, family):
    """'A-B' between two lines of a family, '< A' before the first, '> F' after the last."""
    nx, ny = family['normal']
    offset = point[0] * nx + point[1] * ny
    lines = family['lines']
    if not lines:
        return ''
    if offset < lines[0][0]:
        return '< %s' % lines[0][1]
    for index in range(len(lines) - 1):
        if lines[index][0] <= offset < lines[index + 1][0]:
            return '%s-%s' % (lines[index][1], lines[index + 1][1])
    return '> %s' % lines[-1][1]


def grid_bay(point, families):
    """'A-B / 3-4' for a plan point."""
    parts = [bay_of(point, f) for f in families]
    parts = [p for p in parts if p]
    return ' / '.join(parts) if parts else NO_ZONE


def pivot(records, measure='count', top=30):
    """(zones, groups, matrix, zone_totals, group_totals) of one measure (SI) by zone and
    first group key. Past `top` groups the smallest fold into 'Other'."""
    totals = {}
    zones = set()
    for record in records:
        group = record['groups'][0] if record['groups'] else NO_VALUE
        value = 1.0 if measure == 'count' else record['measures'].get(measure)
        zones.add(record.get('zone') or NO_ZONE)
        totals[group] = totals.get(group, 0.0) + (value or 0.0)
    ranked = sorted(totals, key=lambda g: (-totals[g], naming.natural_key(g)))
    kept = set(ranked[:top])
    groups = sorted(kept, key=naming.natural_key)
    if len(ranked) > top:
        groups.append('Other')
    zone_list = sorted(zones, key=naming.natural_key)
    matrix = dict(((z, g), 0.0) for z in zone_list for g in groups)
    for record in records:
        group = record['groups'][0] if record['groups'] else NO_VALUE
        group = group if group in kept else 'Other'
        value = 1.0 if measure == 'count' else record['measures'].get(measure)
        if value is None:
            continue
        cell = (record.get('zone') or NO_ZONE, group)
        matrix[cell] = matrix.get(cell, 0.0) + value
    zone_totals = dict((z, sum(matrix[(z, g)] for g in groups)) for z in zone_list)
    group_totals = dict((g, sum(matrix[(z, g)] for z in zone_list)) for g in groups)
    return zone_list, groups, matrix, zone_totals, group_totals


# ---- workbooks ---------------------------------------------------------------------------------


def _number_style(measure):
    return 'int' if measure == 'count' else 'num2'


def _write_table(ws, rows, measures, unit_set, group_titles, wb):
    specs = [(title, 28, None) for title in group_titles]
    specs += [(header(m, unit_set), 14, _number_style(m)) for m in measures]
    specs.append(('Notes', 40, None))
    ws.columns(specs)
    width = len(specs)
    for row in rows:
        cells = [key if key != '' else None for key in row['keys']]
        for measure in measures:
            if measure == 'count':
                cells.append(row['count'])
            else:
                cells.append(from_si(measure, row['values'].get(measure), unit_set))
        cells.append('; '.join('%s: %s' % (LABELS[m], source_note(row, m)) for m in measures
                               if m != 'count' and source_note(row, m)))
        if row['kind'] == 'group':
            ws.row(cells)
        else:
            styles = ['bold'] * len(group_titles) + [
                'qty_bold_int' if m == 'count' else 'qty_bold_num' for m in measures] + ['bold']
            ws.row(cells, styles=styles)
    ws.autofilter(last_row=ws.next_row - 2 if len(rows) > 1 else None)
    return width


def _styles(wb):
    if not wb.has_style('qty_bold_int'):
        wb.style('qty_bold_int', bold=True, num_format='#,##0', border='top')
        wb.style('qty_bold_num', bold=True, num_format='#,##0.00', border='top')


def _notes_sheet(wb, notes, pairs_used):
    ws = wb.sheet('Notes')
    ws.title('How these quantities were measured', span=2)
    ws.columns([('Item', 34, None), ('Detail', 90, 'wrap')], freeze=False)
    for label, text in notes:
        ws.row([label, text])
    for measure in PROPERTY_MEASURES:
        found = pairs_used.get(measure) or []
        if found:
            ws.row(['%s read from' % LABELS[measure], ', '.join('%s > %s' % p for p in found)])
    return ws


def write_quick_xlsx(path, title, subtitle, rows, measures, unit_set, group_titles, notes,
                     pairs_used=None, objects=None, author=None):
    """Quick Takeoff workbook: Takeoff (groups, subtotals, total), Objects (one row per
    object when given) and Notes. Returns path."""
    from namo import xlsx
    wb = xlsx.Workbook(title=title, author=author)
    _styles(wb)
    ws = wb.sheet('Takeoff')
    span = len(group_titles) + len(measures) + 1
    ws.title(title, span=span)
    ws.subtitle(subtitle, span=span)
    _write_table(ws, rows, measures, unit_set, group_titles, wb)
    if objects:
        sheet = wb.sheet('Objects')
        specs = [('Object', 34, None)] + [(t, 24, None) for t in group_titles]
        specs += [(header(m, unit_set), 14, 'num2') for m in measures if m != 'count']
        specs += [('Source', 24, None)]
        sheet.columns(specs)
        for record in objects:
            cells = [record.get('name', '')] + list(record['groups'])[:len(group_titles)]
            for measure in measures:
                if measure != 'count':
                    cells.append(from_si(measure, record['measures'].get(measure), unit_set))
            sources = sorted(set(v for v in record.get('sources', {}).values() if v != 'property'))
            cells.append(', '.join(sources))
            sheet.row(cells)
        sheet.autofilter()
    _notes_sheet(wb, notes, pairs_used or {})
    return wb.save(path)


def write_zone_xlsx(path, title, subtitle, records, measures, unit_set, group_titles, notes,
                    pivot_measure='count', pairs_used=None, author=None, max_zone_sheets=60):
    """Zone Takeoff workbook: Pivot (zones by first group, one measure), Zones (every zone
    with every measure), one sheet per zone (up to max_zone_sheets), Notes. Returns
    (path, zone sheets written, zones)."""
    from namo import xlsx
    wb = xlsx.Workbook(title=title, author=author)
    _styles(wb)
    zones, groups, matrix, zone_totals, group_totals = pivot(records, pivot_measure)
    ws = wb.sheet('Pivot')
    span = len(groups) + 2
    ws.title('%s: %s by zone' % (title, LABELS[pivot_measure].lower()), span=min(span, 12))
    ws.subtitle('%s; %s' % (subtitle, header(pivot_measure, unit_set)), span=min(span, 12))
    ws.columns([('Zone', 26, None)] + [(g, 14, _number_style(pivot_measure)) for g in groups] +
               [('Total', 14, _number_style(pivot_measure))])
    for zone in zones:
        values = [from_si(pivot_measure, matrix[(zone, g)], unit_set) if pivot_measure != 'count'
                  else int(matrix[(zone, g)]) for g in groups]
        total = zone_totals[zone]
        ws.row([zone] + values + [from_si(pivot_measure, total, unit_set) if pivot_measure != 'count'
                                  else int(total)])
    totals = [from_si(pivot_measure, group_totals[g], unit_set) if pivot_measure != 'count'
              else int(group_totals[g]) for g in groups]
    grand = sum(group_totals.values())
    ws.row(['Total'] + totals + [from_si(pivot_measure, grand, unit_set) if pivot_measure != 'count'
                                 else int(grand)],
           styles=['bold'] + ['qty_bold_int' if pivot_measure == 'count' else 'qty_bold_num'] * (len(groups) + 1))
    by_zone = {}
    for record in records:
        by_zone.setdefault(record.get('zone') or NO_ZONE, []).append(record)
    summary = wb.sheet('Zones')
    summary.title('Every zone', span=len(measures) + 2)
    zone_rows = aggregate([dict(r, groups=[r.get('zone') or NO_ZONE]) for r in records], 1, measures)
    _write_table(summary, zone_rows, measures, unit_set, ['Zone'], wb)
    written = 0
    for zone in zones:
        if written >= max_zone_sheets:
            break
        sheet = wb.sheet(zone)
        sheet.title(zone, span=len(group_titles) + len(measures) + 1)
        _write_table(sheet, aggregate(by_zone.get(zone, []), len(group_titles), measures), measures,
                     unit_set, group_titles, wb)
        written += 1
    if len(zones) > max_zone_sheets:
        notes = list(notes) + [('Zone sheets', 'The first %d of %d zones have their own sheet; the '
                                'Zones and Pivot sheets hold all of them.' % (max_zone_sheets, len(zones)))]
    _notes_sheet(wb, notes, pairs_used or {})
    return wb.save(path), written, zones


# =============================================================================================
# API half
# =============================================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def property_options(objects, limit=300):
    """(label, value) choices for 'group by': the specials, then every property name on
    the first `limit` objects ('Element > Category'), value {'category', 'property'}."""
    from namo import items
    options = [(label, {'special': key}) for key, label in SPECIAL_GROUPS]
    for category, prop, _count in items.sample_properties(objects, limit):
        options.append(('%s > %s' % (category, prop), {'category': category, 'property': prop}))
    return options


def grouper_title(spec):
    if not spec:
        return ''
    if spec.get('special'):
        return dict(SPECIAL_GROUPS).get(spec['special'], spec['special'])
    return '%s > %s' % (spec.get('category', ''), spec.get('property', ''))


def group_value(obj, spec, model_names):
    from namo import items
    special = spec.get('special')
    if special == '@category':
        return group_text(items.category(obj))
    if special == '@model':
        root = _model_root(obj)
        return group_text(model_names.get(root, '') if root is not None else '')
    return group_text(items.prop(obj, spec.get('category', ''), spec.get('property', '')))


def _model_root(obj):
    node = obj
    last = obj
    while node is not None:
        last = node
        node = node.Parent
    return last


def _model_units(obj, cache, doc_units):
    from namo import items
    root = _model_root(obj)
    if root in cache:
        return cache[root]
    value = doc_units
    try:
        model = items.model_of(obj)
        if model is not None:
            value = str(model.Units)
    except Exception:
        pass
    cache[root] = value
    return value


def collect(config, doc=None, report=None):
    """Reads one takeoff. config: {'scope', 'group_by': [spec, spec?], 'measures',
    'geometric', 'zones' (optional zone spec, see zone_assigner)}. report(fraction,
    label) may raise to cancel. Returns {'records', 'pairs', 'sampled', 'total',
    'geometric', 'geometry_skipped', 'doc_units', 'zone_note'}."""
    from namo import fourd_common, items, mesh
    document = _doc(doc)
    report = report or (lambda fraction, label='': True)
    doc_units = str(document.Units)
    scope = config.get('scope') or 'model'
    report(0.0, 'Finding objects')
    objects = fourd_common.scope_objects(scope, document, tick=lambda done, total: report(0.02, 'Finding objects'),
                                         budget=config.get('budget'))
    measures = [m for m in config.get('measures') or ['count'] if m in MEASURES]
    groupers = [g for g in (config.get('group_by') or []) if g][:2] or [{'special': '@category'}]
    pairs = choose_pairs(items.sample_properties(objects, 300),
                         [m for m in measures if m in PROPERTY_MEASURES])
    model_names = {}
    for entry in items.models(document):
        model_names[entry['root']] = entry['name']
    zone_of = zone_assigner(config.get('zones'), objects, document) if config.get('zones') else None
    unit_cache = {}
    records = []
    geometric = 0
    geometry_skipped = 0
    total = len(objects)
    want_geometry = bool(config.get('geometric')) or 'surface' in measures
    for index, obj in enumerate(objects):
        if index % 50 == 0:
            report(0.05 + 0.9 * index / float(total or 1),
                   'Measuring %s of %s objects' % ('{:,}'.format(index + 1), '{:,}'.format(total)))
        zone = None
        if zone_of is not None:
            zone = zone_of(obj)
            if zone is None:
                continue                # a zone object itself: not counted
        model_units = _model_units(obj, unit_cache, doc_units)
        record = {'name': str(obj.DisplayName or ''), 'groups': [group_value(obj, g, model_names) for g in groupers],
                  'measures': {}, 'sources': {}, 'item': obj}
        if zone_of is not None:
            record['zone'] = zone
        for measure in measures:
            if measure in PROPERTY_MEASURES:
                value = None
                for category, prop in pairs.get(measure, []):
                    value = to_si(measure, items.prop(obj, category, prop, fallback_to_object=False),
                                  model_units)
                    if value is not None:
                        break
                record['measures'][measure] = value
                if value is not None:
                    record['sources'][measure] = 'property'
        needs = want_geometry and (
            'surface' in measures or
            (config.get('geometric') and (('volume' in measures and record['measures'].get('volume') is None) or
                                          ('length' in measures and record['measures'].get('length') is None))))
        if needs:
            if geometric >= GEOMETRY_BUDGET:
                geometry_skipped += 1
            else:
                geometric += 1
                _measure_geometry(obj, record, measures, doc_units, mesh, bool(config.get('geometric')))
        records.append(record)
    report(0.97, 'Adding up')
    return {'records': records, 'pairs': pairs, 'sampled': bool(objects.sampled), 'total': total,
            'geometric': geometric, 'geometry_skipped': geometry_skipped, 'doc_units': doc_units,
            'scope': scope, 'groupers': groupers, 'measures': measures}


def _measure_geometry(obj, record, measures, doc_units, mesh, fill_missing):
    from namo import items
    data = mesh.item_triangles(obj, budget=TRIANGLE_BUDGET)
    tris = data['tris']
    factor = unit_factor(doc_units, 1)
    if tris:
        if 'surface' in measures:
            record['measures']['surface'] = mesh.area(tris) * factor ** 2
            record['sources']['surface'] = 'geometric'
        if fill_missing and 'volume' in measures and record['measures'].get('volume') is None:
            solid = solid_measure(tris)
            if solid is not None:
                record['measures']['volume'] = solid['volume'] * factor ** 3
                record['sources']['volume'] = 'geometric'
    if fill_missing and 'length' in measures and record['measures'].get('length') is None:
        size = items.size(obj)
        if size is not None:
            record['measures']['length'] = max(size) * factor
            record['sources']['length'] = 'bbox'


def zone_assigner(spec, objects, doc=None):
    """A function obj -> zone name for a zone spec:
    {'mode': 'levels'} grid levels of the active grid system;
    {'mode': 'objects', 'set': 'Folder/Set' or '' for the current selection};
    {'mode': 'grid'} grid bays; {'mode': 'tiles', 'spacing': model units}.
    Raises ValueError with a sentence when the zones cannot be built."""
    from namo import items
    document = _doc(doc)
    mode = (spec or {}).get('mode') or 'levels'
    if mode == 'levels':
        levels = grid_levels(document)
        if not levels:
            raise ValueError('The model has no grid levels. Pick another zone source.')
        bands = level_bands(levels)

        def by_level(obj):
            center = items.center(obj)
            return assign_band(center[2], bands) if center is not None else NO_ZONE
        return by_level
    if mode == 'objects':
        zone_items = zone_objects(spec.get('set') or '', document)
        if not zone_items:
            raise ValueError('No zone objects found. Select rooms or areas, or name a selection set.')
        zones = []
        names = unique_names([zone_name(z) for z in zone_items])
        for name, zone in zip(names, zone_items):
            box = items.bbox(zone)
            if box is not None:
                zones.append({'name': name, 'box': box})
        zone_set = set(zone_items)

        def by_box(obj):
            if obj in zone_set:
                return None                 # the zone objects themselves are not counted
            box = items.bbox(obj)
            return assign_box(box, zones) if box is not None else NO_ZONE
        return by_box
    if mode == 'grid':
        box = items.bbox(items.roots(document))
        families = grid_families(grid_intersections(document, box))
        if not families:
            raise ValueError('The model has no grid lines. Pick another zone source.')

        def by_bay(obj):
            center = items.center(obj)
            return grid_bay(center, families) if center is not None else NO_ZONE
        return by_bay
    spacing = float(spec.get('spacing') or 0)
    if spacing <= 0:
        raise ValueError('The tile size must be more than zero.')
    box = items.bbox(items.roots(document))
    if box is None:
        raise ValueError('The model has no extent to tile.')
    origin = box[0]
    counts = (int((box[1][0] - box[0][0]) // spacing) + 1, int((box[1][1] - box[0][1]) // spacing) + 1)

    def by_tile(obj):
        center = items.center(obj)
        return assign_tile(center, origin, spacing, counts) if center is not None else NO_ZONE
    return by_tile


def grid_levels(doc=None):
    """[(name, elevation)] of the active grid system's levels, or []."""
    try:
        system = _doc(doc).Grids.ActiveSystem
        if system is None:
            return []
        return [(str(level.DisplayName), float(level.Elevation)) for level in system.Levels]
    except Exception:
        return []


def grid_intersections(doc, box, samples=24):
    """Distinct grid intersections found by asking the active grid system for the closest
    one to each point of a samples x samples lattice over the model's plan box."""
    from pynavis._api import Api
    try:
        system = _doc(doc).Grids.ActiveSystem
    except Exception:
        system = None
    if system is None or box is None:
        return []
    found = {}
    z = (box[0][2] + box[1][2]) / 2.0
    for i in range(samples + 1):
        for j in range(samples + 1):
            x = box[0][0] + (box[1][0] - box[0][0]) * i / float(samples)
            y = box[0][1] + (box[1][1] - box[0][1]) * j / float(samples)
            try:
                hit = system.ClosestIntersection(Api.Point3D(x, y, z))
            except Exception:
                hit = None
            if hit is None:
                continue
            try:
                key = (str(hit.Line1.DisplayName), str(hit.Line2.DisplayName))
                if key in found:
                    continue
                found[key] = {'line1': key[0], 'line2': key[1],
                              'dir1': (hit.Line1Direction.X, hit.Line1Direction.Y),
                              'dir2': (hit.Line2Direction.X, hit.Line2Direction.Y),
                              'pos': (hit.Position.X, hit.Position.Y)}
            except Exception:
                continue
    return [found[k] for k in sorted(found)]


def zone_objects(set_path, doc=None):
    """Zone objects: the objects of a selection set, or of the current selection."""
    from namo import items
    document = _doc(doc)
    if set_path:
        from pynavis import sets
        saved = sets.find(set_path, document)
        if saved is None:
            return []
        try:
            members = sets.items_of(saved, document)
        except ValueError:              # a folder of sets, not a set
            return []
        return items.objects(items.as_list(members))
    return items.objects(items.selected(document))


def zone_name(obj):
    """'101 Office' from Revit room/space properties, else the display name."""
    from namo import items
    number = None
    name = None
    for category in ('Element', 'Room', 'Space', 'Identity Data'):
        number = number or items.prop(obj, category, 'Number')
        name = name or items.prop(obj, category, 'Name')
    parts = [group_text(v) for v in (number, name) if v not in (None, '')]
    text = ' '.join(p for p in parts if p != NO_VALUE)
    return text or str(obj.DisplayName or '') or 'Zone'


def select_records(records, indexes, doc=None):
    """Selects the objects of the given record indexes; returns how many."""
    from namo import items
    chosen = [records[i]['item'] for i in indexes if 0 <= i < len(records)]
    return items.select(chosen, doc=doc)


# ---- configurations and runs (shared by the buttons, templates and reports) ------------------


def default_quick_config():
    return {'scope': 'model', 'group_by': [{'special': '@category'}],
            'measures': ['count', 'length', 'area', 'volume'], 'geometric': False, 'units': 'auto'}


def default_zone_config():
    config = default_quick_config()
    config.update({'zones': {'mode': 'levels'}, 'pivot_measure': 'count'})
    return config


ZONE_MODES = [('levels', 'Grid levels (bands between levels)'), ('objects', 'Zone objects (rooms, areas, a set)'),
              ('grid', 'Grid bays (between grid lines)'), ('tiles', 'Square tiles of a fixed size')]


def describe_config(config):
    """'Whole model by Category: count, length, area, volume' (+ zones)."""
    from namo import fourd_common
    scope = fourd_common.SCOPE_LABELS.get(config.get('scope') or 'model', 'Whole model')
    groups = ' and '.join(grouper_title(g) for g in (config.get('group_by') or []) if g) or 'Category'
    measures = ', '.join(LABELS[m].lower() for m in config.get('measures') or ['count'] if m in LABELS)
    text = '%s by %s: %s' % (scope, groups, measures)
    zones = config.get('zones')
    if zones:
        label = dict(ZONE_MODES).get(zones.get('mode'), zones.get('mode'))
        text += '; zones: %s' % label.split(' (')[0].lower()
    return text


def status_text(data, groups):
    """One line for the result window and the toast detail."""
    from namo import fourd_common
    parts = ['%s in %s' % (fourd_common.plural(len(data['records']), 'object'),
                           fourd_common.plural(groups, 'group'))]
    if data.get('geometric'):
        parts.append('%s measured from geometry' % fourd_common.plural(data['geometric'], 'object'))
    if data.get('geometry_skipped'):
        parts.append('%s past the geometry budget' % '{:,}'.format(data['geometry_skipped']))
    if data.get('sampled'):
        parts.append('sampled')
    return ', '.join(parts) + '.'


def notes_for(data, config, unit_set):
    from namo import fourd_common
    notes = [('Scope', fourd_common.SCOPE_LABELS.get(data.get('scope'), data.get('scope') or '')),
             ('Units', ', '.join('%s %s' % (LABELS[m], units.symbol(unit_set[m]))
                                 for m in ('length', 'area', 'volume', 'weight', 'surface')
                                 if m in data.get('measures', []))),
             ('Property values', 'Values with units are converted; bare numbers are read in the units '
                                 'of the model they come from.')]
    if config.get('geometric') or 'surface' in data.get('measures', []):
        notes.append(('Geometric values', 'Volumes come from meshes that enclose a solid only; lengths from '
                      'geometry are the longest side of the bounding box. Both are flagged in the '
                      'Notes column.'))
    if data.get('geometry_skipped'):
        notes.append(('Geometry budget', '%s objects were past the budget of %s and were not measured '
                      'from geometry.' % ('{:,}'.format(data['geometry_skipped']), '{:,}'.format(GEOMETRY_BUDGET))))
    if data.get('sampled'):
        notes.append(('Sampled', 'The object count hit the budget; the totals are for a sample.'))
    return notes


def run(config, doc=None, report=None):
    """Collects and aggregates one takeoff. Returns {'data', 'rows', 'unit_set', 'measures',
    'group_titles', 'notes', 'status'}. Raises ValueError for zones that cannot be built."""
    from namo import config as namo_config
    data = collect(config, doc, report)
    measures = data['measures']
    unit_set = display_units(config.get('units') or namo_config.get('report_units') or 'auto',
                             data['doc_units'])
    levels = len(data['groupers'])
    rows = aggregate(data['records'], levels, measures)
    group_titles = [grouper_title(g) for g in data['groupers']]
    groups = len([r for r in rows if r['kind'] == 'group'])
    return {'data': data, 'rows': rows, 'unit_set': unit_set, 'measures': measures,
            'group_titles': group_titles, 'notes': notes_for(data, config, unit_set),
            'status': status_text(data, groups)}

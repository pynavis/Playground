# -*- coding: utf-8 -*-
"""Centre of gravity and weight of selected objects.

Per object (API half, measure_object):
  1. Mass: an explicit Weight or Mass property wins (namo.takeoff.to_si: units read from
     the text, bare numbers kg in metric models, lb in imperial ones); otherwise volume x
     density, the density matched from the material (or, failing that, the category)
     against the density table.
  2. Volume and centroid: the triangle mesh when it encloses a solid
     (namo.takeoff.solid_measure, then namo.mesh's solid centroid). An open or unreadable
     mesh falls back to the bounding box centre and the box volume x the fill factor,
     flagged 'estimate' everywhere it is shown.
Combined: the mass-weighted mean of the centroids, and the total mass. Objects with
no mass (no density match and no default) are listed but not in the total.

Pure half: density tables (text form 'steel = 7850' one per line), matching, combining,
formatting and the overlay marker. Densities are kg/m3.
"""

DEFAULT_DENSITIES = [('steel', 7850.0), ('concrete', 2400.0), ('aluminium', 2700.0),
                     ('aluminum', 2700.0), ('timber', 500.0), ('wood', 500.0), ('glass', 2500.0)]
DEFAULTS = {'densities': '\n'.join('%s = %s' % (k, ('%g' % v)) for k, v in DEFAULT_DENSITIES),
            'fill_factor': 0.6, 'default_density': None}
METHODS = {'mesh': 'Closed mesh', 'bbox': 'Bounding box (estimate)', 'none': 'No geometry'}
MARKER_TAG = 'playground-cog'
MAX_OBJECTS = 2000

WEIGHT_NAMES = ('weight', 'mass', 'net weight', 'netweight', 'gross weight', 'grossweight')
MATERIAL_NAMES = ('material', 'structural material', 'material name', 'name of material')


def parse_densities(text):
    """([(keyword lowercased, kg/m3)], [sentence]) from 'keyword = number' lines;
    blank lines and '#' comments skipped."""
    table = []
    errors = []
    for number, line in enumerate(str(text or '').replace('\r', '').split('\n')):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            errors.append('Line %d: write it as material = density, like steel = 7850.' % (number + 1))
            continue
        key, value = line.split('=', 1)
        key = ' '.join(key.strip().lower().split())
        try:
            density = float(value.strip().replace(',', ''))
        except ValueError:
            errors.append('Line %d: "%s" is not a number.' % (number + 1, value.strip()))
            continue
        if not key or density <= 0:
            errors.append('Line %d: needs a material word and a density above zero.' % (number + 1))
            continue
        table.append((key, density))
    return table, errors


def match_density(materials, category, table):
    """(keyword, density, 'material' | 'category') for the first table keyword found in a
    material text, else in the category; None when nothing matches."""
    for source, texts in (('material', materials), ('category', [category] if category else [])):
        lowered = [str(t).lower() for t in texts if t]
        for keyword, density in table:
            for text in lowered:
                if keyword in text:
                    return keyword, density, source
    return None


def combine(parts):
    """{'mass': kg, 'cog': (x, y, z) or None, 'count': objects in the total} from
    [(mass_kg or None, centroid or None)]."""
    total = 0.0
    acc = [0.0, 0.0, 0.0]
    count = 0
    base = None                 # moments are taken about the first centroid, not the origin
    for mass, point in parts:
        if mass is None or point is None or mass <= 0:
            continue
        if base is None:
            base = (float(point[0]), float(point[1]), float(point[2]))
        total += mass
        count += 1
        for axis in range(3):
            acc[axis] += mass * (point[axis] - base[axis])
    if total <= 0:
        return {'mass': 0.0, 'cog': None, 'count': 0}
    return {'mass': total, 'count': count,
            'cog': tuple(base[axis] + acc[axis] / total for axis in range(3))}


def format_mass(kg, imperial=False):
    """'860 kg', '12.4 t' (metric) or '27,340 lb' (imperial)."""
    if kg is None:
        return ''
    if imperial:
        return '{:,.0f} lb'.format(kg / 0.45359237)
    if kg < 1000.0:
        return '{:,.0f} kg'.format(kg)
    return '{:,.1f} t'.format(kg / 1000.0)


def format_point(point, decimals=3):
    """'X, Y, Z' (the shape pyNavis Get/Go to Coordinates use)."""
    spec = '%.' + str(int(decimals)) + 'f'
    return ', '.join(spec % float(v) for v in point)


def marker_segments(point, size):
    """A 3-axis cross on the point for pynavis.overlay.add."""
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    arm = abs(float(size))
    return [((x - arm, y, z), (x + arm, y, z), False), ((x, y - arm, z), (x, y + arm, z), False),
            ((x, y, z - arm), (x, y, z + arm), False)]


def marker_size(box, unit_to_m):
    """Arm length: 3% of the selection's box diagonal, at least 0.25 m."""
    floor = 0.25 / (unit_to_m or 1.0)
    if box is None:
        return floor
    diagonal = sum((box[1][i] - box[0][i]) ** 2 for i in range(3)) ** 0.5
    return max(floor, 0.03 * diagonal)


def result_rows(results, imperial, doc_units):
    """Table rows for the results window: object, mass, volume (m3 or ft3), density,
    centroid X/Y/Z, method."""
    from namo import units
    rows = []
    volume_unit = 'ft3' if imperial else 'm3'
    for index, r in enumerate(results):
        volume = units.convert(r['volume_m3'], 'm3', volume_unit) if r.get('volume_m3') is not None else None
        center = r.get('centroid') or ('', '', '')
        density = ''
        if r.get('density'):
            density = '%s (%s)' % ('{:,.0f}'.format(r['density']), r.get('density_from') or '')
        rows.append({'cells': [r['name'], format_mass(r.get('mass_kg'), imperial) or 'No mass',
                               round(volume, 3) if volume is not None else '', density,
                               round(center[0], 3) if center[0] != '' else '',
                               round(center[1], 3) if center[1] != '' else '',
                               round(center[2], 3) if center[2] != '' else '',
                               r.get('method_label', '')], 'value': index})
    return rows


# ---- API half -------------------------------------------------------------------------------


def _scan(item):
    """(weights [(value)], materials [text]) from every property of the item and its
    object ancestor."""
    from namo import variants
    from namo import items
    weights = []
    materials = []
    nodes = [item]
    element = items.object_of(item)
    try:
        same = element.Equals(item)
    except Exception:
        same = element is item
    if not same:
        nodes.append(element)
    for node in nodes:
        try:
            rows = variants.all_of(node)
        except Exception:
            rows = []
        for row in rows:
            name = ' '.join(str(row.get('property') or '').lower().split())
            category = ' '.join(str(row.get('category') or '').lower().split())
            if name in WEIGHT_NAMES:
                weights.append(row.get('value'))
            elif (name in MATERIAL_NAMES or name.endswith(' material')
                  or (category == 'material' and name == 'name')):
                if row.get('value') not in (None, ''):
                    materials.append(str(row['value']))
    return weights, materials


def measure_object(obj, doc_units, table, fill_factor=0.6, default_density=None):
    """{'name', 'item', 'mass_kg', 'volume_m3', 'centroid', 'method', 'method_label',
    'density', 'density_from', 'material', 'weight_from_property', 'note'}."""
    from namo import items, mesh, takeoff, units
    to_m = units.to_meters(1.0, doc_units)
    model_units = doc_units
    try:
        model = items.model_of(obj)
        if model is not None:
            model_units = str(model.Units)
    except Exception:
        pass
    out = {'name': str(obj.DisplayName or '') or items.category(obj), 'item': obj, 'mass_kg': None,
           'volume_m3': None, 'centroid': None, 'method': 'none', 'density': None,
           'density_from': None, 'material': None, 'weight_from_property': False, 'note': None}
    data = mesh.item_triangles(obj)
    tris = data['tris']
    solid = takeoff.solid_measure(tris) if tris else None
    if solid is not None:
        out['centroid'] = solid['centroid']
        out['volume_m3'] = solid['volume'] * to_m ** 3
        out['method'] = 'mesh'
    if out['method'] == 'none':
        box = items.bbox(obj)
        if box is not None:
            out['centroid'] = items.box_center(box)
            size = items.box_size(box)
            out['volume_m3'] = size[0] * size[1] * size[2] * to_m ** 3 * float(fill_factor)
            out['method'] = 'bbox'
            out['note'] = data.get('note') or 'the mesh does not enclose a solid'
    weights, materials = _scan(obj)
    for value in weights:
        kg = takeoff.to_si('weight', value, model_units)
        if kg is not None and kg > 0:
            out['mass_kg'] = kg
            out['weight_from_property'] = True
            break
    out['material'] = materials[0] if materials else None
    if out['mass_kg'] is None and out['volume_m3'] is not None:
        found = match_density(materials, items.category(obj), table)
        if found is not None:
            out['density'], out['density_from'] = found[1], found[2]
        elif default_density:
            out['density'], out['density_from'] = float(default_density), 'default'
        if out['density']:
            out['mass_kg'] = out['volume_m3'] * out['density']
    label = METHODS.get(out['method'], out['method'])
    if out['weight_from_property']:
        label = 'Weight property, ' + label.lower()
    out['method_label'] = label
    return out


def show_marker(point, mass_kg, imperial, size):
    """Draws the COG cross with its label; False when the overlay is not loaded."""
    from pynavis import overlay
    overlay.clear(MARKER_TAG)
    drawn = overlay.add(MARKER_TAG, marker_segments(point, size),
                        label='COG  %s' % format_mass(mass_kg, imperial), label_at=point)
    _overlay_redraw()
    return drawn


def clear_marker():
    from pynavis import overlay
    overlay.clear(MARKER_TAG)
    return _overlay_redraw()


def write_xlsx(path, results, combined, imperial, doc_units, title, author=None):
    """The results as a workbook: Summary (total, COG) and Objects."""
    from namo import units, xlsx
    wb = xlsx.Workbook(title=title, author=author)
    ws = wb.sheet('Objects')
    unit = units.doc_unit_symbol(doc_units)
    ws.title(title, span=8)
    if combined['cog'] is not None:
        ws.subtitle('Total %s, centre of gravity %s %s' % (format_mass(combined['mass'], imperial),
                                                           format_point(combined['cog']), unit), span=8)
    mass_unit = 'lb' if imperial else 'kg'
    ws.columns([('Object', 34, None), ('Mass (%s)' % mass_unit, 14, 'num1'),
                ('Volume (%s)' % ('ft3' if imperial else 'm3'), 14, 'num2'), ('Density (kg/m3)', 14, 'int'),
                ('X (%s)' % unit, 13, 'num2'), ('Y (%s)' % unit, 13, 'num2'), ('Z (%s)' % unit, 13, 'num2'),
                ('Method', 30, None)])
    for r in results:
        mass = r.get('mass_kg')
        if mass is not None and imperial:
            mass = mass / 0.45359237
        volume = r.get('volume_m3')
        if volume is not None and imperial:
            volume = units.convert(volume, 'm3', 'ft3')
        c = r.get('centroid') or (None, None, None)
        ws.row([r['name'], mass, volume, r.get('density'), c[0], c[1], c[2], r.get('method_label')])
    ws.autofilter()
    return wb.save(path)


def _overlay_redraw():
    """Redraws the overlay through namo.overlayfix, so labels land on their points."""
    from namo import overlayfix
    return overlayfix.redraw()

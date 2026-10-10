# -*- coding: utf-8 -*-
"""IFC Exporter: which IFC class each object becomes, which storey it sits on, its
property sets, and the walk that turns a Navisworks selection into a namo.ifc model.

Pure half (tested on both engines):

    ifcexport.class_for('Ducts')                       # ('IfcDuctSegment', 'RIGIDSEGMENT')
    ifcexport.class_for('Generic Models')              # ('IfcBuildingElementProxy', None)
    ifcexport.class_for('IfcWallStandardCase')         # ('IfcWall', None): IFC-sourced models
    ifcexport.parse_overrides('Specialty Equipment = IfcFurniture\\n...')
    ifcexport.storey_by_elevation(levels, z)           # the level an object stands on
    ifcexport.plan_storeys(records, levels, mode)      # storeys + each record's storey key
    ifcexport.psets_from_rows(rows, skip)              # property sets from props.all_of rows

API half: collect(selected, options, progress) reads every object through
namo.meshexport.read_objects (same budgets and skipped list as the Geometry Exporter),
adding level, GlobalId and properties; model_for(...) assembles the namo.ifc model dict.

GlobalIds: the model's own IFC GlobalId property when present, else Revit's export GUID
derived from the UniqueId (namo.items.revit_ids, the same rule Revit's IFC exporter
uses), else the item's InstanceGuid, else a stable id from the document and the item
key. Duplicates (a Revit family's nested parts can share ids) get a stable derived id.
"""
import re

from namo import ifc, ifcguid

# Navisworks/Revit category (lower case) -> (IFC4 class, predefined type or None)
CLASS_MAP = {
    'walls': ('IfcWall', None),
    'curtain walls': ('IfcCurtainWall', None),
    'curtain panels': ('IfcPlate', 'CURTAIN_PANEL'),
    'curtain wall mullions': ('IfcMember', 'MULLION'),
    'floors': ('IfcSlab', 'FLOOR'),
    'slabs': ('IfcSlab', None),
    'roofs': ('IfcRoof', None),
    'ceilings': ('IfcCovering', 'CEILING'),
    'structural foundations': ('IfcFooting', None),
    'structural framing': ('IfcBeam', 'BEAM'),
    'structural columns': ('IfcColumn', 'COLUMN'),
    'columns': ('IfcColumn', 'COLUMN'),
    'structural trusses': ('IfcMember', None),
    'doors': ('IfcDoor', 'DOOR'),
    'windows': ('IfcWindow', 'WINDOW'),
    'stairs': ('IfcStair', None),
    'railings': ('IfcRailing', None),
    'top rails': ('IfcRailing', 'HANDRAIL'),
    'handrails': ('IfcRailing', 'HANDRAIL'),
    'ramps': ('IfcRamp', None),
    'furniture': ('IfcFurniture', None),
    'furniture systems': ('IfcFurniture', None),
    'casework': ('IfcFurniture', None),
    'ducts': ('IfcDuctSegment', 'RIGIDSEGMENT'),
    'flex ducts': ('IfcDuctSegment', 'FLEXIBLESEGMENT'),
    'duct fittings': ('IfcDuctFitting', None),
    'duct accessories': ('IfcDamper', None),
    'air terminals': ('IfcAirTerminal', None),
    'pipes': ('IfcPipeSegment', 'RIGIDSEGMENT'),
    'flex pipes': ('IfcPipeSegment', 'FLEXIBLESEGMENT'),
    'pipe fittings': ('IfcPipeFitting', None),
    'pipe accessories': ('IfcValve', None),
    'plumbing fixtures': ('IfcSanitaryTerminal', None),
    'sprinklers': ('IfcFireSuppressionTerminal', 'SPRINKLER'),
    'cable trays': ('IfcCableCarrierSegment', 'CABLETRAYSEGMENT'),
    'cable tray fittings': ('IfcCableCarrierFitting', None),
    'conduits': ('IfcCableCarrierSegment', 'CONDUITSEGMENT'),
    'conduit fittings': ('IfcCableCarrierFitting', None),
    'lighting fixtures': ('IfcLightFixture', None),
    'generic models': ('IfcBuildingElementProxy', None),
}
PROXY = ('IfcBuildingElementProxy', None)

# Predefined type values this exporter may write, per class (each enum also has
# NOTDEFINED and USERDEFINED; the writer turns None into NOTDEFINED).
PREDEFINED = {
    'IfcSlab': ('FLOOR', 'ROOF', 'LANDING', 'BASESLAB'),
    'IfcCovering': ('CEILING', 'FLOORING', 'CLADDING', 'ROOFING', 'INSULATION', 'MEMBRANE',
                    'SLEEVING', 'WRAPPING', 'MOLDING', 'SKIRTINGBOARD'),
    'IfcBeam': ('BEAM', 'JOIST', 'HOLLOWCORE', 'LINTEL', 'SPANDREL', 'T_BEAM'),
    'IfcColumn': ('COLUMN', 'PILASTER'),
    'IfcMember': ('MULLION', 'BRACE', 'CHORD', 'COLLAR', 'MEMBER', 'PLATE', 'POST', 'PURLIN',
                  'RAFTER', 'STRINGER', 'STRUT', 'STUD'),
    'IfcPlate': ('CURTAIN_PANEL', 'SHEET'),
    'IfcDoor': ('DOOR', 'GATE', 'TRAPDOOR'),
    'IfcWindow': ('WINDOW', 'SKYLIGHT', 'LIGHTDOME'),
    'IfcRailing': ('HANDRAIL', 'GUARDRAIL', 'BALUSTRADE'),
    'IfcDuctSegment': ('RIGIDSEGMENT', 'FLEXIBLESEGMENT'),
    'IfcPipeSegment': ('RIGIDSEGMENT', 'FLEXIBLESEGMENT', 'CULVERT', 'GUTTER', 'SPOOL'),
    'IfcCableCarrierSegment': ('CABLETRAYSEGMENT', 'CONDUITSEGMENT', 'CABLELADDERSEGMENT',
                               'CABLETRUNKINGSEGMENT'),
    'IfcFireSuppressionTerminal': ('SPRINKLER', 'BREECHINGINLET', 'FIREHYDRANT', 'HOSEREEL',
                                   'SPRINKLERDEFLECTOR'),
}

# Where a level name is looked for, in order (display names), on the object.
LEVEL_PROPERTIES = [
    ('Element', 'Level'), ('Element', 'Reference Level'), ('Element', 'Base Level'),
    ('Element', 'Base Constraint'), ('Element', 'Schedule Level'),
    ('Constraints', 'Level'), ('Constraints', 'Reference Level'),
    ('Constraints', 'Base Constraint'), ('Revit Element', 'Level'),
]

# Property tabs left out by default: Navisworks' own bookkeeping, not BIM data.
DEFAULT_SKIP_TABS = ('Item', 'Material', 'Geometry', 'Transform', 'Autodesk Material',
                     'Revit Material')

STOREY_MODES = [('auto', 'Level property, then grid levels'), ('grid', 'Grid levels only'),
                ('one', 'One storey for everything')]
PSET_MODES = [('data', 'Every property tab except Navisworks bookkeeping'), ('all', 'Every property tab'),
              ('none', 'No property sets')]

DEFAULT_PER_OBJECT = 100000
DEFAULT_TOTAL = 1000000

_CLASS_NAMES = dict((name.lower(), name) for name in ifc.ELEMENT_CLASSES)
_SUFFIXES = ('standardcase', 'elementedcase')


def _norm(text):
    return ' '.join(str(text or '').strip().lower().split())


def ifc_class_name(text):
    """The writable IFC class for an IFC class name in any case ('IFCWALLSTANDARDCASE',
    'IfcSlabStandardCase' -> IfcSlab), or None."""
    key = re.sub(r'[^a-z0-9]', '', str(text or '').lower())
    if not key.startswith('ifc'):
        return None
    if key in _CLASS_NAMES:
        return _CLASS_NAMES[key]
    for suffix in _SUFFIXES:
        if key.endswith(suffix) and key[:-len(suffix)] in _CLASS_NAMES:
            return _CLASS_NAMES[key[:-len(suffix)]]
    if key == 'ifcbuildingelementproxy':
        return 'IfcBuildingElementProxy'
    return None


def parse_class(text):
    """('IfcClass', predefined or None) from 'IfcBeam' or 'IfcBeam.JOIST'; ValueError
    with a sentence when the class is not one this exporter writes or the type is not
    one of the class's values."""
    raw = str(text or '').strip()
    name, _dot, predefined = raw.partition('.')
    cls = ifc_class_name(name)
    if cls is None:
        raise ValueError('%s is not an IFC class the exporter writes. Use one of: %s.' % (
            name or 'That', ', '.join(sorted(ifc.ELEMENT_CLASSES))))
    predefined = predefined.strip().upper() or None
    if predefined and predefined not in ('NOTDEFINED', 'USERDEFINED') \
            and predefined not in PREDEFINED.get(cls, ()):
        raise ValueError('%s is not a type of %s.' % (predefined, cls))
    if predefined == 'USERDEFINED':
        raise ValueError('USERDEFINED needs an object type; leave the type off instead.')
    return cls, predefined


def parse_overrides(text):
    """({category lower: (class, predefined)}, [error sentences]) from lines like
    'Specialty Equipment = IfcFurniture' or 'Structural Framing = IfcBeam.JOIST'.
    Blank lines and lines starting with # are ignored."""
    mapping = {}
    errors = []
    for number, raw in enumerate(str(text or '').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            errors.append('Line %d needs "Category = IfcClass".' % number)
            continue
        category, _eq, target = line.partition('=')
        if not category.strip():
            errors.append('Line %d has no category before "=".' % number)
            continue
        try:
            mapping[_norm(category)] = parse_class(target)
        except ValueError as error:
            errors.append('Line %d: %s' % (number, error))
    return mapping, errors


def overrides_text(mapping):
    """The editable text for a mapping (sorted by category)."""
    lines = []
    for category in sorted(mapping):
        cls, predefined = mapping[category]
        lines.append('%s = %s%s' % (category, cls, ('.' + predefined) if predefined else ''))
    return '\n'.join(lines)


def class_for(category, overrides=None):
    """(IFC class, predefined type or None) for a Navisworks/Revit category or an IFC
    class name; user overrides win; anything unknown is IfcBuildingElementProxy."""
    key = _norm(category)
    if overrides and key in overrides:
        return tuple(overrides[key])
    if key in CLASS_MAP:
        return CLASS_MAP[key]
    named = ifc_class_name(category)
    if named is not None:
        return (named, None)
    return PROXY


# ---- storeys --------------------------------------------------------------------------


def storey_by_elevation(levels, z, tolerance=0.0):
    """The (name, elevation) level an object whose bottom is at z stands on: the highest
    level at or below z + tolerance; below every level, the lowest. None without levels."""
    ordered = sorted(levels, key=lambda lv: (lv[1], str(lv[0])))
    if not ordered:
        return None
    found = ordered[0]
    for level in ordered:
        if level[1] <= z + tolerance:
            found = level
    return found


def plan_storeys(records, levels, mode='auto', tolerance=0.0):
    """(storeys, keys): storeys [{'key', 'name', 'elevation'}] sorted by elevation, and
    one storey key per record (None = 'No level').

    record keys used: 'level' (a level name from properties, or None) and 'bottom' (the
    object's lowest Z). levels: [(name, elevation)] from the grid system.
    mode 'auto': the level property when present, else the grid level under the object;
    'grid': grid levels only; 'one': a single storey named 'Level 1' at the lowest
    elevation (every object on it)."""
    if mode == 'one':
        bottoms = [r.get('bottom') for r in records if r.get('bottom') is not None]
        elevation = min(bottoms) if bottoms else 0.0
        return [{'key': 'one', 'name': 'Level 1', 'elevation': elevation}], ['one'] * len(records)
    grid = dict((str(name).strip().lower(), (str(name).strip(), float(elev))) for name, elev in levels)
    names = {}
    keys = []
    bottoms_by_key = {}
    for record in records:
        name = None
        if mode == 'auto' and record.get('level'):
            name = str(record['level']).strip()
        elif record.get('bottom') is not None and levels:
            hit = storey_by_elevation(levels, record['bottom'], tolerance)
            name = str(hit[0]).strip() if hit else None
        if not name:
            keys.append(None)
            continue
        key = name.lower()
        names.setdefault(key, name)
        keys.append(key)
        if record.get('bottom') is not None:
            bottoms_by_key.setdefault(key, []).append(record['bottom'])
    storeys = []
    for key in names:
        if key in grid:
            elevation = grid[key][1]
        elif bottoms_by_key.get(key):
            elevation = min(bottoms_by_key[key])
        else:
            elevation = 0.0
        storeys.append({'key': key, 'name': names[key], 'elevation': elevation})
    storeys.sort(key=lambda s: (s['elevation'], ifc._natural(s['name'])))
    return storeys, keys


# ---- properties -----------------------------------------------------------------------


def psets_from_rows(rows, skip=DEFAULT_SKIP_TABS):
    """[(tab, [(property, value)])] from pynavis.props.all_of rows, in first-seen tab
    order, leaving out the tabs named in skip (case-insensitive) and empty values."""
    skipped = set(_norm(s) for s in (skip or ()))
    order = []
    tabs = {}
    for row in rows or []:
        tab = str(row.get('category') or '').strip()
        prop = str(row.get('property') or '').strip()
        value = row.get('value')
        if not tab or not prop or _norm(tab) in skipped or value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if tab not in tabs:
            tabs[tab] = []
            order.append(tab)
        tabs[tab].append((prop, value))
    return [(tab, tabs[tab]) for tab in order]


# ---- identity -------------------------------------------------------------------------


def choose_guid(candidates, seed, key, used):
    """The first valid, unused GlobalId among candidates (IFC GlobalIds or GUID text),
    else a stable one derived from seed and key. Adds the result to used."""
    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate).strip()
        value = None
        if ifcguid.is_valid(text):
            value = text
        else:
            try:
                value = ifcguid.compress(text)
            except ValueError:
                value = None
        if value and value not in used and value != '0000000000000000000000':
            used.add(value)
            return value
    n = 0
    while True:
        value = ifc.guid(seed, 'element', key, n)
        if value not in used:
            used.add(value)
            return value
        n += 1


def object_type_of(ids, category):
    """'Family: Type' when Revit names them, else the category."""
    family = (ids or {}).get('family')
    kind = (ids or {}).get('type')
    if family and kind and kind != family:
        return '%s: %s' % (family, kind)
    return kind or family or category or None


def element_for(record, cls, predefined, guid_value, storey_key, psets, doc_units_scale=1.0):
    """The namo.ifc element dict for one read record (record['tris'] in world model
    units): welded vertices relative to the object's lowest corner."""
    from namo import meshexport
    if record.get('mesh') is not None:
        vertices, faces = record['mesh']
    else:
        vertices, faces = meshexport._weld(record.get('tris') or [], record.get('weld') or 1e-6)
    if not faces:
        return None
    origin = tuple(min(v[a] for v in vertices) for a in range(3))
    local = [(v[0] - origin[0], v[1] - origin[1], v[2] - origin[2]) for v in vertices]
    ids = record.get('ids') or {}
    return {
        'guid': guid_value,
        'ifc_class': cls,
        'predefined': predefined,
        'name': record.get('name'),
        'object_type': object_type_of(ids, record.get('category')),
        'tag': ids.get('element_id'),
        'storey': storey_key,
        'origin': origin,
        'vertices': local,
        'faces': faces,
        'closed': _closed(faces),
        'color': record.get('color'),
        'transparency': record.get('transparency') or 0.0,
        'psets': psets,
    }


def _closed(faces):
    """True when every edge of the welded mesh is used by exactly two triangles."""
    edges = {}
    for i, j, k in faces:
        for a, b in ((i, j), (j, k), (k, i)):
            edge = (a, b) if a < b else (b, a)
            edges[edge] = edges.get(edge, 0) + 1
    return bool(edges) and all(n == 2 for n in edges.values())


def summary(written, skipped, sampled=False, storeys=0):
    """(level, message, detail) for the closing toast."""
    if not written:
        return ('warning', 'Nothing was exported', 'None of the selected objects gave triangles.')
    message = 'Exported %s %s to IFC' % ('{:,}'.format(written), 'object' if written == 1 else 'objects')
    detail = '%s %s.' % ('{:,}'.format(storeys), 'storey' if storeys == 1 else 'storeys')
    if skipped or sampled:
        parts = []
        if skipped:
            parts.append('%s skipped (listed in the output window)' % '{:,}'.format(skipped))
        if sampled:
            parts.append('the selection was sampled')
        text = '; '.join(parts)
        return ('warning', message, text[:1].upper() + text[1:] + '.')
    return ('success', message, detail)


DEFAULT_OPTIONS = {'storeys': 'auto', 'psets': 'data', 'per_object': DEFAULT_PER_OBJECT,
                   'total': DEFAULT_TOTAL, 'building': ''}


def form_fields(values, project, building):
    """The IFC Exporter form (namo.ui.form fields)."""
    return [
        {'kind': 'text', 'key': 'project', 'label': 'Project', 'default': project, 'required': True},
        {'kind': 'text', 'key': 'building', 'label': 'Building', 'default': values.get('building') or building,
         'required': True},
        {'kind': 'radio', 'key': 'storeys', 'label': 'Storeys from', 'default': values['storeys'], 'fallback': None,
         'options': [(label, key) for key, label in STOREY_MODES]},
        {'kind': 'radio', 'key': 'psets', 'label': 'Property sets', 'default': values['psets'], 'fallback': None,
         'options': [(label, key) for key, label in PSET_MODES]},
        {'kind': 'separator'},
        {'kind': 'int', 'key': 'per_object', 'label': 'Triangles per object, at most', 'min': 100,
         'max': 5000000, 'default': values['per_object'], 'required': True},
        {'kind': 'int', 'key': 'total', 'label': 'Triangles in all, at most', 'min': 1000,
         'max': 50000000, 'default': values['total'], 'required': True,
         'hint': 'Objects past either limit are skipped and listed.'},
    ]


OVERRIDE_SAMPLE = 'Specialty Equipment = IfcFurniture' + chr(10) + 'Structural Framing = IfcBeam.JOIST'


def override_fields(current):
    """The Shift+Click form: the team's class rules as text, plus a choice to list the
    built-in ones."""
    def check(text):
        _mapping, errors = parse_overrides(text)
        return errors[0] if errors else None

    return [
        {'kind': 'textarea', 'key': 'map', 'label': 'Category = IFC class', 'rows': 8,
         'default': overrides_text(current), 'placeholder': OVERRIDE_SAMPLE, 'validate': check,
         'hint': 'One line each. Add .TYPE for a predefined type, like IfcBeam.JOIST. Unlisted '
                 'categories keep the built-in class; anything unknown is IfcBuildingElementProxy.'},
        {'kind': 'check', 'key': 'show', 'label': 'List the built-in classes in the output window',
         'default': False},
    ]


def builtin_rows():
    """[category, class, predefined type] for every built-in rule, by category."""
    rows = []
    for category in sorted(CLASS_MAP):
        cls, predefined = CLASS_MAP[category]
        rows.append([category[:1].upper() + category[1:], cls, predefined or ''])
    return rows


def stored_overrides(saved):
    """{category: (class, predefined)} from the stored JSON value, keeping only classes
    this exporter writes."""
    out = {}
    for category in sorted(saved or {}):
        value = saved[category]
        if isinstance(value, (list, tuple)) and value and value[0] in ifc.ELEMENT_CLASSES:
            out[category] = (value[0], value[1] if len(value) > 1 else None)
    return out


FORM_INTRO = ('IFC4, Reference View style: each object as a triangulated body with its colour, in the '
              'storey it stands on. Shift+Click the button to change which IFC class a category becomes.')


# =====================================================================================
# API half
# =====================================================================================


def grid_levels(doc):
    """[(name, elevation)] of the active grid system's levels, or [] (GridLevel.Elevation
    taken as model Z, unverified)."""
    try:
        system = doc.Grids.ActiveSystem
        if system is None:
            return []
        return [(str(level.DisplayName), float(level.Elevation)) for level in system.Levels]
    except Exception:
        return []


def grid_level_at(doc, point):
    """The grid level name Navisworks reports for a point (ClosestIntersection, the call
    pynavis.clash uses for clash levels), or None."""
    try:
        from pynavis._api import Api
        system = doc.Grids.ActiveSystem
        if system is None:
            return None
        hit = system.ClosestIntersection(Api.Point3D(point[0], point[1], point[2]))
        if hit is None or hit.Level is None:
            return None
        return str(hit.Level.DisplayName)
    except Exception:
        return None


def level_property(item):
    """The level name the object carries in its properties, or None."""
    from namo import items
    for category, prop in LEVEL_PROPERTIES:
        value = items.prop(item, category, prop)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def instance_guid(item):
    try:
        value = str(item.InstanceGuid)
    except Exception:
        return None
    if not value or value.strip('{}0-') == '':
        return None
    return value


def collect(selected, doc, options, progress=None):
    """Reads the selection for IFC: meshexport.read_objects plus level, ids and
    property rows per object. options: per_object, total, storeys ('auto'|'grid'|'one'),
    psets ('data'|'all'|'none')."""
    from namo import meshexport
    from namo import variants

    psets_mode = options.get('psets', 'data')
    storey_mode = options.get('storeys', 'auto')

    def extra(item, record):
        tris = record['tris']
        record['bottom'] = min(min(p[2] for p in tri) for tri in tris)
        record['level'] = level_property(item) if storey_mode == 'auto' else None
        record['instance_guid'] = instance_guid(item)
        if psets_mode == 'none':
            record['rows'] = []
        else:
            try:
                record['rows'] = variants.all_of(item)
            except Exception:
                record['rows'] = []

    return meshexport.read_objects(selected, per_object=options.get('per_object', DEFAULT_PER_OBJECT),
                                   total=options.get('total', DEFAULT_TOTAL), progress=progress,
                                   identity=True, extra=extra, doc_units=str(doc.Units))


def model_for(read, doc, options, file_name, seed, overrides=None):
    """(model dict for namo.ifc.build, dropped names). Storeys by grid levels need the
    document (Navisworks' own ClosestIntersection when the level property is missing)."""
    from namo import config, meshexport
    doc_units = str(doc.Units)
    records = read['records']
    levels = grid_levels(doc)
    mode = options.get('storeys', 'auto')
    if mode != 'one' and levels:
        # Levels are horizontal, so one lookup per 5 cm of height serves every object
        # whose bottom falls in that band (ClosestIntersection is the slow call).
        per_metre = 1.0 / meshexport.doc_meters(doc_units)
        band = 0.05 * per_metre
        found_by_band = {}
        for record in records:
            if record.get('level') and mode == 'auto':
                continue
            box = meshexport.union_box([record])
            if box is None:
                continue
            bottom = box[0][2] + 0.1 * per_metre
            key = int(round(bottom / band))
            if key not in found_by_band:
                centre = ((box[0][0] + box[1][0]) / 2.0, (box[0][1] + box[1][1]) / 2.0, bottom)
                found_by_band[key] = grid_level_at(doc, centre)
            if found_by_band[key]:
                record['level'] = found_by_band[key]
    storey_mode = 'auto' if mode != 'one' else 'one'
    storeys, keys = plan_storeys(records, levels, storey_mode)
    used = set()
    elements = []
    dropped = []
    skip = DEFAULT_SKIP_TABS if options.get('psets', 'data') == 'data' else ()
    for record, key in zip(records, keys):
        ids = record.get('ids') or {}
        cls, predefined = class_for(record.get('category'), overrides)
        guid_value = choose_guid([ids.get('ifc_guid'), record.get('instance_guid')], seed,
                                 '%s|%s' % (record.get('model'), record.get('name')), used)
        record['weld'] = meshexport.weld_tolerance(record.get('noise'), doc_units)
        element = element_for(record, cls, predefined, guid_value, key,
                              psets_from_rows(record.get('rows'), skip))
        if element is None:
            dropped.append(record.get('name') or '')
            continue
        elements.append(element)
    cfg = config.load()
    title = ''
    try:
        title = str(doc.Title or '')
    except Exception:
        pass
    model = {
        'file_name': file_name,
        'author': config.user_name(),
        'organization': cfg.get('company') or '',
        'app_version': _version(),
        'seed': seed,
        'project': {'name': options.get('project') or cfg.get('project_name') or title or 'Project'},
        'site': {'name': options.get('site') or 'Site'},
        'building': {'name': options.get('building') or title or 'Building'},
        'length_unit': doc_units,
        'storeys': storeys,
        'elements': elements,
    }
    return model, dropped


def _version():
    try:
        import namo
        return namo.__version__
    except Exception:
        return '0'

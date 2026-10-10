# -*- coding: utf-8 -*-
"""A pure IFC4 (ISO 10303-21 STEP) writer for the IFC Exporter, plus the reader its
tests use.

    text = ifc.build(model, progress=None)      # the whole .ifc file as text
    ifc.write(path, model)                      # the same, saved atomically (ASCII)
    parsed = ifc.read(text)                     # {'header': [...], 'entities': {n: (NAME, args)}}

model (plain data, so it is unit tested on CPython and IronPython alike):

    {'file_name': 'Hospital.ifc', 'timestamp': datetime or None, 'epoch': int or None,
     'author': 'amol', 'organization': 'Acme', 'app_version': '0.1.0',
     'seed': 'c:\\jobs\\hospital.nwf',          # makes every derived GlobalId stable
     'project': {'name', 'guid'?}, 'site': {'name', 'guid'?}, 'building': {'name', 'guid'?},
     'length_unit': 'Millimeters',              # str(doc.Units): what coordinates are in
     'storeys': [{'key', 'name', 'elevation', 'guid'?}],
     'elements': [{'guid', 'ifc_class', 'predefined' (enum text or None), 'name',
                   'object_type', 'tag', 'storey' (a storey key or None),
                   'origin' (x, y, z) in model units, 'vertices' [(x, y, z) relative
                   to origin], 'faces' [(i, j, k) 0-based], 'closed' bool,
                   'color' 'RRGGBB' or None, 'transparency' 0..1,
                   'psets' [(name, [(property, value)])]}]}

What it writes (IFC4 ADD2 TC1, Reference View flavoured): owner history; units from the
document (SI with prefix, or conversion-based feet/inches/yards/miles); a 3D model
context with a 'Body' sub-context; IfcProject > IfcSite > IfcBuilding > IfcBuildingStorey
(IfcRelAggregates, local placements, storey elevations); one element per object
(IfcWall, IfcDuctSegment ... or IfcBuildingElementProxy) placed relative to its storey,
geometry as IfcTriangulatedFaceSet over IfcCartesianPointList3D in an
IfcShapeRepresentation 'Body' 'Tessellation'; colour and transparency through
IfcStyledItem > IfcSurfaceStyle > IfcSurfaceStyleShading (shared per colour);
IfcRelContainedInSpatialStructure per storey; property sets of IfcPropertySingleValue
(IfcLabel, IfcText past 255 characters, IfcReal, IfcInteger, IfcBoolean), identical
sets shared, attached with IfcRelDefinesByProperties.

Strings follow ISO 10303-21: apostrophes doubled, backslashes doubled, anything outside
printable ASCII as \\X2\\hhhh\\X0\\ (UTF-16 code units) or \\X4\\hhhhhhhh\\X0\\ (beyond the
BMP). Reals always carry a decimal point. Entities are numbered in creation order and
only ever reference entities written before them.
"""
import datetime
import os
import re
import time
import uuid

from namo import ifcguid

SCHEMA = 'IFC4'
VIEW = 'ViewDefinition [ReferenceView_V1.2]'
LABEL_MAX = 255

# Attribute counts of every entity this writer creates (IFC4 ADD2 TC1). The tests
# check each written entity against this table.
ATTRIBUTES = {
    'IFCPERSON': 8, 'IFCORGANIZATION': 5, 'IFCPERSONANDORGANIZATION': 3, 'IFCAPPLICATION': 4,
    'IFCOWNERHISTORY': 8, 'IFCSIUNIT': 4, 'IFCDIMENSIONALEXPONENTS': 7,
    'IFCMEASUREWITHUNIT': 2, 'IFCCONVERSIONBASEDUNIT': 4, 'IFCUNITASSIGNMENT': 1,
    'IFCCARTESIANPOINT': 1, 'IFCDIRECTION': 1, 'IFCAXIS2PLACEMENT3D': 3,
    'IFCGEOMETRICREPRESENTATIONCONTEXT': 6, 'IFCGEOMETRICREPRESENTATIONSUBCONTEXT': 10,
    'IFCPROJECT': 9, 'IFCSITE': 14, 'IFCBUILDING': 12, 'IFCBUILDINGSTOREY': 10,
    'IFCLOCALPLACEMENT': 2, 'IFCRELAGGREGATES': 6, 'IFCCARTESIANPOINTLIST3D': 1,
    'IFCTRIANGULATEDFACESET': 5, 'IFCCOLOURRGB': 4, 'IFCSURFACESTYLESHADING': 2,
    'IFCSURFACESTYLE': 3, 'IFCSTYLEDITEM': 3, 'IFCSHAPEREPRESENTATION': 4,
    'IFCPRODUCTDEFINITIONSHAPE': 3, 'IFCRELCONTAINEDINSPATIALSTRUCTURE': 6,
    'IFCPROPERTYSINGLEVALUE': 4, 'IFCPROPERTYSET': 5, 'IFCRELDEFINESBYPROPERTIES': 6,
}

# Element classes the exporter may write: attribute count and the default predefined
# type (every one of these enums has NOTDEFINED).
ELEMENT_CLASSES = {
    'IfcBuildingElementProxy': 9, 'IfcWall': 9, 'IfcCurtainWall': 9, 'IfcSlab': 9,
    'IfcRoof': 9, 'IfcCovering': 9, 'IfcBeam': 9, 'IfcColumn': 9, 'IfcMember': 9,
    'IfcPlate': 9, 'IfcFooting': 9, 'IfcStair': 9, 'IfcRamp': 9, 'IfcRailing': 9,
    'IfcFurniture': 9, 'IfcDoor': 13, 'IfcWindow': 13,
    'IfcDuctSegment': 9, 'IfcDuctFitting': 9, 'IfcAirTerminal': 9, 'IfcDamper': 9,
    'IfcPipeSegment': 9, 'IfcPipeFitting': 9, 'IfcValve': 9, 'IfcSanitaryTerminal': 9,
    'IfcFireSuppressionTerminal': 9, 'IfcCableCarrierSegment': 9,
    'IfcCableCarrierFitting': 9, 'IfcLightFixture': 9,
}
for _name in ELEMENT_CLASSES:
    ATTRIBUTES[_name.upper()] = ELEMENT_CLASSES[_name]

# Length units: str(doc.Units) -> ('si', prefix) or ('conversion', name, metres per unit)
LENGTH_UNITS = {
    'Meters': ('si', None), 'Millimeters': ('si', 'MILLI'), 'Centimeters': ('si', 'CENTI'),
    'Kilometers': ('si', 'KILO'), 'Micrometers': ('si', 'MICRO'),
    'Feet': ('conversion', 'FOOT', 0.3048), 'Inches': ('conversion', 'INCH', 0.0254),
    'Yards': ('conversion', 'YARD', 0.9144), 'Miles': ('conversion', 'MILE', 1609.344),
    'Mils': ('conversion', 'MIL', 2.54e-5), 'Microinches': ('conversion', 'MICROINCH', 2.54e-8),
}


# =====================================================================================
# STEP values
# =====================================================================================


class Ref(object):
    """A reference to entity #n."""

    def __init__(self, number):
        self.number = number

    def __repr__(self):
        return '#%d' % self.number


class Enum(object):
    """.VALUE."""

    def __init__(self, value):
        self.value = str(value).upper()


class Typed(object):
    """IFCLABEL('x'): a value of a defined type inside a SELECT."""

    def __init__(self, type_name, value):
        self.type_name = str(type_name).upper()
        self.value = value


class _Derived(object):
    pass


DERIVED = _Derived()


def real(value, digits=12):
    """A STEP REAL: always with a decimal point, exponent as E: 0., 1.5, -2.5E-06."""
    value = float(value)
    if value != value or value in (float('inf'), float('-inf')):
        raise ValueError('IFC cannot hold %r' % value)
    text = '%.*g' % (digits, value)
    if text in ('-0', '0'):
        return '0.'
    mantissa, _e, exponent = text.lower().partition('e')
    if '.' not in mantissa:
        mantissa += '.'
    if exponent:
        sign = ''
        if exponent[0] in '+-':
            sign, exponent = exponent[0], exponent[1:]
        exponent = exponent.lstrip('0') or '0'
        return '%sE%s%s' % (mantissa, '-' if sign == '-' else '', exponent)
    return mantissa


def _code_points(text):
    """Code points of text, joining UTF-16 surrogate pairs (IronPython strings are
    UTF-16, so a character beyond the BMP arrives as two halves there)."""
    out = []
    pending = None
    for ch in text:
        code = ord(ch)
        if pending is not None:
            if 0xDC00 <= code <= 0xDFFF:
                out.append(0x10000 + ((pending - 0xD800) << 10) + (code - 0xDC00))
                pending = None
                continue
            out.append(pending)
            pending = None
        if 0xD800 <= code <= 0xDBFF:
            pending = code
        else:
            out.append(code)
    if pending is not None:
        out.append(pending)
    return out


def encode_string(text):
    """text as an ISO 10303-21 string literal (with the quotes)."""
    out = ["'"]
    run = []           # pending \X2\ code units
    wide = []          # pending \X4\ code points

    def flush():
        if run:
            out.append('\\X2\\' + ''.join('%04X' % c for c in run) + '\\X0\\')
            del run[:]
        if wide:
            out.append('\\X4\\' + ''.join('%08X' % c for c in wide) + '\\X0\\')
            del wide[:]

    for code in _code_points('' if text is None else str(text)):
        if 0x20 <= code <= 0x7E:
            flush()
            ch = chr(code)
            if ch == "'":
                out.append("''")
            elif ch == '\\':
                out.append('\\\\')
            else:
                out.append(ch)
        elif code > 0xFFFF:
            if run:
                flush()
            wide.append(code)
        else:
            if wide:
                flush()
            run.append(code)
    flush()
    out.append("'")
    return ''.join(out)


def _chr(code):
    """A character for a code point on both engines (IronPython needs a surrogate pair
    beyond the BMP)."""
    try:
        return chr(code)
    except ValueError:
        code -= 0x10000
        return chr(0xD800 + (code >> 10)) + chr(0xDC00 + (code & 0x3FF))


def decode_string(literal):
    """The text of a STEP string literal (with or without its quotes): '' and \\\\ and
    \\X2\\..\\X0\\, \\X4\\..\\X0\\, \\X\\hh, \\S\\c."""
    body = literal[1:-1] if literal.startswith("'") and literal.endswith("'") else literal
    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "'" and body[i:i + 2] == "''":
            out.append("'")
            i += 2
        elif ch == '\\':
            if body.startswith('\\\\', i):
                out.append('\\')
                i += 2
            elif body.startswith('\\X2\\', i) or body.startswith('\\X4\\', i):
                width = 4 if body[i + 2] == '2' else 8
                end = body.index('\\X0\\', i + 4)
                hexes = body[i + 4:end]
                codes = [int(hexes[k:k + width], 16) for k in range(0, len(hexes), width)]
                if width == 4:
                    text = ''.join(chr(c) for c in codes)
                    out.append(''.join(_chr(c) for c in _code_points(text)))
                else:
                    out.append(''.join(_chr(c) for c in codes))
                i = end + 4
            elif body.startswith('\\X\\', i):
                out.append(chr(int(body[i + 3:i + 5], 16)))
                i += 5
            elif body.startswith('\\S\\', i):
                out.append(chr(ord(body[i + 3]) + 128))
                i += 4
            else:
                out.append(ch)
                i += 1
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def encode(value):
    """One attribute value as STEP text."""
    if value is None:
        return '$'
    if value is DERIVED:
        return '*'
    if isinstance(value, Ref):
        return '#%d' % value.number
    if isinstance(value, Enum):
        return '.%s.' % value.value
    if isinstance(value, Typed):
        return '%s(%s)' % (value.type_name, encode(value.value))
    if isinstance(value, bool):
        return '.T.' if value else '.F.'
    if isinstance(value, int):
        return '%d' % value
    if isinstance(value, float):
        return real(value)
    if isinstance(value, str):
        return encode_string(value)
    if isinstance(value, (list, tuple)):
        return '(' + ','.join(encode(v) for v in value) + ')'
    raise TypeError('cannot write %r to IFC' % (value,))


def label(text, limit=LABEL_MAX):
    """Text cut to an IfcLabel (255 characters), None for empty."""
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    return text[:limit]


class Step(object):
    """The DATA section under construction: add() writes '#n=NAME(args);' and returns
    the Ref. Every argument is encoded immediately, so a forward reference cannot
    happen."""

    def __init__(self):
        self.lines = []
        self.count = 0

    def add(self, name, *args):
        self.count += 1
        self.lines.append('#%d=%s(%s);' % (self.count, name.upper(), ','.join(encode(a) for a in args)))
        return Ref(self.count)

    def add_raw(self, name, arg_text):
        """For huge lists already formatted (point and index lists)."""
        self.count += 1
        self.lines.append('#%d=%s(%s);' % (self.count, name.upper(), arg_text))
        return Ref(self.count)


# =====================================================================================
# GlobalIds and units
# =====================================================================================


def guid(seed, *parts):
    """A stable GlobalId from a seed and a role: the same document exported twice keeps
    its project, storey, property set and relationship ids."""
    text = 'playground-ifc|%s|%s' % (seed or '', '|'.join(str(p) for p in parts))
    return ifcguid.compress(uuid.uuid5(uuid.NAMESPACE_URL, text).hex)


def length_unit(doc_units):
    """LENGTH_UNITS entry for str(doc.Units); ValueError for an unknown name."""
    name = str(doc_units)
    if name not in LENGTH_UNITS:
        raise ValueError('Unknown document units %r' % name)
    return LENGTH_UNITS[name]


def is_imperial(doc_units):
    return length_unit(doc_units)[0] == 'conversion'


def _units(step, doc_units):
    spec = length_unit(doc_units)
    metre = None
    if spec[0] == 'si':
        length = step.add('IfcSIUnit', DERIVED, Enum('LENGTHUNIT'), Enum(spec[1]) if spec[1] else None,
                          Enum('METRE'))
    else:
        metre = step.add('IfcSIUnit', DERIVED, Enum('LENGTHUNIT'), None, Enum('METRE'))
        dims = step.add('IfcDimensionalExponents', 1, 0, 0, 0, 0, 0, 0)
        factor = step.add('IfcMeasureWithUnit', Typed('IfcLengthMeasure', float(spec[2])), metre)
        length = step.add('IfcConversionBasedUnit', dims, Enum('LENGTHUNIT'), spec[1], factor)
    if spec[0] == 'conversion':
        square = step.add('IfcSIUnit', DERIVED, Enum('AREAUNIT'), None, Enum('SQUARE_METRE'))
        cube = step.add('IfcSIUnit', DERIVED, Enum('VOLUMEUNIT'), None, Enum('CUBIC_METRE'))
        dims2 = step.add('IfcDimensionalExponents', 2, 0, 0, 0, 0, 0, 0)
        dims3 = step.add('IfcDimensionalExponents', 3, 0, 0, 0, 0, 0, 0)
        area = step.add('IfcConversionBasedUnit', dims2, Enum('AREAUNIT'), 'SQUARE FOOT',
                        step.add('IfcMeasureWithUnit', Typed('IfcAreaMeasure', 0.09290304), square))
        volume = step.add('IfcConversionBasedUnit', dims3, Enum('VOLUMEUNIT'), 'CUBIC FOOT',
                          step.add('IfcMeasureWithUnit', Typed('IfcVolumeMeasure', 0.028316846592), cube))
    else:
        area = step.add('IfcSIUnit', DERIVED, Enum('AREAUNIT'), None, Enum('SQUARE_METRE'))
        volume = step.add('IfcSIUnit', DERIVED, Enum('VOLUMEUNIT'), None, Enum('CUBIC_METRE'))
    angle = step.add('IfcSIUnit', DERIVED, Enum('PLANEANGLEUNIT'), None, Enum('RADIAN'))
    return step.add('IfcUnitAssignment', [length, area, volume, angle])


# =====================================================================================
# Property values
# =====================================================================================


def nominal_value(value):
    """(Typed value, kind) for a property value, or None to skip it: text is IfcLabel
    (IfcText past 255 characters), bool IfcBoolean, int IfcInteger, float IfcReal,
    dates and points as IfcLabel text."""
    if value is None:
        return None
    if isinstance(value, bool):
        return Typed('IfcBoolean', value)
    if isinstance(value, int):
        if -2147483648 <= value <= 2147483647:
            return Typed('IfcInteger', value)
        return Typed('IfcLabel', str(value))
    if isinstance(value, float):
        if value != value or value in (float('inf'), float('-inf')):
            return None
        return Typed('IfcReal', value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return Typed('IfcLabel', value.isoformat())
    if isinstance(value, (tuple, list)):
        text = ', '.join(str(v) for v in value)
    else:
        text = str(value)
    if not text.strip():
        return None
    if len(text) > LABEL_MAX:
        return Typed('IfcText', text)
    return Typed('IfcLabel', text)


def clean_psets(psets):
    """[(name, [(property, Typed)])] with blank names, unwritable values, duplicate
    property names (first wins) and empty sets dropped. Pure; keeps order."""
    out = []
    used_sets = set()
    for name, props in psets or []:
        set_name = label(name)
        if set_name is None or set_name.lower() in used_sets:
            continue
        seen = set()
        cleaned = []
        for prop, value in props or []:
            prop_name = label(prop)
            typed = nominal_value(value)
            if prop_name is None or typed is None or prop_name.lower() in seen:
                continue
            seen.add(prop_name.lower())
            cleaned.append((prop_name, typed))
        if cleaned:
            used_sets.add(set_name.lower())
            out.append((set_name, cleaned))
    return out


def _pset_key(name, props):
    return (name, tuple((p, t.type_name, encode(t.value)) for p, t in props))


# =====================================================================================
# The file
# =====================================================================================


def _epoch(model):
    if model.get('epoch') is not None:
        return int(model['epoch'])
    stamp = model.get('timestamp')
    if isinstance(stamp, datetime.datetime):
        return int(time.mktime(stamp.timetuple()))
    return int(time.time())


def _stamp_text(model):
    stamp = model.get('timestamp')
    if isinstance(stamp, datetime.datetime):
        return stamp.replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%S')
    if stamp:
        return str(stamp)
    return datetime.datetime.fromtimestamp(_epoch(model)).strftime('%Y-%m-%dT%H:%M:%S')


def header(model):
    """The HEADER section lines."""
    author = model.get('author') or ''
    organization = model.get('organization') or ''
    app = 'Playground %s' % (model.get('app_version') or '')
    return [
        'FILE_DESCRIPTION((%s),%s);' % (encode_string(VIEW), encode_string('2;1')),
        'FILE_NAME(%s,%s,(%s),(%s),%s,%s,%s);' % (
            encode_string(model.get('file_name') or 'export.ifc'), encode_string(_stamp_text(model)),
            encode_string(author), encode_string(organization), encode_string(app.strip()),
            encode_string('Playground IFC Exporter for Navisworks'), encode_string('')),
        'FILE_SCHEMA((%s));' % encode_string(SCHEMA),
    ]


def _points_text(vertices):
    return '((' + '),('.join('%s,%s,%s' % (real(x, 10), real(y, 10), real(z, 10))
                             for x, y, z in vertices) + '))'


def _index_text(faces):
    return '((' + '),('.join('%d,%d,%d' % (i + 1, j + 1, k + 1) for i, j, k in faces) + '))'


def check_element(element):
    """A sentence describing what is wrong with an element dict, or None."""
    cls = element.get('ifc_class')
    if cls not in ELEMENT_CLASSES:
        return 'unknown IFC class %r' % (cls,)
    if not ifcguid.is_valid(element.get('guid')):
        return 'invalid GlobalId %r' % (element.get('guid'),)
    vertices = element.get('vertices') or []
    faces = element.get('faces') or []
    if len(vertices) < 3 or not faces:
        return 'no triangles'
    count = len(vertices)
    for face in faces:
        for index in face:
            if index < 0 or index >= count:
                return 'a triangle points at vertex %d of %d' % (index, count)
    return None


def build(model, progress=None):
    """The complete .ifc text for a model dict (see the module docstring).
    progress(fraction, label) is called per 50 elements; returning False raises
    RuntimeError('cancelled')."""
    seed = model.get('seed') or ''
    step = Step()
    author = model.get('author') or 'Playground'
    organization = model.get('organization') or 'Playground'

    person = step.add('IfcPerson', None, label(author), None, None, None, None, None, None)
    org = step.add('IfcOrganization', None, label(organization), None, None, None)
    user = step.add('IfcPersonAndOrganization', person, org, None)
    developer = step.add('IfcOrganization', None, 'Playground', None, None, None)
    app = step.add('IfcApplication', developer, label(model.get('app_version') or '0'),
                   'Playground IFC Exporter', 'Playground')
    history = step.add('IfcOwnerHistory', user, app, None, Enum('NOCHANGE'), None, None, None, _epoch(model))

    units = _units(step, model.get('length_unit') or 'Meters')
    origin = step.add('IfcCartesianPoint', (0.0, 0.0, 0.0))
    z_axis = step.add('IfcDirection', (0.0, 0.0, 1.0))
    x_axis = step.add('IfcDirection', (1.0, 0.0, 0.0))
    world = step.add('IfcAxis2Placement3D', origin, z_axis, x_axis)
    context = step.add('IfcGeometricRepresentationContext', None, 'Model', 3, 1e-5, world, None)
    body = step.add('IfcGeometricRepresentationSubContext', 'Body', 'Model', DERIVED, DERIVED, DERIVED,
                    DERIVED, context, None, Enum('MODEL_VIEW'), None)

    project_info = model.get('project') or {}
    site_info = model.get('site') or {}
    building_info = model.get('building') or {}
    project = step.add('IfcProject', project_info.get('guid') or guid(seed, 'project'), history,
                       label(project_info.get('name')) or 'Project', None, None, None, None, [context], units)

    def placement(relative_to, xyz):
        point = step.add('IfcCartesianPoint', tuple(float(v) for v in xyz))
        axes = step.add('IfcAxis2Placement3D', point, None, None)
        return step.add('IfcLocalPlacement', relative_to, axes)

    site_place = placement(None, (0.0, 0.0, 0.0))
    site = step.add('IfcSite', site_info.get('guid') or guid(seed, 'site'), history,
                    label(site_info.get('name')) or 'Site', None, None, site_place, None, None,
                    Enum('ELEMENT'), None, None, None, None, None)
    building_place = placement(site_place, (0.0, 0.0, 0.0))
    building = step.add('IfcBuilding', building_info.get('guid') or guid(seed, 'building'), history,
                        label(building_info.get('name')) or 'Building', None, None, building_place, None,
                        None, Enum('ELEMENT'), None, None, None)
    step.add('IfcRelAggregates', guid(seed, 'rel', 'project-site'), history, None, None, project, [site])
    step.add('IfcRelAggregates', guid(seed, 'rel', 'site-building'), history, None, None, site, [building])

    elements = list(model.get('elements') or [])
    storeys = list(model.get('storeys') or [])
    keys = set(s.get('key') for s in storeys)
    if any(e.get('storey') not in keys for e in elements):
        storeys.append({'key': None, 'name': 'No level', 'elevation': 0.0})
    storeys.sort(key=lambda s: (float(s.get('elevation') or 0.0), _natural(s.get('name'))))
    storey_ref = {}
    storey_place = {}
    storey_elev = {}
    storey_refs = []
    for index, info in enumerate(storeys):
        elevation = float(info.get('elevation') or 0.0)
        place = placement(building_place, (0.0, 0.0, elevation))
        ref = step.add('IfcBuildingStorey', info.get('guid') or guid(seed, 'storey', info.get('name'), index),
                       history, label(info.get('name')) or 'Level', None, None, place, None, None,
                       Enum('ELEMENT'), elevation)
        storey_ref[info.get('key')] = ref
        storey_place[info.get('key')] = place
        storey_elev[info.get('key')] = elevation
        storey_refs.append(ref)
    if storey_refs:
        step.add('IfcRelAggregates', guid(seed, 'rel', 'building-storeys'), history, None, None,
                 building, storey_refs)

    styles = {}
    contained = dict((info.get('key'), []) for info in storeys)
    pset_refs = []
    pset_index = {}
    pset_users = {}
    written = 0
    used_guids = set()
    total = len(elements)
    for number, element in enumerate(elements):
        if progress is not None and number % 50 == 0:
            if progress(float(number) / max(1, total), 'Writing %s of %s objects' % (
                    '{:,}'.format(number + 1), '{:,}'.format(total))) == False:  # noqa: E712
                raise RuntimeError('cancelled')
        problem = check_element(element)
        if problem is None and element['guid'] in used_guids:
            problem = 'GlobalId %s is used twice' % element['guid']
        if problem is not None:
            raise ValueError('%s: %s' % (element.get('name') or 'element', problem))
        used_guids.add(element['guid'])
        key = element.get('storey') if element.get('storey') in storey_ref else None
        points = step.add_raw('IfcCartesianPointList3D', _points_text(element['vertices']))
        faceset = step.add_raw('IfcTriangulatedFaceSet', '%s,$,%s,%s,$' % (
            encode(points), encode(bool(element.get('closed'))), _index_text(element['faces'])))
        color = (str(element.get('color') or 'BFBFBF')).upper()
        transparency = round(max(0.0, min(1.0, float(element.get('transparency') or 0.0))), 3)
        style_key = (color, transparency)
        if style_key not in styles:
            r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
            colour = step.add('IfcColourRgb', None, round(r / 255.0, 6), round(g / 255.0, 6), round(b / 255.0, 6))
            shading = step.add('IfcSurfaceStyleShading', colour, transparency if transparency > 0 else None)
            styles[style_key] = step.add('IfcSurfaceStyle', color if not transparency else '%s %d%%' % (
                color, int(round((1 - transparency) * 100))), Enum('BOTH'), [shading])
        step.add('IfcStyledItem', faceset, [styles[style_key]], None)
        shape = step.add('IfcShapeRepresentation', body, 'Body', 'Tessellation', [faceset])
        product = step.add('IfcProductDefinitionShape', None, None, [shape])
        ox, oy, oz = element.get('origin') or (0.0, 0.0, 0.0)
        place = placement(storey_place[key], (ox, oy, oz - storey_elev[key]))
        cls = element['ifc_class']
        predefined = Enum(element.get('predefined') or 'NOTDEFINED')
        common = [element['guid'], history, label(element.get('name')) or cls[3:], None,
                  label(element.get('object_type')), place, product, label(element.get('tag'))]
        if ELEMENT_CLASSES[cls] == 13:
            args = common + [None, None, predefined, None, None]
        else:
            args = common + [predefined]
        ref = step.add(cls, *args)
        contained[key].append(ref)
        for set_name, props in clean_psets(element.get('psets')):
            pkey = _pset_key(set_name, props)
            if pkey not in pset_index:
                values = [step.add('IfcPropertySingleValue', prop, None, typed, None) for prop, typed in props]
                pset_index[pkey] = len(pset_refs)
                pset_refs.append(step.add('IfcPropertySet', guid(seed, 'pset', len(pset_refs), set_name),
                                          history, set_name, None, values))
                pset_users[pset_index[pkey]] = []
            pset_users[pset_index[pkey]].append(ref)
        written += 1

    for index, info in enumerate(storeys):
        members = contained.get(info.get('key')) or []
        if members:
            step.add('IfcRelContainedInSpatialStructure', guid(seed, 'rel', 'contained', info.get('name'), index),
                     history, None, None, members, storey_ref[info.get('key')])
    for index, ref in enumerate(pset_refs):
        step.add('IfcRelDefinesByProperties', guid(seed, 'rel', 'pset', index), history, None, None,
                 pset_users[index], ref)
    if progress is not None:
        progress(1.0, 'Wrote %s objects' % '{:,}'.format(written))
    lines = ['ISO-10303-21;', 'HEADER;'] + header(model) + ['ENDSEC;', 'DATA;'] + step.lines + \
        ['ENDSEC;', 'END-ISO-10303-21;']
    return '\n'.join(lines) + '\n'


def write(path, model, progress=None):
    """Writes build(model) to path (ASCII, atomic). Returns path."""
    from namo import paths
    return paths.atomic_write_bytes(path, build(model, progress).encode('ascii'))


def _natural(text):
    return re.sub(r'\d+', lambda m: m.group(0).zfill(12), str(text or '').lower())


# =====================================================================================
# Reader (for tests and sanity checks)
# =====================================================================================


_TOKEN = re.compile(r"\s*(?:(#\d+)|('(?:[^']|'')*')|(\.[A-Z0-9_]+\.)|"
                    r"([-+]?\d+\.\d*(?:E[-+]?\d+)?)|([-+]?\d+)|(\$)|(\*)|([A-Z][A-Z0-9_]*)|(\()|(\))|(,))")


class Value(object):
    """A parsed typed value: name and inner value."""

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        return '%s(%r)' % (self.name, self.value)


def _parse_args(text):
    """The argument list of one entity: refs as Ref, strings decoded, enums as Enum,
    reals as float, integers as int, '$' None, '*' DERIVED, typed values as Value,
    lists as lists."""
    tokens = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match or match.end() == pos:
            if text[pos:].strip() == '':
                break
            raise ValueError('cannot read %r' % text[pos:pos + 30])
        pos = match.end()
        tokens.append(match)
    index = [0]

    def value():
        m = tokens[index[0]]
        index[0] += 1
        ref, string, enum, flt, integer, null, star, name, lpar, rpar, comma = m.groups()
        if ref:
            return Ref(int(ref[1:]))
        if string is not None:
            return decode_string(string)
        if enum:
            text_ = enum[1:-1]
            if text_ in ('T', 'F'):
                return text_ == 'T'
            return Enum(text_)
        if flt:
            return float(flt)
        if integer:
            return int(integer)
        if null:
            return None
        if star:
            return DERIVED
        if name:
            index[0] += 1          # '('
            inner = value()
            index[0] += 1          # ')'
            return Value(name, inner)
        if lpar:
            items = []
            if tokens[index[0]].group(10):
                index[0] += 1
                return items
            while True:
                items.append(value())
                closing = tokens[index[0]]
                index[0] += 1
                if closing.group(10):
                    return items
        raise ValueError('unexpected token %r' % m.group(0))

    if not tokens:
        return []
    out = []
    while index[0] < len(tokens):
        out.append(value())
        if index[0] < len(tokens):
            index[0] += 1          # ','
    return out


_ENTITY = re.compile(r'^#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\);\s*$', re.S)


def read(text):
    """{'header': [lines], 'entities': {number: (NAME, [args])}} from STEP text
    written one entity per line (as build() writes). ValueError on anything else."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != 'ISO-10303-21;' or lines[-1].strip() != 'END-ISO-10303-21;':
        raise ValueError('not an ISO 10303-21 file')
    try:
        header_start = lines.index('HEADER;')
        data_start = lines.index('DATA;')
    except ValueError:
        raise ValueError('missing HEADER or DATA section')
    head = lines[header_start + 1:data_start - 1]
    entities = {}
    for line in lines[data_start + 1:]:
        if line in ('ENDSEC;', 'END-ISO-10303-21;'):
            continue
        match = _ENTITY.match(line)
        if not match:
            raise ValueError('cannot read entity line %r' % line[:60])
        number = int(match.group(1))
        if number in entities:
            raise ValueError('entity #%d written twice' % number)
        entities[number] = (match.group(2), _parse_args(match.group(3)))
    return {'header': head, 'entities': entities}


def references(args):
    """Every Ref number inside a parsed argument list."""
    out = []
    stack = list(args)
    while stack:
        item = stack.pop()
        if isinstance(item, Ref):
            out.append(item.number)
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, Value):
            stack.append(item.value)
    return out


def file_stem_ok(name):
    """True when a file name ends in .ifc (case-insensitive)."""
    return os.path.splitext(str(name or ''))[1].lower() == '.ifc'

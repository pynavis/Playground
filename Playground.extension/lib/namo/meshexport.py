# -*- coding: utf-8 -*-
"""Geometry out of Navisworks: glTF 2.0 binary (.glb), OBJ + MTL, binary STL and DXF
3D faces, from the selected objects' own triangles.

Pure half (unit tested on CPython and IronPython, byte-identical output on both):

    meshes = meshexport.build_meshes(records, fmt='glb', doc_units='Millimeters',
                                     shift=(512000.0, 304000.0, 0.0))
    data = meshexport.glb_bytes(meshes, title='Hospital')     # also obj_text/mtl_text,
                                                              # stl_bytes, dxf_text
    gltf, binary = meshexport.parse_glb(data)                 # the reader the tests use

A record is one object: {'name', 'model', 'category', 'color' 'RRGGBB' or None,
'transparency' 0..1, 'tris' [((x, y, z), (x, y, z), (x, y, z))] in WORLD document units,
'noise' (float32 coordinate noise in document units), 'extras' {...}}. build_meshes welds
each record (shared corners merged, collapsed triangles dropped), subtracts the local
origin, converts units and axes for the format and returns meshes {'name', 'model',
'category', 'color', 'alpha', 'vertices', 'faces', 'translation', 'extras'} whose
vertices are relative to 'translation' (the centre of the object, so float32 storage
keeps full precision however far the model sits from 0,0,0).

Format rules (the reasons are in each writer's docstring):
  glb  metres, Y up (x, y, z) -> (x, z, -y), one node and mesh per object under a node
       per model, PBR materials from the item colours (sRGB converted to linear),
       uint16 or uint32 indices, accessors with min/max, extras with the chosen data.
  obj  chosen units, Y up by default (what Blender, 3ds Max and most viewers import),
       a group per object, one material per colour in the .mtl beside it.
  stl  chosen units, Z up, binary, facet normals from the winding.
  dxf  chosen units, Z up, DXF R12 structure with 3DFACE entities, a layer per model
       or category, the nearest AutoCAD colour index (62) plus true colour (420).

API half: read_objects() walks the selection's objects with a per-object and a total
triangle budget, reading triangles (namo.mesh.item_triangles), colour (namo.paint),
identity (namo.items) and chosen properties. IronPython only, like item_triangles.
"""
import array
import datetime
import json
import math
import os
import re
import struct
import sys

FORMATS = [('glb', 'glTF binary (.glb)'), ('obj', 'OBJ with materials (.obj + .mtl)'),
           ('stl', 'STL, binary (.stl)'), ('dxf', 'DXF 3D faces (.dxf)')]
FORMAT_NAMES = dict(FORMATS)
EXTENSIONS = {'glb': '.glb', 'obj': '.obj', 'stl': '.stl', 'dxf': '.dxf'}
FILTERS = {
    'glb': 'glTF binary (*.glb)|*.glb',
    'obj': 'OBJ files (*.obj)|*.obj',
    'stl': 'STL files (*.stl)|*.stl',
    'dxf': 'DXF files (*.dxf)|*.dxf',
}

# Target units a user may pick for OBJ, STL and DXF ('doc' keeps the document's units).
UNIT_CHOICES = [('doc', 'Document units'), ('m', 'Metres'), ('mm', 'Millimetres'),
                ('ft', 'Feet'), ('in', 'Inches')]
UNIT_METERS = {'m': 1.0, 'mm': 0.001, 'cm': 0.01, 'ft': 0.3048, 'in': 0.0254}
UNIT_WORDS = {'m': 'metres', 'mm': 'millimetres', 'cm': 'centimetres', 'ft': 'feet',
              'in': 'inches'}

DOC_UNIT_METERS = {
    'Meters': 1.0, 'Centimeters': 0.01, 'Millimeters': 0.001, 'Feet': 0.3048,
    'Inches': 0.0254, 'Yards': 0.9144, 'Kilometers': 1000.0, 'Micrometers': 1e-6,
    'Microinches': 2.54e-8, 'Mils': 2.54e-5, 'Miles': 1609.344,
}

FALLBACK_COLOR = 'BFBFBF'          # objects whose colour cannot be read
DEFAULT_PER_OBJECT = 200000
DEFAULT_TOTAL = 2000000
GENERATOR = 'Playground Geometry Exporter'

# glTF constants (spec 2.0)
_FLOAT = 5126
_UINT16 = 5123
_UINT32 = 5125
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963
_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942


# =====================================================================================
# Numbers and JSON that print the same on every engine
# =====================================================================================


class Exact(object):
    """A number already formatted (min/max of float32 data), written as is."""

    def __init__(self, text):
        self.text = text


def num_text(value, digits=15):
    """A JSON/text number: '%.<digits>g' with the exponent kept valid and -0 as 0.
    IronPython's repr() is not shortest-round-trip, so nothing here uses it."""
    value = float(value)
    if value != value or value in (float('inf'), float('-inf')):
        raise ValueError('not a finite number')
    text = '%.*g' % (digits, value)
    if text in ('-0', '-0.0'):
        text = '0'
    return text


def f32(value):
    """value rounded to float32, as a double."""
    return struct.unpack('<f', struct.pack('<f', float(value)))[0]


def exact32(value):
    """The float32 nearest value, printed exactly (17 significant digits round-trip
    a double, and a float32 is a double)."""
    return Exact(num_text(f32(value), 17))


def json_text(value):
    """Compact JSON with sorted keys, ASCII only, floats via num_text: deterministic
    across CPython and IronPython. Non-finite floats become null."""
    out = []
    _emit(value, out)
    return ''.join(out)


def _emit(value, out):
    if value is None:
        out.append('null')
    elif value is True:
        out.append('true')
    elif value is False:
        out.append('false')
    elif isinstance(value, Exact):
        out.append(value.text)
    elif isinstance(value, bool):
        out.append('true' if value else 'false')
    elif isinstance(value, int):
        out.append('%d' % value)
    elif isinstance(value, float):
        try:
            out.append(num_text(value))
        except ValueError:
            out.append('null')
    elif isinstance(value, str):
        out.append(json.dumps(value, ensure_ascii=True))
    elif isinstance(value, dict):
        out.append('{')
        first = True
        for key in sorted(value, key=lambda k: str(k)):
            if not first:
                out.append(',')
            first = False
            out.append(json.dumps(str(key), ensure_ascii=True))
            out.append(':')
            _emit(value[key], out)
        out.append('}')
    elif isinstance(value, (list, tuple)):
        out.append('[')
        for index, item in enumerate(value):
            if index:
                out.append(',')
            _emit(item, out)
        out.append(']')
    elif isinstance(value, (datetime.datetime, datetime.date)):
        out.append(json.dumps(value.isoformat(), ensure_ascii=True))
    else:
        out.append(json.dumps(str(value), ensure_ascii=True))


def json_value(value):
    """A property value as something JSON can hold: text, number, bool, list."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float('inf'), float('-inf')) else None
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return str(value)


def _pack(code, values):
    """Little-endian bytes of values: array when its item size is right (fast on both
    engines), struct otherwise."""
    size = struct.calcsize('<' + code)
    try:
        data = array.array(code, values)
        if data.itemsize == size:
            if sys.byteorder != 'little':
                data.byteswap()
            return data.tobytes()
    except (OverflowError, TypeError, ValueError):
        pass
    values = list(values)
    return struct.pack('<%d%s' % (len(values), code), *values)


# =====================================================================================
# Colours
# =====================================================================================


def parse_color(value):
    """'RRGGBB' upper case, or None."""
    if value is None:
        return None
    text = str(value).strip().lstrip('#')
    if len(text) != 6:
        return None
    try:
        int(text, 16)
    except ValueError:
        return None
    return text.upper()


def rgb(hex_value):
    text = parse_color(hex_value) or FALLBACK_COLOR
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def srgb_to_linear(channel):
    """One sRGB channel 0..1 to linear light 0..1 (glTF baseColorFactor is linear)."""
    c = float(channel)
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _hsv_rgb(hue, sat, val):
    h = (hue % 360) / 60.0
    i = int(h)
    f = h - i
    p = val * (1 - sat)
    q = val * (1 - sat * f)
    t = val * (1 - sat * (1 - f))
    r, g, b = [(val, t, p), (q, val, p), (p, val, t), (p, q, val), (t, p, val), (val, p, q)][i % 6]
    return (int(r), int(g), int(b))


def aci_palette():
    """The 256 AutoCAD Color Index colours as (r, g, b); index 0 (ByBlock) is black.
    10..249 follow the ACI pattern: 24 hues 15 degrees apart, each at five values
    (255, 165, 127, 76, 38) in full and half saturation; 250..255 are greys. It matches
    the standard table to within one step per channel, which is all a nearest-colour
    pick needs (the exact colour travels in group 420)."""
    palette = [(0, 0, 0), (255, 0, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255),
               (0, 0, 255), (255, 0, 255), (255, 255, 255), (128, 128, 128), (192, 192, 192)]
    values = [255, 165, 127, 76, 38]
    for index in range(10, 250):
        group, step = divmod(index - 10, 10)
        value = values[step // 2]
        sat = 1.0 if step % 2 == 0 else 0.5
        palette.append(_hsv_rgb(group * 15, sat, value))
    palette.extend([(51, 51, 51), (91, 91, 91), (132, 132, 132), (173, 173, 173),
                    (214, 214, 214), (255, 255, 255)])
    return palette


def nearest_aci(hex_value, palette=None):
    """The AutoCAD Color Index (1..255) closest to a colour; ties take the lower index."""
    palette = palette or aci_palette()
    r, g, b = rgb(hex_value)
    best, best_d = 7, None
    for index in range(1, 256):
        pr, pg, pb = palette[index]
        d = (pr - r) * (pr - r) + (pg - g) * (pg - g) + (pb - b) * (pb - b)
        if best_d is None or d < best_d:
            best, best_d = index, d
    return best


def true_color(hex_value):
    """DXF group 420: 0x00RRGGBB as an int."""
    r, g, b = rgb(hex_value)
    return (r << 16) | (g << 8) | b


# =====================================================================================
# Preparing meshes
# =====================================================================================


def doc_meters(doc_units):
    """Metres per document unit. ValueError for an unknown unit name."""
    name = str(doc_units)
    if name not in DOC_UNIT_METERS:
        raise ValueError('Unknown document units %r' % name)
    return DOC_UNIT_METERS[name]


def target_units(fmt, choice, doc_units):
    """(scale from document units, unit word for messages) for a format: glTF is always
    metres; 'doc' keeps document units."""
    per_doc = doc_meters(doc_units)
    if fmt == 'glb':
        return per_doc, 'metres'
    if not choice or choice == 'doc':
        return 1.0, str(doc_units).lower()
    if choice not in UNIT_METERS:
        raise ValueError('Unknown units %r' % choice)
    return per_doc / UNIT_METERS[choice], UNIT_WORDS[choice]


def y_up(point):
    """Navisworks Z up to glTF / OBJ Y up, keeping a right-handed frame:
    (x, y, z) -> (x, z, -y)."""
    return (point[0], point[2], -point[1])


def nice_step(doc_units):
    """The rounding step of a local origin in document units: about a metre or a foot,
    so the offset reads cleanly."""
    return {'Millimeters': 1000.0, 'Centimeters': 100.0, 'Inches': 12.0,
            'Micrometers': 1e6, 'Mils': 12000.0, 'Microinches': 12e6,
            'Kilometers': 0.001, 'Miles': 0.001}.get(str(doc_units), 1.0)


def local_origin(box, doc_units):
    """The point to subtract for 'shift to local origin': the box's plan centre and its
    bottom, rounded to whole metres or feet (in document units). None without a box."""
    if box is None:
        return None
    step = nice_step(doc_units)

    def snap(value):
        return round(value / step) * step
    cx = (box[0][0] + box[1][0]) / 2.0
    cy = (box[0][1] + box[1][1]) / 2.0
    return (snap(cx), snap(cy), math.floor(box[0][2] / step) * step)


def _points_of(record):
    """Every corner of a record: its welded vertices, or its raw triangles."""
    if record.get('mesh') is not None:
        for point in record['mesh'][0]:
            yield point
        return
    for tri in record.get('tris') or []:
        for point in tri:
            yield point


def union_box(records):
    """((xmin, ymin, zmin), (xmax, ymax, zmax)) over every record, or None."""
    low = [None, None, None]
    high = [None, None, None]
    for record in records:
        for point in _points_of(record):
            for axis in range(3):
                value = point[axis]
                if low[axis] is None or value < low[axis]:
                    low[axis] = value
                if high[axis] is None or value > high[axis]:
                    high[axis] = value
    if low[0] is None:
        return None
    return (tuple(low), tuple(high))


def weld_tolerance(noise, doc_units):
    """A weld grid: a few times the float32 noise, never under a micrometre."""
    floor = 1e-6 / doc_meters(doc_units)
    return max(float(noise or 0.0) * 4.0, floor)


def _weld(tris, tol):
    """(vertices, faces) with shared corners merged on a tol grid; collapsed triangles
    dropped. Same rule as namo.mesh.weld (kept here so this module stays importable
    without the API half)."""
    index_of = {}
    vertices = []
    faces = []
    for tri in tris:
        ids = []
        for point in tri:
            key = (int(round(point[0] / tol)), int(round(point[1] / tol)), int(round(point[2] / tol)))
            found = index_of.get(key)
            if found is None:
                found = len(vertices)
                index_of[key] = found
                vertices.append((float(point[0]), float(point[1]), float(point[2])))
            ids.append(found)
        if ids[0] != ids[1] and ids[1] != ids[2] and ids[0] != ids[2]:
            faces.append((ids[0], ids[1], ids[2]))
    return vertices, faces


def build_meshes(records, fmt, doc_units, shift=None, units_choice='doc', obj_y_up=True):
    """Meshes ready for a writer (see the module docstring). Records with no triangle
    left after welding are dropped (their names are in the second value).
    Returns (meshes, dropped_names)."""
    scale, _word = target_units(fmt, units_choice, doc_units)
    sx, sy, sz = shift if shift else (0.0, 0.0, 0.0)
    to_y = fmt == 'glb' or (fmt == 'obj' and obj_y_up)
    meshes = []
    dropped = []
    for record in records:
        if record.get('mesh') is not None:
            vertices, faces = record['mesh']
        else:
            vertices, faces = _weld(record.get('tris') or [], weld_tolerance(record.get('noise'), doc_units))
        if not faces:
            dropped.append(record.get('name') or '')
            continue
        moved = []
        for x, y, z in vertices:
            point = ((x - sx) * scale, (y - sy) * scale, (z - sz) * scale)
            moved.append(y_up(point) if to_y else point)
        low = [min(p[a] for p in moved) for a in range(3)]
        high = [max(p[a] for p in moved) for a in range(3)]
        centre = tuple((low[a] + high[a]) / 2.0 for a in range(3))
        if fmt == 'glb':
            local = [(p[0] - centre[0], p[1] - centre[1], p[2] - centre[2]) for p in moved]
            translation = centre
        else:
            local = moved
            translation = (0.0, 0.0, 0.0)
        transparency = record.get('transparency') or 0.0
        meshes.append({
            'name': record.get('name') or 'Object',
            'model': record.get('model') or '',
            'category': record.get('category') or '',
            'color': parse_color(record.get('color')) or FALLBACK_COLOR,
            'alpha': max(0.0, min(1.0, 1.0 - float(transparency))),
            'vertices': local,
            'faces': faces,
            'translation': translation,
            'extras': record.get('extras') or {},
        })
    return meshes, dropped


def counts(meshes):
    """(objects, vertices, triangles)."""
    return (len(meshes), sum(len(m['vertices']) for m in meshes),
            sum(len(m['faces']) for m in meshes))


# =====================================================================================
# glTF 2.0 binary
# =====================================================================================


def _pad(data, fill):
    extra = (4 - len(data) % 4) % 4
    return data + fill * extra


def material_key(mesh):
    return (mesh['color'], round(mesh['alpha'], 4))


def gltf_material(color, alpha):
    """A metallic-roughness material: baseColorFactor in LINEAR light (glTF rule),
    matte and non-metallic like most building materials, double-sided because CAD
    meshes are often open or inconsistently wound."""
    r, g, b = rgb(color)
    material = {
        'name': color if alpha >= 1.0 else '%s %d%%' % (color, int(round(alpha * 100))),
        'pbrMetallicRoughness': {
            'baseColorFactor': [round(srgb_to_linear(r / 255.0), 6), round(srgb_to_linear(g / 255.0), 6),
                                round(srgb_to_linear(b / 255.0), 6), round(alpha, 4)],
            'metallicFactor': 0.0,
            'roughnessFactor': 0.9,
        },
        'doubleSided': True,
    }
    if alpha < 1.0:
        material['alphaMode'] = 'BLEND'
    return material


def glb_bytes(meshes, title='Model', extras=None, generator=GENERATOR):
    """The .glb file as bytes: a root node named title, a node per model, a node and
    mesh per object (translation = object centre, extras = its data), one material
    per distinct colour and opacity. No NORMAL attribute: viewers must then compute
    flat normals (spec), which is right for faceted building geometry."""
    gltf = {
        'asset': {'version': '2.0', 'generator': generator},
        'scene': 0,
        'scenes': [{'name': title, 'nodes': [0]}],
        'nodes': [{'name': title, 'children': []}],
        'meshes': [],
        'materials': [],
        'accessors': [],
        'bufferViews': [],
        'buffers': [],
    }
    if extras:
        gltf['asset']['extras'] = extras
    binary = bytearray()
    material_index = {}
    model_node = {}
    for mesh in meshes:
        key = material_key(mesh)
        if key not in material_index:
            material_index[key] = len(gltf['materials'])
            gltf['materials'].append(gltf_material(mesh['color'], mesh['alpha']))
        model = mesh['model'] or 'Model'
        if model not in model_node:
            model_node[model] = len(gltf['nodes'])
            gltf['nodes'][0]['children'].append(model_node[model])
            gltf['nodes'].append({'name': model, 'children': []})

        vertices = mesh['vertices']
        flat = []
        for p in vertices:
            flat.extend(p)
        low = [min(p[a] for p in vertices) for a in range(3)]
        high = [max(p[a] for p in vertices) for a in range(3)]
        offset = len(binary)
        chunk = _pack('f', flat)
        binary.extend(chunk)
        gltf['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(chunk),
                                    'target': _ARRAY_BUFFER})
        position = len(gltf['accessors'])
        gltf['accessors'].append({
            'bufferView': len(gltf['bufferViews']) - 1, 'componentType': _FLOAT,
            'count': len(vertices), 'type': 'VEC3',
            'min': [exact32(v) for v in low], 'max': [exact32(v) for v in high]})

        indices = []
        for face in mesh['faces']:
            indices.extend(face)
        wide = len(vertices) > 65535          # 65535 itself is reserved (primitive restart)
        offset = len(binary)
        chunk = _pack('I' if wide else 'H', indices)
        binary.extend(chunk)
        gltf['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(chunk),
                                    'target': _ELEMENT_ARRAY_BUFFER})
        while len(binary) % 4:
            binary.append(0)
        index_accessor = len(gltf['accessors'])
        gltf['accessors'].append({
            'bufferView': len(gltf['bufferViews']) - 1,
            'componentType': _UINT32 if wide else _UINT16,
            'count': len(indices), 'type': 'SCALAR'})

        mesh_index = len(gltf['meshes'])
        gltf['meshes'].append({'name': mesh['name'], 'primitives': [{
            'attributes': {'POSITION': position}, 'indices': index_accessor,
            'material': material_index[key], 'mode': 4}]})
        node = {'name': mesh['name'], 'mesh': mesh_index,
                'translation': [float(v) for v in mesh['translation']]}
        if mesh.get('extras'):
            node['extras'] = mesh['extras']
        gltf['nodes'][model_node[model]]['children'].append(len(gltf['nodes']))
        gltf['nodes'].append(node)
    gltf['buffers'].append({'byteLength': len(binary)})
    if not gltf['meshes']:
        for key in ('meshes', 'materials', 'accessors', 'bufferViews', 'buffers'):
            del gltf[key]
    json_chunk = _pad(json_text(gltf).encode('ascii'), b' ')
    bin_chunk = _pad(bytes(binary), b'\x00')
    total = 12 + 8 + len(json_chunk) + (8 + len(bin_chunk) if bin_chunk else 0)
    out = bytearray(struct.pack('<III', _GLB_MAGIC, 2, total))
    out.extend(struct.pack('<II', len(json_chunk), _CHUNK_JSON))
    out.extend(json_chunk)
    if bin_chunk:
        out.extend(struct.pack('<II', len(bin_chunk), _CHUNK_BIN))
        out.extend(bin_chunk)
    return bytes(out)


def parse_glb(data):
    """(gltf dict, binary chunk bytes) from a .glb. ValueError naming what is wrong:
    the reader the tests check every file with."""
    data = bytes(data)
    if len(data) < 20:
        raise ValueError('too short for a GLB file')
    magic, version, total = struct.unpack('<III', data[:12])
    if magic != _GLB_MAGIC:
        raise ValueError('not a GLB file')
    if version != 2:
        raise ValueError('GLB version %d' % version)
    if total != len(data):
        raise ValueError('header length %d, file %d bytes' % (total, len(data)))
    offset = 12
    gltf = None
    binary = b''
    first = True
    while offset < len(data):
        length, kind = struct.unpack('<II', data[offset:offset + 8])
        if length % 4:
            raise ValueError('chunk length %d is not a multiple of 4' % length)
        body = data[offset + 8:offset + 8 + length]
        if len(body) != length:
            raise ValueError('chunk runs past the end of the file')
        if first and kind != _CHUNK_JSON:
            raise ValueError('the first chunk is not JSON')
        if kind == _CHUNK_JSON:
            gltf = json.loads(body.decode('utf-8'))
        elif kind == _CHUNK_BIN:
            binary = body
        offset += 8 + length
        first = False
    if gltf is None:
        raise ValueError('no JSON chunk')
    return gltf, binary


def read_accessor(gltf, binary, index):
    """The values of an accessor as a flat list (float or int), for tests."""
    accessor = gltf['accessors'][index]
    view = gltf['bufferViews'][accessor['bufferView']]
    code = {_FLOAT: 'f', _UINT16: 'H', _UINT32: 'I', 5121: 'B'}[accessor['componentType']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[accessor['type']]
    count = accessor['count'] * width
    start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    size = struct.calcsize('<' + code)
    return list(struct.unpack('<%d%s' % (count, code), binary[start:start + count * size]))


# =====================================================================================
# OBJ + MTL
# =====================================================================================


_OBJ_NAME = re.compile(r'\s+')


def obj_name(text, taken):
    """A group name OBJ readers keep whole: whitespace becomes '_', unique (case-
    insensitive) among taken (a set it adds to)."""
    base = _OBJ_NAME.sub('_', str(text or '').strip()) or 'Object'
    name = base
    n = 2
    while name.lower() in taken:
        name = '%s_%d' % (base, n)
        n += 1
    taken.add(name.lower())
    return name


def material_name(color, alpha):
    if alpha >= 1.0:
        return 'mat_%s' % color
    return 'mat_%s_%d' % (color, int(round(alpha * 100)))


def obj_text(meshes, mtl_file, header_lines=None):
    """The .obj text: vertices then faces per object (global, 1-based indices), 'o'
    and 'g' per object, 'usemtl' per colour. Coordinates with 6 decimals."""
    lines = ['# %s' % GENERATOR]
    for line in header_lines or []:
        lines.append('# %s' % line)
    lines.append('mtllib %s' % mtl_file)
    taken = set()
    base = 1
    for mesh in meshes:
        name = obj_name(mesh['name'], taken)
        lines.append('o %s' % name)
        lines.append('g %s' % name)
        lines.append('usemtl %s' % material_name(mesh['color'], mesh['alpha']))
        tx, ty, tz = mesh['translation']
        for x, y, z in mesh['vertices']:
            lines.append('v %s %s %s' % (_fixed(x + tx), _fixed(y + ty), _fixed(z + tz)))
        for i, j, k in mesh['faces']:
            lines.append('f %d %d %d' % (i + base, j + base, k + base))
        base += len(mesh['vertices'])
    return '\n'.join(lines) + '\n'


def mtl_text(meshes):
    """The .mtl text: one material per distinct colour and opacity (Kd is the sRGB
    colour, d the opacity), in first-use order."""
    lines = ['# %s' % GENERATOR]
    seen = set()
    for mesh in meshes:
        name = material_name(mesh['color'], mesh['alpha'])
        if name in seen:
            continue
        seen.add(name)
        r, g, b = rgb(mesh['color'])
        lines.append('')
        lines.append('newmtl %s' % name)
        lines.append('Ka 0 0 0')
        lines.append('Kd %s %s %s' % (_fixed(r / 255.0, 4), _fixed(g / 255.0, 4), _fixed(b / 255.0, 4)))
        lines.append('Ks 0 0 0')
        lines.append('d %s' % _fixed(mesh['alpha'], 4))
        lines.append('illum 1')
    return '\n'.join(lines) + '\n'


def _fixed(value, decimals=6):
    text = '%.*f' % (decimals, float(value))
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text in ('-0', ''):
        text = '0'
    return text


def parse_obj(text):
    """{'vertices': [...], 'groups': [(name, material, [faces 0-based])], 'mtllib'}:
    the reader the tests use."""
    vertices = []
    groups = []
    mtllib = None
    current = None
    material = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if parts[0] == 'v':
            vertices.append(tuple(float(v) for v in parts[1:4]))
        elif parts[0] == 'g':
            current = [parts[1], material, []]
            groups.append(current)
        elif parts[0] == 'usemtl':
            material = parts[1]
            if current is not None:
                current[1] = material
        elif parts[0] == 'f':
            current[2].append(tuple(int(v.split('/')[0]) - 1 for v in parts[1:4]))
        elif parts[0] == 'mtllib':
            mtllib = parts[1]
    return {'vertices': vertices, 'groups': [tuple(g) for g in groups], 'mtllib': mtllib}


# =====================================================================================
# Binary STL
# =====================================================================================


def facet_normal(a, b, c):
    """Unit normal from the winding (right hand), (0, 0, 0) for a degenerate face."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 0.0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def stl_header(text):
    """80 bytes of ASCII that never start with 'solid' (that would make readers try
    the text format)."""
    data = str(text or '').encode('ascii', 'replace')
    if data[:5].lower() == b'solid':
        data = b'Playground ' + data
    return (data + b' ' * 80)[:80]


def stl_bytes(meshes, header='Playground binary STL'):
    """Binary STL: 80-byte header, uint32 count, then per triangle the facet normal,
    three corners (float32) and a zero attribute word."""
    total = sum(len(m['faces']) for m in meshes)
    out = bytearray(stl_header(header))
    out.extend(struct.pack('<I', total))
    batch = []
    batch_count = 0
    for mesh in meshes:
        tx, ty, tz = mesh['translation']
        points = [(x + tx, y + ty, z + tz) for x, y, z in mesh['vertices']]
        for i, j, k in mesh['faces']:
            a, b, c = points[i], points[j], points[k]
            n = facet_normal(a, b, c)
            batch.extend(n)
            batch.extend(a)
            batch.extend(b)
            batch.extend(c)
            batch.append(0)
            batch_count += 1
            if batch_count == 2000:
                out.extend(struct.pack('<' + '12fH' * batch_count, *batch))
                batch = []
                batch_count = 0
    if batch_count:
        out.extend(struct.pack('<' + '12fH' * batch_count, *batch))
    return bytes(out)


def parse_stl(data):
    """(header, [(normal, a, b, c)]) from binary STL bytes; ValueError when the size
    does not match the triangle count."""
    data = bytes(data)
    if len(data) < 84:
        raise ValueError('too short for a binary STL')
    count = struct.unpack('<I', data[80:84])[0]
    if len(data) != 84 + 50 * count:
        raise ValueError('%d triangles need %d bytes, file has %d' % (count, 84 + 50 * count, len(data)))
    out = []
    for index in range(count):
        values = struct.unpack('<12fH', data[84 + 50 * index:84 + 50 * (index + 1)])
        out.append((values[0:3], values[3:6], values[6:9], values[9:12]))
    return data[:80], out


# =====================================================================================
# DXF (R12 structure, 3DFACE, true colour)
# =====================================================================================


_LAYER_BAD = re.compile(r'[^A-Za-z0-9_$-]+')


def layer_name(text, taken):
    """An R12-safe layer name: letters, digits, '_', '$' and '-' only, at most 31
    characters, unique ignoring case (taken is a dict lower -> name it adds to)."""
    base = _LAYER_BAD.sub('_', str(text or '').strip()).strip('_')[:31] or 'Unnamed'
    if base == '0':
        base = 'Layer_0'
    name = base
    n = 2
    while name.lower() in taken:
        suffix = '_%d' % n
        name = base[:31 - len(suffix)] + suffix
        n += 1
    taken[name.lower()] = name
    return name


def dxf_layer_key(mesh, by):
    """What a mesh's layer is named after: its model file (without extension) or its
    category."""
    if by == 'category':
        return mesh.get('category') or 'Uncategorised'
    model = mesh.get('model') or 'Model'
    return os.path.splitext(model)[0] or model


def _g(out, code, value):
    out.append('%3d' % code if code < 1000 else str(code))
    out.append(value)


def _dxf_num(value):
    return _fixed(value, 9)


def dxf_text(meshes, layer_by='model', comment=None):
    """A DXF that AutoCAD and every DXF reader open: R12 sections (HEADER, TABLES with
    LTYPE and LAYER, ENTITIES), one 3DFACE per triangle (fourth corner = third) on a
    layer per model or category, colour as the nearest AutoCAD Color Index (62) for
    old readers plus the exact true colour (420) for current ones."""
    palette = aci_palette()
    taken = {}
    layer_of_key = {}
    layer_colour = {}
    layer_order = []
    for mesh in meshes:
        key = dxf_layer_key(mesh, layer_by)
        if key not in layer_of_key:
            layer_of_key[key] = layer_name(key, taken)
            layer_order.append(layer_of_key[key])
            layer_colour[layer_of_key[key]] = mesh['color']
    points = []
    for mesh in meshes:
        tx, ty, tz = mesh['translation']
        for x, y, z in mesh['vertices']:
            points.append((x + tx, y + ty, z + tz))
    low = [min(p[a] for p in points) for a in range(3)] if points else [0.0, 0.0, 0.0]
    high = [max(p[a] for p in points) for a in range(3)] if points else [0.0, 0.0, 0.0]

    out = []
    if comment:
        for line in str(comment).splitlines():
            _g(out, 999, line)
    _g(out, 0, 'SECTION')
    _g(out, 2, 'HEADER')
    _g(out, 9, '$ACADVER')
    _g(out, 1, 'AC1009')
    _g(out, 9, '$INSBASE')
    for code in (10, 20, 30):
        _g(out, code, '0')
    _g(out, 9, '$EXTMIN')
    for code, value in zip((10, 20, 30), low):
        _g(out, code, _dxf_num(value))
    _g(out, 9, '$EXTMAX')
    for code, value in zip((10, 20, 30), high):
        _g(out, code, _dxf_num(value))
    _g(out, 0, 'ENDSEC')

    _g(out, 0, 'SECTION')
    _g(out, 2, 'TABLES')
    _g(out, 0, 'TABLE')
    _g(out, 2, 'LTYPE')
    _g(out, 70, '1')
    _g(out, 0, 'LTYPE')
    _g(out, 2, 'CONTINUOUS')
    _g(out, 70, '0')
    _g(out, 3, 'Solid line')
    _g(out, 72, '65')
    _g(out, 73, '0')
    _g(out, 40, '0')
    _g(out, 0, 'ENDTAB')
    _g(out, 0, 'TABLE')
    _g(out, 2, 'LAYER')
    _g(out, 70, '%d' % (len(layer_order) + 1))
    for name, colour in [('0', None)] + [(n, layer_colour[n]) for n in layer_order]:
        _g(out, 0, 'LAYER')
        _g(out, 2, name)
        _g(out, 70, '0')
        _g(out, 62, '%d' % (7 if colour is None else nearest_aci(colour, palette)))
        _g(out, 6, 'CONTINUOUS')
    _g(out, 0, 'ENDTAB')
    _g(out, 0, 'ENDSEC')

    _g(out, 0, 'SECTION')
    _g(out, 2, 'ENTITIES')
    aci_cache = {}
    for mesh in meshes:
        layer = layer_of_key[dxf_layer_key(mesh, layer_by)]
        colour = mesh['color']
        if colour not in aci_cache:
            aci_cache[colour] = ('%d' % nearest_aci(colour, palette), '%d' % true_color(colour))
        aci, true = aci_cache[colour]
        tx, ty, tz = mesh['translation']
        verts = [(x + tx, y + ty, z + tz) for x, y, z in mesh['vertices']]
        for i, j, k in mesh['faces']:
            corners = (verts[i], verts[j], verts[k], verts[k])
            _g(out, 0, '3DFACE')
            _g(out, 8, layer)
            _g(out, 62, aci)
            _g(out, 420, true)
            for n, (x, y, z) in enumerate(corners):
                _g(out, 10 + n, _dxf_num(x))
                _g(out, 20 + n, _dxf_num(y))
                _g(out, 30 + n, _dxf_num(z))
    _g(out, 0, 'ENDSEC')
    _g(out, 0, 'EOF')
    return '\r\n'.join(out) + '\r\n'


def parse_dxf(text):
    """{'header': {var: [values]}, 'layers': {name: aci}, 'faces': [{'layer', 'aci',
    'true', 'corners'}]}: a strict group-code pair reader, for tests."""
    lines = text.replace('\r\n', '\n').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    if len(lines) % 2:
        raise ValueError('odd number of lines: group codes and values must pair up')
    pairs = [(int(lines[i].strip()), lines[i + 1]) for i in range(0, len(lines), 2)]
    header = {}
    layers = {}
    faces = []
    section = None
    index = 0
    while index < len(pairs):
        code, value = pairs[index]
        if code == 0 and value == 'SECTION':
            section = pairs[index + 1][1]
            index += 2
            continue
        if code == 0 and value == 'ENDSEC':
            section = None
        elif section == 'HEADER' and code == 9:
            values = []
            index += 1
            while index < len(pairs) and pairs[index][0] not in (0, 9):
                values.append(pairs[index][1])
                index += 1
            header[value] = values
            continue
        elif section == 'TABLES' and code == 0 and value == 'LAYER':
            record = {}
            index += 1
            while pairs[index][0] != 0:
                record[pairs[index][0]] = pairs[index][1]
                index += 1
            layers[record[2]] = int(record.get(62, 7))
            continue
        elif section == 'ENTITIES' and code == 0 and value == '3DFACE':
            record = {}
            index += 1
            while pairs[index][0] != 0:
                record[pairs[index][0]] = pairs[index][1]
                index += 1
            corners = [(float(record[10 + n]), float(record[20 + n]), float(record[30 + n]))
                       for n in range(4)]
            faces.append({'layer': record[8], 'aci': int(record[62]), 'true': int(record[420]),
                          'corners': corners})
            continue
        index += 1
    if not pairs or pairs[-1] != (0, 'EOF'):
        raise ValueError('no EOF')
    return {'header': header, 'layers': layers, 'faces': faces}


# =====================================================================================
# Files, names and the offset note
# =====================================================================================


def offset_note(origin, doc_units, fmt, units_word, source, when=None, axes_y_up=False):
    """The sidecar text written beside a shifted export: what was subtracted, in the
    model's own units, and how to put the geometry back."""
    when = when or datetime.datetime.now()
    sym = {'Meters': 'm', 'Millimeters': 'mm', 'Centimeters': 'cm', 'Feet': 'ft',
           'Inches': 'in'}.get(str(doc_units), str(doc_units).lower())
    per = doc_meters(doc_units)
    x, y, z = origin
    lines = [
        'Playground Geometry Exporter: local origin',
        'Source: %s' % (source or 'Untitled'),
        'Exported: %s' % when.strftime('%Y-%m-%d %H:%M'),
        'Format: %s, %s%s' % (FORMAT_NAMES.get(fmt, fmt), units_word, ', Y up' if axes_y_up else ', Z up'),
        '',
        'Every coordinate was moved by subtracting this point (Navisworks model coordinates):',
        '  X = %s %s  (%s m)' % (_grouped(x), sym, _grouped(x * per, 3)),
        '  Y = %s %s  (%s m)' % (_grouped(y), sym, _grouped(y * per, 3)),
        '  Z = %s %s  (%s m)' % (_grouped(z), sym, _grouped(z * per, 3)),
        '',
    ]
    if axes_y_up:
        lines.append('The file is Y up: its X is model X, its Y is model Z and its Z is minus model Y.')
        lines.append('To put the geometry back, move it by (X, Z, -Y) in the file\'s axes, in %s.' % units_word)
    else:
        lines.append('To put the geometry back, move it by (X, Y, Z) above, in %s.' % units_word)
    return '\n'.join(lines) + '\n'


def _grouped(value, decimals=None):
    if decimals is None:
        text = _fixed(value, 6)
    else:
        text = _fixed(value, decimals)
    negative = text.startswith('-')
    if negative:
        text = text[1:]
    whole, _dot, frac = text.partition('.')
    whole = '{:,}'.format(int(whole))
    return ('-' if negative else '') + whole + ('.' + frac if frac else '')


def mtl_path(path):
    """The .mtl beside an .obj, with spaces in its name turned into '_' ('mtllib'
    takes whitespace-separated names, so most readers would cut a spaced name)."""
    folder, name = os.path.split(path)
    stem = os.path.splitext(name)[0].replace(' ', '_')
    return os.path.join(folder, stem + '.mtl')


def sidecar_path(path):
    stem, _ext = os.path.splitext(path)
    return stem + ' - offset.txt'


def write_files(path, fmt, meshes, title='Model', extras=None, layer_by='model', header_lines=None):
    """Writes the export (and the .mtl beside an .obj) atomically. Returns the list
    of files written."""
    from namo import paths
    written = []
    if fmt == 'glb':
        paths.atomic_write_bytes(path, glb_bytes(meshes, title=title, extras=extras))
        written.append(path)
    elif fmt == 'obj':
        mtl = mtl_path(path)
        paths.atomic_write_text(path, obj_text(meshes, os.path.basename(mtl), header_lines))
        paths.atomic_write_text(mtl, mtl_text(meshes))
        written.extend([path, mtl])
    elif fmt == 'stl':
        paths.atomic_write_bytes(path, stl_bytes(meshes, header='Playground %s' % (title or '')))
        written.append(path)
    elif fmt == 'dxf':
        paths.atomic_write_bytes(path, dxf_text(meshes, layer_by, comment='\n'.join(header_lines or []))
                                 .encode('ascii', 'replace'))
        written.append(path)
    else:
        raise ValueError('Unknown format %r' % fmt)
    return written


DEFAULT_OPTIONS = {'format': 'glb', 'units': 'doc', 'shift': True, 'obj_y_up': True, 'layers': 'model',
                   'identity': True, 'properties': [], 'per_object': DEFAULT_PER_OBJECT,
                   'total': DEFAULT_TOTAL}
PAIR_SEP = chr(9)            # tab: never part of a Navisworks property name


def property_option(category, prop):
    """(label, value) for a property in the extras chooser."""
    return ('%s > %s' % (category, prop), '%s%s%s' % (category, PAIR_SEP, prop))


def property_pairs(values):
    """[(category, property)] from the chooser's values."""
    return [tuple(v.split(PAIR_SEP, 1)) for v in values or [] if PAIR_SEP in str(v)]


def form_fields(values, doc_units, prop_options):
    """The Geometry Exporter form (namo.ui.form fields)."""
    unit_options = [('Document units (%s)' % str(doc_units).lower(), 'doc')] +         [(label, key) for key, label in UNIT_CHOICES if key != 'doc']
    fields = [
        {'kind': 'radio', 'key': 'format', 'label': 'Format', 'options': [(label, key) for key, label in FORMATS],
         'default': values['format'], 'fallback': None},
        {'kind': 'choice', 'key': 'units', 'label': 'Units', 'options': unit_options, 'default': values['units'], 'fallback': None,
         'enabled_if': ('format', ['obj', 'stl', 'dxf']), 'hint': 'glTF is always in metres.'},
        {'kind': 'check', 'key': 'shift', 'label': 'Move to a local origin (the offset is saved beside the file)',
         'default': values['shift']},
        {'kind': 'check', 'key': 'obj_y_up', 'label': 'Y up, as Blender and 3ds Max import OBJ',
         'default': values['obj_y_up'], 'enabled_if': ('format', 'obj')},
        {'kind': 'radio', 'key': 'layers', 'label': 'DXF layers', 'inline': True,
         'options': [('By model', 'model'), ('By category', 'category')], 'default': values['layers'], 'fallback': None,
         'enabled_if': ('format', 'dxf')},
        {'kind': 'check', 'key': 'identity', 'label': 'Category, model and Revit and IFC ids in glTF extras',
         'default': values['identity'], 'enabled_if': ('format', 'glb')},
    ]
    if prop_options:
        known = set(v for _l, v in prop_options)
        fields.append({'kind': 'multi', 'key': 'properties', 'label': 'Properties in glTF extras',
                       'options': prop_options, 'default': [v for v in values.get('properties') or [] if v in known],
                       'enabled_if': ('format', 'glb')})
    fields += [
        {'kind': 'separator'},
        {'kind': 'int', 'key': 'per_object', 'label': 'Triangles per object, at most', 'min': 100,
         'max': 20000000, 'default': values['per_object'], 'required': True},
        {'kind': 'int', 'key': 'total', 'label': 'Triangles in all, at most', 'min': 1000,
         'max': 100000000, 'default': values['total'], 'required': True,
         'hint': 'Objects past either limit are skipped and listed.'},
    ]
    return fields


_OVER = re.compile(r'(\d+) primitives is over the (\d+) budget')


def skip_reason(note, capped_by_total=False):
    """Why an object gave no triangles, in words, from namo.mesh.item_triangles' note
    (pynavis.geometry's notes: 'N primitives is over the M budget', 'no geometry
    nodes', ...)."""
    text = str(note or '').strip()
    match = _OVER.search(text)
    if match:
        return 'Too big: %s triangles, over the %s left %s' % (
            '{:,}'.format(int(match.group(1))), '{:,}'.format(int(match.group(2))),
            'in the total' if capped_by_total else 'per object')
    if not text or text == 'no triangles':
        return 'No triangles'
    if text == 'no geometry nodes':
        return 'No geometry'
    if text.startswith('triangle walk failed:'):
        return 'Could not read its triangles:' + text[len('triangle walk failed:'):]
    return text[:1].upper() + text[1:]


def plan_budget(remaining_total, per_object):
    """How many triangles the next object may have: the per-object budget, capped by
    what is left of the total; 0 means stop reading."""
    return max(0, min(int(per_object), int(remaining_total)))


def summary(meshes, skipped, dropped, fmt, sampled=False):
    """(level, message, detail) for the closing toast."""
    objects, _vertices, triangles = counts(meshes)
    if not objects:
        return ('warning', 'Nothing was exported',
                'None of the %s selected objects gave triangles.' % '{:,}'.format(len(skipped) + len(dropped)))
    message = 'Exported %s %s, %s triangles' % ('{:,}'.format(objects), 'object' if objects == 1 else 'objects',
                                                 '{:,}'.format(triangles))
    left = len(skipped) + len(dropped)
    if left or sampled:
        parts = []
        if left:
            parts.append('%s skipped (listed in the output window)' % '{:,}'.format(left))
        if sampled:
            parts.append('the selection was sampled')
        text = '; '.join(parts)
        return ('warning', message, text[:1].upper() + text[1:] + '.')
    return ('success', message, FORMAT_NAMES.get(fmt, fmt))


# =====================================================================================
# API half (IronPython inside Navisworks)
# =====================================================================================


IDENTITY_KEYS = ('element_id', 'unique_id', 'ifc_guid')


def object_name(item):
    try:
        name = item.DisplayName
        if name:
            return str(name)
        return str(item.ClassDisplayName or 'Object')
    except Exception:
        return 'Object'


def property_values(item, pairs):
    """{category: {property: value}} for the chosen (category, property) pairs that the
    item carries (JSON-safe values)."""
    from namo import variants
    out = {}
    for category, prop in pairs:
        try:
            value = variants.get(item, category, prop)
        except Exception:
            value = None
        if value is None:
            continue
        out.setdefault(str(category), {})[str(prop)] = json_value(value)
    return out


def read_objects(selected, per_object=DEFAULT_PER_OBJECT, total=DEFAULT_TOTAL, progress=None,
                 identity=True, property_pairs=None, extra=None, object_budget=None, doc_units=None):
    """Reads the selection's objects: {'records', 'skipped' [(name, reason, item)],
    'sampled', 'objects'}. Each record: name, model, category, color, transparency,
    tris (world, document units), noise, extras, item. extra(item, record) may add to
    a record (the IFC exporter's hook; it sees 'tris'). With doc_units each object is
    welded as soon as it is read: 'mesh' (vertices, faces) replaces 'tris', which keeps
    memory to a fraction on big selections. progress(fraction, label) may cancel by
    raising (namo.progress) or returning False."""
    from namo import items, mesh, paint
    from namo.items import Cancelled

    def report(fraction, label):
        if progress is not None and progress(fraction, label) == False:  # noqa: E712
            raise Cancelled()

    def tick(done, _total):
        report(0.0, 'Finding objects: %s items' % '{:,}'.format(done))
        return True

    objects = items.objects(selected, tick=tick, budget=object_budget)
    records = []
    skipped = []
    used = 0
    count = len(objects)
    for index, obj in enumerate(objects):
        name = object_name(obj)
        if index % 10 == 0 or index == count - 1:
            report(float(index) / max(1, count), 'Reading %s of %s objects' % (
                '{:,}'.format(index + 1), '{:,}'.format(count)))
        allowance = plan_budget(total - used, per_object)
        if allowance <= 0:
            skipped.append((name, 'Over the total triangle budget of %s' % '{:,}'.format(total), obj))
            continue
        data = mesh.item_triangles(obj, budget=allowance)
        tris = data.get('tris') or []
        if not tris:
            skipped.append((name, skip_reason(data.get('note'), allowance < per_object), obj))
            continue
        used += len(tris)
        hex_value, transparency = paint.read_color(obj)
        record = {
            'name': name,
            'model': items.model_name(obj),
            'category': items.category(obj),
            'color': hex_value,
            'transparency': transparency or 0.0,
            'tris': tris,
            'noise': data.get('noise') or 0.0,
            'item': obj,
        }
        extras = {'category': record['category'], 'model': record['model']}
        if identity:
            try:
                ids = items.revit_ids(obj) or {}
            except Exception:
                ids = {}
            for key in IDENTITY_KEYS:
                if ids.get(key):
                    extras[key] = ids[key]
            record['ids'] = ids
        if property_pairs:
            values = property_values(obj, property_pairs)
            if values:
                extras['properties'] = values
        record['extras'] = extras
        if extra is not None:
            extra(obj, record)
        if doc_units:
            record['mesh'] = _weld(tris, weld_tolerance(record['noise'], doc_units))
            record['triangles'] = len(tris)
            del record['tris']
        records.append(record)
    report(1.0, 'Read %s objects' % '{:,}'.format(count))
    return {'records': records, 'skipped': skipped, 'sampled': bool(getattr(objects, 'sampled', False)),
            'objects': count}

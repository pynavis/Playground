# -*- coding: utf-8 -*-
"""Saved viewpoints out of Navisworks, as plain records, as Navisworks viewpoint
exchange XML, and as a Playground package (.nvp.json) that Viewpoint Sync reads back.

A view RECORD (JSON-safe, lengths in the units named next to it):
    {'folder': 'A/B', 'name', 'guid',
     'camera': namo.camera dict + 'near', 'far', 'linear', 'angular', 'world_up',
     'render', 'lighting', 'tool',
     'clip': vp_common.clip_state_of() dict or None,
     'comments': [{'body', 'author', 'status', 'date'}]}

EXCHANGE_LAYOUT below is the ONE place the XML element/attribute layout is defined;
the writer and the reader both follow it. Our own reader round-trips it exactly
(tests). Whether Navisworks' Import Viewpoints accepts every part is an in-app check
(dev/notes/views.md): the camera part is what Navisworks itself writes, the section
part is written only when asked for and is the least certain.
"""
import math
import os
import xml.dom.minidom

FORMAT = 'playground-viewpoints'
VERSION = 1
SCHEMA = 'http://download.autodesk.com/us/navisworks/schemas/nw-exchange-12.0.xsd'

EXCHANGE_LAYOUT = """
Navisworks viewpoint exchange XML, as Navisworks' own Saved Viewpoints > Export
Viewpoints writes it (nw-exchange-12.0.xsd; reconstructed from exported files and
Autodesk's published schema name, not from the XSD text itself):

<?xml version="1.0" encoding="UTF-8" ?>
<exchange xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:noNamespaceSchemaLocation="...nw-exchange-12.0.xsd"
          units="ft" filename="Hospital.nwf" filepath="C:\\Jobs">
  <viewpoints>
    <viewfolder name="Folder" guid="...">          (nested freely)
      <view name="Name" guid="...">
        <viewpoint tool="none" render="shaded" lighting="headlight"
                   focal="20.5" linear="3.3" angular="0.785398">
          <camera projection="persp|ortho" near="0.1" far="500" aspect="1.6"
                  height="0.785398">                (persp: vertical FOV radians;
                                                     ortho: visible height, units)
            <position><pos3f x="" y="" z=""/></position>
            <rotation><quaternion a="" b="" c="" d=""/></rotation>
          </camera>
          <up><vec3f x="0" y="0" z="1"/></up>        (the world up vector)
        </viewpoint>
        <clipplaneset enabled="1" mode="planes|box" linked="0" current="0">   (optional)
          <range><box3f><min><pos3f/></min><max><pos3f/></max></box3f></range>
          <clipplanes>
            <clipplane state="enabled|disabled|default" alignment="custom|top|...">
              <plane distance="d"><vec3f x="" y="" z=""/></plane>     (normal . p = d)
            </clipplane>  x6
          </clipplanes>
          <box><box3f><min><pos3f/></min><max><pos3f/></max></box3f></box>
          <box-rotation><rotation><quaternion a b c d/></rotation></box-rotation>
        </clipplaneset>
        <comments>
          <comment id="1" status="new|active|approved|resolved">
            <user>name</user>
            <body>text</body>
            <createddate><date year="" month="" day="" hour="" minute="" second=""/></createddate>
          </comment>
        </comments>
      </view>
    </viewfolder>
  </viewpoints>
</exchange>

Quaternion a, b, c, d = Rotation3D A, B, C, D (vector part first, scalar last; see
namo.camera). Numbers are written with '.' and up to 10 significant decimals.
"""

UNIT_CODES = [
    ('Meters', 'm'), ('Centimeters', 'cm'), ('Millimeters', 'mm'), ('Feet', 'ft'),
    ('Inches', 'in'), ('Yards', 'yd'), ('Kilometers', 'km'), ('Miles', 'mi'),
    ('Micrometers', 'um'), ('Mils', 'mil'), ('Microinches', 'uin'),
]
RENDER_CODES = [('FullRender', 'full'), ('Shaded', 'shaded'), ('Wireframe', 'wireframe'),
                ('HiddenLine', 'hidden'), ('Preview', 'shaded')]
LIGHTING_CODES = [('None', 'none'), ('Headlight', 'headlight'), ('SceneLights', 'scene'),
                  ('FullLights', 'full')]
STATUS_CODES = [('New', 'new'), ('Active', 'active'), ('Approved', 'approved'), ('Resolved', 'resolved')]


# ---- pure: codes and numbers -------------------------------------------------------


def _code(table, name, default):
    for full, code in table:
        if full.lower() == str(name).lower():
            return code
    return default


def _name(table, code, default):
    text = str(code or '').strip().lower()
    for full, short in table:
        if short == text or full.lower() == text:
            return full
    return default


def unit_code(doc_units):
    """'Feet' -> 'ft' for the exchange file's units attribute."""
    return _code(UNIT_CODES, doc_units, 'm')


def unit_name(code):
    """'ft' (or 'Feet') -> 'Feet'; unknown -> 'Meters'."""
    return _name(UNIT_CODES, code, 'Meters')


def num(value, places=10):
    """A number as the file writes it: fixed point, trailing zeros trimmed,
    never '-0', never exponent notation."""
    v = float(value)
    if v != v or v in (float('inf'), float('-inf')):
        v = 0.0
    text = ('%.' + str(int(places)) + 'f') % v
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text in ('-0', ''):
        text = '0'
    return text


def esc(text):
    """Attribute/element text escaped for XML; control characters dropped."""
    out = []
    for ch in str(text if text is not None else ''):
        code = ord(ch)
        if code < 32 and ch not in '\t\n\r':
            continue
        out.append({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'}.get(ch, ch))
    return ''.join(out)


# ---- pure: scaling between units -----------------------------------------------------


def scale_camera(cam, k):
    """A copy of a camera dict with every length multiplied by k (position,
    focal distance, near/far, linear speed, and the HEIGHT of an ortho camera)."""
    out = dict(cam)
    if k == 1.0:
        return out
    out['position'] = [float(v) * k for v in cam['position']]
    for key in ('focal_distance', 'near', 'far', 'linear'):
        if out.get(key) is not None:
            out[key] = float(out[key]) * k
    if str(cam.get('projection', 'persp')).startswith('ortho') and out.get('height_field') is not None:
        out['height_field'] = float(out['height_field']) * k
    out['json'] = None          # Navisworks' own camera text cannot be rescaled safely
    return out


def scale_clip(clip, k):
    """A copy of a clip_state dict with origins, distances, range and box scaled by k."""
    if not clip or k == 1.0:
        return clip
    out = dict(clip)
    planes = []
    for plane in clip.get('planes') or []:
        p = dict(plane)
        if p.get('origin') is not None:
            p['origin'] = [float(v) * k for v in p['origin']]
        if p.get('distance') is not None:
            p['distance'] = float(p['distance']) * k
        planes.append(p)
    out['planes'] = planes
    if clip.get('range'):
        out['range'] = [[float(v) * k for v in corner] for corner in clip['range']]
    if clip.get('box'):
        box = dict(clip['box'])
        for key in ('min', 'max'):
            if box.get(key) is not None:
                box[key] = [float(v) * k for v in box[key]]
        out['box'] = box
    return out


def scale_record(record, k):
    out = dict(record)
    if record.get('camera'):
        out['camera'] = scale_camera(record['camera'], k)
    if record.get('clip'):
        out['clip'] = scale_clip(record['clip'], k)
    return out


# ---- pure: exchange XML writer ----------------------------------------------------------


def _tree(records):
    """Nested [('folder', name, guid, children) | ('view', record)] in record order."""
    root = []
    folders = {}
    for record in records:
        parent = root
        path = []
        for part in [p for p in str(record.get('folder') or '').split('/') if p]:
            path.append(part)
            key = '/'.join(path)
            if key not in folders:
                node = ('folder', part, (record.get('folder_guids') or {}).get(key), [])
                parent.append(node)
                folders[key] = node
            parent = folders[key][3]
        parent.append(('view', record))
    return root


def _pos(tag, xyz, indent):
    x, y, z = [num(v) for v in list(xyz)[:3]]
    return '%s<%s x="%s" y="%s" z="%s"/>' % (indent, tag, x, y, z)


def _date_attrs(text):
    from namo import dates
    stamp = dates.parse(text) if text else None
    if stamp is None:
        return None
    return 'year="%d" month="%d" day="%d" hour="%d" minute="%d" second="%d"' % (
        stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)


def _camera_xml(cam, ind):
    out = []
    near = cam.get('near')
    far = cam.get('far')
    attrs = ['projection="%s"' % ('ortho' if str(cam.get('projection')).startswith('ortho') else 'persp')]
    attrs.append('near="%s"' % num(near if near else 0.1))
    attrs.append('far="%s"' % num(far if far else 1000.0))
    attrs.append('aspect="%s"' % num(cam.get('aspect') or 1.6))
    height = cam.get('height_field')
    if height is None:
        height = math.radians(60.0)
    attrs.append('height="%s"' % num(height))
    out.append('%s<camera %s>' % (ind, ' '.join(attrs)))
    out.append('%s  <position>' % ind)
    out.append(_pos('pos3f', cam['position'], ind + '    '))
    out.append('%s  </position>' % ind)
    q = cam.get('rotation') or cam.get('rotation_computed') or (0.0, 0.0, 0.0, 1.0)
    out.append('%s  <rotation>' % ind)
    out.append('%s    <quaternion a="%s" b="%s" c="%s" d="%s"/>' % (ind, num(q[0]), num(q[1]), num(q[2]), num(q[3])))
    out.append('%s  </rotation>' % ind)
    out.append('%s</camera>' % ind)
    return out


def _clip_xml(clip, ind):
    out = []
    mode = 'box' if clip.get('mode') == 'Box' else 'planes'
    out.append('%s<clipplaneset enabled="%d" mode="%s" linked="%d" current="0">' % (
        ind, 1 if clip.get('enabled') else 0, mode, 1 if clip.get('linked') else 0))
    if clip.get('range'):
        low, high = clip['range']
        out.append('%s  <range><box3f><min>%s</min><max>%s</max></box3f></range>' % (
            ind, _pos('pos3f', low, '').strip(), _pos('pos3f', high, '').strip()))
    out.append('%s  <clipplanes>' % ind)
    for plane in clip.get('planes') or []:
        normal = plane.get('normal') or [0.0, 0.0, 1.0]
        distance = plane.get('distance')
        if distance is None:
            origin = plane.get('origin') or [0.0, 0.0, 0.0]
            distance = sum(float(a) * float(b) for a, b in zip(origin, normal))
        state = str(plane.get('state') or 'Default').lower()
        if not plane.get('enabled') and state == 'enabled':
            state = 'disabled'
        alignment = str(plane.get('alignment') or 'Custom').lower()
        out.append('%s    <clipplane state="%s" alignment="%s">' % (ind, esc(state), esc(alignment)))
        out.append('%s      <plane distance="%s">%s</plane>' % (ind, num(distance), _pos('vec3f', normal, '').strip()))
        out.append('%s    </clipplane>' % ind)
    out.append('%s  </clipplanes>' % ind)
    box = clip.get('box')
    if box and box.get('min') is not None and box.get('max') is not None:
        out.append('%s  <box><box3f><min>%s</min><max>%s</max></box3f></box>' % (
            ind, _pos('pos3f', box['min'], '').strip(), _pos('pos3f', box['max'], '').strip()))
        rotation = box.get('rotation')
        if rotation:
            out.append('%s  <box-rotation><rotation><quaternion a="%s" b="%s" c="%s" d="%s"/></rotation></box-rotation>'
                       % (ind, num(rotation[0]), num(rotation[1]), num(rotation[2]), num(rotation[3])))
    out.append('%s</clipplaneset>' % ind)
    return out


def _comments_xml(comments, ind):
    out = ['%s<comments>' % ind]
    for index, comment in enumerate(comments):
        status = _code(STATUS_CODES, comment.get('status') or 'New', 'new')
        out.append('%s  <comment id="%d" status="%s">' % (ind, index + 1, status))
        out.append('%s    <user>%s</user>' % (ind, esc(comment.get('author') or '')))
        out.append('%s    <body>%s</body>' % (ind, esc(comment.get('body') or '')))
        attrs = _date_attrs(comment.get('date'))
        if attrs:
            out.append('%s    <createddate><date %s/></createddate>' % (ind, attrs))
        out.append('%s  </comment>' % ind)
    out.append('%s</comments>' % ind)
    return out


def _view_xml(record, ind, include_clip, include_comments):
    cam = record['camera']
    out = ['%s<view name="%s"%s>' % (ind, esc(record['name']),
                                      (' guid="%s"' % esc(record['guid'])) if record.get('guid') else '')]
    attrs = ['tool="%s"' % esc(cam.get('tool') or 'none'),
             'render="%s"' % esc(_code(RENDER_CODES, cam.get('render') or 'Shaded', 'shaded')),
             'lighting="%s"' % esc(_code(LIGHTING_CODES, cam.get('lighting') or 'Headlight', 'headlight'))]
    focal = cam.get('focal_distance')
    if focal:
        attrs.append('focal="%s"' % num(focal))
    if cam.get('linear'):
        attrs.append('linear="%s"' % num(cam['linear']))
    if cam.get('angular'):
        attrs.append('angular="%s"' % num(cam['angular']))
    out.append('%s  <viewpoint %s>' % (ind, ' '.join(attrs)))
    out.extend(_camera_xml(cam, ind + '    '))
    up = cam.get('world_up') or (0.0, 0.0, 1.0)
    out.append('%s    <up>' % ind)
    out.append(_pos('vec3f', up, ind + '      '))
    out.append('%s    </up>' % ind)
    out.append('%s  </viewpoint>' % ind)
    if include_clip and record.get('clip'):
        out.extend(_clip_xml(record['clip'], ind + '  '))
    if include_comments and record.get('comments'):
        out.extend(_comments_xml(record['comments'], ind + '  '))
    out.append('%s</view>' % ind)
    return out


def exchange_xml(records, doc_units, filename='', filepath='', include_clip=False,
                 include_comments=True):
    """The exchange XML text for records (tree order; folders rebuilt from each
    record's 'folder'; optional 'folder_guids' {path: guid} on records)."""
    lines = ['<?xml version="1.0" encoding="UTF-8" ?>', '',
             '<exchange xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'xsi:noNamespaceSchemaLocation="%s" units="%s" filename="%s" filepath="%s">'
             % (SCHEMA, unit_code(doc_units), esc(filename), esc(filepath)),
             '  <viewpoints>']

    def emit(nodes, ind):
        for node in nodes:
            if node[0] == 'folder':
                guid = (' guid="%s"' % esc(node[2])) if node[2] else ''
                lines.append('%s<viewfolder name="%s"%s>' % (ind, esc(node[1]), guid))
                emit(node[3], ind + '  ')
                lines.append('%s</viewfolder>' % ind)
            else:
                lines.extend(_view_xml(node[1], ind, include_clip, include_comments))
    emit(_tree(records), '    ')
    lines.append('  </viewpoints>')
    lines.append('</exchange>')
    return '\n'.join(lines) + '\n'


# ---- pure: exchange XML reader -------------------------------------------------------------


def _children(node, tag=None):
    return [c for c in node.childNodes if c.nodeType == c.ELEMENT_NODE and (tag is None or c.tagName == tag)]


def _first(node, tag):
    found = _children(node, tag)
    return found[0] if found else None


def _deep(node, *tags):
    for tag in tags:
        if node is None:
            return None
        node = _first(node, tag)
    return node


def _float(node, attr, default=None):
    if node is None or not node.hasAttribute(attr):
        return default
    try:
        return float(node.getAttribute(attr))
    except ValueError:
        return default


def _xyz_of(node, default=None):
    if node is None:
        return default
    return [_float(node, 'x', 0.0), _float(node, 'y', 0.0), _float(node, 'z', 0.0)]


def _text(node):
    if node is None:
        return ''
    return ''.join(c.data for c in node.childNodes if c.nodeType in (c.TEXT_NODE, c.CDATA_SECTION_NODE))


def _read_camera(vp_node):
    from namo import camera as _camera
    cam_node = _first(vp_node, 'camera')
    if cam_node is None:
        raise ValueError('a view has no camera')
    position = _xyz_of(_deep(cam_node, 'position', 'pos3f'))
    if position is None:
        raise ValueError('a camera has no position')
    quat = _deep(cam_node, 'rotation', 'quaternion')
    rotation = None
    if quat is not None:
        rotation = (_float(quat, 'a', 0.0), _float(quat, 'b', 0.0), _float(quat, 'c', 0.0), _float(quat, 'd', 1.0))
    projection = 'ortho' if cam_node.getAttribute('projection').lower().startswith('ortho') else 'persp'
    cam = _camera.make_cam(position, rotation=rotation or (0.0, 0.0, 0.0, 1.0), projection=projection,
                           height_field=_float(cam_node, 'height'),
                           focal_distance=_float(vp_node, 'focal'), aspect=_float(cam_node, 'aspect'))
    cam['position'] = list(cam['position'])
    cam['rotation'] = list(cam['rotation'])
    cam['direction'] = list(cam['direction'])
    cam['up'] = list(cam['up'])
    cam['near'] = _float(cam_node, 'near')
    cam['far'] = _float(cam_node, 'far')
    cam['linear'] = _float(vp_node, 'linear')
    cam['angular'] = _float(vp_node, 'angular')
    cam['world_up'] = _xyz_of(_deep(vp_node, 'up', 'vec3f'), [0.0, 0.0, 1.0])
    cam['tool'] = vp_node.getAttribute('tool') or 'none'
    cam['render'] = _name(RENDER_CODES, vp_node.getAttribute('render') or 'shaded', 'Shaded')
    cam['lighting'] = _name(LIGHTING_CODES, vp_node.getAttribute('lighting') or 'headlight', 'Headlight')
    return cam


def _read_clip(node):
    if node is None:
        return None
    clip = {'enabled': node.getAttribute('enabled') in ('1', 'true'),
            'mode': 'Box' if node.getAttribute('mode').lower() == 'box' else 'Planes',
            'linked': node.getAttribute('linked') in ('1', 'true'), 'planes': []}
    rng = _deep(node, 'range', 'box3f')
    if rng is not None:
        clip['range'] = [_xyz_of(_deep(rng, 'min', 'pos3f'), [0, 0, 0]), _xyz_of(_deep(rng, 'max', 'pos3f'), [0, 0, 0])]
    planes = _first(node, 'clipplanes')
    for index, plane_node in enumerate(_children(planes, 'clipplane') if planes is not None else []):
        plane = _first(plane_node, 'plane')
        normal = _xyz_of(_first(plane, 'vec3f') if plane is not None else None, [0.0, 0.0, 1.0])
        distance = _float(plane, 'distance', 0.0)
        state = (plane_node.getAttribute('state') or 'default').lower()
        clip['planes'].append({
            'index': index, 'state': state.capitalize(), 'enabled': state == 'enabled',
            'alignment': (plane_node.getAttribute('alignment') or 'custom').capitalize(),
            'normal': normal, 'distance': distance,
            'origin': [n * distance for n in normal],
        })
    clip['active'] = len([p for p in clip['planes'] if p['enabled']])
    box = _deep(node, 'box', 'box3f')
    if box is not None:
        quat = _deep(node, 'box-rotation', 'rotation', 'quaternion')
        clip['box'] = {'min': _xyz_of(_deep(box, 'min', 'pos3f'), [0, 0, 0]),
                       'max': _xyz_of(_deep(box, 'max', 'pos3f'), [0, 0, 0]),
                       'rotation': ([_float(quat, k, 0.0) for k in 'abcd'] if quat is not None else None)}
    return clip


def _read_comments(node):
    out = []
    for c in _children(node, 'comment') if node is not None else []:
        date = ''
        d = _deep(c, 'createddate', 'date')
        if d is not None:
            try:
                date = '%04d-%02d-%02dT%02d:%02d:%02d' % tuple(int(_float(d, k, 0)) for k in
                                                               ('year', 'month', 'day', 'hour', 'minute', 'second'))
            except Exception:
                date = ''
        out.append({'body': _text(_first(c, 'body')), 'author': _text(_first(c, 'user')),
                    'status': _name(STATUS_CODES, c.getAttribute('status') or 'new', 'New'), 'date': date})
    return out


def read_exchange(text):
    """(records, doc units name, notes) from exchange XML text. Raises ValueError
    with a sentence when the text is not a Navisworks viewpoint export."""
    try:
        dom = xml.dom.minidom.parseString(text.encode('utf-8') if not isinstance(text, bytes) else text)
    except Exception as error:
        raise ValueError('The file is not valid XML (%s).' % error)
    root = dom.documentElement
    if root.tagName != 'exchange':
        raise ValueError('The file is not a Navisworks exchange file (its root is <%s>).' % root.tagName)
    units = unit_name(root.getAttribute('units') or 'm')
    holder = _first(root, 'viewpoints')
    if holder is None:
        raise ValueError('The file holds no viewpoints (it may be a search set export).')
    records = []
    notes = []

    def walk(node, folder):
        for child in _children(node):
            if child.tagName == 'viewfolder':
                name = child.getAttribute('name') or 'Folder'
                walk(child, (folder + '/' + name) if folder else name)
            elif child.tagName == 'view':
                name = child.getAttribute('name') or 'View'
                vp_node = _first(child, 'viewpoint')
                if vp_node is None:
                    notes.append('%s has no viewpoint and was skipped.' % name)
                    continue
                try:
                    cam = _read_camera(vp_node)
                except ValueError as error:
                    notes.append('%s was skipped: %s.' % (name, error))
                    continue
                clip_node = _first(child, 'clipplaneset') or _first(vp_node, 'clipplaneset')
                records.append({'folder': folder, 'name': name, 'guid': child.getAttribute('guid') or '',
                                'camera': cam, 'clip': _read_clip(clip_node),
                                'comments': _read_comments(_first(child, 'comments'))})
            elif child.tagName == 'animation':
                notes.append('Animation %s was skipped.' % (child.getAttribute('name') or ''))
    walk(holder, '')
    return records, units, notes


# ---- pure: package (.nvp.json) -----------------------------------------------------


def package(records, doc_units, source=None, created=None):
    """The package dict Viewpoint Sync reads: records plus where they came from."""
    from namo import dates
    return {'format': FORMAT, 'version': VERSION, 'units': str(doc_units),
            'created': created or dates.iso(dates.now()), 'source': dict(source or {}),
            'views': [_clean_record(r) for r in records]}


def _clean_record(record):
    out = {}
    for key in ('folder', 'name', 'guid', 'camera', 'clip', 'comments'):
        out[key] = record.get(key)
    cam = dict(out['camera'] or {})
    for key in list(cam):
        value = cam[key]
        if isinstance(value, tuple):
            cam[key] = list(value)
    out['camera'] = cam
    out['folder'] = out['folder'] or ''
    out['comments'] = list(out['comments'] or [])
    return out


def read_package(data):
    """(records, units, notes) from a loaded package dict. ValueError with a
    sentence for anything that is not one."""
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise ValueError('The file is not a Playground viewpoint package.')
    if int(data.get('version') or 0) > VERSION:
        raise ValueError('The package was made by a newer Playground (version %s).' % data.get('version'))
    records = []
    notes = []
    for raw in data.get('views') or []:
        try:
            cam = raw['camera']
            if cam.get('position') is None or (cam.get('rotation') is None and cam.get('direction') is None):
                raise KeyError('camera')
            records.append({'folder': str(raw.get('folder') or ''), 'name': str(raw['name']),
                            'guid': str(raw.get('guid') or ''), 'camera': cam,
                            'clip': raw.get('clip'), 'comments': list(raw.get('comments') or [])})
        except (KeyError, TypeError, AttributeError):
            notes.append('A damaged view entry was skipped.')
    return records, str(data.get('units') or 'Meters'), notes


def read_file(path):
    """(records, units, notes) from a .nvp.json package or an exchange .xml."""
    from namo import paths
    if str(path).lower().endswith('.xml'):
        text = paths.read_text(path)
        if text is None:
            raise ValueError('Could not read %s.' % os.path.basename(path))
        return read_exchange(text)
    data = paths.load_json(path, default=None, move_aside=False)
    if data is None:
        raise ValueError('Could not read %s as a package.' % os.path.basename(path))
    return read_package(data)


def folder_counts(records):
    """[(folder path, number of views directly in it)] in first-seen order."""
    order = []
    counts = {}
    for r in records:
        f = r.get('folder') or ''
        if f not in counts:
            counts[f] = 0
            order.append(f)
        counts[f] += 1
    return [(f, counts[f]) for f in order]


EXPORT_FORMATS = [('Navisworks viewpoints XML (.xml)', 'xml'), ('Playground package (.nvp.json)', 'package'),
                  ('Both', 'both')]      # (label, value)


def export_fields(cfg):
    """The ui.form fields of Export Viewpoints' options step (cfg: the tool's
    settings with 'format', 'comments', 'clip_xml')."""
    return [
        {'kind': 'radio', 'key': 'format', 'label': 'Export as', 'options': EXPORT_FORMATS,
         'default': cfg['format'], 'fallback': None},
        {'kind': 'check', 'key': 'comments', 'label': 'Include the viewpoint comments', 'default': cfg['comments']},
        {'kind': 'check', 'key': 'clip_xml', 'label': 'Include section planes in the XML',
         'default': cfg['clip_xml'], 'enabled_if': ('format', ['xml', 'both']),
         'hint': 'The package always keeps them; Navisworks may ignore them in the XML.'},
    ]


# ==== API half ======================================================================


def _enum_name(value, default):
    try:
        return str(value)
    except Exception:
        return default


def viewpoint_extras(viewpoint):
    """Near/far, speeds, world up, render, lighting of a Viewpoint (best effort)."""
    extras = {}

    def grab(key, getter):
        try:
            extras[key] = getter()
        except Exception:
            extras[key] = None
    grab('near', lambda: float(viewpoint.NearPlaneDistance))
    grab('far', lambda: float(viewpoint.FarPlaneDistance))
    grab('linear', lambda: float(viewpoint.LinearSpeed) if viewpoint.HasLinearSpeed else None)
    grab('angular', lambda: float(viewpoint.AngularSpeed) if viewpoint.HasAngularSpeed else None)
    grab('world_up', lambda: [float(viewpoint.WorldUpVector.X), float(viewpoint.WorldUpVector.Y),
                              float(viewpoint.WorldUpVector.Z)] if viewpoint.HasWorldUpVector else None)
    grab('render', lambda: _enum_name(viewpoint.RenderStyle, 'Shaded') if viewpoint.HasRenderStyle else None)
    grab('lighting', lambda: _enum_name(viewpoint.Lighting, 'Headlight') if viewpoint.HasLighting else None)
    return extras


def folder_guids(document):
    """{'A/B': guid} for every saved-viewpoints folder."""
    from pynavis._api import Api
    out = {}

    def walk(children, folder):
        for child in children:
            if isinstance(child, Api.FolderItem):
                path = (folder + '/' + child.DisplayName) if folder else child.DisplayName
                out[path] = str(child.Guid)
                walk(child.Children, path)
    try:
        walk(document.SavedViewpoints.RootItem.Children, '')
    except Exception:
        pass
    return out


def records_from(rows, document=None, include_clip=True):
    """Records for view rows (vp_common.view_rows), in their order."""
    from namo import camera, vp_common
    guids = folder_guids(document) if document is not None else {}
    out = []
    for row in rows:
        viewpoint = row['item'].Viewpoint
        cam = camera.from_viewpoint(viewpoint)
        cam.update(viewpoint_extras(viewpoint))
        for key in ('position', 'rotation', 'direction', 'up', 'rotation_computed'):
            if isinstance(cam.get(key), tuple):
                cam[key] = list(cam[key])
        record = {'folder': row['folder'], 'name': row['name'], 'guid': row['guid'], 'camera': cam,
                  'clip': vp_common.clip_state_of(viewpoint) if include_clip else None,
                  'comments': vp_common.comments_of(row['item'])}
        if guids:
            record['folder_guids'] = guids
        out.append(record)
    return out


def write_exchange(path, records, document, include_clip=False, include_comments=True):
    from namo import paths, vp_common
    filename = vp_common.doc_path(document)
    text = exchange_xml(records, str(document.Units), os.path.basename(filename),
                        os.path.dirname(filename), include_clip, include_comments)
    return paths.atomic_write_text(path, text)


def write_package(path, records, document):
    from namo import config, paths, vp_common
    source = {'file': os.path.basename(vp_common.doc_path(document)), 'title': '',
              'user': config.user_name()}
    try:
        source['title'] = str(document.Title or '')
    except Exception:
        pass
    return paths.write_json(path, package(records, str(document.Units), source))

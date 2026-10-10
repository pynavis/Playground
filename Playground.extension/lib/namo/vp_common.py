# -*- coding: utf-8 -*-
"""Shared helpers for the Views tools (Viewpoints, Capture and Navigate panels).

Pure half (tested on both engines): counts and lengths as text, the default output
folder, the "which viewpoints" spec that reports store in their config
({'mode': 'all' | 'folders' | 'list', 'folders': [...], 'views': [[folder, name]]}),
ordering, size presets, a camera comparison and the cancel test used inside batches.

API half (lazy imports): the saved-viewpoint tree as rows, comments as plain dicts,
the section of ANY viewpoint as a dict and back (namo.camera only reads and writes the
CURRENT view; see dev/notes/views.md, request 1), and add_view(), which files a
detached Viewpoint into a folder with a keep-both / replace / skip policy.

Every saved-viewpoint path here is a (folder, name) pair rather than 'A/B/Name' text,
because a viewpoint name may itself contain a slash.
"""
import math
import os

SIZE_PRESETS = [
    ('1280 x 720', (1280, 720)),
    ('1920 x 1080', (1920, 1080)),
    ('3840 x 2160', (3840, 2160)),
]
CUSTOM = 'custom'


# ---- pure: text -------------------------------------------------------------------


def count_text(n):
    """1234 -> '1,234'."""
    return '{:,}'.format(int(n))


def plural(n, word, many=None):
    """'1 viewpoint', '3 viewpoints', '1,200 viewpoints'."""
    n = int(n)
    if n == 1:
        return '1 %s' % word
    return '%s %s' % (count_text(n), many or (word + 's'))


_IMPERIAL = ('feet', 'inches', 'yards', 'miles', 'mils', 'microinches')
_SYMBOLS = {'meters': 'm', 'centimeters': 'cm', 'millimeters': 'mm', 'kilometers': 'km', 'decimeters': 'dm',
            'micrometers': 'um', 'feet': 'ft', 'inches': 'in', 'yards': 'yd', 'miles': 'mi',
            'mils': 'mil', 'microinches': 'uin'}
_TO_METERS = {'meters': 1.0, 'centimeters': 0.01, 'millimeters': 0.001, 'kilometers': 1000.0, 'decimeters': 0.1,
              'micrometers': 1e-6, 'feet': 0.3048, 'inches': 0.0254, 'yards': 0.9144,
              'miles': 1609.344, 'mils': 2.54e-5, 'microinches': 2.54e-8}


def unit_symbol(doc_units):
    """'Feet' -> 'ft', 'Millimeters' -> 'mm' (unknown -> 'm')."""
    return _SYMBOLS.get(str(doc_units).lower(), 'm')


def to_meters_factor(doc_units):
    """Metres per document unit (1.0 for anything unknown)."""
    return _TO_METERS.get(str(doc_units).lower(), 1.0)


def unit_factor(from_units, to_units):
    """Multiply a length in from_units by this to get to_units."""
    return to_meters_factor(from_units) / to_meters_factor(to_units)


def length_text(value, doc_units, decimals=3):
    """A length as people read it: 12' 6 1/2" in Feet/Inches documents (feet and
    inches to 1/16"), else '12.345 m' with the document unit's symbol."""
    if value is None:
        return ''
    units = str(doc_units).lower()
    value = float(value)
    if units in ('feet', 'inches'):
        from namo import units as _units
        feet = value if units == 'feet' else value / 12.0
        return _units.format_feet_inches(feet)
    spec = '%.' + str(max(0, int(decimals))) + 'f'
    text = spec % value
    if text.startswith('-') and float(text) == 0.0:
        text = text[1:]
    return '%s %s' % (text, unit_symbol(doc_units))


def meters_text(value, doc_units, decimals=3):
    """The same length in metres, '3.810 m'."""
    if value is None:
        return ''
    spec = '%.' + str(max(0, int(decimals))) + 'f m'
    return spec % (float(value) * to_meters_factor(doc_units))


def signed_length(text, doc_units):
    """A length that may be negative, as typed: '-1250', '-3.5 m', "-12' 6\"", '4,2'.
    None when it does not read."""
    from namo import units
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    raw = str(text).strip()
    if not raw:
        return None
    number = units.parse_number(raw)
    if number is not None:
        return float(number)
    sign = 1.0
    if raw[:1] in '+-':
        sign = -1.0 if raw[0] == '-' else 1.0
        raw = raw[1:].strip()
    length = units.parse_length(raw, doc_units)
    return None if length is None else sign * float(length)


def length_input(value, doc_units):
    """A length (maybe negative) written the way it is typed back."""
    from namo import units
    value = float(value or 0.0)
    text = units.format_length_input(abs(value), doc_units)
    return ('-' + text) if value < 0 and text not in ('0', '0\' 0"') else text


def point_text(point, doc_units, decimals=3):
    """'X 12.000 m  Y 3.500 m  Z 0.000 m' (two spaces between axes)."""
    return '  '.join('%s %s' % (axis, length_text(v, doc_units, decimals))
                     for axis, v in zip('XYZ', point))


# ---- pure: folders and files ------------------------------------------------------


def documents_folder():
    """The user's Documents folder (MyDocuments under .NET, else ~/Documents)."""
    try:
        from System import Environment
        folder = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)
        if folder:
            return str(folder)
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def default_folder(doc_path, documents=None):
    """The document's folder when it has been saved (and still exists), else the
    user's Documents folder."""
    if doc_path:
        folder = os.path.dirname(str(doc_path))
        if folder and os.path.isdir(folder):
            return folder
    return documents or documents_folder()


def file_stem(doc_path, fallback='Untitled'):
    """'Hospital' for C:\\Jobs\\Hospital.nwf; fallback for an unsaved document."""
    if not doc_path:
        return fallback
    return os.path.splitext(os.path.basename(str(doc_path)))[0] or fallback


def join_path(folder, name):
    """'A/B/Name' for display ('Name' at top level)."""
    return '%s/%s' % (folder, name) if folder else name


def folder_label(folder):
    return folder if folder else '(top level)'


def parse_size(text):
    """(width, height) from '1920 x 1080', '1920x1080', '1920, 1080' or None."""
    if text is None:
        return None
    cleaned = str(text).lower().replace('*', 'x').replace(',', 'x').replace(' ', '')
    parts = [p for p in cleaned.split('x') if p]
    if len(parts) != 2:
        return None
    try:
        w, h = int(float(parts[0])), int(float(parts[1]))
    except ValueError:
        return None
    if not (16 <= w <= 8000 and 16 <= h <= 8000):
        return None
    return (w, h)


def size_options():
    """[(label, value)] for a size choice field: the presets plus Custom."""
    out = [(label, '%dx%d' % size) for label, size in SIZE_PRESETS]
    out.append(('Custom size', CUSTOM))
    return out


def size_from(choice, width=None, height=None):
    """(w, h) from a size choice value ('1920x1080' or 'custom' + width/height)."""
    if choice == CUSTOM:
        if not width or not height:
            return None
        return parse_size('%sx%s' % (width, height))
    return parse_size(choice)


# ---- pure: which viewpoints ------------------------------------------------------


def all_spec():
    return {'mode': 'all', 'folders': [], 'views': []}


def _under(folder, parent):
    """True when folder is parent or inside it ('' parent: top level only)."""
    if parent == '':
        return folder == ''
    return folder == parent or folder.startswith(parent + '/')


def select_rows(rows, spec):
    """The rows a spec picks, in tree order. rows: [{'folder', 'name', ...}].
    'folders' takes every view in each folder and its subfolders ('' = the top
    level only); 'list' takes the [folder, name] pairs (first match of each)."""
    spec = spec or all_spec()
    mode = spec.get('mode') or 'all'
    if mode == 'all':
        return list(rows)
    if mode == 'folders':
        wanted = list(spec.get('folders') or [])
        return [r for r in rows if any(_under(r['folder'], f) for f in wanted)]
    pairs = set(view_pairs(spec))
    out = []
    taken = set()
    for r in rows:
        key = (r['folder'], r['name'])
        if key in pairs and key not in taken:
            taken.add(key)
            out.append(r)
    return out


def missing_views(rows, spec):
    """[folder/name] of 'list' entries no row matches (a renamed or deleted view)."""
    if (spec or {}).get('mode') != 'list':
        return []
    have = set((r['folder'], r['name']) for r in rows)
    return [join_path(key[0], key[1]) for key in view_pairs(spec) if key not in have]


def view_pairs(spec):
    """The (folder, name) pairs of a 'list' spec, in order; malformed entries skipped."""
    out = []
    for pair in (spec or {}).get('views') or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            out.append((str(pair[0] or ''), str(pair[1])))
    return out


def folder_paths(rows):
    """Every folder path that holds views, with its ancestors, in first-seen order:
    [(path, views directly or below)]; '' (top level) first when it holds views."""
    counts = {}
    order = []
    for r in rows:
        folder = r['folder']
        chain = []
        if folder:
            parts = folder.split('/')
            for i in range(1, len(parts) + 1):
                chain.append('/'.join(parts[:i]))
        else:
            chain.append('')
        for path in chain:
            if path not in counts:
                counts[path] = 0
                order.append(path)
            counts[path] += 1
    order.sort(key=lambda p: (p != '', ))
    return [(p, counts[p]) for p in order]


def spec_for(rows, chosen):
    """The smallest spec that picks `chosen` (rows, a subset of rows): 'all' when
    everything, 'folders' when the choice is exactly some whole folders (so a
    scheduled run picks up views added to them later), else 'list'."""
    rows = list(rows)
    chosen_keys = set((r['folder'], r['name']) for r in chosen)
    all_keys = set((r['folder'], r['name']) for r in rows)
    if not chosen_keys:
        return {'mode': 'list', 'folders': [], 'views': []}
    if chosen_keys == all_keys:
        return all_spec()
    complete = []
    for path, _count in folder_paths(rows):
        inside = set((r['folder'], r['name']) for r in rows if _under(r['folder'], path))
        if inside and inside <= chosen_keys:
            complete.append(path)
    # keep only the outermost complete folders ('' stands alone: top level only)
    outer = [p for p in complete
             if p == '' or not any(q != '' and q != p and p.startswith(q + '/') for q in complete)]
    covered = set()
    for path in outer:
        for r in rows:
            if _under(r['folder'], path):
                covered.add((r['folder'], r['name']))
    if outer and covered == chosen_keys:
        return {'mode': 'folders', 'folders': outer, 'views': []}
    pairs = [[r['folder'], r['name']] for r in rows if (r['folder'], r['name']) in chosen_keys]
    return {'mode': 'list', 'folders': [], 'views': pairs}


def describe_spec(spec, total=None):
    """'All viewpoints', '2 folders', '14 viewpoints'."""
    spec = spec or all_spec()
    mode = spec.get('mode') or 'all'
    if mode == 'all':
        return 'All viewpoints'
    if mode == 'folders':
        folders = spec.get('folders') or []
        if len(folders) == 1:
            return 'Folder %s' % folder_label(folders[0])
        return plural(len(folders), 'folder')
    return plural(len(spec.get('views') or []), 'viewpoint')


def apply_order(rows, order):
    """rows re-ordered by `order` ([[folder, name], ...]); rows the order does not
    name keep their tree order after the named ones."""
    if not order:
        return list(rows)
    rank = {}
    for index, pair in enumerate(order):
        try:
            key = (str(pair[0] or ''), str(pair[1]))
        except (IndexError, TypeError):
            continue
        if key not in rank:
            rank[key] = index
    first = []
    rest = []
    for r in rows:
        key = (r['folder'], r['name'])
        (first if key in rank else rest).append(r)
    first.sort(key=lambda r: rank[(r['folder'], r['name'])])
    return first + rest


# ---- pure: cameras -----------------------------------------------------------------


def _quat_dot(a, b):
    return sum(float(x) * float(y) for x, y in zip(a, b))


def same_camera(a, b, position_tol=1e-3, angle_tol_deg=0.05):
    """True when two camera dicts (position + rotation) stand at the same place
    looking the same way. position_tol is in model units; q and -q are the same
    rotation."""
    if a is None or b is None:
        return False
    pa, pb = a.get('position'), b.get('position')
    qa, qb = a.get('rotation'), b.get('rotation')
    if pa is None or pb is None or qa is None or qb is None:
        return False
    if any(abs(float(x) - float(y)) > position_tol for x, y in zip(pa, pb)):
        return False
    na = math.sqrt(_quat_dot(qa, qa))
    nb = math.sqrt(_quat_dot(qb, qb))
    if not (na > 0 and nb > 0):
        return False
    cos_half = min(1.0, abs(_quat_dot(qa, qb)) / (na * nb))
    angle = math.degrees(2.0 * math.acos(cos_half))
    return angle <= angle_tol_deg


# ---- pure: batches -----------------------------------------------------------------


def is_cancel(error):
    """True for every Cancelled flavour (forms, items, reports)."""
    return type(error).__name__ == 'Cancelled'


def report_step(report, fraction, label):
    """Calls report(fraction, label) and returns True when the user cancelled
    (the callback raised a Cancelled). report None is never cancelled."""
    if report is None:
        return False
    try:
        result = report(fraction, label)
    except Exception as error:
        if is_cancel(error):
            return True
        raise
    return result == False  # noqa: E712 (False, not None, means stop)


# ==== API half ======================================================================


def active_doc():
    from pynavis._api import Application
    return Application.ActiveDocument


def doc_path(doc=None):
    document = doc if doc is not None else active_doc()
    try:
        return str(document.FileName or '')
    except Exception:
        return ''


def has_models(doc=None):
    document = doc if doc is not None else active_doc()
    try:
        return document is not None and document.Models.Count > 0
    except Exception:
        return False


def count_of(collection):
    """Count of a .NET collection or a Python list."""
    try:
        return int(collection.Count)
    except AttributeError:
        return len(collection)


def comments_of(saved):
    """[{'body', 'author', 'status', 'date'}] of a saved item's comments
    (date ISO text or '')."""
    out = []
    try:
        comments = saved.Comments
    except Exception:
        return out
    for comment in comments or []:
        try:
            body = str(comment.Body or '')
        except Exception:
            continue
        author = ''
        status = 'New'
        date = ''
        try:
            author = str(comment.Author or '')
        except Exception:
            pass
        try:
            status = str(comment.Status)
        except Exception:
            pass
        try:
            from namo import dates
            stamp = dates.from_net(comment.CreationDate)
            date = dates.iso(stamp) if stamp is not None else ''
        except Exception:
            date = ''
        out.append({'body': body, 'author': author, 'status': status, 'date': date})
    return out


def view_rows(doc=None, include_animations=False):
    """The saved viewpoints as rows in tree order: {'folder' 'A/B' ('' at top
    level), 'name', 'path' (display), 'guid', 'item' (the live SavedItem),
    'animation' bool, 'comments' (count)}."""
    from pynavis._api import Api
    from pynavis.doc import walk_saved_viewpoints
    document = doc if doc is not None else active_doc()
    rows = []
    for folders, item in walk_saved_viewpoints(document):
        is_view = isinstance(item, Api.SavedViewpoint)
        if not is_view and not include_animations:
            continue
        folder = '/'.join(folders)
        try:
            comments = count_of(item.Comments)
        except Exception:
            comments = 0
        rows.append({'folder': folder, 'name': str(item.DisplayName), 'path': join_path(folder, item.DisplayName),
                     'guid': str(item.Guid), 'item': item, 'animation': not is_view,
                     'comments': comments})
    return rows


def choose_views(title, rows, spec=None, prompt=None, ok='OK'):
    """A ticked list of the viewpoints (Folder, Name, Comments), opened with the
    spec's views ticked (all when None). Returns (chosen rows, spec) or None
    when cancelled."""
    from namo import ui
    ticked = select_rows(rows, spec) if spec else list(rows)
    # By identity: select_rows hands back the same row dicts, and `r in ticked` would
    # compare whole dicts (live saved items included) rows x rows times.
    marked = set(id(r) for r in ticked)
    checked = [i for i, r in enumerate(rows) if id(r) in marked]
    table = [{'value': i, 'cells': [folder_label(r['folder']), r['name'], r['comments']]}
             for i, r in enumerate(rows)]
    picked = ui.choose(title, table, ['Folder', 'Name', 'Comments'], multiselect=True,
                       checked=checked, ok=ok,
                       prompt=prompt or 'Tick the viewpoints. Type a folder name in the filter, '
                                        'then Select all, to take a whole folder.')
    if picked is None:
        return None
    chosen = [rows[i] for i in sorted(picked)]
    return chosen, spec_for(rows, chosen)


def _xyz(p):
    return [float(p.X), float(p.Y), float(p.Z)]


def clip_state_of(viewpoint):
    """The section of ANY viewpoint as namo.camera.clip_state's dict (that function
    reads only the current view). JSON-safe; None when unreadable."""
    from pynavis._api import Api
    from namo import camera
    try:
        planes = viewpoint.ClipPlanes
    except Exception:
        return None
    payload = {'enabled': bool(planes.Enabled),
               'mode': 'Box' if planes.Mode == Api.ClipPlaneSetMode.Box else 'Planes',
               'linked': bool(planes.Linked), 'planes': []}
    try:
        rng = planes.Range
        recorded = [_xyz(rng.Min), _xyz(rng.Max)]
        if camera.range_ok(recorded):
            payload['range'] = recorded
    except Exception:
        pass
    for index in range(planes.Size()):
        plane = planes.Get(index)
        record = {'index': index, 'state': str(plane.State), 'enabled': bool(plane.Enabled),
                  'origin': _xyz(plane.Origin), 'normal': _xyz(plane.Normal)}
        try:
            record['alignment'] = str(plane.Alignment)
        except Exception:
            pass
        try:
            record['distance'] = float(plane.Distance)
        except Exception:
            pass
        payload['planes'].append(record)
    payload['active'] = len([p for p in payload['planes'] if p['enabled']])
    if payload['mode'] == 'Box':
        box = {'min': _xyz(planes.Box.Min), 'max': _xyz(planes.Box.Max), 'rotation': None}
        try:
            api_box = Api.BoundingBox3D()
            rotation = Api.Rotation3D()
            planes.GetOrientedBox(api_box, rotation)
            box = {'min': _xyz(api_box.Min), 'max': _xyz(api_box.Max),
                   'rotation': [float(rotation.A), float(rotation.B), float(rotation.C),
                                float(rotation.D)]}
        except Exception:
            pass
        payload['box'] = box
    return payload


def apply_clip_state(viewpoint, payload):
    """Writes a clip_state dict onto an editable (detached) Viewpoint, the way
    namo.camera.set_clip_state does for the current view. None or {} leaves the
    viewpoint's section alone. Returns the viewpoint."""
    if not payload:
        return viewpoint
    from pynavis._api import Api
    from namo import camera
    planes = viewpoint.ClipPlanes
    box_mode = payload.get('mode') == 'Box'
    planes.Mode = Api.ClipPlaneSetMode.Box if box_mode else Api.ClipPlaneSetMode.Planes
    planes.Linked = bool(payload.get('linked'))
    rng = payload.get('range')
    if camera.range_ok(rng):
        planes.Range = Api.BoundingBox3D(Api.Point3D(*[float(v) for v in rng[0]]),
                                         Api.Point3D(*[float(v) for v in rng[1]]))
    if box_mode:
        box = payload.get('box') or {}
        corners = [box.get('min'), box.get('max')]
        if camera.range_ok(corners):
            api_box = Api.BoundingBox3D(Api.Point3D(*[float(v) for v in corners[0]]),
                                        Api.Point3D(*[float(v) for v in corners[1]]))
            done = False
            rotation = box.get('rotation')
            if rotation:
                try:
                    planes.SetOrientedBox(api_box, Api.Rotation3D(*[float(x) for x in rotation]))
                    done = True
                except Exception:
                    done = False
            if not done:
                planes.Box = api_box
    else:
        size = planes.Size()
        for record in payload.get('planes') or []:
            index = record.get('index', -1)
            if not (0 <= index < size):
                continue
            plane = planes.Get(index)
            normal = record.get('normal') or [0.0, 0.0, 1.0]
            plane.AlignToPick(Api.ClipPlaneAlignment.Custom,
                              Api.Point3D(*[float(v) for v in record.get('origin') or [0, 0, 0]]),
                              Api.UnitVector3D(*[float(v) for v in normal]))
            plane.State = getattr(Api.ClipPlaneState, str(record.get('state', 'Default')),
                                  Api.ClipPlaneState.Default)
            plane.Enabled = bool(record.get('enabled'))
    planes.Enabled = bool(payload.get('enabled'))
    return viewpoint


def set_planes(viewpoint, wanted, box=None):
    """Puts horizontal (or any) planes on a detached viewpoint: wanted is
    [(origin, normal)] (normals INTO the kept volume, namo.camera.horizontal_planes);
    plane i gets wanted[i], the rest are switched off; box ((min), (max)) becomes
    the clip range. An empty list switches sectioning off."""
    from pynavis._api import Api
    planes = viewpoint.ClipPlanes
    if not wanted:
        planes.Enabled = False
        return viewpoint
    planes.Mode = Api.ClipPlaneSetMode.Planes
    planes.Linked = False
    if box is not None:
        try:
            planes.Range = Api.BoundingBox3D(Api.Point3D(*box[0]), Api.Point3D(*box[1]))
        except Exception:
            pass
    for index in range(planes.Size()):
        plane = planes.Get(index)
        if index < len(wanted):
            origin, normal = wanted[index]
            plane.AlignToPick(Api.ClipPlaneAlignment.Custom,
                              Api.Point3D(float(origin[0]), float(origin[1]), float(origin[2])),
                              Api.UnitVector3D(float(normal[0]), float(normal[1]), float(normal[2])))
            plane.State = Api.ClipPlaneState.Enabled
            plane.Enabled = True
        else:
            plane.Enabled = False
    planes.Enabled = True
    return viewpoint


def find_child(parent, name, folders=False):
    """The direct child of a saved-viewpoints folder named `name` (exact), a
    folder when folders=True, else a non-folder; None when absent."""
    from pynavis._api import Api
    loose = None
    wanted = str(name).strip().lower()
    for child in parent.Children:
        try:
            if isinstance(child, Api.FolderItem) != bool(folders):
                continue
            text = str(child.DisplayName)
        except Exception:
            continue
        if text == name:
            return child
        if loose is None and text.strip().lower() == wanted:
            loose = child
    return loose


def add_comments(document, item, comments):
    """Adds comments (text or {'body', 'author', 'status'} dicts) to a live saved
    item. Returns how many were added."""
    from pynavis._api import Api
    added = 0
    for comment in comments or []:
        if isinstance(comment, dict):
            body = str(comment.get('body') or '')
            author = str(comment.get('author') or '')
            status = getattr(Api.CommentStatus, str(comment.get('status') or 'New'),
                             Api.CommentStatus.New)
        else:
            body, author, status = str(comment or ''), '', Api.CommentStatus.New
        if not body.strip():
            continue
        # A comment Navisworks refuses must not fail the viewpoint it belongs to (the
        # view is already filed by now): log it and carry on.
        try:
            made = Api.Comment(body, status, author) if author else Api.Comment(body, status)
            document.SavedViewpoints.AddComment(item, made)
            added += 1
        except Exception as error:
            from namo import session
            session.log('warning', 'comment not added to %s: %s' % (getattr(item, 'DisplayName', 'a viewpoint'), error))
    return added


def add_view(document, folder_path, name, viewpoint=None, saved_item=None, comments=None,
             policy='keep'):
    """Files a viewpoint into the folder at folder_path ('' = top level, created as
    needed). Give a detached Viewpoint (wrapped in a new SavedViewpoint) or a
    ready SavedViewpoint (saved_item, e.g. CaptureRuntimeOverrides()).

    policy for an existing sibling with the same name: 'keep' adds 'name (2)',
    'replace' swaps it in place (same position), 'skip' leaves it.
    Returns (live tree-resident item, outcome 'created' | 'replaced' | 'skipped').
    Call inside a viewpoints.transaction."""
    from pynavis._api import Api
    from namo import camera, naming
    saved = document.SavedViewpoints
    at_root = not camera.split_path(folder_path)
    parent = saved.RootItem if at_root else camera.ensure_folder(folder_path, document)
    name = str(name)
    existing = find_child(parent, name)
    if existing is not None and policy == 'skip':
        return existing, 'skipped'
    item = saved_item if saved_item is not None else Api.SavedViewpoint(viewpoint)
    if existing is not None and policy == 'replace':
        index = -1
        children = parent.Children
        for i in range(count_of(children)):
            if children[i] is existing or str(children[i].Guid) == str(existing.Guid):
                index = i
                break
        item.DisplayName = name
        if at_root:
            saved.ReplaceWithCopy(index, item)
        else:
            saved.ReplaceWithCopy(parent, index, item)
        live = parent.Children[index]
        add_comments(document, live, comments)
        return live, 'replaced'
    siblings = [str(child.DisplayName) for child in parent.Children]
    final = naming.unique(name, siblings) if existing is not None else name
    item.DisplayName = final
    if at_root:
        saved.AddCopy(item)
    else:
        saved.AddCopy(parent, item)
    children = parent.Children
    live = children[count_of(children) - 1]
    if str(live.DisplayName) != final:
        live = find_child(parent, final) or live
    add_comments(document, live, comments)
    return live, 'created'

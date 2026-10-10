# -*- coding: utf-8 -*-
"""Viewpoints from Excel: saved viewpoints to a workbook and back.

The sheet 'Viewpoints' has one row per viewpoint, lengths in DOCUMENT units as plain
numbers (decimal feet in a feet model):

    Folder | Name | Eye X | Eye Y | Eye Z | Target X | Target Y | Target Z |
    Up X | Up Y | Up Z | Projection | FOV/Height | Comment

Target is the point the camera looks at (eye + view direction x focal distance).
FOV/Height is the vertical field of view in degrees for a Perspective view and the
visible height for an Orthographic one. Import matches rows to saved viewpoints by
Folder + Name (case-insensitive): a match gets the row's camera (its section,
comments, redlines, hidden items and overrides stay: the saved item is copied,
edited and swapped back in, the way pyNavis' Speeds to Saved does it), anything
else is created with the section off. Comment lines not already on the viewpoint are added; nothing is ever
removed. Header names are found wherever the header row is (within the first ten
rows) and in any column order; cells may hold numbers or text with units ('12.5 m',
"41' 6\"").

Pure half: header mapping, cell and row parsing, the plan; API half: reading views,
writing the workbook (namo.xlsx), applying the plan in one transaction.
"""
import math

COLUMNS = ['Folder', 'Name', 'Eye X', 'Eye Y', 'Eye Z', 'Target X', 'Target Y', 'Target Z',
           'Up X', 'Up Y', 'Up Z', 'Projection', 'FOV/Height', 'Comment']
SHEET = 'Viewpoints'

ALIASES = {
    'folder': ['folder', 'folder path', 'path'],
    'name': ['name', 'viewpoint', 'viewpoint name', 'view'],
    'eye_x': ['eye x', 'eyex', 'position x', 'camera x'],
    'eye_y': ['eye y', 'eyey', 'position y', 'camera y'],
    'eye_z': ['eye z', 'eyez', 'position z', 'camera z'],
    'target_x': ['target x', 'targetx', 'look at x'],
    'target_y': ['target y', 'targety', 'look at y'],
    'target_z': ['target z', 'targetz', 'look at z'],
    'up_x': ['up x', 'upx'],
    'up_y': ['up y', 'upy'],
    'up_z': ['up z', 'upz'],
    'projection': ['projection', 'type', 'camera type'],
    'fov': ['fov/height', 'fov / height', 'fov', 'field of view', 'height', 'fov or height'],
    'comment': ['comment', 'comments', 'note', 'notes'],
}
REQUIRED = ['name', 'eye_x', 'eye_y', 'eye_z', 'target_x', 'target_y', 'target_z']
LABELS = {'name': 'Name', 'eye_x': 'Eye X', 'eye_y': 'Eye Y', 'eye_z': 'Eye Z',
          'target_x': 'Target X', 'target_y': 'Target Y', 'target_z': 'Target Z'}


# ---- pure ---------------------------------------------------------------------------


def _key(text):
    return ' '.join(str(text or '').replace('_', ' ').strip().lower().split())


def header_map(row):
    """{field: column index} for a header row; each field takes the first column
    whose header matches one of its aliases."""
    found = {}
    texts = [_key(cell) for cell in row]
    for field in ['folder', 'name', 'eye_x', 'eye_y', 'eye_z', 'target_x', 'target_y', 'target_z',
                  'up_x', 'up_y', 'up_z', 'projection', 'fov', 'comment']:
        for alias in ALIASES[field]:
            if alias in texts and texts.index(alias) not in found.values():
                found[field] = texts.index(alias)
                break
    return found


def find_header(rows, scan=10):
    """(row index, mapping) of the first row (within `scan`) that names every
    required column, or (None, missing labels of the best row)."""
    best_missing = [LABELS[f] for f in REQUIRED]
    for index, row in enumerate(rows[:scan]):
        mapping = header_map(row)
        missing = [LABELS[f] for f in REQUIRED if f not in mapping]
        if not missing:
            return index, mapping
        if len(missing) < len(best_missing):
            best_missing = missing
    return None, best_missing


def parse_length_cell(value, doc_units):
    """A length from a cell: a number, numeric text ('1,234.5', '12,5'), or text with
    units read like a pyNavis length field ('12.5 m', "41' 6\"", '-3 ft'). None when
    blank; ValueError when it does not read."""
    from namo import units
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('a yes/no value is not a length')
    if isinstance(value, (int, float)):
        if value != value or value in (float('inf'), float('-inf')):
            raise ValueError('not a number')
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    number = units.parse_number(text)
    if number is not None:
        return float(number)
    sign = 1.0
    if text[:1] in '+-':
        sign = -1.0 if text[0] == '-' else 1.0
        text = text[1:].strip()
    length = units.parse_length(text, doc_units)
    if length is None:
        raise ValueError('%r is not a length' % str(value))
    return sign * float(length)


def parse_projection(value):
    """'persp' | 'ortho' from 'Perspective', 'persp', 'P', 'Orthographic', 'ortho',
    'O', 'Parallel'; blank is perspective. ValueError otherwise."""
    text = _key(value)
    if not text or text in ('p', 'persp', 'perspective'):
        return 'persp'
    if text in ('o', 'ortho', 'orthographic', 'parallel', 'orthogonal'):
        return 'ortho'
    raise ValueError('Projection must be Perspective or Orthographic, not %r' % str(value))


def _cell(row, mapping, field):
    index = mapping.get(field)
    if index is None or index >= len(row):
        return None
    return row[index]


def _text_cell(value):
    if value is None:
        return ''
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def _fov_value(value, projection, doc_units):
    """FOV degrees (perspective; '60', '60°', '60 deg') or a height (orthographic,
    any length text). ValueError when it does not read."""
    from namo import units
    if projection == 'ortho':
        try:
            return parse_length_cell(value, doc_units)
        except ValueError:
            raise ValueError('FOV/Height is not a length')
    if isinstance(value, bool):
        raise ValueError('FOV/Height is not a number')
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(chr(176), ' ').lower().replace('degrees', ' ').replace('deg', ' ').strip()
    number = units.parse_number(text)
    if number is None:
        raise ValueError('FOV/Height is not a number')
    return float(number)


def parse_row(row, mapping, doc_units):
    """A record {'folder', 'name', 'eye', 'target', 'up', 'projection',
    'fov_height', 'comment'} or raises ValueError with the problem."""
    name = _text_cell(_cell(row, mapping, 'name'))
    if not name:
        raise ValueError('Name is empty')
    folder = '/'.join(p.strip() for p in _text_cell(_cell(row, mapping, 'folder')).replace('\\', '/').split('/')
                      if p.strip())
    coords = {}
    for field in ('eye_x', 'eye_y', 'eye_z', 'target_x', 'target_y', 'target_z'):
        try:
            value = parse_length_cell(_cell(row, mapping, field), doc_units)
        except ValueError as error:
            raise ValueError('%s: %s' % (LABELS[field], error))
        if value is None:
            raise ValueError('%s is empty' % LABELS[field])
        coords[field] = value
    eye = (coords['eye_x'], coords['eye_y'], coords['eye_z'])
    target = (coords['target_x'], coords['target_y'], coords['target_z'])
    if math.sqrt(sum((a - b) ** 2 for a, b in zip(eye, target))) < 1e-9:
        raise ValueError('Eye and Target are the same point')
    up = []
    for field in ('up_x', 'up_y', 'up_z'):
        try:
            up.append(parse_length_cell(_cell(row, mapping, field), doc_units))
        except ValueError:
            raise ValueError('Up %s is not a number' % field[-1].upper())
    if any(v is None for v in up):
        up = (0.0, 0.0, 1.0)
    else:
        up = tuple(up)
        if math.sqrt(sum(v * v for v in up)) < 1e-12:
            up = (0.0, 0.0, 1.0)
    projection = parse_projection(_cell(row, mapping, 'projection'))
    fov = _cell(row, mapping, 'fov')
    fov_height = None
    if fov is not None and str(fov).strip() != '':
        fov_height = _fov_value(fov, projection, doc_units)
        if projection == 'persp' and not (0.5 <= fov_height <= 179.0):
            raise ValueError('FOV must be between 0.5 and 179 degrees')
        if projection == 'ortho' and not (fov_height > 0):
            raise ValueError('Height must be more than zero')
    comment = _cell(row, mapping, 'comment')
    return {'folder': folder, 'name': name, 'eye': eye, 'target': target, 'up': up,
            'projection': projection, 'fov_height': fov_height,
            'comment': '' if comment is None else str(comment).strip()}


def is_blank(row):
    return all(cell is None or str(cell).strip() == '' for cell in row)


def parse_rows(rows, doc_units):
    """(records, errors, header row index). records carry 'row' (1-based Excel
    row); errors are [(row, folder, name, problem)]. A row repeating an earlier
    Folder + Name is an error. ValueError when no header row is found."""
    index, mapping = find_header(rows)
    if index is None:
        raise ValueError('No header row found: the sheet needs the columns %s.' % ', '.join(mapping))
    records = []
    errors = []
    seen = {}
    for offset, row in enumerate(rows[index + 1:]):
        excel_row = index + offset + 2
        if is_blank(row):
            continue
        try:
            record = parse_row(row, mapping, doc_units)
        except ValueError as error:
            errors.append((excel_row, _text_cell(_cell(row, mapping, 'folder')),
                           _text_cell(_cell(row, mapping, 'name')), str(error)))
            continue
        key = (record['folder'].lower(), record['name'].lower())
        if key in seen:
            errors.append((excel_row, record['folder'], record['name'],
                           'Repeats Folder and Name of row %d' % seen[key]))
            continue
        seen[key] = excel_row
        record['row'] = excel_row
        records.append(record)
    return records, errors, index


def camera_of(record, default_fov=60.0):
    """namo.camera dict for a parsed record."""
    from namo import camera
    eye, target = record['eye'], record['target']
    direction = tuple(t - e for e, t in zip(eye, target))
    distance = math.sqrt(sum(v * v for v in direction))
    if record['projection'] == 'ortho':
        height = record['fov_height'] if record['fov_height'] else 2.0 * distance * math.tan(math.radians(default_fov / 2.0))
    else:
        height = camera.height_field_for(record['fov_height'] or default_fov)
    return camera.make_cam(eye, direction=direction, up=record['up'], projection=record['projection'],
                           height_field=height, focal_distance=distance)


def row_of(folder, name, cam, comments_text, default_distance):
    """The workbook row for a camera dict (target from the focal distance)."""
    from namo import camera
    distance = cam.get('focal_distance') or default_distance
    target = camera.target_of(cam, distance)
    eye = cam['position']
    up = cam.get('up') or (0.0, 0.0, 1.0)
    if str(cam.get('projection')).startswith('ortho'):
        projection, fov = 'Orthographic', cam.get('height_field')
    else:
        projection = 'Perspective'
        fov = camera.fov_degrees(cam.get('height_field'), 'persp')
    return [folder, name, eye[0], eye[1], eye[2], target[0], target[1], target[2],
            up[0], up[1], up[2], projection, fov, comments_text]


def comment_lines(text):
    """Non-empty lines of a Comment cell."""
    return [line.strip() for line in str(text or '').replace('\r', '\n').split('\n') if line.strip()]


def new_comments(cell_text, existing_bodies):
    """Lines of the cell that are not already one of the viewpoint's comments."""
    have = set(b.strip() for b in existing_bodies)
    for body in existing_bodies:
        for line in comment_lines(body):
            have.add(line)
    return [line for line in comment_lines(cell_text) if line not in have]


def plan(records, exists):
    """[(record, 'create' | 'update')] where exists(folder, name) is True for a
    viewpoint already in the document."""
    return [(r, 'update' if exists(r['folder'], r['name']) else 'create') for r in records]


def plan_sentence(steps, errors):
    from namo import vp_common
    create = len([s for s in steps if s[1] == 'create'])
    update = len([s for s in steps if s[1] == 'update'])
    parts = []
    if create:
        parts.append('create %s' % vp_common.plural(create, 'viewpoint'))
    if update:
        parts.append('update %s' % vp_common.plural(update, 'viewpoint'))
    if errors:
        parts.append('skip %s with problems' % vp_common.plural(len(errors), 'row'))
    text = ', '.join(parts) or 'nothing to do'
    return text[0].upper() + text[1:] + '.'


# ==== API half ======================================================================


def write_workbook(path, document, rows, example=False):
    """Writes the viewpoints of `rows` (vp_common.view_rows) to path. example=True
    writes the current view as one sample row (the blank template)."""
    from namo import camera, config, vp_common, xlsx
    units = str(document.Units)
    k = 1.0 / vp_common.to_meters_factor(units)
    wb = xlsx.Workbook(title='Viewpoints', author=config.user_name())
    wb.style('coord', num_format='0.000')
    ws = wb.sheet(SHEET)
    file_name = vp_common.file_stem(vp_common.doc_path(document))
    ws.title('Viewpoints of %s' % file_name, span=len(COLUMNS))
    unit_word = units.lower()
    if unit_word in ('feet', 'inches'):
        unit_word = 'decimal %s' % unit_word
    ws.subtitle('Lengths in %s. FOV/Height: vertical field of view in degrees (Perspective) or '
                'visible height (Orthographic). Edit, then import with Viewpoints from Excel.' % unit_word,
                span=len(COLUMNS))
    widths = [22, 28, 12, 12, 12, 12, 12, 12, 8, 8, 8, 14, 11, 40]
    styles = [None, None] + ['coord'] * 9 + [None, 'num2', 'wrap']
    ws.columns([(h, w, s) for h, w, s in zip(COLUMNS, widths, styles)])
    count = 0
    if example:
        cam = camera.capture(document)
        ws.row(row_of('Example', 'Current view', cam, 'Delete this row or edit it.', 10.0 * k))
        count = 1
    for row in rows:
        cam = camera.from_viewpoint(row['item'].Viewpoint)
        text = '\n'.join(c['body'] for c in vp_common.comments_of(row['item']))
        ws.row(row_of(row['folder'], row['name'], cam, text, 10.0 * k))
        count += 1
    ws.autofilter()
    notes = wb.sheet('Read me')
    notes.title('How to use this workbook', span=2)
    notes.columns([('Column', 18, 'bold'), ('Meaning', 90, 'wrap')])
    for line in [
            ('Folder', 'Saved viewpoints folder, with / between levels. Empty: top level.'),
            ('Name', 'Viewpoint name. Folder + Name finds the viewpoint to update (case does not matter).'),
            ('Eye X, Y, Z', 'Where the camera stands, in %s.' % unit_word),
            ('Target X, Y, Z', 'The point the camera looks at.'),
            ('Up X, Y, Z', 'Which way is up on screen. Leave empty for Z up.'),
            ('Projection', 'Perspective or Orthographic. Empty: Perspective.'),
            ('FOV/Height', 'Perspective: vertical field of view in degrees (60 when empty). '
                           'Orthographic: visible height.'),
            ('Comment', 'Lines not already on the viewpoint are added as comments. Nothing is removed.'),
            ('Import', 'Existing viewpoints keep their section, hidden items and colors; new ones '
                       'are made with sectioning off. One Ctrl+Z undoes the whole import.')]:
        notes.row(list(line))
    wb.save(path)
    return count


def read_sheet(path):
    """Rows of the 'Viewpoints' sheet (else the first sheet) via pynavis.xl."""
    from pynavis import xl
    names = xl.sheets(path)
    sheet = None
    for name in names:
        if name.strip().lower() == SHEET.lower():
            sheet = name
            break
    return xl.read(path, sheet)


def lookup(document):
    """(exists(folder, name), find(folder, name) -> live SavedViewpoint)."""
    from namo import vp_common
    rows = vp_common.view_rows(document)
    index = {}
    for row in rows:
        index.setdefault((row['folder'].lower(), row['name'].lower()), row['item'])
    return (lambda f, n: (f.lower(), n.lower()) in index,
            lambda f, n: index.get((f.lower(), n.lower())))


def _index_in(children, item):
    from namo import vp_common
    guid = str(item.Guid)
    for i in range(vp_common.count_of(children)):
        if str(children[i].Guid) == guid:
            return i
    return -1


def _editable_view_of(item):
    """The Viewpoint of a DETACHED saved-item copy when that copy really takes a
    write, else None. The probe pyNavis' Speeds to Saved uses (its lib/vpspeeds.py,
    proven in the field): write, read back through the item, restore. IsReadOnly is
    what the object claims; the read-back is what it did."""
    try:
        view = item.Viewpoint
        if view.IsReadOnly:
            return None
        before = view.LinearSpeed
        view.LinearSpeed = before + 7.0
        stuck = abs(item.Viewpoint.LinearSpeed - (before + 7.0)) < 1e-9
        view.LinearSpeed = before
        return item.Viewpoint if stuck else None
    except Exception:
        return None


def full_copy_works(saved):
    """Whether this document hands back editable saved-viewpoint copies (decided on
    a detached copy, so the probe cannot touch the document)."""
    try:
        return _editable_view_of(saved.CreateCopy()) is not None
    except Exception:
        return False


def _edited_copy(saved, cam):
    """A detached copy of the saved viewpoint carrying cam, or None when a copy
    will not take the write. The copy keeps the name, comments, redlines, hidden
    items and overrides, and nothing is recalled on screen."""
    from namo import camera
    try:
        copy = saved.CreateCopy()
        view = _editable_view_of(copy)
        if view is None:
            return None
        camera.write_camera(view, cam)
        return copy
    except Exception:
        return None


def update_camera(document, saved, cam):
    """Gives a saved viewpoint a new camera, keeping its name, place, Guid,
    comments and section.

    The route is the one pyNavis' Speeds to Saved ships with: copy the saved ITEM,
    edit the copy's viewpoint (a detached copy is not read-only) and swap it in with
    ReplaceWithCopy. Nothing is loaded on screen and the copy carries redlines,
    hidden items and overrides across. Only a document that refuses an editable
    copy falls back: a view that stores hidden items or overrides is then recalled,
    re-aimed and updated from the view (ReplaceFromCurrentView; the caller wraps the
    batch in capture.KeepState), any other is rebuilt from its camera."""
    from pynavis._api import Api
    from namo import camera, vp_common
    saved_items = document.SavedViewpoints
    replacement = _edited_copy(saved, cam)
    if replacement is None:
        overrides = False
        try:
            overrides = bool(saved.ContainsVisibilityOverrides) or bool(saved.ContainsAppearanceOverrides)
        except Exception:
            overrides = False
        if overrides:
            saved_items.CurrentSavedViewpoint = saved
            camera.apply(cam, document)
            saved_items.ReplaceFromCurrentView(saved)
            return saved
        replacement = Api.SavedViewpoint(camera.to_viewpoint(cam, base=saved.Viewpoint))
    parent = saved.Parent
    root = saved_items.RootItem
    at_root = parent is None or str(parent.Guid) == str(root.Guid)
    holder = root if at_root else parent
    index = _index_in(holder.Children, saved)
    if index < 0:
        raise RuntimeError('the viewpoint is no longer in its folder')
    replacement.DisplayName = saved.DisplayName
    try:
        replacement.Guid = saved.Guid           # settable: the view keeps its identity
    except Exception:
        pass
    comments = Api.CommentCollection(saved.Comments)
    if at_root:
        saved_items.ReplaceWithCopy(index, replacement)
    else:
        saved_items.ReplaceWithCopy(holder, index, replacement)
    live = holder.Children[index]
    try:
        if vp_common.count_of(live.Comments) < vp_common.count_of(comments):
            saved_items.EditComments(live, comments)
    except Exception:
        pass
    return live


def apply(document, steps, report=None):
    """Applies a plan in ONE transaction (the view is restored afterwards).
    Returns {'created', 'updated', 'failed' [(row, name, error)], 'stopped'}."""
    from pynavis.viewpoints import transaction
    from namo import capture, session, vp_common
    out = {'created': 0, 'updated': 0, 'failed': [], 'stopped': False, 'comments': 0}
    _exists, find = lookup(document)
    updated = [find(r['folder'], r['name']) for r, action in steps if action == 'update']
    updated = [s for s in updated if s is not None]
    # Only the fallback route recalls views on screen; when copies are editable (the
    # normal case) nothing is recalled and there is no state to keep.
    recalled = [] if (updated and full_copy_works(updated[0])) else updated
    with transaction('Viewpoints from Excel', document):
        with capture.KeepState(document, recalled):
            base = document.CurrentViewpoint.CreateCopy()
            for index, (record, action) in enumerate(steps):
                if vp_common.report_step(report, float(index) / max(1, len(steps)),
                                         'Row %d: %s' % (record['row'], record['name'])):
                    out['stopped'] = True
                    break
                try:
                    cam = camera_of(record)
                    if action == 'update':
                        saved = find(record['folder'], record['name'])
                        if saved is None:
                            raise RuntimeError('the viewpoint is no longer there')
                        live = update_camera(document, saved, cam)
                        bodies = [c['body'] for c in vp_common.comments_of(live)]
                        out['comments'] += vp_common.add_comments(document, live,
                                                                  new_comments(record['comment'], bodies))
                        out['updated'] += 1
                    else:
                        from namo import camera
                        viewpoint = base.CreateCopy()
                        viewpoint.ClipPlanes.Enabled = False
                        viewpoint = camera.to_viewpoint(cam, base=viewpoint)
                        vp_common.add_view(document, record['folder'], record['name'], viewpoint=viewpoint,
                                           comments=comment_lines(record['comment']), policy='keep')
                        out['created'] += 1
                except Exception as error:
                    if vp_common.is_cancel(error):
                        out['stopped'] = True
                        break
                    session.log('warning', 'Viewpoints from Excel row %d: %s' % (record['row'], error))
                    out['failed'].append((record['row'], record['name'], str(error)))
    return out

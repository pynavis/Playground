# -*- coding: utf-8 -*-
"""Photo Pins and the Photo Browser: site photos pinned to points in the model.

A pin is one record in the per-document RecordStore 'photo-pins' (namo.store, so it
follows Playground's data mode: local, shared or inside the model):

    {'id': 'PH-007', 'point': [x, y, z], 'units': 'Meters', 'caption': 'Riser leak',
     'level': 'Level 2', 'grid': 'C-4', 'item': [entry], 'item_name': 'Pipe 25 mm',
     'camera': {camera dict}, 'photos': [{'file': 'IMG_0412.jpg', 'original': 'D:\\...',
     'taken': '2026-10-01T14:32:10', 'bytes': 2481111}], 'created', 'user'}

Photos are COPIED into the pin's media folder (<store folder>\\_media\\<pin id>\\), so the
pin keeps working when the camera roll moves. In model mode the records travel inside
the NWF/NWD but the media folder stays local (stated in the tool's notes).

Pins are drawn with pynavis.overlay, one item per pin tagged 'playground-photos:<id>': an
outline centred on the point and drawn in all three planes (so it reads from the side, from
the front and in a plan view alike), a small cross on the point itself and the label on
top of it. The overlay draws through geometry, like the native measure lines. Sizes are
real-world (PIN_SIZES, metres) converted to the model's units. hk_photopins redraws the
pins when a document opens and clears them when it closes, if Photo Pins' show setting
is on; the Shift+Click settings and the hook read the same settings file.

Pure half: EXIF DateTimeOriginal from JPEG bytes (no imaging library), pin records,
overlay geometry, filtering and grouping, the HTML photo report.
"""

import datetime
import os
import struct

STORE = 'photo-pins'
TAG_PREFIX = 'playground-photos:'
PREVIEW_TAG = TAG_PREFIX + 'new'
SETTINGS_TOOL = 'playground_photopins'
SETTINGS_DEFAULTS = {'show_pins': True, 'label': 'caption', 'size': 'medium'}
PIN_SIZES = [('small', 'Small', 0.5), ('medium', 'Medium', 1.0), ('large', 'Large', 2.5)]   # pin size in metres; the marker is 0.4 of it across
GO_TO_RADIUS_M = 2.5                     # half the box Go to frames when a pin has no camera
PHOTO_FILTER = 'Photos (*.jpg;*.jpeg;*.png;*.heic;*.tif;*.tiff)|*.jpg;*.jpeg;*.png;*.heic;*.tif;*.tiff|All files (*.*)|*.*'
THUMB_WIDTH = 320
GROUPS = [('level', 'Level'), ('grid', 'Grid'), ('item', 'Linked object'), ('none', 'No grouping')]
EXIF_TAGS = (0x9003, 0x9004, 0x0132)     # DateTimeOriginal, DateTimeDigitized, DateTime
_IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')


# ---- EXIF -----------------------------------------------------------------------------------


def _exif_block(data):
    """The TIFF block inside a JPEG's APP1 Exif segment, or None."""
    if len(data) < 4 or data[0:2] != b'\xff\xd8':
        return None
    pos = 2
    while pos + 4 <= len(data):
        if data[pos:pos + 1] != b'\xff':
            return None
        marker = bytearray(data[pos + 1:pos + 2])[0]
        if marker in (0xD9, 0xDA):                 # end of image, start of scan
            return None
        length = struct.unpack('>H', data[pos + 2:pos + 4])[0]
        body = data[pos + 4:pos + 2 + length]
        if marker == 0xE1 and body[:6] == b'Exif\x00\x00':
            return body[6:]
        pos += 2 + length
    return None


def _ifd_entries(tiff, offset, endian):
    if offset + 2 > len(tiff):
        return []
    count = struct.unpack(endian + 'H', tiff[offset:offset + 2])[0]
    out = []
    for index in range(count):
        start = offset + 2 + index * 12
        if start + 12 > len(tiff):
            break
        tag, kind, number = struct.unpack(endian + 'HHI', tiff[start:start + 8])
        out.append((tag, kind, number, tiff[start + 8:start + 12]))
    return out


def _ascii(tiff, kind, number, raw, endian):
    if kind != 2:
        return None
    if number <= 4:
        text = raw[:number]
    else:
        pointer = struct.unpack(endian + 'I', raw)[0]
        text = tiff[pointer:pointer + number]
    return text.split(b'\x00')[0].decode('ascii', 'replace').strip()


def parse_exif_time(text):
    """'2026:10:01 14:32:10' -> datetime, or None."""
    try:
        return datetime.datetime.strptime(str(text).strip()[:19], '%Y:%m:%d %H:%M:%S')
    except (ValueError, TypeError):
        return None


def exif_datetime(data):
    """When a JPEG was taken (DateTimeOriginal, else DateTimeDigitized, else DateTime),
    from its bytes; None when absent or unreadable. Never raises."""
    try:
        tiff = _exif_block(bytes(data))
        if not tiff or len(tiff) < 8:
            return None
        endian = '<' if tiff[:2] == b'II' else '>' if tiff[:2] == b'MM' else None
        if endian is None:
            return None
        first = struct.unpack(endian + 'I', tiff[4:8])[0]
        found = {}
        entries = _ifd_entries(tiff, first, endian)
        for tag, kind, number, raw in entries:
            if tag == 0x0132:
                found[tag] = _ascii(tiff, kind, number, raw, endian)
            elif tag == 0x8769:
                pointer = struct.unpack(endian + 'I', raw)[0]
                for sub, kind2, number2, raw2 in _ifd_entries(tiff, pointer, endian):
                    if sub in (0x9003, 0x9004):
                        found[sub] = _ascii(tiff, kind2, number2, raw2, endian)
        for tag in EXIF_TAGS:
            value = parse_exif_time(found.get(tag))
            if value is not None:
                return value
    except Exception:
        return None
    return None


def taken_from_file(path, head_bytes=262144):
    """(datetime, 'exif' | 'file') for a photo: EXIF when the first bytes hold it (cheap),
    else the file's modified time."""
    try:
        with open(path, 'rb') as handle:
            head = handle.read(head_bytes)
        when = exif_datetime(head)
        if when is not None:
            return when, 'exif'
    except (IOError, OSError):
        pass
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).replace(microsecond=0), 'file'
    except (IOError, OSError):
        return None, 'file'


# ---- records ----------------------------------------------------------------------------------


def new_pin(point, doc_units, photos, caption, level='', grid='', item=None, item_name='',
            camera=None, user='', now=None):
    """A pin record without an id (RecordStore.add gives it 'PH-001'...)."""
    stamp = (now or datetime.datetime.now()).replace(microsecond=0).isoformat()
    return {'point': [float(point[0]), float(point[1]), float(point[2])], 'units': str(doc_units),
            'caption': str(caption or '').strip(), 'level': level or '', 'grid': grid or '',
            'item': list(item or []), 'item_name': item_name or '', 'camera': camera,
            'photos': list(photos), 'created': stamp, 'user': user or ''}


def photo_entry(file_name, original, taken, size):
    return {'file': file_name, 'original': original, 'taken': taken.isoformat() if taken else '',
            'bytes': int(size or 0)}


def unique_file(name, taken):
    """name, or 'name (2).ext'... among `taken` (case-insensitive)."""
    lowered = set(t.lower() for t in taken)
    if name.lower() not in lowered:
        return name
    stem, ext = os.path.splitext(name)
    n = 2
    while ('%s (%d)%s' % (stem, n, ext)).lower() in lowered:
        n += 1
    return '%s (%d)%s' % (stem, n, ext)


def label_of(pin, mode='caption', limit=28):
    """The overlay label: the caption (cut with ...) or the pin id."""
    text = pin.get('caption') if mode == 'caption' else ''
    text = (text or pin.get('id') or '').strip()
    if len(text) > limit:
        text = text[:limit - 3].rstrip() + '...'
    return text


def pin_segments(point, height):
    """Overlay segments for one pin, `height` tall in model units: the shared Playground pin
    (namo.pins: an octahedron outline centred on the point, which no camera angle
    sees edge on, with a small cross on the point itself), the same glyph Issue Pins draws."""
    from namo import pins
    return pins.segments(point, height)


def pin_label_point(point, height):
    """Where the label is anchored: the top of the marker."""
    from namo import pins
    return pins.top(point, height)


def pin_height(unit_to_m, size='medium'):
    """The pin's height in model units for a size name ('small' 0.5 m, 'medium' 1 m,
    'large' 2.5 m; anything else is medium). unit_to_m is metres per model unit."""
    metres = 1.0
    for key, _label, value in PIN_SIZES:
        if key == size:
            metres = value
    factor = float(unit_to_m or 0.0)
    return metres / factor if factor > 0 else metres


def go_to_box(point, unit_to_m, radius_m=GO_TO_RADIUS_M):
    """The box Go to frames around a pin that has no camera: radius_m metres each way,
    in model units (never a fixed number of model units: a millimetre model would zoom
    into a 2 mm cube)."""
    factor = float(unit_to_m or 0.0)
    r = radius_m / factor if factor > 0 else radius_m
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    return ((x - r, y - r, z - r), (x + r, y + r, z + r))


def tags_to_clear(remembered, live_tags):
    """Every photo-pin overlay tag to remove: the ones this session remembers drawing and
    any still in the overlay under the pin prefix (pins drawn before a Reload dropped the
    session's memory). Sorted, no repeats."""
    found = set(str(t) for t in (remembered or []) if t)
    for tag in live_tags or []:
        if tag and str(tag).startswith(TAG_PREFIX):
            found.add(str(tag))
    return sorted(found)


def group_label(pin, by):
    if by == 'level':
        return pin.get('level') or 'No level'
    if by == 'grid':
        return pin.get('grid') or 'No grid'
    if by == 'item':
        return pin.get('item_name') or 'No linked object'
    return 'All photos'


def search_text(pin):
    parts = [pin.get('id', ''), pin.get('caption', ''), pin.get('level', ''), pin.get('grid', ''),
             pin.get('item_name', ''), pin.get('user', ''), pin.get('created', '')[:10]]
    parts.extend(p.get('file', '') for p in pin.get('photos') or [])
    return ' '.join(str(p) for p in parts).lower()


def filter_pins(pins, query):
    """Pins whose text holds every word of the query."""
    words = str(query or '').lower().split()
    if not words:
        return list(pins)
    return [p for p in pins if all(w in search_text(p) for w in words)]


def group_pins(pins, by):
    """[(label, [pins])] in natural label order; pins newest first inside a group."""
    from namo import naming
    groups = {}
    for pin in pins:
        groups.setdefault(group_label(pin, by), []).append(pin)
    out = []
    for label in sorted(groups, key=naming.natural_key):
        members = sorted(groups[label], key=lambda p: (p.get('created') or '', p.get('id') or ''), reverse=True)
        out.append((label, members))
    return out


def taken_text(photo):
    value = photo.get('taken') or ''
    return value.replace('T', ' ')[:16]


def report_html(pins, title, group_by, thumbs, doc_name='', user=''):
    """The photo report: KPIs, then a section per group with a gallery of every photo
    (thumbs: {(pin id, file): image path or bytes}) and a table of the pins."""
    from namo import htmlreport
    photos = sum(len(p.get('photos') or []) for p in pins)
    report = htmlreport.Report(title, subtitle=doc_name or None,
                               meta=[('Pins', len(pins)), ('Photos', photos), ('By', user or '')])
    report.kpis([('Pins', len(pins), None), ('Photos', photos, None),
                 ('Groups', len(group_pins(pins, group_by)), None)])
    for label, members in group_pins(pins, group_by):
        report.section(label, intro='%d %s' % (len(members), 'pin' if len(members) == 1 else 'pins'))
        items = []
        for pin in members:
            for photo in pin.get('photos') or []:
                image = thumbs.get((pin['id'], photo['file']))
                if image is None:
                    continue
                caption = '%s  %s  %s' % (pin['id'], pin.get('caption') or '', taken_text(photo))
                items.append((image, caption.strip()))
        if items:
            report.gallery(items, columns=3)
        rows = [[p['id'], p.get('caption') or '', p.get('grid') or '', p.get('item_name') or '',
                 len(p.get('photos') or []), (p.get('created') or '')[:16].replace('T', ' ')]
                for p in members]
        report.table(['Pin', 'Caption', 'Grid', 'Linked object', 'Photos', 'Pinned'], rows)
    if not pins:
        report.note('There are no photo pins in this model yet.')
    return report


# ---- API half ---------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def settings():
    from pynavis import settings as _settings
    return _settings.load(SETTINGS_TOOL, SETTINGS_DEFAULTS)


def save_settings(values):
    from pynavis import settings as _settings
    merged = dict(SETTINGS_DEFAULTS)
    merged.update(values)
    _settings.save(SETTINGS_TOOL, merged)


def store(doc=None):
    from namo import store as _store
    return _store.records_for_active_doc(STORE, doc=_doc(doc))


def media_root(records, doc=None):
    """The folder photo copies live under: the store's own folder, or (model mode) the
    local per-document data folder."""
    from namo import fourd_common, paths
    if records.folder:
        return os.path.join(records.folder, '_media')
    return os.path.join(paths.data_root(), 'docs', paths.doc_key(fourd_common.doc_path(doc)),
                        'photo-pins-media')


def media_folder(records, pin_id, doc=None):
    return os.path.join(media_root(records, doc), pin_id)


def photo_path(records, pin, photo, doc=None):
    return os.path.join(media_folder(records, pin['id'], doc), photo['file'])


def location_labels(point, doc=None):
    """(level name, grid intersection name) at a point from the active grid system,
    ('', '') without one."""
    try:
        from pynavis._api import Api
        system = _doc(doc).Grids.ActiveSystem
        if system is None:
            return '', ''
        hit = system.ClosestIntersection(Api.Point3D(point[0], point[1], point[2]))
        if hit is None:
            return '', ''
        level = ''
        try:
            level = str(hit.Level.DisplayName) if hit.Level is not None else ''
        except Exception:
            level = ''
        return level, str(hit.DisplayName or '')
    except Exception:
        return '', ''


def choose_photos(title='Choose photos'):
    """Paths from a multi-select Open dialog, or None on cancel."""
    import clr
    clr.AddReference('PresentationFramework')
    from Microsoft.Win32 import OpenFileDialog
    dialog = OpenFileDialog()
    dialog.Title = title
    dialog.Filter = PHOTO_FILTER
    dialog.Multiselect = True
    if dialog.ShowDialog() != True:      # noqa: E712 (Nullable<bool>)
        return None
    return [str(name) for name in dialog.FileNames]


def add_pin(records, record, sources, doc=None):
    """Copies the photo files and stores the pin (next free 'PH-' id). Returns the stored
    record. IOError when a copy or the record cannot be written."""
    import shutil
    from namo import paths
    saved = records.add(dict(record, photos=[]), prefix='PH-', width=3)
    folder = media_folder(records, saved['id'], doc)
    photos = []
    names = []
    try:
        paths.ensure_dir(folder)
        for source in sources:
            name = unique_file(os.path.basename(source), names)
            target = os.path.join(folder, name)
            try:
                shutil.copyfile(source, target)
            except (IOError, OSError) as error:
                raise IOError('Could not copy %s: %s' % (os.path.basename(source), error))
            names.append(name)
            taken, _how = taken_from_file(source)
            photos.append(photo_entry(name, source, taken, os.path.getsize(target)))
        saved['photos'] = photos
        stored = records.put(saved)
    except Exception:
        try:
            records.delete(saved['id'])
        except Exception:
            pass
        shutil.rmtree(folder, ignore_errors=True)
        raise
    for photo in photos:                 # paid once here, so Photo Browser opens at once
        thumbnail(records, stored, photo, doc)
    return stored


def delete_pin(records, pin, doc=None):
    """Removes the record and its photo copies. Returns True when the record existed."""
    import shutil
    removed = records.delete(pin['id'])
    folder = media_folder(records, pin['id'], doc)
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
    return removed


def thumbnail(records, pin, photo, doc=None):
    """A cached JPEG thumbnail of a photo (made on first use), or None when the photo is
    missing or unreadable."""
    source = photo_path(records, pin, photo, doc)
    if not os.path.exists(source):
        return None
    stem = os.path.splitext(photo['file'])[0]
    target = os.path.join(media_folder(records, pin['id'], doc), '_thumbs', stem + '.jpg')
    try:
        if os.path.exists(target) and os.path.getmtime(target) >= os.path.getmtime(source):
            return target
        if not photo['file'].lower().endswith(_IMAGE_EXT):
            return None
        from namo import images, paths
        paths.ensure_dir(os.path.dirname(target))
        return images.thumbnail(source, target, max_width=THUMB_WIDTH, quality=82)
    except Exception:
        return None


def _unit_to_m(doc=None):
    from namo import units
    try:
        return units.to_meters(1.0, str(_doc(doc).Units))
    except Exception:
        return 1.0


def _live_tags():
    """Tags of the items in the overlay right now ([] when they cannot be read)."""
    try:
        from pynavis import overlay
        return [str(item.Tag) for item in overlay.OverlayRegistry.Items if item.Tag]
    except Exception:
        return []


def _clear_tags():
    from pynavis import overlay
    from namo import session
    holder = session.holder('photopins')
    for tag in tags_to_clear(getattr(holder, 'drawn', None), _live_tags()):
        overlay.clear(tag)
    holder.drawn = []
    return holder


def draw(pins, doc=None, label_mode=None, size=None):
    """Draws every pin (clearing the pins drawn before). Returns how many were drawn; 0
    when the overlay plug-in is not loaded."""
    from pynavis import overlay
    holder = _clear_tags()
    values = settings()
    mode = label_mode or values.get('label', 'caption')
    height = pin_height(_unit_to_m(doc), size or values.get('size', 'medium'))
    count = 0
    for pin in pins:
        point = pin.get('point')
        if not point or len(point) != 3:
            continue
        tag = TAG_PREFIX + str(pin['id'])
        if overlay.add(tag, pin_segments(point, height), label=label_of(pin, mode),
                       label_at=pin_label_point(point, height)):
            count += 1
            holder.drawn.append(tag)
    _overlay_redraw()
    return count


def clear_drawn():
    from pynavis import overlay
    _clear_tags()
    _overlay_redraw()


def preview(point, doc=None):
    """Marks a freshly clicked point with a pin labelled 'New pin' while the photo and
    caption prompts are up, so the place is confirmed before anything is saved. The next
    draw() or clear_drawn() removes it. False when the overlay is not loaded."""
    from pynavis import overlay
    height = pin_height(_unit_to_m(doc), settings().get('size', 'medium'))
    shown = overlay.add(PREVIEW_TAG, pin_segments(point, height), label='New pin',
                        label_at=pin_label_point(point, height))
    _overlay_redraw()
    return shown


def clear_preview():
    from pynavis import overlay
    overlay.clear(PREVIEW_TAG)
    _overlay_redraw()


def refresh(doc=None):
    """Makes the view agree with the settings and the document's pins: drawn when Show
    pins is on, cleared when it is off or there are none. Returns how many are drawn.
    The button, its settings, Photo Browser and the document hook all end here."""
    if not settings().get('show_pins', True):
        clear_drawn()
        return 0
    pins = store(doc).list()
    if not pins:
        clear_drawn()
        return 0
    return draw(pins, doc)


def go_to(pin, doc=None):
    """The pin's camera (or, without one, the point framed along the current view
    direction) and its linked object selected. Returns True when the view moved."""
    from namo import camera, items
    document = _doc(doc)
    moved = False
    cam = pin.get('camera')
    if cam:
        try:
            camera.apply(cam, document)
            moved = True
        except Exception:
            moved = False
    if not moved and pin.get('point'):
        try:
            moved = bool(camera.zoom_to(go_to_box(pin['point'], _unit_to_m(document)), document))
        except Exception:
            moved = False
    if pin.get('item'):
        try:
            found, _missing = items.resolve(pin['item'], document)
            if found:
                items.select(found, doc=document)
        except Exception:
            pass
    return moved


def _overlay_redraw():
    """Redraws the overlay through namo.overlayfix, so labels land on their points."""
    from namo import overlayfix
    return overlayfix.redraw()

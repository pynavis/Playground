# -*- coding: utf-8 -*-
"""namo.photopins: EXIF dates, pin records, overlay geometry, filtering, grouping, report."""
import datetime
import os
import struct

import _compat
from namo import photopins as pp

D = datetime.datetime


def _exif_jpeg(endian='<', original=b'2026:10:01 14:32:10', plain=b'2026:10:02 08:00:00', with_sub=True):
    """A minimal JPEG: SOI, APP1 Exif (IFD0 DateTime + ExifIFD DateTimeOriginal), EOI."""
    e = endian
    ifd0_count = 2 if with_sub else 1
    ifd0_offset = 8
    ifd0_size = 2 + ifd0_count * 12 + 4
    sub_offset = ifd0_offset + ifd0_size
    sub_size = 2 + 1 * 12 + 4
    data_offset = sub_offset + (sub_size if with_sub else 0)
    plain_offset = data_offset
    original_offset = data_offset + 20
    tiff = (b'II' if e == '<' else b'MM') + struct.pack(e + 'HI', 42, ifd0_offset)
    tiff += struct.pack(e + 'H', ifd0_count)
    tiff += struct.pack(e + 'HHII', 0x0132, 2, 20, plain_offset)
    if with_sub:
        tiff += struct.pack(e + 'HHII', 0x8769, 4, 1, sub_offset)
    tiff += struct.pack(e + 'I', 0)
    if with_sub:
        tiff += struct.pack(e + 'H', 1) + struct.pack(e + 'HHII', 0x9003, 2, 20, original_offset)
        tiff += struct.pack(e + 'I', 0)
    tiff += plain + b'\x00' + original + b'\x00'
    body = b'Exif\x00\x00' + tiff
    app0 = b'\xff\xe0' + struct.pack('>H', 16) + b'JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    return b'\xff\xd8' + app0 + b'\xff\xe1' + struct.pack('>H', len(body) + 2) + body + b'\xff\xd9'


def test_exif_little_and_big_endian():
    assert pp.exif_datetime(_exif_jpeg('<')) == D(2026, 10, 1, 14, 32, 10)
    assert pp.exif_datetime(_exif_jpeg('>')) == D(2026, 10, 1, 14, 32, 10)
    assert pp.exif_datetime(_exif_jpeg('<', with_sub=False)) == D(2026, 10, 2, 8, 0, 0)
    assert pp.exif_datetime(_exif_jpeg('<', original=b'0000:00:00 00:00:00')) == D(2026, 10, 2, 8, 0, 0)
    assert pp.exif_datetime(b'not a jpeg') is None
    assert pp.exif_datetime(b'\xff\xd8\xff\xd9') is None
    assert pp.exif_datetime(_exif_jpeg()[:40]) is None
    assert pp.parse_exif_time('2026:01:31 23:59:59') == D(2026, 1, 31, 23, 59, 59)
    assert pp.parse_exif_time(None) is None


def test_exif_against_pillow_written_file():
    _compat.require_cpython('Pillow')
    from PIL import Image
    folder = _compat.tmpdir('photopins_exif')
    path = os.path.join(folder, 'site.jpg')
    image = Image.new('RGB', (64, 48), (200, 120, 40))
    exif = Image.Exif()
    exif[0x0132] = '2026:09:30 07:15:00'
    exif.get_ifd(0x8769)[0x9003] = '2026:09:29 16:45:12'
    image.save(path, exif=exif.tobytes())
    when, how = pp.taken_from_file(path)
    assert (when, how) == (D(2026, 9, 29, 16, 45, 12), 'exif')
    plain = os.path.join(folder, 'plain.png')
    image.save(plain)
    when, how = pp.taken_from_file(plain)
    assert how == 'file' and when is not None


def test_records_and_labels():
    pin = pp.new_pin((1, 2, 3), 'Meters', [pp.photo_entry('a.jpg', 'D:\\a.jpg', D(2026, 1, 2), 10)],
                     '  Riser leak at the slab edge, north core  ', level='Level 2', grid='C-4',
                     item=[{'m': 'x', 'i': 1, 'p': '0/1'}], item_name='Pipe', user='amol',
                     now=D(2026, 10, 5, 9, 30, 15, 99))
    assert pin['point'] == [1.0, 2.0, 3.0] and pin['created'] == '2026-10-05T09:30:15'
    assert pin['photos'][0]['taken'] == '2026-01-02T00:00:00'
    pin['id'] = 'PH-004'
    assert pp.label_of(pin) == 'Riser leak at the slab ed...'
    assert pp.label_of(pin, 'id') == 'PH-004'
    assert pp.unique_file('IMG.JPG', ['img.jpg', 'IMG (2).jpg']) == 'IMG (3).JPG'
    assert pp.unique_file('new.jpg', ['old.jpg']) == 'new.jpg'


def test_pin_segments():
    # Field: a head on a stem a metre above the click read as a pin somewhere else, so
    # the marker is centred on the clicked point itself.
    segs = pp.pin_segments((0, 0, 0), 1.0)
    assert len(segs) == 15                                  # 12 head edges, 3 centre strokes
    assert all(s[2] is False for s in segs)
    head = [p for s in segs[1:13] for p in s[:2]]
    for axis in range(3):
        assert _compat.approx(max(p[axis] for p in head), 0.2)
        assert _compat.approx(min(p[axis] for p in head), -0.2)
    assert pp.pin_label_point((0, 0, 0), 1.0) == (0.0, 0.0, 0.2)


def _extent(segs, axis_a, axis_b):
    """How wide the head (segments 1..12) is on screen axes a and b."""
    points = [p for s in segs[1:13] for p in s[:2]]
    return (max(p[axis_a] for p in points) - min(p[axis_a] for p in points),
            max(p[axis_b] for p in points) - min(p[axis_b] for p in points))


def test_pin_head_reads_from_every_axis():
    # Regression: the head was one diamond in the X/Z plane, a bare line seen along X and
    # nothing but a dash in a plan view. Looking down any axis it must span both screen axes.
    segs = pp.pin_segments((0, 0, 0), 1.0)
    for a, b in ((1, 2), (0, 2), (0, 1)):           # looking along X, along Y, down Z (plan)
        wide, tall = _extent(segs, a, b)
        assert wide > 0.3 and tall > 0.3, (a, b, wide, tall)
        drawn = [s for s in segs[1:13] if abs(s[0][a] - s[1][a]) > 1e-9 and abs(s[0][b] - s[1][b]) > 1e-9]
        assert len(drawn) >= 4                      # a closed outline, not a single stroke


def test_pin_far_from_the_origin_keeps_its_shape():
    # The owner's model sits 1.37 million feet out: the pin there must be the pin at the
    # origin moved, to well under a millimetre.
    far = (1370000.25, -1370000.75, 312.5)
    near = pp.pin_segments((0, 0, 0), 3.28)
    moved = pp.pin_segments(far, 3.28)
    assert len(near) == len(moved)
    for (a0, a1, _), (b0, b1, _) in zip(near, moved):
        for p, q in ((a0, b0), (a1, b1)):
            for axis in range(3):
                assert abs((q[axis] - far[axis]) - p[axis]) < 1e-6
    mid = [(moved[0][0][i] + moved[0][1][i]) / 2.0 for i in range(3)]
    assert all(abs(mid[i] - far[i]) < 1e-6 for i in range(3))     # centred on the clicked point


def test_pin_sizes_are_real_world():
    assert _compat.approx(pp.pin_height(0.3048), 1.0 / 0.3048)          # feet: 1 m is 3.28 ft
    assert _compat.approx(pp.pin_height(0.001, 'small'), 500.0)         # millimetres
    assert _compat.approx(pp.pin_height(1.0, 'large'), 2.5)
    assert _compat.approx(pp.pin_height(1.0, 'no such size'), 1.0)
    assert _compat.approx(pp.pin_height(0), 1.0) and _compat.approx(pp.pin_height(None), 1.0)
    assert sorted(k for k, _l, _m in pp.PIN_SIZES) == ['large', 'medium', 'small']
    assert pp.SETTINGS_DEFAULTS['size'] in [k for k, _l, _m in pp.PIN_SIZES]


def test_go_to_box_is_metres_not_model_units():
    # Regression: Go to framed the point plus or minus ONE model unit, a 2 mm cube in a
    # millimetre model.
    low, high = pp.go_to_box((1000.0, 2000.0, 3000.0), 0.001)
    assert _compat.approx(high[0] - low[0], 5000.0) and _compat.approx(low[2], 500.0)
    low, high = pp.go_to_box((0.0, 0.0, 0.0), 0.3048)
    assert _compat.approx(high[1], 2.5 / 0.3048)


def test_tags_to_clear_finds_pins_the_session_forgot():
    live = ['playground-photos:PH-001', 'playground-cog', 'playground-photos:new', None, 'playground-issues:7']
    assert pp.tags_to_clear(['playground-photos:PH-002'], live) == [
        'playground-photos:PH-001', 'playground-photos:PH-002', 'playground-photos:new']
    assert pp.tags_to_clear(None, []) == []
    assert pp.PREVIEW_TAG.startswith(pp.TAG_PREFIX)


def test_hook_listens_for_open_and_close():
    from namo import hooks
    assert 'hk_photopins' in hooks.handlers_for('doc-opened')
    assert 'hk_photopins' in hooks.handlers_for('doc-closed')


def _pins():
    def pin(id_, caption, level, grid, created, item=''):
        return {'id': id_, 'caption': caption, 'level': level, 'grid': grid, 'created': created,
                'item_name': item, 'photos': [{'file': id_ + '.jpg', 'taken': '2026-10-01T10:00:00'}]}
    return [pin('PH-001', 'Leak', 'Level 2', 'C-4', '2026-10-01T10:00:00', 'Pipe'),
            pin('PH-002', 'Crack in slab', 'Level 10', 'A-1', '2026-10-03T10:00:00'),
            pin('PH-003', 'Leak again', 'Level 2', 'C-5', '2026-10-04T10:00:00'),
            pin('PH-004', 'Roof', '', '', '2026-10-02T10:00:00')]


def test_filter_and_group():
    pins = _pins()
    assert [p['id'] for p in pp.filter_pins(pins, 'leak level')] == ['PH-001', 'PH-003']
    assert [p['id'] for p in pp.filter_pins(pins, 'ph-002.jpg')] == ['PH-002']
    assert len(pp.filter_pins(pins, '  ')) == 4
    groups = pp.group_pins(pins, 'level')
    assert [g for g, _ in groups] == ['Level 2', 'Level 10', 'No level']
    assert [p['id'] for p in groups[0][1]] == ['PH-003', 'PH-001']
    assert [g for g, _ in pp.group_pins(pins, 'item')] == ['No linked object', 'Pipe']
    assert pp.group_pins(pins, 'none')[0][0] == 'All photos'
    assert pp.taken_text({'taken': '2026-10-01T10:00:00'}) == '2026-10-01 10:00'


def test_report_html():
    pins = _pins()
    png_bytes = __import__('namo.png', fromlist=['encode']).encode(2, 2, [0] * 12)
    thumbs = {('PH-001', 'PH-001.jpg'): png_bytes}
    html = pp.report_html(pins, 'Site photos', 'level', thumbs, 'Tower.nwf', 'amol').to_string()
    assert 'Site photos' in html and 'Level 10' in html and 'PH-001  Leak' in html
    assert 'data:image/png;base64' in html
    empty = pp.report_html([], 'Site photos', 'level', {}).to_string()
    assert 'There are no photo pins' in empty


def test_add_and_delete_pin_in_a_record_store():
    from namo import paths, store
    folder = _compat.tmpdir('photopins_store')
    previous = paths.redirect(os.path.join(folder, 'appdata'))
    try:
        records = store.RecordStore(pp.STORE, doc_path=os.path.join(folder, 'Tower.nwf'), mode='local')
        source = os.path.join(folder, 'IMG_0001.jpg')
        with open(source, 'wb') as handle:
            handle.write(_exif_jpeg())
        twin = os.path.join(folder, 'sub')
        os.makedirs(twin)
        second = os.path.join(twin, 'IMG_0001.jpg')
        with open(second, 'wb') as handle:
            handle.write(b'not really a jpeg')
        record = pp.new_pin((1, 2, 3), 'Meters', [], 'Leak', 'Level 2', 'C-4')
        saved = pp.add_pin(records, record, [source, second])
        assert saved['id'] == 'PH-001'
        assert [p['file'] for p in saved['photos']] == ['IMG_0001.jpg', 'IMG_0001 (2).jpg']
        assert saved['photos'][0]['taken'] == '2026-10-01T14:32:10'
        media = pp.media_folder(records, 'PH-001')
        assert sorted(n for n in os.listdir(media) if n != '_thumbs') == ['IMG_0001 (2).jpg', 'IMG_0001.jpg']
        assert records.get('PH-001')['caption'] == 'Leak'
        again = pp.add_pin(records, pp.new_pin((0, 0, 0), 'Meters', [], 'Second'), [source])
        assert again['id'] == 'PH-002'
        _compat.raises(IOError, pp.add_pin, records, pp.new_pin((0, 0, 0), 'Meters', [], 'Bad'),
                       [os.path.join(folder, 'missing.jpg')])
        assert records.ids() == ['PH-001', 'PH-002']
        assert not os.path.isdir(pp.media_folder(records, 'PH-003'))
        assert pp.delete_pin(records, saved)
        assert records.ids() == ['PH-002'] and not os.path.isdir(media)
    finally:
        paths.redirect(previous)

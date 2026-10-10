# -*- coding: utf-8 -*-
"""namo.images: pure sizing/format rules (both engines) and the System.Drawing writers
(IronPython, real GDI+: PNG/JPEG/BMP headers, JPEG quality, thumbnails, disposal)."""
import os

import _compat

from namo import images


def test_format_for():
    assert images.format_for('a/b.PNG') == 'png'
    assert images.format_for('x.jpg') == 'jpeg'
    assert images.format_for('x.jpeg') == 'jpeg'
    assert images.format_for('x.bmp') == 'bmp'
    _compat.raises(ValueError, images.format_for, 'x.gif')
    _compat.raises(ValueError, images.format_for, 'noext')


def test_fit_size():
    assert images.fit_size(1920, 1080, 320) == (320, 180)
    assert images.fit_size(100, 50, 320) == (100, 50)          # never scales up
    assert images.fit_size(1000, 4000, 320, 200) == (50, 200)
    assert images.fit_size(10000, 1, 320) == (320, 1)
    _compat.raises(ValueError, images.fit_size, 0, 10, 5)


def test_quality_and_size_checks():
    assert images.clamp_quality(150) == 100
    assert images.clamp_quality(0) == 1
    assert images.clamp_quality('junk') == 90
    assert images.check_size(640.0, 360) == (640, 360)
    _compat.raises(ValueError, images.check_size, 0, 10)
    _compat.raises(ValueError, images.check_size, 10, images.MAX_SIDE + 1)


def test_styles_table():
    assert images.STYLES['scene'] == 'Scene'
    assert images.STYLES['overlay'] == 'ScenePlusOverlay'


def _bitmap(width=200, height=100):
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Bitmap, Color
    bmp = Bitmap(width, height)
    for x in range(width):
        for y in range(height):
            bmp.SetPixel(x, y, Color.FromArgb(255, (x * 7) % 256, (y * 13) % 256, (x * y) % 256))
    return bmp


def _head(path, n=4):
    with open(path, 'rb') as handle:
        return bytearray(handle.read(n))


def test_save_bitmap_formats_and_disposal():
    _compat.require_ironpython()
    folder = _compat.tmpdir('images_save')
    png = images.save_bitmap(_bitmap(), os.path.join(folder, 'sub', 'a.png'))
    assert _head(png, 4) == bytearray(b'\x89PNG')
    jpg = images.save_bitmap(_bitmap(), os.path.join(folder, 'a.jpg'), quality=80)
    assert _head(jpg, 2) == bytearray(b'\xff\xd8')
    bmp_path = images.save_bitmap(_bitmap(), os.path.join(folder, 'a.bmp'))
    assert _head(bmp_path, 2) == bytearray(b'BM')
    assert not [n for n in os.listdir(folder) if n.endswith('.part')]
    assert images.image_size(png) == (200, 100)
    # disposed: touching the bitmap afterwards fails
    source = _bitmap(20, 10)
    images.save_bitmap(source, os.path.join(folder, 'b.png'))
    failed = False
    try:
        source.Width
    except Exception:
        failed = True
    assert failed
    # overwrite in place
    images.save_bitmap(_bitmap(30, 10), png)
    assert images.image_size(png) == (30, 10)


def test_jpeg_quality_changes_size():
    _compat.require_ironpython()
    folder = _compat.tmpdir('images_quality')
    low = images.save_bitmap(_bitmap(), os.path.join(folder, 'low.jpg'), quality=10)
    high = images.save_bitmap(_bitmap(), os.path.join(folder, 'high.jpg'), quality=100)
    assert os.path.getsize(low) < os.path.getsize(high)


def test_save_bitmap_rejects_bad_extension_and_disposes():
    _compat.require_ironpython()
    folder = _compat.tmpdir('images_bad')
    _compat.raises(ValueError, images.save_bitmap, _bitmap(10, 10), os.path.join(folder, 'x.gif'))
    _compat.raises(ValueError, images.save_bitmap, None, os.path.join(folder, 'x.png'))


def test_thumbnail():
    _compat.require_ironpython()
    folder = _compat.tmpdir('images_thumb')
    src = images.save_bitmap(_bitmap(640, 320), os.path.join(folder, 'big.png'))
    dst = images.thumbnail(src, os.path.join(folder, 'small.jpg'), max_width=160)
    assert images.image_size(dst) == (160, 80)
    tiny = images.save_bitmap(_bitmap(50, 20), os.path.join(folder, 'tiny.png'))
    same = images.thumbnail(tiny, os.path.join(folder, 'tiny2.png'), max_width=160)
    assert images.image_size(same) == (50, 20)
    # the source is not locked
    os.remove(src)
    assert not os.path.exists(src)


def test_api_capture_clash_and_view_keeper():
    _compat.require_ironpython()
    import test_items as nav
    folder = _compat.tmpdir('images_api')
    doc = nav.Document()
    result = nav.ClashResult('Clash1')
    doc.clash_data = nav.FakeTestsData()
    with nav.FakeNav(doc):
        path = images.capture(os.path.join(folder, 'view.png'), 320, 200, style='overlay', sectioning=False)
        assert images.image_size(path) == (320, 200)
        assert doc.images[-1] == ('ScenePlusOverlay', 320, 200, False)
        _compat.raises(ValueError, images.capture, os.path.join(folder, 'view.tif'))
        _compat.raises(ValueError, images.style_enum, 'sepia')
        saved = nav.SavedViewpoint(nav.Viewpoint())
        saved.DisplayName = 'Front'
        before = nav.SavedViewpoint(nav.Viewpoint())
        before.DisplayName = 'Start'
        doc.SavedViewpoints.CurrentSavedViewpoint = before
        doc.CurrentViewpoint.vp.Position = nav.Point3D(7, 7, 7)
        with images.ViewKeeper():
            images.capture_saved(saved, os.path.join(folder, 'front.jpg'), width=100, height=50, quality=70)
            assert doc.SavedViewpoints.CurrentSavedViewpoint is saved
            doc.CurrentViewpoint.vp.Position = nav.Point3D(0, 0, 0)
        assert doc.SavedViewpoints.CurrentSavedViewpoint is before
        assert doc.CurrentViewpoint.vp.Position.t() == (7, 7, 7)
        clash_path = images.clash(result, os.path.join(folder, 'clash.png'), 64, 36)
        assert images.image_size(clash_path) == (64, 36)
        assert doc.clash_data.calls[-1] == ('image', 'Clash1', 'Scene')

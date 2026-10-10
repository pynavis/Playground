# -*- coding: utf-8 -*-
"""namo.rep_batch_pdf: the contract, the page plan and layout maths, and a whole
handout built from JPEGs (structure checked; pypdf under CPython when installed)."""
import base64
import os
import re

import _compat
from _compat import approx

from namo import rep_batch_pdf, reports

JPEG = base64.b64decode(
    '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLikxMC4pLSwzOko+MzZGNywtQFdBRkxOUlNSMj5a'
    'YVpQYEpRUk//2wBDAQ4ODhMREyYVFSZPNS01T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0//wAAR'
    'CAASACADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEG'
    'E1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWG'
    'h4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEB'
    'AQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk'
    'NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0'
    'tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDOooorzD6kKKKKACiiigAooooA/9k=')


def test_contract():
    config = rep_batch_pdf.default_config()
    assert config['folder'] == '' and config['name_template'] == rep_batch_pdf.NAME_TEMPLATE
    assert config['views']['mode'] == 'all' and config['paper'] == 'A4'
    assert rep_batch_pdf.describe(config) == 'All viewpoints, A4 landscape, JPEG 85%'
    assert rep_batch_pdf.TITLE == reports.title_of('batch_pdf')
    assert reports.module_exists('batch_pdf')


def test_page_box_and_pixels():
    width, height, box = rep_batch_pdf.page_box('A4', comments=True)
    assert (width, height) == (297.0, 210.0)
    x, y, w, h = box
    assert x == 12.0 and approx(y, 27.0) and approx(w, 273.0) and approx(h, 210 - 12 - 3 - 20 - 27)
    _w, _h, plain = rep_batch_pdf.page_box('A4', comments=False)
    assert plain[3] > h
    px = rep_batch_pdf.image_pixels(w, h, 150)
    assert px[0] == int(round(w / 25.4 * 150)) and approx(float(px[0]) / px[1], w / h, 0.01)
    capped = rep_batch_pdf.image_pixels(800, 400, 300, max_side=2000)
    assert capped == (2000, 1000)


def test_page_plan():
    per = rep_batch_pdf.contents_rows_per_page('A4')
    assert per >= 20
    assert rep_batch_pdf.plan_pages(10, True, True, 30) == (1, 3)
    assert rep_batch_pdf.plan_pages(61, True, True, 30) == (3, 5)
    assert rep_batch_pdf.plan_pages(5, False, False, 30) == (0, 1)
    assert rep_batch_pdf.plan_pages(0, True, True, 30) == (0, 2)


def test_footer_and_comments_text():
    dot = rep_batch_pdf.DOT
    template = rep_batch_pdf.default_config()['footer']
    assert rep_batch_pdf.footer_text(template, {'project': 'Tower', 'file': 'A', 'date': 'D'}) == u'Tower %s A %s D' % (dot, dot)
    assert rep_batch_pdf.footer_text(template, {'project': '', 'file': 'A', 'date': 'D'}) == u'A %s D' % dot
    assert rep_batch_pdf.footer_text('{project}   {file}', {'project': 'Tower', 'file': 'A'}) == 'Tower A'
    text = rep_batch_pdf.comment_text([{'body': 'Fix  the\nduct', 'author': 'Ann'}, {'body': ' '}, {'body': 'x'}])
    assert text == 'Ann: Fix the duct\nx'


def _pages(data):
    return len(re.findall(rb'/Type\s*/Page[^s]', data))


def test_build_writes_a_handout():
    folder = _compat.tmpdir('batch_pdf_build')
    image = os.path.join(folder, 'v1.jpg')
    with open(image, 'wb') as handle:
        handle.write(JPEG)
    views = [{'name': 'Corridor', 'folder': 'Level 2', 'image': image,
              'comments': [{'body': 'Duct clashes with the beam', 'author': 'Ann'}]},
             {'name': 'Plant room', 'folder': '', 'image': None, 'error': 'render failed', 'comments': []},
             {'name': 'Roof', 'folder': 'Roof', 'image': image, 'comments': []}]
    values = {'title': '', 'file': 'Tower', 'project': 'Tower block', 'project_number': 'P-101',
              'company': 'ACME', 'user': 'Ann', 'date': '2026-10-05'}
    config = rep_batch_pdf.default_config()
    path = rep_batch_pdf.build(os.path.join(folder, 'out.pdf'), views, config, values)
    with open(path, 'rb') as handle:
        data = handle.read()
    assert data.startswith(b'%PDF') and _pages(data) == 5          # title, contents, three views
    assert data.count(b'/DCTDecode') == 1                             # the same JPEG stored once
    no_extras = dict(config, title_page=False, contents=False, comments=False)
    path2 = rep_batch_pdf.build(os.path.join(folder, 'plain.pdf'), views, no_extras, values)
    with open(path2, 'rb') as handle:
        assert _pages(handle.read()) == 3
    if not _compat.IRONPYTHON:
        try:
            import pypdf
        except ImportError:
            return
        reader = pypdf.PdfReader(path, strict=True)
        assert len(reader.pages) == 5
        text = reader.pages[0].extract_text()
        assert 'Tower' in text and 'Tower block' in text
        assert 'Contents' in reader.pages[1].extract_text()
        assert 'Ann: Duct clashes with the beam' in reader.pages[2].extract_text()
        assert 'No image: render failed' in reader.pages[3].extract_text()


def test_option_fields_defaults_are_option_values():
    import test_vp_common as vpfake
    from namo import ui
    cfg = rep_batch_pdf.default_config()
    cfg.update({'open': True, 'hand_order': True, 'paper': 'B5', 'dpi': 220})
    fields = rep_batch_pdf.option_fields(cfg)
    vpfake.check_defaults(fields)
    by_key = dict((f['key'], f) for f in ui.normalize_fields(fields))
    assert by_key['paper']['default'] == 'A4' and by_key['dpi']['default'] == 220
    assert by_key['hand_order']['default'] is True and by_key['footer']['default'] == cfg['footer']

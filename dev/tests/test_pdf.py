# -*- coding: utf-8 -*-
"""namo.pdf: metrics, encoding, and a parse of our own output (xref offsets, stream
lengths, page order, images) on both engines; pypdf / PyMuPDF cross-checks on CPython."""
import datetime
import io
import os
import re
import zlib

import _compat
from _compat import approx, raises, tmpdir

from namo import pdf, png

CREATED = datetime.datetime(2026, 10, 5, 9, 30, 0)


def _rgb_png(w=8, h=4):
    return png.encode(w, h, [(x * 30) % 256 for x in range(w * h * 3)], 'RGB')


def _rgba_png(w=6, h=3, opaque=False):
    px = []
    for i in range(w * h):
        px.extend([i * 10 % 256, 100, 200, 255 if opaque else (i * 37) % 256])
    return png.encode(w, h, px, 'RGBA')


def _fake_jpeg(w=40, h=30, components=3):
    """Header-only JPEG: enough for the size reader; viewers would not decode it."""
    import struct
    sof = b'\xff\xc0' + struct.pack('>HBHHB', 8 + 3 * components, 8, h, w, components) + b'\x00' * (3 * components)
    return b'\xff\xd8' + sof + b'\xff\xda\x00\x02\xff\xd9'


# --- a small PDF parser for our own output --------------------------------------------

def _parse(data):
    assert data.startswith(b'%PDF-1.4\n')
    assert data.endswith(b'%%EOF\n')
    sx = data.rindex(b'startxref')
    xref_pos = int(data[sx + len(b'startxref'):].split()[0])
    assert data[xref_pos:xref_pos + 5] == b'xref\n'
    head_end = data.index(b'\n', xref_pos + 5)
    first, count = [int(v) for v in data[xref_pos + 5:head_end].split()]
    assert first == 0
    table_start = head_end + 1
    entries = []
    for i in range(count):
        entry = data[table_start + 20 * i:table_start + 20 * (i + 1)]
        assert len(entry) == 20 and entry.endswith(b'\r\n'), entry
        entries.append((int(entry[:10]), int(entry[11:16]), entry[17:18]))
    assert entries[0] == (0, 65535, b'f')
    trailer = data[table_start + 20 * count:sx].decode('latin-1')
    assert ('/Size %d' % count) in trailer
    objects = {}
    for num in range(1, count):
        offset, gen, kind = entries[num]
        assert kind == b'n' and gen == 0
        prefix = ('%d 0 obj\n' % num).encode('ascii')
        assert data[offset:offset + len(prefix)] == prefix, (num, data[offset:offset + 20])
        start = offset + len(prefix)
        marker = data.find(b'stream\n', start)
        end_obj = data.find(b'endobj', start)
        if marker != -1 and marker < end_obj:
            head = data[start:marker].decode('latin-1')
            length = int(re.search(r'/Length (\d+)', head).group(1))
            stream = data[marker + 7:marker + 7 + length]
            assert data[marker + 7 + length:marker + 7 + length + 18] == b'\nendstream\nendobj\n'
            objects[num] = (head, stream)
        else:
            objects[num] = (data[start:end_obj].decode('latin-1'), None)
    return objects, trailer


def _content(objects, page_head):
    num = int(re.search(r'/Contents (\d+) 0 R', page_head).group(1))
    head, stream = objects[num]
    return (zlib.decompress(stream) if '/FlateDecode' in head else stream).decode('latin-1')


def _pages(objects):
    kids = re.search(r'/Kids \[([^\]]*)\]', objects[2][0]).group(1)
    return [int(n) for n in re.findall(r'(\d+) 0 R', kids)]


def _sample():
    doc = pdf.Document(size='A4', landscape=True, margin_mm=12, title='Report (one)', author=u'Am\u00f6l',
                       created=CREATED)
    first = doc.page()
    first.text(first.left, first.top, 'First page', size=18, bold=True)
    first.wrap(first.left, 30, 60, 'word ' * 40, size=10)
    first.line(12, 50, 100, 50, color=(224, 224, 224))
    first.rect(12, 60, 50, 10, stroke=None, fill='F2F2F2')
    first.image(_rgb_png(), 120, 20, 40)
    first.image(_rgba_png(), 170, 20, 30)
    first.image(_fake_jpeg(), 120, 60, 40)
    first.link(12, 80, 40, 6, 'https://example.com/x y')
    second = doc.page(landscape=False)
    second.text(10, 10, 'Second page')
    second.image(_rgb_png(), 10, 20, 40)             # same bytes: one XObject
    third = doc.page()
    third.text(10, 10, 'Third page')
    doc.page_numbers()
    return doc


# --- metrics and encoding (both engines) ------------------------------------------------

def test_text_width_uses_afm_metrics():
    expected = (722 + 556 + 222 + 222 + 556) / 1000.0 * 10 / pdf.MM
    assert approx(pdf.text_width('Hello', 10), expected)
    bold = (722 + 556 + 278 + 278 + 611) / 1000.0 * 10 / pdf.MM
    assert approx(pdf.text_width('Hello', 10, bold=True), bold)
    assert approx(pdf.text_width(u'\u20ac', 10), 556 / 100.0 / pdf.MM)          # Euro -> 0x80
    assert approx(pdf.text_width(u'\u4e2d', 10), pdf.text_width('?', 10))       # outside cp1252
    assert approx(pdf.text_width('a\tb', 10), pdf.text_width('a b', 10))
    assert pdf.text_width('', 10) == 0


def test_codes_and_literals():
    assert pdf._codes(u'A\u00e9\u2014\u2019\u4e2d') == [0x41, 0xE9, 0x97, 0x92, 0x3F]
    assert pdf._codes(u'\U0001F600') == [0x3F]                                  # one '?' on both engines
    assert pdf._literal(u'a(b)c\\d') == u'(a\\(b\\)c\\\\d)'
    assert pdf._literal(u'caf\u00e9 \u20ac') == u'(caf\\351 \\200)'
    assert pdf._info_string('Plain (x)') == u'(Plain \\(x\\))'
    assert pdf._info_string(u'\u00e9') == u'<FEFF00E9>'
    assert pdf._info_string(u'\U0001F600') == u'<FEFFD83DDE00>'
    assert pdf._uri(r'C:\A dir\x.pdf') == u'file:///C:/A%20dir/x.pdf'
    assert pdf._uri(u'https://x.com/\u00e9') == u'https://x.com/%C3%A9'
    assert pdf._n(1.0) == u'1' and pdf._n(-0.0001) == u'0' and pdf._n(2.5) == u'2.5'


def test_fit_and_wrap():
    text = 'The quick brown fox jumps over the lazy dog'
    assert pdf.fit_text(text, 500, 10) == text
    cut = pdf.fit_text(text, 30, 10)
    assert cut.endswith(u'\u2026') and pdf.text_width(cut, 10) <= 30 + 1e-9
    lines = pdf.wrap_lines(text + '\n\nSecond paragraph ' + 'z' * 80, 40, 10)
    assert all(pdf.text_width(l, 10) <= 40 + 1e-9 for l in lines)
    assert '' in lines                                                          # blank line kept
    assert ' '.join(l for l in lines if l and 'zz' not in l).startswith('The quick')
    assert ''.join(l for l in lines if set(l) == set('z')) == 'z' * 80          # long word split
    assert pdf.wrap_lines('', 40) == ['']
    assert approx(pdf.line_height(10, 1.3), 13 / pdf.MM)


def test_page_sizes_and_colours():
    assert pdf.page_size('A4', True) == (297.0, 210.0)
    assert pdf.page_size('letter', False) == (215.9, 279.4)
    assert pdf.page_size((100, 50)) == (100.0, 50.0)
    raises(ValueError, pdf.page_size, 'B7')
    assert pdf._rgb((255, 0, 0)) == (1.0, 0.0, 0.0)
    assert pdf._rgb((0.5, 0.5, 0.5)) == (0.5, 0.5, 0.5)
    assert pdf._rgb('#000000') == (0.0, 0.0, 0.0)
    assert pdf._rgb(None) is None
    raises(ValueError, pdf._rgb, 'red')


# --- structure of our own output (both engines) -----------------------------------------

def test_xref_offsets_streams_and_trailer():
    objects, trailer = _parse(_sample().to_bytes())
    assert '/Root 1 0 R' in trailer and '/Info 5 0 R' in trailer and '/ID [<' in trailer
    assert objects[1][0].strip().startswith('<< /Type /Catalog /Pages 2 0 R')
    assert '/BaseFont /Helvetica ' in objects[3][0] and '/WinAnsiEncoding' in objects[3][0]
    assert '/BaseFont /Helvetica-Bold' in objects[4][0]
    info = objects[5][0]
    assert '/Title (Report \\(one\\))' in info and '/Author <FEFF0041006D00F6006C>' in info
    assert '/CreationDate (D:20261005093000)' in info


def test_pages_in_order_with_sizes_and_numbers():
    objects, _ = _parse(_sample().to_bytes())
    kids = _pages(objects)
    assert len(kids) == 3 and '/Count 3' in objects[2][0]
    texts = [_content(objects, objects[k][0]) for k in kids]
    assert '(First page) Tj' in texts[0] and '(Second page) Tj' in texts[1] and '(Third page) Tj' in texts[2]
    for index, text in enumerate(texts):
        assert '(Page %d of 3) Tj' % (index + 1) in text
    assert '/MediaBox [0 0 841.89 595.276]' in objects[kids[0]][0]
    assert '/MediaBox [0 0 595.276 841.89]' in objects[kids[1]][0]
    assert '/F2 18 Tf' in texts[0]                       # bold title


def test_text_placement_is_top_of_caps():
    doc = pdf.Document(size=(100, 100), margin_mm=10, compress=False, created=CREATED)
    page = doc.page()
    width = page.text(50, 20, 'Right', size=10, align='right')
    page.text(50, 30, 'Mid', size=10, align='center')
    objects, _ = _parse(doc.to_bytes())
    text = _content(objects, objects[_pages(objects)[0]][0])
    match = re.search(r'1 0 0 1 ([0-9.]+) ([0-9.]+) Tm \(Right\) Tj', text)
    x, y = float(match.group(1)), float(match.group(2))
    assert approx(x, (50 - width) * pdf.MM, 1e-3)
    assert approx(y, (100 - 20 - 10 * pdf.ASCENT / pdf.MM) * pdf.MM, 1e-3)
    match = re.search(r'1 0 0 1 ([0-9.]+) [0-9.]+ Tm \(Mid\) Tj', text)
    assert approx(float(match.group(1)), (50 - pdf.text_width('Mid', 10) / 2) * pdf.MM, 1e-3)


def test_wrap_returns_next_line_position():
    page = pdf.Document(created=CREATED).page()
    y = page.wrap(10, 20, 50, 'one two three four five six seven eight nine ten', size=10, leading=1.5)
    lines = pdf.wrap_lines('one two three four five six seven eight nine ten', 50, 10)
    assert approx(y, 20 + len(lines) * pdf.line_height(10, 1.5))
    y2 = page.wrap(10, 20, 20, 'many words ' * 30, size=10, max_lines=2)
    assert approx(y2, 20 + 2 * pdf.line_height(10))
    assert page._ops[-1].endswith(u'\\205) Tj ET')        # ellipsis (0x85) ends the last line
    count = len(page._ops)
    assert page.wrap(10, 33, 50, '') == 33 and page.wrap(10, 33, 50, None) == 33
    assert page.wrap(10, 33, 50, '  \n ') == 33 and len(page._ops) == count


def test_images_passthrough_softmask_and_dedupe():
    rgb = _rgb_png()
    jpeg = _fake_jpeg()
    objects, _ = _parse(_sample().to_bytes())
    images = dict((num, obj) for num, obj in objects.items() if '/Subtype /Image' in obj[0])
    assert len(images) == 4                              # RGB png, RGBA png + its mask, jpeg
    jpeg_obj = [o for o in images.values() if '/DCTDecode' in o[0]][0]
    assert jpeg_obj[1] == jpeg and '/Width 40 /Height 30' in jpeg_obj[0]
    png_obj = [o for o in images.values() if '/Predictor 15' in o[0]][0]
    assert png_obj[1] == png.idat_stream(rgb) and '/Colors 3 /BitsPerComponent 8 /Columns 8' in png_obj[0]
    masked = [o for o in images.values() if '/SMask' in o[0]][0]
    mask_num = int(re.search(r'/SMask (\d+) 0 R', masked[0]).group(1))
    _w, _h, _mode, pixels = png.decode(_rgba_png())
    assert zlib.decompress(masked[1]) == bytes(bytearray(b for i, b in enumerate(bytearray(pixels)) if i % 4 != 3))
    assert zlib.decompress(objects[mask_num][1]) == bytes(bytearray(pixels)[3::4])
    kids = _pages(objects)
    assert '/XObject << /Im1 ' in objects[kids[1]][0]    # page 2 reuses the first image


def test_opaque_rgba_has_no_mask_and_errors():
    doc = pdf.Document(created=CREATED)
    page = doc.page()
    drawn = page.image(_rgba_png(opaque=True), 10, 10, 30, 30, fit=True)
    assert approx(drawn[2], 30) and approx(drawn[3], 15) and approx(drawn[1], 17.5)
    assert approx(page.image(_rgb_png(8, 4), 0, 0, h_mm=10)[2], 20)
    objects, _ = _parse(doc.to_bytes())
    assert not any('/SMask' in o[0] for o in objects.values())
    raises(ValueError, page.image, b'GIF89a' + b'\x00' * 20, 0, 0, 10)
    raises(ValueError, page.image, _rgb_png(), 0, 0)
    raises(ValueError, page.text, 0, 0, 'x', align='justify')


def test_links_annotations():
    objects, _ = _parse(_sample().to_bytes())
    first = objects[_pages(objects)[0]][0]
    annot = int(re.search(r'/Annots \[(\d+) 0 R\]', first).group(1))
    assert '/URI (https://example.com/x%20y)' in objects[annot][0]
    assert '/Subtype /Link' in objects[annot][0]


def test_empty_document_and_determinism():
    objects, _ = _parse(pdf.Document(created=CREATED).to_bytes())
    assert len(_pages(objects)) == 1
    assert _sample().to_bytes() == _sample().to_bytes()


def test_save_atomic():
    folder = tmpdir('pdf_save')
    path = os.path.join(folder, 'sub', 'out.pdf')
    assert _sample().save(path) == path
    assert not os.path.exists(path + '.tmp')
    with open(path, 'rb') as handle:
        _parse(handle.read())


# --- third-party readers (CPython) ------------------------------------------------------

def _need(module):
    _compat.require_cpython('%s runs under CPython' % module)
    try:
        return __import__(module)
    except ImportError:
        raise _compat.SkipTest('%s is not installed' % module)


def _real_jpeg(w=64, h=32, mode='RGB'):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new(mode, (w, h), (200, 60, 40) if mode == 'RGB' else 128).save(buffer, 'JPEG')
    return buffer.getvalue()


def _readable_doc():
    doc = pdf.Document(title=u'Caf\u00e9 report', author='Tester', created=CREATED)
    page = doc.page()
    page.text(page.left, page.top, u'Caf\u00e9 \u20ac (12)', size=14, bold=True)
    page.text(page.right, page.top, 'Right edge', size=10, align='right')
    page.wrap(page.left, 40, 80, 'alpha beta gamma delta ' * 10, size=10)
    page.image(_real_jpeg(), page.left, 100, 40)
    page.link(page.left, 160, 30, 6, 'https://example.com/')
    second = doc.page(landscape=False)
    second.text(10, 10, 'Portrait page')
    return doc


def test_pypdf_reads_it_strictly():
    pypdf = _need('pypdf')
    reader = pypdf.PdfReader(io.BytesIO(_readable_doc().to_bytes()), strict=True)
    assert len(reader.pages) == 2
    assert reader.metadata.title == u'Caf\u00e9 report' and reader.metadata.author == 'Tester'
    text = reader.pages[0].extract_text()
    assert u'Caf\u00e9 \u20ac (12)' in text and 'Right edge' in text and 'alpha beta' in text
    assert 'Portrait page' in reader.pages[1].extract_text()
    assert float(reader.pages[1].mediabox.width) < float(reader.pages[1].mediabox.height)


def test_pymupdf_layout_and_images():
    fitz = _need('fitz')
    from PIL import Image
    doc = _readable_doc()
    rgb = _rgb_png(32, 16)
    rgba = _rgba_png(12, 6)
    pal_buffer = io.BytesIO()
    Image.frombytes('RGB', (20, 10), bytes(bytearray((i * 7) % 256 for i in range(600)))).quantize(5).save(
        pal_buffer, 'PNG')
    pal = pal_buffer.getvalue()
    page = doc.pages[0]
    page.image(rgb, 100, 100, 30)
    page.image(rgba, 140, 100, 30)
    page.image(pal, 180, 100, 30)
    reader = fitz.open(stream=doc.to_bytes(), filetype='pdf')
    assert reader.page_count == 2 and not reader.needs_pass
    first = reader[0]
    # right-aligned text ends at the right margin: our AFM widths match the viewer's font
    words = [w for w in first.get_text('words') if w[4] == 'edge']
    assert abs(words[0][2] - doc.pages[0].right * pdf.MM) < 1.0
    # every embedded PNG decodes to exactly the source pixels
    expected = {(32, 16): png.decode(rgb)[3], (20, 10): Image.open(io.BytesIO(pal)).convert('RGB').tobytes()}
    _w, _h, _m, rgba_px = png.decode(rgba)
    expected[(12, 6)] = bytes(bytearray(b for i, b in enumerate(bytearray(rgba_px)) if i % 4 != 3))
    seen = 0
    for info in first.get_images(full=True):
        pix = fitz.Pixmap(reader, info[0])
        key = (pix.width, pix.height)
        if key in expected:
            samples = pix.samples if pix.alpha == 0 else bytes(
                bytearray(b for i, b in enumerate(bytearray(pix.samples)) if i % 4 != 3))
            assert samples == expected[key], key
            seen += 1
    assert seen == 3
    links = first.get_links()
    assert links and links[0]['uri'] == 'https://example.com/'


# --- same bytes on both engines ---------------------------------------------------------

GOLDEN_PDF = '94ab2dccdb3078899a7bf72ef97ca18e'


def test_golden_digest_matches_on_both_engines():
    """An uncompressed PDF hashes the same under CPython and IronPython (number
    formatting, metrics, offsets). If you change the output on purpose, update
    GOLDEN_PDF after checking both engines agree."""
    import hashlib
    doc = pdf.Document(title=u'Golden é', author='Both', created=CREATED, compress=False)
    page = doc.page()
    page.text(page.left, page.top, 'Golden page', size=17.5, bold=True)
    page.text(page.right, page.top, u'Right €', size=9, align='right', color=(0.2, 0.4, 0.6))
    page.wrap(page.left, 30, 77.7, 'lorem ipsum dolor sit amet ' * 12, size=9.5, leading=1.25)
    page.image(_fake_jpeg(), 100, 50, 33.3)
    page.line(10, 10, 200, 10, width_mm=0.15, dash=(1, 0.5))
    page.rect(10, 120, 50, 7, stroke='A6A6A6', fill=(242, 242, 242))
    page.link(10, 120, 50, 7, 'https://example.com/q?a=1')
    doc.page(landscape=False).text(10, 10, 'Two', align='center')
    doc.page_numbers()
    assert hashlib.md5(doc.to_bytes()).hexdigest() == GOLDEN_PDF

# -*- coding: utf-8 -*-
"""namo.png: encoder, decoder (every filter, bit depth, palette, tRNS, Adam7) and sniffers.

Pure tests run on both engines; the Pillow cross-checks run under CPython only.
"""
import binascii
import io
import os
import struct
import zlib

import _compat
from _compat import raises, tmpdir

from namo import png

# Reference files written by Pillow (CPython) and embedded so IronPython decodes them too.
PAL_TRNS = binascii.unhexlify(
    '89504e470d0a1a0a0000000d4948445200000003000000020803000000aaaa962800000300504c5445'
    '0a141ec8643200ff00' + '00' * 759 + '21cd58430000000274524e53ff00e5b7304a00000010'
    '49444154789c63606064626062640000002000071d2b70a00000000049454e44ae426082')
G16 = binascii.unhexlify(
    '89504e470d0a1a0a0000000d4948445200000002000000021000000000074d8ebb0000001249444154'
    '789c636060f8ff9f49c864cd3900101103c1f84961630000000049454e44ae426082')
BIT1 = binascii.unhexlify(
    '89504e470d0a1a0a0000000d494844520000000a000000020100000000491a707d0000000e49444154'
    '789c635c25c6c0e0000003f60102bae7c6080000000049454e44ae426082')
RGBA_OPT = binascii.unhexlify(
    '89504e470d0a1a0a0000000d4948445200000004000000030806000000b4f4aec60000002449444154'
    '78da63646060f86fc3c0f006865918521818181834e018492080818121800100da9b0689f0a805ed00'
    '00000049454e44ae426082')
RGBA_OPT_PIXELS = [(x * 60, y * 100, (x * y * 40) % 256, 255 - x * 20)
                   for y in range(3) for x in range(4)]


def _pil():
    _compat.require_cpython('Pillow cross-check runs under CPython')
    try:
        from PIL import Image
    except ImportError:
        raise _compat.SkipTest('Pillow is not installed')
    return Image


def _flat(pixel_tuples):
    out = []
    for px in pixel_tuples:
        out.extend(px)
    return bytes(bytearray(out))


# --- independent test encoder: applies every filter type and optional Adam7 -------------

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _filter_rows(rows, bpp, first_filter):
    out = bytearray()
    prev = bytearray(len(rows[0])) if rows else bytearray()
    for index, row in enumerate(rows):
        ftype = (first_filter + index) % 5
        row = bytearray(row)
        enc = bytearray(len(row))
        for i in range(len(row)):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            pred = (0, a, b, (a + b) // 2, _paeth(a, b, c))[ftype]
            enc[i] = (row[i] - pred) & 0xFF
        out.append(ftype)
        out.extend(enc)
        prev = row
    return out


def _chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xFFFFFFFF))


def _make_png(width, height, ctype, channels, pixels, interlace=False):
    """8-bit PNG with rows cycling through filters 0..4 (and Adam7 when asked)."""
    stride = width * channels
    raw = bytearray()
    if not interlace:
        rows = [pixels[y * stride:(y + 1) * stride] for y in range(height)]
        raw = _filter_rows(rows, channels, 0)
    else:
        passes = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                  (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
        for n, (xs, ys, dx, dy) in enumerate(passes):
            rows = []
            for y in range(ys, height, dy):
                row = bytearray()
                for x in range(xs, width, dx):
                    row.extend(pixels[(y * width + x) * channels:(y * width + x + 1) * channels])
                if row:
                    rows.append(row)
            if rows:
                raw.extend(_filter_rows(rows, channels, n))
    ihdr = struct.pack('>IIBBBBB', width, height, 8, ctype, 0, 0, 1 if interlace else 0)
    return (png.SIGNATURE + _chunk(b'IHDR', ihdr) + _chunk(b'IDAT', zlib.compress(bytes(raw)))
            + _chunk(b'IEND', b''))


def _pattern(width, height, channels):
    return bytes(bytearray(((x * 37 + y * 91 + c * 53 + (x * y) % 7) & 0xFF)
                           for y in range(height) for x in range(width) for c in range(channels)))


# --- encoding ----------------------------------------------------------------------------

def test_encode_roundtrip_all_layouts():
    pixels = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (10, 20, 30)]
    expected = _flat(pixels)
    layouts = [
        expected,                                   # flat bytes
        bytearray(expected),                        # flat bytearray
        list(bytearray(expected)),                  # flat list of ints
        pixels,                                     # flat list of pixel tuples
        [list(bytearray(expected[:6])), list(bytearray(expected[6:]))],   # rows of samples
        [pixels[:2], pixels[2:]],                   # rows of pixel tuples
    ]
    for layout in layouts:
        data = png.encode(2, 2, layout, 'RGB')
        assert data.startswith(png.SIGNATURE)
        w, h, mode, out = png.decode(data)
        assert (w, h, mode) == (2, 2, 'RGB')
        assert out == expected


def test_encode_every_mode_roundtrips():
    for mode, channels in (('L', 1), ('LA', 2), ('RGB', 3), ('RGBA', 4)):
        pixels = _pattern(5, 3, channels)
        w, h, out_mode, out = png.decode(png.encode(5, 3, pixels, mode))
        assert (w, h, out_mode) == (5, 3, mode)
        assert out == pixels


def test_encode_one_bit():
    values = [0, 1, 255, 0, 0, 7, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 9]   # 10x2
    data = png.encode(10, 2, values, '1')
    head = png.info(data)
    assert head['bit_depth'] == 1 and head['color_type'] == 0
    w, h, mode, out = png.decode(data)
    assert mode == 'L'
    assert list(bytearray(out)) == [255 if v else 0 for v in values]


def test_encode_errors():
    raises(ValueError, png.encode, 2, 2, b'\x00' * 11, 'RGB')
    raises(ValueError, png.encode, 1, 1, [0, 0, 0], 'CMYK')
    raises(ValueError, png.encode, 1, 1, [300, 0, 0], 'RGB')
    raises(ValueError, png.encode, 0, 1, [], 'L')
    raises(TypeError, png.encode, 1, 1, 'abc', 'RGB')


def test_write_and_read_file():
    folder = tmpdir('png_write')
    path = os.path.join(folder, 'tiny.png')
    assert png.write(path, 3, 1, [1, 2, 3, 4, 5, 6, 7, 8, 9]) == path
    assert png.read(path) == (3, 1, 'RGB', bytes(bytearray(range(1, 10))))


# --- decoding ----------------------------------------------------------------------------

def test_decode_every_filter_type():
    for ctype, channels, mode in ((0, 1, 'L'), (2, 3, 'RGB'), (4, 2, 'LA'), (6, 4, 'RGBA')):
        pixels = _pattern(9, 7, channels)
        data = _make_png(9, 7, ctype, channels, pixels)
        assert png.decode(data) == (9, 7, mode, pixels)


def test_decode_adam7_interlaced():
    for width, height in ((9, 7), (1, 1), (3, 10), (16, 16)):
        pixels = _pattern(width, height, 3)
        data = _make_png(width, height, 2, 3, pixels, interlace=True)
        assert png.info(data)['interlace'] == 1
        assert png.decode(data) == (width, height, 'RGB', pixels)


def test_decode_reference_files():
    w, h, mode, out = png.decode(PAL_TRNS)
    assert (w, h, mode) == (3, 2, 'RGBA')
    expected = [(10, 20, 30, 255), (200, 100, 50, 0), (0, 255, 0, 255),
                (0, 255, 0, 255), (200, 100, 50, 0), (10, 20, 30, 255)]
    assert out == _flat(expected)
    assert png.info(PAL_TRNS)['mode'] == 'RGBA'

    assert png.decode(G16) == (2, 2, 'L', bytes(bytearray([0, 255, 0x12, 0xAB])))
    assert png.decode(BIT1)[3] == bytes(bytearray(
        [255, 0, 255, 0, 255, 0, 255, 0, 255, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 255]))
    assert png.decode(RGBA_OPT) == (4, 3, 'RGBA', _flat(RGBA_OPT_PIXELS))


def test_decode_rejects_bad_input():
    raises(ValueError, png.decode, b'not a png at all')
    good = png.encode(2, 2, [0] * 12)
    broken = bytearray(good)
    broken[30] ^= 0xFF          # inside IHDR: CRC no longer matches
    raises(ValueError, png.decode, bytes(broken))
    raises(ValueError, png.decode, good[:40])


def test_sizes_and_sniffing():
    data = png.encode(7, 5, [0] * 35, 'L')
    assert png.size(data) == (7, 5)
    assert png.image_size(data) == (7, 5)
    assert png.sniff(data) == 'png'
    assert png.mime_type(data) == 'image/png'
    gif = b'GIF89a' + struct.pack('<HH', 12, 34) + b'\x00' * 20
    assert png.sniff(gif) == 'gif' and png.image_size(gif) == (12, 34)
    bmp = b'BM' + b'\x00' * 16 + struct.pack('<ii', 40, -30) + b'\x00' * 30
    assert png.sniff(bmp) == 'bmp' and png.image_size(bmp) == (40, 30)
    assert png.sniff(b'<?xml version="1.0"?><svg xmlns="x"></svg>') == 'svg'
    assert png.sniff(b'hello') is None
    assert png.image_size(b'hello') is None
    raises(ValueError, png.size, b'\xff\xd8\xff\xe0')


def test_jpeg_size_from_markers():
    # SOI, APP0 (len 16), APP14 Adobe, SOF2 (progressive) 3 components 300x200, SOS
    app0 = b'\xff\xe0' + struct.pack('>H', 16) + b'JFIF\x00' + b'\x00' * 9
    app14 = b'\xff\xee' + struct.pack('>H', 14) + b'Adobe' + b'\x00' * 7
    sof = b'\xff\xc2' + struct.pack('>HBHHB', 17, 8, 200, 300, 3) + b'\x00' * 9
    data = b'\xff\xd8' + app0 + app14 + sof + b'\xff\xda\x00\x02' + b'\xff\xd9'
    assert png.jpeg_size(data) == (300, 200)
    head = png.jpeg_info(data)
    assert head['components'] == 3 and head['progressive'] and head['adobe']
    assert png.sniff(data) == 'jpeg'
    raises(ValueError, png.jpeg_size, b'\xff\xd8\xff\xda\x00\x02')


def test_idat_and_palette_helpers():
    plte, trns = png.palette_of(PAL_TRNS)
    assert plte[:9] == bytes(bytearray([10, 20, 30, 200, 100, 50, 0, 255, 0]))
    assert trns == b'\xff\x00'
    raw = zlib.decompress(png.idat_stream(PAL_TRNS))
    assert len(raw) == 2 * (1 + 3)          # two rows: filter byte + 3 index bytes


# --- Pillow cross-checks (CPython) ---------------------------------------------------------

def test_pillow_reads_our_output():
    Image = _pil()
    for mode, channels in (('L', 1), ('LA', 2), ('RGB', 3), ('RGBA', 4)):
        pixels = _pattern(13, 6, channels)
        image = Image.open(io.BytesIO(png.encode(13, 6, pixels, mode)))
        assert image.mode == mode and image.size == (13, 6)
        assert image.tobytes() == pixels
    bits = [(x + y) % 3 == 0 for y in range(4) for x in range(11)]
    image = Image.open(io.BytesIO(png.encode(11, 4, [255 if b else 0 for b in bits], '1')))
    assert image.mode == '1'
    assert list(image.convert('L').tobytes()) == [255 if b else 0 for b in bits]


def test_we_read_pillow_output():
    Image = _pil()
    for mode in ('L', 'LA', 'RGB', 'RGBA'):
        source = Image.frombytes(mode, (17, 9), _pattern(17, 9, len(mode)))
        buffer = io.BytesIO()
        source.save(buffer, 'PNG', optimize=True)
        assert png.decode(buffer.getvalue()) == (17, 9, mode, source.tobytes())
    rgb = Image.frombytes('RGB', (17, 9), _pattern(17, 9, 3))
    pal = rgb.quantize(colors=16)
    buffer = io.BytesIO()
    pal.save(buffer, 'PNG')
    assert png.decode(buffer.getvalue()) == (17, 9, 'RGB', pal.convert('RGB').tobytes())


def test_pillow_agrees_on_filtered_and_interlaced():
    Image = _pil()
    pixels = _pattern(11, 9, 4)
    for interlace in (False, True):
        data = _make_png(11, 9, 6, 4, pixels, interlace=interlace)
        assert Image.open(io.BytesIO(data)).tobytes() == pixels


def test_jpeg_size_matches_pillow():
    Image = _pil()
    for mode, kwargs in (('RGB', {}), ('RGB', {'progressive': True}), ('L', {}), ('CMYK', {})):
        buffer = io.BytesIO()
        Image.new(mode, (123, 45)).save(buffer, 'JPEG', **kwargs)
        data = buffer.getvalue()
        assert png.jpeg_size(data) == (123, 45)
        head = png.jpeg_info(data)
        assert head['components'] == len(mode)
        assert head['progressive'] == bool(kwargs.get('progressive'))
        if mode == 'CMYK':
            assert head['adobe']

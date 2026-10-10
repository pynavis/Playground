# -*- coding: utf-8 -*-
"""Tiny pure-Python PNG codec plus image-header sniffing (PNG, JPEG, GIF, BMP).

Pure `zlib` + `struct`, no Pillow, no System.Drawing, so it runs the same under
CPython and IronPython 3.4. Used by namo.pdf (embedding), namo.xlsx and
namo.htmlreport (pixel sizes), and by tools that want to write a small image.

    data = png.encode(2, 1, [255, 0, 0, 0, 0, 255])         # 2x1 RGB: red, blue
    png.write(path, w, h, rows, mode='RGBA')
    w, h, mode, pixels = png.decode(data)                   # 8-bit samples, flat bytes
    png.size(data); png.jpeg_size(data); png.image_size(data); png.sniff(data)

Encoding writes 8-bit L/RGB/RGBA or 1-bit ('1') images, filter type 0, never
interlaced. Decoding reads every standard PNG: bit depths 1/2/4/8/16, grey, grey +
alpha, RGB, RGBA, palette, tRNS transparency and Adam7 interlacing. Output samples are
always 8-bit (16-bit keeps the high byte, low depths are scaled to 0..255).

Speed: decoding is a per-byte Python loop for rows that use the Sub/Average/Paeth
filters, about 0.35 s per million bytes under IronPython (measured: Paeth-filtered
640x360 RGBA 0.37 s, 1920x1080 RGB 2.1 s). Prefer JPEG or plain RGB PNG when you only
need to embed an image in a PDF: namo.pdf passes those through without decoding.
"""
import struct
import zlib

SIGNATURE = b'\x89PNG\r\n\x1a\n'

# mode -> (colour type, channels) for the encoder; '1' is 1-bit greyscale.
_ENCODE_MODES = {
    'L': (0, 1),
    'LA': (4, 2),
    'RGB': (2, 3),
    'RGBA': (6, 4),
    '1': (0, 1),
}

# colour type -> channels in the file
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_VALID_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}

_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
          (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))

# JPEG start-of-frame markers (baseline, extended, progressive, lossless, arithmetic).
_SOF_MARKERS = (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF)
_PROGRESSIVE_SOF = (0xC2, 0xC6, 0xCA, 0xCE)


# ---------------------------------------------------------------------------
# Sniffing and sizes
# ---------------------------------------------------------------------------

def _as_bytes(data):
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    raise TypeError('expected bytes, got %s' % type(data).__name__)


def sniff(data):
    """Image format from the first bytes: 'png', 'jpeg', 'gif', 'bmp', 'webp', 'svg' or None."""
    if not isinstance(data, (bytes, bytearray)):
        return None
    head = bytes(data[:512])
    if head.startswith(SIGNATURE):
        return 'png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if head.startswith(b'GIF87a') or head.startswith(b'GIF89a'):
        return 'gif'
    if head.startswith(b'BM') and len(head) >= 26:
        return 'bmp'
    if head.startswith(b'RIFF') and head[8:12] == b'WEBP':
        return 'webp'
    text = head.lstrip(b'\xef\xbb\xbf \t\r\n').lower()
    if text.startswith(b'<svg') or (text.startswith(b'<?xml') and b'<svg' in text):
        return 'svg'
    return None


def mime_type(data):
    """MIME type for sniff(data), or None when the bytes are not a known image."""
    return {
        'png': 'image/png', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'bmp': 'image/bmp',
        'webp': 'image/webp', 'svg': 'image/svg+xml',
    }.get(sniff(data))


def info(data):
    """PNG header as a dict: width, height, bit_depth, color_type, interlace, mode.

    `mode` is what decode() returns for this file. Raises ValueError when the bytes
    are not a PNG.
    """
    data = _as_bytes(data)
    if not data.startswith(SIGNATURE) or len(data) < 33 or data[12:16] != b'IHDR':
        raise ValueError('not a PNG file')
    width, height, depth, ctype, _comp, _filt, interlace = struct.unpack('>IIBBBBB', data[16:29])
    has_trns = b'tRNS' in _kinds_before_idat(data)
    if ctype == 0:
        mode = 'LA' if has_trns else 'L'
    elif ctype == 2:
        mode = 'RGBA' if has_trns else 'RGB'
    elif ctype == 3:
        mode = 'RGBA' if has_trns else 'RGB'
    elif ctype == 4:
        mode = 'LA'
    else:
        mode = 'RGBA'
    return {'width': width, 'height': height, 'bit_depth': depth, 'color_type': ctype,
            'interlace': interlace, 'mode': mode, 'transparency': has_trns}


def _kinds_before_idat(data):
    """Chunk type codes from IHDR up to (not including) the first IDAT; no CRC checks."""
    kinds = []
    pos = len(SIGNATURE)
    while pos + 8 <= len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        if kind in (b'IDAT', b'IEND'):
            break
        kinds.append(kind)
        pos += 12 + length
    return kinds


def size(data):
    """(width, height) from a PNG's IHDR chunk. Raises ValueError for non-PNG bytes."""
    head = info(data)
    return head['width'], head['height']


def jpeg_info(data):
    """JPEG frame header: {'width','height','components','bits','progressive','adobe'}.

    `adobe` is True when an Adobe APP14 marker is present (CMYK JPEGs written by
    Adobe software store inverted samples; namo.pdf uses it to set /Decode). Raises
    ValueError when no start-of-frame marker is found.
    """
    data = _as_bytes(data)
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('not a JPEG file')
    pos = 2
    end = len(data)
    adobe = False
    while pos < end:
        if data[pos] != 0xFF:
            pos += 1
            continue
        while pos < end and data[pos] == 0xFF:
            pos += 1
        if pos >= end:
            break
        marker = data[pos]
        pos += 1
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            continue
        if marker == 0xD9:
            break
        if pos + 2 > end:
            break
        length = struct.unpack('>H', data[pos:pos + 2])[0]
        if marker == 0xEE and data[pos + 2:pos + 7] == b'Adobe':
            adobe = True
        if marker in _SOF_MARKERS:
            if pos + 8 > end:
                break
            bits = data[pos + 2]
            height, width = struct.unpack('>HH', data[pos + 3:pos + 7])
            components = data[pos + 7]
            if width == 0 or height == 0:
                raise ValueError('JPEG frame has no size (DNL marker files are not supported)')
            return {'width': width, 'height': height, 'components': components, 'bits': bits,
                    'progressive': marker in _PROGRESSIVE_SOF, 'adobe': adobe}
        if marker == 0xDA:
            break
        pos += length
    raise ValueError('JPEG has no frame header')


def jpeg_size(data):
    """(width, height) from a JPEG's start-of-frame marker. Raises ValueError otherwise."""
    head = jpeg_info(data)
    return head['width'], head['height']


def image_size(data):
    """(width, height) for PNG, JPEG, GIF or BMP bytes; None for anything else."""
    kind = sniff(data)
    try:
        if kind == 'png':
            return size(data)
        if kind == 'jpeg':
            return jpeg_size(data)
        if kind == 'gif' and len(data) >= 10:
            return struct.unpack('<HH', bytes(data[6:10]))
        if kind == 'bmp':
            width, height = struct.unpack('<ii', bytes(data[18:26]))
            return abs(width), abs(height)
    except (ValueError, struct.error):
        return None
    return None


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def _chunk(kind, payload):
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', crc)


def _is_seq(value):
    return isinstance(value, (list, tuple, bytes, bytearray))


def _flatten(width, height, pixels, channels):
    """Any accepted pixel layout -> one bytearray of width*height*channels samples."""
    expected = width * height * channels
    if isinstance(pixels, (bytes, bytearray)):
        flat = bytearray(pixels)
    elif isinstance(pixels, str):
        raise TypeError('pixels must be bytes, bytearray or a list, not str')
    else:
        items = list(pixels)
        if items and _is_seq(items[0]):
            # rows, or one tuple per pixel; either way flatten one or two levels
            out = bytearray()
            for item in items:
                if len(item) and _is_seq(item[0]):
                    for px in item:          # a row of per-pixel tuples
                        out.extend(bytearray(px))
                else:
                    out.extend(bytearray(item))   # a row of samples, or one pixel
            flat = out
        else:
            flat = bytearray(items)
    if len(flat) != expected:
        raise ValueError('expected %d samples (%dx%d, %d channel(s)), got %d'
                         % (expected, width, height, channels, len(flat)))
    return flat


def _pack_bits(flat, width, height):
    """1-bit rows: nonzero sample -> white (1), zero -> black (0), MSB first."""
    rows = []
    for y in range(height):
        row = flat[y * width:(y + 1) * width]
        packed = bytearray((width + 7) // 8)
        for x in range(width):
            if row[x]:
                packed[x >> 3] |= 0x80 >> (x & 7)
        rows.append(packed)
    return rows


def encode(width, height, pixels, mode='RGB', compress_level=6):
    """PNG bytes for an image.

    pixels: flat bytes/bytearray/list of 8-bit samples (row by row, channel
    interleaved), a list of rows (each a flat sequence), or a list of per-pixel
    tuples (flat or in rows). mode: 'L', 'LA', 'RGB', 'RGBA', or '1' (1-bit: zero is
    black, any nonzero sample is white). Raises ValueError on a size mismatch or a
    sample outside 0..255.
    """
    if mode not in _ENCODE_MODES:
        raise ValueError('unknown PNG mode %r (use L, LA, RGB, RGBA or 1)' % (mode,))
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        raise ValueError('image size must be positive, got %dx%d' % (width, height))
    ctype, channels = _ENCODE_MODES[mode]
    flat = _flatten(width, height, pixels, channels)
    raw = bytearray()
    if mode == '1':
        depth = 1
        for packed in _pack_bits(flat, width, height):
            raw.append(0)
            raw.extend(packed)
    else:
        depth = 8
        stride = width * channels
        for y in range(height):
            raw.append(0)
            raw.extend(flat[y * stride:(y + 1) * stride])
    header = struct.pack('>IIBBBBB', width, height, depth, ctype, 0, 0, 0)
    return (SIGNATURE + _chunk(b'IHDR', header)
            + _chunk(b'IDAT', zlib.compress(bytes(raw), compress_level))
            + _chunk(b'IEND', b''))


def write(path, width, height, pixels, mode='RGB'):
    """Encode and write a PNG file; returns path."""
    data = encode(width, height, pixels, mode)
    handle = open(path, 'wb')
    try:
        handle.write(data)
    finally:
        handle.close()
    return path


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

def _read_chunks(data):
    """[(kind, payload)] in file order up to IEND; critical-chunk CRCs verified."""
    if not data.startswith(SIGNATURE):
        raise ValueError('not a PNG file')
    pos = len(SIGNATURE)
    end = len(data)
    chunks = []
    while pos + 8 <= end:
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        if len(payload) != length or pos + 12 + length > end:
            raise ValueError('PNG chunk %r is truncated' % (kind,))
        crc = struct.unpack('>I', data[pos + 8 + length:pos + 12 + length])[0]
        if kind in (b'IHDR', b'PLTE', b'IDAT', b'IEND'):
            if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
                raise ValueError('PNG chunk %r has a bad CRC' % (kind,))
        chunks.append((kind, payload))
        pos += 12 + length
        if kind == b'IEND':
            break
    return chunks


def _unfilter(raw, offset, stride, height, bpp):
    """Reverse PNG scanline filters. Returns (bytearray of height*stride, next offset)."""
    out = bytearray(stride * height)
    prev = bytearray(stride)
    pos = offset
    for y in range(height):
        if pos >= len(raw):
            raise ValueError('PNG image data is truncated')
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        if len(line) != stride:
            raise ValueError('PNG image data is truncated')
        pos += stride
        if ftype == 0:
            pass
        elif ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            line = bytearray([(a + b) & 0xFF for a, b in zip(line, prev)])
        elif ftype == 3:
            for i in range(min(bpp, stride)):
                line[i] = (line[i] + (prev[i] >> 1)) & 0xFF
            for i in range(bpp, stride):
                line[i] = (line[i] + ((line[i - bpp] + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(min(bpp, stride)):
                line[i] = (line[i] + prev[i]) & 0xFF
            for i in range(bpp, stride):
                a = line[i - bpp]
                b = prev[i]
                c = prev[i - bpp]
                p = a + b - c
                pa = p - a if p >= a else a - p
                pb = p - b if p >= b else b - p
                pc = p - c if p >= c else c - p
                if pa <= pb and pa <= pc:
                    pred = a
                elif pb <= pc:
                    pred = b
                else:
                    pred = c
                line[i] = (line[i] + pred) & 0xFF
        else:
            raise ValueError('PNG uses unknown filter type %d' % ftype)
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out, pos


def _samples(unfiltered, width, height, stride, depth, channels):
    """Unfiltered scanlines -> flat list-like of raw sample values (no scaling)."""
    if depth == 8:
        if stride == width * channels:
            return unfiltered
        out = bytearray()
        for y in range(height):
            out.extend(unfiltered[y * stride:y * stride + width * channels])
        return out
    if depth == 16:
        count = width * channels
        out = []
        for y in range(height):
            row = unfiltered[y * stride:(y + 1) * stride]
            out.extend(struct.unpack('>%dH' % count, bytes(row)))
        return out
    # 1, 2 or 4 bits per sample (grey or palette, one channel)
    out = bytearray()
    mask = (1 << depth) - 1
    per_byte = 8 // depth
    for y in range(height):
        row = unfiltered[y * stride:(y + 1) * stride]
        values = bytearray()
        for byte in row:
            for k in range(per_byte):
                values.append((byte >> (8 - depth * (k + 1))) & mask)
        out.extend(values[:width])
    return out


def _to_output(samples, count, depth, ctype, palette, trns):
    """Raw samples for `count` pixels -> (mode, 8-bit bytearray)."""
    if ctype == 3:
        if palette is None:
            raise ValueError('palette PNG has no PLTE chunk')
        entries = len(palette) // 3
        alpha = None
        if trns is not None:
            alpha = bytearray(trns) + bytearray([255] * max(0, entries - len(trns)))
        lut_rgb = [bytes(palette[i * 3:i * 3 + 3]) for i in range(entries)]
        if alpha is None:
            out = bytearray()
            for index in samples[:count]:
                if index >= entries:
                    raise ValueError('palette index %d out of range' % index)
                out.extend(lut_rgb[index])
            return 'RGB', out
        lut = [lut_rgb[i] + bytes(bytearray([alpha[i]])) for i in range(entries)]
        out = bytearray()
        for index in samples[:count]:
            if index >= entries:
                raise ValueError('palette index %d out of range' % index)
            out.extend(lut[index])
        return 'RGBA', out

    channels = _CHANNELS[ctype]
    if depth == 8:
        scaled = samples
    elif depth == 16:
        scaled = bytearray([v >> 8 for v in samples])
    else:
        factor = 255 // ((1 << depth) - 1)
        scaled = bytearray([v * factor for v in samples])

    if trns is not None and ctype in (0, 2):
        if ctype == 0:
            key = (struct.unpack('>H', bytes(trns[:2]))[0],)
        else:
            key = struct.unpack('>HHH', bytes(trns[:6]))
        out = bytearray()
        for i in range(count):
            raw = tuple(samples[i * channels:(i + 1) * channels])
            out.extend(scaled[i * channels:(i + 1) * channels])
            out.append(0 if raw == key else 255)
        return ('LA' if ctype == 0 else 'RGBA'), out
    mode = {0: 'L', 2: 'RGB', 4: 'LA', 6: 'RGBA'}[ctype]
    return mode, bytearray(scaled)


def decode(data):
    """Decode PNG bytes -> (width, height, mode, pixels).

    mode is 'L', 'LA', 'RGB' or 'RGBA'; pixels is flat bytes of 8-bit samples, row
    by row. Palette images come back as 'RGB' (or 'RGBA' with a tRNS chunk); grey or
    RGB images with a tRNS colour key come back as 'LA'/'RGBA'. Raises ValueError for
    anything that is not a valid PNG.
    """
    data = _as_bytes(data)
    chunks = _read_chunks(data)
    if not chunks or chunks[0][0] != b'IHDR':
        raise ValueError('PNG does not start with IHDR')
    width, height, depth, ctype, comp, filt, interlace = struct.unpack('>IIBBBBB', chunks[0][1][:13])
    if ctype not in _CHANNELS or depth not in _VALID_DEPTHS[ctype]:
        raise ValueError('unsupported PNG colour type %d / bit depth %d' % (ctype, depth))
    if comp != 0 or filt != 0 or interlace not in (0, 1):
        raise ValueError('unsupported PNG compression, filter or interlace method')
    if width == 0 or height == 0:
        raise ValueError('PNG has zero size')
    palette = None
    trns = None
    idat = []
    for kind, payload in chunks[1:]:
        if kind == b'PLTE':
            palette = payload
        elif kind == b'tRNS':
            trns = payload
        elif kind == b'IDAT':
            idat.append(payload)
    if not idat:
        raise ValueError('PNG has no image data')
    try:
        raw = zlib.decompress(b''.join(idat))
    except zlib.error as error:
        raise ValueError('PNG image data does not decompress: %s' % error)

    channels = _CHANNELS[ctype]
    bits_pp = depth * channels
    bpp = max(1, bits_pp // 8)

    if interlace == 0:
        stride = (width * bits_pp + 7) // 8
        unfiltered, _ = _unfilter(raw, 0, stride, height, bpp)
        samples = _samples(unfiltered, width, height, stride, depth, channels)
        mode, pixels = _to_output(samples, width * height, depth, ctype, palette, trns)
        return width, height, mode, bytes(pixels)

    # Adam7: decode each pass to output pixels, then scatter into the full image.
    full = None
    mode = None
    out_ch = 0
    offset = 0
    for xs, ys, dx, dy in _ADAM7:
        pw = (width - xs + dx - 1) // dx if width > xs else 0
        ph = (height - ys + dy - 1) // dy if height > ys else 0
        if pw == 0 or ph == 0:
            continue
        stride = (pw * bits_pp + 7) // 8
        unfiltered, offset = _unfilter(raw, offset, stride, ph, bpp)
        samples = _samples(unfiltered, pw, ph, stride, depth, channels)
        pass_mode, pixels = _to_output(samples, pw * ph, depth, ctype, palette, trns)
        if full is None:
            mode = pass_mode
            out_ch = len(mode)
            full = bytearray(width * height * out_ch)
        for py in range(ph):
            y = ys + py * dy
            for px in range(pw):
                x = xs + px * dx
                src = (py * pw + px) * out_ch
                dst = (y * width + x) * out_ch
                full[dst:dst + out_ch] = pixels[src:src + out_ch]
    return width, height, mode, bytes(full)


def read(path):
    """decode() the PNG file at path."""
    handle = open(path, 'rb')
    try:
        data = handle.read()
    finally:
        handle.close()
    return decode(data)


def idat_stream(data):
    """The concatenated (still compressed, still filtered) IDAT payload of a PNG.

    namo.pdf embeds this directly with a PNG predictor for non-interlaced images.
    """
    data = _as_bytes(data)
    return b''.join(payload for kind, payload in _read_chunks(data) if kind == b'IDAT')


def palette_of(data):
    """(PLTE bytes or None, tRNS bytes or None) of a PNG."""
    data = _as_bytes(data)
    plte = None
    trns = None
    for kind, payload in _read_chunks(data):
        if kind == b'PLTE':
            plte = payload
        elif kind == b'tRNS':
            trns = payload
    return plte, trns

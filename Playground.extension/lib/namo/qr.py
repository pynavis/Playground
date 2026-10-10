# -*- coding: utf-8 -*-
"""A pure QR Code encoder (ISO/IEC 18004:2015), PNG and SVG output.

Encodes text or bytes in byte mode (numeric and alphanumeric modes exist too, for the
published test vectors) at error correction level L, M, Q or H, in the smallest of the
40 versions that holds it (or a version you ask for), picks the best of the 8 masks
with the standard penalty rules (or the mask you ask for), and writes the format and
version information. Reed-Solomon runs over GF(256) with the 0x11D polynomial.

    from namo import qr
    code = qr.encode('https://example.com/?guid=3Zu5Bv0LOHrPC10026FoQQ', level='M')
    code.version, code.size, code.mask      # 3, 29, 4 (for example)
    code.modules[row][col]                  # True = dark
    png_bytes = qr.to_png(code, scale=8, border=4)
    svg_text = qr.to_svg(code, size_mm=30)

Text is encoded as UTF-8 without an ECI header (every current phone reader detects
UTF-8; ASCII payloads are unaffected either way).

Pure stdlib (+ namo.png); identical on CPython and IronPython 3.4. The structure
follows the reference algorithm published by Project Nayuki (function patterns, the
zigzag codeword placement, the run-history finder penalty), re-implemented here.
"""

LEVELS = ('L', 'M', 'Q', 'H')
_LEVEL_INDEX = {'L': 0, 'M': 1, 'Q': 2, 'H': 3}
# The two format bits each level writes (ISO 18004 table 12): L 01, M 00, Q 11, H 10.
FORMAT_BITS = {'L': 1, 'M': 0, 'Q': 3, 'H': 2}

MIN_VERSION = 1
MAX_VERSION = 40

# Error correction codewords per block, by level then version (index 0 unused).
_ECC_PER_BLOCK = (
    (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28,
     28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26,
     26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30,
     28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28,
     30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
)

# Error correction blocks, by level then version (index 0 unused).
_NUM_BLOCKS = (
    (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12,
     12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18,
     20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23,
     25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34,
     30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
)

# Penalty weights (ISO 18004 7.8.3.1, N1..N4).
PENALTY_N1 = 3
PENALTY_N2 = 3
PENALTY_N3 = 40
PENALTY_N4 = 10

_FORMAT_GENERATOR = 0x537       # BCH(15,5) generator x^10+x^8+x^5+x^4+x^2+x+1
_FORMAT_MASK = 0x5412           # XORed so no format word is all zeros
_VERSION_GENERATOR = 0x1F25     # BCH(18,6) generator

_ALNUM = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:'

# Mode indicator and character count bits per version range (1-9, 10-26, 27-40).
MODES = {
    'numeric': (0x1, (10, 12, 14)),
    'alphanumeric': (0x2, (9, 11, 13)),
    'byte': (0x4, (8, 16, 16)),
}


class QRError(ValueError):
    """The data does not fit, or an argument is out of range."""


# ---- GF(256) and Reed-Solomon ---------------------------------------------------------

_EXP = [0] * 512
_LOG = [0] * 256


def _build_tables():
    value = 1
    for power in range(255):
        _EXP[power] = value
        _LOG[value] = power
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for power in range(255, 512):
        _EXP[power] = _EXP[power - 255]


_build_tables()


def gf_mul(a, b):
    """a * b in GF(256) modulo x^8 + x^4 + x^3 + x^2 + 1 (0x11D)."""
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_pow2(power):
    """alpha^power (alpha = 2)."""
    return _EXP[power % 255]


def rs_divisor(degree):
    """Coefficients of prod(x - alpha^i, i < degree), highest power first, without the
    leading 1 (length `degree`)."""
    if not 1 <= degree <= 255:
        raise QRError('Reed-Solomon degree out of range')
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = gf_mul(root, 2)
    return result


def rs_remainder(data, divisor):
    """The Reed-Solomon error correction codewords of data for a divisor."""
    result = [0] * len(divisor)
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        if factor:
            for index, coef in enumerate(divisor):
                result[index] ^= gf_mul(coef, factor)
    return result


def rs_syndromes(codeword, count):
    """S_i = c(alpha^i) for i < count over a block (data then ECC, highest power
    first). All zero for a valid codeword: the independent check the tests use."""
    out = []
    for i in range(count):
        x = gf_pow2(i)
        acc = 0
        for byte in codeword:
            acc = gf_mul(acc, x) ^ byte
        out.append(acc)
    return out


# ---- sizes and capacities -------------------------------------------------------------


def _check_version(version):
    if not isinstance(version, int) or not MIN_VERSION <= version <= MAX_VERSION:
        raise QRError('QR versions run from 1 to 40, not %r' % (version,))


def _level(level):
    key = str(level or 'M').strip().upper()
    if key not in _LEVEL_INDEX:
        raise QRError('Error correction level must be L, M, Q or H, not %r' % (level,))
    return key


def size_of(version):
    """Modules per side: 21 for version 1, +4 per version."""
    _check_version(version)
    return version * 4 + 17


def raw_data_modules(version):
    """Modules left for data and ECC once every function pattern is placed."""
    _check_version(version)
    result = (16 * version + 128) * version + 64
    if version >= 2:
        count = version // 7 + 2
        result -= (25 * count - 10) * count - 55
        if version >= 7:
            result -= 36
    return result


def ecc_per_block(version, level):
    return _ECC_PER_BLOCK[_LEVEL_INDEX[_level(level)]][version]


def num_blocks(version, level):
    return _NUM_BLOCKS[_LEVEL_INDEX[_level(level)]][version]


def data_codewords(version, level):
    """8-bit data codewords a version holds at a level."""
    _check_version(version)
    return raw_data_modules(version) // 8 - ecc_per_block(version, level) * num_blocks(version, level)


def count_bits(mode, version):
    """Width of the character count field."""
    _check_version(version)
    widths = MODES[mode][1]
    return widths[0] if version <= 9 else widths[1] if version <= 26 else widths[2]


def segment_bits(mode, count, version):
    """Bits a segment of `count` characters (bytes in byte mode) takes, header included."""
    if mode == 'byte':
        payload = count * 8
    elif mode == 'alphanumeric':
        payload = (count // 2) * 11 + (count % 2) * 6
    else:
        payload = (count // 3) * 10 + {0: 0, 1: 4, 2: 7}[count % 3]
    return 4 + count_bits(mode, version) + payload


def capacity(version, level, mode='byte'):
    """Most characters (bytes in byte mode) that fit in a version at a level."""
    bits = data_codewords(version, level) * 8
    best = 0
    low, high = 0, 8000
    while low <= high:
        middle = (low + high) // 2
        needed = segment_bits(mode, middle, version)
        if middle < (1 << count_bits(mode, version)) and needed <= bits:
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    return best


def alignment_positions(version):
    """Row/column centres of the alignment patterns (ISO 18004 annex E)."""
    _check_version(version)
    if version == 1:
        return []
    count = version // 7 + 2
    step = (version * 8 + count * 3 + 5) // (count * 4 - 4) * 2
    size = size_of(version)
    result = [size - 7 - i * step for i in range(count - 1)] + [6]
    return list(reversed(result))


def format_bits(level, mask):
    """The 15-bit format word: 2 level bits, 3 mask bits, 10 BCH bits, XOR 0x5412."""
    if not 0 <= int(mask) <= 7:
        raise QRError('Masks run from 0 to 7')
    data = (FORMAT_BITS[_level(level)] << 3) | int(mask)
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * _FORMAT_GENERATOR)
    return ((data << 10) | (rem & 0x3FF)) ^ _FORMAT_MASK


def version_bits(version):
    """The 18-bit version word (versions 7 and up): 6 version bits, 12 BCH bits."""
    _check_version(version)
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * _VERSION_GENERATOR)
    return (version << 12) | (rem & 0xFFF)


# ---- data encoding ----------------------------------------------------------------------


class _Bits(object):
    def __init__(self):
        self.bits = []

    def append(self, value, length):
        for shift in range(length - 1, -1, -1):
            self.bits.append((value >> shift) & 1)

    def __len__(self):
        return len(self.bits)


def to_bytes(data):
    """bytes for a str (UTF-8), bytes, bytearray or a list of ints."""
    if isinstance(data, bytes):
        return bytearray(data)
    if isinstance(data, bytearray):
        return bytearray(data)
    if isinstance(data, (list, tuple)):
        return bytearray(data)
    return bytearray(str(data).encode('utf-8'))


def mode_for(text):
    """The most compact single mode for text: numeric, alphanumeric or byte."""
    if isinstance(text, (bytes, bytearray, list, tuple)):
        return 'byte'
    text = str(text)
    if text and all(ch in '0123456789' for ch in text):
        return 'numeric'
    if text and all(ch in _ALNUM for ch in text):
        return 'alphanumeric'
    return 'byte'


def _append_segment(bits, mode, data, version):
    indicator = MODES[mode][0]
    bits.append(indicator, 4)
    if mode == 'byte':
        payload = to_bytes(data)
        bits.append(len(payload), count_bits(mode, version))
        for byte in payload:
            bits.append(byte, 8)
    elif mode == 'alphanumeric':
        text = str(data)
        bits.append(len(text), count_bits(mode, version))
        for index in range(0, len(text) - 1, 2):
            bits.append(_ALNUM.index(text[index]) * 45 + _ALNUM.index(text[index + 1]), 11)
        if len(text) % 2:
            bits.append(_ALNUM.index(text[-1]), 6)
    else:
        text = str(data)
        bits.append(len(text), count_bits(mode, version))
        for index in range(0, len(text), 3):
            chunk = text[index:index + 3]
            bits.append(int(chunk), {1: 4, 2: 7, 3: 10}[len(chunk)])


def _segment_length(mode, data):
    return len(to_bytes(data)) if mode == 'byte' else len(str(data))


def data_codeword_bytes(data, version, level, mode='byte'):
    """The data codewords (header, payload, terminator, pad bytes) for one segment."""
    _check_version(version)
    level = _level(level)
    count = _segment_length(mode, data)
    if count >= (1 << count_bits(mode, version)):
        raise QRError('Too much data for version %d' % version)
    capacity_bits = data_codewords(version, level) * 8
    bits = _Bits()
    _append_segment(bits, mode, data, version)
    if len(bits) > capacity_bits:
        raise QRError('%d bits do not fit in version %d-%s (%d bits)'
                      % (len(bits), version, level, capacity_bits))
    bits.append(0, min(4, capacity_bits - len(bits)))
    bits.append(0, (8 - len(bits) % 8) % 8)
    out = []
    for index in range(0, len(bits.bits), 8):
        value = 0
        for bit in bits.bits[index:index + 8]:
            value = (value << 1) | bit
        out.append(value)
    pad = 0xEC
    while len(out) < capacity_bits // 8:
        out.append(pad)
        pad = 0x11 if pad == 0xEC else 0xEC
    return out


def split_blocks(data, version, level):
    """[(data_block, ecc_block)] in block order: short blocks first."""
    level = _level(level)
    blocks = num_blocks(version, level)
    ecc_len = ecc_per_block(version, level)
    raw = raw_data_modules(version) // 8
    short_count = blocks - raw % blocks
    short_len = raw // blocks
    divisor = rs_divisor(ecc_len)
    out = []
    start = 0
    for index in range(blocks):
        length = short_len - ecc_len + (0 if index < short_count else 1)
        chunk = list(data[start:start + length])
        start += length
        out.append((chunk, rs_remainder(chunk, divisor)))
    if start != len(data):
        raise QRError('Data length does not match the version and level')
    return out


def interleave(data, version, level):
    """Final codeword sequence: data blocks interleaved, then ECC blocks interleaved."""
    blocks = split_blocks(data, version, level)
    out = []
    longest = max(len(d) for d, _e in blocks)
    for index in range(longest):
        for chunk, _ecc in blocks:
            if index < len(chunk):
                out.append(chunk[index])
    for index in range(len(blocks[0][1])):
        for _chunk, ecc in blocks:
            out.append(ecc[index])
    return out


# ---- the matrix --------------------------------------------------------------------------


class QrCode(object):
    """A finished symbol: version, level, mask, size and modules[row][col] (True dark)."""

    def __init__(self, version, level, mask, modules, mode='byte', data_length=0):
        self.version = version
        self.level = level
        self.mask = mask
        self.modules = modules
        self.size = len(modules)
        self.mode = mode
        self.data_length = data_length

    def __repr__(self):
        return '<QrCode %d-%s mask %d, %dx%d>' % (self.version, self.level, self.mask,
                                                   self.size, self.size)

    def dark(self, row, col):
        return bool(self.modules[row][col])

    def text(self, dark='##', light='  '):
        """The symbol as text rows (debugging, tests)."""
        return '\n'.join(''.join(dark if cell else light for cell in row) for row in self.modules)


class _Grid(object):
    def __init__(self, version):
        self.version = version
        self.size = size_of(version)
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.function = [[False] * self.size for _ in range(self.size)]

    def set_function(self, col, row, dark):
        self.modules[row][col] = bool(dark)
        self.function[row][col] = True


def _bit(value, index):
    return ((value >> index) & 1) != 0


def _draw_finder(grid, col, row):
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            x, y = col + dx, row + dy
            if 0 <= x < grid.size and 0 <= y < grid.size:
                grid.set_function(x, y, max(abs(dx), abs(dy)) not in (2, 4))


def _draw_alignment(grid, col, row):
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            grid.set_function(col + dx, row + dy, max(abs(dx), abs(dy)) != 1)


def _draw_format(grid, level, mask):
    bits = format_bits(level, mask)
    size = grid.size
    for i in range(0, 6):
        grid.set_function(8, i, _bit(bits, i))
    grid.set_function(8, 7, _bit(bits, 6))
    grid.set_function(8, 8, _bit(bits, 7))
    grid.set_function(7, 8, _bit(bits, 8))
    for i in range(9, 15):
        grid.set_function(14 - i, 8, _bit(bits, i))
    for i in range(0, 8):
        grid.set_function(size - 1 - i, 8, _bit(bits, i))
    for i in range(8, 15):
        grid.set_function(8, size - 15 + i, _bit(bits, i))
    grid.set_function(8, size - 8, True)          # the dark module


def _draw_version(grid):
    if grid.version < 7:
        return
    bits = version_bits(grid.version)
    for i in range(18):
        dark = _bit(bits, i)
        a = grid.size - 11 + i % 3
        b = i // 3
        grid.set_function(a, b, dark)
        grid.set_function(b, a, dark)


def _draw_function_patterns(grid, level):
    size = grid.size
    for i in range(size):
        grid.set_function(6, i, i % 2 == 0)
        grid.set_function(i, 6, i % 2 == 0)
    _draw_finder(grid, 3, 3)
    _draw_finder(grid, size - 4, 3)
    _draw_finder(grid, 3, size - 4)
    positions = alignment_positions(grid.version)
    count = len(positions)
    skips = ((0, 0), (0, count - 1), (count - 1, 0))
    for i in range(count):
        for j in range(count):
            if (i, j) not in skips:
                _draw_alignment(grid, positions[i], positions[j])
    _draw_format(grid, level, 0)                 # reserves the area; rewritten later
    _draw_version(grid)


def _draw_codewords(grid, codewords):
    size = grid.size
    total = len(codewords) * 8
    index = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                col = right - j
                upward = ((right + 1) & 2) == 0
                row = (size - 1 - vert) if upward else vert
                if not grid.function[row][col] and index < total:
                    grid.modules[row][col] = _bit(codewords[index >> 3], 7 - (index & 7))
                    index += 1
        right -= 2
    if index != total:
        raise QRError('Codewords did not fill the symbol')


def mask_condition(mask, row, col):
    """True where mask pattern `mask` inverts a data module (ISO 18004 table 10)."""
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    if mask == 7:
        return ((row + col) % 2 + (row * col) % 3) % 2 == 0
    raise QRError('Masks run from 0 to 7')


def _apply_mask(grid, mask):
    size = grid.size
    for row in range(size):
        modules = grid.modules[row]
        function = grid.function[row]
        for col in range(size):
            if not function[col] and mask_condition(mask, row, col):
                modules[col] = not modules[col]


def _run_history_add(history, length, size):
    if history[0] == 0:
        length += size                           # light border before the first run
    history.insert(0, length)
    del history[7:]


def _finder_like(history, size):
    n = history[1]
    core = (n > 0 and history[2] == n and history[4] == n and history[5] == n
            and history[3] == n * 3)
    count = 0
    if core and history[0] >= n * 4 and history[6] >= n:
        count += 1
    if core and history[6] >= n * 4 and history[0] >= n:
        count += 1
    return count


def _line_penalty(cells, size):
    """Rule 1 (runs) and rule 3 (finder-like 1:1:3:1:1 with 4 light) for one line."""
    score = 0
    run_dark = False
    run = 0
    history = [0] * 7
    for cell in cells:
        if cell == run_dark:
            run += 1
            if run == 5:
                score += PENALTY_N1
            elif run > 5:
                score += 1
        else:
            _run_history_add(history, run, size)
            if not run_dark:
                score += _finder_like(history, size) * PENALTY_N3
            run_dark = cell
            run = 1
    if run_dark:
        _run_history_add(history, run, size)
        run = 0
    run += size                                   # light border after the last run
    _run_history_add(history, run, size)
    score += _finder_like(history, size) * PENALTY_N3
    return score


def penalty(modules):
    """The ISO 18004 penalty score of a finished matrix (lower is better)."""
    size = len(modules)
    score = 0
    for row in modules:
        score += _line_penalty(row, size)
    for col in range(size):
        score += _line_penalty([modules[row][col] for row in range(size)], size)
    for row in range(size - 1):
        upper = modules[row]
        lower = modules[row + 1]
        for col in range(size - 1):
            value = upper[col]
            if value == upper[col + 1] and value == lower[col] and value == lower[col + 1]:
                score += PENALTY_N2
    dark = 0
    for row in modules:
        for cell in row:
            if cell:
                dark += 1
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    score += max(0, k) * PENALTY_N4
    return score


def choose_version(data, level='M', mode='byte', min_version=1, max_version=MAX_VERSION):
    """Smallest version from min_version that holds the data at the level."""
    level = _level(level)
    count = _segment_length(mode, data)
    for version in range(max(MIN_VERSION, int(min_version)), int(max_version) + 1):
        if count >= (1 << count_bits(mode, version)):
            continue
        if segment_bits(mode, count, version) <= data_codewords(version, level) * 8:
            return version
    raise QRError('Too long for a QR code: %d %s at level %s (the most at this level is %d)'
                  % (count, 'bytes' if mode == 'byte' else 'characters', level,
                     capacity(MAX_VERSION, level, mode)))


def encode(data, level='M', version=None, mask=None, mode='byte', min_version=1):
    """A QrCode for data (str is UTF-8, or bytes). mode 'byte' (default),
    'alphanumeric', 'numeric' or 'auto' (the most compact one mode). version None picks
    the smallest that fits; mask None picks the lowest penalty. Raises QRError when the
    data does not fit or an argument is out of range."""
    level = _level(level)
    if mode == 'auto':
        mode = mode_for(data)
    if mode not in MODES:
        raise QRError('Unknown mode %r' % (mode,))
    if mode == 'alphanumeric' and any(ch not in _ALNUM for ch in str(data)):
        raise QRError('Alphanumeric mode takes 0-9, A-Z, space and $%*+-./: only')
    if mode == 'numeric' and any(ch not in '0123456789' for ch in str(data)):
        raise QRError('Numeric mode takes digits only')
    if version is None:
        version = choose_version(data, level, mode, min_version)
    _check_version(version)
    codewords = interleave(data_codeword_bytes(data, version, level, mode), version, level)
    grid = _Grid(version)
    _draw_function_patterns(grid, level)
    _draw_codewords(grid, codewords)
    if mask is None:
        best = None
        for candidate in range(8):
            _apply_mask(grid, candidate)
            _draw_format(grid, level, candidate)
            score = penalty(grid.modules)
            if best is None or score < best[0]:
                best = (score, candidate)
            _apply_mask(grid, candidate)          # XOR again undoes it
        mask = best[1]
    if not 0 <= int(mask) <= 7:
        raise QRError('Masks run from 0 to 7')
    _apply_mask(grid, int(mask))
    _draw_format(grid, level, int(mask))
    return QrCode(version, level, int(mask), grid.modules, mode, _segment_length(mode, data))


def function_mask(version):
    """modules[row][col] True where a function pattern (not data) sits."""
    grid = _Grid(version)
    _draw_function_patterns(grid, 'M')
    return grid.function


# ---- output --------------------------------------------------------------------------------


def pixels(code, scale=8, border=4):
    """(width, rows) of 0/255 grey samples: dark modules 0, light 255, with a quiet
    zone of `border` modules (4 is the standard minimum)."""
    scale = max(1, int(scale))
    border = max(0, int(border))
    size = code.size + 2 * border
    width = size * scale
    rows = []
    light_row = bytearray([255]) * width
    for row in range(-border, code.size + border):
        if row < 0 or row >= code.size:
            line = light_row
        else:
            line = bytearray()
            source = code.modules[row]
            for col in range(-border, code.size + border):
                dark = 0 <= col < code.size and source[col]
                line.extend(bytearray([0 if dark else 255]) * scale)
        for _ in range(scale):
            rows.append(bytes(line))
    return width, rows


def to_png(code, scale=8, border=4):
    """PNG bytes (8-bit grey) of the symbol."""
    from namo import png
    width, rows = pixels(code, scale, border)
    return png.encode(width, width, b''.join(rows), mode='L')


def write_png(code, path, scale=8, border=4):
    """Writes the PNG atomically; returns path."""
    from namo import paths
    return paths.atomic_write_bytes(path, to_png(code, scale, border))


def svg_path(code, border=4):
    """The 'd' of one path drawing every dark module, in module units, runs merged."""
    parts = []
    for row in range(code.size):
        cells = code.modules[row]
        col = 0
        while col < code.size:
            if cells[col]:
                start = col
                while col < code.size and cells[col]:
                    col += 1
                parts.append('M%d %dh%dv1h-%dz' % (start + border, row + border,
                                                   col - start, col - start))
            else:
                col += 1
    return ''.join(parts)


def to_svg(code, size_mm=None, border=4, dark='#000000', light='#FFFFFF'):
    """A standalone SVG of the symbol (crisp at any print size). size_mm sets the
    printed width and height; None leaves it to the container."""
    total = code.size + 2 * border
    dims = ''
    if size_mm:
        dims = ' width="%smm" height="%smm"' % (_num(size_mm), _num(size_mm))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d"%s '
            'shape-rendering="crispEdges"><rect width="%d" height="%d" fill="%s"/>'
            '<path d="%s" fill="%s"/></svg>'
            % (total, total, dims, total, total, light, svg_path(code, border), dark))


def _num(value):
    text = '%.2f' % float(value)
    return text.rstrip('0').rstrip('.')

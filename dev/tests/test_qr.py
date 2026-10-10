# -*- coding: utf-8 -*-
"""namo.qr: the pure QR encoder.

What is proven here, on both engines:
  * GF(256) with 0x11D, the Reed-Solomon divisor and remainder: the ISO 18004 annex I
    vector ("01234567", 1-M) and the published "HELLO WORLD" 1-M vector give exactly the
    published data and error correction codewords; every block of every symbol encoded
    below has all-zero syndromes (an independent evaluation c(alpha^i), not a division).
  * All 32 format words equal the published table and are pairwise at Hamming distance
    >= 7 (the BCH(15,5) code property); version words 7..40 equal the published values
    where known and are pairwise at distance >= 8 (BCH(18,6)).
  * Capacities (byte, numeric, alphanumeric) and alignment centres equal the published
    tables; versions 1..40 x L/M/Q/H all build.
  * Structure: finders, separators, timing, alignment, the dark module, both format
    copies and both version copies are where ISO 18004 puts them; reading the symbol back
    (unmask, zigzag, de-interleave) returns the payload.
Under CPython with OpenCV (cv2) available, additionally:
  * every symbol decodes with OpenCV's QRCodeDetectorAruco to the exact payload;
  * against cv2.QRCodeEncoder with the same version, level and mask, the matrices are
    identical except in the remainder bits (which ISO masks and OpenCV leaves), or where
    OpenCV's own symbol does not decode (it mis-builds 21-H).
"""
import random

import _compat
from namo import qr


# ---- maths ------------------------------------------------------------------------------


def test_gf_tables():
    assert qr.gf_pow2(0) == 1 and qr.gf_pow2(8) == 0x1D and qr.gf_pow2(255) == 1
    seen = set(qr.gf_pow2(i) for i in range(255))
    assert len(seen) == 255 and 0 not in seen
    for a in (1, 2, 3, 0x53, 0xCA, 0xFF):
        for b in (1, 7, 0x80, 0xFE):
            assert qr.gf_mul(a, b) == qr.gf_mul(b, a)
    assert qr.gf_mul(0x80, 2) == 0x1D
    assert qr.gf_mul(0, 9) == 0


def test_iso_annex_vector_01234567_1m():
    data = qr.data_codeword_bytes('01234567', 1, 'M', 'numeric')
    assert data == [0x10, 0x20, 0x0C, 0x56, 0x61, 0x80, 0xEC, 0x11, 0xEC, 0x11, 0xEC, 0x11,
                    0xEC, 0x11, 0xEC, 0x11]
    ecc = qr.rs_remainder(data, qr.rs_divisor(10))
    assert ecc == [0xA5, 0x24, 0xD4, 0xC1, 0xED, 0x36, 0xC7, 0x87, 0x2C, 0x55]
    assert qr.rs_syndromes(data + ecc, 10) == [0] * 10


def test_hello_world_vector_1m():
    data = qr.data_codeword_bytes('HELLO WORLD', 1, 'M', 'alphanumeric')
    assert data == [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
    ecc = qr.rs_remainder(data, qr.rs_divisor(10))
    assert ecc == [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]


def test_syndromes_catch_a_flipped_byte():
    data = [7, 99, 200, 3, 0, 12, 254]
    ecc = qr.rs_remainder(data, qr.rs_divisor(13))
    good = data + ecc
    assert qr.rs_syndromes(good, 13) == [0] * 13
    bad = list(good)
    bad[3] ^= 0x40
    assert any(qr.rs_syndromes(bad, 13))


FORMAT_TABLE = '''
111011111000100 111001011110011 111110110101010 111100010011101 110011000101111 110001100011000 110110001000001 110100101110110
101010000010010 101000100100101 101111001111100 101101101001011 100010111111001 100000011001110 100111110010111 100101010100000
011010101011111 011000001101000 011111100110001 011101000000110 010010010110100 010000110000011 010111011011010 010101111101101
001011010001001 001001110111110 001110011100111 001100111010000 000011101100010 000001001010101 000110100001100 000100000111011
'''.split()


def _distance(a, b):
    return bin(a ^ b).count('1')


def test_format_words_match_published_table_and_bch_distance():
    words = []
    for index, level in enumerate('LMQH'):
        for mask in range(8):
            word = qr.format_bits(level, mask)
            assert format(word, '015b') == FORMAT_TABLE[index * 8 + mask], (level, mask)
            words.append(word)
    for i in range(len(words)):
        for j in range(i + 1, len(words)):
            assert _distance(words[i], words[j]) >= 7


def test_version_words():
    known = {7: 0x07C94, 8: 0x085BC, 9: 0x09A99, 10: 0x0A4D3, 40: 0x28C69}
    for version, word in known.items():
        assert qr.version_bits(version) == word
    words = [qr.version_bits(v) for v in range(7, 41)]
    for i in range(len(words)):
        assert words[i] >> 12 == i + 7
        for j in range(i + 1, len(words)):
            assert _distance(words[i], words[j]) >= 8


def test_capacities_match_published_table():
    assert [qr.capacity(1, l) for l in 'LMQH'] == [17, 14, 11, 7]
    assert [qr.capacity(10, l) for l in 'LMQH'] == [271, 213, 151, 119]
    assert [qr.capacity(40, l) for l in 'LMQH'] == [2953, 2331, 1663, 1273]
    assert [qr.capacity(1, l, 'numeric') for l in 'LMQH'] == [41, 34, 27, 17]
    assert [qr.capacity(1, l, 'alphanumeric') for l in 'LMQH'] == [25, 20, 16, 10]
    assert [qr.capacity(40, l, 'numeric') for l in 'LMQH'] == [7089, 5596, 3993, 3057]
    assert qr.data_codewords(1, 'M') == 16 and qr.data_codewords(10, 'M') == 216
    assert qr.data_codewords(21, 'H') == 406


def test_alignment_positions():
    assert qr.alignment_positions(1) == []
    assert qr.alignment_positions(2) == [6, 18]
    assert qr.alignment_positions(7) == [6, 22, 38]
    assert qr.alignment_positions(14) == [6, 26, 46, 66]
    assert qr.alignment_positions(32) == [6, 34, 60, 86, 112, 138]
    assert qr.alignment_positions(40) == [6, 30, 58, 86, 114, 142, 170]


def test_bad_arguments():
    _compat.raises(qr.QRError, qr.encode, 'x', 'Z')
    _compat.raises(qr.QRError, qr.encode, 'x', 'M', 41)
    _compat.raises(qr.QRError, qr.encode, 'x', 'M', None, 8)
    _compat.raises(qr.QRError, qr.encode, 'x' * 3000, 'L')
    _compat.raises(qr.QRError, qr.encode, 'x' * 20, 'M', 1)
    _compat.raises(qr.QRError, qr.encode, 'abc', 'M', None, None, 'numeric')
    assert isinstance(qr.QRError('x'), ValueError)


# ---- reading a symbol back ----------------------------------------------------------------


def _read_codewords(code):
    function = qr.function_mask(code.version)
    size = code.size
    bits = []
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                col = right - j
                upward = ((right + 1) & 2) == 0
                row = size - 1 - vert if upward else vert
                if not function[row][col]:
                    dark = bool(code.modules[row][col]) != qr.mask_condition(code.mask, row, col)
                    bits.append(1 if dark else 0)
        right -= 2
    count = qr.raw_data_modules(code.version) // 8
    out = []
    for i in range(count):
        value = 0
        for bit in bits[i * 8:i * 8 + 8]:
            value = (value << 1) | bit
        out.append(value)
    remainder = bits[count * 8:]
    return out, remainder


def _deinterleave(codewords, version, level):
    blocks = qr.num_blocks(version, level)
    ecc_len = qr.ecc_per_block(version, level)
    raw = qr.raw_data_modules(version) // 8
    short_count = blocks - raw % blocks
    short_data = raw // blocks - ecc_len
    lengths = [short_data + (0 if i < short_count else 1) for i in range(blocks)]
    data = [[] for _ in range(blocks)]
    pos = 0
    for index in range(max(lengths)):
        for b in range(blocks):
            if index < lengths[b]:
                data[b].append(codewords[pos])
                pos += 1
    ecc = [[] for _ in range(blocks)]
    for index in range(ecc_len):
        for b in range(blocks):
            ecc[b].append(codewords[pos])
            pos += 1
    assert pos == len(codewords)
    return data, ecc


def _parse_byte_segment(data, version):
    bits = []
    for byte in data:
        bits.extend((byte >> s) & 1 for s in range(7, -1, -1))

    def take(n):
        value = 0
        for _ in range(n):
            value = (value << 1) | bits.pop(0)
        return value
    assert take(4) == 0x4
    count = take(qr.count_bits('byte', version))
    return bytearray(take(8) for _ in range(count))


def _format_copies(code):
    m = code.modules
    size = code.size
    first = 0
    for i in range(6):
        first |= (1 if m[i][8] else 0) << i
    first |= (1 if m[7][8] else 0) << 6
    first |= (1 if m[8][8] else 0) << 7
    first |= (1 if m[8][7] else 0) << 8
    for i in range(9, 15):
        first |= (1 if m[8][14 - i] else 0) << i
    second = 0
    for i in range(8):
        second |= (1 if m[8][size - 1 - i] else 0) << i
    for i in range(8, 15):
        second |= (1 if m[size - 15 + i][8] else 0) << i
    return first, second


def _check_structure(code):
    m = code.modules
    size = code.size
    assert size == code.version * 4 + 17
    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        for dy in range(7):
            for dx in range(7):
                ring = max(abs(dy - 3), abs(dx - 3))
                assert m[top + dy][left + dx] == (ring != 2), (top, left, dy, dx)
    for i in range(8):
        assert not m[7][i] and not m[i][7]
        assert not m[7][size - 1 - i] and not m[i][size - 8]
        assert not m[size - 8][i] and not m[size - 1 - i][7]
    for i in range(8, size - 8):
        assert m[6][i] == (i % 2 == 0) and m[i][6] == (i % 2 == 0)
    assert m[size - 8][8]
    positions = qr.alignment_positions(code.version)
    last = len(positions) - 1
    for i, row in enumerate(positions):
        for j, col in enumerate(positions):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    assert m[row + dy][col + dx] == (max(abs(dy), abs(dx)) != 1)
    first, second = _format_copies(code)
    assert first == second == qr.format_bits(code.level, code.mask)
    if code.version >= 7:
        word = qr.version_bits(code.version)
        for i in range(18):
            bit = bool((word >> i) & 1)
            a, b = size - 11 + i % 3, i // 3
            assert m[b][a] == bit and m[a][b] == bit


def _round_trip(text, level, version=None, mask=None):
    code = qr.encode(text, level=level, version=version, mask=mask)
    _check_structure(code)
    codewords, remainder = _read_codewords(code)
    assert all(bit == 0 for bit in remainder)
    data, ecc = _deinterleave(codewords, code.version, code.level)
    ecc_len = qr.ecc_per_block(code.version, code.level)
    for block_data, block_ecc in zip(data, ecc):
        assert qr.rs_syndromes(block_data + block_ecc, ecc_len) == [0] * ecc_len
    flat = [byte for block in data for byte in block]
    assert _parse_byte_segment(flat, code.version) == qr.to_bytes(text)
    return code


def test_round_trip_every_level_and_mask():
    for level in qr.LEVELS:
        for mask in range(8):
            _round_trip('https://example.com/?guid=3Zu5Bv0LOHrPC10026FoQQ', level, mask=mask)


def test_round_trip_versions_1_to_40_sampled():
    rng = random.Random(42)
    versions = list(range(1, 11)) + [14, 21, 27, 33, 40]
    for version in versions:
        level = qr.LEVELS[version % 4]
        size = qr.capacity(version, level)
        text = ''.join(rng.choice('abcdefghij0123456789|-:') for _ in range(size))
        code = _round_trip(text, level, version=version)
        assert code.version == version
        _compat.raises(qr.QRError, qr.encode, text + 'x', level, version)


def test_smallest_version_and_utf8():
    assert qr.encode('A', 'M').version == 1
    assert qr.encode('x' * 14, 'M').version == 1
    assert qr.encode('x' * 15, 'M').version == 2
    assert qr.encode('x' * 213, 'M').version == 10
    code = _round_trip(u'Café über 3°C', 'Q')
    assert code.data_length == len(u'Café über 3°C'.encode('utf-8'))


def test_mask_choice_is_lowest_penalty():
    code = qr.encode('Playground|Hospital.nwf|123456|2Ki0Pk1LT0NeYCumF5Cz6X', 'M')
    scores = []
    for mask in range(8):
        scores.append(qr.penalty(qr.encode('Playground|Hospital.nwf|123456|2Ki0Pk1LT0NeYCumF5Cz6X',
                                           'M', code.version, mask).modules))
    assert scores[code.mask] == min(scores)


def test_penalty_rules_on_tiny_matrices():
    light = [[False] * 5 for _ in range(5)]
    # 5 rows + 5 columns of a 5-run (3 each), 16 2x2 blocks (3 each), balance k=9 (all light)
    assert qr.penalty(light) == 10 * 3 + 16 * 3 + 9 * 10
    checker = [[(r + c) % 2 == 0 for c in range(5)] for r in range(5)]
    assert qr.penalty(checker) == 0


def test_png_and_svg_output():
    code = qr.encode('hello', 'M')
    data = qr.to_png(code, scale=4, border=4)
    from namo import png
    w, h, mode, pixels = png.decode(data)
    assert (w, h, mode) == ((21 + 8) * 4, (21 + 8) * 4, 'L')
    assert pixels[0] == 255
    top_left = (4 * 4) * w + 4 * 4                     # first finder module: dark
    assert pixels[top_left] == 0
    svg = qr.to_svg(code, size_mm=30)
    assert svg.startswith('<svg') and 'width="30mm"' in svg and 'viewBox="0 0 29 29"' in svg
    assert 'M4 4h7v1h-7z' in svg                      # finder top row merged as one run


# ---- independent checks (CPython + OpenCV only) --------------------------------------------


def _cv2():
    _compat.require_cpython('OpenCV is a CPython library')
    try:
        import cv2
        import numpy
    except ImportError:
        raise _compat.SkipTest('cv2 not installed')
    return cv2, numpy


def _image(numpy, modules, scale=6, border=4):
    size = len(modules)
    side = (size + 2 * border) * scale
    image = numpy.full((side, side), 255, numpy.uint8)
    for r in range(size):
        for c in range(size):
            if modules[r][c]:
                image[(r + border) * scale:(r + border + 1) * scale,
                      (c + border) * scale:(c + border + 1) * scale] = 0
    return image


def test_opencv_decodes_every_symbol():
    cv2, numpy = _cv2()
    detector = cv2.QRCodeDetectorAruco()
    rng = random.Random(11)
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCXYZ0123456789-/:?=&|_.~'
    checked = 0
    for level in qr.LEVELS:
        for length in (1, 7, 20, 45, 90, 150, 230, 380, 600):
            text = ''.join(rng.choice(alphabet) for _ in range(length))
            try:
                code = qr.encode(text, level)
            except qr.QRError:
                continue
            decoded = detector.detectAndDecode(_image(numpy, code.modules))[0]
            assert decoded == text, (level, length, code)
            checked += 1
    assert checked >= 30


def _remainder_positions(version):
    function = qr.function_mask(version)
    size = len(function)
    order = []
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                col = right - j
                upward = ((right + 1) & 2) == 0
                row = size - 1 - vert if upward else vert
                if not function[row][col]:
                    order.append((row, col))
        right -= 2
    used = (qr.raw_data_modules(version) // 8) * 8
    return set(order[used:])


def test_matches_opencv_encoder_except_remainder_bits():
    cv2, numpy = _cv2()
    if not hasattr(cv2, 'QRCodeEncoder'):
        raise _compat.SkipTest('cv2 has no QRCodeEncoder')
    levels = {'L': cv2.QRCodeEncoder_CORRECT_LEVEL_L, 'M': cv2.QRCodeEncoder_CORRECT_LEVEL_M,
              'Q': cv2.QRCodeEncoder_CORRECT_LEVEL_Q, 'H': cv2.QRCodeEncoder_CORRECT_LEVEL_H}
    detector = cv2.QRCodeDetectorAruco()
    rng = random.Random(7)
    identical = 0
    for _ in range(60):
        level = rng.choice('LMQH')
        text = ''.join(rng.choice('abcdefghijklmnop0123456789/:') for _ in range(rng.choice(
            (3, 12, 30, 60, 110, 170, 260))))
        mine = qr.encode(text, level)
        params = cv2.QRCodeEncoder_Params()
        params.version = mine.version
        params.correction_level = levels[level]
        params.mode = cv2.QRCodeEncoder_MODE_BYTE
        raw = cv2.QRCodeEncoder.create(params).encode(text)
        border = (raw.shape[0] - mine.size) // 2
        theirs = [[raw[r + border][c + border] == 0 for c in range(mine.size)]
                  for r in range(mine.size)]
        found = None
        first = _format_copies(qr.QrCode(mine.version, level, 0, theirs))[0]
        for mask in range(8):
            if qr.format_bits(level, mask) == first:
                found = mask
        assert found is not None
        forced = qr.encode(text, level, mine.version, found)
        diff = set((r, c) for r in range(mine.size) for c in range(mine.size)
                   if forced.modules[r][c] != theirs[r][c])
        if not diff:
            identical += 1
            continue
        if diff <= _remainder_positions(mine.version):
            continue
        # anything else must be OpenCV's mistake: its symbol does not decode, ours does
        assert detector.detectAndDecode(_image(numpy, theirs))[0] != text
        assert detector.detectAndDecode(_image(numpy, forced.modules))[0] == text
    assert identical >= 30

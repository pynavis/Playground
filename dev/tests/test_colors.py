# -*- coding: utf-8 -*-
"""namo.colors: parsing, conversion, ramps, categorical assignment, contrast."""
import _compat

from namo import colors


def test_parse_hex_forms():
    assert colors.parse_hex('ff8800') == 'FF8800'
    assert colors.parse_hex('#Ff8800') == 'FF8800'
    assert colors.parse_hex(' #f80 ') == 'FF8800'
    assert colors.parse_hex('#80FF8800') == 'FF8800'
    assert colors.parse_hex('xyz') is None
    assert colors.parse_hex('12345') is None
    assert colors.parse_hex(None) is None
    assert colors.parse_hex('') is None


def test_rgb_round_trip():
    assert colors.hex_to_rgb('4E79A7') == (78, 121, 167)
    assert colors.rgb_to_hex(78, 121, 167) == '4E79A7'
    assert colors.rgb_to_hex((78, 121, 167)) == '4E79A7'
    assert colors.rgb_to_hex(300, -5, 127.6) == 'FF0080'
    r, g, b = colors.rgb01('FF0000')
    assert (r, g, b) == (1.0, 0.0, 0.0)
    assert colors.from_rgb01(1.0, 0.5, 0.0) == 'FF8000'
    assert colors.from_rgb01(colors.rgb01('4E79A7')) == '4E79A7'


def test_hex_to_rgb_rejects_junk():
    _compat.raises(ValueError, colors.hex_to_rgb, 'nope')


def test_contrast_text():
    assert colors.contrast_text('FFFFFF') == '000000'
    assert colors.contrast_text('000000') == 'FFFFFF'
    assert colors.contrast_text('EDC948') == '000000'
    assert colors.contrast_text('1D4E89') == 'FFFFFF'


def test_contrast_ratio_bounds():
    assert _compat.approx(colors.contrast_ratio('000000', 'FFFFFF'), 21.0, 1e-6)
    assert _compat.approx(colors.contrast_ratio('777777', '777777'), 1.0)


def test_palette_is_distinct_and_mid_tone():
    assert len(colors.PALETTE) == 12
    assert len(set(colors.PALETTE)) == 12
    for i, a in enumerate(colors.PALETTE):
        assert colors.parse_hex(a) == a
        lum = colors.luminance(a)
        # readable as a fill on white and on the #202020 dark theme
        assert 0.08 < lum < 0.7, a
        for b in colors.PALETTE[i + 1:]:
            assert colors.distance(a, b) > 55, (a, b)


def test_for_values_order_and_repeats():
    pairs = colors.for_values(['Ducts', 'Pipes', 'Ducts', None, 'Walls'])
    assert [p[0] for p in pairs] == ['Ducts', 'Pipes', None, 'Walls']
    assert [p[1] for p in pairs] == colors.PALETTE[:4]


def test_for_values_beyond_palette_stays_distinct():
    pairs = colors.for_values(range(30))
    hexes = [p[1] for p in pairs]
    assert len(set(hexes)) == 30
    for h in hexes:
        assert colors.parse_hex(h) == h


def test_for_values_unhashable_values():
    pairs = colors.for_values([[1, 2], [1, 2], [3]])
    assert len(pairs) == 2


def test_for_values_custom_palette():
    pairs = colors.for_values(['a', 'b', 'c'], palette=['111111', '222222'])
    assert pairs[0][1] == '111111' and pairs[1][1] == '222222'
    assert pairs[2][1] == colors.generated(0)


def test_sequential_endpoints_and_monotone_lightness():
    assert colors.sequential(0) == colors.SEQUENTIAL_STOPS[0]
    assert colors.sequential(1) == colors.SEQUENTIAL_STOPS[-1]
    assert colors.sequential(-3) == colors.SEQUENTIAL_STOPS[0]
    assert colors.sequential(7) == colors.SEQUENTIAL_STOPS[-1]
    lums = [colors.luminance(colors.sequential(i / 10.0)) for i in range(11)]
    assert all(lums[i] > lums[i + 1] for i in range(10))


def test_sequential_nan_is_start():
    assert colors.sequential(float('nan')) == colors.SEQUENTIAL_STOPS[0]


def test_diverging_mid_is_neutral():
    assert colors.diverging(0.5) == 'E0E0E0'
    assert colors.diverging(0.0) == '2166AC'
    assert colors.diverging(1.0) == 'B2182B'


def test_bands():
    assert colors.bands(0) == []
    assert colors.bands(1) == [colors.sequential(1.0)]
    four = colors.bands(4)
    assert len(four) == 4 and four[-1] == colors.sequential(1.0)
    assert colors.luminance(four[0]) > colors.luminance(four[-1])


def test_blend_and_shades():
    assert colors.blend('000000', 'FFFFFF', 0.5) == '808080'
    assert colors.lighten('000000', 1.0) == 'FFFFFF'
    assert colors.darken('FFFFFF', 1.0) == '000000'


def test_hsl():
    assert colors.hsl_to_hex(0, 1, 0.5) == 'FF0000'
    assert colors.hsl_to_hex(120, 1, 0.5) == '00FF00'
    assert colors.hsl_to_hex(240, 1, 0.5) == '0000FF'
    assert colors.hsl_to_hex(0, 0, 0.5) == '808080'


def test_status_colors():
    assert colors.status_color('new') == colors.STATUS['New']
    assert colors.status_color(' Resolved ') == colors.STATUS['Resolved']
    assert colors.status_color('mystery') == colors.MISSING
    assert colors.status_color(None, default='000000') == '000000'
    for name in ('New', 'Active', 'Reviewed', 'Approved', 'Resolved'):
        assert name in colors.STATUS

# -*- coding: utf-8 -*-
"""namo.legend under IronPython + WPF: renders real legend PNGs (DrawingVisual +
RenderTargetBitmap) and checks their size and pixels with namo.png."""
import os

import _compat

_compat.require_ironpython()

from namo import colorize, colors, legend, png  # noqa: E402


def _scheme():
    plan = colorize.plan_scheme([('Ducts', 120), ('Pipes', 80), ('Cable Trays', 12),
                                 (colorize.NO_VALUE, 5), ('Walls', 3), ('Doors', 1)], top=3, other='grey')
    return colorize.make_scheme('Element', 'Category', plan, 'visible items')


def _pixel(decoded, x, y):
    width, _height, mode, data = decoded
    channels = 4 if mode == 'RGBA' else 3
    index = (int(y) * width + int(x)) * channels
    return tuple(bytearray(data[index:index + 3]))


def test_render_size_background_and_swatches():
    scheme = _scheme()
    data, width, height = legend.render(scheme)
    decoded = png.decode(data)
    assert decoded[0] == int(round(width * legend.SCALE)) and decoded[1] == int(round(height * legend.SCALE))
    assert width >= legend.STYLE['min_width'] and height > 100
    assert _pixel(decoded, 2, 2) == (255, 255, 255)
    text = legend._Text(legend.SCALE)
    plan = legend.layout(scheme, text.measure)
    for (x, y, size, hex_value), entry in zip(plan['swatches'], scheme['entries']):
        cx, cy = (x + size / 2.0) * legend.SCALE, (y + size / 2.0) * legend.SCALE
        got = _pixel(decoded, cx, cy)
        if hex_value:
            assert got == colors.hex_to_rgb(hex_value), (entry['value'], got, hex_value)
        else:
            assert got == (255, 255, 255)


def test_text_is_drawn_dark_on_white():
    scheme = _scheme()
    data, width, height = legend.render(scheme)
    decoded = png.decode(data)
    text = legend._Text(legend.SCALE)
    plan = legend.layout(scheme, text.measure)
    x, y, title = plan['texts'][0][0], plan['texts'][0][1], plan['texts'][0][2]
    w, h = text.measure(title, legend.STYLE['title_size'], True)
    dark = 0
    for py in range(int(y * 2), int((y + h) * 2), 2):
        for px in range(int(x * 2), int((x + w) * 2), 3):
            r, g, b = _pixel(decoded, px, py)
            if r + g + b < 200:
                dark += 1
    assert dark > 20


def test_save_png_and_long_values():
    folder = _compat.tmpdir('smoke_legend')
    scheme = _scheme()
    scheme['entries'][0]['value'] = 'A remarkably long category name ' * 8
    target = os.path.join(folder, 'sub', legend.default_name('Category', 'Hospital'))
    path, width, height, data = legend.save_png(scheme, target)
    assert os.path.exists(path) and os.path.getsize(path) == len(data)
    assert png.size(open(path, 'rb').read()) == (int(round(width * 2)), int(round(height * 2)))
    assert width < 720


def test_many_values_are_cut():
    plan = colorize.plan_scheme([('v%d' % i, 200 - i) for i in range(90)], top=40)
    scheme = colorize.make_scheme('Item', 'Layer', plan, 'whole model')
    data, width, height = legend.render(scheme)
    assert png.size(data)[1] < 2 * 60 * 30 + 400


def test_image_html_from_render():
    data, width, _height = legend.render(_scheme())
    html = legend.image_html(data, width, 'C:\\out\\legend.png')
    assert html.count('data:image/png;base64,') == 1 and ('width:%dpx' % width) in html

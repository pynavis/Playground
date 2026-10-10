# -*- coding: utf-8 -*-
"""namo.legend pure half: text fitting, rows, the layout with a fake measure, names,
the output-window image and the form."""
import _compat

from namo import colorize, legend


def measure(text, size, bold=False):
    """A fake font: every character 0.55 em wide (0.6 bold), 1.33 em tall."""
    return (len(text) * size * (0.6 if bold else 0.55), size * 1.33)


def _scheme(n=3, title='Category'):
    plan = colorize.plan_scheme([('Value %d' % i, 100 - i) for i in range(n)] + [(colorize.NO_VALUE, 5)],
                                top=n, other='leave')
    return colorize.make_scheme('Element', 'Category', plan, 'whole model', title=title)


def test_fit_cuts_with_ellipsis():
    assert legend.fit('Ducts', 100, measure, 10) == 'Ducts'
    cut = legend.fit('A very long value that will not fit', 60, measure, 10)
    assert cut.endswith(legend.ELLIPSIS) and measure(cut, 10)[0] <= 60
    assert legend.fit(None, 60, measure, 10) == ''


def test_rows_and_more():
    rows, more, total = legend.rows_of(_scheme(5), max_rows=3)
    assert len(rows) == 2 and more == 'and 4 more values'
    assert total == sum(100 - i for i in range(5)) + 5
    rows, more, _t = legend.rows_of(_scheme(2))
    assert more is None and rows[-1][0] is None and rows[-1][1] == colorize.NO_VALUE
    assert rows[0][2] == '100'


def test_layout_geometry():
    plan = legend.layout(_scheme(3), measure)
    assert plan['width'] >= legend.STYLE['min_width']
    assert len(plan['swatches']) == 4
    swatch_ys = [s[1] for s in plan['swatches']]
    assert swatch_ys == sorted(swatch_ys)
    assert plan['swatches'][-1][3] is None
    texts = [t[2] for t in plan['texts']]
    assert texts[0] == 'Category' and texts[1] == 'Element > Category, whole model'
    assert 'Total' in texts and '302' in texts
    right = [t for t in plan['texts'] if t[6] == 'right']
    assert right and all(t[0] <= plan['width'] - legend.STYLE['pad'] + 0.01 for t in right)
    assert len(plan['lines']) == 2
    assert plan['height'] > plan['lines'][1][1]


def test_layout_long_labels_are_capped():
    scheme = _scheme(1)
    scheme['entries'][0]['value'] = 'x' * 400
    plan = legend.layout(scheme, measure)
    label = [t for t in plan['texts'] if t[2].startswith('xxx')][0]
    assert label[2].endswith(legend.ELLIPSIS)
    assert plan['width'] < 700


def test_names_and_html():
    assert legend.default_name('Status', 'Hospital') == 'Hospital - Legend - Status.png'
    assert legend.default_name('A/B', '') == 'Legend - A_B.png'
    assert legend.view_name('Status') == 'Legend - Status'
    html = legend.image_html(b'\x89PNG', 300, 'C:\\out\\a <b>.png')
    assert 'width:300px' in html and 'data:image/png;base64,iVBORw==' in html
    assert '&lt;b&gt;' in html


def test_form_fields():
    fields = legend.form_fields(_scheme(), 'C:\\x\\Legend - Category.png', {'view': True})
    by_key = dict((f['key'], f) for f in fields)
    assert by_key['title']['default'] == 'Category'
    assert by_key['path']['default_name'] == 'Legend - Category.png'
    assert by_key['view']['default'] is True

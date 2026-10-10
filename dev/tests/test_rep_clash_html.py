# -*- coding: utf-8 -*-
"""rep_clash_html and clashrep_svg: the dashboard built from realistic fake clashes, parsed
back (KPIs, charts, tables, thumbnails, escaping), plus run() through the fake layer."""
import os

import _compat

import test_clashreport as fx
from namo import clashrep_svg as svg
from namo import clashreport as cr
from namo import png, reports
from namo import rep_clash_html as rep

try:
    from html.parser import HTMLParser
except ImportError:          # pragma: no cover
    HTMLParser = None


class Page(HTMLParser):
    """Collects what the tests look at: tags with classes, KPI blocks, table rows, images."""

    def __init__(self):
        HTMLParser.__init__(self)
        self.tags = []
        self.text = []
        self.kpis = []
        self._kpi = None
        self._field = None
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        cls = attrs.get('class') or ''
        if tag == 'script':
            self.scripts += 1
        if tag == 'div' and cls.startswith('kpi'):
            self._kpi = {'class': cls}
            self.kpis.append(self._kpi)
        elif self._kpi is not None and tag == 'div' and cls in ('l', 'v', 'd'):
            self._field = cls

    def handle_endtag(self, tag):
        if tag == 'div' and self._field is None and self._kpi is not None:
            self._kpi = None
        self._field = None

    def handle_data(self, data):
        self.text.append(data)
        if self._kpi is not None and self._field:
            self._kpi[self._field] = self._kpi.get(self._field, '') + data

    def count(self, tag, cls=None):
        return sum(1 for t, a in self.tags if t == tag and (cls is None or cls in (a.get('class') or '').split()))


def _parse(text):
    if HTMLParser is None:
        raise _compat.SkipTest('html.parser is not available')
    page = Page()
    page.feed(text)
    return page


def _thumbs(data, folder, count=4):
    pixels = bytes(bytearray([30, 90, 200] * (cr.THUMB_W * cr.THUMB_H)))
    made = 0
    for t_index, test in enumerate(data['tests']):
        for row in cr.filter_rows(test['rows'], cr.OPEN)[:count]:
            path = os.path.join(folder, 't%d-%d.png' % (t_index, row['id']))
            png.write(path, cr.THUMB_W, cr.THUMB_H, pixels, 'RGB')
            row['image'] = path
            made += 1
    return made


def test_contract():
    config = rep.default_config()
    assert config['name_template'] == rep.NAME_TEMPLATE and config['folder'] == ''
    assert reports.title_of('clash_html') == rep.TITLE
    assert rep.describe(config).startswith('Every test with results, table of open clashes')


def test_dashboard_content():
    folder = _compat.tmpdir('rep-clash-html')
    data = fx.fake_data()
    made = _thumbs(data, folder)
    text = rep.build_report(data, {'statuses': cr.OPEN, 'images': True}).to_string()
    page = _parse(text)
    kpis = dict((k.get('l', '').strip(), k.get('v', '').strip()) for k in page.kpis)
    assert kpis['Clashes'] == '600' and kpis['Open'] == '420'
    tally = cr.kpis(data)
    for status in cr.STATUSES:
        assert kpis[status] == '{:,}'.format(tally['by_status'][status])
    assert kpis['Oldest open (days)'] == str(tally['oldest']['age'])
    classes = [k['class'] for k in page.kpis]
    assert 'kpi t-new' in classes and 'kpi t-resolved' in classes
    assert page.count('div', 'chart-donut') == 1
    assert page.count('svg') >= 7
    assert page.count('path', 'tn-new') >= 1 and page.count('rect', 'tn-active') == 4
    assert page.count('svg', 'heatmap') == 1
    tables = page.count('table', 'data')
    assert tables >= 5
    assert page.count('img') == made
    assert '<script>alert' not in text and '&lt;script&gt;alert(&quot;x&quot;)' not in text
    assert u'Duct &lt;Supply&gt; &amp; Return ± Café' in text
    assert page.scripts == 1
    joined = ''.join(page.text)
    assert '420 clashes listed (New, Active, Reviewed)' in joined
    assert 'Out of date' in joined
    assert 'Open clashes, model against model' in joined
    assert 'no grid intersection' in joined
    assert 'Distances are in mm' in joined


def test_dashboard_without_images_or_groups():
    data = fx.fake_data()
    for test in data['tests']:
        for row in test['rows']:
            row['group'] = None
    text = rep.build_report(data, {'statuses': ['Resolved'], 'images': True}).to_string()
    page = _parse(text)
    assert page.count('img') == 0
    joined = ''.join(page.text)
    assert 'Groups' not in [t.strip() for t in page.text]
    assert '108 clashes listed (Resolved)' in joined


def test_dashboard_empty_data():
    data = fx.fake_data()
    for test in data['tests']:
        test['rows'] = []
    text = rep.build_report(data, {'statuses': cr.OPEN}).to_string()
    page = _parse(text)
    assert 'No data' in ''.join(page.text) and 'No rows.' in ''.join(page.text)


def test_identical_on_both_engines():
    fx.cross_engine('clash_html', rep.build_report(fx.fake_data(), {'statuses': cr.OPEN}).to_string().encode('utf-8'))


def test_svg_donut_and_bars():
    html = svg.status_donut({'New': 3, 'Active': 1, 'Resolved': 0}, 'Mix <b>')
    assert html.count('<path class="tn-') == 2 and 'Mix &lt;b&gt;' in html
    assert 'New: 3 (75.0%)' in html and '>4<' in html
    one = svg.status_donut({'Approved': 5})
    assert one.count('<path class="tn-approved"') == 2              # a full ring is two halves
    none = svg.status_donut({})
    assert 'stroke-width:26px' in none and '<path' not in none
    bars = svg.stacked_bars([('A & B', {'New': 2, 'Active': 1}), ('C', {'Resolved': 4})], 'By test')
    assert bars.count('<rect class="tn-') == 3 and 'A &amp; B' in bars
    assert '<li><span class="key tn-new"></span>New</li>' in bars and 'tn-approved' not in bars
    assert 'No data' in svg.stacked_bars([], 'Empty')
    assert svg.status_mix_html({'New': 2, 'Approved': 1}, lambda t, tone: '[%s|%s]' % (t, tone)) == \
        '[2 New|new] [1 Approved|approved]'


def test_data_uri():
    folder = _compat.tmpdir('rep-clash-html-uri')
    path = os.path.join(folder, 'x.png')
    png.write(path, 2, 2, bytes(bytearray([0] * 12)), 'RGB')
    assert rep.data_uri(path).startswith('data:image/png;base64,iVBOR')
    assert rep.data_uri(os.path.join(folder, 'missing.png')) is None


def test_run_through_fake_navisworks():
    doc, _a, _b = fx.fake_clash_doc()
    with fx.Redirected('rep-clash-html-run') as folder:
        with fx.nav.FakeNav(doc):
            result = reports.run('clash_html', {'images': False, 'folder': folder, 'statuses': []}, doc=doc)
    assert result['level'] == 'success', result
    assert result['message'] == 'Saved the clash dashboard'
    assert result['paths'][0].endswith('.html') and os.path.isfile(result['paths'][0])
    with open(result['paths'][0], 'rb') as handle:
        text = handle.read().decode('utf-8')
    assert 'Ducts vs Walls' in text and 'All 5 clashes listed' in text

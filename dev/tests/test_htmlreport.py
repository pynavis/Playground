# -*- coding: utf-8 -*-
"""namo.htmlreport: escaping, structure, tables, charts (well-formed SVG), images,
determinism. A node syntax check of the inline script runs when node is installed."""
import base64
import datetime
import io
import json
import os
import re
from xml.dom import minidom

import _compat
from _compat import raises, tmpdir

from namo import htmlreport as H
from namo import png

EVIL = u'<script>alert("x")</script>&\'"'


def _thumb(w=40, h=20):
    return png.encode(w, h, [30, 90, 160] * (w * h))


def _full_report():
    r = H.Report('Clash summary', subtitle='Level 3', meta=[('Model', 'a.nwf'), ('Tests', 1234)])
    r.kpis([('Clashes', 1270, None), ('New', 412, 'bad'), ('Ratio', 0.5, 'info', 'of all')])
    r.section('Status', intro='Intro text')
    r.bar_chart(['New', 'Active'], [412, 300], title='By status', tones=['new', 'active'])
    r.bar_chart(['L1', 'L2', 'L3'], [5, None, 2.5], title='Columns', horizontal=False)
    r.section('Trend')
    r.line_chart(['R1', 'R2', 'R3'], [('New', [3, 2, None]), ('Resolved', [0, 1, 4])], title='Trend')
    r.section('Share')
    r.donut(['A', 'B', 'C'], [1, 2, 3], title='Share')
    r.section('Matrix')
    r.heatmap(['M1', 'M2'], ['M1', 'M2'], [[0, 7], [7, 0]], title='Matrix')
    r.table(['Name', 'Status', 'Distance'], [['C1', r.status('New'), -0.05], ['C2', r.status('Resolved'), 0.1]],
            cell_html=set([(0, 1), (1, 1)]), row_tones=['bad', None], caption='Clashes')
    r.text('Para')
    r.note('Note')
    r.bullets(['one', 'two'])
    r.image(_thumb(), caption='Thumb', max_width=200)
    r.gallery([(_thumb(), 'G1'), (_thumb(16, 9), None)], columns=3)
    r.page_break()
    return r


class _Balance(object):
    """Checks that every non-void HTML element is closed in order."""
    VOID = set(['meta', 'img', 'br', 'input', 'hr', 'link', 'source', 'col', 'wbr', 'area', 'base'])

    def __init__(self, text):
        from html.parser import HTMLParser
        stack = []
        errors = []

        class P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag not in _Balance.VOID:
                    stack.append(tag)

            def handle_startendtag(self, tag, attrs):
                pass

            def handle_endtag(self, tag):
                if not stack or stack[-1] != tag:
                    errors.append('unexpected </%s> (open: %s)' % (tag, stack[-3:]))
                else:
                    stack.pop()

        P().feed(text)
        self.errors = errors
        self.open = stack


def _svgs(html):
    return re.findall(r'<svg .*?</svg>', html, re.S)


# --- escaping and formatting ------------------------------------------------------------

def test_escape():
    assert H.escape(EVIL) == u'&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;&amp;&#39;&quot;'
    assert H.escape(None) == u''
    assert H.escape(12) == u'12'
    assert H.escape(0.1) == u'0.1' and H.escape(2026.0) == u'2026'   # same on both engines
    assert H.escape(u'a\x00b\x1fc') == u'abc'


def test_numeric_labels_and_heat_text_are_engine_independent():
    r = H.Report('T')
    r.bar_chart([2025.0, 2026.0, 0.1], [1, 2, 3])
    r.heatmap([1.5], ['c'], [[1.0 / 3]])
    svgs = _svgs(r.to_string())
    assert u'>2025<' in svgs[0] and u'>2026<' in svgs[0] and u'>0.1<' in svgs[0]
    assert u'>0.33<' in svgs[1] and u'>1.5<' in svgs[1]


def test_format_number():
    assert H.format_number(1234567) == u'1,234,567'
    assert H.format_number(-1234.5) == u'-1,234.5'
    assert H.format_number(2.0) == u'2'
    assert H.format_number(0.125) == u'0.12'
    assert H.format_number(0.125, 3) == u'0.125'
    assert H.format_number(1e20) == u'100,000,000,000,000,000,000'
    for bad in (None, float('nan'), float('inf'), True):
        assert H.format_number(bad) == u''


def test_status_chips_and_tones():
    assert H.status_chip('New') == u'<span class="chip t-new">New</span>'
    assert H.status_chip('Resolved') == u'<span class="chip t-resolved">Resolved</span>'
    assert H.status_chip('Late', 'warn') == u'<span class="chip t-warn">Late</span>'
    assert H.status_chip('Whatever') == u'<span class="chip t-neutral">Whatever</span>'
    assert H.status_chip(u'<b>', 'good') == u'<span class="chip t-good">&lt;b&gt;</span>'
    assert H.tone_for_status(' APPROVED ') == 'approved'
    assert H.tone_for_status(None) == 'neutral'
    raises(ValueError, H.status_chip, 'x', 'purple')
    assert H.Report('t').status('Active') == u'<span class="chip t-active">Active</span>'


def test_links_and_file_urls():
    assert H.file_url(r'C:\Reports\a b#1.pdf') == u'file:///C:/Reports/a%20b%231.pdf'
    assert H.file_url(r'\\server\share\x.nwd') == u'file://server/share/x.nwd'
    assert H.file_url('https://x.com/?a=1&b=2') == u'https://x.com/?a=1&b=2'
    assert H.file_url(r'img\a.png') == u'img/a.png'
    assert H.link('https://x.com/?a=1&b=2', u'<x>') == u'<a href="https://x.com/?a=1&amp;b=2">&lt;x&gt;</a>'
    raises(ValueError, H.link, 'javascript:alert(1)')
    raises(ValueError, H.link, '  JavaScript:alert(1)')


def test_nice_ticks():
    assert H._nice_ticks(0, 512) == [0, 200, 400, 600]
    assert H._nice_ticks(0, 1) == [0, 0.25, 0.5, 0.75, 1.0]
    assert H._nice_ticks(0, 3, integers=True) == [0, 1, 2, 3]
    assert H._nice_ticks(0, 0) == [0, 0.25, 0.5, 0.75, 1.0]
    assert H._nice_ticks(-30, 70)[0] <= -30 and H._nice_ticks(-30, 70)[-1] >= 70


# --- whole report -----------------------------------------------------------------------

def test_report_structure():
    html = _full_report().to_string()
    assert html.startswith(u'<!DOCTYPE html>')
    assert u'<html lang="en">' in html and u'<meta charset="utf-8">' in html
    assert u'<title>Clash summary</title>' in html
    assert u'prefers-color-scheme: dark' in html and u'@media print' in html
    assert u'Segoe UI Variable' in html and u'font-size: 13px' in html
    assert u'<dt>Tests</dt><dd>1,234</dd>' in html
    assert u'<div class="v">1,270</div>' in html and u'kpi t-bad' in html
    assert u'<div class="d">of all</div>' in html
    assert u'<nav class="toc"' in html            # four sections -> contents list
    assert html.count(u'<h2 id="s') == 4
    assert u'class="intro">Intro text<' in html
    assert u'<footer class="foot">Made with pyNavis Playground</footer>' in html
    assert u'id="tip"' in html and u'id="lb"' in html
    assert u'<div class="pb"></div>' in html
    balance = _Balance(html)
    assert balance.errors == [] and balance.open == [], (balance.errors, balance.open)


def test_design_rules_hold():
    html = _full_report().to_string()
    css = html[html.index(u'<style>'):html.index(u'</style>')]
    assert u'gradient' not in css
    shadows = re.findall(r'box-shadow[^;]*;', css)
    assert len(shadows) == 1           # the floating tooltip is the only shadow
    for dash in (u'\u2014', u'\u2013'):
        assert dash not in html


def test_toc_and_footer_options():
    r = H.Report('T', toc=False, footer='')
    for i in range(5):
        r.section('S%d' % i)
    html = r.to_string()
    assert u'<nav class="toc"' not in html and u'<footer' not in html
    r = H.Report('T', toc=True, footer='Custom <foot>')
    r.section('Only')
    html = r.to_string()
    assert u'<a href="#s1">Only</a>' in html
    assert u'<footer class="foot">Custom &lt;foot&gt;</footer>' in html
    plain = H.Report('Plain').to_string()
    assert u'id="tip"' not in plain and u'id="lb"' not in plain


def test_every_text_input_is_escaped():
    r = H.Report(EVIL, subtitle=EVIL, meta=[(EVIL, EVIL)], footer=EVIL, toc=True)
    r.kpis([(EVIL, EVIL, None, EVIL)])
    r.section(EVIL, intro=EVIL)
    r.text(EVIL)
    r.note(EVIL)
    r.bullets([EVIL])
    r.table([EVIL], [[EVIL]], caption=EVIL)
    r.bar_chart([EVIL], [1], title=EVIL)
    r.bar_chart([EVIL], [1], title=EVIL, horizontal=False)
    r.line_chart([EVIL, EVIL], [(EVIL, [1, 2]), ('b', [2, 1])], title=EVIL)
    r.donut([EVIL], [1], title=EVIL)
    r.heatmap([EVIL], [EVIL], [[1]], title=EVIL)
    r.image(_thumb(), caption=EVIL)
    r.gallery([(_thumb(), EVIL)])
    html = r.to_string()
    assert html.count(u'<script>') == 1               # only the report's own script
    assert u'alert("x")' not in html and u"&'\"" not in html
    for svg in _svgs(html):
        minidom.parseString(svg.encode('utf-8'))      # still well-formed XML
    balance = _Balance(html)
    assert balance.errors == [] and balance.open == []


def test_output_is_deterministic():
    assert _full_report().to_string() == _full_report().to_string()


def test_save_writes_utf8_atomically():
    folder = tmpdir('htmlreport_save')
    path = os.path.join(folder, 'sub', 'r.html')
    r = H.Report(u'Caf\u00e9 \u4e2d\u6587 \U0001F600')
    assert r.save(path) == path
    assert not os.path.exists(path + '.tmp')
    text = io.open(path, encoding='utf-8').read()
    assert u'<title>Caf\u00e9 \u4e2d\u6587 \U0001F600</title>' in text


# --- tables -----------------------------------------------------------------------------

def test_table_numeric_detection_sorting_and_tones():
    r = H.Report('T')
    rows = [['a', 1, '1,234', 0.5, True, datetime.date(2026, 1, 2)],
            ['b', 2.25, '12', 7, False, datetime.datetime(2026, 1, 2, 3, 4)],
            ['c', None, '', 1, None, None]]
    tid = r.table(['Name', 'N', 'Text num', 'Mixed', 'Flag', 'When'], rows, row_tones=[None, 'warn', None])
    html = r.to_string()
    block = html[html.index(u'id="%s"' % tid):]
    heads = re.findall(r'<th scope="col" class="([^"]*)">', block)[:6]
    assert heads == [u'btn', u'btn num', u'btn num', u'btn num', u'btn', u'btn']
    assert u'data-sortable="1"' in block
    assert u'<input type="search" class="filter"' in block
    assert u'<span class="count">3 rows</span>' in block
    # consistent decimals per numeric column: 1 -> 1.00 beside 2.25; 0.5 / 7 / 1 -> one place
    assert u'<td class="num" data-v="1">1.00</td>' in block
    assert u'<td class="num" data-v="2.25">2.25</td>' in block
    assert u'<td class="num" data-v="7">7.0</td>' in block
    assert u'<td>Yes</td>' in block and u'<td>No</td>' in block
    assert u'<td data-v="2026-01-02">2026-01-02</td>' in block
    assert u'<td data-v="2026-01-02T03:04:00">2026-01-02 03:04</td>' in block
    assert u'<tr class="t-warn">' in block and u'table class="data toned"' in block


def test_table_options():
    r = H.Report('T')
    r.table(['A', 'B'], [[u'<b>x</b>', u'<b>y</b>']], cell_html=set([(0, 1)]), sortable=False,
            filterable=False, numeric=[0])
    html = r.to_string()
    assert u'&lt;b&gt;x&lt;/b&gt;' in html and u'<td><b>y</b></td>' in html
    assert u'data-sortable="1"' not in html and u'class="filter"' not in html
    assert u'<th scope="col" class="num">A</th>' in html
    r = H.Report('T')
    r.table(['A'], [[i] for i in range(25)], max_rows=10, caption='Capped')
    html = r.to_string()
    assert html.count(u'<td class="num"') == 10
    assert u'Showing the first 10 of 25 rows.' in html
    assert u'aria-labelledby="t1-cap"' in html and u'<h3 id="t1-cap">Capped</h3>' in html
    r = H.Report('T')
    r.table(['Empty'], [])
    assert u'No rows.' in r.to_string()
    raises(ValueError, H.Report('T').table, ['A'], [[1]], row_tones=['loud'])


# --- charts -----------------------------------------------------------------------------

def test_charts_are_wellformed_svg():
    html = _full_report().to_string()
    svgs = _svgs(html)
    assert len(svgs) == 5            # bar, column, line, donut, heatmap
    for svg in svgs:
        root = minidom.parseString(svg.encode('utf-8')).documentElement
        assert root.getAttribute('role') == 'img' and root.getAttribute('viewBox')
    assert html.count(u'<details class="data"><summary>Data</summary>') == 5


def test_bar_charts():
    r = H.Report('T')
    r.bar_chart(['A', 'B', 'C'], [3, None, -1], title='Bars')
    svg = _svgs(r.to_string())[0]
    assert svg.count(u'<path class="s1"') == 2          # missing value draws no bar
    assert u'data-tip="B: no value"' in svg
    assert u'<text class="val"' in svg
    r = H.Report('T')
    r.bar_chart(['A', 'B'], [1, 2], tones=['good', None], horizontal=False)
    svg = _svgs(r.to_string())[0]
    assert u'<path class="tn-good"' in svg and u'<path class="s1"' in svg
    assert u'class="tick"' in svg                      # columns get a value axis
    r = H.Report('T')
    r.bar_chart([], [])
    assert u'No data' in r.to_string()
    r = H.Report('T')
    r.bar_chart(['A'], [1234.5], value_format='{:.0f} m')
    assert u'1234 m' in r.to_string() or u'1235 m' in r.to_string()


def test_line_chart_data_and_gaps():
    r = H.Report('T')
    series = [('S%d' % i, [i, i + 1, None, i + 2]) for i in range(8)]
    r.line_chart(['a', 'b', 'c', 'd'], series, title='Lines')
    html = r.to_string()
    svg = _svgs(html)[0]
    data = json.loads(H_unescape(re.search(r'data-d="([^"]*)"', svg).group(1)))
    assert data['labels'] == ['a', 'b', 'c', 'd']
    assert len(data['series']) == 8 and data['series'][0] == ['S0', ['0', '1', None, '2']]
    assert svg.count(u'class="ln k1"') == 1 and svg.count(u'class="ln ko lo"') == 2
    assert u'2 more series' in html                     # legend folds series 7 and 8
    assert u'class="xh"' in svg


def H_unescape(text):
    return (text.replace(u'&quot;', u'"').replace(u'&#39;', u"'").replace(u'&lt;', u'<')
            .replace(u'&gt;', u'>').replace(u'&amp;', u'&'))


def test_donut_folds_into_other():
    r = H.Report('T')
    labels = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    r.donut(labels, [1, 80, 3, 40, 5, 60, 7, 2])
    html = r.to_string()
    assert u'Other (3)' in html                        # A, C and H are the three smallest
    svg = _svgs(html)[0]
    assert svg.count(u'stroke-dasharray') == 6 and u'class="ko"' in svg
    assert u'>198<' in svg                             # total in the middle
    assert u'40.4%' in html                            # 80 of 198
    r = H.Report('T')
    r.donut(['A', 'B'], [0, None])
    assert u'No data' in r.to_string()


def test_heatmap_steps():
    r = H.Report('T')
    r.heatmap(['R1', 'R2'], ['C1', 'C2', 'C3'], [[0, 70, 10], [35, None, 1]], title='Heat')
    svg = _svgs(r.to_string())[0]
    assert u'<rect class="h7"' in svg                   # the peak
    assert u'<rect class="h4"' in svg                   # 35 of 70
    assert u'<rect class="h1"' in svg                   # 1 and 10 of 70
    assert svg.count(u'<rect class="h0"') == 2          # zero and missing stay unshaded
    assert u'data-tip="R2 / C2: no value"' in svg
    assert u'>0<' not in svg                            # zero not printed by default
    r = H.Report('T')
    r.heatmap(['R'], ['C'], [[0]], show_zero=True)
    assert u'>0<' in _svgs(r.to_string())[0]


# --- images -----------------------------------------------------------------------------

def test_image_embedding():
    data = _thumb(40, 20)
    r = H.Report('T')
    r.image(data, caption='Cap', max_width=300)
    html = r.to_string()
    uri = re.search(r'src="data:image/png;base64,([^"]+)"', html).group(1)
    assert base64.b64decode(uri) == data
    assert u'width="40" height="20"' in html and u'max-width:min(100%, 300px)' in html
    assert u'<figcaption>Cap</figcaption>' in html
    folder = tmpdir('htmlreport_img')
    path = os.path.join(folder, 'pic.png')
    png.write(path, 2, 2, [0] * 12)
    r = H.Report('T')
    r.image(path)
    assert u'alt="pic.png"' in r.to_string()
    raises(ValueError, H.Report('T').image, b'not an image')


def test_gallery():
    r = H.Report('T')
    r.gallery([(_thumb(), 'One'), (_thumb(), None)], columns=5)
    html = r.to_string()
    assert u'style="--cols:5"' in html
    assert html.count(u'<button type="button" class="zoom"') == 2
    assert u'aria-label="Enlarge: One"' in html and u'aria-label="Enlarge: Image"' in html
    assert u'role="dialog"' in html


# --- script (CPython + node) --------------------------------------------------------------

def test_inline_script_parses_in_node():
    _compat.require_cpython('runs node through subprocess')
    import subprocess
    import shutil
    node = shutil.which('node')
    if not node:
        raise _compat.SkipTest('node is not installed')
    html = _full_report().to_string()
    script = html[html.index(u'<script>') + len(u'<script>'):html.index(u'</script>')]
    folder = tmpdir('htmlreport_js')
    path = os.path.join(folder, 'report.js')
    io.open(path, 'w', encoding='utf-8').write(script)
    proc = subprocess.run([node, '--check', path], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# --- same text on both engines ----------------------------------------------------------

GOLDEN_HTML = '37da4d52c042787fd8388c3202150772'


def test_golden_digest_matches_on_both_engines():
    """The report text hashes the same under CPython and IronPython (float formatting in
    SVG and the line chart's JSON, dict order). If you change the output on purpose,
    update GOLDEN_HTML after checking both engines agree."""
    import hashlib
    r = H.Report(u'Golden é', subtitle='Both engines', meta=[('Count', 1234567), ('Ratio', 2.0 / 3)])
    r.kpis([('A', 1270, 'bad'), ('B', 0.125, None), ('C', 1e-7, 'good')])
    r.section('Charts')
    r.bar_chart(['a', 'b', 'c'], [1.0 / 3, 2, 7.5], title='Bars')
    r.bar_chart(['a', 'b', 'c'], [3, 1, 4], horizontal=False)
    r.line_chart(['x%d' % i for i in range(9)], [('s1', [i / 3.0 for i in range(9)]),
                                                 ('s2', [9 - i for i in range(9)])])
    r.donut(['p', 'q', 'r', 's', 't', 'u', 'v'], [5, 4, 3, 2, 1, 0.5, 0.25])
    r.heatmap(['r1', 'r2'], ['c1', 'c2'], [[1, 2.5], [0, None]])
    r.table(['N', 'V', 'D'], [[i, i / 9.0, datetime.date(2026, 1, 1 + i)] for i in range(10)],
            row_tones=['bad', None, 'good'])
    assert hashlib.md5(r.to_string().encode('utf-8')).hexdigest() == GOLDEN_HTML

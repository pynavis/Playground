# -*- coding: utf-8 -*-
"""Standalone HTML reports: one self-contained .html file (inline CSS, JS, SVG charts and
base64 images) that opens in any browser, offline, in light or dark theme.

    r = htmlreport.Report('Clash summary', subtitle='Level 3', meta=[('Model', 'Hospital.nwf')])
    r.kpis([('Clashes', 1270, None), ('New', 412, 'bad'), ('Resolved', 96, 'good')])
    r.section('By status', intro='Every clash test in the model.')
    r.bar_chart(['New', 'Active', 'Resolved'], [412, 300, 96], title='Clashes by status')
    r.table(['Name', 'Status', 'Distance'], rows,
            cell_html=set((i, 1) for i in range(len(rows))))   # status column holds r.status(...)
    r.save(path)

The look is the pyNavis design system on the web: Segoe UI Variable, 13px body, solid
surfaces, hairlines, accent only on links and the focus ring, status tags as the only
chip, tabular right-aligned numbers, six categorical chart colours validated for colour
vision deficiency in both themes. No gradients, no shadows on content, no emoji.

Every text argument is HTML-escaped. The only ways to inject markup are r.html(),
cell_html and the strings returned by status()/link(), all of which you control.
Output is deterministic: the same calls produce the same bytes (no clock, no random ids).
"""
import base64
import datetime
import io
import json
import math
import os
import re

from namo import png as _png

TONES = ('good', 'warn', 'bad', 'info', 'neutral', 'new', 'active', 'reviewed', 'approved',
         'resolved')
CLASH_STATUS_TONES = {'new': 'new', 'active': 'active', 'reviewed': 'reviewed',
                      'approved': 'approved', 'resolved': 'resolved'}
SERIES_COLORS = 6
_CHAR_W = 0.58          # average glyph width as a fraction of the font size (Segoe UI)
_CTRL = re.compile(u'[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]')
_URL_SCHEME = re.compile(u'^[A-Za-z][A-Za-z0-9+.\\-]+:')
_NUMERIC_TEXT = re.compile(u'^[-+]?(\\d+\\.?\\d*|\\.\\d+)([eE][-+]?\\d+)?%?$')

# ---------------------------------------------------------------------------
# Escaping and formatting
# ---------------------------------------------------------------------------


def escape(text):
    """HTML-escape any value for element text or a quoted attribute (None -> '').
    Numbers become their shortest text (0.1 -> '0.1' on both engines)."""
    if text is None:
        return u''
    if not isinstance(text, str):
        text = _short_num(text) if _finite(text) else u'%s' % (text,)
    text = _CTRL.sub(u'', text)
    return (text.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')
            .replace(u'"', u'&quot;').replace(u"'", u'&#39;'))


def _escape_lines(text):
    return escape(text).replace(u'\r\n', u'\n').replace(u'\r', u'\n').replace(u'\n', u'<br>')


def _short_num(value):
    """Shortest round-trip text for a number (identical on CPython and IronPython)."""
    if isinstance(value, int):
        return u'%d' % value
    for precision in (15, 16, 17):
        text = u'%.*g' % (precision, value)
        if float(text) == value:
            return text
    return text


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and \
        value == value and value not in (float('inf'), float('-inf'))


def format_number(value, decimals=2):
    """1234567 -> '1,234,567'; 1234.5 -> '1,234.5'; up to `decimals` places, trailing
    zeros trimmed; None, NaN and infinities -> ''."""
    if value is None or isinstance(value, bool) or not _finite(value):
        return u''
    if isinstance(value, int):
        return u'{:,}'.format(value)
    rounded = round(value, decimals)
    if rounded == int(rounded) and abs(rounded) < 1e15:
        return u'{:,}'.format(int(rounded))
    text = (u'{:,.%df}' % decimals).format(rounded)
    if u'.' in text:
        text = text.rstrip(u'0').rstrip(u'.')
    return text


def _fmt(value, value_format):
    if value is None:
        return u''
    if value_format is None:
        return format_number(value)
    if callable(value_format):
        return u'%s' % (value_format(value),)
    return value_format.format(value)


def _number(value):
    """Chart input -> finite float, or None for missing/bad values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float('inf'), float('-inf')):
        return None
    return number


def _check_tone(tone):
    if tone is None:
        return None
    key = (u'%s' % tone).strip().lower()
    if key not in TONES:
        raise ValueError('unknown tone %r (use %s)' % (tone, ', '.join(TONES)))
    return key


def tone_for_status(status):
    """Chip tone for a Navisworks clash status ('New' -> 'new'...), else 'neutral'."""
    if status is None:
        return 'neutral'
    return CLASH_STATUS_TONES.get((u'%s' % status).strip().lower(), 'neutral')


def status_chip(text, tone=None):
    """HTML for a status tag (the only chip in the design system).

    tone: 'good'|'warn'|'bad'|'info'|'neutral' or a clash status ('new', 'active',
    'reviewed', 'approved', 'resolved'); None picks the clash-status tone from the
    text itself, else neutral.
    """
    tone = _check_tone(tone) or tone_for_status(text)
    return u'<span class="chip t-%s">%s</span>' % (tone, escape(text))


def file_url(path):
    """A Windows/UNC/relative file path -> a URL a browser can open from the report."""
    text = (u'%s' % path).strip()
    if _URL_SCHEME.match(text):         # http:, https:, mailto:, file: (a drive letter is 1 char)
        return text
    safe = text.replace(u'\\', u'/').replace(u'%', u'%25').replace(u' ', u'%20').replace(u'#', u'%23')
    if re.match(u'^[A-Za-z]:/', safe):
        return u'file:///' + safe
    if safe.startswith(u'//'):
        return u'file:' + safe
    return safe


def link(href, text=None):
    """HTML for a link (escaped). Paths become file:// URLs; javascript: is refused."""
    url = file_url(href)
    if url.lower().lstrip().startswith(u'javascript:'):
        raise ValueError('javascript: links are not allowed')
    return u'<a href="%s">%s</a>' % (escape(url), escape(href if text is None else text))


def _text_w(text, size=12):
    return len(text) * size * _CHAR_W


def _clip(text, max_px, size=12):
    """Text cut with an ellipsis so its estimated width fits max_px."""
    text = u'%s' % (text,)
    if _text_w(text, size) <= max_px:
        return text
    keep = max(1, int(max_px / (size * _CHAR_W)) - 1)
    return text[:keep].rstrip() + u'…'


def _p(value):
    """Coordinate text: 1 decimal, no trailing zeros."""
    text = u'%.1f' % value
    if text.endswith(u'.0'):
        text = text[:-2]
    return u'0' if text == u'-0' else text


def _nice_ticks(lo, hi, count=5, integers=False):
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        if hi == 0:
            hi = 1.0
        else:
            lo, hi = (0.0, hi) if hi > 0 else (hi, 0.0)
    raw = (hi - lo) / float(max(1, count - 1))
    magnitude = 10 ** math.floor(math.log10(raw))
    step = magnitude * 10
    for factor in (1, 2, 2.5, 5, 10):
        if factor * magnitude >= raw:
            step = factor * magnitude
            break
    if integers and step < 1:
        step = 1.0
    start = math.floor(lo / step) * step
    end = math.ceil(hi / step) * step
    ticks = []
    value = start
    while value <= end + step * 1e-9 and len(ticks) < 50:
        ticks.append(round(value, 10))
        value += step
    return ticks


# ---------------------------------------------------------------------------
# Static CSS and JS
# ---------------------------------------------------------------------------

_LIGHT = u"""
  --paper:#FFFFFF; --surface:#F7F7F7; --line:#E0E0E0; --frame:#A6A6A6; --ink:#1A1A1A;
  --muted:#6B6B6B; --accent:#005FB8; --hover:#F5F5F5;
  --good:#0F6C33; --good-wash:#F2FAF5; --good-line:#BFE0CC;
  --warn:#8A6A00; --warn-wash:#FEF9E6; --warn-line:#DEC88F;
  --bad:#C50F1F; --bad-wash:#FDF3F4; --bad-line:#E8C4C8;
  --info:#005FB8; --info-wash:#F2F7FC; --info-line:#BCD6EE;
  --neutral:#5C5C5C; --neutral-wash:#F7F7F7; --neutral-line:#D6D6D6;
  --active:#A44D00; --active-wash:#FDF4EC; --active-line:#EDC9A8;
  --resolved:#6F6100; --resolved-wash:#FBF8E1; --resolved-line:#DDD18A;
  --c1:#2A78D6; --c2:#D95926; --c3:#199E70; --c4:#C98500; --c5:#D55181; --c6:#008300;
  --other:#A6A6A6;
  --h1:#CDE2FB; --h2:#9EC5F4; --h3:#6DA7EC; --h4:#3987E5; --h5:#256ABF; --h6:#184F95; --h7:#0D366B;
  --h1t:#1A1A1A; --h2t:#1A1A1A; --h3t:#1A1A1A; --h4t:#0B0B0B; --h5t:#FFFFFF; --h6t:#FFFFFF; --h7t:#FFFFFF;
"""

_DARK = u"""
  --paper:#202020; --surface:#2B2B2B; --line:#3D3D3D; --frame:#6E6E6E; --ink:#E8E8E8;
  --muted:#9A9A9A; --accent:#4CC2FF; --hover:#2B2B2B;
  --good:#6CCB8A; --good-wash:#1F2E24; --good-line:#3B6B4B;
  --warn:#E5C15D; --warn-wash:#3F3A1F; --warn-line:#8B7E42;
  --bad:#FF7B72; --bad-wash:#3B2A2B; --bad-line:#6E3E41;
  --info:#7FBDF5; --info-wash:#1E2B38; --info-line:#3B5E80;
  --neutral:#B5B5B5; --neutral-wash:#2B2B2B; --neutral-line:#4A4A4A;
  --active:#F0A35E; --active-wash:#3A2C1F; --active-line:#7A5634;
  --resolved:#D9CB6A; --resolved-wash:#34321C; --resolved-line:#77703A;
  --c1:#3987E5; --c2:#D95926; --c3:#199E70; --c4:#C98500; --c5:#D55181; --c6:#008300;
  --other:#6E6E6E;
  --h1:#0D366B; --h2:#104281; --h3:#184F95; --h4:#256ABF; --h5:#3987E5; --h6:#6DA7EC; --h7:#9EC5F4;
  --h1t:#FFFFFF; --h2t:#FFFFFF; --h3t:#FFFFFF; --h4t:#FFFFFF; --h5t:#0B0B0B; --h6t:#0B0B0B; --h7t:#0B0B0B;
"""

_CSS = u""":root {""" + _LIGHT + u"""  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {""" + _DARK + u"""  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: "Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", system-ui,
    -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 13px; line-height: 1.5;
}
.page { max-width: 1240px; margin: 0 auto; padding: 32px 24px 48px; }
h1 { font-size: 20px; font-weight: 600; line-height: 1.3; margin: 0; }
h2 { font-size: 16px; font-weight: 600; line-height: 1.35; margin: 32px 0 4px;
  padding-top: 24px; border-top: 1px solid var(--line); }
h3 { font-size: 14px; font-weight: 600; margin: 0 0 8px; }
p { margin: 8px 0; max-width: 90ch; }
ul.bullets { margin: 8px 0; padding-left: 20px; max-width: 90ch; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; border-radius: 4px; }
.head .sub { color: var(--muted); margin: 4px 0 0; }
dl.meta { display: flex; flex-wrap: wrap; gap: 8px 32px; margin: 16px 0 0; }
dl.meta dt { font-size: 12px; color: var(--muted); margin: 0; }
dl.meta dd { margin: 0; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
nav.toc { margin: 24px 0 0; }
nav.toc ol { display: flex; flex-wrap: wrap; gap: 4px 24px; margin: 0; padding: 0; list-style: none; }
.intro { color: var(--muted); margin: 0 0 12px; }
.note { color: var(--muted); font-size: 12px; border-left: 3px solid var(--line);
  padding: 2px 0 2px 10px; margin: 12px 0; max-width: 90ch; }
.kpis { display: flex; flex-wrap: wrap; gap: 16px 48px; margin: 24px 0; }
.kpi .v { font-size: 28px; font-weight: 300; line-height: 1.2; letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums; }
.kpi .l { font-size: 12px; color: var(--muted); }
.kpi .d { font-size: 12px; color: var(--muted); }
.kpi.t-good .v, .kpi.t-approved .v { color: var(--good); }
.kpi.t-warn .v { color: var(--warn); }
.kpi.t-bad .v, .kpi.t-new .v { color: var(--bad); }
.kpi.t-info .v, .kpi.t-reviewed .v { color: var(--info); }
.kpi.t-active .v { color: var(--active); }
.kpi.t-resolved .v { color: var(--resolved); }
.kpi.t-neutral .v { color: var(--muted); }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0);
  white-space: nowrap; }
.chip { display: inline-block; font-size: 11px; font-weight: 500; line-height: 16px;
  padding: 0 7px; border-radius: 3px; border: 1px solid var(--neutral-line);
  background: var(--neutral-wash); color: var(--neutral); white-space: nowrap; }
.chip.t-good, .chip.t-approved { color: var(--good); background: var(--good-wash); border-color: var(--good-line); }
.chip.t-warn { color: var(--warn); background: var(--warn-wash); border-color: var(--warn-line); }
.chip.t-bad, .chip.t-new { color: var(--bad); background: var(--bad-wash); border-color: var(--bad-line); }
.chip.t-info, .chip.t-reviewed { color: var(--info); background: var(--info-wash); border-color: var(--info-line); }
.chip.t-active { color: var(--active); background: var(--active-wash); border-color: var(--active-line); }
.chip.t-resolved { color: var(--resolved); background: var(--resolved-wash); border-color: var(--resolved-line); }
.block { margin: 16px 0 24px; }
.tools { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: 0 0 8px; }
.tools input { height: 32px; width: 280px; max-width: 100%; padding: 0 10px; font: inherit;
  color: var(--ink); background: var(--paper); border: 1px solid var(--frame); border-radius: 4px; }
.tools input::placeholder { color: var(--muted); }
.tools input:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
.count { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.scroll { max-height: 72vh; overflow: auto; border: 1px solid var(--frame); border-radius: 4px; }
table.data { border-collapse: separate; border-spacing: 0; width: 100%; }
table.data th { position: sticky; top: 0; z-index: 1; background: var(--surface);
  text-align: left; font-size: 12px; font-weight: 500; color: var(--muted);
  border-bottom: 1px solid var(--line); padding: 7px 12px; white-space: nowrap; }
table.data th.btn { padding: 0; }
table.data th button { display: block; width: 100%; margin: 0; padding: 7px 12px; border: 0;
  background: transparent; color: inherit; font: inherit; text-align: inherit; cursor: pointer; }
table.data th button:hover { color: var(--ink); }
table.data th .pl { display: none; }
table.data th[aria-sort="ascending"] button::after { content: " \\2191"; }
table.data th[aria-sort="descending"] button::after { content: " \\2193"; }
table.data th[aria-sort] button { color: var(--ink); }
table.data td { padding: 6px 12px; border-bottom: 1px solid var(--line); vertical-align: top;
  overflow-wrap: anywhere; }
table.data tbody tr:last-child td { border-bottom: 0; }
table.data tbody tr:hover td { background: var(--hover); }
table.data .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
table.data td.num { color: var(--muted); }
table.data.toned td:first-child { border-left: 3px solid transparent; }
""" + u''.join(u"""table.data tr.t-%s td { background: var(--%s-wash); }
table.data tr.t-%s td:first-child { border-left-color: var(--%s); }
""" % (t, c, t, c) for t, c in (
    ('good', 'good'), ('warn', 'warn'), ('bad', 'bad'), ('info', 'info'), ('neutral', 'neutral'),
    ('new', 'bad'), ('active', 'active'), ('reviewed', 'info'), ('approved', 'good'),
    ('resolved', 'resolved'))) + u""".empty { color: var(--muted); padding: 12px; }
.trunc { color: var(--muted); font-size: 12px; margin: 6px 0 0; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart svg text { font-family: inherit; font-size: 12px; fill: var(--muted); }
.chart svg text.lbl, .chart svg text.val { fill: var(--ink); }
.chart svg text.val, .chart svg text.tick { font-variant-numeric: tabular-nums; }
.chart svg text.big { font-size: 20px; font-weight: 300; fill: var(--ink); }
.chart .grid { stroke: var(--line); stroke-width: 1; }
.chart .axis { stroke: var(--frame); stroke-width: 1; }
.chart .xh { stroke: var(--frame); stroke-width: 1; visibility: hidden; }
.chart .hit { fill: transparent; }
.chart .dot { stroke: var(--paper); stroke-width: 2; }
.chart path.ln { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.chart path.ln.lo { stroke-width: 1.5; }
""" + u''.join(u""".chart .s%d { fill: var(--c%d); }
.chart .k%d { stroke: var(--c%d); }
""" % (i, i, i, i) for i in range(1, SERIES_COLORS + 1)) + u""".chart .so { fill: var(--other); }
.chart .ko { stroke: var(--other); }
""" + u''.join(u""".chart .tn-%s { fill: var(--%s); }
""" % (t, c) for t, c in (
    ('good', 'good'), ('warn', 'warn'), ('bad', 'bad'), ('info', 'info'), ('neutral', 'neutral'),
    ('new', 'bad'), ('active', 'active'), ('reviewed', 'info'), ('approved', 'good'),
    ('resolved', 'resolved'))) + u""".chart rect.h0 { fill: var(--surface); }
.chart svg text.h0 { fill: var(--muted); }
.chart svg text.hv { font-variant-numeric: tabular-nums; }
""" + u''.join(u""".chart rect.h%d { fill: var(--h%d); }
.chart svg text.h%d { fill: var(--h%dt); }
""" % (i, i, i, i) for i in range(1, 8)) + u"""ul.legend { display: flex; flex-wrap: wrap; gap: 4px 20px; margin: 0 0 8px; padding: 0;
  list-style: none; font-size: 12px; }
.key { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
.key.line { width: 16px; height: 2px; border-radius: 1px; vertical-align: 3px; }
""" + u''.join(u""".key.s%d { background: var(--c%d); }
""" % (i, i) for i in range(1, SERIES_COLORS + 1)) + u""".key.so { background: var(--other); }
""" + u''.join(u""".key.tn-%s { background: var(--%s); }
""" % (t, c) for t, c in (
    ('good', 'good'), ('warn', 'warn'), ('bad', 'bad'), ('info', 'info'), ('neutral', 'neutral'),
    ('new', 'bad'), ('active', 'active'), ('reviewed', 'info'), ('approved', 'good'),
    ('resolved', 'resolved'))) + u""".key.heat { width: 18px; height: 12px; margin: 0; border-radius: 0; }
""" + u''.join(u""".key.h%d { background: var(--h%d); }
""" % (i, i) for i in range(1, 8)) + u""".heatkey { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted);
  margin: 8px 0 0; font-variant-numeric: tabular-nums; }
.heatkey span.ramp { display: inline-flex; gap: 2px; }
.pie-body { display: flex; flex-wrap: wrap; align-items: center; gap: 16px 40px; }
.pie-body svg { width: 200px; max-width: 200px; flex: none; }
table.lg { border-collapse: collapse; font-size: 13px; }
table.lg td { padding: 4px 16px 4px 0; border-bottom: 1px solid var(--line); }
table.lg tr:last-child td { border-bottom: 0; }
table.lg td.num { text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }
.hm { overflow-x: auto; }
.hm svg { width: auto; max-width: none; }
details.data { margin: 8px 0 0; }
details.data summary { color: var(--muted); font-size: 12px; cursor: pointer; width: max-content; }
details.data table.data { margin-top: 8px; border: 1px solid var(--frame); border-radius: 4px; }
details.data table.data th { position: static; }
figure.img { margin: 16px 0 24px; }
figure.img img { display: block; max-width: 100%; height: auto; border-radius: 4px; }
figcaption { color: var(--muted); font-size: 12px; margin-top: 6px; }
.gal { display: grid; grid-template-columns: repeat(var(--cols, 4), minmax(0, 1fr)); gap: 16px;
  margin: 16px 0 24px; }
.gal figure { margin: 0; min-width: 0; }
.gal button.zoom { display: block; width: 100%; padding: 0; border: 1px solid var(--line);
  border-radius: 4px; background: var(--surface); cursor: zoom-in; overflow: hidden; }
.gal button.zoom img { display: block; width: 100%; height: auto; }
.gal figcaption { overflow-wrap: anywhere; }
#tip { position: fixed; z-index: 10; pointer-events: none; max-width: 340px;
  background: var(--paper); color: var(--ink); border: 1px solid var(--frame); border-radius: 4px;
  padding: 6px 10px; font-size: 12px; white-space: pre-line; font-variant-numeric: tabular-nums;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18); }
#lb { position: fixed; inset: 0; z-index: 20; background: var(--paper); display: flex;
  flex-direction: column; padding: 16px 24px 24px; }
#lb[hidden], #tip[hidden] { display: none; }
#lb .bar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
#lb .bar .cap { flex: 1; min-width: 0; color: var(--muted); overflow-wrap: anywhere; }
#lb button { height: 32px; min-width: 32px; padding: 0 12px; font: inherit; color: var(--ink);
  background: var(--paper); border: 1px solid var(--frame); border-radius: 4px; cursor: pointer; }
#lb .stage { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; }
#lb img { max-width: 100%; max-height: 100%; object-fit: contain; }
footer.foot { margin-top: 48px; padding-top: 12px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 12px; }
@media (max-width: 800px) {
  .page { padding: 24px 16px 40px; }
  .gal { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media print {
  :root {""" + _LIGHT + u"""    color-scheme: light;
  }
  body { font-size: 11px; }
  .page { max-width: none; padding: 0; }
  .tools, #tip, #lb, details.data { display: none !important; }
  .scroll { max-height: none; overflow: visible; }
  table.data th { position: static; }
  thead { display: table-header-group; }
  tr, .kpi, .chart, figure, .gal figure { break-inside: avoid; }
  h2, h3 { break-after: avoid; }
  .pb { break-before: page; }
  a { color: inherit; text-decoration: underline; }
  .gal button.zoom { border: 0; }
  table.data th button { display: none; }
  table.data th .pl { display: block; padding: 7px 12px; }
}
"""

_JS = u"""(function () {
  'use strict';
  var tip = document.getElementById('tip');
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }
  function fmt(n) { return String(n).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ','); }
  function closest(el, sel) {
    while (el && el.nodeType === 1) { if (el.matches(sel)) { return el; } el = el.parentNode; }
    return null;
  }
  function showTip(e, text) {
    if (!tip) { return; }
    tip.textContent = text;
    tip.hidden = false;
    var x = e.clientX + 14, y = e.clientY + 14;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    if (x + w > window.innerWidth - 8) { x = Math.max(8, e.clientX - w - 14); }
    if (y + h > window.innerHeight - 8) { y = Math.max(8, e.clientY - h - 14); }
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  function hideTip() { if (tip) { tip.hidden = true; } }
  document.addEventListener('mousemove', function (e) {
    var el = closest(e.target, '[data-tip]');
    if (el) { showTip(e, el.getAttribute('data-tip')); }
    else if (!closest(e.target, 'svg.line')) { hideTip(); }
  });
  document.addEventListener('scroll', hideTip, true);

  var collator = (window.Intl && Intl.Collator) ?
    new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' }) : null;
  function cmpText(a, b) { return collator ? collator.compare(a, b) : (a < b ? -1 : (a > b ? 1 : 0)); }
  function keyOf(td) {
    if (!td) { return ''; }
    var v = td.getAttribute('data-v');
    return v === null ? td.textContent.replace(/^\\s+|\\s+$/g, '') : v;
  }
  function num(s) {
    var t = s.replace(/[,\\s\\u00a0]/g, '');
    return /^[-+]?(\\d+\\.?\\d*|\\.\\d+)(e[-+]?\\d+)?%?$/i.test(t) ? parseFloat(t) : NaN;
  }
  each(document.querySelectorAll('div.tbl'), function (box) {
    var table = box.querySelector('table.data');
    if (!table || !table.tBodies.length) { return; }
    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    each(rows, function (r, i) { r._i = i; });
    var total = rows.length;
    var count = box.querySelector('.count');
    function update() {
      if (!count) { return; }
      var shown = 0;
      each(rows, function (r) { if (!r.hidden) { shown += 1; } });
      count.textContent = shown === total ? fmt(total) + (total === 1 ? ' row' : ' rows')
        : fmt(shown) + ' of ' + fmt(total) + ' rows';
    }
    var input = box.querySelector('input.filter');
    if (input) {
      input.addEventListener('input', function () {
        var terms = input.value.toLowerCase().split(/\\s+/).filter(function (t) { return t; });
        each(rows, function (r) {
          if (r._t === undefined) { r._t = r.textContent.toLowerCase(); }
          var ok = true;
          for (var k = 0; k < terms.length; k += 1) {
            if (r._t.indexOf(terms[k]) < 0) { ok = false; break; }
          }
          r.hidden = !ok;
        });
        update();
      });
    }
    if (table.getAttribute('data-sortable') !== '1' || !table.tHead) { return; }
    var heads = table.tHead.rows[0].cells;
    each(heads, function (th, c) {
      var button = th.querySelector('button');
      if (!button) { return; }
      button.addEventListener('click', function () {
        var dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
        each(heads, function (o) { o.removeAttribute('aria-sort'); });
        th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
        var keyed = rows.map(function (r) {
          var k = keyOf(r.cells[c]);
          return { r: r, k: k, n: num(k) };
        });
        keyed.sort(function (a, b) {
          if (a.k === '' || b.k === '') {
            if (a.k === b.k) { return a.r._i - b.r._i; }
            return a.k === '' ? 1 : -1;
          }
          var d = (!isNaN(a.n) && !isNaN(b.n)) ? a.n - b.n : cmpText(a.k, b.k);
          return d === 0 ? a.r._i - b.r._i : d * dir;
        });
        var frag = document.createDocumentFragment();
        each(keyed, function (x) { frag.appendChild(x.r); });
        tbody.appendChild(frag);
      });
    });
  });

  each(document.querySelectorAll('svg.line'), function (svg) {
    var d;
    try { d = JSON.parse(svg.getAttribute('data-d')); } catch (err) { return; }
    var xh = svg.querySelector('.xh');
    svg.addEventListener('mousemove', function (e) {
      var m = svg.getScreenCTM();
      if (!m || !d.labels.length) { return; }
      var pt = svg.createSVGPoint();
      pt.x = e.clientX; pt.y = e.clientY;
      var p = pt.matrixTransform(m.inverse());
      var i = d.step > 0 ? Math.round((p.x - d.x0) / d.step) : 0;
      i = Math.max(0, Math.min(d.labels.length - 1, i));
      var x = d.x0 + i * d.step;
      xh.setAttribute('x1', x); xh.setAttribute('x2', x);
      xh.style.visibility = 'visible';
      var lines = [d.labels[i]];
      each(d.series, function (s) { lines.push(s[0] + ': ' + (s[1][i] === null ? 'no value' : s[1][i])); });
      showTip(e, lines.join('\\n'));
    });
    svg.addEventListener('mouseleave', function () { xh.style.visibility = 'hidden'; hideTip(); });
  });

  var lb = document.getElementById('lb');
  if (lb) {
    var lbImg = lb.querySelector('img'), lbCap = lb.querySelector('.cap');
    var list = [], index = 0, opener = null;
    var show = function (i) {
      index = (i + list.length) % list.length;
      var b = list[index], img = b.querySelector('img');
      lbImg.src = img.src; lbImg.alt = img.alt;
      var cap = b.getAttribute('data-cap') || '';
      var where = (index + 1) + ' of ' + list.length;
      lbCap.textContent = cap ? cap + ' (' + where + ')' : 'Image ' + where;
    };
    var close = function () {
      lb.hidden = true; lbImg.removeAttribute('src');
      if (opener) { opener.focus(); }
    };
    document.addEventListener('click', function (e) {
      var b = closest(e.target, 'button.zoom');
      if (!b) { return; }
      list = Array.prototype.slice.call(closest(b, '.gal').querySelectorAll('button.zoom'));
      opener = b;
      show(list.indexOf(b));
      lb.hidden = false;
      lb.querySelector('.close').focus();
    });
    lb.querySelector('.close').addEventListener('click', close);
    lb.querySelector('.prev').addEventListener('click', function () { show(index - 1); });
    lb.querySelector('.next').addEventListener('click', function () { show(index + 1); });
    document.addEventListener('keydown', function (e) {
      if (lb.hidden) { return; }
      if (e.key === 'Escape') { close(); }
      else if (e.key === 'ArrowRight') { show(index + 1); }
      else if (e.key === 'ArrowLeft') { show(index - 1); }
    });
  }
}());
"""


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

_EXT_MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
             '.bmp': 'image/bmp', '.webp': 'image/webp', '.svg': 'image/svg+xml'}


def _load_image(path_or_bytes):
    """-> (data URI, (w, h) or None, default alt text)."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
        name = u''
        ext = u''
    else:
        handle = open(path_or_bytes, 'rb')
        try:
            data = handle.read()
        finally:
            handle.close()
        name = os.path.basename(u'%s' % path_or_bytes)
        ext = os.path.splitext(name)[1].lower()
    mime = _png.mime_type(data) or _EXT_MIME.get(ext)
    if mime is None:
        raise ValueError('not an image the report can embed (PNG, JPEG, GIF, BMP, WEBP or SVG)')
    encoded = base64.b64encode(data)
    if not isinstance(encoded, str):
        encoded = encoded.decode('ascii')
    return u'data:%s;base64,%s' % (mime, encoded), _png.image_size(data), name


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class Report(object):
    """A report built block by block, in call order. See the module docstring."""

    def __init__(self, title, subtitle=None, meta=None, toc=None, footer=None, lang='en'):
        """title: the page heading and browser title. subtitle: one muted line.
        meta: [(label, value)] shown under the title. toc: True/False, or None for a
        contents list when there are 4 or more sections. footer: text for the small
        footer line ('' for none; None for 'Made with pyNavis Playground')."""
        self.title = u'%s' % (title,)
        self.subtitle = subtitle
        self.meta = list(meta or [])
        self.toc = toc
        self.footer = footer
        self.lang = lang
        self._blocks = []
        self._sections = []
        self._ids = 0
        self._uses_tip = False
        self._uses_gallery = False

    def _next_id(self, prefix):
        self._ids += 1
        return u'%s%d' % (prefix, self._ids)

    # --- text blocks -----------------------------------------------------------------

    def kpis(self, items):
        """A row of readouts: [(label, value, tone_or_None), ...]; an optional 4th item
        is a muted detail line. Numbers get thousands separators."""
        parts = [u'<div class="kpis">']
        for item in items:
            item = tuple(item)
            label = item[0]
            value = item[1] if len(item) > 1 else None
            tone = _check_tone(item[2]) if len(item) > 2 else None
            detail = item[3] if len(item) > 3 else None
            shown = format_number(value) if _finite(value) else escape(value)
            cls = u'kpi t-%s' % tone if tone else u'kpi'
            parts.append(u'<div class="%s"><div class="l">%s</div><div class="v">%s</div>%s</div>' % (
                cls, escape(label), shown,
                u'<div class="d">%s</div>' % escape(detail) if detail is not None else u''))
        parts.append(u'</div>')
        self._blocks.append(u''.join(parts))

    def section(self, title, intro=None):
        """Start a section: a heading with a hairline above, plus an optional muted intro.
        Returns the section's anchor id ('s1', 's2'...)."""
        sid = self._next_id(u's')
        self._sections.append((sid, u'%s' % (title,)))
        html = u'<h2 id="%s">%s</h2>' % (sid, escape(title))
        if intro:
            html += u'<p class="intro">%s</p>' % _escape_lines(intro)
        self._blocks.append(html)
        return sid

    def text(self, paragraph):
        """A paragraph of escaped text (newlines become line breaks)."""
        self._blocks.append(u'<p>%s</p>' % _escape_lines(paragraph))

    def note(self, text):
        """A muted aside with a hairline rule on the left (method notes, caveats)."""
        self._blocks.append(u'<p class="note">%s</p>' % _escape_lines(text))

    def bullets(self, items):
        """A plain bulleted list of escaped strings."""
        self._blocks.append(u'<ul class="bullets">%s</ul>'
                            % u''.join(u'<li>%s</li>' % _escape_lines(i) for i in items))

    def html(self, trusted_html, tooltips=False):
        """Raw HTML you built and trust (never user or model data unescaped).
        tooltips=True (or any data-tip= attribute in it) adds the shared tooltip
        element, so custom charts get hover tips without a built-in chart."""
        text = u'%s' % (trusted_html,)
        if tooltips or u'data-tip=' in text:
            self._uses_tip = True
        self._blocks.append(text)

    def page_break(self):
        """Start a new page when the report is printed."""
        self._blocks.append(u'<div class="pb"></div>')

    def status(self, text, tone=None):
        """HTML for a status chip (to use in cell_html cells or html()); see status_chip."""
        return status_chip(text, tone)

    # --- tables ----------------------------------------------------------------------

    def table(self, headers, rows, numeric=None, sortable=True, filterable=True, row_tones=None,
              cell_html=None, caption=None, max_rows=None):
        """A data table with sticky header, click-to-sort headers (numeric aware), a
        filter box and a row count.

        numeric: None (auto: every non-empty cell is a number or numeric text) or an
        iterable of column indexes. row_tones: per-row tone or None (a tinted row with a
        coloured rail). cell_html: set of (row, col) whose value is trusted HTML (e.g.
        r.status(...)). max_rows: render only the first N rows and say so.
        """
        headers = [u'%s' % (h,) for h in headers]
        rows = [list(r) for r in rows]
        total = len(rows)
        if max_rows is not None and total > max_rows:
            rows = rows[:max_rows]
        trusted = set(cell_html or ())
        tones = list(row_tones or [])
        tid = self._next_id(u't')
        num_cols = self._numeric_columns(headers, rows, numeric, trusted)
        parts = [u'<div class="block tbl" id="%s">' % tid]
        if caption:
            parts.append(u'<h3 id="%s-cap">%s</h3>' % (tid, escape(caption)))
        if filterable and rows:
            label = caption or (self._sections[-1][1] if self._sections else u'this table')
            parts.append(u'<div class="tools"><input type="search" class="filter" '
                         u'placeholder="Filter rows" aria-label="Filter rows in %s">'
                         u'<span class="count">%s</span></div>'
                         % (escape(label), _rows_text(len(rows))))
        parts.append(self._table_html(headers, rows, num_cols, trusted, tones,
                                      sortable and bool(rows), tid if caption else None))
        if total > len(rows):
            parts.append(u'<p class="trunc">Showing the first %s of %s rows.</p>'
                         % (format_number(len(rows)), format_number(total)))
        parts.append(u'</div>')
        self._blocks.append(u''.join(parts))
        return tid

    @staticmethod
    def _numeric_columns(headers, rows, numeric, trusted):
        if numeric is not None:
            return set(int(c) for c in numeric)
        cols = set()
        for col in range(len(headers)):
            seen = False
            ok = True
            for r, row in enumerate(rows):
                value = row[col] if col < len(row) else None
                if value is None or value == u'' or (r, col) in trusted:
                    continue
                seen = True
                if isinstance(value, bool):
                    ok = False
                elif isinstance(value, (int, float)):
                    continue
                elif isinstance(value, str) and _NUMERIC_TEXT.match(
                        value.replace(u',', u'').replace(u' ', u'').replace(u' ', u'')):
                    continue
                else:
                    ok = False
                if not ok:
                    break
            if seen and ok:
                cols.add(col)
        return cols

    def _table_html(self, headers, rows, num_cols, trusted, tones, sortable, label_id):
        decimals = _column_decimals(rows, num_cols, trusted)
        toned = any(tones)
        cls = u'data toned' if toned else u'data'
        attrs = u' data-sortable="1"' if sortable else u''
        if label_id:
            attrs += u' aria-labelledby="%s-cap"' % label_id
        parts = [u'<div class="scroll"><table class="%s"%s><thead><tr>' % (cls, attrs)]
        for col, header in enumerate(headers):
            num = u' num' if col in num_cols else u''
            if sortable:
                # the aria-hidden copy is what prints: Chromium leaves buttons blank in
                # the table header it repeats on every printed page
                parts.append(u'<th scope="col" class="btn%s"><button type="button">%s</button>'
                             u'<span class="pl" aria-hidden="true">%s</span></th>'
                             % (num, escape(header), escape(header)))
            else:
                parts.append(u'<th scope="col"%s>%s</th>' % (u' class="num"' if num else u'',
                                                             escape(header)))
        parts.append(u'</tr></thead><tbody>')
        if not rows:
            parts.append(u'<tr><td class="empty" colspan="%d">No rows.</td></tr>' % max(1, len(headers)))
        for r, row in enumerate(rows):
            tone = _check_tone(tones[r]) if r < len(tones) else None
            parts.append(u'<tr class="t-%s">' % tone if tone else u'<tr>')
            for col in range(len(headers)):
                value = row[col] if col < len(row) else None
                content, sort_key = _cell(value, (r, col) in trusted, decimals.get(col))
                cell_cls = u' class="num"' if col in num_cols else u''
                data_v = u' data-v="%s"' % escape(sort_key) if sort_key is not None else u''
                parts.append(u'<td%s%s>%s</td>' % (cell_cls, data_v, content))
            parts.append(u'</tr>')
        parts.append(u'</tbody></table></div>')
        return u''.join(parts)

    def _data_table(self, headers, rows):
        """Plain table for a chart's 'Data' disclosure (not sortable, no filter)."""
        num_cols = self._numeric_columns(headers, rows, None, set())
        return (u'<details class="data"><summary>Data</summary>%s</details>'
                % self._table_html(headers, rows, num_cols, set(), [], False, None))

    # --- charts ----------------------------------------------------------------------

    def _chart_block(self, kind, title, body, data_headers, data_rows, extra=u''):
        cid = self._next_id(u'c')
        self._uses_tip = True
        parts = [u'<div class="block chart chart-%s" id="%s">' % (kind, cid)]
        if title:
            parts.append(u'<h3>%s</h3>' % escape(title))
        parts.append(body)
        parts.append(extra)
        parts.append(self._data_table(data_headers, data_rows))
        parts.append(u'</div>')
        self._blocks.append(u''.join(parts))
        return cid

    def bar_chart(self, labels, values, title=None, horizontal=True, value_format=None, tones=None,
                  value_label=u'Value'):
        """One-series bar chart (horizontal by default; horizontal=False for columns).

        Every bar takes the first chart colour; tones (a per-bar tone list) colours bars
        by status instead. value_format: None (thousands separators), a format string
        like '{:.1f}' or a function. Missing values draw no bar."""
        labels = [_label(l) for l in labels]
        values = [_number(v) for v in list(values)[:len(labels)]]
        labels = labels[:len(values)]
        tones = [(_check_tone(t) if t else None) for t in (tones or [])]
        texts = [_fmt(v, value_format) for v in values]
        if not labels:
            body = _empty_svg(u'No data')
        elif horizontal:
            body = _hbar_svg(labels, values, texts, tones, title)
        else:
            body = _vbar_svg(labels, values, texts, tones, title)
        return self._chart_block(u'bar', title, body, [u'Label', value_label],
                                 [[l, t] for l, t in zip(labels, texts)])

    def line_chart(self, labels, series, title=None, value_format=None):
        """Line chart over shared x labels. series: [(name, values)] in legend order
        (first six get the categorical colours, the rest draw in grey). None values
        leave gaps. Hover shows a crosshair with every series' value."""
        labels = [_label(l) for l in labels]
        clean = []
        for name, vals in series:
            vals = [_number(v) for v in list(vals)[:len(labels)]]
            vals += [None] * (len(labels) - len(vals))
            clean.append((_label(name), vals))
        texts = [[(_fmt(v, value_format) if v is not None else None) for v in vals]
                 for _n, vals in clean]
        legend = u''
        if len(clean) >= 2:
            items = []
            for i, (name, _v) in enumerate(clean[:SERIES_COLORS]):
                items.append(u'<li><span class="key line s%d"></span>%s</li>' % (i + 1, escape(name)))
            if len(clean) > SERIES_COLORS:
                items.append(u'<li><span class="key line so"></span>%d more series</li>'
                             % (len(clean) - SERIES_COLORS))
            legend = u'<ul class="legend">%s</ul>' % u''.join(items)
        if not labels or not any(v is not None for _n, vals in clean for v in vals):
            body = _empty_svg(u'No data')
        else:
            body = _line_svg(labels, clean, texts, title)
        data_rows = []
        for i, label in enumerate(labels):
            data_rows.append([label] + [texts[s][i] or u'' for s in range(len(clean))])
        return self._chart_block(u'line', title, legend + body, [u'Label'] + [n for n, _v in clean],
                                 data_rows)

    def donut(self, labels, values, title=None, value_format=None, center_label=u'Total'):
        """Donut of shares with the total in the middle and a legend table (value and
        share). More than six categories: the five largest stay, the rest fold into
        'Other'. Zero, negative and missing values get no slice."""
        labels = [_label(l) for l in labels]
        values = [_number(v) for v in list(values)[:len(labels)]]
        labels = labels[:len(values)]
        entries = [(l, max(0.0, v or 0.0)) for l, v in zip(labels, values)]
        if len(entries) > SERIES_COLORS:
            ranked = sorted(range(len(entries)), key=lambda i: (-entries[i][1], i))
            keep = set(ranked[:SERIES_COLORS - 1])
            other = [entries[i] for i in range(len(entries)) if i not in keep]
            entries = [entries[i] for i in range(len(entries)) if i in keep]
            entries.append((u'Other (%d)' % len(other), sum(v for _l, v in other)))
            colours = [u's%d' % (i + 1) for i in range(SERIES_COLORS - 1)] + [u'so']
        else:
            colours = [u's%d' % (i + 1) for i in range(len(entries))]
        total = sum(v for _l, v in entries)
        texts = [_fmt(v, value_format) for _l, v in entries]
        shares = [(u'%.1f%%' % (v * 100.0 / total)) if total > 0 else u'' for _l, v in entries]
        if total <= 0:
            body = _empty_svg(u'No data')
        else:
            svg = _donut_svg(entries, colours, texts, shares, _fmt(total, value_format),
                             center_label, title)
            legend_rows = []
            for (label, _v), colour, text, share in zip(entries, colours, texts, shares):
                legend_rows.append(u'<tr><td><span class="key %s"></span>%s</td><td class="num">%s</td>'
                                   u'<td class="num">%s</td></tr>' % (colour, escape(label), escape(text),
                                                                      escape(share)))
            body = u'<div class="pie-body">%s<table class="lg">%s</table></div>' % (svg, u''.join(legend_rows))
        return self._chart_block(u'donut', title, body, [u'Label', u'Value', u'Share'],
                                 [[l, t, s] for (l, _v), t, s in zip(entries, texts, shares)])

    def heatmap(self, row_labels, col_labels, matrix, title=None, value_format='{:,}',
                show_zero=False):
        """A grid of cells shaded on a 7-step sequential scale (largest value darkest),
        values printed in each cell. matrix[r][c]; None or 0 cells stay unshaded (0 is
        printed only with show_zero=True). Scrolls sideways when wide."""
        row_labels = [_label(l) for l in row_labels]
        col_labels = [_label(l) for l in col_labels]
        grid = []
        for r in range(len(row_labels)):
            source = list(matrix[r]) if r < len(matrix) else []
            grid.append([_number(source[c]) if c < len(source) else None for c in range(len(col_labels))])
        texts = [[(_heat_fmt(v, value_format) if v is not None else u'') for v in row] for row in grid]
        peak = max([v for row in grid for v in row if v is not None and v > 0] or [0])
        if not row_labels or not col_labels:
            body = _empty_svg(u'No data')
        else:
            body = u'<div class="hm">%s</div>' % _heat_svg(row_labels, col_labels, grid, texts, peak,
                                                         show_zero, title)
            low = _heat_fmt(0, value_format) if peak > 0 else u''
            body += (u'<div class="heatkey"><span>%s</span><span class="ramp">%s</span><span>%s</span></div>'
                     % (escape(low), u''.join(u'<span class="key heat h%d"></span>' % i for i in range(1, 8)),
                        escape(_heat_fmt(peak, value_format) if peak > 0 else u'')))
        data_rows = [[label] + row for label, row in zip(row_labels, texts)]
        return self._chart_block(u'heat', title, body, [u''] + col_labels, data_rows)

    # --- images ----------------------------------------------------------------------

    def image(self, path_or_bytes, caption=None, max_width=None, alt=None):
        """An embedded image (base64) with an optional caption, never wider than the page
        (or max_width px)."""
        uri, size, name = _load_image(path_or_bytes)
        style = u' style="max-width:min(100%%, %dpx)"' % int(max_width) if max_width else u''
        dims = u' width="%d" height="%d"' % size if size else u''
        text = alt if alt is not None else (caption or name or u'Image')
        html = u'<figure class="img"><img src="%s" alt="%s"%s%s>' % (uri, escape(text), dims, style)
        if caption:
            html += u'<figcaption>%s</figcaption>' % escape(caption)
        self._blocks.append(html + u'</figure>')

    def gallery(self, items, columns=4):
        """A grid of captioned thumbnails: [(path_or_bytes, caption), ...]. Click (or
        Enter) opens an image full size; arrow keys step through, Esc closes."""
        self._uses_gallery = True
        columns = max(1, int(columns))
        parts = [u'<div class="gal" style="--cols:%d">' % columns]
        for item in items:
            item = tuple(item)
            source = item[0]
            caption = item[1] if len(item) > 1 else None
            uri, size, name = _load_image(source)
            text = caption or name or u'Image'
            dims = u' width="%d" height="%d"' % size if size else u''
            parts.append(u'<figure><button type="button" class="zoom" data-cap="%s" aria-label="%s">'
                         u'<img src="%s" alt="%s"%s></button>%s</figure>' % (
                             escape(caption or u''), escape(u'Enlarge: ' + text), uri, escape(text), dims,
                             u'<figcaption>%s</figcaption>' % escape(caption) if caption else u''))
        parts.append(u'</div>')
        self._blocks.append(u''.join(parts))

    # --- output ----------------------------------------------------------------------

    def to_string(self):
        """The whole report as one HTML document (str)."""
        parts = [u'<!DOCTYPE html>\n<html lang="%s">\n<head>\n<meta charset="utf-8">\n'
                 u'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                 u'<meta name="generator" content="Playground">\n<title>%s</title>\n<style>\n%s</style>\n'
                 u'</head>\n<body>\n<main class="page">\n' % (escape(self.lang), escape(self.title), _CSS)]
        head = [u'<header class="head"><h1>%s</h1>' % escape(self.title)]
        if self.subtitle:
            head.append(u'<p class="sub">%s</p>' % _escape_lines(self.subtitle))
        if self.meta:
            head.append(u'<dl class="meta">')
            for item in self.meta:
                label, value = item[0], item[1]
                shown = format_number(value) if _finite(value) else escape(value)
                head.append(u'<div><dt>%s</dt><dd>%s</dd></div>' % (escape(label), shown))
            head.append(u'</dl>')
        head.append(u'</header>')
        parts.append(u''.join(head) + u'\n')
        show_toc = self.toc if self.toc is not None else len(self._sections) >= 4
        if show_toc and self._sections:
            parts.append(u'<nav class="toc" aria-label="Contents"><ol>%s</ol></nav>\n' % u''.join(
                u'<li><a href="#%s">%s</a></li>' % (sid, escape(title)) for sid, title in self._sections))
        for block in self._blocks:
            parts.append(block + u'\n')
        footer = u'Made with pyNavis Playground' if self.footer is None else self.footer
        if footer:
            parts.append(u'<footer class="foot">%s</footer>\n' % escape(footer))
        parts.append(u'</main>\n')
        if self._uses_tip:
            parts.append(u'<div id="tip" role="tooltip" hidden></div>\n')
        if self._uses_gallery:
            parts.append(u'<div id="lb" role="dialog" aria-modal="true" aria-label="Image viewer" hidden>'
                         u'<div class="bar"><span class="cap"></span>'
                         u'<button type="button" class="prev" aria-label="Previous image">Previous</button>'
                         u'<button type="button" class="next" aria-label="Next image">Next</button>'
                         u'<button type="button" class="close">Close</button></div>'
                         u'<div class="stage"><img alt=""></div></div>\n')
        parts.append(u'<script>\n%s</script>\n</body>\n</html>\n' % _JS)
        return u''.join(parts)

    def save(self, path):
        """Write the report (UTF-8) atomically: temp file, then replace. Returns path."""
        data = self.to_string().encode('utf-8', 'replace')
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            os.makedirs(folder)
        temp = path + '.tmp'
        try:
            handle = open(temp, 'wb')
            try:
                handle.write(data)
            finally:
                handle.close()
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                try:
                    os.remove(temp)
                except OSError:
                    pass
        return path


def _rows_text(count):
    return u'%s %s' % (format_number(count), u'row' if count == 1 else u'rows')


def _label(value):
    """Category label text; numbers formatted the same on both engines (2026.0 -> '2026')."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and _finite(value):
        return _short_num(value)
    return u'%s' % ('' if value is None else value,)


def _heat_fmt(value, value_format):
    """Heatmap cell text: whole numbers through value_format; with the default '{:,}' a
    fractional value uses format_number so it reads the same on both engines."""
    value = _intish(value)
    if value_format == '{:,}' and isinstance(value, float):
        return format_number(value)
    return _fmt(value, value_format)


def _intish(value):
    """Whole floats -> int so '{:,}' prints '12' and not '12.0'."""
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return int(value)
    return value


def _decimals_needed(value):
    rounded = round(value, 2)
    if rounded == round(rounded):
        return 0
    return 1 if round(value, 1) == rounded else 2


def _column_decimals(rows, num_cols, trusted):
    """{col: decimals} so every number in a numeric column shows the same number of
    decimal places (0..2) and the column lines up."""
    out = {}
    for col in num_cols:
        places = 0
        for r, row in enumerate(rows):
            value = row[col] if col < len(row) else None
            if isinstance(value, float) and _finite(value) and (r, col) not in trusted:
                places = max(places, _decimals_needed(value))
                if places == 2:
                    break
        out[col] = places
    return out


def _cell(value, trusted, decimals=None):
    """Table cell value -> (inner HTML, sort key or None). decimals fixes the number of
    decimal places for numbers (None: format_number's trimmed style)."""
    if trusted:
        return u'%s' % ('' if value is None else value,), None
    if value is None:
        return u'', None
    if isinstance(value, bool):
        return (u'Yes' if value else u'No'), None
    if isinstance(value, (int, float)):
        if not _finite(value):
            return u'', None
        if decimals:
            return (u'{:,.%df}' % decimals).format(value), _short_num(value)
        return format_number(value), _short_num(value)
    if isinstance(value, datetime.datetime):
        return value.strftime(u'%Y-%m-%d %H:%M'), value.strftime(u'%Y-%m-%dT%H:%M:%S')
    if isinstance(value, datetime.date):
        return value.strftime(u'%Y-%m-%d'), value.strftime(u'%Y-%m-%d')
    return _escape_lines(value), None


# ---------------------------------------------------------------------------
# SVG renderers (pure, return markup)
# ---------------------------------------------------------------------------

def _svg_open(width, height, label, cls=u'', extra=u''):
    return (u'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" width="%s" height="%s" '
            u'style="max-width:%spx" role="img" aria-label="%s"%s%s>' % (
                _p(width), _p(height), _p(width), _p(height), _p(width), escape(label),
                u' class="%s"' % cls if cls else u'', extra))


def _empty_svg(message):
    return (_svg_open(720, 64, message)
            + u'<rect x="0.5" y="0.5" width="719" height="63" rx="4" fill="none" class="grid"/>'
            u'<text x="360" y="36" text-anchor="middle">%s</text></svg>' % escape(message))


def _bar_class(index, tones):
    tone = tones[index] if index < len(tones) else None
    return u'tn-%s' % tone if tone else u's1'


def _round_rect(x0, y0, x1, y1, end, radius=4.0):
    """A bar from x0..x1, y0..y1 with rounded corners only on the data end
    ('right', 'left', 'top' or 'bottom'); square at the baseline."""
    w = abs(x1 - x0)
    h = abs(y1 - y0)
    if w <= 0 or h <= 0:
        return u''
    left, right = min(x0, x1), max(x0, x1)
    top, bottom = min(y0, y1), max(y0, y1)
    r = min(radius, w / 2.0, h / 2.0)
    if end == 'right':
        d = (u'M%s %sH%sA%s %s 0 0 1 %s %sV%sA%s %s 0 0 1 %s %sH%sZ' % (
            _p(left), _p(top), _p(right - r), _p(r), _p(r), _p(right), _p(top + r), _p(bottom - r),
            _p(r), _p(r), _p(right - r), _p(bottom), _p(left)))
    elif end == 'left':
        d = (u'M%s %sH%sA%s %s 0 0 0 %s %sV%sA%s %s 0 0 0 %s %sH%sZ' % (
            _p(right), _p(top), _p(left + r), _p(r), _p(r), _p(left), _p(top + r), _p(bottom - r),
            _p(r), _p(r), _p(left + r), _p(bottom), _p(right)))
    elif end == 'top':
        d = (u'M%s %sV%sA%s %s 0 0 1 %s %sH%sA%s %s 0 0 1 %s %sV%sZ' % (
            _p(left), _p(bottom), _p(top + r), _p(r), _p(r), _p(left + r), _p(top), _p(right - r),
            _p(r), _p(r), _p(right), _p(top + r), _p(bottom)))
    else:
        d = (u'M%s %sV%sA%s %s 0 0 0 %s %sH%sA%s %s 0 0 0 %s %sV%sZ' % (
            _p(left), _p(top), _p(bottom - r), _p(r), _p(r), _p(left + r), _p(bottom), _p(right - r),
            _p(r), _p(r), _p(right), _p(bottom - r), _p(top)))
    return d


def _hbar_svg(labels, values, texts, tones, title):
    width = 720.0
    row_h = 28.0
    bar_h = 16.0
    label_w = min(240.0, max(60.0, max(_text_w(l) for l in labels) + 16))
    value_w = max(_text_w(t) for t in texts) + 12 if any(texts) else 12
    plot_x0 = label_w
    plot_w = max(80.0, width - label_w - value_w - 8)
    present = [v for v in values if v is not None]
    lo = min([0.0] + present)
    hi = max([0.0] + present)
    if hi == lo:
        hi = lo + 1.0

    def sx(v):
        return plot_x0 + (v - lo) / (hi - lo) * plot_w

    height = len(labels) * row_h + 8
    parts = [_svg_open(width, height, title or u'Bar chart', u'bars')]
    zero = sx(0.0)
    parts.append(u'<line class="axis" x1="%s" y1="2" x2="%s" y2="%s"/>' % (_p(zero), _p(zero), _p(height - 4)))
    for i, (label, value, text) in enumerate(zip(labels, values, texts)):
        y = 4 + i * row_h
        cy = y + row_h / 2.0
        tip = u'%s: %s' % (label, text if value is not None else u'no value')
        parts.append(u'<g data-tip="%s"><rect class="hit" x="0" y="%s" width="%s" height="%s"/>'
                     % (escape(tip), _p(y), _p(width), _p(row_h)))
        parts.append(u'<text class="lbl" x="%s" y="%s" text-anchor="end">%s</text>'
                     % (_p(label_w - 8), _p(cy + 4), escape(_clip(label, label_w - 14))))
        if value is not None:
            end = sx(value)
            d = _round_rect(zero, cy - bar_h / 2.0, end, cy + bar_h / 2.0, 'right' if value >= 0 else 'left')
            if d:
                parts.append(u'<path class="%s" d="%s"/>' % (_bar_class(i, tones), d))
            tx = max(end, zero) + 6
            parts.append(u'<text class="val" x="%s" y="%s">%s</text>' % (_p(tx), _p(cy + 4), escape(text)))
        parts.append(u'</g>')
    parts.append(u'</svg>')
    return u''.join(parts)


def _vbar_svg(labels, values, texts, tones, title):
    width = 720.0
    height = 280.0
    present = [v for v in values if v is not None]
    ticks = _nice_ticks(min([0.0] + present), max([0.0] + present),
                        integers=all(float(v).is_integer() for v in present))
    lo, hi = ticks[0], ticks[-1]
    tick_texts = [format_number(t) for t in ticks]
    left = max(_text_w(t) for t in tick_texts) + 12
    top, bottom, right = 20.0, 40.0, 8.0
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sy(v):
        return top + (hi - v) / (hi - lo) * plot_h

    n = len(labels)
    slot = plot_w / float(n)
    bar_w = min(24.0, slot * 0.6)
    label_every = 1 if slot >= 36 else int(math.ceil(36 / slot))
    parts = [_svg_open(width, height, title or u'Column chart', u'bars')]
    for tick, text in zip(ticks, tick_texts):
        y = sy(tick)
        parts.append(u'<line class="%s" x1="%s" y1="%s" x2="%s" y2="%s"/>' % (
            u'axis' if tick == 0 else u'grid', _p(left), _p(y), _p(width - right), _p(y)))
        parts.append(u'<text class="tick" x="%s" y="%s" text-anchor="end">%s</text>'
                     % (_p(left - 8), _p(y + 4), escape(text)))
    zero = sy(0.0)
    for i, (label, value, text) in enumerate(zip(labels, values, texts)):
        cx = left + slot * (i + 0.5)
        tip = u'%s: %s' % (label, text if value is not None else u'no value')
        parts.append(u'<g data-tip="%s"><rect class="hit" x="%s" y="%s" width="%s" height="%s"/>'
                     % (escape(tip), _p(left + slot * i), _p(top), _p(slot), _p(plot_h + bottom)))
        if value is not None:
            end = sy(value)
            d = _round_rect(cx - bar_w / 2.0, zero, cx + bar_w / 2.0, end, 'top' if value >= 0 else 'bottom')
            if d:
                parts.append(u'<path class="%s" d="%s"/>' % (_bar_class(i, tones), d))
            if _text_w(text) + 4 <= slot:
                ty = end - 6 if value >= 0 else end + 16
                parts.append(u'<text class="val" x="%s" y="%s" text-anchor="middle">%s</text>'
                             % (_p(cx), _p(ty), escape(text)))
        if i % label_every == 0:
            parts.append(u'<text class="lbl" x="%s" y="%s" text-anchor="middle">%s</text>'
                         % (_p(cx), _p(height - bottom + 18), escape(_clip(label, slot * label_every - 4))))
        parts.append(u'</g>')
    parts.append(u'</svg>')
    return u''.join(parts)


def _line_svg(labels, series, texts, title):
    width = 720.0
    height = 280.0
    present = [v for _n, vals in series for v in vals if v is not None]
    lo, hi = min(present), max(present)
    if lo >= 0 and lo <= hi * 0.5:
        lo = 0.0
    ticks = _nice_ticks(lo, hi, integers=all(float(v).is_integer() for v in present))
    lo, hi = ticks[0], ticks[-1]
    tick_texts = [format_number(t) for t in ticks]
    left = max(_text_w(t) for t in tick_texts) + 12
    top, bottom, right = 12.0, 32.0, 16.0
    plot_w = width - left - right
    plot_h = height - top - bottom
    n = len(labels)
    step = plot_w / float(n - 1) if n > 1 else 0.0
    x0 = left if n > 1 else left + plot_w / 2.0

    def sy(v):
        return top + (hi - v) / (hi - lo) * plot_h

    # Built by hand: json.dumps writes floats with repr, which differs on IronPython.
    data = u'{"labels":%s,"series":%s,"step":%s,"x0":%s}' % (
        json.dumps(labels, separators=(',', ':')),
        json.dumps([[name, texts[i]] for i, (name, _v) in enumerate(series)], separators=(',', ':')),
        _short_num(round(step, 4)), _short_num(round(x0, 2)))
    attr = u' data-d="%s"' % escape(data)
    parts = [_svg_open(width, height, title or u'Line chart', u'line', attr)]
    for tick, text in zip(ticks, tick_texts):
        y = sy(tick)
        parts.append(u'<line class="%s" x1="%s" y1="%s" x2="%s" y2="%s"/>' % (
            u'axis' if tick == lo else u'grid', _p(left), _p(y), _p(width - right), _p(y)))
        parts.append(u'<text class="tick" x="%s" y="%s" text-anchor="end">%s</text>'
                     % (_p(left - 8), _p(y + 4), escape(text)))
    max_label = max(_text_w(l) for l in labels) + 16
    room = max(1, int(plot_w // max_label) + 1)
    stride = max(1, int(math.ceil(n / float(room))))
    for i, label in enumerate(labels):
        if i % stride:
            continue
        x = x0 + step * i
        anchor = u'start' if (i == 0 and n > 1) else (u'end' if (i == n - 1 and n > 1) else u'middle')
        parts.append(u'<text class="tick" x="%s" y="%s" text-anchor="%s">%s</text>'
                     % (_p(x), _p(height - bottom + 20), anchor,
                        escape(_clip(label, max(40.0, step * stride - 8)))))
    parts.append(u'<line class="xh" x1="0" y1="%s" x2="0" y2="%s"/>' % (_p(top), _p(top + plot_h)))
    # draw later series first so series 1 sits on top
    for index in range(len(series) - 1, -1, -1):
        _name, vals = series[index]
        cls = u'k%d' % (index + 1) if index < SERIES_COLORS else u'ko lo'
        fill = u's%d' % (index + 1) if index < SERIES_COLORS else u'so'
        runs = []
        current = []
        for i, v in enumerate(vals):
            if v is None:
                if current:
                    runs.append(current)
                current = []
            else:
                current.append((x0 + step * i, sy(v)))
        if current:
            runs.append(current)
        for run in runs:
            if len(run) > 1:
                d = u'M' + u'L'.join(u'%s %s' % (_p(x), _p(y)) for x, y in run)
                parts.append(u'<path class="ln %s" d="%s"/>' % (cls, d))
        last = [(i, v) for i, v in enumerate(vals) if v is not None]
        if last:
            i, v = last[-1]
            parts.append(u'<circle class="dot %s" cx="%s" cy="%s" r="4"/>' % (fill, _p(x0 + step * i), _p(sy(v))))
        for run in runs:
            if len(run) == 1:
                parts.append(u'<circle class="dot %s" cx="%s" cy="%s" r="4"/>' % (fill, _p(run[0][0]), _p(run[0][1])))
    parts.append(u'<rect class="hit" x="%s" y="%s" width="%s" height="%s"/>' % (
        _p(left), _p(top), _p(plot_w), _p(plot_h)))
    parts.append(u'</svg>')
    return u''.join(parts)


def _donut_svg(entries, colours, texts, shares, total_text, center_label, title):
    size = 200.0
    c = size / 2.0
    radius = 72.0
    ring = 26.0
    circumference = 2 * math.pi * radius
    total = sum(v for _l, v in entries)
    slices = [(i, v) for i, (_l, v) in enumerate(entries) if v > 0]
    gap = 2.0 if len(slices) > 1 else 0.0
    parts = [_svg_open(size, size, title or u'Donut chart', u'pie')]
    offset = 0.0
    for i, value in slices:
        length = value / total * circumference
        dash = max(0.6, length - gap) if gap else length
        tip = u'%s: %s (%s)' % (entries[i][0], texts[i], shares[i])
        parts.append(u'<circle class="%s" data-tip="%s" cx="%s" cy="%s" r="%s" fill="none" '
                     u'stroke-width="%s" stroke-dasharray="%s %s" stroke-dashoffset="%s" '
                     u'transform="rotate(-90 %s %s)"/>' % (
                         colours[i].replace(u's', u'k', 1) if colours[i] != u'so' else u'ko',
                         escape(tip), _p(c), _p(c), _p(radius), _p(ring), _num2(dash),
                         _num2(circumference), _num2(-offset), _p(c), _p(c)))
        offset += length
    parts.append(u'<text class="big" x="%s" y="%s" text-anchor="middle">%s</text>'
                 % (_p(c), _p(c + 4), escape(total_text)))
    parts.append(u'<text x="%s" y="%s" text-anchor="middle">%s</text>'
                 % (_p(c), _p(c + 22), escape(center_label)))
    parts.append(u'</svg>')
    return u''.join(parts)


def _num2(value):
    text = u'%.2f' % value
    text = text.rstrip(u'0').rstrip(u'.')
    return u'0' if text in (u'-0', u'') else text


def _heat_step(value, peak):
    if value is None or value <= 0 or peak <= 0:
        return 0
    return max(1, min(7, int(math.ceil(value / peak * 7))))


def _heat_svg(row_labels, col_labels, grid, texts, peak, show_zero, title):
    cell_h = 28.0
    widest = max([_text_w(t) for row in texts for t in row] + [0])
    cell_w = max(44.0, widest + 14)
    row_w = min(260.0, max(_text_w(l) for l in row_labels) + 20)
    col_label_w = min(180.0, max(_text_w(l) for l in col_labels))
    head_h = col_label_w * 0.71 + 18
    right_pad = col_label_w * 0.71 + 8
    width = row_w + len(col_labels) * cell_w + right_pad
    height = head_h + len(row_labels) * cell_h + 4
    parts = [_svg_open(width, height, title or u'Heatmap', u'heatmap')]
    for c, label in enumerate(col_labels):
        x = row_w + c * cell_w + cell_w / 2.0
        y = head_h - 8
        parts.append(u'<text class="lbl" x="%s" y="%s" transform="rotate(-45 %s %s)">%s</text>'
                     % (_p(x), _p(y), _p(x), _p(y), escape(_clip(label, col_label_w + 2))))
    for r, label in enumerate(row_labels):
        y = head_h + r * cell_h
        parts.append(u'<text class="lbl" x="%s" y="%s" text-anchor="end">%s</text>'
                     % (_p(row_w - 8), _p(y + cell_h / 2.0 + 4), escape(_clip(label, row_w - 14))))
        for c in range(len(col_labels)):
            value = grid[r][c]
            step = _heat_step(value, peak)
            x = row_w + c * cell_w
            text = texts[r][c]
            if value is not None and value == 0 and not show_zero:
                text = u''
            tip = u'%s / %s: %s' % (label, col_labels[c], texts[r][c] or u'no value')
            parts.append(u'<g data-tip="%s"><rect class="h%d" x="%s" y="%s" width="%s" height="%s"/>'
                         % (escape(tip), step, _p(x + 1), _p(y + 1), _p(cell_w - 2), _p(cell_h - 2)))
            if text:
                parts.append(u'<text class="hv h%d" x="%s" y="%s" text-anchor="middle">%s</text>'
                             % (step, _p(x + cell_w / 2.0), _p(y + cell_h / 2.0 + 4), escape(text)))
            parts.append(u'</g>')
    parts.append(u'</svg>')
    return u''.join(parts)

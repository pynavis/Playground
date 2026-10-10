# -*- coding: utf-8 -*-
"""Status-coloured charts for the clash dashboard, drawn in namo.htmlreport's own idiom.

htmlreport's donut takes categorical colours, but clash statuses must keep the native
Clash Detective colours everywhere (New red, Active orange, Reviewed blue, Approved green,
Resolved yellow). These two charts reuse htmlreport's CSS classes so they theme, print
and show tooltips exactly like its charts:

  * `.chart .tn-<tone>` fills (tones new/active/reviewed/approved/resolved),
  * `.key.tn-<tone>` legend swatches, `ul.legend`, `table.lg`, `.pie-body`,
  * `[data-tip]` hover tooltips, `text.lbl` / `text.val` / `text.big` labels,
  * the collapsed `details.data` table under each chart.

Each function returns trusted HTML for `Report.html()`. Every text is escaped here.
Pure: no Navisworks, same output on both engines.
"""

import math

from namo.htmlreport import escape, format_number

STATUS_TONES = [('New', 'new'), ('Active', 'active'), ('Reviewed', 'reviewed'),
                ('Approved', 'approved'), ('Resolved', 'resolved')]
_CHAR_W = 0.58


def _p(value):
    """Short coordinate text (two decimals, trimmed)."""
    text = u'%.2f' % value
    text = text.rstrip(u'0').rstrip(u'.')
    return u'0' if text in (u'-0', u'') else text


def _text_w(text, size=12):
    return len(u'%s' % (text,)) * size * _CHAR_W


def _clip(text, max_px, size=12):
    text = u'%s' % (text,)
    if _text_w(text, size) <= max_px:
        return text
    keep = max(1, int(max_px / (size * _CHAR_W)) - 1)
    return text[:keep] + u'…'


def _share(value, total):
    return (u'%.1f%%' % (value * 100.0 / total)) if total else u''


def _data_table(headers, rows):
    """The collapsed 'Data' table htmlreport puts under each chart."""
    head = u''.join(u'<th scope="col"%s>%s</th>' % (u' class="num"' if i else u'', escape(h))
                    for i, h in enumerate(headers))
    body = []
    for row in rows:
        cells = []
        for i, value in enumerate(row):
            cells.append(u'<td%s>%s</td>' % (u' class="num"' if i else u'', escape(value)))
        body.append(u'<tr>%s</tr>' % u''.join(cells))
    return (u'<details class="data"><summary>Data</summary><div class="scroll"><table class="data">'
            u'<thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></details>'
            % (head, u''.join(body)))


def _annulus(cx, cy, r_out, r_in, a0, a1):
    """SVG path of a ring sector from angle a0 to a1 (radians, clockwise from 12 o'clock)."""
    def point(r, a):
        return cx + r * math.sin(a), cy - r * math.cos(a)
    large = 1 if (a1 - a0) > math.pi else 0
    x0, y0 = point(r_out, a0)
    x1, y1 = point(r_out, a1)
    x2, y2 = point(r_in, a1)
    x3, y3 = point(r_in, a0)
    return (u'M%s %sA%s %s 0 %d 1 %s %sL%s %sA%s %s 0 %d 0 %s %sZ' % (
        _p(x0), _p(y0), _p(r_out), _p(r_out), large, _p(x1), _p(y1), _p(x2), _p(y2),
        _p(r_in), _p(r_in), large, _p(x3), _p(y3)))


def status_donut(by_status, title=None, center_label=u'Clashes'):
    """A donut of clash statuses in their own colours with the total in the middle and a
    legend table (count and share). by_status: {status: n}. Zero statuses get no slice."""
    entries = [(name, tone, int(by_status.get(name) or 0)) for name, tone in STATUS_TONES]
    total = sum(n for _name, _tone, n in entries)
    parts = [u'<div class="block chart chart-donut">']
    if title:
        parts.append(u'<h3>%s</h3>' % escape(title))
    size = 200.0
    c = size / 2.0
    r_out, r_in = 85.0, 59.0
    svg = [u'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200" '
           u'style="max-width:200px" role="img" aria-label="%s" class="pie">' % escape(title or u'Clash statuses')]
    if total <= 0:
        svg.append(u'<circle cx="100" cy="100" r="72" fill="none" class="grid" style="stroke-width:26px"/>')
    else:
        slices = [(name, tone, n) for name, tone, n in entries if n > 0]
        gap = math.radians(1.2) if len(slices) > 1 else 0.0
        angle = 0.0
        for name, tone, n in slices:
            sweep = 2 * math.pi * n / float(total)
            tip = u'%s: %s (%s)' % (name, format_number(n), _share(n, total))
            if len(slices) == 1:
                halves = [(0.0, math.pi), (math.pi, 2 * math.pi)]
                for a0, a1 in halves:
                    svg.append(u'<path class="tn-%s" data-tip="%s" d="%s"/>'
                               % (tone, escape(tip), _annulus(c, c, r_out, r_in, a0, a1)))
            else:
                a0 = angle + gap / 2.0
                a1 = angle + max(sweep - gap / 2.0, gap / 2.0 + 0.002)
                svg.append(u'<path class="tn-%s" data-tip="%s" d="%s"/>'
                           % (tone, escape(tip), _annulus(c, c, r_out, r_in, a0, a1)))
            angle += sweep
    svg.append(u'<text class="big" x="100" y="104" text-anchor="middle">%s</text>' % escape(format_number(total)))
    svg.append(u'<text x="100" y="122" text-anchor="middle">%s</text>' % escape(center_label))
    svg.append(u'</svg>')
    legend = []
    for name, tone, n in entries:
        legend.append(u'<tr><td><span class="key tn-%s"></span>%s</td><td class="num">%s</td>'
                      u'<td class="num">%s</td></tr>' % (tone, escape(name), format_number(n), _share(n, total)))
    parts.append(u'<div class="pie-body">%s<table class="lg">%s</table></div>' % (u''.join(svg), u''.join(legend)))
    parts.append(_data_table([u'Status', u'Clashes', u'Share'],
                             [[name, format_number(n), _share(n, total)] for name, _tone, n in entries]))
    parts.append(u'</div>')
    return u''.join(parts)


def stacked_bars(rows, title=None, note=None):
    """Horizontal bars, one per label, stacked by status in Clash Detective order, with the
    total at the tip and a legend of the statuses present. rows: [(label, {status: n})]."""
    width = 720.0
    row_h = 30.0
    bar_h = 18.0
    totals = [sum(int(counts.get(s) or 0) for s, _t in STATUS_TONES) for _label, counts in rows]
    present = [(s, t) for s, t in STATUS_TONES if any(int(c.get(s) or 0) for _l, c in rows)]
    parts = [u'<div class="block chart chart-bar">']
    if title:
        parts.append(u'<h3>%s</h3>' % escape(title))
    if present:
        parts.append(u'<ul class="legend">%s</ul>' % u''.join(
            u'<li><span class="key tn-%s"></span>%s</li>' % (tone, escape(name)) for name, tone in present))
    if not rows or not any(totals):
        parts.append(u'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 64" width="720" height="64" '
                     u'style="max-width:720px" role="img" aria-label="No data"><rect x="0.5" y="0.5" '
                     u'width="719" height="63" rx="4" fill="none" class="grid"/><text x="360" y="36" '
                     u'text-anchor="middle">No data</text></svg>')
    else:
        label_w = min(260.0, max(60.0, max(_text_w(l) for l, _c in rows) + 16))
        texts = [format_number(t) for t in totals]
        value_w = max(_text_w(t) for t in texts) + 12
        plot_w = max(80.0, width - label_w - value_w - 8)
        peak = float(max(totals)) or 1.0
        height = len(rows) * row_h + 8
        svg = [u'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" width="%s" height="%s" '
               u'style="max-width:%spx" role="img" aria-label="%s" class="bars">'
               % (_p(width), _p(height), _p(width), _p(height), _p(width), escape(title or u'Clashes by status'))]
        svg.append(u'<line class="axis" x1="%s" y1="2" x2="%s" y2="%s"/>' % (_p(label_w), _p(label_w), _p(height - 4)))
        for i, (label, counts) in enumerate(rows):
            y = 4 + i * row_h
            cy = y + row_h / 2.0
            svg.append(u'<text class="lbl" x="%s" y="%s" text-anchor="end">%s</text>'
                       % (_p(label_w - 8), _p(cy + 4), escape(_clip(label, label_w - 14))))
            x = label_w
            for name, tone in STATUS_TONES:
                n = int(counts.get(name) or 0)
                if n <= 0:
                    continue
                w = plot_w * n / peak
                tip = u'%s\n%s: %s (%s)' % (label, name, format_number(n), _share(n, totals[i]))
                svg.append(u'<rect class="tn-%s" data-tip="%s" x="%s" y="%s" width="%s" height="%s"/>'
                           % (tone, escape(tip), _p(x), _p(cy - bar_h / 2.0), _p(max(w, 0.8)), _p(bar_h)))
                x += w
            svg.append(u'<text class="val" x="%s" y="%s">%s</text>' % (_p(x + 6), _p(cy + 4), escape(texts[i])))
        svg.append(u'</svg>')
        parts.append(u''.join(svg))
    if note:
        parts.append(u'<p class="intro">%s</p>' % escape(note))
    headers = [u'Label'] + [name for name, _t in STATUS_TONES] + [u'Total']
    data_rows = [[label] + [format_number(int(counts.get(name) or 0)) for name, _t in STATUS_TONES] +
                 [format_number(totals[i])] for i, (label, counts) in enumerate(rows)]
    parts.append(_data_table(headers, data_rows))
    parts.append(u'</div>')
    return u''.join(parts)


def thumb_cell(data_uri, alt):
    """An <img> for a table cell (trusted HTML): fixed 160 x 90 box, lazy loaded."""
    return (u'<img src="%s" width="160" height="90" alt="%s" loading="lazy" '
            u'style="display:block;border-radius:3px;max-width:none">' % (data_uri, escape(alt)))


def status_mix_html(by_status, chip):
    """Status chips for a mix like {'New': 3, 'Active': 1}: chip(text, tone) builds one
    (htmlreport.status_chip). Zero statuses are left out."""
    parts = []
    for name, tone in STATUS_TONES:
        n = int(by_status.get(name) or 0)
        if n:
            parts.append(chip(u'%s %s' % (format_number(n), name), tone))
    return u' '.join(parts)

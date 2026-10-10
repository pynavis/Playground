# -*- coding: utf-8 -*-
"""Output-window HTML for the clash reports: a heading, a strip of headline numbers and
plain tables, all on the pyNavis output window's own CSS (table.pynavis, td.num, the
--fg / --muted / --line variables), so they follow its light or dark theme.

Every function returns trusted HTML for pynavis.output.print_html and escapes the text it
is given, except the cells named in `trusted` (HTML the caller built, such as
output.element_link). Pure.
"""

from namo.htmlreport import escape, format_number
# Page and deliver started here and moved to namo.reports so every report can use
# them; the names stay importable from this module.
from namo.reports import Page, deliver  # noqa: F401


def heading(title, sub=None):
    html = u'<div style="font-size:18px;font-weight:600;margin:0 0 2px">%s</div>' % escape(title)
    if sub:
        html += u'<div style="color:var(--muted);margin:0 0 4px">%s</div>' % escape(sub)
    return html


def subheading(title, sub=None):
    html = u'<div style="font-size:14px;font-weight:600;margin:18px 0 2px">%s</div>' % escape(title)
    if sub:
        html += u'<div style="color:var(--muted);margin:0 0 2px">%s</div>' % escape(sub)
    return html


def kpi_strip(items):
    """Big light numbers with a muted label above and an optional muted line below:
    [(label, value, detail or None)]."""
    parts = [u'<div style="display:flex;flex-wrap:wrap;gap:8px 40px;margin:12px 0 8px">']
    for item in items:
        label, value = item[0], item[1]
        detail = item[2] if len(item) > 2 else None
        shown = format_number(value) if isinstance(value, (int, float)) and not isinstance(value, bool) \
            else escape(value)
        parts.append(u'<div><div style="font-size:12px;color:var(--muted)">%s</div>'
                     u'<div style="font-size:26px;font-weight:300;line-height:1.2;'
                     u'font-variant-numeric:tabular-nums">%s</div>%s</div>' % (
                         escape(label), shown,
                         u'<div style="font-size:12px;color:var(--muted)">%s</div>' % escape(detail) if detail else u''))
    parts.append(u'</div>')
    return u''.join(parts)


def _cell(value):
    if value is None:
        return u''
    if isinstance(value, bool):
        return u'Yes' if value else u'No'
    if isinstance(value, (int, float)):
        return format_number(value)
    return escape(value).replace(u'\n', u'<br>')


def table(headers, rows, numeric=(), trusted=(), limit=None, more=None):
    """A table.pynavis. numeric: column indexes right-aligned; trusted: column indexes whose
    cells are trusted HTML. limit: rows shown; more: the sentence printed under a cut
    table (default 'Showing the first N of M.')."""
    numeric = set(numeric)
    trusted = set(trusted)
    shown = rows if limit is None else rows[:limit]
    parts = [u'<table class="pynavis"><tr>']
    for i, header in enumerate(headers):
        parts.append(u'<th%s>%s</th>' % (u' class="num"' if i in numeric else u'', escape(header)))
    parts.append(u'</tr>')
    for row in shown:
        parts.append(u'<tr>')
        for i in range(len(headers)):
            value = row[i] if i < len(row) else None
            content = (u'%s' % value if value is not None else u'') if i in trusted else _cell(value)
            parts.append(u'<td%s>%s</td>' % (u' class="num"' if i in numeric else u'', content))
        parts.append(u'</tr>')
    parts.append(u'</table>')
    if limit is not None and len(rows) > limit:
        parts.append(u'<div style="color:var(--muted);font-size:12px;margin:2px 0 0">%s</div>' % escape(
            more or u'Showing the first %s of %s.' % (format_number(limit), format_number(len(rows)))))
    return u''.join(parts)


def note(text):
    return u'<div style="color:var(--muted);font-size:12px;margin:10px 0 0">%s</div>' % escape(text)


def legend(names):
    """Series swatches matching pynavis.output.chart_line, which colours series in
    name-sorted order with --chart-1..6."""
    parts = [u'<div style="display:flex;flex-wrap:wrap;gap:4px 20px;font-size:12px;margin:2px 0 6px">']
    for i, name in enumerate(sorted(names)):
        parts.append(u'<span><span style="display:inline-block;width:16px;height:2px;vertical-align:3px;'
                     u'margin-right:6px;background:var(--chart-%d)"></span>%s</span>' % (i % 6 + 1, escape(name)))
    parts.append(u'</div>')
    return u''.join(parts)

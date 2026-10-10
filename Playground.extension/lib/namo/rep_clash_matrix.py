# -*- coding: utf-8 -*-
"""Clash Count Matrix: trade against trade (or model against model) counts of open and of
new clashes across the chosen tests.

A clash between two trades is counted once, in the upper triangle (row before column in
the configured trade order, the diagonal holding same-trade clashes); 'Involving' counts
every clash a trade takes part in. Interactive runs draw both matrices in the output
window as heat tables that follow the window's theme (fills mixed from the window's own
chart colour, solid, readable in light and dark) plus the top pairs; the workbook has the
same matrices with graded fills (sheets Open and New) and every pair (sheet Pairs).

Implements the namo.reports rep_<id>.py contract.
"""

import os

from namo import clashrep_out as out
from namo import clashreport as cr
from namo import colors, reports, xlsx
from namo.htmlreport import escape

TITLE = 'Clash Count Matrix'
NAME_TEMPLATE = '{file} - Clash matrix - {date}'
AXES = [('trade', 'Trades'), ('model', 'Models')]
HEAT_PERCENT = [0, 12, 21, 30, 39, 47, 55]     # mix of --chart-1 into --bg per step; text stays --fg
TOP_PAIRS = 12


def default_config():
    return reports.base_config(tests=[], axis='trade', xlsx=True, path='', name_template=NAME_TEMPLATE)


def axis_word(axis, plural=False):
    word = 'model' if axis == 'model' else 'trade'
    return word + 's' if plural else word


def describe(config):
    word = axis_word(config.get('axis'))
    return '%s, %s against %s' % (cr.tests_text(config.get('tests')), word, word)


# ---- pure ---------------------------------------------------------------------------------------


def build(data, axis='trade'):
    """{'axis', 'open': matrix, 'new': matrix on the same labels, 'pairs': [(a, b, open, new)]}."""
    rows = cr.all_rows(data)
    order = data.get('trades_order') if axis != 'model' else None
    open_m = cr.matrix(rows, axis, cr.OPEN, order)
    new_m = cr.matrix(rows, axis, ['New'], order, labels=open_m['labels'])
    return {'axis': axis, 'open': open_m, 'new': new_m, 'pairs': cr.pair_tally(rows, axis)}


def peak_of(m):
    return max([v for row in m['grid'] for v in row if v] or [0])


def matrix_html(m, title, note=None):
    """A heat table for the pyNavis output window (its CSS variables), as trusted HTML."""
    labels = m['labels']
    parts = [u'<div style="margin:16px 0 4px;font-size:14px;font-weight:600">%s</div>' % escape(title)]
    if note:
        parts.append(u'<div style="color:var(--muted);margin:0 0 6px">%s</div>' % escape(note))
    if not labels or not m['total']:
        parts.append(u'<div style="color:var(--muted)">No clashes.</div>')
        return u''.join(parts)
    peak = peak_of(m)
    head = [u'<th></th>'] + [u'<th class="num" style="white-space:normal;max-width:120px">%s</th>' % escape(l)
                             for l in labels] + [u'<th class="num">Involving</th>']
    parts.append(u'<table class="pynavis" style="width:auto"><tr>%s</tr>' % u''.join(head))
    for r, label in enumerate(labels):
        cells = [u'<td style="font-weight:600;white-space:nowrap">%s</td>' % escape(label)]
        for c in range(len(labels)):
            value = m['grid'][r][c]
            if value is None:
                cells.append(u'<td style="background:var(--surface)"></td>')
                continue
            step = cr.heat_step(value, peak)
            if not step:
                cells.append(u'<td class="num"></td>')
                continue
            style = u'background:color-mix(in srgb, var(--chart-1) %d%%, var(--bg));color:var(--fg)' % HEAT_PERCENT[step]
            if step >= 5:
                style += u';font-weight:600'
            cells.append(u'<td class="num" style="%s" title="%s / %s: %s">%s</td>' % (
                style, escape(label), escape(labels[c]), '{:,}'.format(value), '{:,}'.format(value)))
        cells.append(u'<td class="num">%s</td>' % '{:,}'.format(m['involving'][r]))
        parts.append(u'<tr>%s</tr>' % u''.join(cells))
    parts.append(u'</table>')
    return u''.join(parts)


def pairs_html(pairs, axis, limit=TOP_PAIRS):
    rows = [u'<tr><th>%s</th><th>Clashes with</th><th class="num">Open</th><th class="num">New</th></tr>'
            % escape(axis_word(axis).capitalize())]
    for a, b, n_open, n_new in pairs[:limit]:
        rows.append(u'<tr><td>%s</td><td>%s</td><td class="num">%s</td><td class="num">%s</td></tr>' % (
            escape(a), escape(b), '{:,}'.format(n_open), '{:,}'.format(n_new)))
    return (u'<div style="margin:16px 0 4px;font-size:14px;font-weight:600">Top pairs</div>'
            u'<table class="pynavis" style="width:auto">%s</table>' % u''.join(rows))


def output_html(data, built):
    """Everything the output window shows (trusted HTML)."""
    axis = built['axis']
    word = axis_word(axis)
    tests = data.get('tests') or []
    head = (u'<div style="font-size:18px;font-weight:600;margin:0 0 2px">Clash count matrix: %s against %s</div>'
            u'<div style="color:var(--muted)">%s, %s. Open means New, Active or Reviewed. Each clash counts once, '
            u'above the diagonal; Involving counts every clash a %s is part of.</div>' % (
                escape(word), escape(word), escape(data.get('file') or 'Untitled'),
                escape(', '.join(t['name'] for t in tests) if len(tests) <= 3 else cr.plural(len(tests), 'test')),
                escape(word)))
    body = [head,
            matrix_html(built['open'], u'Open clashes', u'%s in total' % cr.plural(built['open']['total'], 'open clash',
                                                                                     'open clashes')),
            matrix_html(built['new'], u'New clashes', u'%s in total' % cr.plural(built['new']['total'], 'new clash',
                                                                                   'new clashes'))]
    if built['pairs']:
        body.append(pairs_html(built['pairs'], axis))
    return u''.join(body)


def write_matrix_sheet(wb, name, title, subtitle, m):
    ws = wb.sheet(name)
    labels = m['labels']
    span = len(labels) + 2
    ws.set_width(0, 24)
    for c in range(1, span):
        ws.set_width(c, 13)
    ws.title(title, span=max(2, span))
    ws.subtitle(subtitle, span=max(2, span))
    if not labels:
        ws.row(['No clashes.'], styles='muted')
        return ws
    header = ws.row([''] + labels + ['Involving'], styles=['header'] + ['m_head'] * len(labels) + ['m_head'],
                    height=32)
    ws.freeze(header + 1, 1)
    peak = peak_of(m)
    for r, label in enumerate(labels):
        values = [label]
        styles = ['bold']
        for c in range(len(labels)):
            value = m['grid'][r][c]
            if value is None:
                values.append(None)
                styles.append('m_blank')
                continue
            step = cr.heat_step(value, peak)
            values.append(value if value else None)
            styles.append(wb.fill_style(colors.sequential(step / 6.0), base='m_int') if step else 'm_int')
        values.append(m['involving'][r])
        styles.append('m_total')
        ws.row(values, styles=styles)
    ws.skip()
    ws.row(['Darker cells hold more clashes. Cells below the diagonal are not used: each pair is counted once.'],
           styles='muted')
    return ws


def build_workbook(data, built):
    word = axis_word(built['axis'])
    wb = xlsx.Workbook(title='Clash count matrix', author=data.get('user') or None)
    wb.style('m_int', num_format='#,##0', align='center', valign='center')
    wb.style('m_blank', fill='F2F2F2')
    wb.style('m_head', base='header', wrap=True, align='center')
    wb.style('m_total', bold=True, num_format='#,##0', align='center', border='left', border_color='A6A6A6')
    tests = data.get('tests') or []
    generated = data.get('generated')
    where = '%s, %s, %s.' % (data.get('file') or 'Untitled', cr.plural(len(tests), 'test'),
                             generated.strftime('%Y-%m-%d %H:%M') if generated else '')
    write_matrix_sheet(wb, 'Open', 'Open clashes, %s against %s' % (word, word),
                       '%s Open means New, Active or Reviewed.' % where, built['open'])
    write_matrix_sheet(wb, 'New', 'New clashes, %s against %s' % (word, word), where, built['new'])
    ws = wb.sheet('Pairs')
    ws.title('Every %s pair' % word, span=4)
    ws.subtitle(where, span=4)
    header = ws.columns([(word.capitalize(), 26, None), ('Clashes with', 26, None), ('Open', 10, 'int'),
                         ('New', 10, 'int')])
    rows = cr.all_rows(data)
    pairs = cr.pair_tally(rows, built['axis'], open_only=False)
    for a, b, n_open, n_new in pairs:
        ws.row([a, b, n_open, n_new])
    if pairs:
        ws.autofilter(header, header + len(pairs), 0, 3)
    ws = wb.sheet('Tests')
    ws.title('Tests counted', span=4)
    ws.columns([('Test', 40, None), ('Clashes', 10, 'int'), ('Open', 10, 'int'), ('New', 10, 'int')])
    for test in tests:
        tally = cr.counts(test.get('rows') or [])
        ws.row([test.get('path') or test['name'], tally['total'], tally['open'], tally['by_status']['New']])
    return wb


def headline(built):
    """(message, detail) for the toast."""
    word = axis_word(built['axis'], plural=True)
    total = built['open']['total']
    if not total:
        return 'No open clashes between %s' % word, 'Every clash in these tests is approved or resolved.'
    top = built['pairs'][0] if built['pairs'] else None
    detail = ''
    if top:
        detail = 'Most: %s with %s (%s open).' % (top[0], top[1], '{:,}'.format(top[2]))
    return '%s open across %s %s' % (cr.plural(total, 'clash', 'clashes'), '{:,}'.format(len(built['open']['labels'])),
                                     word), detail


# ---- run ----------------------------------------------------------------------------------------


def run(config, doc=None, interactive=True, progress=None):
    """See namo.reports. interactive: the matrices for the output window (printed at once
    without a progress callback, else left in result['output'], a clashrep_out.Page the
    caller shows once its progress window has closed); the workbook is written when
    config['xlsx'] (always when not interactive)."""
    stage = cr.Stage(progress)
    document = cr.active_doc(doc)
    tests, missing = cr.resolve_tests(config.get('tests'), document)
    if not tests:
        if missing:
            return reports.result('warning', 'None of the chosen clash tests is in this model',
                                  'Missing: %s.' % ', '.join(missing))
        return reports.result('info', 'No clash results to count', 'Run your clash tests in Clash Detective first.')
    axis = 'model' if config.get('axis') == 'model' else 'trade'
    data = cr.collect(tests, document, stage.sub(0.0, 0.85), categories=False)
    built = build(data, axis)
    message, detail = headline(built)
    paths = []
    # The output window is printed by the caller once its progress window has closed.
    page = out.Page('Clash Count Matrix').html(output_html(data, built)) if interactive else None
    if config.get('xlsx') or not interactive:
        stage(0.9, 'Writing the workbook')
        path = reports.output_path(config, TITLE, 'xlsx', values=cr.report_values(data))
        try:
            build_workbook(data, built).save(path)
        except (IOError, OSError):
            return out.deliver(reports.result('error', 'Could not save the workbook',
                                              'Close %s in Excel, then try again.' % os.path.basename(path)),
                               page, progress)
        paths.append(path)
        detail = ('%s Saved %s.' % (detail, os.path.basename(path))).strip()
        if page is not None:
            page.saved(paths)
    stage(1.0, 'Done')
    level = 'warning' if missing else 'success'
    if missing:
        detail = ('%s Not found: %s.' % (detail, ', '.join(missing))).strip()
    return out.deliver(reports.result(level, message, detail, paths=paths), page, progress)

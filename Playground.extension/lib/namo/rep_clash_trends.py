# -*- coding: utf-8 -*-
"""Clash Trends: open and resolved clashes over the model's clash snapshots.

One point per snapshot (Snapshot, or the automatic snapshot on save), plus the current
state as a last 'Now' point when config['current'] (it reads the tests). Series: open and
resolved for the chosen tests together, or open per test. Between consecutive points the
burn-down table also gives new and fixed clashes (clashdata.compare on the stored rows)
and the change in open clashes; a snapshot that lacks some chosen tests is marked
'2 of 3' in the Tests column.

Interactive runs draw the line chart (pynavis output.chart_line) with a legend and print
the burn-down table in the output window. Files: a workbook (sheets Trend and Open by
test) and/or a CSV of the burn-down table.

Implements the namo.reports rep_<id>.py contract; the builders are pure.
"""

import io
import os

from namo import clashrep_history as hist
from namo import clashrep_out as out
from namo import clashreport as cr
from namo import reports, xlsx

TITLE = 'Clash Trends'
NAME_TEMPLATE = '{file} - Clash trends - {date}'
FLOW_MAX = 60                     # snapshots whose rows are loaded for new/fixed counts
HEADERS = ['When', 'Label', 'Tests', 'Open', 'Resolved', 'Total', 'New', 'Fixed', 'Change']


def default_config():
    return reports.base_config(tests=[], series='total', current=True, flow=True, xlsx=True, csv=False,
                               path='', name_template=NAME_TEMPLATE)


def describe(config):
    series = 'open per test' if config.get('series') == 'per_test' else 'open and resolved'
    return '%s, %s%s' % (cr.tests_text(config.get('tests')), series,
                         ', with the current state' if config.get('current', True) else '')


# ---- pure ---------------------------------------------------------------------------------------


def series_of(points, names, mode):
    """[(name, values)] for the chart: ('Open', ...), ('Resolved', ...) or one per test."""
    if mode == 'per_test':
        return [(name, [p['per_test'].get(name) for p in points]) for name in names]
    return [('Open', [p['open'] for p in points]), ('Resolved', [p['closed'] for p in points])]


def change_text(value):
    if value is None:
        return ''
    if value > 0:
        return '+' + '{:,}'.format(value)
    return '{:,}'.format(value)


def trend_message(points):
    """'610 open now, down 232 since 2026-08-01' (the toast line)."""
    if not points:
        return 'No points to draw'
    now = points[-1]['open']
    head = '%s open now' % '{:,}'.format(now)
    if len(points) < 2:
        return head
    first = points[0]
    change = now - first['open']
    since = first['time'].strftime('%Y-%m-%d') if first['time'] is not None else 'the first snapshot'
    if not change:
        return '%s, no change since %s' % (head, since)
    return '%s, %s %s since %s' % (head, 'down' if change < 0 else 'up', '{:,}'.format(abs(change)), since)


def table_rows(points, labels, flow):
    """Burn-down rows with Change as signed text."""
    rows = hist.burndown_rows(points, labels, flow)
    return [r[:-1] + [change_text(r[-1])] for r in rows]


def span_text(points, names):
    """'12 snapshots from 2026-08-01 to 2026-10-04 and the current state, 3 tests.'"""
    snaps = [p for p in points if p['id'] is not None]
    parts = [cr.plural(len(snaps), 'snapshot')]
    times = [p['time'] for p in snaps if p['time'] is not None]
    if times:
        first, last = min(times), max(times)
        parts.append('from %s to %s' % (first.strftime('%Y-%m-%d'), last.strftime('%Y-%m-%d'))
                     if first.date() != last.date() else 'on %s' % first.strftime('%Y-%m-%d'))
    text = ' '.join(parts)
    if any(p['id'] is None for p in points):
        text += ' and the current state'
    return '%s, %s.' % (text, cr.plural(len(names), 'test'))


def output_html_head(points, names):
    return out.heading('Clash trends', '%s %s' % (span_text(points, names), hist.trend_summary(points)))


def output_html_table(points, labels, flow):
    rows = table_rows(points, labels, flow)
    html = out.subheading('Burn-down', 'Open = New, Active or Reviewed. Resolved = Resolved or Approved. New and '
                          'fixed are counted against the point before.')
    html += out.table(HEADERS, rows, numeric=range(3, 9))
    if any(p['partial'] for p in points):
        html += out.note('A snapshot that does not hold every chosen test shows "n of m" tests; in the per-test '
                         'chart a missing test plots as zero.')
    return html


def build_workbook(points, names, labels, flow, data_file, generated=None):
    wb = xlsx.Workbook(title='Clash trends')
    sub = '%s %s' % (data_file or 'Untitled', span_text(points, names))
    ws = wb.sheet('Trend')
    ws.title('Clash trends', span=len(HEADERS))
    ws.subtitle(sub, span=len(HEADERS))
    summary = hist.trend_summary(points)
    if summary:
        ws.subtitle(summary, span=len(HEADERS))
    header = ws.columns([('When', 18, None), ('Label', 30, None), ('Tests', 9, None), ('Open', 10, 'int'),
                         ('Resolved', 10, 'int'), ('Total', 10, 'int'), ('New', 9, 'int'), ('Fixed', 9, 'int'),
                         ('Change', 10, 'int')])
    rows = hist.burndown_rows(points, labels, flow)
    for row in rows:
        ws.row(row)
    if rows:
        ws.autofilter(header, header + len(rows), 0, len(HEADERS) - 1)
    ws = wb.sheet('Open by test')
    ws.title('Open clashes per test', span=max(2, len(names) + 1))
    ws.subtitle('Blank where a snapshot does not hold the test.', span=max(2, len(names) + 1))
    ws.columns([('When', 18, None)] + [(name, max(10, min(30, len(name) + 2)), 'int') for name in names])
    for point, label in zip(points, labels):
        ws.row([label] + [point['per_test'].get(name) for name in names])
    return wb


def write_csv(path, points, labels, flow):
    """The burn-down table as UTF-8 CSV with a byte order mark (so Excel reads accents),
    written in one go: IronPython's utf-8-sig writer repeats the mark on every write."""
    import csv
    from namo import paths
    rows = hist.burndown_rows(points, labels, flow)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\r\n')
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow(['' if v is None else v for v in row])
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return paths.atomic_write_bytes(path, b'\xef\xbb\xbf' + buffer.getvalue().encode('utf-8'))


# ---- run ----------------------------------------------------------------------------------------


def run(config, doc=None, interactive=True, progress=None):
    """See namo.reports. interactive: the chart and table for the output window (printed
    at once without a progress callback, else left in result['output']: see
    clashrep_out.deliver)."""
    from namo import clashdata
    stage = cr.Stage(progress)
    document = cr.active_doc(doc)
    doc_path, stem, _title = cr.file_info(document)
    if not doc_path:
        return reports.result('info', 'Save the model first',
                              'Clash snapshots are kept per model file, so an unsaved model has none.')
    entries = clashdata.list_history(doc_path)
    if not entries:
        return reports.result('info', 'No clash snapshots yet',
                              'Take one with Snapshot (or turn on automatic snapshots), then come back after the next run.')
    names = None
    current = None
    current_rows = None
    missing = []
    if config.get('tests') or config.get('current', True):
        tests, missing = cr.resolve_tests(config.get('tests'), document)
        if config.get('tests'):
            names = clashdata.unique_names([t.DisplayName for t in tests])
        if config.get('current', True) and tests:
            data = cr.collect(tests, document, stage.sub(0.0, 0.5), categories=False)
            current_rows = dict((t['name'], t['rows']) for t in data['tests'])
            current = {'time': data['generated'],
                       'counts': dict((name, clashdata.counts(current_rows[name])) for name in current_rows)}
    points, names = hist.trend_points(entries, names, current)
    flow = [None] * len(points)
    if config.get('flow', True) and len(points) > 1:
        snaps = [p for p in points if p['id'] is not None]
        loaded = set(p['id'] for p in snaps[-FLOW_MAX:])
        rows_per_point = []
        for index, p in enumerate(points):
            stage(0.5 + 0.35 * index / float(len(points)), 'Comparing snapshots')
            if p['id'] is None:
                rows_per_point.append(current_rows)
            elif p['id'] in loaded:
                rows_per_point.append(clashdata.load_history(doc_path, p['id']))
            else:
                rows_per_point.append(None)
        flow = hist.flows(rows_per_point, names)
    labels = hist.point_labels(points)
    message = trend_message(points)
    detail = hist.trend_summary(points) or 'Take another snapshot after the next run to see a trend.'
    page = None
    if interactive:
        # Printed by the caller once its progress window has closed.
        page = out.Page('Clash Trends').html(output_html_head(points, names))
        series = series_of(points, names, config.get('series'))
        if len(points) > 1:
            page.html(out.legend([name for name, _values in series]))
            page.line_chart(hist.thin(labels), dict((name, [v if v is not None else 0 for v in values])
                                                    for name, values in series),
                            'Open clashes per test' if config.get('series') == 'per_test'
                            else 'Open and resolved clashes')
        page.html(output_html_table(points, labels, flow))
    paths = []
    values = cr.file_values(stem)
    try:
        if config.get('xlsx') or (not interactive and not config.get('csv')):
            stage(0.9, 'Writing the workbook')
            path = reports.output_path(config, TITLE, 'xlsx', values=values)
            build_workbook(points, names, labels, flow, stem).save(path)
            paths.append(path)
        if config.get('csv'):
            if paths:
                path = os.path.splitext(paths[0])[0] + '.csv'
            else:
                path = reports.output_path(config, TITLE, 'csv', values=values)
            write_csv(path, points, labels, flow)
            paths.append(path)
    except (IOError, OSError) as error:
        return out.deliver(reports.result('error', 'Could not save the trend file',
                                          'Close it in Excel, then try again (%s).' % error), page, progress)
    if paths:
        detail = '%s Saved %s.' % (detail, ', '.join(os.path.basename(p) for p in paths))
        if page is not None:
            page.saved(paths)
    stage(1.0, 'Done')
    level = 'warning' if missing else 'success'
    if missing:
        detail += ' Not found now: %s.' % ', '.join(missing)
    return out.deliver(reports.result(level, message, detail, paths=paths), page, progress)

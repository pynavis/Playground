# -*- coding: utf-8 -*-
"""Clash Delta: the chosen tests now against a clash snapshot.

Per test and in total: open clashes then and now, new (open now, no match then), fixed
(open then, now gone or closed, and which), still open, and status changes. Matching is
namo.clashdata.compare: the same two elements with the clash centre within 0.1 m. The
default snapshot is the latest one taken before today (else the latest), so a morning
run compares with yesterday.

Interactive runs print the summary, the per-test table and the new, fixed and changed
clashes (new ones with Show links) in the output window, and return the new clashes'
items in result['new_items'] for the tool's "select" option. The workbook holds the same
in sheets Summary, New, Fixed, Status changed and Still open.

Implements the namo.reports rep_<id>.py contract; the builders are pure.
"""

import os

from namo import clashrep_history as hist
from namo import clashrep_out as out
from namo import clashreport as cr
from namo import reports, xlsx

TITLE = 'Clash Delta'
NAME_TEMPLATE = '{file} - Clash delta - {date}'
SHOWN = 100                     # rows per list in the output window (the workbook has all)


def default_config():
    return reports.base_config(tests=[], baseline='auto', xlsx=True, path='', name_template=NAME_TEMPLATE)


def describe(config):
    ref = str(config.get('baseline') or 'auto')
    against = 'the latest snapshot before today' if ref.lower() in ('', 'auto') else ref
    return '%s against %s' % (cr.tests_text(config.get('tests')), against)


# ---- pure ---------------------------------------------------------------------------------------


def history_dist(row, unit):
    return cr.to_unit(row.get('distance_m'), unit) if row.get('distance_m') is not None else None


def summary_rows(d):
    rows = []
    for t in d['tests']:
        if t['baseline']:
            rows.append([t['test'], t['then_open'], t['now_open'], len(t['new']), len(t['fixed']),
                         len(t['persisting']), len(t['changed']), t['net']])
        else:
            rows.append([t['test'], None, t['now_open'], None, None, None, None, None])
    totals = d['totals']
    rows.append(['Total', totals['then_open'], totals['now_open'], totals['new'], totals['fixed'],
                 totals['persisting'], totals['changed'], totals['net']])
    return rows


SUMMARY_HEADERS = ['Test', 'Open then', 'Open now', 'New', 'Fixed', 'Still open', 'Status changed', 'Change']


def change_text(n):
    if n is None:
        return ''
    if n == 0:
        return 'no change'
    return '%s %s' % ('down' if n < 0 else 'up', '{:,}'.format(abs(n)))


def snapshot_line(entry, now):
    when = hist.entry_time(entry)
    label = (entry.get('label') or '').strip()
    stamp = when.strftime('%Y-%m-%d %H:%M') if when else ''
    named = '%s (%s)' % (label, stamp) if label and label[:16].replace('T', ' ') != stamp else stamp
    return 'Snapshot %s, %s.' % (named, hist.age_text(when, now)) if when else 'Snapshot %s.' % named


def output_html(d, entry, data, link=None):
    """The output-window page (trusted HTML). link(row) -> HTML for a new clash's Show
    link, or None."""
    unit = data.get('unit') or 'm'
    now = data.get('generated')
    t = d['totals']
    parts = [out.heading('Clash delta: now against the snapshot',
                         '%s Clashes match when they involve the same two elements within 0.1 m.'
                         % snapshot_line(entry, now))]
    parts.append(out.kpi_strip([('New', t['new'], 'open now, not there then'),
                                ('Fixed', t['fixed'], 'gone or closed'),
                                ('Still open', t['persisting']),
                                ('Status changed', t['changed']),
                                ('Open', t['now_open'], 'was %s, %s' % ('{:,}'.format(t['then_open']),
                                                                        change_text(t['net'])))]))
    rows = summary_rows(d)
    printable = [r[:-1] + [change_text(r[-1])] for r in rows]
    parts.append(out.table(SUMMARY_HEADERS, printable, numeric=range(1, 7)))
    if d['without_baseline']:
        parts.append(out.note('Not in the snapshot, so counted as open now only: %s.' % ', '.join(d['without_baseline'])))

    new_rows = [(t_['test'], r) for t_ in d['tests'] for r in t_['new']]
    if new_rows:
        table_rows = []
        for test, r in new_rows[:SHOWN]:
            table_rows.append([test, r.get('name'), r.get('status'), cr.number_text(r.get('dist'), unit),
                               ', '.join(x for x in (r.get('level'), r.get('grid')) if x),
                               '%s\n%s' % (r.get('item_a_name') or '', r.get('item_b_name') or ''),
                               (link(r) if link else None) or ''])
        parts.append(out.subheading('New clashes', '%s, worst first in each test (the smallest distance).'
                                    % cr.plural(len(new_rows), 'new clash', 'new clashes')))
        parts.append(out.table(['Test', 'Clash', 'Status', 'Distance (%s)' % unit, 'Location', 'Items', ''],
                               table_rows, numeric=[3], trusted=[6], limit=None))
        if len(new_rows) > SHOWN:
            parts.append(out.note('Showing the first %s of %s; the workbook lists them all.'
                                  % ('{:,}'.format(SHOWN), '{:,}'.format(len(new_rows)))))
    fixed = [(t_['test'], r, how) for t_ in d['tests'] for r, how in t_['fixed']]
    if fixed:
        table_rows = [[test, r.get('name'), r.get('status'), how, ', '.join(x for x in (r.get('level'), r.get('grid')) if x),
                       ' / '.join(x for x in (r.get('trade_a'), r.get('trade_b')) if x)] for test, r, how in fixed]
        parts.append(out.subheading('Fixed clashes', '%s since the snapshot.' % cr.plural(len(fixed), 'clash',
                                                                                          'clashes')))
        parts.append(out.table(['Test', 'Clash', 'Was', 'Now', 'Location', 'Trades'], table_rows, limit=SHOWN,
                               more='Showing the first %s of %s; the workbook lists them all.'
                               % ('{:,}'.format(SHOWN), '{:,}'.format(len(fixed)))))
    changed = [(t_['test'], o, n) for t_ in d['tests'] for o, n in t_['changed']]
    if changed:
        table_rows = [[test, n.get('name'), o.get('status'), n.get('status'), n.get('assigned') or '']
                      for test, o, n in changed]
        parts.append(out.subheading('Status changes', cr.plural(len(changed), 'clash', 'clashes') + '.'))
        parts.append(out.table(['Test', 'Clash', 'Was', 'Now', 'Assigned to'], table_rows, limit=SHOWN,
                               more='Showing the first %s of %s; the workbook lists them all.'
                               % ('{:,}'.format(SHOWN), '{:,}'.format(len(changed)))))
    if not new_rows and not fixed and not changed:
        parts.append(out.note('Nothing changed since the snapshot.'))
    return u''.join(parts)


def sort_new(d):
    """Puts each test's new clashes worst first (smallest distance: the deepest penetration
    or the tightest clearance), then by name."""
    from namo import naming
    for t in d['tests']:
        t['new'].sort(key=lambda r: (r.get('dist') if r.get('dist') is not None else 0.0,
                                     naming.natural_key(r.get('name') or '')))
    return d


def build_workbook(d, entry, data):
    unit = data.get('unit') or 'm'
    wb = xlsx.Workbook(title='Clash delta', author=data.get('user') or None)
    wb.style('dist', num_format=cr.UNIT_FORMATS.get(unit, '#,##0.000'))
    wb.style('t_label', bold=True, border='top', border_color='A6A6A6')
    wb.style('t_int', bold=True, border='top', border_color='A6A6A6', num_format='#,##0')
    sub = '%s %s, now %s.' % (data.get('file') or 'Untitled', snapshot_line(entry, data.get('generated')),
                              data['generated'].strftime('%Y-%m-%d %H:%M') if data.get('generated') else '')

    ws = wb.sheet('Summary')
    ws.title('Clash delta: now against the snapshot', span=8)
    ws.subtitle(sub, span=8)
    ws.subtitle('Clashes match when they involve the same two elements within 0.1 m. Open means New, Active '
                'or Reviewed.', span=8)
    ws.columns([('Test', 34, None), ('Open then', 11, 'int'), ('Open now', 11, 'int'), ('New', 9, 'int'),
                ('Fixed', 9, 'int'), ('Still open', 11, 'int'), ('Status changed', 15, 'int'), ('Change', 10, 'int')],
               freeze=False)
    rows = summary_rows(d)
    for row in rows[:-1]:
        ws.row(row)
    ws.row(rows[-1], styles=['t_label'] + ['t_int'] * 7)
    if d['without_baseline']:
        ws.skip()
        ws.row(['Not in the snapshot (counted as open now only): %s.' % ', '.join(d['without_baseline'])],
               styles='muted')

    def table(name, title, columns, rows_):
        sheet = wb.sheet(name)
        sheet.title(title, span=len(columns))
        sheet.subtitle(sub, span=len(columns))
        header = sheet.columns(columns)
        for values, styles in rows_:
            sheet.row(values, styles=styles)
        if rows_:
            sheet.autofilter(header, header + len(rows_), 0, len(columns) - 1)
        else:
            sheet.row(['None.'], styles='muted')

    current_cols = [('Test', 26, None), ('Clash', 14, None), ('Status', 11, None), ('Distance (%s)' % unit, 13, 'dist'),
                    ('Level', 13, None), ('Grid', 10, None), ('Item A', 28, None), ('Item B', 28, None),
                    ('Trade A', 14, None), ('Trade B', 14, None), ('Assigned to', 16, None), ('Found', 11, 'date'),
                    ('Age (days)', 10, 'int')]

    def current(r, test):
        return ([test, r.get('name'), r.get('status'), r.get('dist'), r.get('level') or '', r.get('grid') or '',
                 r.get('item_a_name') or '', r.get('item_b_name') or '', r.get('trade_a') or '', r.get('trade_b') or '',
                 r.get('assigned') or '', r.get('found'), r.get('age')],
                [None, None, xlsx.status_style(r.get('status'))])

    table('New', 'New clashes', current_cols, [current(r, t['test']) for t in d['tests'] for r in t['new']])
    table('Fixed', 'Fixed clashes', [('Test', 26, None), ('Clash', 14, None), ('Was', 11, None), ('Now', 11, None),
                                     ('Distance then (%s)' % unit, 17, 'dist'), ('Level', 13, None), ('Grid', 10, None),
                                     ('Trade A', 14, None), ('Trade B', 14, None)],
          [([t['test'], r.get('name'), r.get('status'), how, history_dist(r, unit), r.get('level') or '',
             r.get('grid') or '', r.get('trade_a') or '', r.get('trade_b') or ''],
            [None, None, xlsx.status_style(r.get('status')), xlsx.status_style(how)])
           for t in d['tests'] for r, how in t['fixed']])
    table('Status changed', 'Status changes', [('Test', 26, None), ('Clash', 14, None), ('Was', 11, None),
                                               ('Now', 11, None), ('Assigned to', 16, None), ('Level', 13, None),
                                               ('Grid', 10, None)],
          [([t['test'], n.get('name'), o.get('status'), n.get('status'), n.get('assigned') or '',
             n.get('level') or '', n.get('grid') or ''],
            [None, None, xlsx.status_style(o.get('status')), xlsx.status_style(n.get('status'))])
           for t in d['tests'] for o, n in t['changed']])
    table('Still open', 'Still open', current_cols,
          [current(r, t['test']) for t in d['tests'] for r in t['persisting']])
    return wb


# ---- run ----------------------------------------------------------------------------------------


def run(config, doc=None, interactive=True, progress=None):
    """See namo.reports. Adds result['delta'] (the hist.delta dict) and, interactive,
    result['new_items'] (ModelItems of the new clashes) for the tool's select option and
    the output-window page (result['output'] behind a progress callback: see
    clashrep_out.deliver)."""
    from namo import clashdata
    stage = cr.Stage(progress)
    document = cr.active_doc(doc)
    doc_path, _stem, _title = cr.file_info(document)
    if not doc_path:
        return reports.result('info', 'Save the model first',
                              'Clash snapshots are kept per model file, so an unsaved model has none.')
    entries = clashdata.list_history(doc_path)
    if not entries:
        return reports.result('info', 'No clash snapshots yet',
                              'Take one with Snapshot (or turn on automatic snapshots), then compare after the next run.')
    entry = hist.find_entry(entries, config.get('baseline'))
    if entry is None:
        return reports.result('warning', 'That snapshot is not there',
                              'No snapshot matches %s; pick another one.' % config.get('baseline'))
    old = clashdata.load_history(doc_path, entry['id'])
    if old is None:
        return reports.result('error', 'The snapshot could not be read',
                              'Its file is missing or damaged; pick another snapshot.')
    tests, missing = cr.resolve_tests(config.get('tests'), document)
    if not tests:
        return reports.result('info', 'No clash results to compare', 'Run your clash tests in Clash Detective first.')
    data = cr.collect(tests, document, stage.sub(0.0, 0.8), categories=False)
    d = sort_new(hist.delta(old, dict((t['name'], t['rows']) for t in data['tests']),
                            [t['name'] for t in data['tests']]))
    message = hist.delta_headline(d)
    detail = snapshot_line(entry, data['generated'])
    paths = []
    extra = {}
    page = None
    if interactive:
        live = data.get('live') or {}

        def link(row):
            try:
                from pynavis import output
                result = live[row['test']][row['id']]
                item = result.Item1 if result.Item1 is not None else result.Item2
                return output.element_link(item, 'Show') if item is not None else ''
            except Exception:
                return ''
        # Built and printed by the caller once its progress window has closed: even
        # output.element_link opens the output window.
        page = out.Page('Clash Delta').later(lambda: output_html(d, entry, data, link))
        found = []
        for t in d['tests']:
            for row in t['new']:
                try:
                    result = live[t['test']][row['id']]
                except Exception:
                    continue
                for item in (result.Item1, result.Item2):
                    if item is not None:
                        found.append(item)
        extra['new_items'] = found
    if config.get('xlsx') or not interactive:
        stage(0.9, 'Writing the workbook')
        path = reports.output_path(config, TITLE, 'xlsx', values=cr.report_values(data))
        try:
            build_workbook(d, entry, data).save(path)
        except (IOError, OSError):
            failed = reports.result('error', 'Could not save the workbook',
                                    'Close %s in Excel, then try again.' % os.path.basename(path))
            failed.update(extra)
            return out.deliver(failed, page, progress)
        paths.append(path)
        detail = '%s Saved %s.' % (detail, os.path.basename(path))
        if page is not None:
            page.saved(paths)
    stage(1.0, 'Done')
    level = 'success'
    if missing or d['without_baseline']:
        level = 'warning'
        gaps = list(missing) + list(d['without_baseline'])
        detail = '%s Not compared: %s.' % (detail, ', '.join(gaps))
    result = reports.result(level, message, detail, paths=paths)
    result['delta'] = d
    result.update(extra)
    return out.deliver(result, page, progress)

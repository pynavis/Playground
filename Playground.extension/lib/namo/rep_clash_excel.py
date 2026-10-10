# -*- coding: utf-8 -*-
"""Clash Excel Report: one styled workbook for the chosen clash tests.

Sheets, in order:
  * Summary: a headline band (clashes, open, each status, oldest open), one row per test
    (type, tolerance, last run and whether it is out of date, counts per status in the
    Clash Detective colours, a link to the test's sheet), totals, then the open clashes
    by trade pair, by assignee and by level.
  * One sheet per test: a row per listed clash with an optional 160 x 90 thumbnail,
    name, group, status (coloured), distance in report units, level, grid, items,
    models, trades, categories, assignee, found date, age, approval, description,
    comments. Frozen header and first columns, autofilter, thumbnails anchored to their
    cells so filtering hides them with their rows.
  * All clashes (two or more tests): every listed clash in one table with a Test column,
    for pivots.

Implements the namo.reports rep_<id>.py contract; build_workbook() is pure (tested with
openpyxl), run() reads Navisworks.
"""

import os

from namo import clashreport as cr
from namo import naming, reports, xlsx

TITLE = 'Clash Excel Report'
NAME_TEMPLATE = '{file} - Clash report - {date}'
SUMMARY = 'Summary'
ALL_SHEET = 'All clashes'
TOP_ROWS = 15                     # rows in each Summary breakdown

SUMMARY_COLUMNS = [('Test', 34), ('Type', 18), ('Tolerance', 12), ('Last run', 17), ('Test status', 13),
                   ('Clashes', 10), ('New', 9), ('Active', 9), ('Reviewed', 10), ('Approved', 10),
                   ('Resolved', 10), ('Open', 9), ('Listed', 9), ('Sheet', 10)]


def default_config():
    return reports.base_config(tests=[], statuses=list(cr.OPEN), images=True, image_cap=cr.IMAGE_CAP,
                               categories=True, combined=True, path='', name_template=NAME_TEMPLATE)


def describe(config):
    return '%s, %s%s' % (cr.tests_text(config.get('tests')), cr.statuses_text(config.get('statuses')),
                         ', with thumbnails' if config.get('images') else '')


# ---- pure: workbook --------------------------------------------------------------------------


def define_styles(wb, unit):
    """The named styles this report uses (on top of xlsx's built-ins)."""
    wb.style('c', valign='center')
    wb.style('c_wrap', valign='center', wrap=True)
    wb.style('c_int', valign='center', num_format='#,##0')
    wb.style('c_dist', valign='center', num_format=cr.UNIT_FORMATS.get(unit, '#,##0.000'))
    wb.style('c_date', valign='center', num_format='yyyy-mm-dd')
    wb.style('c_datetime', valign='center', num_format='yyyy-mm-dd hh:mm')
    wb.style('c_muted', valign='center', color='6B6B6B')
    wb.style('c_zero', valign='center', color='A6A6A6', num_format='#,##0')
    wb.style('c_warn', base='warn', valign='center')
    wb.style('c_link', base='link', valign='center')
    wb.style('section', bold=True, size=12)
    wb.style('note', color='6B6B6B', italic=True)
    wb.style('kpi_label', color='6B6B6B', size=9, valign='bottom')
    wb.style('kpi_value', size=20, valign='center', num_format='#,##0', align='left')
    wb.style('total_label', bold=True, border='top', border_color='A6A6A6')
    wb.style('total_int', bold=True, border='top', border_color='A6A6A6', num_format='#,##0')
    builtin = dict(xlsx.BUILTIN_STYLES)
    for status in cr.STATUSES:
        low = status.lower()
        base = 'status_' + low
        wash = builtin[base]
        wb.style('c_' + low, base=base, valign='center', align='center')
        wb.style('n_' + low, base=base, num_format='#,##0')
        wb.style('h_' + low, base='header', fill=wash['fill'], color=wash['color'])
        wb.style('kpi_' + low, base=base, size=9, valign='bottom')


def clash_columns(unit, images, with_test=False):
    """[(header, width, style)] of a clash table."""
    cols = []
    if images:
        cols.append(('Image', 24, 'c'))
    if with_test:
        cols.append(('Test', 26, 'c'))
    cols += [('Clash', 14, 'c'), ('Group', 22, 'c_wrap'), ('Status', 11, 'c'),
             ('Distance (%s)' % unit, 13, 'c_dist'), ('Level', 13, 'c'), ('Grid', 11, 'c'),
             ('Item A', 28, 'c_wrap'), ('Item B', 28, 'c_wrap'), ('Model A', 20, 'c'), ('Model B', 20, 'c'),
             ('Trade A', 14, 'c'), ('Trade B', 14, 'c'), ('Category A', 18, 'c'), ('Category B', 18, 'c'),
             ('Assigned to', 16, 'c'), ('Found', 11, 'c_date'), ('Age (days)', 10, 'c_int'),
             ('Approved by', 14, 'c'), ('Approved', 11, 'c_date'), ('Description', 34, 'c_wrap'),
             ('Comments', 10, 'c_int')]
    return cols


def clash_values(row, images, with_test=False):
    """Cell values for one shaped row, in clash_columns order."""
    values = []
    if images:
        values.append(None)
    if with_test:
        values.append(row.get('test') or '')
    values += [row.get('name') or '', row.get('group') or '', row.get('status') or '', row.get('dist'),
               row.get('level') or '', row.get('grid') or '', row.get('item_a_name') or '',
               row.get('item_b_name') or '', row.get('model_a') or '', row.get('model_b') or '',
               row.get('trade_a') or '', row.get('trade_b') or '', row.get('cat_a') or '',
               row.get('cat_b') or '', row.get('assigned') or '', row.get('found'), row.get('age'),
               row.get('approved_by') or '', row.get('approved'), row.get('description') or '',
               row.get('comments') if row.get('comments') else None]
    return values


def clash_styles(row, images, with_test=False):
    """Per-cell styles: only the status cell differs from its column style."""
    status_col = (1 if images else 0) + (1 if with_test else 0) + 2
    styles = [None] * (status_col + 1)
    style = 'c_' + str(row.get('status') or '').lower()
    styles[status_col] = style if style[2:] in [s.lower() for s in cr.STATUSES] else None
    return styles


def subtitle_text(data, statuses):
    parts = []
    if data.get('file'):
        parts.append(data['file'])
    generated = data.get('generated')
    if generated is not None:
        parts.append(generated.strftime('%Y-%m-%d %H:%M'))
    if data.get('user'):
        parts.append('by %s' % data['user'])
    head = ', '.join(parts)
    tail = 'Distances in %s (negative = penetration). Listed: %s.' % (data.get('unit') or 'm',
                                                                        cr.statuses_text(statuses))
    return '%s. %s' % (head, tail) if head else tail


def _int_or_zero(value, style):
    return (value, style if value else 'c_zero')


def write_summary(ws, data, statuses, sheets, title):
    """Fills the Summary sheet. sheets: {test name: Worksheet} for the links."""
    unit = data.get('unit') or 'm'
    span = len(SUMMARY_COLUMNS)
    for col, (_header, width) in enumerate(SUMMARY_COLUMNS):
        ws.set_width(col, width)
    ws.title(title, span=span, height=26)
    ws.subtitle(subtitle_text(data, statuses), span=span)
    ws.skip()
    k = cr.kpis(data)
    labels = ['Clashes', 'Open'] + list(cr.STATUSES) + ['Oldest open (days)']
    label_styles = ['kpi_label', 'kpi_label'] + ['kpi_' + s.lower() for s in cr.STATUSES] + ['kpi_label']
    ws.row(labels, styles=label_styles)
    oldest = k['oldest']
    values = [k['total'], k['open']] + [k['by_status'][s] for s in cr.STATUSES] + \
        [oldest['age'] if oldest else None]
    ws.row(values, styles='kpi_value', height=30)
    if oldest:
        found = oldest.get('found')
        ws.row(['Oldest open clash: %s in %s%s.' % (oldest.get('name') or '', oldest.get('test') or '',
                                                    ', found %s' % found.strftime('%Y-%m-%d') if found else '')],
               styles='muted')
    ws.skip()

    ws.row(['Tests'], styles='section')
    ws.row([h for h, _w in SUMMARY_COLUMNS],
           styles=['header'] * 6 + ['h_' + s.lower() for s in cr.STATUSES] + ['header'] * 3)
    sums = [0] * 8
    for test in data.get('tests') or []:
        tally = cr.counts(test.get('rows') or [])
        listed = len(cr.filter_rows(test.get('rows') or [], statuses))
        state = test.get('state') or ''
        sheet = sheets.get(test['name'])
        link = xlsx.Link('#%s!A1' % xlsx.quote_sheet(sheet.name), 'Open') if sheet is not None else None
        cells = [(test.get('path') or test['name'], 'c'), (test.get('type') or '', 'c'),
                 (cr.length_text(test.get('tolerance_m'), unit) if test.get('tolerance_m') is not None else '', 'c'),
                 (test.get('last_run'), 'c_datetime'),
                 (state, 'c_warn' if state == cr.TEST_STATES['old'] else
                  ('c_muted' if state in (cr.TEST_STATES['new'], cr.TEST_STATES['partial']) else 'c'))]
        cells.append(_int_or_zero(tally['total'], 'c_int'))
        for status in cr.STATUSES:
            cells.append(_int_or_zero(tally['by_status'][status], 'n_' + status.lower()))
        cells.append(_int_or_zero(tally['open'], 'c_int'))
        cells.append(_int_or_zero(listed, 'c_int'))
        cells.append((link, 'c_link'))
        ws.row([c[0] for c in cells], styles=[c[1] for c in cells])
        for i, value in enumerate([tally['total']] + [tally['by_status'][s] for s in cr.STATUSES] +
                                  [tally['open'], listed]):
            sums[i] += value
    ws.row(['Total', '', '', '', ''] + sums + [''],
           styles=['total_label'] * 5 + ['total_int'] * 8 + ['total_label'])

    rows = cr.all_rows(data)
    blocks = [
        ('Open clashes by trade pair', ['Trade A', 'Trade B', 'Open', 'New'],
         [[a, b, n_open, n_new] for a, b, n_open, n_new in cr.pair_tally(rows, 'trade', limit=TOP_ROWS)]),
        ('Open clashes by assignee', ['Assigned to', 'Open', 'Oldest (days)'],
         _assignee_rows(rows)),
        ('Open clashes by level', ['Level', 'Open'], _level_rows(rows)),
    ]
    for heading, headers, block_rows in blocks:
        if not block_rows:
            continue
        ws.skip()
        ws.row([heading], styles='section')
        ws.row(headers, styles='header')
        for values_ in block_rows:
            ws.row(values_, styles=['c_int' if isinstance(v, (int, float)) and not isinstance(v, bool) else 'c'
                                    for v in values_])
    notes = ['Open means New, Active or Reviewed; Approved and Resolved count as closed.'] + \
        list(data.get('notes') or [])
    ws.skip()
    for note in notes:
        ws.row([note], styles='note')


def _level_rows(rows):
    """Open clashes per level in level order ('Level 2' before 'Level 10'), No level last."""
    found = cr.tally(rows, 'level', blank=cr.NO_LEVEL)
    found.sort(key=lambda p: (p[0] == cr.NO_LEVEL, naming.natural_key(p[0])))
    return [[label, n] for label, n in found[:40]]


def _assignee_rows(rows):
    ages = {}
    for row in rows:
        if not cr.is_open(row.get('status')):
            continue
        label = (row.get('assigned') or '').strip() or cr.NOT_ASSIGNED
        if row.get('age') is not None:
            ages[label] = max(ages.get(label, 0), row['age'])
    return [[label, n, ages.get(label)] for label, n in
            cr.tally(rows, 'assigned', blank=cr.NOT_ASSIGNED, limit=TOP_ROWS)]


def write_clash_table(ws, rows, unit, images, with_test=False, heading=None, subtitles=()):
    """Title, subtitles, header and one row per clash (+ thumbnails). Returns the number
    of pictures placed."""
    cols = clash_columns(unit, images, with_test)
    span = len(cols)
    if heading:
        ws.title(heading, span=span, height=24)
    for line in subtitles:
        if line:
            ws.subtitle(line, span=span)
    header = ws.columns(cols)
    ws.freeze(header + 1, (1 if images else 0) + (1 if with_test else 0) + 1)
    if not rows:
        ws.row(['No clashes with these statuses.'], styles='muted')
        return 0
    placed = 0
    for row in rows:
        r = ws.row(clash_values(row, images, with_test), styles=clash_styles(row, images, with_test))
        if images and row.get('image'):
            try:
                ws.image(row['image'], r, 0, width_px=cr.THUMB_W, height_px=cr.THUMB_H, offset_px=(4, 4),
                         fit_cell=True, anchor='cell', description=row.get('name') or 'Clash')
                placed += 1
            except (ValueError, IOError, OSError):
                pass
    ws.autofilter(header, header + len(rows), 0, span - 1)
    return placed


def build_workbook(data, config, title=None):
    """The whole workbook (pure). config: statuses, images, combined."""
    statuses = cr.ordered_statuses(config.get('statuses'))
    images = bool(config.get('images'))
    unit = data.get('unit') or 'm'
    heading = title or ('Clash report: %s' % data['project'] if data.get('project') else 'Clash report')
    wb = xlsx.Workbook(title=heading, author=data.get('user') or None)
    define_styles(wb, unit)
    summary = wb.sheet(SUMMARY)
    summary.tab_color('0078D4')
    sheets = {}
    listed_all = []
    tests = data.get('tests') or []
    for test in tests:
        ws = wb.sheet(test['name'])
        sheets[test['name']] = ws
        listed = cr.filter_rows(test.get('rows') or [], statuses)
        listed_all.extend(listed)
        has_images = images and any(r.get('image') for r in listed)
        tally = cr.counts(test.get('rows') or [])
        lines = ['%s. %s.' % (cr.test_line(test, unit), cr.counts_line(tally)),
                 '%s. Distances in %s.' % (cr.listed_text(len(listed), statuses), unit)]
        write_clash_table(ws, listed, unit, has_images, heading=test['name'], subtitles=lines)
    if config.get('combined', True) and len(tests) > 1:
        ws = wb.sheet(ALL_SHEET)
        write_clash_table(ws, listed_all, unit, False, with_test=True, heading='All listed clashes',
                          subtitles=['%s from %s. Listed: %s.' % (cr.plural(len(listed_all), 'clash', 'clashes'),
                                                                   cr.plural(len(tests), 'test'),
                                                                   cr.statuses_text(statuses))])
    write_summary(summary, data, statuses, sheets, heading)
    return wb


# ---- run ---------------------------------------------------------------------------------------


def prepare(config, doc=None, progress=None, span=(0.0, 0.9)):
    """Reads the tests and makes the thumbnails: (data, folder, problem result or None).
    The caller removes folder (cr.remove_folder) when done. Shared with rep_clash_html and
    rep_per_trade."""
    stage = cr.Stage(progress).sub(span[0], span[1])
    document = cr.active_doc(doc)
    tests, missing = cr.resolve_tests(config.get('tests'), document)
    if not tests:
        if missing:
            return None, None, reports.result('warning', 'None of the chosen clash tests is in this model',
                                              'Missing: %s.' % ', '.join(missing))
        return None, None, reports.result('info', 'No clash results to report',
                                          'Run your clash tests in Clash Detective first.')
    statuses = cr.ordered_statuses(config.get('statuses'))
    data = cr.collect(tests, document, stage.sub(0.0, 0.6 if config.get('images') else 1.0),
                      categories=config.get('categories', True))
    data['missing'] = list(missing)
    for name in missing:
        data['notes'].append('The test %s is not in this model, so it is left out.' % name)
    folder = None
    if config.get('images'):
        cap = int(config.get('image_cap') or 0)
        plan = cr.thumbnail_plan(data, statuses, cap)
        planned = sum(len(plan[name]) for name in plan)
        if planned:
            listed = dict((t['name'], len(cr.filter_rows(t['rows'], statuses))) for t in data['tests'])
            folder = cr.temp_folder()
            try:
                stats = cr.thumbnails(data, plan, folder, document, stage.sub(0.6, 0.4))
            except Exception:
                cr.remove_folder(folder)           # cancelled (or broken): leave nothing behind
                raise
            data['image_stats'] = stats
            note = cr.image_note(stats, planned, cap, cr.over_cap(listed, cap))
            if note:
                data['notes'].append(note)
    return data, folder, None


def outcome(data, path, statuses, noun='clash report'):
    """(level, message, detail) for a finished report file."""
    listed = sum(len(cr.filter_rows(t['rows'], statuses)) for t in data['tests'])
    detail = '%s from %s, in %s' % (cr.plural(listed, 'clash', 'clashes'), cr.plural(len(data['tests']), 'test'),
                                    path)
    stats = data.get('image_stats') or {}
    if stats.get('failed') or stats.get('skipped'):
        return 'warning', 'Saved the %s; some thumbnails are missing' % noun, detail
    if data.get('missing'):
        return 'warning', 'Saved the %s; some tests were not found' % noun, detail
    return 'success', 'Saved the %s' % noun, detail


def run(config, doc=None, interactive=True, progress=None):
    """See namo.reports. Writes the workbook to config['path'] (an explicit file) or
    config['folder'] + config['name_template']."""
    data, folder, problem = prepare(config, doc, progress)
    if problem is not None:
        return problem
    try:
        stage = cr.Stage(progress)
        stage(0.92, 'Writing the workbook')
        wb = build_workbook(data, config)
        path = reports.output_path(config, TITLE, 'xlsx', values=cr.report_values(data))
        try:
            wb.save(path)
        except (IOError, OSError):
            return reports.result('error', 'Could not save the workbook',
                                  'Close %s in Excel, then try again.' % os.path.basename(path))
        stage(1.0, 'Saved')
    finally:
        cr.remove_folder(folder)
    level, message, detail = outcome(data, path, cr.ordered_statuses(config.get('statuses')))
    return reports.result(level, message, detail, paths=[path])

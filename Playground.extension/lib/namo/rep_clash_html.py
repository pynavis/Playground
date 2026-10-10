# -*- coding: utf-8 -*-
"""Clash Dashboard: one standalone HTML page (namo.htmlreport) for the chosen clash tests.

Top to bottom: headline numbers (clashes, open, each status in its Clash Detective
colour, oldest open clash), a status donut and status-by-test bars with a tests table
(type, tolerance, last run, out-of-date flag), where the open clashes are (by level, by
grid, model against model), who holds them and for how long (by assignee, age bands),
the result groups, then every listed clash in a sortable, filterable table with optional
thumbnails. Opens offline anywhere, follows the reader's light or dark theme, prints
light.

Implements the namo.reports rep_<id>.py contract; build_report() is pure.
"""

import base64
import os

from namo import clashrep_svg as svg
from namo import clashreport as cr
from namo import htmlreport, naming, png, reports

TITLE = 'Clash HTML Dashboard'
NAME_TEMPLATE = '{file} - Clash dashboard - {date}'
TABLE_ROWS = 5000
TOP = 15


def default_config():
    return reports.base_config(tests=[], statuses=list(cr.OPEN), images=True, image_cap=cr.IMAGE_CAP,
                               categories=False, path='', name_template=NAME_TEMPLATE)


def describe(config):
    return '%s, table of %s%s' % (cr.tests_text(config.get('tests')), cr.statuses_text(config.get('statuses')),
                                  ', with thumbnails' if config.get('images') else '')


# ---- pure ---------------------------------------------------------------------------------------


def data_uri(path):
    """A data: URI for an image file, or None when it cannot be read."""
    try:
        handle = open(path, 'rb')
        try:
            raw = handle.read()
        finally:
            handle.close()
    except (IOError, OSError, TypeError):
        return None
    mime = png.mime_type(raw)
    if mime is None:
        return None
    encoded = base64.b64encode(raw)
    if not isinstance(encoded, str):
        encoded = encoded.decode('ascii')
    return 'data:%s;base64,%s' % (mime, encoded)


def _level_bars(rows):
    found = cr.tally(rows, 'level', blank=cr.NO_LEVEL)
    found.sort(key=lambda p: (p[0] == cr.NO_LEVEL, naming.natural_key(p[0])))
    return found[:40]


def _subtitle(data):
    parts = []
    if data.get('project'):
        parts.append(data['project'] + (' (%s)' % data['project_number'] if data.get('project_number') else ''))
    elif data.get('doc_title'):
        parts.append(data['doc_title'])
    return ', '.join(parts) or None


def build_report(data, config, title=None):
    """The dashboard as a namo.htmlreport.Report (pure)."""
    statuses = cr.ordered_statuses(config.get('statuses'))
    unit = data.get('unit') or 'm'
    tests = data.get('tests') or []
    rows = cr.all_rows(data)
    k = cr.kpis(data)
    generated = data.get('generated')
    meta = [('Model', data.get('file') or 'Untitled'), ('Tests', len(tests)),
            ('Generated', generated.strftime('%Y-%m-%d %H:%M') if generated else ''),
            ('By', data.get('user') or ''), ('Distances', unit)]
    report = htmlreport.Report(title or 'Clash dashboard', subtitle=_subtitle(data), meta=meta)

    oldest = k['oldest']
    kpis = [('Clashes', k['total'], None, cr.plural(len(tests), 'test')),
            ('Open', k['open'], None, 'New, Active or Reviewed')]
    for status in cr.STATUSES:
        kpis.append((status, k['by_status'][status], status.lower()))
    if oldest is not None:
        kpis.append(('Oldest open (days)', oldest['age'], 'warn' if oldest['age'] > cr.AGE_BUCKETS[-1] else None,
                     '%s, %s' % (oldest.get('name') or '', oldest.get('test') or '')))
    report.kpis(kpis)

    # Status ---------------------------------------------------------------------------------
    report.section('Status', 'Every clash in the chosen tests, in Clash Detective\'s colours.')
    report.html(svg.status_donut(k['by_status'], 'Clashes by status'))
    report.html(svg.stacked_bars([(t['name'], cr.counts(t.get('rows') or [])['by_status']) for t in tests],
                                 'Status by test'))
    test_rows = []
    trusted = set()
    for i, test in enumerate(tests):
        tally = cr.counts(test.get('rows') or [])
        state = test.get('state') or ''
        tone = 'warn' if state == cr.TEST_STATES['old'] else ('neutral' if state else None)
        test_rows.append([test.get('path') or test['name'], test.get('type') or '',
                          cr.length_text(test.get('tolerance_m'), unit) if test.get('tolerance_m') is not None else '',
                          test['last_run'].strftime('%Y-%m-%d %H:%M') if test.get('last_run') else '',
                          htmlreport.status_chip(state, tone) if state else '',
                          tally['total'], tally['open'], tally['by_status']['New']])
        trusted.add((i, 4))
    report.table(['Test', 'Type', 'Tolerance', 'Last run', 'Test status', 'Clashes', 'Open', 'New'], test_rows,
                 cell_html=trusted, caption='Tests', filterable=len(test_rows) > 8)

    # Where ----------------------------------------------------------------------------------
    report.section('Where the open clashes are', 'Open means New, Active or Reviewed.')
    levels = _level_bars(rows)
    report.bar_chart([l for l, _n in levels], [n for _l, n in levels], title='Open clashes by level',
                     value_label='Open clashes')
    grids = [g for g in cr.tally(rows, 'grid', blank=cr.NO_GRID) if g[0] != cr.NO_GRID]
    no_grid = sum(1 for r in rows if r.get('open') and not (r.get('grid') or '').strip())
    if grids:
        report.bar_chart([g for g, _n in grids[:TOP]], [n for _g, n in grids[:TOP]],
                         title='Open clashes by grid intersection (top %d)' % TOP if len(grids) > TOP else
                         'Open clashes by grid intersection', value_label='Open clashes')
    if no_grid:
        report.note('%s no grid intersection (the model has no grid system, or the clash lies away '
                    'from the grids).' % cr.plural(no_grid, 'open clash has', 'open clashes have'))
    models = cr.oriented_matrix(rows, 'model')
    if models['rows']:
        report.heatmap(models['rows'], models['cols'], models['grid'],
                       title='Open clashes, model against model (rows: side A, columns: side B)')
    pairs = cr.pair_tally(rows, 'trade', limit=TOP)
    if pairs:
        report.table(['Trade', 'Clashes with', 'Open', 'New'], [[a, b, o, n] for a, b, o, n in pairs],
                     caption='Open clashes by trade pair', filterable=False)

    # Who and how long -------------------------------------------------------------------------
    report.section('Who has them, and for how long', 'Open clashes by assignee and by days since found.')
    people = cr.tally(rows, 'assigned', blank=cr.NOT_ASSIGNED, limit=TOP)
    if people:
        report.bar_chart([p for p, _n in people], [n for _p, n in people], title='Open clashes by assignee',
                         value_label='Open clashes')
    ages = cr.age_tally(rows)
    report.bar_chart([a for a, _n in ages], [n for _a, n in ages], title='Age of open clashes',
                     horizontal=False, value_label='Open clashes')

    # Groups ---------------------------------------------------------------------------------
    groups = cr.groups_view(rows)
    if groups:
        report.section('Groups', 'Clash Detective result groups with the clashes they hold.')
        group_rows = []
        trusted = set()
        for i, group in enumerate(groups):
            group_rows.append([group['test'], group['group'], group['count'], group['open'],
                               svg.status_mix_html(group['by_status'], htmlreport.status_chip),
                               group['assigned'], group['level'], group['grid'],
                               cr.number_text(group['worst'], unit) if group['worst'] is not None else '',
                               group['oldest'] if group['oldest'] is not None else ''])
            trusted.add((i, 4))
        report.table(['Test', 'Group', 'Clashes', 'Open', 'Statuses', 'Assigned to', 'Level', 'Grid',
                      'Min distance (%s)' % unit, 'Oldest open (days)'], group_rows, cell_html=trusted,
                     max_rows=TABLE_ROWS)

    # Clashes --------------------------------------------------------------------------------
    listed = []
    for test in tests:
        listed.extend(cr.filter_rows(test.get('rows') or [], statuses))
    with_images = bool(config.get('images')) and any(r.get('image') for r in listed[:TABLE_ROWS])
    report.section('Clashes', '%s. Each clash shows its test under its name, the level over the grid, '
                   'item A over item B and trade A over trade B. Filter to narrow the list; click a '
                   'heading to sort.' % cr.listed_text(len(listed), statuses))
    headers = (['Image'] if with_images else []) + [
        'Clash', 'Status', 'Distance (%s)' % unit, 'Location', 'Items', 'Trades', 'Group', 'Assigned to',
        'Age (days)']
    table_rows = []
    trusted = set()
    offset = 1 if with_images else 0
    for i, row in enumerate(listed[:TABLE_ROWS]):
        cells = []
        if with_images:
            uri = data_uri(row['image']) if row.get('image') else None
            cells.append(svg.thumb_cell(uri, row.get('name') or 'Clash') if uri else '')
            trusted.add((i, 0))
        place = '\n'.join(t for t in (row.get('level'), row.get('grid')) if t)
        items = '\n'.join(t for t in (row.get('item_a_name'), row.get('item_b_name')) if t)
        trades = '\n'.join(t for t in (row.get('trade_a'), row.get('trade_b')) if t)
        cells += ['%s\n%s' % (row.get('name') or '', row.get('test') or ''),
                  htmlreport.status_chip(row.get('status') or ''),
                  cr.number_text(row['dist'], unit) if row.get('dist') is not None else '',
                  place, items, trades, row.get('group') or '', row.get('assigned') or '',
                  row.get('age') if row.get('age') is not None else '']
        trusted.add((i, offset + 1))
        table_rows.append(cells)
    report.table(headers, table_rows, cell_html=trusted, max_rows=TABLE_ROWS)

    notes = ['Distances are in %s; negative values are penetrations, as Clash Detective shows them.' % unit,
             'Open means New, Active or Reviewed; Approved and Resolved count as closed.'] + \
        list(data.get('notes') or [])
    for note in notes:
        report.note(note)
    return report


# ---- run ----------------------------------------------------------------------------------------


def run(config, doc=None, interactive=True, progress=None):
    """See namo.reports. Writes the page to config['path'] or folder + name_template."""
    from namo import rep_clash_excel as base
    data, folder, problem = base.prepare(config, doc, progress)
    if problem is not None:
        return problem
    try:
        stage = cr.Stage(progress)
        stage(0.92, 'Writing the dashboard')
        page = build_report(data, config)
        path = reports.output_path(config, TITLE, 'html', values=cr.report_values(data))
        try:
            page.save(path)
        except (IOError, OSError):
            return reports.result('error', 'Could not save the dashboard',
                                  'Close %s wherever it is open, then try again.' % os.path.basename(path))
        stage(1.0, 'Saved')
    finally:
        cr.remove_folder(folder)
    level, message, detail = base.outcome(data, path, cr.ordered_statuses(config.get('statuses')),
                                          'clash dashboard')
    return reports.result(level, message, detail, paths=[path])

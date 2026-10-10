# -*- coding: utf-8 -*-
"""Count by Property: how many objects carry each value of one property (or each pair
of values of two, as a two-level pivot), in the output window and/or an Excel file."""

from namo import data_common, propindex, reports

TITLE = 'Count by Property'
TABLE_ROWS = 1000           # rows printed in the output window; the workbook has them all
CHART_BARS = 20


def default_config():
    return reports.base_config(category='Element', property='Category', category2='',
                               property2='', scope='model', level='objects',
                               budget=propindex.DEFAULT_BUDGET, xlsx=False, path='',
                               name_template='{file} - Count by property - {date}')


def specs_of(config):
    """[(category, property)] for one or two levels."""
    specs = [(config.get('category') or '', config.get('property') or '')]
    if config.get('property2'):
        specs.append((config.get('category2') or '', config.get('property2')))
    return specs


def heading_of(config):
    names = [propindex.pair_text(c, p) if c else p for c, p in specs_of(config)]
    return ' by '.join(names)


def describe(config):
    return '%s, %s' % (heading_of(config),
                       propindex.SCOPE_NAMES.get(config.get('scope'), 'whole model').lower())


def table_rows(pv):
    """Rows for the output table and the workbook: [v1, (v2,) count, share 0..1]."""
    total = pv['total']
    rows = []
    for group in pv['groups']:
        share = float(group['count']) / total if total else 0.0
        rows.append(list(group['key']) + [group['count'], share])
    return rows


def chart_data(pv, limit=CHART_BARS):
    """(labels, values) for the top bars: values, or first-level totals for a pivot."""
    if pv['levels'] == 1:
        groups = pv['groups'][:limit]
        return [g['key'][0] for g in groups], [g['count'] for g in groups]
    totals = propindex.first_totals(pv['groups'])[:limit]
    return [t[0] for t in totals], [t[1] for t in totals]


def headers_of(config):
    specs = specs_of(config)
    names = [p for _c, p in specs]
    if len(names) == 2 and names[0] == names[1]:
        names = [propindex.pair_text(c, p) for c, p in specs]
    return names + ['Count', 'Share']


def write_workbook(path, config, pv, scope_line):
    from namo import naming, xlsx
    wb = xlsx.Workbook(title='Count by %s' % heading_of(config), author=naming.standard_values().get('user'))
    ws = wb.sheet('Counts')
    headers = headers_of(config)
    span = len(headers)
    ws.title('Count by %s' % heading_of(config), span=span)
    ws.subtitle(scope_line, span=span)
    specs = [(h, 28, None) for h in headers[:-2]] + [('Count', 12, 'int'), ('Share', 10, 'pct1')]
    ws.columns(specs)
    for row in table_rows(pv):
        ws.row(row)
    ws.autofilter()
    if pv['levels'] == 2:
        totals = wb.sheet('Totals')
        totals.columns([(headers[0], 28, None), ('Count', 12, 'int'), ('Share', 10, 'pct1')])
        for value, count in propindex.first_totals(pv['groups']):
            totals.row([value, count, float(count) / pv['total'] if pv['total'] else 0.0])
        totals.autofilter()
    return wb.save(path)


def _page(config, pv, scope_line, path):
    """The output-window page: recorded here, printed once no progress window is up
    (see namo.reports.Page)."""
    from namo import htmlreport
    rows = table_rows(pv)
    page = reports.Page()
    page.html('<div class="pynavis-card" style="padding:12px 16px"><div style="font-size:16px;'
              'font-weight:600">Count by %s</div><div style="color:var(--muted)">%s</div></div>'
              % (htmlreport.escape(heading_of(config)), htmlreport.escape(scope_line)))
    labels, values = chart_data(pv)
    if len(labels) > 1:
        title = 'Top %d' % len(labels) if len(pv['groups']) > len(labels) else None
        page.bar_chart([str(l) for l in labels], values, title)
    shown = rows[:TABLE_ROWS]
    printable = [[str(c) for c in row[:-2]] + ['{:,}'.format(row[-2]), propindex.share_text(row[-2], pv['total'])]
                 for row in shown]
    page.table(printable, headers_of(config))
    if len(rows) > len(shown):
        page.md('Showing the first %s of %s rows%s.' % (
            '{:,}'.format(len(shown)), '{:,}'.format(len(rows)),
            '; the workbook lists them all' if path else '; tick the Excel option to get them all'))
    return page


def run(config, doc=None, interactive=True, progress=None):
    """See namo.reports. interactive: prints to the output window (once the caller's
    progress window has closed: reports.deliver) and returns
    result['groups'] = [{'key', 'count', 'items'}] for the Select a group step."""
    document = doc if doc is not None else data_common.active_doc()
    if not data_common.has_models(document):
        return reports.result('info', 'No model is open', 'Open or append a model, then run %s again.' % TITLE)
    specs = specs_of(config)
    if not specs[0][1]:
        return reports.result('warning', 'No property chosen', 'Choose the property to count by.')
    scope = config.get('scope') or 'model'
    level = config.get('level') or 'objects'
    budget = int(config.get('budget') or propindex.DEFAULT_BUDGET)
    data_common.report(progress, 0.0, 'Collecting items')
    item_list = propindex.scope_items(scope, level, document,
                                      tick=data_common.stage(progress, 0.0, 0.0, 'Collecting items: %s'),
                                      budget=budget)
    if not item_list:
        message, detail = data_common.nothing_text(scope)
        return reports.result('info', message, detail)
    readings = propindex.read_pairs(item_list, specs, document,
                                    tick=data_common.stage(progress, 0.05, 0.9, 'Reading values: %s'))
    pv = propindex.pivot(readings)
    scope_line = propindex.scope_text(scope, level, len(item_list), item_list.sampled)
    paths = []
    path = ''
    if config.get('xlsx') or not interactive:
        path = config.get('path') or reports.output_path(config, TITLE, 'xlsx')
        data_common.report(progress, 0.97, 'Writing the workbook')
        try:
            write_workbook(path, config, pv, scope_line)
        except (IOError, OSError) as error:
            return reports.result('error', 'Could not write the workbook', '%s %s' % (data_common.LOCKED, error))
        paths.append(path)
    page = _page(config, pv, scope_line, path) if interactive else None
    distinct = len(pv['groups'])
    message = 'Counted %s %s over %s %s' % (
        '{:,}'.format(distinct), 'value' if distinct == 1 else 'values', '{:,}'.format(len(item_list)),
        propindex.noun(level, len(item_list)))
    if pv['levels'] == 2:
        message = 'Counted %s pairs over %s %s' % ('{:,}'.format(distinct), '{:,}'.format(len(item_list)),
                                                   propindex.noun(level, len(item_list)))
    detail = path or ('Sampled: the scan stopped at %s items.' % '{:,}'.format(budget)
                      if item_list.sampled else '')
    out = reports.result('warning' if item_list.sampled else 'success', message, detail, paths)
    out['sampled'] = bool(item_list.sampled)
    if interactive:
        out['groups'] = [{'key': g['key'], 'count': g['count'],
                          'items': [item_list[i] for i in g['indices']]} for g in pv['groups']]
    return reports.deliver(out, page, progress)

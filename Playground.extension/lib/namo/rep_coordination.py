# -*- coding: utf-8 -*-
"""Coordination Report: the issue register as an HTML page and a workbook.

KPIs (open, overdue, due this week, closed in the last 7 days), open issues by trade,
by priority and by age, the overdue list, issues due this week, one section per trade
with its open issues and snapshot thumbnails, and what closed recently. The workbook
carries the same tables plus every issue (filterable, thumbnails anchored to their rows).

Implements the namo.reports rep_<id>.py contract: run() takes everything from config and
never opens a dialog when interactive is False.
"""

import os

from namo import reports

TITLE = 'Coordination Report'
FORMATS = ('html', 'xlsx')


def default_config():
    return reports.base_config(name_template='{file} - Coordination report - {date}',
                               formats=list(FORMATS), thumbnails=True, max_thumbnails=120,
                               trades=[], include_void=False, open_after=True)


def describe(config):
    formats = ' and '.join(f.upper() for f in config.get('formats') or FORMATS)
    trades = config.get('trades') or []
    scope = ('%d trade%s' % (len(trades), '' if len(trades) == 1 else 's')) if trades else 'every trade'
    return '%s, %s%s' % (formats, scope, ', thumbnails' if config.get('thumbnails') else '')


# ---- pure: what the report holds --------------------------------------------------------------


def _text(value):
    return '' if value is None else (u'%s' % (value,)).strip()


def select_rows(rows, config):
    """The issues the report covers (config trades; Void left out unless asked)."""
    from namo import issues
    out = rows
    trades = config.get('trades') or []
    if trades:
        out = issues.filter_issues(out, trade=trades)
    if not config.get('include_void'):
        out = [i for i in out if i.get('status') != 'Void']
    return out


ISSUE_HEADERS = ['Issue', 'Title', 'Type', 'Status', 'Priority', 'Trade', 'Assignee', 'Due',
                 'Days late', 'Level', 'Grid', 'Created', 'Age (days)', 'Comments']


def issue_cells(issue, today=None):
    """One table row for an issue (plain values)."""
    from namo import issues
    location = issue.get('location') or {}
    late = issues.days_overdue(issue, today)
    return [issue.get('id'), issue.get('title'), issue.get('type'), issue.get('status'),
            issue.get('priority'), issue.get('trade') or '', issue.get('assignee') or '',
            issue.get('due') or '', late or '', location.get('level') or '',
            location.get('grid') or '', (issue.get('created') or '')[:10],
            issues.age_days(issue, today), len(issue.get('comments') or [])]


def headline(summary):
    """The toast line: 'Coordination report: 12 open, 3 overdue'."""
    k = summary['kpis']
    return 'Coordination report: %s open, %s overdue' % ('{:,}'.format(k['open']),
                                                         '{:,}'.format(k['overdue']))


def build_html(rows, summary, meta, thumbs=None, title='Coordination report'):
    """The namo.htmlreport.Report (pure; thumbs: {issue id: image path or bytes})."""
    from namo import htmlreport, issues
    thumbs = thumbs or {}
    k = summary['kpis']
    r = htmlreport.Report(title, subtitle=meta.get('subtitle'), meta=meta.get('pairs'))
    r.kpis([('Open', k['open'], None, 'Open and in progress'),
            ('Overdue', k['overdue'], 'bad' if k['overdue'] else None),
            ('Due this week', k['due_week'], 'warn' if k['due_week'] else None),
            ('Closed, last 7 days', k['closed_recent'], 'good' if k['closed_recent'] else None)])
    r.section('Open issues', intro='Open and in progress issues by trade, priority and age.')
    if summary['open_by_trade']:
        r.bar_chart([t for t, _n in summary['open_by_trade']],
                    [n for _t, n in summary['open_by_trade']], title='Open issues by trade',
                    value_label='Issues')
        priorities = summary['open_by_priority']
        r.bar_chart([p for p, _n in priorities], [n for _p, n in priorities],
                    title='Open issues by priority', value_label='Issues',
                    tones=[issues.PRIORITY_TONES.get(p, 'neutral') for p, _n in priorities])
        r.bar_chart([a for a, _n in summary['aging']], [n for _a, n in summary['aging']],
                    title='Open issues by age', horizontal=False, value_label='Issues')
    else:
        r.note('No open issues.')

    def chip(status):
        return htmlreport.status_chip(status, issues.STATUS_TONES.get(status, 'neutral'))

    def table(rows_, caption):
        body = []
        html = set()
        for index, issue in enumerate(rows_):
            cells = issue_cells(issue, summary['today'])
            cells[3] = chip(issue['status'])
            html.add((index, 3))
            body.append(cells)
        r.table(ISSUE_HEADERS, body, cell_html=html, caption=caption, max_rows=2000,
                numeric=(8, 12, 13))

    r.section('Overdue', intro='Open issues past their due date, most days late first.')
    if summary['overdue']:
        table(summary['overdue'], '%d overdue' % len(summary['overdue']))
    else:
        r.note('Nothing is overdue.')
    r.section('Due this week')
    if summary['due_week']:
        table(summary['due_week'], '%d due within 7 days' % len(summary['due_week']))
    else:
        r.note('Nothing else falls due in the next 7 days.')
    for trade, members in summary['by_trade']:
        r.section('%s' % trade, intro='%d open issue%s.' % (len(members), '' if len(members) == 1 else 's'))
        table(members, None)
        gallery = [(thumbs[i['id']], '%s  %s' % (i['id'], i['title'])) for i in members
                   if i['id'] in thumbs]
        if gallery:
            r.gallery(gallery, columns=4)
    r.section('Recently closed', intro='Resolved or closed in the last 14 days.')
    if summary['recently_closed']:
        table(summary['recently_closed'], None)
    else:
        r.note('Nothing closed in the last 14 days.')
    return r


def build_workbook(rows, summary, meta, thumbs=None, title='Coordination report'):
    """The namo.xlsx.Workbook (pure; thumbs: {issue id: image path})."""
    from namo import issues, xlsx
    thumbs = thumbs or {}
    wb = xlsx.Workbook(title=title, author=meta.get('user'))
    ws = wb.sheet('Summary')
    ws.title(title, span=4)
    ws.subtitle(meta.get('subtitle') or '', span=4)
    ws.skip()
    k = summary['kpis']
    ws.columns([('Measure', 28, None), ('Count', 12, 'int')], freeze=False)
    for label, value, style in (('Open', k['open'], None), ('Overdue', k['overdue'], 'bad'),
                                ('Due this week', k['due_week'], 'warn'),
                                ('Closed, last 7 days', k['closed_recent'], 'good')):
        ws.row([label, value], styles=[None, style if value else None])
    for heading, pairs in (('Open by trade', summary['open_by_trade']),
                           ('Open by priority', summary['open_by_priority']),
                           ('Open by age', summary['aging'])):
        ws.skip()
        ws.row([heading, 'Open'], styles='header')
        for label, value in pairs:
            ws.row([label, value])
    status_styles = {'good': 'good', 'warn': 'warn', 'bad': 'bad', 'info': 'info'}

    def sheet(name, rows_, pictures=False):
        sheet_ = wb.sheet(name)
        widths = [12, 44, 14, 13, 11, 18, 20, 12, 10, 12, 10, 12, 11, 11]
        specs = [(h, w, None) for h, w in zip(ISSUE_HEADERS, widths)]
        specs[1] = ('Title', 44, 'wrap')
        specs[8] = ('Days late', 10, 'int')
        specs[12] = ('Age (days)', 11, 'int')
        specs[13] = ('Comments', 11, 'int')
        if pictures:
            specs.append(('Snapshot', 18, None))
        sheet_.columns(specs)
        for issue in rows_:
            tone = issues.STATUS_TONES.get(issue['status'])
            styles = [None, None, None, status_styles.get(tone)]
            if issue['priority'] == 'Critical':
                styles.append('bad')
            row = sheet_.row(issue_cells(issue, summary['today']), styles=styles,
                             height=52 if pictures and issue['id'] in thumbs else None)
            if pictures and issue['id'] in thumbs:
                try:
                    sheet_.image(thumbs[issue['id']], row, len(ISSUE_HEADERS), width_px=120,
                                 offset_px=(3, 3), anchor='cell')
                except (ValueError, IOError, OSError):
                    pass
        sheet_.autofilter()
        return sheet_

    open_rows = [i for i in rows if issues.is_open(i)]
    sheet('Open issues', issues.sort_issues(open_rows), pictures=bool(thumbs))
    sheet('Overdue', summary['overdue'])
    sheet('Recently closed', summary['recently_closed'])
    sheet('All issues', issues.sort_issues(rows, 'id'))
    return wb


# ---- the run ----------------------------------------------------------------------------------


def _thumbnails(store, members, limit, progress):
    """{issue id: thumbnail jpg path} for up to limit issues (System.Drawing); {} when
    images are unavailable here."""
    from namo import images, issueapi
    out = {}
    count = 0
    for issue in members:
        if count >= limit:
            break
        source = store.snapshot_path(issue)
        if not source:
            continue
        try:
            target = issueapi.temp_path('.jpg', 'thumb-' + issue['id'])
            images.thumbnail(source, target, max_width=320, quality=82)
            out[issue['id']] = target
            count += 1
        except Exception:
            break
        if progress is not None and progress(0.2 + 0.5 * count / float(limit or 1),
                                             'Thumbnails %d' % count) == False:  # noqa: E712
            raise reports.Cancelled()
    return out


def run(config, doc=None, interactive=True, progress=None):
    from namo import config as namo_config
    from namo import dates, issues, issuestore
    document = doc if doc is not None else issuestore.active_doc()
    store = issuestore.for_doc(document) if document is not None else None
    if store is None or not store.saved:
        return reports.result('info', 'Save the model first',
                              'Issues are kept with the model file; there is no register yet.')
    rows = select_rows(store.list(), config)
    if not rows:
        return reports.result('info', 'No issues to report',
                              'Raise issues in the Issues panel, with Issue Stamps or Clash to Issues.')
    if progress is not None:
        progress(0.05, 'Reading %d issues' % len(rows))
    today = dates.today()
    summary = issues.summary(rows, today)
    doc_name = os.path.basename(store.doc_path)
    user = namo_config.user_name()
    meta = {'subtitle': doc_name, 'user': user,
            'pairs': [('Model', doc_name), ('Date', dates.format(today)), ('Issues', len(rows)),
                      ('Data', store.describe()), ('By', user)]}
    thumbs = {}
    if config.get('thumbnails'):
        wanted = [i for _t, members in summary['by_trade'] for i in members]
        thumbs = _thumbnails(store, wanted, int(config.get('max_thumbnails') or 0), progress)
    formats = [f for f in (config.get('formats') or FORMATS) if f in FORMATS] or list(FORMATS)
    paths_written = []
    try:
        if 'html' in formats:
            if progress is not None:
                progress(0.75, 'Writing the HTML page')
            html_path = reports.output_path(config, TITLE, 'html', values={'file': os.path.splitext(doc_name)[0]})
            build_html(rows, summary, meta, thumbs).save(html_path)
            paths_written.append(html_path)
        if 'xlsx' in formats:
            if progress is not None:
                progress(0.9, 'Writing the workbook')
            xlsx_path = reports.output_path(config, TITLE, 'xlsx', values={'file': os.path.splitext(doc_name)[0]})
            build_workbook(rows, summary, meta, thumbs).save(xlsx_path)
            paths_written.append(xlsx_path)
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the report',
                              '%s Close the file if it is open, then try again.' % error,
                              paths=paths_written)
    finally:
        for path in thumbs.values():
            try:
                os.remove(path)
            except OSError:
                pass
    if progress is not None:
        progress(1.0, 'Done')
    detail = paths_written[0] if paths_written else ''
    if config.get('thumbnails') and not thumbs and any(i.get('images') for i in rows):
        detail += ' (thumbnails unavailable here)'
    return reports.result('success', headline(summary), detail, paths=paths_written)

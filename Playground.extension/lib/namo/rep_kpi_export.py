# -*- coding: utf-8 -*-
"""KPI Export: flat tables for Power BI (or any BI tool) from the issue register and Clash
Detective, written as CSV (UTF-8 with BOM, which Excel and Power BI read without asking)
and JSON into one folder, with a README.txt describing every column.

Tables (fixed file names, so a scheduled export overwrites last week's and a Power BI
refresh just reads the folder again):

    issues.csv / .json          one row per issue
    issue_comments.csv / .json  one row per comment (status changes included)
    clash_results.csv / .json   one row per clash result (namo.clashdata.snapshot_all)
    clash_tests.csv / .json     one row per clash test with its counts
    clash_history.csv / .json   one row per clash per saved history snapshot

Every row carries snapshot_time (when this export ran) and model (the model file name);
dates are ISO 8601; keys are stable across exports (issue guid, comment guid, test guid,
result guid, history id), so rows from several exports append cleanly.

The folder is config 'folder' (default %APPDATA%\\pyNavis\\playground\\reports) joined with
config 'name_template' rendered (default '{file} KPI', no date: a fixed folder per
model). An empty name_template writes straight into 'folder'.

Implements the namo.reports rep_<id>.py contract.
"""

import json
import os

from namo import reports

TITLE = 'KPI Export'
TABLE_NAMES = ('issues', 'issue_comments', 'clash_results', 'clash_tests', 'clash_history')

COLUMNS = {
    'issues': [
        ('issue_key', 'Stable key: the issue GUID (also its BCF Topic Guid).'),
        ('issue_id', 'The issue number as people see it, e.g. RFI-012.'),
        ('model', 'Model file the register belongs to.'),
        ('title', 'Issue title.'),
        ('type', 'Issue type (template), e.g. RFI, Clash.'),
        ('status', 'Open, In progress, Resolved, Closed or Void.'),
        ('is_open', '1 when Open or In progress, else 0.'),
        ('priority', 'Low, Normal, High or Critical.'),
        ('priority_rank', '1 Critical, 2 High, 3 Normal, 4 Low (sort order).'),
        ('trade', 'Responsible trade (blank when none).'),
        ('assignee', 'Person or company the issue is assigned to.'),
        ('due_date', 'Due date (YYYY-MM-DD), blank when none.'),
        ('days_overdue', 'Days past the due date for open issues, else 0.'),
        ('is_overdue', '1 when open and past due, else 0.'),
        ('created', 'When the issue was raised (local time, ISO 8601).'),
        ('created_by', 'Who raised it.'),
        ('modified', 'Last change (local time, ISO 8601).'),
        ('modified_by', 'Who changed it last.'),
        ('closed', 'When it entered Resolved, Closed or Void; blank while open.'),
        ('age_days', 'Days from created to the snapshot (open) or to closed.'),
        ('age_bucket', 'Age band: 0-7, 8-14, 15-30 or Over 30 days.'),
        ('level', 'Nearest level of the issue pin.'),
        ('grid', 'Nearest grid intersection of the issue pin.'),
        ('location_x', 'Pin X in model units (blank without a pin).'),
        ('location_y', 'Pin Y in model units.'),
        ('location_z', 'Pin Z in model units.'),
        ('location_units', 'Units of the pin coordinates.'),
        ('labels', 'Labels, separated by "; ".'),
        ('source', 'How it was raised: manual, stamp, clash or bcf.'),
        ('source_ref', 'Clash test and result GUIDs, or the BCF file, it came from.'),
        ('element_count', 'Model elements attached to the issue.'),
        ('comment_count', 'Comments on the issue.'),
        ('image_count', 'Snapshots and screenshots on the issue.'),
        ('snapshot_time', 'When this export ran (local time, ISO 8601).'),
    ],
    'issue_comments': [
        ('comment_key', 'Stable key: the comment GUID.'),
        ('issue_key', 'The issue GUID (joins to issues.issue_key).'),
        ('issue_id', 'The issue number.'),
        ('model', 'Model file.'),
        ('author', 'Who wrote it.'),
        ('date', 'When (local time, ISO 8601).'),
        ('text', 'The comment text.'),
        ('status_from', 'For a status change: the status before.'),
        ('status_to', 'For a status change: the status after.'),
        ('snapshot_time', 'When this export ran.'),
    ],
    'clash_results': [
        ('result_key', 'Stable key: test GUID + "|" + clash result GUID.'),
        ('test_key', 'The clash test GUID (joins to clash_tests.test_key).'),
        ('test', 'Clash test name.'),
        ('model', 'Model file.'),
        ('clash', 'Clash name.'),
        ('group', 'Innermost result group name, blank when ungrouped.'),
        ('status', 'New, Active, Reviewed, Approved or Resolved.'),
        ('is_open', '1 for New, Active and Reviewed, else 0.'),
        ('distance_m', 'Clash distance in metres (negative = penetration).'),
        ('assigned_to', 'AssignedTo of the result.'),
        ('created', 'When Navisworks found it (ISO 8601).'),
        ('approved', 'When it was approved (ISO 8601), blank when not.'),
        ('approved_by', 'Who approved it.'),
        ('resolved', 'When it was resolved (ISO 8601), blank when not.'),
        ('level', 'Nearest level.'),
        ('grid', 'Nearest grid intersection.'),
        ('model_a', 'Source file of item 1.'),
        ('model_b', 'Source file of item 2.'),
        ('trade_a', 'Trade of item 1 (namo.trades).'),
        ('trade_b', 'Trade of item 2.'),
        ('item_a', 'Name of item 1.'),
        ('item_b', 'Name of item 2.'),
        ('center_x_m', 'Clash point X in metres.'),
        ('center_y_m', 'Clash point Y in metres.'),
        ('center_z_m', 'Clash point Z in metres.'),
        ('comment_count', 'Comments on the result.'),
        ('pair_key', 'Element pair and position key used to match clashes between runs.'),
        ('snapshot_time', 'When this export ran.'),
    ],
    'clash_tests': [
        ('test_key', 'Stable key: the clash test GUID.'),
        ('test', 'Clash test name.'),
        ('model', 'Model file.'),
        ('total', 'Clash results in the test.'),
        ('new', 'Results with status New.'),
        ('active', 'Results with status Active.'),
        ('reviewed', 'Results with status Reviewed.'),
        ('approved', 'Results with status Approved.'),
        ('resolved', 'Results with status Resolved.'),
        ('open', 'New + Active + Reviewed.'),
        ('snapshot_time', 'When this export ran.'),
    ],
    'clash_history': [
        ('history_key', 'Stable key: history id + "|" + test + "|" + pair key.'),
        ('history_id', 'The saved clash history snapshot (namo.clashdata history).'),
        ('history_time', 'When that snapshot was taken (ISO 8601).'),
        ('history_label', 'Its label.'),
        ('model', 'Model file.'),
        ('test', 'Clash test name.'),
        ('clash', 'Clash name.'),
        ('status', 'Status at that time.'),
        ('is_open', '1 for New, Active and Reviewed, else 0.'),
        ('distance_m', 'Distance in metres.'),
        ('created', 'When Navisworks found the clash.'),
        ('trade_a', 'Trade of item 1.'),
        ('trade_b', 'Trade of item 2.'),
        ('grid', 'Nearest grid intersection.'),
        ('level', 'Nearest level.'),
        ('pair_key', 'Element pair and position key.'),
        ('snapshot_time', 'When this export ran.'),
    ],
}


def default_config():
    return reports.base_config(name_template='{file} KPI', tables=list(TABLE_NAMES),
                               formats=['csv', 'json'], max_clash_rows=200000)


def describe(config):
    tables = config.get('tables') or TABLE_NAMES
    where = config.get('folder') or 'Playground reports'
    return '%d table%s as %s into %s' % (len(tables), '' if len(tables) == 1 else 's',
                                         ' and '.join(f.upper() for f in config.get('formats') or ['csv']),
                                         where)


# ---- pure: shaping ----------------------------------------------------------------------------------


def _t(value):
    return '' if value is None else (u'%s' % (value,))


def _num(value):
    return '' if value is None else value


def issue_rows(rows, model, snapshot_time, today=None):
    """issues table rows (dicts keyed by COLUMNS['issues'])."""
    from namo import dates, issues
    out = []
    for issue in rows:
        location = issue.get('location') or {}
        point = location.get('point') or [None, None, None]
        if issues.is_open(issue):
            age = issues.age_days(issue, today)
        else:
            created = dates.parse(issue.get('created'))
            closed = dates.parse(issue.get('closed')) or dates.parse(issue.get('modified'))
            age = (closed.date() - created.date()).days if created and closed else None
        source = issue.get('source') or {}
        out.append({
            'issue_key': issue.get('guid'), 'issue_id': issue.get('id'), 'model': model,
            'title': _t(issue.get('title')), 'type': _t(issue.get('type')),
            'status': issue.get('status'), 'is_open': 1 if issues.is_open(issue) else 0,
            'priority': issue.get('priority'),
            'priority_rank': issues.URGENCY.index(issue['priority']) + 1
            if issue.get('priority') in issues.URGENCY else '',
            'trade': _t(issue.get('trade')), 'assignee': _t(issue.get('assignee')),
            'due_date': _t(issue.get('due')), 'days_overdue': issues.days_overdue(issue, today),
            'is_overdue': 1 if issues.is_overdue(issue, today) else 0,
            'created': _t(issue.get('created')), 'created_by': _t(issue.get('created_by')),
            'modified': _t(issue.get('modified')), 'modified_by': _t(issue.get('modified_by')),
            'closed': _t(issue.get('closed')), 'age_days': _num(age),
            'age_bucket': dates.age_bucket(age) if age is not None else '',
            'level': _t(location.get('level')), 'grid': _t(location.get('grid')),
            'location_x': _num(point[0]), 'location_y': _num(point[1]), 'location_z': _num(point[2]),
            'location_units': _t(location.get('units')),
            'labels': '; '.join(issue.get('labels') or []),
            'source': _t(source.get('kind')), 'source_ref': _t(source.get('ref')),
            'element_count': len(issue.get('elements') or []),
            'comment_count': len(issue.get('comments') or []),
            'image_count': len(issue.get('images') or []),
            'snapshot_time': snapshot_time,
        })
    return out


def comment_rows(rows, model, snapshot_time):
    out = []
    for issue in rows:
        for comment in issue.get('comments') or []:
            change = comment.get('status_change') or {}
            out.append({'comment_key': comment.get('guid'), 'issue_key': issue.get('guid'),
                        'issue_id': issue.get('id'), 'model': model,
                        'author': _t(comment.get('author')), 'date': _t(comment.get('date')),
                        'text': _t(comment.get('text')), 'status_from': _t(change.get('from')),
                        'status_to': _t(change.get('to')), 'snapshot_time': snapshot_time})
    return out


OPEN_CLASH = ('New', 'Active', 'Reviewed')


def clash_rows(by_test, model, snapshot_time, limit=None):
    """(clash_results rows, clash_tests rows, truncated) from clashdata.snapshot_all."""
    results = []
    tests = []
    truncated = False
    for name in sorted(by_test):
        rows = by_test[name]
        counts = {'New': 0, 'Active': 0, 'Reviewed': 0, 'Approved': 0, 'Resolved': 0}
        test_key = ''
        for row in rows:
            test_key = test_key or _t(row.get('test_guid'))
            status = _t(row.get('status'))
            if status in counts:
                counts[status] += 1
            if limit is not None and len(results) >= limit:
                truncated = True
                continue
            center = row.get('center_m') or (None, None, None)
            results.append({
                'result_key': '%s|%s' % (_t(row.get('test_guid')), _t(row.get('guid'))),
                'test_key': _t(row.get('test_guid')), 'test': name, 'model': model,
                'clash': _t(row.get('name')), 'group': _t(row.get('group')), 'status': status,
                'is_open': 1 if status in OPEN_CLASH else 0,
                'distance_m': _num(row.get('distance_m')), 'assigned_to': _t(row.get('assigned')),
                'created': _t(row.get('created')), 'approved': _t(row.get('approved_time')),
                'approved_by': _t(row.get('approved_by')), 'resolved': _t(row.get('resolved_time')),
                'level': _t(row.get('level')), 'grid': _t(row.get('grid')),
                'model_a': _t(row.get('model_a')), 'model_b': _t(row.get('model_b')),
                'trade_a': _t(row.get('trade_a')), 'trade_b': _t(row.get('trade_b')),
                'item_a': _t(row.get('item_a_name')), 'item_b': _t(row.get('item_b_name')),
                'center_x_m': _num(center[0]), 'center_y_m': _num(center[1]),
                'center_z_m': _num(center[2]), 'comment_count': _num(row.get('comments')),
                'pair_key': _t(row.get('key')), 'snapshot_time': snapshot_time})
        tests.append({'test_key': test_key, 'test': name, 'model': model, 'total': len(rows),
                      'new': counts['New'], 'active': counts['Active'],
                      'reviewed': counts['Reviewed'], 'approved': counts['Approved'],
                      'resolved': counts['Resolved'],
                      'open': counts['New'] + counts['Active'] + counts['Reviewed'],
                      'snapshot_time': snapshot_time})
    return results, tests, truncated


def history_rows(entries, model, snapshot_time):
    """clash_history rows from [(entry {'id','label','time'}, {test: [rows]})]."""
    out = []
    for entry, by_test in entries:
        for test in sorted(by_test or {}):
            for row in by_test[test]:
                status = _t(row.get('status'))
                out.append({
                    'history_key': '%s|%s|%s' % (entry.get('id'), test, _t(row.get('key'))),
                    'history_id': _t(entry.get('id')), 'history_time': _t(entry.get('time')),
                    'history_label': _t(entry.get('label')), 'model': model, 'test': test,
                    'clash': _t(row.get('name')), 'status': status,
                    'is_open': 1 if status in OPEN_CLASH else 0,
                    'distance_m': _num(row.get('distance_m')), 'created': _t(row.get('created')),
                    'trade_a': _t(row.get('trade_a')), 'trade_b': _t(row.get('trade_b')),
                    'grid': _t(row.get('grid')), 'level': _t(row.get('level')),
                    'pair_key': _t(row.get('key')), 'snapshot_time': snapshot_time})
    return out


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, float):
        text = repr(value)
        return text[:-2] if text.endswith('.0') else text
    text = u'%s' % (value,)
    if any(ch in text for ch in (',', '"', '\n', '\r')) or text != text.strip():
        return u'"%s"' % text.replace('"', '""')
    return text


def csv_text(table, rows):
    """CSV text (CRLF line ends, RFC 4180 quoting) with the table's columns in order."""
    names = [name for name, _desc in COLUMNS[table]]
    lines = [u','.join(names)]
    for row in rows:
        lines.append(u','.join(_cell(row.get(name)) for name in names))
    return u'\r\n'.join(lines) + u'\r\n'


def json_rows(table, rows):
    """Rows as JSON objects with exactly the documented columns (missing ones null)."""
    names = [name for name, _desc in COLUMNS[table]]
    return [dict((name, row.get(name)) for name in names) for row in rows]


def readme_text(tables, model, snapshot_time, notes=()):
    lines = ['Playground KPI Export', '=================', '',
             'Model: %s' % model, 'Exported: %s' % snapshot_time, '',
             'CSV files are UTF-8 with a byte order mark; JSON files hold the same rows as',
             'arrays of objects. Dates are ISO 8601 in local time. Keys are stable across',
             'exports, so the same issue or clash keeps the same key every week.', '']
    for note in notes:
        lines.append('Note: %s' % note)
    if notes:
        lines.append('')
    for table in tables:
        lines.append('%s' % table)
        lines.append('-' * len(table))
        for name, description in COLUMNS[table]:
            lines.append('  %-16s %s' % (name, description))
        lines.append('')
    return u'\r\n'.join(lines)


# ---- the run ------------------------------------------------------------------------------------------


def target_folder(config, model_stem):
    """Where the tables go (created)."""
    from namo import naming, paths
    base = str(config.get('folder') or '').strip()
    base = os.path.expanduser(os.path.expandvars(base)) if base else os.path.join(paths.data_root(), 'reports')
    template = str(config.get('name_template') or '').strip()
    if template:
        values = naming.standard_values()
        values['file'] = model_stem
        values['report'] = TITLE
        name, _missing = naming.render(template, values)
        base = os.path.join(base, naming.sanitize(name, for_file=True))
    return paths.ensure_dir(base)


def _clash_data(document, wanted, limit, progress, notes, model, stamp_text, doc_path):
    from namo import clashdata
    out = {}
    if 'clash_results' in wanted or 'clash_tests' in wanted:
        try:
            def tick(fraction, label):
                if progress is not None:
                    return progress(0.2 + 0.5 * fraction, label)
                return True
            by_test = clashdata.snapshot_all(None, document, tick)
            results, tests, truncated = clash_rows(by_test, model, stamp_text, limit)
            out['clash_results'], out['clash_tests'] = results, tests
            if truncated:
                notes.append('clash_results holds the first %s rows (max_clash_rows).'
                             % '{:,}'.format(limit))
        except ImportError:
            notes.append('Clash Detective is not available here; the clash tables are empty.')
            out['clash_results'], out['clash_tests'] = [], []
        except Exception as error:
            if type(error).__name__ == 'Cancelled':
                raise
            notes.append('Clash results could not be read: %s' % error)
            out['clash_results'], out['clash_tests'] = [], []
    if 'clash_history' in wanted:
        try:
            entries = []
            for entry in clashdata.list_history(doc_path):
                entries.append((entry, clashdata.load_history(doc_path, entry['id']) or {}))
            out['clash_history'] = history_rows(entries, model, stamp_text)
        except Exception as error:
            notes.append('Clash history could not be read: %s' % error)
            out['clash_history'] = []
    return out


def run(config, doc=None, interactive=True, progress=None):
    from namo import dates, issuestore, paths
    document = doc if doc is not None else issuestore.active_doc()
    store = issuestore.for_doc(document) if document is not None else None
    if store is None or not store.saved:
        return reports.result('info', 'Save the model first',
                              'The export is keyed by the model file; save it, then export.')
    wanted = [t for t in (config.get('tables') or TABLE_NAMES) if t in COLUMNS]
    formats = [f for f in (config.get('formats') or ['csv', 'json']) if f in ('csv', 'json')] or ['csv']
    model = os.path.basename(store.doc_path)
    stem = os.path.splitext(model)[0]
    stamp_text = dates.iso(dates.now())
    notes = []
    tables = {}
    rows = store.list()
    if 'issues' in wanted:
        tables['issues'] = issue_rows(rows, model, stamp_text)
    if 'issue_comments' in wanted:
        tables['issue_comments'] = comment_rows(rows, model, stamp_text)
    if progress is not None:
        progress(0.1, 'Read %d issues' % len(rows))
    limit = int(config.get('max_clash_rows') or 0) or None
    tables.update(_clash_data(document, wanted, limit, progress, notes, model, stamp_text,
                              store.doc_path))
    folder = target_folder(config, stem)
    written = []
    try:
        for table in wanted:
            data = tables.get(table, [])
            if 'csv' in formats:
                path = os.path.join(folder, table + '.csv')
                paths.atomic_write_bytes(path, b'\xef\xbb\xbf' + csv_text(table, data).encode('utf-8'))
                written.append(path)
            if 'json' in formats:
                path = os.path.join(folder, table + '.json')
                paths.atomic_write_text(path, json.dumps(json_rows(table, data), indent=1,
                                                         sort_keys=True, ensure_ascii=False) + u'\n')
                written.append(path)
        readme = os.path.join(folder, 'README.txt')
        paths.atomic_write_bytes(readme, b'\xef\xbb\xbf' + readme_text(wanted, model, stamp_text,
                                                                       notes).encode('utf-8'))
        written.append(readme)
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the KPI tables',
                              '%s Close the files in Excel or Power BI, then try again.' % error,
                              paths=written)
    if progress is not None:
        progress(1.0, 'Done')
    counts = ', '.join('%s %s' % ('{:,}'.format(len(tables.get(t, []))), t.replace('_', ' '))
                       for t in wanted)
    level = 'warning' if notes else 'success'
    return reports.result(level, 'Exported %d KPI table%s' % (len(wanted), '' if len(wanted) == 1 else 's'),
                          '%s. %s%s' % (counts, folder, ('. ' + notes[0]) if notes else ''),
                          paths=written)

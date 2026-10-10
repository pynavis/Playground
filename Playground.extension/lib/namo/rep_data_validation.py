# -*- coding: utf-8 -*-
"""Data Validation: runs the JSON rule files in <team_root>\\rules\\validation over a
scope and reports per rule (checked, passed, failed), the failing elements, an Excel
workbook, and optionally one selection set per failing rule."""

from namo import data_common, propindex, reports, validator

TITLE = 'Data Validation'


def default_config():
    return reports.base_config(rule_files=[], scope='model', level='objects',
                               budget=propindex.DEFAULT_BUDGET, xlsx=False, sets=False, path='',
                               name_template='{file} - Data validation - {date}')


def describe(config):
    files = config.get('rule_files') or []
    return '%s, %s' % ('%d rule files' % len(files) if files else 'every rule file',
                       propindex.SCOPE_NAMES.get(config.get('scope'), 'whole model').lower())


def choose_rulesets(rulesets, wanted):
    """The rulesets whose file names are in wanted (case-insensitive); all when empty."""
    if not wanted:
        return list(rulesets)
    keys = [w.lower() for w in wanted]
    return [r for r in rulesets if r['file'].lower() in keys]


def message_for(results, count, level):
    """(level, message) for the toast."""
    total = validator.totals(results)
    things = '%s %s' % ('{:,}'.format(count), propindex.noun(level, count))
    if not total['checked']:
        return 'info', 'No rule applied to the %s' % things
    if not total['failed']:
        return 'success', 'All %d %s passed on %s' % (total['rules'], 'rule' if total['rules'] == 1 else 'rules',
                                                       things)
    return 'warning', '%d of %d %s failed: %s %s' % (
        total['failing_rules'], total['rules'], 'rule' if total['rules'] == 1 else 'rules',
        '{:,}'.format(total['failed']), 'failure' if total['failed'] == 1 else 'failures')


def write_workbook(path, results, problems, scope_line, reader_ctx):
    from namo import inspect, naming, xlsx
    wb = xlsx.Workbook(title=TITLE, author=naming.standard_values().get('user'))
    ws = wb.sheet('Summary')
    ws.title(TITLE, span=7)
    ws.subtitle(scope_line, span=7)
    ws.columns([('Rule', 40, None), ('Rule file', 24, None), ('Severity', 10, None), ('Checked', 11, 'int'),
                ('Passed', 11, 'int'), ('Failed', 11, 'int'), ('Pass rate', 11, 'pct')])
    for row in validator.summary_rows(results):
        rate = row[6]
        style = None
        if rate is not None:
            style = 'good' if rate >= 1 else ('warn' if rate >= 0.9 else 'bad')
        ws.row(row[:6] + [rate], styles=[None, None, None, None, None, None, style])
    ws.autofilter()
    failures = wb.sheet('Failures')
    failures.columns([('Rule', 36, None), ('Severity', 10, None), ('Element', 30, None), ('Element ID', 14, None),
                      ('Source file', 24, None), ('Tree path', 50, None), ('Problem', 60, None)])
    for rule, item, problem in validator.failure_rows(results):
        record = inspect.id_record(item)
        severity = ''
        for r in results:
            if r['rule'] == rule:
                severity = r['severity']
                break
        failures.row([rule, severity, record['name'], record['element_id'], record['file'], record['path'],
                      problem])
    failures.autofilter()
    if problems:
        sheet = wb.sheet('Rule file problems')
        sheet.columns([('Problem', 120, None)])
        for line in problems:
            sheet.row([line])
    return wb.save(path)


def make_sets(results, doc=None):
    """One static selection set per failing rule in the 'Validation' folder, replacing
    a set of the same name; one undo step. Returns the number of sets written."""
    from pynavis import sets, viewpoints
    written = 0
    with viewpoints.transaction('Validation sets', doc):
        for result in results:
            if not result['failed']:
                continue
            name = validator.set_name(result['rule'])
            failing = [item for item, _problems in result['failures']]
            existing = sets.find('%s/%s' % (validator.SET_FOLDER, name.replace('/', '\\/')), doc)
            if existing is not None:
                sets.update(existing, failing, doc)
            else:
                sets.create(name, failing, folder=validator.SET_FOLDER, doc=doc)
            written += 1
    return written


def _page(results, problems, scope_line):
    """The output-window page: recorded here, printed once no progress window is up
    (see namo.reports.Page). The failure links are built at show time, because
    pynavis.output.element_link opens the output window."""
    from namo import htmlreport
    total = validator.totals(results)
    page = reports.Page()
    page.html('<div class="pynavis-card" style="padding:12px 16px"><div style="font-size:16px;'
              'font-weight:600">Data validation</div><div style="color:var(--muted)">%s, %s rules, '
              '%s checks, %s failures</div></div>'
              % (htmlreport.escape(scope_line), '{:,}'.format(total['rules']),
                 '{:,}'.format(total['checked']), '{:,}'.format(total['failed'])))
    if problems:
        page.md('**Rule file problems** (these rules were skipped; Shift+Click checks the files):')
        page.table([[p] for p in problems], ['Problem'])
    page.html(validator.summary_html(results))
    rows = validator.failure_rows(results, validator.FAILURE_ROWS_SHOWN)
    if rows:
        def failures():
            from namo import inspect, items

            def link(item):
                name = item.DisplayName or item.ClassDisplayName or 'Element'
                return inspect.link_html(item, name)
            return validator.failures_html(rows, link, items.model_name, total['failed'])
        page.later(failures)
    return page


def run(config, doc=None, interactive=True, progress=None):
    document = doc if doc is not None else data_common.active_doc()
    if not data_common.has_models(document):
        return reports.result('info', 'No model is open', 'Open or append a model, then validate again.')
    folder = validator.rules_folder()
    validator.ensure_starter(folder)
    rulesets = choose_rulesets(validator.load_folder(folder), config.get('rule_files') or [])
    problems = []
    for ruleset in rulesets:
        problems.extend(ruleset.get('problems') or [])
    active = [r for r in rulesets if any(rule.get('enabled', True) for rule in r['rules'])]
    if not active:
        detail = problems[0] if problems else 'Add rule files to %s.' % folder
        return reports.result('warning', 'No rules to run', detail)
    scope = config.get('scope') or 'model'
    level = config.get('level') or 'objects'
    budget = int(config.get('budget') or propindex.DEFAULT_BUDGET)
    item_list = propindex.scope_items(scope, level, document,
                                      tick=data_common.stage(progress, 0.0, 0.0, 'Collecting items: %s'),
                                      budget=budget)
    if not item_list:
        message, detail = data_common.nothing_text(scope)
        return reports.result('info', message, detail)
    reader = propindex.Reader(document)
    results = validator.run_rules(active, item_list, reader,
                                  tick=data_common.stage(progress, 0.05, 0.85, 'Checking %s'))
    scope_line = propindex.scope_text(scope, level, len(item_list), item_list.sampled)
    paths = []
    if config.get('xlsx') or not interactive:
        path = config.get('path') or reports.output_path(config, TITLE, 'xlsx')
        data_common.report(progress, 0.92, 'Writing the workbook')
        try:
            write_workbook(path, results, problems, scope_line, reader.ctx)
        except (IOError, OSError) as error:
            return reports.result('error', 'Could not write the workbook', '%s %s' % (data_common.LOCKED, error))
        paths.append(path)
    sets_written = 0
    if config.get('sets'):
        data_common.report(progress, 0.96, 'Saving selection sets')
        sets_written = make_sets(results, document)
    page = _page(results, problems, scope_line) if interactive else None
    level_name, message = message_for(results, len(item_list), level)
    notes = []
    if paths:
        notes.append(paths[0])
    if sets_written:
        notes.append('%d selection %s in %s' % (sets_written, 'set' if sets_written == 1 else 'sets',
                                                 validator.SET_FOLDER))
    if item_list.sampled:
        notes.append('Sampled at %s items' % '{:,}'.format(budget))
    if problems:
        notes.append('%d rule file %s' % (len(problems), 'problem' if len(problems) == 1 else 'problems'))
        if level_name == 'success':
            level_name = 'warning'
    out = reports.result(level_name, message, '. '.join(notes), paths)
    out['totals'] = validator.totals(results)
    out['folder'] = folder
    return reports.deliver(out, page, progress)

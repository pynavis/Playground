# -*- coding: utf-8 -*-
"""Builds or updates TimeLiner tasks from an Excel or CSV schedule, or writes a template to fill in."""
import os

from pynavis import forms, script, toast

from namo import config as namo_config
from namo import fourd_attach, fourd_common, fourd_ui, progress, timeliner, ui

TITLE = 'TimeLiner from Excel'
DEFAULTS = {'mode': 'merge', 'day_first': True, 'attach': True, 'last_file': ''}
FILTER = ('Schedules (*.xlsx;*.csv)|*.xlsx;*.csv|Excel workbooks (*.xlsx)|*.xlsx|'
          'CSV files (*.csv)|*.csv')


def write_template(doc, rows, types):
    path = fourd_common.ask_save(doc, 'TimeLiner tasks', 'xlsx', 'Write a TimeLiner template')
    if path is None:
        return
    for row in rows:
        row['attach_hint'] = timeliner.attach_paths(row, doc)
    try:
        timeliner.write_template_xlsx(path, timeliner.template_rows(rows), types,
                                      author=namo_config.user_name())
    except (IOError, OSError) as error:
        toast.error('Could not write the template', 'Close it in Excel, then try again. %s' % error)
        return
    what = '%s from the model' % fourd_common.plural(len(rows), 'task') if rows else 'three example tasks'
    toast.success('Template written with %s' % what, path)
    fourd_common.open_file(path)


def ask_import(existing):
    values = script.get_config(DEFAULTS)
    last = values.get('last_file') or ''
    fields = [
        {'kind': 'file_open', 'key': 'path', 'label': 'Schedule (Excel or CSV)', 'filter': FILTER,
         'default': last if last and os.path.exists(last) else '', 'required': True},
        {'kind': 'radio', 'key': 'mode', 'label': 'Tasks already in TimeLiner',
         'options': [('Merge: update tasks with the same Task ID, add the rest', 'merge'),
                     ('Replace: delete every task, then import the sheet', 'replace')],
         'default': values.get('mode', 'merge'), 'fallback': 'merge'},
        {'kind': 'radio', 'key': 'day_first', 'label': 'Dates typed as text', 'inline': True,
         'options': [('Day first (31/12/2026)', True), ('Month first (12/31/2026)', False)],
         'default': bool(values.get('day_first', True))},
        {'kind': 'check', 'key': 'attach', 'label': 'Attach model items from the Attach column',
         'default': bool(values.get('attach', True))},
    ]
    intro = ('TimeLiner holds %s now. Rows are checked before anything changes.'
             % fourd_common.plural(len(existing), 'task'))
    answer = ui.form(TITLE, fields, intro=intro, ok='Check')
    if answer is None:
        return None
    values.update({'mode': answer['mode'], 'day_first': bool(answer['day_first']),
                   'attach': bool(answer['attach']), 'last_file': answer['path']})
    script.save_config(values)
    return values


def resolve_attachments(doc, tasks, report):
    """{row: target} for every task with attach text, and [(row, name, entry, why)] misses."""
    from pynavis import sets
    found_sets = {}

    def set_exists(path):
        if path not in found_sets:
            try:
                saved = sets.find(path, doc)
                found_sets[path] = saved if saved is not None and not saved.IsGroup else None
            except Exception:
                found_sets[path] = None
        return found_sets[path] is not None
    plans = timeliner.attach_targets(tasks, set_exists)
    names = dict((t['row'], t['name']) for t in tasks)
    misses = []
    groups = [conds for plan in plans.values() for conds in plan['rules']]
    index = None
    if groups:
        report(0.1, 'Finding every object in the model')
        objects = fourd_attach.model_objects(doc, tick=lambda done, total: report(0.15, 'Finding objects'))
        index = fourd_attach.ObjectIndex(objects, fourd_attach.read_pairs)
        index.prepare(groups, tick=lambda done, total: report(
            0.2 + 0.5 * done / float(total or 1), 'Reading properties of %s objects' % '{:,}'.format(total)))
    targets = {}
    for row in sorted(plans):
        plan = plans[row]
        for entry, why in plan['misses']:
            misses.append((row, names.get(row, ''), entry, why))
        matched = []
        for conds in plan['rules']:
            hits = index.find(conds)
            if not hits:
                misses.append((row, names.get(row, ''), ' & '.join(_rule_text(c) for c in conds),
                               'The rule matched no objects.'))
            matched.extend(hits)
        saved = [found_sets[path] for path in plan['sets']]
        if matched and saved:
            for item in saved:
                matched.extend(list(sets.items_of(item, doc)))
            targets[row] = ('items', matched)
        elif matched:
            targets[row] = ('items', matched)
        elif saved:
            targets[row] = ('sets', saved)
    return targets, misses


def _rule_text(cond):
    from namo import rules
    return rules.describe(cond)


def import_schedule(doc, existing, types):
    values = ask_import(existing)
    if values is None:
        return
    try:
        sheet = timeliner.read_sheet(values['last_file'])
    except ValueError as error:
        toast.error('Could not read the schedule', str(error))
        return
    ids = [r['id'] for r in existing if r.get('id')]
    parsed = timeliner.parse_rows(sheet, values['day_first'], types,
                                  ids if values['mode'] == 'merge' else None)
    if parsed['header_row'] is None:
        toast.error('No header row found', parsed['problems'][0]['message'])
        return
    valid = [t for t in parsed['tasks'] if t['ok']]
    if not valid:
        first = parsed['problems'][0]['message'] if parsed['problems'] else 'The sheet has no task rows.'
        toast.error('No task can be imported', first)
        return
    plan = timeliner.plan_import(parsed, existing, values['mode'])
    summary = fourd_ui.import_summary(plan)
    if parsed['problems']:
        rows = fourd_ui.problem_rows(parsed['problems'])
        if not fourd_ui.review(TITLE, ['Row', 'Level', 'Column', 'Problem'], rows, summary,
                               'Import %s' % fourd_common.plural(len(valid), 'task')):
            return
    elif not forms.confirm(summary + ' Continue?', title=TITLE):
        return

    def work(report):
        targets, misses = {}, []
        if values['attach'] and 'attach' in parsed['columns']:
            targets, misses = resolve_attachments(doc, valid, report)
        report(0.8, 'Writing TimeLiner tasks')
        timeliner.commit_import(plan, lambda task: targets.get(task['row']), doc)
        return targets, misses
    try:
        outcome = progress.run(TITLE, work)
    except RuntimeError as error:
        toast.error('Could not write the TimeLiner tasks', '%s Nothing was imported; if tasks look wrong, '
                    'press Ctrl+Z.' % error)
        return
    if outcome is progress.CANCELLED:
        return
    targets, misses = outcome
    detail = '%s new, %s updated' % ('{:,}'.format(plan['created']), '{:,}'.format(plan['updated']))
    if targets:
        detail += ', %s attached' % fourd_common.plural(len(targets), 'task')
    if parsed['problems']:
        errors = len([p for p in parsed['problems'] if p['level'] == 'error'])
        if errors:
            detail += ', %s skipped' % fourd_common.plural(plan['skipped'], 'row')
    total = plan['created'] + plan['updated']
    if misses:
        toast.warning('Imported %s; %s found nothing' % (fourd_common.plural(total, 'task'),
                                                         fourd_common.plural(len(misses), 'attach entry',
                                                                             'attach entries')), detail)
        rows = [{'cells': [m[0], m[1], m[2], m[3]], 'value': i} for i, m in enumerate(misses)]
        ui.table_window('Attach entries that found nothing', ['Row', 'Task', 'Entry', 'Why'], rows,
                        modeless=True, key='playground-timeliner-misses',
                        status='Fix the Attach cells, then import again with Merge.')
    else:
        toast.success('Imported %s' % fourd_common.plural(total, 'task'), detail)


def run():
    if ui.is_runner():
        toast.info('%s asks for a file' % TITLE, 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    if not fourd_common.has_models(doc):
        toast.info('No model is open', 'Open or append a model first.')
        return
    try:
        types = timeliner.task_types(doc)
        existing = timeliner.snapshot(doc)
    except RuntimeError as error:
        toast.error('TimeLiner is not available', str(error))
        return
    action = forms.ask_options('Import a schedule into TimeLiner, or write a template to fill in?',
                               ['Import a schedule', 'Write a template'], title=TITLE)
    if action is None:
        return
    if action == 'Write a template':
        write_template(doc, existing, types)
    else:
        import_schedule(doc, existing, types)


run()

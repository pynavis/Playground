# -*- coding: utf-8 -*-
"""Schedule Health: TimeLiner checks (attachments, dates, overlaps, coverage) with a score,
as a standalone HTML report, plus a 'Playground/Not scheduled' selection set."""
from namo import reports

TITLE = 'Schedule Health'


def default_config():
    """'coverage': walk the model for objects in no task (and overlaps); 'create_set':
    put those objects in the selection set named 'set_path'."""
    return reports.base_config(coverage=True, create_set=True, set_path='Playground/Not scheduled')


def describe(config):
    parts = ['Dates and attachments']
    if config.get('coverage'):
        parts.append('coverage')
    if config.get('create_set'):
        parts.append('set %s' % config.get('set_path'))
    return ', '.join(parts)


def _name(row):
    return ('%s %s' % (row.get('outline') or '', row.get('name') or '')).strip()


def run(config, doc=None, interactive=True, progress=None):
    from namo import config as namo_config, dates, fourd_common, items, timeliner
    try:
        rows = timeliner.snapshot(doc)
    except RuntimeError as error:
        return reports.result('error', 'TimeLiner is not available', str(error))
    if not rows:
        return reports.result('info', 'No TimeLiner tasks',
                              'Add tasks in TimeLiner, or build them with TimeLiner from Excel.')
    task_objects = None
    all_objects = None
    if config.get('coverage', True):
        task_objects = {}
        leaves = [i for i, r in enumerate(rows) if not r.get('has_children')
                  and (r.get('attach_kind') or 'none') != 'none']
        for done, index in enumerate(leaves):
            if progress:
                progress(0.6 * done / float(len(leaves) or 1), 'Reading the items of each task')
            collection = timeliner.selected_items(rows[index]['task'], doc)
            task_objects[index] = set(items.objects(collection)) if collection is not None else set()
        if progress:
            progress(0.6, 'Finding every object in the model')

        def tick(done, total):
            if progress:
                progress(0.6 + 0.3 * min(1.0, done / 500000.0), 'Finding every object in the model')
        all_objects = set(items.objects(items.roots(doc), tick=tick))
    found = timeliner.health(rows, task_objects, all_objects, dates.today())
    set_note = ''
    if config.get('create_set', True) and found['unscheduled']:
        set_note = _write_set(config.get('set_path') or 'Playground/Not scheduled', found['unscheduled'], doc)
    if progress:
        progress(0.95, 'Writing the report')
    report = _report(rows, found, config, fourd_common.doc_title(doc), namo_config.user_name(), set_note)
    path = reports.output_path(config, TITLE, 'html')
    try:
        report.save(path)
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the report', str(error))
    problems = len(set(found['unattached']) | set(found['missing_dates']) | set(found['end_before_start']))
    level = 'success' if found['score'] >= 85 else 'warning'
    detail = '%s with problems' % fourd_common.plural(problems, 'task')
    if all_objects is not None:
        detail += ', %s in no task' % fourd_common.plural(len(found['unscheduled']), 'object')
    if set_note:
        detail += '. ' + set_note
    return reports.result(level, 'Schedule health %d of 100' % found['score'], detail, paths=[path])


def _write_set(path, objects, doc):
    from pynavis import sets
    folder, _sep, name = path.rpartition('/')
    try:
        existing = sets.find(path, doc)
        if existing is not None:
            sets.update(existing, list(objects), doc)
        else:
            sets.create(name, list(objects), folder=folder or None, doc=doc)
        return 'Saved them in the set %s.' % path
    except Exception as error:
        from namo import session
        session.log('warning', 'schedule health: set not written: %s' % error)
        return 'The set %s could not be written.' % path


def _report(rows, found, config, doc_name, user, set_note):
    from namo import htmlreport, timeliner
    leaves = len(found['leaves'])
    report = htmlreport.Report('Schedule health', subtitle=doc_name or None,
                               meta=[('Tasks', len(rows)), ('Leaf tasks', leaves), ('By', user)])
    date_problems = len(set(found['missing_dates']) | set(found['end_before_start']))
    kpis = [('Score', found['score'], timeliner.score_tone(found['score']), 'of 100'),
            ('No items attached', len(found['unattached']), 'bad' if found['unattached'] else 'good'),
            ('Date problems', date_problems, 'bad' if date_problems else 'good')]
    if config.get('coverage', True):
        kpis.append(('In more than one task', len(found['overlap']), 'warn' if found['overlap'] else 'good'))
        kpis.append(('Objects in no task', len(found['unscheduled']), 'bad' if found['unscheduled'] else 'good'))
    report.kpis(kpis)
    report.bar_chart(['No items attached', 'Missing dates', 'End before start', 'Zero duration'],
                     [len(found['unattached']), len(found['missing_dates']),
                      len(found['end_before_start']), len(found['zero_duration'])],
                     title='Tasks with problems')

    def task_table(title, indexes, intro):
        report.section(title, intro=intro)
        if not indexes:
            report.note('None.')
            return
        table = [[rows[i].get('outline'), rows[i].get('id') or '', rows[i].get('name') or '',
                  rows[i].get('start'), rows[i].get('end'), rows[i].get('type') or ''] for i in indexes]
        report.table(['WBS', 'Task ID', 'Name', 'Start', 'End', 'Type'], table, max_rows=2000)
    task_table('No items attached', found['unattached'],
               'Leaf tasks that hide or show nothing in a simulation.')
    task_table('Missing dates', found['missing_dates'], 'Leaf tasks without a planned start or end.')
    task_table('End before start', found['end_before_start'],
               'Tasks whose planned or actual end is earlier than their start.')
    task_table('Zero duration', found['zero_duration'],
               'Leaf tasks that start and end at the same moment; fine for milestones.')
    if config.get('coverage', True):
        report.section('In more than one task', intro='Objects attached to several leaf tasks.')
        if found['overlap']:
            table = []
            ordered = sorted(found['overlap'].items(),
                             key=lambda kv: (-len(kv[1]), str(getattr(kv[0], 'DisplayName', ''))))
            for obj, owners in ordered[:500]:
                table.append([str(getattr(obj, 'DisplayName', obj) or ''), len(owners),
                              '; '.join(_name(rows[i]) for i in owners[:5])])
            report.table(['Object', 'Tasks', 'Task names'], table)
        else:
            report.note('None.')
        report.section('Objects in no task',
                       intro='%s of %s objects are not attached to any task.'
                       % ('{:,}'.format(len(found['unscheduled'])),
                          '{:,}'.format(len(found['unscheduled']) + found['scheduled'])))
        if set_note:
            report.note(set_note)
    report.section('How the score works')
    phrases = {'unattached': 'leaf tasks with nothing attached',
               'dates': 'leaf tasks with missing or reversed dates',
               'overlap': 'objects in more than one task', 'unscheduled': 'objects in no task'}
    report.bullets(['Up to %d points off for %s, in proportion.' % (int(round(weight * 100)), phrases[name])
                    for name, weight in timeliner.HEALTH_WEIGHTS])
    return report

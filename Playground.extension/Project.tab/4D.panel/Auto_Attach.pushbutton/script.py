# -*- coding: utf-8 -*-
"""Attaches model items to TimeLiner tasks by rules on task names, IDs, types and user fields."""
from pynavis import script, toast

from namo import fourd_attach, fourd_common, fourd_ui, progress, templates, timeliner, ui

TITLE = 'Auto Attach'
TEMPLATES = 'auto_attach'
DEFAULTS = {'rules': fourd_attach.EXAMPLE, 'mode': 'skip', 'leaf_only': True}
MODES = [('Skip tasks that already have items', 'skip'), ('Replace the items they have', 'replace'),
         ('Add to the items they have', 'add')]


def validate_rules(text):
    found, errors = fourd_attach.parse_rules(text)
    if errors:
        return 'Line %d: %s' % errors[0]
    if not found:
        return 'Write at least one rule (lines starting with # are notes).'
    return None


def ask(values):
    fields = [
        {'kind': 'textarea', 'key': 'rules', 'label': 'Rules, one per line', 'rows': 9,
         'default': values.get('rules') or fourd_attach.EXAMPLE, 'validate': validate_rules,
         'hint': 'Task field, test, then => and a set or conditions joined by &. '
                 'The first rule that matches a task wins.'},
        {'kind': 'radio', 'key': 'mode', 'label': 'Tasks that already have items', 'options': MODES,
         'default': values.get('mode', 'skip'), 'fallback': 'skip'},
        {'kind': 'check', 'key': 'leaf_only', 'label': 'Leaf tasks only (not summary tasks)',
         'default': bool(values.get('leaf_only', True))},
        {'kind': 'text', 'key': 'save_as', 'label': 'Save these rules as a template (optional)',
         'placeholder': 'Template name'},
    ]
    return ui.form(TITLE, fields, ok='Preview', width=620)


def preview(doc, rows, entries, mode, report):
    """[{'entry', 'row', 'found': [items], 'sets': [SavedItem], 'attached': n, 'action'}]."""
    from pynavis import sets
    groups = [e['targets']['conditions'] for e in entries if e.get('targets') and e['targets']['conditions']]
    index = None
    if groups:
        report(0.05, 'Finding every object in the model')
        objects = fourd_attach.model_objects(doc, tick=lambda done, total: report(0.1, 'Finding objects'))
        index = fourd_attach.ObjectIndex(objects, fourd_attach.read_pairs)
        index.prepare(groups, tick=lambda done, total: report(
            0.15 + 0.6 * done / float(total or 1), 'Reading properties of %s objects' % '{:,}'.format(total)))
    found_sets = {}
    out = []
    for number, entry in enumerate(entries):
        report(0.75 + 0.2 * number / float(len(entries) or 1), 'Checking tasks')
        row = rows[entry['index']]
        item = {'entry': entry, 'row': row, 'found': [], 'sets': [], 'missing_sets': [], 'attached': 0}
        if (row.get('attach_kind') or 'none') != 'none':
            current = timeliner.selected_items(row['task'], doc)
            item['attached'] = current.Count if current is not None else 0
            item['has'] = True
        targets = entry.get('targets')
        if targets:
            for path in targets['sets']:
                if path not in found_sets:
                    saved = sets.find(path, doc)
                    found_sets[path] = saved if saved is not None and not saved.IsGroup else None
                if found_sets[path] is None:
                    item['missing_sets'].append(path)
                else:
                    item['sets'].append(found_sets[path])
            if targets['conditions']:
                item['found'] = index.find(targets['conditions'])
        item['count'] = len(item['found']) + sum(sets.items_of(s, doc).Count for s in item['sets'])
        item['action'] = action_of(item, mode)
        out.append(item)
    return out


def action_of(item, mode):
    entry = item['entry']
    if entry['rule'] is None:
        return ('none', 'No rule matched')
    if entry.get('error'):
        return ('error', entry['error'])
    if not item['count']:
        if item['missing_sets']:
            return ('empty', 'No set called %s' % item['missing_sets'][0])
        return ('empty', 'Found nothing')
    if item.get('has') and mode == 'skip':
        return ('skip', 'Skip: has %s' % fourd_common.plural(item['attached'], 'item'))
    verb = {'replace': 'Replace with', 'add': 'Add'}.get(mode, 'Attach') if item.get('has') else 'Attach'
    return ('attach', '%s %s' % (verb, fourd_common.plural(item['count'], 'item')))


def preview_rows(items):
    out = []
    for index, item in enumerate(items):
        row = item['row']
        rule = item['entry']['rule']
        out.append({'cells': [row.get('outline'), row.get('name') or '', 'Line %d' % rule['line'] if rule else '',
                              item['count'], item['attached'], item['action'][1]], 'value': index})
    return out


def apply(doc, items, mode):
    from pynavis import sets
    changes = []
    for item in items:
        if item['action'][0] != 'attach':
            continue
        if item['found'] or mode == 'add' and item.get('has'):
            objects = list(item['found'])
            for saved in item['sets']:
                objects.extend(list(sets.items_of(saved, doc)))
            if mode == 'add' and item.get('has'):
                current = timeliner.selected_items(item['row']['task'], doc)
                if current is not None:
                    objects.extend(list(current))
            target = ('items', objects)
        else:
            target = ('sets', item['sets'])
        changes.append((item['row'], _setter(target, doc)))
    return timeliner.edit_tasks(changes, doc, 'Auto attach')


def _setter(target, doc):
    def edit(values):
        timeliner.set_attachment(values, target, doc)
    return edit


def run():
    if ui.is_runner():
        toast.info('%s needs a person at the screen' % TITLE, 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    try:
        rows = timeliner.snapshot(doc)
    except RuntimeError as error:
        toast.error('TimeLiner is not available', str(error))
        return
    if not rows:
        toast.info('No TimeLiner tasks', 'Add tasks in TimeLiner, or build them with TimeLiner from Excel.')
        return
    values = script.get_config(DEFAULTS)
    answer = ask(values)
    if answer is None:
        return
    values.update({'rules': answer['rules'], 'mode': answer['mode'], 'leaf_only': bool(answer['leaf_only'])})
    script.save_config(values)
    if answer['save_as'].strip():
        try:
            templates.Templates(TEMPLATES).save(answer['save_as'], {'rules': answer['rules']})
        except (ValueError, IOError) as error:
            toast.warning('Rules not saved as a template', str(error))
    rule_list, _errors = fourd_attach.parse_rules(answer['rules'])
    entries = fourd_attach.plan(rows, rule_list, bool(answer['leaf_only']))
    if not entries:
        toast.info('No tasks to attach to', 'Every task is a summary task; untick Leaf tasks only.')
        return
    items = progress.run(TITLE, lambda report: preview(doc, rows, entries, answer['mode'], report))
    if items is progress.CANCELLED:
        return
    todo = [i for i in items if i['action'][0] == 'attach']
    unmatched = len([i for i in items if i['action'][0] == 'none'])
    empty = len([i for i in items if i['action'][0] in ('empty', 'error')])
    if not todo:
        toast.info('Nothing to attach', '%s matched no rule, %s found nothing.'
                   % (fourd_common.plural(unmatched, 'task'), fourd_common.plural(empty, 'rule match', 'rule matches')))
        return
    status = '%s to attach, %s matched no rule, %s found nothing.' % (
        fourd_common.plural(len(todo), 'task'), '{:,}'.format(unmatched), '{:,}'.format(empty))
    if not fourd_ui.review(TITLE, ['WBS', 'Task', 'Rule', 'Items found', 'Attached now', 'Action'],
                           preview_rows(items), status, 'Attach to %s' % fourd_common.plural(len(todo), 'task')):
        return
    written, errors = apply(doc, items, answer['mode'])
    detail = '%s matched no rule, %s found nothing.' % (fourd_common.plural(unmatched, 'task'), '{:,}'.format(empty))
    if errors:
        toast.warning('Attached items to %s, %d failed' % (fourd_common.plural(written, 'task'), len(errors)),
                      errors[0])
    else:
        toast.success('Attached items to %s' % fourd_common.plural(written, 'task'), detail)


run()

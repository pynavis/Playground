# -*- coding: utf-8 -*-
"""TimeLiner: every Playground access to Navisworks TimeLiner, plus the pure schedule logic.

Pure half (unit tested on both engines): reading a schedule sheet (header aliases,
dates through namo.dates, progress as 0..100 or Excel fractions, hierarchy from a
Parent ID, a WBS code or an outline level), validating it (dates, duplicates, missing
parents, cycles, problems inherited by children), planning an import (replace all, or
merge by Task ID), outline numbers, durations, task status and the Schedule Health
checks and score.

API half (lazy imports; nothing Navisworks at module level):
  * The TimeLiner part of a document: TimelinerDocumentExtensions.GetTimeliner(doc)
    (static, the documented route), else DocumentTimeliner.TimelinerInstance(doc), else
    doc.Timeliner (IDocumentTimeliner). Autodesk.Navisworks.Timeliner is loaded with
    clr.AddReference first, exactly as pynavis.clash does for Clash.
  * Reading: snapshot() walks TasksRoot depth first into plain dict rows that keep a
    reference to the live task for this run only.
  * Writing, always ONE undo step (pynavis.viewpoints.transaction):
      - import: the new task tree is built DETACHED, bottom up (each node a fresh
        TimelinerTask, or CreateCopyWithoutChildren() of a live task for a merge, its
        children added before it is added to its own parent: the shape pynavis.clash
        verified for clash groups), then committed with ONE TasksCopyFrom(roots).
        If TasksCopyFrom refuses, TasksClear() + TaskAddCopy(root) per root, in the
        same transaction.
      - edits of existing tasks (attachments, progress): TaskEdit(parent, index,
        values) per task, values = CreateCopyWithoutChildren() of the live task with
        the change applied.
Every behaviour above is inferred from the 2026 API dump; dev/notes/fourd_qty_field.md
lists the in-app checks.
"""

import datetime
import re

from namo import dates, naming, rules

# ---- columns -----------------------------------------------------------------------------

USER_FIELDS = ['user%d' % n for n in range(1, 11)]

# field -> header spellings (compared lowercased, single-spaced, trailing ':' dropped).
HEADER_ALIASES = [
    ('id', ['task id', 'id', 'display id', 'activity id', 'task number', 'task no', 'task code']),
    ('parent', ['parent id', 'parent', 'parent task id', 'parent task', 'parent activity id']),
    ('wbs', ['wbs', 'wbs code', 'outline number']),
    ('outline', ['outline level', 'indent level', 'outline']),
    ('name', ['name', 'task name', 'task', 'activity name', 'activity']),
    ('start', ['start', 'planned start', 'start date', 'planned start date', 'start time']),
    ('end', ['end', 'finish', 'planned end', 'planned finish', 'end date', 'finish date',
             'planned end date', 'planned finish date', 'end time']),
    ('actual_start', ['actual start', 'actual start date', 'actual start time']),
    ('actual_end', ['actual end', 'actual finish', 'actual end date', 'actual finish date',
                    'actual end time']),
    ('type', ['task type', 'type', 'simulation type', 'simulation task type']),
    ('attach', ['attach', 'attached', 'attachment', 'attach to', 'selection set', 'set']),
    ('progress', ['progress %', 'progress', '% complete', 'percent complete', 'complete %',
                  'progress percent', '% done']),
] + [('user%d' % n, ['user%d' % n, 'user %d' % n, 'user field %d' % n, 'text%d' % n,
                     'text %d' % n]) for n in range(1, 11)]

# What the template writes, in order. Attach and the user fields round-trip.
TEMPLATE_COLUMNS = [
    ('id', 'Task ID', 12), ('parent', 'Parent ID', 12), ('name', 'Name', 40),
    ('start', 'Start', 13), ('end', 'End', 13), ('actual_start', 'Actual start', 13),
    ('actual_end', 'Actual end', 13), ('type', 'Task type', 14), ('attach', 'Attach', 42),
    ('progress', 'Progress %', 11), ('user1', 'User1', 14), ('user2', 'User2', 14),
    ('user3', 'User3', 14),
]

DEFAULT_TYPES = ['Construct', 'Demolish', 'Temporary']
DATE_FIELDS = ('start', 'end', 'actual_start', 'actual_end')
FIELD_LABELS = {'id': 'Task ID', 'parent': 'Parent ID', 'wbs': 'WBS', 'outline': 'Outline level',
                'name': 'Name', 'start': 'Start', 'end': 'End', 'actual_start': 'Actual start',
                'actual_end': 'Actual end', 'type': 'Task type', 'attach': 'Attach',
                'progress': 'Progress %'}
for _n in range(1, 11):
    FIELD_LABELS['user%d' % _n] = 'User%d' % _n

MODES = ('merge', 'replace')


def normalise_header(text):
    """'  Planned  Start: ' -> 'planned start'."""
    value = rules.text_of(text).lower().replace('_', ' ')
    value = ' '.join(value.split())
    return value.rstrip(':').strip()


_ALIAS_INDEX = {}
for _field, _names in HEADER_ALIASES:
    for _name in _names:
        _ALIAS_INDEX.setdefault(_name, _field)


def field_of(header):
    """The schedule field a header cell names, or None."""
    return _ALIAS_INDEX.get(normalise_header(header))


def map_headers(row):
    """{field: column index} for a header row (first column wins for a repeated field)."""
    mapping = {}
    for index, cell in enumerate(row or []):
        field = field_of(cell)
        if field is not None and field not in mapping:
            mapping[field] = index
    return mapping


def find_header(rows, scan=20):
    """(row index, mapping) of the first row in the first `scan` rows that names the
    task Name and at least one more known column; (None, {}) when there is none."""
    for index, row in enumerate(rows[:scan]):
        mapping = map_headers(row)
        if 'name' in mapping and len(mapping) >= 2:
            return index, mapping
    return None, {}


def cell_text(value):
    """A cell as trimmed text: None '', 12.0 '12', True 'Yes', text trimmed."""
    if value is None:
        return ''
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return rules.text_of(value)


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def progress_scale(values):
    """100.0 when a progress column holds Excel percentages (every number within 0..1 and
    at least one strictly between), else 1.0."""
    numbers = []
    for value in values:
        if _blank(value):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numbers.append(float(value))
        else:
            text = str(value).strip()
            if text.endswith('%'):
                return 1.0
            number = rules.to_number(text)
            if number is None:
                continue
            numbers.append(number)
    if numbers and all(0.0 <= n <= 1.0 for n in numbers) and any(0.0 < n < 1.0 for n in numbers):
        return 100.0
    return 1.0


def parse_progress(value, scale=1.0):
    """(percent 0..100 or None, problem sentence or None)."""
    if _blank(value):
        return None, None
    if isinstance(value, bool):
        return None, 'Progress must be a number from 0 to 100.'
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().rstrip('%').strip()
        try:
            number = float(text.replace(',', '.')) if text.count(',') == 1 and '.' not in text \
                else float(text.replace(',', ''))
        except ValueError:
            return None, 'Progress "%s" is not a number.' % str(value).strip()
    number *= scale
    if number < -1e-9 or number > 100.0 + 1e-9:
        return None, 'Progress must be from 0 to 100, not %s.' % naming.format_value(number)
    return max(0.0, min(100.0, number)), None


def _wbs_parent(wbs):
    text = str(wbs).strip().rstrip('.')
    if '.' not in text:
        return ''
    return text.rsplit('.', 1)[0]


def _problem(problems, row, field, message, level='error'):
    problems.append({'row': row, 'field': field, 'label': FIELD_LABELS.get(field, field or ''),
                     'message': message, 'level': level})


def parse_rows(rows, day_first=True, known_types=None, existing_ids=None):
    """Reads a schedule sheet (a list of rows of cell values, as pynavis.xl.read or the
    csv module give them). Returns

        {'header_row': 1-based row of the header or None,
         'columns': [fields present], 'hierarchy': 'parent' | 'wbs' | 'outline' | 'flat',
         'tasks': [task], 'problems': [problem], 'scale': progress scale used}

    task = {'row', 'id', 'parent', 'name', 'start', 'end', 'actual_start', 'actual_end'
    (datetimes or None), 'type' (canonical name or text), 'attach' (text), 'progress'
    (0..100 or None), 'user': {1: text, ...}, 'present': [fields that have a value in
    this row], 'ok' (no errors), 'children': [] (filled by build_tree)}.
    problem = {'row', 'field', 'label', 'message', 'level' ('error' | 'warning')}.

    existing_ids: Task IDs already in the model (merge): a Parent ID may name one of them.
    known_types: the document's task type names (case-insensitive match to canonical)."""
    problems = []
    header_index, mapping = find_header(rows)
    out = {'header_row': None, 'columns': [], 'hierarchy': 'flat', 'tasks': [],
           'problems': problems, 'scale': 1.0}
    if header_index is None:
        _problem(problems, None, None, 'No header row found. The sheet needs a Name column '
                 'and at least one other, such as Task ID or Start.')
        return out
    out['header_row'] = header_index + 1
    out['columns'] = sorted(mapping, key=lambda f: [f2 for f2, _ in HEADER_ALIASES].index(f))
    data_rows = rows[header_index + 1:]

    def cell(row, field):
        index = mapping.get(field)
        if index is None or index >= len(row):
            return None
        return row[index]

    scale = progress_scale([cell(r, 'progress') for r in data_rows]) if 'progress' in mapping else 1.0
    out['scale'] = scale
    types = {}
    for name in (known_types if known_types is not None else DEFAULT_TYPES):
        types.setdefault(str(name).strip().lower(), str(name))

    tasks = []
    for offset, row in enumerate(data_rows):
        row_no = header_index + 2 + offset
        if not row or all(_blank(v) for v in row):
            continue
        task = {'row': row_no, 'id': cell_text(cell(row, 'id')), 'parent': cell_text(cell(row, 'parent')),
                'wbs': cell_text(cell(row, 'wbs')), 'outline': None,
                'name': cell_text(cell(row, 'name')), 'type': cell_text(cell(row, 'type')),
                'attach': rules.text_of(cell(row, 'attach')) if not _blank(cell(row, 'attach')) else '',
                'progress': None, 'user': {}, 'present': [], 'ok': True, 'children': [],
                'errors': []}
        for field in DATE_FIELDS:
            task[field] = None
        for field in ('id', 'parent', 'name', 'type', 'attach', 'wbs'):
            if task[field]:
                task['present'].append(field)
        if not task['name']:
            _problem(problems, row_no, 'name', 'The task has no name.')
            task['ok'] = False
        for field in DATE_FIELDS:
            raw = cell(row, field)
            if _blank(raw):
                continue
            parsed = dates.parse(raw, day_first=day_first)
            if parsed is None:
                _problem(problems, row_no, field, '%s "%s" is not a date.'
                         % (FIELD_LABELS[field], rules.text_of(raw)))
                task['ok'] = False
            else:
                task[field] = parsed
                task['present'].append(field)
        if task['start'] and task['end'] and task['end'] < task['start']:
            _problem(problems, row_no, 'end', 'End is before Start.')
            task['ok'] = False
        if task['actual_start'] and task['actual_end'] and task['actual_end'] < task['actual_start']:
            _problem(problems, row_no, 'actual_end', 'Actual end is before Actual start.')
            task['ok'] = False
        value, error = parse_progress(cell(row, 'progress'), scale)
        if error:
            _problem(problems, row_no, 'progress', error)
            task['ok'] = False
        elif value is not None:
            task['progress'] = value
            task['present'].append('progress')
        if task['type']:
            canonical = types.get(task['type'].lower())
            if canonical is None:
                _problem(problems, row_no, 'type', 'Task type "%s" is not defined in TimeLiner; '
                         'add it on the Configure tab or it shows as blank.' % task['type'], 'warning')
            else:
                task['type'] = canonical
        for n in range(1, 11):
            raw = cell(row, 'user%d' % n)
            if not _blank(raw):
                task['user'][n] = cell_text(raw)
                task['present'].append('user%d' % n)
        if 'outline' in mapping:
            level = rules.to_number(cell(row, 'outline'))
            task['outline'] = int(level) if level is not None and level >= 0 else None
        tasks.append(task)

    hierarchy = 'flat'
    if 'parent' in mapping and any(t['parent'] for t in tasks):
        hierarchy = 'parent'
    elif 'wbs' in mapping and any(t['wbs'] for t in tasks):
        hierarchy = 'wbs'
    elif 'outline' in mapping and any(t['outline'] is not None for t in tasks):
        hierarchy = 'outline'
    out['hierarchy'] = hierarchy

    if hierarchy == 'wbs':
        for task in tasks:
            if not task['id'] and task['wbs']:
                task['id'] = task['wbs']
                task['present'].append('id')
    # Duplicate ids: the first keeps the id, later rows are errors.
    seen = {}
    for task in tasks:
        if not task['id']:
            continue
        if task['id'] in seen:
            _problem(problems, task['row'], 'id', 'Task ID %s is also used on row %d.'
                     % (task['id'], seen[task['id']]))
            task['ok'] = False
            task['duplicate'] = True
        else:
            seen[task['id']] = task['row']
    by_id = dict((t['id'], t) for t in tasks if t['id'] and not t.get('duplicate'))
    existing = set(existing_ids or [])

    if hierarchy == 'wbs':
        wbs_index = dict((t['wbs'], t) for t in tasks if t['wbs'])
        for task in tasks:
            parent_wbs = _wbs_parent(task['wbs']) if task['wbs'] else ''
            if not parent_wbs:
                continue
            parent = wbs_index.get(parent_wbs)
            if parent is not None:
                task['parent'] = parent['id']
            elif parent_wbs in existing:
                task['parent'] = parent_wbs
            else:
                _problem(problems, task['row'], 'wbs', 'No task has WBS %s; placed at the top level.'
                         % parent_wbs, 'warning')
    elif hierarchy == 'outline':
        stack = []
        for task in tasks:
            level = task['outline'] if task['outline'] is not None else 1
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                parent = stack[-1][1]
                if not parent['id']:
                    parent['id'] = '@row%d' % parent['row']      # internal link only
                    parent['auto_id'] = True
                task['parent'] = parent['id']
            stack.append((level, task))
        by_id = dict((t['id'], t) for t in tasks if t['id'] and not t.get('duplicate'))
    elif hierarchy == 'parent':
        for task in tasks:
            if task['parent'] and task['parent'] == task['id']:
                _problem(problems, task['row'], 'parent', 'The task names itself as its parent.')
                task['ok'] = False
            elif task['parent'] and task['parent'] not in by_id and task['parent'] not in existing:
                _problem(problems, task['row'], 'parent', 'Parent ID %s does not exist.' % task['parent'])
                task['ok'] = False

    # Cycles through Parent IDs inside the sheet.
    for task in tasks:
        chain = []
        seen_ids = []
        node = task
        while node is not None and node['parent'] and node['parent'] in by_id:
            if id(node) in seen_ids:
                break
            chain.append(node)
            seen_ids.append(id(node))
            node = by_id[node['parent']]
        if node is not None and id(node) in seen_ids:
            loop = chain[seen_ids.index(id(node)):]
            for member in loop:
                if member.get('in_cycle'):
                    continue
                member['in_cycle'] = True
                member['ok'] = False
                _problem(problems, member['row'], 'parent', 'Parent IDs form a loop: %s.'
                         % ' > '.join(m['id'] for m in loop + [loop[0]]))

    # Children of a task with errors cannot be placed.
    changed = True
    while changed:
        changed = False
        for task in tasks:
            if not task['ok'] or not task['parent']:
                continue
            parent = by_id.get(task['parent'])
            if parent is not None and not parent['ok']:
                task['ok'] = False
                changed = True
                _problem(problems, task['row'], 'parent', 'Its parent on row %d has problems.'
                         % parent['row'])
    for task in tasks:
        if task['ok'] and (not task['id'] or task.get('auto_id')):
            _problem(problems, task['row'], 'id', 'No Task ID: a later merge cannot update this '
                     'task.', 'warning')
    problems.sort(key=lambda p: (p['row'] or 0, 0 if p['level'] == 'error' else 1, p['field'] or ''))
    out['tasks'] = tasks
    return out


def build_tree(tasks):
    """Roots of the valid tasks with 'children' filled in row order. A task whose parent
    is not among them (an existing model task, or nothing) is a root here."""
    valid = [t for t in tasks if t['ok']]
    by_id = dict((t['id'], t) for t in valid if t['id'])
    for task in valid:
        task['children'] = []
    roots = []
    for task in valid:
        parent = by_id.get(task['parent']) if task['parent'] else None
        if parent is not None and parent is not task:
            parent['children'].append(task)
        else:
            roots.append(task)
    return roots


def walk_tree(roots):
    """(task, depth) depth first over build_tree roots."""
    stack = [(t, 0) for t in reversed(roots)]
    while stack:
        task, depth = stack.pop()
        yield task, depth
        for child in reversed(task.get('children') or []):
            stack.append((child, depth + 1))


def count_tree(roots):
    return sum(1 for _ in walk_tree(roots))


def plan_import(parsed, existing_rows, mode='merge'):
    """What an import does, decided before anything is written.

    existing_rows: snapshot() rows ({'key', 'parent_key', 'id', ...}).
    Returns {'mode', 'roots' (replace: the whole new tree), 'updates': [(key, task)],
    'adds': {existing key: [subtree roots]}, 'new_roots': [subtree roots], 'created',
    'updated', 'kept_in_place' (updated tasks whose Parent ID in the sheet differs from
    where they sit: merge never moves an existing task), 'skipped' (rows with errors),
    'ambiguous': [ids that more than one model task carries; the first is updated]}."""
    if mode not in MODES:
        raise ValueError('mode must be merge or replace')
    tasks = parsed['tasks']
    valid = [t for t in tasks if t['ok']]
    plan = {'mode': mode, 'roots': [], 'updates': [], 'adds': {}, 'new_roots': [],
            'created': 0, 'updated': 0, 'kept_in_place': 0, 'skipped': len(tasks) - len(valid),
            'ambiguous': []}
    if mode == 'replace':
        plan['roots'] = build_tree(tasks)
        plan['created'] = count_tree(plan['roots'])
        return plan
    existing_by_id = {}
    id_of_key = {}
    seen_twice = set()
    for row in existing_rows:
        id_of_key[row['key']] = row.get('id') or ''
        if row.get('id'):
            if row['id'] in existing_by_id:
                seen_twice.add(row['id'])
            else:
                existing_by_id[row['id']] = row
    plan['ambiguous'] = sorted(seen_twice, key=naming.natural_key)
    matched = {}
    for task in valid:
        row = existing_by_id.get(task['id']) if task['id'] else None
        if row is not None:
            matched[task['id']] = row
            plan['updates'].append((row['key'], task))
            current_parent = id_of_key.get(row.get('parent_key'), '') if row.get('parent_key') else ''
            if (task['parent'] or '') != (current_parent or '') and 'parent' in task['present']:
                plan['kept_in_place'] += 1
    plan['updated'] = len(plan['updates'])
    creates = [t for t in valid if not (t['id'] and t['id'] in matched)]
    create_ids = dict((t['id'], t) for t in creates if t['id'])
    for task in creates:
        task['children'] = []
    for task in creates:
        parent_id = task['parent']
        if parent_id and parent_id in create_ids and create_ids[parent_id] is not task:
            create_ids[parent_id]['children'].append(task)
        elif parent_id and parent_id in matched:
            plan['adds'].setdefault(matched[parent_id]['key'], []).append(task)
        elif parent_id and parent_id in existing_by_id:
            plan['adds'].setdefault(existing_by_id[parent_id]['key'], []).append(task)
        else:
            plan['new_roots'].append(task)
    plan['created'] = len(creates)
    return plan


# ---- reading the schedule back ----------------------------------------------------------


def outline_number(key):
    """(0, 2, 1) -> '1.3.2'."""
    return '.'.join(str(i + 1) for i in key)


def duration_days(start, end):
    """Days from start to end (fractions kept), or None."""
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() / 86400.0, 3)


def task_status(row, today=None):
    """'Complete', 'In progress', 'In progress, late', 'Late start', 'Not started' or
    'No dates' from planned/actual dates and progress, as of today."""
    today = today or dates.today()
    progress = row.get('progress')
    if (progress is not None and progress >= 100.0) or row.get('actual_end'):
        return 'Complete'
    started = row.get('actual_start') or (progress is not None and progress > 0.0)
    end = row.get('end')
    start = row.get('start')
    if started:
        if end is not None and end < today:
            return 'In progress, late'
        return 'In progress'
    if start is None and end is None:
        return 'No dates'
    if start is not None and start <= today:
        return 'Late start'
    return 'Not started'


STATUS_TONES = {'Complete': 'good', 'In progress': 'info', 'In progress, late': 'bad',
                'Late start': 'warn', 'Not started': 'neutral', 'No dates': 'neutral'}


def schedule_bounds(rows, actual=False):
    """(earliest start, latest end) over rows, or (None, None)."""
    first = last = None
    for row in rows:
        start = row.get('actual_start') if actual else row.get('start')
        end = row.get('actual_end') if actual else row.get('end')
        if actual:
            start = start or row.get('start')
            end = end or row.get('end')
        for value in (start, end):
            if value is None:
                continue
            if first is None or value < first:
                first = value
            if last is None or value > last:
                last = value
    return first, last


# ---- Schedule Health (pure) ----------------------------------------------------------------

HEALTH_WEIGHTS = (('unattached', 0.25), ('dates', 0.25), ('overlap', 0.15), ('unscheduled', 0.35))


def health(rows, task_objects=None, all_objects=None, today=None):
    """The Schedule Health checks over snapshot rows.

    task_objects: {row index: set of object keys attached} for leaf tasks (None skips the
    overlap and coverage checks); all_objects: set of every geometry object key in the
    model (for 'not in any task').

    Returns {'leaves', 'unattached': [rows], 'missing_dates': [rows], 'end_before_start':
    [rows], 'zero_duration': [rows], 'overlap': {key: [row indexes]}, 'unscheduled':
    set of keys, 'scheduled': count, 'score': 0..100, 'parts': {name: fraction}}."""
    leaves = [i for i, r in enumerate(rows) if not r.get('has_children')]
    out = {'leaves': leaves, 'unattached': [], 'missing_dates': [], 'end_before_start': [],
           'zero_duration': [], 'overlap': {}, 'unscheduled': set(), 'scheduled': 0,
           'score': 100, 'parts': {}}
    for index, row in enumerate(rows):
        if row.get('start') and row.get('end') and row['end'] < row['start']:
            out['end_before_start'].append(index)
        elif row.get('actual_start') and row.get('actual_end') and row['actual_end'] < row['actual_start']:
            out['end_before_start'].append(index)
    for index in leaves:
        row = rows[index]
        if (row.get('attach_kind') or 'none') == 'none':
            out['unattached'].append(index)
        if row.get('start') is None or row.get('end') is None:
            out['missing_dates'].append(index)
        elif row['start'] == row['end']:
            out['zero_duration'].append(index)
    if task_objects is not None:
        owners = {}
        for index in sorted(task_objects):
            for key in task_objects[index]:
                owners.setdefault(key, []).append(index)
        out['overlap'] = dict((k, v) for k, v in owners.items() if len(v) > 1)
        scheduled = set(owners)
        out['scheduled'] = len(scheduled)
        if all_objects is not None:
            out['unscheduled'] = set(all_objects) - scheduled
    n_leaves = float(len(leaves) or 1)
    bad_dates = set(out['missing_dates']) | set(i for i in out['end_before_start'] if i in set(leaves))
    parts = {'unattached': len(out['unattached']) / n_leaves,
             'dates': len(bad_dates) / n_leaves,
             'overlap': 0.0, 'unscheduled': 0.0}
    if task_objects is not None and out['scheduled']:
        parts['overlap'] = len(out['overlap']) / float(out['scheduled'])
    if all_objects:
        parts['unscheduled'] = len(out['unscheduled']) / float(len(all_objects))
    out['parts'] = parts
    penalty = sum(weight * min(1.0, parts[name]) for name, weight in HEALTH_WEIGHTS)
    out['score'] = int(round(100.0 * (1.0 - penalty)))
    if not leaves:
        out['score'] = 0
    return out


def score_tone(score):
    return 'good' if score >= 85 else 'warn' if score >= 60 else 'bad'


# ---- template rows ------------------------------------------------------------------------


def template_rows(rows):
    """Rows (lists, TEMPLATE_COLUMNS order) for an exported template: the model's tasks
    with Parent IDs, or three example tasks when there are none."""
    out = []
    if rows:
        id_of_key = dict((r['key'], r.get('id') or '') for r in rows)
        for row in rows:
            parent = id_of_key.get(row.get('parent_key'), '') if row.get('parent_key') else ''
            values = {'id': row.get('id') or '', 'parent': parent, 'name': row.get('name') or '',
                      'start': row.get('start'), 'end': row.get('end'),
                      'actual_start': row.get('actual_start'), 'actual_end': row.get('actual_end'),
                      'type': row.get('type') or '', 'attach': row.get('attach_hint') or '',
                      'progress': row.get('progress'),
                      'user1': (row.get('user') or [''] * 10)[0],
                      'user2': (row.get('user') or [''] * 10)[1],
                      'user3': (row.get('user') or [''] * 10)[2]}
            out.append([values[field] for field, _label, _w in TEMPLATE_COLUMNS])
        return out
    today = dates.today()
    examples = [
        {'id': '1', 'name': 'Level 1', 'start': today, 'end': today + datetime.timedelta(days=27),
         'type': 'Construct'},
        {'id': '1.1', 'parent': '1', 'name': 'Level 1 columns', 'start': today,
         'end': today + datetime.timedelta(days=9), 'type': 'Construct',
         'attach': 'Element > Category = Structural Columns'},
        {'id': '1.2', 'parent': '1', 'name': 'Level 1 slab', 'start': today + datetime.timedelta(days=10),
         'end': today + datetime.timedelta(days=27), 'type': 'Construct', 'attach': 'Structure/Slabs',
         'progress': 0},
    ]
    for example in examples:
        out.append([example.get(field, '' if field not in DATE_FIELDS and field != 'progress' else None)
                    for field, _label, _w in TEMPLATE_COLUMNS])
    return out


README_LINES = [
    ('Task ID', 'Unique per task. Merge imports update the task with the same ID (TimeLiner Display ID).'),
    ('Parent ID', 'The Task ID of the parent task, in this sheet or already in the model. '
                  'Instead of Parent ID you may use a WBS column (1.2.3) or an Outline level column.'),
    ('Name', 'Required.'),
    ('Start, End', 'Planned dates. Excel dates, ISO text (2026-10-05) or local text dates.'),
    ('Actual start, Actual end', 'Optional actual dates.'),
    ('Task type', 'A TimeLiner task type, such as Construct, Demolish or Temporary.'),
    ('Attach', 'A selection set path (Folder/Set name) or a rule such as '
               'Element > Category = Ducts. Several entries: one per line (Alt+Enter).'),
    ('Progress %', '0 to 100 (Excel percentages also read).'),
    ('User1 to User10', 'Free text; becomes the TimeLiner user columns.'),
    ('Empty cells', 'In a merge, an empty cell leaves the existing value unchanged.'),
]


def split_attach(text):
    """Attach entries from a cell: one per line, blanks dropped."""
    return [line.strip() for line in str(text or '').replace('\r', '\n').split('\n') if line.strip()]


def classify_attach(entry, set_exists):
    """('set', path) when set_exists(path) is True, else ('rule', [conditions]) when the
    entry reads as rules joined by ' & ' (namo.rules.parse_cell; all must hold), else
    ('miss', sentence)."""
    if set_exists(entry):
        return ('set', entry)
    try:
        parts = [p.strip() for p in re.split(r'\s+&\s+', entry) if p.strip()]
        return ('rule', [rules.parse_cell(part) for part in parts])
    except ValueError:
        return ('miss', 'No selection set is called "%s" and it is not a rule.' % entry)


# ---- workbooks ------------------------------------------------------------------------------


def read_sheet(path):
    """Rows of cell values from a schedule file: .csv (UTF-8, comma or semicolon) or
    .xlsx (the sheet named Tasks, else the first). Raises ValueError with a sentence."""
    import io
    import os
    ext = os.path.splitext(str(path))[1].lower()
    if ext == '.csv':
        import csv
        try:
            with io.open(path, 'r', encoding='utf-8-sig', newline='') as handle:
                text = handle.read()
        except (IOError, OSError) as error:
            raise ValueError('Could not read %s: %s' % (os.path.basename(path), error))
        except UnicodeDecodeError:
            with io.open(path, 'r', encoding='cp1252', newline='') as handle:
                text = handle.read()
        first = text.split('\n', 1)[0]
        delimiter = ';' if first.count(';') > first.count(',') else ','
        return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    if ext not in ('.xlsx', '.xlsm'):
        raise ValueError('Use an Excel workbook (.xlsx) or a CSV file.')
    from pynavis import xl
    try:
        names = xl.sheets(path)
        sheet = None
        for name in names:
            if name.strip().lower() == 'tasks':
                sheet = name
                break
        return xl.read(path, sheet)
    except (IOError, OSError) as error:
        raise ValueError('Could not open %s. Close it in Excel, then try again. (%s)'
                         % (os.path.basename(path), error))
    except Exception as error:
        raise ValueError('%s is not a workbook Playground can read: %s' % (os.path.basename(path), error))


def write_template_xlsx(path, rows, types, title='TimeLiner tasks', author=None):
    """The import template: Tasks (TEMPLATE_COLUMNS, dates formatted, Attach wrapped),
    Read me (what each column takes) and Task types (the document's). Returns path."""
    from namo import xlsx
    wb = xlsx.Workbook(title=title, author=author)
    ws = wb.sheet('Tasks')
    specs = []
    for field, label, width in TEMPLATE_COLUMNS:
        style = 'date' if field in DATE_FIELDS else 'num1' if field == 'progress' else \
            'wrap' if field == 'attach' else None
        specs.append((label, width, style))
    ws.columns(specs)
    for row in rows:
        ws.row(row)
    ws.autofilter()
    readme = wb.sheet('Read me')
    readme.title('How to fill in the Tasks sheet', span=2)
    readme.columns([('Column', 24, 'bold'), ('What it takes', 100, 'wrap')], freeze=False)
    for label, text in README_LINES:
        readme.row([label, text])
    kinds = wb.sheet('Task types')
    kinds.columns([('Task type', 24, None)])
    for name in types:
        kinds.row([name])
    return wb.save(path)


def attach_targets(tasks, set_exists):
    """Pure planning of the Attach column: {row: {'sets': [paths], 'rules': [conditions],
    'misses': [(entry, sentence)]}} for every task with attach text."""
    out = {}
    for task in tasks:
        if not task.get('attach'):
            continue
        plan = {'sets': [], 'rules': [], 'misses': []}
        for entry in split_attach(task['attach']):
            kind, value = classify_attach(entry, set_exists)
            if kind == 'set':
                plan['sets'].append(value)
            elif kind == 'rule':
                plan['rules'].append(value)
            else:
                plan['misses'].append((entry, value))
        out[task['row']] = plan
    return out

ATTACH_LABELS = {'none': '', 'sets': 'Selection sets', 'search': 'Search', 'items': 'Items',
                 'other': 'Other'}
STATUS_STYLES = {'Complete': 'good', 'In progress': 'info', 'In progress, late': 'bad',
                 'Late start': 'warn'}


def export_rows(rows, counts=None, today=None):
    """Plain dicts for the export: outline, name, dates, durations, type, progress,
    status, attachment and item count per task (counts: {row index: items})."""
    out = []
    for index, row in enumerate(rows):
        out.append({'depth': row.get('depth', 0), 'outline': row.get('outline') or outline_number(row['key']),
                    'id': row.get('id') or '', 'name': row.get('name') or '',
                    'start': row.get('start'), 'end': row.get('end'),
                    'planned_days': duration_days(row.get('start'), row.get('end')),
                    'actual_start': row.get('actual_start'), 'actual_end': row.get('actual_end'),
                    'actual_days': duration_days(row.get('actual_start'), row.get('actual_end')),
                    'type': row.get('type') or '', 'progress': row.get('progress'),
                    'status': task_status(row, today), 'attach': ATTACH_LABELS.get(row.get('attach_kind') or 'none', ''),
                    'attach_text': row.get('attach_text') or '',
                    'items': (counts or {}).get(index), 'summary': bool(row.get('has_children')),
                    'user': list(row.get('user') or [''] * 10)})
    return out


def write_export_xlsx(path, table, title, subtitle, author=None):
    """TimeLiner Export workbook: Tasks (outline-indented names, parent tasks bold, dates,
    durations, status washes, attachments, user columns that hold anything) and Summary
    (tasks by status and by type). Returns path."""
    from namo import xlsx
    wb = xlsx.Workbook(title=title, author=author)
    depth_max = max([r['depth'] for r in table] + [0])
    for depth in range(min(depth_max, 14) + 1):
        wb.style('tl_name_%d' % depth, indent=depth)
        wb.style('tl_sum_%d' % depth, indent=depth, bold=True)
    users = [n for n in range(10) if any(r['user'][n] for r in table if len(r['user']) > n)]
    ws = wb.sheet('Tasks')
    headers = [('Task ID', 10, None), ('WBS', 9, None), ('Name', 46, None), ('Planned start', 13, 'date'),
               ('Planned end', 13, 'date'), ('Planned days', 9, 'num1'), ('Actual start', 13, 'date'),
               ('Actual end', 13, 'date'), ('Actual days', 9, 'num1'), ('Task type', 13, None),
               ('Progress %', 10, 'num1'), ('Status', 16, None), ('Attached', 14, None),
               ('Items', 9, 'int'), ('Attachment', 34, None)]
    headers += [('User%d' % (n + 1), 14, None) for n in users]
    ws.title(title, span=8)
    ws.subtitle(subtitle, span=8)
    ws.columns(headers)
    for row in table:
        depth = min(row['depth'], 14)
        name_style = ('tl_sum_%d' if row['summary'] else 'tl_name_%d') % depth
        cells = [row['id'], row['outline'], row['name'], row['start'], row['end'], row['planned_days'],
                 row['actual_start'], row['actual_end'], row['actual_days'], row['type'],
                 row['progress'], row['status'], row['attach'], row['items'], row['attach_text']]
        cells += [row['user'][n] for n in users]
        styles = [None, None, name_style] + [None] * 8 + [STATUS_STYLES.get(row['status'])]
        ws.row(cells, styles=styles)
    ws.freeze(rows=ws.header_row + 1, cols=3)
    ws.autofilter()
    summary = wb.sheet('Summary')
    summary.title('Tasks by status and type', span=3)
    summary.columns([('Status', 22, None), ('Tasks', 10, 'int')], freeze=False)
    by_status = {}
    by_type = {}
    for row in table:
        if row['summary']:
            continue
        by_status[row['status']] = by_status.get(row['status'], 0) + 1
        by_type[row['type'] or '(no type)'] = by_type.get(row['type'] or '(no type)', 0) + 1
    for status in ('Complete', 'In progress', 'In progress, late', 'Late start', 'Not started', 'No dates'):
        if status in by_status:
            summary.row([status, by_status[status]], styles=[STATUS_STYLES.get(status)])
    summary.skip()
    summary.row(['Task type', 'Tasks'], styles='header')
    for name in sorted(by_type, key=naming.natural_key):
        summary.row([name, by_type[name]])
    return wb.save(path)


# =============================================================================================
# API half
# =============================================================================================


def _tl():
    """The Autodesk.Navisworks.Api.Timeliner namespace (assembly loaded on first use)."""
    from pynavis import _api
    _api.add_reference('Autodesk.Navisworks.Timeliner')
    import Autodesk.Navisworks.Api.Timeliner as TimelinerApi
    return TimelinerApi


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _log(level, message):
    try:
        from namo import session
        session.log(level, 'timeliner: ' + message)
    except Exception:
        pass


def get_timeliner(doc=None):
    """The document's DocumentTimeliner. Raises RuntimeError with a sentence when
    TimeLiner is not available (the plug-in is not loaded in this product)."""
    document = _doc(doc)
    api = _tl()
    errors = []
    for label, getter in (
            ('GetTimeliner', lambda: api.TimelinerDocumentExtensions.GetTimeliner(document)),
            ('TimelinerInstance', lambda: api.DocumentTimeliner.TimelinerInstance(document)),
            ('Document.Timeliner', lambda: document.Timeliner)):
        try:
            value = getter()
        except Exception as error:
            errors.append('%s: %s' % (label, error))
            continue
        if value is not None:
            if not hasattr(value, 'TasksRoot'):
                errors.append('%s returned %s' % (label, type(value).__name__))
                continue
            return value
    _log('warning', 'no TimeLiner part: ' + '; '.join(errors))
    raise RuntimeError('TimeLiner is not available in this Navisworks product.')


def task_types(doc=None):
    """The document's simulation task type names, in TimeLiner order."""
    try:
        timeliner = get_timeliner(doc)
        names = [str(item.DisplayName) for item in timeliner.SimulationTaskTypes]
        return names or list(DEFAULT_TYPES)
    except Exception:
        return list(DEFAULT_TYPES)


def _date(value):
    return dates.from_net(value) if value is not None else None


def _float(value):
    try:
        return None if value is None else float(value)
    except Exception:
        return None


def _attach_kind(task):
    try:
        selection = task.Selection
        if selection is None or selection.IsClear:
            return 'none', ''
        text = ''
        try:
            text = str(selection.DisplayString or '')
        except Exception:
            text = ''
        if selection.HasSelectionSources:
            return 'sets', text
        if selection.HasSearch:
            return 'search', text
        if selection.HasExplicitSelection:
            return 'items', text
        return 'other', text
    except Exception:
        return 'none', ''


def _row_of(task, key, parent_key, parent, depth):
    users = []
    for n in range(1, 11):
        try:
            users.append(str(getattr(task, 'User%d' % n) or ''))
        except Exception:
            users.append('')
    kind, text = _attach_kind(task)
    try:
        children = task.Children.Count
    except Exception:
        children = 0
    return {
        'key': key, 'parent_key': parent_key, 'depth': depth, 'outline': outline_number(key),
        'name': str(task.DisplayName or ''), 'id': str(task.DisplayId or ''),
        'start': _date(task.PlannedStartDate), 'end': _date(task.PlannedEndDate),
        'actual_start': _date(task.ActualStartDate), 'actual_end': _date(task.ActualEndDate),
        'type': str(task.SimulationTaskTypeName or ''), 'progress': _float(task.ProgressPercent),
        'enabled': bool(task.IsEnabled), 'user': users, 'attach_kind': kind,
        'attach_text': text, 'has_children': children > 0, 'children': children,
        'task': task, 'parent': parent,
    }


def snapshot(doc=None, timeliner=None):
    """Every task as a plain row, depth first in TimeLiner order (see _row_of for the
    keys; 'task' and 'parent' are live objects valid during this run only).

    Raises RuntimeError with a sentence, never anything else: no shipped pyNavis tool
    reads TimeLiner, so a member that behaves differently in the field must end as a
    toast in the calling tool (they all catch RuntimeError), with the cause in the log."""
    try:
        return _snapshot(doc, timeliner)
    except RuntimeError:
        raise
    except Exception as error:
        _log('error', 'reading the tasks failed: %s' % error)
        raise RuntimeError('TimeLiner could not be read (%s). The pyNavis log has the details.' % error)


def _snapshot(doc=None, timeliner=None):
    tl = timeliner or get_timeliner(doc)
    out = []
    stack = []
    roots = list(tl.Tasks)
    for index in range(len(roots) - 1, -1, -1):
        stack.append((roots[index], (index,), None, None, 0))
    while stack:
        task, key, parent_key, parent, depth = stack.pop()
        if not _is_task(task):
            continue
        out.append(_row_of(task, key, parent_key, parent, depth))
        children = list(task.Children)
        for index in range(len(children) - 1, -1, -1):
            stack.append((children[index], key + (index,), key, task, depth + 1))
    return out


def _is_task(item):
    try:
        api = _tl()
        return isinstance(item, api.TimelinerTask)
    except Exception:
        return hasattr(item, 'DisplayId')


def attach_paths(row, doc=None):
    """The selection set paths a 'sets' attachment points at ('Folder/Set'), one per
    line, for the template export; '' for any other kind."""
    if row.get('attach_kind') != 'sets':
        return ''
    document = _doc(doc)
    out = []
    try:
        for source in row['task'].Selection.SelectionSources:
            saved = document.SelectionSets.ResolveSelectionSource(source)
            if saved is None:
                continue
            names = []
            node = saved
            while node is not None and node.Parent is not None:
                names.append(str(node.DisplayName))
                node = node.Parent
            out.append('/'.join(reversed(names)))
    except Exception as error:
        _log('info', 'set paths unreadable: %s' % error)
    return '\n'.join(out)


def selected_items(task, doc=None):
    """The ModelItemCollection a task's attachment resolves to (sets and searches
    evaluated now), or None when nothing is attached."""
    try:
        selection = task.Selection
        if selection is None or selection.IsClear:
            return None
        return selection.GetSelectedItems(_doc(doc))
    except Exception as error:
        _log('warning', 'could not resolve the attachment of %s: %s' % (task.DisplayName, error))
        return None


def _set_text(task, attr, value):
    setattr(task, attr, '' if value is None else str(value))


def write_fields(task, fields, present=None):
    """Writes schedule fields (a parse_rows task dict) onto an editable task. present
    limits it to those fields (a merge writes only the cells that have values)."""
    wanted = set(present) if present is not None else None

    def want(field):
        return wanted is None or field in wanted
    if want('name') and fields.get('name'):
        task.DisplayName = str(fields['name'])
    if want('id') and fields.get('id') and not fields.get('auto_id'):
        task.DisplayId = str(fields['id'])
    for field, attr in (('start', 'PlannedStartDate'), ('end', 'PlannedEndDate'),
                        ('actual_start', 'ActualStartDate'), ('actual_end', 'ActualEndDate')):
        if want(field) and fields.get(field) is not None:
            setattr(task, attr, dates.to_net(fields[field]))
    try:
        if (want('start') or want('end')) and (fields.get('start') or fields.get('end')):
            task.IsPlannedEnabled = True
        if (want('actual_start') or want('actual_end')) and (fields.get('actual_start') or fields.get('actual_end')):
            task.IsActualEnabled = True
    except Exception as error:
        _log('info', 'planned/actual enable flags not set: %s' % error)
    if want('type') and fields.get('type'):
        task.SimulationTaskTypeName = str(fields['type'])
    if want('progress') and fields.get('progress') is not None:
        task.ProgressPercent = float(fields['progress'])
    for n, text in sorted((fields.get('user') or {}).items()):
        if want('user%d' % n):
            _set_text(task, 'User%d' % n, text)


def set_attachment(task, target, doc=None):
    """Points an editable task's attachment at target: ('sets', [SavedItem]),
    ('items', ModelItems) or ('clear', None)."""
    kind, value = target
    if kind == 'clear':
        task.Selection.Clear()
        return
    if kind == 'sets':
        from pynavis._api import Api
        document = _doc(doc)
        sources = Api.SelectionSourceCollection()
        for saved in value:
            sources.Add(document.SelectionSets.CreateSelectionSource(saved))
        task.Selection.CopyFrom(sources)
        return
    from namo import items as _items
    task.Selection.CopyFrom(_items.collection(value))


def new_task(fields, attach=None, doc=None):
    """A detached TimelinerTask carrying fields (and an attachment)."""
    api = _tl()
    task = api.TimelinerTask()
    write_fields(task, fields)
    try:
        task.IsEnabled = True
    except Exception:
        pass
    if attach is not None:
        set_attachment(task, attach, doc)
    return task


def _build_new(task_dict, attach_for, doc):
    node = new_task(task_dict, attach_for(task_dict), doc)
    for child in task_dict.get('children') or []:
        node.Children.Add(_build_new(child, attach_for, doc))
    return node


def _rebuild(live, key, edits, adds, attach_for, doc):
    node = live.CreateCopyWithoutChildren()
    if key in edits:
        task_dict = edits[key]
        write_fields(node, task_dict, task_dict.get('present'))
        target = attach_for(task_dict)
        if target is not None:
            set_attachment(node, target, doc)
    children = list(live.Children)
    for index, child in enumerate(children):
        if _is_task(child):
            node.Children.Add(_rebuild(child, key + (index,), edits, adds, attach_for, doc))
    for task_dict in adds.get(key, []):
        node.Children.Add(_build_new(task_dict, attach_for, doc))
    return node


def _commit_roots(timeliner, roots):
    """Replaces every task with roots in one call. Three routes, safest first; the first
    two leave the old tasks alone when they are refused."""
    from pynavis._api import Api
    from System.Collections.Generic import List
    batch = List[Api.SavedItem]()
    for root in roots:
        batch.Add(root)
    try:
        timeliner.TasksCopyFrom(batch)
        return 'TasksCopyFrom'
    except Exception as error:
        _log('warning', 'TasksCopyFrom(list) refused (%s); trying a copy of the task root' % error)
    try:
        # The shape Autodesk's own samples use: fill a copy of the root, hand over its children.
        holder = timeliner.TasksRoot.CreateCopy()
        holder.Children.Clear()
        for root in roots:
            holder.Children.Add(root)
        timeliner.TasksCopyFrom(holder.Children)
        return 'TasksCopyFrom(root copy)'
    except Exception as error:
        _log('warning', 'TasksCopyFrom(root copy) refused (%s); clearing and adding roots one by one' % error)
    timeliner.TasksClear()
    for root in roots:
        timeliner.TaskAddCopy(root)
    return 'TaskAddCopy'


def commit_import(plan, attach_for, doc=None, name='Import TimeLiner tasks'):
    """Writes an import plan as ONE undo step. attach_for(task_dict) returns the
    attachment target for a task (or None). Returns the commit route used. Raises
    RuntimeError with a sentence when TimeLiner refuses every route."""
    import time
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    timeliner = get_timeliner(document)
    started = time.time()
    with transaction(name, document):
        if plan['mode'] == 'replace':
            roots = [_build_new(task, attach_for, document) for task in plan['roots']]
        else:
            edits = dict((key, task) for key, task in plan['updates'])
            live_roots = [t for t in timeliner.Tasks if _is_task(t)]
            roots = [_rebuild(root, (index,), edits, plan['adds'], attach_for, document)
                     for index, root in enumerate(live_roots)]
            roots.extend(_build_new(task, attach_for, document) for task in plan['new_roots'])
        try:
            route = _commit_roots(timeliner, roots)
        except Exception as error:
            # Leaving the transaction on an error disposes it without committing.
            _log('error', 'import not committed: %s' % error)
            raise RuntimeError('TimeLiner refused the tasks (%s).' % error)
    _log('info', 'import committed with %s in %.2f s (%d roots)'
         % (route, time.time() - started, len(roots)))
    return route


def _live_at(timeliner, key):
    """(parent task or None for a root task, index among its siblings, the live task) at a
    snapshot key, read from the document now rather than from references kept in rows."""
    parent = None
    task = None
    children = timeliner.Tasks
    for depth, index in enumerate(key):
        task = children[int(index)]
        if depth < len(key) - 1:
            parent = task
            children = task.Children
    return parent, int(key[-1]), task


def edit_tasks(changes, doc=None, name='Edit TimeLiner tasks'):
    """Applies changes = [(row, fn)] where fn(values_task) edits a detached copy of the
    row's live task; written back with TaskEdit, all in ONE undo step. Returns how many
    tasks were written and the errors ([sentence]).

    Written so it holds whichever way TaskEdit treats children (nobody has seen it run):
    a task WITH children is copied with them, so an edit that replaced the children would
    put the same ones back; tasks are found again by their position before each edit and
    the deepest are written first, so an edit that re-creates a branch cannot strand a
    reference this loop still needs."""
    import time
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    timeliner = get_timeliner(document)
    written = 0
    errors = []
    started = time.time()
    ordered = sorted(changes, key=lambda change: -len(change[0]['key']))
    with transaction(name, document):
        for row, fn in ordered:
            try:
                parent, index, task = _live_at(timeliner, row['key'])
                values = task.CreateCopy() if task.Children.Count > 0 else task.CreateCopyWithoutChildren()
                fn(values)
                if parent is None:
                    timeliner.TaskEdit(index, values)
                else:
                    timeliner.TaskEdit(parent, index, values)
                written += 1
            except Exception as error:
                errors.append('%s: %s' % (row.get('name') or 'task', error))
    _log('info', 'TaskEdit x%d in %.2f s, %d errors' % (written, time.time() - started, len(errors)))
    if errors:
        _log('warning', 'TaskEdit errors, first: %s' % errors[0])
    return written, errors

# -*- coding: utf-8 -*-
"""Progress Painter: percent complete on model objects, rolled up into TimeLiner tasks,
and the model painted by progress.

Progress lives in a custom property tab 'Playground' > 'Progress' (0..100) written with
pynavis.props.set_custom. That call REPLACES a whole tab, so every write here merges:
each object's existing Playground tab is read first and objects that end up with the same
tab are written together. A task's progress is the mean over its attached objects, an
object without a value counting 0 (earned progress, not the mean of the ones reported).
The property writes and the TaskEdit calls share ONE transaction (one undo step).

Painting uses permanent colour overrides (namo.paint, one undo step), banded as
fourd_ui.PROGRESS_BANDS: 0 grey, 1 to 49 amber, 50 to 99 blue, 100 green.
"""

TAB = 'Playground'
PROPERTY = 'Progress'
HOLDER = 'progress-paint'


def to_percent(value):
    """0..100 from a stored value (number, '45', '45 %'), or None."""
    from namo import rules
    if value is None or isinstance(value, bool):
        return None
    number = rules.to_number(value)
    if number is None:
        return None
    return max(0.0, min(100.0, float(number)))


def _plain(value):
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)


def merged_tab(existing, updates):
    """The tab an object should carry: its existing tab (values made writable) plus
    updates."""
    tab = {}
    for key, value in sorted((existing or {}).items()):
        if value is not None:
            tab[str(key)] = _plain(value)
    for key, value in sorted(updates.items()):
        tab[str(key)] = value
    return tab


def group_writes(objects, existing_tabs, updates):
    """[(tab dict, [objects])]: objects sharing the same merged tab, written together."""
    groups = {}
    order = []
    for obj, existing in zip(objects, existing_tabs):
        tab = merged_tab(existing, updates)
        key = tuple(sorted((k, repr(v)) for k, v in tab.items()))
        if key not in groups:
            groups[key] = (tab, [])
            order.append(key)
        groups[key][1].append(obj)
    return [groups[key] for key in order]


def task_average(values):
    """Mean of percentages with None counted as 0; None for no objects."""
    if not values:
        return None
    return round(sum(v or 0.0 for v in values) / float(len(values)), 2)


def band_counts(percentages):
    from namo import fourd_ui
    counts = {}
    for value in percentages:
        band = fourd_ui.band_of(value)
        if band is not None:
            counts[band] = counts.get(band, 0) + 1
    return counts


# ---- API half ---------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def object_progress(obj):
    """The object's progress (its own tab, else its element ancestor's), or None."""
    from namo import items
    return to_percent(items.prop(obj, TAB, PROPERTY))


def set_progress(objects, percent, doc=None, report=None):
    """Writes Progress = percent on objects and updates the TimeLiner tasks whose
    attachments contain them, in ONE transaction. Returns {'objects', 'tasks',
    'errors', 'timeliner' (False when TimeLiner is unavailable)}."""
    from pynavis import props
    from pynavis.viewpoints import transaction
    from namo import items, timeliner
    document = _doc(doc)
    report = report or (lambda fraction, label='': True)
    objects = items.as_list(objects)
    report(0.05, 'Reading the Playground tab of %s objects' % '{:,}'.format(len(objects)))
    existing = []
    for obj in objects:
        try:
            existing.append(props.get_custom(obj, TAB))
        except Exception:
            existing.append(None)
    writes = group_writes(objects, existing, {PROPERTY: float(percent)})
    result = {'objects': 0, 'tasks': 0, 'errors': [], 'timeliner': True}
    plan = []
    try:
        rows = timeliner.snapshot(document)
    except RuntimeError:
        rows = []
        result['timeliner'] = False
    if rows:
        plan = affected_tasks(rows, objects, float(percent), document, report)
    # Last chance to cancel: nothing below asks, so a cancel never leaves half a write.
    report(0.6, 'Writing progress and updating TimeLiner')
    try:
        with transaction('Set progress', document):
            for tab, group in writes:
                written, errors = props.set_custom(group, TAB, tab, document)
                result['objects'] += written
                result['errors'].extend(errors)
            if plan:
                changes = [(row, _progress_setter(value)) for row, value in plan]
                written, errors = timeliner.edit_tasks(changes, document, 'Set progress')
                result['tasks'] = written
                result['errors'].extend(errors)
    finally:
        # A custom tab changed: Property Explorer's cached scan must not show the old
        # values (the namo README rule for every custom-property writer).
        try:
            from namo import propindex
            propindex.invalidate()
        except Exception:
            pass
    return result


def _progress_setter(value):
    def edit(task):
        task.ProgressPercent = float(value)
    return edit


def affected_tasks(rows, objects, percent, doc, report):
    """[(row, new percent)] for tasks whose attachments hold any of objects."""
    from namo import items, timeliner
    chosen = set(objects)
    out = []
    attached = [r for r in rows if (r.get('attach_kind') or 'none') != 'none']
    for index, row in enumerate(attached):
        report(0.1 + 0.45 * index / float(len(attached) or 1), 'Checking TimeLiner tasks')
        collection = timeliner.selected_items(row['task'], doc)
        if collection is None or not collection.Count:
            continue
        members = items.objects(collection)
        if not any(member in chosen for member in members):
            continue
        values = [percent if member in chosen else object_progress(member) for member in members]
        out.append((row, task_average(values)))
    return out


def paint_items(objects, doc=None, report=None):
    """Paints objects by their own progress. Returns (counts by band, painted objects)."""
    from namo import fourd_ui
    report = report or (lambda fraction, label='': True)
    groups = {}
    for index, obj in enumerate(objects):
        if index % 200 == 0:
            report(0.1 + 0.8 * index / float(len(objects) or 1), 'Reading progress')
        band = fourd_ui.band_of(object_progress(obj))
        if band is not None:
            groups.setdefault(band, []).append(obj)
    return _paint(groups, doc)


def paint_tasks(rows, doc=None, report=None):
    """Paints each task's attached items by the task's TimeLiner progress (tasks later in
    the list win where attachments overlap). Returns (counts by band, painted objects)."""
    from namo import fourd_ui, timeliner
    report = report or (lambda fraction, label='': True)
    band_of = {}
    attached = [r for r in rows if (r.get('attach_kind') or 'none') != 'none' and r.get('progress') is not None]
    for index, row in enumerate(attached):
        report(0.1 + 0.8 * index / float(len(attached) or 1), 'Reading TimeLiner tasks')
        collection = timeliner.selected_items(row['task'], doc)
        if collection is None:
            continue
        band = fourd_ui.band_of(row['progress'])
        for item in collection:
            band_of[item] = band
    groups = {}
    for item, band in band_of.items():
        groups.setdefault(band, []).append(item)
    return _paint(groups, doc)


def _paint(groups, doc):
    from namo import fourd_ui, paint, session
    plan = [(groups[band], fourd_ui.PROGRESS_BANDS[band][3], None) for band in sorted(groups)]
    painted = []
    for band in sorted(groups):
        painted.extend(groups[band])
    if plan:
        paint.apply(plan, doc, 'Paint progress')
    session.set(HOLDER, 'painted', painted)
    return dict((band, len(groups[band])) for band in groups), painted


def clear_paint(doc=None):
    """Removes the colours the last paint of this session added; how many objects, or
    None when nothing was painted this session."""
    from namo import paint, session
    painted = session.get(HOLDER, 'painted')
    if not painted:
        return None
    count = paint.reset(painted, doc, 'Clear progress paint')
    session.set(HOLDER, 'painted', [])
    return count

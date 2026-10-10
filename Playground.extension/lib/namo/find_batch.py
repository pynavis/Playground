# -*- coding: utf-8 -*-
"""Batch Sets: one search set per value of a property ('By Level/Level 1', ...).

Flow (script): pick a property from a sample (selection or model) -> collect its distinct
values (from the selection, or a full scan of every item carrying the property) -> choose
values, name and folder templates, an optional fixed extra condition, replace or skip
existing sets -> create every set in ONE undo step.

Each set is `property = value` (typed like the value: numbers as numbers, floats as a
tight >= / <= window, text ignoring case unless asked) AND the extra condition. The extra
condition is written as text and read by namo.rules.parse_cell ('Element > Category =
Ducts'); it must compile to one native condition list.
"""

from namo import find_query

DEFAULTS = {'category': '', 'property': '', 'name_template': '{value}',
            'folder_template': 'By {property}', 'extra': '', 'replace': False,
            'ignore_case': True, 'source': 'selection'}
NAME_TEMPLATES = ['{value}', '{property} {value}', '{property}: {value}', '{category} {value}']
SAMPLE_SIZE = 300


# ---- pure half ---------------------------------------------------------------------


def render(template, category, prop, value_text, count=None):
    """A set or folder name from a template with {value}, {property}, {category},
    {count}; tidied. Unknown tokens stay as written."""
    from namo import naming
    values = {'value': value_text, 'property': prop, 'category': category,
              'count': '' if count is None else '{:,}'.format(count)}
    text, _missing = naming.render(template, values)
    return naming.sanitize(text)


def render_folder(template, category, prop):
    """The folder path: each '/'-separated part of the template rendered on its own, so
    a '/' inside a property name cannot split the path."""
    from namo import find_sets
    parts = [render(part, category, prop, '') for part in str(template or '').split('/')]
    parts = [p for p in parts if p]
    return '/'.join(find_sets.escape(p) for p in parts)


def extra_conditions(text):
    """pynavis conditions for the optional extra rule ('' gives []). Raises ValueError
    with a sentence when it does not read or needs more than one native condition list."""
    from namo import rules
    text = (text or '').strip()
    if not text:
        return []
    cond = rules.parse_cell(text)
    plan = rules.native_plan([cond], numbers_as_text=True, max_groups=1)
    if plan is None or len(plan) != 1:
        raise ValueError('The extra condition must be a single native search condition, '
                         'for example Element > Category = Ducts.')
    out = []
    for category, prop, op, value, ignore_case in plan[0]:
        native = {'exists': 'has_property', 'missing': 'not_has_property'}.get(op, op)
        out.append(find_query._cond(category, prop, native, value, ignore_case))
    return out


def value_choices(tally):
    """multi-field options [(label, value_text)] from find_query.tally_values, blanks
    left out (a native equals cannot select 'no value')."""
    return [('%s  (%s)' % (text, '{:,}'.format(count)), text)
            for text, count, _raw in tally if text != find_query.NO_VALUE]


def plan(category, prop, chosen, tally, name_template, folder_template, extra, existing,
         replace=False, ignore_case=True):
    """The sets to write: [{'name', 'folder', 'query', 'value', 'count', 'action'
    ('create' | 'replace' | 'skip'), 'guid' (existing set, for replace)}].

    chosen: value texts ticked; tally: find_query.tally_values rows (text, count, raw);
    existing: find_sets.existing_index(); names repeated inside the batch get ' (2)'."""
    from namo import find_sets, naming
    raw_of = dict((text, raw) for text, _count, raw in tally)
    count_of = dict((text, count) for text, count, _raw in tally)
    folder = render_folder(folder_template, category, prop)
    out = []
    used = []
    for text in chosen:
        if text not in raw_of or text == find_query.NO_VALUE:
            continue
        raw = raw_of[text]
        kind = find_query.kind_of(raw) or 'text'
        conds = find_query.conditions(category, prop, 'equals', raw, kind=kind,
                                      ignore_case=ignore_case) + list(extra)
        name = render(name_template, category, prop, text, count_of.get(text)) or text
        name = naming.unique(name, used)
        used.append(name)
        guid = existing.get((folder.lower(), name.lower()))
        if guid is None:
            action = 'create'
        else:
            action = 'replace' if replace else 'skip'
        out.append({'name': name, 'folder': folder, 'query': find_query.query_dict([conds]),
                    'value': text, 'count': count_of.get(text, 0), 'action': action,
                    'guid': guid})
    return out


def summary(created, replaced, skipped, errors, folder):
    """(level, message, detail) for the toast."""
    from namo import find_sets
    where = find_sets.plain_folder(folder) or 'the root'
    total = created + replaced
    parts = []
    if replaced:
        parts.append('%d replaced' % replaced)
    if skipped:
        parts.append('%d already existed and %s skipped' % (skipped, 'was' if skipped == 1 else 'were'))
    if errors:
        parts.append('%d failed: %s' % (len(errors), errors[0]))
    detail = '; '.join(parts) or None
    if not total:
        if errors:
            return ('error', 'No search sets were created', detail)
        return ('info', 'No new search sets', detail or 'Every chosen value already has a set.')
    noun = 'search set' if total == 1 else 'search sets'
    if created and not replaced:
        message = "Created %d %s in '%s'" % (created, noun, where)
    elif replaced and not created:
        message = "Replaced %d %s in '%s'" % (replaced, noun, where)
    else:
        message = "Wrote %d %s in '%s'" % (total, noun, where)
    return ('warning' if errors else 'success', message, detail)


# ---- API half -------------------------------------------------------------------------


def _doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def carriers(category, prop, scope=None, doc=None):
    """Every item carrying the property (one native search, pruned below matches)."""
    from pynavis import sets
    query = sets.query().prop(category, prop).exists()
    return sets.run(query, _doc(doc), prune=True, scope=scope)


def collect(items_, category, prop, report=None):
    """Raw values of the property on items (report(fraction, label) every 200; raises to
    cancel)."""
    values = []
    data = list(items_)
    total = len(data)
    for index, item in enumerate(data):
        exists, value = find_query.read(item, category, prop)
        if exists:
            values.append(value)
        if report is not None and index % 200 == 0:
            report(float(index) / max(1, total), 'Reading %s of %s items' % (
                '{:,}'.format(index), '{:,}'.format(total)))
    return values


def apply(rows, doc=None, report=None):
    """Writes the plan in ONE undo step. Returns (created, replaced, skipped, errors,
    stopped): when report raises a Cancelled (the user pressed Cancel) the loop stops and
    what was already written is kept and committed, so the toast can say what exists."""
    from pynavis import viewpoints
    from namo import find_sets
    document = _doc(doc)
    created = replaced = skipped = 0
    errors = []
    stopped = False
    with viewpoints.transaction('Batch Sets', document):
        for index, row in enumerate(rows):
            if report is not None:
                try:
                    report(float(index) / max(1, len(rows)), 'Writing %d of %d sets' % (index + 1, len(rows)))
                except Exception as error:
                    if type(error).__name__ == 'Cancelled':
                        stopped = True
                        break
                    raise
            try:
                if row['action'] == 'skip':
                    skipped += 1
                elif row['action'] == 'replace':
                    item = find_sets.resolve_guid(row['guid'], document)
                    if item is None:
                        find_sets.create_set(row['name'], row['query'], row['folder'] or None,
                                             doc=document)
                        created += 1
                    else:
                        find_sets.update_set(item, row['query'], document)
                        replaced += 1
                else:
                    find_sets.create_set(row['name'], row['query'], row['folder'] or None,
                                         doc=document)
                    created += 1
            except Exception as error:
                errors.append("'%s': %s" % (row['name'], error))
    return created, replaced, skipped, errors, stopped

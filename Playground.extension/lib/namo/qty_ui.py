# -*- coding: utf-8 -*-
"""Forms and windows of the Quantities panel (Quick Takeoff, Zone Takeoff, Takeoff
Templates, COG Calculator), built on namo.ui.

Result windows are modeless (the model stays usable): their actions run after the
script returned, so everything they need is captured in closures during the run and
every handler goes through ui.safe (table_window does that).
"""

import os

QUICK_TOOL = 'quick_takeoff'
ZONE_TOOL = 'zone_takeoff'
TOOL_LABELS = {QUICK_TOOL: 'Quick Takeoff', ZONE_TOOL: 'Zone Takeoff'}
NONE = '(none)'
UNIT_CHOICES = [('As in Playground settings', 'auto'), ('Millimetres', 'mm'), ('Metres', 'm'), ('Feet', 'ft'),
                ('Inches', 'in')]
MEASURE_OPTIONS = [('Count', 'count'), ('Length', 'length'), ('Area', 'area'), ('Volume', 'volume'),
                   ('Weight', 'weight'), ('Surface area (from geometry)', 'surface')]


def _spec_key(spec):
    if not spec:
        return NONE
    if spec.get('special'):
        return spec['special']
    return '%s > %s' % (spec.get('category', ''), spec.get('property', ''))


def group_choices(options):
    """('Label', key) choices from takeoff.property_options and a key -> spec map."""
    choices = []
    specs = {}
    for label, spec in options:
        key = _spec_key(spec)
        if key not in specs:
            specs[key] = spec
            choices.append((label, key))
    return choices, specs


def quick_fields(values, has_selection, choices, zone=False):
    """The form fields shared by Quick and Zone Takeoff."""
    from namo import fourd_common
    keys = [k for _l, k in choices]
    groups = values.get('group_by') or [{'special': '@category'}]
    first = _spec_key(groups[0]) if groups else '@category'
    second = _spec_key(groups[1]) if len(groups) > 1 else NONE
    fields = [
        {'kind': 'radio', 'key': 'scope', 'label': 'Measure', 'inline': True,
         'options': fourd_common.scope_options(has_selection),
         'default': fourd_common.default_scope(values.get('scope'), has_selection), 'fallback': None},
        {'kind': 'choice', 'key': 'group1', 'label': 'Group by', 'options': choices,
         'default': first if first in keys else '@category'},
    ]
    if not zone:
        fields.append({'kind': 'choice', 'key': 'group2', 'label': 'Then by (optional)',
                       'options': [('(none)', NONE)] + choices, 'default': second if second in keys else NONE})
    fields += [
        {'kind': 'multi', 'key': 'measures', 'label': 'Quantities', 'options': MEASURE_OPTIONS,
         'default': values.get('measures') or ['count', 'length', 'area', 'volume']},
        {'kind': 'check', 'key': 'geometric', 'label': 'Measure the geometry where volume or length is missing (slower)',
         'default': bool(values.get('geometric'))},
        {'kind': 'choice', 'key': 'units', 'label': 'Units', 'options': UNIT_CHOICES,
         'default': values.get('units') or 'auto', 'fallback': 'auto'},
    ]
    return fields


def zone_fields(values):
    from namo import takeoff
    zones = values.get('zones') or {'mode': 'levels'}
    return [
        {'kind': 'radio', 'key': 'zone_mode', 'label': 'Zones',
         'options': [(label, value) for value, label in takeoff.ZONE_MODES],
         'default': zones.get('mode', 'levels'), 'fallback': 'levels'},
        {'kind': 'text', 'key': 'zone_set', 'label': 'Zone objects from the set (blank: the current selection)',
         'default': zones.get('set', ''), 'placeholder': 'Folder/Set name', 'enabled_if': ('zone_mode', 'objects')},
        {'kind': 'length', 'key': 'tile', 'label': 'Tile size', 'default': zones.get('spacing') or None,
         'enabled_if': ('zone_mode', 'tiles')},
    ]


def config_from(answer, specs, zone=False):
    config = {'scope': answer['scope'], 'measures': answer['measures'] or ['count'],
              'geometric': bool(answer['geometric']), 'units': answer['units'],
              'group_by': [specs.get(answer['group1']) or {'special': '@category'}]}
    if not zone and answer.get('group2') and answer['group2'] != NONE:
        config['group_by'].append(specs[answer['group2']])
    if zone:
        config['zones'] = {'mode': answer['zone_mode'], 'set': (answer.get('zone_set') or '').strip(),
                           'spacing': answer.get('tile')}
        config['pivot_measure'] = answer.get('pivot') or 'count'
    return config


def validate_zone(answer):
    if answer.get('zone_mode') == 'tiles' and not answer.get('tile'):
        return {'tile': 'Give the tile size, like 8 m or 25 ft.'}
    if (answer.get('zone_mode') == 'objects' and not (answer.get('zone_set') or '').strip()
            and answer.get('scope') == 'selection'):
        # The zone objects come from the selection and are never counted themselves, so
        # measuring the same selection would find nothing.
        return {'scope': 'The selection holds the zone objects. Measure the visible items or the '
                         'whole model, or name a zone set.'}
    if not answer.get('measures'):
        return {'measures': 'Pick at least one quantity.'}
    return None


def validate_quick(answer):
    if not answer.get('measures'):
        return {'measures': 'Pick at least one quantity.'}
    return None


# ---- result window ---------------------------------------------------------------------------


def result_rows(result, zone=False):
    from namo import takeoff
    if zone:
        records = [dict(r, groups=[r.get('zone') or takeoff.NO_ZONE, r['groups'][0]])
                   for r in result['data']['records']]
        rows = takeoff.aggregate(records, 2, result['measures'])
        titles = ['Zone', result['group_titles'][0]]
    else:
        records = result['data']['records']
        rows = result['rows']
        titles = result['group_titles']
    return records, rows, titles


def build_results(title, result, export, select, save_template, zone=False):
    """The results window (unshown): a table of groups with subtotals and totals, and
    Export to Excel / Select objects / Save as template."""
    from namo import takeoff, ui
    records, rows, titles = result_rows(result, zone)
    table = takeoff.table_rows(rows, result['measures'], result['unit_set'], titles)
    headers = takeoff.table_headers(result['measures'], result['unit_set'], titles)
    actions = [{'label': 'Export to Excel', 'fn': lambda selected: export(), 'needs_selection': False,
                'primary': True},
               {'label': 'Select objects', 'fn': lambda selected: select(records, rows, selected),
                'needs_selection': True},
               {'label': 'Save as template', 'fn': lambda selected: save_template(), 'needs_selection': False}]
    return ui.build_table(title, headers, table, actions=actions, status=result['status'], width=900)


def show_results(title, key, result, export, select, save_template, zone=False):
    from namo import ui
    ui.Modeless.close(key)
    win = build_results(title, result, export, select, save_template, zone)
    return ui.Modeless(key, title, None, window_factory=lambda: win).show()


def select_rows(records, rows, selected, doc):
    """Selects the objects behind the chosen table rows; returns how many."""
    from namo import items
    chosen = []
    seen = set()
    for index in selected:
        for member in rows[index]['members']:
            if member not in seen:
                seen.add(member)
                chosen.append(records[member]['item'])
    return items.select(chosen, doc=doc)


# ---- templates window ----------------------------------------------------------------------------


def template_rows(entries):
    """entries: [(tool, name, info, config)] -> ui rows (value = (tool, name))."""
    from namo import takeoff
    rows = []
    for tool, name, info, config in entries:
        rows.append({'cells': [name, TOOL_LABELS.get(tool, tool), takeoff.describe_config(config),
                               (info or {}).get('updated', '')[:16].replace('T', ' '), (info or {}).get('user', '')],
                     'value': (tool, name)})
    return rows


def collect_templates():
    from namo import templates
    entries = []
    for tool in (QUICK_TOOL, ZONE_TOOL):
        store = templates.Templates(tool)
        for name in store.names():
            config = store.get(name)
            if config is not None:
                entries.append((tool, name, store.info(name), config))
    return entries


TEMPLATE_HEADERS = ['Name', 'Tool', 'What it measures', 'Updated', 'By']


def build_templates(entries, actions):
    from namo import ui
    if entries:
        status = '%s. Run one, or rename, duplicate, delete, export and import them.' % (
            '{:,} templates'.format(len(entries)) if len(entries) != 1 else '1 template')
    else:
        status = 'No templates yet. Save one from a Quick or Zone Takeoff result, or import a file.'
    return ui.build_table('Takeoff templates', TEMPLATE_HEADERS, template_rows(entries), actions=actions,
                          status=status, width=900)


def export_paths(path, tools):
    """{tool: file} for an export: the chosen path for one tool, '<stem> - <Tool>.json' each for two."""
    if len(tools) <= 1:
        return dict((tool, path) for tool in tools)
    stem, ext = os.path.splitext(path)
    return dict((tool, '%s - %s%s' % (stem, TOOL_LABELS[tool], ext or '.json')) for tool in tools)

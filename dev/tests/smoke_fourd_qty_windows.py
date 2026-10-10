# -*- coding: utf-8 -*-
"""4D and Quantities windows under IronPython + WPF: built with sample data, driven
through their state objects, never shown."""
import _compat

_compat.require_ironpython()

from namo import cog, fourd_ui, qty_ui, takeoff, timeliner, ui  # noqa: E402


def test_import_review_window():
    parsed = timeliner.parse_rows([['Task ID', 'Parent ID', 'Name', 'Start', 'End'],
                                   ['1', '', 'Good', '2026-10-01', '2026-10-02'],
                                   ['2', '9', 'Orphan', '2026-10-01', '2026-10-02'],
                                   ['3', '', '', '2026-10-01', '2026-10-02']])
    plan = timeliner.plan_import(parsed, [], 'merge')
    rows = fourd_ui.problem_rows(parsed['problems'])
    win, outcome = fourd_ui.build_review('TimeLiner from Excel', ['Row', 'Level', 'Column', 'Problem'], rows,
                                         fourd_ui.import_summary(plan), 'Import 1 task')
    state = win.Tag
    assert state.table.total() == len(parsed['problems']) == 2
    action = state.buttons[0]
    assert action.IsEnabled                     # needs no selection
    assert not outcome['go']
    action.RaiseEvent(_click())
    assert outcome['go']
    assert 'Import 1 task' in fourd_ui.import_summary(plan) or 'Import' in fourd_ui.import_summary(plan)


def _click():
    from System.Windows import RoutedEventArgs
    from System.Windows.Controls.Primitives import ButtonBase
    return RoutedEventArgs(ButtonBase.ClickEvent)


def test_import_summary_texts():
    plan = {'mode': 'merge', 'created': 3, 'updated': 2, 'skipped': 1, 'kept_in_place': 1, 'ambiguous': ['A']}
    text = fourd_ui.import_summary(plan, misses=2)
    assert text.startswith('Import 5 tasks: 3 new, 2 updated.')
    assert '1 row with errors skipped' in text and '2 attach entries found nothing' in text
    assert fourd_ui.import_summary({'mode': 'replace', 'created': 4, 'updated': 0, 'skipped': 0}) == \
        'Replace every TimeLiner task with 4 tasks.'
    assert [fourd_ui.band_of(v) for v in (None, 0, 0.5, 49.9, 50, 99.99, 100, 140)] == [None, 0, 1, 1, 2, 2, 3, 3]


def test_progress_legend():
    cleared = []
    win = fourd_ui.build_legend({0: 12, 1: 3, 3: 1250}, 'Colours from each object\'s progress.',
                                on_clear=lambda: cleared.append(True))
    assert win.Title == 'Progress legend'
    assert fourd_ui.legend_rows({3: 7})[3] == ('Complete (100%)', '59A14F', 7)


def _result(zone=False):
    records = [
        {'name': 'W1', 'groups': ['Walls', 'L1'], 'zone': 'Level 1', 'measures': {'volume': 2.0, 'length': 4.0},
         'sources': {'volume': 'property', 'length': 'property'}, 'item': 'w1'},
        {'name': 'W2', 'groups': ['Walls', 'L2'], 'zone': 'Level 2', 'measures': {'volume': 1.0, 'length': None},
         'sources': {'volume': 'geometric'}, 'item': 'w2'},
        {'name': 'D1', 'groups': ['Ducts', 'L1'], 'zone': 'Level 1', 'measures': {'volume': None, 'length': 9.0},
         'sources': {'length': 'bbox'}, 'item': 'd1'},
    ]
    measures = ['count', 'volume', 'length']
    unit_set = takeoff.display_units('m', 'Meters')
    data = {'records': records, 'geometric': 1, 'geometry_skipped': 0, 'sampled': False, 'pairs': {},
            'scope': 'model', 'measures': measures, 'groupers': [{'special': '@category'}, {'special': '@model'}]}
    rows = takeoff.aggregate(records, 2, measures)
    return {'data': data, 'rows': rows, 'unit_set': unit_set, 'measures': measures,
            'group_titles': ['Category', 'Model file'], 'notes': [], 'status': takeoff.status_text(data, 3)}


def test_takeoff_results_window_and_select():
    calls = []
    result = _result()
    win = qty_ui.build_results('Quick takeoff', result, lambda: calls.append('export'),
                               lambda records, rows, selected: calls.append(('select', selected)),
                               lambda: calls.append('save'))
    state = win.Tag
    assert state.table.total() == len(result['rows'])
    export, select, save = state.buttons
    assert export.IsEnabled and not select.IsEnabled and save.IsEnabled
    state.table.select_values([0])
    assert select.IsEnabled
    select.RaiseEvent(_click())
    export.RaiseEvent(_click())
    assert calls == [('select', [0]), 'export']
    zone_win = qty_ui.build_results('Zone takeoff', result, lambda: None, lambda *a: None, lambda: None, zone=True)
    records, rows, titles = qty_ui.result_rows(result, zone=True)
    assert titles == ['Zone', 'Category'] and zone_win.Tag.table.total() == len(rows)
    chosen = []

    class _Items(object):
        pass
    import namo.items as items_module
    original = items_module.select
    items_module.select = lambda objs, zoom=False, doc=None: chosen.extend(objs) or len(objs)
    try:
        count = qty_ui.select_rows(result['data']['records'], result['rows'], [1], None)
    finally:
        items_module.select = original
    assert count == len(result['rows'][1]['members'])


def test_takeoff_forms_build():
    choices, specs = qty_ui.group_choices([('Category', {'special': '@category'}),
                                           ('Model file', {'special': '@model'}),
                                           ('Element > Level', {'category': 'Element', 'property': 'Level'})])
    values = takeoff.default_zone_config()
    fields = qty_ui.zone_fields(values) + qty_ui.quick_fields(values, True, choices, zone=True)
    win = ui.build_form('Zone Takeoff', fields, units='Meters', validate=qty_ui.validate_zone)
    state = win.Tag
    state.set_raw('zone_mode', 'tiles')
    values_, errors = state.collect()
    assert 'tile' in errors or state.accept() is False
    state.set_raw('tile', '8m')
    state.set_raw('group1', 'Element > Level')
    assert state.accept()
    config = qty_ui.config_from(state.result, specs, zone=True)
    assert config['zones'] == {'mode': 'tiles', 'set': '', 'spacing': 8.0}
    assert config['group_by'] == [{'category': 'Element', 'property': 'Level'}]
    quick = ui.build_form('Quick Takeoff', qty_ui.quick_fields(takeoff.default_quick_config(), False, choices),
                          units='Feet')
    quick.Tag.set_raw('group2', '@model')
    assert quick.Tag.accept()
    config = qty_ui.config_from(quick.Tag.result, specs)
    assert config['scope'] == 'model' and len(config['group_by']) == 2


def test_templates_window():
    entries = [('quick_takeoff', 'Walls by level', {'updated': '2026-10-05T10:00:00', 'user': 'amol'},
                takeoff.default_quick_config()),
               ('zone_takeoff', 'Ducts by zone', None, takeoff.default_zone_config())]
    ran = []
    win = qty_ui.build_templates(entries, [{'label': 'Run', 'fn': lambda s: ran.append(s), 'primary': True}])
    assert win.Tag.table.total() == 2
    win.Tag.table.select_values([('zone_takeoff', 'Ducts by zone')])
    win.Tag.buttons[0].RaiseEvent(_click())
    assert ran == [[('zone_takeoff', 'Ducts by zone')]]
    empty = qty_ui.build_templates([], [])
    assert 'No templates yet' in empty.Tag.status_block.Text
    assert qty_ui.export_paths('C:\\t\\x.json', ['quick_takeoff']) == {'quick_takeoff': 'C:\\t\\x.json'}
    both = qty_ui.export_paths('C:\\t\\x.json', ['quick_takeoff', 'zone_takeoff'])
    assert both['zone_takeoff'] == 'C:\\t\\x - Zone Takeoff.json'


def test_cog_table():
    results = [{'name': 'Beam', 'mass_kg': 785.0, 'volume_m3': 0.1, 'centroid': (1.0, 2.0, 3.0),
                'method_label': cog.METHODS['mesh'], 'density': 7850.0, 'density_from': 'material'},
               {'name': 'Slab', 'mass_kg': None, 'volume_m3': None, 'centroid': None,
                'method_label': cog.METHODS['none'], 'density': None}]
    win = ui.build_table('Centre of gravity', ['Object', 'Mass', 'Volume', 'Density', 'X', 'Y', 'Z', 'Method'],
                         cog.result_rows(results, False, 'Meters'))
    assert win.Tag.table.total() == 2

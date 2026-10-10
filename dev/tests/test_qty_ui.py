# -*- coding: utf-8 -*-
"""namo.qty_ui pure helpers and the takeoff configuration texts."""
from namo import qty_ui, takeoff


def test_group_choices_and_config():
    options = [('Category', {'special': '@category'}), ('Model file', {'special': '@model'}),
               ('Element > Level', {'category': 'Element', 'property': 'Level'}),
               ('Element > Level', {'category': 'Element', 'property': 'Level'})]
    choices, specs = qty_ui.group_choices(options)
    assert choices == [('Category', '@category'), ('Model file', '@model'), ('Element > Level', 'Element > Level')]
    answer = {'scope': 'visible', 'measures': ['count', 'volume'], 'geometric': 1, 'units': 'mm',
              'group1': 'Element > Level', 'group2': '@model'}
    config = qty_ui.config_from(answer, specs)
    assert config == {'scope': 'visible', 'measures': ['count', 'volume'], 'geometric': True, 'units': 'mm',
                      'group_by': [{'category': 'Element', 'property': 'Level'}, {'special': '@model'}]}
    answer.update({'group2': qty_ui.NONE, 'zone_mode': 'objects', 'zone_set': ' Rooms/All ', 'tile': None,
                   'pivot': 'volume'})
    zone = qty_ui.config_from(answer, specs, zone=True)
    assert zone['zones'] == {'mode': 'objects', 'set': 'Rooms/All', 'spacing': None}
    assert zone['pivot_measure'] == 'volume' and len(zone['group_by']) == 1
    assert qty_ui.validate_zone({'zone_mode': 'tiles', 'tile': None, 'measures': ['count']})['tile']
    assert qty_ui.validate_zone({'zone_mode': 'levels', 'measures': []})['measures']
    assert qty_ui.validate_quick({'measures': ['count']}) is None


def test_zone_objects_from_selection_need_another_scope():
    # Zone objects taken from the selection are never measured themselves, so measuring
    # only that same selection would always find nothing.
    base = {'zone_mode': 'objects', 'zone_set': '', 'measures': ['count']}
    assert qty_ui.validate_zone(dict(base, scope='selection'))['scope']
    assert qty_ui.validate_zone(dict(base, scope='model')) is None
    assert qty_ui.validate_zone(dict(base, scope='selection', zone_set='Rooms/All')) is None


def test_fields_defaults():
    choices, _specs = qty_ui.group_choices([('Category', {'special': '@category'})])
    fields = qty_ui.quick_fields({'group_by': [{'special': '@gone'}]}, False, choices)
    by_key = dict((f['key'], f) for f in fields)
    assert by_key['group1']['default'] == '@category' and by_key['group2']['default'] == qty_ui.NONE
    assert by_key['scope']['default'] == 'model'
    zone = qty_ui.zone_fields({'zones': {'mode': 'tiles', 'spacing': 8.0}})
    assert zone[0]['default'] == 'tiles' and zone[0]['options'][0][1] == 'levels'
    assert zone[2]['default'] == 8.0


def test_template_rows_and_describe():
    rows = qty_ui.template_rows([('zone_takeoff', 'By level', {'updated': '2026-10-05T10:20:30', 'user': 'ana'},
                                  takeoff.default_zone_config())])
    assert rows[0]['value'] == ('zone_takeoff', 'By level')
    assert rows[0]['cells'][:2] == ['By level', 'Zone Takeoff'] and rows[0]['cells'][3] == '2026-10-05 10:20'
    text = takeoff.describe_config(takeoff.default_zone_config())
    assert text == 'Whole model by Category: count, length, area, volume; zones: grid levels'
    config = dict(takeoff.default_quick_config(), scope='selection',
                  group_by=[{'category': 'Element', 'property': 'Level'}, {'special': '@model'}])
    assert takeoff.describe_config(config).startswith('Current selection by Element > Level and Model file')


def test_status_and_notes():
    data = {'records': [1] * 1200, 'geometric': 8, 'geometry_skipped': 3, 'sampled': True, 'scope': 'visible',
            'measures': ['count', 'volume', 'length']}
    assert takeoff.status_text(data, 12) == ('1,200 objects in 12 groups, 8 objects measured from geometry, '
                                             '3 past the geometry budget, sampled.')
    notes = dict(takeoff.notes_for(data, {'geometric': True}, takeoff.display_units('m', 'Meters')))
    assert notes['Scope'] == 'Visible items' and 'Volume m³' in notes['Units']
    assert 'Geometric values' in notes and 'Geometry budget' in notes and 'Sampled' in notes

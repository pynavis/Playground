# -*- coding: utf-8 -*-
"""namo.issue_templates: defaults, normalising, validation, lookup, the team store, form
fields; namo.issue_stamps planning."""
import datetime

import _compat

from namo import issue_stamps, issue_templates, paths

NOW = datetime.datetime(2026, 10, 5, 14, 30, 0)


def isolated(fn):
    def wrapper():
        folder = _compat.tmpdir('g8-templates-' + fn.__name__)
        previous = paths.redirect(folder)
        try:
            return fn(folder)
        finally:
            paths.redirect(previous)
    wrapper.__name__ = fn.__name__
    return wrapper


def test_defaults_ship_the_six_types():
    types = [t['type'] for t in issue_templates.copy_defaults()]
    assert types == ['RFI', 'Hold', 'Verify', 'Safety', 'Clash', 'Design change']
    prefixes = [t['prefix'] for t in issue_templates.copy_defaults()]
    assert len(set(prefixes)) == 6 and all(p.endswith('-') for p in prefixes)
    assert issue_templates.default('safety')['priority'] == 'Critical'
    assert issue_templates.default('nope') is None


def test_normalise_and_validate():
    t = issue_templates.normalise({'type': ' Fire stopping ', 'prefix': '', 'priority': 'major',
                                   'due_days': '5', 'labels': 'Fire, Walls'})
    assert t['type'] == 'Fire stopping' and t['prefix'] == 'FIRE-'
    assert t['priority'] == 'High' and t['due_days'] == 5 and t['labels'] == ['Fire', 'Walls']
    assert t['stamp_label'] == 'Fire stopping' and t['title_pattern'] == '{type} {n:000}'
    assert issue_templates.normalise({'due_days': 'x'})['due_days'] is None
    assert issue_templates.normalise({'due_days': -3})['due_days'] == 0
    others = issue_templates.copy_defaults()
    assert issue_templates.validate({'type': 'rfi'}, others)[0] == 'There is already a template called RFI.'
    clash = issue_templates.validate({'type': 'Requests', 'prefix': 'RFI'}, others)
    assert 'already uses the prefix RFI-' in clash[0]
    assert issue_templates.validate({'type': ''}, [])[0].startswith('Give the template a type')
    bad = issue_templates.validate({'type': 'X', 'prefix': 'X', 'title_pattern': '{type} {nope}'}, [])
    assert bad == ['The title pattern uses unknown tokens: nope.']
    assert issue_templates.validate({'type': 'X', 'prefix': 'X', 'title_pattern': '{clash}: {a} vs {b}'}, []) == []


def test_find_by_type_or_stamp_label():
    templates = [{'type': 'Request for information', 'prefix': 'RFI', 'stamp_label': 'RFI'}]
    assert issue_templates.find(templates, 'rfi')['type'] == 'Request for information'
    assert issue_templates.find(templates, 'REQUEST FOR INFORMATION')['prefix'] == 'RFI-'
    assert issue_templates.find(templates, '') is None


def test_rows_and_form_fields():
    rows = issue_templates.rows(issue_templates.copy_defaults()[:2])
    assert rows[0] == {'value': 'RFI', 'cells': ['RFI', 'RFI-', 'Normal', 'From model', '7 days',
                                                  '{type} {n:000}']}
    fields = issue_templates.form_fields({'type': 'RFI', 'trade': 'Custom'}, ['Mechanical'])
    keys = [f['key'] for f in fields]
    assert keys == list(issue_templates.FIELDS)
    trade = [f for f in fields if f['key'] == 'trade'][0]
    assert ('Custom', 'Custom') in trade['options'] and trade['options'][0][1] == ''


@isolated
def test_store_uses_defaults_until_the_first_edit(folder):
    assert issue_templates.saved() == []
    assert [t['type'] for t in issue_templates.load()][0] == 'RFI'
    assert issue_templates.resolve('hold')['prefix'] == 'HOLD-'
    issue_templates.save({'type': 'Fire stopping', 'prefix': 'FS', 'priority': 'High'})
    names = [t['type'] for t in issue_templates.saved()]
    assert 'Fire stopping' in names and 'RFI' in names and len(names) == 7
    issue_templates.delete('Verify')
    assert issue_templates.resolve('Verify') is not None             # falls back to the shipped default
    assert 'Verify' not in [t['type'] for t in issue_templates.load()]
    issue_templates.save({'type': 'Fire stop', 'prefix': 'FS'}, old_type='Fire stopping')
    names = [t['type'] for t in issue_templates.load()]
    assert 'Fire stop' in names and 'Fire stopping' not in names
    target = folder + '\\export.json'
    assert issue_templates.export(target, ['RFI', 'Hold']) == 2


def test_stamp_plan_fields():
    template = issue_templates.default('RFI')
    element = {'name': 'Duct 600x400', 'model': 'MEP.nwc', 'element_id': '123'}
    location = {'point': [1, 2, 3], 'units': 'Feet', 'level': 'Level 2', 'grid': 'C-4'}
    fields, prefix, pattern, values = issue_stamps.plan_fields(template, element, 'Mechanical',
                                                               location, NOW)
    assert prefix == 'RFI-' and pattern == '{type} {n:000}'
    assert fields['trade'] == 'Mechanical' and fields['elements'] == [element]
    assert fields['location'] == location and fields['due'] == '2026-10-12'
    assert fields['source'] == {'kind': 'stamp', 'ref': 'RFI'}
    assert values == {'element': 'Duct 600x400', 'model': 'MEP.nwc', 'level': 'Level 2', 'grid': 'C-4'}
    fixed = dict(template, trade='Structure')
    fields, _p, _pat, _v = issue_stamps.plan_fields(fixed, None, 'Mechanical', None, NOW)
    assert fields['trade'] == 'Structure' and 'elements' not in fields
    fields, _p, _pat, _v = issue_stamps.plan_fields(template, None, 'Unassigned', None, NOW)
    assert fields['trade'] == ''
    assert issue_stamps.created_message({'id': 'RFI-012', 'number': 12}, template) == 'RFI 012 created'
    assert issue_stamps.created_message({'id': 'X'}, template) == 'X created'
    # The toast detail names the id, the place only when the model has grids, and the object.
    placed = {'id': 'RFI-012', 'location': {'point': [1, 2, 3], 'level': 'L2', 'grid': 'C-4'}}
    assert issue_stamps.created_detail(placed, {'name': 'Duct'}, 'Level L2, grid C-4') ==         'RFI-012, Level L2, grid C-4, on Duct'
    bare = {'id': 'RFI-013', 'location': {'point': [1, 2, 3], 'level': '', 'grid': ''}}
    assert issue_stamps.created_detail(bare, None, 'Pin set (no grid nearby)', 'no view') ==         'RFI-013, no object under the point. No snapshot: no view'

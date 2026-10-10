# -*- coding: utf-8 -*-
"""namo.look_status: config, matching, paint plans, tab merges, the settings form,
and the API half through the fake Navisworks layer."""
import sys
import types

import _compat

from namo import colorize, look_status

import test_colorize
import test_items as nav


def test_normalize_config_defaults_and_cleanup():
    cfg = look_status.normalize_config(None)
    assert cfg['category'] == 'Playground' and cfg['property'] == 'Status'
    assert [s[0] for s in cfg['statuses']][:2] == ['Installed', 'In progress']
    assert cfg['statuses'][-1] == ['Not started', None]
    cfg = look_status.normalize_config({'category': ' ', 'statuses': [['A', '#abc'], ['a', '000000'],
                                                                      ['', '111111'], ['B', 'nope'], 'x']})
    assert cfg['category'] == 'Playground'
    assert cfg['statuses'] == [['A', 'AABBCC'], ['B', None]]
    assert look_status.is_default_source(look_status.normalize_config({}))


def test_match_status_ignores_case_and_spaces():
    statuses = look_status.normalize_config({})['statuses']
    assert look_status.match_status('  in   PROGRESS ', statuses) == 'In progress'
    assert look_status.match_status('Done', statuses) is None
    assert look_status.match_status(None, statuses) is None


def test_plan_paint_groups_reset_counts_unknown():
    statuses = look_status.normalize_config({})['statuses']
    groups = [('installed', ['a', 'b']), ('Installed', ['c']), ('Not started', ['d']),
              ('Fabricated', ['e']), (colorize.NO_VALUE, ['f'])]
    plan = look_status.plan_paint(groups, statuses)
    assert plan['groups'] == [(['a', 'b', 'c'], '59A14F', None)]
    assert plan['reset'] == ['d']
    assert plan['counts'][0] == ('Installed', 3) and ('Not started', 1) in plan['counts']
    assert plan['unknown'] == [('Fabricated', 1)]


def test_status_scheme_and_detail():
    cfg = look_status.normalize_config({})
    scheme = look_status.status_scheme(cfg, [('Installed', 3), ('Issue', 1)], [('Fabricated', 2)])
    assert scheme['entries'][0] == {'value': 'Installed', 'hex': '59A14F', 'count': 3}
    assert scheme['kinds'][-1] == 'other' and scheme['entries'][-1]['hex'] is None
    assert scheme['total'] == 6 and scheme['subtitle'] == 'Playground > Status'
    detail = look_status.counts_detail([('Installed', 3), ('Planned', 0)], [('X', 1), ('Y', 1), ('Z', 1), ('W', 1)])
    assert detail == 'Installed 3. Not a status: "X", "Y", "Z" and 1 more.'
    assert look_status.counts_detail([('Installed', 0)]) == 'No item carries a known status.'


def test_merge_tab_and_group_writes():
    assert look_status.merge_tab({'Owner': 'Amol', 'Status': 'Planned'}, 'Status', 'Issue') == \
        {'Owner': 'Amol', 'Status': 'Issue'}
    assert look_status.merge_tab(None, 'Status', 'Issue') == {'Status': 'Issue'}
    assert look_status.merge_tab({'Status': 'Issue'}, 'Status', None) == {}
    import datetime
    merged = look_status.merge_tab({'When': datetime.datetime(2026, 1, 2), 'N': 3, 'Flag': True}, 'S', 'x')
    assert merged == {'When': '2026-01-02 00:00:00', 'N': 3, 'Flag': True, 'S': 'x'}
    groups = look_status.group_writes([('a', None), ('b', {'Owner': 'A'}), ('c', {}), ('d', {'Owner': 'A'})],
                                      'Status', 'Issue')
    assert groups == [({'Status': 'Issue'}, ['a', 'c']), ({'Owner': 'A', 'Status': 'Issue'}, ['b', 'd'])]
    cleared = look_status.group_writes([('a', {'Status': 'X'}), ('b', {'Status': 'Y', 'O': 1})], 'Status', None)
    assert cleared == [({}, ['a']), ({'O': 1}, ['b'])]


def test_chunks():
    groups = [({'S': 'A'}, list(range(5))), ({}, ['x'])]
    assert look_status.chunks(groups, 2) == [({'S': 'A'}, [0, 1]), ({'S': 'A'}, [2, 3]), ({'S': 'A'}, [4]), ({}, ['x'])]
    assert look_status.chunks([], 2) == []


def test_parse_extra_and_options():
    statuses, problems = look_status.parse_extra('Delivered = 4E79A7\n\nFabricated=#abc\nbad line\n = 123456\nX = zz')
    assert statuses == [['Delivered', '4E79A7'], ['Fabricated', 'AABBCC']]
    assert len(problems) == 3 and problems[0].startswith('Line 4')
    cfg = look_status.normalize_config({})
    assert look_status.status_options(cfg)[-1] == look_status.CLEAR


def test_config_form_roundtrip():
    cfg = look_status.normalize_config({'statuses': [['Installed', '010203'], ['In progress', None],
                                                     ['Delivered', '4E79A7']]})
    fields = look_status.config_fields(cfg)
    keys = [f.get('key') for f in fields if f.get('key')]
    assert keys[:2] == ['category', 'property'] and 'extra' in keys
    by_key = dict((f['key'], f) for f in fields if f.get('key'))
    assert by_key['on0']['default'] is True and by_key['hex0']['default'] == '010203'
    assert by_key['on1']['default'] is False
    assert by_key['extra']['default'] == 'Delivered = 4E79A7'
    assert by_key['extra']['validate']('A = 123456') is None
    assert by_key['extra']['validate']('nonsense').startswith('Line 1')
    values = {'category': 'Custom', 'property': 'State', 'extra': 'Delivered = 4E79A7'}
    for index in range(len(look_status.DEFAULT_STATUSES)):
        values['on%d' % index] = index == 0
        values['hex%d' % index] = '0A0B0C'
    cfg = look_status.config_from_form(values)
    assert cfg['category'] == 'Custom' and cfg['statuses'][0] == ['Installed', '0A0B0C']
    assert cfg['statuses'][1] == ['In progress', None] and cfg['statuses'][-1] == ['Delivered', '4E79A7']


# ---- API half -----------------------------------------------------------------------------


def _props_module(tabs, calls):
    module = types.ModuleType('pynavis.props')
    module.get = lambda item, category, prop, by_display=True: item.props.get((category, prop))
    module.get_custom = lambda item, tab: tabs.get((item.DisplayName, tab))

    def set_custom(members, tab, values, doc=None, progress=None):
        calls.append(('set', [m.DisplayName for m in members], tab, dict(values)))
        return len(members), []

    def remove_custom(members, tab, doc=None, progress=None):
        calls.append(('remove', [m.DisplayName for m in members], tab))
        return len(members), []
    module.set_custom = set_custom
    module.remove_custom = remove_custom
    return module


def test_api_set_status_merges_and_paints_once():
    doc, n = nav.model_tree()
    calls = []
    tabs = {('Wall 1', 'Playground'): {'Owner': 'Amol', 'Status': 'Planned'}}
    with test_colorize.fake(doc):
        saved = sys.modules.get('pynavis.props')
        sys.modules['pynavis.props'] = _props_module(tabs, calls)
        sys.modules['pynavis'].props = sys.modules['pynavis.props']
        try:
            cfg = look_status.normalize_config({})
            written, errors, stopped = look_status.set_status([n['Wall 1'], n['Wall 2']], cfg, 'Issue')
            assert written == 2 and errors == [] and stopped is False
            assert calls == [('set', ['Wall 1'], 'Playground', {'Owner': 'Amol', 'Status': 'Issue'}),
                             ('set', ['Wall 2'], 'Playground', {'Status': 'Issue'})]
            assert doc.transactions == ['Set status']
            assert doc.Models.calls[-1][0] == 'color'
            del calls[:]
            look_status.set_status([n['Duct']], cfg, None)
            assert calls == [('remove', ['Duct'], 'Playground')]
            assert doc.Models.calls[-1][0] == 'reset'
        finally:
            sys.modules['pynavis.props'] = saved


def test_api_set_status_stops_between_pieces():
    doc, n = nav.model_tree()
    calls = []
    Cancelled = type('Cancelled', (Exception,), {})
    seen = []

    def progress(fraction, label):
        seen.append(label)
        if len(seen) == 2:
            raise Cancelled()
    with test_colorize.fake(doc):
        saved = sys.modules.get('pynavis.props')
        sys.modules['pynavis.props'] = _props_module({}, calls)
        sys.modules['pynavis'].props = sys.modules['pynavis.props']
        previous = look_status.CHUNK
        look_status.CHUNK = 1
        try:
            cfg = look_status.normalize_config({})
            targets = [n['Wall 1'], n['Wall 2'], n['Duct']]
            written, errors, stopped = look_status.set_status(targets, cfg, 'Planned', progress=progress)
            assert (written, stopped) == (1, True)
            assert seen == ['Writing 0 of 3', 'Writing 1 of 3']
            assert doc.Models.calls[-1] == ('color', [n['Wall 1']], doc.Models.calls[-1][2])
        finally:
            look_status.CHUNK = previous
            sys.modules['pynavis.props'] = saved


def test_api_writable_problem_spots_model_tabs():
    class Category(object):
        def __init__(self, display, name):
            self.DisplayName = display
            self.Name = name

    class Item(object):
        def __init__(self, cats):
            self.PropertyCategories = cats
    cfg = look_status.normalize_config({'category': 'Element'})
    assert look_status.writable_problem(cfg, [Item([Category('Element', 'LcRevitData_Element')])])
    assert look_status.writable_problem(cfg, [Item([Category('Element', look_status.USER_TAB_NAME)])]) is None
    assert look_status.writable_problem(cfg, [Item([])]) is None

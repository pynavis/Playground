# -*- coding: utf-8 -*-
"""namo.colorize: ranking, stable colours, scheme planning, legend HTML, presets,
and the API half through the fake Navisworks layer."""
import contextlib
import os
import sys

import _compat

from namo import colorize, colors, paths

import test_items as nav


# ---- ranking and colours -----------------------------------------------------------


def test_rank_groups_most_common_then_natural():
    ranked = colorize.rank_groups({'Level 10': [1], 'Level 2': [1], 'Walls': [1, 2, 3], 'b': [1, 2]})
    assert [v for v, _m in ranked] == ['Walls', 'b', 'Level 2', 'Level 10']


def test_group_by_value_parallel_lists():
    groups = colorize.group_by_value(['a', 'b', 'c', 'd'], ['X', 'Y', 'X', 'X'])
    assert groups == [('X', ['a', 'c', 'd']), ('Y', ['b'])]


def test_assign_colors_fresh_follow_palette():
    pairs = colorize.assign_colors(['A', 'B', 'C'])
    assert pairs == [('A', colors.PALETTE[0]), ('B', colors.PALETTE[1]), ('C', colors.PALETTE[2])]


def test_assign_colors_keeps_remembered_and_never_shares():
    remembered = {'B': colors.PALETTE[0], 'C': colors.PALETTE[0], 'D': 'not a colour'}
    pairs = dict(colorize.assign_colors(['A', 'B', 'C', 'D'], remembered))
    assert pairs['B'] == colors.PALETTE[0]          # B claimed its colour first
    assert pairs['C'] != colors.PALETTE[0]          # C lost the clash
    assert len(set(pairs.values())) == 4
    assert colors.GHOST not in pairs.values() and colors.MISSING not in pairs.values()


def test_assign_colors_past_palette_stays_distinct():
    values = ['v%d' % i for i in range(30)]
    hexes = [h for _v, h in colorize.assign_colors(values)]
    assert len(set(hexes)) == 30
    assert all(colors.parse_hex(h) == h for h in hexes)


def test_assign_colors_reserved_skipped():
    pairs = colorize.assign_colors(['A'], reserved=(colors.PALETTE[0],))
    assert pairs == [('A', colors.PALETTE[1])]


def test_plan_scheme_top_missing_other_grey():
    ranked = [('Ducts', 50), (colorize.NO_VALUE, 7), ('Pipes', 30), ('Walls', 3), ('Doors', 1)]
    plan = colorize.plan_scheme(ranked, top=2, other='grey')
    assert [e['value'] for e in plan['entries']] == ['Ducts', 'Pipes', colorize.NO_VALUE, 'Other (2 values)']
    assert plan['kinds'] == ['value', 'value', 'missing', 'other']
    assert plan['entries'][2]['hex'] == colors.MISSING
    assert plan['entries'][3]['hex'] == colors.GHOST and plan['entries'][3]['count'] == 4
    assert plan['other_values'] == ['Walls', 'Doors']
    assert plan['total'] == 91


def test_plan_scheme_leave_and_no_fold():
    plan = colorize.plan_scheme([('A', 2), (colorize.NO_VALUE, 1)], top=12, other='leave')
    assert plan['kinds'] == ['value', 'missing']
    assert plan['entries'][1]['hex'] is None
    plan = colorize.plan_scheme([('A', 2), ('B', 1)], top=1, other='leave')
    assert plan['entries'][1] == {'value': 'Other (1 value)', 'hex': None, 'count': 1}


def test_plan_scheme_clamps_top():
    ranked = [('v%d' % i, 100 - i) for i in range(60)]
    plan = colorize.plan_scheme(ranked, top=500)
    assert plan['kinds'].count('value') == colorize.MAX_TOP
    assert colorize.plan_scheme(ranked, top=0)['kinds'].count('value') == colorize.DEFAULT_TOP


def test_plan_scheme_uses_memory():
    plan = colorize.plan_scheme([('A', 5), ('B', 4)], remembered={'B': '123456'})
    assert plan['entries'][1]['hex'] == '123456'


def test_memory_roundtrip_newest_first_and_capped():
    memory = colorize.update_memory({}, 'k', [('A', '111111'), ('B', '222222')])
    memory = colorize.update_memory(memory, 'k', [('B', '333333'), ('C', None)])
    assert memory['k'] == [['B', '333333'], ['A', '111111']]
    assert colorize.memory_map(memory, 'k') == {'A': '111111', 'B': '333333'}
    capped = colorize.update_memory(memory, 'k', [('Z', '444444')], limit=2)
    assert capped['k'] == [['Z', '444444'], ['B', '333333']]
    assert colorize.memory_map({}, 'missing') == {}
    assert memory is not capped and 'k' in memory


def test_value_pairs_and_make_scheme():
    plan = colorize.plan_scheme([('A', 5), (colorize.NO_VALUE, 2), ('B', 1)], top=1)
    scheme = colorize.make_scheme('Element', 'Category', plan, 'visible items')
    assert scheme['title'] == 'Category'
    assert scheme['subtitle'] == 'Element > Category, visible items'
    assert colorize.value_pairs(scheme) == [('A', plan['entries'][0]['hex'])]
    assert colorize.scheme_key(' Element ', 'Category') == 'element > category'


# ---- text -------------------------------------------------------------------------------


def test_share_and_plural():
    assert colorize.share_text(1, 3) == '33%'
    assert colorize.share_text(1, 30) == '3.3%'
    assert colorize.share_text(50, 100) == '50%'
    assert colorize.share_text(1, 100000) == '<0.1%'
    assert colorize.share_text(1, 0) == ''
    assert colorize.plural(1, 'item') == '1 item'
    assert colorize.plural(2345, 'item') == '2,345 items'
    assert colorize.plural(2, 'value had', 'values had') == '2 values had'


def test_legend_html_escapes_and_marks_unchanged():
    scheme = {'title': 'A <b>', 'subtitle': 'x & y',
              'entries': [{'value': '<script>', 'hex': '4E79A7', 'count': 3},
                          {'value': 'Other (2 values)', 'hex': None, 'count': 1}]}
    html = colorize.legend_html(scheme)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'A &lt;b&gt;' in html and 'x &amp; y' in html
    assert 'background:#4E79A7' in html and '(unchanged)' in html
    assert '75%' in html and '25%' in html


def test_legend_lines_and_summary():
    plan = colorize.plan_scheme([('A', 5), ('B', 4), ('C', 1)], top=2)
    scheme = colorize.make_scheme('Element', 'Category', plan, 'whole model')
    lines = colorize.legend_lines(scheme)
    assert lines[0] == 'Category' and lines[1].startswith('Element > Category')
    assert lines[2].startswith('#') and lines[2].endswith('A  5')
    message, detail = colorize.summary(scheme, 10)
    assert message == 'Colored 10 items by Category'
    assert detail.startswith('2 values colored, 1 value as Other')
    assert '—' not in detail and '–' not in detail


def test_sample_evenly():
    assert colorize.sample_evenly(range(5), 10) == [0, 1, 2, 3, 4]
    picked = colorize.sample_evenly(range(1001), 3)
    assert picked == [0, 500, 1000]
    assert colorize.sample_evenly(range(10), 1) == [0]


def test_property_rows_sorted_and_valued():
    rows = colorize.property_rows([('Item', 'Name', 300), ('Element', 'Level 10', 3),
                                   ('Element', 'Level 2', 5)], 300)
    assert [r['cells'][1] for r in rows] == ['Level 2', 'Level 10', 'Name']
    assert rows[0]['value'] == ('Element', 'Level 2')


def test_options_fields_scope_fallback():
    fields = colorize.options_fields(0, {'scope': 'selection', 'top': 5})
    scope = fields[0]
    assert [v for _l, v in scope['options']] == ['visible', 'model']
    assert scope['default'] == 'visible'
    assert fields[1]['default'] == 5
    fields = colorize.options_fields(3, {})
    assert fields[0]['options'][0] == ('Current selection (3 items)', 'selection')
    # a selection is the default scope whatever was remembered (catalog rule)
    assert colorize.options_fields(3, {'scope': 'model'})[0]['default'] == 'selection'
    assert colorize.options_fields(0, {'scope': 'model'})[0]['default'] == 'model'


# ---- presets ----------------------------------------------------------------------------


def _scheme():
    plan = colorize.plan_scheme([('Ducts', 5), (colorize.NO_VALUE, 2), ('Pipes', 1), ('Doors', 1)], top=2)
    return colorize.make_scheme('Element', 'Category', plan, 'whole model', ghost=0.85)


def test_preset_from_scheme_keeps_values_and_extras():
    import datetime
    preset = colorize.preset_from_scheme(_scheme(), 'By category', user='amol',
                                         now=datetime.datetime(2026, 10, 5, 9, 0, 0))
    assert [e['value'] for e in preset['entries']] == ['Ducts', 'Pipes']
    assert preset['missing'] == colors.MISSING and preset['other'] == colors.GHOST
    assert preset['ghost'] == 0.85 and preset['updated'] == '2026-10-05T09:00:00'
    assert preset['property'] == {'category': 'Element', 'property': 'Category'}


def test_preset_from_scheme_without_values_refuses():
    scheme = {'entries': [{'value': 'A', 'hex': None, 'count': 1}], 'kinds': ['value'],
              'property': {'category': 'E', 'property': 'P'}}
    _compat.raises(ValueError, colorize.preset_from_scheme, scheme, 'x')


def test_normalize_preset_sentences():
    for bad in (None, {}, {'format': 'other'}):
        error = _compat.raises(ValueError, colorize.normalize_preset, bad)
        assert 'not a Playground color preset' in str(error)
    base = {'format': colorize.PRESET_FORMAT, 'name': 'X', 'property': {'category': 'E', 'property': 'P'},
            'entries': [{'value': 'A', 'hex': '#abc'}, {'value': 'A', 'hex': '000000'},
                        {'value': None, 'hex': '000000'}, 'junk'], 'ghost': 'bad'}
    clean = colorize.normalize_preset(base)
    assert clean['entries'] == [{'value': 'A', 'hex': 'AABBCC'}] and clean['ghost'] is None
    _compat.raises(ValueError, colorize.normalize_preset, dict(base, name='  '))
    _compat.raises(ValueError, colorize.normalize_preset, dict(base, property={}))
    _compat.raises(ValueError, colorize.normalize_preset, dict(base, entries=[]))


def test_preset_files_roundtrip():
    folder = _compat.tmpdir('colorize_presets')
    preset = colorize.preset_from_scheme(_scheme(), 'By category')
    path = colorize.save_preset(preset, folder)
    assert os.path.basename(path) == 'By category.json'
    assert [p['name'] for p in colorize.list_presets(folder)] == ['By category']
    preset['entries'][0]['hex'] = '010203'
    assert colorize.save_preset(preset, folder) == path            # same name replaces
    assert colorize.find_preset('BY CATEGORY', folder)['entries'][0]['hex'] == '010203'
    with open(os.path.join(folder, 'junk.json'), 'w') as handle:
        handle.write('{"format": "something else"}')
    assert len(colorize.list_presets(folder)) == 1
    assert colorize.rename_preset('By category', 'Trades', folder) == 'Trades'
    assert [p['name'] for p in colorize.list_presets(folder)] == ['Trades']
    assert not os.path.exists(path)
    exported = os.path.join(folder, 'out', 'shared.json')
    colorize.export_preset('Trades', exported, folder)
    assert colorize.import_preset(exported, folder) == 'Trades (2)'
    _compat.raises(ValueError, colorize.rename_preset, 'Trades (2)', 'trades', folder)
    _compat.raises(ValueError, colorize.rename_preset, 'Nope', 'X', folder)
    assert colorize.delete_preset('Trades (2)', folder) is True
    assert colorize.delete_preset('Trades (2)', folder) is False
    _compat.raises(ValueError, colorize.import_preset, os.path.join(folder, 'junk.json'), folder)


def test_presets_folder_follows_team_root():
    folder = _compat.tmpdir('colorize_root')
    previous = paths.redirect(folder)
    try:
        assert colorize.presets_folder().startswith(folder)
        assert colorize.presets_folder().endswith(os.path.join('presets', 'colors'))
        assert colorize.list_presets() == []
    finally:
        paths.redirect(previous)


def test_search_friendly():
    assert colorize.search_friendly(['Ducts', 'Pipes'])
    assert not colorize.search_friendly(['Ducts', '12'])
    assert not colorize.search_friendly(['1,250.5'])
    assert not colorize.search_friendly([colorize.NO_VALUE])
    assert not colorize.search_friendly([])
    assert not colorize.search_friendly(['v%d x' % i for i in range(20)])
    assert colorize.search_friendly(['Level 1'])


def test_preset_plan_and_missed_text():
    preset = colorize.normalize_preset({'format': colorize.PRESET_FORMAT, 'name': 'P',
                                        'property': {'category': 'E', 'property': 'C'},
                                        'entries': [{'value': 'A', 'hex': '111111'},
                                                    {'value': 'B', 'hex': '222222'}]})
    plan = colorize.preset_plan(preset, [('A', ['a1', 'a2']), ('B', [])])
    assert plan['groups'] == [(['a1', 'a2'], '111111', None)]
    assert plan['missed'] == ['B'] and plan['painted'] == 2
    assert plan['scheme']['subtitle'] == 'E > C, preset'
    assert colorize.missed_text(['B']) == '1 value had no match: B.'
    text = colorize.missed_text(['a', 'b', 'c', 'd', 'e', 'f'])
    assert text.startswith('6 values had no match: a, b, c, d and 2 more')
    assert colorize.missed_text([]) == ''


def test_paint_groups_collects_other():
    plan = colorize.plan_scheme([('A', 2), ('B', 1), ('C', 1), (colorize.NO_VALUE, 1)], top=1)
    groups = [('A', ['a1', 'a2']), ('B', ['b']), ('C', ['c']), (colorize.NO_VALUE, ['n'])]
    out = colorize.paint_groups(groups, plan)
    assert out[0] == (['a1', 'a2'], plan['entries'][0]['hex'], None)
    assert out[1] == (['n'], colors.MISSING, None)
    assert out[2] == (['b', 'c'], colors.GHOST, None)
    leave = colorize.plan_scheme([('A', 2), ('B', 1)], top=1, other='leave')
    assert colorize.paint_groups([('A', ['a']), ('B', ['b'])], leave) == [(['a'], leave['entries'][0]['hex'], None)]


# ---- API half through the fake layer ------------------------------------------------------


@contextlib.contextmanager
def fake(doc):
    """FakeNav with a nesting-aware transaction (Navisworks ignores a transaction
    opened inside another; the shared fake records every call)."""
    with nav.FakeNav(doc) as layer:
        depth = [0]

        @contextlib.contextmanager
        def transaction(name, d=None):
            if depth[0] == 0:
                (d or doc).transactions.append(name)
            depth[0] += 1
            try:
                yield None
            finally:
                depth[0] -= 1
        sys.modules['pynavis.viewpoints'].transaction = transaction
        yield layer


def test_api_visible_objects_skips_hidden():
    doc, n = nav.model_tree()
    with fake(doc):
        objs = colorize.visible_objects([n['ARCH.nwc'], n['MEP.nwc']])
        assert [o.DisplayName for o in objs] == ['Wall 1', 'Wall 2', 'Duct']
        n['Level 1'].IsHidden = True
        objs = colorize.scope_objects('visible')
        assert [o.DisplayName for o in objs] == ['Duct']
        assert [o.DisplayName for o in colorize.scope_objects('model')] == \
            ['Wall 1', 'Wall 2', 'Duct', 'Hidden box']
        doc.CurrentSelection.SelectedItems = [n['Wall 2']]
        assert [o.DisplayName for o in colorize.scope_objects('selection')] == ['Wall 2']


def test_api_visible_objects_parent_not_on_stack():
    doc, n = nav.model_tree()
    with fake(doc):
        n['Level 1'].IsHidden = True
        assert colorize.visible_objects([n['Wall 1']]) == []
        assert [o.DisplayName for o in colorize.visible_objects([n['Duct']])] == ['Duct']


def test_api_read_groups_and_apply_one_step():
    doc, n = nav.model_tree()
    with fake(doc):
        objs = colorize.scope_objects('model')
        groups = colorize.read_groups(objs, 'Element', 'Category')
        assert [(v, len(m)) for v, m in groups] == [('Walls', 2), (colorize.NO_VALUE, 1), ('Ducts', 1)]
        plan = colorize.plan_scheme([(v, len(m)) for v, m in groups], top=1)
        assert len(colorize.paint_groups(groups, plan)) == 3       # Walls, (no value), Other
        leave = colorize.plan_scheme([(v, len(m)) for v, m in groups], top=1, other='leave')
        painted = colorize.apply(colorize.paint_groups(groups, leave), reset_first=True, rest_transparency=0.85)
        assert painted == 2
        assert doc.Models.calls[0][0] == 'reset_all'
        assert doc.Models.calls[1][0] == 'color' and len(doc.Models.calls[1][1]) == 2
        assert doc.Models.calls[2] == ('transparency', [n['MEP.nwc']], 0.85)
        assert doc.transactions == ['Color by property']


def test_api_apply_resets_only_the_selection_when_asked():
    doc, n = nav.model_tree()
    with fake(doc):
        colorize.apply([([n['Duct']], '112233', None)], reset_first=True, reset_items=[n['Duct']])
        assert doc.Models.calls[0] == ('reset', [n['Duct']], None)
        assert doc.Models.calls[1][0] == 'color'
        del doc.Models.calls[:]
        colorize.apply([([n['Duct']], '112233', None)], reset_first=True, reset_items=[])
        assert [c[0] for c in doc.Models.calls] == ['color']


def test_api_find_by_walk_ignores_case():
    doc, n = nav.model_tree()
    with fake(doc):
        objs = colorize.scope_objects('model')
        found = colorize.find_by_walk('Element', 'Category', ['walls', 'Roofs'], objs)
        assert [(v, [i.DisplayName for i in m]) for v, m in found] == [('walls', ['Wall 1', 'Wall 2']), ('Roofs', [])]


def test_api_property_names_sampled():
    doc, n = nav.model_tree()
    with fake(doc):
        names, sampled = colorize.property_names(colorize.scope_objects('model'), limit=2)
        assert sampled == 2
        assert ('Element', 'Category', 1) in names

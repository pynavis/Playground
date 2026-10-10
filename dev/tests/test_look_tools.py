# -*- coding: utf-8 -*-
"""namo.look_tools: reset kinds and wording, appearance merging, background presets,
and the API halves through the fake Navisworks layer."""
import _compat

from namo import colors, look_tools

import test_colorize
import test_items as nav


def test_reset_kinds_and_summary():
    assert look_tools.normalize_kinds(['hidden', 'bogus', 'materials']) == ['materials', 'hidden']
    assert look_tools.reset_summary(['hidden']) == 'Reset hidden items'
    assert look_tools.reset_summary(['transforms', 'materials', 'hidden']) == \
        'Reset colors and transparency, hidden items and moved items'
    assert look_tools.reset_summary([]) == 'Nothing reset'
    field = look_tools.reset_fields([])[0]
    assert field['default'] == look_tools.RESET_DEFAULT
    assert field['validate']([]) and field['validate'](['hidden']) is None
    assert look_tools.reset_fields(['flags'])[0]['default'] == ['flags']


def test_nearest_override_per_part():
    chain = [None, ('4E79A7', None), (None, 0.85), ('FF0000', 0.2)]
    assert look_tools.nearest_override(chain) == ('4E79A7', 0.85)
    assert look_tools.nearest_override([]) == (None, None)
    assert look_tools.nearest_override([(None, 1.7)]) == (None, 1.0)


def test_merge_appearance():
    assert look_tools.merge_appearance(('112233', None), ('445566', 0.0)) == ('112233', 0.0, 'override')
    assert look_tools.merge_appearance((None, 0.5), ('445566', 0.0)) == ('445566', 0.5, 'override')
    assert look_tools.merge_appearance((None, None), ('445566', 0.25)) == ('445566', 0.25, 'model')
    assert look_tools.merge_appearance((None, None), (None, None)) == (None, None, None)


def test_appearance_text_and_fields():
    assert look_tools.appearance_text('4E79A7', 0.3) == '#4E79A7, 30% transparent'
    assert look_tools.appearance_text('4E79A7', 0.0) == '#4E79A7'
    assert look_tools.appearance_text(None, 0.0) == 'opaque'
    assert look_tools.appearance_text(None, None) == 'unknown'
    fields = look_tools.match_fields('Duct', None, 0.5)
    assert fields[1]['default'] == colors.GHOST and fields[2]['default'] == 50


def test_match_fields_refuse_blank_answers():
    # Regression: a cleared colour or transparency box came back as '' / None and
    # crashed Match Appearance (None / 100.0, a '' colour in paint.apply).
    from namo import ui
    fields = ui.normalize_fields(look_tools.match_fields('Duct', '4E79A7', 0.3))
    values, errors = ui.collect(fields, {'hex': '', 'transparency': ''})
    assert 'hex' in errors and 'transparency' in errors
    values, errors = ui.collect(fields, {'hex': '4E79A7', 'transparency': '30'})
    assert errors == {} and values == {'hex': '4E79A7', 'transparency': 30}


def test_backgrounds():
    assert look_tools.background_named('dark GRADIENT')['colors'] == ['3C4352', '121519']
    assert look_tools.background_named('nope') is None
    assert look_tools.normalize_background({'style': 'graduated', 'colors': ['fff']}) is None
    assert look_tools.normalize_background({'style': 'odd', 'colors': []}) is None
    read = {'style': 'graduated', 'colors': ['FEFEFE', 'C8D0DA']}
    assert look_tools.match_background(read) == 1
    assert look_tools.match_background({'style': 'plain', 'colors': ['808080']}) is None
    assert look_tools.match_background(None) is None
    assert look_tools.next_background(None) == 0
    assert look_tools.next_background(1) == 2
    assert look_tools.next_background(len(look_tools.BACKGROUNDS) - 1) == 0
    assert look_tools.next_background(99) == 0


def test_background_form():
    fields = look_tools.background_fields({'choice': 'Black'})
    assert fields[0]['default'] == 'Black'
    assert look_tools.background_fields({'choice': 'nonsense'})[0]['default'] == 'White'
    spec = look_tools.background_from_form({'choice': look_tools.CUSTOM_GRADIENT, 'top': '#111111',
                                            'bottom': '222222'})
    assert spec == {'name': look_tools.CUSTOM_GRADIENT, 'style': 'graduated', 'colors': ['111111', '222222']}
    assert look_tools.background_from_form({'choice': look_tools.CUSTOM_PLAIN, 'top': 'ABCDEF'})['style'] == 'plain'
    assert look_tools.background_from_form({'choice': 'Horizon'})['style'] == 'horizon'


# ---- API half ------------------------------------------------------------------------------


class _Calls(object):
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, len(args)))
        return record


def test_api_reset_one_transaction():
    doc, n = nav.model_tree()
    with test_colorize.fake(doc):
        models = _Calls()
        doc.Models = models
        chosen = look_tools.reset(['flags', 'transforms', 'materials'])
        assert chosen == ['materials', 'transforms', 'flags']
        assert [c[0] for c in models.calls] == ['ResetAllPermanentMaterials', 'ResetAllPermanentTransforms',
                                               'ResetAllRequired', 'ResetAllFrozen']
        assert doc.transactions == ['Reset overrides']


def test_api_set_background_styles():
    doc, n = nav.model_tree()
    calls = []
    doc.SetPlainBackground = lambda c: calls.append(('plain', (c.R, c.G, c.B)))
    doc.SetGraduatedBackground = lambda a, b: calls.append(('graduated', a.R, b.R))
    doc.SetHorizonBackground = lambda a, b, c, d: calls.append(('horizon',))
    with test_colorize.fake(doc):
        look_tools.set_background(look_tools.background_named('Black'))
        look_tools.set_background(look_tools.background_named('White'))
        look_tools.set_background(look_tools.background_named('Light gradient'))
        look_tools.set_background(look_tools.background_named('Horizon'))
        _compat.raises(ValueError, look_tools.set_background, {'style': 'plain', 'colors': []})
    assert calls[0] == ('plain', (0.0, 0.0, 0.0)) and calls[1] == ('plain', (1.0, 1.0, 1.0))
    assert calls[2][0] == 'graduated' and calls[3] == ('horizon',)


def test_api_read_background_refuses_quietly():
    assert look_tools.read_background() is None


def test_api_read_appearance_falls_back_to_model():
    doc, n = nav.model_tree()
    with test_colorize.fake(doc):
        n['Duct solid'].color = (1.0, 0.5, 0.0)
        hex_value, transparency, how = look_tools.read_appearance(n['Duct'])
        assert (hex_value, transparency, how) == ('FF8000', 0.25, 'model')


def test_api_read_appearance_uses_ancestor_overrides():
    doc, n = nav.model_tree()

    class Override(object):
        def __init__(self, item, color=None, transparency=None):
            self.Item = item
            self.Color = color
            self.Transparency = transparency

    class Snapshot(object):
        ContainsAppearanceOverrides = True

        def GetAppearanceOverrides(self):
            return nav._Ns(MaterialOverrides=[Override(n['MEP.nwc'], None, 0.85),
                                              Override(n['Duct'], nav.Color(0.0, 0.0, 1.0), None)])
    doc.SavedViewpoints.CaptureRuntimeOverrides = lambda: Snapshot()
    with test_colorize.fake(doc):
        assert look_tools.read_appearance(n['Duct solid']) == ('0000FF', 0.85, 'override')
        assert look_tools.read_appearance(n['Wall 1'])[2] == 'model'


def test_look_detail_says_where_the_look_came_from():
    assert look_tools.look_detail('#4E79A7', 'override') == '#4E79A7, read from its color override.'
    assert look_tools.look_detail('#4E79A7', 'model') == '#4E79A7, read from its own model color.'
    assert look_tools.look_detail('#4E79A7, 30% transparent', 'chosen') == '#4E79A7, 30% transparent.'


def test_click_prompt_counts_and_explains_a_miss():
    assert look_tools.click_prompt('#4E79A7', 0) == 'Click an object to paint it #4E79A7'
    assert look_tools.click_prompt('#4E79A7', 1234) == 'Click the next object (1,234 painted)'
    assert look_tools.click_prompt('#4E79A7', 2, 'Nothing under that point.') ==         'Nothing under that point. Click the next object (2 painted)'


def test_match_appearance_picks_through_namo_picking():
    """Regression: the script used pynavis.pick.point (banned: its marker and its hit
    disagree in the field). Every click goes through namo.picking.point."""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    panel = os.path.join(here, '..', '..', 'Playground.extension', 'Model.tab', 'Look.panel')
    script = os.path.join(panel, 'Look_Tools.stack', 'Match_Appearance.pushbutton', 'script.py')
    with open(script) as handle:
        text = handle.read()
    assert text.count('picking.point(') == 2 and 'want_item=True' in text
    for banned in ('pick.point', 'point_then', 'pick.Unavailable', 'import pick'):
        assert banned not in text.replace('picking.point', ''), banned

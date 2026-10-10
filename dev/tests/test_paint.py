# -*- coding: utf-8 -*-
"""namo.paint pure half: group planning and the remembered-scheme shape."""
import datetime

import _compat

from namo import paint


def test_plan_groups_drops_empty_and_noop():
    planned = paint.plan_groups([
        ([], 'FF0000', None),
        (['a'], None, None),
        (['b', 'c'], '#00ff00', None),
        (('d',), None, 1.7),
        (['e'], 'abc', -0.2),
    ])
    assert planned == [(['b', 'c'], '00FF00', None), (['d'], None, 1.0), (['e'], 'AABBCC', 0.0)]


def test_plan_groups_rejects_bad_colour():
    _compat.raises(ValueError, paint.plan_groups, [(['a'], 'not a colour', None)])


def test_plan_groups_short_tuples():
    assert paint.plan_groups([(['a'], 'FFFFFF')]) == [(['a'], 'FFFFFF', None)]


def test_normalize_scheme():
    stamp = datetime.datetime(2026, 10, 5, 9, 30, 0)
    scheme = paint.normalize_scheme({
        'title': 'By category',
        'property': {'category': 'Element', 'property': 'Category'},
        'entries': [{'value': 'Ducts', 'hex': '#4e79a7', 'count': '12'},
                    {'value': None, 'hex': None}],
        'ghost': 2,
        'extra': 'kept',
    }, now=stamp)
    assert scheme['time'] == '2026-10-05T09:30:00'
    assert scheme['entries'][0] == {'value': 'Ducts', 'hex': '4E79A7', 'count': 12}
    assert scheme['entries'][1] == {'value': None, 'hex': None, 'count': 0}
    assert scheme['ghost'] == 1.0
    assert scheme['extra'] == 'kept'
    assert scheme['property'] == {'category': 'Element', 'property': 'Category'}


def test_normalize_scheme_defaults():
    scheme = paint.normalize_scheme(None)
    assert scheme['title'] == '' and scheme['entries'] == [] and scheme['ghost'] is None
    assert scheme['property'] == {'category': '', 'property': ''}


# ---- API half through the fake Navisworks layer (see test_items) -----------------

import test_items as nav  # noqa: E402


def test_api_apply_one_transaction():
    doc, n = nav.model_tree()
    with nav.FakeNav(doc):
        count = paint.apply([([n['Wall 1'], n['Wall 2']], 'FF0000', None),
                             ([], '00FF00', 0.5),
                             ([n['Duct']], None, 0.3)], name='Color by category')
        assert count == 3
        assert doc.transactions == ['Color by category']
        assert doc.Models.calls == [('color', [n['Wall 1'], n['Wall 2']], (1.0, 0.0, 0.0)),
                                    ('transparency', [n['Duct']], 0.3)]
        assert paint.apply([]) == 0 and doc.transactions == ['Color by category']


def test_api_ghost_touches_only_the_complement():
    doc, n = nav.model_tree()
    with nav.FakeNav(doc):
        assert paint.ghost([]) == 0 and doc.Models.calls == []
        ghosted = paint.ghost([n['Wall 1'], n['Duct solid']], transparency=0.8, hex='BFBFBF')
        assert ghosted == 2          # Duct holds a kept item, so only its sibling goes
        names = [i.DisplayName for i in doc.Models.calls[0][1]]
        assert names == ['Wall 2', 'Hidden box']
        assert [c[0] for c in doc.Models.calls] == ['color', 'transparency']
        for _kind, touched, _value in doc.Models.calls:
            assert n['Wall 1'] not in touched and n['Duct solid'] not in touched
            assert n['Level 1'] not in touched and n['ARCH.nwc'] not in touched
        assert doc.transactions == ['Ghost other items']


def test_api_reset_temporary_and_read_color():
    doc, n = nav.model_tree()
    with nav.FakeNav(doc):
        assert paint.reset() == -1
        assert paint.reset([n['Duct']]) == 1
        assert paint.reset([]) == 0
        assert [c[0] for c in doc.Models.calls] == ['reset_all', 'reset']
        assert paint.temporary([([n['Duct']], '336699', 0.1)]) == 1
        paint.reset_temporary()
        assert [c[0] for c in doc.Models.calls][-3:] == ['temp_color', 'temp_transparency', 'reset_temp']
        n['Duct solid'].color = (1.0, 0.5, 0.0)
        assert paint.read_color(n['Duct']) == ('FF8000', 0.25)
        assert paint.read_color(object()) == (None, None)

# -*- coding: utf-8 -*-
"""namo.data_labels: leader and anchor geometry, label text, draw/clear through a fake
pynavis.overlay."""
import sys
import types

import _compat
import test_propindex as pf

from namo import data_labels, session


def test_geometry():
    box = ((0.0, 0.0, 0.0), (3.0, 4.0, 12.0))
    assert _compat.approx(data_labels.leader_length(box), 13.0 * data_labels.LEADER_SHARE)
    assert data_labels.leader_length(None) == 0.0
    # Refit: the leader is a real-world length, whatever the model units are.
    point = ((1, 1, 1), (1, 1, 1))
    assert _compat.approx(data_labels.leader_length(point), data_labels.MIN_LEADER_M)
    assert _compat.approx(data_labels.leader_length(point, 0.3048), data_labels.MIN_LEADER_M / 0.3048)
    assert _compat.approx(data_labels.leader_length(point, 0.001), 150.0)
    campus = ((0.0, 0.0, 0.0), (3000.0, 4000.0, 0.0))
    assert _compat.approx(data_labels.leader_length(campus, 0.3048), data_labels.MAX_LEADER_M / 0.3048)
    # far from the origin (shared coordinates) the size only depends on the box extent
    far = ((1370000.0, 1370000.0, 0.0), (1370003.0, 1370004.0, 12.0))
    assert _compat.approx(data_labels.leader_length(far, 0.3048), data_labels.MIN_LEADER_M / 0.3048)
    start, end = data_labels.label_anchor(((0, 0, 0), (2, 4, 3)), 0.5)
    assert start == (1.0, 2.0, 3) and end == (1.0, 2.0, 3.5)


def test_label_text():
    assert data_labels.label_text(' a\n b ') == 'a b'
    long = data_labels.label_text('x' * 100)
    assert len(long) == data_labels.MAX_TEXT and long.endswith('...')


def _fake_overlay(loaded=True):
    module = types.ModuleType('pynavis.overlay')
    module.items = {}
    module.redraws = 0

    def add(tag, segments, label=None, label_at=None, anchor=None):
        module.items[tag] = (segments, label, label_at)
        return loaded

    def clear(tag=None):
        if tag is None:
            module.items.clear()
        else:
            module.items.pop(tag, None)
        return loaded

    def redraw():
        module.redraws += 1
        return loaded
    module.add, module.clear, module.redraw = add, clear, redraw
    return module


def test_draw_and_clear():
    doc, n = pf.tree()
    with pf.Fake(doc):
        fake = _fake_overlay()
        sys.modules['pynavis.overlay'] = fake
        sys.modules['pynavis'].overlay = fake
        try:
            session.clear(data_labels.HOLDER)
            drawn, loaded = data_labels.draw([(((0, 0, 0), (1, 1, 1)), 'W1'), (((5, 0, 0), (6, 1, 2)), 'W2')])
            assert (drawn, loaded) == (2, True)
            assert sorted(fake.items) == ['playground-labels:1', 'playground-labels:2']
            segments, label, at = fake.items['playground-labels:2']
            assert label == 'W2' and at[2] > 2
            assert data_labels.clear() == 2 and fake.items == {}
            assert data_labels.clear() == 0
            missing = _fake_overlay(loaded=False)
            sys.modules['pynavis.overlay'] = missing
            sys.modules['pynavis'].overlay = missing
            assert data_labels.draw([(((0, 0, 0), (1, 1, 1)), 'W1')]) == (0, False)
            assert data_labels.tags() == [] and missing.items == {}
        finally:
            sys.modules.pop('pynavis.overlay', None)
            session.clear(data_labels.HOLDER)

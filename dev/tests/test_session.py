# -*- coding: utf-8 -*-
"""namo.session: holders that survive the per-run lib sweep, and the shared log."""
import sys

from namo import session


def test_holder_is_one_module_object_under_a_playground_key():
    h = session.holder('f2test')
    assert sys.modules['playground_f2test'] is h
    assert session.holder('f2test') is h
    assert getattr(h, '__file__', None) is None             # the per-run sweep keys on __file__
    h.window = 'w'
    assert session.get('f2test', 'window') == 'w'
    assert session.get('f2test', 'missing', 7) == 7
    assert session.set('f2test', 'count', 3) == 3
    assert session.holder('f2test').count == 3
    assert 'f2test' in session.keys()
    assert session.clear('f2test')
    assert 'playground_f2test' not in sys.modules
    assert not session.clear('f2test')
    assert session.get('f2test', 'count') is None           # a fresh holder


def test_holder_survives_reimporting_the_module():
    session.set('f2survive', 'value', 42)
    del sys.modules['namo.session']
    import namo.session as again
    try:
        assert again.get('f2survive', 'value') == 42
    finally:
        again.clear('f2survive')


def test_log_keeps_recent_lines():
    session.log('warning', 'f2 test warning line')
    session.log('nonsense-level', 'f2 test info line')
    lines = session.recent_log()
    assert ('warning', 'Playground: f2 test warning line') in lines
    assert ('info', 'Playground: f2 test info line') in lines
    assert all(level == 'warning' for level, _t in session.recent_log('warning'))
    for i in range(session.LOG_KEEP + 10):
        session.log('debug', 'filler %d' % i)
    assert len(session.recent_log()) == session.LOG_KEEP

# -*- coding: utf-8 -*-
"""namo.textmatch: fuzzy matching, ranking, highlighting, and a speed check on both engines."""
import random
import time

import _compat

from namo import textmatch


def titles(results):
    return [item for _score, item in results]


def test_score_basics():
    assert textmatch.score('', 'anything') == 0.0
    assert textmatch.score('x', None) == 0.0
    assert textmatch.score('zzz', 'Section Plane') == 0.0
    assert textmatch.score('sec', 'Section Plane') > 0
    assert textmatch.score('SEC', 'section plane') == textmatch.score('sec', 'Section Plane') or \
        textmatch.score('SEC', 'section plane') > 0                 # case-insensitive
    assert textmatch.score('spe', 'Section Plane') > 0              # subsequence
    assert textmatch.score('eps', 'Section Plane') == 0.0           # order matters


def test_every_word_must_match():
    assert textmatch.score('sec pl', 'Section Plane') > 0
    assert textmatch.score('pl sec', 'Section Plane') > 0           # any order
    assert textmatch.score('sec zz', 'Section Plane') == 0.0


def test_word_starts_beat_mid_word_runs():
    ranked = titles(textmatch.rank('sp', ['Display', 'Section Plane', 'Spline']))
    assert ranked[0] == 'Spline'                                    # prefix
    assert ranked.index('Section Plane') < ranked.index('Display')  # acronym beats 'sp' in Display


def test_prefix_exact_and_length():
    ranked = titles(textmatch.rank('wall', ['Curtain Wall', 'Walls and floors', 'Wall', 'drywall']))
    assert ranked == ['Wall', 'Walls and floors', 'Curtain Wall', 'drywall']


def test_camel_case_humps():
    ranked = titles(textmatch.rank('qf', ['Quick Find', 'QuickFind', 'quiff', 'Equifax']))
    assert ranked[0] in ('Quick Find', 'QuickFind')
    assert ranked.index('QuickFind') < ranked.index('quiff')
    assert textmatch.score('qf', 'QuickFind') > textmatch.score('qf', 'Quickfind')


def test_separators_count_as_word_starts():
    a = textmatch.score('lev', 'Walls > Level 1')
    b = textmatch.score('lev', 'Walls > Clevis')
    assert a > b > 0
    assert textmatch.score('mm', 'Duct_Main_Mech') > textmatch.score('mm', 'Dummy')


def test_rank_is_stable_and_limited():
    items = ['alpha one', 'alpha two', 'alpha three', 'beta']
    ranked = textmatch.rank('alpha', items, limit=2)
    assert [s for s, _ in ranked][0] >= [s for s, _ in ranked][1]
    same = textmatch.rank('x', ['ax', 'bx', 'cx'], limit=None)
    assert titles(same) == ['ax', 'bx', 'cx']                      # equal scores keep input order
    assert textmatch.rank('', items, limit=2) == [(0.0, 'alpha one'), (0.0, 'alpha two')]
    assert len(textmatch.rank('', items, limit=None)) == 4
    assert textmatch.rank('zzz', items) == []


def test_rank_with_key_and_index():
    commands = [{'title': 'Clash Excel Report'}, {'title': 'Count by Property'},
                {'title': 'Clash Matrix'}, {'title': None}]
    ranked = textmatch.rank('clash mat', commands, key=lambda c: c['title'])
    assert [c['title'] for _s, c in ranked] == ['Clash Matrix']
    index = textmatch.Index(commands, key=lambda c: c['title'])
    assert len(index) == 4
    assert [c['title'] for _s, c in index.rank('cl')] == \
        [c['title'] for _s, c in textmatch.rank('cl', commands, key=lambda c: c['title'])]
    assert index.rank('', limit=1) == [(0.0, commands[0])]


def test_spans():
    assert textmatch.spans('secpl', 'Section Plane') == [(0, 3), (8, 10)]
    assert textmatch.spans('plane sec', 'Section Plane') == [(0, 3), (8, 13)]
    assert textmatch.spans('zz', 'Section Plane') == []
    assert textmatch.spans('', 'x') == []
    text = 'Walls > Basic Wall > Generic 200mm'
    for start, end in textmatch.spans('gen 200', text):
        assert 0 <= start < end <= len(text)


def test_scores_are_positive_for_any_match():
    rng = random.Random(7)
    letters = 'abcdefghij -_'
    for _ in range(300):
        text = ''.join(rng.choice(letters) for _ in range(rng.randint(1, 60)))
        query = ''.join(rng.choice('abcdefghij') for _ in range(rng.randint(1, 4)))
        s = textmatch.score(query, text)
        positions = textmatch.spans(query, text)
        assert (s > 0) == bool(positions), (query, text)


def _corpus(n):
    rng = random.Random(42)
    words = ['Walls', 'Basic Wall', 'Generic', 'Ducts', 'Rectangular Duct', 'Pipes', 'Copper',
             'Level', 'Floors', 'Concrete', 'Structural Framing', 'W-Wide Flange', 'Cable Tray',
             'Mechanical Equipment', 'AHU', 'Sprinkler', 'Door', 'Window', 'Furniture', 'Roof']
    out = []
    for i in range(n):
        parts = [rng.choice(words) for _ in range(3)]
        out.append('%s > %s > %s %dmm %05d' % (parts[0], parts[1], parts[2], rng.randint(50, 900), i))
    return out


def test_fast_path_scores_equal_the_general_path():
    items = _corpus(3000) + ['DUCT', 'Duct', 'duCt', 'AirHandler', 'a1b2', '12345', 'x', 'X',
                             'Walls>Basic', 'basic_wall', 'ABCdef', 'abcDEF', 'W12x40']
    queries = ['duct', 'd', 'wall', 'gen', 'ahu', '123', 'x', 'basic wall', 'ah', '00', 'w12',
               'bcd', 'cde', 'abc']
    fast = [[textmatch.score(q, t) for t in items] for q in queries]
    fast_spans = [textmatch.spans(q, t) for q in queries for t in items[-13:]]
    textmatch._FAST = False
    try:
        slow = [[textmatch.score(q, t) for t in items] for q in queries]
        slow_spans = [textmatch.spans(q, t) for q in queries for t in items[-13:]]
    finally:
        textmatch._FAST = True
    assert fast == slow
    assert fast_spans == slow_spans


def test_speed_20000_items():
    """The contract: 20,000 items x a short query well under 200 ms on IronPython. The
    asserted bound is generous so a busy machine does not fail the suite; the measured
    time is printed."""
    items = _corpus(20000)
    index = textmatch.Index(items)
    textmatch.rank('duct', items[:200])          # warm up (IronPython compiles on first call)
    timings = []
    for query in ('duct', 'gen wal', 'sprk', 'cpr 300', 'zzz'):
        started = time.time()
        result = textmatch.rank(query, items, limit=50)
        timings.append(time.time() - started)
        assert len(result) <= 50
    started = time.time()
    index.rank('duct')
    index_time = time.time() - started
    worst = max(timings)
    print('textmatch: 20,000 items, worst rank() %.0f ms, Index.rank %.0f ms (%s)'
          % (worst * 1000, index_time * 1000, 'IronPython' if _compat.IRONPYTHON else 'CPython'))
    assert worst < 1.5, 'rank() took %.2f s for 20,000 items' % worst
    assert index_time < 1.5

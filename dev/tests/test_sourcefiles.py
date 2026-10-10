# -*- coding: utf-8 -*-
"""namo.sourcefiles pure half: row texts, the status line, the selection model, lazy counting."""
import _compat

from namo import sourcefiles as sf


def _info(**kw):
    info = {'key': 'arch.nwc#g#0', 'name': 'ARCH.rvt', 'kind': 'RVT', 'units': 'Millimeters',
            'file': r'C:\M\ARCH.nwc', 'source': r'C:\M\ARCH.rvt', 'transformed': False}
    info.update(kw)
    return info


def test_row_texts_tags_only_problems():
    stale = {'status': 'Out of date', 'detail': 'ARCH.rvt was saved 2 days after ARCH.nwc.',
             'cache_time': None}
    texts = sf.row_texts(_info(), stale, {'items': 1234, 'done': True})
    assert texts['name'] == 'ARCH.rvt'
    assert texts['detail'] == u'RVT \u00b7 Millimeters \u00b7 1,234 items'
    assert texts['tag'] == 'Out of date' and texts['tag_level'] == 'warn'
    assert 'Loaded from: C:\\M\\ARCH.nwc' in texts['tooltip'] and 'saved 2 days' in texts['tooltip']
    texts = sf.row_texts(_info(), {'status': 'Current', 'detail': ''}, {'items': 10, 'done': False})
    assert texts['tag'] == '' and texts['detail'].endswith('counting')
    texts = sf.row_texts(_info(transformed=True), {'status': 'File not found'})
    assert texts['tag_level'] == 'fail' and 'Units and Transform' in texts['tooltip']
    texts = sf.row_texts(_info(kind='', units=''), None)
    assert texts['detail'] == ''


def test_status_text():
    assert sf.status_text([], no_document=True).startswith('Open or append')
    assert sf.status_text([]) == 'No models appended yet.'
    rows = [{'status': 'Out of date'}, {'status': 'File not found', 'hidden': True}, {'status': 'Current'}]
    assert sf.status_text(rows, counting=True) == \
        '3 models, 1 out of date, 1 not found, 1 hidden. Counting items.'
    assert sf.status_text([{'status': 'Current'}]) == '1 model.'


def test_selection_click_ctrl_shift():
    s = sf.Selection(['a', 'b', 'c', 'd'])
    s.click('b')
    assert s.ordered() == ['b']
    s.click('d', shift=True)
    assert s.ordered() == ['b', 'c', 'd']
    s.click('a', ctrl=True)
    assert s.ordered() == ['a', 'b', 'c', 'd']
    s.click('c', ctrl=True)
    assert s.ordered() == ['a', 'b', 'd']
    s.click('zzz')
    assert s.ordered() == ['a', 'b', 'd']
    s.set_keys(['d', 'b', 'x'])
    assert s.ordered() == ['d', 'b'] and s.anchor is None


def test_selection_keyboard_moves():
    s = sf.Selection(['a', 'b', 'c'])
    assert s.move(1) == 'a' and s.ordered() == ['a']
    assert s.move(1) == 'b'
    s.move(1, extend=True)
    assert s.ordered() == ['b', 'c']
    assert s.move(5) == 'c' and s.ordered() == ['c']
    assert s.move(-9) == 'a'
    s.select_all()
    assert s.ordered() == ['a', 'b', 'c']
    s.select(['c', 'nope'])
    assert s.ordered() == ['c'] and s.anchor == 'c'
    assert sf.Selection([]).move(1) is None


def test_count_job_slices_and_finishes():
    ticks = [0.0]

    def clock():
        ticks[0] += 1.0
        return ticks[0]

    job = sf.CountJob(range(10), has_geometry=lambda i: i % 2 == 0, clock=clock)
    assert job.advance(seconds=0.5, chunk=3) is False      # one chunk, then out of time
    assert job.items == 3 and not job.done
    while not job.advance(seconds=0.5, chunk=3):
        pass
    assert job.done and job.items == 10 and job.geometry == 5 and not job.failed
    assert job.advance() is True


def test_count_job_failure_is_contained():
    def broken():
        yield 1
        raise RuntimeError('model removed')
    job = sf.CountJob(broken())
    assert job.advance() is True and job.failed and job.items == 1


def test_cache_key():
    assert sf.cache_key({'key': 'k'}, {'cache_time': 12.4}) == 'k|12'
    assert sf.cache_key({'key': 'k'}, None) == 'k|'

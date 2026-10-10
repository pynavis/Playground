# -*- coding: utf-8 -*-
"""namo.movie: task kinds, item states, frame dates, frame planning, the player, the
ffmpeg command, and the exact restore (through fakes)."""
import contextlib
import datetime
import json
import os
import sys
import types

import _compat
from namo import movie

D = datetime.datetime


def test_task_kind_and_window():
    assert movie.task_kind('Construct') == 'construct'
    assert movie.task_kind('DEMOLISH') == 'demolish' and movie.task_kind('Removal') == 'demolish'
    assert movie.task_kind('Temporary works') == 'temporary'
    assert movie.task_kind('') == 'construct' and movie.task_kind(None) == 'construct'
    row = {'start': D(2026, 1, 1), 'end': D(2026, 1, 5), 'actual_start': D(2026, 1, 2)}
    assert movie.task_window(row) == (D(2026, 1, 1), D(2026, 1, 5))
    assert movie.task_window(row, 'actual') == (D(2026, 1, 2), D(2026, 1, 5))
    assert movie.task_window({'end': D(2026, 1, 3)}) == (D(2026, 1, 3), D(2026, 1, 3))
    assert movie.task_window({'start': D(2026, 1, 3), 'end': D(2026, 1, 1)}) == (D(2026, 1, 3), D(2026, 1, 3))
    assert movie.task_window({}) is None


def test_state_machine():
    build = [(D(2026, 1, 10), D(2026, 1, 20), 'construct')]
    assert movie.state_at(build, D(2026, 1, 9)) == 'hidden'
    assert movie.state_at(build, D(2026, 1, 10)) == 'building'
    assert movie.state_at(build, D(2026, 1, 19)) == 'building'
    assert movie.state_at(build, D(2026, 1, 20)) == 'normal'
    demo = [(D(2026, 1, 10), D(2026, 1, 20), 'demolish')]
    assert [movie.state_at(demo, d) for d in (D(2026, 1, 1), D(2026, 1, 15), D(2026, 1, 25))] == [
        'normal', 'demolishing', 'hidden']
    temp = [(D(2026, 1, 10), D(2026, 1, 20), 'temporary')]
    assert [movie.state_at(temp, d) for d in (D(2026, 1, 1), D(2026, 1, 15), D(2026, 1, 25))] == [
        'hidden', 'temporary', 'hidden']
    life = movie.normalise_schedule([(D(2026, 3, 1), D(2026, 3, 5), 'demolish'), build[0]])
    seq = [movie.state_at(life, d) for d in (D(2026, 1, 1), D(2026, 1, 12), D(2026, 2, 1),
                                               D(2026, 3, 2), D(2026, 3, 9))]
    assert seq == ['hidden', 'building', 'normal', 'demolishing', 'hidden']
    instant = [(D(2026, 1, 10), D(2026, 1, 10), 'construct')]
    assert movie.state_at(instant, D(2026, 1, 10)) == 'normal'
    assert movie.state_at([], D(2026, 1, 1)) == 'normal'


def test_frame_dates():
    dates_ = movie.frame_dates(D(2026, 1, 1), D(2026, 1, 20), 1, 'weeks')
    assert dates_ == [D(2026, 1, 1), D(2026, 1, 8), D(2026, 1, 15), D(2026, 1, 20)]
    assert movie.count_frames(D(2026, 1, 1), D(2026, 1, 20), 1, 'weeks') == 4
    assert movie.frame_dates(D(2026, 1, 1), D(2026, 1, 3)) == [D(2026, 1, 1), D(2026, 1, 2), D(2026, 1, 3)]
    assert movie.count_frames(D(2026, 1, 1), D(2026, 1, 3)) == 3
    assert movie.frame_dates(D(2026, 1, 1), D(2026, 1, 1)) == [D(2026, 1, 1)]
    assert movie.count_frames(D(2026, 1, 1), D(2026, 1, 1)) == 1
    _compat.raises(ValueError, movie.frame_dates, D(2026, 1, 2), D(2026, 1, 1))
    _compat.raises(ValueError, movie.frame_dates, None, D(2026, 1, 1))
    _compat.raises(ValueError, movie.frame_dates, D(2020, 1, 1), D(2030, 1, 1), 1, 'days')
    _compat.raises(ValueError, movie.frame_dates, D(2020, 1, 1), D(2020, 2, 1), 0)


def test_plan_frames_sends_deltas():
    schedules = {
        'col': [(D(2026, 1, 2), D(2026, 1, 4), 'construct')],
        'old': [(D(2026, 1, 3), D(2026, 1, 4), 'demolish')],
        'prop': [(D(2026, 1, 1), D(2026, 1, 3), 'temporary')],
    }
    frames = list(movie.plan_frames(schedules, movie.frame_dates(D(2026, 1, 1), D(2026, 1, 4))))
    assert frames[0][2] == {'hidden': ['col'], 'normal': ['old'], 'temporary': ['prop']}
    assert frames[1][2] == {'building': ['col']}
    assert frames[2][2] == {'demolishing': ['old'], 'hidden': ['prop']}
    assert frames[3][2] == {'normal': ['col'], 'hidden': ['old']}
    assert frames[3][3]['normal'] == 1 and frames[3][3]['hidden'] == 2


def test_stamp_lines_and_active():
    windows = [(D(2026, 1, 1), D(2026, 1, 5), 'construct', 'Slab'),
               (D(2026, 1, 2), D(2026, 1, 9), 'construct', 'Columns'),
               (D(2026, 1, 3), D(2026, 1, 4), 'construct', 'Beams'),
               (D(2026, 1, 3), D(2026, 1, 9), 'construct', 'Walls')]
    active = movie.active_tasks(windows, D(2026, 1, 3))
    assert active == ['Slab', 'Columns', 'Beams', 'Walls']
    head, detail = movie.stamp_lines(D(2026, 10, 5), active)
    assert head == '2026-10-05  Mon'
    assert detail == '4 tasks under way: Beams, Columns, Slab and 1 more'
    assert movie.stamp_lines(D(2026, 10, 5), [], weekday=False) == ('2026-10-05', 'No task under way')
    assert movie.stamp_lines(D(2026, 10, 5), ['A'])[1] == '1 task under way: A'


def test_player_html():
    frames = [{'file': 'frame_0001.png', 'date': '2026-10-05', 'detail': 'x </script> y'},
              {'file': 'frame_0002.png', 'date': '2026-10-06'}]
    html = movie.player_html('Tower <A>', frames, 'Planned dates', fps=8)
    assert '<title>Tower &lt;A&gt;</title>' in html
    assert 'src="frame_0001.png"' in html and 'max="1"' in html
    assert '<option value="8" selected>8 fps</option>' in html
    assert '</script> y' not in html and '<\\/script>' in html
    payload = html.split('var frames=')[1].split(';var i=0')[0]
    assert [f['file'] for f in json.loads(payload)] == ['frame_0001.png', 'frame_0002.png']
    _compat.raises(ValueError, movie.player_html, 'x', [])


def test_ffmpeg_command():
    command = movie.ffmpeg_command('ffmpeg.exe', 'C:\\out', 6, 'C:\\out\\movie.mp4')
    assert command[0] == 'ffmpeg.exe' and command[command.index('-framerate') + 1] == '6'
    assert command[command.index('-i') + 1] == os.path.join('C:\\out', 'frame_%04d.png')
    assert command[-1] == 'C:\\out\\movie.mp4' and 'yuv420p' in command


# ---- API half -----------------------------------------------------------------------------------


class Item(object):
    def __init__(self, name, hidden=False, children=()):
        self.name = name
        self.IsHidden = hidden
        self.children = list(children)

    @property
    def DescendantsAndSelf(self):
        out = [self]
        for child in self.children:
            out.extend(child.DescendantsAndSelf)
        return out

    def __repr__(self):
        return self.name


class Models(object):
    def __init__(self, roots):
        self.roots = roots
        self.calls = []

    @property
    def Count(self):
        return len(self.roots)

    def __getitem__(self, index):
        return types.SimpleNamespace(RootItem=self.roots[index])

    def SetHidden(self, coll, value):
        self.calls.append(('hidden', sorted(i.name for i in coll), value))
        for item in coll:
            item.IsHidden = value

    def ResetAllHidden(self):
        self.calls.append(('reset_hidden',))
        for root in self.roots:
            for item in root.DescendantsAndSelf:
                item.IsHidden = False

    def ResetTemporaryMaterials(self, coll):
        self.calls.append(('reset_temp', sorted(i.name for i in coll)))

    def OverrideTemporaryColor(self, coll, color):
        self.calls.append(('tint', sorted(i.name for i in coll), color))


class Viewpoints(object):
    def __init__(self):
        self.copied = []

    def CreateCopy(self):
        return 'camera-before'

    def CopyFrom(self, value):
        self.copied.append(value)


@contextlib.contextmanager
def fake_api(doc):
    names = ('pynavis', 'pynavis._api')
    saved = dict((n, sys.modules.get(n)) for n in names)
    package = types.ModuleType('pynavis')
    package.__path__ = []
    api = types.ModuleType('pynavis._api')
    api.Api = types.SimpleNamespace(ModelItem=Item, ModelItemCollection=_Coll,
                                    Color=lambda r, g, b: (round(r, 3), round(g, 3), round(b, 3)))
    api.Application = types.SimpleNamespace(ActiveDocument=doc)
    package._api = api
    sys.modules['pynavis'] = package
    sys.modules['pynavis._api'] = api
    try:
        yield
    finally:
        for name in names:
            if saved[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved[name]


class _Coll(list):
    def Add(self, item):
        self.append(item)

    @property
    def Count(self):
        return len(self)


def _scene():
    a, b, c = Item('a'), Item('b', hidden=True), Item('c')
    sub = Item('sub', hidden=True, children=[Item('deep', hidden=True)])
    root = Item('root', children=[a, b, c, sub])
    doc = types.SimpleNamespace(Models=Models([root]), CurrentViewpoint=Viewpoints())
    return doc, a, b, c


def test_hidden_items_and_exact_restore_on_error():
    doc, a, b, c = _scene()
    with fake_api(doc):
        before = movie.hidden_items(doc)
        assert sorted(i.name for i in before) == ['b', 'deep', 'sub']
        try:
            with movie.SceneKeeper(doc, before) as keeper:
                movie.apply_changes(doc, {'hidden': [a], 'building': [b], 'normal': [c]}, keeper)
                assert a.IsHidden and not b.IsHidden
                assert keeper.tinted == set([b])
                raise RuntimeError('render failed')
        except RuntimeError:
            pass
        assert not a.IsHidden and b.IsHidden and not c.IsHidden
        assert doc.CurrentViewpoint.copied == ['camera-before']
        calls = doc.Models.calls
        assert ('reset_hidden',) in calls
        assert calls[-2] == ('reset_temp', ['b']) or ('reset_temp', ['b']) in calls
        assert ('hidden', ['b', 'deep', 'sub'], True) in calls


def test_apply_changes_order_and_untint():
    doc, a, b, c = _scene()
    with fake_api(doc):
        keeper = movie.SceneKeeper(doc, [])
        movie.apply_changes(doc, {'building': [a], 'temporary': [c]}, keeper)
        movie.apply_changes(doc, {'normal': [a], 'hidden': [c]}, keeper)
        calls = doc.Models.calls
        assert calls[0] == ('hidden', ['a', 'c'], False)
        assert calls[1][0] == 'tint' and calls[1][1] == ['a']
        assert calls[2][0] == 'tint' and calls[2][1] == ['c']
        assert calls[3] == ('hidden', ['a'], False)
        assert calls[4] == ('reset_temp', ['a', 'c'])
        assert calls[5] == ('hidden', ['c'], True)
        assert keeper.tinted == set()


def test_stamp_draws_on_a_real_bitmap():
    _compat.require_ironpython('System.Drawing')
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Bitmap
    bitmap = Bitmap(640, 360)
    movie.stamp(bitmap, '2026-10-05  Mon', '2 tasks under way: A, B', 0.5)
    left = bitmap.GetPixel(12, 340)
    bar = bitmap.GetPixel(100, 359)
    assert (left.R, left.G, left.B) == (32, 32, 32)
    assert (bar.R, bar.G, bar.B) == (0, 120, 212)
    end = bitmap.GetPixel(600, 359)
    assert (end.R, end.G, end.B) == (64, 64, 64)
    bitmap.Dispose()

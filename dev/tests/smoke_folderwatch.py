# -*- coding: utf-8 -*-
"""Folder Watch under IronPython + WPF: start/stop with a real DispatcherTimer against a
fake document, polls over real files (a change reported after two settled polls, a
Navisworks refresh rebasing), the notification window built and rendered off screen."""
import _compat

_compat.require_ironpython()

import io  # noqa: E402
import os  # noqa: E402

import clr  # noqa: E402

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

import test_items as nav  # noqa: E402

from namo import folderwatch as fw  # noqa: E402
from namo import session  # noqa: E402


class FakeEvent(object):
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)
        return self

    def fire(self):
        for handler in list(self.handlers):
            handler(None, None)


class _Model(object):
    def __init__(self, path, source=''):
        self.FileName = path
        self.SourceFileName = source
        self.Units = 'Meters'
        self.Creator = ''
        self.Guid = 'g-' + os.path.basename(path)
        self.RootItem = nav.ModelItem(os.path.basename(path))
        self.Transform = nav._Ns(IsIdentity=lambda: True)


def _write(path, text, stamp):
    with io.open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    os.utime(path, (stamp, stamp))


def _setup():
    folder = _compat.tmpdir('smoke_folderwatch')
    arch = os.path.join(folder, 'ARCH.nwc')
    mep = os.path.join(folder, 'MEP.nwc')
    _write(arch, u'a', 1000000000)
    _write(mep, u'm', 1000000000)
    doc = nav.Document([_Model(arch), _Model(mep)])
    doc.FilesUpdated = FakeEvent()
    doc.updates = []
    doc.UpdateFiles = lambda: doc.updates.append(1) or True
    return folder, arch, mep, doc


def test_start_poll_notice_refresh_stop():
    session.clear(fw.HOLDER)
    folder, arch, mep, doc = _setup()
    shown = []
    original = fw.show_notice
    fw.show_notice = lambda changed: shown.append(list(changed))
    try:
        with nav.FakeNav(doc):
            result = fw.start({'interval': 10})
            held = fw.holder()
            assert result['ok'] and fw.is_on() and held.timer is not None
            assert 'Watching 2 model files in 1 folder' in result['detail']
            assert len(doc.FilesUpdated.handlers) == 1
            fw.tick()
            assert shown == []
            _write(arch, u'aa', 1000000500)          # changed on disk
            fw.tick()
            assert shown == []                        # first sighting: pending
            fw.tick()
            assert [k for k, n in shown[0]] == [held.files[0][1]]
            assert shown[0][0][1] == 'ARCH.nwc'
            # Navisworks refreshes on its own: FilesUpdated rebases, nothing pending
            doc.FilesUpdated.fire()
            assert held.changed == []
            _write(mep, u'mm', 1000000600)
            fw.tick()
            fw.tick()
            assert [n for k, n in shown[-1]] == ['MEP.nwc']
            fw.refresh_now()
            assert doc.updates == [1] and held.changed == []
            fw.stop(save=False)
            assert not fw.is_on() and held.timer is None
            assert doc.FilesUpdated.handlers == []
    finally:
        fw.show_notice = original
        session.clear(fw.HOLDER)


def test_notice_window_builds_and_renders():
    clicks = []
    changed = [('a#0', 'ARCH.rvt'), ('m#0', 'MEP.nwc'), ('s#0', 'STR.nwc')]
    win = fw.build_notice(changed, lambda: clicks.append('refresh'), lambda: clicks.append('later'),
                          lambda: clicks.append('show'))
    parts = win.Tag
    assert parts['title'] == '3 models updated' and parts['lines'] == ['ARCH.rvt', 'MEP.nwc', 'STR.nwc']
    from System.Windows import RoutedEventArgs
    from System.Windows.Controls.Primitives import ButtonBase
    for name in ('refresh', 'later', 'show'):
        parts[name].RaiseEvent(RoutedEventArgs(ButtonBase.ClickEvent))
    assert clicks == ['refresh', 'later', 'show']
    from System.Windows import Rect, Size
    from System.Windows.Media import PixelFormats
    from System.Windows.Media.Imaging import BitmapFrame, PngBitmapEncoder, RenderTargetBitmap
    from System.IO import File
    content = win.Content
    win.Content = None
    content.Measure(Size(360, 400))
    height = content.DesiredSize.Height
    content.Arrange(Rect(0, 0, 360, height))
    bitmap = RenderTargetBitmap(360, int(height), 96.0, 96.0, PixelFormats.Pbgra32)
    from System.Windows.Controls import Border
    frame = Border()
    frame.Background = win.Background
    frame.Child = content
    frame.Measure(Size(360, height))
    frame.Arrange(Rect(0, 0, 360, height))
    bitmap.Render(frame)
    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(bitmap))
    path = os.path.join(_compat.tmpdir('smoke_folderwatch_png'), 'notice.png')
    stream = File.Create(path)
    try:
        encoder.Save(stream)
    finally:
        stream.Close()
    assert os.path.getsize(path) > 1000

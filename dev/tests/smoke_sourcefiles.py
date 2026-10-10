# -*- coding: utf-8 -*-
"""Source Files pane under IronPython + WPF: built from its real pane.xaml against a fake
document with live events, driven (select, keyboard, visibility, isolate, lazy counts,
rebuild on CollectionChanged, Reload detach) and rendered to PNG off screen."""
import _compat

_compat.require_ironpython()

import io  # noqa: E402
import os  # noqa: E402

import clr  # noqa: E402

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

import test_items as nav  # noqa: E402

from namo import sourcefiles  # noqa: E402

PANE = os.path.join(_compat.ROOT, 'Playground.extension', 'Project.tab', 'Models.panel',
                    'Source_Files.dockpane', 'pane.xaml')


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


class FakePane(object):
    def __init__(self, root):
        self.Content = root
        self.Visible = True
        self.Title = 'Source Files'
        self.BundleKey = sourcefiles.PANE_KEY

    def Find(self, name):
        return self.Content.FindName(name)


class _Model(object):
    def __init__(self, path, root, units='Millimeters', source=None):
        self.FileName = path
        self.SourceFileName = source if source is not None else path.replace('.nwc', '.rvt')
        self.Units = units
        self.Creator = 'Revit'
        self.Guid = 'guid-' + os.path.basename(path).lower()
        self.RootItem = root
        self.Transform = nav._Ns(IsIdentity=lambda: True)


def _tree(name, count):
    children = [nav.ModelItem('%s %d' % (name, i), geometry=True, box=((i, 0, 0), (i + 1, 1, 1)))
                for i in range(count)]
    return nav.ModelItem(name, children)


def _load_pane():
    from System.Windows.Markup import XamlReader
    with io.open(PANE, encoding='utf-8') as handle:
        root = XamlReader.Parse(handle.read())
    return FakePane(root)


def _doc():
    folder = _compat.tmpdir('smoke_sourcefiles')
    cache = os.path.join(folder, 'ARCH.nwc')
    source = os.path.join(folder, 'ARCH.rvt')
    for path, stamp in ((cache, 1000000000), (source, 1000086400)):
        with io.open(path, 'w', encoding='utf-8') as handle:
            handle.write(u'x')
        os.utime(path, (stamp, stamp))
    models = [_Model(cache, _tree('ARCH.nwc', 30), source=source),
              _Model(os.path.join(folder, 'MEP.nwc'), _tree('MEP.nwc', 12), units='Feet'),
              _Model(os.path.join(folder, 'STR.nwc'), _tree('STR.nwc', 5), source='')]
    doc = nav.Document(models)
    doc.Models.CollectionChanged = FakeEvent()
    doc.FilesUpdated = FakeEvent()
    doc.UpdateFiles = lambda: False
    return doc


def _render(element, path, width=320, height=420):
    from System.Windows import Size, Rect
    from System.Windows.Media import PixelFormats
    from System.Windows.Media.Imaging import PngBitmapEncoder, RenderTargetBitmap, BitmapFrame
    from System.IO import File
    element.Measure(Size(width, height))
    element.Arrange(Rect(0, 0, width, height))
    element.UpdateLayout()
    bitmap = RenderTargetBitmap(width, height, 96.0, 96.0, PixelFormats.Pbgra32)
    bitmap.Render(element)
    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(bitmap))
    stream = File.Create(path)
    try:
        encoder.Save(stream)
    finally:
        stream.Close()


def _view(doc, pane):
    sourcefiles.attach(pane, None)
    selector = sourcefiles.holder().select_model
    return selector.__self__


def test_pane_builds_rows_and_status():
    doc = _doc()
    with nav.FakeNav(doc) as fake:
        import sys
        sys.modules['pynavis._api'].Application.ActiveDocumentChanged = FakeEvent()
        pane = _load_pane()
        view = _view(doc, pane)
        try:
            assert pane.Find('Rows').Children.Count == 3
            assert view.toolbar.Children.Count == 7
            texts = sourcefiles.row_texts(view.infos[0], view.stale[view.infos[0]['key']])
            assert texts['tag'] == 'Out of date' and texts['name'] == 'ARCH.rvt'
            assert view.stale[view.infos[2]['key']]['status'] == 'File not found'
            assert '3 models' in pane.Find('Status').Text and 'out of date' in pane.Find('Status').Text
            # no selection: selection-bound buttons are disabled
            assert not view.buttons['isolate'].IsEnabled and view.buttons['show'].IsEnabled
            assert len(doc.Models.CollectionChanged.handlers) == 1
        finally:
            view.detach()
        assert doc.Models.CollectionChanged.handlers == []


def test_pane_selection_keyboard_visibility_isolate():
    doc = _doc()
    with nav.FakeNav(doc):
        import sys
        sys.modules['pynavis._api'].Application.ActiveDocumentChanged = FakeEvent()
        pane = _load_pane()
        view = _view(doc, pane)
        try:
            keys = [i['key'] for i in view.infos]
            view.selection.click(keys[0])
            view.selection.click(keys[2], shift=True)
            view._paint_selection()
            assert view.selection.ordered() == keys
            assert view.buttons['isolate'].IsEnabled
            view.selection.click(keys[1])
            view._paint_selection()
            view.toggle_visible([keys[1]], False)
            assert doc.Models.calls[-1][0] == 'hidden' and doc.Models.calls[-1][2] is True
            view.do_isolate()
            assert doc.transactions[-1] == 'Isolate models'
            view.select_key(keys[2])
            assert view.selection.ordered() == [keys[2]]
            # lazy counting finishes over a few ticks and lands in the row text
            for _ in range(20):
                view._advance_counts()
                if not view.jobs:
                    break
            assert not view.jobs
            detail = view.row_views[keys[0]]['detail'].Text
            assert '31 items' in detail, detail
            light = os.path.join(_compat.tmpdir('smoke_sourcefiles_png'), 'source_files.png')
            _render(pane.Content, light)
            assert os.path.getsize(light) > 1000
        finally:
            view.detach()


def test_pane_rebuilds_on_collection_changed_and_reload_detaches():
    doc = _doc()
    with nav.FakeNav(doc):
        import sys
        app = sys.modules['pynavis._api'].Application
        app.ActiveDocumentChanged = FakeEvent()
        pane = _load_pane()
        view = _view(doc, pane)
        doc.Models.models.append(_Model(r'C:\nowhere\NEW.nwc', _tree('NEW.nwc', 2)))
        view.rebuild()
        assert pane.Find('Rows').Children.Count == 4
        # Reload: a second attach detaches the first view
        pane2 = _load_pane()
        view2 = _view(doc, pane2)
        try:
            assert view.detached and not view2.detached
            assert len(app.ActiveDocumentChanged.handlers) == 1
            assert len(doc.Models.CollectionChanged.handlers) == 1
        finally:
            view2.detach()

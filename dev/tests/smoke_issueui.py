# -*- coding: utf-8 -*-
"""The Issues pane under IronPython + WPF: pane.xaml loaded the way pyNavis loads it,
namo.issueui mounted on it with sample issues through a fake environment, driven through
selection, editing, saving, new-from-view, comments, pins, delete and a Reload re-mount,
then rendered off screen to PNGs in the test's temp folder for a visual check."""
import _compat

_compat.require_ironpython()

import datetime  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402

import clr  # noqa: E402

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from namo import issuestore, issueui, paths, png, session  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PANE = os.path.join(_compat.ROOT, 'Playground.extension', 'Coordinate.tab', 'Issues.panel',
                    'Issues.dockpane', 'pane.xaml')
DOC = r'C:\Projects\Tower\Coordination.nwf'


class FakeDoc(object):
    def __init__(self, path):
        self.FileName = path


class Hit(object):
    def __init__(self, point):
        self.point = point
        self.item = None


def _image(folder, name, shade):
    path = os.path.join(folder, name)
    width, height = 64, 36
    pixels = []
    for y in range(height):
        for x in range(width):
            pixels.extend([shade, 120 + (x % 60), 200 - y])
    png.write(path, width, height, pixels, 'RGB')
    return path


class FakeEnv(object):
    def __init__(self, folder):
        self.folder = folder
        self.doc = FakeDoc(DOC)
        self.toasts = []
        self.opened = []
        self.went = []
        self.pins = 0
        self.pane = None
        self.picks = 0
        self.confirm_answer = True
        self.shots = 0

    def document(self):
        return self.doc

    def has_model(self, doc):
        return doc is not None

    def store(self, doc):
        return issuestore.IssueStore(doc.FileName, doc=None)

    def capture(self, doc, image=True, model_items=None):
        self.shots += 1
        return {'camera': {'position': [1.0, 2.0, 3.0], 'rotation': [0, 0, 0, 1], 'direction': [0, 0, -1],
                           'up': [0, 1, 0], 'projection': 'persp', 'height_field': 0.8},
                'camera_units': 'Feet',
                'elements': [{'entry': {'m': 'M.nwc', 'i': 0, 'p': '0/1'}, 'name': 'Duct 600x400',
                              'model': 'M.nwc', 'element_id': '1234', 'ifc_guid': None}],
                'element_total': 1,
                'location': {'point': [10.0, 20.0, 3.0], 'units': 'Feet', 'level': 'Level 2',
                             'grid': 'C-4'},
                'image': _image(self.folder, 'capture-%d.png' % self.shots, 90) if image else None,
                'image_error': None}

    def go_to(self, issue, doc):
        self.went.append(issue['id'])
        return {'moved': bool(issue.get('camera')), 'selected': len(issue.get('elements') or []),
                'missing': 0}

    def select(self, issue, doc):
        self.went.append('select ' + issue['id'])
        return {'moved': False, 'selected': len(issue.get('elements') or []), 'missing': 0}

    def pick(self, prompt, doc=None):
        self.picks += 1
        if self.pane is not None:
            # The pick keeps the window alive: a second Set pin click while it waits
            # must not start another pick.
            assert self.pane.picking and not self.pane.pin_button.IsEnabled
            self.pane.set_pin()
        return Hit((5.0, 6.0, 7.0))

    def location(self, point, doc):
        return {'point': list(point), 'units': 'Feet', 'level': 'Level 3', 'grid': 'B-2'}

    def screenshot(self, doc):
        return _image(self.folder, 'screen-%d.png' % len(os.listdir(self.folder)), 160)

    def confirm(self, message, title):
        return self.confirm_answer

    def toast(self, level, message, detail=None):
        self.toasts.append((level, message, detail))

    def open_path(self, path):
        self.opened.append(path)

    def redraw_pins(self, doc):
        self.pins += 1

    def watch(self, changed, log):
        return lambda: None


class FakePane(object):
    def __init__(self, root):
        self.Content = root

    def Find(self, name):
        return self.Content.FindName(name)


def _load_pane():
    from System.Windows.Markup import XamlReader
    with io.open(PANE, encoding='utf-8') as handle:
        return XamlReader.Parse(handle.read())


def _seed(folder):
    s = issuestore.IssueStore(DOC)
    now = datetime.datetime.now().replace(microsecond=0)
    rows = [
        ({'title': 'Duct clashes with transfer beam at gridline C', 'type': 'RFI', 'priority': 'Critical',
          'trade': 'Mechanical', 'assignee': 'Jane Smith', 'due': (now - datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
          'description': 'The 600x400 supply duct runs through the beam web.', 'labels': ['L2'],
          'location': {'point': [1, 2, 3], 'units': 'Feet', 'level': 'Level 2', 'grid': 'C-4'}}, 'RFI-'),
        ({'title': 'Hold: shaft opening not confirmed', 'type': 'Hold', 'priority': 'High',
          'trade': 'Structure', 'due': (now + datetime.timedelta(days=2)).strftime('%Y-%m-%d')}, 'HOLD-'),
        ({'title': 'Check sprinkler head clearance in corridor', 'type': 'Verify', 'priority': 'Normal',
          'trade': 'Fire Protection', 'status': 'In progress', 'assignee': 'Ken'}, 'VER-'),
        ({'title': 'Cable tray route agreed', 'type': 'Issue', 'priority': 'Low', 'trade': 'Electrical',
          'status': 'Resolved'}, 'ISS-'),
        ({'title': 'Old question, not an issue', 'status': 'Void'}, 'ISS-'),
    ]
    made = []
    for fields, prefix in rows:
        made.append(s.create(fields, prefix=prefix, user='amol'))
    s.add_comment(made[0]['id'], 'Mechanical to reroute below the beam.', user='jane')
    s.update(made[0]['id'], {'status': 'In progress'}, note='Reroute started', user='jane')
    s.add_image(made[0]['id'], _image(folder, 'seed.png', 30), kind='snapshot', move=True)
    return s, made


def _setup(name):
    folder = _compat.tmpdir('smoke-issueui-' + name)
    previous = paths.redirect(folder)
    return folder, previous


def _pump():
    """Runs queued dispatcher work (the DataGrid sizes star columns there)."""
    from System import Action
    from System.Windows.Threading import Dispatcher, DispatcherFrame, DispatcherPriority
    frame = DispatcherFrame()
    Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.Background,
                                             Action(lambda: setattr(frame, 'Continue', False)))
    Dispatcher.PushFrame(frame)


def _render(root, path, width=440.0, height=1100.0):
    from System.Windows import Rect, Size
    from System.Windows.Media import PixelFormats
    from System.Windows.Media.Imaging import BitmapFrame, PngBitmapEncoder, RenderTargetBitmap
    for _ in range(2):
        root.Measure(Size(width, height))
        root.Arrange(Rect(0.0, 0.0, width, height))
        root.UpdateLayout()
        _pump()
    bitmap = RenderTargetBitmap(int(width), int(height), 96.0, 96.0, PixelFormats.Pbgra32)
    bitmap.Render(root)
    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(bitmap))
    from System.IO import File
    stream = File.Create(path)
    try:
        encoder.Save(stream)
    finally:
        stream.Close()
    return path


def test_pane_builds_and_lists():
    folder, previous = _setup('build')
    try:
        _seed(folder)
        env = FakeEnv(folder)
        root = _load_pane()
        pane = issueui.mount(FakePane(root), env=env)
        assert pane.table.Rows.Count == 3                       # default filter: open + in progress
        ids = [str(pane.table.Rows[i]['id']) for i in range(pane.table.Rows.Count)]
        assert ids[0] == 'RFI-001'                               # most urgent open issue first
        assert 'ISS-002' not in ids                              # void hidden
        assert '3 open' in pane.status.Text and 'Local data' in pane.status.Text
        # status filter: all
        pane.status_combo.SelectedIndex = 1
        assert pane.table.Rows.Count == 5
        pane.search_box.Text = 'sprinkler'
        pane.apply_filter()
        assert pane.table.Rows.Count == 1
        pane.search_box.Text = ''
        pane.apply_filter()
        # trades offered from the register and the configuration
        labels = [label for label, _v in pane.trade_combo.Tag.pairs]
        assert labels[0] == 'All trades' and 'Mechanical' in labels and 'No trade' in labels
    finally:
        paths.redirect(previous)


def test_select_edit_save_comment_and_actions():
    folder, previous = _setup('edit')
    try:
        s, made = _seed(folder)
        env = FakeEnv(folder)
        root = _load_pane()
        pane = issueui.mount(FakePane(root), env=env)
        rfi = made[0]['id']
        assert pane._select_row(rfi)
        pane._selection_changed(None, None)
        assert pane.current['id'] == rfi and pane.heading.Text == rfi
        assert pane.chip_text.Text == 'In progress'
        assert pane.images.Children.Count == 1
        assert pane.comments.Children.Count == 2
        assert not pane.save_button.IsEnabled
        pane.title_box.Text = 'Duct clashes with beam (rerouting)'
        pane.due_box.Text = 'not a date'
        assert pane.dirty and pane.save_button.IsEnabled
        assert pane.due_note.Text.startswith('Not a date')
        assert pane.save() is False                             # invalid due: kept, toast
        assert env.toasts[-1][0] == 'error'
        pane.due_box.Text = '2030-01-15'
        assert pane.save() is True
        stored = s.get(rfi)
        assert stored['title'] == 'Duct clashes with beam (rerouting)' and stored['due'] == '2030-01-15'
        assert not pane.dirty
        pane.comment_box.Text = 'Coordinated in the meeting.'
        pane.add_comment()
        assert s.get(rfi)['comments'][-1]['text'] == 'Coordinated in the meeting.'
        pane.go_to()
        assert env.went[-1] == rfi
        pane.select_elements()
        assert env.went[-1] == 'select ' + rfi
        env.pane = pane
        pane.set_pin()
        env.pane = None
        assert s.get(rfi)['location']['grid'] == 'B-2' and env.pins == 1
        assert env.picks == 1 and not pane.picking and pane.pin_button.IsEnabled
        pane.add_screenshot()
        assert len(s.get(rfi)['images']) == 2
        pane.update_view()
        assert [i['kind'] for i in s.get(rfi)['images']].count('snapshot') == 1
        # moving to another issue with unsaved edits saves them first
        pane.title_box.Text = 'Edited then moved away'
        hold = made[1]['id']
        pane._select_row(hold)
        pane._selection_changed(None, None)
        assert s.get(rfi)['title'] == 'Edited then moved away'
        assert pane.current['id'] == hold
        env.confirm_answer = False
        pane.delete()
        assert s.get(hold) is not None
        env.confirm_answer = True
        pane.delete()
        assert s.get(hold) is None and pane.current is None
    finally:
        paths.redirect(previous)


def test_new_from_view_and_session_events():
    folder, previous = _setup('new')
    try:
        s, made = _seed(folder)
        env = FakeEnv(folder)
        root = _load_pane()
        pane = issueui.mount(FakePane(root), env=env)
        pane.type_combo.SelectedIndex = [v for _l, v in pane.type_combo.Tag.pairs].index('RFI')
        pane.new_from_view()
        new_id = pane.current['id']
        assert new_id == 'RFI-002'
        issue = s.get(new_id)
        assert issue['title'] == 'RFI 002' and issue['type'] == 'RFI'
        assert issue['camera_units'] == 'Feet' and issue['location']['grid'] == 'C-4'
        assert issue['images'][0]['kind'] == 'snapshot'
        assert env.toasts[-1][1] == 'RFI-002 created'
        # another tool writes: the pane hears it (debounced) and lists it
        s.create({'title': 'Raised by Clash to Issues', 'type': 'Clash'}, prefix='CLA-', user='bot')
        pane.debounce.flush()
        ids = [str(pane.table.Rows[i]['id']) for i in range(pane.table.Rows.Count)]
        assert 'CLA-001' in ids
        assert issuestore.listeners().count(issueui.EVENT_KEY) == 1
    finally:
        paths.redirect(previous)


def test_empty_states_and_reload_remount():
    folder, previous = _setup('empty')
    try:
        env = FakeEnv(folder)
        env.doc = FakeDoc('')
        root = _load_pane()
        pane = issueui.mount(FakePane(root), env=env)
        from System.Windows import Visibility
        assert pane.empty.Visibility == Visibility.Visible
        assert root.FindName('EmptyTitle').Text == 'Save the model first'
        assert not pane.new_button.IsEnabled
        pane.new_from_view()
        assert env.toasts[-1][1] == 'Save the model first'
        env.doc = None
        pane.refresh()
        assert root.FindName('EmptyTitle').Text == 'No model open'
        env.doc = FakeDoc(DOC)
        pane.refresh()
        assert root.FindName('EmptyTitle').Text == 'No issues yet'
        # Reload: the script runs again against fresh controls; the old build detaches
        root2 = _load_pane()
        pane2 = issueui.mount(FakePane(root2), env=env)
        assert session.holder(issueui.HOLDER).pane is pane2
        assert pane.detachers == []
        assert issuestore.listeners().count(issueui.EVENT_KEY) == 1
    finally:
        paths.redirect(previous)


def test_render_pane_png():
    folder, previous = _setup('render')
    try:
        s, made = _seed(folder)
        env = FakeEnv(folder)
        root = _load_pane()
        pane = issueui.mount(FakePane(root), env=env)
        pane._select_row(made[0]['id'])
        pane._selection_changed(None, None)
        out = os.path.join(folder, 'issues-pane.png')
        _render(root, out)
        data = open(out, 'rb').read()
        assert png.size(data) == (440, 1100)
        scroll = root.FindName('DetailScroll')
        scroll.ScrollToVerticalOffset(520.0)
        root.UpdateLayout()
        _render(root, os.path.join(folder, 'issues-pane-lower.png'))
        wide = _load_pane()
        wide_pane = issueui.mount(FakePane(wide), env=env)
        wide_pane._fit_columns(800.0)
        _render(wide, os.path.join(folder, 'issues-pane-wide.png'), width=820.0, height=520.0)
    finally:
        paths.redirect(previous)


def test_document_switch_saves_pending_edit():
    folder, previous = _setup('switch')
    try:
        s, made = _seed(folder)
        env = FakeEnv(folder)
        root = _load_pane()
        pane = issueui.mount(FakePane(root), env=env)
        rfi = made[0]['id']
        pane._select_row(rfi)
        pane._selection_changed(None, None)
        pane.title_box.Text = 'Edited before the model changed'
        assert pane.dirty
        other = r'C:\Projects\Tower\Other.nwf'
        issuestore.IssueStore(other).create({'title': 'Same id, other model'}, prefix='RFI-')
        env.doc = FakeDoc(other)
        pane.refresh()
        assert s.get(rfi)['title'] == 'Edited before the model changed'
        assert issuestore.IssueStore(other).get(rfi)['title'] == 'Same id, other model'
        assert pane.current is None and not pane.dirty
        assert [str(pane.table.Rows[i]['id']) for i in range(pane.table.Rows.Count)] == ['RFI-001']
    finally:
        paths.redirect(previous)

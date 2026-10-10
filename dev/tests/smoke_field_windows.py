# -*- coding: utf-8 -*-
"""Photo Browser and Field Checklists windows under IronPython + WPF, with in-memory
stores and real thumbnail files; never shown."""
import copy
import os

import _compat

_compat.require_ironpython()

from namo import checklists, field_checklistwin, field_photobrowser, photopins, png  # noqa: E402


class MemoryStore(object):
    """The RecordStore surface the windows use."""

    def __init__(self, folder=None, records=None):
        self.folder = folder
        self.note = None
        self.records = dict((r['id'], copy.deepcopy(r)) for r in records or [])
        self.puts = []

    def list(self):
        return [copy.deepcopy(self.records[k]) for k in sorted(self.records)]

    def get(self, record_id):
        record = self.records.get(record_id)
        return copy.deepcopy(record) if record else None

    def put(self, record):
        self.records[record['id']] = copy.deepcopy(record)
        self.puts.append(record['id'])
        return record

    def delete(self, record_id):
        return self.records.pop(record_id, None) is not None


class Toasts(object):
    def __enter__(self):
        from pynavis import toast
        self.module = toast
        self.saved = dict((name, getattr(toast, name)) for name in ('success', 'info', 'warning', 'error'))
        self.calls = []
        for name in self.saved:
            setattr(toast, name, self._make(name))
        return self

    def _make(self, name):
        def record(message, detail=None):
            self.calls.append((name, message, detail))
        return record

    def __exit__(self, *exc):
        for name, fn in self.saved.items():
            setattr(self.module, name, fn)
        return False


def _pins(folder):
    store = MemoryStore(folder)
    pins = []
    for index, (level, grid, caption) in enumerate((('Level 2', 'C-4', 'Riser leak'), ('Level 2', 'C-5', 'Crack'),
                                                    ('Level 10', 'A-1', 'Roof drain'), ('', '', 'Loose'))):
        pin = photopins.new_pin((index, 0, 0), 'Meters', [], caption, level, grid)
        pin['id'] = 'PH-%03d' % (index + 1)
        media = photopins.media_folder(store, pin['id'])
        os.makedirs(media)
        names = ['a.png', 'b.png'] if index == 0 else ['a.png']
        for name in names:
            png.write(os.path.join(media, name), 8, 6, [200, 120, 40] * 48)
            pin['photos'].append(photopins.photo_entry(name, 'C:\\camera\\' + name, None, 100))
        store.put(pin)
        pins.append(pin)
    pins[3]['photos'].append({'file': 'missing.jpg', 'taken': ''})
    return store, pins


def test_photo_browser_builds_groups_and_filters():
    folder = _compat.tmpdir('smoke_photobrowser')
    store, pins = _pins(folder)
    win = field_photobrowser.build(None, store, pins)
    browser = win.Tag
    assert len(browser.cards) == 6                       # 2 + 1 + 1 + 2 (one missing photo)
    assert browser.status.Text == '4 pins, 6 photos.'
    assert browser.selected == ('PH-002', 'a.png')       # Level 2 first, newest first... same stamp: id desc
    thumbs = os.path.join(photopins.media_folder(store, 'PH-001'), '_thumbs')
    assert os.path.isdir(thumbs) and len(os.listdir(thumbs)) == 2
    browser.move(1)
    assert browser.selected == ('PH-001', 'a.png')
    pin, photo = browser.current()
    assert pin['id'] == 'PH-001' and photo['file'] == 'a.png'
    browser.on_filter('roof')
    assert len(browser.cards) == 1 and browser.selected == ('PH-003', 'a.png')
    browser.on_filter('')
    browser.on_group('none')
    assert len(browser.cards) == 6
    browser.on_filter('nothing matches this')
    assert browser.cards == [] and browser.selected is None
    assert not browser.go_button.IsEnabled


def test_card_entries_limit():
    pins = [{'id': 'PH-%03d' % i, 'caption': 'x', 'created': '2026-10-05', 'level': 'L1',
             'photos': [{'file': 'p%d.jpg' % i}]} for i in range(5)]
    groups, shown, total = field_photobrowser.card_entries(pins, 'level', '', limit=3)
    assert shown == 3 and total == 5 and len(groups[0][1]) == 3
    assert field_photobrowser.status_text(pins, 3, 5) == '5 pins, 5 photos; showing the first 3, filter to narrow.'
    assert field_photobrowser.status_text([], 0, 0).startswith('No photo pins yet')


def _views():
    return [{'guid': 'g1', 'name': 'Core', 'folder': 'Level 2', 'path': 'Level 2/Core', 'saved': None},
            {'guid': 'g2', 'name': 'Roof', 'folder': '', 'path': 'Roof', 'saved': None}]


def test_checklist_window_attach_answer_save_and_step():
    existing = checklists.new_checklist('g2', 'Roof', '', 'Safety walk', checklists.BUILTIN['Safety walk'])
    store = MemoryStore(records=[existing])
    with Toasts() as toasts:
        win = field_checklistwin.build(None, store, _views(), checklists.BUILTIN, current_guid='g1', user='amol')
        state = win.Tag
        assert state.index == 0 and state.record is None
        assert 'No checklist attached' in state.info.Text
        assert not state.inspector.IsEnabled
        state.attach('QA inspection')
        assert state.record['template'] == 'QA inspection' and store.puts == ['g1']
        assert state.inspector.Text == 'amol' and state.inspector.IsEnabled
        first = state.record['items'][0]['id']
        state._on_result(first, 'fail')(None, None)
        state._on_result(state.record['items'][1]['id'], 'pass')(None, None)
        assert state.dirty and 'Not saved yet' in state.info.Text
        assert state.save()
        assert not state.dirty and store.records['g1']['items'][0]['result'] == 'fail'
        assert 'Level 2/Core  (2/' in str(state.combo.Items[0])
        state.signed.IsChecked = True
        state.touch()
        state.save()
        assert not state.signed.IsChecked                 # items still open: refused
        assert any(kind == 'info' and message == 'Not signed off' for kind, message, _d in toasts.calls)
        state.step(1)
        assert state.index == 1 and state.record['template'] == 'Safety walk'
        assert state.combo.SelectedIndex == 1
        state.step(1)
        assert state.index == 1
        state.step(-1)
        assert state.record['items'][0]['result'] == 'fail'


def test_checklist_window_grows_with_template():
    old = checklists.new_checklist('g1', 'Core', 'Level 2', 'Mine', {'text': 'One\nTwo'})
    old['items'][0]['result'] = 'pass'
    store = MemoryStore(records=[old])
    with Toasts():
        win = field_checklistwin.build(None, store, _views(), {'Mine': {'text': 'One\nTwo\nThree'}}, 'g1', 'amol')
        state = win.Tag
        assert len(state.record['items']) == 3 and state.dirty
        assert state.record['items'][0]['result'] == 'pass'
    assert field_checklistwin.start_index(_views(), 'zz', {'g2': {}}) == 1
    assert field_checklistwin.start_index(_views(), None, {}) == 0
    assert field_checklistwin.viewpoint_label(_views()[0], None) == 'Level 2/Core'

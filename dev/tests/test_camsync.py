# -*- coding: utf-8 -*-
"""namo.camsync: the message protocol, timing, partner choice, and two Sync objects
talking through a folder on the fake (apply, unit conversion, no echo, dead files)."""
import json
import os

import _compat
from _compat import approx

import test_items as nav
import test_vp_common as vpfake
from namo import camera, camsync


CAM = camera.make_cam((1.0, 2.0, 3.0), rotation=(0.0, 0.0, 0.0, 1.0), projection='persp', height_field=1.0,
                      focal_distance=5.0, json='{"camera": 1}')


def test_file_names():
    assert camsync.file_name(1234) == '1234.json'
    assert camsync.pid_of(r'C:\x\1234.json') == 1234
    assert camsync.pid_of('1234.json.tmp') is None and camsync.pid_of('abc.json') is None


def test_message_round_trip_and_validation():
    msg = camsync.message(42, 7, CAM, 'Feet', 'Tower.nwf', now=100.5)
    text = camsync.dumps(msg)
    back = camsync.parse(text)
    assert back['pid'] == 42 and back['seq'] == 7 and back['time'] == 100.5 and back['units'] == 'Feet'
    assert back['camera']['position'] == [1.0, 2.0, 3.0] and back['camera']['json'] == '{"camera": 1}'
    assert camsync.parse(camsync.dumps(camsync.message(1, 1, None, 'Meters')))['camera'] is None
    assert camsync.parse('{"format": "playground-camsync", "pid": 1') is None          # a torn read
    assert camsync.parse(json.dumps({'format': 'other', 'pid': 1, 'seq': 1})) is None
    assert camsync.parse(json.dumps({'format': 'playground-camsync', 'pid': 'x', 'seq': 1})) is None
    bad_cam = dict(msg, camera={'position': [1, 2], 'rotation': [0, 0, 0, 1]})
    assert camsync.parse(json.dumps(bad_cam)) is None


def test_pick_partner_and_should_apply():
    entries = [{'pid': 1, 'mtime': 10}, {'pid': 2, 'mtime': 30}, {'pid': 3, 'mtime': 20}, {'pid': 9, 'mtime': 99}]
    alive = lambda pid: pid != 2
    assert camsync.pick_partner(entries, 9, alive)['pid'] == 3
    assert camsync.pick_partner(entries, 9, lambda pid: False) is None
    msg = {'pid': 3, 'seq': 5, 'camera': {}}
    assert camsync.should_apply(msg, {})
    assert camsync.should_apply(msg, {3: (0.0, 4)}) and not camsync.should_apply(msg, {3: (0.0, 5)})
    assert not camsync.should_apply({'pid': 3, 'seq': 9, 'camera': None}, {})
    assert not camsync.should_apply(None, {})


def test_write_due_debounce_and_ceiling():
    assert not camsync.write_due(1.0, None, None)
    assert not camsync.write_due(1.05, 1.0, 1.0)              # still moving within 80 ms
    assert camsync.write_due(1.09, 1.0, 1.0)                  # still for 80 ms
    assert camsync.write_due(1.26, 1.0, 1.25)                 # moving for 250 ms: send anyway
    assert not camsync.write_due(1.2, 1.0, 1.19)


def test_convert_units():
    same = camsync.convert(CAM, 'Feet', 'Feet')
    assert same['json'] == CAM['json']
    mm = camsync.convert(CAM, 'Meters', 'Millimeters')
    assert approx(mm['position'], [1000.0, 2000.0, 3000.0]) and mm['json'] is None
    assert approx(mm['focal_distance'], 5000.0) and mm['height_field'] == 1.0


def test_status_text():
    assert camsync.status_text(None)[0] == 'Waiting for another session'
    assert camsync.status_text({'pid': 77, 'title': 'B.nwf'}) == ('Syncing with Navisworks (PID 77)', 'B.nwf')


def _sync(folder, pid, doc, alive):
    sync = camsync.Sync(alive=alive, root=folder)
    sync.pid = pid
    sync.path = os.path.join(folder, camsync.file_name(pid))
    sync.doc = doc
    sync.running = True
    return sync


def test_two_sessions_follow_each_other_without_echo():
    folder = _compat.tmpdir('camsync_pair')
    doc_a = vpfake.make_doc(units='Meters', path=r'C:\A.nwf')
    doc_b = vpfake.make_doc(units='Millimeters', path=r'C:\B.nwd')
    with nav.FakeNav(doc_a) as fake:
        vpfake.extend(fake.Api)
        live = set([111, 222])
        a = _sync(folder, 111, doc_a, lambda pid: pid in live)
        b = _sync(folder, 222, doc_b, lambda pid: pid in live)
        a.write(presence=True)
        b.poll()
        assert b.partner == 111 and doc_b.CurrentViewpoint.writes == []
        doc_a.CurrentViewpoint.vp.Position = nav.Point3D(1.0, 2.0, 3.0)
        assert a.write() is True
        b.poll()
        assert len(doc_b.CurrentViewpoint.writes) == 1
        assert approx(doc_b.CurrentViewpoint.vp.Position.t(), (1000.0, 2000.0, 3000.0))
        assert b.seen[111] == (a.started, a.seq)
        assert b.write() is False                      # the camera it was given is not sent back
        b.poll()
        assert len(doc_b.CurrentViewpoint.writes) == 1
        doc_b.CurrentViewpoint.vp.Position = nav.Point3D(5000.0, 0.0, 0.0)
        assert b.write() is True
        a.poll()
        assert approx(doc_a.CurrentViewpoint.vp.Position.t(), (5.0, 0.0, 0.0))
        assert a.write() is False
        dead = os.path.join(folder, '999.json')
        with open(dead, 'w') as handle:
            handle.write(camsync.dumps(camsync.message(999, 50, CAM, 'Meters')))
        a.poll()
        assert not os.path.exists(dead)
        assert approx(doc_a.CurrentViewpoint.vp.Position.t(), (5.0, 0.0, 0.0))
        b.stop()
        assert not os.path.exists(b.path) and not b.running
        live.discard(222)
        a.poll()
        assert a.partner is None


def test_apply_skips_a_camera_already_there():
    folder = _compat.tmpdir('camsync_same')
    doc = vpfake.make_doc()
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        sync = _sync(folder, 5, doc, lambda pid: True)
        here = camera.capture(doc)
        msg = camsync.message(6, 1, here, 'Meters')
        assert sync.apply(msg) is False and doc.CurrentViewpoint.writes == []
        assert sync.last_applied is not None


def test_stop_and_start_holder_without_a_sync():
    from namo import session
    session.clear(camsync.HOLDER)
    assert camsync.stop() is False
    assert camsync.is_running() is False and camsync.current() is None
    session.clear(camsync.HOLDER)


def test_a_partner_that_restarts_is_heard_again():
    # Regression: seq starts again at 1 when the other window switches Camera Sync off
    # and on. Judged by seq alone, this window stayed deaf until the new count passed
    # the old one (hundreds of camera moves later).
    seen = {7: (100.0, 480)}
    old = {'pid': 7, 'seq': 480, 'started': 100.0, 'camera': {}}
    again = {'pid': 7, 'seq': 2, 'started': 250.0, 'camera': {}}
    assert not camsync.should_apply(old, seen)
    assert camsync.should_apply(again, seen)
    seen[7] = camsync.stamp_of(again)
    assert not camsync.should_apply(again, seen)
    assert camsync.should_apply(dict(again, seq=3), seen)
    # a message from before 'started' existed reads as started 0.0
    assert camsync.stamp_of({'pid': 7, 'seq': 4}) == (0.0, 4)
    back = camsync.parse(camsync.dumps(camsync.message(7, 2, CAM, 'Feet', started=250.0)))
    assert back['started'] == 250.0


def test_restart_through_the_folder():
    folder = _compat.tmpdir('camsync_restart')
    doc_a = vpfake.make_doc(units='Meters', path=r'C:\A.nwf')
    doc_b = vpfake.make_doc(units='Meters', path=r'C:\B.nwf')
    with nav.FakeNav(doc_a) as fake:
        vpfake.extend(fake.Api)
        alive = lambda pid: True
        a = _sync(folder, 111, doc_a, alive)
        b = _sync(folder, 222, doc_b, alive)
        for x in (1.0, 2.0, 3.0):
            doc_a.CurrentViewpoint.vp.Position = nav.Point3D(x, 0.0, 0.0)
            assert a.write() is True
            b.poll()
        assert approx(doc_b.CurrentViewpoint.vp.Position.t(), (3.0, 0.0, 0.0))
        a.stop()
        a2 = _sync(folder, 111, doc_a, alive)           # Camera Sync off and on again
        a2.started = a.started + 60.0
        doc_a.CurrentViewpoint.vp.Position = nav.Point3D(9.0, 0.0, 0.0)
        assert a2.write() is True and a2.seq == 1
        b.poll()
        assert approx(doc_b.CurrentViewpoint.vp.Position.t(), (9.0, 0.0, 0.0))


def test_file_changed_reads_fresh_files_whatever_the_stamp():
    assert camsync.file_changed((100.0, 900), None, 500.0)
    assert camsync.file_changed((100.0, 900), (99.0, 900), 500.0)
    assert not camsync.file_changed((100.0, 900), (100.0, 900), 500.0)
    # coarse file times: a second write inside the same tick keeps the stamp
    assert camsync.file_changed((100.0, 900), (100.0, 900), 100.5)


def test_liveness_is_asked_once_a_second():
    folder = _compat.tmpdir('camsync_alive')
    asked = []

    def alive(pid):
        asked.append(pid)
        return True
    sync = _sync(folder, 5, vpfake.make_doc(), alive)
    assert sync._is_alive(8) and sync._is_alive(8) and sync._is_alive(8)
    assert asked == [8]
    sync.checked[8] = (sync.checked[8][0] - 5.0, True)
    assert sync._is_alive(8) and asked == [8, 8]


class _Timer(object):
    def __init__(self):
        self.IsEnabled = False
        self.starts = 0

    def Start(self):
        self.IsEnabled = True
        self.starts += 1

    def Stop(self):
        self.IsEnabled = False


def test_a_failed_write_is_tried_again():
    # Regression: the pending flags were cleared before the write, so one busy file
    # left the other window a move behind until the camera moved again.
    folder = _compat.tmpdir('camsync_retry')
    doc = vpfake.make_doc()
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        sync = _sync(folder, 5, doc, lambda pid: True)
        sync.write_timer = _Timer()
        calls = []

        def busy(presence=False):
            calls.append(1)
            raise IOError('file in use')
        real_write = sync.write
        sync.write = busy
        sync.first_change = sync.last_change = 1.0          # long ago: due now
        sync._on_write_tick(None, None)
        assert calls == [1] and sync.write_failures == 1
        assert sync.first_change is not None and sync.write_timer.IsEnabled
        sync.write = real_write
        sync.first_change = sync.last_change = 1.0
        sync._on_write_tick(None, None)
        assert sync.write_failures == 0 and sync.first_change is None
        assert os.path.exists(sync.path)
        sync.write = busy
        for _ in range(camsync.WRITE_RETRIES + 3):
            sync.first_change = sync.last_change = 1.0
            sync._on_write_tick(None, None)
        assert sync.first_change is None                    # gave up: no endless retry

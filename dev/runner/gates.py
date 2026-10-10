# -*- coding: utf-8 -*-
"""Library gate checks under `pynavis run` (dev only): the headless subset of
dev/IN_APP_CHECKS.md G1-G7 plus Quick Find's index and pynavis.sets.create.

    pynavis run dev\\runner\\gates.py D:\\Temp\\pg-runner\\models\\a.nwd D:\\Temp\\pg-runner\\models\\b.nwd --timeout 300

Runs once per model. Every check records pass/fail and the numbers it saw in
__result__ (the runner copies it into results.json). Files go to
D:\\Temp\\pg-runner\\gates; per-user data to the sandbox (see _bootstrap.py). The model is
a throwaway copy and the runner is never asked to save it.
"""
import os
import sys
import traceback

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import _bootstrap  # noqa: E402

OUT = r'D:\Temp\pg-runner\gates'
RED = 'E15759'

_bootstrap.use_playground_lib()
_bootstrap.enter_sandbox()
checks = []


def check(name, fn):
    try:
        ok, detail = fn()
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})
    except Exception as error:
        checks.append({'check': name, 'ok': False, 'detail': '%s: %s' % (type(error).__name__, error),
                       'traceback': traceback.format_exc().strip().splitlines()[-4:]})


def biggest_gap(a, b):
    return max(abs(float(x) - float(y)) for x, y in zip(a, b))


def rounded(v, n=4):
    return [round(float(x), n) for x in v]


def g0_imports():
    from namo import camera, items, paint, images, clashdata, ui, docdb  # noqa: F401
    import namo
    return True, os.path.dirname(namo.__file__)


def g1_axes():
    from namo import camera
    start = camera.capture()
    out = {}
    ok = True
    for label, direction, up in (('front', (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                                 ('top', (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))):
        cam = camera.make_cam(start['position'], direction=direction, up=up)
        cam['height_field'] = None
        camera.apply(cam)
        got = camera.capture()
        gap = max(biggest_gap(got['direction'], direction), biggest_gap(got['up'], up))
        out[label] = {'direction': rounded(got['direction']), 'up': rounded(got['up']), 'gap': round(gap, 6)}
        ok = ok and gap < 1e-3
    camera.apply(start)
    return ok, out


def g2_round_trip():
    from namo import camera
    start = camera.capture()
    eye = start['position']
    away = (eye[0] + 10.0, eye[1] - 7.0, eye[2] + 3.0)
    camera.look_at(away, (0.0, 0.0, 0.0))
    moved = camera.capture()
    camera.apply(start)
    back = camera.capture()
    gaps = {'position': biggest_gap(back['position'], start['position']),
            'direction': biggest_gap(back['direction'], start['direction']),
            'up': biggest_gap(back['up'], start['up']),
            'moved_away_by': biggest_gap(moved['position'], start['position'])}
    ok = gaps['moved_away_by'] > 1.0 and gaps['position'] < 1e-6 * max(1.0, max(abs(x) for x in eye)) + 1e-4 \
        and gaps['direction'] < 1e-4 and gaps['up'] < 1e-4
    return ok, {k: round(v, 8) for k, v in gaps.items()}


def g3_image(stem):
    from namo import camera, images
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    path = os.path.join(OUT, '%s-1280x720.png' % stem)
    if os.path.exists(path):
        os.remove(path)
    images.capture(path, 1280, 720)
    size = images.image_size(path) if os.path.isfile(path) else None
    views = camera.saved_views()
    detail = {'path': path, 'bytes': os.path.getsize(path) if os.path.isfile(path) else 0,
              'size': list(size) if size else None, 'saved_views': len(views)}
    return bool(size) and tuple(size) == (1280, 720), detail


def g4_clash():
    from namo import clashdata
    tests = clashdata.tests()
    detail = {'tests': len(tests)}
    if tests:
        rows = clashdata.snapshot(tests[0])
        detail['rows_first_test'] = len(rows)
        detail['results_first_test'] = len(clashdata.results(tests[0]))
        return len(rows) == detail['results_first_test'], detail
    return True, detail


def _red_count(objs):
    count = 0
    for item in objs:
        geometry = item.Geometry
        if geometry is None:
            continue
        color = geometry.PermanentColor
        if color is not None and color.R > 0.8 and color.G < 0.45 and color.B < 0.45:
            count += 1
    return count


def g5_paint_undo():
    from namo import items, paint
    from pynavis._api import Application
    document = Application.ActiveDocument
    geo = list(items.geometry_items(items.roots()))
    before_red = _red_count(geo)
    undo_before = document.NextUndo
    paint.apply([(geo, RED, None)])
    after_red = _red_count(geo)
    undo_name = document.NextUndo
    undone = document.TryUndo()
    undo_after = document.NextUndo
    final_red = _red_count(geo)
    detail = {'geometry_items': len(geo), 'red_before': before_red, 'red_after_apply': after_red,
              'next_undo_after_apply': str(undo_name), 'try_undo': bool(undone),
              'red_after_one_undo': final_red, 'next_undo_before': str(undo_before),
              'next_undo_after_undo': str(undo_after)}
    ok = after_red == len(geo) and bool(undone) and final_red == before_red
    return ok, detail


def g6_revit_ids():
    from namo import items
    objs = list(items.objects(items.roots()))
    ids = items.revit_ids(objs[0]) if objs else None
    return ids is not None, {'objects': len(objs), 'first': ids}


def g7_docdb():
    from namo import docdb
    available = docdb.available()
    if not available:
        return False, {'available': False}
    docdb.kv_set('runner-check', {'a': 1})
    back = docdb.kv_get('runner-check')
    keys = docdb.kv_keys()
    return back == {'a': 1}, {'available': True, 'read_back': back, 'keys': list(keys)}


def quickfind_index():
    from namo import quickfind
    index = quickfind.build()
    rows = len(index.rows)
    path = quickfind.index_path()
    return rows > 0, {'rows': rows, 'sampled': bool(index.sampled), 'index_file': path,
                      'saved': os.path.isfile(path)}


def sets_create():
    from namo import items
    from pynavis import sets
    from pynavis._api import Application
    document = Application.ActiveDocument
    objs = list(items.objects(items.roots()))[:5]
    before = document.SelectionSets.Value.Count
    created = sets.create('Runner gate set', objs)
    after = document.SelectionSets.Value.Count
    name = str(created.DisplayName) if created is not None else None
    return after == before + 1 and name is not None, {'items': len(objs), 'sets_before': before,
                                                      'sets_after': after, 'name': name}


stem = os.path.splitext(os.path.basename(str(__model__ or 'none')))[0]  # noqa: F821
try:
    check('G0 imports', g0_imports)
    check('G1 camera axes (front, top)', g1_axes)
    check('G2 camera capture/apply round trip', g2_round_trip)
    check('G3 images.capture 1280x720', lambda: g3_image(stem))
    check('G4 clashdata.tests', g4_clash)
    check('G5 paint.apply + one undo', g5_paint_undo)
    check('G6 items.revit_ids', g6_revit_ids)
    check('G7 docdb kv set/get', g7_docdb)
    check('Quick Find index build', quickfind_index)
    check('pynavis sets.create', sets_create)
finally:
    _bootstrap.leave_sandbox()

for row in checks:
    print('%s  %s  %s' % ('PASS' if row['ok'] else 'FAIL', row['check'], row['detail']))
__result__ = {'model': stem, 'checks': checks}

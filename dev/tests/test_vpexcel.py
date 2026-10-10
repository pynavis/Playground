# -*- coding: utf-8 -*-
"""namo.vpexcel: header mapping, cell and row parsing, cameras both ways, a workbook
round trip (namo.xlsx out, pynavis.xl in), comments, and the import on the fake."""
import math
import os

import _compat
from _compat import approx, raises

import test_items as nav
import test_vp_common as vpfake
from namo import camera, vpexcel


HEADER = vpexcel.COLUMNS


def row(folder, name, eye, target, up=(None, None, None), projection='', fov=None, comment=None):
    return [folder, name] + list(eye) + list(target) + list(up) + [projection, fov, comment]


def test_header_map_any_order_and_aliases():
    mapping = vpexcel.header_map(['Name', 'Comments', 'Position X', 'Position Y', 'Position Z',
                                  'Target X', 'target y', 'TARGET_Z', 'FOV'])
    assert mapping['name'] == 0 and mapping['comment'] == 1 and mapping['eye_x'] == 2
    assert mapping['target_z'] == 7 and mapping['fov'] == 8 and 'folder' not in mapping


def test_find_header_below_a_title():
    rows = [['Viewpoints of Hospital'], ['Lengths in feet'], HEADER, row('', 'A', (0, 0, 0), (1, 0, 0))]
    index, mapping = vpexcel.find_header(rows)
    assert index == 2 and mapping['projection'] == 11
    index, missing = vpexcel.find_header([['Name', 'Eye X']])
    assert index is None and 'Target X' in missing


def test_parse_length_cell():
    assert vpexcel.parse_length_cell(12, 'Meters') == 12.0
    assert vpexcel.parse_length_cell('1,234.5', 'Meters') == 1234.5
    assert vpexcel.parse_length_cell('12,5', 'Meters') == 12.5
    assert vpexcel.parse_length_cell('2.5 m', 'Millimeters') == 2500.0
    assert approx(vpexcel.parse_length_cell("-41' 6\"", 'Feet'), -41.5)
    assert vpexcel.parse_length_cell('', 'Meters') is None
    assert vpexcel.parse_length_cell(None, 'Meters') is None
    raises(ValueError, vpexcel.parse_length_cell, 'twelve', 'Meters')
    raises(ValueError, vpexcel.parse_length_cell, True, 'Meters')


def test_parse_projection():
    assert vpexcel.parse_projection('') == 'persp'
    assert vpexcel.parse_projection('Perspective') == 'persp'
    assert vpexcel.parse_projection(' ortho ') == 'ortho'
    assert vpexcel.parse_projection('Parallel') == 'ortho'
    raises(ValueError, vpexcel.parse_projection, 'fisheye')


def test_parse_row_good_and_bad():
    mapping = vpexcel.header_map(HEADER)
    good = vpexcel.parse_row(row(' A / B ', 'View 1', (0, 0, 1.6), (10, 0, 1.6), projection='Perspective',
                                 fov=u'45°', comment='Check the duct'), mapping, 'Meters')
    assert good['folder'] == 'A/B' and good['up'] == (0.0, 0.0, 1.0) and good['fov_height'] == 45.0
    ortho = vpexcel.parse_row(row('', 7.0, (0, 0, 50), (0, 0, 0), up=(0, 1, 0), projection='O', fov='12 m'),
                              mapping, 'Millimeters')
    assert ortho['name'] == '7' and ortho['fov_height'] == 12000.0 and ortho['up'] == (0.0, 1.0, 0.0)
    problems = [
        (row('', '', (0, 0, 0), (1, 0, 0)), 'Name is empty'),
        (row('', 'X', ('', 0, 0), (1, 0, 0)), 'Eye X is empty'),
        (row('', 'X', ('abc', 0, 0), (1, 0, 0)), 'Eye X'),
        (row('', 'X', (1, 1, 1), (1, 1, 1)), 'same point'),
        (row('', 'X', (0, 0, 0), (1, 0, 0), projection='Perspective', fov=200), 'between'),
        (row('', 'X', (0, 0, 0), (1, 0, 0), projection='Orthographic', fov=-1), 'more than zero'),
        (row('', 'X', (0, 0, 0), (1, 0, 0), fov='wide'), 'not a number'),
        (row('', 'X', (0, 0, 0), (1, 0, 0), projection='fish'), 'Projection'),
    ]
    for cells, text in problems:
        try:
            vpexcel.parse_row(cells, mapping, 'Meters')
        except ValueError as error:
            assert text in str(error), (text, str(error))
        else:
            raise AssertionError('no error for %r' % (cells,))


def test_parse_rows_numbers_rows_and_finds_repeats():
    rows = [['Title'], HEADER, row('A', 'One', (0, 0, 0), (1, 0, 0)), ['', '', '', ''],
            row('A', 'one', (0, 0, 0), (1, 0, 0)), row('B', '', (0, 0, 0), (1, 0, 0)),
            row('B', 'Two', (0, 0, 0), (0, 1, 0))]
    records, errors, header = vpexcel.parse_rows(rows, 'Meters')
    assert header == 1
    assert [(r['row'], r['name']) for r in records] == [(3, 'One'), (7, 'Two')]
    assert errors == [(5, 'A', 'one', 'Repeats Folder and Name of row 3'), (6, 'B', '', 'Name is empty')]
    raises(ValueError, vpexcel.parse_rows, [['nothing here']], 'Meters')


def test_camera_of_records():
    persp = vpexcel.camera_of({'eye': (0, 0, 0), 'target': (10, 0, 0), 'up': (0, 0, 1), 'projection': 'persp',
                               'fov_height': None})
    assert approx(persp['direction'], (1.0, 0.0, 0.0)) and approx(persp['fov'], 60.0)
    assert persp['focal_distance'] == 10.0 and persp['rotation'] is None
    ortho = vpexcel.camera_of({'eye': (0, 0, 10), 'target': (0, 0, 0), 'up': (0, 1, 0), 'projection': 'ortho',
                               'fov_height': None})
    assert approx(ortho['height_field'], 2 * 10 * math.tan(math.radians(30)))
    assert approx(ortho['up'], (0.0, 1.0, 0.0))


def test_row_of_and_back():
    cam = camera.make_cam((1.0, 2.0, 3.0), direction=(0, 1, 0), up=(0, 0, 1), projection='persp',
                          height_field=camera.height_field_for(50.0), focal_distance=4.0)
    cells = vpexcel.row_of('F', 'N', cam, 'note', 10.0)
    assert cells[:2] == ['F', 'N'] and approx(cells[5:8], [1.0, 6.0, 3.0]) and cells[11] == 'Perspective'
    assert approx(cells[12], 50.0) and cells[13] == 'note'
    record = vpexcel.parse_row(cells, vpexcel.header_map(HEADER), 'Meters')
    back = vpexcel.camera_of(record)
    assert approx(back['position'], cam['position']) and approx(back['direction'], cam['direction'])
    assert approx(back['fov'], 50.0)
    ortho = camera.make_cam((0, 0, 9), direction=(0, 0, -1), up=(0, 1, 0), projection='ortho', height_field=30.0)
    cells = vpexcel.row_of('', 'Plan', ortho, '', 9.0)
    assert cells[11] == 'Orthographic' and cells[12] == 30.0 and approx(cells[7], 0.0)


def test_workbook_round_trip():
    from namo import xlsx
    from pynavis import xl
    folder = _compat.tmpdir('vpexcel_book')
    path = os.path.join(folder, 'views.xlsx')
    wb = xlsx.Workbook(title='Viewpoints')
    ws = wb.sheet(vpexcel.SHEET)
    ws.title('Viewpoints of test', span=len(HEADER))
    ws.columns(HEADER)
    ws.row(row('Level 2', 'Corridor', (1.5, 2.25, 1.6), (11.5, 2.25, 1.6), (0, 0, 1), 'Perspective', 55.0,
               'First line\nSecond line'))
    ws.row(row('', 'Plan', (0, 0, 40), (0, 0, 0), (0, 1, 0), 'Orthographic', 25.0, None))
    wb.sheet('Read me').row(['notes'])
    wb.save(path)
    rows = xl.read(path, vpexcel.SHEET)
    records, errors, header = vpexcel.parse_rows(rows, 'Meters')
    assert errors == [] and header == 1
    assert records[0]['folder'] == 'Level 2' and records[0]['eye'] == (1.5, 2.25, 1.6)
    assert records[0]['comment'] == 'First line\nSecond line' and records[1]['projection'] == 'ortho'


def test_comment_lines_and_new_comments():
    assert vpexcel.comment_lines(' a \r\n\nb ') == ['a', 'b']
    assert vpexcel.new_comments('a\nb\nc', ['a', 'x\nb']) == ['c']
    assert vpexcel.new_comments('', ['a']) == []


def test_plan_and_sentence():
    records = [{'folder': 'A', 'name': 'x'}, {'folder': 'A', 'name': 'y'}]
    steps = vpexcel.plan(records, lambda f, n: n == 'y')
    assert [s[1] for s in steps] == ['create', 'update']
    assert vpexcel.plan_sentence(steps, [1, 2]) == 'Create 1 viewpoint, update 1 viewpoint, skip 2 rows with problems.'
    assert vpexcel.plan_sentence([], []) == 'Nothing to do.'


def test_apply_creates_and_updates_on_the_fake():
    doc = vpfake.make_doc()
    vpfake.tree(doc)
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        records = [{'row': 3, 'folder': 'A', 'name': 'one', 'eye': (5, 5, 5), 'target': (5, 15, 5), 'up': (0, 0, 1),
                    'projection': 'persp', 'fov_height': None, 'comment': 'New note'},
                   {'row': 4, 'folder': 'Z', 'name': 'Fresh', 'eye': (0, 0, 9), 'target': (0, 0, 0), 'up': (0, 1, 0),
                    'projection': 'ortho', 'fov_height': 20.0, 'comment': 'a\nb'}]
        exists, find = vpexcel.lookup(doc)
        steps = vpexcel.plan(records, exists)
        assert [s[1] for s in steps] == ['update', 'create']
        out = vpexcel.apply(doc, steps)
    assert out['created'] == 1 and out['updated'] == 1 and out['failed'] == [] and out['comments'] == 1
    assert doc.transactions[0] == 'Viewpoints from Excel'
    folder_a = doc.SavedViewpoints.RootItem.Children[1]
    one = folder_a.Children[0]
    assert one.DisplayName == 'One' and one.Viewpoint.Position.t() == (5.0, 5.0, 5.0)
    assert [c.Body for c in one.Comments] == ['New note']
    fresh = doc.SavedViewpoints.RootItem.Children[-1].Children[0]
    assert fresh.DisplayName == 'Fresh' and [c.Body for c in fresh.Comments] == ['a', 'b']
    assert fresh.Viewpoint.ClipPlanes.Enabled is False


class _CopyableView(nav.SavedViewpoint):
    """A saved viewpoint as Navisworks hands it out: CreateCopy gives a detached,
    editable item (pyNavis' Speeds to Saved relies on exactly this)."""

    def __init__(self, viewpoint, editable=True):
        nav.SavedViewpoint.__init__(self, viewpoint)
        self.editable = editable
        self.redlines = ['cloud']
        self.ContainsVisibilityOverrides = True
        self.ContainsAppearanceOverrides = False

    def CreateCopy(self):
        import copy
        clone = copy.copy(self)
        clone.Viewpoint = self.Viewpoint.CreateCopy()
        clone.Viewpoint.IsReadOnly = not self.editable
        return clone


def _copyable_doc(editable):
    doc = vpfake.make_doc()
    vp = nav.Viewpoint()
    vp.IsReadOnly = True                 # the document-owned viewpoint never takes a write
    vp.LinearSpeed = 3.0
    item = _CopyableView(vp, editable)
    item.DisplayName = 'Lobby'
    item.Comments.append(nav.Comment('Keep me', 'New', 'Ann'))
    doc.SavedViewpoints.RootItem.Children.append(item)
    return doc, item


def test_update_keeps_redlines_and_hidden_items_without_recalling_the_view():
    # Regression: a view that stores hidden items used to be recalled on screen,
    # re-aimed and re-captured (ReplaceFromCurrentView), and any other view was
    # rebuilt from its camera, losing its redlines. The shipped route is a copy of
    # the saved item, edited and swapped in.
    doc, item = _copyable_doc(editable=True)
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        assert vpexcel.full_copy_works(item)
        cam = vpexcel.camera_of({'eye': (7.0, 8.0, 9.0), 'target': (7.0, 18.0, 9.0), 'up': (0, 0, 1),
                                 'projection': 'persp', 'fov_height': None})
        live = vpexcel.update_camera(doc, item, cam)
    assert live.Viewpoint.Position.t() == (7.0, 8.0, 9.0)
    assert live.redlines == ['cloud'] and live.ContainsVisibilityOverrides
    assert live.Guid == item.Guid and live.DisplayName == 'Lobby'
    assert [c.Body for c in live.Comments] == ['Keep me']
    assert doc.SavedViewpoints.updated == [] and doc.CurrentViewpoint.writes == []
    assert doc.SavedViewpoints.CurrentSavedViewpoint is None
    assert approx(live.Viewpoint.LinearSpeed, 3.0)          # the probe put it back


def test_update_falls_back_when_copies_are_read_only():
    doc, item = _copyable_doc(editable=False)
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        assert not vpexcel.full_copy_works(item)
        cam = vpexcel.camera_of({'eye': (1.0, 2.0, 3.0), 'target': (1.0, 12.0, 3.0), 'up': (0, 0, 1),
                                 'projection': 'persp', 'fov_height': None})
        vpexcel.update_camera(doc, item, cam)
    # it stores hidden items, so the fallback is recall + ReplaceFromCurrentView
    assert doc.SavedViewpoints.updated == ['Lobby']

# -*- coding: utf-8 -*-
"""namo.vp_common: text helpers, view specs, ordering, cameras, and the saved-view API
half through the shared fake Navisworks layer (extended here for the Views tools:
other Views tests import this module as `vpfake`)."""
import copy
import os

import _compat
from _compat import approx, raises

import test_items as nav
from namo import vp_common


# ---- the fake layer, extended ----------------------------------------------------------


class ViewsSaved(nav.SavedViewpoints):
    """SavedViewpoints with the calls the Views tools use beyond test_items' set."""

    def __init__(self, doc=None):
        nav.SavedViewpoints.__init__(self)
        self.doc = doc
        self.replaced = []
        self.updated = []

    def ReplaceWithCopy(self, *args):
        if len(args) == 2:
            parent, (index, item) = self.RootItem, args
        else:
            parent, index, item = args
        clone = copy.copy(item)
        clone.Guid = getattr(item, 'Guid', None) or nav._new_guid()
        clone.Parent = None if parent is self.RootItem else parent
        clone.Comments = []
        parent.Children[index] = clone
        self.replaced.append(clone.DisplayName)

    def EditComments(self, item, comments):
        item.Comments = list(comments)

    def CaptureRuntimeOverrides(self):
        item = nav.SavedViewpoint(self.doc.CurrentViewpoint.CreateCopy() if self.doc else nav.Viewpoint())
        item.ContainsVisibilityOverrides = True
        item.ContainsAppearanceOverrides = False
        item.hidden_then = list(getattr(self.doc, 'hidden_now', []))
        return item

    def Remove(self, *args):
        parent, item = (self.RootItem, args[0]) if len(args) == 1 else args
        for index, child in enumerate(parent.Children):
            if child is item:
                del parent.Children[index]
                return True
        return False

    def ReplaceFromCurrentView(self, saved):
        saved.Viewpoint = self.doc.CurrentViewpoint.CreateCopy()
        self.updated.append(saved.DisplayName)


def extend(api):
    """Adds the enums the Views modules read that test_items' fake Api lacks."""
    api.ViewpointRenderStyle = nav._enum('FullRender', 'Preview', 'Shaded', 'Wireframe', 'HiddenLine')
    api.ViewpointLighting = nav._enum('None', 'SceneLights', 'Headlight', 'FullLights')
    api.SavedViewpointAnimation = type('SavedViewpointAnimation', (nav.GroupItem,), {})
    return api


def make_doc(models=(), units='Meters', path=r'C:\Jobs\Hospital.nwf'):
    doc = nav.Document(models)
    doc.SavedViewpoints = ViewsSaved(doc)
    doc.Units = units
    doc.FileName = path
    doc.Title = os.path.basename(path) if path else 'Untitled'
    doc.hidden_now = []
    return doc


def view(name, position=(0.0, 0.0, 10.0), comments=()):
    vp = nav.Viewpoint()
    vp.Position = nav.Point3D(*position)
    item = nav.SavedViewpoint(vp)
    item.DisplayName = name
    for text in comments:
        item.Comments.append(nav.Comment(text, 'New', 'Ann'))
    return item


def folder(name, children=()):
    item = nav.FolderItem()
    item.DisplayName = name
    for child in children:
        child.Parent = item
        item.Children.append(child)
    return item


def tree(doc):
    """Top, A/One, A/B/Two, C/Three (folders in that order)."""
    root = doc.SavedViewpoints.RootItem
    for item in (view('Top', comments=['Look here']), folder('A', [view('One'), folder('B', [view('Two')])]),
                 folder('C', [view('Three')])):
        root.Children.append(item)
    return root


def check_defaults(fields):
    """Every choice/radio default is one of its option VALUES (options are (label,
    value) pairs: a pair written the other way round reads back as None)."""
    from namo import ui
    for field in ui.normalize_fields(fields):
        if field['kind'] in ('choice', 'radio') and field.get('default') is not None:
            values = [v for _l, v in ui.options_of(field)]
            assert field['default'] in values, (field['key'], field['default'], values)
        if field['kind'] == 'multi':
            values = [v for _l, v in ui.options_of(field)]
            assert all(d in values for d in field.get('default') or []), field['key']


ROWS = [{'folder': '', 'name': 'Top'}, {'folder': 'A', 'name': 'One'}, {'folder': 'A/B', 'name': 'Two'},
        {'folder': 'C', 'name': 'Three'}, {'folder': 'C', 'name': 'Four'}]


# ---- pure ----------------------------------------------------------------------------------


def test_counts_and_plurals():
    assert vp_common.count_text(1234567) == '1,234,567'
    assert vp_common.plural(1, 'viewpoint') == '1 viewpoint'
    assert vp_common.plural(1200, 'viewpoint') == '1,200 viewpoints'
    assert vp_common.plural(2, 'box', 'boxes') == '2 boxes'


def test_length_text_metric_and_imperial():
    assert vp_common.length_text(1.2, 'Meters') == '1.200 m'
    assert vp_common.length_text(-0.0001, 'Meters') == '0.000 m'
    assert vp_common.length_text(1250, 'Millimeters', 0) == '1250 mm'
    assert vp_common.length_text(12.5, 'Feet') == "12' 6\""
    assert vp_common.length_text(18, 'Inches') == "1' 6\""
    assert vp_common.length_text(None, 'Meters') == ''
    assert vp_common.meters_text(10, 'Feet') == '3.048 m'
    assert vp_common.point_text((1, 2, 3), 'Meters') == 'X 1.000 m  Y 2.000 m  Z 3.000 m'


def test_unit_factors():
    assert vp_common.unit_symbol('Millimeters') == 'mm'
    assert vp_common.unit_symbol('Nonsense') == 'm'
    assert approx(vp_common.unit_factor('Feet', 'Inches'), 12.0)
    assert approx(vp_common.unit_factor('Millimeters', 'Meters'), 0.001)
    assert vp_common.to_meters_factor('Unknown') == 1.0


def test_signed_lengths():
    assert vp_common.signed_length('-1250', 'Millimeters') == -1250.0
    assert vp_common.signed_length('-3.5 m', 'Millimeters') == -3500.0
    assert approx(vp_common.signed_length("-12' 6\"", 'Feet'), -12.5)
    assert vp_common.signed_length('4,2', 'Meters') == 4.2
    assert vp_common.signed_length(3, 'Meters') == 3.0
    assert vp_common.signed_length('', 'Meters') is None
    assert vp_common.signed_length('abc', 'Meters') is None
    assert vp_common.length_input(-2.5, 'Meters') == '-2.5'
    assert vp_common.length_input(12.5, 'Feet') == "12' 6\""
    assert vp_common.length_input(0, 'Meters') == '0'


def test_default_folder_and_stem():
    here = _compat.tmpdir('vp_common_folder')
    assert vp_common.default_folder(os.path.join(here, 'A.nwf'), 'DOCS') == here
    assert vp_common.default_folder('', 'DOCS') == 'DOCS'
    assert vp_common.default_folder(r'Z:\does\not\exist\A.nwf', 'DOCS') == 'DOCS'
    assert vp_common.file_stem(r'C:\Jobs\Hospital.nwf') == 'Hospital'
    assert vp_common.file_stem('') == 'Untitled'
    assert vp_common.join_path('A/B', 'View') == 'A/B/View' and vp_common.join_path('', 'V') == 'V'
    assert vp_common.folder_label('') == '(top level)'


def test_sizes():
    assert vp_common.parse_size('1920 x 1080') == (1920, 1080)
    assert vp_common.parse_size('1280x720') == (1280, 720)
    assert vp_common.parse_size('800, 600') == (800, 600)
    assert vp_common.parse_size('9000x10') is None
    assert vp_common.parse_size('big') is None
    assert vp_common.size_from('3840x2160') == (3840, 2160)
    assert vp_common.size_from('custom', 1000, 500) == (1000, 500)
    assert vp_common.size_from('custom', None, 500) is None
    assert vp_common.size_options()[-1] == ('Custom size', 'custom')


def test_select_rows_by_spec():
    names = lambda rows: [r['name'] for r in rows]
    assert names(vp_common.select_rows(ROWS, None)) == ['Top', 'One', 'Two', 'Three', 'Four']
    assert names(vp_common.select_rows(ROWS, {'mode': 'folders', 'folders': ['A']})) == ['One', 'Two']
    assert names(vp_common.select_rows(ROWS, {'mode': 'folders', 'folders': ['']})) == ['Top']
    assert names(vp_common.select_rows(ROWS, {'mode': 'folders', 'folders': ['A/B', 'C']})) == ['Two', 'Three', 'Four']
    spec = {'mode': 'list', 'views': [['C', 'Four'], ['', 'Top'], ['X', 'Gone'], 'junk']}
    assert names(vp_common.select_rows(ROWS, spec)) == ['Top', 'Four']
    assert vp_common.missing_views(ROWS, spec) == ['X/Gone']
    assert vp_common.missing_views(ROWS, {'mode': 'all'}) == []


def test_folder_paths_include_ancestors_and_top_first():
    rows = [{'folder': 'A/B', 'name': 'x'}, {'folder': '', 'name': 'y'}, {'folder': 'A', 'name': 'z'}]
    assert vp_common.folder_paths(rows) == [('', 1), ('A', 2), ('A/B', 1)]


def test_spec_for_picks_the_smallest_spec():
    assert vp_common.spec_for(ROWS, ROWS)['mode'] == 'all'
    folders = vp_common.spec_for(ROWS, [ROWS[1], ROWS[2]])
    assert folders == {'mode': 'folders', 'folders': ['A'], 'views': []}
    top_and_c = vp_common.spec_for(ROWS, [ROWS[0], ROWS[3], ROWS[4]])
    assert top_and_c['mode'] == 'folders' and sorted(top_and_c['folders']) == ['', 'C']
    listed = vp_common.spec_for(ROWS, [ROWS[1], ROWS[3]])
    assert listed == {'mode': 'list', 'folders': [], 'views': [['A', 'One'], ['C', 'Three']]}
    assert vp_common.spec_for(ROWS, [])['views'] == []
    for spec in (folders, top_and_c, listed):
        picked = vp_common.select_rows(ROWS, spec)
        assert picked == [r for r in ROWS if r in picked]


def test_describe_spec():
    assert vp_common.describe_spec(None) == 'All viewpoints'
    assert vp_common.describe_spec({'mode': 'folders', 'folders': ['']}) == 'Folder (top level)'
    assert vp_common.describe_spec({'mode': 'folders', 'folders': ['A', 'B']}) == '2 folders'
    assert vp_common.describe_spec({'mode': 'list', 'views': [['', 'a']]}) == '1 viewpoint'


def test_apply_order():
    order = [['C', 'Three'], ['', 'Top'], ['', 'Top'], ['Q', 'Missing']]
    names = [r['name'] for r in vp_common.apply_order(ROWS, order)]
    assert names == ['Three', 'Top', 'One', 'Two', 'Four']
    assert vp_common.apply_order(ROWS, None) == ROWS


def test_same_camera():
    a = {'position': (0, 0, 0), 'rotation': (0, 0, 0, 1)}
    assert vp_common.same_camera(a, {'position': (0.0005, 0, 0), 'rotation': (0, 0, 0, -1)})
    assert not vp_common.same_camera(a, {'position': (0.01, 0, 0), 'rotation': (0, 0, 0, 1)})
    turned = {'position': (0, 0, 0), 'rotation': (0, 0, 0.0087265, 0.9999619)}   # 1 degree
    assert not vp_common.same_camera(a, turned)
    assert vp_common.same_camera(a, turned, angle_tol_deg=1.5)
    assert not vp_common.same_camera(a, None)
    assert not vp_common.same_camera(a, {'position': (0, 0, 0), 'rotation': None})


def test_report_step_and_cancel():
    class Cancelled(Exception):
        pass

    def stop(fraction, label):
        raise Cancelled()
    assert vp_common.report_step(None, 0.5, 'x') is False
    assert vp_common.report_step(lambda f, l: None, 0.5, 'x') is False
    assert vp_common.report_step(lambda f, l: False, 0.5, 'x') is True
    assert vp_common.report_step(stop, 0.5, 'x') is True
    assert vp_common.is_cancel(Cancelled())
    raises(ValueError, vp_common.report_step, lambda f, l: int('x'), 0.1, 'y')


# ---- API half through the fake -------------------------------------------------------------


def test_view_rows_walk_the_tree():
    doc = make_doc()
    tree(doc)
    with nav.FakeNav(doc) as fake:
        extend(fake.Api)
        rows = vp_common.view_rows(doc)
    assert [(r['folder'], r['name']) for r in rows] == [('', 'Top'), ('A', 'One'), ('A/B', 'Two'), ('C', 'Three')]
    assert rows[0]['comments'] == 1 and rows[0]['path'] == 'Top' and rows[2]['path'] == 'A/B/Two'


def test_comments_of():
    item = view('V', comments=['First', 'Second'])
    comments = vp_common.comments_of(item)
    assert [c['body'] for c in comments] == ['First', 'Second']
    assert comments[0]['author'] == 'Ann' and comments[0]['status'] == 'New'


def test_add_view_keep_replace_skip():
    doc = make_doc()
    tree(doc)
    with nav.FakeNav(doc) as fake:
        extend(fake.Api)
        root = doc.SavedViewpoints.RootItem
        live, outcome = vp_common.add_view(doc, '', 'Top', viewpoint=nav.Viewpoint(), comments=['made'])
        assert outcome == 'created' and live.DisplayName == 'Top (2)'
        assert [c.Body for c in live.Comments] == ['made']
        live, outcome = vp_common.add_view(doc, 'A/B', 'Two', viewpoint=nav.Viewpoint(), policy='replace')
        assert outcome == 'replaced' and doc.SavedViewpoints.replaced == ['Two']
        b = root.Children[1].Children[1]
        assert [c.DisplayName for c in b.Children] == ['Two']
        existing, outcome = vp_common.add_view(doc, 'C', 'three', viewpoint=nav.Viewpoint(), policy='skip')
        assert outcome == 'skipped' and existing.DisplayName == 'Three'
        live, outcome = vp_common.add_view(doc, 'New/Deep', 'X', viewpoint=nav.Viewpoint())
        assert outcome == 'created'
        assert [c.DisplayName for c in root.Children][-1] == 'New'
        assert root.Children[-1].Children[0].Children[0].DisplayName == 'X'
        snap = nav.SavedViewpoint(nav.Viewpoint())
        live, outcome = vp_common.add_view(doc, '', 'Hidden', saved_item=snap)
        assert outcome == 'created' and live.DisplayName == 'Hidden'
    assert doc.transactions.count('Create viewpoint folder') >= 1


def test_clip_state_round_trip_on_a_detached_viewpoint():
    doc = make_doc()
    with nav.FakeNav(doc) as fake:
        api = extend(fake.Api)
        vp = nav.Viewpoint()
        planes = vp.ClipPlanes
        planes.Mode = api.ClipPlaneSetMode.Planes
        planes.Enabled = True
        planes.Range = nav.BoundingBox3D(nav.Point3D(0, 0, 0), nav.Point3D(10, 10, 10))
        planes.planes[0].Origin = nav.Point3D(0, 0, 3)
        planes.planes[0].Normal = nav.UnitVector3D(0, 0, -1)
        planes.planes[0].Enabled = True
        planes.planes[0].State = api.ClipPlaneState.Enabled
        state = vp_common.clip_state_of(vp)
        assert state['enabled'] and state['mode'] == 'Planes' and state['active'] == 1
        assert state['planes'][0]['origin'] == [0.0, 0.0, 3.0] and state['range'][1] == [10.0, 10.0, 10.0]
        other = nav.Viewpoint()
        vp_common.apply_clip_state(other, state)
        assert other.ClipPlanes.Enabled is True
        assert other.ClipPlanes.planes[0].alignment == api.ClipPlaneAlignment.Custom
        assert other.ClipPlanes.planes[0].Origin.t() == (0.0, 0.0, 3.0)
        assert other.ClipPlanes.planes[0].Enabled is True and other.ClipPlanes.planes[1].Enabled is False
        assert vp_common.apply_clip_state(other, None) is other


def test_set_planes_on_a_detached_viewpoint():
    doc = make_doc()
    with nav.FakeNav(doc) as fake:
        api = extend(fake.Api)
        vp = nav.Viewpoint()
        wanted = [((0, 0, 4.2), (0, 0, -1)), ((0, 0, 2.5), (0, 0, 1))]
        vp_common.set_planes(vp, wanted, ((0, 0, 0), (20, 10, 9)))
        planes = vp.ClipPlanes
        assert planes.Enabled and planes.Mode == api.ClipPlaneSetMode.Planes and planes.Linked is False
        assert planes.planes[0].Origin.t() == (0.0, 0.0, 4.2) and planes.planes[1].Normal.t() == (0.0, 0.0, 1.0)
        assert [p.Enabled for p in planes.planes] == [True, True, False, False, False, False]
        vp_common.set_planes(vp, [])
        assert planes.Enabled is False


def test_a_refused_comment_does_not_fail_the_viewpoint():
    # Regression: AddComment raising (a comment Navisworks will not take) propagated out
    # of add_view after the view was already filed, so the batch counted it as failed.
    doc = make_doc()
    tree(doc)

    def refuse(item, comment):
        raise RuntimeError('no comments today')
    doc.SavedViewpoints.AddComment = refuse
    with nav.FakeNav(doc) as fake:
        extend(fake.Api)
        live, outcome = vp_common.add_view(doc, 'A', 'Fresh', viewpoint=nav.Viewpoint(), comments=['made'])
        assert outcome == 'created' and live.DisplayName == 'Fresh'
        assert vp_common.add_comments(doc, live, ['one', 'two']) == 0


def test_choose_views_ticks_by_identity():
    rows = [{'folder': '', 'name': 'A'}, {'folder': 'F', 'name': 'B'}, {'folder': 'F', 'name': 'A'}]
    ticked = vp_common.select_rows(rows, {'mode': 'folders', 'folders': ['F']})
    marked = set(id(r) for r in ticked)
    assert [i for i, r in enumerate(rows) if id(r) in marked] == [1, 2]

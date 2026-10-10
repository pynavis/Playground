# -*- coding: utf-8 -*-
"""namo.items pure half: tree walks, ticks, boxes, tallies, keys, the complement frontier."""
import _compat

from namo import items


class Node(object):
    def __init__(self, name, children=(), parent=None):
        self.name = name
        self.Children = []
        self.Parent = parent
        for child in children:
            self.add(child)

    def add(self, child):
        child.Parent = self
        self.Children.append(child)
        return child

    def __repr__(self):
        return self.name


def _tree():
    #  A - B - D
    #    |   + E
    #    + C - F
    #        + G - H      and Z - Y
    d, e, f, h = Node('D'), Node('E'), Node('F'), Node('H')
    g = Node('G', [h])
    b = Node('B', [d, e])
    c = Node('C', [f, g])
    a = Node('A', [b, c])
    z = Node('Z', [Node('Y')])
    return a, z, dict((n.name, n) for n in (a, b, c, d, e, f, g, h, z, z.Children[0]))


def test_walk_tree_preorder_and_depth():
    a, z, n = _tree()
    order = [(node.name, depth) for node, depth in items.walk_tree([a, z], lambda x: x.Children)]
    assert order == [('A', 0), ('B', 1), ('D', 2), ('E', 2), ('C', 1), ('F', 2), ('G', 2),
                     ('H', 3), ('Z', 0), ('Y', 1)]


def test_walk_tree_max_depth():
    a, z, n = _tree()
    names = [node.name for node, depth in items.walk_tree([a], lambda x: x.Children, max_depth=1)]
    assert names == ['A', 'B', 'C']


def test_ticker_cancels_on_false_only():
    calls = []

    def tick(done, total):
        calls.append(done)
        return None

    t = items.Ticker(tick, every=2)
    for _ in range(5):
        t.step()
    t.finish()
    assert calls == [2, 4, 5]

    def stop(done, total):
        return False

    t = items.Ticker(stop, every=1)
    _compat.raises(items.Cancelled, t.step)


def test_ticker_none_is_free():
    t = items.Ticker(None)
    for _ in range(1000):
        t.step()
    t.finish()
    assert t.done == 1000


def test_union_and_box_helpers():
    box = items.union_boxes([((0, 0, 0), (1, 1, 1)), None, ((-1, 2, 0.5), (0.5, 3, 4))])
    assert box == ((-1, 0, 0), (1, 3, 4))
    assert items.union_boxes([None]) is None
    assert items.union_boxes([]) is None
    assert items.box_center(box) == (0.0, 1.5, 2.0)
    assert items.box_size(box) == (2, 3, 4)
    assert items.box_center(None) is None


def test_value_text():
    assert items.value_text(None) == items.NO_VALUE
    assert items.value_text('  ') == items.NO_VALUE
    assert items.value_text(True) == 'Yes'
    assert items.value_text(2.5000) == '2.5'
    assert items.value_text(3.0) == '3'
    assert items.value_text(-0.0) == '0'
    assert items.value_text((1.0, 2.5, 3)) == '1, 2.5, 3'
    assert items.value_text('Ducts') == 'Ducts'
    assert items.value_text(12) == '12'


def test_tally_order_is_stable():
    result = items.tally(['b', 'a', 'B', 'a', 'c', 'b'])
    assert result == [('a', 2), ('b', 2), ('B', 1), ('c', 1)]


def test_key_text():
    assert items.key_text(r'C:\Models\ARCH.nwc', '0/1/5') == 'arch.nwc|0/1/5'
    assert items.key_text(None, 'x') == '|x'


def test_dedupe_keeps_first():
    assert items.dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]
    assert items.dedupe(['a', 'A', 'b'], key=str.lower) == ['a', 'b']


def test_item_list_flag():
    out = items.ItemList([1, 2])
    assert out.sampled is False
    out.sampled = True
    assert out.sampled and list(out) == [1, 2]


def test_frontier_excludes_kept_subtrees():
    a, z, n = _tree()
    keep = [n['E'], n['G']]
    ancestors = items.ancestor_closure(keep, lambda x: x.Parent)
    assert set(x.name for x in ancestors) == set(['A', 'B', 'C'])
    out = items.frontier([a, z], lambda x: x.Children, set(keep), ancestors)
    assert [x.name for x in out] == ['D', 'F', 'Z']


def test_frontier_covers_everything_else():
    a, z, n = _tree()
    keep = [n['H']]
    ancestors = items.ancestor_closure(keep, lambda x: x.Parent)
    out = items.frontier([a, z], lambda x: x.Children, set(keep), ancestors)
    assert [x.name for x in out] == ['B', 'F', 'Z']
    # every node is either under the frontier, kept, or an ancestor of a kept node
    covered = set()
    for top in out:
        for node, _depth in items.walk_tree([top], lambda x: x.Children):
            covered.add(node.name)
    assert covered == set(['B', 'D', 'E', 'F', 'Z', 'Y'])


def test_frontier_keep_root_and_empty_keep():
    a, z, n = _tree()
    out = items.frontier([a, z], lambda x: x.Children, set([a]), set())
    assert [x.name for x in out] == ['Z']
    out = items.frontier([a, z], lambda x: x.Children, set(), set())
    assert [x.name for x in out] == ['A', 'Z']


def test_frontier_nested_keeps():
    a, z, n = _tree()
    keep = [n['C'], n['H']]          # H is inside C: C wins
    ancestors = items.ancestor_closure(keep, lambda x: x.Parent)
    out = items.frontier([a, z], lambda x: x.Children, set(keep), ancestors)
    assert [x.name for x in out] == ['B', 'Z']


def test_revit_property_table_is_well_formed():
    for field in ('element_id', 'unique_id', 'ifc_guid', 'category', 'family', 'type'):
        pairs = items.REVIT_PROPERTIES[field]
        assert pairs and all(len(p) == 2 for p in pairs)


# =============================================================================
# A fake Navisworks layer, shared by test_camera, test_paint, test_clashdata and
# test_images. It mirrors ONLY the members namo calls, with the names and shapes in
# dev/api/*.txt (and pynavis' public functions), so the API halves can be driven for
# Python-level mistakes on both engines. It proves nothing about Navisworks itself.
# =============================================================================

import contextlib  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402


class _Ns(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Enum(object):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<%s>' % self.name

    def __eq__(self, other):
        return isinstance(other, _Enum) and other.name == self.name

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.name)

    def __deepcopy__(self, memo):
        return self


def _enum(*names):
    return _Ns(**dict((n, _Enum(n)) for n in names))


class Point3D(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = float(x), float(y), float(z)

    def t(self):
        return (self.X, self.Y, self.Z)


class Vector3D(Point3D):
    pass


class UnitVector3D(Point3D):
    def __init__(self, x=0.0, y=0.0, z=1.0):
        n = (x * x + y * y + z * z) ** 0.5
        Point3D.__init__(self, x / n, y / n, z / n)


class Rotation3D(object):
    def __init__(self, a=0.0, b=0.0, c=0.0, d=1.0):
        self.A, self.B, self.C, self.D = float(a), float(b), float(c), float(d)


class BoundingBox3D(object):
    def __init__(self, low=None, high=None):
        self.Min = low if low is not None else Point3D(1, 1, 1)
        self.Max = high if high is not None else Point3D(-1, -1, -1)

    @property
    def IsEmpty(self):
        return self.Min.X > self.Max.X


class Color(object):
    def __init__(self, r, g, b):
        self.R, self.G, self.B = float(r), float(g), float(b)


class ClipPlane(object):
    def __init__(self):
        self.Origin = Point3D()
        self.Normal = UnitVector3D(0, 0, 1)
        self.State = None
        self.Enabled = False
        self.alignment = None

    def AlignToPick(self, alignment, origin, normal):
        self.alignment, self.Origin, self.Normal = alignment, origin, normal


class ClipPlaneSet(object):
    def __init__(self):
        self.Enabled = False
        self.Mode = None
        self.Linked = True
        self.Range = BoundingBox3D()
        self.Box = BoundingBox3D()
        self.planes = [ClipPlane() for _ in range(6)]
        self.oriented = None

    def Size(self):
        return len(self.planes)

    def Get(self, index):
        return self.planes[index]

    def GetOrientedBox(self, box, rotation):
        raise RuntimeError('not oriented')

    def SetOrientedBox(self, box, rotation):
        self.Box, self.oriented = box, rotation


class Viewpoint(object):
    def __init__(self):
        self.Position = Point3D(0, 0, 10)
        self.Rotation = Rotation3D()
        self.Projection = None
        self.HeightField = 1.0
        self.FocalDistance = 10.0
        self.HasFocalDistance = True
        self.AspectRatio = 1.5
        self.VerticalExtentAtFocalDistance = 8.0
        self.ClipPlanes = ClipPlaneSet()
        self.aligned = []
        self.zoomed = None

    def CreateCopy(self):
        import copy
        return copy.deepcopy(self)

    def AlignDirection(self, v):
        self.aligned.append(('direction', v.t()))

    def AlignUp(self, v):
        self.aligned.append(('up', v.t()))

    def ZoomBox(self, box):
        self.zoomed = (box.Min.t(), box.Max.t())

    def GetCamera(self):
        return '{"camera": 1}'


class CurrentViewpoint(object):
    def __init__(self, viewpoint):
        self.vp = viewpoint
        self.writes = []

    def CreateCopy(self):
        return self.vp.CreateCopy()

    def CopyFrom(self, viewpoint):
        self.writes.append(viewpoint)
        self.vp = viewpoint.CreateCopy()


_GUID = [0]


def _new_guid():
    _GUID[0] += 1
    return '00000000-0000-0000-0000-%012d' % _GUID[0]


class SavedItem(object):
    def __init__(self):
        self.Guid = _new_guid()
        self.DisplayName = ''
        self.Parent = None
        self.Comments = []


class GroupItem(SavedItem):
    def __init__(self):
        SavedItem.__init__(self)
        self.Children = []


class FolderItem(GroupItem):
    pass


class SavedViewpoint(SavedItem):
    def __init__(self, viewpoint=None):
        SavedItem.__init__(self)
        self.Viewpoint = viewpoint


class Comment(object):
    def __init__(self, body, status, author=None):
        self.Body, self.Status, self.Author = body, status, author


class CommentCollection(list):
    def __init__(self, other=None):
        list.__init__(self, other or [])

    def Add(self, item):
        self.append(item)

    @property
    def Count(self):
        return len(self)


class Assignee(object):
    def __init__(self, name=None):
        self.DisplayName = name or ''
        self.Assigned = bool(name)

    def Unassign(self):
        self.Assigned = False


class SavedViewpoints(object):
    def __init__(self):
        self.RootItem = FolderItem()
        self.CurrentSavedViewpoint = None
        self.comments = []

    def AddCopy(self, *args):
        parent, item = (self.RootItem, args[0]) if len(args) == 1 else args
        import copy
        clone = copy.copy(item)
        clone.Guid = _new_guid()
        if isinstance(item, GroupItem):
            clone.Children = []
        clone.Parent = None if parent is self.RootItem else parent
        clone.Comments = []
        parent.Children.append(clone)

    def AddComment(self, item, comment):
        item.Comments.append(comment)
        self.comments.append(comment)


class ModelItem(object):
    def __init__(self, name, children=(), geometry=False, hidden=False, model=None, box=None,
                 props=None, klass='Solid'):
        self.DisplayName = name
        self.ClassDisplayName = klass
        self.Children = []
        self.Parent = None
        self.HasGeometry = geometry
        self.IsHidden = hidden
        self.Model = model
        self.HasModel = model is not None
        self.box = box
        self.props = props or {}
        self.object = None
        self.color = None
        for child in children:
            child.Parent = self
            self.Children.append(child)

    @property
    def DescendantsAndSelf(self):
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.Children))

    def FindFirstObjectAncestor(self):
        return self.object

    def BoundingBox(self):
        boxes = [n.box for n in self.DescendantsAndSelf if n.box is not None]
        if not boxes:
            return BoundingBox3D()
        box = items.union_boxes(boxes)
        return BoundingBox3D(Point3D(*box[0]), Point3D(*box[1]))

    def Equals(self, other):
        return self is other

    @property
    def PropertyCategories(self):
        cats = {}
        for (cat, name), value in sorted(self.props.items()):
            cats.setdefault(cat, []).append(_Ns(DisplayName=name, Value=value))
        return [_Ns(DisplayName=cat, Properties=cats[cat]) for cat in sorted(cats)]

    def FindFirstGeometry(self):
        for node in self.DescendantsAndSelf:
            if node.HasGeometry:
                return node.Geometry
        return None

    @property
    def Geometry(self):
        r, g, b = self.color or (0.5, 0.5, 0.5)
        return _Ns(ActiveColor=Color(r, g, b), ActiveTransparency=0.25)


class ModelItemCollection(list):
    def Add(self, item):
        self.append(item)

    @property
    def Count(self):
        return len(self)

    def BoundingBox(self):
        box = items.union_boxes(items._box_tuple(i.BoundingBox()) for i in self)
        if box is None:
            return BoundingBox3D()
        return BoundingBox3D(Point3D(*box[0]), Point3D(*box[1]))


class DocumentModels(object):
    def __init__(self, models):
        self.models = models
        self.calls = []

    @property
    def Count(self):
        return len(self.models)

    def __getitem__(self, index):
        return self.models[index]

    def _rec(self, name, coll, value=None):
        self.calls.append((name, list(coll), value))

    def OverridePermanentColor(self, coll, color):
        self._rec('color', coll, (color.R, color.G, color.B))

    def OverridePermanentTransparency(self, coll, value):
        self._rec('transparency', coll, value)

    def OverrideTemporaryColor(self, coll, color):
        self._rec('temp_color', coll, (color.R, color.G, color.B))

    def OverrideTemporaryTransparency(self, coll, value):
        self._rec('temp_transparency', coll, value)

    def ResetPermanentMaterials(self, coll):
        self._rec('reset', coll)

    def ResetAllPermanentMaterials(self):
        self.calls.append(('reset_all', None, None))

    def ResetAllTemporaryMaterials(self):
        self.calls.append(('reset_temp', None, None))

    def SetHidden(self, coll, flag):
        self._rec('hidden', coll, flag)

    def CreatePathId(self, item):
        node, path = item, []
        while node.Parent is not None:
            path.append(str(node.Parent.Children.index(node)))
            node = node.Parent
        index = [m.RootItem for m in self.models].index(node)
        return _Ns(ModelIndex=index, PathId='/'.join(reversed(path)) or 'a')


class Model(object):
    def __init__(self, source, root=None, units='Meters'):
        self.SourceFileName = source
        self.FileName = source.replace('.rvt', '.nwc')
        self.Units = units
        self.RootItem = root


class Document(object):
    def __init__(self, models=(), u2m=1.0):
        self.CurrentViewpoint = CurrentViewpoint(Viewpoint())
        self.SavedViewpoints = SavedViewpoints()
        self.Models = DocumentModels(list(models))
        self.CurrentSelection = _Ns(SelectedItems=[], CopyFrom=self._select)
        self.selected = None
        self.transactions = []
        self.Units = 'Meters'
        self.u2m = u2m
        self.clash_tests = []
        self.clash_data = None
        self.box = BoundingBox3D(Point3D(0, 0, 0), Point3D(20, 10, 9))
        self.ActiveView = _Ns(GetClippingPlanes=lambda: '{"planes": []}',
                              TrySetClippingPlanes=lambda text: text.startswith('{'))
        self.images = []

    def _select(self, coll):
        self.selected = list(coll)

    def GetBoundingBox(self, ignore_hidden):
        return self.box

    def GenerateImage(self, style, width, height, sectioning):
        self.images.append((str(style), width, height, sectioning))
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Bitmap
        return Bitmap(width, height)


def _make_api(doc):
    api = _Ns(
        Point3D=Point3D, Vector3D=Vector3D, UnitVector3D=UnitVector3D, Rotation3D=Rotation3D,
        BoundingBox3D=BoundingBox3D, Color=Color, FolderItem=FolderItem, GroupItem=GroupItem,
        SavedItem=SavedItem, SavedViewpoint=SavedViewpoint, Comment=Comment,
        CommentCollection=CommentCollection, Assignee=Assignee, ModelItem=ModelItem,
        ModelItemCollection=ModelItemCollection,
        ViewpointProjection=_enum('Perspective', 'Orthographic'),
        ClipPlaneSetMode=_enum('Planes', 'Box'),
        ClipPlaneAlignment=_enum('Custom', 'Top', 'View'),
        ClipPlaneState=_enum('Default', 'Enabled', 'Disabled'),
        ImageGenerationStyle=_enum('Scene', 'ScenePlusOverlay', 'SceneUsingRayTrace'),
        CommentStatus=_enum('New', 'Active', 'Approved', 'Resolved'),
    )
    doc.CurrentViewpoint.vp.Projection = api.ViewpointProjection.Perspective
    return api


class ClashResult(SavedItem):
    def __init__(self, name, a=None, b=None, center=(0, 0, 0), status='New', distance=-0.01):
        SavedItem.__init__(self)
        self.DisplayName = name
        self.Item1, self.Item2 = a, b
        self.CompositeItem1 = self.CompositeItem2 = None
        self.Center = Point3D(*center) if center is not None else None
        self.Status = _Enum(status)
        self.Distance = distance
        self.CreatedTime = _Ns(Year=2026, Month=10, Day=1, Hour=8, Minute=30, Second=0)
        self.ApprovedTime = None
        self.ResolvedTime = None
        self.ApprovedBy = Assignee(None)
        self.AssignedTo = Assignee(None)
        self.Description = 'desc ' + name
        self.Priority = 3
        self.Comments = CommentCollection([Comment('first', None)])


class ClashResultGroup(GroupItem):
    def __init__(self, name, children=()):
        GroupItem.__init__(self)
        self.DisplayName = name
        for child in children:
            child.Parent = self
            self.Children.append(child)


class ClashTest(GroupItem):
    def __init__(self, name, children=()):
        GroupItem.__init__(self)
        self.DisplayName = name
        for child in children:
            child.Parent = self
            self.Children.append(child)


class FakeTestsData(object):
    def __init__(self):
        self.calls = []

    def TestsEditResultAssignedTo(self, result, who):
        self.calls.append(('assigned', result.DisplayName, who.DisplayName if who.Assigned else None))

    def TestsEditResultDescription(self, result, text):
        self.calls.append(('description', result.DisplayName, text))

    def TestsEditResultPriority(self, result, value):
        self.calls.append(('priority', result.DisplayName, value))

    def TestsEditResultComments(self, result, comments):
        self.calls.append(('comments', result.DisplayName, [c.Body for c in comments]))

    def TestsViewpointForResult(self, result):
        return Viewpoint()

    def TestsImageForResult(self, result, style, width, height):
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Bitmap
        self.calls.append(('image', result.DisplayName, str(style)))
        return Bitmap(width, height)

    def ResolveGuid(self, guid):
        wanted = str(guid).lower()
        stack = list(getattr(self, 'tests', []))
        while stack:
            node = stack.pop()
            if str(node.Guid).lower() == wanted:
                return node
            stack.extend(getattr(node, 'Children', []))
        return None


def _fake_snapshot_results(clash):
    """Mirrors pynavis.clash.snapshot_results' walk and keys (model_a/b left blank,
    the way an element without HasModel comes out)."""
    def snapshot_results(test, doc=None, progress=None):
        rows = []

        def walk(children, group_name):
            for child in children:
                if isinstance(child, ClashResultGroup):
                    walk(child.Children, child.DisplayName)
                elif isinstance(child, ClashResult):
                    c = child.Center
                    rows.append({'id': len(rows), 'name': child.DisplayName,
                                 'center': (c.X, c.Y, c.Z) if c is not None else None,
                                 'item_a': child.Item1.DisplayName if child.Item1 else '',
                                 'item_b': child.Item2.DisplayName if child.Item2 else '',
                                 'item_a_name': '', 'item_b_name': '', 'level': None, 'grid': None,
                                 'model_a': '', 'model_b': '', 'status': str(child.Status),
                                 'assigned': '', 'group': group_name})
                    if progress is not None and len(rows) % 2 == 0 and progress(len(rows)) == False:  # noqa: E712
                        raise clash.Cancelled()
        walk(test.Children, None)
        if progress is not None and progress(len(rows)) == False:  # noqa: E712
            raise clash.Cancelled()
        return rows
    return snapshot_results


class FakeNav(object):
    """with FakeNav(doc) as nav: ... installs fake pynavis/Autodesk modules in
    sys.modules (restored on exit). nav.Api, nav.doc, nav.clash, nav.view."""

    NAMES = ('pynavis', 'pynavis._api', 'pynavis.viewpoints', 'pynavis.clash', 'pynavis.doc',
             'pynavis.props', 'pynavis.view', 'Autodesk', 'Autodesk.Navisworks',
             'Autodesk.Navisworks.Api', 'Autodesk.Navisworks.Api.Clash')

    def __init__(self, doc=None):
        self.doc = doc or Document()
        self.saved = {}

    def __enter__(self):
        for name in self.NAMES:
            self.saved[name] = sys.modules.get(name)
        self.Api = _make_api(self.doc)
        doc = self.doc

        package = types.ModuleType('pynavis')
        package.__path__ = []
        api_module = types.ModuleType('pynavis._api')
        api_module.Api = self.Api
        api_module.Application = _Ns(ActiveDocument=doc)

        viewpoints = types.ModuleType('pynavis.viewpoints')

        @contextlib.contextmanager
        def transaction(name, d=None):
            (d or doc).transactions.append(name)
            yield None
        viewpoints.transaction = transaction

        doc_module = types.ModuleType('pynavis.doc')

        def walk(d=None):
            def flatten(children, folders):
                for item in children:
                    if isinstance(item, FolderItem):
                        for pair in flatten(item.Children, folders + [item.DisplayName]):
                            yield pair
                    else:
                        yield folders, item
            return flatten((d or doc).SavedViewpoints.RootItem.Children, [])
        doc_module.walk_saved_viewpoints = walk
        doc_module.get_doc = lambda: doc

        props = types.ModuleType('pynavis.props')
        props.get = lambda item, category, prop, by_display=True: item.props.get((category, prop))

        view = types.ModuleType('pynavis.view')
        view.calls = []
        view.isolate = lambda its, d=None: view.calls.append(('isolate', list(its))) or len(list(its))
        view.unhide_all = lambda d=None: view.calls.append(('unhide_all',))
        view.zoom_selected = lambda d=None: view.calls.append(('zoom',)) or True

        clash_api = types.ModuleType('Autodesk.Navisworks.Api.Clash')
        clash_api.ClashResult = ClashResult
        clash_api.ClashResultGroup = ClashResultGroup
        autodesk = types.ModuleType('Autodesk')
        autodesk.__path__ = []
        nw = types.ModuleType('Autodesk.Navisworks')
        nw.__path__ = []
        nw_api = types.ModuleType('Autodesk.Navisworks.Api')
        nw_api.__path__ = []
        autodesk.Navisworks = nw
        nw.Api = nw_api
        nw_api.Clash = clash_api

        clash = types.ModuleType('pynavis.clash')
        clash.Cancelled = type('Cancelled', (Exception,), {})
        clash.walk_tests = lambda d=None: iter((d or doc).clash_tests)
        clash.get_clash = lambda d=None: _Ns(TestsData=(d or doc).clash_data)
        clash.units_to_meters = lambda d=None: (d or doc).u2m
        clash.snapshot_results = _fake_snapshot_results(clash)
        self.clash = clash

        package._api = api_module
        package.viewpoints = viewpoints
        package.doc = doc_module
        package.props = props
        package.view = view
        package.clash = clash
        modules = {'pynavis': package, 'pynavis._api': api_module, 'pynavis.viewpoints': viewpoints,
                   'pynavis.clash': clash, 'pynavis.doc': doc_module, 'pynavis.props': props,
                   'pynavis.view': view, 'Autodesk': autodesk, 'Autodesk.Navisworks': nw,
                   'Autodesk.Navisworks.Api': nw_api, 'Autodesk.Navisworks.Api.Clash': clash_api}
        for name in self.NAMES:
            sys.modules[name] = modules[name]
        self.view = view
        return self

    def __exit__(self, *exc):
        for name in self.NAMES:
            if self.saved[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = self.saved[name]
        return False


def model_tree():
    """Two models: ARCH (walls with a geometry child each) and MEP (a duct, a hidden box)."""
    wall1_geo = ModelItem('Wall 1 solid', geometry=True, box=((0, 0, 0), (1, 5, 3)))
    wall2_geo = ModelItem('Wall 2 solid', geometry=True, box=((5, 0, 0), (6, 5, 3)))
    wall1 = ModelItem('Wall 1', [wall1_geo], klass='Wall',
                      props={('Element', 'Category'): 'Walls', ('Element ID', 'Value'): 101,
                             ('Element', 'UniqueId'): 'u-101'})
    wall2 = ModelItem('Wall 2', [wall2_geo], klass='Wall', props={('Element', 'Category'): 'Walls'})
    wall1_geo.object = wall1
    wall2_geo.object = wall2
    level = ModelItem('Level 1', [wall1, wall2])
    arch_root = ModelItem('ARCH.nwc', [level])
    duct_geo = ModelItem('Duct solid', geometry=True, box=((2, 2, 2), (4, 2.5, 2.5)))
    duct = ModelItem('Duct', [duct_geo], props={('Element', 'Category'): 'Ducts'})
    duct_geo.object = duct
    hidden = ModelItem('Hidden box', geometry=True, hidden=True, box=((9, 9, 9), (10, 10, 10)))
    mep_root = ModelItem('MEP.nwc', [duct, hidden])
    arch = Model(r'C:\Models\ARCH.rvt', arch_root)
    mep = Model(r'C:\Models\MEP.rvt', mep_root, units='Millimeters')
    arch_root.Model, arch_root.HasModel = arch, True
    mep_root.Model, mep_root.HasModel = mep, True
    doc = Document([arch, mep])
    named = dict((n.DisplayName, n) for root in (arch_root, mep_root) for n in root.DescendantsAndSelf)
    return doc, named


# ---- items API half through the fake layer ---------------------------------------


def test_api_geometry_items_objects_and_budget():
    doc, n = model_tree()
    with FakeNav(doc):
        roots = items.roots()
        assert [r.DisplayName for r in roots] == ['ARCH.nwc', 'MEP.nwc']
        geo = items.geometry_items(roots)
        assert [g.DisplayName for g in geo] == ['Wall 1 solid', 'Wall 2 solid', 'Duct solid', 'Hidden box']
        assert geo.sampled is False
        capped = items.geometry_items(roots, budget=2)
        assert len(capped) == 2 and capped.sampled
        overlapping = items.geometry_items([n['Level 1'], n['Wall 1']])
        assert [g.DisplayName for g in overlapping] == ['Wall 1 solid', 'Wall 2 solid']
        objs = items.objects(roots)
        assert [o.DisplayName for o in objs] == ['Wall 1', 'Wall 2', 'Duct', 'Hidden box']
        ticks = []
        items.geometry_items(roots, tick=lambda done, total: ticks.append(done))
        assert ticks and ticks[-1] == 10
        _compat.raises(items.Cancelled, items.objects, roots, lambda done, total: False)


def test_api_identity_and_paths():
    doc, n = model_tree()
    with FakeNav(doc):
        assert items.visible(n['Wall 1 solid'])
        assert not items.visible(n['Hidden box'])
        assert items.tree_path(n['Wall 1 solid']) == 'ARCH.nwc > Level 1 > Wall 1 > Wall 1 solid'
        assert items.model_name(n['Duct solid']) == 'MEP.rvt'
        assert items.model_of(n['Wall 2']).Units == 'Meters'
        assert items.key(n['Wall 2 solid']) == 'arch.rvt|0/1/0'
        assert items.keys([n['Duct'], n['MEP.nwc']]) == ['mep.rvt|0', 'mep.rvt|a']
        rows = items.models()
        assert [(r['index'], r['name'], r['units']) for r in rows] == [
            (0, 'ARCH.rvt', 'Meters'), (1, 'MEP.rvt', 'Millimeters')]


def test_api_boxes_props_and_tallies():
    doc, n = model_tree()
    with FakeNav(doc):
        assert items.bbox(n['Level 1']) == ((0, 0, 0), (6, 5, 3))
        assert items.bbox([n['Wall 1'], n['Duct']]) == ((0, 0, 0), (4, 5, 3))
        assert items.center(n['Wall 1']) == (0.5, 2.5, 1.5)
        assert items.size(n['Duct']) == (2, 0.5, 0.5)
        ids = items.revit_ids(n['Wall 1 solid'])
        assert ids['element_id'] == '101' and ids['unique_id'] == 'u-101' and ids['category'] == 'Walls'
        assert ids['family'] is None
        assert items.category(n['Duct solid']) == 'Ducts'
        assert items.category(n['Hidden box']) == 'Solid'
        assert items.prop(n['Wall 1 solid'], 'Element', 'Category') == 'Walls'
        assert items.prop(n['Wall 1 solid'], 'Element', 'Category', fallback_to_object=False) is None
        sampled = items.sample_properties([n['Wall 1'], n['Wall 2'], n['Duct']])
        assert sampled[0] == ('Element', 'Category', 3)
        values = items.distinct_values([n['Wall 1'], n['Wall 2'], n['Duct'], n['Hidden box']],
                                       'Element', 'Category')
        assert values == [('Walls', 2), ('(no value)', 1), ('Ducts', 1)]


def test_api_selection_visibility_and_complement():
    doc, n = model_tree()
    with FakeNav(doc) as nav:
        assert items.select([n['Wall 1'], n['Duct']]) == 2
        assert doc.selected == [n['Wall 1'], n['Duct']]
        items.select([n['Duct']], zoom=True)
        assert ('zoom',) in nav.view.calls
        assert items.hide([n['Duct']]) == 1
        assert doc.transactions == ['Hide items']
        assert doc.Models.calls[-1] == ('hidden', [n['Duct']], True)
        assert items.hide([]) == 0
        out = items.complement([n['Wall 1']])
        assert [o.DisplayName for o in out] == ['Wall 2', 'MEP.nwc']
        coll = items.collection([n['Wall 1']])
        assert items.collection(coll) is coll

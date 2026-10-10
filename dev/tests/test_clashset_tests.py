# -*- coding: utf-8 -*-
"""namo.clashset_tests: definitions, lengths, set paths, and the API half (configure,
write_test, resolve_side, read_definition) through a fake clash layer.

The fake layer here (ClashNav) extends test_items.FakeNav with clash tests, selection
sets and selection sources; the other clash test files import it as `cf`."""
import sys
import types

import _compat
import test_items as nav

from namo import clashset_tests as defs


# ---- fake clash layer ---------------------------------------------------------------------


class Flag(object):
    """A flags enum value that supports | and int() like a .NET [Flags] enum."""

    def __init__(self, value, name=''):
        self.value = int(value)
        self.name = name

    def __or__(self, other):
        return Flag(self.value | int(other), 'combined')

    def __int__(self):
        return self.value

    def __eq__(self, other):
        return int(self) == int(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return self.value


PrimitiveTypes = nav._Ns(None_=Flag(0), Triangles=Flag(1, 'Triangles'), Lines=Flag(2, 'Lines'),
                         Points=Flag(4, 'Points'), SnapPoints=Flag(8, 'SnapPoints'),
                         Text=Flag(16, 'Text'))


class SelectionSourceCollection(list):
    def Add(self, item):
        self.append(item)

    @property
    def Count(self):
        return len(self)


class FakeSource(object):
    def __init__(self, item):
        self.item = item

    def __str__(self):
        return 'source:%s' % self.item.DisplayName


class FakeSelection(object):
    def __init__(self):
        self.sources = []
        self.explicit = []

    def CopyFrom(self, value):
        if isinstance(value, SelectionSourceCollection):
            self.sources, self.explicit = list(value), []
        else:
            self.sources, self.explicit = [], list(value)

    @property
    def HasSelectionSources(self):
        return bool(self.sources)

    @property
    def SelectionSources(self):
        return list(self.sources)

    @property
    def HasExplicitSelection(self):
        return bool(self.explicit)

    @property
    def ExplicitSelection(self):
        return list(self.explicit)


class FakeClashSelection(object):
    def __init__(self):
        self.Selection = FakeSelection()
        self.PrimitiveTypes = PrimitiveTypes.Triangles
        self.SelfIntersect = False


ClashTestType = nav._enum('Hard', 'HardConservative', 'Clearance', 'Duplicate', 'Custom')
ClashResultStatus = nav._enum('New', 'Active', 'Reviewed', 'Approved', 'Resolved')


class Kids(list):
    """A SavedItemCollection stand-in: Add, Clear, Count, indexing."""

    def Add(self, item):
        self.append(item)

    def Clear(self):
        del self[:]

    @property
    def Count(self):
        return len(self)


def deep_copy(item):
    """A detached copy like SavedItem.CreateCopy: children copied, new Guid, no Parent."""
    import copy
    clone = copy.copy(item)
    clone.Guid = nav._new_guid()
    if hasattr(item, 'Children'):
        clone.Children = Kids(deep_copy(child) for child in item.Children)
        for child in clone.Children:
            child.Parent = clone
    clone.Comments = nav.CommentCollection(getattr(item, 'Comments', []) or [])
    clone.Parent = None
    return clone


class Result(nav.ClashResult):
    def CreateCopy(self):
        return deep_copy(self)


class Group(nav.ClashResultGroup):
    def __init__(self, name, children=()):
        nav.ClashResultGroup.__init__(self, name, children)
        self.AssignedTo = nav.Assignee(None)
        self.Status = nav._Enum('New')

    def CreateCopy(self):
        return deep_copy(self)


class ClashTest(nav.ClashTest):
    def __init__(self, name='', children=()):
        nav.ClashTest.__init__(self, name, children)
        self.Children = Kids(self.Children)
        self.SelectionA = FakeClashSelection()
        self.SelectionB = FakeClashSelection()
        self.TestType = ClashTestType.Hard
        self.Tolerance = 0.0
        self.MergeComposites = False

    def CreateCopy(self):
        clone = deep_copy(self)
        for attr in ('SelectionA', 'SelectionB'):
            source = getattr(self, attr)
            fresh = FakeClashSelection()
            fresh.Selection.sources = list(source.Selection.sources)
            fresh.Selection.explicit = list(source.Selection.explicit)
            fresh.PrimitiveTypes = source.PrimitiveTypes
            fresh.SelfIntersect = source.SelfIntersect
            setattr(clone, attr, fresh)
        return clone


class FakeClashData(nav.FakeTestsData):
    """TestsData with tests at the root (data.Tests) and every edit recorded."""

    def __init__(self, doc):
        nav.FakeTestsData.__init__(self)
        self.doc = doc
        self.Tests = doc.clash_tests
        self.tests = self.Tests

    def TestsAddCopy(self, test):
        clone = test.CreateCopy()
        clone.Guid = nav._new_guid()
        self.Tests.append(clone)
        self.calls.append(('add', clone.DisplayName))

    def TestsEditTestFromCopy(self, test, copy):
        for attr in ('TestType', 'Tolerance', 'MergeComposites', 'SelectionA', 'SelectionB'):
            setattr(test, attr, getattr(copy, attr))
        self.calls.append(('edit_test', test.DisplayName))

    def TestsEditDisplayName(self, item, name):
        self.calls.append(('rename', item.DisplayName, name))
        item.DisplayName = name

    def TestsReplaceWithCopy(self, *args):
        if len(args) == 2:
            index, new_test = args
            collection = self.Tests
        else:
            parent, index, new_test = args
            collection = parent.Children
        old = collection[index]
        old.dead = True
        clone = deep_copy(new_test)
        clone.Guid = old.Guid
        collection[index] = clone
        self.calls.append(('replace', index, clone.DisplayName))

    def TestsRunTest(self, test):
        self.calls.append(('run', test.DisplayName))

    def TestsEditResultStatus(self, result, status, who):
        result.Status = status
        self.calls.append(('status', result.DisplayName, str(status), who.DisplayName))

    def TestsEditResultAssignedTo(self, result, who):
        result.AssignedTo = who
        nav.FakeTestsData.TestsEditResultAssignedTo(self, result, who)

    def TestsEditResultComments(self, result, comments):
        result.Comments = nav.CommentCollection(list(comments))
        nav.FakeTestsData.TestsEditResultComments(self, result, comments)


class FakeSelectionSets(object):
    def __init__(self):
        self.RootItem = nav.FolderItem()

    def CreateSelectionSource(self, item):
        return FakeSource(item)

    def ResolveSelectionSource(self, source):
        return source.item


class FakeSet(nav.SavedItem):
    def __init__(self, name, items=(), query=None):
        nav.SavedItem.__init__(self)
        self.DisplayName = name
        self.items = list(items)
        self.query = query
        self.HasSearch = query is not None

    def GetSelectedItems(self, doc=None):
        return list(self.items)


def add_set(doc, path, items=(), query=None):
    """Adds a set at 'Folder/Name' (folders created) to the fake document."""
    names = defs.split_set_path(path)
    parent = doc.SelectionSets.RootItem
    for name in names[:-1]:
        found = None
        for child in parent.Children:
            if isinstance(child, nav.FolderItem) and child.DisplayName == name:
                found = child
        if found is None:
            found = nav.FolderItem()
            found.DisplayName = name
            found.Parent = parent
            parent.Children.append(found)
        parent = found
    item = FakeSet(names[-1], items, query)
    item.Parent = parent
    parent.Children.append(item)
    return item


def _fake_sets_module(doc):
    module = types.ModuleType('pynavis.sets')
    module.calls = []

    def find(path, d=None):
        names = defs.split_set_path(path)
        node = doc.SelectionSets.RootItem
        if len(names) == 1:
            stack = list(node.Children)
            while stack:
                item = stack.pop(0)
                if item.DisplayName == names[0]:
                    return item
                stack[0:0] = list(getattr(item, 'Children', []))
            return None
        for name in names[:-1]:
            nxt = None
            for child in node.Children:
                if isinstance(child, nav.FolderItem) and child.DisplayName == name:
                    nxt = child
            if nxt is None:
                return None
            node = nxt
        for child in node.Children:
            if child.DisplayName == names[-1]:
                return child
        return None

    def create(name, source, folder=None, doc=None):
        module.calls.append(('create', name, folder))
        path = defs.join_set_path(defs.split_set_path(folder or '') + [name])
        return add_set(doc_ref[0], path, [], source)

    def update(item, source, doc=None):
        module.calls.append(('update', item.DisplayName))
        item.query = source
        return item

    def to_dict(item, doc=None):
        return item.query if item.query is not None else {'items': len(item.items)}

    def snapshot(doc=None):
        rows = []

        def walk(children, parent_key, depth):
            for index, item in enumerate(children):
                key = parent_key + '/' + str(index) if parent_key else str(index)
                folder = isinstance(item, nav.FolderItem)
                rows.append({'guid': item.Guid, 'key': key, 'parent_key': parent_key,
                             'name': item.DisplayName, 'depth': depth, 'is_folder': folder,
                             'has_search': (not folder) and bool(getattr(item, 'HasSearch', False))})
                if folder:
                    walk(item.Children, key, depth + 1)
        walk(doc_ref[0].SelectionSets.RootItem.Children, '', 0)
        return rows

    doc_ref = [doc]
    module.find = find
    module.create = create
    module.update = update
    module.to_dict = to_dict
    module.snapshot = snapshot
    return module


class ClashNav(nav.FakeNav):
    """FakeNav plus clash tests, selection sets and sources. nav.data is the
    TestsData; nav.sets the fake pynavis.sets module."""

    EXTRA = ('pynavis.sets', 'pynavis.memory', 'pynavis.clashtest')

    def __enter__(self):
        doc = self.doc
        if not hasattr(doc, 'SelectionSets'):
            doc.SelectionSets = FakeSelectionSets()
        if doc.clash_data is None:
            doc.clash_data = FakeClashData(doc)
        self.data = doc.clash_data
        nav.FakeNav.__enter__(self)
        self.Api.PrimitiveTypes = PrimitiveTypes
        self.Api.SelectionSourceCollection = SelectionSourceCollection
        clash_api = sys.modules['Autodesk.Navisworks.Api.Clash']
        clash_api.ClashTest = ClashTest
        clash_api.ClashTestType = ClashTestType
        clash_api.ClashResultStatus = ClashResultStatus
        self.clash.ClashApi = clash_api
        self.clash.count_results = lambda test: (len(_leaves(test)), 0)
        self.extra_saved = dict((name, sys.modules.get(name)) for name in self.EXTRA)
        self.sets = _fake_sets_module(doc)
        sys.modules['pynavis.sets'] = self.sets
        sys.modules['pynavis'].sets = self.sets
        memory = types.ModuleType('pynavis.memory')
        memory.encode_items = lambda its, d: [{'m': 'x', 'i': 0, 'p': it.DisplayName} for it in its]
        memory.resolve_entries = lambda entries, d: ([], len(entries), [])
        sys.modules['pynavis.memory'] = memory
        sys.modules['pynavis'].memory = memory
        clashtest = types.ModuleType('pynavis.clashtest')
        clashtest.run = lambda test, d=None: doc.clash_data.TestsRunTest(test)
        sys.modules['pynavis.clashtest'] = clashtest
        sys.modules['pynavis'].clashtest = clashtest
        return self

    def __exit__(self, *exc):
        for name in self.EXTRA:
            if self.extra_saved.get(name) is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = self.extra_saved[name]
        return nav.FakeNav.__exit__(self, *exc)


def _leaves(test):
    out = []

    def walk(children):
        for child in children:
            if isinstance(child, nav.ClashResultGroup):
                walk(child.Children)
            elif isinstance(child, nav.ClashResult):
                out.append(child)
    walk(test.Children)
    return out


def new_doc():
    doc, named = nav.model_tree()
    return doc, named


def clash_doc():
    """A document with one test: Clash1 loose, Group 1 (Clash2, Inner (Clash3))."""
    doc, named = new_doc()
    duct, wall = named['Duct solid'], named['Wall 1 solid']
    results = [Result('Clash1', duct, wall, center=(1, 1, 1)),
               Result('Clash2', duct, wall, center=(2, 1, 1)),
               Result('Clash3', duct, wall, center=(3, 1, 1))]
    inner = Group('Inner', [results[2]])
    group = Group('Group 1', [results[1], inner])
    group.Comments = nav.CommentCollection([nav.Comment('keep me', None)])
    test = ClashTest('Ducts vs Walls', [results[0], group])
    doc.clash_tests.append(test)
    return doc, test


# ---- pure ------------------------------------------------------------------------------


def test_type_keys_and_members():
    assert defs.type_member('hard_conservative') == 'HardConservative'
    assert defs.type_key('HardConservative') == 'hard_conservative'
    assert defs.type_key('Clearance') == 'clearance'
    assert defs.type_key('Duplicate') == 'duplicate'
    assert defs.type_key('Custom') == 'custom'
    assert defs.type_key('hard') == 'hard'
    _compat.raises(ValueError, defs.type_member, 'custom')


def test_primitives_decode_and_normalise():
    members = [('triangles', 1), ('lines', 2), ('points', 4), ('snap_points', 8), ('text', 16)]
    assert defs.decode_primitives(5, members) == ['triangles', 'points']
    assert defs.decode_primitives(Flag(2), members) == ['lines']
    assert defs.decode_primitives('junk', members) == []
    assert defs.normalise_primitives(['POINTS', 'triangles', 'x']) == ['triangles', 'points']
    assert defs.normalise_primitives([]) == ['triangles']


def test_primitive_flags_combines_members():
    api = nav._Ns(PrimitiveTypes=PrimitiveTypes)
    assert int(defs.primitive_flags(['points'], api)) == 4
    assert int(defs.primitive_flags(['triangles', 'points', 'lines'], api)) == 7
    assert int(defs.primitive_flags([], api)) == 1


def test_length_text_metric_and_imperial():
    assert defs.length_text(25.0, 'Millimeters') == '25 mm'
    assert defs.length_text(2.5, 'Millimeters') == '2.5 mm'
    assert defs.length_text(-0.0384, 'Meters') == '-0.038 m'
    assert defs.length_text(1250.0, 'Millimeters') == '1,250 mm'
    assert defs.length_text(1.5416666, 'Feet') == "1' 6 1/2\""
    assert defs.length_text(None, 'Meters') == ''
    assert defs.tolerance_text(0.01, 'Millimeters') == '10 mm'
    assert defs.trim_number(-0.0001, 3) == '0'


def test_set_paths_round_trip_with_slashes():
    path = defs.join_set_path(['MEP', 'Ducts/Pipes', 'Level 1'])
    assert path == 'MEP/Ducts\\/Pipes/Level 1'
    assert defs.split_set_path(path) == ['MEP', 'Ducts/Pipes', 'Level 1']
    assert defs.set_name_of(path) == 'Level 1'
    assert defs.split_set_path('') == []
    assert defs.split_set_path(' A / B ') == ['A', 'B']


def test_normalise_and_validate_definition():
    d = defs.normalise_definition({'name': ' T ', 'type': 'Clearance', 'tolerance_m': '0.05',
                                   'a': {'sources': [{'kind': 'set', 'path': 'X'}, {'kind': 'bad'}],
                                         'primitives': ['points']},
                                   'junk': 1})
    assert d['name'] == 'T' and d['type'] == 'clearance' and d['tolerance_m'] == 0.05
    assert d['a']['sources'] == [{'kind': 'set', 'path': 'X', 'folder': False, 'search': None}]
    assert d['a']['primitives'] == ['points']
    assert 'junk' not in d
    problems = defs.validate_definition(d)
    assert problems == ['Selection B is empty.']
    assert defs.validate_definition({'name': '', 'type': 'custom'})[0] == 'The test needs a name.'


def test_describe_and_portability():
    side = defs.new_side([{'kind': 'set', 'path': 'MEP/Ducts'}, {'kind': 'model', 'name': 'A.nwc'},
                          {'kind': 'items', 'count': 1200}])
    assert defs.describe_side(side) == 'Set MEP/Ducts; Model A.nwc; 1,200 picked items'
    assert not defs.side_is_portable(side)
    assert defs.side_is_portable(defs.new_side([{'kind': 'set', 'path': 'X'}]))
    assert defs.describe_side(defs.new_side()) == '(empty)'


def test_query_from_plan_and_portability():
    query = defs.query_from_plan([[('Element', 'Category', 'equals', 'Ducts', True),
                                   ('Item', 'Name', 'exists', None, False)],
                                  [('Element', 'Category', 'equals', 'Pipes', True)]])
    assert query == {'or': [{'and': [{'category': 'Element', 'prop': 'Category', 'op': 'equals',
                                      'value': 'Ducts', 'ignore_case': True},
                                     {'category': 'Item', 'prop': 'Name', 'op': 'has_property'}]},
                            {'and': [{'category': 'Element', 'prop': 'Category', 'op': 'equals',
                                      'value': 'Pipes', 'ignore_case': True}]}]}
    assert defs.query_is_portable(query)
    assert len(defs.single_group_queries(query)) == 2
    assert not defs.query_is_portable({'or': [{'and': [{'op': 'raw', 'text': 'x'}]}]})
    assert not defs.query_is_portable({'or': [{'and': []}]})
    assert not defs.query_is_portable(None)


def test_unique_and_safe_names():
    assert defs.unique_test_names(['A', 'a', 'B'], ['b']) == ['A', 'a (2)', 'B (2)']
    assert defs.safe_test_name('  Ducts\nvs\tBeams  ') == 'Ducts vs Beams'
    assert len(defs.safe_test_name('x' * 300)) == 120


# ---- API half through the fake layer --------------------------------------------------------


def _ducts_and_walls(doc, named):
    ducts = add_set(doc, 'MEP/Ducts', [named['Duct']])
    walls = add_set(doc, 'ARCH/Walls', [named['Wall 1'], named['Wall 2']])
    return ducts, walls


def test_resolve_side_prefers_set_references():
    doc, named = new_doc()
    with ClashNav(doc):
        _ducts_and_walls(doc, named)
        side = defs.new_side([{'kind': 'set', 'path': 'MEP/Ducts'}])
        resolved = defs.resolve_side(side, doc)
        assert resolved['missing'] == []
        assert resolved['items'] is None
        assert [s.item.DisplayName for s in resolved['sources']] == ['Ducts']


def test_resolve_side_mixed_goes_explicit_with_a_note():
    doc, named = new_doc()
    with ClashNav(doc):
        _ducts_and_walls(doc, named)
        side = defs.new_side([{'kind': 'set', 'path': 'Walls'},
                              {'kind': 'model', 'name': 'mep.RVT'},
                              {'kind': 'set', 'path': 'Nope/Missing'}])
        resolved = defs.resolve_side(side, doc)
        assert resolved['sources'] is None
        names = [i.DisplayName for i in resolved['items']]
        assert names == ['Wall 1', 'Wall 2', 'MEP.nwc']
        assert resolved['missing'] == ['Selection set "Nope/Missing" is not in this model.']
        assert 'follow later set changes' in resolved['notes'][0]


def test_write_test_creates_then_updates_keeping_results():
    doc, named = new_doc()
    with ClashNav(doc) as fake:
        _ducts_and_walls(doc, named)
        definition = defs.new_definition('Ducts vs Walls', 'clearance', 0.05,
                                         defs.new_side([{'kind': 'set', 'path': 'MEP/Ducts'}]),
                                         defs.new_side([{'kind': 'set', 'path': 'ARCH/Walls'}],
                                                       primitives=['points', 'triangles']))
        ra = defs.resolve_side(definition['a'], doc)
        rb = defs.resolve_side(definition['b'], doc)
        outcome, live = defs.write_test(definition, ra, rb, 'skip', doc)
        assert outcome == 'created' and live is doc.clash_tests[0]
        assert str(live.TestType) == 'Clearance'
        assert abs(live.Tolerance - 0.05) < 1e-12
        assert int(live.SelectionB.PrimitiveTypes) == 5
        assert defs.references_sets(live)
        live.Children.append(nav.ClashResult('Clash1'))
        again, same = defs.write_test(definition, ra, rb, 'skip', doc)
        assert again == 'skipped' and same is live
        changed = dict(definition, tolerance_m=0.1)
        outcome, same = defs.write_test(changed, ra, rb, 'update', doc)
        assert outcome == 'updated' and same is live
        assert abs(live.Tolerance - 0.1) < 1e-12
        assert [c.DisplayName for c in live.Children] == ['Clash1']
        assert ('edit_test', 'Ducts vs Walls') in fake.data.calls


def test_tolerance_written_in_document_units():
    doc, named = new_doc()
    doc.Units = 'Millimeters'
    with ClashNav(doc):
        _ducts_and_walls(doc, named)
        definition = defs.new_definition('T', 'hard', 0.01,
                                         defs.new_side([{'kind': 'set', 'path': 'Ducts'}]),
                                         defs.new_side([{'kind': 'set', 'path': 'Walls'}]))
        outcome, live = defs.write_test(definition, defs.resolve_side(definition['a'], doc),
                                        defs.resolve_side(definition['b'], doc), 'skip', doc)
        assert abs(live.Tolerance - 10.0) < 1e-9


def test_read_definition_round_trip():
    doc, named = new_doc()
    with ClashNav(doc):
        ducts, walls = _ducts_and_walls(doc, named)
        ducts.query = {'or': [{'and': [{'category': 'Element', 'prop': 'Category',
                                        'op': 'equals', 'value': 'Ducts'}]}]}
        ducts.HasSearch = True
        test = ClashTest('Ducts vs Model')
        test.TestType = ClashTestType.HardConservative
        test.Tolerance = 0.002
        sources = SelectionSourceCollection()
        sources.Add(FakeSource(ducts))
        test.SelectionA.Selection.CopyFrom(sources)
        test.SelectionB.Selection.CopyFrom([named['MEP.nwc']])
        test.SelectionB.PrimitiveTypes = PrimitiveTypes.Points
        definition = defs.read_definition(test, doc)
        assert definition['type'] == 'hard_conservative'
        assert definition['a']['sources'] == [{'kind': 'set', 'path': 'MEP/Ducts', 'folder': False,
                                               'search': ducts.query}]
        assert definition['b']['sources'] == [{'kind': 'model', 'name': 'MEP.rvt'}]
        assert definition['b']['primitives'] == ['points']
        assert abs(definition['tolerance_m'] - 0.002) < 1e-12


def test_find_model_roots_by_name_and_wildcard():
    doc, named = new_doc()
    with ClashNav(doc):
        assert [r.DisplayName for r in defs.find_model_roots('arch.nwc', doc)] == ['ARCH.nwc']
        assert [r.DisplayName for r in defs.find_model_roots('*.rvt', doc)] == ['ARCH.nwc', 'MEP.nwc']
        assert defs.find_model_roots('nothing.nwc', doc) == []


def test_combine_flags_falls_back_to_integers():
    class Plain(object):                       # an enum value that refuses |
        def __init__(self, value):
            self.value = value

        def __int__(self):
            return self.value

    made = []

    def to_enum(number):
        made.append(number)
        return Plain(number)

    assert int(defs.combine_flags([Plain(1), Plain(4), Plain(2)], to_enum)) == 7
    assert made == [5, 7]
    assert defs.combine_flags([]) is None


def test_configure_leaves_default_settings_alone():
    # A plain test writes only what pynavis.clashtest.create writes: the geometry types,
    # self-intersect and merge-composites setters are not touched when nothing differs.
    doc, named = new_doc()
    with ClashNav(doc):
        _ducts_and_walls(doc, named)
        definition = defs.new_definition('T', 'hard', 0.0,
                                         defs.new_side([{'kind': 'set', 'path': 'Ducts'}]),
                                         defs.new_side([{'kind': 'set', 'path': 'Walls'}]))

        class Strict(FakeClashSelection):
            def __setattr__(self, name, value):
                if name in ('PrimitiveTypes', 'SelfIntersect') and name in self.__dict__:
                    raise RuntimeError('setter touched: %s' % name)
                object.__setattr__(self, name, value)

        test = ClashTest('x')
        test.SelectionA, test.SelectionB = Strict(), Strict()
        ra = defs.resolve_side(definition['a'], doc)
        rb = defs.resolve_side(definition['b'], doc)
        defs.configure(test, definition, ra, rb, doc)
        assert ra['notes'] == [] and rb['notes'] == []
        assert test.SelectionA.Selection.HasSelectionSources


def test_set_references_refused_fall_back_to_items_with_a_note():
    # Regression: a refused selection-source reference crashed Clash Matrix halfway.
    doc, named = new_doc()
    with ClashNav(doc):
        _ducts_and_walls(doc, named)
        definition = defs.new_definition('T', 'hard', 0.0,
                                         defs.new_side([{'kind': 'set', 'path': 'Ducts'}]),
                                         defs.new_side([{'kind': 'set', 'path': 'Walls'}]))

        class Refusing(FakeSelection):
            def CopyFrom(self, value):
                if isinstance(value, SelectionSourceCollection):
                    raise RuntimeError('no sources here')
                FakeSelection.CopyFrom(self, value)

        test = ClashTest('x')
        test.SelectionA.Selection = Refusing()
        ra = defs.resolve_side(definition['a'], doc)
        rb = defs.resolve_side(definition['b'], doc)
        defs.configure(test, definition, ra, rb, doc)
        assert [i.DisplayName for i in test.SelectionA.Selection.ExplicitSelection] == ['Duct']
        assert ra['notes'] == [defs.SET_FALLBACK_NOTE]
        assert test.SelectionB.Selection.HasSelectionSources and rb['notes'] == []

        def refuse(item):
            raise RuntimeError('no')
        doc.SelectionSets.CreateSelectionSource = refuse
        again = defs.resolve_side(definition['b'], doc)
        assert again['sources'] is None
        assert [i.DisplayName for i in again['items']] == ['Wall 1', 'Wall 2']
        assert again['notes'] == [defs.SET_FALLBACK_NOTE]


def test_result_count_walks_and_has_results_is_cheap():
    doc, test = clash_doc()
    with ClashNav(doc):
        assert defs.result_count(test) == 3
        assert defs.has_results(test)
        assert not defs.has_results(ClashTest('empty'))


def test_run_tests_goes_through_pynavis_clashtest_and_counts():
    doc, test = clash_doc()
    with ClashNav(doc) as fake:
        counts = defs.run_tests([test], doc)
        assert ('run', 'Ducts vs Walls') in fake.data.calls
        assert counts == {str(test.Guid): 3}

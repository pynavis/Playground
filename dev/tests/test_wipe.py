# -*- coding: utf-8 -*-
"""namo.wipe: option labels, the second confirmation, the result summary, and counting
and wiping through the fake Navisworks layer (with an in-memory document database)."""
import _compat

from namo import docdb, wipe


COUNTS = {'viewpoints': 24, 'sets': 3, 'clash_tests': 5, 'comments': 12, 'redlines': None,
          'overrides': None, 'hidden': 7, 'transforms': None, 'timeliner': 0, 'playground_data': 6}


def test_options_are_fixed_and_ordered():
    assert wipe.OPTION_IDS == ['viewpoints', 'sets', 'clash_tests', 'comments', 'redlines', 'overrides',
                               'hidden', 'transforms', 'timeliner', 'playground_data']
    rows = wipe.option_rows(COUNTS)
    assert [value for _label, value in rows] == [o for o in wipe.OPTION_IDS if o != 'redlines']


def test_label_with_count():
    assert wipe.label_with_count('viewpoints', 24) == 'Saved viewpoints (24)'
    assert wipe.label_with_count('viewpoints', 1234) == 'Saved viewpoints (1,234)'
    assert wipe.label_with_count('timeliner', 0) == 'TimeLiner tasks (none)'
    assert wipe.label_with_count('overrides', None) == 'Appearance overrides (all)'
    assert wipe.label_with_count('hidden', 7) == 'Hidden state (7 items)'
    assert wipe.label_with_count('hidden', 1, approx=True) == 'Hidden state (at least 1 item)'
    assert wipe.label_with_count('hidden', 0, approx=True) == 'Hidden state (none found in the items checked)'
    assert wipe.label_with_count('hidden', 0) == 'Hidden state (none found)'
    assert wipe.label_with_count('hidden', None) == 'Hidden state (unhide everything)'
    assert wipe.label_with_count('redlines', None) == 'Redlines (not reachable by scripts)'
    assert wipe.label_with_count('sets', 5, approx=True) == 'Selection sets (at least 5)'


def test_phrase():
    assert wipe.phrase('viewpoints', 1) == '1 saved viewpoint'
    assert wipe.phrase('clash_tests', None) == 'all clash tests'
    assert wipe.phrase('overrides', None) == 'appearance overrides'
    assert wipe.phrase('hidden', 3, approx=True) == 'hidden state (at least 3 hidden items)'
    assert wipe.phrase('hidden', 0) == 'hidden state'
    assert wipe.phrase('playground_data', 2) == '2 Playground records'


def test_confirm_text_names_exact_counts():
    text = wipe.confirm_text(['clash_tests', 'viewpoints', 'sets'], COUNTS, (), 'Model.nwf')
    assert text.startswith('Remove 24 saved viewpoints, 3 selection sets and 5 clash tests from Model.nwf?')
    assert text.endswith('Save a copy first if you may need any of it.')
    text = wipe.confirm_text(['overrides', 'hidden', 'playground_data'], COUNTS, (), 'Model.nwf')
    assert 'Remove 6 Playground records from Model.nwf? Also reset appearance overrides and hidden state (7 hidden items).' in text
    assert 'cannot be brought back with Ctrl+Z' in text
    text = wipe.confirm_text(['transforms'], COUNTS, (), 'Model.nwf')
    assert text.startswith('Reset item transforms in Model.nwf?')
    text = wipe.confirm_text(['viewpoints', 'comments', 'redlines'], COUNTS, (), 'A.nwd')
    assert 'Remove 24 saved viewpoints and 12 comments from A.nwd?' in text
    assert 'The comments go with the viewpoints.' in text and 'edline' not in text


def test_summary():
    level, message, detail = wipe.summary({'done': ['viewpoints', 'sets'], 'failed': [], 'left': []}, COUNTS)
    assert (level, message, detail) == ('success', 'Wiped 24 saved viewpoints and 3 selection sets', None)
    result = {'done': ['sets', 'viewpoints', 'overrides'], 'failed': [('clash_tests', 'locked')],
              'left': [('redlines', 'Redlines were left: Navisworks has no script route to them.')]}
    level, message, detail = wipe.summary(result, COUNTS)
    assert level == 'warning' and message == 'Wiped 3 kinds of data'
    assert detail.startswith('Removed 24 saved viewpoints, 3 selection sets and appearance overrides.')
    assert 'Could not wipe clash tests (locked).' in detail and 'Redlines were left' in detail
    level, message, detail = wipe.summary({'done': [], 'failed': [('sets', 'no')], 'left': []}, COUNTS)
    assert level == 'error' and message == 'Nothing was wiped' and detail == 'Selection sets: no'
    assert wipe.summary({'done': [], 'failed': [], 'left': []}, COUNTS)[0] == 'info'


# ---- API half -----------------------------------------------------------------------------------


def _fake():
    import test_items as nav

    class Models(nav.DocumentModels):
        def ResetAllHidden(self):
            self.calls.append(('reset_hidden', None, None))

        def ResetAllPermanentTransforms(self):
            self.calls.append(('reset_transforms', None, None))

    class Saved(nav.SavedViewpoints):
        def __init__(self):
            nav.SavedViewpoints.__init__(self)
            self.edits = []
            self.cleared = False

        def EditComments(self, item, comments):
            self.edits.append((item.DisplayName, len(comments)))
            item.Comments = comments

        def Clear(self):
            self.cleared = True
            self.RootItem.Children = []

    class Sets(object):
        def __init__(self):
            self.RootItem = nav.FolderItem()
            self.cleared = False

        def Clear(self):
            self.cleared = True
            self.RootItem.Children = []

    class Tests(object):
        def __init__(self, fail=False):
            self.fail = fail
            self.cleared = False
            self.stubborn = False       # True: TestsClear returns but removes nothing
            self.doc = None

        def TestsClear(self):
            if self.fail:
                raise RuntimeError('Clash tests are locked')
            self.cleared = True
            if not self.stubborn:
                self.doc.clash_tests = []

    doc, named = nav.model_tree()
    doc.Models = Models(doc.Models.models)
    doc.SavedViewpoints = Saved()
    doc.SelectionSets = Sets()
    doc.clash_data = Tests()
    doc.clash_data.doc = doc
    doc.clash_tests = [nav.ClashTest('A'), nav.ClashTest('B')]

    folder = nav.FolderItem()
    folder.DisplayName = 'Coordination'
    folder.Comments = nav.CommentCollection([nav.Comment('f', None)])
    view1 = nav.SavedViewpoint()
    view1.DisplayName = 'L1'
    view1.Comments = nav.CommentCollection([nav.Comment('a', None), nav.Comment('b', None)])
    view2 = nav.SavedViewpoint()
    view2.DisplayName = 'L2'
    view2.Comments = nav.CommentCollection()
    folder.Children = [view1, view2]
    view3 = nav.SavedViewpoint()
    view3.DisplayName = 'Top'
    view3.Comments = nav.CommentCollection()
    doc.SavedViewpoints.RootItem.Children = [folder, view3]
    set_folder = nav.FolderItem()
    set_folder.Children = [nav.SavedItem(), nav.SavedItem()]
    for item in set_folder.Children:
        item.Comments = nav.CommentCollection()
    set_folder.Comments = nav.CommentCollection()
    doc.SelectionSets.RootItem.Children = [set_folder]
    return nav, doc


def test_counts_through_fake_layer():
    nav, doc = _fake()
    previous = docdb.use_backend(docdb.SqliteBackend())
    try:
        docdb.kv_set('store:issues', {'a': 1})
        docdb.record_put('photos', 'P1', {'x': 1})
        docdb.record_put('photos', 'P2', {'x': 2})
        with nav.FakeNav(doc):
            seen = []
            counts, approx = wipe.counts(doc, progress=lambda f, label: seen.append(f))
            small, small_approx = wipe.counts(doc, hidden_budget=2)
    finally:
        docdb.use_backend(previous)
    assert counts['viewpoints'] == 3 and counts['comments'] == 3
    assert counts['sets'] == 2 and counts['clash_tests'] == 2
    assert counts['hidden'] == 1 and approx == []
    assert counts['timeliner'] == 0 and counts['playground_data'] == 3
    assert counts['redlines'] is None and counts['overrides'] is None and counts['transforms'] is None
    assert seen[0] == 0.0 and seen[-1] == 1.0
    assert small_approx == ['hidden'] and small['hidden'] == 0


def test_execute_everything_in_one_transaction():
    nav, doc = _fake()
    previous = docdb.use_backend(docdb.SqliteBackend())
    try:
        docdb.kv_set('store:issues', {'a': 1})
        docdb.record_put('photos', 'P1', {'x': 1})
        with nav.FakeNav(doc):
            result = wipe.execute(doc, ['comments', 'sets', 'clash_tests', 'overrides', 'hidden',
                                        'transforms', 'playground_data', 'redlines'])
        assert docdb.kv_keys() == [] and docdb.records('photos') == []
    finally:
        docdb.use_backend(previous)
    assert doc.transactions == ['Model Wipe']
    assert result['done'] == ['comments', 'sets', 'clash_tests', 'overrides', 'hidden', 'transforms',
                              'playground_data']
    assert result['failed'] == []
    assert result['left'][0][0] == 'redlines'
    assert sorted(doc.SavedViewpoints.edits) == [('Coordination', 0), ('L1', 0)]
    assert doc.SelectionSets.cleared and doc.clash_data.cleared
    calls = [c[0] for c in doc.Models.calls]
    assert calls == ['reset_all', 'reset_hidden', 'reset_transforms']


def test_execute_comments_go_with_viewpoints_and_failures_are_recorded():
    nav, doc = _fake()
    doc.clash_data.fail = True
    with nav.FakeNav(doc):
        result = wipe.execute(doc, ['viewpoints', 'comments', 'clash_tests', 'timeliner'])
    assert doc.SavedViewpoints.cleared and doc.SavedViewpoints.edits == []
    assert 'viewpoints' in result['done'] and 'comments' in result['done']
    failed = dict(result['failed'])
    assert failed['clash_tests'] == 'Clash tests are locked'
    assert failed['timeliner'] == 'TimeLiner is not available'
    level, message, detail = wipe.summary(result, {'viewpoints': 3, 'comments': 3})
    assert level == 'warning' and 'Could not wipe clash tests (Clash tests are locked)' in detail


def test_execute_docdb_only_needs_no_transaction():
    nav, doc = _fake()
    previous = docdb.use_backend(docdb.SqliteBackend())
    try:
        with nav.FakeNav(doc):
            result = wipe.execute(doc, ['playground_data'])
    finally:
        docdb.use_backend(previous)
    assert doc.transactions == [] and result['done'] == ['playground_data']


def test_form_fields_parse():
    from namo import ui
    fields = ui.normalize_fields(wipe.form_fields(COUNTS, (), 'Model.nwf'))
    multi = [f for f in fields if f['kind'] == 'multi'][0]
    assert multi['default'] == [] and len(multi['options']) == len(wipe.OPTION_IDS) - 1
    assert 'Model.nwf' in fields[0]['text'] and 'Redlines cannot be wiped' in fields[-1]['text']
    values, errors = ui.collect(fields, {'chosen': ['sets', 'viewpoints']})
    assert errors == {} and values['chosen'] == ['sets', 'viewpoints']


# ---- refit: nothing is reported as wiped on trust -----------------------------------------


def test_a_clear_that_removes_nothing_is_reported_as_not_wiped():
    nav, doc = _fake()
    doc.clash_data.stubborn = True
    with nav.FakeNav(doc):
        result = wipe.execute(doc, ['clash_tests', 'sets'])
    assert result['done'] == ['sets']
    assert dict(result['failed'])['clash_tests'] == '2 clash tests still there'
    level, message, detail = wipe.summary(result, {'sets': 2, 'clash_tests': 2})
    assert level == 'warning' and message == 'Wiped 2 selection sets'
    assert 'Could not wipe clash tests (2 clash tests still there).' in detail


def test_saved_items_fall_back_to_remove_when_clear_does_nothing():
    nav, doc = _fake()
    removed = []

    def lazy_clear():
        doc.SavedViewpoints.cleared = True      # returns, removes nothing

    def remove(item):
        removed.append(item.DisplayName)
        doc.SavedViewpoints.RootItem.Children = [
            c for c in doc.SavedViewpoints.RootItem.Children if c is not item]
        return True
    doc.SavedViewpoints.Clear = lazy_clear
    doc.SavedViewpoints.Remove = remove
    with nav.FakeNav(doc):
        result = wipe.execute(doc, ['viewpoints'])
        assert wipe.remaining(doc, 'viewpoints') == 0
    assert sorted(removed) == ['Coordination', 'Top'] and result['done'] == ['viewpoints']


class _Count(object):
    def __init__(self, count):
        self.Count = count


class _Root(object):
    def __init__(self, count):
        self.Children = _Count(count)


class _Timeliner(object):
    def __init__(self, clear_works):
        self.tasks = 3
        self.clear_works = clear_works
        self.calls = []
        self.TasksRoot = _Root(3)

    def TasksClear(self):
        self.calls.append('clear')
        if not self.clear_works:
            raise RuntimeError('refused')
        self.tasks = 0

    def TasksCopyFrom(self, value):
        self.calls.append('copy')

    def TaskTotalTasks(self):
        return self.tasks

    def TaskRemoveAt(self, index):
        self.calls.append('remove %d' % index)
        self.tasks -= 1


def test_timeliner_uses_tasksclear_then_falls_back():
    good = _Timeliner(True)
    wipe._clear_timeliner(good)
    assert good.calls == ['clear'] and good.tasks == 0
    bad = _Timeliner(False)
    wipe._clear_timeliner(bad)
    assert bad.calls[0] == 'clear' and bad.calls[-3:] == ['remove 2', 'remove 1', 'remove 0']
    assert bad.tasks == 0

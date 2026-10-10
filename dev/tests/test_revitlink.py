# -*- coding: utf-8 -*-
"""namo.revitlink and the pyRevit companion's lib: file matching, messages, queries; the
two copies of the pure helpers agree; selection and search through the fakes."""
import datetime
import io
import json
import os
import sys

import _compat
import test_clashset_tests as cf

from namo import paths
from namo import revitlink as rl

COMPANION = os.path.join(_compat.ROOT, 'companions', 'PlaygroundLink.extension')
NOW = datetime.datetime(2026, 10, 5, 14, 30, 0)


def _companion_lib():
    path = os.path.join(COMPANION, 'lib', 'playgroundlink.py')
    with io.open(path, encoding='utf-8') as handle:
        source = handle.read()
    namespace = {'__name__': 'playgroundlink_test', '__file__': path}
    exec(compile(source, path, 'exec'), namespace)
    return namespace


def test_stem_and_same_file():
    assert rl.stem(r'C:\Projects\Hospital_MEP.rvt') == 'hospital_mep'
    assert rl.stem('Hospital_MEP.NWC') == 'hospital_mep'
    assert rl.stem('Hospital MEP') == 'hospital mep'
    assert rl.same_file('Hospital_MEP.rvt', 'hospital_mep.nwc')
    assert rl.same_file('Hospital_MEP_jdoe.rvt', 'Hospital_MEP.rvt', user='JDoe')
    assert not rl.same_file('Hospital_MEP_jdoe.rvt', 'Hospital_MEP.rvt')
    assert not rl.same_file('', 'x')


def test_loose_match():
    assert rl.loose_match('Hospital_MEP', 'Hospital_MEP_R24.nwc')
    assert rl.loose_match('Hospital_MEP.rvt', 'Coord-Hospital_MEP.nwc')
    assert not rl.loose_match('Hospital', 'HospitalWing.nwc')
    assert rl.loose_match('A', 'a.nwc')
    assert not rl.loose_match('', 'a')


def test_message_round_trip_and_problems():
    data = rl.message('to-revit', 'Hospital.nwf',
                      [{'file': 'A.rvt', 'element_id': 12, 'unique_id': 'u-1', 'name': 'Duct'},
                       {'file': 'A.rvt'}], now=NOW)
    assert data['sent'] == '2026-10-05T14:30:00' and data['from'] == 'Hospital.nwf'
    elements, problem = rl.read_message(json.loads(json.dumps(data)), 'to-revit')
    assert problem is None and [e['element_id'] for e in elements] == ['12']
    assert rl.read_message(data, 'to-navisworks')[1] == 'The link file holds elements going the other way.'
    assert rl.read_message({'format': 'x'}, 'to-revit')[1].startswith('The link file is not')
    assert rl.read_message({'format': rl.FORMAT, 'elements': []}, 'to-revit')[1] == \
        'The link file holds no elements.'


def test_age_text_and_grouping():
    assert rl.age_text('2026-10-05T14:29:30', NOW) == 'just now'
    assert rl.age_text('2026-10-05T14:00:00', NOW) == '30 minutes ago'
    assert rl.age_text('2026-10-05T10:30:00', NOW) == '4 hours ago'
    assert rl.age_text('2026-10-01T10:30:00', NOW) == '4 days ago'
    assert rl.age_text('junk', NOW) == ''
    groups = rl.group_by_file([{'file': 'A.rvt', 'element_id': '1'}, {'file': 'b.rvt', 'element_id': '2'},
                               {'file': 'a.RVT', 'element_id': '3'}])
    assert [(f, [e['element_id'] for e in es]) for f, es in groups] == [('A.rvt', ['1', '3']),
                                                                       ('b.rvt', ['2'])]


def test_match_models_and_queries():
    models = [{'index': 0, 'names': ['ARCH.rvt', 'ARCH.nwc']},
              {'index': 1, 'names': ['Hospital_MEP_R24.nwc']}, {'index': 2, 'names': ['STR.nwc']}]
    assert rl.match_models('arch.rvt', models) == ([0], 'exact')
    assert rl.match_models('Hospital_MEP.rvt', models) == ([1], 'loose')
    assert rl.match_models('Other.rvt', models) == ([0, 1, 2], 'all')
    queries = rl.id_queries('123456')
    assert queries[0]['or'][0]['and'][0] == {'category': 'Element ID', 'prop': 'Value',
                                             'op': 'equals', 'value': '123456'}
    assert queries[0]['or'][0]['and'][1]['by_display'] is False
    assert queries[1]['or'][0]['and'][0]['value'] == '[123456]'
    assert len(rl.id_queries('123', elements_only=False)[0]['or'][0]['and']) == 1
    assert rl.id_queries('abc') == []
    assert rl.is_element([('Element', 'LcRevitData_Element')])
    assert rl.short_list(range(8), 3) == '0, 1, 2 and 5 more'


def test_companion_helpers_agree():
    lib = _companion_lib()
    cases = [('Hospital_MEP.rvt', 'hospital_mep.nwc', None), ('A_jdoe.rvt', 'A.rvt', 'jdoe'),
             ('A_jdoe.rvt', 'A.rvt', None), ('X', 'Y', None), ('', 'a', None)]
    for a, b, user in cases:
        assert lib['same_file'](a, b, user) == rl.same_file(a, b, user)
        assert lib['loose_match'](a, b) == rl.loose_match(a, b)
        assert lib['stem'](a) == rl.stem(a)
    elements = [{'file': 'A.rvt', 'element_id': '7', 'unique_id': '', 'name': 'n', 'category': 'c'}]
    assert lib['message']('to-navisworks', 'A', elements, NOW) == rl.message('to-navisworks', 'A', elements, NOW)
    data = rl.message('to-navisworks', 'A', elements, NOW)
    assert lib['read_message'](data, 'to-navisworks') == rl.read_message(data, 'to-navisworks')
    assert lib['age_text']('2026-10-05T14:00:00', NOW) == rl.age_text('2026-10-05T14:00:00', NOW)
    assert lib['group_by_file'](elements) == rl.group_by_file(elements)


def test_companion_files_round_trip():
    folder = _compat.tmpdir('revitlink-companion')
    lib = _companion_lib()
    saved = os.environ.get('APPDATA')
    os.environ['APPDATA'] = folder
    try:
        data = lib['message']('to-navisworks', 'Hospital_MEP', [{'file': 'Hospital_MEP.rvt',
                                                                 'element_id': '42'}], NOW)
        path = lib['write_file'](lib['TO_NAVISWORKS'], data)
        assert path == os.path.join(folder, 'pyNavis', 'playground', 'revit-link', 'to-navisworks.json')
        back, problem = lib['read_file'](lib['TO_NAVISWORKS'])
        assert problem is None and back == data
        assert lib['read_file']('missing.json') == (None, None)
    finally:
        if saved is None:
            os.environ.pop('APPDATA', None)
        else:
            os.environ['APPDATA'] = saved


def test_companion_sources_are_python27_shaped():
    """pyRevit runs these under IronPython 2.7: no f-strings, walrus, async, nonlocal,
    annotations, keyword-only arguments, or print calls."""
    import ast
    banned = ('JoinedStr', 'NamedExpr', 'AsyncFunctionDef', 'Nonlocal', 'AnnAssign',
              'YieldFrom', 'Await')
    checked = 0
    for folder, _dirs, files in os.walk(COMPANION):
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(folder, name)
            with io.open(path, encoding='utf-8') as handle:
                text = handle.read()
            tree = ast.parse(text, path)
            for node in ast.walk(tree):
                assert type(node).__name__ not in banned, (path, type(node).__name__)
                if isinstance(node, ast.FunctionDef):
                    assert not node.args.kwonlyargs and node.returns is None, path
                    assert all(a.annotation is None for a in node.args.args), path
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id != 'print', path
            checked += 1
    assert checked == 3


def test_companion_bundles_are_complete():
    panel = os.path.join(COMPANION, 'Playground.tab', 'Navisworks.panel')
    for button in ('Show from Navisworks.pushbutton', 'Send to Navisworks.pushbutton'):
        for needed in ('script.py', 'bundle.yaml', 'icon.png', 'icon.dark.png'):
            assert os.path.exists(os.path.join(panel, button, needed)), (button, needed)


def test_send_to_revit_writes_through_scratch_root():
    folder = _compat.tmpdir('revitlink-send')
    previous = paths.redirect(folder)
    try:
        doc, named = cf.new_doc()
        with cf.ClashNav(doc) as fake:
            doc_module = sys.modules['pynavis.doc']
            doc_module.get_title = lambda d=None: 'Hospital.nwf'
            props = sys.modules['pynavis.props']
            props.categories = lambda item: [('Element', 'LcRevitData_Element')] \
                if item.props.get(('Element ID', 'Value')) else []
            doc.CurrentSelection.SelectedItems = [named['Wall 1 solid'], named['Wall 1'], named['Duct']]
            elements, skipped = rl.selected_elements(doc)
            assert skipped == 1
            assert elements == [{'file': 'ARCH.rvt', 'element_id': '101', 'unique_id': 'u-101',
                                 'name': 'Wall 1', 'category': 'Walls'}]
            path = rl.send_to_revit(elements, doc)
            assert path == os.path.join(folder, 'pyNavis', 'playground', 'revit-link', 'to-revit.json')
            with io.open(path, encoding='utf-8') as handle:
                data = json.load(handle)
            assert data['from'] == 'Hospital.nwf' and data['direction'] == 'to-revit'
            fake.view  # keep the fake layer referenced
    finally:
        paths.redirect(previous)


def test_find_elements_scoped_through_fakes():
    doc, named = cf.new_doc()
    calls = []

    def find_first(query, d=None, scope=None):
        calls.append((query, [s.DisplayName for s in scope or []]))
        cond = query['or'][0]['and'][0]
        if cond.get('op') == 'has_category':
            return named['Wall 1']
        if cond.get('value') == '101':
            return named['Wall 1']
        return None

    with cf.ClashNav(doc):
        sys.modules['pynavis.sets'].find_first = find_first
        found, missing, notes = rl.find_elements(
            [{'file': 'ARCH.rvt', 'element_id': '101', 'unique_id': '', 'name': 'Wall'},
             {'file': 'ARCH.rvt', 'element_id': '999', 'unique_id': '', 'name': 'Gone'},
             {'file': 'Other.rvt', 'element_id': '101', 'unique_id': '', 'name': 'Again'}], doc)
    assert [f.DisplayName for f in found] == ['Wall 1']
    assert missing == ['999']
    assert notes == ['No model is named like Other.rvt; every model was searched.']
    assert calls[1][1] == ['ARCH.nwc']
    assert calls[-1][1] == ['ARCH.nwc', 'MEP.nwc']


def test_id_property_follows_the_shipped_element_id_settings():
    # Show from Revit looks where pyNavis' own Select by IDs was told the id lives.
    assert rl.id_property(lambda key, defaults: dict(defaults)) == ('Element ID', 'Value')
    seen = []

    def custom(key, defaults):
        seen.append(key)
        return {'id_category': 'Revit Tag', 'id_property': ' Mark '}
    assert rl.id_property(custom) == ('Revit Tag', 'Mark')
    assert seen == ['cfg_element_ids']

    def broken(key, defaults):
        raise IOError('no settings')
    assert rl.id_property(broken) == ('Element ID', 'Value')
    first = rl.id_queries('123', True, 'Revit Tag', 'Mark')[0]['or'][0]['and'][0]
    assert (first['category'], first['prop'], first['value']) == ('Revit Tag', 'Mark', '123')
    assert rl.id_queries('123')[0]['or'][0]['and'][0]['category'] == 'Element ID'

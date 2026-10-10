# -*- coding: utf-8 -*-
"""tools/build_catalog.py and tools/package.py: the catalog the in-app browser reads and
the release zip it installs from. CPython only (the tools are dev-time CPython 3.11)."""
import hashlib
import io
import json
import os
import sys
import zipfile

import _compat
from _compat import raises

if _compat.IRONPYTHON:
    raise _compat.SkipTest('tools/ are CPython-only')

TOOLS = os.path.join(_compat.ROOT, 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import build_catalog as bc  # noqa: E402
import package  # noqa: E402

_BUILT = []


def catalog():
    """One fresh build per test process (the walk reads every bundle)."""
    if not _BUILT:
        _BUILT.append(bc.build('0.1.0', '', '2026-10-09'))
    return _BUILT[0]


def tools_by_id():
    return dict((t['id'], t) for t in catalog()['tools'])


def write(path, text):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
    return path


# ---- the whole catalog ---------------------------------------------------------------------

def test_header_follows_schema_1():
    c = catalog()
    assert c['schema'] == 1 and c['name'] == 'pyNavis Playground'
    assert c['extension'] == 'Playground.extension' and c['min_pynavis'] == '1.3.0'
    assert c['download']['zip'] == ('https://github.com/pynavis/Playground/releases/download/'
                                    'v0.1.0/Playground.extension.zip')
    assert c['shared'] == ['extension.yaml', 'startup.py', 'lib/namo/**', 'hooks/*.py']


def test_every_tool_has_every_field_and_real_files():
    fields = {'id', 'title', 'kind', 'tab', 'panel', 'container', 'summary', 'status',
              'status_note', 'status_date', 'status_by', 'feature', 'shortcut', 'context', 'hooks', 'files',
              'icon', 'source', 'leads', 'siblings'}
    ids = [t['id'] for t in catalog()['tools']]
    assert len(ids) == len(set(ids))
    for tool in catalog()['tools']:
        assert set(tool) == fields, tool['id']
        assert tool['kind'] in bc.LEAF_KINDS
        assert tool['status'] in bc.STATUSES
        assert tool['summary'] and u'\u2014' not in tool['summary'], tool['id']
        assert tool['id'] + '/bundle.yaml' in tool['files']
        for path in tool['files']:
            assert '\\' not in path and '__pycache__' not in path
            assert os.path.isfile(os.path.join(bc.EXT, path)), path
        assert tool['icon'] in tool['files']


def test_tool_count_matches_the_bundles_on_disk():
    leaves = package.leaf_folders()
    assert set(t['id'] for t in catalog()['tools']) == leaves


def test_containers_cover_every_parent():
    containers = dict((c['id'], c) for c in catalog()['containers'])
    for tool in catalog()['tools']:
        assert tool['container'] in containers
        parts = tool['id'].split('/')
        assert containers[parts[0]]['kind'] == 'tab' and containers[parts[0]]['title'] == tool['tab']
        assert containers['/'.join(parts[:2])]['title'] == tool['panel']
    for container in containers.values():
        assert container['id'] + '/bundle.yaml' in container['files']


def test_tabs_come_in_extension_layout_order():
    tabs = [c['title'] for c in catalog()['containers'] if c['kind'] == 'tab']
    assert tabs == ['Model', 'Views', 'Coordinate', 'Project', 'Dev']


def test_select_similar_matches_the_charter_example():
    tool = tools_by_id()['Model.tab/Select.panel/Select_Similar.pushbutton']
    assert tool['title'] == 'Select Similar' and tool['kind'] == 'pushbutton'
    assert tool['tab'] == 'Model' and tool['panel'] == 'Select'
    assert tool['container'] == 'Model.tab/Select.panel'
    assert tool['feature'] == 4 and tool['context'] == 'selection' and tool['shortcut'] is None
    assert tool['hooks'] == [] and tool['siblings'] == []
    assert tool['icon'] == 'Model.tab/Select.panel/Select_Similar.pushbutton/icon.png'


def test_stack_members_list_their_siblings():
    tool = tools_by_id()['Model.tab/Select.panel/Quick.stack/Invert.pushbutton']
    assert tool['siblings'] == ['Model.tab/Select.panel/Quick.stack/Select_by_File.pushbutton',
                                'Model.tab/Select.panel/Quick.stack/Save_as_Set.pushbutton']


def test_features_resolve_through_stacks_and_pulldowns():
    tools = tools_by_id()
    assert tools['Model.tab/Select.panel/History.stack/Back.pushbutton']['feature'] == 7
    assert tools['Coordinate.tab/Issues.panel/Issue_Stamps.pulldown/RFI.pushbutton']['feature'] == 40
    assert tools['Model.tab/Look.panel/Color_by_Property.pushbutton']['feature'] == 76
    assert tools['Project.tab/Field.panel/Photo_Pins.pushbutton']['feature'] == 95


def test_hooks_follow_the_handlers_a_tool_depends_on():
    tools = tools_by_id()
    assert tools['Model.tab/Select.panel/History.stack/Back.pushbutton']['hooks'] == ['selection-changed']
    assert tools['Project.tab/Field.panel/Photo_Pins.pushbutton']['hooks'] == ['doc-closed', 'doc-opened']
    assert tools['Dev.tab/Automate.panel/Macro_Record.toggle']['hooks'] == ['after-command']
    assert tools['Model.tab/Find.panel/Quick_Find.pushbutton']['hooks'] == []
    events = set(e for t in catalog()['tools'] for e in t['hooks'])
    assert 'startup' not in events
    assert events <= set(os.path.splitext(n)[0] for n in os.listdir(os.path.join(bc.EXT, 'hooks')))


def test_ledger_statuses_reach_the_catalog():
    tools = tools_by_id()
    pins = tools['Project.tab/Field.panel/Photo_Pins.pushbutton']
    assert pins['status'] == 'launched' and pins['status_date'] == '2026-10-05'
    assert pins['status_by'] == 'log'
    assert 'refit to the host Measure pick' in pins['status_note']
    sectioner = tools['Views.tab/Navigate.panel/Level_Sectioner.pushbutton']
    assert sectioner['status'] == 'launched' and 'NameError fixed' in sectioner['status_note']
    assert sectioner['status_date'] == '2026-10-09'
    assert tools['Model.tab/Select.panel/Select_Similar.pushbutton']['status'] == 'untested'


def test_output_is_stable_json():
    text = bc.dumps(catalog())
    assert text == bc.dumps(json.loads(text)) and text.endswith('}\n')


# ---- pieces --------------------------------------------------------------------------------

def test_status_ledger_rejects_what_the_ladder_forbids():
    folder = _compat.tmpdir('catalog-status')
    good = write(os.path.join(folder, 'good.yaml'),
                 '# comment\nA.tab/B.panel/C.pushbutton:\n  status: launched\n'
                 '  note: "Ran once."\n  date: 2026-10-05\n  by: log\n')
    assert bc.read_status(good) == {'A.tab/B.panel/C.pushbutton': {
        'status': 'launched', 'note': 'Ran once.', 'date': '2026-10-05', 'by': 'log'}}
    bad = write(os.path.join(folder, 'bad.yaml'),
                'A.tab/B.panel/C.pushbutton:\n  status: verified\n  date: 2026-10-05\n  by: log\n')
    assert 'person' in str(raises(bc.CatalogError, bc.read_status, bad))
    odd = write(os.path.join(folder, 'odd.yaml'),
                'A.tab/B.panel/C.pushbutton:\n  status: works\n  date: 2026-10-05\n  by: log\n')
    raises(bc.CatalogError, bc.read_status, odd)
    assert bc.read_status(os.path.join(folder, 'absent.yaml')) == {}


def test_features_match_by_path_title_and_container():
    folder = _compat.tmpdir('catalog-features')
    md = write(os.path.join(folder, 'CATALOG.md'), '\n'.join([
        '## G1 x: tab Model, panels `Select.panel`',
        '### Select.panel  layout: A, Box',
        '* **#4 Aye** `Select.panel/A.pushbutton` (large).',
        '* `Select.panel/Box.stack`: **#7 Box things**',
        '  * **#9 Written Here** (context: doc): no path, matched by title',
        '## G2 y: tab Views, panel `Look.panel`',
        '* **#11 Aye** `A.pushbutton` (same name, other panel).',
    ]))
    bundles = ['Model.tab/Select.panel/A.pushbutton', 'Model.tab/Select.panel/Box.stack',
               'Model.tab/Select.panel/Box.stack/B.pushbutton',
               'Model.tab/Select.panel/Box.stack/Written_Here.pushbutton',
               'Views.tab/Look.panel/A.pushbutton', 'Views.tab/Look.panel/Z.pushbutton']
    found = bc.read_features(md, bundles)
    assert found['Model.tab/Select.panel/A.pushbutton'] == 4
    assert found['Model.tab/Select.panel/Box.stack/B.pushbutton'] == 7
    assert found['Model.tab/Select.panel/Box.stack/Written_Here.pushbutton'] == 9
    assert found['Views.tab/Look.panel/A.pushbutton'] == 11
    assert 'Views.tab/Look.panel/Z.pushbutton' not in found


def test_sources_pass_via_through_and_normalise_leads():
    folder = _compat.tmpdir('catalog-sources')
    write(os.path.join(folder, 'a.json'), json.dumps({
        'agent': 'a', 'date': '2026-10-09',
        'tools': {'T/one': {'found': True, 'quote': 'Please add this', 'url': 'https://x/1',
                            'site': 'Forum', 'date': '2019-03', 'relevance': 'high'},
                  'T/two': {'found': False, 'note': 'Would not open.'},
                  'T/three': {'found': True, 'quote': 'No url here'}},
        'leads': {'T/two': ['https://x/2', {'url': 'https://x/3', 'title': 'Three'}]}}))
    write(os.path.join(folder, 'b.json'), json.dumps({
        'tools': {'T/one': {'found': True, 'quote': 'Later file', 'url': 'https://x/9',
                            'via': 'search snippet'},
                  'T/two': {'found': True, 'quote': 'Snippet words', 'url': 'https://x/2',
                            'site': 'Forum', 'date': '2020', 'via': 'search snippet'}},
        'leads': {'T/two': [{'url': 'https://x/2', 'title': 'Two'}, 'https://x/3']}}))
    sources, leads, notes = bc.read_sources(folder)
    assert sources['T/one'] == {'quote': 'Please add this', 'url': 'https://x/1', 'site': 'Forum',
                                'date': '2019-03', 'via': 'page'}
    assert sources['T/two']['via'] == 'search snippet'
    assert 'T/three' not in sources and any('T/three' in n for n in notes)
    assert leads['T/two'] == [{'url': 'https://x/2', 'title': 'Two'},
                              {'url': 'https://x/3', 'title': 'Three'}]
    assert bc.read_sources(os.path.join(folder, 'missing')) == ({}, {}, [])


def test_sources_naming_a_missing_bundle_fail_the_build():
    folder = _compat.tmpdir('catalog-sources-stale')
    write(os.path.join(folder, 'a.json'), json.dumps({
        'tools': {'Dev.tab/Team.panel/Team_Tools.stack/Old_Name.pushbutton': {'found': False}},
        'leads': {'Model.tab/Nowhere.panel/Gone.pushbutton': ['https://x/1']}}))
    error = raises(bc.CatalogError, bc.build, '0.1.0', '', '2026-10-09', sources_folder=folder)
    assert 'Old_Name' in str(error) and 'Gone' in str(error)


def test_render_keeps_the_date_when_nothing_else_changed():
    folder = _compat.tmpdir('catalog-render')
    path = os.path.join(folder, 'catalog.json')
    text, old = bc.render(path, '', today='2026-10-01')
    assert old is None and '"generated": "2026-10-01"' in text
    write(path, text)
    again, old = bc.render(path, today='2026-12-31')
    assert again == old == text


# ---- package -------------------------------------------------------------------------------

def test_stamp_adds_or_replaces_the_status_line():
    assert package.stamp('title: A\n') == 'title: A\nstatus: experimental\n'
    assert package.stamp('title: A') == 'title: A\nstatus: experimental\n'
    assert package.stamp('title: A\nstatus: stable\ntooltip: B\n') == \
        'title: A\nstatus: experimental\ntooltip: B\n'
    assert package.stamp('') == 'status: experimental\n'


def test_zip_is_deterministic_stamped_and_clean():
    data = package.build_zip()
    assert hashlib.sha256(data).hexdigest() == hashlib.sha256(package.build_zip()).hexdigest()
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = archive.namelist()
    assert names == sorted(names)
    assert all(n.startswith('Playground.extension/') for n in names)
    assert not [n for n in names if '__pycache__' in n or n.endswith('.pyc')]
    for name in ('extension.yaml', 'startup.py', 'lib/namo/__init__.py', 'hooks/doc-opened.py'):
        assert 'Playground.extension/' + name in names
    leaf = 'Playground.extension/Model.tab/Select.panel/Select_Similar.pushbutton/bundle.yaml'
    assert archive.read(leaf).decode('utf-8').endswith('status: experimental\n')
    container = 'Playground.extension/Model.tab/Select.panel/bundle.yaml'
    assert 'status:' not in archive.read(container).decode('utf-8')
    with io.open(os.path.join(bc.EXT, 'Model.tab', 'Select.panel', 'Select_Similar.pushbutton',
                              'bundle.yaml'), encoding='utf-8') as handle:
        assert 'status:' not in handle.read()
    stamped = [n for n in names if n.endswith('/bundle.yaml')
               and bc.kind_of(n.split('/')[-2]) in bc.LEAF_KINDS]
    assert len(stamped) == len(catalog()['tools'])


def test_zip_ignores_checkout_line_endings():
    names = [n for n, _ in package.entries()]
    data = dict(package.entries())
    text = [n for n in names if n.endswith(('.py', '.yaml', '.xaml'))]
    assert text and not [n for n in text if b'\r\n' in data[n]]

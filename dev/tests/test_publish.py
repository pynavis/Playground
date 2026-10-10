# -*- coding: utf-8 -*-
"""namo.publish: names, versions across dates, archive plans, publish fields, history,
and the API half's three write methods through a fake document."""
import datetime
import os

import _compat

from namo import paths, publish

TEMPLATE = publish.DEFAULT_TEMPLATE


def _values(project='HSP', file_name='Hospital', day=5):
    return {'project': project, 'file': file_name, 'date': datetime.date(2026, 10, day),
            'time': datetime.time(14, 30), 'user': 'amol'}


def test_render_name():
    assert publish.render_name(TEMPLATE, _values(), 3) == ('HSP_Hospital_20261005_v03.nwd', [])
    assert publish.render_name(TEMPLATE, _values(), 123)[0] == 'HSP_Hospital_20261005_v123.nwd'


def test_render_name_collapses_empty_tokens():
    assert publish.render_name(TEMPLATE, _values(project=''), 1)[0] == 'Hospital_20261005_v01.nwd'
    assert publish.render_name(TEMPLATE, _values(project='', file_name=''), 2)[0] == '20261005_v02.nwd'
    name, missing = publish.render_name('{project} - {file} - v{version:00}', _values(project=''), 4)
    assert name == 'Hospital - v04.nwd' and missing == []
    assert publish.render_name('{project}__{file}', {'project': '', 'file': ''}, 1)[0] == 'Published.nwd'


def test_render_name_adds_extension_and_reports_unknown_tokens():
    name, missing = publish.render_name('{file}_{phase}_v{version:00}', _values(), 7)
    assert name == 'Hospital_{phase}_v07.nwd' and missing == ['phase']
    assert publish.render_name('Out/In:{file}_v{version}.nwd', _values(), 1)[0] == 'Out_In_Hospital_v1.nwd'


def test_template_problems():
    assert publish.template_problems(TEMPLATE) == []
    problems = publish.template_problems('{file}_{phase}.nwd')
    assert problems[0] == 'Unknown token: {phase}.'
    assert 'Add {version}' in problems[1]
    assert publish.template_problems('{Project}_{FILE}_{version:000}') == []


def test_next_version_across_dates_and_gaps():
    names = ['HSP_Hospital_20261001_v01.nwd', 'HSP_Hospital_20261003_v03.nwd',
             'hsp_hospital_20261004_V07.NWD', 'HSP_Hospital_20261003_v03 (2).nwd',
             'Other_Hospital_20261001_v09.nwd', 'notes.txt']
    assert publish.next_version(TEMPLATE, _values(), names) == 8
    assert publish.next_version(TEMPLATE, _values(), ['HSP_Hospital_20261001_v01.nwd',
                                                      'HSP_Hospital_20261003_v03.nwd']) == 4
    assert publish.next_version(TEMPLATE, _values(), []) == 1
    assert publish.next_version(TEMPLATE, _values(project=''), ['Hospital_20261001_v02.nwd']) == 3


def test_versions_in_order_and_no_version_token():
    names = ['HSP_Hospital_20261003_v10.nwd', 'HSP_Hospital_20261001_v02.nwd']
    assert publish.versions_in(TEMPLATE, _values(), names) == [
        (2, 'HSP_Hospital_20261001_v02.nwd'), (10, 'HSP_Hospital_20261003_v10.nwd')]
    assert publish.name_pattern('{file}.nwd', _values()) is None
    assert publish.next_version('{file}.nwd', _values(), ['Hospital.nwd']) == 1


def test_plan_target_never_reuses_a_name():
    names = ['HSP_Hospital_20261005_v01.nwd']
    assert publish.plan_target(TEMPLATE, _values(), names) == (2, 'HSP_Hospital_20261005_v02.nwd')
    # a taken name that does not fit the pattern still bumps the version
    odd = '{file}_v{version:00}_{project}.nwd'
    taken = ['Hospital_v01_HSP.nwd']
    assert publish.plan_target(odd, _values(), taken)[1] == 'Hospital_v02_HSP.nwd'
    assert publish.plan_target('{file}.nwd', _values(), ['hospital.nwd', 'Hospital (2).nwd']) == \
        (1, 'Hospital (3).nwd')


def test_archive_plan_unique_targets():
    folder = ['HSP_Hospital_20261001_v01.nwd', 'HSP_Hospital_20261003_v02.nwd',
              'HSP_Hospital_20261005_v03.nwd', 'readme.txt']
    plan = publish.archive_plan(folder, TEMPLATE, _values(), 'HSP_Hospital_20261005_v03.nwd',
                                ['HSP_Hospital_20261001_v01.nwd', 'HSP_Hospital_20261001_v01 (2).nwd'])
    assert [p['name'] for p in plan] == ['HSP_Hospital_20261001_v01.nwd', 'HSP_Hospital_20261003_v02.nwd']
    assert plan[0]['target'] == 'HSP_Hospital_20261001_v01 (3).nwd'
    assert plan[1]['target'] == 'HSP_Hospital_20261003_v02.nwd' and plan[1]['version'] == 2
    assert publish.archive_plan([], TEMPLATE, _values(), 'x.nwd') == []


def test_normalize_settings():
    out = publish.normalize_settings({'method': 'fax', 'expiry_days': '-3', 'archive': 0,
                                      'template': '  ', 'unknown': 1, 'title': None})
    assert out['method'] == 'publish' and out['expiry_days'] == 0 and out['archive'] is False
    assert out['template'] == publish.DEFAULT_TEMPLATE and 'unknown' not in out
    assert out['title'] == '' and out['subfolder'] == 'Published'
    assert publish.normalize_settings(None) == publish.normalize_settings({})


def test_publish_fields():
    options, props, expiry = publish.publish_fields({
        'title': 'Hospital v3', 'author': 'Amol', 'comments': '  ', 'copyright': '(c) 2026',
        'publisher': 'Amol', 'exclude_hidden': True, 'embed_xrefs': False, 'allow_resave': False,
        'expiry_days': 30})
    assert options == {'ExcludeHiddenItems': True, 'EmbedXrefs': False}
    assert props == {'AllowResave': False, 'DisplayOnOpen': False, 'Title': 'Hospital v3',
                     'Author': 'Amol', 'Copyright': '(c) 2026', 'Publisher': 'Amol'}
    assert expiry == 30


def test_history_record_and_toast_text():
    record = publish.history_record(r'C:\P\A_v02.nwd', 2, 'publish', 1234, 'passed', 'amol',
                                    r'C:\P\A.nwf', 1, when=datetime.datetime(2026, 10, 5, 9, 30))
    assert record == {'time': '2026-10-05T09:30:00', 'user': 'amol', 'path': r'C:\P\A_v02.nwd',
                      'name': 'A_v02.nwd', 'version': 2, 'method': 'publish', 'size': 1234,
                      'preflight': 'passed', 'document': r'C:\P\A.nwf', 'archived': 1}
    level, message, detail = publish.toast_text('A_v02.nwd', r'C:\P', 1, [], None, 'publish')
    assert (level, message) == ('success', 'Published A_v02.nwd')
    assert detail == os.path.join('C:\\P', 'A_v02.nwd') + '. 1 older version moved to Archive.'
    level, message, detail = publish.toast_text('A_v02.nwd', r'C:\P', 0, ['A_v01.nwd'], None, 'export')
    assert level == 'warning' and message == 'Exported A_v02.nwd' and 'A_v01.nwd' in detail
    assert publish.toast_text('A.nwd', 'C:', 0, [], 'History failed.', 'save')[0] == 'warning'


def test_folders():
    folder = _compat.tmpdir('publish_folders' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    doc_path = os.path.join(folder, 'Model.nwf')
    assert publish.default_folder(doc_path) == folder
    assert publish.default_folder('') != ''
    assert publish.target_folder({'folder': folder, 'subfolder': ' Published\\ '}) == \
        os.path.join(folder, 'Published')
    assert publish.target_folder({'folder': folder, 'subfolder': ''}) == folder


def test_archive_moves_files_and_lists():
    folder = _compat.tmpdir('publish_archive' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    for name in ('HSP_Hospital_20261001_v01.nwd', 'HSP_Hospital_20261005_v02.nwd'):
        with open(os.path.join(folder, name), 'wb') as handle:
            handle.write(b'nwd')
    names = publish.list_files(folder)
    plan = publish.archive_plan(names, TEMPLATE, _values(), 'HSP_Hospital_20261005_v02.nwd',
                                publish.list_files(os.path.join(folder, 'Archive')))
    moved, failed = publish.archive(folder, plan)
    assert moved == ['HSP_Hospital_20261001_v01.nwd'] and failed == []
    assert publish.list_files(os.path.join(folder, 'Archive')) == ['HSP_Hospital_20261001_v01.nwd']
    assert publish.list_files(folder) == ['HSP_Hospital_20261005_v02.nwd']
    assert publish.list_files(os.path.join(folder, 'nope')) == []
    assert publish.archive(folder, []) == ([], [])


def test_profiles_and_history_storage():
    folder = _compat.tmpdir('publish_profiles' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    previous = paths.redirect(folder)
    try:
        assert publish.profile_names() == []
        publish.save_profile('Weekly', {'subfolder': 'Weekly', 'method': 'export'})
        assert publish.profile_names() == ['Weekly']
        assert publish.load_profile('weekly')['method'] == 'export'
        assert publish.load_profile('Nope') is None
        from namo import store
        record = publish.history_record('x.nwd', 1, 'publish', 1, 'skipped', 'u', r'C:\J\Job.nwf', 0)
        assert publish.log_history(record, doc=object(), doc_path=r'C:\J\Job.nwf') is None
        records = store.RecordStore(publish.HISTORY_STORE, doc_path=r'C:\J\Job.nwf').list()
        assert [r['id'] for r in records] == ['P0001'] and records[0]['name'] == 'x.nwd'
    finally:
        paths.redirect(previous)


# ---- API half through a fake document -------------------------------------------------------


class _Options(object):
    pass


class _Props(object):
    pass


class _Doc(object):
    def __init__(self):
        self.calls = []

    def PublishFile(self, path, options, props):
        self.calls.append(('publish', path, dict(options.__dict__), dict(props.__dict__)))

    def ExportToNwd(self, path, options):
        self.calls.append(('export', path, dict(options.__dict__)))

    def SaveFile(self, path):
        self.calls.append(('save', path))


def _with_fake_api(fn):
    import sys
    import types
    names = ('pynavis', 'pynavis._api', 'pynavis.export', 'pynavis.doc')
    saved = dict((n, sys.modules.get(n)) for n in names)
    package = types.ModuleType('pynavis')
    package.__path__ = []
    api = types.ModuleType('pynavis._api')

    class Api(object):
        NwdExportOptions = _Options
        PublishProperties = _Props
    api.Api = Api
    doc_module = types.ModuleType('pynavis.doc')
    export = types.ModuleType('pynavis.export')
    export.save_nwd = lambda path, doc=None, version=None: doc.SaveFile(path)
    package._api, package.export, package.doc = api, export, doc_module
    for name, module in (('pynavis', package), ('pynavis._api', api), ('pynavis.export', export),
                         ('pynavis.doc', doc_module)):
        sys.modules[name] = module
    try:
        return fn()
    finally:
        for name in names:
            if saved[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved[name]


def test_publish_methods():
    doc = _Doc()
    props = {'title': 'T', 'author': 'A', 'exclude_hidden': True, 'expiry_days': 0}

    def go():
        publish.publish(doc, r'C:\x.nwd', 'publish', props)
        publish.publish(doc, r'C:\y.nwd', 'export', props)
        publish.publish(doc, r'C:\z.nwd', 'save', props)
    _with_fake_api(go)
    kind, path, options, properties = doc.calls[0]
    assert (kind, path) == ('publish', r'C:\x.nwd')
    assert options == {'ExcludeHiddenItems': True, 'EmbedXrefs': True}
    assert properties['Title'] == 'T' and properties['Author'] == 'A'
    assert properties['AllowResave'] is True and 'ExpiryDate' not in properties
    assert doc.calls[1] == ('export', r'C:\y.nwd', {'ExcludeHiddenItems': True, 'EmbedXrefs': True})
    assert doc.calls[2] == ('save', r'C:\z.nwd')


def test_publish_expiry_uses_net_datetime():
    _compat.require_ironpython('needs System.DateTime')
    doc = _Doc()
    _with_fake_api(lambda: publish.publish(doc, r'C:\x.nwd', 'publish', {'expiry_days': 10}))
    expiry = doc.calls[0][3]['ExpiryDate']
    from System import DateTime
    days = (expiry - DateTime.Now).TotalDays
    assert 9.9 < days < 10.1


def test_form_fields_parse_and_validate():
    from namo import ui
    folder = _compat.tmpdir('publish_form' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    settings = publish.normalize_settings({'folder': folder, 'method': 'export',
                                           'preflight_profile': 'QA'})
    fields = ui.normalize_fields(publish.form_fields(settings, '', ['Standard', 'QA'], 'amol'))
    by_key = dict((f['key'], f) for f in fields if f.get('key'))
    assert by_key['folder']['default'] == folder
    assert by_key['author']['default'] == 'amol' and by_key['method']['default'] == 'export'
    assert by_key['preflight_profile']['default'] == 'QA'
    raws = dict((f['key'], f.get('default')) for f in fields if f.get('key'))
    raws['folder'] = folder
    raws['expiry_days'] = '30'
    values, errors = ui.collect(fields, raws)
    assert errors == {}, errors
    assert values['method'] == 'export' and values['expiry_days'] == 30
    values, errors = ui.collect(fields, dict(raws, template='{file}_{phase}.nwd'))
    assert 'Unknown token: {phase}.' in errors['template']
    missing = publish.normalize_settings({'folder': r'C:\definitely\not\here', 'preflight_profile': 'Gone'})
    fields = ui.normalize_fields(publish.form_fields(missing, os.path.join(folder, 'A.nwf'), [], 'u'))
    by_key = dict((f['key'], f) for f in fields if f.get('key'))
    assert by_key['folder']['default'] == folder
    assert by_key['preflight_profile']['default'] == 'Standard'
    assert publish.start_folder({'folder': folder}, '') == folder


# ---- refit: never write over or move the open document or a model file --------------------


def test_protected_paths_and_target_problem():
    protected = publish.protected_paths(r'C:\P\Model.nwf', [r'C:\P\ARCH.nwc', '', None, r'C:\P\arch.RVT'])
    assert len(protected) == 3
    assert publish.is_protected(r'c:\p\MODEL.NWF', protected)
    assert publish.is_protected(r'C:\P\sub\..\ARCH.nwc', protected)
    assert not publish.is_protected(r'C:\P\Model_v01.nwd', protected)
    assert publish.protected_paths('', []) == set()
    assert publish.target_problem(r'C:\P\Model_v01.nwd', protected, exists=False) is None
    assert 'open document' in publish.target_problem(r'C:\P\Model.nwf', protected, exists=True)
    assert 'already there' in publish.target_problem(r'C:\P\Model_v01.nwd', protected, exists=True)


def test_archive_plan_leaves_the_open_document_where_it_is():
    # after Save as NWD the open document IS the last published version: the next
    # publish must not move it into Archive from under Navisworks
    folder = ['HSP_Hospital_20261001_v01.nwd', 'HSP_Hospital_20261003_v02.nwd',
              'HSP_Hospital_20261005_v03.nwd']
    plan = publish.archive_plan(folder, TEMPLATE, _values(), 'HSP_Hospital_20261005_v03.nwd',
                                keep=['hsp_hospital_20261003_V02.nwd'])
    assert [p['name'] for p in plan] == ['HSP_Hospital_20261001_v01.nwd']


def test_archive_never_overwrites_a_file_already_archived():
    folder = _compat.tmpdir('publish_archive_keep' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    os.makedirs(os.path.join(folder, 'Archive'))
    for name in ('A_v01.nwd', os.path.join('Archive', 'A_v01.nwd')):
        with open(os.path.join(folder, name), 'wb') as handle:
            handle.write(name.encode('ascii'))
    moved, failed = publish.archive(folder, [{'name': 'A_v01.nwd', 'target': 'A_v01.nwd', 'version': 1}])
    assert moved == [] and failed == ['A_v01.nwd']
    with open(os.path.join(folder, 'Archive', 'A_v01.nwd'), 'rb') as handle:
        assert handle.read() == os.path.join('Archive', 'A_v01.nwd').encode('ascii')


def test_toast_says_exactly_what_was_written():
    level, message, detail = publish.toast_text('A_v02.nwd', r'C:\P', 0, [], None, 'save', 5 * 1024 * 1024)
    assert message == 'Saved as A_v02.nwd'
    assert detail == os.path.join('C:\\P', 'A_v02.nwd') + ', 5.0 MB. It is now the open document.'
    question = publish.save_question('A_v02.nwd', 'Model.nwf')
    assert 'A_v02.nwd the open document' in question and 'Model.nwf stays on disk' in question


def test_confirm_text_names_the_file_and_what_moves():
    text = publish.confirm_text('A_v03.nwd', r'C:\P\Published', 'publish', 2, 'Model.nwf')
    lines = text.split('\n')
    assert lines[0] == 'Publish A_v03.nwd?' and r'Folder: C:\P\Published' in lines
    assert '2 older versions will move into Archive.' in lines
    assert lines[-1] == 'The open document is not changed.'
    text = publish.confirm_text('A_v03.nwd', r'C:\P', 'export', 1)
    assert text.startswith('Export A_v03.nwd?') and '1 older version will move into Archive.' in text
    text = publish.confirm_text('A_v03.nwd', r'C:\P', 'save', 0, 'Model.nwf')
    assert text.startswith('Save as A_v03.nwd?') and 'Archive' not in text
    assert 'A_v03.nwd becomes the open document. Model.nwf stays on disk' in text

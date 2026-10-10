# -*- coding: utf-8 -*-
"""namo.reportrunner: the template catalog (built and unbuilt reports), generated forms
and the config they give back, export/import bundles, batch runs and their summary."""
import json
import os

import _compat

from namo import paths, reportrunner as rr, reports, templates

REGISTRY = [('alpha', 'Alpha Report', 'rep_alpha'), ('beta', 'Beta Report', 'rep_beta'),
            ('gamma', 'Gamma Report', 'rep_gamma')]


class FakeStore(object):
    data = {}

    def __init__(self, report_id):
        self.report_id = report_id

    def names(self):
        return sorted(self.data.get(self.report_id, {}))

    def get(self, name):
        found = self.data.get(self.report_id, {}).get(name)
        return dict(found) if found is not None else None

    def info(self, name):
        if name not in self.data.get(self.report_id, {}):
            return None
        return {'name': name, 'updated': '2026-10-05T14:30:12', 'user': 'amol'}


def fake_data():
    FakeStore.data = {'alpha': {'Weekly': {'folder': '', 'tests': ['A']}, 'Daily': {'scope': 'selection'}},
                      'gamma': {'Old': {'x': 1}}}


def test_catalog_lists_every_template_and_marks_unbuilt():
    fake_data()
    rows = rr.catalog(REGISTRY, exists=lambda rid: rid != 'gamma', store=FakeStore,
                      describe=lambda rid, config: '%d keys' % len(config))
    assert [(r['report'], r['name'], r['available']) for r in rows] == [
        ('alpha', 'Daily', True), ('alpha', 'Weekly', True), ('gamma', 'Old', False)]
    assert rows[0]['description'] == '1 keys' and rows[2]['description'] == rr.NOT_BUILT
    assert rr.cells(rows[1]) == ['Alpha Report', 'Weekly', '2 keys', '2026-10-05 14:30', 'amol']


def test_reports_list_for_the_new_chooser():
    fake_data()
    out = rr.reports_list(REGISTRY, exists=lambda rid: rid == 'beta', store=FakeStore)
    assert [(c['report'], c['available'], c['count']) for c in out] == [
        ('alpha', False, 2), ('beta', True, 0), ('gamma', False, 1)]


def test_real_registry_catalog_runs():
    previous = paths.redirect(_compat.tmpdir('reportrunner_real'))
    try:
        templates.Templates('stale_files').save('Every model', {'tolerance_seconds': 5.0})
        templates.Templates('clash_excel').save('Weekly', {'tests': []})
        rows = rr.catalog()
    finally:
        paths.redirect(previous)
    by_name = dict((r['name'], r) for r in rows)
    assert by_name['Every model']['available'] == reports.module_exists('stale_files')
    assert by_name['Weekly']['available'] == reports.module_exists('clash_excel')
    if not reports.module_exists('clash_excel'):
        assert by_name['Weekly']['description'] == rr.NOT_BUILT


def test_humanize_and_kinds():
    assert rr.humanize('count_items') == 'Count items'
    assert rr.kind_for(True) == 'check' and rr.kind_for(3) == 'int' and rr.kind_for(2.5) == 'number'
    assert rr.kind_for('x') == 'text' and rr.kind_for([]) == 'json' and rr.kind_for(None) == 'json'
    assert rr.ordered_keys({'b': 1, 'folder': ''}, {'a': 1, 'name_template': ''}) == \
        ['folder', 'name_template', 'a', 'b']


def test_fields_for_generates_typed_fields():
    defaults = {'folder': '', 'name_template': '{report} {date}', 'tests': [], 'images': False,
                'budget': 40000, 'tolerance': 0.5, 'scope': 'model', 'mapping': {}}
    config = dict(defaults, folder='%USERPROFILE%\\Reports', tests=['Ducts vs Pipes'], budget=10)
    fields, kinds = rr.fields_for(config, defaults, 'Weekly', existing=['Daily'])
    by_key = dict((f['key'], f) for f in fields)
    assert fields[0]['key'] == '__name' and fields[0]['default'] == 'Weekly'
    assert by_key['folder']['kind'] == 'text'               # %VARS% stay text (no Browse check)
    assert by_key['images']['kind'] == 'check' and by_key['budget']['kind'] == 'int'
    assert by_key['budget']['default'] == 10 and by_key['tolerance']['kind'] == 'number'
    assert by_key['tests']['kind'] == 'textarea' and json.loads(by_key['tests']['default']) == ['Ducts vs Pipes']
    assert by_key['scope']['hint'].startswith('Scheduled runs')
    assert fields[0]['validate']('daily') is not None and fields[0]['validate']('Weekly') is None
    assert by_key['tests']['validate']('{"a": 1}') == 'Enter a JSON list, like ["A", "B"].'
    assert by_key['tests']['validate']('[1, 2') is not None
    assert by_key['mapping']['validate']('[]') is not None and by_key['mapping']['validate']('{}') is None
    plain, _kinds = rr.fields_for({'folder': ''}, {'folder': ''})
    assert plain[1]['kind'] == 'folder'
    odd, _kinds = rr.fields_for({'tolerance': 'abc', 'budget': True}, {'tolerance': 2.0, 'budget': 10})
    odd = dict((f['key'], f) for f in odd)
    assert odd['tolerance']['default'] == 2.0 and odd['budget']['default'] == 10


def test_config_from_form_values():
    defaults = {'folder': '', 'tests': [], 'images': False, 'budget': 40000, 'name_template': 'x'}
    _fields, kinds = rr.fields_for(defaults, defaults, 'A')
    values = {'__name': '  Weekly\tcoordination ', 'folder': ' C:\\Out ', 'tests': '["A", "B"]', 'images': 1,
              'budget': 5, 'name_template': '{report}'}
    name, config = rr.config_from(values, kinds)
    assert name == 'Weekly coordination'
    assert config == {'folder': 'C:\\Out', 'tests': ['A', 'B'], 'images': True, 'budget': 5,
                      'name_template': '{report}'}


def test_bundle_round_trip_and_rejections():
    body = rr.bundle_body({'alpha': {'Weekly': {'config': {'a': 1}, 'updated': 'x', 'user': 'u'}}})
    parts = rr.bundle_parts(json.loads(json.dumps(body)), known_ids=['alpha'])
    assert sorted(parts) == ['alpha'] and parts['alpha']['format'] == templates.FORMAT
    assert parts['alpha']['templates']['Weekly']['config'] == {'a': 1}
    single = {'format': templates.FORMAT, 'version': 1, 'tool': 'alpha', 'templates': {}}
    assert rr.bundle_parts(single, known_ids=['alpha']) == {'alpha': single}
    for bad in (None, {'format': 'nope'}, {'format': templates.FORMAT, 'tool': 'zeta'},
                {'format': rr.BUNDLE_FORMAT, 'reports': {}},
                {'format': rr.BUNDLE_FORMAT, 'reports': {'zeta': {'x': {}}}}):
        error = _compat.raises(ValueError, rr.bundle_parts, bad, ['alpha'])
        assert str(error).endswith('.')


def test_entries_export_import_through_real_templates():
    previous = paths.redirect(_compat.tmpdir('reportrunner_bundle'))
    try:
        store = templates.Templates('stale_files')
        store.save('A', {'tolerance_seconds': 1.0})
        store.save('B', {'tolerance_seconds': 2.0})
        entries = rr.entries_of('stale_files', ['b', 'missing'])
        assert sorted(entries) == ['B'] and entries['B']['config'] == {'tolerance_seconds': 2.0}
        parts = rr.bundle_parts(rr.bundle_body({'stale_files': entries}))
        temp = os.path.join(paths.data_root(), 'part.json')
        paths.write_json(temp, parts['stale_files'])
        assert store.import_file(temp) == 1
        assert store.names() == ['A', 'B', 'B (2)']
    finally:
        paths.redirect(previous)


def test_prepared_config_folder_override():
    config = {'folder': 'C:\\A', 'path': 'C:\\A\\x.xlsx', 'k': [1]}
    out = rr.prepared_config(config, 'D:\\Out')
    assert out == {'folder': 'D:\\Out', 'path': '', 'k': [1]}
    out['k'].append(2)
    assert config['k'] == [1]
    assert rr.prepared_config(config) == config


def test_run_templates_in_order_with_progress_and_missing():
    fake_data()
    calls = []

    def runner(report_id, config, doc=None, interactive=True, progress=None):
        calls.append((report_id, config, interactive))
        progress(0.5, 'half')
        return dict(reports.result('success', 'Wrote it', 'detail', ['C:\\out\\%s.xlsx' % report_id]),
                    report=report_id, title=report_id, seconds=0.1)

    seen = []
    results = rr.run_templates([('alpha', 'Weekly'), ('alpha', 'Gone'), ('gamma', 'Old')], doc='DOC',
                               progress=lambda f, label: seen.append((round(f, 3), label)),
                               folder='D:\\Out', store=FakeStore, runner=runner)
    assert [r['template'] for r in results] == ['Weekly', 'Gone', 'Old']
    assert [r['level'] for r in results] == ['success', 'error', 'success']
    assert results[1]['message'] == 'Template not found'
    assert calls[0] == ('alpha', {'folder': 'D:\\Out', 'tests': ['A']}, False)
    assert (round(1 / 6.0, 3), 'Weekly: half') in seen and seen[-1] == (1.0, 'Done')


def test_run_templates_stops_on_cancel():
    fake_data()

    def runner(report_id, config, doc=None, interactive=True, progress=None):
        out = reports.result('info', 'Report cancelled')
        out['cancelled'] = True
        return out

    _compat.raises(reports.Cancelled, rr.run_templates, [('alpha', 'Weekly'), ('alpha', 'Daily')],
                   store=FakeStore, runner=runner)


def test_summarize():
    one = [dict(reports.result('success', 'Wrote 3 sheets', '', ['C:\\a.xlsx']), template='Weekly')]
    assert rr.summarize(one) == ('success', 'Weekly: Wrote 3 sheets', 'C:\\a.xlsx', ['C:\\a.xlsx'])
    many = one + [dict(reports.result('error', 'Clash Excel Report failed', 'boom'), template='Daily')]
    level, message, detail, paths_ = rr.summarize(many)
    assert (level, message, detail) == ('error', 'Ran 2 templates, 1 failed', 'Daily: Clash Excel Report failed')
    warned = one + [dict(reports.result('warning', 'Sampled'), template='Big')]
    assert rr.summarize(warned)[:2] == ('warning', 'Ran 2 templates, 1 with warnings')
    good = one + [dict(reports.result('success', 'Done', '', ['C:\\b.html']), template='B')]
    # the toast says where the files went
    assert rr.summarize(good) == ('success', 'Ran 2 templates', '2 files written, in C:\\',
                                  ['C:\\a.xlsx', 'C:\\b.html'])
    assert rr.files_text(['C:\\r\\a.xlsx', 'D:\\s\\b.html']) == '2 files written, the first in C:\\r'
    assert rr.files_text([]) is None
    assert rr.summarize([])[0] == 'info'


def test_run_closed_runs_after_the_window_and_is_silent_on_cancel():
    """Refit: Run closes the Report Templates window first; the run itself needs no
    window (a progress window over a modal window breaks modality)."""
    fake_data()
    toasts = []
    opened = []
    saved = (rr.run_templates, rr._toast)

    class FakeUi(object):
        @staticmethod
        def open_path(path):
            opened.append(('open', path))

        @staticmethod
        def show_in_explorer(path):
            opened.append(('reveal', path))

    class FakeProgress(object):
        CANCELLED = object()
        cancel = False

        @classmethod
        def run(cls, title, work):
            return cls.CANCELLED if cls.cancel else work(lambda fraction, label: True)

    import sys
    import namo
    held = dict((name, sys.modules.get(name)) for name in ('namo.ui', 'namo.progress'))
    held_attrs = dict((name, getattr(namo, name, None)) for name in ('ui', 'progress'))
    try:
        sys.modules['namo.ui'] = namo.ui = FakeUi
        sys.modules['namo.progress'] = namo.progress = FakeProgress
        rr._toast = lambda level, message, detail=None: toasts.append((level, message, detail))
        rr.run_templates = lambda pairs, doc=None, progress=None: [
            dict(reports.result('success', 'Wrote it', '', ['C:\\out\\%s.xlsx' % name]), template=name)
            for _rid, name in pairs]
        one = rr.run_closed([('alpha', 'Weekly')], doc='DOC', skipped=1)
        two = rr.run_closed([('alpha', 'Weekly'), ('alpha', 'Daily')])
        FakeProgress.cancel = True
        none = rr.run_closed([('alpha', 'Weekly')])
    finally:
        rr.run_templates, rr._toast = saved
        for name in held:
            if held[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = held[name]
        for name in held_attrs:
            if held_attrs[name] is None:
                if hasattr(namo, name):
                    delattr(namo, name)
            else:
                setattr(namo, name, held_attrs[name])
    assert len(one) == 1 and len(two) == 2 and none is None
    assert toasts == [('success', 'Weekly: Wrote it', 'C:\\out\\Weekly.xlsx 1 not run: report not built yet.'),
                      ('success', 'Ran 2 templates', '2 files written, in C:\\out')]     # cancel: no toast
    assert opened == [('open', 'C:\\out\\Weekly.xlsx'), ('reveal', 'C:\\out\\Weekly.xlsx')]


def test_schedule_problems():
    fake_data()
    rows = rr.catalog(REGISTRY, exists=lambda rid: rid != 'gamma', store=FakeStore,
                      describe=lambda rid, config: '')
    problems = rr.schedule_problems([('alpha', 'weekly'), ('alpha', 'Daily'), ('gamma', 'Old'),
                                     ('beta', 'Nope')], rows)
    assert problems == [
        'Daily works on the current selection, which a scheduled run does not have. Edit it to use the whole model.',
        'Gamma Report is not built yet, so Old cannot run.',
        'The template Nope no longer exists.']

# -*- coding: utf-8 -*-
"""namo.reports: the fixed registry, run() and output_path()."""
import datetime
import os
import sys
import types

import _compat
from _compat import raises

from namo import paths, reports

EXPECTED = [
    ('property_export', 'Property Export', 'rep_property_export'),
    ('model_tree', 'Model Tree Export', 'rep_model_tree'),
    ('count_by_property', 'Count by Property', 'rep_count_by_property'),
    ('data_validation', 'Data Validation', 'rep_data_validation'),
    ('clash_excel', 'Clash Excel Report', 'rep_clash_excel'),
    ('clash_html', 'Clash HTML Dashboard', 'rep_clash_html'),
    ('clash_matrix', 'Clash Count Matrix', 'rep_clash_matrix'),
    ('clash_delta', 'Clash Delta', 'rep_clash_delta'),
    ('clash_trends', 'Clash Trends', 'rep_clash_trends'),
    ('per_trade', 'Per-Trade Reports', 'rep_per_trade'),
    ('coordination', 'Coordination Report', 'rep_coordination'),
    ('kpi_export', 'KPI Export', 'rep_kpi_export'),
    ('health_check', 'Model Health Check', 'rep_health_check'),
    ('session_stats', 'Session Stats', 'rep_session_stats'),
    ('stale_files', 'Stale File Alert', 'rep_stale_files'),
    ('preflight', 'Preflight Checks', 'rep_preflight'),
    ('timeliner_export', 'TimeLiner Export', 'rep_timeliner_export'),
    ('schedule_health', 'Schedule Health', 'rep_schedule_health'),
    ('quick_takeoff', 'Quick Takeoff', 'rep_quick_takeoff'),
    ('zone_takeoff', 'Zone Takeoff', 'rep_zone_takeoff'),
    ('viewpoint_images', 'Viewpoints to Images', 'rep_viewpoint_images'),
    ('batch_pdf', 'Batch PDF Printer', 'rep_batch_pdf'),
]


def test_registry_is_exactly_the_contract():
    assert reports.REGISTRY == EXPECTED
    assert len(reports.REGISTRY) == 22
    assert reports.ids()[0] == 'property_export' and reports.ids()[-1] == 'batch_pdf'
    assert reports.title_of('clash_excel') == 'Clash Excel Report'
    raises(KeyError, reports.title_of, 'nope')
    raises(KeyError, reports.module_for, 'nope')


def test_available_lists_only_built_modules():
    built = reports.available()
    for rid, title in built:
        assert reports.module_exists(rid)
        assert (rid, title) in [(r, t) for r, t, _m in EXPECTED]
    for rid, _title, _module in EXPECTED:
        if not reports.module_exists(rid):
            assert rid not in [r for r, _t in built]


def _fake_module(name, run, default=None, describe=None):
    module = types.ModuleType('namo.' + name)
    module.TITLE = 'Fake'
    module.default_config = default or (lambda: reports.base_config(tests=[]))
    module.describe = describe or (lambda config: 'Fake with %d tests' % len(config['tests']))
    module.run = run
    return module


class _Installed(object):
    """Puts a fake rep_ module in place for one test: an empty marker file in a SCRATCH
    module folder (reports.MODULE_DIR, never the shared lib folder) plus the module object
    in sys.modules, so module_for() imports the fake."""

    def __init__(self, report_id, module):
        self.name = reports.entry(report_id)[2]
        self.module = module

    def __enter__(self):
        self.folder = _compat.tmpdir('f2-reports-modules')
        self.previous_dir = reports.MODULE_DIR
        reports.MODULE_DIR = self.folder
        open(os.path.join(self.folder, self.name + '.py'), 'w').close()
        self.previous_module = sys.modules.get('namo.' + self.name)
        sys.modules['namo.' + self.name] = self.module
        import namo
        self.previous_attr = getattr(namo, self.name, None)
        setattr(namo, self.name, self.module)
        return self

    def __exit__(self, *exc):
        reports.MODULE_DIR = self.previous_dir
        import namo
        if self.previous_module is None:
            sys.modules.pop('namo.' + self.name, None)
        else:
            sys.modules['namo.' + self.name] = self.previous_module
        if self.previous_attr is None:
            if hasattr(namo, self.name):
                delattr(namo, self.name)
        else:
            setattr(namo, self.name, self.previous_attr)
        return False


def test_run_merges_config_and_normalises_the_result():
    seen = {}

    def run(config, doc=None, interactive=True, progress=None):
        seen.update(config=config, doc=doc, interactive=interactive)
        if progress:
            progress(0.5, 'Half')
        return {'level': 'success', 'message': 'Wrote 1 file', 'paths': ['x.xlsx'], 'extra': 1}

    calls = []
    with _Installed('batch_pdf', _fake_module('rep_batch_pdf', run)):
        assert ('batch_pdf', 'Batch PDF Printer') in reports.available()
        out = reports.run('batch_pdf', {'tests': ['A']}, doc='DOC',
                          progress=lambda f, label: calls.append((f, label)))
        assert reports.describe('batch_pdf', {'tests': ['A', 'B']}) == 'Fake with 2 tests'
        assert reports.default_config('batch_pdf')['name_template'] == '{report} {date}'
    assert out['level'] == 'success' and out['message'] == 'Wrote 1 file'
    assert out['detail'] == '' and out['paths'] == ['x.xlsx'] and out['extra'] == 1
    assert out['report'] == 'batch_pdf' and out['title'] == 'Batch PDF Printer'
    assert out['seconds'] >= 0
    assert seen['config'] == {'folder': '', 'name_template': '{report} {date}', 'tests': ['A']}
    assert seen['doc'] == 'DOC' and seen['interactive'] is False
    assert calls == [(0.5, 'Half')]


def test_run_never_raises():
    out = reports.run('nope', {})
    assert out['level'] == 'error' and out['report'] == 'nope'

    missing = [r for r, _t, _m in EXPECTED if not reports.module_exists(r)]
    if missing:
        out = reports.run(missing[0], {})
        assert out['level'] == 'error' and 'not available' in out['message']

    def crash(config, doc=None, interactive=True, progress=None):
        raise RuntimeError('boom')

    def cancel(config, doc=None, interactive=True, progress=None):
        raise reports.Cancelled()

    class Cancelled(Exception):
        pass

    def foreign_cancel(config, doc=None, interactive=True, progress=None):
        raise Cancelled()

    def junk(config, doc=None, interactive=True, progress=None):
        return 'not a dict'

    with _Installed('batch_pdf', _fake_module('rep_batch_pdf', crash)):
        out = reports.run('batch_pdf', None)
    assert out['level'] == 'error' and out['message'] == 'Batch PDF Printer failed'
    assert 'boom' in out['detail']
    with _Installed('batch_pdf', _fake_module('rep_batch_pdf', cancel)):
        assert reports.run('batch_pdf', {})['message'] == 'Report cancelled'
    with _Installed('batch_pdf', _fake_module('rep_batch_pdf', foreign_cancel)):
        assert reports.run('batch_pdf', {})['level'] == 'info'
    with _Installed('batch_pdf', _fake_module('rep_batch_pdf', junk)):
        assert reports.run('batch_pdf', {})['level'] == 'error'


def test_result_helpers():
    assert reports.result('weird', 'm') == {'level': 'info', 'message': 'm', 'detail': '', 'paths': []}
    r = reports.normalise_result({'level': 'warning', 'message': 3})
    assert r == {'level': 'warning', 'message': '3', 'detail': '', 'paths': []}
    assert reports.normalise_result(None)['level'] == 'error'


def test_output_path():
    folder = _compat.tmpdir('f2-reports-output')
    previous = paths.redirect(folder)
    try:
        today = datetime.date.today().strftime('%Y-%m-%d')
        path = reports.output_path({}, 'Clash Excel Report', 'xlsx')
        assert path == os.path.join(folder, 'pyNavis', 'playground', 'reports', 'Clash Excel Report %s.xlsx' % today)
        assert os.path.isdir(os.path.dirname(path))
        target = os.path.join(folder, 'out')
        path = reports.output_path({'folder': target, 'name_template': '{report} - {test} {n}'},
                                   'Clash', '.html', values={'test': 'A/B', 'n': 3})
        assert path == os.path.join(target, 'Clash - A_B 3.html')
        path = reports.output_path({'folder': target, 'name_template': 'x.pdf'}, 'X', 'pdf')
        assert path == os.path.join(target, 'x.pdf')
        open(path, 'w').close()
        assert reports.output_path({'folder': target, 'name_template': 'x'}, 'X', 'pdf',
                                   unique=True) == os.path.join(target, 'x (2).pdf')
        os.environ['PLAYGROUND_F2_TEST_DIR'] = target
        path = reports.output_path({'folder': '%PLAYGROUND_F2_TEST_DIR%\\sub', 'name_template': 'r'},
                                   'R', 'csv')
        assert path == os.path.join(target, 'sub', 'r.csv') and os.path.isdir(os.path.join(target, 'sub'))
    finally:
        os.environ.pop('PLAYGROUND_F2_TEST_DIR', None)
        paths.redirect(previous)


class _FakeOutput(object):
    def __init__(self):
        self.calls = []

    def set_title(self, text):
        self.calls.append(('title', text))

    def print_html(self, html):
        self.calls.append(('html', html))

    def print_md(self, text):
        self.calls.append(('md', text))

    def print_table(self, rows, headers):
        self.calls.append(('table', rows, headers))

    def chart_bar(self, labels, values, title=None):
        self.calls.append(('bar', labels, values, title))

    def chart_line(self, labels, series, title=None):
        self.calls.append(('line', labels, sorted(series), title))


def test_page_records_every_output_kind_and_prints_in_order_once():
    built = []
    page = reports.Page('Counts').html('<b>card</b>').bar_chart(['a', 'b'], [2, 1], 'Top 2')
    page.table([('Walls', '2')], ('Category', 'Count')).md('Showing the first 1 of 2 rows.').md('')
    page.later(lambda: built.append(1) or '<i>links</i>').line_chart(['w1'], {'Open': [3]})
    assert built == []                                   # nothing touches the output window yet
    fake = _FakeOutput()
    assert page.show(fake) == 7
    assert [c[0] for c in fake.calls] == ['title', 'html', 'bar', 'table', 'md', 'html', 'line']
    assert fake.calls[2] == ('bar', ['a', 'b'], [2, 1], 'Top 2')
    assert fake.calls[3] == ('table', [['Walls', '2']], ['Category', 'Count'])
    assert fake.calls[5][1] == '<i>links</i>' and built == [1]
    assert page.show(fake) == 0 and len(fake.calls) == 7


def test_deliver_and_show_output():
    page = reports.Page().md('x')
    held = reports.deliver(reports.result('success', 'Done'), page, lambda fraction, label: True)
    assert held['output'] is page and page.calls         # behind a progress window: not printed
    fake = _FakeOutput()
    assert reports.show_output(held, fake) is True
    assert fake.calls == [('md', 'x')] and 'output' not in held
    assert reports.show_output(held, fake) is False      # nothing left
    assert reports.show_output(None) is False and reports.show_output(object()) is False
    assert 'output' not in reports.deliver(reports.result('info', 'Nothing'), None, None)


def test_clashrep_out_still_exports_page_and_deliver():
    from namo import clashrep_out
    assert clashrep_out.Page is reports.Page and clashrep_out.deliver is reports.deliver

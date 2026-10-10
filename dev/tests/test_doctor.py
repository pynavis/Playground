# -*- coding: utf-8 -*-
"""namo.doctor pure half: log scanning, every check from sample facts, the text report."""
import io
import os

import _compat

from namo import doctor

HEALTHY = {
    'navisworks': {'product': 'Navisworks Manage 2026', 'api': '23.0', 'year': 2026},
    'pynavis': {'version': '1.2.0', 'library': '1.2.0', 'runtime': 'C:\\pyNavis\\PyNavis.Runtime.dll'},
    'engines': {'ironpython': '3.4.2', 'cpython_configured': '', 'cpython_found': '', 'cpython_bundles': 0},
    'roots': [{'path': 'C:\\ext', 'exists': True}],
    'extensions': [{'name': 'Playground', 'folder': 'C:\\ext\\Playground.extension', 'tabs': 5, 'buttons': 115,
                    'problems': [], 'hooks': ['after-command'], 'startup': True}],
    'libs': [],
    'shortcuts': {'count': 12, 'problems': []},
    'panes': {'slots': 5, 'dockpanes': ['a', 'b']},
    'webview2': '128.0.1',
    'runner': 'C:\\pyNavis\\cli\\pynavis.exe',
    'plugins': [{'id': 'PyNavis.Boot.PYNV', 'name': 'pyNavis', 'developer': 'PYNV', 'loaded': True, 'failed': False},
                {'id': 'Clash.ADSK', 'name': 'Clash', 'developer': 'ADSK', 'loaded': True, 'failed': False}],
    'config': {'path': 'C:\\cfg.json', 'exists': True, 'error': None},
    'log': {'path': 'C:\\log', 'errors': [], 'total': 0},
    'folders': [{'label': 'Playground data', 'path': 'C:\\d', 'writable': True}],
    'overlay': True, 'pick': True,
}


def test_log_errors_since_the_last_boot():
    lines = ['2026-10-01 10:00:00.000 [ERROR] old one',
             '2026-10-02 09:00:00.000 [INFO ] ==== pyNavis runtime booting ====',
             '2026-10-02 09:00:01.000 [ERROR] Shortcut: bad',
             'Traceback line that continues the error',
             '2026-10-02 09:00:02.000 [INFO ] fine',
             '2026-10-02 09:00:03.000 [ERROR] second']
    errors, total = doctor.last_session_errors(lines)
    assert total == 2 and errors[0].endswith('Shortcut: bad') and errors[1].endswith('second')
    errors, total = doctor.last_session_errors(lines, cap=1)
    assert total == 2 and len(errors) == 1 and errors[0].endswith('second')
    assert doctor.last_session_errors([]) == ([], 0)


def test_healthy_machine():
    results = doctor.checks(HEALTHY)
    counts = doctor.totals(results)
    assert counts[doctor.FAIL] == 0 and counts[doctor.WARN] == 0
    assert doctor.headline(results) == ('success', 'Everything checks out')
    areas = [r[1] for r in results]
    for area in ('Navisworks', 'pyNavis', 'Engines', 'Extensions', 'Shortcuts', 'Panels', 'Windows',
                 'Add-ins', 'Settings', 'Log', 'Folders'):
        assert area in areas, area
    ext = [r for r in results if r[2] == 'Playground'][0]
    assert ext[3] == '5 tabs, 115 buttons, C:\\ext\\Playground.extension; hooks: after-command; startup.py'


def test_problems_are_reported():
    facts = dict(HEALTHY)
    facts['pynavis'] = {'version': '1.2.0', 'library': '1.1.0'}
    facts['engines'] = {'ironpython': '3.4.2', 'cpython_configured': 'C:\\py', 'cpython_found': '', 'cpython_bundles': 3}
    facts['roots'] = [{'path': 'D:\\gone', 'exists': False}]
    facts['extensions'] = [{'name': 'A', 'folder': 'x', 'tabs': 1, 'buttons': 2, 'problems': ['Stack s holds 1 button(s)']},
                           {'name': 'a', 'folder': 'y', 'tabs': 1, 'buttons': 2, 'problems': []}]
    facts['shortcuts'] = {'count': 3, 'problems': ["'k' wants Ctrl+K but 'j' already has it - first wins"]}
    facts['panes'] = {'slots': 5, 'dockpanes': list('abcdef')}
    facts['webview2'] = ''
    facts['plugins'] = [{'id': 'PyNavis.Boot.PYNV', 'name': 'pyNavis', 'developer': 'PYNV', 'loaded': True},
                        {'id': 'pynavis.boot.pynv', 'name': 'pyNavis', 'developer': 'PYNV', 'loaded': False},
                        {'id': 'X.ACME', 'name': 'Acme Tools', 'developer': 'ACME', 'loaded': True, 'failed': True}]
    facts['config'] = {'path': 'c', 'exists': True, 'error': 'c is not valid JSON, so nothing was saved.'}
    facts['log'] = {'path': 'L', 'errors': ['e1'], 'total': 4}
    facts['folders'] = [{'label': 'Team folder', 'path': '\\\\srv\\team', 'writable': False}]
    facts['overlay'] = False
    results = doctor.checks(facts)
    by_check = dict(((r[1], r[2]), r) for r in results)
    assert by_check[('pyNavis', 'Library')][0] == doctor.WARN
    assert by_check[('Engines', 'CPython')][0] == doctor.FAIL
    assert by_check[('Engines', 'CPython')][3] == '3 buttons need CPython and none was found at C:\\py.'
    assert by_check[('Extensions', 'Root')][0] == doctor.WARN
    assert by_check[('Extensions', 'A')][3].endswith('1 problem: Stack s holds 1 button(s)')
    assert by_check[('Extensions', 'Duplicate')][3].startswith('a is installed 2 times')
    assert by_check[('Shortcuts', 'Problem')][0] == doctor.WARN
    assert by_check[('Panels', 'Slots')][0] == doctor.WARN
    assert by_check[('Windows', 'WebView2 runtime')][0] == doctor.WARN
    assert by_check[('Add-ins', 'pyNavis loader')][0] == doctor.FAIL
    assert by_check[('Add-ins', 'Acme Tools')][3] == 'Failed to start (X.ACME).'
    assert by_check[('Add-ins', 'Third party')][3] == 'Acme Tools'
    assert by_check[('Settings', 'config.json')][0] == doctor.FAIL
    assert by_check[('Log', 'Errors this session')][3].startswith('4 errors')
    assert by_check[('Folders', 'Team folder')][0] == doctor.FAIL
    assert by_check[('pyNavis', 'View overlay')][0] == doctor.WARN
    level, text = doctor.headline(results)
    assert level == 'error' and text.startswith('4 problems')
    report = doctor.text_report(results, '2026-10-05 10:00')
    assert report.startswith('Playground Environment Doctor 2026-10-05 10:00\n\nPASS ')
    assert 'FAIL    Engines' in report
    assert report.rstrip().endswith('4 fail, %d info' % doctor.totals(results)[doctor.INFO])


def test_cpython_states():
    facts = {'engines': {'ironpython': 'x', 'cpython_configured': '', 'cpython_found': '', 'cpython_bundles': 0}}
    assert [r for r in doctor.checks(facts) if r[2] == 'CPython'][0][0] == doctor.INFO
    facts['engines']['cpython_configured'] = 'C:\\nope'
    assert [r for r in doctor.checks(facts) if r[2] == 'CPython'][0][0] == doctor.WARN
    facts['engines']['cpython_found'] = 'C:\\py\\python311.dll'
    assert [r for r in doctor.checks(facts) if r[2] == 'CPython'][0][0] == doctor.PASS


def test_probes_and_log_tail():
    folder = _compat.tmpdir('doctor_probe')
    assert doctor.probe_writable(os.path.join(folder, 'sub'))
    log = os.path.join(folder, 'pyNavis.log')
    with io.open(log, 'w', encoding='utf-8', newline='') as handle:
        handle.write(u'line one\nline two\n')
    assert doctor.read_log_tail(log) == ['line one', 'line two']
    assert doctor.read_log_tail(log, limit=12) == ['line two']
    assert doctor.read_log_tail(os.path.join(folder, 'missing.log')) == []


def test_product_name():
    assert doctor.product_name('Navisworks Manage', 2026) == 'Navisworks Manage 2026'
    assert doctor.product_name('Autodesk Navisworks Manage 2026', 2026) == 'Autodesk Navisworks Manage 2026'
    assert doctor.product_name('', 0) == 'Navisworks'

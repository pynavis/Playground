# -*- coding: utf-8 -*-
"""IronPython 3.4 side of the Playground harness (run through dev\\ipy.ps1).

    ipy.ps1 dev\\ipy_driver.py compile            compile every .py in the extension
    ipy.ps1 dev\\ipy_driver.py test [substring]   run dev\\tests\\test_*.py under IronPython
    ipy.ps1 dev\\ipy_driver.py smoke [substring]  run dev\\tests\\smoke_*.py (WPF builds, no show)

Tests are plain functions named test_* using bare asserts, so the same files run
under CPython pytest and here. Skip a test on one engine by raising SkipTest from
_compat (pytest's own skip is not available under IronPython).
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXT = os.path.join(ROOT, 'Playground.extension')
TESTS = os.path.join(HERE, 'tests')

EXIT_CODE = 0


def _py_files(top):
    for folder, dirs, files in os.walk(top):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in sorted(files):
            if name.endswith('.py'):
                yield os.path.join(folder, name)


def do_compile():
    bad = 0
    count = 0
    for path in _py_files(EXT):
        count += 1
        with open(path, 'rb') as handle:
            data = handle.read()
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError as error:
            bad += 1
            print('ENCODING %s: %s' % (path, error))
            continue
        try:
            compile(text, path, 'exec')
        except SyntaxError as error:
            bad += 1
            print('SYNTAX %s:%s: %s' % (path, error.lineno, error.msg))
    print('compiled %d file(s) under IronPython %s, %d failure(s)' % (
        count, sys.version.split()[0], bad))
    return 1 if bad else 0


def _run_module_tests(prefix, needle):
    import _compat
    failures = 0
    passed = 0
    skipped = 0
    names = sorted(n for n in os.listdir(TESTS) if n.startswith(prefix) and n.endswith('.py'))
    for name in names:
        if needle and needle not in name:
            continue
        modname = name[:-3]
        try:
            # Reuse a module another test already imported (pytest imports each file once
            # too): re-importing would give helper modules such as test_items a second
            # generation of fake classes and break isinstance checks in the full run.
            module = sys.modules.get(modname) or __import__(modname)
        except _compat.SkipTest as skip:
            skipped += 1
            print('SKIP  %s (%s)' % (modname, skip))
            continue
        except Exception:
            failures += 1
            print('ERROR importing %s' % modname)
            traceback.print_exc()
            continue
        tests = sorted(k for k in dir(module) if k.startswith('test_') and callable(getattr(module, k)))
        for test in tests:
            caught = _catch_callback_errors() if prefix == 'smoke_' else None
            try:
                getattr(module, test)()
                if caught is not None:
                    _check_callback_errors(caught)
                passed += 1
            except _compat.SkipTest as skip:
                skipped += 1
                print('SKIP  %s.%s (%s)' % (modname, test, skip))
            except Exception:
                failures += 1
                print('FAIL  %s.%s' % (modname, test))
                traceback.print_exc()
            finally:
                if caught is not None:
                    caught['restore']()
    print('IronPython: %d passed, %d failed, %d skipped' % (passed, failures, skipped))
    return 1 if failures else 0


def _catch_callback_errors():
    """Records what namo.ui.safe logs while a smoke test builds windows. A WPF callback
    that raises is swallowed and only logged, so a NameError in one (a nested function
    called before its def ran, as in Level Sectioner's chooser) would otherwise pass."""
    try:
        from namo import ui
    except Exception:
        return None
    original = ui.log_error
    seen = []

    def recording(message, logger=None):
        seen.append(message)
        return original(message, logger)

    ui.log_error = recording

    def restore():
        ui.log_error = original
    return {'seen': seen, 'restore': restore}


def _check_callback_errors(caught):
    bad = [m for m in caught['seen'] if 'NameError' in m or 'UnboundLocalError' in m]
    if bad:
        raise AssertionError('A window callback raised while building: ' + bad[0])


def main(argv):
    mode = argv[1] if len(argv) > 1 else 'test'
    needle = argv[2] if len(argv) > 2 else ''
    if mode == 'compile':
        return do_compile()
    if mode == 'test':
        return _run_module_tests('test_', needle)
    if mode == 'smoke':
        return _run_module_tests('smoke_', needle)
    print('unknown mode %r' % mode)
    return 2


EXIT_CODE = main(sys.argv)

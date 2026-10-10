# -*- coding: utf-8 -*-
"""Helpers shared by tests that must run under both CPython pytest and IronPython 3.4.

Keep tests to plain `def test_x():` functions with bare asserts. Use these instead of
pytest features so dev\\ipy_driver.py can run the same file.
"""
import os
import sys

IRONPYTHON = sys.implementation.name == 'ironpython'

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LIB = os.path.join(ROOT, 'Playground.extension', 'lib')
if LIB not in sys.path:
    sys.path.insert(0, LIB)

# The pure pynavis modules (settings, xl, clashgroup, memory's pure half, ...) importable
# under CPython too. Under the IronPython harness the installed runtime copy is already on
# sys.path ahead of this, so this only matters for pytest. Modules that need
# PyNavis.Runtime or Navisworks still fail to import under CPython: skip those tests.
PYNAVISLIB = os.path.join(os.environ.get('PYNAVIS_SRC') or os.path.join(os.path.dirname(ROOT), 'pyNavis'),
                          'pynavislib')
if os.path.isdir(PYNAVISLIB) and PYNAVISLIB not in sys.path:
    sys.path.append(PYNAVISLIB)


try:
    if IRONPYTHON:
        raise ImportError
    from _pytest.outcomes import Skipped as _SkipBase
except ImportError:
    _SkipBase = None


if _SkipBase is None:
    class SkipTest(Exception):
        """Raise to skip a test (or a whole module at import) on this engine."""
else:
    class SkipTest(_SkipBase):
        """Raise to skip a test (or a whole module at import) on this engine."""

        def __init__(self, msg=''):
            _SkipBase.__init__(self, msg, allow_module_level=True)


def raises(exc_type, fn, *args, **kwargs):
    """Assert fn(*args, **kwargs) raises exc_type; returns the exception."""
    try:
        fn(*args, **kwargs)
    except exc_type as error:
        return error
    raise AssertionError('%s was not raised' % exc_type.__name__)


def approx(a, b, tol=1e-9):
    """True when two floats (or equal-length sequences of floats) agree within tol."""
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(approx(x, y, tol) for x, y in zip(a, b))
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


_TMP_ROOT = [None]


def _tmp_root():
    """%TEMP%\\playground-tests\\<engine>-<pid>: one scratch root per test PROCESS, removed
    when the process ends.

    The root used to be shared by every run of an engine. Two verify runs at the same
    time (ten agents once shared this machine) then deleted each other's folders in the
    middle of a test: a report file gone between writing and reading it
    (test_preflight.test_report_writes_html_and_xlsx), or FileExistsError from the
    rmtree/makedirs race. A folder per process cannot collide; the engine name stays in
    it so a leftover from CPython never leaks into IronPython."""
    if _TMP_ROOT[0] is None:
        import atexit
        import shutil
        import tempfile
        base = os.path.join(tempfile.gettempdir(), 'playground-tests')
        root = os.path.join(base, '%s-%d' % (sys.implementation.name, os.getpid()))
        _sweep_stale(base)
        atexit.register(lambda: shutil.rmtree(root, ignore_errors=True))
        _TMP_ROOT[0] = root
    return _TMP_ROOT[0]


def _sweep_stale(base, older_than_hours=24.0):
    """Removes per-process roots (and the old shared 'cpython' / 'ironpython' folders)
    that nothing has touched for a day: what a killed run left behind."""
    import shutil
    import time
    try:
        names = os.listdir(base)
    except OSError:
        return
    cutoff = time.time() - older_than_hours * 3600.0
    for name in names:
        if not (name.startswith('cpython') or name.startswith('ironpython')):
            continue
        path = os.path.join(base, name)
        try:
            if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


def tmpdir(name):
    """A fresh, empty scratch folder for this test process:
    %TEMP%\\playground-tests\\<engine>-<pid>\\<name>."""
    import shutil
    path = os.path.join(_tmp_root(), name)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    if not os.path.isdir(path):
        os.makedirs(path)
    else:
        # Something still holds a file in it (a scanner, an open handle): empty what can
        # be emptied rather than fail the test on FileExistsError.
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
                else:
                    os.remove(full)
            except OSError:
                pass
    return path


def require_cpython(reason='needs CPython'):
    if IRONPYTHON:
        raise SkipTest(reason)


def require_ironpython(reason='needs IronPython and .NET'):
    if not IRONPYTHON:
        raise SkipTest(reason)

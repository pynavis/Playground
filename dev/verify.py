# -*- coding: utf-8 -*-
"""Runs every Playground check that does not need Navisworks, in order, and summarises.

    python dev/verify.py              all stages
    python dev/verify.py --fast       skip the IronPython smoke stage
    python dev/verify.py -k clash     only tests whose file name contains 'clash'

Stages:
  1. check.py      bundle contract + house rules (CPython, static)
  2. pytest        dev/tests/test_*.py under CPython
  3. ipy compile   every extension .py compiled by IronPython 3.4 (the real engine)
  4. ipy test      dev/tests/test_*.py again under IronPython 3.4
  5. ipy smoke     dev/tests/smoke_*.py: WPF windows built (not shown) under IronPython
  6. parse.ps1     the real pyNavis BundleParser over the root: what the ribbon would hold
  7. fresh_import  every namo module imported in a FRESH IronPython engine (no .NET
                   references left over from other tests, no Navisworks at import)
  8. pyflakes      undefined names in any extension file (pyNavis' injected globals
                   excepted); skipped when pyflakes is not installed
  9. catalog       tools/build_catalog.py --check, tools/package.py --check and
                   tools/build_site.py --check: red when catalog.json no longer matches
                   status.yaml and the bundles, or the site in docs/ no longer matches
                   catalog.json
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PS = ['powershell', '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-File']


def run(label, cmd, show_tail=40):
    print('=== %s' % label)
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    out = (proc.stdout or '') + (proc.stderr or '')
    lines = out.strip().splitlines()
    for line in lines[-show_tail:]:
        print('  ' + line)
    print('  -> %s' % ('ok' if proc.returncode == 0 else 'FAILED (%d)' % proc.returncode))
    return proc.returncode == 0


INJECTED = ('__event__', '__pane__', '__file__', '__runner__', '__commandpath__', '__title__',
            '__selfinit__', '__button__', '__pynavis__', '__model__', '__models__', '__args__',
            '__run_dir__', '__result__')


def undefined_names():
    print('=== pyflakes (undefined names)')
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        print('  pyflakes not installed: skipped')
        return True
    proc = subprocess.run([sys.executable, '-m', 'pyflakes', os.path.join(ROOT, 'Playground.extension')],
                          cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    bad = []
    for line in (proc.stdout + proc.stderr).splitlines():
        if 'undefined name' in line or 'syntax' in line.lower() or 'invalid syntax' in line:
            if any("'%s'" % g in line for g in INJECTED):
                continue
            bad.append(line)
    for line in bad[:80]:
        print('  ' + line)
    print('  -> %s' % ('ok' if not bad else 'FAILED (%d)' % len(bad)))
    return not bad


def main():
    fast = '--fast' in sys.argv
    needle = ''
    if '-k' in sys.argv:
        needle = sys.argv[sys.argv.index('-k') + 1]
    results = []
    results.append(('check', run('check.py', [sys.executable, os.path.join(HERE, 'check.py'), '--quiet'], 200)))
    pytest_cmd = [sys.executable, '-m', 'pytest', os.path.join(HERE, 'tests'), '-q', '-p', 'no:cacheprovider']
    if needle:
        pytest_cmd += ['-k', needle]
    results.append(('pytest', run('pytest (CPython)', pytest_cmd)))
    ipy = PS + [os.path.join(HERE, 'ipy.ps1'), os.path.join(HERE, 'ipy_driver.py')]
    results.append(('ipy compile', run('IronPython compile', ipy + ['compile'])))
    results.append(('ipy test', run('IronPython tests', ipy + ['test'] + ([needle] if needle else []))))
    if not fast:
        results.append(('ipy smoke', run('IronPython WPF smoke', ipy + ['smoke'] + ([needle] if needle else []))))
    results.append(('parse', run('pyNavis BundleParser', PS + [os.path.join(HERE, 'parse.ps1')], 400)))
    results.append(('fresh', run('IronPython fresh-engine imports',
                                 PS + [os.path.join(HERE, 'ipy.ps1'), os.path.join(HERE, 'fresh_import.py')])))
    results.append(('names', undefined_names()))
    tools = os.path.join(ROOT, 'tools')
    fresh = run('catalog freshness (build_catalog --check)',
                [sys.executable, os.path.join(tools, 'build_catalog.py'), '--check'])
    fresh = run('release zip freshness (package --check)',
                [sys.executable, os.path.join(tools, 'package.py'), '--check']) and fresh
    fresh = run('site freshness (build_site --check)',
                [sys.executable, os.path.join(tools, 'build_site.py'), '--check']) and fresh
    results.append(('catalog', fresh))
    print('=== summary: ' + ', '.join('%s %s' % (n, 'ok' if ok else 'FAILED') for n, ok in results))
    return 0 if all(ok for _, ok in results) else 1


if __name__ == '__main__':
    sys.exit(main())

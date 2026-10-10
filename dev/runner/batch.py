# -*- coding: utf-8 -*-
"""Runs Playground tools one by one under `pynavis run` and records each outcome (dev only).

    python dev/runner/batch.py KEY [KEY ...] [--select-all|--select-first] [--model PATH]
    python dev/runner/batch.py --file keys.txt [...]

One hidden Navisworks session per tool (the runner takes one script per invocation),
120 s timeout each. Every run appends one JSON line to D:/Temp/pg-runner/ledger.jsonl:
key, select mode, outcome, error, traceback head, run folder id, transcript excerpt,
blocked shell calls. CPython 3, stdlib only. Never passes --save or --show. Before each
tool it checks free memory and stops (exit 3, "PAUSED before <key>") under 2 GB.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(os.environ.get('APPDATA', ''), 'pyNavis', 'cli', 'pynavis.exe')
DRIVER = os.path.join(HERE, 'run_tool.py')
WORK = r'D:\Temp\pg-runner'
MODEL = os.path.join(WORK, 'models', 'a.nwd')
LEDGER = os.path.join(WORK, 'ledger.jsonl')
TIMEOUT = 120
MIN_FREE_MB = 2048     # pause the batch rather than start Navisworks below this


def free_mb():
    """Free physical memory in MB (GlobalMemoryStatusEx), or None when unknown."""
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.ullAvailPhys // (1024 * 1024)
    except Exception:
        return None


def run_one(key, select=None, model=MODEL):
    cmd = [RUNNER, 'run', DRIVER, model, '--timeout', str(TIMEOUT), '--', key]
    if select:
        cmd.append('--select-' + select)
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=TIMEOUT + 120)
        out, code = (proc.stdout or '') + (proc.stderr or ''), proc.returncode
    except subprocess.TimeoutExpired as error:
        out, code = str(error.stdout or ''), 'hung'
    entry = {'key': key, 'select': select or '', 'exit': code, 'wall': round(time.time() - started, 1)}
    match = re.search(r'Summary: (.+results\.json)', out)
    run_dir = os.path.dirname(match.group(1).strip()) if match else ''
    entry['run'] = os.path.basename(run_dir)
    result, status, transcript = None, None, ''
    if run_dir:
        try:
            with open(os.path.join(run_dir, 'results.json'), encoding='utf-8') as handle:
                summary = json.load(handle)
            model_row = summary['models'][0]
            status, result = model_row.get('status'), model_row.get('result')
            entry['runner_error'] = (model_row.get('error') or '')[:400]
        except Exception as error:
            entry['runner_error'] = 'results.json unreadable: %s' % error
        path = os.path.join(run_dir, 'transcript-1.txt')
        if os.path.isfile(path):
            with open(path, encoding='utf-8', errors='replace') as handle:
                transcript = handle.read()
    entry['status'] = status
    lines = [line for line in transcript.splitlines() if line.strip()]
    entry['transcript'] = lines[:12]
    entry['transcript_traceback'] = 'Traceback' in transcript
    if isinstance(result, dict):
        entry['outcome'] = result.get('outcome')
        entry['error'] = result.get('error', '')
        entry['traceback'] = '\n'.join((result.get('traceback') or '').strip().splitlines()[-8:])
        entry['blocked'] = result.get('blocked', [])
        entry['selected'] = result.get('selected', 0)
        entry['seconds'] = result.get('seconds')
        entry['namo'] = result.get('namo')
        if result.get('pre_error'):
            entry['pre_error'] = result['pre_error']
        if entry['outcome'] == 'ok' and entry['transcript_traceback']:
            entry['outcome'] = 'failed'
            entry['error'] = 'Traceback in the transcript'
    else:
        entry['outcome'] = 'failed'
        entry['error'] = entry.get('runner_error') or ('runner exit %s with no result' % code)
        entry['console'] = out.strip().splitlines()[-15:]
    with open(LEDGER, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry) + '\n')
    return entry


def main(argv):
    select, model, keys = None, MODEL, []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('--select-all', '--select-first'):
            select = arg.split('-')[-1]
        elif arg == '--model':
            i += 1
            model = argv[i]
        elif arg == '--file':
            i += 1
            with open(argv[i], encoding='utf-8') as handle:
                keys += [line.strip() for line in handle if line.strip() and not line.startswith('#')]
        else:
            keys.append(arg)
        i += 1
    for key in keys:
        free = free_mb()
        if free is not None and free < MIN_FREE_MB:
            sys.stdout.write('PAUSED before %s: %d MB free (under %d MB)\n' % (key, free, MIN_FREE_MB))
            sys.stdout.flush()
            return 3
        entry = run_one(key, select, model)
        sys.stdout.write('%-12s %-6s %s  %s\n' % (entry['outcome'], entry.get('run', ''), key,
                                                   (entry.get('error') or '')[:140]))
        sys.stdout.flush()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]) or 0)

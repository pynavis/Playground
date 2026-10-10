# -*- coding: utf-8 -*-
"""Turns the runner ledger into dev/runner/RESULTS.md rows (dev only).

    python dev/runner/report.py            print the per-tool table (markdown) and counts
    python dev/runner/report.py --json     the same verdicts as JSON (for the status update)

Inputs: D:/Temp/pg-runner/ledger.jsonl (dev/runner/batch.py appends one line per run) and
dev/runner/skips.json ({bundle key: reason} for tools not run). For each tool the LAST run of
each selection mode counts. Verdict per tool:

  skipped-unsafe  listed in skips.json (not-runnable when the reason says so: dock panes)
  failed          a counted run failed
  needs-dialog    every counted run stopped at its first dialog, or at the tool's own
                  runner guard (a toast saying it needs the Navisworks window)
  ok              otherwise; 'path' says whether a run did real work ('ran to the end')
                  or stopped early on a missing precondition ('early exit')
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = r'D:\Temp\pg-runner\ledger.jsonl'
SKIPS = os.path.join(HERE, 'skips.json')
CATALOG = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'catalog.json')

TOAST = re.compile(r'^\[(info|success|warning|error)\] ([^:]+)(?::\s*(.*))?$')
EARLY_WORDS = ('nothing', 'no ', 'select ', 'open ', 'not ', 'needs', 'run ', 'pick ', 'there are no')
EARLY_INSIDE = (' yet', ' is off', ' is empty', 'already empty', 'not found', ' no ', ' not on')
GUARD_WORDS = ('navisworks window', 'pynavis run', 'needs navisworks', 'under the runner',
               'run it from the ribbon', 'needs a person at the screen')


def load_ledger():
    runs = {}
    if not os.path.isfile(LEDGER):
        return runs
    with open(LEDGER, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            runs.setdefault(entry['key'], {})[entry.get('select') or ''] = entry
    return runs


def toasts(entry):
    out = []
    for line in entry.get('transcript') or []:
        match = TOAST.match(line.strip())
        if match:
            out.append((match.group(1), match.group(2).strip(), (match.group(3) or '').strip()))
    return out


def describe(entry):
    """(kind, text) for one run: kind is 'dialog', 'failed', 'early' or 'real'."""
    outcome = entry.get('outcome')
    seen = toasts(entry)
    if outcome == 'needs-dialog':
        before = '; after toast "%s"' % seen[-1][1] if seen else ''
        return 'dialog', 'stopped at its first dialog%s' % before
    if outcome != 'ok':
        return 'failed', (entry.get('error') or 'failed')[:160]
    if not seen:
        other = [line for line in entry.get('transcript') or [] if line.strip()]
        return 'real', 'ran to the end (%s)' % ('wrote output' if other else 'no toast')
    level, title, detail = seen[-1]
    text = ('%s %s' % (title, detail)).lower()
    if any(word in text for word in GUARD_WORDS):
        return 'guard', 'runner guard: "%s"' % title
    if level in ('info', 'warning') and (title.lower().startswith(EARLY_WORDS)
                                          or any(word in title.lower() for word in EARLY_INSIDE)):
        return 'early', 'early exit: "%s"' % title
    return 'real', 'ran to the end: "%s"' % title


def verdicts():
    runs = load_ledger()
    skips = {}
    if os.path.isfile(SKIPS):
        with open(SKIPS, encoding='utf-8') as handle:
            skips = json.load(handle)
    with open(CATALOG, encoding='utf-8') as handle:
        keys = [tool['id'] for tool in json.load(handle)['tools']]
    out = []
    for key in keys:
        if key in skips:
            kind = 'not-runnable' if skips[key].startswith('Not runnable') else 'skipped-unsafe'
            out.append({'key': key, 'outcome': kind, 'path': '', 'note': skips[key], 'runs': ''})
            continue
        modes = runs.get(key, {})
        if not modes:
            out.append({'key': key, 'outcome': 'not-run', 'path': '', 'note': '', 'runs': ''})
            continue
        parts, kinds, notes, ids = [], [], [], []
        for mode in ('', 'all', 'first'):
            entry = modes.get(mode)
            if entry is None:
                continue
            kind, text = describe(entry)
            kinds.append(kind)
            label = {'': 'no selection', 'all': '17 parts selected', 'first': 'first element selected'}[mode]
            parts.append('%s: %s' % (label, text))
            ids.append(entry.get('run', ''))
            if entry.get('blocked'):
                notes.append('stubbed: %s' % ', '.join(b.split('(')[0] for b in entry['blocked']))
            if kind == 'failed' and entry.get('traceback'):
                notes.append(entry['traceback'].strip().splitlines()[-1][:200])
        if 'failed' in kinds:
            outcome = 'failed'
        elif all(kind in ('dialog', 'guard') for kind in kinds):
            # a tool that stops itself under the runner because it would ask is a dialog
            # stop too, only a polite one
            outcome = 'needs-dialog'
        else:
            outcome = 'ok'
        out.append({'key': key, 'outcome': outcome, 'real': 'real' in kinds, 'path': '; '.join(parts),
                    'note': '; '.join(notes), 'runs': ', '.join(i for i in ids if i)})
    return out


def main(argv):
    rows = verdicts()
    if '--json' in argv:
        sys.stdout.write(json.dumps(rows, indent=1))
        return 0
    counts = {}
    for row in rows:
        counts[row['outcome']] = counts.get(row['outcome'], 0) + 1
    sys.stdout.write('| Bundle key | Outcome | Path run | Note | Run folder |\n|---|---|---|---|---|\n')
    for row in rows:
        sys.stdout.write('| `%s` | %s | %s | %s | %s |\n' % (
            row['key'], row['outcome'], row['path'].replace('|', '/'), row['note'].replace('|', '/'), row['runs']))
    sys.stdout.write('\n' + ', '.join('%s %d' % (k, v) for k, v in sorted(counts.items())) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

# -*- coding: utf-8 -*-
"""Applies the runner verdicts (dev/runner/report.py) to status.yaml (dev only).

    python dev/runner/apply_status.py [--date YYYY-MM-DD] [--dry-run]

Rules (dev/CHARTER.md: statuses only go up through evidence):
  ok with a run that did real work ('ran to the end')
        -> launched, by: runner, note "Ran headless under pynavis run against a sample
           model; <path>; result not checked by a person". An entry already launched
           from the log keeps its status, by and date; the runner note is merged in. A
           previous runner entry is replaced.
  failed -> known-issue with the first error line (never over a launched/verified entry).
  ok on an early exit only, needs-dialog, skipped-unsafe, not-run -> no change.
  EXTRA notes (below) override the generated note for one key.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STATUS = os.path.join(ROOT, 'status.yaml')

EXTRA = {
    'Views.tab/Navigate.panel/Level_Sectioner.pushbutton':
        'NameError fixed 2026-10-09; reran headless. The sample model has no levels, so the rerun '
        'took the "No levels found" exit; the fixed chooser path is pinned by a smoke test, not yet '
        'clicked in Navisworks.',
}
FORCE_LAUNCHED = set(EXTRA)


def read(path):
    header, entries, order, key = [], {}, [], None
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            text = line.rstrip('\n')
            if not entries and (text.startswith('#') or not text.strip()):
                header.append(text)
                continue
            if not text.strip():
                continue
            if not text.startswith(' '):
                key = text.rstrip(':')
                entries[key] = {}
                order.append(key)
                continue
            field, value = text.strip().split(':', 1)
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"')
            entries[key][field] = value
    return header, entries


def write(path, header, entries):
    lines = list(header)
    if lines and lines[-1].strip():
        lines.append('')
    for key in sorted(entries):
        entry = entries[key]
        lines.append('%s:' % key)
        for field in ('status', 'note', 'date', 'by'):
            if entry.get(field):
                value = entry[field]
                if field == 'note':
                    value = '"%s"' % value.replace('"', '\\"')
                lines.append('  %s: %s' % (field, value))
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(lines) + '\n')


def sentence(text):
    return text[:1].upper() + text[1:]


def main(argv):
    date = '2026-10-09'
    if '--date' in argv:
        date = argv[argv.index('--date') + 1]
    rows = json.loads(subprocess.check_output([sys.executable, os.path.join(HERE, 'report.py'), '--json']))
    header, entries = read(STATUS)
    changed = []
    for row in rows:
        key, outcome = row['key'], row['outcome']
        current = entries.get(key, {})
        if key in FORCE_LAUNCHED and outcome == 'ok':
            entries[key] = {'status': 'launched', 'note': EXTRA[key], 'date': date, 'by': 'runner'}
            changed.append((key, 'launched'))
            continue
        if outcome == 'ok' and row.get('real'):
            path = [part for part in row['path'].split('; ') if 'ran to the end' in part][0]
            note = 'Ran headless under pynavis run against a sample model; %s; result not checked by a person' % path
            if row.get('note'):
                note += ' (%s)' % row['note']
            note = sentence(note.replace('"', "'")) + '.'
            if current.get('status') in ('launched', 'verified') and current.get('by') != 'runner':
                old = current.get('note', '')
                merged = (old.rstrip('.') + '. ' + note) if old and note not in old else (old or note)
                current['note'] = merged
                entries[key] = current
                changed.append((key, 'note merged'))
            else:
                entries[key] = {'status': 'launched', 'note': note, 'date': date, 'by': 'runner'}
                changed.append((key, 'launched'))
        elif outcome == 'failed' and current.get('status') not in ('launched', 'verified'):
            first = (row.get('note') or row.get('path') or 'failed').split('; ')[0]
            entries[key] = {'status': 'known-issue', 'note': sentence(first.replace('"', "'")),
                            'date': date, 'by': 'runner'}
            changed.append((key, 'known-issue'))
    for key, what in changed:
        sys.stdout.write('%-12s %s\n' % (what, key))
    if '--dry-run' not in argv:
        write(STATUS, header, entries)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

# -*- coding: utf-8 -*-
"""Finds search sets whose Search In scope finds nothing and re-scopes them."""
from pynavis import output, toast
from pynavis._api import Application

from namo import find_repair, items, ui

document = Application.ActiveDocument
HEADERS = ['Set', 'Folder', 'Status', 'Pointed at', 'Matched models', 'After']

entries, total = find_repair.scan(document)
model_names = [m['name'] for m in items.models(document)]

if not total:
    toast.info('No search sets', 'This model has no search sets to check.')
elif not entries:
    toast.success('Every search set has a working Search In scope',
                  '%d search %s checked.' % (total, 'set' if total == 1 else 'sets'))
else:
    holder = {}

    def selected_entries(guids):
        wanted = set(guids)
        return [e for e in entries if e['guid'] in wanted]

    def refresh():
        holder['win'].Tag.update(find_repair.table_rows(entries), find_repair.status_line(entries, total))

    def report(done, failed, skipped=0):
        refresh()
        parts = []
        if failed:
            parts.append('%d could not be rewritten; see the After column' % failed)
        if skipped:
            parts.append('%d had no file name to match' % skipped)
        if done:
            toast.show('warning' if parts else 'success',
                       'Re-scoped %d search %s' % (done, 'set' if done == 1 else 'sets'),
                       '; '.join(parts) or None)
        elif parts:
            toast.warning('No search set was re-scoped', '; '.join(parts))

    def use_matches(guids):
        chosen = selected_entries(guids)
        ready = [e for e in chosen if e['suggest']]
        done, failed = find_repair.rescope_many(ready, lambda e: e['suggest'], document)
        report(done, failed, len(chosen) - len(ready))

    def choose_models(guids):
        chosen = selected_entries(guids)
        picked = ui.choose('Search in these models', [{'value': n, 'cells': [n]} for n in model_names],
                           ['Model'], multiselect=True, ok='Re-scope', width=480, height=460,
                           prompt='The %d chosen search %s will search these models.' % (
                               len(chosen), 'set' if len(chosen) == 1 else 'sets'))
        if picked is None:
            return
        done, failed = find_repair.rescope_many(chosen, lambda e: list(picked), document)
        report(done, failed)

    def whole_model(guids):
        done, failed = find_repair.rescope_many(selected_entries(guids), lambda e: find_repair.WHOLE,
                                                document)
        report(done, failed)

    holder['win'] = ui.build_table(
        'Repair Search In', HEADERS, find_repair.table_rows(entries),
        actions=[{'label': 'Use matched models', 'fn': use_matches, 'primary': True},
                 ('Choose models', choose_models), ('Whole model', whole_model)],
        status=find_repair.status_line(entries, total), width=1100, height=560)
    ui.show_modal(holder['win'])

    changed = [e for e in entries if e['status'] in ('repaired', 'failed')]
    if changed:
        output.print_md('## Search In repairs')
        output.print_table([[e['name'], e['folder'], e['before'], e.get('after', '')] for e in changed],
                           ['Set', 'Folder', 'Before', 'After'])

# -*- coding: utf-8 -*-
"""The Write Data pulldown's dialogs and flows: Bulk Property Writer, Find and Replace,
Property Mapper and External Data Link. The logic they rest on (planning, matching,
mapping, writing inside one transaction) is namo.propwrite; this module asks, previews and
reports. Every flow takes the BoundScript `me` (settings) and the document, returns
nothing and toasts every outcome; cancelling any dialog is silent.
"""

import os
import time

from namo import data_common, propindex, propwrite

PROGRESS_FROM = 200          # writes to more items than this show a progress window
WRITE_TICK = 25              # ...which moves every this many items
UNMATCHED_STORED = 5000      # unmatched objects a data link remembers for "Select unmatched"


# =============================================================================
# Pure helpers
# =============================================================================


def write_summary(result, noun='item'):
    """(level, message, detail) for a propwrite.write_tabs result."""
    written = result['written']
    errors = result['errors']
    message = 'Wrote %s %s' % ('{:,}'.format(written), noun if written == 1 else noun + 's')
    if result.get('stopped'):
        return ('warning', 'Stopped after %s %s' % ('{:,}'.format(written), noun if written == 1 else noun + 's'),
                'The items already written keep their new values.')
    if errors:
        return ('warning', '%s, %d failed' % (message, len(errors)), errors[0])
    if not written:
        return ('info', 'Nothing changed', 'Every item already held these values.')
    # No promise about undo here: the writes are grouped in one transaction, but
    # whether Navisworks undoes custom tabs written through COM is not confirmed.
    detail = ''
    if result['unchanged']:
        detail = '%s already up to date.' % '{:,}'.format(result['unchanged'])
    return ('success', message, detail)


def sentences(*parts):
    """The non-empty parts joined by spaces (toast detail lines)."""
    return ' '.join(part for part in parts if part)


def match_status(plan, matching):
    """The preview's status line."""
    parts = ['%s matched' % '{:,}'.format(len(matching['matched'])),
             '%s not found' % '{:,}'.format(len(matching['unmatched']))]
    if matching['ambiguous']:
        parts.append('%s match several items' % '{:,}'.format(len(matching['ambiguous'])))
    if plan['duplicates']:
        parts.append('%s repeated keys (the later row wins)' % '{:,}'.format(len(plan['duplicates'])))
    if plan['blank']:
        parts.append('%s rows without a key' % '{:,}'.format(len(plan['blank'])))
    return ', '.join(parts)


def plan_from_matching(matching, tab):
    """[(item, {tab: values})] for write_tabs; an item matched by several rows takes
    the values of the last one."""
    order = []
    by_item = {}
    for entry, found in matching['matched']:
        for item in found:
            if item not in by_item:
                order.append(item)
                by_item[item] = {}
            by_item[item].update(entry['values'])
    return [(item, {tab: by_item[item]}) for item in order]


def unmatched_path(source):
    """'<folder>\\<stem> - unmatched.xlsx' beside the source spreadsheet."""
    folder = os.path.dirname(source)
    stem = os.path.splitext(os.path.basename(source))[0]
    return os.path.join(folder, '%s - unmatched.xlsx' % stem)


def change_rows(changes):
    """Find and Replace preview rows."""
    rows = []
    for index, change in enumerate(changes):
        item = change['item']
        try:
            name = item.DisplayName or item.ClassDisplayName
        except AttributeError:
            name = str(item)
        tab = change['category'] if change['custom'] else propwrite.CORRECTED_TAB
        prop = change['property'] if change['custom'] else propwrite.corrected_name(change['category'],
                                                                                    change['property'])
        rows.append({'cells': [name, tab, prop, change['old'], str(change['new'])], 'value': index})
    return rows


def coverage_rows(rows):
    return [{'cells': [model, field, total, hits, '%d%%' % int(round(share * 100))], 'value': i}
            for i, (model, field, total, hits, share) in enumerate(rows)]


EXAMPLE_PROFILE = '''# One field per line: Field: Category > Property | another source | ...
# The first source present and not blank wins. Optional regex after a ~:
#   ~ /pattern/              keeps group 1 (or the whole match)
#   ~ /pattern/replacement/  rewrites the value
# [model name] limits a line to models whose file name matches (* and ? allowed).
# tab: Name sets the tab written (default Standard).
System: Element > System Name | IFC > SystemName | Item > Layer
Level: Element > Level | Element > Reference Level | Element > Base Constraint
Mark: Element > Mark | IFC > Tag
'''


# =============================================================================
# Shared dialogs
# =============================================================================


def _toast():
    from pynavis import toast
    return toast


def preview(title, headers, rows, action, status):
    """A modal table with one primary action; True when the action was chosen."""
    from namo import ui
    chosen = {'go': False}

    def go(_selected):
        chosen['go'] = True
        win.Tag.close()
    win = ui.build_table(title, headers, rows, actions=[{'label': action, 'fn': go, 'needs_selection': False,
                                                         'primary': True}], status=status, width=920)
    ui.show_modal(win)
    return chosen['go']


def read_sheet(title):
    """(path, headers, data rows) of a spreadsheet the user picks, or None."""
    from pynavis import forms
    toast = _toast()
    path = forms.open_file(filter=data_common.TABLE_FILTER, title=title)
    if path is None:
        return None
    try:
        sheets = propwrite.table_sheets(path)
    except Exception as error:
        toast.error('Could not open the workbook', '%s: %s' % (os.path.basename(path), error))
        return None
    sheet = sheets[0] if sheets else None
    if len(sheets) > 1:
        sheet = forms.select_from_list(sheets, title=title, prompt='Read which sheet?')
        if sheet is None:
            return None
    try:
        rows = propwrite.read_table(path, sheet or None)
    except Exception as error:
        toast.error('Could not read the sheet', '%s: %s' % (os.path.basename(path), error))
        return None
    headers, data = propwrite.headers_of(rows)
    if not headers or not data:
        toast.info('The sheet is empty', 'Put a header row and data rows in %s.' % os.path.basename(path))
        return None
    return path, sheet, headers, data


def ask_key(headers, title):
    """(column index, key kind) for the spreadsheet, asking when no header names one."""
    from pynavis import forms
    from namo import ui
    index, kind = propwrite.detect_key(headers)
    if index is not None:
        return index, kind
    rows = [{'cells': [h or '(blank)'], 'value': i} for i, h in enumerate(headers)]
    picked = ui.choose(title, rows, ['Column'], multiselect=False, ok='Next',
                       prompt='Which column identifies the model items? (Name it Element ID, GUID or '
                              'Category > Property next time and it is found by itself.)')
    if picked is None:
        return None
    index = picked[0]
    options = ['Revit Element ID', 'GUID (UniqueId or IFC GlobalId)', 'Another property']
    choice = forms.ask_options('What does the column %s hold?' % headers[index], options, title=title)
    if choice is None:
        return None
    if choice == options[0]:
        return index, propwrite.KEY_ELEMENT_ID
    if choice == options[1]:
        return index, propwrite.KEY_GUID
    text = forms.ask_string('Which property holds the same values? Write it as Category > Property.',
                            default='Element > Mark', title=title)
    if text is None:
        return None
    kind = propwrite.key_kind(text)
    if not isinstance(kind, tuple):
        _toast().error('That is not a property', 'Write it as Category > Property, like Element > Mark.')
        return None
    return index, kind


def write(plan, doc, name, replace=False):
    """write_tabs with a progress window for large plans. Cancel stops cleanly after
    the current item: what was written stays and the result says 'stopped'. The
    bar moves every WRITE_TICK items (a window update per item would cost more than
    the write). Never None."""
    from namo import progress
    if len(plan) <= PROGRESS_FROM:
        return propwrite.write_tabs(plan, doc, name=name, replace=replace)
    state = {'stopped': False}

    def work(report):
        def tick(done, total):
            if state['stopped']:
                return False
            if done % WRITE_TICK and done != total:
                return True
            try:
                report(float(done) / total, 'Writing %s of %s' % ('{:,}'.format(done), '{:,}'.format(total)))
            except Exception as error:
                if type(error).__name__ != 'Cancelled':
                    raise
                state['stopped'] = True
                return False
            return True
        return propwrite.write_tabs(plan, doc, name=name, replace=replace, progress=tick)
    outcome = progress.run(name, work)
    if outcome is progress.CANCELLED:
        outcome = {'written': 0, 'unchanged': 0, 'errors': []}
        state['stopped'] = True
    outcome['stopped'] = state['stopped']
    return outcome


def scoped_items(doc, scope, level, title):
    """The scope's items with a progress window; None when cancelled or empty (toasted)."""
    from namo import progress
    toast = _toast()
    outcome = progress.run(title, lambda report: propindex.scope_items(
        scope, level, doc, tick=data_common.stage(report, 0.0, 0.0, 'Collecting items: %s'),
        budget=propindex.DEFAULT_BUDGET))
    if outcome is progress.CANCELLED:
        return None
    if not outcome:
        message, detail = data_common.nothing_text(scope)
        toast.info(message, detail)
        return None
    return outcome


# =============================================================================
# Bulk Property Writer
# =============================================================================

BULK_DEFAULTS = {'tab': propwrite.DEFAULT_TAB, 'lines': 'Status = Approved', 'target': 'objects',
                 'replace': False, 'scope': 'model', 'level': 'objects'}


def bulk_flow(me, doc):
    from pynavis import forms
    choice = forms.ask_options('Write properties to the selection, or match rows of a spreadsheet to model items?',
                               ['Write to selection', 'From Excel'], title='Bulk Property Writer')
    if choice is None:
        return
    values = me.get_config(BULK_DEFAULTS)
    if choice == 'Write to selection':
        bulk_selection(me, doc, values)
    else:
        bulk_excel(me, doc, values)


def bulk_selection(me, doc, values):
    from namo import items, ui
    toast = _toast()
    selected = items.selected(doc)
    if not selected:
        toast.info('Nothing selected', 'Select the items to write to, or choose From Excel.')
        return

    def check(answer):
        problems = {}
        if not (answer.get('tab') or '').strip():
            problems['tab'] = 'Name the tab.'
        found = propwrite.parse_lines(answer.get('lines') or '')[1]
        if found:
            problems['lines'] = found[0]
        return problems
    fields = [
        {'kind': 'text', 'key': 'tab', 'label': 'Tab', 'default': values.get('tab') or propwrite.DEFAULT_TAB},
        {'kind': 'textarea', 'key': 'lines', 'label': 'Properties (up to 10)', 'rows': 8,
         'default': values.get('lines') or '',
         'hint': 'One per line: Name = Value. Numbers and true/false are typed; quote text that looks '
                 'like a number, like "007".'},
        {'kind': 'radio', 'key': 'target', 'label': 'Write to', 'default': values.get('target') or 'objects', 'fallback': 'objects',
         'options': [('Their elements (objects)', 'objects'), ('The items exactly as selected', 'items')]},
        {'kind': 'check', 'key': 'replace', 'label': 'Replace the whole tab (otherwise merge into it)',
         'default': bool(values.get('replace'))},
    ]
    answer = ui.form('Bulk Property Writer', fields, ok='Write', validate=check,
                     intro='%s selected. Navisworks keeps these in a custom tab, saved with the NWF or NWD.'
                           % '{:,}'.format(len(selected)))
    if answer is None:
        return
    pairs, _problems = propwrite.parse_lines(answer['lines'])
    tab = answer['tab'].strip()
    values.update({'tab': tab, 'lines': answer['lines'], 'target': answer['target'],
                   'replace': bool(answer['replace'])})
    me.save_config(values)
    targets = selected if answer['target'] == 'items' else items.dedupe(items.object_of(i) for i in selected)
    new = dict(pairs)
    plan = [(item, {tab: new}) for item in targets]
    result = write(plan, doc, 'Write properties', replace=bool(answer['replace']))
    level, message, detail = write_summary(result)
    if level == 'success':
        message = 'Wrote %d %s to %s %s' % (len(pairs), 'property' if len(pairs) == 1 else 'properties',
                                             '{:,}'.format(result['written']),
                                             'item' if result['written'] == 1 else 'items')
        detail = sentences('Tab %s.' % tab, detail)
    toast.show(level, message, detail or None)


def bulk_excel(me, doc, values):
    from namo import progress, ui, xlsx
    toast = _toast()
    title = 'Bulk Property Writer'
    sheet = read_sheet('Write properties from a spreadsheet')
    if sheet is None:
        return
    path, _sheet_name, headers, data = sheet
    key = ask_key(headers, title)
    if key is None:
        return
    key_index, kind = key
    columns = [h for i, h in enumerate(headers) if i != key_index and h]
    if not columns:
        toast.info('No value columns', 'The sheet has only the key column; add columns to write.')
        return
    has_selection = data_common.selected_count(doc) > 0
    fields = [{'kind': 'label', 'text': 'Key column: %s (%s).' % (headers[key_index], propwrite.key_label(kind))},
              {'kind': 'text', 'key': 'tab', 'label': 'Tab', 'default': values.get('tab') or propwrite.DEFAULT_TAB,
               'required': True},
              {'kind': 'multi', 'key': 'columns', 'label': 'Columns to write', 'options': columns,
               'default': columns}]
    fields += data_common.scope_fields(has_selection, values.get('scope'), values.get('level'))
    answer = ui.form(title, fields, ok='Match')
    if answer is None:
        return
    if not answer['columns']:
        toast.info('No columns ticked', 'Tick at least one column to write.')
        return
    tab = answer['tab'].strip() or propwrite.DEFAULT_TAB
    values.update({'tab': tab, 'scope': answer['scope'], 'level': answer['level']})
    me.save_config(values)
    item_list = scoped_items(doc, answer['scope'], answer['level'], title)
    if item_list is None:
        return
    reader = propindex.Reader(doc)
    index = progress.run(title, lambda report: propwrite.key_index(
        item_list, kind, reader, tick=data_common.stage(report, 0.0, 1.0, 'Reading keys: %s')))
    if index is progress.CANCELLED:
        return
    plan = propwrite.plan_rows(headers, data, key_index, kind, answer['columns'])
    matching = propwrite.match_rows(plan['rows'], index)
    if not matching['matched']:
        toast.warning('No rows matched', 'None of the %s keys in %s matched a %s in scope.' % (
            '{:,}'.format(len(plan['rows'])), headers[key_index], propwrite.key_label(kind)))
        return
    rows = propwrite.preview_rows(plan, matching)
    targets = plan_from_matching(matching, tab)
    if not preview(title, ['Row', 'Key', 'Outcome', 'Values'], rows,
                   'Write %s %s' % ('{:,}'.format(len(targets)), 'item' if len(targets) == 1 else 'items'),
                   match_status(plan, matching)):
        return
    result = write(targets, doc, 'Write properties from Excel')
    level, message, detail = write_summary(result)
    if matching['unmatched']:
        head, out = propwrite.unmatched_sheet(headers, data, plan, matching, key_index)
        target = unmatched_path(path)
        try:
            xlsx.write_simple(target, [{'name': 'Unmatched', 'headers': head, 'rows': out}])
            note = '%s rows matched nothing; they are listed in %s.' % ('{:,}'.format(len(out)), target)
        except (IOError, OSError):
            note = '%s rows matched nothing (the list could not be saved: %s)' % (
                '{:,}'.format(len(out)), data_common.LOCKED)
        detail = sentences(note, detail)
        if level in ('success', 'info'):
            level = 'warning'
    toast.show(level, message, detail or None)


# =============================================================================
# Find and Replace
# =============================================================================

FIND_DEFAULTS = {'find': '', 'replace': '', 'regex': False, 'match_case': False, 'whole': False,
                 'where': 'all', 'property': 'Element > Mark', 'scope': 'model', 'level': 'objects'}


def find_flow(me, doc):
    from namo import progress, ui
    toast = _toast()
    title = 'Find and Replace'
    values = me.get_config(FIND_DEFAULTS)
    has_selection = data_common.selected_count(doc) > 0

    def check(answer):
        problems = {}
        try:
            propwrite.compile_find(answer.get('find'), answer.get('replace'), answer.get('regex'),
                                   answer.get('match_case'), answer.get('whole'))
        except ValueError as error:
            problems['find'] = str(error)
        if answer.get('where') == 'one':
            pair = propindex.split_pair(answer.get('property') or '')
            if pair is None or not pair[0] or not pair[1]:
                problems['property'] = 'Write it as Category > Property, like Element > Mark.'
        return problems
    fields = [
        {'kind': 'text', 'key': 'find', 'label': 'Find', 'default': values.get('find') or '', 'required': True},
        {'kind': 'text', 'key': 'replace', 'label': 'Replace with', 'default': values.get('replace') or ''},
        {'kind': 'check', 'key': 'match_case', 'label': 'Match case', 'default': bool(values.get('match_case'))},
        {'kind': 'check', 'key': 'whole', 'label': 'Whole value only', 'default': bool(values.get('whole'))},
        {'kind': 'check', 'key': 'regex', 'label': 'Regular expression (\\1 in the replacement is group 1)',
         'default': bool(values.get('regex'))},
        {'kind': 'radio', 'key': 'where', 'label': 'Look in', 'default': values.get('where') or 'all', 'fallback': 'all',
         'options': [('Every property', 'all'), ('One property', 'one')]},
        {'kind': 'text', 'key': 'property', 'label': 'Property', 'default': values.get('property') or '',
         'enabled_if': ('where', 'one'), 'placeholder': 'Element > Mark'},
    ]
    fields += data_common.scope_fields(has_selection, values.get('scope'), values.get('level'))
    intro = ('Navisworks properties are read-only, so a replaced value is written to a custom tab named %s, as '
             '"<Category> - <Property>". Values already in custom tabs are edited in place. You see every '
             'change before anything is written.' % propwrite.CORRECTED_TAB)
    answer = ui.form(title, fields, intro=intro, ok='Find', validate=check, width=520)
    if answer is None:
        return
    values.update(dict((k, answer[k]) for k in FIND_DEFAULTS if k in answer))
    me.save_config(values)
    apply = propwrite.compile_find(answer['find'], answer['replace'], answer['regex'], answer['match_case'],
                                   answer['whole'])
    only = propindex.split_pair(answer['property']) if answer['where'] == 'one' else None
    item_list = scoped_items(doc, answer['scope'], answer['level'], title)
    if item_list is None:
        return
    reader = propindex.Reader(doc)
    changes = progress.run(title, lambda report: propwrite.scan_find(
        item_list, apply, reader, only=only, tick=data_common.stage(report, 0.0, 1.0, 'Searching %s')))
    if changes is progress.CANCELLED:
        return
    if not changes:
        where = propindex.pair_text(*only) if only else 'any property'
        toast.info('Nothing matched', '"%s" is not in %s of the %s.' % (
            answer['find'], where, propindex.scope_text(answer['scope'], answer['level'], len(item_list))))
        return
    grouped = propwrite.group_changes(changes)
    if not preview(title, ['Item', 'Tab', 'Property', 'Old value', 'New value'], change_rows(changes),
                   'Apply %s %s' % ('{:,}'.format(len(changes)), 'change' if len(changes) == 1 else 'changes'),
                   '%s values on %s items' % ('{:,}'.format(len(changes)), '{:,}'.format(len(grouped)))):
        return
    result = write(grouped, doc, 'Find and replace')
    level, message, detail = write_summary(result)
    if level == 'success':
        message = 'Replaced %s %s on %s %s' % ('{:,}'.format(len(changes)), 'value' if len(changes) == 1 else 'values',
                                                '{:,}'.format(result['written']),
                                                'item' if result['written'] == 1 else 'items')
        native = len([c for c in changes if not c['custom']])
        if native:
            detail = sentences('%s native values went to the %s tab.' % ('{:,}'.format(native),
                                                                         propwrite.CORRECTED_TAB), detail)
    toast.show(level, message, detail or None)


# =============================================================================
# Property Mapper
# =============================================================================

MAPPER_TOOL = 'property_mapper'
RUN, NEW, EDIT, IMPORT, EXPORT, DELETE = ('Run a profile', 'New profile', 'Edit a profile', 'Import profiles',
                                          'Export profiles', 'Delete a profile')
MAPPER_DEFAULTS = {'profile': '', 'scope': 'model', 'level': 'objects'}


def mapper_flow(me, doc):
    from pynavis import forms
    from namo import templates
    store = templates.Templates(MAPPER_TOOL)
    names = store.names()
    if not names:
        edit_profile(store, None)
        return
    options = [RUN, NEW, EDIT, IMPORT, EXPORT, DELETE]
    choice = forms.ask_options('Map other properties into one standard tab. %d %s saved.' % (
        len(names), 'profile' if len(names) == 1 else 'profiles'), options, title='Property Mapper')
    if choice is None:
        return
    if choice == RUN:
        run_profile(me, doc, store)
    elif choice == NEW:
        edit_profile(store, None)
    elif choice == EDIT:
        name = pick_profile(store, 'Edit which profile?')
        if name is not None:
            edit_profile(store, name)
    elif choice == IMPORT:
        import_profiles(store)
    elif choice == EXPORT:
        export_profiles(store)
    else:
        delete_profile(store)


def pick_profile(store, prompt, remembered=None):
    from pynavis import forms
    names = store.names()
    if len(names) == 1:
        return names[0]
    return forms.select_from_list(names, title='Property Mapper', prompt=prompt,
                                  checked=[remembered] if remembered in names else None)


def edit_profile(store, name):
    from namo import ui
    toast = _toast()
    saved = store.get(name) if name else None
    text = (saved or {}).get('text') or EXAMPLE_PROFILE

    def check(answer):
        problems = {}
        if not (answer.get('name') or '').strip():
            problems['name'] = 'Name the profile.'
        found = propwrite.parse_profile(answer.get('text') or '')[1]
        if found:
            problems['text'] = found[0]
        return problems
    fields = [{'kind': 'text', 'key': 'name', 'label': 'Profile name', 'default': name or '', 'required': True},
              {'kind': 'textarea', 'key': 'text', 'label': 'Fields', 'rows': 14, 'default': text,
               'hint': 'Field: Category > Property | Category > Property ~ /regex/. Lines starting with # are notes.'}]
    answer = ui.form('Property Mapper profile', fields, ok='Save', validate=check, width=640)
    if answer is None:
        return
    profile, _problems = propwrite.parse_profile(answer['text'])
    try:
        if name and answer['name'].strip().lower() != name.lower():
            store.rename(name, answer['name'].strip())
        stored = store.save(answer['name'].strip(), {'text': answer['text'], 'profile': profile})
    except (ValueError, IOError, OSError) as error:
        toast.error('Could not save the profile', str(error))
        return
    toast.success('Profile saved', '%s: %d %s, writes the %s tab.' % (
        stored, len(propwrite.field_names(profile)), 'field' if len(propwrite.field_names(profile)) == 1
        else 'fields', profile['tab']))


def import_profiles(store):
    from pynavis import forms
    toast = _toast()
    path = forms.open_file(filter=data_common.JSON_FILTER, title='Import mapping profiles')
    if path is None:
        return
    try:
        count = store.import_file(path)
    except ValueError as error:
        toast.error('Could not import the profiles', str(error))
        return
    toast.success('Imported %d %s' % (count, 'profile' if count == 1 else 'profiles'), path)


def export_profiles(store):
    toast = _toast()
    path = data_common.ask_save('Mapping profiles - {date}', 'json', 'Export mapping profiles')
    if path is None:
        return
    try:
        count = store.export(path)
    except (IOError, OSError) as error:
        toast.error('Could not write the file', str(error))
        return
    toast.success('Exported %d %s' % (count, 'profile' if count == 1 else 'profiles'), path)


def delete_profile(store):
    from pynavis import forms
    toast = _toast()
    name = pick_profile(store, 'Delete which profile?')
    if name is None:
        return
    if not forms.confirm('Delete the mapping profile %s?' % name, title='Property Mapper'):
        return
    store.delete(name)
    toast.success('Profile deleted', name)


def run_profile(me, doc, store):
    from namo import progress, ui
    toast = _toast()
    title = 'Property Mapper'
    values = me.get_config(MAPPER_DEFAULTS)
    name = pick_profile(store, 'Run which profile?', values.get('profile'))
    if name is None:
        return
    saved = store.get(name) or {}
    profile, problems = propwrite.parse_profile(saved.get('text') or '')
    if problems:
        toast.error('The profile does not read', problems[0])
        return
    has_selection = data_common.selected_count(doc) > 0
    fields = data_common.scope_fields(has_selection, values.get('scope'), values.get('level'))
    answer = ui.form(title, fields, ok='Preview', intro='Profile %s writes the %s tab.' % (name, profile['tab']))
    if answer is None:
        return
    values.update({'profile': name, 'scope': answer['scope'], 'level': answer['level']})
    me.save_config(values)
    item_list = scoped_items(doc, answer['scope'], answer['level'], title)
    if item_list is None:
        return
    reader = propindex.Reader(doc)
    mapped = progress.run(title, lambda report: propwrite.map_items(
        profile, item_list, reader, tick=data_common.stage(report, 0.0, 1.0, 'Mapping %s')))
    if mapped is progress.CANCELLED:
        return
    fields_ = propwrite.field_names(profile)
    rows = propwrite.coverage([(model, result) for _item, model, result in mapped], fields_)
    plan = []
    for item, _model, result in mapped:
        found = dict((field, value) for field, (value, _source) in result.items() if value is not None)
        if found:
            plan.append((item, {profile['tab']: found}))
    if not plan:
        toast.info('Nothing mapped', 'None of the sources in %s is on the %s.' % (
            name, propindex.scope_text(answer['scope'], answer['level'], len(item_list))))
        return
    status = '%s of %s %s get at least one field' % ('{:,}'.format(len(plan)), '{:,}'.format(len(item_list)),
                                                      propindex.noun(answer['level'], len(item_list)))
    if not preview(title, ['Model', 'Field', 'Items', 'Mapped', 'Coverage'], coverage_rows(rows),
                   'Write the %s tab' % profile['tab'], status):
        return
    result = write(plan, doc, 'Map properties', replace=True)
    level, message, detail = write_summary(result)
    if level == 'success':
        detail = sentences('Tab %s.' % profile['tab'], detail)
    toast.show(level, message, detail or None)


# =============================================================================
# External Data Link
# =============================================================================

LINKS = 'data-links'


def _mtime(path):
    try:
        return os.path.getmtime(path) if path and os.path.exists(path) else None
    except OSError:
        return None


def link_store(doc):
    from namo import store
    return store.for_active_doc(LINKS, doc=doc)


def load_links(holder):
    data = holder.load({'links': []}) or {'links': []}
    return list(data.get('links') or [])


def save_links(holder, links):
    holder.save({'links': links})


def next_link_id(links):
    numbers = []
    for link in links:
        text = str(link.get('id') or '')
        if text[1:].isdigit():
            numbers.append(int(text[1:]))
    return 'L%03d' % ((max(numbers) if numbers else 0) + 1)


def link_flow(me, doc):
    from namo import ui
    toast = _toast()
    holder = link_store(doc)
    if holder.note:
        toast.info('Data links', holder.note)
    state = {'links': load_links(holder)}

    def rows():
        return propwrite.link_rows(state['links'], _mtime)

    def find(link_id):
        for link in state['links']:
            if link.get('id') == link_id:
                return link
        return None

    def persist():
        try:
            save_links(holder, state['links'])
        except (IOError, OSError) as error:
            toast.error('Could not save the data links', str(error))

    def status_text():
        count = len(state['links'])
        if not count:
            return 'No links yet. New link connects a spreadsheet to this document.'
        return '%d %s saved with this document\'s Playground data.' % (count, 'link' if count == 1 else 'links')

    def refresh_job(links):
        def job():
            refresh_links(doc, links)
            persist()
        return job

    def remove_job(chosen):
        def job():
            removed = remove_links(doc, chosen)
            if removed is None:
                return
            state['links'] = [link for link in state['links'] if link not in chosen]
            persist()
        return job

    # Refresh and Remove open a progress window. pyNavis' progress window re-enables the
    # Navisworks main window when it closes, which under this MODAL list would leave
    # Navisworks live behind it. So those actions close the list, do the work, and the
    # list comes back with the new state (ui.modal_loop).
    def build(defer):
        holder_ = {}

        def on_new(_selected):
            link = new_link(doc, state['links'])
            if link is None:
                return
            state['links'].append(link)
            persist()
            holder_['win'].Tag.update(rows(), status_text())
            from pynavis import forms
            if forms.confirm('Refresh %s now? It writes the %s tab to the matched objects.'
                             % (link['name'], link['tab']), title='External Data Link'):
                defer(refresh_job([link]))

        def on_refresh_all(_selected):
            if not state['links']:
                toast.info('No links yet', 'Make one with New link.')
                return
            defer(refresh_job(list(state['links'])))

        def on_refresh(selected):
            chosen = [find(i) for i in selected if find(i) is not None]
            if chosen:
                defer(refresh_job(chosen))

        def on_remove(selected):
            chosen = [find(i) for i in selected if find(i) is not None]
            if chosen:
                defer(remove_job(chosen))

        def on_unmatched(selected):
            link = find(selected[0]) if selected else None
            if link is not None:
                select_unmatched(doc, link)

        actions = [{'label': 'New link', 'fn': on_new, 'needs_selection': False, 'primary': True},
                   {'label': 'Refresh all', 'fn': on_refresh_all, 'needs_selection': False},
                   ('Refresh', on_refresh), ('Remove', on_remove), ('Select unmatched', on_unmatched)]
        holder_['win'] = ui.build_table('External Data Link', propwrite.LINK_HEADERS, rows(), actions=actions,
                                        status=status_text(), width=1100, height=480)
        return holder_['win']
    ui.modal_loop(build)


def new_link(doc, links):
    """Asks for a new link; returns the record or None."""
    from namo import ui
    toast = _toast()
    title = 'New data link'
    sheet = read_sheet(title)
    if sheet is None:
        return None
    path, sheet_name, headers, _data = sheet
    key = ask_key(headers, title)
    if key is None:
        return None
    key_index, kind = key
    columns = [h for i, h in enumerate(headers) if i != key_index and h]
    if not columns:
        toast.info('No value columns', 'The sheet has only the key column.')
        return None
    stem = os.path.splitext(os.path.basename(path))[0]
    fields = [{'kind': 'label', 'text': 'Key: %s matched to %s.' % (headers[key_index], propwrite.key_label(kind))},
              {'kind': 'text', 'key': 'name', 'label': 'Link name', 'default': stem, 'required': True},
              {'kind': 'text', 'key': 'tab', 'label': 'Tab to write', 'default': stem, 'required': True,
               'hint': 'Refreshing replaces this whole tab on every matched object.'},
              {'kind': 'multi', 'key': 'columns', 'label': 'Columns to bring in', 'options': columns,
               'default': columns}]
    answer = ui.form(title, fields, ok='Save link')
    if answer is None:
        return None
    if not answer['columns']:
        toast.info('No columns ticked', 'Tick at least one column to bring in.')
        return None
    link = propwrite.new_link(answer['name'].strip(), path, sheet_name, headers[key_index], kind,
                              answer['columns'], answer['tab'].strip())
    link['id'] = next_link_id(links)
    toast.success('Link saved', '%s: %s to %s' % (link['name'], os.path.basename(path), link['tab']))
    return link


def refresh_links(doc, links):
    """Refreshes each link (re-read, re-match, rewrite its tab) and toasts a summary."""
    from namo import items, progress
    toast = _toast()
    item_list = scoped_items(doc, 'model', 'objects', 'Refresh data links')
    if item_list is None:
        return
    reader = propindex.Reader(doc)
    done = []
    from pynavis import viewpoints
    # Refresh all is one user action: every link's rewrite lands in ONE undo step
    # (write_tabs' own transaction is skipped while this one is open).
    with viewpoints.transaction('Refresh data links', doc):
        for link in links:
            path = link.get('source')
            if not path or not os.path.exists(path):
                toast.warning('Source file missing', '%s: %s' % (link.get('name'), path))
                continue
            try:
                rows = propwrite.read_table(path, link.get('sheet') or None)
            except Exception as error:
                toast.error('Could not read %s' % os.path.basename(path), str(error))
                continue
            headers, data = propwrite.headers_of(rows)
            if link.get('key_column') not in headers:
                toast.error('Key column missing', '%s has no column %s any more.' % (os.path.basename(path),
                                                                                    link.get('key_column')))
                continue
            kind = propwrite.link_key_kind(link)
            key_index = headers.index(link['key_column'])
            index = progress.run('Refresh %s' % link.get('name'), lambda report: propwrite.key_index(
                item_list, kind, reader, tick=data_common.stage(report, 0.0, 1.0, 'Reading keys: %s')))
            if index is progress.CANCELLED:
                return
            plan = propwrite.plan_rows(headers, data, key_index, kind, link.get('columns') or [])
            matching = propwrite.match_rows(plan['rows'], index)
            targets = plan_from_matching(matching, link['tab'])
            result = write(targets, doc, 'Refresh data link', replace=True) if targets else \
                {'written': 0, 'unchanged': 0, 'errors': []}
            if result.get('stopped'):
                toast.warning('Refresh stopped', '%s: %s objects written before you stopped it.' % (
                    link.get('name'), '{:,}'.format(result['written'])))
                return
            row_keys = set(entry['key'] for entry in plan['rows'])
            orphans = []
            for key, found in index.items():
                if key not in row_keys:
                    orphans.extend(found)
            orphans = items.dedupe(orphans)
            try:
                link['unmatched_items'] = items.entries(orphans[:UNMATCHED_STORED])
            except Exception:
                link['unmatched_items'] = []
            link['stats'] = {'matched': len(matching['matched']), 'unmatched': len(matching['unmatched']),
                             'changed': result['written'], 'objects_without_row': len(orphans),
                             'errors': len(result['errors'])}
            link['last_refresh'] = time.strftime('%Y-%m-%d %H:%M')
            link['file_mtime'] = _mtime(path)
            done.append(link)
    if not done:
        return
    matched = sum(l['stats']['matched'] for l in done)
    unmatched = sum(l['stats']['unmatched'] for l in done)
    changed = sum(l['stats']['changed'] for l in done)
    level = 'warning' if unmatched or any(l['stats']['errors'] for l in done) else 'success'
    toast.show(level, 'Refreshed %d %s' % (len(done), 'link' if len(done) == 1 else 'links'),
               '%s rows matched, %s unmatched, %s objects changed.' % ('{:,}'.format(matched),
                                                                       '{:,}'.format(unmatched),
                                                                       '{:,}'.format(changed)))


def remove_links(doc, links):
    """Removes links (optionally stripping their tabs); None when cancelled."""
    from pynavis import forms
    from namo import progress
    toast = _toast()
    names = ', '.join(l.get('name') or '' for l in links)
    options = ['Remove and strip the tab', 'Remove, keep the tab']
    choice = forms.ask_options('Remove %s? Stripping deletes the link\'s tab from every object that has it.' % names,
                               options, title='External Data Link')
    if choice is None:
        return None
    stripped = 0
    if choice == options[0]:
        item_list = scoped_items(doc, 'model', 'objects', 'Remove data links')
        if item_list is None:
            return None
        tabs = set(l.get('tab') for l in links if l.get('tab'))

        def work(report):
            tick = data_common.stage(report, 0.0, 1.0, 'Finding tabs: %s')
            from namo import items
            ticker = items.Ticker(tick, total=len(item_list), every=500)
            carriers = {}
            for item in item_list:
                for tab in tabs:
                    if propwrite.custom_tab(item, tab) is not None:
                        carriers.setdefault(tab, []).append(item)
                ticker.step()
            ticker.finish()
            return carriers
        carriers = progress.run('Remove data links', work)
        if carriers is progress.CANCELLED:
            return None
        from pynavis import viewpoints
        with viewpoints.transaction('Remove data links', doc):   # one undo step for every tab
            for tab in sorted(carriers):
                removed, _errors = propwrite.remove_tab(carriers[tab], tab, doc)
                stripped += removed
    toast.success('Removed %d %s' % (len(links), 'link' if len(links) == 1 else 'links'),
                  ('Tabs stripped from %s objects.' % '{:,}'.format(stripped)) if choice == options[0]
                  else 'Their tabs stay on the objects.')
    return len(links)


def select_unmatched(doc, link):
    from namo import items
    toast = _toast()
    entries = link.get('unmatched_items') or []
    if not link.get('last_refresh'):
        toast.info('Refresh the link first', 'Unmatched objects are found when the link is refreshed.')
        return
    if not entries:
        toast.success('Every keyed object has a row', '%s matched every object that carries a key.' % link.get('name'))
        return
    found, missing = items.resolve(entries, doc)
    if not found:
        toast.info('Those objects are gone', 'Refresh the link to find unmatched objects again.')
        return
    items.select(found)
    detail = 'Objects with a key but no row in %s.' % os.path.basename(link.get('source') or '')
    if missing:
        detail += ' %s no longer in the model.' % '{:,}'.format(missing)
    total = (link.get('stats') or {}).get('objects_without_row', len(found))
    if total > len(found) + (missing or 0):
        detail += ' The first %s are listed.' % '{:,}'.format(UNMATCHED_STORED)
    toast.success('Selected %s unmatched %s' % ('{:,}'.format(len(found)), 'object' if len(found) == 1 else 'objects'),
                  detail)

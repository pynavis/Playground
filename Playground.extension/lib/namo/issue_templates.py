# -*- coding: utf-8 -*-
"""Issue templates: what a new RFI, Hold, Verify, Safety or Clash issue starts with.

A template is a namo.templates entry of the tool 'issue_templates' (shared with the
team whenever a shared folder is set):

    {'type': 'RFI', 'prefix': 'RFI-', 'title_pattern': '{type} {n:000}',
     'priority': 'Normal', 'trade': '', 'assignee': '', 'due_days': 7,
     'description': 'Request for information: ', 'labels': ['RFI'], 'stamp_label': 'RFI'}

title_pattern tokens (namo.naming): {type}, {n} (the issue number, '{n:000}' pads it),
{date}, {user}, {project}, {file}, {trade}, {priority}, {level}, {grid}, {element},
{model}; Clash to Issues adds {test}, {clash}, {a}, {b}. trade '' means "from the
clicked object's model" for stamps and "from the clash rules" for clash issues.

DEFAULTS ship RFI, Hold, Verify, Safety, Clash and Design change. Until someone saves a
template the defaults are used as they are (nothing is written); the first edit writes
them all, so deleting one later really deletes it. Deleting every template brings the
defaults back.

Pure half (normalise, validate, resolve against a list) first; the store and the
editor window follow.
"""

import copy
import re

TOOL = 'issue_templates'
PRIORITIES = ['Low', 'Normal', 'High', 'Critical']

DEFAULTS = [
    {'type': 'RFI', 'prefix': 'RFI-', 'title_pattern': '{type} {n:000}', 'priority': 'Normal',
     'trade': '', 'assignee': '', 'due_days': 7,
     'description': 'Request for information: ', 'labels': ['RFI'], 'stamp_label': 'RFI'},
    {'type': 'Hold', 'prefix': 'HOLD-', 'title_pattern': '{type} {n:000}', 'priority': 'High',
     'trade': '', 'assignee': '', 'due_days': 3,
     'description': 'Hold: do not proceed with work here until this is released.',
     'labels': ['Hold'], 'stamp_label': 'Hold'},
    {'type': 'Verify', 'prefix': 'VER-', 'title_pattern': '{type} {n:000}', 'priority': 'Normal',
     'trade': '', 'assignee': '', 'due_days': 7,
     'description': 'Verify on site or in the authoring model: ', 'labels': ['Verify'],
     'stamp_label': 'Verify'},
    {'type': 'Safety', 'prefix': 'SAF-', 'title_pattern': '{type} {n:000}',
     'priority': 'Critical', 'trade': '', 'assignee': '', 'due_days': 1,
     'description': 'Safety concern: ', 'labels': ['Safety'], 'stamp_label': 'Safety'},
    {'type': 'Clash', 'prefix': 'CLA-', 'title_pattern': '{clash}: {a} vs {b}',
     'priority': 'Normal', 'trade': '', 'assignee': '', 'due_days': 14,
     'description': '', 'labels': ['Clash'], 'stamp_label': 'Clash'},
    {'type': 'Design change', 'prefix': 'DC-', 'title_pattern': '{type} {n:000}',
     'priority': 'Normal', 'trade': '', 'assignee': '', 'due_days': 14,
     'description': 'Design change: ', 'labels': ['Design change'],
     'stamp_label': 'Design change'},
]

FIELDS = ('type', 'prefix', 'title_pattern', 'priority', 'trade', 'assignee', 'due_days',
          'description', 'labels', 'stamp_label')


# ---- pure ---------------------------------------------------------------------------------


def _text(value):
    return '' if value is None else (u'%s' % (value,)).strip()


def _prefix(text, type_name):
    from namo import issues
    cleaned = issues.clean_prefix(text)
    if cleaned:
        return cleaned
    letters = re.sub(r'[^A-Za-z]', '', type_name or '').upper()[:4]
    return issues.clean_prefix(letters) or issues.DEFAULT_PREFIX


def normalise(template):
    """A complete template dict (a copy) from any stored config; junk becomes defaults."""
    from namo import issues
    t = dict(template or {})
    type_name = _text(t.get('type')) or 'Issue'
    try:
        due = t.get('due_days')
        due = None if due in (None, '') else max(0, int(float(due)))
    except (TypeError, ValueError):
        due = None
    labels = t.get('labels')
    if not isinstance(labels, (list, tuple)):
        labels = issues.labels_from_text(labels)
    return {
        'type': type_name,
        'prefix': _prefix(t.get('prefix'), type_name),
        'title_pattern': _text(t.get('title_pattern')) or '{type} {n:000}',
        'priority': issues.canonical_priority(t.get('priority')),
        'trade': _text(t.get('trade')),
        'assignee': _text(t.get('assignee')),
        'due_days': due,
        'description': u'%s' % (t.get('description') or ''),
        'labels': [_text(l) for l in labels if _text(l)],
        'stamp_label': _text(t.get('stamp_label')) or type_name,
    }


def validate(template, others=()):
    """[sentence]: problems that stop a save. others: the OTHER templates (for the
    unique type and prefix rules)."""
    t = normalise(template)
    out = []
    if not _text((template or {}).get('type')):
        out.append('Give the template a type, for example RFI.')
    for other in others:
        o = normalise(other)
        if o['type'].lower() == t['type'].lower():
            out.append('There is already a template called %s.' % o['type'])
        elif o['prefix'] == t['prefix']:
            out.append('%s already uses the prefix %s; numbers would be shared.'
                       % (o['type'], t['prefix']))
    from namo import naming
    unknown = [n for n in naming.tokens(t['title_pattern']) if n.lower() not in TOKENS]
    if unknown:
        out.append('The title pattern uses unknown tokens: %s.' % ', '.join(unknown))
    return out


TOKENS = ('type', 'n', 'date', 'time', 'datetime', 'year', 'month', 'day', 'user', 'project',
          'project_number', 'company', 'file', 'title', 'trade', 'priority', 'level', 'grid',
          'element', 'model', 'test', 'clash', 'a', 'b')


def find(templates, name):
    """The template (normalised) whose type or stamp label is name (any case), else None."""
    wanted = _text(name).lower()
    if not wanted:
        return None
    for template in templates:
        t = normalise(template)
        if t['type'].lower() == wanted:
            return t
    for template in templates:
        t = normalise(template)
        if t['stamp_label'].lower() == wanted:
            return t
    return None


def default(name):
    """The shipped default template for a type name (normalised), or None."""
    return find(DEFAULTS, name)


def days_text(days):
    """'1 day' / '7 days'."""
    return '%d day%s' % (days, '' if days == 1 else 's')


def rows(templates):
    """Table rows for the editor: [{'value': type, 'cells': [...]}]."""
    out = []
    for template in templates:
        t = normalise(template)
        due = '' if t['due_days'] is None else days_text(t['due_days'])
        out.append({'value': t['type'], 'cells': [t['type'], t['prefix'], t['priority'],
                                                  t['trade'] or 'From model', due,
                                                  t['title_pattern']]})
    return out


# ---- store --------------------------------------------------------------------------------


def _store():
    from namo import templates
    return templates.Templates(TOOL)


def saved():
    """The saved templates (normalised), natural order of type. [] when none saved."""
    from namo import naming
    try:
        s = _store()
        out = [normalise(s.get(name)) for name in s.names()]
    except Exception:
        return []
    return sorted([t for t in out if t], key=lambda t: naming.natural_key(t['type']))


def load():
    """The templates in use: the saved ones, or the shipped defaults when none are saved."""
    found = saved()
    return found if found else [normalise(t) for t in DEFAULTS]


def resolve(name):
    """The template for a type name: saved, else shipped default. None when neither."""
    return find(load(), name) or default(name)


def materialise():
    """Writes the shipped defaults when nothing is saved yet (before the first edit)."""
    if saved():
        return 0
    s = _store()
    for template in DEFAULTS:
        t = normalise(template)
        s.save(t['type'], t)
    return len(DEFAULTS)


def save(template, old_type=None):
    """Saves a template (renaming from old_type when given). Returns the stored type."""
    t = normalise(template)
    materialise()
    s = _store()
    if old_type and _text(old_type).lower() != t['type'].lower():
        s.delete(old_type)
    return s.save(t['type'], t)


def delete(type_name):
    materialise()
    return _store().delete(type_name)


def export(path, names=None):
    materialise()
    return _store().export(path, names)


def import_file(path, replace=False):
    materialise()
    return _store().import_file(path, replace)


# ---- editor (WPF; namo.ui) ------------------------------------------------------------------

COLUMNS = ['Type', 'Prefix', 'Priority', 'Trade', 'Due', 'Title pattern']


def form_fields(template, trades):
    """ui.form fields for one template (pure)."""
    t = normalise(template)
    trade_options = [('From the model or clash rules', '')] + [(x, x) for x in trades]
    if t['trade'] and t['trade'] not in trades:
        trade_options.append((t['trade'], t['trade']))
    return [
        {'kind': 'text', 'key': 'type', 'label': 'Type', 'default': t['type'], 'required': True,
         'hint': 'Shown on issues and as the BCF topic type, for example RFI.'},
        {'kind': 'text', 'key': 'prefix', 'label': 'Number prefix', 'default': t['prefix'],
         'hint': 'Issues are numbered per prefix: RFI-001, RFI-002...'},
        {'kind': 'text', 'key': 'title_pattern', 'label': 'Title pattern',
         'default': t['title_pattern'],
         'hint': 'Tokens: {type} {n:000} {date} {trade} {level} {grid} {element} {model} {user}.'},
        {'kind': 'choice', 'key': 'priority', 'label': 'Priority', 'options': PRIORITIES,
         'default': t['priority'], 'fallback': None},
        {'kind': 'choice', 'key': 'trade', 'label': 'Trade', 'options': trade_options,
         'default': t['trade'], 'fallback': None},
        {'kind': 'text', 'key': 'assignee', 'label': 'Assign to', 'default': t['assignee']},
        {'kind': 'int', 'key': 'due_days', 'label': 'Due after', 'suffix': 'days', 'min': 0,
         'max': 365, 'default': t['due_days'], 'hint': 'Blank for no due date.'},
        {'kind': 'textarea', 'key': 'description', 'label': 'Description', 'rows': 3,
         'default': t['description']},
        {'kind': 'text', 'key': 'labels', 'label': 'Labels', 'default': ', '.join(t['labels']),
         'hint': 'Separate with commas.'},
        {'kind': 'text', 'key': 'stamp_label', 'label': 'Stamp name', 'default': t['stamp_label'],
         'hint': 'The name Stamp from Template lists.'},
    ]


def edit_dialog(template, others, trades, title='Issue template'):
    """Asks for a template's fields. Returns the new template or None (cancelled)."""
    from namo import ui

    def check(values):
        problems = validate(values, others)
        return problems[0] if problems else None

    answers = ui.form(title, form_fields(template, trades), ok='Save', width=520,
                      validate=check)
    if answers is None:
        return None
    return normalise(answers)


def open_editor(trades=None):
    """The template manager (modal table window): New, Edit, Duplicate, Delete, Export,
    Import. Every change is saved at once."""
    from namo import config, ui
    from pynavis import forms, toast
    trades = trades if trades is not None else config.get('trades') or []
    holder = {}

    def refresh(status=None):
        win = holder.get('window')
        if win is not None:
            win.Tag.update(rows(load()), status)

    def others_than(type_name):
        return [t for t in load() if t['type'].lower() != _text(type_name).lower()]

    def do_new(selected):
        base = {'type': '', 'prefix': '', 'title_pattern': '{type} {n:000}', 'due_days': 7}
        result = edit_dialog(base, load(), trades, 'New issue template')
        if result is None:
            return
        save(result)
        refresh('Saved %s.' % result['type'])

    def do_edit(selected):
        if not selected:
            return
        current = resolve(selected[0])
        if current is None:
            return
        result = edit_dialog(current, others_than(current['type']), trades,
                             'Edit %s' % current['type'])
        if result is None:
            return
        save(result, old_type=current['type'])
        refresh('Saved %s.' % result['type'])

    def do_duplicate(selected):
        if not selected:
            return
        current = resolve(selected[0])
        if current is None:
            return
        copy_of = dict(current)
        copy_of['type'] = '%s copy' % current['type']
        copy_of['prefix'] = ''
        result = edit_dialog(copy_of, load(), trades, 'Duplicate %s' % current['type'])
        if result is None:
            return
        save(result)
        refresh('Saved %s.' % result['type'])

    def do_delete(selected):
        if not selected:
            return
        names = ', '.join(selected)
        if not forms.confirm('Delete the issue template%s %s? Issues already made from it '
                             'keep their type and numbers.' % ('s' if len(selected) > 1 else '',
                                                               names),
                             title='Delete templates'):
            return
        for name in selected:
            delete(name)
        refresh('Deleted %s.' % names)

    def do_export(selected):
        path = forms.save_file(filter='Playground templates (*.json)|*.json',
                               default_name='Issue templates.json', title='Export templates')
        if path is None:
            return
        count = export(path, selected or None)
        toast.success('Exported %d template%s' % (count, '' if count == 1 else 's'), path)

    def do_import(selected):
        path = forms.open_file(filter='Playground templates (*.json)|*.json',
                               title='Import templates')
        if path is None:
            return
        try:
            count = import_file(path)
        except ValueError as error:
            toast.error('Could not import templates', str(error))
            return
        refresh('Imported %d template%s.' % (count, '' if count == 1 else 's'))

    actions = [{'label': 'New', 'fn': do_new, 'needs_selection': False, 'primary': True},
               ('Edit', do_edit), ('Duplicate', do_duplicate), ('Delete', do_delete),
               {'label': 'Export', 'fn': do_export, 'needs_selection': False},
               {'label': 'Import', 'fn': do_import, 'needs_selection': False}]
    status = ('Shared with the team folder.' if _shared() else 'Saved on this computer.')
    win = ui.build_table('Issue templates', COLUMNS, rows(load()), actions=actions,
                         on_open=lambda value: do_edit([value]), status=status,
                         width=860, height=480)
    holder['window'] = win
    ui.show_modal(win)
    return win


def build_editor_window(trades=None):
    """The unshown editor window (smoke tests)."""
    from namo import ui
    return ui.build_table('Issue templates', COLUMNS, rows(load()),
                          actions=[{'label': 'New', 'fn': lambda s: None,
                                    'needs_selection': False, 'primary': True},
                                   ('Edit', lambda s: None), ('Delete', lambda s: None)],
                          status='Saved on this computer.', width=860, height=480)


def _shared():
    try:
        from namo import paths
        return paths.team_available()
    except Exception:
        return False


def copy_defaults():
    """A deep copy of the shipped defaults (normalised)."""
    return [normalise(copy.deepcopy(t)) for t in DEFAULTS]

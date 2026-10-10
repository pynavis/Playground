# -*- coding: utf-8 -*-
"""Search Set Wizard: a guided builder for Navisworks search sets.

One window, four steps: (1) where to search (whole model, chosen models, the current
selection), (2) conditions, AND within a set and optional OR sets, each row category /
property / native operator / value / ignore case, picked from a property sample with
observed values and counts, (3) count the matches, (4) name, folder, select now.

A Navisworks search set holds ONE list of AND conditions, so every OR set becomes its own
search set ('Name (set 2)'); the window says so. Values keep the kind observed on the
property (namo.find_query), so a numeric property is searched as a number.

The model is a plain dict (pure, unit tested):

    {'scope': 'model'|'models'|'selection', 'models': [file names], 'name', 'folder',
     'select_now': bool, 'groups': [[{'category', 'property', 'op', 'value',
     'ignore_case'}, ...], ...]}
"""

import time

from namo import find_query

SCOPES = [('model', 'Whole model'), ('models', 'Chosen models'), ('selection', 'Current selection')]
SCOPE_OPTIONS = [(label, value) for value, label in SCOPES]     # ui radio order: (label, value)
SAMPLE_SIZE = 600
DEFAULT_FOLDER = 'Playground'
EXPLAIN_OR = ('Every condition in a set must hold. Add an OR set to also match something else: '
              'each set becomes its own search set, because a Navisworks search set holds one '
              'list of conditions.')


# ---- pure half: the model ------------------------------------------------------------


def new_condition(category='', prop='', op='equals', value='', ignore_case=True):
    return {'category': category, 'property': prop, 'op': op, 'value': value,
            'ignore_case': bool(ignore_case)}


def new_model():
    return {'scope': 'model', 'models': [], 'name': '', 'folder': DEFAULT_FOLDER,
            'select_now': True, 'groups': [[new_condition()]]}


def normalise(model):
    """A clean copy of a (remembered) model: unknown scope falls back, empty groups go,
    at least one group with one row remains."""
    out = new_model()
    model = model or {}
    if model.get('scope') in [s for s, _l in SCOPES]:
        out['scope'] = model['scope']
    out['models'] = [str(m) for m in (model.get('models') or [])]
    out['name'] = str(model.get('name') or '')
    out['folder'] = str(model.get('folder') if model.get('folder') is not None else DEFAULT_FOLDER)
    out['select_now'] = bool(model.get('select_now', True))
    groups = []
    for group in model.get('groups') or []:
        rows = []
        for cond in group or []:
            op = cond.get('op') if cond.get('op') in find_query.OP_NEEDS_VALUE else 'equals'
            rows.append(new_condition(str(cond.get('category') or ''), str(cond.get('property') or ''),
                                      op, '' if cond.get('value') is None else str(cond.get('value')),
                                      cond.get('ignore_case', True)))
        if rows:
            groups.append(rows)
    out['groups'] = groups or [[new_condition()]]
    return out


def is_blank(cond):
    return not (cond.get('category') or cond.get('property') or str(cond.get('value') or '').strip())


def condition_problem(cond, kind='text'):
    """One sentence about what is wrong with a row, or None."""
    if not str(cond.get('category') or '').strip():
        return 'Choose a category.'
    if not str(cond.get('property') or '').strip():
        return 'Choose a property.'
    op = cond.get('op')
    if op not in find_query.OP_NEEDS_VALUE:
        return 'Choose an operator.'
    if not find_query.OP_NEEDS_VALUE[op]:
        return None
    value = str(cond.get('value') or '').strip()
    if not value:
        return 'Type a value.'
    if op in find_query.NUMERIC_OPS and find_query.parse_number(value) is None:
        return '%s needs a number.' % find_query.OP_LABELS[op].capitalize()
    if op in ('equals', 'not_equals') and kind in ('int', 'float', 'bool'):
        try:
            find_query.coerce(value, kind)
        except ValueError as error:
            return str(error)
    return None


def compile_group(group, kinds=None):
    """pynavis conditions for one OR set (blank rows skipped). Raises ValueError."""
    kinds = kinds or {}
    out = []
    for cond in group:
        if is_blank(cond):
            continue
        kind = kinds.get((cond['category'], cond['property']), 'text')
        problem = condition_problem(cond, kind)
        if problem:
            raise ValueError(problem)
        value = cond.get('value')
        if find_query.OP_NEEDS_VALUE[cond['op']]:
            value = str(value).strip()
            if cond['op'] in ('equals', 'not_equals'):
                value = find_query.coerce(value, kind)
        out.extend(find_query.conditions(cond['category'], cond['property'], cond['op'], value,
                                         kind=kind, ignore_case=cond.get('ignore_case', True)))
    return out


def problems(model, kinds=None):
    """[(group index, row index, sentence)]: everything that stops Create, in order.
    (row index None means the whole set or the model.)"""
    kinds = kinds or {}
    found = []
    filled = 0
    for g, group in enumerate(model['groups']):
        rows = [c for c in group if not is_blank(c)]
        if not rows:
            continue
        filled += 1
        for r, cond in enumerate(group):
            if is_blank(cond):
                continue
            problem = condition_problem(cond, kinds.get((cond['category'], cond['property']), 'text'))
            if problem:
                found.append((g, r, problem))
    if not filled:
        found.append((0, None, 'Add at least one condition.'))
    if model['scope'] == 'models' and not model['models']:
        found.append((None, None, 'Choose the models to search in.'))
    return found


def queries(model, kinds=None):
    """[query dict] one per OR set that has conditions. Raises ValueError (first
    problem) when the model is not ready."""
    issues = problems(model, kinds)
    if issues:
        raise ValueError(issues[0][2])
    out = []
    for group in model['groups']:
        conds = compile_group(group, kinds)
        if conds:
            out.append(find_query.query_dict([conds]))
    return out


def set_names(name, count):
    """The search set names for `count` OR sets."""
    name = (name or '').strip() or 'Search set'
    if count <= 1:
        return [name]
    return ['%s (set %d)' % (name, i + 1) for i in range(count)]


def default_name(model):
    """A name from the first set's first condition values: 'Ducts on Level 3'."""
    values = []
    for group in model['groups'][:1]:
        for cond in group:
            if cond.get('op') == 'equals' and str(cond.get('value') or '').strip():
                values.append(str(cond['value']).strip())
    if not values:
        return 'Search set'
    if len(values) == 1:
        return values[0]
    return '%s on %s' % (values[0], ', '.join(values[1:]))


def describe_group(group):
    texts = [find_query.describe(c['category'], c['property'], c['op'], c.get('value'))
             for c in group if not is_blank(c)]
    return ' and '.join(texts)


def count_text(counts, union, seconds):
    """'412 items match (1.3 s)' or, for several sets, 'Set 1: 12, set 2: 400; 412 in all
    (2.1 s)'."""
    if len(counts) == 1:
        return '%s %s (%.1f s)' % ('{:,}'.format(union), 'item matches' if union == 1 else 'items match',
                                   seconds)
    parts = ['set %d: %s' % (i + 1, '{:,}'.format(n)) for i, n in enumerate(counts)]
    text = '; '.join(parts)
    return '%s%s; %s in all (%.1f s)' % (text[0].upper(), text[1:], '{:,}'.format(union), seconds)


def query_key(query_list, model):
    """What a count depends on: the compiled queries and the scope (to know whether a
    count shown in the window still holds at Create)."""
    import json
    return json.dumps({'q': query_list, 'scope': model['scope'], 'models': sorted(model['models'])},
                      sort_keys=True)


class Sample(object):
    """Properties and values seen on a sample of elements (pure: built from rows of
    (category, property, value) per element)."""

    def __init__(self, elements_rows=(), sampled=False, total=0):
        self.values = {}            # (category, property) -> [value]
        self.carriers = {}          # (category, property) -> elements carrying it
        self.sampled = sampled
        self.total = total
        for rows in elements_rows:
            seen = set()
            for category, prop, value in rows:
                key = (category, prop)
                self.values.setdefault(key, []).append(value)
                if key not in seen:
                    seen.add(key)
                    self.carriers[key] = self.carriers.get(key, 0) + 1

    def categories(self):
        from namo import naming
        return sorted(set(k[0] for k in self.values), key=naming.natural_key)

    def properties(self, category):
        from namo import naming
        return sorted(set(k[1] for k in self.values if k[0] == category), key=naming.natural_key)

    def observed(self, category, prop, limit=80):
        """[(text, count)] most common first."""
        rows = find_query.tally_values(self.values.get((category, prop), []))
        return [(text, count) for text, count, _raw in rows if text != find_query.NO_VALUE][:limit]

    def kind(self, category, prop):
        return find_query.majority_kind(self.values.get((category, prop), []))

    def kinds(self):
        return dict((key, find_query.majority_kind(vals)) for key, vals in self.values.items())


# ---- API half -------------------------------------------------------------------------------


def _doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def build_sample(doc=None, size=SAMPLE_SIZE, report=None):
    """A Sample from elements of the selection (half) and the whole model (the rest)."""
    from namo import variants
    from namo import items
    document = _doc(doc)
    chosen = []
    selected = items.selected(document)
    if selected:
        chosen.extend(items.objects(selected, budget=size // 2))
    model_part = find_query.sample_objects(items.roots(document), size - len(chosen))
    chosen.extend(model_part)
    chosen = items.dedupe(chosen)
    rows = []
    for index, element in enumerate(chosen):
        try:
            rows.append([(r['category'], r['property'], r['value']) for r in variants.all_of(element)
                         if find_query.kind_of(r['value']) is not None])
        except Exception:
            continue
        if report is not None and index % 25 == 0:
            report(float(index) / max(1, len(chosen)), 'Reading properties of %d of %d elements' % (
                index, len(chosen)))
    return Sample(rows, sampled=getattr(model_part, 'sampled', False), total=len(chosen))


def scope_items(model, doc=None):
    """None (whole model), the chosen models' roots, or the selection."""
    from namo import items
    document = _doc(doc)
    if model['scope'] == 'selection':
        return items.selected(document)
    if model['scope'] == 'models':
        wanted = set(n.lower() for n in model['models'])
        return [m['root'] for m in items.models(document) if m['name'].lower() in wanted]
    return None


def count(model, kinds=None, doc=None):
    """([count per set], union count, seconds) for the model's queries."""
    from pynavis import sets
    document = _doc(doc)
    query_list = queries(model, kinds)
    scope = scope_items(model, document)
    started = time.time()
    counts = []
    seen = set()
    for query in query_list:
        found = sets.run(query, document, scope=scope)
        counts.append(found.Count)
        if len(query_list) > 1:
            for item in found:
                seen.add(item)
    total = len(seen) if len(query_list) > 1 else (counts[0] if counts else 0)
    return counts, total, time.time() - started


def matches(model, kinds=None, doc=None):
    """Every item the model's sets find (union over the OR sets), as one collection."""
    from pynavis import sets
    from namo import items
    document = _doc(doc)
    scope = scope_items(model, document)
    query_list = queries(model, kinds)
    if len(query_list) == 1:
        return sets.run(query_list[0], document, scope=scope)
    union = items.collection([])
    seen = set()
    for query in query_list:
        for item in sets.run(query, document, scope=scope):
            if item not in seen:
                seen.add(item)
                union.Add(item)
    return union


def folder_paths(doc=None):
    """Every selection-set folder as a path, for the folder box."""
    from namo import find_sets
    return find_sets.folder_paths(find_sets.snapshot(doc))


def create(model, kinds=None, doc=None):
    """Creates one search set per OR set in ONE undo step. Returns [final names]."""
    from pynavis import viewpoints
    from namo import find_sets
    document = _doc(doc)
    query_list = queries(model, kinds)
    names = set_names(model['name'], len(query_list))
    scope = scope_items(model, document)
    if scope is not None and not scope:
        raise ValueError('The search scope is empty: choose models or select items first.')
    folder = (model.get('folder') or '').strip() or None
    out = []
    with viewpoints.transaction('Search Set Wizard', document):
        for name, query in zip(names, query_list):
            _item, final = find_sets.create_set(name, query, folder, scope, document)
            out.append(final)
    return out


# ---- window -----------------------------------------------------------------------------------


class WizardState(object):
    """window.Tag of the wizard: `model` (live), `result` (the model, once Create was
    pressed with a valid model), `counted` ({'key', 'counts', 'union'} of the last count)."""

    def __init__(self, win, model, source):
        self.window = win
        self.model = model
        self.source = source
        self.result = None
        self.counted = None
        self.rows = []              # [(group index, row index, controls bag)]


def _combo(options, text='', editable=True, width=None):
    from namo import ui
    from System.Windows.Controls import ComboBox
    control = ComboBox()
    control.IsEditable = bool(editable)
    control.IsTextSearchEnabled = True
    for option in options:
        control.Items.Add(option)
    if editable:
        control.Text = text or ''
    if width:
        control.Width = float(width)
    control.Margin = ui._thickness(0, 0, 8, 0)
    return control


def _value_items(control, observed):
    """Fills a value combo with observed values: the item shows 'value  (count)', choosing
    it writes just the value (TextSearch.Text)."""
    from System.Windows.Controls import ComboBoxItem, TextSearch
    keep = control.Text
    control.Items.Clear()
    for text, count in observed:
        item = ComboBoxItem()
        item.Content = '%s  (%s)' % (text, '{:,}'.format(count))
        TextSearch.SetText(item, text)
        control.Items.Add(item)
    control.Text = keep


def build_window(model, source, models=(), folders=()):
    """The wizard window, unshown (window.Tag is a WizardState).

    source supplies the data: .categories(), .properties(cat), .observed(cat, prop),
    .kinds(), .count(model) -> (counts, union, seconds) (may raise ValueError with a
    sentence). models: appended file names; folders: existing set folders."""
    from namo import ui
    ui._wpf()
    from System.Windows import HorizontalAlignment, VerticalAlignment
    from System.Windows.Controls import (Dock, DockPanel, Orientation, StackPanel, WrapPanel)
    from System.Windows.Input import Key
    logger = ui.pinned_logger()
    colors = ui.palette()
    model = normalise(model)
    win = ui.window('Search Set Wizard', width=900, height=None, resizable=True, min_width=760)
    state = WizardState(win, model, source)
    win.Tag = state
    models = list(models)

    body = StackPanel()
    body.Margin = ui._thickness(24, 20, 24, 12)

    def step(number, title):
        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        row.Margin = ui._thickness(0, 0, 0, 8)
        badge = ui.text('%d' % number, size=13, bold=True, color=colors['muted'], wrap=False)
        badge.Margin = ui._thickness(0, 0, 10, 0)
        row.Children.Add(badge)
        row.Children.Add(ui.text(title, size=15, bold=True, wrap=False))
        body.Children.Add(row)

    # 1 scope
    step(1, 'Search in')
    scope_panel, scope_buttons = ui.radio_group(SCOPE_OPTIONS, model['scope'], inline=True,
                                                group='namo_wizard_scope')
    body.Children.Add(scope_panel)
    model_line = StackPanel()
    model_line.Orientation = Orientation.Horizontal
    model_line.Margin = ui._thickness(0, 4, 0, 24)
    model_note = ui.hint('')
    model_note.VerticalAlignment = VerticalAlignment.Center

    def model_text():
        chosen = [m for m in models if m.lower() in set(n.lower() for n in model['models'])]
        if model['scope'] != 'models':
            return ''
        if not chosen:
            return 'No models chosen yet'
        if len(chosen) <= 3:
            return ', '.join(chosen)
        return '%d of %d models' % (len(chosen), len(models))

    def choose_models():
        rows = [{'value': m, 'cells': [m]} for m in models]
        picked = ui.choose('Search in these models', rows, ['Model'], multiselect=True,
                           checked=[m for m in models if m.lower() in set(n.lower() for n in model['models'])],
                           width=480, height=460)
        if picked is not None:
            model['models'] = list(picked)
            if picked:
                set_scope('models')
            refresh_scope()
    choose_button = ui.button('Choose models', choose_models, 'secondary', logger)
    model_note.Margin = ui._thickness(12, 0, 0, 0)
    model_line.Children.Add(choose_button)
    model_line.Children.Add(model_note)
    body.Children.Add(model_line)

    def set_scope(value):
        for control, (_label, scope) in zip(scope_buttons, SCOPE_OPTIONS):
            control.IsChecked = scope == value

    def refresh_scope(*args):
        model['scope'] = ui.radio_value(scope_buttons, SCOPE_OPTIONS) or 'model'
        model_note.Text = model_text()
        invalidate()
    for control in scope_buttons:
        control.Checked += ui.safe(lambda s, e: refresh_scope(), 'wizard scope', logger)

    # 2 conditions
    step(2, 'Conditions')
    explain = ui.hint(EXPLAIN_OR)
    explain.Margin = ui._thickness(0, 0, 0, 12)
    body.Children.Add(explain)
    groups_panel = StackPanel()
    body.Children.Add(groups_panel)
    # read_rows first: rebuild() redraws every row from the model, so text typed into the
    # rows since the last read would otherwise be thrown away.
    add_group = ui.button('Add OR set', lambda: (read_rows(), model['groups'].append([new_condition()]),
                                                 rebuild()),
                          'quiet', logger)
    add_group.HorizontalAlignment = HorizontalAlignment.Left
    add_group.Margin = ui._thickness(0, 4, 0, 24)
    body.Children.Add(add_group)

    op_pairs = [(label, op) for op, label, _needs in find_query.NATIVE_OPS]

    def read_rows():
        for g, r, bag in state.rows:
            cond = model['groups'][g][r]
            cond['category'] = bag.category.Text.strip()
            cond['property'] = bag.prop.Text.strip()
            index = bag.op.SelectedIndex
            cond['op'] = op_pairs[index][1] if 0 <= index < len(op_pairs) else 'equals'
            cond['value'] = bag.value.Text
            cond['ignore_case'] = bool(bag.case.IsChecked)

    def condition_row(g, r, cond):
        from System.Windows.Controls import TextBlock
        line = StackPanel()
        line.Margin = ui._thickness(0, 0, 0, 8)
        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        category = _combo(source.categories(), cond['category'], width=170)
        prop = _combo(source.properties(cond['category']) if cond['category'] else [],
                      cond['property'], width=190)
        op = _combo([label for label, _op in op_pairs], editable=False, width=150)
        op.SelectedIndex = [o for _l, o in op_pairs].index(cond['op']) if cond['op'] in \
            [o for _l, o in op_pairs] else 0
        value = _combo([], cond.get('value') or '', width=210)
        if cond['category'] and cond['property']:
            _value_items(value, source.observed(cond['category'], cond['property']))
        case = ui.check('Ignore case', cond.get('ignore_case', True))
        case.VerticalAlignment = VerticalAlignment.Center
        case.Margin = ui._thickness(0, 0, 8, 0)
        remove = ui.button('Remove', lambda: remove_row(g, r), 'quiet', logger)
        for control in (category, prop, op, value, case, remove):
            row.Children.Add(control)
        error = TextBlock()
        error.FontSize = 12.0
        error.Foreground = ui.brush(colors['error'])
        error.Margin = ui._thickness(0, 4, 0, 0)
        error.Visibility = _collapsed()
        line.Children.Add(row)
        line.Children.Add(error)
        bag = ui._Bag(category=category, prop=prop, op=op, value=value, case=case, error=error)

        def category_changed(*args):
            text = category.Text.strip()
            keep = prop.Text
            prop.Items.Clear()
            for name in source.properties(text):
                prop.Items.Add(name)
            prop.Text = keep
            invalidate()

        def prop_changed(*args):
            if category.Text.strip() and prop.Text.strip():
                _value_items(value, source.observed(category.Text.strip(), prop.Text.strip()))
            invalidate()

        def op_changed(*args):
            index = op.SelectedIndex
            needs = find_query.OP_NEEDS_VALUE.get(op_pairs[index][1], True) if index >= 0 else True
            value.IsEnabled = needs
            case.IsEnabled = needs
            invalidate()
        category.LostKeyboardFocus += ui.safe(category_changed, 'wizard category', logger)
        category.SelectionChanged += ui.safe(lambda s, e: ui.run_later(category_changed),
                                             'wizard category', logger)
        prop.LostKeyboardFocus += ui.safe(prop_changed, 'wizard property', logger)
        prop.SelectionChanged += ui.safe(lambda s, e: ui.run_later(prop_changed), 'wizard property',
                                         logger)
        op.SelectionChanged += ui.safe(op_changed, 'wizard operator', logger)
        value.LostKeyboardFocus += ui.safe(lambda s, e: invalidate(), 'wizard value', logger)
        op_changed()
        return line, bag

    def remove_row(g, r):
        read_rows()
        group = model['groups'][g]
        del group[r]
        if not group:
            del model['groups'][g]
        if not model['groups']:
            model['groups'].append([new_condition()])
        rebuild()

    def add_row(g):
        read_rows()
        model['groups'][g].append(new_condition())
        rebuild()

    def rebuild():
        groups_panel.Children.Clear()
        state.rows = []
        for g, group in enumerate(model['groups']):
            inner = StackPanel()
            inner.Margin = ui._thickness(12, 12, 12, 4)
            for r, cond in enumerate(group):
                line, bag = condition_row(g, r, cond)
                inner.Children.Add(line)
                state.rows.append((g, r, bag))
            add = ui.button('Add condition', (lambda index: lambda: add_row(index))(g), 'quiet', logger)
            add.HorizontalAlignment = HorizontalAlignment.Left
            inner.Children.Add(add)
            frame = ui.group('Set %d' % (g + 1) if len(model['groups']) > 1 else 'Conditions', inner)
            frame.Margin = ui._thickness(0, 0, 0, 12)
            groups_panel.Children.Add(frame)
        invalidate()

    # 3 count
    step(3, 'Count the matches')
    count_line = StackPanel()
    count_line.Orientation = Orientation.Horizontal
    count_line.Margin = ui._thickness(0, 0, 0, 24)
    count_result = ui.text('', wrap=False)
    count_result.VerticalAlignment = VerticalAlignment.Center
    count_result.Margin = ui._thickness(12, 0, 0, 0)

    def do_count():
        read_rows()
        if not show_problems():
            return
        try:
            query_list = queries(model, source.kinds())
            counts, union, seconds = source.count(model)
        except ValueError as error:
            count_result.Text = str(error)
            return
        state.counted = {'key': query_key(query_list, model), 'counts': counts, 'union': union}
        count_result.Text = count_text(counts, union, seconds)
    count_line.Children.Add(ui.button('Count matches', do_count, 'secondary', logger))
    count_line.Children.Add(count_result)
    body.Children.Add(count_line)

    def invalidate(*args):
        if state.counted is not None:
            state.counted = None
            count_result.Text = 'Conditions changed: count again to see the matches.'

    # 4 save
    step(4, 'Save')
    save_row = WrapPanel()
    name_label = ui.text('Name', wrap=False)
    name_label.VerticalAlignment = VerticalAlignment.Center
    name_label.Margin = ui._thickness(0, 0, 8, 0)
    name_shell, name_box = ui.text_box(model['name'], placeholder='Named from the values when blank')
    name_shell.Width = 320.0
    folder_label = ui.text('Folder', wrap=False)
    folder_label.VerticalAlignment = VerticalAlignment.Center
    folder_label.Margin = ui._thickness(24, 0, 8, 0)
    folder = _combo(list(folders), model['folder'], width=260)
    for control in (name_label, name_shell, folder_label, folder):
        save_row.Children.Add(control)
    body.Children.Add(save_row)
    select_now = ui.check('Select the matches when the set is created', model['select_now'])
    select_now.Margin = ui._thickness(0, 12, 0, 0)
    body.Children.Add(select_now)
    problem_line = ui.text('', color=colors['error'])
    problem_line.Margin = ui._thickness(0, 12, 0, 0)
    body.Children.Add(problem_line)

    def show_problems():
        kinds = source.kinds()
        found = problems(model, kinds)
        by_row = dict(((g, r), text) for g, r, text in found if r is not None)
        for g, r, bag in state.rows:
            text = by_row.get((g, r))
            bag.error.Text = text or ''
            bag.error.Visibility = _visible() if text else _collapsed()
        general = [text for g, r, text in found if r is None]
        problem_line.Text = general[0] if general else ''
        return not found

    def accept():
        read_rows()
        model['name'] = name_box.Text.strip() or default_name(model)
        model['folder'] = folder.Text.strip()
        model['select_now'] = bool(select_now.IsChecked)
        if not show_problems():
            return
        state.result = model
        ui._close_with(win, True)

    create = ui.button('Create', accept, 'primary', logger)
    create.IsDefault = False
    cancel = ui.button('Cancel', lambda: ui._close_with(win, False), 'secondary', logger)
    cancel.IsCancel = True
    note = ui.hint('Sampled %s elements for the lists' % '{:,}'.format(getattr(source, 'total', 0))
                   if getattr(source, 'total', 0) else '')
    bottom = ui.footer([create, cancel], left=note)

    layout = DockPanel()
    DockPanel.SetDock(bottom, Dock.Bottom)
    layout.Children.Add(bottom)
    area = ui.work_area()
    layout.Children.Add(ui.scroll(body, max_height=(area[3] - area[1]) * 0.75))
    win.Content = layout

    def keys(sender, args):
        if args.Key == Key.Escape:
            ui._close_with(win, False)
            args.Handled = True
    win.PreviewKeyDown += ui.safe(keys, 'wizard keys', logger)
    rebuild()
    refresh_scope()
    state.count = do_count
    state.accept = accept
    state.read_rows = read_rows
    state.rebuild = rebuild
    state.add_row = add_row
    state.remove_row = remove_row
    state.name_box = name_box
    state.folder_box = folder
    return win


def _collapsed():
    from System.Windows import Visibility
    return Visibility.Collapsed


def _visible():
    from System.Windows import Visibility
    return Visibility.Visible


def dialog(model, source, models=(), folders=()):
    """Shows the wizard; returns (model, counted) or None when cancelled."""
    from namo import ui
    win = build_window(model, source, models, folders)
    ui.show_modal(win)
    state = win.Tag
    if state.result is None:
        return None
    return state.result, state.counted


class LiveSource(object):
    """The wizard's data from the open document: a property Sample plus counting."""

    def __init__(self, sample, doc=None):
        self.sample = sample
        self.doc = doc
        self.total = sample.total

    def categories(self):
        return self.sample.categories()

    def properties(self, category):
        return self.sample.properties(category)

    def observed(self, category, prop):
        return self.sample.observed(category, prop)

    def kinds(self):
        return self.sample.kinds()

    def count(self, model):
        return count(model, self.sample.kinds(), self.doc)

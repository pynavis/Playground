# -*- coding: utf-8 -*-
"""Clash Namer: rename clash results and result groups from a name template.

Tokens for clashes (namo.naming syntax, so {n:000} pads and {distance:>8} formats):

    {test} {n} {name} {grid} {level} {model_a} {model_b} {trade_a} {trade_b}
    {cat_a} {cat_b} {item_a} {item_b} {status} {distance} {group} {assigned}
    plus {date} {user} {project} {file} ...      (namo.naming.standard_values)

Groups have the same tokens computed over their clashes (the most common grid, level,
models, trades and status; the deepest {distance}) plus {count}. {n} counts clashes,
or groups, within each test in Clash Detective's order. {distance} is in document units
(negative = penetration, as Clash Detective shows it).

Writing, in ONE undo step:
  * up to `threshold` renames (config, default 200): DocumentClashTests
    .TestsEditDisplayName per item inside one transaction. The default is low on
    purpose: pyNavis measured every document-side clash edit at a fixed cost that grows
    with the model (~170 ms each on a 350,000-clash file), so thousands of them freeze
    Navisworks for minutes;
  * above it: each test is rebuilt once on a detached copy with the new names and
    swapped in with TestsReplaceWithCopy, the shipped Clash Grouper's route
    (namo.clashset_edit: CreateCopy, Children.Clear, Children.Add of copies; untouched
    groups copied whole, so nesting, comments and statuses survive). The old test
    wrappers are dead after the swap, so everything needed is read first.

Pure planning first (unit tested); the API half and the preview window after.
"""

from namo import clashset_edit
from namo import clashset_tests as defs
from namo.clashset_common import close_window
from namo.clashset_common import thickness as _thickness
from namo import naming

CLASH_TOKENS = ['test', 'n', 'name', 'grid', 'level', 'model_a', 'model_b', 'trade_a', 'trade_b',
                'cat_a', 'cat_b', 'item_a', 'item_b', 'status', 'distance', 'group', 'assigned']
GROUP_TOKENS = ['test', 'n', 'name', 'count', 'grid', 'level', 'model_a', 'model_b', 'trade_a',
                'trade_b', 'status', 'distance']
CATEGORY_TOKENS = ('cat_a', 'cat_b')
DEFAULT_CLASH = '{test} {n:000}'
DEFAULT_GROUP = '{test} G{n:00} {grid}'
SCOPES = [('Clashes', 'clashes'), ('Groups', 'groups'), ('Clashes and groups', 'both')]   # (label, value)
DEFAULT_THRESHOLD = clashset_edit.EDIT_LIMIT
OLD_DEFAULT_THRESHOLD = 3000      # the first build's default; a saved 3,000 is not a choice
PREVIEW_ROWS = 25
MAX_NAME = 250
TOKEN_HINT = ('Tokens: {test} {n:000} {grid} {level} {model_a} {model_b} {trade_a} {trade_b} '
              '{cat_a} {cat_b} {item_a} {item_b} {status} {distance} {name} {group}. '
              'Groups also have {count}.')


# ---- pure ---------------------------------------------------------------------------------


def tidy(text):
    """A finished name: namo.naming.sanitize (spaces collapsed, no control characters)
    and at most MAX_NAME characters."""
    return naming.sanitize(text)[:MAX_NAME].strip()


def dominant(values):
    """The most common non-empty value (ties: natural order), or ''."""
    counts = {}
    for value in values:
        text = '' if value is None else str(value).strip()
        if text:
            counts[text] = counts.get(text, 0) + 1
    if not counts:
        return ''
    return sorted(counts, key=lambda v: (-counts[v], naming.natural_key(v), v))[0]


def clash_values(row, doc_units, categories=None):
    """Token values for one clash row (namo.clashdata snapshot row). categories:
    (cat_a, cat_b) or None."""
    cat_a, cat_b = categories if categories else ('', '')
    return {
        'test': row.get('test') or '', 'name': row.get('name') or '',
        'grid': row.get('grid') or '', 'level': row.get('level') or '',
        'model_a': row.get('model_a') or '', 'model_b': row.get('model_b') or '',
        'trade_a': row.get('trade_a') or '', 'trade_b': row.get('trade_b') or '',
        'cat_a': cat_a or '', 'cat_b': cat_b or '',
        'item_a': row.get('item_a_name') or '', 'item_b': row.get('item_b_name') or '',
        'status': row.get('status') or '', 'group': row.get('group') or '',
        'assigned': row.get('assigned') or '',
        'distance': defs.length_text(row.get('distance'), doc_units),
    }


def group_values(name, rows, doc_units, test_name=''):
    """Token values for a group from its clash rows."""
    distances = [r.get('distance') for r in rows if r.get('distance') is not None]
    return {
        'test': test_name, 'name': name or '', 'count': len(rows),
        'grid': dominant(r.get('grid') for r in rows),
        'level': dominant(r.get('level') for r in rows),
        'model_a': dominant(r.get('model_a') for r in rows),
        'model_b': dominant(r.get('model_b') for r in rows),
        'trade_a': dominant(r.get('trade_a') for r in rows),
        'trade_b': dominant(r.get('trade_b') for r in rows),
        'status': dominant(r.get('status') for r in rows),
        'distance': defs.length_text(min(distances), doc_units) if distances else '',
    }


def needs_categories(*templates):
    """True when a template uses {cat_a} or {cat_b} (reading categories costs a
    property read per element, so only then)."""
    for template in templates:
        for token in naming.tokens(template or ''):
            if token.lower() in CATEGORY_TOKENS:
                return True
    return False


def unknown_tokens(template, allowed):
    """Tokens in a template that are neither allowed nor standard name tokens."""
    standard = set(['date', 'time', 'datetime', 'year', 'month', 'day', 'user', 'project',
                    'project_number', 'company', 'file', 'title'])
    allowed_lower = set(a.lower() for a in allowed) | standard
    return [t for t in naming.tokens(template or '') if t.lower() not in allowed_lower]


def plan_test(test_name, rows, groups, clash_template, group_template, scope, doc_units,
              category_of=None, standard=None, limit=None):
    """Renames for one test: {'clashes': [(row id, old, new)], 'groups': [(group id, old,
    new)], 'unchanged': n, 'considered': n}. Only names that change are listed.

    rows: snapshot rows (row['id'] is the leaf index); groups: [{'gid', 'name', 'ids'}]
    in tree order (every group at any depth, ids = leaves beneath it). category_of(row)
    -> (cat_a, cat_b) when the clash template needs categories. limit stops after that
    many renames (the preview)."""
    out = {'clashes': [], 'groups': [], 'unchanged': 0, 'considered': 0}
    base = dict(standard or {})
    use_cats = category_of is not None and needs_categories(clash_template)

    def full():
        return limit is not None and len(out['clashes']) + len(out['groups']) >= limit

    if scope in ('clashes', 'both') and clash_template:
        for n, row in enumerate(rows):
            if full():
                return out
            values = dict(base)
            values.update(clash_values(row, doc_units, category_of(row) if use_cats else None))
            values['test'] = test_name
            text, _missing = naming.render(clash_template, values, counter=n + 1)
            new = tidy(text)
            out['considered'] += 1
            if not new or new == row.get('name'):
                out['unchanged'] += 1
                continue
            out['clashes'].append((row['id'], row.get('name') or '', new))
    if scope in ('groups', 'both') and group_template:
        by_id = dict((row['id'], row) for row in rows)
        for n, group in enumerate(groups):
            if full():
                return out
            members = [by_id[i] for i in group['ids'] if i in by_id]
            values = dict(base)
            values.update(group_values(group['name'], members, doc_units, test_name))
            text, _missing = naming.render(group_template, values, counter=n + 1)
            new = tidy(text)
            out['considered'] += 1
            if not new or new == group['name']:
                out['unchanged'] += 1
                continue
            out['groups'].append((group['gid'], group['name'] or '', new))
    return out


def preview_rows(plans, limit=PREVIEW_ROWS):
    """Table rows [test, kind, before, after] for the first `limit` renames of
    [(test name, plan)]."""
    out = []
    for test_name, plan in plans:
        for _gid, old, new in plan['groups']:
            out.append([test_name, 'Group', old, new])
        for _rid, old, new in plan['clashes']:
            out.append([test_name, 'Clash', old, new])
    return out[:limit]


def _counted(count, singular, plural):
    return '{:,} {}'.format(count, singular if count == 1 else plural)


def summary_text(counts, test_count):
    """'Renames 1,240 clashes and 35 groups in 3 tests' (the window's status line)."""
    parts = []
    if counts.get('clashes'):
        parts.append(_counted(counts['clashes'], 'clash', 'clashes'))
    if counts.get('groups'):
        parts.append(_counted(counts['groups'], 'group', 'groups'))
    return 'Renames %s in %s' % (' and '.join(parts), _counted(test_count, 'test', 'tests'))


FULL_PREVIEW = 5000           # names planned in full on every keystroke (counts exact)
FULL_PREVIEW_CATEGORIES = 1000


def threshold_of(values):
    """The one-by-one limit from saved settings: a positive whole number, else the
    default. The first build saved 3,000 as its default, which is minutes of frozen
    Navisworks on a big model, so that exact value falls back to the default too."""
    try:
        value = int((values or {}).get('threshold') or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0 or value == OLD_DEFAULT_THRESHOLD:
        return DEFAULT_THRESHOLD
    return value


def preview(entries, clash_template, group_template, scope, doc_units, category_readers=None,
            standard=None):
    """(table rows, status sentence, ok) for the window. entries: read_test dicts (only
    'name', 'rows' and 'specs' are used); category_readers: one category_of per entry
    or None. Counts are exact up to FULL_PREVIEW names, else the first rows are shown."""
    clash_template = clash_template or ''
    group_template = group_template or ''
    use_clashes = scope in ('clashes', 'both')
    use_groups = scope in ('groups', 'both')
    bad = []
    if use_clashes:
        if not clash_template.strip():
            return [], 'Enter a name template for clashes.', False
        bad.extend(unknown_tokens(clash_template, CLASH_TOKENS))
    if use_groups:
        if not group_template.strip():
            return [], 'Enter a name template for groups.', False
        bad.extend(unknown_tokens(group_template, GROUP_TOKENS))
    if bad:
        return [], '{%s} is not a token; use the ones listed above.' % bad[0], False
    clash_total = sum(len(e['rows']) for e in entries) if use_clashes else 0
    group_total = sum(len(e['specs']) for e in entries) if use_groups else 0
    if not clash_total and not group_total:
        return [], ('These tests have no result groups.' if use_groups and not use_clashes
                    else 'These tests have no clash results.'), False
    limit = FULL_PREVIEW_CATEGORIES if use_clashes and needs_categories(clash_template) else FULL_PREVIEW
    full = clash_total + group_total <= limit
    plans = []
    for index, entry in enumerate(entries):
        reader = category_readers[index] if category_readers else None
        plans.append((entry['name'], plan_test(entry['name'], entry['rows'], entry['specs'],
                                               clash_template, group_template, scope, doc_units,
                                               reader, standard,
                                               None if full else PREVIEW_ROWS)))
    rows = preview_rows(plans)
    if not full:
        return rows, ('Showing the first {:,} of {:,} names; names that already match are '
                      'left alone.'.format(len(rows), clash_total + group_total)), True
    counts = {'clashes': sum(len(p['clashes']) for _n, p in plans),
              'groups': sum(len(p['groups']) for _n, p in plans)}
    if not counts['clashes'] and not counts['groups']:
        return rows, 'Every name already matches this template.', False
    tests = sum(1 for _n, p in plans if p['clashes'] or p['groups'])
    return rows, summary_text(counts, tests), True


def plan_all(entries, clash_template, group_template, scope, doc_units, category_readers=None,
             standard=None, progress=None):
    """The full plans (one per entry). progress(fraction, label) between tests; a False
    answer raises namo.items.Cancelled (nothing has been written yet)."""
    plans = []
    count = len(entries) or 1
    for index, entry in enumerate(entries):
        if progress is not None and progress(float(index) / count, 'Planning %s' % entry['name']) == False:  # noqa: E712
            from namo import items as _items
            raise _items.Cancelled()
        reader = category_readers[index] if category_readers else None
        plans.append(plan_test(entry['name'], entry['rows'], entry['specs'], clash_template,
                               group_template, scope, doc_units, reader, standard))
    return plans


def result_text(clashes, groups, tests):
    """The toast line: 'Renamed 1,240 clashes in 3 tests' (+ groups when any)."""
    parts = []
    if clashes:
        parts.append('{:,} clash{}'.format(clashes, '' if clashes == 1 else 'es'))
    if groups:
        parts.append('{:,} group{}'.format(groups, '' if groups == 1 else 's'))
    return 'Renamed {} in {:,} test{}'.format(' and '.join(parts), tests, '' if tests == 1 else 's')


def walk_tree(children, is_group, is_leaf, children_of):
    """(nodes, leaves, groups) of a results tree in Clash Detective order:
    nodes are ('leaf', item, leaf id) and ('group', item, group id, [nodes]); leaf ids
    follow pynavis.clash.snapshot_results' depth-first order; group ids number every
    group at any depth in pre-order. Pure over the three callables."""
    leaves = []
    groups = []

    def walk(items):
        nodes = []
        for child in items:
            if is_group(child):
                gid = len(groups)
                groups.append(child)
                nodes.append(('group', child, gid, walk(children_of(child))))
            elif is_leaf(child):
                nodes.append(('leaf', child, len(leaves)))
                leaves.append(child)
        return nodes

    return walk(children), leaves, groups


def group_specs(nodes):
    """[{'gid', 'ids'}] for every group node (any depth), pre-order, ids = leaf ids
    beneath it."""
    out = []

    def leaf_ids(items):
        ids = []
        for node in items:
            if node[0] == 'leaf':
                ids.append(node[2])
            else:
                ids.extend(leaf_ids(node[3]))
        return ids

    def walk(items):
        for node in items:
            if node[0] == 'group':
                out.append({'gid': node[2], 'ids': leaf_ids(node[3])})
                walk(node[3])

    walk(nodes)
    out.sort(key=lambda g: g['gid'])
    return out


def touched_groups(nodes, clash_names, group_names):
    """Group ids whose subtree holds a renamed clash or group (pure)."""
    return clashset_edit.touched_groups(nodes, clash_names, group_names)


# ==== API half (Navisworks only; lazy imports) =============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def read_test(test, doc=None, progress=None):
    """{'test', 'name', 'guid', 'rows', 'nodes', 'leaves', 'groups', 'specs'} for one
    live test. Raises RuntimeError when the tree and the snapshot disagree."""
    from namo import clashdata
    ClashApi = defs.clash_api()
    rows = clashdata.snapshot(test, _doc(doc), progress)
    nodes, leaves, groups = walk_tree(
        test.Children,
        lambda item: isinstance(item, ClashApi.ClashResultGroup),
        lambda item: isinstance(item, ClashApi.ClashResult),
        lambda item: item.Children)
    if len(leaves) != len(rows):
        raise RuntimeError('The clash results of %s changed while they were read; run it again.'
                           % test.DisplayName)
    specs = group_specs(nodes)
    for spec in specs:
        spec['name'] = groups[spec['gid']].DisplayName
    return {'test': test, 'name': test.DisplayName, 'guid': str(test.Guid), 'rows': rows,
            'nodes': nodes, 'leaves': leaves, 'groups': groups, 'specs': specs}


def category_reader(entry):
    """category_of(row) for plan_test over one read_test entry, memoised per element."""
    from namo import items as _items
    memo = {}

    def element(result, side):
        composite = result.CompositeItem1 if side == 'a' else result.CompositeItem2
        if composite is not None:
            return composite
        return result.Item1 if side == 'a' else result.Item2

    def category_of(row):
        out = []
        result = entry['leaves'][row['id']]
        for side in ('a', 'b'):
            key = row.get('item_' + side) or ('%s:%s' % (side, row['id']))
            if key not in memo:
                item = element(result, side)
                try:
                    memo[key] = _items.category(item) if item is not None else ''
                except Exception:
                    memo[key] = ''
            out.append(memo[key])
        return tuple(out)

    return category_of


_commit = clashset_edit.commit


def _renamer(name):
    def edit(copy):
        copy.DisplayName = name
    return edit


def rebuild(entry, clash_names, group_names):
    """A detached copy of entry's test with the new names (no document edit)."""
    return clashset_edit.rebuild(
        entry,
        dict((rid, _renamer(name)) for rid, name in clash_names.items()),
        dict((gid, _renamer(name)) for gid, name in group_names.items()))


def apply(entries, plans, threshold=DEFAULT_THRESHOLD, doc=None, progress=None):
    """Writes the plans (one per entry, same order) in ONE undo step. Returns
    {'clashes', 'groups', 'tests', 'mode' ('edit' | 'rebuild')}. progress(fraction,
    label) only reports: a write is never stopped halfway (its answer is ignored)."""
    document = _doc(doc)
    data = defs._clash().get_clash(document).TestsData
    total = sum(len(p['clashes']) + len(p['groups']) for p in plans)
    result = {'clashes': sum(len(p['clashes']) for p in plans),
              'groups': sum(len(p['groups']) for p in plans),
              'tests': sum(1 for p in plans if p['clashes'] or p['groups']),
              'mode': clashset_edit.mode_for(total, threshold)}
    if not total:
        return result
    with clashset_edit.one_step('Rename clashes', document, result['mode'], result['tests']):
        if result['mode'] == 'edit':
            done = 0
            for entry, plan in zip(entries, plans):
                for gid, _old, new in plan['groups']:
                    data.TestsEditDisplayName(entry['groups'][gid], new)
                    done += 1
                for rid, _old, new in plan['clashes']:
                    data.TestsEditDisplayName(entry['leaves'][rid], new)
                    done += 1
                    if progress is not None and done % 200 == 0:
                        progress(float(done) / total, 'Renaming {:,} of {:,}'.format(done, total))
        else:
            count = len(entries) or 1
            for index, (entry, plan) in enumerate(zip(entries, plans)):
                if not (plan['clashes'] or plan['groups']):
                    continue
                if progress is not None:
                    progress(float(index) / count, 'Renaming %s' % entry['name'])
                clash_names = dict((rid, new) for rid, _old, new in plan['clashes'])
                group_names = dict((gid, new) for gid, _old, new in plan['groups'])
                new_test = rebuild(entry, clash_names, group_names)
                _commit(data, entry['test'], new_test)
    if progress is not None:
        progress(1.0, 'Done')
    return result


# ---- the preview window -------------------------------------------------------------------


class NamerState(object):
    """window.Tag: the controls, `result` ({'clash_template', 'group_template',
    'scope'}) and `accepted` after Apply."""

    def __init__(self, window, preview):
        self.window = window
        self.preview = preview
        self.result = None
        self.accepted = False
        self.clash_box = None
        self.group_box = None
        self.scope_buttons = None
        self.table = None
        self.status = None
        self.apply_button = None

    def values(self):
        from namo import ui
        return {'clash_template': self.clash_box.Text, 'group_template': self.group_box.Text,
                'scope': ui.radio_value(self.scope_buttons, SCOPES) or 'clashes'}

    def refresh(self):
        values = self.values()
        rows, status, ok = self.preview(values['clash_template'], values['group_template'],
                                        values['scope'])
        self.table.update(rows)
        self.status.Text = status
        self.apply_button.IsEnabled = bool(ok)
        return rows

    def accept(self):
        values = self.values()
        _rows, _status, ok = self.preview(values['clash_template'], values['group_template'],
                                          values['scope'])
        if not ok:
            return False
        self.result = values
        self.accepted = True
        try:
            self.window.DialogResult = True
        except Exception:
            self.window.Close()
        return True


def build_window(preview, defaults, title='Clash Namer'):
    """The unshown Clash Namer window. preview(clash_template, group_template, scope)
    -> (table rows [test, kind, before, after], status text, ok). defaults: the
    starting {'clash_template', 'group_template', 'scope'}."""
    from namo import ui
    from namo.clashset_common import wpf
    wpf()
    from System.Windows import GridLength, GridUnitType, VerticalAlignment
    from System.Windows.Controls import ColumnDefinition, Dock, DockPanel, Grid, RowDefinition
    logger = ui.pinned_logger()
    win = ui.window(title, width=900, height=640, resizable=True, min_width=640, min_height=440)
    state = NamerState(win, preview)
    win.Tag = state

    form = Grid()
    form.Margin = _thickness(16, 16, 16, 8)
    for width in (GridLength(120.0), GridLength(1.0, GridUnitType.Star)):
        column = ColumnDefinition()
        column.Width = width
        form.ColumnDefinitions.Add(column)
    for _index in range(4):
        definition = RowDefinition()
        definition.Height = GridLength.Auto
        form.RowDefinitions.Add(definition)

    def place(element, row, col, span=1):
        Grid.SetRow(element, row)
        Grid.SetColumn(element, col)
        if span > 1:
            Grid.SetColumnSpan(element, span)
        form.Children.Add(element)

    clash_shell, state.clash_box = ui.text_box(defaults.get('clash_template', DEFAULT_CLASH))
    group_shell, state.group_box = ui.text_box(defaults.get('group_template', DEFAULT_GROUP))
    scope_panel, state.scope_buttons = ui.radio_group(SCOPES, defaults.get('scope', 'clashes'),
                                                      inline=True)
    for row, (label, element) in enumerate((('Clash names', clash_shell),
                                            ('Group names', group_shell),
                                            ('Rename', scope_panel))):
        caption = ui.text(label)
        caption.VerticalAlignment = VerticalAlignment.Center
        caption.Margin = _thickness(0, 0, 8, 8)
        element.Margin = _thickness(0, 0, 0, 8)
        place(caption, row, 0)
        place(element, row, 1)
    tokens_hint = ui.hint(TOKEN_HINT)
    tokens_hint.Margin = _thickness(0, 0, 0, 4)
    place(tokens_hint, 3, 1)

    state.table = ui.Table(['Test', 'Kind', 'Before', 'After'], [], multiselect=False, logger=logger)
    table_host = state.table.element
    table_host.Margin = _thickness(16, 4, 16, 12)

    state.status = ui.hint('')
    state.apply_button = ui.button('Rename', lambda: state.accept(), 'primary', logger)
    state.apply_button.IsDefault = True
    cancel = ui.button('Cancel', lambda: close_window(win, False), 'secondary', logger)
    cancel.IsCancel = True
    bar = ui.footer([state.apply_button, cancel], left=state.status, padding=16)

    layout = DockPanel()
    DockPanel.SetDock(bar, Dock.Bottom)
    layout.Children.Add(bar)
    DockPanel.SetDock(form, Dock.Top)
    layout.Children.Add(form)
    layout.Children.Add(table_host)
    win.Content = layout

    debounce = ui.Debouncer(250, lambda: state.refresh())
    for box in (state.clash_box, state.group_box):
        box.TextChanged += ui.safe(lambda s, e: debounce.trigger(), 'namer preview', logger)
    for control in state.scope_buttons:
        control.Checked += ui.safe(lambda s, e: state.refresh(), 'namer scope', logger)
    win.ContentRendered += ui.safe(lambda s, e: state.clash_box.Focus(), 'namer focus', logger)
    state.refresh()
    return win

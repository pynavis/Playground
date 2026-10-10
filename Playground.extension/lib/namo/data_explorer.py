# -*- coding: utf-8 -*-
"""Property Explorer: the scan flow and the modeless three-list window.

    Categories (items)  ->  Properties (items, distinct values)  ->  Values (count, share)

Picking a category fills the properties, picking a property fills its values; every
list filters as you type. Actions on the picked values: Select items (within the
scanned items, read exactly the way the list was built), Create search set (a live
search for text, whole-number and yes/no values; a fixed set otherwise, and the toast
says which), Copy (the value list as tab-separated text) and Export the whole index to
Excel. Rescan asks for the scope again and reloads the lists in place.

Every handler runs after the button's script returned: it uses the BoundScript `me`
and the logger pinned during the run, and is wrapped by namo.ui (logged, never raised).
"""

import time

from namo import data_common, propindex

KEY = 'property-explorer'
TITLE = 'Property Explorer'
SET_FOLDER = 'Property Explorer'
DEFAULTS = {'scope': 'model', 'level': 'objects', 'budget': propindex.DEFAULT_BUDGET}
PREFERRED = (('Element', 'Category'), ('Item', 'Name'))


# =============================================================================
# Pure half
# =============================================================================


def category_rows(index):
    return [{'cells': [cat, items], 'value': cat} for cat, items, _n in index.categories()]


def property_rows(index, category):
    return [{'cells': [prop, items, distinct], 'value': prop}
            for prop, items, distinct, _kind, _capped in index.properties(category)]


def value_rows(index, category, prop):
    total = index.total
    return [{'cells': [text, count, propindex.share_text(count, total)], 'value': text}
            for text, count in index.values(category, prop)]


def status_text(entry, now=None):
    """'48,213 objects in the whole model, scanned at 14:02'."""
    stamp = time.strftime('%H:%M', time.localtime(entry.get('time') or now or time.time()))
    return '%s, scanned at %s' % (propindex.scope_text(entry['scope'], entry['level'], entry['index'].total,
                                                       entry.get('sampled')), stamp)


def first_choice(values, preferred):
    """preferred if it is among values, else the first value, else None."""
    if preferred in values:
        return preferred
    return values[0] if values else None


def set_name(category, prop, value):
    """'Category = Ducts' style set names (property name only, short)."""
    shown = value if len(value) <= 60 else value[:57] + '...'
    return '%s = %s' % (prop or category, shown)


def export_rows(index):
    return index.rows()


# =============================================================================
# Scan flow (runs inside the button's run, or from Rescan)
# =============================================================================


def ask_scope(me, doc):
    """The scope form; returns (scope, level, budget) or None when cancelled. The
    choice is remembered through the BoundScript me."""
    from namo import ui
    values = me.get_config(DEFAULTS)
    has_selection = data_common.selected_count(doc) > 0
    fields = data_common.scope_fields(has_selection, values.get('scope'), values.get('level'),
                                      budget=values.get('budget') or propindex.DEFAULT_BUDGET)
    answer = ui.form(TITLE, fields, intro='Scan which items? Every property of every item is read once; '
                                           'the lists then filter instantly.', ok='Scan')
    if answer is None:
        return None
    me.save_config({'scope': answer['scope'], 'level': answer['level'],
                    'budget': int(answer.get('budget') or propindex.DEFAULT_BUDGET)})
    return answer['scope'], answer['level'], int(answer.get('budget') or propindex.DEFAULT_BUDGET)


def scan_flow(me, doc):
    """Ask the scope, scan with progress + cancel, cache and return the entry. None
    when cancelled (silent) or nothing to scan (toasted)."""
    from pynavis import toast
    from namo import progress
    choice = ask_scope(me, doc)
    if choice is None:
        return None
    scope, level, budget = choice

    def work(report):
        item_list = propindex.scope_items(scope, level, doc,
                                          tick=data_common.stage(report, 0.0, 0.0, 'Collecting items: %s'),
                                          budget=budget)
        if not item_list:
            return None
        index = propindex.scan(item_list, doc, tick=data_common.stage(report, 0.02, 0.98, 'Reading %s'))
        return propindex.remember(index, item_list, scope, level, budget, doc)
    entry = progress.run('Scanning properties', work)
    if entry is progress.CANCELLED:
        return None
    if entry is None:
        message, detail = data_common.nothing_text(scope)
        toast.info(message, detail)
        return None
    return entry


# =============================================================================
# Window
# =============================================================================


class ExplorerState(object):
    """window.Tag: the three tables and the entry they show."""

    def __init__(self, win, entry, me, logger):
        self.window = win
        self.entry = entry
        self.me = me
        self.logger = logger
        self.categories = None
        self.properties = None
        self.values = None
        self.status = None
        self.footer_note = None
        self.category = None
        self.prop = None
        self.busy = False

    # -- loading --

    def load(self, entry):
        self.entry = entry
        self.status.Text = status_text(entry)
        self.category = None
        self.prop = None
        index = entry['index']
        self.categories.update(category_rows(index))
        cats = [cat for cat, _i, _n in index.categories()]
        chosen = first_choice(cats, PREFERRED[0][0])
        if chosen is not None:
            self.categories.select_values([chosen])
        self.on_category()

    def on_category(self):
        if self.busy:
            return
        picked = self.categories.selected_values()
        category = picked[0] if picked else None
        if category == self.category and self.properties.total():
            return
        self.category = category
        self.busy = True
        try:
            index = self.entry['index']
            rows = property_rows(index, category) if category else []
            self.properties.update(rows)
            props = [r['value'] for r in rows]
            preferred = [p for c, p in PREFERRED if c == category]
            chosen = first_choice(props, preferred[0] if preferred else None)
            if chosen is not None:
                self.properties.select_values([chosen])
        finally:
            self.busy = False
        self.on_property(force=True)

    def on_property(self, force=False):
        if self.busy:
            return
        picked = self.properties.selected_values()
        prop = picked[0] if picked else None
        if prop == self.prop and not force:
            return
        self.prop = prop
        index = self.entry['index']
        rows = value_rows(index, self.category, prop) if (self.category and prop) else []
        self.values.update(rows)
        self.on_value()

    def on_value(self):
        picked = self.values.selected_values()
        if not self.prop:
            self.footer_note.Text = ''
            return
        stats = self.entry['index'].stats(self.category, self.prop) or {}
        kind = stats.get('kind') or 'none'
        if picked:
            counts = dict((text, n) for text, n in self.entry['index'].values(self.category, self.prop))
            total = sum(counts.get(v, 0) for v in picked)
            self.footer_note.Text = '%s %s picked, %s items' % (
                '{:,}'.format(len(picked)), 'value' if len(picked) == 1 else 'values', '{:,}'.format(total))
        else:
            self.footer_note.Text = '%s > %s: %s values, %s' % (
                self.category, self.prop, '{:,}'.format(len(stats.get('values') or {})), kind)

    # -- actions --

    def picked(self):
        if not (self.category and self.prop):
            return None
        values = self.values.selected_values()
        return values or None

    def select_items(self):
        from pynavis import toast
        from namo import items, progress
        values = self.picked()
        if values is None:
            toast.info('Pick a value first', 'Choose one or more values in the list on the right.')
            return
        wanted = set(values)
        category, prop = self.category, self.prop
        item_list = self.entry['items']
        reader = propindex.Reader()

        def work(report):
            tick = data_common.stage(report, 0.0, 1.0, 'Checking %s')
            ticker = items.Ticker(tick, total=len(item_list), every=500)
            found = []
            for item in item_list:
                if reader.text(item, category, prop) in wanted:
                    found.append(item)
                ticker.step()
            ticker.finish()
            return found
        found = progress.run('Selecting items', work)
        if found is progress.CANCELLED:
            return
        if not found:
            toast.info('No items have that value now', 'The model may have changed since the scan. Rescan to refresh.')
            return
        items.select(found)
        toast.success('Selected %s %s' % ('{:,}'.format(len(found)), 'item' if len(found) == 1 else 'items'),
                      '%s > %s: %s' % (category, prop, values[0] if len(values) == 1 else
                                       '%d values' % len(values)))

    def create_set(self):
        from pynavis import sets, toast
        values = self.picked()
        if values is None:
            toast.info('Pick a value first', 'Choose the value the set should collect.')
            return
        if len(values) > 1:
            toast.info('Pick one value', 'A search set holds one value; pick a single row.')
            return
        value = values[0]
        category, prop = self.category, self.prop
        vtype = self.entry['index'].vtype_of(category, prop)
        name = set_name(category, prop, value)
        builder = None
        try:
            builder = propindex.search_builder(category, prop, vtype, value)
        except Exception:
            builder = None
        if builder is not None:
            try:
                count = sets.run(builder).Count
            except Exception:
                count = 0
            if count:
                created = sets.create(name, builder, folder=SET_FOLDER)
                toast.success('Search set saved', '%s matches %s %s in the whole model.' % (
                    created.DisplayName, '{:,}'.format(count), 'item' if count == 1 else 'items'))
                return
        reader = propindex.Reader()
        found = [item for item in self.entry['items'] if reader.text(item, category, prop) == value]
        if not found:
            toast.info('No items have that value now', 'Rescan to refresh the lists.')
            return
        created = sets.create(name, found, folder=SET_FOLDER)
        toast.success('Selection set saved', '%s holds %s %s (a fixed list: Navisworks cannot search this '
                      'kind of value exactly).' % (created.DisplayName, '{:,}'.format(len(found)),
                                                   'item' if len(found) == 1 else 'items'))

    def copy_values(self):
        from pynavis import toast
        from namo import ui
        if not (self.category and self.prop):
            toast.info('Pick a property first', 'Choose a property to copy its values.')
            return
        index = self.entry['index']
        rows = [[text, count, propindex.share_text(count, index.total)]
                for text, count in index.values(self.category, self.prop)]
        visible = set(self.values.rows[i]['value'] for i in self.values.visible_indices())
        rows = [row for row in rows if row[0] in visible]
        text = propindex.tsv(rows, ['%s > %s' % (self.category, self.prop), 'Count', 'Share'])
        if ui.copy(text):
            toast.success('Copied %s %s' % ('{:,}'.format(len(rows)), 'value' if len(rows) == 1 else 'values'),
                          'Paste into Excel or a report.')
        else:
            toast.error('Could not copy', 'Another program is holding the clipboard; try again.')

    def export(self):
        from pynavis import toast
        from namo import naming, xlsx
        index = self.entry['index']
        path = data_common.ask_save('{file} - Properties index - {date}', 'xlsx', 'Export the property index')
        if path is None:
            return
        try:
            wb = xlsx.Workbook(title=TITLE, author=naming.standard_values().get('user'))
            ws = wb.sheet('Index')
            ws.title('Property index', span=5)
            ws.subtitle(status_text(self.entry), span=5)
            ws.columns([('Category', 24, None), ('Property', 30, None), ('Value', 40, None),
                        ('Count', 12, 'int'), ('Share', 10, 'pct1')])
            for row in export_rows(index):
                ws.row(row)
            ws.autofilter()
            props = wb.sheet('Properties')
            props.columns([('Category', 24, None), ('Property', 30, None), ('Items', 12, 'int'),
                           ('Distinct values', 16, 'int'), ('Kind', 12, None), ('Capped', 10, None)])
            for cat, _i, _n in index.categories():
                for prop, count, distinct, kind, capped in index.properties(cat):
                    props.row([cat, prop, count, distinct, kind, 'Yes' if capped else ''])
            props.autofilter()
            wb.save(path)
        except (IOError, OSError) as error:
            toast.error('Could not write the workbook', '%s %s' % (data_common.LOCKED, error))
            return
        toast.success('Exported the property index', path)

    def rescan(self):
        from pynavis._api import Application
        document = Application.ActiveDocument
        if not data_common.has_models(document):
            data_common.no_model_toast()
            return
        entry = scan_flow(self.me, document)
        if entry is not None:
            self.load(entry)


def build_window(entry, me=None, logger=None):
    """The Explorer window (unshown) for a cached scan entry; window.Tag is its
    ExplorerState."""
    from namo import ui
    ui._wpf()
    from System.Windows import GridLength, GridUnitType, Thickness, VerticalAlignment
    from System.Windows.Controls import (ColumnDefinition, Dock, DockPanel, Grid, Orientation, RowDefinition,
                                         StackPanel)
    logger = logger or ui.pinned_logger()
    win = ui.window(TITLE, width=1120, height=680, resizable=True, min_width=760, min_height=420)
    state = ExplorerState(win, entry, me, logger)
    win.Tag = state

    def guarded(fn, label):
        return ui.safe(fn, label, logger)

    state.categories = ui.Table(['Category', 'Items'], [], multiselect=True,
                                on_change=guarded(state.on_category, 'categories'), logger=logger)
    state.properties = ui.Table(['Property', 'Items', 'Values'], [], multiselect=True,
                                on_change=guarded(state.on_property, 'properties'), logger=logger)
    state.values = ui.Table(['Value', 'Count', 'Share'], [], multiselect=True,
                            on_open=lambda value: guarded(state.select_items, 'open value')(),
                            on_change=guarded(state.on_value, 'values'), logger=logger)

    root = DockPanel()
    top = DockPanel()
    top.Margin = Thickness(16, 14, 16, 10)
    rescan = ui.button('Rescan', state.rescan, 'secondary', logger)
    export = ui.button('Export to Excel', state.export, 'secondary', logger)
    export.Margin = Thickness(8, 0, 0, 0)
    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.Children.Add(rescan)
    buttons.Children.Add(export)
    DockPanel.SetDock(buttons, Dock.Right)
    top.Children.Add(buttons)
    state.status = ui.text('', 13, muted=True, wrap=False)
    state.status.VerticalAlignment = VerticalAlignment.Center
    top.Children.Add(state.status)
    DockPanel.SetDock(top, Dock.Top)
    root.Children.Add(top)

    state.footer_note = ui.hint('')
    select = ui.button('Select items', state.select_items, 'primary', logger)
    create = ui.button('Create search set', state.create_set, 'secondary', logger)
    copy = ui.button('Copy', state.copy_values, 'secondary', logger)
    close = ui.button('Close', lambda: win.Close(), 'secondary', logger)
    close.IsCancel = True
    bar = ui.footer([select, create, copy, close], left=state.footer_note, padding=16)
    DockPanel.SetDock(bar, Dock.Bottom)
    root.Children.Add(bar)

    grid = Grid()
    grid.Margin = Thickness(16, 0, 16, 12)
    for weight in (1.0, 1.2, 1.5):
        column = ColumnDefinition()
        column.Width = GridLength(weight, GridUnitType.Star)
        grid.ColumnDefinitions.Add(column)
    for index, (heading, table, placeholder) in enumerate((
            ('Categories', state.categories, 'Filter categories'),
            ('Properties', state.properties, 'Filter properties'),
            ('Values', state.values, 'Filter values'))):
        panel = Grid()
        panel.Margin = Thickness(0 if index == 0 else 8, 0, 0, 0)
        for size in ('auto', 'auto', 'star'):
            row = RowDefinition()
            row.Height = GridLength(1, GridUnitType.Star) if size == 'star' else GridLength.Auto
            panel.RowDefinitions.Add(row)
        label = ui.text(heading, 13, bold=True)
        label.Margin = Thickness(0, 0, 0, 6)
        Grid.SetRow(label, 0)
        panel.Children.Add(label)
        search, _box = ui.search_box(placeholder, (lambda t: (lambda query: t.set_filter(query)))(table))
        search.Margin = Thickness(0, 0, 0, 8)
        Grid.SetRow(search, 1)
        panel.Children.Add(search)
        Grid.SetRow(table.element, 2)
        panel.Children.Add(table.element)
        Grid.SetColumn(panel, index)
        grid.Children.Add(panel)
    root.Children.Add(grid)
    win.Content = root
    state.load(entry)
    return win


def show(entry, me, logger=None):
    """Opens the Explorer for entry, or brings the open one forward and reloads it."""
    from namo import ui
    existing = ui.Modeless.get(KEY)
    if existing is not None:
        state = existing.Tag
        if isinstance(getattr(state, 'entry', None), dict) and state.entry is not entry:
            state.load(entry)
        existing.Activate()
        return existing
    return ui.Modeless(KEY, TITLE, window_factory=lambda: build_window(entry, me, logger)).show()

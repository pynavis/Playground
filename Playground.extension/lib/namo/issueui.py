# -*- coding: utf-8 -*-
"""The Issues dock pane: the register, the editor, the comments thread.

script.py of Issues.dockpane calls mount(__pane__, script.bind(), logger). Everything
the pane does to Navisworks goes through an Env (the live one by default, a fake in the
smoke tests): read the active document's register (namo.issuestore), capture the view,
go to an issue, pick a pin point, take a screenshot.

Robustness rules, the Viewpoint Tracker's (lib/vptrackerlive.py in pyNavis):
  * Reload re-runs script.py against fresh controls; the previous pane's detach() (kept
    in the 'issues_pane' session holder) runs first, so no old handler keeps painting
    into controls that are gone.
  * Every handler that fires after the run (clicks, timers, document events, issue
    events) is wrapped with namo.ui.safe and a pinned logger: an exception is logged,
    never thrown back into Navisworks.
  * It subscribes to Navisworks directly (ActiveDocumentChanged, FileNameChanged)
    rather than through pyNavis hooks, which are skipped while any command runs.
  * It works with no document, an empty document and an unsaved one (each says what to
    do), refreshes when any tool in this session changes issues (namo.issuestore
    events) and when the panel is shown again; Refresh re-reads a shared folder.
  * Edits are explicit: Save (or moving to another issue, which saves first) sends only
    the fields that changed, so a colleague's edits to other fields survive; comments are
    appended at once.

Pure helpers (cells, keys, options, field diffs, text) come first and are unit tested;
WPF is imported inside the functions that build controls.
"""

import os
import traceback

HOLDER = 'issues_pane'
EVENT_KEY = 'issues-pane'
CONFIG_DEFAULTS = {'status': 'open', 'trade': '', 'assignee': '', 'new_type': 'Issue',
                   'splitter': None}
STATUS_FILTERS = [('Unresolved', 'open'), ('All statuses', 'all'),
                  ('Open', 'Open'), ('In progress', 'In progress'), ('Resolved', 'Resolved'),
                  ('Closed', 'Closed'), ('Void', 'Void'), ('Resolved or closed', 'closed')]
# Columns dropped, in this order, as the pane gets narrower: (min list width, column index).
NARROW = [(600, 4), (500, 3), (420, 5)]


def hidden_columns(width):
    """Indexes of the list columns to hide at a list width (Trade first, then Priority,
    then Due); ID, Title and Status always show."""
    return sorted(index for limit, index in NARROW if width < limit)
TONE_TOKENS = {'good': 'success', 'warn': 'warning', 'bad': 'error', 'info': 'info'}


def _text(value):
    return '' if value is None else (u'%s' % (value,)).strip()


# =====================================================================================
# Pure half
# =====================================================================================


def natural_text_key(text):
    """A text that sorts naturally as plain text: lower case, digit runs zero-padded
    ('Level 2' < 'Level 10')."""
    import re
    return re.sub(r'\d+', lambda m: m.group(0).zfill(12), _text(text).lower())


def sort_keys(issue):
    """The hidden k_* sort columns for one issue (text keys that sort right)."""
    from namo import issues
    prefix, number = issues.split_id(issue.get('id'))
    status_rank = issues._rank(issue.get('status'), issues.STATUSES)
    priority_rank = issues._rank(issue.get('priority'), issues.URGENCY)
    return {'k_id': u'%s|%09d' % (prefix.lower(), number if number is not None else 0),
            'k_title': natural_text_key(issue.get('title')),
            'k_status': u'%d' % status_rank,
            'k_priority': u'%d' % priority_rank,
            'k_trade': _text(issue.get('trade')).lower() or u'~',
            'k_due': _text(issue.get('due')) or u'9999-12-31'}


def row_values(issue, today=None):
    """Display text for the list: {'id', 'title', 'status', 'priority', 'trade', 'due',
    'due_state', 'status_tone', 'priority_tone'}."""
    from namo import dates, issues
    due = _text(issue.get('due'))
    return {'id': _text(issue.get('id')), 'title': _text(issue.get('title')),
            'status': _text(issue.get('status')), 'priority': _text(issue.get('priority')),
            'trade': _text(issue.get('trade')),
            'due': dates.format(due) if due else '',
            'due_state': issues.due_state(issue, today),
            'status_tone': issues.STATUS_TONES.get(issue.get('status'), 'neutral'),
            'priority_tone': issues.PRIORITY_TONES.get(issue.get('priority'), 'neutral')}


def chip_colors(tone, palette):
    """(background, foreground) '#RRGGBB' for a status chip in the current theme: a wash
    of the tone colour over the paper, the tone colour for text (neutral: surface and
    muted). palette: namo.ui.palette()."""
    from namo import colors
    paper = palette['paper']
    if tone not in TONE_TOKENS:
        return palette.get('surface', paper), palette.get('muted', palette.get('ink'))
    base = palette[TONE_TOKENS[tone]]
    dark = colors.luminance(paper.lstrip('#')) < 0.3
    background = colors.blend(base.lstrip('#'), paper.lstrip('#'), 0.78 if dark else 0.86)
    foreground = base.lstrip('#')
    if colors.contrast_ratio(foreground, background) < 4.0:
        foreground = colors.blend(foreground, 'FFFFFF' if dark else '000000', 0.35)
    return '#' + background, '#' + foreground


def filter_options(rows, config_trades=None):
    """(trades, assignees) chooser options [(label, value)] for the rows: 'All' first,
    the values found, then the configured trades not yet used, then 'No trade' /
    'Unassigned' when some rows have none."""
    from namo import issues, naming
    found = issues.distinct(rows, 'trade')
    lower = set(t.lower() for t in found)
    extra = [t for t in (config_trades or []) if t.lower() not in lower and t != issues.NO_TRADE
             and t.lower() != 'unassigned']
    trades = sorted(found + extra, key=naming.natural_key)
    trade_opts = [('All trades', '')] + [(t, t) for t in trades] + [(issues.NO_TRADE, issues.NO_TRADE)]
    people = issues.distinct(rows, 'assignee')
    assignee_opts = [('Everyone', '')] + [(p, p) for p in people] + \
        [(issues.NO_ASSIGNEE, issues.NO_ASSIGNEE)]
    return trade_opts, assignee_opts


def apply_filters(rows, status, trade, assignee, text, today=None):
    """The rows the pane shows (default order: open first, most urgent, earliest due)."""
    from namo import issues
    found = issues.filter_issues(rows, status=status or None, trade=trade or None,
                                 assignee=assignee or None, text=text or '', today=today)
    return issues.sort_issues(found)


FIELDS = ('title', 'type', 'status', 'priority', 'trade', 'assignee', 'due', 'labels',
          'description')


def diff_fields(loaded, edited):
    """{field: new value} for the editor fields that differ from the loaded issue
    (labels compared as lists; text trimmed except the description)."""
    from namo import issues
    out = {}
    for key in FIELDS:
        new = edited.get(key)
        old = loaded.get(key)
        if key == 'labels':
            new_list = issues.labels_from_text(new) if not isinstance(new, (list, tuple)) \
                else [_text(v) for v in new if _text(v)]
            if new_list != list(old or []):
                out[key] = new_list
            continue
        if key == 'description':
            if (new or '') != (old or ''):
                out[key] = new or ''
            continue
        if key == 'due':
            if _text(new) != _text(old) and issues.due_text(new) != _text(old):
                out[key] = _text(new)
            continue
        if _text(new) != _text(old):
            out[key] = _text(new)
    return out


def location_text(issue):
    """'Level 2, grid C-4' / 'Pin set (no grid)' / 'No pin'."""
    location = issue.get('location')
    if not location:
        return 'No pin'
    parts = []
    if location.get('level'):
        parts.append('Level %s' % location['level'] if not
                     _text(location['level']).lower().startswith('level') else location['level'])
    if location.get('grid'):
        parts.append('grid %s' % location['grid'])
    return ', '.join(parts) if parts else 'Pin set (no grid nearby)'


def elements_text(issue):
    elements = issue.get('elements') or []
    if not elements:
        return 'No elements'
    first = elements[0].get('name') or 'element'
    if len(elements) == 1:
        return first
    return '%s and %d more' % (first, len(elements) - 1)


def comment_head(comment):
    """'jane, 2026-10-05 14:30'."""
    from namo import dates
    when = dates.parse(comment.get('date'))
    stamp = when.strftime('%Y-%m-%d %H:%M') if when is not None else ''
    return ', '.join(p for p in (_text(comment.get('author')) or 'Unknown', stamp) if p)


def created_text(issue):
    """'Raised by amol on 2026-10-05; changed by jane on 2026-10-06'."""
    from namo import dates
    parts = []
    created = dates.parse(issue.get('created'))
    if created is not None:
        parts.append('Raised by %s on %s' % (issue.get('created_by') or 'someone',
                                              dates.format(created)))
    modified = dates.parse(issue.get('modified'))
    if modified is not None and _text(issue.get('modified')) != _text(issue.get('created')):
        parts.append('changed by %s on %s' % (issue.get('modified_by') or 'someone',
                                               dates.format(modified)))
    return '; '.join(parts)


def save_failure(error):
    """(message, detail) for the toast when an issue write raised: IOError / OSError (the
    data folder or a file) or ValueError (a sentence, by the namo.issuestore contract)."""
    if isinstance(error, (IOError, OSError)):
        return ('Could not save the change', '%s Check the data folder is reachable, then try again.'
                % error)
    return ('Could not save the change', str(error) or 'The change could not be saved.')


def empty_state(has_doc, has_model, saved, total, shown):
    """(title, text) for the empty overlay, or None when the list has rows."""
    if not has_doc or not has_model:
        return ('No model open', 'Open or append a model to see its issues.')
    if not saved:
        return ('Save the model first', 'Issues are kept with the model file. Save it as an '
                'NWF or NWD, then raise issues here.')
    if total == 0:
        return ('No issues yet', 'Set up the view, select what matters, then click New from '
                'view. Issue Stamps and Clash to Issues add issues too.')
    if shown == 0:
        return ('No issues match', 'Change the status, trade or assignee choosers, or clear '
                'the filter box.')
    return None


# =====================================================================================
# The live environment (tests replace it)
# =====================================================================================


class Env(object):
    """What the pane needs from Navisworks; the smoke test passes a fake."""

    def document(self):
        from namo import issuestore
        return issuestore.active_doc()

    def has_model(self, doc):
        from namo import issueapi
        return doc is not None and issueapi.has_model(doc)

    def store(self, doc):
        from namo import issuestore
        return issuestore.for_doc(doc)

    def capture(self, doc, image=True, model_items=None):
        from namo import issueapi
        return issueapi.capture(doc, image=image, model_items=model_items)

    def go_to(self, issue, doc):
        from namo import issueapi
        return issueapi.go_to(issue, doc)

    def select(self, issue, doc):
        from namo import issueapi
        return issueapi.select_elements(issue, doc)

    def pick(self, prompt, doc=None):
        """A point clicked in the view (namo.picking: the host's Measure tool, the prompt
        on the banner), or None on cancel. hit.point is all the pane uses."""
        from namo import picking
        return picking.point(prompt, doc=doc)

    def location(self, point, doc):
        from namo import issueapi
        return issueapi.location_of(point, doc)

    def screenshot(self, doc):
        from namo import issueapi
        return issueapi.snapshot(doc)

    def confirm(self, message, title):
        from pynavis import forms
        return forms.confirm(message, title=title)

    def toast(self, level, message, detail=None):
        from pynavis import toast
        toast.show(level, message, detail)

    def open_path(self, path):
        os.startfile(path)

    def redraw_pins(self, doc):
        from namo import issueapi
        issueapi.redraw_pins(doc)

    def watch(self, changed, log):
        """Subscribes to document changes; returns detach(). changed() is called (wrapped)
        when the active document or its file changes."""
        from pynavis._api import Application
        subscribed = [None]

        def on_file(sender, args):
            try:
                changed()
            except Exception:
                log('document change failed:\n%s' % traceback.format_exc())

        def subscribe(document):
            previous = subscribed[0]
            if previous is document:
                return
            if previous is not None:
                try:
                    previous.FileNameChanged -= on_file
                except Exception:
                    pass
                try:
                    previous.Models.CollectionChanged -= on_file
                except Exception:
                    pass
            subscribed[0] = document
            if document is not None:
                document.FileNameChanged += on_file
                document.Models.CollectionChanged += on_file

        def on_active(sender, args):
            try:
                subscribe(Application.ActiveDocument)
                changed()
            except Exception:
                log('active document change failed:\n%s' % traceback.format_exc())

        Application.ActiveDocumentChanged += on_active
        try:
            subscribe(Application.ActiveDocument)
        except Exception:
            log('could not watch the document:\n%s' % traceback.format_exc())

        def detach():
            try:
                Application.ActiveDocumentChanged -= on_active
            except Exception:
                pass
            try:
                subscribe(None)
            except Exception:
                pass
        return detach


# =====================================================================================
# The pane
# =====================================================================================


def _wpf():
    import clr
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase', 'System.Data'):
        try:
            clr.AddReference(name)
        except Exception:
            pass


class IssuePane(object):
    """The controller behind pane.xaml. find(name) returns a named XAML element."""

    def __init__(self, root, find, env=None, bound=None, logger=None):
        from namo import ui
        _wpf()
        self.ui = ui
        self.root = root
        self.find = find
        self.env = env or Env()
        self.bound = bound
        self.logger = logger or ui.pinned_logger()
        self.rows = []
        self.shown = []
        self.store = None
        self.doc = None
        self.current = None          # the issue as loaded (normalised dict)
        self.dirty = False
        self.loading = False
        self.picking = False         # True while Set pin waits for its click
        self.version_seen = None
        self.detachers = []
        self.settings = dict(CONFIG_DEFAULTS)
        if bound is not None:
            try:
                self.settings.update(bound.get_config(dict(CONFIG_DEFAULTS)))
            except Exception:
                pass
        self.palette = ui.palette()
        self._brushes = {}
        self._build()

    # ---- small helpers ----

    def safe(self, fn, label):
        return self.ui.safe(fn, label, self.logger)

    def action(self, fn, label):
        """safe() for a button that writes to the register: a failed write (the folder
        unreachable, the issue deleted meanwhile) is toasted, not only logged."""
        def guarded(*args):
            try:
                return fn(*args)
            except (IOError, OSError, ValueError) as error:
                self.log('%s failed:\n%s' % (label, traceback.format_exc()))
                message, detail = save_failure(error)
                self.toast('error', message, detail)
                return None
        return self.safe(guarded, label)

    def log(self, message):
        self.ui.log_error('Issues pane: %s' % message, self.logger)

    def brush(self, hex_value):
        key = hex_value.upper()
        if key not in self._brushes:
            self._brushes[key] = self.ui.brush(key)
        return self._brushes[key]

    def say(self, text):
        self.status.Text = text or ''

    def toast(self, level, message, detail=None):
        try:
            self.env.toast(level, message, detail)
        except Exception:
            self.log('toast failed: %s' % message)

    def _save_settings(self):
        if self.bound is None:
            return
        try:
            self.bound.save_config(dict(self.settings))
        except Exception:
            self.log('settings not saved:\n%s' % traceback.format_exc())

    # ---- construction ----

    def _build(self):
        from System.Windows import FontWeights, Thickness, Visibility
        ui = self.ui
        p = self.palette
        self.root.Background = self.brush(p['paper'])
        ui.apply_theme(self.root)
        self.resources = ui.theme_resources()
        self.status = self.find('Status')
        self.status.Foreground = self.brush(p['muted'])
        bar = self.find('StatusBar')
        bar.Background = self.brush(p['surface'])
        bar.BorderBrush = self.brush(p['line'])
        empty_title = self.find('EmptyTitle')
        empty_title.Foreground = self.brush(p['ink'])
        self.find('EmptyText').Foreground = self.brush(p['muted'])
        self.empty = self.find('Empty')
        self.empty.Visibility = Visibility.Collapsed
        self.bold = FontWeights.SemiBold
        self.normal = FontWeights.Normal

        toolbar = self.find('Toolbar')
        self.new_button = ui.button('New from view', self.action(self.new_from_view, 'New from view'),
                                    'primary', self.logger)
        types = self._type_options()
        self.type_combo = ui.combo(types, selected=self.settings.get('new_type') or 'Issue', width=128)
        self.type_combo.ToolTip = 'The type of the next new issue (its template and numbering)'
        self.type_combo.SelectionChanged += self.safe(lambda s, e: self._remember_type(), 'type')
        self.goto_button = ui.button('Go to', self.safe(self.go_to, 'Go to'), 'secondary', self.logger)
        self.goto_button.ToolTip = 'Restore the issue\'s saved view and select its elements (or double-click it)'
        for control in (self.new_button, self.type_combo, self.goto_button):
            control.Margin = Thickness(0, 0, 8, 8)
            toolbar.Children.Add(control)
        self.refresh_button = ui.button('Refresh', self.safe(lambda: self.refresh(True), 'Refresh'),
                                        'quiet', self.logger)
        self.refresh_button.ToolTip = 'Read the register again (picks up colleagues\' changes in a shared folder)'
        self.refresh_button.MinHeight = 0.0
        self.refresh_button.Height = 26.0
        self.refresh_button.FontSize = 12.0
        self.find('RefreshHost').Content = self.refresh_button

        self.status_combo = ui.combo(STATUS_FILTERS, selected=self.settings.get('status') or 'open')
        self.status_combo.ToolTip = 'Show issues with this status'
        self.trade_combo = ui.combo([('All trades', '')], selected='')
        self.trade_combo.ToolTip = 'Show one trade'
        self.assignee_combo = ui.combo([('Everyone', '')], selected='')
        self.assignee_combo.ToolTip = 'Show one assignee'
        search_element, self.search_box = ui.search_box(
            'Filter by id, title, comment, label...', lambda text: self.apply_filter())
        self.find('StatusHost').Content = self.status_combo
        self.find('TradeHost').Content = self.trade_combo
        self.find('AssigneeHost').Content = self.assignee_combo
        self.find('SearchHost').Content = search_element
        for combo in (self.status_combo, self.trade_combo, self.assignee_combo):
            combo.SelectionChanged += self.safe(lambda s, e: self._filters_changed(), 'filter')

        splitter = self.find('Splitter')
        splitter.Background = self.brush(p['line'])
        splitter.BorderBrush = self.brush(p['paper'])
        splitter.BorderThickness = Thickness(0, 4, 0, 4)
        splitter.ToolTip = 'Drag to give the list or the issue more room'
        self.grid = self.find('List')
        self._build_table()
        detail = self.find('Detail')
        self._build_detail(detail)
        self.root.IsVisibleChanged += self.safe(self._visible_changed, 'visibility')

    def _type_options(self):
        from namo import issue_templates, issues
        names = [issues.DEFAULT_TYPE]
        try:
            for template in issue_templates.load():
                if template['type'].lower() not in [n.lower() for n in names]:
                    names.append(template['type'])
        except Exception:
            pass
        return names

    def _remember_type(self):
        if self.loading:
            return
        value = self.ui.combo_value(self.type_combo)
        if value and value != self.settings.get('new_type'):
            self.settings['new_type'] = value
            self._save_settings()

    def _build_table(self):
        import clr
        from System import Object, String
        from System.Data import DataTable
        grid = self.grid
        grid.Resources.MergedDictionaries.Add(self.resources)
        grid.Style = self.resources['namo.grid']
        for column in grid.Columns:
            try:
                if column.GetType().Name == 'DataGridTextColumn':
                    column.ElementStyle = self.resources['namo.celltext']
            except Exception:
                pass
        table = DataTable()
        table.CaseSensitive = False
        for name in ('id', 'title', 'status', 'priority', 'trade', 'due', 'k_id', 'k_title',
                     'k_status', 'k_priority', 'k_trade', 'k_due'):
            table.Columns.Add(name, clr.GetClrType(String))
        for name in ('s_bg', 's_fg', 'p_fg', 'p_weight', 'd_fg', 'd_weight'):
            table.Columns.Add(name, clr.GetClrType(Object))
        self.table = table
        grid.ItemsSource = table.DefaultView
        grid.SelectionChanged += self.safe(self._selection_changed, 'select')
        grid.MouseDoubleClick += self.safe(self._double_click, 'double click')
        grid.PreviewKeyDown += self.safe(self._grid_keys, 'list keys')
        grid.SizeChanged += self.safe(lambda s, e: self._fit_columns(), 'list size')

    def _fit_columns(self, width=None):
        """Hides the least important columns when the pane is narrow."""
        from System.Windows import Visibility
        width = self.grid.ActualWidth if width is None else width
        if not width:
            return
        hide = hidden_columns(width)
        for index in range(self.grid.Columns.Count):
            self.grid.Columns[index].Visibility = (Visibility.Collapsed if index in hide
                                                   else Visibility.Visible)

    # ---- detail editor ----

    def _label(self, text):
        block = self.ui.text(text, 12, muted=True, wrap=False)
        from System.Windows import VerticalAlignment
        block.VerticalAlignment = VerticalAlignment.Center
        return block

    def _field_row(self, grid, row, label, control):
        from System.Windows import GridLength, Thickness, VerticalAlignment
        from System.Windows.Controls import Grid, RowDefinition
        definition = RowDefinition()
        definition.Height = GridLength.Auto
        grid.RowDefinitions.Add(definition)
        block = self._label(label)
        block.VerticalAlignment = VerticalAlignment.Top
        block.Margin = Thickness(0, 8, 8, 8)
        Grid.SetRow(block, row)
        Grid.SetColumn(block, 0)
        grid.Children.Add(block)
        control.Margin = Thickness(0, 0, 0, 8)
        Grid.SetRow(control, row)
        Grid.SetColumn(control, 1)
        grid.Children.Add(control)

    def _build_detail(self, panel):
        from System.Windows import (CornerRadius, GridLength, GridUnitType, HorizontalAlignment,
                                    Thickness, VerticalAlignment)
        from System.Windows.Controls import (Border, ColumnDefinition, DockPanel, Dock, Grid,
                                             StackPanel, WrapPanel)
        from namo import config, issues
        ui = self.ui
        self.detail_panel = panel

        head = DockPanel()
        head.Margin = Thickness(0, 4, 0, 2)
        self.chip = Border()
        self.chip.CornerRadius = CornerRadius(3)
        self.chip.Padding = Thickness(6, 1, 6, 2)
        self.chip.VerticalAlignment = VerticalAlignment.Center
        self.chip_text = ui.text('', 12, wrap=False)
        self.chip.Child = self.chip_text
        DockPanel.SetDock(self.chip, Dock.Right)
        head.Children.Add(self.chip)
        self.heading = ui.text('No issue selected', 15, bold=True)
        head.Children.Add(self.heading)
        panel.Children.Add(head)
        self.meta = ui.hint('')
        self.meta.Margin = Thickness(0, 0, 0, 10)
        panel.Children.Add(self.meta)
        editor = StackPanel()
        self.editor = editor
        panel.Children.Add(editor)

        form = Grid()
        for width in (GridLength(84), GridLength(1, GridUnitType.Star)):
            column = ColumnDefinition()
            column.Width = width
            form.ColumnDefinitions.Add(column)
        self.form = form
        title_shell, self.title_box = ui.text_box('', placeholder='What is wrong, where')
        self.type_field = ui.combo(self._type_options())
        self.status_field = ui.combo(issues.STATUSES)
        self.priority_field = ui.combo(issues.URGENCY)
        trades = [('No trade', '')] + [(t, t) for t in config.get('trades') or []]
        self.trade_field = ui.combo(trades)
        assignee_shell, self.assignee_box = ui.text_box('', placeholder='Name or company')
        due_shell, self.due_box = ui.text_box('', placeholder='YYYY-MM-DD')
        labels_shell, self.labels_box = ui.text_box('', placeholder='Separate with commas')
        description_shell, self.description_box = ui.text_box('', multiline=True, rows=4)
        due_stack = StackPanel()
        due_stack.Children.Add(due_shell)
        self.due_note = ui.hint('')
        self.due_note.Margin = Thickness(2, 4, 0, 0)
        due_stack.Children.Add(self.due_note)
        rows = [('Title', title_shell), ('Type', self.type_field), ('Status', self.status_field),
                ('Priority', self.priority_field), ('Trade', self.trade_field),
                ('Assignee', assignee_shell), ('Due', due_stack), ('Labels', labels_shell),
                ('Description', description_shell)]
        for index, (label, control) in enumerate(rows):
            self._field_row(form, index, label, control)
        editor.Children.Add(form)
        for box in (self.title_box, self.assignee_box, self.due_box, self.labels_box,
                    self.description_box):
            box.TextChanged += self.safe(lambda s, e: self._edited(), 'edit')
        for combo in (self.type_field, self.status_field, self.priority_field, self.trade_field):
            combo.SelectionChanged += self.safe(lambda s, e: self._edited(), 'edit')

        actions = WrapPanel()
        actions.Margin = Thickness(0, 4, 0, 12)
        self.save_button = ui.button('Save', self.safe(self.save, 'Save'), 'primary', self.logger)
        self.revert_button = ui.button('Revert', self.safe(self.revert, 'Revert'), 'secondary',
                                       self.logger)
        self.update_button = ui.button('Update view', self.action(self.update_view, 'Update view'),
                                       'secondary', self.logger)
        self.update_button.ToolTip = 'Replace the saved view, elements and snapshot with what is on screen now'
        self.delete_button = ui.button('Delete', self.action(self.delete, 'Delete'), 'danger',
                                       self.logger)
        for control in (self.save_button, self.revert_button, self.update_button, self.delete_button):
            control.Margin = Thickness(0, 0, 8, 8)
            actions.Children.Add(control)
        editor.Children.Add(actions)

        where = Grid()
        for width in (GridLength(84), GridLength(1, GridUnitType.Star), GridLength.Auto):
            column = ColumnDefinition()
            column.Width = width
            where.ColumnDefinitions.Add(column)
        self.location_text = ui.text('', 13)
        self.elements_text = ui.text('', 13)
        self.pin_button = ui.button('Set pin', self.action(self.set_pin, 'Set pin'), 'quiet', self.logger)
        self.pin_button.ToolTip = 'Click a point in the view to place this issue\'s pin'
        self.select_button = ui.button('Select', self.safe(self.select_elements, 'Select'), 'quiet',
                                       self.logger)
        self.select_button.ToolTip = 'Select this issue\'s elements in the model'
        for row, (label, block, button) in enumerate((('Location', self.location_text, self.pin_button),
                                                      ('Elements', self.elements_text, self.select_button))):
            self._field_row(where, row, label, block)
            button.Margin = Thickness(8, 0, 0, 8)
            Grid.SetRow(button, row)
            Grid.SetColumn(button, 2)
            where.Children.Add(button)
        editor.Children.Add(where)

        images_head = DockPanel()
        images_head.Margin = Thickness(0, 12, 0, 6)
        self.shot_button = ui.button('Add screenshot', self.action(self.add_screenshot, 'Screenshot'),
                                     'quiet', self.logger)
        DockPanel.SetDock(self.shot_button, Dock.Right)
        images_head.Children.Add(self.shot_button)
        images_head.Children.Add(ui.heading('Images'))
        editor.Children.Add(images_head)
        self.images = WrapPanel()
        editor.Children.Add(self.images)

        comments_head = ui.heading('Comments')
        comments_head.Margin = Thickness(0, 16, 0, 6)
        editor.Children.Add(comments_head)
        self.comments = StackPanel()
        editor.Children.Add(self.comments)
        comment_shell, self.comment_box = ui.text_box('', placeholder='Add a comment', multiline=True,
                                                      rows=2)
        comment_shell.Margin = Thickness(0, 8, 0, 8)
        editor.Children.Add(comment_shell)
        self.comment_button = ui.button('Add comment', self.action(self.add_comment, 'Add comment'),
                                        'secondary', self.logger)
        self.comment_button.HorizontalAlignment = HorizontalAlignment.Left
        editor.Children.Add(self.comment_button)
        self.comment_box.PreviewKeyDown += self.safe(self._comment_keys, 'comment keys')
        self._show_issue(None)

    # ---- lifecycle ----

    def attach(self):
        """Subscribes to issue and document events and fills the list."""
        from namo import issuestore
        debounce = self.ui.Debouncer(200, self.safe(lambda: self.refresh(False), 'refresh'))
        self.debounce = debounce

        def issues_changed(kind, ids, key):
            if self.store is not None and key not in (None, self.store.key):
                return
            debounce.trigger()
        self.detachers.append(issuestore.subscribe(EVENT_KEY, issues_changed))
        try:
            self.detachers.append(self.env.watch(lambda: debounce.trigger(), self.log))
        except Exception:
            self.log('document events not watched:\n%s' % traceback.format_exc())
        self.detachers.append(debounce.cancel)
        self.refresh(False)
        return self

    def detach(self):
        """Removes every subscription and timer. Each step guarded."""
        for step in reversed(self.detachers):
            try:
                step()
            except Exception:
                pass
        self.detachers = []

    def _visible_changed(self, sender, args):
        if self.root.IsVisible:
            from namo import issuestore
            if self.version_seen != issuestore.version():
                self.refresh(False)

    # ---- loading ----

    def refresh(self, manual=False):
        """Re-reads the register of the active document and repaints, keeping the
        selection (and any unsaved edits) when the issue is still there."""
        from namo import issuestore
        doc = self.env.document()
        store = self.env.store(doc) if doc is not None else None
        old_key = self.store.key if self.store is not None else None
        new_key = store.key if store is not None else None
        if old_key != new_key and self.current is not None:
            if self.dirty and self.store is not None:
                # Into the register it was loaded from, but only when that register still
                # holds THIS issue: in model data mode the store reads the document's own
                # database, which already belongs to the newly opened model (ids repeat
                # from model to model), while a Save As keeps the same issue there.
                stored = self.store.get(self.current['id'])
                if stored is not None and stored['guid'] == self.current['guid']:
                    self.save(quiet=True)
                else:
                    self.toast('warning', 'Edits to %s were not saved' % self.current['id'],
                               'Another model was opened before they were saved.')
            self.dirty = False
            self._show_issue(None)
        self.doc = doc
        has_model = self.env.has_model(doc) if doc is not None else False
        self.store = store
        saved = bool(self.store is not None and self.store.saved)
        self.rows = self.store.list() if (saved and has_model) else []
        self.version_seen = issuestore.version()
        self._fill_filters()
        self.apply_filter(keep=True)
        self._enable(doc is not None and has_model and saved)
        if manual:
            self.say('Refreshed: %s' % self._status_text())

    def _enable(self, ready):
        for control in (self.new_button, self.type_combo, self.goto_button, self.status_combo,
                        self.trade_combo, self.assignee_combo, self.search_box):
            control.IsEnabled = bool(ready)
        self.ready = bool(ready)

    def _fill_filters(self):
        from namo import config
        was = self.loading
        self.loading = True
        try:
            trade_opts, assignee_opts = filter_options(self.rows, config.get('trades') or [])
            self._refill(self.trade_combo, trade_opts, self.settings.get('trade') or '')
            self._refill(self.assignee_combo, assignee_opts, self.settings.get('assignee') or '')
            types = self._type_options()
            self._refill(self.type_combo, types,
                         self.ui.combo_value(self.type_combo) or self.settings.get('new_type') or 'Issue')
            if self.current is None:
                self._refill(self.type_field, types, types[0])
        finally:
            self.loading = was

    def _refill(self, combo, options, wanted):
        from namo import ui
        combo.Items.Clear()
        pairs = ui.options_of({'options': options})
        for label, _value in pairs:
            combo.Items.Add(label)
        combo.Tag.pairs = pairs
        values = [v for _l, v in pairs]
        combo.SelectedIndex = values.index(wanted) if wanted in values else 0

    def _filters_changed(self):
        if self.loading:
            return
        self.settings['status'] = self.ui.combo_value(self.status_combo) or 'open'
        self.settings['trade'] = self.ui.combo_value(self.trade_combo) or ''
        self.settings['assignee'] = self.ui.combo_value(self.assignee_combo) or ''
        self._save_settings()
        self.apply_filter(keep=True)

    def apply_filter(self, keep=True):
        was = self.loading
        self.loading = True
        try:
            self._apply_filter(keep)
        finally:
            self.loading = was

    def _apply_filter(self, keep):
        status = self.ui.combo_value(self.status_combo) or 'open'
        trade = self.ui.combo_value(self.trade_combo) or ''
        assignee = self.ui.combo_value(self.assignee_combo) or ''
        self.shown = apply_filters(self.rows, status, trade, assignee, self.search_box.Text)
        selected = self.current['id'] if (keep and self.current) else None
        self._load_table(self.shown)
        state = empty_state(self.doc is not None, self.env.has_model(self.doc) if self.doc is not None
                            else False, bool(self.store and self.store.saved), len(self.rows),
                            len(self.shown))
        from System.Windows import Visibility
        if state is None:
            self.empty.Visibility = Visibility.Collapsed
            self.grid.Visibility = Visibility.Visible
        else:
            self.find('EmptyTitle').Text, self.find('EmptyText').Text = state
            self.empty.Visibility = Visibility.Visible
            self.grid.Visibility = Visibility.Collapsed
        if selected and any(i['id'] == selected for i in self.rows):
            self._select_row(selected)
            fresh = self._issue(selected)
            if fresh is not None and not self.dirty:
                self._show_issue(fresh)
        elif self.current is not None and not any(i['id'] == self.current['id'] for i in self.rows):
            self.dirty = False
            self._show_issue(None)
        self.say(self._status_text())

    def _status_text(self):
        from namo import issues
        if self.store is None or not self.store.saved or not self.rows:
            text = ''
        else:
            text = issues.status_line(self.rows, shown=len(self.shown))
        if self.store is not None and self.store.saved:
            mode = self.store.describe()
            text = (text + '  |  ' if text else '') + mode
            if self.store.note:
                text += '. ' + self.store.note
        return text

    def _load_table(self, rows):
        from System import Array, Object
        table = self.table
        table.BeginLoadData()
        try:
            table.Rows.Clear()
            for issue in rows:
                v = row_values(issue)
                k = sort_keys(issue)
                s_bg, s_fg = chip_colors(v['status_tone'], self.palette)
                p_fg = self.palette['ink']
                p_weight = self.normal
                if v['priority_tone'] in ('bad', 'warn'):
                    p_fg = chip_colors(v['priority_tone'], self.palette)[1]
                    p_weight = self.bold if v['priority_tone'] == 'bad' else self.normal
                d_fg = self.palette['ink']
                d_weight = self.normal
                if v['due_state'] == 'overdue':
                    d_fg = self.palette['error']
                    d_weight = self.bold
                elif v['due_state'] in ('done', 'none'):
                    d_fg = self.palette['muted']
                values = [v['id'], v['title'], v['status'], v['priority'], v['trade'] or '',
                          v['due'] + (' late' if v['due_state'] == 'overdue' else ''),
                          k['k_id'], k['k_title'], k['k_status'], k['k_priority'], k['k_trade'],
                          k['k_due'], self.brush(s_bg), self.brush(s_fg), self.brush(p_fg), p_weight,
                          self.brush(d_fg), d_weight]
                table.Rows.Add(Array[Object](values))
        finally:
            table.EndLoadData()

    def _issue(self, issue_id):
        for issue in self.rows:
            if issue['id'] == issue_id:
                return issue
        return None

    def _select_row(self, issue_id):
        view = self.table.DefaultView
        was = self.loading
        self.loading = True
        try:
            for index in range(view.Count):
                if str(view[index]['id']) == issue_id:
                    self.grid.SelectedItem = view[index]
                    try:
                        self.grid.ScrollIntoView(view[index])
                    except Exception:
                        pass
                    return True
            self.grid.SelectedItem = None
            return False
        finally:
            self.loading = was

    def _selected_id(self):
        item = self.grid.SelectedItem
        if item is None:
            return None
        try:
            return str(item['id'])
        except Exception:
            return None

    def _selection_changed(self, sender, args):
        if self.loading:
            return
        wanted = self._selected_id()
        if self.current is not None and wanted == self.current['id']:
            return
        if self.dirty and self.current is not None:
            if not self.save(quiet=True):
                self._select_row(self.current['id'])          # stay: the edit is not valid
                return
            if wanted:
                self._select_row(wanted)                      # saving re-selected the old row
        self._show_issue(self._issue(wanted) if wanted else None)

    def _double_click(self, sender, args):
        if self._selected_id():
            self.go_to()

    def _grid_keys(self, sender, args):
        from System.Windows.Input import Key
        if args.Key == Key.Enter and self._selected_id():
            args.Handled = True
            self.go_to()

    def _comment_keys(self, sender, args):
        from System.Windows.Input import Key, Keyboard, ModifierKeys
        if args.Key == Key.Enter and Keyboard.Modifiers == ModifierKeys.Control:
            args.Handled = True
            self.action(self.add_comment, 'Add comment')()

    # ---- the editor ----

    def _set_combo(self, combo, value):
        values = [v for _l, v in combo.Tag.pairs]
        if value not in values and value:
            combo.Items.Add(value)
            combo.Tag.pairs = combo.Tag.pairs + [(value, value)]
            values.append(value)
        combo.SelectedIndex = values.index(value) if value in values else 0

    def _show_issue(self, issue):
        from System.Windows import Visibility
        was = self.loading
        self.loading = True
        try:
            self.current = issue
            self.dirty = False
            enabled = issue is not None
            for control in (self.title_box, self.type_field, self.status_field, self.priority_field,
                            self.trade_field, self.assignee_box, self.due_box, self.labels_box,
                            self.description_box, self.update_button, self.delete_button,
                            self.pin_button, self.select_button, self.shot_button,
                            self.comment_box, self.comment_button):
                control.IsEnabled = enabled
            self.editor.Visibility = Visibility.Visible if enabled else Visibility.Collapsed
            if issue is None:
                self.heading.Text = 'No issue selected'
                self.meta.Text = 'Pick an issue in the list, or click New from view.'
                self.chip.Visibility = Visibility.Collapsed
                for box in (self.title_box, self.assignee_box, self.due_box, self.labels_box,
                            self.description_box, self.comment_box):
                    box.Text = ''
                self.location_text.Text = ''
                self.elements_text.Text = ''
                self.due_note.Text = ''
                self.images.Children.Clear()
                self.comments.Children.Clear()
                self._update_buttons()
                return
            from namo import issues
            self.heading.Text = issue['id']
            self.meta.Text = created_text(issue)
            self._paint_chip(issue['status'])
            self.title_box.Text = issue['title']
            self._set_combo(self.type_field, issue['type'])
            self._set_combo(self.status_field, issue['status'])
            self._set_combo(self.priority_field, issue['priority'])
            self._set_combo(self.trade_field, issue['trade'])
            self.assignee_box.Text = issue['assignee']
            self.due_box.Text = issue['due']
            self.labels_box.Text = issues.labels_text(issue['labels'])
            self.description_box.Text = issue['description']
            self.due_note.Text = issues.due_note(issue)
            self.location_text.Text = location_text(issue)
            self.elements_text.Text = elements_text(issue)
            self.select_button.IsEnabled = bool(issue['elements'])
            self._paint_images(issue)
            self._paint_comments(issue)
            self._update_buttons()
        finally:
            self.loading = was

    def _paint_chip(self, status):
        from System.Windows import Visibility
        from namo import issues
        background, foreground = chip_colors(issues.STATUS_TONES.get(status, 'neutral'), self.palette)
        self.chip.Background = self.brush(background)
        self.chip_text.Foreground = self.brush(foreground)
        self.chip_text.Text = status
        self.chip.Visibility = Visibility.Visible

    def _paint_images(self, issue):
        from System import Uri, UriKind
        from System.Windows import Thickness
        from System.Windows.Controls import Border, Image
        from System.Windows.Input import Cursors
        from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
        self.images.Children.Clear()
        found = self.store.images_on_disk(issue) if self.store is not None else []
        if not found:
            self.images.Children.Add(self.ui.hint('No images yet. New issues get a snapshot of '
                                                  'the view.'))
            return
        for image, path in found[:12]:
            try:
                bitmap = BitmapImage()
                bitmap.BeginInit()
                bitmap.CacheOption = BitmapCacheOption.OnLoad
                bitmap.DecodePixelWidth = 192
                bitmap.UriSource = Uri(path, UriKind.Absolute)
                bitmap.EndInit()
                bitmap.Freeze()
            except Exception:
                continue
            picture = Image()
            picture.Source = bitmap
            picture.Width = 96.0
            picture.Height = 54.0
            frame = Border()
            frame.BorderBrush = self.brush(self.palette['line'])
            frame.BorderThickness = Thickness(1)
            frame.Margin = Thickness(0, 0, 8, 8)
            frame.Child = picture
            frame.Cursor = Cursors.Hand
            frame.ToolTip = '%s (%s). Click to open.' % (image.get('caption') or image['file'],
                                                         image.get('kind') or 'image')
            frame.MouseLeftButtonUp += self.safe(self._opener(path), 'open image')
            self.images.Children.Add(frame)

    def _opener(self, path):
        def open_it(sender, args):
            self.env.open_path(path)
        return open_it

    def _paint_comments(self, issue):
        from System.Windows import Thickness
        from System.Windows.Controls import StackPanel
        from namo import issues
        self.comments.Children.Clear()
        comments = issue.get('comments') or []
        if not comments:
            self.comments.Children.Add(self.ui.hint('No comments yet.'))
            return
        for comment in comments[-50:]:
            block = StackPanel()
            block.Margin = Thickness(0, 0, 0, 10)
            head = self.ui.text(comment_head(comment), 12, muted=True)
            block.Children.Add(head)
            body = self.ui.text(issues.comment_text(comment) or '(no text)', 13)
            block.Children.Add(body)
            self.comments.Children.Add(block)
        if len(comments) > 50:
            self.comments.Children.Insert(0, self.ui.hint('Showing the last 50 of %d comments.'
                                                          % len(comments)))

    def _edited(self):
        if self.loading or self.current is None:
            return
        self.dirty = bool(diff_fields(self.current, self._edited_values()))
        from namo import issues
        due = self.due_box.Text.strip()
        if due and not issues.due_text(due):
            self.due_note.Text = 'Not a date: use YYYY-MM-DD.'
        else:
            probe = dict(self.current, due=issues.due_text(due),
                         status=self.ui.combo_value(self.status_field) or self.current['status'])
            self.due_note.Text = issues.due_note(probe)
        self._update_buttons()

    def _update_buttons(self):
        dirty = bool(self.dirty and self.current is not None)
        self.save_button.IsEnabled = dirty
        self.revert_button.IsEnabled = dirty
        self.goto_button.IsEnabled = bool(self.current is not None and getattr(self, 'ready', False))

    def _edited_values(self):
        return {'title': self.title_box.Text, 'type': self.ui.combo_value(self.type_field),
                'status': self.ui.combo_value(self.status_field),
                'priority': self.ui.combo_value(self.priority_field),
                'trade': self.ui.combo_value(self.trade_field) or '',
                'assignee': self.assignee_box.Text, 'due': self.due_box.Text,
                'labels': self.labels_box.Text, 'description': self.description_box.Text}

    # ---- actions ----

    def _need_ready(self):
        if not getattr(self, 'ready', False):
            state = empty_state(self.doc is not None, self.env.has_model(self.doc) if self.doc is not None
                                else False, bool(self.store and self.store.saved), len(self.rows), 1)
            if state:
                self.toast('info', state[0], state[1])
            return False
        return True

    def save(self, quiet=False):
        """Saves the editor's changed fields. Returns True when saved (or nothing to save)."""
        if self.current is None or not self.dirty:
            return True
        changes = diff_fields(self.current, self._edited_values())
        if not changes:
            self.dirty = False
            self._update_buttons()
            return True
        try:
            issue, note = self.store.update(self.current['id'], changes,
                                            base_rev=self.current['rev'])
        except ValueError as error:
            self.toast('error', 'Could not save %s' % self.current['id'], str(error))
            return False
        except (IOError, OSError) as error:
            self.toast('error', 'Could not save %s' % self.current['id'],
                       '%s Check the folder is reachable, then try again.' % error)
            return False
        self.dirty = False
        self._replace(issue)
        if note:
            self.toast('warning', 'Saved %s' % issue['id'], note)
        elif not quiet:
            self.say('Saved %s.' % issue['id'])
        else:
            self.say('Saved %s before moving on.' % issue['id'])
        return True

    def _replace(self, issue):
        self.rows = [issue if i['id'] == issue['id'] else i for i in self.rows]
        if not any(i['id'] == issue['id'] for i in self.rows):
            self.rows.append(issue)
        self.current = issue
        self.dirty = False
        self.apply_filter(keep=True)
        self._show_issue(issue)

    def revert(self):
        if self.current is not None:
            fresh = self.store.get(self.current['id']) if self.store is not None else None
            self._show_issue(fresh or self.current)

    def new_from_view(self):
        if not self._need_ready():
            return
        if self.dirty and not self.save(quiet=True):
            return
        from namo import issue_templates, issuestore, issues
        kind = self.ui.combo_value(self.type_combo) or issues.DEFAULT_TYPE
        template = issue_templates.resolve(kind)
        shot = self.env.capture(self.doc, image=True)
        fields = {}
        prefix, pattern = issues.DEFAULT_PREFIX, '{type} {n:000}'
        if template is not None:
            fields, prefix, pattern = issuestore.template_fields(template)
        else:
            fields['type'] = kind
        for key in ('camera', 'camera_units', 'elements', 'location'):
            if shot.get(key) is not None:
                fields[key] = shot[key]
        values = issuestore.capture_title_values(shot)
        try:
            issue = self.store.create(fields, prefix=prefix, title_pattern=pattern,
                                      title_values=values)
        except issuestore.NotSaved as error:
            self.toast('info', 'Save the model first', str(error))
            return
        if shot.get('image'):
            try:
                issue = self.store.add_image(issue['id'], shot['image'], kind='snapshot', move=True)
            except Exception as error:
                self.log('snapshot not attached: %s' % error)
        self.rows.append(issue)
        self._reset_filters_to_show(issue)
        self._select_row(issue['id'])
        self._show_issue(issue)
        self.title_box.Focus()
        self.title_box.SelectAll()
        detail = '%d element%s recorded' % (len(issue['elements']), '' if len(issue['elements']) == 1
                                             else 's')
        if shot.get('element_total', 0) > len(issue['elements']):
            detail += ' (the first %d of %s selected)' % (len(issue['elements']),
                                                          '{:,}'.format(shot['element_total']))
        if shot.get('image_error'):
            detail += '; no snapshot: %s' % shot['image_error']
        self.toast('success', '%s created' % issue['id'], detail + '. Give it a title.')

    def _reset_filters_to_show(self, issue):
        """Make sure a new issue is visible: clear choosers that would hide it."""
        shown = apply_filters([issue], self.ui.combo_value(self.status_combo) or 'open',
                              self.ui.combo_value(self.trade_combo) or '',
                              self.ui.combo_value(self.assignee_combo) or '', self.search_box.Text)
        self._fill_filters()
        if not shown:
            was = self.loading
            self.loading = True
            try:
                self.status_combo.SelectedIndex = 0
                self.trade_combo.SelectedIndex = 0
                self.assignee_combo.SelectedIndex = 0
                self.search_box.Text = ''
            finally:
                self.loading = was
        self.apply_filter(keep=False)

    def go_to(self):
        if self.current is None:
            self.toast('info', 'No issue selected', 'Pick an issue in the list first.')
            return
        result = self.env.go_to(self.current, self.doc)
        from namo import issueapi
        note = issueapi.go_to_note(result)
        if note:
            self.toast('warning' if result['missing'] else 'info', 'Went to %s' % self.current['id']
                       if result['moved'] else 'Nothing to show for %s' % self.current['id'], note)
        else:
            self.say('Showing %s.' % self.current['id'])

    def select_elements(self):
        if self.current is None:
            return
        result = self.env.select(self.current, self.doc)
        if result['missing']:
            from namo import issueapi
            self.toast('warning', 'Selected %d element%s' % (result['selected'],
                                                            '' if result['selected'] == 1 else 's'),
                       issueapi.go_to_note(result))
        else:
            self.say('Selected %d element%s of %s.' % (result['selected'],
                                                      '' if result['selected'] == 1 else 's',
                                                      self.current['id']))

    def update_view(self):
        if self.current is None or not self._need_ready():
            return
        if self.dirty and not self.save(quiet=True):
            return
        shot = self.env.capture(self.doc, image=True)
        changes = {'camera': shot['camera'], 'camera_units': shot['camera_units']}
        if shot.get('elements'):
            changes['elements'] = shot['elements']
            if shot.get('location'):
                changes['location'] = shot['location']
        issue, note = self.store.update(self.current['id'], changes, base_rev=self.current['rev'])
        if shot.get('image'):
            issue = self.store.add_image(issue['id'], shot['image'], kind='snapshot', move=True,
                                         replace_kind=True)
        self._replace(issue)
        self.toast('success', 'Updated the view of %s' % issue['id'],
                   note or ('Elements kept from before: nothing was selected.'
                            if not shot.get('elements') else
                            '%d element%s recorded.' % (len(shot['elements']),
                                                        '' if len(shot['elements']) == 1 else 's')))

    def set_pin(self):
        if self.current is None or not self._need_ready():
            return
        if self.dirty and not self.save(quiet=True):
            return
        if self.picking:
            return                       # the pick already waiting owns the next click
        issue_id = self.current['id']
        doc, store = self.doc, self.store
        # The pick blocks here but keeps the window alive (a nested message loop), so
        # the pane stays clickable: Set pin is greyed until the click or the cancel, and
        # the pin goes to the issue and register it was asked for, whatever is showing
        # by then.
        self.picking = True
        self.pin_button.IsEnabled = False
        try:
            hit = self.env.pick('Click where the pin for %s goes' % issue_id, doc)
        finally:
            self.picking = False
            self.pin_button.IsEnabled = self.current is not None
        if hit is None:
            return                       # Esc, right-click or another tool: say nothing
        location = self.env.location(hit.point, doc)
        issue, note = store.update(issue_id, {'location': location})
        if self.store is not None and self.store.key == store.key:
            if self.current is not None and self.current['id'] == issue_id and not self.dirty:
                self._replace(issue)
            else:
                self.refresh(False)
        self.env.redraw_pins(doc)
        self.toast('success', 'Pin set for %s' % issue_id, location_text(issue))

    def add_screenshot(self):
        if self.current is None or not self._need_ready():
            return
        try:
            path = self.env.screenshot(self.doc)
        except Exception as error:
            self.toast('error', 'Could not capture the view', str(error))
            return
        issue = self.store.add_image(self.current['id'], path, kind='screenshot', move=True)
        self._replace(issue)
        self.say('Added a screenshot to %s.' % issue['id'])

    def add_comment(self):
        if self.current is None:
            return
        text = self.comment_box.Text.strip()
        if not text:
            self.toast('info', 'Write a comment first', 'Type in the box above Add comment.')
            return
        if self.dirty and not self.save(quiet=True):
            return
        issue = self.store.add_comment(self.current['id'], text)
        self.comment_box.Text = ''
        self._replace(issue)
        self.say('Comment added to %s.' % issue['id'])

    def delete(self):
        if self.current is None:
            return
        issue_id = self.current['id']
        count = len(self.current.get('images') or [])
        message = 'Delete %s "%s"%s? This cannot be undone.' % (
            issue_id, self.current['title'], ' and its %d image%s' % (count, '' if count == 1 else 's')
            if count else '')
        if not self.env.confirm(message, 'Delete issue'):
            return
        if self.store.delete(issue_id):
            self.rows = [i for i in self.rows if i['id'] != issue_id]
            self.dirty = False
            self._show_issue(None)
            self.apply_filter(keep=False)
            self.env.redraw_pins(self.doc)
            self.toast('success', 'Deleted %s' % issue_id)
        else:
            self.toast('info', '%s was already deleted' % issue_id)


# =====================================================================================
# script.py entry
# =====================================================================================


def mount(pane, bound=None, logger=None, env=None):
    """Builds the pane into __pane__'s content, detaching the previous build first (a
    Reload re-runs script.py). Returns the IssuePane."""
    from namo import session
    held = session.holder(HOLDER)
    previous = getattr(held, 'detach', None)
    if previous is not None:
        try:
            previous()
        except Exception:
            pass
        held.detach = None
    root = pane.Find('Root') or pane.Content
    controller = IssuePane(root, pane.Find, env=env, bound=bound, logger=logger)
    held.detach = controller.detach
    held.pane = controller
    controller.attach()
    return controller

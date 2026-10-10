# -*- coding: utf-8 -*-
"""The Source Files dock pane: a live list of the appended models.

One row per model: a visibility box (hides or shows the whole model), the name, and a
muted line with the file type, units, file time and item count; a status tag only
when something needs attention (out of date, file not found, folder offline). The
toolbar acts on the selected rows: Isolate, Show all, Select, Zoom, Open folder,
Refresh changed (Document.UpdateFiles), Remove (after a confirm; indexes re-resolved
at click time from each row's model key).

Live behaviour, the way the shipped Viewpoint Tracker does it: the pane subscribes to
the Navisworks events directly (hooks are skipped while any pyNavis command runs, a
panel must not freeze then): Application.ActiveDocumentChanged, the document's
Models.CollectionChanged and FilesUpdated rebuild the list (debounced, an append of
twelve files rebuilds once). A 300 ms timer, only while the pane is visible, keeps
the visibility boxes in step with hiding done elsewhere and counts items lazily: each
model's DescendantsAndSelf is walked a slice at a time (never more than ~40 ms per
tick), so a 2-million-item federation never freezes the pane. Counts are cached per
model file and time in the session, so a Reload or a re-open does not recount.

Every handler body is wrapped (an exception escaping a UI-thread handler can take
Navisworks down) and logs through the logger pinned when the pane was built. Reload
re-runs the pane's script against fresh controls: attach() first calls the previous
run's detach() kept in the session holder.

Pure helpers come first (row texts, the selection model, the count job) and are unit
tested; the WPF/API half is built by dev/tests/smoke_sourcefiles.py.
"""

import time

PANE_KEY = 'Project.tab/Models.panel/Source_Files.dockpane'
HOLDER = 'sourcefiles'
TICK_MS = 300
CHUNK = 4000
SLICE_SECONDS = 0.04
HIDDEN_REFRESH_SECONDS = 1.5
DOT = u' · '

TAG_STATUSES = ('Out of date', 'File not found', 'Folder offline')


# ---- pure: texts ------------------------------------------------------------------------------


def count_text(count):
    """'12,345 items' / 'counting' / '' for a count entry (None = not started)."""
    if count is None:
        return ''
    if count.get('done'):
        return '{:,} items'.format(count['items'])
    return 'counting'


def row_texts(info, stale, count=None):
    """{'name', 'detail', 'tag', 'tag_level', 'tooltip'} for one model row.

    info: a modelmgmt.models_info dict; stale: its modelmgmt.stale_rows row (or
    None); count: {'items', 'done'} or None."""
    from namo import modelmgmt
    parts = []
    kind = info.get('kind') or ''
    if kind:
        parts.append(kind)
    if info.get('units'):
        parts.append(info['units'])
    counted = count_text(count)
    if counted:
        parts.append(counted)
    when = modelmgmt.format_time(stale.get('cache_time')) if stale else ''
    if when:
        parts.append(when)
    tag = ''
    level = ''
    status = stale.get('status') if stale else ''
    if status in TAG_STATUSES:
        tag = status
        level = 'warn' if status == 'Out of date' else 'fail'
    tip = []
    if info.get('file'):
        tip.append('Loaded from: %s' % info['file'])
    if info.get('source') and info.get('source') != info.get('file'):
        tip.append('Source: %s' % info['source'])
    if stale and stale.get('detail'):
        tip.append(stale['detail'])
    if info.get('transformed'):
        tip.append('Moved by its Units and Transform.')
    return {'name': info.get('name') or '', 'detail': DOT.join(parts), 'tag': tag,
            'tag_level': level, 'tooltip': '\n'.join(tip)}


def status_text(rows, counting=False, no_document=False):
    """The pane's bottom line: '8 models, 2 out of date. Counting items.'"""
    from namo import modelmgmt
    if no_document:
        return 'Open or append a model to list its files here.'
    if not rows:
        return 'No models appended yet.'
    text = modelmgmt.plural(len(rows), 'model')
    late = sum(1 for r in rows if r.get('status') == 'Out of date')
    lost = sum(1 for r in rows if r.get('status') in ('File not found', 'Folder offline'))
    hidden = sum(1 for r in rows if r.get('hidden'))
    extras = []
    if late:
        extras.append('%d out of date' % late)
    if lost:
        extras.append('%d not found' % lost)
    if hidden:
        extras.append('%d hidden' % hidden)
    if extras:
        text += ', ' + ', '.join(extras)
    text += '.'
    if counting:
        text += ' Counting items.'
    return text


# ---- pure: selection model ---------------------------------------------------------------------


class Selection(object):
    """Rows selected by key, with an anchor for Shift ranges. Keys are kept in the
    list's order so ranges and keyboard moves are well defined."""

    def __init__(self, keys=None):
        self.keys = list(keys or [])
        self.selected = set()
        self.anchor = None

    def set_keys(self, keys):
        """New row order (after a rebuild): keeps what is still there."""
        self.keys = list(keys)
        self.selected = set(k for k in self.selected if k in self.keys)
        if self.anchor not in self.keys:
            self.anchor = None

    def ordered(self):
        return [k for k in self.keys if k in self.selected]

    def click(self, key, ctrl=False, shift=False):
        if key not in self.keys:
            return
        if shift and self.anchor in self.keys:
            a, b = self.keys.index(self.anchor), self.keys.index(key)
            lo, hi = min(a, b), max(a, b)
            span = set(self.keys[lo:hi + 1])
            self.selected = (self.selected | span) if ctrl else span
            return
        if ctrl:
            if key in self.selected:
                self.selected.discard(key)
            else:
                self.selected.add(key)
            self.anchor = key
            return
        self.selected = set([key])
        self.anchor = key

    def move(self, step, extend=False):
        """Up/Down: moves the focus row by step (extend grows the range from the anchor)."""
        if not self.keys:
            return None
        current = self.anchor if self.anchor in self.keys else None
        if current is None:
            target = self.keys[0] if step > 0 else self.keys[-1]
        else:
            index = max(0, min(len(self.keys) - 1, self.keys.index(current) + step))
            target = self.keys[index]
        if extend and self.selected:
            start = self.ordered()[0] if step > 0 else self.ordered()[-1]
            a, b = self.keys.index(start), self.keys.index(target)
            lo, hi = min(a, b), max(a, b)
            self.selected = set(self.keys[lo:hi + 1])
            self.anchor = target
        else:
            self.selected = set([target])
            self.anchor = target
        return target

    def select_all(self):
        self.selected = set(self.keys)

    def select(self, keys):
        wanted = [k for k in keys if k in self.keys]
        self.selected = set(wanted)
        self.anchor = wanted[0] if wanted else None


# ---- pure: lazy counting --------------------------------------------------------------------


class CountJob(object):
    """Counts an iterable a slice at a time: advance(budget_seconds) walks until the
    time is spent or the iterable ends. done, items, geometry, failed."""

    def __init__(self, iterable, has_geometry=None, clock=None):
        self.iterator = iter(iterable)
        self.has_geometry = has_geometry
        self.clock = clock or time.time
        self.items = 0
        self.geometry = 0
        self.done = False
        self.failed = False

    def advance(self, seconds=SLICE_SECONDS, chunk=CHUNK):
        if self.done:
            return True
        stop = self.clock() + seconds
        try:
            while True:
                for _ in range(chunk):
                    item = next(self.iterator)
                    self.items += 1
                    if self.has_geometry is not None and self.has_geometry(item):
                        self.geometry += 1
                if self.clock() >= stop:
                    return False
        except StopIteration:
            self.done = True
        except Exception:
            self.done = True
            self.failed = True
        return True


def cache_key(info, stale):
    """Counts are cached per model file and its time: '<key>|<cache mtime>'."""
    stamp = stale.get('cache_time') if stale else None
    return '%s|%s' % (info.get('key'), '' if stamp is None else '%.0f' % stamp)


# ---- WPF / API half -------------------------------------------------------------------------


def holder():
    from namo import session
    return session.holder(HOLDER)


def show_model(key):
    """Asks the pane to select a model (Link Navigator's 'Show in Source Files'):
    remembered until the pane builds, applied at once when it is attached."""
    held = holder()
    held.pending_select = key
    selector = getattr(held, 'select_model', None)
    if selector is not None:
        try:
            selector(key)
        except Exception:
            pass


def attach(pane, logger=None):
    """Builds the pane's content into the named elements of pane.xaml and wires it to
    the active document. Returns detach(). Safe to call again (Reload)."""
    from namo import ui
    held = holder()
    previous = getattr(held, 'detach', None)
    if previous is not None:
        try:
            previous()
        except Exception:
            pass
    view = PaneView(pane, logger or ui.pinned_logger())
    held.detach = view.detach
    held.select_model = view.select_key
    return view.detach


class PaneView(object):
    """The live pane. Built by attach(); everything it wires is undone by detach()."""

    def __init__(self, pane, logger):
        from namo import ui
        ui._wpf()
        self.pane = pane
        self.logger = logger
        self.find = pane.Find
        self.root = self.find('Root')
        self.rows_panel = self.find('Rows')
        self.status = self.find('Status')
        self.toolbar = self.find('Toolbar')
        self.colors = ui.palette()
        self.selection = Selection()
        self.infos = []
        self.stale = {}
        self.row_views = {}
        self.jobs = {}
        self.document = [None]
        self.detached = False
        self.last_hidden_refresh = 0.0
        self.counts = getattr(holder(), 'counts', None)
        if self.counts is None:
            self.counts = {}
            holder().counts = self.counts
        self._theme()
        self._toolbar()
        self.rebuild_later = ui.Debouncer(250, self._safe(self.rebuild, 'rebuild'))
        self.timer = None
        self._wire()
        self._safe(self.rebuild, 'first build')()

    # -- safety --

    def _safe(self, fn, label):
        from namo import ui
        return ui.safe(fn, 'Source Files: %s' % label, self.logger)

    def _guarded(self, label, action):
        """A toolbar action that never fails silently: what Navisworks refused is
        logged AND shown in a toast (a click that does nothing reads as broken)."""
        def run():
            try:
                action()
            except Exception as error:
                from namo import ui
                ui.log_error('Source Files: %s failed: %s' % (label, error), self.logger)
                self._toast('error', 'Could not finish %s' % label,
                            str(error) or type(error).__name__)
        return run

    # -- look --

    def _theme(self):
        from namo import ui
        c = self.colors
        self.root.Background = ui.brush(c['paper'])
        try:
            ui.apply_theme(self.root)       # themed check boxes, scroll bars, tooltips
        except Exception:
            pass
        rule = self.find('Rule')
        if rule is not None:
            rule.Background = ui.brush(c['line'])
        self.status.Foreground = ui.brush(c['muted'])

    def _toolbar(self):
        from namo import ui
        from System.Windows import Thickness
        self.buttons = {}
        specs = [('isolate', 'Isolate', 'quiet', 'Hide every other model and show the selected ones.'),
                 ('show', 'Show all', 'quiet', 'Show every model again (items hidden inside a model stay hidden).'),
                 ('select', 'Select', 'quiet', 'Select the selected models in the scene.'),
                 ('zoom', 'Zoom', 'quiet', 'Frame the selected models (double-click a row too).'),
                 ('folder', 'Open folder', 'quiet', 'Open the folder of the selected model in Explorer.'),
                 ('refresh', 'Refresh changed', 'quiet', 'Reload every model whose file changed on disk.'),
                 ('remove', 'Remove', 'danger', 'Remove the selected models from this document (Delete).')]
        actions = {'isolate': self.do_isolate, 'show': self.do_show_all, 'select': self.do_select,
                   'zoom': self.do_zoom, 'folder': self.do_folder, 'refresh': self.do_refresh,
                   'remove': self.do_remove}
        for key, label, kind, tip in specs:
            button = ui.button(label, self._guarded(label, actions[key]), kind, self.logger)
            button.ToolTip = tip
            button.Height = 28.0
            button.Padding = Thickness(8, 0, 8, 0)
            button.Margin = Thickness(0, 0, 4, 4)
            self.toolbar.Children.Add(button)
            self.buttons[key] = button

    def _enable(self):
        has_rows = bool(self.infos)
        has_selection = bool(self.selection.selected)
        for key in ('isolate', 'select', 'zoom', 'folder', 'remove'):
            self.buttons[key].IsEnabled = has_selection
        for key in ('show', 'refresh'):
            self.buttons[key].IsEnabled = has_rows

    # -- events --

    def _wire(self):
        from pynavis._api import Application
        from System import TimeSpan
        from System.Windows.Threading import DispatcherPriority, DispatcherTimer
        self.on_document_changed = self._safe(self._document_changed, 'document changed')
        self.on_models_changed = self._safe(lambda *a: self.rebuild_later.trigger(), 'models changed')
        self.on_key = self._safe(self._key, 'key')
        self.on_tick = self._safe(self._tick, 'tick')
        self.timer = DispatcherTimer(DispatcherPriority.Background)
        self.timer.Interval = TimeSpan.FromMilliseconds(TICK_MS)
        try:
            self.timer.Tick += self.on_tick
            self.root.PreviewKeyDown += self.on_key
            Application.ActiveDocumentChanged += self.on_document_changed
            self._subscribe(Application.ActiveDocument)
            self.timer.Start()
        except Exception:
            self.detach()
            raise

    def _subscribe(self, document):
        old = self.document[0]
        if old is document:
            return
        if old is not None:
            try:
                old.Models.CollectionChanged -= self.on_models_changed
            except Exception:
                pass
            try:
                old.FilesUpdated -= self.on_models_changed
            except Exception:
                pass
        self.document[0] = document
        if document is None:
            return
        document.Models.CollectionChanged += self.on_models_changed
        document.FilesUpdated += self.on_models_changed

    def _document_changed(self, sender, args):
        from pynavis._api import Application
        self._subscribe(Application.ActiveDocument)
        self.rebuild_later.trigger()

    def detach(self):
        """Removes every subscription and stops the timer, each step guarded so one
        failure cannot leave the others attached."""
        if self.detached:
            return
        self.detached = True

        def stop_timer():
            self.timer.Stop()
            self.timer.Tick -= self.on_tick

        def unhook_app():
            from pynavis._api import Application
            Application.ActiveDocumentChanged -= self.on_document_changed

        def unhook_keys():
            self.root.PreviewKeyDown -= self.on_key

        for step in (stop_timer, self.rebuild_later.cancel, unhook_app, unhook_keys,
                     lambda: self._subscribe(None)):
            try:
                step()
            except Exception:
                pass
        held = holder()
        if getattr(held, 'select_model', None) == self.select_key:
            held.select_model = None

    # -- data --

    def _doc(self):
        from pynavis._api import Application
        return Application.ActiveDocument

    def rebuild(self):
        """Reads the models and their files again and redraws every row."""
        from namo import modelmgmt
        document = self._doc()
        if document is not self.document[0]:
            self._subscribe(document)
        try:
            self.infos = modelmgmt.models_info(document) if document is not None else []
        except Exception:
            self.infos = []
        rows = modelmgmt.stale_rows(document, self.infos) if self.infos else []
        self.stale = dict((r['key'], r) for r in rows)
        self.selection.set_keys([i['key'] for i in self.infos])
        pending = getattr(holder(), 'pending_select', None)
        if pending is not None and pending in self.selection.keys:
            self.selection.select([pending])
            holder().pending_select = None
        live = set()
        for info in self.infos:
            ck = cache_key(info, self.stale.get(info['key']))
            live.add(ck)
            if ck not in self.counts and ck not in self.jobs:
                try:
                    self.jobs[ck] = CountJob(info['root'].DescendantsAndSelf)
                except Exception:
                    pass
        for ck in list(self.jobs):
            if ck not in live:
                del self.jobs[ck]
        self._draw()

    def _count_for(self, info):
        ck = cache_key(info, self.stale.get(info['key']))
        if ck in self.counts:
            return {'items': self.counts[ck], 'done': True}
        if ck in self.jobs:
            return {'items': self.jobs[ck].items, 'done': False}
        return None

    def _draw(self):
        self.rows_panel.Children.Clear()
        self.row_views = {}
        for info in self.infos:
            view = self._row(info)
            self.rows_panel.Children.Add(view['element'])
            self.row_views[info['key']] = view
        self._paint_selection()
        self._status()
        self._enable()

    def _status(self):
        rows = []
        from namo import modelmgmt
        for info in self.infos:
            stale = self.stale.get(info['key']) or {}
            rows.append({'status': stale.get('status'), 'hidden': modelmgmt.model_hidden(info)})
        self.status.Text = status_text(rows, counting=bool(self.jobs), no_document=self._doc() is None)

    def _row(self, info):
        from namo import modelmgmt, ui
        from System.Windows import (CornerRadius, GridLength, GridUnitType, HorizontalAlignment,
                                    TextTrimming, Thickness, VerticalAlignment)
        from System.Windows.Controls import Border, CheckBox, ColumnDefinition, Grid, StackPanel, TextBlock
        from System.Windows.Input import Cursors
        c = self.colors
        texts = row_texts(info, self.stale.get(info['key']), self._count_for(info))
        border = Border()
        border.BorderBrush = ui.brush(c['line'])
        border.BorderThickness = Thickness(0, 0, 0, 1)
        border.MinHeight = 44.0
        border.ToolTip = texts['tooltip'] or None
        grid = Grid()
        for width in (3.0, 34.0, None, -1.0):
            column = ColumnDefinition()
            if width is None:
                column.Width = GridLength(1.0, GridUnitType.Star)
            elif width < 0:
                column.Width = GridLength.Auto
            else:
                column.Width = GridLength(width)
            grid.ColumnDefinitions.Add(column)
        rail = Border()
        Grid.SetColumn(rail, 0)
        grid.Children.Add(rail)
        box = CheckBox()
        box.IsChecked = not modelmgmt.model_hidden(info)
        box.VerticalAlignment = VerticalAlignment.Center
        box.HorizontalAlignment = HorizontalAlignment.Center
        box.ToolTip = 'Show or hide this model'
        key = info['key']
        box.Click += self._safe(lambda sender, args: self.toggle_visible([key], bool(sender.IsChecked)),
                                'visibility')
        Grid.SetColumn(box, 1)
        grid.Children.Add(box)
        stack = StackPanel()
        stack.VerticalAlignment = VerticalAlignment.Center
        stack.Margin = Thickness(0, 4, 8, 4)
        name = TextBlock()
        name.Text = texts['name']
        name.FontSize = 13.0
        name.Foreground = ui.brush(c['ink'])
        name.TextTrimming = TextTrimming.CharacterEllipsis
        detail = TextBlock()
        detail.Text = texts['detail']
        detail.FontSize = 11.5
        detail.Foreground = ui.brush(c['muted'])
        detail.TextTrimming = TextTrimming.CharacterEllipsis
        stack.Children.Add(name)
        stack.Children.Add(detail)
        Grid.SetColumn(stack, 2)
        grid.Children.Add(stack)
        tag = None
        if texts['tag']:
            color = c['warning'] if texts['tag_level'] == 'warn' else c['error']
            tag = Border()
            tag.CornerRadius = CornerRadius(4)
            tag.BorderBrush = ui.brush(color)
            tag.BorderThickness = Thickness(1)
            tag.Padding = Thickness(6, 0, 6, 1)
            tag.Margin = Thickness(0, 0, 10, 0)
            tag.VerticalAlignment = VerticalAlignment.Center
            label = TextBlock()
            label.Text = texts['tag']
            label.FontSize = 11.5
            label.Foreground = ui.brush(color)
            tag.Child = label
            Grid.SetColumn(tag, 3)
            grid.Children.Add(tag)
        border.Child = grid
        border.Cursor = Cursors.Arrow
        border.MouseLeftButtonDown += self._safe(lambda sender, args: self._row_click(key, args), 'row click')
        return {'element': border, 'rail': rail, 'box': box, 'detail': detail, 'name': name, 'tag': tag}

    def _paint_selection(self):
        from namo import ui
        from System.Windows.Media import Brushes
        c = self.colors
        for key, view in self.row_views.items():
            on = key in self.selection.selected
            view['element'].Background = ui.brush(c['selection']) if on else Brushes.Transparent
            view['rail'].Background = ui.brush(c['accent']) if on else Brushes.Transparent
        self._enable()

    def _row_click(self, key, args):
        from System.Windows.Input import Keyboard, ModifierKeys
        modifiers = Keyboard.Modifiers
        ctrl = (modifiers & ModifierKeys.Control) == ModifierKeys.Control
        shift = (modifiers & ModifierKeys.Shift) == ModifierKeys.Shift
        try:
            clicks = int(args.ClickCount)
        except Exception:
            clicks = 1
        self.selection.click(key, ctrl, shift)
        self._paint_selection()
        try:
            self.root.Focus()
        except Exception:
            pass
        if clicks >= 2:
            self._guarded('Zoom', self.do_zoom)()

    def select_key(self, key):
        """Selects one model's row (Link Navigator) and brings it into view."""
        if key not in self.selection.keys:
            holder().pending_select = key
            self.rebuild_later.trigger()
            return
        self.selection.select([key])
        holder().pending_select = None
        self._paint_selection()
        view = self.row_views.get(key)
        if view is not None:
            try:
                view['element'].BringIntoView()
            except Exception:
                pass

    def _key(self, sender, args):
        from System.Windows.Input import Key, Keyboard, ModifierKeys
        modifiers = Keyboard.Modifiers
        shift = (modifiers & ModifierKeys.Shift) == ModifierKeys.Shift
        ctrl = (modifiers & ModifierKeys.Control) == ModifierKeys.Control
        if args.Key in (Key.Up, Key.Down):
            self.selection.move(-1 if args.Key == Key.Up else 1, extend=shift)
            self._paint_selection()
            view = self.row_views.get(self.selection.anchor)
            if view is not None:
                view['element'].BringIntoView()
            args.Handled = True
        elif args.Key == Key.Space and self.selection.selected:
            keys = self.selection.ordered()
            infos = [i for i in self.infos if i['key'] in set(keys)]
            from namo import modelmgmt
            visible_now = any(not modelmgmt.model_hidden(i) for i in infos)
            self.toggle_visible(keys, not visible_now)
            args.Handled = True
        elif args.Key == Key.Delete and self.selection.selected:
            self._guarded('Remove', self.do_remove)()
            args.Handled = True
        elif args.Key == Key.Enter and self.selection.selected:
            self._guarded('Zoom', self.do_zoom)()
            args.Handled = True
        elif args.Key == Key.A and ctrl:
            self.selection.select_all()
            self._paint_selection()
            args.Handled = True

    def _tick(self, sender, args):
        try:
            if not self.pane.Visible:
                return
        except Exception:
            return
        now = time.time()
        if now - self.last_hidden_refresh > HIDDEN_REFRESH_SECONDS:
            self.last_hidden_refresh = now
            self._refresh_hidden()
        if self.jobs:
            self._advance_counts()

    def _refresh_hidden(self):
        from namo import modelmgmt
        changed = False
        for info in self.infos:
            view = self.row_views.get(info['key'])
            if view is None:
                continue
            visible = not modelmgmt.model_hidden(info)
            if bool(view['box'].IsChecked) != visible:
                view['box'].IsChecked = visible
                changed = True
        if changed:
            self._status()

    def _advance_counts(self):
        stop = time.time() + SLICE_SECONDS
        for ck in sorted(self.jobs):
            job = self.jobs[ck]
            finished = job.advance(max(0.005, stop - time.time()))
            if finished:
                del self.jobs[ck]
                if not job.failed:
                    self.counts[ck] = job.items
            self._update_detail(ck)
            if time.time() >= stop:
                break
        if not self.jobs:
            self._status()

    def _update_detail(self, ck):
        for info in self.infos:
            if cache_key(info, self.stale.get(info['key'])) == ck:
                view = self.row_views.get(info['key'])
                if view is not None:
                    texts = row_texts(info, self.stale.get(info['key']), self._count_for(info))
                    view['detail'].Text = texts['detail']
                return

    # -- actions --

    def _selected(self):
        return self.selection.ordered()

    def _toast(self, level, message, detail=None):
        try:
            from pynavis import toast
            toast.show(level, message, detail)
        except Exception:
            pass

    def toggle_visible(self, keys, visible):
        from namo import modelmgmt
        try:
            count = modelmgmt.set_models_hidden(keys, not visible, self._doc())
        except Exception as error:
            self._refresh_hidden()          # put the boxes back to what the model says
            self._toast('error', 'Could not %s the model' % ('show' if visible else 'hide'),
                        str(error) or type(error).__name__)
            return 0
        for key in keys:
            view = self.row_views.get(key)
            if view is not None:
                view['box'].IsChecked = bool(visible)
        self._status()
        return count

    def do_isolate(self):
        from namo import modelmgmt
        keys = self._selected()
        if not keys:
            return
        shown = modelmgmt.isolate_models(keys, self._doc())
        self._refresh_hidden()
        self._toast('success', 'Isolated %s' % modelmgmt.plural(shown, 'model'))

    def do_show_all(self):
        from namo import modelmgmt
        count = modelmgmt.show_all_models(self._doc())
        self._refresh_hidden()
        self._toast('success', 'Showing all %s' % modelmgmt.plural(count, 'model'),
                    'Items hidden inside a model stay hidden.')

    def do_select(self):
        from namo import modelmgmt
        keys = self._selected()
        if not keys:
            return
        modelmgmt.select_models(keys, self._doc())
        self._toast('success', 'Selected %s' % modelmgmt.plural(len(keys), 'model'))

    def do_zoom(self):
        from namo import modelmgmt
        keys = self._selected()
        if not keys:
            return
        if not modelmgmt.zoom_models(keys, self._doc()):
            self._toast('info', 'Nothing to frame', 'The selected models have no visible extent.')

    def do_folder(self):
        from namo import modelmgmt, ui
        keys = self._selected()
        infos = [i for i in self.infos if i['key'] in set(keys)]
        if not infos:
            return
        target = modelmgmt.model_folder(infos[0])
        if not target:
            self._toast('warning', 'Folder not found',
                        'Neither %s nor its source file is on this computer.' % infos[0]['name'])
            return
        ui.show_in_explorer(target)

    def do_refresh(self):
        from namo import modelmgmt
        before = [r for r in self.stale.values() if r.get('status') == 'Out of date']
        changed = modelmgmt.refresh_files(self._doc())
        self.rebuild()
        if changed:
            self._toast('success', 'Reloaded the changed models',
                        modelmgmt.join_names([r['name'] for r in before]) if before else None)
        else:
            self._toast('info', 'No model files changed', 'Every model is as new as its file.')

    def do_remove(self):
        from pynavis import forms
        from namo import modelmgmt
        keys = self._selected()
        infos = [i for i in self.infos if i['key'] in set(keys)]
        if not infos:
            return
        names = [i['name'] for i in infos]
        question = ('Remove %s from this document?\n\n%s\n\nSave first if you may want %s back.'
                    % (modelmgmt.plural(len(infos), 'model'), '\n'.join(names[:12]),
                       'it' if len(infos) == 1 else 'them'))
        if not forms.confirm(question, 'Source Files'):
            return
        removed, failed = modelmgmt.remove_models(keys, self._doc())
        self.rebuild()
        if failed:
            self._toast('warning', 'Removed %d, %d failed' % (len(removed), len(failed)),
                        'Could not remove %s.' % modelmgmt.join_names(failed))
        else:
            self._toast('success', 'Removed %s' % modelmgmt.plural(len(removed), 'model'),
                        modelmgmt.join_names(removed))

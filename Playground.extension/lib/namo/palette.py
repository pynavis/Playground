# -*- coding: utf-8 -*-
"""Command Palette: type a few letters, press Enter, the command runs.

Lists every pyNavis button of every extension (title, tab > panel, shortcut), dock
panels and url/link buttons, every native Navisworks ribbon command (via AdWindows),
saved viewpoints ("Go to view: ...") and selection sets ("Select set: ..."). Recently
used entries come first (MRU in the local global store 'palette-mru').

Enter closes the window and then runs the entry: pyNavis bundles and native commands
are deferred through namo.ribbon until the palette's own run released the RunGate;
views and sets are applied at once. A button the ribbon has greyed out (its context:
rule is false) is listed but refused, with the reason in the status line.

Pure half: entry builders, Ranker (title matches first, then path and tooltip,
plus an MRU bonus), display rows, status text, blocked(). API half: gather(), run(),
the window.
"""
import time

from namo import camera, macros, ribbon, session, store, textmatch, ui

MRU_STORE = 'palette-mru'
MRU_LIMIT = 40
SHOWN = 100
MAX_VIEWS = 5000
MAX_SETS = 5000
TITLE_BONUS = 20.0
MRU_BONUS = 30.0
OTHER_WEIGHT = 0.6
BLOCKED_PENALTY = 15.0

# ---- entries ------------------------------------------------------------------------------


def entry_id(entry):
    """The MRU identity of an entry."""
    kind = entry.get('kind')
    if kind == 'bundle':
        return ('bundle|%s|%s' % (entry.get('extension', ''), ribbon.normalize_key(entry['key']))).lower()
    if kind in ('view', 'set'):
        return ('%s|%s' % (kind, entry.get('target', ''))).lower()
    return ('%s|%s' % (kind, entry.get('key', ''))).lower()


def from_command(command):
    """A palette entry from a namo.ribbon command dict."""
    entry = dict(command)
    kind = command.get('kind')
    if kind == 'native':
        entry['detail'] = ribbon.command_path('Navisworks', command.get('path'))
    elif kind == 'bundle' and command.get('hidden'):
        entry['detail'] = ribbon.command_path(command.get('path'), 'shortcut only')
    else:
        entry['detail'] = command.get('path') or ''
    entry['id'] = entry_id(entry)
    return entry


def view_entries(views, limit=MAX_VIEWS):
    """Entries for saved viewpoints: views [(folder_path 'A/B', name)] in tree order."""
    out = []
    for folder, name in views[:limit]:
        target = macros.view_path(folder, name)
        where = ribbon.command_path('Saved viewpoints', *(folder.split('/') if folder else []))
        entry = {'kind': 'view', 'key': 'view:' + target, 'target': target, 'name': name,
                 'title': 'Go to view: %s' % name, 'detail': where, 'path': where, 'tooltip': '',
                 'shortcut': '', 'enabled': True, 'context': '', 'extension': 'Navisworks'}
        entry['id'] = entry_id(entry)
        out.append(entry)
    return out


def set_path(segments):
    """A pynavis.sets.find path: literal '/' in a name written '\\/'."""
    return '/'.join(s.replace('/', '\\/') for s in segments)


def set_entries(rows, limit=MAX_SETS):
    """Entries for selection sets from pynavis.sets.snapshot rows (folders skipped)."""
    out = []
    names_by_key = {}
    for row in rows:
        names_by_key[row['key']] = row['name']
        if row.get('is_folder'):
            continue
        segments = []
        parent = row.get('parent_key') or ''
        while parent:
            segments.insert(0, names_by_key.get(parent, ''))
            parent = parent.rsplit('/', 1)[0] if '/' in parent else ''
        target = set_path(segments + [row['name']])
        where = ribbon.command_path('Selection sets', *segments)
        entry = {'kind': 'set', 'key': 'set:' + target, 'target': target, 'name': row['name'],
                 'title': 'Select set: %s' % row['name'], 'detail': where, 'path': where,
                 'tooltip': '', 'shortcut': '', 'enabled': True, 'context': '',
                 'extension': 'Navisworks', 'guid': row.get('guid')}
        entry['id'] = entry_id(entry)
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def blocked(entry):
    """Why an entry cannot run now (a sentence), or None."""
    if entry.get('enabled', True):
        return None
    needs = ribbon.needs_text(entry.get('context'))
    if needs:
        return '%s needs %s.' % (entry['title'], needs)
    return '%s is not available right now.' % entry['title']


def search_text(entry):
    return ' '.join(t for t in (entry.get('title'), entry.get('detail'), entry.get('tooltip'),
                                entry.get('shortcut')) if t)


class Ranker(object):
    """Ranks entries for a query: a title match beats a path or tooltip match, recently
    used entries get a bonus, greyed-out ones sink a little. Texts are lowercased once."""

    def __init__(self, entries, mru=None):
        self.entries = list(entries)
        self.indices = list(range(len(self.entries)))
        self.titles = textmatch.Index(self.indices, lambda i: self.entries[i].get('title') or '')
        self.full = textmatch.Index(self.indices, lambda i: search_text(self.entries[i]))
        self.set_mru(mru)

    def set_mru(self, mru):
        self.mru = [m for m in (mru or []) if isinstance(m, str)]
        size = max(1, len(self.mru))
        self.bonus = {}
        for position, item in enumerate(self.mru):
            self.bonus.setdefault(item.lower(), MRU_BONUS * (1.0 - float(position) / size))

    def rank(self, query, limit=SHOWN):
        """(total matches, [entry index]) best first."""
        words = (query or '').split()
        if not words:
            order = []
            seen = set()
            by_id = {}
            for index, entry in enumerate(self.entries):
                by_id.setdefault(entry.get('id'), index)
            for item in self.mru:
                index = by_id.get(item.lower())
                if index is not None and index not in seen:
                    order.append(index)
                    seen.add(index)
            for index in self.indices:
                if index not in seen:
                    order.append(index)
            return len(order), (order[:limit] if limit else order)
        scores = {}
        for score, index in self.titles.rank(query, limit=0):
            scores[index] = score + TITLE_BONUS
        for score, index in self.full.rank(query, limit=0):
            if index not in scores:
                scores[index] = score * OTHER_WEIGHT
        ranked = []
        for index, score in scores.items():
            entry = self.entries[index]
            score += self.bonus.get(entry.get('id') or '', 0.0)
            if not entry.get('enabled', True):
                score -= BLOCKED_PENALTY
            ranked.append((-score, index))
        ranked.sort()
        order = [index for _neg, index in ranked]
        return len(order), (order[:limit] if limit else order)


def display(entry, query):
    """{'title', 'title_spans', 'detail', 'detail_spans', 'shortcut', 'muted'} for a row."""
    title = entry.get('title') or ''
    detail = entry.get('detail') or ''
    reason = None
    if not entry.get('enabled', True):
        needs = ribbon.needs_text(entry.get('context'))
        reason = ('needs %s' % needs) if needs else 'not available now'
        detail = '%s, %s' % (detail, reason) if detail else reason
    return {'title': title, 'title_spans': textmatch.spans(query, title) if query else [],
            'detail': detail, 'detail_spans': textmatch.spans(query, detail) if query else [],
            'shortcut': entry.get('shortcut') or '', 'muted': reason is not None}


def pieces(text, spans):
    """[(text, highlighted)] runs of text cut at the spans."""
    out = []
    at = 0
    for start, end in sorted(spans or []):
        start, end = max(start, at), min(end, len(text))
        if start >= end:
            continue
        if start > at:
            out.append((text[at:start], False))
        out.append((text[start:end], True))
        at = end
    if at < len(text):
        out.append((text[at:], False))
    return out or [(text, False)]


def status_text(total_entries, matches, shown, query):
    if not (query or '').strip():
        return '%s commands, views and sets' % '{:,}'.format(total_entries)
    if not matches:
        return 'No matches'
    if matches > shown:
        return '%s matches, showing the best %s' % ('{:,}'.format(matches), '{:,}'.format(shown))
    return '%s %s' % ('{:,}'.format(matches), 'match' if matches == 1 else 'matches')


# ---- MRU ------------------------------------------------------------------------------------


def mru_store():
    return store.Store(MRU_STORE, scope='global', mode='local')


def load_mru():
    value = mru_store().load([])
    return [m for m in value if isinstance(m, str)] if isinstance(value, list) else []


def remember(entry):
    try:
        mru_store().update(lambda current: ribbon.mru_push(current if isinstance(current, list) else [],
                                                           entry['id'], MRU_LIMIT), [])
    except Exception as error:
        session.log('warning', 'palette: could not save recent commands: %s' % error)


# ==================================================================================
# API half
# ==================================================================================


def gather(doc=None):
    """Every entry for the live session, in kind order (bundles, panels and links,
    native commands, views, sets). Returns (entries, notes)."""
    notes = []
    entries = [from_command(c) for c in ribbon.buttons()]
    entries += [from_command(c) for c in ribbon.other_items()]
    entries += [from_command(c) for c in ribbon.native_commands()]
    try:
        views = camera.saved_views(doc)
        entries += view_entries([(folder, str(saved.DisplayName)) for folder, saved in views])
        if len(views) > MAX_VIEWS:
            notes.append('Showing the first %s saved viewpoints.' % '{:,}'.format(MAX_VIEWS))
    except Exception as error:
        session.log('info', 'palette: no saved viewpoints listed: %s' % error)
    try:
        from pynavis import sets
        rows = sets.snapshot(doc)
        entries += set_entries(rows)
    except Exception as error:
        session.log('info', 'palette: no selection sets listed: %s' % error)
    return entries, notes


def _timeout_only(job):
    if job.state == 'timeout':
        busy = ribbon.gate_title()
        _toast('info', 'Could not start %s' % job.label,
               ('%s is still running.' % busy) if busy else 'Something else is still running.')


def _native_done(job):
    if job.state == 'timeout':
        _timeout_only(job)
    elif not job.ok and job.message:
        _toast('info', job.message)


def _toast(level, message, detail=None):
    try:
        from pynavis import toast
        toast.show(level, message, detail)
    except Exception:
        session.log('info', '%s %s' % (message, detail or ''))


def run(entry, doc=None):
    """Runs an entry (after the palette closed). Returns a short outcome text."""
    kind = entry.get('kind')
    remember(entry)
    if kind == 'bundle':
        model = entry.get('model')
        ribbon.run_bundle(model if model is not None else entry['key'], entry.get('extension') or None,
                          on_done=_timeout_only)
        return 'deferred'
    macros.record_entry(entry)
    if kind == 'native':
        ribbon.run_native(entry, on_done=_native_done)
        return 'deferred'
    if kind == 'view':
        saved = macros.find_saved_view(entry['target'], doc)
        if saved is None:
            _toast('warning', 'That viewpoint is gone', entry['target'])
            return 'missing'
        camera.recall(saved, doc)
        _toast('success', 'Showing %s' % entry.get('name'))
        return 'done'
    if kind == 'set':
        from pynavis import sets
        found = macros.find_selection_set(entry['target'], doc)
        if found is None:
            _toast('warning', 'That selection set is gone', entry['target'])
            return 'missing'
        items = sets.items_of(found, doc)
        sets.select(items, doc)
        count = int(items.Count)
        _toast('success' if count else 'info', 'Selected %s' % entry.get('name'),
               '%s item%s' % ('{:,}'.format(count), '' if count == 1 else 's') if count
               else 'The set matches nothing in this model.')
        return 'done'
    if kind == 'pane':
        ok, message = ribbon.toggle_pane(entry['key'])
        if not ok:
            _toast('warning', 'Could not open %s' % entry['title'], message)
        return 'done' if ok else 'failed'
    if kind == 'url':
        if not ribbon.open_url(entry.get('url')):
            _toast('warning', 'Could not open the link', entry.get('url'))
        return 'done'
    if kind == 'link':
        plugin = entry.get('plugin')
        job = ribbon.Job(entry['title'], ribbon.gate_held, lambda: ribbon.run_link(plugin),
                         outcome=lambda result: result, on_done=_native_done)
        ribbon.schedule(job)
        return 'deferred'
    return 'unknown'


# ---- window ------------------------------------------------------------------------------

_ITEM_STYLE = r'''
<Style xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
       xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="ListBoxItem">
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ListBoxItem">
        <Grid Background="Transparent">
          <Border x:Name="Wash" Background="Transparent"/>
          <Border x:Name="Rail" Width="3" HorizontalAlignment="Left" Background="Transparent"/>
          <ContentPresenter Margin="12,5,12,5"/>
        </Grid>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="Wash" Property="Background" Value="%(surface)s"/>
          </Trigger>
          <Trigger Property="IsSelected" Value="True">
            <Setter TargetName="Wash" Property="Background" Value="%(selection)s"/>
            <Setter TargetName="Rail" Property="Background" Value="%(accent)s"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>
'''


def _rich(text, spans, size, muted, colors):
    from System.Windows import FontWeights, TextTrimming, TextWrapping
    from System.Windows.Documents import Run
    block = ui.text('', size=size, muted=muted, wrap=False)
    block.TextWrapping = TextWrapping.NoWrap
    block.TextTrimming = TextTrimming.CharacterEllipsis
    for piece, hit in pieces(text, spans):
        run_ = Run(piece)
        if hit:
            run_.FontWeight = FontWeights.SemiBold
            run_.Foreground = ui.brush(colors['ink'] if not muted else colors['muted'])
        block.Inlines.Add(run_)
    return block


def _row_visual(shown, colors):
    from System.Windows import GridLength, GridUnitType, VerticalAlignment
    from System.Windows.Controls import ColumnDefinition, Grid, StackPanel
    grid = Grid()
    for width in ('star', 'auto'):
        column = ColumnDefinition()
        column.Width = GridLength(1, GridUnitType.Star) if width == 'star' else GridLength.Auto
        grid.ColumnDefinitions.Add(column)
    stack = StackPanel()
    stack.Children.Add(_rich(shown['title'], shown['title_spans'], 13, shown['muted'], colors))
    if shown['detail']:
        stack.Children.Add(_rich(shown['detail'], shown['detail_spans'], 12, True, colors))
    Grid.SetColumn(stack, 0)
    grid.Children.Add(stack)
    if shown['shortcut']:
        chord = ui.text(shown['shortcut'], size=12, muted=True, wrap=False)
        chord.Margin = ui.thickness(16, 0, 0, 0)
        chord.VerticalAlignment = VerticalAlignment.Center
        Grid.SetColumn(chord, 1)
        grid.Children.Add(chord)
    return grid


class PaletteState(object):
    """window.Tag: result is the chosen entry once Enter ran one."""

    def __init__(self, win, ranker):
        self.window = win
        self.ranker = ranker
        self.shown = []
        self.matches = 0
        self.query = ''
        self.result = None

    def run_query(self, query):
        self.query = query or ''
        self.matches, self.shown = self.ranker.rank(self.query, SHOWN)
        return self.matches

    def choose(self, index):
        """Picks shown[index]; returns None when accepted, else the refusal sentence."""
        if not (0 <= index < len(self.shown)):
            return 'Nothing to run.'
        entry = self.ranker.entries[self.shown[index]]
        reason = blocked(entry)
        if reason:
            return reason
        self.result = entry
        ui.close_with(self.window, True)
        return None


def build_window(entries, mru=None, query='', notes=None):
    """The palette, unshown (window.Tag is a PaletteState)."""
    ui.load_wpf()
    from System.Windows import GridLength, GridUnitType
    from System.Windows.Controls import (Dock, DockPanel, Grid, ListBox, RowDefinition,
                                         ScrollBarVisibility, ScrollViewer)
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    from System.Windows.Markup import XamlReader
    logger = ui.pinned_logger()
    colors = ui.palette()
    win = ui.window('Command Palette', width=700, height=560, min_width=480, min_height=320)
    ranker = Ranker(entries, mru)
    state = PaletteState(win, ranker)
    win.Tag = state

    listing = ListBox()
    listing.BorderThickness = ui.thickness(0)
    listing.Background = ui.brush(colors['paper'])
    listing.ItemContainerStyle = XamlReader.Parse(_ITEM_STYLE % colors)
    ScrollViewer.SetHorizontalScrollBarVisibility(listing, ScrollBarVisibility.Disabled)
    status = ui.hint('')
    base_status = {'text': ''}

    def refresh(text):
        state.run_query(text)
        listing.Items.Clear()
        for index in state.shown:
            listing.Items.Add(_row_visual(display(ranker.entries[index], state.query), colors))
        if listing.Items.Count:
            listing.SelectedIndex = 0
            listing.ScrollIntoView(listing.Items[0])
        base_status['text'] = status_text(len(ranker.entries), state.matches, len(state.shown), state.query)
        if notes and not state.query:
            base_status['text'] += '. ' + ' '.join(notes)
        status.Text = base_status['text']
        run_button.IsEnabled = bool(state.shown)

    search, box = ui.search_box('Type a command, a view or a set', lambda text: refresh(text), delay_ms=60)

    def accept():
        if state.query != box.Text:
            refresh(box.Text)
        problem = state.choose(listing.SelectedIndex)
        if problem:
            status.Text = problem

    def move(delta, absolute=None):
        count = listing.Items.Count
        if not count:
            return
        position = absolute if absolute is not None else listing.SelectedIndex + delta
        position = max(0, min(count - 1, position))
        listing.SelectedIndex = position
        listing.ScrollIntoView(listing.Items[position])
        status.Text = base_status['text']

    def keys(sender, args):
        key = args.Key
        ctrl = Keyboard.Modifiers == ModifierKeys.Control
        if key == Key.Down:
            move(1)
        elif key == Key.Up:
            move(-1)
        elif key == Key.PageDown:
            move(8)
        elif key == Key.PageUp:
            move(-8)
        elif key == Key.Home and ctrl:
            move(0, 0)
        elif key == Key.End and ctrl:
            move(0, listing.Items.Count - 1)
        elif key in (Key.Enter, Key.Return):
            accept()
        elif key == Key.Escape:
            ui.close_with(win, False)
        else:
            return
        args.Handled = True
    win.PreviewKeyDown += ui.safe(keys, 'palette keys', logger)
    listing.MouseDoubleClick += ui.safe(lambda s, e: accept(), 'palette open', logger)

    root = Grid()
    root.Margin = ui.thickness(16, 16, 16, 8)
    for size in ('auto', 'auto', 'star'):
        definition = RowDefinition()
        definition.Height = GridLength(1, GridUnitType.Star) if size == 'star' else GridLength.Auto
        root.RowDefinitions.Add(definition)
    Grid.SetRow(search, 0)
    root.Children.Add(search)
    status.Margin = ui.thickness(2, 6, 0, 8)
    Grid.SetRow(status, 1)
    root.Children.Add(status)
    Grid.SetRow(listing, 2)
    root.Children.Add(listing)

    hint = ui.hint('Enter runs, arrows move, Esc closes')
    run_button = ui.button('Run', accept, 'primary', logger)
    close_button = ui.button('Close', lambda: ui.close_with(win, False), 'secondary', logger)
    close_button.IsCancel = True
    bottom = ui.footer([run_button, close_button], left=hint, padding=16)
    layout = DockPanel()
    DockPanel.SetDock(bottom, Dock.Bottom)
    layout.Children.Add(bottom)
    layout.Children.Add(root)
    win.Content = layout

    def first_focus(sender, args):
        box.Focus()
        box.SelectAll()
    win.ContentRendered += ui.safe(first_focus, 'palette focus', logger)
    if query:
        box.Text = query
    refresh(query)
    state.refresh = refresh
    state.box = box
    state.listing = listing
    state.status = status
    state.accept = accept
    state.move = move
    return win


def dialog(entries, mru=None, notes=None):
    """Shows the palette; returns the chosen entry or None."""
    win = build_window(entries, mru, '', notes)
    ui.show_modal(win)
    return win.Tag.result


def open_palette(doc=None):
    """The whole Command Palette click: gather, show, run. Returns the outcome text or None."""
    started = time.time()
    entries, notes = gather(doc)
    session.log('debug', 'palette: %d entries in %.2f s' % (len(entries), time.time() - started))
    chosen = dialog(entries, load_mru(), notes)
    if chosen is None:
        return None
    return run(chosen, doc)

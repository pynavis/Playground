# -*- coding: utf-8 -*-
"""Meeting Mode: walk a coordination meeting through the chosen issues and write minutes.

The window is modeless (Navisworks stays usable): issue N of M with its details and
snapshot, big Previous / Next, one-click status buttons, a decision box (each decision
becomes a comment 'Meeting 2026-10-05: ...'), assignee and due edits, Take screenshot,
Mark discussed. Moving to an issue restores its view and selects its elements (Follow
in view, on by default). Every change is saved to the register at once, so nothing is
lost if Navisworks closes mid-meeting; the meeting log (what was discussed and changed)
lives in a session holder until the minutes are written.

End meeting (or closing the window after anything happened) writes the minutes, an
HTML page (namo.htmlreport) and a workbook (namo.xlsx), into the model's folder (else
Documents) and opens the page.

Pure half (filters, log, minutes rows, minutes files) first and unit tested; the window
after.
"""

import copy
import datetime
import os

HOLDER = 'issue_meeting'
WINDOW_KEY = 'playground-issue-meeting'
DEFAULTS = {'statuses': ['Open', 'In progress'], 'trades': [], 'priorities': [], 'due': 'any',
            'order': 'priority', 'follow': True}
DUE_CHOICES = [('Any due date', 'any'), ('Overdue only', 'overdue'),
               ('Overdue or due within 7 days', 'soon'), ('No due date', 'none')]
ORDERS = [('Most urgent first', 'priority'), ('Earliest due first', 'due'), ('By number', 'id'),
          ('By trade', 'trade')]


def _text(value):
    return '' if value is None else (u'%s' % (value,)).strip()


# ---- pure: choosing issues ------------------------------------------------------------------


def filter_fields(rows, saved=None):
    """ui.form fields for the meeting filter, defaults from the last meeting."""
    from namo import issues
    saved = dict(DEFAULTS, **(saved or {}))
    trades = issues.distinct(rows, 'trade', blank=issues.NO_TRADE)
    return [
        {'kind': 'multi', 'key': 'statuses', 'label': 'Status', 'options': issues.STATUSES,
         'default': [s for s in saved['statuses'] if s in issues.STATUSES]},
        {'kind': 'multi', 'key': 'trades', 'label': 'Trades (none ticked: every trade)',
         'options': trades, 'default': [t for t in saved['trades'] if t in trades]},
        {'kind': 'multi', 'key': 'priorities', 'label': 'Priority (none ticked: every priority)',
         'options': issues.URGENCY, 'default': [p for p in saved['priorities'] if p in issues.URGENCY]},
        {'kind': 'choice', 'key': 'due', 'label': 'Due', 'options': DUE_CHOICES, 'default': saved['due'], 'fallback': None},
        {'kind': 'choice', 'key': 'order', 'label': 'Order', 'options': ORDERS, 'default': saved['order'], 'fallback': None},
        {'kind': 'check', 'key': 'follow', 'label': 'Go to each issue in the view as the meeting moves',
         'default': bool(saved['follow'])},
    ]


def choose(rows, options, today=None):
    """The issues for the meeting, in meeting order (pure)."""
    from namo import issues
    options = dict(DEFAULTS, **(options or {}))
    found = issues.filter_issues(rows, status=options['statuses'] or None,
                                 trade=options['trades'] or None,
                                 priority=options['priorities'] or None,
                                 due=None if options['due'] == 'any' else options['due'], today=today)
    order = options.get('order') or 'priority'
    if order == 'priority':
        return issues.sort_issues(found)
    return issues.sort_issues(found, order)


# ---- pure: the meeting log -----------------------------------------------------------------


def new_log(ids, user='', now=None, doc_name=''):
    """A fresh meeting log for these issue ids."""
    from namo import issues
    return {'started': issues.stamp(now), 'ended': '', 'user': user, 'doc': doc_name,
            'ids': list(ids), 'position': 0, 'entries': {}, 'events': []}


def _entry(log, issue_id):
    entry = log['entries'].get(issue_id)
    if entry is None:
        entry = {'discussed': False, 'decisions': [], 'status': None, 'assignee': None,
                 'due': None, 'screenshots': 0, 'visited': False}
        log['entries'][issue_id] = entry
    return entry


def record(log, issue_id, kind, before=None, after=None, text='', now=None):
    """Adds one event: kind 'visit' | 'discussed' | 'decision' | 'status' | 'assignee' |
    'due' | 'screenshot'. Status/assignee/due keep the FIRST before and LAST after so
    the minutes show the net change. Returns the log."""
    from namo import issues
    entry = _entry(log, issue_id)
    if kind == 'visit':
        entry['visited'] = True
        return log
    log['events'].append({'time': issues.stamp(now), 'issue': issue_id, 'kind': kind,
                          'before': _text(before), 'after': _text(after), 'text': _text(text)})
    if kind == 'discussed':
        entry['discussed'] = True
    elif kind == 'decision':
        entry['decisions'].append(_text(text))
        entry['discussed'] = True
    elif kind in ('status', 'assignee', 'due'):
        current = entry[kind]
        entry[kind] = (current[0] if current else _text(before), _text(after))
        entry['discussed'] = True
    elif kind == 'screenshot':
        entry['screenshots'] += 1
    return log


def has_activity(log):
    """True when anything worth minutes happened."""
    return bool(log.get('events'))


def step(log, delta):
    """Moves the position by delta (clamped). Returns the new position."""
    count = len(log['ids'])
    if not count:
        return 0
    log['position'] = max(0, min(count - 1, log['position'] + delta))
    return log['position']


def counts(log):
    """{'issues', 'discussed', 'decisions', 'status_changes', 'reassigned', 'new_due',
    'screenshots'}."""
    entries = log['entries']
    out = {'issues': len(log['ids']), 'discussed': 0, 'decisions': 0, 'status_changes': 0,
           'reassigned': 0, 'new_due': 0, 'screenshots': 0}
    for issue_id in log['ids']:
        entry = entries.get(issue_id)
        if entry is None:
            continue
        out['discussed'] += 1 if entry['discussed'] else 0
        out['decisions'] += len(entry['decisions'])
        out['status_changes'] += 1 if entry['status'] and entry['status'][0] != entry['status'][1] else 0
        out['reassigned'] += 1 if entry['assignee'] and entry['assignee'][0] != entry['assignee'][1] else 0
        out['new_due'] += 1 if entry['due'] and entry['due'][0] != entry['due'][1] else 0
        out['screenshots'] += entry['screenshots']
    return out


def _change(pair):
    if not pair or pair[0] == pair[1]:
        return ''
    return '%s > %s' % (pair[0] or 'none', pair[1] or 'none')


def minutes_rows(log, by_id):
    """One row per issue in the meeting: [id, title, status now, status change, decisions,
    assignee change, due change, discussed] (pure; by_id: {id: issue})."""
    rows = []
    for issue_id in log['ids']:
        issue = by_id.get(issue_id) or {}
        entry = log['entries'].get(issue_id) or {}
        rows.append([issue_id, _text(issue.get('title')), _text(issue.get('status')),
                     _change(entry.get('status')), '\n'.join(entry.get('decisions') or []),
                     _change(entry.get('assignee')), _change(entry.get('due')),
                     bool(entry.get('discussed'))])
    return rows


MINUTES_HEADERS = ['Issue', 'Title', 'Status now', 'Status change', 'Decisions',
                   'Assignee change', 'Due change', 'Discussed']


def duration_text(log, now=None):
    from namo import dates
    start = dates.parse(log.get('started'))
    end = dates.parse(log.get('ended')) or now or datetime.datetime.now()
    if start is None:
        return ''
    minutes = int((end - start).total_seconds() // 60)
    if minutes < 60:
        return '%d min' % minutes
    return '%d h %02d min' % (minutes // 60, minutes % 60)


def minutes_report(log, by_id, title='Meeting minutes'):
    """The minutes as a namo.htmlreport.Report (pure)."""
    from namo import dates, htmlreport, issues
    c = counts(log)
    started = dates.parse(log.get('started'))
    report = htmlreport.Report(title, subtitle=log.get('doc') or None, meta=[
        ('Date', dates.format(started) if started else ''),
        ('Started', started.strftime('%H:%M') if started else ''),
        ('Duration', duration_text(log)), ('Chaired by', log.get('user') or ''),
        ('Issues', '%d of %d discussed' % (c['discussed'], c['issues']))])
    report.kpis([('Discussed', c['discussed'], None), ('Decisions', c['decisions'], 'info'),
                 ('Status changes', c['status_changes'], 'good' if c['status_changes'] else None),
                 ('New due dates', c['new_due'], 'warn' if c['new_due'] else None)])
    report.section('Issues', intro='Every issue on the agenda, in meeting order.')
    rows = minutes_rows(log, by_id)
    cells = []
    html = set()
    for index, row in enumerate(rows):
        status = row[2]
        cells.append([row[0], row[1], htmlreport.status_chip(status, issues.STATUS_TONES.get(status,
                                                                                            'neutral'))
                      if status else '', row[3], row[4], row[5], row[6], row[7]])
        if status:
            html.add((index, 2))
    report.table(MINUTES_HEADERS, cells, cell_html=html, numeric=())
    decided = [(issue_id, log['entries'][issue_id]) for issue_id in log['ids']
               if log['entries'].get(issue_id, {}).get('decisions')]
    if decided:
        report.section('Decisions')
        for issue_id, entry in decided:
            title = _text((by_id.get(issue_id) or {}).get('title'))
            report.html('<h3>%s</h3>' % htmlreport.escape('%s  %s' % (issue_id, title)))
            report.bullets(entry['decisions'])
    if log.get('events'):
        report.section('Change log', intro='Everything recorded during the meeting, in order.')
        report.table(['Time', 'Issue', 'What', 'Before', 'After', 'Note'],
                     [[e['time'][11:16], e['issue'], e['kind'].title(), e['before'], e['after'],
                       e['text']] for e in log['events']], numeric=())
    return report


def minutes_workbook(log, by_id, title='Meeting minutes'):
    """The minutes as a namo.xlsx.Workbook (pure)."""
    from namo import dates, xlsx
    wb = xlsx.Workbook(title=title, author=log.get('user') or None)
    ws = wb.sheet('Minutes')
    started = dates.parse(log.get('started'))
    ws.title(title, span=len(MINUTES_HEADERS))
    ws.subtitle('%s, %s, %s' % (log.get('doc') or 'Model', dates.format(started) if started else '',
                                duration_text(log)), span=len(MINUTES_HEADERS))
    ws.skip()
    ws.columns([('Issue', 12, None), ('Title', 40, 'wrap'), ('Status now', 14, None),
                ('Status change', 22, None), ('Decisions', 50, 'wrap'), ('Assignee change', 24, None),
                ('Due change', 24, None), ('Discussed', 11, None)])
    for row in minutes_rows(log, by_id):
        ws.row(row)
    ws.autofilter()
    log_sheet = wb.sheet('Change log')
    log_sheet.columns([('Time', 18, None), ('Issue', 12, None), ('What', 14, None),
                       ('Before', 20, None), ('After', 20, None), ('Note', 60, 'wrap')])
    for event in log.get('events') or []:
        log_sheet.row([event['time'].replace('T', ' '), event['issue'], event['kind'].title(),
                       event['before'], event['after'], event['text']])
    log_sheet.autofilter()
    return wb


def minutes_base_name(doc_name, now=None):
    """'Tower - Meeting minutes - 2026-10-05' (no extension, file-safe)."""
    from namo import naming
    when = now or datetime.datetime.now()
    stem = os.path.splitext(os.path.basename(doc_name or ''))[0] or 'Model'
    return naming.sanitize('%s - Meeting minutes - %s' % (stem, when.strftime('%Y-%m-%d')),
                           for_file=True)


def write_minutes(log, by_id, folder, now=None):
    """Writes '<model> - Meeting minutes - <date>.html' and '.xlsx' (unique names) into
    folder. Returns (html_path, xlsx_path)."""
    from namo import paths
    log = copy.deepcopy(log)
    if not log.get('ended'):
        from namo import issues
        log['ended'] = issues.stamp(now)
    paths.ensure_dir(folder)
    base = minutes_base_name(log.get('doc'), now)
    html_path = paths.unique_path(os.path.join(folder, base + '.html'))
    xlsx_path = paths.unique_path(os.path.join(folder, base + '.xlsx'))
    minutes_report(log, by_id).save(html_path)
    minutes_workbook(log, by_id).save(xlsx_path)
    return html_path, xlsx_path


def minutes_folder(doc_path):
    """The model's folder when saved and writable, else Documents."""
    folder = os.path.dirname(doc_path or '')
    if folder and os.path.isdir(folder) and os.access(folder, os.W_OK):
        return folder
    return os.path.join(os.path.expanduser('~'), 'Documents')


# ---- the window --------------------------------------------------------------------------------


class Meeting(object):
    """The meeting window's state and behaviour. env: the same environment the Issues
    pane uses (namo.issueui.Env); store: the IssueStore; bound: script.bind()."""

    def __init__(self, ids, store, env, doc, bound=None, logger=None, follow=True, user=''):
        from namo import ui
        self.ui = ui
        self.store = store
        self.env = env
        self.doc = doc
        self.bound = bound
        self.logger = logger or ui.pinned_logger()
        self.log = new_log(ids, user, doc_name=os.path.basename(store.doc_path))
        self.follow = follow
        self.finished = False
        self.window = None
        self.palette = ui.palette()

    def safe(self, fn, label):
        """fn as a late callback: a failed register write (the folder unreachable, the
        issue deleted meanwhile) is toasted as well as logged; anything else is logged."""
        def guarded(*args):
            try:
                return fn(*args)
            except (IOError, OSError, ValueError) as error:
                import traceback
                from namo import issueui
                self.ui.log_error('meeting %s failed:\n%s' % (label, traceback.format_exc()),
                                  self.logger)
                message, detail = issueui.save_failure(error)
                try:
                    self.env.toast('error', message, detail)
                except Exception:
                    pass
                return None
        return self.ui.safe(guarded, label, self.logger)

    def current_id(self):
        ids = self.log['ids']
        return ids[self.log['position']] if ids else None

    def current(self):
        issue_id = self.current_id()
        return self.store.get(issue_id) if issue_id else None

    # -- construction --

    def build(self):
        """The unshown window (smoke tests build it; open_window() shows it)."""
        from System.Windows import (GridLength, GridUnitType, HorizontalAlignment, Thickness,
                                    VerticalAlignment)
        from System.Windows.Controls import (Border, ColumnDefinition, Dock, DockPanel, Grid, Image,
                                             Orientation, StackPanel, WrapPanel)
        from System.Windows.Media import Stretch
        from namo import issues
        ui = self.ui
        win = ui.window('Meeting mode', width=900, height=700, min_width=720, min_height=560)
        self.window = win
        root = DockPanel()

        head = DockPanel()
        head.Margin = Thickness(24, 20, 24, 8)
        self.follow_check = ui.check('Follow in view', self.follow)
        self.follow_check.ToolTip = 'Go to each issue\'s saved view and select its elements'
        self.follow_check.VerticalAlignment = VerticalAlignment.Center
        DockPanel.SetDock(self.follow_check, Dock.Right)
        head.Children.Add(self.follow_check)
        self.counter = ui.text('', 13, muted=True)
        self.counter.VerticalAlignment = VerticalAlignment.Center
        head.Children.Add(self.counter)
        DockPanel.SetDock(head, Dock.Top)
        root.Children.Add(head)

        self.prev_button = ui.button('Previous', self.safe(lambda: self.go(-1), 'Previous'),
                                     'secondary', self.logger)
        self.next_button = ui.button('Next', self.safe(lambda: self.go(1), 'Next'), 'secondary',
                                     self.logger)
        for big in (self.prev_button, self.next_button):
            big.MinWidth = 128.0
            big.Height = 40.0
            big.FontSize = 15.0
        self.discussed_button = ui.button('Mark discussed', self.safe(self.mark_discussed, 'Discussed'),
                                          'secondary', self.logger)
        self.end_button = ui.button('End meeting', self.safe(self.end, 'End meeting'), 'primary',
                                    self.logger)
        nav = StackPanel()
        nav.Orientation = Orientation.Horizontal
        self.prev_button.Margin = Thickness(0, 0, 8, 0)
        nav.Children.Add(self.prev_button)
        nav.Children.Add(self.next_button)
        bottom = ui.footer([self.discussed_button, self.end_button], left=nav, padding=24)
        DockPanel.SetDock(bottom, Dock.Bottom)
        root.Children.Add(bottom)

        body = Grid()
        body.Margin = Thickness(24, 4, 24, 16)
        for width in (GridLength(1, GridUnitType.Star), GridLength(24), GridLength(384)):
            column = ColumnDefinition()
            column.Width = width
            body.ColumnDefinitions.Add(column)
        left = StackPanel()
        self.heading = ui.text('', 20, bold=True)
        left.Children.Add(self.heading)
        chips = WrapPanel()
        chips.Margin = Thickness(0, 8, 0, 8)
        self.status_chip = self._chip()
        self.priority_chip = self._chip()
        chips.Children.Add(self.status_chip)
        chips.Children.Add(self.priority_chip)
        left.Children.Add(chips)
        self.facts = ui.text('', 13)
        left.Children.Add(self.facts)
        self.description = ui.text('', 13, muted=True)
        self.description.Margin = Thickness(0, 8, 0, 8)
        left.Children.Add(self.description)

        left.Children.Add(self._section('Status'))
        statuses = WrapPanel()
        self.status_buttons = {}
        for status in issues.STATUSES:
            button = ui.button(status, self.safe(self._setter(status), 'Status %s' % status),
                               'secondary', self.logger)
            button.Margin = Thickness(0, 0, 8, 8)
            self.status_buttons[status] = button
            statuses.Children.Add(button)
        left.Children.Add(statuses)

        left.Children.Add(self._section('Decision'))
        decision_shell, self.decision_box = ui.text_box('', placeholder='What was agreed (Ctrl+Enter adds it)',
                                                        multiline=True, rows=2)
        left.Children.Add(decision_shell)
        self.decision_button = ui.button('Add decision', self.safe(self.add_decision, 'Decision'),
                                         'secondary', self.logger)
        self.decision_button.Margin = Thickness(0, 8, 0, 0)
        self.decision_button.HorizontalAlignment = HorizontalAlignment.Left
        left.Children.Add(self.decision_button)

        left.Children.Add(self._section('Assignee and due date'))
        edits = Grid()
        for width in (GridLength(1, GridUnitType.Star), GridLength(8), GridLength(140),
                      GridLength(8), GridLength.Auto):
            column = ColumnDefinition()
            column.Width = width
            edits.ColumnDefinitions.Add(column)
        assignee_shell, self.assignee_box = ui.text_box('', placeholder='Assignee')
        due_shell, self.due_box = ui.text_box('', placeholder='YYYY-MM-DD')
        self.apply_button = ui.button('Apply', self.safe(self.apply_edits, 'Apply'), 'secondary',
                                      self.logger)
        for column, control in ((0, assignee_shell), (2, due_shell), (4, self.apply_button)):
            Grid.SetColumn(control, column)
            edits.Children.Add(control)
        left.Children.Add(edits)
        self.edit_note = ui.hint('')
        self.edit_note.Margin = Thickness(0, 4, 0, 0)
        left.Children.Add(self.edit_note)
        scroll = ui.scroll(left)
        Grid.SetColumn(scroll, 0)
        body.Children.Add(scroll)

        right = StackPanel()
        frame = Border()
        frame.BorderBrush = ui.brush(self.palette['line'])
        frame.BorderThickness = Thickness(1)
        frame.Height = 218.0
        self.picture = Image()
        self.picture.Stretch = Stretch.Uniform
        frame.Child = self.picture
        right.Children.Add(frame)
        self.picture_note = ui.hint('')
        self.picture_note.Margin = Thickness(0, 6, 0, 8)
        right.Children.Add(self.picture_note)
        self.shot_button = ui.button('Take screenshot', self.safe(self.screenshot, 'Screenshot'),
                                     'secondary', self.logger)
        self.shot_button.HorizontalAlignment = HorizontalAlignment.Left
        right.Children.Add(self.shot_button)
        right.Children.Add(self._section('Latest comments'))
        self.comments = StackPanel()
        right.Children.Add(self.comments)
        Grid.SetColumn(right, 2)
        body.Children.Add(right)
        root.Children.Add(body)
        win.Content = root
        win.PreviewKeyDown += self.safe(self._keys, 'meeting keys')
        win.Closed += self.safe(lambda s, e: self._closed(), 'meeting closed')
        self.follow_check.Checked += self.safe(lambda s, e: self._follow_changed(), 'follow')
        self.follow_check.Unchecked += self.safe(lambda s, e: self._follow_changed(), 'follow')
        self.show_current(move_view=False)
        return win

    def _chip(self):
        from System.Windows import CornerRadius, Thickness
        from System.Windows.Controls import Border
        chip = Border()
        chip.CornerRadius = CornerRadius(3)
        chip.Padding = Thickness(8, 2, 8, 3)
        chip.Margin = Thickness(0, 0, 8, 0)
        chip.Child = self.ui.text('', 13, wrap=False)
        return chip

    def _paint_chip(self, chip, text, tone):
        from namo import issueui
        background, foreground = issueui.chip_colors(tone, self.palette)
        chip.Background = self.ui.brush(background)
        chip.Child.Foreground = self.ui.brush(foreground)
        chip.Child.Text = text

    def _section(self, title):
        from System.Windows import Thickness
        block = self.ui.text(title, 13, bold=True)
        block.Margin = Thickness(0, 16, 0, 8)
        return block

    def _setter(self, status):
        return lambda: self.set_status(status)

    # -- showing --

    def show_current(self, move_view=True):
        from namo import issueui, issues
        issue = self.current()
        total = len(self.log['ids'])
        position = self.log['position']
        self.prev_button.IsEnabled = position > 0
        self.next_button.IsEnabled = position < total - 1
        if issue is None:
            self.counter.Text = 'Issue %d of %d' % (position + 1, total) if total else 'No issues'
            self.heading.Text = 'This issue was deleted'
            self.facts.Text = ''
            self.description.Text = ''
            return
        record(self.log, issue['id'], 'visit')
        entry = self.log['entries'].get(issue['id']) or {}
        self.counter.Text = 'Issue %d of %d%s' % (position + 1, total,
                                                  ', discussed' if entry.get('discussed') else '')
        self.heading.Text = issues.display_title(issue)
        self._paint_chip(self.status_chip, issue['status'],
                         issues.STATUS_TONES.get(issue['status'], 'neutral'))
        self._paint_chip(self.priority_chip, issue['priority'],
                         issues.PRIORITY_TONES.get(issue['priority'], 'neutral'))
        lines = ['%s, %s' % (issue['type'], issue['trade'] or 'no trade'),
                 'Assigned to %s' % (issue['assignee'] or 'nobody yet'),
                 ('Due %s, %s' % (issue['due'], issues.due_note(issue).lower())
                  if issues.due_note(issue) else 'Due %s' % issue['due']) if issue['due']
                 else 'No due date', issueui.location_text(issue)]
        self.facts.Text = '\n'.join(lines)
        text = issue['description'] or ''
        self.description.Text = text if len(text) < 700 else text[:697] + '...'
        for status, button in sorted(self.status_buttons.items()):
            button.IsEnabled = status != issue['status']
        self.assignee_box.Text = issue['assignee']
        self.due_box.Text = issue['due']
        self.edit_note.Text = ''
        self._paint_picture(issue)
        self._paint_comments(issue)
        if move_view and self.follow:
            try:
                self.env.go_to(issue, self.doc)
            except Exception as error:
                self.ui.log_error('meeting go to failed: %s' % error, self.logger)

    def _paint_picture(self, issue):
        from System import Uri, UriKind
        from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
        path = self.store.snapshot_path(issue)
        found = self.store.images_on_disk(issue)
        if found:
            path = found[-1][1] if found[-1][0].get('kind') == 'screenshot' else path
        if not path:
            self.picture.Source = None
            self.picture_note.Text = 'No snapshot. Take screenshot records the view as it is now.'
            return
        try:
            bitmap = BitmapImage()
            bitmap.BeginInit()
            bitmap.CacheOption = BitmapCacheOption.OnLoad
            bitmap.DecodePixelWidth = 760
            bitmap.UriSource = Uri(path, UriKind.Absolute)
            bitmap.EndInit()
            bitmap.Freeze()
            self.picture.Source = bitmap
            self.picture_note.Text = '%d image%s' % (len(found), '' if len(found) == 1 else 's')
        except Exception:
            self.picture.Source = None
            self.picture_note.Text = 'The snapshot could not be read.'

    def _paint_comments(self, issue):
        from System.Windows import Thickness
        from namo import issueui, issues
        self.comments.Children.Clear()
        recent = (issue.get('comments') or [])[-3:]
        if not recent:
            self.comments.Children.Add(self.ui.hint('No comments yet.'))
            return
        for comment in reversed(recent):
            head = self.ui.text(issueui.comment_head(comment), 12, muted=True)
            body = self.ui.text(issues.comment_text(comment), 13)
            body.Margin = Thickness(0, 0, 0, 8)
            self.comments.Children.Add(head)
            self.comments.Children.Add(body)

    # -- actions --

    def go(self, delta):
        before = self.log['position']
        if step(self.log, delta) != before:
            self.show_current()

    def _note(self):
        return 'Meeting %s' % datetime.date.today().strftime('%Y-%m-%d')

    def set_status(self, status):
        issue = self.current()
        if issue is None or issue['status'] == status:
            return
        updated, note = self.store.update(issue['id'], {'status': status}, note=self._note())
        record(self.log, issue['id'], 'status', issue['status'], status)
        if note:
            self.env.toast('warning', 'Saved %s' % issue['id'], note)
        self.show_current(move_view=False)

    def add_decision(self):
        issue = self.current()
        text = self.decision_box.Text.strip()
        if issue is None:
            return
        if not text:
            self.env.toast('info', 'Write the decision first', 'Type what was agreed, then Add decision.')
            return
        self.store.add_comment(issue['id'], '%s: %s' % (self._note(), text))
        record(self.log, issue['id'], 'decision', text=text)
        self.decision_box.Text = ''
        self.show_current(move_view=False)

    def apply_edits(self):
        from namo import issues
        issue = self.current()
        if issue is None:
            return
        assignee = self.assignee_box.Text.strip()
        due_raw = self.due_box.Text.strip()
        due = issues.due_text(due_raw)
        if due_raw and not due:
            self.edit_note.Text = 'Not a date: use YYYY-MM-DD.'
            return
        changes = {}
        if assignee != issue['assignee']:
            changes['assignee'] = assignee
        if due != issue['due']:
            changes['due'] = due
        if not changes:
            self.edit_note.Text = 'Nothing changed.'
            return
        self.store.update(issue['id'], changes, note=self._note())
        for key in sorted(changes):
            record(self.log, issue['id'], key, issue[key], changes[key])
        self.show_current(move_view=False)
        self.edit_note.Text = 'Saved.'

    def mark_discussed(self):
        issue = self.current()
        if issue is None:
            return
        record(self.log, issue['id'], 'discussed')
        if self.log['position'] < len(self.log['ids']) - 1:
            self.go(1)
        else:
            self.show_current(move_view=False)

    def screenshot(self):
        issue = self.current()
        if issue is None:
            return
        try:
            path = self.env.screenshot(self.doc)
        except Exception as error:
            self.env.toast('error', 'Could not capture the view', str(error))
            return
        self.store.add_image(issue['id'], path, kind='screenshot', caption=self._note(), move=True)
        record(self.log, issue['id'], 'screenshot')
        self.show_current(move_view=False)

    def _follow_changed(self):
        self.follow = bool(self.follow_check.IsChecked)
        if self.bound is not None:
            try:
                values = self.bound.get_config(dict(DEFAULTS))
                values['follow'] = self.follow
                self.bound.save_config(values)
            except Exception:
                pass

    def _keys(self, sender, args):
        from System.Windows.Controls import TextBox
        from System.Windows.Input import Key, Keyboard, ModifierKeys
        typing = isinstance(args.OriginalSource, TextBox)
        if args.Key == Key.Enter and Keyboard.Modifiers == ModifierKeys.Control and \
                args.OriginalSource is self.decision_box:
            args.Handled = True
            self.add_decision()
        elif not typing and args.Key in (Key.Right, Key.PageDown):
            args.Handled = True
            self.go(1)
        elif not typing and args.Key in (Key.Left, Key.PageUp):
            args.Handled = True
            self.go(-1)

    # -- finishing --

    def write(self):
        """Writes the minutes; returns (html, xlsx) or None when nothing happened."""
        if not has_activity(self.log):
            return None
        from namo import issues
        self.log['ended'] = issues.stamp()
        by_id = dict((i['id'], i) for i in self.store.list())
        return write_minutes(self.log, by_id, minutes_folder(self.store.doc_path))

    def end(self):
        self._finish(close=True)

    def _closed(self):
        self._finish(close=False)

    def _finish(self, close):
        if self.finished:
            return
        self.finished = True
        try:
            written = self.write()
        except (IOError, OSError) as error:
            self.env.toast('error', 'Could not write the minutes', str(error))
            written = None
        if written is not None:
            html_path, _xlsx = written
            c = counts(self.log)
            self.env.toast('success', 'Minutes written', '%d discussed, %d decisions: %s'
                           % (c['discussed'], c['decisions'], os.path.basename(html_path)))
            try:
                self.env.open_path(html_path)
            except Exception:
                pass
        elif close:
            self.env.toast('info', 'Meeting ended', 'Nothing was discussed or changed, so no minutes were written.')
        if close and self.window is not None:
            try:
                self.window.Close()
            except Exception:
                pass


def activate_open():
    """Brings the window of a meeting that is already running to the front. True when
    there was one (the caller then asks nothing and starts nothing)."""
    from namo import ui
    try:
        existing = ui.Modeless.get(WINDOW_KEY)
        if existing is None:
            return False
        existing.Activate()
        return True
    except Exception:
        return False


def open_window(ids, store, doc, bound=None, logger=None, follow=True, env=None, user=''):
    """Shows the meeting window (one at a time). Returns the Meeting."""
    from namo import issueui, session, ui
    existing = ui.Modeless.get(WINDOW_KEY)
    if existing is not None:
        existing.Activate()
        return getattr(session.holder(HOLDER), 'meeting', None)
    meeting = Meeting(ids, store, env or issueui.Env(), doc, bound, logger, follow, user)
    session.holder(HOLDER).meeting = meeting
    ui.Modeless(WINDOW_KEY, 'Meeting mode', window_factory=meeting.build).show()
    meeting.show_current(move_view=True)
    return meeting

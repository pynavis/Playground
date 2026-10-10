# -*- coding: utf-8 -*-
"""Windows of the 4D tools, built on namo.ui.

  * build_review / review: a table with one primary action that closes it (the import
    check of TimeLiner from Excel, the Auto Attach preview). True only when the action
    was clicked; Esc, Close and the title bar cancel silently.
  * build_legend / show_legend: the Progress Painter legend, a small modeless window with
    the four bands, their colours and counts.
Pure helpers (rows and texts) are at the top.
"""

PROGRESS_BANDS = [
    ('Not started (0%)', 0.0, 0.0, 'BAB0AC'),
    ('Under way (1 to 49%)', 0.0001, 49.9999, 'F28E2B'),
    ('Well advanced (50 to 99%)', 50.0, 99.9999, '4E79A7'),
    ('Complete (100%)', 100.0, 100.0, '59A14F'),
]
LEGEND_KEY = 'playground-progress-legend'


def _wpf():
    """Loads the WPF assemblies so System.Windows names import (namo.ui does the same)."""
    import clr
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase'):
        clr.AddReference(name)


def band_of(percent):
    """Index of the PROGRESS_BANDS band a percentage falls in (None for no value)."""
    if percent is None:
        return None
    value = max(0.0, min(100.0, float(percent)))
    if value <= 0.0:
        return 0
    if value >= 100.0:
        return 3
    return 1 if value < 50.0 else 2


def problem_rows(problems):
    """ui table rows for parse problems: Row, Level, Column, Problem."""
    out = []
    for index, problem in enumerate(problems):
        out.append({'cells': [problem['row'] if problem['row'] is not None else '',
                              'Error' if problem['level'] == 'error' else 'Warning',
                              problem.get('label') or '', problem['message']], 'value': index})
    return out


def import_summary(plan, misses=0):
    """'Import 124 tasks: 98 new, 26 updated.' plus what is skipped or ignored."""
    from namo import fourd_common
    total = plan['created'] + plan['updated']
    parts = []
    if plan['mode'] == 'replace':
        text = 'Replace every TimeLiner task with %s.' % fourd_common.plural(total, 'task')
    else:
        text = 'Import %s: %s new, %s updated.' % (fourd_common.plural(total, 'task'),
                                                   '{:,}'.format(plan['created']), '{:,}'.format(plan['updated']))
    if plan['skipped']:
        parts.append('%s with errors skipped' % fourd_common.plural(plan['skipped'], 'row'))
    if plan.get('kept_in_place'):
        parts.append('%s kept where they are (merge never moves a task)'
                     % fourd_common.plural(plan['kept_in_place'], 'updated task'))
    if plan.get('ambiguous'):
        parts.append('Task ID %s is on more than one model task; the first is updated'
                     % ', '.join(plan['ambiguous'][:3]))
    if misses:
        parts.append('%s found nothing' % fourd_common.plural(misses, 'attach entry', 'attach entries'))
    return text + (' ' + '; '.join(parts) + '.' if parts else '')


def legend_rows(counts):
    """[(label, hex, count)] for the legend."""
    return [(label, color, counts.get(index, 0)) for index, (label, _lo, _hi, color) in enumerate(PROGRESS_BANDS)]


# ---- windows ------------------------------------------------------------------------------------


def build_review(title, headers, rows, status, action_label, width=860, height=560):
    """(window, outcome): outcome['go'] turns True when the action button is clicked."""
    from namo import ui
    outcome = {'go': False}
    holder = {}

    def go(selected):
        outcome['go'] = True
        holder['win'].Tag.close()
    win = ui.build_table(title, headers, rows,
                         actions=[{'label': action_label, 'fn': go, 'needs_selection': False, 'primary': True}],
                         status=status, width=width, height=height, close_label='Cancel')
    holder['win'] = win
    return win, outcome


def review(title, headers, rows, status, action_label):
    """Shows build_review modally; True when the action was chosen."""
    from namo import ui
    win, outcome = build_review(title, headers, rows, status, action_label)
    ui.show_modal(win)
    return outcome['go']


def build_legend(counts, source_text, on_clear=None):
    """The legend window, unshown: a swatch, label and count per band, a note on how to
    undo, Clear paint (when on_clear) and Close."""
    from namo import ui
    _wpf()
    from System.Windows import (CornerRadius, GridLength, GridUnitType, HorizontalAlignment,
                                Thickness, VerticalAlignment)
    from System.Windows.Controls import Border, ColumnDefinition, Grid, RowDefinition, StackPanel
    win = ui.window('Progress legend', width=360, resizable=False)
    body = StackPanel()
    body.Margin = Thickness(24, 20, 24, 16)
    body.Children.Add(ui.text(source_text, 12, muted=True))
    grid = Grid()
    grid.Margin = Thickness(0, 12, 0, 0)
    for width in (24.0, None, 72.0):
        column = ColumnDefinition()
        column.Width = GridLength(1, GridUnitType.Star) if width is None else GridLength(width)
        grid.ColumnDefinitions.Add(column)
    for index, (label, color, count) in enumerate(legend_rows(counts)):
        row = RowDefinition()
        row.Height = GridLength(32.0)
        grid.RowDefinitions.Add(row)
        swatch = Border()
        swatch.Width = swatch.Height = 16.0
        swatch.CornerRadius = CornerRadius(3)
        swatch.Background = ui.brush(color)
        swatch.VerticalAlignment = VerticalAlignment.Center
        swatch.HorizontalAlignment = HorizontalAlignment.Left
        Grid.SetRow(swatch, index)
        grid.Children.Add(swatch)
        text = ui.text(label, wrap=False)
        text.VerticalAlignment = VerticalAlignment.Center
        Grid.SetRow(text, index)
        Grid.SetColumn(text, 1)
        grid.Children.Add(text)
        number = ui.text('{:,}'.format(count), wrap=False)
        number.VerticalAlignment = VerticalAlignment.Center
        number.HorizontalAlignment = HorizontalAlignment.Right
        Grid.SetRow(number, index)
        Grid.SetColumn(number, 2)
        grid.Children.Add(number)
    body.Children.Add(grid)
    hint = ui.hint('Ctrl+Z removes the paint, or click Clear paint.')
    hint.Margin = Thickness(0, 12, 0, 0)
    body.Children.Add(hint)
    buttons = []
    if on_clear is not None:
        def clear():
            on_clear()
            win.Close()
        buttons.append(ui.button('Clear paint', clear, 'secondary'))
    close = ui.button('Close', lambda: win.Close(), 'primary')
    close.IsCancel = True
    buttons.append(close)
    from System.Windows.Controls import Dock, DockPanel
    layout = DockPanel()
    bar = ui.footer(buttons)
    DockPanel.SetDock(bar, Dock.Bottom)
    layout.Children.Add(bar)
    layout.Children.Add(body)
    win.Content = layout
    return win


def show_legend(counts, source_text, on_clear=None):
    """Opens (or replaces) the modeless legend beside Navisworks."""
    from namo import ui
    ui.Modeless.close(LEGEND_KEY)
    return ui.Modeless(LEGEND_KEY, 'Progress legend', None,
                       window_factory=lambda: build_legend(counts, source_text, on_clear)).show()

# -*- coding: utf-8 -*-
"""Output-window HTML for the Models, Quality and Publish tools (pure string building).

The pyNavis output window themes itself with CSS custom properties emitted per theme
(--fg, --muted, --line, --surface, --frame, --accent, --err, --err-wash, --err-line,
--warn, --warn-wash, --warn-line, --chart-1..6). Everything here uses only those, so
the same markup reads in light and dark. Every text argument is escaped; only the
cells named in `raw` (element links from pynavis.output.element_link, chips from
chip()) go in as HTML.

Trap: the output window opens web and mail links in the browser but NOT file: links:
a click on one would navigate the output window itself to the file. Paths are
therefore printed as text (path_line), and tools open files from the script.

Pure stdlib; no Navisworks, no pynavis import.
"""

LEVELS = ('pass', 'info', 'warn', 'fail')

# level -> (label, text colour, background, border)
_CHIP = {
    'pass': ('Pass', 'var(--chart-3)', 'transparent', 'var(--line)'),
    'info': ('Info', 'var(--muted)', 'transparent', 'var(--line)'),
    'warn': ('Warning', 'var(--warn)', 'var(--warn-wash)', 'var(--warn-line)'),
    'fail': ('Fail', 'var(--err)', 'var(--err-wash)', 'var(--err-line)'),
}

_TONE_COLOR = {'pass': 'var(--chart-3)', 'good': 'var(--chart-3)', 'warn': 'var(--warn)',
               'fail': 'var(--err)', 'bad': 'var(--err)', 'info': 'var(--fg)', None: 'var(--fg)'}


def esc(value):
    """HTML-escaped text for element content and quoted attributes; None is ''."""
    if value is None:
        return ''
    text = value if isinstance(value, str) else str(value)
    out = []
    for ch in text:
        if ch == '&':
            out.append('&amp;')
        elif ch == '<':
            out.append('&lt;')
        elif ch == '>':
            out.append('&gt;')
        elif ch == '"':
            out.append('&quot;')
        elif ch == "'":
            out.append('&#39;')
        elif ch == '\n':
            out.append('<br>')
        elif ord(ch) < 32 and ch not in '\t':
            continue
        else:
            out.append(ch)
    return ''.join(out)


def number(value, decimals=0):
    """'12,345' / '12.5' with thousands separators; None or '' gives ''."""
    if value is None or value == '':
        return ''
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, int):
        return '{:,}'.format(value)
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals <= 0:
        return '{:,}'.format(int(round(number_value)))
    text = ('{:,.%df}' % decimals).format(number_value)
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text


def level_of(text):
    """'pass' | 'info' | 'warn' | 'fail' from a level word ('warning', 'error' too)."""
    word = str(text or '').strip().lower()
    if word in ('fail', 'failed', 'error', 'bad'):
        return 'fail'
    if word in ('warn', 'warning'):
        return 'warn'
    if word in ('pass', 'passed', 'ok', 'good', 'success'):
        return 'pass'
    return 'info'


def chip(level, text=None):
    """The status tag (the one chip in the design system) for a level."""
    label, color, background, border = _CHIP[level_of(level)]
    return ('<span style="display:inline-block;padding:0 6px;border-radius:4px;'
            'font-size:12px;line-height:18px;color:%s;background:%s;border:1px solid %s;'
            'white-space:nowrap;">%s</span>'
            % (color, background, border, esc(label if text is None else text)))


def heading(text, level=2):
    level = 2 if level not in (1, 2, 3) else level
    return '<h%d>%s</h%d>' % (level, esc(text), level)


def note(text):
    """A muted paragraph."""
    return '<p style="color:var(--muted);">%s</p>' % esc(text)


def paragraph(text):
    return '<p>%s</p>' % esc(text)


def path_line(label, path):
    """'Saved: <path>' with the path as selectable code (never a file: link)."""
    return '<p>%s <code>%s</code></p>' % (esc(label), esc(path))


def kpis(items):
    """A row of large numbers: items [(label, value, tone)] with tone None, 'pass',
    'warn', 'fail' (or 'good'/'bad'); value text or a number."""
    cells = []
    for item in items:
        label, value = item[0], item[1]
        tone = item[2] if len(item) > 2 else None
        shown = number(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else esc(value)
        cells.append(
            '<div style="display:inline-block;margin:4px 28px 8px 0;vertical-align:top;">'
            '<div style="font-size:24px;font-weight:300;font-variant-numeric:tabular-nums;'
            'color:%s;">%s</div><div style="font-size:12px;color:var(--muted);">%s</div></div>'
            % (_TONE_COLOR.get(tone, 'var(--fg)'), shown, esc(label)))
    return '<div>%s</div>' % ''.join(cells)


def _is_number_text(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    text = str(value).replace(',', '').strip()
    if not text:
        return False
    try:
        float(text)
        return True
    except ValueError:
        return False


def numeric_columns(rows, count):
    """Columns where every non-empty cell is a number or numeric text (and at least one
    cell is non-empty): those are right-aligned in tabular figures."""
    out = []
    for col in range(count):
        seen = False
        numeric = True
        for row in rows:
            value = row[col] if col < len(row) else ''
            if value is None or value == '':
                continue
            seen = True
            if not _is_number_text(value):
                numeric = False
                break
        out.append(seen and numeric)
    return out


def table(headers, rows, raw=None, numeric=None, max_rows=None, caption=None):
    """A themed table (table.pynavis). raw: set of (row, col) or of col indexes whose
    cells are trusted HTML. numeric: column indexes to right-align (None: decided from
    the data). Numbers get thousands separators. max_rows cuts long tables with a
    muted line saying how many were left out."""
    raw = set(raw or [])
    shown = list(rows)
    cut = 0
    if max_rows is not None and len(shown) > max_rows:
        cut = len(shown) - max_rows
        shown = shown[:max_rows]
    count = len(headers)
    if numeric is None:
        flags = numeric_columns([r for r in shown], count)
    else:
        wanted = set(numeric)
        flags = [i in wanted for i in range(count)]
    parts = ['<table class="pynavis">']
    if caption:
        parts.append('<caption style="text-align:left;color:var(--muted);padding:4px 0;">%s</caption>'
                     % esc(caption))
    parts.append('<tr>')
    for i, header in enumerate(headers):
        parts.append('<th%s>%s</th>' % (' class="num"' if flags[i] else '', esc(header)))
    parts.append('</tr>')
    for r, row in enumerate(shown):
        parts.append('<tr>')
        for c in range(count):
            value = row[c] if c < len(row) else ''
            if (r, c) in raw or c in raw:
                cell = '' if value is None else str(value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                cell = number(value, 0 if isinstance(value, int) else 2)
            else:
                cell = esc(value)
            parts.append('<td%s>%s</td>' % (' class="num"' if flags[c] else '', cell))
        parts.append('</tr>')
    parts.append('</table>')
    if cut:
        parts.append(note('%s more rows are in the exported file.' % '{:,}'.format(cut)))
    return ''.join(parts)


def kv_table(pairs, raw_keys=()):
    """Two-column label/value table for an info card: pairs [(label, value)]."""
    raw_keys = set(raw_keys)
    parts = ['<table class="pynavis">']
    for label, value in pairs:
        cell = str(value) if label in raw_keys else esc(value)
        parts.append('<tr><td style="color:var(--muted);white-space:nowrap;">%s</td><td>%s</td></tr>'
                     % (esc(label), cell))
    parts.append('</table>')
    return ''.join(parts)


def checklist(checks):
    """A pass/warn/fail list: checks [{'level', 'name', 'detail'}] as a table with the
    chip first."""
    rows = [[chip(c.get('level')), c.get('name', ''), c.get('detail', '')] for c in checks]
    return table(['Result', 'Check', 'Detail'], rows, raw=set([0]), numeric=[])


def bars(labels, values, title=None, value_format=None, note_text=None):
    """A small horizontal bar chart in plain HTML (one series, --chart-1). For output
    windows where pynavis.output.chart_bar is not wanted (e.g. inside a card)."""
    numbers = [float(v or 0) for v in values]
    top = max(numbers) if numbers else 0.0
    parts = []
    if title:
        parts.append('<h3>%s</h3>' % esc(title))
    parts.append('<table style="border-collapse:collapse;width:100%;max-width:720px;">')
    for label, value in zip(labels, numbers):
        width = 0 if top <= 0 else max(1, int(round(100.0 * value / top)))
        text = value_format(value) if value_format else number(value)
        parts.append(
            '<tr><td style="padding:2px 8px 2px 0;white-space:nowrap;max-width:240px;'
            'overflow:hidden;text-overflow:ellipsis;">%s</td>'
            '<td style="width:70%%;padding:2px 0;"><div style="background:var(--chart-1);height:12px;'
            'width:%d%%;border-radius:2px;"></div></td>'
            '<td style="padding:2px 0 2px 8px;text-align:right;font-variant-numeric:tabular-nums;'
            'color:var(--muted);white-space:nowrap;">%s</td></tr>'
            % (esc(label), width, esc(text)))
    parts.append('</table>')
    if note_text:
        parts.append(note(note_text))
    return ''.join(parts)

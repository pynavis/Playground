# -*- coding: utf-8 -*-
"""Usage Analytics: which tools people run, when, and for how long. Opt-in.

Nothing is recorded until someone turns it on (the first click explains and asks).
hk_usage stamps the time on before-command and appends one line on after-command:
time, user, machine, extension, bundle key, title, duration in ms. NO document names,
file paths or model data are recorded. Lines go to a monthly CSV in
<data_root>\\usage\\usage-YYYY-MM.csv, or, with "store in the team folder" on, to
<team_root>\\usage\\<user> YYYY-MM.csv (one file per user, so nobody writes another
person's file).

Pure half: settings defaults, csv_line/parse_csv, file naming, aggregate() (top tools,
runs per day, per user, never-used tools), xlsx sheets. API half: the hook functions
(fast, never raise), reading files, the output-window report.
"""
import csv
import datetime
import io
import os
import time

from namo import paths, session

FIELDS = ['time', 'user', 'machine', 'extension', 'key', 'title', 'ms']
DEFAULTS = {'enabled': False, 'asked': False, 'shared': False}
HOLDER = 'usage'
CACHE_SECONDS = 30.0

# ---- pure ----------------------------------------------------------------------------------


def csv_line(values):
    """One CSV line (RFC 4180 quoting) ending in CRLF."""
    out = []
    for value in values:
        text = '' if value is None else str(value)
        text = text.replace('\r', ' ').replace('\n', ' ')
        if any(c in text for c in ',"') or text != text.strip():
            text = '"%s"' % text.replace('"', '""')
        out.append(text)
    return ','.join(out) + '\r\n'


def parse_csv(text):
    """Rows as dicts from usage CSV text (header line first); bad lines skipped."""
    rows = []
    lines = (text or '').splitlines()
    if not lines:
        return rows
    reader = csv.reader(lines)
    header = None
    for record in reader:
        if header is None:
            header = [h.strip() for h in record]
            continue
        if len(record) < len(header):
            continue
        row = dict(zip(header, record))
        try:
            row['ms'] = int(float(row.get('ms') or 0))
        except ValueError:
            row['ms'] = 0
        if not row.get('key'):
            continue
        rows.append(row)
    return rows


def month_name(when):
    return when.strftime('%Y-%m')


def file_for(folder, when, user=None, shared=False):
    """The CSV a line written at `when` goes to."""
    if shared:
        return os.path.join(folder, '%s %s.csv' % (paths.safe_filename(user or 'user', 60), month_name(when)))
    return os.path.join(folder, 'usage-%s.csv' % month_name(when))


def line_values(when, user, machine, extension, key, title, ms):
    return [when.strftime('%Y-%m-%dT%H:%M:%S'), user, machine, extension, key, title, int(ms)]


def _day(row):
    return (row.get('time') or '')[:10]


def aggregate(rows, commands=None, days=60, today=None):
    """{'runs', 'tools', 'users', 'first', 'last', 'by_tool': [{'key', 'title', 'runs',
    'users', 'seconds', 'median_s'}], 'by_day': [(YYYY-MM-DD, runs)] for the last `days`
    days (zeros filled), 'by_user': [(user, runs, tools)], 'never': [command]} where
    commands are namo.ribbon button dicts (never = listed tools nobody ran)."""
    by_key = {}
    users = {}
    day_counts = {}
    for row in rows:
        key = row['key'].lower()
        tool = by_key.get(key)
        if tool is None:
            tool = {'key': row['key'], 'title': row.get('title') or row['key'], 'runs': 0,
                    'users': set(), 'durations': [], 'extension': row.get('extension') or ''}
            by_key[key] = tool
        tool['runs'] += 1
        tool['users'].add(row.get('user') or '')
        tool['durations'].append(row.get('ms') or 0)
        user = users.setdefault(row.get('user') or '', {'runs': 0, 'tools': set()})
        user['runs'] += 1
        user['tools'].add(key)
        day = _day(row)
        if day:
            day_counts[day] = day_counts.get(day, 0) + 1
    tools = []
    for tool in by_key.values():
        durations = sorted(tool['durations'])
        median = durations[len(durations) // 2] / 1000.0 if durations else 0.0
        tools.append({'key': tool['key'], 'title': tool['title'], 'runs': tool['runs'],
                      'users': len(tool['users']), 'seconds': sum(durations) / 1000.0,
                      'median_s': median, 'extension': tool['extension']})
    tools.sort(key=lambda t: (-t['runs'], t['title'].lower()))
    end = today or (max(day_counts) if day_counts else datetime.date.today().isoformat())
    if not isinstance(end, str):
        end = end.isoformat()
    end_date = datetime.date(int(end[:4]), int(end[5:7]), int(end[8:10]))
    by_day = []
    for offset in range(days - 1, -1, -1):
        day = (end_date - datetime.timedelta(days=offset)).isoformat()
        by_day.append((day, day_counts.get(day, 0)))
    by_user = sorted([(name, info['runs'], len(info['tools'])) for name, info in users.items()],
                     key=lambda u: (-u[1], u[0].lower()))
    used = set(by_key)
    never = []
    seen = set()
    for command in commands or []:
        key = (command.get('key') or '').lower()
        if not key or key in used or key in seen or command.get('hidden'):
            continue
        seen.add(key)
        never.append(command)
    never.sort(key=lambda c: ((c.get('path') or '').lower(), (c.get('title') or '').lower()))
    days_seen = sorted(day_counts)
    return {'runs': len(rows), 'tools': len(by_key), 'users': len(users),
            'first': days_seen[0] if days_seen else '', 'last': days_seen[-1] if days_seen else '',
            'by_tool': tools, 'by_day': by_day, 'by_user': by_user, 'never': never}


def xlsx_sheets(summary):
    """write_simple sheets for an export."""
    return [
        {'name': 'Tools', 'headers': ['Tool', 'Extension', 'Bundle key', 'Runs', 'Users',
                                      'Total seconds', 'Median seconds'],
         'rows': [[t['title'], t['extension'], t['key'], t['runs'], t['users'],
                   round(t['seconds'], 1), round(t['median_s'], 2)] for t in summary['by_tool']]},
        {'name': 'Per day', 'headers': ['Day', 'Runs'], 'rows': [[d, n] for d, n in summary['by_day']]},
        {'name': 'Per user', 'headers': ['User', 'Runs', 'Tools used'],
         'rows': [[u, r, t] for u, r, t in summary['by_user']]},
        {'name': 'Never used', 'headers': ['Tool', 'Where'],
         'rows': [[c.get('title'), c.get('path')] for c in summary['never']]},
    ]


# ---- settings (a fixed file: the hook has no bundle of its own) -----------------------------


def settings_path():
    return os.path.join(paths.data_root(), 'usage', 'settings.json')


def load_settings():
    stored = paths.load_json(settings_path(), {})
    out = dict(DEFAULTS)
    if isinstance(stored, dict):
        for key in DEFAULTS:
            if key in stored:
                out[key] = bool(stored[key])
    return out


def save_settings(values):
    current = load_settings()
    for key in DEFAULTS:
        if key in values:
            current[key] = bool(values[key])
    paths.write_json(settings_path(), current)
    holder = session.holder(HOLDER)
    holder.settings = current
    holder.loaded = time.time()
    return current


def cached_settings():
    """Settings for the hook, re-read at most every 30 s (the tool updates the cache)."""
    holder = session.holder(HOLDER)
    now = time.time()
    current = getattr(holder, 'settings', None)
    if current is None or now - getattr(holder, 'loaded', 0) > CACHE_SECONDS:
        current = load_settings()
        holder.settings = current
        holder.loaded = now
    return current


def folder_for(settings):
    """Where lines are written now: team usage folder when shared and reachable."""
    if settings.get('shared') and paths.team_available():
        return os.path.join(paths.team_root(), 'usage'), True
    return os.path.join(paths.data_root(), 'usage'), False


# ---- the hook (fast, quiet) -----------------------------------------------------------------


def before(key):
    if not key or not cached_settings().get('enabled'):
        return
    holder = session.holder(HOLDER)
    started = getattr(holder, 'started', None)
    if started is None:
        started = {}
        holder.started = started
    started[key.lower()] = time.time()


def _title_of(key):
    """(extension, title) of a bundle key, cached per Reload."""
    holder = session.holder(HOLDER)
    try:
        from namo import ribbon
        exts = ribbon.extensions()
        marker = id(exts[0]) if exts else 0
        cache = getattr(holder, 'titles', None)
        if cache is None or getattr(holder, 'titles_marker', None) != marker:
            cache = {}
            for command in ribbon.buttons(exts):
                cache.setdefault(ribbon.normalize_key(command['key']).lower(),
                                 (command['extension'], command['title']))
            holder.titles = cache
            holder.titles_marker = marker
        return cache.get(ribbon.normalize_key(key).lower(), ('', ''))
    except Exception:
        return ('', '')


def after(key, now=None):
    """Appends the line for a finished command. Returns the file written, or None."""
    settings = cached_settings()
    if not key or not settings.get('enabled'):
        return None
    holder = session.holder(HOLDER)
    started = getattr(holder, 'started', None) or {}
    begin = started.pop(key.lower(), None)
    end = now if now is not None else time.time()
    ms = int(round((end - begin) * 1000.0)) if begin else 0
    from namo import config
    user = config.user_name()
    machine = os.environ.get('COMPUTERNAME') or ''
    extension, title = _title_of(key)
    folder, shared = folder_for(settings)
    when = datetime.datetime.fromtimestamp(end)
    path = file_for(folder, when, user, shared)
    write_line(path, line_values(when, user, machine, extension, key, title, ms))
    return path


def write_line(path, values):
    paths.ensure_dir(os.path.dirname(path))
    new = not os.path.exists(path)
    with io.open(path, 'a', encoding='utf-8', newline='') as handle:
        if new:
            handle.write(csv_line(FIELDS))
        handle.write(csv_line(values))


# ---- reading and the report ------------------------------------------------------------------


def read_rows(folders):
    """Every row in every *.csv directly in the folders."""
    rows = []
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith('.csv'):
                continue
            text = paths.read_text(os.path.join(folder, name), '')
            rows.extend(parse_csv(text))
    rows.sort(key=lambda r: r.get('time') or '')
    return rows


def report_folders(settings):
    folders = [os.path.join(paths.data_root(), 'usage')]
    if settings.get('shared') and paths.team_available():
        folders.append(os.path.join(paths.team_root(), 'usage'))
    return folders


def _fmt_seconds(value):
    if value >= 3600:
        return '%.1f h' % (value / 3600.0)
    if value >= 60:
        return '%.1f min' % (value / 60.0)
    return '%.1f s' % value


def print_report(summary, scope_text):
    """Writes the report into the pyNavis output window."""
    from pynavis import output
    output.set_title('Usage Analytics')
    output.print_md('# Usage analytics\n\n%s\n\n- **%s** runs of **%s** tools by **%s** %s\n- From %s to %s'
                    % (scope_text, '{:,}'.format(summary['runs']), '{:,}'.format(summary['tools']),
                       '{:,}'.format(summary['users']), 'person' if summary['users'] == 1 else 'people',
                       summary['first'], summary['last']))
    top = summary['by_tool'][:15]
    if top:
        output.chart_bar([t['title'] for t in top], [t['runs'] for t in top], title='Most used tools')
    days = summary['by_day']
    if days:
        output.chart_line([d[5:] for d, _n in days], {'Runs': [n for _d, n in days]},
                          title='Runs per day, last %d days' % len(days))
    output.print_md('## Every tool used')
    output.print_table([[t['title'], t['extension'], '{:,}'.format(t['runs']), t['users'],
                         _fmt_seconds(t['seconds']), '%.1f s' % t['median_s']] for t in summary['by_tool']],
                       ['Tool', 'Extension', 'Runs', 'People', 'Total time', 'Typical run'])
    if summary['users'] > 1:
        output.print_md('## Per person')
        output.print_table([[u, '{:,}'.format(r), t] for u, r, t in summary['by_user']],
                           ['Person', 'Runs', 'Tools used'])
    never = summary['never']
    output.print_md('## Never used (%s)' % '{:,}'.format(len(never)))
    if never:
        output.print_table([[c.get('title'), c.get('path')] for c in never[:500]], ['Tool', 'Where'])

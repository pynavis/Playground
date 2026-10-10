# -*- coding: utf-8 -*-
"""Per-Trade Reports: one clash workbook (and optionally one dashboard) per responsible
trade, plus an index workbook, into one folder.

Who is responsible for a clash, in order:
  1. its Assigned to, when set: a person Clash Assigner maps to a trade ('Mechanical =
     Jane Smith') counts for that trade, a trade name for itself, anyone else under
     their own name;
  2. else the trade that moves under Clash Assigner's "who moves" list (the LOWER
     priority trade of the pair moves; namo.clashassign.mover);
  3. else (a model without a trade, or a tie it cannot decide) both trades.
The list and the names are read from Clash Assigner's own saved options (its Shift+Click),
unless the config carries 'priority' / 'names'. Each trade's workbook is the Clash Excel
Report layout over that trade's clashes only; trades with nothing listed get no file.

Implements the namo.reports rep_<id>.py contract; routing and planning are pure.
"""

import os

from namo import clashassign
from namo import clashreport as cr
from namo import naming, reports, xlsx

TITLE = 'Per-Trade Reports'
NAME_TEMPLATE = '{file} - Clashes - {trade} - {date}'
INDEX_TEMPLATE = '{file} - Clashes by trade - {date}'
FOLDER_TEMPLATE = '{file} - Clash reports by trade - {date}'
# Clash Assigner's settings key; it lives in clashassign (read through saved_settings).
ASSIGNER_KEY = clashassign.SETTINGS_KEY
WHY_ASSIGNED = 'assigned'
WHY_MOVES = 'moves'
WHY_BOTH = 'both'


def default_config():
    return reports.base_config(tests=[], statuses=list(cr.OPEN), html=False, images=False,
                               image_cap=cr.IMAGE_CAP, categories=True, priority=[], names='',
                               subfolder=True, name_template=NAME_TEMPLATE)


def describe(config):
    return '%s, %s, one workbook per trade%s' % (cr.tests_text(config.get('tests')),
                                                 cr.statuses_text(config.get('statuses')),
                                                 ' and dashboard' if config.get('html') else '')


# ---- pure: routing ------------------------------------------------------------------------------


def assigner_settings(priority=None, names=None, loader=None):
    """(priority list, {trade lower: person}) from the arguments when given, else Clash
    Assigner's saved options (clashassign.saved_settings), else its defaults.
    loader(key, defaults) is a test seam for pynavis.settings.load."""
    stored_priority, stored_names = list(clashassign.DEFAULT_PRIORITY), {}
    if not priority or not names:
        stored_priority, stored_names = clashassign.saved_settings(loader)
    chosen = clashassign.priority_list(priority or stored_priority)
    people = clashassign.names_map(names if names else stored_names)
    return chosen or list(clashassign.DEFAULT_PRIORITY), people


def people_lookup(people, known_trades):
    """{person lower: trade} from Clash Assigner's {trade lower: person}, trade names in
    their known spelling."""
    spelled = dict((str(t).lower(), t) for t in known_trades or [])
    out = {}
    for trade_low, person in people.items():
        out[str(person).strip().lower()] = spelled.get(trade_low, trade_low.title())
    return out


def responsible(row, priority, people_to_trade, known_trades):
    """([trades], why) for one clash (see the module docstring)."""
    from namo import clashassign
    assigned = (row.get('assigned') or '').strip()
    if assigned:
        low = assigned.lower()
        if low in people_to_trade:
            return [people_to_trade[low]], WHY_ASSIGNED
        for trade in known_trades or []:
            if str(trade).lower() == low:
                return [trade], WHY_ASSIGNED
        return [assigned], WHY_ASSIGNED
    trade_a = (row.get('trade_a') or '').strip() or cr.UNASSIGNED
    trade_b = (row.get('trade_b') or '').strip() or cr.UNASSIGNED
    moving = clashassign.mover(trade_a, trade_b, priority)
    if moving:
        return [moving], WHY_MOVES
    both = []
    for trade in (trade_a, trade_b):
        if trade not in both:
            both.append(trade)
    return both, WHY_BOTH


def route(data, priority, people, known_trades):
    """Sets row['responsible'] and row['why'] on every row; returns {trade: [rows]}."""
    lookup = people_lookup(people, list(known_trades or []) + list(priority or []))
    out = {}
    for row in cr.all_rows(data):
        trades, why = responsible(row, priority, lookup, list(known_trades or []) + list(priority or []))
        row['responsible'] = trades
        row['why'] = why
        for trade in trades:
            out.setdefault(trade, []).append(row)
    return out


def trade_data(data, trade):
    """data narrowed to one trade's clashes; tests without any are dropped."""
    narrowed = cr.subset(data, lambda r: trade in (r.get('responsible') or []))
    narrowed['tests'] = [t for t in narrowed['tests'] if t['rows']]
    narrowed['trade'] = trade
    return narrowed


def plan(data, statuses, priority, people, known_trades):
    """[{'trade', 'rows', 'listed', 'open', 'new', 'oldest', 'why': {why: n}}] for trades
    with at least one listed clash, most listed first (ties by name)."""
    routed = route(data, priority, people, known_trades)
    out = []
    for trade in routed:
        rows = routed[trade]
        listed = cr.filter_rows(rows, statuses)
        if not listed:
            continue
        tally = cr.counts(rows)
        oldest = cr.oldest_open(rows)
        whys = {}
        for row in listed:
            whys[row['why']] = whys.get(row['why'], 0) + 1
        out.append({'trade': trade, 'rows': rows, 'listed': len(listed), 'open': tally['open'],
                    'new': tally['by_status']['New'], 'oldest': oldest['age'] if oldest else None, 'why': whys})
    out.sort(key=lambda e: (-e['listed'], naming.natural_key(e['trade'])))
    return out


def file_name(template, trade, ext, stem, now=None):
    """A safe file name from a naming template with {trade} and {file} filled."""
    values = naming.standard_values()
    if now is not None:
        values.update({'date': now.date(), 'time': now.time(), 'datetime': now})
    values.update(cr.file_values(stem))
    values['trade'] = trade
    text, _missing = naming.render(template or NAME_TEMPLATE, values)
    name = naming.sanitize(text, for_file=True) or naming.sanitize(trade or 'Clashes', for_file=True)
    if not ext:
        return name
    if not ext.startswith('.'):
        ext = '.' + ext
    return name if name.lower().endswith(ext) else name + ext


def routing_note(priority):
    return ('Each clash goes to its Assigned to (people Clash Assigner maps to a trade count for that trade); '
            'an unassigned clash goes to the trade that moves (%s: the later trade moves), and to both trades '
            'when that cannot be decided.' % ' > '.join(priority))


def build_index(data, entries, files, priority, statuses):
    """The index workbook: one row per trade with links to its files."""
    wb = xlsx.Workbook(title='Clashes by trade', author=data.get('user') or None)
    wb.style('wrapnote', wrap=True, color='6B6B6B', valign='top')
    ws = wb.sheet('Trades')
    ws.title('Clashes by trade%s' % (': %s' % data['project'] if data.get('project') else ''), span=8)
    generated = data.get('generated')
    ws.subtitle('%s, %s. Listed in each workbook: %s.' % (
        data.get('file') or 'Untitled', generated.strftime('%Y-%m-%d %H:%M') if generated else '',
        cr.statuses_text(statuses)), span=8)
    header = ws.columns([('Trade', 24, None), ('Listed', 9, 'int'), ('Open', 9, 'int'), ('New', 9, 'int'),
                         ('Oldest open (days)', 18, 'int'), ('Assigned', 10, 'int'), ('Trade that moves', 16, 'int'),
                         ('Both trades', 12, 'int'), ('Workbook', 40, None), ('Dashboard', 40, None)])
    for entry in entries:
        links = files.get(entry['trade']) or {}
        ws.row([entry['trade'], entry['listed'], entry['open'], entry['new'], entry['oldest'],
                entry['why'].get(WHY_ASSIGNED, 0), entry['why'].get(WHY_MOVES, 0), entry['why'].get(WHY_BOTH, 0),
                xlsx.Link(links['xlsx'], links['xlsx']) if links.get('xlsx') else '',
                xlsx.Link(links['html'], links['html']) if links.get('html') else ''])
    if entries:
        ws.autofilter(header, header + len(entries), 0, 9)
    ws.skip()
    row = ws.row([routing_note(priority)], styles='wrapnote', height=48)
    ws.merge(row, 0, row, 9)
    ws.row(['A clash routed to both trades appears in both workbooks.'], styles='muted')
    return wb


# ---- run ----------------------------------------------------------------------------------------


def target_folder(config, stem, now=None):
    """The folder the files go to (created): config['folder'] (or <data_root>\\reports),
    plus a dated subfolder when config['subfolder']."""
    from namo import paths
    base = str(config.get('folder') or '').strip()
    base = os.path.expanduser(os.path.expandvars(base)) if base else os.path.join(paths.data_root(), 'reports')
    if config.get('subfolder', True):
        base = os.path.join(base, file_name(FOLDER_TEMPLATE, '', '', stem, now))
    paths.ensure_dir(base)
    return base


def run(config, doc=None, interactive=True, progress=None):
    """See namo.reports. result['folder'] is the folder written."""
    from namo import rep_clash_excel as excel
    from namo import rep_clash_html as dashboard
    stage = cr.Stage(progress)
    data, thumbs, problem = excel.prepare(config, doc, progress, span=(0.0, 0.7))
    if problem is not None:
        return problem
    written = []
    try:
        statuses = cr.ordered_statuses(config.get('statuses'))
        priority, people = assigner_settings(config.get('priority'), config.get('names'))
        entries = plan(data, statuses, priority, people, data.get('trades_order'))
        if not entries:
            return reports.result('info', 'No clashes to send to trades',
                                  'None of the chosen tests has %s.' % cr.statuses_text(statuses))
        folder = target_folder(config, data.get('file'), data.get('generated'))
        note = routing_note(priority)
        files = {}
        used = []
        for index, entry in enumerate(entries):
            trade = entry['trade']
            stage(0.7 + 0.28 * index / float(len(entries)), 'Writing %s' % trade)
            narrowed = trade_data(data, trade)
            narrowed['notes'] = list(narrowed.get('notes') or []) + [note]
            names = {}
            name = file_name(config.get('name_template'), trade, 'xlsx', data.get('file'), data.get('generated'))
            stem = naming.unique(os.path.splitext(name)[0], used)     # two trades that read the same as files
            used.append(stem)
            path = os.path.join(folder, stem + '.xlsx')
            excel.build_workbook(narrowed, config, title='Clash report: %s' % trade).save(path)
            names['xlsx'] = os.path.basename(path)
            written.append(path)
            if config.get('html'):
                page = os.path.splitext(path)[0] + '.html'
                dashboard.build_report(narrowed, config, title='Clash dashboard: %s' % trade).save(page)
                names['html'] = os.path.basename(page)
                written.append(page)
            files[trade] = names
        index_path = os.path.join(folder, file_name(INDEX_TEMPLATE, '', 'xlsx', data.get('file'), data.get('generated')))
        build_index(data, entries, files, priority, statuses).save(index_path)
        written.insert(0, index_path)
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the trade reports',
                              'Close any of them open in Excel, then try again (%s).' % error)
    finally:
        cr.remove_folder(thumbs)
    stage(1.0, 'Done')
    top = ', '.join('%s %s' % (e['trade'], '{:,}'.format(e['listed'])) for e in entries[:4])
    detail = '%s%s, in %s' % (top, ' and more' if len(entries) > 4 else '', folder)
    stats = data.get('image_stats') or {}
    level = 'warning' if (data.get('missing') or stats.get('failed') or stats.get('skipped')) else 'success'
    result = reports.result(level, 'Wrote clash reports for %s' % cr.plural(len(entries), 'trade'), detail,
                            paths=written)
    result['folder'] = folder
    return result

# -*- coding: utf-8 -*-
"""Clash Matrix: a battery of clash tests driven by a workbook.

The workbook has three sheets:

  Read me   what the codes mean (written by the template, ignored when reading)
  Trades    Trade | Source | Notes. One row per source; a row with a blank Trade adds
            another source to the trade above it. A source is
              Set: MEP/Ducts          a selection set (or folder) by path
              Model: MEP-L1.nwc       a whole model by file name (* and ? allowed)
              Element > Category = Ducts
                                      a property condition (namo.rules.parse_cell);
                                      several lines in one cell are ANDed
              MEP/Ducts               a bare path is a set (when it is not a condition)
  Matrix    trade names across row 1 and down column A; a cell is
              blank                   no test
              H, H 10mm               hard, optional tolerance (overlaps up to it ignored)
              HC, HC 5mm              hard (conservative)
              C 50mm                  clearance, the distance is required
              D, D 1mm                duplicates
            A length is anything pynavis reads (25mm, 1/2", 0.1m); a bare number is in
            the document's units. The cell in row X, column Y builds "X vs Y"; when the
            mirror cell holds the same code the test is made once.

Conditions become SEARCH sets in a 'Clash Matrix' selection-set folder (created or
updated, one per trade), and every side references sets through selection sources, so
the tests follow model updates. Whole models are explicit items, as in Clash Detective.

Pure parsing and planning first (unit tested); the API half builds through
namo.clashset_tests.
"""

import re

from namo import clashset_tests as defs
from namo import naming, rules, units

SHEET_HELP = 'Read me'
SHEET_TRADES = 'Trades'
SHEET_MATRIX = 'Matrix'
SET_FOLDER = 'Clash Matrix'
DEFAULT_NAME = '{a} vs {b}'

_CODE = re.compile(r'^\s*(hard\s+conservative|hard|clearance|duplicates?|hc|h|c|d)(?![a-z])\.?\s*(.*)$',
                   re.IGNORECASE)
_CODE_TYPE = {'h': 'hard', 'hard': 'hard', 'hc': 'hard_conservative',
              'hard conservative': 'hard_conservative', 'c': 'clearance',
              'clearance': 'clearance', 'd': 'duplicate', 'duplicate': 'duplicate',
              'duplicates': 'duplicate'}
_SHORT = {'hard': 'H', 'hard_conservative': 'HC', 'clearance': 'C', 'duplicate': 'D'}


# ---- pure: cells ------------------------------------------------------------------------


def col_letter(col):
    """'A'..'XFD' for a 0-based column."""
    letters = ''
    col += 1
    while col:
        col, rest = divmod(col - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def cell_ref(row, col):
    return '%s%d' % (col_letter(col), row + 1)


def cell_text(value):
    """A workbook value as trimmed text ('' for None; 3.0 reads '3')."""
    return rules.text_of(value)


def parse_code(text, doc_units):
    """A matrix cell as {'type', 'tolerance' (document units), 'code'} or None for a blank
    cell. Raises ValueError with a sentence when it does not read."""
    raw = cell_text(text)
    if not raw:
        return None
    match = _CODE.match(raw)
    if not match:
        raise ValueError('"%s" is not a test code; use H, HC, C or D, like H 10mm.' % raw)
    word = ' '.join(match.group(1).lower().split())
    test_type = _CODE_TYPE[word]
    rest = match.group(2).strip()
    tolerance = None
    if rest:
        tolerance = units.parse_length(rest, doc_units)
        if tolerance is None:
            raise ValueError('"%s" is not a length; write it like 10mm, 1/2" or 0.01m.' % rest)
    if test_type == 'clearance' and not tolerance:
        raise ValueError('A clearance test needs a distance, like C 50mm.')
    return {'type': test_type, 'tolerance': tolerance or 0.0, 'code': raw}


def code_for(test_type, tolerance, doc_units):
    """The shortest code that reads back as this test ('H', 'C 50 mm')."""
    short = _SHORT.get(test_type, 'H')
    if not tolerance:
        return short
    return '%s %s' % (short, defs.length_text(tolerance, doc_units).replace(' ', ''))


# ---- pure: the Trades sheet ----------------------------------------------------------------


def classify_source(text):
    """One Source cell as a source dict ({'kind': 'set'|'model'|'search', ...}).
    Raises ValueError with a sentence when it cannot be used."""
    raw = str(text or '').strip()
    if not raw:
        raise ValueError('The source is empty.')
    lowered = raw.lower()
    for prefix, kind in (('set:', 'set'), ('folder:', 'folder'), ('model:', 'model'),
                         ('search:', 'search')):
        if lowered.startswith(prefix):
            rest = raw[len(prefix):].strip()
            if not rest:
                raise ValueError('"%s" names nothing after the colon.' % raw)
            if kind == 'set':
                return {'kind': 'set', 'path': rest, 'folder': False, 'search': None}
            if kind == 'folder':
                return {'kind': 'set', 'path': rest, 'folder': True, 'search': None}
            if kind == 'model':
                return {'kind': 'model', 'name': rest}
            return condition_source(rest)
    lines = [line.strip() for line in raw.replace('\r', '\n').split('\n') if line.strip()]
    if len(lines) > 1:
        return condition_source(raw)
    try:
        rules.parse_cell(raw)
    except ValueError:
        return {'kind': 'set', 'path': raw, 'folder': False, 'search': None}
    return condition_source(raw)


def condition_source(text):
    """A 'search' source from one or more condition lines (ANDed)."""
    lines = [line.strip() for line in str(text).replace('\r', '\n').split('\n') if line.strip()]
    conds = []
    for line in lines:
        cond = rules.parse_cell(line)
        problems = rules.validate(cond)
        if problems:
            raise ValueError('%s: %s' % (line, problems[0]))
        if not cond.get('category'):
            raise ValueError('"%s" needs a category, like Element > Category = Ducts.' % line)
        conds.append(cond)
    plan = rules.native_plan(conds, numbers_as_text=True, max_groups=4)
    if plan is None:
        raise ValueError('Navisworks cannot search for "%s"; use =, !=, contains, like, '
                         'numbers, exists, is missing or is one of.' % ' and '.join(lines))
    label = ' and '.join(rules.describe(c) for c in conds)
    return {'kind': 'search', 'query': defs.query_from_plan(plan), 'label': label}


def _header_columns(row):
    """(trade_col, source_col) when this row is the Trades header, else None."""
    texts = [cell_text(v).lower() for v in row]
    if 'trade' not in texts:
        return None
    trade_col = texts.index('trade')
    for word in ('source', 'selection', 'set', 'condition', 'search'):
        if word in texts:
            return trade_col, texts.index(word)
    return trade_col, trade_col + 1


def read_trades(rows):
    """The Trades sheet: ([(trade, [(source_text, cell)])] in sheet order, problems).
    A blank Trade continues the trade above; a trade named twice gathers both rows."""
    rows = [list(r) for r in rows or []]
    start, trade_col, source_col = 0, 0, 1
    for index, row in enumerate(rows[:10]):
        found = _header_columns(row)
        if found is not None:
            start, (trade_col, source_col) = index + 1, found
            break
    order = []
    sources = {}
    problems = []
    current = None
    for r in range(start, len(rows)):
        row = rows[r]
        trade = cell_text(row[trade_col]) if trade_col < len(row) else ''
        source = cell_text(row[source_col]) if source_col < len(row) else ''
        if trade:
            current = trade
            key = trade.lower()
            if key not in sources:
                sources[key] = (trade, [])
                order.append(key)
        if not source:
            if trade:
                problems.append('Trades %s: %s has no source.' % (cell_ref(r, source_col), trade))
            continue
        if current is None:
            problems.append('Trades %s: a source with no trade above it.' % cell_ref(r, source_col))
            continue
        sources[current.lower()][1].append((source, cell_ref(r, source_col)))
    out = []
    for key in order:
        trade, items = sources[key]
        if items:
            out.append((trade, items))
    return out, problems


def trade_sources(trades):
    """{trade lower: (trade, [source dicts], [problems])} from read_trades output."""
    out = {}
    for trade, items in trades:
        dicts = []
        problems = []
        for text, ref in items:
            try:
                dicts.append(classify_source(text))
            except ValueError as error:
                problems.append('Trades %s: %s' % (ref, error))
        out[trade.lower()] = (trade, dicts, problems)
    return out


# ---- pure: the Matrix sheet ----------------------------------------------------------------


def read_matrix(rows, doc_units):
    """([{'a', 'b', 'type', 'tolerance', 'code', 'cell'}], problems) from the Matrix sheet.
    Row 1 (the first non-empty row) holds the column trades from column B on."""
    rows = [list(r) for r in rows or []]
    header = None
    for index, row in enumerate(rows):
        if any(cell_text(v) for v in row):
            header = index
            break
    if header is None:
        return [], ['The Matrix sheet is empty.']
    columns = [cell_text(v) for v in rows[header]]
    entries = []
    problems = []
    for r in range(header + 1, len(rows)):
        row = rows[r]
        if not row:
            continue
        trade_a = cell_text(row[0]) if row else ''
        for c in range(1, len(row)):
            try:
                spec = parse_code(row[c], doc_units)
            except ValueError as error:
                problems.append('Matrix %s: %s' % (cell_ref(r, c), error))
                continue
            if spec is None:
                continue
            trade_b = columns[c] if c < len(columns) else ''
            if not trade_a or not trade_b:
                problems.append('Matrix %s: the code has no trade %s.'
                                % (cell_ref(r, c), 'row' if not trade_a else 'column'))
                continue
            spec.update({'a': trade_a, 'b': trade_b, 'cell': cell_ref(r, c)})
            entries.append(spec)
    return entries, problems


def plan_tests(trades_by_key, entries, name_template, doc_units, values=None):
    """The tests the matrix asks for: ([{'name', 'a', 'b', 'type', 'tolerance_m',
    'tolerance', 'cell', 'code'}], problems, notes). trades_by_key is trade_sources()
    output. A mirror cell repeating the same code is made once (noted). Names come
    from name_template (tokens {a} {b} {type} {code} {tolerance} {n} plus values) and
    are made unique among themselves."""
    template = name_template or DEFAULT_NAME
    tests = []
    problems = []
    notes = []
    made = {}
    for entry in entries:
        missing = [t for t in (entry['a'], entry['b']) if t.lower() not in trades_by_key]
        if missing:
            problems.append('Matrix %s: %s is not on the Trades sheet.' % (entry['cell'], missing[0]))
            continue
        a_name = trades_by_key[entry['a'].lower()][0]
        b_name = trades_by_key[entry['b'].lower()][0]
        signature = (entry['type'], round(float(entry['tolerance']), 9))
        pair = tuple(sorted([a_name.lower(), b_name.lower()]))
        if (pair, signature) in made:
            notes.append('Matrix %s repeats %s; that test is made once.'
                         % (entry['cell'], made[(pair, signature)]))
            continue
        made[(pair, signature)] = entry['cell']
        tests.append({'a': a_name, 'b': b_name, 'type': entry['type'],
                      'tolerance': entry['tolerance'],
                      'tolerance_m': units.to_meters(entry['tolerance'], doc_units),
                      'cell': entry['cell'], 'code': entry.get('code', '')})
    names = []
    for index, test in enumerate(tests):
        tokens = dict(values or {})
        tokens.update({'a': test['a'], 'b': test['b'], 'type': defs.TYPE_LABELS[test['type']],
                       'code': test['code'],
                       'tolerance': defs.length_text(test['tolerance'], doc_units)
                       if test['tolerance'] else ''})
        text, _missing = naming.render(template, tokens, counter=index + 1)
        names.append(defs.safe_test_name(text) or '%s vs %s' % (test['a'], test['b']))
    for test, name in zip(tests, defs.unique_test_names(names)):
        test['name'] = name
    return tests, problems, notes


def read_workbook(path, doc_units, reader=None):
    """(trades_by_key, entries, problems) from a workbook path. reader(path, sheet)
    defaults to pynavis.xl.read; sheet names are matched ignoring case."""
    if reader is None:
        from pynavis import xl
        reader = xl.read
        sheet_names = xl.sheets(path)
    else:
        sheet_names = [SHEET_TRADES, SHEET_MATRIX]

    def find(name):
        for sheet in sheet_names:
            if sheet.strip().lower() == name.lower():
                return sheet
        return None

    problems = []
    trades_sheet = find(SHEET_TRADES)
    matrix_sheet = find(SHEET_MATRIX)
    if trades_sheet is None or matrix_sheet is None:
        missing = [n for n, s in ((SHEET_TRADES, trades_sheet), (SHEET_MATRIX, matrix_sheet)) if s is None]
        return {}, [], ['The workbook has no %s sheet. Write a template to start from.'
                        % ' or '.join('"%s"' % m for m in missing)]
    trades, trade_problems = read_trades(reader(path, trades_sheet))
    entries, matrix_problems = read_matrix(reader(path, matrix_sheet), doc_units)
    by_key = trade_sources(trades)
    problems.extend(trade_problems)
    for key in sorted(by_key):
        problems.extend(by_key[key][2])
    problems.extend(matrix_problems)
    return by_key, entries, problems


# ---- pure: the template workbook ----------------------------------------------------------

HELP_LINES = [
    'How this workbook builds clash tests',
    '',
    'Trades sheet: one row per source. A row with a blank Trade adds a source to the trade above.',
    'Sources: "Set: Folder/Name" (a selection set), "Folder: Name" (every set in a folder),',
    '"Model: file.nwc" (a whole model, * and ? allowed), or a property condition such as',
    '"Element > Category = Ducts". Several condition lines in one cell must all match.',
    'Conditions become search sets in the "Clash Matrix" set folder, so tests follow model updates.',
    '',
    'Matrix sheet: the cell in row X, column Y builds the test "X vs Y".',
    'H = hard, H 10mm = hard ignoring overlaps up to 10 mm, HC = hard (conservative),',
    'C 50mm = clearance (the distance is required), D = duplicates. Leave a cell blank for no test.',
    'A bare number is in the document units (%s). A mirror cell with the same code is made once.',
    '',
    'Trade names in the Matrix must match the Trades sheet. Add rows and columns as you need.',
]


def write_template(path, trade_rows, doc_units, title='Clash matrix', author=None):
    """Writes the template workbook. trade_rows: [(trade, source, note)]. Returns path."""
    from namo import xlsx
    wb = xlsx.Workbook(title=title, author=author)
    wb.style('diagonal', fill='F2F2F2', border=True, align='center')
    wb.style('code', border=True, align='center')
    wb.style('rowhead', bold=True, border=True)
    wb.style('colhead', bold=True, border=True, align='center', valign='bottom', wrap=True)

    help_sheet = wb.sheet(SHEET_HELP)
    help_sheet.title(HELP_LINES[0], span=1)
    help_sheet.set_width(0, 110)
    for line in HELP_LINES[1:]:
        text = line % units.doc_unit_symbol(doc_units) if '%s' in line else line
        help_sheet.row([text])

    trades_sheet = wb.sheet(SHEET_TRADES)
    trades_sheet.columns([('Trade', 26, None), ('Source', 56, None), ('Notes', 36, 'muted')])
    names = []
    for trade, source, note in trade_rows:
        trades_sheet.row([trade, source, note or ''])
        if trade and trade.lower() not in [n.lower() for n in names]:
            names.append(trade)
    trades_sheet.autofilter()

    matrix = wb.sheet(SHEET_MATRIX)
    matrix.row([''] + names, styles=[None] + ['colhead'] * len(names), height=48)
    matrix.set_width(0, 26)
    for c in range(len(names)):
        matrix.set_width(c + 1, 14)
    for r, name in enumerate(names):
        styles = ['rowhead'] + ['diagonal' if c == r else 'code' for c in range(len(names))]
        matrix.row([name] + [None] * len(names), styles=styles)
    matrix.freeze(1, 1)
    return wb.save(path)


# ==== API half (Navisworks only; lazy imports) =============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def template_rows(doc=None):
    """[(trade, source, note)] for the template: every selection set (folders skipped),
    then every model as a whole-model trade named by its discipline when one reads."""
    from pynavis import sets
    from namo import items as _items
    from namo import trades
    document = _doc(doc)
    out = []
    taken = []
    rows = sets.snapshot(document)
    names = dict((row['key'], row['name']) for row in rows)
    for row in rows:
        if row['is_folder']:
            continue
        chain = []
        key = row['key']
        while key:
            chain.append(names.get(key, ''))
            key = key.rpartition('/')[0]
        chain.reverse()
        trade = naming.unique(row['name'], taken)
        taken.append(trade)
        out.append((trade, 'Set: %s' % defs.join_set_path(chain),
                    'Search set' if row['has_search'] else 'Static set'))
    try:
        rules_list = trades.rules_from_config()
    except Exception:
        rules_list = None
    for model in _items.models(document):
        name = model['name']
        if not name:
            continue
        trade = trades.trade_of(name, rules_list)
        if trade == trades.UNASSIGNED:
            trade = name.rsplit('.', 1)[0]
        trade = naming.unique(trade, taken)
        taken.append(trade)
        out.append((trade, 'Model: %s' % name, 'Whole model'))
    return out


def own_set(name, doc=None):
    """The set this tool made for `name` in the root 'Clash Matrix' folder, or None.
    pynavis.sets.create de-duplicates names across the whole document, so the set may
    carry a ' (2)' suffix when a set of that name lives elsewhere: that is matched too."""
    from pynavis._api import Api
    document = _doc(doc)
    folder = None
    for child in document.SelectionSets.RootItem.Children:
        if isinstance(child, Api.FolderItem) and child.DisplayName == SET_FOLDER:
            folder = child
            break
    if folder is None:
        return None
    pattern = re.compile(r'^%s(?: \(\d+\))?$' % re.escape(name), re.IGNORECASE)
    for child in folder.Children:
        if not isinstance(child, Api.FolderItem) and pattern.match(child.DisplayName or ''):
            return child
    return None


def ensure_search_sets(trade, source, doc=None):
    """Turns a 'search' source into set sources: one search set per OR group in the
    'Clash Matrix' folder, created or updated in place. Returns [set source dicts]."""
    from pynavis import sets
    document = _doc(doc)
    queries = defs.single_group_queries(source['query'])
    out = []
    for index, query in enumerate(queries):
        name = trade if len(queries) == 1 else '%s %d' % (trade, index + 1)
        name = name.replace('/', '-')
        existing = own_set(name, document)
        if existing is not None:
            live = sets.update(existing, query, document)
        else:
            live = sets.create(name, query, folder=SET_FOLDER, doc=document)
        out.append({'kind': 'set', 'path': defs.set_path_of(live, document), 'folder': False,
                    'search': query})
    return out


def build(tests, trades_by_key, existing='skip', doc=None, progress=None):
    """Creates or updates every planned test in ONE undo step. Returns rows
    [{'name', 'a', 'b', 'type', 'tolerance_m', 'outcome' ('created' | 'updated' |
    'skipped' | 'failed'), 'detail', 'test' (live or None), 'linked' (bool)}].
    progress(fraction, label) only reports: a write is never stopped halfway."""
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    out = []
    side_cache = {}
    total = len(tests) or 1
    with transaction('Clash matrix', document):
        for index, test in enumerate(tests):
            if progress is not None:
                progress(float(index) / total, 'Building %s' % test['name'])
            row = {'name': test['name'], 'a': test['a'], 'b': test['b'], 'type': test['type'],
                   'tolerance_m': test['tolerance_m'], 'outcome': 'failed', 'detail': '',
                   'test': None, 'linked': False}
            out.append(row)
            sides = []
            problems = []
            for trade in (test['a'], test['b']):
                key = trade.lower()
                if key not in side_cache:
                    side_cache[key] = _trade_side(trades_by_key[key], document)
                side, resolved, side_problems = side_cache[key]
                sides.append((side, resolved))
                problems.extend(side_problems)
            if problems:
                row['detail'] = problems[0]
                continue
            definition = defs.new_definition(test['name'], test['type'], test['tolerance_m'],
                                             sides[0][0], sides[1][0])
            try:
                outcome, live = defs.write_test(definition, sides[0][1], sides[1][1], existing,
                                                document)
            except Exception as error:
                row['detail'] = str(error)
                continue
            row['outcome'] = outcome
            row['test'] = live
            notes = sides[0][1]['notes'] + sides[1][1]['notes']
            if outcome == 'skipped':
                row['detail'] = 'A test with this name already exists.'
            elif notes:
                row['detail'] = notes[0]
            if live is not None and outcome != 'skipped':
                row['linked'] = defs.references_sets(live)
    if progress is not None:
        progress(1.0, 'Done')
    return out


def _trade_side(entry, document):
    """(side, resolved, problems) for one trade, turning searches into sets first."""
    trade, sources, problems = entry
    problems = list(problems)
    final = []
    for source in sources:
        if source['kind'] == 'search':
            try:
                final.extend(ensure_search_sets(trade, source, document))
            except Exception as error:
                problems.append('%s: the search set could not be saved (%s).' % (trade, error))
        else:
            final.append(source)
    side = defs.new_side(final)
    if not final:
        problems.append('%s has no usable source.' % trade)
        return side, None, problems
    resolved = defs.resolve_side(side, document)
    problems.extend(resolved['missing'])
    return side, resolved, problems

# -*- coding: utf-8 -*-
"""Writing properties: Bulk Property Writer, Find and Replace, Property Mapper and
External Data Link.

Navisworks' own properties are read-only; what can be written are custom (user) tabs
through pynavis.props.set_custom, which REPLACES a whole tab per item. Every writer here
therefore reads the item's current tab, merges, and writes the merged tab back, all
inside ONE pynavis.viewpoints.transaction (props.set_custom's own transaction is skipped
while one is active, so a whole run is one undo step; that COM writes join the .NET undo
step is pynavis' documented, still unverified assumption).

Pure half (tested): value inference, 'Name = Value' lines, merging, spreadsheet keys and
row plans, matching, find/replace planning, mapping profiles (a one-line-per-field text
grammar), coverage, data link records.
API half: key indexes over model items, table reading (xlsx/csv), the batched writer,
custom-tab detection, find/replace scanning, mapping, data link refresh.
"""

import csv
import io
import os
import re
import time

from namo import naming

DEFAULT_TAB = 'Playground'
CORRECTED_TAB = 'Playground Corrected'
STANDARD_TAB = 'Standard'
MAX_LINES = 10
INT32 = 2147483647
USER_TAB_NAME = 'LcOaPropOverrideCat'     # internal name of user-defined tabs (UNVERIFIED)

KEY_ELEMENT_ID = 'element_id'
KEY_GUID = 'guid'
_ELEMENT_ID_HEADERS = ('element id', 'elementid', 'element_id', 'revit id', 'revit element id', 'id')
_GUID_HEADERS = ('guid', 'ifc guid', 'ifcguid', 'ifc globalid', 'globalid', 'global id', 'uniqueid',
                 'unique id', 'revit uniqueid', 'ifc_guid')


# =============================================================================
# Pure: values and 'Name = Value' lines
# =============================================================================

_INT_RE = re.compile(r'^[+-]?(0|[1-9]\d*)$')
_FLOAT_RE = re.compile(r'^[+-]?(\d+\.\d*|\.\d+|\d+(\.\d*)?[eE][+-]?\d+)$')


def infer_value(text):
    """A typed value for what a user typed: '12' -> 12, '1.5' -> 1.5, 'true'/'false' ->
    bool, '"007"' -> '007' (quotes force text), leading zeros stay text, else text."""
    if text is None:
        return ''
    raw = str(text).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in '"\'':
        return raw[1:-1]
    lowered = raw.lower()
    if lowered in ('true', 'false'):
        return lowered == 'true'
    if _INT_RE.match(raw):
        number = int(raw)
        if -INT32 - 1 <= number <= INT32:
            return number
        return raw
    if _FLOAT_RE.match(raw):
        try:
            return float(raw)
        except ValueError:
            return raw
    return raw


def value_label(value):
    """How a typed value reads in a preview: 12, 1.5, Yes/No, "text"."""
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (int, float)):
        return ('%r' % value) if isinstance(value, float) else str(value)
    return '"%s"' % value


def parse_lines(text, limit=MAX_LINES):
    """([(name, value)], [problems]) from 'Name = Value' lines (blank lines and lines
    starting with # ignored). A repeated name keeps the last value."""
    pairs = []
    problems = []
    index_of = {}
    for number, line in enumerate((text or '').splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if '=' not in stripped:
            problems.append('Line %d needs a name and a value: Name = Value.' % number)
            continue
        name, value = stripped.split('=', 1)
        name = ' '.join(name.split())
        if not name:
            problems.append('Line %d has no property name before the equals sign.' % number)
            continue
        typed = infer_value(value)
        if name.lower() in index_of:
            position = index_of[name.lower()]
            pairs[position] = (pairs[position][0], typed)
            continue
        index_of[name.lower()] = len(pairs)
        pairs.append((name, typed))
    if len(pairs) > limit:
        problems.append('Write at most %d properties at a time (%d given).' % (limit, len(pairs)))
    if not pairs and not problems:
        problems.append('Type at least one line like Status = Approved.')
    return pairs, problems


def format_lines(pairs):
    """'Name = Value' lines (text values that would read as numbers get quotes)."""
    lines = []
    for name, value in pairs:
        if isinstance(value, bool):
            text = 'true' if value else 'false'
        elif isinstance(value, (int, float)):
            text = repr(value) if isinstance(value, float) else str(value)
        else:
            text = str(value)
            if infer_value(text) != text:
                text = '"%s"' % text
        lines.append('%s = %s' % (name, text))
    return '\n'.join(lines)


def writable(value):
    """A value props.set_custom accepts (str/int/float/bool); None becomes ''; ints
    outside Int32 and anything else become text."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if -INT32 - 1 <= value <= INT32 else str(value)
    if isinstance(value, float):
        if value != value or value in (float('inf'), float('-inf')):
            return str(value)
        return value
    return str(value)


def merge(existing, new, replace=False):
    """The tab to write: existing values (a dict or None) overlaid with new, or only
    new when replace. Every value made writable()."""
    out = {}
    if existing and not replace:
        for name, value in existing.items():
            out[name] = writable(value)
    for name, value in new.items():
        out[name] = writable(value)
    return out


def same_tab(existing, wanted):
    """True when writing wanted would change nothing (text-compared)."""
    if existing is None:
        return False
    if set(existing) != set(wanted):
        return False
    for name in wanted:
        if str(writable(existing[name])) != str(wanted[name]):
            return False
    return True


# =============================================================================
# Pure: spreadsheets
# =============================================================================


def key_kind(header):
    """'element_id', 'guid', ('prop', category, property) or None for a header."""
    text = ' '.join(str(header or '').split())
    lowered = text.lower()
    if lowered in _ELEMENT_ID_HEADERS:
        return KEY_ELEMENT_ID
    if lowered in _GUID_HEADERS:
        return KEY_GUID
    if '>' in text:
        category, prop = text.split('>', 1)
        if category.strip() and prop.strip():
            return ('prop', category.strip(), prop.strip())
    return None


def key_label(kind):
    if kind == KEY_ELEMENT_ID:
        return 'Element ID'
    if kind == KEY_GUID:
        return 'GUID'
    if isinstance(kind, (tuple, list)) and len(kind) == 3:
        return '%s > %s' % (kind[1], kind[2])
    return str(kind)


def detect_key(headers):
    """(column index, kind) of the first header that names a key, or (None, None)."""
    for index, header in enumerate(headers):
        kind = key_kind(header)
        if kind is not None:
            return index, kind
    return None, None


def cell_text(value):
    """A spreadsheet cell as key text: 123456.0 -> '123456', trimmed."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return str(value).strip()


def normalise_key(text, kind):
    """Key text as compared: GUIDs lowercase without braces, everything trimmed and
    case-folded."""
    text = cell_text(text)
    if kind == KEY_GUID:
        return text.strip('{}').lower()
    return text.lower()


def cell_value(value):
    """A spreadsheet cell as a value to write: integral floats become ints, text stays
    text, blanks are None (not written)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value == int(value) and abs(value) <= INT32:
            return int(value)
        return value
    if isinstance(value, int):
        return writable(value)
    text = str(value)
    return text if text.strip() else None


def headers_of(rows):
    """(header texts, data rows): the first non-blank row is the header."""
    for index, row in enumerate(rows):
        if any(cell_text(c) for c in row):
            headers = [cell_text(c) for c in row]
            return headers, rows[index + 1:]
    return [], []


def plan_rows(headers, rows, key_index, kind, columns):
    """The spreadsheet as write instructions:
    {'rows': [{'row': excel row number, 'key': normalised key, 'raw': key text,
               'values': {column: value}}], 'blank': [row numbers], 'duplicates': [(row,
     earlier row)]}. columns: header names to bring in (key column excluded). A key
    repeated in a later row wins (and is reported)."""
    wanted = [(i, h) for i, h in enumerate(headers) if h in columns and i != key_index]
    out = []
    blank = []
    duplicates = []
    seen = {}
    for offset, row in enumerate(rows):
        number = offset + 2
        raw = cell_text(row[key_index]) if key_index < len(row) else ''
        if not raw:
            if any(cell_text(c) for c in row):
                blank.append(number)
            continue
        values = {}
        for index, header in wanted:
            value = cell_value(row[index]) if index < len(row) else None
            if value is not None:
                values[header] = value
        key = normalise_key(raw, kind)
        entry = {'row': number, 'key': key, 'raw': raw, 'values': values}
        if key in seen:
            duplicates.append((number, out[seen[key]]['row']))
            out[seen[key]] = entry
            continue
        seen[key] = len(out)
        out.append(entry)
    return {'rows': out, 'blank': blank, 'duplicates': duplicates}


def match_rows(plan_entries, index):
    """Matches row entries against index {key: [items]}: returns {'matched': [(entry,
    items)], 'unmatched': [entry], 'ambiguous': [(entry, items)]} (ambiguous rows
    matched more than one item and are in matched too)."""
    matched = []
    unmatched = []
    ambiguous = []
    for entry in plan_entries:
        found = index.get(entry['key'])
        if not found:
            unmatched.append(entry)
            continue
        matched.append((entry, found))
        if len(found) > 1:
            ambiguous.append((entry, found))
    return {'matched': matched, 'unmatched': unmatched, 'ambiguous': ambiguous}


def preview_rows(plan, matching):
    """Rows for the preview table: [{'cells': [row, key, outcome, values], 'value': row}]
    in spreadsheet order."""
    outcome = {}
    for entry, found in matching['matched']:
        if len(found) > 1:
            outcome[entry['row']] = 'Matches %d items' % len(found)
        else:
            outcome[entry['row']] = 'Matched'
    for entry in matching['unmatched']:
        outcome[entry['row']] = 'Not found'
    late = dict((row, earlier) for row, earlier in plan['duplicates'])
    rows = []
    for entry in sorted(plan['rows'], key=lambda e: e['row']):
        text = outcome.get(entry['row'], '')
        if entry['row'] in late:
            text += ', replaces row %d' % late[entry['row']]
        values = ', '.join('%s = %s' % (k, entry['values'][k])
                           for k in sorted(entry['values'], key=naming.natural_key))
        rows.append({'cells': [entry['row'], entry['raw'], text, values], 'value': entry['row']})
    return rows


def unmatched_sheet(headers, rows, plan, matching, key_index):
    """(headers, rows) of the spreadsheet rows that matched nothing, with their row
    number first, for the export back to Excel."""
    wanted = set(entry['row'] for entry in matching['unmatched'])
    out = []
    for offset, row in enumerate(rows):
        number = offset + 2
        if number in wanted:
            cells = list(row) + [''] * (len(headers) - len(row))
            out.append([number] + cells[:len(headers)])
    return ['Row'] + list(headers), out


# =============================================================================
# Pure: find and replace
# =============================================================================


def compile_find(find, replace, regex=False, match_case=False, whole=False):
    """fn(text) -> new text, or None when text does not match (or would not change).
    Raises ValueError with a readable sentence for a bad pattern or empty find."""
    if find is None or find == '':
        raise ValueError('Type the text to find.')
    flags = 0 if match_case else re.IGNORECASE
    if regex:
        try:
            pattern = re.compile(find, flags)
        except re.error as error:
            raise ValueError('The pattern does not read: %s.' % error)
    else:
        pattern = re.compile(re.escape(find), flags)
    replacement = replace or ''
    anchored = re.compile(r'^(?:%s)\Z' % pattern.pattern, flags)
    substitute = replacement if regex else _literal(replacement)

    def apply(text):
        if text is None:
            return None
        if whole:
            if not anchored.match(text):
                return None
            new = anchored.sub(substitute, text, count=1)
        else:
            if not pattern.search(text):
                return None
            new = pattern.sub(substitute, text)
        return new if new != text else None
    return apply


def _literal(replacement):
    return lambda found: replacement


def corrected_name(category, prop):
    """'Element - Mark': the property name used in the corrected tab."""
    return '%s - %s' % (category, prop)


def plan_changes(readings, apply):
    """[change] from readings [(item, category, property, text, is_custom)]:
    {'item', 'category', 'property', 'old', 'new', 'custom'}."""
    out = []
    for item, category, prop, text, custom in readings:
        new = apply(text)
        if new is None:
            continue
        out.append({'item': item, 'category': category, 'property': prop, 'old': text, 'new': new,
                    'custom': bool(custom)})
    return out


def group_changes(changes, corrected_tab=CORRECTED_TAB):
    """[(item, {tab: {property: new value}})] in first-seen item order: custom-tab
    matches edit their own tab, native ones go to the corrected tab as
    '<Category> - <Property>'."""
    order = []
    by_item = {}
    for change in changes:
        key = change['item']
        if key not in by_item:
            by_item[key] = (change['item'], {})
            order.append(key)
        tabs = by_item[key][1]
        if change['custom']:
            tabs.setdefault(change['category'], {})[change['property']] = change['new']
        else:
            tabs.setdefault(corrected_tab, {})[corrected_name(change['category'], change['property'])] = change['new']
    return [by_item[key] for key in order]


def typed_like(old_value, new_text):
    """Keep a custom value's type when the replacement still reads as one."""
    if isinstance(old_value, bool) or not isinstance(old_value, (int, float)):
        return new_text
    typed = infer_value(new_text)
    if isinstance(typed, (int, float)) and not isinstance(typed, bool):
        return typed
    return new_text


# =============================================================================
# Pure: property mapper profiles
# =============================================================================

_FIELD_RE = re.compile(r'^\s*([^\[:]+?)\s*(?:\[([^\]]*)\])?\s*:\s*(.*)$')


def parse_modifier(text):
    """(pattern, replacement or None) from '/pattern/' or '/pattern/replacement/'."""
    text = text.strip()
    if len(text) < 2 or text[0] != '/' or text[-1] != '/':
        raise ValueError('Write the regex between slashes: /pattern/ or /pattern/replacement/.')
    body = text[1:-1]
    parts = []
    current = ''
    escaped = False
    for ch in body:
        if escaped:
            current += ch if ch == '/' else '\\' + ch
            escaped = False
        elif ch == '\\':
            escaped = True
        elif ch == '/':
            parts.append(current)
            current = ''
        else:
            current += ch
    if escaped:
        current += '\\'
    parts.append(current)
    if len(parts) > 2:
        raise ValueError('Use at most one slash between the pattern and the replacement (escape others as \\/).')
    pattern = parts[0]
    try:
        re.compile(pattern)
    except re.error as error:
        raise ValueError('The pattern does not read: %s.' % error)
    return pattern, (parts[1] if len(parts) == 2 else None)


def parse_profile(text):
    """(profile, problems). One field per line:

        System: Element > System Name | IFC > SystemName | Item > Layer
        Level: Element > Level | Element > Reference Level ~ /^Level (\\d+)/L\\1/
        Level [ARCH*.rvt]: Element > Base Constraint

    Sources are tried in order (the first one present and not blank wins); '~ /re/'
    extracts (group 1, else the whole match) and '~ /re/replacement/' rewrites;
    '[model]' makes the line apply only to models whose file name matches (* and ?
    allowed). 'tab: Name' sets the tab written (default Standard). # starts a comment."""
    profile = {'tab': STANDARD_TAB, 'fields': []}
    problems = []
    names = []
    for number, line in enumerate((text or '').splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        found = _FIELD_RE.match(stripped)
        if not found:
            problems.append('Line %d: write Field: Category > Property | Category > Property.' % number)
            continue
        name, model, rest = found.group(1).strip(), (found.group(2) or '').strip(), found.group(3)
        if name.lower() == 'tab' and not model:
            if rest.strip():
                profile['tab'] = rest.strip()
            else:
                problems.append('Line %d: the tab needs a name.' % number)
            continue
        modifier = None
        if ' ~ ' in rest or rest.strip().startswith('~'):
            rest, _sep, modifier = rest.partition('~')
        sources = []
        for part in rest.split('|'):
            part = part.strip()
            if not part:
                continue
            if '>' not in part:
                problems.append('Line %d: source "%s" needs Category > Property.' % (number, part))
                continue
            category, prop = part.split('>', 1)
            if not category.strip() or not prop.strip():
                problems.append('Line %d: source "%s" needs Category > Property.' % (number, part))
                continue
            sources.append([category.strip(), prop.strip()])
        if not sources:
            problems.append('Line %d: field %s has no sources.' % (number, name))
            continue
        pattern, replacement = '', None
        if modifier is not None:
            try:
                pattern, replacement = parse_modifier(modifier)
            except ValueError as error:
                problems.append('Line %d: %s' % (number, error))
                continue
        profile['fields'].append({'name': name, 'model': model, 'sources': sources,
                                  'pattern': pattern, 'replace': replacement})
        if name.lower() not in [n.lower() for n in names]:
            names.append(name)
    if not profile['fields'] and not problems:
        problems.append('Add at least one field, like System: Element > System Name.')
    return profile, problems


def format_profile(profile):
    """The text parse_profile reads back."""
    lines = []
    tab = profile.get('tab') or STANDARD_TAB
    if tab != STANDARD_TAB:
        lines.append('tab: %s' % tab)
    for field in profile.get('fields') or []:
        head = field['name'] + (' [%s]' % field['model'] if field.get('model') else '')
        sources = ' | '.join('%s > %s' % (c, p) for c, p in field['sources'])
        text = '%s: %s' % (head, sources)
        if field.get('pattern'):
            pattern = field['pattern'].replace('/', '\\/')
            if field.get('replace') is not None:
                text += ' ~ /%s/%s/' % (pattern, field['replace'].replace('/', '\\/'))
            else:
                text += ' ~ /%s/' % pattern
        lines.append(text)
    return '\n'.join(lines)


def field_names(profile):
    """Distinct field names in first-appearance order."""
    out = []
    for field in profile.get('fields') or []:
        if field['name'] not in out:
            out.append(field['name'])
    return out


def _model_matches(pattern, model_name):
    from namo import rules
    return rules.wildcard_regex(pattern, True).match(model_name or '') is not None


def resolve_field(profile, name, model_name):
    """The field spec that applies to a model: the first line for that field whose
    [model] pattern matches, else its line without one (None when neither)."""
    default = None
    for field in profile.get('fields') or []:
        if field['name'] != name:
            continue
        if field.get('model'):
            if _model_matches(field['model'], model_name):
                return field
        elif default is None:
            default = field
    return default


def apply_modifier(text, pattern, replacement):
    """The mapped text after the field's regex: extract (group 1 or the match) or
    rewrite; None when the pattern does not match."""
    if not pattern:
        return text
    compiled = re.compile(pattern)
    if replacement is None:
        found = compiled.search(text)
        if not found:
            return None
        return found.group(1) if found.groups() and found.group(1) is not None else found.group(0)
    if not compiled.search(text):
        return None
    return compiled.sub(replacement, text)


def map_values(profile, read_text, model_name):
    """{field: (value or None, source 'Category > Property' or None)} for one item.
    read_text(category, property) -> display text or None (missing / no value)."""
    out = {}
    for name in field_names(profile):
        field = resolve_field(profile, name, model_name)
        result = (None, None)
        if field is not None:
            for category, prop in field['sources']:
                text = read_text(category, prop)
                if text is None or not str(text).strip():
                    continue
                mapped = apply_modifier(str(text), field.get('pattern'), field.get('replace'))
                if mapped is None or not mapped.strip():
                    continue
                result = (mapped.strip(), '%s > %s' % (category, prop))
                break
        out[name] = result
    return out


def coverage(records, fields):
    """[(model, field, items, mapped, share)] from records [(model, {field: (value,
    source)})], models and fields in natural / profile order."""
    counts = {}
    models = []
    for model, mapped in records:
        if model not in models:
            models.append(model)
        for name in fields:
            key = (model, name)
            total, hits = counts.get(key, (0, 0))
            value = mapped.get(name, (None, None))[0]
            counts[key] = (total + 1, hits + (1 if value is not None else 0))
    models.sort(key=lambda m: (naming.natural_key(m), m))
    out = []
    for model in models:
        for name in fields:
            total, hits = counts.get((model, name), (0, 0))
            out.append((model, name, total, hits, float(hits) / total if total else 0.0))
    return out


# =============================================================================
# Pure: data links
# =============================================================================


def new_link(name, source, sheet, key_column, key, columns, tab):
    """A data link record (see the module docstring for the fields)."""
    return {'id': '', 'name': name, 'source': source, 'sheet': sheet or '',
            'key_column': key_column, 'key': key_label(key),
            'columns': list(columns), 'tab': tab, 'created': time.strftime('%Y-%m-%d %H:%M'),
            'last_refresh': '', 'file_mtime': None, 'stats': {}, 'unmatched_items': []}


def link_key_kind(link):
    """The key kind of a link's model key text ('Element ID', 'GUID', 'Cat > Prop')."""
    kind = key_kind(link.get('key'))
    return kind if kind is not None else key_kind('Element ID')


def link_state(link, mtime):
    """'Not refreshed yet' / 'Source file missing' / 'File changed since the last
    refresh' / 'Up to date'."""
    if mtime is None:
        return 'Source file missing'
    if not link.get('last_refresh'):
        return 'Not refreshed yet'
    stored = link.get('file_mtime')
    if stored is None or abs(float(stored) - float(mtime)) > 1.0:
        return 'File changed since the last refresh'
    return 'Up to date'


def time_text(stamp):
    """'2026-10-05 14:30' for a file time (seconds), '' for None."""
    if stamp is None:
        return ''
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(float(stamp)))


def link_rows(links, mtime_of):
    """Table rows for the data link window."""
    rows = []
    for link in links:
        mtime = mtime_of(link.get('source'))
        stats = link.get('stats') or {}
        summary = ''
        if stats:
            summary = '%s matched, %s unmatched, %s changed' % (
                '{:,}'.format(stats.get('matched', 0)), '{:,}'.format(stats.get('unmatched', 0)),
                '{:,}'.format(stats.get('changed', 0)))
        rows.append({'cells': [link.get('name'), os.path.basename(link.get('source') or ''),
                               link.get('key'), link.get('tab'), link.get('last_refresh') or 'Never',
                               time_text(mtime) or 'Missing', link_state(link, mtime), summary],
                     'value': link.get('id')})
    return rows


LINK_HEADERS = ['Link', 'Source file', 'Key', 'Tab', 'Last refresh', 'File saved', 'State',
                'Last result']


# =============================================================================
# API half
# =============================================================================


def is_custom_category(category):
    """True for a user-defined (custom) tab: PropertyCategory.IsEditable, or the
    internal name user tabs carry (both UNVERIFIED in-app)."""
    try:
        if bool(category.IsEditable):
            return True
    except Exception:
        pass
    try:
        # pyNavis' COM writer creates user tabs with the internal name 'pyNavis'.
        return str(category.Name) in (USER_TAB_NAME, 'pyNavis')
    except Exception:
        return False


def custom_tab(item, tab):
    """{name: value} of a custom tab on item, or None (pynavis.props.get_custom)."""
    from pynavis import props
    try:
        return props.get_custom(item, tab)
    except Exception:
        return None


def write_tabs(plan, doc=None, name='Write properties', replace=False, progress=None):
    """Writes [(item, {tab: {property: value}})] merging into each item's existing tab
    (replace=True writes exactly the given values). ONE transaction. Returns
    {'written': items written, 'unchanged': items skipped, 'errors': [sentences]}.
    progress(done, total) after each item; returning False stops early."""
    from pynavis import props, viewpoints
    from namo import propindex
    from pynavis._api import Application
    document = doc if doc is not None else Application.ActiveDocument
    written = unchanged = 0
    errors = []
    total = len(plan)
    try:
        with viewpoints.transaction(name, document):
            for index, (item, tabs) in enumerate(plan):
                wrote = False
                for tab in sorted(tabs):
                    existing = custom_tab(item, tab)
                    values = merge(existing, tabs[tab], replace)
                    if not values or same_tab(existing, values):
                        continue
                    count, failures = props.set_custom([item], tab, values, doc=document)
                    if failures:
                        errors.append('%s: %s' % (_name(item), failures[0]))
                    elif count:
                        wrote = True
                if wrote:
                    written += 1
                else:
                    unchanged += 1
                if progress is not None and progress(index + 1, total) == False:  # noqa: E712
                    break
    finally:
        propindex.invalidate()
    return {'written': written, 'unchanged': unchanged, 'errors': errors}


def remove_tab(item_list, tab, doc=None):
    """Removes a custom tab from items, one undo step: (removed, errors)."""
    from pynavis import props
    from namo import propindex
    try:
        return props.remove_custom(list(item_list), tab, doc=doc)
    finally:
        propindex.invalidate()


def _name(item):
    try:
        return item.DisplayName or item.ClassDisplayName or 'item'
    except Exception:
        return 'item'


def item_keys(item, kind, reader):
    """Normalised key texts an item answers to: element ids, GUIDs (UniqueId, IFC
    GlobalId, and the IFC GUID derived from a UniqueId), or one property's text."""
    from namo import items, propindex
    out = []
    if kind == KEY_ELEMENT_ID or kind == KEY_GUID:
        field_names_ = ['element_id'] if kind == KEY_ELEMENT_ID else ['unique_id', 'ifc_guid']
        for field in field_names_:
            for category, prop in items.REVIT_PROPERTIES[field]:
                exists, vkind, value = reader.one(item, category, prop)
                if exists and value is not None and str(value).strip():
                    out.append(normalise_key(propindex.display_text(vkind, value, reader.ctx), kind))
                    break
        if kind == KEY_GUID and out:
            try:
                from namo import ifcguid
                derived = ifcguid.from_revit_unique_id(out[0])
                out.append(normalise_key(derived, kind))
            except Exception:
                pass
        return items.dedupe(out)
    _tag, category, prop = kind
    exists, vkind, value = reader.one(item, category, prop)
    if exists and value is not None:
        text = propindex.display_text(vkind, value, reader.ctx)
        if text != propindex.NO_VALUE:
            out.append(normalise_key(text, kind))
    return out


def is_revit_element(item):
    """True when the item carries Revit's element category (internal name
    LcRevitData_Element): a real element, not a nested part of a family instance."""
    from namo import items
    try:
        for category in item.PropertyCategories:
            if category.Name == items.REVIT_ELEMENT_CATEGORY:
                return True
    except Exception:
        pass
    return False


def _model_index(item, reader):
    try:
        from pynavis._api import Application
        document = getattr(reader, 'doc', None) or Application.ActiveDocument
        return int(document.Models.CreatePathId(item).ModelIndex)
    except Exception:
        return None


def drop_type_ids(entries):
    """Element ID entries [(item, keys, model, is_element)] without the items that only
    repeat a TYPE's id. Field fact: the nested parts under a Revit family instance carry
    the Element ID tab too, holding the type's id (one number on every instance of the
    type), and only real elements carry the element category. So in a model where real
    elements exist, an id on anything else is dropped; a model whose exporter never
    wrote the category keeps every id (the old rule)."""
    with_elements = set(model for _item, _keys, model, is_element in entries if is_element)
    return [(item, keys) for item, keys, model, is_element in entries
            if is_element or model not in with_elements]


def key_index(item_list, kind, reader, tick=None):
    """{normalised key: [items]} over item_list (namo.items.Ticker tick). Element ID
    keys only index real Revit elements where the model has them (drop_type_ids)."""
    from namo import items
    data = list(item_list)
    ticker = items.Ticker(tick, total=len(data), every=200)
    entries = []
    for item in data:
        keys = item_keys(item, kind, reader)
        if keys:
            if kind == KEY_ELEMENT_ID:
                entries.append((item, keys, _model_index(item, reader), is_revit_element(item)))
            else:
                entries.append((item, keys))
        ticker.step()
    ticker.finish()
    if kind == KEY_ELEMENT_ID:
        entries = drop_type_ids(entries)
    index = {}
    for item, keys in entries:
        for key in keys:
            bucket = index.setdefault(key, [])
            if item not in bucket:
                bucket.append(item)
    return index


def table_sheets(path):
    """Sheet names of a workbook ([''] for a CSV file)."""
    if path.lower().endswith('.csv'):
        return ['']
    from pynavis import xl
    return xl.sheets(path)


def read_table(path, sheet=None):
    """Rows of a sheet (xlsx via pynavis.xl: numbers as float) or a CSV file (UTF-8,
    comma or semicolon, decided from the first line)."""
    if path.lower().endswith('.csv'):
        with io.open(path, 'r', encoding='utf-8-sig', newline='') as handle:
            text = handle.read()
        first = text.split('\n', 1)[0]
        delimiter = ';' if first.count(';') > first.count(',') else ','
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        return [[_csv_cell(c) for c in row] for row in rows]
    from pynavis import xl
    return xl.read(path, sheet or None)


def _csv_cell(text):
    stripped = text.strip()
    if _INT_RE.match(stripped) and len(stripped) < 16:
        return float(stripped)
    if _FLOAT_RE.match(stripped):
        try:
            return float(stripped)
        except ValueError:
            return text
    return text


def scan_find(item_list, apply, reader, only=None, tick=None):
    """Find and Replace readings: every property (or only (category, property)) of
    each item whose display text apply() changes. Returns plan_changes() output with
    'raw' (the original value) added for typed custom edits."""
    from namo import items, propindex
    data = list(item_list)
    ticker = items.Ticker(tick, total=len(data), every=100)
    out = []
    for item in data:
        try:
            categories = item.PropertyCategories
        except Exception:
            ticker.step()
            continue
        for cat in categories:
            cname = cat.DisplayName
            if only is not None and cname != only[0]:
                continue
            custom = None
            for prop in cat.Properties:
                pname = prop.DisplayName
                if only is not None and pname != only[1]:
                    continue
                kind, _vtype, value = propindex.coerce(prop.Value, reader.table)
                value = reader.si(item, kind, value)
                text = propindex.display_text(kind, value, reader.ctx)
                if text == propindex.NO_VALUE:
                    continue
                new = apply(text)
                if new is None:
                    continue
                if custom is None:
                    custom = is_custom_category(cat)
                out.append({'item': item, 'category': cname, 'property': pname, 'old': text,
                            'new': typed_like(value, new) if custom else new, 'custom': custom})
        ticker.step()
    ticker.finish()
    return out


def map_items(profile, item_list, reader, tick=None):
    """[(item, model name, {field: (value, source)})] for the mapper preview."""
    from namo import items, propindex
    data = list(item_list)
    ticker = items.Ticker(tick, total=len(data), every=200)
    out = []
    for item in data:
        model = items.model_name(item)

        def read_text(category, prop, item=item):
            exists, kind, value = reader.one(item, category, prop)
            if not exists:
                return None
            text = propindex.display_text(kind, value, reader.ctx)
            return None if text == propindex.NO_VALUE else text
        out.append((item, model, map_values(profile, read_text, model)))
        ticker.step()
    ticker.finish()
    return out

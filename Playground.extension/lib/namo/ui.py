# -*- coding: utf-8 -*-
"""WPF building blocks for Playground tools, themed from the pyNavis design system.

Everything a tool shows beyond a toast or a pynavis.forms prompt is built here, so
every Playground window looks and behaves the same:

  * Colours come from PyNavis.Runtime.Forms.DesignSystem.Tokens.Current (light or
    dark, following Navisworks) plus the Windows accent, which appears only on the
    primary button, the selection rail, checked boxes and the focus ring. Solid
    surfaces, hairlines, no gradients, no glass, no opacity-as-disabled.
  * Segoe UI Variable, 13 px body, 32 px controls and rows, 8 px gaps, 24 px padding
    (16 px in data-dense windows), 4 px corners.
  * Keyboard first: Tab order follows the layout, Enter is the primary action, Esc
    cancels, Ctrl+F jumps to a filter box, Space ticks rows, arrows move in lists.
  * Every window is owned by the Navisworks main window (FluentChrome.Apply) when
    shown. Modeless windows call ElementHost.EnableModelessKeyboardInterop BEFORE
    Show, live in a session holder (one per key) and wrap every late callback so an
    exception is logged instead of reaching Navisworks.
  * Modal windows refuse to open under `pynavis run` (RunnerContext), with the same
    message pynavis.forms gives; check __runner__ first.

The API in three layers:
  ready-made   form(), choose(), table_window()   (each has a build_* twin that
               returns the unshown Window, which smoke tests and custom code use)
  parts        window(), Table, text(), button(), text_box(), combo(), check(),
               radio_group(), search_box(), footer(), group(), separator()
  plumbing     Modeless, non_activating(), host_rect(), run_later(), Debouncer,
               safe(), copy(), open_path(), show_in_explorer(), show_modal()

The pure half (field specs, parsing, validation, filtering, sorting keys, cell text)
is at the top and unit tested on both engines; nothing .NET is imported at module
level, so `import namo.ui` works anywhere.
"""

import os
import re
import sys
import traceback

FIELD_KINDS = ('text', 'textarea', 'int', 'number', 'length', 'choice', 'radio', 'check',
               'multi', 'file_open', 'file_save', 'folder', 'color', 'date', 'label',
               'separator')
VALUELESS = ('label', 'separator')
PATH_KINDS = ('file_open', 'file_save', 'folder')     # their checks touch the disk or network
SEARCHABLE_OVER = 8           # a 'multi' field gets a filter box past this many options

FONT = 'Segoe UI Variable Text, Segoe UI'
RUNNER_MESSAGE = ('Dialogs are not available under pynavis run. Check __runner__ and skip '
                  'the prompt.')


# =============================================================================
# Pure half
# =============================================================================


def options_of(field):
    """[(label, value)] from a field's 'options' (strings or (label, value) pairs)."""
    out = []
    for option in field.get('options') or []:
        if isinstance(option, (tuple, list)) and len(option) == 2:
            out.append((str(option[0]), option[1]))
        else:
            out.append((str(option), option))
    return out


def normalize_fields(fields):
    """Validated copies of form field specs with defaults filled. Raises ValueError
    naming the problem (unknown kind, missing or duplicate key, choice without
    options, enabled_if naming an unknown key).

    A choice/radio 'default' must be one of the option VALUES (options are strings
    or (label, value) pairs); None means the first option. A default that is not an
    option raises, because the window would open with nothing chosen: that is what
    options written as (value, label) look like. A default read from saved settings
    can be stale for good reasons (the set was deleted, the option list changed), so
    such a field also gives 'fallback': a value (or None for the first option) used
    instead of raising when the default is not offered. An enabled_if on a
    choice/radio field must compare with a value that field offers (a list needs at
    least one), and on a check field with True or False: anything else could never
    switch."""
    out = []
    keys = set()
    for index, raw in enumerate(fields or []):
        if not isinstance(raw, dict):
            raise ValueError('field %d is not a dict' % index)
        field = dict(raw)
        kind = field.get('kind', 'text')
        if kind not in FIELD_KINDS:
            raise ValueError('field %d: unknown kind %r' % (index, kind))
        field['kind'] = kind
        if kind not in VALUELESS:
            key = field.get('key')
            if not key:
                raise ValueError('field %d (%s) needs a key' % (index, kind))
            if key in keys:
                raise ValueError('field key %r is used twice' % key)
            keys.add(key)
        if kind in ('choice', 'radio', 'multi') and not options_of(field):
            raise ValueError('field %r needs options' % field.get('key'))
        if kind in ('choice', 'radio'):
            _check_default(field)
        field.setdefault('label', '')
        field.setdefault('hint', None)
        field.setdefault('required', False)
        if kind == 'textarea':
            field.setdefault('rows', 4)
        out.append(field)
    for field in out:
        condition = field.get('enabled_if')
        if condition is not None:
            if not isinstance(condition, (tuple, list)) or len(condition) != 2:
                raise ValueError('enabled_if must be (other_key, value)')
            if condition[0] not in keys:
                raise ValueError('enabled_if names an unknown field %r' % (condition[0],))
            _check_condition(field, condition, out)
    return out


def _among(wanted, values):
    """Whether wanted equals one of values by ==, the test the controls use."""
    for value in values:
        try:
            if value == wanted:
                return True
        except Exception:
            pass
    return False


def _check_default(field):
    """Settles a choice/radio default: kept when offered, else the 'fallback' when
    the field has one, else ValueError. Works on the copy normalize_fields made."""
    default = field.get('default')
    if default is None:
        return
    values = [value for _label, value in options_of(field)]
    if _among(default, values):
        return
    if 'fallback' in field:
        fallback = field['fallback']
        if fallback is not None and not _among(fallback, values):
            raise ValueError('field %r: fallback %r is not one of its option values %s'
                             % (field.get('key'), fallback, _values_text(values)))
        field['default'] = fallback
        return
    raise ValueError('field %r: default %r is not one of its option values %s. Options are '
                     '(label, value) pairs and the default is a value; give a fallback when '
                     'the default comes from saved settings.'
                     % (field.get('key'), default, _values_text(values)))


def _check_condition(field, condition, fields):
    """ValueError when an enabled_if could never be true: its value is not offered by
    the choice/radio field it watches, or is not a bool for a check field."""
    other_key, wanted = condition[0], condition[1]
    other = [f for f in fields if f.get('key') == other_key and f['kind'] not in VALUELESS][0]
    many = isinstance(wanted, (list, tuple, set))
    wanted_values = list(wanted) if many else [wanted]
    if other['kind'] in ('choice', 'radio'):
        values = [value for _label, value in options_of(other)]
        if not any(_among(w, values) for w in wanted_values):
            raise ValueError('field %r: enabled_if compares %r with %r, which is not one of '
                             'its option values %s' % (field.get('key'), other_key, wanted,
                                                       _values_text(values)))
    elif other['kind'] == 'check':
        if not wanted_values or not all(_among(w, (True, False)) for w in wanted_values):
            raise ValueError('field %r: enabled_if compares the check box %r with %r; use True '
                             'or False' % (field.get('key'), other_key, wanted))


def _values_text(values, limit=8):
    shown = ', '.join(repr(v) for v in values[:limit])
    return '[%s%s]' % (shown, ', ...' if len(values) > limit else '')


def _range_text(min_value, max_value):
    def fmt(v):
        return ('%.6f' % v).rstrip('0').rstrip('.') if isinstance(v, float) else str(v)
    if min_value is not None and max_value is not None:
        return ' between %s and %s' % (fmt(min_value), fmt(max_value))
    if min_value is not None:
        return ' of at least %s' % fmt(min_value)
    if max_value is not None:
        return ' of at most %s' % fmt(max_value)
    return ''


def _number_text(text):
    """A float from typed text, or None. Spaces are ignored; '1,234.5' and
    '1 234,5' both read; a lone comma is a decimal comma unless exactly three digits
    follow it ('1,234' is one thousand two hundred and thirty-four)."""
    if text is None:
        return None
    value = str(text).strip().replace(' ', '').replace(chr(0xa0), '')
    if not value:
        return None
    if ',' in value and '.' in value:
        value = value.replace(',', '')
    elif value.count(',') == 1:
        head, tail = value.split(',')
        if len(tail) == 3 and head.lstrip('+-').isdigit():
            value = head + tail
        else:
            value = head + '.' + tail
    elif value.count(',') > 1:
        value = value.replace(',', '')
    try:
        number = float(value)
    except ValueError:
        return None
    if number != number or number in (float('inf'), float('-inf')):
        return None
    return number


def parse_number(text, min_value=None, max_value=None):
    """(float, None) or (None, error sentence) for a typed number."""
    number = _number_text(text)
    if number is None:
        return None, 'Enter a number%s.' % _range_text(min_value, max_value)
    if (min_value is not None and number < min_value) or (max_value is not None and number > max_value):
        return None, 'Enter a number%s.' % _range_text(min_value, max_value)
    return number, None


def parse_int(text, min_value=None, max_value=None):
    """(int, None) or (None, error sentence) for a typed whole number."""
    number = _number_text(text)
    if number is None or number != int(number):
        return None, 'Enter a whole number%s.' % _range_text(min_value, max_value)
    value = int(number)
    if (min_value is not None and value < min_value) or (max_value is not None and value > max_value):
        return None, 'Enter a whole number%s.' % _range_text(min_value, max_value)
    return value, None


_DATE = re.compile(r'^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s*$')


def parse_date(text):
    """('YYYY-MM-DD', None) or (None, error) for a typed date. ISO order only
    (2026-10-05, 2026/10/5): day-month order is ambiguous, so it is refused."""
    import datetime
    match = _DATE.match(str(text or ''))
    if match:
        try:
            value = datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return value.strftime('%Y-%m-%d'), None
        except ValueError:
            pass
    return None, 'Enter a date as year-month-day, like 2026-10-05.'


def parse_color(text):
    """('RRGGBB', None) or (None, error) for a typed colour."""
    from namo import colors
    value = colors.parse_hex(text)
    if value is None:
        return None, 'Enter a color as six hex digits, like 4E79A7.'
    return value, None


def is_enabled(field, values):
    """Whether a field is live given the current values of the others:
    enabled_if (key, wanted) compares with ==, or membership when wanted is a
    list/tuple/set."""
    condition = field.get('enabled_if')
    if not condition:
        return True
    other, wanted = condition[0], condition[1]
    current = values.get(other)
    if isinstance(wanted, (list, tuple, set)):
        return current in wanted
    return current == wanted


def validate_value(field, raw, length_parser=None, units=None, path_exists=None, quick=False):
    """(value, error) for one field from its raw control state.

    quick=True is the per-keystroke check: a path field (file_open, file_save, folder)
    is only checked for being filled in, never for existing, and its own 'validate'
    is skipped, because both may probe a disk or a network share (typing a UNC path
    would otherwise probe it once per character). The full check runs on OK.

    raw is: text for text-like kinds (text, textarea, int, number, length, file_open,
    file_save, folder, color, date); a bool for check; the chosen VALUE (or None)
    for choice/radio; the list of ticked values for multi. length_parser(text,
    units) -> float or None (pynavis.lengths.parse in the window). path_exists(path,
    kind) -> bool checks file_open/folder (os.path by default). A field's own
    'validate' callable(value) -> error or None runs last.
    """
    kind = field['kind']
    required = bool(field.get('required'))
    value, error = None, None
    if kind == 'check':
        value = bool(raw)
    elif kind in ('choice', 'radio'):
        value = raw
        if value is None and required:
            error = 'Choose one.'
    elif kind == 'multi':
        value = list(raw or [])
        if required and not value:
            error = 'Tick at least one.'
    else:
        text = '' if raw is None else str(raw)
        blank = not text.strip()
        if blank:
            if required:
                error = 'Choose a file.' if kind in ('file_open', 'file_save') else \
                    'Choose a folder.' if kind == 'folder' else 'Enter a value.'
            value = None if kind in ('int', 'number', 'length') else ''
        elif kind == 'int':
            value, error = parse_int(text, field.get('min'), field.get('max'))
        elif kind == 'number':
            value, error = parse_number(text, field.get('min'), field.get('max'))
        elif kind == 'length':
            parsed = length_parser(text, units) if length_parser is not None else _number_text(text)
            if parsed is None:
                error = 'Enter a length%s.' % ((', ' + length_hint(units)) if units else '')
            else:
                value = float(parsed)
                low, high = field.get('min'), field.get('max')
                if (low is not None and value < low) or (high is not None and value > high):
                    value, error = None, 'Enter a length%s.' % _range_text(low, high)
        elif kind == 'date':
            value, error = parse_date(text)
        elif kind == 'color':
            value, error = parse_color(text)
        elif quick and kind in PATH_KINDS:
            value = text.strip()
        elif kind in ('file_open', 'folder'):
            value = text.strip()
            exists = path_exists or (lambda p, k: os.path.isdir(p) if k == 'folder' else os.path.isfile(p))
            if not exists(value, kind):
                error = 'That folder does not exist.' if kind == 'folder' else 'That file does not exist.'
        elif kind == 'file_save':
            value = text.strip()
            folder = os.path.dirname(value)
            if not folder or not (path_exists or (lambda p, k: os.path.isdir(p)))(folder, 'folder'):
                error = 'Choose a file in a folder that exists.'
        else:
            value = text
    custom = field.get('validate')
    if quick and kind in PATH_KINDS:
        custom = None
    if error is None and custom is not None:
        try:
            error = custom(value)
        except Exception as problem:
            error = str(problem)
    return value, error


def length_hint(units):
    """What may be typed into a length box, for document units."""
    imperial = str(units) in ('Feet', 'Inches', 'Yards', 'Miles', 'Mils', 'Microinches')
    if imperial:
        return 'like 3", 1\' 6 1/2" or 25mm'
    return 'in %s, or with a unit like 2" or 0.1m' % str(units or 'model units').lower()


def collect(fields, raws, length_parser=None, units=None, path_exists=None, form_validate=None,
            quick=False, form_keys=None):
    """(values, errors) for a whole form. raws: {key: raw}. Disabled fields
    (enabled_if false) skip validation and return their default. errors: {key:
    sentence}. form_validate(values) may add errors: it returns {key: sentence}, a
    sentence (shown under the first field), or None.

    quick=True is the per-keystroke pass: no path is probed and form_validate is not
    called (see validate_value); carry_errors() keeps what the last full pass found.
    form_keys: a dict that receives {key: True} for each error the form-level validate
    added (carry_errors treats those differently)."""
    values = {}
    errors = {}
    if quick:
        form_validate = None
    for field in fields:
        if field['kind'] in VALUELESS:
            continue
        key = field['key']
        value, error = validate_value(field, raws.get(key), length_parser, units, path_exists, quick)
        values[key] = value
        if error:
            errors[key] = error
    for field in fields:
        if field['kind'] in VALUELESS:
            continue
        if not is_enabled(field, values):
            key = field['key']
            if errors.pop(key, None) is not None:
                values[key] = field.get('default')
    if not errors and form_validate is not None:
        extra = form_validate(values)
        added = {}
        if isinstance(extra, dict):
            added = dict((k, v) for k, v in extra.items() if v)
        elif extra:
            first = [f['key'] for f in fields if f['kind'] not in VALUELESS]
            if first:
                added[first[0]] = str(extra)
        errors.update(added)
        if form_keys is not None:
            for key in added:
                form_keys[key] = True
    return values, errors


def carry_errors(fields, raws, quick_errors, checked_raws, checked_errors, values=None):
    """The inline errors to show between two full checks: what the quick pass found,
    plus the errors of the last full pass that the quick pass cannot re-test, for as
    long as they can still be true.

      * a path field's own error (the file is missing, its 'validate' refused it)
        stays until that field's text changes;
      * an error from the form-level validate looks at several fields at once: it
        stays until anything changes. checked_errors['__form__'] = {key: True} names
        those (FormState records it).

    Every other error is one the quick pass tests itself, so it is not carried. A
    field that is disabled now (values given) shows no error. Nothing here touches
    the disk: the next OK re-checks everything."""
    merged = dict(quick_errors or {})
    if not checked_errors or checked_raws is None:
        return merged
    by_key = dict((f['key'], f) for f in fields if f['kind'] not in VALUELESS)
    unchanged = dict((key, raws.get(key) == checked_raws.get(key)) for key in by_key)
    nothing_changed = all(unchanged.values())
    from_form = checked_errors.get('__form__') or {}
    for key in sorted(k for k in checked_errors if k in by_key):
        if key in merged:
            continue
        field = by_key[key]
        if values is not None and not is_enabled(field, values):
            continue
        if key in from_form:
            keep = nothing_changed
        else:
            keep = field['kind'] in PATH_KINDS and unchanged[key]
        if keep:
            merged[key] = checked_errors[key]
    return merged


def default_text(field, units=None, length_formatter=None, length_parser=None):
    """The text a text-like control opens with, from the field's default.

    A length goes through length_formatter (pynavis.lengths.format_input), which in a
    feet-and-inches document rounds to the nearest 1/16 in: half a millimetre would
    open as 0' 0" and read back as zero. With length_parser (pynavis.lengths.parse)
    given, a non-zero default whose text reads back as zero opens as decimal inches
    instead (0.0197"), which parses to the value it shows."""
    value = field.get('default')
    if value is None:
        return ''
    kind = field['kind']
    if kind == 'length' and length_formatter is not None:
        try:
            number = float(value)
            shown = length_formatter(number, units)
        except Exception:
            return str(value)
        if number != 0.0 and length_parser is not None:
            try:
                back = length_parser(shown, units)
            except Exception:
                back = None
            if back is not None and float(back) == 0.0:
                small = small_length_text(number, units)
                try:
                    if small and float(length_parser(small, units) or 0.0) != 0.0:
                        return small
                except Exception:
                    pass
        return shown
    if kind == 'number' and isinstance(value, float):
        return ('%.6f' % value).rstrip('0').rstrip('.')
    if kind == 'color':
        from namo import colors
        return colors.parse_hex(value) or str(value)
    return str(value)


def small_length_text(value, units):
    """A length too small for the 1/16 in grid, in document units, as decimal inches
    with three significant digits: '0.0197"' for half a millimetre in a feet
    document. None when units is not a name namo.units knows."""
    import math
    try:
        from namo import units as unit_table
        inches = unit_table.to_meters(abs(float(value)), units) / 0.0254
    except Exception:
        return None
    if not inches > 0.0:
        return None
    decimals = min(9, max(0, 2 - int(math.floor(math.log10(inches)))))
    digits = ('%.*f' % (decimals, inches))
    if '.' in digits:
        digits = digits.rstrip('0').rstrip('.')
    if not digits.strip('0.'):
        return None
    return '%s%s"' % ('-' if float(value) < 0 else '', digits)


# ---- tables, pure -------------------------------------------------------------------


def natural_key(text):
    """A sort key that orders 'Level 2' before 'Level 10': lower case, every digit
    run zero-padded to 12 places."""
    text = '' if text is None else str(text)
    return re.sub(r'\d+', lambda m: m.group(0).zfill(12), text.strip().lower())


def format_cell(value):
    """Display text for a cell: thousands separators for numbers, two decimals for
    floats (three significant figures below 1), Yes/No for booleans, '' for None."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, int):
        return '{:,}'.format(value)
    if isinstance(value, float):
        if value != value:
            return ''
        if value != 0 and abs(value) < 1:
            return '%.3g' % value
        return '{:,.2f}'.format(value)
    return str(value)


def cell_number(value):
    """The number behind a cell for numeric sorting, or None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return _number_text(value) if re.match(r'^\s*[-+]?[\d,.\s]+\s*$', str(value)) else None


def numeric_columns(rows, count):
    """[bool] per column: True when every non-empty cell is a number (or numeric
    text), and at least one is."""
    seen = [False] * count
    ok = [True] * count
    for cells in rows:
        for index in range(count):
            value = cells[index] if index < len(cells) else None
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            seen[index] = True
            if cell_number(value) is None:
                ok[index] = False
    return [seen[i] and ok[i] for i in range(count)]


def column_weights(rows, count, sample=200):
    """Star widths per column from the average text length of the first rows
    (clamped 4..40 characters), so a name column gets more room than a count."""
    totals = [0] * count
    seen = 0
    for cells in rows[:sample]:
        seen += 1
        for index in range(count):
            value = cells[index] if index < len(cells) else None
            totals[index] += len(format_cell(value))
    if not seen:
        return [1.0] * count
    return [float(max(4, min(40, totals[i] / float(seen)))) for i in range(count)]


def normalize_rows(rows):
    """[{'cells': [...], 'value': v, 'checked': bool}] from dict rows or plain
    sequences (a plain row's value is its index)."""
    out = []
    for index, row in enumerate(rows or []):
        if isinstance(row, dict):
            cells = list(row.get('cells') or [])
            value = row['value'] if 'value' in row else index
            checked = bool(row.get('checked', False))
        else:
            cells = list(row)
            value = index
            checked = False
        out.append({'cells': cells, 'value': value, 'checked': checked})
    return out


def search_text(cells):
    """The lower-case text a row is filtered on."""
    return ' '.join(format_cell(c) for c in cells).lower()


def filter_words(query):
    return [w for w in str(query or '').lower().split() if w]


def matches(query, text):
    """True when every word of query is in text (case-insensitive)."""
    lowered = (text or '').lower()
    return all(word in lowered for word in filter_words(query))


def like_escape(word):
    """A word made safe inside a DataView LIKE '%...%' pattern."""
    out = []
    for ch in word:
        if ch in '*%[]':
            out.append('[' + ch + ']')
        elif ch == "'":
            out.append("''")
        else:
            out.append(ch)
    return ''.join(out)


def row_filter(query, column='txt'):
    """A DataView.RowFilter expression for query (every word must appear), or ''.
    Wildcards may only sit at the ends of a LIKE pattern, so each word is its own
    clause."""
    words = filter_words(query)
    return ' AND '.join("%s LIKE '%%%s%%'" % (column, like_escape(w)) for w in words)


def count_text(checked, total, visible=None, noun='selected'):
    """'3 of 120 selected' (and ', 40 shown' while filtered)."""
    text = '%s of %s %s' % ('{:,}'.format(checked), '{:,}'.format(total), noun)
    if visible is not None and visible != total:
        text += ', %s shown' % '{:,}'.format(visible)
    return text


def place_rect(host, size, where='center', margin=24):
    """(left, top) for a window of size (w, h) inside host (l, t, r, b): 'center',
    'top-right', 'bottom-right', 'bottom-left', 'top-left'. Clamped inside host."""
    left, top, right, bottom = host
    width, height = size
    if where == 'top-right':
        x, y = right - width - margin, top + margin
    elif where == 'bottom-right':
        x, y = right - width - margin, bottom - height - margin
    elif where == 'bottom-left':
        x, y = left + margin, bottom - height - margin
    elif where == 'top-left':
        x, y = left + margin, top + margin
    else:
        x, y = left + (right - left - width) / 2.0, top + (bottom - top - height) / 2.0
    x = max(left, min(x, right - width))
    y = max(top, min(y, bottom - height))
    return (x, y)


# =============================================================================
# .NET half
# =============================================================================

_LOADED = []


def _wpf():
    """Loads the WPF and runtime assemblies once per engine."""
    if _LOADED:
        return
    import clr
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase', 'System.Xaml',
                 'System.Data', 'System.Drawing', 'System.Windows.Forms',
                 'WindowsFormsIntegration', 'PyNavis.Runtime'):
        try:
            clr.AddReference(name)
        except Exception:
            pass
    _LOADED.append(True)


def _holder(key):
    """namo.session.holder, with a same-keyed fallback while it is unavailable."""
    try:
        from namo import session
        return session.holder(key)
    except Exception:
        import types
        name = 'playground_' + key
        existing = sys.modules.get(name)
        if existing is None:
            existing = types.ModuleType(name)
            sys.modules[name] = existing
        return existing


# ---- logging and safety ------------------------------------------------------------


def pinned_logger():
    """The running command's logger, captured NOW for use in late callbacks
    (pynavis.script.get_logger()); None outside the runtime."""
    try:
        from pynavis import script
        return script.get_logger()
    except Exception:
        return None


def log_error(message, logger=None):
    """Writes an error line to the pinned logger (else namo.session.log). Never raises."""
    text = 'Playground: %s' % message
    if logger is not None:
        try:
            logger.error(text)
            return
        except Exception:
            pass
    try:
        from namo import session
        session.log('error', message)
    except Exception:
        try:
            sys.stderr.write(text + '\n')
        except Exception:
            pass


def safe(fn, label=None, logger=None):
    """fn wrapped for use as a late WPF/.NET callback: any exception is logged with
    its traceback (and label) and swallowed, because one escaping a UI-thread
    handler can take Navisworks down. Returns the wrapper."""
    if logger is None:
        logger = pinned_logger()
    name = label or getattr(fn, '__name__', 'callback')

    def wrapper(*args):
        try:
            return fn(*args)
        except Exception:
            log_error('%s failed:\n%s' % (name, traceback.format_exc()), logger)
            return None
    return wrapper


def _toast_error(message, detail=None):
    try:
        from pynavis import toast
        toast.error(message, detail)
    except Exception:
        pass


def is_runner():
    """True while a `pynavis run` script executes (no window may open)."""
    try:
        _wpf()
        from PyNavis.Runtime.Execution.Runner import RunnerContext
        return bool(RunnerContext.IsActive)
    except Exception:
        return False


def _refuse_under_runner():
    if is_runner():
        raise RuntimeError(RUNNER_MESSAGE)


# ---- theme --------------------------------------------------------------------------


def tokens(dark=None):
    """DesignSystem.Tokens: Current (following Navisworks) or For(dark)."""
    _wpf()
    from PyNavis.Runtime.Forms import DesignSystem
    if dark is None:
        return DesignSystem.Tokens.Current
    return DesignSystem.Tokens.For(bool(dark))


def hex_of(color):
    """'#RRGGBB' for a WPF Color."""
    return '#%02X%02X%02X' % (color.R, color.G, color.B)


def accent():
    _wpf()
    from PyNavis.Runtime.Forms import DesignSystem
    return DesignSystem.Accent


def palette(t=None):
    """{'paper', 'surface', 'line', 'line_strong', 'frame', 'ink', 'muted',
    'selection', 'error', 'error_bg', 'error_line', 'success', 'info', 'warning',
    'accent', 'on_accent'} as '#RRGGBB' for the current theme."""
    _wpf()
    from PyNavis.Runtime.Forms import DesignSystem
    t = t or tokens()
    a = DesignSystem.Accent
    return {
        'paper': hex_of(t.Paper), 'surface': hex_of(t.Surface), 'line': hex_of(t.Line),
        'line_strong': hex_of(t.LineStrong), 'frame': hex_of(t.FrameLine),
        'ink': hex_of(t.Ink), 'muted': hex_of(t.Muted), 'selection': hex_of(t.Selection),
        'error': hex_of(t.Error), 'error_bg': hex_of(t.ErrorWashBg),
        'error_line': hex_of(t.ErrorWashLine), 'success': hex_of(t.Success),
        'info': hex_of(t.Info), 'warning': hex_of(t.Warning),
        'accent': hex_of(a), 'on_accent': hex_of(DesignSystem.OnAccent(a)),
    }


def brush(hex_value):
    """A frozen SolidColorBrush from '#RRGGBB' / 'RRGGBB'."""
    _wpf()
    from System.Windows.Media import Color, SolidColorBrush
    from namo import colors
    r, g, b = colors.hex_to_rgb(hex_value)
    value = SolidColorBrush(Color.FromRgb(r, g, b))
    value.Freeze()
    return value


_THEME_XAML = r'''
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Style x:Key="namo.focus">
    <Setter Property="Control.Template">
      <Setter.Value>
        <ControlTemplate>
          <Rectangle Margin="-3" RadiusX="4" RadiusY="4" Stroke="%(accent)s" StrokeThickness="2"/>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <ControlTemplate x:Key="namo.vscroll" TargetType="ScrollBar">
    <Grid Background="Transparent">
      <Track x:Name="PART_Track" IsDirectionReversed="True">
        <Track.DecreaseRepeatButton><RepeatButton Command="ScrollBar.PageUpCommand" Opacity="0" Focusable="False"/></Track.DecreaseRepeatButton>
        <Track.IncreaseRepeatButton><RepeatButton Command="ScrollBar.PageDownCommand" Opacity="0" Focusable="False"/></Track.IncreaseRepeatButton>
        <Track.Thumb><Thumb Focusable="False"><Thumb.Template><ControlTemplate TargetType="Thumb">
          <Border Background="#59808080" CornerRadius="3" Margin="3,1"/>
        </ControlTemplate></Thumb.Template></Thumb></Track.Thumb>
      </Track>
    </Grid>
  </ControlTemplate>
  <ControlTemplate x:Key="namo.hscroll" TargetType="ScrollBar">
    <Grid Background="Transparent">
      <Track x:Name="PART_Track" IsDirectionReversed="False">
        <Track.DecreaseRepeatButton><RepeatButton Command="ScrollBar.PageLeftCommand" Opacity="0" Focusable="False"/></Track.DecreaseRepeatButton>
        <Track.IncreaseRepeatButton><RepeatButton Command="ScrollBar.PageRightCommand" Opacity="0" Focusable="False"/></Track.IncreaseRepeatButton>
        <Track.Thumb><Thumb Focusable="False"><Thumb.Template><ControlTemplate TargetType="Thumb">
          <Border Background="#59808080" CornerRadius="3" Margin="1,3"/>
        </ControlTemplate></Thumb.Template></Thumb></Track.Thumb>
      </Track>
    </Grid>
  </ControlTemplate>
  <Style TargetType="ScrollBar">
    <Setter Property="Width" Value="10"/>
    <Setter Property="MinWidth" Value="10"/>
    <Setter Property="Template" Value="{StaticResource namo.vscroll}"/>
    <Style.Triggers>
      <Trigger Property="Orientation" Value="Horizontal">
        <Setter Property="Width" Value="Auto"/>
        <Setter Property="MinWidth" Value="0"/>
        <Setter Property="Height" Value="10"/>
        <Setter Property="MinHeight" Value="10"/>
        <Setter Property="Template" Value="{StaticResource namo.hscroll}"/>
      </Trigger>
    </Style.Triggers>
  </Style>

  <Style TargetType="TextBox">
    <Setter Property="CaretBrush" Value="%(ink)s"/>
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="FontSize" Value="13"/>
  </Style>

  <Style TargetType="ToolTip">
    <Setter Property="Background" Value="%(paper)s"/>
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="BorderBrush" Value="%(line_strong)s"/>
    <Setter Property="FontSize" Value="12"/>
    <Setter Property="Padding" Value="8,4"/>
  </Style>

  <Style TargetType="CheckBox">
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="FontSize" Value="13"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="FocusVisualStyle" Value="{StaticResource namo.focus}"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="CheckBox">
          <Grid Background="Transparent" MinHeight="24">
            <Grid.ColumnDefinitions>
              <ColumnDefinition Width="Auto"/>
              <ColumnDefinition Width="*"/>
            </Grid.ColumnDefinitions>
            <Border x:Name="box" Width="16" Height="16" CornerRadius="3" BorderThickness="1"
                    BorderBrush="%(line_strong)s" Background="%(paper)s" VerticalAlignment="Center"/>
            <Path x:Name="tick" Data="M 0,3.6 L 3.3,6.8 L 9,0.6" Stroke="%(on_accent)s" StrokeThickness="1.6"
                  StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round"
                  Width="9" Height="7" HorizontalAlignment="Center" VerticalAlignment="Center" Visibility="Collapsed"/>
            <ContentPresenter Grid.Column="1" Margin="8,0,0,0" VerticalAlignment="Center" RecognizesAccessKey="True"/>
          </Grid>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="box" Property="BorderBrush" Value="%(frame)s"/>
            </Trigger>
            <Trigger Property="IsChecked" Value="True">
              <Setter TargetName="box" Property="Background" Value="%(accent)s"/>
              <Setter TargetName="box" Property="BorderBrush" Value="%(accent)s"/>
              <Setter TargetName="tick" Property="Visibility" Value="Visible"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter Property="Foreground" Value="%(muted)s"/>
              <Setter TargetName="box" Property="Background" Value="%(surface)s"/>
              <Setter TargetName="box" Property="BorderBrush" Value="%(line)s"/>
              <Setter Property="Cursor" Value="Arrow"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="RadioButton">
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="FontSize" Value="13"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="FocusVisualStyle" Value="{StaticResource namo.focus}"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="RadioButton">
          <Grid Background="Transparent" MinHeight="24">
            <Grid.ColumnDefinitions>
              <ColumnDefinition Width="Auto"/>
              <ColumnDefinition Width="*"/>
            </Grid.ColumnDefinitions>
            <Ellipse x:Name="ring" Width="16" Height="16" StrokeThickness="1" Stroke="%(line_strong)s"
                     Fill="%(paper)s" VerticalAlignment="Center"/>
            <Ellipse x:Name="dot" Width="6" Height="6" Fill="%(on_accent)s" Visibility="Collapsed"
                     HorizontalAlignment="Center" VerticalAlignment="Center"/>
            <ContentPresenter Grid.Column="1" Margin="8,0,0,0" VerticalAlignment="Center" RecognizesAccessKey="True"/>
          </Grid>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="ring" Property="Stroke" Value="%(frame)s"/>
            </Trigger>
            <Trigger Property="IsChecked" Value="True">
              <Setter TargetName="ring" Property="Fill" Value="%(accent)s"/>
              <Setter TargetName="ring" Property="Stroke" Value="%(accent)s"/>
              <Setter TargetName="dot" Property="Visibility" Value="Visible"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter Property="Foreground" Value="%(muted)s"/>
              <Setter TargetName="ring" Property="Fill" Value="%(surface)s"/>
              <Setter TargetName="ring" Property="Stroke" Value="%(line)s"/>
              <Setter Property="Cursor" Value="Arrow"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="ComboBoxItem">
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="FontSize" Value="13"/>
    <Setter Property="Height" Value="32"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="ComboBoxItem">
          <Border x:Name="shell" Background="Transparent">
            <DockPanel>
              <Border x:Name="rail" Width="3" DockPanel.Dock="Left" Background="Transparent"/>
              <ContentPresenter Margin="9,0,12,0" VerticalAlignment="Center"/>
            </DockPanel>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsHighlighted" Value="True">
              <Setter TargetName="shell" Property="Background" Value="%(surface)s"/>
            </Trigger>
            <Trigger Property="IsSelected" Value="True">
              <Setter TargetName="shell" Property="Background" Value="%(selection)s"/>
              <Setter TargetName="rail" Property="Background" Value="%(accent)s"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="ComboBox">
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="FontSize" Value="13"/>
    <Setter Property="Height" Value="32"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="MaxDropDownHeight" Value="320"/>
    <Setter Property="FocusVisualStyle" Value="{StaticResource namo.focus}"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="ComboBox">
          <Grid>
            <ToggleButton x:Name="face" Focusable="False" ClickMode="Press"
                          IsChecked="{Binding IsDropDownOpen, Mode=TwoWay, RelativeSource={RelativeSource TemplatedParent}}">
              <ToggleButton.Template>
                <ControlTemplate TargetType="ToggleButton">
                  <Border x:Name="shell" CornerRadius="4" BorderThickness="1" BorderBrush="%(line_strong)s"
                          Background="%(paper)s">
                    <TextBlock Text="&#xE70D;" FontFamily="Segoe MDL2 Assets" FontSize="9" Foreground="%(muted)s"
                               HorizontalAlignment="Right" VerticalAlignment="Center" Margin="0,0,10,0"/>
                  </Border>
                  <ControlTemplate.Triggers>
                    <Trigger Property="IsMouseOver" Value="True">
                      <Setter TargetName="shell" Property="Background" Value="%(surface)s"/>
                    </Trigger>
                    <Trigger Property="IsEnabled" Value="False">
                      <Setter TargetName="shell" Property="Background" Value="%(surface)s"/>
                      <Setter TargetName="shell" Property="BorderBrush" Value="%(line)s"/>
                    </Trigger>
                  </ControlTemplate.Triggers>
                </ControlTemplate>
              </ToggleButton.Template>
            </ToggleButton>
            <ContentPresenter x:Name="content" IsHitTestVisible="False" Margin="10,0,28,0"
                              VerticalAlignment="Center" HorizontalAlignment="Left"
                              Content="{TemplateBinding SelectionBoxItem}"
                              ContentTemplate="{TemplateBinding SelectionBoxItemTemplate}"
                              ContentTemplateSelector="{TemplateBinding ItemTemplateSelector}"/>
            <Popup x:Name="PART_Popup" Placement="Bottom" VerticalOffset="4" AllowsTransparency="True"
                   Focusable="False" PopupAnimation="None"
                   IsOpen="{Binding IsDropDownOpen, RelativeSource={RelativeSource TemplatedParent}}">
              <Border Background="%(paper)s" BorderBrush="%(line)s" BorderThickness="1" CornerRadius="4"
                      Margin="0,0,12,12"
                      MinWidth="{Binding ActualWidth, RelativeSource={RelativeSource TemplatedParent}}"
                      MaxHeight="{Binding MaxDropDownHeight, RelativeSource={RelativeSource TemplatedParent}}">
                <Border.Effect>
                  <DropShadowEffect BlurRadius="12" ShadowDepth="2" Opacity="0.14" Direction="270"/>
                </Border.Effect>
                <ScrollViewer Margin="0,4" VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled">
                  <ItemsPresenter KeyboardNavigation.DirectionalNavigation="Contained"/>
                </ScrollViewer>
              </Border>
            </Popup>
          </Grid>
          <ControlTemplate.Triggers>
            <Trigger Property="IsEnabled" Value="False">
              <Setter TargetName="content" Property="TextElement.Foreground" Value="%(muted)s"/>
              <Setter Property="Cursor" Value="Arrow"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style x:Key="namo.gripper" TargetType="Thumb">
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="Thumb"><Border Background="Transparent"/></ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style x:Key="namo.header" TargetType="DataGridColumnHeader">
    <Setter Property="Foreground" Value="%(muted)s"/>
    <Setter Property="FontSize" Value="12"/>
    <Setter Property="Height" Value="32"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="HorizontalContentAlignment" Value="Left"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="DataGridColumnHeader">
          <Grid>
            <Border x:Name="shell" Background="%(surface)s" BorderBrush="%(line_strong)s" BorderThickness="0,0,0,1"
                    Padding="12,0,12,0">
              <DockPanel>
                <Path x:Name="arrow" DockPanel.Dock="Right" Width="8" Height="5" Margin="6,0,0,0" Stretch="Fill"
                      Fill="%(muted)s" Visibility="Collapsed" VerticalAlignment="Center" Data="M 0,0 L 4,5 L 8,0 Z"/>
                <ContentPresenter VerticalAlignment="Center" RecognizesAccessKey="True"
                                  HorizontalAlignment="{TemplateBinding HorizontalContentAlignment}"/>
              </DockPanel>
            </Border>
            <Thumb x:Name="PART_LeftHeaderGripper" HorizontalAlignment="Left" Width="6" Cursor="SizeWE"
                   Style="{StaticResource namo.gripper}"/>
            <Thumb x:Name="PART_RightHeaderGripper" HorizontalAlignment="Right" Width="6" Cursor="SizeWE"
                   Style="{StaticResource namo.gripper}"/>
          </Grid>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="shell" Property="Background" Value="%(selection)s"/>
            </Trigger>
            <Trigger Property="SortDirection" Value="Ascending">
              <Setter TargetName="arrow" Property="Visibility" Value="Visible"/>
              <Setter TargetName="arrow" Property="Data" Value="M 0,5 L 4,0 L 8,5 Z"/>
            </Trigger>
            <Trigger Property="SortDirection" Value="Descending">
              <Setter TargetName="arrow" Property="Visibility" Value="Visible"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style x:Key="namo.row" TargetType="DataGridRow">
    <Setter Property="Background" Value="Transparent"/>
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="DataGridRow">
          <Border x:Name="shell" Background="{TemplateBinding Background}" BorderBrush="%(line)s"
                  BorderThickness="0,0,0,1" SnapsToDevicePixels="True">
            <Grid>
              <DataGridCellsPresenter ItemsPanel="{TemplateBinding ItemsPanel}"
                                      SnapsToDevicePixels="{TemplateBinding SnapsToDevicePixels}"/>
              <Border x:Name="rail" Width="3" HorizontalAlignment="Left" Background="Transparent"/>
            </Grid>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="shell" Property="Background" Value="%(surface)s"/>
            </Trigger>
            <Trigger Property="IsSelected" Value="True">
              <Setter TargetName="shell" Property="Background" Value="%(selection)s"/>
              <Setter TargetName="rail" Property="Background" Value="%(accent)s"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style x:Key="namo.cell" TargetType="DataGridCell">
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="DataGridCell">
          <Border Background="Transparent" Padding="12,0" SnapsToDevicePixels="True">
            <ContentPresenter VerticalAlignment="Center"/>
          </Border>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style x:Key="namo.celltext" TargetType="TextBlock">
    <Setter Property="TextTrimming" Value="CharacterEllipsis"/>
    <Setter Property="VerticalAlignment" Value="Center"/>
  </Style>
  <Style x:Key="namo.cellnum" TargetType="TextBlock">
    <Setter Property="TextAlignment" Value="Right"/>
    <Setter Property="Typography.NumeralAlignment" Value="Tabular"/>
    <Setter Property="VerticalAlignment" Value="Center"/>
  </Style>

  <DataTemplate x:Key="namo.checkcell">
    <Grid Width="16" Height="16" HorizontalAlignment="Center" VerticalAlignment="Center">
      <Border x:Name="box" CornerRadius="3" BorderThickness="1" BorderBrush="%(line_strong)s" Background="Transparent"/>
      <Path x:Name="tick" Data="M 0,3.6 L 3.3,6.8 L 9,0.6" Stroke="%(on_accent)s" StrokeThickness="1.6"
            StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round"
            Width="9" Height="7" HorizontalAlignment="Center" VerticalAlignment="Center" Visibility="Collapsed"/>
    </Grid>
    <DataTemplate.Triggers>
      <DataTrigger Binding="{Binding chk}" Value="True">
        <Setter TargetName="box" Property="Background" Value="%(accent)s"/>
        <Setter TargetName="box" Property="BorderBrush" Value="%(accent)s"/>
        <Setter TargetName="tick" Property="Visibility" Value="Visible"/>
      </DataTrigger>
    </DataTemplate.Triggers>
  </DataTemplate>

  <Style x:Key="namo.grid" TargetType="DataGrid">
    <Setter Property="Background" Value="%(paper)s"/>
    <Setter Property="RowBackground" Value="Transparent"/>
    <Setter Property="AlternatingRowBackground" Value="Transparent"/>
    <Setter Property="Foreground" Value="%(ink)s"/>
    <Setter Property="BorderBrush" Value="%(line_strong)s"/>
    <Setter Property="BorderThickness" Value="1"/>
    <Setter Property="RowHeight" Value="32"/>
    <Setter Property="ColumnHeaderHeight" Value="32"/>
    <Setter Property="FontSize" Value="13"/>
    <Setter Property="GridLinesVisibility" Value="None"/>
    <Setter Property="HeadersVisibility" Value="Column"/>
    <Setter Property="AutoGenerateColumns" Value="False"/>
    <Setter Property="CanUserAddRows" Value="False"/>
    <Setter Property="CanUserDeleteRows" Value="False"/>
    <Setter Property="CanUserReorderColumns" Value="False"/>
    <Setter Property="CanUserResizeRows" Value="False"/>
    <Setter Property="CanUserResizeColumns" Value="True"/>
    <Setter Property="CanUserSortColumns" Value="True"/>
    <Setter Property="IsReadOnly" Value="True"/>
    <Setter Property="SelectionUnit" Value="FullRow"/>
    <Setter Property="EnableRowVirtualization" Value="True"/>
    <Setter Property="EnableColumnVirtualization" Value="True"/>
    <Setter Property="VirtualizingPanel.IsVirtualizing" Value="True"/>
    <Setter Property="VirtualizingPanel.VirtualizationMode" Value="Recycling"/>
    <Setter Property="VirtualizingPanel.ScrollUnit" Value="Item"/>
    <Setter Property="ScrollViewer.CanContentScroll" Value="True"/>
    <Setter Property="ColumnHeaderStyle" Value="{StaticResource namo.header}"/>
    <Setter Property="RowStyle" Value="{StaticResource namo.row}"/>
    <Setter Property="CellStyle" Value="{StaticResource namo.cell}"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  </Style>
</ResourceDictionary>
'''


def theme_xaml(colors_by_name):
    """The theme ResourceDictionary XAML with '#RRGGBB' tokens filled in (pure, so
    tests can check it is complete)."""
    return _THEME_XAML % colors_by_name


def theme_resources():
    """A ResourceDictionary of implicit styles (CheckBox, RadioButton, ComboBox,
    ComboBoxItem, ScrollBar, TextBox, ToolTip) and keyed ones ('namo.focus',
    'namo.grid', 'namo.header', 'namo.row', 'namo.cell', 'namo.celltext',
    'namo.cellnum', 'namo.checkcell') for the current theme."""
    _wpf()
    from System.Windows.Markup import XamlReader
    return XamlReader.Parse(theme_xaml(palette()))


def apply_theme(element):
    """Merges theme_resources() into element.Resources (once) and returns them."""
    resources = theme_resources()
    element.Resources.MergedDictionaries.Add(resources)
    return resources


def _resource(element, key):
    return element.FindResource(key)


# ---- parts -------------------------------------------------------------------------


def _thickness(*values):
    from System.Windows import Thickness
    if len(values) == 1:
        return Thickness(values[0])
    if len(values) == 2:
        return Thickness(values[0], values[1], values[0], values[1])
    return Thickness(*values)


def window(title, width=560, height=None, resizable=True, min_width=None, min_height=None):
    """A themed, unshown Window: paper background, Segoe UI Variable 13 px, ink
    text, theme resources merged, centred on its owner. height None sizes to
    content (no resize grip)."""
    _wpf()
    from System.Windows import ResizeMode, SizeToContent, Window, WindowStartupLocation
    from System.Windows.Documents import TextElement
    from System.Windows.Media import FontFamily
    t = tokens()
    win = Window()
    win.Title = str(title)
    win.Width = float(width)
    if height is None:
        win.SizeToContent = SizeToContent.Height
    else:
        win.Height = float(height)
    win.ResizeMode = ResizeMode.CanResize if resizable else ResizeMode.NoResize
    if min_width:
        win.MinWidth = float(min_width)
    if min_height:
        win.MinHeight = float(min_height)
    win.WindowStartupLocation = WindowStartupLocation.CenterOwner
    win.ShowInTaskbar = False
    win.Background = brush(hex_of(t.Paper))
    win.FontFamily = FontFamily(FONT)
    win.FontSize = 13.0
    TextElement.SetForeground(win, brush(hex_of(t.Ink)))
    win.UseLayoutRounding = True
    win.SnapsToDevicePixels = True
    apply_theme(win)
    return win


def text(value, size=13, muted=False, bold=False, color=None, wrap=True):
    """A TextBlock in ink (or muted, or a '#RRGGBB' color), Medium weight when bold."""
    _wpf()
    from System.Windows import FontWeights, TextWrapping
    from System.Windows.Controls import TextBlock
    t = tokens()
    block = TextBlock()
    block.Text = '' if value is None else str(value)
    block.FontSize = float(size)
    block.Foreground = brush(color or hex_of(t.Muted if muted else t.Ink))
    if bold:
        block.FontWeight = FontWeights.Medium
    block.TextWrapping = TextWrapping.Wrap if wrap else TextWrapping.NoWrap
    return block


def heading(value):
    """A 15 px Medium section heading."""
    return text(value, 15, bold=True)


def hint(value):
    """A 12 px muted line, for help under a control."""
    return text(value, 12, muted=True)


def button(label, on_click=None, kind='secondary', logger=None):
    """A DesignSystem button: kind 'primary' (accent, one per window), 'secondary',
    'quiet' (toolbar) or 'danger'. on_click() is wrapped with safe()."""
    _wpf()
    from PyNavis.Runtime.Forms import DesignSystem
    t = tokens()
    factory = {'primary': DesignSystem.Primary, 'secondary': DesignSystem.Secondary,
               'quiet': DesignSystem.Quiet, 'danger': DesignSystem.Danger}.get(kind)
    if factory is None:
        raise ValueError('unknown button kind %r' % kind)
    control = factory(t, str(label), None)
    if on_click is not None:
        handler = safe(lambda *args: on_click(), label, logger)
        control.Click += lambda sender, args: handler()
    return control


def text_box(value='', placeholder=None, suffix=None, multiline=False, rows=4):
    """(shell, box): a DesignSystem.InputField around a TextBox (32 px high, or
    `rows` lines when multiline), with an optional muted placeholder and unit
    suffix. Put `shell` in the layout; read and write `box.Text`."""
    _wpf()
    from System.Windows import HorizontalAlignment, TextWrapping, VerticalAlignment, Visibility
    from System.Windows.Controls import Grid, ScrollBarVisibility, TextBox
    from PyNavis.Runtime.Forms import DesignSystem
    t = tokens()
    box = TextBox()
    box.Text = '' if value is None else str(value)
    if multiline:
        box.AcceptsReturn = True
        box.TextWrapping = TextWrapping.Wrap
        box.Height = 20.0 * max(1, int(rows)) + 12.0
        box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    else:
        box.Height = 30.0
    shell = DesignSystem.InputField(t, box, suffix)
    box.CaretBrush = brush(hex_of(t.Ink))
    if multiline:
        box.VerticalContentAlignment = VerticalAlignment.Top
        box.Padding = _thickness(8, 6, 8, 6)
    if not placeholder:
        return shell, box
    overlay = text(placeholder, 13, muted=True, wrap=False)
    overlay.IsHitTestVisible = False
    overlay.VerticalAlignment = VerticalAlignment.Top if multiline else VerticalAlignment.Center
    overlay.HorizontalAlignment = HorizontalAlignment.Left
    overlay.Margin = _thickness(11, 7 if multiline else 0, 0, 0)
    grid = Grid()
    grid.Children.Add(shell)
    grid.Children.Add(overlay)

    def refresh(*args):
        overlay.Visibility = Visibility.Collapsed if box.Text else Visibility.Visible
    box.TextChanged += safe(lambda s, e: refresh())
    refresh()
    return grid, box


def search_box(placeholder='Filter', on_change=None, delay_ms=150):
    """(element, box): a filter field; on_change(text) runs delay_ms after typing
    stops (Debouncer), so big tables stay responsive."""
    element, box = text_box('', placeholder=placeholder)
    if on_change is not None:
        debounce = Debouncer(delay_ms, lambda: on_change(box.Text))
        box.TextChanged += safe(lambda s, e: debounce.trigger())
    return element, box


def combo(options, selected=None, width=None):
    """A themed ComboBox of option labels; options are strings or (label, value)
    pairs; selected is a value. combo_value(control) reads the chosen value."""
    _wpf()
    from System.Windows.Controls import ComboBox
    pairs = options_of({'options': options})
    control = ComboBox()
    for label, _value in pairs:
        control.Items.Add(label)
    control.Tag = _Bag(pairs=pairs)
    index = _index_of([v for _l, v in pairs], selected)
    control.SelectedIndex = index if index is not None else (0 if pairs and selected is None else -1)
    if width:
        control.Width = float(width)
    return control


def combo_value(control):
    """The value behind a combo()'s current choice, or None."""
    index = control.SelectedIndex
    pairs = control.Tag.pairs
    return pairs[index][1] if 0 <= index < len(pairs) else None


def _index_of(values, wanted):
    if wanted is None:
        return None
    for index, value in enumerate(values):
        if value == wanted:
            return index
    return None


def check(label, checked=False):
    """A themed CheckBox."""
    _wpf()
    from System.Windows.Controls import CheckBox
    control = CheckBox()
    control.Content = str(label)
    control.IsChecked = bool(checked)
    return control


def radio_group(options, selected=None, inline=False, group=None):
    """(panel, buttons): themed RadioButtons for options (strings or (label,
    value)); radio_value(buttons, pairs) reads the choice."""
    _wpf()
    from System.Windows.Controls import Orientation, RadioButton, StackPanel, WrapPanel
    pairs = options_of({'options': options})
    panel = WrapPanel() if inline else StackPanel()
    if not inline:
        panel.Orientation = Orientation.Vertical
    buttons = []
    name = group or 'namo_%d' % id(panel)
    for index, (label, value) in enumerate(pairs):
        control = RadioButton()
        control.Content = label
        control.GroupName = name
        control.IsChecked = (value == selected) if selected is not None else index == 0
        control.Margin = _thickness(0, 0, 16 if inline else 0, 6)
        panel.Children.Add(control)
        buttons.append(control)
    return panel, buttons


def radio_value(buttons, pairs):
    for control, (_label, value) in zip(buttons, pairs):
        if control.IsChecked:
            return value
    return None


def separator(margin=(0, 4, 0, 20)):
    """A 1 px hairline."""
    _wpf()
    from System.Windows.Controls import Border
    rule = Border()
    rule.Height = 1.0
    rule.Background = brush(hex_of(tokens().Line))
    rule.Margin = _thickness(*margin)
    return rule


def group(title, content):
    """DesignSystem.GroupFrame: a bold frame with its title on the border."""
    _wpf()
    from PyNavis.Runtime.Forms import DesignSystem
    return DesignSystem.GroupFrame(tokens(), title, content)


def footer(buttons, left=None, padding=24):
    """The footer bar: surface fill, hairline on top, buttons on the right (8 px
    apart, in the order given) and an optional element on the left."""
    _wpf()
    from System.Windows import HorizontalAlignment, VerticalAlignment
    from System.Windows.Controls import Border, Dock, DockPanel, Orientation, StackPanel
    t = tokens()
    row = StackPanel()
    row.Orientation = Orientation.Horizontal
    row.HorizontalAlignment = HorizontalAlignment.Right
    for index, control in enumerate(buttons):
        control.Margin = _thickness(0 if index == 0 else 8, 0, 0, 0)
        row.Children.Add(control)
    dock = DockPanel()
    dock.LastChildFill = False
    if left is not None:
        left.VerticalAlignment = VerticalAlignment.Center
        DockPanel.SetDock(left, Dock.Left)
        dock.Children.Add(left)
    DockPanel.SetDock(row, Dock.Right)
    dock.Children.Add(row)
    bar = Border()
    bar.Background = brush(hex_of(t.Surface))
    bar.BorderBrush = brush(hex_of(t.LineStrong))
    bar.BorderThickness = _thickness(0, 1, 0, 0)
    bar.Padding = _thickness(padding, 12, padding, 12)
    bar.Child = dock
    return bar


def scroll(content, max_height=None):
    """A vertical ScrollViewer (slim bars from the theme) around content."""
    _wpf()
    from System.Windows.Controls import ScrollBarVisibility, ScrollViewer
    viewer = ScrollViewer()
    viewer.Content = content
    viewer.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    viewer.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
    viewer.Focusable = False
    if max_height:
        viewer.MaxHeight = float(max_height)
    return viewer


def work_area():
    """(left, top, right, bottom) of the primary screen's work area in WPF units."""
    _wpf()
    from System.Windows import SystemParameters
    area = SystemParameters.WorkArea
    return (area.Left, area.Top, area.Right, area.Bottom)


class _Bag(object):
    """Attribute bag stored in a control's Tag."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# ---- Table -----------------------------------------------------------------------


class Table(object):
    """A themed, virtualised, sortable, filterable table (WPF DataGrid over a
    DataTable view), usable on its own inside any window.

    rows: [{'cells': [...], 'value': v, 'checked': bool}] or plain cell lists (the
    value is then the row index). Cells may be text or numbers: a column whose
    cells are all numbers sorts numerically, right-aligned with tabular figures,
    shown with thousands separators (format_cell); text columns sort naturally
    ('Level 2' before 'Level 10'). Header clicks sort.

    checkboxes=True adds a tick column: a click on a row ticks it, Space ticks the
    selected rows. on_open(value) fires on double-click or Enter. on_change() fires
    when the selection or the ticks change.
    """

    def __init__(self, columns, rows, checkboxes=False, multiselect=True, show_headers=True,
                 on_open=None, on_change=None, logger=None):
        _wpf()
        from System.Windows.Controls import DataGrid, DataGridSelectionMode
        self.logger = logger or pinned_logger()
        self.columns = [str(c) for c in columns]
        self.checkboxes = bool(checkboxes)
        self.on_open = on_open
        self.on_change = on_change
        self.rows = []
        self.query = ''
        normalized = normalize_rows(rows)
        cells = [r['cells'] for r in normalized]
        self.numeric = numeric_columns(cells, len(self.columns))
        self._new_table()
        self.grid = DataGrid()
        resources = theme_resources()
        self.resources = resources
        self.grid.Resources.MergedDictionaries.Add(resources)
        self.grid.Style = resources['namo.grid']
        self.grid.SelectionMode = (DataGridSelectionMode.Extended if multiselect
                                   else DataGridSelectionMode.Single)
        if not show_headers:
            from System.Windows.Controls import DataGridHeadersVisibility
            self.grid.HeadersVisibility = getattr(DataGridHeadersVisibility, 'None')
        self._build_columns(resources, cells)
        self.grid.ItemsSource = self.view
        self._load(normalized)
        self._wire()

    # -- construction --

    def _build_columns(self, resources, cells):
        from System.Windows.Controls import DataGridLength, DataGridTemplateColumn, DataGridTextColumn
        from System.Windows.Data import Binding
        if self.checkboxes:
            column = DataGridTemplateColumn()
            column.CellTemplate = resources['namo.checkcell']
            column.Header = ''
            column.Width = DataGridLength(44.0)
            column.SortMemberPath = 'chk'
            column.CanUserResize = False
            self.grid.Columns.Add(column)
        weights = column_weights(cells, len(self.columns))
        for index, header in enumerate(self.columns):
            column = DataGridTextColumn()
            column.Header = header
            column.Binding = Binding('c%d' % index)
            column.SortMemberPath = 'k%d' % index
            self._style_column(column, index, self.numeric[index], resources, weights[index])
            self.grid.Columns.Add(column)

    def _style_column(self, column, index, is_number, resources, weight):
        import clr
        from System.Windows import HorizontalAlignment, Setter, Style
        from System.Windows.Controls import Control, DataGridLength, DataGridLengthUnitType
        from System.Windows.Controls.Primitives import DataGridColumnHeader
        if is_number:
            right_header = Style(clr.GetClrType(DataGridColumnHeader), resources['namo.header'])
            right_header.Setters.Add(Setter(Control.HorizontalContentAlignmentProperty,
                                            HorizontalAlignment.Right))
            column.ElementStyle = resources['namo.cellnum']
            column.HeaderStyle = right_header
            column.Width = DataGridLength(1.0, DataGridLengthUnitType.Auto)
            column.MinWidth = 72.0
        else:
            column.ElementStyle = resources['namo.celltext']
            column.HeaderStyle = resources['namo.header']
            column.Width = DataGridLength(weight or 8.0, DataGridLengthUnitType.Star)
            column.MinWidth = 80.0

    def _load(self, normalized):
        from System import Array, DBNull, Object
        self.rows = normalized
        count = len(self.columns)
        numeric = self.numeric
        self.data.BeginLoadData()
        try:
            self.data.Rows.Clear()
            for index, row in enumerate(normalized):
                cells = row['cells']
                size = len(cells)
                texts = [format_cell(cells[c]) if c < size else '' for c in range(count)]
                values = [index, bool(row['checked']), ' '.join(texts).lower()]
                for col in range(count):
                    values.append(texts[col])
                    if numeric[col]:
                        number = cell_number(cells[col]) if col < size else None
                        values.append(DBNull.Value if number is None else number)
                    else:
                        values.append(natural_key(texts[col]))
                self.data.Rows.Add(Array[Object](values))
        finally:
            self.data.EndLoadData()

    def _new_table(self):
        """A fresh DataTable (and view) typed for self.numeric: 'idx', 'chk', 'txt'
        (filter text), then per column 'c<i>' (display text) and 'k<i>' (sort key:
        Double for numeric columns, natural-order text otherwise)."""
        import clr
        from System import Boolean, Double, Int32, String
        from System.Data import DataTable
        data = DataTable()
        data.CaseSensitive = False
        data.Columns.Add('idx', clr.GetClrType(Int32))
        data.Columns.Add('chk', clr.GetClrType(Boolean))
        data.Columns.Add('txt', clr.GetClrType(String))
        for index in range(len(self.columns)):
            data.Columns.Add('c%d' % index, clr.GetClrType(String))
            data.Columns.Add('k%d' % index, clr.GetClrType(Double if self.numeric[index] else String))
        self.data = data
        self.view = data.DefaultView

    def _retype(self, cells):
        """Re-decides which columns are numeric for a new set of rows (a table
        opened empty and filled later, say): a DataColumn cannot change type once
        it held data, so the table is rebuilt and rebound, keeping the filter."""
        numeric = numeric_columns(cells, len(self.columns))
        if numeric == self.numeric:
            return
        self.numeric = numeric
        self.grid.ItemsSource = None
        self._new_table()
        offset = 1 if self.checkboxes else 0
        for index, is_number in enumerate(numeric):
            self._style_column(self.grid.Columns[index + offset], index, is_number, self.resources, None)
        self.grid.ItemsSource = self.view

    def _wire(self):
        from System.Windows.Input import (FocusNavigationDirection, Key, Keyboard, ModifierKeys,
                                          TraversalRequest)
        grid = self.grid

        def preview_down(sender, args):
            if not self.checkboxes:
                return
            row_view = _row_view_at(args.OriginalSource)
            if row_view is not None:
                self._toggle([int(row_view['idx'])])

        def key_down(sender, args):
            if args.Key == Key.Tab:
                # Tab leaves the table instead of walking its cells.
                backwards = (Keyboard.Modifiers & ModifierKeys.Shift) == ModifierKeys.Shift
                direction = FocusNavigationDirection.Previous if backwards else FocusNavigationDirection.Next
                grid.MoveFocus(TraversalRequest(direction))
                args.Handled = True
            elif args.Key == Key.Space and self.checkboxes:
                indices = self.selected_indices()
                if indices:
                    self._toggle(indices)
                    args.Handled = True
            elif args.Key == Key.Enter and self.on_open is not None:
                values = self.selected_values()
                if values:
                    args.Handled = True
                    self.on_open(values[0])

        def double_click(sender, args):
            if self.on_open is None:
                return
            if _row_view_at(args.OriginalSource) is None:
                return
            values = self.selected_values()
            if values:
                self.on_open(values[0])

        def selection_changed(sender, args):
            self._changed()

        def focused(sender, args):
            # Keyboard focus arriving with nothing selected would be invisible:
            # the selection rail is the focus cue in a table.
            if grid.SelectedItems.Count == 0 and self.view.Count:
                grid.SelectedIndex = 0

        grid.GotKeyboardFocus += safe(focused, 'table focus', self.logger)
        grid.PreviewMouseLeftButtonDown += safe(preview_down, 'table click', self.logger)
        grid.PreviewKeyDown += safe(key_down, 'table key', self.logger)
        grid.MouseDoubleClick += safe(double_click, 'table open', self.logger)
        grid.SelectionChanged += safe(selection_changed, 'table selection', self.logger)

    def _changed(self):
        if self.on_change is not None:
            self.on_change()

    def _toggle(self, indices):
        rows = self.data.Rows
        turn_on = any(not bool(rows[i]['chk']) for i in indices)
        for i in indices:
            rows[i]['chk'] = turn_on
            self.rows[i]['checked'] = turn_on
        self._changed()

    # -- public --

    @property
    def element(self):
        """The UIElement to put in a layout (the DataGrid)."""
        return self.grid

    def update(self, rows):
        """Replaces the rows, keeping ticks on rows whose value was ticked before
        (when values are hashable) and re-applying the filter."""
        before = set()
        for row in self.rows:
            if row['checked']:
                try:
                    before.add(row['value'])
                except TypeError:
                    pass
        normalized = normalize_rows(rows)
        for row in normalized:
            try:
                if row['value'] in before:
                    row['checked'] = True
            except TypeError:
                pass
        self._retype([r['cells'] for r in normalized])
        self._load(normalized)
        self.set_filter(self.query)
        self._changed()

    def set_filter(self, query):
        """Shows only rows containing every word of query (any column)."""
        self.query = query or ''
        expression = row_filter(self.query)
        try:
            self.view.RowFilter = expression
        except Exception:
            # A pattern DataView refuses: fall back to an exact id list.
            wanted = [str(i) for i, row in enumerate(self.rows)
                      if matches(self.query, search_text(row['cells']))]
            self.view.RowFilter = 'idx IN (%s)' % ','.join(wanted) if wanted else 'idx < 0'
        self._changed()

    def total(self):
        return len(self.rows)

    def visible_count(self):
        return int(self.view.Count)

    def visible_indices(self):
        return [int(self.view[i]['idx']) for i in range(self.view.Count)]

    def selected_indices(self):
        out = []
        for item in self.grid.SelectedItems:
            try:
                out.append(int(item['idx']))
            except Exception:
                pass
        return out

    def selected_values(self):
        """Values of the selected rows, in table order."""
        return [self.rows[i]['value'] for i in sorted(self.selected_indices())]

    def checked_indices(self):
        return [i for i, row in enumerate(self.rows) if row['checked']]

    def checked_values(self):
        """Values of the ticked rows, in the original row order."""
        return [row['value'] for row in self.rows if row['checked']]

    def set_checked(self, values=None, on=True, visible_only=False):
        """Ticks (on=True) or clears rows: values=None means every row (or every
        visible row with visible_only)."""
        if values is None:
            indices = self.visible_indices() if visible_only else range(len(self.rows))
        else:
            wanted = list(values)
            indices = [i for i, row in enumerate(self.rows) if row['value'] in wanted]
        data_rows = self.data.Rows
        for i in indices:
            data_rows[i]['chk'] = bool(on)
            self.rows[i]['checked'] = bool(on)
        self._changed()

    def select_values(self, values):
        """Selects (highlights) the rows with these values."""
        wanted = list(values or [])
        from System.Windows.Controls import DataGridSelectionMode
        if self.grid.SelectionMode == DataGridSelectionMode.Single:
            # SelectedItems is read-only in single mode ("Can only change SelectedItems
            # collection in multiple selection modes"): select the first match instead.
            self.grid.SelectedItem = None
            for i in range(self.view.Count):
                row_view = self.view[i]
                if self.rows[int(row_view['idx'])]['value'] in wanted:
                    self.grid.SelectedItem = row_view
                    break
            return
        self.grid.SelectedItems.Clear()
        for i in range(self.view.Count):
            row_view = self.view[i]
            if self.rows[int(row_view['idx'])]['value'] in wanted:
                self.grid.SelectedItems.Add(row_view)

    def focus_first(self):
        """Puts keyboard focus on the first visible row (selecting it)."""
        if self.view.Count:
            if not self.grid.SelectedItems.Count:
                self.grid.SelectedIndex = 0
            self.grid.Focus()


def _row_view_at(source):
    """The DataRowView of the DataGridRow under a clicked element, or None (header,
    scrollbar, empty space)."""
    from System.Windows.Controls import DataGridRow
    from System.Windows.Controls.Primitives import DataGridColumnHeader, ScrollBar
    from System.Windows.Media import Visual, VisualTreeHelper
    node = source
    while node is not None:
        if isinstance(node, (DataGridColumnHeader, ScrollBar)):
            return None
        if isinstance(node, DataGridRow):
            return node.Item
        if not isinstance(node, Visual):
            try:
                node = node.Parent
            except Exception:
                return None
            continue
        node = VisualTreeHelper.GetParent(node)
    return None


# ---- modal helpers -------------------------------------------------------------------


def show_modal(win):
    """Shows a window modally, owned by Navisworks with Fluent chrome. Raises
    RuntimeError under `pynavis run`. Returns the DialogResult (True/False/None)."""
    _refuse_under_runner()
    _wpf()
    from PyNavis.Runtime.Forms import FluentChrome
    FluentChrome.Apply(win)
    return win.ShowDialog()


def modal_loop(build, show=None):
    """A modal window whose actions may need a progress window.

    pyNavis' progress window re-enables the Navisworks main window when it closes. Started
    from a button of a MODAL window, that leaves Navisworks live underneath the dialog. So
    such an action does not run in place: it calls defer(job), which closes the window;
    job() then runs with no modal window open (free to use namo.progress.run, prompts,
    toasts), and the window is built and shown again with fresh rows.

        def build(defer):
            def on_refresh(selected):
                defer(lambda: refresh_links(doc, selected))
            return ui.build_table('Links', HEADERS, rows(), actions=[('Refresh', on_refresh)])
        ui.modal_loop(build)

    build(defer) returns the unshown window and is called once per round, so it reads
    its rows each time. Returns the last window once it closes with nothing deferred.
    A job that raises is logged and toasted, and the window still comes back. show is a
    test seam for show_modal."""
    show = show or show_modal
    logger = pinned_logger()
    while True:
        pending = []
        holder = {}

        def defer(job, _pending=pending, _holder=holder):
            _pending.append(job)
            win_ = _holder.get('win')
            if win_ is not None:
                _close_window(win_)
        win = build(defer)
        holder['win'] = win
        if not pending:                     # a job deferred while building runs first
            show(win)
        if not pending:
            return win
        for job in list(pending):
            try:
                job()
            except Exception as error:
                log_error('deferred action failed:\n%s' % traceback.format_exc(), logger)
                _toast_error('Could not finish that', str(error))


def _close_window(win):
    state = getattr(win, 'Tag', None)
    try:
        if isinstance(state, TableState):
            state.close()
        else:
            win.Close()
    except Exception:
        pass


def _close_with(win, result):
    try:
        win.DialogResult = result
    except Exception:
        try:
            win.Close()
        except Exception:
            pass


# ---- form ---------------------------------------------------------------------------


class FormState(object):
    """What build_form puts in window.Tag: the field specs, the live controls and,
    after OK, `result` (the values dict) and `accepted` True."""

    def __init__(self, win, fields, units, form_validate, logger):
        self.window = win
        self.fields = fields
        self.units = units
        self.form_validate = form_validate
        self.logger = logger
        self.controls = {}          # key -> _Bag(kind, read, set_error, set_enabled, focus)
        self.result = None
        self.accepted = False
        self.tried = False
        self.checked_raws = None    # the raws and errors of the last full check (accept)
        self.checked_errors = {}

    def raws(self):
        return dict((key, bag.read()) for key, bag in self.controls.items())

    def _parsers(self):
        try:
            from pynavis import lengths
            return lengths.parse
        except Exception:
            return None

    def collect(self):
        """(values, errors) for the form as it stands, without closing it. The FULL
        check: paths are probed and the form-level validate runs."""
        return collect(self.fields, self.raws(), self._parsers(), self.units,
                       form_validate=self.form_validate)

    def _check(self):
        """The full check, remembered so the per-keystroke pass can keep showing what
        it found without probing again (carry_errors)."""
        raws = self.raws()
        from_form = {}      # the errors the form-level validate added (they span fields)
        values, errors = collect(self.fields, raws, self._parsers(), self.units,
                                 form_validate=self.form_validate, form_keys=from_form)
        remembered = dict(errors)
        remembered['__form__'] = from_form
        self.checked_raws = raws
        self.checked_errors = remembered
        return values, errors

    def refresh(self):
        """Re-applies enabled_if and, once OK was tried, the inline errors. Runs on
        every keystroke, so it never probes a path and never calls the form-level
        validate: those errors are carried from the last OK until the text they are
        about changes, and are checked again on the next OK."""
        raws = self.raws()
        values, errors = collect(self.fields, raws, self._parsers(), self.units, quick=True)
        errors = carry_errors(self.fields, raws, errors, self.checked_raws, self.checked_errors, values)
        self._show(values, errors)
        return values, errors

    def _show(self, values, errors):
        for field in self.fields:
            key = field.get('key')
            if key not in self.controls:
                continue
            bag = self.controls[key]
            bag.set_enabled(is_enabled(field, values))
            if self.tried:
                bag.set_error(errors.get(key))

    def accept(self):
        """Validates in full; closes with the values when everything reads, else shows
        the errors inline and focuses the first bad field. Returns True on success."""
        self.tried = True
        values, errors = self._check()
        self._show(values, errors)
        if errors:
            for field in self.fields:
                key = field.get('key')
                if key in errors and key in self.controls:
                    self.controls[key].focus()
                    break
            return False
        self.result = values
        self.accepted = True
        _close_with(self.window, True)
        return True

    def set_raw(self, key, raw):
        """Test/automation seam: puts a raw value into a field's control."""
        self.controls[key].write(raw)
        self.refresh()


def _document_units():
    try:
        from pynavis._api import Application
        return str(Application.ActiveDocument.Units)
    except Exception:
        return 'Meters'


def build_form(title, fields, intro=None, ok='OK', cancel='Cancel', width=460, units=None,
               validate=None):
    """The form window, unshown; window.Tag is its FormState. See form()."""
    _wpf()
    from System.Windows.Controls import Dock, DockPanel, StackPanel
    specs = normalize_fields(fields)
    units = units or (_document_units() if any(f['kind'] == 'length' for f in specs) else None)
    logger = pinned_logger()
    win = window(title, width=width, height=None, resizable=False)
    state = FormState(win, specs, units, validate, logger)
    win.Tag = state

    body = StackPanel()
    body.Margin = _thickness(24, 20, 24, 8)
    if intro:
        lead = text(intro)
        lead.Margin = _thickness(0, 0, 0, 16)
        body.Children.Add(lead)
    for field in specs:
        body.Children.Add(_field_row(state, field))

    ok_button = button(ok, lambda: state.accept(), 'primary', logger)
    ok_button.IsDefault = True
    cancel_button = button(cancel, lambda: _close_with(win, False), 'secondary', logger)
    cancel_button.IsCancel = True
    bar = footer([ok_button, cancel_button])

    layout = DockPanel()
    DockPanel.SetDock(bar, Dock.Bottom)
    layout.Children.Add(bar)
    area = work_area()
    layout.Children.Add(scroll(body, max_height=(area[3] - area[1]) * 0.8))
    win.Content = layout

    def first_focus(sender, args):
        for field in specs:
            key = field.get('key')
            if key in state.controls and state.controls[key].enabled():
                state.controls[key].focus()
                break
    win.ContentRendered += safe(first_focus, 'form focus', logger)
    state.refresh()
    return win


def form(title, fields, intro=None, ok='OK', cancel='Cancel', width=460, units=None,
         validate=None):
    """A modal form; returns {key: value} for every non-label field, or None when
    cancelled (Esc, Cancel, close box). Never closes on invalid input: errors show
    in red under each field. See README for the field kinds and their values.
    units: document units for 'length' fields (default: the active document's)."""
    win = build_form(title, fields, intro, ok, cancel, width, units, validate)
    show_modal(win)
    state = win.Tag
    return state.result if state.accepted else None


def _field_row(state, field):
    """One field: label, control, hint/error line. Registers the control bag."""
    from System.Windows import Visibility
    from System.Windows.Controls import StackPanel
    t = tokens()
    kind = field['kind']
    row = StackPanel()
    row.Margin = _thickness(0, 0, 0, 16)
    if kind == 'separator':
        return separator()
    if kind == 'label':
        block = text(field.get('text', field.get('label', '')), 13, muted=bool(field.get('muted')))
        row.Children.Add(block)
        return row

    label_block = None
    if kind != 'check' and field.get('label'):
        label_block = text(field['label'])
        label_block.Margin = _thickness(0, 0, 0, 6)
        row.Children.Add(label_block)

    control, bag = _field_control(state, field)
    row.Children.Add(control)

    hint_text = field.get('hint')
    if kind == 'length' and not hint_text:
        hint_text = length_hint(state.units)
        hint_text = hint_text[0].upper() + hint_text[1:]
    note = text(hint_text or '', 12, muted=True)
    note.Margin = _thickness(0, 4, 0, 0)
    note.Visibility = Visibility.Visible if hint_text else Visibility.Collapsed
    row.Children.Add(note)

    shell = bag.shell

    def set_error(message):
        if message:
            note.Text = message
            note.Foreground = brush(hex_of(t.Error))
            note.Visibility = Visibility.Visible
            if shell is not None:
                shell.BorderBrush = brush(hex_of(t.Error))
        else:
            note.Text = hint_text or ''
            note.Foreground = brush(hex_of(t.Muted))
            note.Visibility = Visibility.Visible if hint_text else Visibility.Collapsed
            if shell is not None:
                shell.BorderBrush = brush(hex_of(t.LineStrong))

    def set_enabled(on):
        control.IsEnabled = bool(on)
        if label_block is not None:
            label_block.Foreground = brush(hex_of(t.Ink if on else t.Muted))

    bag.set_error = set_error
    bag.set_enabled = set_enabled
    bag.enabled = lambda: bool(control.IsEnabled)
    state.controls[field['key']] = bag
    return row


def _field_control(state, field):
    """(element, bag) for one field kind; bag has read(), write(raw), focus(), shell."""
    from System.Windows.Controls import Dock, DockPanel
    kind = field['kind']
    logger = state.logger
    changed = safe(lambda *args: state.refresh(), 'form change', logger)

    if kind in ('text', 'textarea', 'int', 'number', 'length', 'date'):
        suffix = field.get('suffix')
        if kind == 'length' and suffix is None:
            try:
                from pynavis import lengths
                suffix = lengths.suffix(state.units) or None
            except Exception:
                suffix = None
        formatter = None
        if kind == 'length':
            try:
                from pynavis import lengths
                formatter = lengths.format_input
            except Exception:
                formatter = None
        placeholder = field.get('placeholder') or ('YYYY-MM-DD' if kind == 'date' else None)
        element, box = text_box(default_text(field, state.units, formatter,
                                             state._parsers() if kind == 'length' else None), placeholder,
                                suffix, multiline=(kind == 'textarea'), rows=field.get('rows', 4))
        box.TextChanged += lambda s, e: changed()
        shell = element if placeholder is None else element.Children[0]
        if kind == 'date':
            today = button('Today', lambda: _write_text(box, _today()), 'quiet', logger)
            today.Margin = _thickness(8, 0, 0, 0)
            dock = DockPanel()
            DockPanel.SetDock(today, Dock.Right)
            dock.Children.Add(today)
            dock.Children.Add(element)
            element = dock
        bag = _Bag(shell=shell, read=lambda: box.Text, write=lambda raw: _write_text(box, raw),
                   focus=lambda: _focus_text(box), box=box)
        return element, bag

    if kind in ('file_open', 'file_save', 'folder'):
        element, box = text_box(default_text(field), field.get('placeholder'))
        box.TextChanged += lambda s, e: changed()
        shell = element if not field.get('placeholder') else element.Children[0]

        def browse():
            picked = _browse(kind, field, box.Text)
            if picked:
                _write_text(box, picked)
        browse_button = button('Browse', browse, 'secondary', logger)
        browse_button.MinWidth = 0.0
        browse_button.Margin = _thickness(8, 0, 0, 0)
        dock = DockPanel()
        DockPanel.SetDock(browse_button, Dock.Right)
        dock.Children.Add(browse_button)
        dock.Children.Add(element)
        bag = _Bag(shell=shell, read=lambda: box.Text, write=lambda raw: _write_text(box, raw),
                   focus=lambda: _focus_text(box), box=box)
        return dock, bag

    if kind == 'color':
        return _color_control(state, field, changed)

    if kind == 'choice':
        control = combo(field['options'], field.get('default'))
        control.SelectionChanged += lambda s, e: changed()

        def write(raw):
            index = _index_of([v for _l, v in control.Tag.pairs], raw)
            control.SelectedIndex = index if index is not None else -1
        bag = _Bag(shell=None, read=lambda: combo_value(control), write=write,
                   focus=lambda: control.Focus(), control=control)
        return control, bag

    if kind == 'radio':
        pairs = options_of(field)
        panel, buttons = radio_group(field['options'], field.get('default'),
                                     inline=bool(field.get('inline')), group='namo_' + field['key'])
        for control in buttons:
            control.Checked += lambda s, e: changed()

        def write(raw):
            for control, (_label, value) in zip(buttons, pairs):
                control.IsChecked = value == raw
        bag = _Bag(shell=None, read=lambda: radio_value(buttons, pairs), write=write,
                   focus=lambda: buttons[0].Focus() if buttons else None, buttons=buttons)
        return panel, bag

    if kind == 'check':
        control = check(field.get('label', ''), bool(field.get('default')))
        control.Checked += lambda s, e: changed()
        control.Unchecked += lambda s, e: changed()

        def write(raw):
            control.IsChecked = bool(raw)
        bag = _Bag(shell=None, read=lambda: bool(control.IsChecked), write=write,
                   focus=lambda: control.Focus(), control=control)
        return control, bag

    if kind == 'multi':
        return _multi_control(state, field, changed)

    raise ValueError('no control for kind %r' % kind)


def _write_text(box, raw):
    box.Text = '' if raw is None else str(raw)
    box.CaretIndex = len(box.Text)


def _focus_text(box):
    box.Focus()
    box.SelectAll()


def _today():
    import datetime
    return datetime.date.today().strftime('%Y-%m-%d')


def _browse(kind, field, current):
    """Runs the file/folder dialog for a path field; returns the path or None."""
    from pynavis import forms
    if kind == 'folder':
        return forms.pick_folder(field.get('title') or 'Select folder',
                                 current if current and os.path.isdir(current) else None)
    file_filter = field.get('filter') or 'All files (*.*)|*.*'
    if kind == 'file_open':
        return forms.open_file(file_filter, field.get('title') or 'Open file')
    return forms.save_file(file_filter, save_dialog_name(current, field.get('default_name')),
                           field.get('title') or 'Save file')


def save_dialog_name(current, default_name=None, isdir=None):
    """What the Save dialog is opened with for a file_save field showing `current`.

    The whole path when its folder exists: the Windows dialog then opens IN that folder
    with the file name filled in (the same route the shipped exporters use), instead
    of in whatever folder was used last. Only the file name when the folder is missing
    or the field holds a bare name; default_name (or '') when the field is empty."""
    text = (current or '').strip().strip('"')
    if not text:
        return default_name or ''
    isdir = isdir or os.path.isdir
    folder = os.path.dirname(text)
    try:
        if folder and isdir(folder):
            return text
    except Exception:
        pass
    return os.path.basename(text) or (default_name or '')


def _color_control(state, field, changed):
    from System.Windows.Controls import Border, Dock, DockPanel
    from System.Windows import CornerRadius
    t = tokens()
    logger = state.logger
    element, box = text_box(default_text(field), None)
    swatch = Border()
    swatch.Width = 32.0
    swatch.Height = 32.0
    swatch.CornerRadius = CornerRadius(4)
    swatch.BorderThickness = _thickness(1)
    swatch.BorderBrush = brush(hex_of(t.LineStrong))
    swatch.Margin = _thickness(0, 0, 8, 0)

    def paint_swatch():
        from namo import colors
        value = colors.parse_hex(box.Text)
        swatch.Background = brush(value) if value else brush(hex_of(t.Surface))

    def on_text(sender, args):
        paint_swatch()
        changed()
    box.TextChanged += safe(on_text, 'color text', logger)
    paint_swatch()

    def pick():
        picked = _pick_color(box.Text)
        if picked:
            _write_text(box, picked)
    pick_button = button('Pick', pick, 'secondary', logger)
    pick_button.MinWidth = 0.0
    pick_button.Margin = _thickness(8, 0, 0, 0)
    dock = DockPanel()
    DockPanel.SetDock(swatch, Dock.Left)
    DockPanel.SetDock(pick_button, Dock.Right)
    dock.Children.Add(swatch)
    dock.Children.Add(pick_button)
    dock.Children.Add(element)
    bag = _Bag(shell=element, read=lambda: box.Text, write=lambda raw: _write_text(box, raw),
               focus=lambda: _focus_text(box), box=box)
    return dock, bag


def _pick_color(current):
    """The Windows colour dialog; returns 'RRGGBB' or None."""
    _wpf()
    from System.Windows.Forms import ColorDialog, DialogResult
    from System.Drawing import Color
    from namo import colors
    dialog = ColorDialog()
    dialog.FullOpen = True
    value = colors.parse_hex(current)
    if value:
        r, g, b = colors.hex_to_rgb(value)
        dialog.Color = Color.FromArgb(255, r, g, b)
    try:
        if dialog.ShowDialog() == DialogResult.OK:
            c = dialog.Color
            return colors.rgb_to_hex(c.R, c.G, c.B)
        return None
    finally:
        dialog.Dispose()


def _multi_control(state, field, changed):
    from System.Windows import HorizontalAlignment
    from System.Windows.Controls import Dock, DockPanel, StackPanel
    pairs = options_of(field)
    ticked = list(field.get('default') or field.get('checked') or [])
    rows = [{'cells': [label], 'value': value, 'checked': value in ticked} for label, value in pairs]
    table = Table([field.get('label') or ''], rows, checkboxes=True, multiselect=True,
                  show_headers=False, on_change=lambda: (changed(), counter_refresh()),
                  logger=state.logger)
    table.grid.Height = 32.0 * min(max(len(rows), 3), 8) + 2.0
    panel = StackPanel()
    counter = hint('')

    def counter_refresh():
        counter.Text = count_text(len(table.checked_values()), table.total(),
                                  table.visible_count(), 'ticked')

    if len(rows) > SEARCHABLE_OVER:
        top = DockPanel()
        top.Margin = _thickness(0, 0, 0, 8)
        all_button = button('All', lambda: table.set_checked(None, True, visible_only=True), 'quiet',
                            state.logger)
        none_button = button('None', lambda: table.set_checked(None, False, visible_only=True), 'quiet',
                             state.logger)
        for control in (none_button, all_button):
            control.Margin = _thickness(4, 0, 0, 0)
            DockPanel.SetDock(control, Dock.Right)
            top.Children.Add(control)
        search, _box = search_box('Filter', lambda query: table.set_filter(query))
        top.Children.Add(search)
        panel.Children.Add(top)
    panel.Children.Add(table.element)
    counter.Margin = _thickness(0, 4, 0, 0)
    counter.HorizontalAlignment = HorizontalAlignment.Left
    panel.Children.Add(counter)
    counter_refresh()

    def write(raw):
        table.set_checked(None, False)
        table.set_checked(list(raw or []), True)
    bag = _Bag(shell=None, read=lambda: table.checked_values(), write=write,
               focus=lambda: table.focus_first(), table=table)
    return panel, bag


# ---- choose -----------------------------------------------------------------------


class ChooseState(object):
    """window.Tag of build_choose: `table`, `result` and `accepted` after OK."""

    def __init__(self, win, table, multiselect):
        self.window = win
        self.table = table
        self.multiselect = multiselect
        self.result = None
        self.accepted = False

    def values(self):
        if self.multiselect:
            return self.table.checked_values()
        return self.table.selected_values()[:1]

    def accept(self):
        values = self.values()
        if not values:
            return False
        self.result = values
        self.accepted = True
        _close_with(self.window, True)
        return True


def build_choose(title, rows, columns, multiselect=True, checked=None, prompt=None, search=True,
                 ok='OK', width=640, height=540):
    """The chooser window, unshown; window.Tag is its ChooseState. See choose()."""
    _wpf()
    from System.Windows import GridLength, GridUnitType
    from System.Windows.Controls import Dock, DockPanel, Grid, RowDefinition
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    logger = pinned_logger()
    win = window(title, width=width, height=height, resizable=True, min_width=420, min_height=360)
    normalized = normalize_rows(rows)
    wanted = list(checked or [])
    if multiselect:
        for row in normalized:
            if row['value'] in wanted:
                row['checked'] = True
    holder = {}

    def changed():
        # The table can fire this while the window is still being built (a single-select
        # chooser opened on a row), before the footer exists: holder only gets 'refresh'
        # once refresh_footer is defined below.
        refresh = holder.get('refresh')
        if holder.get('state') is None or refresh is None:
            return
        refresh()

    table = Table(columns, normalized, checkboxes=bool(multiselect), multiselect=True,
                  on_open=(None if multiselect else (lambda value: holder['state'].accept())),
                  on_change=changed, logger=logger)
    state = ChooseState(win, table, bool(multiselect))
    holder['state'] = state
    win.Tag = state
    if not multiselect and wanted:
        table.select_values(wanted[:1])

    root = Grid()
    root.Margin = _thickness(16, 16, 16, 12)
    for size in ('auto', 'auto', 'star'):
        definition = RowDefinition()
        definition.Height = GridLength(1, GridUnitType.Star) if size == 'star' else GridLength.Auto
        root.RowDefinitions.Add(definition)
    if prompt:
        lead = text(prompt)
        lead.Margin = _thickness(0, 0, 0, 12)
        Grid.SetRow(lead, 0)
        root.Children.Add(lead)
    search_input = None
    if search or multiselect:
        bar = DockPanel()
        bar.Margin = _thickness(0, 0, 0, 8)
        if multiselect:
            clear_button = button('Clear', lambda: table.set_checked(None, False, visible_only=True),
                                  'quiet', logger)
            all_button = button('Select all', lambda: table.set_checked(None, True, visible_only=True),
                                'quiet', logger)
            for control in (clear_button, all_button):
                control.Margin = _thickness(4, 0, 0, 0)
                DockPanel.SetDock(control, Dock.Right)
                bar.Children.Add(control)
        if search:
            element, search_input = search_box('Filter', lambda query: table.set_filter(query))
            bar.Children.Add(element)
        Grid.SetRow(bar, 1)
        root.Children.Add(bar)
    Grid.SetRow(table.element, 2)
    root.Children.Add(table.element)

    counter = hint('')
    ok_button = button(ok, lambda: state.accept(), 'primary', logger)
    ok_button.IsDefault = True
    cancel_button = button('Cancel', lambda: _close_with(win, False), 'secondary', logger)
    cancel_button.IsCancel = True
    bar_bottom = footer([ok_button, cancel_button], left=counter, padding=16)

    def refresh_footer():
        if multiselect:
            counter.Text = count_text(len(table.checked_values()), table.total(), table.visible_count())
            ok_button.IsEnabled = bool(table.checked_values())
        else:
            counter.Text = '%s of %s shown' % ('{:,}'.format(table.visible_count()),
                                               '{:,}'.format(table.total())) \
                if table.visible_count() != table.total() else '%s rows' % '{:,}'.format(table.total())
            ok_button.IsEnabled = bool(table.selected_values())
    holder['refresh'] = refresh_footer

    layout = DockPanel()
    DockPanel.SetDock(bar_bottom, Dock.Bottom)
    layout.Children.Add(bar_bottom)
    layout.Children.Add(root)
    win.Content = layout

    def keys(sender, args):
        if args.Key == Key.F and Keyboard.Modifiers == ModifierKeys.Control and search_input is not None:
            search_input.Focus()
            search_input.SelectAll()
            args.Handled = True
        elif args.Key == Key.Down and search_input is not None and search_input.IsKeyboardFocused:
            table.focus_first()
            args.Handled = True
        elif args.Key == Key.Enter and table.grid.IsKeyboardFocusWithin:
            args.Handled = state.accept() or True
    win.PreviewKeyDown += safe(keys, 'choose keys', logger)

    def first_focus(sender, args):
        if search_input is not None:
            search_input.Focus()
        else:
            table.focus_first()
    win.ContentRendered += safe(first_focus, 'choose focus', logger)
    refresh_footer()
    return win


def choose(title, rows, columns, multiselect=True, checked=None, prompt=None, search=True,
           ok='OK', width=640, height=540):
    """A modal multi-column picker. rows: [{'value': v, 'cells': [...]}] (plain
    lists work too: the value is the row index). columns: header texts.
    multiselect: tick boxes (click or Space), Select all / Clear act on the rows
    the filter shows; otherwise one row (double-click or Enter picks it).
    checked: values to open ticked (or selected). Returns [values] (ticked ones in
    row order; a one-item list in single mode), or None when cancelled."""
    win = build_choose(title, rows, columns, multiselect, checked, prompt, search, ok, width, height)
    show_modal(win)
    state = win.Tag
    return state.result if state.accepted else None


# ---- table window ---------------------------------------------------------------------


def _actions(actions):
    """[{'label', 'fn', 'needs_selection', 'primary'}] from tuples or dicts."""
    out = []
    for action in actions or []:
        if isinstance(action, dict):
            spec = {'label': action['label'], 'fn': action['fn'],
                    'needs_selection': action.get('needs_selection', True),
                    'primary': bool(action.get('primary', False))}
        else:
            spec = {'label': action[0], 'fn': action[1],
                    'needs_selection': action[2] if len(action) > 2 else True, 'primary': False}
        out.append(spec)
    return out


class TableState(object):
    """window.Tag of a table window: `table`, `status` TextBlock, `update(rows,
    status=None)`, `selected()`, `close()`."""

    def __init__(self, win, table, status_block, buttons, logger):
        self.window = win
        self.table = table
        self.status_block = status_block
        self.buttons = buttons
        self.logger = logger

    def update(self, rows, status=None):
        """Replaces the rows (keeping the filter) and, when given, the status line."""
        self.table.update(rows)
        if status is not None:
            self.status_block.Text = str(status)

    def set_status(self, status):
        self.status_block.Text = '' if status is None else str(status)

    def selected(self):
        return self.table.selected_values()

    def close(self):
        try:
            self.window.Close()
        except Exception:
            pass


def build_table(title, headers, rows, actions=None, on_open=None, status=None, width=820,
                height=560, close_label='Close'):
    """The table window, unshown; window.Tag is its TableState. See table_window()."""
    _wpf()
    from System.Windows import GridLength, GridUnitType, VerticalAlignment
    from System.Windows.Controls import Dock, DockPanel, Grid, RowDefinition
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    logger = pinned_logger()
    win = window(title, width=width, height=height, resizable=True, min_width=480, min_height=320)
    specs = _actions(actions)
    buttons = []
    holder = {}

    def changed():
        selected = bool(holder['table'].selected_indices()) if 'table' in holder else False
        for spec, control in zip(specs, buttons):
            control.IsEnabled = selected or not spec['needs_selection']
        if 'counter' in holder:
            table_ = holder['table']
            visible, total = table_.visible_count(), table_.total()
            holder['counter'].Text = ('%s of %s rows' % ('{:,}'.format(visible), '{:,}'.format(total))
                                      if visible != total else '%s rows' % '{:,}'.format(total))

    def opened(value):
        if on_open is not None:
            on_open(value)

    table = Table(headers, rows, checkboxes=False, multiselect=True,
                  on_open=opened if on_open is not None else None, on_change=changed, logger=logger)
    holder['table'] = table

    status_block = hint('' if status is None else str(status))
    state = TableState(win, table, status_block, buttons, logger)
    win.Tag = state

    def run_action(spec):
        def go():
            try:
                spec['fn'](table.selected_values())
            except Exception as error:
                log_error('%s failed:\n%s' % (spec['label'], traceback.format_exc()), logger)
                _toast_error('Could not %s' % spec['label'].lower(), str(error))
        return go

    for spec in specs:
        control = button(spec['label'], run_action(spec), 'primary' if spec['primary'] else 'secondary',
                         logger)
        buttons.append(control)
    close_button = button(close_label, lambda: state.close(), 'secondary', logger)
    close_button.IsCancel = True

    root = Grid()
    root.Margin = _thickness(16, 16, 16, 12)
    for size in ('auto', 'star'):
        definition = RowDefinition()
        definition.Height = GridLength(1, GridUnitType.Star) if size == 'star' else GridLength.Auto
        root.RowDefinitions.Add(definition)
    bar = DockPanel()
    bar.Margin = _thickness(0, 0, 0, 8)
    counter = hint('')
    counter.Margin = _thickness(12, 0, 0, 0)
    counter.VerticalAlignment = VerticalAlignment.Center
    DockPanel.SetDock(counter, Dock.Right)
    bar.Children.Add(counter)
    holder['counter'] = counter
    element, search_input = search_box('Filter', lambda query: table.set_filter(query))
    bar.Children.Add(element)
    Grid.SetRow(bar, 0)
    root.Children.Add(bar)
    Grid.SetRow(table.element, 1)
    root.Children.Add(table.element)

    bottom = footer(buttons + [close_button], left=status_block, padding=16)
    layout = DockPanel()
    DockPanel.SetDock(bottom, Dock.Bottom)
    layout.Children.Add(bottom)
    layout.Children.Add(root)
    win.Content = layout

    def keys(sender, args):
        if args.Key == Key.F and Keyboard.Modifiers == ModifierKeys.Control:
            search_input.Focus()
            search_input.SelectAll()
            args.Handled = True
        elif args.Key == Key.Down and search_input.IsKeyboardFocused:
            table.focus_first()
            args.Handled = True
        elif args.Key == Key.Escape:
            state.close()
            args.Handled = True
    win.PreviewKeyDown += safe(keys, 'table keys', logger)
    win.ContentRendered += safe(lambda s, e: table.focus_first(), 'table focus', logger)
    changed()
    return win


def table_window(title, headers, rows, actions=None, on_open=None, modeless=False, key=None,
                 status=None, width=820, height=560):
    """A results table: filter box (Ctrl+F), sortable headers, multi-select rows,
    a status line, action buttons and Close (Esc).

    rows: [{'cells': [...], 'value': v}]. actions: [(label, fn)] or
    [(label, fn, needs_selection)] or dicts {'label', 'fn', 'needs_selection'
    (default True: greyed until a row is selected), 'primary'}; fn(selected
    values) runs with exceptions logged and toasted. on_open(value) on
    double-click or Enter.

    modeless=False: blocks until closed (returns the closed window).
    modeless=True: one window per `key` (default: title) that stays open beside
    Navisworks; calling again with the same key updates its rows and status and
    brings it forward instead of opening a second one. Callbacks then run OUTSIDE
    the tool's run: use objects pinned during the run (script.bind()).

    Returns the Window; window.Tag.update(rows, status) refreshes it."""
    if not modeless:
        win = build_table(title, headers, rows, actions, on_open, status, width, height)
        show_modal(win)
        return win
    existing = Modeless.get(key or title)
    if existing is not None:
        state = existing.Tag
        if isinstance(state, TableState):
            state.update(rows, status)
            try:
                existing.Activate()
            except Exception:
                pass
            return existing
    win = build_table(title, headers, rows, actions, on_open, status, width, height)
    Modeless(key or title, title, None, window_factory=lambda: win).show()
    return win


def update_table(win, rows, status=None):
    """Same as win.Tag.update(rows, status)."""
    win.Tag.update(rows, status)


# ---- modeless ---------------------------------------------------------------------------


class Modeless(object):
    """Create-or-activate a modeless window, one per key, surviving the run.

        Modeless('my-tool', 'My tool', build).show()

    build(window) fills the (themed, unshown) window and may return its content
    (set as window.Content) or None. show() returns the live window: the existing
    one, brought forward, when the key is already open. The window is owned by
    Navisworks, gets ElementHost.EnableModelessKeyboardInterop BEFORE Show (or
    typing never reaches it), and forgets itself when closed. Wrap every handler
    you attach with ui.safe().
    """

    HOLDER = 'ui_modeless'

    def __init__(self, key, title, content_builder=None, width=560, height=None,
                 window_factory=None):
        self.key = str(key)
        self.title = title
        self.content_builder = content_builder
        self.width = width
        self.height = height
        self.window_factory = window_factory

    @classmethod
    def _windows(cls):
        holder = _holder(cls.HOLDER)
        windows = getattr(holder, 'windows', None)
        if windows is None:
            windows = {}
            holder.windows = windows
        return windows

    @classmethod
    def get(cls, key):
        """The open window for key, or None (a closed one is forgotten)."""
        windows = cls._windows()
        win = windows.get(str(key))
        if win is None:
            return None
        try:
            if win.IsLoaded and win.IsVisible:
                return win
        except Exception:
            pass
        windows.pop(str(key), None)
        return None

    @classmethod
    def close(cls, key):
        win = cls.get(key)
        if win is not None:
            try:
                win.Close()
            except Exception:
                pass

    def build(self):
        """The unshown window (for tests and callers that show it themselves)."""
        if self.window_factory is not None:
            win = self.window_factory()
        else:
            win = window(self.title, width=self.width, height=self.height)
        if self.content_builder is not None:
            content = self.content_builder(win)
            if content is not None:
                win.Content = content
        return win

    def show(self):
        _refuse_under_runner()
        existing = Modeless.get(self.key)
        if existing is not None:
            try:
                from System.Windows import WindowState
                if existing.WindowState == WindowState.Minimized:
                    existing.WindowState = WindowState.Normal
                existing.Activate()
            except Exception:
                pass
            return existing
        win = self.build()
        windows = Modeless._windows()
        key = self.key

        def closed(sender, args):
            if windows.get(key) is win:
                windows.pop(key, None)
        win.Closed += safe(closed, 'modeless closed')
        _wpf()
        from PyNavis.Runtime.Forms import FluentChrome
        from System.Windows.Forms.Integration import ElementHost
        FluentChrome.Apply(win)
        ElementHost.EnableModelessKeyboardInterop(win)
        win.Show()
        windows[key] = win
        return win


def non_activating(win):
    """Makes a window a notification: shown without taking focus, not in the
    taskbar or Alt+Tab (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, applied when its
    handle exists). Call before Show."""
    _wpf()
    from System.Windows.Interop import WindowInteropHelper
    win.ShowActivated = False
    win.ShowInTaskbar = False

    def apply_style(*args):
        handle = WindowInteropHelper(win).Handle
        if not handle or int(handle.ToInt64()) == 0:
            return
        _set_ex_style(int(handle.ToInt64()), 0x08000000 | 0x00000080)
    if int(WindowInteropHelper(win).Handle.ToInt64()) != 0:
        safe(apply_style, 'non-activating style')()
    else:
        win.SourceInitialized += safe(apply_style, 'non-activating style')
    return win


def _set_ex_style(hwnd, bits):
    import ctypes
    user32 = ctypes.windll.user32
    GWL_EXSTYLE = -20
    getter = getattr(user32, 'GetWindowLongPtrW', None) or user32.GetWindowLongW
    setter = getattr(user32, 'SetWindowLongPtrW', None) or user32.SetWindowLongW
    getter.restype = ctypes.c_ssize_t
    getter.argtypes = [ctypes.c_void_p, ctypes.c_int]
    setter.restype = ctypes.c_ssize_t
    setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    current = getter(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
    setter(ctypes.c_void_p(hwnd), GWL_EXSTYLE, current | bits)


def host_rect():
    """(left, top, right, bottom) of the Navisworks main window in SCREEN PIXELS
    (divide by the DPI scale for WPF units). Falls back to the primary screen's
    work area when there is no main window (tests, the runner)."""
    try:
        import ctypes
        from ctypes import wintypes
        from System.Diagnostics import Process
        handle = Process.GetCurrentProcess().MainWindowHandle
        hwnd = int(handle.ToInt64())
        if hwnd:
            rect = wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
                return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    _wpf()
    from System.Windows.Forms import Screen
    area = Screen.PrimaryScreen.WorkingArea
    return (area.Left, area.Top, area.Right, area.Bottom)


def dpi_scale(visual=None):
    """Device pixels per WPF unit (1.0 at 96 dpi)."""
    try:
        _wpf()
        from System.Windows.Media import VisualTreeHelper
        if visual is not None:
            return float(VisualTreeHelper.GetDpi(visual).DpiScaleX)
    except Exception:
        pass
    try:
        import ctypes
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)
        ctypes.windll.user32.ReleaseDC(0, dc)
        return dpi / 96.0 if dpi else 1.0
    except Exception:
        return 1.0


# ---- timing -------------------------------------------------------------------------


def run_later(fn, delay_ms=0):
    """Runs fn() once on the UI thread after delay_ms (a one-shot DispatcherTimer;
    exceptions logged). Returns cancel(), which stops it if it has not run."""
    _wpf()
    from System import TimeSpan
    from System.Windows.Threading import DispatcherPriority, DispatcherTimer
    timer = DispatcherTimer(DispatcherPriority.Background)
    timer.Interval = TimeSpan.FromMilliseconds(max(0, int(delay_ms)))
    call = safe(fn, getattr(fn, '__name__', 'run_later'))

    def tick(sender, args):
        timer.Stop()
        call()
    timer.Tick += tick
    timer.Start()

    def cancel():
        try:
            timer.Stop()
        except Exception:
            pass
    return cancel


class Debouncer(object):
    """Collapses bursts of calls: trigger() (re)starts a delay_ms timer and fn()
    runs once, delay_ms after the last trigger. cancel() drops a pending call;
    flush() runs it now. UI thread only."""

    def __init__(self, delay_ms, fn):
        _wpf()
        from System import TimeSpan
        from System.Windows.Threading import DispatcherPriority, DispatcherTimer
        self.fn = safe(fn, getattr(fn, '__name__', 'debounced'))
        self.timer = DispatcherTimer(DispatcherPriority.Background)
        self.timer.Interval = TimeSpan.FromMilliseconds(max(1, int(delay_ms)))
        self.pending = False
        self.timer.Tick += self._tick

    def _tick(self, sender, args):
        self.timer.Stop()
        if self.pending:
            self.pending = False
            self.fn()

    def trigger(self):
        self.pending = True
        self.timer.Stop()
        self.timer.Start()

    def cancel(self):
        self.pending = False
        self.timer.Stop()

    def flush(self):
        self.timer.Stop()
        if self.pending:
            self.pending = False
            self.fn()


# ---- shell -------------------------------------------------------------------------------


def copy(value):
    """Puts text on the clipboard. Returns False when the clipboard is busy."""
    try:
        from pynavis import script
        script.clipboard_copy(str(value))
        return True
    except Exception:
        try:
            _wpf()
            from System.Windows import Clipboard
            Clipboard.SetText(str(value))
            return True
        except Exception:
            return False


def open_path(path):
    """Opens a file or folder with its default application."""
    os.startfile(str(path))


def show_in_explorer(path):
    """Opens Explorer with the file selected (or at the folder)."""
    try:
        from pynavis import script
        script.show_in_explorer(str(path))
        return
    except Exception:
        pass
    from System.Diagnostics import Process
    target = str(path)
    if os.path.isfile(target):
        Process.Start('explorer.exe', '/select,"%s"' % target)
    else:
        Process.Start('explorer.exe', '"%s"' % target)


# Public names for the parts custom windows build on (stable; the underscored originals
# stay for existing callers).
thickness = _thickness
close_with = _close_with
load_wpf = _wpf
Bag = _Bag

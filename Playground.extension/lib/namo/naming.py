# -*- coding: utf-8 -*-
"""Name templates: '{test} - {n:000}', '{date:%Y%m%d} {project}', '{{literal braces}}'.

    text, missing = naming.render('{test} {n:000}', {'test': 'Ducts vs Pipes'}, counter=7)
    # -> ('Ducts vs Pipes 007', [])

Token syntax: {name} or {name:spec}. Names are letters, digits, '_' and '.', matched
case-insensitively when there is no exact key. spec is
  * all zeros ('000')       zero-pads a number to that width
  * a strftime pattern      for date/time values ('%Y%m%d'); text that reads as a date
                            is parsed first
  * a Python format spec    (',', '.2f', '>8') applied with format(); text that reads as
                            a number is converted first
An unknown token stays in the text exactly as written ('{token}') and is reported in
missing_tokens; '{{' and '}}' are literal braces; a lone brace is literal text.

Pure except standard_values(), which lazy-imports pynavis.doc and namo.config (and still
works without a document).
"""
import datetime
import os
import re

TOKEN = re.compile(r'\{([A-Za-z_][A-Za-z0-9_.]*)(?::([^{}]*))?\}')

DATE_FORMAT = '%Y-%m-%d'
TIME_FORMAT = '%H%M'
DATETIME_FORMAT = '%Y-%m-%d %H%M'


def _scan(template):
    """Yields ('text', str) and ('token', name, spec, raw) pieces in order."""
    template = template or ''
    i = 0
    buf = []
    length = len(template)
    while i < length:
        ch = template[i]
        if ch == '{':
            if template.startswith('{{', i):
                buf.append('{')
                i += 2
                continue
            match = TOKEN.match(template, i)
            if match:
                if buf:
                    yield ('text', ''.join(buf))
                    buf = []
                yield ('token', match.group(1), match.group(2), match.group(0))
                i = match.end()
                continue
            buf.append(ch)
            i += 1
            continue
        if ch == '}' and template.startswith('}}', i):
            buf.append('}')
            i += 2
            continue
        buf.append(ch)
        i += 1
    if buf:
        yield ('text', ''.join(buf))


def tokens(template):
    """Token names in a template, in order of first appearance, without duplicates."""
    out = []
    for piece in _scan(template):
        if piece[0] == 'token' and piece[1] not in out:
            out.append(piece[1])
    return out


def _lookup(values, name):
    if name in values:
        return True, values[name]
    lowered = name.lower()
    for key in sorted(values):
        if str(key).lower() == lowered:
            return True, values[key]
    return False, None


def _as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        text = str(value).strip().replace(',', '')
        if re.match(r'^[+-]?\d+$', text):
            return int(text)
        return float(text)
    except Exception:
        return None


def _as_date(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value
    try:
        from namo import dates
        return dates.parse(value)
    except Exception:
        return None


def format_value(value, spec=None):
    """One value as text, applying a token spec (see the module docstring)."""
    if value is None:
        return ''
    if spec:
        if set(spec) == set('0'):
            number = _as_number(value)
            if number is not None:
                return '%0*d' % (len(spec), int(round(number)))
            return str(value)
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if '%' in spec and not is_number:
            when = _as_date(value)
            if when is not None:
                try:
                    return when.strftime(spec)
                except Exception:
                    return str(value)
            return str(value)
        try:
            return format(value, spec)
        except Exception:
            number = _as_number(value)
            if number is not None:
                try:
                    return format(number, spec)
                except Exception:
                    pass
            return str(value)
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, datetime.datetime):
        return value.strftime(DATETIME_FORMAT)
    if isinstance(value, datetime.date):
        return value.strftime(DATE_FORMAT)
    if isinstance(value, datetime.time):
        return value.strftime(TIME_FORMAT)
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return str(value)


def render(template, values, counter=None):
    """(text, missing_tokens): the template with every known token replaced.

    values is a dict of token values (str, numbers, dates; None renders as ''); counter,
    when not None, fills {n} unless values already has 'n'. Unknown tokens stay as
    written and their names are listed in missing_tokens (in order, no duplicates).
    """
    values = dict(values or {})
    if counter is not None and 'n' not in values:
        values['n'] = counter
    out = []
    missing = []
    for piece in _scan(template):
        if piece[0] == 'text':
            out.append(piece[1])
            continue
        _kind, name, spec, raw = piece
        found, value = _lookup(values, name)
        if not found:
            out.append(raw)
            if name not in missing:
                missing.append(name)
            continue
        out.append(format_value(value, spec))
    return ''.join(out), missing


def standard_values(doc=None):
    """The tokens every name template may use, as a dict:

    date, time, datetime (date/time objects: '{date}' renders 2026-10-05, '{time}' 1430,
    '{date:%d %b %Y}' any strftime), year, month, day (zero-padded text), user, project,
    project_number, company (namo.config), file (the document's file name without
    extension), title (the document title). Without Navisworks or a document, file and
    title are ''.
    """
    now = datetime.datetime.now().replace(microsecond=0)
    values = {
        'date': now.date(),
        'time': now.time(),
        'datetime': now,
        'year': '%04d' % now.year,
        'month': '%02d' % now.month,
        'day': '%02d' % now.day,
        'user': '',
        'project': '',
        'project_number': '',
        'company': '',
        'file': '',
        'title': '',
    }
    try:
        from namo import config
        cfg = config.load()
        values['user'] = cfg.get('user') or ''
        values['project'] = cfg.get('project_name') or ''
        values['project_number'] = cfg.get('project_number') or ''
        values['company'] = cfg.get('company') or ''
    except Exception:
        pass
    try:
        from pynavis import doc as _doc
        d = doc if doc is not None else _doc.get_doc()
        if d is not None:
            filename = _doc.get_filename(d) or ''
            values['file'] = os.path.splitext(os.path.basename(filename))[0]
            values['title'] = _doc.get_title(d) or ''
    except Exception:
        pass
    return values


def unique(name, existing, pattern='{name} ({n})'):
    """name when no entry of existing matches it (case-insensitively), else the first free
    pattern rendering with n = 2, 3, ... ('Level 1 (2)')."""
    taken = set(str(e).strip().lower() for e in existing)
    if str(name).strip().lower() not in taken:
        return name
    for n in range(2, 100000):
        candidate = render(pattern, {'name': name}, counter=n)[0]
        if candidate.strip().lower() not in taken:
            return candidate
    raise ValueError('No free name for %r' % name)


def _dash_map():
    # Built from code points so this file carries no dash characters (house rule).
    return {chr(0x2013): '-', chr(0x2014): '-', chr(0x2212): '-', chr(0x2010): '-',
            chr(0x2011): '-', chr(0x00A0): ' ', chr(0x2009): ' ', chr(0x202F): ' '}


def sanitize(text, for_file=False):
    """Tidies a generated name: control characters and line breaks become spaces, long
    dashes become '-', runs of spaces collapse, ends are trimmed. for_file=True also
    makes it a Windows-safe file name (namo.paths.safe_filename)."""
    if text is None:
        text = ''
    text = str(text)
    dashes = _dash_map()
    chars = []
    for ch in text:
        if ch in dashes:
            chars.append(dashes[ch])
        elif ord(ch) < 32 or ord(ch) == 127:
            chars.append(' ')
        else:
            chars.append(ch)
    cleaned = ' '.join(''.join(chars).split())
    if for_file:
        from namo import paths
        return paths.safe_filename(cleaned)
    return cleaned


_DIGITS = re.compile(r'(\d+)')


def natural_key(text):
    """Sort key that orders embedded numbers by value, case-insensitively:
    'Level 2' < 'Level 10', 'RFI-9' < 'RFI-10'."""
    parts = _DIGITS.split(str(text or '').lower())
    key = []
    for i, part in enumerate(parts):
        if i % 2:
            key.append((1, int(part), part))
        else:
            key.append((0, 0, part))
    return tuple(key)

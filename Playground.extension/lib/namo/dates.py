# -*- coding: utf-8 -*-
"""Dates from anywhere (ISO text, typed dates, Excel serials, .NET DateTime) and the few
calculations reports need.

    dates.parse('2026-10-05T14:30:00')      # datetime.datetime(2026, 10, 5, 14, 30)
    dates.parse('05/10/2026')               # 5 October (day first unless impossible)
    dates.parse(45935.5)                    # Excel serial -> 2025-10-05 12:00
    dates.parse(clash_result.CreatedTime)   # .NET DateTime (anything with .Year/.Month/.Day)
    dates.days_between(created, dates.today())
    dates.age_bucket(12)                    # '8-14 days'
    dates.format(dt)                        # config date_format, default '%Y-%m-%d'

parse() returns a naive local datetime or None, never raises. Text it reads, in order:
ISO (2026-10-05, 2026/10/05, 2026-10-05 14:30, 2026-10-05T14:30:00.123Z; a time zone is
converted to local time), compact 20261005, numeric d/m/y or m/d/y (a part over 12
decides; otherwise day first, or month first with day_first=False; 2-digit years are
1970..2069), month names (5 Oct 2026, 05-Oct-2026, October 5, 2026, Mon 5 Oct 2026),
optional times with seconds and am/pm, and number-only text in 20000..80000 as an Excel
serial (1954..2119).

Pure stdlib except from_net/to_net, which lazy-import System.
"""
import calendar
import datetime
import re

EXCEL_EPOCH = datetime.datetime(1899, 12, 30)
DEFAULT_FORMAT = '%Y-%m-%d'

MONTHS = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3, 'apr': 4,
    'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7, 'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9, 'oct': 10, 'october': 10, 'nov': 11,
    'november': 11, 'dec': 12, 'december': 12,
}
_WEEKDAYS = r'(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\.?,?\s+'

_TIME = (r'(?:(?:[T\s]+|\s*,\s*)(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d{1,6})\d*)?)?'
         r'\s*([ap])?\.?(?:m\.?)?)?\s*(z|utc|gmt|[+-]\d{2}:?\d{2})?')
_RE_ISO = re.compile(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})' + _TIME + '$', re.IGNORECASE)
_RE_COMPACT = re.compile(r'^(\d{4})(\d{2})(\d{2})(?:t?(\d{2})(\d{2})(\d{2})?)?$', re.IGNORECASE)
_RE_NUMERIC = re.compile(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})' + _TIME + '$', re.IGNORECASE)
_RE_DAY_MONTH = re.compile(r'^(\d{1,2})(?:st|nd|rd|th)?[\s\-/.]+([a-z]+)\.?[\s\-/.,]+(\d{4}|\d{2})'
                           + _TIME + '$', re.IGNORECASE)
_RE_MONTH_DAY = re.compile(r'^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})' + _TIME + '$',
                           re.IGNORECASE)
_RE_NUMBER = re.compile(r'^\d{5}(?:\.\d+)?$')


def _year(text):
    year = int(text)
    if len(text) == 2:
        year += 2000 if year < 70 else 1900
    return year


def _to_local(naive_utc):
    try:
        stamp = calendar.timegm(naive_utc.timetuple())
        return datetime.datetime.fromtimestamp(stamp).replace(microsecond=naive_utc.microsecond)
    except Exception:
        return naive_utc


def _build(year, month, day, groups):
    """datetime from date parts plus the 6 _TIME groups, or None when invalid."""
    hour, minute, second, fraction, ampm, zone = groups
    try:
        h = int(hour) if hour else 0
        if ampm:
            ampm = ampm.lower()
            if h > 12 or h == 0:
                return None
            if ampm == 'p' and h != 12:
                h += 12
            elif ampm == 'a' and h == 12:
                h = 0
        micro = int((fraction or '0').ljust(6, '0')[:6])
        value = datetime.datetime(int(year), int(month), int(day), h,
                                  int(minute) if minute else 0, int(second) if second else 0, micro)
    except (ValueError, OverflowError):
        return None
    if zone:
        zone = zone.lower()
        if zone in ('z', 'utc', 'gmt'):
            offset = 0
        else:
            digits = zone[1:].replace(':', '')
            offset = int(digits[:2]) * 60 + int(digits[2:])
            if zone[0] == '-':
                offset = -offset
        value = _to_local(value - datetime.timedelta(minutes=offset))
    return value


def from_excel(serial):
    """The datetime of an Excel serial number (days since 1899-12-30), or None outside
    1..2958465 (year 9999)."""
    try:
        serial = float(serial)
    except (TypeError, ValueError):
        return None
    if not 1 <= serial < 2958466:
        return None
    return (EXCEL_EPOCH + datetime.timedelta(days=serial)).replace(microsecond=0)


def to_excel(value):
    """The Excel serial (float) of a date/datetime/parseable value, or None."""
    dt = parse(value)
    if dt is None:
        return None
    delta = dt - EXCEL_EPOCH
    return delta.days + delta.seconds / 86400.0


def _parse_text(text, day_first):
    t = text.strip()
    t = re.sub(r'^' + _WEEKDAYS, '', t, flags=re.IGNORECASE)
    m = _RE_ISO.match(t)
    if m:
        return _build(m.group(1), m.group(2), m.group(3), m.groups()[3:9])
    m = _RE_COMPACT.match(t)
    if m:
        try:
            return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                     int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0))
        except ValueError:
            return None
    m = _RE_NUMERIC.match(t)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        if a > 12:
            day, month = a, b
        elif b > 12:
            month, day = a, b
        elif day_first:
            day, month = a, b
        else:
            month, day = a, b
        return _build(year, month, day, m.groups()[3:9])
    m = _RE_DAY_MONTH.match(t)
    if m and m.group(2).lower() in MONTHS:
        return _build(_year(m.group(3)), MONTHS[m.group(2).lower()], m.group(1), m.groups()[3:9])
    m = _RE_MONTH_DAY.match(t)
    if m and m.group(1).lower() in MONTHS:
        return _build(m.group(3), MONTHS[m.group(1).lower()], m.group(2), m.groups()[3:9])
    if _RE_NUMBER.match(t):
        number = float(t)
        if 20000 <= number <= 80000:
            return from_excel(number)
    return None


def parse(value, day_first=True):
    """A naive local datetime.datetime from value, or None (never raises). See the module
    docstring for what reads."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)):
        return from_excel(value)
    if hasattr(value, 'Year') and hasattr(value, 'Month') and hasattr(value, 'Day'):
        return from_net(value)
    try:
        text = str(value)
    except Exception:
        return None
    if not text.strip():
        return None
    try:
        return _parse_text(text, day_first)
    except Exception:
        return None


def iso(value, date_only=False):
    """'YYYY-MM-DDTHH:MM:SS' (or 'YYYY-MM-DD' with date_only, or for a datetime.date);
    '' when value does not parse."""
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value.strftime('%Y-%m-%d')
    dt = parse(value)
    if dt is None:
        return ''
    if date_only:
        return '%04d-%02d-%02d' % (dt.year, dt.month, dt.day)
    return '%04d-%02d-%02dT%02d:%02d:%02d' % (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def now():
    """The current local datetime, to the second."""
    return datetime.datetime.now().replace(microsecond=0)


def today():
    """Today at 00:00 (a datetime, like everything parse returns)."""
    d = datetime.date.today()
    return datetime.datetime(d.year, d.month, d.day)


def add_days(value, n):
    """value + n days (datetime), or None when value does not parse."""
    dt = parse(value)
    if dt is None:
        return None
    return dt + datetime.timedelta(days=n)


def days_between(a, b):
    """Whole calendar days from a to b (b later gives a positive number; times of day are
    ignored), or None when either does not parse."""
    da, db = parse(a), parse(b)
    if da is None or db is None:
        return None
    return (db.date() - da.date()).days


def bucket_labels(buckets=(7, 14, 30)):
    """The labels age_bucket can return, in order: '0-7 days', '8-14 days', '15-30 days',
    'Over 30 days'."""
    labels = []
    low = 0
    for edge in buckets:
        labels.append('%d-%d days' % (low, edge))
        low = edge + 1
    labels.append('Over %d days' % buckets[-1])
    return labels


def age_bucket(days, buckets=(7, 14, 30)):
    """The age band for a number of days (see bucket_labels); negative ages fall in the
    first band, None gives 'Unknown'."""
    if days is None:
        return 'Unknown'
    labels = bucket_labels(buckets)
    for index, edge in enumerate(buckets):
        if days <= edge:
            return labels[index]
    return labels[-1]


def _config_format():
    try:
        from namo import config
        return config.get('date_format') or DEFAULT_FORMAT
    except Exception:
        return DEFAULT_FORMAT


def format(value, fmt=None):  # noqa: A001 (contract name)
    """value as text with fmt (default: config date_format, '%Y-%m-%d'); '' when value does
    not parse."""
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        dt = datetime.datetime(value.year, value.month, value.day)
    else:
        dt = parse(value)
    if dt is None:
        return ''
    try:
        return dt.strftime(fmt or _config_format())
    except Exception:
        return iso(dt, date_only=True)


def week_start(value):
    """Monday 00:00 of value's week, or None."""
    dt = parse(value)
    if dt is None:
        return None
    monday = dt.date() - datetime.timedelta(days=dt.weekday())
    return datetime.datetime(monday.year, monday.month, monday.day)


def from_net(net):
    """A .NET DateTime (or anything with Year/Month/Day/Hour/Minute/Second/Millisecond) as
    a naive local datetime. UTC values are converted to local time; DateTime.MinValue
    (year 1, Navisworks' "no date") and None give None."""
    if net is None:
        return None
    try:
        if str(getattr(net, 'Kind', '')) == 'Utc':
            net = net.ToLocalTime()
        if int(net.Year) <= 1:
            return None
        return datetime.datetime(int(net.Year), int(net.Month), int(net.Day),
                                 int(getattr(net, 'Hour', 0)), int(getattr(net, 'Minute', 0)),
                                 int(getattr(net, 'Second', 0)),
                                 int(getattr(net, 'Millisecond', 0)) * 1000)
    except Exception:
        return None


def to_net(value):
    """A System.DateTime (local kind) for a date/datetime/parseable value, or None."""
    dt = parse(value)
    if dt is None:
        return None
    from System import DateTime, DateTimeKind
    return DateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second,
                    dt.microsecond // 1000, DateTimeKind.Local)

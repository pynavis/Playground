# -*- coding: utf-8 -*-
"""namo.dates: parsing from every source, buckets, formatting."""
import datetime

import _compat

from namo import dates

D = datetime.datetime


def test_parse_iso_forms():
    assert dates.parse('2026-10-05') == D(2026, 10, 5)
    assert dates.parse('2026/10/05') == D(2026, 10, 5)
    assert dates.parse('2026.10.05') == D(2026, 10, 5)
    assert dates.parse('2026-10-05T14:30:00') == D(2026, 10, 5, 14, 30)
    assert dates.parse('2026-10-05 14:30') == D(2026, 10, 5, 14, 30)
    assert dates.parse('2026-10-05T14:30:15.250') == D(2026, 10, 5, 14, 30, 15, 250000)
    assert dates.parse('  2026-1-5  ') == D(2026, 1, 5)
    assert dates.parse('20261005') == D(2026, 10, 5)
    assert dates.parse('20261005T143000') == D(2026, 10, 5, 14, 30)


def test_parse_time_zones_become_local():
    utc = dates.parse('2026-10-05T12:00:00Z')
    plus = dates.parse('2026-10-05T14:00:00+02:00')
    assert utc is not None and utc == plus
    # The same instant written three ways must land on the same local time.
    assert dates.parse('2026-10-05T07:00:00-05:00') == utc


def test_parse_day_month_order():
    assert dates.parse('05/10/2026') == D(2026, 10, 5)              # day first by default
    assert dates.parse('05/10/2026', day_first=False) == D(2026, 5, 10)
    assert dates.parse('25/10/2026') == D(2026, 10, 25)             # 25 cannot be a month
    assert dates.parse('10/25/2026') == D(2026, 10, 25)             # nor here
    assert dates.parse('5.10.26') == D(2026, 10, 5)
    assert dates.parse('05-10-1999 18:45') == D(1999, 10, 5, 18, 45)
    assert dates.parse('31/02/2026') is None                         # no such day


def test_parse_month_names_and_am_pm():
    assert dates.parse('5 Oct 2026') == D(2026, 10, 5)
    assert dates.parse('05-Oct-2026') == D(2026, 10, 5)
    assert dates.parse('5 October 2026 14:30') == D(2026, 10, 5, 14, 30)
    assert dates.parse('October 5, 2026') == D(2026, 10, 5)
    assert dates.parse('Oct 5, 2026 2:30 pm') == D(2026, 10, 5, 14, 30)
    assert dates.parse('Mon, 5 Oct 2026') == D(2026, 10, 5)
    assert dates.parse('12 Sept 2026 12:15 AM') == D(2026, 9, 12, 0, 15)
    assert dates.parse('5 Foo 2026') is None


def test_parse_numbers_objects_and_rubbish():
    assert dates.parse(45935.5) == D(2025, 10, 5, 12, 0)
    assert dates.parse(45935) == D(2025, 10, 5)
    assert dates.parse('45935') == D(2025, 10, 5)
    assert dates.parse(datetime.date(2026, 10, 5)) == D(2026, 10, 5)
    stamp = D(2026, 10, 5, 1, 2, 3)
    assert dates.parse(stamp) is stamp
    for bad in (None, '', '   ', 'soon', True, 0, -5, '12345678901', '2026-13-01', object()):
        assert dates.parse(bad) is None, bad


class FakeNet(object):
    """Duck-typed .NET DateTime."""

    def __init__(self, *parts, **kw):
        y, m, d, hh, mm, ss, ms = (list(parts) + [0] * 7)[:7]
        self.Year, self.Month, self.Day = y, m, d
        self.Hour, self.Minute, self.Second, self.Millisecond = hh, mm, ss, ms
        self.Kind = kw.get('kind', 'Local')


def test_from_net_and_parse_of_net_values():
    assert dates.from_net(FakeNet(2026, 10, 5, 14, 30, 5, 250)) == D(2026, 10, 5, 14, 30, 5, 250000)
    assert dates.parse(FakeNet(2026, 10, 5)) == D(2026, 10, 5)
    assert dates.from_net(FakeNet(1, 1, 1)) is None                 # DateTime.MinValue: no date
    assert dates.from_net(None) is None


def test_to_net_needs_dotnet():
    if not _compat.IRONPYTHON:
        raise _compat.SkipTest('System.DateTime needs IronPython')
    net = dates.to_net('2026-10-05T14:30:05')
    assert (net.Year, net.Month, net.Day, net.Hour, net.Minute, net.Second) == (2026, 10, 5, 14, 30, 5)
    assert dates.from_net(net) == D(2026, 10, 5, 14, 30, 5)
    assert dates.to_net('nonsense') is None


def test_excel_round_trip():
    assert dates.to_excel(D(2025, 10, 5, 12, 0)) == 45935.5
    assert dates.from_excel(dates.to_excel('2026-03-01')) == D(2026, 3, 1)
    assert dates.from_excel(0) is None
    assert dates.to_excel('nope') is None


def test_iso_and_format():
    assert dates.iso(D(2026, 10, 5, 14, 30, 1, 999)) == '2026-10-05T14:30:01'
    assert dates.iso('2026-10-05') == '2026-10-05T00:00:00'
    assert dates.iso('2026-10-05 14:30', date_only=True) == '2026-10-05'
    assert dates.iso(datetime.date(2026, 10, 5)) == '2026-10-05'
    assert dates.iso('nope') == ''
    assert dates.format('2026-10-05', '%d %b %Y') == '05 Oct 2026'
    assert dates.format(datetime.date(2026, 10, 5), '%Y%m%d') == '20261005'
    assert dates.format(None) == ''


def test_format_uses_config_date_format():
    from namo import config, paths
    folder = _compat.tmpdir('f2-dates-config')
    previous = paths.redirect(folder)
    try:
        assert dates.format('2026-10-05') == '2026-10-05'
        config.save({'date_format': '%d/%m/%Y'})
        assert dates.format('2026-10-05') == '05/10/2026'
    finally:
        paths.redirect(previous)


def test_today_now_add_days_between():
    today = dates.today()
    assert (today.hour, today.minute, today.second) == (0, 0, 0)
    assert dates.now().microsecond == 0
    assert dates.add_days('2026-02-27', 2) == D(2026, 3, 1)
    assert dates.add_days('x', 2) is None
    assert dates.days_between('2026-10-01 23:59', '2026-10-02 00:01') == 1
    assert dates.days_between('2026-10-05', '2026-10-01') == -4
    assert dates.days_between('2026-10-05', None) is None


def test_age_buckets():
    assert dates.bucket_labels() == ['0-7 days', '8-14 days', '15-30 days', 'Over 30 days']
    assert dates.age_bucket(0) == '0-7 days'
    assert dates.age_bucket(7) == '0-7 days'
    assert dates.age_bucket(8) == '8-14 days'
    assert dates.age_bucket(14) == '8-14 days'
    assert dates.age_bucket(15) == '15-30 days'
    assert dates.age_bucket(30) == '15-30 days'
    assert dates.age_bucket(31) == 'Over 30 days'
    assert dates.age_bucket(-3) == '0-7 days'
    assert dates.age_bucket(None) == 'Unknown'
    assert dates.age_bucket(5, buckets=(1, 3)) == 'Over 3 days'
    for label in dates.bucket_labels():
        assert chr(0x2013) not in label and chr(0x2014) not in label


def test_week_start():
    assert dates.week_start('2026-10-08 13:00') == D(2026, 10, 5)     # a Thursday -> Monday
    assert dates.week_start('nope') is None

# -*- coding: utf-8 -*-
"""namo.usage: CSV lines, settings, the hook path into temp files, aggregation."""
import datetime
import io
import os

import _compat

from namo import paths, session, usage


def test_csv_line_and_parse_roundtrip():
    line = usage.csv_line(['2026-10-05T10:00:00', 'Amy, B', 'PC1', 'Playground', 'A.tab/B.panel/C.pushbutton',
                           'Say "hi"', 1200])
    assert line == '2026-10-05T10:00:00,"Amy, B",PC1,Playground,A.tab/B.panel/C.pushbutton,"Say ""hi""",1200\r\n'
    text = usage.csv_line(usage.FIELDS) + line + 'broken\r\n' + usage.csv_line(['t', 'u', 'm', 'e', '', 'x', 1])
    rows = usage.parse_csv(text)
    assert len(rows) == 1
    assert rows[0]['user'] == 'Amy, B' and rows[0]['title'] == 'Say "hi"' and rows[0]['ms'] == 1200
    assert usage.parse_csv('') == []


def test_file_names():
    when = datetime.datetime(2026, 10, 5, 9, 30)
    assert usage.file_for('C:\\u', when) == os.path.join('C:\\u', 'usage-2026-10.csv')
    assert usage.file_for('C:\\u', when, 'amy:b', shared=True) == os.path.join('C:\\u', 'amy_b 2026-10.csv')


def test_hook_writes_only_when_enabled():
    folder = _compat.tmpdir('usage_hook')
    previous = paths.redirect(folder)
    session.clear(usage.HOLDER)
    try:
        key = 'Dev.tab/Tools.panel/Unit_Converter.pushbutton'
        usage.before(key)
        assert usage.after(key) is None                       # opted out: nothing written
        assert not os.path.exists(os.path.join(folder, 'pyNavis', 'playground', 'usage', 'usage-%s.csv'
                                               % datetime.date.today().strftime('%Y-%m')))
        saved = usage.save_settings({'enabled': True, 'asked': True})
        assert saved == {'enabled': True, 'asked': True, 'shared': False}
        assert usage.load_settings() == saved
        usage.before(key)
        holder = session.holder(usage.HOLDER)
        holder.started[key.lower()] -= 1.5
        path = usage.after(key)
        assert path.endswith('.csv')
        with io.open(path, encoding='utf-8') as handle:
            rows = usage.parse_csv(handle.read())
        assert len(rows) == 1
        assert rows[0]['key'] == key and 1400 <= rows[0]['ms'] <= 3000
        usage.after(key)                                      # no before: duration 0
        rows = usage.read_rows([os.path.dirname(path)])
        assert [r['ms'] for r in rows][1] == 0
    finally:
        session.clear(usage.HOLDER)
        paths.redirect(previous)


def _row(day, key, user='amy', ms=1000, title=None):
    return {'time': '%sT10:00:00' % day, 'user': user, 'machine': 'PC', 'extension': 'Playground',
            'key': key, 'title': title or key.split('/')[-1], 'ms': ms}


def test_aggregate():
    rows = [_row('2026-10-01', 'A', ms=1000), _row('2026-10-01', 'A', 'bob', ms=3000),
            _row('2026-10-03', 'B', ms=500), _row('2026-10-03', 'a', ms=2000)]
    commands = [{'key': 'A', 'title': 'Alpha', 'path': 'T > P'}, {'key': 'C', 'title': 'Charlie', 'path': 'T > P'},
                {'key': 'D', 'title': 'Delta', 'path': 'T > P', 'hidden': True},
                {'key': 'B', 'title': 'Bravo', 'path': 'T > P'}]
    summary = usage.aggregate(rows, commands, days=5)
    assert (summary['runs'], summary['tools'], summary['users']) == (4, 2, 2)
    assert (summary['first'], summary['last']) == ('2026-10-01', '2026-10-03')
    top = summary['by_tool'][0]
    assert top['key'] == 'A' and top['runs'] == 3 and top['users'] == 2
    assert top['seconds'] == 6.0 and top['median_s'] == 2.0
    assert summary['by_day'] == [('2026-09-29', 0), ('2026-09-30', 0), ('2026-10-01', 2),
                                 ('2026-10-02', 0), ('2026-10-03', 2)]
    assert summary['by_user'] == [('amy', 3, 2), ('bob', 1, 1)]
    assert [c['title'] for c in summary['never']] == ['Charlie']
    sheets = usage.xlsx_sheets(summary)
    assert [s['name'] for s in sheets] == ['Tools', 'Per day', 'Per user', 'Never used']
    assert sheets[0]['rows'][0][:5] == ['A', 'Playground', 'A', 3, 2]
    empty = usage.aggregate([], [], days=2, today='2026-10-05')
    assert empty['by_day'] == [('2026-10-04', 0), ('2026-10-05', 0)] and empty['first'] == ''


def test_xlsx_export_opens():
    _compat.require_cpython('openpyxl')
    import openpyxl
    from namo import xlsx
    folder = _compat.tmpdir('usage_xlsx')
    summary = usage.aggregate([_row('2026-10-01', 'A')], [{'key': 'B', 'title': 'Bravo', 'path': 'x'}], days=2)
    path = xlsx.write_simple(os.path.join(folder, 'usage.xlsx'), usage.xlsx_sheets(summary))
    book = openpyxl.load_workbook(path)
    assert book.sheetnames == ['Tools', 'Per day', 'Per user', 'Never used']
    assert book['Never used']['A2'].value == 'Bravo'


def _event(values):
    """pyNavis' __event__: a .NET Dictionary[str, object] under IronPython (no .get()),
    a stand-in with only 'in' and [] under CPython."""
    if _compat.IRONPYTHON:
        from System import Object, String
        from System.Collections.Generic import Dictionary
        event = Dictionary[String, Object]()
        for key in values:
            event[key] = values[key]
        return event

    class NetDictionary(object):
        def __init__(self, items):
            self._items = dict(items)

        def __contains__(self, key):
            return key in self._items

        def __getitem__(self, key):
            return self._items[key]
    return NetDictionary(values)


def test_hk_usage_records_from_the_net_event_dictionary():
    from namo import hk_usage
    folder = _compat.tmpdir('usage_hk_event')
    previous = paths.redirect(folder)
    session.clear(usage.HOLDER)
    try:
        key = 'Dev.tab/Tools.panel/Unit_Converter.pushbutton'
        assert hk_usage.command_of(_event({'name': 'after-command', 'command': key})) == key
        assert hk_usage.command_of(_event({'name': 'doc-opened'})) is None
        usage.save_settings({'enabled': True, 'asked': True})
        hk_usage.handle('before-command', _event({'name': 'before-command', 'command': key, 'viewpoint': None}))
        hk_usage.handle('after-command', _event({'name': 'after-command', 'command': key, 'viewpoint': None}))
        rows = usage.read_rows([os.path.join(folder, 'pyNavis', 'playground', 'usage')])
        assert [r['key'] for r in rows] == [key]
    finally:
        session.clear(usage.HOLDER)
        paths.redirect(previous)

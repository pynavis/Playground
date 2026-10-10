# -*- coding: utf-8 -*-
"""namo.naming: templates, tokens, standard values, unique names, sanitising."""
import datetime

import _compat
from _compat import raises

from namo import naming


def test_render_basic_tokens_and_counter():
    text, missing = naming.render('{test} - {n:000}', {'test': 'Ducts vs Pipes'}, counter=7)
    assert text == 'Ducts vs Pipes - 007' and missing == []
    assert naming.render('{n}', {}, counter=12) == ('12', [])
    assert naming.render('{n:00}', {'n': 3}, counter=9) == ('03', [])     # values win over counter
    assert naming.render('{value}', {'value': 2.0}) == ('2', [])
    assert naming.render('{value}', {'value': None}) == ('', [])
    assert naming.render('{flag}', {'flag': True}) == ('Yes', [])


def test_render_unknown_tokens_are_kept_and_reported():
    text, missing = naming.render('{a} {b:%Y} {a} {c}', {'c': 'C'})
    assert text == '{a} {b:%Y} {a} C'
    assert missing == ['a', 'b']
    assert naming.render('{n}', {}) == ('{n}', ['n'])             # no counter given


def test_render_escapes_and_lone_braces():
    assert naming.render('{{literal}} {x}', {'x': 1}) == ('{literal} 1', [])
    assert naming.render('a { b } c', {}) == ('a { b } c', [])
    assert naming.render('}}{{', {}) == ('}{', [])
    assert naming.render('{1abc}', {}) == ('{1abc}', [])          # not a token name
    assert naming.render('', {}) == ('', [])
    assert naming.render(None, {}) == ('', [])


def test_render_dates_and_specs():
    when = datetime.datetime(2026, 10, 5, 14, 30)
    values = {'date': when.date(), 'time': when.time(), 'datetime': when, 'text_date': '2026-10-05'}
    assert naming.render('{date}', values)[0] == '2026-10-05'
    assert naming.render('{date:%Y%m%d}', values)[0] == '20261005'
    assert naming.render('{time}', values)[0] == '1430'
    assert naming.render('{time:%H:%M}', values)[0] == '14:30'
    assert naming.render('{datetime}', values)[0] == '2026-10-05 1430'
    assert naming.render('{text_date:%d.%m.%Y}', values)[0] == '05.10.2026'
    assert naming.render('{x:,}', {'x': 1234567})[0] == '1,234,567'
    assert naming.render('{x:.1f}', {'x': '2.345'})[0] == '2.3'
    assert naming.render('{x:.0%}', {'x': 0.5})[0] == '50%'
    assert naming.render('{x:>5}', {'x': 'ab'})[0] == '   ab'
    assert naming.render('{x:zz}', {'x': 'ab'})[0] == 'ab'           # bad spec: plain text


def test_render_case_insensitive_lookup():
    assert naming.render('{Test}', {'test': 'A'}) == ('A', [])
    assert naming.render('{test}', {'Test': 'B'}) == ('B', [])


def test_tokens():
    assert naming.tokens('{a} {b:000} {{c}} {a} {d.e}') == ['a', 'b', 'd.e']
    assert naming.tokens('') == []


def test_standard_values_without_navisworks():
    from namo import config, paths
    folder = _compat.tmpdir('f2-naming-standard')
    previous = paths.redirect(folder)
    try:
        config.save({'project_name': 'Tower', 'project_number': 'P-42', 'company': 'Acme',
                     'user': 'Pat'})
        values = naming.standard_values()
    finally:
        paths.redirect(previous)
    for key in ('date', 'time', 'datetime', 'user', 'project', 'project_number', 'company',
                'file', 'title', 'year', 'month', 'day'):
        assert key in values, key
    assert values['project'] == 'Tower' and values['project_number'] == 'P-42'
    assert values['company'] == 'Acme' and values['user'] == 'Pat'
    assert values['file'] == '' and values['title'] == ''
    assert len(values['year']) == 4 and len(values['month']) == 2 and len(values['day']) == 2
    text, missing = naming.render('{project} {date:%Y}', values)
    assert missing == [] and text.startswith('Tower ')


def test_unique():
    assert naming.unique('Level 1', ['Level 2']) == 'Level 1'
    assert naming.unique('Level 1', ['level 1']) == 'Level 1 (2)'
    assert naming.unique('A', ['A', 'A (2)', 'a (3)']) == 'A (4)'
    assert naming.unique('A', ['A'], pattern='{name}_{n:00}') == 'A_02'


def test_sanitize():
    dash = chr(0x2014)
    assert naming.sanitize('  Clash\tgroup\n one ') == 'Clash group one'
    assert naming.sanitize('A ' + dash + ' B') == 'A - B'
    assert naming.sanitize(None) == ''
    assert naming.sanitize('Report: 1/2?', for_file=True) == 'Report_ 1_2_'
    assert naming.sanitize('CON', for_file=True) == '_CON'


def test_natural_key():
    names = ['Level 10', 'level 2', 'Level 1', 'RFI-10', 'RFI-9', 'B']
    assert sorted(names, key=naming.natural_key) == ['B', 'Level 1', 'level 2', 'Level 10',
                                                     'RFI-9', 'RFI-10']
    assert naming.natural_key(None) == naming.natural_key('')


def test_format_value_edges():
    assert naming.format_value(7, '000') == '007'
    assert naming.format_value('7', '000') == '007'
    assert naming.format_value('x', '000') == 'x'
    assert naming.format_value(None) == ''
    raises(TypeError, naming.render, '{a}', 5)

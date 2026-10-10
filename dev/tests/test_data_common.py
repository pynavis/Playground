# -*- coding: utf-8 -*-
"""namo.data_common pure half: progress stages, default names, scope fields."""
import _compat  # noqa: F401  (puts lib on sys.path)
from namo import data_common


def test_stage_maps_ticks_into_a_slice():
    calls = []

    def progress(fraction, label):
        calls.append((round(fraction, 3), label))
        return True
    tick = data_common.stage(progress, 0.2, 0.5, 'Reading %s')
    assert tick(50, 100) is True
    assert tick(7, None) is True
    assert calls == [(0.45, 'Reading 50 of 100'), (0.2, 'Reading 7')]
    plain = data_common.stage(progress, 0.0, 1.0, 'Working')
    plain(1, 2)
    assert calls[-1] == (0.5, 'Working')
    assert data_common.stage(None, 0, 1, 'x')(1, 2) is True
    assert data_common.report(None, 0.5, 'x') is True


def test_stage_passes_a_cancel_through():
    tick = data_common.stage(lambda f, l: False, 0, 1, 'x')
    assert tick(1, 2) is False


def test_default_name():
    values = {'file': 'Tower', 'date': '2026-10-05'}
    assert data_common.default_name('{file} - Properties - {date}', values, 'xlsx') == \
        'Tower - Properties - 2026-10-05.xlsx'
    assert data_common.default_name('{file} - Properties - {date}', {'file': '', 'date': 'd'}, '.csv') == \
        'Properties - d.csv'
    assert data_common.default_name('{file}', {'file': 'a:b'}, 'xlsx') == 'a_b.xlsx'
    assert data_common.default_name('{file}', {'file': ''}, 'xlsx') == 'untitled.xlsx'


def test_scope_fields_and_texts():
    fields = data_common.scope_fields(False, 'selection', 'geometry', budget=1000)
    assert [f['key'] for f in fields] == ['scope', 'level', 'budget']
    assert fields[0]['default'] == 'model'
    assert [v for _l, v in fields[0]['options']] == ['visible', 'model']
    assert fields[1]['default'] == 'geometry'
    assert fields[2]['default'] == 1000
    assert len(data_common.scope_fields(True, levels=False)) == 1
    assert data_common.nothing_text('selection')[0] == 'Nothing selected'
    assert data_common.nothing_text('visible')[0] == 'Nothing visible'
    assert data_common.nothing_text('model')[0] == 'No geometry in the model'

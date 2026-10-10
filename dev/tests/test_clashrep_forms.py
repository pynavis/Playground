# -*- coding: utf-8 -*-
"""clashrep_forms: every Clash Reports question is a valid namo.ui form (pure checks; the
WPF build is smoke_clashrep_forms), plus the thumbnail choices and the status rule."""
import _compat  # noqa: F401

from namo import clashrep_forms as cf
from namo import clashreport as cr
from namo import ui


def all_forms(folder=None):
    import os
    folder = folder or os.path.join('C:' + os.sep, 'Temp')
    path = os.path.join(folder, 'Report.xlsx')
    values = {'statuses': ['New'], 'images': False, 'open': True, 'axis': 'model', 'xlsx': True, 'select': True,
              'series': 'per_test', 'current': False, 'csv': True, 'html': True, 'subfolder': False,
              'auto_on_save': True, 'min_hours': 6.0, 'max_results': 20000, 'tests': ['B', 'Gone']}
    return [
        ('Clash Excel Report', cf.excel_fields(values, path)),
        ('Clash Dashboard', cf.dashboard_fields(values, path.replace('.xlsx', '.html'))),
        ('Clash Count Matrix', cf.matrix_fields(values, path)),
        ('Clash Delta', cf.delta_fields(values, [('Meeting 4, 2026-10-04 17:30: 3 tests', 'h2'),
                                                 ('2026-10-01 08:00: 3 tests', 'h1')], 'h2', path)),
        ('Clash Trends', cf.trends_fields(values, path)),
        ('Per-Trade Reports', cf.per_trade_fields(values, folder, ['Structure', 'Mechanical'])),
        ('Clash snapshots', cf.snapshot_settings_fields(values, ['A', 'B'], 'local')),
        ('Clash snapshots', cf.snapshot_settings_fields(dict(), [], 'model')),
    ]


def test_every_form_is_valid():
    for title, fields in all_forms():
        specs = ui.normalize_fields(fields)
        keys = [f['key'] for f in specs if f.get('key')]
        assert len(keys) == len(set(keys)), title
        for field in specs:
            for text in (field.get('label') or '', field.get('text') or '', field.get('hint') or ''):
                assert u'\u2014' not in text and u'\u2013' not in text
                assert not text or not text[0].isalpha() or text[0].isupper(), (title, text)


def test_defaults_follow_saved_values():
    values = {'statuses': ['Resolved', 'New'], 'images': False, 'xlsx': True, 'csv': False}
    fields = dict((f['key'], f) for f in cf.excel_fields(values, 'x.xlsx') if f.get('key'))
    assert fields['statuses']['default'] == ['New', 'Resolved'] and fields['images']['default'] is False
    assert dict((f['key'], f) for f in cf.excel_fields({}, 'x'))['statuses']['default'] == cr.OPEN
    trends = dict((f['key'], f) for f in cf.trends_fields(values, 'x.xlsx') if f.get('key'))
    assert trends['export']['default'] == 'xlsx' and trends['path']['enabled_if'] == ('export', ['xlsx', 'csv', 'both'])
    assert cf.export_of({'xlsx': True, 'csv': True}) == 'both' and cf.export_of({}) == 'none'
    assert cf.export_of({'csv': True}) == 'csv'
    snap = dict((f['key'], f) for f in cf.snapshot_settings_fields({'tests': ['B', 'Gone']}, ['A', 'B'], 'local')
                if f.get('key'))
    assert snap['tests']['default'] == ['B'] and snap['min_hours']['default'] == 4.0


def test_status_rule_and_image_choices():
    assert cf.need_status({'statuses': []}) == {'statuses': 'Tick at least one status.'}
    assert cf.need_status({'statuses': ['New']}) is None and cf.need_status({}) is None
    choices = cf.image_choices({'A': 500, 'B': 20}, 300)
    assert [v for _l, v in choices] == [cf.IMAGES_CAPPED, cf.IMAGES_ALL, cf.IMAGES_NONE]
    assert choices[0][0] == 'Thumbnails for the first 300 clashes of each test (320 images)'
    assert choices[1][0] == 'Thumbnails for every listed clash (520 images)'

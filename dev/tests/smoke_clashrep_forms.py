# -*- coding: utf-8 -*-
"""Every Clash Reports question built as a real namo.ui form under IronPython + WPF (never
shown): the field lists parse, enable rules wire up and the defaults read back."""
import os

import _compat

_compat.require_ironpython()

from namo import clashrep_forms as cf  # noqa: E402
from namo import ui  # noqa: E402

import test_clashrep_forms as forms  # noqa: E402


def test_every_form_builds_and_reads_back():
    folder = _compat.tmpdir('smoke-clashrep-forms')
    for title, fields in forms.all_forms(folder):
        win = ui.build_form(title, fields, units='Millimeters', validate=cf.need_status)
        values, errors = win.Tag.collect()
        assert isinstance(values, dict), title
        for field in fields:
            key = field.get('key')
            if key and field['kind'] in ('check', 'radio', 'choice', 'multi'):
                assert key in values, (title, key)
        if title == 'Clash Excel Report':
            assert values['statuses'] == ['New'] and values['open'] is True
            assert not errors
        if title == 'Clash Delta':
            assert values['baseline'] == 'h2' and values['select'] is True
        if title == 'Clash Trends':
            assert values['export'] == 'both' and values['series'] == 'per_test'
        win.Close()


def test_empty_status_list_is_refused():
    win = ui.build_form('Clash Excel Report', cf.excel_fields({'statuses': ['New']}, os.path.join(_compat.tmpdir('smoke-clashrep-forms-2'), 'x.xlsx')),
                        validate=cf.need_status)
    state = win.Tag
    state.set_raw('statuses', [])
    values, errors = state.collect()
    assert errors and not state.accept()
    win.Close()

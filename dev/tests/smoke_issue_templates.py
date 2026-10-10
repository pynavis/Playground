# -*- coding: utf-8 -*-
"""Issue Templates under IronPython + WPF: the template manager table and the edit form
built with the shipped defaults, the form collected and validated, rendered off screen to
a PNG in the test's temp folder."""
import _compat

_compat.require_ironpython()

import os  # noqa: E402

import smoke_issueui as pane_smoke  # noqa: E402

from namo import issue_templates, paths, png, ui  # noqa: E402



def test_manager_and_edit_form():
    folder = _compat.tmpdir('smoke-templates')
    previous = paths.redirect(folder)
    try:
        win = issue_templates.build_editor_window()
        state = win.Tag
        assert state.table.total() == 6
        form = ui.build_form('Edit RFI', issue_templates.form_fields(issue_templates.default('RFI'),
                                                                     ['Mechanical', 'Structure']),
                             ok='Save', width=520)
        values, errors = form.Tag.collect()
        assert errors == {} or not errors
        assert values['type'] == 'RFI' and values['prefix'] == 'RFI-' and values['due_days'] == 7
        assert issue_templates.validate(values, [t for t in issue_templates.load()
                                                 if t['type'] != 'RFI']) == []
        form.Tag.set_raw('type', 'Hold')
        values, errors = form.Tag.collect()
        problems = issue_templates.validate(values, issue_templates.load())
        assert any(p.startswith('There is already a template called Hold') for p in problems)
        out = pane_smoke._render(win.Content, os.path.join(folder, 'templates.png'), 860.0, 480.0)
        with open(out, 'rb') as handle:
            data = handle.read()
        assert png.size(data) == (860, 480)
    finally:
        paths.redirect(previous)

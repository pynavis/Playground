# -*- coding: utf-8 -*-
"""The Preflight profile, NWD Publisher and Model Wipe forms built as real WPF windows
(namo.ui.build_form, never shown) and collected."""
import _compat

_compat.require_ironpython()

import os  # noqa: E402

from namo import preflight, publish, ui, wipe  # noqa: E402


def test_preflight_profile_form_builds():
    base = preflight.normalize_profile(preflight.DEFAULT_PROFILE)
    win = ui.build_form('Preflight profile', preflight.profile_form_fields(base, True), ok='Save',
                        width=520, units='Meters')
    values, errors = win.Tag.collect()
    assert errors == {}, errors
    profile = preflight.profile_from_form(values, base)
    assert preflight.enabled_checks(profile) == preflight.enabled_checks(base)
    assert preflight.blocking_checks(profile) == preflight.blocking_checks(base)


def test_publisher_form_builds_and_follows_method():
    folder = _compat.tmpdir('smoke_publish_form')
    settings = publish.normalize_settings({'folder': folder})
    fields = publish.form_fields(settings, os.path.join(folder, 'Job.nwf'), ['Standard', 'QA'], 'amol')
    win = ui.build_form('NWD Publisher', fields, ok='Publish', width=560, units='Meters',
                        intro='Next file: Job_v01.nwd in %s.' % folder)
    state = win.Tag
    values, errors = state.collect()
    assert errors == {}, errors
    assert values['method'] == 'publish' and values['folder'] == folder
    assert state.controls['title'].enabled()
    state.set_raw('method', 'save')
    assert not state.controls['title'].enabled() and not state.controls['exclude_hidden'].enabled()
    state.set_raw('method', 'export')
    assert state.controls['exclude_hidden'].enabled()
    state.set_raw('template', '{file}.nwd')
    values, errors = state.collect()
    assert 'template' in errors


def test_wipe_form_builds():
    counts = {'viewpoints': 24, 'sets': 0, 'clash_tests': 5, 'comments': 3, 'overrides': None,
              'hidden': 2, 'transforms': None, 'timeliner': 0, 'playground_data': 1}
    win = ui.build_form('Model Wipe', wipe.form_fields(counts, ['hidden'], 'Job.nwf'), ok='Continue',
                        width=520, units='Meters')
    state = win.Tag
    values, errors = state.collect()
    assert errors == {} and values['chosen'] == []
    state.set_raw('chosen', ['viewpoints', 'playground_data'])
    assert state.collect()[0]['chosen'] == ['viewpoints', 'playground_data']

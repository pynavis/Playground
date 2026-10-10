# -*- coding: utf-8 -*-
"""The Views forms that used to be built inline in script.py, built under IronPython
+ WPF from the same field functions the scripts now call (never shown): Export
Viewpoints options, the Viewpoint Sync import step, Batch Image Export sources (plus
its clash and issue steps), Batch PDF options and Level Sectioner settings."""
import _compat

_compat.require_ironpython()

from namo import capture, levels, rep_batch_pdf, ui, vp_sync, vpexport  # noqa: E402

BATCH_IMAGES = {'views_on': True, 'clashes_on': False, 'issues_on': False, 'views': None, 'tests': [],
                'statuses': ['New', 'Active'], 'cap': 300, 'issue_statuses': [], 'width': 1280, 'height': 720,
                'format': 'jpg', 'quality': 88, 'folder': '', 'open': True}


def test_export_viewpoints_options():
    cfg = {'views': None, 'format': 'xml', 'comments': True, 'clip_xml': False}
    win = ui.build_form('Export Viewpoints', vpexport.export_fields(cfg), intro='3 viewpoints chosen.', ok='Export')
    state = win.Tag
    values, errors = state.collect()
    assert not errors, errors
    assert values == {'format': 'xml', 'comments': True, 'clip_xml': False}
    state.set_raw('format', 'package')
    assert not state.controls['clip_xml'].enabled()
    state.set_raw('format', 'both')
    state.set_raw('clip_xml', True)
    values, errors = state.collect()
    assert not errors and values['format'] == 'both' and values['clip_xml'] is True
    win.Close()


def test_viewpoint_sync_import_step():
    cfg = {'target': '', 'keep_paths': True, 'policy': 'skip', 'clip': True, 'comments': True}
    win = ui.build_form('Viewpoint Sync', vp_sync.import_fields(cfg), intro='4 viewpoints from A.nvp.json.',
                        ok='Import')
    state = win.Tag
    values, errors = state.collect()
    assert not errors, errors
    assert values == {'target': '', 'keep_paths': True, 'policy': 'skip', 'clip': True, 'comments': True}
    state.set_raw('policy', 'replace')
    state.set_raw('target', 'From ARCH')
    values, _errors = state.collect()
    assert values['policy'] == 'replace' and values['target'] == 'From ARCH'
    win.Close()


def test_batch_images_sources_step():
    folder = _compat.tmpdir('smoke-views-inline-sources')
    for have_issues in (False, True):
        fields = capture.source_fields(dict(BATCH_IMAGES), folder, True, True, have_issues)
        win = ui.build_form('Batch Image Export', fields, ok='Next', width=500,
                            validate=capture.source_validator(True, True))
        state = win.Tag
        values, errors = state.collect()
        assert not errors, errors
        assert values['views_on'] is True and values['clashes_on'] is False and values['open'] is True
        assert values['size'] == '1280x720' and values['format'] == 'jpg' and values['folder'] == folder
        assert ('issues_on' in values) == have_issues
        state.set_raw('views_on', False)
        assert not state.accept()
        _values, errors = state.collect()
        assert errors.get('views_on') == 'Tick at least one source.'
        win.Close()
    # a source the model does not have is refused
    fields = capture.source_fields(dict(BATCH_IMAGES), folder, False, True, False)
    win = ui.build_form('Batch Image Export', fields, validate=capture.source_validator(False, True))
    state = win.Tag
    state.set_raw('views_on', True)
    _values, errors = state.collect()
    assert errors.get('views_on') == 'This model has no saved viewpoints.'
    win.Close()


def test_batch_images_clash_and_issue_steps_need_a_choice():
    win = ui.build_form('Batch Image Export', capture.clash_fields(BATCH_IMAGES), ok='Next')
    state = win.Tag
    values, errors = state.collect()
    assert not errors and values == {'statuses': ['New', 'Active'], 'cap': 300}
    state.set_raw('statuses', [])
    state.set_raw('cap', '')
    _values, errors = state.collect()
    assert 'statuses' in errors and 'cap' in errors
    win.Close()
    statuses = ['Open', 'In progress', 'Resolved', 'Closed', 'Void']
    win = ui.build_form('Batch Image Export', capture.issue_fields(BATCH_IMAGES, statuses), ok='Next')
    state = win.Tag
    values, errors = state.collect()
    assert not errors and values['issue_statuses'] == ['Open', 'In progress']
    state.set_raw('issue_statuses', [])
    _values, errors = state.collect()
    assert 'issue_statuses' in errors
    win.Close()


def test_batch_pdf_options():
    cfg = rep_batch_pdf.default_config()
    cfg.update({'open': True, 'hand_order': False})
    win = ui.build_form('Batch PDF', rep_batch_pdf.option_fields(cfg), intro='5 viewpoints chosen.', ok='Next',
                        width=500)
    state = win.Tag
    values, errors = state.collect()
    assert not errors, errors
    assert values['hand_order'] is False and values['paper'] == 'A4' and values['dpi'] == 150
    assert values['quality'] == 85 and values['footer'] == cfg['footer'] and values['open'] is True
    state.set_raw('hand_order', True)
    state.set_raw('dpi', 220)
    state.set_raw('paper', 'Tabloid')
    values, _errors = state.collect()
    assert values['hand_order'] is True and values['dpi'] == 220 and values['paper'] == 'Tabloid'
    win.Close()
    # a stored paper that is not offered any more falls back to A4
    cfg['paper'] = 'B5'
    win = ui.build_form('Batch PDF', rep_batch_pdf.option_fields(cfg))
    values, _errors = win.Tag.collect()
    assert values['paper'] == 'A4'
    win.Close()


def test_level_sectioner_settings():
    cfg = levels.settings_values({'cut_height_m': 1.5, 'slab': True, 'slab_depth_m': 0.4, 'plan': True})
    win = ui.build_form('Level Sectioner settings', levels.settings_fields(cfg, 'Millimeters'), ok='Save',
                        units='Millimeters')
    state = win.Tag
    values, errors = state.collect()
    assert not errors, errors
    assert abs(values['cut'] - 1500.0) < 1e-6 and abs(values['depth'] - 400.0) < 1e-6
    assert values['slab'] is True and values['plan'] is True
    state.set_raw('slab', False)
    assert not state.controls['depth'].enabled()
    state.set_raw('cut', '')
    assert not state.accept()
    _values, errors = state.collect()
    assert 'cut' in errors              # a blank cut height used to reach the script as None
    win.Close()

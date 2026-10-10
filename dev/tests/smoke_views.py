# -*- coding: utf-8 -*-
"""The Views windows under IronPython + WPF, built with sample data and driven
through their state objects, never shown: every form the tools open (Batch Viewpoints
per generator, image options, Sheet Overlay placement), the viewpoint chooser, and
the Batch PDF hand-order list."""
import _compat

_compat.require_ironpython()

from namo import capture, sheetoverlay, ui, vp_common, vp_ui, vpbatch  # noqa: E402

ROWS = [{'folder': '', 'name': 'Top', 'comments': 1}, {'folder': 'A', 'name': 'One', 'comments': 0},
        {'folder': 'A/B', 'name': 'Two', 'comments': 3}]


def test_batch_viewpoints_forms_build_and_read_back():
    cfg = vpbatch.settings(None)
    for generator, _label in vpbatch.GENERATORS:
        options = [('Level 1 (0.000 m)', 'Level 1'), ('Level 2 (4.000 m)', 'Level 2')] if generator == 'grid' else None
        win = ui.build_form('Batch Viewpoints', vpbatch.fields_for(generator, cfg, 'Meters', options),
                            units='Meters')
        values, errors = win.Tag.collect()
        assert not errors, (generator, errors)
        assert values['policy'] == 'replace' and values['name'] == cfg['name_' + generator]
        if generator == 'level':
            assert abs(values['cut_height'] - 1.2) < 1e-9 and values['level_view'] == 'plan'
        if generator == 'grid':
            assert values['grid_level'] == 'Level 1'
        updated = vpbatch.update_settings(cfg, generator, values, 'Meters')
        assert updated['generator'] == generator
        win.Close()


def test_image_options_form():
    cfg = {'width': 1000, 'height': 500, 'format': 'png', 'quality': 90, 'image_template': '{name}', 'folder': ''}
    folder = _compat.tmpdir('smoke-views-images')
    win = ui.build_form('Viewpoints to Images', capture.image_fields(cfg, folder))
    state = win.Tag
    values, errors = state.collect()
    assert not errors and values['size'] == 'custom' and values['width'] == 1000
    state.set_raw('size', '1920x1080')
    values, errors = state.collect()
    assert capture.image_values(cfg, values)['width'] == 1920
    win.Close()


def test_sheet_overlay_placement_form_validates():
    drawing = {'units_name': 'Millimeters', 'segments': [], 'texts': [], 'layers': {}}
    options = [('Level 1 (0.000 m)', 'level:Level 1'), ('Type an elevation', 'typed')]
    win = ui.build_form('Sheet Overlay', sheetoverlay.placement_fields(drawing, {}, options, 'Meters'),
                        validate=sheetoverlay.validator('Meters'))
    state = win.Tag
    values, errors = state.collect()
    assert not errors and values['units_choice'] == 'file' and values['mode'] == 'manual'
    state.set_raw('mode', 'points')
    state.set_raw('p1', 'nope')
    assert not state.accept()
    _values, errors = state.collect()
    assert 'p1' in errors
    win.Close()


def test_viewpoint_chooser_ticks_the_spec():
    table = [{'value': i, 'cells': [vp_common.folder_label(r['folder']), r['name'], r['comments']]}
             for i, r in enumerate(ROWS)]
    picked = vp_common.select_rows(ROWS, {'mode': 'folders', 'folders': ['A']})
    win = ui.build_choose('Viewpoints', table, ['Folder', 'Name', 'Comments'],
                          checked=[i for i, r in enumerate(ROWS) if r in picked])
    state = win.Tag
    assert state.values() == [1, 2]
    chosen = [ROWS[i] for i in state.values()]
    assert vp_common.spec_for(ROWS, chosen) == {'mode': 'folders', 'folders': ['A'], 'views': []}
    win.Close()


def test_order_window_moves_rows():
    win = vp_ui.build_order('Batch PDF: page order', ['Top', 'A/One', 'A/B/Two'])
    state = win.Tag
    assert state.order == [0, 1, 2] and state.table.total() == 3
    state.table.select_values([2])
    state.move('top')
    assert state.order == [2, 0, 1]
    state.move('down')
    assert state.order == [0, 2, 1]
    state.table.select_values([1])
    state.move('up')
    assert state.order == [0, 1, 2]
    assert not state.accepted
    win.Close()

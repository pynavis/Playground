# -*- coding: utf-8 -*-
"""Every Look panel form and window built with sample data under IronPython + WPF
(never shown): the field lists parse and validate, the choosers and the Manage
presets table build, and their state objects return what the scripts expect."""
import os

import _compat

_compat.require_ironpython()

from namo import colorize, explode, legend, look_ghost, look_status, look_tools, paths, presentation, ui  # noqa: E402


def _values(win):
    values, errors = win.Tag.collect()
    assert errors == {}, errors
    return values


def test_color_by_property_options_and_chooser():
    win = ui.build_form('Color by Property', colorize.options_fields(3, {'scope': 'selection'}), ok='Next')
    values = _values(win)
    assert values['scope'] == 'selection' and values['top'] == colorize.DEFAULT_TOP
    assert values['other'] == 'grey' and values['reset'] is True and values['ghost'] is False
    win.Tag.set_raw('top', '99')
    _values_bad, errors = win.Tag.collect()
    assert 'top' in errors
    rows = colorize.property_rows([('Element', 'Category', 290), ('Item', 'Layer', 300)], 300)
    chooser = ui.build_choose('Color by Property', rows, ['Category', 'Property', 'Found on'],
                              multiselect=False, checked=[('Item', 'Layer')], ok='Color', prompt='Pick')
    assert chooser.Tag.values() == [('Item', 'Layer')]


def test_manage_presets_window():
    folder = _compat.tmpdir('smoke_look_presets')
    previous = paths.redirect(folder)
    try:
        presets = os.path.join(folder, 'presets')
        plan = colorize.plan_scheme([('Ducts', 3), ('Pipes', 2)], top=2)
        scheme = colorize.make_scheme('Element', 'Category', plan, 'whole model')
        colorize.save_preset(colorize.preset_from_scheme(scheme, 'By category'), presets)
        win = colorize.build_manage_window(presets)
        state = win.Tag
        assert state.table.total() == 1
        state.update(colorize.manage_rows(colorize.list_presets(presets)), 'Refreshed')
        assert state.status_block.Text == 'Refreshed'
    finally:
        paths.redirect(previous)


def test_status_settings_form():
    cfg = look_status.normalize_config({'statuses': [['Installed', '010203'], ['Delivered', '4E79A7']]})
    win = ui.build_form('Status Painter settings', look_status.config_fields(cfg), ok='Save', width=480)
    values = _values(win)
    back = look_status.config_from_form(values)
    assert back['statuses'][0] == ['Installed', '010203']
    assert back['statuses'][-1] == ['Delivered', '4E79A7']
    win.Tag.set_raw('extra', 'nonsense line')
    _v, errors = win.Tag.collect()
    assert 'extra' in errors


def test_trade_ghost_chooser_and_settings():
    groups = [('Mechanical', ['M-01.nwc', 'M-02.nwc']), ('Unassigned', ['notes.nwc'])]
    rows = look_ghost.chooser_rows(groups, 4)
    chooser = ui.build_choose('Trade Ghost', rows, ['Focus', 'Size', 'Models'], multiselect=True,
                              checked=['Mechanical'], ok='Ghost the rest', prompt='Tick')
    assert chooser.Tag.values() == ['Mechanical']
    win = ui.build_form('Trade Ghost settings', look_ghost.config_fields(look_ghost.normalize_config({})))
    assert _values(win) == {'transparency': 85, 'grey': True}


def test_look_tool_forms():
    win = ui.build_form('Reset Overrides', look_tools.reset_fields(['hidden', 'transforms']), ok='Reset')
    assert _values(win)['kinds'] == ['hidden', 'transforms']
    win = ui.build_form('Background', look_tools.background_fields({'choice': look_tools.CUSTOM_GRADIENT,
                                                                      'top': '112233'}))
    spec = look_tools.background_from_form(_values(win))
    assert spec['style'] == 'graduated' and spec['colors'][0] == '112233'
    win = ui.build_form('Match Appearance', look_tools.match_fields('Duct', '4E79A7', None), ok='Paint')
    assert _values(win) == {'hex': '4E79A7', 'transparency': 0}


def test_explode_presentation_and_legend_forms():
    win = ui.build_form('Exploded View', explode.option_fields({'factor': 2.5}, 3), ok='Explode')
    values = _values(win)
    assert values['factor'] == 2.5 and values['mode'] == 'radial' and values['units'] == 'items'
    win = ui.build_form('Presentation Mode settings', presentation.option_fields({'background': 'Black'}))
    assert presentation.normalize_options(_values(win)) == {'panes': True, 'maximize': True,
                                                            'background': 'Black'}
    plan = colorize.plan_scheme([('A', 2)], top=1)
    scheme = colorize.make_scheme('E', 'P', plan, 'whole model')
    folder = _compat.tmpdir('smoke_look_legend_form')
    path = os.path.join(folder, legend.default_name('P', 'Model'))
    win = ui.build_form('Legend Maker', legend.form_fields(scheme, path, {}), ok='Save legend')
    values = _values(win)
    assert values['path'] == path and values['title'] == 'P' and values['view'] is False

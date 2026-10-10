# -*- coding: utf-8 -*-
"""Every window of the Exchange and Reports panels built as real WPF (never shown):
the Geometry and IFC Exporter forms, the IFC class rules form, the Report Templates list,
its generated template form and report chooser, the Scheduled Reports list, the
schedule form, the mail profiles list and form, and the password dialog."""
import _compat

_compat.require_ironpython()

import os  # noqa: E402

from namo import (ifcexport, meshexport, reportrunner, sched_mail, sched_ui, schedule,  # noqa: E402
                  ui)


def test_geometry_exporter_form():
    options = [meshexport.property_option('Element', 'Mark'), meshexport.property_option('Element', 'Level')]
    values = dict(meshexport.DEFAULT_OPTIONS, properties=[options[1][1], 'Gone\tProperty'])
    win = ui.build_form('Geometry exporter', meshexport.form_fields(values, 'Millimeters', options), ok='Export',
                        width=560, units='Millimeters')
    state = win.Tag
    got, errors = state.collect()
    assert errors == {}, errors
    assert got['format'] == 'glb' and got['properties'] == [options[1][1]]
    assert not state.controls['units'].enabled() and not state.controls['layers'].enabled()
    state.set_raw('format', 'dxf')
    assert state.controls['units'].enabled() and state.controls['layers'].enabled()
    assert not state.controls['identity'].enabled()
    state.set_raw('per_object', '10')
    assert 'per_object' in state.collect()[1]
    assert meshexport.property_pairs(got['properties']) == [('Element', 'Level')]


def test_ifc_exporter_forms():
    win = ui.build_form('IFC exporter', ifcexport.form_fields(dict(ifcexport.DEFAULT_OPTIONS), 'Hospital', 'Main'),
                        ok='Export', width=560, units='Meters', intro=ifcexport.FORM_INTRO)
    got, errors = win.Tag.collect()
    assert errors == {} and got['storeys'] == 'auto' and got['project'] == 'Hospital'
    rules = ui.build_form('IFC classes', ifcexport.override_fields({'walls': ('IfcCurtainWall', None)}), ok='Save',
                          width=600, units='Meters')
    got, errors = rules.Tag.collect()
    assert errors == {} and got['map'] == 'walls = IfcCurtainWall' and got['show'] is False
    rules.Tag.set_raw('map', 'Walls = IfcSpaceship')
    assert rules.Tag.collect()[1]['map'].startswith('Line 1: IfcSpaceship')


def test_report_templates_window_and_forms():
    rows = [{'report': 'stale_files', 'title': 'Stale File Alert', 'name': 'Every model', 'available': True,
             'description': 'Every model', 'updated': '2026-10-05T14:30:00', 'user': 'amol', 'config': {}},
            {'report': 'clash_html', 'title': 'Clash HTML Dashboard', 'name': 'Board', 'available': False,
             'description': reportrunner.NOT_BUILT, 'updated': '', 'user': '', 'config': {}}]
    table_rows = reportrunner._table_rows(rows)
    clicked = []
    actions = [{'label': 'New', 'fn': lambda v: clicked.append('new'), 'needs_selection': False},
               {'label': 'Run', 'fn': lambda v: clicked.append(v), 'primary': True}]
    win = ui.build_table('Report templates', reportrunner.HEADERS, table_rows, actions=actions,
                         status=reportrunner._status(rows), width=940, height=560)
    state = win.Tag
    assert state.table.total() == 2
    assert state.status_block.Text == '2 templates, 1 for reports not built yet.'
    state.update(table_rows[:1], 'One left.')
    assert state.table.total() == 1 and state.status_block.Text == 'One left.'

    defaults = {'folder': '', 'name_template': '{report} {date}', 'tests': [], 'images': False, 'budget': 40000,
                'tolerance': 2.0}
    fields, kinds = reportrunner.fields_for(dict(defaults, tests=['A']), defaults, 'Weekly', ['Daily'])
    form = ui.build_form('Clash Excel Report template', fields, ok='Save', width=560, units='Meters')
    got, errors = form.Tag.collect()
    assert errors == {}, errors
    name, config = reportrunner.config_from(got, kinds)
    assert name == 'Weekly' and config['tests'] == ['A'] and config['budget'] == 40000
    form.Tag.set_raw('tests', '{"not": "a list"}')
    assert form.Tag.collect()[1]['tests'] == 'Enter a JSON list, like ["A", "B"].'
    form.Tag.set_raw('__name', 'daily')
    assert '__name' in form.Tag.collect()[1]

    chooser = ui.build_choose('New template', [{'cells': ['Stale File Alert', 'Ready', 1], 'value': 'stale_files'},
                                               {'cells': ['Clash HTML Dashboard', reportrunner.NOT_BUILT, 0],
                                                'value': 'clash_html'}],
                              ['Report', 'Status', 'Templates'], multiselect=False)
    assert chooser.Tag.table.total() == 2


def test_scheduled_reports_windows():
    folder = _compat.tmpdir('smoke_schedule')
    model = os.path.join(folder, 'Hospital.nwd')
    with open(model, 'wb') as handle:
        handle.write(b'x')
    options = [('Clash Excel Report: Weekly', ('clash_excel', 'Weekly')),
               ('Model Health Check: Every model', ('health_check', 'Every model'))]
    win = ui.build_form('New schedule', sched_ui.schedule_fields(None, options, ['Office 365'], [], model),
                        ok='Save', width=600, units='Meters')
    state = win.Tag
    got, errors = state.collect()
    assert sorted(errors) == ['name', 'templates'], errors
    state.set_raw('name', 'Nightly')
    state.set_raw('templates', [options[1][1]])
    state.set_raw('frequency', 'daily')
    assert not state.controls['days'].enabled()
    got, errors = state.collect()
    assert errors == {}, errors
    record = sched_ui.schedule_from(got, os.path.join(folder, 'scheduled_runner.py'))
    assert record['name'] == 'Nightly' and record['model'] == model
    assert record['templates'] == [['health_check', 'Every model']] and record['frequency'] == 'daily'
    assert schedule.validate(record, runner_exists=True) == []

    item = dict(record, enabled=True)
    rows = [{'cells': sched_ui.row_for(item, {'exists': True, 'next_run': 'tomorrow', 'last_run': 'N/A',
                                              'result_text': 'Not run yet'}), 'value': item['name']}]
    table = ui.build_table('Scheduled reports', sched_ui.HEADERS, rows,
                           actions=[{'label': 'New', 'fn': lambda v: None, 'needs_selection': False,
                                     'primary': True}], status='1 schedule.', width=1040, height=520)
    assert table.Tag.table.total() == 1

    profile = ui.build_form('Mail profile', sched_ui.profile_fields(None, []), ok='Save', width=520, units='Meters')
    for key, raw in (('name', 'Office 365'), ('server', 'smtp.office365.com'), ('sender', 'r@x.com'),
                     ('to', 'a@b.com\nc@d.com')):
        profile.Tag.set_raw(key, raw)
    got, errors = profile.Tag.collect()
    assert errors == {}, errors
    assert sched_ui.profile_from(got, '')['to'] == ['a@b.com', 'c@d.com']
    profiles = ui.build_table('Mail settings', sched_ui.PROFILE_HEADERS,
                              [{'cells': sched_ui.profile_row(sched_ui.profile_from(got, '')), 'value': 'Office 365'}],
                              actions=[{'label': 'Send test', 'fn': lambda v: None, 'primary': True}],
                              width=820, height=420)
    assert profiles.Tag.table.total() == 1

    password = sched_mail.build_password_window('Mail password', 'Password for r@x.com on smtp.office365.com',
                                                keep_hint=True)
    assert password.Tag.result is None
    password.Tag.box.Password = 'secret'
    assert password.Tag.box.Password == 'secret'

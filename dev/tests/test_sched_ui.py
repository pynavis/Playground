# -*- coding: utf-8 -*-
"""namo.sched_ui pure half (list rows, schedule and mail forms and what they give back)
and namo.xchg_common's pure helpers."""
import datetime

import _compat

from namo import naming, sched_ui as su, xchg_common


def catalog_rows():
    return [{'report': 'clash_excel', 'title': 'Clash Excel Report', 'name': 'Weekly', 'available': True},
            {'report': 'clash_html', 'title': 'Clash HTML Dashboard', 'name': 'Board', 'available': False},
            {'report': 'health_check', 'title': 'Model Health Check', 'name': 'Every model', 'available': True}]


def test_template_options_only_available():
    assert su.template_options(catalog_rows()) == [
        ('Clash Excel Report: Weekly', ('clash_excel', 'Weekly')),
        ('Model Health Check: Every model', ('health_check', 'Every model'))]


def test_row_for():
    item = {'name': 'Weekly', 'model': r'C:\Jobs\Hospital.nwf', 'templates': [['a', 'b'], ['c', 'd']],
            'frequency': 'weekly', 'days': ['MON'], 'time': '07:00', 'enabled': False}
    state = {'exists': True, 'next_run': '12/10/2026 07:00:00', 'last_run': 'N/A', 'result_text': 'Not run yet'}
    assert su.row_for(item, state) == ['Weekly', 'Mon at 07:00 (off)', 'Hospital.nwf', 2, '12/10/2026 07:00:00',
                                       'N/A', 'Not run yet']
    last = {'results': [{}, {}], 'failed': 0, 'problems': []}
    assert su.row_for(item, state, last)[-1] == '2 of 2 succeeded'
    gone = su.row_for(item, {'exists': False, 'status': 'Missing in Task Scheduler'})
    assert gone[-1].startswith('Missing in Task Scheduler')


def test_schedule_fields_and_record():
    options = su.template_options(catalog_rows())
    fields = su.schedule_fields(None, options, ['Office 365'], ['Daily'], default_model=r'C:\Jobs\H.nwf')
    by_key = dict((f['key'], f) for f in fields if f.get('key'))
    assert by_key['model']['default'] == r'C:\Jobs\H.nwf' and by_key['frequency']['default'] == 'weekly'
    assert by_key['days']['default'] == ['MON', 'TUE', 'WED', 'THU', 'FRI']
    assert by_key['mail']['options'][0] == ('Do not send mail', '') and by_key['mail']['default'] == ''
    assert by_key['name']['validate']('daily') == 'Another schedule already has that name.'
    assert by_key['name']['validate'](':::') == 'A schedule needs a name with letters or digits.'
    assert by_key['name']['validate']('Weekly') is None
    assert by_key['time']['validate']('25:00') == 'Enter a time between 00:00 and 23:59.'
    values = {'name': ' Weekly\tcoordination ', 'model': r' C:\Jobs\H.nwf ', 'templates': [('clash_excel', 'Weekly')],
              'frequency': 'weekly', 'days': ['FRI', 'MON'], 'time': '7:5', 'timeout_minutes': 60, 'folder': '',
              'copy_to': r'\\srv\share', 'mail': 'Office 365', 'attach': False, 'enabled': True}
    _compat.raises(ValueError, su.schedule_from, values, r'C:\r.py')
    values['time'] = '7:05'
    record = su.schedule_from(values, r'C:\r.py', now=datetime.datetime(2026, 10, 5, 9, 0))
    assert record == {'name': 'Weekly coordination', 'model': r'C:\Jobs\H.nwf', 'templates': [['clash_excel', 'Weekly']],
                      'frequency': 'weekly', 'days': ['MON', 'FRI'], 'time': '07:05', 'timeout_minutes': 60,
                      'folder': '', 'copy_to': r'\\srv\share', 'mail': 'Office 365', 'attach': False,
                      'enabled': True, 'runner': r'C:\r.py', 'updated': '2026-10-05T09:00:00'}
    daily = su.schedule_from(dict(values, frequency='daily'), 'r.py')
    assert daily['days'] == []
    editing = su.schedule_fields(record, options, ['Office 365'], [])
    by_key = dict((f['key'], f) for f in editing if f.get('key'))
    assert by_key['templates']['default'] == [('clash_excel', 'Weekly')] and by_key['mail']['default'] == 'Office 365'
    assert by_key['attach']['default'] is False


def test_profile_fields_and_record():
    fields = su.profile_fields(None, ['Office'])
    by_key = dict((f['key'], f) for f in fields)
    assert by_key['name']['validate']('office') is not None
    assert by_key['sender']['validate']('nope') == 'Enter an address, like reports@example.com.'
    assert by_key['to']['validate']('a@b.com\nbad') == 'Not an address: bad'
    assert by_key['to']['validate']('') == 'Enter at least one address.'
    assert by_key['security']['options'][0] == ('STARTTLS (port 587)', 'starttls')
    values = {'name': 'Office 365', 'server': ' smtp.office365.com ', 'port': 587, 'security': 'starttls',
              'sender': 'reports@x.com', 'to': 'a@b.com; c@d.com', 'username': ' reports@x.com ', 'engine': 'auto'}
    profile = su.profile_from(values, 'SEALED')
    assert profile == {'name': 'Office 365', 'server': 'smtp.office365.com', 'port': 587, 'security': 'starttls',
                       'sender': 'reports@x.com', 'to': ['a@b.com', 'c@d.com'], 'username': 'reports@x.com',
                       'password': 'SEALED', 'engine': 'auto'}
    assert su.profile_row(profile) == ['Office 365', 'smtp.office365.com:587', 'STARTTLS', 'reports@x.com',
                                       'a@b.com, c@d.com']


def test_xchg_default_names_and_skipped_rows():
    values = naming.standard_values()
    values.update({'file': '', 'date': datetime.date(2026, 10, 5)})
    assert xchg_common.default_name('{file} - Geometry - {date}', '.glb', values) == 'Untitled - Geometry - 2026-10-05.glb'
    values['file'] = 'Hospital: tower'
    assert xchg_common.default_name('{file}', '.ifc', values) == 'Hospital_ tower.ifc'
    rows = xchg_common.skipped_rows([('Duct 10', 'No triangles', None), ('Duct 9', 'No triangles', None),
                                     ('Big', 'More than 5 triangles', None)])
    assert rows == [('Big', 'More than 5 triangles'), ('Duct 9', 'No triangles'), ('Duct 10', 'No triangles')]


class FakeDoc(object):
    def __init__(self, title, filename):
        self.Title = title
        self.FileName = filename


def test_xchg_doc_helpers():
    folder = _compat.tmpdir('xchg_doc')
    import os
    saved = FakeDoc('Hospital.nwf', os.path.join(folder, 'Hospital.nwf'))
    assert xchg_common.doc_folder(saved) == folder
    assert xchg_common.doc_title(FakeDoc('', '')) == 'Untitled'
    assert xchg_common.doc_title(FakeDoc('', r'C:\x\Job.nwd')) == 'Job.nwd'
    assert xchg_common.doc_folder(FakeDoc('', '')).lower().endswith(('documents', os.path.expanduser('~').lower()))


def test_xchg_where_text_always_names_the_file():
    """Refit: an export that skipped objects used to toast the skip count and lose the
    path; the detail now always ends with where the file is."""
    path = r'C:\Jobs\Tower - Geometry.glb'
    assert xchg_common.where_text('3 skipped (listed in the output window).', path) == \
        '3 skipped (listed in the output window). ' + path
    assert xchg_common.where_text('', path) == path
    assert xchg_common.where_text('2 storeys.', '') == '2 storeys.'


def test_xchg_under_runner_is_false_outside_pynavis_run():
    assert xchg_common.under_runner() is False

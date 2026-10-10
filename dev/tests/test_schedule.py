# -*- coding: utf-8 -*-
"""namo.schedule: Windows command lines (quoting with spaces), task names, the runner's
arguments both ways, times and next starts, the task XML, schtasks commands and their
CSV output, schedule records, run logs, and the runner side on fakes. Nothing here
creates a task or runs schtasks."""
import datetime
import io
import os
import xml.etree.ElementTree as ET

import _compat

from namo import paths, schedule as s

NS = '{http://schemas.microsoft.com/windows/2004/02/mit/task}'


def sample(**changes):
    item = {'name': 'Weekly coordination', 'model': r'\\server\Jobs\Hospital Tower\Hospital.nwf',
            'templates': [['clash_excel', 'Weekly; all tests'], ['health_check', 'Every model']],
            'frequency': 'weekly', 'days': ['FRI', 'MON'], 'time': '07:30', 'timeout_minutes': 90,
            'folder': r'D:\Reports Out', 'copy_to': '', 'mail': 'Office 365', 'attach': True, 'enabled': True}
    item.update(changes)
    return item


# ---- command lines ---------------------------------------------------------------------------


def test_quote_arg_rules():
    assert s.quote_arg('plain') == 'plain'
    assert s.quote_arg('') == '""'
    assert s.quote_arg(r'C:\Program Files\x.exe') == r'"C:\Program Files\x.exe"'
    assert s.quote_arg(r'C:\Folder With Space' + '\\') == r'"C:\Folder With Space\\"'
    assert s.quote_arg('say "hi"') == r'"say \"hi\""'
    assert s.quote_arg(r'a\\b') == r'a\\b'
    assert s.quote_arg(r'back\"quote') == r'"back\\\"quote"'


def test_quote_matches_subprocess_list2cmdline():
    if _compat.IRONPYTHON:
        raise _compat.SkipTest('compared on CPython')
    import subprocess
    plain = ['run', r'C:\A B\script.py', r'\\srv\share\m 1.nwf', '--', '--templates', 'x:a b;y:c',
             '', 'tail\\', 'sp ace\\', 'tab\there']
    assert s.command_line(plain) == subprocess.list2cmdline(plain)
    # with a quote inside, list2cmdline leaves the word bare and this module quotes it:
    # both read back as the same argument
    quoted = ['a"b', 'x']
    assert s.split_command_line(s.command_line(quoted)) == s.split_command_line(subprocess.list2cmdline(quoted))


def test_command_line_round_trips_through_argv_rules():
    args = ['run', r'C:\Users\Jo Smith\Playground.extension\Scheduled_Reports.pushbutton\scheduled_runner.py',
            r'\\server\Jobs\Hospital Tower\Hospital.nwf', '--timeout', '5400', '--', '--schedule',
            'Weekly "A" run', '--templates', 'clash_excel:Weekly;; all;health_check:Every model',
            '--folder', 'D:\\Reports Out\\', '--copy-to', '', '--mail', u'Caf\u00e9 profile']
    assert s.split_command_line(s.command_line(args)) == args


def test_split_command_line_known_cases():
    assert s.split_command_line(r'a "b c" d') == ['a', 'b c', 'd']
    assert s.split_command_line(r'"a\"b"') == ['a"b']
    assert s.split_command_line(r'a\\\"b') == ['a\\"b']
    assert s.split_command_line(r'"c:\x\\" y') == ['c:\\x\\', 'y']
    assert s.split_command_line('""') == ['']


# ---- names and runner arguments -------------------------------------------------------------


def test_task_names():
    assert s.task_name('Weekly: clash / report?') == 'Weekly clash report'
    assert s.task_path('Weekly coordination') == '\\Playground\\Weekly coordination'
    _compat.raises(ValueError, s.task_name, ' :/ ')
    assert len(s.task_name('x' * 300)) == 120


def test_templates_argument_both_ways():
    pairs = [('clash_excel', 'Weekly; all tests'), ('health_check', 'Every model')]
    text = s.encode_templates(pairs)
    assert text == 'clash_excel:Weekly;; all tests;health_check:Every model'
    assert s.decode_templates(text) == pairs
    assert s.decode_templates('a:b;;c;') == [('a', 'b;c')]
    assert s.decode_templates('a:Level: 2') == [('a', 'Level: 2')]
    _compat.raises(ValueError, s.decode_templates, 'no colon here')


def test_runner_args_and_parse_back():
    item = sample()
    args = s.runner_args(item, r'C:\ext\scheduled_runner.py', r'C:\logs\last-results.json')
    assert args[:7] == ['run', r'C:\ext\scheduled_runner.py', item['model'], '--timeout', '5400',
                        '--results', r'C:\logs\last-results.json']
    after = args[args.index('--') + 1:]
    options, problems = s.parse_runner_args(after)
    assert problems == []
    assert options == {'schedule': 'Weekly coordination', 'templates': [('clash_excel', 'Weekly; all tests'),
                                                                         ('health_check', 'Every model')],
                       'mail': 'Office 365', 'folder': r'D:\Reports Out', 'copy_to': '', 'attach': True}
    quiet = s.runner_args(sample(mail='', folder='', attach=False), 'r.py', None)
    assert '--mail' not in quiet and '--results' not in quiet and quiet[-1] == '--no-attach'


def test_parse_runner_args_problems():
    assert s.parse_runner_args([])[1] == ['No templates were given (--templates).']
    assert s.parse_runner_args(['--templates'])[1] == ['--templates needs a value.']
    assert s.parse_runner_args(['--templates', 'a:b', '--frobnicate'])[1] == ['Unknown option --frobnicate.']
    assert s.parse_runner_args(['--templates', 'oops'])[1] == ['"oops" is not report:template.']


# ---- when -----------------------------------------------------------------------------------


def test_parse_time():
    assert s.parse_time('7:30') == (7, 30)
    assert s.parse_time(' 0730 ') == (7, 30)
    assert s.parse_time('19.05') == (19, 5)
    for bad in ('24:00', '7:60', 'seven', '', None):
        _compat.raises(ValueError, s.parse_time, bad)


def test_next_start():
    monday_9 = datetime.datetime(2026, 10, 5, 9, 0, 30)          # a Monday
    assert s.next_start(monday_9, 10, 0) == datetime.datetime(2026, 10, 5, 10, 0)
    assert s.next_start(monday_9, 7, 0) == datetime.datetime(2026, 10, 6, 7, 0)
    assert s.next_start(monday_9, 9, 0) == datetime.datetime(2026, 10, 6, 9, 0)
    assert s.next_start(monday_9, 7, 0, 'weekly', ['FRI', 'MON']) == datetime.datetime(2026, 10, 9, 7, 0)
    assert s.next_start(monday_9, 7, 0, 'weekly', ['mon']) == datetime.datetime(2026, 10, 12, 7, 0)
    _compat.raises(ValueError, s.next_start, monday_9, 7, 0, 'weekly', [])


def test_describe_when():
    assert s.describe_when(sample()) == 'Mon and Fri at 07:30'
    assert s.describe_when(sample(days=['WED', 'MON', 'FRI'])) == 'Mon, Wed and Fri at 07:30'
    assert s.describe_when(sample(days=['MON', 'TUE', 'WED', 'THU', 'FRI'])) == 'Weekdays at 07:30'
    assert s.describe_when(sample(frequency='daily')) == 'Daily at 07:30'
    assert s.describe_when(sample(time='late')) == 'Unknown time'


# ---- task XML and schtasks --------------------------------------------------------------------


def test_task_xml_is_valid_and_complete():
    item = sample()
    arguments = s.command_line(s.runner_args(item, r'C:\A B\scheduled_runner.py', r'C:\logs\r.json'))
    text = s.task_xml(item, r'C:\Users\Jo Smith\AppData\Roaming\pyNavis\cli\pynavis.exe', arguments,
                      'LAPTOP\\amol', datetime.datetime(2026, 10, 5, 9, 0), working_dir=r'C:\logs')
    assert text.startswith('<?xml version="1.0" encoding="UTF-16"?>')
    data = text.encode('utf-16')
    assert data[:2] == b'\xff\xfe'
    root = ET.fromstring(text.split('?>', 1)[1].strip())
    assert root.tag == NS + 'Task' and root.get('version') == '1.2'
    assert root.find(NS + 'RegistrationInfo/' + NS + 'URI').text == '\\Playground\\Weekly coordination'
    trigger = root.find(NS + 'Triggers/' + NS + 'CalendarTrigger')
    assert trigger.find(NS + 'StartBoundary').text == '2026-10-09T07:30:00'
    days = [child.tag[len(NS):] for child in trigger.find(NS + 'ScheduleByWeek/' + NS + 'DaysOfWeek')]
    assert days == ['Monday', 'Friday']
    principal = root.find(NS + 'Principals/' + NS + 'Principal')
    assert principal.find(NS + 'LogonType').text == 'InteractiveToken'
    assert principal.find(NS + 'RunLevel').text == 'LeastPrivilege'
    assert principal.find(NS + 'UserId').text == 'LAPTOP\\amol'
    settings = root.find(NS + 'Settings')
    assert settings.find(NS + 'StartWhenAvailable').text == 'true'
    assert settings.find(NS + 'DisallowStartIfOnBatteries').text == 'false'
    assert settings.find(NS + 'MultipleInstancesPolicy').text == 'IgnoreNew'
    assert settings.find(NS + 'ExecutionTimeLimit').text == 'PT300M'
    exec_ = root.find(NS + 'Actions/' + NS + 'Exec')
    assert exec_.find(NS + 'Command').text.endswith('pynavis.exe')
    assert s.split_command_line(exec_.find(NS + 'Arguments').text) == \
        s.runner_args(item, r'C:\A B\scheduled_runner.py', r'C:\logs\r.json')
    assert exec_.find(NS + 'WorkingDirectory').text == r'C:\logs'


def test_task_xml_daily_disabled_and_escaped():
    item = sample(frequency='daily', enabled=False, name='R&D <weekly>')
    text = s.task_xml(item, 'p.exe', 'run "a&b"', 'D\\u', datetime.datetime(2026, 10, 5, 8, 0))
    root = ET.fromstring(text.split('?>', 1)[1].strip())
    trigger = root.find(NS + 'Triggers/' + NS + 'CalendarTrigger')
    assert trigger.find(NS + 'ScheduleByDay/' + NS + 'DaysInterval').text == '1'
    assert trigger.find(NS + 'StartBoundary').text == '2026-10-06T07:30:00'
    assert root.find(NS + 'Settings/' + NS + 'Enabled').text == 'false'
    assert root.find(NS + 'Actions/' + NS + 'Exec/' + NS + 'Arguments').text == 'run "a&b"'
    assert root.find(NS + 'RegistrationInfo/' + NS + 'URI').text == '\\Playground\\R&D weekly'


def test_execution_limit():
    assert s.execution_limit(120) == 'PT390M'
    assert s.execution_limit(10000) == 'PT4320M'


def test_schtasks_commands_quote_spaces():
    exe = s.schtasks_exe()
    assert exe.lower().endswith('system32\\schtasks.exe')
    create = s.create_command('Weekly coordination', r'C:\Users\Jo Smith\task.xml')
    assert create[1:] == ['/Create', '/TN', '\\Playground\\Weekly coordination', '/XML',
                          r'C:\Users\Jo Smith\task.xml', '/F']
    line = s.command_line(create)
    assert '"\\Playground\\Weekly coordination"' in line and r'"C:\Users\Jo Smith\task.xml"' in line
    assert s.split_command_line(line) == create
    assert s.run_command('A')[1:] == ['/Run', '/TN', '\\Playground\\A']
    assert s.delete_command('A')[1:] == ['/Delete', '/TN', '\\Playground\\A', '/F']
    assert s.query_command('A')[1:] == ['/Query', '/TN', '\\Playground\\A', '/FO', 'CSV', '/V', '/NH']
    assert s.change_command('A', False)[-1] == '/DISABLE' and s.change_command('A', True)[-1] == '/ENABLE'


def test_register_quotes_a_command_path_with_spaces():
    """Regression: register() wrote pynavis.exe into <Command> unquoted, so under a user
    folder with a space (C:\\Users\\Jo Smith\\...) Task Scheduler could split the
    program path. schtasks is faked: nothing is registered."""
    folder = _compat.tmpdir('schedule_register')
    previous = paths.redirect(folder)
    exe = os.path.join(folder, 'Jo Smith', 'pyNavis', 'cli', 'pynavis.exe')
    paths.ensure_dir(os.path.dirname(exe))
    with open(exe, 'wb') as handle:
        handle.write(b'MZ')
    calls = []

    def fake_schtasks(args, timeout=60):
        calls.append(list(args))
        return 0, 'SUCCESS'

    saved = (s.pynavis_exe, s.run_schtasks)
    s.pynavis_exe = lambda: exe
    s.run_schtasks = fake_schtasks
    item = sample()
    runner = r'C:\A B\scheduled_runner.py'
    try:
        ok, _message = s.register(item, runner)
        with open(s.xml_path(item['name']), 'rb') as handle:
            text = handle.read().decode('utf-16')
        working = s.log_folder(item['name'])
        expected = s.runner_args(item, runner, s.results_path(item['name']))
    finally:
        s.pynavis_exe, s.run_schtasks = saved
        paths.redirect(previous)
    assert ok
    # first pynavis.exe is asked whether it has the run command, then the task is created
    assert calls[0] == [exe, 'run', '--help']
    assert calls[1][1:3] == ['/Create', '/TN'] and len(calls) == 2
    exec_ = ET.fromstring(text.split('?>', 1)[1].strip()).find(NS + 'Actions/' + NS + 'Exec')
    assert exec_.find(NS + 'Command').text == '"%s"' % exe
    assert s.split_command_line(exec_.find(NS + 'Arguments').text) == expected
    assert exec_.find(NS + 'WorkingDirectory').text == working


def test_runner_state_tells_an_old_pynavis_exe_from_one_with_run():
    """Refit: a pynavis.exe from a pyNavis without `pynavis run` exists on disk but exits 2
    for every run, so the file being there is not enough. The probe is `run --help`, which
    never starts Navisworks."""
    asked = []

    def probe_ok(args):
        asked.append(list(args))
        return 0, 'pynavis run <script.py> ...'

    def broken(args):
        raise OSError('cannot start')

    exe = r'C:\Users\Jo Smith\AppData\Roaming\pyNavis\cli\pynavis.exe'
    assert s.help_command(exe) == [exe, 'run', '--help']
    assert s.runner_state(exe, exists=lambda p: False, probe=probe_ok) == 'missing' and not asked
    assert s.runner_state(exe, exists=lambda p: True, probe=probe_ok) == 'ok'
    assert asked == [[exe, 'run', '--help']]
    assert s.runner_state(exe, exists=lambda p: True, probe=lambda args: (2, 'pynavis - pyNavis command line')) == 'old'
    assert s.runner_state(exe, exists=lambda p: True, probe=broken) == 'ok'
    assert s.runner_problem('ok') is None
    assert s.runner_problem('missing')[0] == 'pyNavis command line runner not found'
    title, sentence = s.runner_problem('old')
    assert 'pynavis run' in sentence and sentence.endswith('Update pyNavis, then try again.')


def test_register_refuses_an_old_pynavis_exe():
    folder = _compat.tmpdir('schedule_register_old')
    previous = paths.redirect(folder)
    exe = os.path.join(folder, 'cli', 'pynavis.exe')
    paths.ensure_dir(os.path.dirname(exe))
    with open(exe, 'wb') as handle:
        handle.write(b'MZ')
    calls = []

    def fake(args, timeout=60):
        calls.append(list(args))
        return 2, 'usage'

    saved = (s.pynavis_exe, s.run_schtasks)
    s.pynavis_exe = lambda: exe
    s.run_schtasks = fake
    try:
        ok, message = s.register(sample(), r'C:\x\scheduled_runner.py')
    finally:
        s.pynavis_exe, s.run_schtasks = saved
        paths.redirect(previous)
    assert not ok and message == s.old_runner_message()
    assert calls == [[exe, 'run', '--help']]            # no task was created


QUERY = ('"LAPTOP","\\Playground\\Weekly coordination","09/10/2026 07:30:00","Ready","Interactive only",'
         '"05/10/2026 07:30:01","1","LAPTOP\\amol","C:\\x\\pynavis.exe run ...","N/A","N/A","Enabled",'
         '"Disabled","Stop On Battery Mode","amol","Disabled","72:00:00","Scheduling data is not available '
         'in this format.","Weekly","07:30:00","09/10/2026","N/A","MON, FRI","Every 1 week(s)","N/A",'
         '"Disabled","Disabled","Disabled"\r\n')


def test_parse_query_by_position():
    parsed = s.parse_query(QUERY)
    assert parsed == {'task': '\\Playground\\Weekly coordination', 'next_run': '09/10/2026 07:30:00',
                      'status': 'Ready', 'last_run': '05/10/2026 07:30:01', 'last_result': 1}
    german = QUERY.replace('"Ready"', '"Bereit"').replace('"1","LAPTOP', '"-2147216609","LAPTOP')
    parsed = s.parse_query(german)
    assert parsed['status'] == 'Bereit' and parsed['last_result'] == 0x8004131F
    assert s.parse_query('') is None and s.parse_query('"a","b"') is None


def test_result_text():
    assert s.result_text(0) == 'Succeeded'
    assert s.result_text(267011) == 'Not run yet'
    assert s.result_text(3).startswith('Failed: Navisworks')
    assert s.result_text(0x80070005) == 'Failed (code 0x80070005)'
    assert s.result_text(None) == ''


# ---- records, validation, logs ------------------------------------------------------------------


def test_records_save_rename_and_remove():
    previous = paths.redirect(_compat.tmpdir('schedule_records'))
    try:
        assert s.load_all() == []
        s.save(sample())
        s.save(sample(name='Daily health', frequency='daily'))
        assert [x['name'] for x in s.load_all()] == ['Daily health', 'Weekly coordination']
        s.save(sample(name='Weekly coordination 2'), old_name='weekly coordination')
        assert [x['name'] for x in s.load_all()] == ['Daily health', 'Weekly coordination 2']
        assert s.get('DAILY HEALTH')['frequency'] == 'daily'
        assert s.remove('daily health') and not s.remove('daily health')
        assert s.log_folder('A: b').endswith(os.path.join('schedules', 'logs', 'A b'))
        assert s.xml_path('A').endswith(os.path.join('schedules', 'tasks', 'A.xml'))
        assert s.pynavis_exe() == os.path.join(paths.appdata(), 'pyNavis', 'cli', 'pynavis.exe')
    finally:
        paths.redirect(previous)


def test_validate():
    assert s.validate(sample(), model_exists=lambda p: True) == []
    problems = s.validate(sample(name=':', model='', templates=[], time='25:00', days=[]),
                          existing_names=[], runner_exists=False)
    assert problems == ['A schedule needs a name with letters or digits.', 'Pick the model file to open.',
                        'Tick at least one report template.', 'Enter a time between 00:00 and 23:59.',
                        'Pick at least one day.',
                        'The runner script is missing from the Scheduled Reports button folder.']
    assert s.validate(sample(), existing_names=['weekly coordination'])[0] == 'Another schedule already has that name.'
    assert s.validate(sample(model='x.docx'))[0].startswith('The model must be')
    assert s.validate(sample(), model_exists=lambda p: False)[0].startswith('The model file was not found')


def results():
    return [{'report': 'clash_excel', 'title': 'Clash Excel Report', 'template': 'Weekly', 'level': 'success',
             'message': 'Wrote 3 sheets', 'detail': '', 'paths': [r'C:\out\a.xlsx'], 'seconds': 12.5},
            {'report': 'health_check', 'title': 'Model Health Check', 'template': 'Every model', 'level': 'error',
             'message': 'Model Health Check failed', 'detail': 'boom. Details are in the pyNavis log.',
             'paths': [], 'seconds': 0.2}]


def test_log_record_text_and_subject():
    started = datetime.datetime(2026, 10, 9, 7, 30, 0)
    record = s.log_record({'schedule': 'Weekly'}, r'C:\Jobs\Hospital.nwf', started,
                          started + datetime.timedelta(minutes=4), results(), copied=[r'\\srv\a.xlsx'],
                          host='LAPTOP')
    assert record['ok'] == 1 and record['failed'] == 1
    text = s.log_text(record)
    assert text.splitlines()[:3] == ['Scheduled reports: Weekly', r'Model: C:\Jobs\Hospital.nwf',
                                     'Ran: 2026-10-09 07:30:00 to 07:34 on LAPTOP']
    assert 'Clash Excel Report, template "Weekly": Wrote 3 sheets (12.5 s)' in text
    assert '  boom. Details are in the pyNavis log.' in text and 'Copied 1 file to the shared folder.' in text
    assert s.subject(record) == 'Playground reports, Hospital: 1 of 2 failed'
    record['failed'] = 0
    assert s.subject(record) == 'Playground reports, Hospital: 2 of 2 succeeded'
    broken = s.log_record({'schedule': 'W'}, '', started, started, [], problems=['No templates were given.'])
    assert s.subject(broken) == 'Playground reports, no model: the run failed'
    assert s.last_text(broken) == 'Failed: No templates were given.'


def test_write_log_prune_and_last():
    previous = paths.redirect(_compat.tmpdir('schedule_logs'))
    try:
        base = datetime.datetime(2026, 10, 1, 7, 0, 0)
        for n in range(4):
            when = base + datetime.timedelta(days=n)
            record = s.log_record({'schedule': 'Weekly'}, 'm.nwf', when, when, results()[:1 + n % 2])
            path = s.write_log(record, when)
        assert path.endswith('20261004-070000.txt')
        with io.open(path, encoding='utf-8') as handle:
            assert handle.read().startswith('Scheduled reports: Weekly')
        assert s.last_text(s.last_log('Weekly')) == '1 of 2 failed'
        assert s.prune_logs(s.log_folder('Weekly'), keep=2) == 4
        assert len(os.listdir(s.log_folder('Weekly'))) == 4
        assert s.last_log('Nobody') is None
    finally:
        paths.redirect(previous)


def test_copy_results():
    folder = _compat.tmpdir('schedule_copy')
    source = os.path.join(folder, 'report.xlsx')
    with open(source, 'wb') as handle:
        handle.write(b'xlsx')
    target = os.path.join(folder, 'share', 'out')
    copied, problems = s.copy_results([source, os.path.join(folder, 'missing.html')], target)
    assert copied == [os.path.join(target, 'report.xlsx')] and problems == []
    with open(copied[0], 'rb') as handle:
        assert handle.read() == b'xlsx'
    assert s.copy_results([], target) == ([], [])


# ---- the runner side on fakes ----------------------------------------------------------------


def test_run_from_runner_runs_copies_mails_and_logs():
    from namo import reportrunner, sched_mail
    folder = _compat.tmpdir('schedule_runner')
    previous = paths.redirect(folder)
    produced = os.path.join(folder, 'Hospital - Clash.xlsx')
    with open(produced, 'wb') as handle:
        handle.write(b'x')
    calls = {}

    def fake_run(pairs, doc=None, progress=None, folder=None, interactive=False):
        calls.setdefault('run', (pairs, doc, folder, interactive))
        out = results()
        out[0]['paths'] = [produced]
        return out

    def fake_send(profile, subject_text, body, files, password=None):
        calls.setdefault('mail', (profile['name'], subject_text, files))
        return 'smtplib'

    saved = (reportrunner.run_templates, sched_mail.get_profile, sched_mail.send)
    reportrunner.run_templates = fake_run
    sched_mail.get_profile = lambda name: {'name': name, 'to': ['a@b.com']} if name == 'Office' else None
    sched_mail.send = fake_send
    clock = iter([datetime.datetime(2026, 10, 9, 7, 30), datetime.datetime(2026, 10, 9, 7, 41)])
    try:
        argv = ['--schedule', 'Weekly', '--templates', 'clash_excel:Weekly;health_check:Every model',
                '--mail', 'Office', '--folder', r'D:\Out', '--copy-to', os.path.join(folder, 'share')]
        summary = s.run_from_runner(argv, r'C:\Jobs\Hospital.nwf', doc='DOC', clock=lambda: next(clock))
        missing = s.run_from_runner(['--schedule', 'W2', '--templates', 'a:b', '--mail', 'Nope'], 'm.nwf',
                                    doc='DOC')
        bad = s.run_from_runner(['--oops'], 'm.nwf', doc='DOC')
    finally:
        reportrunner.run_templates, sched_mail.get_profile, sched_mail.send = saved
        paths.redirect(previous)
    assert calls['run'] == ([('clash_excel', 'Weekly'), ('health_check', 'Every model')], 'DOC', r'D:\Out', False)
    assert calls['mail'] == ('Office', 'Playground reports, Hospital: 1 of 2 failed', [produced])
    assert summary['ok'] == 1 and summary['failed'] == 1 and summary['files'] == [produced]
    assert summary['mail'] == {'sent': True, 'engine': 'smtplib', 'to': ['a@b.com']}
    assert summary['log'].endswith('20261009-073000.txt') and os.path.isfile(summary['log'])
    assert os.path.isfile(os.path.join(folder, 'share', 'Hospital - Clash.xlsx'))
    assert missing['mail'] == {'sent': False, 'error': 'There is no mail profile called Nope.'}
    assert bad['problems'] == ['Unknown option --oops.']
    assert bad['ok'] == 0 and bad['files'] == []


def test_runner_script_wiring():
    """scheduled_runner.py itself, run with the globals pynavis run gives it."""
    import sys
    path = os.path.join(_compat.ROOT, 'Playground.extension', 'Dev.tab', 'Reports.panel',
                        'Scheduled_Reports.pushbutton', s.RUNNER_FILE)
    folder = _compat.tmpdir('schedule_runner_script')
    log = os.path.join(folder, 'run.txt')
    with io.open(log, 'w', encoding='utf-8') as handle:
        handle.write(u'Scheduled reports: Weekly\n')
    seen = {}

    def fake(argv, model, doc=None, clock=None):
        seen['args'] = (argv, model)
        return {'schedule': 'Weekly', 'ok': 1, 'failed': seen.get('failed', 0), 'problems': [], 'files': [],
                'mail': {}, 'log': log}

    saved = s.run_from_runner
    s.run_from_runner = fake
    with io.open(path, encoding='utf-8') as handle:
        code = compile(handle.read(), path, 'exec')
    try:
        scope = {'__file__': path, '__runner__': True, '__args__': ['--templates', 'a:b'],
                 '__model__': r'C:\Jobs\H.nwf', '__name__': 'pynavis_run'}
        exec(code, scope)
        assert seen['args'] == (['--templates', 'a:b'], r'C:\Jobs\H.nwf')
        assert scope['__result__']['ok'] == 1
        lib = os.path.join(_compat.ROOT, 'Playground.extension', 'lib')
        assert any(os.path.normcase(p) == os.path.normcase(lib) for p in sys.path)
        seen['failed'] = 1
        exit_code = None
        try:
            exec(code, dict(scope))
        except SystemExit as error:
            exit_code = error.code
        assert exit_code == 1
    finally:
        s.run_from_runner = saved

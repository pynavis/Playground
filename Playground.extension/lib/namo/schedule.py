# -*- coding: utf-8 -*-
"""Scheduled Reports: Windows scheduled tasks that open a model in a hidden Navisworks
through the pyNavis headless runner and run Report Templates, then mail or copy the
results.

How a schedule runs (nothing here ever runs a task during development):

    Task Scheduler (task \\Playground\\<name>, current user, only while signed in)
      -> %APPDATA%\\pyNavis\\cli\\pynavis.exe run "<bundle>\\scheduled_runner.py" "<model>"
             --timeout <s> --results "<log folder>\\last-results.json"
             -- --schedule "<name>" --templates "<id>:<name>;<id>:<name>" [--mail "<profile>"]
                [--folder "<folder>"] [--copy-to "<folder>"] [--no-attach]
      -> scheduled_runner.py (checks __runner__) -> schedule.run_from_runner()
         -> reportrunner.run_templates(..., interactive=False) -> run log -> mail / copy

Tasks are registered from XML (schtasks /Create /XML) rather than /SC switches: the
/TR command line of a /SC task is limited to 261 characters (the runner, a model on a
share and a few template names pass that easily), and only the XML can say "run a
missed start as soon as possible", "keep running on battery" and "never two at once".
The task runs only while the user is signed in (InteractiveToken): Navisworks needs a
desktop session, and no password is ever stored with Windows. pynavis.exe is a console
program, so a console window shows while a schedule runs; closing it stops the run.

Pure half (tested on both engines): quote_arg, command_line, split_command_line,
task_name, task_path, encode_templates, decode_templates, runner_args,
parse_runner_args, parse_time, next_start, describe_when, task_xml, schtasks commands,
parse_query, result_text, schedule records, log shaping.
API half: run_schtasks (Popen, no window), status, register, run_from_runner.
"""
import csv
import datetime
import io
import os
import re
import shutil
import socket

from namo import paths, session

FOLDER = 'Playground'
STORE_FORMAT = 'playground-schedules'
DAYS = ('MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN')
DAY_NAMES = {'MON': 'Monday', 'TUE': 'Tuesday', 'WED': 'Wednesday', 'THU': 'Thursday',
             'FRI': 'Friday', 'SAT': 'Saturday', 'SUN': 'Sunday'}
DAY_SHORT = {'MON': 'Mon', 'TUE': 'Tue', 'WED': 'Wed', 'THU': 'Thu', 'FRI': 'Fri',
             'SAT': 'Sat', 'SUN': 'Sun'}
XML_DAY_ORDER = ('SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT')
RUNNER_FILE = 'scheduled_runner.py'
MODEL_EXTENSIONS = ('.nwd', '.nwf', '.nwc', '.ifc', '.ifczip', '.rvt', '.dwg', '.dxf', '.dgn', '.fbx', '.3ds',
                    '.skp', '.step', '.stp', '.iges', '.igs', '.ipt', '.iam', '.sat', '.jt', '.rcp', '.rcs')
LOG_KEEP = 60
CREATE_NO_WINDOW = 0x08000000

# Task Scheduler's own last-result codes, and pynavis.exe's exit codes.
RESULT_TEXT = {
    0: 'Succeeded',
    1: 'Failed: a report, the model or a save failed',
    2: 'Failed: pynavis run was called wrongly',
    3: 'Failed: Navisworks is not installed, attached or would not start',
    0x41300: 'Ready',
    0x41301: 'Running',
    0x41302: 'Disabled',
    0x41303: 'Not run yet',
    0x41304: 'No more runs scheduled',
    0x41306: 'Stopped',
    0x8004131F: 'Skipped: the previous run was still going',
    0xC000013A: 'Stopped: the window was closed',
    0x800710E0: 'Refused by Windows (the computer was busy or the account changed)',
}


# =====================================================================================
# Command lines (Windows argv rules)
# =====================================================================================


def quote_arg(arg):
    """One argument quoted the way CommandLineToArgvW and the C runtime read it back
    (same rules as subprocess.list2cmdline): quotes only when needed, backslashes
    doubled only before a quote."""
    text = '' if arg is None else str(arg)
    if text and not re.search(r'[\s"]', text):
        return text
    out = ['"']
    slashes = 0
    for ch in text:
        if ch == '\\':
            slashes += 1
        elif ch == '"':
            out.append('\\' * (slashes * 2 + 1) + '"')
            slashes = 0
        else:
            out.append('\\' * slashes + ch)
            slashes = 0
    out.append('\\' * (slashes * 2))
    out.append('"')
    return ''.join(out)


def command_line(args):
    return ' '.join(quote_arg(a) for a in args)


def split_command_line(text):
    """The argv a Windows program sees for a command line (CommandLineToArgvW rules for
    every argument after the first): the inverse of command_line(), for tests."""
    args = []
    current = []
    in_quotes = False
    has_token = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            j = i
            while j < len(text) and text[j] == '\\':
                j += 1
            count = j - i
            if j < len(text) and text[j] == '"':
                current.append('\\' * (count // 2))
                if count % 2:
                    current.append('"')
                    i = j + 1
                else:
                    i = j
                has_token = True
                continue
            current.append('\\' * count)
            has_token = True
            i = j
            continue
        if ch == '"':
            if in_quotes and i + 1 < len(text) and text[i + 1] == '"':
                current.append('"')
                i += 2
                continue
            in_quotes = not in_quotes
            has_token = True
            i += 1
            continue
        if ch in ' \t' and not in_quotes:
            if has_token:
                args.append(''.join(current))
                current = []
                has_token = False
            i += 1
            continue
        current.append(ch)
        has_token = True
        i += 1
    if has_token:
        args.append(''.join(current))
    return args


# =====================================================================================
# Names, templates argument, runner arguments
# =====================================================================================


_TASK_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def task_name(name):
    """A Task Scheduler task name from a schedule name: no path or wildcard characters,
    trimmed, at most 120 characters. ValueError when nothing is left."""
    text = _TASK_BAD.sub(' ', str(name or ''))
    text = ' '.join(text.split()).strip(' .')[:120].strip(' .')
    if not text:
        raise ValueError('A schedule needs a name with letters or digits.')
    return text


def task_path(name):
    """'\\Playground\\<task name>'."""
    return '\\%s\\%s' % (FOLDER, task_name(name))


def encode_templates(pairs):
    """'<id>:<name>;<id>:<name>' with ';' inside a name written as ';;'."""
    return ';'.join('%s:%s' % (rid, str(name).replace(';', ';;')) for rid, name in pairs)


def decode_templates(text):
    """[(report id, template name)] from encode_templates text. ValueError with a
    sentence for a part without 'id:'."""
    parts = []
    current = []
    text = str(text or '')
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == ';':
            if text[i:i + 2] == ';;':
                current.append(';')
                i += 2
                continue
            parts.append(''.join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    parts.append(''.join(current))
    out = []
    for part in parts:
        if not part.strip():
            continue
        rid, colon, name = part.partition(':')
        if not colon or not rid.strip() or not name.strip():
            raise ValueError('"%s" is not report:template.' % part)
        out.append((rid.strip(), name.strip()))
    return out


def runner_args(schedule, runner, results_path):
    """The words after 'pynavis.exe' for a schedule (see the module docstring)."""
    timeout = int(schedule.get('timeout_minutes') or 120) * 60
    args = ['run', runner, schedule['model'], '--timeout', str(timeout)]
    if results_path:
        args += ['--results', results_path]
    args += ['--', '--schedule', schedule['name'],
             '--templates', encode_templates([tuple(p) for p in schedule.get('templates') or []])]
    if schedule.get('mail'):
        args += ['--mail', schedule['mail']]
    if schedule.get('folder'):
        args += ['--folder', schedule['folder']]
    if schedule.get('copy_to'):
        args += ['--copy-to', schedule['copy_to']]
    if not schedule.get('attach', True):
        args.append('--no-attach')
    return args


def parse_runner_args(argv):
    """({'schedule', 'templates', 'mail', 'folder', 'copy_to', 'attach'}, [problems])
    from the runner's __args__."""
    options = {'schedule': '', 'templates': [], 'mail': '', 'folder': '', 'copy_to': '', 'attach': True}
    problems = []
    takes = {'--schedule': 'schedule', '--templates': 'templates', '--mail': 'mail',
             '--folder': 'folder', '--copy-to': 'copy_to'}
    words = [str(a) for a in (argv or [])]
    i = 0
    while i < len(words):
        word = words[i]
        if word in takes:
            if i + 1 >= len(words):
                problems.append('%s needs a value.' % word)
                break
            value = words[i + 1]
            if takes[word] == 'templates':
                try:
                    options['templates'] = decode_templates(value)
                except ValueError as error:
                    problems.append(str(error))
            else:
                options[takes[word]] = value
            i += 2
            continue
        if word == '--no-attach':
            options['attach'] = False
        else:
            problems.append('Unknown option %s.' % word)
        i += 1
    if not options['templates'] and not problems:
        problems.append('No templates were given (--templates).')
    return options, problems


# =====================================================================================
# When
# =====================================================================================


def parse_time(text):
    """(hour, minute) from '7:30', '07:30', '730' or '19.05'; ValueError with a sentence."""
    value = str(text or '').strip().replace('.', ':')
    match = re.match(r'^(\d{1,2}):(\d{2})$', value) or re.match(r'^(\d{1,2})(\d{2})$', value)
    if not match:
        raise ValueError('Enter a time as hours and minutes, like 07:30.')
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError('Enter a time between 00:00 and 23:59.')
    return hour, minute


def normalise_days(days):
    """Known day codes in Monday-first order, without repeats."""
    wanted = set(str(d).strip().upper()[:3] for d in (days or []))
    return [d for d in DAYS if d in wanted]


def next_start(now, hour, minute, frequency='daily', days=None):
    """The first run at or after now: today when the time has not passed (and today is
    one of the days), else the next matching day. Used as the trigger's StartBoundary,
    so registering never counts as a missed run."""
    days = normalise_days(days) if frequency == 'weekly' else list(DAYS)
    if not days:
        raise ValueError('Pick at least one day.')
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for offset in range(0, 8):
        moment = candidate + datetime.timedelta(days=offset)
        if moment <= now:
            continue
        if DAYS[moment.weekday()] in days:
            return moment
    raise ValueError('No start found.')


def describe_when(schedule):
    """'Daily at 07:00' or 'Mon, Wed and Fri at 07:00' or 'Weekdays at 06:30'."""
    try:
        hour, minute = parse_time(schedule.get('time'))
    except ValueError:
        return 'Unknown time'
    clock = '%02d:%02d' % (hour, minute)
    if schedule.get('frequency') != 'weekly':
        return 'Daily at %s' % clock
    days = normalise_days(schedule.get('days'))
    if days == list(DAYS[:5]):
        return 'Weekdays at %s' % clock
    if days == list(DAYS):
        return 'Daily at %s' % clock
    names = [DAY_SHORT[d] for d in days]
    if len(names) == 1:
        text = names[0]
    else:
        text = '%s and %s' % (', '.join(names[:-1]), names[-1])
    return '%s at %s' % (text, clock)


# =====================================================================================
# Task XML and schtasks
# =====================================================================================


def _x(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def execution_limit(timeout_minutes):
    """Task-level stop for a run that hangs past the runner's own timeouts: three
    timeouts (open, script, save) plus half an hour, at most three days."""
    minutes = min(int(timeout_minutes or 120) * 3 + 30, 72 * 60)
    return 'PT%dM' % minutes


def task_xml(schedule, command, arguments, user, now, working_dir=None, description=None):
    """The Task Scheduler 1.2 XML for a schedule (UTF-16 text; write it with
    encoding='utf-16'). user is 'DOMAIN\\name'."""
    hour, minute = parse_time(schedule.get('time'))
    frequency = schedule.get('frequency') or 'daily'
    start = next_start(now, hour, minute, frequency, schedule.get('days'))
    if frequency == 'weekly':
        days = normalise_days(schedule.get('days'))
        inner = ''.join('<%s />' % DAY_NAMES[d] for d in XML_DAY_ORDER if d in days)
        calendar = ('<ScheduleByWeek><DaysOfWeek>%s</DaysOfWeek><WeeksInterval>1</WeeksInterval>'
                    '</ScheduleByWeek>' % inner)
    else:
        calendar = '<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>'
    enabled = 'true' if schedule.get('enabled', True) else 'false'
    lines = [
        '<?xml version="1.0" encoding="UTF-16"?>',
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">',
        '  <RegistrationInfo>',
        '    <Date>%s</Date>' % now.replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%S'),
        '    <Author>%s</Author>' % _x(user),
        '    <Description>%s</Description>' % _x(description or 'Playground Scheduled Reports: %s' % schedule['name']),
        '    <URI>%s</URI>' % _x(task_path(schedule['name'])),
        '  </RegistrationInfo>',
        '  <Triggers>',
        '    <CalendarTrigger>',
        '      <StartBoundary>%s</StartBoundary>' % start.strftime('%Y-%m-%dT%H:%M:%S'),
        '      <Enabled>true</Enabled>',
        '      %s' % calendar,
        '    </CalendarTrigger>',
        '  </Triggers>',
        '  <Principals>',
        '    <Principal id="Author">',
        '      <UserId>%s</UserId>' % _x(user),
        '      <LogonType>InteractiveToken</LogonType>',
        '      <RunLevel>LeastPrivilege</RunLevel>',
        '    </Principal>',
        '  </Principals>',
        '  <Settings>',
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>',
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>',
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>',
        '    <AllowHardTerminate>true</AllowHardTerminate>',
        '    <StartWhenAvailable>true</StartWhenAvailable>',
        '    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>',
        '    <IdleSettings>',
        '      <StopOnIdleEnd>false</StopOnIdleEnd>',
        '      <RestartOnIdle>false</RestartOnIdle>',
        '    </IdleSettings>',
        '    <AllowStartOnDemand>true</AllowStartOnDemand>',
        '    <Enabled>%s</Enabled>' % enabled,
        '    <Hidden>false</Hidden>',
        '    <RunOnlyIfIdle>false</RunOnlyIfIdle>',
        '    <WakeToRun>false</WakeToRun>',
        '    <ExecutionTimeLimit>%s</ExecutionTimeLimit>' % execution_limit(schedule.get('timeout_minutes')),
        '    <Priority>7</Priority>',
        '  </Settings>',
        '  <Actions Context="Author">',
        '    <Exec>',
        '      <Command>%s</Command>' % _x(command),
        '      <Arguments>%s</Arguments>' % _x(arguments),
    ]
    if working_dir:
        lines.append('      <WorkingDirectory>%s</WorkingDirectory>' % _x(working_dir))
    lines += ['    </Exec>', '  </Actions>', '</Task>']
    return '\r\n'.join(lines) + '\r\n'


def schtasks_exe():
    root = os.environ.get('SystemRoot') or os.environ.get('windir') or r'C:\Windows'
    return os.path.join(root, 'System32', 'schtasks.exe')


def create_command(name, xml_path):
    return [schtasks_exe(), '/Create', '/TN', task_path(name), '/XML', xml_path, '/F']


def run_command(name):
    return [schtasks_exe(), '/Run', '/TN', task_path(name)]


def delete_command(name):
    return [schtasks_exe(), '/Delete', '/TN', task_path(name), '/F']


def query_command(name):
    return [schtasks_exe(), '/Query', '/TN', task_path(name), '/FO', 'CSV', '/V', '/NH']


def change_command(name, enable):
    return [schtasks_exe(), '/Change', '/TN', task_path(name), '/ENABLE' if enable else '/DISABLE']


def parse_query(text):
    """{'task', 'next_run', 'status', 'last_run', 'last_result' (int or None)} from
    'schtasks /Query /FO CSV /V /NH' output for one task. Columns are read by position
    (headers and dates are in the Windows display language; positions are not). A task
    with several triggers prints several rows: the first is used. None when empty."""
    rows = [r for r in csv.reader(io.StringIO(str(text or ''))) if r and any(c.strip() for c in r)]
    if not rows:
        return None
    row = rows[0]
    if len(row) < 7:
        return None
    try:
        code = int(row[6].strip())
    except ValueError:
        code = None
    if code is not None and code < 0:
        code += 1 << 32
    return {'task': row[1].strip(), 'next_run': row[2].strip(), 'status': row[3].strip(),
            'last_run': row[5].strip(), 'last_result': code}


def result_text(code):
    """Words for a task's last result code."""
    if code is None:
        return ''
    if code in RESULT_TEXT:
        return RESULT_TEXT[code]
    return 'Failed (code 0x%08X)' % (code & 0xFFFFFFFF)


# =====================================================================================
# Records (where schedules, task XML and logs live)
# =====================================================================================


def folder():
    return os.path.join(paths.data_root(), 'schedules')


def store_path():
    return os.path.join(folder(), 'schedules.json')


def log_folder(name):
    return os.path.join(folder(), 'logs', paths.safe_filename(task_name(name)))


def xml_path(name):
    return os.path.join(folder(), 'tasks', paths.safe_filename(task_name(name)) + '.xml')


def results_path(name):
    return os.path.join(log_folder(name), 'last-results.json')


def load_all():
    """[schedule] in natural name order. Never raises."""
    data = paths.load_json(store_path(), {})
    found = data.get('schedules') if isinstance(data, dict) else None
    if not isinstance(found, dict):
        return []
    from namo import naming
    out = [dict(found[k], name=k) for k in found if isinstance(found[k], dict)]
    out.sort(key=lambda s: naming.natural_key(s['name']))
    return out


def get(name):
    for schedule in load_all():
        if schedule['name'].lower() == str(name).strip().lower():
            return schedule
    return None


def save(schedule, old_name=None):
    """Stores a schedule (replacing old_name when renamed). IOError on failure."""
    record = dict(schedule)
    name = record.pop('name')
    target = store_path()
    with paths.FileLock(target):
        data = paths.load_json(target, {})
        found = data.get('schedules') if isinstance(data, dict) else None
        found = dict(found) if isinstance(found, dict) else {}
        for key in list(found):
            if key.lower() in (str(name).lower(), str(old_name or '').lower()):
                del found[key]
        found[name] = record
        paths.write_json(target, {'format': STORE_FORMAT, 'version': 1, 'schedules': found})
    return name


def remove(name):
    """Forgets a schedule record. True when one was removed."""
    target = store_path()
    with paths.FileLock(target):
        data = paths.load_json(target, {})
        found = data.get('schedules') if isinstance(data, dict) else None
        if not isinstance(found, dict):
            return False
        keys = [k for k in found if k.lower() == str(name).lower()]
        for key in keys:
            del found[key]
        if keys:
            paths.write_json(target, {'format': STORE_FORMAT, 'version': 1, 'schedules': found})
        return bool(keys)


def validate(schedule, existing_names=(), runner_exists=True, model_exists=None):
    """Sentences describing what stops a schedule being created."""
    problems = []
    try:
        task_name(schedule.get('name'))
    except ValueError as error:
        problems.append(str(error))
    if str(schedule.get('name') or '').strip().lower() in set(str(n).lower() for n in existing_names):
        problems.append('Another schedule already has that name.')
    model = str(schedule.get('model') or '').strip()
    if not model:
        problems.append('Pick the model file to open.')
    elif os.path.splitext(model)[1].lower() not in MODEL_EXTENSIONS:
        problems.append('The model must be a file Navisworks opens, like an .nwf, .nwd or .nwc.')
    elif model_exists is not None and not model_exists(model):
        problems.append('The model file was not found: %s' % model)
    if not schedule.get('templates'):
        problems.append('Tick at least one report template.')
    try:
        parse_time(schedule.get('time'))
    except ValueError as error:
        problems.append(str(error))
    if schedule.get('frequency') == 'weekly' and not normalise_days(schedule.get('days')):
        problems.append('Pick at least one day.')
    if not runner_exists:
        problems.append('The runner script is missing from the Scheduled Reports button folder.')
    return problems


# =====================================================================================
# Run logs
# =====================================================================================


def log_record(options, model, started, finished, results, mail=None, copied=None, problems=None,
               host=None):
    """The JSON-safe record of one scheduled run."""
    rows = []
    for r in results:
        rows.append({'report': r.get('report'), 'title': r.get('title'), 'template': r.get('template'),
                     'level': r.get('level'), 'message': r.get('message'), 'detail': r.get('detail'),
                     'paths': list(r.get('paths') or []), 'seconds': r.get('seconds')})
    ok = len([r for r in rows if r['level'] in ('success', 'info', 'warning')])
    return {'schedule': options.get('schedule') or '', 'model': model or '',
            'started': started.strftime('%Y-%m-%dT%H:%M:%S'),
            'finished': finished.strftime('%Y-%m-%dT%H:%M:%S'),
            'host': host or '', 'results': rows, 'ok': ok, 'failed': len(rows) - ok,
            'mail': mail or {}, 'copied': list(copied or []), 'problems': list(problems or [])}


def log_text(record):
    """The run log as plain text (also the mail body)."""
    lines = ['Scheduled reports: %s' % (record.get('schedule') or 'Playground'),
             'Model: %s' % (record.get('model') or 'none'),
             'Ran: %s to %s%s' % (record.get('started', '').replace('T', ' '),
                                  record.get('finished', '')[11:16],
                                  (' on %s' % record['host']) if record.get('host') else ''),
             '']
    for problem in record.get('problems') or []:
        lines.append('Problem: %s' % problem)
    if record.get('problems'):
        lines.append('')
    for row in record.get('results') or []:
        seconds = row.get('seconds')
        timing = ' (%.1f s)' % seconds if isinstance(seconds, (int, float)) else ''
        lines.append('%s, template "%s": %s%s' % (row.get('title') or row.get('report'),
                                                    row.get('template'), row.get('message') or '', timing))
        if row.get('detail') and row.get('level') in ('error', 'warning', 'info'):
            lines.append('  %s' % row['detail'])
        for path in row.get('paths') or []:
            lines.append('  %s' % path)
    copied = record.get('copied') or []
    if copied:
        lines.append('')
        lines.append('Copied %d %s to the shared folder.' % (len(copied), 'file' if len(copied) == 1 else 'files'))
    mail = record.get('mail') or {}
    if mail.get('error'):
        lines.append('')
        lines.append('Mail was not sent: %s' % mail['error'])
    return '\n'.join(lines) + '\n'


def subject(record):
    """'Playground reports, Hospital: 3 of 3 succeeded' (or how many failed)."""
    model = os.path.splitext(os.path.basename(record.get('model') or ''))[0] or 'no model'
    total = len(record.get('results') or [])
    failed = record.get('failed') or 0
    if record.get('problems') and not total:
        return 'Playground reports, %s: the run failed' % model
    if failed:
        return 'Playground reports, %s: %d of %d failed' % (model, failed, total)
    return 'Playground reports, %s: %d of %d succeeded' % (model, total - failed, total)


def write_log(record, when=None):
    """Writes <logs>\\<schedule>\\<yyyymmdd-HHMMSS>.json and .txt and prunes the oldest
    beyond LOG_KEEP runs. Returns the .txt path."""
    when = when or datetime.datetime.now()
    target = log_folder(record.get('schedule') or 'Unnamed')
    paths.ensure_dir(target)
    stem = os.path.join(target, when.strftime('%Y%m%d-%H%M%S'))
    paths.write_json(stem + '.json', record)
    paths.atomic_write_text(stem + '.txt', log_text(record).replace('\n', '\r\n'))
    prune_logs(target)
    return stem + '.txt'


def prune_logs(target, keep=LOG_KEEP):
    try:
        stems = sorted(set(os.path.splitext(n)[0] for n in os.listdir(target)
                           if re.match(r'^\d{8}-\d{6}\.(json|txt)$', n)))
    except OSError:
        return 0
    removed = 0
    for stem in stems[:-keep] if len(stems) > keep else []:
        for ext in ('.json', '.txt'):
            try:
                os.remove(os.path.join(target, stem + ext))
                removed += 1
            except OSError:
                pass
    return removed


def last_log(name):
    """The newest run record of a schedule, or None."""
    target = log_folder(name)
    try:
        names = sorted(n for n in os.listdir(target) if re.match(r'^\d{8}-\d{6}\.json$', n))
    except OSError:
        return None
    if not names:
        return None
    return paths.load_json(os.path.join(target, names[-1]), None)


def last_text(record):
    """'3 of 3 succeeded' / '1 of 3 failed' for the list, from a run record."""
    if not record:
        return ''
    total = len(record.get('results') or [])
    failed = record.get('failed') or 0
    if record.get('problems') and not total:
        return 'Failed: %s' % record['problems'][0]
    if failed:
        return '%d of %d failed' % (failed, total)
    return '%d of %d succeeded' % (total, total)


# =====================================================================================
# API half
# =====================================================================================


def pynavis_exe():
    """%APPDATA%\\pyNavis\\cli\\pynavis.exe (the pyNavis command line runner)."""
    return os.path.join(paths.appdata(), 'pyNavis', 'cli', 'pynavis.exe')


def missing_runner_message():
    return ('Scheduled Reports needs pyNavis with the command line runner (pynavis.exe in '
            '%APPDATA%\\pyNavis\\cli). Update pyNavis, then try again.')


def old_runner_message():
    return ('The pynavis.exe in %APPDATA%\\pyNavis\\cli is from a pyNavis without the "pynavis run" '
            'command, so a schedule would fail every time. Update pyNavis, then try again.')


def help_command(exe=None):
    """'pynavis.exe run --help': prints the usage and exits 0 when this pynavis.exe has the
    run command (an older one prints its own usage and exits 2). It never starts
    Navisworks: --help returns before anything is looked up."""
    return [exe or pynavis_exe(), 'run', '--help']


def runner_state(exe=None, exists=None, probe=None):
    """'ok', 'missing' (no pynavis.exe) or 'old' (a pynavis.exe without `run`). exists(path)
    and probe(args) -> (exit code, output) are test seams. A probe that cannot be started
    counts as 'ok': the task itself will say what is wrong."""
    exe = exe or pynavis_exe()
    if not (exists or os.path.isfile)(exe):
        return 'missing'
    try:
        code, _output = (probe or run_schtasks)(help_command(exe))
    except Exception as error:
        session.log('warning', 'could not ask pynavis.exe for its run command: %s' % error)
        return 'ok'
    return 'ok' if code == 0 else 'old'


def runner_problem(state):
    """(title, sentence) for a runner state that stops schedules, else None."""
    if state == 'missing':
        return ('pyNavis command line runner not found', missing_runner_message())
    if state == 'old':
        return ('This pyNavis cannot run scripts from the command line', old_runner_message())
    return None


def _decode(data):
    """schtasks prints in the console (OEM) code page."""
    if isinstance(data, str):
        return data
    try:
        from System.Globalization import CultureInfo
        from System.Text import Encoding
        from System import Array, Byte
        code_page = CultureInfo.CurrentCulture.TextInfo.OEMCodePage
        return Encoding.GetEncoding(code_page).GetString(Array[Byte](bytearray(data)))
    except Exception:
        pass
    for encoding in ('mbcs', 'cp437', 'latin-1'):
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode('latin-1', 'replace')


def run_schtasks(args, timeout=60):
    """(exit code, output text) of schtasks.exe (or another console program: args[0]) with
    no console window."""
    import subprocess
    process = subprocess.Popen(command_line(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    output, _ = process.communicate()
    return process.returncode, _decode(output or b'').strip()


def current_user():
    """'DOMAIN\\name' of the signed-in Windows user as Windows itself spells it (the account
    the task is registered for); the environment's spelling when .NET cannot say."""
    try:
        from System.Security.Principal import WindowsIdentity
        name = str(WindowsIdentity.GetCurrent().Name or '')
        if name:
            return name
    except Exception:
        pass
    domain =os.environ.get('USERDOMAIN') or os.environ.get('COMPUTERNAME') or ''
    user = os.environ.get('USERNAME') or ''
    return ('%s\\%s' % (domain, user)) if domain else user


def register(schedule, runner):
    """Writes the task XML and registers the task (replacing one of the same name).
    Returns (ok, message)."""
    exe = pynavis_exe()
    problem = runner_problem(runner_state(exe))
    if problem is not None:
        return False, problem[1]
    result_file = results_path(schedule['name'])
    paths.ensure_dir(os.path.dirname(result_file))
    args = runner_args(schedule, runner, result_file)
    arguments = command_line(args)
    # <Command> heads the command line Task Scheduler builds: a pynavis.exe under a user
    # folder with a space (C:\Users\Jo Smith\...) is quoted, the form the Task
    # Scheduler window itself writes when you browse to a program, so the path is never
    # split into the program and stray first arguments. WorkingDirectory stays unquoted
    # (quotes there stop the task from starting).
    text = task_xml(schedule, quote_arg(exe), arguments, current_user(), datetime.datetime.now(),
                    working_dir=log_folder(schedule['name']))
    target = xml_path(schedule['name'])
    paths.ensure_dir(os.path.dirname(target))
    paths.atomic_write_bytes(target, text.encode('utf-16'))
    code, output = run_schtasks(create_command(schedule['name'], target))
    if code != 0:
        return False, output or 'schtasks.exe stopped with code %d.' % code
    return True, output


def status(schedule):
    """{'next_run', 'status', 'last_run', 'last_result', 'result_text', 'exists'} from
    Task Scheduler for one schedule (exists False when the task is gone)."""
    code, output = run_schtasks(query_command(schedule['name']))
    if code != 0:
        return {'exists': False, 'next_run': '', 'status': 'Missing in Task Scheduler', 'last_run': '',
                'last_result': None, 'result_text': ''}
    parsed = parse_query(output) or {}
    parsed['exists'] = True
    parsed['result_text'] = result_text(parsed.get('last_result'))
    return parsed


# ---- the runner side ------------------------------------------------------------------


def copy_results(file_paths, target):
    """(copied paths, problems): each file copied into target (replacing a file of the
    same name, so a fixed-name report always holds the latest)."""
    copied = []
    problems = []
    if not file_paths:
        return copied, problems
    try:
        paths.ensure_dir(target)
    except OSError as error:
        return copied, ['Could not reach %s: %s' % (target, error)]
    for source in file_paths:
        if not os.path.isfile(source):
            continue
        destination = os.path.join(target, os.path.basename(source))
        try:
            shutil.copy2(source, destination)
            copied.append(destination)
        except (IOError, OSError) as error:
            problems.append('Could not copy %s: %s' % (os.path.basename(source), error))
    return copied, problems


def run_from_runner(argv, model, doc=None, clock=None):
    """What scheduled_runner.py does under pynavis run: parse the arguments, run the
    templates without dialogs, copy and mail the results, write the run log. Returns a
    JSON-friendly summary (the script's __result__). Never raises; never opens a window."""
    from namo import reportrunner
    clock = clock or datetime.datetime.now
    started = clock()
    options, problems = parse_runner_args(argv)
    results = []
    if not problems and doc is None:
        try:
            from pynavis._api import Application
            doc = Application.ActiveDocument
        except Exception as error:
            problems.append('Navisworks has no document open: %s' % error)
    if not problems:
        try:
            results = reportrunner.run_templates(options['templates'], doc=doc, progress=None,
                                                 folder=options['folder'] or None, interactive=False)
        except Exception as error:
            problems.append('The run stopped: %s' % (str(error) or type(error).__name__))
            session.log('error', 'scheduled run stopped: %s' % error)
    files = []
    for result in results:
        for path in result.get('paths') or []:
            if path not in files:
                files.append(path)
    copied = []
    if options['copy_to'] and files:
        copied, copy_problems = copy_results(files, options['copy_to'])
        problems.extend(copy_problems)
    try:
        host = socket.gethostname()
    except Exception:
        host = ''
    record = log_record(options, model, started, clock(), results, copied=copied, problems=problems,
                        host=host)
    if options['mail']:
        record['mail'] = _mail(options, record, files)
    try:
        record['log'] = write_log(record, started)
    except Exception as error:
        session.log('error', 'could not write the scheduled run log: %s' % error)
    return {'schedule': record['schedule'], 'ok': record['ok'], 'failed': record['failed'],
            'problems': record['problems'], 'files': files, 'mail': record.get('mail') or {},
            'log': record.get('log') or ''}


def _mail(options, record, files):
    try:
        from namo import sched_mail
        profile = sched_mail.get_profile(options['mail'])
        if profile is None:
            return {'sent': False, 'error': 'There is no mail profile called %s.' % options['mail']}
        attachments = files if options.get('attach', True) else []
        engine = sched_mail.send(profile, subject(record), log_text(record), attachments)
        return {'sent': True, 'engine': engine, 'to': profile.get('to') or []}
    except Exception as error:
        session.log('error', 'scheduled report mail failed: %s' % error)
        return {'sent': False, 'error': str(error) or type(error).__name__}

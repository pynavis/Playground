# -*- coding: utf-8 -*-
"""The Scheduled Reports windows: the list of schedules, the schedule form and the mail
profiles. Pure helpers (rows, form fields, schedule from form values) are tested; the
windows are built in smoke tests and only shown inside Navisworks.
"""
import datetime
import os

from namo import naming, schedule

MODEL_FILTER = ('Navisworks files (*.nwd;*.nwf;*.nwc)|*.nwd;*.nwf;*.nwc|'
                'Other models (*.ifc;*.rvt;*.dwg)|*.ifc;*.rvt;*.dwg|All files (*.*)|*.*')
HEADERS = ['Schedule', 'When', 'Model', 'Reports', 'Next run', 'Last run', 'Last result']
PROFILE_HEADERS = ['Profile', 'Server', 'Security', 'From', 'To']
DAY_OPTIONS = [(schedule.DAY_SHORT[d], d) for d in schedule.DAYS]
NO_MAIL = ''


# =====================================================================================
# Pure
# =====================================================================================


def row_for(item, state=None, last=None):
    """Table cells for one schedule; state from schedule.status(), last a run record."""
    state = state or {}
    model = os.path.basename(str(item.get('model') or ''))
    count = len(item.get('templates') or [])
    when = schedule.describe_when(item)
    if not item.get('enabled', True):
        when += ' (off)'
    if last:
        result = schedule.last_text(last)
    else:
        result = state.get('result_text') or ''
    if state and not state.get('exists', True):
        result = 'Missing in Task Scheduler: edit and save to create it again'
    return [item['name'], when, model, count, state.get('next_run') or '', state.get('last_run') or '', result]


def template_options(rows):
    """[(label, (report id, name))] for the available templates, catalog order."""
    return [('%s: %s' % (r['title'], r['name']), (r['report'], r['name'])) for r in rows if r['available']]


def schedule_fields(item, options, profiles, existing, default_model=''):
    """namo.ui.form fields for a schedule (item None for a new one)."""
    item = item or {}
    taken = set(str(n).lower() for n in existing)

    def name_check(value):
        if str(value).strip().lower() in taken:
            return 'Another schedule already has that name.'
        try:
            schedule.task_name(value)
        except ValueError as error:
            return str(error)
        return None

    def time_check(value):
        try:
            schedule.parse_time(value)
        except ValueError as error:
            return str(error)
        return None

    ticked = [tuple(p) for p in item.get('templates') or []]
    mail_options = [('Do not send mail', NO_MAIL)] + [(p, p) for p in profiles]
    mail_default = item.get('mail') if item.get('mail') in profiles else NO_MAIL
    fields = [
        {'kind': 'text', 'key': 'name', 'label': 'Name', 'default': item.get('name') or '',
         'required': True, 'validate': name_check, 'placeholder': 'Weekly coordination'},
        {'kind': 'file_open', 'key': 'model', 'label': 'Model to open',
         'default': item.get('model') or default_model, 'required': True, 'filter': MODEL_FILTER,
         'hint': 'Opened in a hidden Navisworks for each run. Use a path every run can reach.'},
        {'kind': 'multi', 'key': 'templates', 'label': 'Report templates', 'options': options,
         'default': ticked, 'required': True},
        {'kind': 'radio', 'key': 'frequency', 'label': 'Repeat', 'inline': True,
         'options': [('Daily', 'daily'), ('Weekly', 'weekly')],
         'default': item.get('frequency') or 'weekly', 'fallback': 'weekly'},
        {'kind': 'multi', 'key': 'days', 'label': 'On', 'options': DAY_OPTIONS,
         'default': schedule.normalise_days(item.get('days')) or list(schedule.DAYS[:5]),
         'enabled_if': ('frequency', 'weekly')},
        {'kind': 'text', 'key': 'time', 'label': 'At', 'default': item.get('time') or '07:00',
         'required': True, 'validate': time_check, 'hint': '24 hour clock, like 07:30.'},
        {'kind': 'int', 'key': 'timeout_minutes', 'label': 'Give up after',
         'default': int(item.get('timeout_minutes') or 120), 'min': 5, 'max': 1440, 'suffix': 'minutes',
         'required': True, 'hint': 'For each step: opening the model, then running the reports.'},
        {'kind': 'separator'},
        {'kind': 'folder', 'key': 'folder', 'label': 'Save reports in', 'default': item.get('folder') or '',
         'hint': 'Blank: where each template saves its file.'},
        {'kind': 'folder', 'key': 'copy_to', 'label': 'Also copy them to', 'default': item.get('copy_to') or '',
         'hint': 'Blank: no copy. A project share works well here.'},
        {'kind': 'choice', 'key': 'mail', 'label': 'Mail the results with', 'options': mail_options,
         'default': mail_default, 'fallback': None,
         'hint': 'Mail profiles are set up with Mail settings in the Scheduled Reports window.'},
        {'kind': 'check', 'key': 'attach', 'label': 'Attach the files (up to 15 MB in total)',
         'default': bool(item.get('attach', True))},
        {'kind': 'check', 'key': 'enabled', 'label': 'Turned on', 'default': bool(item.get('enabled', True))},
    ]
    return fields


def schedule_from(values, runner, now=None):
    """The schedule record from the form's values."""
    now = now or datetime.datetime.now()
    hour, minute = schedule.parse_time(values.get('time'))
    return {
        'name': naming.sanitize(values.get('name') or ''),
        'model': str(values.get('model') or '').strip(),
        'templates': [list(p) for p in values.get('templates') or []],
        'frequency': values.get('frequency') or 'weekly',
        'days': schedule.normalise_days(values.get('days')) if values.get('frequency') == 'weekly' else [],
        'time': '%02d:%02d' % (hour, minute),
        'timeout_minutes': int(values.get('timeout_minutes') or 120),
        'folder': str(values.get('folder') or '').strip(),
        'copy_to': str(values.get('copy_to') or '').strip(),
        'mail': values.get('mail') or '',
        'attach': bool(values.get('attach', True)),
        'enabled': bool(values.get('enabled', True)),
        'runner': runner,
        'updated': now.strftime('%Y-%m-%dT%H:%M:%S'),
    }


def profile_fields(profile, existing):
    from namo import sched_mail
    profile = sched_mail.normalise_profile(profile or {}) if profile else {}
    taken = set(str(n).lower() for n in existing)

    def name_check(value):
        if str(value).strip().lower() in taken:
            return 'Another mail profile already has that name.'
        return None

    def sender_check(value):
        return None if sched_mail.is_address(value) else 'Enter an address, like reports@example.com.'

    def to_check(value):
        good, bad = sched_mail.parse_addresses(value)
        if bad:
            return 'Not an address: %s' % bad[0]
        if not good:
            return 'Enter at least one address.'
        return None

    return [
        {'kind': 'text', 'key': 'name', 'label': 'Profile name', 'default': profile.get('name') or '',
         'required': True, 'validate': name_check, 'placeholder': 'Office 365'},
        {'kind': 'text', 'key': 'server', 'label': 'SMTP server', 'default': profile.get('server') or '',
         'required': True, 'placeholder': 'smtp.office365.com'},
        {'kind': 'radio', 'key': 'security', 'label': 'Security', 'inline': True,
         'options': [(label, value) for value, label in sched_mail.SECURITY],
         'default': profile.get('security') or 'starttls', 'fallback': 'starttls'},
        {'kind': 'int', 'key': 'port', 'label': 'Port', 'default': profile.get('port') or 587, 'min': 1,
         'max': 65535, 'required': True, 'hint': 'Usually 587 with STARTTLS, 465 with SSL/TLS.'},
        {'kind': 'text', 'key': 'sender', 'label': 'From', 'default': profile.get('sender') or '',
         'required': True, 'validate': sender_check},
        {'kind': 'textarea', 'key': 'to', 'label': 'To', 'rows': 3,
         'default': '\n'.join(profile.get('to') or []), 'required': True, 'validate': to_check,
         'hint': 'One address per line.'},
        {'kind': 'text', 'key': 'username', 'label': 'Sign in as', 'default': profile.get('username') or '',
         'hint': 'Blank for a server that needs no sign-in. The password is asked next.'},
        {'kind': 'radio', 'key': 'engine', 'label': 'Send with', 'inline': True,
         'options': [(label, value) for value, label in sched_mail.ENGINES],
         'default': profile.get('engine') or 'auto', 'fallback': 'auto'},
    ]


def profile_from(values, sealed_password):
    from namo import sched_mail
    to, _bad = sched_mail.parse_addresses(values.get('to'))
    return {'name': naming.sanitize(values.get('name') or ''), 'server': str(values.get('server') or '').strip(),
            'port': int(values.get('port') or 587), 'security': values.get('security') or 'starttls',
            'sender': str(values.get('sender') or '').strip(), 'to': to,
            'username': str(values.get('username') or '').strip(), 'password': sealed_password or '',
            'engine': values.get('engine') or 'auto'}


def profile_row(profile):
    from namo import sched_mail
    security = dict(sched_mail.SECURITY).get(profile.get('security'), '')
    return [profile['name'], '%s:%s' % (profile.get('server'), profile.get('port')), security.split(' (')[0],
            profile.get('sender') or '', ', '.join(profile.get('to') or [])]


# =====================================================================================
# Windows
# =====================================================================================


def _toast(level, message, detail=None):
    from pynavis import toast
    toast.show(level, message, detail)


def _doc_file(doc):
    try:
        name = str(doc.FileName or '') if doc is not None else ''
    except Exception:
        name = ''
    return name if name and os.path.isfile(name) else ''


def open_window(doc, runner):
    """The Scheduled Reports window (modal)."""
    from namo import reportrunner, ui
    from pynavis import forms

    holder = {}

    def gather():
        items = schedule.load_all()
        rows = []
        for item in items:
            state = schedule.status(item)
            rows.append({'cells': row_for(item, state, schedule.last_log(item['name'])), 'value': item['name']})
        return items, rows

    def runner_state():
        # Asked once per window: 'pynavis.exe run --help' (it never starts Navisworks).
        if 'runner_state' not in holder:
            holder['runner_state'] = schedule.runner_state()
        return holder['runner_state']

    def status_line(items):
        state = runner_state()
        if state == 'missing':
            return 'pynavis.exe was not found, so schedules cannot run. Update pyNavis first.'
        if state == 'old':
            return 'This pyNavis has no "pynavis run" command, so schedules cannot run. Update pyNavis first.'
        if not items:
            return 'No schedules yet. New makes one; it runs while you are signed in to Windows.'
        return '%d %s in Task Scheduler under Playground. They run while you are signed in to Windows.' % (
            len(items), 'schedule' if len(items) == 1 else 'schedules')

    def refresh():
        items, rows = gather()
        holder['win'].Tag.update(rows, status_line(items))

    def runner_ok():
        problem = schedule.runner_problem(runner_state())
        if problem is not None:
            _toast('error', problem[0], problem[1])
            return False
        if not runner or not os.path.isfile(runner):
            _toast('error', 'The runner script is missing',
                   'scheduled_runner.py should be in the Scheduled Reports button folder. Reinstall Playground.')
            return False
        return True

    def edit(item):
        if not runner_ok():
            return
        rows = reportrunner.catalog()
        options = template_options(rows)
        if not options:
            _toast('info', 'No report templates to schedule', 'Make one with Report Templates first.')
            return
        from namo import sched_mail
        existing = [s['name'] for s in schedule.load_all()
                    if item is None or s['name'].lower() != item['name'].lower()]
        fields = schedule_fields(item, options, sched_mail.profile_names(), existing, _doc_file(doc))

        def check(values):
            problems = {}
            chosen = [tuple(p) for p in values.get('templates') or []]
            found = reportrunner.schedule_problems(chosen, rows)
            if found:
                problems['templates'] = found[0]
            if values.get('frequency') == 'weekly' and not values.get('days'):
                problems['days'] = 'Pick at least one day.'
            return problems or None

        answer = ui.form('Edit schedule' if item else 'New schedule', fields, validate=check, ok='Save',
                         width=600, intro='A Windows scheduled task opens the model in a hidden Navisworks '
                                          'and runs the templates, with no dialogs.')
        if answer is None:
            return
        record = schedule_from(answer, runner)
        problems = schedule.validate(record, existing, os.path.isfile(runner))
        if problems:
            _toast('error', 'The schedule was not saved', problems[0])
            return
        ok, message = schedule.register(record, runner)
        if not ok:
            _toast('error', 'Could not create the scheduled task', message)
            return
        if item is not None and item['name'].lower() != record['name'].lower():
            schedule.run_schtasks(schedule.delete_command(item['name']))
            try:
                os.remove(schedule.xml_path(item['name']))
            except OSError:
                pass
        schedule.save(record, item['name'] if item else None)
        refresh()
        _toast('success', 'Scheduled %s' % record['name'], '%s, %d %s.' % (
            schedule.describe_when(record), len(record['templates']),
            'template' if len(record['templates']) == 1 else 'templates'))

    def on_new(_values):
        edit(None)

    def selected_item(values):
        for value in values:
            item = schedule.get(value)
            if item is not None:
                return item
        return None

    def on_edit(values):
        item = selected_item(values)
        if item is not None:
            edit(item)

    def on_run(values):
        item = selected_item(values)
        if item is None or not runner_ok():
            return
        if not forms.confirm('Run %s now? A hidden Navisworks opens %s and runs %d %s. It uses a '
                             'Navisworks licence while it runs.' % (
                                 item['name'], os.path.basename(item.get('model') or ''),
                                 len(item.get('templates') or []),
                                 'template' if len(item.get('templates') or []) == 1 else 'templates'),
                             'Run now'):
            return
        code, output = schedule.run_schtasks(schedule.run_command(item['name']))
        if code != 0:
            _toast('error', 'Could not start %s' % item['name'], output or 'Edit and save it to create the task again.')
            return
        _toast('success', 'Started %s' % item['name'], 'The results go to the run log%s.' % (
            ' and by mail' if item.get('mail') else ''))
        ui.run_later(lambda: _safe_refresh(refresh), 3000)

    def on_toggle(values):
        item = selected_item(values)
        if item is None:
            return
        turn_on = not item.get('enabled', True)
        code, output = schedule.run_schtasks(schedule.change_command(item['name'], turn_on))
        if code != 0:
            _toast('error', 'Could not change %s' % item['name'], output)
            return
        item['enabled'] = turn_on
        schedule.save(item)
        refresh()
        _toast('success', '%s is %s' % (item['name'], 'on' if turn_on else 'off'))

    def on_delete(values):
        item = selected_item(values)
        if item is None:
            return
        if not forms.confirm('Delete the schedule %s? Its scheduled task is removed; reports already '
                             'written and the run logs stay.' % item['name'], 'Delete schedule'):
            return
        code, output = schedule.run_schtasks(schedule.delete_command(item['name']))
        state_missing = code != 0 and not schedule.status(item).get('exists')
        if code != 0 and not state_missing:
            _toast('error', 'Could not delete the scheduled task', output)
            return
        schedule.remove(item['name'])
        try:
            os.remove(schedule.xml_path(item['name']))
        except OSError:
            pass
        refresh()
        _toast('success', 'Deleted %s' % item['name'])

    def on_logs(values):
        from namo import paths
        item = selected_item(values)
        target = schedule.log_folder(item['name']) if item else schedule.folder()
        ui.open_path(paths.ensure_dir(target))

    def on_mail(_values):
        open_profiles()

    actions = [
        {'label': 'New', 'fn': on_new, 'needs_selection': False, 'primary': True},
        {'label': 'Edit', 'fn': on_edit},
        {'label': 'Run now', 'fn': on_run},
        {'label': 'On or off', 'fn': on_toggle},
        {'label': 'Delete', 'fn': on_delete},
        {'label': 'Logs', 'fn': on_logs, 'needs_selection': False},
        {'label': 'Mail settings', 'fn': on_mail, 'needs_selection': False},
    ]
    items, rows = gather()
    win = ui.build_table('Scheduled reports', HEADERS, rows, actions=actions,
                         on_open=lambda value: on_edit([value]), status=status_line(items),
                         width=1040, height=520)
    holder['win'] = win
    ui.show_modal(win)
    return win


def _wait_cursor(on):
    """The busy cursor over Playground's windows while a blocking call runs. Never raises."""
    try:
        from System.Windows.Input import Cursors, Mouse
        Mouse.OverrideCursor = Cursors.Wait if on else None
    except Exception:
        pass


def _safe_refresh(fn):
    try:
        fn()
    except Exception:
        pass


def open_profiles():
    """The mail profiles window (modal)."""
    from namo import sched_mail, ui

    holder = {}

    def rows():
        profiles = sched_mail.load_profiles()
        return [{'cells': profile_row(profiles[n]), 'value': n} for n in sched_mail.profile_names()]

    def refresh():
        holder['win'].Tag.update(rows())

    def edit(profile):
        names = [n for n in sched_mail.profile_names()
                 if profile is None or n.lower() != profile['name'].lower()]
        answer = ui.form('Mail profile', profile_fields(profile, names), ok='Save', width=520,
                         intro='How Scheduled Reports sends its results.')
        if answer is None:
            return
        sealed = profile.get('password') if profile else ''
        if str(answer.get('username') or '').strip():
            typed = sched_mail.ask_password('Mail password', 'Password for %s on %s' % (
                answer['username'], answer['server']), keep_hint=bool(profile and sealed))
            if typed is None:
                return
            if typed:
                try:
                    sealed = sched_mail.protect(typed)
                except RuntimeError as error:
                    _toast('error', 'Could not save the password', str(error))
                    return
        else:
            sealed = ''
        record = profile_from(answer, sealed)
        problems = sched_mail.profile_problems(record)
        if problems:
            _toast('error', 'The mail profile was not saved', problems[0])
            return
        sched_mail.save_profile(record, profile['name'] if profile else None)
        refresh()
        _toast('success', 'Saved the mail profile %s' % record['name'])

    def chosen(values):
        for value in values:
            found = sched_mail.get_profile(value)
            if found is not None:
                return found
        return None

    def on_test(values):
        profile = chosen(values)
        if profile is None:
            return
        body = 'This is a test from Playground Scheduled Reports on %s.\n' % datetime.datetime.now().strftime(
            '%Y-%m-%d %H:%M')
        # Sending blocks until the server answers (up to a minute): show the wait cursor.
        _wait_cursor(True)
        try:
            engine = sched_mail.send(profile, 'Playground test mail', body, [])
        except Exception as error:
            _toast('error', 'The test mail was not sent', str(error) or type(error).__name__)
            return
        finally:
            _wait_cursor(False)
        _toast('success', 'Sent a test mail to %s' % ', '.join(profile['to']),
               'Sent with %s.' % ('.NET SmtpClient' if engine == 'dotnet' else 'Python smtplib'))

    def on_delete(values):
        from pynavis import forms
        profile = chosen(values)
        if profile is None:
            return
        users = [s['name'] for s in schedule.load_all() if str(s.get('mail') or '').lower() == profile['name'].lower()]
        note = (' %d schedule%s use%s it and will stop mailing.' % (
            len(users), '' if len(users) == 1 else 's', 's' if len(users) == 1 else '')) if users else ''
        if not forms.confirm('Delete the mail profile %s?%s' % (profile['name'], note), 'Delete mail profile'):
            return
        sched_mail.delete_profile(profile['name'])
        refresh()
        _toast('success', 'Deleted the mail profile %s' % profile['name'])

    actions = [
        {'label': 'New', 'fn': lambda values: edit(None), 'needs_selection': False},
        {'label': 'Edit', 'fn': lambda values: edit(chosen(values)) if chosen(values) else None},
        {'label': 'Delete', 'fn': on_delete},
        {'label': 'Send test', 'fn': on_test, 'primary': True},
    ]
    win = ui.build_table('Mail settings', PROFILE_HEADERS, rows(), actions=actions,
                         on_open=lambda value: edit(sched_mail.get_profile(value)),
                         status='Passwords are encrypted for your Windows account on this computer.',
                         width=820, height=420)
    holder['win'] = win
    ui.show_modal(win)
    return win

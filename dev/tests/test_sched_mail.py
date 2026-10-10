# -*- coding: utf-8 -*-
"""namo.sched_mail: addresses, profiles, attachments, the message, DPAPI (IronPython),
and a real smtplib exchange with a loopback SMTP responder on 127.0.0.1 (both engines;
nothing leaves the computer)."""
import email
import os
import socket
import threading

import _compat

from namo import paths, sched_mail as sm


def test_parse_addresses():
    good, bad = sm.parse_addresses('a@b.com; Amol Shah <amol@x.co.uk>\nA@B.com, nope, c@d')
    assert good == ['a@b.com', 'amol@x.co.uk'] and bad == ['nope', 'c@d']
    assert sm.parse_addresses('') == ([], [])
    assert sm.is_address('reports@example.com') and not sm.is_address('reports@')


def test_normalise_and_problems():
    p = sm.normalise_profile({'security': 'ssl', 'port': '', 'to': 'a@b.com\nc@d.com', 'engine': 'weird'})
    assert p['port'] == 465 and p['to'] == ['a@b.com', 'c@d.com'] and p['engine'] == 'auto'
    assert sm.normalise_profile({'security': 'bogus'})['security'] == 'starttls'
    good = {'name': 'Office', 'server': 'smtp.x.com', 'port': 587, 'sender': 'r@x.com', 'to': ['a@b.com']}
    assert sm.profile_problems(good) == []
    problems = sm.profile_problems({'name': '', 'server': '', 'port': 70000, 'sender': 'x', 'to': []})
    assert problems == ['A mail profile needs a name.', 'Enter the SMTP server, like smtp.office365.com.',
                        'Enter a port between 1 and 65535.', 'Enter the address the mail comes from.',
                        'Enter at least one address to send to.']
    assert sm.profile_problems(dict(good, engine='dotnet', security='ssl'))[0].startswith('.NET SmtpClient')


def test_plan_attachments():
    sizes = {'a': 5, 'b': 8, 'c': 3}

    def size_of(path):
        if path not in sizes:
            raise OSError('missing')
        return sizes[path]
    assert sm.plan_attachments(['a', 'b', 'gone', 'c'], limit=10, size_of=size_of) == (['a', 'c'], ['b'])


def test_message_and_body():
    folder = _compat.tmpdir('sched_mail_message')
    path = os.path.join(folder, 'Hospital - Clash report.xlsx')
    with open(path, 'wb') as handle:
        handle.write(b'PK\x03\x04data')
    body = sm.body_with_attachments('Report body', [path], [r'C:\big.html'])
    assert 'Attached: Hospital - Clash report.xlsx.' in body
    assert 'Not attached (over 15 MB in total), find them at:\n  C:\\big.html' in body
    assert body.rstrip().endswith('Sent by Playground Scheduled Reports.')
    profile = {'sender': 'reports@x.com', 'to': ['a@b.com', 'c@d.com']}
    message = sm.build_message(profile, 'Playground reports, Hospital: 2 of 2 succeeded', body, [path])
    parsed = email.message_from_bytes(message.as_bytes())
    assert parsed['To'] == 'a@b.com, c@d.com' and parsed['From'] == 'reports@x.com'
    assert parsed['Subject'] == 'Playground reports, Hospital: 2 of 2 succeeded'
    parts = [p for p in parsed.walk() if p.get_filename()]
    assert len(parts) == 1 and parts[0].get_filename() == 'Hospital - Clash report.xlsx'
    assert parts[0].get_payload(decode=True) == b'PK\x03\x04data'
    assert parts[0].get_content_type() == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def test_profiles_store_locally():
    previous = paths.redirect(_compat.tmpdir('sched_mail_store'))
    try:
        assert sm.load_profiles() == {}
        sm.save_profile({'name': 'Office', 'server': 'smtp.x.com', 'sender': 'r@x.com', 'to': ['a@b.com'],
                         'password': 'SEALED'})
        sm.save_profile({'name': 'Backup', 'server': 'smtp.y.com', 'sender': 'r@y.com', 'to': ['a@b.com']})
        assert sm.profile_names() == ['Backup', 'Office']
        assert sm.get_profile('office')['password'] == 'SEALED'
        sm.save_profile({'name': 'Office 365', 'server': 'smtp.z.com', 'sender': 'r@z.com', 'to': ['a@b.com']},
                        old_name='Office')
        assert sm.profile_names() == ['Backup', 'Office 365']
        assert sm.store_path().startswith(paths.data_root())
        assert sm.delete_profile('backup') and not sm.delete_profile('backup')
        _compat.raises(ValueError, sm.save_profile, {'name': ' '})
    finally:
        paths.redirect(previous)


def test_dpapi_round_trip():
    if not _compat.IRONPYTHON:
        _compat.raises(RuntimeError, sm.protect, 'secret')
        assert sm.protect('') == '' and sm.unprotect('') == ''
        return
    sealed = sm.protect(u'p\u00e4ss w0rd')
    assert sealed and 'p\u00e4ss' not in sealed
    assert sm.unprotect(sealed) == u'p\u00e4ss w0rd'
    _compat.raises(RuntimeError, sm.unprotect, 'AAAA')


# ---- a loopback SMTP responder -------------------------------------------------------------------


def smtp_responder():
    """A one-connection SMTP server on 127.0.0.1 that records what it is told."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    server.settimeout(15)
    port = server.getsockname()[1]
    got = {'commands': [], 'data': b''}

    def serve():
        try:
            conn, _address = server.accept()
        except Exception:
            server.close()
            return
        conn.settimeout(15)
        buffer = [b'']

        def readline():
            while b'\n' not in buffer[0]:
                chunk = conn.recv(4096)
                if not chunk:
                    line, buffer[0] = buffer[0], b''
                    return line
                buffer[0] += chunk
            line, rest = buffer[0].split(b'\n', 1)
            buffer[0] = rest
            return line + b'\n'

        def reply(text):
            conn.sendall(text.encode('ascii') + b'\r\n')

        try:
            reply('220 localhost ESMTP Playground test')
            while True:
                raw = readline()
                if not raw:
                    break
                command = raw.decode('ascii', 'replace').strip()
                got['commands'].append(command)
                upper = command.upper()
                if upper.startswith('EHLO'):
                    conn.sendall(b'250-localhost\r\n250 SIZE 20000000\r\n')
                elif upper.startswith(('HELO', 'MAIL', 'RCPT', 'RSET', 'NOOP')):
                    reply('250 OK')
                elif upper == 'DATA':
                    reply('354 End data with <CR><LF>.<CR><LF>')
                    lines = []
                    while True:
                        line = readline()
                        if line in (b'.\r\n', b'.\n', b''):
                            break
                        lines.append(line)
                    got['data'] = b''.join(lines)
                    reply('250 Queued')
                elif upper == 'QUIT':
                    reply('221 Bye')
                    break
                else:
                    reply('502 Not implemented')
        finally:
            conn.close()
            server.close()

    thread = threading.Thread(target=serve)
    thread.daemon = True
    thread.start()
    return port, got, thread


def test_smtplib_sends_through_loopback():
    folder = _compat.tmpdir('sched_mail_send')
    path = os.path.join(folder, 'report.html')
    with open(path, 'wb') as handle:
        handle.write(b'<html>ok</html>')
    port, got, thread = smtp_responder()
    profile = {'name': 'Loopback', 'server': '127.0.0.1', 'port': port, 'security': 'none',
               'sender': 'reports@example.com', 'to': ['a@example.com', 'b@example.com'], 'engine': 'smtplib'}
    engine = sm.send(profile, 'Playground reports, Test: 1 of 1 succeeded', 'Body text', [path], password='')
    thread.join(15)
    assert engine == 'smtplib'
    commands = [c.upper() for c in got['commands']]
    assert commands[0].startswith('EHLO')
    assert 'MAIL FROM:<REPORTS@EXAMPLE.COM>' in [c.split(' SIZE')[0] for c in commands]
    assert 'RCPT TO:<A@EXAMPLE.COM>' in commands and 'RCPT TO:<B@EXAMPLE.COM>' in commands
    assert commands[-1] == 'QUIT'
    message = email.message_from_bytes(got['data'])
    assert message['Subject'] == 'Playground reports, Test: 1 of 1 succeeded'
    names = [p.get_filename() for p in message.walk() if p.get_filename()]
    assert names == ['report.html']


def test_unreachable_server_is_a_readable_error():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()                                        # nothing listens there now
    profile = {'name': 'Nowhere', 'server': '127.0.0.1', 'port': port, 'security': 'none',
               'sender': 'reports@example.com', 'to': ['a@example.com'], 'engine': 'auto'}
    error = _compat.raises(RuntimeError, sm.send, profile, 'x', 'y', [], '')
    assert 'Could not reach 127.0.0.1:%d' % port in str(error)
    if _compat.IRONPYTHON:
        assert '.NET SmtpClient' in str(error)           # auto tried the fallback too


def test_send_refuses_an_incomplete_profile():
    error = _compat.raises(RuntimeError, sm.send, {'name': 'x', 'server': '', 'to': []}, 's', 'b', [], '')
    assert str(error) == 'Enter the SMTP server, like smtp.office365.com.'

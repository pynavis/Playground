# -*- coding: utf-8 -*-
"""Mail for Scheduled Reports: SMTP profiles, the password kept with Windows DPAPI, the
message, and sending it.

Profiles live in %APPDATA%\\pyNavis\\playground\\schedules\\mail.json, always on this computer (never in
the team folder): {name: {'server', 'port', 'security' ('starttls' | 'ssl' | 'none'),
'sender', 'to' [addresses], 'username', 'password' (DPAPI, CurrentUser, base64),
'engine' ('auto' | 'smtplib' | 'dotnet')}}. A password is encrypted for the signed-in
Windows user (System.Security.Cryptography.ProtectedData, CurrentUser scope, with
Playground entropy): only that user on that computer can read it back, and it is never
written as plain text.

Sending: Python's smtplib works under IronPython 3.4 (checked in the harness: smtplib,
ssl.SSLContext backed by .NET SslStream, email; a loopback SMTP exchange runs in the
tests). TLS through IronPython's ssl module has not met a real server here, so 'auto'
falls back to .NET's System.Net.Mail.SmtpClient when smtplib fails BEFORE the message is
handed over (connection, TLS or sign-in), never after, so nothing is sent twice.
SmtpClient cannot do implicit TLS (port 465): 'ssl' profiles always use smtplib.
"""
import base64
import mimetypes
import os
import re

from namo import paths

SECURITY = [('starttls', 'STARTTLS (port 587)'), ('ssl', 'SSL/TLS (port 465)'), ('none', 'None (port 25)')]
ENGINES = [('auto', 'Automatic'), ('smtplib', 'Python smtplib'), ('dotnet', '.NET SmtpClient')]
DEFAULT_PORTS = {'starttls': 587, 'ssl': 465, 'none': 25}
MAX_ATTACH_BYTES = 15 * 1024 * 1024
ENTROPY = b'Playground scheduled reports mail'
TIMEOUT = 60

_ADDRESS = re.compile(r'^[^@\s<>,;"]+@[^@\s<>,;"]+\.[^@\s<>,;"]+$')


# =====================================================================================
# Pure: addresses, profiles, messages
# =====================================================================================


def parse_addresses(text):
    """([addresses], [bad entries]) from text split on newlines, commas or semicolons;
    'Name <a@b.com>' keeps the address. Duplicates (ignoring case) are dropped."""
    good = []
    bad = []
    seen = set()
    for part in re.split(r'[\n\r,;]+', str(text or '')):
        entry = part.strip()
        if not entry:
            continue
        match = re.search(r'<([^<>]+)>\s*$', entry)
        address = (match.group(1) if match else entry).strip()
        if not _ADDRESS.match(address):
            bad.append(entry)
            continue
        if address.lower() not in seen:
            seen.add(address.lower())
            good.append(address)
    return good, bad


def is_address(text):
    return bool(_ADDRESS.match(str(text or '').strip()))


def normalise_profile(profile):
    """A profile with every key, port an int, security and engine valid."""
    out = dict(profile or {})
    security = out.get('security') if out.get('security') in DEFAULT_PORTS else 'starttls'
    out['security'] = security
    try:
        out['port'] = int(out.get('port') or DEFAULT_PORTS[security])
    except (TypeError, ValueError):
        out['port'] = DEFAULT_PORTS[security]
    out['server'] = str(out.get('server') or '').strip()
    out['sender'] = str(out.get('sender') or '').strip()
    to = out.get('to')
    if isinstance(to, str):
        to = parse_addresses(to)[0]
    out['to'] = list(to or [])
    out['username'] = str(out.get('username') or '').strip()
    out['password'] = str(out.get('password') or '')
    out['engine'] = out.get('engine') if out.get('engine') in dict(ENGINES) else 'auto'
    return out


def profile_problems(profile):
    """Sentences for what a profile still needs."""
    p = normalise_profile(profile)
    problems = []
    if not str(profile.get('name') or '').strip():
        problems.append('A mail profile needs a name.')
    if not p['server']:
        problems.append('Enter the SMTP server, like smtp.office365.com.')
    if not (0 < p['port'] < 65536):
        problems.append('Enter a port between 1 and 65535.')
    if not is_address(p['sender']):
        problems.append('Enter the address the mail comes from.')
    if not p['to']:
        problems.append('Enter at least one address to send to.')
    if p['engine'] == 'dotnet' and p['security'] == 'ssl':
        problems.append('.NET SmtpClient cannot use SSL/TLS on port 465: pick STARTTLS or Automatic.')
    return problems


def plan_attachments(file_paths, limit=MAX_ATTACH_BYTES, size_of=None):
    """(attach, too_big): files in order until their total passes limit; the rest are
    listed in the body instead. Missing files are left out of both."""
    size_of = size_of or os.path.getsize
    attach = []
    too_big = []
    total = 0
    for path in file_paths or []:
        try:
            size = size_of(path)
        except OSError:
            continue
        if total + size <= limit:
            attach.append(path)
            total += size
        else:
            too_big.append(path)
    return attach, too_big


def build_message(profile, subject_text, body, attachments, now=None):
    """An email.message.EmailMessage (From, To, Subject, Date, plain text body and the
    files attached). Pure stdlib; the same on both engines."""
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid
    p = normalise_profile(profile)
    message = EmailMessage()
    message['From'] = p['sender']
    message['To'] = ', '.join(p['to'])
    message['Subject'] = subject_text
    message['Date'] = formatdate(now, localtime=True)
    message['Message-ID'] = make_msgid(domain='playground.local')
    message.set_content(body)
    for path in attachments or []:
        kind, _encoding = mimetypes.guess_type(path)
        maintype, subtype = (kind or 'application/octet-stream').split('/', 1)
        with open(path, 'rb') as handle:
            data = handle.read()
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(path))
    return message


def body_with_attachments(body, attached, too_big):
    """The body plus a closing note on what is attached and what was too big."""
    lines = [body.rstrip('\n'), '']
    if attached:
        lines.append('Attached: %s.' % ', '.join(os.path.basename(p) for p in attached))
    if too_big:
        lines.append('Not attached (over %d MB in total), find them at:' % (MAX_ATTACH_BYTES // (1024 * 1024)))
        for path in too_big:
            lines.append('  %s' % path)
    lines.append('')
    lines.append('Sent by Playground Scheduled Reports.')
    return '\n'.join(lines) + '\n'


# =====================================================================================
# Profile storage (local only)
# =====================================================================================


def store_path():
    return os.path.join(paths.data_root(), 'schedules', 'mail.json')


def load_profiles():
    """{name: profile} (normalised). Never raises."""
    data = paths.load_json(store_path(), {})
    found = data.get('profiles') if isinstance(data, dict) else None
    if not isinstance(found, dict):
        return {}
    out = {}
    for name in found:
        if isinstance(found[name], dict):
            profile = normalise_profile(found[name])
            profile['name'] = name
            out[name] = profile
    return out


def profile_names():
    from namo import naming
    return sorted(load_profiles(), key=naming.natural_key)


def get_profile(name):
    profiles = load_profiles()
    for key in profiles:
        if key.lower() == str(name or '').strip().lower():
            return profiles[key]
    return None


def save_profile(profile, old_name=None):
    """Stores a profile (its 'password' must already be DPAPI text). IOError on failure."""
    record = normalise_profile(profile)
    name = str(profile.get('name') or '').strip()
    if not name:
        raise ValueError('A mail profile needs a name.')
    record.pop('name', None)
    target = store_path()
    with paths.FileLock(target):
        data = paths.load_json(target, {})
        found = data.get('profiles') if isinstance(data, dict) else None
        found = dict(found) if isinstance(found, dict) else {}
        for key in list(found):
            if key.lower() in (name.lower(), str(old_name or '').lower()):
                del found[key]
        found[name] = record
        paths.write_json(target, {'format': 'playground-mail-profiles', 'version': 1, 'profiles': found})
    return name


def delete_profile(name):
    target = store_path()
    with paths.FileLock(target):
        data = paths.load_json(target, {})
        found = data.get('profiles') if isinstance(data, dict) else None
        if not isinstance(found, dict):
            return False
        keys = [k for k in found if k.lower() == str(name).lower()]
        for key in keys:
            del found[key]
        if keys:
            paths.write_json(target, {'format': 'playground-mail-profiles', 'version': 1, 'profiles': found})
        return bool(keys)


# =====================================================================================
# DPAPI
# =====================================================================================


def _dpapi():
    try:
        import clr
        clr.AddReference('System.Security')
        from System.Security.Cryptography import DataProtectionScope, ProtectedData
        from System import Array, Byte
    except Exception:
        raise RuntimeError('Saving a mail password needs Windows data protection (.NET), which is '
                           'only there inside Navisworks.')
    return ProtectedData, DataProtectionScope, Array, Byte


def protect(text):
    """base64 text of the DPAPI-encrypted (CurrentUser) UTF-8 password; '' for ''."""
    if not text:
        return ''
    ProtectedData, Scope, Array, Byte = _dpapi()
    data = Array[Byte](bytearray(str(text).encode('utf-8')))
    entropy = Array[Byte](bytearray(ENTROPY))
    sealed = ProtectedData.Protect(data, entropy, Scope.CurrentUser)
    return base64.b64encode(bytes(bytearray(sealed))).decode('ascii')


def unprotect(sealed):
    """The password from protect()'s text; '' for ''. RuntimeError with a sentence when
    it cannot be read (another Windows user or computer)."""
    if not sealed:
        return ''
    ProtectedData, Scope, Array, Byte = _dpapi()
    try:
        raw = Array[Byte](bytearray(base64.b64decode(sealed)))
        entropy = Array[Byte](bytearray(ENTROPY))
        plain = ProtectedData.Unprotect(raw, entropy, Scope.CurrentUser)
    except Exception:
        raise RuntimeError('The saved mail password cannot be read by this Windows user. Enter it '
                           'again in Scheduled Reports, Mail settings.')
    return bytes(bytearray(plain)).decode('utf-8')


# =====================================================================================
# Sending
# =====================================================================================


class SetupError(Exception):
    """smtplib failed before the message was handed over (safe to retry elsewhere)."""


def _is_ironpython():
    import sys
    return sys.implementation.name == 'ironpython'


def send_smtplib(profile, message, password):
    import smtplib
    import ssl
    p = normalise_profile(profile)
    try:
        if p['security'] == 'ssl':
            server = smtplib.SMTP_SSL(p['server'], p['port'], timeout=TIMEOUT,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(p['server'], p['port'], timeout=TIMEOUT)
    except Exception as error:
        raise SetupError('Could not reach %s:%d: %s' % (p['server'], p['port'], error))
    try:
        try:
            server.ehlo()
            if p['security'] == 'starttls':
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if p['username']:
                server.login(p['username'], password)
        except Exception as error:
            raise SetupError(str(error) or type(error).__name__)
        server.send_message(message, from_addr=p['sender'], to_addrs=p['to'])
    finally:
        try:
            server.quit()
        except Exception:
            pass


def send_dotnet(profile, subject_text, body, attachments, password):
    import clr
    clr.AddReference('System')
    from System.Net import NetworkCredential
    from System.Net.Mail import Attachment, MailAddress, MailMessage, SmtpClient
    p = normalise_profile(profile)
    if p['security'] == 'ssl':
        raise RuntimeError('.NET SmtpClient cannot use SSL/TLS on port 465.')
    message = MailMessage()
    client = SmtpClient(p['server'], p['port'])
    try:
        message.From = MailAddress(p['sender'])
        for address in p['to']:
            message.To.Add(MailAddress(address))
        message.Subject = subject_text
        message.Body = body
        for path in attachments or []:
            message.Attachments.Add(Attachment(path))
        client.EnableSsl = p['security'] == 'starttls'
        client.Timeout = TIMEOUT * 1000
        if p['username']:
            client.Credentials = NetworkCredential(p['username'], password)
        client.Send(message)
    finally:
        message.Dispose()
        try:
            client.Dispose()
        except Exception:
            pass


def send(profile, subject_text, body, file_paths, password=None):
    """Sends the run's mail; returns the engine used ('smtplib' or 'dotnet'). Raises
    with a readable message on failure. password None reads the stored DPAPI one."""
    p = normalise_profile(profile)
    problems = profile_problems(dict(p, name=profile.get('name') or 'profile'))
    if problems:
        raise RuntimeError(problems[0])
    if password is None:
        password = unprotect(p['password'])
    attach, too_big = plan_attachments(file_paths)
    full_body = body_with_attachments(body, attach, too_big)
    engine = p['engine']
    if engine == 'dotnet':
        send_dotnet(p, subject_text, full_body, attach, password)
        return 'dotnet'
    message = build_message(p, subject_text, full_body, attach)
    try:
        send_smtplib(p, message, password)
        return 'smtplib'
    except SetupError as error:
        if engine == 'auto' and p['security'] != 'ssl' and _is_ironpython():
            try:
                send_dotnet(p, subject_text, full_body, attach, password)
                return 'dotnet'
            except Exception as second:
                raise RuntimeError('%s (and .NET SmtpClient: %s)' % (error, second))
        raise RuntimeError(str(error))


# =====================================================================================
# Password prompt (WPF; never under pynavis run)
# =====================================================================================


def build_password_window(title, prompt, keep_hint=False):
    """The unshown password dialog: window.Tag has .result (None until OK) and
    .box (the PasswordBox)."""
    from namo import ui
    ui.load_wpf()
    from System.Windows import CornerRadius, Thickness, VerticalAlignment
    from System.Windows.Controls import Border, Dock, DockPanel, PasswordBox, StackPanel
    from System.Windows.Media import Brushes
    from PyNavis.Runtime.Forms import DesignSystem
    t = ui.tokens()
    win = ui.window(title, width=420, resizable=False)
    state = ui.Bag(result=None, box=None)
    box = PasswordBox()
    box.Height = 30.0
    box.FontSize = 13.0
    box.Foreground = ui.brush(ui.hex_of(t.Ink))
    box.Background = Brushes.Transparent
    box.BorderThickness = Thickness(0)
    box.Padding = Thickness(8, 0, 8, 0)
    box.VerticalContentAlignment = VerticalAlignment.Center
    box.FocusVisualStyle = DesignSystem.FocusRing(DesignSystem.Accent)
    frame = Border()
    frame.CornerRadius = CornerRadius(4)
    frame.BorderBrush = ui.brush(ui.hex_of(t.LineStrong))
    frame.BorderThickness = Thickness(1)
    frame.Background = ui.brush(ui.hex_of(t.Paper))
    frame.Child = box
    state.box = box
    body = StackPanel()
    body.Margin = Thickness(24, 24, 24, 16)
    label = ui.text(prompt)
    label.Margin = Thickness(0, 0, 0, 8)
    body.Children.Add(label)
    body.Children.Add(frame)
    hint = ui.hint('Leave it empty to keep the saved password.' if keep_hint else
                   'Kept encrypted for your Windows account on this computer.')
    hint.Margin = Thickness(0, 6, 0, 0)
    body.Children.Add(hint)

    def accept():
        state.result = str(box.Password)
        ui.close_with(win, True)

    ok = ui.button('OK', accept, 'primary')
    ok.IsDefault = True
    cancel = ui.button('Cancel', lambda: ui.close_with(win, False))
    cancel.IsCancel = True
    layout = DockPanel()
    bottom = ui.footer([ok, cancel])
    DockPanel.SetDock(bottom, Dock.Bottom)
    layout.Children.Add(bottom)
    layout.Children.Add(body)
    win.Content = layout
    win.Tag = state
    win.ContentRendered += ui.safe(lambda s, e: box.Focus(), 'password focus')
    return win


def ask_password(title, prompt, keep_hint=False):
    """The password typed, '' for an empty OK, or None when cancelled."""
    from namo import ui
    win = build_password_window(title, prompt, keep_hint)
    ui.show_modal(win)
    return win.Tag.result

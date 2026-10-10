# -*- coding: utf-8 -*-
"""Helpers for running Playground code under `pynavis run` (dev only, never shipped).

Under the runner a script gets __runner__ True, its toasts and output land in the run's
transcript, and any dialog raises "Dialogs are not available under pynavis run". This
module makes the Playground library importable there and runs one bundle's script.py
with the same globals a ribbon click gives it (pyNavis ScriptExecutor.RunScript):
__file__, __commandpath__, __title__, __selfinit__ False, __pynavis__, plus __runner__
True and the runner's own __model__, __models__, __args__ and __run_dir__.

Sandbox: everything a Python-side tool would write under %APPDATA%, %LOCALAPPDATA%,
%TEMP% or the user's home (settings, stores, reports in Documents) is pointed at
D:\\Temp\\pg-runner\\sandbox for the run, and the shell side effects a tool can reach
through namo.ui and pynavis.script (open a file, open Explorer, the clipboard, Reload)
are replaced by no-ops that record what they would have done. .NET calls that bypass
these (Process.Start, Environment.GetFolderPath) are not caught here; the tool list in
dev/runner/SAFETY.md says which tools were skipped for that reason.
"""
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
EXTENSION = os.path.join(REPO, 'Playground.extension')
LIB = os.path.join(EXTENSION, 'lib')
SANDBOX = r'D:\Temp\pg-runner\sandbox'
DIALOG_MESSAGE = 'Dialogs are not available under pynavis run'

BLOCKED = []      # what the no-op shell stubs were asked to do, in order
_SAVED_ENV = {}


def use_playground_lib():
    """Puts Playground.extension\\lib first on sys.path and drops any namo already
    imported (pyNavis runs every configured extension's startup.py before a run, and
    another extension may carry its own namo)."""
    while LIB in sys.path:
        sys.path.remove(LIB)
    sys.path.insert(0, LIB)
    for name in list(sys.modules):
        if name == 'namo' or name.startswith('namo.'):
            del sys.modules[name]
    import namo
    return os.path.abspath(namo.__file__)


def _env(name, value):
    if name not in _SAVED_ENV:
        _SAVED_ENV[name] = os.environ.get(name)
    os.environ[name] = value


def enter_sandbox(root=SANDBOX):
    """Points per-user folders at the sandbox for this process. Returns the root."""
    folders = {
        'APPDATA': os.path.join(root, 'AppData', 'Roaming'),
        'LOCALAPPDATA': os.path.join(root, 'AppData', 'Local'),
        'TEMP': os.path.join(root, 'Temp'),
        'TMP': os.path.join(root, 'Temp'),
        'USERPROFILE': os.path.join(root, 'home'),
        'HOME': os.path.join(root, 'home'),
    }
    for name, folder in folders.items():
        if not os.path.isdir(folder):
            os.makedirs(folder)
        _env(name, folder)
    documents = os.path.join(folders['HOME'], 'Documents')
    if not os.path.isdir(documents):
        os.makedirs(documents)
    try:
        import tempfile
        tempfile.tempdir = None
    except Exception:
        pass
    from namo import paths
    paths.redirect(folders['APPDATA'])
    try:
        from pynavis import settings
        settings._APPDATA_OVERRIDE = folders['APPDATA']
    except Exception:
        pass
    _stub_shell()
    return root


def leave_sandbox():
    for name, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    _SAVED_ENV.clear()
    try:
        from namo import paths
        paths.redirect(None)
    except Exception:
        pass
    try:
        from pynavis import settings
        settings._APPDATA_OVERRIDE = None
    except Exception:
        pass


def _blocker(what, result=None):
    def blocked(*args, **kwargs):
        BLOCKED.append('%s(%s)' % (what, ', '.join(repr(a) for a in args)))
        return result
    return blocked


def _stub_shell():
    """Shell side effects become recorded no-ops."""
    os.startfile = _blocker('os.startfile')
    try:
        import subprocess
        subprocess.Popen = _blocker('subprocess.Popen')
        subprocess.call = _blocker('subprocess.call', 1)
        subprocess.check_call = _blocker('subprocess.check_call')
        subprocess.check_output = _blocker('subprocess.check_output', b'')
        subprocess.run = _blocker('subprocess.run')
    except Exception:
        pass
    os.system = _blocker('os.system', 1)
    try:
        import webbrowser
        webbrowser.open = _blocker('webbrowser.open', True)
        webbrowser.open_new_tab = _blocker('webbrowser.open_new_tab', True)
    except Exception:
        pass
    try:
        from pynavis import script
        for name in ('reload_pynavis', 'show_in_explorer', 'open_folder', 'open_url',
                     'open_file', 'clipboard_copy'):
            if hasattr(script, name):
                setattr(script, name, _blocker('pynavis.script.' + name, True))
    except Exception:
        pass
    from namo import ui
    ui.copy = _blocker('namo.ui.copy', True)
    ui.open_path = _blocker('namo.ui.open_path')
    ui.show_in_explorer = _blocker('namo.ui.show_in_explorer')
    # Documents through .NET (Environment.GetFolderPath) ignores %USERPROFILE%.
    documents = os.path.join(os.environ.get('USERPROFILE', SANDBOX), 'Documents')
    from namo import data_common, vp_common
    data_common.documents_folder = lambda: documents
    vp_common.documents_folder = lambda: documents


def select_items(mode):
    """'all' selects every item with geometry (the sample model's 17 parts sit under one
    element, so element-level selection would give a single item), 'first' only the
    first element. Returns how many are selected."""
    from namo import items
    if mode == 'first':
        found = list(items.objects(items.roots()))[:1]
    else:
        found = list(items.geometry_items(items.roots()))
    return items.select(found)


def read_title(bundle_dir):
    """The ribbon title: bundle.yaml's title:, else the folder name without its suffix
    and with _ as a space (pyNavis BundleParser.ToTitle)."""
    yaml_path = os.path.join(bundle_dir, 'bundle.yaml')
    if os.path.isfile(yaml_path):
        with open(yaml_path, 'r') as handle:
            for line in handle:
                if line.startswith('title:'):
                    value = line.split(':', 1)[1].strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                        value = value[1:-1]
                    if value:
                        return value
    base = os.path.basename(bundle_dir.rstrip('\\/'))
    return base.rsplit('.', 1)[0].replace('_', ' ')


def bundle_dir(key):
    return os.path.join(EXTENSION, key.replace('/', os.sep))


def run_bundle(key, runner_globals, script_name='script.py'):
    """Runs one bundle's script with ribbon-click globals. Returns a dict:
    outcome ('ok', 'needs-dialog', 'failed'), error (first line), traceback, seconds,
    result (the script's own __result__, if any)."""
    folder = bundle_dir(key)
    script = os.path.join(folder, script_name)
    if not os.path.isfile(script):
        return {'outcome': 'failed', 'error': 'No %s in %s' % (script_name, key), 'traceback': '', 'seconds': 0}
    if folder not in sys.path:
        sys.path.insert(1, folder)
    host = runner_globals.get('__pynavis__')
    title = read_title(folder)
    if host is not None:
        try:
            host.SetCommandContext(script, folder, title, key)
        except Exception:
            pass
    scope = {
        '__name__': '__main__',
        '__builtins__': runner_globals.get('__builtins__'),
        '__file__': script,
        '__commandpath__': folder,
        '__title__': title,
        '__selfinit__': False,
        '__pynavis__': host,
        '__runner__': True,
        '__model__': runner_globals.get('__model__'),
        '__models__': runner_globals.get('__models__'),
        '__args__': [],
        '__run_dir__': runner_globals.get('__run_dir__'),
    }
    with open(script, 'rb') as handle:
        source = handle.read().decode('utf-8-sig')
    started = time.time()
    outcome = {'outcome': 'ok', 'error': '', 'traceback': ''}
    try:
        code = compile(source, script, 'exec')
        exec(code, scope)
    except SystemExit:
        pass
    except BaseException as error:
        text = traceback.format_exc()
        message = '%s: %s' % (type(error).__name__, error)
        outcome['traceback'] = text
        outcome['error'] = message.splitlines()[0] if message else type(error).__name__
        outcome['outcome'] = 'needs-dialog' if DIALOG_MESSAGE in text else 'failed'
    outcome['seconds'] = round(time.time() - started, 2)
    result = scope.get('__result__')
    if result is not None:
        try:
            import json
            json.dumps(result)
            outcome['result'] = result
        except Exception:
            outcome['result'] = repr(result)
    return outcome

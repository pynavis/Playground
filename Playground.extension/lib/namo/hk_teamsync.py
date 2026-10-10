# -*- coding: utf-8 -*-
"""Team Sync at startup: with "Pull at startup" on, checks the team folder's version stamp
on a worker thread (a slow or offline share never blocks Navisworks) and, when it
changed, pulls on the UI thread once no pyNavis script is running, then toasts. Off by
default; skipped under pynavis run.

Why the pull is not on the worker: it rewrites config.json (team shortcuts and extension
folders), and pyNavis rewrites the same file from the UI thread right after startup.py
(pane assignments). Two threads doing read-modify-write on one file lose an edit. The
worker therefore only reads files (teamsync.startup_probe: no Navisworks API, no WPF, no
logging) and hands its answer over in a plain dict that a DispatcherTimer polls.
"""

WAIT_LIMIT_S = 1800.0        # give up quietly (logged) if the share or the gate never frees
STATE_FILE = 'team-sync.json'        # teamsync.STATE_FILE (a test keeps the two equal)


def auto_pull_on(data_root=None):
    """Whether "Pull at startup" is on, read straight from the small state file.

    startup.py runs at boot and on every Reload, and almost nobody has this on: the
    answer must not cost importing teamsync (and through it the whole UI library).
    A state file that cannot be read says True, so teamsync looks at it properly."""
    import io
    import json
    import os
    if data_root is None:
        from namo import paths
        data_root = paths.data_root()
    path = os.path.join(data_root, STATE_FILE)
    if not os.path.exists(path):
        return False
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as handle_:
            state = json.loads(handle_.read())
    except Exception:
        return True
    return bool(isinstance(state, dict) and state.get('auto_pull'))


def handle(name, event):
    if name != 'startup' or (event or {}).get('runner'):
        return
    if not auto_pull_on():
        return
    from namo import teamsync
    state = teamsync.load_state()
    if not state.get('auto_pull') or not teamsync.team_folder(state):
        return
    from System.Threading import Thread, ThreadStart
    from pynavis import toast
    from namo import ribbon, session

    found = {}                                   # the worker writes 'outcome' once

    def work():
        # Worker thread: file reads only. Anything escaping a .NET worker thread ends
        # the Navisworks process, so every exception is caught and handed over.
        try:
            outcome = ('folder', teamsync.startup_probe())
        except BaseException as error:
            outcome = ('error', error)
        found['outcome'] = outcome

    def waiting():
        return 'outcome' not in found or ribbon.gate_held()

    def pull():
        kind, value = found['outcome']
        if kind == 'error':
            raise IOError(str(value) or value.__class__.__name__)
        return teamsync.pull(value) if value else None

    def done(job):
        try:
            if job.state == 'failed':
                session.log('warning', 'team sync at startup: %s' % job.message)
                level, message, detail = teamsync.result_toast(IOError(job.message))
            elif job.state == 'done' and job.handle is not None:
                level, message, detail = teamsync.result_toast(job.handle)
            else:
                if job.state == 'timeout':
                    session.log('warning', 'team sync at startup: gave up waiting for the team '
                                           'folder or for a running script')
                return
            toast.show(level, message, detail)
        except Exception:
            pass

    job = ribbon.Job('Team Sync', waiting, pull, timeout_s=WAIT_LIMIT_S, on_done=done)
    ribbon.schedule(job, 250)                    # a DispatcherTimer on this (UI) thread
    worker = Thread(ThreadStart(work))
    worker.IsBackground = True
    worker.Name = 'Playground team sync'
    worker.Start()

# -*- coding: utf-8 -*-
"""Camera Sync's app-closing handler: stops syncing and removes this session's file,
so the other Navisworks window stops following a session that is gone."""
import os


def handle(name, event):
    if name != 'app-closing':
        return
    try:
        from namo import camsync, paths, session
        sync = getattr(session.holder(camsync.HOLDER), 'sync', None)
        path = os.path.join(paths.data_root(), 'camsync', camsync.file_name(camsync.own_pid()))
        if sync is None and not os.path.exists(path):
            return
        camsync.shutdown()
    except Exception:
        pass

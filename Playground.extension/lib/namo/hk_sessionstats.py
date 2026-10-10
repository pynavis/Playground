# -*- coding: utf-8 -*-
"""Session Stats handler: stamps when the document opened and when each model arrived,
so Session Stats can say how and when every model joined this session.

Kept in the session holder 'sessionstats' (not saved anywhere):
    docs = {document key: {'opened_at': epoch or None, 'known': [model keys],
                           'models': {model key: {'appended_at', 'via', 'load_seconds'}}}}

Batch Append records the exact seconds each file took (record_batch), because hooks do
not run while a Playground command is running: its appends would otherwise go unseen.
"""

import time

HOLDER = 'sessionstats'


def _holder():
    from namo import session
    held = session.holder(HOLDER)
    if getattr(held, 'docs', None) is None:
        held.docs = {}
    return held


def doc_key(document):
    try:
        name = document.FileName or ''
    except Exception:
        name = ''
    return name.lower() or 'untitled'


def _entry(document, create=True):
    held = _holder()
    key = doc_key(document)
    entry = held.docs.get(key)
    if entry is None and create:
        entry = {'opened_at': None, 'known': [], 'models': {}}
        held.docs[key] = entry
    return entry


def _keys(document):
    from namo import modelmgmt
    return [i['key'] for i in modelmgmt.models_info(document)]


def handle(name, event):
    from pynavis._api import Application
    document = Application.ActiveDocument
    if document is None:
        return
    now = time.time()
    if name == 'doc-opened':
        held = _holder()
        entry = {'opened_at': now, 'known': [], 'models': {}}
        held.docs[doc_key(document)] = entry
        keys = _keys(document)
        entry['known'] = keys
        for key in keys:
            entry['models'][key] = {'appended_at': now, 'via': 'opened with the document',
                                    'load_seconds': None}
        return
    if name == 'model-appended':
        entry = _entry(document)
        keys = _keys(document)
        known = set(entry['known'])
        for key in keys:
            if key not in known and key not in entry['models']:
                entry['models'][key] = {'appended_at': now, 'via': 'appended', 'load_seconds': None}
        entry['known'] = keys


def record_batch(document, seconds_by_key, via='Batch Append'):
    """Stamps models appended by a Playground command with their measured load seconds."""
    try:
        entry = _entry(document)
        now = time.time()
        for key in sorted(seconds_by_key):
            entry['models'][key] = {'appended_at': now, 'via': via,
                                    'load_seconds': seconds_by_key[key]}
        entry['known'] = _keys(document)
    except Exception:
        pass


def stamps_for(document):
    """{model key: stamp} for the document (the untitled entry when it was saved since)."""
    held = _holder()
    entry = held.docs.get(doc_key(document))
    if entry is None:
        entry = held.docs.get('untitled')
    return dict(entry['models']) if entry else {}


def opened_at(document):
    held = _holder()
    entry = held.docs.get(doc_key(document))
    return entry.get('opened_at') if entry else None

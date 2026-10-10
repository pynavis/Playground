# -*- coding: utf-8 -*-
"""Transform Fixer handler: when a model is appended and a transform preset marked
"apply automatically" exists for its file name, puts that transform on it (one undo
step) and says so in a toast. Presets are off unless a preset was saved with the
option ticked, so with none the handler only reads the small preset file.

Which models are new: hk_sessionstats (registered before this handler for the same
event) stamps every model with how it arrived; models stamped 'appended' that this
handler has not seen yet are new. Models appended by Batch Append are handled by
Batch Append itself (hooks do not run while a Playground command runs)."""

HOLDER = 'transformpresets'


def handle(name, event):
    if name != 'model-appended':
        return
    from namo import transforms
    presets = transforms.all_presets()
    if not any(p.get('auto_apply') for p in presets.values()):
        return
    from namo import hk_sessionstats, modelmgmt, session
    from pynavis._api import Application
    document = Application.ActiveDocument
    if document is None:
        return
    held = session.holder(HOLDER)
    seen = getattr(held, 'seen', None)
    if seen is None:
        seen = held.seen = {}
    dkey = hk_sessionstats.doc_key(document)
    infos = modelmgmt.models_info(document)
    keys = [i['key'] for i in infos]
    processed = seen.get(dkey)
    stamps = hk_sessionstats.stamps_for(document)
    if stamps:
        fresh = [k for k in keys if (processed is None or k not in processed)
                 and (stamps.get(k) or {}).get('via') == 'appended']
    elif processed is None:
        fresh = keys[-1:]
    else:
        fresh = [k for k in keys if k not in processed]
    seen[dkey] = set(keys)
    if not fresh:
        return
    applied, failed = transforms.apply_auto_presets(fresh, document)
    from pynavis import toast
    if applied:
        toast.success('Applied the transform preset for %s' % modelmgmt.join_names(applied),
                      'Undo with Ctrl+Z if this model should stay where it was.')
    if failed:
        toast.warning('Could not apply a transform preset',
                      '%s: %s' % (failed[0][0], failed[0][1]))

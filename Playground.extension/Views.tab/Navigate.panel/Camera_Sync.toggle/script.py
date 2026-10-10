"""Mirrors the camera live between Navisworks sessions on this machine, or stops mirroring."""
from namo import camsync, ui, vp_common
from pynavis import script, toast


def run():
    if camsync.is_running():
        camsync.stop()
        script.set_toggle_state(False)
        toast.info('Camera sync off', 'This window no longer follows or leads the other one.')
        return
    if vp_common.active_doc() is None:
        script.set_toggle_state(False)
        toast.info('No document open', 'Open a model, then turn Camera Sync on.')
        return
    try:
        partner = camsync.start(log=ui.pinned_logger())
    except Exception as error:
        camsync.stop()
        script.set_toggle_state(False)
        toast.error('Could not start Camera Sync', str(error))
        return
    script.set_toggle_state(True)
    message, detail = camsync.status_text(partner)
    if partner is None:
        toast.info(message, detail)
    else:
        toast.success(message, detail)


run()

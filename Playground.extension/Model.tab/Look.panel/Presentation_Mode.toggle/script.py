"""Turns Presentation Mode on (ribbon minimized, panels closed, window maximized) or puts everything back."""
from namo import presentation
from pynavis import script, toast


def run():
    if presentation.is_on():
        restored, problems = presentation.leave()
        script.set_toggle_state(False)
        level, message, detail = presentation.exit_message(restored, problems)
        toast.show(level, message, detail)
        return
    if script.get_toggle_state():
        script.set_toggle_state(False)        # left through Ctrl+Alt+F11: only the button was behind
        toast.info('Presentation mode is already off', 'Click again to start presenting.')
        return
    options = presentation.normalize_options(script.get_config(presentation.DEFAULTS))
    state, notes = presentation.enter(options)
    if not presentation.changed(state):
        presentation.leave()                    # nothing to hold: stay off
        script.set_toggle_state(False)
        message, detail = presentation.nothing_message(notes)
        toast.info(message, detail)
        return
    script.set_toggle_state(True)
    message, detail = presentation.enter_message(state, notes)
    if notes:
        toast.warning(message, detail)
    else:
        toast.success(message, detail)


run()

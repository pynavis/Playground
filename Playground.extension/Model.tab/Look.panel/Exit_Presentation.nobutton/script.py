"""Leaves Presentation Mode from anywhere and puts the ribbon, panels, window and background back."""
from namo import presentation
from pynavis import toast

if presentation.is_on():
    restored, problems = presentation.leave()
    level, message, detail = presentation.exit_message(restored, problems)
    toast.show(level, message, detail)
else:
    toast.info('Presentation mode is not on', 'Nothing to put back.')

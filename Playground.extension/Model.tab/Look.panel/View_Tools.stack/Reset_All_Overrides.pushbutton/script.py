"""Resets the chosen kinds of override (colors, hidden items, moves, flags) in one undo step."""
from namo import explode, look_ghost, look_tools, ui
from pynavis import doc as nwdoc
from pynavis import forms, script, toast

TITLE = 'Reset Overrides'
DEFAULTS = {'kinds': list(look_tools.RESET_DEFAULT)}


def run():
    document = nwdoc.get_doc()
    if document.Models.Count == 0:
        toast.info('No model open', 'Open a model, then run Reset Overrides again.')
        return
    cfg = script.get_config(DEFAULTS)
    values = ui.form(TITLE, look_tools.reset_fields(cfg.get('kinds')), ok='Reset')
    if values is None:
        return
    kinds = look_tools.normalize_kinds(values['kinds'])
    if 'transforms' in kinds and not forms.confirm(
            'Put every moved or rotated item back where its source file has it? This also undoes '
            'moves made on purpose, such as a model aligned by hand.', title=TITLE):
        return
    cfg['kinds'] = kinds
    script.save_config(cfg)
    look_tools.reset(kinds, document)
    if 'transforms' in kinds and explode.load_record(document) is not None:
        explode.save_record(None, document)       # nothing is exploded any more
    if 'materials' in kinds and look_ghost.load_record(document) is not None:
        look_ghost.save_record(None, document)    # nothing is ghosted any more
    if 'temporary' in kinds:
        detail = 'Ctrl+Z undoes it in one step, except the temporary colors, which Navisworks does not keep.'
    else:
        detail = 'Ctrl+Z undoes it in one step.'
    toast.success(look_tools.reset_summary(kinds), detail)


run()

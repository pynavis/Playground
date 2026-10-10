"""Moves the level section one level down (Alt+PgDn) and says which level it is on."""
from namo import levels, progress, vp_common
from pynavis import toast

document = vp_common.active_doc()
if not vp_common.has_models(document):
    toast.info('No model open', 'Open or append a model first.')
else:
    if levels.cached_or_none(document) is None:
        outcome = progress.run('Level Down', lambda report: levels.step(-1, document, report), 'Looking for levels')
    else:
        outcome = levels.step(-1, document)
    if outcome is not progress.CANCELLED:
        toast.show(outcome[0], outcome[1], outcome[2])

"""Sends the selected elements to Revit, where the Playground Link button for pyRevit selects them."""
from pynavis import toast

from namo import revitlink
from namo import clashset_common as common


def run():
    elements, skipped = revitlink.selected_elements()
    if not elements:
        if skipped:
            toast.info('The selection has no Revit elements',
                       'Select elements from models exported from Revit, then click again.')
        else:
            toast.info('Nothing selected', 'Select the elements to show in Revit, then click again.')
        return
    try:
        revitlink.send_to_revit(elements)
    except (IOError, OSError) as error:
        toast.error('Could not write the link file', str(error))
        return
    files = sorted(set(e['file'] for e in elements if e['file']))
    detail = 'In Revit, open %s and click Playground > Show from Navisworks.' % (
        revitlink.short_list(files, 2) if files else 'the model')
    if skipped:
        detail = '%s without Revit IDs left out. %s' % (common.plural(skipped, 'item'), detail)
    toast.success('Sent %s to Revit' % common.plural(len(elements), 'element'), detail)


run()

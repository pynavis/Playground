"""Steps the view background to the next preset: White, Light gradient, Dark gradient, Black, Horizon."""
from namo import look_tools
from pynavis import doc as nwdoc
from pynavis import toast


def run():
    document = nwdoc.get_doc()
    index = look_tools.next_background(look_tools.current_background_index(document))
    spec = look_tools.BACKGROUNDS[index]
    try:
        look_tools.set_background(spec, document)
    except Exception as error:
        toast.error('Could not change the background', str(error))
        return
    look_tools.remember_background(index)
    following = look_tools.BACKGROUNDS[look_tools.next_background(index)]['name']
    toast.success('Background: %s' % spec['name'], 'Click again for %s. Shift+Click to pick one.' % following)


run()

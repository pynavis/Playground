"""Sets the local origin Coordinate Spotter measures from, or goes back to the model origin."""
from namo import levels, picking, spotter, vp_common
from pynavis import forms, toast

TITLE = 'Coordinate Spotter origin'
CHOICES = ['Pick the local origin', 'Type the local origin', 'Use the model origin']


def run():
    document = vp_common.active_doc()
    if not vp_common.has_models(document):
        toast.info('No model open', 'Open or append a model first.')
        return
    units = str(document.Units)
    current = spotter.load_origin(document)
    where = vp_common.point_text(current, units) if current else 'the model origin'
    choice = forms.ask_options('Coordinates are measured from %s.' % where, CHOICES, title=TITLE)
    if choice is None:
        return
    origin = None
    if choice == CHOICES[0]:
        hit = picking.point('Click the point to measure from')
        if hit is None:                         # Esc, right-click or another tool: say nothing
            return
        origin = hit.point
    elif choice == CHOICES[1]:
        start = ', '.join('%.3f' % v for v in current) if current else '0, 0, 0'
        text = forms.ask_string('Local origin X, Y, Z in %s, with commas between:' % units.lower(),
                                default=start, title=TITLE)
        if text is None:
            return
        origin = spotter.parse_xyz(text, units)
        if origin is None:
            toast.error('That is not three coordinates', 'Type X, Y and Z with commas between, like 12.5, 3, 0.')
            return
    try:
        spotter.save_origin(document, origin)
    except (IOError, OSError) as error:
        toast.error('Could not save the origin', str(error))
        return
    if spotter.state().points:
        spotter.redraw_all(units, origin, spotter.marker_size(units, levels.model_box(document)))
    if origin is None:
        toast.success('Measuring from the model origin')
    else:
        toast.success('Local origin set', vp_common.point_text(origin, units))


run()

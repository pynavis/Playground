"""Drops numbered coordinate markers where you click until Esc, then lists the points and copies them."""
import os

from namo import levels, picking, spotter, vp_common
from pynavis import forms, output, overlay, script, toast

TITLE = 'Coordinate Spotter'
SAVE = ['Save as Excel', 'Save as CSV']


def _overlay_redraw():
    """Redraws the overlay through namo.overlayfix, so labels land on their points."""
    from namo import overlayfix
    return overlayfix.redraw()


def pick_loop(document, units, origin, holder, size):
    """Picks until Esc, a right-click or another tool; returns how many points were
    added. Each pick runs on the Measure tool with its prompt on the banner
    (namo.picking shows and clears it), and the prompt carries the last reading."""
    added = 0
    while True:
        n = holder.count + 1
        last = holder.points[-1] if holder.points else None
        hit = picking.point(spotter.prompt_text(n, last, units, origin), want_item=True, doc=document)
        if hit is None:
            return added
        record = spotter.record_of(n, hit)
        holder.points.append(record)
        holder.count = n
        added += 1
        spotter.draw(record, units, origin, size)
        _overlay_redraw()


def save(document, head, rows, origin, units):
    """Offers Excel or CSV; True when saved, False when it failed, None when skipped."""
    choice = forms.ask_options(None, SAVE, title=TITLE)
    if choice is None:
        return None
    excel = choice == SAVE[0]
    stem = '%s - Coordinates' % vp_common.file_stem(vp_common.doc_path(document))
    folder = vp_common.default_folder(vp_common.doc_path(document))
    if excel:
        path = forms.save_file(filter='Excel workbooks (*.xlsx)|*.xlsx',
                               default_name=os.path.join(folder, stem + '.xlsx'), title=TITLE)
    else:
        path = forms.save_file(filter='CSV files (*.csv)|*.csv',
                               default_name=os.path.join(folder, stem + '.csv'), title=TITLE)
    if path is None:
        return None
    title = 'Coordinates in %s' % units.lower()
    if origin:
        title += ', measured from the local origin at %s' % vp_common.point_text(origin, units)
    try:
        if excel:
            path = path if path.lower().endswith('.xlsx') else path + '.xlsx'
            spotter.write_xlsx(path, head, rows, title)
        else:
            path = path if path.lower().endswith('.csv') else path + '.csv'
            spotter.write_csv(path, head, rows)
    except (IOError, OSError) as error:
        toast.error('Could not save the points', '%s. Close the file, then try again.' % error)
        return False
    toast.success('Saved %s' % vp_common.plural(len(rows), 'point'), path)
    return True


def run():
    document = vp_common.active_doc()
    if not vp_common.has_models(document):
        toast.info('No model open', 'Open or append a model, then run Coordinate Spotter again.')
        return
    units = str(document.Units)
    origin = spotter.load_origin(document)
    holder = spotter.state()
    key = vp_common.doc_path(document).lower() or 'untitled'
    if holder.doc is not None and holder.doc != key:
        spotter.clear()
        holder = spotter.state()
    holder.doc = key
    size = spotter.marker_size(units, levels.model_box(document))
    if not pick_loop(document, units, origin, holder, size):
        return                                  # ended without a new point: say nothing
    head = spotter.headers(units, origin)
    where = ''
    if origin:
        where = ', measured from the local origin at %s' % vp_common.point_text(origin, units)
    output.set_title(TITLE)
    output.print_md('## Spotted points\nIn %s%s. Clear Spots removes the markers.' % (units.lower(), where))
    output.print_table(spotter.display_rows(holder.points, units, origin), head)
    rows = spotter.data_rows(holder.points, units, origin)
    script.clipboard_copy(spotter.tsv(head, rows))
    if save(document, head, rows, origin, units) is None:
        toast.success('%s spotted' % vp_common.plural(len(holder.points), 'point'),
                      'The table is in the output window and on the clipboard.')


run()

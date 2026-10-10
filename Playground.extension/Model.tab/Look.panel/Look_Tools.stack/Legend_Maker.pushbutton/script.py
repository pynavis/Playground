"""Draws the last color scheme as a PNG legend, shows it, and can save a viewpoint with those colors."""
import os

from namo import colorize, legend, naming, paint, session, ui
from pynavis import doc as nwdoc
from pynavis import output, script, toast

TITLE = 'Legend Maker'
DEFAULTS = {'view': False, 'folder': ''}


def default_folder(document, cfg):
    """The last folder used, else the document's folder, else Documents."""
    if cfg.get('folder') and os.path.isdir(cfg['folder']):
        return cfg['folder']
    path = nwdoc.get_filename(document)
    if path and os.path.isdir(os.path.dirname(path)):
        return os.path.dirname(path)
    from System import Environment
    return Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)


def run():
    scheme = paint.last_scheme()
    if not scheme or not scheme.get('entries'):
        toast.info('No color scheme yet', 'Run Color by Property, Color Presets or Status Painter first.')
        return
    document = nwdoc.get_doc()
    cfg = script.get_config(DEFAULTS)
    stem = os.path.splitext(os.path.basename(nwdoc.get_filename(document) or ''))[0]
    path = os.path.join(default_folder(document, cfg), legend.default_name(scheme.get('title') or 'Legend', stem))
    values = ui.form(TITLE, legend.form_fields(scheme, path, cfg), ok='Save legend')
    if values is None:
        return
    title = naming.sanitize(values['title']).strip() or 'Legend'
    target = values['path']
    if not target.lower().endswith('.png'):
        target += '.png'
    cfg.update({'view': values['view'], 'folder': os.path.dirname(target)})
    script.save_config(cfg)
    scheme = dict(scheme, title=title)
    try:
        _path, width, _height, data = legend.save_png(scheme, target)
    except (IOError, OSError) as error:
        toast.error('Could not save the legend', 'Close the file if another program has it open. %s' % error)
        return
    output.print_html(legend.image_html(data, width, target))
    if not (values['view'] and document.Models.Count):
        toast.success('Saved the legend', target)
        return
    try:
        comment = '\n'.join(colorize.legend_lines(scheme))
        name, with_colors = legend.save_view(legend.view_name(title), comment, document)
    except Exception as error:
        session.log('error', 'legend viewpoint not saved: %s' % error)
        toast.warning('Saved the legend, not the viewpoint', 'Navisworks refused the viewpoint: %s' % error)
        return
    if with_colors:
        toast.success('Saved the legend and a viewpoint', 'Recall "%s" to bring these colors back. %s'
                      % (name, target))
    else:
        toast.success('Saved the legend and a viewpoint', '"%s" holds the camera only: no colors were '
                      'applied when it was saved. %s' % (name, target))


run()

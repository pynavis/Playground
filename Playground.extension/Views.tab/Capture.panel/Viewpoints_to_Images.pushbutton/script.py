"""Saves an image of each chosen saved viewpoint, plus an index.html contact sheet, into a dated folder."""
from namo import capture, progress, reports, ui, vp_common
from pynavis import script, toast

TITLE = 'Viewpoints to Images'
REPORT = 'viewpoint_images'


def run():
    document = vp_common.active_doc()
    rows = vp_common.view_rows(document) if vp_common.has_models(document) else []
    if not rows:
        toast.info('No saved viewpoints', 'Save some viewpoints, then run Viewpoints to Images again.')
        return
    defaults = reports.default_config(REPORT)
    defaults['open'] = True
    cfg = script.get_config(defaults)
    picked = vp_common.choose_views('%s: viewpoints' % TITLE, rows, cfg.get('views'), ok='Next')
    if picked is None:
        return
    chosen, spec = picked
    if not chosen:
        toast.info('No viewpoints chosen', 'Tick at least one viewpoint, then run Viewpoints to Images again.')
        return
    fields = capture.image_fields(cfg, vp_common.default_folder(vp_common.doc_path(document)))
    fields += [
        {'kind': 'check', 'key': 'overlay', 'label': 'Include redlines and on-screen marks',
         'default': cfg.get('overlay', False)},
        {'kind': 'check', 'key': 'index_html', 'label': 'Write an index.html contact sheet',
         'default': cfg.get('index_html', True)},
        {'kind': 'check', 'key': 'open', 'label': 'Open it when done', 'default': cfg.get('open', True)},
    ]
    values = ui.form(TITLE, fields, intro='%s chosen. The view comes back where it was afterwards.'
                     % vp_common.plural(len(chosen), 'viewpoint'), ok='Save images', width=500)
    if values is None:
        return
    cfg = capture.image_values(cfg, values)
    cfg.update({'views': spec, 'overlay': values['overlay'], 'index_html': values['index_html'],
                'open': values['open']})
    script.save_config(cfg)
    result = progress.run(TITLE, lambda report: reports.run(REPORT, cfg, doc=document, interactive=True,
                                                            progress=report), 'Capturing')
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])
    if cfg.get('open') and result['level'] in ('success', 'warning'):
        target = result.get('index') or result.get('folder')
        if target:
            try:
                ui.open_path(target)
            except Exception:
                pass


run()

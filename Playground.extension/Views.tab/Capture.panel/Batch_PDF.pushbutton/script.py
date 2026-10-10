"""Prints an ordered set of saved viewpoints to one PDF handout with a title page, contents and page footers."""
import os

from namo import progress, rep_batch_pdf, reports, ui, vp_common, vp_ui
from pynavis import forms, script, toast

TITLE = 'Batch PDF'
REPORT = 'batch_pdf'


def run():
    document = vp_common.active_doc()
    rows = vp_common.view_rows(document) if vp_common.has_models(document) else []
    if not rows:
        toast.info('No saved viewpoints', 'Save some viewpoints, then run Batch PDF again.')
        return
    defaults = reports.default_config(REPORT)
    defaults.update({'open': True, 'hand_order': False})
    cfg = script.get_config(defaults)
    picked = vp_common.choose_views('%s: viewpoints' % TITLE, rows, cfg.get('views'), ok='Next')
    if picked is None:
        return
    chosen, spec = picked
    if not chosen:
        toast.info('No viewpoints chosen', 'Tick at least one viewpoint, then run Batch PDF again.')
        return
    values = ui.form(TITLE, rep_batch_pdf.option_fields(cfg),
                     intro='%s chosen. Project and author come from the Playground settings.'
                           % vp_common.plural(len(chosen), 'viewpoint'),
                     ok='Next', width=500)
    if values is None:
        return
    order = []
    if values['hand_order'] and len(chosen) > 1:
        current = vp_common.apply_order(chosen, cfg.get('order'))
        labels = [vp_common.join_path(r['folder'], r['name']) for r in current]
        indices = vp_ui.order('%s: page order' % TITLE, labels)
        if indices is None:
            return
        order = [[current[i]['folder'], current[i]['name']] for i in indices]
    cfg.update(values)
    cfg['views'] = spec
    cfg['order'] = order
    stem = '%s - Viewpoints' % vp_common.file_stem(vp_common.doc_path(document))
    folder = vp_common.default_folder(vp_common.doc_path(document))
    path = forms.save_file(filter='PDF files (*.pdf)|*.pdf', default_name=os.path.join(folder, stem + '.pdf'),
                           title=TITLE)
    if path is None:
        return
    if not path.lower().endswith('.pdf'):
        path += '.pdf'
    script.save_config(cfg)
    run_cfg = dict(cfg)
    run_cfg['folder'] = os.path.dirname(path)
    run_cfg['name_template'] = os.path.splitext(os.path.basename(path))[0].replace('{', '{{').replace('}', '}}')
    # The file the user picked, exactly: folder + name_template alone would pass the name
    # through naming.sanitize and safe_filename (cut at 80 characters, dashes changed).
    run_cfg['path'] = path
    result = progress.run(TITLE, lambda report: reports.run(REPORT, run_cfg, doc=document, interactive=True,
                                                            progress=report), 'Capturing')
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])
    if cfg['open'] and result.get('pdf') and result['level'] in ('success', 'warning'):
        try:
            ui.open_path(result['pdf'])
        except Exception:
            pass


run()

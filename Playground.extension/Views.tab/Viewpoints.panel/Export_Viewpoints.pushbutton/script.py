"""Exports the saved viewpoints you choose as Navisworks viewpoints XML, a Playground package, or both."""
import os

from namo import dates, ui, vp_common, vpexport
from pynavis import forms, script, toast

TITLE = 'Export Viewpoints'
DEFAULTS = {'views': None, 'format': 'xml', 'comments': True, 'clip_xml': False}


def run():
    document = vp_common.active_doc()
    rows = vp_common.view_rows(document) if document is not None else []
    if not rows:
        toast.info('No saved viewpoints', 'Save some viewpoints, then run Export Viewpoints again.')
        return
    cfg = script.get_config(DEFAULTS)
    picked = vp_common.choose_views('%s: viewpoints' % TITLE, rows, cfg.get('views'), ok='Next')
    if picked is None:
        return
    chosen, spec = picked
    if not chosen:
        toast.info('No viewpoints chosen', 'Tick at least one viewpoint, then run Export Viewpoints again.')
        return
    values = ui.form(TITLE, vpexport.export_fields(cfg),
                     intro='%s chosen. The XML file is what Navisworks imports through Saved Viewpoints, Import '
                           'Viewpoints; the package is what Viewpoint Sync reads.'
                           % vp_common.plural(len(chosen), 'viewpoint'),
                     ok='Export')
    if values is None:
        return
    cfg.update({'views': spec, 'format': values['format'], 'comments': values['comments'],
                'clip_xml': values['clip_xml']})
    script.save_config(cfg)
    stem = '%s - Viewpoints - %s' % (vp_common.file_stem(vp_common.doc_path(document)),
                                     dates.format(dates.now(), '%Y-%m-%d'))
    folder = vp_common.default_folder(vp_common.doc_path(document))
    if values['format'] == 'package':
        path = forms.save_file(filter='Playground viewpoint packages (*.nvp.json)|*.nvp.json',
                               default_name=os.path.join(folder, stem + '.nvp.json'), title=TITLE)
    else:
        path = forms.save_file(filter='Navisworks viewpoints XML (*.xml)|*.xml',
                               default_name=os.path.join(folder, stem + '.xml'), title=TITLE)
    if path is None:
        return
    records = vpexport.records_from(chosen, document, include_clip=True)
    written = []
    try:
        if values['format'] in ('xml', 'both'):
            xml_path = path if path.lower().endswith('.xml') else path + '.xml'
            written.append(vpexport.write_exchange(xml_path, records, document, include_clip=values['clip_xml'],
                                                   include_comments=values['comments']))
        if values['format'] in ('package', 'both'):
            base = path
            for ext in ('.nvp.json', '.json', '.xml'):
                if base.lower().endswith(ext):
                    base = base[:-len(ext)]
                    break
            if not values['comments']:
                records = [dict(r, comments=[]) for r in records]
            written.append(vpexport.write_package(base + '.nvp.json', records, document))
    except (IOError, OSError) as error:
        toast.error('Could not write the export', '%s. Check the folder is writable, then try again.' % error)
        return
    toast.success('Exported %s' % vp_common.plural(len(records), 'viewpoint'),
                  ' and '.join(os.path.basename(p) for p in written) + ' in ' + os.path.dirname(written[0]))


run()

# -*- coding: utf-8 -*-
"""Makes a QR code for each selected object: PNG files, a printable label sheet and a Playground > QR property."""
import os

from pynavis import script, toast

from namo import field_qr, fourd_common, items, naming, paths, progress, qr, ui

TITLE = 'QR Tagger'
MAX_OBJECTS = 2000
DEFAULTS = {'template': field_qr.DEFAULT_TEMPLATE, 'level': 'M', 'scale': 8, 'folder': '', 'sheet': True,
            'property': True}
LEVELS = [('L, 7% damage', 'L'), ('M, 15%', 'M'), ('Q, 25%', 'Q'), ('H, 30%', 'H')]


def ask(doc, count, values):
    folder = values.get('folder') or ''
    if not folder or not os.path.isdir(folder):
        folder = fourd_common.doc_folder(doc)
    fields = [
        {'kind': 'text', 'key': 'template', 'label': 'Payload', 'default': values.get('template'),
         'required': True, 'validate': field_qr.check_template,
         'hint': 'Tokens: %s. A URL works too: https://example.com/asset?guid={guid}'
                 % ' '.join('{%s}' % t for t in field_qr.TOKENS)},
        {'kind': 'radio', 'key': 'level', 'label': 'Error correction (how much damage it survives)',
         'options': LEVELS, 'inline': True, 'default': values.get('level', 'M'), 'fallback': 'M'},
        {'kind': 'int', 'key': 'scale', 'label': 'Module size in the PNG files', 'min': 2, 'max': 40,
         'suffix': 'px', 'default': int(values.get('scale') or 8), 'required': True},
        {'kind': 'folder', 'key': 'folder', 'label': 'Save in', 'default': folder, 'required': True,
         'hint': 'A new folder is made inside it for the PNG files and the label sheet.'},
        {'kind': 'check', 'key': 'sheet', 'label': 'Write a printable A4 label sheet',
         'default': bool(values.get('sheet', True))},
        {'kind': 'check', 'key': 'property', 'label': 'Write the payload into each object (Playground > QR)',
         'default': bool(values.get('property', True))},
    ]
    return ui.form(TITLE, fields, intro='%s selected.' % fourd_common.plural(count, 'object'),
                   ok='Make codes', width=600)


def make(objects, answer, folder, doc, report):
    standard = naming.standard_values(doc)
    labels = []
    payloads = []
    for index, obj in enumerate(objects):
        report(0.8 * index / float(len(objects) or 1), 'Encoding %s of %s' % ('{:,}'.format(index + 1),
                                                                         '{:,}'.format(len(objects))))
        values = field_qr.object_values(obj, standard)
        payload, _missing = field_qr.render_payload(answer['template'], values)
        code = qr.encode(payload, answer['level'])
        labels.append({'code': code, 'payload': payload, 'name': values['name'],
                       'element_id': values['element_id'],
                       'lines': ['ID %s' % values['element_id'] if values['element_id'] else '',
                                 values['guid']]})
        payloads.append(payload)
    paths.ensure_dir(folder)
    for label, name in zip(labels, field_qr.file_names(labels)):
        qr.write_png(label['code'], os.path.join(folder, name), scale=answer['scale'])
        label['file'] = name
    sheet = None
    if answer['sheet']:
        report(0.85, 'Writing the label sheet')
        sheet = os.path.join(folder, 'QR labels.html')
        rows = [{'svg': qr.to_svg(l['code']), 'name': l['name'], 'lines': l['lines']} for l in labels]
        paths.atomic_write_text(sheet, field_qr.sheet_html(
            rows, 'QR labels', '%s. Print at 100%% scale on A4.' % fourd_common.plural(len(rows), 'label')))
    written, errors = 0, []
    if answer['property']:
        report(0.9, 'Writing the Playground > QR property')
        written, errors = field_qr.write_property(objects, payloads, doc)
    return {'labels': labels, 'sheet': sheet, 'written': written, 'errors': errors}


def run():
    if ui.is_runner():
        toast.info('%s works on the selection' % TITLE, 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    # Stop the walk one past the limit: a whole-model selection must not be walked in full
    # just to be refused.
    objects = items.objects(items.selected(doc), budget=MAX_OBJECTS + 1)
    if not objects:
        toast.info('Nothing selected', 'Select the objects to tag, then run QR Tagger.')
        return
    if len(objects) > MAX_OBJECTS:
        toast.info('Too many objects selected', 'Select at most %s objects; more are selected.'
                   % '{:,}'.format(MAX_OBJECTS))
        return
    values = script.get_config(DEFAULTS)
    answer = ask(doc, len(objects), values)
    if answer is None:
        return
    values.update(dict((k, answer[k]) for k in ('template', 'level', 'scale', 'folder', 'sheet', 'property')))
    script.save_config(values)
    folder = field_qr.output_folder(answer['folder'], fourd_common.doc_title(doc))
    try:
        result = progress.run(TITLE, lambda report: make(objects, answer, folder, doc, report))
    except qr.QRError as error:
        toast.error('A payload is too long for a QR code', '%s Shorten the payload template.' % error)
        return
    except (IOError, OSError) as error:
        toast.error('Could not write the QR files', str(error))
        return
    if result is progress.CANCELLED:
        return
    largest = max(l['code'].version for l in result['labels'])
    made = 'Made %s' % fourd_common.plural(len(result['labels']), 'QR code')
    detail = 'PNG files%s in %s. Largest code: version %d.' % (
        ' and a label sheet' if result['sheet'] else '', folder, largest)
    repeats = field_qr.repeated_payloads([l['payload'] for l in result['labels']])
    if result['errors']:
        toast.warning('%s; %s not written' % (made, fourd_common.plural(len(result['errors']), 'property',
                                                                        'properties')),
                      '%s The files are in %s.' % (result['errors'][0], folder))
    elif repeats:
        toast.warning(made, '%s the same payload as another: the template has nothing that tells them '
                      'apart (no Element ID or GUID). Files in %s.'
                      % ('1 object has' if repeats == 1 else '%s objects have' % '{:,}'.format(repeats), folder))
    else:
        toast.success(made, detail)
    fourd_common.open_file(result['sheet'] or folder)


run()

# -*- coding: utf-8 -*-
"""Reads a BCF file into the issue register, with saved viewpoints and found elements."""
import os

from pynavis import forms, script, toast

from namo import bcf, bcf_exchange, issueapi, issuestore, progress, ui

DEFAULTS = {'viewpoints': True, 'elements': True}


def run():
    doc = issuestore.active_doc()
    if doc is None or not issueapi.has_model(doc):
        toast.info('No model open', 'Open the model the BCF file belongs to, then import it.')
        return
    store = issuestore.for_doc(doc)
    if not store.saved:
        toast.info('Save the model first', issuestore.NOT_SAVED)
        return
    path = forms.open_file(filter='BCF files (*.bcfzip;*.bcf)|*.bcfzip;*.bcf|All files (*.*)|*.*',
                           title='Import BCF')
    if path is None:
        return
    try:
        data = bcf.read(path)
    except bcf.BcfError as error:
        toast.error('Could not read %s' % os.path.basename(path), str(error))
        return
    except (IOError, OSError) as error:
        toast.error('Could not open %s' % os.path.basename(path), str(error))
        return
    if not data['topics']:
        toast.info('No topics in %s' % os.path.basename(path),
                   data['notes'][0] if data['notes'] else 'The file holds no issues.')
        return
    preview = bcf_exchange.preview(data, store)
    me = script.bind()
    values = me.get_config(dict(DEFAULTS))
    intro = ('%s: BCF %s, %d topic%s (%d new, %d already in this register), %d viewpoint%s, '
             '%d component%s.' % (os.path.basename(path), preview['version'], preview['topics'],
                                  '' if preview['topics'] == 1 else 's', preview['new'],
                                  preview['matching'], preview['viewpoints'],
                                  '' if preview['viewpoints'] == 1 else 's', preview['components'],
                                  '' if preview['components'] == 1 else 's'))
    fields = [
        {'kind': 'check', 'key': 'viewpoints', 'label': 'Save the viewpoints under BCF in Saved Viewpoints',
         'default': bool(values['viewpoints'])},
        {'kind': 'check', 'key': 'elements', 'label': 'Find the components in the model',
         'default': bool(values['elements']),
         'hint': 'By IFC GUID, then Revit Element ID. Each lookup searches the model; large '
                 'models take longer (stops after 3 minutes).'},
        {'kind': 'label', 'muted': True,
         'text': 'Topics already in the register take the BCF fields when the BCF is newer; new '
                 'comments are added either way, never duplicated.'},
    ]
    answers = ui.form('BCF Import', fields, intro=intro, ok='Import', width=560)
    if answers is None:
        return
    values.update(answers)
    me.save_config(values)
    name = os.path.basename(path)
    try:
        outcome = progress.run('BCF import', lambda report: bcf_exchange.import_topics(
            data, name, answers, doc, report))
    except (IOError, OSError) as error:
        toast.error('Could not save the imported issues', '%s Check the data folder, then try again.'
                    % error)
        return
    if outcome is progress.CANCELLED:
        return
    detail = bcf_exchange.detail_line(outcome)
    level = 'warning' if (outcome['missing'] or outcome['not_searched'] or outcome['notes']) else 'success'
    toast.show(level, 'Imported %s' % bcf_exchange.summary_line(outcome), detail)


run()

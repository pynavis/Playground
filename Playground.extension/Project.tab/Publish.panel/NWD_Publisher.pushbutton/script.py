# -*- coding: utf-8 -*-
"""Publishes the document as the next numbered NWD, after a Preflight, and archives older versions."""
import os

from pynavis import doc as navis_doc
from pynavis import forms, script, toast

from namo import config as namo_config
from namo import modelmgmt, naming, paths, preflight, progress, publish, ui

LAST = 'Last used settings'


def choose_settings(config):
    """The settings to pre-fill: the last used ones, or a saved profile. None = cancel."""
    saved = publish.profile_names()
    last = publish.normalize_settings(config.get('last') or {})
    if not saved:
        return last, None
    options = [LAST] + saved
    checked = config.get('profile') if config.get('profile') in saved else LAST
    picked = forms.select_from_list(options, title='NWD Publisher',
                                    prompt='Start from which settings?', checked=[checked])
    if picked is None:
        return None, None
    if picked == LAST:
        return last, None
    return (publish.load_profile(picked) or last), picked


def run():
    doc = navis_doc.get_doc()
    doc_path = navis_doc.get_filename(doc) or ''
    config = script.get_config({'last': {}, 'profile': ''})
    settings, profile_name = choose_settings(config)
    if settings is None:
        return
    values = naming.standard_values(doc)
    folder_now = publish.target_folder(dict(settings, folder=publish.start_folder(settings, doc_path)))
    _version, preview = publish.plan_target(settings['template'], values, publish.list_files(folder_now))
    fields = publish.form_fields(settings, doc_path, preflight.profile_names(), namo_config.user_name())
    answers = ui.form('NWD Publisher', fields, ok='Publish', width=560,
                      intro='Next file: %s in %s.' % (preview, folder_now))
    if answers is None:
        return
    save_as = (answers.pop('save_as') or '').strip()
    chosen = publish.normalize_settings(dict(settings, **answers))
    folder = publish.target_folder(chosen)

    preflight_text = 'skipped'
    if chosen['preflight']:
        profile = preflight.load_profile(chosen['preflight_profile']) or \
            preflight.normalize_profile(preflight.DEFAULT_PROFILE)
        checks = progress.run('Preflight', lambda report: preflight.run_profile(profile, doc, report),
                              'Reading the models')
        if checks is progress.CANCELLED:
            return
        preflight_text = preflight.summary_text(checks)
        failed = [c for c in checks if c['level'] == 'fail']
        if failed:
            question = ('Preflight (%s) found %d failed check%s: %s. Publish anyway?'
                        % (profile['name'], len(failed), '' if len(failed) == 1 else 's',
                           preflight.failures_text(checks)))
            if not forms.confirm(question, title='NWD Publisher'):
                return
            preflight_text += ', published anyway'

    existing = publish.list_files(folder)
    version, name = publish.plan_target(chosen['template'], values, existing)
    path = os.path.join(folder, name)
    # Never write over, or archive, the open document or a file a model was loaded from.
    try:
        model_files = [p for info in modelmgmt.models_info(doc) for p in (info['file'], info['source'])]
    except Exception:
        model_files = []
    protected = publish.protected_paths(doc_path, model_files)
    problem = publish.target_problem(path, protected)
    if problem:
        toast.error('Nothing was published', problem)
        return
    staying = [n for n in existing if publish.is_protected(os.path.join(folder, n), protected)]
    to_archive = 0
    if chosen['archive']:
        to_archive = len(publish.archive_plan(existing, chosen['template'], values, name, keep=staying))
    # The one question before anything is written: the exact file, and what moves.
    if not forms.confirm(publish.confirm_text(name, folder, chosen['method'], to_archive,
                                              os.path.basename(doc_path)), title='NWD Publisher'):
        return
    try:
        paths.ensure_dir(folder)
    except Exception as error:
        toast.error('Could not create the folder', '%s: %s' % (folder, error))
        return
    props = dict(chosen)
    named = dict(values, version=version)
    props['title'] = naming.render(chosen['title'], named)[0].strip() or os.path.splitext(name)[0]
    props['comments'] = naming.render(chosen['comments'], named)[0]
    props['publisher'] = namo_config.user_name()
    try:
        publish.publish(doc, path, chosen['method'], props)
    except Exception as error:
        toast.error('Could not write %s' % name,
                    '%s. Check that %s can be written to, then try again.'
                    % (str(error) or type(error).__name__, folder))
        return
    if not os.path.isfile(path):
        toast.error('Navisworks did not write %s' % name,
                    'Nothing is at %s. Check the folder can be written to.' % path)
        return

    moved, archive_failed = [], []
    if chosen['archive']:
        plan = publish.archive_plan(publish.list_files(folder), chosen['template'], values, name,
                                    publish.list_files(os.path.join(folder, publish.ARCHIVE_FOLDER)),
                                    keep=staying)
        moved, archive_failed = publish.archive(folder, plan)

    size = os.path.getsize(path)
    record = publish.history_record(path, version, chosen['method'], size,
                                    preflight_text, namo_config.user_name(), doc_path, len(moved))
    history_note = publish.log_history(record, doc, doc_path)

    last = dict(chosen)
    script.save_config({'last': last, 'profile': profile_name or ''})
    if save_as:
        try:
            publish.save_profile(save_as, chosen)
        except (IOError, OSError, ValueError) as error:
            history_note = ((history_note or '') + ' The profile was not saved: %s.' % error).strip()

    level, message, detail = publish.toast_text(name, folder, len(moved), archive_failed,
                                                history_note, chosen['method'], size)
    toast.show(level, message, detail)
    if chosen['open_folder']:
        ui.show_in_explorer(path)


run()

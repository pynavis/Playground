"""Exports saved viewpoints to an Excel workbook, or creates and updates viewpoints from one."""
import os

from namo import dates, progress, vp_common, vpexcel
from pynavis import forms, output, toast

TITLE = 'Viewpoints from Excel'
ACTIONS = ['Export viewpoints to Excel', 'Import viewpoints from Excel', 'Blank template']
FILTER = 'Excel workbooks (*.xlsx)|*.xlsx'


def default_name(document, what):
    return '%s - %s - %s.xlsx' % (vp_common.file_stem(vp_common.doc_path(document)), what,
                                  dates.format(dates.now(), '%Y-%m-%d'))


def ask_save(document, what):
    """The workbook path (the dialog opens in the model's folder), or None."""
    folder = vp_common.default_folder(vp_common.doc_path(document))
    path = forms.save_file(filter=FILTER, default_name=os.path.join(folder, default_name(document, what)),
                           title=TITLE)
    if path is None:
        return None
    if not path.lower().endswith('.xlsx'):
        path += '.xlsx'
    return path


def export(document, example=False):
    rows = [] if example else vp_common.view_rows(document)
    if not example and not rows:
        toast.info('No saved viewpoints', 'Choose Blank template to start a workbook from the current view.')
        return
    if not example:
        picked = vp_common.choose_views('%s: export' % TITLE, rows, ok='Export')
        if picked is None:
            return
        rows = picked[0]
        if not rows:
            toast.info('No viewpoints chosen', 'Tick at least one viewpoint, then export again.')
            return
    path = ask_save(document, 'Viewpoint template' if example else 'Viewpoints')
    if path is None:
        return
    try:
        count = vpexcel.write_workbook(path, document, rows, example=example)
    except (IOError, OSError) as error:
        toast.error('Could not save the workbook', '%s. Close it in Excel, then try again.' % error)
        return
    if example:
        toast.success('Template saved', '%s. Fill in a row per viewpoint, then import it.' % path)
    else:
        toast.success('Exported %s' % vp_common.plural(count, 'viewpoint'), path)


def show_errors(errors, units):
    output.set_title('%s: rows not imported' % TITLE)
    output.print_md('## Rows not imported\nLengths are read in %s. Fix these rows and import again.' % units.lower())
    output.print_table([[row, vp_common.folder_label(folder), name, problem] for row, folder, name, problem in errors],
                       ['Row', 'Folder', 'Name', 'Problem'])


def import_(document):
    path = forms.open_file(filter=FILTER, title=TITLE)
    if path is None:
        return
    units = str(document.Units)
    try:
        rows = vpexcel.read_sheet(path)
        records, errors, _header = vpexcel.parse_rows(rows, units)
    except (IOError, OSError) as error:
        toast.error('Could not read the workbook', '%s. Close it in Excel, then try again.' % error)
        return
    except ValueError as error:
        toast.error('Not a viewpoints workbook', str(error))
        return
    except Exception as error:
        toast.error('Could not read the workbook', 'It is not an Excel .xlsx file (%s).' % type(error).__name__)
        return
    if not records:
        if errors:
            show_errors(errors, units)
            toast.warning('No row could be imported', 'The problems are listed in the output window.')
        else:
            toast.info('The workbook has no viewpoint rows', 'Add a row per viewpoint under the header.')
        return
    exists, _find = vpexcel.lookup(document)
    steps = vpexcel.plan(records, exists)
    question = '%s\n\nLengths are read in %s. One Ctrl+Z undoes the whole import.' % (
        vpexcel.plan_sentence(steps, errors), units.lower())
    if not forms.confirm(question, TITLE):
        return
    result = progress.run(TITLE, lambda report: vpexcel.apply(document, steps, report), 'Importing')
    if result is progress.CANCELLED:
        return
    failed = [(row, '', name, problem) for row, name, problem in result['failed']]
    if errors or failed:
        show_errors(sorted(errors + failed), units)
    parts = []
    if result['created']:
        parts.append('created %s' % vp_common.count_text(result['created']))
    if result['updated']:
        parts.append('updated %s' % vp_common.count_text(result['updated']))
    done = result['created'] + result['updated']
    summary = ', '.join(parts)
    summary = (summary[0].upper() + summary[1:]) if summary else 'Nothing imported'
    skipped = len(errors) + len(failed)
    if result['stopped']:
        toast.warning('Stopped after %s' % vp_common.plural(done, 'viewpoint'), 'Ctrl+Z undoes what was imported.')
    elif skipped and done:
        toast.warning('%s, skipped %s' % (summary, vp_common.plural(skipped, 'row')),
                      'The skipped rows are listed in the output window.')
    elif skipped:
        toast.error('No row could be imported', 'The problems are listed in the output window.')
    else:
        toast.success('%s %s' % (summary, 'viewpoint' if done == 1 else 'viewpoints'),
                      'One Ctrl+Z undoes the import.')


def run():
    document = vp_common.active_doc()
    if not vp_common.has_models(document):
        toast.info('No model open', 'Open or append a model, then run Viewpoints from Excel again.')
        return
    action = forms.ask_options(None, ACTIONS, title=TITLE)
    if action == ACTIONS[0]:
        export(document)
    elif action == ACTIONS[1]:
        import_(document)
    elif action == ACTIONS[2]:
        export(document, example=True)


run()

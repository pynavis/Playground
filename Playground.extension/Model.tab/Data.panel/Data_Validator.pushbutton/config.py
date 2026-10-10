# -*- coding: utf-8 -*-
"""Opens the validation rules folder, checks every rule file, or restores the starter rules."""
from pynavis import forms, output, toast

from namo import ui, validator

OPEN = 'Open the rules folder'
CHECK = 'Check the rule files'
RESTORE = 'Restore the starter rules'


def check(folder):
    rulesets = validator.load_folder(folder)
    if not rulesets:
        toast.info('No rule files', 'The folder %s holds no .json files.' % folder)
        return
    problems = []
    rules = 0
    for ruleset in rulesets:
        problems.extend(ruleset.get('problems') or [])
        rules += len(ruleset['rules'])
    if not problems:
        toast.success('Every rule file reads cleanly', '%d %s, %d %s.' % (
            len(rulesets), 'file' if len(rulesets) == 1 else 'files', rules, 'rule' if rules == 1 else 'rules'))
        return
    output.print_md('**Rule file problems** in %s' % folder)
    output.print_table([[line] for line in problems], ['Problem'])
    toast.warning('%d %s in the rule files' % (len(problems), 'problem' if len(problems) == 1 else 'problems'),
                  'Each one is listed with its line in the output window.')


def run():
    if ui.is_runner():
        toast.info('Settings need the Navisworks window', 'They cannot open under pynavis run.')
        return
    folder = validator.rules_folder()
    validator.ensure_starter(folder)
    choice = forms.ask_options('Validation rules live in %s.' % folder, [OPEN, CHECK, RESTORE],
                               title='Data Validator')
    if choice is None:
        return
    if choice == OPEN:
        ui.open_path(folder)
        toast.success('Opened the rules folder', folder)
    elif choice == CHECK:
        check(folder)
    else:
        if not forms.confirm('Overwrite %s with the shipped starter rules? Your other rule files are kept.'
                             % validator.STARTER_FILE, title='Data Validator'):
            return
        try:
            path = validator.restore_starter(folder)
        except (IOError, OSError) as error:
            toast.error('Could not write the starter rules', str(error))
            return
        toast.success('Starter rules restored', path)


run()

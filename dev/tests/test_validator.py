# -*- coding: utf-8 -*-
"""namo.validator: rule files (parsing, line-numbered problems, the starter set),
evaluation, tallies, HTML, folder loading and run_rules() through the fake layer."""
import io
import json
import os

import _compat
import test_propindex as pf

from namo import paths, propindex, validator


def test_starter_set_reads_cleanly():
    ruleset, problems = validator.check_text(validator.starter_text(), validator.STARTER_FILE)
    assert problems == []
    assert ruleset['name'] == 'Playground starter rules'
    assert len(ruleset['rules']) == len(validator.STARTER['rules'])
    levels = [r for r in ruleset['rules'] if r['name'] == 'Elements are hosted on a level'][0]
    assert levels['require_mode'] == 'any' and levels['severity'] == 'warning'
    assert levels['applies_to'][0]['op'] == 'exists'
    ducts = ruleset['rules'][0]
    assert ducts['applies_to'][0]['op'] == 'in_list'
    assert ducts['require'][0] == dict(ducts['require'][0], category='Element', property='System Name',
                                       op='not_empty')


def test_json_syntax_error_has_line_and_context():
    text = '{\n  "rules": [\n    {"name": "A" "require": []}\n  ]\n}\n'
    ruleset, problems = validator.check_text(text, 'bad.json')
    assert ruleset is None
    line, sentence, context = problems[0]
    assert line == 3
    assert sentence.startswith('The file is not valid JSON')
    assert '"name": "A"' in context
    lines = validator.format_problems('bad.json', problems)
    assert lines[0].startswith('bad.json, line 3: The file is not valid JSON')


def test_rule_problems_name_the_rule_and_line():
    data = {'format': 'playground-validation', 'rules': [
        {'name': 'Good', 'require': ['Element > Mark is not empty']},
        {'name': 'Bad op', 'require': ['Element > Mark frobs 3'], 'colour': 'red'},
        {'name': 'No requirements'},
        {'name': 'Good', 'require': ['Item > Name exists']},
        {'require': ['Element > Mark is not empty'], 'severity': 'loud', 'require_mode': 'some'},
    ]}
    text = json.dumps(data, indent=2)
    ruleset, problems = validator.check_text(text, 'r.json')
    assert [r['name'] for r in ruleset['rules']] == ['Good']
    sentences = [p[1] for p in problems]
    assert any('Rule 2 "Bad op", requirement 1:' in s for s in sentences)
    assert any('unknown field "colour"' in s for s in sentences)
    assert any('Rule 3 "No requirements" has no requirements.' == s for s in sentences)
    assert any('same name as rule 1' in s for s in sentences)
    assert any('Rule 5 has no name.' == s for s in sentences)
    assert any('severity must be' in s for s in sentences)
    assert any('require_mode must be' in s for s in sentences)
    bad_line = [p for p in problems if 'Bad op' in p[1]][0][0]
    assert text.splitlines()[bad_line - 1].strip().startswith('"name": "Bad op"')


def test_structure_problems():
    assert validator.check_text('[]')[1][0][1].startswith('The file must hold')
    assert 'needs a "rules" list' in validator.check_text('{"rules": []}')[1][0][1]
    assert 'not a Playground validation file' in validator.check_text('{"format": "x", "rules": [1]}')[1][0][1]


def _getter(values):
    def get(category, prop):
        key = (category, prop)
        if key in values:
            return True, values[key]
        return False, None
    return get


def _rule(**kw):
    raw = {'name': 'R', 'require': ['Element > System Name is not empty']}
    raw.update(kw)
    rule, problems = validator.normalise_rule(raw, 1)
    assert problems == [], problems
    return rule


def test_check_item_applies_passes_and_explains():
    rule = _rule(applies_to=['Element > Category = Ducts'])
    assert validator.check_item(rule, _getter({('Element', 'Category'): 'Walls'})) == (False, True, [])
    duct = {('Element', 'Category'): 'Ducts', ('Element', 'System Name'): 'SA'}
    assert validator.check_item(rule, _getter(duct)) == (True, True, [])
    blank = {('Element', 'Category'): 'Ducts', ('Element', 'System Name'): ' '}
    assert validator.check_item(rule, _getter(blank)) == (True, False, ['System Name is empty'])
    missing = {('Element', 'Category'): 'Ducts'}
    assert validator.check_item(rule, _getter(missing))[2] == ['System Name is missing']
    regex = _rule(require=['Element > Comments matches ^[A-Z]{3}-\\d{3}$'])
    applies, passed, problems = validator.check_item(regex, _getter({('Element', 'Comments'): 'ahu 1'}))
    assert not passed and problems == ['Comments is "ahu 1", expected matches ^[A-Z]{3}-\\d{3}$']
    ranged = _rule(require=['Element > Offset between 0 and 3'])
    assert validator.check_item(ranged, _getter({('Element', 'Offset'): 2.5}))[1] is True
    assert validator.check_item(ranged, _getter({('Element', 'Offset'): 4.0}))[1] is False
    listed = _rule(require=['Element > Phase is one of Existing, New'])
    assert validator.check_item(listed, _getter({('Element', 'Phase'): 'new'}))[1] is True
    anyof = _rule(require=['Element > Level is not empty', 'Element > Base Constraint is not empty'],
                  require_mode='any')
    assert validator.check_item(anyof, _getter({('Element', 'Base Constraint'): 'L1'}))[1] is True
    problems = validator.check_item(anyof, _getter({}))[2]
    assert problems == ['None of the 2 options: Level is missing; Base Constraint is missing']


def test_tallies_rows_and_html():
    rule = _rule(name='Ducts <sys>', description='Why & how')
    result = validator.new_result(rule, 'Set')
    validator.add_outcome(result, 'a', True, True, [])
    validator.add_outcome(result, 'b', True, False, ['System Name is empty'])
    validator.add_outcome(result, 'c', False, True, [])
    assert (result['checked'], result['passed'], result['failed']) == (2, 1, 1)
    assert validator.pass_rate(result) == 0.5
    empty = validator.new_result(_rule(name='Empty'), 'Set')
    assert validator.pass_rate(empty) is None
    assert validator.totals([result, empty]) == {'rules': 2, 'checked': 2, 'passed': 1, 'failed': 1,
                                                 'failing_rules': 1}
    assert validator.summary_rows([result])[0] == ['Ducts <sys>', 'Set', 'error', 2, 1, 1, 0.5]
    html = validator.summary_html([result, empty])
    assert 'Ducts &lt;sys&gt;' in html and 'Why &amp; how' in html
    assert 'width:50%' in html and '50%' in html and 'Nothing to check' in html
    rows = validator.failure_rows([result])
    assert rows == [('Ducts <sys>', 'b', 'System Name is empty')]
    table = validator.failures_html(rows, lambda item: '<a>%s</a>' % item, lambda item: 'M.rvt', 900)
    assert '<a>b</a>' in table and 'Showing the first 1 of 900 failures' in table
    assert validator.set_name('A/B: c') == 'A-B: c'


def test_folder_starter_and_loading():
    folder = _compat.tmpdir('g2_validator')
    assert validator.ensure_starter(folder) == os.path.join(folder, validator.STARTER_FILE)
    assert validator.ensure_starter(folder) is None
    with io.open(os.path.join(folder, 'broken.json'), 'w', encoding='utf-8') as handle:
        handle.write(u'{"rules": [ }')
    sets = validator.load_folder(folder)
    assert [s['file'] for s in sets] == ['broken.json', validator.STARTER_FILE]
    assert sets[0]['rules'] == [] and sets[0]['problems'][0].startswith('broken.json, line 1')
    assert sets[1]['problems'] == [] and sets[1]['rules']


def test_rules_folder_under_team_root():
    previous = paths.redirect(_compat.tmpdir('g2_validator_root'))
    try:
        folder = validator.rules_folder()
        assert folder.endswith(os.path.join('rules', 'validation')) and os.path.isdir(folder)
    finally:
        paths.redirect(previous)


def test_run_rules_through_fakes():
    doc, n = pf.tree()
    with pf.Fake(doc, 'Meters'):
        ruleset, problems = validator.check_text(json.dumps({'rules': [
            {'name': 'Walls have a mark', 'applies_to': ['Element > Category = Walls'],
             'require': ['Element > Mark is not empty']},
            {'name': 'Long things', 'applies_to': ['Element > Length exists'],
             'require': ['Element > Length >= 2'], 'enabled': True},
            {'name': 'Off', 'require': ['Item > Name exists'], 'enabled': False},
        ]}), 'x.json')
        assert problems == []
        objs = propindex.scope_items('model', 'objects', doc)
        results = validator.run_rules([ruleset], objs, propindex.Reader(doc, 'auto'))
        assert [r['rule'] for r in results] == ['Walls have a mark', 'Long things']
        walls, lengths = results
        assert (walls['checked'], walls['passed'], walls['failed']) == (2, 1, 1)
        assert walls['failures'][0][0] is n['Wall 2']
        assert walls['failures'][0][1] == ['Mark is empty']
        assert (lengths['checked'], lengths['failed']) == (3, 1)
        assert lengths['failures'][0][1][0].startswith('Length is "1.5", expected >= 2')


def test_starter_text_reads_top_down():
    text = validator.starter_text()
    lines = text.splitlines()
    assert lines[1].strip().startswith('"format"') and lines[2].strip().startswith('"version"')
    assert text.index('"name": "Ducts have a system name"') < text.index('"applies_to"')
    assert text.endswith('}' + chr(10))

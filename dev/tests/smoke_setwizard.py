# -*- coding: utf-8 -*-
"""Search Set Wizard window under IronPython + WPF: built from a fake source, rows added
and removed, values typed, counted and accepted through WizardState, never shown."""
import _compat

_compat.require_ironpython()

from namo import setwizard as sw  # noqa: E402


class FakeSource(object):
    total = 600

    def __init__(self):
        self.sample = sw.Sample([
            [('Element', 'Category', 'Ducts'), ('Element', 'Level', 'Level 3'), ('Element', 'Width', 0.4)],
            [('Element', 'Category', 'Pipes'), ('Element', 'Level', 'Level 3'), ('Item', 'Name', 'P1')],
        ], total=2)
        self.counted = []

    def categories(self):
        return self.sample.categories()

    def properties(self, category):
        return self.sample.properties(category)

    def observed(self, category, prop):
        return self.sample.observed(category, prop)

    def kinds(self):
        return self.sample.kinds()

    def count(self, model):
        self.counted.append(sw.queries(model, self.kinds()))
        return [412] * len(self.counted[-1]), 412, 1.25


def build(model=None):
    source = FakeSource()
    win = sw.build_window(model or sw.new_model(), source, ['Arch.nwc', 'MEP.nwc'], ['Playground', 'By Level'])
    return win, win.Tag, source


def set_row(state, index, category, prop, op_index, value):
    _g, _r, bag = state.rows[index]
    bag.category.Text = category
    bag.prop.Text = prop
    bag.op.SelectedIndex = op_index
    bag.value.Text = value


def test_builds_with_one_empty_row():
    win, state, _source = build()
    assert len(state.rows) == 1
    bag = state.rows[0][2]
    assert bag.category.Items.Count == 2           # Element, Item from the sample
    assert bag.op.Items.Count == len(sw.find_query.NATIVE_OPS)


def test_rows_count_and_accept():
    win, state, source = build()
    set_row(state, 0, 'Element', 'Category', 0, 'Ducts')
    state.add_row(0)
    assert len(state.rows) == 2
    set_row(state, 1, 'Element', 'Level', 0, 'Level 3')
    state.count()
    assert len(source.counted) == 1 and state.counted['union'] == 412
    state.name_box.Text = ''
    state.accept()
    model = state.result
    assert model['name'] == 'Ducts on Level 3'      # named from the values
    assert model['groups'][0][1]['value'] == 'Level 3'
    assert model['folder'] == 'Playground'


def test_invalid_rows_block_accept():
    win, state, source = build()
    set_row(state, 0, 'Element', 'Width', 4, 'wide')   # greater than + text
    state.accept()
    assert state.result is None
    assert state.rows[0][2].error.Text == 'Greater than needs a number.'
    state.count()
    assert source.counted == []


def test_or_sets_and_remove():
    model = sw.new_model()
    model['groups'] = [[sw.new_condition('Element', 'Category', 'equals', 'Ducts')],
                       [sw.new_condition('Element', 'Category', 'equals', 'Pipes')]]
    win, state, source = build(model)
    assert len(state.rows) == 2
    state.count()
    assert len(source.counted[-1]) == 2
    state.remove_row(1, 0)
    assert len(state.model['groups']) == 1 and len(state.rows) == 1


def test_remembered_model_restores():
    model = sw.new_model()
    model['scope'] = 'models'
    model['models'] = ['MEP.nwc']
    model['groups'] = [[sw.new_condition('Element', 'Level', 'equals', 'Level 3')]]
    win, state, _source = build(model)
    assert state.model['scope'] == 'models'
    assert state.rows[0][2].value.Text == 'Level 3'
    assert state.rows[0][2].value.Items.Count == 1  # observed values loaded for the row

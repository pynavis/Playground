# -*- coding: utf-8 -*-
"""namo.propindex: value display, the index, pivots, and the API half through a fake
Navisworks layer with typed VariantData (reused by the other G2 tests:
`import test_propindex as pf`)."""
import datetime

import _compat
import test_items as nav

from namo import items, propindex

# ---- fake typed property layer -------------------------------------------------------

TYPE_CODES = dict((name, index) for index, (name, _kind) in enumerate(propindex.TYPE_KINDS))


class VariantDataType(object):
    pass


for _name, _code in TYPE_CODES.items():
    setattr(VariantDataType, _name, _code)


class Variant(object):
    """A VariantData stand-in: DataType is the int code of a VariantDataType name."""

    def __init__(self, type_name, value):
        self.DataType = TYPE_CODES[type_name]
        self.type_name = type_name
        self.value = value

    def ToDisplayString(self):
        return self.value

    def ToIdentifierString(self):
        return self.value

    def ToAnyDouble(self):
        return float(self.value)

    def ToInt32(self):
        return int(self.value)

    def ToInt64(self):
        return int(self.value)

    def ToNat32(self):
        return int(self.value)

    def ToNat64(self):
        return int(self.value)

    def ToBoolean(self):
        return bool(self.value)

    def ToNamedConstant(self):
        return nav._Ns(DisplayName=self.value, Name=self.value)

    def ToDateTime(self):
        return self.value

    def ToPoint3D(self):
        x, y, z = self.value
        return nav.Point3D(x, y, z)

    def ToString(self):
        return '%s:%s' % (self.type_name, self.value)


def v(value):
    """A Variant for a plain python value: str DisplayString, bool Boolean, int Int32,
    float Double; ('Length', 3.0) style tuples pick another type."""
    if isinstance(value, Variant):
        return value
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        names = {'Length': 'DoubleLength', 'Area': 'DoubleArea', 'Volume': 'DoubleVolume',
                 'Angle': 'DoubleAngle', 'Id': 'IdentifierString', 'Date': 'DateTime',
                 'Named': 'NamedConstant', 'Point': 'Point3D', 'None': 'None'}
        return Variant(names.get(value[0], value[0]), value[1])
    if isinstance(value, bool):
        return Variant('Boolean', value)
    if isinstance(value, int):
        return Variant('Int32', value)
    if isinstance(value, float):
        return Variant('Double', value)
    if value is None:
        return Variant('None', None)
    return Variant('DisplayString', value)


class Prop(object):
    def __init__(self, name, value):
        self.DisplayName = name
        self.Name = name
        self.Value = v(value)


class Cat(object):
    def __init__(self, name, props, editable=False, internal=None):
        self.DisplayName = name
        self.Name = internal or name
        self.IsEditable = editable
        self.Properties = props


class Cats(list):
    def FindPropertyByDisplayName(self, category, prop):
        for cat in self:
            if cat.DisplayName == category:
                for p in cat.Properties:
                    if p.DisplayName == prop:
                        return p
        return None

    def FindCategoryByDisplayName(self, category):
        for cat in self:
            if cat.DisplayName == category:
                return cat
        return None


class Item(nav.ModelItem):
    """test_items.ModelItem with typed properties: props {(cat, prop): value}; a cat
    named in `editable` reads as a user (custom) tab."""

    def __init__(self, name, children=(), editable=(), guid=None, **kw):
        nav.ModelItem.__init__(self, name, children, **kw)
        self.editable = set(editable)
        self.InstanceGuid = guid
        self.IsRequired = False
        self.IsFrozen = False
        self.ClassName = 'Lc' + self.ClassDisplayName

    @property
    def PropertyCategories(self):
        order = []
        grouped = {}
        for (cat, name), value in sorted(self.props.items()):
            if cat not in grouped:
                grouped[cat] = []
                order.append(cat)
            grouped[cat].append(Prop(name, value))
        return Cats(Cat(c, grouped[c], editable=c in self.editable,
                        internal='LcOaPropOverrideCat' if c in self.editable else None)
                    for c in order)

    @property
    def Descendants(self):
        for node in self.DescendantsAndSelf:
            if node is not self:
                yield node


class Fake(object):
    """with Fake(doc) as f: test_items.FakeNav plus VariantDataType and units."""

    def __init__(self, doc, units='Meters'):
        self.nav = nav.FakeNav(doc)
        self.doc = doc
        doc.Units = units
        doc.FileName = r'C:\Jobs\Tower.nwf'
        doc.Title = 'Tower.nwf'

    def __enter__(self):
        self.nav.__enter__()
        self.nav.Api.VariantDataType = VariantDataType
        self.Api = self.nav.Api
        return self

    def __exit__(self, *exc):
        return self.nav.__exit__(*exc)


UID = '60f91daf-3dd7-4283-a86d-24137b73f3da-00000065'


def tree():
    """ARCH: two walls (objects) with geometry leaves; MEP: a duct, a hidden pipe."""
    w1g = Item('Wall 1 solid', geometry=True, box=((0, 0, 0), (1, 5, 3)))
    w2g = Item('Wall 2 solid', geometry=True, box=((5, 0, 0), (6, 5, 3)))
    w1 = Item('Wall 1', [w1g], klass='Wall', guid='{AAAA0000-0000-0000-0000-000000000001}',
              props={('Element', 'Category'): 'Walls', ('Element ID', 'Value'): '101',
                     ('Element', 'UniqueId'): UID, ('Element', 'Length'): ('Length', 3.0),
                     ('Element', 'Mark'): 'W1', ('Item', 'Name'): 'Wall 1'})
    w2 = Item('Wall 2', [w2g], klass='Wall',
              props={('Element', 'Category'): 'Walls', ('Element ID', 'Value'): '102',
                     ('Element', 'Length'): ('Length', 1.5), ('Element', 'Mark'): '',
                     ('Item', 'Name'): 'Wall 2', ('Playground', 'Status'): 'Open'},
              editable=('Playground',))
    w1g.object = w1
    w2g.object = w2
    level = Item('Level 1', [w1, w2])
    arch_root = Item('ARCH.nwc', [level])
    dg = Item('Duct solid', geometry=True, box=((2, 2, 2), (4, 2.5, 2.5)))
    duct = Item('Duct', [dg], props={('Element', 'Category'): 'Ducts', ('Element', 'System Name'): 'SA-1',
                                     ('Element', 'Length'): ('Length', 2.0), ('Item', 'Name'): 'Duct'})
    dg.object = duct
    pipe = Item('Pipe', geometry=True, hidden=True, box=((9, 9, 9), (10, 10, 10)),
                props={('Element', 'Category'): 'Pipes', ('Item', 'Name'): 'Pipe'})
    mep_root = Item('MEP.nwc', [duct, pipe])
    arch = nav.Model(r'C:\Models\ARCH.rvt', arch_root)
    mep = nav.Model(r'C:\Models\MEP.rvt', mep_root)
    arch_root.Model, arch_root.HasModel = arch, True
    mep_root.Model, mep_root.HasModel = mep, True
    doc = nav.Document([arch, mep])
    named = dict((n.DisplayName, n) for root in (arch_root, mep_root) for n in root.DescendantsAndSelf)
    return doc, named


# ---- pure ----------------------------------------------------------------------------


def test_default_scope_and_options():
    assert propindex.default_scope(True, 'model') == 'selection'
    assert propindex.default_scope(False, 'visible') == 'visible'
    assert propindex.default_scope(False, 'selection') == 'model'
    assert propindex.default_scope(False, None) == 'model'
    assert [v for _l, v in propindex.scope_options(False)] == ['visible', 'model']
    assert [v for _l, v in propindex.scope_options(True)] == ['selection', 'visible', 'model']


def test_scope_text_and_pairs():
    assert propindex.scope_text('model', 'objects', 1234) == '1,234 objects in the whole model'
    assert propindex.scope_text('selection', 'geometry', 1) == '1 geometry item in the current selection'
    assert 'sampled' in propindex.scope_text('visible', 'objects', 5, sampled=True)
    assert propindex.split_pair('Element > Category') == ('Element', 'Category')
    assert propindex.split_pair('Element>Category') == ('Element', 'Category')
    assert propindex.split_pair('Mark') == ('', 'Mark')
    assert propindex.split_pair('  ') is None


def test_display_text_kinds():
    metric = propindex.context_for('Millimeters')
    imperial = propindex.context_for('Feet')
    assert propindex.display_text('text', '  Walls ') == 'Walls'
    assert propindex.display_text('text', '   ') == propindex.NO_VALUE
    assert propindex.display_text('none', None) == propindex.NO_VALUE
    assert propindex.display_text('bool', True) == 'Yes'
    assert propindex.display_text('int', 123456) == '123456'
    assert propindex.display_text('float', 2.50) == '2.5'
    assert propindex.display_text('length', 3.0, metric) == '3,000 mm'
    assert propindex.display_text('length', 0.3048 * 12.5, imperial) == '12\' 6"'
    assert propindex.display_text('length', 1.5, propindex.context_for('Meters')) == '1.5 m'
    assert propindex.display_text('area', 2.0, metric).startswith('2 m')
    assert propindex.display_text('angle', 3.141592653589793) == u'180\u00b0'
    assert propindex.display_text('date', datetime.datetime(2026, 10, 5)) == '2026-10-05'
    assert propindex.display_text('date', datetime.datetime(2026, 10, 5, 14, 30)) == '2026-10-05 14:30'
    assert propindex.display_text('point', (1.0, 2.5, -3.0)) == '1, 2.5, -3'


def test_plain_value_converts_quantities():
    ctx = propindex.context_for('Millimeters')
    assert _compat.approx(propindex.plain_value('length', 3.0, ctx), 3000.0)
    assert propindex.plain_value('text', 'x', ctx) == 'x'
    assert propindex.plain_value('date', datetime.datetime(2026, 1, 2), ctx) == '2026-01-02'
    assert propindex.plain_value('int', 5, ctx) == 5
    assert propindex.plain_value('none', None, ctx) is None


def test_index_counts_distinct_and_missing():
    index = propindex.PropIndex()
    index.add([('Element', 'Category', 'text', 'DisplayString', 'Walls'),
               ('Element', 'Mark', 'text', 'DisplayString', 'W1'),
               ('Element', 'Mark', 'text', 'DisplayString', 'W1')])   # duplicate counts once
    index.add([('Element', 'Category', 'text', 'DisplayString', 'Walls')])
    index.add([('Element', 'Category', 'text', 'DisplayString', 'Ducts'),
               ('Item', 'Name', 'text', 'DisplayString', 'Duct')])
    assert index.total == 3
    assert index.categories() == [('Element', 3, 2), ('Item', 1, 1)]
    assert index.properties('Element') == [('Category', 3, 2, 'text', False), ('Mark', 1, 1, 'text', False)]
    assert index.values('Element', 'Category') == [('Walls', 2), ('Ducts', 1)]
    assert index.values('Element', 'Mark') == [('W1', 1), (propindex.MISSING, 2)]
    assert index.values('Nope', 'X') == [(propindex.MISSING, 3)]
    assert index.kind_of('Element', 'Category') == 'text'
    assert index.vtype_of('Element', 'Category') == 'DisplayString'
    rows = index.rows()
    assert rows[0][:4] == ['Element', 'Category', 'Walls', 2]
    assert _compat.approx(rows[0][4], 2.0 / 3)
    assert index.pairs() == [('Element', 'Category'), ('Element', 'Mark'), ('Item', 'Name')]


def test_index_caps_distinct_values_and_mixed_kinds():
    index = propindex.PropIndex(max_values=2)
    for value in ('a', 'b', 'c', 'c', 'a'):
        index.add([('T', 'P', 'text', 'DisplayString', value)])
    index.add([('T', 'P', 'int', 'Int32', '7')])
    stats = index.stats('T', 'P')
    assert stats['capped'] and stats['other'] == 3
    assert stats['kind'] == 'mixed'
    values = index.values('T', 'P')
    assert values[-1] == ('(other values)', 3)
    assert index.properties('T')[0][4] is True


def test_value_order_is_natural_on_ties():
    rows = propindex.sort_counts([('Level 10', 2), ('Level 2', 2), ('B', 5)])
    assert rows == [('B', 5), ('Level 2', 2), ('Level 10', 2)]


def test_pivot_one_and_two_levels():
    one = propindex.pivot([('Walls',), ('Ducts',), ('Walls',)])
    assert one['levels'] == 1 and one['total'] == 3
    assert [(g['key'], g['count'], g['indices']) for g in one['groups']] == [
        (('Walls',), 2, [0, 2]), (('Ducts',), 1, [1])]
    two = propindex.pivot([('Walls', 'L1'), ('Ducts', 'L1'), ('Walls', 'L2'), ('Walls', 'L1'),
                           ('Ducts', 'L2'), ('Ducts', 'L2')])
    keys = [(g['key'], g['count']) for g in two['groups']]
    # both firsts total 3: natural order Ducts before Walls; then count desc
    assert keys == [(('Ducts', 'L2'), 2), (('Ducts', 'L1'), 1), (('Walls', 'L1'), 2), (('Walls', 'L2'), 1)]
    assert propindex.first_totals(two['groups']) == [('Ducts', 3), ('Walls', 3)]
    assert propindex.pivot([])['groups'] == []


def test_share_and_tsv():
    assert propindex.share_text(1, 3) == '33.3%'
    assert propindex.share_text(2, 2) == '100%'
    assert propindex.share_text(1, 0) == '0%'
    text = propindex.tsv([['a\tb', 'c\nd'], [1, None]], ['H1', 'H2'])
    assert text == 'H1\tH2\r\na b\tc d\r\n1\t'


# ---- API half --------------------------------------------------------------------------


def test_reader_coerces_every_kind():
    doc, n = tree()
    with Fake(doc, 'Millimeters'):
        reader = propindex.Reader(doc, report_units='auto')
        table = reader.table
        assert propindex.coerce(v(('Length', 2.0)), table) == ('length', 'DoubleLength', 2.0)
        assert propindex.coerce(v(('Id', 'abc')), table) == ('text', 'IdentifierString', 'abc')
        assert propindex.coerce(v(('Named', 'Basic')), table) == ('text', 'NamedConstant', 'Basic')
        assert propindex.coerce(v(True), table) == ('bool', 'Boolean', True)
        assert propindex.coerce(v(7), table) == ('int', 'Int32', 7)
        assert propindex.coerce(v(('Point', (1, 2, 3))), table)[2] == (1, 2, 3)
        assert propindex.coerce(None, table)[0] == 'none'
        rows = reader.all(n['Wall 1'])
        assert ('Element', 'Length', 'length', 'DoubleLength', '3,000 mm') in rows
        assert reader.one(n['Wall 1'], 'Element', 'Mark') == (True, 'text', 'W1')
        assert reader.one(n['Wall 1'], 'Element', 'Nope') == (False, 'none', None)
        assert reader.one(n['Wall 1'], '', 'UniqueId') == (True, 'text', UID)
        assert reader.text(n['Wall 2'], 'Element', 'Mark') == propindex.NO_VALUE
        assert reader.text(n['Duct'], 'Element', 'Mark') == propindex.MISSING
        get = reader.getter(n['Wall 1 solid'], fallback_to_object=True)
        exists, value = get('Element', 'Length')
        assert exists and _compat.approx(value, 3000.0)
        assert reader.getter(n['Wall 1 solid'])('Element', 'Length') == (False, None)


def test_quantities_are_read_in_the_source_model_units():
    # Refit: a Revit export stores lengths in feet, areas in square feet. The reader
    # converts from the item's own Model.Units, not from an assumed SI value.
    doc, n = tree()
    n['Wall 1'].props[('Element', 'Area')] = ('Area', 100.0)
    with Fake(doc, 'Feet'):
        for model in doc.Models:
            model.Units = 'Feet'
        reader = propindex.Reader(doc, report_units='auto')
        assert reader.text(n['Wall 1'], 'Element', 'Length') == "3' 0" + '"'
        assert ('Element', 'Length', 'length', 'DoubleLength', "3' 0" + '"') in reader.all(n['Wall 1'])
        exists, kind, value = reader.one(n['Wall 1'], 'Element', 'Length')
        assert exists and kind == 'length' and _compat.approx(value, 3.0 * 0.3048)
        assert _compat.approx(propindex.plain_value(kind, value, reader.ctx), 3.0)
        assert reader.text(n['Wall 1'], 'Element', 'Area').startswith('100 ')
        # a metric model appended to the same feet document keeps its own units
        doc.Models[1].Units = 'Millimeters'
        mixed = propindex.Reader(doc, report_units='m')
        assert mixed.text(n['Duct'], 'Element', 'Length') == '0.002 m'
        assert mixed.text(n['Wall 1'], 'Element', 'Length') == '0.914 m'
    assert _compat.approx(propindex.to_si('volume', 1.0, 0.3048), 0.3048 ** 3)
    assert propindex.to_si('angle', 1.0, 0.3048) == 1.0
    assert propindex.source_factor_for('Feet') == 0.3048
    assert propindex.source_factor_for('Bananas', 2.0) == 2.0


def test_scope_items_for_each_scope():
    doc, n = tree()
    with Fake(doc):
        model = propindex.scope_items('model', 'objects', doc)
        assert [i.DisplayName for i in model] == ['Wall 1', 'Wall 2', 'Duct', 'Pipe']
        visible = propindex.scope_items('visible', 'objects', doc)
        assert [i.DisplayName for i in visible] == ['Wall 1', 'Wall 2', 'Duct']
        geometry = propindex.scope_items('visible', 'geometry', doc)
        assert [i.DisplayName for i in geometry] == ['Wall 1 solid', 'Wall 2 solid', 'Duct solid']
        doc.CurrentSelection.SelectedItems = [n['Level 1']]
        sel = propindex.scope_items('selection', 'objects', doc)
        assert [i.DisplayName for i in sel] == ['Wall 1', 'Wall 2']
        capped = propindex.scope_items('visible', 'objects', doc, budget=2)
        assert len(capped) == 2 and capped.sampled
        doc.CurrentSelection.SelectedItems = []
        assert propindex.scope_items('selection', 'objects', doc) == []


def test_scan_find_and_read_pairs():
    doc, n = tree()
    with Fake(doc):
        objs = propindex.scope_items('model', 'objects', doc)
        ticks = []
        index = propindex.scan(objs, doc, tick=lambda done, total: ticks.append((done, total)))
        assert ticks[-1] == (4, 4)
        assert index.total == 4
        assert index.values('Element', 'Category') == [('Walls', 2), ('Ducts', 1), ('Pipes', 1)]
        assert ('Playground', 1, 1) in index.categories()
        found = propindex.find_matching(objs, 'Element', 'Category', 'Walls', doc)
        assert [i.DisplayName for i in found] == ['Wall 1', 'Wall 2']
        missing = propindex.find_matching(objs, 'Element', 'Mark', propindex.MISSING, doc)
        assert [i.DisplayName for i in missing] == ['Duct', 'Pipe']
        pairs = propindex.read_pairs(objs, [('Element', 'Category'), ('Element', 'Mark')], doc)
        assert pairs == [('Walls', 'W1'), ('Walls', propindex.NO_VALUE), ('Ducts', propindex.MISSING),
                         ('Pipes', propindex.MISSING)]
        _compat.raises(items.Cancelled, propindex.scan, objs, doc, lambda d, t: False)


def test_cache_remember_and_invalidate():
    from namo import session
    doc, n = tree()
    with Fake(doc):
        session.clear('propindex')
        objs = propindex.scope_items('model', 'objects', doc)
        index = propindex.scan(objs, doc)
        propindex.remember(index, objs, 'model', 'objects', 1000, doc)
        entry = propindex.cached(doc)
        assert entry is not None and entry['index'] is index
        assert propindex.cached(doc, scope='visible') is None
        choices = propindex.property_choices(doc)
        assert ('Element', 'Category', 4) in choices
        propindex.invalidate()
        assert propindex.cached(doc) is None
        fresh = propindex.property_choices(doc)
        assert ('Element', 'Category', 4) in fresh
        session.clear('propindex')

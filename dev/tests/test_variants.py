# -*- coding: utf-8 -*-
"""namo.variants: property values read without pynavis.props tripping on typed doubles.

pynavis.props._variant_to_python calls VariantData.ToDouble() for every IsDouble* kind,
but Navisworks only allows ToDouble() on a plain IsDouble value: a length, area, volume
or angle raises "Not supported if '!IsDouble'" (Select Similar on a selected item, found
under pynavis run on 2026-10-09). Each typed double has its own To* reader."""
import sys
import types

import _compat  # noqa: F401 (puts the library on sys.path)

from namo import variants


class FakeVariant(object):
    """Only the probe named in `kind` is True; ToDouble() refuses unless kind is IsDouble."""

    def __init__(self, kind, value):
        self.kind = kind
        self.value = value

    def __getattr__(self, name):
        if name.startswith('Is'):
            return name == self.kind
        raise AttributeError(name)

    def ToDouble(self):
        if self.kind != 'IsDouble':
            raise SystemError("Not supported if '!IsDouble'")
        return self.value

    def ToDoubleLength(self):
        assert self.kind == 'IsDoubleLength'
        return self.value

    def ToDoubleArea(self):
        assert self.kind == 'IsDoubleArea'
        return self.value

    def ToDoubleVolume(self):
        assert self.kind == 'IsDoubleVolume'
        return self.value

    def ToDoubleAngle(self):
        assert self.kind == 'IsDoubleAngle'
        return self.value

    def ToDisplayString(self):
        return self.value


class FakeProp(object):
    def __init__(self, name, value):
        self.DisplayName = name
        self.Name = name
        self.Value = value


class FakeCategory(object):
    def __init__(self, name, props):
        self.DisplayName = name
        self.Name = name
        self.Properties = props


class FakeCategories(list):
    def FindPropertyByDisplayName(self, category, prop):
        for cat in self:
            if cat.DisplayName == category:
                for p in cat.Properties:
                    if p.DisplayName == prop:
                        return p
        return None

    FindPropertyByName = FindPropertyByDisplayName


class FakeItem(object):
    def __init__(self, categories):
        self.PropertyCategories = FakeCategories(categories)


def _with_fake_pynavis(body):
    """pynavis.props stand-in whose conversion has the real module's ToDouble() bug."""
    fake = types.ModuleType('pynavis.props')

    def convert(variant):
        if variant.IsDisplayString:
            return variant.ToDisplayString()
        if any(getattr(variant, n) for n in ('IsDouble', 'IsDoubleLength', 'IsDoubleArea',
                                             'IsDoubleVolume', 'IsDoubleAngle')):
            return float(variant.ToDouble())
        return 'other'
    fake._variant_to_python = convert
    parent = sys.modules.get('pynavis')
    created = parent is None
    if created:
        parent = types.ModuleType('pynavis')
        sys.modules['pynavis'] = parent
    saved_module = sys.modules.get('pynavis.props')
    saved_attr = getattr(parent, 'props', None)
    sys.modules['pynavis.props'] = fake
    parent.props = fake
    try:
        body()
    finally:
        if saved_module is None:
            sys.modules.pop('pynavis.props', None)
        else:
            sys.modules['pynavis.props'] = saved_module
        if saved_attr is None:
            try:
                delattr(parent, 'props')
            except AttributeError:
                pass
        else:
            parent.props = saved_attr
        if created:
            sys.modules.pop('pynavis', None)


def test_typed_doubles_read_through_their_own_reader():
    def body():
        for kind in ('IsDoubleLength', 'IsDoubleArea', 'IsDoubleVolume', 'IsDoubleAngle', 'IsDouble'):
            value = variants.to_python(FakeVariant(kind, 2.5))
            assert value == 2.5 and isinstance(value, float), kind
        assert variants.to_python(FakeVariant('IsDisplayString', 'Wall')) == 'Wall'
    _with_fake_pynavis(body)


def test_all_of_and_get_survive_a_length():
    item = FakeItem([FakeCategory('Element', [FakeProp('Name', FakeVariant('IsDisplayString', 'Duct')),
                                              FakeProp('Length', FakeVariant('IsDoubleLength', 4.0))])])

    def body():
        rows = variants.all_of(item)
        assert rows == [{'category': 'Element', 'property': 'Name', 'value': 'Duct'},
                        {'category': 'Element', 'property': 'Length', 'value': 4.0}]
        assert variants.get(item, 'Element', 'Length') == 4.0
        assert variants.get(item, 'Element', 'Missing') is None
        assert variants.get(item, 'Element', 'Length', by_display=False) == 4.0
    _with_fake_pynavis(body)

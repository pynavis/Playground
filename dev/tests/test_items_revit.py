# -*- coding: utf-8 -*-
"""items.revit_element / revit_ids prefer the real Revit element over a nested part,
whose Element ID is the family TYPE's id (field-measured in pyNavis' Select by IDs)."""
import _compat  # noqa: F401

from namo import items


class Prop(object):
    def __init__(self, display, value):
        self.DisplayName = display
        self.Name = display
        self.Value = value


class Cat(object):
    def __init__(self, name, display, props):
        self.Name = name
        self.DisplayName = display
        self.Properties = props


class Node(object):
    def __init__(self, cats, parent=None):
        self.PropertyCategories = cats
        self.Parent = parent

    def Equals(self, other):
        return self is other

    def FindFirstObjectAncestor(self):
        return self


def test_revit_element_climbs_to_element_category():
    element = Node([Cat('LcRevitData_Element', 'Element', [Prop('Id', 1001)])])
    part = Node([Cat('LcRevitData_Element_Type', 'Element ID', [Prop('Value', 77)])], parent=element)
    assert items.revit_element(part) is element
    assert items.revit_element(element) is element


def test_revit_element_none_outside_revit():
    root = Node([Cat('LcOaNode', 'Item', [])])
    leaf = Node([Cat('LcOaNode', 'Item', [])], parent=root)
    assert items.revit_element(leaf) is None

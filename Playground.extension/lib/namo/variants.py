# -*- coding: utf-8 -*-
"""Property values as Python values, the way pynavis.props reads them, minus one trap.

    from namo import variants
    variants.to_python(prop.Value)          # str / int / float / bool / datetime / tuple
    variants.get(item, 'Element', 'Length') # one property by display name, or None
    variants.all_of(item)                   # [{'category', 'property', 'value'}]

pynavis.props._variant_to_python calls VariantData.ToDouble() for every IsDouble* kind,
but Navisworks allows ToDouble() only on a plain IsDouble value: a length, area, volume
or angle raises "Not supported if '!IsDouble'" (found running Select Similar under
pynavis run, 2026-10-09). Those four kinds have their own readers (ToDoubleLength and
so on), tried here first; everything else goes through pynavis.props unchanged.

Use these instead of pynavis.props.get / all_of anywhere in Playground.
"""

TYPED_DOUBLES = (('IsDoubleLength', 'ToDoubleLength'), ('IsDoubleArea', 'ToDoubleArea'),
                 ('IsDoubleVolume', 'ToDoubleVolume'), ('IsDoubleAngle', 'ToDoubleAngle'))


def to_python(variant):
    """The Python value of a VariantData (see pynavis.props._variant_to_python), with
    lengths, areas, volumes and angles read as floats through their own readers."""
    for probe, reader in TYPED_DOUBLES:
        if getattr(variant, probe, False):
            return float(getattr(variant, reader)())
    from pynavis import props
    return props._variant_to_python(variant)


def get(item, category, prop, by_display=True):
    """One property's value on item, or None when the category or property is absent
    (pynavis.props.get's lookup: display names, or internal names with by_display False).
    pynavis.props.get answers first; only when it raises (the typed-double trap) is the
    property read again here."""
    from pynavis import props
    try:
        if by_display:
            return props.get(item, category, prop)
        return props.get(item, category, prop, by_display=False)
    except Exception:
        pass
    categories = item.PropertyCategories
    finder = categories.FindPropertyByDisplayName if by_display else categories.FindPropertyByName
    found = finder(category, prop)
    if found is None:
        return None
    return to_python(found.Value)


def all_of(item):
    """Every property on item as {'category', 'property', 'value'} rows (display names),
    in PropertyCategories / Properties order (pynavis.props.all_of's shape). As get():
    pynavis first, read again here only when it raises."""
    from pynavis import props
    try:
        return props.all_of(item)
    except Exception:
        pass
    rows = []
    for category in item.PropertyCategories:
        for prop in category.Properties:
            rows.append({
                'category': category.DisplayName,
                'property': prop.DisplayName,
                'value': to_python(prop.Value),
            })
    return rows

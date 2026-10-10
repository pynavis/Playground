# -*- coding: utf-8 -*-
"""Sets which IFC class a category becomes in IFC Exporter, for the whole team."""
from pynavis import output, toast

from namo import ifcexport, store, ui, xchg_common


def run():
    if xchg_common.under_runner():
        return
    holder = store.Store('ifc-class-map', scope='global')
    current = ifcexport.stored_overrides(holder.load({}))
    answer = ui.form('IFC classes', ifcexport.override_fields(current), ok='Save', width=600,
                     intro='These lines win over the built-in mapping for everyone who shares your '
                           'Playground team folder.')
    if answer is None:
        return
    mapping, _errors = ifcexport.parse_overrides(answer['map'])
    try:
        holder.save(dict((category, list(mapping[category])) for category in mapping))
    except (IOError, OSError) as error:
        toast.error('Could not save the IFC classes', str(error))
        return
    if answer['show']:
        output.set_title('IFC classes')
        output.print_md('### Built-in IFC classes')
        output.print_table(ifcexport.builtin_rows(), ['Category', 'IFC class', 'Predefined type'])
    if mapping:
        toast.success('Saved %d IFC class %s' % (len(mapping), 'rule' if len(mapping) == 1 else 'rules'),
                      holder.note or None)
    else:
        toast.success('Using the built-in IFC classes', holder.note or None)


run()

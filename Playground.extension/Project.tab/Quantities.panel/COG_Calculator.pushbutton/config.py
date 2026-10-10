# -*- coding: utf-8 -*-
"""Densities, the bounding-box fill factor and the COG marker for COG Calculator."""
from pynavis import script, toast

from namo import cog, ui


def validate_table(text):
    _table, errors = cog.parse_densities(text)
    return errors[0] if errors else None


def run():
    if ui.is_runner():
        return
    values = script.get_config(cog.DEFAULTS)
    fields = [
        {'kind': 'textarea', 'key': 'densities', 'label': 'Densities in kg/m³, one material word per line',
         'rows': 8, 'default': values.get('densities') or cog.DEFAULTS['densities'], 'validate': validate_table,
         'hint': "The first word found in an object's material (else its category) sets its density."},
        {'kind': 'number', 'key': 'default_density', 'label': 'Density when nothing matches (blank: leave it out)',
         'min': 1, 'default': values.get('default_density'), 'suffix': 'kg/m³'},
        {'kind': 'number', 'key': 'fill_factor', 'label': 'Fill factor for bounding-box estimates', 'min': 0.01,
         'max': 1, 'default': values.get('fill_factor') or 0.6,
         'hint': 'Used when a mesh is not closed: the box volume times this share.'},
        {'kind': 'check', 'key': 'clear', 'label': 'Remove the COG marker from the view now', 'default': False},
    ]
    answer = ui.form('COG Calculator settings', fields, ok='Save', width=520)
    if answer is None:
        return
    values.update({'densities': answer['densities'], 'default_density': answer['default_density'],
                   'fill_factor': answer['fill_factor'] or 0.6})
    script.save_config(values)
    if answer['clear']:
        cog.clear_marker()
        toast.success('Saved, and removed the COG marker')
    else:
        toast.success('Saved the COG settings', '%d materials in the density table.'
                      % len(cog.parse_densities(values['densities'])[0]))


run()

# -*- coding: utf-8 -*-
"""Sets where the Extension Manager reads its registry of extensions."""
import os
import re

from pynavis import script, toast

from namo import extmanager, paths, ui

cfg = script.get_config({'registry': ''})
default = extmanager.default_registry(paths.team_root())


def check(values):
    location = (values.get('registry') or '').strip()
    if location and not re.match(r'^https?://', location, re.IGNORECASE) and not os.path.isfile(location):
        return {'registry': 'Give a web address (https://...) or a JSON file that exists.'}
    return {}


values = ui.form('Extension Manager', [
    {'kind': 'text', 'key': 'registry', 'label': 'Registry (URL or JSON file)', 'default': cfg['registry'],
     'placeholder': default if default != extmanager.PLACEHOLDER else 'https://intranet/pynavis/registry.json',
     'hint': 'Blank uses extension-registry.json in the team folder when there is one.'},
], intro='The registry lists extensions as {"extensions": [{"name", "version", "download", ...}]}.',
    ok='Save', validate=check)
if values is not None:
    script.save_config({'registry': (values['registry'] or '').strip()})
    toast.success('Registry saved', (values['registry'] or '').strip() or 'Using the team folder default.')

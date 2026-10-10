# -*- coding: utf-8 -*-
"""Imports every lib/namo module in a FRESH IronPython engine (run through dev\\ipy.ps1).

The normal test stage runs every test in one engine, so .NET references added by one
test (clr.AddReference('WindowsBase')...) hide a module that forgot them. A fresh engine
behaves like the first click of a Navisworks session. It also proves no namo module needs
Navisworks at import time (the brief forbids importing the API at module level).
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), 'Playground.extension', 'lib', 'namo')

failures = []
names = sorted(n[:-3] for n in os.listdir(LIB) if n.endswith('.py') and n != '__init__.py')
for name in names:
    try:
        __import__('namo.' + name)
    except Exception:
        failures.append((name, traceback.format_exc().strip().splitlines()[-1]))

for name, line in failures:
    print('IMPORT FAILED namo.%s: %s' % (name, line))
print('fresh engine: imported %d of %d namo modules' % (len(names) - len(failures), len(names)))
EXIT_CODE = 1 if failures else 0

# -*- coding: utf-8 -*-
"""Lists every saved template of every Playground report and runs, edits, duplicates, deletes, exports or imports them."""
from pynavis import doc as nwdoc

from namo import reportrunner, xchg_common

if not xchg_common.under_runner():
    reportrunner.open_window(nwdoc.get_doc())

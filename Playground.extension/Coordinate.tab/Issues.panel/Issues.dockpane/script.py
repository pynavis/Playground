# -*- coding: utf-8 -*-
"""The Issues register: list, filter, edit and discuss the model's coordination issues.

Runs once when the panel's content is built (and again on every Reload, against fresh
controls). All behaviour is in lib/namo/issueui.py: mount() first detaches the previous
build's subscriptions and timers (kept in a session holder), then themes pane.xaml,
fills the register of the active document and listens for document changes and for
issue changes made by any Playground tool in this session.
"""

from pynavis import script

from namo import issueui

pane = __pane__

issueui.mount(pane, script.bind(), script.get_logger())

# -*- coding: utf-8 -*-
"""Raises an issue from a template you choose, where you click."""
from namo import issue_stamps

if issue_stamps.ready() is not None:
    choice = issue_stamps.choose_template()
    if choice is not None:             # None: cancelled, say nothing
        issue_stamps.stamp(choice)

# -*- coding: utf-8 -*-
"""Restores the selection you had before this one."""
from pynavis import toast

from namo import sel_history

level, message, detail = sel_history.go(-1)
toast.show(level, message, detail)

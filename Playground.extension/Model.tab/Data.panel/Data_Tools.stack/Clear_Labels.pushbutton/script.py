# -*- coding: utf-8 -*-
"""Removes the labels Property Labels drew in the view."""
from pynavis import toast

from namo import data_labels


def run():
    removed = data_labels.clear()
    if not removed:
        toast.info('No labels to clear', 'Property Labels draws them.')
        return
    toast.success('Cleared %s %s' % ('{:,}'.format(removed), 'label' if removed == 1 else 'labels'))


run()

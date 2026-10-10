# -*- coding: utf-8 -*-
"""namo.progress: the adapter between forms.progress handles and Playground callbacks."""
import _compat  # noqa: F401  (puts lib on sys.path)

from namo import progress


class Cancelled(Exception):
    pass


class FakeHandle(object):
    def __init__(self, cancel_after=None):
        self.updates = []
        self.cancel_after = cancel_after

    def check(self):
        if self.cancel_after is not None and len(self.updates) >= self.cancel_after:
            raise Cancelled()

    def update(self, fraction, label=''):
        self.updates.append((fraction, label))
        return True


def test_adapter_clamps_and_maps_span():
    h = FakeHandle()
    report = progress.adapter(h, start=0.5, span=0.5)
    report(2.0, 'done')
    report(-1, None)
    assert h.updates == [(1.0, 'done'), (0.5, '')]


def test_adapter_raises_cancel_from_check():
    h = FakeHandle(cancel_after=1)
    report = progress.adapter(h)
    report(0.1, 'a')
    error = _compat.raises(Cancelled, report, 0.2, 'b')
    assert type(error).__name__ == 'Cancelled'


def test_tick_formats_counts():
    seen = []
    t = progress.tick(lambda f, l: seen.append((round(f, 3), l)))
    t(1500, 3000)
    t(7, None)
    assert seen == [(0.5, '1,500 of 3,000'), (0.0, '7')]


def test_is_cancel_by_name():
    assert progress._is_cancel(Cancelled())
    assert not progress._is_cancel(ValueError())


def test_a_report_page_is_shown_only_after_the_work_returned():
    class Page(object):
        shown = 0

        def show(self, output=None):
            Page.shown += 1
    outcome = {'level': 'success', 'output': Page()}
    assert progress._show_pending(outcome) is True
    assert Page.shown == 1 and 'output' not in outcome
    assert progress._show_pending(outcome) is False              # shown once
    assert progress._show_pending(progress.CANCELLED) is False
    assert progress._show_pending(None) is False and progress._show_pending([1]) is False

    class Broken(object):
        def show(self, output=None):
            raise RuntimeError('no output window')
    assert progress._show_pending({'output': Broken()}) is False  # logged, never raised

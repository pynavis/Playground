# -*- coding: utf-8 -*-
"""Glue between pyNavis' cancellable progress window and Playground's progress callbacks.

Playground modules report progress as `progress(fraction 0..1, label)` (clashdata, reports)
or `tick(done, total)` (items). pyNavis' `forms.progress` is a context manager whose
handle has `update(fraction, label)` and `check()` (raises forms.Cancelled once Cancel was
clicked). Use:

    from namo import progress

    outcome = progress.run('Exporting clashes', lambda report: work(progress=report))
    if outcome is progress.CANCELLED:
        return                       # cancelling is silent: no toast

    # items-style callbacks:
    progress.run('Scanning', lambda report: items.geometry_items(roots, tick=progress.tick(report)))

`run` opens the window, passes a callback, and turns every cancel flavour (forms.Cancelled,
namo.items.Cancelled, namo.reports.Cancelled, or anything named 'Cancelled') into the
CANCELLED marker so callers have one check. Other exceptions propagate (a real bug should
reach the output window with its traceback). Under `pynavis run` (no dialogs) it runs the
work with a silent callback.

Nothing may print to the pyNavis output window while the progress window is up (the
output window would open empty behind it). A report records a namo.reports.Page instead
and leaves it in its result under 'output'; `run` prints that page right after the
progress window closed, so callers need do nothing.
"""

CANCELLED = object()


def _is_cancel(error):
    return type(error).__name__ == 'Cancelled'


def adapter(handle, start=0.0, span=1.0):
    """A progress(fraction, label) callback driving a forms.progress handle. Raises the
    handle's Cancelled from check() once the user cancels. start/span map the callback's
    0..1 into a slice of the bar (for multi-stage work)."""
    def report(fraction, label=''):
        handle.check()
        try:
            value = float(fraction)
        except (TypeError, ValueError):
            value = 0.0
        value = max(0.0, min(1.0, value))
        handle.update(start + span * value, label or '')
        return True
    return report


def tick(report, label='%s of %s'):
    """Turns a progress(fraction, label) callback into an items-style tick(done, total)
    callback. With an unknown total the bar stays at 0 and the label shows the count."""
    def _tick(done, total=None):
        if total:
            report(float(done) / float(total), label % ('{:,}'.format(done), '{:,}'.format(total)))
        else:
            report(0.0, '{:,}'.format(done))
        return True
    return _tick


def silent(fraction=None, label=None):
    """A progress callback that does nothing (automation, tests)."""
    return True


def _runner_active():
    try:
        from PyNavis.Runtime.Execution.Runner import RunnerContext
        return bool(RunnerContext.IsActive)
    except Exception:
        return False


def run(title, work, first_label='Starting'):
    """Runs work(report) inside a cancellable forms.progress window. Returns work's
    result, or CANCELLED when the user cancelled (any Cancelled flavour)."""
    if _runner_active():
        try:
            return work(silent)
        except Exception as error:
            if _is_cancel(error):
                return CANCELLED
            raise
    from pynavis import forms
    try:
        with forms.progress(title, first_label) as handle:
            outcome = work(adapter(handle))
    except Exception as error:
        if _is_cancel(error):
            return CANCELLED
        raise
    _show_pending(outcome)
    return outcome


def _show_pending(outcome):
    """Prints the output-window page a report left in outcome['output'] (see
    namo.reports.Page), now that the progress window has closed. A failure to print
    is logged, never raised: the work itself succeeded."""
    if not isinstance(outcome, dict) or outcome.get('output') is None:
        return False
    try:
        from namo import reports
        return reports.show_output(outcome)
    except Exception:
        try:
            import traceback
            from namo import session
            session.log('error', 'showing a report page failed:\n%s' % traceback.format_exc())
        except Exception:
            pass
        return False

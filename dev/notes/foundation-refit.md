# Foundation refit pass (shared library), 2026-10-05

Nothing here was run in Navisworks. Everything below is verified headlessly only: pure tests
on CPython and IronPython 3.4, WPF smoke under IronPython, the real BundleParser, fresh-engine imports.

## Per item

1. `ui.normalize_fields` now raises ValueError when a choice/radio `default` is not an option
   VALUE, when an `enabled_if` on a choice/radio names a value that field does not offer (a list
   needs one live value, so conditionally offered options stay legal), or compares a check box with
   a non-bool. `None` = first option. New field key `'fallback'` (value or None) is used instead of
   raising when a saved default is stale, and is itself checked. Audited all 95 choice/radio fields
   and 75 `enabled_if` by AST script plus reading: no swapped tuple left. 80 fields fed from saved
   settings got a `fallback` (28 with their literal default, 52 with None); 15 guarded or literal ones stay strict.
2. `ui.default_text` takes the length parser: a non-zero default whose `format_input` text reads back
   as zero opens as decimal inches (`0.0197"`, new `ui.small_length_text`). Checked against the real
   `pynavis.lengths` in a smoke test. The other length defaults (cut heights, tile, heat cell) are
   metre scale. Duplicate Finder / Model Compare keep their own round-up (still correct).
3. `Page` / `deliver` moved to `namo.reports` (plus `md`, `table`, `bar_chart`, `show_output`);
   `clashrep_out` re-exports them. `progress.run` now prints a pending page after the window closes.
   `ui.modal_loop(build)` added for the modal case (action calls `defer(job)`: window closes, job
   runs, window returns).
4. `namo/__init__.py`: references added once per engine behind a `_playground_references` marker module
   in `sys.modules` (no `__file__`, not a session holder key). Fresh engine stage still green (182 modules).
5. `camera.write_camera(viewpoint, cam)` public, `vpexcel` uses it. `camera.view_path` /
   `match_view` added; `find_view` tries the exact stored path, then the split walk, then a bare
   name with a slash. `macros.find_saved_view` now delegates.
6. New `namo/pins.py` (`segments`, `top`): the octahedron pin. `photopins.pin_segments` and
   `issues.pin_segments` both call it; colours, labels, tags unchanged. The issue pin keeps its
   overall height (head top at 1.4 x `pin_height`, label point unchanged) but is now readable in plan.
7. `paths.is_reachable` already logged nothing; `team_root()` logged on EVERY call while the share
   was away: now once, and again only after it came back. `_replace(temp, path, retries=None)`,
   passed through `atomic_write_bytes/text(retries=)`; no sleep after the last attempt. Camera Sync writes with `retries=1`.
8. `ui._browse`: new `ui.save_dialog_name`: the full path when its folder exists (dialog opens
   there), else the base name.
9. `FormState.refresh` is now a quick pass: path fields are only checked for being filled in, their
   own `validate` and the form-level `validate` are not called. `accept()` does the full check;
   `ui.carry_errors` keeps a path error until that text changes and a form-level error until anything changes.
10. `dev/check.py` fails on a call to `pick.point` / `pick.point_then` (and `from pynavis.pick import
    point`); AST based, so docstrings and comments do not trip it. CATALOG: 5 entries now say
    `namo.picking`. README index: `picking`, `pins`, `clashset_edit` rows, plus convention bullets for items 1, 3, 5, 9.
11. `mesh.summary` has one caller outside takeoff: Duplicate Finder's deep compare. No wrong volume
    was shown, but an unwelded watertight solid (any pipe) got volume None, so volumes were not
    compared. Moved the geometric test to `mesh.solid_measure` (takeoff delegates); `summary` and
    `centroid` use it ('closed' is geometric, new 'welded' is topological; a miswound mesh no longer
    gets a volume). `tol` defaults to `mesh.weld_tolerance(tris, noise)` instead of 1e-6.

## Tool bugs the stricter checks and greps exposed

* Count by Property and Data Validator: `rep_count_by_property` / `rep_data_validation` printed to
  the output window (card, chart, table, element links) inside `progress.run`. Now a `reports.Page`.
* External Data Link (`data_write.link_flow`): Refresh, Refresh all, Remove and New link's refresh ran
  progress windows from a modal table. Now `ui.modal_loop`.
* Extension Manager (`extmanager.run_window`): Install / Update downloaded behind a progress window from a modal table. Same fix.
* Clash to Issues settings: default `'Clash'` with a template list that may not hold it (renamed
  templates) opened with nothing chosen; fallback None.
* Stale saved choices in 80 fields opened a blank combo or an unticked radio and returned None; they now fall back.
* No other report module or script prints during progress; no other modal window starts one
  (Report Templates, Takeoff Templates, Clash Namer, Status Rules already close first).

## Flaky tests

`_compat.tmpdir` used one folder per engine for every process. Concurrent verify runs deleted each
other's folders mid-test: that is `test_preflight.test_report_writes_html_and_xlsx` (file gone
between write and read) and the FileExistsError (rmtree/makedirs race). Not dict order or time.
Now `%TEMP%\playground-tests\<engine>-<pid>\<name>`, removed at exit, stale roots swept after a day.

## Not done

* `picking.point` option to keep the banner between picks (views request 2) and the other requests
  outside the eleven items (items walk speed, `clashreport.status_counts`, the test fake) are untouched.
* In-app behaviour of everything above is unverified: especially that a full path in the Save dialog
  opens in that folder, the modal windows that now close and reopen around a progress window, and
  the once-per-session references under real hook runs.

## Verify

`python dev\verify.py` (run twice, both green):
`summary: check ok, pytest ok, ipy compile ok, ipy test ok, ipy smoke ok, parse ok, fresh ok, names ok`
check 140 bundles / 368 files / 0 problems; pytest 1,655 passed, 19 skipped; IronPython compile 368
files, 0 failures; IronPython tests 1,637 passed, 0 failed, 37 skipped; WPF smoke 117 passed;
BundleParser 138 buttons; fresh engine 182 of 182 modules.

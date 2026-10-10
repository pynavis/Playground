# G4 clash_setup_results: Clash Setup and Clash Results panels

Tab Coordinate. Everything below is verified headlessly only (unit tests on CPython
and IronPython 3.4, WPF smoke builds, pyNavis' real BundleParser). Nothing has been
clicked in Navisworks or Revit yet.

## Tools

Clash Setup panel

* **Clash Matrix**: writes a template workbook (Read me, Trades pre-filled with every
  selection set and every model, Matrix) and builds "A vs B" tests from it. Codes: H,
  H 10mm, HC, C 50mm, D. Conditions in the Trades sheet become search sets in a
  "Clash Matrix" set folder; every side references sets as selection sources so tests
  follow model updates. Existing tests are left alone or updated (results kept);
  optional run; a report table in the output window.
* **Clash Templates**: save chosen tests as a named, team-shared template (type,
  tolerance in metres, sets by path with their search conditions, models, self-intersect,
  primitives, merge composites); apply it in another model with a per-test status
  (ready, rebuilds missing search sets, missing items named); import, export, delete.
* **Scan vs Model**: suggests scan models (points or .rcp .rcs .e57 ...), builds one
  clearance test (design surfaces vs scan points, tolerance = largest band), runs it,
  colours each design element by the band of its closest scan points (Intrudes, Within
  25 mm, 25 to 50 mm ...), lists counts per band and the closest elements.

Clash Results panel

* **Clash Namer**: renames clashes and/or groups from a template ({test} {n:000} {grid}
  {level} {model_a} {model_b} {trade_a} {trade_b} {cat_a} {cat_b} {status} {distance}
  ...) in a live preview window (first 25 before and after). Up to 3,000 names (Shift+Click
  to change) are renamed one by one in one undo step; above that each test is rebuilt once
  on a copy and swapped in (TestsReplaceWithCopy), keeping groups, nesting and comments.
* **Status Rules**: ordered rules in team-shared rule sets ("Examples" ships three:
  Touching only, Inside one model, Stale reviews). Conditions are text lines (depth < 3 mm,
  trade pair = Mechanical / Structure, age > 30, A: Element > Category = Ducts ...); first
  match wins; the editor shows matches per rule and what will change; writes status,
  assignee and a comment, one undo step per test.
* **Clash Assigner**: Auto (the lower trade in the who-moves list moves; Shift+Click sets
  the list and trade-to-person names), Manual (chosen groups or clashes to a chosen trade
  or person), or Dashboard. Writes AssignedTo on top-level groups and ungrouped clashes in
  one undo step and appends ball-in-court history to the document database (local files
  when it is unavailable). Dashboard: open items per assignee, ages, the oldest 50 with how
  long the current assignee has held them.
* **Clash to Viewpoints**: one saved viewpoint per group (ungrouped clashes get their own)
  or per clash, by status, in "Clashes/{test}/{group}" folders, camera from
  TestsViewpointForResult, a comment with status, distance, both elements, grid and
  level; existing names skipped or replaced; confirm above 500; one undo step.
* **Clash Heatmap**: counts chosen-status clashes per element, colours them in up to five
  geometric bands (light to strong blue), optional ghosting, legend and top 20 hotspots
  with Show links, optional 3D density markers (pyNavis overlay crosses with counts).
  Shift+Click clears colours and markers.
* **Revit Link stack**: **Show in Revit** writes the selected elements (nearest Revit
  element, ids, UniqueId, source file) to %APPDATA%\pyNavis\playground\revit-link\to-revit.json;
  **Show from Revit** reads to-navisworks.json and finds the elements by Element ID in the
  matching models only, then selects and zooms.
* **pyRevit companion** (companions\PlaygroundLink.extension, tab Playground,
  panel Navisworks): **Show from Navisworks** selects and shows the elements Navisworks
  sent (UniqueId first, then id; workshared local copies match their central file);
  **Send to Navisworks** writes the Revit selection.

## In-app checks (please click these, in order)

Use a federated NWF with at least two Revit NWCs, two or three selection sets (one search
set, one static), and Clash Detective (Manage).

1. Ribbon: Coordinate shows Clash Setup (3 large buttons) and Clash Results (5 large
   buttons and a Show in Revit / Show from Revit stack), with icons in light and dark.
2. Clash Matrix > Write a template. Excel opens the workbook: Trades lists every set as
   "Set: path" and every model as "Model: file". Close it.
3. Fill the Matrix sheet: one H, one C 50mm, one D, and add a trade whose source is
   `Element > Category = Ducts`. Save, then Clash Matrix > Build. In Clash Detective >
   Select, both sides of a set-based test must show the SETS (not items): this is the
   first use of `DocumentSelectionSets.CreateSelectionSource` + `Selection.CopyFrom
   (SelectionSourceCollection)` on a new ClashTest. The report's "Follows sets" column
   should say Yes; tell us if a side shows items instead.
4. Same tests: the tolerance shows the code in document units; only Surfaces is ticked on
   each side; a "Clash Matrix" set folder holds a search set named like the Ducts trade.
   Build again: "Left as it was"; build with "Update their settings": statuses of
   existing results survive (TestsEditTestFromCopy). One Ctrl+Z after a first build removes
   the new tests and sets together.
5. Clash Templates > Save two tests. Open a copy of the model, delete one of the search
   sets, Clash Templates > Apply: that test says "Ready (recreates sets)"; after building,
   the set is back in its folder and the test references it. Export, delete, import the
   template file.
6. Scan vs Model (needs a model with an RCP/RCS scan): the scan is suggested with
   "(points)". Run with 25, 50, 100 mm. In Clash Detective the test is Clearance, 100 mm,
   and side B has only Points ticked. UNVERIFIED and important: that the API run reports
   point-cloud results like the UI does, which item a result names on the scan side, and
   that Distance is negative for scan points inside an element. Elements get coloured and
   the output lists bands; tell us if every result lands in "Intrudes" or none at all.
7. Clash Namer: type in the templates and watch the preview; Rename: Clash Detective
   shows the names; one Ctrl+Z restores them. Shift+Click, set the limit to 1, rename
   again: each test is rebuilt; check groups, nested groups, comments, statuses,
   assignees and each result's saved viewpoint (if it had one) are kept.
8. Status Rules: the "Examples" rule set appears; the Matches column fills in; Apply.
   Approved clashes must show YOU in "Approved by" (the third argument of
   TestsEditResultStatus is the current user in the dump) and keep their Assigned to.
   If Assigned to was changed by the status call the tool puts it back; tell us if you
   see that. Comments carry your name. One Ctrl+Z per test.
9. Clash Assigner: Shift+Click shows the who-moves list. Auto: the confirm lists names and
   counts; groups show the new Assigned to (check whether the clashes inside a group show
   it too or keep their own). Save the NWF, reopen, Clash Assigner > Dashboard: "Held
   (days)" is filled (history read back from the document database). With Playground data
   mode set to local the toast says history went to local files.
10. Clash to Viewpoints: folders Clashes/<test>/<group>; clicking a viewpoint gives the
    same camera as clicking the result in Clash Detective; the comment text is there. Run
    again: everything skipped; tick Replace: replaced. One Ctrl+Z removes them.
11. Clash Heatmap with markers on: elements coloured, the rest ghosted, crosses with
    counts at clash clusters; run again: old colours and markers replaced; Shift+Click
    clears both. Check the "Results" column of every test chooser equals Clash
    Detective's count: it comes from `Interop.LcOclClashUtils.CountByStatus(test,
    status, True)`; if it is higher by the number of groups, groups are being counted.
12. Revit: in pyRevit Settings add `companions` to the custom extension
    folders and Reload; a Playground tab with a Navisworks panel appears. In Navisworks select
    a duct (also try a nested family part such as a fitting's sub-solid) > Show in Revit;
    in Revit (same model, a workshared local copy is fine) > Show from Navisworks: the duct
    is selected and zoomed (the nested part resolves to its host element, not its type).
    Reverse: select in Revit > Send to Navisworks; in Navisworks > Show from Revit.

## Requests for shared modules (not edited; worked around locally)

1. **namo.ui.Table.select_values** raises "Can only change SelectedItems collection in
   multiple selection modes" when the table was built with `multiselect=False`. Fix: at
   the top of `select_values`, `from System.Windows.Controls import DataGridSelectionMode`
   and when `self.grid.SelectionMode == DataGridSelectionMode.Single` set
   `self.grid.SelectedItem` to the first matching row view (or None) and return. Status
   Rules uses an extended-selection table meanwhile.
2. **namo.items.revit_ids** reads ids off `object_of(item)`; for nested family parts that
   object carries the TYPE id (pyNavis' Select by IDs field notes). Fix: before building
   the candidates, climb from the item to the first ancestor-or-self whose
   `pynavis.props.categories(node)` contains internal name `LcRevitData_Element`, and
   use that as the element. `namo.revitlink.revit_element` does this locally.
3. **namo.ui** custom windows need `_wpf()`, `_thickness()` and `_close_with()`, which are
   private. Please expose `ui.wpf()`, `ui.thickness(*values)` and `ui.close(win, result)`.
   Local copies live in `namo.clashset_common`.
4. **Test harness**: `dev/ipy_driver.py` deletes and re-imports each test module, so a test
   file that imports another test module (the README's `import test_items as nav`) can
   hold a different generation of the fake classes than a module imported earlier, and
   `isinstance` checks in the fakes fail only in the full run. My tests reach every fake
   through one module (`test_clashset_tests`, which re-exports `nav`). Suggest saying so
   in the README, or only deleting the module about to run.
5. Observation for pyNavis (read-only here): `pynavis.clashtest.set_status` passes each
   result's AssignedTo as the third argument of `TestsEditResultStatus`, which the 2026
   dump names `current_user` (it likely sets Approved by / Resolved by). Status Rules
   writes statuses itself with the current user and guards AssignedTo.

## Decisions and assumptions

* Tests are built through `namo.clashset_tests` rather than `pynavis.clashtest.create`,
  because create() only takes items: selection-set references need
  `CreateSelectionSource`. New tests go to the top level of Clash Detective (no folders).
* "Replace existing" means update the definition and keep results (TestsEditTestFromCopy
  on a CreateCopy), so coordination history is never thrown away.
* A side that mixes sets with models or picked items is written as items, with a note.
* Workbook tolerances without a unit are in document units (pyNavis' length rule).
* The Status Rules note is added as a comment (history is kept) rather than replacing the
  description.
* Writes run behind pyNavis' ProgressScope with no Cancel (a cancel inside a transaction
  would leave half an edit); reads use namo.progress with Cancel.
* Scan vs Model bands use the clearance distance: negative = scan points inside the
  element (worst), then 0 to the first band, and so on.

## Files

* Bundles: `Playground.extension\Coordinate.tab\Clash_Setup.panel\` and
  `...\Clash_Results.panel\` (config.py on Clash Namer, Clash Assigner, Clash Heatmap).
* Modules: `lib\namo\clashset_tests.py` (definitions, build, read), `clashset_common.py`
  (choosers, progress, file names), `clashmatrix.py`, `clashtemplates.py`,
  `scanvsmodel.py`, `clashname.py`, `clashrules.py`, `clashassign.py`,
  `clashres_views.py`, `clashheat.py`, `revitlink.py`.
* Companion: `companions\PlaygroundLink.extension\` (lib\playgroundlink.py, two
  buttons; icons generated by `python dev\icons\clash_setup_results.py`).
* Tests: `dev\tests\test_clashset_tests.py` (also the shared fake clash layer),
  `test_clashmatrix.py`, `test_clashtemplates.py`, `test_scanvsmodel.py`,
  `test_clashname.py`, `test_clashrules.py`, `test_clashassign.py`,
  `test_clashres_views.py`, `test_clashheat.py`, `test_revitlink.py`,
  `smoke_clashname.py`, `smoke_clashrules.py`.
* Icons: `dev\icons\clash_setup_results.py`, sheet `dev\notes\clash_setup_results-icons.png`.

## Refit pass

Second pass after the first field click. Every bundle in both panels was re-read against
the shipped Clash Grouper, `pynavis.clash` / `clashtest` / `_clashapply` and the element-ID
bundles. Still headless: nothing below has been clicked in Navisworks.

The failure class found here: **result edits written one document edit per clash.**
pyNavis measured every `DocumentClashTests` edit at a fixed cost that grows with the model
(~170 ms per `TestsAddCopy`, 1 to 3 s per `TestsMove` on a 350,000-clash file), which is
why the shipped Clash Grouper rebuilds a test on a detached copy and commits it with one
`TestsReplaceWithCopy`. Clash Namer (default 3,000 per-item renames), Status Rules (up to
three edits per matching clash, unbounded) and Clash Assigner (one per unit, unbounded)
all took the slow road. New module `namo.clashset_edit` gives all three the Grouper route
above 200 document edits, and a single rebuilt test is committed bare exactly as Clash
Grouper commits it (no transaction around the one swap).

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Clash Matrix | fixed | A refused set reference (`CreateSelectionSource` / `Selection.CopyFrom(sources)`) crashed the build halfway: now falls back to the sets' items with a note in the report. `PrimitiveTypes`, `SelfIntersect`, `MergeComposites` are only written when they differ, so an ordinary test writes exactly what `pynavis.clashtest.create` writes. Flags combined safely when the enum refuses `\|`. Runs go through `pynavis.clashtest.run`; a failed run is a warning toast, not a traceback. First run opens on "Write a template". | Proven for model-vs-model tests; **unproven**: set references on a new test (`CreateSelectionSource`, `Selection.CopyFrom(SelectionSourceCollection)`), guarded |
| Clash Templates | fixed | Same builder fixes. A test Navisworks will not describe no longer stops Save (it is named and left out). Failed run reported. | Same as Clash Matrix; **unproven**: reading a side back (`ResolveSelectionSource`, `ExplicitSelection`), guarded per test |
| Scan vs Model | fixed | If the Points switch does not take, the tool stops and says so instead of comparing surfaces with surfaces. Any failure of the build or run is a toast naming the test. `a or b` on ModelItems replaced with explicit None checks. | **Unproven** (no alternative): `ClashSelection.PrimitiveTypes = Points`, point clearance results through the API, sign of `Distance` |
| Clash Namer | fixed | One-by-one limit 3,000 -> 200 (a saved 3,000 is treated as the old default); above it the Grouper rebuild. Live preview plans 5,000 names per keystroke, not 20,000. Tooltip says how to use it and ends "Shift+Click for settings." | Rebuild: proven route (`CreateCopy` + `TestsReplaceWithCopy`); **unproven**: `DisplayName` set on a copied result, `TestsEditDisplayName` on results (small counts) |
| Status Rules | fixed | Above 200 edits each test is rebuilt once (status via `UserTransitionStatus(status, who)` on the copy, falling back to `Status`; assignee and comment set on the copy). Does not use `pynavis.clashtest.set_status` (the recorded assignee bug): the current user is the actor and a moved AssignedTo is put back. | Rebuild commit proven; **unproven**: `TestsEditResultStatus/AssignedTo/Comments` (small counts), `UserTransitionStatus`, `Status`/`AssignedTo` setters and `Comments.Add` on a copy |
| Clash Assigner | fixed | Above 200 units each test is rebuilt once; a rebuilt group hands its assignee to its clashes, as Clash Detective does. Ball-in-court history is also found by test + name, so "Held (days)" survives a rebuild that changes result ids. Tooltip ends "Shift+Click for settings." | Same split as Status Rules; `TestsEditResultAssignedTo` on a group **unproven** |
| Clash to Viewpoints | fixed | The comment is added to the detached viewpoint before `AddCopy` (how Clash Grouper comments new groups); `AddComment` is only the fallback and can no longer mark a saved viewpoint as failed. A folder that cannot be made fails its views, not the run. All-failed is an error toast with a next step. | `SavedViewpoint(viewpoint)` + `AddCopy` proven; **unproven** (no alternative): `TestsViewpointForResult` |
| Clash Heatmap | fixed | Overlay use matches True Distance (unique tag per item, clear, redraw). Markers capped at the 150 densest cells (every overlay item and label is redrawn each frame); the report says "the 150 densest of N". | Proven (`pynavis.overlay`, permanent overrides via `namo.paint`) |
| Show in Revit | ok as built | Reads the nearest `LcRevitData_Element` ancestor, like IDs of Selection. | Proven |
| Show from Revit | fixed | Looks for the id in the property the user set for pyNavis' own Select by IDs (`cfg_element_ids`), not a hard-coded "Element ID > Value". | Proven (`sets.find_first` scoped, element-category rule, `view.zoom_selected`) |
| pyRevit companion | ok as built | Read through; not runnable here. | Unproven (Revit side) |

Shared: the test chooser's Results column and every "has results" check now use
`pynavis.clash.count_results` (the walk Clash Grouper counts with) instead of
`Interop.LcOclClashUtils.CountByStatus`, an Interop call no shipped tool makes; in-app check
11 above no longer applies. With exactly one candidate test the chooser is skipped.

### Foundation requests

1. `namo/clashreport.py` `status_counts` (G7) and the README convention still call
   `Interop.LcOclClashUtils.CountByStatus`. No shipped tool uses it; `pynavis.clash.summarize`
   / `count_results` are the proven counts. Worth the same swap, or at least a field check first.
2. `namo/clashdata.py` `set_assigned`, `set_description`, `set_priority`, `add_comment` are one
   document edit per result. The docstring says "measure before tens of thousands"; the measured
   answer is in `pynavis/_clashapply.py`. Any caller looping over more than a couple of hundred
   results should go through `namo.clashset_edit.rebuild` + `commit`. Consider moving
   `clashset_edit` into the foundation index and saying so in the README.
3. `dev/tests/test_items.py` `SavedViewpoints.AddCopy` resets `clone.Comments = []`, so a comment
   put on a viewpoint before `AddCopy` cannot be asserted through the shared fake. Keep the
   item's comments (my test substitutes its own SavedViewpoint class meanwhile).
4. pyNavis (read-only here): `clashtest.set_status` still passes each result's AssignedTo as
   the acting user. `ClashResult.UserTransitionStatus(new_status, who)` in the dump names the
   same argument `who`, which supports the pending.md reading.

### First three things to click

1. **Clash Heatmap** on one test, "Mark the densest spots" ticked. Correct: elements with
   clashes turn light to strong blue, the rest ghost, crosses with clash counts sit at the
   clusters and stay put while you orbit; the output window lists bands and the top 20 with
   Show links. Shift+Click puts the colours back and removes the crosses.
2. **Clash Namer** on a test with more than 200 clashes, template `{test} {n:000}`. Correct:
   the preview fills as you type; Rename returns in seconds with "Each test was rebuilt once";
   Clash Detective shows the new names with groups, nested groups, comments, statuses and
   assignees intact; one Ctrl+Z restores the old names. Then a test with fewer than 200 (the
   one-by-one route): same result, toast without the rebuild line.
3. **Clash Matrix**: write the template, put `H` in one cell between two selection-set
   trades, build. Correct: one new test whose two sides show the SETS in Clash Detective's
   Select tab and "Follows sets: Yes" in the report. If the report instead carries the note
   "Navisworks did not accept a reference to the selection sets", the fallback worked and
   the unproven set-reference call is the thing to tell us about.

### Verify

`python dev/verify.py`: check ok, pytest ok (1617 passed, 19 skipped), ipy compile ok (367
files), ipy test ok (1602 passed, 35 skipped), ipy smoke ok (115 passed), parse ok (138
buttons), fresh ok (181 modules), names ok.

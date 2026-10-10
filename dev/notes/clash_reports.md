# G7 clash_reports: the Clash Reports panel (tab Coordinate)

Built by agent G7. Everything here is verified headlessly only (CPython pytest, IronPython
3.4 tests, IronPython WPF smoke, the real pyNavis BundleParser, headless Edge renders of
the HTML). Nothing has been clicked in Navisworks yet.

Ribbon order: Clash Excel, Clash Dashboard, Count Matrix, History (stack: Snapshot, Clash
Delta, Clash Trends), Per-Trade Reports. Every button has `context: clash-tests`. No
shortcuts (the catalog assigns none). Only Snapshot has a Shift+Click (config.py).

## 1. Tools

| Tool | What it does |
|---|---|
| Clash Excel (#25) | Test picker (remembers by test path), one form (statuses to list, thumbnails, Save as, open when saved), a three-way question only when a test lists more than 300 clashes (first 300 per test / all / none). Workbook: Summary (headline band, one row per test with type, tolerance, last run, Out of date flag, counts per status in Clash Detective colours, link to its sheet, totals, then open clashes by trade pair, assignee and level, notes), one sheet per test (160 x 90 JPEG thumbnail anchored to its cell, clash, group, status fill, distance in report units, level, grid, items, models, trades, categories, assignee, found, age, approval, description, comments; frozen header and first columns, autofilter), and All clashes (every listed clash with a Test column, for pivots). |
| Clash Dashboard (#26) | Same questions; one offline HTML page opened in the browser: KPIs (clashes, open, each status in its colour, oldest open), status donut and status-by-test bars in Clash Detective colours, tests table (Out of date chip), open clashes by level and grid, model A against model B heatmap, trade pairs, by assignee, age bands, result groups with status chips, and a sortable, filterable clash table with thumbnails. Light/dark follows the reader, prints light. |
| Count Matrix (#27) | Trade against trade (or model against model) counts of open (New, Active, Reviewed) and of New clashes, upper triangle, an Involving column, top pairs. Output window heat tables mixed from the window's own chart colour (readable in both themes); optional workbook with graded fills (Open, New, Pairs, Tests). |
| Snapshot | Records the chosen tests' clashes as a history snapshot of the saved model (clashdata.save_history), optional label. Shift+Click: automatic snapshot on save (off by default; at most one every N hours, default 4; skipped above a result cap, default 50,000, or when the counts per status did not change, or in model data mode) or review and delete snapshots. |
| Clash Delta (#28) | Compare now with a snapshot (default: the latest taken before today): per test open then and now, new, fixed (and how: Resolved, Approved or Gone), still open, status changes. Output window with Show links for new clashes; optional workbook (Summary, New, Fixed, Status changed, Still open); optional "select the items of the new clashes" (and zoom). |
| Clash Trends (#29) | Line chart over the snapshots (open and resolved together, or open per test) with the current state as a last "Now" point, plus a burn-down table (open, resolved, total, new and fixed since the point before, change). Optional workbook (Trend, Open by test) and/or CSV (UTF-8 with BOM). |
| Per-Trade Reports (#31) | One Clash Excel workbook (and optionally one dashboard) per responsible trade into a dated folder, plus an index workbook linking them; opens the folder. Responsible = Assigned to (a person mapped to a trade in Clash Assigner counts for that trade), else the trade that moves under Clash Assigner's who-moves list, else both trades. |

All six reports implement the `rep_<id>.py` contract (`clash_excel`, `clash_html`,
`clash_matrix`, `clash_delta`, `clash_trends`, `per_trade`) and run with
`interactive=False` and no dialogs (Report Templates, Scheduled Reports, macros). Under
`pynavis run` every button runs its report from its saved options and toasts the result.
`hk_clashhistory` handles `doc-saved` (registered in `namo.hooks`).

Modules (all mine): `clashreport` (data dict, shaping, tallies, matrices, thumbnails,
snapshots), `clashrep_history` (baselines, delta, trend series), `clashrep_svg` (status
donut and stacked bars in htmlreport's CSS), `clashrep_out` (output-window HTML parts),
`clashrep_forms` (every form's fields, test picking, the thumbnail question),
`rep_clash_excel`, `rep_clash_html`, `rep_clash_matrix`, `rep_clash_delta`,
`rep_clash_trends`, `rep_per_trade`, `hk_clashhistory`. Pure halves tested on both
engines from ~600 realistic fake clashes (`dev/tests/test_clashreport.py: fake_data`);
API halves through the shared fake Navisworks layer (`fake_clash_doc`); the xlsx and
HTML outputs are byte-compared between CPython and IronPython (`cross_engine`).

Assumptions I made (decided without anyone to ask):
* Listing default is open clashes (New, Active, Reviewed); the Summary, KPIs and charts
  always count every status.
* Distances use Playground's `report_units` (auto = document units) as numbers with a unit in
  the header (mm 0.1, cm 0.01, m/ft 0.001, in 0.01) so Excel can sort and filter them;
  negative = penetration, as Clash Detective shows it.
* Automatic snapshots are skipped in `model` data mode: writing into the model right
  after a save would mark it changed again. The Shift+Click form says so.
* A delta test the snapshot does not hold is reported as "not compared" (its open count
  only); none of its clashes is called new.
* Per-Trade puts a clash with an undecidable mover into both trades' files and says so in
  each workbook and the index.

## 2. Check in Navisworks (in this order)

1. Reload. Tab Coordinate shows the Clash Reports panel exactly as listed above; the
   buttons are greyed until the model has clash tests.
2. Open a federated model with at least two run tests, one holding result groups, one
   whose models changed since it ran (Clash Detective shows it as Old). Save it.
3. Console check of the fast counter (UNVERIFIED: that `LcOclClashUtils.CountByStatus`
   counts results inside groups):
   `from namo import clashreport as cr, clashdata; [cr.status_counts(t) for t in clashdata.tests()]`
   must equal Clash Detective's per-status counts for every test, grouped ones included.
4. Clash Excel, all tests, thumbnails on. If a test has more than 300 open clashes the
   three-way question appears. Watch: counted progress with Cancel; the view does not
   jump around (or comes back exactly when done); the workbook opens in Excel without a
   repair prompt. Check: Summary counts equal Clash Detective's; tolerance in your units;
   Last run equals Clash Detective's time (not shifted by your UTC offset); the old test
   reads Out of date; thumbnails show each clash with its pair highlighted; filtering
   Status hides thumbnails with their rows; Category A/B filled (Revit categories); Level
   and Grid match Clash Detective's Grid Location; the Sheet link jumps.
5. Run Clash Excel again and Cancel during the thumbnails: no file, no toast, camera where
   it was. Run it once with a test name that has `/` or `:` (sheet names are cleaned).
6. Clash Dashboard: opens in the default browser; KPIs equal the Excel Summary; switch the
   OS to dark mode and reload the page; hover a donut slice and a heatmap cell (tooltips).
7. Count Matrix: the heat tables are readable in Navisworks' light AND dark theme (the
   fills use CSS `color-mix`, which needs WebView2 based on Chromium 111 or later; without
   it the cells are plain but still readable). Trade names come from Playground's trade rules
   (a combined "MEP" model reads Unassigned unless you add a rule). Optional workbook:
   graded fills, frozen labels.
8. Snapshot: label it, check the toast ("Kept on this computer." in local mode). Shift+Click
   Snapshot, turn automatic snapshots on. Save the model: a toast "Clash snapshot saved"
   after the save, and the model is NOT marked modified afterwards. Save again at once:
   no snapshot (the pyNavis log says "Clash history: no automatic snapshot: the last
   snapshot is less than 4 hours old"). With a big test, the log line "snapshot ... in N s"
   tells how long the save was held; report N.
9. Clash Detective: re-run a test without changing the model, then Clash Delta against
   the snapshot. Every open clash must count as Still open (0 new, 0 fixed). This proves the
   clash keys (element InstanceGuid plus a 0.1 m centre cell, clashdata.pair_key) survive
   a re-run (UNVERIFIED in F3). Then resolve two clashes and move one element so a clash
   disappears and one appears: New 1, Fixed 3 (2 Resolved, 1 Gone). Show links select
   the item; "Select the items of the new clashes" selects and zooms.
10. Clash Trends: chart with a legend, the "Now" point last, burn-down numbers match the
    deltas; the CSV opens in Excel with accented names intact.
11. Per-Trade Reports: the form names Clash Assigner's who-moves order (change it with
    Shift+Click on Clash Assigner first and see it follow). Assign a clash to a person
    mapped to a trade in Clash Assigner ("Mechanical = Jane Smith"): it lands in the
    Mechanical workbook. The folder opens; the index links open each workbook.
12. Report Templates / Scheduled Reports (G10) and `pynavis run`: each of the six reports
    runs without a window and writes into `%APPDATA%\pyNavis\playground\reports` (or the configured
    folder).

## 3. Requests for modules I do not own

1. **G4 `clashset_tests.result_count`** calls `LcOclClashUtils.CountByStatus(test, status,
   True)` with three arguments; the 2026 dump has only
   `CountByStatus(GroupItem group, ClashResultStatus status)` (static). The call always
   raises and falls back to walking every result, which is what the fast path was meant
   to avoid (and `clashset_common.clash_problem` / `choose_tests` call it per test).
   Fix: `int(LcOclClashUtils.CountByStatus(test, getattr(ClashApi.ClashResultStatus, status)))`.
   (`clashreport.status_counts` already uses the two-argument form, with a walk when the
   fast total is 0 for a test that has children.)
2. **F3 `clashdata.compare`**: when several old rows share one `pair_key` (the same two
   elements within 0.1 m, possible across groups or after a split), the first pass pairs
   them by order, so a status change can be reported on the wrong clash. Clash Detective
   keeps result names across runs, so prefer a same-name candidate: in the first loop,
   replace `candidate = bucket.pop(0)` with
   `pick = next((i for i, c in enumerate(bucket) if old_rows[c].get('name') == row.get('name')), 0); candidate = bucket.pop(pick)`.
3. **F1 `htmlreport.Report.html()`**: custom chart blocks with `data-tip` only get the
   tooltip element when the report also holds a built-in chart (`_uses_tip`). The
   dashboard always has built-in bar charts so it works today; a public switch would make
   it safe: `def html(self, trusted_html, tooltips=False)` setting `self._uses_tip = True`
   when asked (or when `'data-tip='` is in the HTML).
4. **G4 `clashassign`**: Per-Trade Reports reads Clash Assigner's saved who-moves list
   and names from that bundle's own settings key
   (`cfg_coordinate_tab_clash_results_panel_clash_assigner_pushbutton`, the key
   `pynavis.script.get_config` derives from the bundle path; a test pins it to the folder).
   If G4 adds `clashassign.saved_settings()` returning `(priority, names)` from that key,
   rep_per_trade should call it so the key lives in one place.

Note for everyone writing CSV under IronPython 3.4: `io.open(path, 'w',
encoding='utf-8-sig')` writes the byte order mark before EVERY write call. Build the text
in memory and write bytes once (`rep_clash_trends.write_csv`).

## Refit pass

Every bundle of the panel was re-read against the shipped pyNavis tools (Clash Grouper,
Clash Report, Excel Sets) and the pynavis library. Reading already went the proven way
(`clashdata.snapshot` is built on `pynavis.clash.snapshot_results`, all six `rep_*.run`
open no dialog with `interactive=False`, and every script checks the runner first).

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Clash Excel | fixed | Toast named only the file name. Detail now ends with the full path; with "Open it when it is saved" off, the file is shown in Explorer | Proven read (pynavis.clash snapshot). Unproven: thumbnails (`DocumentClashTests.TestsImageForResult`), guarded: three failures in a row stop the images and the report says so; `LcOclClashUtils.CountByStatus(test, status, True)` for the thumbnail question, falls back to a walk |
| Clash Dashboard | fixed | Same toast fix (full path); still opens in the browser | As Clash Excel |
| Count Matrix | fixed | Printed to the output window while the progress window was up (the shipped Clash Grouper avoids exactly that: an empty window opens behind the progress one). The report now hands its page back (`clashrep_out.Page`) and the button prints it after the progress window closed. A saved workbook is named with its full path at the foot of the page and shown in Explorer | Proven |
| Snapshot (+ Shift+Click) | ok as built | | Proven read; storage is namo.store |
| Clash Delta | fixed | Same output-window fix; here even `output.element_link` (the Show links) opened the output window mid-progress, so the page is built after the progress window closed. Workbook path on the page, file shown in Explorer | Proven; unproven: clash keys surviving a re-run (InstanceGuid + 0.1 m cell), see check 9 above |
| Clash Trends | fixed | Same output-window fix (chart and table printed after progress); saved xlsx/csv named on the page and shown in Explorer | Proven (`output.chart_line`) |
| Per-Trade Reports | fixed | Toast named only the folder's name; now the full folder path (the folder still opens) | As Clash Excel |
| hk_clashhistory (save hook) | ok as built | Off by default; logs and swallows every failure | Proven read |

Excel output stays on `namo.xlsx`, not `pynavis.xl`: `pynavis.xl` writes values and a bold
header only, and these workbooks need fills, frozen panes, filters, links and pictures.
Both write a temp file and move it over the target.

New in the library: `clashrep_out.Page` / `deliver` (deferred output), `clashrep_forms.reveal`.
Regression tests: `dev/tests/test_clashrep_out.py`, the full-path assertion in
`test_rep_clash_excel.py`.

Foundation requests
* Every other group's report button calls `reports.run(..., interactive=True)` inside
  `progress.run`, and their `rep_*` modules print to the output window from there. Same
  trap as above. A shared fix: `namo.progress.run` could collect `result['output']` pages
  (move `clashrep_out.Page` into a foundation module) and show them after the window closes.
* `ui._browse` gives the Save dialog only the file name of the field's current path, so
  Browse opens in the last used folder, not the document's folder the field shows.

First three clicks
1. Count Matrix on a model with run tests: progress window, then (only after it closes)
   the output window with two heat tables and the top pairs; no empty output window
   behind the progress bar.
2. Clash Excel with thumbnails on, "Open it when it is saved" ticked: counted progress
   with Cancel, the camera back where it was, Excel opens the workbook without a repair
   prompt, Summary counts equal Clash Detective's, the toast ends with the full path.
3. Snapshot, then Clash Delta with "Also save an Excel workbook": zero new and zero
   fixed straight after a snapshot, Show links select items, Explorer opens on the workbook.

Verify (full run, 2026-10-05): check ok, pytest ok, ipy compile ok, ipy test ok, ipy smoke
ok, parse ok, fresh ok, names ok.

# G8 issues_bcf: Issues and BCF panels (tab Coordinate)

Verified headlessly only (CPython 3.11 + IronPython 3.4 harness, WPF built and rendered
off screen, real pyNavis BundleParser). Nothing here has been clicked in Navisworks.

## 1. Tools

**Issues.panel** (layout: Issues, Issue Stamps, Issue Pins, Meeting Mode, Issue Tools, Coordination Report, KPI Export)

* **Issues** (`Issues.dockpane`): the register as a dock panel. Status / trade / assignee
  choosers and a filter box; sortable list (ID, title, status chip, priority, trade, due
  with a red "late" marker; trade, priority and due drop out as the panel narrows); the
  editor (title, type, status, priority, trade, assignee, due, labels, description) with
  Save / Revert, Update view, Delete; location with Set pin; elements with Select; image
  strip with Add screenshot; comments thread with Add comment (Ctrl+Enter). New from view
  (with the issue type chooser) captures camera, selection and a snapshot. Double-click or
  Enter on a row goes to the issue. Moving to another issue saves pending edits; Save
  sends only the changed fields. Refreshes on issue changes from any Playground tool in this
  session, on document change, when re-shown, and on Refresh (shared folder).
* **Issue Stamps** (`Issue_Stamps.pulldown`): RFI, Hold, Verify, Safety, Stamp from
  Template. Pick a point (namo.picking: the host's Measure tool, prompt on the banner), get an issue from the template there: the
  clicked object as element, trade from its model (unless the template fixes one), pin
  with grid and level, camera and snapshot. Toast "RFI 012 created".
* **Issue Pins** (`Issue_Pins.toggle`): draws open issues with a location as overlay pins
  (stem + double diamond head, a real 1.2 m stem in every model, the size Photo Pins uses,
  label "#12 RFI: title"); follows edits (debounced listener) and redraws on doc-opened
  (`hk_issuepins`). Tags are `playground-issues:<id>` (one overlay item per pin, because an
  overlay tag holds one label).
* **Meeting Mode**: filter (status, trades, priorities, due, order, follow in view), then
  a modeless window: issue N of M, details, snapshot, big Previous / Next (arrow keys),
  status buttons, decisions (comment "Meeting <date>: ..."), assignee and due, Take
  screenshot, Mark discussed, End meeting. Minutes as HTML + xlsx into the model folder
  (opened); also written if the window is closed after anything happened.
* **Issue Templates** (stack): manager table (New, Edit, Duplicate, Delete, Export,
  Import) over `namo.templates` 'issue_templates' (team folder when set). Ships RFI, Hold,
  Verify, Safety, Clash, Design change (used virtually until the first edit writes them).
* **Clash to Issues** (stack, context clash-results): one issue per top-level group or
  ungrouped clash of the chosen tests and statuses, once (source ref test guid | unit
  guid); trade from AssignedTo or who-moves rule, priority from penetration depth, due
  from priority, clash viewpoint, clash image, both sides' elements. Shift+Click: template,
  who moves, depth bands, due days, snapshot cap.
* **Coordination Report** (report `coordination`): HTML + xlsx: KPIs, open by trade /
  priority / age, overdue, due this week, per-trade sections with thumbnails, recently
  closed, all issues. Shift+Click: formats, thumbnails, trades, void, folder, name.
* **KPI Export** (report `kpi_export`): issues, issue_comments, clash_results,
  clash_tests, clash_history as CSV (UTF-8 BOM) + JSON + README.txt; stable keys, ISO
  dates, snapshot_time. Shift+Click: fixed folder for scheduled refresh, tables, formats.

**BCF.panel** (layout: BCF Export, BCF Import)

* **BCF Export**: issues (by status) or clash units straight from Clash Detective, BCF 2.1
  (default) or 3.0; cameras in metres, components by IFC GUID with Element ID as
  AuthoringToolId, snapshots (PNG for 2.1), 3.0 extensions.xml and attached documents.
* **BCF Import**: BCF 2.0 / 2.1 / 3.0; preview counts; merge by Topic Guid (topic newer
  than the issue updates fields; comments merged by guid, never duplicated); viewpoints as
  saved viewpoints under `BCF/<file name>` in one undo step; components found by IFC GUID
  then Element ID (progress, cancel, 3 minute budget).

Modules: `issues` (model + public API facade, documented at its top), `issuestore`
(storage, merging, media, session events), `issueapi` (Navisworks half), `issueui` (pane),
`issue_templates`, `issue_stamps`, `issue_clash`, `issue_meeting`, `bcf` (pure BCF),
`bcf_exchange`, `rep_coordination`, `rep_kpi_export`, `hk_issuepins`.

Storage: local `%APPDATA%\pyNavis\playground\docs\<doc key>\issues\<id>.json`; shared
`<shared>\docs\<file name key>\issues\` (one file per issue, last writer wins per issue,
comments and images merged, ids handed out under the RecordStore folder lock); model:
docdb records 'issues' (saved with the NWF/NWD). Images: `<issues folder>\_media\<guid>\`,
or in model mode `%APPDATA%\pyNavis\playground\issue-media\<guid>\` (local: pictures do not travel
inside the model).

BCF schema evidence: the writer follows the BCF-XML release_2_1 / release_3_0 element
order as reconstructed from memory; `dev/tests/test_bcf.py` validates every written file
with lxml against XSDs reconstructed in that test (structure, order, multiplicity,
required attributes, Guid / IfcGuid patterns, FieldOfView 45..60 in 2.1 and (0, 180) in
3.0, AspectRatio in 3.0), and `bcf.check()` re-checks structure on both engines. Not run
against the official buildingSMART XSD files (not available offline): see check 18.

## 2. In-app checks (in this order)

1. Reload. Coordinate shows Issues (Issues, Issue Stamps, Issue Pins, Meeting Mode,
   the Issue Templates / Clash to Issues stack, Coordination Report, KPI Export) and BCF
   (BCF Export, BCF Import) with icons in light and dark themes.
2. Open the Issues panel with no model: "No model open". Append models without saving:
   "Save the model first", New from view greyed. Save as NWF: "No issues yet".
3. Select a duct, choose type RFI, New from view: RFI-001 is listed and selected, the
   title box has focus, the thumbnail shows the view (Document.GenerateImage at the view's
   aspect), toast "RFI-001 created". Type a title, Save.
4. Change Status to Resolved and Save: the comments thread shows "Status: Open > Resolved".
   The due marker turns muted once resolved.
5. Orbit away, double-click RFI-001: the camera returns exactly (captured Rotation3D
   written back) and the duct is selected. Select selects without moving the view.
6. Set pin (a pick started from a dock pane button): click a point; Location shows
   "Level ..., grid ..." when the model has grids. Confirm the pick ends cleanly and the
   previous tool comes back.
7. Add screenshot: second thumbnail; clicking a thumbnail opens the picture.
8. Issue Pins on: one pin per open issue with a location, label "#1 RFI: title"; each pin is about a person tall (1.2 m stem) at the model's real scale, on a small and
   on a very large model alike. Close an issue: its pin disappears within a second. Hide Pins.
9. With pins on, open another model: its pins replace the first model's (hook). Close the
   model: pins stay until one is opened (see request 3).
10. Issue Stamps > RFI: the prompt is on the banner and the pointer snaps like Measure;
    click a wall: RFI-002 with the wall as element, trade from its model name, due
    today + 7, toast "RFI 002 created". Esc or right-click during the pick: no toast, the
    banner goes and the previous tool comes back.
11. Stamp from Template: choose Safety, click: SAF-001 Critical due tomorrow.
12. Issue Templates: edit Hold (due 5 days), stamp a Hold: due today + 5. Delete Verify,
    reopen: Verify gone; export and re-import a template file.
13. Clash to Issues on a test with groups and ungrouped clashes: one CLA issue per group
    and per ungrouped clash, clash image as snapshot (TestsImageForResult and
    TestsViewpointForResult called with a ClashResultGroup; the code falls back to its
    RepresentativeResult if a group is refused: tell me which happened). Run again:
    "N already had issues". Check trade (who moves), priority (depth) and due.
14. Meeting Mode: pick Open + In progress; Next / Previous (and arrow keys) move the view
    to each issue; a status button saves immediately; Add decision; set assignee and due;
    Take screenshot; End meeting: minutes HTML opens from the model's folder, xlsx beside
    it. Typing in the decision box must reach the window (modeless keyboard interop).
15. Coordination Report: HTML opens with KPI tiles, charts, per-trade thumbnails
    (System.Drawing thumbnails of snapshots); the workbook has five sheets, thumbnails on
    Open issues stay with their rows when filtering.
16. KPI Export: pick a folder; CSV and JSON per table plus README.txt; issues.csv opens in
    Excel with accents intact; load the folder in Power BI (Get data > Folder).
17. BCF Export 2.1 of a few issues; open in a second BCF tool (BIMcollab Zoom, Revit BCF
    Manager or Solibri): titles, statuses, comments, snapshot, and that the viewpoint lands
    on the same place and selects the same elements. If the view is offset, the two tools
    use different coordinate bases (Revit shared vs internal): note the offset.
18. Validate an exported 2.1 and 3.0 file against the official buildingSMART BCF-XML
    schemas (release_2_1, release_3_0 Schemas folders) with any XSD validator, or open the
    3.0 file in a 3.0 tool.
19. BCF Import of a file from another tool: preview counts right; topics become issues;
    saved viewpoints under BCF/<file name> (one Ctrl+Z removes all of them); cameras land
    right (metres to document units, perspective and orthogonal); components selected by
    Go to; import the same file again: everything "kept", no duplicate comments.
20. Shared folder mode (two people, same NWF name): both edit different fields of the
    same issue; the second Save toasts "... was also changed by ..." and keeps both
    changes; comments from both survive. Two people creating issues at once get
    different numbers.
21. Model data mode (Playground settings): create issues, save the NWF, reopen: issues are
    there; images still show on this computer (they are local by design).
22. Orthographic view: New from view, export BCF: OrthogonalCamera with a sensible
    ViewToWorldScale (HeightField read as the view height: unverified in namo.camera).
23. Reload with the Issues panel open: it keeps working, one refresh per change (log has
    no duplicate "issues-pane" errors), toggling pins after Reload still works.
24. Dark theme, Reload: list, chips, editor and meeting window readable.

Known limits (by design, stated to users where it matters): issues are keyed by the model
file name in local and shared modes, so Save As starts an empty register under the new
name (use model mode, or keep the name); BCF clipping planes, coloring and visibility are
read but not applied; the overlay draws every pin in its single accent colour (no colour
per status: the overlay API has no colour); in model mode the pictures stay on the
computer that took them.

## 3. Requests for shared modules (not edited; worked around locally)

1. **namo README**: add the `namo.issues` public API (top of `issues.py`) and
   `namo.issuestore` (events, storage layout) to the module index.
2. **namo.config**: one shared "who moves" list (`'move_priority': [...]` in DEFAULTS).
   Clash Assigner keeps its list in its own bundle config and Clash to Issues in its own
   (same default order), so the two can drift.
3. **namo.hooks**: add `('doc-closed', 'hk_issuepins'),` to HANDLERS. The handler already
   clears the pins on doc-closed; until then pins of a closed model stay drawn until the
   next model opens.
4. **namo.store**: a public `RecordStore.path(id)` (issuestore builds it from
   `store.id_to_filename` + `folder` for its per-record lock), and an mtime cache in
   `RecordStore.list()` for shared folders (issuestore implements one locally:
   `IssueStore._read_files`).
5. **namo.ui**: a status-chip column kind for `ui.Table` (cell tone per row), so panes need
   not hand-build a DataGrid (issueui does, in pane.xaml); and `Table` star columns are
   only sized after a dispatcher pass, which off-screen smoke renders must pump.
6. **namo.images**: `to_png(src, dst)` (BCF 2.1 snapshots are converted with
   `images.thumbnail(..., max_width=1500)`, which also caps the size).
7. pyNavis (read-only, for the record): `pynavis.viewpoints.transaction(name, doc)` imports
   `pynavis.doc` even when a document is passed, so it cannot be used in CPython tests;
   tests patch it.

## Refit pass

Second pass after the first field click (2026-10-05). Headless only; nothing clicked.

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Issues (dock pane) | fixed | Set pin called the banned `pick.point`. Now `namo.picking.point` (Measure tool, banner prompt); Set pin is greyed and guarded while the pick waits (the pick keeps the pane clickable), and the pin goes to the issue and register it was asked for | Pane itself: proven route (shipped dock panes). Unproven: a Measure pick started from a dock pane button (shipped tools start it from the ribbon); `Document.GenerateImage` snapshot |
| Issue Stamps: RFI, Hold, Verify, Safety | fixed | `pick.point` + `pick.Unavailable` replaced by `picking.point(prompt, want_item=True)`; toast detail no longer says "at Pin set (no grid nearby)"; refuses under `pynavis run` | Proven (True Distance pick and item lookup) |
| Stamp from Template | fixed | Same pick fix; checks model and saved state before asking for a template | Proven |
| Issue Pins | fixed | Pins were 1.5 % of the model diagonal (0.3 to 6 m): now a real 1.2 m in document units. The click decided by toggle state only; now toggle state or session flag, so Hide Pins always hides. Hiding also clears pins the session no longer lists (tag prefix sweep). Overlay not loaded: button stays off with an error toast. No model: says so | Proven (`pynavis.overlay` as Go to Coordinates). Unproven: `OverlayRegistry.Items` read for the sweep (guarded, falls back to the remembered tags) |
| Meeting Mode | fixed | With a meeting already running it asked the agenda question and then threw the answer away; now it brings the window forward and says so | Proven route (namo.ui modeless window); `Document.GenerateImage` unproven |
| Issue Templates | ok as built | | Proven (forms and files only) |
| Clash to Issues | ok as built | Tooltip ending normalised | Unproven: `TestsViewpointForResult` / `TestsImageForResult` given a group (falls back to its RepresentativeResult; a failed image is counted in the toast) |
| Coordination Report | ok as built | | Proven (files only) |
| KPI Export | ok as built | | Proven (files, `clashdata.snapshot_all`) |
| BCF Export | fixed | Default file was `.bcfzip` (the BCF 2.0 extension): now `.bcf`, with `.bcfzip` still offered. Every export toasted a warning because a Navisworks lens is outside BCF 2.1's 45 to 60 degrees: the clamp is now counted apart from real losses and reported as plain detail on a success toast | Unproven: orthographic `HeightField` as view height (ViewToWorldScale); offset between Revit shared and internal coordinates in other tools |
| BCF Import | fixed | BCF 3.0 colouring components (wrapped in `Components`) were read as empty; both shapes are read now | Unproven: `AlignDirection` + `AlignUp` aim from a BCF camera (the route Plan to Selection uses), saved viewpoints through `SavedViewpoints.AddCopy` |

Foundation requests

1. `namo.picking`: nothing needed. Note for its README: `point()` is safe from a late callback (dock pane button), it only needs `app.get_doc()` and a logger.
2. `namo.camera.from_viewpoint`: orthographic `HeightField` is still an unverified reading; BCF Export's ViewToWorldScale depends on it.
3. pyNavis (read-only, for the record): `pynavis.overlay` has no "clear by tag prefix" or "list tags"; issueapi reads `OverlayRegistry.Items` directly for that. Photo Pins has the same need.
4. Panel slots: pyNavis ships five and its own extension uses three; Playground adds Issues and Source Files, so the count is exactly five. Any stale claim in config.json means one of them toasts "No panel slot free" until Panel slots adds more and Navisworks restarts.

First three clicks

1. Issue Stamps > RFI on a saved model: banner "Click where the RFI goes", the pointer snaps like Measure, click a duct. Toast "RFI 001 created" with the id, level and grid (when the model has grids) and "on <duct name>"; Measure is switched off again and no dimension is left. Esc instead: nothing at all.
2. Issue Pins: toast "1 issue pin shown"; an orange pin exactly on the clicked point, about a person tall beside the duct (not storey sized), label "#1 RFI: RFI 001". Click again (Hide Pins): the pin goes.
3. Issues (dock pane): opens with RFI-001 listed, thumbnail of the view; select it, Set pin, click elsewhere: Location updates, the pin moves within a second, Set pin was greyed while waiting. Double-click the row after orbiting away: the camera returns.

Verify (full run, 2026-10-05): check ok, ipy compile ok (367 files), ipy smoke ok (115), parse ok (138 buttons), fresh ok, names ok; pytest 1,566 passed and 1 failed, IronPython 1,557 passed and 1 failed, the one failure in both being `test_publish.test_history_record_and_toast_text` (group G5, mid-edit). Every issues_bcf test and smoke passes on both engines.

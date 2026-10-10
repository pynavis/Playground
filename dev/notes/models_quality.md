# G5 models_quality: Models, Quality and Publish panels (Project tab)

Everything below is verified headlessly only: pure halves unit tested on CPython 3.11 and
IronPython 3.4, API halves driven through fake Navisworks objects, the two WPF surfaces
(Source Files pane, Folder Watch notice) built from their real XAML/code and rendered off
screen in light and dark, every ribbon script run end to end against fake pynavis modules,
and the real pyNavis BundleParser shows the three panels in the specified order. Nothing
has run inside Navisworks yet.

## 1. Tools

Models panel (Batch_Append, Source_Files, Link_Navigator, Transform_Fixer, Folder_Watch, Stale_File_Alert)

- **Batch Append** (#47): appends many files from a folder (subfolders and file types optional) or a txt/csv/xlsx manifest (optional Order and Trade columns), after a preview that ticks only files not appended yet; one `TryAppendFile` per file under counted progress, stops cleanly between files on Cancel, reports failures by name, stamps load times for Session Stats and applies auto transform presets.
- **Source Files** (#51, dock pane): live list of appended models (show/hide box, name, type, units, item count counted lazily, file time, Out of date / File not found tags) with Isolate, Show all, Select, Zoom, Open folder, Refresh changed and Remove; keyboard Up/Down, Space, Delete, Enter, Ctrl+A; rebuilds on append/remove/refresh and document change.
- **Link Navigator** (#117): from the selected element(s) to their model: info card (files, freshness, creator, units, transform, contents) in the output window, then Select, Isolate, Hide, Open folder, Refresh files, Remove, or Show in Source Files.
- **Transform Fixer** (#55): moves (typed signed lengths or two picked points), turns about Z (about each model's centre, the origin or a picked point), changes model units, resets, and saves/applies transform presets per model file (optionally applied automatically whenever that file is appended); one undo step; checks where the model actually landed and self-corrects the offset-units convention (see check 13).
- **Folder Watch** (#50, toggle): polls the appended models' files every 30 s (no FileSystemWatcher), reports a change once it held still for two polls in a small notice that never takes focus (Refresh now / Later / Show); Navisworks' own refreshes rebase it; Shift+Click for folders, interval, native files, start with Navisworks.
- **Stale Files** (#49): loaded file (NWC) against its source file for every model: Out of date, File not found, folder offline, source not on this computer; output table and toast; Shift+Click to check automatically whenever a model opens (report `stale_files`).

Quality panel (Model_Health_Check, Duplicate_Finder, Model_Compare, Preflight, Session_Stats)

- **Health Check** (#48): scores each model 0 to 100 (units, implausible size, distance from origin 10/100 km, far-away objects beyond 20x the typical object distance, empty models, element ID coverage, duplicate appends, model transforms, file age/freshness, item counts) as output-window cards plus HTML and Excel reports; Shift+Click for thresholds, formats, folder (report `health_check`).
- **Duplicate Finder** (#54): element-level objects with the same class, primitive count and all six box coordinates within a tolerance (default 1 mm), Same model or Across models, optional mesh volume/centroid check; selects the extra copies and saves set `Playground/Duplicates <date time>`.
- **Model Compare** (#53): two appended versions, or a model against a saved snapshot; matches by Revit UniqueId, IFC GlobalId, Element ID, instance GUID, then name and box (a key only when unique on both sides); added green, changed amber (moved/resized/properties), removed red on the old model, unchanged faded; sets `Compare/Added|Changed|Removed` updated in place; Excel list.
- **Preflight** (#107): checks the document against a profile (saved, units consistent, expected models, files current, required sets, clash tests run after the newest model data, New clashes within a limit, saved viewpoints, no hidden items, no leftover overrides (best effort), sectioning off, TimeLiner tasks attached (off by default)); Shift+Click edits team-shared profiles (report `preflight`).
- **Session Stats** (#75): per model file sizes, items, geometry items, primitives and fragments (exact up to 40,000 geometry items per model, then a weighted sample, marked "estimated"), extent, arrival and load time; table, bar chart and workbook beside the document (report `session_stats`).

Publish panel (NWD_Publisher, Model_Wipe)

- **NWD Publisher** (#52): writes the next numbered NWD from a name template (`{project}_{file}_{date:%Y%m%d}_v{version:00}.nwd`, version counted across dates), by Publish (with title, author, comments, copyright, expiry...), Export (plain copy) or Save as; optional Preflight first (a failed check asks "Publish anyway?"); archives older versions into `Archive\`; logs history; opens the folder.
- **Model Wipe** (#108, the one alert-red icon): counts every kind of removable data (saved viewpoints, sets, clash tests, viewpoint comments, overrides, hidden state, item transforms, TimeLiner tasks, Playground data), nothing ticked to start, a second confirm with exact counts, one 'Model Wipe' transaction; redlines always reported as left (no script route).

Hooks (registered in `lib\namo\hooks.py`): `hk_stalecheck` (doc-opened, off by default), `hk_folderwatch` (startup, doc-opened, app-closing), `hk_sessionstats` (doc-opened, model-appended), `hk_transformpresets` (model-appended).

## 2. In-app checks (please click through in this order)

Use a saved federated NWF of 3+ Revit NWCs (one in different units if possible) and keep `%APPDATA%\pyNavis\logs\pyNavis.log` open; search it for `Playground:` after each step.

Source Files
1. Click Source Files. The panel title bar reads "Source Files"; one row per model with name, type, units, item count ("counting" first, then a number within a few seconds even on a big model) and file time. Navisworks stays responsive while counting.
2. Untick a model: it disappears; one Ctrl+Z brings it back. Hide a model from the Selection Tree instead: within about 2 s its box unticks.
3. Ctrl+click two rows, Isolate: only those two show; Show all brings every model back but items you hid inside a model stay hidden. Select selects the model roots; Zoom and a double-click frame them.
4. Re-save (or touch) the RVT/source of one NWC so it is newer, then close and reopen the NWF (or append something to trigger a rebuild): that row shows "Out of date". Refresh changed reloads it and the tag clears. Report what `Document.UpdateFiles()` returned (toast "Reloaded the changed models" vs "No model files changed").
5. Append a model (Navisworks' own Append) with the panel open: the list updates once. Remove a model from the panel: a confirm, then it is gone. Report whether Ctrl+Z brings a removed model back (unknown).
6. Click Reload with the panel open: the panel rebuilds with no errors in the log; append a model again and confirm the list updates once (no doubled subscriptions).
7. Keyboard: click a row, then Up/Down, Shift+Down, Space (toggles visibility), Enter (zoom), Delete (asks to remove), Ctrl+A.
8. Switch Navisworks to the dark theme, Reload: rows, tags and themed check boxes stay readable.

Batch Append
9. Point it at a folder of NWCs where some are already appended: the preview ticks only the new ones and says how many are already appended. Append: counted progress per file; press Cancel half way: "Appended n of m files, stopped before the rest". Note how long 10 NWCs take compared with selecting the same files in Navisworks' Append dialog (Playground appends one file per `TryAppendFile` for progress, cancel and per-file failures; `AppendFiles` in one call is not used).
10. A manifest .xlsx with Order and Trade columns: the preview follows Order, shows Trade, and lists missing paths as Missing (unticked).
11. Append an RVT directly; run Batch Append on the same folder again: the RVT shows as Appended (matched through its NWC cache's folder and name). Report what Model.FileName and Model.SourceFileName hold for that model (Link Navigator shows both as "Loaded from" and "Source file"). Playground assumes FileName is the loaded file (the NWC) and SourceFileName the native file.

Link Navigator
12. Select an element: the card shows its model, files with sizes and dates, freshness, "Created by" (Model.Creator: note what text Navisworks gives), units, transform and contents. Choose Show in Source Files: the panel opens with that model's row selected.

Transform Fixer (the convention checks matter most)
13. Document and model in the same units: Move X by 1 m (or 3'). The model moves exactly that far east; Navisworks' own Units and Transform dialog shows Origin X 1. One Ctrl+Z undoes it.
14. Document in metres with a model in millimetres (or feet/inches): Move X 1 m. The model must move exactly 1 m. If the toast says Playground "corrected the move", Navisworks reads model offsets in DOCUMENT units: please report it (the learned convention is saved in `%APPDATA%\pyNavis\settings\playground_transforms.json`, key `translation_units`).
15. Turn 90 degrees about the model centre: seen from the Top view the model turns COUNTER-clockwise and stays centred, and the toast does not say it could not confirm where the model landed. Clockwise means the Rotation3D component order assumption (A, B, C, D = x, y, z, w, from namo.camera) is wrong for writing: report it.
16. Move by two picked points: picks snap like Measure; the model moves from the first point to the second.
17. Change the units of a model (Millimeters to Meters): it scales by 1000; Ctrl+Z. A model with a scale in its Units and Transform keeps that scale after a move.
18. Save a preset with "Apply it automatically", remove the model, append the file again with Navisworks' Append: toast "Applied the transform preset for ..." and the model is back in the preset position. Repeat with Batch Append: the toast detail mentions the preset.

Folder Watch
19. Click Folder Watch: toast "Watching N model files in M folders". Re-save an appended NWC in place: within about a minute (two 30 s polls) a notice slides in at the bottom right of Navisworks WITHOUT taking focus (keep typing in a field while it appears). Refresh now reloads the model; Later dismisses; Show opens Source Files on that model.
20. Change a source RVT and use Navisworks' own Refresh: no extra notice for the NWC Navisworks regenerates.
21. Shift+Click: interval 10 s and "Start watching with Navisworks". Close Navisworks while watching, start it again: the button shows pressed (set from the startup hook through the runtime's ToggleStateStore, an unofficial route) and watching resumes (touch a file to confirm). Switch it off, restart: not watching.

Stale Files and Session Stats
22. Stale Files: the table shows a status tag per model and the toast summarises. Shift+Click "Check whenever a model opens", reopen an NWF with an out-of-date model: a warning toast; with every model current: nothing.
23. Session Stats: table, bar chart and a workbook beside the NWF (path printed). Primitives are non-zero (Geometry.PrimitiveCount); a big model's Note says "estimated from N of M". Models opened with the NWF say "opened with the document", files appended with Navisworks' Append say "appended" with a time, Batch Append files show load seconds.

Health Check, Duplicate Finder, Model Compare
24. Health Check on the federated model: one card per model, worst first; an HTML and an xlsx (Summary, Checks, Outliers) beside the NWF, paths printed (paths are text, not links: the output window cannot open file links). Element ID coverage should read about 100% on Revit models; if low, the Revit property names differ from `namo.items.REVIT_PROPERTIES` (note what the Properties window calls them).
25. Move one element about 50 km with Item Tools and run Health Check again: Far-away objects warns and links it (the link selects it). Note the time on the largest model.
26. Health Check Shift+Click: untick HTML, tick "Open the HTML report": only the xlsx is written.
27. Append the same NWC twice, run Duplicate Finder on the whole model: one group per object, kind Across models, the extra copies selected, set `Playground/Duplicates ...` in the Sets window; one Ctrl+Z removes the set. With the shape check on, it still finishes and does not split real duplicates. A 1/16" tolerance works in a feet document.
28. Append V1 and V2 of one Revit model, Model Compare > two models: green/amber/red colours with the unchanged objects of BOTH versions faded; Compare folder holds Added, Changed, Removed; "Matched by" says Revit UniqueId; one Ctrl+Z removes the colours and sets; running it again updates the sets in place.
29. Save a snapshot of V1 in a saved NWF, reopen, compare with V2: removed objects are listed but not coloured. With "Also compare properties" = Element > Type, retyped objects show "Properties changed".

Preflight, NWD Publisher, Model Wipe
30. Preflight with unsaved changes: "Document saved" warns; mixed units are named.
31. Run all clash tests, Preflight: "Clash tests run after the newest models" passes. Re-export one NWC and Refresh, Preflight again: it names the tests as run before the newest model data (ClashTest.LastRun read as local time; the newest model time is the newest NWC file time, so a test run between an export and its refresh still passes).
32. Leave some clashes New: "New clashes within the limit" reports the count; with a profile limit of 50 it reads "within the limit of 50".
33. Hide an item: "No hidden items" names it. Override a colour: "No leftover appearance overrides" counts it (unverified: Geometry.PermanentColor vs OriginalColor); a clean model reports none. Sectioning on: "Sectioning off" warns.
34. Preflight Shift+Click: save a profile with an expected model pattern (ARCH*), a required set (Folder/Set) and the TimeLiner check: the missing pattern and set fail; the TimeLiner check counts leaf tasks with nothing attached.
35. NWD Publisher on a saved NWF: writes `<project>_<file>_<yyyymmdd>_v01.nwd` into `<doc folder>\Published`; File > Publish properties of that NWD show the Title, Author, Copyright and Expiry from the form; a second run writes v02 and moves v01 into `Published\Archive`; "Leave hidden items out" really leaves them out.
36. Publisher method Export: the open document is unchanged. Method Save: the open document becomes the NWD; history stays with the original NWF.
37. Publisher with a failing Preflight check: the confirm names the failures; No stops silently.
38. Model Wipe on a COPY of a model with viewpoints (with comments), sets, clash tests, overrides, hidden items, a moved item, TimeLiner tasks and Playground data: the labels show counts; wipe everything; press Ctrl+Z once and note which kinds come back (unverified whether Clear/TestsClear/TimeLiner edits join the transaction's undo; Playground data is known not to). TimeLiner tasks must be gone (TasksCopyFrom with an empty list, falling back to TaskRemoveAt). Comments-only wipe keeps the viewpoints.
39. `reports.run('preflight', {'formats': ['html', 'xlsx']}, interactive=False)`, and the same for `health_check`, `session_stats`, `stale_files`: no dialogs, files written, result level sensible.

## 3. Requests for shared modules (not edited; worked around locally)

- `namo.paths.is_reachable(folder)` logs "shared folder ... is not reachable; using local data" for ANY folder, which misleads callers probing model folders. Fix: move that `session.log` call into `team_root()` (log only when the shared root itself is unreachable). Models tools use their own share probe (`modelmgmt.reachable`, cached per share root).
- Cross-module trap worth a README line (no change needed in namo): the pyNavis output window opens only http(s)/mailto links externally; a clicked `file:` link navigates the output window itself (`HtmlOutputWindow.IsExternalLink`). Print paths as text (`namo.mdl_output.path_line`) and open files from the script.
- `dev/tests/_compat.tmpdir(name)` wipes with `ignore_errors=True`, so a folder still locked from the CPython run can leak files into the IronPython run seconds later (seen once as a transient failure). Suggest `tmpdir` append the engine name (`name + ('-ipy' if IRONPYTHON else '-cpy')`). My test files do this themselves.

Assumptions recorded in code (all checked by the steps above): Model.FileName is the loaded file and SourceFileName the native file (11); model offsets are in model units, self-corrected when not (14); Rotation3D(a, b, c, d) is (x, y, z, w) (15); `UpdateFiles()` returns True when it reloaded something (4); the startup hook may set the toggle's pressed state through `PyNavis.Runtime.Ribbon.ToggleStateStore.Set` (21).

## Refit pass

Second pass after the first field click (dev\REFIT_BRIEF.md). Every bundle in the group was read end to end with its namo modules; nothing was run in Navisworks.

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Batch Append | ok as built | Nothing found. | Unproven: `Document.TryAppendFile` (per file, guarded, failures named) |
| Source Files (dock pane) | fixed | Built like the shipped Viewpoint Tracker and Section Nudge (`__pane__.Find`, `pane.Visible`, session holder detach, guarded handlers). A toolbar action Navisworks refused was only logged, so the click looked dead: every action, the visibility box, Delete, Enter and double-click now toast the failure too. | Proven pane route. Unproven: `Models.CollectionChanged`, `Document.FilesUpdated`, `UpdateFiles`, `TryRemoveFile`, `Models.SetHidden` on a model root |
| Link Navigator | fixed | Counted up to 500,000 items per model (8 models) before showing anything, with no progress: now 200,000 shared across the selection, and it says Source Files has the full count. Refresh failures toast. | Unproven: `UpdateFiles`, `TryRemoveFile` |
| Transform Fixer | fixed | The known defect: three `pick.point` calls (turn-about point, move from, move to) replaced by `namo.picking.point` and `namo.picking.points`; `pick.Unavailable` handling gone. The check of where the model landed took the first prediction inside a tolerance that is 2.7 ft at 1.37 million ft, so a move made in the wrong units convention could be reported as fine: the nearest prediction now wins, and the tolerance is the `pynavis.faces.tolerance_for` float32 formula. "Same point" test scales with the coordinates. Units, reset and save-preset failures toast instead of raising. | Picks proven. Unproven: `SetModelUnitsAndTransform`, `Transform3D.Factor()` / `Combine()`, writing `Rotation3D(a, b, c, d)` (order read as x, y, z, w, as shipped Section Nudge reads it) |
| Folder Watch (toggle) | ok as built | Nothing found. The toggle follows the Hide Tabs pattern (the session decides, not the button state). | Unproven: the non-activating notice (WS_EX_NOACTIVATE through ctypes, foundation `ui.non_activating`), `FilesUpdated`, `ToggleStateStore.Set` from the startup hook |
| Stale Files | ok as built | Nothing found. | Proven (file stats and the output window only) |
| Health Check | fixed | A model in shared coordinates (the owner's is 418 km out) failed "Distance from origin" on every model with "expect jitter and inaccurate clashes", which the field measurements contradict. Beyond the warn distance it now measures the float32 noise of a few objects (`pynavis.geometry.world_triangles` stats, the True Distance route) and reports info when the geometry still reads true, warn above 0.5 mm, fail above 10 mm; distance alone decides only when nothing could be measured. | Proven noise route. Unproven: none new |
| Duplicate Finder | fixed | In a feet document the 1 mm default prefilled the tolerance box as `0' 0"`, which the form's own check refused: first click failed on the owner's model. The prefill now rounds up to 1/16 in and the saved 1 mm does not drift. Far from the origin: the hash slack is float64 steps at the largest coordinate (was a fixed 1e-12), boxes that turn out to be float32 values widen the tolerance to their real precision and the result says so, the shape check welds at the measured float noise and compares centroids at it. Tolerance reads `1/16 in`. | Proven: `pynavis.sets.create`, selection, `geometry.world_triangles`. Unproven: `Geometry.PrimitiveCount` at this scale |
| Model Compare | fixed | Same tolerance prefill and drift fix; tolerance widened to the boxes' precision far from the origin, with a note. | Unproven: `ModelItem.InstanceGuid`, permanent colour overrides through `namo.paint`, snapshots in the document database |
| Preflight | ok as built | Nothing found. Sectioning is read the way `pynavis.section.clear` reads it. | Unproven: `ClashTest.LastRun`, `Geometry.PermanentColor` vs `OriginalColor` (labelled best effort), TimeLiner `Selection.IsClear` |
| Session Stats | ok as built | Nothing found. | Unproven: `Geometry.FragmentCount` |
| NWD Publisher | fixed | Archiving could move the OPEN document: after Save as NWD the open file is the last published version, and the next publish moved every older version, including it, into Archive. The open document and every appended model's file are now protected from both the write and the archive move, nothing is ever overwritten (target or archive), one confirm names the exact file, the folder, how many versions move and what Save as NWD does to the open document, the folder is only created after that confirm, and the toast gives the full path and size. | Unproven: `Document.PublishFile`, `ExportToNwd`, `SaveFile` (guarded; a missing file after the call is reported) |
| Model Wipe | fixed | Reported kinds as wiped on trust. Now every countable kind is counted again afterwards and anything still there is reported as not wiped with how many are left. TimeLiner uses `TasksClear()` first; saved viewpoints and sets fall back from `Clear()` to `Remove()` per top-level item (the shipped Deleter route). The toast says the file on disk is unchanged until you save. "Permanent item transforms" reads "Item transforms (moves made with Item Tools)". | Proven: `SavedViewpoints.Remove`. Unproven: `SavedViewpoints.Clear`, `SelectionSets.Clear`, `TestsClear`, `ResetAllPermanentMaterials/Hidden/Transforms`, TimeLiner clears, whether they join one undo step |

Foundation requests (nothing in a shared module was edited):
- `namo/paths.py` `is_reachable`: still logs "shared folder ... not reachable" for any folder; move the log into `team_root()`.
- `namo/ui.py` length fields: a default smaller than 1/16 in prefills as `0' 0"` in a feet document. Any tool with a small length default hits what Duplicate Finder hit. Suggest `default_text` fall back to decimal inches when `lengths.format_input` rounds a non-zero value to zero.
- `namo/mesh.py` `summary(tris, tol=1e-6)` and `weld(..., tol=1e-6)`: the default weld tolerance is a fixed epsilon; callers far from the origin must pass the walk's noise (Duplicate Finder now does).

First three things to click:
1. Duplicate Finder on the federated model in feet: the tolerance box opens with `0' 0 1/16"` and Find runs; the toast and note read "Tolerance 1/16 in" (a "Wider than asked" note would mean the boxes are single precision this far out: please report it).
2. Transform Fixer > Move by two picked points: the banner along the bottom asks for the two points, the marker is Navisworks' own Measure snap, the model moves from the first to the second, the toast says "Moved ..." without "Could not confirm where it landed", and one Ctrl+Z undoes it. Then "A point I pick" with a 90 degree turn.
3. NWD Publisher with method Publish: one confirm names the exact file and folder and says the open document is not changed; the toast gives the full path and size; a second run writes v02 and moves v01 to Archive. Then Health Check: "Distance from origin" should be Info ("as models in shared coordinates do ... reads true to ...") rather than Fail.

Verify: `check ok, pytest ok, ipy compile ok, ipy test ok, ipy smoke ok, parse ok, fresh ok, names ok` (pytest 1,618 passed, IronPython 1,603 passed, WPF smoke 115 passed).

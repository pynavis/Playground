# G6 views: the Viewpoints, Capture and Navigate panels (tab Views)

Built by agent G6. Everything here is verified headlessly only (CPython pytest,
IronPython 3.4 tests, IronPython WPF smoke, the real pyNavis BundleParser, pyflakes).
Nothing has been clicked in Navisworks yet.

Ribbon order: Viewpoints panel (Batch Viewpoints, Viewpoints from Excel, Export
Viewpoints, Viewpoint Sync, Where Am I), Capture panel (Viewpoints to Images, Batch
Images, Batch PDF), Navigate panel (Level Sectioner, Level Up and Level Down as
nobuttons on Alt+PgUp / Alt+PgDn, Camera Sync toggle, Spotter stack: Coordinate
Spotter | Clear Spots, Sheet stack: Sheet Overlay | Clear Sheet).

## 1. Tools

| Tool | What it does |
|---|---|
| Batch Viewpoints (#13) | Quick switch Per level / Per grid intersection / Per selection or search set / Per model, then a form (view type, cut and eye heights, floor clip, frame, folder and name templates with tokens, replace / keep both / skip) and a ticked list. Every view is built DETACHED from a copy of the current view (keeps lighting and render style) and filed in ONE transaction. Plans: section plane at level + cut (default 1.2 m), optional bottom plane, top-down orthographic camera framed by ZoomBox on what stands on that level (tree descent, `levels.band_boxes`). Eye level: from the south-west corner of the floor, top plane just under the next level. Grid intersections are found by sampling `GridLevel.ClosestIntersection` over the model, then completed from the grid lines (every crossing inside the model asked once more). Sets and models: ZoomBox along the current view direction, optional "hide everything else" (hidden flags set, `CaptureRuntimeOverrides`, flags put back, camera restored). Each view gets a provenance comment (option). |
| Viewpoints from Excel (#18) | Quick switch Export / Import / Blank template. Workbook 'Viewpoints' (Folder, Name, Eye XYZ, Target XYZ, Up XYZ, Projection, FOV/Height, Comment) in document units plus a 'Read me' sheet. Import finds the header row anywhere in the first ten rows, any column order, numbers or length text; plans create/update by Folder + Name (case-insensitive), confirms, applies in ONE transaction; row problems go to the output window. Updates keep name, place, Guid, comments and section (`ReplaceWithCopy`), or, for views that store hidden items/overrides, recall + re-aim + `ReplaceFromCurrentView`. New comment lines are added, never removed. |
| Export Viewpoints (#15) | Ticked list of saved viewpoints (filter by folder + Select all), then Navisworks viewpoint exchange XML, a Playground package (.nvp.json), or both. Comments optional; section planes in the XML optional (off by default; the package always keeps them). The XML layout lives in `vpexport.EXCHANGE_LAYOUT`. |
| Viewpoint Sync (#21) | Export package (choose folders, subfolders follow) / Import package (.nvp.json, or a Navisworks .xml): choose folders, target folder, keep or flatten the package folders, skip / replace / keep both, sections and comments on or off, unit conversion when the package came from other units; ONE transaction; a report table in the output window. |
| Where Am I (#106) | One `forms.alert` with Copy: file, the saved viewpoint (and whether the camera is still on it), eye in document units, compass heading + bearing + pitch, nearest level (grid levels or the session's estimated levels) with height above it, grid position (`FormatCombinedDisplayString` + nearest intersection and distance), lens, section, models and geometry item count (time-boxed at 2 s, cached), units, selection count. |
| Viewpoints to Images (#16, report `viewpoint_images`) | Ticked list, then size (720p, 1080p, 4K, custom), PNG/JPG + quality, file name template (`{n:00} {name}`, `{folder}_{name}`...), folder, overlay (ScenePlusOverlay), contact sheet, open when done. Writes a dated subfolder with the images, `thumbs\` and `index.html` (relative links, so the folder travels). Counted progress, cancel keeps what was saved. |
| Batch Images (#73) | Sources: saved viewpoints, clash results (tests chosen, statuses, top-level groups and ungrouped clashes, a confirm above the cap), Playground issues (statuses; via `namo.issues.list` / `issues.go_to`, guarded: says "not available" when the module set is missing). Folder layout `Viewpoints\`, `Clashes\<test>\`, `Issues\` + one `index.html`. |
| Batch PDF (#120, report `batch_pdf`) | Ticked list, folder order or a hand order (Top / Up / Down / Bottom, Ctrl+Up/Down), A4/A3/Letter/Tabloid landscape, 150 or 220 dpi, JPEG quality, title page (title, project number and name, company, model, date, author, count), contents page(s), comments under each image, a footer template, page numbers. JPEG captures into a temporary folder (removed afterwards) embedded by `namo.pdf`. |
| Level Sectioner (#20) | Levels from the active grid system, else IFC storeys in the tree, else the Revit Level property (Element > Level, Base Constraint, Reference Level, Schedule Level), estimated elevations marked "Estimated"/approximate. Single-pick list with the current level selected; section at level + cut height, optional slab view (bottom plane), optional plan camera; ONE CopyFrom (one undo step). Shift+Click: cut height, slab view and depth, plan view (shared with Level Up/Down, stored in metres). Remembers the level per document. |
| Level Up / Level Down | Alt+PgUp / Alt+PgDn (nobuttons): step the cut one level, toast the level name and the cut height. Current level = the level under the section's top plane when one is on (the remembered level while the plane still sits where it put it), else the remembered level, else under the eye. |
| Camera Sync (#116) | Toggle. Each session writes `%APPDATA%\pyNavis\playground\camsync\<pid>.json` (atomic) from `CurrentViewpoint.Changed`: written once the camera is still for 80 ms, or every 250 ms while it keeps moving. A 120 ms DispatcherTimer polls the newest live OTHER session and applies a newer camera (SetCamera json on a copy, else the converted camera dict when units differ, then one CopyFrom). Echo protection: an applying flag plus "never send back the camera just applied". Dead sessions' files are deleted. Off, a fresh start (Reload) and app closing (`hk_camsync`) stop timers, unhook events and delete the file. |
| Coordinate Spotter (#81) | Pick loop on the Measure tool (`namo.picking.point`, native snapping, the object found under the picked point) with the prompt and the last reading on the banner; each point a 3D cross + label 'P3  X ...  Y ...  Z ...' under its own overlay tag, numbering kept until Clear Spots. On Esc: table in the output window (doc units, metres, object, model), TSV on the clipboard, then Save as Excel / Save as CSV (Esc skips). Shift+Click: local origin (pick, type, or back to the model origin), stored per document; markers relabel. |
| Clear Spots | Clears every spot tag and restarts numbering. |
| Sheet Overlay (#82) | First run (or Shift+Click): DXF file, layers ticked (counts of lines and texts), elevation (a level or typed, negatives allowed), drawing units (from $INSUNITS or chosen), position by rotation + offset or by two reference points (drawing points typed, model points picked in one two-click run of the Measure tool, `namo.picking.points`; scale from the units or from the points, with a sanity note). Draws all lines in one overlay item (cap 30,000, says when cut) and up to 300 texts as labels with small ticks. The placement is stored per document: the next click redraws it at once. |
| Clear Sheet | Removes the sheet and its labels. |

Deviations and decisions (no catalog change needed, but worth knowing):
* Coordinate Spotter's local origin is set with Shift+Click (config.py), so a plain click goes
  straight to picking.
* Camera Sync writes are "debounced 80 ms with a 250 ms ceiling" so the other window follows an
  orbit while it happens; a pure 80 ms debounce would only update when the orbit stops.
* Camera Sync has no `context:` so it can always be switched off.
* Export Viewpoints writes section planes into the XML only on request (least certain part of
  the schema); the package always has them.
* Viewpoints to Images and Batch Images write into a dated subfolder of the chosen folder (the
  report contract's `name_template`), so runs never overwrite each other's contact sheets.
* Capture runs use `capture.KeepState`: when a captured view stores hidden items or overrides,
  the user's own hidden/override state is snapshotted into a temporary saved viewpoint
  ('.Playground view to restore') and recalled afterwards, all inside one transaction that nets
  to nothing. Without that, recalling such views would leave the model hidden the way the
  last captured view was.

Modules (all mine): `vp_common` (shared: specs, lengths, add_view, section of any viewpoint),
`vpbatch`, `vpexcel`, `vpexport`, `vp_sync`, `vp_whereami`, `vp_ui` (hand-order window),
`levels`, `camsync`, `hk_camsync`, `spotter`, `dxf`, `sheetoverlay`, `capture`,
`rep_viewpoint_images`, `rep_batch_pdf`.

Data kept: per-tool settings via `script.get_config`; level settings in pynavis.settings
`playground_levels`; current level per document (session + store `level-sectioner`); estimated
levels (session); spotter points (session holder `spotter`), spotter origin (store
`coordinate-spotter`); sheet placement (store `sheet-overlay`); camera sync files
(`%APPDATA%\pyNavis\playground\camsync`).

## 2. In-app checks (please click these, in this order)

Use a saved NWF of a Revit federation with a grid system and levels (Grids and Levels on),
a few saved viewpoint folders (one view that stores hidden items), two clash tests with
results, and a second copy of the file in another folder for Viewpoint Sync and Camera Sync.

1. **Camera convention first** (it underpins everything): Where Am I in the ViewCube Front
   view must say "Looking: N, bearing 0°, level"; in Top it must say "straight down".
   Click the ViewCube's Right face (the camera east of the model, looking west): bearing 270°.
2. **Where Am I**: on a saved view it names it; orbit a little: "moved away from ...".
   Note what Grid shows: the first part comes from `GridIntersection.FormatCombinedDisplayString(point,
   1.0)`. If it shows nonsense (or feet where you work in mm), tell me the text: the 1.0
   conversion factor is a guess. The nearest intersection and distance after it are ours.
3. **Level Sectioner**: pick Level 2. Expect one section plane 1.2 m above Level 2 keeping
   what is below (if the model above stays and below vanishes, the plane direction is
   inverted: tell me). One Ctrl+Z must undo it. Shift+Click: tick slab view and plan view,
   run again: the floors below Level 2 vanish (0.5 m below kept) and the camera looks straight
   down, framed on the model, north up.
4. **Level Up / Level Down**: press Alt+PgUp and Alt+PgDn over the 3D view. Expect the cut to
   step and a toast "Level 3 / Cut at ...". At the top: "Already at the top level". If
   Navisworks swallows Alt+PgUp, tell me which keys reach it.
5. **Level fallback**: open a model without grids (Revit NWC). Level Sectioner should list
   levels as "Estimated" after a short progress window; check the elevations against Revit
   (they should be within a few cm). Try an IFC with IfcBuildingStorey nodes too.
6. **Batch Viewpoints, per level (plan)**: all levels, default names. Expect a folder
   Batch/Levels with one plan per level, each cut and framed on that level (a podium level
   framed wider than a tower level). One Ctrl+Z removes all. Run it again with Replace: the
   views are replaced in place (same position in the tree).
7. **Batch Viewpoints, eye level**: views stand inside the SW corner of each floor looking
   across, the floor above cut away.
8. **Batch Viewpoints, per grid intersection**: choose a level. Check the chooser lists every
   intersection of your grid (names like A-1). Plan zoom views are centred on each one;
   eye-level views look along the chosen axis. Report a missing or extra intersection.
9. **Batch Viewpoints, per set with "Hide everything else"**: each saved view, when clicked,
   must show only its set. After the run, nothing you had hidden before is changed and the
   camera is back. If the toast warns that hidden items were not stored, turn on Options >
   Interface > Viewpoint Defaults > Save Hide/Required Attributes and run again; tell me
   whether that was needed (it decides whether `CaptureRuntimeOverrides` follows that option).
10. **Viewpoints from Excel**: Export all, open in Excel, change one Eye Z, add a row with a new
    name and folder, add a comment line, save, Import. Confirm says "Create 1 viewpoint, update
    1 viewpoint". The changed view moved, kept its comments plus the new line, kept its
    section; the new view sits in the new folder with sectioning off. One Ctrl+Z undoes all.
    Repeat with a view that stores hidden items: it must keep them.
11. **Export Viewpoints XML into Navisworks**: export two folders as XML, open another file,
    Saved Viewpoints > right-click > Import Viewpoints. Folders, names and cameras must match
    (compare with Where Am I). If Navisworks refuses the file, send me the first lines of its
    error; then try again with comments off. Then tick "Include section planes" and check
    whether the sections come across (that part of the schema is the least certain).
12. **Viewpoint Sync**: export two folders as a package from file A, import into file B under
    "From A", policy Keep both. Cameras and sections must match A's; the report table lists
    every view. Try a package from a model in other units (mm vs ft): positions convert.
13. **Viewpoints to Images**: 3 views including the one with hidden items, 1280 x 720 PNG.
    Each image must show its own view (this checks that `CurrentSavedViewpoint` applies
    before `GenerateImage` renders). Afterwards the model shows exactly what you had hidden
    before, the camera is back, and no '.Playground view to restore' viewpoint remains. Check the
    Undo list: at most one "Keep the view" entry. Open index.html: thumbnails link to images.
14. **Batch Images**: viewpoints + one clash test (New, Active) + issues if installed. Folders
    Viewpoints, Clashes\<test>, Issues; clash images show the highlighted pair.
15. **Batch PDF**: 5 views, hand order, A3, comments on. Check the title page fields come from
    Playground settings (project, company, user), the contents page numbers match, the footer, and
    that the images are sharp enough at 150 dpi (try 220). Note the time per page.
16. **Camera Sync**: open the second copy in a second Navisworks window, turn Camera Sync on
    in both. Orbit in one: the other follows during the orbit (not only after). Swap. No
    jitter or ping-pong. Check Edit > Undo does not fill up with view changes (if it does,
    tell me: the CopyFrom route would need changing). Close one window: the other toasts
    "Camera sync partner closed". Turn it off: `%APPDATA%\pyNavis\playground\camsync` holds no file of
    that session. Try with an mm model against an m model.
17. **Coordinate Spotter**: click 3 points on edges and vertices: crosses and labels appear,
    the banner shows the last reading. Esc: the table, then Save as Excel. Paste into Excel
    too (TSV). Shift+Click > Pick the local origin, then Spotter again: values relative.
    Clear Spots removes them.
18. **Sheet Overlay**: a DXF floor plan in mm onto a model in m, at Level 1, two reference
    points (two grid intersections typed from the DXF, picked in the model). The plan must
    sit on the grids. Untick hatch/dimension layers. Note the frame rate with ~30,000 lines.
    Click Sheet Overlay again: it redraws at once. Clear Sheet removes it.
19. **Save dialogs**: every save dialog should open in the model's folder with a sensible name
    (we pass a full path as the default file name).

## 3. Requests for modules I do not own

1. `namo.camera.clip_state` / `set_clip_state` only read and write the CURRENT view. I needed
   them for any Viewpoint and duplicated them as `vp_common.clip_state_of(viewpoint)` and
   `vp_common.apply_clip_state(viewpoint, payload)`. Fix: give `clip_state` a `viewpoint=None`
   argument (`planes = (viewpoint or _doc(doc).CurrentViewpoint.CreateCopy()).ClipPlanes`),
   and split the body of `set_clip_state` into `apply_clip_state(viewpoint, payload)` that
   `set_clip_state` calls before its CopyFrom. Also record `plane.Alignment` and
   `plane.Distance` (the exchange XML wants both).
2. `namo.camera.save_view` builds its viewpoint from a camera dict on the current view and
   always dedupes names. I needed a ready detached Viewpoint (or a SavedViewpoint from
   `CaptureRuntimeOverrides`) and a replace / keep / skip policy: `vp_common.add_view`. Fix:
   `save_view(name, folder=None, cam=None, comments=None, doc=None, viewpoint=None,
   saved_item=None, policy='keep')`, using `ReplaceWithCopy(parent, index, item)` for
   replace (the root overload is `ReplaceWithCopy(index, item)`).
3. `namo.images.ViewKeeper` puts back the camera and re-applies the saved view that was
   current; it cannot restore the user's own hidden items/overrides after capturing views that
   carry theirs. `capture.KeepState` does it (temporary viewpoint from
   `CaptureRuntimeOverrides`, recalled and removed in one transaction). Worth moving into
   `images` and mentioning in the README trap for `capture_saved`.
4. `dev/tests/test_items.py` fake: `SavedViewpoints` lacks `ReplaceWithCopy`, `Remove`,
   `EditComments`, `CaptureRuntimeOverrides`, `ReplaceFromCurrentView`; the fake `Api` lacks
   `ViewpointRenderStyle`, `ViewpointLighting`, `SavedViewpointAnimation`; `SelectedItems` is
   a list without `.Count`. Extended locally in `dev/tests/test_vp_common.py` (`ViewsSaved`,
   `extend`, `make_doc`).
5. `namo.ui` 'length' fields refuse negative values (pynavis.lengths). Elevations and offsets
   can be negative, so Sheet Overlay uses text fields read by `vp_common.signed_length`. A
   `'signed': True` option on length fields would be cleaner.

## Refit pass

Second pass after the first field click (Photo Pins). Every bundle of the tab was re-read
against the shipped pyNavis tools; nothing here has been clicked in Navisworks.

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Batch Viewpoints | fixed (small) | A comment Navisworks refuses no longer fails a view that was already filed (`vp_common.add_comments` logs and carries on). Sections and plan cameras already follow `pynavis.section` (AlignToPick Custom, AlignDirection + AlignUp + ZoomBox, one transaction). | Proven for level, set and model views. Unproven: `GridLevel.Elevation`, `GridLevel.ClosestIntersection`, `GridIntersection.Line1/Line1Direction` (per grid intersection), `ContainsVisibilityOverrides` after "hide everything else"; all guarded with a toast |
| Viewpoints from Excel | fixed | Updating a view rebuilt it from its camera (redlines lost) or, for a view with hidden items, recalled it on screen and re-captured it (`ReplaceFromCurrentView`, the dead end `lib\vpspeeds.py` documents). Now the shipped Speeds to Saved route: copy the saved item, edit the copy's viewpoint, `ReplaceWithCopy`, keep the Guid; the old routes remain only as fallback. Ticking nothing now says so. | Proven (vpspeeds route, `pynavis.xl`) |
| Export Viewpoints | fixed (small) | Ticking nothing ended silently; now a toast. | Package: proven reads. Unproven: the exchange XML layout against Navisworks' own Import Viewpoints |
| Viewpoint Sync | fixed (small) | Importing with no folder ticked ended silently; now a toast. It is a package copy between files as the catalog specifies, not a live link. | Proven (AddCopy, ReplaceWithCopy, transaction). Unproven: `Viewpoint.TrySetCamera` json, `AddComment` |
| Where Am I | ok as built | Live camera read through `CreateCopy`, grid through `GridSystem.ClosestIntersection` as `pynavis.clash` does. | Proven. Unproven: `FormatCombinedDisplayString(point, 1.0)` (guarded; the nearest intersection and distance are ours) |
| Viewpoints to Images | fixed (small) | Ticking nothing ended silently; now a toast. Image route is `Document.GenerateImage` through `namo.images`, as BRIEF.md names. | Unproven: `GenerateImage` right after `CurrentSavedViewpoint = view` (no shipped tool renders images); failures are per image and reported |
| Batch Images | ok as built | Same capture route; clash images through `TestsImageForResult`. | Unproven: `GenerateImage`, `TestsImageForResult` |
| Batch PDF | fixed (small) | Ticking nothing ended silently; now a toast. | Unproven: `GenerateImage` |
| Level Sectioner | fixed | Tooltip ended "Shift+Click sets the cut."; now "Shift+Click for settings.". The cut itself already matches `pynavis.section` and `lib\sectionnudge.py` (CreateCopy, AlignToPick Custom with the normal into the kept side, one CopyFrom). | Proven. Unproven: `GridLevel.Elevation` (falls back to estimated levels) |
| Level Up / Level Down | fixed | The remembered level always won, so after the cut was moved with Section Nudge (or by hand) the next step started from where the plane used to be. Now the plane decides when one is on (`levels.pick_current`). | Proven |
| Camera Sync | fixed | (1) After the other window switched Camera Sync off and on, its count began again at 1 and this window stayed deaf until the count passed the old one: messages now carry `started`, and a new start is always heard. (2) A partner file was skipped when its time and size had not changed, which coarse file times can cause: files written in the last 2 s are always read. (3) A failed camera write lost the resting camera: it is retried. (4) Process lookups ran 8 times a second: once a second now. (5) The running Sync's stop is parked in an AppDomain slot (as Hide Tabs parks its tabs), so a start in an engine that lost the session holder cannot run two Syncs. | Proven: `CurrentViewpoint.Changed` debounced, `CreateCopy`, `CopyFrom`, DispatcherTimer, session holder (vptrackerlive). Unproven: `Viewpoint.GetCamera` / `TrySetCamera` (falls back to position + rotation), whether follow-moves fill the undo list |
| Coordinate Spotter | fixed | Called the banned `pick.point` in script.py and config.py and drove the banner itself. Now `namo.picking.point(prompt, want_item=True)` in the loop; picking shows and clears the banner, and the prompt carries the last reading ("Click point 4. Last: P3 X .. Y .. Z .."). The "Snapped to" column is gone (a measured point knows no snap kind, so it could only say Surface). Marker arm capped at 1 m (it grew with the model diagonal, which is meaningless when one stray object sits at the origin and the site 1,370,000 ft away). Esc with no new point is silent instead of reopening the table and the save prompt. | Proven (`pick.measure_point`, banner, overlay, `faces.candidates_at`) |
| Clear Spots | ok as built | | Proven |
| Sheet Overlay | fixed | `_pick_model_point` called `pick.point` twice with its own banner handling; the two reference points now come from one `namo.picking.points` run (two clicks on the Measure tool, as True Distance asks for its faces). `pick.Unavailable` handling removed. | Proven. Field check: frame rate with 30,000 overlay segments |
| Clear Sheet | ok as built | | Proven |

Also changed: `vp_common.choose_views` ticked rows by comparing whole row dicts rows x rows
times; it now goes by identity.

### Foundation requests

1. `namo/camera.py`: make `_write_camera(Api, viewpoint, cam)` public as
   `write_camera(viewpoint, cam)`. `vpexcel._edited_copy` has to write a camera onto an
   existing detached viewpoint in place (the vpspeeds route) and calls the private one today.
2. `namo/picking.py`, `point()`: an option to leave the banner up between the picks of a loop
   (Coordinate Spotter clears and re-shows it on every click, a visible flicker).
3. `namo/paths.py`, `_replace()`: up to about a second of `time.sleep` retries on the UI thread;
   Camera Sync writes while the user navigates and would rather fail fast (it retries on its own
   next tick). A `retries=` argument would do.
4. The five requests in section 3 above still stand (`camera.clip_state(viewpoint=)`,
   `camera.save_view(policy=)`, `KeepState` into `images`, the test fake, signed length fields).

### First three things to click

1. **Coordinate Spotter**: click three points on vertices and edges. The marker under the
   pointer is Navisworks' own Measure marker, and each cross with its label (P1, P2, P3) sits
   exactly on it. The banner along the bottom reads "Click point 2. Last: P1 X .. Y .. Z ..".
   Esc: a table with Point, X Y Z in model units, X Y Z in metres, Object, Model; the same on
   the clipboard; then Save as Excel / Save as CSV. Clear Spots removes the crosses.
2. **Level Sectioner, then Alt+PgUp / Alt+PgDn**: pick a level: the model is cut 1.2 m above
   it and what is below stays; one Ctrl+Z undoes it. Alt+PgUp steps to the next level with a
   toast naming it. Move the plane with Section Nudge past another level, press Alt+PgUp
   again: it steps from where the plane now is.
3. **Camera Sync** in two Navisworks windows: orbit in one, the other follows during the
   orbit, no ping-pong. Switch it off and on in the first window and orbit again: the second
   still follows. Then look at Edit, Undo in the following window and tell me whether it
   filled with view changes.

### Verify

`python dev/verify.py`, once at the end: check ok (140 bundles, 0 problems), pytest ok (1,592 passed, 18 skipped),
ipy compile ok, ipy test ok (1,587 passed, 0 failed, 35 skipped), ipy smoke ok (115 passed), parse ok, fresh ok, names ok.

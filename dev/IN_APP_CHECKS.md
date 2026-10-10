# Playground: the first session in Navisworks

Most of Playground has not run inside Navisworks yet: `status.yaml` at the repo root says
which tools have, and how it went. Everything was verified headlessly (see the root README). This is the order to test it in: load it, run the gate checks (the few
assumptions dozens of tools stand on), take the smoke tour, then work through each
group's full list in `dev\notes\`.

Use a saved federated NWF with at least two Revit NWCs (ideally one in millimetres and one
in feet), a few selection and search sets, saved viewpoints, two run clash tests (one with
result groups), grids with levels, and some hidden items. Keep
`%APPDATA%\pyNavis\logs\pyNavis.log` open; every Playground failure is logged there.

## 0. Load it

1. Close Navisworks. In `%APPDATA%\pyNavis\config.json`, add the root (keep anything else
   that is there):
   ```json
   "extensions": ["C:\\src\\pyNavis-playground"]
   ```
2. Start Navisworks and open the NWF. Expect five new tabs: Model, Views,
   Coordinate, Project, Dev. The log should show
   `Extension root 'this repo': 1 extension(s).`, `Ribbon built: ...` with no Playground
   errors, and `Panes configured: ...` (Issues and Source Files claim two free panel slots).
3. Dev > Team > **Environment Doctor**: a pass / warning / fail report of the whole
   setup. Anything red here comes first.
4. Light and dark: switch the Navisworks theme, click pyNavis Reload, glance at all five
   tabs. Icons should read in both.

To remove Playground: delete that entry and restart.

## 1. Gate checks (pyNavis Console, about 15 minutes)

Open the pyNavis Console and run this first, once:

```python
import sys; sys.path.append(r'Playground.extension\lib')
from namo import camera, items, paint, images, clashdata, ui, docdb
```

If any of these fails, stop and report it: many tools depend on each.

| # | Check | Expect |
|---|---|---|
| G1 | ViewCube **Front**, then `c = camera.capture(); c['direction'], c['up']`. Then **Top**. | Front about `(0, 1, 0)`, `(0, 0, 1)`. Top `(0, 0, -1)`, `(0, 1, 0)`. Wrong means the quaternion convention is flipped (every camera, BCF and viewpoint tool). |
| G2 | Orbit, `c = camera.capture()`, orbit away, `camera.apply(c)`. | The view comes back exactly. |
| G3 | `images.capture(r'C:\Temp\a.png', 1280, 720)`; then with three saved views: `with images.ViewKeeper(): [images.capture_saved(v, r'C:\Temp\%d.png' % i) for i, (_p, v) in enumerate(camera.saved_views()[:3])]` | Files open at that size; each shows ITS view, and your view is back afterwards. |
| G4 | On the grouped test `t = clashdata.tests()[0]`: `rows = clashdata.snapshot(t); len(rows)` | Equals Clash Detective's result count; names line up with `clashdata.results(t)`. |
| G5 | Select a few elements: `paint.apply([(items.selected(), 'E15759', None)])`, Ctrl+Z; then `paint.ghost(items.selected(), 0.85, 'BFBFBF')`, Ctrl+Z | Red, undone in one step; everything else grey and see-through while the selection keeps its colours, undone in one step. |
| G6 | `items.revit_ids(items.selected()[0])` on a nested family part (e.g. a pipe fitting's sub-solid) | The Element ID of the family INSTANCE, not its type. |
| G7 | `docdb.available(); docdb.kv_set('check', {'a': 1}); docdb.kv_get('check')` | `True`, then `{'a': 1}`. Save, reopen, `kv_get('check')` still returns it. (Issues and Clash Assigner can store data inside the NWF through this.) |
| G8 | Status Painter > Set status on two items, choose Issue; then again with Installed | Items turn red then green; Properties shows a Playground tab whose other properties survive; one Ctrl+Z per action. The second run must not refuse with "is a tab from the model". |
| G9 | `ui.form('Test', [{'kind': 'text', 'key': 'a', 'label': 'Name'}, {'kind': 'length', 'key': 'b', 'label': 'Offset'}])` | Typing works, Tab order is right, Enter = OK, Esc = Cancel, themed in dark and light. |
| G10 | `ui.table_window('Results', ['Name'], [{'cells': ['x'], 'value': 1}], modeless=True, key='t')`, then click in the model and type in the window's filter | Keystrokes reach the filter (modeless keyboard interop). |

Full foundation lists (30 Navisworks-core checks, 11 data-in-model checks):
`dev\notes\foundation-F3.md`, `dev\notes\foundation-F2.md`.

## 2. Smoke tour (one click per panel group)

| Tab > panel | Click | Expect |
|---|---|---|
| Model > Select | Select a duct, **Select Similar**, tick Category + Type | "Selected N similar items" |
| Model > Find | **Quick Find** (Ctrl+Alt+F), type a level name, Enter | Indexing progress first time, then select + zoom |
| Model > Inspect | **What Is It** (Ctrl+Alt+I) on an element | A card with ids, tree path, box, geometry |
| Model > Data | **Count by Property** on Element > Category | Table + bar chart; pick a group to select it |
| Model > Look | **Color by Property** on Element > Category | Colours, legend in the output window, one undo step |
| Views > Viewpoints | **Where Am I** | One popup: view, eye, bearing, level, grid, section |
| Views > Capture | **Viewpoints to Images**, three views, 1280x720 | A dated folder with images and index.html |
| Views > Navigate | **Level Sectioner**, pick a level; then Alt+PgUp | Section at the level + cut height; steps up a level |
| Coordinate > Clash Setup | **Clash Templates** > Save two tests | A template listed for Apply |
| Coordinate > Clash Results | **Clash Heatmap** on a run test | Elements coloured by clash count, top 20 table |
| Coordinate > Clash Reports | **Clash Excel** on two tests | Workbook opens in Excel with no repair prompt; thumbnails |
| Coordinate > Issues | Open the **Issues** pane, New from view | An issue with camera and snapshot; Go to restores it |
| Coordinate > BCF | **BCF Export** that issue, then **BCF Import** it into a copy | Topic, comment and viewpoint come back |
| Project > Models | Open the **Source Files** pane | Models listed; untick one hides it (one undo step) |
| Project > Quality | **Health Check** | Score cards per model |
| Project > 4D | **TimeLiner from Excel** > Write a template, then import it | Tasks created; one undo step |
| Project > Quantities | **Quick Takeoff** grouped by Category | Volumes match the Properties panel |
| Project > Field | **QR Tagger** on two elements | PNGs that scan on a phone; label sheet |
| Project > Exchange | **Geometry Exporter** to .glb | Opens upright and to scale in Windows 3D Viewer |
| Dev > Automate | **Command Palette** (Ctrl+Shift+P), type "what is", Enter | Runs What Is It after the palette closes |
| Dev > Reports | **Report Templates**, New on Health Check, Run | A file without any dialog |
| Dev > Tools | **Unit Converter**, type `12' 6" to mm` | 3810 mm, live |

## 3. Full lists, by group

Each file starts with what every tool does, then ordered in-app steps (the riskiest
marked UNVERIFIED), then requests the build agent made of shared modules.

| Group | File | Tools |
|---|---|---|
| Select & Find | `dev\notes\select_find.md` | 21 buttons |
| Inspect & Data | `dev\notes\inspect_data.md` | 16 |
| Look | `dev\notes\look.md` | 11 |
| Views | `dev\notes\views.md` | 16 |
| Clash Setup & Results | `dev\notes\clash_setup_results.md` (+ pyRevit companion) | 10 |
| Clash Reports | `dev\notes\clash_reports.md` | 7 |
| Issues & BCF | `dev\notes\issues_bcf.md` | 14 |
| Models, Quality, Publish | `dev\notes\models_quality.md` | 13 |
| 4D, Quantities, Field | `dev\notes\fourd_qty_field.md` | 14 |
| Exchange & Reports | `dev\notes\exchange_reports.md` | 4 |
| Dev & Team | `dev\notes\dev_team.md` | 14 |

Corrections made after the group notes were written (reviews):
* Status Rules applies in ONE undo step across tests (`clash_setup_results.md` step 8
  still says one per test).
* `LcOclClashUtils.CountByStatus` has a 3-argument `recurse` overload in the 2026 API; the
  clash tools use it (`clash_reports.md` request 1 is resolved).
* Per-Trade Reports, Clash to Issues and BCF Export (clash topics) all read the "who moves"
  order from Clash Assigner (`clashassign.saved_settings()`), so they cannot disagree;
  Clash to Issues' Shift+Click shows that order instead of its own list.
* Issue Pins also clear when a model closes (`doc-closed` is registered).
* Issue status filters: an exact status (Open, Closed) now means only that status.
* Hook handlers receive a plain dict: pyNavis passes `__event__` as a .NET Dictionary
  (no `.get` under IronPython), which had silently broken Record Macro and Usage
  Analytics; `namo.hooks.dispatch` now converts it once for every handler.
* Team Sync's startup pull: only a read-only probe runs on a worker thread; the pull itself
  and its toast run on the UI thread once pyNavis is idle (`dev_team.md` still describes
  the old worker-thread pull; in-app step 14 still applies).

## 4. The riskiest unverified behaviours (what to watch for)

1. Native Navisworks ribbon commands run from code (Command Palette, macro steps, native
   hotkeys): `namo.ribbon` executes AdWindows command handlers after CanExecute.
2. Text values read back from saved search sets may carry a `DisplayString:` prefix
   (pynavis `sets._variant_to_python`); Playground strips it (`namo.find_query.stored_value`),
   and the same suspicion is logged for pyNavis' own Excel Sets in `docs\pending.md`.
3. Whether `Document.GenerateImage` sees a just-recalled saved view (Viewpoints to Images,
   Batch Images, Batch PDF, 4D Movie Maker frames inside a transaction).
4. Selection-source references on new clash tests (Clash Matrix: tests should follow sets).
5. Writing custom property tabs through COM as ONE undo step (Status Painter, Number
   Picked, Bulk Property Writer, Progress Painter, QR Tagger).
6. Point-cloud clash results through the API (Scan vs Model).
7. Units of property values read as numbers (assumed SI: Quick Takeoff, Explorer).
8. Transform Fixer's offset units and rotation direction (it self-corrects and says so).
9. The Windows Task Scheduler XML accepted by schtasks, and SMTP over TLS from
   IronPython (Scheduled Reports).
10. Viewpoint exchange XML accepted by Navisworks' own Import Viewpoints (Export
    Viewpoints, Viewpoint Sync).

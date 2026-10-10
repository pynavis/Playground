# G10 exchange_reports: Exchange panel (Project) and Reports panel (Dev)

Everything below is verified headlessly only: pure halves unit tested on CPython 3.11 and
IronPython 3.4 (the four mesh writers and the IFC writer produce byte-identical files on
both engines, checked by golden digests), the API halves driven through fake Navisworks
objects, every window built from real WPF in the IronPython harness, and the real pyNavis
BundleParser shows both panels in the specified order. Nothing has run inside Navisworks,
no scheduled task was ever created and no mail was ever sent.

External checks run during development (packages installed only into my scratch folder,
not into the dev Python, so the matching tests skip in `verify.py`):

* ifcopenshell 0.9.0 opens the IFC, `ifcopenshell.validate` with `express_rules=True`
  reports zero issues, its unit scale reads 0.3048 for a feet document, psets and storey
  containment come back, and its geometry kernel places a door at the expected world
  height.
* pygltflib 1.16.5 loads the .glb and agrees on meshes, materials, nodes and accessor
  min/max.
* ezdxf 1.4.4 (installed in the dev Python, so this one runs in verify) reads the DXF as
  AC1009 with every 3DFACE, layer and true colour, and its audit finds no errors.
* A loopback SMTP responder on 127.0.0.1 receives a real smtplib exchange (EHLO, MAIL,
  RCPT, DATA with attachment, QUIT) on BOTH engines; DPAPI protect/unprotect round-trips
  under IronPython.

## 1. Tools

Exchange panel (Geometry_Exporter, IFC_Exporter)

- **Geometry Exporter** (#72): the selected objects' own triangles (`namo.mesh.item_triangles`, budget per object and in total, counted progress with Cancel, skipped objects listed in the output window with links) to glTF binary (.glb: a node per model and a node and mesh per object, metres, Y up, PBR materials from the item colours converted to linear light, uint16/uint32 indices, POSITION min/max, extras with category, model, Revit/IFC ids and chosen properties), OBJ + MTL (a group per object, a material per colour, Y up by default), binary STL (facet normals) or DXF (R12 structure, 3DFACE, a layer per model or category, nearest ACI plus true colour 420). Optional local origin (whole metres or feet) with the offset written to `<file> - offset.txt`; units choice for OBJ/STL/DXF.
- **IFC Exporter** (#71): the selection as IFC4 (Reference View flavoured): IfcProject with the document's units, IfcSite, IfcBuilding, an IfcBuildingStorey per level (Level property, else Navisworks' grid level under the object, or one storey), classes from Revit/IFC categories (Walls IfcWall, Floors IfcSlab, Ducts IfcDuctSegment, Pipes IfcPipeSegment, Structural Framing IfcBeam, Columns IfcColumn, Doors IfcDoor, Windows IfcWindow, Cable Trays IfcCableCarrierSegment and 30 more, else IfcBuildingElementProxy), IfcTriangulatedFaceSet bodies placed relative to their storey, colours and transparency through shared IfcSurfaceStyles, GlobalIds from the model (IFC GlobalId, Revit export GUID from UniqueId, InstanceGuid, else stable derived), property sets per Navisworks tab (IfcLabel/IfcText/IfcReal/IfcInteger/IfcBoolean, identical sets written once), IfcRelAggregates, IfcRelContainedInSpatialStructure, IfcRelDefinesByProperties. Shift+Click: team-shared "Category = IfcClass[.TYPE]" rules.

Reports panel (Report_Templates, Scheduled_Reports)

- **Report Templates** (#69): every saved template of every report in `namo.reports.REGISTRY` in one table (report, template, the report's own one-line description, updated, by); reports not built yet show "Not built yet" and cannot be run or given new templates. New (a form generated from `default_config()`: folder, name template, fixed path, booleans, numbers, text, lists and objects as validated JSON), Run (one or several, without dialogs, `interactive=False`, progress, toast, opens the file or its folder), Edit (rename included), Duplicate, Delete, Export (one report: the namo.templates file; several: a bundle) and Import (either kind).
- **Scheduled Reports** (#70): Windows scheduled tasks in the Task Scheduler folder `\Playground\` (current user, only while signed in, no admin, no stored Windows password) that run `%APPDATA%\pyNavis\cli\pynavis.exe run <bundle>\scheduled_runner.py "<model>" --timeout N --results <log> -- --schedule "<name>" --templates "<id>:<name>;..." [--mail <profile>] [--folder ...] [--copy-to ...] [--no-attach]` daily or weekly at a time. The runner (checks `__runner__`, never opens a dialog) runs the templates, writes a run log (.txt + .json, last 60 kept), copies results to a share, and mails them through a profile (SMTP server, port, STARTTLS/SSL/none, from, to; password DPAPI CurrentUser in `%APPDATA%\pyNavis\playground\schedules\mail.json`). The window lists schedules with next run, last run and last result, and offers New, Edit, Run now, On or off, Delete, Logs and Mail settings (New, Edit, Delete, Send test). A missing pynavis.exe is explained in the status line and on every action that needs it.

Modules: `meshexport.py` (pure writers + `read_objects`), `ifc.py` (pure IFC4 STEP writer + reader), `ifcexport.py` (class mapping, storeys, psets, ids, model assembly), `reportrunner.py` (catalog, generated forms, `run_templates` shared by the ribbon and the scheduler, window), `schedule.py` (command lines, task XML, schtasks, records, logs, the runner side), `sched_mail.py` (profiles, DPAPI, message, smtplib with .NET SmtpClient fallback, password dialog), `sched_ui.py` (Scheduled Reports windows), `xchg_common.py` (paths, names, skipped list).

Design decisions worth knowing:

- Tasks are registered from XML (`schtasks /Create /TN \Playground\<name> /XML <file> /F`, UTF-16 like Task Scheduler's own exports), not `/SC ... /TR ...`: a `/TR` command is limited to 261 characters (runner path + model on a share + template names pass it easily) and only XML can set "run a missed start as soon as possible", "keep running on battery" and "never two at once". The first start is the next future occurrence, so registering never counts as a missed run.
- pynavis.exe is a console program: a console window shows during a scheduled run; closing it stops the run.
- Mail: smtplib first (works under IronPython; plain SMTP proven over loopback); 'Automatic' falls back to System.Net.Mail.SmtpClient only when smtplib fails before handing over the message (connect, TLS, sign-in), so nothing is sent twice. SmtpClient cannot do implicit TLS (port 465), so SSL profiles always use smtplib. Attachments up to 15 MB in total; the rest are listed by path.
- Each object is welded as soon as its triangles are read, so a 2 million triangle export holds shared vertices, not raw triangle tuples. Defaults: glTF/OBJ/STL/DXF 200,000 triangles per object and 2,000,000 in total; IFC 100,000 and 1,000,000.
- glTF vertices are stored relative to each object's centre (node translation) so float32 keeps full precision far from the origin even without the local-origin option.

## 2. In-app checks (please click through in this order)

Use a saved federated NWF of Revit NWCs (one in millimetres or metres, one in feet if you have it) and keep `%APPDATA%\pyNavis\logs\pyNavis.log` open; search it for `Playground:` after each step.

Geometry Exporter
1. Select a wall, a duct run and a door. Click Geometry Exporter: the form opens on glTF, and "Properties in glTF extras" lists names like "Element > Category". Tick two, keep "Move to a local origin", Export. Expect the toast "Exported 3 objects, N triangles" with the path, and `<name> - offset.txt` beside the file.
2. Open the .glb in Windows 3D Viewer, Blender (File > Import > glTF 2.0) or gltf.report: the objects stand upright (Y up), a 3 m wall measures 3 units, colours match Navisworks, transparent glass is see-through, and each object node's custom properties show category, model, ids and the two properties. Please report whether the colours are right: they come from `ModelGeometry.ActiveColor` through `namo.paint.read_color`, which is unverified (older notes found overrides unreadable). Objects whose colour cannot be read come out light grey BFBFBF.
3. Export the same selection as DXF with the local origin OFF and "DXF layers: By category". Open it in AutoCAD or DWG TrueView: 3D faces on layers named after the categories, and the Properties palette shows the exact RGB (true colour). Then Append the DXF into the same NWF in Navisworks: it must sit exactly on the source objects (this proves world coordinates and units). Repeat with STL in document units (Navisworks appends .stl).
4. Export OBJ (Y up ticked) and import it into Blender with default settings: upright, materials named `mat_RRGGBB`.
5. Select a whole large model: counted progress per object; Cancel stops with no toast. Lower "Triangles per object" to 100: the output window lists skipped objects ("Too big: 2,304 triangles, over the 100 left per object"); clicking a name selects it in Navisworks.
6. Please note how long a 500,000 triangle glTF export takes (the writers are Python loops on IronPython).

IFC Exporter
7. Select walls, floors, doors, ducts, pipes, cable trays and some generic models; export with "Level property, then grid levels" and "Every property tab except Navisworks bookkeeping". Open the IFC in a viewer (BIMcollab ZOOM, Solibri Anywhere, usBIM.viewer+, or Navisworks Append): IfcWall/IfcSlab/IfcDoor/IfcDuctSegment/IfcPipeSegment/IfcCableCarrierSegment, generic models as IfcBuildingElementProxy, storeys named after the Revit levels with their elevations, colours, and property sets named Element, Revit Type and so on.
8. If you have an IFC exported from Revit for the same model, compare a wall's GlobalId: Playground takes the IfcGUID property when the NWC has one, else derives Revit's export GUID from the UniqueId (the revit-ifc rule).
9. Append the IFC back into the NWF: it must overlay the source objects, in a millimetre document and in a feet document (units come from `doc.Units`).
10. In a model whose objects carry no Level property, turn grids on and export with "Grid levels only": each object lands on the level under it. Please report whether the storey elevations in the IFC match Navisworks' grid levels (`GridLevel.Elevation` is taken as absolute model Z, unverified; the level per object comes from `GridSystem.ClosestIntersection(point).Level`, the call pyNavis' clash snapshot uses).
11. Shift+Click IFC Exporter: add `Generic Models = IfcFurniture`, tick "List the built-in classes", Save: a toast and an output table. Export again: the generic models are IfcFurniture. A bad line (`Walls = IfcSpaceship`) is refused in the form.

Report Templates
12. Save a template or two from Health Check, Preflight, Stale File Alert or Count by Property first (those tools' own template saving). Click Report Templates: one row per template; templates of reports that are not built yet show "Not built yet".
13. New, pick Stale File Alert (or any built report): the form shows the folder, name template and the report's own settings; Save. Select it and Run: a progress window, then a toast naming the file, and the file opens. Run two at once: one toast ("Ran 2 templates") and Explorer opens on the first file.
14. Select two templates of different reports, Export to a .json, Delete both (confirm), Import the file: both come back. Edit one, rename it, Save; Duplicate it.

Scheduled Reports
15. Click Scheduled Reports. With pynavis.exe in place the status line counts schedules; rename `%APPDATA%\pyNavis\cli` briefly to see the "pynavis.exe was not found" line and the error toast on New (then rename it back).
16. Mail settings > New: a real profile (Office 365: smtp.office365.com, 587, STARTTLS; Gmail: smtp.gmail.com, 587, STARTTLS with an app password). The password is asked in its own dialog (dots, not text). Send test: please report the toast's last line, "Sent with Python smtplib" or "Sent with .NET SmtpClient". If it says .NET, smtplib's TLS failed under IronPython and the fallback did its job: please copy the `scheduled report mail` or smtplib line from the log. Also try an SSL profile on port 465 if your server offers one (smtplib only).
17. New schedule: the saved NWF, two templates, Weekly, today, a time three minutes ahead, the mail profile, "Also copy them to" a test folder. Save: toast "Scheduled ...". Open Windows Task Scheduler > Task Scheduler Library > Playground: the task exists, General says "Run only when user is logged on", Conditions has "Start the task only if the computer is on AC power" unticked, Settings has "Run task as soon as possible after a scheduled start is missed" ticked. Please report if creating the Playground folder was refused ("Access is denied") for a standard user.
18. At the time (or with Run now and confirm): a console window shows the pynavis run output, a hidden Navisworks opens the model, and afterwards the list shows Last result "2 of 2 succeeded"; Logs opens the folder with one .txt and .json per run plus last-results.json; the test folder holds copies; the mail arrives with the files attached.
19. Let a schedule fire with Navisworks closed (it must not need a running Navisworks), and once with Navisworks open (a second instance takes a licence seat while it runs).
20. Edit the schedule and rename it: Task Scheduler shows only the new name. On or off: the task's status follows. Delete: the task disappears.

## 3. Requests for shared modules (not edited; worked around locally)

1. `namo.ui`: a `password` field kind for `ui.form` (a PasswordBox in the DesignSystem InputField frame, value read from `.Password`). Mail profiles ask for the password in a separate small dialog (`sched_mail.build_password_window`) because a text field would show it.
2. `namo.templates`: a public read of stored entries, e.g. `Templates.entries(names=None) -> {name: {'config', 'updated', 'user'}}`. Report Templates' multi-report export calls the private `templates._entries` and `templates._find` to build its bundle.
3. `namo.ui` `multi` fields: per-option disabled state (`'disabled': [values]`), so the schedule form could show templates of unbuilt reports greyed out; today they are left out of that list and Report Templates explains them.
4. Dev environment: install `ifcopenshell` and `pygltflib` into the dev Python so the cross-check tests in `test_ifc.py` and `test_meshexport.py` run inside `verify.py` instead of skipping (both pass when the packages are importable).

## 4. Honest limits

- IFC: no type objects (IfcWallType...), materials (IfcMaterial), openings or georeferencing (IfcMapConversion); every body is a tessellation; doors and windows leave OverallHeight/OverallWidth empty; property values are IfcLabel/IfcText/IfcReal/IfcInteger/IfcBoolean only (no measures with units).
- glTF: no normals (viewers compute flat ones, as the spec requires), no textures, no instancing. STL carries no colour. DXF follows R12 structure, which has no units variable: the units are in the 999 comments and the offset note.
- Report Templates edits top-level config keys; nested values are edited as JSON text.
- Scheduled runs show a console window, need the user signed in to Windows, and use a Navisworks licence while they run.

## Refit pass

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Geometry Exporter | fixed | An export that skipped objects toasted the skip count and lost the path; the detail now always ends with the full path and the file is shown in Explorer. Under `pynavis run` it raised from the form; it now toasts "cannot run under pynavis run" and stops | Proven triangles (`pynavis.geometry.world_triangles`, per-object float noise for welding, no fixed epsilon). Unproven: colours (`ModelGeometry.ActiveColor` / `ActiveTransparency`), guarded: grey BFBFBF when unreadable |
| IFC Exporter (+ Shift+Click) | fixed | Same path and Explorer fix, same runner guard (script and config) | As above, plus unproven `GridLevel.Elevation` as absolute Z (only labels the storey; placement does not depend on it). `GridSystem.ClosestIntersection` is proven (pynavis.clash uses it) |
| Report Templates | fixed | Run opened the progress window on top of the modal list. pyNavis' progress window disables only the Navisworks main window and switches it back ON when it closes, so the list stayed clickable during a run (Run twice, Delete mid-run) and afterwards Navisworks itself was live under a modal window. Run now closes the list first, then runs (as Clash Grouper closes its dialog before it writes), toasts where the files are, and opens the file (one) or shows it in Explorer (several). Runner guard added | Proven |
| Scheduled Reports | fixed | (1) Only the existence of pynavis.exe was checked. A pyNavis without the runner (1.2.0 as released) also ships pynavis.exe, so a schedule would be created and then fail every run with exit code 2. The window now asks `pynavis.exe run --help` once (exit 0 only when `run` exists; it returns before anything is looked up, so Navisworks is never started), says so in the status line, and New, Edit, Run now and `register` refuse with a sentence. (2) The task's user came from USERDOMAIN/USERNAME; it now comes from `WindowsIdentity.GetCurrent().Name` (environment as fallback). (3) Send test froze the window silently for up to a minute; it now shows the wait cursor. (4) Runner guard on the button | Unproven end to end: no shipped tool uses Task Scheduler, smtplib or `pynavis run` from a task. Checked here: argv quoting round-trips (list2cmdline rules), the command line against `RunArgs.Parse` (everything after `--` reaches `__args__`; `sys.exit(1)` makes the run "failed", exit code 1), Popen with CREATE_NO_WINDOW under IronPython 3.4 (a real, read-only `schtasks /Query` of a missing task returned its error text), UTF-16 XML with BOM. Authoring only ever runs `schtasks /Query, /Create, /Change, /Delete` and `run --help`; Navisworks starts only from Run now (after a confirm) or from the task itself |

Regression tests: `test_schedule.py` (runner_state, register refusing an old exe),
`test_reportrunner.py` (run_closed, files_text), `test_sched_ui.py` (where_text, under_runner).

Foundation requests
* `namo.progress.run` (or `ui.show_modal`): refuse or adapt when a modal Playground window
  is open. Any table-window action that starts a progress window has the Report Templates
  problem above. Worth a grep across groups for `progress.run` inside `ui.build_table` actions.
* The older requests in section 3 still stand (password field kind, public
  `Templates.entries`, disabled options in `multi`).

First three clicks
1. Report Templates: New, pick Clash Count Matrix (or any built report), Save, select it,
   Run. The list closes, a progress window runs, one toast names the file and the file opens.
2. Geometry Exporter on three selected objects, glTF: toast "Exported 3 objects, N
   triangles" with the path, Explorer opens with the .glb selected, the offset note beside it.
3. Scheduled Reports: read the status line. On a pyNavis without the runner it must read
   'This pyNavis has no "pynavis run" command'; with the runner it counts the schedules and
   New opens the form. Nothing may start Navisworks until Run now is confirmed.

Verify (full run, 2026-10-05): check ok, pytest ok, ipy compile ok, ipy test ok, ipy smoke
ok, parse ok, fresh ok, names ok.

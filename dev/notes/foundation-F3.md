# Foundation F3: Navisworks core (items, clashdata, camera, images, colors, paint, mesh, ui)

Verified headlessly only: pure halves unit tested on CPython and IronPython 3.4, API
halves driven through a fake Navisworks layer (names and shapes from dev/api, in
dev/tests/test_items.py), WPF windows built, laid out off screen and rendered to PNG in
light and dark under the IronPython harness. Nothing here has run inside Navisworks yet.

## 1. What each module does

* `items`: walk/collect/identify model items (geometry items, element-level objects,
  stable keys, Revit ids, property samples and tallies, boxes), select/zoom/hide, and
  `complement` (everything except some items, touching none of their ancestors).
* `clashdata`: clash snapshots (pynavis' snapshot plus guid, distance, dates,
  description, comments, trades, group guid, pair key), groups, run-to-run `compare`,
  history in namo.store, per-result edits, clash images and viewpoints.
* `camera`: Rotation3D maths (convention documented), capture/apply/look-at/zoom,
  BCF camera conversion, saved viewpoints in folders, section state, horizontal
  sections, section box.
* `images`: GenerateImage / TestsImageForResult to PNG/JPEG/BMP, thumbnails, ViewKeeper
  for batch exports.
* `colors`: palette, ramps, status colours, contrast, hex parsing (pure).
* `paint`: permanent colour/transparency overrides in one undo step, ghost everything
  else, reset, temporary previews, remembered scheme, best-effort colour read-back.
* `mesh`: area, volume, centroid, closure, welding of triangle lists, and the item
  triangle source.
* `ui`: themed form / chooser / table windows, a reusable virtualised Table, parts for
  custom windows, modeless and non-activating windows, timers and debouncing.

## 2. In-app checks (please click through these; each says what to look for)

Run the snippets from the pyNavis Console (or a scratch bundle) with a Revit-based
federated model open. `from namo import camera, items, paint, images, clashdata, ui`.

Camera (the most important one: the quaternion convention)
1. Click the ViewCube **Front** face, then run `c = camera.capture(); c['direction'], c['up']`.
   Expect about `(0, 1, 0)` and `(0, 0, 1)`. Click **Top**: expect `(0, 0, -1)` and `(0, 1, 0)`.
   If either is wrong, stop and report it: camera.quat_to_axes needs flipping.
2. `camera.look_at((x, y - 30, z + 1.5), (x, y, z + 1.5))` with x, y, z near the model:
   the view should look north, level, from 30 units south. Undo history: note whether
   the camera move appears as an undo step.
3. Orbit somewhere, `c = camera.capture()`, orbit away, `camera.apply(c)`: the view must
   come back exactly (position, roll, lens).
4. Switch to **Orthographic**, `camera.capture()['height_field']`: compare with the
   visible height of the view in model units (UNVERIFIED that HeightField is a height in
   ortho). Then `camera.apply(camera.make_cam(c['position'], direction=c['direction'],
   up=c['up'], projection='persp'))` should return to a sane 60 degree perspective.
5. `camera.zoom_to(items.selected(), margin=0.1)` frames the selection without changing it.
6. `camera.save_view('Check', 'Playground/Test', comments='hello')` twice: two views
   `Check` and `Check (2)` inside folders Playground > Test, each with the comment; one
   Ctrl+Z removes the last one (folder creation and save are one step).
7. `camera.horizontal_section(z)` with z mid-storey (model units): Sectioning tab shows
   plane 1 on, cutting at z, keeping what is BELOW; `camera.horizontal_section(z, z - 3)`
   adds plane 2 keeping what is above it. One Ctrl+Z removes the section change.
8. `s = camera.clip_state()`, change the section, `camera.set_clip_state(s)`: restored.
   Then try `t = camera.clip_json()` / `camera.set_clip_json(t)` and report whether it
   restores and whether it is undoable (UNVERIFIED).
9. `camera.saved_views()` lists every view with its folder path; animations are skipped.

Images
10. `images.capture(r'C:\Temp\a.png', 1280, 720)` and `.jpg` with `quality=40`: both
    files open, at that size; the JPEG is visibly lower quality.
11. With three saved views: `with images.ViewKeeper(): [images.capture_saved(v,
    r'C:\Temp\%d.png' % i) for i, (_p, v) in enumerate(camera.saved_views()[:3])]`.
    Each file must show ITS view (not the previous one; UNVERIFIED that the recall is
    applied before rendering), and afterwards the camera and current saved view are as
    before.
12. `images.clash(clashdata.results(t)[0], r'C:\Temp\c.png')` shows the clash with its
    highlight colours.

Clash data
13. On a test with result groups: `rows = clashdata.snapshot(t)`; `len(rows)` equals
    the result count shown by Clash Detective; `rows[i]['name']` matches
    `clashdata.results(t)[i].DisplayName`; `group` and `group_guid` set for grouped ones.
14. Report `rows[0]['model_a']` and also `pynavis.clash.snapshot_results(t)[0]['model_a']`:
    if pynavis' own is `''`, ModelItem.HasModel is root-only as suspected and namo's fill
    is doing the work.
15. `created`, `approved_by`, `description`, `priority`, `comments` match the Clash
    Detective columns; `trade_a`/`trade_b` look right for your file names.
16. `clashdata.set_assigned([r], 'Your Name')`, `set_description`, `set_priority([r], 2)`,
    `add_comment(r, 'test')`: visible in Clash Detective; each is one undo step; the
    comment shows the author (Navisworks 2026 takes the author as text; on 2027 the
    code falls back to the two-argument comment).
17. `clashdata.resolve_guid(t, rows[5]['guid'])` returns that result quickly (Guid index).
18. Run the test again, snapshot again, `clashdata.compare(old, new)`: unchanged clashes
    land in `persisting` (this proves pair_key is stable: InstanceGuid UNVERIFIED across
    re-runs and re-appended models).

Paint and items
19. `paint.apply([(items.selected(), 'E15759', None)])` colours the selection red; one
    Ctrl+Z undoes it.
20. Select a few elements, colour them, then `paint.ghost(items.selected(), 0.85, 'BFBFBF')`:
    everything else grey and see-through, the selection keeps its colour; one Ctrl+Z
    undoes the ghost only. Time it on the biggest model you have.
21. `paint.read_color(item)` after an override: report whether it returns the override
    colour or the original (UNVERIFIED; older notes say overrides are unreadable).
22. `items.revit_ids(item)` on a Revit element: element id and unique id match the
    Properties panel; note which property names worked (REVIT_PROPERTIES order) and
    whether `ifc_guid` came from the model or was derived.
23. `items.model_name(item)`, `items.tree_path(item)`, `items.key(item)` read sensibly;
    `items.resolve(items.entries(sel))` gives the same items back.
24. `items.objects(items.roots(), budget=50000)` on a big model: time it; `.sampled`.
25. `mesh.item_triangles(duct)`: `mesh.summary(r['tris'], r['noise'] * 4)`: closed True
    for a Revit duct segment, volume plausible against Revit.

UI (both themes: switch pyNavis theme to dark and light)
26. `ui.form('Test', [...every kind...])` (copy ALL_FIELDS from dev/tests/smoke_ui.py):
    typing works in every box, Tab order top to bottom, Enter = OK, Esc = Cancel, errors
    appear in red under fields, Browse/Pick/Today buttons work, the ComboBox dropdown is
    themed (no light gradient in dark), checkboxes and radios show the accent when on.
27. `ui.choose('Pick', rows, ['Name', 'Count'])` with 5,000 rows: filter typing stays
    responsive, Space ticks, Select all ticks only the filtered rows, clicking the Count
    header sorts numerically.
28. `ui.table_window('Results', [...], rows, modeless=True, key='t')`: typing in its
    filter works while Navisworks has focus elsewhere (keyboard interop), calling it
    again updates the same window, action buttons work after the script ended, closing
    and reopening works.
29. `w = ui.window('Note', 300); ui.non_activating(w); w.Show()`: appears without
    taking focus from the model view.
30. Under `pynavis run`, `ui.form(...)` raises "Dialogs are not available under pynavis
    run..." instead of hanging.

## 3. Requests and notes for the lead

* No changes needed in modules I do not own. clashdata uses `namo.trades`,
  `namo.config` and `namo.store` (F2) lazily and degrades to 'Unassigned' trades if they
  fail; items uses `namo.ifcguid.from_revit_unique_id` when present.
* `dev/tests/test_items.py` carries a fake Navisworks layer (`FakeNav`, `model_tree()`,
  fake clash classes). Tool agents can reuse it in their own tests with
  `import test_items as nav` to drive their API halves headlessly.
* Contract deviations: `images.STYLES` holds enum member NAMES (resolved by
  `style_enum`) so the module imports outside Navisworks; `ui.choose` in single mode
  returns a one-item list, as the contract's "[row values]" says; `ui.table_window`
  returns the Window, refresh through `window.Tag.update(...)`.
* README-F3.md is ready to merge into lib/namo/README.md.

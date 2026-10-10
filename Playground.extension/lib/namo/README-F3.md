# namo, F3 Navisworks core: items, clashdata, camera, images, colors, paint, mesh, ui

Eight modules that touch the live Navisworks API (or WPF). Each one has a pure half
(plain tuples, dicts, strings; unit tested under CPython and IronPython 3.4) and an API
half that lazy-imports `pynavis._api` / `pynavis.clash` inside the functions, so
`import namo.<module>` always works, in tests and in a script that runs before a model
is open. Every API function takes `doc=None` meaning the active document.

Conventions shared by all eight:

* Colours are `'RRGGBB'` text, upper case, no `#` (input also accepts `#RRGGBB`, `RGB`,
  lower case). Transparency is 0.0 (opaque) to 1.0 (invisible).
* Points and vectors are `(x, y, z)` float tuples in MODEL units (`doc.Units`), boxes
  are `((xmin, ymin, zmin), (xmax, ymax, zmax))`. Anything in metres says `_m`.
* Every document edit is ONE undo step (`pynavis.viewpoints.transaction`, or one
  `CurrentViewpoint.CopyFrom` of an edited copy for camera/section changes).
* One `Cancelled` exception for every namo walk: `namo.items.Cancelled` (also exported
  as `namo.clashdata.Cancelled`). Tick callbacks cancel by returning exactly `False`
  (`== False`, so `None` from a side-effect callback carries on).
* Nothing here prints, toasts or opens a window unless that is the function's job
  (`ui.form`, `ui.choose`, `ui.table_window`). Tools report outcomes themselves.

Items marked **UNVERIFIED** are API behaviours inferred from the dump and pyNavis
sources that no one has clicked yet; `dev/notes/foundation-F3.md` lists the in-app
checks.

---------------------------------------------------------------------------------------

## items: walking, identifying, measuring and showing model items

The vocabulary every tool uses for "things in the model". A *geometry item* has
`HasGeometry`; an *object* is `FindFirstObjectAncestor()` of a geometry item (what a
user calls an element) and falls back to the item; a *key* is
`'<source file basename lower>|<PathId>'`, stable across sessions while the model
keeps its source files. Long walks return an `ItemList` (a plain list with a
`sampled` attribute, True when a `budget` cut it short: the tool must then say
"sampled").

| Function | Returns, behaviour |
|---|---|
| `Cancelled` | Exception raised when a `tick` returns False. |
| `ItemList` | list subclass; `.sampled` bool. |
| `selected(doc=None)` | `[ModelItem]` snapshot of the current selection. |
| `roots(doc=None)` | `[ModelItem]` root item of each model, model order. |
| `walk(roots, max_depth=None)` | generator of `(item, depth)`, depth first, children in order (Python recursion over `.Children`: fine for a branch, slow for a federation). |
| `geometry_items(roots, tick=None, budget=None)` | `ItemList` of items with geometry under roots (native `DescendantsAndSelf`). `tick(done, None)` every 500 items walked. Overlapping roots yield each item once. |
| `objects(roots_or_items, tick=None, budget=None)` | `ItemList` of distinct objects of the geometry items, first-seen order; `budget` caps the objects. |
| `object_of(item)` | the element-level item (object ancestor, else the item). |
| `visible(item)` | False when the item or ANY ancestor is hidden (`IsHidden` is the own flag only). |
| `key(item, doc=None)` / `keys(items, doc=None)` | stable key text (see above); `keys` reads model names once. |
| `entries(items, doc=None)` | JSON-safe `[{'m','i','p'}]` (pynavis.memory schema): survives appended or reordered models. |
| `resolve(entries, doc=None)` | `(found_items, missing_count)`. |
| `model_of(item)` / `model_name(item)` | the `Model` (climbing to the model root) / its source file basename or `''`. |
| `models(doc=None)` | `[{'index','model','name','file','source','units','root'}]`; `name` is the source basename. |
| `tree_path(item, sep=' > ')` | `'file.nwc > Level 1 > Walls > Basic Wall'` (blank names show the class name). |
| `bbox(items_or_item)` | world box (union, empty boxes skipped) or None; a `ModelItemCollection` is measured natively. |
| `center(item)` / `size(item)` | box centre / `(dx, dy, dz)`, or None. |
| `revit_ids(item)` | `{'element_id','unique_id','ifc_guid','category','family','type','ifc_guid_derived'}` text or None, tried in `REVIT_PROPERTIES` order on the item then its object. With no IFC GUID but a UniqueId, `ifc_guid` is derived (`namo.ifcguid.from_revit_unique_id`) and `ifc_guid_derived` is True. |
| `category(item)` | Revit/IFC category (`Element > Category`) of the item or its object, else `ClassDisplayName`. |
| `prop(item, category, prop_name, fallback_to_object=True)` | coerced value (pynavis.props: str/int/float/bool/datetime/tuple) by DISPLAY names, or None. |
| `sample_properties(items, limit=200)` | `[(category, property, count)]` of property NAMES on the first `limit` items, sorted. Names only, fast. |
| `distinct_values(items, category_name, prop_name, tick=None, fallback_to_object=False)` | `[(value_text, count)]` most common first; missing reads `NO_VALUE` (`'(no value)'`). |
| `collection(items)` | `ModelItemCollection` (passes one through). |
| `select(items, zoom=False, doc=None)` | replaces the selection, optional COM zoom to it; returns the count. |
| `zoom(items, doc=None, margin=0.0)` | frames items without touching the selection (`camera.zoom_to`). |
| `isolate(items, doc=None)` / `hide(items, hidden=True, doc=None)` / `unhide_all(doc=None)` | one undo step each; `isolate` of nothing is a no-op. |
| `complement(keep, doc=None)` | the FEWEST items covering the whole model except `keep` and what is under it (what `paint.ghost` overrides; also an "invert" that never touches a kept item's ancestors). |
| `as_list(x)` | list from a ModelItem, a collection, None or any iterable. |

Pure helpers (tested): `Ticker(tick, total=None, every=500)` with `.step()`/`.finish()`,
`walk_tree(roots, children_of, max_depth)`, `dedupe(values, key)`, `union_boxes`,
`box_center`, `box_size`, `value_text(value)`, `tally(texts)` (most common first, ties
by text), `key_text(source, path_id)`, `join_path`, `ancestor_closure(keep,
parent_of)`, `frontier(roots, children_of, keep, ancestors)`.

Traps: `ModelItem.HasModel`/`.Model` are documented for the model ROOT item, so
`model_of` climbs; never call `item.Model` on an element. ModelItems are used in Python
sets (IronPython hashes them through .NET `GetHashCode`/`Equals`, which ModelItem
overrides). Revit property names are a best guess list (`REVIT_PROPERTIES`); a model
exported with other settings may use other names.

---------------------------------------------------------------------------------------

## clashdata: one reader for every clash tool

Reads never edit. `snapshot()` is `pynavis.clash.snapshot_results` (its element and
grid memos, field measured) plus one extra pass over the same leaves to add what
tools need. ORDER, verified in pynavis/clash.py: snapshot_results walks
`test.Children` depth first, recursing into a `ClashResultGroup` before the next
sibling, appending only `ClashResult` leaves; `row['id']` is that index. `results()`
walks with the same two isinstance tests in the same order (`clash.walk_results` is NOT
used for alignment: it would also yield a non-group non-result child). `snapshot()`
checks the count and every name pairwise and raises rather than mislabel a row.

Row keys: pynavis' `id, name, center, item_a, item_b, item_a_name, item_b_name, level,
grid, model_a, model_b, status, assigned, group` plus `test, test_guid, guid, distance`
(model units, negative = penetration) `, distance_m, center_m, created, approved_time,
resolved_time` (ISO text or None) `, approved_by, description, priority, comments`
(count) `, trade_a, trade_b` (namo.trades of the model names, 'Unassigned' when trades is
unavailable) `, group_guid` (innermost group or None) `, key` (pair_key). `model_a` /
`model_b` are filled from the element's model root when pynavis left them blank.

Progress callbacks here are `progress(fraction 0..1, label)` (same as namo.reports);
returning False raises `Cancelled`.

| Function | Returns, behaviour |
|---|---|
| `STATUSES` | `['New', 'Active', 'Reviewed', 'Approved', 'Resolved']`; `CLOSED = ('Resolved', 'Approved')`. |
| `tests(doc=None)` | every `ClashTest`, folders flattened, tree order. |
| `test_by_name(name, doc=None)` | exact name, then case-insensitive, then `'Folder/Test'` path; None when absent. |
| `test_path(test)` | `'Folder/Sub/Test'`. |
| `results(test)` | `[ClashResult]` in snapshot order: `results(test)[row['id']]`. |
| `groups(test)` | `[{'name','guid','result' (the group),'count','statuses'}]` top-level groups. |
| `snapshot(test, doc=None, progress=None)` | `[row]` (above). Raises `Cancelled`, or `RuntimeError` if the tree changed mid-read. |
| `snapshot_all(tests=None, doc=None, progress=None)` | `{test name: rows}`; None = every test; duplicate names get `' (2)'`. |
| `pair_key(row)` | `'<a>|<b>@x,y,z'`: element keys sorted, centre in 0.1 m cells (uses `center_m`, else `center` read as metres); a history row keeps its `key`. |
| `split_key(key)` | `(pair_text, (cx, cy, cz) or None)`. |
| `compare(old_rows, new_rows)` | PURE. `{'new','fixed','persisting','status_changed','closed_new','matched'}`; see below. |
| `counts(rows)` | `{'total', 'by_status'}`. |
| `save_history(doc_path, rows_by_test, label=None)` | stores a record, returns `{'id','label','time','counts'}`. |
| `list_history(doc_path)` | `[{'id','label','time','counts'}]` oldest first (rebuilt from records if the index is lost). |
| `load_history(doc_path, history_id)` | `{test: [rows with HISTORY_FIELDS keys]}` or None. |
| `delete_history(doc_path, history_id)` | True when it existed. |
| `image(result, path, width=640, height=360, doc=None, style='scene', quality=90)` | `images.clash`. |
| `viewpoint(result, doc=None)` | `TestsViewpointForResult` Viewpoint. |
| `show(result, doc=None)` | moves the view to the result and selects its two items. |
| `set_assigned(results, name, doc=None)` | one undo step; `''`/None unassigns; returns count. |
| `set_description(results, text, doc=None)` / `set_priority(results, priority, doc=None)` | one undo step each; count. |
| `add_comment(result, text, doc=None, author=None, status='New')` | existing comments plus one; author defaults to `namo.config.user_name()`; returns the new comment count. |
| `resolve_guid(test, guid_text, doc=None)` | live result (document Guid index first, then a walk) or None. |

`compare` matches by exact `pair_key`, then (for what is left) the same element pair
with the centre at most one 0.1 m cell away on each axis (a centre that sat on a
rounding boundary). `new` = unmatched open new rows; `fixed` = OLD rows that were open
and are now gone or Resolved/Approved; `persisting` = new rows still open whose old
match was open; `status_changed` = `[(old, new)]` pairs whose status differs;
`closed_new` = unmatched new rows already closed; `matched` = pair count.

History lives in `namo.store`: a `Store('clash-history-index', doc_path)` index plus a
`RecordStore('clash-history', doc_path)` with one compact record per save (rows as lists
in `HISTORY_FIELDS` order: `key, test, status, distance_m, created, trade_a, trade_b,
name, grid, level`), so listing never loads the rows. Mode follows `namo.config`
`data_mode` (local, shared, or inside the model).

Traps: the per-result edits are `TestsEditResult*` calls, fine for hundreds; measure
before running them over tens of thousands. Never restructure results here: grouping is
`pynavis.clash.apply_plan`. `pair_key` stability across runs rests on
`ModelItem.InstanceGuid` being stable for re-exported elements (**UNVERIFIED**).

---------------------------------------------------------------------------------------

## camera: the camera, saved viewpoints and section planes as data

**Rotation3D convention.** `Viewpoint.Rotation` is a unit quaternion `(A, B, C, D) =
(x, y, z, w)`: vector part first, scalar last. The camera looks along its local -Z with
local +Y up and +X right; the rotation maps that frame to the world. Identity is a plan
view (looking down -Z, world +Y up the screen); a Front view (looking +Y, Z up) is
`(0.7071, 0, 0, 0.7071)`. Evidence: pyNavis' shipped Section Nudge reads the live
camera exactly this way; Autodesk's view-direction sample uses the same formula;
`Rotation3D(a, b, c, d)` takes components in A, B, C, D order. **UNVERIFIED in-app** (the
first check in the notes). To stay safe, `apply()` only WRITES a Rotation3D it was
given (a captured camera round-trips exactly whatever the convention); cameras built
from maths (`look_at`, `from_bcf`, `make_cam(direction=...)`) are aimed with
`Viewpoint.AlignDirection` + `AlignUp`, the calls the shipped Plan to Selection uses.

`HeightField` is the vertical field of view in RADIANS for perspective (field verified
by Apply Speeds) and is taken to be the visible HEIGHT in model units for orthographic
(**UNVERIFIED**).

Camera dict (what `capture` returns, `apply` accepts): `{'position', 'rotation'
(A, B, C, D) or None, 'rotation_computed', 'direction', 'up', 'projection' ('persp' |
'ortho'), 'height_field', 'fov' (degrees or None), 'focal_distance', 'aspect', 'json'
(Viewpoint.GetCamera text or None)}`. Tuples, floats and text only, so it goes straight
into JSON (tuples come back as lists; `apply` accepts either).

Pure: `quat_to_axes(a, b, c, d) -> (direction, up, right)`, `axes_to_quat(direction,
up) -> (a, b, c, d)` (D >= 0), `rotate(q, v)`, `orthonormal_up(direction, up)` (falls back
to +Y then +X when up is parallel, so straight-down views are north-up),
`look_at_axes(eye, target, up=(0,0,1))`, `bearing_pitch(direction, north=(0,1,0),
up=(0,0,1)) -> (degrees clockwise from north, degrees above horizon)`,
`compass_name(bearing)`, `projection_name(x)`, `fov_degrees(height_field, projection)`
(None for ortho), `height_field_for(fov_deg)`, `vertical_fov(h, aspect)`,
`horizontal_fov(v, aspect)`, `make_cam(position, direction=None, up=None, rotation=None,
projection='persp', height_field=None, focal_distance=None, aspect=None, json=None)`,
`target_of(cam, distance=None)`, `to_bcf(cam, unit_to_m)`, `from_bcf(bcf_cam,
m_to_unit)`, `horizontal_planes(z_top, z_bottom=None, center=(0,0))`, `range_ok(rng)`,
`unique_name(name, existing)`, `split_path(path)`, `normalize(v)`.

BCF dicts: `{'type': 'PerspectiveCamera' | 'OrthogonalCamera', 'CameraViewPoint',
'CameraDirection', 'CameraUpVector' (tuples, metres for the point), 'FieldOfView'
(vertical degrees, perspective), 'ViewToWorldScale' (visible height in metres,
orthogonal), 'AspectRatio'}`. `from_bcf` also reads lower-case keys and the short
names `position/direction/up/fov/scale`, re-orthogonalises the up vector, and leaves
`rotation` None (so `apply` aims with AlignDirection/AlignUp).

| API | Returns, behaviour |
|---|---|
| `capture(doc=None)` | camera dict from `CurrentViewpoint.CreateCopy()` (`.Value` does not follow the live camera). |
| `from_viewpoint(viewpoint)` | camera dict from any Viewpoint (saved view, clash view). |
| `apply(cam, doc=None)` | one CopyFrom of an edited copy; keeps the current clip planes, lighting, style. Without `height_field` the lens is kept, except across a projection change (perspective gets 60 degrees; orthographic gets the vertical extent at the focal distance). Returns the Viewpoint written. |
| `to_viewpoint(cam, base=None, doc=None)` | detached Viewpoint (base default: current copy). |
| `look_at(eye, target, up=(0,0,1), fov_deg=None, doc=None)` | perspective, focal distance on the target. |
| `zoom_to(items_or_bbox, doc=None, margin=0.0)` | `ZoomBox` on a copy along the current direction; False when nothing has extent. |
| `ensure_folder(path, doc=None)` / `folder(path, doc=None)` | the saved-viewpoints FolderItem at `'A/B/C'`, created as needed (one undo step), tree-resident. |
| `save_view(name, folder=None, cam=None, comments=None, doc=None)` | SavedViewpoint (tree-resident, re-found by Guid after AddCopy), name deduped among siblings `'name (2)'`, comments a string or list. Camera and sections only: hidden items and overrides are NOT captured by `SavedViewpoint(Viewpoint)`. |
| `saved_views(doc=None, include_animations=False)` | `[(folder_path 'A/B', SavedViewpoint)]` tree order. |
| `find_view(name_or_path, doc=None)` | the view at a stored path (`view_path(folder_path, name)`) or with a bare name; None. The exact stored path is tried before splitting on `/`, so a name holding a slash is found (`match_view` is the pure lookup). |
| `write_camera(viewpoint, cam)` | writes a camera dict onto a Viewpoint you already hold, in place; returns it. |
| `recall(saved, doc=None)` | makes it current (camera, sections, its hide/override state). |
| `clip_state(doc=None)` / `set_clip_state(payload, doc=None)` | the section as a JSON-safe dict in pynavis.viewstate's own shape (Copy State compatible); set is one undo step, planes re-aimed with `AlignToPick(Custom, ...)`. Prefer these. |
| `clip_json(doc=None)` / `set_clip_json(text, doc=None)` | Navisworks' own JSON via `View.GetClippingPlanes` / `TrySetClippingPlanes` (raises ValueError when refused). **UNVERIFIED**, including undo. |
| `horizontal_section(z_top, z_bottom=None, doc=None)` | plane 1 at z_top keeps what is below, plane 2 at z_bottom keeps what is above, other planes off, range = model box. One undo step; returns planes written. |
| `section_box(box, doc=None)` | Box mode around `((min), (max))`. |
| `clear_section(doc=None)` | sectioning off; False when already off. |

Plane normals point INTO the kept volume (pynavis.section.KEEP_INWARD, the one empirical
constant of the shipped Section tools).

---------------------------------------------------------------------------------------

## images: images of the model

`Document.GenerateImage(style, width, height, sectioning)` and
`TestsImageForResult(result, style, width, height)` return a `System.Drawing.Bitmap`;
`save_bitmap` writes it (format from the extension: .png, .jpg/.jpeg with quality via
an Int64 EncoderParameter, .bmp) through a temp file, and always disposes it.
`pynavis.export.viewpoint_image` is an unverified COM guess: do not use it.

| Function | Returns, behaviour |
|---|---|
| `STYLES` | `{'scene': 'Scene', 'overlay': 'ScenePlusOverlay', 'raytrace': 'SceneUsingRayTrace'}` (enum member NAMES, resolved by `style_enum`, so the module imports anywhere). |
| `capture(path, width=1920, height=1080, doc=None, style='scene', sectioning=True, quality=90)` | path. ValueError for a bad extension or size (1..8000 a side). |
| `capture_saved(saved_viewpoint, path, **kw)` | makes it current, then capture. Wrap batches in ViewKeeper. |
| `clash(result, path, width=640, height=360, doc=None, style='scene', quality=90)` | the result's own image. |
| `thumbnail(src, dst, max_width=320, quality=85, max_height=None)` | dst; never scales up; JPEG gets a white background; src is not locked. |
| `ViewKeeper(doc=None, restore_saved=True)` | context manager: puts the current saved viewpoint (re-applying its states) and then the exact camera back on exit, even after an exception. |
| `save_bitmap(bitmap, path, quality=90, dispose=True)` | path; IOError naming the path when GDI+ refuses. |
| `resize(image, width, height, background=None)` | new Bitmap, high-quality bicubic, clamped edges (caller disposes). |
| `image_size(path)` | `(w, h)` without locking the file. |
| Pure | `format_for(path)`, `fit_size(w, h, max_w=None, max_h=None)`, `clamp_quality(q)`, `check_size(w, h)`. |

Trap: `capture_saved` relies on the recalled view being applied before
`GenerateImage` renders (**UNVERIFIED**; see notes).

---------------------------------------------------------------------------------------

## colors (pure) and paint (API)

`colors`: `PALETTE` (12 categorical mid tones, readable as fills on light and dark,
pairwise distinct), `for_values(values, palette=None) -> [(value, hex)]` (distinct
values in first-seen order; past 12 it continues with golden-angle generated hues, so
no two values share a colour), `color_at(index)`, `generated(index)`, `sequential(t)`
(0..1 light-to-strong blue), `diverging(t)` (blue, grey at 0.5, red), `bands(n)` (n
ordered tints, first visible, last strongest), `ramp(stops, t)`, `STATUS` (clash
statuses New red, Active orange, Reviewed blue, Approved green, Resolved yellow, plus
Not started, Planned, In progress, Complete, Delayed, On hold, Demolish, Temporary,
Existing) with `status_color(name, default=None)` (case-insensitive), `GHOST`,
`MISSING`, `parse_hex(text)` (None when not a colour), `hex_to_rgb`, `rgb_to_hex(r, g, b)`
or `rgb_to_hex((r, g, b))`, `rgb01(hex)` (0..1 for Api.Color), `from_rgb01`,
`luminance`, `contrast_ratio`, `contrast_text(hex) -> '000000' | 'FFFFFF'`,
`distance`, `blend(a, b, t)`, `lighten`, `darken`, `hsl_to_hex`.

`paint` (every write one undo step):

| Function | Returns, behaviour |
|---|---|
| `nw_color(hex)` | `Api.Color` (0..1 channels). |
| `apply(groups, doc=None, name='Color items')` | groups `[(items, hex_or_None, transparency_or_None)]`, permanent overrides in ONE transaction named `name`; empty and do-nothing groups skipped; returns items written. ValueError for a bad colour. |
| `ghost(keep_items, transparency=0.85, hex=None, doc=None, name='Ghost other items')` | ghosts everything EXCEPT keep_items, leaving the kept items' own colours alone; returns how many top-level subtrees were ghosted; 0 and no edit for an empty keep. transparency None with a hex greys without fading. |
| `reset(items=None, doc=None, name='Reset appearance')` | removes permanent overrides from items, or everything (returns -1). |
| `temporary(groups, doc=None)` / `reset_temporary(doc=None)` | temporary overrides (not saved, not undoable) for previews. |
| `remember_scheme(scheme)` / `last_scheme()` | global store `'last-color-scheme'`; scheme `{'title', 'property': {'category','property'}, 'entries': [{'value','hex','count'}], 'ghost', 'time'}` (normalized by `normalize_scheme`). |
| `read_color(item)` | `(hex, transparency)` from the first geometry's ActiveColor/ActiveTransparency, `(None, None)` on failure. **UNVERIFIED**: older field notes found overrides unreadable through COM; treat as best effort. |
| `plan_groups(groups)` | pure: what apply would write. |

Why ghost is built on `items.complement` rather than "override the roots, then reset the
kept items": that would wipe colours just given to the kept items, and whether resetting
a child undoes an override stored on its ancestor depends on undocumented storage. The
complement never touches a kept item or any of its ancestors, so it is right either
way; the cost is the kept items' ancestors and their children, then one override call.

---------------------------------------------------------------------------------------

## mesh (pure) + one triangle source

Triangles are `((x,y,z), (x,y,z), (x,y,z))` in world coordinates
(`pynavis.geometry.world_triangles`). `area(tris)`, `signed_volume(tris)`,
`volume(tris)` (abs, computed relative to the box corner for precision far from the
origin), `bbox(tris)`, `area_centroid(tris)`, `solid_centroid(tris)` (None when the
volume is ~0), `centroid(tris)` (solid when `solid_measure` passes, else area), `solid_measure(tris) -> {'volume','centroid'} or None` (GEOMETRIC closure: accepts a watertight solid whose faces share no vertices, refuses open and miswound meshes), `weld_tolerance(tris, noise=0.0)` (4 x noise, at least 1e-7 of the mesh size; the default `tol`), `weld(tris, tol=None) ->
(vertices, faces)` (rounding to a tol grid, collapsed triangles dropped),
`edge_counts`, `is_closed(tris, tol)` (every welded edge used exactly twice),
`open_edges`, `translate(tris, v)`, `count(tris)`, `triangle_area(tri)`,
`summary(tris, tol=None) -> {'triangles','area','volume' (None unless solid_measure passes),'closed' (geometric),'welded' (topological is_closed),
'centroid','bbox'}`.

`item_triangles(item, budget=200000) -> {'tris', 'note', 'noise'}`: IronPython only (COM
callback). Empty `tris` means UNKNOWN (note says why), never "no faces". `noise` is the
float32 coordinate noise in model units: use a few times it as the weld/closure
tolerance on models far from the origin. Only a closed mesh has a meaningful volume.

---------------------------------------------------------------------------------------

## ui: WPF building blocks themed by the pyNavis design system

Colours come from `PyNavis.Runtime.Forms.DesignSystem.Tokens.Current` (light/dark
following Navisworks) plus the Windows accent, used only on the primary button,
selection rails, checked boxes and focus rings. Segoe UI Variable 13 px, 32 px controls
and rows, 8 px gaps, 24 px padding (16 px in data-dense windows), solid surfaces. Every
window is owned by Navisworks (`FluentChrome.Apply`) when shown; modal ones refuse to
open under `pynavis run` (RuntimeError, same message as pynavis.forms: check
`__runner__` first). Keyboard: Tab order follows the layout, Enter = primary, Esc =
cancel, Ctrl+F = filter, Space ticks rows, Down from a filter box enters the table.

### Ready-made windows

`form(title, fields, intro=None, ok='OK', cancel='Cancel', width=460, units=None,
validate=None)` -> `{key: value}` for every non-label field, or None on Esc/Cancel/close.
Never closes on invalid input: the field's hint line turns into a red sentence and the
first bad field gets focus; errors update live after the first OK. `units` are the
document units for 'length' fields (default: the active document's). `validate(values)`
may return `{key: sentence}` or one sentence (shown under the first field).

Field dicts: `{'kind', 'key', 'label', 'default', 'fallback' (choice/radio: used when a saved default is no longer an option; without it a default that is not an option VALUE raises), 'hint', 'required', 'enabled_if':
(other_key, value or list of values), 'validate': fn(value) -> sentence or None}` plus:

| kind | extra keys | value returned |
|---|---|---|
| `text` | `placeholder` | str (`''` when blank) |
| `textarea` | `rows` (4), `placeholder` | str with `\n` |
| `int` | `min`, `max`, `suffix` | int or None when blank |
| `number` | `min`, `max`, `suffix` | float or None |
| `length` | `min`, `max` | float in DOCUMENT units (pynavis.lengths: `1' 6 1/2"`, `25mm`, bare numbers in doc units); default pre-filled the way users type it; auto hint |
| `choice` | `options` (str or (label, value)) | the value (first option when no default) |
| `radio` | `options`, `inline` | the value |
| `check` | (label sits beside the box) | bool |
| `multi` | `options`, `default` (ticked values) | [values] in option order; filter box + All/None past 8 options |
| `file_open` | `filter`, `title` | path (must exist) or `''` |
| `file_save` | `filter`, `default_name`, `title` | path (its folder must exist) or `''` |
| `folder` | `title` | path (must exist) or `''` |
| `color` | | `'RRGGBB'` (swatch + Pick button with the Windows colour dialog) |
| `date` | | `'YYYY-MM-DD'` text or `''` (ISO order only; a Today button) |
| `label` | `text`, `muted` | (no value) |
| `separator` | | (no value) |

A disabled field (`enabled_if` false) is not validated and returns its value if it
reads, else its default.

`choose(title, rows, columns, multiselect=True, checked=None, prompt=None, search=True,
ok='OK', width=640, height=540)` -> `[values]` or None. rows `[{'value': v, 'cells':
[...]}]` (plain lists work: the value is the row index); `checked` opens those values
ticked (or selected). Multiselect: click a row or press Space to tick; Select all /
Clear act on the rows the filter shows; the result is the ticked values in row order.
Single: double-click or Enter picks; the result is a ONE-item list.

`table_window(title, headers, rows, actions=None, on_open=None, modeless=False, key=None,
status=None, width=820, height=560)` -> Window. Filter box, sortable headers, multi-row
selection, a status line, action buttons and Close (Esc). `actions`: `(label, fn)`,
`(label, fn, needs_selection)` or `{'label', 'fn', 'needs_selection' (default True:
greyed until a row is selected), 'primary'}`; `fn(selected_values)` runs with
exceptions logged and toasted ("Could not <label>"). `on_open(value)` on double-click or
Enter. Modal by default (returns after close). `modeless=True`: one window per `key`
(default the title) that stays open; calling again updates its rows/status and brings
it forward. Refresh with `window.Tag.update(rows, status=None)` or `update_table(window,
rows, status)`; `window.Tag.selected()`; `window.Tag.set_status(text)`.

Each has a `build_*` twin returning the unshown Window (`build_form` with
`window.Tag` a `FormState`: `.collect() -> (values, errors)`, `.accept()`, `.set_raw(key,
raw)`, `.result`, `.accepted`; `build_choose` -> `ChooseState`: `.table`, `.values()`,
`.accept()`; `build_table` -> `TableState`). Show a built window with
`show_modal(window)`.

### Tables

Cells may be text or numbers. A column whose cells are all numbers (or numeric text)
sorts numerically, right-aligned with tabular figures and thousands separators
(`format_cell`: ints `1,234`, floats two decimals or three significant figures below 1,
Yes/No for booleans); text columns sort naturally (`Level 2` before `Level 10`).
Pass pre-formatted text when you want another format. Column kinds are decided from
the rows given (and re-decided by `update`).

`Table(columns, rows, checkboxes=False, multiselect=True, show_headers=True,
on_open=None, on_change=None)`: `.element` (put it in a layout), `.update(rows)` (keeps
ticks by value and the filter), `.set_filter(query)` (every word must appear in some
cell), `.checked_values()`, `.set_checked(values=None, on=True, visible_only=False)`,
`.selected_values()`, `.select_values(values)`, `.visible_count()`, `.total()`,
`.focus_first()`. A WPF DataGrid over a DataTable view: virtualised (20,000 rows build
in about 1.5 s under IronPython; filtering is instant).

### Parts for custom windows

`window(title, width=560, height=None, resizable=True, min_width=None, min_height=None)`
(themed, unshown; height None sizes to content), `text(value, size=13, muted=False,
bold=False, color=None, wrap=True)`, `heading(value)`, `hint(value)`, `button(label,
on_click=None, kind='secondary'|'primary'|'quiet'|'danger')` (on_click wrapped by
`safe`), `text_box(value='', placeholder=None, suffix=None, multiline=False, rows=4) ->
(shell, box)`, `search_box(placeholder='Filter', on_change=None, delay_ms=150) ->
(element, box)` (debounced), `combo(options, selected=None, width=None)` +
`combo_value(control)`, `check(label, checked=False)`, `radio_group(options,
selected=None, inline=False) -> (panel, buttons)` + `radio_value(buttons, pairs)`,
`separator()`, `group(title, content)` (DesignSystem.GroupFrame), `footer(buttons,
left=None, padding=24)`, `scroll(content, max_height=None)`, `tokens(dark=None)`,
`palette()` (`'#RRGGBB'` by token name), `brush(hex)`, `accent()`,
`theme_resources()` / `apply_theme(element)` (implicit styles for CheckBox,
RadioButton, ComboBox, ScrollBar, TextBox, ToolTip; keyed `namo.grid`, `namo.header`,
`namo.row`, `namo.cell`, `namo.checkcell`, `namo.focus`), `work_area()`.

### Plumbing

`Modeless(key, title, content_builder=None, width=560, height=None)`: `.show()` creates
the window (content_builder(window) may return the content) or brings the open one
forward; owned by Navisworks, `ElementHost.EnableModelessKeyboardInterop` BEFORE Show,
forgets itself when closed; `Modeless.get(key)`, `Modeless.close(key)`, `.build()`.
`non_activating(window)` (no focus steal, not in the taskbar: WS_EX_NOACTIVATE |
WS_EX_TOOLWINDOW via ctypes; call before Show). `host_rect()` (Navisworks main window in
screen PIXELS; work area fallback), `dpi_scale()`, `place_rect(host, size,
where='center'|'top-right'|'bottom-right'|'bottom-left'|'top-left', margin=24)`.
`run_later(fn, delay_ms=0) -> cancel()` (UI-thread one-shot), `Debouncer(delay_ms,
fn)` with `.trigger()`, `.cancel()`, `.flush()`. `safe(fn, label=None, logger=None)`
wraps a late callback (logs the traceback, never raises); `pinned_logger()` captures
the running command's logger for later; `log_error(message, logger=None)`.
`copy(text)`, `open_path(path)`, `show_in_explorer(path)`, `is_runner()`.

Pure helpers (tested): `normalize_fields`, `options_of`, `parse_int`, `parse_number`
(`1,234.5`, `1 234,5`, `12,5`), `parse_date`, `parse_color`, `validate_value`,
`collect`, `is_enabled`, `default_text`, `length_hint`, `natural_key`, `format_cell`,
`cell_number`, `numeric_columns`, `column_weights`, `normalize_rows`, `search_text`,
`matches`, `filter_words`, `like_escape`, `row_filter`, `count_text`, `place_rect`,
`theme_xaml`.

Rules for callbacks that run after the script returned (modeless windows, timers):
capture `me = script.bind()` and `ui.pinned_logger()` during the run; wrap every
handler with `ui.safe`; never call `script.get_config()` from a late callback.

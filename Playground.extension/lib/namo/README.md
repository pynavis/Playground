# namo: the Playground shared library

Every Playground tool is a thin `script.py` over modules in this folder. Read the section of
each module you use, then open its source: every public function has a docstring. The
three sections below were written by the agents who built them and are accurate to the
code.

## Module index

| Module | Purpose | Navisworks? |
|---|---|---|
| `xlsx` | Styled Excel workbooks: fills, formats, widths, freeze, autofilter, merges, links, images | pure |
| `htmlreport` | Standalone themed HTML reports: KPIs, sortable/filterable tables, SVG charts, images | pure |
| `pdf` | Minimal PDF writer: pages, text, wrap, images, lines, page numbers | pure |
| `png` | PNG encode/decode, image size sniffing | pure |
| `paths` | Data roots (local/team), document keys, safe file names, atomic writes, locks | pure |
| `config` | Playground-wide settings (user, project, data mode, trades, report units) | pure |
| `session` | State that survives pyNavis' per-run lib reload (holders, small log) | pure |
| `store` | Per-document / global JSON stores and record stores (local, shared, in the model) | pure (+docdb) |
| `docdb` | Data stored INSIDE the NWF/NWD (Document.Database SQLite) | API |
| `naming` | Name templates (`{test} {n:000} {date:%Y%m%d}`), unique names, sanitising | pure |
| `rules` | One condition engine (18 operators), cell parsing, native search mapping | pure (+sets) |
| `trades` | Trade of a model/file name from rules | pure |
| `textmatch` | Fuzzy ranking and highlight spans (Quick Find, Command Palette) | pure |
| `ifcguid` | IFC GlobalId compress/expand, Revit UniqueId to IFC GUID | pure |
| `templates` | Named saved configurations per tool (team-shareable) | pure |
| `reports` | Registry + runner for automation-ready reports (`rep_<id>.py` contract); `Page` / `deliver` / `show_output`: a report's output-window page, recorded during the run and printed after the progress window closed | pure |
| `dates` | Parse/format dates, Excel serials, ages and buckets | pure |
| `units` | Length/area/volume/mass conversion, quantity and display-string parsing | pure |
| `items` | Walk, identify, measure, select and show model items | API (+pure) |
| `variants` | Property values as Python values (pynavis.props.get and all_of with lengths, areas, volumes and angles read through their own readers); use instead of pynavis.props | API |
| `clashdata` | Clash snapshots, history, compare, images, viewpoints, result edits | API (+pure) |
| `camera` | Cameras and saved viewpoints as data, BCF cameras, sections | API (+pure) |
| `images` | Images of the model and of clash results (GenerateImage) | API |
| `colors` / `paint` | Palettes and colour math / applying colour, transparency, ghosting | pure / API |
| `mesh` | Area, volume, centroid, closedness, welding of triangle meshes | pure (+geometry) |
| `ui` | WPF forms, choosers, tables, modeless windows themed by the design system | WPF |
| `progress` | Cancellable progress window <-> Playground progress callbacks, one CANCELLED marker; `run` prints a report's pending `reports.Page` once the window has closed | pyNavis forms |
| `hooks` | Event dispatcher: hooks/<event>.py -> `hk_<name>.handle(name, event)` | pure |
| `picking` | THE way to click a point or an object in the view: `point(prompt, want_item=False)` / `points(prompt, second_prompt)` on the host's Measure tool with the prompt on `pynavis.banner` (None on Esc). `pynavis.pick.point` / `point_then` are banned (`dev/check.py` fails on them). `point()` is safe from a late callback such as a dock pane button: it needs only the active document and a logger, no run context | API |
| `pins` | The one pin glyph for the view (Photo Pins, Issue Pins): `segments(point, height)` stem, octahedron head readable from any side and in plan, foot cross; `top()` for the label | pure |
| `clashset_edit` | Bulk edits of clash results (names, statuses, assignees, comments): one by one up to `EDIT_LIMIT` (200), above that one detached rebuild per test and a single `TestsReplaceWithCopy` (`mode_for`, `rebuild`, `commit`, `one_step`). Use it instead of looping `clashdata.set_*` over hundreds of results | API (+pure) |

## Conventions that cross modules (read these)

* **Cancelling is silent.** `ui.form`/`ui.choose` return None, `forms.*` return None/False:
  return with no toast. `reports.run` returns `result['cancelled'] = True` on a cancel:
  interactive callers check it and exit WITHOUT a toast.
* **One Cancelled class**: `namo.items.Cancelled`. Progress callbacks in `items`
  (`tick(done, total)`) and `clashdata` (`progress(fraction, label)`) stop the work when
  they return False, which raises `items.Cancelled`. `reports.Cancelled` is the report-level
  equivalent (`reports.run` treats both as a cancel).
* **Progress shape for reports** is `progress(fraction 0..1, label)`, the same as
  `clashdata`. Use `namo.progress`: `outcome = progress.run('Exporting', lambda report:
  work(progress=report))` opens pyNavis' cancellable progress window, and returns
  `progress.CANCELLED` for every cancel flavour (exit silently on it).
  `progress.tick(report)` adapts to items-style `tick(done, total)`;
  `progress.adapter(handle, start, span)` drives a slice of an existing `forms.progress`
  bar for multi-stage work; `progress.silent` for automation.
* **Images into PDFs**: write JPEG (or RGB PNG) with `images.capture(..., path.jpg)`;
  RGBA PNGs must be decoded in pure Python by `pdf` (slow at 1920x1080 on IronPython).
* **Thumbnails in filtered Excel tables**: `ws.image(..., anchor='cell')` so filtering
  hides a thumbnail with its row.
* **Colours**: hex 'RRGGBB' strings everywhere (`colors`, `xlsx`, `htmlreport`,
  `ui` colour fields); `paint.nw_color(hex)` converts for the API. Clash statuses use the
  native Clash Detective colours in every module (New red, Active orange, Reviewed blue,
  Approved green, Resolved yellow).
* **Units**: model values are in DOCUMENT units; convert with `units.to_meters(value,
  str(doc.Units))`; reports honour `config.get('report_units')`.
* **Tests that need real pynavis pure modules** import them directly: `_compat` already put
  `<pyNavis checkout>\pynavislib` on `sys.path` under CPython. A fake Navisworks layer for
  API-half tests lives in `dev/tests/test_items.py` (`import test_items as nav`).
* **Custom windows** may use these public `ui` parts: `ui.thickness(*values)`,
  `ui.close_with(win, result)`, `ui.load_wpf()` (imports the WPF namespaces),
  `ui.Bag` (attribute bag), plus `ui.window`, `ui.text`, `ui.heading`, `ui.hint`,
  `ui.button`, `ui.text_box`, `ui.search_box`, `ui.combo`, `ui.check`, `ui.radio_group`
  (options are `(label, value)` pairs), `ui.group`, `ui.footer`, `ui.scroll`, `ui.Table`,
  `ui.show_modal`, `ui.safe`, `ui.pinned_logger`. `textmatch.Index(items).subset(indices)`
  ranks a filtered part of a big list without re-lowercasing.
* **The pyNavis output window opens only http(s) and mailto links.** A file link clicked
  there navigates the output window itself. Print file paths as text (or
  `output.element_link` for model items) and open files from the script (`ui.open_path`,
  `ui.show_in_explorer`), e.g. after a confirm or as a toast detail.
* **Report output**: `reports.output_path(config, ...)` honours `config['path']` (a file
  the user picked) before `folder` + `name_template`.
* **Writing custom properties**: any tool that writes or removes custom tabs calls
  `namo.propindex.invalidate()` afterwards (guarded import), so Property Explorer's
  cached scan never shows stale values.
* **CSV under IronPython 3.4**: `io.open(path, 'w', encoding='utf-8-sig')` writes the
  byte-order mark before EVERY write call. Build the whole text in memory and write it
  once (as bytes: `codecs.BOM_UTF8 + text.encode('utf-8')`), as `rep_clash_trends.write_csv`
  does.
* **LcOclClashUtils.CountByStatus** has a 2-argument and a 3-argument (`recurse`) overload;
  pass `True` to count results inside result groups.
* **.NET UI references**: pyNavis' engine references no WPF/WinForms assemblies, so
  `from System.Windows.Threading import ...` fails on the first WPF use of a session.
  Importing the `namo` package references WindowsBase, PresentationCore,
  PresentationFramework, System.Xaml, System.Drawing, System.Windows.Forms and
  WindowsFormsIntegration, so import any `namo` module BEFORE importing a `System.Windows`
  or `System.Drawing` namespace in a script. `devresh_import.py` (a verify stage) imports
  every namo module in a fresh engine to catch regressions.
* **Never import Navisworks at module level** in a namo module: lazy-import inside functions
  so `import namo.<module>` works in tests and outside a session.

* **Choice and radio defaults are checked** (`ui.normalize_fields`, so every `ui.form`):
  options are `(label, value)` pairs and `default` is a VALUE. A default that is not one of
  the option values raises `ValueError` (the window would open with nothing chosen; options
  written `(value, label)` look exactly like that). `None` means the first option. A default
  read from saved settings can be stale for good reasons, so give such a field
  `'fallback': <value>` (or `None` for the first option): it is used instead of raising, and
  is itself checked. An `enabled_if` on a choice/radio field must compare with a value that
  field offers (a list needs at least one), on a check field with `True`/`False`.
* **Nothing prints to the output window while a progress window is up** (it would open
  empty behind the bar; even `output.element_link` opens it). A report builds a
  `reports.Page` (`html`, `md`, `table`, `bar_chart`, `line_chart`, `later(build)` for
  markup with element links) and returns `reports.deliver(result, page, progress)`;
  `progress.run` prints the page after the window closed. Scripts print only after
  `progress.run` has returned.
* **No progress window from a button of a MODAL window.** pyNavis' progress window
  re-enables the Navisworks main window when it closes, leaving Navisworks live under the
  dialog. Build the window in `ui.modal_loop(build)` and have the action call
  `defer(job)`: the window closes, the job runs (progress, prompts, toasts), the window
  comes back with fresh rows. `reportrunner.run_closed`, `data_write.link_flow` and
  `extmanager.run_window` are the examples. Modeless windows are not affected.
* **Path fields are probed on OK, not per keystroke** (`ui.FormState`): while typing, a
  `file_open` / `file_save` / `folder` field is only checked for being filled in, its own
  `validate` and the form-level `validate` do not run, and the errors of the last OK stay
  until the text they are about changes.
* **Small length defaults**: a `length` field whose default rounds to `0' 0"` on the
  1/16 in grid opens as decimal inches (`0.0197"`), which reads back as the value shown.
* **Saved viewpoint paths**: store `camera.view_path(folder_path, name)` and read back with
  `camera.find_view(path)`; it tries the exact stored path before splitting on `/`, so a
  viewpoint named `Level 1/2` is found. `camera.write_camera(viewpoint, cam)` edits a
  viewpoint you already hold in place.
* **The namo package body runs on every click and every hook run** (pyNavis drops lib
  modules each run); its `clr.AddReference` calls run once per engine behind a marker
  module in `sys.modules`. Keep `namo/__init__.py` free of anything slower.

## namo documents: xlsx, htmlreport, pdf, png (foundation F1)

Four pure modules that write the files Playground tools hand to people: Excel workbooks,
standalone HTML reports, PDFs and PNGs. None of them imports Navisworks or .NET; all
four behave identically on CPython 3.11 and IronPython 3.4, down to the byte (golden
digest tests prove the same calls produce the same xlsx, HTML and PDF on both engines).
Every writer saves atomically (temp file beside the target, then `os.replace`), creates
missing folders, and returns the path. A file locked by Excel or a PDF viewer raises
`IOError`/`OSError` from `save()`: catch it in the tool and toast "Close the file in
Excel, then try again."

Rows, columns and pixels are 0-based. Colours are hex `'RRGGBB'` text unless a module
says otherwise. Never pass user or model text as trusted HTML: every text argument is
escaped for you, and only `htmlreport` `html()`, `cell_html` cells and the strings from
`status()`/`status_chip()`/`link()` go in raw.

---------------------------------------------------------------------------------------

### xlsx: styled Excel writer

Writes real `.xlsx` packages (zipfile + string-built OOXML): named cell styles (fonts,
fills, borders, alignment, number formats), column widths, row heights, merged title
rows, frozen panes, autofilter, hyperlinks (web, file, in-workbook), formulas and
embedded PNG/JPEG pictures. Verified: openpyxl loads every test workbook with warnings
treated as errors, and Excel 16.0.20430 (by automation, where a file needing repair
fails to open) opens the demo, test, `write_simple` and a 20,000-row IronPython-written
workbook cleanly, seeing the expected pictures, links, filters, frozen panes and merges.

```python
from namo import xlsx
wb = xlsx.Workbook(title='Clash report', author=user)        # file properties
ws = wb.sheet('Clashes')                                     # name sanitised + deduped
ws.title('Level 3 coordination', span=6)                     # merged bold row 0
ws.subtitle('Hospital.nwf, 2026-10-05', span=6)              # merged muted row 1
ws.columns([('Name', 28, None), ('Status', 12, None), ('Distance', 12, 'num2'),
            ('Found', 12, 'date'), ('Link', 10, None), ('Image', None, None)])
for c in clashes:
    r = ws.row([c['name'], c['status'], c['distance'], c['created'],
                xlsx.Link(c['image_path'], 'Open')],
               styles=[None, xlsx.status_style(c['status'])], height=50)
    ws.image(c['thumb_png'], r, 5, width_px=96, offset_px=(4, 4), fit_cell=True, anchor='cell')
ws.autofilter()
wb.save(path)
```

#### Module functions and classes

| Call | Returns | Behaviour |
|---|---|---|
| `Workbook(title=None, author=None, created=None)` | Workbook | Built-in styles installed. `created` (naive UTC datetime, default now) stamps file properties and zip entries: fix it for byte-identical output. |
| `wb.style(name, bold=False, italic=False, size=None, color=None, fill=None, border=False, align=None, valign=None, wrap=False, num_format=None, underline=False, base=None, font=None, border_color='BFBFBF', border_style='thin', indent=0)` | name | Define or redefine a style. `border`: `False`, `True`/`'all'`, or sides `'bottom'`, `'top bottom'`. `align`: left/center/right/fill/justify/centerContinuous/distributed/general. `valign`: top/center (`'middle'` accepted)/bottom. `color`/`fill`: `'RRGGBB'`, `'#RRGGBB'`, `'AARRGGBB'` or `(r, g, b)`. `base='x'` starts from style x and overrides only what you pass. Bad values raise `ValueError` now, not at save. |
| `wb.fill_style(hex_fill, base='cell')` | style name `'fill:RRGGBB:base'` | Cached: `base` plus a solid fill; text turns white on dark fills (luminance < 0.18). Use for heatmaps, e.g. `wb.fill_style(colors.sequential(round(t * 7) / 7.0), base='int')` (quantised so a few styles serve the whole sheet). |
| `wb.has_style(name)` / `wb.style_names()` | bool / sorted list | |
| `wb.sheet(name)` | Worksheet | Appended in call order. Name: `[]:*?/\` become spaces, max 31 chars, no edge apostrophes, `'History'` becomes `'History sheet'`, duplicates get `' (2)'`. Read the final name from `ws.name`. |
| `wb.get_sheet(name)` | Worksheet or None | Case-insensitive, by final name. |
| `wb.sheets` | list | In workbook order. |
| `wb.to_bytes()` | bytes | Whole package. A workbook with no sheets gets an empty `Sheet1`. |
| `wb.save(path)` | path | Atomic. |
| `Formula(text, value=None)` | | `'=SUM(B2:B9)'` or `'SUM(B2:B9)'`. Workbooks with formulas are flagged to recalculate fully on open; `value` is an optional cached result. |
| `Link(target, text=None, tip=None)` | | `target`: http(s)/mailto URL, file path (`C:\...`, `\\server\...`, or relative to the workbook), or `'#Sheet!A1'` inside the workbook (quote names with spaces: `'#' + quote_sheet('My sheet') + '!A1'`). `text` defaults to the target (without `#`). Paths become `file:///C:/...` with `%20`/`%23`/`%25` escapes. |
| `col_letter(col)` | `'A'`..`'XFD'` | 0-based. |
| `cell_ref(row, col, absolute=False)` | `'B3'` / `'$B$3'` | 0-based. |
| `range_ref(r1, c1, r2, c2, absolute=False)` | `'A1:C5'` | Corners in any order; one cell gives `'A1'`. |
| `quote_sheet(name)` | `"'My sheet'"` | For formulas and in-workbook links. |
| `sanitize_sheet_name(name, existing=())` | str | The rule `wb.sheet` applies. |
| `status_style(status)` | `'status_new'`.. or None | From a clash status text, any case. |
| `excel_serial(value)` | float | date/datetime/time to a 1900-system serial. |
| `px_to_points(px)`, `px_to_chars(px)`, `chars_to_px(chars)` | number | Row height points; column width characters (Calibri 11). |
| `write_simple(path, sheets, title=None, author=None)` | path | `sheets`: `[{'name', 'headers', 'rows', 'widths'?, 'styles'?, 'title'?, 'filter'?=True}]`. Header row, frozen panes, autofilter, auto widths for `None` widths. |
| `MAX_ROWS`, `MAX_COLS`, `MAX_TEXT` (32,767), `MAX_LINKS` (65,530), `EMU_PER_PX`, `BUILTIN_STYLES`, `STATUS_STYLES` | constants | |

#### Worksheet

| Call | Returns | Behaviour |
|---|---|---|
| `ws.title(text, span=6, style='title', height=22)` | row | At `next_row`; merged across `span` columns (span 1: no merge). |
| `ws.subtitle(text, span=6, style='muted')` | row | Same, muted, no height. |
| `ws.skip(rows=1)` | new next_row | Blank rows. |
| `ws.columns(specs, freeze=True)` | header row | `specs`: `(header, width_chars, style)`, `(header, width)`, `(header,)` or plain strings. Writes the header with style `header`; `width None` = auto-size at save; the style becomes the default for that column below the header. Freezes below the header (keeps frozen columns). Remembered for `autofilter()`. |
| `ws.row(values, styles=None, height=None)` | row | Appends at `next_row`. `styles`: one name for all cells or a per-cell list (shorter lists are padded with None). |
| `ws.write(row, col, value, style=None)` | None | Any cell. Moves `next_row` past `row`. |
| `ws.cell(row, col)` | (value, style) | What is stored (None, None when empty). |
| `ws.set_width(col, chars)` / `ws.set_height(row, points)` | | Excel units (width clamped 0..255, height 0..409). |
| `ws.merge(r1, c1, r2, c2)` | | Inclusive. Single cell ignored. Overlapping an existing merge raises `ValueError` (Excel would repair the file). |
| `ws.freeze(rows=1, cols=0)` | | `freeze(0, 0)` unfreezes. |
| `ws.autofilter(first_row=None, last_row=None, first_col=None, last_col=None)` | | Defaults resolve at SAVE time: header row (else row 0) to the last written row, across the header's columns (else all used columns). Also writes the hidden `_xlnm._FilterDatabase` name Excel expects. |
| `ws.autofit(min_chars=6, max_chars=60, cols=None)` | | Sets widths from content now (cells merged across columns, like titles, are ignored). |
| `ws.tab_color(hex)` | | Sheet tab colour, None resets. |
| `ws.image(path_or_bytes, row, col, width_px=None, height_px=None, offset_px=(0, 0), fit_cell=False, description=None, anchor='one')` | (w_px, h_px) | PNG/JPEG (also GIF/BMP). Native size by default; one of width/height keeps the aspect ratio; both stretch. `fit_cell=True` grows the row height and column width to hold it. `anchor='one'` (default, oneCellAnchor): moves with its cell, keeps its size, stays visible when a filter hides its row. `anchor='cell'` (twoCellAnchor, end cell computed from the final widths and heights): moves and sizes with its cells. **Use `anchor='cell'` for row thumbnails in a filterable table**: measured in Excel, filtering a 12-row demo to 3 rows hid 9 of 12 `cell` pictures but none of the `one` pictures (they float over the remaining rows). `description` is the picture's alt text (default: the file name). Identical image bytes are stored once per workbook. Raises `ValueError` for other formats. |
| `ws.next_row` | int | Plain attribute; you may set it. |
| `ws.header_row` | int or None | Last `columns()` header. |
| `ws.used_range()` | (r1, c1, r2, c2) or None | |
| `ws.name`, `ws.workbook` | | |

**Style resolution for a cell whose `style` is None:** column style from `columns()`
(rows below that header only), then the value type: date `date`, datetime `datetime`,
time `time`, `Link` `link`. An explicit style always wins; so does a column style over
the type default (a `date` column shows datetimes as dates).

**Values:** `str`; `int`/`float` (NaN and infinity become a `#NUM!` error cell);
`bool`; `None` (an empty cell, kept only when it has a style); `date`/`datetime`/`time`
(written as serial numbers with a date format); `Formula`; `Link`; .NET `DateTime`
(anything with Year..Second) becomes a datetime; `Decimal` becomes float; anything else
is written as its text. Text: control characters are removed, `\r\n` becomes `\n`
(shows as line breaks with the `wrap` style), Excel's `_xHHHH_` escape is protected,
and cells are capped at 32,767 characters (Excel's limit).

#### Built-in styles

`cell` (plain, index 0), `header` (bold, F2F2F2 fill, A6A6A6 bottom border, centred
vertically), `title` (bold 14), `muted` (6B6B6B text), `bold`, `center`, `int` (#,##0),
`num1` (#,##0.0), `num2` (#,##0.00), `pct` (0%), `pct1` (0.0%), `date` (yyyy-mm-dd),
`datetime` (yyyy-mm-dd hh:mm), `time` (hh:mm), `good`/`warn`/`bad`/`info` (soft wash
plus readable text), `link` (0563C1 underlined), `wrap` (wrap, top aligned), and the
Navisworks clash status colours softened to washes: `status_new` (red), `status_active`
(orange), `status_reviewed` (blue), `status_approved` (green), `status_resolved` (yellow).

#### Traps

* Styles are referenced by name and checked when you write: define custom styles first.
* `autofilter()` and `width None` resolve at save, so call order does not matter, but a
  stray cell written far below the table extends the filter range: pass `last_row`.
* Internal links need quoted sheet names when they contain spaces (use `quote_sheet`).
* `fill_style` caches by colour: quantise heatmap colours to a ramp (7 steps) rather
  than one style per distinct value.
* Speed: about 15 microseconds per cell on IronPython (200,000 cells built and saved:
  3 s; CPython 0.7 s). Show `forms.progress` while building big sheets.
* `anchor='cell'` stores the picture as a cell range computed at save time from the
  widths and heights (Calibri 11 pixel metrics; Excel showed the 96x54 px demo
  thumbnails at exactly 54 px). From then on the picture follows those cells, so a user
  resizing a row or column in Excel resizes the picture too.
* File links are written as `file:///C:/...` URLs. Excel opened them in testing as
  hyperlinks, but clicking a file link (and Excel's security prompt for it) is only
  checkable by hand.

---------------------------------------------------------------------------------------

### htmlreport: standalone HTML report

One self-contained `.html` (inline CSS and JS, SVG charts, base64 images) that opens
anywhere offline and follows the OS light or dark theme (`prefers-color-scheme`); it
always prints light. The pyNavis design system on the web: Segoe UI Variable stack, 13px
body, solid surfaces, hairlines, accent (#005FB8 light / #4CC2FF dark) only on links
and the focus ring, status tags as the only chip, numbers right-aligned in tabular
figures, no gradients, no shadows on content (the floating tooltip is the one popup
shadow), no emoji. Blocks render in call order.

```python
from namo import htmlreport
r = htmlreport.Report('Clash summary', subtitle='Level 3',
                      meta=[('Model', name), ('Tests', len(tests)), ('By', user)])
r.kpis([('Clashes', total, None), ('New', new, 'bad'), ('Resolved', fixed, 'good')])
r.section('Status', intro='Every clash test in the model.')
r.bar_chart(statuses, counts, title='Clashes by status', tones=[s.lower() for s in statuses])
rows = [[c['name'], r.status(c['status']), c['distance'], c['grid']] for c in clashes]
r.table(['Name', 'Status', 'Distance', 'Grid'], rows,
        cell_html=set((i, 1) for i in range(len(rows))), max_rows=5000, caption='All clashes')
r.gallery([(c['image_path'], c['name']) for c in clashes[:40]], columns=4)
r.save(path)
```

#### Module functions

| Call | Returns | Behaviour |
|---|---|---|
| `escape(text)` | str | HTML-escapes `& < > " '`, drops control characters; None gives `''`; numbers give their shortest text. Safe in element text and quoted attributes. |
| `format_number(value, decimals=2)` | str | `1234567` gives `'1,234,567'`; floats up to `decimals` places, trailing zeros trimmed; None/NaN/inf/bool give `''`. |
| `status_chip(text, tone=None)` | HTML | The status tag. `tone`: `good`, `warn`, `bad`, `info`, `neutral`, or a clash status `new`, `active`, `reviewed`, `approved`, `resolved`; None derives it from a clash status text, else neutral. Unknown tone raises `ValueError`. |
| `tone_for_status(status)` | tone | Clash status to tone, else `'neutral'`. |
| `link(href, text=None)` | HTML | Escaped anchor; file paths become `file:///` URLs; `javascript:` raises `ValueError`. |
| `file_url(path)` | str | Path to URL (`C:\a b.pdf` gives `file:///C:/a%20b.pdf`); URLs pass through. |
| `TONES`, `SERIES_COLORS` (6) | constants | |

#### Report

| Call | Returns | Behaviour |
|---|---|---|
| `Report(title, subtitle=None, meta=None, toc=None, footer=None, lang='en')` | Report | `meta`: `[(label, value)]` under the title (numbers formatted). `toc`: None shows a contents line when there are 4+ sections. `footer`: None gives "Made with pyNavis Playground", `''` none. |
| `r.kpis(items)` | | `[(label, value, tone)]`, optional 4th item: muted detail line. Large light readout numbers; tone colours the number. |
| `r.section(title, intro=None)` | id `'s1'`.. | Heading with a hairline above, optional muted intro. |
| `r.table(headers, rows, numeric=None, sortable=True, filterable=True, row_tones=None, cell_html=None, caption=None, max_rows=None)` | id `'t1'`.. | Sticky header inside a scroll box (72% of the window tall), click a header to sort (numeric aware, empty cells last, stable), filter box (every word must match), live row count. `numeric`: None auto-detects columns where every non-empty cell is a number or numeric text; or an iterable of column indexes. A numeric column shows every number with the same decimals (0..2). `row_tones`: per-row tone (washed row plus coloured rail). `cell_html`: set of `(row, col)` holding trusted HTML. `max_rows` renders the first N and says "Showing the first N of M rows." No rows shows "No rows.". Cells: bool shows Yes/No, dates ISO, `\n` becomes a line break. |
| `r.bar_chart(labels, values, title=None, horizontal=True, value_format=None, tones=None, value_label='Value')` | id `'c1'`.. | One series, one colour (categorical slot 1); `tones` (per bar) colours bars by status instead. Horizontal: labels left (clipped with an ellipsis), value at each tip. `horizontal=False`: columns with a value axis and gridlines, values on caps when they fit. Missing values draw no bar; negatives draw left/down from zero. |
| `r.line_chart(labels, series, title=None, value_format=None)` | id | `series`: `[(name, values)]` in legend order. First six series get the categorical colours, more draw thin grey and fold into "N more series" in the legend. None leaves a gap. 2px lines, end dots, value axis from zero when sensible, hover crosshair with every series' value. |
| `r.donut(labels, values, title=None, value_format=None, center_label='Total')` | id | Total in the middle, legend table with value and share. More than six categories: the five largest stay, the rest fold into "Other (n)" in grey. Zero/negative/missing values get no slice. |
| `r.heatmap(row_labels, col_labels, matrix, title=None, value_format='{:,}', show_zero=False)` | id | 7-step sequential blue scale (largest value darkest; zero and None unshaded); values printed in cells (0 only with `show_zero`); rotated column labels; scrolls sideways when wide; low/high key. |
| `r.image(path_or_bytes, caption=None, max_width=None, alt=None)` | | Embedded base64 (PNG, JPEG, GIF, BMP, WEBP, SVG), never wider than the page. |
| `r.gallery(items, columns=4)` | | `[(path_or_bytes, caption)]`; 2 columns on narrow screens. Click or Enter opens a full-window viewer: Previous/Next, arrow keys, Esc closes and returns focus. |
| `r.status(text, tone=None)` | HTML | Same as `status_chip`. |
| `r.text(paragraph)` / `r.note(text)` / `r.bullets(items)` | | Escaped paragraph; muted aside with a rule; bulleted list. |
| `r.html(trusted_html)` | | Raw HTML you built and trust. |
| `r.page_break()` | | New page when printed. |
| `r.to_string()` / `r.save(path)` | str / path | UTF-8, atomic. |

**Charts:** every chart ships a collapsed "Data" table beneath it (the accessible and
printable view) and hover tooltips on bars, slices and cells. `value_format`: None
(thousands separators, up to 2 decimals), a format string like `'{:,.1f} m'`, or a
function. Colours: six categorical slots validated for colour vision deficiency in both
themes (light #2A78D6 #D95926 #199E70 #C98500 #D55181 #008300, dark steps of the same
hues), status colours only through `tones`. Labels that are numbers print the same on
both engines (`2026.0` as `2026`).

#### Traps

* Charts render at their natural width (720px) so text stays 12px; they shrink, never
  grow, with the window.
* Pass floats with a fixed-precision `value_format` (`'{:,.2f}'`) when you format them
  yourself: a bare `'{:,}'` prints IronPython's long float repr (`heatmap` guards its own
  default, the other charts default to `format_number`).
* Images are embedded as base64 (+33%): thumbnail big captures first (`namo.images.thumbnail`)
  before putting hundreds in a gallery.
* Use `max_rows` on any table that can grow large: every rendered row is in the file
  and in the page (measured: 5,000 rows build in 0.3 s on IronPython and weigh 0.8 MB).
* Rendering was verified in Chromium (Edge headless, light, dark and print) and the
  script with node; Firefox and Safari were not tested.

---------------------------------------------------------------------------------------

### pdf: minimal PDF writer

Pages with Helvetica / Helvetica-Bold text (WinAnsi; characters outside Windows-1252
print as `?`), real Adobe AFM widths for alignment, wrapping and fitting, lines,
rectangles, clickable link areas, page numbers, JPEG and PNG images. Coordinates are
**millimetres from the top-left corner**. For text, `y` is where the **top of the
capital letters** sits (baseline = y + 0.718 x size in mm), so text and images placed
at the same y line up and `wrap()` returns the y for the next block. Colours:
`(r, g, b)` ints 0..255, floats 0..1 (any float, all <= 1), or `'RRGGBB'`.

```python
from namo import pdf
doc = pdf.Document(size='A4', landscape=True, margin_mm=12, title='Viewpoints', author=user)
for name, image_path in views:
    page = doc.page()
    page.text(page.left, page.top, name, size=16, bold=True, max_width=page.content_width)
    x, y, w, h = page.image(image_path, page.left, page.top + 10, page.content_width,
                            page.content_height - 20, fit=True)
    page.line(page.left, y + h + 3, page.right, y + h + 3, color=(224, 224, 224))
doc.page_numbers()
doc.save(path)
```

| Call | Returns | Behaviour |
|---|---|---|
| `Document(size='A4', landscape=True, margin_mm=12, title=None, author=None, subject=None, created=None, compress=True)` | Document | `size`: a `SIZES` name (case-insensitive) or `(w, h)` mm used exactly. `created` stamps the info dictionary (default now). `compress=False` writes readable content streams. |
| `doc.page(size=None, landscape=None)` | Page | Appended in order; per-page size or orientation allowed. |
| `doc.page_numbers(template='Page {page} of {pages}', size=8, color=(107, 107, 107), align='right', y_mm=None)` | | Drawn on every page at save time, centred in the bottom margin. |
| `doc.pages`, `doc.width`, `doc.height`, `doc.margin` | | |
| `doc.to_bytes()` / `doc.save(path)` | bytes / path | An empty document gets one blank page. Atomic save. |
| `page.left`, `.top`, `.right`, `.bottom`, `.content_width`, `.content_height`, `.width`, `.height` | mm | Margin box. |
| `page.text(x_mm, y_mm, text, size=11, bold=False, color=(0, 0, 0), align='left', max_width=None)` | width mm | One line; `align` 'left' (x is the start), 'center', 'right' (x is the end); newlines become spaces; `max_width` cuts with an ellipsis. |
| `page.wrap(x_mm, y_mm, w_mm, text, size=10, leading=1.3, bold=False, color=(0, 0, 0), align='left', max_lines=None)` | y after | Wraps at spaces, keeps your newlines (blank lines too), splits words longer than the width. Returns `y + lines x line_height`. `max_lines` ends the last kept line with an ellipsis. Empty text returns `y` unchanged. |
| `page.line(x1, y1, x2, y2, width_mm=0.2, color=(0, 0, 0), dash=None)` | | `dash=(on_mm, off_mm)`. |
| `page.rect(x, y, w, h, stroke=(0, 0, 0), fill=None, width_mm=0.2)` | | Top-left corner at (x, y); `stroke=None` for fill only. |
| `page.image(path_or_bytes, x_mm, y_mm, w_mm=None, h_mm=None, fit=False)` | (x, y, w, h) drawn | Give w and/or h; a missing side follows the aspect ratio; both with `fit=True` keeps the aspect inside the box, centred. |
| `page.link(x, y, w, h, url)` | | Clickable area: URL or file path. |
| `text_width(text, size=11, bold=False)` | mm | Exact for what viewers draw (no kerning applied by the writer either). |
| `line_height(size=10, leading=1.3)` | mm | |
| `fit_text(text, width_mm, size=11, bold=False)` | str | Cut with an ellipsis to fit. |
| `wrap_lines(text, width_mm, size=10, bold=False)` | [str] | The lines `wrap()` would draw (for measuring before drawing, e.g. page breaks). |
| `page_size(size='A4', landscape=True)` | (w, h) mm | |
| `SIZES` | dict | Portrait mm: A5, A4, A3, A2, A1, A0, Letter, Legal, Tabloid. |
| `MM`, `ASCENT`, `DESCENT` | constants | Points per mm; Helvetica cap height and descender per unit size. |

**Images:** JPEG is embedded unchanged (grey, RGB, CMYK; Adobe CMYK gets the inverted
`/Decode`; 12-bit JPEG raises `ValueError`). Non-interlaced 1/2/4/8-bit grey, RGB and
palette PNGs without transparency are embedded unchanged too (IDAT plus a PNG
predictor), fast on any engine. PNGs with alpha or tRNS, 16-bit or interlaced are
decoded by `namo.png` (pure Python, see its speed note) and re-compressed; alpha becomes
a soft mask (dropped when fully opaque). The same image bytes on many pages are stored
once. GIF/BMP raise `ValueError`.

**Traps:** no automatic page breaks: measure with `wrap_lines`/`line_height` and call
`doc.page()` yourself. Text outside Windows-1252 (CJK, emoji) prints as `?`; say so in
tool notes for reports that may carry such names. Verified with pypdf (strict mode) and
PyMuPDF (layout, links, pixel-exact images); Acrobat itself was not available.

---------------------------------------------------------------------------------------

### png: tiny PNG codec and image sniffing

Pure `zlib` + `struct`. Encodes 8-bit L/LA/RGB/RGBA and 1-bit images; decodes every
standard PNG (bit depths 1/2/4/8/16, grey, grey+alpha, RGB, RGBA, palette, tRNS, Adam7
interlace) to 8-bit samples; reads sizes from PNG, JPEG, GIF and BMP headers.
Cross-checked against Pillow both ways.

| Call | Returns | Behaviour |
|---|---|---|
| `encode(width, height, pixels, mode='RGB', compress_level=6)` | bytes | `pixels`: flat bytes/bytearray/list of samples (rows top to bottom, channels interleaved), a list of rows, or per-pixel tuples (flat or in rows). `mode`: `'L'`, `'LA'`, `'RGB'`, `'RGBA'`, `'1'` (zero is black, any nonzero sample white). Wrong count or a sample outside 0..255 raises `ValueError`. Filter type 0, not interlaced. |
| `write(path, width, height, pixels, mode='RGB')` | path | |
| `decode(data)` | (w, h, mode, bytes) | `mode` is L, LA, RGB or RGBA; palette becomes RGB (RGBA with tRNS); grey/RGB with a tRNS colour key become LA/RGBA. 16-bit keeps the high byte; low depths scale to 0..255. Critical-chunk CRCs checked; anything broken raises `ValueError`. |
| `read(path)` | as decode | |
| `info(data)` | dict | `width, height, bit_depth, color_type, interlace, mode, transparency` from the header. |
| `size(data)` | (w, h) | PNG only; `ValueError` otherwise. |
| `jpeg_size(data)` / `jpeg_info(data)` | (w, h) / dict | From the start-of-frame marker; info adds `components, bits, progressive, adobe`. |
| `image_size(data)` | (w, h) or None | PNG, JPEG, GIF or BMP. |
| `sniff(data)` | `'png'`, `'jpeg'`, `'gif'`, `'bmp'`, `'webp'`, `'svg'` or None | From the first bytes. |
| `mime_type(data)` | str or None | |
| `idat_stream(data)`, `palette_of(data)` | bytes, (PLTE, tRNS) | Used by `pdf` passthrough. |
| `SIGNATURE` | bytes | |

**Speed:** decoding rows that use the Sub/Average/Paeth filters is a per-byte Python
loop: about 0.35 s per million bytes on IronPython (measured: Paeth-filtered 640x360
RGBA 0.37 s, 1920x1080 RGB 2.1 s). Encoding and filter-0 rows are fast (640x360 RGBA:
0.1 s). Only decode when you need pixels.

## namo data core (F2): paths, config, session, store, docdb, naming, rules, trades, textmatch, ifcguid, templates, reports, dates, units

Everything here is pure stdlib and runs on IronPython 3.4 and CPython 3.11, except the
Navisworks half of `docdb` (lazy `pynavis._api` import) and `dates.to_net` (lazy `System`).
Every module imports cleanly outside Navisworks. Tests: `dev/tests/test_<module>.py`.

Shared conventions:

* **Reads never raise, writes raise `IOError`.** Missing file: the default. Damaged JSON:
  renamed `<file>.corrupt-<YYYYmmdd-HHMMSS>`, logged, the default. A failed write leaves
  the old file untouched and raises `IOError` naming the file; toast it.
* **All writes are atomic** (temp file beside the target, then `os.replace`, with short
  retries for antivirus locks). JSON files are `indent=2`, sorted keys, UTF-8, final newline.
* **Logging:** `session.log(level, message)` writes to the pyNavis log (never opens the output
  window). `session.recent_log()` returns the last 200 lines (tests assert on it).
* **Tests must never touch the real `%APPDATA%`:** call `paths.redirect(folder)` (redirects
  `data_root()` AND the settings file) and restore with `paths.redirect(previous)` in a
  `finally`. Use `docdb.use_backend(docdb.SqliteBackend())` to exercise model mode offline.
* **Never rely on dict order.** Every function that returns a list sorts it (natural order
  for names and ids: 'RFI-9' before 'RFI-10'; see `naming.natural_key`).

---------------------------------------------------------------------------------------

### paths

Where Playground keeps files and how it writes them. `data_root()` is `%APPDATA%\pyNavis\playground`;
`team_root()` is the configured shared folder when set and reachable, else `data_root()`.
Document keys follow `pynavis.memory`'s identity rule exactly (tested against it).

```python
paths.appdata() -> str                       # %APPDATA% (or the redirect folder)
paths.redirect(folder) -> previous_folder    # TEST SEAM: data_root() and config file under folder; None restores
paths.data_root() -> str                     # <appdata>\Playground, created on demand
paths.shared_root() -> str                   # config 'shared_root' stripped, '' when unset
paths.team_available() -> bool               # shared root set AND reachable now
paths.team_root() -> str                     # shared root when reachable, else data_root()
paths.is_reachable(folder) -> bool           # os.path.isdir, cached per session (60 s ok / 15 s not); logs nothing (team_root logs an unreachable share once)
paths.forget_reachability()                  # drop that cache (after the user edits shared_root)
paths.doc_key(doc_path, shared=False) -> str # '<stem, 40 chars>-<sha1[:8]>' of the LOWERCASED full path
                                             #   (shared=True: of the lowercased BASENAME only); ''/None -> 'untitled'
paths.safe_filename(text, max_len=80, replacement='_') -> str
    # Windows-safe: <>:"/\|?* and control chars replaced, runs collapsed, no trailing dots/spaces,
    # CON/PRN/AUX/NUL/COM1-9/LPT1-9 (also 'con.txt') prefixed, cut to max_len keeping a short
    # extension; '' or nothing left -> 'untitled'
paths.unique_path(path) -> str               # path, or 'name (2).ext', 'name (3).ext' ...
paths.ensure_dir(path) -> path               # makedirs when missing (race-safe)
paths.atomic_write_text(path, text, encoding='utf-8', retries=None) -> path   # exact text, no newline translation; retries=1 fails fast (no sleeping retries) for UI-thread callers
paths.atomic_write_bytes(path, data) -> path
paths.read_text(path, default=None) -> str   # UTF-8 (BOM tolerated) or default
paths.load_json(path, default=None, move_aside=True) -> value   # never raises (see conventions)
paths.write_json(path, value) -> path        # atomic; TypeError/ValueError if not serialisable
paths.dumps(value) -> str                    # the JSON text every Playground file uses
paths.quarantine(path) -> new_path or None   # rename to <file>.corrupt-<timestamp>, logged
paths.FileLock(path, timeout=3.0, stale=30.0)    # context manager on '<path>.lock' (O_EXCL)
    # .held says whether it was obtained. After timeout the block RUNS ANYWAY (logged): a
    # stuck lock must never stop a save. Locks older than `stale` seconds are broken.
```

Traps: `team_root()` ignores `data_mode` (templates are team-wide whenever a shared folder
is set); `store` decides per data mode. Probing an offline UNC share can block for seconds;
the cache keeps that to once per 15 s.

### config

Playground-wide settings in one file through `pynavis.settings` (tool key `'playground'`, i.e.
`%APPDATA%\pyNavis\settings\playground.json`). Per-tool options belong in the bundle's own
`script.get_config()`; this holds what several tools share.

```python
config.DEFAULTS = {'user': <Windows USERNAME>, 'project_name': '', 'project_number': '',
    'company': '', 'data_mode': 'local', 'shared_root': '',
    'trades': ['Architecture', 'Structure', 'Mechanical', 'Electrical', 'Plumbing',
               'Fire Protection', 'Civil', 'Unassigned'],
    'trade_rules': [], 'report_units': 'auto', 'date_format': '%Y-%m-%d'}
config.MODES = ('local', 'shared', 'model') ; config.REPORT_UNITS = ('auto', 'mm', 'm', 'ft', 'in')
config.DEFAULT_TRADES ; config.TOOL = 'playground'
config.load() -> dict          # DEFAULTS overlaid with the file, normalised; NEVER raises
config.save(values) -> dict    # writes the given keys (any subset; unknown keys ignored) over the
                               #   current values; returns the saved dict; raises IOError/OSError
config.get(key, default=None)  # one normalised value; default for a non-Playground key
config.user_name() -> str      # config 'user', else Windows user; never empty
config.defaults() -> dict      # deep copy of DEFAULTS
config.normalise(values) -> dict   # bad mode/units -> defaults, trades deduped, trade_rules keep
                                   #   only [regex, trade] pairs that compile, bad date_format -> ISO
config.path() -> str
```

Traps: values are re-read from disk on every call (no cache; module globals reset per run
anyway). Outside the pyNavis runtime an identical built-in reader/writer is used (same
file), so CPython tests work without pynavis on the path.

### session

State that outlives a run, and the shared logger. pyNavis drops every lib module from
`sys.modules` before each run, so module globals are fresh on every click.

```python
session.holder(key) -> module        # sys.modules['playground_' + key], created once per engine life
session.get(key, attr, default=None) # holder(key).attr
session.set(key, attr, value) -> value
session.clear(key) -> bool           # forget a holder
session.keys() -> [key]              # sorted
session.log(level, message)          # 'debug'|'info'|'warning'|'error'; pyNavis log; never raises
session.recent_log(level=None) -> [(level, text)]   # last 200 lines, oldest first
```

Store windows, timers, event handlers and caches on a holder; remember that a handler that
fires later is "outside a run" (use `script.bind()` captured during the run for config).

### store

Per-document and global JSON stores in one of three places (mode None = config `data_mode`):

| mode | doc scope | global scope |
|---|---|---|
| `'local'` | `<data_root>\docs\<doc_key>\<name>.json` | `<data_root>\global\<name>.json` |
| `'shared'` | `<team_root>\docs\<doc_key(shared=True)>\<name>.json` | `<team_root>\global\<name>.json` |
| `'model'` | docdb kv key `'store:<name>'` (inside the NWF/NWD) | never: global stays local |

```python
s = store.Store(name, doc_path=None, scope='doc', mode=None, doc=None)
    # ValueError for an empty name, a scope not 'doc'/'global', a mode not in MODES
s.load(default=None) -> value        # never raises
s.save(value)                        # IOError on failure
s.update(fn, default=None) -> new    # locked read-modify-write; new = fn(current or a COPY of
                                     #   default); fn returning None saves the mutated current value
s.exists() -> bool ; s.delete() -> bool
s.name, s.scope, s.doc_path, s.doc
s.mode    # the EFFECTIVE mode after fallbacks
s.path    # the JSON file (None in model mode) ; s.folder
s.note    # None, or a user-facing sentence when a fallback happened:
          #   'The shared folder is unreachable; using local data.' /
          #   'No shared folder is set in Playground settings; using local data.' /
          #   'Model data is unavailable here; using local data.'   (toast it if it matters)

r = store.RecordStore(name, doc_path=None, scope='doc', mode=None, doc=None)
    # one JSON file per record: <root>\docs\<doc_key>\<name>\<id>.json (or <root>\global\<name>\)
    # model mode: docdb records table, collection = name
r.list() -> [record]          # natural id order; damaged files moved aside and skipped; never raises
r.ids() -> [id]
r.get(id) -> record or None
r.put(record) -> record       # record['id'] required (ValueError); replaces that id; IOError on failure
r.delete(id) -> bool
r.next_number(prefix='') -> int   # 1 + largest trailing number among ids starting with prefix
                                  #   (case-insensitive); 1 when none: ['RFI-001','RFI-007'] -> 8
r.add(record, prefix='', width=3) -> record   # assigns prefix + zero-padded next number under a
                                              #   folder lock (no duplicate numbers across users)
r.folder, r.mode, r.note, r.name, r.scope

store.for_active_doc(name, **kw) -> Store           # doc + file name of the active document (Navisworks)
store.records_for_active_doc(name, **kw) -> RecordStore
store.id_to_filename(id) / store.filename_to_id(filename)   # reversible %XX escaping
store.next_number_of(ids, prefix='') ; store.sort_records(records)
```

Traps: **'shared' keys documents by file NAME**, so two different projects' `Model.nwf` on
the same share share data; that is the price of drive-letter independence. **Record ids are
case-insensitive on disk** ('RFI-1' and 'rfi-1' are one file); keep a consistent case. An
unsaved document is `'untitled'` (shared by all unsaved documents). `update()` on a shared
store holds `<file>.lock` for the duration of `fn`: keep `fn` quick and dialog-free.

### docdb

Playground data INSIDE the document: Navisworks' per-document SQLite (`Document.Database`),
saved with the NWF/NWD. Tables (created on the first write):
`playground_kv(key TEXT PRIMARY KEY, value TEXT, updated TEXT)` and
`playground_records(collection TEXT, id TEXT, value TEXT, updated TEXT, PRIMARY KEY(collection, id))`.
Values are JSON text; `updated` is local ISO time.

```python
docdb.available(doc=None) -> bool              # can the database be read here; never raises
docdb.kv_get(key, default=None, doc=None)      # never raises (default when missing/unreadable)
docdb.kv_set(key, value, doc=None)             # JSON value; IOError on failure; document becomes modified
docdb.kv_delete(key, doc=None) -> bool
docdb.kv_keys(prefix='', doc=None) -> [key]    # sorted, case-sensitive prefix
docdb.records(collection, doc=None) -> [dict]  # natural id order; a dict value gets 'id' (setdefault),
                                               #   other values come back as {'id', 'value'}
docdb.record_get(collection, id, doc=None) -> dict or None
docdb.record_put(collection, id, value, doc=None)    # IOError on failure
docdb.record_delete(collection, id, doc=None) -> bool
docdb.collections(doc=None) -> [name]
# pure helpers (unit tested): SQL_* constants, encode(value), decode(text, default),
#   params(**values) -> [('@name', value)], statement(sql, **values), create_statements(present),
#   filter_keys(keys, prefix), rows_to_records(rows), now_text()
docdb.SqliteBackend(path=':memory:')   # same SQL over Python sqlite3 (tests, offline tools)
docdb.use_backend(backend) -> previous # TEST SEAM; None = the active document
docdb.NavisworksBackend(doc)           # the API half
```

How the API half works (all members grepped in the 2026 dump; **unverified in-app**, see
`dev/notes/foundation-F2.md`): reads build `NavisworksCommand(sql, doc.Database.Value)`, bind
`@name` parameters with `Parameters.AddWithValue`, and fill a `DataTable` through
`NavisworksDataAdapter(command).Fill` (Autodesk's documented read route; it opens/closes the
connection itself), falling back to `ExecuteReader` on an explicitly opened connection.
Writes run in `doc.Database.BeginTransaction(DatabaseChangedAction.Edited)`, `Commit()`, with
`Rollback()` on any error; missing tables are created first in a separate
`DatabaseChangedAction.Reset` transaction. Parameterised SQL only (`@name`), `INSERT OR
REPLACE` upserts (works on old SQLite too; tested on 3.7.7 and 3.45).

Traps: writes are NOT undoable (no `EnableTableUndoable`); do not call docdb inside an open
`viewpoints.transaction()` (untested nesting); the user must SAVE the NWF/NWD for the data to
persist; data in an NWD travels to everyone who opens it.

### naming

Name templates for files, viewpoints, sets, tests: `'{test} - {n:000}'`, `'{date:%Y%m%d}'`.

```python
naming.render(template, values, counter=None) -> (text, missing_tokens)
    # {name} or {name:spec}; names are letters/digits/_/. (matched case-insensitively when
    # there is no exact key). spec: all zeros pads a number ('{n:000}' -> 007); a strftime
    # pattern for dates/times (text that reads as a date is parsed); any Python format spec
    # (',', '.2f', '.0%', '>8'). Unknown tokens stay as written and are listed (order, no dups).
    # '{{' and '}}' are braces; a lone brace is text. counter fills {n} unless values has 'n'.
    # Defaults without spec: date 2026-10-05, time 1430, datetime '2026-10-05 1430', True 'Yes',
    # 2.0 '2', None ''.
naming.tokens(template) -> [names]               # first-appearance order, no duplicates
naming.standard_values(doc=None) -> dict         # date, time, datetime (objects), year, month, day
    # (zero-padded text), user, project, project_number, company (config), file (document
    # file stem), title. Without Navisworks/document: file and title are ''.
naming.unique(name, existing, pattern='{name} ({n})') -> name   # case-insensitive; n from 2
naming.sanitize(text, for_file=False) -> str     # control chars/newlines -> space, long dashes
    # -> '-', spaces collapsed, trimmed; for_file=True then paths.safe_filename
naming.natural_key(text) -> tuple                # sort key: 'Level 2' < 'Level 10', case-insensitive
naming.format_value(value, spec=None) -> str     # one token's formatting
```

### rules

One condition engine for every rule-driven tool. A condition is
`{'category', 'property', 'op', 'value', 'ignore_case'}` (`'prop'` accepted for `'property'`).

```python
rules.OPS   # ordered [(op, label, needs_value)]: equals, not_equals, contains, not_contains,
            #   starts_with, ends_with, wildcard, regex, gt, ge, lt, le, between ([lo, hi]),
            #   in_list ([...]), exists, missing, empty, not_empty   (labels are lowercase UI text)
rules.OP_NAMES ; rules.LABELS ; rules.NEEDS_VALUE ; rules.SYMBOLS ; rules.OP_ALIASES
rules.evaluate(cond, exists, value) -> bool
rules.matches(conds, getter, mode='all') -> bool   # getter(category, property) -> (exists, value),
    # called once per distinct pair; a raising getter = missing property; 'all' (True when empty)
    # or 'any' (False when empty)
rules.to_number(value) -> float or None   # number at the START: '12.5 m' 12.5, '1,234' 1234,
                                          #   '3.2 ft' 3.2; bool/None -> None
rules.text_of(value) -> str               # None '', True 'Yes', 3.0 '3', 2.5 '2.5', text trimmed
rules.describe(cond) -> 'Element > Category = Ducts'     # parse_cell() reads it back
rules.validate(cond) -> [sentence]                       # [] when fine
rules.parse_cell(text) -> cond            # ValueError (readable) when no comparison is found
rules.normalise(cond) -> cond ; rules.op_of(spelling) -> op or None
rules.as_list(value) ; rules.bounds(value) -> (lo, hi) ; rules.wildcard_regex(pattern, ignore_case)
rules.native_ops() -> [op]
rules.native_plan(conds, mode='all', numbers_as_text=False, max_groups=4) -> groups or None  # pure
rules.native_query(conds, mode='all', numbers_as_text=False, max_groups=4) -> sets Builder or None
```

Semantics (identical everywhere): `ignore_case` defaults True; text compares trimmed values.
**Every value operator is False when the property does not exist** (like Find Items); use
`missing`. `empty` = missing OR blank; `not_empty` = present and not blank. `equals`,
`not_equals`, `in_list` compare as numbers when BOTH sides read entirely as numbers ('3' equals
3.0 and '3.000'), else as text; booleans match yes/no/true/false/1/0. `gt/ge/lt/le/between`
use `to_number` on both sides (a side without a number makes it False). `wildcard`: `*` and
`?`, whole value. `regex`: `re.search`; a bad pattern is False (validate reports it).
`category ''` means "any category" for getters that support it.

`parse_cell` forms: `Element > Category = Ducts`, `Item > Name contains PIPE`, `Level >= 3`
(category ''), `Element > Mark is empty`, `... exists`, `... is missing`, `... is not empty`,
`... like P-*`, `... matches ^P\d+` (or `/.../`), `... between 1 and 3`, `... is one of A, B`
(`;` separates when values contain commas), `... starts with`, `... ends with`,
`... does not contain`, `!=`/`<>`, `(match case)` at the end. Quote names or values that
contain operator words: `Element > "Phase is" = "a = b"`.

native_query: returns a `pynavis.sets.query()` Builder (run with `sets.run(builder)` /
`sets.find_first`) or None when Python must decide: regex, not_contains, empty, not_empty, a
blank category, no conditions, starts/ends_with values containing `* ? [ ] #`, or more than
`max_groups` OR groups (each is a full model walk; `in_list` expands to one group per value).
**Trap:** equals/not_equals/in_list with number-like values return None unless
`numbers_as_text=True`, because native matching compares display strings: right for text
properties such as `Element ID > Value`, wrong for Int32/Double properties that `evaluate`
would match. Native matching is by display names. Unverified in-app: that DisplayString
wildcard/contains/NotEqual behave exactly like `evaluate` (see notes).

### trades

Trade from a model / source file name.

```python
trades.DEFAULT_RULES        # ordered [(regex, trade)], case-insensitive, searched in the BASENAME
trades.UNASSIGNED = 'Unassigned'
trades.trade_of(name, rules=None) -> trade or 'Unassigned'   # first matching rule wins; memoised
trades.explain(name, rules=None) -> (trade, pattern or None)
trades.rules_from_config(cfg=None) -> [(regex, trade)]       # config trade_rules first, then defaults
trades.classify(names, rules=None) -> {name: trade}
trades.basename_of(name) -> lowercased file name
```

Order of DEFAULT_RULES: discipline words (fire protection/sprinkler, plumb/sanitary/drainage,
mech/hvac/duct, elec/lighting/power/cable tray, struct/steel/rebar/foundation,
arch/interior/facade, civil/landscape/topo/site), then standalone codes (FP FPS SPK, PL PLG,
ME MEC MCH HV MV, EL ELV LT LV, STR STRU ST, AR ARC ARCHI, CIV), then a single-letter prefix
at the very START (`A-`, `S_`, `M `, `E.`, `P-`, `F-`, `C-`). Combined `MEP` models and
mid-name letters ('Tower A', 'Block C') stay Unassigned on purpose; users add
`trade_rules` such as `['\\bmep\\b', 'Mechanical']`.

### textmatch

Fuzzy matching for Quick Find, the Command Palette and filter boxes.

```python
textmatch.score(query, text) -> float      # 0.0 = no match; empty query 0.0
textmatch.rank(query, items, key=None, limit=50) -> [(score, item)]   # best first, ties keep
    # input order; limit None/0 = all; empty query = first `limit` items with score 0.0
textmatch.spans(query, text) -> [(start, end)]   # merged ranges to highlight; [] when no match
textmatch.Index(items, key=None).rank(query, limit=50)   # texts lowercased once (per keystroke use)
```

Each query word (split on spaces) must match as an ordered subsequence, case-insensitively;
all words must match (any order) and their scores add. fzf v1 scoring on three alignments
(best contiguous occurrence, tightest subsequence, word-start/acronym): word starts after
space or `- _ . / \ > :` etc., CamelCase humps and digit runs score high; consecutive runs,
prefix and exact match add bonuses; gaps cost a little (capped, so any match is > 0); longer
texts lose up to 1 point. Measured: 20,000 items, short query: 70 to 150 ms on IronPython
(harness, loaded machine), 30 to 50 ms on CPython (`test_speed_20000_items`). Use `Index`
when the same list is ranked on every keystroke.

### ifcguid

```python
ifcguid.compress(uuid_text) -> 22-char GlobalId      # hyphens/braces/urn:uuid:/case optional; ValueError
ifcguid.expand(ifc) -> '8-4-4-4-12' lowercase         # ValueError when not valid
ifcguid.is_valid(text) -> bool                        # 22 chars of 0-9A-Za-z_$, first 0..3
ifcguid.new() -> random GlobalId
ifcguid.revit_export_guid(unique_id) -> guid text     # episode GUID with last 8 hex XOR element id
ifcguid.from_revit_unique_id(unique_id) -> GlobalId   # compress(revit_export_guid(...))
ifcguid.ALPHABET
```

Vectors: zero GUID -> `0000000000000000000000`, all-F -> `3$$$$$$$$$$$$$$$$$$$$$`; packing
cross-checked against the revit-ifc `ConvertToIFCGuid` byte layout. Trap: an element whose
Revit `IfcGUID` parameter was set carries that value; prefer the property when present.

### templates

Named saved configurations per tool, team-shared when a shared folder is set.

```python
t = templates.Templates(tool_id)        # file <team_root>\templates\<tool_id>.json ; ValueError for ''
t.names() -> [name]                     # natural, case-insensitive order
t.get(name) -> config copy or None      # exact name, else case-insensitive
t.info(name) -> {'name', 'updated', 'user'} or None
t.save(name, config) -> stored_name     # name sanitised; replaces same name in any case;
                                        #   ValueError for empty name / non-dict config
t.delete(name) -> bool
t.rename(old, new) -> new               # ValueError: old missing, new empty, new taken
t.export(path, names=None) -> count     # portable file; unknown names skipped
t.import_file(path, replace=False) -> count   # clashes become 'Name (2)' unless replace;
    # ValueError (sentence) for a missing/unreadable/foreign/other-tool file; never moves it aside
templates.all_tools() -> [tool_id]      # tools with at least one template in the current team root
templates.folder() ; t.path ; t.tool_id
```

File body: `{"format": "playground-templates", "version": 1, "tool": ..., "templates":
{name: {"config": {...}, "updated": ISO, "user": ...}}}`. Every change is a locked
read-modify-write. Trap: switching `shared_root` on or off changes which templates a user
sees (local ones are not merged in).

### reports

> A cancelled run returns `{'level': 'info', 'message': 'Report cancelled', 'cancelled': True, ...}`. Interactive callers check `result.get('cancelled')` and exit with NO toast (cancel is silent).

The fixed registry of automation-ready reports plus shared helpers.

```python
reports.REGISTRY      # [(id, title, module)], exactly the 22 entries below, in this order
reports.ids() ; reports.entry(id) -> (id, title, module) ; reports.title_of(id)   # KeyError if unknown
reports.module_exists(id) -> bool             # lib\namo\rep_<id>.py exists (no import)
reports.module_for(id) -> module              # KeyError unknown id, ImportError not built / broken
reports.available() -> [(id, title)]          # modules that exist, registry order
reports.run(id, config, doc=None, interactive=False, progress=None) -> result
    # config is merged OVER module.default_config(); NEVER raises: unknown id, missing module,
    # crash (logged with traceback) and cancel all come back as results; adds 'report',
    # 'title', 'seconds'
reports.output_path(config, default_name, ext, values=None, unique=False) -> path
    # folder: config['folder'] (%VARS% and ~ expanded) or <data_root>\reports, created;
    # name: config['name_template'] (default '{report} {date}') rendered with
    # naming.standard_values() + {'report': default_name} + values, sanitised; ext with or
    # without the dot; unique=True -> ' (2)' instead of overwriting
reports.base_config(**extra) -> {'folder': '', 'name_template': '{report} {date}', ...}
reports.default_config(id) ; reports.describe(id, config=None) -> str (title on failure)
reports.result(level, message, detail='', paths=None) -> result dict
reports.normalise_result(value) -> result dict
reports.Cancelled         # raise it (or any exception class named Cancelled) to stop
reports.LEVELS = ('success', 'info', 'warning', 'error') ; reports.MODULE_DIR (test seam)
```

| id | title | module |
|---|---|---|
| property_export | Property Export | rep_property_export |
| model_tree | Model Tree Export | rep_model_tree |
| count_by_property | Count by Property | rep_count_by_property |
| data_validation | Data Validation | rep_data_validation |
| clash_excel | Clash Excel Report | rep_clash_excel |
| clash_html | Clash HTML Dashboard | rep_clash_html |
| clash_matrix | Clash Count Matrix | rep_clash_matrix |
| clash_delta | Clash Delta | rep_clash_delta |
| clash_trends | Clash Trends | rep_clash_trends |
| per_trade | Per-Trade Reports | rep_per_trade |
| coordination | Coordination Report | rep_coordination |
| kpi_export | KPI Export | rep_kpi_export |
| health_check | Model Health Check | rep_health_check |
| session_stats | Session Stats | rep_session_stats |
| stale_files | Stale File Alert | rep_stale_files |
| preflight | Preflight Checks | rep_preflight |
| timeliner_export | TimeLiner Export | rep_timeliner_export |
| schedule_health | Schedule Health | rep_schedule_health |
| quick_takeoff | Quick Takeoff | rep_quick_takeoff |
| zone_takeoff | Zone Takeoff | rep_zone_takeoff |
| viewpoint_images | Viewpoints to Images | rep_viewpoint_images |
| batch_pdf | Batch PDF Printer | rep_batch_pdf |

#### The rep_<id>.py contract (every report tool implements it)

```python
# lib\namo\rep_clash_excel.py
"""Clash Excel Report: one workbook per run, a sheet per clash test."""
from namo import reports

TITLE = 'Clash Excel Report'               # same as REGISTRY


def default_config():
    """JSON-serialisable; ALWAYS includes 'folder' and 'name_template'."""
    return reports.base_config(tests=[], statuses=['New', 'Active'], images=False)


def describe(config):
    """One line for Report Templates / Scheduled Reports lists."""
    return '%d tests, %s' % (len(config['tests']), ', '.join(config['statuses']))


def run(config, doc=None, interactive=True, progress=None):
    """interactive=False: NO dialogs, prompts, windows or toasts (pynavis run, schedules,
    macros). Decide every option from config; report problems in the result instead.
    progress(fraction 0..1, label) may be None: call it only `if progress:`.
    Raise reports.Cancelled (or let namo.items.Cancelled through) to stop."""
    path = reports.output_path(config, TITLE, 'xlsx')
    ...                                     # write the file (namo.xlsx etc.)
    return reports.result('success', 'Wrote 3 sheets', path, paths=[path])
    # {'level': 'success'|'info'|'warning'|'error', 'message': str, 'detail': str,
    #  'paths': [files written]}
```

Rules: `run` receives the merged config (defaults + caller's keys), may receive `doc=None`
(meaning the active document), and must not toast or open the file itself when
`interactive=False` (the caller decides). The ribbon `script.py` gathers options (dialog or
`script.get_config`), calls `reports.run(id, config, interactive=True, progress=...)` and
toasts `result['message']` / `result['detail']`. Keep nothing in module globals.

### dates

```python
dates.parse(value, day_first=True) -> datetime or None    # never raises; naive LOCAL time
    # ISO (2026-10-05, 2026/10/05, 2026-10-05 14:30, 2026-10-05T14:30:00.123Z: zones converted
    # to local), compact 20261005[T143000], d/m/y or m/d/y (a part over 12 decides, else
    # day_first), 2-digit years 1970..2069, month names (5 Oct 2026, 05-Oct-2026,
    # October 5, 2026, Mon 5 Oct 2026), times with seconds and am/pm, Excel serial numbers
    # (int/float 1..2958465; number-only TEXT only in 20000..80000), datetime/date objects,
    # .NET DateTime (anything with Year/Month/Day)
dates.iso(value, date_only=False) -> 'YYYY-MM-DDTHH:MM:SS' | 'YYYY-MM-DD' | ''
dates.now() ; dates.today() -> datetime at 00:00
dates.add_days(value, n) -> datetime or None
dates.days_between(a, b) -> int or None      # calendar days b - a (times ignored)
dates.age_bucket(days, buckets=(7, 14, 30)) -> '0-7 days' | '8-14 days' | '15-30 days' | 'Over 30 days'
                                             #   (negative -> first band, None -> 'Unknown')
dates.bucket_labels(buckets=(7, 14, 30)) -> [labels in order]
dates.format(value, fmt=None) -> str         # fmt default: config date_format; '' when unparseable
dates.week_start(value) -> Monday 00:00 or None
dates.from_excel(serial) ; dates.to_excel(value)
dates.from_net(net) -> datetime or None      # UTC kind converted to local; MinValue (year 1) -> None
dates.to_net(value) -> System.DateTime (Local kind) or None   # needs .NET
```

### units

```python
units.DOC_UNIT_METERS   # {'Meters':1.0,'Centimeters':0.01,'Millimeters':0.001,'Feet':0.3048,'Inches':0.0254,
                        #  'Yards':0.9144,'Kilometers':1000,'Micrometers':1e-6,'Microinches':2.54e-8,
                        #  'Mils':2.54e-5,'Miles':1609.344}   keys = str(doc.Units)
units.to_meters(value, doc_units) ; units.from_meters(value_m, doc_units)   # doc names or length aliases;
                                                                           #   ValueError when unknown
units.KINDS = ('length', 'area', 'volume', 'mass') ; units.BASE ; units.UNITS {symbol: (kind, SI factor)}
units.ALIASES {unit_key: symbol} ; units.unit_key(text) ; units.resolve(text) -> symbol or None
units.kind_of(text) -> kind or None
units.convert(value, from_unit, to_unit) -> float   # any aliases; ValueError across kinds/unknown;
                                                    #   rounded to 12 significant digits (24 in = 2.0 ft)
units.parse_quantity(text) -> (value, unit, kind) or None   # bare number -> (value, None, None)
units.parse_conversion(text) -> (value, from_unit, to_unit) or None
units.convert_text(text) -> (value, to_unit)        # ValueError with a sentence for a toast
units.format(value, unit, decimals=2, ascii=False) -> '1,250.00 mm' / '3.50 m²'
units.symbol(unit, ascii=False) ; units.DISPLAY
units.parse_number(text) -> float or None ; units.split_number(text) -> (value, rest)
units.parse_length(text, doc_units) -> float or None      # pure port of pynavis.lengths.parse
units.format_length_input(value, doc_units, denominator=16)   # pure port of format_input
units.format_feet_inches(feet, denominator=16) -> "12' 6 1/2\""
units.is_imperial(doc_units) ; units.doc_unit_symbol(doc_units) -> 'ft' | 'mm' | ...
units.report_units_for(report_units, doc_units) -> {'length', 'area', 'volume'}   # metric: m2/m3,
                                                                                  #   imperial: ft2/ft3
```

Canonical symbols: length m mm cm km um in ft yd mi mil uin; area m2 mm2 cm2 km2 ha in2 ft2
yd2 ac; volume m3 mm3 cm3 l ml in3 ft3 yd3 gal (US) gal_uk; mass kg g t (tonne) lb oz ton (US
short ton). Aliases ignore case, spaces, dots and `^`, read superscripts as digits: m², sq m,
sqm, SF, sq ft, ft², CF, cu ft, cuyd, CY, L, litres, gal(US), gal (UK), lbs, tonnes...
`parse_quantity` tries "number + one unit" first (so `250 ft2` is an area, not 250 ft 2 in),
then feet-and-inches (`12' - 6 1/2"`, `12'6"`, `6 1/2"`, `2 ft 3 in`). Numbers: `1,234` and
`1 234` are thousands, `12,5` and `0,250` decimal commas, `1.234,5` / `1,234.5` both work.
`parse_conversion` separators: ` to `, ` in `, ` into `, ` as `, `->`, `=>`, `=` (the last one
that leaves a quantity on the left and a unit on the right wins: `5 in in mm`). Trap:
`parse_length` keeps the pynavis rules exactly (negative lengths refused, the `1 6` space form
only in imperial documents); use `parse_quantity` for signed values.

## namo, F3 Navisworks core: items, clashdata, camera, images, colors, paint, mesh, ui

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

### items: walking, identifying, measuring and showing model items

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

### clashdata: one reader for every clash tool

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

### camera: the camera, saved viewpoints and section planes as data

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

### images: images of the model

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

### colors (pure) and paint (API)

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

### mesh (pure) + one triangle source

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

### ui: WPF building blocks themed by the pyNavis design system

Colours come from `PyNavis.Runtime.Forms.DesignSystem.Tokens.Current` (light/dark
following Navisworks) plus the Windows accent, used only on the primary button,
selection rails, checked boxes and focus rings. Segoe UI Variable 13 px, 32 px controls
and rows, 8 px gaps, 24 px padding (16 px in data-dense windows), solid surfaces. Every
window is owned by Navisworks (`FluentChrome.Apply`) when shown; modal ones refuse to
open under `pynavis run` (RuntimeError, same message as pynavis.forms: check
`__runner__` first). Keyboard: Tab order follows the layout, Enter = primary, Esc =
cancel, Ctrl+F = filter, Space ticks rows, Down from a filter box enters the table.

#### Ready-made windows

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

#### Tables

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

#### Parts for custom windows

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

#### Plumbing

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

## Tool modules, by panel group

Each group's build notes (what every tool does, its in-app checks) are in `dev
otes\<group>.md`. Module docstrings are the contract; this index is their first line.

### Select & Find (Model)

| Module | Purpose |
|---|---|
| `find_batch` |  |
| `find_library` |  |
| `find_query` |  |
| `find_repair` |  |
| `find_sets` |  |
| `hk_pickorder` |  |
| `hk_selhistory` |  |
| `quickfind` |  |
| `sel_history` |  |
| `sel_pickorder` |  |
| `selecttools` |  |
| `setexchange` |  |
| `setwizard` |  |

### Inspect & Data (Model)

| Module | Purpose |
|---|---|
| `data_common` |  |
| `data_explorer` |  |
| `data_labels` |  |
| `data_write` |  |
| `hud` |  |
| `insp_propsplus` |  |
| `inspect` |  |
| `propindex` |  |
| `propwrite` |  |
| `rep_count_by_property` |  |
| `rep_data_validation` |  |
| `rep_model_tree` |  |
| `rep_property_export` |  |
| `validator` |  |

### Look (Model)

| Module | Purpose |
|---|---|
| `colorize` |  |
| `explode` |  |
| `hk_presentation` |  |
| `legend` |  |
| `look_ghost` |  |
| `look_status` |  |
| `look_tools` |  |
| `presentation` |  |

### Views (Views)

| Module | Purpose |
|---|---|
| `camsync` |  |
| `capture` |  |
| `dxf` |  |
| `hk_camsync` |  |
| `levels` |  |
| `rep_batch_pdf` |  |
| `rep_viewpoint_images` |  |
| `sheetoverlay` |  |
| `spotter` |  |
| `vp_common` |  |
| `vp_sync` |  |
| `vp_ui` |  |
| `vp_whereami` |  |
| `vpbatch` |  |
| `vpexcel` |  |
| `vpexport` |  |

### Clash Setup & Results (Coordinate)

| Module | Purpose |
|---|---|
| `clashassign` |  |
| `clashheat` |  |
| `clashmatrix` |  |
| `clashname` |  |
| `clashres_views` |  |
| `clashrules` |  |
| `clashset_common` |  |
| `clashset_tests` |  |
| `clashtemplates` |  |
| `revitlink` |  |
| `scanvsmodel` |  |

### Clash Reports (Coordinate)

| Module | Purpose |
|---|---|
| `clashrep_forms` |  |
| `clashrep_history` |  |
| `clashrep_out` |  |
| `clashrep_svg` |  |
| `clashreport` |  |
| `hk_clashhistory` |  |
| `rep_clash_delta` |  |
| `rep_clash_excel` |  |
| `rep_clash_html` |  |
| `rep_clash_matrix` |  |
| `rep_clash_trends` |  |
| `rep_per_trade` |  |

### Issues & BCF (Coordinate)

| Module | Purpose |
|---|---|
| `bcf` |  |
| `bcf_exchange` | BCF Export and BCF Import: issues (or clash results) to a .bcfzip and back. |
| `hk_issuepins` |  |
| `issue_clash` |  |
| `issue_meeting` |  |
| `issue_stamps` |  |
| `issue_templates` |  |
| `issueapi` |  |
| `issues` |  |
| `issuestore` |  |
| `issueui` |  |
| `rep_coordination` |  |
| `rep_kpi_export` |  |

### Models, Quality, Publish (Project)

| Module | Purpose |
|---|---|
| `duplicates` |  |
| `folderwatch` |  |
| `health` |  |
| `hk_folderwatch` |  |
| `hk_sessionstats` |  |
| `hk_stalecheck` |  |
| `hk_transformpresets` |  |
| `mdl_output` |  |
| `mdl_stats` |  |
| `modelcompare` |  |
| `modelmgmt` |  |
| `preflight` |  |
| `publish` |  |
| `rep_health_check` |  |
| `rep_preflight` |  |
| `rep_session_stats` |  |
| `rep_stale_files` |  |
| `sourcefiles` |  |
| `transforms` |  |
| `wipe` |  |

### 4D, Quantities, Field (Project)

| Module | Purpose |
|---|---|
| `checklists` |  |
| `cog` |  |
| `field_checklistwin` |  |
| `field_photobrowser` |  |
| `field_qr` |  |
| `fourd_attach` |  |
| `fourd_common` |  |
| `fourd_progress` |  |
| `fourd_ui` |  |
| `hk_photopins` |  |
| `movie` |  |
| `photopins` |  |
| `qr` |  |
| `qty_run` |  |
| `qty_ui` |  |
| `rep_quick_takeoff` |  |
| `rep_schedule_health` |  |
| `rep_timeliner_export` |  |
| `rep_zone_takeoff` |  |
| `takeoff` |  |
| `timeliner` |  |

### Exchange & Reports (Project / Dev)

| Module | Purpose |
|---|---|
| `ifc` |  |
| `ifcexport` |  |
| `meshexport` |  |
| `reportrunner` |  |
| `sched_mail` |  |
| `sched_ui` |  |
| `schedule` |  |
| `xchg_common` |  |

### Dev & Team (Dev)

| Module | Purpose |
|---|---|
| `buttonmaker` |  |
| `converter` |  |
| `doctor` |  |
| `editor` |  |
| `extmanager` |  |
| `hk_macro` |  |
| `hk_teamsync` |  |
| `hk_usage` |  |
| `hotkeys` |  |
| `macros` |  |
| `palette` |  |
| `ribbon` |  |
| `team_settings` |  |
| `teamsync` |  |
| `usage` |  |

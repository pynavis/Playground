# namo documents: xlsx, htmlreport, pdf, png (foundation F1)

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

## xlsx: styled Excel writer

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

### Module functions and classes

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

### Worksheet

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

### Built-in styles

`cell` (plain, index 0), `header` (bold, F2F2F2 fill, A6A6A6 bottom border, centred
vertically), `title` (bold 14), `muted` (6B6B6B text), `bold`, `center`, `int` (#,##0),
`num1` (#,##0.0), `num2` (#,##0.00), `pct` (0%), `pct1` (0.0%), `date` (yyyy-mm-dd),
`datetime` (yyyy-mm-dd hh:mm), `time` (hh:mm), `good`/`warn`/`bad`/`info` (soft wash
plus readable text), `link` (0563C1 underlined), `wrap` (wrap, top aligned), and the
Navisworks clash status colours softened to washes: `status_new` (red), `status_active`
(orange), `status_reviewed` (blue), `status_approved` (green), `status_resolved` (yellow).

### Traps

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

## htmlreport: standalone HTML report

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

### Module functions

| Call | Returns | Behaviour |
|---|---|---|
| `escape(text)` | str | HTML-escapes `& < > " '`, drops control characters; None gives `''`; numbers give their shortest text. Safe in element text and quoted attributes. |
| `format_number(value, decimals=2)` | str | `1234567` gives `'1,234,567'`; floats up to `decimals` places, trailing zeros trimmed; None/NaN/inf/bool give `''`. |
| `status_chip(text, tone=None)` | HTML | The status tag. `tone`: `good`, `warn`, `bad`, `info`, `neutral`, or a clash status `new`, `active`, `reviewed`, `approved`, `resolved`; None derives it from a clash status text, else neutral. Unknown tone raises `ValueError`. |
| `tone_for_status(status)` | tone | Clash status to tone, else `'neutral'`. |
| `link(href, text=None)` | HTML | Escaped anchor; file paths become `file:///` URLs; `javascript:` raises `ValueError`. |
| `file_url(path)` | str | Path to URL (`C:\a b.pdf` gives `file:///C:/a%20b.pdf`); URLs pass through. |
| `TONES`, `SERIES_COLORS` (6) | constants | |

### Report

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

### Traps

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

## pdf: minimal PDF writer

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

## png: tiny PNG codec and image sniffing

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

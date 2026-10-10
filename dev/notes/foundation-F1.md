# Foundation F1: Documents (xlsx, htmlreport, pdf, png)

## 1. What was built

* `lib/namo/png.py`: pure PNG encoder (L, LA, RGB, RGBA, 1-bit) and decoder (every
  standard PNG: depths 1..16, palette, tRNS, Adam7) plus PNG/JPEG/GIF/BMP size and
  format sniffing.
* `lib/namo/xlsx.py`: styled Excel writer (named styles, number formats, widths,
  heights, merged titles, frozen panes, autofilter, web/file/in-workbook links,
  formulas, PNG/JPEG pictures with one-cell or move-and-size anchors, `write_simple`).
* `lib/namo/htmlreport.py`: standalone themed HTML report (KPI readouts, sections,
  sortable/filterable tables with tones and trusted cells, SVG bar/column/line/donut/
  heatmap charts with tooltips and data tables, images, gallery with viewer, status
  chips, print stylesheet).
* `lib/namo/pdf.py`: minimal PDF writer (pages, Helvetica text with AFM metrics,
  alignment, wrapping, fitting, lines, rects, links, page numbers, JPEG and PNG images
  with passthrough where possible, soft masks for alpha).
* `lib/namo/README-F1.md`: every public function with signature, return and
  behaviour, plus traps.
* Tests: `dev/tests/test_png.py`, `test_xlsx.py`, `test_htmlreport.py`, `test_pdf.py`.

## 2. Deviations from FOUNDATION.md (all additive; no contract name or parameter changed)

* **Golden digests.** Each test file holds one digest that BOTH engines must match, so
  the writers are proven byte-identical on CPython and IronPython (IronPython's float
  repr is not shortest, `0.1` prints `0.10000000000000001`; every number we write goes
  through a shortest-round-trip formatter). Change output on purpose: update the
  constant after checking both engines agree (`python <file>` under CPython and the
  IronPython harness print the same digest).
* **xlsx** additions: `Workbook(title, author, created)`, `style(..., base, font,
  border_color, border_style, indent)`, `ws.subtitle`, `ws.skip`, `ws.cell`,
  `ws.autofit`, `ws.tab_color`, `ws.used_range`, `ws.header_row`,
  `autofilter(first_col, last_col)`, `image(offset_px, fit_cell, description, anchor)`
  returning `(w, h)`, helpers `col_letter`, `cell_ref`, `range_ref`, `quote_sheet`,
  `sanitize_sheet_name`, `status_style`, `excel_serial`, px conversions, built-ins
  `cell`, `bold`, `center`, `pct1`, `time`. `write()` also advances `next_row`.
  `columns()` third element is the column's default cell style (the contract left
  its meaning open). Image default stays `oneCellAnchor` per the contract, but
  `anchor='cell'` (twoCellAnchor) exists because measured in Excel only it hides
  pictures with rows a filter hides: clash-report tools should use it for row
  thumbnails.
* **htmlreport** additions: `Report(toc, footer, lang)`, `bullets`, `page_break`,
  `status(text, tone=None)` (tone optional, derived from clash status text), clash
  statuses accepted as tones, chart options `value_format`, `tones`, `value_label`,
  `center_label`, `show_zero`, `image(alt)`, module `format_number`, `status_chip`,
  `tone_for_status`, `link`, `file_url`. Chart colours are NOT the pyNavis output
  window palette (its chart-1 is the accent, which the brief reserves for links and
  focus): six validated categorical hues instead (CVD-checked with the dataviz
  validator in both themes, all at least 3:1 against the page).
* **pdf**: text `y` is the top of the capitals (the contract said only "y from top";
  this makes text and images at the same y align and lets `wrap()` return the next
  y). PNG images are passed through (IDAT plus PNG predictor) when they are
  non-interlaced 8-bit-or-less grey/RGB/palette without transparency, instead of
  always decoding: same pixels (verified pixel-exact with PyMuPDF), far faster on
  IronPython. Others decode through png.py as specified. Additions: `subject`,
  `created`, `compress`, per-page size, `page_numbers`, `page.link`, `text(max_width)`,
  `wrap(bold, color, align, max_lines)`, `image(fit)` returning the drawn box,
  `line(dash)`, `text_width`, `fit_text`, `wrap_lines`, `line_height`, `page_size`,
  more `SIZES` (A5, A2, A1, A0, Legal).
* **png**: decode reads more than the contract's "8-bit non-interlaced" (all depths,
  Adam7, tRNS); palette images come back as RGB/RGBA. Additions: `read`, `info`,
  `jpeg_info`, `image_size`, `sniff`, `mime_type`, `idat_stream`, `palette_of`,
  `encode(compress_level)`.

## 3. Verified headlessly (this machine)

* Tests: CPython 84 passed (png 16, xlsx 29, htmlreport 23, pdf 16). IronPython 70
  passed, 14 skipped (png 12+4, xlsx 22+7, htmlreport 22+1, pdf 14+2): the skips are
  the third-party cross-checks (openpyxl, Pillow, pypdf, PyMuPDF, node), CPython only
  by design. `python dev/verify.py`: pytest, IronPython compile/tests/smoke and the
  BundleParser pass; check.py reports only the 25 expected empty tab/panel layouts,
  none in these files.
* Files written by IronPython and by CPython for the same calls are byte-identical
  (xlsx, html, pdf compared by md5), and openpyxl/pypdf read the IronPython-written ones.
* Excel 16.0.20430 by automation (invisible, read-only, alerts off): demo, test sample,
  `write_simple` and a 20,000-row IronPython-written workbook open with no repair, with
  the expected pictures, hyperlinks, autofilter, frozen panes, merges, fills and
  formats. Negative control: a workbook with one element out of schema order fails to
  open the same way, so a clean open means no repair was needed.
* Excel filter behaviour: `anchor='cell'` thumbnails hide with filtered rows (9 of 12
  hidden); `anchor='one'` thumbnails stay visible (0 of 12 hidden).
* HTML rendered in headless Edge in light, dark and print; table sort (numeric,
  natural text, both directions, empties last), filter (all words), row count, bar
  tooltips, line crosshair, gallery viewer (arrows, Esc, focus return) driven by
  script; inline script passes `node --check`. Print found and fixed a Chromium quirk
  (button text blank in repeated table headers).
* PDF read by pypdf in strict mode and PyMuPDF: page count and order, sizes, metadata,
  text, link URI, right-aligned text ending at the margin (AFM widths match the
  viewer's font), and JPEG/RGB/palette/RGBA PNG images pixel-exact.
* Speed on IronPython: xlsx 200,000 cells 3.0 s; HTML table 5,000 rows 0.3 s; PDF 20
  pages with images 0.2 s; PNG encode 640x360 RGBA 0.1 s; PNG decode Paeth-filtered
  640x360 RGBA 0.37 s, 1920x1080 RGB 2.1 s.

Demo files (throwaway): `%TEMP%\playground-f1-demo\` holds `demo.xlsx` (status-coloured
table, `anchor='cell'` PNG thumbnails made with png.py, heatmap sheet, links, unicode
sheet), `demo-one.xlsx` (same with one-cell anchors), `sample.xlsx`, `simple.xlsx`,
`demo-report.html` (every component), `demo.pdf` (3 pages), and the light/dark/print
screenshots.

## 4. Checklist for a human (things only a person can confirm)

1. Open `%TEMP%\playground-f1-demo\demo.xlsx` in Excel by double-click: no repair prompt;
   status cells readable in their washes; thumbnails sit inside column G; filter
   Status to "New" and confirm the other thumbnails disappear; sort by Distance and
   confirm thumbnails travel with their rows (sorting was not automated).
2. In the same workbook, click a "Open" web link, the "Open the demo PDF" file link on
   the "Notes draft" sheet (Excel may show a security notice for file links), and the
   "Back to the clash list" in-workbook link.
3. Open `demo-report.html` in Edge with Windows set to dark, then light: colours swap,
   charts stay readable; Tab reaches the filter box, header sort buttons and gallery
   images with a visible focus ring; Ctrl+P preview shows a light page with table
   headers repeated on each page.
4. Open the same HTML in Firefox if available (only Chromium was tested).
5. Open `demo.pdf` in Acrobat Reader: no warnings, title bar shows the document title,
   the link at the bottom of page 1 opens a browser, page numbers read "Page n of 3".

## 5. Requests for shared modules I do not own

* F3 `namo.colors.STATUS`: my clash status colours (Navisworks convention, softened)
  are New red, Active orange, Reviewed blue, Approved green, Resolved yellow, in
  `xlsx.BUILTIN_STYLES` (washes) and htmlreport CSS (chips). Please align
  `colors.STATUS` hues with these, or tell the lead to align mine, so a status looks
  the same in the model, Excel and HTML.
* F3 `namo.images`: for images headed into PDFs, prefer JPEG or 24-bit RGB PNG (no
  alpha): those embed instantly; RGBA PNG must be decoded in pure Python
  (`System.Drawing` saves 32bpp ARGB bitmaps as RGBA PNG).
* Lead: merge `README-F1.md` into `lib/namo/README.md`.

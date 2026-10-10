# -*- coding: utf-8 -*-
"""Regenerates every Playground ribbon icon. Dev-time CPython + Pillow only, never shipped.

    python dev/make_icons.py                      write every bundle's icons
    python dev/make_icons.py --sheet sheet.png    also write a contact sheet
    python dev/make_icons.py --only clash         only glyph modules whose name contains 'clash'

The drawing language is pyNavis' own (tools\\make_icons.py of a pyNavis checkout is
imported, not copied): a 0..96 canvas drawn at 4x, neutral ink draws the THING, a solid
accent mark draws the ACTION, rounded caps, one stroke weight per density. The small
32 px files are separate simplified drawings (Ctx.small is True, the stroke is heavier),
never resized copies. Alert red appears exactly once in Playground: Model Wipe.

Glyphs live in dev/icons/<group>.py, one module per panel owner, each exposing:

    ICONS = {'Model.tab/Select.panel/Select_Similar.pushbutton': draw_fn, ...}
    TOGGLES = {'<bundle path>.toggle': (off_fn, on_fn)}          # optional
    DOCKPANE_ON = {'<bundle path>.dockpane': on_fn}             # optional

draw_fn(c) receives a pyNavis Ctx (c.line, c.circle, c.disc, c.rrect, c.poly, c.arrow_v,
c.t['ink'|'accent'|'alert'|'paper'], c.small). Shared marks (tray, spark, plus, dots,
eye, brackets, sight, gauge...) come from `pn` (the pyNavis generator module).
Never hand-edit a PNG: change the glyph and re-run.
"""
import argparse
import glob
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXT = os.path.join(ROOT, 'Playground.extension')
# A pyNavis checkout: PYNAVIS_SRC, else a 'pyNavis' folder beside this repo.
PYNAVIS_TOOLS = os.path.join(os.environ.get('PYNAVIS_SRC') or os.path.join(os.path.dirname(ROOT), 'pyNavis'), 'tools')

sys.path.insert(0, PYNAVIS_TOOLS)
import make_icons as pn  # noqa: E402  (pyNavis' generator: Ctx, THEMES, render, marks)

from PIL import Image, ImageDraw  # noqa: E402


def load_groups(only=None):
    groups = []
    for path in sorted(glob.glob(os.path.join(HERE, 'icons', '*.py'))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name.startswith('_') or (only and only not in name):
            continue
        spec = importlib.util.spec_from_file_location('playground_icons_' + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        groups.append((name, module))
    return groups


def _folder(bundle):
    return os.path.join(EXT, bundle.replace('/', os.sep))


def write_all(groups):
    missing = []
    for name, module in groups:
        for table in ('ICONS', 'TOGGLES', 'DOCKPANE_ON'):
            for bundle in getattr(module, table, {}):
                if not os.path.isdir(_folder(bundle)):
                    missing.append('%s: %s' % (name, bundle))
    if missing:
        raise SystemExit('bundle folder(s) missing:\n  ' + '\n  '.join(sorted(missing)))

    written = bundles = 0
    for name, module in groups:
        for bundle, fn in sorted(getattr(module, 'ICONS', {}).items()):
            folder = _folder(bundle)
            for suffix, theme in pn.THEMES:
                pn.render(fn, theme, False).png(pn.LARGE_PX).save(os.path.join(folder, 'icon%s.png' % suffix))
                pn.render(fn, theme, True).png(pn.SMALL_PX).save(os.path.join(folder, 'icon.small%s.png' % suffix))
                written += 2
            bundles += 1
        for bundle, (off_fn, on_fn) in sorted(getattr(module, 'TOGGLES', {}).items()):
            folder = _folder(bundle)
            for suffix, theme in pn.THEMES:
                pn.render(off_fn, theme, False).png(pn.LARGE_PX).save(os.path.join(folder, 'icon%s.png' % suffix))
                pn.render(off_fn, theme, False).png(pn.LARGE_PX).save(os.path.join(folder, 'icon.off%s.png' % suffix))
                pn.render(on_fn, theme, False).png(pn.LARGE_PX).save(os.path.join(folder, 'icon.on%s.png' % suffix))
                pn.render(off_fn, theme, True).png(pn.SMALL_PX).save(os.path.join(folder, 'icon.small%s.png' % suffix))
                written += 4
            bundles += 1
        for bundle, on_fn in sorted(getattr(module, 'DOCKPANE_ON', {}).items()):
            folder = _folder(bundle)
            for suffix, theme in pn.THEMES:
                pn.render(on_fn, theme, False).png(pn.LARGE_PX).save(os.path.join(folder, 'icon.on%s.png' % suffix))
                written += 1
    print('done: %d bundles, %d files' % (bundles, written))


def write_sheet(groups, path):
    entries = []
    for name, module in groups:
        for bundle, fn in sorted(getattr(module, 'ICONS', {}).items()):
            entries.append((bundle, fn))
        for bundle, (off_fn, on_fn) in sorted(getattr(module, 'TOGGLES', {}).items()):
            entries.append((bundle + ' off', off_fn))
            entries.append((bundle + ' on', on_fn))
        for bundle, on_fn in sorted(getattr(module, 'DOCKPANE_ON', {}).items()):
            entries.append((bundle + ' on', on_fn))
    cols = 3
    rows = (len(entries) + cols - 1) // cols
    cell_w, cell_h = 520, 60
    img = Image.new('RGB', (cell_w * cols, 20 + rows * cell_h), (243, 243, 243))
    d = ImageDraw.Draw(img)
    for i, (bundle, fn) in enumerate(entries):
        x0 = (i % cols) * cell_w
        y = 10 + (i // cols) * cell_h
        label = bundle.rsplit('/', 1)[-1]
        d.text((x0 + 10, y + 20), label[:34], fill=(60, 60, 60))
        img.paste(Image.new('RGB', (150, 56), (31, 31, 31)), (x0 + 350, y - 4))
        for x, theme in ((x0 + 230, pn.LIGHT), (x0 + 360, pn.DARK)):
            big = pn.render(fn, theme, False).png(48)
            img.paste(big, (x, y), big)
            sm = pn.render(fn, theme, True).png(16)
            img.paste(sm, (x + 62, y + 16), sm)
    img.save(path)
    print('sheet: %s (%d glyphs)' % (path, len(entries)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sheet', help='also write a contact sheet here')
    ap.add_argument('--sheet-only', action='store_true', help='write only the contact sheet')
    ap.add_argument('--only', help='only glyph modules whose file name contains this')
    args = ap.parse_args()
    groups = load_groups(args.only)
    if not args.sheet_only:
        write_all(groups)
    if args.sheet:
        write_sheet(groups, args.sheet)


if __name__ == '__main__':
    main()

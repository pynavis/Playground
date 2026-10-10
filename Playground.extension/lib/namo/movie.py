# -*- coding: utf-8 -*-
"""4D Movie Maker: a self-driven construction sequence rendered frame by frame.

No TimeLiner playback API is needed: each frame date gives every attached item a state
from its tasks' dates and types, the model is set to those states (hidden flags plus
TEMPORARY colour overrides), the view is rendered with Document.GenerateImage, the date
is stamped on the frame, and the frames become PNG files, a standalone HTML player and,
when ffmpeg is on PATH, an MP4. ffmpeg is never required.

States (pure, state_at):
    construct  before start: hidden   during: building (green)     after end: normal
    demolish   before start: normal   during: demolishing (red)    after end: hidden
    temporary  before start: hidden   during: temporary (yellow)   after end: hidden
An item in several tasks follows the task that started most recently (a column built
by one task and demolished by a later one goes hidden, green, normal, red, hidden).

Restoring (API half, always, even on cancel or error): the hidden state is captured
BEFORE anything changes as every item whose own IsHidden flag is set; at the end
ResetAllHidden() then SetHidden(those, True) puts it back exactly (the same exact
restore pynavis.viewstate's Paste Hidden Items uses). Colours are only ever TEMPORARY
overrides on the items the movie tinted, reset with ResetTemporaryMaterials(tinted);
permanent colours are never touched. The camera is a CreateCopy() put back with
CopyFrom. All model changes run inside ONE transaction, so the movie is one undo step
whose net effect is nothing.
"""

import datetime
import json
import os
import shutil

STATES = ('hidden', 'normal', 'building', 'demolishing', 'temporary')
TINTS = {'building': '59A14F', 'demolishing': 'E15759', 'temporary': 'EDC948'}
STATE_LABELS = {'hidden': 'Not built', 'normal': 'Complete', 'building': 'In progress',
                'demolishing': 'Being demolished', 'temporary': 'Temporary works'}
KINDS = ('construct', 'demolish', 'temporary')
MAX_FRAMES = 2000
UNIT_DAYS = {'days': 1, 'weeks': 7}
SIZES = [('1280 x 720', (1280, 720)), ('1920 x 1080', (1920, 1080)), ('2560 x 1440', (2560, 1440)),
         ('3840 x 2160', (3840, 2160))]
FRAME_NAME = 'frame_%04d.png'
# All frame changes inside one Document transaction (one undo step, net effect nothing).
# UNVERIFIED that GenerateImage sees changes made inside an open transaction: if the
# frames come out identical in Navisworks, set this False (changes then apply one by one).
ONE_TRANSACTION = True


def task_kind(type_name):
    """'construct', 'demolish' or 'temporary' from a TimeLiner task type name (custom
    names containing 'demol'/'remov' or 'temp' count too; anything else builds)."""
    text = (type_name or '').strip().lower()
    if 'demol' in text or 'remov' in text:
        return 'demolish'
    if 'temp' in text:
        return 'temporary'
    return 'construct'


def task_window(row, basis='planned'):
    """(start, end) of a task for the movie, or None when it has no start.

    basis 'planned' uses the planned dates; 'actual' uses actual dates where they exist
    and planned ones elsewhere. A missing end is the start (an instant)."""
    if basis == 'actual':
        start = row.get('actual_start') or row.get('start')
        end = row.get('actual_end') or row.get('end')
    else:
        start, end = row.get('start'), row.get('end')
    if start is None:
        start = end
    if start is None:
        return None
    if end is None or end < start:
        end = start
    return (start, end)


def state_for(kind, phase):
    if kind == 'demolish':
        return {'before': 'normal', 'during': 'demolishing', 'after': 'hidden'}[phase]
    if kind == 'temporary':
        return {'before': 'hidden', 'during': 'temporary', 'after': 'hidden'}[phase]
    return {'before': 'hidden', 'during': 'building', 'after': 'normal'}[phase]


def normalise_schedule(schedule):
    """Sorted list of (start, end, kind): by start, then end, then kind."""
    return sorted(schedule, key=lambda s: (s[0], s[1], KINDS.index(s[2]) if s[2] in KINDS else 9))


def state_at(schedule, when):
    """The state of an item on `when` from its sorted schedule (see the module doc)."""
    if not schedule:
        return 'normal'
    latest = None
    for entry in schedule:
        if entry[0] <= when:
            latest = entry
        else:
            break
    if latest is None:
        return state_for(schedule[0][2], 'before')
    start, end, kind = latest
    return state_for(kind, 'during' if when < end else 'after')


def frame_dates(start, end, step=1, unit='days', limit=MAX_FRAMES):
    """Frame dates from start to end inclusive, every step days or weeks; the last frame
    is always `end`. Raises ValueError for a bad range or more than limit frames."""
    if start is None or end is None:
        raise ValueError('The movie needs a start and an end date.')
    if end < start:
        raise ValueError('The end date is before the start date.')
    days = int(step) * UNIT_DAYS.get(unit, 1)
    if days < 1:
        raise ValueError('The step must be at least one day.')
    out = []
    current = start
    delta = datetime.timedelta(days=days)
    while current < end:
        out.append(current)
        if len(out) > limit:
            raise ValueError('That makes more than %s frames; use a longer step.' % '{:,}'.format(limit))
        current = current + delta
    out.append(end)
    if len(out) > limit:
        raise ValueError('That makes more than %s frames; use a longer step.' % '{:,}'.format(limit))
    return out


def count_frames(start, end, step=1, unit='days'):
    """How many frames frame_dates would make (no list built)."""
    if start is None or end is None or end < start:
        return 0
    days = max(1, int(step) * UNIT_DAYS.get(unit, 1))
    span = (end - start).total_seconds() / 86400.0
    whole = int(span // days)
    exact = abs(span - whole * days) < 1e-9
    return whole + (1 if exact else 2)


def plan_frames(schedules, dates_):
    """For each frame date: (index, date, changes, counts).

    schedules: {key: sorted schedule}. changes: {state: [keys]} - every key on the first
    frame, then only the keys whose state changed. counts: {state: n} for the frame."""
    try:
        keys = sorted(schedules)
    except TypeError:
        keys = list(schedules)          # ModelItems: order inside a change list is irrelevant
    current = {}
    for index, when in enumerate(dates_):
        changes = {}
        counts = dict((s, 0) for s in STATES)
        for key in keys:
            state = state_at(schedules[key], when)
            counts[state] += 1
            if current.get(key) != state:
                changes.setdefault(state, []).append(key)
                current[key] = state
        yield index, when, changes, counts


def active_tasks(windows, when):
    """Names of tasks under way on `when` ([(start, end, kind, name)])."""
    return [w[3] for w in windows if w[0] <= when < w[1]]


def stamp_lines(when, active, fmt='%Y-%m-%d', weekday=True):
    """(headline, detail) for the frame stamp: '2026-10-05  Mon', '3 tasks under way:
    Level 2 slab, ...'."""
    headline = when.strftime(fmt)
    if weekday:
        headline += '  ' + when.strftime('%a')
    if not active:
        detail = 'No task under way'
    else:
        names = ', '.join(sorted(active)[:3])
        more = len(active) - 3
        detail = '%d %s under way: %s%s' % (len(active), 'task' if len(active) == 1 else 'tasks',
                                            names, ' and %d more' % more if more > 0 else '')
    return headline, detail


# ---- the HTML player ------------------------------------------------------------------------

_PLAYER = u"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
:root{--bg:#F3F3F3;--surface:#FFFFFF;--ink:#1B1B1B;--muted:#616161;--line:#E0E0E0;--accent:#005FB8;}
@media (prefers-color-scheme:dark){:root{--bg:#202020;--surface:#2B2B2B;--ink:#F3F3F3;--muted:#ABABAB;--line:#3A3A3A;--accent:#4CC2FF;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif}
header{padding:16px 24px 8px}
h1{font-size:20px;font-weight:600;margin:0}
.sub{color:var(--muted);margin-top:2px}
main{padding:8px 24px 24px}
.stage{background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:8px}
.stage img{display:block;width:100%%;height:auto;border-radius:2px}
.bar{display:flex;align-items:center;gap:8px;margin-top:12px;flex-wrap:wrap}
button,select{height:32px;min-width:32px;padding:0 12px;border:1px solid var(--line);border-radius:4px;background:var(--surface);color:var(--ink);font:inherit;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#FFFFFF;min-width:72px}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
input[type=range]{flex:1;min-width:160px;accent-color:var(--accent)}
.date{font-variant-numeric:tabular-nums;font-weight:600;min-width:120px}
.count{color:var(--muted);font-variant-numeric:tabular-nums;min-width:90px;text-align:right}
.detail{color:var(--muted);margin-top:6px;min-height:19px}
footer{color:var(--muted);padding:0 24px 24px;font-size:12px}
</style></head><body>
<header><h1>%(title)s</h1><div class="sub">%(subtitle)s</div></header>
<main>
<div class="stage"><img id="frame" alt="Frame" src="%(first)s"></div>
<div class="bar">
<button id="prev" title="Previous frame (Left)" aria-label="Previous frame">&#9664;</button>
<button id="play" class="primary" title="Play or pause (Space)">Play</button>
<button id="next" title="Next frame (Right)" aria-label="Next frame">&#9654;</button>
<span class="date" id="date"></span>
<input type="range" id="slider" min="0" max="%(last)d" value="0" aria-label="Frame">
<span class="count" id="count"></span>
<select id="speed" aria-label="Frames per second">%(speeds)s</select>
</div>
<div class="detail" id="detail"></div>
</main>
<footer>Made with pyNavis Playground. Space plays or pauses, the arrow keys step, Home and End jump.</footer>
<script>
var frames=%(frames)s;var i=0,timer=null;
var img=document.getElementById('frame'),slider=document.getElementById('slider');
var play=document.getElementById('play'),speed=document.getElementById('speed');
var cache=[];
function preload(n){if(n<frames.length&&!cache[n]){var p=new Image();p.src=frames[n].file;cache[n]=p;}}
function show(n){i=Math.max(0,Math.min(frames.length-1,n));var f=frames[i];img.src=f.file;
slider.value=i;document.getElementById('date').textContent=f.date;
document.getElementById('count').textContent=(i+1)+' of '+frames.length;
document.getElementById('detail').textContent=f.detail||'';preload(i+1);preload(i+2);}
function stop(){if(timer){clearInterval(timer);timer=null;}play.textContent='Play';}
function start(){if(i>=frames.length-1){show(0);}stop();play.textContent='Pause';
timer=setInterval(function(){if(i>=frames.length-1){stop();return;}show(i+1);},1000/parseFloat(speed.value));}
play.onclick=function(){timer?stop():start();};
document.getElementById('prev').onclick=function(){stop();show(i-1);};
document.getElementById('next').onclick=function(){stop();show(i+1);};
slider.oninput=function(){stop();show(parseInt(slider.value,10));};
speed.onchange=function(){if(timer){start();}};
document.addEventListener('keydown',function(e){if(e.target.tagName==='SELECT'){return;}
if(e.key===' '){e.preventDefault();timer?stop():start();}
else if(e.key==='ArrowLeft'){stop();show(i-1);}else if(e.key==='ArrowRight'){stop();show(i+1);}
else if(e.key==='Home'){stop();show(0);}else if(e.key==='End'){stop();show(frames.length-1);}});
show(0);
</script></body></html>
"""


def _escape(text):
    from namo import htmlreport
    return htmlreport.escape(text)


def player_html(title, frames, subtitle='', fps=4):
    """A standalone HTML player for frames [{'file', 'date', 'detail'}] (files relative
    to the HTML), with play/pause, a slider, speed and keyboard control, light and
    dark themes."""
    if not frames:
        raise ValueError('There are no frames to play.')
    speeds = []
    for value in (1, 2, 4, 8, 12, 24):
        speeds.append('<option value="%d"%s>%d fps</option>'
                      % (value, ' selected' if value == int(fps) else '', value))
    payload = json.dumps([{'file': f['file'], 'date': f.get('date', ''), 'detail': f.get('detail', '')}
                          for f in frames], sort_keys=True).replace('</', '<\\/')
    return _PLAYER % {'title': _escape(title), 'subtitle': _escape(subtitle),
                      'first': _escape(frames[0]['file']), 'last': len(frames) - 1,
                      'speeds': ''.join(speeds), 'frames': payload}


def find_ffmpeg():
    """The ffmpeg executable on PATH, or None."""
    try:
        return shutil.which('ffmpeg')
    except Exception:
        return None


def ffmpeg_command(exe, folder, fps, output):
    """Arguments for an H.264 MP4 from folder/frame_%04d.png (even dimensions forced,
    yuv420p so every player opens it)."""
    return [exe, '-y', '-loglevel', 'error', '-framerate', str(int(fps)),
            '-i', os.path.join(folder, 'frame_%04d.png'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-movflags', '+faststart', output]


# =============================================================================================
# API half
# =============================================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def gather(rows, basis='planned', doc=None, tick=None):
    """What the movie animates, read from timeliner.snapshot rows.

    Returns {'schedules': {ModelItem: sorted schedule}, 'windows': [(start, end, kind,
    name)], 'tasks': tasks used, 'no_dates': tasks with items but no dates,
    'empty': tasks whose attachment resolved to nothing}. tick(done, total) per task."""
    from namo import timeliner
    document = _doc(doc)
    schedules = {}
    windows = []
    used = no_dates = empty = 0
    total = len(rows)
    for index, row in enumerate(rows):
        if tick is not None and tick(index, total) == False:   # noqa: E712
            from namo.items import Cancelled
            raise Cancelled()
        if (row.get('attach_kind') or 'none') == 'none' or not row.get('enabled', True):
            continue
        window = task_window(row, basis)
        if window is None:
            no_dates += 1
            continue
        collection = timeliner.selected_items(row['task'], document)
        if collection is None or not collection.Count:
            empty += 1
            continue
        kind = task_kind(row.get('type'))
        entry = (window[0], window[1], kind)
        for item in collection:
            schedules.setdefault(item, []).append(entry)
        windows.append((window[0], window[1], kind, row.get('name') or ''))
        used += 1
    for item in list(schedules):
        schedules[item] = normalise_schedule(schedules[item])
    return {'schedules': schedules, 'windows': windows, 'tasks': used, 'no_dates': no_dates,
            'empty': empty}


def hidden_items(doc=None, tick=None):
    """Every item whose OWN hidden flag is set (native DescendantsAndSelf walk of each
    model root): the state restore() puts back exactly."""
    from namo import items as _items
    document = _doc(doc)
    ticker = _items.Ticker(tick)
    out = []
    for root in _items.roots(document):
        for item in root.DescendantsAndSelf:
            ticker.step()
            if item.IsHidden:
                out.append(item)
    ticker.finish()
    return out


class SceneKeeper(object):
    """with SceneKeeper(doc, hidden_before) as keeper: ... restores hidden flags, the
    temporary colours the block added (keeper.tinted) and the camera on exit, however
    the block ends. Never raises on exit; problems are logged."""

    def __init__(self, doc, hidden_before):
        self.doc = _doc(doc)
        self.hidden_before = list(hidden_before)
        self.tinted = set()
        self.viewpoint = None
        self.restored = False

    def __enter__(self):
        self.viewpoint = self.doc.CurrentViewpoint.CreateCopy()
        return self

    def restore(self):
        from namo import items as _items
        from namo import session
        models = self.doc.Models
        try:
            models.ResetAllHidden()
            if self.hidden_before:
                models.SetHidden(_items.collection(self.hidden_before), True)
        except Exception as error:
            session.log('error', 'movie: hidden state not restored: %s' % error)
        try:
            if self.tinted:
                models.ResetTemporaryMaterials(_items.collection(list(self.tinted)))
        except Exception as error:
            session.log('error', 'movie: temporary colours not reset: %s' % error)
        try:
            if self.viewpoint is not None:
                self.doc.CurrentViewpoint.CopyFrom(self.viewpoint)
        except Exception as error:
            session.log('error', 'movie: camera not restored: %s' % error)
        self.restored = True

    def __exit__(self, exc_type, exc, tb):
        if not self.restored:
            self.restore()
        return False


def apply_changes(doc, changes, keeper):
    """Puts the items of one frame's changes into their states (bulk calls only)."""
    from namo import items as _items
    from namo import paint
    models = _doc(doc).Models
    show = []
    for state in ('normal', 'building', 'demolishing', 'temporary'):
        show.extend(changes.get(state, []))
    if show:
        models.SetHidden(_items.collection(show), False)
    untint = list(changes.get('normal', [])) + list(changes.get('hidden', []))
    untint = [item for item in untint if item in keeper.tinted]
    if untint:
        models.ResetTemporaryMaterials(_items.collection(untint))
        for item in untint:
            keeper.tinted.discard(item)
    for state in ('building', 'demolishing', 'temporary'):
        group = changes.get(state, [])
        if group:
            models.OverrideTemporaryColor(_items.collection(group), paint.nw_color(TINTS[state]))
            keeper.tinted.update(group)
    hide = changes.get('hidden', [])
    if hide:
        models.SetHidden(_items.collection(hide), True)


def stamp(bitmap, headline, detail, fraction):
    """Draws the date stamp and a timeline bar on a System.Drawing bitmap in place."""
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import (Color, Font, FontStyle, Graphics, GraphicsUnit, RectangleF,
                                SolidBrush)
    from System.Drawing.Drawing2D import SmoothingMode
    from System.Drawing.Text import TextRenderingHint
    width, height = bitmap.Width, bitmap.Height
    unit = max(8.0, height / 36.0)
    graphics = Graphics.FromImage(bitmap)
    try:
        graphics.SmoothingMode = SmoothingMode.AntiAlias
        graphics.TextRenderingHint = TextRenderingHint.AntiAliasGridFit
        big = Font('Segoe UI Semibold', float(unit * 1.15), FontStyle.Regular, GraphicsUnit.Pixel)
        small = Font('Segoe UI', float(unit * 0.62), FontStyle.Regular, GraphicsUnit.Pixel)
        pad = unit * 0.9
        text_w = max(graphics.MeasureString(headline, big).Width,
                     graphics.MeasureString(detail, small).Width)
        box_w = min(width - 2 * pad, text_w + 2 * pad)
        box_h = unit * 2.9
        left, top = pad, height - pad - box_h
        brushes = [SolidBrush(Color.FromArgb(255, 32, 32, 32)), SolidBrush(Color.FromArgb(255, 255, 255, 255)),
                   SolidBrush(Color.FromArgb(255, 200, 200, 200)), SolidBrush(Color.FromArgb(255, 64, 64, 64)),
                   SolidBrush(Color.FromArgb(255, 0, 120, 212))]
        panel, white, grey, track, accent = brushes
        graphics.FillRectangle(panel, RectangleF(float(left), float(top), float(box_w), float(box_h)))
        graphics.DrawString(headline, big, white, float(left + pad), float(top + unit * 0.35))
        graphics.DrawString(detail, small, grey, float(left + pad), float(top + unit * 1.75))
        bar_h = max(3.0, unit * 0.18)
        graphics.FillRectangle(track, RectangleF(0.0, float(height - bar_h), float(width), float(bar_h)))
        graphics.FillRectangle(accent, RectangleF(0.0, float(height - bar_h),
                                                  float(width * max(0.0, min(1.0, fraction))), float(bar_h)))
        for brush in brushes:
            brush.Dispose()
        big.Dispose()
        small.Dispose()
    finally:
        graphics.Dispose()


def render(doc, path, width, height, headline, detail, fraction):
    """GenerateImage of the current view, stamped, saved as PNG (namo.images)."""
    from namo import images
    document = _doc(doc)
    bitmap = document.GenerateImage(images.style_enum('scene'), int(width), int(height), True)
    if bitmap is None:
        raise RuntimeError('Navisworks returned no image for the current view')
    try:
        stamp(bitmap, headline, detail, fraction)
    except Exception as error:
        from namo import session
        session.log('warning', 'movie: frame not stamped: %s' % error)
    return images.save_bitmap(bitmap, path)


def make(doc, rows, options, report):
    """Renders the movie. options: {'basis', 'start', 'end', 'step', 'unit', 'width',
    'height', 'folder', 'title', 'viewpoint' (SavedViewpoint or None), 'show_unscheduled',
    'mp4', 'fps', 'date_format'}. report(fraction, label) drives the progress window (it
    raises to cancel). Returns {'frames', 'folder', 'html', 'mp4', 'items', 'tasks',
    'no_dates', 'empty', 'mp4_note'}."""
    from namo import camera, items as _items, paths, session
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    report(0.0, 'Reading the schedule')
    found = gather(rows, options.get('basis', 'planned'), document,
                   tick=lambda done, total: report(0.05 * done / float(total or 1), 'Reading tasks'))
    schedules = found['schedules']
    result = {'frames': 0, 'folder': options['folder'], 'html': None, 'mp4': None,
              'items': len(schedules), 'tasks': found['tasks'], 'no_dates': found['no_dates'],
              'empty': found['empty'], 'mp4_note': None}
    if not schedules:
        return result
    dates_ = frame_dates(options['start'], options['end'], options.get('step', 1),
                         options.get('unit', 'days'))
    report(0.05, 'Recording what is hidden now')
    hidden_before = hidden_items(document, tick=lambda done, total: report(0.08, 'Recording what is hidden now'))
    folder = paths.ensure_dir(options['folder'])
    frames = []
    width, height = int(options.get('width', 1920)), int(options.get('height', 1080))
    fmt = options.get('date_format') or '%Y-%m-%d'
    span = float(len(dates_) - 1 or 1)
    group = transaction('Make 4D movie', document) if ONE_TRANSACTION else _no_transaction()
    with group:
        with SceneKeeper(document, hidden_before) as keeper:
            saved = options.get('viewpoint')
            if saved is not None:
                camera.apply(camera.from_viewpoint(saved.Viewpoint), document)
            if not options.get('show_unscheduled', True):
                others = _items.complement(list(schedules), document)
                if others:
                    document.Models.SetHidden(_items.collection(others), True)
            for index, when, changes, counts in plan_frames(schedules, dates_):
                report(0.1 + 0.85 * index / span, 'Frame %s of %s, %s'
                       % ('{:,}'.format(index + 1), '{:,}'.format(len(dates_)), when.strftime(fmt)))
                apply_changes(document, changes, keeper)
                headline, detail = stamp_lines(when, active_tasks(found['windows'], when), fmt)
                path = os.path.join(folder, FRAME_NAME % (index + 1))
                render(document, path, width, height, headline, detail, index / span)
                frames.append({'file': FRAME_NAME % (index + 1), 'date': headline, 'detail': detail})
            keeper.restore()
    result['frames'] = len(frames)
    title = options.get('title') or '4D sequence'
    subtitle = '%s to %s, %s frames, %s' % (dates_[0].strftime(fmt), dates_[-1].strftime(fmt),
                                             '{:,}'.format(len(frames)),
                                             'actual dates' if options.get('basis') == 'actual'
                                             else 'planned dates')
    html_path = os.path.join(folder, 'index.html')
    paths.atomic_write_text(html_path, player_html(title, frames, subtitle, options.get('fps', 4)))
    result['html'] = html_path
    if options.get('mp4', True):
        exe = find_ffmpeg()
        if exe is None:
            result['mp4_note'] = 'No MP4: ffmpeg is not on PATH.'
        else:
            result['mp4'] = _encode(exe, folder, options.get('fps', 4), title, report)
            if result['mp4'] is None:
                result['mp4_note'] = 'ffmpeg could not make the MP4; the log has its message.'
    session.log('info', 'movie: %d frames in %s' % (len(frames), folder))
    return result


class _no_transaction(object):
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def _encode(exe, folder, fps, title, report):
    import subprocess
    import time
    from namo import naming, session
    output = os.path.join(folder, naming.sanitize(title, for_file=True) + '.mp4')
    command = ffmpeg_command(exe, folder, fps, output)
    report(0.96, 'Encoding the MP4 with ffmpeg')
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as error:
        session.log('warning', 'movie: ffmpeg did not start: %s' % error)
        return None
    try:
        while process.poll() is None:
            report(0.97, 'Encoding the MP4 with ffmpeg')
            time.sleep(0.2)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
        raise
    if process.returncode != 0:
        try:
            message = process.stderr.read()
        except Exception:
            message = ''
        session.log('warning', 'movie: ffmpeg failed (%s): %s' % (process.returncode, message))
        return None
    return output if os.path.exists(output) else None

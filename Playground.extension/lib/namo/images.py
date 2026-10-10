# -*- coding: utf-8 -*-
"""Images of the model: the current view, saved viewpoints, clash results, thumbnails.

THE image route is Document.GenerateImage(ImageGenerationStyle, width, height,
enableSectioning) (and DocumentClashTests.TestsImageForResult for a clash), both
returning a System.Drawing.Bitmap. save_bitmap() writes it as PNG, JPEG (quality via
EncoderParameters, which GDI+ only honours as an Int64) or BMP, picked from the file
extension, through a temporary file so a failed write never leaves half an image,
and ALWAYS disposes the bitmap (GDI+ memory is not reclaimed by the Python side).

pynavis.export.viewpoint_image is an unverified COM guess; do not use it.

STYLES maps our names to ImageGenerationStyle member NAMES ('Scene',
'ScenePlusOverlay', 'SceneUsingRayTrace'); style_enum() resolves them, so this module
imports without Navisworks.

Batch exports wrap their loop in ViewKeeper, which puts the camera (and the saved
viewpoint that was current) back afterwards.
"""

import os

STYLES = {
    'scene': 'Scene',
    'overlay': 'ScenePlusOverlay',
    'raytrace': 'SceneUsingRayTrace',
}

FORMATS = {
    '.png': 'png',
    '.jpg': 'jpeg',
    '.jpeg': 'jpeg',
    '.bmp': 'bmp',
}

MAX_SIDE = 8000


# ---- pure ----------------------------------------------------------------------


def format_for(path):
    """'png' | 'jpeg' | 'bmp' from the file extension; ValueError otherwise."""
    ext = os.path.splitext(str(path))[1].lower()
    if ext not in FORMATS:
        raise ValueError('images are saved as .png, .jpg or .bmp, not %r' % (ext or path))
    return FORMATS[ext]


def clamp_quality(quality):
    """JPEG quality as an int 1..100 (90 for anything unreadable)."""
    try:
        q = int(round(float(quality)))
    except (TypeError, ValueError):
        return 90
    return 1 if q < 1 else 100 if q > 100 else q


def check_size(width, height):
    """(width, height) as ints, or ValueError when either is not 1..MAX_SIDE."""
    w, h = int(width), int(height)
    if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
        raise ValueError('image size must be 1 to %d pixels a side, not %d x %d'
                         % (MAX_SIDE, w, h))
    return w, h


def fit_size(width, height, max_width=None, max_height=None):
    """(w, h) scaled down (never up) to fit max_width / max_height, keeping the
    aspect ratio; each side at least 1 pixel."""
    w, h = float(width), float(height)
    if w <= 0 or h <= 0:
        raise ValueError('an image needs a positive size')
    scale = 1.0
    if max_width:
        scale = min(scale, float(max_width) / w)
    if max_height:
        scale = min(scale, float(max_height) / h)
    return (max(1, int(round(w * scale))), max(1, int(round(h * scale))))


# ---- System.Drawing half (IronPython / .NET only) ---------------------------------


def _drawing():
    import clr
    clr.AddReference('System.Drawing')


def _ensure_folder(path):
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)


def save_bitmap(bitmap, path, quality=90, dispose=True):
    """Writes a System.Drawing image to path (format from the extension) and
    returns path. JPEG uses `quality` (1..100). Written to a temporary file beside
    the target then moved over it. Disposes the bitmap unless dispose=False.
    Raises IOError naming the path when GDI+ refuses (a locked file, a missing
    drive)."""
    _drawing()
    from System import Int64
    from System.Drawing.Imaging import (Encoder, EncoderParameter, EncoderParameters,
                                        ImageCodecInfo, ImageFormat)
    try:
        if bitmap is None:
            raise ValueError('there is no image to save')
        kind = format_for(path)
        path = os.path.abspath(str(path))
        _ensure_folder(path)
        temp = path + '.part'
        try:
            if kind == 'jpeg':
                codec = None
                for candidate in ImageCodecInfo.GetImageEncoders():
                    if candidate.MimeType == 'image/jpeg':
                        codec = candidate
                        break
                if codec is None:
                    bitmap.Save(temp, ImageFormat.Jpeg)
                else:
                    params = EncoderParameters(1)
                    params.Param[0] = EncoderParameter(Encoder.Quality, Int64(clamp_quality(quality)))
                    try:
                        bitmap.Save(temp, codec, params)
                    finally:
                        params.Dispose()
            elif kind == 'png':
                bitmap.Save(temp, ImageFormat.Png)
            else:
                bitmap.Save(temp, ImageFormat.Bmp)
            os.replace(temp, path) if hasattr(os, 'replace') else _move(temp, path)
        except Exception as error:
            try:
                if os.path.exists(temp):
                    os.remove(temp)
            except Exception:
                pass
            if isinstance(error, (ValueError, IOError)):
                raise
            raise IOError('Could not write the image to %s: %s' % (path, error))
        return path
    finally:
        if dispose and bitmap is not None:
            try:
                bitmap.Dispose()
            except Exception:
                pass


def _move(temp, path):
    if os.path.exists(path):
        os.remove(path)
    os.rename(temp, path)


def image_size(path):
    """(width, height) of an image file, read through System.Drawing without
    keeping the file locked."""
    _drawing()
    from System.Drawing import Image
    from System.IO import File, MemoryStream
    stream = MemoryStream(File.ReadAllBytes(str(path)))
    try:
        image = Image.FromStream(stream)
        try:
            return (int(image.Width), int(image.Height))
        finally:
            image.Dispose()
    finally:
        stream.Dispose()


def resize(image, width, height, background=None):
    """A new Bitmap of image scaled to width x height with high-quality bicubic
    sampling (edges clamped, so no grey seam). background ('RRGGBB') fills first,
    which JPEG targets need when the source has transparency. The caller disposes
    both images."""
    _drawing()
    from System.Drawing import Bitmap, Color, Graphics, GraphicsUnit, Rectangle
    from System.Drawing.Drawing2D import (CompositingQuality, InterpolationMode,
                                          PixelOffsetMode, SmoothingMode, WrapMode)
    from System.Drawing.Imaging import ImageAttributes
    out = Bitmap(int(width), int(height))
    graphics = Graphics.FromImage(out)
    attributes = ImageAttributes()
    try:
        if background:
            from namo import colors
            r, g, b = colors.hex_to_rgb(background)
            graphics.Clear(Color.FromArgb(255, r, g, b))
        graphics.InterpolationMode = InterpolationMode.HighQualityBicubic
        graphics.SmoothingMode = SmoothingMode.HighQuality
        graphics.PixelOffsetMode = PixelOffsetMode.HighQuality
        graphics.CompositingQuality = CompositingQuality.HighQuality
        attributes.SetWrapMode(WrapMode.TileFlipXY)
        graphics.DrawImage(image, Rectangle(0, 0, int(width), int(height)),
                           0, 0, int(image.Width), int(image.Height),
                           GraphicsUnit.Pixel, attributes)
    finally:
        attributes.Dispose()
        graphics.Dispose()
    return out


def thumbnail(src, dst, max_width=320, quality=85, max_height=None):
    """Writes a copy of the image at src scaled down to fit max_width (and
    max_height) into dst (format from dst's extension; JPEG gets a white
    background). Never scales up. Returns dst. The source file is not locked."""
    _drawing()
    from System.Drawing import Image
    from System.IO import File, MemoryStream
    stream = MemoryStream(File.ReadAllBytes(str(src)))
    try:
        image = Image.FromStream(stream)
        try:
            w, h = fit_size(image.Width, image.Height, max_width, max_height)
            background = 'FFFFFF' if format_for(dst) == 'jpeg' else None
            scaled = resize(image, w, h, background)
        finally:
            image.Dispose()
    finally:
        stream.Dispose()
    return save_bitmap(scaled, dst, quality)


# ---- Navisworks half --------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def style_enum(style):
    """Api.ImageGenerationStyle for 'scene' / 'overlay' / 'raytrace', an enum
    member name, or an enum value passed through."""
    from pynavis._api import Api
    if not isinstance(style, str):
        return style
    name = STYLES.get(style.lower(), style)
    value = getattr(Api.ImageGenerationStyle, name, None)
    if value is None:
        raise ValueError('unknown image style %r (use %s)' % (style, ', '.join(sorted(STYLES))))
    return value


def capture(path, width=1920, height=1080, doc=None, style='scene', sectioning=True,
            quality=90):
    """Renders the current view (Document.GenerateImage) to path (.png/.jpg/.bmp)
    and returns path. sectioning=False renders as if the section were off."""
    w, h = check_size(width, height)
    format_for(path)
    bitmap = _doc(doc).GenerateImage(style_enum(style), w, h, bool(sectioning))
    if bitmap is None:
        raise RuntimeError('Navisworks returned no image for the current view')
    return save_bitmap(bitmap, path, quality)


def capture_saved(saved_viewpoint, path, **kw):
    """Makes saved_viewpoint current (camera, sections and any hide/override state
    it stores), then capture(path, **kw). Wrap a batch in ViewKeeper."""
    document = _doc(kw.get('doc'))
    document.SavedViewpoints.CurrentSavedViewpoint = saved_viewpoint
    kw['doc'] = document
    return capture(path, **kw)


def clash(result, path, width=640, height=360, doc=None, style='scene', quality=90):
    """The clash result's own image (DocumentClashTests.TestsImageForResult: its
    viewpoint with the clashing pair highlighted) written to path; returns path."""
    w, h = check_size(width, height)
    format_for(path)
    from pynavis import clash as _clash
    data = _clash.get_clash(_doc(doc)).TestsData
    bitmap = data.TestsImageForResult(result, style_enum(style), w, h)
    if bitmap is None:
        raise RuntimeError('Navisworks returned no image for the clash')
    return save_bitmap(bitmap, path, quality)


class ViewKeeper(object):
    """with images.ViewKeeper(): ... remembers the camera (a CreateCopy of the
    current viewpoint) and the current saved viewpoint, and puts both back on exit,
    even after an exception. Restoring re-applies that saved viewpoint (so a view
    that carries hidden items or overrides brings them back), then the exact
    camera. restore_saved=False restores the camera only. Never raises on exit."""

    def __init__(self, doc=None, restore_saved=True):
        self.doc = doc
        self.restore_saved = restore_saved
        self.viewpoint = None
        self.saved = None

    def __enter__(self):
        self.doc = _doc(self.doc)
        self.viewpoint = self.doc.CurrentViewpoint.CreateCopy()
        try:
            self.saved = self.doc.SavedViewpoints.CurrentSavedViewpoint
        except Exception:
            self.saved = None
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.restore_saved and self.saved is not None:
            try:
                self.saved.DisplayName          # a dead handle throws here
                self.doc.SavedViewpoints.CurrentSavedViewpoint = self.saved
            except Exception:
                pass
        if self.viewpoint is not None:
            try:
                self.doc.CurrentViewpoint.CopyFrom(self.viewpoint)
            except Exception:
                pass
        return False

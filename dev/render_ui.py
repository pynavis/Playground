# Renders namo.ui windows offscreen to PNG for visual review.
# Run through the harness: powershell -STA -File dev/ipy.ps1 dev/render_ui.py OUTDIR
import os, sys
import clr
clr.AddReference('PresentationFramework'); clr.AddReference('PresentationCore'); clr.AddReference('WindowsBase')
from System.Windows import Size, Rect, Point, WindowStartupLocation
from System.Windows.Media import PixelFormats
from System.Windows.Media.Imaging import RenderTargetBitmap, PngBitmapEncoder, BitmapFrame
from System.IO import FileStream, FileMode
from namo import ui

OUT = sys.argv[1]
dark = len(sys.argv) > 2 and sys.argv[2] == 'dark'
try:
    from PyNavis.Runtime.Output import PyNavisTheme
except Exception:
    PyNavisTheme = None

def render(window, name):
    window.Left = -10000; window.Top = -10000
    window.ShowActivated = False
    window.Show()
    content = window.Content
    w = int(window.ActualWidth); h = int(window.ActualHeight)
    rtb = RenderTargetBitmap(max(w, 1), max(h, 1), 96, 96, PixelFormats.Pbgra32)
    rtb.Render(content)
    enc = PngBitmapEncoder(); enc.Frames.Add(BitmapFrame.Create(rtb))
    fs = FileStream(os.path.join(OUT, name + ('-dark' if dark else '') + '.png'), FileMode.Create)
    enc.Save(fs); fs.Close()
    window.Close()

fields = [
    {'kind': 'label', 'text': 'Pick what to colour and how.'},
    {'kind': 'choice', 'key': 'prop', 'label': 'Property', 'options': ['Element > Category', 'Element > Level', 'Item > Layer'], 'default': 'Element > Level'},
    {'kind': 'text', 'key': 'name', 'label': 'Set name', 'default': 'Ducts on L3', 'hint': 'Tokens: {value}, {date}'},
    {'kind': 'number', 'key': 'tol', 'label': 'Tolerance (mm)', 'default': 25, 'min': 0, 'max': 500},
    {'kind': 'check', 'key': 'ghost', 'label': 'Ghost everything else', 'default': True},
    {'kind': 'radio', 'key': 'scope', 'label': 'Scope', 'options': ['Selection', 'Visible', 'Whole model'], 'default': 'Visible'},
    {'kind': 'multi', 'key': 'vals', 'label': 'Values', 'options': ['Level 1', 'Level 2', 'Level 3', 'Roof'], 'checked': ['Level 1', 'Roof']},
    {'kind': 'folder', 'key': 'folder', 'label': 'Output folder', 'default': r'C:\Projects\Tower\Reports'},
    {'kind': 'color', 'key': 'col', 'label': 'Colour', 'default': '0078D4'},
    {'kind': 'date', 'key': 'due', 'label': 'Due', 'default': '2026-10-12'},
]
render(ui.build_form('Color by Property', fields, intro='Colours every visible object by one property value.'), 'form')
rows = [{'value': i, 'cells': ['Ducts vs Pipes %d' % i, 'Active', '%d' % (i * 37), 'Level %d' % (i % 5)]} for i in range(1, 30)]
render(ui.build_choose('Choose clash tests', rows, ['Test', 'Status', 'Clashes', 'Level'], checked=[1, 3]), 'choose')
render(ui.build_table('Clash hotspots', ['Element', 'Category', 'Clashes', 'Model'], [{'value': i, 'cells': ['Duct %d' % i, 'Ducts', str(100 - i), 'MEP.nwc']} for i in range(40)], actions=[('Select', lambda v: None), ('Export', lambda v: None)], status='40 elements'), 'table')
print('rendered')

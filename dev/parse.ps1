# Parses the Playground root with the REAL pyNavis BundleParser (PyNavis.Runtime.dll), the same
# code Navisworks runs at Reload, and prints what the ribbon would contain plus every
# problem or skip the parser logged. No Navisworks needed.
#
#   powershell -NoProfile -STA -ExecutionPolicy Bypass -File dev\parse.ps1 [-Json out.json]
param([string]$Json = '')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$rt = Join-Path $env:APPDATA 'pyNavis\2026\runtime'
# Fallback: a pyNavis checkout's build output (PYNAVIS_SRC, else a 'pyNavis' folder beside this repo).
$src = if ($env:PYNAVIS_SRC) { $env:PYNAVIS_SRC } else { Join-Path (Split-Path -Parent $root) 'pyNavis' }
if (-not (Test-Path $rt)) { $rt = Join-Path $src 'bin\2026\runtime' }
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
$asm = [Reflection.Assembly]::LoadFrom((Join-Path $rt 'PyNavis.Runtime.dll'))
$logFile = Join-Path $env:TEMP 'playground-parse.log'
if (Test-Path $logFile) { Remove-Item $logFile }
$asm.GetType('PyNavis.Runtime.Log').GetField('_path', [Reflection.BindingFlags]'NonPublic, Static').SetValue($null, $logFile)

$parser = $asm.GetType('PyNavis.Runtime.Bundles.BundleParser')
$exts = $parser.GetMethod("ParseRoot").Invoke($null, [object[]]@([string]$root))

$report = @()
$buttons = 0
foreach ($e in $exts) {
  "EXTENSION $($e.Name)  engine=$($e.DefaultEngineId)  hooks=$($e.Hooks.Count)  startup=$([bool]$e.StartupScriptPath)"
  foreach ($p in $e.Problems) { "  PROBLEM $p" }
  foreach ($t in $e.Tabs) {
    "  TAB $($t.Title)"
    foreach ($panel in $t.Panels) {
      $line = "    PANEL $($panel.Title):"
      foreach ($item in $panel.Items) {
        $kind = $item.GetType().Name -replace 'Model$', ''
        $title = ''
        try { $title = $item.Title } catch {}
        if (-not $title) { try { $title = ($item.Buttons | ForEach-Object { $_.Title }) -join ' | ' } catch {} }
        $line += "`n      $kind  $title"
      }
      if ($panel.Slideout.Count) {
        foreach ($item in $panel.Slideout) { $line += "`n      (slideout) $($item.GetType().Name -replace 'Model$','')  $($item.Title)" }
      }
      $line
      foreach ($b in $panel.Buttons) {
        $buttons++
        $report += [pscustomobject]@{
          key = $b.BundleKey; title = $b.Title; tooltip = $b.Tooltip; shortcut = $b.Shortcut
          engine = $b.EngineId; config = [bool]$b.ConfigScriptPath; icon = [bool]$b.IconPath
          smallIcon = [bool]$b.SmallIconPath; dark = [bool]$b.DarkIconPath; noUi = $b.NoUi; toggle = $b.IsToggle
          tab = $t.Title; panel = $panel.Title
        }
      }
    }
  }
}
"BUTTONS $buttons"
if (Test-Path $logFile) {
  "--- parser log ---"
  Get-Content $logFile | ForEach-Object { $_ -replace '^\S+ \S+ ', '' }
}
if ($Json) { $report | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $Json }

# Runs a Python file under the SAME IronPython 3.4 that pyNavis ships, outside Navisworks.
#
#   powershell -NoProfile -STA -ExecutionPolicy Bypass -File dev\ipy.ps1 dev\ipy_driver.py [args...]
#
# Search path order mirrors a pyNavis bundle run: bundled stdlib, pynavislib, the
# extension's lib\, then dev\tests (so test helpers import). PyNavis.Runtime.dll and the
# WPF assemblies are loaded so pynavis.forms / DesignSystem / WPF objects can be built
# (never shown modally). The Navisworks API is NOT available: anything importing
# pynavis._api raises ImportError here, which is why tools keep a pure half.
param([Parameter(Mandatory = $true)][string]$Script, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$rt = Join-Path $env:APPDATA 'pyNavis\2026\runtime'
# Fallback: a pyNavis checkout's build output (PYNAVIS_SRC, else a 'pyNavis' folder beside this repo).
$src = if ($env:PYNAVIS_SRC) { $env:PYNAVIS_SRC } else { Join-Path (Split-Path -Parent $root) 'pyNavis' }
if (-not (Test-Path $rt)) { $rt = Join-Path $src 'bin\2026\runtime' }

foreach ($a in 'PresentationFramework', 'PresentationCore', 'WindowsBase', 'System.Xaml', 'System.Windows.Forms', 'WindowsFormsIntegration', 'System.Drawing') {
  Add-Type -AssemblyName $a
}
foreach ($d in 'Microsoft.Scripting.dll', 'Microsoft.Dynamic.dll', 'IronPython.dll', 'IronPython.Modules.dll', 'IronPython.Wpf.dll', 'IronPython.SQLite.dll') {
  $p = Join-Path $rt $d
  if (Test-Path $p) { [void][Reflection.Assembly]::LoadFrom($p) }
}

# Keep the runtime's own log out of the user's pyNavis.log.
try {
  $runtimeAsm = [Reflection.Assembly]::LoadFrom((Join-Path $rt 'PyNavis.Runtime.dll'))
  $logType = $runtimeAsm.GetType('PyNavis.Runtime.Log')
  $logFile = Join-Path $env:TEMP 'playground-harness-runtime.log'
  $logType.GetField('_path', [Reflection.BindingFlags]'NonPublic, Static').SetValue($null, $logFile)
} catch { Write-Warning "PyNavis.Runtime not loaded: $($_.Exception.Message)" }

$scriptPath = [string](Resolve-Path $Script).Path
$searchPaths = @((Join-Path $rt 'lib'), (Join-Path $rt 'pynavislib'), (Join-Path $root 'Playground.extension\lib'),
                 (Join-Path $root 'dev\tests'), (Join-Path $root 'dev'))
$argList = @($scriptPath) + @($Rest | Where-Object { $_ })

function PyList($items) { '[' + (($items | ForEach-Object { "r'" + ([string]$_).Replace("'", "") + "'" }) -join ', ') + ']' }

$engine = [IronPython.Hosting.Python]::CreateEngine()
$engine.Runtime.IO.SetOutput([Console]::OpenStandardOutput(), [Text.Encoding]::UTF8)
$engine.Runtime.IO.SetErrorOutput([Console]::OpenStandardError(), [Text.Encoding]::UTF8)
$scope = $engine.CreateScope()
$boot = "import sys`nsys.path[0:0] = $(PyList $searchPaths)`nsys.argv = $(PyList $argList)`n__file__ = r'$scriptPath'`n"
try {
  [void]$engine.Execute($boot, $scope)
  $source = $engine.CreateScriptSourceFromFile($scriptPath, [Text.Encoding]::UTF8)
  [void]$source.Execute($scope)
  $code = 0
  if ($scope.ContainsVariable('EXIT_CODE')) { $code = [int]$scope.GetVariable('EXIT_CODE') }
  exit $code
} catch {
  $ex = $_.Exception
  while ($ex.InnerException -and $ex -is [System.Management.Automation.MethodInvocationException]) { $ex = $ex.InnerException }
  try {
    $ops = $engine.GetService([Microsoft.Scripting.Hosting.ExceptionOperations])
    [Console]::Error.WriteLine($ops.FormatException($ex))
  } catch { [Console]::Error.WriteLine($ex.ToString()) }
  exit 1
}

# Dumps the public surface of the Navisworks .NET assemblies to dev\api\<Assembly>.txt,
# one line per member, so every API name a Playground tool uses can be grepped before it is
# trusted. Reflection-only: no Navisworks process is started.
#
#   powershell -NoProfile -File dev\apidump.ps1 [-Year 2026]
param([int]$Year = 2026)

$nw = "D:\Program Files\Autodesk\Navisworks Manage $Year"
$out = Join-Path $PSScriptRoot 'api'
New-Item -ItemType Directory -Force $out | Out-Null

$names = @(
  'Autodesk.Navisworks.Api', 'Autodesk.Navisworks.Clash', 'Autodesk.Navisworks.Timeliner',
  'Autodesk.Navisworks.Takeoff', 'Autodesk.Navisworks.ComApi', 'Autodesk.Navisworks.Interop.ComApi',
  'AdWindows'
)

[AppDomain]::CurrentDomain.add_ReflectionOnlyAssemblyResolve({
  param($s, $e)
  $short = ($e.Name -split ',')[0]
  $candidate = Join-Path $nw ($short + '.dll')
  if (Test-Path $candidate) { return [Reflection.Assembly]::ReflectionOnlyLoadFrom($candidate) }
  try { return [Reflection.Assembly]::ReflectionOnlyLoad($e.Name) } catch { return $null }
})

function TypeName($t) {
  if ($t -eq $null) { return 'void' }
  try {
    if ($t.IsGenericType) {
      $base = $t.Name -replace '`\d+$', ''
      $args = ($t.GetGenericArguments() | ForEach-Object { TypeName $_ }) -join ', '
      return "$base<$args>"
    }
    return $t.Name
  } catch { return '?' }
}

$flags = [Reflection.BindingFlags]'Public, Instance, Static, DeclaredOnly'

foreach ($n in $names) {
  $path = Join-Path $nw ($n + '.dll')
  if (-not (Test-Path $path)) { continue }
  $asm = [Reflection.Assembly]::ReflectionOnlyLoadFrom($path)
  $lines = New-Object System.Collections.Generic.List[string]
  try { $types = $asm.GetExportedTypes() } catch [Reflection.ReflectionTypeLoadException] {
    $types = $_.Exception.Types | Where-Object { $_ -ne $null -and $_.IsPublic }
  }
  foreach ($t in ($types | Sort-Object FullName)) {
    try {
      $kind = if ($t.IsEnum) { 'enum' } elseif ($t.IsInterface) { 'interface' } elseif ($t.IsValueType) { 'struct' } else { 'class' }
      $base = if ($t.BaseType) { ' : ' + $t.BaseType.FullName } else { '' }
      $lines.Add("$kind $($t.FullName)$base")
      if ($t.IsEnum) {
        foreach ($f in $t.GetFields([Reflection.BindingFlags]'Public, Static')) { $lines.Add("  $($t.FullName).$($f.Name) = enum value") }
        continue
      }
      foreach ($c in $t.GetConstructors()) {
        $ps = ($c.GetParameters() | ForEach-Object { (TypeName $_.ParameterType) + ' ' + $_.Name }) -join ', '
        $lines.Add("  $($t.FullName)::.ctor($ps)")
      }
      foreach ($p in $t.GetProperties($flags)) {
        $acc = @(); if ($p.CanRead -and $p.GetGetMethod()) { $acc += 'get' }; if ($p.CanWrite -and $p.GetSetMethod()) { $acc += 'set' }
        $static = if (($p.GetGetMethod() -and $p.GetGetMethod().IsStatic)) { 'static ' } else { '' }
        $idx = $p.GetIndexParameters()
        $ix = if ($idx.Count) { '[' + (($idx | ForEach-Object { TypeName $_.ParameterType }) -join ', ') + ']' } else { '' }
        $lines.Add("  $($t.FullName)::$($p.Name)$ix : $static$(TypeName $p.PropertyType) {$($acc -join ';')}")
      }
      foreach ($m in $t.GetMethods($flags)) {
        if ($m.IsSpecialName) { continue }
        $ps = ($m.GetParameters() | ForEach-Object { (TypeName $_.ParameterType) + ' ' + $_.Name }) -join ', '
        $static = if ($m.IsStatic) { 'static ' } else { '' }
        $lines.Add("  $($t.FullName)::$($m.Name)($ps) -> $static$(TypeName $m.ReturnType)")
      }
      foreach ($e in $t.GetEvents($flags)) { $lines.Add("  $($t.FullName)::$($e.Name) : event $(TypeName $e.EventHandlerType)") }
      foreach ($f in $t.GetFields($flags)) {
        $static = if ($f.IsStatic) { 'static ' } else { '' }
        $lines.Add("  $($t.FullName)::$($f.Name) : field $static$(TypeName $f.FieldType)")
      }
    } catch { $lines.Add("  !! $($t.FullName): $($_.Exception.Message)") }
  }
  $file = Join-Path $out ($n + '.txt')
  [IO.File]::WriteAllLines($file, $lines)
  "{0}: {1} lines" -f $n, $lines.Count
}

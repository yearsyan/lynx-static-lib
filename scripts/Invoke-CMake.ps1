$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Find-CMake() {
  $command = Get-Command cmake.exe -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  $candidateDirs = @(
    (Join-Path $env:ProgramFiles 'CMake\bin'),
    (Join-Path ${env:ProgramFiles(x86)} 'CMake\bin'),
    (Join-Path $env:LOCALAPPDATA 'Programs\CMake\bin')
  )

  $vsRoot = 'C:\Program Files\Microsoft Visual Studio\2022'
  foreach ($edition in @('BuildTools', 'Community', 'Professional', 'Enterprise')) {
    $candidateDirs += Join-Path $vsRoot "$edition\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin"
  }

  foreach ($dir in $candidateDirs) {
    if (-not $dir) {
      continue
    }

    $candidate = Join-Path $dir 'cmake.exe'
    if (Test-Path -LiteralPath $candidate) {
      return $candidate
    }
  }

  if (Test-Path -LiteralPath $vsRoot) {
    $found = Get-ChildItem -LiteralPath $vsRoot -Recurse -Filter cmake.exe -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match '\\CommonExtensions\\Microsoft\\CMake\\CMake\\bin\\cmake\.exe$' } |
      Sort-Object FullName |
      Select-Object -First 1
    if ($found) {
      return $found.FullName
    }
  }

  throw @"
cmake.exe was not found.
Install CMake or the Visual Studio 2022 C++ CMake tools component, then rerun the workflow.
"@
}

$cmake = Find-CMake
Write-Host "Using CMake: $cmake"
& $cmake @args
if ((Test-Path -LiteralPath variable:/LASTEXITCODE)) {
  exit $LASTEXITCODE
}

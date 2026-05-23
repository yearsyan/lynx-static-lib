param(
  [ValidateSet('deps', 'sdk', 'static', 'explorer', 'all')]
  [string]$Target = 'all',
  [string]$LynxRoot = (Join-Path $PSScriptRoot '..\third_party\lynx'),
  [string]$OutDir = (Join-Path $PSScriptRoot '..\out\lynx\Default'),
  [switch]$SkipDeps
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Resolve-ExistingPath([string]$Path, [string]$Name) {
  $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
  if (-not $resolved) {
    throw "$Name not found: $Path"
  }
  return $resolved.Path
}

function Find-MsvcTool([string]$ToolName) {
  $candidate = Get-Command $ToolName -ErrorAction SilentlyContinue
  if ($candidate) {
    return $candidate.Source
  }

  $vsRoot = 'C:\Program Files\Microsoft Visual Studio\2022'
  if (Test-Path -LiteralPath $vsRoot) {
    $found = Get-ChildItem -LiteralPath $vsRoot -Recurse -Filter $ToolName -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match '\\bin\\Hostx64\\x64\\' } |
      Select-Object -First 1
    if ($found) {
      return $found.FullName
    }
  }
  return $null
}

function Set-VisualStudioEnvironment() {
  $vsCommunity = 'C:\Program Files\Microsoft Visual Studio\2022\Community'
  $realVsRoot = $env:GYP_MSVS_OVERRIDE_PATH
  if (-not $env:GYP_MSVS_OVERRIDE_PATH -and (Test-Path -LiteralPath $vsCommunity)) {
    $realVsRoot = $vsCommunity
  }
  if (-not $realVsRoot) {
    throw "Visual Studio 2022 was not found. Install VS 2022 C++ build tools before building Lynx for Windows."
  }

  $vcVars = Join-Path $realVsRoot 'VC\Auxiliary\Build\vcvarsall.bat'
  if (-not (Test-Path -LiteralPath $vcVars)) {
    throw "vcvarsall.bat not found under Visual Studio root: $realVsRoot"
  }

  $vsClang = Join-Path $realVsRoot 'VC\Tools\Llvm\x64\bin\clang-cl.exe'
  $vsLld = Join-Path $realVsRoot 'VC\Tools\Llvm\x64\bin\lld-link.exe'
  if (-not (Test-Path -LiteralPath $vsClang) -or -not (Test-Path -LiteralPath $vsLld)) {
    throw @"
Lynx's Windows GN toolchain requires the Visual Studio LLVM/Clang toolset.
Install Visual Studio component:
  Microsoft.VisualStudio.ComponentGroup.NativeDesktop.Llvm.Clang
Expected:
  $vsClang
  $vsLld
"@
  }

  $env:GYP_MSVS_OVERRIDE_PATH = $realVsRoot

  $sdkRoot = 'C:\Program Files (x86)\Windows Kits\10'
  if (-not $env:WINDOWSSDKDIR -and (Test-Path -LiteralPath $sdkRoot)) {
    $env:WINDOWSSDKDIR = $sdkRoot
  }

  $env:DEPOT_TOOLS_WIN_TOOLCHAIN = '0'

  $python = Get-Command python.exe -ErrorAction SilentlyContinue
  if (-not $python) {
    throw "python.exe is required by Lynx GN scripts"
  }

  $shimDir = Join-Path $script:RepoRoot 'third_party\_cache\python-shim'
  New-Item -ItemType Directory -Force -Path $shimDir | Out-Null
  $shim = Join-Path $shimDir 'python3.cmd'
  "@echo off`r`n`"$($python.Source)`" %*" |
    Set-Content -LiteralPath $shim -Encoding ASCII
  Copy-Item -LiteralPath $python.Source -Destination (Join-Path $shimDir 'python3.exe') -Force
  $env:PATH = "$shimDir;$([IO.Path]::GetDirectoryName($python.Source));$env:PATH"
}

function Test-VisualStudioClang() {
  if (-not $env:GYP_MSVS_OVERRIDE_PATH) {
    return $false
  }
  $clang = Join-Path $env:GYP_MSVS_OVERRIDE_PATH 'VC\Tools\Llvm\x64\bin\clang-cl.exe'
  return (Test-Path -LiteralPath $clang)
}

function Get-GnArgs([bool]$UseClang) {
  $useClangValue = if ($UseClang) { 'true' } else { 'false' }
@"
desktop_enable_embedder_layer = true
enable_clay_standalone = true
disable_visibility_hidden = true
use_flutter_cxx = false
use_ndk_static_cxx = false
enable_linker_map = false
enable_clay = true
is_headless = true
skia_enable_flutter_defines = true
skia_use_dng_sdk = false
skia_use_sfntly = false
skia_enable_pdf = false
skia_enable_svg = true
enable_svg = true
skia_enable_skottie = true
skia_use_x11 = false
skia_use_wuffs = true
skia_use_expat = true
skia_use_fontconfig = false
clay_enable_skshaper = true
skia_use_icu = true
allow_deprecated_api_calls = true
stripped_symbols = true
is_official_build = true
enable_lto = false
lynx_export_symbols = false
base_export_symbols = false
lynx_static_link = true
is_clang = $useClangValue
enable_lepusng_worklet = true
enable_napi_binding = true
is_debug = false
enable_inspector = true
enable_libcpp_abi_namespace_cr = false
jsengine_type = "quickjs"
"@
}

function Invoke-GnGen([string]$Gn, [string]$OutDir, [string]$SourceRoot, [bool]$UseClang) {
  $gnArgs = Get-GnArgs -UseClang $UseClang
  New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
  Set-Content -LiteralPath (Join-Path $OutDir 'args.gn') -Value $gnArgs -Encoding ASCII
  Write-Host "Generating GN build: $OutDir"
  Push-Location -LiteralPath $SourceRoot
  try {
    & $Gn gen $OutDir --ide=vs
    if ($LASTEXITCODE -ne 0) {
      throw "gn gen failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Invoke-NinjaTarget([string]$Ninja, [string]$OutDir, [string]$NinjaTarget) {
  Write-Host "Building GN target: $NinjaTarget"
  & $Ninja -C $OutDir $NinjaTarget
  if ($LASTEXITCODE -ne 0) {
    throw "ninja target '$NinjaTarget' failed with exit code $LASTEXITCODE"
  }
}

function New-StaticArchive([string]$OutDir) {
  $objRoot = Join-Path $OutDir 'obj'
  if (-not (Test-Path -LiteralPath $objRoot)) {
    throw "GN object directory does not exist: $objRoot"
  }

  $objects = Get-ChildItem -LiteralPath $objRoot -Recurse -Filter '*.obj' |
    Where-Object {
      $_.FullName -notmatch '\\obj\\explorer\\' -and
      $_.FullName -notmatch '\\obj\\testing\\'
    } |
    Sort-Object FullName

  if ($objects.Count -eq 0) {
    throw "No object files found under $objRoot"
  }

  $libraries = @()
  $boringSslAsm = Join-Path $objRoot 'third_party\boringssl\boringssl_asm.lib'
  if (Test-Path -LiteralPath $boringSslAsm) {
    $libraries += Get-Item -LiteralPath $boringSslAsm
  }

  $archive = Join-Path $OutDir 'lynx_static.lib'
  $rsp = Join-Path $OutDir 'lynx_static.objects.rsp'
  @($objects + $libraries) | ForEach-Object { '"' + $_.FullName + '"' } |
    Set-Content -LiteralPath $rsp -Encoding ASCII

  $lib = Find-MsvcTool 'lib.exe'
  if (-not $lib) {
    $lib = Find-MsvcTool 'llvm-lib.exe'
  }
  if (-not $lib) {
    throw "Could not find lib.exe or llvm-lib.exe"
  }

  Write-Host "Archiving $($objects.Count) official Lynx object files and $($libraries.Count) static libraries into $archive"
  & $lib /NOLOGO "/OUT:$archive" "@$rsp"
  if ($LASTEXITCODE -ne 0) {
    throw "Static archive creation failed with exit code $LASTEXITCODE"
  }
}

$repoRoot = Resolve-ExistingPath (Join-Path $PSScriptRoot '..') 'lynxlib root'
$script:RepoRoot = $repoRoot
$lynx = Resolve-ExistingPath $LynxRoot 'Lynx source root'
$out = [IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force -Path $out | Out-Null

if (-not $SkipDeps -or $Target -eq 'deps') {
  & (Join-Path $PSScriptRoot 'Sync-LynxDeps.ps1') -LynxRoot $lynx
}
if ($Target -eq 'deps') {
  return
}

Set-VisualStudioEnvironment
$useClang = Test-VisualStudioClang
if (-not $useClang) {
  throw "Visual Studio LLVM clang-cl.exe was not found after environment setup."
}
Write-Host "Using Visual Studio LLVM clang-cl.exe toolchain."

$pyDeps = Join-Path $lynx 'third_party\py_deps'
if (Test-Path -LiteralPath $pyDeps) {
  $env:PYTHONPATH = if ($env:PYTHONPATH) { "$pyDeps;$env:PYTHONPATH" } else { $pyDeps }
}

$gn = Join-Path $lynx 'buildtools\gn\gn.exe'
$ninja = Join-Path $lynx 'buildtools\ninja\ninja.exe'
if (-not (Test-Path -LiteralPath $gn)) {
  throw "GN not found after dependency sync: $gn"
}
if (-not (Test-Path -LiteralPath $ninja)) {
  throw "Ninja not found after dependency sync: $ninja"
}

Invoke-GnGen -Gn $gn -OutDir $out -SourceRoot $lynx -UseClang $useClang

switch ($Target) {
  'sdk' {
    Invoke-NinjaTarget -Ninja $ninja -OutDir $out -NinjaTarget 'platform/windows:package_sdk'
  }
  'static' {
    Invoke-NinjaTarget -Ninja $ninja -OutDir $out -NinjaTarget 'platform/windows:windows'
    New-StaticArchive -OutDir $out
  }
  'explorer' {
    Invoke-NinjaTarget -Ninja $ninja -OutDir $out -NinjaTarget 'explorer'
  }
  'all' {
    Invoke-NinjaTarget -Ninja $ninja -OutDir $out -NinjaTarget 'platform/windows:package_sdk'
    Invoke-NinjaTarget -Ninja $ninja -OutDir $out -NinjaTarget 'platform/windows:windows'
    New-StaticArchive -OutDir $out
    Invoke-NinjaTarget -Ninja $ninja -OutDir $out -NinjaTarget 'explorer'
  }
}

Write-Host "Lynx Windows target '$Target' completed."

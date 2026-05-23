param(
  [string]$LynxRoot = (Join-Path $PSScriptRoot '..\third_party\lynx')
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')
$manifestPath = Join-Path $repoRoot 'third_party\official_deps.manifest.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json

function Apply-GitPatches([string]$RepoPath, [string]$PatchDir, [string]$Label) {
  if (-not (Test-Path -LiteralPath $PatchDir)) {
    return
  }

  Get-ChildItem -LiteralPath $PatchDir -Filter '*.patch' | Sort-Object Name | ForEach-Object {
    Write-Host "Applying local $Label compatibility patch: $($_.Name)"
    & git -C $RepoPath apply --check $_.FullName 2>$null
    if ($LASTEXITCODE -eq 0) {
      & git -C $RepoPath apply $_.FullName
      if ($LASTEXITCODE -ne 0) {
        throw "Failed to apply patch: $($_.FullName)"
      }
      return
    }

    & git -C $RepoPath apply --reverse --check $_.FullName 2>$null
    if ($LASTEXITCODE -eq 0) {
      Write-Host "Patch already applied: $($_.Name)"
      return
    }

    throw "Patch cannot be applied cleanly: $($_.FullName)"
  }
}

$resolvedLynx = Resolve-Path -LiteralPath $LynxRoot -ErrorAction SilentlyContinue
if (-not $resolvedLynx) {
  throw "Lynx submodule not found at '$LynxRoot'. Run: git submodule update --init --recursive"
}

$actualCommit = (& git -C $resolvedLynx.Path rev-parse HEAD).Trim()
if ($actualCommit -ne $manifest.lynx.commit) {
  throw "Lynx submodule commit mismatch. Expected $($manifest.lynx.commit), got $actualCommit"
}

$cacheDir = Join-Path $repoRoot 'third_party\_cache'
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

$habPath = Join-Path $cacheDir "hab-$($manifest.habitat.version).exe"
if (-not (Test-Path -LiteralPath $habPath)) {
  Write-Host "Downloading Habitat $($manifest.habitat.version)..."
  Invoke-WebRequest -Uri $manifest.habitat.windows_url -OutFile $habPath
}

$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $habPath).Hash.ToLowerInvariant()
if ($actualHash -ne $manifest.habitat.windows_sha256) {
  throw "Habitat checksum mismatch. Expected $($manifest.habitat.windows_sha256), got $actualHash"
}

Write-Host "Using Habitat $($manifest.habitat.version): $habPath"

foreach ($target in $manifest.sync_targets) {
  if ($target -eq 'default') {
    Write-Host "Synchronizing Lynx default dependencies..."
    & $habPath sync $resolvedLynx.Path
  } else {
    Write-Host "Synchronizing Lynx dependency target '$target'..."
    & $habPath sync $resolvedLynx.Path --target $target
  }
  if ($LASTEXITCODE -ne 0) {
    throw "hab sync failed for target '$target' with exit code $LASTEXITCODE"
  }
}

if ($manifest.node) {
  $packageManager = [string]$manifest.node.package_manager
  $workspace = [string]$manifest.node.weak_node_api_workspace
  $nodeDir = Join-Path $resolvedLynx.Path 'buildtools\node'
  $pnpm = Join-Path $nodeDir 'pnpm.CMD'
  if (-not (Test-Path -LiteralPath $pnpm)) {
    throw "Official Lynx pnpm was not found after dependency sync: $pnpm"
  }

  $lockFile = Join-Path $resolvedLynx.Path 'pnpm-lock.yaml'
  $lockHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $lockFile).Hash.ToLowerInvariant()
  $fullInstallStamp = Join-Path $cacheDir "pnpm-full-workspace-$lockHash.stamp"
  $explorerDependency = Join-Path $resolvedLynx.Path 'devtool\base_devtool\js_libraries\logbox\node_modules\source-map\lib\mappings.wasm'
  if (-not (Test-Path -LiteralPath $fullInstallStamp) -or -not (Test-Path -LiteralPath $explorerDependency)) {
    Write-Host "Installing full Lynx pnpm workspace with $packageManager..."
    Push-Location -LiteralPath $resolvedLynx.Path
    try {
      $env:PATH = "$nodeDir;$env:PATH"
      & $pnpm install --frozen-lockfile
      if ($LASTEXITCODE -ne 0) {
        throw "pnpm install failed with exit code $LASTEXITCODE"
      }
      Set-Content -LiteralPath $fullInstallStamp -Value $lockHash -Encoding ASCII
    } finally {
      Pop-Location
    }
  } else {
    Write-Host "Full Lynx pnpm workspace is already installed for lock hash $lockHash."
  }

  $expectedPackage = Join-Path $resolvedLynx.Path 'third_party\weak-node-api\node_modules\@lynx-js\weak-node-api'
  $hoistedPackage = Join-Path $resolvedLynx.Path 'node_modules\@lynx-js\weak-node-api'

  if (-not (Test-Path -LiteralPath $expectedPackage)) {
    Write-Host "Installing Lynx node workspace dependency '$workspace' with $packageManager..."
    Push-Location -LiteralPath $resolvedLynx.Path
    try {
      $env:PATH = "$nodeDir;$env:PATH"
      & $pnpm install --filter $workspace --frozen-lockfile
      if ($LASTEXITCODE -ne 0) {
        throw "pnpm install failed with exit code $LASTEXITCODE"
      }
    } finally {
      Pop-Location
    }
  }

  if (-not (Test-Path -LiteralPath $expectedPackage)) {
    if (-not (Test-Path -LiteralPath $hoistedPackage)) {
      throw "weak-node-api package was not installed at '$expectedPackage' or '$hoistedPackage'"
    }

    $expectedParent = Split-Path -Parent $expectedPackage
    New-Item -ItemType Directory -Force -Path $expectedParent | Out-Null
    Write-Host "Copying hoisted weak-node-api package to the official GN script location..."
    Copy-Item -LiteralPath $hoistedPackage -Destination $expectedPackage -Recurse -Force
  }
}

Apply-GitPatches -RepoPath $resolvedLynx.Path `
                 -PatchDir (Join-Path $repoRoot 'patches\lynx') `
                 -Label 'Lynx'
Apply-GitPatches -RepoPath (Join-Path $resolvedLynx.Path 'third_party\quickjs\src') `
                 -PatchDir (Join-Path $repoRoot 'patches\quickjs-src') `
                 -Label 'QuickJS'

Write-Host "Pinned official Lynx dependencies are ready."
